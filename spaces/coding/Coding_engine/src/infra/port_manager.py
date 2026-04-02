"""
Port Manager für dynamische Port-Zuweisung bei parallelen Container-Runs.

Dieses Modul ermöglicht:
1. Automatische Erkennung freier Ports im definierten Range
2. Thread-sichere Port-Allokation für parallele Container
3. Automatisches Freigeben von Ports nach Container-Ende
4. Tracking aller aktiven Port-Zuweisungen

Usage:
    from src.infra.port_manager import PortManager

    pm = PortManager()
    allocation = pm.allocate_ports("container-1")
    print(f"Frontend: {allocation.frontend_port}, Backend: {allocation.backend_port}")
    
    # Nach Container-Ende
    pm.release_ports("container-1")
"""

import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Set
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class PortManagerError(Exception):
    """Basis-Exception für PortManager-Fehler."""
    pass


class NoAvailablePortError(PortManagerError):
    """Kein freier Port im definierten Range verfügbar."""
    pass


class PortAlreadyAllocatedError(PortManagerError):
    """Port ist bereits einem Container zugewiesen."""
    pass


class ContainerNotFoundError(PortManagerError):
    """Container-ID nicht in den Allokationen gefunden."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PortRange:
    """Definiert einen Port-Range für eine Service-Kategorie."""
    start: int
    end: int
    name: str = "default"
    
    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError(f"start ({self.start}) must be < end ({self.end})")
        if self.start < 1024:
            raise ValueError(f"start ({self.start}) should be >= 1024 (non-privileged)")
        if self.end > 65535:
            raise ValueError(f"end ({self.end}) must be <= 65535")
    
    @property
    def size(self) -> int:
        """Anzahl verfügbarer Ports im Range."""
        return self.end - self.start
    
    def __contains__(self, port: int) -> bool:
        """Prüft ob Port im Range liegt."""
        return self.start <= port < self.end


@dataclass
class PortAllocation:
    """Speichert eine Port-Zuweisung für einen Container."""
    container_id: str
    frontend_port: int
    backend_port: int
    allocated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "container_id": self.container_id,
            "frontend_port": self.frontend_port,
            "backend_port": self.backend_port,
            "allocated_at": self.allocated_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PortAllocation":
        """Erstellt PortAllocation aus Dictionary."""
        return cls(
            container_id=data["container_id"],
            frontend_port=data["frontend_port"],
            backend_port=data["backend_port"],
            allocated_at=datetime.fromisoformat(data["allocated_at"]),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Port Manager
# =============================================================================

class PortManager:
    """
    Thread-sicherer Manager für dynamische Port-Zuweisung.
    
    Features:
    - Automatische Erkennung freier Ports
    - Parallele Container-Unterstützung
    - Tracking aller aktiven Allokationen
    - Cleanup bei Container-Ende
    
    Default Port Ranges:
    - Frontend: 3100-3199 (100 Slots)
    - Backend: 8100-8199 (100 Slots)
    """
    
    # Default Port Ranges
    DEFAULT_FRONTEND_RANGE = PortRange(start=3100, end=3200, name="frontend")
    DEFAULT_BACKEND_RANGE = PortRange(start=8100, end=8200, name="backend")
    
    def __init__(
        self,
        frontend_range: Optional[PortRange] = None,
        backend_range: Optional[PortRange] = None,
    ):
        """
        Initialisiert den PortManager.
        
        Args:
            frontend_range: Custom Range für Frontend-Ports
            backend_range: Custom Range für Backend-Ports
        """
        self.frontend_range = frontend_range or self.DEFAULT_FRONTEND_RANGE
        self.backend_range = backend_range or self.DEFAULT_BACKEND_RANGE
        
        # Thread-sichere Datenstrukturen
        self._lock = threading.RLock()
        self._allocations: Dict[str, PortAllocation] = {}
        self._allocated_frontend_ports: Set[int] = set()
        self._allocated_backend_ports: Set[int] = set()
        
        self.logger = logger.bind(component="port_manager")
        self.logger.info(
            "port_manager_initialized",
            frontend_range=f"{self.frontend_range.start}-{self.frontend_range.end}",
            backend_range=f"{self.backend_range.start}-{self.backend_range.end}",
        )
    
    # =========================================================================
    # Core Port Detection
    # =========================================================================
    
    @staticmethod
    def is_port_in_use(port: int, host: str = "localhost") -> bool:
        """
        Prüft ob ein Port bereits belegt ist.
        
        Args:
            port: Port-Nummer zu prüfen
            host: Host-Adresse (default: localhost)
            
        Returns:
            True wenn Port belegt, False wenn frei
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            result = sock.connect_ex((host, port))
            return result == 0
    
    def _is_port_available(self, port: int, port_type: str = "frontend") -> bool:
        """
        Prüft ob Port verfügbar ist (nicht belegt + nicht allokiert).
        
        Args:
            port: Port-Nummer
            port_type: "frontend" oder "backend"
            
        Returns:
            True wenn verfügbar
        """
        # Prüfe ob bereits intern allokiert
        allocated_set = (
            self._allocated_frontend_ports 
            if port_type == "frontend" 
            else self._allocated_backend_ports
        )
        if port in allocated_set:
            return False
        
        # Prüfe ob Port auf System belegt
        return not self.is_port_in_use(port)
    
    def find_free_port(
        self,
        port_range: PortRange,
        port_type: str = "frontend",
    ) -> int:
        """
        Findet einen freien Port im angegebenen Range.
        
        Args:
            port_range: PortRange in dem gesucht werden soll
            port_type: "frontend" oder "backend" für Tracking
            
        Returns:
            Freier Port
            
        Raises:
            NoAvailablePortError: Wenn kein freier Port gefunden
        """
        for port in range(port_range.start, port_range.end):
            if self._is_port_available(port, port_type):
                return port
        
        raise NoAvailablePortError(
            f"Kein freier Port im Range {port_range.start}-{port_range.end} ({port_range.name})"
        )
    
    # =========================================================================
    # Allocation Management
    # =========================================================================
    
    def allocate_ports(
        self,
        container_id: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> PortAllocation:
        """
        Allokiert ein Port-Paar (Frontend + Backend) für einen Container.
        
        Thread-sicher - kann parallel von mehreren Threads aufgerufen werden.
        
        Args:
            container_id: Eindeutige ID des Containers
            metadata: Optionale Metadaten zur Allokation
            
        Returns:
            PortAllocation mit den zugewiesenen Ports
            
        Raises:
            PortAlreadyAllocatedError: Wenn container_id bereits Ports hat
            NoAvailablePortError: Wenn keine freien Ports verfügbar
        """
        with self._lock:
            # Prüfe ob Container bereits Ports hat
            if container_id in self._allocations:
                raise PortAlreadyAllocatedError(
                    f"Container {container_id} hat bereits Ports allokiert"
                )
            
            # Finde freie Ports
            frontend_port = self.find_free_port(self.frontend_range, "frontend")
            backend_port = self.find_free_port(self.backend_range, "backend")
            
            # Erstelle Allokation
            allocation = PortAllocation(
                container_id=container_id,
                frontend_port=frontend_port,
                backend_port=backend_port,
                metadata=metadata or {},
            )
            
            # Registriere Allokation
            self._allocations[container_id] = allocation
            self._allocated_frontend_ports.add(frontend_port)
            self._allocated_backend_ports.add(backend_port)
            
            self.logger.info(
                "ports_allocated",
                container_id=container_id,
                frontend_port=frontend_port,
                backend_port=backend_port,
            )
            
            return allocation
    
    def release_ports(self, container_id: str) -> bool:
        """
        Gibt die Ports eines Containers frei.
        
        Args:
            container_id: ID des Containers dessen Ports freigegeben werden
            
        Returns:
            True wenn erfolgreich, False wenn Container nicht gefunden
        """
        with self._lock:
            if container_id not in self._allocations:
                self.logger.warning("release_failed_not_found", container_id=container_id)
                return False
            
            allocation = self._allocations[container_id]
            
            # Entferne aus Tracking
            self._allocated_frontend_ports.discard(allocation.frontend_port)
            self._allocated_backend_ports.discard(allocation.backend_port)
            del self._allocations[container_id]
            
            self.logger.info(
                "ports_released",
                container_id=container_id,
                frontend_port=allocation.frontend_port,
                backend_port=allocation.backend_port,
            )
            
            return True
    
    def release_all(self) -> int:
        """
        Gibt alle allokierten Ports frei.
        
        Returns:
            Anzahl der freigegebenen Allokationen
        """
        with self._lock:
            count = len(self._allocations)
            self._allocations.clear()
            self._allocated_frontend_ports.clear()
            self._allocated_backend_ports.clear()
            
            self.logger.info("all_ports_released", count=count)
            return count
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_allocation(self, container_id: str) -> Optional[PortAllocation]:
        """
        Holt die Port-Allokation für einen Container.
        
        Args:
            container_id: ID des Containers
            
        Returns:
            PortAllocation oder None wenn nicht gefunden
        """
        with self._lock:
            return self._allocations.get(container_id)
    
    def list_allocations(self) -> List[PortAllocation]:
        """
        Listet alle aktiven Port-Allokationen.
        
        Returns:
            Liste aller PortAllocations
        """
        with self._lock:
            return list(self._allocations.values())
    
    def get_stats(self) -> dict:
        """
        Gibt Statistiken über die Port-Nutzung zurück.
        
        Returns:
            Dictionary mit Statistiken
        """
        with self._lock:
            return {
                "active_allocations": len(self._allocations),
                "frontend_ports_used": len(self._allocated_frontend_ports),
                "backend_ports_used": len(self._allocated_backend_ports),
                "frontend_ports_available": self.frontend_range.size - len(self._allocated_frontend_ports),
                "backend_ports_available": self.backend_range.size - len(self._allocated_backend_ports),
                "frontend_range": f"{self.frontend_range.start}-{self.frontend_range.end}",
                "backend_range": f"{self.backend_range.start}-{self.backend_range.end}",
            }
    
    def is_container_allocated(self, container_id: str) -> bool:
        """Prüft ob ein Container bereits Ports allokiert hat."""
        with self._lock:
            return container_id in self._allocations
    
    # =========================================================================
    # Context Manager Support
    # =========================================================================
    
    def __enter__(self):
        """Context Manager Entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Exit - gibt alle Ports frei."""
        self.release_all()
        return False


# =============================================================================
# Singleton Instance
# =============================================================================

# Global singleton für einfachen Zugriff
_global_port_manager: Optional[PortManager] = None
_global_lock = threading.Lock()


def get_port_manager() -> PortManager:
    """
    Gibt die globale PortManager-Instanz zurück (Singleton).
    
    Returns:
        Globale PortManager-Instanz
    """
    global _global_port_manager
    
    if _global_port_manager is None:
        with _global_lock:
            if _global_port_manager is None:
                _global_port_manager = PortManager()
    
    return _global_port_manager


def reset_global_port_manager() -> None:
    """Setzt den globalen PortManager zurück (für Tests)."""
    global _global_port_manager
    with _global_lock:
        if _global_port_manager:
            _global_port_manager.release_all()
        _global_port_manager = None
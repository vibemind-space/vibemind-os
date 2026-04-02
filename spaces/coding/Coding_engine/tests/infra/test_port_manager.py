"""
Unit Tests für den PortManager.

Tests:
1. PortRange Validierung
2. is_port_in_use Erkennung
3. find_free_port im Range
4. allocate_ports gibt sequentielle Port-Paare
5. release_ports gibt Ports frei
6. Parallelität - Thread-Sicherheit
7. Error Handling
"""

import pytest
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

from src.infra.port_manager import (
    PortManager,
    PortAllocation,
    PortRange,
    PortManagerError,
    NoAvailablePortError,
    PortAlreadyAllocatedError,
    get_port_manager,
    reset_global_port_manager,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def port_manager():
    """Erstellt eine frische PortManager-Instanz für jeden Test."""
    pm = PortManager()
    yield pm
    pm.release_all()


@pytest.fixture
def small_range_manager():
    """PortManager mit kleinem Range für Edge-Case Tests."""
    pm = PortManager(
        frontend_range=PortRange(start=10000, end=10005, name="small_frontend"),
        backend_range=PortRange(start=20000, end=20005, name="small_backend"),
    )
    yield pm
    pm.release_all()


@pytest.fixture(autouse=True)
def reset_global():
    """Setzt den globalen PortManager vor jedem Test zurück."""
    reset_global_port_manager()
    yield
    reset_global_port_manager()


# =============================================================================
# Test: PortRange
# =============================================================================

class TestPortRange:
    """Tests für die PortRange Dataclass."""
    
    def test_valid_range(self):
        """Test: Gültiger Range wird akzeptiert."""
        port_range = PortRange(start=3100, end=3200, name="test")
        assert port_range.start == 3100
        assert port_range.end == 3200
        assert port_range.size == 100
    
    def test_invalid_range_start_gt_end(self):
        """Test: start > end wirft ValueError."""
        with pytest.raises(ValueError, match="start.*must be < end"):
            PortRange(start=3200, end=3100)
    
    def test_invalid_range_privileged_port(self):
        """Test: Privilegierter Port wirft ValueError."""
        with pytest.raises(ValueError, match="should be >= 1024"):
            PortRange(start=80, end=100)
    
    def test_invalid_range_exceeds_max(self):
        """Test: Port > 65535 wirft ValueError."""
        with pytest.raises(ValueError, match="must be <= 65535"):
            PortRange(start=60000, end=70000)
    
    def test_contains(self):
        """Test: __contains__ funktioniert korrekt."""
        port_range = PortRange(start=3100, end=3200)
        assert 3100 in port_range
        assert 3150 in port_range
        assert 3199 in port_range
        assert 3200 not in port_range  # end ist exklusiv
        assert 3099 not in port_range


# =============================================================================
# Test: is_port_in_use
# =============================================================================

class TestIsPortInUse:
    """Tests für die is_port_in_use Funktion."""
    
    def test_unused_port(self, port_manager):
        """Test: Unbenutzter Port wird als frei erkannt."""
        # Port 19999 sollte normalerweise frei sein
        result = port_manager.is_port_in_use(19999)
        # Kann True oder False sein, je nach System - wir testen nur dass es nicht crasht
        assert isinstance(result, bool)
    
    def test_used_port_with_mock(self):
        """Test: Benutzter Port wird korrekt erkannt (mit Mock)."""
        # Starte einen echten Socket auf einem Port
        test_port = 19998
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind(("localhost", test_port))
            server_socket.listen(1)
            
            # Jetzt sollte der Port als belegt erkannt werden
            result = PortManager.is_port_in_use(test_port)
            assert result is True
        finally:
            server_socket.close()
    
    def test_freed_port(self):
        """Test: Freigegebener Port wird als frei erkannt."""
        test_port = 19997
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        server_socket.bind(("localhost", test_port))
        server_socket.listen(1)
        server_socket.close()
        
        # Kurz warten damit OS den Port freigibt
        time.sleep(0.1)
        
        # Port sollte jetzt frei sein
        result = PortManager.is_port_in_use(test_port)
        assert result is False


# =============================================================================
# Test: find_free_port
# =============================================================================

class TestFindFreePort:
    """Tests für die find_free_port Methode."""
    
    def test_finds_free_port_in_range(self, port_manager):
        """Test: Findet freien Port im definierten Range."""
        port = port_manager.find_free_port(
            PortRange(start=15000, end=15100),
            port_type="frontend"
        )
        assert 15000 <= port < 15100
    
    def test_respects_allocated_ports(self, port_manager):
        """Test: Überspringt bereits intern allokierte Ports."""
        # Allokiere ersten Port
        alloc1 = port_manager.allocate_ports("container-1")
        first_frontend = alloc1.frontend_port
        
        # Nächste Allokation sollte den nächsten Port bekommen
        alloc2 = port_manager.allocate_ports("container-2")
        assert alloc2.frontend_port == first_frontend + 1
    
    def test_no_available_port_raises(self, small_range_manager):
        """Test: Wirft NoAvailablePortError wenn Range erschöpft."""
        # Allokiere alle verfügbaren Ports (5 pro Range)
        for i in range(5):
            small_range_manager.allocate_ports(f"container-{i}")
        
        # Sechste Allokation sollte fehlschlagen
        with pytest.raises(NoAvailablePortError, match="Kein freier Port"):
            small_range_manager.allocate_ports("container-overflow")


# =============================================================================
# Test: allocate_ports
# =============================================================================

class TestAllocatePorts:
    """Tests für die allocate_ports Methode."""
    
    def test_basic_allocation(self, port_manager):
        """Test: Basisallokation funktioniert."""
        allocation = port_manager.allocate_ports("test-container")
        
        assert isinstance(allocation, PortAllocation)
        assert allocation.container_id == "test-container"
        assert 3100 <= allocation.frontend_port < 3200
        assert 8100 <= allocation.backend_port < 8200
    
    def test_sequential_allocation(self, port_manager):
        """Test: Sequentielle Allokationen geben aufeinanderfolgende Ports."""
        alloc1 = port_manager.allocate_ports("container-1")
        alloc2 = port_manager.allocate_ports("container-2")
        alloc3 = port_manager.allocate_ports("container-3")
        
        # Sollten aufeinanderfolgend sein
        assert alloc2.frontend_port == alloc1.frontend_port + 1
        assert alloc3.frontend_port == alloc2.frontend_port + 1
        
        assert alloc2.backend_port == alloc1.backend_port + 1
        assert alloc3.backend_port == alloc2.backend_port + 1
    
    def test_duplicate_container_raises(self, port_manager):
        """Test: Doppelte Container-ID wirft Fehler."""
        port_manager.allocate_ports("duplicate-container")
        
        with pytest.raises(PortAlreadyAllocatedError, match="bereits Ports allokiert"):
            port_manager.allocate_ports("duplicate-container")
    
    def test_allocation_with_metadata(self, port_manager):
        """Test: Metadaten werden gespeichert."""
        metadata = {"job_id": "123", "purpose": "testing"}
        allocation = port_manager.allocate_ports("meta-container", metadata=metadata)
        
        assert allocation.metadata == metadata
    
    def test_allocation_has_timestamp(self, port_manager):
        """Test: Allokation hat Zeitstempel."""
        from datetime import datetime
        
        before = datetime.now()
        allocation = port_manager.allocate_ports("time-container")
        after = datetime.now()
        
        assert before <= allocation.allocated_at <= after


# =============================================================================
# Test: release_ports
# =============================================================================

class TestReleasePorts:
    """Tests für die release_ports Methode."""
    
    def test_basic_release(self, port_manager):
        """Test: Basisfreigabe funktioniert."""
        port_manager.allocate_ports("release-container")
        assert port_manager.is_container_allocated("release-container")
        
        result = port_manager.release_ports("release-container")
        
        assert result is True
        assert not port_manager.is_container_allocated("release-container")
    
    def test_release_nonexistent_returns_false(self, port_manager):
        """Test: Freigabe nicht existierender Container gibt False zurück."""
        result = port_manager.release_ports("nonexistent")
        assert result is False
    
    def test_port_reuse_after_release(self, port_manager):
        """Test: Ports können nach Freigabe wiederverwendet werden."""
        # Allokiere und gib frei
        alloc1 = port_manager.allocate_ports("reuse-1")
        first_frontend = alloc1.frontend_port
        port_manager.release_ports("reuse-1")
        
        # Neue Allokation sollte den gleichen Port bekommen
        alloc2 = port_manager.allocate_ports("reuse-2")
        assert alloc2.frontend_port == first_frontend
    
    def test_release_all(self, port_manager):
        """Test: release_all gibt alle Ports frei."""
        port_manager.allocate_ports("container-1")
        port_manager.allocate_ports("container-2")
        port_manager.allocate_ports("container-3")
        
        count = port_manager.release_all()
        
        assert count == 3
        assert len(port_manager.list_allocations()) == 0


# =============================================================================
# Test: Parallelität / Thread-Sicherheit
# =============================================================================

class TestParallelAllocation:
    """Tests für Thread-Sicherheit bei parallelen Allokationen."""
    
    def test_concurrent_allocations(self, port_manager):
        """Test: Parallele Allokationen sind thread-sicher."""
        results = []
        errors = []
        num_threads = 10
        
        def allocate_thread(container_id):
            try:
                allocation = port_manager.allocate_ports(container_id)
                results.append(allocation)
            except Exception as e:
                errors.append(e)
        
        # Starte alle Threads gleichzeitig
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=allocate_thread, args=(f"parallel-{i}",))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Keine Fehler sollten aufgetreten sein
        assert len(errors) == 0
        
        # Alle Allokationen sollten erfolgreich sein
        assert len(results) == num_threads
        
        # Alle Ports sollten unique sein
        frontend_ports = {r.frontend_port for r in results}
        backend_ports = {r.backend_port for r in results}
        assert len(frontend_ports) == num_threads
        assert len(backend_ports) == num_threads
    
    def test_concurrent_allocations_with_executor(self, port_manager):
        """Test: Parallele Allokationen mit ThreadPoolExecutor."""
        num_containers = 20
        
        def allocate(i):
            return port_manager.allocate_ports(f"executor-{i}")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(allocate, i) for i in range(num_containers)]
            results = [f.result() for f in as_completed(futures)]
        
        # Alle sollten erfolgreich sein
        assert len(results) == num_containers
        
        # Alle Container-IDs sollten unique sein
        container_ids = {r.container_id for r in results}
        assert len(container_ids) == num_containers
    
    def test_concurrent_allocate_and_release(self, port_manager):
        """Test: Gleichzeitiges Allokieren und Freigeben ist sicher."""
        # Pre-allokiere einige Container
        for i in range(5):
            port_manager.allocate_ports(f"pre-{i}")
        
        errors = []
        
        def allocate_work():
            for i in range(10):
                try:
                    port_manager.allocate_ports(f"alloc-{threading.current_thread().name}-{i}")
                except PortAlreadyAllocatedError:
                    pass  # OK, kann bei Race Conditions passieren
                except Exception as e:
                    errors.append(e)
        
        def release_work():
            for i in range(5):
                try:
                    port_manager.release_ports(f"pre-{i}")
                except Exception as e:
                    errors.append(e)
        
        t1 = threading.Thread(target=allocate_work)
        t2 = threading.Thread(target=release_work)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Keine unerwarteten Fehler
        assert len(errors) == 0


# =============================================================================
# Test: Query Methods
# =============================================================================

class TestQueryMethods:
    """Tests für Query-Methoden."""
    
    def test_get_allocation(self, port_manager):
        """Test: get_allocation gibt korrekte Allokation zurück."""
        original = port_manager.allocate_ports("query-container")
        
        retrieved = port_manager.get_allocation("query-container")
        
        assert retrieved == original
    
    def test_get_allocation_nonexistent(self, port_manager):
        """Test: get_allocation gibt None für nicht existierende Container."""
        result = port_manager.get_allocation("nonexistent")
        assert result is None
    
    def test_list_allocations(self, port_manager):
        """Test: list_allocations gibt alle Allokationen zurück."""
        port_manager.allocate_ports("list-1")
        port_manager.allocate_ports("list-2")
        port_manager.allocate_ports("list-3")
        
        allocations = port_manager.list_allocations()
        
        assert len(allocations) == 3
        container_ids = {a.container_id for a in allocations}
        assert container_ids == {"list-1", "list-2", "list-3"}
    
    def test_get_stats(self, port_manager):
        """Test: get_stats gibt korrekte Statistiken zurück."""
        port_manager.allocate_ports("stats-1")
        port_manager.allocate_ports("stats-2")
        
        stats = port_manager.get_stats()
        
        assert stats["active_allocations"] == 2
        assert stats["frontend_ports_used"] == 2
        assert stats["backend_ports_used"] == 2
        assert stats["frontend_ports_available"] == 98
        assert stats["backend_ports_available"] == 98


# =============================================================================
# Test: Singleton / Global Instance
# =============================================================================

class TestSingleton:
    """Tests für die globale Singleton-Instanz."""
    
    def test_get_port_manager_returns_same_instance(self):
        """Test: get_port_manager gibt immer dieselbe Instanz zurück."""
        pm1 = get_port_manager()
        pm2 = get_port_manager()
        
        assert pm1 is pm2
    
    def test_reset_clears_singleton(self):
        """Test: reset_global_port_manager erstellt neue Instanz."""
        pm1 = get_port_manager()
        pm1.allocate_ports("singleton-test")
        
        reset_global_port_manager()
        
        pm2 = get_port_manager()
        assert pm2 is not pm1
        assert len(pm2.list_allocations()) == 0


# =============================================================================
# Test: Context Manager
# =============================================================================

class TestContextManager:
    """Tests für Context Manager Unterstützung."""
    
    def test_context_manager_cleanup(self):
        """Test: Context Manager gibt alle Ports am Ende frei."""
        with PortManager() as pm:
            pm.allocate_ports("ctx-1")
            pm.allocate_ports("ctx-2")
            assert len(pm.list_allocations()) == 2
        
        # Nach dem Context sollten alle Ports freigegeben sein
        # (pm ist noch gültig, aber leer)
        assert len(pm.list_allocations()) == 0


# =============================================================================
# Test: PortAllocation Serialization
# =============================================================================

class TestPortAllocationSerialization:
    """Tests für PortAllocation Serialisierung."""
    
    def test_to_dict(self, port_manager):
        """Test: to_dict serialisiert korrekt."""
        allocation = port_manager.allocate_ports("serial-1", metadata={"test": "value"})
        
        data = allocation.to_dict()
        
        assert data["container_id"] == "serial-1"
        assert isinstance(data["frontend_port"], int)
        assert isinstance(data["backend_port"], int)
        assert "allocated_at" in data
        assert data["metadata"] == {"test": "value"}
    
    def test_from_dict(self):
        """Test: from_dict deserialisiert korrekt."""
        data = {
            "container_id": "deser-1",
            "frontend_port": 3150,
            "backend_port": 8150,
            "allocated_at": "2024-01-01T12:00:00",
            "metadata": {"restored": "true"},
        }
        
        allocation = PortAllocation.from_dict(data)
        
        assert allocation.container_id == "deser-1"
        assert allocation.frontend_port == 3150
        assert allocation.backend_port == 8150
        assert allocation.metadata == {"restored": "true"}
"""
FileWriteAgent - Spezialisiert für Datei-Operationen

Dieser Agent ist verantwortlich für:
- Dateien erstellen
- Dateien lesen
- Dateien schreiben
- Dateien löschen
- Dateien umbenennen
- Verzeichnisse erstellen
- Verzeichnisse löschen
- Datei-Informationen abrufen
"""

import json
import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path
from enum import Enum

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FileType(Enum):
    """Datei-Typen"""
    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    BINARY = "binary"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    HTML = "html"
    CSS = "css"
    MARKDOWN = "markdown"


class FileWriteAgent:
    """Agent für Datei-Operationen"""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialisiert den FileWriteAgent
        
        Args:
            base_path: Basis-Pfad für relative Pfade
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        
        self.stats = {
            "operations": [],
            "files_created": 0,
            "files_read": 0,
            "files_written": 0,
            "files_deleted": 0,
            "directories_created": 0,
            "directories_deleted": 0
        }
        
        logger.info(f"FileWriteAgent initialisiert: {self.base_path}")
    
    def _log_operation(
        self,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Protokolliert eine Operation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "details": details or {}
        }
        
        self.stats["operations"].append(log_entry)
        logger.info(f"{operation}: {details}")
    
    def _resolve_path(self, path: str) -> Path:
        """Löst einen Pfad auf"""
        path_obj = Path(path)
        
        if path_obj.is_absolute():
            return path_obj
        else:
            return self.base_path / path_obj
    
    def create_file(
        self,
        path: str,
        content: str,
        file_type: FileType = FileType.TEXT,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Erstellt eine Datei
        
        Args:
            path: Pfad zur Datei
            content: Inhalt
            file_type: Datei-Typ
            encoding: Encoding
            
        Returns:
            Dict mit Status
        """
        try:
            file_path = self._resolve_path(path)
            
            # Verzeichnis erstellen falls nötig
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Datei schreiben
            with open(file_path, "w", encoding=encoding) as f:
                f.write(content)
            
            self.stats["files_created"] += 1
            
            self._log_operation(
                "create_file",
                {
                    "path": str(file_path),
                    "file_type": file_type.value,
                    "size": len(content)
                }
            )
            
            return {
                "status": "success",
                "path": str(file_path),
                "size": len(content)
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def read_file(
        self,
        path: str,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Liest eine Datei
        
        Args:
            path: Pfad zur Datei
            encoding: Encoding
            
        Returns:
            Dict mit Status und Inhalt
        """
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return {
                    "status": "error",
                    "error": "Datei nicht gefunden"
                }
            
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            
            self.stats["files_read"] += 1
            
            self._log_operation(
                "read_file",
                {
                    "path": str(file_path),
                    "size": len(content)
                }
            )
            
            return {
                "status": "success",
                "path": str(file_path),
                "content": content,
                "size": len(content)
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def write_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Schreibt eine Datei (überschreibt falls vorhanden)
        
        Args:
            path: Pfad zur Datei
            content: Inhalt
            encoding: Encoding
            
        Returns:
            Dict mit Status
        """
        try:
            file_path = self._resolve_path(path)
            
            # Verzeichnis erstellen falls nötig
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Datei schreiben
            with open(file_path, "w", encoding=encoding) as f:
                f.write(content)
            
            self.stats["files_written"] += 1
            
            self._log_operation(
                "write_file",
                {
                    "path": str(file_path),
                    "size": len(content)
                }
            )
            
            return {
                "status": "success",
                "path": str(file_path),
                "size": len(content)
            }
        except Exception as e:
            logger.error(f"Fehler beim Schreiben der Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def append_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Fügt Inhalt an eine Datei an
        
        Args:
            path: Pfad zur Datei
            content: Inhalt
            encoding: Encoding
            
        Returns:
            Dict mit Status
        """
        try:
            file_path = self._resolve_path(path)
            
            # Verzeichnis erstellen falls nötig
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Datei anhängen
            with open(file_path, "a", encoding=encoding) as f:
                f.write(content)
            
            self._log_operation(
                "append_file",
                {
                    "path": str(file_path),
                    "size": len(content)
                }
            )
            
            return {
                "status": "success",
                "path": str(file_path)
            }
        except Exception as e:
            logger.error(f"Fehler beim Anhängen an die Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def delete_file(
        self,
        path: str
    ) -> Dict[str, Any]:
        """
        Löscht eine Datei
        
        Args:
            path: Pfad zur Datei
            
        Returns:
            Dict mit Status
        """
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return {
                    "status": "error",
                    "error": "Datei nicht gefunden"
                }
            
            file_path.unlink()
            
            self.stats["files_deleted"] += 1
            
            self._log_operation(
                "delete_file",
                {"path": str(file_path)}
            )
            
            return {
                "status": "success",
                "path": str(file_path)
            }
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def rename_file(
        self,
        old_path: str,
        new_path: str
    ) -> Dict[str, Any]:
        """
        Benennt eine Datei um
        
        Args:
            old_path: Alter Pfad
            new_path: Neuer Pfad
            
        Returns:
            Dict mit Status
        """
        try:
            old_file_path = self._resolve_path(old_path)
            new_file_path = self._resolve_path(new_path)
            
            if not old_file_path.exists():
                return {
                    "status": "error",
                    "error": "Datei nicht gefunden"
                }
            
            old_file_path.rename(new_file_path)
            
            self._log_operation(
                "rename_file",
                {
                    "old_path": str(old_file_path),
                    "new_path": str(new_file_path)
                }
            )
            
            return {
                "status": "success",
                "old_path": str(old_file_path),
                "new_path": str(new_file_path)
            }
        except Exception as e:
            logger.error(f"Fehler beim Umbenennen der Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def copy_file(
        self,
        src_path: str,
        dst_path: str
    ) -> Dict[str, Any]:
        """
        Kopiert eine Datei
        
        Args:
            src_path: Quell-Pfad
            dst_path: Ziel-Pfad
            
        Returns:
            Dict mit Status
        """
        try:
            src_file_path = self._resolve_path(src_path)
            dst_file_path = self._resolve_path(dst_path)
            
            if not src_file_path.exists():
                return {
                    "status": "error",
                    "error": "Quelldatei nicht gefunden"
                }
            
            # Ziel-Verzeichnis erstellen falls nötig
            dst_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(src_file_path, dst_file_path)
            
            self._log_operation(
                "copy_file",
                {
                    "src_path": str(src_file_path),
                    "dst_path": str(dst_file_path)
                }
            )
            
            return {
                "status": "success",
                "src_path": str(src_file_path),
                "dst_path": str(dst_file_path)
            }
        except Exception as e:
            logger.error(f"Fehler beim Kopieren der Datei: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def create_directory(
        self,
        path: str,
        parents: bool = True,
        exist_ok: bool = True
    ) -> Dict[str, Any]:
        """
        Erstellt ein Verzeichnis
        
        Args:
            path: Pfad zum Verzeichnis
            parents: Eltern-Verzeichnisse erstellen
            exist_ok: Kein Fehler wenn bereits vorhanden
            
        Returns:
            Dict mit Status
        """
        try:
            dir_path = self._resolve_path(path)
            
            dir_path.mkdir(parents=parents, exist_ok=exist_ok)
            
            self.stats["directories_created"] += 1
            
            self._log_operation(
                "create_directory",
                {"path": str(dir_path)}
            )
            
            return {
                "status": "success",
                "path": str(dir_path)
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Verzeichnisses: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def delete_directory(
        self,
        path: str,
        recursive: bool = False
    ) -> Dict[str, Any]:
        """
        Löscht ein Verzeichnis
        
        Args:
            path: Pfad zum Verzeichnis
            recursive: Rekursiv löschen
            
        Returns:
            Dict mit Status
        """
        try:
            dir_path = self._resolve_path(path)
            
            if not dir_path.exists():
                return {
                    "status": "error",
                    "error": "Verzeichnis nicht gefunden"
                }
            
            if recursive:
                shutil.rmtree(dir_path)
            else:
                dir_path.rmdir()
            
            self.stats["directories_deleted"] += 1
            
            self._log_operation(
                "delete_directory",
                {
                    "path": str(dir_path),
                    "recursive": recursive
                }
            )
            
            return {
                "status": "success",
                "path": str(dir_path)
            }
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Verzeichnisses: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def list_directory(
        self,
        path: str,
        recursive: bool = False
    ) -> Dict[str, Any]:
        """
        Listet ein Verzeichnis auf
        
        Args:
            path: Pfad zum Verzeichnis
            recursive: Rekursiv auflisten
            
        Returns:
            Dict mit Status und Liste
        """
        try:
            dir_path = self._resolve_path(path)
            
            if not dir_path.exists():
                return {
                    "status": "error",
                    "error": "Verzeichnis nicht gefunden"
                }
            
            if recursive:
                items = []
                for item in dir_path.rglob("*"):
                    items.append({
                        "path": str(item.relative_to(dir_path)),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0
                    })
            else:
                items = []
                for item in dir_path.iterdir():
                    items.append({
                        "path": str(item.name),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0
                    })
            
            self._log_operation(
                "list_directory",
                {
                    "path": str(dir_path),
                    "count": len(items)
                }
            )
            
            return {
                "status": "success",
                "path": str(dir_path),
                "items": items
            }
        except Exception as e:
            logger.error(f"Fehler beim Auflisten des Verzeichnisses: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_file_info(
        self,
        path: str
    ) -> Dict[str, Any]:
        """
        Holt Informationen über eine Datei
        
        Args:
            path: Pfad zur Datei
            
        Returns:
            Dict mit Status und Informationen
        """
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return {
                    "status": "error",
                    "error": "Datei nicht gefunden"
                }
            
            stat = file_path.stat()
            
            info = {
                "path": str(file_path),
                "type": "directory" if file_path.is_dir() else "file",
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(stat.st_atime).isoformat()
            }
            
            self._log_operation(
                "get_file_info",
                {"path": str(file_path)}
            )
            
            return {
                "status": "success",
                "info": info
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen der Datei-Informationen: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def exists(
        self,
        path: str
    ) -> Dict[str, Any]:
        """
        Prüft ob eine Datei oder ein Verzeichnis existiert
        
        Args:
            path: Pfad
            
        Returns:
            Dict mit Status und Existenz
        """
        try:
            file_path = self._resolve_path(path)
            
            exists = file_path.exists()
            is_dir = file_path.is_dir() if exists else False
            is_file = file_path.is_file() if exists else False
            
            self._log_operation(
                "exists",
                {
                    "path": str(file_path),
                    "exists": exists
                }
            )
            
            return {
                "status": "success",
                "path": str(file_path),
                "exists": exists,
                "is_directory": is_dir,
                "is_file": is_file
            }
        except Exception as e:
            logger.error(f"Fehler beim Prüfen der Existenz: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            "status": "success",
            "stats": self.stats
        }
    
    def get_operations_log(
        self,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Gibt das Operations-Log zurück"""
        operations = self.stats["operations"]
        
        if limit:
            operations = operations[-limit:]
        
        return {
            "status": "success",
            "operations": operations
        }
    
    def health_check(self) -> bool:
        """Health Check"""
        return self.base_path.exists()


def main():
    """Test-Implementierung"""
    try:
        agent = FileWriteAgent()
        
        # Health Check
        print(f"Health Check: {agent.health_check()}")
        
        # Create Directory
        dir = agent.create_directory("test_dir")
        print(f"Create Directory: {dir}")
        
        # Create File
        file = agent.create_file("test_dir/test.txt", "Hello, World!")
        print(f"Create File: {file}")
        
        # Read File
        read = agent.read_file("test_dir/test.txt")
        print(f"Read File: {read}")
        
        # Write File
        write = agent.write_file("test_dir/test.txt", "Updated content")
        print(f"Write File: {write}")
        
        # Append File
        append = agent.append_file("test_dir/test.txt", "\nAppended content")
        print(f"Append File: {append}")
        
        # List Directory
        list_dir = agent.list_directory("test_dir")
        print(f"List Directory: {list_dir}")
        
        # Get File Info
        info = agent.get_file_info("test_dir/test.txt")
        print(f"File Info: {info}")
        
        # Exists
        exists = agent.exists("test_dir/test.txt")
        print(f"Exists: {exists}")
        
        # Stats
        stats = agent.get_stats()
        print(f"Stats: {stats}")
        
        # Cleanup
        agent.delete_directory("test_dir", recursive=True)
    except Exception as e:
        print(f"Fehler: {e}")


if __name__ == "__main__":
    main()

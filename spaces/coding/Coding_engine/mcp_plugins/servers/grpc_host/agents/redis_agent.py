"""
RedisAgent - Spezialisiert für Redis-Operationen

Dieser Agent ist verantwortlich für:
- Redis-Verbindung herstellen
- Keys lesen
- Keys schreiben
- Keys löschen
- Keys auflisten
- Redis-Status prüfen
- Redis-Flush
- Redis-Info abrufen
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RedisDataType(Enum):
    """Redis-Datentypen"""
    STRING = "string"
    HASH = "hash"
    LIST = "list"
    SET = "set"
    ZSET = "zset"


class RedisAgent:
    """Agent für Redis-Operationen"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None
    ):
        """
        Initialisiert den RedisAgent
        
        Args:
            host: Redis Host
            port: Redis Port
            db: Redis Datenbank
            password: Redis Passwort
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis-Paket ist nicht installiert. "
                "Installiere es mit: pip install redis"
            )
        
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        
        self.client = None
        self.connected = False
        
        self.stats = {
            "operations": [],
            "keys_read": 0,
            "keys_written": 0,
            "keys_deleted": 0,
            "connections": 0
        }
        
        logger.info(f"RedisAgent initialisiert: {host}:{port}/{db}")
    
    def connect(self) -> Dict[str, Any]:
        """
        Verbindet sich mit Redis
        
        Returns:
            Dict mit Status
        """
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            
            # Verbindung testen
            self.client.ping()
            
            self.connected = True
            self.stats["connections"] += 1
            
            self._log_operation(
                "connect",
                {
                    "host": self.host,
                    "port": self.port,
                    "db": self.db
                }
            )
            
            return {
                "status": "success",
                "message": "Verbunden mit Redis"
            }
        except Exception as e:
            logger.error(f"Fehler beim Verbinden mit Redis: {e}")
            self.connected = False
            return {
                "status": "error",
                "error": str(e)
            }
    
    def disconnect(self) -> Dict[str, Any]:
        """
        Trennt die Verbindung zu Redis
        
        Returns:
            Dict mit Status
        """
        try:
            if self.client:
                self.client.close()
                self.connected = False
                
                self._log_operation(
                    "disconnect",
                    {}
                )
            
            return {
                "status": "success",
                "message": "Verbindung getrennt"
            }
        except Exception as e:
            logger.error(f"Fehler beim Trennen der Verbindung: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _ensure_connected(self) -> bool:
        """Stellt sicher, dass eine Verbindung besteht"""
        if not self.connected:
            result = self.connect()
            return result["status"] == "success"
        return True
    
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
    
    def get(
        self,
        key: str
    ) -> Dict[str, Any]:
        """
        Liest einen Key
        
        Args:
            key: Key Name
            
        Returns:
            Dict mit Status und Wert
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            value = self.client.get(key)
            
            self.stats["keys_read"] += 1
            
            self._log_operation(
                "get",
                {"key": key}
            )
            
            return {
                "status": "success",
                "key": key,
                "value": value
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen des Keys: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Schreibt einen Key
        
        Args:
            key: Key Name
            value: Wert
            ttl: TTL in Sekunden
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            if ttl:
                self.client.setex(key, ttl, value)
            else:
                self.client.set(key, value)
            
            self.stats["keys_written"] += 1
            
            self._log_operation(
                "set",
                {
                    "key": key,
                    "ttl": ttl
                }
            )
            
            return {
                "status": "success",
                "key": key,
                "message": "Key gesetzt"
            }
        except Exception as e:
            logger.error(f"Fehler beim Setzen des Keys: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def delete(
        self,
        key: str
    ) -> Dict[str, Any]:
        """
        Löscht einen Key
        
        Args:
            key: Key Name
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            deleted = self.client.delete(key)
            
            if deleted:
                self.stats["keys_deleted"] += 1
                
                self._log_operation(
                    "delete",
                    {"key": key}
                )
            
            return {
                "status": "success",
                "key": key,
                "deleted": deleted > 0
            }
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Keys: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def exists(
        self,
        key: str
    ) -> Dict[str, Any]:
        """
        Prüft, ob ein Key existiert
        
        Args:
            key: Key Name
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            exists = self.client.exists(key)
            
            self._log_operation(
                "exists",
                {"key": key}
            )
            
            return {
                "status": "success",
                "key": key,
                "exists": exists > 0
            }
        except Exception as e:
            logger.error(f"Fehler beim Prüfen des Keys: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def keys(
        self,
        pattern: str = "*"
    ) -> Dict[str, Any]:
        """
        Listet alle Keys auf
        
        Args:
            pattern: Key Pattern
            
        Returns:
            Dict mit Status und Key-Liste
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            keys = self.client.keys(pattern)
            
            self._log_operation(
                "keys",
                {
                    "pattern": pattern,
                    "count": len(keys)
                }
            )
            
            return {
                "status": "success",
                "keys": keys,
                "count": len(keys)
            }
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Keys: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_type(
        self,
        key: str
    ) -> Dict[str, Any]:
        """
        Holt den Typ eines Keys
        
        Args:
            key: Key Name
            
        Returns:
            Dict mit Status und Typ
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            key_type = self.client.type(key)
            
            self._log_operation(
                "get_type",
                {"key": key}
            )
            
            return {
                "status": "success",
                "key": key,
                "type": key_type
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen des Key-Typs: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def hget(
        self,
        key: str,
        field: str
    ) -> Dict[str, Any]:
        """
        Liest ein Hash-Feld
        
        Args:
            key: Key Name
            field: Feld Name
            
        Returns:
            Dict mit Status und Wert
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            value = self.client.hget(key, field)
            
            self.stats["keys_read"] += 1
            
            self._log_operation(
                "hget",
                {"key": key, "field": field}
            )
            
            return {
                "status": "success",
                "key": key,
                "field": field,
                "value": value
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen des Hash-Felds: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def hset(
        self,
        key: str,
        field: str,
        value: str
    ) -> Dict[str, Any]:
        """
        Schreibt ein Hash-Feld
        
        Args:
            key: Key Name
            field: Feld Name
            value: Wert
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            self.client.hset(key, field, value)
            
            self.stats["keys_written"] += 1
            
            self._log_operation(
                "hset",
                {"key": key, "field": field}
            )
            
            return {
                "status": "success",
                "key": key,
                "field": field,
                "message": "Hash-Feld gesetzt"
            }
        except Exception as e:
            logger.error(f"Fehler beim Setzen des Hash-Felds: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def hgetall(
        self,
        key: str
    ) -> Dict[str, Any]:
        """
        Liest alle Hash-Felder
        
        Args:
            key: Key Name
            
        Returns:
            Dict mit Status und Hash
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            hash_data = self.client.hgetall(key)
            
            self._log_operation(
                "hgetall",
                {"key": key}
            )
            
            return {
                "status": "success",
                "key": key,
                "hash": hash_data
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen des Hash: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def hdel(
        self,
        key: str,
        field: str
    ) -> Dict[str, Any]:
        """
        Löscht ein Hash-Feld
        
        Args:
            key: Key Name
            field: Feld Name
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            deleted = self.client.hdel(key, field)
            
            if deleted:
                self.stats["keys_deleted"] += 1
                
                self._log_operation(
                    "hdel",
                    {"key": key, "field": field}
                )
            
            return {
                "status": "success",
                "key": key,
                "field": field,
                "deleted": deleted > 0
            }
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Hash-Felds: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def lrange(
        self,
        key: str,
        start: int = 0,
        end: int = -1
    ) -> Dict[str, Any]:
        """
        Liest eine Liste
        
        Args:
            key: Key Name
            start: Start Index
            end: End Index
            
        Returns:
            Dict mit Status und Liste
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            values = self.client.lrange(key, start, end)
            
            self._log_operation(
                "lrange",
                {"key": key, "start": start, "end": end}
            )
            
            return {
                "status": "success",
                "key": key,
                "values": values
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Liste: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def lpush(
        self,
        key: str,
        *values: str
    ) -> Dict[str, Any]:
        """
        Fügt Werte am Anfang einer Liste hinzu
        
        Args:
            key: Key Name
            values: Werte
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            length = self.client.lpush(key, *values)
            
            self.stats["keys_written"] += 1
            
            self._log_operation(
                "lpush",
                {"key": key, "count": len(values)}
            )
            
            return {
                "status": "success",
                "key": key,
                "length": length
            }
        except Exception as e:
            logger.error(f"Fehler beim Hinzufügen zur Liste: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def flushdb(self) -> Dict[str, Any]:
        """
        Löscht alle Keys in der aktuellen Datenbank
        
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            self.client.flushdb()
            
            self._log_operation(
                "flushdb",
                {}
            )
            
            return {
                "status": "success",
                "message": "Datenbank geleert"
            }
        except Exception as e:
            logger.error(f"Fehler beim Leeren der Datenbank: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def flushall(self) -> Dict[str, Any]:
        """
        Löscht alle Keys in allen Datenbanken
        
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            self.client.flushall()
            
            self._log_operation(
                "flushall",
                {}
            )
            
            return {
                "status": "success",
                "message": "Alle Datenbanken geleert"
            }
        except Exception as e:
            logger.error(f"Fehler beim Leeren aller Datenbanken: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def info(self) -> Dict[str, Any]:
        """
        Holt Redis-Info
        
        Returns:
            Dict mit Status und Info
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            info = self.client.info()
            
            self._log_operation(
                "info",
                {}
            )
            
            return {
                "status": "success",
                "info": info
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen der Redis-Info: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def ping(self) -> Dict[str, Any]:
        """
        Ping Redis
        
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_connected():
                return {
                    "status": "error",
                    "error": "Nicht mit Redis verbunden"
                }
            
            pong = self.client.ping()
            
            self._log_operation(
                "ping",
                {}
            )
            
            return {
                "status": "success",
                "pong": pong
            }
        except Exception as e:
            logger.error(f"Fehler beim Pingen von Redis: {e}")
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
        try:
            result = self.ping()
            return result["status"] == "success"
        except Exception:
            return False


def main():
    """Test-Implementierung"""
    try:
        agent = RedisAgent()
        
        # Connect
        print(f"Connect: {agent.connect()}")
        
        # Ping
        print(f"Ping: {agent.ping()}")
        
        # Set
        print(f"Set: {agent.set('test_key', 'test_value')}")
        
        # Get
        print(f"Get: {agent.get('test_key')}")
        
        # Keys
        print(f"Keys: {agent.keys('test_*')}")
        
        # Info
        print(f"Info: {agent.info()}")
        
        # Stats
        stats = agent.get_stats()
        print(f"Stats: {stats}")
        
        # Disconnect
        print(f"Disconnect: {agent.disconnect()}")
    except Exception as e:
        print(f"Fehler: {e}")


if __name__ == "__main__":
    main()

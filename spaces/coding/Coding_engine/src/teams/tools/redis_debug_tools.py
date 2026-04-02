"""
RedisDebugTools - Redis-Tools für Debugging.

Verantwortlichkeiten:
- Keys nach Pattern suchen
- Key-Informationen abrufen
- Cache-Hit-Rate analysieren
- Redis-Logs abrufen
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class RedisDebugTools:
    """
    Redis Debug Tools - Bietet Funktionen für Redis-Debugging.
    
    Verwendet Redis CLI für Cache-Analyse.
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.logger = logger.bind(
            component="redis_debug_tools",
            host=redis_host,
            port=redis_port,
        )
    
    async def get_keys_pattern(
        self,
        pattern: str = "*",
        count: int = 100,
    ) -> Dict[str, Any]:
        """
        Holt Keys nach einem Pattern.
        
        Args:
            pattern: Key-Pattern (z.B. "user:*", "session:*")
            count: Maximale Anzahl von Keys
            
        Returns:
            Dict mit success, keys, metadata
        """
        self.logger.info(
            "getting_keys_pattern",
            pattern=pattern,
            count=count,
        )
        
        try:
            # Redis KEYS command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "KEYS", pattern]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                keys_text = stdout.decode('utf-8', errors='replace').strip()
                keys = [key.strip() for key in keys_text.split('\n') if key.strip()]
                
                # Limit auf count
                keys = keys[:count]
                
                return {
                    "success": True,
                    "keys": keys,
                    "count": len(keys),
                    "pattern": pattern,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "pattern": pattern,
                }
                
        except Exception as e:
            self.logger.error(
                "get_keys_pattern_failed",
                pattern=pattern,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "pattern": pattern,
            }
    
    async def get_key_info(
        self,
        key: str,
    ) -> Dict[str, Any]:
        """
        Holt Informationen über einen Key.
        
        Args:
            key: Der Key
            
        Returns:
            Dict mit success, key_info, metadata
        """
        self.logger.info(
            "getting_key_info",
            key=key,
        )
        
        try:
            # Redis INFO command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "INFO", key]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                info_text = stdout.decode('utf-8', errors='replace')
                
                # INFO-Output parsen
                key_info = self._parse_redis_info(info_text)
                
                return {
                    "success": True,
                    "key": key,
                    "key_info": key_info,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "key": key,
                }
                
        except Exception as e:
            self.logger.error(
                "get_key_info_failed",
                key=key,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "key": key,
            }
    
    def _parse_redis_info(self, info_text: str) -> Dict[str, Any]:
        """
        Parst Redis INFO-Output.
        
        Args:
            info_text: INFO-Output als String
            
        Returns:
            Geparste Key-Informationen
        """
        info = {}
        
        for line in info_text.split('\n'):
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()
        
        return info
    
    async def get_key_value(
        self,
        key: str,
    ) -> Dict[str, Any]:
        """
        Holt den Wert eines Keys.
        
        Args:
            key: Der Key
            
        Returns:
            Dict mit success, value, metadata
        """
        self.logger.info(
            "getting_key_value",
            key=key,
        )
        
        try:
            # Redis GET command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "GET", key]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                value = stdout.decode('utf-8', errors='replace').strip()
                
                return {
                    "success": True,
                    "key": key,
                    "value": value,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "key": key,
                }
                
        except Exception as e:
            self.logger.error(
                "get_key_value_failed",
                key=key,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "key": key,
            }
    
    async def analyze_cache_hit_rate(
        self,
        time_range: str = "1h",
    ) -> Dict[str, Any]:
        """
        Analysiert die Cache-Hit-Rate.
        
        Args:
            time_range: Zeitbereich für Analyse (z.B. "1h", "24h")
            
        Returns:
            Dict mit success, cache_info, metadata
        """
        self.logger.info(
            "analyzing_cache_hit_rate",
            time_range=time_range,
        )
        
        try:
            # Redis INFO command für Stats
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "INFO", "stats"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                info_text = stdout.decode('utf-8', errors='replace')
                stats = self._parse_redis_info(info_text)
                
                # Cache-Hit-Rate berechnen
                keyspace_hits = int(stats.get("keyspace_hits", 0))
                keyspace_misses = int(stats.get("keyspace_misses", 0))
                
                total_requests = keyspace_hits + keyspace_misses
                hit_rate = (keyspace_hits / total_requests * 100) if total_requests > 0 else 0
                
                return {
                    "success": True,
                    "cache_info": {
                        "hit_rate": round(hit_rate, 2),
                        "hits": keyspace_hits,
                        "misses": keyspace_misses,
                        "total_requests": total_requests,
                        "time_range": time_range,
                    },
                    "stats": stats,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "time_range": time_range,
                }
                
        except Exception as e:
            self.logger.error(
                "analyze_cache_hit_rate_failed",
                time_range=time_range,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "time_range": time_range,
            }
    
    async def get_memory_usage(
        self,
    ) -> Dict[str, Any]:
        """
        Holt die Speichernutzung von Redis.
        
        Returns:
            Dict mit success, memory_info, metadata
        """
        self.logger.info("getting_memory_usage")
        
        try:
            # Redis INFO command für Memory
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "INFO", "memory"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                info_text = stdout.decode('utf-8', errors='replace')
                memory_info = self._parse_redis_info(info_text)
                
                # Speicher in MB umrechnen
                used_memory = int(memory_info.get("used_memory", 0)) / (1024 * 1024)
                peak_memory = int(memory_info.get("used_memory_peak", 0)) / (1024 * 1024)
                max_memory = int(memory_info.get("maxmemory", 0)) / (1024 * 1024)
                
                return {
                    "success": True,
                    "memory_info": {
                        "used_memory_mb": round(used_memory, 2),
                        "peak_memory_mb": round(peak_memory, 2),
                        "max_memory_mb": round(max_memory, 2),
                        "usage_percent": round((used_memory / max_memory * 100) if max_memory > 0 else 0, 2),
                    },
                    "raw_info": memory_info,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                }
                
        except Exception as e:
            self.logger.error(
                "get_memory_usage_failed",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_recent_logs(
        self,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Holt die letzten Redis-Logs.
        
        Args:
            limit: Anzahl der letzten Log-Einträge
            
        Returns:
            Dict mit success, logs, metadata
        """
        self.logger.info(
            "getting_recent_logs",
            limit=limit,
        )
        
        try:
            # Redis SLOWLOG command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "SLOWLOG", "GET", str(limit)]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logs_text = stdout.decode('utf-8', errors='replace')
                
                # Logs parsen
                logs = []
                for line in logs_text.split('\n'):
                    line = line.strip()
                    if line:
                        logs.append(line)
                
                return {
                    "success": True,
                    "logs": logs,
                    "count": len(logs),
                    "limit": limit,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "limit": limit,
                }
                
        except Exception as e:
            self.logger.error(
                "get_recent_logs_failed",
                limit=limit,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "limit": limit,
            }
    
    async def get_slow_queries(
        self,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Holt die langsamsten Redis-Queries.
        
        Args:
            limit: Maximale Anzahl von Queries
            
        Returns:
            Dict mit success, queries, metadata
        """
        self.logger.info(
            "getting_slow_queries",
            limit=limit,
        )
        
        try:
            # Redis SLOWLOG command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "SLOWLOG", "LEN"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                count = int(stdout.decode('utf-8', errors='replace').strip())
                
                # Queries holen
                if count > 0:
                    cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "SLOWLOG", "GET", str(min(count, limit))]
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0:
                        queries_text = stdout.decode('utf-8', errors='replace')
                        
                        # Queries parsen
                        queries = []
                        for line in queries_text.split('\n'):
                            line = line.strip()
                            if line:
                                queries.append(line)
                        
                        return {
                            "success": True,
                            "queries": queries,
                            "count": len(queries),
                            "limit": limit,
                        }
                    else:
                        error = stderr.decode('utf-8', errors='replace')
                        return {
                            "success": False,
                            "error": error,
                            "limit": limit,
                        }
                else:
                    return {
                        "success": True,
                        "queries": [],
                        "count": 0,
                        "limit": limit,
                    }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "limit": limit,
                }
                
        except Exception as e:
            self.logger.error(
                "get_slow_queries_failed",
                limit=limit,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "limit": limit,
            }
    
    async def delete_key(
        self,
        key: str,
    ) -> Dict[str, Any]:
        """
        Löscht einen Key.
        
        Args:
            key: Der zu löschende Key
            
        Returns:
            Dict mit success, metadata
        """
        self.logger.info(
            "deleting_key",
            key=key,
        )
        
        try:
            # Redis DEL command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "DEL", key]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                result = stdout.decode('utf-8', errors='replace').strip()
                
                return {
                    "success": True,
                    "key": key,
                    "result": result,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "key": key,
                }
                
        except Exception as e:
            self.logger.error(
                "delete_key_failed",
                key=key,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "key": key,
            }
    
    async def flush_cache(
        self,
        database: int = 0,
    ) -> Dict[str, Any]:
        """
        Leert den Cache (löscht alle Keys).
        
        Args:
            database: Datenbank-Nummer (default: 0)
            
        Returns:
            Dict mit success, metadata
        """
        self.logger.info(
            "flushing_cache",
            database=database,
        )
        
        try:
            # Redis FLUSHDB command
            cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "FLUSHDB"]
            
            if database > 0:
                cmd = ["redis-cli", "-h", self.redis_host, "-p", str(self.redis_port), "-n", str(database), "FLUSHDB"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                result = stdout.decode('utf-8', errors='replace').strip()
                
                return {
                    "success": True,
                    "result": result,
                    "database": database,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "database": database,
                }
                
        except Exception as e:
            self.logger.error(
                "flush_cache_failed",
                database=database,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "database": database,
            }

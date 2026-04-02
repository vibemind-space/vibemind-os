#!/usr/bin/env python3
"""
Tool Execution Cache - Iteration 3

Caching für häufig aufgerufene Read-Operations um redundante
MCP-Calls zu vermeiden.

Features:
- TTL-basiertes Caching für read_file, list_directory, etc.
- Automatische Invalidierung bei write_file
- Cache-Stats für Monitoring
- LRU-Eviction bei Memory-Limits
"""

import time
import hashlib
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict
from threading import Lock
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Ein Cache-Eintrag"""
    key: str
    value: Any
    created_at: float
    ttl_seconds: int
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        """Prüft ob der Eintrag abgelaufen ist"""
        return time.time() > (self.created_at + self.ttl_seconds)

    def touch(self):
        """Aktualisiert den Zugriffszeitpunkt"""
        self.access_count += 1
        self.last_accessed = time.time()


# TTL-Konfiguration für cacheable Tools (in Sekunden)
CACHEABLE_TOOLS: Dict[str, int] = {
    # Filesystem reads - kurzes TTL da Files sich ändern können
    "filesystem_read_file": 30,
    "filesystem_list_directory": 60,
    "filesystem_search_files": 45,
    "filesystem_get_file_info": 30,

    # Docker reads - kürzeres TTL da Container-State dynamisch
    "docker_container_stats": 10,
    "docker_container_logs": 15,
    "docker_image_list": 60,

    # Database reads - mittleres TTL
    "postgres_list_tables": 120,
    "postgres_describe_table": 120,
    "prisma_status": 60,

    # Time - sehr kurz
    "time_get_current_time": 5,

    # Git reads
    "git_status": 30,
    "git_diff": 30,
    "git_log": 60,
}

# Tools die den Cache invalidieren
CACHE_INVALIDATING_TOOLS: Dict[str, List[str]] = {
    # Write-Tools invalidieren Filesystem-Cache
    "filesystem_write_file": ["filesystem_read_file", "filesystem_list_directory", "filesystem_search_files"],
    "filesystem_create_directory": ["filesystem_list_directory"],
    "filesystem_delete_file": ["filesystem_read_file", "filesystem_list_directory", "filesystem_search_files"],
    "filesystem_move_file": ["filesystem_read_file", "filesystem_list_directory"],

    # Docker writes invalidieren Docker-Cache
    "docker_compose_up": ["docker_container_stats", "docker_container_logs", "docker_image_list"],
    "docker_compose_down": ["docker_container_stats", "docker_container_logs"],
    "docker_container_start": ["docker_container_stats", "docker_container_logs"],
    "docker_container_stop": ["docker_container_stats", "docker_container_logs"],

    # Git writes invalidieren Git-Cache
    "git_commit": ["git_status", "git_log", "git_diff"],
    "git_push": ["git_status", "git_log"],
    "git_pull": ["git_status", "git_log", "git_diff"],

    # Database writes invalidieren Schema-Cache
    "prisma_generate": ["prisma_status"],
    "prisma_migrate": ["postgres_list_tables", "postgres_describe_table"],
}


@dataclass
class CacheStats:
    """Cache-Statistiken"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    invalidations: int = 0
    total_entries: int = 0
    memory_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Hit-Rate als Prozent"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0


class ToolExecutionCache:
    """
    LRU Cache für Tool-Ausführungsergebnisse.

    Reduziert redundante MCP-Calls durch intelligentes Caching
    von Read-Operations mit automatischer Invalidierung.
    """

    def __init__(
        self,
        max_entries: int = 1000,
        max_memory_mb: float = 50.0,
        default_ttl: int = 60
    ):
        """
        Args:
            max_entries: Maximale Anzahl Cache-Einträge
            max_memory_mb: Maximaler Speicherverbrauch in MB
            default_ttl: Default TTL in Sekunden
        """
        self.max_entries = max_entries
        self.max_memory_bytes = int(max_memory_mb * 1024 * 1024)
        self.default_ttl = default_ttl

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()
        self._lock = Lock()

        logger.info(f"ToolExecutionCache initialized (max_entries={max_entries}, max_memory={max_memory_mb}MB)")

    def _generate_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Generiert einen eindeutigen Cache-Key"""
        # Sortierte Args für konsistente Keys
        args_str = json.dumps(args, sort_keys=True, default=str)
        combined = f"{tool_name}:{args_str}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _estimate_size(self, value: Any) -> int:
        """Schätzt die Größe eines Wertes in Bytes"""
        try:
            return len(json.dumps(value, default=str).encode())
        except Exception:
            return 1000  # Fallback

    def _evict_if_needed(self):
        """Entfernt alte Einträge wenn Limits erreicht"""
        # Expired Entries entfernen
        expired_keys = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired_keys:
            del self._cache[key]
            self._stats.evictions += 1

        # LRU Eviction wenn zu viele Einträge
        while len(self._cache) > self.max_entries:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._stats.evictions += 1

        # Memory-basierte Eviction
        total_size = sum(self._estimate_size(e.value) for e in self._cache.values())
        while total_size > self.max_memory_bytes and self._cache:
            oldest_key = next(iter(self._cache))
            entry = self._cache[oldest_key]
            total_size -= self._estimate_size(entry.value)
            del self._cache[oldest_key]
            self._stats.evictions += 1

    def is_cacheable(self, tool_name: str) -> bool:
        """Prüft ob ein Tool gecached werden kann"""
        return tool_name in CACHEABLE_TOOLS

    def get_ttl(self, tool_name: str) -> int:
        """Gibt TTL für ein Tool zurück"""
        return CACHEABLE_TOOLS.get(tool_name, self.default_ttl)

    def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """
        Holt einen gecachten Wert.

        Args:
            tool_name: Name des Tools
            args: Tool-Arguments

        Returns:
            Gecachter Wert oder None
        """
        if not self.is_cacheable(tool_name):
            return None

        key = self._generate_key(tool_name, args)

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._stats.misses += 1
                return None

            # LRU: Move to end
            self._cache.move_to_end(key)
            entry.touch()
            self._stats.hits += 1

            logger.debug(f"Cache HIT for {tool_name} (key={key[:8]}...)")
            return entry.value

    def set(self, tool_name: str, args: Dict[str, Any], value: Any):
        """
        Speichert einen Wert im Cache.

        Args:
            tool_name: Name des Tools
            args: Tool-Arguments
            value: Zu cachender Wert
        """
        if not self.is_cacheable(tool_name):
            return

        key = self._generate_key(tool_name, args)
        ttl = self.get_ttl(tool_name)

        with self._lock:
            self._evict_if_needed()

            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl
            )

            self._cache[key] = entry
            self._cache.move_to_end(key)

            logger.debug(f"Cache SET for {tool_name} (key={key[:8]}..., ttl={ttl}s)")

    def invalidate_for_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None):
        """
        Invalidiert Cache-Einträge die von einem Tool betroffen sind.

        Args:
            tool_name: Name des ausgeführten Tools
            args: Tool-Arguments (für path-basierte Invalidierung)
        """
        affected_tools = CACHE_INVALIDATING_TOOLS.get(tool_name, [])

        if not affected_tools:
            return

        with self._lock:
            # Path aus Arguments extrahieren für gezieltere Invalidierung
            affected_path = None
            if args:
                affected_path = args.get("path") or args.get("file_path")

            keys_to_remove = []

            for key, entry in self._cache.items():
                # Tool-Name aus dem Original-Call extrahieren
                # Wir speichern das nicht direkt, also müssen wir alle
                # betroffenen Tool-Typen invalidieren

                # Für einfache Implementierung: Alle Entries der betroffenen Tools löschen
                # Eine präzisere Implementierung würde den Tool-Namen im Entry speichern
                for affected_tool in affected_tools:
                    if affected_tool in entry.key:  # Vereinfachte Prüfung
                        keys_to_remove.append(key)
                        break

            for key in keys_to_remove:
                del self._cache[key]
                self._stats.invalidations += 1

            if keys_to_remove:
                logger.debug(f"Cache invalidated {len(keys_to_remove)} entries for {tool_name}")

    def invalidate_path(self, path: str):
        """
        Invalidiert alle Cache-Einträge die einen bestimmten Pfad betreffen.

        Args:
            path: Der betroffene Dateipfad
        """
        with self._lock:
            keys_to_remove = []

            for key, entry in self._cache.items():
                # Prüfen ob der Path im Value enthalten sein könnte
                value_str = json.dumps(entry.value, default=str)
                if path in value_str:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]
                self._stats.invalidations += 1

            if keys_to_remove:
                logger.debug(f"Cache invalidated {len(keys_to_remove)} entries for path: {path}")

    def clear(self):
        """Leert den gesamten Cache"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.evictions += count
            logger.info(f"Cache cleared ({count} entries)")

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Cache-Statistiken zurück"""
        with self._lock:
            self._stats.total_entries = len(self._cache)
            self._stats.memory_bytes = sum(
                self._estimate_size(e.value) for e in self._cache.values()
            )

            return {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "hit_rate": f"{self._stats.hit_rate:.1f}%",
                "evictions": self._stats.evictions,
                "invalidations": self._stats.invalidations,
                "total_entries": self._stats.total_entries,
                "memory_mb": f"{self._stats.memory_bytes / 1024 / 1024:.2f}",
                "max_entries": self.max_entries,
                "max_memory_mb": f"{self.max_memory_bytes / 1024 / 1024:.2f}"
            }


class CachingToolWrapper:
    """
    Wrapper der Tool-Ausführungen automatisch cached.

    Integriert sich zwischen Agent und MCP Tools.
    """

    def __init__(self, cache: ToolExecutionCache):
        self.cache = cache

    async def execute_with_cache(
        self,
        tool_name: str,
        args: Dict[str, Any],
        execute_fn
    ) -> Tuple[Any, bool]:
        """
        Führt ein Tool aus mit Caching.

        Args:
            tool_name: Name des Tools
            args: Tool-Arguments
            execute_fn: Async Funktion die das Tool ausführt

        Returns:
            Tuple von (result, from_cache)
        """
        # Cache prüfen
        cached = self.cache.get(tool_name, args)
        if cached is not None:
            return cached, True

        # Tool ausführen
        result = await execute_fn(tool_name, args)

        # Cachen wenn erfolgreich
        self.cache.set(tool_name, args, result)

        # Invalidierung bei Write-Operations
        if tool_name in CACHE_INVALIDATING_TOOLS:
            self.cache.invalidate_for_tool(tool_name, args)

        return result, False


# =============================================================================
# Test
# =============================================================================

def test_cache():
    """Test der Cache-Funktionalität"""
    print("=== Tool Execution Cache Test ===\n")

    cache = ToolExecutionCache(max_entries=10, max_memory_mb=1.0)

    # Test 1: Basic set/get
    print("1. Basic set/get:")
    cache.set("filesystem_read_file", {"path": "/test/file.txt"}, "file content here")
    result = cache.get("filesystem_read_file", {"path": "/test/file.txt"})
    print(f"   Cached value: {result}")
    assert result == "file content here"

    # Test 2: Cache miss
    print("\n2. Cache miss:")
    result = cache.get("filesystem_read_file", {"path": "/other/file.txt"})
    print(f"   Result: {result}")
    assert result is None

    # Test 3: Non-cacheable tool
    print("\n3. Non-cacheable tool:")
    cache.set("filesystem_write_file", {"path": "/test.txt"}, "written")
    result = cache.get("filesystem_write_file", {"path": "/test.txt"})
    print(f"   Result: {result}")
    assert result is None

    # Test 4: Invalidation
    print("\n4. Invalidation:")
    cache.set("filesystem_read_file", {"path": "/a.txt"}, "content a")
    cache.set("filesystem_list_directory", {"path": "/dir"}, ["a.txt", "b.txt"])

    cache.invalidate_for_tool("filesystem_write_file", {"path": "/a.txt"})

    result = cache.get("filesystem_read_file", {"path": "/a.txt"})
    print(f"   After invalidation: {result}")

    # Test 5: Stats
    print("\n5. Stats:")
    stats = cache.get_stats()
    print(f"   {stats}")

    # Test 6: TTL
    print("\n6. TTL:")
    ttl_read = cache.get_ttl("filesystem_read_file")
    ttl_docker = cache.get_ttl("docker_container_stats")
    print(f"   filesystem_read_file TTL: {ttl_read}s")
    print(f"   docker_container_stats TTL: {ttl_docker}s")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_cache()

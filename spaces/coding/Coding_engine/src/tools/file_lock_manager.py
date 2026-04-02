"""
File Lock Manager - Prevents race conditions when multiple Claude instances write files.

This module provides:
1. Per-file async locks for safe concurrent access
2. Lock timeout handling to prevent deadlocks
3. Conflict merging for concurrent writes
4. Global lock registry for coordination across instances
"""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, TypeVar, Any
from contextlib import asynccontextmanager
from datetime import datetime
import structlog
import hashlib

logger = structlog.get_logger(__name__)

T = TypeVar('T')


@dataclass
class LockInfo:
    """Information about a held lock."""
    file_path: str
    holder: str  # ID of holder (e.g., agent name)
    acquired_at: datetime
    timeout_seconds: float = 30.0

    @property
    def is_expired(self) -> bool:
        """Check if lock has exceeded timeout."""
        elapsed = (datetime.now() - self.acquired_at).total_seconds()
        return elapsed > self.timeout_seconds


@dataclass
class WriteOperation:
    """Represents a pending write operation."""
    file_path: str
    content: str
    source: str  # Which agent/instance is writing
    timestamp: datetime = field(default_factory=datetime.now)
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.md5(self.content.encode()).hexdigest()[:16]


@dataclass
class MergeResult:
    """Result of attempting to merge conflicting writes."""
    success: bool
    merged_content: Optional[str] = None
    conflict_type: Optional[str] = None
    resolution: Optional[str] = None


class FileLockManager:
    """
    Global file lock manager for concurrent file operations.
    
    Ensures only one Claude instance can write to a file at a time.
    Provides automatic timeout and conflict resolution.
    
    Usage:
        lock_manager = FileLockManager.get_instance()
        
        async with lock_manager.lock_file("src/app.ts", holder="fixer_1"):
            # Safe to write to file
            write_file("src/app.ts", content)
    """
    
    _instance: Optional["FileLockManager"] = None
    _creation_lock = asyncio.Lock()
    
    def __init__(self):
        """Initialize the lock manager."""
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_info: dict[str, LockInfo] = {}
        self._pending_writes: dict[str, list[WriteOperation]] = {}
        self._manager_lock = asyncio.Lock()
        self._logger = logger.bind(component="FileLockManager")
    
    @classmethod
    async def get_instance(cls) -> "FileLockManager":
        """Get singleton instance of FileLockManager."""
        if cls._instance is None:
            async with cls._creation_lock:
                if cls._instance is None:
                    cls._instance = FileLockManager()
        return cls._instance
    
    @classmethod
    def get_instance_sync(cls) -> "FileLockManager":
        """Get singleton instance synchronously (for init)."""
        if cls._instance is None:
            cls._instance = FileLockManager()
        return cls._instance
    
    def _normalize_path(self, file_path: str) -> str:
        """Normalize file path for consistent locking."""
        return str(Path(file_path).resolve())
    
    async def _get_lock(self, file_path: str) -> asyncio.Lock:
        """Get or create lock for a file."""
        normalized = self._normalize_path(file_path)
        async with self._manager_lock:
            if normalized not in self._locks:
                self._locks[normalized] = asyncio.Lock()
        return self._locks[normalized]
    
    @asynccontextmanager
    async def lock_file(
        self,
        file_path: str,
        holder: str = "unknown",
        timeout: float = 30.0,
    ):
        """
        Context manager for safely locking a file.
        
        Args:
            file_path: Path to the file to lock
            holder: Identifier for who is holding the lock
            timeout: Maximum time to wait for lock (seconds)
            
        Raises:
            asyncio.TimeoutError: If lock cannot be acquired within timeout
        """
        normalized = self._normalize_path(file_path)
        lock = await self._get_lock(file_path)
        
        try:
            # Try to acquire with timeout
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            
            # Record lock info
            self._lock_info[normalized] = LockInfo(
                file_path=normalized,
                holder=holder,
                acquired_at=datetime.now(),
                timeout_seconds=timeout,
            )
            
            self._logger.debug(
                "file_locked",
                file=file_path,
                holder=holder,
            )
            
            yield
            
        except asyncio.TimeoutError:
            self._logger.warning(
                "lock_timeout",
                file=file_path,
                holder=holder,
                timeout=timeout,
            )
            raise
            
        finally:
            # Release lock
            if lock.locked():
                lock.release()
            
            # Remove lock info
            self._lock_info.pop(normalized, None)
            
            self._logger.debug(
                "file_unlocked",
                file=file_path,
                holder=holder,
            )
    
    async def safe_write(
        self,
        file_path: str,
        content: str,
        holder: str = "unknown",
        timeout: float = 30.0,
        merge_on_conflict: bool = True,
    ) -> tuple[bool, str]:
        """
        Safely write to a file with automatic locking.
        
        Args:
            file_path: Path to write to
            content: Content to write
            holder: Identifier for who is writing
            timeout: Lock timeout
            merge_on_conflict: If True, attempt to merge with pending writes
            
        Returns:
            Tuple of (success, final_content)
        """
        async with self.lock_file(file_path, holder, timeout):
            path = Path(file_path)
            
            # Check for existing content
            existing_content = ""
            if path.exists():
                try:
                    existing_content = path.read_text(encoding='utf-8', errors='replace')
                except Exception as e:
                    self._logger.warning("read_existing_failed", file=file_path, error=str(e))
            
            # Check if content is same (no actual change needed)
            if existing_content == content:
                self._logger.debug("content_unchanged", file=file_path)
                return True, content
            
            # Attempt merge if there's existing content and merge is enabled
            final_content = content
            if existing_content and merge_on_conflict:
                merge_result = self._merge_content(existing_content, content, path.suffix)
                if merge_result.success:
                    final_content = merge_result.merged_content or content
                    self._logger.info(
                        "content_merged",
                        file=file_path,
                        resolution=merge_result.resolution,
                    )
            
            # Write the file
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(final_content, encoding='utf-8')
                self._logger.debug("file_written", file=file_path, size=len(final_content))
                return True, final_content
            except Exception as e:
                self._logger.error("write_failed", file=file_path, error=str(e))
                return False, existing_content
    
    def _merge_content(
        self,
        existing: str,
        new: str,
        file_ext: str,
    ) -> MergeResult:
        """
        Attempt to merge existing and new content.
        
        Args:
            existing: Current file content
            new: New content to write
            file_ext: File extension (for language-aware merging)
            
        Returns:
            MergeResult with merged content or failure info
        """
        # If new is a superset of existing, use new
        if existing in new:
            return MergeResult(
                success=True,
                merged_content=new,
                conflict_type="superset",
                resolution="new_contains_existing",
            )
        
        # If existing is a superset of new, keep existing
        if new in existing:
            return MergeResult(
                success=True,
                merged_content=existing,
                conflict_type="subset",
                resolution="existing_contains_new",
            )
        
        # Try language-specific merge
        if file_ext in ['.ts', '.tsx', '.js', '.jsx']:
            merged = self._merge_typescript(existing, new)
            if merged:
                return MergeResult(
                    success=True,
                    merged_content=merged,
                    conflict_type="different_content",
                    resolution="typescript_merge",
                )
        
        if file_ext == '.py':
            merged = self._merge_python(existing, new)
            if merged:
                return MergeResult(
                    success=True,
                    merged_content=merged,
                    conflict_type="different_content",
                    resolution="python_merge",
                )
        
        # Cannot merge - use new content
        return MergeResult(
            success=False,
            conflict_type="incompatible",
            resolution="overwrite_with_new",
        )
    
    def _merge_typescript(self, existing: str, new: str) -> Optional[str]:
        """Merge TypeScript/JavaScript files by combining imports and code."""
        import re
        
        # Extract imports
        import_pattern = r'^import\s+.*$'
        existing_imports = set(re.findall(import_pattern, existing, re.MULTILINE))
        new_imports = set(re.findall(import_pattern, new, re.MULTILINE))
        
        # Combine imports
        all_imports = sorted(existing_imports | new_imports)
        
        # Remove imports from both versions
        existing_code = re.sub(import_pattern, '', existing, flags=re.MULTILINE).strip()
        new_code = re.sub(import_pattern, '', new, flags=re.MULTILINE).strip()
        
        # If code sections are identical after removing imports, just use new
        if existing_code == new_code:
            merged = '\n'.join(all_imports) + '\n\n' + new_code
            return merged
        
        # Check for different exports (incompatible)
        existing_exports = set(re.findall(r'export\s+(?:const|function|class)\s+(\w+)', existing))
        new_exports = set(re.findall(r'export\s+(?:const|function|class)\s+(\w+)', new))
        
        # If same exports exist in both, use newer version
        conflicts = existing_exports & new_exports
        if conflicts and existing_exports == new_exports:
            return new  # Same structure, use newer
        
        # Can't automatically merge complex differences
        return None
    
    def _merge_python(self, existing: str, new: str) -> Optional[str]:
        """Merge Python files by combining imports and definitions."""
        import re
        
        # Extract imports
        import_pattern = r'^(?:from\s+\S+\s+)?import\s+.*$'
        existing_imports = set(re.findall(import_pattern, existing, re.MULTILINE))
        new_imports = set(re.findall(import_pattern, new, re.MULTILINE))
        
        all_imports = sorted(existing_imports | new_imports)
        
        # Remove imports
        existing_code = re.sub(import_pattern, '', existing, flags=re.MULTILINE).strip()
        new_code = re.sub(import_pattern, '', new, flags=re.MULTILINE).strip()
        
        if existing_code == new_code:
            merged = '\n'.join(all_imports) + '\n\n' + new_code
            return merged
        
        # Check for class/function definitions
        existing_defs = set(re.findall(r'(?:class|def)\s+(\w+)', existing))
        new_defs = set(re.findall(r'(?:class|def)\s+(\w+)', new))
        
        # If same definitions, use newer
        if existing_defs == new_defs:
            return new
        
        return None
    
    def is_locked(self, file_path: str) -> bool:
        """Check if a file is currently locked."""
        normalized = self._normalize_path(file_path)
        lock = self._locks.get(normalized)
        return lock.locked() if lock else False
    
    def get_lock_info(self, file_path: str) -> Optional[LockInfo]:
        """Get information about who holds a file lock."""
        normalized = self._normalize_path(file_path)
        return self._lock_info.get(normalized)
    
    def get_all_locks(self) -> dict[str, LockInfo]:
        """Get all currently held locks."""
        return dict(self._lock_info)
    
    async def force_release(self, file_path: str) -> bool:
        """
        Force release a lock (use with caution!).
        
        Only use this for expired or orphaned locks.
        """
        normalized = self._normalize_path(file_path)
        lock = self._locks.get(normalized)
        
        if lock and lock.locked():
            # Check if expired
            info = self._lock_info.get(normalized)
            if info and info.is_expired:
                self._logger.warning(
                    "force_releasing_expired_lock",
                    file=file_path,
                    holder=info.holder,
                    held_for=(datetime.now() - info.acquired_at).total_seconds(),
                )
                lock.release()
                self._lock_info.pop(normalized, None)
                return True
        
        return False
    
    async def cleanup_expired_locks(self) -> int:
        """Clean up all expired locks. Returns count of released locks."""
        released = 0
        for path, info in list(self._lock_info.items()):
            if info.is_expired:
                if await self.force_release(path):
                    released += 1
        return released


# Global singleton accessor
_file_lock_manager: Optional[FileLockManager] = None


def get_file_lock_manager() -> FileLockManager:
    """Get the global FileLockManager instance."""
    global _file_lock_manager
    if _file_lock_manager is None:
        _file_lock_manager = FileLockManager.get_instance_sync()
    return _file_lock_manager


# Convenience decorator for file operations
def with_file_lock(file_path_arg: int = 0, holder_arg: Optional[int] = None):
    """
    Decorator to automatically lock files during function execution.
    
    Args:
        file_path_arg: Position of file path in function args
        holder_arg: Position of holder ID in args (optional)
        
    Usage:
        @with_file_lock(file_path_arg=0)
        async def write_config(file_path: str, content: str):
            # File is locked during this function
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            file_path = args[file_path_arg]
            holder = args[holder_arg] if holder_arg is not None else "decorator"
            
            lock_manager = get_file_lock_manager()
            async with lock_manager.lock_file(file_path, holder):
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator
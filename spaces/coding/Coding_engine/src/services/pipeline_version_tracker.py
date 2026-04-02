"""Pipeline version tracker.

Tracks versions of pipeline components, artifacts, and configurations.
Supports semantic versioning, changelogs, and version comparison.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class _Version:
    """A version entry."""
    version_id: str = ""
    component: str = ""
    version: str = ""  # semantic version string e.g. "1.2.3"
    major: int = 0
    minor: int = 0
    patch: int = 0
    changelog: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: str = "draft"  # draft, released, deprecated
    created_at: float = 0.0
    released_at: float = 0.0
    seq: int = 0


class PipelineVersionTracker:
    """Tracks component versions."""

    VERSION_STATUSES = ("draft", "released", "deprecated")

    def __init__(self, max_versions: int = 100000):
        self._max_versions = max_versions
        self._versions: Dict[str, _Version] = {}
        self._version_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_versions_created": 0,
            "total_released": 0,
            "total_deprecated": 0,
        }

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------

    def create_version(self, component: str, version: str,
                       changelog: str = "", author: str = "",
                       tags: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None) -> str:
        """Create a new version entry."""
        if not component or not version:
            return ""
        parsed = self._parse_version(version)
        if parsed is None:
            return ""
        if len(self._versions) >= self._max_versions:
            self._prune_versions()

        self._version_seq += 1
        vid = "ver-" + hashlib.md5(
            f"{component}{version}{time.time()}{self._version_seq}".encode()
        ).hexdigest()[:12]

        major, minor, patch = parsed
        self._versions[vid] = _Version(
            version_id=vid,
            component=component,
            version=version,
            major=major,
            minor=minor,
            patch=patch,
            changelog=changelog,
            author=author,
            tags=tags or [],
            metadata=metadata or {},
            created_at=time.time(),
            seq=self._version_seq,
        )
        self._stats["total_versions_created"] += 1
        self._fire("version_created", {
            "version_id": vid, "component": component, "version": version,
        })
        return vid

    def get_version(self, version_id: str) -> Optional[Dict]:
        """Get version info."""
        v = self._versions.get(version_id)
        if not v:
            return None
        return {
            "version_id": v.version_id,
            "component": v.component,
            "version": v.version,
            "major": v.major,
            "minor": v.minor,
            "patch": v.patch,
            "changelog": v.changelog,
            "author": v.author,
            "tags": list(v.tags),
            "status": v.status,
            "seq": v.seq,
        }

    def release_version(self, version_id: str) -> bool:
        """Release a version."""
        v = self._versions.get(version_id)
        if not v or v.status != "draft":
            return False
        v.status = "released"
        v.released_at = time.time()
        self._stats["total_released"] += 1
        return True

    def deprecate_version(self, version_id: str) -> bool:
        """Deprecate a version."""
        v = self._versions.get(version_id)
        if not v or v.status == "deprecated":
            return False
        v.status = "deprecated"
        self._stats["total_deprecated"] += 1
        return True

    def remove_version(self, version_id: str) -> bool:
        """Remove a version."""
        if version_id not in self._versions:
            return False
        del self._versions[version_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_latest(self, component: str,
                   status: Optional[str] = None) -> Optional[Dict]:
        """Get latest version for a component."""
        best = None
        for v in self._versions.values():
            if v.component != component:
                continue
            if status and v.status != status:
                continue
            if best is None or self._compare(v, best) > 0:
                best = v
        if not best:
            return None
        return {
            "version_id": best.version_id,
            "component": best.component,
            "version": best.version,
            "status": best.status,
        }

    def get_component_history(self, component: str,
                              limit: int = 50) -> List[Dict]:
        """Get version history for a component."""
        result = []
        for v in self._versions.values():
            if v.component != component:
                continue
            result.append({
                "version_id": v.version_id,
                "version": v.version,
                "status": v.status,
                "changelog": v.changelog,
                "author": v.author,
                "seq": v.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def search_versions(self, component: Optional[str] = None,
                        status: Optional[str] = None,
                        author: Optional[str] = None,
                        tag: Optional[str] = None,
                        limit: int = 100) -> List[Dict]:
        """Search versions."""
        result = []
        for v in self._versions.values():
            if component and v.component != component:
                continue
            if status and v.status != status:
                continue
            if author and v.author != author:
                continue
            if tag and tag not in v.tags:
                continue
            result.append({
                "version_id": v.version_id,
                "component": v.component,
                "version": v.version,
                "status": v.status,
                "seq": v.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def list_components(self) -> List[Dict]:
        """List all components with their latest versions."""
        comp_latest: Dict[str, _Version] = {}
        comp_count: Dict[str, int] = {}
        for v in self._versions.values():
            comp_count[v.component] = comp_count.get(v.component, 0) + 1
            if v.component not in comp_latest or \
               self._compare(v, comp_latest[v.component]) > 0:
                comp_latest[v.component] = v

        result = []
        for comp, latest in comp_latest.items():
            result.append({
                "component": comp,
                "latest_version": latest.version,
                "latest_status": latest.status,
                "version_count": comp_count[comp],
            })
        result.sort(key=lambda x: x["component"])
        return result

    def compare_versions(self, version_a: str,
                         version_b: str) -> int:
        """Compare two version strings. Returns -1, 0, or 1."""
        pa = self._parse_version(version_a)
        pb = self._parse_version(version_b)
        if pa is None or pb is None:
            return 0
        if pa < pb:
            return -1
        elif pa > pb:
            return 1
        return 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_version(version: str) -> Optional[Tuple[int, int, int]]:
        """Parse semantic version string."""
        parts = version.split(".")
        if len(parts) != 3:
            return None
        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None

    @staticmethod
    def _compare(a: _Version, b: _Version) -> int:
        """Compare two version objects."""
        ta = (a.major, a.minor, a.patch)
        tb = (b.major, b.minor, b.patch)
        if ta < tb:
            return -1
        elif ta > tb:
            return 1
        return 0

    def _prune_versions(self) -> None:
        """Remove oldest deprecated versions."""
        prunable = [(k, v) for k, v in self._versions.items()
                    if v.status == "deprecated"]
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._versions) // 4)
        for k, _ in prunable[:to_remove]:
            del self._versions[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_versions": len(self._versions),
            "released_versions": sum(
                1 for v in self._versions.values() if v.status == "released"
            ),
            "component_count": len(set(
                v.component for v in self._versions.values()
            )),
        }

    def reset(self) -> None:
        self._versions.clear()
        self._version_seq = 0
        self._stats = {k: 0 for k in self._stats}

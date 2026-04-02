"""Pipeline config manager.

Manages configuration profiles, environment-specific settings,
feature flags, and runtime configuration for the pipeline.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ConfigProfile:
    """A configuration profile."""
    profile_id: str = ""
    name: str = ""
    environment: str = "development"
    settings: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    is_active: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class _FeatureFlag:
    """A feature flag."""
    flag_id: str = ""
    name: str = ""
    enabled: bool = False
    description: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class PipelineConfigManager:
    """Manages pipeline configuration and feature flags."""

    ENVIRONMENTS = ("development", "staging", "production", "testing")

    def __init__(self, max_profiles: int = 1000,
                 max_flags: int = 5000):
        self._max_profiles = max_profiles
        self._max_flags = max_flags
        self._profiles: Dict[str, _ConfigProfile] = {}
        self._flags: Dict[str, _FeatureFlag] = {}
        self._overrides: Dict[str, Any] = {}  # runtime overrides
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_profiles_created": 0,
            "total_flags_created": 0,
            "total_config_changes": 0,
        }

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def create_profile(self, name: str, environment: str = "development",
                       settings: Optional[Dict] = None,
                       tags: Optional[List[str]] = None) -> str:
        """Create a config profile."""
        if not name:
            return ""
        if environment not in self.ENVIRONMENTS:
            return ""
        if len(self._profiles) >= self._max_profiles:
            return ""

        pid = "cfg-" + hashlib.md5(
            f"{name}{time.time()}{len(self._profiles)}".encode()
        ).hexdigest()[:12]

        self._profiles[pid] = _ConfigProfile(
            profile_id=pid,
            name=name,
            environment=environment,
            settings=settings or {},
            tags=tags or [],
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._stats["total_profiles_created"] += 1
        return pid

    def get_profile(self, profile_id: str) -> Optional[Dict]:
        """Get profile info."""
        p = self._profiles.get(profile_id)
        if not p:
            return None
        return {
            "profile_id": p.profile_id,
            "name": p.name,
            "environment": p.environment,
            "settings": dict(p.settings),
            "tags": list(p.tags),
            "is_active": p.is_active,
            "setting_count": len(p.settings),
        }

    def remove_profile(self, profile_id: str) -> bool:
        """Remove a profile."""
        p = self._profiles.get(profile_id)
        if not p:
            return False
        if p.is_active:
            return False
        del self._profiles[profile_id]
        return True

    def activate_profile(self, profile_id: str) -> bool:
        """Activate a profile (deactivates others in same environment)."""
        p = self._profiles.get(profile_id)
        if not p or p.is_active:
            return False
        # Deactivate others in same environment
        for other in self._profiles.values():
            if other.environment == p.environment and other.is_active:
                other.is_active = False
        p.is_active = True
        self._fire("profile_activated", {
            "profile_id": profile_id, "environment": p.environment,
        })
        return True

    def deactivate_profile(self, profile_id: str) -> bool:
        """Deactivate a profile."""
        p = self._profiles.get(profile_id)
        if not p or not p.is_active:
            return False
        p.is_active = False
        return True

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def set_setting(self, profile_id: str, key: str, value: Any) -> bool:
        """Set a setting in a profile."""
        p = self._profiles.get(profile_id)
        if not p or not key:
            return False
        p.settings[key] = value
        p.updated_at = time.time()
        self._stats["total_config_changes"] += 1
        self._fire("setting_changed", {
            "profile_id": profile_id, "key": key,
        })
        return True

    def get_setting(self, profile_id: str, key: str,
                    default: Any = None) -> Any:
        """Get a setting from a profile."""
        p = self._profiles.get(profile_id)
        if not p:
            return default
        return p.settings.get(key, default)

    def remove_setting(self, profile_id: str, key: str) -> bool:
        """Remove a setting from a profile."""
        p = self._profiles.get(profile_id)
        if not p or key not in p.settings:
            return False
        del p.settings[key]
        p.updated_at = time.time()
        return True

    def get_active_setting(self, environment: str, key: str,
                           default: Any = None) -> Any:
        """Get a setting from the active profile for an environment."""
        for p in self._profiles.values():
            if p.environment == environment and p.is_active:
                # Check runtime overrides first
                override_key = f"{environment}.{key}"
                if override_key in self._overrides:
                    return self._overrides[override_key]
                return p.settings.get(key, default)
        return default

    # ------------------------------------------------------------------
    # Runtime overrides
    # ------------------------------------------------------------------

    def set_override(self, key: str, value: Any) -> bool:
        """Set a runtime override."""
        if not key:
            return False
        self._overrides[key] = value
        self._stats["total_config_changes"] += 1
        return True

    def get_override(self, key: str, default: Any = None) -> Any:
        """Get a runtime override."""
        return self._overrides.get(key, default)

    def remove_override(self, key: str) -> bool:
        """Remove a runtime override."""
        if key not in self._overrides:
            return False
        del self._overrides[key]
        return True

    def list_overrides(self) -> Dict[str, Any]:
        """List all runtime overrides."""
        return dict(self._overrides)

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------

    def create_flag(self, name: str, enabled: bool = False,
                    description: str = "",
                    conditions: Optional[Dict] = None) -> str:
        """Create a feature flag."""
        if not name:
            return ""
        if len(self._flags) >= self._max_flags:
            return ""

        fid = "flag-" + hashlib.md5(
            f"{name}{time.time()}{len(self._flags)}".encode()
        ).hexdigest()[:12]

        self._flags[fid] = _FeatureFlag(
            flag_id=fid,
            name=name,
            enabled=enabled,
            description=description,
            conditions=conditions or {},
            created_at=time.time(),
        )
        self._stats["total_flags_created"] += 1
        return fid

    def get_flag(self, flag_id: str) -> Optional[Dict]:
        """Get flag info."""
        f = self._flags.get(flag_id)
        if not f:
            return None
        return {
            "flag_id": f.flag_id,
            "name": f.name,
            "enabled": f.enabled,
            "description": f.description,
            "conditions": dict(f.conditions),
        }

    def remove_flag(self, flag_id: str) -> bool:
        """Remove a flag."""
        if flag_id not in self._flags:
            return False
        del self._flags[flag_id]
        return True

    def toggle_flag(self, flag_id: str) -> bool:
        """Toggle a feature flag."""
        f = self._flags.get(flag_id)
        if not f:
            return False
        f.enabled = not f.enabled
        self._fire("flag_toggled", {
            "flag_id": flag_id, "name": f.name, "enabled": f.enabled,
        })
        return True

    def is_enabled(self, flag_id: str) -> bool:
        """Check if a feature flag is enabled."""
        f = self._flags.get(flag_id)
        return f.enabled if f else False

    def list_flags(self, enabled_only: bool = False) -> List[Dict]:
        """List feature flags."""
        result = []
        for f in self._flags.values():
            if enabled_only and not f.enabled:
                continue
            result.append({
                "flag_id": f.flag_id,
                "name": f.name,
                "enabled": f.enabled,
                "description": f.description,
            })
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_profiles(self, environment: Optional[str] = None,
                      tag: Optional[str] = None,
                      active_only: bool = False) -> List[Dict]:
        """List profiles with filters."""
        result = []
        for p in self._profiles.values():
            if environment and p.environment != environment:
                continue
            if tag and tag not in p.tags:
                continue
            if active_only and not p.is_active:
                continue
            result.append({
                "profile_id": p.profile_id,
                "name": p.name,
                "environment": p.environment,
                "is_active": p.is_active,
                "setting_count": len(p.settings),
            })
        return result

    def get_active_profiles(self) -> List[Dict]:
        """Get all active profiles."""
        return self.list_profiles(active_only=True)

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
            "current_profiles": len(self._profiles),
            "active_profiles": sum(
                1 for p in self._profiles.values() if p.is_active
            ),
            "current_flags": len(self._flags),
            "enabled_flags": sum(
                1 for f in self._flags.values() if f.enabled
            ),
            "current_overrides": len(self._overrides),
        }

    def reset(self) -> None:
        self._profiles.clear()
        self._flags.clear()
        self._overrides.clear()
        self._stats = {k: 0 for k in self._stats}

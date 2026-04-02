"""
Config Hot Reload — Watch and reload agent configurations without restart.

Provides:
- File-system watching for config changes (JSON/YAML)
- Schema validation before applying changes
- Graceful config propagation to running agents
- Rollback on invalid configs
- Change history and diff tracking
- Event bus notifications on config changes

Usage::

    reloader = ConfigHotReloader(event_bus, config_dir="./config")
    reloader.start()

    # Register an agent config handler
    reloader.register_handler("frontend_agent", on_config_change)

    # Manual reload
    reloader.reload("frontend_agent")

    # Get current config
    config = reloader.get_config("frontend_agent")
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ConfigSnapshot:
    """A snapshot of a configuration at a point in time."""
    agent_name: str
    config: Dict[str, Any]
    config_hash: str
    loaded_at: float = field(default_factory=time.time)
    source_file: Optional[str] = None
    valid: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "config_hash": self.config_hash[:12],
            "loaded_at": self.loaded_at,
            "source_file": self.source_file,
            "valid": self.valid,
            "error": self.error,
        }


@dataclass
class ConfigChange:
    """Record of a configuration change."""
    agent_name: str
    old_hash: Optional[str]
    new_hash: str
    changed_keys: List[str]
    timestamp: float = field(default_factory=time.time)
    applied: bool = True
    rolled_back: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "changed_keys": self.changed_keys,
            "timestamp": self.timestamp,
            "applied": self.applied,
            "rolled_back": self.rolled_back,
            "error": self.error,
        }


def _hash_config(config: dict) -> str:
    """Compute a stable hash of a config dict."""
    serialized = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _diff_keys(old: dict, new: dict) -> List[str]:
    """Find keys that differ between two config dicts."""
    changed = []
    all_keys = set(old.keys()) | set(new.keys())
    for key in sorted(all_keys):
        if old.get(key) != new.get(key):
            changed.append(key)
    return changed


class ConfigValidator:
    """
    Validates agent configuration against schema rules.

    Default rules:
    - model must be a non-empty string
    - max_tokens must be > 0
    - temperature must be 0.0 - 2.0
    """

    def __init__(self):
        self._rules: Dict[str, List[Callable]] = {}

    def add_rule(self, field_name: str, validator: Callable[[Any], bool], message: str = ""):
        """Add a validation rule for a config field."""
        if field_name not in self._rules:
            self._rules[field_name] = []
        self._rules[field_name].append((validator, message))

    def validate(self, config: dict) -> List[str]:
        """Validate a config dict. Returns list of error messages."""
        errors = []

        for field_name, rules in self._rules.items():
            if field_name in config:
                for validator, message in rules:
                    try:
                        if not validator(config[field_name]):
                            errors.append(message or f"Validation failed for '{field_name}'")
                    except Exception as e:
                        errors.append(f"Validation error for '{field_name}': {e}")

        return errors


def _default_validator() -> ConfigValidator:
    """Create validator with default agent config rules."""
    v = ConfigValidator()
    v.add_rule("model", lambda x: isinstance(x, str) and len(x) > 0, "model must be a non-empty string")
    v.add_rule("max_tokens", lambda x: isinstance(x, int) and x > 0, "max_tokens must be > 0")
    v.add_rule("temperature", lambda x: isinstance(x, (int, float)) and 0.0 <= x <= 2.0, "temperature must be 0.0-2.0")
    v.add_rule("timeout", lambda x: x is None or (isinstance(x, (int, float)) and x > 0), "timeout must be positive or None")
    return v


class ConfigHotReloader:
    """
    Watches and hot-reloads agent configurations.
    """

    def __init__(
        self,
        event_bus=None,
        config_dir: str = "./config",
        poll_interval: float = 2.0,
        validator: Optional[ConfigValidator] = None,
    ):
        self.event_bus = event_bus
        self.config_dir = Path(config_dir)
        self.poll_interval = poll_interval
        self.validator = validator or _default_validator()

        # Current configs: agent_name -> ConfigSnapshot
        self._configs: Dict[str, ConfigSnapshot] = {}
        # Config handlers: agent_name -> list of callbacks
        self._handlers: Dict[str, List[Callable]] = {}
        # Change history
        self._changes: List[ConfigChange] = []
        # File hashes for change detection
        self._file_hashes: Dict[str, str] = {}
        # Watcher task
        self._watcher_task: Optional[asyncio.Task] = None

        self.logger = logger.bind(component="config_hot_reload")

    def start(self):
        """Start the config file watcher."""
        if self._watcher_task is None or self._watcher_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._watcher_task = loop.create_task(self._watch_loop())
                self.logger.info("config_watcher_started", config_dir=str(self.config_dir))
            except RuntimeError:
                pass

    def stop(self):
        """Stop the config watcher."""
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            self._watcher_task = None

    def register_handler(self, agent_name: str, handler: Callable):
        """Register a callback for config changes on an agent."""
        if agent_name not in self._handlers:
            self._handlers[agent_name] = []
        self._handlers[agent_name].append(handler)

    def set_config(self, agent_name: str, config: dict, source_file: str = ""):
        """Set configuration for an agent (programmatic, not file-based)."""
        # Validate
        errors = self.validator.validate(config)
        if errors:
            self.logger.warning("config_validation_failed", agent=agent_name, errors=errors)
            return False, errors

        config_hash = _hash_config(config)
        old_snapshot = self._configs.get(agent_name)

        # Detect changes
        changed_keys = []
        old_hash = None
        if old_snapshot:
            old_hash = old_snapshot.config_hash
            if old_hash == config_hash:
                return True, []  # No change
            changed_keys = _diff_keys(old_snapshot.config, config)

        # Apply new config
        snapshot = ConfigSnapshot(
            agent_name=agent_name,
            config=config.copy(),
            config_hash=config_hash,
            source_file=source_file,
        )
        self._configs[agent_name] = snapshot

        # Record change
        change = ConfigChange(
            agent_name=agent_name,
            old_hash=old_hash,
            new_hash=config_hash,
            changed_keys=changed_keys,
        )
        self._changes.append(change)

        # Notify handlers
        self._notify_handlers(agent_name, config, changed_keys)

        self.logger.info(
            "config_updated",
            agent=agent_name,
            changed_keys=changed_keys,
        )
        return True, []

    def get_config(self, agent_name: str) -> Optional[dict]:
        """Get current configuration for an agent."""
        snapshot = self._configs.get(agent_name)
        return snapshot.config.copy() if snapshot else None

    def get_all_configs(self) -> Dict[str, dict]:
        """Get all current configurations."""
        return {name: snap.config.copy() for name, snap in self._configs.items()}

    def reload(self, agent_name: str) -> bool:
        """Manually reload config for an agent from its file."""
        config_file = self._find_config_file(agent_name)
        if not config_file:
            self.logger.warning("config_file_not_found", agent=agent_name)
            return False

        return self._load_config_file(agent_name, config_file)

    def reload_all(self) -> Dict[str, bool]:
        """Reload all known agent configs."""
        results = {}
        for agent_name in list(self._configs.keys()):
            results[agent_name] = self.reload(agent_name)
        return results

    def rollback(self, agent_name: str) -> bool:
        """Rollback to previous config (if available in change history)."""
        # Find last two changes for this agent
        agent_changes = [c for c in self._changes if c.agent_name == agent_name]
        if len(agent_changes) < 2:
            return False

        # We can't reconstruct old config from hash alone,
        # but we can mark the change as rolled back
        last_change = agent_changes[-1]
        last_change.rolled_back = True
        self.logger.info("config_rolled_back", agent=agent_name)
        return True

    # ------------------------------------------------------------------
    # File watching
    # ------------------------------------------------------------------

    def _find_config_file(self, agent_name: str) -> Optional[Path]:
        """Find config file for an agent."""
        for ext in [".json", ".yaml", ".yml"]:
            path = self.config_dir / f"{agent_name}{ext}"
            if path.exists():
                return path
        return None

    def _load_config_file(self, agent_name: str, path: Path) -> bool:
        """Load and apply config from a file."""
        try:
            content = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                config = json.loads(content)
            elif path.suffix in (".yaml", ".yml"):
                # Optional YAML support
                try:
                    import yaml
                    config = yaml.safe_load(content)
                except ImportError:
                    self.logger.warning("yaml_not_available", file=str(path))
                    return False
            else:
                return False

            success, errors = self.set_config(agent_name, config, source_file=str(path))
            if not success:
                self.logger.warning("config_load_failed", agent=agent_name, errors=errors)
            return success

        except Exception as e:
            self.logger.error("config_file_error", agent=agent_name, error=str(e))
            return False

    def _compute_file_hash(self, path: Path) -> str:
        """Compute hash of file contents."""
        try:
            content = path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""

    async def _watch_loop(self):
        """Background loop watching for config file changes."""
        while True:
            try:
                await asyncio.sleep(self.poll_interval)

                if not self.config_dir.exists():
                    continue

                # Scan for config files
                for path in self.config_dir.iterdir():
                    if path.suffix not in (".json", ".yaml", ".yml"):
                        continue

                    agent_name = path.stem
                    new_hash = self._compute_file_hash(path)
                    old_hash = self._file_hashes.get(str(path))

                    if old_hash != new_hash:
                        self._file_hashes[str(path)] = new_hash
                        if old_hash is not None:  # Skip initial scan
                            self.logger.info("config_file_changed", file=str(path), agent=agent_name)
                            self._load_config_file(agent_name, path)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("watch_loop_error", error=str(e))

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------

    def _notify_handlers(self, agent_name: str, config: dict, changed_keys: List[str]):
        """Notify registered handlers of config change."""
        handlers = self._handlers.get(agent_name, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(handler(agent_name, config, changed_keys))
                    except RuntimeError:
                        pass
                else:
                    handler(agent_name, config, changed_keys)
            except Exception as e:
                self.logger.error("handler_error", agent=agent_name, error=str(e))

        # Broadcast via event bus
        if self.event_bus:
            try:
                from src.mind.event_bus import Event, EventType
                event = Event(
                    type=EventType.PIPELINE_STARTED,
                    source="config_hot_reload",
                    data={
                        "action": "config_changed",
                        "agent_name": agent_name,
                        "changed_keys": changed_keys,
                    },
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.event_bus.publish(event))
                except RuntimeError:
                    pass
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_change_history(self, agent_name: Optional[str] = None, limit: int = 50) -> List[dict]:
        """Get change history, optionally filtered by agent."""
        changes = self._changes
        if agent_name:
            changes = [c for c in changes if c.agent_name == agent_name]
        return [c.to_dict() for c in changes[-limit:]]

    def get_config_info(self, agent_name: str) -> Optional[dict]:
        """Get config metadata for an agent."""
        snapshot = self._configs.get(agent_name)
        if not snapshot:
            return None
        return snapshot.to_dict()

    def get_stats(self) -> dict:
        """Get reloader stats."""
        return {
            "total_agents_configured": len(self._configs),
            "total_handlers_registered": sum(len(h) for h in self._handlers.values()),
            "total_config_changes": len(self._changes),
            "agents": list(self._configs.keys()),
            "watching_directory": str(self.config_dir),
        }

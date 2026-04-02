"""Agent output formatter.

Formats agent output data into specified formats (json, csv-like, summary),
providing per-agent format configuration and change notifications.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _FormatConfig:
    """A single format configuration."""
    config_id: str = ""
    agent_id: str = ""
    format_type: str = "json"
    created_at: float = 0.0
    seq: int = 0


class AgentOutputFormatter:
    """Formats agent output data into specified formats."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._formatters: Dict[str, _FormatConfig] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max(1, max_entries)
        self._stats = {
            "total_configured": 0,
            "total_formatted": 0,
            "total_removed": 0,
        }

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure_format(
        self,
        agent_id: str,
        format_type: str = "json",
    ) -> str:
        """Configure output format for an agent. Returns config ID."""
        if not agent_id:
            return ""
        if format_type not in ("json", "csv", "summary"):
            format_type = "json"
        if len(self._formatters) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()

        raw = f"{agent_id}{format_type}{now}{self._seq}".encode()
        cid = "aof-" + hashlib.sha256(raw).hexdigest()[:12]

        self._formatters[cid] = _FormatConfig(
            config_id=cid,
            agent_id=agent_id,
            format_type=format_type,
            created_at=now,
            seq=self._seq,
        )
        self._stats["total_configured"] += 1

        logger.debug("format_configured", config_id=cid, agent_id=agent_id,
                      format_type=format_type)
        self._fire("format_configured", {
            "config_id": cid,
            "agent_id": agent_id,
            "format_type": format_type,
        })
        return cid

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def format_output(self, agent_id: str, data: dict) -> str:
        """Format data according to the agent's configured format."""
        cfg = self._find_config(agent_id)
        if cfg is None:
            return ""

        self._stats["total_formatted"] += 1

        if cfg.format_type == "json":
            return json.dumps(data)
        elif cfg.format_type == "csv":
            keys = list(data.keys())
            vals = [str(data[k]) for k in keys]
            return ",".join(keys) + "\n" + ",".join(vals)
        elif cfg.format_type == "summary":
            parts = [f"{k}={v}" for k, v in data.items()]
            return "; ".join(parts)
        return ""

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_config(self, agent_id: str) -> Optional[Dict]:
        """Get format config for an agent."""
        cfg = self._find_config(agent_id)
        if cfg is None:
            return None
        return self._to_dict(cfg)

    def remove_config(self, config_id: str) -> bool:
        """Remove a format config by ID."""
        if config_id not in self._formatters:
            return False
        del self._formatters[config_id]
        self._stats["total_removed"] += 1
        logger.debug("format_removed", config_id=config_id)
        self._fire("format_removed", {"config_id": config_id})
        return True

    def get_config_count(self, agent_id: str = "") -> int:
        """Return the number of stored configs, optionally filtered by agent."""
        if not agent_id:
            return len(self._formatters)
        return sum(1 for c in self._formatters.values() if c.agent_id == agent_id)

    def list_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have format configs."""
        agents: set[str] = set()
        for c in self._formatters.values():
            agents.add(c.agent_id)
        return sorted(agents)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = cb
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return formatter statistics."""
        return {
            **self._stats,
            "current_configs": len(self._formatters),
            "current_agents": len(self.list_agents()),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all configs, callbacks, and stats."""
        self._formatters.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_config(self, agent_id: str) -> Optional[_FormatConfig]:
        """Find the latest config for an agent."""
        latest: Optional[_FormatConfig] = None
        for c in self._formatters.values():
            if c.agent_id != agent_id:
                continue
            if latest is None or (c.created_at, c.seq) > (latest.created_at, latest.seq):
                latest = c
        return latest

    @staticmethod
    def _to_dict(c: _FormatConfig) -> Dict:
        return {
            "config_id": c.config_id,
            "agent_id": c.agent_id,
            "format_type": c.format_type,
            "created_at": c.created_at,
            "seq": c.seq,
        }

    def _prune(self) -> None:
        """Remove the oldest quarter of configs."""
        items = sorted(self._formatters.items(),
                       key=lambda x: (x[1].created_at, x[1].seq))
        to_remove = max(1, len(items) // 4)
        for k, _ in items[:to_remove]:
            del self._formatters[k]
        logger.debug("configs_pruned", count=to_remove)

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.warning("callback_error", action=action, exc_info=True)

"""Phase 11.D — Agent-YAML Registry.

Loads `configs/agents/*.yaml` files which define which events each agent
claims. Schema per file:

  agent: brain-bubbles
  description: "Bubble CRUD + navigation on the VibeMind canvas"
  default_namespace: bubble        # for auto-seed; events with this prefix
                                   # default to this agent if no other claims
  events:
    - bubble.create
    - bubble.update
    - bubble.evaluate
  fallback_agent: brain-bubbles-phi3   # optional — when primary offline
  notes: |
    Free-text notes about this agent's role.

Constraints:
  - One event lives in exactly ONE agent's events: list. Conflicts are flagged
    in validate(). The first-loaded YAML wins on conflict (deterministic by
    alphabetical filename order).
  - Pro Agent: many events. Pro Event: one agent.

Public API:
  AgentYamlRegistry().get_event_agent(event_id) -> str|None
  AgentYamlRegistry().get_agent_events(agent_name) -> list[str]
  AgentYamlRegistry().list_agents() -> list[dict]
  AgentYamlRegistry().move_event(event_id, from_agent, to_agent) -> bool
  AgentYamlRegistry().reload() -> dict (stats)
  AgentYamlRegistry().validate() -> list[str]   (conflict messages)
  AgentYamlRegistry().auto_seed(namespace_to_agent_map) -> dict
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "configs" / "agents"


def _atomic_write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Write YAML atomically: tmp file + rename."""
    import yaml as _yaml
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        _yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True,
                        default_flow_style=False)
    os.replace(tmp, path)


class AgentYamlRegistry:
    """In-memory registry of agent-event mappings, loaded from YAML files."""

    def __init__(self, configs_dir: Optional[Path] = None) -> None:
        self.dir = Path(configs_dir) if configs_dir else _CONFIGS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._agents: Dict[str, Dict[str, Any]] = {}    # agent_name -> manifest
        self._event_to_agent: Dict[str, str] = {}        # event_id -> agent_name
        self._mtime_cache: Dict[Path, float] = {}
        self._last_load_ts: float = 0.0
        self._stats: Dict[str, Any] = {
            "agents_loaded": 0, "events_total": 0, "conflicts": [],
            "last_reload_ts": 0.0,
        }
        self.reload()

    def reload(self) -> Dict[str, Any]:
        """Re-read all YAMLs from disk. Idempotent."""
        try:
            import yaml as _yaml
        except Exception as e:
            logger.error(f"[agent_yaml] PyYAML not available: {e}")
            return {"ok": False, "error": "pyyaml not installed"}

        with self._lock:
            self._agents.clear()
            self._event_to_agent.clear()
            conflicts: List[str] = []
            yaml_files = sorted(self.dir.glob("*.yaml")) + sorted(self.dir.glob("*.yml"))

            for fp in yaml_files:
                try:
                    data = _yaml.safe_load(open(fp, encoding="utf-8")) or {}
                except Exception as e:
                    conflicts.append(f"parse error in {fp.name}: {e}")
                    continue
                agent_name = data.get("agent") or fp.stem
                events = data.get("events") or []
                if not isinstance(events, list):
                    events = []
                self._agents[agent_name] = {
                    "agent": agent_name,
                    "description": data.get("description", ""),
                    "default_namespace": data.get("default_namespace", ""),
                    "events": list(events),
                    "fallback_agent": data.get("fallback_agent", ""),
                    "notes": data.get("notes", ""),
                    "_path": str(fp),
                    "_mtime": fp.stat().st_mtime,
                }
                self._mtime_cache[fp] = fp.stat().st_mtime
                for ev in events:
                    if ev in self._event_to_agent:
                        conflicts.append(
                            f"event '{ev}' claimed by both "
                            f"'{self._event_to_agent[ev]}' and '{agent_name}' — "
                            f"first wins"
                        )
                        continue
                    self._event_to_agent[ev] = agent_name

            # The space registry is the canonical event/agent source. Agent YAMLs
            # may add metadata, but cannot leave whole event families unroutable.
            canonical = self.dir.parents[3] / "config" / "space_agent_registry.yml"
            if canonical.exists():
                try:
                    space_data = _yaml.safe_load(canonical.read_text(encoding="utf-8")) or {}
                    for space in (space_data.get("spaces") or {}).values():
                        if not isinstance(space, dict) or not space.get("enabled", True):
                            continue
                        agent_name = space.get("agent")
                        events = space.get("events") or {}
                        if not agent_name or not isinstance(events, dict):
                            continue
                        for event_id in events:
                            owner = self._event_to_agent.get(event_id)
                            if owner and owner != agent_name:
                                conflicts.append(
                                    f"canonical event '{event_id}' maps to '{agent_name}' "
                                    f"but agent YAML claims '{owner}'"
                                )
                            self._event_to_agent[event_id] = agent_name
                except Exception as e:
                    conflicts.append(f"canonical space registry parse error: {e}")

            self._stats = {
                "agents_loaded": len(self._agents),
                "events_total": len(self._event_to_agent),
                "conflicts": conflicts,
                "last_reload_ts": time.time(),
            }
            self._last_load_ts = time.time()
            return dict(self._stats)

    def reload_if_changed(self) -> bool:
        """Cheap mtime check; only reloads if any YAML file changed."""
        with self._lock:
            for fp in self.dir.glob("*.yaml"):
                if fp.stat().st_mtime > self._mtime_cache.get(fp, 0):
                    logger.info(f"[agent_yaml] {fp.name} changed, reloading")
                    self.reload()
                    return True
            # New files
            current = set(self.dir.glob("*.yaml")) | set(self.dir.glob("*.yml"))
            if current - set(self._mtime_cache.keys()):
                self.reload()
                return True
            return False

    def get_event_agent(self, event_id: str) -> Optional[str]:
        with self._lock:
            return self._event_to_agent.get(event_id)

    def get_agent_events(self, agent_name: str) -> List[str]:
        with self._lock:
            a = self._agents.get(agent_name)
            return list(a["events"]) if a else []

    def list_agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {k: v for k, v in a.items() if not k.startswith("_")}
                for a in self._agents.values()
            ]

    def get_agent(self, agent_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            a = self._agents.get(agent_name)
            if not a:
                return None
            return {k: v for k, v in a.items() if not k.startswith("_")}

    def validate(self) -> List[str]:
        with self._lock:
            return list(self._stats.get("conflicts", []))

    def move_event(
        self, event_id: str, from_agent: str, to_agent: str,
    ) -> Dict[str, Any]:
        """Move event_id from from_agent's YAML to to_agent's YAML.
        If from_agent is empty/None, just adds to to_agent.
        Atomic: writes both YAMLs via tmp+rename.
        """
        with self._lock:
            if to_agent not in self._agents:
                # Auto-create new agent YAML if it doesn't exist yet
                self._agents[to_agent] = {
                    "agent": to_agent,
                    "description": "",
                    "default_namespace": "",
                    "events": [],
                    "fallback_agent": "",
                    "notes": "",
                    "_path": str(self.dir / f"{to_agent}.yaml"),
                    "_mtime": 0,
                }

            if from_agent and from_agent in self._agents:
                from_a = self._agents[from_agent]
                if event_id in from_a["events"]:
                    from_a["events"] = [e for e in from_a["events"] if e != event_id]
                    self._persist_agent(from_agent)

            to_a = self._agents[to_agent]
            if event_id not in to_a["events"]:
                to_a["events"].append(event_id)
                self._persist_agent(to_agent)

            # Update event_to_agent map
            if from_agent and self._event_to_agent.get(event_id) == from_agent:
                self._event_to_agent.pop(event_id, None)
            self._event_to_agent[event_id] = to_agent
            return {
                "ok": True,
                "event_id": event_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
            }

    def remove_event(self, event_id: str, from_agent: str) -> Dict[str, Any]:
        with self._lock:
            if from_agent not in self._agents:
                return {"ok": False, "error": f"agent '{from_agent}' not found"}
            a = self._agents[from_agent]
            if event_id not in a["events"]:
                return {"ok": False, "error": f"event not in agent's list"}
            a["events"] = [e for e in a["events"] if e != event_id]
            self._persist_agent(from_agent)
            self._event_to_agent.pop(event_id, None)
            return {"ok": True, "event_id": event_id, "from_agent": from_agent}

    def _persist_agent(self, agent_name: str) -> None:
        """Write the agent's YAML to disk atomically."""
        a = self._agents[agent_name]
        path = Path(a.get("_path") or self.dir / f"{agent_name}.yaml")
        data = {
            "agent": a["agent"],
            "description": a.get("description", ""),
            "default_namespace": a.get("default_namespace", ""),
            "events": list(a.get("events") or []),
            "fallback_agent": a.get("fallback_agent", ""),
            "notes": a.get("notes", ""),
        }
        try:
            _atomic_write_yaml(path, data)
            self._mtime_cache[path] = path.stat().st_mtime
            a["_mtime"] = path.stat().st_mtime
        except Exception as e:
            logger.error(f"[agent_yaml] persist failed for {agent_name}: {e}")

    def stats_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    def auto_seed(
        self,
        namespace_to_agent: Dict[str, str],
        events_by_namespace: Dict[str, List[str]],
        descriptions: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Bootstrap initial YAMLs from a namespace→agent mapping.

        For each (namespace, agent) pair, all events with that namespace
        prefix are added to the agent's YAML. Idempotent: existing claims
        are preserved, only missing events are filled in.

        Args:
            namespace_to_agent: e.g. {"bubble": "brain-bubbles", "idea": "brain-ideas"}
            events_by_namespace: e.g. {"bubble": ["bubble.create", ...], ...}
            descriptions: optional {agent_name: description} overrides
        """
        descriptions = descriptions or {}
        seeded = 0
        with self._lock:
            for ns, agent in namespace_to_agent.items():
                events = events_by_namespace.get(ns, [])
                if not events:
                    continue
                if agent not in self._agents:
                    self._agents[agent] = {
                        "agent": agent,
                        "description": descriptions.get(agent, f"Auto-seeded for {ns}.* events"),
                        "default_namespace": ns,
                        "events": [],
                        "fallback_agent": "",
                        "notes": f"Auto-seeded from namespace='{ns}'.",
                        "_path": str(self.dir / f"{agent}.yaml"),
                        "_mtime": 0,
                    }
                a = self._agents[agent]
                if not a.get("default_namespace"):
                    a["default_namespace"] = ns
                existing = set(a.get("events") or [])
                new_events = [e for e in events if e not in existing]
                if new_events:
                    # Filter out events already claimed by other agents
                    truly_new = [e for e in new_events
                                 if e not in self._event_to_agent]
                    a["events"] = sorted(list(existing | set(truly_new)))
                    for e in truly_new:
                        self._event_to_agent[e] = agent
                    seeded += len(truly_new)
                    self._persist_agent(agent)
            return {
                "ok": True,
                "events_seeded": seeded,
                "agents": list(namespace_to_agent.values()),
            }


# ──────────────────────────────────────────────────────────────────────
# Singleton accessor
# ──────────────────────────────────────────────────────────────────────

_INSTANCE: Optional[AgentYamlRegistry] = None
_INSTANCE_LOCK = threading.Lock()


def get_registry() -> AgentYamlRegistry:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = AgentYamlRegistry()
        return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None

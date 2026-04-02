"""Agent Version Controller – manages versioned agent configurations.

Tracks version history, allows rollback to previous versions, and
supports branching for experimental agent configurations.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Version:
    version_id: str
    agent: str
    version_num: int
    config: Dict[str, Any]
    message: str
    parent_version: str
    branch: str
    tags: List[str]
    created_at: float


@dataclass
class _VersionEvent:
    event_id: str
    agent: str
    action: str
    version_num: int
    timestamp: float


class AgentVersionController:
    """Manages versioned agent configurations."""

    def __init__(self, max_agents: int = 10000, max_versions_per_agent: int = 1000, max_history: int = 100000):
        self._versions: Dict[str, List[_Version]] = {}  # agent -> [versions]
        self._current: Dict[str, int] = {}  # agent -> current version index
        self._branches: Dict[str, Dict[str, int]] = {}  # agent -> {branch: version_index}
        self._history: List[_VersionEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_agents = max_agents
        self._max_versions = max_versions_per_agent
        self._max_history = max_history
        self._seq = 0
        self._total_commits = 0
        self._total_rollbacks = 0

    def init_agent(self, agent: str, config: Dict[str, Any], message: str = "initial", tags: Optional[List[str]] = None) -> str:
        if not agent or agent in self._versions:
            return ""
        if len(self._versions) >= self._max_agents:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{agent}-0-{now}-{self._seq}"
        vid = "ver-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        v = _Version(version_id=vid, agent=agent, version_num=1, config=dict(config), message=message, parent_version="", branch="main", tags=tags or [], created_at=now)
        self._versions[agent] = [v]
        self._current[agent] = 0
        self._branches[agent] = {"main": 0}
        self._total_commits += 1
        self._record_event(agent, "initialized", 1)
        self._fire("agent_initialized", {"agent": agent, "version": 1})
        return vid

    def commit(self, agent: str, config: Dict[str, Any], message: str = "", branch: str = "main") -> str:
        if agent not in self._versions:
            return ""
        versions = self._versions[agent]
        if len(versions) >= self._max_versions:
            return ""
        self._seq += 1
        now = time.time()
        vnum = len(versions) + 1
        parent = versions[self._current[agent]].version_id
        raw = f"{agent}-{vnum}-{now}-{self._seq}"
        vid = "ver-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        v = _Version(version_id=vid, agent=agent, version_num=vnum, config=dict(config), message=message, parent_version=parent, branch=branch, tags=[], created_at=now)
        versions.append(v)
        idx = len(versions) - 1
        self._current[agent] = idx
        self._branches[agent][branch] = idx
        self._total_commits += 1
        self._record_event(agent, "committed", vnum)
        self._fire("version_committed", {"agent": agent, "version": vnum, "branch": branch})
        return vid

    def get_current(self, agent: str) -> Optional[Dict[str, Any]]:
        if agent not in self._versions:
            return None
        v = self._versions[agent][self._current[agent]]
        return self._version_to_dict(v)

    def get_version(self, agent: str, version_num: int) -> Optional[Dict[str, Any]]:
        if agent not in self._versions:
            return None
        versions = self._versions[agent]
        if version_num < 1 or version_num > len(versions):
            return None
        return self._version_to_dict(versions[version_num - 1])

    def rollback(self, agent: str, version_num: int) -> bool:
        if agent not in self._versions:
            return False
        versions = self._versions[agent]
        if version_num < 1 or version_num > len(versions):
            return False
        self._current[agent] = version_num - 1
        self._total_rollbacks += 1
        self._record_event(agent, "rolled_back", version_num)
        self._fire("version_rolled_back", {"agent": agent, "version": version_num})
        return True

    def get_log(self, agent: str, limit: int = 50) -> List[Dict[str, Any]]:
        if agent not in self._versions:
            return []
        versions = self._versions[agent]
        results = []
        for v in reversed(versions):
            results.append(self._version_to_dict(v))
            if len(results) >= limit:
                break
        return results

    def diff(self, agent: str, v1: int, v2: int) -> Dict[str, Any]:
        ver1 = self.get_version(agent, v1)
        ver2 = self.get_version(agent, v2)
        if not ver1 or not ver2:
            return {"error": "version_not_found"}
        c1, c2 = ver1["config"], ver2["config"]
        added = {k: c2[k] for k in c2 if k not in c1}
        removed = {k: c1[k] for k in c1 if k not in c2}
        changed = {k: {"old": c1[k], "new": c2[k]} for k in c1 if k in c2 and c1[k] != c2[k]}
        return {"added": added, "removed": removed, "changed": changed}

    def create_branch(self, agent: str, branch_name: str) -> bool:
        if agent not in self._versions or not branch_name:
            return False
        if branch_name in self._branches.get(agent, {}):
            return False
        self._branches[agent][branch_name] = self._current[agent]
        return True

    def switch_branch(self, agent: str, branch_name: str) -> bool:
        if agent not in self._versions:
            return False
        branches = self._branches.get(agent, {})
        if branch_name not in branches:
            return False
        self._current[agent] = branches[branch_name]
        return True

    def list_branches(self, agent: str) -> List[str]:
        return sorted(self._branches.get(agent, {}).keys())

    def list_agents(self) -> List[str]:
        return sorted(self._versions.keys())

    def _version_to_dict(self, v: _Version) -> Dict[str, Any]:
        return {"version_id": v.version_id, "agent": v.agent, "version_num": v.version_num, "config": dict(v.config), "message": v.message, "parent_version": v.parent_version, "branch": v.branch, "tags": list(v.tags), "created_at": v.created_at}

    def get_history(self, agent: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if agent and ev.agent != agent:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "agent": ev.agent, "action": ev.action, "version_num": ev.version_num, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, agent: str, action: str, version_num: int) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{agent}-{action}-{version_num}-{now}-{self._seq}"
        evid = "vev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _VersionEvent(event_id=evid, agent=agent, action=action, version_num=version_num, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        total_versions = sum(len(v) for v in self._versions.values())
        return {"current_agents": len(self._versions), "total_versions": total_versions, "total_commits": self._total_commits, "total_rollbacks": self._total_rollbacks, "history_size": len(self._history)}

    def reset(self) -> None:
        self._versions.clear()
        self._current.clear()
        self._branches.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_commits = 0
        self._total_rollbacks = 0

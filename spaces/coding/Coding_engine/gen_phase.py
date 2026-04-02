"""Generate source + test files for a batch of modules."""
import os

MODULES = [
    ("pipeline_data_translator_v2", "PipelineDataTranslatorV2", "PipelineDataTranslatorV2State", "pdtrv-", "translate_v2", "pipeline_id", "data_key", "lang", "en", "get_translation", "get_translations", "get_translation_count", "total_translations", "unique_pipelines", "pipeline_id", "str"),
    ("agent_workflow_balancer_v2", "AgentWorkflowBalancerV2", "AgentWorkflowBalancerV2State", "awblv-", "balance_v2", "agent_id", "workflow_name", "strategy", "round_robin", "get_balance", "get_balances", "get_balance_count", "total_balances", "unique_agents", "agent_id", "str"),
    ("pipeline_step_versioner_v2", "PipelineStepVersionerV2", "PipelineStepVersionerV2State", "psvnv-", "version_step_v2", "pipeline_id", "step_name", "tag", "v1", "get_step_version", "get_step_versions", "get_step_version_count", "total_step_versions", "unique_pipelines", "pipeline_id", "str"),
    ("agent_task_collector_v2", "AgentTaskCollectorV2", "AgentTaskCollectorV2State", "atclv-", "collect_task_v2", "task_id", "agent_id", "scope", "local", "get_task_collection", "get_task_collections", "get_task_collection_count", "total_task_collections", "unique_agents", "agent_id", "str"),
]

SRC = '''import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class {state}:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)

class {cls}:
    PREFIX = "{prefix}"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = {state}()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{{self.PREFIX}}{{self._state._seq}}-{{id(self)}}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(self._state.entries, key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k]["_seq"]))
        remove_count = len(sorted_keys) // 4
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data = {{"action": action, **detail}}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    def {method}(self, {p1}: str, {p2}: str, {p3}: {p3ann} = {p3defval}, metadata: Optional[dict] = None) -> str:
        if not {p1} or not {p2}:
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry = {{
            "record_id": record_id,
            "{p1}": {p1},
            "{p2}": {p2},
            "{p3}": {p3},
            "metadata": copy.deepcopy(metadata) if metadata else {{}},
            "created_at": now,
            "_seq": self._state._seq,
        }}
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("{method}", {p1}={p1}, record_id=record_id)
        return record_id

    def {get1}(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def {getl}(self, {filtby}: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if {filtby}:
            entries = [e for e in entries if e["{filtby}"] == {filtby}]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def {getc}(self, {filtby}: str = "") -> int:
        if not {filtby}:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["{filtby}"] == {filtby})

    def get_stats(self) -> dict:
        entries = list(self._state.entries.values())
        unique = set(e["{filtby}"] for e in entries)
        return {{"{statk}": len(entries), "{statk2}": len(unique)}}

    def reset(self) -> None:
        self._state = {state}()
        self._on_change = None
'''

TEST = '''import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.{mod} import {cls}

class TestBasic:
    def test_returns_id(self):
        s = {cls}()
        rid = s.{method}("v1", "v2")
        assert rid.startswith("{prefix}")
    def test_fields(self):
        s = {cls}()
        rid = s.{method}("v1", "v2", metadata={{"k": "v"}})
        e = s.{get1}(rid)
        assert e["{p1}"] == "v1"
        assert e["{p2}"] == "v2"
        assert e["metadata"] == {{"k": "v"}}
    def test_default_param(self):
        s = {cls}()
        rid = s.{method}("v1", "v2")
        {da}
    def test_metadata_deepcopy(self):
        s = {cls}()
        m = {{"x": [1]}}
        rid = s.{method}("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.{get1}(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = {cls}()
        assert s.{method}("", "v2") == ""
    def test_empty_p2(self):
        s = {cls}()
        assert s.{method}("v1", "") == ""
class TestGet:
    def test_found(self):
        s = {cls}()
        rid = s.{method}("v1", "v2")
        assert s.{get1}(rid) is not None
    def test_not_found(self):
        s = {cls}()
        assert s.{get1}("nope") is None
    def test_copy(self):
        s = {cls}()
        rid = s.{method}("v1", "v2")
        assert s.{get1}(rid) is not s.{get1}(rid)
class TestList:
    def test_all(self):
        s = {cls}()
        s.{method}("v1", "v2")
        s.{method}("v3", "v4")
        assert len(s.{getl}()) == 2
    def test_filter(self):
        s = {cls}()
        s.{method}("v1", "v2")
        s.{method}("v3", "v4")
        assert len(s.{getl}({filtby}="{fv}")) == 1
    def test_newest_first(self):
        s = {cls}()
        s.{method}("{n1p1}", "{n1p2}")
        s.{method}("{n2p1}", "{n2p2}")
        items = s.{getl}({filtby}="{fn}")
        assert items[0]["_seq"] > items[-1]["_seq"]
class TestCount:
    def test_total(self):
        s = {cls}()
        s.{method}("v1", "v2")
        s.{method}("v3", "v4")
        assert s.{getc}() == 2
    def test_filtered(self):
        s = {cls}()
        s.{method}("v1", "v2")
        s.{method}("v3", "v4")
        assert s.{getc}("{cfv}") == 1
class TestStats:
    def test_data(self):
        s = {cls}()
        s.{method}("v1", "v2")
        assert s.get_stats()["{statk}"] == 1
class TestCallbacks:
    def test_on_change(self):
        s = {cls}()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.{method}("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = {cls}()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = {cls}()
        assert s.remove_callback("nope") is False
class TestPrune:
    def test_prune(self):
        s = {cls}()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.{method}(f"p{{i}}", f"v{{i}}")
        assert s.{getc}() <= 6
class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = {cls}()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.{method}("t1", "a1")
        assert captured[0]["action"] == "{method}"
        assert captured[0]["record_id"].startswith("{prefix}")
class TestReset:
    def test_clears(self):
        s = {cls}()
        s.on_change = lambda a, d: None
        s.{method}("v1", "v2")
        s.reset()
        assert s.{getc}() == 0
        assert s.on_change is None
    def test_seq(self):
        s = {cls}()
        s.{method}("v1", "v2")
        s.reset()
        assert s._state._seq == 0
'''

for m in MODULES:
    mod, cls, state, prefix, method, p1, p2, p3, p3def, get1, getl, getc, statk, statk2, filtby, p3type = m
    p3ann = p3type
    p3defval = p3def if p3type == "int" else f'"{p3def}"'
    d = dict(locals())
    with open(f"src/services/{mod}.py", "w") as f:
        f.write(SRC.format(**d))

    da = f'assert s.{get1}(rid)["{p3}"] == {p3def}' if p3type == "int" else f'assert s.{get1}(rid)["{p3}"] == "{p3def}"'
    if filtby == "agent_id" and p1 == "task_id":
        fv, n1p1, n1p2, n2p1, n2p2, cfv, fn = "v2", "t1", "a1", "t2", "a1", "v2", "a1"
    elif filtby == "agent_id":
        fv, n1p1, n1p2, n2p1, n2p2, cfv, fn = "v1", "v1", "w1", "v1", "w2", "v1", "v1"
    else:
        fv, n1p1, n1p2, n2p1, n2p2, cfv, fn = "v1", "v1", "w1", "v1", "w2", "v1", "v1"
    d.update(locals())
    with open(f"tests/test_{mod}.py", "w") as f:
        f.write(TEST.format(**d))
    print(f"Created {mod}")

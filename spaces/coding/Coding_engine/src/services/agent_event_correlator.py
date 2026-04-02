"""Agent Event Correlator - Correlate events across agents to find patterns and relationships."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentEventCorrelatorState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentEventCorrelator:
    """Correlate events across agents to find patterns and relationships."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "aec2-"

    def __init__(self):
        self._state = AgentEventCorrelatorState()
        self._callbacks: dict = {}
        self._events: list = []
        self._rules: dict = {}
        logger.info("AgentEventCorrelator initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        if len(self._events) > self.MAX_ENTRIES:
            excess = len(self._events) - self.MAX_ENTRIES
            self._events = self._events[excess:]
            logger.info("Pruned %d events", excess)

    def on_change(self, callback_id: str, callback):
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event_name: str, data=None):
        for cb in self._callbacks.values():
            try:
                cb(event_name, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def add_event(self, agent_id: str, event_type: str, timestamp=None, payload=None) -> str:
        if timestamp is None:
            timestamp = time.time()
        event_id = self._generate_id(f"{agent_id}{event_type}{timestamp}")
        event = {
            "event_id": event_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "payload": payload,
        }
        self._events.append(event)
        self._state.entries[event_id] = event
        self._prune()
        self._fire("event_added", event)
        logger.debug("Added event %s for agent %s", event_id, agent_id)
        return event_id

    def create_rule(self, rule_name: str, event_types: list, time_window_seconds: float = 60.0) -> str:
        rule_id = self._generate_id(f"rule:{rule_name}")
        rule = {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "event_types": list(event_types),
            "time_window_seconds": time_window_seconds,
        }
        self._rules[rule_id] = rule
        self._fire("rule_created", rule)
        logger.debug("Created rule %s: %s", rule_id, rule_name)
        return rule_id

    def find_correlations(self, rule_id: str) -> list:
        rule = self._rules.get(rule_id)
        if rule is None:
            return []
        event_types = rule["event_types"]
        window = rule["time_window_seconds"]
        if not event_types:
            return []

        # Group events by type
        by_type: dict = {}
        for ev in self._events:
            et = ev["event_type"]
            if et in event_types:
                by_type.setdefault(et, []).append(ev)

        # All required types must be present
        for et in event_types:
            if et not in by_type:
                return []

        # Find correlations: for each event of the first type, find co-occurring events
        correlations = []
        anchor_type = event_types[0]
        other_types = event_types[1:]

        for anchor in by_type[anchor_type]:
            t0 = anchor["timestamp"]
            matched_events = [anchor]
            all_matched = True
            for ot in other_types:
                found = None
                for candidate in by_type[ot]:
                    if abs(candidate["timestamp"] - t0) <= window:
                        found = candidate
                        break
                if found is None:
                    all_matched = False
                    break
                matched_events.append(found)
            if all_matched:
                correlations.append({
                    "events": matched_events,
                    "rule_id": rule_id,
                    "timestamp": t0,
                })

        return correlations

    def get_events(self, agent_id: str = "", event_type: str = "") -> list:
        result = self._events
        if agent_id:
            result = [e for e in result if e["agent_id"] == agent_id]
        if event_type:
            result = [e for e in result if e["event_type"] == event_type]
        return list(result)

    def get_rule(self, rule_id: str):
        return self._rules.get(rule_id)

    def get_rules(self) -> list:
        return list(self._rules.values())

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._fire("rule_removed", {"rule_id": rule_id})
            return True
        return False

    def get_event_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(1 for e in self._events if e["agent_id"] == agent_id)
        return len(self._events)

    def list_agents(self) -> list:
        agents = set()
        for e in self._events:
            agents.add(e["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        return {
            "total_events": len(self._events),
            "total_rules": len(self._rules),
            "agents": self.list_agents(),
            "seq": self._state._seq,
        }

    def reset(self):
        self._state = AgentEventCorrelatorState()
        self._events.clear()
        self._rules.clear()
        self._callbacks.clear()
        self._fire("reset", None)
        logger.info("AgentEventCorrelator reset")

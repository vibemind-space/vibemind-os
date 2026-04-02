"""Pipeline step audit trail for tracking pipeline step executions."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepAuditState:
    """State container for pipeline step audit entries."""
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepAudit:
    """Audit trail for pipeline step executions with who/what/when/result."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "psa2-"

    def __init__(self):
        self._state = PipelineStepAuditState()
        self._callbacks = {}
        logger.info("PipelineStepAudit initialized")

    def _generate_id(self, data: str) -> str:
        """Generate a unique audit ID using sha256."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_part = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_part}"

    def _prune(self):
        """Prune entries if exceeding MAX_ENTRIES, removing oldest first."""
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("timestamp", 0)
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]
            logger.debug("Pruned %d audit entries", to_remove)

    def on_change(self, callback_id: str, callback) -> None:
        """Register a change callback."""
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a registered callback. Returns True if it existed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event: str, data: dict) -> None:
        """Fire all registered callbacks."""
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback %s failed: %s", cb_id, e)

    def log_execution(
        self,
        pipeline_id: str,
        step_name: str,
        executor: str = "system",
        input_summary: str = "",
        output_summary: str = "",
        status: str = "success",
    ) -> str:
        """Log a pipeline step execution and return the audit ID."""
        audit_id = self._generate_id(f"{pipeline_id}:{step_name}:{time.time()}")
        entry = {
            "audit_id": audit_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "executor": executor,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "status": status,
            "timestamp": time.time(),
        }
        self._state.entries[audit_id] = entry
        self._prune()
        self._fire("execution_logged", entry)
        logger.info("Logged execution %s for pipeline %s step %s", audit_id, pipeline_id, step_name)
        return audit_id

    def get_audit_trail(self, pipeline_id: str, step_name: str = "", limit: int = 50) -> list:
        """Get audit trail for a pipeline, optionally filtered by step name."""
        results = [
            e for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
            and (not step_name or e["step_name"] == step_name)
        ]
        results.sort(key=lambda e: e["timestamp"], reverse=True)
        return results[:limit]

    def get_audit_entry(self, audit_id: str) -> dict | None:
        """Get a single audit entry by ID."""
        return self._state.entries.get(audit_id)

    def get_audit_summary(self, pipeline_id: str) -> dict:
        """Get summary statistics for a pipeline's audit trail."""
        entries = [e for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id]
        success_count = sum(1 for e in entries if e["status"] == "success")
        failure_count = sum(1 for e in entries if e["status"] != "success")
        unique_steps = set(e["step_name"] for e in entries)
        unique_executors = set(e["executor"] for e in entries)
        return {
            "total_executions": len(entries),
            "success_count": success_count,
            "failure_count": failure_count,
            "unique_steps": len(unique_steps),
            "unique_executors": len(unique_executors),
        }

    def clear_audit(self, pipeline_id: str) -> int:
        """Clear all audit entries for a pipeline. Returns count cleared."""
        to_remove = [k for k, v in self._state.entries.items() if v["pipeline_id"] == pipeline_id]
        for k in to_remove:
            del self._state.entries[k]
        if to_remove:
            self._fire("audit_cleared", {"pipeline_id": pipeline_id, "count": len(to_remove)})
        logger.info("Cleared %d audit entries for pipeline %s", len(to_remove), pipeline_id)
        return len(to_remove)

    def get_audit_count(self, pipeline_id: str = "") -> int:
        """Get count of audit entries, optionally filtered by pipeline ID."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def list_pipelines(self) -> list:
        """List all pipeline IDs that have audit entries."""
        return sorted(set(e["pipeline_id"] for e in self._state.entries.values()))

    def get_stats(self) -> dict:
        """Get overall statistics."""
        return {
            "total_entries": len(self._state.entries),
            "total_pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineStepAuditState()
        self._callbacks.clear()
        logger.info("PipelineStepAudit reset")

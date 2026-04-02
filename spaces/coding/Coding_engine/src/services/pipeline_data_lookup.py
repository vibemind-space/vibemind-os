import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class PipelineDataLookupState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataLookup:
    """Create and query lookup tables for pipeline data enrichment."""

    def __init__(self):
        self._state = PipelineDataLookupState()
        self._callbacks: dict = {}
        logger.info("PipelineDataLookup initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "pdl-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Callback system ──────────────────────────────────────────

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        return self._callbacks.pop(cb_id, None) is not None

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    # ── Pruning ──────────────────────────────────────────────────

    def _prune(self):
        entries = self._state.entries
        if len(entries) <= MAX_ENTRIES:
            return
        sorted_keys = sorted(entries, key=lambda k: entries[k].get("_created", 0))
        to_remove = len(entries) - MAX_ENTRIES
        for key in sorted_keys[:to_remove]:
            del entries[key]
        logger.info("Pruned %d entries", to_remove)

    # ── API ──────────────────────────────────────────────────────

    def create_table(self, pipeline_id: str, table_name: str, key_field: str) -> str:
        table_id = self._generate_id(f"{pipeline_id}:{table_name}")
        self._state.entries[table_id] = {
            "type": "table",
            "pipeline_id": pipeline_id,
            "table_name": table_name,
            "key_field": key_field,
            "records": {},
            "_created": time.time(),
        }
        self._prune()
        self._fire("table_created", {"table_id": table_id, "pipeline_id": pipeline_id})
        logger.info("Created table %s for pipeline %s", table_id, pipeline_id)
        return table_id

    def load_data(self, table_id: str, records: list) -> int:
        table = self._state.entries.get(table_id)
        if table is None or table.get("type") != "table":
            raise ValueError(f"Table not found: {table_id}")
        key_field = table["key_field"]
        count = 0
        for record in records:
            key = record.get(key_field)
            if key is not None:
                table["records"][key] = record
                count += 1
        self._fire("data_loaded", {"table_id": table_id, "count": count})
        logger.info("Loaded %d records into table %s", count, table_id)
        return count

    def lookup(self, table_id: str, key) -> dict | None:
        table = self._state.entries.get(table_id)
        if table is None or table.get("type") != "table":
            return None
        return table["records"].get(key)

    def lookup_many(self, table_id: str, keys: list) -> list:
        table = self._state.entries.get(table_id)
        if table is None or table.get("type") != "table":
            return [None] * len(keys)
        records = table["records"]
        return [records.get(k) for k in keys]

    def get_table(self, table_id: str) -> dict | None:
        entry = self._state.entries.get(table_id)
        if entry is None or entry.get("type") != "table":
            return None
        return {
            "table_id": table_id,
            "pipeline_id": entry["pipeline_id"],
            "table_name": entry["table_name"],
            "key_field": entry["key_field"],
            "size": len(entry["records"]),
        }

    def get_tables(self, pipeline_id: str) -> list:
        results = []
        for tid, entry in self._state.entries.items():
            if entry.get("type") == "table" and entry["pipeline_id"] == pipeline_id:
                results.append({
                    "table_id": tid,
                    "pipeline_id": entry["pipeline_id"],
                    "table_name": entry["table_name"],
                    "key_field": entry["key_field"],
                    "size": len(entry["records"]),
                })
        return results

    def get_table_size(self, table_id: str) -> int:
        table = self._state.entries.get(table_id)
        if table is None or table.get("type") != "table":
            return 0
        return len(table["records"])

    def get_table_count(self, pipeline_id: str = "") -> int:
        count = 0
        for entry in self._state.entries.values():
            if entry.get("type") != "table":
                continue
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            count += 1
        return count

    def list_pipelines(self) -> list:
        pipeline_ids = set()
        for entry in self._state.entries.values():
            if entry.get("type") == "table":
                pipeline_ids.add(entry["pipeline_id"])
        return sorted(pipeline_ids)

    # ── Stats / Reset ────────────────────────────────────────────

    def get_stats(self) -> dict:
        total_tables = 0
        total_records = 0
        pipelines = set()
        for entry in self._state.entries.values():
            if entry.get("type") == "table":
                total_tables += 1
                total_records += len(entry["records"])
                pipelines.add(entry["pipeline_id"])
        return {
            "total_tables": total_tables,
            "total_records": total_records,
            "total_pipelines": len(pipelines),
            "total_entries": len(self._state.entries),
            "callbacks": len(self._callbacks),
            "seq": self._state._seq,
        }

    def reset(self):
        self._state = PipelineDataLookupState()
        self._callbacks.clear()
        logger.info("PipelineDataLookup reset")

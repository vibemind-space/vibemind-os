"""Define and validate data schemas for pipeline records."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

VALID_TYPES = {"str", "int", "float", "bool", "list", "dict"}
TYPE_MAP = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


@dataclasses.dataclass
class PipelineDataSchemaState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataSchema:
    """Define and validate data schemas for pipeline records."""

    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataSchemaState()
        self._callbacks: dict = {}
        self._created_at = time.time()
        logger.info("PipelineDataSchema initialized")

    # ---- ID generation ----

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pdsc-{hash_val}"

    # ---- Callbacks ----

    def on_change(self, name: str, callback) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, event: str, data: dict) -> None:
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback %s error: %s", cb_name, e)

    # ---- Pruning ----

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", to_remove)

    # ---- API ----

    def define_schema(self, pipeline_id: str, fields: dict) -> str:
        """Define a schema for a pipeline. Returns schema_id."""
        schema_id = self._generate_id(pipeline_id)
        entry = {
            "schema_id": schema_id,
            "pipeline_id": pipeline_id,
            "fields": fields,
            "created_at": time.time(),
        }
        self._state.entries[schema_id] = entry
        self._prune()
        self._fire("schema_defined", entry)
        logger.info("Defined schema %s for pipeline %s", schema_id, pipeline_id)
        return schema_id

    def validate_record(self, pipeline_id: str, record: dict) -> dict:
        """Validate a record against the schema for a pipeline."""
        schema = self.get_schema(pipeline_id)
        if schema is None:
            return {"valid": False, "errors": [f"No schema found for pipeline '{pipeline_id}'"]}

        errors = []
        fields = schema.get("fields", {})

        for field_name, field_def in fields.items():
            required = field_def.get("required", False)
            field_type = field_def.get("type", "str")

            if field_name not in record:
                if required:
                    if "default" not in field_def:
                        errors.append(f"Missing required field '{field_name}'")
                continue

            value = record[field_name]
            if value is not None:
                expected_type = TYPE_MAP.get(field_type)
                if expected_type and not isinstance(value, expected_type):
                    errors.append(
                        f"Field '{field_name}' expected type '{field_type}', "
                        f"got '{type(value).__name__}'"
                    )

        return {"valid": len(errors) == 0, "errors": errors}

    def get_schema(self, pipeline_id: str) -> dict | None:
        """Get schema for a pipeline by pipeline_id."""
        for entry in self._state.entries.values():
            if entry.get("pipeline_id") == pipeline_id:
                return entry
        return None

    def infer_schema(self, pipeline_id: str, records: list) -> dict:
        """Infer a schema from sample records and define it."""
        if not records:
            return self.define_schema(pipeline_id, {}), {}

        field_types: dict = {}
        field_counts: dict = {}
        total = len(records)

        for rec in records:
            for key, value in rec.items():
                vtype = type(value).__name__
                # Map Python types to schema types
                mapped = vtype
                if vtype in ("str",):
                    mapped = "str"
                elif vtype in ("int",):
                    mapped = "int"
                elif vtype in ("float",):
                    mapped = "float"
                elif vtype in ("bool",):
                    mapped = "bool"
                elif vtype in ("list", "tuple"):
                    mapped = "list"
                elif vtype in ("dict",):
                    mapped = "dict"
                else:
                    mapped = "str"

                if key not in field_types:
                    field_types[key] = {}
                field_types[key][mapped] = field_types[key].get(mapped, 0) + 1
                field_counts[key] = field_counts.get(key, 0) + 1

        fields = {}
        for key, types in field_types.items():
            # Pick most common type
            dominant_type = max(types, key=types.get)
            required = field_counts[key] == total
            fields[key] = {
                "type": dominant_type,
                "required": required,
            }

        schema_id = self.define_schema(pipeline_id, fields)
        return schema_id

    def remove_schema(self, schema_id: str) -> bool:
        """Remove a schema by schema_id."""
        if schema_id in self._state.entries:
            entry = self._state.entries.pop(schema_id)
            self._fire("schema_removed", entry)
            logger.info("Removed schema %s", schema_id)
            return True
        return False

    def get_schema_count(self) -> int:
        """Return the number of schemas."""
        return len(self._state.entries)

    def list_pipelines(self) -> list:
        """Return list of pipeline_ids that have schemas."""
        return list({
            entry["pipeline_id"]
            for entry in self._state.entries.values()
            if "pipeline_id" in entry
        })

    # ---- Stats / Reset ----

    def get_stats(self) -> dict:
        return {
            "total_schemas": len(self._state.entries),
            "pipelines": len(self.list_pipelines()),
            "seq": self._state._seq,
            "callbacks": len(self._callbacks),
            "uptime": time.time() - self._created_at,
        }

    def reset(self) -> None:
        self._state = PipelineDataSchemaState()
        self._callbacks.clear()
        self._created_at = time.time()
        logger.info("PipelineDataSchema reset")

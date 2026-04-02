"""Evaluate simple expressions on pipeline data fields (computed columns)."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataExpressionState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataExpression:
    """Evaluate simple expressions on pipeline data fields (computed columns)."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "pde-"

    def __init__(self):
        self._state = PipelineDataExpressionState()
        self._callbacks: dict = {}
        self._created = time.time()

    # ---- ID generation ----

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_part = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_part}"

    # ---- Callbacks ----

    def on_change(self, name: str, callback) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, event: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.warning("Callback error: %s", exc)

    # ---- Pruning ----

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]
            logger.info("Pruned %d entries", to_remove)

    # ---- Core API ----

    def add_expression(
        self,
        pipeline_id: str,
        name: str,
        field_a: str,
        operator: str,
        field_b_or_value,
    ) -> str:
        """Add an expression definition. Returns expression id."""
        valid_ops = {"+", "-", "*", "/", "concat", "upper", "lower"}
        if operator not in valid_ops:
            raise ValueError(f"Invalid operator: {operator}. Must be one of {valid_ops}")

        expr_id = self._generate_id(f"{pipeline_id}{name}{field_a}{operator}{field_b_or_value}")
        entry = {
            "id": expr_id,
            "pipeline_id": pipeline_id,
            "name": name,
            "field_a": field_a,
            "operator": operator,
            "field_b_or_value": field_b_or_value,
            "created_at": time.time(),
        }
        self._state.entries[expr_id] = entry
        self._prune()
        self._fire("add_expression", entry)
        logger.debug("Added expression %s for pipeline %s", expr_id, pipeline_id)
        return expr_id

    def evaluate(self, pipeline_id: str, record: dict) -> dict:
        """Evaluate all expressions for a pipeline against a record, returning enriched copy."""
        result = dict(record)
        expressions = self.get_expressions(pipeline_id)
        for expr in expressions:
            op = expr["operator"]
            field_a = expr["field_a"]
            name = expr["name"]
            field_b_or_value = expr["field_b_or_value"]

            a_val = result.get(field_a)

            try:
                if op == "upper":
                    result[name] = str(a_val).upper() if a_val is not None else ""
                elif op == "lower":
                    result[name] = str(a_val).lower() if a_val is not None else ""
                elif op == "concat":
                    b_val = result.get(field_b_or_value, field_b_or_value)
                    a_str = str(a_val) if a_val is not None else ""
                    b_str = str(b_val) if b_val is not None else ""
                    result[name] = a_str + b_str
                elif op in ("+", "-", "*", "/"):
                    # field_b_or_value can be a field name or a numeric value
                    if isinstance(field_b_or_value, (int, float)):
                        b_val = field_b_or_value
                    else:
                        b_val = result.get(field_b_or_value, field_b_or_value)
                        if isinstance(b_val, str):
                            try:
                                b_val = float(b_val)
                            except (ValueError, TypeError):
                                b_val = 0

                    a_num = float(a_val) if a_val is not None else 0
                    if op == "+":
                        result[name] = a_num + b_val
                    elif op == "-":
                        result[name] = a_num - b_val
                    elif op == "*":
                        result[name] = a_num * b_val
                    elif op == "/":
                        result[name] = a_num / b_val if b_val != 0 else 0
            except Exception as exc:
                logger.warning("Expression %s eval error: %s", expr["id"], exc)
                result[name] = None

        return result

    def evaluate_many(self, pipeline_id: str, records: list) -> list:
        """Evaluate expressions against multiple records."""
        return [self.evaluate(pipeline_id, r) for r in records]

    def get_expressions(self, pipeline_id: str) -> list:
        """Get all expressions for a pipeline."""
        return [
            e for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        ]

    def remove_expression(self, expr_id: str) -> bool:
        """Remove an expression by id."""
        if expr_id in self._state.entries:
            entry = self._state.entries.pop(expr_id)
            self._fire("remove_expression", entry)
            return True
        return False

    def get_expression_count(self, pipeline_id: str = "") -> int:
        """Get count of expressions, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def list_pipelines(self) -> list:
        """List distinct pipeline ids."""
        return list({e["pipeline_id"] for e in self._state.entries.values()})

    # ---- Stats / Reset ----

    def get_stats(self) -> dict:
        return {
            "total_expressions": len(self._state.entries),
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
            "seq": self._state._seq,
            "uptime": time.time() - self._created,
        }

    def reset(self) -> None:
        self._state = PipelineDataExpressionState()
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("PipelineDataExpression reset")

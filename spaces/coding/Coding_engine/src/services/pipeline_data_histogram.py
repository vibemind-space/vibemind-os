"""Pipeline data histogram service for building histograms from numeric pipeline data fields."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class PipelineDataHistogramState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataHistogram:
    """Build histograms from numeric pipeline data fields."""

    def __init__(self):
        self.state = PipelineDataHistogramState()
        self.callbacks = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self.state._seq}"
        self.state._seq += 1
        return "pdh-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _fire(self, event: str, data: dict):
        for cb in list(self.callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self.callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self.callbacks:
            del self.callbacks[cb_id]
            return True
        return False

    def _prune(self):
        if len(self.state.entries) > MAX_ENTRIES:
            sorted_keys = sorted(
                self.state.entries.keys(),
                key=lambda k: self.state.entries[k].get("created_at", 0),
            )
            while len(self.state.entries) > MAX_ENTRIES:
                removed_key = sorted_keys.pop(0)
                del self.state.entries[removed_key]
            logger.info("Pruned entries to %d", len(self.state.entries))

    def create_histogram(
        self,
        pipeline_id: str,
        field: str,
        bin_count: int = 10,
        min_val: float = 0.0,
        max_val: float = 100.0,
    ) -> str:
        histogram_id = self._generate_id(f"{pipeline_id}-{field}")
        bin_width = (max_val - min_val) / bin_count
        bins = []
        for i in range(bin_count):
            low = min_val + i * bin_width
            high = min_val + (i + 1) * bin_width
            bins.append({"low": low, "high": high, "count": 0})

        entry = {
            "histogram_id": histogram_id,
            "pipeline_id": pipeline_id,
            "field": field,
            "bin_count": bin_count,
            "min_val": min_val,
            "max_val": max_val,
            "bins": bins,
            "total": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.state.entries[histogram_id] = entry
        self._prune()
        self._fire("histogram_created", {"histogram_id": histogram_id})
        logger.info("Created histogram %s for pipeline %s field %s", histogram_id, pipeline_id, field)
        return histogram_id

    def add_values(self, histogram_id: str, values: list) -> bool:
        if histogram_id not in self.state.entries:
            logger.warning("Histogram %s not found", histogram_id)
            return False
        entry = self.state.entries[histogram_id]
        bins = entry["bins"]
        min_val = entry["min_val"]
        max_val = entry["max_val"]
        for v in values:
            if v < min_val or v > max_val:
                continue
            for b in bins:
                if b["low"] <= v < b["high"]:
                    b["count"] += 1
                    entry["total"] += 1
                    break
            else:
                # Handle value equal to max_val: put in last bin
                if v == max_val and bins:
                    bins[-1]["count"] += 1
                    entry["total"] += 1
        entry["updated_at"] = time.time()
        self._fire("values_added", {"histogram_id": histogram_id, "count": len(values)})
        return True

    def get_histogram(self, histogram_id: str) -> dict:
        if histogram_id not in self.state.entries:
            return {}
        entry = self.state.entries[histogram_id]
        return {
            "histogram_id": entry["histogram_id"],
            "bins": [{"low": b["low"], "high": b["high"], "count": b["count"]} for b in entry["bins"]],
            "total": entry["total"],
        }

    def get_percentile(self, histogram_id: str, percentile: float) -> float:
        if histogram_id not in self.state.entries:
            return 0.0
        entry = self.state.entries[histogram_id]
        if entry["total"] == 0:
            return 0.0
        target = (percentile / 100.0) * entry["total"]
        cumulative = 0
        for b in entry["bins"]:
            cumulative += b["count"]
            if cumulative >= target:
                # Linear interpolation within bin
                overshoot = cumulative - target
                fraction = 1.0 - (overshoot / b["count"]) if b["count"] > 0 else 0.0
                return b["low"] + fraction * (b["high"] - b["low"])
        # Fallback to max
        return entry["max_val"]

    def get_histograms(self, pipeline_id: str) -> list:
        result = []
        for entry in self.state.entries.values():
            if entry.get("pipeline_id") == pipeline_id:
                result.append({
                    "histogram_id": entry["histogram_id"],
                    "bins": [{"low": b["low"], "high": b["high"], "count": b["count"]} for b in entry["bins"]],
                    "total": entry["total"],
                })
        return result

    def remove_histogram(self, histogram_id: str) -> bool:
        if histogram_id in self.state.entries:
            del self.state.entries[histogram_id]
            self._fire("histogram_removed", {"histogram_id": histogram_id})
            logger.info("Removed histogram %s", histogram_id)
            return True
        return False

    def get_histogram_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self.state.entries)
        return sum(1 for e in self.state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def list_pipelines(self) -> list:
        pipelines = set()
        for entry in self.state.entries.values():
            pid = entry.get("pipeline_id")
            if pid:
                pipelines.add(pid)
        return sorted(pipelines)

    def get_stats(self) -> dict:
        return {
            "total_histograms": len(self.state.entries),
            "total_callbacks": len(self.callbacks),
            "seq": self.state._seq,
            "pipelines": len(self.list_pipelines()),
        }

    def reset(self):
        self.state.entries.clear()
        self.callbacks.clear()
        self.state._seq = 0
        logger.info("Reset pipeline data histogram")

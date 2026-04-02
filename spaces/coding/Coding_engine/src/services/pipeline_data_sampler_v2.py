"""Advanced data sampling with reservoir sampling and stratified sampling."""

import time
import hashlib
import dataclasses
import logging
import random

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class PipelineDataSamplerV2State:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataSamplerV2:
    """Advanced data sampling with reservoir sampling and stratified sampling."""

    def __init__(self):
        self._state = PipelineDataSamplerV2State()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "pds2-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        while len(self._state.entries) > MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]

    # -- Callback machinery --

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    # -- Core API --

    def create_sampler(self, pipeline_id: str, strategy: str = "reservoir", sample_size: int = 100) -> str:
        if strategy not in ("reservoir", "stratified", "systematic"):
            raise ValueError(f"Unknown strategy: {strategy}")
        sampler_id = self._generate_id(f"sampler-{pipeline_id}-{time.time()}")
        entry = {
            "sampler_id": sampler_id,
            "pipeline_id": pipeline_id,
            "strategy": strategy,
            "sample_size": sample_size,
            "sample": [],
            "total_records": 0,
            "created_at": time.time(),
            "strata_field": None,
            "strata_sizes": None,
            "strata_samples": {},
            "systematic_interval": None,
            "systematic_counter": 0,
        }
        self._state.entries[sampler_id] = entry
        self._prune()
        self._fire("sampler_created", entry)
        logger.info("Created sampler %s for pipeline %s (strategy=%s)", sampler_id, pipeline_id, strategy)
        return sampler_id

    def add_record(self, sampler_id: str, record) -> bool:
        entry = self._state.entries.get(sampler_id)
        if entry is None:
            raise KeyError(f"Sampler not found: {sampler_id}")

        entry["total_records"] += 1
        included = False
        strategy = entry["strategy"]

        if strategy == "reservoir":
            included = self._reservoir_add(entry, record)
        elif strategy == "stratified":
            included = self._stratified_add(entry, record)
        elif strategy == "systematic":
            included = self._systematic_add(entry, record)

        if included:
            self._fire("record_added", {"sampler_id": sampler_id, "record": record})
        return included

    def _reservoir_add(self, entry: dict, record) -> bool:
        sample = entry["sample"]
        n = entry["total_records"]
        size = entry["sample_size"]
        if len(sample) < size:
            sample.append(record)
            return True
        j = random.randint(0, n - 1)
        if j < size:
            sample[j] = record
            return True
        return False

    def _stratified_add(self, entry: dict, record) -> bool:
        strata_field = entry["strata_field"]
        if strata_field is None:
            # Fall back to reservoir if no strata configured
            return self._reservoir_add(entry, record)

        if isinstance(record, dict):
            stratum = record.get(strata_field, "__default__")
        else:
            stratum = "__default__"

        strata_samples = entry["strata_samples"]
        if stratum not in strata_samples:
            strata_samples[stratum] = []

        stratum_sample = strata_samples[stratum]
        strata_sizes = entry.get("strata_sizes") or {}
        max_for_stratum = strata_sizes.get(stratum, entry["sample_size"])

        if len(stratum_sample) < max_for_stratum:
            stratum_sample.append(record)
            # Rebuild combined sample
            entry["sample"] = []
            for s_records in strata_samples.values():
                entry["sample"].extend(s_records)
            return True

        # Reservoir replacement within stratum
        n = sum(1 for _ in stratum_sample) + 1  # approximate count for this stratum
        j = random.randint(0, entry["total_records"] - 1)
        if j < max_for_stratum:
            stratum_sample[j % len(stratum_sample)] = record
            entry["sample"] = []
            for s_records in strata_samples.values():
                entry["sample"].extend(s_records)
            return True
        return False

    def _systematic_add(self, entry: dict, record) -> bool:
        if entry["systematic_interval"] is None:
            entry["systematic_interval"] = max(1, entry["total_records"] // max(1, entry["sample_size"]))
            if entry["systematic_interval"] < 1:
                entry["systematic_interval"] = 1

        entry["systematic_counter"] += 1
        interval = entry["systematic_interval"]

        if entry["systematic_counter"] % interval == 0:
            sample = entry["sample"]
            if len(sample) < entry["sample_size"]:
                sample.append(record)
                return True
            # Replace oldest if over size
            sample.pop(0)
            sample.append(record)
            return True
        return False

    def get_sample(self, sampler_id: str) -> list:
        entry = self._state.entries.get(sampler_id)
        if entry is None:
            raise KeyError(f"Sampler not found: {sampler_id}")
        return list(entry["sample"])

    def get_sample_size(self, sampler_id: str) -> int:
        entry = self._state.entries.get(sampler_id)
        if entry is None:
            raise KeyError(f"Sampler not found: {sampler_id}")
        return len(entry["sample"])

    def configure_strata(self, sampler_id: str, strata_field: str, strata_sizes: dict = None) -> bool:
        entry = self._state.entries.get(sampler_id)
        if entry is None:
            return False
        entry["strata_field"] = strata_field
        entry["strata_sizes"] = strata_sizes
        self._fire("strata_configured", {"sampler_id": sampler_id, "strata_field": strata_field})
        return True

    def get_sampler(self, sampler_id: str):
        entry = self._state.entries.get(sampler_id)
        if entry is None:
            return None
        return dict(entry)

    def get_samplers(self, pipeline_id: str) -> list:
        return [
            dict(e) for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        ]

    def get_sampler_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def list_pipelines(self) -> list:
        seen = []
        for e in self._state.entries.values():
            pid = e.get("pipeline_id")
            if pid and pid not in seen:
                seen.append(pid)
        return seen

    def get_stats(self) -> dict:
        total_records = sum(e.get("total_records", 0) for e in self._state.entries.values())
        total_sampled = sum(len(e.get("sample", [])) for e in self._state.entries.values())
        return {
            "sampler_count": len(self._state.entries),
            "pipeline_count": len(self.list_pipelines()),
            "total_records_seen": total_records,
            "total_sampled": total_sampled,
            "callback_count": len(self._callbacks),
        }

    def reset(self):
        self._state = PipelineDataSamplerV2State()
        self._callbacks.clear()
        logger.info("PipelineDataSamplerV2 reset")

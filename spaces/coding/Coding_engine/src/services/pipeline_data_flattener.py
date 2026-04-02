import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataFlattenerState:
    entries: dict
    _seq: int = 0


class PipelineDataFlattener:
    def __init__(self):
        self._state = PipelineDataFlattenerState(entries={})
        self._callbacks = {}

    def _generate_id(self, data):
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "pdf2-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def on_change(self, name, cb):
        self._callbacks[name] = cb

    def remove_callback(self, name):
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action, detail_dict):
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail_dict)
            except Exception as e:
                logger.error(f"Callback {name} failed: {e}")

    def _prune(self):
        if len(self._state.entries) > 10000:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("timestamp", 0),
            )
            to_remove = sorted_keys[:-5000]
            for k in to_remove:
                del self._state.entries[k]
            logger.info(f"Pruned entries to 5000")

    def configure(self, pipeline_id, separator=".", max_depth=10):
        config_id = self._generate_id(f"config:{pipeline_id}")
        entry = {
            "id": config_id,
            "pipeline_id": pipeline_id,
            "separator": separator,
            "max_depth": max_depth,
            "timestamp": time.time(),
            "type": "config",
        }
        self._state.entries[config_id] = entry
        self._prune()
        self._fire("configure", {"config_id": config_id, "pipeline_id": pipeline_id})
        logger.info(f"Configured flattener for pipeline {pipeline_id}: {config_id}")
        return config_id

    def _get_pipeline_config(self, pipeline_id):
        for entry in self._state.entries.values():
            if entry.get("type") == "config" and entry.get("pipeline_id") == pipeline_id:
                return entry
        return None

    def flatten(self, pipeline_id, record):
        config = self._get_pipeline_config(pipeline_id)
        if config is None:
            raise ValueError(f"No configuration found for pipeline {pipeline_id}")
        separator = config["separator"]
        max_depth = config["max_depth"]
        result = {}
        self._flatten_recursive(record, "", separator, max_depth, 0, result)
        self._fire("flatten", {"pipeline_id": pipeline_id, "keys": len(result)})
        return result

    def _flatten_recursive(self, obj, prefix, separator, max_depth, depth, result):
        if depth >= max_depth:
            result[prefix] = obj
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}{separator}{key}" if prefix else key
                self._flatten_recursive(value, new_key, separator, max_depth, depth + 1, result)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                new_key = f"{prefix}{separator}{i}" if prefix else str(i)
                self._flatten_recursive(value, new_key, separator, max_depth, depth + 1, result)
        else:
            result[prefix] = obj

    def unflatten(self, pipeline_id, record):
        config = self._get_pipeline_config(pipeline_id)
        if config is None:
            raise ValueError(f"No configuration found for pipeline {pipeline_id}")
        separator = config["separator"]
        result = {}
        for key, value in record.items():
            parts = key.split(separator)
            current = result
            for i, part in enumerate(parts[:-1]):
                next_part = parts[i + 1]
                is_next_index = next_part.isdigit()
                if part not in current:
                    current[part] = [] if is_next_index else {}
                current = current[part]
            last = parts[-1]
            if isinstance(current, list):
                idx = int(last)
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
            else:
                current[last] = value
        self._fire("unflatten", {"pipeline_id": pipeline_id, "keys": len(record)})
        return result

    def get_config(self, pipeline_id):
        config = self._get_pipeline_config(pipeline_id)
        if config is None:
            return None
        return dict(config)

    def remove_config(self, config_id):
        if config_id in self._state.entries:
            del self._state.entries[config_id]
            self._fire("remove_config", {"config_id": config_id})
            return True
        return False

    def get_config_count(self, pipeline_id=""):
        count = 0
        for entry in self._state.entries.values():
            if entry.get("type") == "config":
                if pipeline_id == "" or entry.get("pipeline_id") == pipeline_id:
                    count += 1
        return count

    def list_pipelines(self):
        pipelines = []
        for entry in self._state.entries.values():
            if entry.get("type") == "config":
                pid = entry.get("pipeline_id")
                if pid not in pipelines:
                    pipelines.append(pid)
        return pipelines

    def get_stats(self):
        total = len(self._state.entries)
        configs = sum(1 for e in self._state.entries.values() if e.get("type") == "config")
        return {
            "total_entries": total,
            "config_count": configs,
            "seq": self._state._seq,
            "callback_count": len(self._callbacks),
        }

    def reset(self):
        self._state = PipelineDataFlattenerState(entries={})
        self._fire("reset", {})
        logger.info("PipelineDataFlattener reset")

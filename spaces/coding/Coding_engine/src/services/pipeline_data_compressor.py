"""Pipeline data compressor - compresses/decompresses pipeline data using simple strategies."""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineDataCompressor:
    """Compresses and decompresses pipeline data using configurable strategies.

    Supports per-pipeline compression configuration with base64 and json_compact strategies.
    """

    max_entries: int = 10000
    _configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_configs_created: int = field(default=0)
    _total_compressions: int = field(default=0)
    _total_decompressions: int = field(default=0)

    def _next_id(self, pipeline_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{pipeline_id}{self._seq}".encode()).hexdigest()[:12]
        return f"pdco-{raw}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "pipeline_data_compressor.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def configure(
        self, pipeline_id: str, strategy: str = "base64"
    ) -> str:
        """Configure compression for a pipeline.

        Args:
            pipeline_id: The pipeline this config belongs to.
            strategy: Compression strategy - "base64" or "json_compact".

        Returns:
            The config ID (prefixed with 'pdco-').
        """
        if not pipeline_id:
            return ""
        if strategy not in ("base64", "json_compact"):
            return ""
        if len(self._configs) >= self.max_entries:
            return ""

        config_id = self._next_id(pipeline_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "config_id": config_id,
            "pipeline_id": pipeline_id,
            "strategy": strategy,
            "created_at": now,
        }
        self._configs[config_id] = entry
        self._total_configs_created += 1
        logger.info(
            "pipeline_data_compressor.configured",
            config_id=config_id,
            pipeline_id=pipeline_id,
            strategy=strategy,
        )
        self._fire("configured", {"config_id": config_id, "pipeline_id": pipeline_id})
        return config_id

    def compress(self, pipeline_id: str, data: str) -> str:
        """Compress data using the configured strategy for the pipeline.

        For base64: base64 encode the data.
        For json_compact: strip whitespace.

        Returns:
            Compressed string.
        """
        cfg = self._get_latest_config(pipeline_id)
        if cfg is None:
            return data

        strategy = cfg["strategy"]
        if strategy == "base64":
            result = base64.b64encode(data.encode()).decode()
        elif strategy == "json_compact":
            result = data.replace(" ", "").replace("\n", "").replace("\t", "")
        else:
            result = data

        self._total_compressions += 1
        logger.info(
            "pipeline_data_compressor.compressed",
            pipeline_id=pipeline_id,
            strategy=strategy,
            input_len=len(data),
            output_len=len(result),
        )
        self._fire("compressed", {"pipeline_id": pipeline_id, "strategy": strategy})
        return result

    def decompress(self, pipeline_id: str, data: str) -> str:
        """Decompress data using the configured strategy for the pipeline.

        For base64: base64 decode the data.
        For json_compact: return as-is (already valid).

        Returns:
            Decompressed string.
        """
        cfg = self._get_latest_config(pipeline_id)
        if cfg is None:
            return data

        strategy = cfg["strategy"]
        if strategy == "base64":
            result = base64.b64decode(data.encode()).decode()
        elif strategy == "json_compact":
            result = data
        else:
            result = data

        self._total_decompressions += 1
        logger.info(
            "pipeline_data_compressor.decompressed",
            pipeline_id=pipeline_id,
            strategy=strategy,
        )
        self._fire("decompressed", {"pipeline_id": pipeline_id, "strategy": strategy})
        return result

    def get_config(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest compression configuration for a pipeline."""
        cfg = self._get_latest_config(pipeline_id)
        if cfg is None:
            return None
        return dict(cfg)

    def get_config_count(self, pipeline_id: str = "") -> int:
        """Return the number of configs, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._configs)
        count = 0
        for entry in self._configs.values():
            if entry["pipeline_id"] == pipeline_id:
                count += 1
        return count

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline IDs that have compression configs."""
        seen: set[str] = set()
        result: List[str] = []
        for entry in self._configs.values():
            pid = entry["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns True if registered, False if name exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        logger.debug("pipeline_data_compressor.callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if found, False otherwise."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("pipeline_data_compressor.callback_removed", name=name)
        return True

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_configs": len(self._configs),
            "total_configs_created": self._total_configs_created,
            "total_compressions": self._total_compressions,
            "total_decompressions": self._total_decompressions,
            "max_entries": self.max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._configs.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_configs_created = 0
        self._total_compressions = 0
        self._total_decompressions = 0
        logger.info("pipeline_data_compressor.reset")

    # -- internal helpers ----------------------------------------------------

    def _get_latest_config(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recently created config for a pipeline."""
        cfg = None
        for entry in self._configs.values():
            if entry["pipeline_id"] == pipeline_id:
                if cfg is None or entry["created_at"] > cfg["created_at"]:
                    cfg = entry
        return cfg

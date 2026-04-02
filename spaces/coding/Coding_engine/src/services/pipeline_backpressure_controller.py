"""Pipeline backpressure controller - manage flow control and rate limiting."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Channel:
    """A backpressure-controlled channel."""
    channel_id: str = ""
    name: str = ""
    max_pending: int = 100
    current_pending: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    total_drained: int = 0
    strategy: str = "drop"
    status: str = "open"
    tags: list = field(default_factory=list)
    created_at: float = 0.0
    paused_at: float = 0.0


class PipelineBackpressureController:
    """Control flow with backpressure across pipeline channels."""

    STRATEGIES = ("drop", "block", "buffer", "sample", "throttle")
    STATUSES = ("open", "paused", "closed")

    def __init__(self, max_channels: int = 5000):
        self._max_channels = max(1, max_channels)
        self._channels: Dict[str, Channel] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_channels": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "total_drained": 0,
            "total_pressure_events": 0,
        }

    # --- Channel Management ---

    def create_channel(
        self,
        name: str,
        max_pending: int = 100,
        strategy: str = "drop",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a backpressure channel."""
        if not name:
            return ""
        if strategy not in self.STRATEGIES:
            return ""
        if max_pending < 1:
            return ""
        if len(self._channels) >= self._max_channels:
            return ""

        cid = f"bp-{uuid.uuid4().hex[:12]}"
        self._channels[cid] = Channel(
            channel_id=cid,
            name=name,
            max_pending=max_pending,
            strategy=strategy,
            tags=list(tags or []),
            created_at=time.time(),
        )
        self._stats["total_channels"] += 1
        return cid

    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """Get channel details."""
        ch = self._channels.get(channel_id)
        if not ch:
            return None
        return {
            "channel_id": ch.channel_id,
            "name": ch.name,
            "max_pending": ch.max_pending,
            "current_pending": ch.current_pending,
            "total_accepted": ch.total_accepted,
            "total_rejected": ch.total_rejected,
            "total_drained": ch.total_drained,
            "strategy": ch.strategy,
            "status": ch.status,
            "pressure_ratio": ch.current_pending / ch.max_pending if ch.max_pending > 0 else 0.0,
            "tags": list(ch.tags),
        }

    def remove_channel(self, channel_id: str) -> bool:
        """Remove a channel."""
        if channel_id not in self._channels:
            return False
        del self._channels[channel_id]
        return True

    # --- Flow Control ---

    def try_accept(self, channel_id: str, count: int = 1) -> bool:
        """Try to accept items into channel. Returns True if accepted."""
        ch = self._channels.get(channel_id)
        if not ch or ch.status == "closed":
            return False
        if ch.status == "paused":
            self._stats["total_rejected"] += count
            ch.total_rejected += count
            return False
        if count < 1:
            return False

        if ch.current_pending + count > ch.max_pending:
            # Apply strategy
            if ch.strategy == "drop":
                self._stats["total_rejected"] += count
                ch.total_rejected += count
                self._check_pressure(ch)
                return False
            elif ch.strategy == "sample":
                # Accept only 1 item when over pressure
                ch.current_pending += 1
                ch.total_accepted += 1
                self._stats["total_accepted"] += 1
                self._stats["total_rejected"] += (count - 1)
                ch.total_rejected += (count - 1)
                self._check_pressure(ch)
                return True
            else:
                # buffer/block/throttle: reject when full
                self._stats["total_rejected"] += count
                ch.total_rejected += count
                self._check_pressure(ch)
                return False

        ch.current_pending += count
        ch.total_accepted += count
        self._stats["total_accepted"] += count
        self._check_pressure(ch)
        return True

    def drain(self, channel_id: str, count: int = 1) -> int:
        """Drain items from channel. Returns number actually drained."""
        ch = self._channels.get(channel_id)
        if not ch or count < 1:
            return 0

        actual = min(count, ch.current_pending)
        ch.current_pending -= actual
        ch.total_drained += actual
        self._stats["total_drained"] += actual
        return actual

    def drain_all(self, channel_id: str) -> int:
        """Drain all pending items."""
        ch = self._channels.get(channel_id)
        if not ch:
            return 0
        return self.drain(channel_id, ch.current_pending)

    def pause_channel(self, channel_id: str) -> bool:
        """Pause a channel (rejects new items)."""
        ch = self._channels.get(channel_id)
        if not ch or ch.status != "open":
            return False
        ch.status = "paused"
        ch.paused_at = time.time()
        self._fire("channel_paused", {"channel_id": channel_id})
        return True

    def resume_channel(self, channel_id: str) -> bool:
        """Resume a paused channel."""
        ch = self._channels.get(channel_id)
        if not ch or ch.status != "paused":
            return False
        ch.status = "open"
        ch.paused_at = 0.0
        self._fire("channel_resumed", {"channel_id": channel_id})
        return True

    def close_channel(self, channel_id: str) -> bool:
        """Close a channel permanently."""
        ch = self._channels.get(channel_id)
        if not ch or ch.status == "closed":
            return False
        ch.status = "closed"
        self._fire("channel_closed", {"channel_id": channel_id})
        return True

    def set_max_pending(self, channel_id: str, max_pending: int) -> bool:
        """Update max pending for a channel."""
        ch = self._channels.get(channel_id)
        if not ch or max_pending < 1:
            return False
        ch.max_pending = max_pending
        return True

    # --- Queries ---

    def list_channels(
        self,
        status: str = "",
        strategy: str = "",
        tag: str = "",
    ) -> List[Dict]:
        """List channels with filters."""
        results = []
        for ch in self._channels.values():
            if status and ch.status != status:
                continue
            if strategy and ch.strategy != strategy:
                continue
            if tag and tag not in ch.tags:
                continue
            results.append({
                "channel_id": ch.channel_id,
                "name": ch.name,
                "status": ch.status,
                "strategy": ch.strategy,
                "current_pending": ch.current_pending,
                "max_pending": ch.max_pending,
                "pressure_ratio": ch.current_pending / ch.max_pending if ch.max_pending > 0 else 0.0,
            })
        return results

    def get_pressure_report(self) -> List[Dict]:
        """Get pressure status for all channels, sorted by pressure ratio."""
        report = []
        for ch in self._channels.values():
            ratio = ch.current_pending / ch.max_pending if ch.max_pending > 0 else 0.0
            report.append({
                "channel_id": ch.channel_id,
                "name": ch.name,
                "pressure_ratio": round(ratio, 4),
                "current_pending": ch.current_pending,
                "max_pending": ch.max_pending,
                "status": ch.status,
            })
        report.sort(key=lambda x: x["pressure_ratio"], reverse=True)
        return report

    def get_high_pressure_channels(self, threshold: float = 0.8) -> List[Dict]:
        """Get channels above pressure threshold."""
        return [
            r for r in self.get_pressure_report()
            if r["pressure_ratio"] >= threshold
        ]

    def get_channel_throughput(self, channel_id: str) -> Dict:
        """Get throughput stats for a channel."""
        ch = self._channels.get(channel_id)
        if not ch:
            return {}
        elapsed = time.time() - ch.created_at if ch.created_at > 0 else 1.0
        return {
            "channel_id": ch.channel_id,
            "total_accepted": ch.total_accepted,
            "total_rejected": ch.total_rejected,
            "total_drained": ch.total_drained,
            "accept_rate": ch.total_accepted / elapsed if elapsed > 0 else 0.0,
            "reject_ratio": ch.total_rejected / (ch.total_accepted + ch.total_rejected) if (ch.total_accepted + ch.total_rejected) > 0 else 0.0,
        }

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_channels": len(self._channels),
            "open_channels": sum(1 for ch in self._channels.values() if ch.status == "open"),
            "paused_channels": sum(1 for ch in self._channels.values() if ch.status == "paused"),
        }

    def reset(self) -> None:
        self._channels.clear()
        self._callbacks.clear()
        self._stats = {
            "total_channels": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "total_drained": 0,
            "total_pressure_events": 0,
        }

    # --- Internal ---

    def _check_pressure(self, ch: Channel) -> None:
        """Check and fire pressure events."""
        ratio = ch.current_pending / ch.max_pending if ch.max_pending > 0 else 0.0
        if ratio >= 0.9:
            self._stats["total_pressure_events"] += 1
            self._fire("high_pressure", {
                "channel_id": ch.channel_id,
                "pressure_ratio": ratio,
            })

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

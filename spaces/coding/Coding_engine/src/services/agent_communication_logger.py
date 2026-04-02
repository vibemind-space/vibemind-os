"""Agent communication logger.

Logs and analyzes inter-agent communication patterns, message volumes,
response times, and conversation threads.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _CommEntry:
    """A communication log entry."""
    entry_id: str = ""
    sender: str = ""
    receiver: str = ""
    channel: str = ""
    msg_type: str = "message"  # message, request, response, broadcast, error
    content_summary: str = ""
    size_bytes: int = 0
    thread_id: str = ""
    tags: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    seq: int = 0


@dataclass
class _Thread:
    """A conversation thread."""
    thread_id: str = ""
    subject: str = ""
    participants: List[str] = field(default_factory=list)
    entry_count: int = 0
    status: str = "active"  # active, closed
    created_at: float = 0.0
    closed_at: float = 0.0


class AgentCommunicationLogger:
    """Logs and analyzes agent communications."""

    MSG_TYPES = ("message", "request", "response", "broadcast", "error")

    def __init__(self, max_entries: int = 200000,
                 max_threads: int = 50000):
        self._max_entries = max_entries
        self._max_threads = max_threads
        self._entries: Dict[str, _CommEntry] = {}
        self._threads: Dict[str, _Thread] = {}
        self._entry_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_entries_logged": 0,
            "total_bytes_logged": 0,
            "total_threads_created": 0,
            "total_threads_closed": 0,
        }

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_comm(self, sender: str, receiver: str, channel: str = "",
                 msg_type: str = "message", content_summary: str = "",
                 size_bytes: int = 0, thread_id: str = "",
                 tags: Optional[List[str]] = None) -> str:
        """Log a communication entry."""
        if not sender or not receiver:
            return ""
        if msg_type not in self.MSG_TYPES:
            return ""
        if len(self._entries) >= self._max_entries:
            self._prune_entries()

        self._entry_seq += 1
        eid = "comm-" + hashlib.md5(
            f"{sender}{receiver}{time.time()}{self._entry_seq}".encode()
        ).hexdigest()[:12]

        self._entries[eid] = _CommEntry(
            entry_id=eid,
            sender=sender,
            receiver=receiver,
            channel=channel,
            msg_type=msg_type,
            content_summary=content_summary,
            size_bytes=size_bytes,
            thread_id=thread_id,
            tags=tags or [],
            timestamp=time.time(),
            seq=self._entry_seq,
        )
        self._stats["total_entries_logged"] += 1
        self._stats["total_bytes_logged"] += size_bytes

        # Update thread if specified
        if thread_id and thread_id in self._threads:
            t = self._threads[thread_id]
            t.entry_count += 1
            if sender not in t.participants:
                t.participants.append(sender)
            if receiver not in t.participants:
                t.participants.append(receiver)

        self._fire("comm_logged", {
            "entry_id": eid, "sender": sender, "receiver": receiver,
            "msg_type": msg_type,
        })
        return eid

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Get log entry."""
        e = self._entries.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id,
            "sender": e.sender,
            "receiver": e.receiver,
            "channel": e.channel,
            "msg_type": e.msg_type,
            "content_summary": e.content_summary,
            "size_bytes": e.size_bytes,
            "thread_id": e.thread_id,
            "tags": list(e.tags),
            "timestamp": e.timestamp,
        }

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a log entry."""
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        return True

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def create_thread(self, subject: str,
                      participants: Optional[List[str]] = None) -> str:
        """Create a conversation thread."""
        if not subject:
            return ""
        if len(self._threads) >= self._max_threads:
            return ""

        tid = "thr-" + hashlib.md5(
            f"{subject}{time.time()}{len(self._threads)}".encode()
        ).hexdigest()[:12]

        self._threads[tid] = _Thread(
            thread_id=tid,
            subject=subject,
            participants=participants or [],
            created_at=time.time(),
        )
        self._stats["total_threads_created"] += 1
        return tid

    def get_thread(self, thread_id: str) -> Optional[Dict]:
        """Get thread info."""
        t = self._threads.get(thread_id)
        if not t:
            return None
        return {
            "thread_id": t.thread_id,
            "subject": t.subject,
            "participants": list(t.participants),
            "entry_count": t.entry_count,
            "status": t.status,
        }

    def close_thread(self, thread_id: str) -> bool:
        """Close a thread."""
        t = self._threads.get(thread_id)
        if not t or t.status != "active":
            return False
        t.status = "closed"
        t.closed_at = time.time()
        self._stats["total_threads_closed"] += 1
        return True

    def remove_thread(self, thread_id: str) -> bool:
        """Remove a thread."""
        if thread_id not in self._threads:
            return False
        del self._threads[thread_id]
        return True

    def get_thread_entries(self, thread_id: str) -> List[Dict]:
        """Get entries in a thread."""
        result = []
        for e in self._entries.values():
            if e.thread_id != thread_id:
                continue
            result.append({
                "entry_id": e.entry_id,
                "sender": e.sender,
                "receiver": e.receiver,
                "msg_type": e.msg_type,
                "content_summary": e.content_summary,
                "seq": e.seq,
            })
        result.sort(key=lambda x: x["seq"])
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_entries(self, sender: Optional[str] = None,
                       receiver: Optional[str] = None,
                       channel: Optional[str] = None,
                       msg_type: Optional[str] = None,
                       tag: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """Search log entries."""
        result = []
        for e in self._entries.values():
            if sender and e.sender != sender:
                continue
            if receiver and e.receiver != receiver:
                continue
            if channel and e.channel != channel:
                continue
            if msg_type and e.msg_type != msg_type:
                continue
            if tag and tag not in e.tags:
                continue
            result.append({
                "entry_id": e.entry_id,
                "sender": e.sender,
                "receiver": e.receiver,
                "msg_type": e.msg_type,
                "channel": e.channel,
                "timestamp": e.timestamp,
                "seq": e.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_agent_comm_stats(self, agent: str) -> Dict:
        """Get communication stats for an agent."""
        sent = 0
        received = 0
        bytes_sent = 0
        bytes_received = 0
        for e in self._entries.values():
            if e.sender == agent:
                sent += 1
                bytes_sent += e.size_bytes
            if e.receiver == agent:
                received += 1
                bytes_received += e.size_bytes
        return {
            "agent": agent,
            "messages_sent": sent,
            "messages_received": received,
            "bytes_sent": bytes_sent,
            "bytes_received": bytes_received,
        }

    def get_channel_volume(self) -> Dict[str, int]:
        """Get message counts by channel."""
        volume: Dict[str, int] = {}
        for e in self._entries.values():
            ch = e.channel or "(direct)"
            volume[ch] = volume.get(ch, 0) + 1
        return dict(sorted(volume.items(), key=lambda x: -x[1]))

    def get_msg_type_counts(self) -> Dict[str, int]:
        """Get counts by message type."""
        counts = {t: 0 for t in self.MSG_TYPES}
        for e in self._entries.values():
            counts[e.msg_type] += 1
        return counts

    def get_busiest_pairs(self, limit: int = 10) -> List[Dict]:
        """Get most active sender-receiver pairs."""
        pairs: Dict[str, int] = {}
        for e in self._entries.values():
            key = f"{e.sender}->{e.receiver}"
            pairs[key] = pairs.get(key, 0) + 1
        result = [{"pair": k, "count": v}
                  for k, v in sorted(pairs.items(), key=lambda x: -x[1])]
        return result[:limit]

    def list_threads(self, status: Optional[str] = None) -> List[Dict]:
        """List threads."""
        result = []
        for t in self._threads.values():
            if status and t.status != status:
                continue
            result.append({
                "thread_id": t.thread_id,
                "subject": t.subject,
                "participant_count": len(t.participants),
                "entry_count": t.entry_count,
                "status": t.status,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_entries(self) -> None:
        """Remove oldest entries."""
        items = sorted(self._entries.items(), key=lambda x: x[1].seq)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._entries[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "current_threads": len(self._threads),
            "active_threads": sum(
                1 for t in self._threads.values() if t.status == "active"
            ),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._threads.clear()
        self._entry_seq = 0
        self._stats = {k: 0 for k in self._stats}

"""Pipeline secret vault.

Securely stores and manages secrets (API keys, tokens, credentials)
used by pipeline components and agents. Supports versioning, access
control, and rotation tracking.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Secret:
    """A stored secret."""
    secret_id: str = ""
    name: str = ""
    value: str = ""  # in production would be encrypted
    secret_type: str = "generic"  # generic, api_key, token, credential, certificate
    owner: str = ""
    status: str = "active"  # active, rotated, revoked, expired
    version: int = 1
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    allowed_accessors: List[str] = field(default_factory=list)
    access_count: int = 0
    last_accessed_at: float = 0.0
    last_rotated_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _AccessLog:
    """A secret access log entry."""
    log_id: str = ""
    secret_id: str = ""
    accessor: str = ""
    action: str = ""  # read, rotate, revoke
    granted: bool = True
    created_at: float = 0.0
    seq: int = 0


class PipelineSecretVault:
    """Manages pipeline secrets securely."""

    SECRET_TYPES = ("generic", "api_key", "token", "credential", "certificate")
    STATUSES = ("active", "rotated", "revoked", "expired")
    ACCESS_ACTIONS = ("read", "rotate", "revoke")

    def __init__(self, max_secrets: int = 10000,
                 max_logs: int = 500000):
        self._max_secrets = max_secrets
        self._max_logs = max_logs
        self._secrets: Dict[str, _Secret] = {}
        self._logs: Dict[str, _AccessLog] = {}
        self._name_index: Dict[str, str] = {}  # name -> secret_id
        self._secret_seq = 0
        self._log_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_secrets_created": 0,
            "total_accesses": 0,
            "total_rotations": 0,
            "total_revocations": 0,
            "total_denied": 0,
        }

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def store_secret(self, name: str, value: str,
                     secret_type: str = "generic",
                     owner: str = "",
                     allowed_accessors: Optional[List[str]] = None,
                     tags: Optional[List[str]] = None,
                     metadata: Optional[Dict] = None) -> str:
        """Store a new secret."""
        if not name or not value:
            return ""
        if secret_type not in self.SECRET_TYPES:
            return ""
        if name in self._name_index:
            return ""  # duplicate name
        if len(self._secrets) >= self._max_secrets:
            return ""

        self._secret_seq += 1
        sid = "sec-" + hashlib.md5(
            f"{name}{time.time()}{self._secret_seq}{len(self._secrets)}".encode()
        ).hexdigest()[:12]

        self._secrets[sid] = _Secret(
            secret_id=sid,
            name=name,
            value=value,
            secret_type=secret_type,
            owner=owner,
            allowed_accessors=allowed_accessors or [],
            tags=tags or [],
            metadata=metadata or {},
            created_at=time.time(),
            seq=self._secret_seq,
        )
        self._name_index[name] = sid
        self._stats["total_secrets_created"] += 1
        self._fire("secret_stored", {"secret_id": sid, "name": name})
        return sid

    def get_secret_info(self, secret_id: str) -> Optional[Dict]:
        """Get secret metadata (not the value)."""
        s = self._secrets.get(secret_id)
        if not s:
            return None
        return {
            "secret_id": s.secret_id,
            "name": s.name,
            "secret_type": s.secret_type,
            "owner": s.owner,
            "status": s.status,
            "version": s.version,
            "tags": list(s.tags),
            "allowed_accessors": list(s.allowed_accessors),
            "access_count": s.access_count,
            "last_accessed_at": s.last_accessed_at,
            "seq": s.seq,
        }

    def read_secret(self, secret_id: str, accessor: str = "") -> Optional[str]:
        """Read a secret value with access control."""
        s = self._secrets.get(secret_id)
        if not s or s.status != "active":
            return None

        # Check access control
        if s.allowed_accessors and accessor not in s.allowed_accessors:
            self._log_access(secret_id, accessor, "read", granted=False)
            self._stats["total_denied"] += 1
            return None

        s.access_count += 1
        s.last_accessed_at = time.time()
        self._stats["total_accesses"] += 1
        self._log_access(secret_id, accessor, "read", granted=True)
        return s.value

    def read_secret_by_name(self, name: str, accessor: str = "") -> Optional[str]:
        """Read a secret by name."""
        sid = self._name_index.get(name)
        if not sid:
            return None
        return self.read_secret(sid, accessor)

    def rotate_secret(self, secret_id: str, new_value: str,
                      accessor: str = "") -> bool:
        """Rotate a secret to a new value."""
        s = self._secrets.get(secret_id)
        if not s or s.status != "active":
            return False
        if not new_value:
            return False

        s.value = new_value
        s.version += 1
        s.last_rotated_at = time.time()
        self._stats["total_rotations"] += 1
        self._log_access(secret_id, accessor, "rotate", granted=True)
        self._fire("secret_rotated", {
            "secret_id": secret_id, "version": s.version,
        })
        return True

    def revoke_secret(self, secret_id: str, accessor: str = "") -> bool:
        """Revoke a secret."""
        s = self._secrets.get(secret_id)
        if not s or s.status == "revoked":
            return False

        s.status = "revoked"
        s.value = ""  # clear the value
        self._stats["total_revocations"] += 1
        self._log_access(secret_id, accessor, "revoke", granted=True)
        return True

    def remove_secret(self, secret_id: str) -> bool:
        """Remove a secret entirely."""
        s = self._secrets.get(secret_id)
        if not s:
            return False
        del self._name_index[s.name]
        del self._secrets[secret_id]
        # Cascade remove logs
        to_remove = [lid for lid, l in self._logs.items()
                     if l.secret_id == secret_id]
        for lid in to_remove:
            del self._logs[lid]
        return True

    def grant_access(self, secret_id: str, accessor: str) -> bool:
        """Grant an accessor access to a secret."""
        s = self._secrets.get(secret_id)
        if not s or not accessor:
            return False
        if accessor in s.allowed_accessors:
            return False
        s.allowed_accessors.append(accessor)
        return True

    def revoke_access(self, secret_id: str, accessor: str) -> bool:
        """Revoke an accessor's access to a secret."""
        s = self._secrets.get(secret_id)
        if not s or accessor not in s.allowed_accessors:
            return False
        s.allowed_accessors.remove(accessor)
        return True

    # ------------------------------------------------------------------
    # Access Logging
    # ------------------------------------------------------------------

    def _log_access(self, secret_id: str, accessor: str,
                    action: str, granted: bool) -> str:
        if len(self._logs) >= self._max_logs:
            return ""
        self._log_seq += 1
        lid = "slog-" + hashlib.md5(
            f"{secret_id}{accessor}{time.time()}{self._log_seq}".encode()
        ).hexdigest()[:12]
        self._logs[lid] = _AccessLog(
            log_id=lid,
            secret_id=secret_id,
            accessor=accessor,
            action=action,
            granted=granted,
            created_at=time.time(),
            seq=self._log_seq,
        )
        return lid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_secrets(self, secret_type: Optional[str] = None,
                       owner: Optional[str] = None,
                       status: Optional[str] = None,
                       tag: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """Search secrets (returns metadata only)."""
        result = []
        for s in self._secrets.values():
            if secret_type and s.secret_type != secret_type:
                continue
            if owner and s.owner != owner:
                continue
            if status and s.status != status:
                continue
            if tag and tag not in s.tags:
                continue
            result.append({
                "secret_id": s.secret_id,
                "name": s.name,
                "secret_type": s.secret_type,
                "owner": s.owner,
                "status": s.status,
                "version": s.version,
                "access_count": s.access_count,
                "seq": s.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_access_log(self, secret_id: Optional[str] = None,
                       accessor: Optional[str] = None,
                       granted: Optional[bool] = None,
                       limit: int = 100) -> List[Dict]:
        """Get access log entries."""
        result = []
        for l in self._logs.values():
            if secret_id and l.secret_id != secret_id:
                continue
            if accessor and l.accessor != accessor:
                continue
            if granted is not None and l.granted != granted:
                continue
            result.append({
                "log_id": l.log_id,
                "secret_id": l.secret_id,
                "accessor": l.accessor,
                "action": l.action,
                "granted": l.granted,
                "seq": l.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_secret_by_name(self, name: str) -> Optional[Dict]:
        """Get secret info by name (no value)."""
        sid = self._name_index.get(name)
        if not sid:
            return None
        return self.get_secret_info(sid)

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
            "current_secrets": len(self._secrets),
            "active_secrets": sum(1 for s in self._secrets.values()
                                  if s.status == "active"),
            "current_logs": len(self._logs),
        }

    def reset(self) -> None:
        self._secrets.clear()
        self._logs.clear()
        self._name_index.clear()
        self._secret_seq = 0
        self._log_seq = 0
        self._stats = {k: 0 for k in self._stats}

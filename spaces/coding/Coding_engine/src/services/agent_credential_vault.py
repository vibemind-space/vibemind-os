"""Secure in-memory credential storage for agents.

Stores credential name and masked value per agent, with change callbacks,
max-entries pruning, and structured logging via structlog.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CredentialEntry:
    """Single credential stored in the vault."""

    agent_id: str
    name: str
    value: str
    masked_value: str
    created_at: float = field(default_factory=time.time)
    seq: int = 0


def _generate_id(key: str, seq: int) -> str:
    """Return an ``acv-`` prefixed ID derived from *key*, a uuid, and *seq*."""
    raw = f"{key}{uuid.uuid4()}{seq}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"acv-{digest}"


def _mask(value: str) -> str:
    """Return a masked representation of *value*."""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


class AgentCredentialVault:
    """Secure in-memory credential storage for autonomous agents."""

    def __init__(self) -> None:
        self._credentials: Dict[str, Dict[str, CredentialEntry]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_credential(self, agent_id: str, name: str, value: str) -> str:
        """Store a credential and return its unique ID."""
        self._seq += 1
        cred_id = _generate_id(f"{agent_id}:{name}", self._seq)

        entry = CredentialEntry(
            agent_id=agent_id,
            name=name,
            value=value,
            masked_value=_mask(value),
            seq=self._seq,
        )

        if agent_id not in self._credentials:
            self._credentials[agent_id] = {}

        self._credentials[agent_id][name] = entry
        self._prune()

        logger.info(
            "credential.stored",
            agent_id=agent_id,
            name=name,
            masked_value=entry.masked_value,
            credential_id=cred_id,
        )
        self._fire("store", {"agent_id": agent_id, "name": name, "credential_id": cred_id})
        return cred_id

    def get_credential(self, agent_id: str, name: str) -> Optional[str]:
        """Retrieve the raw credential value, or ``None`` if absent."""
        agent_creds = self._credentials.get(agent_id)
        if agent_creds is None:
            return None
        entry = agent_creds.get(name)
        if entry is None:
            return None
        logger.debug("credential.accessed", agent_id=agent_id, name=name)
        return entry.value

    def has_credential(self, agent_id: str, name: str) -> bool:
        """Return whether *agent_id* owns a credential called *name*."""
        agent_creds = self._credentials.get(agent_id)
        if agent_creds is None:
            return False
        return name in agent_creds

    def revoke_credential(self, agent_id: str, name: str) -> bool:
        """Remove a credential. Return ``True`` if it existed."""
        agent_creds = self._credentials.get(agent_id)
        if agent_creds is None or name not in agent_creds:
            logger.warning("credential.revoke_miss", agent_id=agent_id, name=name)
            return False

        del agent_creds[name]
        if not agent_creds:
            del self._credentials[agent_id]

        logger.info("credential.revoked", agent_id=agent_id, name=name)
        self._fire("revoke", {"agent_id": agent_id, "name": name})
        return True

    def list_credentials(self, agent_id: str) -> List[str]:
        """Return credential names (never values) for *agent_id*."""
        agent_creds = self._credentials.get(agent_id)
        if agent_creds is None:
            return []
        return list(agent_creds.keys())

    def list_agents(self) -> List[str]:
        """Return all agent IDs that have stored credentials."""
        return list(self._credentials.keys())

    def get_credential_count(self) -> int:
        """Return total number of credentials across all agents."""
        return sum(len(creds) for creds in self._credentials.values())

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*."""
        self._callbacks[name] = callback
        logger.debug("callback.registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Return ``True`` if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback.removed", name=name)
        return True

    def get_stats(self) -> Dict:
        """Return a dictionary of vault statistics."""
        return {
            "total_credentials": self.get_credential_count(),
            "total_agents": len(self._credentials),
            "seq": self._seq,
            "max_entries": self._max_entries,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all credentials, callbacks, and counters."""
        self._credentials.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("vault.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict) -> None:
        """Invoke every registered callback with *action* and *detail*."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback.error", callback=cb_name, action=action)

    def _prune(self) -> None:
        """Remove oldest entries when the vault exceeds ``_max_entries``."""
        total = self.get_credential_count()
        if total <= self._max_entries:
            return

        all_entries: List[CredentialEntry] = []
        for agent_creds in self._credentials.values():
            all_entries.extend(agent_creds.values())

        all_entries.sort(key=lambda e: e.created_at)
        remove_count = total - self._max_entries

        for entry in all_entries[:remove_count]:
            agent_creds = self._credentials.get(entry.agent_id)
            if agent_creds and entry.name in agent_creds:
                del agent_creds[entry.name]
                if not agent_creds:
                    del self._credentials[entry.agent_id]

        logger.info("vault.pruned", removed=remove_count)

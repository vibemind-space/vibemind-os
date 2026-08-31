"""Central config & secret resolution for the Brain (Phase C foundation).

ONE place that answers three questions the rest of the code keeps asking
ad-hoc via scattered ``os.environ.get``:

  1. **Secrets** — resolve a key with a clear precedence:
       Docker-Swarm secret file  (``<NAME>_FILE`` -> /run/secrets/<name>)
         >  process env          (``<NAME>``)
         >  repo .env            (loaded by the existing load_env.py)
     The ``<NAME>_FILE`` convention matches the existing
     ``vibemind-os/coding-engine/infra/docker/docker-stack.yml`` which already
     does ``OPENROUTER_API_KEY_FILE: /run/secrets/openrouter_api_key``.

  2. **Identity** — BRAIN_ID / SPACE_ID / BRAIN_ROLE. Defaults reproduce
     today's behaviour exactly (single unnamed mono brain), so importing &
     using this module changes nothing until the env vars are set.

  3. **Checkpoint paths** — namespaced by BRAIN_ID/SPACE_ID when set, else
     the legacy flat ``data/...`` path (byte-for-byte unchanged default).

Design rules:
  * Importing this module has NO side effects beyond what load_env.py already
    does (it just calls load_env.py's loader, which is idempotent and only
    fills vars that are unset).
  * Every getter is safe to call before/without Docker — the secret-file
    branch simply doesn't match outside Swarm.
  * Nothing here raises on a missing key; callers keep their existing
    "warn + None/default" behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Reuse the existing .env loader instead of re-implementing parsing. It is
# import-safe (auto-loads once) and only sets vars that aren't already set,
# so calling its loader again is a no-op when env is already populated.
try:
    from load_env import load_env_file as _load_env_file  # type: ignore
except Exception:  # pragma: no cover - load_env lives at brain root
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from load_env import load_env_file as _load_env_file  # type: ignore
    except Exception:
        def _load_env_file(env_path: str = ".env") -> None:  # fallback no-op
            return None


# ---------------------------------------------------------------------------
# Secret resolution
# ---------------------------------------------------------------------------

# Where Docker mounts swarm secrets. Overridable for tests.
_SECRETS_DIR = os.environ.get("VIBEMIND_SECRETS_DIR", "/run/secrets")


def _read_secret_file(path: str) -> Optional[str]:
    try:
        p = Path(path)
        if p.is_file():
            val = p.read_text(encoding="utf-8").strip()
            return val or None
    except Exception:
        pass
    return None


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve a secret/config value with Swarm-aware precedence.

    Order (first non-empty wins):
      1. ``<name>_FILE`` env var pointing at a file (Swarm injects this).
      2. ``/run/secrets/<name lowercased>`` directly (Swarm default mount).
      3. ``<name>`` process env var (covers .env via load_env.py).
      4. ``default``.

    ``name`` is treated case-insensitively for the file lookups but the env
    var lookup uses it verbatim (env vars are conventionally UPPER_SNAKE).
    """
    # 1. <NAME>_FILE -> file contents (docker-stack.yml convention)
    file_env = os.environ.get(f"{name}_FILE")
    if file_env:
        v = _read_secret_file(file_env)
        if v is not None:
            return v

    # 2. /run/secrets/<name lower> (Swarm mounts secrets here by name)
    v = _read_secret_file(os.path.join(_SECRETS_DIR, name.lower()))
    if v is not None:
        return v

    # 3. process env (this also covers repo .env once load_env ran)
    _load_env_file()  # idempotent; only fills unset vars
    v = os.environ.get(name)
    if v:
        return v

    return default


# Convenience accessors for the keys the codebase asks for most. These keep
# call sites terse and make the migration grep-able.
def openrouter_key() -> Optional[str]:
    return get_secret("OPENROUTER_API_KEY")


def openai_key() -> Optional[str]:
    return get_secret("OPENAI_API_KEY")


def anthropic_key() -> Optional[str]:
    return get_secret("ANTHROPIC_API_KEY")


def groq_key() -> Optional[str]:
    return get_secret("GROQ_API_KEY")


def qdrant_url() -> str:
    # Same default as core/qdrant_kg.py:52 so behaviour is unchanged when
    # nothing overrides it.
    return get_secret("QDRANT_URL", "http://127.0.0.1:16333") or "http://127.0.0.1:16333"


def learner_url() -> Optional[str]:
    """Phase D2: where an inference replica forwards reward/train to.

    Returns the learner's base URL (e.g. ``http://brain-learner:5000``) or
    ``None`` when unset. ``None`` is the safe default: a mono/learner brain
    never forwards (it applies locally), and an inference replica with no
    learner configured falls back to the D1 202 "not applied" behaviour
    rather than silently losing the signal to a wrong target.
    """
    v = (os.environ.get("BRAIN_LEARNER_URL", "") or "").strip().rstrip("/")
    return v or None


def embedding_service_url() -> str:
    """Base URL of the embedding-service (docs/superpowers/specs/2026-07-13-
    brain-embedder-external-api-design.md). Default matches the Docker Swarm
    service name on the vibemind-shared overlay network."""
    v = (os.environ.get("EMBEDDING_SERVICE_URL", "") or "").strip().rstrip("/")
    return v or "http://embedding-service:8080"


# ---------------------------------------------------------------------------
# Identity (BRAIN_ID / SPACE_ID / BRAIN_ROLE)
# ---------------------------------------------------------------------------
# Defaults reproduce today's single-mono-brain behaviour exactly.

#: "default" keeps checkpoint dirs == legacy flat layout (see checkpoint_dir).
BRAIN_ID_DEFAULT = "default"
#: empty == not space-scoped (Tier-1 / mono behaviour).
SPACE_ID_DEFAULT = ""
#: mono == initialise everything (Tier-1 + Tier-2), i.e. unchanged.
BRAIN_ROLE_DEFAULT = "mono"

_VALID_ROLES = ("mono", "learner", "inference")


def brain_id() -> str:
    v = os.environ.get("BRAIN_ID", "").strip()
    return v or BRAIN_ID_DEFAULT


def space_id() -> str:
    return os.environ.get("SPACE_ID", "").strip() or SPACE_ID_DEFAULT


def brain_role() -> str:
    v = os.environ.get("BRAIN_ROLE", "").strip().lower()
    return v if v in _VALID_ROLES else BRAIN_ROLE_DEFAULT


def is_learner() -> bool:
    """True if this instance owns learning writes (centroids, Qdrant, snapshots).

    ``mono`` (default) and ``learner`` both write; only ``inference`` is
    read-only. So today's default (mono) behaves exactly as before.
    """
    return brain_role() in ("mono", "learner")


def is_mono() -> bool:
    return brain_role() == "mono"


# ---------------------------------------------------------------------------
# Checkpoint path namespacing
# ---------------------------------------------------------------------------
# CRITICAL INVARIANT: with the default identity (BRAIN_ID="default",
# SPACE_ID="") these helpers return the EXACT legacy paths so existing
# checkpoints keep loading and tests stay green. Namespacing only kicks in
# once BRAIN_ID/SPACE_ID are explicitly set (Phase D/E multi-brain).


def _namespace_segments() -> list[str]:
    """Path segments to insert for the current identity, or [] for legacy.

    - default brain, no space  -> []                       (legacy flat)
    - named brain              -> ["brains", <brain_id>]
    - + space scoped           -> ["brains", <brain_id>, "spaces", <space_id>]
    """
    bid = brain_id()
    sid = space_id()
    if bid == BRAIN_ID_DEFAULT and not sid:
        return []  # byte-for-byte legacy layout
    segs = ["brains", bid]
    if sid:
        segs += ["spaces", sid]
    return segs


def checkpoint_dir(kind: str = "brain_checkpoints", base: str = "data") -> str:
    """Return the checkpoint directory for ``kind`` under the current identity.

    Examples (kind="ctm_checkpoints"):
      default identity      -> "data/ctm_checkpoints"          (UNCHANGED)
      BRAIN_ID=alpha         -> "data/brains/alpha/ctm_checkpoints"
      +SPACE_ID=ideas        -> "data/brains/alpha/spaces/ideas/ctm_checkpoints"
    """
    segs = _namespace_segments()
    if segs:
        return os.path.join(base, *segs, kind)
    return os.path.join(base, kind)


def checkpoint_path(filename: str, kind: str = "brain_checkpoints",
                    base: str = "data") -> str:
    """Full path to a checkpoint file, identity-namespaced (legacy by default).

    Replaces hardcoded literals like
    ``"data/ctm_checkpoints/logic_brain_epoch_24.pth"`` with
    ``checkpoint_path("logic_brain_epoch_24.pth", "ctm_checkpoints")``.
    """
    return os.path.join(checkpoint_dir(kind, base), filename)


# ---------------------------------------------------------------------------
# Introspection (for /api/health, logs, debugging)
# ---------------------------------------------------------------------------

def identity_summary() -> dict:
    """Small dict describing this instance's identity — safe to log/expose."""
    return {
        "brain_id": brain_id(),
        "space_id": space_id() or None,
        "brain_role": brain_role(),
        "is_learner": is_learner(),
        "legacy_paths": _namespace_segments() == [],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(identity_summary(), indent=2))
    print("qdrant_url:", qdrant_url())
    print("ctm ckpt  :", checkpoint_path("logic_brain_epoch_24.pth", "ctm_checkpoints"))
    print("routing dir:", checkpoint_dir("brain_checkpoints"))

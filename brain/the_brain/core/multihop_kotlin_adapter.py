"""
Multihop -> KotlinGraph ingest adapter.

The PlanExecutor produces one HopResult per completed hop of a multi-hop
plan (`core/plan_schema.py`), each now carrying gate-derived learning
signals (`contract_pass`, `reward`). Nothing writes those hops into the
domain-agnostic episodic memory (`core/kotlin_graph.py`, coordinated by
`core/dual_graph.py`) yet. This module is that write path.

`record_plan(dual_graph, plan, executed, trace_id=...)` turns a completed
plan's hops (in completion order) into one `add_event` call per hop via
`dual_graph.record_event`.

NOTE — `record_plan` is NOT the live production write path any more. The
PlanExecutor enqueues (`enqueue_plan`), and the drain
(`core/multihop_diary_drain.py`) replays the queued events into the graph
directly. `record_plan` is kept for the tests and for non-swarm callers that
genuinely want a direct, in-process write into a dual_graph they own — do not
mistake it for how episodes reach memory in production.

Design notes
------------
- **State is a small, size-bounded fingerprint, not raw results.** Each
  hop's `state`/`next_state` carries `capability`, `completed_hops`,
  `plan_hops`, and a rolling `context_hash` (sha256 chain seeded from
  `plan.intent`). We deliberately never put raw hop results, tool output,
  or user text (beyond the intent hash) into state — KotlinGraph state
  dicts are hashed/indexed and persisted to disk (plan decision #4: size +
  PII).

- **`done` closes the episode; it is a *structural* boundary, not a
  success signal.** KotlinGraph has one global `current_episode_id`;
  every event with `done=False` stays in the current episode, and the
  first `done=True` event closes it and advances the counter. Because
  hops are written in completion order, `done=True` is set ONLY on the
  LAST event of THIS plan — otherwise a later plan's events would be
  folded into this plan's episode (or vice versa). This is orthogonal to
  whether the plan actually *succeeded*. If the write loop dies mid-plan
  (a `record_event` raises), we best-effort emit a synthetic closing
  event (`done=True`, `action="none::aborted"`, `metadata["aborted"]`)
  so the aborted episode does not stay OPEN and swallow the next plan's
  events.

- **Episode SUCCESS is a separate, richer signal carried in metadata.**
  KG-C3 (`KotlinGraph.is_episode_done`) is the 3-condition rule (last hop
  + validator passed if present + no pending hops) for whether an episode
  should be considered a *clean success* for pattern mining purposes. We
  compute it here as `metadata["episode_success"]` on the last event
  (with `pending_hops=0` since `executed` only contains completed hops),
  alongside a simpler `metadata["plan_ok"]` (all hops' `ok` truthy). Both
  are metadata annotations on the boundary event, never conflated with
  the `done` flag itself. `validator_present`/`validator_passed` are fed
  from the hop's *effective* contract_pass (explicit field, else derived
  via `contract_pass_from`) rather than a literal "verdict is a dict"
  check — a hard hop failure (`ok=False`) is a definite non-pass and must
  not fall into KG-C3's vacuous-truth-when-unverified branch; only a
  genuinely unverified *success* (`ok=True`, no usable verdict) is
  vacuously satisfied. The same effective value is what lands in
  `metadata["contract_pass"]` (it is the signal that actually drove
  reward/episode_success).

- **Episode purity under concurrency.** PlanExecutor runs up to 3 plans
  concurrently. `KotlinGraph.add_event` is thread-safe per call, but two
  plans interleaving their `add_event` calls would land in the SAME
  episode (there is one global `current_episode_id`). `record_plan` holds
  a module-level lock for the entire write of one plan's hops so each
  episode contains exactly one plan's events; the critical section does
  no I/O besides the `record_event` calls themselves.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.kotlin_graph import KotlinGraph
from core.plan_schema import contract_pass_from

logger = logging.getLogger(__name__)

# Guards the whole per-plan write so two concurrently-executing plans never
# interleave their events into a single KotlinGraph episode.
_WRITE_LOCK = threading.Lock()

# Serializes queue appends BETWEEN THREADS OF THIS PROCESS only, and guards
# the mkdir race. It does NOT and CANNOT provide the cross-process guarantee:
# brain-core runs TWO uvicorn worker PROCESSES appending to the same file, and
# a threading.Lock is per-interpreter. The cross-process atomicity comes from
# the OS file lock in `_locked_append` — not from this.
_ENQUEUE_LOCK = threading.Lock()

# data/ is the bind-mounted volume shared host<->container, same idiom as
# routing_matrix_autotrain.py's _QUEUE_PATH (core/ -> ../data).
#
# ONE LINE = ONE WHOLE EPISODE, and an episode can be LARGE: a 50-hop plan
# (MULTIHOP_REPEAT_MAX=50 is a real shipped code path) measures ~33 KB — 8x
# over PIPE_BUF (4096). So the usual "small appends are atomic" argument does
# NOT hold here; not even a single os.write() is reliably atomic at that size
# on every filesystem. That is precisely why `_locked_append` takes a real
# cross-process file lock instead of relying on write size.
#
# NOTE — this is only the DEFAULT. Prefer `resolve_queue_path()`, which reads
# MULTIHOP_DIARY_QUEUE at CALL time. If the queue IS pinned via that env var,
# it MUST be set IDENTICALLY on brain-core (which appends) AND brain-loops
# (which drains): the two halves talk to each other through this one file, and
# nothing else detects a mismatch. Pin it on one service only — or fat-finger
# one of the two paths — and the drain simply never sees an episode, silently
# and forever.
QUEUE_PATH = Path(
    os.environ.get(
        "MULTIHOP_DIARY_QUEUE",
        str(Path(__file__).resolve().parent.parent / "data"
            / "multihop_diary_queue.jsonl"),
    )
)


def resolve_queue_path(queue_path: Optional[Any] = None) -> Path:
    """Queue path, resolved at CALL time.

    The env var must therefore be set identically on every process that
    touches the queue (brain-core appends, brain-loops drains). Reading it at
    import time — as the QUEUE_PATH constant above does, kept for back-compat
    — would freeze whatever the environment happened to be when the module
    was first imported, which makes a brain-core/brain-loops path MISMATCH
    both invisible at runtime and untestable (a test's monkeypatch.setenv
    could not affect an already-imported module without an importlib.reload
    dance). Resolving here means the env var actually works.
    """
    if queue_path is not None:
        return Path(queue_path)
    env = os.environ.get("MULTIHOP_DIARY_QUEUE")
    return Path(env) if env else QUEUE_PATH

_DISABLE_VALUES = {"0", "false", "False"}

# Windows: open the queue fd in BINARY mode so the CRT does not translate our
# '\n' into '\r\n' (which would corrupt the drain's byte-offset math — see
# _locked_append). The flag does not exist on POSIX, where 0 makes it a no-op.
_O_BINARY = getattr(os, "O_BINARY", 0)

# Logged at most once: we could not take a cross-process lock on this platform.
_lock_warning_emitted = False
# Logged at most once WITH a traceback: the lock CALL failed. That failure is
# persistent (e.g. flock unsupported on a network/overlay FS), not transient,
# so an unguarded warning would emit a stack trace on every single enqueue.
_lock_failure_warning_emitted = False


def _write_all(fd: int, data: bytes) -> None:
    """os.write() may write FEWER bytes than requested — notably on ENOSPC it
    returns a SHORT COUNT instead of raising. A fragment left in the file would
    be permanently corrupt: the next writer appends straight after it, and the
    drain (which waits for a `\\n`) would glue the fragment onto the following
    episode into one unparseable line — losing TWO episodes, not one. So loop
    until everything is out. Looping is safe precisely because atomicity here
    is carried by the FILE LOCK, not by the number of syscalls."""
    n = 0
    while n < len(data):
        n += os.write(fd, data[n:])


def _locked_append(path: Path, data: bytes) -> None:
    """Append `data` to `path` as ONE atomic unit, safe across PROCESSES.

    Two defenses, both required (belt and braces):

    (a) A raw O_APPEND fd written via `_write_all`, instead of Python's
        buffered TextIOWrapper. A buffered `f.write()` may split into
        several write() syscalls at arbitrary boundaries — another process
        can land its bytes in the gap, tearing both lines.

    (b) A real OS-level exclusive file lock around that write (flock on
        POSIX / msvcrt.locking on Windows), so the append is serialized
        across processes REGARDLESS of line size. (a) alone is insufficient
        because our lines run ~33 KB, far past any atomic-append guarantee.

    The two platform paths are NOT equally strong. POSIX `flock` blocks
    indefinitely until the holder releases — that is the strong path, and it
    is what production (Linux container) runs. Windows `msvcrt.locking(LK_LOCK)`
    only blocks ~10s (10 retries at 1s) and then RAISES, which drops us into
    the degraded unlocked write below — so under heavy contention on the
    Windows dev host a torn line remains possible. Do not read the Windows
    path as a production guarantee; it is a dev-host convenience.

    If neither locking primitive is importable, fall back to the unlocked
    write and warn ONCE — degraded, but still the best available. Raises only
    on genuine I/O failure; the caller turns that into False.
    """
    global _lock_warning_emitted

    try:
        import fcntl  # POSIX (the container)

        def _acquire(fd: int) -> None:
            fcntl.flock(fd, fcntl.LOCK_EX)

        def _release(fd: int) -> None:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except ImportError:
        try:
            import msvcrt  # Windows (native dev host)

            # msvcrt.locking locks a byte range at the CURRENT file offset, so
            # both lock and unlock must be pinned to the SAME byte — we use
            # byte 0, giving every process one shared mutex. os.write() under
            # O_APPEND leaves the offset at EOF, hence the explicit lseek(0)
            # on release; without it we would unlock the wrong byte.
            def _acquire(fd: int) -> None:
                os.lseek(fd, 0, os.SEEK_SET)
                # LK_LOCK blocks (retries ~10x/1s) until the holder releases.
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

            def _release(fd: int) -> None:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except ImportError:
            if not _lock_warning_emitted:
                _lock_warning_emitted = True
                logger.warning(
                    "diary queue: neither fcntl nor msvcrt available — "
                    "cross-process append atomicity is NOT guaranteed on this "
                    "platform; concurrent writers may tear a line (= silently "
                    "lost episode)"
                )

            def _acquire(fd: int) -> None:
                return None

            def _release(fd: int) -> None:
                return None

    global _lock_failure_warning_emitted

    # O_BINARY is REQUIRED on Windows: without it the CRT opens the fd in text
    # mode and translates every '\n' we write into '\r\n'. The drain
    # (core/multihop_diary_drain.py) resumes from a BYTE offset and splits on
    # b'\n', so a silently-injected extra byte per line makes every offset it
    # computes wrong — episodes get mis-sliced or lost. Production is Linux
    # (where the flag does not exist and getattr yields 0, i.e. a no-op), so
    # this is a DEV-HOST correctness fix, not a production one.
    fd = os.open(
        str(path),
        os.O_APPEND | os.O_CREAT | os.O_WRONLY | _O_BINARY,
        0o644,
    )
    try:
        try:
            _acquire(fd)
        except OSError:
            # Lock unavailable (flock unsupported on a network/overlay FS, or
            # Windows LK_LOCK timed out). The write below is still our best
            # effort — do not lose the episode over a failed lock. This
            # condition is typically PERSISTENT, so only the first occurrence
            # carries a traceback; after that we stay quiet-ish rather than
            # dumping a stack trace on every enqueue.
            if not _lock_failure_warning_emitted:
                _lock_failure_warning_emitted = True
                logger.warning(
                    "diary queue: could not take file lock on %s — appending "
                    "unlocked; cross-process tears are possible from here on "
                    "(further occurrences logged without traceback)",
                    path, exc_info=True,
                )
            else:
                logger.warning(
                    "diary queue: appending unlocked to %s (lock unavailable)",
                    path,
                )
            _write_all(fd, data)
            return
        try:
            _write_all(fd, data)
        finally:
            try:
                _release(fd)
            except OSError:
                pass
    finally:
        os.close(fd)


def ingest_enabled() -> bool:
    """MULTIHOP_KOTLIN_INGEST env flag, default enabled ("1")."""
    val = os.environ.get("MULTIHOP_KOTLIN_INGEST", "1")
    return val not in _DISABLE_VALUES


def _get(hop: Any, name: str, default: Any = None) -> Any:
    """Duck-typed field access: works for dataclass-like objects (HopResult)
    and plain dicts alike."""
    if isinstance(hop, dict):
        return hop.get(name, default)
    return getattr(hop, name, default)


def _action_for(target: Optional[str], capability: Optional[str]) -> str:
    """target like 'openfang:brain-coder' -> kind='openfang', rest='brain-coder'.
    None/empty target -> kind='none', rest=''."""
    cap = capability or ""
    if target:
        if ":" in target:
            kind, rest = target.split(":", 1)
        else:
            kind, rest = target, ""
    else:
        kind, rest = "none", ""
    return f"{kind}:{rest}:{cap}"


def _effective_contract_pass(ok: bool, contract_pass: Optional[bool], verdict: Any) -> Optional[bool]:
    """The hop's gate verdict: the explicit `contract_pass` field if the hop
    carries one, else derived via `contract_pass_from` (which itself maps
    ok=False -> False regardless of any validator, and ok=True with no/bad
    verdict -> None = unverified)."""
    if contract_pass is not None:
        return contract_pass
    return contract_pass_from(bool(ok), verdict if isinstance(verdict, dict) else None)


def _reward_for(reward: Any, effective_contract_pass: Optional[bool]) -> float:
    if reward is not None:
        try:
            return float(reward)
        except (TypeError, ValueError):
            pass
    if effective_contract_pass is True:
        return 1.0
    if effective_contract_pass is False:
        return -1.0
    return 0.0


def _close_aborted_episode(
    dual_graph: Any,
    plan_id: str,
    trace_id: str,
    completed_hops: int,
    total: int,
    context_hash: str,
    task_class_id: str = "",
) -> None:
    """Best-effort synthetic done=True event so a mid-write failure does not
    leave the KotlinGraph episode OPEN (which would fold the NEXT plan's
    events into this plan's episode). If this also fails, log and give up."""
    try:
        state = {
            "capability": "",
            "completed_hops": completed_hops,
            "plan_hops": total,
            "context_hash": context_hash,
        }
        next_state = dict(state)
        metadata: Dict[str, Any] = {
            "source": "multihop",
            "plan_id": plan_id,
            "trace_id": trace_id,
            "aborted": True,
            "episode_success": False,
            "plan_ok": False,
        }
        if task_class_id:
            metadata["task_class_id"] = task_class_id
        dual_graph.record_event(
            state,
            "none::aborted",
            next_state,
            -1.0,
            True,
            metadata=metadata,
        )
    except Exception:
        logger.warning(
            "record_plan: could not close aborted episode for plan %s — "
            "episode stays open, next plan's events may join it",
            plan_id,
            exc_info=True,
        )


def build_episode(
    plan: Any, executed: Optional[Dict[str, Any]], *,
    trace_id: str = "", task_class_id: str = "",
) -> Dict[str, Any]:
    """PURE: turn one completed plan's hops into the episode dict this
    module writes — either directly via `record_plan`'s `dual_graph.
    record_event(**event)` calls, or as a queue line via `enqueue_plan`.

    No I/O, no locking, never touches a dual_graph. Same event order and
    semantics `record_plan` used to build inline: `done=True` only on the
    last event, `episode_success`/`plan_ok` only in the last event's
    metadata, `task_class_id` in every event's metadata only when
    non-empty. Safe to call with `executed` falsy — yields `events: []`.
    """
    plan_id = getattr(plan, "plan_id", "") or ""
    eff_trace_id = trace_id or getattr(plan, "trace_id", "") or ""

    events: List[Dict[str, Any]] = []
    if executed:
        items = list(executed.items())
        total = len(items)
        intent = getattr(plan, "intent", "") or ""

        h = hashlib.sha256(intent.encode()).hexdigest()[:16]
        all_ok = True

        for i, (step_id, hop) in enumerate(items):
            ok = bool(_get(hop, "ok", False))
            contract_pass = _get(hop, "contract_pass", None)
            reward_field = _get(hop, "reward", None)
            verdict = _get(hop, "validator_verdict", None)
            capability = _get(hop, "capability", None)
            target = _get(hop, "target", None)

            all_ok = all_ok and ok

            action = _action_for(target, capability)
            effective_contract_pass = _effective_contract_pass(ok, contract_pass, verdict)
            reward = _reward_for(reward_field, effective_contract_pass)

            is_last = i == total - 1
            next_h = hashlib.sha256(
                (h + action + ("ok" if ok else "fail")).encode()
            ).hexdigest()[:16]

            state = {
                "capability": capability or "",
                "completed_hops": i,
                "plan_hops": total,
                "context_hash": h,
            }
            next_state = {
                "capability": capability or "",
                "completed_hops": i + 1,
                "plan_hops": total,
                "context_hash": next_h,
            }

            metadata: Dict[str, Any] = {
                "source": "multihop",
                "plan_id": plan_id,
                "trace_id": eff_trace_id,
                "step_id": step_id,
                "capability": capability or "",
                "target": target,
                "ok": ok,
                # the COMPUTED effective gate verdict — the value that
                # actually drove reward/episode_success
                "contract_pass": effective_contract_pass,
            }
            if task_class_id:
                metadata["task_class_id"] = task_class_id

            done = is_last
            if is_last:
                # validator_present widens beyond "verdict is a dict": a
                # hard hop failure (ok=False) is a DEFINITE non-pass, not
                # an ambiguous/unverified case, so it must not fall into
                # KG-C3's vacuous-truth-when-unverified branch. Both
                # effective_contract_pass=False (from a failing verdict
                # OR from ok=False) and =True (verdict passed) count as
                # "a validator ran"; only None (truly unverified success)
                # is vacuously satisfied.
                validator_present = effective_contract_pass is not None
                validator_passed = effective_contract_pass is True
                metadata["episode_success"] = KotlinGraph.is_episode_done(
                    is_last_hop=True,
                    validator_present=validator_present,
                    validator_passed=validator_passed,
                    pending_hops=0,
                )
                metadata["plan_ok"] = all_ok

            events.append({
                "state": state,
                "action": action,
                "next_state": next_state,
                "reward": reward,
                "done": done,
                "metadata": metadata,
            })
            h = next_h

    return {
        "v": 1,
        "plan_id": plan_id,
        "trace_id": eff_trace_id,
        "task_class_id": task_class_id,
        "ts": time.time(),
        "events": events,
    }


def record_plan(
    dual_graph: Any, plan: Any, executed: Optional[Dict[str, Any]], *,
    trace_id: str = "", task_class_id: str = "",
) -> int:
    """Write one KotlinGraph event per completed hop of `plan`.

    Returns the number of events written: 0 on no-op (flag off, no
    dual_graph, empty executed); partial count on mid-loop failure (plus a
    best-effort synthetic closing event so the episode does not stay open).
    Never raises.
    """
    if not ingest_enabled():
        return 0
    if dual_graph is None:
        return 0
    if not executed:
        return 0

    written = 0
    with _WRITE_LOCK:
        plan_id = ""
        eff_trace_id = trace_id
        episode_closed = False
        total = 0
        h = ""
        try:
            plan_id = getattr(plan, "plan_id", "") or ""
            eff_trace_id = trace_id or getattr(plan, "trace_id", "") or ""
            intent = getattr(plan, "intent", "") or ""
            h = hashlib.sha256(intent.encode()).hexdigest()[:16]

            episode = build_episode(
                plan, executed, trace_id=trace_id, task_class_id=task_class_id,
            )
            events = episode["events"]
            total = len(events)

            for event in events:
                dual_graph.record_event(
                    event["state"],
                    event["action"],
                    event["next_state"],
                    event["reward"],
                    event["done"],
                    metadata=event["metadata"],
                )
                written += 1
                if event["done"]:
                    episode_closed = True
                h = event["next_state"]["context_hash"]

        except Exception:
            logger.warning(
                "record_plan: ingest failed after %d events (plan %s)",
                written,
                plan_id,
                exc_info=True,
            )
            # Episode purity: if we wrote any events but never the done=True
            # boundary, the episode is still OPEN — close it (still under the
            # lock, so no other plan can interleave before the close).
            if written > 0 and not episode_closed:
                _close_aborted_episode(
                    dual_graph, plan_id, eff_trace_id, written, total, h,
                    task_class_id=task_class_id,
                )

    return written


def enqueue_plan(
    plan: Any, executed: Optional[Dict[str, Any]], *,
    trace_id: str = "", task_class_id: str = "",
    queue_path: Optional[Any] = None,
) -> bool:
    """Append ONE JSON line (the `build_episode` dict) to the diary queue.

    Phase 1 of the swarm fix: brain-core (2 uvicorn workers, no background
    loops, nothing ever calls dual_graph.save()) enqueues here instead of
    writing straight into its own doomed in-memory graph. A later drain
    (brain-loops, the only process that persists) replays these lines. Same
    idiom as `routing_matrix_autotrain.py::maybe_autotrain`: hook appends,
    separate drain worker consumes.

    ONE LINE = ONE WHOLE EPISODE, and it can be LARGE (~33 KB for a 50-hop
    repeat-plan — see QUEUE_PATH). This queue is the SOLE path to
    persistence, so a torn line is a silently lost episode. The append
    therefore goes through `_locked_append`: a cross-process file lock plus
    a short-write-safe raw write. Plain buffered `open("a").write()` is NOT
    safe here — brain-core is two processes, and the lines are far past any
    atomic-append size guarantee.

    True on success; False on flag-off, empty `executed`, or any failure
    (bad path, disk full, ...). Never raises — the executor calls this in a
    `finally` block.
    """
    if not ingest_enabled():
        return False
    if not executed:
        return False
    try:
        episode = build_episode(
            plan, executed, trace_id=trace_id, task_class_id=task_class_id,
        )
        line = json.dumps(episode, ensure_ascii=False, default=str)
        data = (line + "\n").encode("utf-8")
        # CALL-time resolution (not the import-time QUEUE_PATH constant): the
        # env var is what pins this file to the shared volume in the swarm, and
        # brain-core/brain-loops must land on the SAME file. See
        # resolve_queue_path.
        path = resolve_queue_path(queue_path)
        # The threading.Lock only serializes THIS process's threads (and the
        # mkdir race). Cross-process safety is _locked_append's file lock.
        with _ENQUEUE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            _locked_append(path, data)
        return True
    except Exception:
        logger.warning(
            "enqueue_plan: failed to enqueue plan %s",
            getattr(plan, "plan_id", ""),
            exc_info=True,
        )
        return False

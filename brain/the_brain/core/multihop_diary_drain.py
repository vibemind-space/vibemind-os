"""
Multihop diary queue -> dual_graph DRAIN (the read side of the swarm fix).

WHY this module exists
-----------------------
Every executed multi-hop plan is meant to become ONE episode in the episodic
diary (`KotlinGraph` inside `DualGraph`). In the production Docker Swarm this
was measurably broken:

- `brain-core` (the HTTP service) runs **2 uvicorn worker processes** -> two
  separate in-memory `dual_graph` instances, neither of which is "the"
  memory.
- `brain-core` sets `BRAIN_BACKGROUND_LOOPS=0`. In `web/brain_server.py` the
  `MemoryConsolidator` -- the ONLY caller of `dual_graph.save()` -- is gated
  by `if _loops_enabled(): consolidator.start()`, so on brain-core it never
  starts. Nothing ever persists.
- Swarm reschedules brain-core tasks constantly -> whatever sits in that
  in-memory graph evaporates on every restart.
- `brain-loops` (a separate container, `BRAIN_BACKGROUND_LOOPS=1`,
  `BRAIN_ROLE=learner`) DOES run the consolidator and DOES persist -- but it
  builds its own independent `dual_graph` and never sees a single hop,
  because hops are executed on brain-core's side.

The fix mirrors this repo's proven `routing_matrix_autotrain.py` ->
`production/autotrain_drain.py` pattern: the write side
(`core/multihop_kotlin_adapter.enqueue_plan`, built in the previous task)
appends each completed plan as ONE JSONL line to a queue file in the shared
volume. THIS module is the read side: it runs inside the loop-process
(`brain-loops` / `brain_loops_worker.py`, wherever `_loops_enabled()` is
true) and replays those lines into the `dual_graph` that process actually
persists. brain-core only ever appends; it never touches the graph that
gets saved.

Offset / partial-line rules
----------------------------
The queue is append-only JSONL, written under a cross-process file lock
(`_locked_append` in `multihop_kotlin_adapter.py`) but a reader can still be
mid-scan while a writer is mid-append -- the lock only serializes *complete*
appends against each other, it does not stop a concurrent *read* from
observing a write in progress.

1. **Trailing partial line.** We track a byte offset (in a sibling
   `<queue>.state.json` file) and read everything from there to EOF. Any
   bytes AFTER the last `\n` in that chunk are, by definition, a write that
   has not finished yet (or never will, e.g. a torn write) -- we never parse
   them and never advance the offset past them. They are simply re-read,
   complete, on the next cycle once the writer finishes its `\n`.
2. **Idempotent.** The offset is a monotonically advancing watermark; a
   second drain with nothing new past it does no work and writes nothing.
3. **Rotation.** Size alone is NOT a rotation signal: a queue that is
   truncated and then refilled can coincidentally reach the same (or a
   larger) size than the offset we stored, and we would then happily resume
   mid-file and skip real episodes. So we also fingerprint the file's HEAD
   (`head_sha`: sha256 of its first `min(256, size)` bytes) into the state
   file. We reset the offset to 0 if the size is smaller than the stored
   offset OR the current head_sha differs from the stored one — the head
   bytes change iff the file was replaced/rotated, at any size.
4. **A permanently broken LINE is skipped.** Two flavours: a line that fails
   `json.loads`, and a line that is valid JSON but structurally unusable
   (an event missing `state`, a non-numeric `reward`, ...) -- see
   `_episode_problem`. Both are logged and SKIPPED, offset advancing past
   them. This distinction matters enormously: without the structural check,
   such a line would land in rule 5 below and park the offset in front of
   itself FOREVER, starving every good episode queued behind it.
5. **A failing GRAPH stops the cycle.** If `record_event` raises on an
   episode we already validated, the problem is the graph, not the line: we
   log a warning and STOP right there. The offset is NOT advanced past that
   episode, so it is retried whole next cycle. Whatever was cleanly drained
   earlier in the same cycle is still persisted and committed.
   **Backstop:** if the SAME offset fails `_MAX_STALL` times in a row
   (tracked as `stall_offset`/`stall_count` in the state file) we log an
   ERROR, skip that line and move on. That deliberately trades one lost
   episode for an unblocked queue -- an unforeseen *permanent* record_event
   failure would otherwise cost us every future episode, which is far worse.
6. **Never raises.** `drain_once` is wrapped end to end; any unexpected
   failure yields `{"episodes": 0, "events": 0, "offset": 0}` rather than
   propagating into the caller's (daemon-thread) loop.

Durability: PERSIST-THEN-COMMIT + IDEMPOTENT REPLAY
----------------------------------------------------
The state file's own write is atomic (tmp + `os.replace`), but do not mistake
that for the durability story -- it only means the offset file is never torn.
The real property comes from two things working TOGETHER:

- **Persist-then-commit** (`_persist`): we call `dual_graph.save('memory')`
  BEFORE writing the advanced offset, and refuse to advance if the save
  fails. Committing first was a silent data-loss bug: the drain advances the
  offset every 30s, but `MemoryConsolidator` (the only other saver) persists
  only every 300s -- a 10x window in which a swarm reschedule would leave the
  state file claiming episodes were "drained" that never reached the disk.
- **Idempotent replay** (`_seen_plan_ids`): before replaying, we skip any
  episode whose `plan_id` is already in the graph. This is what MAKES
  persist-then-commit safe -- the reordering means a crash can now leave
  episodes persisted but not committed, so they WILL be re-read, and
  re-reading must be a harmless no-op rather than a duplicate.

Neither half is sufficient alone. Note also that `DualGraph.save` ->
`KotlinGraph.save` writes with a plain `open(path, 'w')` (no tmp+rename), so
it is NOT atomic; `_SAVE_LOCK` serializes the drain's own saves, but the
MemoryConsolidator saves the same graph from its own thread without it.

Replay strategy
----------------
Each queue line is exactly the `build_episode(...)` dict `enqueue_plan`
wrote: `events` is already a list of
`{"state", "action", "next_state", "reward", "done", "metadata"}` dicts in
completion order -- precisely the positional shape `DualGraph.record_event`
takes. We replay those dicts directly (`dual_graph.record_event(state,
action, next_state, reward, done, metadata=metadata)`) rather than
reconstructing a fake `plan`/`executed` pair and going back through
`record_plan`/`build_episode` a second time: the queue line already IS the
built episode, so re-deriving it would just be redundant work (and a second
place that could silently disagree with the first). Because the drain runs
single-threaded, single-process, and processes one whole queue line (= one
whole plan) at a time, episode purity (one KotlinGraph episode == one plan)
falls out structurally -- no lock is needed here the way `record_plan`
needs `_WRITE_LOCK` for concurrent in-process writers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Union

from core.multihop_kotlin_adapter import resolve_queue_path

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

_EMPTY_RESULT: Dict[str, int] = {"episodes": 0, "events": 0, "offset": 0}

# How many leading bytes of the queue identify "this file, not a new one".
_HEAD_BYTES = 256

# Rule-5 backstop: how often we may fail to replay THE SAME line before we
# give up on it, skip it and move on. See `drain_once`.
_MAX_STALL = 5

# The queue is never rotated (rotation is only DETECTED, never performed), so
# it grows without bound. Warn once we are past this — nobody watches a file
# that silently becomes a disk-filler.
_QUEUE_WARN_BYTES = 100 * 1024 * 1024  # 100 MB

# Serializes OUR dual_graph.save() calls. NOTE: DualGraph.save -> KotlinGraph
# .save writes with a plain `open(path, 'w')` + json.dump — it is NOT atomic
# (no tmp+rename), so two concurrent savers can interleave and leave a
# truncated/corrupt JSON file. This lock only protects drain-vs-drain. The
# MemoryConsolidator calls dual_graph.save('memory') from ITS OWN thread in
# the same process and does not take this lock, so drain-vs-consolidator
# remains unprotected — flagged for a separate decision.
_SAVE_LOCK = threading.Lock()

# Structural contract of one queued event (what DualGraph.record_event needs).
_REQUIRED_EVENT_KEYS = ("state", "action", "next_state", "reward", "done")


def _default_state_path(queue_path: Path) -> Path:
    return Path(str(queue_path) + ".state.json")


def _seen_plan_ids(dual_graph: Any) -> set:
    """Every multihop plan_id ALREADY present in the graph.

    This is what makes replay idempotent (and therefore makes
    persist-then-commit safe): after a crash we may legitimately re-read
    lines we already ingested, and re-adding them would silently duplicate
    the diary. The graph itself is the source of truth — we derive the set
    from it rather than trusting any bookkeeping we wrote earlier."""
    out: set = set()
    try:
        kg = getattr(dual_graph, "kotlingraph", None)
        for e in (getattr(kg, "events", None) or []):
            md = getattr(e, "metadata", None) or {}
            if md.get("source") == "multihop":
                pid = md.get("plan_id")
                if pid:
                    out.add(pid)
    except Exception:
        logger.warning("multihop_diary_drain: could not read existing "
                        "plan_ids from the graph; replay may duplicate",
                        exc_info=True)
    return out


def _episode_problem(episode: Any) -> str:
    """Structural validation. Returns "" if the episode is replayable, else a
    short reason.

    WHY this exists: a JSON-VALID but schema-corrupt line (say, an event with
    no "state") would make record_event raise — and rule 5 reads every
    record_event failure as "transient, retry next cycle", which would park
    the offset in front of that line FOREVER and starve every good episode
    behind it. Validating up front lets us tell a permanently-broken LINE
    (skip it, rule 4) apart from a sick GRAPH (stop, rule 5)."""
    if not isinstance(episode, dict):
        return "episode is not an object"
    events = episode.get("events")
    if not isinstance(events, list):
        return "'events' is not a list"
    if not events:
        return "'events' is empty"
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            return f"event {i} is not an object"
        for key in _REQUIRED_EVENT_KEYS:
            if key not in ev:
                return f"event {i} is missing '{key}'"
        if not isinstance(ev["state"], dict):
            return f"event {i}: 'state' is not an object"
        if not isinstance(ev["next_state"], dict):
            return f"event {i}: 'next_state' is not an object"
        if not isinstance(ev["action"], str):
            return f"event {i}: 'action' is not a string"
        if isinstance(ev["reward"], bool) or not isinstance(ev["reward"], (int, float)):
            return f"event {i}: 'reward' is not a number"
        if not isinstance(ev["done"], bool):
            return f"event {i}: 'done' is not a bool"
        md = ev.get("metadata")
        if md is not None and not isinstance(md, dict):
            return f"event {i}: 'metadata' is neither an object nor null"
    return ""


def _persist(dual_graph: Any) -> bool:
    """Save the graph to disk — the SAME call MemoryConsolidator._phase_persist
    makes (`dual_graph.save('memory')`, core/memory_consolidation.py:580).

    This is the "persist" half of persist-then-commit: the offset may only
    advance AFTER the episodes behind it are actually on disk. Never raises;
    False means "not persisted -> do not commit the offset"."""
    try:
        with _SAVE_LOCK:
            dual_graph.save('memory')
        return True
    except Exception:
        logger.warning("multihop_diary_drain: persisting the graph failed — "
                        "NOT advancing the offset; the episodes stay queued "
                        "and will be retried (replay is idempotent)",
                        exc_info=True)
        return False


def _head_sha(queue_path: Path, offset: int) -> str:
    """Fingerprint of the queue's first `min(_HEAD_BYTES, offset)` bytes.

    This is the ROTATION signal. Size cannot serve that role: a queue that is
    truncated and refilled may land at a coincidentally identical size, and
    resuming from the stale offset would then silently skip real episodes.
    The head bytes, by contrast, change whenever the file is replaced.

    We deliberately hash a prefix of the bytes we have ALREADY CONSUMED
    (bounded by `offset`), not of the file's current size. Under an
    append-only queue the consumed prefix is IMMUTABLE, so the fingerprint is
    stable across cycles by construction. Hashing `min(_HEAD_BYTES, size)`
    instead would be unstable whenever the file is still shorter than
    _HEAD_BYTES: the next append would change those head bytes, we would read
    that as a rotation, reset to 0 and REPLAY already-drained episodes twice.

    offset<=0 -> "" (nothing consumed yet, so there is nothing to protect and
    no reset can be warranted). Unreadable -> "" (unknown; never forces a
    spurious reset)."""
    n = min(_HEAD_BYTES, int(offset))
    if n <= 0:
        return ""
    try:
        with queue_path.open("rb") as f:
            return hashlib.sha256(f.read(n)).hexdigest()
    except Exception:
        return ""


def _load_state(state_path: Path) -> Dict[str, Any]:
    """Best-effort read of the drain's own progress file. Missing/corrupt
    -> a fresh zero state (never raises)."""
    default: Dict[str, Any] = {
        "offset": 0,
        "episodes_drained": 0,
        "events_written": 0,
        # Lines we CONSUMED (offset advanced past them) but never replayed:
        # corrupt JSON, structurally-unusable episodes, and rule-5-backstop
        # abandonments. They are not backlog and they are not drained — without
        # their own counter the books cannot balance, and a reader deriving
        # "pending = enqueued - drained" would overstate the backlog forever.
        # A non-zero value here is an ALARM: episodes were thrown away.
        "lines_skipped": 0,
        "last_plan_id": "",
        "last_ts": 0.0,
        "head_sha": "",
        # Rule-5 backstop bookkeeping: how many cycles in a row a replay has
        # failed at `stall_offset`. Reset whenever we make progress.
        "stall_offset": -1,
        "stall_count": 0,
    }
    try:
        if not state_path.exists():
            return default
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return default
        default.update({k: raw[k] for k in default if k in raw})
        return default
    except Exception:
        logger.warning("multihop_diary_drain: state file %s unreadable; "
                        "starting fresh", state_path, exc_info=True)
        return default


def _write_state(state_path: Path, state: Dict[str, Any]) -> None:
    """The drain is the ONLY writer of this file (a later task lets
    brain-core READ it). Best-effort; a failed write here must not turn
    into a crashed drain cycle."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(state_path) + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(state_path)
    except Exception:
        logger.warning("multihop_diary_drain: could not write state file %s",
                        state_path, exc_info=True)


def _replay_episode(dual_graph: Any, episode: Dict[str, Any]) -> int:
    """Replay one episode's events into `dual_graph`, in order. Returns the
    number of events successfully written. Raises on the first failing
    `record_event` call -- the caller (`drain_once`) decides what that means
    for the offset (rule 5: do not advance past this episode)."""
    written = 0
    for event in episode.get("events") or []:
        dual_graph.record_event(
            event["state"],
            event["action"],
            event["next_state"],
            event["reward"],
            event["done"],
            metadata=event.get("metadata"),
        )
        written += 1
    return written


def drain_once(
    dual_graph: Any, *,
    queue_path: Optional[PathLike] = None,
    state_path: Optional[PathLike] = None,
) -> Dict[str, int]:
    """Drain whatever is new in the diary queue into `dual_graph`, once.

    Returns `{"episodes": int, "events": int, "offset": int}` describing
    THIS cycle (not cumulative totals -- those live in the persisted state
    file). Never raises; see module docstring rules 1-6.
    """
    try:
        # CALL-time resolution, exactly like the write side (enqueue_plan).
        # Both halves MUST land on the same file; if the drain froze its path
        # at import time while the appender read the env var (or vice versa),
        # a MULTIHOP_DIARY_QUEUE set on only one of brain-core/brain-loops
        # would leave the drain watching a file nobody writes — silently, and
        # with no test able to catch it.
        q_path = resolve_queue_path(queue_path)
        s_path = Path(state_path) if state_path is not None else _default_state_path(q_path)

        if not q_path.exists():
            return dict(_EMPTY_RESULT)

        prev = _load_state(s_path)
        offset = int(prev.get("offset", 0) or 0)

        file_size = q_path.stat().st_size
        prev_head = prev.get("head_sha", "") or ""
        # Fingerprint the SAME prefix the stored head_sha covered, i.e. one
        # bounded by the offset we are about to resume from.
        current_head = _head_sha(q_path, offset)

        # Rule 3: rotated/truncated out from under us. Two independent
        # signals, because size alone is insufficient — a truncate-and-refill
        # can coincidentally reach the same size, and we would resume from a
        # stale offset in the middle of a BRAND NEW file, silently skipping
        # every episode before it. The head fingerprint catches exactly that.
        if file_size < offset or (prev_head and current_head != prev_head):
            offset = 0
            # The cumulative counters describe the OLD file, which no longer
            # exists. Carrying them across a rotation makes every number
            # derived from them lie: `episodes_drained` would keep climbing
            # against a queue that restarted at line 0, so a reader comparing
            # it to the queue's line count would see a phantom surplus (and
            # `max(0, ...)`-style clamping would HIDE a real backlog). Reset
            # them with the file they describe.
            prev["episodes_drained"] = 0
            prev["events_written"] = 0
            prev["lines_skipped"] = 0

        with q_path.open("rb") as f:
            f.seek(offset)
            chunk = f.read()

        last_nl = chunk.rfind(b"\n")
        if last_nl == -1:
            # No complete line at all past the current offset (rule 1: pure
            # partial-write tail, or genuinely nothing new).
            complete = b""
        else:
            complete = chunk[: last_nl + 1]

        if file_size > _QUEUE_WARN_BYTES:
            # Rotation is only DETECTED here, never PERFORMED — so nothing
            # ever shrinks this file. Say so out loud before it eats the disk.
            logger.warning(
                "multihop_diary_drain: queue %s is %.1f MB — it is never "
                "rotated, only appended to; consider truncating it (the drain "
                "handles rotation) or adding a rotation policy",
                q_path, file_size / (1024 * 1024),
            )

        cumulative_offset = offset
        episodes_this = 0
        events_this = 0
        skipped_this = 0
        last_plan_id = prev.get("last_plan_id", "")
        last_ts = prev.get("last_ts", 0.0)
        stalled_at = -1          # offset of a rule-5 failure in THIS cycle

        # Fix 1a: the graph is the source of truth for what is already in it.
        seen = _seen_plan_ids(dual_graph)
        # NB: no `or -1` fallback here — offset 0 is a perfectly valid stall
        # position (it is where the FIRST queue line lives), and `0 or -1`
        # would silently turn it into "no stall", so the backstop could never
        # fire for it.
        try:
            prev_stall_offset = int(prev.get("stall_offset", -1))
        except (TypeError, ValueError):
            prev_stall_offset = -1
        try:
            prev_stall_count = int(prev.get("stall_count", 0))
        except (TypeError, ValueError):
            prev_stall_count = 0

        if complete:
            # `complete` always ends in b"\n" -> the final split element is
            # the empty tail; drop it.
            raw_lines = complete.split(b"\n")[:-1]

            for raw_line in raw_lines:
                line_len = len(raw_line) + 1  # +1 for the stripped '\n'
                stripped = raw_line.strip()
                if not stripped:
                    cumulative_offset += line_len
                    continue

                try:
                    episode = json.loads(stripped.decode("utf-8"))
                except Exception:
                    # Rule 4: corrupt line -> warn, skip, keep going. The
                    # offset still advances past it -- a permanently broken
                    # line must not stall the queue forever.
                    logger.warning(
                        "multihop_diary_drain: corrupt queue line at "
                        "offset %d in %s; skipping",
                        cumulative_offset, q_path, exc_info=True,
                    )
                    cumulative_offset += line_len
                    skipped_this += 1
                    continue

                # Rule 4 (extended): JSON-valid but structurally unusable.
                # A permanently malformed LINE must be skipped, never retried
                # forever — otherwise it starves every good episode behind it.
                problem = _episode_problem(episode)
                if problem:
                    logger.warning(
                        "multihop_diary_drain: unusable episode %r at offset "
                        "%d in %s (%s); skipping the line",
                        episode.get("plan_id") if isinstance(episode, dict) else None,
                        cumulative_offset, q_path, problem,
                    )
                    cumulative_offset += line_len
                    skipped_this += 1
                    continue

                plan_id = episode.get("plan_id") or ""

                # Fix 1a: already in the graph (e.g. we persisted it, then
                # crashed before committing the offset). Re-adding it would
                # duplicate the diary. Advance past it — it IS drained.
                if plan_id and plan_id in seen:
                    logger.debug(
                        "multihop_diary_drain: plan %r already in the graph; "
                        "skipping replay (idempotent)", plan_id,
                    )
                    episodes_this += 1
                    last_plan_id = plan_id or last_plan_id
                    last_ts = episode.get("ts", last_ts)
                    cumulative_offset += line_len
                    continue

                # Rule-5 backstop: we have already failed on THIS line
                # _MAX_STALL times. record_event is evidently never going to
                # take it. Losing one episode beats losing every future one.
                if (cumulative_offset == prev_stall_offset
                        and prev_stall_count >= _MAX_STALL):
                    logger.error(
                        "multihop_diary_drain: giving up on episode %r at "
                        "offset %d in %s after %d failed replays — SKIPPING "
                        "it (one episode lost, queue unblocked)",
                        plan_id, cumulative_offset, q_path, prev_stall_count,
                    )
                    cumulative_offset += line_len
                    skipped_this += 1
                    prev_stall_offset, prev_stall_count = -1, 0
                    continue

                try:
                    events_this += _replay_episode(dual_graph, episode)
                except Exception:
                    # Rule 5: the GRAPH failed (the line is structurally fine,
                    # we validated it above) -- STOP here, do not advance past
                    # this episode, retry it whole next cycle. Whatever this
                    # cycle already drained cleanly is still persisted+
                    # committed below.
                    logger.warning(
                        "multihop_diary_drain: replay failed for plan %r "
                        "at offset %d in %s; stopping this cycle, will "
                        "retry",
                        plan_id, cumulative_offset, q_path,
                        exc_info=True,
                    )
                    stalled_at = cumulative_offset
                    break

                episodes_this += 1
                if plan_id:
                    seen.add(plan_id)
                last_plan_id = plan_id or last_plan_id
                last_ts = episode.get("ts", last_ts)
                cumulative_offset += line_len

        # --- Fix 1b: PERSIST, THEN COMMIT ------------------------------------
        # The offset may only move past episodes that are actually ON DISK.
        # Committing first (as we used to) meant: DiaryDrain marks 30s of
        # episodes "drained", MemoryConsolidator only saves every 300s, the
        # swarm reschedules in between -> the state file says "consumed" but
        # the graph on disk never had them. Silently gone. So we save here,
        # and on failure we simply do not advance — the episodes stay queued
        # and the next cycle retries them (harmless, replay is idempotent).
        if episodes_this > 0 and not _persist(dual_graph):
            return {
                "episodes": episodes_this,
                "events": events_this,
                "offset": offset,          # NOT committed
            }

        if stalled_at >= 0:
            stall_count = (prev_stall_count + 1
                            if stalled_at == prev_stall_offset else 1)
        else:
            stall_count = 0

        new_state = {
            "offset": cumulative_offset,
            "episodes_drained": int(prev.get("episodes_drained", 0) or 0) + episodes_this,
            "events_written": int(prev.get("events_written", 0) or 0) + events_this,
            "lines_skipped": int(prev.get("lines_skipped", 0) or 0) + skipped_this,
            "last_plan_id": last_plan_id,
            "last_ts": last_ts,
            # Fingerprint the prefix we have now consumed — that is exactly
            # the region the next cycle will re-check for rotation.
            "head_sha": _head_sha(q_path, cumulative_offset),
            "stall_offset": stalled_at if stalled_at >= 0 else -1,
            "stall_count": stall_count,
        }
        _write_state(s_path, new_state)

        return {
            "episodes": episodes_this,
            "events": events_this,
            "offset": cumulative_offset,
        }
    except Exception:
        logger.warning("multihop_diary_drain: drain_once failed unexpectedly",
                        exc_info=True)
        return dict(_EMPTY_RESULT)


class DiaryDrain:
    """Daemon-thread wrapper: calls `drain_once` on a fixed interval.

    Started only where `_loops_enabled()` is true (brain-loops /
    `brain_loops_worker.py`, or a native single-process run) -- see
    `web/brain_server.py`. brain-core never starts this; it only enqueues.
    """

    def __init__(
        self, dual_graph: Any, interval_s: float = 30.0, *,
        queue_path: Optional[PathLike] = None,
        state_path: Optional[PathLike] = None,
    ) -> None:
        self.dual_graph = dual_graph
        self.interval_s = interval_s
        self.queue_path = queue_path
        self.state_path = state_path
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                drain_once(
                    self.dual_graph,
                    queue_path=self.queue_path,
                    state_path=self.state_path,
                )
            except Exception:
                logger.warning("DiaryDrain: cycle failed unexpectedly",
                                exc_info=True)
            self._stop_event.wait(self.interval_s)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="DiaryDrain", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

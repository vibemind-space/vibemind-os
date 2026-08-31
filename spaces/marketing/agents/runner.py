"""Standalone Redis-stream runner for MarketingBackendAgent.

Consumes events from `events:tasks:marketing` via XREADGROUP, resolves the
event_type to a tool function on MarketingBackendAgent, normalises params,
invokes the tool, publishes the result back on `events:status:marketing`
via XADD.

Why standalone:
  The voice/swarm Python process resolves `spaces.*` through a submodule-
  internal symlink (vibemind-os/voice/python/spaces -> vibemind-os/spaces).
  Our marketing space lives at the REPO ROOT (spaces/marketing/), NOT
  inside the submodule, so it is unreachable from voice/swarm without
  editing files in vibemind-os/ (which would be lost on submodule reset).

  This runner sidesteps that entirely by running as its own process,
  scheduled by Vibemind.debug.ps1 PHASE 4.5 next to Worker A and B.

CUT-OVER RULE:
  See spaces/marketing/agents/marketing_agent.py module docstring. The
  consumer-group name MARKETING_CONSUMER_GROUP is shared with any
  future voice-swarm consumer; running BOTH at once = double-execute.

Env:
  REDIS_URL                    default redis://localhost:6379/0
  MARKETING_RUNNER_CONSUMER    default hostname
  MARKETING_RUNNER_BLOCK_MS    default 5000
  MARKETING_RUNNER_LOG_LEVEL   default INFO

Run:
  python -m spaces.marketing.agents.runner

Stop with Ctrl-C / SIGTERM.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import signal
import socket
import sys
import time
from typing import Any, Dict

try:
    import redis.asyncio as aioredis
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "redis>=4.2 not available in the venv -- pip install 'redis>=4.2' first"
    ) from e

from spaces.marketing.agents.marketing_agent import (
    MARKETING_CONSUMER_GROUP,
    get_marketing_agent,
)


logger = logging.getLogger("marketing_runner")

STATUS_STREAM = "events:status:marketing"
STREAM_MAXLEN = 5000   # cap memory usage of the status stream
MAX_DELIVERIES = 3     # poison-pill threshold; ACK + DROP after N retries


# ─── helpers ────────────────────────────────────────────────────────────


def _decode(b: Any) -> str:
    if isinstance(b, bytes):
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return b.decode("utf-8", errors="replace")
    return str(b)


def _parse_fields(raw: Dict[Any, Any]) -> Dict[str, Any]:
    """Convert XREAD's bytes-keyed dict into str-keyed; parse `payload`/`params` as JSON."""
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        key = _decode(k)
        val = _decode(v)
        if key in ("payload", "params") and val:
            try:
                out[key] = json.loads(val)
            except Exception:
                out[key] = val
        else:
            out[key] = val
    return out


async def _ensure_group(redis, stream: str, group: str) -> None:
    """Idempotent XGROUP CREATE -- swallow BUSYGROUP on rerun."""
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
        logger.info("created consumer group %s on %s", group, stream)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("consumer group %s already exists", group)
        else:
            raise


async def _publish_status(redis, *, job_id: str, state: str, **extra: Any) -> None:
    fields = {
        "job_id": job_id or "",
        "state": state,
        "ts": str(int(time.time())),
    }
    for k, v in extra.items():
        if v is None:
            continue
        fields[k] = v if isinstance(v, str) else json.dumps(v, default=str)
    try:
        await redis.xadd(STATUS_STREAM, fields, maxlen=STREAM_MAXLEN, approximate=True)
    except Exception as e:
        logger.exception("xadd status failed for job_id=%s: %s", job_id, e)


async def _dispatch(agent, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = agent._get_tool_name(event_type)
    if not tool_name:
        return {"success": False, "message": f"unknown event_type: {event_type}", "data": None}
    fn = agent.tools.get(tool_name)
    if fn is None:
        return {"success": False, "message": f"tool not loaded: {tool_name}", "data": None}
    params = agent._normalize_params(event_type, payload or {})
    try:
        if inspect.iscoroutinefunction(fn):
            result = await fn(**params)
        else:
            result = await asyncio.to_thread(fn, **params)
    except TypeError as e:
        return {"success": False, "message": f"bad params for {tool_name}: {e}", "data": None}
    except Exception as e:
        logger.exception("tool %s raised", tool_name)
        return {"success": False, "message": f"tool error: {e}", "data": None}
    if isinstance(result, dict):
        return result
    return {"success": True, "message": "ok", "data": result}


# ─── main lifecycle ─────────────────────────────────────────────────────


async def _run() -> int:
    log_level = os.environ.get("MARKETING_RUNNER_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    consumer_name = os.environ.get("MARKETING_RUNNER_CONSUMER", socket.gethostname())
    block_ms = int(os.environ.get("MARKETING_RUNNER_BLOCK_MS", "5000"))

    agent = get_marketing_agent()
    # Fail-fast: if tools couldn't load, every event would silently fail
    # with 'tool not found'.
    tools = agent.tools
    if not tools:
        logger.error("marketing tools failed to load -- aborting")
        return 1
    logger.info("loaded %d tools: %s", len(tools), sorted(tools.keys()))
    logger.info("stream=%s group=%s consumer=%s", agent.stream,
                MARKETING_CONSUMER_GROUP, consumer_name)

    stop_event = asyncio.Event()

    def _on_signal(signum, _frame=None):
        logger.info("received signal %s -- shutting down", signum)
        stop_event.set()

    # asyncio's loop.add_signal_handler is POSIX-only; on Windows
    # signal.signal works for SIGINT/SIGTERM in the main thread.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass

    redis = aioredis.from_url(redis_url)
    try:
        await _ensure_group(redis, agent.stream, MARKETING_CONSUMER_GROUP)
        logger.info("ready -- waiting for events on %s", agent.stream)

        while not stop_event.is_set():
            try:
                resp = await redis.xreadgroup(
                    MARKETING_CONSUMER_GROUP,
                    consumer_name,
                    streams={agent.stream: ">"},
                    count=10,
                    block=block_ms,
                )
            except aioredis.ConnectionError as e:
                logger.warning("redis connection error: %s -- retrying in 2s", e)
                await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.exception("xreadgroup raised: %s -- retrying in 2s", e)
                await asyncio.sleep(2)
                continue

            if not resp:
                continue

            for _stream, entries in resp:
                for msg_id, raw_fields in entries:
                    fields = _parse_fields(raw_fields)
                    event_type = fields.get("event_type") or fields.get("type") or ""
                    job_id = fields.get("job_id") or _decode(msg_id)
                    payload = fields.get("payload") or fields.get("params") or {}
                    if not isinstance(payload, dict):
                        payload = {}

                    await _publish_status(redis, job_id=job_id, state="processing",
                                          event_type=event_type)

                    if not event_type:
                        await _publish_status(redis, job_id=job_id, state="error",
                                              error="missing event_type")
                        await redis.xack(agent.stream, MARKETING_CONSUMER_GROUP, msg_id)
                        continue

                    result = await _dispatch(agent, event_type, payload)
                    final_state = "completed" if result.get("success") else "error"
                    await _publish_status(
                        redis,
                        job_id=job_id,
                        state=final_state,
                        event_type=event_type,
                        result_message=result.get("message"),
                        result=result.get("data"),
                    )
                    await redis.xack(agent.stream, MARKETING_CONSUMER_GROUP, msg_id)
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass
        logger.info("shutdown complete")
    return 0


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())

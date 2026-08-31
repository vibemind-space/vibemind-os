"""predict_post_reception — wrap Mirofish's multi-step sim pipeline
for marketing posts.

Mirofish's HTTP pipeline is:
    1. POST /api/graph/ontology/generate  (multipart upload of text file)
    2. POST /api/graph/build               (graph from project)
    3. GET  /api/graph/task/{task_id}      (poll graph build)
    4. POST /api/simulation/prepare        (build agent personas)
    5. POST /api/simulation/prepare/status (poll prepare)
    6. POST /api/simulation/create         (start the sim)
    7. GET  /api/simulation/{sim_id}       (poll sim progress)
    8. POST /api/report/generate           (after sim done)
    9. GET  /api/report/check/{sim_id}     (find report by sim)
   10. GET  /api/report/{report_id}        (read final report)

This is too much for a single sync call. We expose 3 async-friendly entry points:

    kick_off(bubble_id, content, channel) -> {project_id, task_id, ...}
    poll_status(state) -> {phase, progress, sim_id?, report_id?, done}
    read_report(report_id) -> {score, persona_summary, full_report}

The worker (workers/bubble_predict_runner.py) drives the kick_off -> poll
-> read sequence and writes results back to public.ideas.

LLM-side this hits Ollama llama3.1 + nomic-embed-text via Mirofish's
LLM_BASE_URL config — already wired in the container.
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional


logger = logging.getLogger("marketing.mirofish.predict_post_reception")


# ─── Config ────────────────────────────────────────────────────────────


def _mirofish_url() -> str:
    return os.environ.get("MIROFISH_URL", "http://127.0.0.1:5101").rstrip("/")


_HTTP_TIMEOUT_S = 30
_PIPELINE_POLL_INTERVAL_S = 5


# Channel -> mirofish-platform mapping. Mirofish supports twitter/reddit
# natively; for unsupported (linkedin, x, mastodon, discord) we map to
# the closest analogue and put the actual channel in the requirement text.
_CHANNEL_TO_PLATFORM = {
    "twitter": "twitter",
    "x": "twitter",
    "linkedin": "twitter",      # closest persona-model
    "reddit": "reddit",
    "mastodon": "twitter",
    "discord": "reddit",        # community/forum-style
    "telegram": "reddit",
}


# ─── HTTP helpers ─────────────────────────────────────────────────────


def _post_json(path: str, body: dict, timeout: int = _HTTP_TIMEOUT_S) -> dict:
    url = f"{_mirofish_url()}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _get_json(path: str, timeout: int = _HTTP_TIMEOUT_S) -> dict:
    url = f"{_mirofish_url()}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _post_multipart(path: str, fields: dict, files: list,
                     timeout: int = _HTTP_TIMEOUT_S) -> dict:
    """Send multipart/form-data. fields=text-fields; files=list of (name, filename, bytes)."""
    boundary = f"----marketing-mf-{int(time.time()*1000)}"
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.write(str(v).encode("utf-8"))
        body.write(b"\r\n")
    for fname, filename, content in files:
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{fname}"; '
            f'filename="{filename}"\r\n'.encode()
        )
        body.write(b"Content-Type: text/plain\r\n\r\n")
        if isinstance(content, str):
            content = content.encode("utf-8")
        body.write(content)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())

    url = f"{_mirofish_url()}{path}"
    req = urllib.request.Request(
        url, data=body.getvalue(), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


# ─── Pipeline steps ───────────────────────────────────────────────────


def _build_requirement_text(channel: str, bubble_title: Optional[str]) -> str:
    """The 'simulation_requirement' steers Mirofish's persona-pool."""
    plat = channel.lower()
    title_hint = f" titled '{bubble_title}'" if bubble_title else ""
    return (
        f"Predict the reception of a marketing-post on {plat}{title_hint}. "
        f"Model the diverse audience-personas typical of {plat} (skeptics, "
        f"enthusiasts, professionals, lurkers, contrarians). Output should "
        f"reflect: (a) probable sentiment distribution, (b) likely first-comment "
        f"angles, (c) which personas would re-share vs ignore, (d) red-flags "
        f"that might trigger negative pile-on."
    )


def kick_off(bubble_id: str, content: str, channel: str,
             bubble_title: Optional[str] = None,
             agent_count: int = 100, rounds: int = 10) -> dict:
    """Step 1+2: ontology/generate + graph build. Returns the project+task IDs
    so the worker can poll progress.

    The bubble's content is uploaded as a single .md "knowledge" file. Mirofish
    extracts entities/relations from it, then builds a graph.
    """
    if not content or len(content.strip()) < 20:
        raise ValueError("bubble content too short to simulate against (<20 chars)")
    if channel not in _CHANNEL_TO_PLATFORM:
        raise ValueError(f"unknown channel {channel!r}")

    requirement = _build_requirement_text(channel, bubble_title)
    project_name = f"vbm-marketing-{bubble_id[:12]}"

    # Step 1 — ontology/generate (multipart)
    resp1 = _post_multipart(
        "/api/graph/ontology/generate",
        fields={
            "simulation_requirement": requirement,
            "project_name": project_name,
            "additional_context": f"Marketing-post evaluation; channel={channel}",
        },
        files=[("files", f"{project_name}.md", content)],
        timeout=180,  # ontology gen can take a while on cold ollama
    )
    if not resp1.get("success"):
        raise RuntimeError(f"ontology/generate failed: {resp1.get('error', resp1)}")
    project_id = resp1["data"]["project_id"]
    logger.info("[%s] ontology generated, project_id=%s", bubble_id, project_id)

    # Step 2 — graph/build (json)
    resp2 = _post_json("/api/graph/build", {
        "project_id": project_id,
        "graph_name": f"vbm-{bubble_id[:8]}",
    })
    if not resp2.get("success"):
        raise RuntimeError(f"graph/build failed: {resp2.get('error', resp2)}")
    task_id = resp2["data"]["task_id"]
    logger.info("[%s] graph build started, task_id=%s", bubble_id, task_id)

    return {
        "phase": "graph_building",
        "project_id": project_id,
        "graph_task_id": task_id,
        "channel": channel,
        "platform": _CHANNEL_TO_PLATFORM[channel],
        "agent_count": agent_count,
        "rounds": rounds,
        "requirement": requirement,
        "started_at": time.time(),
    }


def poll_status(state: dict) -> dict:
    """Advance the pipeline forward one polling-step. Returns new state.

    State machine:
        graph_building   -> graph_ready
        graph_ready      -> sim_preparing (kicks off prepare)
        sim_preparing    -> sim_ready
        sim_ready        -> sim_running (kicks off create)
        sim_running      -> sim_done
        sim_done         -> report_generating (kicks off report)
        report_generating-> done
    """
    phase = state.get("phase")

    if phase == "graph_building":
        task = _get_json(f"/api/graph/task/{state['graph_task_id']}")
        td = task.get("data") or {}
        if td.get("status") in ("completed", "done"):
            state["graph_id"] = td.get("graph_id") or td.get("result", {}).get("graph_id")
            state["phase"] = "graph_ready"
            logger.info("graph_ready graph_id=%s", state["graph_id"])
        elif td.get("status") == "failed":
            state["phase"] = "failed"
            state["error"] = f"graph build failed: {td.get('error', 'unknown')}"
        else:
            state["progress"] = td.get("progress") or 0
        return state

    if phase == "graph_ready":
        # Step 3 — CREATE simulation (returns simulation_id which everything else needs)
        plat = state["platform"]
        resp = _post_json("/api/simulation/create", {
            "project_id": state["project_id"],
            "graph_id": state["graph_id"],
            "enable_twitter": plat in ("twitter",),
            "enable_reddit": plat in ("reddit",),
        })
        if not resp.get("success"):
            state["phase"] = "failed"
            state["error"] = f"sim/create: {resp.get('error', resp)}"
            return state
        state["simulation_id"] = resp["data"]["simulation_id"]
        state["phase"] = "sim_created"
        logger.info("sim_created sim_id=%s", state["simulation_id"])
        return state

    if phase == "sim_created":
        # Step 4 — PREPARE personas (takes simulation_id, not graph_id)
        resp = _post_json("/api/simulation/prepare", {
            "simulation_id": state["simulation_id"],
            "use_llm_for_profiles": True,
            "parallel_profile_count": 5,
        })
        if not resp.get("success"):
            state["phase"] = "failed"
            state["error"] = f"sim/prepare: {resp.get('error', resp)}"
            return state
        # if already_prepared, skip waiting
        if resp["data"].get("already_prepared") or resp["data"].get("status") == "ready":
            state["phase"] = "sim_ready"
        else:
            state["prepare_task_id"] = resp["data"].get("task_id")
            state["phase"] = "sim_preparing"
        return state

    if phase == "sim_preparing":
        resp = _post_json("/api/simulation/prepare/status", {
            "task_id": state["prepare_task_id"],
        })
        rd = resp.get("data") or {}
        if rd.get("status") in ("completed", "done", "ready"):
            state["phase"] = "sim_ready"
        elif rd.get("status") == "failed":
            state["phase"] = "failed"
            state["error"] = f"sim/prepare/status: {rd.get('error', 'unknown')}"
        else:
            state["progress"] = rd.get("progress") or 0
        return state

    if phase == "sim_ready":
        # Step 5 — actually START the prepared sim
        plat = state["platform"]
        resp = _post_json("/api/simulation/start", {
            "simulation_id": state["simulation_id"],
            "platform": plat if plat in ("twitter", "reddit") else "parallel",
            "max_rounds": state["rounds"],
        })
        if not resp.get("success"):
            state["phase"] = "failed"
            state["error"] = f"sim/start: {resp.get('error', resp)}"
            return state
        state["phase"] = "sim_running"
        logger.info("sim_running sim_id=%s", state["simulation_id"])
        return state

    if phase == "sim_running":
        resp = _get_json(
            f"/api/simulation/{state['simulation_id']}/run-status"
        )
        rd = resp.get("data") or {}
        st = rd.get("runner_status") or rd.get("status")
        if st in ("completed", "done", "finished"):
            state["phase"] = "sim_done"
        elif st in ("failed", "error"):
            state["phase"] = "failed"
            state["error"] = f"simulation: {rd.get('error', 'unknown')}"
        else:
            state["progress"] = rd.get("current_round") or 0
        return state

    if phase == "sim_done":
        # Step 5 — generate report
        resp = _post_json("/api/report/generate", {
            "simulation_id": state["simulation_id"],
        })
        if not resp.get("success"):
            state["phase"] = "failed"
            state["error"] = f"report/generate: {resp.get('error', resp)}"
            return state
        state["report_task_id"] = (
            resp["data"].get("task_id") or resp["data"].get("report_id")
        )
        state["phase"] = "report_generating"
        return state

    if phase == "report_generating":
        # /api/report/check/{simulation_id} returns report_id when ready
        resp = _get_json(f"/api/report/check/{state['simulation_id']}")
        rd = resp.get("data") or {}
        if rd.get("report_id"):
            state["report_id"] = rd["report_id"]
            state["phase"] = "done"
            logger.info("done report_id=%s", state["report_id"])
        return state

    return state  # done | failed — no-op


def read_report(report_id: str) -> dict:
    """Fetch the final report + extract a compact 0-100 score for the bubble row."""
    resp = _get_json(f"/api/report/{report_id}")
    rd = resp.get("data") or resp  # tolerate both shapes
    score = _extract_score(rd)
    persona_summary = _extract_persona_summary(rd)
    return {
        "report_id": report_id,
        "score": score,
        "persona_summary": persona_summary,
        "full_report": rd,
    }


def _extract_score(report: dict) -> int:
    """Coerce whatever Mirofish gives us into a 0-100 number for UI badge.

    Heuristic — looks for known keys, falls back to sentiment averaging.
    Never raises; returns 50 (neutral) if nothing usable found.
    """
    for k in ("score", "total_score", "reception_score", "sentiment_score"):
        v = report.get(k)
        if isinstance(v, (int, float)):
            n = int(round(v))
            return max(0, min(100, n))
    sentiment = report.get("sentiment") or report.get("aggregate_sentiment") or {}
    pos = sentiment.get("positive") if isinstance(sentiment, dict) else None
    if isinstance(pos, (int, float)):
        return max(0, min(100, int(round(pos * 100 if pos <= 1 else pos))))
    return 50  # neutral default


def _extract_persona_summary(report: dict) -> list[dict]:
    """Return up to 5 top personas with their summary lines for UI display."""
    out: list[dict] = []
    personas = (
        report.get("top_personas")
        or report.get("personas")
        or report.get("agent_summaries")
        or []
    )
    if not isinstance(personas, list):
        return out
    for p in personas[:5]:
        if not isinstance(p, dict):
            continue
        out.append({
            "name": str(p.get("name") or p.get("agent_name") or "?")[:50],
            "sentiment": str(p.get("sentiment") or p.get("verdict") or "neutral")[:20],
            "comment": str(p.get("comment") or p.get("summary") or "")[:280],
        })
    return out


# ─── Drilldown ──────────────────────────────────────────────────────


def drilldown_persona(report_id: str, persona_name: str,
                       question: str) -> dict:
    """Ask the simulated persona-agent a follow-up question.
    Wraps /api/report/chat (with persona context)."""
    resp = _post_json("/api/report/chat", {
        "report_id": report_id,
        "agent_name": persona_name,
        "question": question[:500],
    }, timeout=60)
    return resp.get("data") or resp

"""Brain execution target for the Video Space.

Long-running video tools are accepted asynchronously and write durable JSON
job evidence. A media-producing job is only completed when at least one
artifact path exists; provider/CLI errors and evidence-free successes fail
closed.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable
from uuid import uuid4


_TARGET = "direct:spaces.video.execution_target:execute_video"
_TERMINAL = {"completed", "failed"}
_MEDIA_EVENTS = {
    "video.team_run",
    "video.vision",
    "video.demo_build",
    "video.lipsync",
    "video.voice_clone",
    "video.voice_tts",
}
_REQUIRED_PARAMS = {
    "video.team_run": ("task",),
    "video.vision": ("url",),
    "video.demo_build": ("description",),
    "video.lipsync": ("video", "audio"),
    "video.voice_clone": ("audio",),
    "video.voice_tts": ("text",),
}
_TOOL_NAMES = {
    "video.status": "video_status",
    "video.team_status": "team_pipeline_status",
    "video.team_run": "team_run_step",
    "video.vision": "vision_generate",
    "video.demo_build": "demo_build",
    "video.lipsync": "lipsync_run",
    "video.voice_clone": "voice_clone",
    "video.voice_tts": "voice_tts",
}
_ARTIFACT_SUFFIXES = {
    ".aac", ".flac", ".json", ".m4a", ".mov", ".mp3", ".mp4",
    ".srt", ".wav", ".webm", ".yaml", ".yml",
}
_JOB_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_dir() -> Path:
    root = Path(os.environ.get("VIBEMIND_VIDEO_JOB_DIR", Path.home() / ".vibemind" / "video-jobs"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_path(job_id: str) -> Path:
    if not job_id.startswith("video-") or any(char in job_id for char in ("/", "\\", "..")):
        raise LookupError(f"video job not found: {job_id}")
    return _job_dir() / f"{job_id}.json"


def _write_job(record: Dict[str, Any]) -> None:
    with _JOB_LOCK:
        path = _job_path(str(record["job_id"]))
        temp = path.with_suffix(f".{uuid4().hex}.tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)


def _read_job(job_id: str) -> Dict[str, Any]:
    with _JOB_LOCK:
        path = _job_path(job_id)
        if not path.is_file():
            raise LookupError(f"video job not found: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))


def _resolve_tool(event_type: str) -> Callable[..., Dict[str, Any]]:
    try:
        tool_name = _TOOL_NAMES[event_type]
    except KeyError as exc:
        raise ValueError(f"unsupported video event: {event_type}") from exc
    from spaces.video.tools import video_tools

    tool = getattr(video_tools, tool_name, None)
    if not callable(tool):
        raise RuntimeError(f"video tool unavailable: {tool_name}")
    return tool


def _tool_params(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    ignored = {"event_type", "job_id", "value", "_capability", "_description", "_intent", "_step_id"}
    params = {key: value for key, value in payload.items() if key not in ignored and value not in (None, "")}
    if event_type == "video.team_run":
        params["step"] = params.pop("task")
    elif event_type == "video.demo_build":
        params["config_path"] = params.pop("description")
    return params


def _candidate_paths(value: Any, key: str = "") -> Iterable[Path]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _candidate_paths(child, str(child_key).lower())
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _candidate_paths(child, key)
    elif isinstance(value, str) and any(token in key for token in ("artifact", "file", "media", "output", "path")):
        yield Path(value).expanduser()


def _artifact_evidence(result: Dict[str, Any]) -> list[Dict[str, Any]]:
    evidence = []
    seen = set()
    for candidate in _candidate_paths(result):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        path = str(resolved)
        if path in seen or not resolved.is_file():
            continue
        seen.add(path)
        evidence.append({"path": path, "exists": True})
    return evidence


def _artifact_roots() -> tuple[Path, ...]:
    from spaces.video.tools.video_tools import DEEPFAKE_DIR, MEDIA_ROOT, VIBEVIDEO_DIR

    return (VIBEVIDEO_DIR, DEEPFAKE_DIR, MEDIA_ROOT)


def _artifact_snapshot() -> Dict[str, tuple[int, int]]:
    snapshot: Dict[str, tuple[int, int]] = {}
    for root in _artifact_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _ARTIFACT_SUFFIXES:
                continue
            try:
                stat = path.stat()
                snapshot[str(path.resolve())] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue
    return snapshot


def _changed_artifacts(before: Dict[str, tuple[int, int]]) -> list[Dict[str, Any]]:
    after = _artifact_snapshot()
    return [
        {"path": path, "exists": True}
        for path, fingerprint in after.items()
        if before.get(path) != fingerprint
    ]


def _run_job(job_id: str, event_type: str, params: Dict[str, Any]) -> None:
    record = _read_job(job_id)
    record.update(status="running", started_at=_now())
    _write_job(record)
    try:
        before = _artifact_snapshot()
        result = _resolve_tool(event_type)(**params)
        if not isinstance(result, dict):
            raise RuntimeError("video tool returned a non-object result")
        if result.get("success") is not True:
            raise RuntimeError(str(result.get("message") or result.get("error") or "video provider failed"))
        artifacts = _artifact_evidence(result)
        known = {item["path"] for item in artifacts}
        artifacts.extend(item for item in _changed_artifacts(before) if item["path"] not in known)
        if event_type in _MEDIA_EVENTS and not artifacts:
            raise RuntimeError("provider returned no existing artifact evidence")
        record.update(
            success=True,
            status="completed",
            artifacts=artifacts,
            media_paths=[item["path"] for item in artifacts if Path(item["path"]).suffix.lower() in _ARTIFACT_SUFFIXES],
            completed_at=_now(),
        )
    except Exception as exc:  # worker boundary: persist an honest terminal state
        record.update(
            success=False,
            status="failed",
            error=str(exc),
            artifacts=[],
            media_paths=[],
            completed_at=_now(),
        )
    _write_job(record)


def _space_status(event_type: str) -> Dict[str, Any]:
    result = _resolve_tool(event_type)()
    if not isinstance(result, dict):
        raise RuntimeError("video status tool returned a non-object result")
    if event_type == "video.status":
        available = bool(result.get("vibevideo_installed") and result.get("deepfake_installed"))
    else:
        available = bool(result.get("available"))
    if not available:
        raise RuntimeError("video providers unavailable")
    return {
        **result,
        "success": available,
        "status": "available" if available else "unavailable",
        "execution_target": _TARGET,
    }


def execute_video(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a canonical ``video.*`` event from Brain's PlanExecutor."""
    if not isinstance(payload, dict):
        raise TypeError("video execution payload must be an object")
    nested_value = payload.get("value")
    if isinstance(nested_value, dict):
        payload = {**nested_value, **{key: value for key, value in payload.items() if key != "value"}}
    event_type = str(payload.get("event_type") or "")
    if not event_type:
        capability = str(payload.get("_capability") or "")
        event_type = capability.replace("video_", "video.", 1)
    if event_type == "video.status" and payload.get("job_id"):
        return _read_job(str(payload["job_id"]))
    if event_type in {"video.status", "video.team_status"}:
        return _space_status(event_type)
    if event_type not in _MEDIA_EVENTS:
        raise ValueError(f"unsupported video event: {event_type}")

    missing = [name for name in _REQUIRED_PARAMS[event_type] if payload.get(name) in (None, "")]
    if missing:
        raise ValueError(f"{event_type} requires: {', '.join(missing)}")

    job_id = f"video-{uuid4().hex}"
    record = {
        "success": True,
        "job_id": job_id,
        "event_type": event_type,
        "status": "accepted",
        "execution_target": _TARGET,
        "artifacts": [],
        "media_paths": [],
        "created_at": _now(),
    }
    _write_job(record)
    worker = threading.Thread(
        target=_run_job,
        args=(job_id, event_type, _tool_params(event_type, payload)),
        name=f"{job_id}-worker",
        daemon=True,
    )
    worker.start()
    return record


__all__ = ["execute_video"]

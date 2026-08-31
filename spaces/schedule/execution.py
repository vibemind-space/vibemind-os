"""Durable, fail-closed execution target for Schedule Brain capabilities."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Berlin"
_TRIGGER_KEYS = ("run_date", "cron", "interval_seconds")


class ScheduleContractError(ValueError):
    """The request cannot safely be translated into a scheduler trigger."""


def _payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ScheduleContractError("schedule payload must be a JSON object") from exc
        value = decoded
    if not isinstance(value, Mapping):
        raise ScheduleContractError("schedule payload must be an object")
    result = dict(value)
    embedded = result.pop("value", None)
    if isinstance(embedded, str) and embedded.lstrip().startswith("{"):
        try:
            decoded = json.loads(embedded)
        except json.JSONDecodeError as exc:
            raise ScheduleContractError("schedule payload value must be valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ScheduleContractError("schedule payload value must be an object")
        return {**decoded, **result}
    return result


def _now() -> datetime:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE))


def _validate_timezone(value: Any) -> str:
    timezone = str(value or DEFAULT_TIMEZONE)
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleContractError(f"unknown IANA timezone: {timezone}") from exc
    return timezone


def _validate_cron(expr: Any) -> str:
    cron = str(expr or "").strip()
    if len(cron.split()) != 5:
        raise ScheduleContractError("cron expression must contain exactly five fields")
    return cron


def _validate_trigger(value: Any, timezone: str) -> tuple[str, Dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ScheduleContractError("trigger_config must be an object")
    supplied = [key for key in _TRIGGER_KEYS if value.get(key) not in (None, "")]
    if len(supplied) != 1:
        raise ScheduleContractError("trigger_config must contain exactly one trigger")
    key = supplied[0]
    if key == "cron":
        return "cron", {"cron": _validate_cron(value[key])}
    if key == "interval_seconds":
        try:
            seconds = int(value[key])
        except (TypeError, ValueError) as exc:
            raise ScheduleContractError("interval_seconds must be an integer") from exc
        if seconds < 1:
            raise ScheduleContractError("interval_seconds must be positive")
        return "interval", {"interval_seconds": seconds}
    try:
        run_date = datetime.fromisoformat(str(value[key]))
    except ValueError as exc:
        raise ScheduleContractError("run_date must be ISO-8601") from exc
    if run_date.tzinfo is None or run_date.utcoffset() is None:
        raise ScheduleContractError("run_date must be timezone-aware")
    return "date", {"run_date": run_date.astimezone(ZoneInfo(timezone)).isoformat()}


class ScheduleRepository:
    """SQLite repository; every operation commits before reporting success."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("SCHEDULE_DB_PATH")
        self.path = Path(configured) if configured else Path(__file__).parent / "data" / "schedule.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    action_text TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_config TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> Dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["trigger_config"] = json.loads(result["trigger_config"])
        return result

    def get(self, task_id: str) -> Dict[str, Any] | None:
        with self._connect() as db:
            return self._row(db.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone())

    def get_by_idempotency_key(self, key: str) -> Dict[str, Any] | None:
        with self._connect() as db:
            return self._row(db.execute("SELECT * FROM scheduled_tasks WHERE idempotency_key = ?", (key,)).fetchone())

    def list(self, status_filter: str = "") -> list[Dict[str, Any]]:
        with self._connect() as db:
            if status_filter:
                rows = db.execute("SELECT * FROM scheduled_tasks WHERE status = ? ORDER BY created_at DESC", (status_filter,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC").fetchall()
        return [self._row(row) for row in rows if row is not None]

    def create(self, task: Mapping[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO scheduled_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task["id"], task["event_type"], task["title"], task["action_text"],
                 task["trigger_type"], json.dumps(task["trigger_config"], sort_keys=True),
                 task["timezone"], task["status"], task.get("idempotency_key"),
                 task["created_at"], task["updated_at"]),
            )

    def update(self, task_id: str, fields: Mapping[str, Any]) -> Dict[str, Any]:
        allowed = {"title", "action_text", "trigger_type", "trigger_config", "timezone", "status", "updated_at"}
        changes = {key: value for key, value in fields.items() if key in allowed}
        if "trigger_config" in changes:
            changes["trigger_config"] = json.dumps(changes["trigger_config"], sort_keys=True)
        assignments = ", ".join(f"{key} = ?" for key in changes)
        with self._connect() as db:
            cursor = db.execute(f"UPDATE scheduled_tasks SET {assignments} WHERE id = ?", (*changes.values(), task_id))
            if cursor.rowcount != 1:
                raise ScheduleContractError(f"scheduled task not found: {task_id}")
        task = self.get(task_id)
        if task is None:
            raise RuntimeError("schedule update was not persisted")
        return task


def _required(data: Mapping[str, Any], key: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ScheduleContractError(f"{key} is required")
    return value


def _task_result(task: Mapping[str, Any], **extra: Any) -> Dict[str, Any]:
    return {"success": True, "schedule_id": task["id"], "status": task["status"],
            "trigger_type": task["trigger_type"], "timezone": task["timezone"], **extra}


def create(value: Any) -> Dict[str, Any]:
    data = _payload(value)
    timezone = _validate_timezone(data.get("timezone"))
    trigger_type, trigger_config = _validate_trigger(data.get("trigger_config"), timezone)
    title = _required(data, "title")
    action_text = _required(data, "action_text")
    key = str(data.get("idempotency_key") or "").strip()
    repo = ScheduleRepository()
    if key:
        existing = repo.get_by_idempotency_key(key)
        if existing:
            canonical = json.dumps([title, action_text, trigger_config, timezone], sort_keys=True)
            old = json.dumps([existing["title"], existing["action_text"], existing["trigger_config"], existing["timezone"]], sort_keys=True)
            if hashlib.sha256(canonical.encode()).digest() != hashlib.sha256(old.encode()).digest():
                raise ScheduleContractError("idempotency key was already used with a different request")
            return _task_result(existing, idempotent_replay=True)
    timestamp = _now().isoformat()
    task = {"id": str(uuid.uuid4()), "event_type": str(data.get("event_type") or "schedule.create"),
            "title": title, "action_text": action_text, "trigger_type": trigger_type,
            "trigger_config": trigger_config, "timezone": timezone, "status": "active",
            "idempotency_key": key or None, "created_at": timestamp, "updated_at": timestamp}
    repo.create(task)
    return _task_result(task, idempotent_replay=False)


def list_tasks(value: Any = None) -> Dict[str, Any]:
    data = {} if value is None else _payload(value)
    tasks = ScheduleRepository().list(str(data.get("status") or ""))
    return {"success": True, "tasks": tasks, "count": len(tasks)}


def _task_id(value: Any) -> tuple[Dict[str, Any], str]:
    data = _payload(value)
    return data, _required(data, "task_id")


def cancel(value: Any) -> Dict[str, Any]:
    _, task_id = _task_id(value)
    task = ScheduleRepository().update(task_id, {"status": "cancelled", "updated_at": _now().isoformat()})
    return _task_result(task)


def modify(value: Any) -> Dict[str, Any]:
    data, task_id = _task_id(value)
    current = ScheduleRepository().get(task_id)
    if current is None:
        raise ScheduleContractError(f"scheduled task not found: {task_id}")
    fields: Dict[str, Any] = {"updated_at": _now().isoformat()}
    if data.get("trigger_config") is not None:
        trigger_type, trigger_config = _validate_trigger(data["trigger_config"], current["timezone"])
        fields.update(trigger_type=trigger_type, trigger_config=trigger_config, status="active")
    for key in ("title", "action_text"):
        if data.get(key):
            fields[key] = str(data[key]).strip()
    if len(fields) == 1:
        raise ScheduleContractError("modify requires a trigger, title, or action_text")
    return _task_result(ScheduleRepository().update(task_id, fields))


def status(value: Any = None) -> Dict[str, Any]:
    data = {} if value is None else _payload(value)
    repo = ScheduleRepository()
    if data.get("task_id"):
        task = repo.get(str(data["task_id"]))
        if task is None:
            raise ScheduleContractError(f"scheduled task not found: {data['task_id']}")
        return {"success": True, "task": task}
    tasks = repo.list()
    counts = {name: sum(task["status"] == name for task in tasks) for name in ("active", "cancelled", "paused", "completed", "failed")}
    return {"success": True, "counts": counts, "total": len(tasks)}


def snooze(value: Any) -> Dict[str, Any]:
    data, task_id = _task_id(value)
    try:
        minutes = int(data.get("minutes", 5))
    except (TypeError, ValueError) as exc:
        raise ScheduleContractError("minutes must be an integer") from exc
    if not 1 <= minutes <= 10080:
        raise ScheduleContractError("minutes must be between 1 and 10080")
    run_date = (_now() + timedelta(minutes=minutes)).isoformat()
    task = ScheduleRepository().update(task_id, {"trigger_type": "date", "trigger_config": {"run_date": run_date},
                                                      "timezone": DEFAULT_TIMEZONE, "status": "active", "updated_at": _now().isoformat()})
    return _task_result(task, new_run_at=run_date, snooze_minutes=minutes)


def openclaw_cron(value: Any) -> Dict[str, Any]:
    data = _payload(value)
    data["event_type"] = "openclaw.cron"
    data["title"] = str(data.get("title") or "OpenClaw cron")
    data["action_text"] = _required(data, "prompt")
    data["trigger_config"] = {"cron": _validate_cron(data.get("cron_expr"))}
    return create(data)

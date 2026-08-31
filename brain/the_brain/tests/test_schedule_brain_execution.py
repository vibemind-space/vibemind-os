from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from brain.the_brain.core.plan_executor import PlanExecutor, PlanRecorder
from brain.the_brain.core.plan_schema import HopSpec, Plan


@pytest.fixture()
def schedule_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCHEDULE_DB_PATH", str(tmp_path / "schedule.sqlite3"))
    module = importlib.import_module("spaces.schedule.execution")
    return importlib.reload(module)


def test_registry_routes_every_schedule_operation_to_real_targets():
    registry_path = Path(__file__).resolve().parents[3] / "config" / "space_agent_registry.yml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    events = registry["spaces"]["schedule"]["events"]

    expected = {
        "schedule.create",
        "schedule.list",
        "schedule.cancel",
        "schedule.modify",
        "schedule.status",
        "schedule.snooze",
        "openclaw.cron",
    }
    assert set(events) == expected
    assert all(event["tool"].startswith("schedule_") for event in events.values())


def test_brain_capabilities_have_resolvable_schedule_execution_targets():
    capabilities_path = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"
    capabilities = {item["capability"]: item for item in yaml.safe_load(capabilities_path.read_text(encoding="utf-8"))}
    expected = {
        "schedule_create": "create",
        "schedule_list": "list_tasks",
        "schedule_cancel": "cancel",
        "schedule_modify": "modify",
        "schedule_status": "status",
        "schedule_snooze": "snooze",
        "schedule_openclaw_cron": "openclaw_cron",
    }
    for capability, function in expected.items():
        assert capabilities[capability]["execution_target"] == f"direct:spaces.schedule.execution:{function}"

    agent_path = Path(__file__).resolve().parents[1] / "configs" / "agents" / "brain-scheduler.yaml"
    agent = yaml.safe_load(agent_path.read_text(encoding="utf-8"))
    assert "openclaw.cron" in agent["events"]


def test_create_is_idempotent_and_survives_repository_reopen(schedule_execution):
    payload = {
        "title": "Daily review",
        "action_text": "OpenClaw: summarize notifications",
        "trigger_config": {"cron": "0 9 * * *"},
        "idempotency_key": "voice-42",
    }

    first = schedule_execution.create(payload)
    second = schedule_execution.create(payload)
    reopened = schedule_execution.ScheduleRepository()

    assert first["schedule_id"] == second["schedule_id"]
    assert second["idempotent_replay"] is True
    assert reopened.get(first["schedule_id"])["timezone"] == "Europe/Berlin"
    assert len(reopened.list()) == 1


def test_openclaw_cron_validates_trigger_and_persists(schedule_execution):
    result = schedule_execution.openclaw_cron({
        "cron_expr": "*/15 * * * *",
        "prompt": "Check inbox",
        "idempotency_key": "api-cron-7",
    })

    assert result["success"] is True
    task = schedule_execution.ScheduleRepository().get(result["schedule_id"])
    assert task["event_type"] == "openclaw.cron"
    assert task["trigger_config"] == {"cron": "*/15 * * * *"}

    with pytest.raises(schedule_execution.ScheduleContractError, match="five fields"):
        schedule_execution.openclaw_cron({"cron_expr": "bad cron", "prompt": "x"})


def test_modify_snooze_cancel_and_status(schedule_execution):
    created = schedule_execution.create({
        "title": "Call dentist",
        "action_text": "Remind me to call dentist",
        "trigger_config": {"run_date": "2030-01-02T10:00:00+01:00"},
    })
    task_id = created["schedule_id"]

    modified = schedule_execution.modify({
        "task_id": task_id,
        "trigger_config": {"cron": "30 8 * * 1-5"},
        "action_text": "Call dentist office",
    })
    snoozed = schedule_execution.snooze({"task_id": task_id, "minutes": 10})
    status = schedule_execution.status({"task_id": task_id})
    cancelled = schedule_execution.cancel({"task_id": task_id})

    assert modified["trigger_type"] == "cron"
    assert snoozed["trigger_type"] == "date"
    assert status["task"]["status"] == "active"
    assert cancelled["status"] == "cancelled"


def test_invalid_or_ambiguous_triggers_fail_closed(schedule_execution):
    with pytest.raises(schedule_execution.ScheduleContractError, match="exactly one"):
        schedule_execution.create({
            "title": "Ambiguous",
            "action_text": "do it",
            "trigger_config": {"cron": "0 9 * * *", "run_date": "2030-01-01T09:00:00+01:00"},
        })

    with pytest.raises(schedule_execution.ScheduleContractError, match="timezone-aware"):
        schedule_execution.create({
            "title": "Naive",
            "action_text": "do it",
            "trigger_config": {"run_date": "2030-01-01T09:00:00"},
        })


def test_plan_executor_runs_structured_schedule_target(schedule_execution, tmp_path: Path):
    plan = Plan(
        plan_id="schedule-plan-1",
        intent="Create a reminder",
        rationale="canonical schedule event",
        hops=[HopSpec(
            step_id="create",
            description="persist reminder",
            capability="schedule_create",
            execution_target="direct:spaces.schedule.execution:create",
            arg_template='{"title":"Review","action_text":"Review alerts","trigger_config":{"cron":"0 9 * * *"}}',
        )],
    )
    executor = PlanExecutor(recorder=PlanRecorder(path=tmp_path / "plans.jsonl"))

    result = executor.execute(plan)

    assert result["ok"] is True
    assert result["executed"]["create"]["result"]["success"] is True


@pytest.mark.asyncio
async def test_worker_reloads_persisted_active_tasks_after_reboot(schedule_execution):
    created = schedule_execution.create({
        "title": "Persistent",
        "action_text": "Run persisted action",
        "trigger_config": {"cron": "0 7 * * *"},
    })
    registered = []

    class FakeScheduler:
        def start(self):
            return None

        def add_job(self, function, **kwargs):
            registered.append(kwargs)

    from spaces.schedule.workers.durable_worker import ScheduleWorker

    class FakeTrigger:
        timezone = "Europe/Berlin"

    worker = ScheduleWorker(
        scheduler_factory=lambda: FakeScheduler(),
        trigger_factory=lambda task: FakeTrigger(),
        execution_target=lambda task: {"ok": True},
    )
    await worker.start()

    assert worker.is_running is True
    assert registered[0]["id"] == created["schedule_id"]
    assert registered[0]["replace_existing"] is True
    assert str(registered[0]["trigger"].timezone) == "Europe/Berlin"

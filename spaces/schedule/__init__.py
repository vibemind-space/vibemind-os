"""
Schedule Space — APScheduler-based task scheduling for VibeMind.

Enables voice-triggered reminders, alarms, and recurring tasks via German NLP.

Two execution modes:
    Simple  (Option B) → APScheduler fires → IntentOrchestrator → Voice Notification
    Complex (Option A) → APScheduler fires → Minibook start_collaboration() → Multi-Space

Usage:
    from spaces.schedule import get_schedule_agent, ScheduleWorker

    # Backend agent (Redis / sync integration)
    agent = get_schedule_agent()
    await agent.start()

    # APScheduler worker (loads active tasks from DB)
    worker = ScheduleWorker(
        realtime_session_getter=get_session,
        orchestrator_getter=get_orchestrator,
    )
    await worker.start()
"""

# Configuration
from .config import ScheduleConfig, get_config

# NLP
from .nlp import ParsedTime, parse_time_expression

# Heavy runtime integrations are intentionally lazy. Brain direct targets can
# import ``spaces.schedule.execution`` without requiring the voice/swarm stack.

__all__ = [
    # Config
    "ScheduleConfig",
    "get_config",
    # NLP
    "ParsedTime",
    "parse_time_expression",
    "ScheduleBackendAgent",
    "get_schedule_agent",
    "create_scheduled_task",
    "list_scheduled_tasks",
    "cancel_scheduled_task",
    "modify_scheduled_task",
    "get_schedule_status",
    "snooze_scheduled_task",
    "ScheduleWorker",
]


def __getattr__(name):
    if name == "ScheduleWorker":
        from .workers import ScheduleWorker
        return ScheduleWorker
    if name in {"ScheduleBackendAgent", "get_schedule_agent"}:
        from .agents import ScheduleBackendAgent, get_schedule_agent
        return {"ScheduleBackendAgent": ScheduleBackendAgent, "get_schedule_agent": get_schedule_agent}[name]
    tool_names = {
        "create_scheduled_task", "list_scheduled_tasks", "cancel_scheduled_task",
        "modify_scheduled_task", "get_schedule_status", "snooze_scheduled_task",
    }
    if name in tool_names:
        from . import tools
        return getattr(tools, name)
    raise AttributeError(name)

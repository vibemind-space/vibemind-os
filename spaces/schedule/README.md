# Schedule Space

Voice-controlled task scheduling with German NLP time parsing, APScheduler persistence, and multi-space execution.

## Architecture

```
Voice: "Erinnere mich in 5 Minuten an den Termin"
    ↓
IntentClassifier → schedule.create {user_text: "..."}
    ↓
ScheduleBackendAgent
    ↓
parse_time_expression() → ParsedTime (regex, no LLM)
    ↓
SQLite (persistence) + APScheduler (trigger engine)
    ↓
Execution:
    ├── SIMPLE: IntentOrchestrator.process_intent_sync()
    └── COMPLEX: Minibook.start_collaboration()
    ↓
Result delivery:
    ├── Direct voice injection (Rachel speaks)
    └── NotificationQueue fallback
```

## Agent

| Property | Value |
|----------|-------|
| **Class** | `ScheduleBackendAgent` |
| **Stream** | `events:tasks:schedule` |
| **File** | `agents/schedule_agent.py` |

## Event Types (6)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `schedule.create` | `create_scheduled_task` | Create task with time parsing |
| `schedule.list` | `list_scheduled_tasks` | List tasks (filtered by status) |
| `schedule.cancel` | `cancel_scheduled_task` | Cancel by ID or fuzzy title |
| `schedule.modify` | `modify_scheduled_task` | Modify time and/or action |
| `schedule.status` | `get_schedule_status` | Summary + counts + next upcoming |
| `schedule.snooze` | `snooze_scheduled_task` | Snooze by X minutes |

## Parameter Mapping (German)

| Event Type | Aliases → Tool Parameter |
|-----------|--------------------------|
| `schedule.create` | `text, eingabe, aufgabe` → `user_text`; `titel, name` → `title` |
| `schedule.cancel` | `name, aufgabe` → `title`; `id` → `task_id` |
| `schedule.modify` | `name, aufgabe` → `title`; `zeit, neue_zeit` → `new_time`; `aktion` → `new_action` |
| `schedule.snooze` | `name, aufgabe` → `title`; `minuten` → `minutes` |

## NLP Time Parser

**File:** `nlp/time_parser.py` — Regex-based (no LLM, fast, deterministic, offline)

### Supported Patterns

| Pattern | Example | Trigger |
|---------|---------|---------|
| `in X Minuten/Stunden/Tagen` | "in 5 Minuten" | DATE (now + duration) |
| `in einer halben Stunde` | "in einer halben Stunde" | DATE (now + 30min) |
| `um HH:MM / HH Uhr` | "um 14 Uhr", "um 9:30" | DATE (today or tomorrow) |
| `jeden [Wochentag] um HH` | "jeden Montag um 9" | CRON |
| `alle X [Einheiten]` | "alle 2 Stunden" | INTERVAL |
| `täglich um HH` | "täglich um 8" | CRON |

Supports German day names, word numbers (eine–fünfzig), and unit variations.

## Schedule Worker

**File:** `workers/schedule_worker.py` — APScheduler-based execution engine

- Uses `AsyncIOScheduler` with `MemoryJobStore`
- SQLite provides persistence across restarts
- On startup: loads active tasks → registers as APScheduler jobs

### Execution Modes

| Mode | When | How |
|------|------|-----|
| **SIMPLE** | Reminders, single-space tasks | `IntentOrchestrator.process_intent_sync(action_text)` |
| **COMPLEX** | Multi-space tasks | `Minibook.start_collaboration(task, goal)` |

### Result Delivery

1. **Direct voice injection** — `session.inject_system_message()` → Rachel speaks immediately
2. **NotificationQueue** — Queued for next user input (fallback)

## Data Model

```python
@dataclass
class ScheduledTask:
    id: str
    title: str
    action_text: str                    # Natural language intent
    trigger_type: str                   # date, cron, interval
    trigger_config: Dict[str, Any]      # APScheduler kwargs
    execution_mode: str                 # simple or complex
    timezone: str                       # default: Europe/Berlin
    status: str                         # active, paused, completed, cancelled, failed
    run_count: int
    max_runs: Optional[int]             # None = unlimited
```

## Directory Structure

```
python/spaces/schedule/
├── agents/
│   ├── __init__.py
│   └── schedule_agent.py              # ScheduleBackendAgent
├── config.py                          # ScheduleConfig dataclass
├── nlp/
│   ├── __init__.py
│   └── time_parser.py                 # parse_time_expression() + ParsedTime
├── tools/
│   ├── __init__.py
│   └── schedule_tools.py              # 6 tool functions (538 lines)
└── workers/
    ├── __init__.py
    └── schedule_worker.py             # AsyncIOScheduler (369 lines)
```

## Configuration

```bash
SCHEDULE_ENABLED=true                  # Enable schedule space
SCHEDULE_TIMEZONE=Europe/Berlin        # IANA timezone
SCHEDULE_MAX_CONCURRENT=5              # Max parallel jobs
SCHEDULE_MISFIRE_GRACE=60              # Grace time in seconds
```

## Status Icons

| Icon | Status |
|------|--------|
| ▶ | active |
| ⏸ | paused |
| ✓ | completed |
| ✗ | cancelled |
| ⚠ | failed |

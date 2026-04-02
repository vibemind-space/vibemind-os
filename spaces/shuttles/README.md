# Shuttles Space

Requirements engineering pipeline and SWE Design submodule. This space has **no dedicated backend agent** — shuttle events are handled by BubblesAgent.

## Architecture

```
Voice: "Bewerte diese Bubble" / "Promote die Bubble"
    ↓
IntentClassifier → bubble.evaluate / bubble.promote
    ↓
BubblesAgent (handles shuttle events)
    ↓
Shuttle Pipeline: Evaluate → Requirements → Design → Promote
```

## Key Facts

| Property | Value |
|----------|-------|
| **Backend Agent** | None (events handled by BubblesAgent) |
| **Event Prefix** | `bubble.evaluate`, `bubble.promote` |
| **Submodule** | `swe_desgine/` (git: github.com/Flissel/swe_desgine) |

## Shuttle Pipeline

Shuttles represent a staged requirements engineering process for ideas/bubbles:

1. **Evaluate** — Assess bubble quality and readiness
2. **Requirements** — Gather and structure requirements
3. **Design** — SWE design phase
4. **Promote** — Promote to implementation

## Data Model

```python
# Database table: shuttles
shuttle_id: str
bubble_id: str
current_stage: str           # evaluate, requirements, design, promote
stage_type: str
stage_data: JSON
```

## Directory Structure

```
python/spaces/shuttles/
└── swe_desgine/             # Git submodule (SWE Design tools)
```

## Related Files

| Component | Location |
|-----------|----------|
| BubblesAgent (handles events) | `python/spaces/ideas/agents/bubbles_agent.py` |
| Shuttle data model | `python/data/models.py` (ScheduledTask → Shuttle) |
| Shuttle tools | `python/tools/bubble_requirements_tool.py` |
| SWE Design UI | `electron-app/swe-design-manager.js` |

## IPC Messages

| Message | Direction | Purpose |
|---------|-----------|---------|
| `shuttle_launched` | Python → Electron | Shuttle pipeline started |
| `shuttle_stage_update` | Python → Electron | Pipeline stage progress |

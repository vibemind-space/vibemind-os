# Minibook Space

Inter-space collaboration layer. Enables multiple VibeMind agents to coordinate on complex tasks via a central message bus (Minibook REST API). Optional **Hub Mode** routes ALL user intents through Minibook for intelligent space routing.

## Architecture

```
Standard Mode:
    Voice → "Koordiniere das mit Coding und Research"
        ↓
    IntentClassifier → minibook.collaborate
        ↓
    MinibookBackendAgent
        ↓
    detect_needed_spaces() → @vibemind_coding @vibemind_research
        ↓
    Minibook REST API (localhost:3480) → POST with @mentions
        ↓
    DiscussionPollerWorker (polls for responses)
        ↓
    Result → Rachel speaks or NotificationQueue

Hub Mode (USE_MINIBOOK_HUB=true):
    ALL intents → MinibookHub.dispatch()
        ↓
    EnrichmentPipeline (4 stages)
        ├── ContextGather (metadata from all stores)
        ├── IntentClassifier (event_type + payload)
        ├── SpaceRouter (LLM: which space(s)?)
        └── TaskEnricher (per-agent payloads)
        ↓
    Single-space: sync-wait (≤10s)
    Multi-space: async-poll via ResultAggregator
```

## Agent

| Property | Value |
|----------|-------|
| **Class** | `MinibookBackendAgent` |
| **Stream** | `events:tasks:minibook` |
| **File** | `agents/minibook_agent.py` |

## Event Types (6)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `minibook.discuss` | `start_discussion` | Start discussion in Minibook |
| `minibook.collaborate` | `start_collaboration` | Multi-space coordination |
| `minibook.status` | `get_minibook_status` | Check Minibook connection |
| `minibook.results` | `get_discussion_results` | Retrieve discussion responses |
| `minibook.list_projects` | `list_projects` | List Minibook projects |
| `minibook.poll` | `poll_responses` | Manual poll for results |

## Parameter Mapping (German)

| Event Type | Aliases → Tool Parameter |
|-----------|--------------------------|
| `minibook.discuss` | `anfrage, thema, nachricht` → `message, topic` |
| `minibook.collaborate` | `aufgabe, ziel, anfrage` → `task, goal` |
| `minibook.results` | `diskussion` → `discussion_id` |

## Tools

### minibook_tools.py — Direct Voice-Controllable

| Tool | Purpose |
|------|---------|
| `get_minibook_status()` | Check connection, agent count |
| `start_discussion(message, topic)` | Create discussion post |
| `get_discussion_results(discussion_id)` | Retrieve comments |
| `list_projects()` | List all projects |

### collaboration_tools.py — Inter-Space Coordination

| Tool | Purpose |
|------|---------|
| `register_all_space_agents(client, project_id)` | Startup: register all 9 spaces |
| `detect_needed_spaces(task)` | Keyword-based space detection |
| `start_collaboration(task, goal)` | Post with @mentions, return immediately |
| `poll_responses()` | Manual poll for active discussions |

### minibook_client.py — HTTP REST Wrapper

`MinibookClient` class wrapping Minibook REST API with bearer token auth per agent.

## Registered Spaces (9)

| Space | Minibook Agent | Domain |
|-------|---------------|--------|
| ideas | `vibemind_ideas` | `bubble.*, idea.*, shuttle.*` |
| coding | `vibemind_coding` | `code.*` |
| desktop | `vibemind_desktop` | `desktop.*, messaging.*, web.*` |
| research | `vibemind_research` | `research.*` |
| rowboat | `vibemind_rowboat` | `roarboot.*` |
| openclaw | `vibemind_openclaw` | `openclaw.*` |
| swe_design | `vibemind_swe_design` | SWE Design pipeline |
| transformer | `vibemind_transformer` | Transformer tasks |
| schedule | `vibemind_schedule` | `schedule.*` |

## Hub Mode

When `USE_MINIBOOK_HUB=true`, Minibook becomes the central dispatch for ALL intents:

### EnrichmentPipeline (4 Stages)
1. **ContextGather** — Collects metadata from SQLite, conversation history
2. **IntentClassifier** — Classifies to event_type + payload
3. **SpaceRouter** — LLM-based routing decision (which space(s)?)
4. **TaskEnricher** — Builds per-agent enriched payloads

### Execution
- **Single-space:** Sync-wait ≤10s → return response
- **Multi-space:** Async-poll via ResultAggregator → acknowledge immediately
- **Fallback:** Direct `_process_sync()` if Minibook unavailable

## Background Workers

### DiscussionPollerWorker
Polls Minibook every 2s for responses. Delivers via voice injection or NotificationQueue. Timeout: 120s.

### SpaceMinibookResponder
Per-space: monitors @mentions → executes tool → posts comment back.

## Directory Structure

```
python/spaces/minibook/
├── agents/
│   ├── __init__.py
│   └── minibook_agent.py              # MinibookBackendAgent
├── config.py                          # MinibookConfig dataclass
├── minibook_hub.py                    # MinibookHub (central dispatch)
├── rachel_interface.py                # Rachel status tracking
├── result_aggregator.py               # Sync/async result aggregation
├── broadcast/                         # Electron event broadcasting
├── enrichment/
│   ├── pipeline.py                    # 4-stage EnrichmentPipeline
│   ├── context_gather.py              # Metadata collection
│   ├── space_router.py                # LLM-based routing
│   └── task_enricher.py               # Per-agent payload building
├── tools/
│   ├── minibook_tools.py              # 4 direct tools
│   ├── collaboration_tools.py         # 4 coordination tools
│   └── minibook_client.py             # HTTP REST wrapper
└── workers/
    └── minibook_workers.py            # DiscussionPoller + Responder
```

## Configuration

```bash
MINIBOOK_ENABLED=true                  # Enable minibook space
MINIBOOK_URL=http://localhost:3480     # Minibook REST API
USE_MINIBOOK_HUB=false                 # Hub mode (route ALL intents)
MINIBOOK_ENRICHMENT_MODEL=openai/gpt-4o-mini  # LLM for space routing
MINIBOOK_COLLABORATION_TIMEOUT=120     # Async poll timeout (seconds)
```

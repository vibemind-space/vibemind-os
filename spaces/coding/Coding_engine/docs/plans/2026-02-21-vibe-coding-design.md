# Design: Vibe-Coding Parallel zur Pipeline

**Date:** 2026-02-21
**Status:** Approved
**Phase:** 31

## Problem

The autonomous pipeline (run_engine.py) generates code from epic tasks, but some issues can't be fixed by the pipeline alone: UI tweaks, edge-case bugs, design adjustments. The user needs to intervene in real-time without stopping the pipeline.

## Requirements

1. **Dashboard-Chat** as the UI for user interventions
2. **Auto-Routing** selects the right Claude Code agent based on user intent
3. **WebSocket Streaming** shows live agent output (text, tool use, files changed)
4. **EventBus Integration** notifies the pipeline after each fix (CODE_FIXED)
5. **User-Managed Files** are protected from pipeline re-generation (validate-only)

## Architecture

```
Dashboard (VibeChat)
    |
    v  WebSocket
Backend (FastAPI)
    |
    +-- POST /api/v1/vibe/execute   (start vibe task)
    +-- WS   /ws/vibe/{project_id}  (stream agent output)
    +-- GET  /api/v1/vibe/history    (past vibe fixes)
    |
    +-- LLM Agent Router (Haiku classify -> agent name)
    +-- run_claude_agent() (cli_wrapper.py)
    |       |
    |       +-- claude -p --agent {name} --output-format stream-json
    |       +-- stdout line-by-line -> WebSocket frames
    |
    +-- After completion:
            +-- SharedState.user_managed_files.add(changed_files)
            +-- EventBus.publish(CODE_FIXED, source="user_vibe")

Pipeline (runs in parallel)
    |
    +-- TaskExecutor: skip regeneration for user_managed files
    +-- GeneratorAgent: validate-only for user_vibe events
    +-- Build/Test agents: still validate everything
```

## Component Details

### 1. Vibe API Route (`src/api/routes/vibe.py`)

New FastAPI route module with:
- `POST /api/v1/vibe/execute` - Accept user prompt, return task ID
- `WebSocket /ws/vibe/{project_id}` - Stream agent output frames
- `GET /api/v1/vibe/history` - List past vibe interventions

### 2. LLM Agent Router

Haiku-class LLM call to classify user intent into one of 12 agents.

```python
ROUTER_PROMPT = """You are an agent router. Given a user request about code,
select the best agent. Reply with ONLY the agent name, nothing else.

Agents:
- coder: Create/modify UI components, pages, styles, features
- debugger: Fix errors, trace bugs, analyze stack traces
- database-agent: Schema changes, migrations, seeding, PostgreSQL
- api-generator: REST endpoints, controllers, DTOs, guards
- test-runner: Run tests, analyze failures
- security-auditor: Security scan, find vulnerabilities (read-only)
- deployment-agent: Docker, containers, health checks
- code-reviewer: Code quality review, convention check

User request: {prompt}

Agent:"""
```

- Model: Haiku (~200ms, ~$0.001/call)
- Fallback: keyword matching if API call fails
- Validation: response must be one of the 8 agent names, else "coder"

### 3. WebSocket Streaming

Claude CLI with `--output-format stream-json` produces JSON-Lines on stdout.

Backend reads with `asyncio.create_subprocess_exec` + `process.stdout.readline()`.
Each line is parsed and sent as a WebSocket frame.

**Frame types:**

| Type | Content | Frontend shows |
|------|---------|----------------|
| `agent` | `{name: "coder"}` | Agent badge at top |
| `text` | `{content: "..."}` | Streaming text bubble |
| `tool_use` | `{tool, file, status}` | "Edited login.tsx" badge |
| `error` | `{message}` | Red error box |
| `complete` | `{files, session_id, success}` | Summary + done indicator |

### 4. Streaming Executor (`cli_wrapper.py`)

New method `execute_streaming()` that yields frames instead of returning a single response.

```python
async def execute_streaming(
    self,
    prompt: str,
    agent_name: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    max_turns: int = 10,
    session_id: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """Yields JSON frames from Claude CLI stream-json output."""
    ...
```

Uses `asyncio.create_subprocess_exec` instead of `subprocess.run` for non-blocking stdout reading.

### 5. `user_managed` in SharedState

```python
# src/mind/shared_state.py
class SharedState:
    def __init__(self):
        ...
        self.user_managed_files: set[str] = set()

    def mark_user_managed(self, file_paths: list[str]):
        self.user_managed_files.update(file_paths)

    def is_user_managed(self, file_path: str) -> bool:
        return file_path in self.user_managed_files
```

### 6. Pipeline Guard

**TaskExecutor** (before code generation):
```python
if any(shared_state.is_user_managed(f) for f in task.target_files):
    return await self._validate_only(task)
```

**GeneratorAgent** (in act()):
```python
if event.metadata.get("source") == "user_vibe":
    await self._publish(EventType.BUILD_STARTED, ...)
    return  # validate, don't regenerate
```

Same pattern as Phase 28 `som_managed` flag.

### 7. VibeChat UI (ReviewChat extension)

Extend existing `ReviewChat.tsx` with a third mode: "Vibe" alongside Chat and Debug.

- New WebSocket connection to `/ws/vibe/{project_id}`
- Renders streaming frames as they arrive
- Shows agent badge, text bubbles, tool-use badges
- Supports session continuity via `session_id`

### 8. EventBus Integration

After vibe fix completes:
```python
await event_bus.publish(
    EventType.CODE_FIXED,
    {
        "source": "user_vibe",
        "files": changed_file_paths,
        "agent": selected_agent_name,
        "session_id": response.session_id,
    }
)
```

Pipeline agents check `source == "user_vibe"` to skip re-generation.

## Files to Create/Modify

### New files:
| File | Purpose |
|------|---------|
| `src/api/routes/vibe.py` | API route + WS handler + LLM router |
| `dashboard-app/src/renderer/components/VibeChat/VibeChat.tsx` | Streaming chat UI |
| `dashboard-app/src/renderer/stores/vibeStore.ts` | Vibe session state |
| `dashboard-app/src/renderer/api/vibeAPI.ts` | WebSocket client |

### Modified files:
| File | Change |
|------|--------|
| `src/api/main.py` | Mount vibe router + WS endpoint |
| `src/autogen/cli_wrapper.py` | Add `execute_streaming()` method |
| `src/mind/shared_state.py` | Add `user_managed_files` set + methods |
| `src/agents/generator_agent.py` | Skip re-gen for `user_vibe` source |
| `dashboard-app/src/renderer/App.tsx` | Add VibeChat to layout |
| `dashboard-app/src/renderer/components/ReviewChat/ReviewChat.tsx` | Add Vibe mode tab |

## Build Sequence

1. Backend: `shared_state.py` (user_managed) - 3 lines
2. Backend: `cli_wrapper.py` (execute_streaming) - new async generator
3. Backend: `vibe.py` (API route + WS + LLM router) - main new file
4. Backend: `main.py` (mount routes) - 2 lines
5. Backend: `generator_agent.py` (pipeline guard) - 5 lines
6. Frontend: `vibeStore.ts` + `vibeAPI.ts` - state + WS client
7. Frontend: `VibeChat.tsx` - streaming UI component
8. Frontend: `ReviewChat.tsx` + `App.tsx` - integration
9. Tests: Backend unit tests + integration test

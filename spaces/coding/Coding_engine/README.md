# DaveFelix Coding Engine

Autonomous code generation system that generates complete production-ready projects from JSON requirements using 37+ specialized AI agents.

```
Requirements JSON  ──>  Epic Orchestrator  ──>  Complete NestJS/React Project
                           |
                    37+ AI Agents (Society of Mind)
                    Kilo CLI + GPT-5.4 / Claude
                    Docker Sandbox + VNC Preview
```

## Quick Start

```bash
# 1. Clone
git clone --recursive https://github.com/Flissel/DaveFelix-Coding-Engine.git
cd DaveFelix-Coding-Engine

# 2. Setup (checks prerequisites, prompts for API keys, builds Docker images)
bash setup.sh

# 3. Start
bash start.sh          # Core: PostgreSQL + Redis + API
bash start.sh --all    # Full: + Sandbox, Gitea, VSCode, Worker

# 4. Stop
bash stop.sh           # Stop all
bash stop.sh --clean   # Stop + wipe volumes
```

### Prerequisites

- **Docker Desktop** (includes Docker Compose v2)
- **Python 3.10+**
- **Node.js 18+**
- **Git**

### Required API Keys

| Key | Purpose | Get it |
|-----|---------|--------|
| `OPENAI_API_KEY` | Code generation (GPT-5.4) | [platform.openai.com](https://platform.openai.com/api-keys) |
| `GITHUB_TOKEN` | Git push, PR management | [github.com/settings/tokens](https://github.com/settings/tokens) |

Optional: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DISCORD_BOT_TOKEN` (see `.env.example`)

## Architecture

```
+-----------------------------------------------------------------+
|  LAYER 1: Society of Mind (37+ Agents)                          |
|  EventBus (push) + SharedState + Convergence Loop               |
|  src/agents/ + src/mind/ + src/engine/                          |
+-----------------------------------------------------------------+
        |
+-----------------------------------------------------------------+
|  LAYER 2: Epic Orchestrator + MCP Tools                         |
|  Parallel task pipeline, Kilo CLI, AutoGen 0.4+ teams           |
|  mcp_plugins/servers/grpc_host/                                 |
+-----------------------------------------------------------------+
        |
+-----------------------------------------------------------------+
|  LAYER 3: MCP Plugin Servers (20+)                              |
|  Playwright, Docker, Redis, GitHub, Prisma, Filesystem, etc.    |
|  mcp_plugins/servers/                                           |
+-----------------------------------------------------------------+
        |
+-----------------------------------------------------------------+
|  OUTPUT: Production-ready project                               |
|  TypeScript/NestJS + React + Prisma + Docker + Tests            |
+-----------------------------------------------------------------+
```

## Services & Ports

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| API Server | 8000 | http://localhost:8000 | FastAPI control plane |
| PostgreSQL | 5432 | — | Primary database |
| Redis | 6382 | — | Task queue + caching |
| Sandbox VNC | 6090 | http://localhost:6090 | Live preview (noVNC) |
| App Preview | 3100 | http://localhost:3100 | Generated app |
| Gitea | 3000 | http://localhost:3000 | Git server |
| VSCode | 8444 | http://localhost:8444 | Code editor (pw: `dev123`) |
| Automation UI | 8007 | http://localhost:8007 | Debug agent |

## Project Structure

```
DaveFelix-Coding-Engine/
|-- setup.sh / start.sh / stop.sh    # Setup & lifecycle scripts
|-- docker-compose.yml               # All services
|-- .env.example                     # Environment template
|-- requirements.txt                 # Python dependencies
|
|-- src/
|   |-- agents/                      # 37+ autonomous AI agents
|   |-- mind/                        # EventBus, SharedState, Orchestrator
|   |-- engine/                      # HybridPipeline, Slicer, Merger
|   |-- api/                         # FastAPI server (main.py)
|   |-- tools/                       # Claude CLI, sandbox, test runner
|   |-- mcp/                         # MCP Event Bridge
|   |-- validators/                  # Build, TypeScript, NoMock validators
|   +-- autogen/                     # Kilo CLI wrapper, task enricher
|
|-- mcp_plugins/servers/             # 20+ MCP tool servers
|   |-- grpc_host/                   # Epic orchestrator, task executor
|   |-- fungus_mcp/                  # Project context tools for Kilo
|   |-- playwright/ docker/ redis/   # Infrastructure tools
|   +-- github/ prisma/ npm/ ...     # Integration tools
|
|-- config/
|   |-- engine_settings.yml          # Models, timeouts, consolidation
|   |-- llm_models.yml               # LLM provider configuration
|   +-- society_defaults.json        # Agent feature flags
|
|-- infra/docker/                    # Dockerfiles (api, sandbox, worker)
|-- Data/                            # Project specs + generated output
|-- dashboard-app/                   # Electron/React dashboard (optional)
+-- .claude/skills/                  # 12 skill definitions for agents
```

## How It Works

### 1. Input: Requirements JSON

```json
{
  "name": "whatsapp-messaging-service",
  "type": "nestjs",
  "features": [
    {"id": "phone-registration", "priority": "high"},
    {"id": "real-time-messaging", "priority": "high"}
  ]
}
```

### 2. Epic Orchestrator Pipeline

1. **Parse** requirements into Epics (EPIC-001 to EPIC-007)
2. **Split** each Epic into ~50-60 consolidated tasks (schema, API, frontend, tests)
3. **Execute** tasks in parallel via Kilo CLI + GPT-5.4
4. **Verify** each task (TypeScript check, build, tests)
5. **Fix** failures automatically via SoM agent loop
6. **Deploy** to Docker sandbox with VNC preview

### 3. Output

Complete production-ready project:
- NestJS backend with all endpoints
- React frontend with all pages
- Prisma database schema + migrations
- JWT auth with RBAC
- Docker + CI/CD configs
- Integration tests (no mocks)

## Configuration

### engine_settings.yml

```yaml
models:
  generation: gpt-5.4     # Primary code gen
  fixing: gpt-5.4         # Bug fixing
  planning: gpt-5.4-mini  # Task planning

generation:
  max_parallel_tasks: 4
  consolidation_mode: feature  # granular|endpoint|feature
  max_task_retries: 3
```

### LLM Providers

The engine supports multiple LLM backends:
- **OpenAI** (GPT-5.4) — primary, via Kilo CLI
- **Anthropic** (Claude) — via Agent SDK
- **OpenRouter** — free models for secondary tasks
- **Ollama** — local models (qwen2.5-coder)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/projects` | GET/POST | Project management |
| `/api/v1/jobs` | POST | Start generation job |
| `/api/v1/dashboard/generation/{id}/pause` | POST | Pause generation |
| `/api/v1/dashboard/generation/{id}/resume` | POST | Resume with feedback |
| `/ws` | WS | Real-time dashboard updates |

## Development

```bash
# Run tests
pytest

# Run specific test
pytest tests/mind/test_push_architecture.py -v

# View API logs
docker compose logs -f api

# View sandbox logs
docker compose logs -f sandbox

# Rebuild API container after code changes
docker compose build api && docker compose up -d api
```

## Connected Projects

| Project | Purpose |
|---------|---------|
| [Minibook](https://github.com/Flissel/minibook) | Agent collaboration (legacy mode) |
| [DaveLovable](https://github.com/Flissel/DaveLovable) | Vibe coding UI |
| [OpenClaw](../../openclaw) | Master orchestrator gateway |

## License

MIT

# Tahlamus System Startup Guide

## Quick Start

```bash
# Single command — starts the unified brain server
python -m web.brain_server
```

Open http://localhost:5000 — all dashboards, API, and WebSocket chat are served from one process.

## Docker

```bash
docker-compose up
```

## What Starts

The unified brain server (`web/brain_server.py`) initializes:

| Component | Description |
|-----------|-------------|
| **RadialAttentionNetwork** | 5-ring network with 10 bridges, 29 hooks |
| **AgentLoop** | Autonomous FSM (9-phase cognitive loop) |
| **ContinuousThinkingEngine** | Background thought generation (500-thought buffer) |
| **MultiLLMRouter** | GPT-4o, DeepSeek R1, Claude 3.5, Gemini Flash |
| **BrainFrequencyController** | Delta/theta/alpha/beta/gamma mode switching |
| **MoltbookStore** | Semantic index with 384-dim embeddings |
| **ExperienceBuffer** | Replay buffer for sleep training |

## Dashboards

| URL | Name | Features |
|-----|------|----------|
| `http://localhost:5000/` | Brain Dashboard | Gates, goals, CTM, chat, strategies |
| `http://localhost:5000/brain` | Unified Brain | SVG visualization, rings, bridges, LLM chat |
| `http://localhost:5000/radial` | Radial Dashboard | 10 bridges, 5 rings, 29 hooks, modulation |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health check |
| `/api/radial/state` | GET | Current radial network state |
| `/api/radial/stream` | GET (SSE) | Live bridge/ring/modulation stream at 2Hz |
| `/api/modulation` | GET | All 29 hook values + 4 factors |
| `/api/experience-buffer/stats` | GET | Experience buffer statistics |
| `/api/cortex/thoughts` | GET | Recent background thoughts |
| `/api/brain/cognitive_loop` | GET | Cognitive loop phase |
| `/api/brain/frequency` | GET | Frequency mode |
| `/ws/chat` | WebSocket | Chat with brain-state-aware GPT-4o |

## Environment Variables

Create `.env` in project root:

```env
OPENROUTER_API_KEY=sk-or-v1-...    # Required for LLM routing

# Optional
ENABLE_COGNITIVE_LOOP=true          # 9-phase cognitive loop
ENABLE_AGENT_LOOP=true              # Autonomous agent FSM
```

## Health Check

```bash
curl http://localhost:5000/health
```

## Port Configuration

Default port is 5000. Change in `web/brain_server.py` or via environment variable.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'web'` | Run from project root: `python -m web.brain_server` |
| Port 5000 in use | `netstat -ano \| findstr "5000"` then `taskkill /PID <PID> /F` |
| No LLM responses in chat | Check `OPENROUTER_API_KEY` in `.env` |
| SSE stream not connecting | Check browser console; ensure `/api/radial/stream` returns data |

## Legacy Services

Old standalone servers are preserved in `web/legacy/` for reference but are no longer needed:
- `web/legacy/brain_dashboard_server.py` (replaced by unified server)
- `web/legacy/autonomous_swarm_server.py` (replaced by unified server)

## Testing

```bash
pytest tests/ -v                            # Full suite (1981+ tests)
pytest tests/test_core.py -v                # Core routing
pytest tests/test_phase7_modules.py -v      # Phase C neuroscience modules
pytest tests/test_phase_d_modules.py -v     # Phase D modules (6)
pytest tests/test_phase_e_modules.py -v     # Phase E modules (9)
pytest tests/test_phase_f_modules.py -v     # Phase F modules (14)
```

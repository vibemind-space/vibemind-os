# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

### Startup

```bash
# Unified brain server (all dashboards + API + WebSocket chat)
python -m web.brain_server                      # Port 5000

# Or via Docker
docker-compose up

# Testing
pytest tests/ -v                                # Full suite (1981+ tests)
pytest tests/test_core.py -v                    # Core routing tests
pytest tests/test_phase7_modules.py -v          # 43 neuroscience modules
```

### Health Check

```bash
curl http://localhost:5000/health
```

### Dashboards (all on port 5000)

| Route | Dashboard |
|-------|-----------|
| `/` | Brain Dashboard (gates, goals, CTM, chat, strategies) |
| `/brain` | Unified Brain (SVG visualization, rings, bridges, chat) |
| `/radial` | Radial Dashboard (10 bridges, 5 rings, 29 hooks, modulation) |

## Project Overview

**Tahlamus** is a brain-inspired cognitive AI system built from 43 neuroscience modules with:

- **5-ring Radial Attention Network**: Sensory(64D) → Pattern(128D) → Semantic(256D) → Abstract(256D) → Meta(128D)
- **10 neuromodulation bridges**: neuromod, cortex, limbic, sleep/wake, motor, defense, memory, integration, visceral, social
- **ModulationContext with 29 hooks**: 4 composite factors (attention_gain, precision_boost, ffn_throughput, threshold_mod)
- **Thalamic gating** with 10 modalities (6 sensory + 4 conversation trace)
- **3-layer hierarchical routing**: TaskFeatureRouter → ConversationPathPlanner → DecisionRouter
- **Multi-CTM Ensemble** with 4 specialized cognitive domains
- **LLM integration**: GPT-4o (communication), DeepSeek R1 (reasoning), Claude 3.5 (planning), Gemini Flash (memory)
- **9-phase Cognitive Loop**: perceive → appraise → remember → attend → modulate → reason → reflect → learn → consolidate
- **V2 Agent Loop**: autonomous FSM with sensors, actions, goals, motivation, safety
- **Chat with brain state**: GPT-4o responses colored by live emotional/neuromodulatory state

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                   BRAIN SERVER (FastAPI :5000)                   │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ AgentLoop   │  │ Radial       │  │ ContinuousThinking     │ │
│  │ (FSM)       │  │ Attention    │  │ Engine (background)    │ │
│  │             │  │ Network      │  │                        │ │
│  │ perceive    │  │              │  │ 500 thought buffer     │ │
│  │ → appraise  │  │ 5 Rings      │  │ Evolutionary selection │ │
│  │ → remember  │  │ 10 Bridges   │  │ 384-dim embeddings     │ │
│  │ → attend    │  │ 29 Hooks     │  │                        │ │
│  │ → modulate  │  │ 4 Factors    │  └────────────────────────┘ │
│  │ → reason    │  │              │                              │
│  │ → reflect   │  │ Predictive   │  ┌────────────────────────┐ │
│  │ → learn     │  │ Coding +     │  │ MultiLLMRouter         │ │
│  │ → consol.   │  │ Hebbian      │  │ GPT-4o / DeepSeek R1   │ │
│  └─────────────┘  └──────────────┘  │ Claude 3.5 / Gemini    │ │
│                                      └────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  43 Neuroscience Modules (Phase C-F)                     │   │
│  │  PFC, ACC, OFC, Amygdala, VTA, LC, Raphe, LHb, PAG,     │   │
│  │  Claustrum, RF, BF, Septal, IO, Mammillary, BNST, PBN,  │   │
│  │  SN, ZI, RN, TMN, PPN, VP, NTS, Olfactory, Fusiform,    │   │
│  │  TPJ, PPC, CorticalColumn, Pineal, CorpusCallosum, ...   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Critical Files

### Core Routing
- `core/thalamo_pc_adaptive.py` — Hebbian learning + homeostasis (10 modalities)
- `core/task_feature_router.py` — Layer 1: Feature extraction
- `core/conversation_path_planner.py` — Layer 2: Graph-based planning
- `core/decision_router.py` — Layer 3: Multi-target routing (10x4 matrix)
- `core/hierarchical_planner.py` — Integration of all layers

### Radial Attention Network
- `core/radial_attention.py` — 5-ring network + DualProcessRouter
- `core/modulation_context.py` — 29 hooks → 4 composite factors
- `core/hebbian_plasticity.py` — Live attention bias updates
- `core/experience_buffer.py` — FIFO replay for sleep training
- `core/radial_sleep_trainer.py` — 4-loss backprop during DreamMode

### 10 Bridges (each has State dataclass + Bridge class)
- `core/neuromodulation_bridge.py` — DA, NE, 5-HT, ACh (VTA, LC, Raphe, BF, LHb)
- `core/cortex_bridge.py` — PFC bias, ACC conflict, OFC value
- `core/limbic_bridge.py` — Valence, arousal, threat, salience (Amygdala, NAcc, Insula, Hypothalamus)
- `core/sleep_wake_bridge.py` — Arousal, histamine, melatonin (RF, TMN, Pineal, PPN)
- `core/motor_bridge.py` — Model confidence, action tendency (Cerebellum, SN, ZI, RN, PPC)
- `core/defense_bridge.py` — Fight/flight/freeze (PAG, PBN, BNST)
- `core/memory_bridge.py` — Theta, encoding (Septal, Olfactory, BF)
- `core/integration_bridge.py` — Cross-modal, consciousness (Claustrum, RF, BF)
- `core/visceral_bridge.py` — Interoception, autonomic (NTS, VP)
- `core/social_perception_bridge.py` — Theory of mind, face (TPJ, Fusiform)

### V2 Systems
- `core/agent_loop.py` — Agent FSM (IDLE/THINKING/ACTING/STOPPED)
- `core/sensor_systems.py` — 11 sensor/fusion modules
- `core/action_systems.py` — 7 action/approval modules
- `core/goal_management.py` — Goal hierarchy + conflict resolution
- `core/motivation_drives.py` — Curiosity, competence, homeostatic
- `core/safety_regulation.py` — Autonomy budget, safety governor
- `core/personality.py` — Personality model, emotional expression
- `core/language_center.py` — Brain language center, context window
- `core/resilience.py` — Graceful degradation, self-healing

### Web Server
- `web/brain_server.py` — FastAPI server (port 5000), all routes + state init
- `web/streams/chat.py` — WebSocket chat: GPT-4o + semantic thought matching + brain state
- `web/routers/radial.py` — SSE stream for bridges/rings/modulation at 2Hz
- `web/templates/unified_brain_dashboard.html` — SVG brain visualization

### Production
- `production/production_planner.py` — Production routing + dream cycle
- `production/unified_brain_service.py` — Legacy unified service
- `configs/default.yaml` — All configuration (radial, bridges, hooks, etc.)

## Key Invariants

1. **Gates sum to 1.0** — Softmax normalization, test after core routing changes
2. **ModulationContext factors clamped to [0.3, 3.0]** — Safety bounds
3. **1-tick delay on bridges** — State computed after forward, used on NEXT forward
4. **All bridge hooks `if state:` guarded** — Zero breaking changes if bridge disabled

## Development Guidelines

```bash
# After modifying core/
pytest tests/test_core.py -v

# After modifying bridges
pytest tests/test_neuromodulation_bridge.py tests/test_cortex_bridge.py tests/test_limbic_bridge.py -v

# After modifying radial attention
pytest tests/test_radial_production.py -v

# Full neuroscience modules
pytest tests/test_phase7_modules.py tests/test_phase_d_modules.py tests/test_phase_e_modules.py tests/test_phase_f_modules.py -v
```

## Environment Setup

```bash
# Python 3.11 (pyenv)
pip install -r requirements.txt

# Required env vars (.env)
OPENROUTER_API_KEY=sk-or-v1-...   # Required for LLM (GPT-4o, etc.)
```

## Key Documentation

| Document | Purpose |
|----------|---------|
| `docs/architecture.md` | System architecture diagram |
| `docs/STRUCTURE.md` | File/directory structure |
| `docs/100_PUNKTE_PLAN_V2.md` | V2 development roadmap |
| `docs/SYSTEM_STARTUP_GUIDE.md` | Server startup guide |
| `docs/WEB_DASHBOARD_GUIDE.md` | Dashboard features |
| `configs/default.yaml` | All configuration values |

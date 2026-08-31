# Brain Space (Tahlamus)

Neuroscience-inspired cognitive routing system. This is a **standalone submodule** with its own microservices architecture — not a traditional VibeMind backend agent.

## Architecture

```
Git Submodule: github.com/Flissel/the_brain
    ↓
5 Microservices:
    ├── Brain Server     (port 5000)  — Central unified brain + dashboards
    ├── Swarm Server     (port 5002)  — 14 cognitive agents (AutoGen)
    ├── Memory API       (port 8001)  — Supermemory integration
    ├── Production API   (port 5001)  — Legacy REST API
    └── Dashboard        (port 5000)  — Brain visualization + chat
```

## Key Facts

| Property | Value |
|----------|-------|
| **Backend Agent** | None (standalone microservices) |
| **Submodule** | `the_brain/` (git: github.com/Flissel/the_brain) |
| **Accuracy** | 77% routing accuracy (10×4 trained matrix) |
| **Learning** | Continuous Hebbian plasticity |

## Core Components

### 5-Ring Radial Attention Network
Sensory (64D) → Pattern (128D) → Semantic (256D) → Abstract (256D) → Meta (128D)

### 10 Neuromodulation Bridges
Neuromod, Cortex, Limbic, Sleep/Wake, Motor, Defense, Memory, Integration, Visceral, Social

### Thalamic Gating (10 Modalities)
- 6 sensory: vision, audio, touch, taste, vestibular, threat
- 4 conversation: tool_trace, temporal_pattern, error_signal, success_signal

### 3-Layer Hierarchical Routing
1. TaskFeatureRouter (feature extraction)
2. ConversationPathPlanner (path planning)
3. DecisionRouter (final decision)

### Multi-CTM Ensemble (4 Domains)
Spatial CTM, Logic CTM, Temporal CTM, Value CTM

### 43 Neuroscience Modules (Phases C–F)
PFC, ACC, OFC, Amygdala, VTA, LC, Raphe, Claustrum, Hippocampus, Cerebellum, and more.

### 9-Phase Cognitive Loop
Perceive → Appraise → Remember → Attend → Modulate → Reason → Reflect → Learn → Consolidate

## LLM Integration

| Model | Role |
|-------|------|
| GPT-4o | Communication |
| DeepSeek R1 | Reasoning |
| Claude 3.5 | Planning |
| Gemini Flash | Memory |

## 14 Cognitive Agents (AutoGen Swarm)

Feature-based agents running on port 5002 via AutoGen swarm architecture.

## Startup

```bash
cd python/spaces/brain/the_brain
python -m web.brain_server                # Port 5000 (all services)
# Or: START_ALL_SERVICES.bat
```

## Dashboards

| URL | View |
|-----|------|
| `http://localhost:5000` | Main dashboard |
| `http://localhost:5000/brain` | Brain visualization |
| `http://localhost:5000/radial` | Radial dashboard (bridges, rings, hooks) |

## 3D UI (Electron)

The Brain space has a dedicated 3D scene in the VibeMind multiverse:
- Organic deformed brain mesh with vertex displacement
- 60 neuron particles with synaptic connection lines
- Brain stem and floating thought bubbles
- Pulsing animation and synapse flicker effects

**Tab:** 🧠 The Brain → navigates camera to brain scene.

## Directory Structure

```
python/spaces/brain/
└── the_brain/               # Git submodule
    ├── web/                 # Brain Server (Flask)
    ├── agents/              # 14 cognitive agents
    ├── core/                # Routing, gating, modulation
    ├── memory/              # Supermemory integration
    └── dashboards/          # Web visualizations
```

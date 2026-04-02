# Tahlamus Brain System - Architecture Diagrams

## 1. Service Architecture and Data Flow

```mermaid
flowchart TB
    subgraph CLIENTS["External Clients"]
        CLI["CLI / Scripts"]
        WEB["Web Browser"]
        SWARM_CLIENT["Swarm Agents"]
    end

    subgraph SERVICES["Service Layer"]
        DASH["Brain Dashboard Server<br/>:5000 / :5004<br/>Web UI + /api/brain/* proxy"]
        UNIFIED["Unified Brain Service<br/>:5003<br/>Central Brain Instance"]
        PROD["Production API Server<br/>:5001<br/>Predictions API"]
        SWARM["Swarm Server<br/>:5002<br/>Autonomous Swarm"]
    end

    subgraph BRAIN_INSTANCE["Brain Instance (core/)"]
        direction TB

        subgraph LAYER_HIERARCHY["3+1 Layer Routing Hierarchy"]
            direction TB
            L1["Layer 1: TaskFeatureRouter<br/>10 modalities<br/>(6 sensory + 4 conversation trace)"]
            L2["Layer 2: ConversationPathPlanner<br/>Optimal conversation path planning"]
            L3["Layer 3: DecisionRouter<br/>Action routing + feedback propagation"]
            L4["Layer 4: TemporalRouter<br/>Temporal pattern processing<br/>Oscillator pipeline"]
            L1 --> L2 --> L3 --> L4
        end

        subgraph COGNITIVE["Cognitive Loop Engine"]
            CL["9-Phase Cognitive Loop<br/>(see Diagram 2)"]
        end

        subgraph MEMORY["Memory Systems"]
            WM["Working Memory"]
            EM["Episodic Memory"]
            TM["Temporal Memory"]
            SM["Semantic Memory"]
        end

        subgraph MODULATION["Modulation & Control"]
            NEURO["Neuromodulation<br/>DA / 5-HT / NE"]
            FREQ["Brain Frequency Controller<br/>ALPHA BETA GAMMA<br/>DELTA THETA"]
            HOMEO["Homeostatic Regulation"]
        end

        subgraph CTM_ENSEMBLE["Multi-CTM Ensemble"]
            LCTM["LogicCTM"]
            TCTM["TemporalCTM"]
            SCTM["SpatialCTM"]
            VCTM["ValueCTM"]
        end

        subgraph ADVANCED["Phase 6 Advanced Modules"]
            TOM["Theory of Mind"]
            CAUSAL["Causal Reasoning"]
            CURIOUS["Intrinsic Curiosity"]
            SAFETY["Safety Layer"]
            EXPLAIN["Explanation Generator"]
            SELF_IMP["Self-Improvement"]
            AUTO_GOAL["Autonomous Goal Generator"]
            MULTI_FUS["Multimodal Fusion"]
            FORMAL["Formal Verifier"]
            THOUGHT["Thought Decoder"]
            SENSORI["Sensorimotor Integration"]
        end

        subgraph PRODUCTION["Phase 7 Production"]
            HEARTBEAT["Brain Heartbeat<br/>Autonomous background processing"]
            SNAPSHOT["Brain Snapshot / Restore<br/>State persistence"]
            EVENTBUS["Event Bus<br/>Inter-module communication"]
            SHUTDOWN["Graceful Shutdown"]
            HEALTH["Health-check Startup"]
        end
    end

    %% Client connections
    WEB -->|HTTP| DASH
    CLI -->|HTTP| PROD
    CLI -->|HTTP| UNIFIED
    SWARM_CLIENT -->|HTTP| SWARM

    %% Service interconnections
    DASH -->|"proxy /api/brain/*"| UNIFIED
    PROD -->|"/predict"| UNIFIED
    SWARM -->|"tasks"| UNIFIED

    %% Request flow through brain
    UNIFIED -->|"1. task arrives"| LAYER_HIERARCHY
    LAYER_HIERARCHY -->|"2. routed task"| COGNITIVE
    COGNITIVE -->|"3. uses subsystems"| MEMORY
    COGNITIVE -->|"4. modulation"| MODULATION
    COGNITIVE -->|"5. CTM selection"| CTM_ENSEMBLE
    COGNITIVE -->|"6. advanced reasoning"| ADVANCED

    %% Production infrastructure
    HEARTBEAT -.->|"monitors"| BRAIN_INSTANCE
    EVENTBUS -.->|"connects"| COGNITIVE
    EVENTBUS -.->|"connects"| MEMORY
    EVENTBUS -.->|"connects"| MODULATION
    SNAPSHOT -.->|"persists"| MEMORY

    %% Key REST endpoints
    UNIFIED ---|"/predict POST<br/>/feedback POST<br/>/brain_state<br/>/statistics<br/>/heartbeat_status<br/>/emotional_state<br/>/homeostatic_state<br/>/memory_state<br/>/sensory_extract POST<br/>/goal_graph_state<br/>/cognitive_loop_state<br/>/neuromodulation_state<br/>/consciousness_state<br/>/frequency_mode<br/>/register<br/>/available_features"| CLIENTS

    style CLIENTS fill:#e1f5fe,stroke:#0288d1,color:#000
    style SERVICES fill:#fff3e0,stroke:#f57c00,color:#000
    style BRAIN_INSTANCE fill:#f3e5f5,stroke:#7b1fa2,color:#000
    style LAYER_HIERARCHY fill:#e8f5e9,stroke:#388e3c,color:#000
    style COGNITIVE fill:#fce4ec,stroke:#c62828,color:#000
    style MEMORY fill:#e0f2f1,stroke:#00796b,color:#000
    style MODULATION fill:#fff9c4,stroke:#f9a825,color:#000
    style CTM_ENSEMBLE fill:#e3f2fd,stroke:#1565c0,color:#000
    style ADVANCED fill:#fbe9e7,stroke:#d84315,color:#000
    style PRODUCTION fill:#f1f8e9,stroke:#558b2f,color:#000
```

---

## 2. Cognitive Loop with All Subsystems

```mermaid
flowchart TB
    TASK_IN(["Task arrives via /predict"])

    subgraph LOOP["Cognitive Loop - 9 Phases (max 2 reflection iterations)"]
        direction TB

        subgraph P1["Phase 1: PERCEIVE"]
            PERCEIVE["SensoryPreprocessor.extract(text)<br/>10 channels: 6 sensory + 4 conv trace"]
            SENSE_OUT["SensoryFeatures"]
            PERCEIVE --> SENSE_OUT
        end

        subgraph P2["Phase 2: APPRAISE EMOTION"]
            APPRAISE["EmotionalSystem.appraise_task()<br/>Valence-Arousal model"]
            EMO_STATE["EmotionalState<br/>valence + arousal"]
            APPRAISE --> EMO_STATE
        end

        subgraph P3["Phase 3: REMEMBER"]
            REMEMBER["MemoryManager.get_context()<br/>similar_tasks: list of (dict, score)"]
            MEM_CTX["Memory Context<br/>biases routing weights"]
            REMEMBER --> MEM_CTX
        end

        subgraph P4["Phase 4: ATTEND"]
            ATTEND["10-Modality Attention + Gating<br/>Gate invariant: sum = 1.0 (softmax)"]
            ATT_OUT["Attention Output<br/>drives CTM selection"]
            ATTEND --> ATT_OUT
        end

        subgraph P5["Phase 5: MODULATE"]
            MODULATE["NeuromodulationSystem<br/>Dopamine: reward/motivation<br/>Serotonin: mood/inhibition<br/>Norepinephrine: arousal/attention"]
            MOD_FX["Neuromod Effects<br/>controls temperature<br/>exploration vs exploitation"]
            MODULATE --> MOD_FX
        end

        subgraph P6["Phase 6: REASON"]
            REASON["Multi-CTM Ensemble Reasoning"]
            LOGIC["LogicCTM"]
            TEMPORAL["TemporalCTM"]
            SPATIAL["SpatialCTM"]
            VALUE["ValueCTM"]
            PRED["Predictive Coding<br/>Hierarchical prediction errors"]
            ACTIVE["Active Inference<br/>Free energy minimization"]
            REASON --> LOGIC & TEMPORAL & SPATIAL & VALUE
            REASON --> PRED & ACTIVE
        end

        subgraph P7["Phase 7: REFLECT"]
            REFLECT["Consciousness Metrics<br/>Phi / IIT-inspired measurement"]
            REFL_DEC{"Reflection<br/>quality check"}
            REFLECT --> REFL_DEC
        end

        subgraph P8["Phase 8: LEARN"]
            LEARN["Meta-Learning System<br/>Adaptive learning rates<br/>Feedback to 6 subsystems:<br/>L3, neuromod, memory,<br/>meta-learning, L2, emotional"]
            LEARN_OUT["Updated weights + parameters"]
            LEARN --> LEARN_OUT
        end

        subgraph P9["Phase 9: CONSOLIDATE"]
            CONSOLIDATE["Memory Consolidation<br/>Working -> Episodic -> Semantic<br/>Temporal pattern storage"]
            RESULT["HierarchicalPrediction<br/>+ brain_gates"]
            CONSOLIDATE --> RESULT
        end

        %% Phase flow
        P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> P7

        %% Reflection loop-back (max 2 iterations)
        REFL_DEC -->|"quality OK"| P8
        REFL_DEC -->|"re-process<br/>(max 2x)"| P1

        P8 --> P9
    end

    %% Subsystem connections from outside
    subgraph SUBSYSTEMS["Supporting Subsystems"]
        direction TB

        subgraph MEM_SYS["Memory Systems"]
            WM2["Working Memory"]
            EM2["Episodic Memory"]
            TM2["Temporal Memory"]
            SM2["Semantic Memory"]
        end

        subgraph GOALS["Goal Management"]
            GG["Goal Graph<br/>Hierarchical goals<br/>get_critical_path()"]
            AGG["Autonomous Goal Generator"]
        end

        subgraph FREQ_CTRL["Frequency Control"]
            BFC["Brain Frequency Controller"]
            ALPHA["ALPHA: relaxed"]
            BETA["BETA: focused"]
            GAMMA["GAMMA: high-processing"]
            DELTA["DELTA: deep rest"]
            THETA["THETA: creative"]
            BFC --- ALPHA & BETA & GAMMA & DELTA & THETA
        end

        subgraph PHASE6_ADV["Phase 6 Advanced"]
            TOM2["Theory of Mind"]
            CAUSAL2["Causal Reasoning"]
            CURIOUS2["Intrinsic Curiosity"]
            SAFETY2["Safety Layer"]
            EXPLAIN2["Explanation Generator"]
            FORMAL2["Formal Verifier"]
        end

        subgraph ROUTING["Layer Hierarchy"]
            RL1["L1: TaskFeatureRouter"]
            RL2["L2: ConversationPathPlanner"]
            RL3["L3: DecisionRouter"]
            RL4["L4: TemporalRouter"]
            RL1 --> RL2 --> RL3 --> RL4
        end

        HOMEO2["Homeostatic Regulation<br/>Stability maintenance"]
    end

    %% Input/output
    TASK_IN --> P1
    RESULT --> TASK_OUT(["Response returned"])

    %% Subsystem links to phases
    MEM_SYS -.->|"context retrieval"| P3
    GOALS -.->|"goal context"| P4
    FREQ_CTRL -.->|"processing mode"| P5
    PHASE6_ADV -.->|"advanced reasoning"| P6
    ROUTING -.->|"layer routing"| P1
    HOMEO2 -.->|"stability signals"| P5
    MEM_SYS -.->|"consolidation"| P9

    style LOOP fill:#fce4ec,stroke:#c62828,color:#000
    style SUBSYSTEMS fill:#e8eaf6,stroke:#283593,color:#000
    style P1 fill:#e1f5fe,stroke:#0277bd,color:#000
    style P2 fill:#fce4ec,stroke:#c62828,color:#000
    style P3 fill:#e0f2f1,stroke:#00796b,color:#000
    style P4 fill:#fff9c4,stroke:#f9a825,color:#000
    style P5 fill:#f3e5f5,stroke:#6a1b9a,color:#000
    style P6 fill:#e8f5e9,stroke:#2e7d32,color:#000
    style P7 fill:#fff3e0,stroke:#e65100,color:#000
    style P8 fill:#e3f2fd,stroke:#1565c0,color:#000
    style P9 fill:#f1f8e9,stroke:#558b2f,color:#000
    style MEM_SYS fill:#e0f2f1,stroke:#00796b,color:#000
    style GOALS fill:#fff9c4,stroke:#f9a825,color:#000
    style FREQ_CTRL fill:#f3e5f5,stroke:#6a1b9a,color:#000
    style PHASE6_ADV fill:#fbe9e7,stroke:#d84315,color:#000
    style ROUTING fill:#e8f5e9,stroke:#388e3c,color:#000
```

---

## Quick Reference

### Data Flow Summary

```
Client Request
    |
    v
Service Layer (:5000/:5001/:5002/:5003)
    |
    v
Layer 1: TaskFeatureRouter (10 modalities)
    |
    v
Layer 2: ConversationPathPlanner
    |
    v
Layer 3: DecisionRouter
    |
    v
Layer 4: TemporalRouter (oscillator pipeline)
    |
    v
Cognitive Loop (9 phases, max 2 reflection iterations)
    |   perceive -> appraise_emotion -> remember -> attend
    |   -> modulate -> reason -> reflect -> learn -> consolidate
    |
    v
HierarchicalPrediction + brain_gates (sum = 1.0)
```

### Port Assignments

| Port | Service                  | Purpose                        |
|------|--------------------------|--------------------------------|
| 5000 | Brain Dashboard Server   | Web UI + API proxy             |
| 5001 | Production API Server    | Predictions API                |
| 5002 | Swarm Server             | Autonomous swarm coordination  |
| 5003 | Unified Brain Service    | Central brain instance         |
| 5004 | Dashboard (alternate)    | Secondary dashboard binding    |

### Gate Invariant

All `brain_gates` arrays MUST sum to 1.0 (enforced via softmax normalization). This applies to:
- `RoutingState.routing_weights` (can be ndarray or list)
- `WorkingMemoryEntry.brain_gates` (can be list or ndarray)
- `EpisodicMemoryEntry.brain_gates` (can be list or ndarray)

### Feedback Propagation Targets

The closed feedback loop in `production_planner.py` propagates to 6 systems:
1. Layer 3 (DecisionRouter)
2. Neuromodulation
3. Memory
4. Meta-Learning
5. Layer 2 (ConversationPathPlanner)
6. Emotional System

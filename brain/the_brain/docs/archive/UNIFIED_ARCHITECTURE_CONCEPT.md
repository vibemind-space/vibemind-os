# Tahlamus: Unified Architecture Concept

**Stand**: Oktober 2025 (nach Phase 13 - Semantic Coherence)
**Frage**: Wie bringt man all die Scripte in ein sinnvolles Gesamtkonzept?

---

## Das zentrale Problem

**Aktuell**: 41 Module, viele Demos, keine klare Story.
**Ziel**: Ein kohärentes System mit klaren Verantwortlichkeiten und Datenfluss.

---

## Die Kern-Idee: Brain as a Service (BaaS)

Tahlamus ist ein **kognitives Routing-System**, das lernt, wie ein Agent-Brain Entscheidungen trifft:

```
INPUT: "Deploy Docker container with health checks"
  |
  v
[TAHLAMUS BRAIN] - Multi-Layer Cognitive System
  |
  v
OUTPUT: {
  decision: "retry",
  confidence: 0.85,
  reasoning: "Docker expertise activated, health checks require validation",
  semantic_status: "GREEN" (brains agree)
}
```

Das ist **nicht** ein LLM-Wrapper. Das ist ein **Meta-Cognitive System**, das:
1. Aus Konversationen lernt (39 Sessions)
2. Optimal Decisions vorhersagt (77% Accuracy)
3. Sich selbst überwacht (Real-time Monitoring)
4. Semantische Wahrheit validiert (Phase 13 - NEU!)

---

## Das 5-Layer Architecture Model

Jedes Modul gehört zu **genau einer** der 5 Layers:

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 5: USER INTERFACE                                     │
│ - Web Dashboard (brain_dashboard_server.py)                 │
│ - REST API (api_server.py)                                  │
│ - Chat Interface (chat_with_semantic_coherence.py)          │
└─────────────────────────────────────────────────────────────┘
                            |
                            v
┌─────────────────────────────────────────────────────────────┐
│ LAYER 4: ORCHESTRATION                                      │
│ - Production Planner (production_planner.py)                │
│ - Hierarchical Planner (hierarchical_planner.py)            │
│ - Multi-Brain Swarm (multi_brain_swarm.py)                  │
└─────────────────────────────────────────────────────────────┘
                            |
                            v
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: COGNITIVE PROCESSING                               │
│ - Task Feature Router (Layer 1 - Feature Extraction)        │
│ - Conversation Path Planner (Layer 2 - Path Prediction)     │
│ - Decision Router (Layer 3 - Multi-Target Routing)          │
│ - Semantic Coherence (Phase 13 - Truth Validation)          │
│ - Meta-Cognitive System (S_(n+1) Pattern Analysis)          │
└─────────────────────────────────────────────────────────────┘
                            |
                            v
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: LEARNING & MEMORY                                  │
│ - Hippocampus (Episodic Memory - Novel Failures)            │
│ - Strategy Library (Proven Success Patterns)                │
│ - CTM Async Reasoner (Deep Reasoning)                       │
│ - Memory Systems (Working/Declarative/Procedural)           │
│ - Temporal Memory (Time-based Patterns)                     │
└─────────────────────────────────────────────────────────────┘
                            |
                            v
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: FOUNDATION (Thalamic Routing)                      │
│ - Thalamo-PC Adaptive (Hebbian Learning, Homeostasis)       │
│ - Multi-Target Router (10×4 Routing Matrix)                 │
│ - LLM Router (OpenRouter, OpenAI, Anthropic, Infinite Chat) │
└─────────────────────────────────────────────────────────────┘
```

**Prinzip**: Jede Layer nutzt **nur** die Layer darunter. Keine Layer-Übersprünge!

---

## Datenfluss: Von User Input zu Decision

### Beispiel: "Deploy Docker container with health checks"

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: USER INTERFACE (Layer 5)                            │
└─────────────────────────────────────────────────────────────┘
User → Web Dashboard → POST /predict
  {
    "task": "Deploy Docker container with health checks",
    "context": {"urgency": "high"}
  }

                    ↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 2: ORCHESTRATION (Layer 4)                             │
└─────────────────────────────────────────────────────────────┘
ProductionPlanner.predict(task)
  |
  ├─> HierarchicalPlanner.predict(task)
  |     |
  |     ├─> Layer 1: TaskFeatureRouter.extract_features(task)
  |     |     → {complexity: 0.65, domain: "docker", urgency: "high"}
  |     |
  |     ├─> Layer 2: ConversationPathPlanner.predict_path(task)
  |     |     → ["suggest deployment", "validate health checks", "retry if needed"]
  |     |
  |     └─> Layer 3: DecisionRouter.route(modalities)
  |           → {primary: "retry", alternatives: ["suggest", "wait"]}
  |
  └─> MultiBrainSwarm.collect_brain_votes(task)
        → 5 Brains vote, Semantic Coherence validates

                    ↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 3: COGNITIVE PROCESSING (Layer 3)                      │
└─────────────────────────────────────────────────────────────┘

3a. TaskFeatureRouter (Layer 1)
    Input: "Deploy Docker container with health checks"
    LLM Call → MultiLLMRouter.extract_features()
    Output: {
      "task_type": "docker",
      "complexity": 0.65,
      "processing_mode": "analytical",
      "keywords": ["deploy", "docker", "health", "checks"]
    }

3b. ConversationPathPlanner (Layer 2)
    Input: Task features + 39 session logs
    ConversationGraph.predict_optimal_path()
    Output: {
      "predicted_path": ["suggest", "retry", "success"],
      "confidence": 0.78
    }

3c. DecisionRouter (Layer 3)
    Input: 10 modality activations
    Multi-Target Routing Matrix (10×4)
    Output: {
      "primary": {"type": "retry", "confidence": 0.85},
      "alternatives": [
        {"type": "suggest", "confidence": 0.60},
        {"type": "wait", "confidence": 0.30}
      ]
    }

3d. MultiBrainSwarm (Phase 13 - Semantic Coherence)
    Input: Task + 5 specialized brains
    Each brain votes: Brain-0 (Docker): "retry", Brain-1 (Github): "suggest", ...

    BrainAnswers → SemanticCoherenceLayer.compute_coherence()
    Output: {
      "consensus": "retry",
      "coherence_K": 0.814,
      "disagreement_U": 0.001,
      "truth_stability": 0.752,
      "semantic_status": "GREEN"  ← Brains agree!
    }

3e. MetaCognitiveSystem (S_(n+1) Level)
    Input: SwarmDecision + BrainAnswers
    Analyze patterns: drift, contradictions, bias
    Output: {
      "detected_patterns": [],
      "policy_updates": {"Brain-0": +0.05}  ← Increase Docker expert weight
    }

                    ↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 4: LEARNING & MEMORY (Layer 2)                         │
└─────────────────────────────────────────────────────────────┘

4a. Hippocampus (Episodic Memory)
    Check: Is this a novel failure?
    Decision: NO (similar Docker deployments seen 8 times)
    Action: Skip storage (memory efficiency: 7.7%)

4b. Strategy Library
    Query: Has "Docker + health checks + retry" worked before?
    Result: YES (13 proven strategies, this is #7)
    Boost confidence: 0.85 → 0.90

4c. CTM Async Reasoner (Deep Reasoning)
    Check complexity: 0.65 < 0.75 (threshold)
    Decision: Skip CTM (not complex enough)
    Action: Return fast prediction (<100ms)

4d. Memory Systems
    Working Memory: Store task in 30-second buffer
    Declarative Memory: Retrieve "Docker requires validation"
    Procedural Memory: Activate "retry-with-backoff" skill

                    ↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 5: FOUNDATION (Layer 1)                                │
└─────────────────────────────────────────────────────────────┘

5a. ThalamoPCAdaptive (Thalamic Routing)
    Input: 10 modality activations
    Gating: softmax([threat, vision, tool_trace, error_signal, ...])
    Output: g = [0.05, 0.10, 0.65, 0.15, ...]  ← tool_trace dominates!

    Hebbian Learning: Update weights based on success
    Homeostatic Tuning: Adjust thresholds

5b. Multi-Target Router (10×4 Matrix)
    Input: Modality gates g
    Matrix Multiplication: y = R @ g
    Output: [suggest: 0.60, retry: 0.85, wait: 0.30, terminate: 0.10]

    Continuous Learning: LR=0.005, update from feedback

5c. LLM Router (Infinite Chat)
    Check: user_id provided?
    YES → SupermemoryLLM (automatic semantic memory)
    Retrieve past Docker conversations → inject into prompt

    LLM Call: OpenRouter (claude-3.5-sonnet)
    Response: "Based on past Docker deployments, retry with validation..."

                    ↓

┌─────────────────────────────────────────────────────────────┐
│ STEP 6: FINAL OUTPUT (Layer 5)                              │
└─────────────────────────────────────────────────────────────┘
Response to User:
{
  "prediction": {
    "primary_action": "retry",
    "confidence": 0.90,
    "alternatives": ["suggest", "wait"]
  },
  "reasoning_chain": [
    "Task classified as docker deployment (complexity 0.65)",
    "5 brains voted: retry (2), suggest (2), wait (1)",
    "Semantic coherence: K=0.814, GREEN status (high agreement)",
    "Strategy #7 (Docker+health checks+retry) proven successful",
    "Prediction: RETRY with validation"
  ],
  "semantic_status": "GREEN",
  "coherence_metrics": {
    "K": 0.814,
    "U": 0.001,
    "truth_stability": 0.752
  },
  "execution_time_ms": 87
}
```

---

## Die 5 Kern-Prinzipien

### 1. **Separation of Concerns**
Jede Layer hat **eine** klare Verantwortung:
- Layer 5 (UI): Kommunikation mit User
- Layer 4 (Orchestration): Koordination der Subsysteme
- Layer 3 (Cognitive): Denken und Entscheiden
- Layer 2 (Memory): Lernen aus Erfahrung
- Layer 1 (Foundation): Grundlegende Routing-Logik

### 2. **Unidirectional Data Flow**
Daten fließen **immer** von oben nach unten und zurück:
```
User Input → Layer 5 → Layer 4 → Layer 3 → Layer 2 → Layer 1
                                                         |
User Output ← Layer 5 ← Layer 4 ← Layer 3 ← Layer 2 ← Layer 1
```

### 3. **Pluggable Components**
Jedes Modul ist **austauschbar**:
- SemanticCoherenceLayer kann deaktiviert werden (flag)
- CTM Async kann durch synchrones CTM ersetzt werden
- LLM Router kann verschiedene Provider nutzen (OpenRouter, OpenAI, Anthropic)
- Memory Systems können erweitert werden (neue Memory-Typen)

### 4. **Observable System**
Jede Layer ist **überwachbar**:
- MonitoringSystem trackt Brain-States
- ExecutionTracker loggt alle Decisions
- ConsciousnessMetrics misst Global Workspace
- Semantic Coherence validiert Wahrheit

### 5. **Continuous Learning**
System lernt auf **3 Ebenen**:
- Offline: Train routing matrix from synthetic tasks
- Meta-Learning: Learn from 39 session logs
- Continuous: Update matrix from production feedback (LR=0.005)

---

## Module-zu-Layer Mapping

### Layer 5: USER INTERFACE (3 Entry Points)

| Modul | Zweck | User Interaction |
|-------|-------|------------------|
| `web/brain_dashboard_server.py` | Real-time visualization | Browser UI at localhost:5000 |
| `production/api_server.py` | REST API (7 endpoints) | curl/Python client at localhost:5001 |
| `demos/chat_with_semantic_coherence.py` | Interactive chat | Terminal chat with semantic analysis |

**Gemeinsame Schnittstelle**: Alle 3 nutzen `ProductionPlanner.predict(task)`.

---

### Layer 4: ORCHESTRATION (3 Koordinatoren)

| Modul | Zweck | Koordiniert |
|-------|-------|-------------|
| `production/production_planner.py` | Main production class | HierarchicalPlanner + MultiBrainSwarm + Matrix versioning |
| `core/hierarchical_planner.py` | 3-layer integration | TaskFeatureRouter + ConversationPathPlanner + DecisionRouter |
| `core/multi_brain_swarm.py` | Multi-brain voting + semantic coherence | 5 Brains + SemanticCoherenceLayer + MetaBrain |

**Data Flow**:
```
ProductionPlanner
  ├─> HierarchicalPlanner (3-layer prediction)
  └─> MultiBrainSwarm (semantic validation)
```

---

### Layer 3: COGNITIVE PROCESSING (8 Denkmodule)

| Modul | Sub-Layer | Zweck |
|-------|-----------|-------|
| `core/task_feature_router.py` | 3.1 - Feature Extraction | Extract task features (complexity, domain, mode) |
| `core/conversation_path_planner.py` | 3.2 - Path Planning | Predict optimal action sequence from graph |
| `core/decision_router.py` | 3.3 - Decision Making | Multi-target routing (10×4 matrix) |
| `core/semantic_coherence.py` | **3.4 - Truth Validation (Phase 13)** | **Compute K, U, truth stability, traffic light** |
| `core/meta_brain.py` | 3.5 - Meta-Level Analysis | S_(n+1) pattern detection (drift, bias, contradictions) |
| `core/meta_router.py` | 3.5 - Meta-Cognitive Routing | 10-modality self-reflective routing |
| `core/conversation_graph.py` | 3.6 - State-Space Search | A* search over conversation states |
| `core/conversation_trace_encoder.py` | 3.6 - Trace Parsing | Parse session logs to feature vectors |

**Data Flow**:
```
TaskFeatureRouter → ConversationPathPlanner → DecisionRouter
                                                  |
                                                  v
                                          SemanticCoherenceLayer
                                                  |
                                                  v
                                            MetaCognitiveSystem
```

---

### Layer 2: LEARNING & MEMORY (8 Speichermodule)

| Modul | Memory Type | Zweck |
|-------|-------------|-------|
| `core/hippocampus.py` | Episodic | Novel failures only (7.7% efficiency) |
| `core/strategy_library.py` | Strategic | Proven success patterns (13 strategies) |
| `core/memory_systems.py` | Working/Declarative/Procedural | Short-term buffer + facts + skills |
| `core/temporal_memory.py` | Temporal | Time-based patterns |
| `core/supermemory_llm_client.py` | Semantic (Infinite Chat) | Automatic LLM memory injection |
| `core/ctm_async_reasoner.py` | Deep Reasoning | Background iterative thinking (5-15s) |
| `core/ctm_integration.py` | Deep Reasoning (Sync) | Synchronous continuous thought |
| `core/brain_monitor.py` | Execution History | Real-time tracking + intervention triggers |

**Gemeinsame Schnittstelle**: Alle nutzen `store()` und `retrieve()` Methoden.

---

### Layer 1: FOUNDATION (5 Basismodule)

| Modul | Zweck | Output |
|-------|-------|--------|
| `core/thalamo_pc_adaptive.py` | Thalamic gating + Hebbian learning | Modality gates g (sum=1.0) |
| `core/multi_target_router.py` | 10×4 routing matrix | 4 intervention weights |
| `core/multi_llm_router.py` | LLM provider abstraction | Feature extraction, classification |
| `core/config_loader.py` | YAML config loading | Model parameters |
| `core/thalamo_pc_live.py` | Base thalamic routing (legacy) | Gates without learning |

**Data Flow**:
```
ThalamoPCAdaptive → gates g → MultiTargetRouter → intervention weights
                                                         |
                                                         v
                                                   MultiLLMRouter
                                                   (for reasoning)
```

---

## Cognitive Systems (Phase 1-6) - Optional Extensions

Diese 6 Module sind **optionale Erweiterungen** (nicht in Production aktiv):

| Modul | Phase | Zweck | Status |
|-------|-------|-------|--------|
| `core/memory_systems.py` | 1 | Working/Declarative/Procedural | 🔬 RESEARCH |
| `core/predictive_coding.py` | 2 | Prediction error minimization | 🔬 RESEARCH |
| `core/attention_mechanisms.py` | 3 | Selective attention gating | 🔬 RESEARCH |
| `core/meta_learning.py` | 4 | Learning-to-learn | 🔬 RESEARCH |
| `core/dream_mode.py` | 5 | Offline consolidation | 🔬 RESEARCH (Brain Heartbeat nutzt es) |
| `core/neuromodulation.py` | 6 | Dopamine/Serotonin/Noradrenaline | 🔬 RESEARCH |

**Integration Point**: `HierarchicalPlanner` kann diese optional aktivieren via Feature Flags.

---

## Monitoring & Observability (Layer übergreifend)

Diese Module sind **Querschnittsfunktionen** (nutzen alle Layers):

| Modul | Zweck | Integration |
|-------|-------|-------------|
| `core/brain_monitor.py` | Real-time monitoring | Dashboard calls monitor.get_state() |
| `core/execution_tracker.py` | Execution history | ProductionPlanner logs all decisions |
| `core/consciousness_metrics.py` | Global Workspace metrics | Dashboard shows consciousness level |

**Data Flow**:
```
All Layers → MonitoringSystem → Dashboard/API
```

---

## Wie alles zusammenpasst: Das Große Bild

```
┌───────────────────────────────────────────────────────────────────────┐
│                          USER (Browser/API/Chat)                       │
└───────────────────────────────────────────────────────────────────────┘
                                    |
                    ┌───────────────┴───────────────┐
                    |                               |
            ┌───────v───────┐               ┌───────v───────┐
            │ Web Dashboard │               │   REST API    │
            │ localhost:5000│               │ localhost:5001│
            └───────┬───────┘               └───────┬───────┘
                    |                               |
                    └───────────────┬───────────────┘
                                    |
                    ┌───────────────v───────────────┐
                    │    ProductionPlanner          │
                    │  - Load routing matrix        │
                    │  - Continuous learning        │
                    │  - Matrix versioning          │
                    └───────────────┬───────────────┘
                                    |
                    ┌───────────────┴───────────────┐
                    |                               |
            ┌───────v────────┐             ┌────────v───────┐
            │ Hierarchical   │             │ Multi-Brain    │
            │    Planner     │             │     Swarm      │
            │   (3 Layers)   │             │  (5 Brains +   │
            │                │             │   Semantic     │
            │  Layer 1: ────┐│             │   Coherence)   │
            │  Feature      ││             │                │
            │  Extraction   ││             │ Phase 13 NEW! │
            │               ││             │                │
            │  Layer 2: ────┤│             │ - Coherence K  │
            │  Path         ││             │ - Truth Stable │
            │  Planning     ││             │ - Traffic Light│
            │               ││             └────────┬───────┘
            │  Layer 3: ────┤│                      |
            │  Decision     ││                      |
            │  Routing      ││             ┌────────v───────┐
            └───────┬───────┘│             │   MetaBrain    │
                    |        │             │ S_(n+1) Level  │
                    |        │             │ - Pattern      │
                    |        │             │   Detection    │
                    |        │             └────────────────┘
                    |        │
                    |        └──────────┐
                    |                   |
        ┌───────────v────────┐   ┌──────v───────┐
        │   Memory Systems   │   │   Thalamic   │
        │                    │   │   Routing    │
        │ - Hippocampus      │   │              │
        │ - Strategy Lib     │   │ - Gates g    │
        │ - CTM Async        │   │ - 10×4 Matrix│
        │ - Temporal Memory  │   │ - Hebbian    │
        │ - Infinite Chat    │   │   Learning   │
        └────────────────────┘   └──────────────┘
                    |                   |
                    └───────────────────┘
                                |
                    ┌───────────v───────────┐
                    │   Monitoring System   │
                    │  - Brain State        │
                    │  - Execution History  │
                    │  - Consciousness      │
                    └───────────────────────┘
```

---

## Wie ein Request durch das System fließt

### Request: "Deploy Docker container with health checks"

```
1. USER INTERFACE (Layer 5)
   curl -X POST localhost:5001/predict -d '{"task": "Deploy Docker..."}'

2. ORCHESTRATION (Layer 4)
   ProductionPlanner.predict()
     ├─> HierarchicalPlanner.predict()
     │     ├─> Layer 1: extract features
     │     ├─> Layer 2: predict path
     │     └─> Layer 3: route decision
     └─> MultiBrainSwarm.collect_brain_votes()
           ├─> 5 Brains vote
           ├─> SemanticCoherenceLayer validates
           └─> MetaBrain analyzes patterns

3. COGNITIVE PROCESSING (Layer 3)
   - TaskFeatureRouter: complexity=0.65, domain=docker
   - ConversationPathPlanner: path=[suggest, retry, success]
   - DecisionRouter: primary=retry (0.85)
   - SemanticCoherence: K=0.814, status=GREEN ✓
   - MetaBrain: no patterns detected

4. LEARNING & MEMORY (Layer 2)
   - Hippocampus: not novel, skip storage
   - StrategyLibrary: strategy #7 found, boost confidence
   - CTM Async: complexity too low, skip
   - InfiniteChat: retrieve past Docker conversations

5. FOUNDATION (Layer 1)
   - ThalamoPCAdaptive: gates=[0.05, 0.10, 0.65, ...]
   - MultiTargetRouter: weights=[0.60, 0.85, 0.30, 0.10]
   - MultiLLMRouter: LLM reasoning with memory context

6. OUTPUT (Layer 5)
   {
     "decision": "retry",
     "confidence": 0.90,
     "semantic_status": "GREEN",
     "reasoning": "5 brains agree (K=0.814), strategy #7 proven"
   }
```

---

## Die 3 Integration Points

### 1. **Memory Integration Point**
Alle Memory-Module nutzen einheitliche Schnittstelle:

```python
class MemoryInterface:
    def store(self, experience: Experience) -> bool:
        """Store experience if novel/important"""
        pass

    def retrieve(self, query: Query) -> List[Experience]:
        """Retrieve relevant experiences"""
        pass

    def consolidate(self) -> None:
        """Offline consolidation (Dream Mode)"""
        pass
```

**Implementiert von**:
- Hippocampus (episodic)
- StrategyLibrary (strategic)
- MemorySystems (working/declarative/procedural)
- TemporalMemory (temporal)
- SupermemoryLLM (semantic via Infinite Chat)

### 2. **Routing Integration Point**
Alle Routing-Module nutzen Modality Gates:

```python
class RoutingInterface:
    def step(self, x_dict: Dict[str, np.ndarray]) -> Dict:
        """Process one timestep"""
        return {
            'v_next': ...,  # Latent states
            'g': ...,       # Gates (sum=1.0)
            'y': ...,       # Outputs
            'pe': ...       # Prediction errors
        }
```

**Implementiert von**:
- ThalamoPCAdaptive (thalamic gating)
- MultiTargetRouter (10×4 matrix)
- DecisionRouter (multi-target decisions)

### 3. **Semantic Integration Point (Phase 13 - NEU!)**
Semantic Coherence validiert alle Decisions:

```python
class SemanticInterface:
    def validate(self, brain_answers: List[BrainAnswer]) -> SemanticConsensus:
        """Validate semantic coherence"""
        K, U, sim_matrix = self.compute_coherence(brain_answers)
        truth_stability = self.compute_truth_stability(voting_score, K)

        return SemanticConsensus(
            coherence_K=K,
            disagreement_U=U,
            truth_stability=truth_stability,
            semantic_status='GREEN' if truth_stability >= 0.75 else 'YELLOW' or 'RED'
        )
```

**Genutzt von**:
- MultiBrainSwarm (alle Decisions)
- HierarchicalPlanner (Layer 3 Output)
- ProductionPlanner (Final Validation)

---

## Wo ist was? (File Organization)

```
Tahlamus/
│
├── core/                          # LAYER 1-3: Foundation + Cognitive
│   ├── Layer 1 (Foundation)
│   │   ├── thalamo_pc_adaptive.py       # Thalamic routing
│   │   ├── multi_target_router.py       # 10×4 matrix
│   │   ├── multi_llm_router.py          # LLM abstraction
│   │   └── config_loader.py             # Config
│   │
│   ├── Layer 2 (Memory)
│   │   ├── hippocampus.py               # Episodic
│   │   ├── strategy_library.py          # Strategic
│   │   ├── memory_systems.py            # Working/Declarative/Procedural
│   │   ├── temporal_memory.py           # Temporal
│   │   ├── supermemory_llm_client.py    # Infinite Chat
│   │   ├── ctm_async_reasoner.py        # Deep Reasoning (async)
│   │   └── ctm_integration.py           # Deep Reasoning (sync)
│   │
│   └── Layer 3 (Cognitive)
│       ├── task_feature_router.py       # Layer 1: Features
│       ├── conversation_path_planner.py # Layer 2: Paths
│       ├── decision_router.py           # Layer 3: Decisions
│       ├── semantic_coherence.py        # Phase 13: Truth (NEW!)
│       ├── meta_brain.py                # S_(n+1) patterns
│       ├── meta_router.py               # Meta-cognitive routing
│       ├── conversation_graph.py        # State-space search
│       └── conversation_trace_encoder.py # Trace parsing
│
├── production/                    # LAYER 4: Orchestration
│   ├── production_planner.py            # Main production class
│   ├── api_server.py                    # REST API (Layer 5 Entry)
│   └── trained_matrices/                # Routing matrices
│
├── web/                           # LAYER 5: User Interface
│   ├── brain_dashboard_server.py        # Web UI
│   └── templates/brain_dashboard.html   # Frontend
│
├── demos/                         # LAYER 5: User Interface (Demos)
│   ├── chat_with_semantic_coherence.py  # Interactive chat
│   ├── chat_semantic_auto.py            # Auto-running demo
│   ├── test_semantic_coherence.py       # Comprehensive tests
│   ├── interactive_coherence_demo.py    # Step-by-step tutorial
│   └── detailed_logging_demo.py         # JSON logging
│
└── monitoring/                    # Cross-Layer: Observability
    ├── brain_monitor.py                 # Real-time monitoring
    ├── execution_tracker.py             # History tracking
    └── consciousness_metrics.py         # Global Workspace
```

---

## Was kann das System? (Use Cases)

### Use Case 1: Production Prediction (API)
```bash
curl -X POST localhost:5001/predict -d '{
  "task": "Deploy Docker container",
  "context": {"urgency": "high"}
}'
```

**System Flow**: Layer 5 → Layer 4 → Layer 3 → Layer 2 → Layer 1 → Output
**Latency**: <100ms (without CTM)
**Accuracy**: 77% (baseline), improves with continuous learning

---

### Use Case 2: Real-Time Visualization (Dashboard)
```bash
python web/brain_dashboard_server.py
# Open http://localhost:5000
```

**System Flow**: Layer 5 (Dashboard) → Layer 4 (Orchestration) → Monitoring System
**Features**:
- Real-time brain state visualization
- Thalamic gate distribution
- Semantic coherence metrics (Phase 13!)
- Active alerts and interventions

---

### Use Case 3: Interactive Chat with Semantic Validation (NEW!)
```bash
python demos/chat_with_semantic_coherence.py
```

**System Flow**: Layer 5 (Chat) → Layer 4 (Swarm) → Layer 3 (Semantic Coherence)
**Output**:
- Brain responses (5 experts)
- Semantic coherence (K=0.806)
- Truth stability (0.725)
- Traffic light status (GREEN/YELLOW/RED)

---

### Use Case 4: Continuous Learning (Production)
```python
# Submit feedback after execution
client.submit_feedback(
    task="Deploy Docker",
    result=prediction,
    success=True,
    user_rating=0.9
)
```

**System Flow**: Layer 5 → Layer 4 → Layer 1 (update routing matrix)
**Learning Rate**: 0.005
**Effect**: Matrix improves over time (77% → 82% → ...)

---

### Use Case 5: Deep Reasoning (Complex Tasks)
```python
# Automatically triggered for complexity >= 0.75
prediction = planner.predict(
    "Design distributed microservice architecture with auto-scaling"
)
```

**System Flow**: Layer 4 → Layer 2 (CTM Async) → Background reasoning (5-15s)
**Benefit**: Deep insights without blocking main prediction

---

## Warum 41 Module? (Rechtfertigung)

### Grund 1: **Separation of Concerns**
Jedes Modul hat **eine** klare Verantwortung. Wenn du Module fusionierst, verlierst du Klarheit.

### Grund 2: **Testbarkeit**
Kleine Module sind leichter zu testen. Jedes Modul hat eigene Tests.

### Grund 3: **Flexibilität**
Du kannst Module austauschen (z.B. SemanticCoherence deaktivieren) ohne alles zu ändern.

### Grund 4: **Evolution**
System wächst organisch. Phase 1-6 sind optional, Phase 13 ist neu. Ohne Modularität → Chaos.

### Grund 5: **Team Collaboration**
Verschiedene Entwickler arbeiten an verschiedenen Modulen. Weniger Konflikte.

---

## Die Antwort auf deine Frage

**Frage**: "Wie bringt man all die Scripte in ein sinnvolles Gesamtkonzept?"

**Antwort**: Durch **5-Layer Architecture** mit klaren Prinzipien:

1. ✅ **Jedes Modul gehört zu genau einer Layer**
2. ✅ **Jede Layer nutzt nur die Layer darunter**
3. ✅ **3 Integration Points** (Memory, Routing, Semantic)
4. ✅ **Unidirectional Data Flow** (top → bottom → top)
5. ✅ **Observable & Testable** (Monitoring überall)

**Das ist kein Chaos von 41 Modulen.**
**Das ist ein kohärentes kognitives System mit klarer Architektur.**

---

## Nächste Schritte (wenn du willst)

1. **Visualisierung erstellen**
   - Mermaid-Diagramme für Datenfluss
   - C4-Diagramme für Architektur
   - Interaktive Visualisierung (D3.js)

2. **Konsolidierung (optional)**
   - Phase A: 41 → 35 Module (Fusioniere verwandte Module)
   - Phase B: 35 → 28 Module (Archiviere Legacy)

3. **Dokumentation verbessern**
   - API-Docs für jedes Modul
   - Integration-Guides
   - Tutorials für jede Layer

4. **Testing erweitern**
   - Integration Tests (Layer zu Layer)
   - End-to-End Tests (User Input → Output)
   - Performance Tests (Latency, Throughput)

Sag mir, was du als nächstes willst!

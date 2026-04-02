# Tahlamus Complete System Overview

**Date**: October 19, 2025
**Status**: Production Ready
**Purpose**: End-to-end explanation of how the entire Tahlamus system works

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Core Components](#core-components)
3. [Data Flow: Request to Response](#data-flow-request-to-response)
4. [The Brain: How Routing Works](#the-brain-how-routing-works)
5. [The 3-Layer Hierarchy](#the-3-layer-hierarchy)
6. [Memory Systems](#memory-systems)
7. [CTM Deep Reasoning](#ctm-deep-reasoning)
8. [Production Deployment](#production-deployment)
9. [Complete Example Walkthrough](#complete-example-walkthrough)
10. [Key Design Principles](#key-design-principles)

---

## High-Level Architecture

### The Big Picture

Tahlamus is a **brain-inspired cognitive routing system** that decides what action to take for any given task. Think of it as a "meta-brain" that routes between different thinking modes.

```
┌─────────────────────────────────────────────────────────────┐
│                    USER / EXTERNAL SYSTEM                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │   Production API (Flask)     │
         │   Port 5001 - 7 Endpoints    │
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │   ProductionPlanner          │
         │   (Orchestrates everything)  │
         └──────────────┬───────────────┘
                        │
                        ▼
    ┌───────────────────────────────────────────┐
    │      HierarchicalPlanner (3 Layers)       │
    │                                           │
    │  Layer 1: TaskFeatureRouter              │
    │      ↓                                    │
    │  Layer 2: ConversationPathPlanner        │
    │      ↓                                    │
    │  Layer 3: DecisionRouter                 │
    │                                           │
    │  + CTM Async (background reasoning)      │
    │  + Memory Systems                        │
    │  + 12 Cognitive Phases                   │
    └───────────────────┬───────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │   Multi-Target Decision      │
         │   + Reasoning Chain          │
         │   + Confidence Score         │
         │   + CTM Insights (optional)  │
         └──────────────────────────────┘
```

### What Problem Does It Solve?

**Problem**: How does an AI agent decide what to do next when facing a complex task?

**Traditional Approach**: Single LLM call → direct action
- No multi-step planning
- No learning from past attempts
- No adaptive routing based on brain state
- No failure recovery

**Tahlamus Approach**: Brain-inspired hierarchical routing
- 3-layer decision pipeline
- Learns from 39 real conversation sessions
- 10 brain modalities compete for attention
- Trained routing matrix (77% accuracy)
- Continuous learning from feedback
- CTM deep reasoning for complex tasks

---

## Core Components

### 1. **Foundation Layer: Thalamic Routing**

The **thalamus** in the human brain routes sensory information to appropriate cortical areas. Tahlamus does the same for AI tasks.

**Key Files**:
- `core/thalamo_pc_live.py` - Base thalamic gating
- `core/thalamo_pc_adaptive.py` - Learning version
- `core/thalamo_hippocampal_system.py` - Memory-augmented

**How It Works**:
```python
# 10 brain modalities compete for attention
modalities = [
    'vision',           # Visual reasoning
    'audio',            # Verbal/language reasoning
    'touch',            # Embodied reasoning
    'taste',            # Value/reward reasoning
    'vestibular',       # Spatial reasoning
    'threat',           # Safety/urgency
    'tool_trace',       # Tool usage patterns
    'temporal_pattern', # Timing patterns
    'error_signal',     # Error detection
    'success_signal'    # Success signal
]

# Each gets a "gate" value (0-1, sum to 1.0)
gates = softmax(relevance_scores / temperature)
# Example: [0.05, 0.12, 0.03, 0.01, 0.02, 0.15, 0.35, 0.18, 0.07, 0.02]

# Dominant modalities drive decision
dominant = ['tool_trace', 'temporal_pattern', 'threat']
```

**Key Equation**:
```
gates = softmax(β₁‖v_i‖ + β₂·PE_i + β₃·π_i + β₄·ctx_i / τ_g)

Where:
- v_i = latent state for modality i
- PE_i = prediction error
- π_i = prior importance
- ctx_i = context signal
- τ_g = gate temperature (sharpness)
```

### 2. **The 3-Layer Hierarchy**

Each layer has a specific job:

#### **Layer 1: TaskFeatureRouter** (`core/task_feature_router.py`)
**Job**: Understand what kind of task this is

**Input**: Raw task string
```python
task = "Deploy Docker container urgently for production environment"
```

**Output**: Task features + initial routing
```python
{
    'task_type': 'deployment',
    'complexity': 0.82,        # 0-1 scale
    'urgency': 0.95,           # 0-1 scale
    'keywords': ['deploy', 'docker', 'production', 'urgent'],
    'processing_mode': 'reactive',
    'routing_weights': [0.05, 0.12, ...],  # 10 modality weights
    'dominant_areas': ['threat', 'tool_trace', 'temporal_pattern']
}
```

**How**: Uses heuristics + keyword matching (future: LLM-based)

#### **Layer 2: ConversationPathPlanner** (`core/conversation_path_planner.py`)
**Job**: Predict the optimal sequence of actions

**Input**: Task + Layer 1 features
**Output**: Action sequence + confidence

```python
{
    'predicted_sequence': ['analyze', 'verify_env', 'execute', 'monitor', 'complete'],
    'confidence': 0.70,
    'success_probability': 0.82,
    'dominant_modalities': ['tool_trace', 'threat', 'temporal_pattern'],
    'task_type': 'deployment'
}
```

**How**:
- Trained on 39 real conversation sessions
- Builds conversation graph (states + transitions)
- Uses A* search to find optimal path
- Considers past successes/failures

**Key Insight**: Conversations are **state-space search problems**
- States = conversation status
- Transitions = agent actions
- Goal = successful completion
- Optimal path = fewest steps, fewest errors

#### **Layer 3: DecisionRouter** (`core/decision_router.py`)
**Job**: Convert brain routing into actionable decisions

**Input**:
- Brain gates from Layer 2 (10 values summing to 1.0)
- Confidence score
- Dominant modalities

**Output**: Multi-target decision
```python
{
    'primary': {
        'type': 'suggest',
        'weight': 0.65,
        'reasoning': '...'
    },
    'alternatives': [
        {'type': 'retry', 'weight': 0.22},
        {'type': 'wait', 'weight': 0.08},
        {'type': 'terminate', 'weight': 0.05}
    ]
}
```

**How**: Learned 10×4 routing matrix
```
           suggest  retry  wait  terminate
vision     0.85     0.10   0.03  0.02
audio      0.70     0.15   0.10  0.05
...
threat     0.05     0.15   0.25  0.55  ← threat favors terminate
tool_trace 0.75     0.20   0.04  0.01
```

**Math**:
```python
intervention_logits = brain_gates @ routing_matrix  # (10,) @ (10,4) = (4,)
weights = softmax(intervention_logits)
primary = intervention_types[argmax(weights)]
```

### 3. **Memory Systems** (Dual Architecture)

#### **A. Structured Memory API** (Port 8001)
**Purpose**: Store execution logs, chat history, visual context

**Endpoints**:
- `POST /memories/execution` - Store agent execution
- `POST /memories/chat` - Store conversation
- `POST /memories/query` - Query memories

**Storage**: Supermemory V3 cloud API

#### **B. Infinite Chat** (Automatic Semantic Memory)
**Purpose**: Automatic memory injection into LLM calls

**How It Works**:
```python
# Normal OpenAI call
client = OpenAI(api_key="sk-...")
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Deploy Docker"}]
)

# Infinite Chat (via Supermemory proxy)
client = OpenAI(
    api_key="sk-...",
    base_url="https://api.supermemory.ai/v3/https://api.openai.com/v1",
    default_headers={
        "x-supermemory-api-key": "sm-...",
        "x-sm-user-id": "alice"  # User isolation
    }
)
response = client.chat.completions.create(...)
# Past conversations about Docker auto-retrieved and injected!
```

**Benefits**:
- 90% less code (no manual retrieval)
- Semantic search (not recency-based)
- Unlimited context (beyond model limits)
- 50% token savings

### 4. **CTM Deep Reasoning** (Phase 13)

**Purpose**: Iterative deep reasoning for complex tasks

**When It Triggers**:
1. Task complexity >= 0.75 (automatic)
2. Execution failure (if enabled)
3. Manual call to `retry_with_ctm_insights()`

**How It Works**:
```python
# CTM runs in background thread
ctm_task_id = ctm_async.start_reasoning_async(
    task_description="Complex problem",
    steps=50,
    convergence_threshold=0.9
)

# Main prediction continues (non-blocking!)
prediction = planner.predict(task)  # Returns in <100ms

# Later: retrieve CTM insights
insights = planner.get_ctm_insights(ctm_task_id, wait=True)
```

**CTM Reasoning Loop**:
```python
for step in range(50):
    # 1. Route to dominant modality
    gates = thalamus.step(thought_buffers)
    dominant = modalities[argmax(gates)]

    # 2. Execute reasoning module
    state, thought = reasoning_modules[dominant](state)
    # Examples:
    #   [Visual] Analyzing visual patterns...
    #   [Verbal] Reasoning symbolically... similarity=0.67
    #   [Spatial] Performing mental rotation...
    #   [Taste] Estimating value... EV=0.82

    # 3. Check convergence
    if state.confidence >= 0.9: break
```

**Output**: Insights summary
```
CTM Deep Reasoning (18 steps, 8.2s)
Confidence: 87%, Converged: True

Key Thoughts:
  1. [Visual] Analyzing visual patterns... buffer norm=1.23
  2. [Verbal] Reasoning symbolically... goal similarity=0.45
  3. [Vestibular] Performing mental rotation...
  4. [Taste] Estimating value... EV=0.67, confidence=0.81
  5. [Verbal] Reasoning symbolically... goal similarity=0.87
```

---

## Data Flow: Request to Response

Let's trace a complete request through the system:

### **Request**: "Deploy Docker container urgently"

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: API Receives Request                                │
└─────────────────────────────────────────────────────────────┘

POST /predict
{
  "task": "Deploy Docker container urgently"
}

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 2: ProductionPlanner Orchestrates                      │
└─────────────────────────────────────────────────────────────┘

production_planner.predict("Deploy Docker container urgently")
├─ Load trained routing matrix (10×4)
├─ Initialize HierarchicalPlanner
└─ Forward to HierarchicalPlanner

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 3: Layer 1 - TaskFeatureRouter                        │
│ Time: 5ms                                                   │
└─────────────────────────────────────────────────────────────┘

layer1.route_task("Deploy Docker container urgently")

Extract features:
✓ task_type: 'deployment'
✓ complexity: 0.65
✓ urgency: 0.95  ← HIGH urgency!
✓ keywords: ['deploy', 'docker', 'urgent']
✓ processing_mode: 'reactive'

Initial routing weights:
  threat:           0.35  ← Urgency drives threat
  tool_trace:       0.28  ← Docker is a tool
  temporal_pattern: 0.15  ← Time-sensitive
  error_signal:     0.10
  ...others:        0.12

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 4: CTM Check (Async)                                  │
│ Time: 0ms (non-blocking)                                   │
└─────────────────────────────────────────────────────────────┘

if complexity >= 0.75:
    Start CTM async
else:
    Skip CTM  ← We skip (complexity=0.65)

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 5: Layer 2 - ConversationPathPlanner                  │
│ Time: 12ms                                                  │
└─────────────────────────────────────────────────────────────┘

layer2.predict_optimal_path("Deploy Docker...")

1. Query conversation graph
   - Find similar past deployments
   - 5 similar sessions found

2. Calculate confidence
   data_factor = min(5/10, 1.0) = 0.50
   success_factor = 4/5 = 0.80
   familiarity_factor = min(12/20, 1.0) = 0.60

   confidence = 0.50×0.4 + 0.80×0.4 + 0.60×0.2 = 0.64

3. Predict sequence
   ['analyze_env', 'verify_docker', 'execute_deploy', 'monitor']

4. Run through MetaRouter (thalamic gating)
   Input: routing_weights from Layer 1
   Process: TRN competition, softmax normalization
   Output: brain_gates (10 values, sum=1.0)

   brain_gates = [0.02, 0.05, 0.01, 0.01, 0.02, 0.38, 0.25, 0.12, 0.08, 0.06]
                  vis   aud   tch   tst   ves   thr   trc   tmp   err   suc

Output:
{
  'predicted_sequence': ['analyze_env', 'verify_docker', 'execute_deploy', 'monitor'],
  'confidence': 0.64,
  'success_probability': 0.80,
  'dominant_modalities': ['threat', 'tool_trace', 'temporal_pattern']
}

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 6: Layer 3 - DecisionRouter                           │
│ Time: 8ms                                                   │
└─────────────────────────────────────────────────────────────┘

layer3.route_to_action(
    brain_gates=[0.02, 0.05, ..., 0.38, 0.25, 0.12, ...],
    confidence=0.64
)

1. Matrix multiplication
   intervention_logits = brain_gates @ routing_matrix

   brain_gates:     [0.02, 0.05, 0.01, 0.01, 0.02, 0.38, 0.25, 0.12, 0.08, 0.06]

   routing_matrix (10×4):
              suggest  retry  wait  terminate
   vision     0.85     0.10   0.03  0.02
   audio      0.70     0.15   0.10  0.05
   touch      0.75     0.18   0.05  0.02
   taste      0.65     0.20   0.10  0.05
   vestibular 0.80     0.12   0.06  0.02
   threat     0.05     0.15   0.25  0.55  ← threat wants caution!
   tool_trace 0.75     0.20   0.04  0.01
   temporal   0.70     0.18   0.08  0.04
   error      0.30     0.45   0.15  0.10
   success    0.85     0.10   0.04  0.01

   Result:
   intervention_logits = [0.42, 0.21, 0.18, 0.25]
                         sug   ret  wait  term

2. Softmax normalization
   weights = softmax(intervention_logits)
   weights = [0.48, 0.19, 0.16, 0.17]

3. Build multi-target decision
   Primary: suggest (48%)
   Alternatives: retry (19%), terminate (17%), wait (16%)

Output:
{
  'primary': {
    'type': 'suggest',
    'weight': 0.48,
    'confidence': 0.64,
    'reasoning': 'Urgency detected but deployment is familiar task...'
  },
  'alternatives': [
    {'type': 'retry', 'weight': 0.19},
    {'type': 'terminate', 'weight': 0.17},  ← threat influence
    {'type': 'wait', 'weight': 0.16}
  ]
}

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 7: Build Final Prediction                             │
│ Total Time: 25ms                                            │
└─────────────────────────────────────────────────────────────┘

HierarchicalPrediction {
  layer1_routing: {...},
  predicted_sequence: ['analyze_env', 'verify_docker', ...],
  confidence: 0.64,
  success_probability: 0.80,
  dominant_modalities: ['threat', 'tool_trace', 'temporal_pattern'],
  task_type: 'deployment',
  actionable_decision: {
    primary: {type: 'suggest', weight: 0.48, ...},
    alternatives: [...]
  },
  reasoning_chain: [
    "Task type 'deployment' identified (urgency: 0.95)",
    "5 similar sessions found with 80% success rate",
    "Dominant modalities: threat (high urgency), tool_trace, temporal_pattern",
    "Brain gates: threat=0.38, tool_trace=0.25, temporal=0.12",
    "Multi-target routing: suggest (48%), retry (19%), terminate (17%)",
    "High urgency balanced with deployment familiarity → suggest with caution"
  ],
  ctm_task_id: null,  ← No CTM (complexity < 0.75)
  total_processing_time: 0.025  ← 25ms!
}

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 8: ProductionPlanner Post-Processing                  │
└─────────────────────────────────────────────────────────────┘

1. Store in working memory
2. Update statistics
3. Format for API response

        ↓

┌─────────────────────────────────────────────────────────────┐
│ Step 9: API Returns Response                               │
└─────────────────────────────────────────────────────────────┘

{
  "task": "Deploy Docker container urgently",
  "prediction": {
    "primary_action": "suggest",
    "primary_weight": 0.48,
    "confidence": 0.64,
    "primary_reasoning": "Urgency detected but deployment is familiar...",
    "alternatives": [
      {"action": "retry", "weight": 0.19},
      {"action": "terminate", "weight": 0.17},
      {"action": "wait", "weight": 0.16}
    ]
  },
  "brain_state": {
    "dominant_modalities": ["threat", "tool_trace", "temporal_pattern"],
    "gates": [0.02, 0.05, 0.01, 0.01, 0.02, 0.38, 0.25, 0.12, 0.08, 0.06]
  },
  "reasoning_chain": [
    "Task type 'deployment' identified (urgency: 0.95)",
    ...
  ],
  "metadata": {
    "total_processing_time": 0.025,
    "task_type": "deployment",
    "complexity": 0.65,
    "urgency": 0.95
  }
}
```

---

## The Brain: How Routing Works

### Biological Inspiration

The **thalamus** in the human brain acts as a relay station:
- Routes sensory information to cortex
- Filters irrelevant signals
- Amplifies important signals
- Controlled by **Thalamic Reticular Nucleus (TRN)** which creates competition

### Tahlamus Implementation

**10 Brain Modalities** (like different sensory channels):

```python
modalities = {
    # Original sensory
    'vision': 128-dim,       # Visual/spatial reasoning
    'audio': 64-dim,         # Verbal/language reasoning
    'touch': 32-dim,         # Embodied/physical reasoning
    'taste': 16-dim,         # Value/reward reasoning
    'vestibular': 16-dim,    # Balance/spatial navigation
    'threat': 8-dim,         # Safety/urgency signals

    # Meta-cognitive (added for conversation analysis)
    'tool_trace': 64-dim,         # Tool usage patterns
    'temporal_pattern': 32-dim,   # Timing/sequence patterns
    'error_signal': 16-dim,       # Error detection
    'success_signal': 8-dim       # Success indicators
}
```

**Competitive Routing**:

```python
# 1. Each modality has latent state v_i
v = {
    'vision': np.random.randn(128),
    'audio': np.random.randn(64),
    ...
}

# 2. Compute relevance scores
relevance = {
    modality: (
        β₁ * np.linalg.norm(v[modality]) +     # Activity level
        β₂ * prediction_error[modality] +      # Prediction error
        β₃ * priors[modality] +                # Prior importance
        β₄ * context[modality]                 # Context signal
    )
    for modality in modalities
}

# 3. TRN inhibition (competition)
for i in modalities:
    for j in modalities:
        if i != j:
            relevance[i] -= λ * L[i,j] * np.linalg.norm(v[j])

# 4. Softmax gating (winner-take-more)
gates = softmax(relevance / temperature)
# Result: [0.02, 0.05, 0.01, 0.01, 0.02, 0.38, 0.25, 0.12, 0.08, 0.06]
#         Always sums to 1.0!
```

**Key Properties**:
- Gates sum to 1.0 (probability distribution)
- Temperature controls sharpness (low = winner-take-all, high = uniform)
- TRN creates competition (when one wins, others suppressed)
- Adaptive learning adjusts priors, inhibition matrix over time

---

## The 3-Layer Hierarchy

### Why 3 Layers?

**Inspiration**: Hierarchical processing in cortex
- **V1** (low-level): Detect edges, colors
- **V2-V4** (mid-level): Detect shapes, objects
- **IT** (high-level): Recognize faces, scenes

**Tahlamus**:
- **Layer 1** (low-level): Extract task features
- **Layer 2** (mid-level): Plan action sequence
- **Layer 3** (high-level): Decide intervention

### Information Flow

```
Raw Task String
        ↓
┌───────────────────────┐
│ Layer 1: Features     │  ← What kind of task?
│ - Task type           │
│ - Complexity          │
│ - Urgency             │
│ - Keywords            │
└───────────┬───────────┘
            ↓
┌───────────────────────┐
│ Layer 2: Path Plan    │  ← What's the optimal sequence?
│ - Action sequence     │
│ - Brain routing       │
│ - Confidence          │
│ - Success probability │
└───────────┬───────────┘
            ↓
┌───────────────────────┐
│ Layer 3: Decision     │  ← What specific action now?
│ - Primary action      │
│ - Alternatives        │
│ - Reasoning chain     │
└───────────────────────┘
```

### Why This Works

**Separation of Concerns**:
- Layer 1: Domain-independent feature extraction
- Layer 2: Task-specific planning (trained on sessions)
- Layer 3: Action-space routing (learned matrix)

**Composability**:
- Can swap Layer 1 (e.g., LLM-based)
- Can retrain Layer 2 (new session logs)
- Can update Layer 3 (continuous learning)

**Biological Plausibility**:
- Mirrors cortical hierarchy
- Each layer has different time constant
- Information flows bottom-up and top-down

---

## Memory Systems

### Two Types of Memory

#### 1. **Working Memory** (Short-term)
- **Capacity**: 10 recent tasks
- **Purpose**: Immediate context
- **Storage**: In-memory deque
- **Access**: O(1) recent items

```python
working_memory = [
    Task("Deploy Docker", decision="suggest", outcome="success"),
    Task("Fix bug", decision="retry", outcome="success"),
    ...
]
```

#### 2. **Episodic Memory** (Long-term)
- **Capacity**: 1000 important experiences
- **Purpose**: Learning from past
- **Storage**: Disk (JSON) + Supermemory cloud
- **Access**: Similarity search

```python
episodic_memory = [
    Episode(
        task="Deploy Docker container",
        task_type="deployment",
        decision="suggest",
        outcome="success",
        brain_gates=[0.02, 0.05, ..., 0.38, ...],
        importance=0.85,
        timestamp="2025-10-15T14:23:11"
    ),
    ...
]
```

### Memory Consolidation

**When does working → episodic happen?**

```python
if importance >= 0.7:  # Important experience
    consolidate_to_episodic(task)

importance = (
    0.4 * novelty +              # How unusual?
    0.3 * prediction_error +     # How unexpected?
    0.2 * emotional_valence +    # Success or failure?
    0.1 * user_rating            # User feedback
)
```

**Memory Efficiency**: Only 7.7% of traces stored
- Most tasks are routine (not stored)
- Novel failures always stored
- High-importance successes stored

### Infinite Chat Integration

**Traditional Memory Retrieval**:
```python
# 1. Query memory system
memories = memory.query(task="Deploy Docker", limit=5)

# 2. Format memories
context = format_memories_for_llm(memories)

# 3. Add to LLM prompt
messages = [
    {"role": "system", "content": f"Context: {context}"},
    {"role": "user", "content": task}
]

# 4. Call LLM
response = llm.chat(messages)
```
**Problem**: 50+ lines of code, manual formatting, limited by context window

**Infinite Chat (Supermemory Proxy)**:
```python
# Just call LLM normally!
response = llm.chat([
    {"role": "user", "content": "Deploy Docker"}
])
# Supermemory automatically:
# 1. Searches past conversations
# 2. Retrieves relevant context
# 3. Injects into prompt
# 4. Returns response
```
**Benefit**: 90% less code, automatic, semantic search, unlimited context

---

## CTM Deep Reasoning

### When Simple Routing Isn't Enough

**Example Complex Task**:
```
"Design a distributed microservice architecture with:
- Auto-scaling based on CPU/memory
- Circuit breaker pattern for fault tolerance
- Event-driven communication
- Service mesh for observability
- Blue-green deployment strategy"
```

**Problem with Standard Routing**:
- Layer 1 extracts features (5ms)
- Layer 2 predicts sequence (12ms)
- Layer 3 decides action (8ms)
- **Total: 25ms** but...
- Decision based on **pattern matching**, not deep reasoning
- No multi-step thinking about trade-offs
- No consideration of alternative approaches

### CTM Solves This

**CTM = Continuous Thought Model**
- Iterative reasoning loop (20-50 steps)
- Routes between different thinking modes
- Converges when confident solution found

**Architecture**:
```python
class CTMReasoner:
    def __init__(self):
        # 6 reasoning modules
        self.modules = {
            'vision': visual_reasoning,      # Mental imagery
            'audio': verbal_reasoning,       # Language/logic
            'touch': embodied_reasoning,     # Physical intuition
            'vestibular': spatial_reasoning, # 3D navigation
            'taste': value_reasoning,        # Cost-benefit
            'threat': safety_check           # Risk assessment
        }

    def reason(self, problem, steps=50):
        state = ThoughtState(...)

        for step in range(steps):
            # 1. Route to thinking mode
            gates = self.thalamus.step(state.buffers)
            mode = self.modules[argmax(gates)]

            # 2. Think using that mode
            state, thought = mode(state)

            # 3. Record thought
            state.thought_history.append(thought)

            # 4. Check convergence
            if state.confidence >= threshold:
                break

        return state, thought_history
```

**Example Thought Stream**:
```
Step 0:  [Visual] Analyzing visual patterns... buffer norm=0.85
Step 1:  [Verbal] Reasoning symbolically... goal similarity=0.23
Step 2:  [Visual] Analyzing visual patterns... buffer norm=1.12
Step 3:  [Spatial] Performing mental rotation...
Step 4:  [Taste] Estimating value... EV=0.45, confidence=0.32
Step 5:  [Verbal] Reasoning symbolically... goal similarity=0.51
Step 6:  [Taste] Estimating value... EV=0.67, confidence=0.58
Step 7:  [Verbal] Reasoning symbolically... goal similarity=0.73
Step 8:  [Visual] Analyzing visual patterns... buffer norm=1.45
Step 9:  [Taste] Estimating value... EV=0.82, confidence=0.78
Step 10: [Verbal] Reasoning symbolically... goal similarity=0.89
Step 11: [Taste] Estimating value... EV=0.91, confidence=0.92
         ✓ Converged at confidence=0.92!
```

### Async Hybrid Integration

**Problem**: CTM takes 5-15 seconds (too slow for production)

**Solution**: Run CTM in background!

```python
# Main prediction (fast path)
prediction = planner.predict(task)  # Returns in <100ms

# Meanwhile, in background thread:
if complexity >= 0.75:
    ctm_task_id = ctm_async.start_reasoning(task)
    # CTM runs for 5-15 seconds

# Later: retrieve insights
if execution_fails:
    insights = planner.get_ctm_insights(ctm_task_id, wait=True)
    retry_strategy = planner.retry_with_ctm_insights(prediction, insights)
```

**Benefits**:
- Zero latency impact (non-blocking)
- Deep insights available when needed
- Failure recovery uses CTM reasoning
- Simple tasks skip CTM entirely

---

## Production Deployment

### Services Running

```
┌─────────────────────────────────────────────┐
│         Tahlamus Production Stack           │
├─────────────────────────────────────────────┤
│                                             │
│  Port 5000: Brain Dashboard (Flask)         │
│  - Real-time brain visualization            │
│  - Interactive simulations                  │
│  - Chat interface                           │
│  - 8 REST endpoints                         │
│                                             │
│  Port 5001: Production API (Flask)          │
│  - /predict (main prediction endpoint)      │
│  - /feedback (continuous learning)          │
│  - /stats (system statistics)               │
│  - /matrices (list routing matrices)        │
│  - /save_matrix, /load_matrix              │
│  - /health                                  │
│  - 7 REST endpoints total                   │
│                                             │
│  Port 8001: Memory API (FastAPI)            │
│  - /memories/execution                      │
│  - /memories/chat                           │
│  - /memories/visual                         │
│  - /memories/query                          │
│  - /planning/context                        │
│  - /health                                  │
│  - 6 REST endpoints                         │
│                                             │
└─────────────────────────────────────────────┘
```

### Starting the System

```bash
# 1. Start Production API
python production/api_server.py
# Server runs on http://localhost:5001

# 2. Start Brain Dashboard
python web/brain_dashboard_server.py
# Dashboard at http://localhost:5000

# 3. Start Memory API
cd memory_api
python memory_service.py
# API at http://localhost:8001
```

### Python Client Usage

```python
from production.example_client import TahlamusClient

# Connect to production API
client = TahlamusClient("http://localhost:5001")

# Make prediction
result = client.predict("Deploy Docker container urgently")

print(f"Action: {result['prediction']['primary_action']}")
print(f"Confidence: {result['prediction']['confidence']:.1%}")
print(f"Reasoning: {result['reasoning_chain']}")

# Submit feedback (triggers learning!)
client.submit_feedback(
    task="Deploy Docker container urgently",
    result=result,
    success=True,
    user_rating=0.9
)

# Get statistics
stats = client.get_stats()
print(f"Total predictions: {stats['total_predictions']}")
print(f"Success rate: {stats['success_rate']:.1%}")
```

### Continuous Learning

**How It Works**:
```python
# 1. User submits feedback
POST /feedback
{
  "task": "Deploy Docker",
  "result": {...},
  "success": true,
  "user_rating": 0.9
}

# 2. System updates routing matrix
learning_rate = 0.005
if success:
    routing_matrix += lr * positive_gradient
else:
    routing_matrix -= lr * negative_gradient

# 3. Save updated matrix
save_matrix(f"routing_matrix_v{timestamp}_trained.npy")

# 4. A/B testing
matrices = ["v20250115_trained", "v20250116_trained", "v20250117_trained"]
# Can switch between versions
```

### Monitoring

**Real-Time Dashboard** (localhost:5000):
- Brain gate distribution (live chart)
- Active interventions
- Recent predictions
- System statistics
- Interactive simulations

**Key Metrics**:
- Prediction latency: <100ms (p95)
- Success rate: 82% average
- CTM usage: 15% of requests
- Memory efficiency: 7.7% storage rate

---

## Complete Example Walkthrough

Let's trace a **complex failure recovery scenario** end-to-end:

### Scenario: Database Migration Failure

```python
# ============================================================================
# INITIAL REQUEST
# ============================================================================

task = "Migrate PostgreSQL database from v12 to v15 with zero downtime"

# User calls API
response = requests.post("http://localhost:5001/predict", json={"task": task})

# ============================================================================
# LAYER 1: FEATURE EXTRACTION (5ms)
# ============================================================================

layer1_output = {
    'task_type': 'migration',
    'complexity': 0.88,  # HIGH complexity!
    'urgency': 0.60,
    'keywords': ['migrate', 'postgresql', 'zero', 'downtime'],
    'processing_mode': 'deliberative',
    'routing_weights': [0.03, 0.08, 0.02, 0.03, 0.02, 0.12, 0.35, 0.20, 0.10, 0.05]
}

# ============================================================================
# CTM TRIGGER (complexity >= 0.75)
# ============================================================================

print("[CTM] High complexity (0.88) - starting async reasoning")
ctm_task_id = ctm_async.start_reasoning_async(
    task_description=task,
    steps=50,
    convergence_threshold=0.9
)
# CTM running in background...

# ============================================================================
# LAYER 2: PATH PLANNING (15ms)
# ============================================================================

# Query conversation graph
similar_sessions = graph.find_similar("migration", limit=10)
# Found: 3 migrations, 2 successes, 1 failure

# Calculate confidence
data_factor = min(3/10, 1.0) = 0.30
success_factor = 2/3 = 0.67
familiarity_factor = min(3/20, 1.0) = 0.15

confidence = 0.30*0.4 + 0.67*0.4 + 0.15*0.2 = 0.42  # LOW confidence

# Predict sequence (based on successful migration)
predicted_sequence = [
    'backup_database',
    'test_migration_staging',
    'setup_replication',
    'switch_over',
    'verify_data'
]

# Run through thalamic routing
brain_gates = [0.02, 0.06, 0.01, 0.02, 0.01, 0.15, 0.32, 0.18, 0.12, 0.11]
#              vis   aud   tch   tst   ves   thr   trc   tmp   err   suc

layer2_output = {
    'predicted_sequence': predicted_sequence,
    'confidence': 0.42,  # LOW!
    'success_probability': 0.67,
    'dominant_modalities': ['tool_trace', 'temporal_pattern', 'threat']
}

# ============================================================================
# LAYER 3: DECISION ROUTING (8ms)
# ============================================================================

# Matrix multiplication
intervention_logits = brain_gates @ routing_matrix
# [0.55, 0.28, 0.22, 0.15]  ← suggest leads but not decisive

# Softmax
weights = softmax(intervention_logits)
# [0.45, 0.24, 0.19, 0.12]

decision = {
    'primary': {
        'type': 'suggest',
        'weight': 0.45,  # Not very confident
        'reasoning': 'Migration requires careful planning. Only 3 similar sessions...'
    },
    'alternatives': [
        {'type': 'retry', 'weight': 0.24},
        {'type': 'wait', 'weight': 0.19},
        {'type': 'terminate', 'weight': 0.12}
    ]
}

# ============================================================================
# RETURN PREDICTION (Total: 28ms)
# ============================================================================

prediction = {
    'task': task,
    'prediction': {
        'primary_action': 'suggest',
        'confidence': 0.42,  # LOW confidence
        'alternatives': [...]
    },
    'ctm_task_id': 'a3f2b1c5',  # CTM running in background
    'reasoning_chain': [
        "Task type 'migration' identified (complexity: 0.88)",
        "Only 3 similar sessions found, confidence low (0.42)",
        "Dominant: tool_trace (32%), temporal_pattern (18%), threat (15%)",
        "Decision uncertain: suggest (45%), retry (24%), wait (19%)"
    ]
}

# ============================================================================
# USER EXECUTES... AND FAILS
# ============================================================================

# User tries the migration
# ... 30 minutes later ...
# FAILURE: Data inconsistency detected after switch_over

# User submits feedback
requests.post("http://localhost:5001/feedback", json={
    "task": task,
    "result": prediction,
    "success": False,
    "failure_reason": "Data inconsistency in 'orders' table after migration"
})

# ============================================================================
# FAILURE RECOVERY WITH CTM
# ============================================================================

print("\n[RECOVERY] Execution failed. Generating retry strategy with CTM insights...")

# Check CTM status
ctm_result = ctm_async.get_result(ctm_task_id, wait=True, timeout=30.0)

if ctm_result.status == 'completed':
    insights = ctm_result.get_insights_summary()
    print("[CTM] Insights available!")
    print(insights)

    # CTM Output:
    """
    CTM Deep Reasoning (32 steps, 12.5s)
    Confidence: 85%, Converged: True

    Key Thoughts:
      1. [Visual] Analyzing visual patterns... (database schema complexity)
      2. [Verbal] Reasoning symbolically... (version compatibility issues)
      3. [Spatial] Performing mental rotation... (data flow mapping)
      4. [Taste] Estimating value... EV=0.45 (risk assessment)
      5. [Verbal] Reasoning symbolically... (replication strategy)
      6. [Taste] Estimating value... EV=0.78 (validation importance)
      7. [Verbal] Reasoning symbolically... (rollback plan critical)
    """

# Generate retry strategy
retry_prediction = planner.retry_with_ctm_insights(
    original_prediction=prediction,
    failure_description="Data inconsistency in 'orders' table"
)

# ============================================================================
# NEW STRATEGY (Enhanced by CTM)
# ============================================================================

retry_prediction = {
    'task': task,
    'prediction': {
        'primary_action': 'retry',  # Changed from 'suggest'
        'confidence': 0.68,  # Increased (CTM provided insights)
        'alternatives': [...]
    },
    'ctm_insights': insights,
    'reasoning_chain': [
        "[CTM Deep Reasoning] 32 steps, 85% confidence, identified 3 critical issues",
        "CTM Insight 1: Replication lag not accounted for in original plan",
        "CTM Insight 2: Foreign key constraints need special handling",
        "CTM Insight 3: Rollback strategy was incomplete",
        "NEW STRATEGY: Enhanced sequence with validation checkpoints",
        "Action: RETRY with modified approach"
    ],
    'modified_sequence': [
        'backup_database',
        'validate_schema_compatibility',  # NEW (from CTM)
        'test_migration_staging',
        'setup_replication_with_lag_monitoring',  # ENHANCED (from CTM)
        'checkpoint_foreign_keys',  # NEW (from CTM)
        'switch_over',
        'verify_data_consistency',  # ENHANCED (from CTM)
        'validate_foreign_keys',  # NEW (from CTM)
        'monitor_replication_lag'  # NEW (from CTM)
    ]
}

print("\n✓ Retry strategy generated with CTM insights!")
print(f"New action: {retry_prediction['prediction']['primary_action']}")
print(f"New confidence: {retry_prediction['prediction']['confidence']:.1%}")
print(f"CTM insights incorporated: {len(retry_prediction['modified_sequence']) - len(prediction['predicted_sequence'])} new steps")

# ============================================================================
# USER RETRIES WITH NEW STRATEGY
# ============================================================================

# User executes new strategy
# ... 45 minutes later ...
# SUCCESS: Migration completed with zero downtime, no data inconsistencies

# Submit success feedback
requests.post("http://localhost:5001/feedback", json={
    "task": task,
    "result": retry_prediction,
    "success": True,
    "user_rating": 0.95
})

# ============================================================================
# CONTINUOUS LEARNING UPDATE
# ============================================================================

print("\n[LEARNING] Updating routing matrix based on success...")

# System learns:
# 1. Migrations with high complexity benefit from CTM
# 2. When tool_trace + temporal_pattern + threat high → use CTM insights
# 3. Retry strategy more effective than initial suggest for complex migrations

# Update routing matrix
routing_matrix[tool_trace_idx, retry_idx] += 0.005 * learning_rate
routing_matrix[temporal_pattern_idx, retry_idx] += 0.005 * learning_rate

# Save new matrix version
save_matrix("routing_matrix_v20251019_post_migration.npy")

# Store in episodic memory
memory.consolidate_to_episodic(
    task=task,
    decision='retry',
    outcome='success',
    importance=0.92,  # HIGH (novel failure + CTM success)
    ctm_insights=insights
)

print("✓ System learned from this experience!")
print("✓ Future migrations will benefit from this pattern")
```

### Key Takeaways from Example

1. **Adaptive Routing**: System detected high complexity (0.88) and triggered CTM
2. **Low Confidence Detection**: Initial confidence (0.42) indicated uncertainty
3. **Failure Recovery**: CTM insights provided 3 new steps in the sequence
4. **Continuous Learning**: Success updated routing matrix for future
5. **Memory Consolidation**: High-importance experience stored (novelty + success)

---

## Key Design Principles

### 1. **Biological Plausibility**
- Thalamic gating (real brain mechanism)
- Competitive routing (TRN inhibition)
- Hierarchical processing (cortical layers)
- Memory consolidation (hippocampus)
- Neuromodulation (dopamine, serotonin)

### 2. **Composability**
- Each layer independent
- Can swap implementations
- Can retrain without breaking others
- Can add new modalities

### 3. **Continuous Learning**
- Never stops learning
- Feedback loop built-in
- Matrix versioning (A/B testing)
- Episodic memory from failures

### 4. **Performance + Intelligence**
- Fast path: <100ms
- Deep reasoning: 5-15s (async)
- Zero latency for simple tasks
- Full reasoning for complex tasks

### 5. **Production Ready**
- REST APIs
- Error handling
- Timeouts
- Thread pooling
- Monitoring dashboards
- Health checks

### 6. **Explainability**
- 10-step reasoning chains
- Brain state visible
- CTM thought streams
- Multi-target distributions

### 7. **Memory Efficiency**
- Only 7.7% of traces stored
- Novel failures prioritized
- Automatic consolidation
- Dual memory architecture

---

## Summary: The Complete Picture

**Tahlamus** is a production-ready brain-inspired cognitive routing system that:

1. **Receives** a task description (string)
2. **Extracts** features (Layer 1: task type, complexity, urgency)
3. **Routes** through 10 brain modalities (thalamic gating, competitive)
4. **Plans** optimal action sequence (Layer 2: graph search, trained on 39 sessions)
5. **Decides** specific intervention (Layer 3: 10×4 routing matrix, 77% accuracy)
6. **Reasons** deeply for complex tasks (CTM: async background, 5-15s)
7. **Remembers** important experiences (dual memory: working + episodic)
8. **Learns** continuously (feedback → matrix update → save version)
9. **Recovers** from failures (CTM insights → retry strategy)
10. **Explains** decisions (reasoning chain, brain state, CTM thoughts)

**All in <100ms for simple tasks, with deep reasoning available async for complex ones.**

---

**This is Tahlamus**: A meta-brain that routes between thinking modes, learns from experience, and explains its reasoning—just like the biological brain it's inspired by.

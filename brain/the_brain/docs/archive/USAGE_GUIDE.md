# Tahlamus Cognitive Architecture - Usage Guide

Complete guide for using and testing the 12-phase cognitive system.

## Table of Contents
1. [Quick Start](#quick-start)
2. [Testing Individual Phases](#testing-individual-phases)
3. [Testing Complete System](#testing-complete-system)
4. [Using in Your Code](#using-in-your-code)
5. [API Reference](#api-reference)
6. [Examples](#examples)

---

## Quick Start

### Test the Complete System

Run the complete cognitive system demo with all 12 phases:

```bash
python demos/test_complete_cognitive_system.py
```

This will demonstrate:
- All 12 phases working together
- Hierarchical routing through 3 layers
- Memory, attention, prediction, and more

### Test Individual Phases

Each phase can be tested independently:

```bash
# Memory Systems
python demos/test_memory_systems.py

# Predictive Coding
python demos/test_predictive_coding.py

# Attention Mechanisms
python demos/test_attention_mechanisms.py

# Meta-Learning
python demos/test_meta_learning.py

# Dream Mode
python demos/test_dream_mode.py

# Neuromodulation
python demos/test_neuromodulation.py

# Temporal Memory
python demos/test_temporal_memory.py

# Active Inference
python demos/test_active_inference.py

# Tool Creation
python demos/test_tool_creation.py

# Consciousness Metrics
python demos/test_consciousness_metrics.py

# Multi-Brain Swarm
python demos/test_multi_brain_swarm.py
```

---

## Testing Individual Phases

### PHASE 1: Memory Systems

Tests working memory, episodic memory, and memory retrieval.

```bash
python demos/test_memory_systems.py
```

**What it tests:**
- Working memory buffer (capacity 10)
- Episodic memory consolidation
- Similarity-based retrieval
- Memory statistics

**Expected output:**
- 5 tasks in working memory
- 3 similar tasks retrieved
- Memory statistics (size, success rate)

### PHASE 2: Predictive Coding

Tests prediction error minimization and curiosity signals.

```bash
python demos/test_predictive_coding.py
```

**What it tests:**
- Task feature prediction
- Decision outcome prediction
- Prediction error computation
- Curiosity-driven exploration

**Expected output:**
- Prediction errors for each layer
- Curiosity signals (epistemic, aleatoric)
- Surprise levels

### PHASE 3: Attention Mechanisms

Tests dynamic attention allocation across modalities.

```bash
python demos/test_attention_mechanisms.py
```

**What it tests:**
- Bottom-up attention (salience)
- Top-down attention (task relevance)
- Attention gating
- Attention statistics

**Expected output:**
- Attention weights per modality
- Attention type (focused, distributed, shifting)
- Top attended modalities

### PHASE 4: Meta-Learning

Tests learning to learn and adaptive meta-parameters.

```bash
python demos/test_meta_learning.py
```

**What it tests:**
- Meta-parameter adaptation
- Learning rate adjustment
- Exploration vs. exploitation
- Performance tracking

**Expected output:**
- Adapted learning rates
- Exploration rates
- Success rates over time

### PHASE 5: Dream Mode

Tests offline memory consolidation and pattern extraction.

```bash
python demos/test_dream_mode.py
```

**What it tests:**
- Dream cycle execution
- Pattern discovery
- Memory replay
- Schema formation

**Expected output:**
- Generated dreams
- Discovered patterns
- Consolidated knowledge

### PHASE 6: Neuromodulation

Tests neuromodulator-driven state changes.

```bash
python demos/test_neuromodulation.py
```

**What it tests:**
- Dopamine, serotonin, norepinephrine, acetylcholine levels
- Learning rate modulation
- Exploration boost
- Attention focus modulation

**Expected output:**
- Neuromodulator levels
- State descriptions (focused, exploratory, etc.)
- Effects on learning

### PHASE 7: Temporal Memory

Tests sequence learning and temporal patterns.

```bash
python demos/test_temporal_memory.py
```

**What it tests:**
- Event tagging (time-of-day, day-of-week)
- Markov chain learning
- Next-event prediction
- Memory decay

**Expected output:**
- Learned sequences
- Next-event predictions
- Temporal statistics

### PHASE 8: Active Inference

Tests hypothesis generation and question asking.

```bash
python demos/test_active_inference.py
```

**What it tests:**
- Multiple hypothesis generation
- Uncertainty estimation (epistemic, aleatoric)
- Question generation
- Information gain calculation

**Expected output:**
- Generated hypotheses
- Questions asked
- Uncertainty-driven behavior

### PHASE 10: Tool Creation

Tests dynamic capability generation.

```bash
python demos/test_tool_creation.py
```

**What it tests:**
- Capability gap identification
- Tool generation
- Tool composition
- Performance-based deprecation

**Expected output:**
- Identified gaps
- Generated tools
- Tool usage statistics

### PHASE 11: Consciousness Metrics

Tests self-awareness and meta-cognition.

```bash
python demos/test_consciousness_metrics.py
```

**What it tests:**
- Cognitive state tracking
- Confidence calibration
- Bias detection
- Introspection

**Expected output:**
- Cognitive states
- Meta-cognitive assessments
- Detected biases
- Known unknowns

### PHASE 12: Multi-Brain Swarm

Tests collaborative intelligence.

```bash
python demos/test_multi_brain_swarm.py
```

**What it tests:**
- Multiple specialized brains
- Consensus mechanisms
- Task decomposition
- Swarm intelligence metrics

**Expected output:**
- Swarm composition
- Consensus decisions
- Agreement levels
- Swarm metrics

---

## Testing Complete System

### Run Full Integration Test

```bash
python demos/test_complete_cognitive_system.py
```

This tests all 12 phases working together in the hierarchical planner.

**What it tests:**
- Layer 1: Task feature extraction
- Layer 2: Path planning with brain routing
- Layer 3: Multi-target actionable decisions
- All 12 cognitive phases integrated

**Expected output:**
```
===========================================
COMPLETE COGNITIVE SYSTEM TEST (7 PHASES)
===========================================

[1/4] Initializing complete system...
   HierarchicalPlanner(predictions=0, layers=3, memory=0/0)
   Memory: ENABLED
   Predictive Coding: ENABLED
   Attention: ENABLED
   Meta-Learning: ENABLED
   Dream Mode: ENABLED
   Neuromodulation: ENABLED
   Temporal Memory: ENABLED

[2/4] Testing cognitive system with tasks...

TASK 1/5: 'Deploy Docker container to production'
---------------------------------------------
  [MEMORY] Retrieved 0 similar tasks
  [PREDICTIVE] Task PE: 0.156, Curiosity: 0.423
  [ATTENTION] Type: focused, Focus: vision (0.42)
  [TEMPORAL MEMORY]
    Time: afternoon, Tuesday
    Previous: None

  Decision: execute (confidence: 87.3%)

...

[4/4] COMPLETE SYSTEM STATISTICS
===========================================

PHASE 1 - MEMORY SYSTEMS:
  Working memory: 5 items
  Episodic memory: 0 items
  Recent success rate: 100.0%

PHASE 2 - PREDICTIVE CODING:
  Predictions made: 10
  Average PE: 0.234

...

ALL 7 PHASES WORKING TOGETHER! ✓
```

---

## Using in Your Code

### Basic Usage

```python
from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

# Initialize Layer 2 components
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train Layer 2 from conversation logs (if available)
session_dir = "path/to/conversation/logs"
planner_layer2.train_from_sessions(session_dir, limit=100)

# Create hierarchical planner with all 12 phases
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,                     # PHASE 1
    enable_predictive_coding=True,          # PHASE 2
    enable_attention=True,                  # PHASE 3
    enable_meta_learning=True,              # PHASE 4
    enable_dream_mode=True,                 # PHASE 5
    enable_neuromodulation=True,            # PHASE 6
    enable_temporal_memory=True,            # PHASE 7
    enable_active_inference=True,           # PHASE 8
    enable_compositional_reasoning=True,    # PHASE 9
    enable_tool_creation=True,              # PHASE 10
    enable_consciousness_metrics=True,      # PHASE 11
    enable_multi_brain_swarm=True,          # PHASE 12
    seed=42
)

# Make a prediction
task = "Deploy Docker container to production"
prediction = planner.predict(task)

# Access results
decision = prediction.actionable_decision.multi_target_decision['primary']['type']
confidence = prediction.confidence

print(f"Decision: {decision} (confidence: {confidence:.1%})")
```

### Access Individual Phase Outputs

```python
# Memory context
if prediction.memory_context:
    similar_tasks = prediction.memory_context['working_memory']['similar_tasks']
    print(f"Found {len(similar_tasks)} similar tasks")

# Prediction errors
if prediction.prediction_errors:
    layer1_pe = prediction.prediction_errors['layer1']['error_magnitude']
    print(f"Task prediction error: {layer1_pe:.3f}")

# Attention state
if prediction.attention_state:
    top_modalities = prediction.attention_state.top_attended_modalities
    print(f"Top attended: {top_modalities}")

# Meta-learning parameters
if prediction.meta_parameters:
    learning_rate = prediction.meta_parameters.learning_rate
    print(f"Learning rate: {learning_rate:.4f}")

# Temporal context
if prediction.temporal_context:
    time_of_day = prediction.temporal_context.time_of_day
    print(f"Time: {time_of_day}")

# Active inference
if prediction.inference_state:
    hypotheses = prediction.inference_state.hypotheses
    should_ask = prediction.inference_state.should_ask_question
    print(f"Generated {len(hypotheses)} hypotheses, ask={should_ask}")

# Cognitive state
if prediction.cognitive_state:
    attention_focus = prediction.cognitive_state.attention_focus
    uncertainty = prediction.cognitive_state.uncertainty_level
    print(f"Attention: {attention_focus}, Uncertainty: {uncertainty:.2f}")

# Swarm decision
if prediction.swarm_decision:
    consensus = prediction.swarm_decision.consensus_decision
    agreement = prediction.swarm_decision.agreement_level
    print(f"Swarm: {consensus} (agreement: {agreement:.1%})")
```

### Record Outcomes and Learn

```python
# Record outcome for memory and meta-learning
planner.consolidate_experience(
    prediction=prediction,
    outcome='success',  # or 'failure'
    importance=0.8,
    user_rating=0.9,
    execution_time_ms=1500
)

# Trigger dream cycle for offline consolidation
if planner.enable_dream_mode:
    dreams = planner.trigger_dream_cycle(num_dreams=5)
    print(f"Consolidated {len(dreams)} dreams")
```

### Get Statistics

```python
stats = planner.get_statistics()

# Memory stats
if 'memory_stats' in stats:
    print(f"Working memory: {stats['memory_stats']['working_memory_size']}")
    print(f"Episodic memory: {stats['memory_stats']['episodic_memory_size']}")

# Predictive coding stats
if 'predictive_coding_stats' in stats:
    print(f"Avg prediction error: {stats['predictive_coding_stats']['average_prediction_error']:.3f}")

# Attention stats
if 'attention_stats' in stats:
    print(f"Attention updates: {stats['attention_stats']['total_attention_updates']}")

# And so on for all 12 phases...
```

---

## API Reference

### HierarchicalPlanner

Main class for the complete cognitive system.

#### `__init__(...)`

Initialize the hierarchical planner with all cognitive features.

**Parameters:**
- `conversation_planner` (ConversationPathPlanner): Pre-trained Layer 2 planner
- `modalities` (List[str], optional): Brain modality names
- `intervention_types` (List[str], optional): Available decision types
- `enable_memory` (bool): Enable memory systems (PHASE 1)
- `enable_predictive_coding` (bool): Enable predictive coding (PHASE 2)
- `enable_attention` (bool): Enable attention mechanisms (PHASE 3)
- `enable_meta_learning` (bool): Enable meta-learning (PHASE 4)
- `enable_dream_mode` (bool): Enable dream mode (PHASE 5)
- `enable_neuromodulation` (bool): Enable neuromodulation (PHASE 6)
- `enable_temporal_memory` (bool): Enable temporal memory (PHASE 7)
- `enable_active_inference` (bool): Enable active inference (PHASE 8)
- `enable_compositional_reasoning` (bool): Enable compositional reasoning (PHASE 9)
- `enable_tool_creation` (bool): Enable tool creation (PHASE 10)
- `enable_consciousness_metrics` (bool): Enable consciousness metrics (PHASE 11)
- `enable_multi_brain_swarm` (bool): Enable multi-brain swarm (PHASE 12)
- `seed` (int): Random seed for reproducibility

#### `predict(task_description: str) -> HierarchicalPrediction`

Make a prediction for a task.

**Parameters:**
- `task_description` (str): Task description

**Returns:**
- `HierarchicalPrediction`: Complete prediction with all phase outputs

#### `consolidate_experience(...)`

Consolidate an important experience to episodic memory and adapt.

**Parameters:**
- `prediction` (HierarchicalPrediction): The prediction to consolidate
- `outcome` (str): 'success' or 'failure'
- `importance` (float): Importance score (0-1)
- `user_rating` (float, optional): User rating
- `execution_time_ms` (float, optional): Execution time

#### `trigger_dream_cycle(num_dreams: Optional[int] = None) -> List[DreamState]`

Trigger offline consolidation through dream mode.

**Parameters:**
- `num_dreams` (int, optional): Number of dreams to generate

**Returns:**
- `List[DreamState]`: Generated dreams

#### `get_statistics() -> Dict`

Get statistics from all cognitive phases.

**Returns:**
- `Dict`: Statistics dictionary with keys for each enabled phase

### HierarchicalPrediction

Complete prediction output from all layers and phases.

**Attributes:**
- `layer1_routing` (RoutingState): Layer 1 feature routing
- `predicted_sequence` (List[str]): Layer 2 predicted sequence
- `confidence` (float): Overall confidence
- `actionable_decision` (ActionableDecision): Layer 3 decision
- `memory_context` (Dict, optional): Memory retrieval results (PHASE 1)
- `prediction_errors` (Dict, optional): Prediction errors (PHASE 2)
- `attention_state` (AttentionState, optional): Attention state (PHASE 3)
- `meta_parameters` (MetaParameters, optional): Meta-parameters (PHASE 4)
- `neuromodulator_levels` (NeuromodulatorLevels, optional): Neuromodulator levels (PHASE 6)
- `temporal_context` (TemporalContext, optional): Temporal context (PHASE 7)
- `inference_state` (InferenceState, optional): Active inference state (PHASE 8)
- `cognitive_state` (CognitiveState, optional): Cognitive state (PHASE 11)
- `swarm_decision` (SwarmDecision, optional): Swarm decision (PHASE 12)

---

## Examples

### Example 1: Simple Task Prediction

```python
from core.hierarchical_planner import HierarchicalPlanner
# ... initialize planner ...

# Make prediction
task = "List all running Docker containers"
prediction = planner.predict(task)

# Get decision
decision = prediction.actionable_decision.multi_target_decision['primary']['type']
print(f"Decision: {decision}")
```

### Example 2: Learning from Outcomes

```python
# Make prediction
task = "Deploy to production"
prediction = planner.predict(task)

# Execute task (simulated)
outcome = 'success'

# Record outcome
planner.consolidate_experience(
    prediction=prediction,
    outcome=outcome,
    importance=0.9,
    user_rating=0.95
)
```

### Example 3: Offline Consolidation

```python
# After many tasks, trigger dream mode
dreams = planner.trigger_dream_cycle(num_dreams=10)

# Check discovered patterns
for dream in dreams:
    if dream.pattern_discovered:
        pattern = dream.pattern_discovered
        print(f"Pattern: {pattern.task_type} -> {pattern.decision_type}")
        print(f"  Confidence: {pattern.confidence:.1%}")
```

### Example 4: Multi-Brain Collaboration

```python
# Create planner with swarm enabled
planner = HierarchicalPlanner(
    # ... other params ...
    enable_multi_brain_swarm=True,
    num_swarm_brains=5
)

# Make prediction (swarm votes)
prediction = planner.predict("Complex task requiring multiple domains")

# Check swarm consensus
if prediction.swarm_decision:
    print(f"Consensus: {prediction.swarm_decision.consensus_decision}")
    print(f"Agreement: {prediction.swarm_decision.agreement_level:.1%}")
    print(f"Mechanism: {prediction.swarm_decision.consensus_mechanism}")
```

---

## Troubleshooting

### No conversation logs available

If you don't have conversation logs for training Layer 2:

```python
# Use a minimal/empty planner
planner_layer2 = ConversationPathPlanner(
    meta_router=MetaRouter(enable_hippocampus=False, seed=42),
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# System will still work, but Layer 2 won't have learned patterns
```

### Memory not persisting

Enable episodic memory persistence:

```python
planner = HierarchicalPlanner(
    # ...
    enable_memory=True,
    memory_save_dir='./episodic_memories'  # Directory for persistence
)
```

### Statistics returning None

Make sure phases are enabled and used at least once:

```python
# Make at least one prediction
prediction = planner.predict("Test task")

# Then get statistics
stats = planner.get_statistics()
```

---

## Performance Tips

1. **Disable unused phases** for faster inference:
   ```python
   planner = HierarchicalPlanner(
       enable_dream_mode=False,  # Disable if not doing offline consolidation
       enable_multi_brain_swarm=False  # Disable if not using swarm
   )
   ```

2. **Limit memory sizes** for large-scale deployments:
   ```python
   planner.memory.working.capacity = 5  # Reduce working memory
   planner.memory.episodic.max_memories = 500  # Limit episodic memory
   ```

3. **Batch dream cycles** instead of after every task:
   ```python
   # Only run dreams periodically
   if num_tasks % 100 == 0:
       planner.trigger_dream_cycle()
   ```

---

## LLM Enhancement (Optional)

The cognitive system can be enhanced with LLM capabilities for more natural and intelligent interactions, particularly for question generation and hypothesis creation.

### Using LLM-Enhanced Active Inference

```python
from core.llm_enhanced_inference import LLM_Enhanced_ActiveInference
from anthropic import Anthropic  # or from openai import OpenAI

# Create LLM client
llm = Anthropic(api_key='your-api-key-here')

# Create LLM-enhanced inference
llm_inference = LLM_Enhanced_ActiveInference(
    llm_client=llm,
    use_llm_for={
        'question_generation': True,      # Natural, context-aware questions
        'hypothesis_generation': False,   # Keep cognitive for speed
        'decision_reasoning': False       # Keep cognitive for speed
    },
    max_hypotheses=5,
    max_questions=3,
    ask_threshold=0.7
)

# Create planner and replace active inference module
planner = HierarchicalPlanner(
    # ... standard params ...
    enable_active_inference=True
)

# Replace with LLM-enhanced version
planner.active_inference = llm_inference

# Use as normal
prediction = planner.predict("list all my containers in docker and get the logs")

# Questions will now be natural and context-aware!
if prediction.inference_state and prediction.inference_state.questions:
    for q in prediction.inference_state.questions:
        print(f"Question: {q.question_text}")
```

### Comparison: Cognitive vs LLM-Enhanced

**Cognitive-Only Questions (template-based):**
- "Is this task primarily about docker or docker?"
- "Should I wait for this task, or is there a better action?"

**LLM-Enhanced Questions (context-aware):**
- "Do you want to list all containers (including stopped ones) or only running containers?"
- "Should I retrieve logs for all containers, or do you want logs for specific containers?"

### Benefits of LLM Enhancement

**Advantages:**
- **Natural language**: Human-like phrasing
- **Context-aware**: Understands domain semantics (Docker, GitHub, etc.)
- **Specific**: Addresses actual ambiguities
- **Intelligent**: No redundant questions

**Trade-offs:**
- **Latency**: +100-500ms per LLM call (vs 1ms cognitive)
- **Cost**: API calls cost money (~$0.001/call)
- **Non-deterministic**: Questions may vary slightly
- **External dependency**: Requires LLM API access

### Recommended Approach: Hybrid

Use **cognitive for speed**, **LLM for quality**:

```python
llm_inference = LLM_Enhanced_ActiveInference(
    llm_client=llm,
    use_llm_for={
        'question_generation': True,      # LLM: High value, user-facing
        'hypothesis_generation': False,   # Cognitive: Internal, needs speed
        'decision_reasoning': False       # Cognitive: Fast routing
    }
)
```

This gives you:
- Fast routing (3ms) with cognitive system
- Natural questions (100ms) when user clarification needed
- Automatic fallback if LLM fails

### Testing LLM Enhancement

**Test with mock LLM (no API key needed):**
```bash
python demos/compare_cognitive_vs_llm.py
python demos/test_llm_enhanced_planner.py
```

**Test with real LLM:**
```bash
python demos/test_llm_enhanced_planner.py --use-llm --api-key YOUR_KEY
```

### LLM Statistics

Track LLM usage and effectiveness:

```python
if hasattr(planner.active_inference, 'get_llm_statistics'):
    stats = planner.active_inference.get_llm_statistics()
    print(f"LLM calls: {stats['llm_calls']}")
    print(f"Fallbacks: {stats['llm_fallbacks']}")
    print(f"Success rate: {stats['llm_success_rate']:.1%}")
```

---

## Next Steps

- Read `PRODUCTION_SYSTEM_COMPLETE.md` for production deployment
- Check `CONVERSATION_PUZZLE_SOLVER.md` for advanced routing patterns
- See `FINAL_STATUS.md` for system completion status
- Test LLM enhancement with `demos/compare_cognitive_vs_llm.py`

---

**Complete 12-Phase Cognitive Architecture** 🧠
Built with neuroscience-inspired design principles.

**Now with optional LLM enhancement for natural interactions!** 💬

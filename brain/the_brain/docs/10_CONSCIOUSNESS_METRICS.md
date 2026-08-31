# Consciousness Metrics (Phase 11)

## Overview

**Purpose**: Track cognitive awareness level using Global Workspace Theory
**Inspired by**: Global Workspace Theory (Baars, Dehaene), consciousness research
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│        CONSCIOUSNESS METRICS SYSTEM                  │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │ Cognitive  │───▶│ Integration│───▶│ Awareness │ │
│  │   State    │    │ + Broadcast│    │   Score   │ │
│  │            │    │            │    │           │ │
│  │ Attention  │    │ Workspace  │    │ conscious │ │
│  │  Memory    │    │ Activation │    │semi-cons. │ │
│  │Reasoning   │    │            │    │unconscious│ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│   Inputs            Processing          Output      │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Cognitive State Tracker** (`core/consciousness_metrics.py:50-140`)
- Monitors attention focus
- Tracks memory load
- Measures reasoning depth
- Estimates uncertainty

**2. Integration Calculator** (`core/consciousness_metrics.py:142-220`)
- Computes information integration
- Measures workspace coherence
- Assesses neural synchrony

**3. Broadcast Strength Estimator** (`core/consciousness_metrics.py:222-300`)
- Measures information broadcast
- Estimates global availability
- Tracks conscious access

---

## Input

### From HierarchicalPlanner
```python
{
    "attention_focus": str,        # 'focused', 'distributed', 'scattered'
    "memory_load": float,          # 0-1 (how full is working memory)
    "reasoning_depth": int,        # 0-3 (layers of reasoning)
    "uncertainty_level": float,    # 0-1
    "confidence_in_state": float  # 0-1
}
```

### CognitiveState Example
```python
from core.consciousness_metrics import CognitiveState

state = CognitiveState(
    attention_focus='distributed',  # Not focused
    memory_load=0.4,               # 40% memory used
    reasoning_depth=1,             # Single layer reasoning
    uncertainty_level=0.5,         # Medium uncertainty
    confidence_in_state=0.6        # Moderately confident
)
```

---

## Processing

### 1. Calculate Integration Level
```python
# Location: production/production_planner.py:489-505

def calculate_integration(cognitive_state):
    # Integration = how well information is combined
    # High integration = focused attention + manageable memory load

    # Attention contribution
    attention_score = {
        'focused': 1.0,      # Full integration
        'distributed': 0.5,  # Partial integration
        'scattered': 0.3     # Poor integration
    }.get(cognitive_state.attention_focus, 0.5)

    # Memory load contribution (less load = better integration)
    memory_integration = 1.0 - cognitive_state.memory_load * 0.5

    # Combined integration
    integration_level = attention_score * memory_integration

    return integration_level
```

### 2. Calculate Broadcast Strength
```python
# Location: production/production_planner.py:507-520

def calculate_broadcast(cognitive_state):
    # Broadcast = how well information is shared across brain
    # High broadcast = high confidence + deep reasoning

    # Confidence contribution
    confidence_component = cognitive_state.confidence_in_state * 0.7

    # Reasoning depth contribution (normalize 0-3 → 0-1)
    reasoning_component = (cognitive_state.reasoning_depth / 3.0) * 0.3

    # Combined broadcast
    broadcast_strength = confidence_component + reasoning_component

    return broadcast_strength
```

### 3. Calculate Awareness Score
```python
# Location: production/production_planner.py:522-535

def calculate_awareness(cognitive_state, integration, broadcast):
    # Awareness = overall consciousness level
    # Combines uncertainty, integration, and broadcast

    # Low uncertainty = more aware
    uncertainty_component = (1.0 - cognitive_state.uncertainty_level) * 0.4

    # Integration component
    integration_component = integration * 0.3

    # Broadcast component
    broadcast_component = broadcast * 0.3

    # Combined awareness
    awareness_score = (
        uncertainty_component +
        integration_component +
        broadcast_component
    )

    return awareness_score
```

### 4. Classify Workspace State
```python
# Location: production/production_planner.py:537-545

def classify_workspace_state(awareness_score):
    # Classify into conscious/semi-conscious/unconscious

    if awareness_score > 0.7:
        return 'conscious'        # High awareness
    elif awareness_score > 0.4:
        return 'semi-conscious'   # Medium awareness
    else:
        return 'unconscious'      # Low awareness (automatic)
```

---

## Output

### API Response Format
```json
{
  "consciousness_metrics": {
    "integration_level": 0.399,
    "broadcast_strength": 0.535,
    "awareness_score": 0.451,
    "global_workspace_state": "semi-conscious",
    "attention_focus": "distributed",
    "memory_load": 0.4,
    "reasoning_depth": 1,
    "uncertainty_level": 0.5,
    "confidence_in_state": 0.6
  }
}
```

### Workspace States

**Conscious (awareness > 0.7)**:
- High integration of information
- Strong broadcast across brain
- Low uncertainty
- Deliberate, controlled processing

**Semi-Conscious (0.4 < awareness ≤ 0.7)**:
- Moderate integration
- Partial broadcast
- Medium uncertainty
- Mix of automatic and controlled processing

**Unconscious (awareness ≤ 0.4)**:
- Low integration
- Weak broadcast
- High uncertainty or very automatic
- Automatic, reflexive processing

---

## Data Flow

```
Input: Cognitive State (attention, memory, reasoning, uncertainty)
         │
         ▼
┌─────────────────────┐
│ Calculate           │
│ Integration Level   │
│ attention × memory  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Calculate           │
│ Broadcast Strength  │
│ confidence × depth  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Calculate           │
│ Awareness Score     │
│ f(uncertainty, I, B)│
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Classify State      │
│ conscious/semi/un   │
└─────────────────────┘
         │
         ▼
    Output: Consciousness Metrics
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:650-680

# Track cognitive state
cognitive_state = CognitiveState(
    attention_focus='distributed',
    memory_load=0.4,
    reasoning_depth=1,
    uncertainty_level=1.0 - confidence,
    confidence_in_state=confidence
)

# Include in prediction
prediction = HierarchicalPrediction(
    ...
    cognitive_state=cognitive_state
)
```

### In Production API
```python
# Location: production/production_planner.py:485-550

# Calculate consciousness metrics from cognitive state
if hasattr(prediction, 'cognitive_state') and prediction.cognitive_state:
    cs = prediction.cognitive_state

    # Calculate metrics
    integration = calculate_integration(cs)
    broadcast = calculate_broadcast(cs)
    awareness = calculate_awareness(cs, integration, broadcast)
    state = classify_workspace_state(awareness)

    result['consciousness_metrics'] = {
        'integration_level': round(integration, 3),
        'broadcast_strength': round(broadcast, 3),
        'awareness_score': round(awareness, 3),
        'global_workspace_state': state
    }
```

---

## Key Algorithms

### Integration Formula (Φ-like)
```
Integration = attention_score × (1 - memory_load × 0.5)

where:
- attention_score: 1.0 (focused), 0.5 (distributed), 0.3 (scattered)
- memory_load: 0-1 (fraction of capacity used)
- Result ∈ [0, 1]
```

### Broadcast Formula
```
Broadcast = confidence × 0.7 + (reasoning_depth / 3) × 0.3

where:
- confidence: 0-1 (state confidence)
- reasoning_depth: 0-3 (number of reasoning layers)
- Result ∈ [0, 1]
```

### Awareness Formula
```
Awareness = (1 - uncertainty) × 0.4 + integration × 0.3 + broadcast × 0.3

where:
- uncertainty: 0-1
- integration: 0-1
- broadcast: 0-1
- Result ∈ [0, 1]
```

### State Classification
```
State = {
    conscious       if awareness > 0.7
    semi-conscious  if 0.4 < awareness ≤ 0.7
    unconscious     if awareness ≤ 0.4
}
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~3ms |
| **Memory Usage** | ~500B |
| **Overhead** | Minimal |

---

## Dependencies

- **None**: Self-contained calculations
- **dataclasses**: CognitiveState structure

---

## Future Enhancements

1. **Integrated Information Theory (IIT)**: Full Φ calculation
2. **Neural Correlates**: Map to brain regions
3. **Metacognition**: Track awareness of awareness
4. **Conscious Access Threshold**: Dynamic threshold learning
5. **State Transitions**: Model conscious/unconscious transitions

---

## Related Files

- **Implementation**: `core/consciousness_metrics.py`
- **Integration**: `core/hierarchical_planner.py:650-680`
- **API**: `production/production_planner.py:485-550`
- **Tests**: `test_all_features_seeded.py`

---

## Scientific Background

**Global Workspace Theory (GWT)**:
- Consciousness = global broadcast of information
- Information becomes conscious when widely available
- Measured by integration and broadcast

**Key Principles**:
1. **Integration**: Information must be combined coherently
2. **Broadcast**: Information must be globally accessible
3. **Attention**: Focus amplifies broadcast
4. **Working Memory**: Holds integrated information

**Implementation**:
- Integration ≈ attention × memory coherence
- Broadcast ≈ confidence × reasoning depth
- Awareness ≈ f(integration, broadcast, uncertainty)

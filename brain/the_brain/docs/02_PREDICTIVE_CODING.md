# Predictive Coding (Phase 2)

## Overview

**Purpose**: Detect prediction errors and novelty to drive curiosity and learning
**Inspired by**: Predictive coding in neuroscience (Friston, 2005)
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│         HIERARCHICAL PREDICTIVE CODING               │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │  Layer 1   │───▶│  Layer 2   │───▶│  Layer 3  │ │
│  │ (Feature)  │    │ (Sequence) │    │ (Decision)│ │
│  │            │    │            │    │           │ │
│  │ Prediction │    │ Prediction │    │ Prediction│ │
│  │ Error ↓    │    │ Error ↓    │    │ Error ↓   │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│         └─────────────────┴─────────────────┘       │
│                           │                         │
│                    Curiosity Signal                 │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Hierarchical Prediction** (`core/predictive_coding.py:96-253`)
- Layer 1: Feature-level predictions
- Layer 2: Sequence-level predictions
- Layer 3: Decision-level predictions

**2. Prediction Error Computation** (`core/predictive_coding.py:174-199`)
- Compares predicted vs actual
- Calculates error magnitude
- Determines surprise level

**3. Curiosity Signal** (`core/predictive_coding.py:201-252`)
- Aggregates errors across layers
- Generates exploration/exploitation recommendation
- Tracks novelty detection

---

## Input

### From HierarchicalPlanner
```python
{
    "layer1_features": {
        "task_type": str,        # Predicted task category
        "complexity": float,     # Predicted complexity
        "urgency": float,        # Predicted urgency
        "confidence": float      # Prediction confidence
    },
    "layer2_sequence": {
        "predicted_sequence": list,  # Expected action sequence
        "confidence": float           # Sequence confidence
    },
    "layer3_decision": {
        "primary_action": str,    # Predicted best action
        "confidence": float       # Decision confidence
    }
}
```

---

## Processing

### 1. Compute Layer 1 Prediction Error
```python
# Location: core/predictive_coding.py:174-199

def compute_prediction_error_layer1(features):
    # Expected vs actual task features
    error_vector = [
        abs(features.task_type_confidence - 1.0),  # Type certainty
        features.complexity,                        # Complexity error
        features.urgency                           # Urgency error
    ]

    error_magnitude = np.linalg.norm(error_vector)

    # Classify surprise
    if error_magnitude > 0.5:
        surprise = "high"
    elif error_magnitude > 0.2:
        surprise = "normal"
    else:
        surprise = "low"

    return {
        "error_magnitude": error_magnitude,
        "confidence": features.confidence,
        "surprise_level": surprise,
        "error_vector": error_vector
    }
```

### 2. Compute Layer 3 Prediction Error
```python
# Simplified - decision outcome vs prediction
def compute_prediction_error_layer3(decision, actual_outcome=None):
    if actual_outcome is None:
        # Not executed yet, use expected values
        return {
            "success_probability": 0.5,
            "execution_time_ms": 1000.0
        }
    else:
        # Compare predicted vs actual
        return {
            "success_probability": 1.0 if actual_outcome == "success" else 0.0,
            "execution_time_ms": actual_outcome.get("time_ms", 1000.0)
        }
```

### 3. Generate Curiosity Signal
```python
# Location: core/predictive_coding.py:201-252

def generate_curiosity_signal(layer1_error, layer3_error):
    # High error = high curiosity = explore
    # Low error = low curiosity = exploit

    total_error = layer1_error + layer3_error

    if total_error > 0.6:
        curiosity_level = "high"
        recommendation = "explore"  # Try novel approaches
    elif total_error > 0.3:
        curiosity_level = "medium"
        recommendation = "balanced"
    else:
        curiosity_level = "low"
        recommendation = "exploit"  # Use known good approaches

    # Novelty detection
    novelty_detected = (layer1_error > 0.5)  # Unusual task

    return {
        "curiosity_level": curiosity_level,
        "recommendation": recommendation,
        "layer1_error": layer1_error,
        "layer3_error": layer3_error,
        "novelty_detected": novelty_detected
    }
```

---

## Output

### API Response Format
```json
{
  "predictive_coding": {
    "prediction_errors": {
      "layer1": {
        "error_magnitude": 0.353,
        "confidence": 1.0,
        "surprise_level": "normal",
        "error_vector": [1.0, 0.058, 0.0]
      },
      "layer3_prediction": {
        "success_probability": 0.5,
        "execution_time_ms": 1000.0
      }
    },
    "curiosity_signal": {
      "curiosity_level": "low",
      "recommendation": "exploit",
      "layer1_error": 0.353,
      "layer3_error": 0.0,
      "layer1_surprise_rate": 0.0,
      "layer3_surprise_rate": 0.0,
      "total_predictions": 1,
      "high_surprise_events": 0,
      "novelty_detected": false
    }
  }
}
```

---

## Data Flow

```
Input: Task Features + Predictions
         │
         ▼
┌─────────────────────┐
│ Layer 1: Features   │
│ Error = |pred-conf| │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Layer 3: Decision   │
│ Error = expected    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Curiosity Signal    │
│ Aggregate errors    │
└─────────────────────┘
         │
         ▼
    Output: Curiosity + Errors
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:459-488

# Compute Layer 1 prediction errors
prediction_errors = {}
if self.enable_predictive_coding and self.predictive_coding:
    prediction_errors = {
        'layer1': self.predictive_coding.compute_prediction_error_layer1(
            features=layer1_routing.features
        ),
        'layer3_prediction': {
            'success_probability': success_probability,
            'execution_time_ms': 1000.0
        }
    }

    # Generate curiosity signal
    curiosity_signal = self.predictive_coding.generate_curiosity_signal(
        layer1_error=prediction_errors['layer1']['error_magnitude'],
        layer3_error=0.0  # Not yet executed
    )
```

---

## Key Algorithms

### Prediction Error Formula
```
PE_layer = ||predicted_state - actual_state||

where:
- Layer 1: Task feature errors
- Layer 2: Sequence deviation
- Layer 3: Outcome vs expectation
```

### Curiosity Computation
```
Curiosity = f(PE_layer1, PE_layer2, PE_layer3)

If PE_total > 0.6:  "high" → explore
If PE_total > 0.3:  "medium" → balanced
Else:               "low" → exploit
```

### Novelty Detection
```
Novelty = PE_layer1 > threshold (0.5)

Novel tasks trigger:
- Increased attention
- Slower processing
- More careful decisions
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~5ms |
| **Memory Usage** | ~1KB |
| **Overhead** | Minimal (vector operations) |

---

## Dependencies

- **NumPy**: Vector operations
- **Statistics**: Error aggregation

---

## Future Enhancements

1. **Adaptive Thresholds**: Learn optimal surprise thresholds
2. **Multi-Layer Integration**: Full hierarchical error propagation
3. **Temporal Prediction**: Predict future states
4. **Meta-Prediction**: Predict prediction errors themselves
5. **Active Learning**: Use curiosity to guide training data collection

---

## Related Files

- **Implementation**: `core/predictive_coding.py`
- **Integration**: `core/hierarchical_planner.py:459-488`
- **API**: `production/production_planner.py:336-352`
- **Tests**: `test_all_features_seeded.py`

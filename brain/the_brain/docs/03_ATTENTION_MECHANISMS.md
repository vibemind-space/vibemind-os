# Attention Mechanisms (Phase 3)

## Overview

**Purpose**: Selectively focus on relevant modalities and filter distractions
**Inspired by**: Attentional gating in neuroscience (selective vs distributed attention)
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│         ATTENTION MECHANISMS SYSTEM                  │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │ Salience   │───▶│  Attention │───▶│  Focused  │ │
│  │ Detection  │    │  Weights   │    │ Modalities│ │
│  │            │    │            │    │           │ │
│  │ 10 inputs  │    │  Softmax   │    │ Top-K     │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│    Bottom-up         Top-down         Output        │
│    (stimulus)        (task goal)                    │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Salience Detection** (`core/attention_mechanisms.py:50-120`)
- Computes salience scores for each modality
- Bottom-up stimulus-driven attention
- Based on activation strength

**2. Task-Driven Focus** (`core/attention_mechanisms.py:122-180`)
- Top-down goal-directed attention
- Task type influences focus
- Context-dependent weighting

**3. Attention Gating** (`core/attention_mechanisms.py:182-250`)
- Softmax-based attention weights
- Selective filtering (top-K modalities)
- Integration with thalamic gates

---

## Input

### From HierarchicalPlanner
```python
{
    "brain_gates": ndarray,        # 10-dim gate activations
    "modality_names": List[str],   # ['vision', 'audio', ..., 'tool_trace', ...]
    "task_type": str,              # 'docker', 'debugging', 'api', etc.
    "attention_mode": str          # 'selective' or 'distributed'
}
```

### Modality Activations
```python
brain_gates = np.array([
    0.15,  # vision
    0.08,  # audio
    0.05,  # touch
    0.02,  # taste
    0.03,  # vestibular
    0.10,  # threat
    0.35,  # tool_trace (highest)
    0.12,  # temporal_pattern
    0.06,  # error_signal
    0.04   # success_signal
])
```

---

## Processing

### 1. Compute Salience Scores
```python
# Location: core/attention_mechanisms.py:50-120

def compute_salience(modality_activations):
    # Bottom-up salience = activation strength
    salience_scores = []

    for i, activation in enumerate(modality_activations):
        # Salience = activation magnitude + variance + surprise
        salience = (
            activation * 1.0 +                    # Current strength
            np.std(activation_history[i]) * 0.3 + # Variance
            abs(activation - mean_activation) * 0.2  # Surprise
        )
        salience_scores.append(salience)

    return np.array(salience_scores)
```

### 2. Apply Task-Driven Modulation
```python
# Location: core/attention_mechanisms.py:122-180

def apply_task_modulation(salience, task_type):
    # Top-down modulation based on task
    task_weights = {
        'docker': {'tool_trace': 2.0, 'error_signal': 1.5},
        'debugging': {'error_signal': 2.0, 'tool_trace': 1.5},
        'api': {'tool_trace': 1.8, 'temporal_pattern': 1.3}
    }

    weights = task_weights.get(task_type, {})

    # Modulate salience
    modulated_salience = salience.copy()
    for modality, boost in weights.items():
        idx = modality_names.index(modality)
        modulated_salience[idx] *= boost

    return modulated_salience
```

### 3. Compute Attention Weights
```python
# Location: core/attention_mechanisms.py:182-220

def compute_attention_weights(salience, temperature=0.5):
    # Softmax over salience scores
    exp_salience = np.exp(salience / temperature)
    attention_weights = exp_salience / np.sum(exp_salience)

    return attention_weights
```

### 4. Select Focused Modalities
```python
# Location: core/attention_mechanisms.py:222-250

def select_focused_modalities(attention_weights, threshold=0.1):
    # Top-K selection based on threshold
    focused_indices = np.where(attention_weights > threshold)[0]

    # Sort by attention weight
    sorted_indices = sorted(
        focused_indices,
        key=lambda i: attention_weights[i],
        reverse=True
    )

    focused_modalities = [modality_names[i] for i in sorted_indices]

    return {
        'top_modality': focused_modalities[0] if focused_modalities else None,
        'focused_modalities': focused_modalities,
        'attention_weights': attention_weights.tolist()
    }
```

---

## Output

### API Response Format
```json
{
  "attention_state": {
    "top_modality": "tool_trace",
    "focused_modalities": [
      "tool_trace",
      "temporal_pattern",
      "error_signal"
    ],
    "attention_weights": [
      0.05,  // vision
      0.03,  // audio
      0.02,  // touch
      0.01,  // taste
      0.01,  // vestibular
      0.04,  // threat
      0.65,  // tool_trace (dominant!)
      0.12,  // temporal_pattern
      0.05,  // error_signal
      0.02   // success_signal
    ],
    "attention_mode": "selective",
    "focus_strength": 0.82
  }
}
```

---

## Data Flow

```
Input: Brain Gates (10 modalities)
         │
         ▼
┌─────────────────────┐
│ Salience Detection  │
│ s_i = ||activation||│
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Task Modulation     │
│ Boost task-relevant │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Softmax Attention   │
│ a_i = exp(s_i)/Σ    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Top-K Selection     │
│ Filter threshold    │
└─────────────────────┘
         │
         ▼
    Output: Focused Modalities
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:420-445

# Compute attention state
attention_state = None
if self.enable_attention and self.attention:
    attention_state = self.attention.compute_attention(
        modality_activations=brain_gates,
        task_type=task_type,
        mode='selective'  # or 'distributed'
    )

    # Apply attention to gates
    focused_gates = brain_gates * attention_state['attention_weights']
```

---

## Key Algorithms

### Salience Formula
```
Salience_i = β₁·activation_i + β₂·variance_i + β₃·surprise_i

where:
- activation_i: Current modality strength
- variance_i: Historical variance (novelty)
- surprise_i: Deviation from mean
- β₁=1.0, β₂=0.3, β₃=0.2 (weights)
```

### Attention Weights (Softmax)
```
α_i = exp(salience_i / τ) / Σⱼ exp(salience_j / τ)

where:
- τ: Temperature (0.5 = sharp focus, 1.0 = distributed)
- Σ α_i = 1.0 (normalized)
```

### Top-K Selection
```
Focused = {modality_i | α_i > threshold}

Default threshold = 0.1 (10% minimum attention)
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~2ms |
| **Memory Usage** | ~500B |
| **Overhead** | Minimal (vector operations) |

---

## Dependencies

- **NumPy**: Vector operations, softmax
- **Scipy**: Statistics (optional)

---

## Future Enhancements

1. **Dynamic Attention Switching**: Automatic mode switching based on task demands
2. **Multi-Scale Attention**: Coarse-to-fine focusing
3. **Attention History**: Temporal attention patterns
4. **Cross-Modal Attention**: Modality interactions
5. **Learned Attention**: Train attention weights from feedback

---

## Related Files

- **Implementation**: `core/attention_mechanisms.py`
- **Integration**: `core/hierarchical_planner.py:420-445`
- **API**: `production/production_planner.py:354-372`
- **Tests**: `test_all_features_seeded.py`

# Neuromodulation (Phase 6)

## Overview

**Purpose**: Modulate brain behavior via neurotransmitter systems (dopamine, serotonin, noradrenaline)
**Inspired by**: Neuromodulatory systems in the brain
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│         NEUROMODULATION SYSTEM                       │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │  Reward/   │───▶│Neurotrans- │───▶│  Behavior │ │
│  │  Hazard    │    │  mitters   │    │  Effects  │ │
│  │  Signals   │    │            │    │           │ │
│  │            │    │  DA, 5-HT, │    │ LR, ε, τ  │ │
│  │  Success   │    │     NE     │    │  boosts   │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│    Feedback         Modulation        Parameters    │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Dopamine System** (`core/neuromodulation.py:50-130`)
- Reward-driven learning
- Motivation and goal-seeking
- Learning rate modulation

**2. Serotonin System** (`core/neuromodulation.py:132-200`)
- Mood and patience
- Exploration vs exploitation
- Temporal discounting

**3. Noradrenaline System** (`core/neuromodulation.py:202-270`)
- Alertness and urgency
- Attention and focus
- Arousal modulation

---

## Input

### From HierarchicalPlanner
```python
{
    "reward": float,           # 0-1 (success signal)
    "hazard": float,           # 0-1 (threat/error signal)
    "outcome": str,            # 'success', 'failure', None
    "prediction_error": float, # |predicted - actual|
    "urgency": float          # Task urgency level
}
```

### Reward Signals
```python
# Success outcome
reward_signal = {
    'dopamine_boost': 0.8,     # High reward
    'outcome': 'success'
}

# Failure outcome
hazard_signal = {
    'dopamine_drop': -0.5,     # Negative reward
    'serotonin_drop': -0.3,    # Reduced mood
    'outcome': 'failure'
}

# Urgent task
urgency_signal = {
    'noradrenaline_boost': 0.7,  # Increased arousal
    'urgency': 0.9
}
```

---

## Processing

### 1. Update Dopamine
```python
# Location: core/neuromodulation.py:50-130

def update_dopamine(reward, prediction_error):
    # Dopamine = reward + prediction error (novelty)
    # Dopamine increases with unexpected rewards

    if reward is not None:
        # Reward-driven update
        dopamine_delta = reward - self.baseline_dopamine

        # Add prediction error (surprise bonus)
        if prediction_error is not None:
            dopamine_delta += prediction_error * 0.3

        # Update with decay
        self.dopamine = (
            self.dopamine * (1 - self.decay_rate) +
            dopamine_delta * self.learning_rate
        )

    # Clamp to [0, 1]
    self.dopamine = np.clip(self.dopamine, 0.0, 1.0)

    return self.dopamine
```

### 2. Update Serotonin
```python
# Location: core/neuromodulation.py:132-200

def update_serotonin(outcome, mood_decay=0.05):
    # Serotonin = mood, patience, persistence

    if outcome == 'success':
        # Success boosts mood
        serotonin_boost = 0.3
        self.serotonin = min(1.0, self.serotonin + serotonin_boost)

    elif outcome == 'failure':
        # Failure reduces mood
        serotonin_drop = -0.2
        self.serotonin = max(0.0, self.serotonin + serotonin_drop)

    # Natural decay to baseline (0.5)
    self.serotonin += (0.5 - self.serotonin) * mood_decay

    return self.serotonin
```

### 3. Update Noradrenaline
```python
# Location: core/neuromodulation.py:202-270

def update_noradrenaline(urgency, hazard):
    # Noradrenaline = alertness, arousal, focus

    # Urgency increases arousal
    urgency_boost = urgency * 0.5

    # Threat increases alertness
    hazard_boost = hazard * 0.7

    # Combined arousal
    arousal = urgency_boost + hazard_boost

    # Update with decay
    self.noradrenaline = (
        self.noradrenaline * (1 - self.decay_rate) +
        arousal * self.sensitivity
    )

    # Clamp to [0, 1]
    self.noradrenaline = np.clip(self.noradrenaline, 0.0, 1.0)

    return self.noradrenaline
```

### 4. Compute Behavioral Effects
```python
# Location: core/neuromodulation.py:272-340

def compute_effects():
    # Dopamine effects
    learning_rate_boost = 1.0 + (self.dopamine - 0.5) * 2.0  # Range: [0, 2]

    # Serotonin effects
    exploration_boost = (1.0 - self.serotonin) * 0.5  # Low mood → explore

    # Noradrenaline effects
    attention_boost = self.noradrenaline * 1.5  # High arousal → focus
    urgency_weight = self.noradrenaline * 2.0   # High arousal → urgency

    return {
        'learning_rate_boost': learning_rate_boost,
        'exploration_boost': exploration_boost,
        'attention_boost': attention_boost,
        'urgency_weight': urgency_weight
    }
```

---

## Output

### API Response Format
```json
{
  "neuromodulation": {
    "dopamine": 0.65,
    "serotonin": 0.52,
    "noradrenaline": 0.48,
    "effects": {
      "learning_rate_boost": 1.3,
      "exploration_boost": 0.24,
      "attention_boost": 0.72,
      "urgency_weight": 0.96
    },
    "state": "motivated",
    "baseline": {
      "dopamine": 0.5,
      "serotonin": 0.5,
      "noradrenaline": 0.5
    }
  }
}
```

### Neuromodulator States
- **Dopamine**:
  - High (>0.7): Motivated, high learning
  - Medium (0.3-0.7): Balanced
  - Low (<0.3): Demotivated, reduced learning

- **Serotonin**:
  - High (>0.7): Happy, patient, exploit
  - Medium (0.3-0.7): Balanced
  - Low (<0.3): Unhappy, impatient, explore

- **Noradrenaline**:
  - High (>0.7): Alert, focused, urgent
  - Medium (0.3-0.7): Balanced
  - Low (<0.3): Relaxed, distributed attention

---

## Data Flow

```
Input: Reward/Hazard/Urgency Signals
         │
         ▼
┌─────────────────────┐
│ Update Dopamine     │
│ reward + PE → DA    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Update Serotonin    │
│ outcome → 5-HT      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Update Noradrenaline│
│ urgency + hazard→NE │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Compute Effects     │
│ LR, ε, attention    │
└─────────────────────┘
         │
         ▼
    Output: Modulated Parameters
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:490-520

# Update neuromodulators
neuromodulation_state = None
if self.enable_neuromodulation and self.neuromodulation:
    # Compute reward from confidence
    reward = confidence if confidence else 0.5

    # Update neurotransmitters
    self.neuromodulation.update(
        reward=reward,
        urgency=layer1_routing.features.urgency,
        prediction_error=0.0  # Not yet known
    )

    # Get current state
    neuromodulation_state = self.neuromodulation.get_state()

    # Apply effects to learning
    effects = neuromodulation_state['effects']
    self.learning_rate *= effects['learning_rate_boost']
    self.exploration_rate += effects['exploration_boost']
```

### After Task Outcome
```python
# Update based on actual outcome
planner.neuromodulation.update(
    reward=1.0 if success else 0.0,
    outcome='success' if success else 'failure',
    prediction_error=abs(predicted_confidence - actual_confidence)
)
```

---

## Key Algorithms

### Dopamine Update (Reward Prediction Error)
```
DA[t+1] = DA[t] · (1-α) + (reward + β·PE) · α

where:
- α: Learning rate (0.1)
- β: PE weight (0.3)
- PE: |predicted - actual|
- DA ∈ [0, 1]
```

### Serotonin Update (Mood)
```
5-HT[t+1] = 5-HT[t] + Δ_outcome + γ·(0.5 - 5-HT[t])

where:
- Δ_outcome: +0.3 (success), -0.2 (failure)
- γ: Decay to baseline (0.05)
- 5-HT ∈ [0, 1]
```

### Noradrenaline Update (Arousal)
```
NE[t+1] = NE[t] · (1-α) + (urgency·0.5 + hazard·0.7) · sensitivity

where:
- α: Decay rate (0.1)
- sensitivity: Responsiveness (1.0)
- NE ∈ [0, 1]
```

### Behavioral Effects
```
LR_boost = 1.0 + (DA - 0.5) · 2.0  ∈ [0, 2]
ε_boost = (1.0 - 5-HT) · 0.5      ∈ [0, 0.5]
attention_boost = NE · 1.5         ∈ [0, 1.5]
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~1ms |
| **Memory Usage** | ~200B |
| **Overhead** | Negligible |

---

## Dependencies

- **NumPy**: Vector clipping, operations
- **None**: Self-contained module

---

## Future Enhancements

1. **Circadian Rhythms**: Time-of-day neuromodulator patterns
2. **Stress Response**: Cortisol system for prolonged challenges
3. **Homeostatic Regulation**: Auto-balance neurotransmitters
4. **Cross-Talk**: Interactions between DA/5-HT/NE
5. **Adaptive Baselines**: Learn optimal baseline levels

---

## Related Files

- **Implementation**: `core/neuromodulation.py`
- **Integration**: `core/hierarchical_planner.py:490-520`
- **API**: `production/production_planner.py:389-410`
- **Tests**: `test_all_features_seeded.py`

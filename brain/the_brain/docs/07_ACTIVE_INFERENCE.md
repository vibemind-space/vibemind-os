# Active Inference (Phase 8)

## Overview

**Purpose**: Generate clarification questions to reduce uncertainty via Bayesian inference
**Inspired by**: Active inference framework (Karl Friston), free energy principle
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│         ACTIVE INFERENCE SYSTEM                      │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │Uncertainty │───▶│ Hypotheses │───▶│ Questions │ │
│  │ Estimation │    │ Generation │    │  to Ask   │ │
│  │            │    │            │    │           │ │
│  │ Free Energy│    │  Bayesian  │    │ Info Gain │ │
│  │    F = KL  │    │  Beliefs   │    │ Maximize  │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│   Prediction         Inference          Actions     │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Free Energy Computation** (`core/active_inference.py:50-130`)
- Measures uncertainty in beliefs
- KL divergence between prior and posterior
- Drives information-seeking behavior

**2. Hypothesis Generator** (`core/active_inference.py:132-220`)
- Generates alternative hypotheses
- Bayesian belief updating
- Action proposals

**3. Question Generator** (`core/active_inference.py:222-310`)
- Identifies information gaps
- Generates clarification questions
- Ranks by expected information gain

---

## Input

### From HierarchicalPlanner
```python
{
    "task": str,                    # Task description
    "uncertainty": float,           # 0-1 confidence inverse
    "available_actions": List[str], # ['wait', 'execute', 'retry', ...]
    "current_beliefs": Dict[str, float],  # Belief distribution
    "context": Dict                 # Additional context
}
```

### Belief Distribution Example
```python
beliefs = {
    'task_is_docker': 0.7,      # 70% confident it's docker
    'urgent': 0.3,              # 30% confident it's urgent
    'has_health_check': 0.5     # 50% uncertain
}
```

---

## Processing

### 1. Compute Free Energy
```python
# Location: core/active_inference.py:50-130

def compute_free_energy(beliefs, observations):
    # Free Energy = Surprise + KL divergence
    # F = -log P(obs|beliefs) + KL(Q||P)

    # Surprise: How unexpected are observations?
    surprise = 0.0
    for obs_key, obs_value in observations.items():
        expected = beliefs.get(obs_key, 0.5)  # Prior belief
        surprise += abs(obs_value - expected)  # Prediction error

    # KL divergence (complexity cost)
    kl_divergence = 0.0
    for key in beliefs:
        q = beliefs[key]               # Approximate posterior
        p = 0.5                        # Uniform prior
        if q > 0 and p > 0:
            kl_divergence += q * np.log(q / p)

    # Free energy (minimize this!)
    free_energy = surprise + kl_divergence

    return {
        'free_energy': free_energy,
        'surprise': surprise,
        'complexity': kl_divergence
    }
```

### 2. Generate Hypotheses
```python
# Location: core/active_inference.py:132-220

def generate_hypotheses(task, available_actions, current_beliefs):
    # Generate alternative action hypotheses

    hypotheses = []

    for action in available_actions:
        # Create hypothesis for each action
        hypothesis = {
            'action': action,
            'expected_outcome': predict_outcome(action, task),
            'confidence': current_beliefs.get(f'should_{action}', 0.5),
            'free_energy': compute_expected_free_energy(action, task)
        }
        hypotheses.append(hypothesis)

    # Sort by expected free energy (lower = better)
    hypotheses.sort(key=lambda h: h['free_energy'])

    return hypotheses
```

### 3. Generate Questions
```python
# Location: core/active_inference.py:222-310

def generate_questions(hypotheses, uncertainty_threshold=0.5):
    # Generate questions to reduce uncertainty

    questions = []

    # Question 1: Clarify task type
    if max(current_beliefs.get('task_is_docker', 0),
           current_beliefs.get('task_is_debugging', 0)) < uncertainty_threshold:
        questions.append("Is this task primarily about docker or debugging?")

    # Question 2: Clarify best action
    if len(hypotheses) > 1:
        top_two = hypotheses[:2]
        if abs(top_two[0]['free_energy'] - top_two[1]['free_energy']) < 0.2:
            questions.append(
                f"Should I {top_two[0]['action']} or {top_two[1]['action']}?"
            )

    # Question 3: Clarify urgency
    if 'urgent' in current_beliefs and current_beliefs['urgent'] < uncertainty_threshold:
        questions.append("Is this task urgent?")

    # Question 4: Clarify missing information
    uncertainty_keys = [
        key for key, value in current_beliefs.items()
        if 0.4 < value < 0.6  # High uncertainty
    ]
    if uncertainty_keys:
        questions.append(
            f"Can you clarify: {', '.join(uncertainty_keys)}?"
        )

    return questions[:5]  # Max 5 questions
```

### 4. Update Beliefs (Bayesian)
```python
# Location: core/active_inference.py:312-380

def update_beliefs(prior_beliefs, new_evidence):
    # Bayesian belief update: P(H|E) = P(E|H)·P(H) / P(E)

    posterior_beliefs = {}

    for hypothesis, prior in prior_beliefs.items():
        # Likelihood: P(evidence | hypothesis)
        likelihood = compute_likelihood(new_evidence, hypothesis)

        # Posterior: P(hypothesis | evidence)
        posterior = (likelihood * prior) / marginal_likelihood

        posterior_beliefs[hypothesis] = posterior

    # Normalize
    total = sum(posterior_beliefs.values())
    for key in posterior_beliefs:
        posterior_beliefs[key] /= total

    return posterior_beliefs
```

---

## Output

### API Response Format
```json
{
  "active_inference": {
    "beliefs": {
      "task_is_docker": 0.7,
      "should_wait": 0.5,
      "urgent": 0.3
    },
    "free_energy": 1.23,
    "hypotheses": 3,
    "questions_to_ask": [
      "Is this task primarily about docker?",
      "Should I wait or is there a better action?",
      "Is this task urgent?"
    ],
    "best_hypothesis": {
      "action": "wait",
      "expected_outcome": "gather_information",
      "confidence": 0.5
    }
  }
}
```

---

## Data Flow

```
Input: Task + Uncertainty + Available Actions
         │
         ▼
┌─────────────────────┐
│ Compute Free Energy │
│ F = surprise + KL   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Generate Hypotheses │
│ For each action     │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Generate Questions  │
│ Maximize info gain  │
└─────────────────────┘
         │
         ▼
    Output: Questions + Hypotheses
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:547-580

# Generate active inference questions
active_inference_state = None
if self.enable_active_inference and self.active_inference:
    # Compute uncertainty
    uncertainty = 1.0 - confidence

    # Generate hypotheses and questions
    active_inference_state = self.active_inference.generate_questions(
        task=task_description,
        uncertainty=uncertainty,
        available_actions=self.layer3.intervention_types
    )

    # If high uncertainty, prioritize questions
    if uncertainty > 0.7:
        # Suggest asking user before acting
        primary_action = 'wait'  # Wait for clarification
```

---

## Key Algorithms

### Free Energy Formula
```
F = -log P(observations | beliefs) + KL(Q(beliefs) || P(beliefs))

where:
- First term: Surprise (prediction error)
- Second term: Complexity (divergence from prior)
- Goal: Minimize F by reducing uncertainty
```

### Bayesian Update
```
P(H | E) = P(E | H) · P(H) / P(E)

where:
- P(H | E): Posterior (updated belief)
- P(E | H): Likelihood (how well hypothesis explains evidence)
- P(H): Prior (initial belief)
- P(E): Marginal likelihood (normalization)
```

### Expected Information Gain
```
IG(question) = H(beliefs) - E[H(beliefs | answer)]

where:
- H: Entropy (uncertainty)
- E: Expectation over possible answers
- Maximize IG to select best question
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~10ms |
| **Memory Usage** | ~2KB |
| **Hypotheses** | 3-5 typical |
| **Questions** | 1-5 per request |

---

## Dependencies

- **NumPy**: Probability computations
- **Scipy**: KL divergence (optional)

---

## Future Enhancements

1. **Multi-Step Lookahead**: Plan question sequences
2. **Value of Information**: Quantify question utility
3. **Dialogue Management**: Conversational follow-ups
4. **Hierarchical Inference**: Multi-level belief updating
5. **Active Learning**: Use questions to improve model

---

## Related Files

- **Implementation**: `core/active_inference.py`
- **Integration**: `core/hierarchical_planner.py:547-580`
- **API**: `production/production_planner.py:429-452`
- **Tests**: `test_all_features_seeded.py`

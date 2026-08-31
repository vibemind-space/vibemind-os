# Meta-Learning (Phase 4)

## Overview

**Purpose**: Learn-to-learn by adapting learning parameters based on task similarity
**Inspired by**: Meta-learning (MAML, Reptile), few-shot learning
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│            META-LEARNING SYSTEM                      │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │   Task     │───▶│ Similarity │───▶│  Adapted  │ │
│  │  History   │    │  Analysis  │    │Parameters │ │
│  │            │    │            │    │           │ │
│  │ Past tasks │    │  Cosine    │    │ LR, ε, τ  │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│    Experience      Generalization      Exploitation │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Task Encoder** (`core/meta_learning.py:45-110`)
- Encodes task into feature vector
- Task type, complexity, urgency → embedding
- Similarity computation (cosine, euclidean)

**2. Experience Database** (`core/meta_learning.py:112-180`)
- Stores past task performances
- Success/failure outcomes
- Learned parameters per task type

**3. Parameter Adaptation** (`core/meta_learning.py:182-250`)
- Adjusts learning rate based on similarity
- Exploration vs exploitation trade-off
- Confidence-aware parameter tuning

---

## Input

### From HierarchicalPlanner
```python
{
    "current_task": {
        "description": str,         # Task text
        "task_type": str,          # Category
        "complexity": float,       # 0-1
        "urgency": float           # 0-1
    },
    "past_tasks": List[{
        "task_type": str,
        "complexity": float,
        "success": bool,
        "learning_rate_used": float,
        "exploration_rate_used": float
    }]
}
```

### Task Feature Vector
```python
task_embedding = np.array([
    task_type_onehot,      # 13-dim (task categories)
    complexity,            # 1-dim
    urgency,              # 1-dim
    has_docker,           # 1-dim (boolean features)
    has_redis,            # 1-dim
    has_health_check      # 1-dim
])  # Total: ~18-dim vector
```

---

## Processing

### 1. Encode Current Task
```python
# Location: core/meta_learning.py:45-110

def encode_task(task_description, task_type, complexity):
    # Extract task features
    features = {
        'task_type': task_type,
        'complexity': complexity,
        'keywords': extract_keywords(task_description),
        'length': len(task_description.split()),
        'urgency': detect_urgency_keywords(task_description)
    }

    # Convert to embedding
    embedding = np.concatenate([
        one_hot_encode(task_type, num_categories=13),
        [complexity],
        [features['urgency']],
        keyword_to_vector(features['keywords'])
    ])

    return embedding
```

### 2. Compute Task Similarity
```python
# Location: core/meta_learning.py:112-150

def compute_similarity(current_embedding, past_task_embeddings):
    # Cosine similarity
    similarities = []

    for past_embedding in past_task_embeddings:
        cosine_sim = np.dot(current_embedding, past_embedding) / (
            np.linalg.norm(current_embedding) * np.linalg.norm(past_embedding)
        )
        similarities.append(cosine_sim)

    # Find most similar task
    max_similarity = max(similarities) if similarities else 0.0
    most_similar_idx = np.argmax(similarities) if similarities else None

    return max_similarity, most_similar_idx
```

### 3. Adapt Learning Parameters
```python
# Location: core/meta_learning.py:182-250

def adapt_parameters(similarity, past_success_rate, base_lr=0.01):
    # High similarity + past success → exploit (lower exploration)
    # Low similarity → explore (higher exploration)

    if similarity > 0.7 and past_success_rate > 0.8:
        # Similar task succeeded before → exploit
        learning_rate = base_lr * 0.5  # Reduce LR
        exploration_rate = 0.1         # Low exploration
        strategy = 'exploit'

    elif similarity > 0.5:
        # Somewhat similar → balanced
        learning_rate = base_lr
        exploration_rate = 0.3
        strategy = 'balanced'

    else:
        # Novel task → explore
        learning_rate = base_lr * 2.0  # Increase LR
        exploration_rate = 0.5         # High exploration
        strategy = 'explore'

    return {
        'adapted_learning_rate': learning_rate,
        'exploration_rate': exploration_rate,
        'task_similarity': similarity,
        'strategy': strategy
    }
```

### 4. Update Experience Database
```python
# Location: core/meta_learning.py:252-300

def update_experience(task_embedding, outcome, parameters_used):
    # Store task experience
    experience_entry = {
        'embedding': task_embedding,
        'outcome': outcome,  # 'success' or 'failure'
        'learning_rate': parameters_used['learning_rate'],
        'exploration_rate': parameters_used['exploration_rate'],
        'timestamp': datetime.now()
    }

    # Add to database
    self.experience_db.append(experience_entry)

    # Update task-type statistics
    if task_type not in self.task_stats:
        self.task_stats[task_type] = {'successes': 0, 'failures': 0}

    if outcome == 'success':
        self.task_stats[task_type]['successes'] += 1
    else:
        self.task_stats[task_type]['failures'] += 1
```

---

## Output

### API Response Format
```json
{
  "meta_learning": {
    "adapted_learning_rate": 0.005,
    "task_similarity": 0.75,
    "exploration_rate": 0.2,
    "strategy": "exploit",
    "most_similar_past_task": "Deploy Docker container",
    "past_success_rate": 0.85,
    "experience_count": 47
  }
}
```

---

## Data Flow

```
Input: Current Task + Past Experience
         │
         ▼
┌─────────────────────┐
│ Task Encoding       │
│ features → vector   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Similarity Search   │
│ cosine(cur, past)   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Parameter Adaptation│
│ If similar→exploit  │
│ If novel→explore    │
└─────────────────────┘
         │
         ▼
    Output: Adapted Parameters
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:460-485

# Adapt learning parameters
meta_learning_state = None
if self.enable_meta_learning and self.meta_learning:
    meta_learning_state = self.meta_learning.adapt_learning_parameters(
        current_task=task_description,
        task_type=task_type,
        complexity=layer1_routing.features.complexity
    )

    # Use adapted learning rate for continuous learning
    if meta_learning_state:
        self.learning_rate = meta_learning_state['adapted_learning_rate']
        self.exploration_rate = meta_learning_state['exploration_rate']
```

### After Task Completion
```python
# Update experience database with outcome
planner.meta_learning.update_experience(
    task_embedding=task_embedding,
    outcome='success',
    parameters_used={'learning_rate': 0.005, 'exploration_rate': 0.2}
)
```

---

## Key Algorithms

### Task Similarity (Cosine)
```
similarity = (v₁ · v₂) / (||v₁|| · ||v₂||)

where:
- v₁: Current task embedding
- v₂: Past task embedding
- Result ∈ [0, 1] (normalized)
```

### Learning Rate Adaptation
```
LR_adapted = LR_base × adaptation_factor

adaptation_factor:
- If similarity > 0.7 & success_rate > 0.8: 0.5 (exploit)
- If similarity > 0.5: 1.0 (balanced)
- If similarity < 0.5: 2.0 (explore)
```

### Exploration Rate
```
ε = f(similarity, uncertainty)

ε_high (0.5): Novel tasks, high uncertainty
ε_medium (0.3): Familiar tasks, medium uncertainty
ε_low (0.1): Well-known tasks, low uncertainty
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~3ms |
| **Memory Usage** | ~1KB |
| **Experience DB** | ~100 entries typical |

---

## Dependencies

- **NumPy**: Vector operations, similarity
- **Scikit-learn**: Optional (cosine_similarity)

---

## Future Enhancements

1. **Cross-Domain Transfer**: Apply learning across task types
2. **Neural Task Encoding**: Learn embeddings instead of hand-crafted
3. **Multi-Objective Optimization**: Balance multiple learning objectives
4. **Hyperparameter Evolution**: Evolve optimal parameters per domain
5. **Few-Shot Adaptation**: Rapid adaptation from 1-5 examples

---

## Related Files

- **Implementation**: `core/meta_learning.py`
- **Integration**: `core/hierarchical_planner.py:460-485`
- **API**: `production/production_planner.py:373-388`
- **Tests**: `test_all_features_seeded.py`

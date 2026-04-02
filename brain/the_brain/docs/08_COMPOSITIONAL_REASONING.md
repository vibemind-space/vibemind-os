# Compositional Reasoning (Phase 9)

## Overview

**Purpose**: Decompose complex tasks into sequences of primitive actions
**Inspired by**: Compositional semantics, hierarchical task networks
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│      COMPOSITIONAL REASONING SYSTEM                  │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │  Complex   │───▶│ Primitives │───▶│ Composed  │ │
│  │   Task     │    │  Library   │    │ Sequences │ │
│  │            │    │            │    │           │ │
│  │  Docker +  │    │wait, exec, │    │[wait→exec │ │
│  │  Redis     │    │retry, term │    │ →verify]  │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│   Decomposition     Mapping           Composition   │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Primitive Actions** (`core/compositional_reasoning.py:45-120`)
- Basic action types: wait, execute, retry, terminate
- Preconditions and postconditions
- Success probability estimates

**2. Task Decomposer** (`core/compositional_reasoning.py:122-200`)
- Maps task types to action sequences
- Identifies dependencies
- Generates candidate sequences

**3. Sequence Composer** (`core/compositional_reasoning.py:202-290`)
- Composes primitives into sequences
- Evaluates feasibility
- Computes composed confidence

---

## Input

### From HierarchicalPlanner
```python
{
    "task_type": str,              # 'docker', 'debugging', 'api', etc.
    "available_actions": List[str], # ['wait', 'execute', 'retry', 'terminate']
    "context": {
        "uncertainty": float,       # 0-1
        "complexity": float,        # 0-1
        "urgency": float           # 0-1
    }
}
```

### Task Complexity Example
```python
context = {
    'uncertainty': 0.5,    # Medium uncertainty
    'complexity': 0.44,    # Medium complexity
    'task_type': 'docker'  # Docker deployment
}
```

---

## Processing

### 1. Map Task to Primitives
```python
# Location: core/compositional_reasoning.py:45-120

def map_task_to_primitives(task_type):
    # Define primitive mappings for each task type

    primitive_mappings = {
        'docker': ['decide', 'execute', 'verify', 'retry'],
        'debugging': ['analyze', 'execute', 'test', 'retry'],
        'api': ['validate', 'execute', 'test'],
        'generic': ['wait', 'execute']
    }

    # Get primitives for task type
    primitives = primitive_mappings.get(task_type, primitive_mappings['generic'])

    return [
        ActionPrimitive(
            action_type=p,
            preconditions=get_preconditions(p),
            postconditions=get_postconditions(p),
            expected_duration=estimate_duration(p)
        )
        for p in primitives
    ]
```

### 2. Compose Sequences
```python
# Location: core/compositional_reasoning.py:122-200

def compose_novel_sequence(task_type, available_actions, context):
    # Generate action sequences from primitives

    primitives = self.map_task_to_primitives(task_type)

    # Compose sequences
    sequences = []

    # Simple sequential composition
    if context['uncertainty'] > 0.6:
        # High uncertainty → start with wait
        sequence = [
            ActionPrimitive('wait', expected_duration=1.0),
            ActionPrimitive('execute', expected_duration=3.0),
            ActionPrimitive('verify', expected_duration=1.0)
        ]
    elif context['urgency'] > 0.7:
        # Urgent → skip wait
        sequence = [
            ActionPrimitive('execute', expected_duration=3.0),
            ActionPrimitive('verify', expected_duration=1.0)
        ]
    else:
        # Normal → standard sequence
        sequence = primitives

    # Compute success probability
    success_rate = 1.0
    for action in sequence:
        success_rate *= action.expected_success_rate

    sequences.append(
        ComposedSequence(
            actions=sequence,
            expected_success_rate=success_rate,
            total_duration=sum(a.expected_duration for a in sequence)
        )
    )

    return sequences
```

### 3. Evaluate Feasibility
```python
# Location: core/compositional_reasoning.py:202-260

def evaluate_sequence(sequence, context):
    # Check if sequence is feasible

    # Check preconditions
    current_state = {'ready': True, 'executed': False}

    for action in sequence.actions:
        # Check preconditions met
        if not all(current_state.get(pre, False)
                   for pre in action.preconditions):
            return {'feasible': False, 'reason': f'Precondition not met for {action.action_type}'}

        # Update state with postconditions
        for post in action.postconditions:
            current_state[post] = True

    # Check total duration
    if sequence.total_duration > context.get('max_duration', 60.0):
        return {'feasible': False, 'reason': 'Sequence too long'}

    return {'feasible': True, 'confidence': sequence.expected_success_rate}
```

### 4. Extract Subtasks
```python
# Location: core/compositional_reasoning.py:262-290

def extract_subtasks(composed_sequences):
    # Extract subtasks from best sequence

    if not composed_sequences:
        return {
            'subtasks': [],
            'dependencies': [],
            'composed_confidence': 0.0
        }

    # Get best sequence
    best_sequence = composed_sequences[0]

    # Extract subtask names
    subtasks = [action.action_type for action in best_sequence.actions]

    # Extract dependencies (sequential)
    dependencies = []
    for i in range(len(subtasks) - 1):
        dependencies.append({
            'from': subtasks[i],
            'to': subtasks[i + 1],
            'type': 'sequential'
        })

    return {
        'subtasks': subtasks,
        'dependencies': dependencies,
        'composed_confidence': best_sequence.expected_success_rate,
        'num_sequences': len(composed_sequences)
    }
```

---

## Output

### API Response Format
```json
{
  "composition": {
    "subtasks": [
      "decide",
      "execute",
      "verify"
    ],
    "dependencies": [
      {"from": "decide", "to": "execute", "type": "sequential"},
      {"from": "execute", "to": "verify", "type": "sequential"}
    ],
    "composed_confidence": 0.72,
    "num_sequences": 1,
    "total_duration_estimate": 5.0
  }
}
```

---

## Data Flow

```
Input: Task Type + Available Actions
         │
         ▼
┌─────────────────────┐
│ Map to Primitives   │
│ task → primitives   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Compose Sequences   │
│ primitives → seq    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Evaluate Feasibility│
│ preconditions check │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Extract Subtasks    │
│ seq → subtasks      │
└─────────────────────┘
         │
         ▼
    Output: Subtasks + Dependencies
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:593-631

# Compositional reasoning
composition_result = None
if self.enable_compositional_reasoning and self.compositional_reasoning:
    # Get available actions from Layer 3
    available_actions = self.layer3.intervention_types

    # Compose novel sequences
    context_for_composition = {
        'uncertainty': 1.0 - confidence,
        'complexity': layer1_routing.features.complexity,
        'task_type': task_type
    }

    novel_sequences = self.compositional_reasoning.compose_novel_sequence(
        task_type=task_type,
        available_actions=available_actions,
        context=context_for_composition
    )

    # Extract subtasks
    if novel_sequences:
        best_seq = novel_sequences[0]
        composition_result = {
            'subtasks': [action.action_type for action in best_seq.actions],
            'dependencies': [],
            'composed_confidence': best_seq.expected_success_rate
        }
```

---

## Key Algorithms

### Sequential Composition
```
Sequence S = [a₁, a₂, ..., aₙ]

Precondition(S) = Precondition(a₁)
Postcondition(S) = Postcondition(aₙ)
Success(S) = ∏ᵢ Success(aᵢ)
```

### Dependency Graph
```
Dependency: (aᵢ, aⱼ) ∈ E if Postcondition(aᵢ) ∈ Precondition(aⱼ)

Types:
- Sequential: aᵢ → aⱼ (must execute in order)
- Parallel: aᵢ ∥ aⱼ (can execute together)
- Conditional: aᵢ ⇒ aⱼ (execute aⱼ if aᵢ succeeds)
```

### Confidence Composition
```
Confidence(composed) = ∏ᵢ Confidence(primitive_i) · feasibility_factor

feasibility_factor = 1.0 if all preconditions met, else 0.0
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~8ms |
| **Memory Usage** | ~1KB |
| **Max Sequence Length** | 5-10 actions |

---

## Dependencies

- **None**: Self-contained module
- **NumPy**: Optional (probability computations)

---

## Future Enhancements

1. **Hierarchical Planning**: Multi-level task decomposition
2. **Parallel Composition**: Concurrent action sequences
3. **Learning Primitives**: Discover new primitives from experience
4. **Goal-Oriented Planning**: STRIPS-like planning
5. **Constraint Satisfaction**: Add temporal and resource constraints

---

## Related Files

- **Implementation**: `core/compositional_reasoning.py`
- **Integration**: `core/hierarchical_planner.py:593-631`
- **API**: `production/production_planner.py:453-468`
- **Tests**: `test_all_features_seeded.py`

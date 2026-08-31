# Memory Systems (Phase 1)

## Overview

**Purpose**: Store and retrieve task experiences to learn from past decisions
**Inspired by**: Human memory systems (Working, Episodic memory)
**Status**: ✅ ACTIVE

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              MEMORY MANAGER                         │
│                                                     │
│  ┌──────────────────┐      ┌──────────────────┐   │
│  │ Working Memory   │      │ Episodic Memory  │   │
│  │ (Short-term)     │      │ (Long-term)      │   │
│  │                  │      │                  │   │
│  │ • 10 slots       │      │ • 1000 max       │   │
│  │ • Recent tasks   │─────▶│ • Consolidation  │   │
│  │ • 30s buffer     │      │ • Novelty-based  │   │
│  └──────────────────┘      └──────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Components

**1. Working Memory** (`core/memory_systems.py:93-257`)
- **Capacity**: 10 items
- **Retention**: ~30 seconds (recent task buffer)
- **Function**: Hold active tasks for immediate retrieval
- **Eviction**: FIFO (oldest removed first)

**2. Episodic Memory** (`core/memory_systems.py:259-507`)
- **Capacity**: 1000 items
- **Retention**: Permanent (with importance-based eviction)
- **Function**: Store significant experiences with outcomes
- **Eviction**: Least important items removed when full

**3. Memory Manager** (`core/memory_systems.py:509-656`)
- **Function**: Coordinate working + episodic memory
- **Consolidation**: Move important tasks from working → episodic
- **Retrieval**: Search both memories for relevant context

---

## Input

### Task Information
```python
{
    "task": str,              # Task description
    "task_type": str,         # Category (docker, debugging, api, etc.)
    "decision": str,          # Action taken (execute, wait, retry, etc.)
    "confidence": float,      # 0-1 confidence score
    "brain_gates": ndarray,   # 10-dim brain activation pattern
    "outcome": str | None     # "success" | "failure" | None
}
```

### For Episodic Consolidation (Additional)
```python
{
    "layer1_features": dict,      # Task features (complexity, urgency)
    "layer2_sequence": list,      # Predicted action sequence
    "reasoning_chain": list,      # Decision reasoning steps
    "importance": float,          # 0-1 importance score
    "emotional_valence": str,     # "positive" | "negative" | "neutral"
    "prediction_error": float,    # |predicted - actual|
    "execution_time_ms": float,   # How long it took
    "user_rating": float          # 0-1 user feedback
}
```

---

## Processing

### 1. Remember Task (Working Memory)
```python
# Location: core/memory_systems.py:539-569
def remember_task(task, task_type, decision, confidence, brain_gates, outcome):
    # Create working memory entry
    entry = WorkingMemoryEntry(
        task=task,
        task_type=task_type,
        decision=decision,
        confidence=confidence,
        outcome=outcome,
        brain_gates=brain_gates,
        timestamp=datetime.now()
    )

    # Add to circular buffer (FIFO)
    working_memory.add(entry)

    # Return: Entry stored in working memory
```

### 2. Consolidate to Episodic
```python
# Location: core/memory_systems.py:571-612
def consolidate_to_episodic(task, outcome, importance, ...):
    # Create episodic entry
    entry = EpisodicMemoryEntry(
        task=task,
        outcome=outcome,
        importance=importance,
        brain_gates=brain_gates,
        layer1_features=layer1_features,
        reasoning_chain=reasoning_chain,
        ...
    )

    # Add to episodic memory
    # If full, evict least important
    episodic_memory.add(entry)

    # Save to disk (persistent storage)
    if save_dir:
        _save_memory(entry)
```

### 3. Retrieve Memories
```python
# Location: core/memory_systems.py:122-143
def get_recent(n=5):
    # Get N most recent tasks from working memory
    return working_memory.buffer[-n:]

# Location: core/memory_systems.py:324-371
def get_important_memories(top_k=10):
    # Sort episodic memories by importance
    sorted_memories = sorted(
        episodic_memory.memories,
        key=lambda m: m.importance,
        reverse=True
    )
    return sorted_memories[:top_k]
```

---

## Output

### API Response Format
```json
{
  "memory_context": {
    "working_memory": [
      "Deploy Docker container",
      "Fix Redis connection timeout",
      "Update API endpoints",
      "Run integration tests"
    ],
    "episodic_memories": [
      {
        "task": "Deploy with Docker urgently",
        "decision": "execute",
        "outcome": "success"
      },
      {
        "task": "Debug memory leak",
        "decision": "retry",
        "outcome": "success"
      }
    ],
    "working_memory_size": 4,
    "episodic_memory_size": 2
  }
}
```

---

## Data Flow

```
Input Task
    │
    ├──▶ remember_task()
    │        │
    │        ▼
    │    Working Memory (10 slots, 30s buffer)
    │        │
    │        │ Important + Outcome known?
    │        ▼
    └──▶ consolidate_to_episodic()
             │
             ▼
         Episodic Memory (1000 max, permanent)
             │
             │ Disk persistence
             ▼
         Saved to file system
```

### Retrieval Flow
```
New Task → task_type identified
    │
    ├──▶ get_recent(5) → Recent working memory
    │
    └──▶ get_important_memories(5) → Top episodic memories
             │
             ▼
         Relevant context for prediction
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:753-759

# After prediction, store in working memory
if self.enable_memory and self.memory:
    self.memory.remember_task(
        task=task_description,
        task_type=task_type,
        decision=primary_action,
        confidence=confidence,
        brain_gates=brain_gates,
        outcome=None  # Not yet known
    )
```

### In Production API (Feedback)
```python
# Location: production/production_planner.py (feedback endpoint)

# When outcome is known, consolidate to episodic
planner.memory.consolidate_to_episodic(
    task=task,
    task_type=task_type,
    decision=decision,
    confidence=confidence,
    outcome="success",  # Now known!
    importance=0.9,
    emotional_valence="positive",
    prediction_error=0.1
)
```

### In Production Response
```python
# Location: production/production_planner.py:307-333

# Retrieve memories for context
working_entries = planner.memory.working.get_recent(n=5)
episodic_entries = planner.memory.episodic.get_important_memories(top_k=5)

result['memory_context'] = {
    'working_memory': [entry.task for entry in working_entries],
    'episodic_memories': [{
        'task': e.task,
        'decision': e.decision,
        'outcome': e.outcome
    } for e in episodic_entries],
    'working_memory_size': len(working_memory.buffer),
    'episodic_memory_size': len(episodic_memory.memories)
}
```

---

## Key Algorithms

### 1. Working Memory Circular Buffer
```python
# FIFO eviction when full
class WorkingMemory:
    def __init__(self, capacity=10):
        self.buffer = deque(maxlen=capacity)  # Automatic FIFO

    def add(self, entry):
        self.buffer.append(entry)  # Old items auto-removed
```

### 2. Episodic Memory Importance-Based Eviction
```python
# Remove least important when full
def add(self, entry):
    if len(self.memories) >= self.max_size:
        # Find least important
        least_important = min(self.memories, key=lambda m: m.importance)
        self.memories.remove(least_important)

    self.memories.append(entry)
```

### 3. Similarity Search
```python
# Find similar past experiences
def retrieve_similar(self, brain_gates, top_k=5):
    # Compute cosine similarity
    similarities = [
        (memory, cosine_similarity(brain_gates, memory.brain_gates))
        for memory in self.memories
    ]

    # Sort by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)
    return [mem for mem, sim in similarities[:top_k]]
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~5ms |
| **Memory Usage** | ~500 bytes per entry |
| **Storage** | Persistent (disk-backed) |
| **Capacity** | 10 working + 1000 episodic |

---

## Dependencies

- **NumPy**: Brain gate vectors
- **datetime**: Timestamps
- **collections.deque**: Circular buffer
- **dataclasses**: Memory entry structures

---

## Future Enhancements

1. **Semantic Search**: Use embeddings instead of brain gates
2. **Memory Decay**: Time-based importance reduction
3. **Clustering**: Group similar experiences
4. **Transfer Learning**: Apply knowledge across task types
5. **Working→Episodic Auto-Consolidation**: Automatic promotion based on importance

---

## Related Files

- **Implementation**: `core/memory_systems.py`
- **Integration**: `core/hierarchical_planner.py:252-258, 753-759`
- **API**: `production/production_planner.py:307-333`
- **Seeding**: `seed_memory_systems.py`
- **Tests**: `test_all_features_seeded.py`

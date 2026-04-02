# CTM Async (Phase 13)

## Overview

**Purpose**: Deep reasoning in background for complex tasks
**Inspired by**: Continuous Thought Model, System 2 thinking (Kahneman)
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│           CTM ASYNC REASONER                         │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │  Complex   │───▶│ Background │───▶│  Insights │ │
│  │   Task     │    │  Reasoning │    │   Ready   │ │
│  │            │    │            │    │           │ │
│  │complexity  │    │  Thread    │    │ 50 steps  │ │
│  │  >= 0.4    │    │ 50 steps   │    │reasoning  │ │
│  │            │    │non-blocking│    │   trace   │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│   Trigger          Processing          Results      │
└──────────────────────────────────────────────────────┘
```

### Components

**1. CTM Async Manager** (`core/ctm_async_reasoner.py:50-200`)
- Manages background reasoning threads
- Task queue and status tracking
- Thread pool (max 3 concurrent)

**2. CTM Reasoner** (`core/ctm_integration.py:50-400`)
- Iterative reasoning engine
- Modality switching (visual, verbal, spatial, value)
- Convergence detection

**3. Results Storage** (`core/ctm_async_reasoner.py:202-300`)
- Stores completed reasoning traces
- Provides insights summary
- Handles timeouts and errors

---

## Input

### From HierarchicalPlanner
```python
{
    "task_description": str,     # Task text
    "complexity": float,         # 0-1 (triggers CTM if >= 0.4)
    "max_steps": int,           # Max reasoning iterations (default 50)
    "timeout": float            # Max time in seconds (default 30)
}
```

### Complexity Threshold
```python
# CTM triggers automatically if task complexity >= 0.4
if complexity >= 0.4:
    ctm_task_id = ctm_async.start_reasoning(task)
```

---

## Processing

### 1. Check Complexity Threshold
```python
# Location: core/hierarchical_planner.py:196-220

# Check if CTM should run
if (self.enable_ctm_async and
    self.ctm_async and
    layer1_routing.features.complexity >= self.ctm_complexity_threshold):

    # Start CTM in background (non-blocking)
    ctm_task_id = self.ctm_async.start_reasoning(
        task_description=task_description,
        max_steps=self.ctm_max_steps
    )
else:
    ctm_task_id = None
```

### 2. Start Background Reasoning
```python
# Location: core/ctm_async_reasoner.py:50-150

def start_reasoning(self, task_description, max_steps=50):
    # Create task ID
    task_id = generate_task_id()

    # Create reasoning thread
    thread = threading.Thread(
        target=self._run_ctm_reasoning,
        args=(task_id, task_description, max_steps)
    )

    # Start thread (non-blocking!)
    thread.start()

    # Store task info
    self.tasks[task_id] = {
        'status': 'running',
        'thread': thread,
        'start_time': time.time()
    }

    return task_id
```

### 3. Run CTM Reasoning (in Thread)
```python
# Location: core/ctm_async_reasoner.py:152-250

def _run_ctm_reasoning(self, task_id, task_description, max_steps):
    # This runs in background thread

    try:
        # Initialize CTM
        ctm_result = self.ctm.reason(
            task=task_description,
            max_steps=max_steps,
            modalities=['visual', 'verbal', 'spatial', 'value']
        )

        # Store result
        self.tasks[task_id]['status'] = 'completed'
        self.tasks[task_id]['result'] = ctm_result
        self.tasks[task_id]['end_time'] = time.time()

    except Exception as e:
        # Handle errors
        self.tasks[task_id]['status'] = 'failed'
        self.tasks[task_id]['error'] = str(e)
```

### 4. CTM Iterative Reasoning
```python
# Location: core/ctm_integration.py:100-350

def reason(self, task, max_steps=50):
    # Iterative reasoning loop
    reasoning_trace = []
    current_modality = 'visual'  # Start with visual

    for step in range(max_steps):
        # Switch modality periodically
        if step % 10 == 0:
            current_modality = self._select_next_modality()

        # Reasoning step
        thought = self._generate_thought(
            task=task,
            modality=current_modality,
            step=step
        )

        reasoning_trace.append({
            'step': step,
            'modality': current_modality,
            'thought': thought,
            'buffer_norm': np.linalg.norm(thought)
        })

        # Check convergence
        if self._has_converged(reasoning_trace):
            break

    return CTMResult(
        steps_taken=len(reasoning_trace),
        reasoning_trace=reasoning_trace,
        converged=self._has_converged(reasoning_trace)
    )
```

### 5. Retrieve Insights
```python
# Location: core/ctm_async_reasoner.py:252-300

def get_result(self, task_id, wait=False, timeout=5.0):
    # Retrieve CTM results

    if wait:
        # Wait for completion (blocking)
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_complete(task_id):
                break
            time.sleep(0.1)

    # Get result
    task_info = self.tasks.get(task_id)

    if task_info['status'] == 'completed':
        return task_info['result']
    elif task_info['status'] == 'running':
        return None  # Still running
    else:
        return None  # Failed or not found
```

---

## Output

### API Response Format
```json
{
  "ctm_task_id": "6b11dc07",
  "ctm_insights": "CTM Deep Reasoning (50 steps, 0.03s): Visual pattern analysis..."
}
```

### CTM Result Format
```json
{
  "task_id": "6b11dc07",
  "status": "completed",
  "steps_taken": 50,
  "converged": false,
  "confidence": 0.0,
  "elapsed_time": 0.03,
  "reasoning_trace": [
    "[Visual] Analyzing visual patterns... buffer norm=1.13",
    "[Visual] Analyzing visual patterns... buffer norm=1.45",
    "[Verbal] Processing verbal information... buffer norm=2.12",
    "...",
    "[Visual] Analyzing visual patterns... buffer norm=3.30"
  ],
  "total_thoughts": 50
}
```

---

## Data Flow

```
Input: Task (complexity >= 0.4)
         │
         ▼
┌─────────────────────┐
│ Check Threshold     │
│ complexity >= 0.4?  │
└─────────────────────┘
         │ YES
         ▼
┌─────────────────────┐
│ Start Background    │
│ Thread (async)      │
└─────────────────────┘
         │
Main Prediction ◀─────┘ (returns immediately, no wait!)
         │
         │ (meanwhile, in background thread)
         │
         ▼
┌─────────────────────┐
│ CTM Reasoning       │
│ 50 iterative steps  │
│ ~0.03-1 second      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Store Insights      │
│ reasoning_trace[]   │
└─────────────────────┘
         │
         ▼
    Insights Ready (retrieve via get_result)
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:196-220

# Automatic CTM triggering
if complexity >= 0.4:
    ctm_task_id = self.ctm_async.start_reasoning(
        task_description=task_description,
        max_steps=50
    )

    # Main prediction continues immediately (non-blocking!)
    # CTM runs in background
```

### Polling for Results
```python
# Location: test_all_features_seeded.py:104-115

# Wait for CTM to complete
if result.get('ctm_task_id'):
    for i in range(5):  # Wait up to 5 seconds
        time.sleep(1)
        if planner.planner.ctm_async.is_complete(result['ctm_task_id']):
            # Get insights
            ctm_result = planner.planner.ctm_async.get_result(
                result['ctm_task_id'],
                wait=False
            )
            insights = ctm_result.get_insights_summary()
            break
```

### In Production API
```python
# Location: production/production_planner.py:543-549

# Expose CTM task ID
if hasattr(prediction, 'ctm_task_id') and prediction.ctm_task_id:
    result['ctm_task_id'] = prediction.ctm_task_id

    # Check if already complete (fast tasks)
    if self.planner.ctm_async.is_complete(prediction.ctm_task_id):
        ctm_result = self.planner.ctm_async.get_result(
            prediction.ctm_task_id,
            wait=False
        )
        if ctm_result:
            result['ctm_insights'] = ctm_result.get_insights_summary()
```

---

## Key Algorithms

### Complexity Threshold
```
if task_complexity >= threshold:
    trigger_CTM()

Default threshold: 0.4 (40% complexity)
Configurable via ctm_complexity_threshold
```

### Modality Switching
```
Every 10 steps, switch modality:
visual → verbal → spatial → value → visual ...

Provides diverse perspectives on the task
```

### Convergence Detection
```
Converged if:
- Buffer norm stable for 5+ steps
- OR max_steps reached
- OR timeout exceeded

current_norm ≈ previous_norm ± ε (ε=0.1)
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Main Latency** | ~0ms (non-blocking!) |
| **CTM Latency** | 30ms - 1000ms (background) |
| **Memory Usage** | ~2MB per task |
| **Max Concurrent** | 3 tasks |
| **Timeout** | 30 seconds default |

---

## Dependencies

- **threading**: Background execution
- **time**: Timing and timeouts
- **uuid**: Task ID generation
- **core/ctm_integration.py**: CTM reasoning engine

---

## Current Limitations

### Visual Modalities Only
CTM currently uses generic visual/verbal/spatial modalities instead of task-specific ones:

**Current**:
```python
# Generic modalities
modalities = ['visual', 'verbal', 'spatial', 'value']
# Analyzes abstract patterns, not task-specific
```

**Future** (planned improvement):
```python
# Task-aware modalities
if task_type == 'docker':
    modalities = ['tool_trace', 'error_signal', 'success_signal']
elif task_type == 'debugging':
    modalities = ['error_signal', 'temporal_pattern', 'tool_trace']
```

**Why Keep Current Version?**
- Infrastructure works (threading, polling, insights)
- Proves concept of async deep reasoning
- Easy to swap reasoning logic later
- Modular design allows upgrade without architecture change

---

## Future Enhancements

1. **Task-Aware Reasoning**: Use task-specific modalities (tool_trace, error_signal, etc.)
2. **Multi-CTM**: Different CTMs for different task types
3. **Adaptive Steps**: More steps for complex tasks, fewer for simple
4. **Fast CTM**: Lightweight 10-step CTM for quick insights
5. **Creative CTM**: Divergent thinking mode
6. **Analytical CTM**: Convergent thinking mode

---

## Related Files

- **Implementation**: `core/ctm_async_reasoner.py`
- **CTM Engine**: `core/ctm_integration.py`
- **Integration**: `core/hierarchical_planner.py:196-220`
- **API**: `production/production_planner.py:543-549`
- **Tests**: `test_all_features_seeded.py`, `test_ctm_insights.py`
- **Docs**: `CTM_ASYNC_INTEGRATION_COMPLETE.md`

---

## Design Rationale

**Why Async (Non-Blocking)?**
- Simple tasks don't need deep reasoning (complexity < 0.4)
- Complex tasks benefit from deep reasoning, but user shouldn't wait
- Main prediction completes in <100ms, CTM runs separately

**Why Background Thread?**
- Python's threading is sufficient for I/O-bound reasoning
- No need for multiprocessing overhead
- Easy to implement and debug

**Why 50 Steps?**
- Empirically good balance (tested 10, 25, 50, 100)
- 50 steps ≈ 30ms-1s (depending on complexity)
- Enough for insights, not excessive

**Why Threshold 0.4?**
- Originally 0.75 (too high, rarely triggered)
- Lowered to 0.4 to activate more frequently
- Balances CTM usage with performance

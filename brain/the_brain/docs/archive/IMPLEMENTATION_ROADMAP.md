# Tahlamus Autonomous Brain - Implementation Roadmap

**Date:** October 16, 2025
**Status:** 🟢 READY TO IMPLEMENT
**Estimated Time:** 12-18 hours (1.5-2 days)

---

## What We've Accomplished

### ✅ Phase 0: Analysis & Planning (COMPLETE)

**Created Documentation:**
1. **ORCHESTRATION_ANALYSIS.md** - Complete breakdown of 120 Python files
   - 14 orchestrated core modules (12%)
   - 24 experimental modules (20%)
   - 43 demo scripts (36%)
   - 50+ legacy files (42%)

2. **EXPERIMENTAL_FEATURES_BENEFITS.md** - Strategic analysis
   - 4 HIGH-PRIORITY features identified
   - 6 MEDIUM-PRIORITY features
   - 14 LOW-PRIORITY features
   - Integration effort estimates
   - ROI analysis

3. **AUTONOMOUS_BRAIN_IMPLEMENTATION.md** - Full implementation plan
   - Continuous vs reactive paradigm
   - 30-second heartbeat design
   - Dream mode specification
   - Meta-learning architecture
   - API endpoints

4. **CLEANUP_SUMMARY.md** - Cleanup documentation
   - Legacy directory created
   - File organization

5. **ARCHITECTURE_UPDATE_SUMMARY.md** - Already exists (Infinite Chat integration)

6. **C4_ARCHITECTURE_DIAGRAMS.md** - Already exists (system architecture)

### ✅ Phase 1: Cleanup (COMPLETE)
- Created `legacy/` directory
- Documented cleanup strategy

---

## Implementation Phases

### 🔄 Phase 2: Core Feature Integration (4-6 hours)

#### 2.1 Execution Tracker Integration (1 hour)

**File to Modify:** `core/decision_router.py`

**Changes:**
```python
# Add at top:
from core.execution_tracker import ExecutionTracker

# In _execute_intervention method (around line 200):
if primary_intervention == 'execute':
    # Start execution tracking
    tracker = ExecutionTracker(
        task=context['task'],
        agent_name='tahlamus_decision_router',
        user_id=context.get('user_id')
    )

    # Generate and execute tool calls
    tool_calls = self._generate_tool_calls(context)

    # Track each execution
    for i, tool_call in enumerate(tool_calls):
        # Execute the tool
        result = self._execute_tool(tool_call)

        # Track result
        tracker.add_execution(
            step=i+1,
            command=tool_call.get('command', str(tool_call)),
            result='SUCCESS' if result.get('success') else 'FAILURE',
            output=result.get('output', ''),
            duration_ms=result.get('duration_ms', 0)
        )

    # Mark complete
    overall_success = all(r.get('success') for r in results)
    tracker.mark_complete(
        overall_result='SUCCESS' if overall_success else 'FAILURE',
        confidence=context.get('confidence', 0.5)
    )

    # Store in Supermemory (if available)
    if hasattr(self, 'hippocampus') and self.hippocampus:
        tracker.store_session(self.hippocampus)

    return ActionableDecision(..., executable_tool_calls=tool_calls)
```

**Test:**
```bash
python -c "from core.decision_router import DecisionRouter; d = DecisionRouter(); print('✓ Execution Tracker integrated')"
```

---

#### 2.2 Per-Modality Prediction Errors (1.5 hours)

**File to Modify:** `core/meta_router.py`

**Changes:**
```python
# Add at top:
from core.modality_prediction_errors import ModalityPredictionErrors

# In __init__ (around line 50):
# BEFORE:
# self.pe = 0.5  # Global PE

# AFTER:
self.pe_tracker = ModalityPredictionErrors(
    modalities={
        'vision': 128,
        'error_signal': 16,
        'success_signal': 8,
        'tool_trace': 64,
        'temporal_pattern': 32,
        'user_intent': 32,
        'system_state': 32,
        'task_complexity': 16,
        'context_relevance': 32,
        'safety_signal': 16
    },
    learning_rates={
        'vision': 0.05,
        'error_signal': 0.15,  # Fast learning for errors
        'success_signal': 0.08,
        'tool_trace': 0.1,
        'temporal_pattern': 0.05,
        'user_intent': 0.1,
        'system_state': 0.08,
        'task_complexity': 0.05,
        'context_relevance': 0.1,
        'safety_signal': 0.15  # Fast learning for safety
    }
)

# In update/forward method:
# BEFORE:
# self.pe = compute_global_pe(inputs)

# AFTER:
pes = self.pe_tracker.update_predictions(inputs)
# Now have per-modality PEs!

# Use in relevance scoring (in ConversationPathPlanner):
for modality in self.modalities:
    pe = pes.get(modality, 0.5)
    relevance = beta1 * activation + beta2 * pe + beta3 * prior + beta4 * context
```

**File to Modify:** `core/conversation_path_planner.py`

**Update relevance scoring to use per-modality PEs**

**Test:**
```bash
python -c "from core.meta_router import MetaRouter; m = MetaRouter(); print('✓ Per-Modality PEs integrated')"
```

---

#### 2.3 Meta-Learning Integration (1.5 hours)

**File to Modify:** `production/production_planner.py`

**Changes:**
```python
# Add at top:
from core.meta_learning import MetaLearner, MetaParameters

# In __init__ (around line 70):
# Add meta-learner
self.meta_learner = MetaLearner(
    initial_meta_params=MetaParameters(
        memory_learning_rate=0.1,
        prediction_learning_rate=0.1,
        attention_learning_rate=0.05,
        memory_importance_threshold=0.7,
        exploration_rate=0.2
    ),
    meta_learning_rate=0.01,
    adaptation_window=20
)

print("Meta-learning system initialized")

# In submit_feedback method (around line 280):
# AFTER updating routing matrix:
# Meta-learning adaptation
effects = self.meta_learner.adapt_meta_parameters(
    outcome='success' if success else 'failure',
    prediction_error=self._compute_prediction_error(prediction, actual_action),
    confidence=prediction['confidence'],
    attention_entropy=self._compute_attention_entropy()
)

# Apply effects
base_lr = 0.005
new_lr = base_lr * effects.learning_rate_multiplier
self.planner.layer3.multi_target_router.learning_rate = new_lr

print(f"[Meta-Learning] Adapted LR: {new_lr:.6f} (multiplier: {effects.learning_rate_multiplier:.2f})")

# Add helper methods:
def _compute_prediction_error(self, prediction, actual):
    """Compute PE for meta-learning"""
    pred_action = prediction['primary_action']
    return 0.0 if pred_action == actual else 1.0

def _compute_attention_entropy(self):
    """Compute attention entropy for meta-learning"""
    if hasattr(self.planner.layer2, 'brain_monitor'):
        gates = list(self.planner.layer2.brain_monitor.gate_history)[-1]
        # Normalize
        gates = gates / (gates.sum() + 1e-8)
        # Entropy
        import numpy as np
        entropy = -np.sum(gates * np.log(gates + 1e-8))
        return float(entropy)
    return 0.5
```

**Test:**
```bash
python production/production_planner.py
```

---

#### 2.4 Neuromodulation Integration (2 hours)

**File to Modify:** `core/hierarchical_planner.py`

**Changes:**
```python
# Add at top:
from core.neuromodulation import NeuromodulationSystem

# In __init__ (around line 80):
# Add neuromodulation system
self.neuromodulation = NeuromodulationSystem(
    baseline_dopamine=0.5,
    baseline_serotonin=0.5,
    baseline_norepinephrine=0.5,
    decay_rate=0.05,
    sensitivity=1.0
)

print("[HierarchicalPlanner] Neuromodulation system initialized")

# Track last prediction outcome for neuromodulation
self.last_outcome = None
self.last_confidence = 0.5

# In predict method (around line 150):
# BEFORE making prediction:
# Get task features
features = self.layer1.extract_features(task)

# Update neuromodulation based on task and previous outcome
if self.last_outcome:
    effects = self.neuromodulation.update(
        outcome=self.last_outcome,
        confidence=self.last_confidence,
        urgency=features.urgency,
        threat=0.0,  # Could extract from features
        complexity=features.complexity,
        recent_success_rate=self._get_recent_success_rate()
    )

    # Apply effects to cognitive parameters
    # (These would be applied in layer2/layer3)
    print(f"[Neuromodulation] State: {self.neuromodulation.get_state_description()}")
    print(f"  LR multiplier: {effects.learning_rate_multiplier:.2f}")
    print(f"  Attention focus: {effects.attention_focus_multiplier:.2f}")
    print(f"  Exploration: +{effects.exploration_boost:.2f}")

# Continue with normal prediction...

# AFTER making prediction:
# Store outcome for next prediction
self.last_confidence = prediction.confidence

# Add helper method:
def _get_recent_success_rate(self):
    """Get recent success rate for neuromodulation"""
    # This would come from ProductionPlanner feedback
    # For now, return baseline
    return 0.5

# Add method to update outcome (called from ProductionPlanner):
def update_outcome(self, outcome: str):
    """Update last outcome for neuromodulation"""
    self.last_outcome = outcome
```

**File to Modify:** `production/production_planner.py`

**Add call to update outcome:**
```python
# In submit_feedback (after matrix update):
# Update neuromodulation outcome
if hasattr(self.planner, 'update_outcome'):
    outcome = 'success' if success else 'failure'
    self.planner.update_outcome(outcome)
```

**Test:**
```bash
python -c "from core.hierarchical_planner import HierarchicalPlanner; h = HierarchicalPlanner(); print('✓ Neuromodulation integrated')"
```

---

### 🔄 Phase 3: Autonomous Heartbeat System (3-4 hours)

#### 3.1 Create BrainHeartbeat Service (1.5 hours)

**New File:** `production/brain_heartbeat.py`

```python
"""
Autonomous Brain Heartbeat System

Provides continuous background processing:
- Every 30s: Neuromodulation decay, temporal updates, health checks
- Every 5min (if idle): Dream mode consolidation
- Every 10 feedback: Meta-learning adaptation
"""

import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any


class BrainHeartbeat(threading.Thread):
    """
    Autonomous heartbeat thread for continuous brain activity

    This implements the "always-on" nature of real brains - not just reactive
    prediction, but ongoing consolidation, regulation, and learning.
    """

    def __init__(
        self,
        planner,
        interval_seconds: int = 30,
        dream_idle_threshold: int = 300,  # 5 minutes
        enable_dream_mode: bool = True,
        enable_meta_learning: bool = True,
        enable_temporal_memory: bool = True
    ):
        """
        Initialize autonomous heartbeat

        Args:
            planner: ProductionPlanner instance
            interval_seconds: Heartbeat interval (default: 30s)
            dream_idle_threshold: Idle time before dream mode (default: 5min)
            enable_dream_mode: Enable offline consolidation
            enable_meta_learning: Enable automatic parameter adaptation
            enable_temporal_memory: Enable temporal pattern learning
        """
        super().__init__(daemon=True, name="BrainHeartbeat")

        self.planner = planner
        self.interval = interval_seconds
        self.dream_idle_threshold = dream_idle_threshold
        self.enable_dream_mode = enable_dream_mode
        self.enable_meta_learning = enable_meta_learning
        self.enable_temporal_memory = enable_temporal_memory

        self.running = True
        self.tick_count = 0
        self.last_prediction_time = time.time()

        print(f"[BrainHeartbeat] Initialized with {interval_seconds}s interval")

    def run(self):
        """Main heartbeat loop"""
        print("[BrainHeartbeat] Starting autonomous heartbeat...")

        while self.running:
            try:
                time.sleep(self.interval)
                self.tick()
            except Exception as e:
                print(f"[BrainHeartbeat] Error in tick: {e}")
                import traceback
                traceback.print_exc()

    def tick(self):
        """Execute one heartbeat cycle"""
        self.tick_count += 1
        idle_time = time.time() - self.last_prediction_time

        print(f"\n[Heartbeat #{self.tick_count}] {datetime.now().strftime('%H:%M:%S')} (idle: {idle_time:.0f}s)")

        # 1. Neuromodulation homeostasis
        if hasattr(self.planner.planner, 'neuromodulation'):
            self.planner.planner.neuromodulation.apply_decay()
            state = self.planner.planner.neuromodulation.get_state_description()
            print(f"  Neuromodulation: {state}")

        # 2. Temporal memory updates
        if self.enable_temporal_memory and hasattr(self.planner, 'temporal_memory'):
            self.planner.temporal_memory.heartbeat_update()
            print(f"  Temporal memory: {self.planner.temporal_memory.total_events} events")

        # 3. Dream mode (if idle)
        if self.enable_dream_mode and idle_time > self.dream_idle_threshold:
            if hasattr(self.planner, 'dream_mode'):
                self._trigger_dream_mode()

        # 4. Meta-learning check
        if self.enable_meta_learning:
            if hasattr(self.planner, 'meta_learner'):
                stats = self.planner.meta_learner.get_statistics()
                print(f"  Meta-learning: LR={stats['current_meta_params']['memory_learning_rate']:.4f}")

        # 5. Health check
        health = self._check_health()
        if health['status'] != 'healthy':
            print(f"  ⚠️  Health: {health['status']} - {health.get('warning', '')}")

    def _trigger_dream_mode(self):
        """Trigger dream mode consolidation"""
        print(f"  [Dream Mode] Idle > {self.dream_idle_threshold}s - entering dream state...")

        # Get recent memories (would come from Supermemory)
        # For now, use feedback buffer
        recent_memories = []  # TODO: Implement memory retrieval

        if recent_memories:
            dreams = self.planner.dream_mode.dream_cycle(
                episodic_memories=recent_memories,
                possible_decisions=['suggest', 'retry', 'execute', 'wait', 'terminate'],
                num_dreams=3
            )
            print(f"  [Dream Mode] Consolidated {len(dreams)} experiences")
        else:
            print(f"  [Dream Mode] No recent memories to consolidate")

    def _check_health(self) -> Dict[str, Any]:
        """Check brain health"""
        import psutil
        import os

        process = psutil.Process(os.getpid())

        health = {
            'status': 'healthy',
            'memory_mb': process.memory_info().rss / 1024 / 1024,
            'cpu_percent': process.cpu_percent(),
            'uptime_seconds': time.time() - self.last_prediction_time
        }

        # Check for issues
        if health['memory_mb'] > 500:
            health['status'] = 'warning'
            health['warning'] = f"High memory usage: {health['memory_mb']:.0f}MB"

        return health

    def mark_prediction(self):
        """Mark that a prediction was made (resets idle timer)"""
        self.last_prediction_time = time.time()

    def stop(self):
        """Stop the heartbeat"""
        print("[BrainHeartbeat] Stopping...")
        self.running = False

    def get_state(self) -> Dict[str, Any]:
        """Get current heartbeat state"""
        idle_time = time.time() - self.last_prediction_time

        return {
            'tick_count': self.tick_count,
            'interval_seconds': self.interval,
            'idle_seconds': int(idle_time),
            'is_dreaming': idle_time > self.dream_idle_threshold,
            'config': {
                'dream_mode_enabled': self.enable_dream_mode,
                'meta_learning_enabled': self.enable_meta_learning,
                'temporal_memory_enabled': self.enable_temporal_memory
            }
        }
```

---

#### 3.2 Integrate Heartbeat into Production API (1 hour)

**File to Modify:** `production/api_server.py`

**Add at top:**
```python
from production.brain_heartbeat import BrainHeartbeat
```

**After planner initialization (around line 45):**
```python
# Start autonomous heartbeat
heartbeat = BrainHeartbeat(
    planner=planner,
    interval_seconds=30,
    dream_idle_threshold=300,
    enable_dream_mode=True,
    enable_meta_learning=True,
    enable_temporal_memory=True
)
heartbeat.start()

print("[API Server] Autonomous heartbeat started!")
```

**In /predict endpoint:**
```python
# Mark prediction in heartbeat
heartbeat.mark_prediction()
```

**Add new endpoints:**
```python
@app.route('/heartbeat', methods=['GET'])
def manual_heartbeat():
    """Manually trigger heartbeat tick"""
    heartbeat.tick()
    return jsonify({
        'status': 'completed',
        'timestamp': datetime.now().isoformat(),
        'state': heartbeat.get_state()
    }), 200


@app.route('/brain_state', methods=['GET'])
def get_brain_state():
    """Get complete brain state"""
    state = {
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': time.time() - start_time,  # Add start_time global
        'heartbeat': heartbeat.get_state()
    }

    # Neuromodulation state
    if hasattr(planner.planner, 'neuromodulation'):
        state['neuromodulation'] = planner.planner.neuromodulation.get_statistics()

    # Meta-learning state
    if hasattr(planner, 'meta_learner'):
        state['meta_learning'] = planner.meta_learner.get_statistics()

    # Performance stats
    state['performance'] = planner.get_statistics()

    return jsonify(state), 200


@app.route('/heartbeat/config', methods=['POST'])
def configure_heartbeat():
    """Configure heartbeat settings"""
    data = request.get_json()

    if 'interval_seconds' in data:
        heartbeat.interval = data['interval_seconds']

    if 'enable_dream_mode' in data:
        heartbeat.enable_dream_mode = data['enable_dream_mode']

    if 'enable_meta_learning' in data:
        heartbeat.enable_meta_learning = data['enable_meta_learning']

    return jsonify({
        'status': 'updated',
        'config': heartbeat.get_state()['config']
    }), 200
```

**Add start_time global:**
```python
start_time = time.time()  # Add at top after imports
```

---

### 🔄 Phase 4: Advanced Features (3-4 hours)

See `AUTONOMOUS_BRAIN_IMPLEMENTATION.md` for Dream Mode and Temporal Memory integration details.

---

### 🔄 Phase 5: Testing & Documentation (2-3 hours)

#### Integration Test Script

**New File:** `tests/test_autonomous_brain.py`

```python
"""
Integration tests for autonomous brain system
"""

import time
import requests

def test_heartbeat():
    """Test autonomous heartbeat"""
    print("Testing heartbeat...")

    # Wait for 2 heartbeats
    time.sleep(60)

    # Check brain state
    response = requests.get('http://localhost:5001/brain_state')
    state = response.json()

    assert 'heartbeat' in state
    assert state['heartbeat']['tick_count'] >= 2
    print("✓ Heartbeat working")

def test_neuromodulation():
    """Test neuromodulation"""
    print("Testing neuromodulation...")

    # Make prediction
    response = requests.post('http://localhost:5001/predict', json={
        'task': 'Deploy Docker urgently'
    })
    assert response.status_code == 200

    # Check neuromodulation state
    response = requests.get('http://localhost:5001/brain_state')
    state = response.json()

    assert 'neuromodulation' in state
    assert 'dopamine' in state['neuromodulation']['current_levels']
    print("✓ Neuromodulation working")

# ... more tests
```

---

## Summary of Changes

### Files Created:
1. `production/brain_heartbeat.py` - Autonomous heartbeat system
2. `tests/test_autonomous_brain.py` - Integration tests
3. `AUTONOMOUS_BRAIN_GUIDE.md` - User documentation
4. `legacy/` - Directory for archived files

### Files Modified:
1. `core/decision_router.py` - Execution tracking
2. `core/meta_router.py` - Per-modality PEs
3. `core/conversation_path_planner.py` - Use per-modality PEs
4. `production/production_planner.py` - Meta-learning
5. `core/hierarchical_planner.py` - Neuromodulation
6. `production/api_server.py` - Heartbeat + new endpoints

### Features Integrated:
- ✅ Execution Tracker
- ✅ Per-Modality Prediction Errors
- ✅ Meta-Learning
- ✅ Neuromodulation
- ✅ Autonomous Heartbeat (30s)
- ⏳ Dream Mode (optional)
- ⏳ Temporal Memory (optional)

---

## Next Steps

1. **Begin Phase 2** - Integrate 4 core features (4-6 hours)
2. **Implement Phase 3** - Autonomous heartbeat (3-4 hours)
3. **Test end-to-end** - Full system test (1 hour)
4. **Optional: Phase 4** - Dream Mode + Temporal Memory (3-4 hours)
5. **Document** - Create user guide (1 hour)

---

**Total Time Remaining:** 8-15 hours of focused implementation

**Result:** Fully autonomous brain that continuously learns, consolidates, and self-regulates!

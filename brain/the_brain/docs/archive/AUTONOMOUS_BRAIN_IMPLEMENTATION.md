# Autonomous Brain Implementation Plan

**Date:** October 16, 2025
**Goal:** Transform Tahlamus from reactive to autonomous brain architecture

---

## Philosophy: Continuous vs Reactive

### ❌ Old Paradigm (Reactive Brain)
```python
# Prediction on demand only
request → predict() → response

# No autonomous activity
# No offline consolidation
# No homeostatic regulation
```

### ✅ New Paradigm (Autonomous Brain)
```python
# Continuous background processes
while True:
    time.sleep(30)  # Every 30 seconds

    # Homeostasis
    neuromodulation.decay_to_baseline()

    # Temporal learning
    temporal_memory.update_patterns()

    # Dream mode (if idle)
    if idle_time > 300:  # 5 minutes
        dream_mode.consolidate_experiences()

    # Meta-learning
    meta_learner.adapt_parameters()
```

**Real brains are ALWAYS active** - even during "rest", they:
- Consolidate memories (hippocampal replay)
- Extract patterns
- Regulate neurotransmitters
- Update temporal models
- Self-monitor health

---

## Implementation Phases

### Phase 1: Cleanup (30 min)
- [x] Create `legacy/` directory
- [x] Move old ATM-R files to legacy
- [x] Document cleanup

### Phase 2: Core Feature Integration (4-6 hours)

**2.1 Execution Tracker** (1 hour)
- Integrate into `DecisionRouter`
- Track all 'execute' interventions
- Auto-store in Supermemory

**2.2 Per-Modality PEs** (1.5 hours)
- Replace global PE in `MetaRouter`
- Update `ConversationPathPlanner` relevance scoring
- Test with 10 modalities

**2.3 Meta-Learning** (1.5 hours)
- Add to `ProductionPlanner`
- Performance-based learning rate adaptation
- Oscillation detection

**2.4 Neuromodulation** (2 hours)
- Add to `HierarchicalPlanner`
- Dopamine/Serotonin/Norepinephrine systems
- Cognitive effect computation

### Phase 3: Autonomous Heartbeat (3-4 hours)

**3.1 BrainHeartbeat Thread** (1 hour)
```python
class BrainHeartbeat(threading.Thread):
    def run(self):
        while self.running:
            time.sleep(self.interval)  # 30 seconds
            self.tick()
```

**3.2 Heartbeat Tick Functions** (2 hours)
- Neuromodulation decay
- Temporal pattern updates
- Dream mode triggers
- Meta-learning checks
- Health monitoring

**3.3 API Endpoints** (1 hour)
- `GET /brain_state` - Complete cognitive state
- `GET /heartbeat` - Manual trigger
- `POST /heartbeat/config` - Configure intervals

### Phase 4: Advanced Features (3-4 hours)

**4.1 Dream Mode Integration** (1.5 hours)
- Offline consolidation
- Experience replay
- Pattern extraction

**4.2 Temporal Memory Integration** (1.5 hours)
- Sequence learning
- Daily/weekly patterns
- Next-event prediction

**4.3 Monitoring Dashboard** (1 hour)
- Real-time brain state visualization
- Neuromodulation levels
- Dream activity log

### Phase 5: Testing & Documentation (2-3 hours)

**5.1 Integration Tests** (1.5 hours)
- Test all 4 core features
- Test heartbeat autonomy
- Test dream mode

**5.2 Documentation** (1.5 hours)
- `AUTONOMOUS_BRAIN_GUIDE.md`
- Update `CLAUDE.md`
- API documentation

---

## Total Estimated Time: 12-18 hours (1.5-2 days)

---

## Detailed Design: Autonomous Brain

### 1. Neuromodulation System

**Purpose:** Emotional/cognitive state that modulates learning and decision-making

```python
class AutonomousBrain:
    def __init__(self):
        self.neuromodulation = NeuromodulationSystem(
            baseline_dopamine=0.5,      # Neutral motivation
            baseline_serotonin=0.5,     # Neutral mood
            baseline_norepinephrine=0.5, # Neutral arousal
            decay_rate=0.05             # 5% decay per heartbeat
        )

    def heartbeat_tick(self):
        # Homeostatic decay (brain calms down naturally)
        self.neuromodulation.apply_decay()

        # Effects on cognition
        effects = self.neuromodulation.compute_effects()
        # → learning_rate_multiplier
        # → exploration_boost
        # → attention_focus_multiplier
        # → confidence_threshold_delta
        # → response_urgency
```

**Heartbeat Behavior:**
```
t=0:   Dopamine=0.8 (recent success!)
t=30s: Dopamine=0.76 (decay)
t=60s: Dopamine=0.72 (decay)
t=90s: Dopamine=0.68 (decay)
...
t=5min: Dopamine=0.5 (baseline restored)
```

---

### 2. Temporal Memory System

**Purpose:** Learn when things happen and what follows what

```python
class AutonomousBrain:
    def __init__(self):
        self.temporal_memory = TemporalMemory(
            decay_rate=0.1,          # Memory decay per day
            sequence_window=5,       # Max sequence length
            temporal_horizon=7       # Days of active context
        )

    def heartbeat_tick(self):
        # Update temporal patterns
        self.temporal_memory.update_daily_patterns()
        self.temporal_memory.update_weekly_patterns()

        # Predict next likely task
        if self.last_task:
            predictions = self.temporal_memory.predict_next_event(
                self.last_task,
                top_k=3
            )
```

**What It Learns:**
```
Sequences:
- "docker" → "push" → "deploy" (85% confidence)
- "git clone" → "npm install" → "npm run" (92% confidence)

Temporal Patterns:
- Monday 9am: "standup" tasks (72% probability)
- Friday 5pm: "deploy" tasks (45% probability)
- After "error": "debug" task (88% probability)
```

---

### 3. Dream Mode (Offline Consolidation)

**Purpose:** Consolidate experiences, extract patterns, counterfactual learning

```python
class AutonomousBrain:
    def __init__(self):
        self.dream_mode = DreamMode(
            replay_rate=0.3,
            counterfactual_rate=0.2,
            max_dreams_per_cycle=5
        )
        self.idle_time = 0

    def heartbeat_tick(self):
        self.idle_time += 30  # seconds

        # Enter dream state if idle > 5 minutes
        if self.idle_time > 300:
            print("[Brain] Entering dream state (consolidating experiences)...")

            dreams = self.dream_mode.dream_cycle(
                episodic_memories=self.get_recent_memories(),
                possible_decisions=['suggest', 'retry', 'execute', 'wait', 'terminate'],
                num_dreams=5
            )

            # Dreams include:
            # - Experience replay (strengthen important memories)
            # - Counterfactuals ("what if I had chosen retry instead?")
            # - Pattern extraction (discover task→decision patterns)
```

**Dream Example:**
```
[Dream 1] REPLAY: "Deploy Docker urgently" → "execute" → SUCCESS
  → Strengthened memory by +0.05

[Dream 2] COUNTERFACTUAL: "Fix bug quickly" → "suggest" → FAILURE
  → What if "execute"? → Hypothetical SUCCESS
  → Learned: For urgent bugs, "execute" > "suggest"

[Dream 3] PATTERN EXTRACTION:
  → docker tasks + high urgency → "execute" (success rate: 85%)
  → Discovered new pattern!
```

---

### 4. Meta-Learning (Learning How to Learn)

**Purpose:** Adapt learning parameters based on performance

```python
class AutonomousBrain:
    def __init__(self):
        self.meta_learner = MetaLearner(
            meta_learning_rate=0.01,
            adaptation_window=20
        )

    def submit_feedback(self, feedback):
        # Normal learning
        self.update_routing_matrix(feedback)

        # Meta-learning
        effects = self.meta_learner.adapt_meta_parameters(
            outcome=feedback.outcome,
            prediction_error=feedback.pe,
            confidence=feedback.confidence
        )

        # Apply adaptations
        self.learning_rate *= effects.learning_rate_multiplier
        self.exploration_rate += effects.exploration_boost

    def heartbeat_tick(self):
        # Periodic meta-learning check
        if self.total_feedback % 10 == 0:
            trend = self.meta_learner.analyze_trends()
            # "oscillating" → reduce learning rate
            # "improving" → maintain current rate
            # "degrading" → increase exploration
```

**Meta-Learning Behavior:**
```
Feedback 1-10: Success rate 40%
  → Meta-learner: "Low performance, increase exploration"
  → learning_rate: 0.005 → 0.008
  → exploration_rate: 0.2 → 0.3

Feedback 11-20: Success rate 75%
  → Meta-learner: "Improving, maintain settings"
  → learning_rate: 0.008 (maintain)

Feedback 21-30: Success rate oscillating (80%, 50%, 85%, 45%...)
  → Meta-learner: "Oscillation detected, stabilize"
  → learning_rate: 0.008 → 0.005
  → exploration_rate: 0.3 → 0.2
```

---

## API Endpoints

### GET /brain_state (Complete Cognitive State)

```json
{
  "timestamp": "2025-10-16T14:30:00",
  "uptime_seconds": 3600,
  "state": "active",

  "neuromodulation": {
    "dopamine": 0.68,
    "serotonin": 0.72,
    "norepinephrine": 0.55,
    "state_description": "MOTIVATED | PATIENT | CALM",
    "effects": {
      "learning_rate_multiplier": 1.18,
      "exploration_boost": 0.08,
      "attention_focus_multiplier": 1.05,
      "confidence_threshold_delta": 0.04,
      "response_urgency": 0.55
    }
  },

  "meta_learning": {
    "current_learning_rate": 0.0062,
    "base_learning_rate": 0.005,
    "exploration_rate": 0.24,
    "recent_success_rate": 0.78,
    "performance_trend": "improving",
    "is_oscillating": false
  },

  "dream_state": {
    "is_dreaming": false,
    "idle_time_seconds": 127,
    "total_dreams": 15,
    "recent_patterns_discovered": 3,
    "last_dream": "2025-10-16T14:15:00"
  },

  "temporal_memory": {
    "total_events": 245,
    "sequences_learned": 38,
    "time_of_day": "afternoon",
    "day_of_week": "wednesday",
    "predicted_next_tasks": [
      {"task_type": "docker", "probability": 0.35},
      {"task_type": "git", "probability": 0.28},
      {"task_type": "debug", "probability": 0.18}
    ]
  },

  "performance": {
    "total_predictions": 432,
    "total_feedback": 387,
    "avg_confidence": 0.76,
    "success_rate": 0.82,
    "avg_prediction_latency_ms": 245,
    "predictions_per_minute": 2.1
  },

  "health": {
    "memory_usage_mb": 145,
    "cpu_usage_percent": 3.2,
    "last_heartbeat": "2025-10-16T14:29:30",
    "heartbeat_interval_seconds": 30,
    "status": "healthy"
  }
}
```

### POST /heartbeat (Manual Trigger)

```json
{
  "action": "tick",
  "force_dream": false
}

Response:
{
  "status": "completed",
  "timestamp": "2025-10-16T14:30:00",
  "actions_taken": [
    "neuromodulation_decay",
    "temporal_pattern_update",
    "health_check"
  ],
  "brain_state": {...}
}
```

### POST /heartbeat/config (Configure Heartbeat)

```json
{
  "interval_seconds": 60,
  "enable_dream_mode": true,
  "dream_idle_threshold_seconds": 300,
  "enable_auto_meta_learning": true
}

Response:
{
  "status": "updated",
  "config": {...}
}
```

---

## Monitoring Dashboard Update

### New Real-Time Displays

**1. Neuromodulation Panel**
```
Neuromodulation State: MOTIVATED | PATIENT | CALM

Dopamine    [████████████░░░░░░] 0.68 (Reward/Motivation)
Serotonin   [██████████████░░░░] 0.72 (Mood/Patience)
Norepineph. [███████████░░░░░░░] 0.55 (Arousal/Urgency)

Effects on Cognition:
  Learning Rate: +18%
  Exploration: +8%
  Attention Focus: +5%
```

**2. Autonomous Activity Log**
```
[14:30:00] Heartbeat tick (uptime: 1h 0m)
[14:29:30] Heartbeat tick (uptime: 59m 30s)
[14:29:00] Heartbeat tick (uptime: 59m 0s)
[14:25:00] Dream mode: Consolidated 3 experiences, discovered 1 pattern
[14:24:30] Entered dream state (idle: 5m 12s)
```

**3. Dream Activity Panel**
```
Recent Dreams (last 10):

[Dream 1] REPLAY: "docker build" → "execute" → SUCCESS
  Strengthened memory: +0.05

[Dream 2] COUNTERFACTUAL: "urgent bug" → "suggest" → FAILURE
  Alternative "execute": hypothetical SUCCESS
  Pattern learned!

[Dream 3] PATTERN: git + morning → "execute" (92% success)
```

**4. Temporal Patterns**
```
Time-of-Day Patterns:
  Morning:   docker (42%), git (35%), debug (15%)
  Afternoon: deploy (38%), test (28%), docker (22%)
  Evening:   commit (45%), push (32%), cleanup (18%)

Sequential Patterns:
  "docker build" → "docker push" (85%)
  "git clone" → "npm install" (92%)
  "error" → "debug" (88%)
```

---

## File Structure After Implementation

```
production/
├── api_server.py                  # Enhanced with heartbeat
├── production_planner.py          # Enhanced with 4 features
├── brain_heartbeat.py            # NEW: Autonomous heartbeat thread
└── trained_matrices/

core/
├── hierarchical_planner.py        # Enhanced with neuromodulation
├── decision_router.py             # Enhanced with execution tracker
├── meta_router.py                 # Enhanced with per-modality PE
├── execution_tracker.py           # USED
├── modality_prediction_errors.py  # USED
├── meta_learning.py               # USED
├── neuromodulation.py             # USED
├── dream_mode.py                  # USED
├── temporal_memory.py             # USED
└── ...

legacy/                            # NEW: Archived files
├── thalamo_pc_live.py
├── thalamo_pc_adaptive.py
├── atmr_torch.py
├── atmr_jax.py
└── ...
```

---

## Success Metrics

### Autonomous Operation
- ✅ Heartbeat runs continuously every 30s
- ✅ Dream mode activates after 5min idle
- ✅ Neuromodulation decays to baseline
- ✅ Temporal patterns updated continuously

### Feature Integration
- ✅ Execution tracking: 100% of 'execute' interventions
- ✅ Per-modality PE: 10 separate PEs tracked
- ✅ Meta-learning: Learning rate adapts every 10 feedback
- ✅ Neuromodulation: Cognitive effects applied

### Performance
- ✅ Heartbeat overhead: <1% CPU
- ✅ Prediction latency increase: <5%
- ✅ Memory usage: <200MB total
- ✅ No crashes after 24h continuous operation

---

## Next Steps

**Phase 1: Start Implementation** (Now)
1. Create legacy/ directory
2. Document cleanup
3. Begin core feature integration

**Phase 2: Core Features** (Hours 1-6)
1. Execution Tracker
2. Per-Modality PEs
3. Meta-Learning
4. Neuromodulation

**Phase 3: Autonomous System** (Hours 7-12)
1. BrainHeartbeat thread
2. Dream Mode integration
3. Temporal Memory integration
4. API endpoints

**Phase 4: Testing & Docs** (Hours 13-18)
1. Integration tests
2. 24h stress test
3. Documentation
4. Dashboard updates

---

**Status:** 🟢 READY TO START

**Est. Completion:** 1.5-2 days (12-18 hours of focused work)

**Result:** Fully autonomous brain that continuously learns, consolidates, and self-regulates - just like a real brain!

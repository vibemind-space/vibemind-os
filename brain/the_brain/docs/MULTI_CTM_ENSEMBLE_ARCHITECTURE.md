# Multi-CTM Ensemble Architecture

**Created**: October 22, 2025
**Branch**: `feature/multi-ctm-ensemble`
**Status**: 🚧 In Development

## Executive Summary

The Multi-CTM Ensemble extends Tahlamus with **specialized Conscious Turing Machines (CTMs)** for different cognitive domains. Instead of a single general-purpose CTM, we deploy **four specialized CTMs** trained on domain-specific tasks:

1. **SpatialCTM**: Architecture, infrastructure, topology (current Klotski brain)
2. **LogicCTM**: Verification, constraints, type checking
3. **TemporalCTM**: Time-series, patterns, scheduling
4. **ValueCTM**: Decisions, trade-offs, prioritization

This mirrors biological brain specialization: different cortical regions excel at different cognitive tasks.

---

## Problem Statement

### Current Limitation: Single CTM with Spatial Bias

The existing Klotski CTM (core/klotski_ctm.py) shows strong **spatial reasoning bias**:
- **SOM (spatial)**: 96% activation
- **VIS (visual)**: 37% activation
- **DMN (consciousness)**: 34% activation
- **LAN (language/logic)**: 0% activation (dropped from 93%)

**Why this happened**: The Klotski neurosymbolic brain was trained on spatial puzzles, learning that "problems are spatial arrangement challenges."

**The limitation**: Non-spatial tasks (logic, temporal patterns, value judgments) get **forced into spatial representation**, losing their inherent structure.

### Evidence from Training

From KlotskiPuzzle training logs (ROUTED_BRAIN_FINAL_SUMMARY.md):

```
Training Phase Transitions:
- Epoch 0:  LAN=93%, SOM=1%  (symbolic reasoning dominant)
- Epoch 10: LAN=45%, SOM=35% (transitioning)
- Epoch 20: LAN=0%,  SOM=96% (spatial reasoning dominant)
```

**Key insight**: The brain's module routing is **task-dependent**. Different training creates different specialists.

---

## Proposed Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TAHLAMUS COGNITIVE SYSTEM                    │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  SYSTEM 1: Fast Heuristic Routing (<100ms)                     │ │
│  │  HierarchicalPlanner → TaskFeatureRouter                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                    │                                  │
│                                    │ complexity >= 0.75               │
│                                    ▼                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  SYSTEM 2: Multi-CTM Ensemble Router                           │ │
│  │                                                                 │ │
│  │  Task Analysis → Domain Classification → CTM Selection         │ │
│  │                                                                 │ │
│  │    ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │ │
│  │    │  Spatial     │   │   Logic      │   │  Temporal    │    │ │
│  │    │  Features    │   │  Features    │   │  Features    │    │ │
│  │    └──────┬───────┘   └──────┬───────┘   └──────┬───────┘    │ │
│  │           │                   │                   │             │ │
│  │           ▼                   ▼                   ▼             │ │
│  │    ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │ │
│  │    │ SpatialCTM   │   │  LogicCTM    │   │ TemporalCTM  │    │ │
│  │    │ (Klotski)    │   │ (untrained)  │   │ (untrained)  │    │ │
│  │    │              │   │              │   │              │    │ │
│  │    │ 3.7M params  │   │ 3.7M params  │   │ 3.7M params  │    │ │
│  │    │ SOM: 96%     │   │ LAN: TBD     │   │ AUD: TBD     │    │ │
│  │    └──────────────┘   └──────────────┘   └──────────────┘    │ │
│  │                                                                 │ │
│  │    ┌──────────────┐                                            │ │
│  │    │  ValueCTM    │                                            │ │
│  │    │ (untrained)  │                                            │ │
│  │    │              │                                            │ │
│  │    │ 3.7M params  │                                            │ │
│  │    │ OFC: TBD     │                                            │ │
│  │    └──────────────┘                                            │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                    │                                  │
│                                    ▼                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  DREAM MODE: Parallel CTM Training (Idle Time)                 │ │
│  │                                                                 │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐               │ │
│  │  │ Logic Task │  │Temporal    │  │ Value Task │               │ │
│  │  │ Replay     │  │Task Replay │  │ Replay     │               │ │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘               │ │
│  │        │               │               │                        │ │
│  │        ▼               ▼               ▼                        │ │
│  │  Train LogicCTM  Train TemporalCTM  Train ValueCTM             │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### 1. **MultiCTMEnsemble** (core/multi_ctm_ensemble.py) - NEW
- Routes tasks to appropriate specialized CTM
- Manages 4 CTM instances (SpatialCTM, LogicCTM, TemporalCTM, ValueCTM)
- Handles fallback to System 1 if CTM unavailable
- Aggregates insights from multiple CTMs if needed

#### 2. **CTMDomainRouter** (core/ctm_domain_router.py) - NEW
- Analyzes task features to determine cognitive domain
- Classifies tasks into: spatial, logic, temporal, value, or mixed
- Confidence scoring for domain classification
- Mixed-domain routing (e.g., "Deploy with auto-scaling" → Spatial + Temporal)

#### 3. **DreamModeCTMTrainer** (core/dream_mode_ctm_trainer.py) - NEW
- Extends Dream Mode with CTM-specific training
- Per-CTM training strategies:
  - **LogicCTM**: Replay constraint violations, type errors, verification failures
  - **TemporalCTM**: Replay timeout patterns, periodic anomalies, scheduling conflicts
  - **ValueCTM**: Replay resource allocation, priority conflicts, risk/benefit decisions
- Checkpoint management per CTM
- Training progress tracking

#### 4. **Specialized CTM Configurations**
Each CTM has domain-specific configuration:

**SpatialCTM** (current Klotski):
```python
{
    'target_modules': ['SOM', 'VIS', 'DMN'],  # Emphasize spatial reasoning
    'consciousness_threshold': 0.85,
    'max_reasoning_steps': 30,
    'task_encoding': 'spatial_grid'  # 5x4 board representation
}
```

**LogicCTM** (to be trained):
```python
{
    'target_modules': ['LAN', 'DLPFC', 'ACC'],  # Emphasize symbolic reasoning
    'consciousness_threshold': 0.90,  # Higher threshold for logical certainty
    'max_reasoning_steps': 50,  # More steps for proof-like reasoning
    'task_encoding': 'symbolic_tree'  # Tree-based constraint representation
}
```

**TemporalCTM** (to be trained):
```python
{
    'target_modules': ['AUD', 'MTL', 'INS'],  # Emphasize temporal patterns
    'consciousness_threshold': 0.80,  # Lower threshold (patterns are fuzzy)
    'max_reasoning_steps': 40,
    'task_encoding': 'time_series'  # Sequential state representation
}
```

**ValueCTM** (to be trained):
```python
{
    'target_modules': ['OFC', 'ACC', 'DMN'],  # Emphasize value estimation
    'consciousness_threshold': 0.85,
    'max_reasoning_steps': 35,
    'task_encoding': 'value_graph'  # Decision tree with utilities
}
```

---

## Task-to-Domain Mapping

### Domain Classification Rules

**Spatial Domain** (route to SpatialCTM):
- Keywords: "architecture", "infrastructure", "topology", "network", "dependencies", "layout"
- Task types: Microservice design, container orchestration, system diagrams
- Features: Graph structure, component relationships, spatial constraints

**Logic Domain** (route to LogicCTM):
- Keywords: "validate", "verify", "check", "constraint", "type", "compliance", "rules"
- Task types: Configuration validation, type checking, policy enforcement
- Features: Boolean logic, symbolic constraints, proof requirements

**Temporal Domain** (route to TemporalCTM):
- Keywords: "timeout", "schedule", "periodic", "pattern", "time-series", "rhythm", "sequence"
- Task types: Anomaly detection, scheduling, temporal pattern recognition
- Features: Time dependencies, periodicity, causal sequences

**Value Domain** (route to ValueCTM):
- Keywords: "decide", "prioritize", "trade-off", "allocate", "optimize", "risk", "benefit"
- Task types: Resource allocation, strategy selection, decision support
- Features: Utility functions, constraints, multi-objective optimization

**Mixed Domain** (route to multiple CTMs):
- Example: "Deploy auto-scaling microservices with fault tolerance"
  - Spatial: Architecture design (SpatialCTM)
  - Logic: Constraint validation (LogicCTM)
  - Temporal: Auto-scaling triggers (TemporalCTM)
  - Value: Resource trade-offs (ValueCTM)
- Strategy: Run CTMs in parallel, combine insights with weighted aggregation

---

## Dream Mode Training Strategy

### Phase 1: SpatialCTM (COMPLETE ✅)
**Status**: Already trained on Klotski puzzles
**Module Dominance**: SOM (96%), VIS (37%), DMN (34%)
**Use Cases**: Architecture, infrastructure, dependencies
**Performance**: 85-90% consciousness convergence in 12-15 steps

### Phase 2: LogicCTM Training (NEXT)
**Training Data Sources**:
- Episodic memories of configuration validation failures
- Type errors from code execution
- Constraint violation patterns
- Policy compliance failures

**Training Procedure**:
1. Dream Mode triggers during idle (5-minute threshold)
2. Select logic-related episodic memories (filter by error type)
3. Encode as symbolic constraint problems
4. Train LogicCTM with consciousness convergence on valid solutions
5. Monitor module shift: Expect LAN ↑, DLPFC ↑, ACC ↑

**Expected Module Dominance**: LAN (70-80%), DLPFC (15-20%), ACC (5-10%)

**Success Criteria**:
- Consciousness convergence on constraint satisfaction problems
- Correct identification of constraint violations
- Suggested strategy focuses on symbolic verification

### Phase 3: TemporalCTM Training
**Training Data Sources**:
- Timeout patterns from execution logs
- Periodic anomalies in system behavior
- Scheduling conflict memories
- Time-series data from monitoring

**Training Procedure**:
1. Encode temporal patterns as sequential states
2. Train on predicting next states and anomaly detection
3. Monitor module shift: Expect AUD ↑, MTL ↑, INS ↑

**Expected Module Dominance**: AUD (60-70%), MTL (20-25%), INS (10-15%)

### Phase 4: ValueCTM Training
**Training Data Sources**:
- Resource allocation decisions (success/failure)
- Priority conflicts and resolutions
- Risk/benefit trade-off outcomes
- Multi-objective optimization scenarios

**Training Procedure**:
1. Encode as decision trees with utility estimates
2. Train on maximizing expected value
3. Monitor module shift: Expect OFC ↑, ACC ↑, DMN ↑

**Expected Module Dominance**: OFC (60-70%), ACC (20-25%), DMN (10-15%)

---

## Integration with HierarchicalPlanner

### Modified Prediction Flow

**Before** (single CTM):
```python
def predict(self, task: str) -> PredictionResult:
    # Layer 1: Feature extraction
    features = self.task_router.extract_features(task)

    # Layer 2: Path planning
    path = self.conversation_planner.predict_path(task)

    # Layer 3: Decision routing
    decision = self.decision_router.route(features)

    # Async CTM (if complex)
    if complexity >= 0.75:
        ctm_task_id = self.ctm_reasoner.start_reasoning_async(task, brain_state)

    return prediction
```

**After** (Multi-CTM Ensemble):
```python
def predict(self, task: str) -> PredictionResult:
    # Layer 1: Feature extraction
    features = self.task_router.extract_features(task)

    # Layer 2: Path planning
    path = self.conversation_planner.predict_path(task)

    # Layer 3: Decision routing
    decision = self.decision_router.route(features)

    # Multi-CTM Ensemble (if complex)
    if complexity >= 0.75:
        # Route to specialized CTM(s)
        ctm_results = self.multi_ctm_ensemble.reason_async(
            task=task,
            brain_state=brain_state,
            domain_hint=features.get('task_type')  # Guide routing
        )

    return prediction
```

### Key Changes
1. Replace `CTMAsyncReasoner` with `MultiCTMEnsemble`
2. Add domain classification before CTM routing
3. Support parallel CTM execution for mixed-domain tasks
4. Aggregate insights from multiple CTMs

---

## Performance Expectations

### Latency
- **System 1 (HierarchicalPlanner)**: <100ms (unchanged)
- **Single CTM reasoning**: 5-15 seconds (unchanged)
- **Multi-CTM parallel reasoning**: 5-15 seconds (same as single, runs in parallel)
- **CTM routing overhead**: <10ms (negligible)

### Memory Footprint
- **Per CTM**: ~15 MB (3.7M parameters × 4 bytes)
- **Total for 4 CTMs**: ~60 MB
- **With checkpoints**: ~240 MB (4 training stages per CTM)

### Training Time
- **LogicCTM**: ~2-4 hours (10K constraint problems in Dream Mode)
- **TemporalCTM**: ~3-5 hours (15K time-series samples)
- **ValueCTM**: ~2-3 hours (8K decision scenarios)
- **Total**: ~10-15 hours of cumulative Dream Mode training

### Accuracy Expectations
- **SpatialCTM**: 85-90% (already validated)
- **LogicCTM**: 75-85% (constraint satisfaction is well-defined)
- **TemporalCTM**: 65-75% (temporal patterns are noisy)
- **ValueCTM**: 70-80% (subjective but learnable)

---

## Biological Plausibility

This architecture mirrors real brain specialization:

| CTM Type | Brain Region | Function |
|----------|--------------|----------|
| **SpatialCTM** | Parietal cortex | Spatial reasoning, navigation, topology |
| **LogicCTM** | Broca's area, DLPFC | Language, symbolic reasoning, planning |
| **TemporalCTM** | Auditory cortex, MTL | Temporal patterns, sequences, memory |
| **ValueCTM** | OFC, ACC | Value estimation, conflict resolution, decisions |

**Key insight**: The brain doesn't have a "universal reasoning module" - it has specialized regions that developed different expertise through evolution and learning.

---

## Implementation Phases

### Phase 1: Foundation (Current - Week 1)
- [ ] Create `MultiCTMEnsemble` class
- [ ] Create `CTMDomainRouter` class
- [ ] Define domain classification rules
- [ ] Test routing logic with current SpatialCTM
- [ ] Update HierarchicalPlanner integration

### Phase 2: Logic CTM Training (Week 2-3)
- [ ] Implement `DreamModeCTMTrainer` for LogicCTM
- [ ] Collect constraint violation memories
- [ ] Create symbolic task encoding
- [ ] Train LogicCTM in Dream Mode
- [ ] Validate on verification tasks

### Phase 3: Temporal CTM Training (Week 4-5)
- [ ] Implement TemporalCTM training strategy
- [ ] Collect time-series and timeout memories
- [ ] Create sequential task encoding
- [ ] Train TemporalCTM in Dream Mode
- [ ] Validate on pattern detection tasks

### Phase 4: Value CTM Training (Week 6-7)
- [ ] Implement ValueCTM training strategy
- [ ] Collect decision and trade-off memories
- [ ] Create value graph encoding
- [ ] Train ValueCTM in Dream Mode
- [ ] Validate on decision support tasks

### Phase 5: Integration & Testing (Week 8)
- [ ] Parallel CTM execution for mixed-domain tasks
- [ ] Insight aggregation strategies
- [ ] End-to-end testing across task types
- [ ] Performance benchmarking
- [ ] Documentation and demos

---

## Success Metrics

### Technical Metrics
1. **Routing Accuracy**: Domain router correctly classifies tasks (target: >85%)
2. **CTM Specialization**: Each CTM shows expected module dominance
3. **Consciousness Convergence**: All CTMs converge on domain-appropriate tasks
4. **Latency**: No regression in System 1 performance (<100ms maintained)

### Cognitive Metrics
1. **Task Coverage**: All 13 task types have optimal CTM routing
2. **Mixed-Domain Performance**: Multi-CTM aggregation improves complex tasks
3. **Explanation Quality**: CTM insights are domain-appropriate
4. **Failure Analysis**: CTMs detect domain-specific failures accurately

### Training Metrics
1. **Module Routing Shift**: Each CTM develops target module dominance during training
2. **Dream Mode Efficiency**: Training converges within expected time windows
3. **Checkpoint Quality**: Saved models show consistent performance across restarts
4. **Memory Efficiency**: Only relevant episodic memories used per CTM

---

## Risk Mitigation

### Risk 1: Training Doesn't Converge
**Mitigation**: Start with simple synthetic tasks per domain, gradually increase complexity

### Risk 2: Module Routing Doesn't Shift
**Mitigation**: Add module-specific loss functions to encourage target activations

### Risk 3: Domain Router Misclassifies Tasks
**Mitigation**: Fallback to SpatialCTM (most general), log misclassifications for manual review

### Risk 4: Memory Footprint Too Large
**Mitigation**: Implement CTM lazy loading - only load needed CTMs into memory

### Risk 5: Dream Mode Training Too Slow
**Mitigation**: Use batch training during dream cycles, prioritize high-impact memories

---

## Future Extensions

### Multi-Task CTM
Once all 4 CTMs are trained, explore:
- Transfer learning between CTMs (shared lower layers)
- Meta-learning across domains
- Curriculum learning (easy → hard tasks)

### Hierarchical CTM Ensemble
- CTMs can invoke other CTMs (e.g., SpatialCTM asks LogicCTM for constraint validation)
- Tree-structured reasoning for complex mixed-domain tasks

### Continual Learning
- CTMs update from production feedback (not just Dream Mode)
- Prevent catastrophic forgetting with elastic weight consolidation

### Human-in-the-Loop
- Users label CTM routing correctness
- Reinforcement learning from human preferences (RLHF)

---

## References

**Internal Documentation**:
- `KLOTSKI_CTM_INTEGRATION.md` - Original single CTM integration
- `DREAM_MODE_GUIDE.md` - Dream Mode implementation details
- `HIERARCHICAL_PLANNER_GUIDE.md` - 3-layer architecture
- `MEMORY_SYSTEM_COMPLETE.md` - Memory integration

**External Research**:
- Kahneman, D. (2011). *Thinking, Fast and Slow* - Dual-system cognitive architecture
- Hassabis, D. et al. (2017). *Neuroscience-Inspired AI* - Brain-inspired specialization
- Frankland & Bontempi (2005). *Systems Consolidation* - Memory replay during sleep

**Klotski Neurosymbolic Brain**:
- `learning_engine/klotski/ROUTED_BRAIN_FINAL_SUMMARY.md` - Training results
- `learning_engine/klotski/neurosymbolic/` - Full brain implementation

---

## Appendix: Task-to-CTM Routing Examples

### Example 1: Pure Spatial Task
**Task**: "Design microservice architecture with service mesh"
**Domain Router Analysis**:
- Spatial features: 0.92 (high)
- Logic features: 0.15 (low)
- Temporal features: 0.08 (low)
- Value features: 0.20 (low)

**Routing Decision**: SpatialCTM (confidence: 0.92)
**Expected Modules**: SOM (90%), VIS (40%), DMN (30%)
**Expected Strategy**: "Consider spatial/topological relationships, visualize dependency graph"

### Example 2: Pure Logic Task
**Task**: "Validate Kubernetes manifest against security policies"
**Domain Router Analysis**:
- Spatial features: 0.10 (low)
- Logic features: 0.95 (high)
- Temporal features: 0.05 (low)
- Value features: 0.12 (low)

**Routing Decision**: LogicCTM (confidence: 0.95)
**Expected Modules**: LAN (75%), DLPFC (20%), ACC (15%)
**Expected Strategy**: "Apply symbolic rules and logical constraints, verify against policy rules"

### Example 3: Mixed-Domain Task
**Task**: "Deploy auto-scaling microservices with fault tolerance and cost optimization"
**Domain Router Analysis**:
- Spatial features: 0.85 (high) - "microservices architecture"
- Logic features: 0.70 (moderate) - "fault tolerance constraints"
- Temporal features: 0.80 (high) - "auto-scaling triggers"
- Value features: 0.90 (high) - "cost optimization"

**Routing Decision**: Parallel execution - SpatialCTM, TemporalCTM, ValueCTM (confidence: 0.85)
**Expected Modules**:
- SpatialCTM: SOM (90%), VIS (40%)
- TemporalCTM: AUD (65%), MTL (25%)
- ValueCTM: OFC (70%), ACC (25%)

**Insight Aggregation**:
1. SpatialCTM: "Service mesh with 3-tier architecture"
2. TemporalCTM: "CPU threshold 70%, scale-up latency 30s"
3. ValueCTM: "Cost vs performance: prefer spot instances for batch jobs"

**Combined Strategy**: "Deploy 3-tier service mesh with auto-scaling on CPU>70% (30s lag), use spot instances for cost optimization while maintaining fault tolerance SLAs"

---

## Conclusion

The Multi-CTM Ensemble architecture provides **domain-specialized deep reasoning** while maintaining Tahlamus's fast System 1 performance. By training specialized CTMs during Dream Mode, we achieve biological-level cognitive specialization without sacrificing general-purpose capabilities.

**Next Steps**: Begin implementation with `MultiCTMEnsemble` and `CTMDomainRouter` classes.

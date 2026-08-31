# ATM-R Development Roadmap: Branch Strategy

This document outlines the development plan for expanding ATM-R into a comprehensive brain-inspired cognitive architecture, organized by feature branches.

---

## Branch Organization

### Phase 1: Core Brain Systems (Foundation)

#### `feature/cortical-feedback` (Priority 1)
**Goal**: Implement bidirectional cortex ↔ thalamus loops

- [ ] Design cortical feedback architecture (cortex → thalamus loops)
- [ ] Implement cortical processor modules that receive routed signals
- [ ] Add top-down attention signals to modulate priors π_i
- [ ] Implement cortical feedback to TRN inhibition matrix L_ij
- [ ] Create cortico-thalamic loop integration tests

**Dependencies**: None (builds on existing ThalamoPC6)
**Estimated effort**: 2-3 weeks
**Files to create**: `core/cortical_processor.py`, `tests/test_cortical_loops.py`

---

#### `feature/predictive-routing` (Priority 1)
**Goal**: Add forward models and anticipatory routing

- [ ] Design forward prediction model architecture
- [ ] Implement next-timestep input prediction mechanism
- [ ] Add anticipatory gate pre-adjustment based on predictions
- [ ] Implement temporal sequence learning for routing patterns
- [ ] Add learned routine detection and execution
- [ ] Create predictive routing unit tests

**Dependencies**: `feature/cortical-feedback` (uses cortical signals for predictions)
**Estimated effort**: 2-3 weeks
**Files to create**: `core/predictive_router.py`, `tests/test_predictive_routing.py`

---

### Phase 2: Action & Memory Systems

#### `feature/basal-ganglia` (Priority 2)
**Goal**: Implement action selection and Go/NoGo gating

- [ ] Design basal ganglia direct/indirect pathway architecture
- [ ] Implement Go/NoGo gating mechanism for action selection
- [ ] Add reward prediction error (RPE) computation for BG learning
- [ ] Integrate basal ganglia with thalamic routing
- [ ] Create basal ganglia unit tests and validation

**Dependencies**: `feature/cortical-feedback`
**Estimated effort**: 3-4 weeks
**Files to create**: `core/basal_ganglia.py`, `tests/test_basal_ganglia.py`

---

#### `feature/hippocampal-memory` (Priority 2)
**Goal**: Add episodic memory and context-dependent routing

- [ ] Design hippocampal memory buffer architecture
- [ ] Implement episodic memory storage (context, routing pattern) pairs
- [ ] Add novelty-based routing to hippocampus (high PE trigger)
- [ ] Implement memory retrieval and pattern completion
- [ ] Add memory-biased routing based on retrieved patterns
- [ ] Create hippocampal integration tests

**Dependencies**: `feature/predictive-routing`
**Estimated effort**: 3-4 weeks
**Files to create**: `core/hippocampus.py`, `tests/test_hippocampal_memory.py`

---

### Phase 3: Hierarchical & Multi-Scale Routing

#### `feature/hierarchical-routing` (Priority 3)
**Goal**: Multi-layer routing with abstraction hierarchy

- [ ] Design hierarchical multi-layer routing architecture
- [ ] Implement early sensory routing layer (V1→V2→V4 style)
- [ ] Implement mid-level semantic routing layer
- [ ] Implement high-level abstract reasoning routing layer
- [ ] Add skip connections between routing layers
- [ ] Create hierarchical routing integration tests

**Dependencies**: `feature/cortical-feedback`, `feature/predictive-routing`
**Estimated effort**: 4-5 weeks
**Files to create**: `core/hierarchical_router.py`, `tests/test_hierarchical_routing.py`

---

### Phase 4: Neuromodulation & Dynamics

#### `feature/neuromodulators` (Priority 3)
**Goal**: Implement dopamine, norepinephrine, acetylcholine, serotonin systems

- [ ] Design neuromodulator control architecture
- [ ] Implement dopamine system (reward-based gating enhancement)
- [ ] Implement norepinephrine system (arousal → broader gates)
- [ ] Implement acetylcholine system (attention → sharper gates)
- [ ] Implement serotonin system (mood effects on threat)
- [ ] Add dynamic τ_g modulation based on neuromodulators
- [ ] Create neuromodulator integration tests

**Dependencies**: `feature/basal-ganglia` (dopamine), `feature/cortical-feedback` (attention)
**Estimated effort**: 3-4 weeks
**Files to create**: `core/neuromodulators.py`, `tests/test_neuromodulators.py`

---

#### `feature/oscillatory-dynamics` (Priority 4)
**Goal**: Multi-frequency neural oscillations and phase coupling

- [ ] Design multi-frequency oscillator architecture
- [ ] Implement theta band oscillations (4-8 Hz)
- [ ] Implement gamma band oscillations (30-100 Hz)
- [ ] Implement alpha band oscillations (8-12 Hz)
- [ ] Add theta-gamma phase-amplitude coupling
- [ ] Implement alpha suppression for increased routing
- [ ] Create cross-frequency coupling tests

**Dependencies**: Extends existing Kuramoto oscillators in ThalamoPC6
**Estimated effort**: 3-4 weeks
**Files to create**: `core/oscillatory_coupling.py`, `tests/test_oscillations.py`

---

#### `feature/sleep-consolidation` (Priority 4)
**Goal**: Sleep mode with replay and synaptic homeostasis

- [ ] Design sleep mode architecture
- [ ] Implement hippocampal replay during sleep
- [ ] Add synaptic homeostasis mechanism
- [ ] Implement offline parameter adaptation
- [ ] Add wake/sleep state transitions
- [ ] Create sleep consolidation tests

**Dependencies**: `feature/hippocampal-memory`
**Estimated effort**: 2-3 weeks
**Files to create**: `core/sleep_mode.py`, `tests/test_sleep_consolidation.py`

---

### Phase 5: ML Framework Integration

#### `feature/pytorch-integration`
**Goal**: PyTorch wrappers for all new brain modules

- [ ] Create PyTorch wrapper for cortical feedback
- [ ] Create PyTorch wrapper for predictive routing
- [ ] Create PyTorch wrapper for basal ganglia
- [ ] Create PyTorch wrapper for hippocampal memory
- [ ] Create PyTorch wrapper for hierarchical routing
- [ ] Create PyTorch wrapper for neuromodulators
- [ ] Create PyTorch wrapper for oscillatory dynamics
- [ ] Create PyTorch wrapper for sleep mode

**Dependencies**: All Phase 1-4 feature branches
**Estimated effort**: 2-3 weeks
**Files to create**: `integrations/brain_torch.py`, `tests/test_torch_wrappers.py`

---

#### `feature/jax-integration`
**Goal**: JAX/Flax wrappers for all new brain modules

- [ ] Create JAX wrapper for cortical feedback
- [ ] Create JAX wrapper for predictive routing
- [ ] Create JAX wrapper for basal ganglia
- [ ] Create JAX wrapper for hippocampal memory
- [ ] Create JAX wrapper for hierarchical routing
- [ ] Create JAX wrapper for neuromodulators
- [ ] Create JAX wrapper for oscillatory dynamics
- [ ] Create JAX wrapper for sleep mode

**Dependencies**: All Phase 1-4 feature branches
**Estimated effort**: 2-3 weeks
**Files to create**: `integrations/brain_jax.py`, `tests/test_jax_wrappers.py`

---

### Phase 6: Visualization & Monitoring

#### `feature/visualization`
**Goal**: Comprehensive visualization tools for all brain subsystems

- [ ] Add visualization tools for cortical feedback loops
- [ ] Add visualization tools for basal ganglia action selection
- [ ] Add visualization tools for hierarchical routing
- [ ] Add visualization tools for memory retrieval patterns
- [ ] Add visualization tools for predictive routing dynamics
- [ ] Add visualization tools for neuromodulator effects
- [ ] Add visualization tools for oscillatory coupling

**Dependencies**: All Phase 1-4 feature branches
**Estimated effort**: 2-3 weeks
**Files to create**: `monitoring/brain_visualizer.py`, `templates/brain_monitor.html`

---

### Phase 7: Testing & Validation

#### `feature/validation`
**Goal**: Comprehensive testing and benchmarking suite

- [ ] Write comprehensive integration tests for all new modules
- [ ] Create validation suite for biological plausibility metrics
- [ ] Benchmark performance of new routing mechanisms
- [ ] Run full system validation on benchmark tasks
- [ ] Optimize performance bottlenecks in new modules

**Dependencies**: All Phase 1-6 branches
**Estimated effort**: 2-3 weeks
**Files to create**: `tests/test_integration.py`, `tests/test_biological_plausibility.py`, `scripts/benchmark_brain.py`

---

### Phase 8: Documentation & Examples

#### `feature/documentation`
**Goal**: Complete documentation for all brain-inspired systems

- [ ] Write documentation for cortico-thalamic system
- [ ] Write documentation for basal ganglia integration
- [ ] Write documentation for hierarchical routing
- [ ] Write documentation for hippocampal memory system
- [ ] Write documentation for predictive routing
- [ ] Write documentation for neuromodulator control
- [ ] Write documentation for oscillatory dynamics
- [ ] Write documentation for sleep consolidation
- [ ] Update README with new brain-inspired features
- [ ] Create ARCHITECTURE.md describing full brain-inspired system
- [ ] Update requirements.txt with new dependencies

**Dependencies**: All Phase 1-6 branches
**Estimated effort**: 2 weeks
**Files to create**: `BRAIN_ARCHITECTURE.md`, `docs/cortical_feedback.md`, `docs/basal_ganglia.md`, etc.

---

#### `feature/demos`
**Goal**: Interactive demonstrations of each brain subsystem

- [ ] Create demo: predictive routing with visual-auditory sequences
- [ ] Create demo: basal ganglia motor action selection
- [ ] Create demo: memory-guided routing with hippocampus
- [ ] Create demo: neuromodulator effects on routing behavior
- [ ] Create demo: sleep consolidation and learning improvement

**Dependencies**: All Phase 1-4 feature branches
**Estimated effort**: 2 weeks
**Files to create**: `demos/predictive_routing_demo.py`, `demos/basal_ganglia_demo.py`, etc.

---

#### `feature/tutorials`
**Goal**: Educational notebooks for each subsystem

- [ ] Create tutorial notebook: Cortico-thalamic loops
- [ ] Create tutorial notebook: Predictive routing
- [ ] Create tutorial notebook: Basal ganglia action selection
- [ ] Create tutorial notebook: Hippocampal memory
- [ ] Create tutorial notebook: Hierarchical routing
- [ ] Create tutorial notebook: Neuromodulators
- [ ] Create tutorial notebook: Oscillatory coupling
- [ ] Create tutorial notebook: Sleep consolidation
- [ ] Create tutorial notebook: Full brain system integration

**Dependencies**: All Phase 1-6 branches
**Estimated effort**: 2-3 weeks
**Files to create**: `notebooks/03_cortical_feedback.ipynb`, `notebooks/04_predictive_routing.ipynb`, etc.

---

### Phase 9: Research & Publication

#### `feature/research-paper`
**Goal**: Write comprehensive research paper documenting the architecture

- [ ] Write introduction & related work
- [ ] Document mathematical formulations for each subsystem
- [ ] Create system architecture diagrams
- [ ] Run experiments and collect results
- [ ] Write results & discussion sections
- [ ] Create figures and tables
- [ ] Write conclusion & future work
- [ ] Submit to conference/journal

**Dependencies**: All previous phases
**Estimated effort**: 4-6 weeks
**Files to create**: `paper/manuscript.tex`, `paper/figures/`, `paper/experiments/`

---

## Git Workflow

### Branch Naming Convention
```
feature/<feature-name>     # New features
bugfix/<bug-description>   # Bug fixes
hotfix/<critical-fix>      # Critical production fixes
docs/<doc-update>          # Documentation only
test/<test-addition>       # Test improvements
```

### Development Flow

1. **Start new feature**:
   ```bash
   git checkout master
   git pull origin master
   git checkout -b feature/cortical-feedback
   ```

2. **Regular commits during development**:
   ```bash
   git add .
   git commit -m "Add cortical processor base class"
   git push -u origin feature/cortical-feedback
   ```

3. **Create pull request** when feature is complete:
   - Run tests: `pytest tests/test_cortical_loops.py -v`
   - Ensure documentation is updated
   - Create PR to merge into `develop` branch

4. **Code review & merge**:
   - At least one reviewer approves
   - All tests pass
   - Merge to `develop`

5. **Release process**:
   - Periodically merge `develop` → `master`
   - Tag releases: `v0.2.0`, `v0.3.0`, etc.

---

## Priority Ordering

### Immediate Priority (Start Now)
1. `feature/cortical-feedback` ← Foundation for everything
2. `feature/predictive-routing` ← High impact, builds on cortical feedback

### High Priority (Next 1-2 months)
3. `feature/basal-ganglia` ← Action selection crucial
4. `feature/hippocampal-memory` ← Memory enables smarter routing

### Medium Priority (Months 3-4)
5. `feature/hierarchical-routing` ← Scalability
6. `feature/neuromodulators` ← Dynamic control

### Lower Priority (Months 5-6)
7. `feature/oscillatory-dynamics` ← Advanced neural dynamics
8. `feature/sleep-consolidation` ← Optimization/consolidation

### Integration & Polish (Months 7-9)
9. `feature/pytorch-integration`
10. `feature/jax-integration`
11. `feature/visualization`
12. `feature/validation`
13. `feature/documentation`
14. `feature/demos`
15. `feature/tutorials`

### Publication (Months 10-12)
16. `feature/research-paper`

---

## Estimated Timeline

**Total Duration**: ~10-12 months for full implementation

- **Phase 1**: Months 1-2 (Foundation)
- **Phase 2**: Months 2-4 (Action & Memory)
- **Phase 3**: Months 4-5 (Hierarchical)
- **Phase 4**: Months 5-7 (Neuromodulation & Dynamics)
- **Phase 5**: Months 7-8 (ML Integration)
- **Phase 6**: Month 8 (Visualization)
- **Phase 7**: Month 9 (Validation)
- **Phase 8**: Months 9-10 (Docs & Examples)
- **Phase 9**: Months 10-12 (Research Paper)

---

## Success Metrics

### Per-Branch Metrics
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Code coverage > 80%
- [ ] Documentation complete
- [ ] Example/demo working

### System-Level Metrics
- [ ] Gates still sum to 1.0 (critical invariant)
- [ ] No performance regression (< 10% slowdown)
- [ ] Biological plausibility metrics improve
- [ ] Benchmark task performance improves
- [ ] Memory usage stays reasonable (< 2GB for standard tasks)

---

## Notes

- **Parallel development**: Some branches can be worked on simultaneously (e.g., `feature/basal-ganglia` + `feature/hippocampal-memory`)
- **Testing discipline**: Every PR must include tests
- **Documentation as you go**: Don't defer all docs to the end
- **Incremental demos**: Create simple demos early, refine later
- **Regular integration**: Merge `develop` → feature branches weekly to avoid conflicts

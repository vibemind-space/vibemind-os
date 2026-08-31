# Neuromodulation Bridge Design

**Date:** 2026-02-25
**Status:** Approved
**Scope:** Connect 5 existing neuromodulator brain modules to the Radial Attention Network

## Problem

The Radial Attention Network (5-ring architecture with predictive coding, Hebbian plasticity, and sleep training) operates independently from the 43 neuroscience brain modules. Five neuromodulator modules (VTA, LC, Raphe, BasalForebrain, LateralHabenula) already implement biologically accurate transmitter dynamics but have no effect on attention, precision, or learning in the Radial Network.

## Decisions

- **Approach:** NeuromodulationBridge class (Ansatz A) — separate mediator between Radial Network and neuromodulator modules
- **When active:** Wake only (forward pass). Sleep training remains pure backprop.
- **Input source:** Prediction errors from the Radial Network forward pass (self-driven, no external signals needed)
- **Scope:** All 5 neuromodulators in one phase

## Architecture

### Data Flow (1-tick delay, biologically correct)

```
RadialAttentionNetwork.forward(seed_embedding)
    |
    +-- rings[0..4].forward(bottom_up, top_down, neuromod=self._neuromod_state)
    |       |
    |       +-- NE gain on attention output
    |       +-- DA + LHb on precision gate
    |       +-- ACh on FFN output
    |       +-- 5-HT on normalization
    |
    +-- compute prediction_errors[0..3]
    |
    +-- NeuromodulationBridge.update(prediction_errors)
    |       |
    |       +-- VTA.process(reward=1-avg_err, novelty=max_err, lhb_inhibition=prev_anti_reward)
    |       +-- LC.process(performance=1-avg_err, conflict=error_spread)
    |       +-- Raphe.process(reward_rate=1-avg_err, goal_progress=1-avg_err)
    |       +-- BF.process(attention=max_err, arousal=lc.arousal, reward=vta.rpe)
    |       +-- LHb.process(expected=1-prev_avg_err, actual=1-avg_err)
    |       |
    |       +-- returns NeuromodState (used on NEXT forward pass)
    |
    +-- DualProcessRouter.forward(s1, s2, neuromod=self._neuromod_state)
            |
            +-- NE explore_ratio modulates conflict threshold
```

### NeuromodState (dataclass)

```python
@dataclass
class NeuromodState:
    dopamine: float = 0.5        # VTA: precision/salience [0, 1]
    norepinephrine: float = 0.5  # LC: attention gain [0, 1]
    serotonin: float = 0.5       # Raphe: stability/decay [0, 1]
    acetylcholine: float = 0.5   # BF: plasticity gate [0, 1]
    anti_reward: float = 0.0     # LHb: suppression [0, 1]
    ne_gain: float = 1.0         # LC derived gain [0.2, 2.0]
    explore_ratio: float = 0.5   # LC explore/exploit [0, 1]
```

### 6 Modulation Hooks

| # | Location | Transmitter | Effect | Formula |
|---|----------|-------------|--------|---------|
| 1 | Attention output | NE (LC) | Gain/SNR | `x *= ne_gain` [0.2, 2.0] |
| 2 | Precision gate | DA (VTA) + LHb | Error trust | `precision *= (0.5+DA) * (1-0.5*LHb)` |
| 3 | FFN output | ACh (BF) | Throughput | `x *= (0.5+ACh)` [0.5, 1.5] |
| 4 | Pre-norm | 5-HT (Raphe) | Stability | `x *= (0.8+0.4*5HT)` [0.8, 1.2] |
| 5 | Hebbian decay | 5-HT (Raphe) | Consolidation | `decay *= (1.5-5HT)` [0.5, 1.5] |
| 6 | DualProcess threshold | NE (LC) | Explore/exploit | `thresh *= (1.5-explore)` [0.5, 1.5] |

### Inter-module Coupling

The 5 modules are coupled biologically:
- **LHb -> VTA:** `lhb_inhibition` suppresses dopamine
- **LC -> BF:** `arousal` drives tonic acetylcholine
- **VTA -> BF:** `rpe` modulates phasic acetylcholine burst

### Backward Compatibility

All hooks are guarded with `if neuromod:` — without a bridge attached, behavior is identical to current implementation. Zero breaking changes.

## Files Affected

| File | Change |
|------|--------|
| `core/neuromodulation_bridge.py` | **NEW** — NeuromodState + NeuromodulationBridge class |
| `core/radial_attention.py` | ADD `neuromod` param to RingLayer.forward(), DualProcessRouter.forward(), RadialAttentionNetwork wiring |
| `core/hebbian_plasticity.py` | ADD `neuromod` param to HebbianAttentionUpdate.update() for decay modulation |
| `production/production_planner.py` | ADD bridge wiring block after radial_attention setup |
| `configs/default.yaml` | ADD `neuromodulation: enabled: true` |
| `tests/test_neuromodulation_bridge.py` | **NEW** — unit + integration tests |

## Config

```yaml
neuromodulation:
  enabled: true  # Master switch, default true
```

No additional config needed — the 5 modules use their existing config sections.

## Wiring Pattern (production_planner.py)

```python
if cfg.get('neuromodulation', {}).get('enabled', False):
    bridge = NeuromodulationBridge(
        vta=self.agent_loop.ventral_tegmental_area,
        lc=self.agent_loop.locus_coeruleus,
        raphe=self.agent_loop.raphe_nuclei,
        basal_forebrain=self.agent_loop.basal_forebrain,
        lateral_habenula=self.agent_loop.lateral_habenula,
    )
    self.agent_loop.radial_attention.attach_neuromodulation(bridge)
    self.agent_loop.neuromod_bridge = bridge
```

## Testing Strategy

1. **Unit tests for NeuromodulationBridge:** Mock all 5 modules, verify state computation from prediction errors
2. **Unit tests for RingLayer modulation:** Verify each hook changes output vs no-neuromod baseline
3. **Integration test:** Full forward pass with bridge attached, verify neuromod_state in output dict
4. **Backward compatibility:** Existing 34 radial tests must still pass unchanged
5. **Eval extension:** Add neuromodulation section to `tests/eval_radial_quality.py`

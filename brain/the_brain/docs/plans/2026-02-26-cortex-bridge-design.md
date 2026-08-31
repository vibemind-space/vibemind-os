# CortexBridge Design — PFC + ACC + OFC → Radial Attention Network

**Date:** 2026-02-26
**Status:** Approved
**Depends on:** NeuromodulationBridge (complete, 25 tests)

## Overview

Connect the Cortex Trio (PrefrontalCortex, AnteriorCingulateCortex, OrbitofrontalCortex)
to the Radial Attention Network via a `CortexBridge` mediator — same pattern as
`NeuromodulationBridge`.

The NeuromodBridge handles **neurochemistry** (DA, NE, 5-HT, ACh, anti-reward).
The CortexBridge handles **cognition** (attention bias, conflict monitoring, value estimation).

## Architecture

```
RadialAttentionNetwork forward()
    ├── ring_activations[0..4]
    ├── prediction_errors[0..3]
    └── neuromod_state
            ↓
    CortexBridge.update(ring_activations, prediction_errors, neuromod_state)
        ├── Ring 4 (Abstract, 256D) → project to 32D → PFC.process()
        ├── Ring 5 (Meta, 128D)     → slice top 8    → ACC.process()
        └── Ring 2 (Pattern, 128D)  → project to 8D  → OFC.process()
            ↓
    CortexState {bias_signal, conflict, control_signal, subjective_value, ...}
        ↓ (used on NEXT forward — 1-tick delay)
    Hook 7: PFC bias_signal → additive modulation on Ring 4
    Hook 8: ACC conflict → DualProcessRouter threshold reduction
    Hook 9: OFC subjective_value → precision gate boost in RingLayers
```

## CortexState Dataclass

```python
@dataclass
class CortexState:
    # PFC outputs
    bias_signal: Optional[np.ndarray] = None  # Top-down attention bias [pfc_state_dim]
    inhibit: bool = False                      # Should current action be suppressed?
    pfc_value: float = 0.5                     # State value estimate
    pfc_surprise: float = 0.0                  # Reward prediction error

    # ACC outputs
    conflict: float = 0.0                      # Response conflict [0, 1]
    control_signal: float = 0.5                # Cognitive effort [0, 1]
    error_likelihood: float = 0.0              # P(error) [0, 1]

    # OFC outputs
    subjective_value: float = 0.5              # Net action value
    decision_confidence: float = 0.5           # How sure about choice [0, 1]
    choice_difficulty: float = 0.5             # 1 - confidence
```

## CortexBridge Class

```python
class CortexBridge:
    def __init__(self, pfc, acc, ofc, ring_to_pfc_dim=32, ring_to_ofc_dim=8):
        self._pfc = pfc
        self._acc = acc
        self._ofc = ofc
        self._state = CortexState()
        self._tick_count = 0

        # Dimension projections (numpy, no gradients)
        self._ring4_to_pfc = np.random.randn(ring_to_pfc_dim, 256) * 0.01
        self._ring2_to_ofc = np.random.randn(ring_to_ofc_dim, 128) * 0.01
```

### update() Flow

1. **Ring 4 (Abstract) -> PFC**: Project 256D to 32D, call `pfc.process(state, context={'conflict': prev_conflict})`
2. **Ring 5 (Meta) -> ACC**: Take top 8 channels as response activations, call `acc.process(activations, reward_magnitude)`
3. **Ring 2 (Pattern) -> OFC**: Project 128D to 8D, call `ofc.process(features, reward_history, effort_cost, risk)`

### Inter-Module Couplings

| From | To | Signal | Purpose |
|------|----|--------|---------|
| ACC conflict (tick t) | PFC context.conflict (tick t+1) | float [0,1] | ACC tells PFC how much control is needed |
| ACC effort | OFC effort_cost | float [0,1] | How expensive is the current action? |
| ACC error_likelihood | OFC risk | float [0,1] | How risky is the current decision? |

## Hooks in RadialAttentionNetwork

### Hook 7: PFC Bias Signal -> Ring 4 Modulation

```python
# After bottom-up pass, before top-down:
if cortex_state is not None and cortex_state.bias_signal is not None:
    bias_tensor = torch.tensor(cortex_state.bias_signal, dtype=torch.float32)
    bias_expanded = self._pfc_bias_proj(bias_tensor)  # 32D -> 256D
    ring_activations[3] = ring_activations[3] + bias_expanded * 0.1
```

PFC steers abstract representations — like a teacher saying "focus on X".

### Hook 8: ACC Conflict -> DualProcessRouter Threshold

```python
# In DualProcessRouter.forward():
if cortex_state is not None:
    effective_threshold *= (1.0 - 0.3 * cortex_state.conflict)
```

High conflict -> lower threshold -> more System 2 (deliberate). Complements Hook 6 (NE explore_ratio).

### Hook 9: OFC Value -> Precision Gate

```python
# In RingLayer.forward(), at precision gate:
if cortex_state is not None:
    value_boost = 0.8 + 0.4 * cortex_state.subjective_value  # [0.8, 1.2]
    precision = precision * value_boost
```

OFC says "this signal is valuable, process it precisely".

## Forward-Pass Order

```
1. Thalamic encoding (seed -> 128D)
2. Bottom-Up Pass (5 rings, neuromod hooks 1-4)
3. Hook 7: PFC bias additive on Ring 4
4. Top-Down Pass (prediction errors, neuromod hooks 1-4)
5. DualProcessRouter (neuromod hook 6 + Hook 8 ACC conflict)
6. NeuromodBridge.update(prediction_errors) -> NeuromodState for t+1
7. CortexBridge.update(ring_activations, prediction_errors) -> CortexState for t+1
```

## Wiring

### RadialAttentionNetwork

```python
def attach_cortex(self, bridge):
    self._cortex_bridge = bridge
    self._cortex_state = None
    self._pfc_bias_proj = nn.Linear(32, 256, bias=False)  # Learnable projection
```

### Production (production_planner.py)

After NeuromodulationBridge block:

```python
cx_cfg = self._yaml_config.get('cortex_bridge', {})
if cx_cfg.get('enabled', False):
    from core.cortex_bridge import CortexBridge
    bridge = CortexBridge(
        pfc=self.agent_loop.prefrontal_cortex,
        acc=self.agent_loop.anterior_cingulate,
        ofc=self.agent_loop.orbitofrontal_cortex,
    )
    self.agent_loop.radial_network.attach_cortex(bridge)
    self.agent_loop.cortex_bridge = bridge
```

### Config (default.yaml)

```yaml
cortex_bridge:
  enabled: true
```

## Backward Compatibility

All hooks guarded with `if cortex_state is not None:` — zero breaking changes.
Existing 59 Radial + Neuromod tests continue to pass untouched.

## Design Decisions

- **1-tick delay**: CortexState computed from tick t, used at tick t+1. Biologically correct.
- **numpy projections**: No torch gradients for CortexBridge projections. These are fixed random
  projections that preserve information structure without training. Sleep training only touches
  RingLayer parameters.
- **inhibit not hooked**: PFC's `inhibit` signal is an agent-loop-level concern, not ring-level.
  Will be wired when CortexBridge connects to the AgentLoop.
- **Separate from NeuromodBridge**: Neurochemistry (transmitters) ≠ Cognition (PFC/ACC/OFC).
  Different abstraction levels, different update frequencies in the future.

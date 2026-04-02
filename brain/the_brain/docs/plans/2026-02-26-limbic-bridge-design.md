# LimbicBridge Design — Amygdala + NAcc + InsularCortex + Hypothalamus -> Radial Attention

**Date:** 2026-02-26
**Pattern:** Same as NeuromodulationBridge / CortexBridge — mediator class, dataclass state, hooks on Radial Network, 1-tick delay.

## Modules

| Module | Primary Method | Input from Radial | Key Outputs |
|--------|---------------|-------------------|-------------|
| AmygdalaComplex | `process_stimulus(features, context)` | Ring 1 (Sensory, 64D) via 10x64 projection | valence, arousal, threat_level, hpa_activation |
| NucleusAccumbens | `evaluate(dopamine, reward_prediction, threat, action_complexity, energy)` | Aggregated signals | go_drive, nogo_drive, net_value, effort_cost |
| InsularCortex | `process(body_signals, novelty, emotional_intensity, stress, task_demand)` | Ring 2 (Pattern, 128D) as novelty source | salience, body_budget, feeling, body_deviation |
| HypothalamusModule | `update_drives(external_signals, elapsed_seconds)` | None (autonomous clock) | urgency, approach_drive, stress, circadian_phase |

## LimbicState Dataclass

```python
@dataclass
class LimbicState:
    # Amygdala outputs
    valence: float = 0.0           # [-1, 1] emotional valence
    arousal: float = 0.3           # [0, 1] emotional arousal
    threat_level: float = 0.0      # [0, 1] threat detection
    is_threat: bool = False        # Binary threat flag

    # NucleusAccumbens outputs
    go_drive: float = 0.5          # [0, 1] approach motivation
    nogo_drive: float = 0.5        # [0, 1] avoidance motivation
    net_value: float = 0.0         # Benefit - Cost
    effort_cost: float = 0.3       # [0, 1] perceived effort

    # InsularCortex outputs
    salience: float = 0.3          # [0, 1] overall salience
    body_budget: float = 1.0       # [0, 1] allostatic balance
    feeling: str = 'neutral'       # Subjective feeling label

    # Hypothalamus outputs
    urgency: float = 0.0           # [0, 1] homeostatic urgency
    approach_drive: float = 0.3    # [0, 1] lateral hypothalamus
    stress: float = 0.0            # [0, 1] HPA cortisol
```

## LimbicBridge.update() Flow

```
Input: ring_activations[5], prediction_errors[4], neuromod_state (optional)
Output: LimbicState

1. Ring 1 (Sensory, 64D) -> Amygdala (10 features via projection matrix)
   amygdala.process_stimulus(features=projected, context=prev_insula_body_state)

2. Ring 2 (Pattern, 128D) -> InsularCortex
   insular_cortex.process(
       novelty=avg_prediction_error,
       emotional_intensity=prev_amygdala_arousal,
       stress=prev_hypo_stress
   )

3. Hypothalamus (autonomous, no ring input)
   hypothalamus.update_drives(elapsed_seconds=1.0)
   hypothalamus.process_stressor(prev_amygdala_hpa_activation)

4. NucleusAccumbens (aggregates all)
   nucleus_accumbens.evaluate(
       dopamine=neuromod_state.dopamine if available else 0.5,
       reward_prediction=1.0 - avg_PE,
       threat=amygdala_threat_level,
       energy=1.0 - hypothalamus_urgency
   )
```

## Inter-Module Coupling (tick t -> tick t+1)

| Source | Target | Signal |
|--------|--------|--------|
| Amygdala hpa_activation | Hypothalamus process_stressor() | Threat -> stress response |
| Amygdala arousal | InsularCortex emotional_intensity | Emotion -> salience |
| Amygdala threat_level | NAcc threat | Threat -> avoidance |
| Hypothalamus stress | InsularCortex stress | Cortisol -> body monitoring |
| Hypothalamus urgency | NAcc energy (1 - urgency) | Needs -> effort cost |
| InsularCortex body_state | Amygdala context | Body signals -> emotional context |

## 4 New Hooks on Radial Attention Network

### Hook 10: Amygdala Arousal -> Attention Gain (RingLayer)
```python
# In RingLayer.forward(), after self-attention, alongside Hook 1 (NE gain):
if limbic_state is not None:
    arousal_gain = 0.7 + 0.6 * limbic_state.arousal  # [0.7, 1.3]
    attended = attended * arousal_gain
```
Emotional arousal amplifies attention across all rings.

### Hook 11: Salience -> Precision Gate (RingLayer)
```python
# In RingLayer.forward(), at precision gate, alongside Hook 2 (DA) and Hook 9 (OFC):
if limbic_state is not None:
    sal_boost = 0.8 + 0.4 * limbic_state.salience  # [0.8, 1.2]
    precision = precision * sal_boost
```
Salient signals get higher prediction-error weighting.

### Hook 12: NoGo Drive -> DualProcessRouter Threshold
```python
# In DualProcessRouter.forward(), alongside Hook 6 (NE) and Hook 8 (ACC):
if limbic_state is not None:
    effective_threshold *= (1.0 - 0.2 * limbic_state.nogo_drive)
```
Avoidance motivation lowers threshold -> more System 2 (cautious deliberation).

### Hook 13: Urgency -> FFN Throughput (RingLayer)
```python
# In RingLayer.forward(), at FFN output, alongside Hook 3 (ACh):
if limbic_state is not None:
    urg_gate = 0.8 + 0.4 * limbic_state.urgency  # [0.8, 1.2]
    output = output * urg_gate
```
Urgent homeostatic needs amplify network throughput.

## Hook Stacking Summary

All hooks compose multiplicatively with existing hooks:

| Location | Hook Chain |
|----------|-----------|
| Attention output | NE gain (H1) * Arousal gain (H10) |
| Precision gate | DA+LHb (H2) * OFC value (H9) * Salience (H11) |
| FFN output | ACh (H3) * 5-HT stability (H4) * Urgency (H13) |
| DualProcess threshold | NE explore (H6) * ACC conflict (H8) * NoGo drive (H12) |

## Wiring in RadialAttentionNetwork

```python
def attach_limbic(self, bridge) -> None:
    self._limbic_bridge = bridge
    self._limbic_state = None
    # No nn.Linear needed -- all hooks are multiplicative, no projection
```

Forward-pass order (after all rings + top-down):
```python
# 1. NeuromodBridge.update(prediction_errors) -> NeuromodState
# 2. CortexBridge.update(ring_acts, PEs, neuromod) -> CortexState
# 3. LimbicBridge.update(ring_acts, PEs, neuromod) -> LimbicState
```

## Production Wiring

```python
# After CortexBridge block in production_planner.py:
lm_cfg = self._yaml_config.get('limbic_bridge', {})
if lm_cfg.get('enabled', False):
    from core.limbic_bridge import LimbicBridge
    limbic_bridge = LimbicBridge(
        amygdala=self.agent_loop.amygdala_complex,
        nucleus_accumbens=self.agent_loop.nucleus_accumbens,
        insular_cortex=self.agent_loop.insular_cortex,
        hypothalamus=self.agent_loop.hypothalamus,
    )
    self.agent_loop.radial_network.attach_limbic(limbic_bridge)
    self.agent_loop.limbic_bridge = limbic_bridge
```

## Config

```yaml
limbic_bridge:
  enabled: true
```

## Projection Matrices

| Source | Target | Matrix Shape | Purpose |
|--------|--------|-------------|---------|
| Ring 1 (64D) | Amygdala (10 features) | (10, 64) | Sensory -> emotional features |

Only one projection needed -- Amygdala expects 10 features from sensory input. All other modules receive scalar signals or cached previous-tick values.

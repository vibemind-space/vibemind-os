# Full Bridge Integration Design — 26 Modules, 7 Bridges, 16 New Hooks

> **Date:** 2026-03-01
> **Goal:** Connect all 26 remaining brain modules to the Radial Attention Network via 7 new bridges (H14-H29), using a unified ModulationContext architecture.

## Architecture: ModulationContext

### Problem
Current pattern adds kwargs per bridge to `RingLayer.forward()`. Going from 3 to 10 bridges makes signatures unscalable.

### Solution
A unified `ModulationContext` dataclass holds all bridge states and pre-computes 4 composite modulation factors. RingLayer and DualProcessRouter consume composite factors instead of individual states.

```python
@dataclass
class ModulationContext:
    # Individual bridge states (set by RadialAttentionNetwork.forward)
    neuromod: Optional[NeuromodState] = None
    cortex: Optional[CortexState] = None
    limbic: Optional[LimbicState] = None
    sleep_wake: Optional[SleepWakeState] = None
    motor: Optional[MotorState] = None
    defense: Optional[DefenseState] = None
    memory: Optional[MemoryState] = None
    integration: Optional[IntegrationState] = None
    visceral: Optional[VisceralState] = None
    social: Optional[SocialPerceptionState] = None

    # Pre-computed composite factors (call compute() after setting states)
    attention_gain: float = 1.0
    precision_boost: float = 1.0
    ffn_throughput: float = 1.0
    threshold_mod: float = 1.0
    ring4_bias: Optional[np.ndarray] = None

    def compute(self):
        """Compute composite factors from all active bridge states.
        Each hook multiplies into its target factor.
        Final product clamped to [0.3, 3.0] for stability.
        """
        att = 1.0
        prec = 1.0
        ffn = 1.0
        thr = 1.0

        # --- Existing hooks (migrated from inline) ---
        if self.neuromod:
            nm = self.neuromod
            att *= 0.5 + nm.ne_gain                              # H1
            prec *= 0.5 + nm.dopamine                            # H2 (part)
            prec *= 1.0 - 0.3 * nm.anti_reward                  # H2 (anti-reward)
            ffn *= 0.5 + nm.acetylcholine                        # H3
            ffn *= 0.8 + 0.4 * nm.serotonin                     # H4
            thr *= 1.5 - nm.explore_ratio                        # H6

        if self.cortex:
            cx = self.cortex
            prec *= 0.7 + 0.6 * cx.subjective_value             # H9
            thr *= 1.0 - 0.3 * cx.conflict                      # H8
            if cx.bias_signal is not None:
                self.ring4_bias = cx.bias_signal                 # H7

        if self.limbic:
            lm = self.limbic
            att *= 0.7 + 0.6 * lm.arousal                       # H10
            prec *= 0.8 + 0.4 * lm.salience                     # H11
            thr *= 1.0 - 0.2 * lm.nogo_drive                    # H12
            ffn *= 0.8 + 0.4 * lm.urgency                       # H13

        # --- New hooks ---
        if self.sleep_wake:
            sw = self.sleep_wake
            att *= 0.5 + sw.arousal                              # H14 [0.5, 1.5]
            ffn *= 0.5 + 0.5 * sw.histamine                     # H15 [0.5, 1.0]
            thr *= 1.0 + 0.3 * sw.melatonin                     # H16

        if self.motor:
            mt = self.motor
            ffn *= 0.8 + 0.4 * mt.model_confidence              # H17 [0.8, 1.2]
            att *= 0.8 + 0.4 * mt.action_tendency                # H18 [0.8, 1.2]

        if self.defense:
            df = self.defense
            att *= 0.7 + 0.8 * df.defense_intensity              # H19 [0.7, 1.5]
            ffn *= 1.0 - 0.4 * df.anxiety_level                  # H20 [0.6, 1.0]

        if self.memory:
            mm = self.memory
            att *= 0.8 + 0.4 * mm.theta_power                   # H21 [0.8, 1.2]
            prec *= 0.8 + 0.4 * mm.consolidation_strength       # H22 [0.8, 1.2]

        if self.integration:
            ig = self.integration
            att *= 0.7 + 0.6 * ig.binding_strength               # H23 [0.7, 1.3]
            ffn *= 1.0 - 0.3 * ig.dmn_activation                 # H24 [0.7, 1.0]
            att *= 0.8 + 0.4 * ig.orienting_saliency             # H25 [0.8, 1.2]

        if self.visceral:
            vs = self.visceral
            thr *= 1.0 - 0.2 * vs.afferent_strength              # H26
            prec *= 0.9 + 0.2 * vs.liking                        # H27 [0.9, 1.1]

        if self.social:
            sc = self.social
            att *= 0.9 + 0.2 * sc.social_salience                # H28 [0.9, 1.1]
            prec *= 0.9 + 0.2 * sc.familiarity                   # H29 [0.9, 1.1]

        # Safety clamp
        self.attention_gain = max(0.3, min(3.0, att))
        self.precision_boost = max(0.3, min(3.0, prec))
        self.ffn_throughput = max(0.3, min(3.0, ffn))
        self.threshold_mod = max(0.3, min(3.0, thr))
```

### RingLayer.forward() simplification

After refactor, the hook section becomes:

```python
# All attention hooks via composite factor
if modulation is not None:
    attended = attended * modulation.attention_gain

# ... precision gate ...
if modulation is not None:
    precision = precision * modulation.precision_boost

# ... FFN ...
if modulation is not None:
    output = output * modulation.ffn_throughput
```

Backward compat: existing `neuromod=`, `cortex_state=`, `limbic_state=` kwargs still accepted. If `modulation` is provided, it takes precedence.

### DualProcessRouter simplification

```python
if modulation is not None:
    effective_threshold = self.conflict_threshold * modulation.threshold_mod
else:
    effective_threshold = self.conflict_threshold
    # ... legacy hook logic for neuromod, cortex, limbic ...
```

---

## Bridge 1: SleepWakeBridge

**File:** `core/sleep_wake_bridge.py`
**Modules:** ReticularFormation, TuberomammillaryNucleus, PinealGland, PedunculopontineNucleus

### SleepWakeState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| arousal | float | [0, 1] | RF.process().arousal |
| sensory_gain | float | [0, 1] | RF.process().sensory_gain |
| histamine | float | [0, 1] | TMN.process().histamine_level |
| is_awake | bool | — | TMN.process().is_awake |
| wakefulness_drive | float | [0, 1] | TMN.process().wakefulness_drive |
| melatonin | float | [0, 1] | PG.process().melatonin_level |
| sleep_pressure | float | [0, 1] | PG.process().sleep_pressure |
| cholinergic_tone | float | [0, 1] | PPN.process().cholinergic_tone |
| rem_probability | float | [0, 1] | PPN.process().rem.rem_probability |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H14 | RF arousal | attention_gain | 0.5 + arousal | [0.5, 1.5] |
| H15 | TMN histamine | ffn_throughput | 0.5 + 0.5 * histamine | [0.5, 1.0] |
| H16 | PG melatonin | threshold_mod | 1.0 + 0.3 * melatonin | [1.0, 1.3] |

### Inter-Module Coupling (1-tick delay via cached values)

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| PinealGland | TMN | melatonin | TMN sleep_pressure input |
| ReticularFormation | PPN | arousal | PPN arousal input |
| PPN | TMN | rem_probability | TMN arousal_drive reduced |
| TMN | RF | is_awake | RF alert_signals input |

### Update Flow

```
RF.process(sensory_input_level=avg_ring_activation, circadian_phase=prev_circadian, alert_signals=prev_is_awake)
  -> arousal, sensory_gain
TMN.process(arousal_drive=rf_arousal, circadian_phase=prev_circadian, sleep_pressure=prev_melatonin)
  -> histamine_level, is_awake, wakefulness_drive
PG.process(light_exposure=0.5, circadian_phase=tick_count/1000, external_zeitgeber=prev_arousal)
  -> melatonin_level, sleep_pressure, circadian_strength
PPN.process(movement_intention=0.0, bg_release=0.5, arousal=rf_arousal, sleep_pressure=prev_sleep_pressure)
  -> cholinergic_tone, rem_probability
```

---

## Bridge 2: MotorBridge

**File:** `core/motor_bridge.py`
**Modules:** CerebellumModule, SubstantiaNigra, ZonaIncerta, RedNucleus, PosteriorParietalCortex

### MotorState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| prediction_error | float | [0, inf) | Cerebellum.compute_sensory_prediction_error().prediction_error |
| model_confidence | float | [0, 1] | Cerebellum.compute_sensory_prediction_error().model_confidence |
| motor_da | float | [0, 1] | SN.process().motor_da |
| go_nogo_balance | float | [-1, 1] | SN.process().go_nogo_balance |
| disinhibited | bool | — | SN.process().disinhibited |
| inhibition_level | float | [0, 1] | ZI.process().inhibition_level |
| action_tendency | float | [0, 1] | ZI.process().action_tendency |
| is_compensating | bool | — | RN.process().is_compensating |
| error_correction | float | [0, inf) | RN.process().error_correction |
| peak_salience | float | [0, 1] | PPC.process().peak_salience |
| movement_confidence | float | [0, 1] | PPC.process().action_plan.movement_confidence |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H17 | Cerebellum confidence | ffn_throughput | 0.8 + 0.4 * model_confidence | [0.8, 1.2] |
| H18 | ZI action_tendency | attention_gain | 0.8 + 0.4 * action_tendency | [0.8, 1.2] |

### Inter-Module Coupling

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| SN | ZI | motor_da | ZI motivation input |
| PPC | SN | peak_salience | SN action_value input |
| Cerebellum | RN | prediction_error | RN error_signal input |
| ZI | PPC | 1 - inhibition_level | PPC goal_relevance scaling |

### Update Flow

```
Cerebellum.compute_sensory_prediction_error(predicted=ring2, actual=ring1)
  -> prediction_error, model_confidence
SN.process(motor_demand=avg_pe, effort=0.5, action_value=prev_peak_salience)
  -> motor_da, go_nogo_balance, disinhibited
ZI.process(motivation=prev_motor_da, motor_readiness=0.5, arousal=0.5)
  -> inhibition_level, action_tendency
RN.process(primary_motor_signal=0.5, error_signal=cerebellum_error, cerebellar_input=model_confidence)
  -> is_compensating, error_correction
PPC.process(visual_salience=ring1[:16], goal_relevance=ring1[:16] * (1 - prev_inhibition))
  -> peak_salience, action_plan.movement_confidence
```

---

## Bridge 3: DefenseBridge

**File:** `core/defense_bridge.py`
**Modules:** PeriaqueductalGray, BedNucleusStriaTerminalis, ParabrachialNucleus

### DefenseState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| defense_mode | str | fight/flight/freeze | PAG.process().selected_defense |
| defense_intensity | float | [0, 1] | PAG.process().defense_intensity |
| emergency_mode | bool | — | PAG.process().emergency_mode |
| autonomic_activation | float | [0, 1] | PAG.process().autonomic_activation |
| anxiety_level | float | [0, 1] | BNST.process().anxiety_level |
| vigilance | float | [0, 1] | BNST.process().vigilance |
| is_chronic_stress | bool | — | BNST.process().is_chronic_stress |
| alarm_level | float | [0, 1] | PBN.process().alarm_level |
| alarm_urgency | float | [0, 1] | PBN.process().urgency |
| should_interrupt | bool | — | PBN.process().should_interrupt (from interoceptive_alarm_priority) |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H19 | PAG defense_intensity | attention_gain | 0.7 + 0.8 * defense_intensity | [0.7, 1.5] |
| H20 | BNST anxiety_level | ffn_throughput | 1.0 - 0.4 * anxiety_level | [0.6, 1.0] |

### Inter-Module Coupling

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| PBN | PAG | alarm_level | PAG threat input |
| BNST | PAG | anxiety_level | PAG arousal input |
| PAG | PBN | autonomic_activation | PBN error_rate input |

### Update Flow

```
PBN.process({pain: avg_pe, error_rate: avg_pe, visceral_distress: prev_autonomic})
  -> alarm_level, urgency, should_interrupt
BNST.process(threat_level=avg_pe, uncertainty=prediction_error_variance, stressor_intensity=prev_alarm)
  -> anxiety_level, vigilance, is_chronic_stress
PAG.process(threat=max(prev_alarm, avg_pe), escapability=0.5, proximity=prev_anxiety, arousal=prev_anxiety)
  -> defense_mode, defense_intensity, emergency_mode, autonomic_activation
```

---

## Bridge 4: MemoryBridge

**File:** `core/memory_bridge.py`
**Modules:** EntorhinalCortex, MammillaryBodies, SeptalNuclei, InferiorOlive

### MemoryState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| theta_power | float | [0, 1] | SN.process().theta_power |
| theta_frequency | float | Hz | SN.process().theta_frequency |
| coupling_strength | float | [0, 1] | SN.process().coupling_strength |
| consolidation_strength | float | [0, 1] | MB.process().consolidation_strength |
| relay_strength | float | [0, 1] | MB.process().relay_strength |
| teaching_signal | float | [0, 1] | IO.process().teaching_signal |
| error_magnitude | float | [0, inf) | IO.process().error_magnitude |
| memory_gateway | float | [0, 1] | norm(EC.process_input(ring1)) normalized |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H21 | SN theta_power | attention_gain | 0.8 + 0.4 * theta_power | [0.8, 1.2] |
| H22 | MB consolidation | precision_boost | 0.8 + 0.4 * consolidation_strength | [0.8, 1.2] |

### Inter-Module Coupling

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| EC | MB | encoding norm | MB hippocampal_signal input |
| SeptalNuclei | EC | theta_power | Modulates EC encoding gain |
| SeptalNuclei | MB | theta_power | MB importance input |

### Update Flow

```
SeptalNuclei.process(arousal=0.5, memory_demand=avg_pe, reward_signal=0.0, threat_signal=0.0)
  -> theta_power, theta_frequency, coupling_strength
ec_encoding = EC.process_input(ring1_activation)
memory_gateway = clamp(norm(ec_encoding) / sqrt(dim), 0, 1)
MB.process(hippocampal_signal=memory_gateway, importance=prev_theta_power, emotional_arousal=0.5)
  -> consolidation_strength, relay_strength
IO.process(prediction=ring2[:io_dim], actual=ring1[:io_dim])
  -> teaching_signal, error_magnitude
```

---

## Bridge 5: IntegrationBridge

**File:** `core/integration_bridge.py`
**Modules:** Claustrum, DefaultModeNetwork, SuperiorColliculus, CorticalColumn, CorpusCallosum

### IntegrationState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| binding_strength | float | [0, 1] | Claustrum.process().binding_strength |
| reached_consciousness | bool | — | Claustrum.process().reached_consciousness |
| dmn_activation | float | [0, 1] | DMN.process().activation_level |
| dmn_mode | str | — | DMN.process().mode |
| orienting_saliency | float | [0, 1] | SC.process().peak_saliency |
| cortical_error | float | [0, inf) | CC_col.process().error_magnitude |
| cortical_output | float | [0, inf) | CC_col.process().output_magnitude |
| bilateral_coherence | float | [0, 1] | CC.process().coordination_quality |
| transfer_efficiency | float | [0, 1] | CC.process().transfer_efficiency |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H23 | Claustrum binding | attention_gain | 0.7 + 0.6 * binding_strength | [0.7, 1.3] |
| H24 | DMN activation | ffn_throughput | 1.0 - 0.3 * dmn_activation | [0.7, 1.0] |
| H25 | SC saliency | attention_gain | 0.8 + 0.4 * orienting_saliency | [0.8, 1.2] |

### Inter-Module Coupling

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| SC | Claustrum | peak_saliency | Claustrum attention input |
| CC | CorticalColumn | coordination_quality | CC_col cortical_input scaling |
| DMN | Claustrum | 1 - activation_level | Claustrum salience input |

### Update Flow

```
SC.process(visual=ring1[:sc_dim])
  -> peak_saliency, orienting_command
DMN.process(state=ring4[:dmn_dim], task_load=1.0 - avg_pe_variance)
  -> activation_level, mode
Claustrum.process(modality_signals={'ring1': ring1, 'ring3': ring3},
                  salience=prev_saliency, attention=1 - prev_dmn_activation)
  -> binding_strength, reached_consciousness
CC_col.process(thalamic_input=ring1[:cc_dim], cortical_input=ring3[:cc_dim] * prev_coherence)
  -> error_magnitude, output_magnitude
CC.process(left_signal=ring3[:cc_half], right_signal=ring3[cc_half:])
  -> coordination_quality, transfer_efficiency
```

---

## Bridge 6: VisceralBridge

**File:** `core/visceral_bridge.py`
**Modules:** NucleusTractSolitarius, VentralPallidum

### VisceralState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| visceral_level | float | [0, 1] | NTS.process().overall_visceral |
| afferent_strength | float | [0, 1] | NTS.process().afferent_strength |
| reflex_active | bool | — | NTS.process().reflex_active |
| liking | float | [0, 1] | VP.process().liking.liking_response |
| wanting | float | [0, 1] | VP.process().wanting_signal |
| approach_strength | float | [0, 1] | VP.process().motor.approach_strength |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H26 | NTS afference | threshold_mod | 1.0 - 0.2 * afferent_strength | [0.8, 1.0] |
| H27 | VP liking | precision_boost | 0.9 + 0.2 * liking | [0.9, 1.1] |

### Inter-Module Coupling

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| NTS | VP | visceral_level | VP inhibition input (visceral distress dampens pleasure) |

### Update Flow

```
NTS.process({heart_rate: 0.5, breathing_rate: 0.5, nutrient_status: 0.5,
             error_rate: avg_pe, visceral_distress: prev_visceral})
  -> overall_visceral, afferent_strength, reflex_active
VP.process(reward_signal=1.0 - avg_pe, opioid_level=0.5,
           wanting_signal=0.5, inhibition=prev_visceral * 0.3)
  -> liking.liking_response, wanting_signal, motor.approach_strength
```

---

## Bridge 7: SocialPerceptionBridge

**File:** `core/social_perception_bridge.py`
**Modules:** FusiformGyrus, TemporoparietalJunction, OlfactorySystem

### SocialPerceptionState Dataclass

| Field | Type | Range | Source |
|-------|------|-------|--------|
| face_detected | bool | — | FG.process().face_result.face_detected |
| identity_score | float | [0, 1] | FG.process().face_result.identity_score |
| text_detected | bool | — | FG.process().text_result.text_detected |
| word_score | float | [0, 1] | FG.process().text_result.word_score |
| agency_score | float | [0, 1] | TPJ.process().agency_result.agency_score |
| reorient_signal | bool | — | TPJ.process().reorienting_result.reorient_signal |
| social_inference | float | [0, 1] | TPJ.process().tom_result.confidence |
| social_salience | float | [0, 1] | max(identity_score, social_inference) |
| familiarity | float | [0, 1] | Olfactory.process().familiarity |
| is_novel | bool | — | Olfactory.process().is_novel |

### Hooks

| Hook | Signal | Target | Formula | Range |
|------|--------|--------|---------|-------|
| H28 | social_salience | attention_gain | 0.9 + 0.2 * social_salience | [0.9, 1.1] |
| H29 | familiarity | precision_boost | 0.9 + 0.2 * familiarity | [0.9, 1.1] |

### Inter-Module Coupling

| From | To | Signal | Mechanism |
|------|----|--------|-----------|
| FG | TPJ | face_detected (as action_signal) | TPJ action_signal = 1.0 if face_detected |
| Olfactory | FG | familiarity | FG input features biased by familiarity |

### Update Flow

```
Olfactory.process(ring1[:32])
  -> familiarity, is_novel
fg_input = ring1[:fg_dim] * (1.0 + 0.1 * prev_familiarity)
FG.process(fg_input, domain='auto')
  -> face_result, text_result
TPJ.process(action_signal=1.0 if prev_face_detected else 0.0,
            sensory_feedback=avg_pe, prediction=1.0 - avg_pe)
  -> agency_result, tom_result, reorienting_result
social_salience = max(identity_score, social_inference)
```

---

## Hook Summary (H1-H29)

### By Target

**Attention gain (9 hooks, multiplicative, clamped [0.3, 3.0]):**
| Hook | Bridge | Signal | Range |
|------|--------|--------|-------|
| H1 | Neuromod | NE gain | [0.5, 1.5] |
| H10 | Limbic | Arousal | [0.7, 1.3] |
| H14 | SleepWake | RF arousal | [0.5, 1.5] |
| H18 | Motor | ZI action_tendency | [0.8, 1.2] |
| H19 | Defense | PAG defense_intensity | [0.7, 1.5] |
| H21 | Memory | SN theta_power | [0.8, 1.2] |
| H23 | Integration | Claustrum binding | [0.7, 1.3] |
| H25 | Integration | SC saliency | [0.8, 1.2] |
| H28 | Social | social_salience | [0.9, 1.1] |

**Precision boost (6 hooks, multiplicative, clamped [0.3, 3.0]):**
| Hook | Bridge | Signal | Range |
|------|--------|--------|-------|
| H2 | Neuromod | DA + anti-reward | [0.5, 1.5] |
| H9 | Cortex | OFC value | [0.7, 1.3] |
| H11 | Limbic | Salience | [0.8, 1.2] |
| H22 | Memory | MB consolidation | [0.8, 1.2] |
| H27 | Visceral | VP liking | [0.9, 1.1] |
| H29 | Social | Familiarity | [0.9, 1.1] |

**FFN throughput (7 hooks, multiplicative, clamped [0.3, 3.0]):**
| Hook | Bridge | Signal | Range |
|------|--------|--------|-------|
| H3 | Neuromod | ACh | [0.5, 1.5] |
| H4 | Neuromod | 5-HT stability | [0.8, 1.2] |
| H13 | Limbic | Urgency | [0.8, 1.2] |
| H15 | SleepWake | TMN histamine | [0.5, 1.0] |
| H17 | Motor | Cerebellum confidence | [0.8, 1.2] |
| H20 | Defense | BNST anxiety | [0.6, 1.0] |
| H24 | Integration | DMN activation (inv) | [0.7, 1.0] |

**DualProcess threshold (5 hooks, multiplicative, clamped [0.3, 3.0]):**
| Hook | Bridge | Signal | Range |
|------|--------|--------|-------|
| H6 | Neuromod | NE explore_ratio | variable |
| H8 | Cortex | ACC conflict | variable |
| H12 | Limbic | NoGo drive | variable |
| H16 | SleepWake | PG melatonin | [1.0, 1.3] |
| H26 | Visceral | NTS afference | [0.8, 1.0] |

**Ring 4 additive (1 hook):**
| Hook | Bridge | Signal |
|------|--------|--------|
| H7 | Cortex | PFC bias_signal |

---

## Implementation Strategy

### Phase 1: ModulationContext + Refactor (foundation)
1. Create `core/modulation_context.py` with ModulationContext dataclass
2. Refactor RingLayer.forward() to use composite factors
3. Refactor DualProcessRouter.forward() to use composite threshold_mod
4. Refactor RadialAttentionNetwork.forward() to build ModulationContext
5. Migrate existing 3 bridges to set states on ModulationContext
6. All existing tests must remain green

### Phase 2: Build 7 bridges (one at a time, TDD)
Each bridge follows the same pattern:
1. State dataclass + Bridge class + tests
2. Wire into ModulationContext.compute()
3. Production wiring + config
4. Eval section

Order: SleepWake -> Motor -> Defense -> Memory -> Integration -> Visceral -> Social

### Phase 3: Eval + MEMORY.md
- Add eval sections 11-17 to eval_radial_quality.py
- Update MEMORY.md with all 7 bridges
- Final integration test: all 10 bridges active simultaneously

---

## Config (default.yaml additions)

```yaml
sleep_wake_bridge:
  enabled: true

motor_bridge:
  enabled: true

defense_bridge:
  enabled: true

memory_bridge:
  enabled: true

integration_bridge:
  enabled: true

visceral_bridge:
  enabled: true

social_perception_bridge:
  enabled: true
```

---

## Production Wiring (production_planner.py additions)

Each bridge wired after existing bridges, same pattern:
```python
sw_cfg = self._yaml_config.get('sleep_wake_bridge', {})
if sw_cfg.get('enabled', False):
    try:
        from core.sleep_wake_bridge import SleepWakeBridge
        sw_bridge = SleepWakeBridge(
            reticular_formation=self.agent_loop.reticular_formation,
            tuberomammillary_nucleus=self.agent_loop.tuberomammillary_nucleus,
            pineal_gland=self.agent_loop.pineal_gland,
            pedunculopontine_nucleus=self.agent_loop.pedunculopontine_nucleus,
        )
        # Attach to RadialAttentionNetwork via ModulationContext
        self.agent_loop.radial_network.attach_bridge('sleep_wake', sw_bridge)
        self.agent_loop.sleep_wake_bridge = sw_bridge
        print("[AgentLoop] SleepWakeBridge wired -> RadialAttentionNetwork")
    except Exception as e:
        print(f"[AgentLoop] SleepWakeBridge not available: {e}")
```

---

## Estimated Scope

- 7 new bridge files (~180 lines each)
- 1 new ModulationContext file (~150 lines)
- Refactor radial_attention.py (~100 lines changed)
- Refactor production_planner.py (~70 lines added)
- 7 new test files (~25-30 tests each, ~175-210 tests total)
- 7 new eval sections
- Config additions
- MEMORY.md updates

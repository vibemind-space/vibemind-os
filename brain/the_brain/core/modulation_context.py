"""ModulationContext -- unified modulation container for RadialAttentionNetwork.

Holds all bridge states and pre-computes 4 composite modulation factors.
See: docs/plans/2026-03-01-full-bridge-integration-design.md
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.hook_coefficients import HookCoefficients


@dataclass
class ModulationContext:
    """Unified container for all bridge states.

    After setting bridge states, call compute() to derive composite factors.
    RingLayer and DualProcessRouter consume the composite factors only.

    Bridge states (set by RadialAttentionNetwork.forward before compute()):
        neuromod:    NeuromodState  -- DA, NE, 5-HT, ACh, anti_reward
        cortex:      CortexState   -- PFC bias, ACC conflict, OFC value
        limbic:      LimbicState   -- arousal, salience, nogo, urgency
        sleep_wake:  SleepWakeState -- arousal, histamine, melatonin
        motor:       MotorState    -- model_confidence, action_tendency
        defense:     DefenseState  -- defense_intensity, anxiety_level
        memory:      MemoryState   -- theta_power, consolidation_strength
        integration: IntegrationState -- binding, DMN, orienting
        visceral:    VisceralState -- afferent_strength, liking
        social:      SocialPerceptionState -- social_salience, familiarity

    Composite factors (computed by compute()):
        attention_gain:  multiplicative gain on attention weights
        precision_boost: multiplicative boost on precision gating
        ffn_throughput:  multiplicative throughput on FFN processing
        threshold_mod:   multiplicative modifier on DualProcess threshold
        ring4_bias:      additive bias on Ring 4 (from PFC top-down)

    Consciousness (set by ConsciousnessLoop, post-compute):
        consciousness_level: scalar [0, 1] from ConsciousnessLoop
        consciousness_state: full ConsciousnessState snapshot
    """
    # --- Bridge states (set before compute()) ---
    neuromod: Optional[object] = None       # NeuromodState
    cortex: Optional[object] = None         # CortexState
    limbic: Optional[object] = None         # LimbicState
    sleep_wake: Optional[object] = None     # SleepWakeState
    motor: Optional[object] = None          # MotorState
    defense: Optional[object] = None        # DefenseState
    memory: Optional[object] = None         # MemoryState
    integration: Optional[object] = None    # IntegrationState
    visceral: Optional[object] = None       # VisceralState
    social: Optional[object] = None         # SocialPerceptionState

    # --- Pre-computed composite factors ---
    attention_gain: float = 1.0
    precision_boost: float = 1.0
    ffn_throughput: float = 1.0
    threshold_mod: float = 1.0
    ring4_bias: Optional[np.ndarray] = None

    # --- Consciousness Loop (set after compute(), used on next tick) ---
    consciousness_level: float = 0.5
    consciousness_state: Optional[object] = None  # ConsciousnessState

    # --- Inter-bridge coupling registry (optional) ---
    coupling_registry: Optional[object] = None  # InterBridgeCouplingRegistry

    # --- Learnable hook coefficients (optional) ---
    hook_coefficients: Optional[HookCoefficients] = None

    def compute(self):
        """Compute composite factors from all active bridge states.

        Each hook multiplies into its target factor.
        Final product clamped to [0.3, 3.0] for stability.

        Hook index reference:
            H1:  NE gain -> attention_gain
            H2:  DA + anti_reward -> precision_boost
            H3:  ACh -> ffn_throughput
            H4:  5-HT -> ffn_throughput (stability)
            H6:  explore_ratio -> threshold_mod
            H7:  PFC bias_signal -> ring4_bias
            H8:  ACC conflict -> threshold_mod
            H9:  OFC subjective_value -> precision_boost
            H10: arousal -> attention_gain
            H11: salience -> precision_boost
            H12: nogo_drive -> threshold_mod
            H13: urgency -> ffn_throughput
            H14: sleep arousal -> attention_gain
            H15: histamine -> ffn_throughput
            H16: melatonin -> threshold_mod
            H17: motor confidence -> ffn_throughput
            H18: action tendency -> attention_gain
            H19: defense intensity -> attention_gain
            H20: anxiety -> ffn_throughput
            H21: theta power -> attention_gain
            H22: consolidation -> precision_boost
            H23: binding strength -> attention_gain
            H24: DMN activation -> ffn_throughput
            H25: orienting saliency -> attention_gain
            H26: afferent strength -> threshold_mod
            H27: liking -> precision_boost
            H28: social salience -> attention_gain
            H29: familiarity -> precision_boost
        """
        # --- Inter-bridge coupling (fires before hooks) ---
        if self.coupling_registry is not None:
            bridge_states = {
                'neuromod': self.neuromod,
                'cortex': self.cortex,
                'limbic': self.limbic,
                'sleep_wake': self.sleep_wake,
                'motor': self.motor,
                'defense': self.defense,
                'memory': self.memory,
                'integration': self.integration,
                'visceral': self.visceral,
                'social': self.social,
            }
            self.coupling_registry.propagate(bridge_states)

        att = 1.0
        prec = 1.0
        ffn = 1.0
        thr = 1.0

        # Use learnable coefficients if provided, else hardcoded defaults
        hc = self.hook_coefficients

        # --- Existing bridge hooks (H1-H13) ---
        if self.neuromod is not None:
            nm = self.neuromod
            if hc is not None:
                att *= hc.h1_att_ne_offset + hc.h1_att_ne_scale * nm.ne_gain         # H1
                prec *= (hc.h2a_prec_da_offset + hc.h2a_prec_da_scale * nm.dopamine) \
                    * (1.0 - hc.h2b_prec_antirwd_scale * nm.anti_reward)              # H2
                ffn *= (hc.h3_ffn_ach_offset + hc.h3_ffn_ach_scale * nm.acetylcholine) \
                    * (hc.h4_ffn_5ht_offset + hc.h4_ffn_5ht_scale * nm.serotonin)    # H3+H4
                thr *= hc.h6_thr_explore_offset - hc.h6_thr_explore_scale * nm.explore_ratio  # H6
            else:
                att *= 0.5 + nm.ne_gain                                               # H1
                prec *= (0.5 + nm.dopamine) * (1.0 - 0.3 * nm.anti_reward)           # H2
                ffn *= (0.5 + nm.acetylcholine) * (0.8 + 0.4 * nm.serotonin)         # H3+H4
                thr *= 1.5 - nm.explore_ratio                                         # H6

        if self.cortex is not None:
            cx = self.cortex
            if hc is not None:
                prec *= hc.h9_prec_value_offset + hc.h9_prec_value_scale * cx.subjective_value  # H9
                thr *= hc.h8_thr_conflict_offset - hc.h8_thr_conflict_scale * cx.conflict       # H8
            else:
                prec *= 0.7 + 0.6 * cx.subjective_value                              # H9
                thr *= 1.0 - 0.3 * cx.conflict                                       # H8
            if cx.bias_signal is not None:
                self.ring4_bias = cx.bias_signal                                      # H7

        if self.limbic is not None:
            lm = self.limbic
            if hc is not None:
                att *= hc.h10_att_arousal_offset + hc.h10_att_arousal_scale * lm.arousal     # H10
                prec *= hc.h11_prec_salience_offset + hc.h11_prec_salience_scale * lm.salience  # H11
                thr *= hc.h12_thr_nogo_offset - hc.h12_thr_nogo_scale * lm.nogo_drive       # H12
                ffn *= hc.h13_ffn_urgency_offset + hc.h13_ffn_urgency_scale * lm.urgency    # H13
            else:
                att *= 0.7 + 0.6 * lm.arousal                                        # H10
                prec *= 0.8 + 0.4 * lm.salience                                      # H11
                thr *= 1.0 - 0.2 * lm.nogo_drive                                     # H12
                ffn *= 0.8 + 0.4 * lm.urgency                                        # H13

        # --- New bridge hooks (H14-H29) ---
        if self.sleep_wake is not None:
            sw = self.sleep_wake
            if hc is not None:
                att *= hc.h14_att_sleep_offset + hc.h14_att_sleep_scale * sw.arousal          # H14
                ffn *= hc.h15_ffn_hist_offset + hc.h15_ffn_hist_scale * sw.histamine          # H15
                thr *= hc.h16_thr_mel_offset + hc.h16_thr_mel_scale * sw.melatonin            # H16
            else:
                att *= 0.5 + sw.arousal                                               # H14
                ffn *= 0.5 + 0.5 * sw.histamine                                      # H15
                thr *= 1.0 + 0.3 * sw.melatonin                                      # H16

        if self.motor is not None:
            mt = self.motor
            if hc is not None:
                ffn *= hc.h17_ffn_motconf_offset + hc.h17_ffn_motconf_scale * mt.model_confidence  # H17
                att *= hc.h18_att_action_offset + hc.h18_att_action_scale * mt.action_tendency      # H18
            else:
                ffn *= 0.8 + 0.4 * mt.model_confidence                               # H17
                att *= 0.8 + 0.4 * mt.action_tendency                                # H18

        if self.defense is not None:
            df = self.defense
            if hc is not None:
                att *= hc.h19_att_defense_offset + hc.h19_att_defense_scale * df.defense_intensity  # H19
                ffn *= hc.h20_ffn_anxiety_offset - hc.h20_ffn_anxiety_scale * df.anxiety_level     # H20
            else:
                att *= 0.7 + 0.8 * df.defense_intensity                              # H19
                ffn *= 1.0 - 0.4 * df.anxiety_level                                  # H20

        if self.memory is not None:
            mm = self.memory
            if hc is not None:
                att *= hc.h21_att_theta_offset + hc.h21_att_theta_scale * mm.theta_power           # H21
                prec *= hc.h22_prec_consol_offset + hc.h22_prec_consol_scale * mm.consolidation_strength  # H22
            else:
                att *= 0.8 + 0.4 * mm.theta_power                                    # H21
                prec *= 0.8 + 0.4 * mm.consolidation_strength                        # H22

        if self.integration is not None:
            ig = self.integration
            if hc is not None:
                att *= hc.h23_att_binding_offset + hc.h23_att_binding_scale * ig.binding_strength   # H23
                ffn *= hc.h24_ffn_dmn_offset - hc.h24_ffn_dmn_scale * ig.dmn_activation            # H24
                att *= hc.h25_att_orient_offset + hc.h25_att_orient_scale * ig.orienting_saliency   # H25
            else:
                att *= 0.7 + 0.6 * ig.binding_strength                               # H23
                ffn *= 1.0 - 0.3 * ig.dmn_activation                                 # H24
                att *= 0.8 + 0.4 * ig.orienting_saliency                             # H25

        if self.visceral is not None:
            vs = self.visceral
            if hc is not None:
                thr *= hc.h26_thr_afferent_offset - hc.h26_thr_afferent_scale * vs.afferent_strength  # H26
                prec *= hc.h27_prec_liking_offset + hc.h27_prec_liking_scale * vs.liking               # H27
            else:
                thr *= 1.0 - 0.2 * vs.afferent_strength                              # H26
                prec *= 0.9 + 0.2 * vs.liking                                        # H27

        if self.social is not None:
            sc = self.social
            if hc is not None:
                att *= hc.h28_att_social_offset + hc.h28_att_social_scale * sc.social_salience      # H28
                prec *= hc.h29_prec_fam_offset + hc.h29_prec_fam_scale * sc.familiarity             # H29
            else:
                att *= 0.9 + 0.2 * sc.social_salience                                # H28
                prec *= 0.9 + 0.2 * sc.familiarity                                   # H29

        # Safety clamp to [0.3, 3.0]
        self.attention_gain = max(0.3, min(3.0, att))
        self.precision_boost = max(0.3, min(3.0, prec))
        self.ffn_throughput = max(0.3, min(3.0, ffn))
        self.threshold_mod = max(0.3, min(3.0, thr))

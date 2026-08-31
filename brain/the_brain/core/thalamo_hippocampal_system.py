"""
Thalamo-Hippocampal System

Integrates thalamic routing with hippocampal episodic memory, basal ganglia action
selection, and cortical feedback loops.

System flow:
1. Thalamic processing generates state and gates
2. High prediction error triggers hippocampal encoding
3. Hippocampus retrieves similar past experiences
4. Basal ganglia selects action mode (ADVANCE/EXPLORE/CORRECT)
5. Memory-biased gates influence routing decisions
6. CA3 pattern completion provides additional gate modulation
7. BG action gates modulate final thalamic output
8. Cortical feedback provides top-down attention modulation

Integration with ActionPotentialOscillator and NeuromodulationSystem:
- Oscillator state provides cortical input to BG and attention control
- Dopamine level modulates BG Go/NoGo competition and goal-driven attention
- Norepinephrine modulates feedback gain (arousal)
- BG output modulates thalamic gates
- Cortical feedback modulates priors and TRN inhibition
"""

import numpy as np
from typing import Dict, Optional, List, TYPE_CHECKING
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive
from core.hippocampus import Hippocampus
from core.basal_ganglia import BasalGanglia, BasalGangliaOutput
from core.cortical_feedback import CorticalProcessor, CorticalFeedback
from core.predictive_router import PredictiveRouter, RoutingPrediction

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels
    from core.multi_band_oscillator import MultiBandOscillator, MultiBandState


class ThalamoHippocampalSystem:
    """
    Thalamic routing system with hippocampal episodic memory, basal ganglia,
    and cortical feedback.

    Combines ThalamoPC6Adaptive with hippocampal memory, basal ganglia, and
    cortical feedback for context-dependent, experience-based routing with
    action selection and top-down attention modulation.

    Integration with ActionPotentialOscillator:
        osc = ActionPotentialOscillator()
        neuromod = NeuromodulationSystem()
        ths = ThalamoHippocampalSystem(enable_basal_ganglia=True, enable_cortex=True)

        # Step with BG and cortical modulation
        result = ths.step(
            x,
            oscillator_state=osc.state,
            neuromod_levels=neuromod.levels,
            goal=goal_vector
        )
    """

    def __init__(
        self,
        # Thalamic parameters
        modalities: Optional[List[str]] = None,
        dimensions: Optional[Dict[str, int]] = None,
        tau: Optional[Dict[str, float]] = None,
        priors: Optional[Dict[str, float]] = None,
        beta: Optional[Dict[str, float]] = None,
        trn_lambda: float = 0.5,
        trn_L: Optional[np.ndarray] = None,
        gate_temp: float = 0.5,
        num_targets: int = 3,
        dt: float = 1.0,
        seed: int = 42,
        nonlinearity: str = "tanh",
        use_phase: bool = False,
        omega: Optional[Dict[str, float]] = None,
        K_coupling: float = 0.05,
        # Adaptive parameters
        lr_input: float = 0.001,
        lr_generative: float = 0.01,
        lr_trn: float = 0.0005,
        lr_prior: float = 0.0001,
        lr_tau: float = 0.0001,
        lr_gate_temp: float = 0.0001,
        target_activity: float = 0.5,
        target_entropy: float = 1.5,
        tau_min: float = 10.0,
        tau_max: float = 200.0,
        prior_min: float = 0.01,
        prior_max: float = 2.0,
        gate_temp_min: float = 0.1,
        gate_temp_max: float = 2.0,
        trn_max: float = 5.0,
        hazard_scale: float = 0.1,
        reward_scale: float = 0.05,
        # Hippocampal parameters
        enable_hippocampus: bool = True,
        dg_dim: int = 512,
        dg_sparsity: float = 0.05,
        memory_capacity: int = 1000,
        novelty_threshold: float = 0.5,
        retrieval_threshold: float = 0.7,
        learning_rate_ca3: float = 0.01,
        memory_influence: float = 0.3,
        # Basal ganglia parameters
        enable_basal_ganglia: bool = True,
        bg_temperature: float = 0.5,
        bg_learning_rate: float = 0.01,
        bg_modulation_strength: float = 0.3,
        # Cortical feedback parameters
        enable_cortex: bool = True,
        goal_dim: int = 32,
        cortex_alpha_goal: float = 0.4,
        cortex_beta_osc: float = 0.3,
        cortex_gamma_pe: float = 0.3,
        cortex_prior_strength: float = 0.1,
        cortex_trn_strength: float = 0.05,
        # Predictive routing parameters
        enable_predictive_routing: bool = True,
        predictive_blend_alpha: float = 0.3,
        predictive_hidden_dim: int = 64,
        predictive_temperature: float = 1.0,
        predictive_sequence_length: int = 5,
        predictive_n_patterns: int = 10,
        # Multi-band oscillator parameters
        enable_multi_band: bool = False,
        multi_band_config: Optional[Dict[str, float]] = None
    ):
        """
        Initialize thalamo-hippocampal system.

        Args:
            modalities: List of modality names
            dimensions: Dict mapping modality -> dimension
            ... (see ThalamoPC6Adaptive for thalamic args)
            enable_hippocampus: If True, enable hippocampal memory
            dg_dim: Dentate gyrus dimension
            dg_sparsity: DG sparsity level (0.05 = 5% active)
            memory_capacity: Maximum number of episodic memories
            novelty_threshold: PE threshold for encoding
            retrieval_threshold: Similarity threshold for retrieval
            learning_rate_ca3: CA3 learning rate
            memory_influence: Strength of memory bias on gates
            enable_basal_ganglia: If True, enable BG action selection
            bg_temperature: BG softmax temperature for action selection
            bg_learning_rate: BG TD learning rate
            bg_modulation_strength: How strongly BG modulates thalamic gates
            enable_cortex: If True, enable cortical feedback loops
            goal_dim: Dimension of goal/task encoding for cortex
            cortex_alpha_goal: Cortex attention weight for goal-driven
            cortex_beta_osc: Cortex attention weight for oscillator-modulated
            cortex_gamma_pe: Cortex attention weight for PE-driven
            cortex_prior_strength: Strength of cortical prior modulation
            cortex_trn_strength: Strength of cortical TRN modulation
            enable_predictive_routing: If True, enable predictive routing
            predictive_blend_alpha: Weight for anticipated gates (0-1)
            predictive_hidden_dim: Hidden dimension for forward models
            predictive_temperature: Softmax temperature for anticipated gates
            predictive_sequence_length: Length of temporal routing patterns
            predictive_n_patterns: Number of patterns to store
            enable_multi_band: If True, enable multi-band oscillator integration
            multi_band_config: Config for multi-band oscillator (theta_freq, alpha_freq, etc.)
        """
        # Initialize thalamus
        self.thalamus = ThalamoPC6Adaptive(
            modalities=modalities,
            dimensions=dimensions,
            tau=tau,
            priors=priors,
            beta=beta,
            trn_lambda=trn_lambda,
            trn_L=trn_L,
            gate_temp=gate_temp,
            num_targets=num_targets,
            dt=dt,
            seed=seed,
            nonlinearity=nonlinearity,
            use_phase=use_phase,
            omega=omega,
            K_coupling=K_coupling,
            lr_input=lr_input,
            lr_generative=lr_generative,
            lr_trn=lr_trn,
            lr_prior=lr_prior,
            lr_tau=lr_tau,
            lr_gate_temp=lr_gate_temp,
            target_activity=target_activity,
            target_entropy=target_entropy,
            tau_min=tau_min,
            tau_max=tau_max,
            prior_min=prior_min,
            prior_max=prior_max,
            gate_temp_min=gate_temp_min,
            gate_temp_max=gate_temp_max,
            trn_max=trn_max,
            hazard_scale=hazard_scale,
            reward_scale=reward_scale
        )

        self.enable_hc = enable_hippocampus
        self.enable_bg = enable_basal_ganglia
        self.bg_modulation_strength = bg_modulation_strength
        self.timestep = 0

        # Initialize basal ganglia
        if enable_basal_ganglia:
            self.basal_ganglia = BasalGanglia(
                n_inputs=6,  # 6D oscillator state
                n_actions=3,  # ADVANCE, EXPLORE, CORRECT
                temperature=bg_temperature,
                learning_rate=bg_learning_rate
            )
            self._last_bg_output: Optional[BasalGangliaOutput] = None
        else:
            self.basal_ganglia = None
            self._last_bg_output = None

        if enable_hippocampus:
            # Compute total state dimension
            state_dim = sum(self.thalamus.d.values())
            context_dim = len(self.thalamus.modalities)

            # Initialize hippocampus
            self.hippocampus = Hippocampus(
                state_dim=state_dim,
                context_dim=context_dim,
                num_modalities=len(self.thalamus.modalities),
                dg_dim=dg_dim,
                sparsity=dg_sparsity,
                memory_capacity=memory_capacity,
                novelty_threshold=novelty_threshold,
                retrieval_threshold=retrieval_threshold,
                learning_rate_ca3=learning_rate_ca3,
                memory_influence=memory_influence,
                seed=seed + 5000
            )
        else:
            self.hippocampus = None

        # Initialize cortical feedback processor
        self.enable_cortex = enable_cortex
        self.goal_dim = goal_dim
        self._last_cortical_feedback: Optional[CorticalFeedback] = None

        if enable_cortex:
            self.cortex = CorticalProcessor(
                n_modalities=len(self.thalamus.modalities),
                goal_dim=goal_dim,
                state_dim=sum(self.thalamus.d.values()),
                modality_dims=self.thalamus.d,
                modality_order=list(self.thalamus.modalities),
                alpha_goal=cortex_alpha_goal,
                beta_osc=cortex_beta_osc,
                gamma_pe=cortex_gamma_pe,
                prior_strength=cortex_prior_strength,
                trn_strength=cortex_trn_strength,
                enable_learning=True,
                seed=seed + 6000
            )
        else:
            self.cortex = None

        # Initialize predictive router
        self.enable_predictive = enable_predictive_routing
        self._last_routing_prediction: Optional[RoutingPrediction] = None

        if enable_predictive_routing:
            self.predictive_router = PredictiveRouter(
                modalities=list(self.thalamus.modalities),
                latent_dims=self.thalamus.d,
                blend_alpha=predictive_blend_alpha,
                hidden_dim=predictive_hidden_dim,
                temperature=predictive_temperature,
                sequence_length=predictive_sequence_length,
                n_patterns=predictive_n_patterns
            )
        else:
            self.predictive_router = None

        # Initialize multi-band oscillator (if enabled)
        self.enable_multi_band = enable_multi_band
        self._multi_band_osc: Optional['MultiBandOscillator'] = None
        self._last_multi_band_state: Optional['MultiBandState'] = None

        if enable_multi_band:
            from core.multi_band_oscillator import MultiBandOscillator as MBO

            # Apply config or use defaults
            config = multi_band_config or {}
            self._multi_band_osc = MBO(
                theta_freq=config.get('theta_freq', 6.0),
                alpha_freq=config.get('alpha_freq', 10.0),
                gamma_freq=config.get('gamma_freq', 40.0),
                pac_theta_alpha=config.get('pac_theta_alpha', 0.5),
                pac_alpha_gamma=config.get('pac_alpha_gamma', 0.5)
            )

    def _pack_state(self) -> np.ndarray:
        """Pack thalamic state for hippocampus."""
        parts = [self.thalamus.v[m] for m in self.thalamus.modalities]
        return np.concatenate(parts)

    def _compute_gates(
        self,
        ctx: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """Compute current gate distribution."""
        s = np.zeros(self.thalamus.M)
        for i, m in enumerate(self.thalamus.modalities):
            activity = np.linalg.norm(self.thalamus.v[m])
            novelty = self.thalamus.PE[m]
            prior = self.thalamus.priors[m]
            context_weight = ctx[i] if ctx is not None else 0.0

            s[i] = (self.thalamus.beta["activity"] * activity +
                    self.thalamus.beta["novelty"] * novelty +
                    self.thalamus.beta["prior"] * prior +
                    self.thalamus.beta["context"] * context_weight)

        # Softmax
        s_scaled = s / self.thalamus.gate_temp
        s_scaled = s_scaled - np.max(s_scaled)
        exp_s = np.exp(s_scaled)
        gates = exp_s / np.sum(exp_s)

        return gates

    def step(
        self,
        x: Dict[str, np.ndarray],
        ctx: Optional[np.ndarray] = None,
        hazard: Optional[Dict[str, float]] = None,
        reward: Optional[Dict[str, float]] = None,
        adapt: bool = True,
        encode_memory: bool = True,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        td_error: Optional[float] = None,
        goal: Optional[np.ndarray] = None
    ) -> Dict:
        """
        Single timestep with hippocampal memory, basal ganglia, and cortical feedback.

        Args:
            x: Modality inputs
            ctx: Context vector
            hazard: Hazard signals
            reward: Reward signals
            adapt: Whether to adapt parameters
            encode_memory: Whether to encode to hippocampus
            oscillator_state: TripleOscillatorState for BG cortical input
            neuromod_levels: NeuromodulatorLevels for dopamine/urgency
            td_error: TD error for BG learning (optional)
            goal: Goal/task encoding for cortical attention [goal_dim]

        Returns:
            Dict with thalamic, hippocampal, BG, and cortical outputs
        """
        # 1) Thalamic processing
        thalamic_out = self.thalamus.step(
            x, ctx=ctx, hazard=hazard, reward=reward, adapt=adapt
        )

        # Compute gates
        gates = self._compute_gates(ctx)

        result = {
            'thalamic_output': thalamic_out,
            'gates': gates,
            'timestep': self.timestep
        }

        # 1.5) Predictive routing adjustment (if enabled)
        routing_prediction = None
        if self.enable_predictive and self.predictive_router is not None:
            # Get current latent states
            v_current = {m: self.thalamus.v[m].copy() for m in self.thalamus.modalities}

            # Get context for prediction (combine ctx and cortical attention if available)
            pred_context = None
            if ctx is not None:
                pred_context = ctx.copy()
            elif self.cortex is not None:
                pred_context = self.cortex.state.attention_weights.copy()

            # Step predictive router
            routing_prediction = self.predictive_router.step(
                v_current=v_current,
                current_gates=gates,
                context=pred_context
            )
            self._last_routing_prediction = routing_prediction

            # Apply predicted gates
            gates = routing_prediction.blended_gates

            # Add predictive info to result
            result['predictive_routing'] = {
                'blended_gates': routing_prediction.blended_gates.tolist(),
                'gate_deltas': routing_prediction.gate_deltas.tolist(),
                'prediction_error': routing_prediction.prediction_error,
                'confidence': routing_prediction.confidence
            }
            result['gates'] = gates.tolist()

        # 2) Basal ganglia processing (if enabled and inputs provided)
        bg_output = None
        if self.enable_bg and self.basal_ganglia is not None:
            if oscillator_state is not None:
                # Get cortical input from oscillator
                cortical_input = oscillator_state.to_6d_vector()

                # Get neuromodulator levels
                dopamine = 0.5
                urgency = 0.5
                if neuromod_levels is not None:
                    dopamine = neuromod_levels.dopamine
                    urgency = neuromod_levels.norepinephrine

                # Step basal ganglia
                bg_output = self.basal_ganglia.step(cortical_input, dopamine, urgency)
                self._last_bg_output = bg_output

                # Learn from TD error if provided
                if td_error is not None:
                    self.basal_ganglia.update_weights(td_error)

                result['bg_output'] = bg_output.to_dict()
                result['bg_action'] = bg_output.selected_action
                result['bg_action_name'] = self.basal_ganglia.get_action_name(bg_output.selected_action)
                result['bg_gates'] = bg_output.action_gates.tolist()

        # 3) Cortical feedback processing
        cortical_feedback = None
        if self.enable_cortex and self.cortex is not None:
            # Prepare thalamic output dict for cortex
            cortex_input = {
                'PE': self.thalamus.PE,
                'priors': self.thalamus.priors,
                'gates': gates
            }

            # Generate cortical feedback
            cortical_feedback = self.cortex.step(
                thalamic_output=cortex_input,
                goal=goal,
                oscillator_state=oscillator_state,
                neuromod_levels=neuromod_levels,
                actual_inputs=x
            )
            self._last_cortical_feedback = cortical_feedback

            # Apply feedback to thalamus
            feedback_applied = self.thalamus.apply_feedback(
                prior_delta=cortical_feedback.prior_modulation,
                trn_delta=cortical_feedback.trn_modulation,
                gain=cortical_feedback.gain_modulation
            )

            # Recompute gates after feedback
            gates = self._compute_gates(ctx)

            # Add cortical info to result
            result['cortical_feedback'] = cortical_feedback.to_dict()
            result['cortical_attention'] = cortical_feedback.attention_weights.tolist()
            result['feedback_applied'] = feedback_applied

        if not self.enable_hc:
            # Apply BG modulation to gates if available
            if bg_output is not None:
                gates = self.basal_ganglia.modulate_thalamic_gates(
                    gates, bg_output, self.bg_modulation_strength
                )
                result['final_gates'] = gates.tolist()
            self.timestep += 1
            return result

        # 3) Hippocampal processing
        state = self._pack_state()

        # Compute average prediction error as novelty signal
        avg_pe = np.mean([self.thalamus.PE[m] for m in self.thalamus.modalities])

        # Hippocampal step
        hc_out = self.hippocampus.step(
            state=state,
            context=ctx,
            gates=gates,
            prediction_error=avg_pe,
            encode=encode_memory
        )

        # 4) Use memory-biased gates for routing
        memory_biased_gates = hc_out['memory_biased_gates']

        # Optionally blend CA3 bias
        ca3_bias = hc_out['ca3_bias']
        # Softmax over CA3 bias for gate adjustment
        ca3_bias_scaled = ca3_bias / (np.max(np.abs(ca3_bias)) + 1e-10)
        ca3_gates = np.exp(ca3_bias_scaled) / np.sum(np.exp(ca3_bias_scaled))

        # 5) Final gates: blend thalamic, memory, CA3, and BG
        if bg_output is not None:
            # With BG: reduce weight of other components
            final_gates = (
                0.35 * gates +
                0.2 * memory_biased_gates +
                0.15 * ca3_gates +
                0.3 * self.basal_ganglia.modulate_thalamic_gates(
                    np.ones(len(gates)) / len(gates),  # uniform base
                    bg_output,
                    modulation_strength=1.0  # full BG modulation
                )
            )
        else:
            # Without BG: original formula
            final_gates = (
                0.5 * gates +
                0.3 * memory_biased_gates +
                0.2 * ca3_gates
            )
        final_gates = final_gates / np.sum(final_gates)

        # 6) Update result with hippocampal info
        result.update({
            'hippocampal_output': hc_out,
            'memory_biased_gates': memory_biased_gates,
            'ca3_gates': ca3_gates,
            'final_gates': final_gates,
            'num_memories': hc_out['num_memories'],
            'memory_encoded': hc_out['encoded']
        })

        self.timestep += 1
        return result

    def reset(self):
        """Reset system state (keep memories and learned weights)."""
        self.thalamus.reset_state()
        self.timestep = 0
        if self.hippocampus is not None:
            self.hippocampus.reset()
        if self.basal_ganglia is not None:
            self.basal_ganglia.reset()
            self._last_bg_output = None
        if self.cortex is not None:
            self.cortex.reset()
            self._last_cortical_feedback = None
        if self.predictive_router is not None:
            self.predictive_router.reset()
            self._last_routing_prediction = None
        if self._multi_band_osc is not None:
            self._multi_band_osc.reset()
            self._last_multi_band_state = None

    def clear_memories(self):
        """Clear all episodic memories."""
        if self.hippocampus is not None:
            self.hippocampus.clear_memories()

    def get_state(self) -> Dict:
        """Get complete system state."""
        state = {
            'timestep': self.timestep,
            'thalamic': self.thalamus.get_adaptive_state()
        }

        if self.enable_hc and self.hippocampus is not None:
            state['hippocampal'] = self.hippocampus.get_state()

        if self.enable_bg and self.basal_ganglia is not None:
            state['basal_ganglia'] = self.basal_ganglia.get_statistics()
            if self._last_bg_output is not None:
                state['last_bg_output'] = self._last_bg_output.to_dict()

        if self.enable_cortex and self.cortex is not None:
            state['cortical'] = self.cortex.get_statistics()
            if self._last_cortical_feedback is not None:
                state['last_cortical_feedback'] = self._last_cortical_feedback.to_dict()

        if self.enable_predictive and self.predictive_router is not None:
            state['predictive_routing'] = self.predictive_router.get_metrics()
            if self._last_routing_prediction is not None:
                state['last_routing_prediction'] = {
                    'blended_gates': self._last_routing_prediction.blended_gates.tolist(),
                    'confidence': self._last_routing_prediction.confidence,
                    'prediction_error': self._last_routing_prediction.prediction_error
                }

        if self.enable_multi_band and self._multi_band_osc is not None:
            state['multi_band'] = self._multi_band_osc.get_statistics()
            if self._last_multi_band_state is not None:
                state['last_multi_band_state'] = {
                    'theta_power': self._last_multi_band_state.theta.power,
                    'alpha_power': self._last_multi_band_state.alpha.power,
                    'gamma_power': self._last_multi_band_state.gamma.power,
                    'pac_theta_alpha': self._last_multi_band_state.pac_theta_alpha,
                    'pac_alpha_gamma': self._last_multi_band_state.pac_alpha_gamma,
                    'dominant_band': self._last_multi_band_state.dominant_band.value
                }

        return state

    def set_hc_enabled(self, enabled: bool):
        """Enable or disable hippocampus."""
        self.enable_hc = enabled

    def set_bg_enabled(self, enabled: bool):
        """Enable or disable basal ganglia."""
        self.enable_bg = enabled

    def get_bg_state_description(self) -> str:
        """Get human-readable BG state description."""
        if self.basal_ganglia is not None and self._last_bg_output is not None:
            return self.basal_ganglia.get_state_description(self._last_bg_output)
        return "BG not active"

    def get_last_bg_output(self) -> Optional[BasalGangliaOutput]:
        """Get the last BG output."""
        return self._last_bg_output

    def set_cortex_enabled(self, enabled: bool):
        """Enable or disable cortical feedback."""
        self.enable_cortex = enabled

    def get_cortex_state_description(self) -> str:
        """Get human-readable cortex state description."""
        if self.cortex is not None and self._last_cortical_feedback is not None:
            attention = self._last_cortical_feedback.attention_weights
            top_idx = np.argmax(attention)
            modality_order = list(self.thalamus.modalities)
            top_modality = modality_order[top_idx] if top_idx < len(modality_order) else f"modality_{top_idx}"

            return (
                f"Attention: {top_modality} ({attention[top_idx]:.2f}), "
                f"Gain: {self._last_cortical_feedback.gain_modulation:.2f}, "
                f"Prior mod: {np.sum(np.abs(self._last_cortical_feedback.prior_modulation)):.3f}"
            )
        return "Cortex not active"

    def get_last_cortical_feedback(self) -> Optional[CorticalFeedback]:
        """Get the last cortical feedback."""
        return self._last_cortical_feedback

    def update_cortex_from_reward(
        self,
        reward: float,
        goal: np.ndarray,
        oscillator_state: Optional['TripleOscillatorState'] = None
    ):
        """
        Update cortical attention weights based on reward.

        Call this after receiving outcome feedback to improve
        goal-driven attention learning.

        Args:
            reward: Reward signal (+1 success, -1 failure)
            goal: Goal that was used
            oscillator_state: Oscillator state that was used
        """
        if self.cortex is not None:
            self.cortex.update_from_reward(reward, goal, oscillator_state)

    def set_predictive_enabled(self, enabled: bool):
        """Enable or disable predictive routing."""
        self.enable_predictive = enabled

    def get_predictive_state_description(self) -> str:
        """Get human-readable predictive routing state description."""
        if self.predictive_router is not None and self._last_routing_prediction is not None:
            pred = self._last_routing_prediction
            metrics = self.predictive_router.get_metrics()
            return (
                f"Confidence: {pred.confidence:.2f}, "
                f"PE: {pred.prediction_error:.4f}, "
                f"Patterns: {metrics['temporal_patterns_used']}, "
                f"Max delta: {np.max(np.abs(pred.gate_deltas)):.3f}"
            )
        return "Predictive routing not active"

    def get_last_routing_prediction(self) -> Optional[RoutingPrediction]:
        """Get the last routing prediction."""
        return self._last_routing_prediction

    def learn_predictive_routing(
        self,
        v_actual: Optional[Dict[str, np.ndarray]] = None,
        v_input: Optional[Dict[str, np.ndarray]] = None
    ):
        """
        Trigger learning update for predictive router.

        Call this after step() to update forward models based on
        actual vs predicted outcomes.

        Args:
            v_actual: Actual latent states (if None, uses current thalamic states)
            v_input: Input latents used for prediction (if None, uses current)
        """
        if self.predictive_router is not None:
            if v_actual is None:
                v_actual = {m: self.thalamus.v[m].copy() for m in self.thalamus.modalities}
            if v_input is None:
                v_input = v_actual
            self.predictive_router.learn(v_actual, v_input)

    # =========================================================================
    # Multi-Band Oscillator Integration
    # =========================================================================

    def step_with_multi_band(
        self,
        x: Dict[str, np.ndarray],
        ctx: Optional[np.ndarray] = None,
        hazard: Optional[Dict[str, float]] = None,
        reward: Optional[Dict[str, float]] = None,
        adapt: bool = True,
        encode_memory: bool = True,
        external_input: Optional[Dict[str, float]] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        td_error: Optional[float] = None,
        goal: Optional[np.ndarray] = None,
        band_weights: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Step with integrated multi-band oscillator.

        Uses the multi-band oscillator for enhanced temporal dynamics and
        automatic oscillator_state generation from band states.

        Args:
            x: Modality inputs
            ctx: Context vector
            hazard: Hazard signals
            reward: Reward signals
            adapt: Whether to adapt parameters
            encode_memory: Whether to encode to hippocampus
            external_input: External input for oscillator (advance/explore/correct)
            neuromod_levels: NeuromodulatorLevels for dopamine/urgency
            td_error: TD error for BG learning
            goal: Goal/task encoding for cortical attention
            band_weights: Optional band weights {'theta', 'alpha', 'gamma'}

        Returns:
            Dict with all outputs plus multi-band state
        """
        if not self.enable_multi_band or self._multi_band_osc is None:
            # Fall back to standard step without multi-band
            return self.step(
                x=x, ctx=ctx, hazard=hazard, reward=reward,
                adapt=adapt, encode_memory=encode_memory,
                oscillator_state=None, neuromod_levels=neuromod_levels,
                td_error=td_error, goal=goal
            )

        # Step the multi-band oscillator
        multi_band_state = self._multi_band_osc.step(
            external_input=external_input,
            dt=1.0,
            band_weights=band_weights
        )
        self._last_multi_band_state = multi_band_state

        # Get legacy oscillator state for compatibility with BG and cortex
        legacy_state = multi_band_state.to_legacy_state()

        # Call standard step with oscillator state
        result = self.step(
            x=x, ctx=ctx, hazard=hazard, reward=reward,
            adapt=adapt, encode_memory=encode_memory,
            oscillator_state=legacy_state,
            neuromod_levels=neuromod_levels,
            td_error=td_error, goal=goal
        )

        # Add multi-band info to result
        result['multi_band'] = {
            'theta_power': multi_band_state.theta.power,
            'alpha_power': multi_band_state.alpha.power,
            'gamma_power': multi_band_state.gamma.power,
            'pac_theta_alpha': multi_band_state.pac_theta_alpha,
            'pac_alpha_gamma': multi_band_state.pac_alpha_gamma,
            'dominant_band': multi_band_state.dominant_band.value,
            'beat_index': multi_band_state.beat_index
        }

        return result

    def set_multi_band_enabled(self, enabled: bool):
        """Enable or disable multi-band oscillator."""
        self.enable_multi_band = enabled

    def get_multi_band_oscillator(self) -> Optional['MultiBandOscillator']:
        """Get the multi-band oscillator instance."""
        return self._multi_band_osc

    def get_last_multi_band_state(self) -> Optional['MultiBandState']:
        """Get the last multi-band state."""
        return self._last_multi_band_state

    def get_multi_band_state_description(self) -> str:
        """Get human-readable multi-band state description."""
        if self._multi_band_osc is not None and self._last_multi_band_state is not None:
            state = self._last_multi_band_state
            return (
                f"Band powers: θ={state.theta.power:.2f}, α={state.alpha.power:.2f}, γ={state.gamma.power:.2f} | "
                f"PAC: θ→α={state.pac_theta_alpha:.2f}, α→γ={state.pac_alpha_gamma:.2f} | "
                f"Dominant: {state.dominant_band.value}"
            )
        return "Multi-band not active"

"""
Meta-Router for Self-Reflective Learning

Integrates conversation traces with thalamic routing to create a
self-aware cognitive architecture that learns from its own execution history.

Flow:
1. Parse conversation logs → Extract features
2. Encode as multi-modal vectors (tool_trace, temporal, error, success)
3. Feed into thalamic routing alongside vision/audio/etc
4. High error signals trigger hippocampal encoding
5. Similar future situations retrieve past failures
6. Basal ganglia learns which actions lead to success/failure
7. BG selects action mode: ADVANCE (goal-directed), EXPLORE (alternatives), CORRECT (repair)
8. Cortical feedback provides top-down attention based on extracted goals

This creates a **meta-cognitive loop** where the system observes and
optimizes its own problem-solving patterns.

Integration with ActionPotentialOscillator and NeuromodulationSystem:
    from core.action_potential_oscillator import ActionPotentialOscillator
    from core.neuromodulation import NeuromodulationSystem

    osc = ActionPotentialOscillator()
    neuromod = NeuromodulationSystem()
    router = MetaRouter(enable_basal_ganglia=True, enable_cortex=True)

    # Process trace with BG-modulated routing and cortical feedback
    result = router.process_trace(
        trace,
        oscillator_state=osc.state,
        neuromod_levels=neuromod.levels,
        td_error=neuromod.reward_prediction_errors[-1] if neuromod.reward_prediction_errors else None,
        goal_context=goal_vector  # Optional external goal
    )
"""

import numpy as np
from typing import Dict, List, Optional, TYPE_CHECKING
from core.thalamo_hippocampal_system import ThalamoHippocampalSystem
from core.conversation_trace_encoder import ConversationTrace, ConversationTraceEncoder, load_session_logs
from core.modality_prediction_errors import ModalityPredictionErrors

if TYPE_CHECKING:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.neuromodulation import NeuromodulatorLevels


class MetaRouter:
    """
    Meta-cognitive routing system that learns from conversation traces.

    Extends thalamo-hippocampal system with conversation trace inputs,
    enabling self-reflective learning from past agentic interactions.
    """

    def __init__(
        self,
        # Base system parameters
        enable_hippocampus: bool = True,
        enable_meta_learning: bool = True,
        enable_basal_ganglia: bool = True,
        enable_cortex: bool = True,
        # Trace encoder dimensions
        trace_dim: int = 64,
        temporal_dim: int = 32,
        error_dim: int = 16,
        success_dim: int = 8,
        # Goal encoding dimension
        goal_dim: int = 32,
        # Hippocampal parameters for meta-learning
        novelty_threshold_meta: float = 0.7,  # Higher threshold for errors
        memory_influence_meta: float = 0.5,   # Stronger influence from past failures
        # Basal ganglia parameters
        bg_temperature: float = 0.5,          # BG softmax temperature
        bg_learning_rate: float = 0.01,       # BG TD learning rate
        bg_modulation_strength: float = 0.3,  # BG influence on thalamic gates
        # Cortical feedback parameters
        cortex_alpha_goal: float = 0.4,       # Goal-driven attention weight
        cortex_beta_osc: float = 0.3,         # Oscillator attention weight
        cortex_gamma_pe: float = 0.3,         # PE-driven attention weight
        # Learning parameters
        error_penalty: float = -1.0,   # Negative reward for high errors
        success_reward: float = 1.0,   # Positive reward for success
        # Phase 2: Per-modality prediction errors
        enable_per_modality_pes: bool = True,
        seed: int = 42
    ):
        """
        Initialize meta-router.

        Args:
            enable_hippocampus: Enable episodic memory
            enable_meta_learning: Enable learning from conversation traces
            enable_basal_ganglia: Enable BG action selection
            enable_cortex: Enable cortical feedback loops
            trace_dim: Tool trace vector dimension
            temporal_dim: Temporal pattern vector dimension
            error_dim: Error signal vector dimension
            success_dim: Success signal vector dimension
            goal_dim: Dimension of goal encoding extracted from traces
            novelty_threshold_meta: PE threshold for encoding failures
            memory_influence_meta: Weight of past experience in routing
            bg_temperature: BG softmax temperature for action selection
            bg_learning_rate: BG TD learning rate
            bg_modulation_strength: How strongly BG modulates routing
            cortex_alpha_goal: Cortex attention weight for goal-driven
            cortex_beta_osc: Cortex attention weight for oscillator
            cortex_gamma_pe: Cortex attention weight for PE-driven
            error_penalty: Reward signal for high error traces
            success_reward: Reward signal for successful traces
            seed: Random seed
        """
        self.enable_meta = enable_meta_learning

        # Initialize conversation trace encoder
        self.encoder = ConversationTraceEncoder(
            trace_dim=trace_dim,
            temporal_dim=temporal_dim,
            error_dim=error_dim,
            success_dim=success_dim
        )

        # Extended modalities including conversation traces
        modalities = [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
        ]

        dimensions = {
            'vision': 128,
            'audio': 64,
            'touch': 32,
            'taste': 16,
            'vestibular': 16,
            'threat': 8,
            'tool_trace': trace_dim,
            'temporal_pattern': temporal_dim,
            'error_signal': error_dim,
            'success_signal': success_dim
        }

        # Default tau (time constants) for all modalities
        tau = {
            'vision': 50.0,
            'audio': 40.0,
            'touch': 30.0,
            'taste': 30.0,
            'vestibular': 30.0,
            'threat': 20.0,  # Fast response
            'tool_trace': 40.0,
            'temporal_pattern': 35.0,
            'error_signal': 25.0,  # Fast error detection
            'success_signal': 30.0
        }

        # Default priors
        priors = {
            'vision': 0.2,
            'audio': 0.15,
            'touch': 0.1,
            'taste': 0.05,
            'vestibular': 0.1,
            'threat': 0.15,
            'tool_trace': 0.1,
            'temporal_pattern': 0.05,
            'error_signal': 0.05,
            'success_signal': 0.05
        }

        # Initialize thalamo-hippocampal system with extended modalities, BG, and cortex
        self.thalamo_system = ThalamoHippocampalSystem(
            modalities=modalities,
            dimensions=dimensions,
            tau=tau,
            priors=priors,
            enable_hippocampus=enable_hippocampus,
            novelty_threshold=novelty_threshold_meta,
            memory_influence=memory_influence_meta,
            enable_basal_ganglia=enable_basal_ganglia,
            bg_temperature=bg_temperature,
            bg_learning_rate=bg_learning_rate,
            bg_modulation_strength=bg_modulation_strength,
            enable_cortex=enable_cortex,
            goal_dim=goal_dim,
            cortex_alpha_goal=cortex_alpha_goal,
            cortex_beta_osc=cortex_beta_osc,
            cortex_gamma_pe=cortex_gamma_pe,
            seed=seed
        )

        self.enable_bg = enable_basal_ganglia
        self.enable_cortex = enable_cortex
        self.goal_dim = goal_dim
        self.rng = np.random.default_rng(seed)

        self.error_penalty = error_penalty
        self.success_reward = success_reward

        # === Phase 2: Per-Modality Prediction Errors ===
        self.enable_per_modality_pes = enable_per_modality_pes

        if enable_per_modality_pes:
            # Initialize per-modality PE tracker
            self.modality_pe_tracker = ModalityPredictionErrors(
                modalities=dimensions,
                learning_rates={
                    'vision': 0.05,
                    'audio': 0.05,
                    'touch': 0.1,
                    'taste': 0.1,
                    'vestibular': 0.1,
                    'threat': 0.15,         # Fast learning for safety
                    'tool_trace': 0.1,      # Fast learning for task patterns
                    'temporal_pattern': 0.05,
                    'error_signal': 0.15,   # Very fast - errors are important!
                    'success_signal': 0.08
                },
                history_length=100
            )
        else:
            self.modality_pe_tracker = None

        # Statistics
        self.traces_processed = 0
        self.failures_encoded = 0
        self.successes_encoded = 0

    def _extract_goal(self, trace: ConversationTrace) -> np.ndarray:
        """
        Extract a goal encoding from a conversation trace.

        The goal vector captures the task intent from the trace features,
        encoding what the system is trying to accomplish.

        Args:
            trace: Conversation trace to extract goal from

        Returns:
            Goal vector [goal_dim]
        """
        features = trace.get_features()
        goal = np.zeros(self.goal_dim)

        # Encode tool usage pattern into goal (which tools → what task type)
        tool_counts = features.get('tool_counts', {})
        tool_idx = 0
        for tool, count in list(tool_counts.items())[:8]:  # Top 8 tools
            if tool_idx < self.goal_dim // 4:
                goal[tool_idx] = np.tanh(count / 5.0)  # Normalize
                tool_idx += 1

        # Encode task complexity
        complexity_idx = self.goal_dim // 4
        total_tool_calls = features.get('tool_call_count', 0)
        goal[complexity_idx] = np.tanh(total_tool_calls / 20.0)

        # Encode error context (what went wrong)
        error_idx = self.goal_dim // 4 + 1
        error_count = features.get('error_count', 0)
        goal[error_idx] = np.tanh(error_count / 5.0)

        # Encode success/failure as goal outcome signal
        success_idx = self.goal_dim // 2
        goal[success_idx] = 1.0 if features.get('success', False) else -1.0

        # Encode temporal patterns
        timing_idx = self.goal_dim // 2 + 1
        mean_gap = features.get('mean_gap', 0)
        goal[timing_idx] = np.tanh(mean_gap / 1000.0)  # Normalize milliseconds

        # Encode final state (pending vs completed)
        state_idx = self.goal_dim - 4
        final_state = features.get('final_state', 'unknown')
        if final_state == 'completed':
            goal[state_idx] = 1.0
        elif final_state == 'error':
            goal[state_idx + 1] = 1.0
        elif final_state == 'pending':
            goal[state_idx + 2] = 1.0

        # Add some noise for exploration
        goal += self.rng.normal(0, 0.01, self.goal_dim)

        return goal

    def process_trace(
        self,
        trace: ConversationTrace,
        sensory_context: Optional[Dict[str, np.ndarray]] = None,
        adapt: bool = True,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        td_error: Optional[float] = None,
        goal_context: Optional[np.ndarray] = None
    ) -> Dict:
        """
        Process a conversation trace through the routing system.

        Args:
            trace: Parsed conversation trace
            sensory_context: Optional sensory inputs (vision, audio, etc.)
            adapt: Whether to adapt and learn
            oscillator_state: TripleOscillatorState for BG cortical input
            neuromod_levels: NeuromodulatorLevels for dopamine/urgency
            td_error: TD error for BG learning (computed from trace if None)
            goal_context: Optional explicit goal vector (extracted from trace if None)

        Returns:
            Dict with routing output, meta-learning info, BG action, and cortical feedback
        """
        # Encode conversation trace
        encoded = self.encoder.encode_full(trace)

        # Prepare input dictionary
        x = {
            'tool_trace': encoded['tool_trace'],
            'temporal_pattern': encoded['temporal_pattern'],
            'error_signal': encoded['error_signal'],
            'success_signal': encoded['success_signal']
        }

        # Add sensory context if provided, otherwise use zeros
        if sensory_context:
            x.update(sensory_context)
        else:
            x['vision'] = np.zeros(128)
            x['audio'] = np.zeros(64)
            x['touch'] = np.zeros(32)
            x['taste'] = np.zeros(16)
            x['vestibular'] = np.zeros(16)
            x['threat'] = np.zeros(8)

        # Compute reward signal based on trace outcome
        features = trace.get_features()
        success = features['success']
        error_count = features['error_count']

        # High errors trigger threat signal
        if error_count > 5:
            x['threat'] = np.ones(8) * min(error_count / 10.0, 1.0)

        # Reward/hazard signals
        reward = {}
        hazard = {}

        if not success:
            # Failure: negative reward, hazard on tool_trace
            reward['tool_trace'] = self.error_penalty
            hazard['error_signal'] = 1.0
            self.failures_encoded += 1
        else:
            # Success: positive reward
            reward['success_signal'] = self.success_reward
            self.successes_encoded += 1

        # === Phase 2: Compute per-modality prediction errors ===
        if self.enable_per_modality_pes and adapt:
            # Update PE tracker and get PEs
            per_modality_pes = self.modality_pe_tracker.update_predictions(x)
        else:
            per_modality_pes = None

        # Compute TD error from trace if not provided and BG enabled
        computed_td_error = td_error
        if computed_td_error is None and self.enable_bg and adapt:
            # TD error based on success/failure
            # Expected success: 0.5 (neutral), actual: 1.0 or 0.0
            expected = 0.5
            actual = 1.0 if success else 0.0
            computed_td_error = actual - expected

        # Extract goal from trace if not provided and cortex enabled
        goal = goal_context
        if goal is None and self.enable_cortex:
            goal = self._extract_goal(trace)

        # Process through thalamo-hippocampal system with BG and cortex
        out = self.thalamo_system.step(
            x,
            hazard=hazard if adapt else None,
            reward=reward if adapt else None,
            adapt=adapt,
            encode_memory=adapt,  # Only encode if adapting
            oscillator_state=oscillator_state,
            neuromod_levels=neuromod_levels,
            td_error=computed_td_error if adapt else None,
            goal=goal
        )

        # Add trace info to output
        out['trace_features'] = features
        out['trace_encoded'] = encoded
        out['error_count'] = error_count
        out['success'] = success
        if goal is not None:
            out['goal'] = goal.tolist()

        # Add per-modality PEs (Phase 2)
        if per_modality_pes is not None:
            out['per_modality_pes'] = per_modality_pes
            # Identify surprising modalities
            out['surprising_modalities'] = self.modality_pe_tracker.identify_surprising_modalities(
                threshold=0.5, window=10
            )

        self.traces_processed += 1

        return out

    def batch_train(
        self,
        traces: List[ConversationTrace],
        verbose: bool = True
    ):
        """
        Train on a batch of conversation traces.

        Args:
            traces: List of conversation traces
            verbose: Print progress
        """
        if verbose:
            print(f"Training on {len(traces)} conversation traces...")

        for i, trace in enumerate(traces):
            out = self.process_trace(trace, adapt=True)

            if verbose and (i + 1) % 5 == 0:
                print(f"  Processed {i+1}/{len(traces)} traces")
                print(f"    Memories: {out.get('num_memories', 0)}")
                print(f"    Failures encoded: {self.failures_encoded}")
                print(f"    Successes encoded: {self.successes_encoded}")

        if verbose:
            print(f"\nTraining complete!")
            print(f"  Total traces: {self.traces_processed}")
            print(f"  Failures: {self.failures_encoded}")
            print(f"  Successes: {self.successes_encoded}")
            print(f"  Episodic memories: {self.thalamo_system.hippocampus.get_state()['num_memories']}")

    def predict_outcome(
        self,
        trace: ConversationTrace,
        sensory_context: Optional[Dict[str, np.ndarray]] = None,
        oscillator_state: Optional['TripleOscillatorState'] = None,
        neuromod_levels: Optional['NeuromodulatorLevels'] = None,
        goal_context: Optional[np.ndarray] = None
    ) -> Dict:
        """
        Predict outcome for a new trace based on past experience.

        Args:
            trace: New conversation trace
            sensory_context: Optional sensory inputs
            oscillator_state: TripleOscillatorState for BG
            neuromod_levels: NeuromodulatorLevels for BG
            goal_context: Optional explicit goal vector

        Returns:
            Dict with prediction, BG action recommendation, cortical attention, and similar cases
        """
        # Process without adaptation (inference mode)
        out = self.process_trace(
            trace, sensory_context, adapt=False,
            oscillator_state=oscillator_state,
            neuromod_levels=neuromod_levels,
            goal_context=goal_context
        )

        # Check if hippocampus retrieved similar failures
        hc_out = out.get('hippocampal_output', {})
        memory_bias = hc_out.get('memory_biased_gates', np.zeros(10))

        # Prediction: if error_signal gate is high, predict failure
        final_gates = out.get('final_gates', np.zeros(10))
        error_gate_idx = 8  # error_signal is 9th modality (index 8)

        if error_gate_idx < len(final_gates):
            error_gate_strength = final_gates[error_gate_idx]
            predicted_failure = error_gate_strength > 0.3

            result = {
                'predicted_failure': predicted_failure,
                'error_gate_strength': error_gate_strength,
                'final_gates': final_gates,
                'memory_biased_gates': memory_bias,
                'similar_cases_retrieved': hc_out.get('num_memories', 0) > 0
            }

            # Add BG action recommendation
            if 'bg_action_name' in out:
                result['bg_recommended_action'] = out['bg_action_name']
                result['bg_gates'] = out.get('bg_gates', [])
                result['bg_confidence'] = out.get('bg_output', {}).get('selection_confidence', 0.0)

            # Add cortical attention info
            if 'cortical_attention' in out:
                result['cortical_attention'] = out['cortical_attention']
                result['cortical_feedback'] = out.get('cortical_feedback', {})

            return result

        return {'predicted_failure': False, 'error_gate_strength': 0.0}

    def load_and_train(
        self,
        log_dir: str,
        limit: Optional[int] = None,
        verbose: bool = True
    ):
        """
        Load session logs and train.

        Args:
            log_dir: Path to sessions directory
            limit: Maximum number of logs to process
            verbose: Print progress
        """
        traces = load_session_logs(log_dir, limit=limit)

        if verbose:
            print(f"Loaded {len(traces)} conversation traces from {log_dir}")

        self.batch_train(traces, verbose=verbose)

    def get_state(self) -> Dict:
        """Get meta-router state."""
        state = {
            'traces_processed': self.traces_processed,
            'failures_encoded': self.failures_encoded,
            'successes_encoded': self.successes_encoded,
            'enable_cortex': self.enable_cortex,
            'goal_dim': self.goal_dim,
            'thalamo_hippocampal_state': self.thalamo_system.get_state()
        }

        # Add per-modality PE statistics (Phase 2)
        if self.enable_per_modality_pes and self.modality_pe_tracker is not None:
            state['per_modality_pes'] = {
                'all_statistics': self.modality_pe_tracker.get_all_statistics(),
                'pe_ranking': self.modality_pe_tracker.get_pe_ranking(window=10),
                'surprising_modalities': self.modality_pe_tracker.identify_surprising_modalities(
                    threshold=0.5, window=10
                )
            }

        return state

    def reset(self):
        """Reset system but keep learned memories."""
        self.thalamo_system.reset()
        # Don't reset statistics or memories - keep learned patterns

    def get_bg_state_description(self) -> str:
        """Get human-readable BG state description."""
        return self.thalamo_system.get_bg_state_description()

    def get_last_bg_output(self):
        """Get the last BG output."""
        return self.thalamo_system.get_last_bg_output()

    def set_bg_enabled(self, enabled: bool):
        """Enable or disable basal ganglia."""
        self.enable_bg = enabled
        self.thalamo_system.set_bg_enabled(enabled)

    def set_cortex_enabled(self, enabled: bool):
        """Enable or disable cortical feedback."""
        self.enable_cortex = enabled
        self.thalamo_system.set_cortex_enabled(enabled)

    def get_cortex_state_description(self) -> str:
        """Get human-readable cortex state description."""
        return self.thalamo_system.get_cortex_state_description()

    def get_last_cortical_feedback(self):
        """Get the last cortical feedback."""
        return self.thalamo_system.get_last_cortical_feedback()

    def update_cortex_from_reward(
        self,
        reward: float,
        goal: np.ndarray,
        oscillator_state: Optional['TripleOscillatorState'] = None
    ):
        """
        Update cortical attention weights based on reward.

        Args:
            reward: Reward signal (+1 success, -1 failure)
            goal: Goal that was used
            oscillator_state: Oscillator state that was used
        """
        self.thalamo_system.update_cortex_from_reward(reward, goal, oscillator_state)

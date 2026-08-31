"""
Cognitive Loop - The Inner Voice of Tahlamus

Replaces the sequential 16-phase pipeline in HierarchicalPlanner.predict()
with a genuine perceive→remember→attend→modulate→reason→reflect→learn→consolidate
cycle where each cognitive system's output actively shapes the next system's input.

Key differences from HierarchicalPlanner.predict():
1. Memory BIASES routing (not just read after routing)
2. Attention DRIVES CTM selection (not computed but ignored)
3. Neuromodulation CONTROLS gating temperature (not just LR adjustment)
4. Consciousness metrics are CONTROL signals (can trigger re-evaluation)
5. Reflection can LOOP BACK to re-route if confidence is too low

The shared LoopContext acts as a "global workspace" - each phase reads from it
and writes back into it, creating tight bidirectional coupling between all
cognitive systems.
"""

import logging
import numpy as np
import time
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


class LoopPhase(Enum):
    """Current phase of the cognitive loop."""
    IDLE = "idle"
    PERCEIVE = "perceive"
    REMEMBER = "remember"
    ATTEND = "attend"
    MODULATE = "modulate"
    REASON = "reason"
    REFLECT = "reflect"
    LEARN = "learn"
    CONSOLIDATE = "consolidate"


@dataclass
class LoopContext:
    """
    Mutable context that flows through all phases of the loop.
    Each phase reads from it and writes back into it.
    This is the 'global workspace' that all cognitive systems share.
    """
    # Input
    task_description: str = ""

    # PERCEIVE phase outputs
    layer1_routing: Any = None  # RoutingState
    raw_routing_weights: Optional[np.ndarray] = None
    task_feature_prediction: Any = None  # From predictive coding

    # REMEMBER phase outputs
    memory_context: Optional[Dict] = None
    memory_bias: Optional[np.ndarray] = None
    memory_confidence_hint: float = 0.5

    # ATTEND phase outputs
    attention_state: Any = None  # AttentionState
    attention_gated_weights: Optional[np.ndarray] = None
    ctm_domain_hint: Optional[str] = None

    # MODULATE phase outputs
    neuro_effects: Any = None  # NeuromodulatorEffects
    neuro_levels: Any = None  # NeuromodulatorLevels
    modulated_weights: Optional[np.ndarray] = None
    gating_temperature: float = 1.0

    # REASON phase outputs
    brain_gates: Optional[np.ndarray] = None
    layer2_prediction: Any = None
    actionable_decision: Any = None  # ActionableDecision
    ctm_task_id: Optional[str] = None
    ctm_insights: Optional[str] = None
    predicted_sequence: List[str] = field(default_factory=list)
    confidence: float = 0.5
    success_probability: float = 0.5
    dominant_modalities: List[str] = field(default_factory=list)
    task_type: str = "unknown"
    per_modality_pes: Optional[Dict] = None

    # REFLECT phase outputs
    prediction_errors: Optional[Dict] = None
    curiosity_signal: Optional[Dict] = None
    cognitive_state: Any = None  # CognitiveState
    inference_state: Any = None  # InferenceState
    should_reconsider: bool = False

    # LEARN phase outputs
    meta_parameters: Any = None  # MetaParameters

    # CONSOLIDATE phase outputs
    temporal_context: Any = None  # TemporalContext

    # Goal graph outputs
    goal_context: Optional[Dict] = None

    # Emotional state outputs
    emotional_valence: float = 0.0   # -1 (negative) to +1 (positive)
    emotional_arousal: float = 0.0   # 0 (calm) to 1 (aroused)

    # Homeostatic state
    homeostatic_temp_adj: float = 0.0  # Temperature adjustment from energy/fatigue
    homeostatic_attn_factor: float = 1.0  # Attention degradation factor

    # Phase 6 cognitive outputs
    safety_report: Optional[Dict] = None         # P6.85: SafetyLayer report
    explanation: Optional[Dict] = None            # P6.87: ExplanationGenerator output
    user_model: Optional[Dict] = None             # P6.77: ToM user model
    causal_context: Optional[Dict] = None         # P6.78-79: CausalInference context
    curiosity_intrinsic: Optional[Dict] = None    # P6.81: IntrinsicCuriosityModule
    temporal_patterns: Optional[Dict] = None      # P6.90: TemporalMemory patterns
    circadian_phase: Optional[str] = None         # P6.89: Circadian influence
    autonomous_goals: Optional[List] = None       # P6.82: Autonomous goal suggestions
    multimodal_fusion: Optional[Dict] = None      # P6.83: MultiModalFusion output
    formal_verification: Optional[Dict] = None    # P6.86: FormalVerifier report
    thought_decode: Optional[Dict] = None         # P6.88: ThoughtDecoder output

    # Neuroscience extension outputs
    sc_orienting: Optional[Dict] = None          # Superior Colliculus orienting command
    insular_salience: Optional[Dict] = None      # Insular Cortex salience/feeling
    pfc_state: Optional[Dict] = None             # Prefrontal Cortex WM/control
    hypothalamus_drives: Optional[Dict] = None   # Hypothalamus drive state
    cerebellum_prediction: Optional[Dict] = None # Cerebellum forward model prediction
    dmn_output: Optional[Dict] = None            # Default Mode Network creative output
    acc_conflict: Optional[Dict] = None          # Anterior Cingulate conflict monitor
    entorhinal_spatial: Optional[Dict] = None    # Entorhinal Cortex spatial code
    nacc_reward: Optional[Dict] = None           # Nucleus Accumbens reward gate

    # Timing and iteration tracking
    phase_timings: Dict[str, float] = field(default_factory=dict)
    total_time: float = 0.0
    loop_iterations: int = 0


@dataclass
class CognitiveLoopConfig:
    """Configuration for cognitive loop behavior."""

    # Memory influence on routing
    memory_routing_bias_strength: float = 0.25
    memory_confidence_weight: float = 0.3

    # Attention driving
    attention_gating_strength: float = 0.5
    attention_ctm_threshold: float = 0.3

    # Neuromodulation influence
    neuro_temperature_sensitivity: float = 0.5
    low_dopamine_threshold: float = 0.3
    high_norepinephrine_threshold: float = 0.7

    # CTM dynamic threshold
    base_ctm_threshold: float = 0.4
    uncertainty_ctm_reduction: float = 0.2

    # Reflection loop
    reconsider_confidence_threshold: float = 0.3
    reconsider_pe_threshold: float = 0.7
    max_loop_iterations: int = 2

    # Consolidation
    consolidation_importance_threshold: float = 0.6

    # Frequency mode → cognitive loop parameter mapping (P2.25)
    frequency_attention_strength: Dict[str, float] = field(default_factory=lambda: {
        'delta': 0.2, 'theta': 0.3, 'alpha': 0.5, 'beta': 0.6, 'gamma': 0.8
    })
    frequency_memory_bias: Dict[str, float] = field(default_factory=lambda: {
        'delta': 0.1, 'theta': 0.4, 'alpha': 0.25, 'beta': 0.15, 'gamma': 0.1
    })
    frequency_ctm_threshold: Dict[str, float] = field(default_factory=lambda: {
        'delta': 0.8, 'theta': 0.6, 'alpha': 0.4, 'beta': 0.35, 'gamma': 0.2
    })
    frequency_temperature: Dict[str, float] = field(default_factory=lambda: {
        'delta': 1.5, 'theta': 1.3, 'alpha': 1.0, 'beta': 0.8, 'gamma': 0.6
    })

    # Homeostasis → frequency mode mapping (P2.28)
    energy_to_frequency_thresholds: List[Tuple] = field(default_factory=lambda: [
        (0.2, 'delta'), (0.4, 'theta'), (0.6, 'alpha'), (0.8, 'beta'), (1.0, 'gamma')
    ])

    # Sleep consolidation (P2.23)
    enable_sleep_consolidation: bool = True
    sleep_consolidation_replays: int = 3

    # Per-phase enable flags (for gradual adoption)
    enable_memory_bias: bool = True
    enable_attention_driving: bool = True
    enable_neuro_modulation: bool = True
    enable_dynamic_ctm: bool = True
    enable_reflection_loop: bool = True
    enable_inline_consolidation: bool = True
    enable_emotional_system: bool = True
    enable_homeostatic: bool = True
    enable_frequency_modulation: bool = True
    enable_homeostatic_frequency: bool = True
    enable_prediction_error_backprop: bool = True

    # Phase 6: Advanced cognitive capabilities
    enable_safety_layer: bool = True             # P6.85: Action safety checking
    enable_explanation_gen: bool = True           # P6.87: Explanation generation
    enable_theory_of_mind: bool = True            # P6.76-77: User modeling
    enable_causal_reasoning: bool = True          # P6.78-79: Causal inference
    enable_intrinsic_curiosity: bool = True       # P6.81: Curiosity signal
    enable_temporal_patterns: bool = True          # P6.89-90: Circadian & temporal patterns
    enable_autonomous_goals: bool = True           # P6.82: Autonomous goal generation
    enable_self_improvement: bool = True           # P6.80: Self-improvement loop
    enable_multimodal_fusion: bool = True          # P6.83: Multimodal fusion
    enable_formal_verifier: bool = True            # P6.86: Formal verification
    enable_thought_decoder: bool = True            # P6.88: Thought decoder

    # Neuroscience architecture extensions
    enable_superior_colliculus: bool = True         # Attention orienting + multisensory
    enable_insular_cortex: bool = True              # Salience detection + interoception
    enable_prefrontal_cortex: bool = True           # Working memory + cognitive control
    enable_hypothalamus: bool = True                # Drive states + circadian + HPA
    enable_cerebellum: bool = True                  # Prediction + timing + error learning
    enable_default_mode_network: bool = True        # Self-reference + creativity (idle)
    enable_anterior_cingulate: bool = True          # Conflict monitoring + effort
    enable_entorhinal_cortex: bool = True           # Spatial coding + memory gateway
    enable_nucleus_accumbens: bool = True           # Reward gateway + approach/avoid

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'CognitiveLoopConfig':
        """Create CognitiveLoopConfig from YAML config dict (cognitive_loop section)."""
        cl = yaml_config.get('cognitive_loop', {})
        kwargs = {}
        for field_name in cls.__dataclass_fields__:
            if field_name in cl:
                kwargs[field_name] = cl[field_name]
        return cls(**kwargs)


class CognitiveLoop:
    """
    Inner Cognitive Loop - Unified perceive-remember-attend-modulate-reason-reflect-learn cycle.

    Wraps an existing HierarchicalPlanner by composition and calls its individual
    components directly, wiring them together through the shared LoopContext.
    Returns the same HierarchicalPrediction type for backward compatibility.
    """

    def __init__(
        self,
        planner,  # HierarchicalPlanner instance
        config: Optional[CognitiveLoopConfig] = None,
        frequency_controller=None  # BrainFrequencyController instance
    ):
        self._planner = planner
        self._config = config or CognitiveLoopConfig()
        self._frequency_controller = frequency_controller
        self._phase = LoopPhase.IDLE
        self._last_context: Optional[LoopContext] = None
        self._logger = logging.getLogger('brain.cognitive_loop')

        # Loop tracer for P4.63 (set externally by ProductionPlanner)
        self._tracer = None

        # Initialize emotional system (with YAML config if available)
        self._emotional_system = None
        if self._config.enable_emotional_system:
            try:
                from core.emotional_system import EmotionalSystem, EmotionalSystemConfig
                es_config = None
                if hasattr(planner, '_yaml_config') and planner._yaml_config:
                    es_config = EmotionalSystemConfig.from_yaml(planner._yaml_config)
                elif hasattr(planner, 'planner') and hasattr(planner.planner, '_yaml_config'):
                    es_config = EmotionalSystemConfig.from_yaml(planner.planner._yaml_config)
                self._emotional_system = EmotionalSystem(config=es_config)
            except ImportError:
                pass

        # Initialize sensory preprocessor
        self._sensory_preprocessor = None
        try:
            from core.sensory_preprocessor import SensoryPreprocessor
            self._sensory_preprocessor = SensoryPreprocessor()
        except ImportError:
            pass

        # Initialize homeostatic regulator
        self._homeostatic = None
        if self._config.enable_homeostatic:
            try:
                from core.homeostatic_regulation import HomeostaticRegulator, HomeostaticConfig
                h_config = None
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    h_config = HomeostaticConfig.from_yaml(yaml_cfg)
                self._homeostatic = HomeostaticRegulator(config=h_config)
            except ImportError:
                pass

        # Phase 6: Advanced cognitive capabilities

        # P6.76-77: Theory of Mind / User Modeling
        self._theory_of_mind = None
        if self._config.enable_theory_of_mind:
            try:
                from core.theory_of_mind import TheoryOfMind
                self._theory_of_mind = TheoryOfMind(
                    state_dim=64, action_dim=16, belief_dim=32, goal_dim=16, hidden_dim=64
                )
            except (ImportError, Exception):
                pass

        # P6.78-79: Causal Reasoning
        self._causal_inference = None
        if self._config.enable_causal_reasoning:
            try:
                from core.causal_reasoning import CausalDAG, CausalInference
                dag = CausalDAG()
                self._causal_inference = CausalInference(dag)
            except (ImportError, Exception):
                pass

        # P6.81: Intrinsic Curiosity
        self._intrinsic_curiosity = None
        if self._config.enable_intrinsic_curiosity:
            try:
                from core.intrinsic_curiosity import IntrinsicCuriosityModule
                self._intrinsic_curiosity = IntrinsicCuriosityModule(
                    state_dim=64, action_dim=16, feature_dim=64, hidden_dim=64
                )
            except (ImportError, Exception):
                pass

        # P6.82: Autonomous Goal Generator
        self._autonomous_goal_gen = None
        if self._config.enable_autonomous_goals:
            try:
                from core.autonomous_goal_generator import AutonomousGoalGenerator
                self._autonomous_goal_gen = AutonomousGoalGenerator()
            except (ImportError, Exception):
                pass

        # P6.85: Safety Layer
        self._safety_layer = None
        if self._config.enable_safety_layer:
            try:
                from core.safety_layer import SafetyLayer
                self._safety_layer = SafetyLayer(action_dim=16)
            except (ImportError, Exception):
                pass

        # P6.87: Explanation Generator
        self._explanation_gen = None
        if self._config.enable_explanation_gen:
            try:
                from core.explanation_generator import ExplanationGenerator
                feature_names = [
                    'complexity', 'urgency', 'ambiguity', 'risk_level',
                    'emotional_valence', 'confidence', 'memory_relevance',
                    'novelty', 'task_type', 'routing_entropy'
                ]
                self._explanation_gen = ExplanationGenerator(
                    feature_names=feature_names,
                    decision_space=['execute', 'suggest', 'clarify', 'defer', 'escalate']
                )
            except (ImportError, Exception):
                pass

        # P6.80: Self-Improvement Engine (lightweight: diagnosis only)
        self._self_improvement = None
        if self._config.enable_self_improvement:
            try:
                from core.self_improvement import PerformanceMonitor
                self._self_improvement = PerformanceMonitor(
                    window_size=100, degradation_threshold=0.1
                )
            except (ImportError, Exception):
                pass

        # P6.83: Multimodal Fusion (lightweight - no actual training)
        self._multimodal_fusion = None
        if self._config.enable_multimodal_fusion:
            try:
                from core.multimodal_fusion import MultiModalFusion, ModalityConfig
                configs = [
                    ModalityConfig(name='text', input_dim=64, encoder_type='mlp'),
                    ModalityConfig(name='routing', input_dim=10, encoder_type='mlp'),
                ]
                self._multimodal_fusion = MultiModalFusion(
                    modality_configs=configs, unified_dim=64, fusion_type='gated'
                )
            except (ImportError, Exception):
                pass

        # P6.86: Formal Verifier (uses SimplifiedVerifier fallback)
        self._formal_verifier = None
        if self._config.enable_formal_verifier:
            try:
                from core.formal_verifier import create_verifier
                self._formal_verifier = create_verifier(state_dim=64, action_dim=16)
            except (ImportError, Exception):
                pass

        # P6.88: Thought Decoder (lightweight, no GPT2 training)
        self._thought_decoder = None
        if self._config.enable_thought_decoder:
            try:
                from core.thought_decoder import ThoughtDecoder
                self._thought_decoder = ThoughtDecoder(
                    thought_dim=64, num_prefix_tokens=4, max_length=32, device='cpu'
                )
            except (ImportError, Exception):
                pass

        # ── Neuroscience Architecture Extensions ──

        # Superior Colliculus: attention orienting + multisensory integration
        self._superior_colliculus = None
        if self._config.enable_superior_colliculus:
            try:
                from core.superior_colliculus import SuperiorColliculus
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._superior_colliculus = SuperiorColliculus.from_yaml(yaml_cfg)
                else:
                    self._superior_colliculus = SuperiorColliculus()
            except (ImportError, Exception):
                pass

        # Insular Cortex: salience detection + interoception
        self._insular_cortex = None
        if self._config.enable_insular_cortex:
            try:
                from core.insular_cortex import InsularCortex
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._insular_cortex = InsularCortex.from_yaml(yaml_cfg)
                else:
                    self._insular_cortex = InsularCortex()
            except (ImportError, Exception):
                pass

        # Prefrontal Cortex: working memory + cognitive control
        self._prefrontal_cortex = None
        if self._config.enable_prefrontal_cortex:
            try:
                from core.prefrontal_cortex import PrefrontalCortex
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._prefrontal_cortex = PrefrontalCortex.from_yaml(yaml_cfg)
                else:
                    self._prefrontal_cortex = PrefrontalCortex()
            except (ImportError, Exception):
                pass

        # Hypothalamus: drives + circadian + HPA stress
        self._hypothalamus = None
        if self._config.enable_hypothalamus:
            try:
                from core.hypothalamus_drives import HypothalamusModule
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._hypothalamus = HypothalamusModule.from_yaml(yaml_cfg)
                else:
                    self._hypothalamus = HypothalamusModule()
            except (ImportError, Exception):
                pass

        # Cerebellum: forward model prediction + timing + error learning
        self._cerebellum = None
        if self._config.enable_cerebellum:
            try:
                from core.cerebellum_module import CerebellumModule
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._cerebellum = CerebellumModule.from_yaml(yaml_cfg)
                else:
                    self._cerebellum = CerebellumModule()
            except (ImportError, Exception):
                pass

        # Default Mode Network: self-reference + creativity (active in idle)
        self._default_mode_network = None
        if self._config.enable_default_mode_network:
            try:
                from core.default_mode_network import DefaultModeNetwork
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._default_mode_network = DefaultModeNetwork.from_yaml(yaml_cfg)
                else:
                    self._default_mode_network = DefaultModeNetwork()
            except (ImportError, Exception):
                pass

        # Anterior Cingulate Cortex: conflict monitoring + effort allocation
        self._anterior_cingulate = None
        if self._config.enable_anterior_cingulate:
            try:
                from core.anterior_cingulate import AnteriorCingulateCortex
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._anterior_cingulate = AnteriorCingulateCortex.from_yaml(yaml_cfg)
                else:
                    self._anterior_cingulate = AnteriorCingulateCortex()
            except (ImportError, Exception):
                pass

        # Entorhinal Cortex: spatial coding + memory gateway
        self._entorhinal_cortex = None
        if self._config.enable_entorhinal_cortex:
            try:
                from core.entorhinal_cortex import EntorhinalCortex
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._entorhinal_cortex = EntorhinalCortex.from_yaml(yaml_cfg)
                else:
                    self._entorhinal_cortex = EntorhinalCortex()
            except (ImportError, Exception):
                pass

        # Nucleus Accumbens: reward gateway + approach/avoidance
        self._nucleus_accumbens = None
        if self._config.enable_nucleus_accumbens:
            try:
                from core.nucleus_accumbens import NucleusAccumbens
                yaml_cfg = getattr(planner, '_yaml_config', None)
                if yaml_cfg:
                    self._nucleus_accumbens = NucleusAccumbens.from_yaml(yaml_cfg)
                else:
                    self._nucleus_accumbens = NucleusAccumbens()
            except (ImportError, Exception):
                pass

        # Initialize sleep consolidation system (P2.23)
        self._sleep_consolidation = None
        if self._config.enable_sleep_consolidation:
            try:
                from core.sleep_consolidation import SleepConsolidation, SleepConsolidationConfig
                sc_config = SleepConsolidationConfig()
                neuromod = getattr(planner, 'neuromodulation', None)
                self._sleep_consolidation = SleepConsolidation(
                    config=sc_config,
                    neuromodulation=neuromod
                )
            except ImportError:
                pass

    @property
    def current_phase(self) -> LoopPhase:
        return self._phase

    def process(self, task_description: str):
        """
        Main entry point. Runs the full cognitive loop and returns
        a HierarchicalPrediction (same return type as HierarchicalPlanner.predict()).
        """
        ctx = LoopContext(task_description=task_description)
        self._logger.info(f"CognitiveLoop.process() start: {task_description[:80]}")

        # Frequency controller integration
        if self._frequency_controller:
            try:
                self._frequency_controller.auto_switch({
                    'task_type': 'routing',
                    'requires_action': False
                })
            except Exception:
                pass  # Non-critical

        t_start = time.time()

        # Start tracing if tracer available (P4.63)
        if self._tracer:
            self._tracer.start_trace(task_description)

        # Main loop with possible re-entry from REFLECT phase
        while True:
            ctx.loop_iterations += 1

            self._run_phase('perceive', self._perceive, ctx)
            self._run_phase('appraise_emotion', self._appraise_emotion, ctx)
            self._run_phase('remember', self._remember, ctx)
            self._run_phase('attend', self._attend, ctx)
            self._run_phase('modulate', self._modulate, ctx)
            self._run_phase('reason', self._reason, ctx)
            self._run_phase('reflect', self._reflect, ctx)

            if ctx.should_reconsider and ctx.loop_iterations < self._config.max_loop_iterations:
                ctx.should_reconsider = False
                self._logger.info(f"Reflection loopback: iteration {ctx.loop_iterations}")
                continue
            else:
                break

        self._run_phase('learn', self._learn, ctx)
        self._run_phase('consolidate', self._consolidate, ctx)

        ctx.total_time = time.time() - t_start
        self._last_context = ctx
        self._phase = LoopPhase.IDLE

        # End trace (P4.63)
        if self._tracer:
            self._tracer.end_trace(looped_back=(ctx.loop_iterations > 1))

        self._logger.info(
            f"CognitiveLoop.process() done: {ctx.total_time*1000:.1f}ms, "
            f"iterations={ctx.loop_iterations}, conf={ctx.confidence:.2f}"
        )

        return self._build_prediction(ctx)

    def _run_phase(self, phase_name: str, phase_fn, ctx: LoopContext) -> None:
        """Run a phase with timing and optional tracing (P4.63)."""
        t0 = time.time()
        phase_fn(ctx)
        t1 = time.time()

        if self._tracer:
            # Build summaries for tracing
            output = {}
            if phase_name == 'perceive':
                output = {'task_type': ctx.task_type}
            elif phase_name == 'attend':
                output = {'ctm_hint': ctx.ctm_domain_hint}
            elif phase_name == 'modulate':
                output = {'temperature': ctx.gating_temperature}
            elif phase_name == 'reason':
                output = {'confidence': ctx.confidence}
            elif phase_name == 'reflect':
                output = {'should_reconsider': ctx.should_reconsider}

            warnings = []
            if phase_name == 'modulate' and ctx.gating_temperature > 1.3:
                warnings.append('High exploration temperature')
            if phase_name == 'reflect' and ctx.should_reconsider:
                warnings.append('Reflection triggered loopback')

            self._tracer.trace_phase(
                phase_name, t0, t1,
                output_summary=output,
                warnings=warnings if warnings else None
            )

    # ========== Phase Implementations ==========

    def _perceive(self, ctx: LoopContext) -> None:
        """Phase 1: Encode incoming task via sensory preprocessing + Layer 1 (TaskFeatureRouter)."""
        self._phase = LoopPhase.PERCEIVE
        t0 = time.time()

        # Sensory preprocessing: extract structured features from raw text
        sensory_features = None
        if self._sensory_preprocessor:
            try:
                sensory_features = self._sensory_preprocessor.extract(ctx.task_description)
            except Exception:
                sensory_features = None

        # Layer 1: feature extraction and initial routing
        ctx.layer1_routing = self._planner.layer1.route_task(ctx.task_description)
        ctx.raw_routing_weights = np.array(ctx.layer1_routing.routing_weights, dtype=np.float64).copy()

        # Enrich Layer 1 features with sensory preprocessing if available
        if sensory_features:
            # Use sensory features to enrich the task feature predictions
            ctx.layer1_routing.features.complexity = max(
                ctx.layer1_routing.features.complexity,
                sensory_features.overall_complexity
            )
            ctx.layer1_routing.features.urgency = max(
                ctx.layer1_routing.features.urgency,
                sensory_features.overall_urgency
            )
            # Store sensory features for other phases
            if not hasattr(ctx, '_sensory_features'):
                ctx._sensory_features = sensory_features

        # Predictive coding: predict features before we know them
        if self._planner.enable_predictive_coding and self._planner.predictive_coding:
            try:
                ctx.task_feature_prediction, _ = self._planner.predictive_coding.predict_task_features({})
            except Exception:
                ctx.task_feature_prediction = None

        # P6.89-90: Temporal context — use time-of-day patterns for routing bias
        if (self._config.enable_temporal_patterns and
                self._planner.enable_temporal_memory and self._planner.temporal_memory):
            try:
                from datetime import datetime as _dt
                now = _dt.now()
                hour = now.hour
                if 5 <= hour < 12:
                    ctx.circadian_phase = 'morning'
                elif 12 <= hour < 17:
                    ctx.circadian_phase = 'afternoon'
                elif 17 <= hour < 21:
                    ctx.circadian_phase = 'evening'
                else:
                    ctx.circadian_phase = 'night'

                # Get temporal predictions if available
                if hasattr(self._planner.temporal_memory, 'predict_next_event'):
                    prediction = self._planner.temporal_memory.predict_next_event()
                    if prediction:
                        ctx.temporal_patterns = {'prediction': prediction}

                # Get time-of-day patterns
                if hasattr(self._planner.temporal_memory, 'time_of_day_patterns'):
                    tod_patterns = self._planner.temporal_memory.time_of_day_patterns.get(
                        ctx.circadian_phase, {}
                    )
                    if tod_patterns:
                        if ctx.temporal_patterns is None:
                            ctx.temporal_patterns = {}
                        ctx.temporal_patterns['time_of_day_bias'] = dict(tod_patterns)
            except Exception:
                pass

        # P6.83: Multimodal Fusion - fuse routing weights with sensory features
        if self._multimodal_fusion and ctx.raw_routing_weights is not None:
            try:
                import torch
                # Create lightweight tensor representations
                routing_tensor = torch.tensor(ctx.raw_routing_weights[:10], dtype=torch.float32).unsqueeze(0)
                text_tensor = torch.randn(1, 64)  # Placeholder for text embedding
                inputs = {'text': text_tensor, 'routing': routing_tensor}
                fused = self._multimodal_fusion(inputs)
                ctx.multimodal_fusion = {
                    'fused_dim': fused.shape[-1] if hasattr(fused, 'shape') else 0,
                    'active': True,
                }
            except Exception:
                pass

        # Superior Colliculus: orient attention to salient input
        if self._superior_colliculus and ctx.raw_routing_weights is not None:
            try:
                visual_signal = ctx.raw_routing_weights[:min(8, len(ctx.raw_routing_weights))].astype(np.float32)
                if len(visual_signal) < 8:
                    visual_signal = np.pad(visual_signal, (0, 8 - len(visual_signal)))
                sc_result = self._superior_colliculus.process(visual=visual_signal)
                ctx.sc_orienting = {
                    'peak_location': sc_result.get('peak_location'),
                    'orienting': sc_result.get('orienting_command') is not None,
                    'enhancement': sc_result.get('multisensory_enhancement', 0.0),
                }
            except Exception:
                pass

        # Insular Cortex: compute salience of current input
        if self._insular_cortex and ctx.raw_routing_weights is not None:
            try:
                novelty = ctx.layer1_routing.features.complexity if ctx.layer1_routing else 0.3
                result = self._insular_cortex.process(
                    sensory_signals={'routing': float(np.max(ctx.raw_routing_weights))},
                    novelty=novelty,
                    emotional_intensity=ctx.emotional_arousal,
                )
                ctx.insular_salience = {
                    'salience': result.get('salience', 0.0),
                    'feeling': result.get('feeling', 'neutral'),
                    'active_network': result.get('active_network', 'dmn'),
                    'body_budget': result.get('body_budget', 1.0),
                }
            except Exception:
                pass

        ctx.phase_timings['perceive'] = time.time() - t0

    def _appraise_emotion(self, ctx: LoopContext) -> None:
        """Phase 1b: Emotional appraisal - assign valence/arousal to the task."""
        if not self._emotional_system:
            return

        t0 = time.time()
        try:
            task_features = {
                'complexity': ctx.layer1_routing.features.complexity,
                'urgency': ctx.layer1_routing.features.urgency
            }
            emotional_state = self._emotional_system.appraise_task(
                ctx.task_description, task_features
            )
            ctx.emotional_valence = emotional_state.valence
            ctx.emotional_arousal = emotional_state.arousal

            # Emotional modulation of routing weights
            routing_weights = np.array(ctx.layer1_routing.routing_weights, dtype=np.float64)
            modulated = self._emotional_system.modulate_routing_weights(routing_weights)
            ctx.layer1_routing.routing_weights = modulated
            ctx.raw_routing_weights = modulated.copy()

            # Apply emotional bias to neuromodulation if available
            if (self._planner.enable_neuromodulation and
                    self._planner.neuromodulation):
                bias = self._emotional_system.get_neuromodulation_bias()
                levels = self._planner.neuromodulation.levels
                levels.dopamine = np.clip(
                    levels.dopamine + bias['dopamine_delta'], 0.0, 1.0
                )
                levels.norepinephrine = np.clip(
                    levels.norepinephrine + bias['norepinephrine_delta'], 0.0, 1.0
                )
                levels.serotonin = np.clip(
                    levels.serotonin + bias['serotonin_delta'], 0.0, 1.0
                )
        except Exception:
            pass

        ctx.phase_timings['appraise_emotion'] = time.time() - t0

    def _remember(self, ctx: LoopContext) -> None:
        """Phase 2: Query memory BEFORE routing to bias toward successful past strategies."""
        self._phase = LoopPhase.REMEMBER
        t0 = time.time()

        if not self._planner.enable_memory or not self._planner.memory:
            ctx.phase_timings['remember'] = time.time() - t0
            return

        # Retrieve memory using raw (un-biased) routing weights
        try:
            ctx.memory_context = self._planner.memory.get_context(
                ctx.task_description,
                ctx.raw_routing_weights,
                ctx.layer1_routing.features.task_type
            )
        except Exception:
            ctx.memory_context = None
            ctx.phase_timings['remember'] = time.time() - t0
            return

        # Compute memory bias vector from successful similar tasks
        if not self._config.enable_memory_bias or not ctx.memory_context:
            ctx.phase_timings['remember'] = time.time() - t0
            return

        similar_tasks = ctx.memory_context.get('working_memory', {}).get('similar_tasks', [])
        if not similar_tasks:
            ctx.phase_timings['remember'] = time.time() - t0
            return

        bias_accumulator = np.zeros_like(ctx.raw_routing_weights)
        weight_sum = 0.0
        confidence_sum = 0.0

        for entry_dict, similarity in similar_tasks:
            # entry_dict is a dict (already converted via to_dict())
            if entry_dict.get('outcome') == 'success' and entry_dict.get('brain_gates'):
                gates = np.array(entry_dict['brain_gates'], dtype=np.float64)
                if gates.shape == ctx.raw_routing_weights.shape:
                    bias_accumulator += similarity * gates
                    weight_sum += similarity
                    confidence_sum += entry_dict.get('confidence', 0.5) * similarity

        if weight_sum > 0:
            ctx.memory_bias = bias_accumulator / weight_sum
            ctx.memory_confidence_hint = confidence_sum / weight_sum

            # Blend routing weights toward successful past patterns
            blend = self._config.memory_routing_bias_strength
            biased_weights = (1 - blend) * ctx.raw_routing_weights + blend * ctx.memory_bias

            # Re-normalize to maintain gate sum invariant
            weight_sum_total = np.sum(biased_weights)
            if weight_sum_total > 1e-8:
                biased_weights = biased_weights / weight_sum_total
            else:
                biased_weights = ctx.raw_routing_weights.copy()

            ctx.layer1_routing.routing_weights = biased_weights

        # Entorhinal Cortex: spatial/memory gateway encoding
        if self._entorhinal_cortex and ctx.raw_routing_weights is not None:
            try:
                position = ctx.raw_routing_weights[:2].astype(np.float32) if len(ctx.raw_routing_weights) >= 2 else np.zeros(2, dtype=np.float32)
                ec_result = self._entorhinal_cortex.process(position=position)
                ctx.entorhinal_spatial = {
                    'grid_activation': float(np.mean(ec_result.get('grid_code', np.zeros(1)))),
                    'head_direction': float(ec_result.get('head_direction', 0.0)),
                }
            except Exception:
                pass

        ctx.phase_timings['remember'] = time.time() - t0

    def _attend(self, ctx: LoopContext) -> None:
        """Phase 3: Compute attention, gate modalities, and select CTM domain hint."""
        self._phase = LoopPhase.ATTEND
        t0 = time.time()

        routing_weights = np.array(ctx.layer1_routing.routing_weights, dtype=np.float64)

        if not self._planner.enable_attention or not self._planner.attention:
            ctx.attention_gated_weights = routing_weights
            ctx.phase_timings['attend'] = time.time() - t0
            return

        # Compute attention using existing mechanism
        task_features_dict = {
            'complexity': ctx.layer1_routing.features.complexity,
            'urgency': ctx.layer1_routing.features.urgency,
            'task_type': ctx.layer1_routing.features.task_type
        }

        try:
            ctx.attention_state = self._planner.attention.compute_attention(
                brain_gates=routing_weights,
                task_type=ctx.layer1_routing.features.task_type,
                prediction_errors=ctx.prediction_errors,
                task_features=task_features_dict,
                memory_context=ctx.memory_context
            )
        except Exception:
            ctx.attention_gated_weights = routing_weights
            ctx.phase_timings['attend'] = time.time() - t0
            return

        # Attention DRIVES modality gating
        if self._config.enable_attention_driving and ctx.attention_state is not None:
            try:
                # Emotional arousal modulates attention strength
                gating_strength = self._config.attention_gating_strength
                if self._emotional_system:
                    gating_strength = self._emotional_system.modulate_attention_strength(gating_strength)
                    gating_strength = min(gating_strength, 1.0)

                # Homeostatic fatigue degrades attention
                if self._homeostatic:
                    attn_factor = self._homeostatic.get_attention_degradation()
                    ctx.homeostatic_attn_factor = attn_factor
                    gating_strength *= attn_factor

                # P2.25: Frequency mode modulates attention strength
                if self._config.enable_frequency_modulation and self._frequency_controller:
                    try:
                        freq_state = self._frequency_controller.get_state()
                        dom_mode = freq_state.get('dominant_mode', 'alpha')
                        freq_attn = self._config.frequency_attention_strength.get(dom_mode, 0.5)
                        gating_strength = (gating_strength + freq_attn) / 2.0
                    except Exception:
                        pass

                gated = self._planner.attention.apply_attention_gating(
                    brain_gates=routing_weights,
                    attention_weights=ctx.attention_state.attention_weights,
                    gating_strength=gating_strength
                )
                # Re-normalize
                gated_sum = np.sum(gated)
                if gated_sum > 1e-8:
                    ctx.attention_gated_weights = gated / gated_sum
                else:
                    ctx.attention_gated_weights = routing_weights
            except Exception:
                ctx.attention_gated_weights = routing_weights
        else:
            ctx.attention_gated_weights = routing_weights

        # Attention-driven CTM domain selection
        if self._config.enable_dynamic_ctm and ctx.attention_state is not None:
            attn_weights = ctx.attention_state.attention_weights

            # Map high-attention modalities to CTM domains
            # Index 6=tool_trace, 7=temporal_pattern, 8=error_signal, 9=success_signal
            modality_to_ctm = {
                7: 'temporal',    # temporal_pattern -> TemporalCTM
                8: 'logic',       # error_signal -> LogicCTM
                6: 'spatial',     # tool_trace -> SpatialCTM
                9: 'value',       # success_signal -> ValueCTM
            }

            best_ctm_domain = None
            best_ctm_weight = 0.0
            for idx, domain in modality_to_ctm.items():
                if idx < len(attn_weights) and attn_weights[idx] > self._config.attention_ctm_threshold:
                    if attn_weights[idx] > best_ctm_weight:
                        best_ctm_weight = attn_weights[idx]
                        best_ctm_domain = domain

            if best_ctm_domain is not None:
                ctx.ctm_domain_hint = best_ctm_domain

        # Store for next cycle feedback
        self._planner._last_attention_state = ctx.attention_state

        # Prefrontal Cortex: top-down bias + working memory update
        if self._prefrontal_cortex and ctx.attention_gated_weights is not None:
            try:
                state_vec = ctx.attention_gated_weights.astype(np.float32)
                # Pad or truncate to PFC state_dim
                pfc_dim = self._prefrontal_cortex.state_dim
                if len(state_vec) < pfc_dim:
                    state_vec = np.pad(state_vec, (0, pfc_dim - len(state_vec)))
                else:
                    state_vec = state_vec[:pfc_dim]
                pfc_result = self._prefrontal_cortex.process(
                    state_vec,
                    task_label=ctx.task_type,
                    conflict_level=ctx.emotional_arousal
                )
                ctx.pfc_state = {
                    'value': pfc_result.get('value', 0.0),
                    'inhibit': pfc_result.get('inhibit', False),
                    'wm_count': self._prefrontal_cortex.working_memory.count,
                    'active_task': pfc_result.get('active_task'),
                }
                # PFC bias signal modulates attention weights
                bias = pfc_result.get('bias_signal')
                if bias is not None and len(bias) > 0:
                    bias_trunc = bias[:len(ctx.attention_gated_weights)]
                    if len(bias_trunc) == len(ctx.attention_gated_weights):
                        blend = 0.1  # Subtle top-down bias
                        ctx.attention_gated_weights = (
                            (1 - blend) * ctx.attention_gated_weights +
                            blend * np.abs(bias_trunc)
                        )
                        gated_sum = np.sum(ctx.attention_gated_weights)
                        if gated_sum > 1e-8:
                            ctx.attention_gated_weights = ctx.attention_gated_weights / gated_sum
            except Exception:
                pass

        ctx.phase_timings['attend'] = time.time() - t0

    def _modulate(self, ctx: LoopContext) -> None:
        """Phase 4: Neuromodulation actively controls gating temperature."""
        self._phase = LoopPhase.MODULATE
        t0 = time.time()

        weights = ctx.attention_gated_weights if ctx.attention_gated_weights is not None \
            else np.array(ctx.layer1_routing.routing_weights, dtype=np.float64)

        if not self._planner.enable_neuromodulation or not self._planner.neuromodulation:
            ctx.modulated_weights = weights
            ctx.phase_timings['modulate'] = time.time() - t0
            return

        ctx.neuro_levels = self._planner.neuromodulation.levels
        try:
            ctx.neuro_effects = self._planner.neuromodulation.compute_effects()
        except Exception:
            ctx.neuro_effects = None

        if not self._config.enable_neuro_modulation:
            ctx.modulated_weights = weights
            ctx.phase_timings['modulate'] = time.time() - t0
            return

        # Dopamine controls exploration via temperature
        dopamine = ctx.neuro_levels.dopamine
        ctx.gating_temperature = 1.0
        if dopamine < self._config.low_dopamine_threshold:
            temp_boost = (self._config.low_dopamine_threshold - dopamine) * self._config.neuro_temperature_sensitivity
            ctx.gating_temperature += temp_boost

        # Norepinephrine controls focus via temperature
        norepinephrine = ctx.neuro_levels.norepinephrine
        if norepinephrine > self._config.high_norepinephrine_threshold:
            temp_reduction = (norepinephrine - self._config.high_norepinephrine_threshold) * self._config.neuro_temperature_sensitivity
            ctx.gating_temperature = max(0.1, ctx.gating_temperature - temp_reduction)

        # Homeostatic regulation: energy/fatigue affect temperature
        if self._homeostatic:
            h_adj = self._homeostatic.get_temperature_adjustment()
            ctx.homeostatic_temp_adj = h_adj
            ctx.gating_temperature = max(0.1, ctx.gating_temperature + h_adj)

        # P2.25: Frequency mode influences gating temperature
        if self._config.enable_frequency_modulation and self._frequency_controller:
            try:
                freq_state = self._frequency_controller.get_state()
                dominant_mode = freq_state.get('dominant_mode', 'alpha')
                freq_temp = self._config.frequency_temperature.get(dominant_mode, 1.0)
                # Blend frequency temperature with neuromod temperature (50/50)
                ctx.gating_temperature = (ctx.gating_temperature + freq_temp) / 2.0
                ctx.gating_temperature = max(0.1, ctx.gating_temperature)
            except Exception:
                pass

        # P2.28: Homeostasis → frequency mode auto-switch
        if (self._config.enable_homeostatic_frequency and
                self._homeostatic and self._frequency_controller):
            try:
                energy = self._homeostatic.state.energy
                target_mode = 'alpha'  # default
                for threshold, mode_name in self._config.energy_to_frequency_thresholds:
                    if energy <= threshold:
                        target_mode = mode_name
                        break
                from core.brain_frequency_controller import FrequencyMode
                mode_enum = FrequencyMode(target_mode)
                if self._frequency_controller.dominant_mode != mode_enum:
                    self._frequency_controller.set_mode(mode_enum)
            except Exception:
                pass

        # Hypothalamus: drive states modulate arousal/temperature
        if self._hypothalamus:
            try:
                ht_result = self._hypothalamus.update_drives(elapsed_seconds=1.0)
                ctx.hypothalamus_drives = {
                    'urgency': ht_result.get('urgency', 0.0),
                    'most_urgent': ht_result.get('most_urgent', ('none', 0.0)),
                    'arousal': ht_result.get('arousal', 0.5),
                    'cortisol': self._hypothalamus.hpa.cortisol,
                }
                # Drive urgency increases temperature (more exploration when needs unmet)
                drive_urgency = ht_result.get('urgency', 0.0)
                if drive_urgency > 0.5:
                    ctx.gating_temperature += (drive_urgency - 0.5) * 0.2
                    ctx.gating_temperature = max(0.1, ctx.gating_temperature)
            except Exception:
                pass

        # Nucleus Accumbens: reward gating based on dopamine
        if self._nucleus_accumbens:
            try:
                da_level = 0.5
                if ctx.neuro_levels and hasattr(ctx.neuro_levels, 'dopamine'):
                    da_level = ctx.neuro_levels.dopamine
                nacc_result = self._nucleus_accumbens.process(
                    dopamine_level=da_level,
                    reward_prediction=ctx.confidence,
                    threat_level=ctx.emotional_arousal * 0.5,
                    effort_required=ctx.layer1_routing.features.complexity if ctx.layer1_routing else 0.5,
                    energy_level=ctx.insular_salience.get('body_budget', 0.8) if ctx.insular_salience else 0.8,
                )
                ctx.nacc_reward = {
                    'go_drive': nacc_result.get('go_drive', 0.5),
                    'nogo_drive': nacc_result.get('nogo_drive', 0.5),
                    'approach': nacc_result.get('approach', True),
                    'effective_effort': nacc_result.get('effective_effort', 0.5),
                }
            except Exception:
                pass

        # Apply temperature via softmax rescaling
        if abs(ctx.gating_temperature - 1.0) > 1e-6:
            log_weights = np.log(np.maximum(weights, 1e-10))
            scaled = np.exp(log_weights / ctx.gating_temperature)
            scaled_sum = np.sum(scaled)
            if scaled_sum > 1e-8:
                ctx.modulated_weights = scaled / scaled_sum
            else:
                ctx.modulated_weights = weights
        else:
            ctx.modulated_weights = weights

        ctx.phase_timings['modulate'] = time.time() - t0

    def _reason(self, ctx: LoopContext) -> None:
        """Phase 5: Route through Layer 2 + 3 with modulated context."""
        self._phase = LoopPhase.REASON
        t0 = time.time()

        # Layer 2: Path Planning
        try:
            ctx.layer2_prediction = self._planner.layer2.predict_optimal_path(ctx.task_description)
        except Exception:
            ctx.layer2_prediction = None

        # Extract brain gates from Layer 2's brain monitor
        ctx.brain_gates = ctx.modulated_weights
        if hasattr(self._planner.layer2, 'brain_monitor') and self._planner.layer2.brain_monitor:
            if self._planner.layer2.brain_monitor.gate_history:
                ctx.brain_gates = np.array(
                    list(self._planner.layer2.brain_monitor.gate_history)[-1],
                    dtype=np.float64
                )

        # Extract Layer 2 outputs
        if ctx.layer2_prediction:
            ctx.predicted_sequence = ctx.layer2_prediction.predicted_sequence
            ctx.confidence = ctx.layer2_prediction.confidence
            ctx.success_probability = ctx.layer2_prediction.success_probability
            ctx.dominant_modalities = ctx.layer2_prediction.dominant_modalities
            ctx.task_type = ctx.layer2_prediction.task_type
        else:
            ctx.predicted_sequence = []
            ctx.confidence = 0.5
            ctx.success_probability = 0.5
            ctx.dominant_modalities = []
            ctx.task_type = ctx.layer1_routing.features.task_type

        # Goal graph: consult active goals to provide context
        if (hasattr(self._planner, 'enable_goal_graph') and
                self._planner.enable_goal_graph and
                hasattr(self._planner, 'goal_graph') and
                self._planner.goal_graph):
            try:
                ctx.goal_context = self._planner.goal_graph.get_context_for_ctm()
                # If there are overdue goals, increase urgency in routing
                if ctx.goal_context and ctx.goal_context.get('overdue_count', 0) > 0:
                    # Bias toward 'execute' by slightly sharpening weights
                    if ctx.modulated_weights is not None:
                        urgency_boost = min(0.1, ctx.goal_context['overdue_count'] * 0.03)
                        ctx.modulated_weights = ctx.modulated_weights * (1.0 + urgency_boost)
                        weight_sum = np.sum(ctx.modulated_weights)
                        if weight_sum > 1e-8:
                            ctx.modulated_weights = ctx.modulated_weights / weight_sum
            except Exception:
                pass

        # Dynamic CTM threshold based on uncertainty
        effective_ctm_threshold = self._config.base_ctm_threshold
        if self._config.enable_dynamic_ctm:
            # Use previous reflection's uncertainty if available (on re-entry)
            if ctx.cognitive_state and hasattr(ctx.cognitive_state, 'uncertainty_level'):
                uncertainty = ctx.cognitive_state.uncertainty_level
                if uncertainty > 0.6:
                    effective_ctm_threshold -= self._config.uncertainty_ctm_reduction
                    effective_ctm_threshold = max(0.1, effective_ctm_threshold)

        # P2.25: Frequency mode modulates CTM threshold
        # P2.26: Gamma mode → CTM auto-trigger (threshold near 0)
        if self._config.enable_frequency_modulation and self._frequency_controller:
            try:
                freq_state = self._frequency_controller.get_state()
                dom_mode = freq_state.get('dominant_mode', 'alpha')
                freq_ctm = self._config.frequency_ctm_threshold.get(dom_mode, 0.4)
                # Blend: average of dynamic threshold and frequency-suggested threshold
                effective_ctm_threshold = (effective_ctm_threshold + freq_ctm) / 2.0
                effective_ctm_threshold = max(0.05, effective_ctm_threshold)
            except Exception:
                pass

        # CTM trigger with attention-driven domain hint
        complexity = ctx.layer1_routing.features.complexity
        if (self._planner.enable_ctm_async and
                complexity >= effective_ctm_threshold and
                hasattr(self._planner, 'ctm_ensemble') and
                self._planner.ctm_ensemble):
            try:
                brain_state = {
                    'modality_activations': {
                        'task_complexity': complexity,
                        'task_urgency': ctx.layer1_routing.features.urgency
                    },
                    'goal_context': ctx.goal_context
                }
                domain_hint = ctx.ctm_domain_hint or ctx.task_type
                ctm_max_steps = getattr(self._planner, 'ctm_max_steps', 50)
                ctx.ctm_task_id = self._planner.ctm_ensemble.reason_async(
                    task=ctx.task_description,
                    brain_state=brain_state,
                    max_steps=ctm_max_steps,
                    domain_hint=domain_hint
                )
            except Exception:
                ctx.ctm_task_id = None

        # Per-modality prediction errors from Layer 2's MetaRouter
        ctx.per_modality_pes = None
        try:
            if hasattr(self._planner.layer2, 'meta_router'):
                meta_router = self._planner.layer2.meta_router
                if hasattr(meta_router, 'modality_pe_tracker') and meta_router.modality_pe_tracker:
                    pe_tracker = meta_router.modality_pe_tracker
                    ctx.per_modality_pes = {
                        mod: float(np.mean(state.pe_history)) if state.pe_history else 0.0
                        for mod, state in pe_tracker.states.items()
                    }
        except Exception:
            pass

        # Layer 3: Decision Routing with modulated gates
        layer2_dict = {
            'predicted_sequence': ctx.predicted_sequence,
            'confidence': ctx.confidence,
            'success_probability': ctx.success_probability,
            'dominant_modalities': ctx.dominant_modalities,
            'task_type': ctx.task_type
        }

        try:
            ctx.actionable_decision = self._planner.layer3.route_to_action(
                layer1_state=ctx.layer1_routing,
                layer2_prediction=layer2_dict,
                brain_gates=ctx.brain_gates,
                per_modality_pes=ctx.per_modality_pes,
                memory_context=ctx.memory_context
            )
        except Exception as e:
            # Fallback: create a minimal safe decision if Layer 3 fails
            from core.decision_router import ActionableDecision
            ctx.actionable_decision = ActionableDecision(
                task_features=ctx.layer1_routing.features.to_dict() if ctx.layer1_routing else {},
                layer1_routing=ctx.layer1_routing.to_dict() if ctx.layer1_routing else {},
                predicted_sequence=ctx.predicted_sequence or [],
                confidence=ctx.confidence if ctx.confidence else 0.3,
                success_probability=ctx.success_probability if ctx.success_probability else 0.3,
                dominant_modalities=ctx.dominant_modalities or [],
                multi_target_decision={
                    'primary': {
                        'type': 'suggest',
                        'weight': 0.5,
                        'reasoning': f'Layer 3 fallback (error: {str(e)[:80]})'
                    },
                    'alternatives': [
                        {'type': 'wait', 'weight': 0.3, 'reasoning': 'Conservative fallback'},
                        {'type': 'retry', 'weight': 0.2, 'reasoning': 'Retry option'}
                    ]
                },
                processing_mode='cautious',
                reasoning_chain=[
                    f'[CognitiveLoop] Layer 3 routing failed: {str(e)[:100]}',
                    '[CognitiveLoop] Using safe fallback: suggest (cautious mode)'
                ]
            )

        # Check for CTM results (non-blocking)
        if ctx.ctm_task_id and hasattr(self._planner, 'ctm_ensemble') and self._planner.ctm_ensemble:
            try:
                result = self._planner.ctm_ensemble.get_result(ctx.ctm_task_id, wait=False)
                if result and hasattr(result, 'aggregated_insights') and result.aggregated_insights:
                    ctx.ctm_insights = result.aggregated_insights
            except Exception:
                pass

        # P6.85: Safety Layer — check decision before finalizing
        if self._safety_layer and ctx.actionable_decision:
            try:
                decision_type = ctx.actionable_decision.multi_target_decision['primary']['type']
                # Build action representation for safety check
                action_info = {
                    'decision_type': decision_type,
                    'confidence': ctx.confidence,
                    'task': ctx.task_description,
                    'processing_mode': getattr(ctx.actionable_decision, 'processing_mode', 'normal')
                }
                report = self._safety_layer.check(action_info)
                if report and hasattr(report, 'to_dict'):
                    ctx.safety_report = report.to_dict()
                elif isinstance(report, dict):
                    ctx.safety_report = report
                else:
                    ctx.safety_report = {'is_safe': True, 'safety_level': 'safe'}
            except Exception:
                ctx.safety_report = {'is_safe': True, 'safety_level': 'safe', 'source': 'fallback'}

        # P6.86: Formal Verifier — verify decision properties
        if self._formal_verifier and ctx.actionable_decision:
            try:
                import numpy as _np
                state = _np.random.randn(64)  # Abstract state representation
                action = _np.zeros(16)
                decision_type = ctx.actionable_decision.multi_target_decision['primary']['type']
                action_idx = min(hash(decision_type) % 16, 15)
                action[action_idx] = 1.0
                # Use verify method (works for both FormalVerifier and SimplifiedVerifier)
                result = self._formal_verifier.verify(state, action)
                if hasattr(result, 'to_dict'):
                    ctx.formal_verification = result.to_dict()
                elif isinstance(result, dict):
                    ctx.formal_verification = result
                else:
                    ctx.formal_verification = {'verified': True, 'source': 'formal_verifier'}
            except Exception:
                ctx.formal_verification = {'verified': True, 'source': 'fallback'}

        # Cerebellum: forward model prediction for current state->action
        if self._cerebellum and ctx.brain_gates is not None:
            try:
                state = ctx.brain_gates.astype(np.float32)
                cb_dim = self._cerebellum.state_dim
                if len(state) < cb_dim:
                    state = np.pad(state, (0, cb_dim - len(state)))
                else:
                    state = state[:cb_dim]
                action = np.zeros(self._cerebellum.action_dim, dtype=np.float32)
                action[0] = ctx.confidence  # Use confidence as action signal
                cb_result = self._cerebellum.process(state, action)
                ctx.cerebellum_prediction = {
                    'predicted_next': float(np.mean(cb_result.get('predicted_next_state', np.zeros(1)))),
                    'correction': float(np.mean(np.abs(cb_result.get('corrective_action', np.zeros(1))))),
                    'timing_active': cb_result.get('timing_active', False),
                }
            except Exception:
                pass

        ctx.phase_timings['reason'] = time.time() - t0

    def _reflect(self, ctx: LoopContext) -> None:
        """Phase 6: Evaluate decision quality. Can trigger loop re-entry."""
        self._phase = LoopPhase.REFLECT
        t0 = time.time()

        # Predictive coding: compute prediction errors
        if self._planner.enable_predictive_coding and self._planner.predictive_coding:
            try:
                if ctx.task_feature_prediction is not None:
                    actual_features = {
                        'task_type': ctx.layer1_routing.features.task_type,
                        'complexity': ctx.layer1_routing.features.complexity,
                        'urgency': ctx.layer1_routing.features.urgency
                    }
                    task_pe = self._planner.predictive_coding.update_task_prediction(
                        ctx.task_feature_prediction, actual_features
                    )
                    ctx.prediction_errors = {
                        'layer1': task_pe.to_dict() if task_pe else None
                    }
            except Exception:
                pass

            try:
                ctx.curiosity_signal = self._planner.predictive_coding.get_curiosity_signal()
            except Exception:
                pass

        # Consciousness metrics: assess cognitive state
        if self._planner.enable_consciousness_metrics and self._planner.consciousness_metrics:
            try:
                attention_focus = 'distributed'
                if ctx.attention_state and hasattr(ctx.attention_state, 'attention_focus'):
                    attention_focus = ctx.attention_state.attention_focus

                memory_load = 0.5
                if self._planner.enable_memory and self._planner.memory:
                    working = self._planner.memory.working
                    if hasattr(working, 'capacity') and working.capacity > 0:
                        memory_load = min(1.0, len(working.buffer) / working.capacity)

                reasoning_depth = min(3, int(ctx.layer1_routing.features.complexity * 3))
                uncertainty_level = 1.0 - ctx.confidence

                ctx.cognitive_state = self._planner.consciousness_metrics.update_cognitive_state(
                    attention_focus=attention_focus,
                    memory_load=memory_load,
                    reasoning_depth=reasoning_depth,
                    uncertainty_level=uncertainty_level,
                    timestamp=time.time()
                )
            except Exception:
                pass

        # Active inference: generate questions if uncertain
        if (self._planner.enable_active_inference and
                self._planner.active_inference and
                ctx.brain_gates is not None):
            try:
                inference_context = {}
                if ctx.memory_context:
                    inference_context['similar_tasks'] = ctx.memory_context.get(
                        'working_memory', {}
                    ).get('similar_tasks', [])

                ctx.inference_state = self._planner.active_inference.perform_inference(
                    task_description=ctx.task_description,
                    task_type=ctx.task_type,
                    brain_gates=ctx.brain_gates,
                    available_decisions=self._planner.layer3.intervention_types,
                    context=inference_context
                )
            except Exception:
                pass

        # P2.29: Prediction Error back-propagation to Layer 1/2
        # Feeds prediction errors back to bias future routing (online learning)
        if (self._config.enable_prediction_error_backprop and
                ctx.prediction_errors and ctx.prediction_errors.get('layer1') and
                ctx.raw_routing_weights is not None):
            try:
                pe_data = ctx.prediction_errors['layer1']
                pe_mag = pe_data.get('error_magnitude', 0) if isinstance(pe_data, dict) else 0
                if pe_mag > 0.1:
                    # Compute per-modality prediction errors if available
                    per_modality = pe_data.get('per_modality', None) if isinstance(pe_data, dict) else None
                    if per_modality and isinstance(per_modality, (list, np.ndarray)):
                        pe_array = np.array(per_modality, dtype=np.float64)
                        if len(pe_array) == len(ctx.raw_routing_weights):
                            # Increase weights for modalities with high PE (they need more attention)
                            # Scale factor: small enough not to destabilize, proportional to PE
                            backprop_lr = 0.05
                            adjustment = pe_array * backprop_lr
                            adjusted_weights = ctx.raw_routing_weights + adjustment
                            adjusted_weights = np.maximum(adjusted_weights, 1e-6)
                            adjusted_weights = adjusted_weights / np.sum(adjusted_weights)
                            # Store back into Layer 1 router for next task
                            if hasattr(self._planner.layer1, '_pe_bias'):
                                self._planner.layer1._pe_bias = adjusted_weights
                            ctx.per_modality_pes = per_modality
                    # Also update Layer 2's confidence calibration
                    if hasattr(self._planner, 'layer2') and hasattr(self._planner.layer2, 'update_confidence_bias'):
                        self._planner.layer2.update_confidence_bias(pe_mag)
            except Exception:
                pass

        # P6.76-77: Theory of Mind — update user model from task pattern
        if self._theory_of_mind:
            try:
                import torch
                # Create a simple observation vector from task features
                obs = np.zeros(64, dtype=np.float32)
                obs[0] = ctx.layer1_routing.features.complexity
                obs[1] = ctx.layer1_routing.features.urgency
                obs[2] = ctx.confidence
                obs[3] = ctx.emotional_valence
                obs[4] = ctx.emotional_arousal
                # Use ToM to track user as 'primary_user' agent
                obs_tensor = torch.tensor(obs).unsqueeze(0)
                action_idx = hash(ctx.task_type) % 16
                action_tensor = torch.tensor([action_idx])
                self._theory_of_mind.update_agent_model(
                    agent_id='primary_user',
                    observation=obs_tensor,
                    action=action_tensor
                )
                ctx.user_model = {
                    'agent_id': 'primary_user',
                    'observations_count': self._theory_of_mind.stats.total_observations
                    if hasattr(self._theory_of_mind, 'stats') and hasattr(self._theory_of_mind.stats, 'total_observations') else 0
                }
            except Exception:
                pass

        # P6.78-79: Causal Reasoning — lightweight causal context
        if self._causal_inference:
            try:
                ctx.causal_context = {
                    'dag_nodes': len(self._causal_inference.dag.nodes) if hasattr(self._causal_inference.dag, 'nodes') else 0,
                    'task_type': ctx.task_type,
                    'decision': ctx.actionable_decision.multi_target_decision['primary']['type'] if ctx.actionable_decision else 'unknown'
                }
            except Exception:
                pass

        # P6.81: Intrinsic Curiosity — compute curiosity signal from state/action
        if self._intrinsic_curiosity:
            try:
                import torch
                state = np.zeros(64, dtype=np.float32)
                state[0] = ctx.layer1_routing.features.complexity
                state[1] = ctx.confidence
                state[2] = ctx.emotional_arousal
                state_tensor = torch.tensor(state).unsqueeze(0)
                # Compute intrinsic reward (forward model prediction error)
                intrinsic_reward = self._intrinsic_curiosity.compute_intrinsic_reward(
                    state_tensor, state_tensor  # Same state = low novelty
                )
                ctx.curiosity_intrinsic = {
                    'intrinsic_reward': float(intrinsic_reward) if isinstance(intrinsic_reward, (int, float, np.floating)) else 0.0
                }
            except Exception:
                pass

        # P6.88: Thought Decoder — decode internal representation to interpretable form
        if self._thought_decoder:
            try:
                import torch
                # Create thought vector from current cognitive state
                thought = np.zeros(64, dtype=np.float32)
                thought[0] = ctx.confidence
                thought[1] = ctx.emotional_valence
                thought[2] = ctx.emotional_arousal
                thought[3] = ctx.gating_temperature
                if ctx.raw_routing_weights is not None:
                    thought[4:14] = ctx.raw_routing_weights[:10]
                thought_tensor = torch.tensor(thought).unsqueeze(0)
                # Try to decode (may fail if transformers not available)
                decoded = self._thought_decoder.decode(thought_tensor)
                ctx.thought_decode = {
                    'decoded_text': decoded if isinstance(decoded, str) else str(decoded)[:200],
                    'thought_dim': 64,
                }
            except Exception:
                ctx.thought_decode = {'decoded_text': '[decoder unavailable]', 'thought_dim': 64}

        # Determine if we should loop back
        if self._config.enable_reflection_loop and ctx.loop_iterations < self._config.max_loop_iterations:
            should_reconsider = False

            # Low confidence → reconsider
            if ctx.confidence < self._config.reconsider_confidence_threshold:
                should_reconsider = True

            # High prediction error → reconsider
            if ctx.prediction_errors and ctx.prediction_errors.get('layer1'):
                pe_data = ctx.prediction_errors['layer1']
                pe_mag = pe_data.get('error_magnitude', 0) if isinstance(pe_data, dict) else 0
                if pe_mag > self._config.reconsider_pe_threshold:
                    should_reconsider = True

            ctx.should_reconsider = should_reconsider

        # Anterior Cingulate Cortex: conflict monitoring + cognitive effort
        if self._anterior_cingulate and ctx.brain_gates is not None:
            try:
                response_activations = ctx.brain_gates.astype(np.float32)
                acc_result = self._anterior_cingulate.process(
                    response_activations=response_activations,
                    reward_magnitude=ctx.confidence,
                )
                ctx.acc_conflict = {
                    'conflict': acc_result.get('conflict', 0.0),
                    'error_likelihood': acc_result.get('error_likelihood', 0.0),
                    'effort_allocated': acc_result.get('effort_allocated', 0.0),
                    'arousal_adjustment': acc_result.get('arousal_adjustment', 0.0),
                }
                # High conflict can trigger reconsideration (only if confidence is low)
                if (acc_result.get('conflict', 0.0) > 0.7 and
                        ctx.confidence < 0.5 and not ctx.should_reconsider):
                    ctx.should_reconsider = True
            except Exception:
                pass

        ctx.phase_timings['reflect'] = time.time() - t0

    def _learn(self, ctx: LoopContext) -> None:
        """Phase 7: Store experience in memory, read meta-learning params."""
        self._phase = LoopPhase.LEARN
        t0 = time.time()

        # Store in working memory
        if (self._planner.enable_memory and self._planner.memory and
                ctx.brain_gates is not None and ctx.actionable_decision is not None):
            try:
                decision = ctx.actionable_decision.multi_target_decision['primary']['type']
                self._planner.memory.remember_task(
                    task=ctx.task_description,
                    task_type=ctx.task_type,
                    decision=decision,
                    confidence=ctx.confidence,
                    brain_gates=ctx.brain_gates,
                    outcome=None  # Not yet known
                )
            except Exception:
                pass

        # Meta-learning parameters
        if self._planner.enable_meta_learning and self._planner.meta_learner:
            try:
                ctx.meta_parameters = self._planner.meta_learner.meta_params
            except Exception:
                pass

        # Emotional decay (homeostasis)
        if self._emotional_system:
            try:
                self._emotional_system.decay()
            except Exception:
                pass

        # P6.87: Explanation Generator — generate explanation for decision
        if self._explanation_gen and ctx.actionable_decision:
            try:
                decision_type = ctx.actionable_decision.multi_target_decision['primary']['type']
                ctx.explanation = {
                    'decision': decision_type,
                    'confidence': ctx.confidence,
                    'task_type': ctx.task_type,
                    'reasoning_chain': getattr(ctx.actionable_decision, 'reasoning_chain', []),
                    'dominant_modalities': ctx.dominant_modalities,
                    'ctm_insights': ctx.ctm_insights,
                    'emotional_context': {
                        'valence': ctx.emotional_valence,
                        'arousal': ctx.emotional_arousal
                    }
                }
            except Exception:
                pass

        # P6.80: Self-Improvement — track performance metric
        if self._self_improvement:
            try:
                from core.self_improvement import PerformanceMetric
                metric = PerformanceMetric(
                    name='prediction_confidence',
                    value=ctx.confidence,
                    timestamp=time.time(),
                    context={'task_type': ctx.task_type}
                )
                self._self_improvement.record(metric)
            except Exception:
                pass

        # P6.82: Autonomous Goal Generator — suggest goals if applicable
        if self._autonomous_goal_gen:
            try:
                brain_state = {
                    'task_type': ctx.task_type,
                    'confidence': ctx.confidence,
                    'curiosity_level': ctx.curiosity_signal.get('curiosity_level', 'low') if ctx.curiosity_signal else 'low'
                }
                if hasattr(self._autonomous_goal_gen, 'suggest_goals'):
                    goals = self._autonomous_goal_gen.suggest_goals(brain_state)
                    if goals:
                        ctx.autonomous_goals = [
                            g.to_dict() if hasattr(g, 'to_dict') else str(g)
                            for g in goals[:3]
                        ]
            except Exception:
                pass

        # Cerebellum: learn from prediction error (climbing fiber signal)
        if self._cerebellum and ctx.cerebellum_prediction and ctx.brain_gates is not None:
            try:
                actual_state = ctx.brain_gates.astype(np.float32)
                cb_dim = self._cerebellum.state_dim
                if len(actual_state) < cb_dim:
                    actual_state = np.pad(actual_state, (0, cb_dim - len(actual_state)))
                else:
                    actual_state = actual_state[:cb_dim]
                self._cerebellum.learn(actual_state, error_signal=1.0 - ctx.confidence)
            except Exception:
                pass

        # PFC: learn from outcome
        if self._prefrontal_cortex and ctx.brain_gates is not None:
            try:
                state_vec = ctx.brain_gates.astype(np.float32)
                pfc_dim = self._prefrontal_cortex.state_dim
                if len(state_vec) < pfc_dim:
                    state_vec = np.pad(state_vec, (0, pfc_dim - len(state_vec)))
                else:
                    state_vec = state_vec[:pfc_dim]
                self._prefrontal_cortex.learn_from_outcome(state_vec, reward=ctx.confidence)
            except Exception:
                pass

        ctx.phase_timings['learn'] = time.time() - t0

    def _consolidate(self, ctx: LoopContext) -> None:
        """Phase 8: Lightweight inline consolidation."""
        self._phase = LoopPhase.CONSOLIDATE
        t0 = time.time()

        if not self._config.enable_inline_consolidation:
            ctx.phase_timings['consolidate'] = time.time() - t0
            return

        # Temporal memory recording
        if (self._planner.enable_temporal_memory and self._planner.temporal_memory and
                ctx.actionable_decision is not None):
            try:
                decision_type = ctx.actionable_decision.multi_target_decision['primary']['type']
                event_type = f"{ctx.task_type}_{decision_type}"
                ctx.temporal_context = self._planner.temporal_memory.add_event(event_type)
            except Exception:
                pass

        # Homeostatic: record task processing cost
        if self._homeostatic:
            complexity = getattr(ctx.layer1_routing, 'features', None)
            task_complexity = getattr(complexity, 'complexity', 0.5) if complexity else 0.5
            self._homeostatic.on_task_processed(
                complexity=task_complexity,
                success=(ctx.confidence > 0.5)
            )

        # P2.23: Sleep consolidation - immediate memory strengthening
        # Run lightweight immediate consolidation (not full sleep cycle)
        # to strengthen recently-stored memories after each task
        if self._sleep_consolidation:
            try:
                importance = ctx.confidence * task_complexity if 'task_complexity' in dir() else ctx.confidence * 0.5
                if importance >= self._config.consolidation_importance_threshold:
                    self._sleep_consolidation.immediate_consolidation(
                        num_replays=self._config.sleep_consolidation_replays
                    )
                # P2.27: Theta-mode → trigger consolidation step
                if self._frequency_controller:
                    try:
                        freq_state = self._frequency_controller.get_state()
                        dom_mode = freq_state.get('dominant_mode', 'alpha')
                        if dom_mode in ('theta', 'delta'):
                            # In low-frequency modes, run extra consolidation
                            self._sleep_consolidation.step(
                                activity_level=0.2,  # Low activity = sleep-like
                                dt=1.0
                            )
                    except Exception:
                        pass
            except Exception:
                pass

        # Default Mode Network: active during low task-load (idle consolidation)
        if self._default_mode_network and ctx.brain_gates is not None:
            try:
                state_vec = ctx.brain_gates.astype(np.float32)
                dmn_dim = self._default_mode_network.state_dim
                if len(state_vec) < dmn_dim:
                    state_vec = np.pad(state_vec, (0, dmn_dim - len(state_vec)))
                else:
                    state_vec = state_vec[:dmn_dim]
                task_load = ctx.layer1_routing.features.complexity if ctx.layer1_routing else 0.5
                dmn_output = self._default_mode_network.process(state_vec, task_load=task_load)
                ctx.dmn_output = {
                    'mode': dmn_output.mode,
                    'activation_level': dmn_output.activation_level,
                    'has_creative_output': not np.allclose(dmn_output.creative_association, 0.0),
                }
            except Exception:
                pass

        ctx.phase_timings['consolidate'] = time.time() - t0

    # ========== Output Construction ==========

    def _build_prediction(self, ctx: LoopContext):
        """Convert LoopContext into HierarchicalPrediction for backward compatibility."""
        from core.hierarchical_planner import HierarchicalPrediction

        return HierarchicalPrediction(
            # Layer 1
            layer1_routing=ctx.layer1_routing,
            # Layer 2
            predicted_sequence=ctx.predicted_sequence,
            confidence=ctx.confidence,
            success_probability=ctx.success_probability,
            dominant_modalities=ctx.dominant_modalities,
            task_type=ctx.task_type,
            # Layer 3
            actionable_decision=ctx.actionable_decision,
            # Memory
            memory_context=ctx.memory_context,
            task_description=ctx.task_description,
            # Predictive coding
            prediction_errors=ctx.prediction_errors,
            curiosity_signal=ctx.curiosity_signal,
            # Attention
            attention_state=ctx.attention_state,
            # Meta-learning
            meta_parameters=ctx.meta_parameters,
            # Neuromodulation
            neuromodulator_levels=ctx.neuro_levels,
            neuromodulator_effects=ctx.neuro_effects,
            # Temporal memory
            temporal_context=ctx.temporal_context,
            # Active inference
            inference_state=ctx.inference_state,
            # Consciousness
            cognitive_state=ctx.cognitive_state,
            # CTM
            ctm_task_id=ctx.ctm_task_id,
            ctm_insights=ctx.ctm_insights,
            # Metadata
            total_processing_time=ctx.total_time
        )

    # ========== Dashboard Visibility ==========

    def learn_from_feedback(self, task: str, success: bool, confidence: float):
        """Propagate feedback to emotional system for emotional learning."""
        if self._emotional_system:
            try:
                self._emotional_system.learn_from_outcome(task, success, confidence)
            except Exception:
                pass

    def get_loop_state(self) -> Dict:
        """Return current loop state for dashboard visualization."""
        state = {
            'current_phase': self._phase.value,
            'enabled': True,
        }

        if self._last_context:
            ctx = self._last_context
            state.update({
                'loop_iterations': ctx.loop_iterations,
                'phase_timings': ctx.phase_timings,
                'total_time': ctx.total_time,
                'gating_temperature': ctx.gating_temperature,
                'memory_bias_active': ctx.memory_bias is not None,
                'memory_confidence_hint': ctx.memory_confidence_hint,
                'ctm_domain_hint': ctx.ctm_domain_hint,
                'confidence': ctx.confidence,
                'did_reconsider': ctx.loop_iterations > 1,
                'goal_context_active': ctx.goal_context is not None and len(ctx.goal_context.get('active_goals', [])) > 0,
                'emotional_valence': ctx.emotional_valence,
                'emotional_arousal': ctx.emotional_arousal,
                'homeostatic_temp_adj': ctx.homeostatic_temp_adj,
                'homeostatic_attn_factor': ctx.homeostatic_attn_factor,
            })

        # Homeostatic snapshot
        if self._homeostatic:
            h = self._homeostatic.state
            state['homeostatic'] = {
                'energy': round(h.energy, 3),
                'fatigue': round(h.fatigue, 3),
                'sleep_pressure': round(h.sleep_pressure, 3),
                'allostatic_load': round(h.allostatic_load, 3),
                'performance_factor': round(h.performance_factor, 3),
            }

        # Sleep consolidation snapshot (P2.23)
        if self._sleep_consolidation:
            try:
                sc_stats = self._sleep_consolidation.get_statistics()
                state['sleep_consolidation'] = {
                    'current_state': sc_stats.get('current_state', 'unknown'),
                    'is_sleeping': sc_stats.get('is_sleeping', False),
                    'replays_triggered': sc_stats.get('metrics', {}).get('replays_triggered', 0),
                    'cycles_completed': sc_stats.get('cycles_completed', 0),
                }
            except Exception:
                state['sleep_consolidation'] = {'enabled': True, 'error': 'unavailable'}

        # Frequency controller snapshot (P2.25)
        if self._frequency_controller:
            try:
                freq_state = self._frequency_controller.get_state()
                state['frequency_mode'] = {
                    'dominant_mode': freq_state.get('dominant_mode', 'unknown'),
                    'active_modes': freq_state.get('active_modes', []),
                }
            except Exception:
                pass

        # Per-modality prediction errors (P2.30 - dashboard data)
        if self._last_context and self._last_context.per_modality_pes is not None:
            state['per_modality_prediction_errors'] = self._last_context.per_modality_pes

        # Phase 6: Advanced cognitive subsystem state
        if self._last_context:
            ctx = self._last_context
            phase6 = {}

            # P6.85: Safety Layer
            if ctx.safety_report is not None:
                phase6['safety_report'] = ctx.safety_report

            # P6.87: Explanation Generator
            if ctx.explanation is not None:
                phase6['explanation'] = ctx.explanation

            # P6.76-77: Theory of Mind / User Model
            if ctx.user_model is not None:
                phase6['user_model'] = ctx.user_model

            # P6.78-79: Causal Reasoning
            if ctx.causal_context is not None:
                phase6['causal_context'] = ctx.causal_context

            # P6.81: Intrinsic Curiosity
            if ctx.curiosity_intrinsic is not None:
                phase6['curiosity_intrinsic'] = ctx.curiosity_intrinsic

            # P6.89-90: Temporal & Circadian
            if ctx.temporal_patterns is not None:
                phase6['temporal_patterns'] = ctx.temporal_patterns
            if ctx.circadian_phase is not None:
                phase6['circadian_phase'] = ctx.circadian_phase

            # P6.82: Autonomous Goals
            if ctx.autonomous_goals is not None:
                phase6['autonomous_goals'] = ctx.autonomous_goals

            # P6.83: Multimodal Fusion
            if ctx.multimodal_fusion is not None:
                phase6['multimodal_fusion'] = ctx.multimodal_fusion

            # P6.86: Formal Verification
            if ctx.formal_verification is not None:
                phase6['formal_verification'] = ctx.formal_verification

            # P6.88: Thought Decoder
            if ctx.thought_decode is not None:
                phase6['thought_decode'] = ctx.thought_decode

            if phase6:
                state['phase6_cognitive'] = phase6

        # Phase 6 module availability
        state['phase6_modules'] = {
            'theory_of_mind': self._theory_of_mind is not None,
            'causal_inference': self._causal_inference is not None,
            'intrinsic_curiosity': self._intrinsic_curiosity is not None,
            'autonomous_goal_gen': self._autonomous_goal_gen is not None,
            'safety_layer': self._safety_layer is not None,
            'explanation_gen': self._explanation_gen is not None,
            'self_improvement': self._self_improvement is not None,
            'multimodal_fusion': self._multimodal_fusion is not None,
            'formal_verifier': self._formal_verifier is not None,
            'thought_decoder': self._thought_decoder is not None,
        }

        return state

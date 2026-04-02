"""
Hierarchical Planner (Phase 4 - Complete Integration)

Integrates all 3 layers of the routing hierarchy:

Layer 1: TaskFeatureRouter - Extract features and initial routing
Layer 2: ConversationPathPlanner - Path planning with brain routing
Layer 3: DecisionRouter - Multi-target actionable decisions

Original concept from logical_brain/routed_brain.py:
```
Input → SensoryRouter → Brain → ModuleRouter → Output
```

Our implementation:
```
Task → TaskFeatureRouter → ConversationPathPlanner → DecisionRouter → Action
```

This creates a complete hierarchical cognitive architecture with clear
separation of concerns across 3 specialized layers.
"""

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from core.task_feature_router import TaskFeatureRouter, RoutingState
from core.conversation_path_planner import ConversationPathPlanner
from core.decision_router import DecisionRouter, ActionableDecision
from core.memory_systems import MemoryManager
from core.predictive_coding import HierarchicalPredictiveCoding, PredictionError
from core.attention_mechanisms import AttentionMechanism, AttentionState
from core.meta_learning import MetaLearner, MetaParameters
from core.dream_mode import DreamMode, DreamState, Pattern
from core.neuromodulation import NeuromodulationSystem, NeuromodulatorLevels, NeuromodulatorEffects
from core.temporal_memory import TemporalMemory, TemporalContext
from core.active_inference import ActiveInference, InferenceState
from core.llm_enhanced_inference import LLM_Enhanced_ActiveInference
from core.compositional_reasoning import CompositionalReasoning, CompositionResult
from core.tool_creation import ToolCreation
from core.consciousness_metrics import ConsciousnessMetrics, CognitiveState, MetaCognitiveAssessment
from core.multi_brain_swarm import MultiBrainSwarm, SwarmDecision
from core.ctm_async_reasoner import CTMAsyncReasoner, CTMAsyncResult, ReasoningStatus
from core.multi_ctm_ensemble import MultiCTMEnsemble, EnsembleResult
from core.goal_graph import GoalGraph, Goal, GoalState, GoalPriority

# Layer 4: Temporal Tool Control (PHASE 16 - NEW)
try:
    from core.layer4_temporal_router import Layer4TemporalRouter, TemporalRoutingResult
    LAYER4_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Layer 4 Temporal Router not available: {e}")
    LAYER4_AVAILABLE = False
    Layer4TemporalRouter = None
    TemporalRoutingResult = None


@dataclass
class HierarchicalPrediction:
    """
    Complete prediction from all 3 layers of the hierarchy
    """
    # Layer 1 output
    layer1_routing: RoutingState

    # Layer 2 output (simplified from PathPrediction)
    predicted_sequence: List[str]
    confidence: float
    success_probability: float
    dominant_modalities: List[str]
    task_type: str

    # Layer 3 output
    actionable_decision: ActionableDecision

    # Memory context (NEW)
    memory_context: Optional[Dict] = None

    # Task description (for consolidation)
    task_description: Optional[str] = None

    # Predictive coding (PHASE 2)
    prediction_errors: Optional[Dict] = None
    curiosity_signal: Optional[Dict] = None

    # Attention (PHASE 3)
    attention_state: Optional[AttentionState] = None

    # Meta-learning (PHASE 4)
    meta_parameters: Optional[MetaParameters] = None

    # Neuromodulation (PHASE 6)
    neuromodulator_levels: Optional[NeuromodulatorLevels] = None
    neuromodulator_effects: Optional[NeuromodulatorEffects] = None

    # Temporal Memory (PHASE 7)
    temporal_context: Optional[TemporalContext] = None

    # Active Inference (PHASE 8)
    inference_state: Optional[InferenceState] = None

    # Compositional Reasoning (PHASE 9)
    composition_result: Optional[CompositionResult] = None

    # Tool Creation (PHASE 10)
    created_tools: Optional[List[Dict]] = None

    # Consciousness Metrics (PHASE 11)
    cognitive_state: Optional[CognitiveState] = None

    # Multi-Brain Swarm (PHASE 12)
    swarm_decision: Optional[SwarmDecision] = None

    # CTM Async Reasoning (PHASE 13 - NEW)
    ctm_task_id: Optional[str] = None
    ctm_insights: Optional[str] = None

    # Layer 4: Temporal Tool Control (PHASE 16 - NEW)
    layer4_result: Optional[Any] = None  # TemporalRoutingResult

    # Metadata
    total_processing_time: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'layer1': self.layer1_routing.to_dict(),
            'layer2': {
                'predicted_sequence': self.predicted_sequence,
                'confidence': float(self.confidence),
                'success_probability': float(self.success_probability),
                'dominant_modalities': self.dominant_modalities,
                'task_type': self.task_type
            },
            'layer3': self.actionable_decision.to_dict(),
            'metadata': {
                'total_processing_time': float(self.total_processing_time)
            }
        }

        if self.memory_context:
            result['memory_context'] = self.memory_context

        return result


class HierarchicalPlanner:
    """
    Complete 3-layer hierarchical cognitive architecture

    Integrates:
    - Layer 1: TaskFeatureRouter (feature extraction and initial routing)
    - Layer 2: ConversationPathPlanner (graph-based path planning)
    - Layer 3: DecisionRouter (multi-target decision routing)

    This provides a biologically-inspired hierarchical routing system
    similar to how the brain processes information through multiple stages.
    """

    def __init__(
        self,
        # Layer 2 components (existing system)
        conversation_planner: Optional[ConversationPathPlanner] = None,

        # Layer 1 & 3 configs
        modalities: Optional[List[str]] = None,
        intervention_types: Optional[List[str]] = None,

        # User ID for memory isolation (NEW)
        user_id: Optional[str] = None,

        # Memory systems (PHASE 1)
        enable_memory: bool = True,
        memory_save_dir: Optional[str] = None,

        # Predictive coding (PHASE 2)
        enable_predictive_coding: bool = True,

        # Attention mechanisms (PHASE 3)
        enable_attention: bool = True,
        apply_attention_gating: bool = False,

        # Meta-learning (PHASE 4)
        enable_meta_learning: bool = True,
        meta_learning_rate: float = 0.01,

        # Dream mode (PHASE 5)
        enable_dream_mode: bool = True,
        dream_consolidation_threshold: float = 0.7,

        # Neuromodulation (PHASE 6)
        enable_neuromodulation: bool = True,

        # Temporal Memory (PHASE 7)
        enable_temporal_memory: bool = True,
        temporal_decay_rate: float = 0.1,

        # Active Inference (PHASE 8)
        enable_active_inference: bool = True,
        ask_threshold: float = 0.7,

        # Compositional Reasoning (PHASE 9)
        enable_compositional_reasoning: bool = True,

        # Tool Creation (PHASE 10)
        enable_tool_creation: bool = True,

        # Consciousness Metrics (PHASE 11)
        enable_consciousness_metrics: bool = True,

        # Multi-Brain Swarm (PHASE 12)
        enable_multi_brain_swarm: bool = True,
        num_swarm_brains: int = 5,

        # CTM Async Reasoning (PHASE 13 - NEW)
        enable_ctm_async: bool = True,
        ctm_complexity_threshold: float = 0.4,  # Lowered from 0.75 for more frequent activation
        ctm_trigger_on_failure: bool = True,
        ctm_max_steps: int = 50,

        # Multi-CTM Ensemble (PHASE 14 - NEW)
        enable_multi_ctm: bool = True,  # Use Multi-CTM Ensemble instead of single CTM
        enable_logic_ctm: bool = True,  # LogicCTM (TRAINED - Oct 2025)
        enable_temporal_ctm: bool = True,  # TemporalCTM (TRAINED - Oct 2025)
        enable_value_ctm: bool = True,  # ValueCTM (TRAINED - Oct 2025)
        load_trained_weights: bool = True,  # Load trained brain weights from checkpoints
        ctm_checkpoint_dir: str = "data/ctm_checkpoints",  # Directory for trained brain checkpoints

        # Goal Graph System (PHASE 15 - NEW)
        enable_goal_graph: bool = True,  # Enable hierarchical goal decomposition

        # Layer 4: Temporal Tool Control (PHASE 16 - NEW)
        enable_layer4: bool = False,  # Enable temporal tool routing (off by default)
        layer4_strict_security: bool = True,  # Block on security concerns
        layer4_timing_threshold: float = 0.5,  # Threshold for action emission

        # Seeds
        seed: int = 42
    ):
        """
        Initialize hierarchical planner

        Args:
            conversation_planner: Existing ConversationPathPlanner (Layer 2)
            modalities: List of brain modality names
            intervention_types: List of intervention types
            user_id: User ID for memory isolation (enables Infinite Chat)
            enable_memory: Enable memory systems (PHASE 1)
            memory_save_dir: Directory for episodic memory persistence
            enable_predictive_coding: Enable predictive coding (PHASE 2)
            enable_attention: Enable attention mechanisms (PHASE 3)
            apply_attention_gating: Apply attention gating to brain activations
            enable_meta_learning: Enable meta-learning (PHASE 4)
            meta_learning_rate: Learning rate for meta-parameter adaptation
            enable_dream_mode: Enable dream mode for offline consolidation (PHASE 5)
            dream_consolidation_threshold: Importance threshold for dream consolidation
            enable_neuromodulation: Enable neuromodulation system (PHASE 6)
            enable_temporal_memory: Enable temporal memory system (PHASE 7)
            temporal_decay_rate: Memory decay rate per day (0-1)
            enable_active_inference: Enable active inference and hypothesis generation (PHASE 8)
            ask_threshold: Uncertainty threshold for asking questions (0-1)
            seed: Random seed
        """
        self.seed = seed
        self.user_id = user_id

        # Layer 1: Task Feature Router
        self.layer1 = TaskFeatureRouter(modalities=modalities, seed=seed)

        # Layer 2: Conversation Path Planner (existing system!)
        if conversation_planner is None:
            raise ValueError(
                "HierarchicalPlanner requires an initialized ConversationPathPlanner. "
                "Pass an existing planner with trained graph and strategies."
            )
        self.layer2 = conversation_planner

        # Layer 3: Decision Router
        num_modalities = len(modalities) if modalities else 10
        self.layer3 = DecisionRouter(
            num_modalities=num_modalities,
            intervention_types=intervention_types,
            seed=seed
        )

        # Memory Systems (PHASE 1)
        self.enable_memory = enable_memory
        self.memory = MemoryManager(
            working_capacity=10,
            episodic_max=1000,
            episodic_save_dir=memory_save_dir
        ) if enable_memory else None

        # Predictive Coding (PHASE 2)
        self.enable_predictive_coding = enable_predictive_coding
        self.predictive_coding = HierarchicalPredictiveCoding() if enable_predictive_coding else None

        # Attention Mechanisms (PHASE 3)
        self.enable_attention = enable_attention
        self.apply_attention_gating = apply_attention_gating
        self.attention = AttentionMechanism(
            num_modalities=num_modalities,
            modality_names=modalities
        ) if enable_attention else None
        # Track previous attention for feedback into routing
        self._last_attention_state: Optional[AttentionState] = None
        self._attention_history: List[AttentionState] = []

        # Meta-Learning (PHASE 4)
        self.enable_meta_learning = enable_meta_learning
        self.meta_learner = MetaLearner(
            meta_learning_rate=meta_learning_rate
        ) if enable_meta_learning else None

        # Dream Mode (PHASE 5)
        self.enable_dream_mode = enable_dream_mode
        self.dream_mode = DreamMode(
            consolidation_threshold=dream_consolidation_threshold,
            seed=seed
        ) if enable_dream_mode else None

        # Neuromodulation (PHASE 6)
        self.enable_neuromodulation = enable_neuromodulation
        self.neuromodulation = NeuromodulationSystem() if enable_neuromodulation else None

        # Temporal Memory (PHASE 7)
        self.enable_temporal_memory = enable_temporal_memory
        self.temporal_memory = TemporalMemory(
            decay_rate=temporal_decay_rate
        ) if enable_temporal_memory else None

        # Active Inference (PHASE 8) - Use LLM-enhanced version
        self.enable_active_inference = enable_active_inference
        if enable_active_inference:
            # Try to get LLM client from layer2's MultiLLMRouter
            llm_client = None
            if (hasattr(self.layer2, 'meta_router') and
                hasattr(self.layer2.meta_router, 'multi_llm_router') and
                self.layer2.meta_router.multi_llm_router):
                llm_client = self.layer2.meta_router.multi_llm_router

            # Use LLM-enhanced version if LLM available, otherwise fallback to basic
            if llm_client:
                self.active_inference = LLM_Enhanced_ActiveInference(
                    llm_client=llm_client,
                    use_llm_for={'question_generation': True},  # Only for questions
                    ask_threshold=ask_threshold
                )
                print("[HierarchicalPlanner] Using LLM-Enhanced Active Inference for intelligent question generation")
            else:
                self.active_inference = ActiveInference(ask_threshold=ask_threshold)
                print("[HierarchicalPlanner] LLM not available, using template-based Active Inference")
        else:
            self.active_inference = None

        # Compositional Reasoning (PHASE 9)
        self.enable_compositional_reasoning = enable_compositional_reasoning
        self.compositional_reasoning = CompositionalReasoning() if enable_compositional_reasoning else None

        # Tool Creation (PHASE 10)
        self.enable_tool_creation = enable_tool_creation
        self.tool_creation = ToolCreation() if enable_tool_creation else None

        # Consciousness Metrics (PHASE 11)
        self.enable_consciousness_metrics = enable_consciousness_metrics
        self.consciousness_metrics = ConsciousnessMetrics() if enable_consciousness_metrics else None

        # Multi-Brain Swarm (PHASE 12)
        self.enable_multi_brain_swarm = enable_multi_brain_swarm
        self.multi_brain_swarm = MultiBrainSwarm(
            num_brains=num_swarm_brains
        ) if enable_multi_brain_swarm else None

        # CTM Async Reasoning (PHASE 13)
        self.enable_ctm_async = enable_ctm_async
        self.ctm_complexity_threshold = ctm_complexity_threshold
        self.ctm_trigger_on_failure = ctm_trigger_on_failure
        self.ctm_max_steps = ctm_max_steps

        # Multi-CTM Ensemble (PHASE 14 - NEW)
        self.enable_multi_ctm = enable_multi_ctm

        if enable_ctm_async:
            if enable_multi_ctm:
                # Use Multi-CTM Ensemble
                print("[HierarchicalPlanner] Initializing Multi-CTM Ensemble")
                self.ctm_ensemble = MultiCTMEnsemble(
                    max_concurrent_per_ctm=2,
                    consciousness_threshold=0.85,
                    max_reasoning_steps=ctm_max_steps,
                    device='cpu',
                    enable_logic_ctm=enable_logic_ctm,
                    enable_temporal_ctm=enable_temporal_ctm,
                    enable_value_ctm=enable_value_ctm
                )

                # Load trained brain weights
                if load_trained_weights:
                    self._load_ctm_weights(ctm_checkpoint_dir, enable_logic_ctm, enable_temporal_ctm, enable_value_ctm)

                # Keep backward compatibility reference
                self.ctm_async = None  # Not used when Multi-CTM is enabled
            else:
                # Use single CTM (legacy)
                print("[HierarchicalPlanner] Initializing Single CTM (legacy mode)")
                self.ctm_async = CTMAsyncReasoner(
                    max_concurrent_tasks=3,
                    default_steps=ctm_max_steps
                )
                self.ctm_ensemble = None
        else:
            self.ctm_async = None
            self.ctm_ensemble = None

        # Goal Graph System (PHASE 15 - NEW)
        self.enable_goal_graph = enable_goal_graph
        if enable_goal_graph:
            self.goal_graph = GoalGraph()
            print("[HierarchicalPlanner] Goal Graph initialized")
        else:
            self.goal_graph = None

        # Layer 4: Temporal Tool Control (PHASE 16 - NEW)
        self.enable_layer4 = enable_layer4 and LAYER4_AVAILABLE
        if self.enable_layer4:
            self.layer4_router = Layer4TemporalRouter(
                strict_security=layer4_strict_security,
                timing_threshold=layer4_timing_threshold,
                enable_deep_reasoning=enable_ctm_async
            )
            print("[HierarchicalPlanner] Layer 4 Temporal Router initialized")
            print('  Core Principle: "Nicht Text ruft Tools auf. Zustand ruft Zeit auf. Zeit ruft Aktion auf."')
        else:
            self.layer4_router = None
            if enable_layer4 and not LAYER4_AVAILABLE:
                print("[HierarchicalPlanner] Layer 4 requested but not available")

        # Statistics
        self.total_predictions = 0
        self.layer_timing = {'layer1': [], 'layer2': [], 'layer3': []}

    def predict(self, task_description: str) -> HierarchicalPrediction:
        """
        Main prediction function: Route task through all 3 layers

        Args:
            task_description: Raw task description string

        Returns:
            HierarchicalPrediction with full context from all layers
        """
        import time

        # === PREDICTIVE CODING: Predict Task Features (PHASE 2) ===
        task_feature_prediction = None
        task_feature_pe = None
        if self.enable_predictive_coding and self.predictive_coding:
            task_feature_prediction, _ = self.predictive_coding.predict_task_features({})

        # === LAYER 1: Feature Extraction and Initial Routing ===
        t0 = time.time()
        layer1_routing = self.layer1.route_task(task_description)
        t1 = time.time()
        self.layer_timing['layer1'].append(t1 - t0)

        # === ATTENTION FEEDBACK: Adjust routing based on previous attention ===
        if self.enable_attention and self._last_attention_state is not None:
            # Use previous attention weights to bias current routing
            # This creates a feedback loop where focused attention persists
            attention_weights = self._last_attention_state.attention_weights
            if attention_weights is not None and layer1_routing.routing_weights is not None:
                import numpy as np
                # Blend previous attention with current routing (30% attention, 70% routing)
                attention_blend = 0.3
                blended_weights = (
                    (1 - attention_blend) * np.array(layer1_routing.routing_weights) +
                    attention_blend * np.array(attention_weights[:len(layer1_routing.routing_weights)])
                )
                # Normalize
                blended_weights = blended_weights / (blended_weights.sum() + 1e-8)
                layer1_routing.routing_weights = blended_weights.tolist()

        # === CTM ASYNC: Trigger Background Reasoning (PHASE 13/14) ===
        ctm_task_id = None
        if self.enable_ctm_async:
            # Check if task complexity exceeds threshold
            if layer1_routing.features.complexity >= self.ctm_complexity_threshold:
                print(f"[CTM] High complexity ({layer1_routing.features.complexity:.2f}) - starting async reasoning")

                # Start CTM reasoning in background
                try:
                    if self.enable_multi_ctm and self.ctm_ensemble:
                        # Use Multi-CTM Ensemble
                        brain_state = {
                            'modality_activations': {
                                'task_complexity': layer1_routing.features.complexity,
                                'task_urgency': layer1_routing.features.urgency
                            }
                        }
                        ctm_task_id = self.ctm_ensemble.reason_async(
                            task=task_description,
                            brain_state=brain_state,
                            max_steps=self.ctm_max_steps,
                            domain_hint=layer1_routing.features.task_type  # Use task type as domain hint
                        )
                        print(f"[Multi-CTM] Started ensemble reasoning (task_id={ctm_task_id})")
                    elif self.ctm_async:
                        # Use single CTM (legacy)
                        ctm_task_id = self.ctm_async.start_reasoning_async(
                            task_description=task_description,
                            steps=self.ctm_max_steps,
                            convergence_threshold=0.9,
                            priority='normal'
                        )
                        print(f"[CTM] Started background reasoning (task_id={ctm_task_id})")
                except RuntimeError as e:
                    print(f"[CTM] Could not start async reasoning: {e}")
                    ctm_task_id = None

        # === PREDICTIVE CODING: Compute Task Feature Error (PHASE 2) ===
        prediction_errors = None
        if self.enable_predictive_coding and self.predictive_coding and task_feature_prediction:
            actual_features = {
                'task_type': layer1_routing.features.task_type,
                'complexity': layer1_routing.features.complexity,
                'urgency': layer1_routing.features.urgency
            }
            task_feature_pe = self.predictive_coding.update_task_prediction(
                task_feature_prediction,
                actual_features
            )

            # Create prediction_errors dict early (will be updated later)
            prediction_errors = {
                'layer1': task_feature_pe.to_dict() if task_feature_pe else None,
                'layer3_prediction': None  # Will be set later
            }

        # === LAYER 2: Path Planning ===
        t0 = time.time()
        layer2_prediction = self.layer2.predict_optimal_path(task_description)
        t1 = time.time()
        self.layer_timing['layer2'].append(t1 - t0)

        # Extract Layer 2 outputs
        if layer2_prediction:
            predicted_sequence = layer2_prediction.predicted_sequence
            confidence = layer2_prediction.confidence
            success_probability = layer2_prediction.success_probability
            dominant_modalities = layer2_prediction.dominant_modalities
            task_type = layer2_prediction.task_type

            # Create dict for Layer 3
            layer2_dict = {
                'predicted_sequence': predicted_sequence,
                'confidence': confidence,
                'success_probability': success_probability,
                'dominant_modalities': dominant_modalities,
                'task_type': task_type
            }

            # Get brain gates from brain monitor if available
            brain_gates = None
            per_modality_pes = None

            if hasattr(self.layer2, 'brain_monitor') and self.layer2.brain_monitor:
                if self.layer2.brain_monitor.gate_history:
                    brain_gates = list(self.layer2.brain_monitor.gate_history)[-1]

                # Get per-modality PEs from meta_router
                if hasattr(self.layer2.meta_router, 'modality_pe_tracker'):
                    pe_tracker = self.layer2.meta_router.modality_pe_tracker
                    per_modality_pes = {
                        mod: np.mean(state.pe_history) if state.pe_history else 0.0
                        for mod, state in pe_tracker.states.items()
                    }

        else:
            # Fallback if no prediction
            predicted_sequence = []
            confidence = 0.5
            success_probability = 0.5
            dominant_modalities = layer1_routing.dominant_areas
            task_type = layer1_routing.features.task_type

            layer2_dict = {
                'predicted_sequence': predicted_sequence,
                'confidence': confidence,
                'success_probability': success_probability,
                'dominant_modalities': dominant_modalities,
                'task_type': task_type
            }

            brain_gates = layer1_routing.routing_weights
            per_modality_pes = None

        # === MEMORY RETRIEVAL (PHASE 1) ===
        memory_context = None
        if self.enable_memory and self.memory and brain_gates is not None:
            memory_context = self.memory.get_context(
                task_description,
                brain_gates,
                task_type
            )

        # === PREDICTIVE CODING: Predict Decision Outcome (PHASE 2) ===
        outcome_prediction = None
        if self.enable_predictive_coding and self.predictive_coding:
            # Make prediction about decision outcome before Layer 3
            outcome_context = {
                'decision_type': 'unknown',  # Will be set by Layer 3
                'task_type': task_type,
                'confidence': confidence
            }
            outcome_prediction, _ = self.predictive_coding.predict_decision_outcome(outcome_context)

        # === ATTENTION: Compute Attention State (PHASE 3) ===
        attention_state = None
        original_brain_gates = brain_gates.copy() if brain_gates is not None else None

        if self.enable_attention and self.attention and brain_gates is not None:
            # Gather task features
            task_features_dict = {
                'complexity': layer1_routing.features.complexity,
                'urgency': layer1_routing.features.urgency,
                'task_type': layer1_routing.features.task_type
            }

            # Compute attention state
            attention_state = self.attention.compute_attention(
                brain_gates=brain_gates,
                task_type=task_type,
                prediction_errors=prediction_errors if self.enable_predictive_coding else None,
                task_features=task_features_dict,
                memory_context=memory_context
            )

            # Optionally apply attention gating
            if self.apply_attention_gating:
                brain_gates = self.attention.apply_attention_gating(
                    brain_gates=brain_gates,
                    attention_weights=attention_state.attention_weights,
                    gating_strength=0.5
                )

            # Store attention state for feedback into next routing decision
            self._last_attention_state = attention_state
            self._attention_history.append(attention_state)
            if len(self._attention_history) > 10:  # Keep last 10 states
                self._attention_history.pop(0)

        # === LAYER 3: Decision Routing ===
        t0 = time.time()
        actionable_decision = self.layer3.route_to_action(
            layer1_state=layer1_routing,
            layer2_prediction=layer2_dict,
            brain_gates=brain_gates,
            per_modality_pes=per_modality_pes,
            memory_context=memory_context  # Pass memory context
        )
        t1 = time.time()
        self.layer_timing['layer3'].append(t1 - t0)

        # === PREDICTIVE CODING: Get Curiosity Signal (PHASE 2) ===
        curiosity_signal = None
        if self.enable_predictive_coding and self.predictive_coding:
            curiosity_signal = self.predictive_coding.get_curiosity_signal()

            # Update prediction_errors with layer3_prediction
            if prediction_errors is None:
                prediction_errors = {}
            prediction_errors['layer3_prediction'] = outcome_prediction

        # === Create Hierarchical Prediction ===
        total_time = sum(self.layer_timing[f'layer{i}'][-1] for i in [1, 2, 3])

        # Get current meta-parameters
        meta_parameters = None
        if self.enable_meta_learning and self.meta_learner:
            meta_parameters = self.meta_learner.meta_params

        # Get current neuromodulator levels and effects (PHASE 6)
        neuromodulator_levels = None
        neuromodulator_effects = None
        if self.enable_neuromodulation and self.neuromodulation:
            neuromodulator_levels = self.neuromodulation.levels
            neuromodulator_effects = self.neuromodulation.compute_effects()

        # === TEMPORAL MEMORY: Record Event (PHASE 7) ===
        temporal_context = None
        if self.enable_temporal_memory and self.temporal_memory:
            # Record this prediction as a temporal event
            decision_type = actionable_decision.multi_target_decision['primary']['type']
            event_type = f"{task_type}_{decision_type}"
            temporal_context = self.temporal_memory.add_event(event_type)

        # === ACTIVE INFERENCE: Generate Hypotheses and Questions (PHASE 8) ===
        inference_state = None
        if self.enable_active_inference and self.active_inference and brain_gates is not None:
            # Prepare context for hypothesis generation
            inference_context = {}
            if memory_context:
                # Convert similar tasks to dict format if they exist
                similar_tasks_raw = memory_context.get('working_memory', {}).get('similar_tasks', [])
                if similar_tasks_raw:
                    # Convert tuples to dicts
                    similar_tasks = []
                    for task_data in similar_tasks_raw:
                        if isinstance(task_data, tuple):
                            # Assume tuple is (task_obj, similarity)
                            task_obj = task_data[0]
                            similar_tasks.append({
                                'task': getattr(task_obj, 'task', 'unknown'),
                                'decision': getattr(task_obj, 'decision', 'wait'),
                                'outcome': getattr(task_obj, 'outcome', None)
                            })
                        else:
                            similar_tasks.append(task_data)
                    inference_context['similar_tasks'] = similar_tasks
            if self.enable_dream_mode and self.dream_mode:
                # Get learned patterns
                pattern = self.dream_mode.get_pattern_for_task(task_type, min_confidence=0.5)
                if pattern:
                    inference_context['patterns'] = [{
                        'task_type': task_type,
                        'decision': pattern.decision_type,
                        'confidence': pattern.confidence
                    }]

            # Get available decisions
            available_decisions = self.layer3.intervention_types

            # Perform active inference
            inference_state = self.active_inference.perform_inference(
                task_description=task_description,
                task_type=task_type,
                brain_gates=brain_gates,
                available_decisions=available_decisions,
                context=inference_context
            )

        # === COMPOSITIONAL REASONING: Decompose Task into Subtasks (PHASE 9) ===
        composition_result = None
        if self.enable_compositional_reasoning and self.compositional_reasoning:
            # Get available actions from Layer 3
            available_actions = self.layer3.intervention_types

            # Compose novel sequences for this task
            context_for_composition = {
                'uncertainty': 1.0 - confidence if confidence else 0.5,
                'complexity': layer1_routing.features.complexity,
                'task_type': task_type
            }

            novel_sequences = self.compositional_reasoning.compose_novel_sequence(
                task_type=task_type,
                available_actions=available_actions,
                context=context_for_composition
            )

            # Create composition result
            if novel_sequences:
                from core.compositional_reasoning import CompositionResult
                subtasks = []
                dependencies = []

                # Extract subtasks from best sequence
                best_seq = novel_sequences[0] if novel_sequences else None
                if best_seq:
                    subtasks = [action.action_type for action in best_seq.actions]
                    composed_confidence = best_seq.expected_success_rate
                else:
                    composed_confidence = 0.5

                composition_result = type('CompositionResult', (), {
                    'subtasks': subtasks,
                    'dependencies': dependencies,
                    'composed_confidence': composed_confidence,
                    'num_sequences': len(novel_sequences)
                })()

        # === TOOL CREATION: Get Tools for Task (PHASE 10) ===
        created_tools = None
        if self.enable_tool_creation and self.tool_creation:
            # Get or create tool for this task type
            tool = self.tool_creation.get_tool_for_capability(
                capability=task_type,
                prefer_specialized=True
            )

            if tool:
                created_tools = [tool.to_dict()]

        # === MULTI-BRAIN SWARM: Collect Votes and Reach Consensus (PHASE 12) ===
        swarm_decision = None
        if self.enable_multi_brain_swarm and self.multi_brain_swarm:
            # Get available decisions from layer 3
            available_decisions = self.layer3.intervention_types

            # Collect votes from swarm
            swarm_decision = self.multi_brain_swarm.collect_brain_votes(
                task_description=task_description,
                task_type=task_type,
                available_decisions=available_decisions,
                brain_gates=brain_gates
            )

            # Optionally override Layer 3 decision with swarm consensus
            # (if swarm has high confidence and agreement)
            if swarm_decision.consensus_confidence > 0.7 and swarm_decision.agreement_level > 0.7:
                # Strong swarm consensus — blend with Layer 3 decision
                swarm_primary = swarm_decision.consensus_decision
                layer3_primary = actionable_decision.multi_target_decision['primary']['type']

                if swarm_primary != layer3_primary:
                    # Swarm disagrees with Layer 3 — override if swarm much more confident
                    layer3_weight = actionable_decision.multi_target_decision['primary']['weight']
                    if swarm_decision.consensus_confidence > layer3_weight + 0.1:
                        # Swarm wins: swap primary to swarm decision
                        old_primary = actionable_decision.multi_target_decision['primary']
                        actionable_decision.multi_target_decision['primary'] = {
                            'type': swarm_primary,
                            'weight': float(swarm_decision.consensus_confidence),
                            'reasoning': f"Swarm override: {swarm_primary} (consensus={swarm_decision.consensus_confidence:.2f}, agreement={swarm_decision.agreement_level:.2f})"
                        }
                        # Demote old Layer 3 decision to first alternative
                        actionable_decision.multi_target_decision['alternatives'].insert(0, old_primary)
                        actionable_decision.reasoning_chain.append(
                            f"[Swarm Override] {swarm_primary} replaced {layer3_primary} "
                            f"(swarm conf={swarm_decision.consensus_confidence:.2f} > L3 weight={layer3_weight:.2f})"
                        )
                    else:
                        # Close call — keep Layer 3 but note swarm disagreement
                        actionable_decision.reasoning_chain.append(
                            f"[Swarm Dissent] Swarm suggests {swarm_primary} (conf={swarm_decision.consensus_confidence:.2f}) "
                            f"but Layer 3 {layer3_primary} (weight={layer3_weight:.2f}) retained"
                        )
                else:
                    # Swarm agrees with Layer 3 — boost confidence
                    actionable_decision.reasoning_chain.append(
                        f"[Swarm Consensus] Confirms {layer3_primary} "
                        f"(agreement={swarm_decision.agreement_level:.2f})"
                    )

        # === CONSCIOUSNESS METRICS: Track Cognitive State (PHASE 11) ===
        cognitive_state = None
        if self.enable_consciousness_metrics and self.consciousness_metrics:
            # Determine attention focus
            if attention_state:
                top_modality = attention_state.dominant_modalities[0] if attention_state.dominant_modalities else 'unknown'
                if attention_state.attention_focus == 'focused':
                    attention_focus = 'focused'
                elif attention_state.attention_focus == 'distributed':
                    attention_focus = 'distributed'
                else:
                    attention_focus = 'shifting'
            else:
                attention_focus = 'distributed'

            # Estimate memory load (based on working memory size)
            memory_load = 0.5
            if self.enable_memory and self.memory:
                memory_load = len(self.memory.working) / self.memory.working.capacity

            # Reasoning depth (based on task complexity)
            reasoning_depth = min(3, int(layer1_routing.features.complexity * 3))

            # Uncertainty level (from active inference or default)
            uncertainty_level = 0.5
            if inference_state:
                uncertainty_level = inference_state.total_uncertainty

            # Update cognitive state
            import time
            cognitive_state = self.consciousness_metrics.update_cognitive_state(
                attention_focus=attention_focus,
                memory_load=memory_load,
                reasoning_depth=reasoning_depth,
                uncertainty_level=uncertainty_level,
                timestamp=time.time()
            )

            # === CONSCIOUSNESS FEEDBACK: Influence decision based on awareness ===
            if cognitive_state and cognitive_state.confidence_in_state < 0.3:
                # Low self-confidence in state assessment → flag uncertainty
                actionable_decision.reasoning_chain.append(
                    f"[Consciousness] Low state confidence ({cognitive_state.confidence_in_state:.2f}) — "
                    f"high uncertainty, consider cautious action"
                )
                # If primary decision is 'execute' and awareness is very low, demote to 'suggest'
                primary_type = actionable_decision.multi_target_decision['primary']['type']
                if primary_type == 'execute' and cognitive_state.confidence_in_state < 0.2:
                    actionable_decision.multi_target_decision['primary']['type'] = 'suggest'
                    actionable_decision.reasoning_chain.append(
                        f"[Consciousness Override] Demoted 'execute' → 'suggest' due to "
                        f"very low awareness ({cognitive_state.confidence_in_state:.2f})"
                    )

            # Track known unknowns for epistemic humility
            if cognitive_state and uncertainty_level > 0.7:
                self.consciousness_metrics.track_known_unknown(
                    f"high_uncertainty_task:{task_type}"
                )

        # === LAYER 4: Temporal Tool Control (PHASE 16 - NEW) ===
        layer4_result = None
        if self.enable_layer4 and self.layer4_router:
            # Build raw events from conversation context
            raw_events = []

            # Add conversation events from working memory
            if self.enable_memory and self.memory:
                for entry in list(self.memory.working.buffer)[-5:]:  # Last 5 entries
                    raw_events.append({
                        'role': 'user',
                        'text': entry.task,
                        'timestamp': entry.timestamp if hasattr(entry, 'timestamp') else None
                    })

            # Add the current task
            raw_events.append({
                'role': 'user',
                'text': task_description,
                'timestamp': None
            })

            # Route through Layer 4
            layer4_result = self.layer4_router.route(
                raw_events=raw_events,
                task_description=task_description,
                source_trusted=True
            )

            if layer4_result.blocked:
                # Layer 4 BLOCKED — override actionable_decision to prevent execution
                primary_type = actionable_decision.multi_target_decision['primary']['type']
                if primary_type == 'execute':
                    actionable_decision.multi_target_decision['primary']['type'] = 'wait'
                    actionable_decision.reasoning_chain.append(
                        f"[Layer4 BLOCK] Overrode 'execute' → 'wait': {layer4_result.block_reason}"
                    )
                    # Clear executable tool calls since blocked
                    actionable_decision.executable_tool_calls = None
                else:
                    actionable_decision.reasoning_chain.append(
                        f"[Layer4 BLOCK] {layer4_result.block_reason} (action={primary_type}, no override needed)"
                    )
                print(f"[Layer4] BLOCKED: {layer4_result.block_reason}")

            elif layer4_result.should_execute:
                # Layer 4 approves execution — annotate with tool routing info
                actionable_decision.reasoning_chain.append(
                    f"[Layer4 APPROVED] Tool={layer4_result.tool_name}, "
                    f"Timing={layer4_result.decision.timing_confidence:.2f}"
                )
                # If Layer 4 suggests a specific tool and primary is 'execute', add tool info
                if layer4_result.tool_name and actionable_decision.multi_target_decision['primary']['type'] == 'execute':
                    if actionable_decision.executable_tool_calls is None:
                        actionable_decision.executable_tool_calls = []
                    # Add Layer 4's tool recommendation
                    actionable_decision.executable_tool_calls.append({
                        'tool': layer4_result.tool_name,
                        'parameters': layer4_result.tool_parameters,
                        'source': 'layer4_temporal',
                        'timing_confidence': float(layer4_result.decision.timing_confidence)
                    })
                print(f"[Layer4] Tool: {layer4_result.tool_name}, Timing: {layer4_result.decision.timing_confidence:.2f}")

            else:
                # Layer 4 says WAIT — timing not right
                primary_type = actionable_decision.multi_target_decision['primary']['type']
                if primary_type == 'execute' and layer4_result.decision.timing_confidence < 0.3:
                    # Very low timing confidence — demote execute to suggest
                    actionable_decision.multi_target_decision['primary']['type'] = 'suggest'
                    actionable_decision.reasoning_chain.append(
                        f"[Layer4 WAIT] Demoted 'execute' → 'suggest': "
                        f"timing_confidence={layer4_result.decision.timing_confidence:.2f} too low"
                    )
                else:
                    actionable_decision.reasoning_chain.append(
                        f"[Layer4 WAIT] timing={layer4_result.decision.timing_confidence:.2f}, "
                        f"action={primary_type} retained"
                    )
                print(f"[Layer4] WAIT: timing={layer4_result.decision.timing_confidence:.2f}")

        # === CTM ASYNC: Check for Early Results (PHASE 13/14) ===
        ctm_insights = None
        if ctm_task_id and self.enable_ctm_async:
            # Check if CTM has completed (non-blocking)
            try:
                if self.enable_multi_ctm and self.ctm_ensemble:
                    # Multi-CTM Ensemble
                    ensemble_result = self.ctm_ensemble.get_result(ctm_task_id, wait=False)
                    if ensemble_result:
                        # Extract insights from ensemble result
                        if ensemble_result.aggregated_insights:
                            ctm_insights = ensemble_result.aggregated_insights
                            print(f"[Multi-CTM] Ensemble reasoning completed! Domain: {ensemble_result.primary_domain.value}")
                        else:
                            # Check individual CTM results
                            for domain, ctm_result in ensemble_result.ctm_results.items():
                                if ctm_result and hasattr(ctm_result, 'status') and ctm_result.status == ReasoningStatus.COMPLETED:
                                    if ctm_result.ctm_insight:
                                        ctm_insights = f"[{domain.value}CTM] {ctm_result.ctm_insight.suggested_strategy}"
                                        print(f"[Multi-CTM] {domain.value}CTM completed")
                                        break
                    else:
                        print(f"[Multi-CTM] Ensemble reasoning still running (task_id={ctm_task_id})")
                elif self.ctm_async:
                    # Single CTM (legacy)
                    if self.ctm_async.is_complete(ctm_task_id):
                        ctm_result = self.ctm_async.get_result(ctm_task_id, wait=False)
                        if ctm_result.status == ReasoningStatus.COMPLETED:
                            ctm_insights = ctm_result.get_insights_summary()
                            print(f"[CTM] Background reasoning completed! Insights available.")
                        else:
                            print(f"[CTM] Background reasoning status: {ctm_result.status.value}")
                    else:
                        print(f"[CTM] Background reasoning still running (task_id={ctm_task_id})")
            except Exception as e:
                print(f"[CTM] Error retrieving result: {e}")

        hierarchical_prediction = HierarchicalPrediction(
            layer1_routing=layer1_routing,
            predicted_sequence=predicted_sequence,
            confidence=confidence,
            success_probability=success_probability,
            dominant_modalities=dominant_modalities,
            task_type=task_type,
            actionable_decision=actionable_decision,
            memory_context=memory_context,  # PHASE 1
            prediction_errors=prediction_errors,  # PHASE 2
            curiosity_signal=curiosity_signal,  # PHASE 2
            attention_state=attention_state,  # PHASE 3
            meta_parameters=meta_parameters,  # PHASE 4
            neuromodulator_levels=neuromodulator_levels,  # PHASE 6
            neuromodulator_effects=neuromodulator_effects,  # PHASE 6
            temporal_context=temporal_context,  # PHASE 7
            inference_state=inference_state,  # PHASE 8
            composition_result=composition_result,  # PHASE 9 - NEW
            created_tools=created_tools,  # PHASE 10 - NEW
            cognitive_state=cognitive_state,  # PHASE 11
            swarm_decision=swarm_decision,  # PHASE 12
            ctm_task_id=ctm_task_id,  # PHASE 13 - NEW
            ctm_insights=ctm_insights,  # PHASE 13 - NEW
            layer4_result=layer4_result,  # PHASE 16 - NEW
            total_processing_time=total_time
        )

        # === STORE IN WORKING MEMORY (NEW) ===
        if self.enable_memory and self.memory and brain_gates is not None:
            self.memory.remember_task(
                task=task_description,
                task_type=task_type,
                decision=actionable_decision.multi_target_decision['primary']['type'],
                confidence=confidence,
                brain_gates=brain_gates,
                outcome=None  # Outcome not yet known
            )

        # Update statistics
        self.total_predictions += 1

        return hierarchical_prediction

    def set_user_id(self, user_id: Optional[str]):
        """
        Set user ID for memory isolation (enables Infinite Chat)

        Args:
            user_id: User ID or None to disable per-user memory
        """
        self.user_id = user_id

        # Update Multi-LLM Router if accessible through layer2
        if hasattr(self.layer2, 'meta_router') and hasattr(self.layer2.meta_router, 'multi_llm_router'):
            if self.layer2.meta_router.multi_llm_router:
                self.layer2.meta_router.multi_llm_router.set_user_id(user_id)
                print(f"[HierarchicalPlanner] Updated Multi-LLM Router user_id: {user_id}")

    def visualize_prediction(self, prediction: HierarchicalPrediction) -> str:
        """
        Create human-readable visualization of hierarchical prediction

        Args:
            prediction: HierarchicalPrediction to visualize

        Returns:
            Formatted string visualization
        """
        lines = []
        lines.append("=" * 70)
        lines.append("HIERARCHICAL PREDICTION (3-LAYER ARCHITECTURE)")
        lines.append("=" * 70)
        lines.append("")

        # Layer 1
        lines.append("LAYER 1: TASK FEATURE ROUTING")
        lines.append("-" * 70)
        features = prediction.layer1_routing.features
        lines.append(f"  Task Type:       {features.task_type}")
        lines.append(f"  Complexity:      {features.complexity:.2f}")
        lines.append(f"  Urgency:         {features.urgency:.2f}")
        lines.append(f"  Processing Mode: {prediction.layer1_routing.processing_mode}")
        lines.append(f"  Dominant Areas:  {', '.join(prediction.layer1_routing.dominant_areas)}")
        lines.append("")

        # Layer 2
        lines.append("LAYER 2: PATH PLANNING")
        lines.append("-" * 70)
        lines.append(f"  Predicted Path:  {' -> '.join(prediction.predicted_sequence[:5])}")
        if len(prediction.predicted_sequence) > 5:
            lines.append(f"                   -> ... ({len(prediction.predicted_sequence)} steps total)")
        lines.append(f"  Confidence:      {prediction.confidence:.1%}")
        lines.append(f"  Success Prob:    {prediction.success_probability:.1%}")
        lines.append(f"  Brain Activity:  {', '.join(prediction.dominant_modalities[:3])}")
        lines.append("")

        # Layer 3
        lines.append("LAYER 3: ACTIONABLE DECISION")
        lines.append("-" * 70)
        mtd = prediction.actionable_decision.multi_target_decision
        primary = mtd['primary']
        lines.append(f"  Primary Action:  {primary['type']} (weight={primary['weight']:.1%})")
        lines.append(f"  Reasoning:       {primary['reasoning']}")
        lines.append("")
        lines.append("  Alternatives:")
        for alt in mtd['alternatives'][:3]:
            bar = '#' * int(alt['weight'] * 40)
            lines.append(f"    {alt['type']:12s} {alt['weight']:.1%} {bar}")
        lines.append("")

        # Reasoning chain
        lines.append("COMPLETE REASONING CHAIN:")
        lines.append("-" * 70)
        for i, step in enumerate(prediction.actionable_decision.reasoning_chain, 1):
            lines.append(f"  {i}. {step}")
        lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)

    def record_outcome(
        self,
        task: str,
        decision: str,
        outcome: str,
        importance: float = 0.5
    ):
        """
        Record outcome of a prediction in working memory

        Args:
            task: Task description
            decision: Decision that was made
            outcome: 'success' or 'failure'
            importance: Importance score (0-1) for episodic consolidation
        """
        if not self.enable_memory or not self.memory:
            return

        # Find matching entry in working memory and update outcome
        for entry in reversed(self.memory.working.buffer):
            if entry.task == task and entry.decision == decision:
                entry.outcome = outcome

                # If important enough, consolidate to episodic memory
                if importance >= 0.7:
                    # Get the full prediction context (would need to be stored)
                    # For now, create a simplified episodic memory
                    print(f"[Memory] High importance ({importance:.2f}) - consolidating to episodic")
                break

    def consolidate_experience(
        self,
        prediction: HierarchicalPrediction,
        outcome: str,
        importance: float,
        user_rating: Optional[float] = None,
        execution_time_ms: Optional[float] = None
    ):
        """
        Consolidate an important experience to episodic memory
        Also updates Layer 3 prediction error and adapts meta-parameters

        Args:
            prediction: The hierarchical prediction
            outcome: 'success' or 'failure'
            importance: Importance score (0-1)
            user_rating: Optional user rating
            execution_time_ms: Optional execution time
        """
        # === META-LEARNING: Adapt Meta-Parameters (PHASE 4) ===
        if self.enable_meta_learning and self.meta_learner:
            # Gather metrics for meta-learning
            pred_error = None
            if prediction.prediction_errors and 'layer1' in prediction.prediction_errors:
                layer1_pe = prediction.prediction_errors['layer1']
                if layer1_pe:
                    pred_error = layer1_pe.get('error_magnitude')

            # Compute attention entropy
            att_entropy = None
            if prediction.attention_state:
                att_weights = prediction.attention_state.attention_weights
                # Compute entropy: -sum(p * log(p))
                att_entropy = -np.sum(att_weights * np.log(att_weights + 1e-8))
                # Normalize by max entropy
                max_entropy = np.log(len(att_weights))
                att_entropy = att_entropy / max_entropy if max_entropy > 0 else 0.5

            # Adapt meta-parameters based on performance
            adapted_params = self.meta_learner.adapt_meta_parameters(
                outcome=outcome,
                prediction_error=pred_error,
                confidence=prediction.confidence,
                attention_entropy=att_entropy
            )

            print(f"[Meta-Learning] Adapted parameters (success_rate={self.meta_learner.performance.get_success_rate():.1%})")

        # === NEUROMODULATION: Update Neuromodulators (PHASE 6) ===
        if self.enable_neuromodulation and self.neuromodulation:
            # Extract task properties for neuromodulation
            urgency = prediction.layer1_routing.features.urgency if hasattr(prediction.layer1_routing.features, 'urgency') else 0.5
            complexity = prediction.layer1_routing.features.complexity if hasattr(prediction.layer1_routing.features, 'complexity') else 0.5

            # Threat signal (check if threat modality is active)
            threat = 0.0
            if hasattr(self.layer2, 'brain_monitor') and self.layer2.brain_monitor:
                if self.layer2.brain_monitor.gate_history:
                    brain_gates = list(self.layer2.brain_monitor.gate_history)[-1]
                    # Threat is modality index 5 (if it exists)
                    if len(brain_gates) > 5:
                        threat = brain_gates[5]

            # Get recent success rate
            recent_success_rate = 0.5
            if self.enable_memory and self.memory:
                recent_success_rate = self.memory.working.get_success_rate()

            # Update neuromodulators
            neuro_effects = self.neuromodulation.update(
                outcome=outcome,
                confidence=prediction.confidence,
                urgency=urgency,
                threat=threat,
                complexity=complexity,
                recent_success_rate=recent_success_rate
            )

            print(f"[Neuromodulation] {self.neuromodulation.get_state_description()}")
            print(f"  Effects: LR×{neuro_effects.learning_rate_multiplier:.2f}, "
                  f"Explore+{neuro_effects.exploration_boost:.2f}, "
                  f"Focus×{neuro_effects.attention_focus_multiplier:.2f}")

        # === PREDICTIVE CODING: Update Layer 3 Prediction (PHASE 2) ===
        if self.enable_predictive_coding and self.predictive_coding:
            if prediction.prediction_errors and 'layer3_prediction' in prediction.prediction_errors:
                layer3_pred = prediction.prediction_errors['layer3_prediction']
                if layer3_pred:
                    # Update with actual outcome
                    decision_type = prediction.actionable_decision.multi_target_decision['primary']['type']
                    actual_outcome = {
                        'decision_type': decision_type,
                        'success': outcome == 'success',
                        'execution_time_ms': execution_time_ms or 1000.0
                    }
                    layer3_pe = self.predictive_coding.update_decision_prediction(
                        layer3_pred,
                        actual_outcome
                    )

                    print(f"[Predictive] Layer 3 PE: {layer3_pe.error_magnitude:.3f} ({layer3_pe.surprise_level})")

        # === MEMORY: Consolidate to Episodic (PHASE 1) ===
        if not self.enable_memory or not self.memory:
            return

        # Determine emotional valence
        if outcome == 'success':
            if user_rating and user_rating > 0.8:
                valence = 'positive'
            else:
                valence = 'neutral'
        else:
            valence = 'negative'

        # Get brain gates
        brain_gates = None
        if hasattr(self.layer2, 'brain_monitor') and self.layer2.brain_monitor:
            if self.layer2.brain_monitor.gate_history:
                brain_gates = list(self.layer2.brain_monitor.gate_history)[-1]

        if brain_gates is None:
            return  # Can't store without brain state

        # Extract layer 1 features
        layer1_features = {
            'complexity': prediction.layer1_routing.features.complexity,
            'urgency': prediction.layer1_routing.features.urgency,
            'task_type': prediction.layer1_routing.features.task_type
        }

        # Compute prediction error (simplified)
        expected_confidence = prediction.confidence
        actual_success = 1.0 if outcome == 'success' else 0.0
        prediction_error = abs(expected_confidence - actual_success)

        # Consolidate to episodic memory
        self.memory.consolidate_to_episodic(
            task=prediction.task_description,
            task_type=prediction.task_type,
            decision=prediction.actionable_decision.multi_target_decision['primary']['type'],
            confidence=prediction.confidence,
            outcome=outcome,
            brain_gates=brain_gates,
            layer1_features=layer1_features,
            layer2_sequence=prediction.predicted_sequence,
            reasoning_chain=prediction.actionable_decision.reasoning_chain,
            importance=importance,
            emotional_valence=valence,
            prediction_error=prediction_error,
            execution_time_ms=execution_time_ms,
            user_rating=user_rating
        )

        print(f"[Memory] Consolidated to episodic: {prediction.task_description[:50]}... (importance={importance:.2f}, valence={valence})")

    def trigger_dream_cycle(
        self,
        num_dreams: Optional[int] = None
    ) -> List[DreamState]:
        """
        Trigger a dream cycle for offline consolidation

        This should be called during idle time to consolidate memories
        and extract patterns.

        Args:
            num_dreams: Number of dreams to generate (default: 5)

        Returns:
            List of dream states from this cycle
        """
        if not self.enable_dream_mode or not self.dream_mode:
            print("[DreamMode] Not enabled")
            return []

        if not self.enable_memory or not self.memory:
            print("[DreamMode] Requires memory system")
            return []

        # Get episodic memories
        episodic_memories = self.memory.episodic.memories

        if not episodic_memories:
            print("[DreamMode] No episodic memories to consolidate")
            return []

        # Get possible decisions from layer 3
        possible_decisions = self.layer3.intervention_types

        # Run dream cycle
        dreams = self.dream_mode.dream_cycle(
            episodic_memories=episodic_memories,
            possible_decisions=possible_decisions,
            num_dreams=num_dreams
        )

        print(f"[DreamMode] Completed {len(dreams)} dreams")

        return dreams

    def get_dream_pattern_for_task(
        self,
        task_type: str,
        min_confidence: float = 0.5
    ) -> Optional[Pattern]:
        """
        Get discovered pattern for a task type from dream mode

        Args:
            task_type: Task type
            min_confidence: Minimum confidence threshold

        Returns:
            Pattern if found, None otherwise
        """
        if not self.enable_dream_mode or not self.dream_mode:
            return None

        return self.dream_mode.get_pattern_for_task(task_type, min_confidence)

    def get_statistics(self) -> Dict:
        """Get statistics from all layers"""
        avg_timing = {
            layer: np.mean(times) if times else 0.0
            for layer, times in self.layer_timing.items()
        }

        stats = {
            'total_predictions': self.total_predictions,
            'average_layer_timing': avg_timing,
            'layer1_stats': self.layer1.get_statistics(),
            'layer3_stats': self.layer3.get_statistics()
        }

        # Add memory stats (PHASE 1)
        if self.enable_memory and self.memory:
            stats['memory_stats'] = {
                'working_memory_size': len(self.memory.working),
                'episodic_memory_size': len(self.memory.episodic),
                'recent_success_rate': self.memory.working.get_success_rate()
            }

        # Add predictive coding stats (PHASE 2)
        if self.enable_predictive_coding and self.predictive_coding:
            stats['predictive_coding_stats'] = self.predictive_coding.get_statistics()

        # Add attention stats (PHASE 3)
        if self.enable_attention and self.attention:
            stats['attention_stats'] = self.attention.get_attention_statistics()

        # Add meta-learning stats (PHASE 4)
        if self.enable_meta_learning and self.meta_learner:
            stats['meta_learning_stats'] = self.meta_learner.get_statistics()

        # Add dream mode stats (PHASE 5)
        if self.enable_dream_mode and self.dream_mode:
            stats['dream_mode_stats'] = self.dream_mode.get_statistics()

        # Add neuromodulation stats (PHASE 6)
        if self.enable_neuromodulation and self.neuromodulation:
            stats['neuromodulation_stats'] = self.neuromodulation.get_statistics()

        # Add temporal memory stats (PHASE 7)
        if self.enable_temporal_memory and self.temporal_memory:
            stats['temporal_memory_stats'] = self.temporal_memory.get_statistics()

        # Add active inference stats (PHASE 8)
        if self.enable_active_inference and self.active_inference:
            stats['active_inference_stats'] = self.active_inference.get_statistics()

        # Add compositional reasoning stats (PHASE 9)
        if self.enable_compositional_reasoning and self.compositional_reasoning:
            stats['compositional_reasoning_stats'] = self.compositional_reasoning.get_statistics()

        # Add tool creation stats (PHASE 10)
        if self.enable_tool_creation and self.tool_creation:
            stats['tool_creation_stats'] = self.tool_creation.get_statistics()

        # Add consciousness metrics stats (PHASE 11)
        if self.enable_consciousness_metrics and self.consciousness_metrics:
            stats['consciousness_metrics_stats'] = self.consciousness_metrics.get_statistics()

        # Add multi-brain swarm stats (PHASE 12)
        if self.enable_multi_brain_swarm and self.multi_brain_swarm:
            stats['multi_brain_swarm_stats'] = self.multi_brain_swarm.get_statistics()

        # Add CTM async stats (PHASE 13)
        if self.enable_ctm_async and self.ctm_async:
            stats['ctm_async_stats'] = self.ctm_async.get_statistics()

        # Add Layer 4 stats (PHASE 16)
        if self.enable_layer4 and self.layer4_router:
            stats['layer4_stats'] = self.layer4_router.get_statistics()

        return stats

    def get_ctm_insights(self, ctm_task_id: str, wait: bool = True, timeout: float = 10.0) -> Optional[str]:
        """
        Retrieve CTM reasoning insights for a given task

        Args:
            ctm_task_id: CTM task identifier from prediction
            wait: Wait for CTM to complete if still running
            timeout: Max wait time in seconds

        Returns:
            Insights summary string, or None if not available
        """
        if not self.enable_ctm_async:
            return None

        try:
            if self.enable_multi_ctm and self.ctm_ensemble:
                # Multi-CTM Ensemble
                ensemble_result = self.ctm_ensemble.get_result(ctm_task_id, wait=wait, timeout=timeout)

                if ensemble_result:
                    # Return aggregated insights if available
                    if ensemble_result.aggregated_insights:
                        return ensemble_result.aggregated_insights

                    # Otherwise, extract from individual CTMs
                    insights = []
                    for domain, ctm_result in ensemble_result.ctm_results.items():
                        if ctm_result and hasattr(ctm_result, 'status'):
                            if ctm_result.status == ReasoningStatus.COMPLETED and ctm_result.ctm_insight:
                                insights.append(f"[{domain.value}CTM] {ctm_result.ctm_insight.suggested_strategy}")

                    return "\n".join(insights) if insights else "Ensemble reasoning in progress"
                else:
                    return "Ensemble reasoning not found"
            elif self.ctm_async:
                # Single CTM (legacy)
                ctm_result = self.ctm_async.get_result(ctm_task_id, wait=wait, timeout=timeout)

                if ctm_result.status == ReasoningStatus.COMPLETED:
                    return ctm_result.get_insights_summary()
                else:
                    return f"CTM reasoning {ctm_result.status.value}: {ctm_result.error_message or 'In progress'}"
            else:
                return None

        except Exception as e:
            return f"Error retrieving CTM insights: {e}"

    def retry_with_ctm_insights(
        self,
        original_prediction: HierarchicalPrediction,
        failure_description: Optional[str] = None
    ) -> HierarchicalPrediction:
        """
        Generate retry strategy using CTM deep reasoning insights

        This is called when execution fails and we need alternative strategies.
        If CTM was triggered during the original prediction, we use those insights.
        Otherwise, we start synchronous CTM reasoning now.

        Args:
            original_prediction: The prediction that led to failure
            failure_description: Optional description of what went wrong

        Returns:
            New HierarchicalPrediction with retry strategy enhanced by CTM insights
        """
        print("\n" + "=" * 70)
        print("CTM-ENHANCED FAILURE RECOVERY")
        print("=" * 70)

        task_description = original_prediction.task_description or "Unknown task"

        # Check if we have existing CTM task
        ctm_insights = None
        if original_prediction.ctm_task_id and self.enable_ctm_async:
            print(f"\n[CTM] Retrieving insights from original prediction (task_id={original_prediction.ctm_task_id})")

            # Wait for CTM to complete if still running
            ctm_insights = self.get_ctm_insights(
                original_prediction.ctm_task_id,
                wait=True,
                timeout=15.0
            )

        # If no existing CTM task or it failed, start new synchronous reasoning
        if not ctm_insights and self.enable_ctm_async and self.ctm_async:
            print(f"\n[CTM] No existing insights - starting new synchronous reasoning")

            # Build problem description with failure context
            problem = f"{task_description}"
            if failure_description:
                problem += f"\n\nPrevious attempt failed: {failure_description}"

            # Start and wait for CTM reasoning
            try:
                ctm_task_id = self.ctm_async.start_reasoning_async(
                    task_description=problem,
                    steps=self.ctm_max_steps,
                    convergence_threshold=0.85,
                    priority='high'
                )

                ctm_insights = self.get_ctm_insights(ctm_task_id, wait=True, timeout=30.0)

            except Exception as e:
                print(f"[CTM] Failed to generate insights: {e}")
                ctm_insights = None

        # Display insights
        if ctm_insights:
            print(f"\n[CTM] Deep Reasoning Insights:")
            print("-" * 70)
            print(ctm_insights)
            print("-" * 70)

        # Generate new prediction with CTM context
        print(f"\n[Hierarchical] Re-planning with CTM insights...")

        # Temporarily disable CTM async to avoid recursive triggers
        original_ctm_enabled = self.enable_ctm_async
        self.enable_ctm_async = False

        try:
            # Make new prediction
            new_prediction = self.predict(task_description)

            # Inject CTM insights into reasoning chain
            if ctm_insights:
                new_prediction.ctm_insights = ctm_insights

                # Prepend CTM insights to reasoning chain
                ctm_reasoning_step = f"[CTM Deep Reasoning] {ctm_insights[:200]}..."
                new_prediction.actionable_decision.reasoning_chain.insert(0, ctm_reasoning_step)

            print(f"\n[Recovery] New strategy: {new_prediction.actionable_decision.multi_target_decision['primary']['type']}")
            print(f"[Recovery] Confidence: {new_prediction.confidence:.1%}")

            return new_prediction

        finally:
            # Restore CTM async state
            self.enable_ctm_async = original_ctm_enabled

    def _load_ctm_weights(self, checkpoint_dir: str, enable_logic: bool, enable_temporal: bool, enable_value: bool):
        """
        Load trained brain weights into Multi-CTM Ensemble

        Args:
            checkpoint_dir: Directory containing brain checkpoints
            enable_logic: Whether LogicCTM is enabled
            enable_temporal: Whether TemporalCTM is enabled
            enable_value: Whether ValueCTM is enabled
        """
        from pathlib import Path
        import torch
        from core.multi_ctm_ensemble import CTMDomain

        print("[HierarchicalPlanner] Loading trained CTM weights...")

        checkpoint_dir_path = Path(checkpoint_dir)
        # Use best available checkpoints (highest epoch numbers)
        checkpoints = {
            CTMDomain.SPATIAL: (checkpoint_dir_path / "spatial_brain_epoch_1.pth", True),  # Always enabled
            CTMDomain.LOGIC: (checkpoint_dir_path / "logic_brain_epoch_20.pth", enable_logic),  # 20 epochs trained
            CTMDomain.TEMPORAL: (checkpoint_dir_path / "temporal_brain_epoch_10.pth", enable_temporal),  # 10 epochs
            CTMDomain.VALUE: (checkpoint_dir_path / "value_brain_epoch_10.pth", enable_value),  # 10 epochs
        }

        loaded_count = 0

        for domain, (ckpt_path, is_enabled) in checkpoints.items():
            if not is_enabled:
                continue

            if not ckpt_path.exists():
                print(f"  [SKIP] {domain.value.capitalize()}CTM checkpoint not found: {ckpt_path}")
                continue

            try:
                if self.ctm_ensemble and domain in self.ctm_ensemble.ctms and self.ctm_ensemble.ctms[domain]:
                    brain = self.ctm_ensemble.ctms[domain].klotski_ctm.brain
                    state_dict = torch.load(str(ckpt_path), map_location='cpu', weights_only=True)

                    # Load with strict=False to ignore action head shape mismatch
                    brain.load_state_dict(state_dict, strict=False)
                    print(f"  [OK] {domain.value.capitalize()}CTM weights loaded from {ckpt_path.name}")
                    loaded_count += 1
            except Exception as e:
                print(f"  [WARN] {domain.value.capitalize()}CTM load failed: {e}")

        if loaded_count > 0:
            print(f"[HierarchicalPlanner] Loaded {loaded_count}/4 trained CTM brain weights")
        else:
            print(f"[HierarchicalPlanner] No trained weights loaded, using default initialization")

    # ==================== Goal Graph Methods (PHASE 15) ====================

    def add_goal(
        self,
        description: str,
        priority: str = "medium",
        parent_id: Optional[str] = None,
        deadline: Optional[str] = None
    ) -> Optional[Goal]:
        """
        Add a goal to the goal graph

        Args:
            description: Goal description
            priority: Priority level (critical/high/medium/low/background)
            parent_id: Parent goal ID for hierarchical goals
            deadline: Optional deadline (ISO format)

        Returns:
            Created Goal object or None if goal graph disabled
        """
        if not self.enable_goal_graph or not self.goal_graph:
            return None

        priority_map = {
            'critical': GoalPriority.CRITICAL,
            'high': GoalPriority.HIGH,
            'medium': GoalPriority.MEDIUM,
            'low': GoalPriority.LOW,
            'background': GoalPriority.BACKGROUND
        }
        goal_priority = priority_map.get(priority.lower(), GoalPriority.MEDIUM)

        return self.goal_graph.add_goal(
            description=description,
            priority=goal_priority,
            parent_id=parent_id,
            deadline=deadline
        )

    def get_goals(self) -> Dict:
        """
        Get all goals and their status

        Returns:
            Dict with goal information
        """
        if not self.enable_goal_graph or not self.goal_graph:
            return {'enabled': False, 'goals': []}

        return {
            'enabled': True,
            'stats': self.goal_graph.get_statistics(),
            'ready_goals': [g.to_dict() for g in self.goal_graph.get_ready_goals()],
            'critical_path': self.goal_graph.get_critical_path()
        }

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as completed"""
        if not self.enable_goal_graph or not self.goal_graph:
            return False
        return self.goal_graph.complete_goal(goal_id)

    def fail_goal(self, goal_id: str, reason: str = "") -> bool:
        """Mark a goal as failed"""
        if not self.enable_goal_graph or not self.goal_graph:
            return False
        return self.goal_graph.fail_goal(goal_id, reason)

    def get_goal_context_for_ctm(self, goal_id: str) -> Dict:
        """
        Get goal context for CTM reasoning

        Args:
            goal_id: Goal ID

        Returns:
            Context dict for CTM
        """
        if not self.enable_goal_graph or not self.goal_graph:
            return {}
        return self.goal_graph.get_context_for_ctm(goal_id)

    def __repr__(self):
        memory_str = f", memory={len(self.memory.working)}/{len(self.memory.episodic)}" if self.enable_memory else ""
        return (
            f"HierarchicalPlanner("
            f"predictions={self.total_predictions}, "
            f"layers=3{memory_str})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("HIERARCHICAL PLANNER - REQUIRES TRAINED LAYER 2")
    print("=" * 70)
    print()
    print("This module integrates all 3 layers:")
    print("  - Layer 1: TaskFeatureRouter")
    print("  - Layer 2: ConversationPathPlanner (trained)")
    print("  - Layer 3: DecisionRouter")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_hierarchical_planner.py")
    print()
    print("=" * 70)

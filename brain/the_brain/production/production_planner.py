"""
Production-Ready Hierarchical Planner with Learned Routing Matrix

Features:
1. Load pre-trained routing matrix
2. Continuous learning from user feedback
3. A/B testing support
4. Matrix versioning
5. Performance monitoring
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

from core.hierarchical_planner import HierarchicalPlanner, HierarchicalPrediction
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor
from core.multi_brain_swarm import MultiBrainSwarm, BrainAnswer
from core.semantic_coherence import SemanticEncoder
from core.config_loader import load_config
from core.subsystem_registry import SubsystemRegistry
from core.brain_monitoring import (
    BrainMetrics, PredictionAuditLog, CognitiveLoopTracer,
    ErrorRateTracker, ActivityHeatmap,
)


@dataclass
class FeedbackEntry:
    """User feedback for a prediction"""
    timestamp: str
    task: str
    predicted_action: str
    predicted_weight: float
    actual_action: Optional[str]
    success: bool
    user_rating: Optional[float]  # 0-1 scale
    brain_gates: List[float]
    execution_time_ms: Optional[float]


@dataclass
class MatrixVersion:
    """Versioned routing matrix"""
    version: str
    timestamp: str
    accuracy: float
    num_predictions: int
    avg_confidence: float
    notes: str


class ProductionPlanner:
    """
    Production-ready hierarchical planner with:
    - Pre-trained matrix loading
    - Continuous learning
    - Feedback collection
    - A/B testing
    - Performance monitoring
    """

    def __init__(
        self,
        session_log_dir: str,
        matrix_dir: str = "production/trained_matrices",
        feedback_dir: str = "production/feedback",
        matrix_version: Optional[str] = None,
        enable_continuous_learning: bool = True,
        learning_rate: float = 0.005,  # Lower for production stability
        enable_semantic_coherence: bool = True,
        embedding_type: str = "neural",  # "hash" or "neural"
        k_min: float = 0.55,
        green_threshold: float = 0.75,
        alpha: float = 0.5,
        user_id: Optional[str] = None,  # NEW: Enable Infinite Chat (Phase 12)
        openrouter_api_key: Optional[str] = None,  # NEW: Enable LLM-powered brain
        enable_cognitive_loop: bool = False,  # NEW: Enable unified cognitive loop
        config_path: Optional[str] = None,  # NEW: YAML config file path
        seed: int = 42
    ):
        """
        Initialize production planner

        Args:
            session_log_dir: Directory with training session logs
            matrix_dir: Directory to save/load trained matrices
            feedback_dir: Directory to save user feedback
            matrix_version: Specific matrix version to load (None = latest)
            enable_continuous_learning: Whether to update matrix from feedback
            learning_rate: Learning rate for continuous updates
            enable_semantic_coherence: Whether to use semantic coherence validation (Phase 13)
            embedding_type: Type of embeddings ("hash" or "neural")
            k_min: Minimum coherence threshold for YELLOW status
            green_threshold: Minimum truth stability for GREEN status
            alpha: Weight for voting score vs coherence (truth_stability = alpha*vote + (1-alpha)*K)
            user_id: User ID for memory isolation (enables Infinite Chat - Phase 12)
            openrouter_api_key: OpenRouter API key for LLM-powered brain (enables MultiLLMRouter)
            enable_cognitive_loop: Whether to use the unified cognitive loop instead of sequential pipeline
            seed: Random seed
        """
        # Load YAML configuration if available (values override defaults, but explicit args take priority)
        self._yaml_config = {}
        if config_path:
            try:
                self._yaml_config = load_config(config_path)
                print(f"[Config] Loaded configuration from {config_path}")
            except Exception as e:
                print(f"[Config] Could not load {config_path}: {e}")
        else:
            # Try default config location
            default_config = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'configs', 'default.yaml')
            if os.path.exists(default_config):
                try:
                    self._yaml_config = load_config(default_config)
                    logger.info(f"Loaded default configuration from {default_config}")
                except Exception as e:
                    logger.warning(f"Could not load default config {default_config}: {e}")

        # Apply YAML production overrides (explicit constructor args take priority)
        prod_cfg = self._yaml_config.get('production', {})

        self.matrix_dir = Path(matrix_dir)
        self.feedback_dir = Path(feedback_dir)
        self.matrix_dir.mkdir(parents=True, exist_ok=True)
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

        self.enable_continuous_learning = enable_continuous_learning
        self.learning_rate = learning_rate
        self.enable_semantic_coherence = enable_semantic_coherence

        # Initialize base planner
        print("Initializing production planner...")

        # Initialize MetaRouter
        meta_router = MetaRouter(
            enable_hippocampus=True,
            enable_per_modality_pes=True,
            seed=seed
        )

        # Add LLM support if API key provided
        if openrouter_api_key:
            print(f"[LLM] Initializing MultiLLMRouter with OpenRouter API key")
            from core.multi_llm_router import MultiLLMRouter
            meta_router.multi_llm_router = MultiLLMRouter(
                openrouter_api_key=openrouter_api_key,
                user_id=user_id,
                enable_infinite_chat=bool(user_id)  # Enable if user_id provided
            )
            print("[LLM] MetaRouter enhanced with MultiLLMRouter support")
        else:
            print("[LLM] No API key provided, using template-based routing")
            meta_router.multi_llm_router = None

        layer2 = ConversationPathPlanner(
            meta_router=meta_router,
            strategy_library=StrategyLibrary(max_strategies_per_type=20),
            brain_monitor=BrainActivityMonitor(history_length=100),
            enable_adaptive_gating=True
        )

        # Train from sessions
        print(f"Training from sessions: {session_log_dir}")
        layer2.train_from_sessions(session_log_dir, limit=39)

        self.planner = HierarchicalPlanner(
            conversation_planner=layer2,
            intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],  # 5 interventions!
            user_id=user_id,  # NEW: Enable Infinite Chat (Phase 12)
            memory_save_dir="data/episodic_memory",  # Persist memory to disk (survive restarts)
            enable_layer4=self._yaml_config.get('layer4', {}).get('enabled', True),  # Enable Layer 4
            seed=seed
        )

        # Load trained matrix
        self.current_version = self._load_matrix(matrix_version)
        print(f"Loaded matrix version: {self.current_version}")

        # Set learning rate
        self.planner.layer3.multi_target_router.learning_rate = self.learning_rate
        print(f"Learning rate: {self.learning_rate}")

        # Initialize semantic coherence (Phase 13)
        if self.enable_semantic_coherence:
            print(f"Initializing semantic coherence (embedding_type={embedding_type})...")
            self.swarm = MultiBrainSwarm(
                num_brains=5,
                enable_semantic_coherence=True,
                k_min=k_min,
                green_threshold=green_threshold,
                alpha=alpha
            )

            # Configure embedding type (austauschbar!)
            if embedding_type == "neural":
                self.swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)
                print("[+] Neural embeddings enabled (sentence-transformers)")
            elif embedding_type == "hash":
                self.swarm.semantic_layer.encoder = SemanticEncoder(use_simple=True)
                print("[+] Hash-based TF-IDF embeddings enabled")
            else:
                raise ValueError(f"Unknown embedding_type: {embedding_type}. Use 'hash' or 'neural'")

            print(f"[+] Semantic coherence thresholds: k_min={k_min}, green={green_threshold}, alpha={alpha}")
        else:
            self.swarm = None
            print("Semantic coherence disabled")

        # Cognitive Loop (opt-in unified brain loop)
        self.cognitive_loop = None
        if enable_cognitive_loop:
            try:
                from core.cognitive_loop import CognitiveLoop, CognitiveLoopConfig
                # Load config from YAML if available
                if self._yaml_config and 'cognitive_loop' in self._yaml_config:
                    loop_config = CognitiveLoopConfig.from_yaml(self._yaml_config)
                    print("[CognitiveLoop] Configuration loaded from YAML")
                else:
                    loop_config = CognitiveLoopConfig()
                self.cognitive_loop = CognitiveLoop(
                    planner=self.planner,
                    config=loop_config
                )
                print("[CognitiveLoop] Unified cognitive loop ENABLED")
            except Exception as e:
                print(f"[CognitiveLoop] Failed to initialize: {e}")
                self.cognitive_loop = None

        # Agent Loop (V2 Phase 3: P3.31-33 - autonomous agent loop)
        self.agent_loop = None
        enable_agent_loop = os.environ.get('ENABLE_AGENT_LOOP', 'false').lower() == 'true'
        if enable_agent_loop:
            try:
                from core.agent_loop import AgentLoop, AgentLoopConfig
                if self._yaml_config and 'agent_loop' in self._yaml_config:
                    loop_config = AgentLoopConfig.from_yaml(self._yaml_config)
                    print("[AgentLoop] Configuration loaded from YAML")
                else:
                    loop_config = AgentLoopConfig()
                self.agent_loop = AgentLoop(config=loop_config)
                # Wire integrations
                self.agent_loop.planner = self
                self.agent_loop.cognitive_loop = self.cognitive_loop
                self.agent_loop.memory = getattr(self.planner, 'memory', None)
                self.agent_loop.homeostatic = getattr(self.planner, 'homeostatic', None)
                self.agent_loop.goal_generator = getattr(self.planner, 'goal_generator', None)
                self.agent_loop.neuromodulation = getattr(self.planner, 'neuromodulation', None)
                # Wire motivation system (P3.34-36)
                try:
                    from core.motivation_drives import MotivationSystem
                    if self._yaml_config and 'motivation' in self._yaml_config:
                        self.agent_loop.motivation = MotivationSystem.from_yaml(self._yaml_config)
                        print("[AgentLoop] MotivationSystem loaded from YAML config")
                    else:
                        self.agent_loop.motivation = MotivationSystem()
                    print("[AgentLoop] MotivationSystem wired (CuriosityDrive + CompetenceDrive + HomeostaticDrives)")
                except Exception as e:
                    print(f"[AgentLoop] MotivationSystem not available: {e}")
                # Wire goal management system (P3.37-40)
                try:
                    from core.goal_management import GoalManager
                    if self._yaml_config and 'goal_management' in self._yaml_config:
                        self.agent_loop.goal_manager = GoalManager.from_yaml(self._yaml_config)
                        print("[AgentLoop] GoalManager loaded from YAML config")
                    else:
                        self.agent_loop.goal_manager = GoalManager()
                    print("[AgentLoop] GoalManager wired (Hierarchy + Generation + Prioritization + Conflict)")
                except Exception as e:
                    print(f"[AgentLoop] GoalManager not available: {e}")

                # Wire proactive behavior system (P3.41-43)
                try:
                    from core.proactive_behavior import ProactiveBehavior
                    if self._yaml_config and 'proactive_behavior' in self._yaml_config:
                        self.agent_loop.proactive = ProactiveBehavior.from_yaml(self._yaml_config)
                        print("[AgentLoop] ProactiveBehavior loaded from YAML config")
                    else:
                        self.agent_loop.proactive = ProactiveBehavior()
                    print("[AgentLoop] ProactiveBehavior wired (Generator + Scheduler + Reactive Patterns)")
                except Exception as e:
                    print(f"[AgentLoop] ProactiveBehavior not available: {e}")

                # Wire safety regulation system (P3.44-45)
                try:
                    from core.safety_regulation import SafetyRegulation
                    if self._yaml_config and 'safety_regulation' in self._yaml_config:
                        self.agent_loop.safety = SafetyRegulation.from_yaml(self._yaml_config)
                        print("[AgentLoop] SafetyRegulation loaded from YAML config")
                    else:
                        self.agent_loop.safety = SafetyRegulation()
                    print("[AgentLoop] SafetyRegulation wired (AutonomyBudget + SafetyGovernor)")
                except Exception as e:
                    print(f"[AgentLoop] SafetyRegulation not available: {e}")

                # ── Phase 4: Language & Communication (P4.46-60) ──

                # Wire language center (P4.46-48)
                try:
                    from core.language_center import BrainLanguageCenter
                    if self._yaml_config and 'language_center' in self._yaml_config:
                        self.agent_loop.language_center = BrainLanguageCenter.from_yaml(self._yaml_config)
                        print("[AgentLoop] BrainLanguageCenter loaded from YAML config")
                    else:
                        self.agent_loop.language_center = BrainLanguageCenter()
                    print("[AgentLoop] BrainLanguageCenter wired (ContextWindow + ResponseGen)")
                except Exception as e:
                    print(f"[AgentLoop] BrainLanguageCenter not available: {e}")

                # Wire personality system (P4.52-54)
                try:
                    from core.personality import PersonalityModel, EmotionalExpression, CommunicationStyle
                    if self._yaml_config and 'personality' in self._yaml_config:
                        self.agent_loop.personality = PersonalityModel.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.personality = PersonalityModel()
                    self.agent_loop.emotional_expression = EmotionalExpression()
                    if self._yaml_config and 'communication_style' in self._yaml_config:
                        self.agent_loop.communication_style = CommunicationStyle.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.communication_style = CommunicationStyle()
                    # Inject personality instructions into language center
                    if self.agent_loop.language_center and self.agent_loop.personality:
                        self.agent_loop.language_center.personality_instructions = (
                            self.agent_loop.personality.get_style_instructions()
                        )
                    print("[AgentLoop] Personality wired (Big5 + Emotion + Style)")
                except Exception as e:
                    print(f"[AgentLoop] Personality not available: {e}")

                # Wire proactive communication (P4.55-57)
                try:
                    from core.proactive_communication import StatusUpdater, ExplanationSystem, SuggestionEngine
                    if self._yaml_config and 'status_updater' in self._yaml_config:
                        self.agent_loop.status_updater = StatusUpdater.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.status_updater = StatusUpdater()
                    self.agent_loop.explanation_system = ExplanationSystem()
                    if self._yaml_config and 'suggestion_engine' in self._yaml_config:
                        self.agent_loop.suggestion_engine = SuggestionEngine.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.suggestion_engine = SuggestionEngine()
                    print("[AgentLoop] ProactiveCommunication wired (Status + Explanation + Suggestion)")
                except Exception as e:
                    print(f"[AgentLoop] ProactiveCommunication not available: {e}")

                # Wire dialogue manager (P4.58-60)
                try:
                    from core.dialogue_manager import DialogueManager
                    if self._yaml_config and 'dialogue_manager' in self._yaml_config:
                        self.agent_loop.dialogue_manager = DialogueManager.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.dialogue_manager = DialogueManager()
                    print("[AgentLoop] DialogueManager wired (Clarification + Memory)")
                except Exception as e:
                    print(f"[AgentLoop] DialogueManager not available: {e}")

                # ── Phase 1: Sensor Systems (P1.3-6, P1.9-15) ──

                try:
                    from core.sensor_systems import (
                        SystemVitalsSensor, FileSystemSensor, ProcessSensor,
                        LogSensor, GitActivitySensor, SensorRegistry,
                        SensorFusion, PerceptionPipeline, AttentionDrivenSampling,
                        NoveltyFilter, SensoryMemory
                    )
                    if self._yaml_config and 'system_vitals_sensor' in self._yaml_config:
                        self.agent_loop.system_vitals_sensor = SystemVitalsSensor.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.system_vitals_sensor = SystemVitalsSensor()
                    if self._yaml_config and 'file_system_sensor' in self._yaml_config:
                        self.agent_loop.file_system_sensor = FileSystemSensor.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.file_system_sensor = FileSystemSensor()
                    if self._yaml_config and 'process_sensor' in self._yaml_config:
                        self.agent_loop.process_sensor = ProcessSensor.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.process_sensor = ProcessSensor()
                    if self._yaml_config and 'log_sensor' in self._yaml_config:
                        self.agent_loop.log_sensor = LogSensor.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.log_sensor = LogSensor()
                    if self._yaml_config and 'git_activity_sensor' in self._yaml_config:
                        self.agent_loop.git_activity_sensor = GitActivitySensor.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.git_activity_sensor = GitActivitySensor()
                    if self._yaml_config and 'sensor_registry' in self._yaml_config:
                        self.agent_loop.sensor_registry = SensorRegistry.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.sensor_registry = SensorRegistry()
                    self.agent_loop.sensor_fusion = SensorFusion.from_yaml(self._yaml_config) if self._yaml_config and 'sensor_fusion' in self._yaml_config else SensorFusion()
                    self.agent_loop.perception_pipeline = PerceptionPipeline.from_yaml(self._yaml_config) if self._yaml_config and 'perception_pipeline' in self._yaml_config else PerceptionPipeline()
                    self.agent_loop.attention_sampling = AttentionDrivenSampling.from_yaml(self._yaml_config) if self._yaml_config and 'attention_sampling' in self._yaml_config else AttentionDrivenSampling()
                    self.agent_loop.novelty_filter = NoveltyFilter.from_yaml(self._yaml_config) if self._yaml_config and 'novelty_filter' in self._yaml_config else NoveltyFilter()
                    self.agent_loop.sensory_memory = SensoryMemory.from_yaml(self._yaml_config) if self._yaml_config and 'sensory_memory' in self._yaml_config else SensoryMemory()
                    print("[AgentLoop] SensorSystems wired (Vitals + FileSystem + Process + Log + Git + Registry + Fusion + Pipeline + Attention + Novelty + Memory)")
                except Exception as e:
                    print(f"[AgentLoop] SensorSystems not available: {e}")

                # ── Phase 2: Action Systems (P2.18, P2.25-30) ──

                try:
                    from core.action_systems import (
                        ApprovalGate, ActionPlanner, ActionValidator,
                        ActionMonitor, ActionOutcomeDetector, ActionReplayMemory,
                        ActionLearning
                    )
                    if self._yaml_config and 'approval_gate' in self._yaml_config:
                        self.agent_loop.approval_gate = ApprovalGate.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.approval_gate = ApprovalGate()
                    if self._yaml_config and 'action_planner' in self._yaml_config:
                        self.agent_loop.action_planner = ActionPlanner.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.action_planner = ActionPlanner()
                    self.agent_loop.action_validator = ActionValidator.from_yaml(self._yaml_config) if self._yaml_config and 'action_validator' in self._yaml_config else ActionValidator()
                    self.agent_loop.action_monitor = ActionMonitor.from_yaml(self._yaml_config) if self._yaml_config and 'action_monitor' in self._yaml_config else ActionMonitor()
                    self.agent_loop.action_outcome_detector = ActionOutcomeDetector.from_yaml(self._yaml_config) if self._yaml_config and 'action_outcome_detector' in self._yaml_config else ActionOutcomeDetector()
                    self.agent_loop.action_replay_memory = ActionReplayMemory.from_yaml(self._yaml_config) if self._yaml_config and 'action_replay_memory' in self._yaml_config else ActionReplayMemory()
                    self.agent_loop.action_learning = ActionLearning.from_yaml(self._yaml_config) if self._yaml_config and 'action_learning' in self._yaml_config else ActionLearning()
                    print("[AgentLoop] ActionSystems wired (ApprovalGate + Planner + Validator + Monitor + OutcomeDetector + ReplayMemory + Learning)")
                except Exception as e:
                    print(f"[AgentLoop] ActionSystems not available: {e}")

                # ── Phase 5: Learning Systems (P5.61-75) ──

                # Wire experience learning (P5.61-63)
                try:
                    from core.experience_learning import ExperienceReplaySystem, AutomaticOutcomeLearning, TransferLearning
                    if self._yaml_config and 'experience_replay' in self._yaml_config:
                        self.agent_loop.experience_replay = ExperienceReplaySystem.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.experience_replay = ExperienceReplaySystem()
                    self.agent_loop.outcome_learning = AutomaticOutcomeLearning()
                    if self._yaml_config and 'transfer_learning' in self._yaml_config:
                        self.agent_loop.transfer_learning = TransferLearning.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.transfer_learning = TransferLearning(self.agent_loop.experience_replay)
                    print("[AgentLoop] ExperienceLearning wired (Replay + Outcome + Transfer)")
                except Exception as e:
                    print(f"[AgentLoop] ExperienceLearning not available: {e}")

                # Wire skill library (P5.64-66)
                try:
                    from core.skill_library import SkillLibrary, SkillComposition, SkillRefinement
                    if self._yaml_config and 'skill_library' in self._yaml_config:
                        self.agent_loop.skill_library = SkillLibrary.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.skill_library = SkillLibrary()
                    self.agent_loop.skill_composition = SkillComposition()
                    self.agent_loop.skill_refinement = SkillRefinement(self.agent_loop.skill_library)
                    print("[AgentLoop] SkillLibrary wired (Library + Composition + Refinement)")
                except Exception as e:
                    print(f"[AgentLoop] SkillLibrary not available: {e}")

                # Wire world model (P5.67-69)
                try:
                    from core.world_model import WorldModel, CausalWorldModel, PredictiveWorldModel
                    if self._yaml_config and 'world_model' in self._yaml_config:
                        self.agent_loop.world_model = WorldModel.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.world_model = WorldModel()
                    if self._yaml_config and 'causal_world_model' in self._yaml_config:
                        self.agent_loop.causal_world_model = CausalWorldModel.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.causal_world_model = CausalWorldModel()
                    if self._yaml_config and 'predictive_world_model' in self._yaml_config:
                        self.agent_loop.predictive_world_model = PredictiveWorldModel.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.predictive_world_model = PredictiveWorldModel()
                    print("[AgentLoop] WorldModel wired (World + Causal + Predictive)")
                except Exception as e:
                    print(f"[AgentLoop] WorldModel not available: {e}")

                # Wire meta-cognition (P5.70-72)
                try:
                    from core.meta_cognition import SelfAwarenessModule, LearningDiagnosis, KnowledgeGapDetection
                    self.agent_loop.self_awareness = SelfAwarenessModule()
                    self.agent_loop.learning_diagnosis = LearningDiagnosis()
                    if self._yaml_config and 'knowledge_gaps' in self._yaml_config:
                        self.agent_loop.knowledge_gaps = KnowledgeGapDetection.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.knowledge_gaps = KnowledgeGapDetection()
                    print("[AgentLoop] MetaCognition wired (SelfAwareness + Diagnosis + Gaps)")
                except Exception as e:
                    print(f"[AgentLoop] MetaCognition not available: {e}")

                # Wire social learning (P5.73-75)
                try:
                    from core.social_learning import LearningFromDemonstration, FeedbackInterpretation, CollaborativeLearning
                    self.agent_loop.demonstration_learning = LearningFromDemonstration()
                    self.agent_loop.feedback_interpretation = FeedbackInterpretation()
                    if self._yaml_config and 'collaborative_learning' in self._yaml_config:
                        self.agent_loop.collaborative_learning = CollaborativeLearning.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.collaborative_learning = CollaborativeLearning()
                    print("[AgentLoop] SocialLearning wired (Demonstration + Feedback + Collaborative)")
                except Exception as e:
                    print(f"[AgentLoop] SocialLearning not available: {e}")

                # ── Phase 6: Identity Systems (P6.76-85) ──

                # Wire self-model + autobiographic memory + value system (P6.76-78)
                try:
                    from core.self_model import SelfModel, AutobiographicMemory, ValueSystem
                    if self._yaml_config and 'self_model' in self._yaml_config:
                        self.agent_loop.self_model = SelfModel.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.self_model = SelfModel()
                    self.agent_loop.autobiographic_memory = AutobiographicMemory()
                    if self._yaml_config and 'value_system' in self._yaml_config:
                        self.agent_loop.value_system = ValueSystem.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.value_system = ValueSystem()
                    print("[AgentLoop] SelfModel wired (SelfModel + Autobiographic + ValueSystem)")
                except Exception as e:
                    print(f"[AgentLoop] SelfModel not available: {e}")

                # Wire emotional memory + mood + stress (P6.79-81)
                try:
                    from core.emotional_memory import EmotionalMemorySystem, MoodSystem, StressResponse
                    if self._yaml_config and 'emotional_memory_system' in self._yaml_config:
                        self.agent_loop.emotional_memory = EmotionalMemorySystem.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.emotional_memory = EmotionalMemorySystem()
                    if self._yaml_config and 'mood_system' in self._yaml_config:
                        self.agent_loop.mood_system = MoodSystem.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.mood_system = MoodSystem()
                    if self._yaml_config and 'stress_response' in self._yaml_config:
                        self.agent_loop.stress_response = StressResponse.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.stress_response = StressResponse()
                    print("[AgentLoop] EmotionalMemory wired (EmotionalMemory + Mood + Stress)")
                except Exception as e:
                    print(f"[AgentLoop] EmotionalMemory not available: {e}")

                # Wire user relationship (P6.82-85)
                try:
                    from core.user_relationship import UserModel, TrustModel, CollaborationPatterns, RelationshipHistory
                    if self._yaml_config and 'user_model' in self._yaml_config:
                        self.agent_loop.user_model = UserModel.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.user_model = UserModel()
                    self.agent_loop.trust_model = TrustModel()
                    self.agent_loop.collaboration_patterns = CollaborationPatterns()
                    self.agent_loop.relationship_history = RelationshipHistory()
                    print("[AgentLoop] UserRelationship wired (UserModel + Trust + Collaboration + History)")
                except Exception as e:
                    print(f"[AgentLoop] UserRelationship not available: {e}")

                # ── Phase 6B: Deep Identity Systems ──

                # Wire CoreAffectSpace (valence x arousal primitive)
                try:
                    from core.emotional_memory import CoreAffectSpace
                    self.agent_loop.core_affect_space = CoreAffectSpace()
                    print("[AgentLoop] CoreAffectSpace wired (Valence x Arousal)")
                except Exception as e:
                    print(f"[AgentLoop] CoreAffectSpace not available: {e}")

                # Wire AgencyModel + IdentityNarrative + MoralConscience
                try:
                    from core.self_model import AgencyModel, IdentityNarrative, MoralConscience
                    self.agent_loop.agency_model = AgencyModel()
                    self.agent_loop.identity_narrative = IdentityNarrative()
                    self.agent_loop.moral_conscience = MoralConscience()
                    print("[AgentLoop] Identity wired (Agency + Narrative + Conscience)")
                except Exception as e:
                    print(f"[AgentLoop] Identity modules not available: {e}")

                # Wire ExistentialPurpose
                try:
                    from core.motivation_drives import ExistentialPurpose
                    self.agent_loop.existential_purpose = ExistentialPurpose()
                    print("[AgentLoop] ExistentialPurpose wired (Meaning + Purpose)")
                except Exception as e:
                    print(f"[AgentLoop] ExistentialPurpose not available: {e}")

                # Wire SocialIdentity
                try:
                    from core.user_relationship import SocialIdentity
                    self.agent_loop.social_identity = SocialIdentity()
                    print("[AgentLoop] SocialIdentity wired (Attachment + Belonging)")
                except Exception as e:
                    print(f"[AgentLoop] SocialIdentity not available: {e}")

                # Wire WisdomModule
                try:
                    from core.meta_cognition import WisdomModule
                    self.agent_loop.wisdom_module = WisdomModule()
                    print("[AgentLoop] WisdomModule wired (Wisdom Integration)")
                except Exception as e:
                    print(f"[AgentLoop] WisdomModule not available: {e}")

                # Wire ConsciousnessGateway
                try:
                    from core.claustrum import ConsciousnessGateway
                    self.agent_loop.consciousness_gateway = ConsciousnessGateway()
                    print("[AgentLoop] ConsciousnessGateway wired (GW + Phi)")
                except Exception as e:
                    print(f"[AgentLoop] ConsciousnessGateway not available: {e}")

                # ── Phase 7: Resilience Systems (P7.86-92) ──

                try:
                    from core.resilience import (
                        GracefulDegradationV2, SelfHealing, AdversarialResilience,
                        UncertaintyHandling, ContextSwitching, LongRunningTaskManager,
                        ResourceAwareness
                    )
                    if self._yaml_config and 'graceful_degradation' in self._yaml_config:
                        self.agent_loop.graceful_degradation = GracefulDegradationV2.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.graceful_degradation = GracefulDegradationV2()
                    self.agent_loop.self_healing = SelfHealing()
                    self.agent_loop.adversarial_resilience = AdversarialResilience()
                    self.agent_loop.uncertainty_handling = UncertaintyHandling()
                    self.agent_loop.context_switching = ContextSwitching()
                    self.agent_loop.long_running_tasks = LongRunningTaskManager()
                    if self._yaml_config and 'resource_awareness' in self._yaml_config:
                        self.agent_loop.resource_awareness = ResourceAwareness.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.resource_awareness = ResourceAwareness()
                    print("[AgentLoop] Resilience wired (Degradation + SelfHealing + Adversarial + Uncertainty + ContextSwitch + LongRunning + ResourceAwareness)")
                except Exception as e:
                    print(f"[AgentLoop] Resilience not available: {e}")

                # ── Phase 8: Ecosystem Intelligence (P8.96-100) ──

                try:
                    from core.ecosystem_intelligence import (
                        OrchestratorOfOrchestrators, SystemSynergyLearning,
                        KnowledgeExport, EvolutionaryGrowth, ConsciousnessEvolution
                    )
                    if self._yaml_config and 'ecosystem_intelligence' in self._yaml_config:
                        self.agent_loop.orchestrator_of_orchestrators = OrchestratorOfOrchestrators.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.orchestrator_of_orchestrators = OrchestratorOfOrchestrators()
                    self.agent_loop.synergy_learning = SystemSynergyLearning()
                    self.agent_loop.knowledge_export = KnowledgeExport()
                    self.agent_loop.evolutionary_growth = EvolutionaryGrowth()
                    self.agent_loop.consciousness_evolution = ConsciousnessEvolution()
                    print("[AgentLoop] EcosystemIntelligence wired (Orchestrator + Synergy + Export + Evolution + Consciousness)")
                except Exception as e:
                    print(f"[AgentLoop] EcosystemIntelligence not available: {e}")

                # ── Moltbook System ──

                # Wire Moltbook Core (Store + SemanticIndex + Graph)
                try:
                    from core.moltbook import MoltbookStore, SemanticIndex, MoltbookGraph
                    if self._yaml_config and 'moltbook' in self._yaml_config:
                        mb_config = self._yaml_config['moltbook']
                        self.agent_loop.moltbook_store = MoltbookStore(config=mb_config)
                        self.agent_loop.semantic_index = self.agent_loop.moltbook_store.semantic_index
                    else:
                        self.agent_loop.moltbook_store = MoltbookStore()
                        self.agent_loop.semantic_index = self.agent_loop.moltbook_store.semantic_index
                    self.agent_loop.moltbook_graph = MoltbookGraph()
                    print("[AgentLoop] Moltbook Core wired (Store + SemanticIndex + Graph)")
                except Exception as e:
                    print(f"[AgentLoop] Moltbook Core not available: {e}")

                # Wire Moltbook Thinking (ThoughtStream + Buffer + Associative + Meta)
                try:
                    from core.moltbook_thinking import (
                        ThoughtStream, ThoughtBuffer,
                        AssociativeThinking, MetaThinking
                    )
                    self.agent_loop.thought_buffer = ThoughtBuffer()
                    self.agent_loop.associative_thinking = AssociativeThinking(
                        moltbook=self.agent_loop.moltbook_store,
                        entorhinal=self.agent_loop.entorhinal_cortex,
                        locus_coeruleus=self.agent_loop.locus_coeruleus
                    )
                    self.agent_loop.thought_stream = ThoughtStream(
                        moltbook=self.agent_loop.moltbook_store,
                        dmn=self.agent_loop.default_mode_network,
                        core_affect=self.agent_loop.core_affect_space,
                        buffer=self.agent_loop.thought_buffer
                    )
                    self.agent_loop.meta_thinking = MetaThinking(
                        acc=self.agent_loop.anterior_cingulate,
                        wisdom=self.agent_loop.wisdom_module
                    )
                    print("[AgentLoop] Moltbook Thinking wired (ThoughtStream + Buffer + Associative + Meta)")
                except Exception as e:
                    print(f"[AgentLoop] Moltbook Thinking not available: {e}")

                # Wire Moltbook Retrieval (Markov + Speculative + Context + Relevance)
                try:
                    from core.moltbook_retrieval import (
                        MarkovKnowledgeChain, SpeculativeRetrieval,
                        ContextPredictor, RelevanceScorer
                    )
                    self.agent_loop.markov_knowledge_chain = MarkovKnowledgeChain(
                        moltbook=self.agent_loop.moltbook_store
                    )
                    self.agent_loop.speculative_retrieval = SpeculativeRetrieval(
                        markov=self.agent_loop.markov_knowledge_chain,
                        moltbook=self.agent_loop.moltbook_store,
                        semantic_index=self.agent_loop.semantic_index
                    )
                    self.agent_loop.context_predictor = ContextPredictor(
                        cerebellum=self.agent_loop.cerebellum
                    )
                    self.agent_loop.relevance_scorer = RelevanceScorer(
                        prefrontal=self.agent_loop.prefrontal_cortex
                    )
                    print("[AgentLoop] Moltbook Retrieval wired (Markov + Speculative + Context + Relevance)")
                except Exception as e:
                    print(f"[AgentLoop] Moltbook Retrieval not available: {e}")

                # Wire Moltbook Thinker-Talker (InternalMonologue + Controller + Talker)
                try:
                    from core.moltbook_thinker import (
                        InternalMonologue, CognitiveController
                    )
                    from core.moltbook_talker import TalkerModule
                    self.agent_loop.internal_monologue = InternalMonologue(
                        goal_manager=self.agent_loop.goal_manager,
                        existential_purpose=self.agent_loop.existential_purpose,
                        moltbook=self.agent_loop.moltbook_store,
                        prefrontal=self.agent_loop.prefrontal_cortex,
                        identity_narrative=self.agent_loop.identity_narrative,
                        emotional_memory=self.agent_loop.emotional_memory,
                        nucleus_accumbens=self.agent_loop.nucleus_accumbens,
                        self_awareness=self.agent_loop.self_awareness,
                        value_system=getattr(self.agent_loop, 'value_system', None),
                        safety_governor=getattr(self.agent_loop, 'safety_governor', None)
                    )
                    self.agent_loop.cognitive_controller = CognitiveController()
                    self.agent_loop.talker_module = TalkerModule(
                        personality=self.agent_loop.personality,
                        core_affect=self.agent_loop.core_affect_space,
                        language_center=self.agent_loop.language_center
                    )
                    print("[AgentLoop] Moltbook Thinker-Talker wired (Monologue + Controller + Talker)")
                except Exception as e:
                    print(f"[AgentLoop] Moltbook Thinker-Talker not available: {e}")

                # Wire Moltbook Pipeline (ThinkTalkOrchestrator + InputAnalyzer + Budget + Monitor)
                try:
                    from core.moltbook_pipeline import (
                        ThinkTalkOrchestrator, RealtimeResponseEngine,
                        InputAnalyzer, ThinkingBudget, DebugStream, PerformanceMonitor
                    )
                    analyzer = InputAnalyzer()
                    budget = ThinkingBudget(
                        acc=self.agent_loop.anterior_cingulate,
                    )
                    engine = RealtimeResponseEngine(
                        moltbook=self.agent_loop.moltbook_store,
                        thought_stream=getattr(self.agent_loop, 'thought_stream', None),
                        internal_monologue=getattr(self.agent_loop, 'internal_monologue', None),
                        talker=getattr(self.agent_loop, 'talker_module', None),
                        speculative=getattr(self.agent_loop, 'speculative_retrieval', None),
                        relevance_scorer=getattr(self.agent_loop, 'relevance_scorer', None),
                        meta_thinking=getattr(self.agent_loop, 'meta_thinking', None),
                    )
                    self.agent_loop.think_talk_orchestrator = ThinkTalkOrchestrator(
                        engine=engine,
                        analyzer=analyzer,
                        budget_allocator=budget,
                        safety=getattr(self.agent_loop, 'safety_governor', None),
                    )
                    self.agent_loop.input_analyzer = analyzer
                    self.agent_loop.thinking_budget = budget
                    self.agent_loop.realtime_engine = engine
                    self.agent_loop.performance_monitor = self.agent_loop.think_talk_orchestrator.performance_monitor
                    self.agent_loop.debug_stream = self.agent_loop.think_talk_orchestrator.debug_stream
                    print("[AgentLoop] Moltbook Pipeline wired (Orchestrator + Analyzer + Budget + Engine)")
                except Exception as e:
                    print(f"[AgentLoop] Moltbook Pipeline not available: {e}")

                # Wire Moltbook Agents (Feeder + Evaluation + Curation + Research + Feedback)
                try:
                    from core.moltbook_agents import (
                        MoltbookFeeder, EvaluationAgent, CurationAgent,
                        ResearchAgent, FeedbackAgent
                    )
                    self.agent_loop.moltbook_feeder = MoltbookFeeder(
                        moltbook=self.agent_loop.moltbook_store,
                        agent_name="brain",
                        graph=getattr(self.agent_loop, 'moltbook_graph', None),
                    )
                    self.agent_loop.evaluation_agent = EvaluationAgent(
                        moltbook=self.agent_loop.moltbook_store,
                        ofc=getattr(self.agent_loop, 'orbitofrontal_cortex', None),
                        semantic_index=getattr(self.agent_loop, 'semantic_index', None),
                    )
                    self.agent_loop.curation_agent = CurationAgent(
                        moltbook=self.agent_loop.moltbook_store,
                        semantic_index=getattr(self.agent_loop, 'semantic_index', None),
                        graph=getattr(self.agent_loop, 'moltbook_graph', None),
                    )
                    research_feeder = MoltbookFeeder(
                        moltbook=self.agent_loop.moltbook_store,
                        agent_name="research_agent",
                        graph=getattr(self.agent_loop, 'moltbook_graph', None),
                    )
                    self.agent_loop.research_agent = ResearchAgent(
                        feeder=research_feeder,
                        knowledge_gap_detection=getattr(self.agent_loop, 'knowledge_gap_detection', None),
                        existential_purpose=getattr(self.agent_loop, 'existential_purpose', None),
                    )
                    self.agent_loop.feedback_agent = FeedbackAgent(
                        moltbook=self.agent_loop.moltbook_store,
                        moral_conscience=getattr(self.agent_loop, 'moral_conscience', None),
                    )
                    print("[AgentLoop] Moltbook Agents wired (Feeder + Evaluation + Curation + Research + Feedback)")
                except Exception as e:
                    print(f"[AgentLoop] Moltbook Agents not available: {e}")

                # ── Neuroscience Architecture Extensions ──

                # Wire Cerebellum (prediction + timing + error learning)
                try:
                    from core.cerebellum_module import CerebellumModule
                    if self._yaml_config and 'cerebellum' in self._yaml_config:
                        self.agent_loop.cerebellum = CerebellumModule.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.cerebellum = CerebellumModule()
                    print("[AgentLoop] Cerebellum wired (Forward/Inverse Model + Timing + Purkinje)")
                except Exception as e:
                    print(f"[AgentLoop] Cerebellum not available: {e}")

                # Wire Prefrontal Cortex (working memory + cognitive control)
                try:
                    from core.prefrontal_cortex import PrefrontalCortex
                    if self._yaml_config and 'prefrontal_cortex' in self._yaml_config:
                        self.agent_loop.prefrontal_cortex = PrefrontalCortex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.prefrontal_cortex = PrefrontalCortex()
                    print("[AgentLoop] PrefrontalCortex wired (WM + CogControl + Value + Inhibition)")
                except Exception as e:
                    print(f"[AgentLoop] PrefrontalCortex not available: {e}")

                # Wire Hypothalamus (drives + circadian + HPA stress)
                try:
                    from core.hypothalamus_drives import HypothalamusModule
                    if self._yaml_config and 'hypothalamus' in self._yaml_config:
                        self.agent_loop.hypothalamus = HypothalamusModule.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.hypothalamus = HypothalamusModule()
                    print("[AgentLoop] Hypothalamus wired (Drives + Circadian + HPA + Comparator)")
                except Exception as e:
                    print(f"[AgentLoop] Hypothalamus not available: {e}")

                # Wire Default Mode Network (self-reference + creativity)
                try:
                    from core.default_mode_network import DefaultModeNetwork
                    if self._yaml_config and 'default_mode_network' in self._yaml_config:
                        self.agent_loop.default_mode_network = DefaultModeNetwork.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.default_mode_network = DefaultModeNetwork()
                    print("[AgentLoop] DefaultModeNetwork wired (SelfRef + FutureSim + MindWander)")
                except Exception as e:
                    print(f"[AgentLoop] DefaultModeNetwork not available: {e}")

                # Wire Insular Cortex (salience + interoception)
                try:
                    from core.insular_cortex import InsularCortex
                    if self._yaml_config and 'insular_cortex' in self._yaml_config:
                        self.agent_loop.insular_cortex = InsularCortex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.insular_cortex = InsularCortex()
                    print("[AgentLoop] InsularCortex wired (Salience + Interoception + BodyBudget)")
                except Exception as e:
                    print(f"[AgentLoop] InsularCortex not available: {e}")

                # Wire Superior Colliculus (attention orienting + multisensory)
                try:
                    from core.superior_colliculus import SuperiorColliculus
                    if self._yaml_config and 'superior_colliculus' in self._yaml_config:
                        self.agent_loop.superior_colliculus = SuperiorColliculus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.superior_colliculus = SuperiorColliculus()
                    print("[AgentLoop] SuperiorColliculus wired (Saliency + Multisensory + IOR)")
                except Exception as e:
                    print(f"[AgentLoop] SuperiorColliculus not available: {e}")

                # Wire Entorhinal Cortex (grid cells + memory gateway)
                try:
                    from core.entorhinal_cortex import EntorhinalCortex
                    if self._yaml_config and 'entorhinal_cortex' in self._yaml_config:
                        self.agent_loop.entorhinal_cortex = EntorhinalCortex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.entorhinal_cortex = EntorhinalCortex()
                    print("[AgentLoop] EntorhinalCortex wired (GridCells + PathIntegration + Gateway)")
                except Exception as e:
                    print(f"[AgentLoop] EntorhinalCortex not available: {e}")

                # Wire Nucleus Accumbens (reward gateway)
                try:
                    from core.nucleus_accumbens import NucleusAccumbens
                    if self._yaml_config and 'nucleus_accumbens' in self._yaml_config:
                        self.agent_loop.nucleus_accumbens = NucleusAccumbens.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.nucleus_accumbens = NucleusAccumbens()
                    print("[AgentLoop] NucleusAccumbens wired (RewardGate + Approach/Avoid + Effort)")
                except Exception as e:
                    print(f"[AgentLoop] NucleusAccumbens not available: {e}")

                # Wire Anterior Cingulate Cortex (conflict monitoring)
                try:
                    from core.anterior_cingulate import AnteriorCingulateCortex
                    if self._yaml_config and 'anterior_cingulate' in self._yaml_config:
                        self.agent_loop.anterior_cingulate = AnteriorCingulateCortex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.anterior_cingulate = AnteriorCingulateCortex()
                    print("[AgentLoop] AnteriorCingulate wired (Conflict + ErrorLikelihood + Effort + Autonomic)")
                except Exception as e:
                    print(f"[AgentLoop] AnteriorCingulate not available: {e}")

                # Wire Phase D: Tier 1 Brain Structures
                # Amygdala Complex (emotional valence + threat detection)
                try:
                    from core.amygdala_complex import AmygdalaComplex
                    if self._yaml_config and 'amygdala' in self._yaml_config:
                        self.agent_loop.amygdala = AmygdalaComplex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.amygdala = AmygdalaComplex()
                    print("[AgentLoop] AmygdalaComplex wired (BLA + CeA + MeA: Valence + Threat + Social)")
                except Exception as e:
                    print(f"[AgentLoop] AmygdalaComplex not available: {e}")

                # Ventral Tegmental Area (reward prediction error + dopamine)
                try:
                    from core.ventral_tegmental_area import VentralTegmentalArea
                    if self._yaml_config and 'vta' in self._yaml_config:
                        self.agent_loop.ventral_tegmental_area = VentralTegmentalArea.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.ventral_tegmental_area = VentralTegmentalArea()
                    print("[AgentLoop] VentralTegmentalArea wired (DA + RPE + Salience + Motivation)")
                except Exception as e:
                    print(f"[AgentLoop] VentralTegmentalArea not available: {e}")

                # Locus Coeruleus (arousal + explore/exploit)
                try:
                    from core.locus_coeruleus import LocusCoeruleus
                    if self._yaml_config and 'locus_coeruleus' in self._yaml_config:
                        self.agent_loop.locus_coeruleus = LocusCoeruleus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.locus_coeruleus = LocusCoeruleus()
                    print("[AgentLoop] LocusCoeruleus wired (Arousal + AdaptiveGain + NetworkReset)")
                except Exception as e:
                    print(f"[AgentLoop] LocusCoeruleus not available: {e}")

                # Raphe Nuclei (patience + mood + serotonin)
                try:
                    from core.raphe_nuclei import RapheNuclei
                    if self._yaml_config and 'raphe_nuclei' in self._yaml_config:
                        self.agent_loop.raphe_nuclei = RapheNuclei.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.raphe_nuclei = RapheNuclei()
                    print("[AgentLoop] RapheNuclei wired (DRN + MRN: Patience + Mood + Theta)")
                except Exception as e:
                    print(f"[AgentLoop] RapheNuclei not available: {e}")

                # Lateral Habenula (anti-reward + avoidance learning)
                try:
                    from core.lateral_habenula import LateralHabenula
                    if self._yaml_config and 'lateral_habenula' in self._yaml_config:
                        self.agent_loop.lateral_habenula = LateralHabenula.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.lateral_habenula = LateralHabenula()
                    print("[AgentLoop] LateralHabenula wired (AntiReward + Avoidance + VTA/DRN inhibition)")
                except Exception as e:
                    print(f"[AgentLoop] LateralHabenula not available: {e}")

                # Periaqueductal Gray (defensive behavior selection)
                try:
                    from core.periaqueductal_gray import PeriaqueductalGray
                    if self._yaml_config and 'periaqueductal_gray' in self._yaml_config:
                        self.agent_loop.periaqueductal_gray = PeriaqueductalGray.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.periaqueductal_gray = PeriaqueductalGray()
                    print("[AgentLoop] PeriaqueductalGray wired (Fight/Flight/Freeze/Autonomic)")
                except Exception as e:
                    print(f"[AgentLoop] PeriaqueductalGray not available: {e}")

                # Wire Phase E: Tier 2 Brain Structures
                # Claustrum (cross-modal binding, consciousness conductor)
                try:
                    from core.claustrum import Claustrum
                    if self._yaml_config and 'claustrum' in self._yaml_config:
                        self.agent_loop.claustrum = Claustrum.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.claustrum = Claustrum()
                    print("[AgentLoop] Claustrum wired (CrossModal + Consciousness + Attention)")
                except Exception as e:
                    print(f"[AgentLoop] Claustrum not available: {e}")

                # Reticular Formation / ARAS (arousal, sensory gating)
                try:
                    from core.reticular_formation import ReticularFormation
                    if self._yaml_config and 'reticular_formation' in self._yaml_config:
                        self.agent_loop.reticular_formation = ReticularFormation.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.reticular_formation = ReticularFormation()
                    print("[AgentLoop] ReticularFormation wired (ARAS + SensoryGating + SleepWake)")
                except Exception as e:
                    print(f"[AgentLoop] ReticularFormation not available: {e}")

                # Basal Forebrain (ACh, plasticity gating)
                try:
                    from core.basal_forebrain import BasalForebrain
                    if self._yaml_config and 'basal_forebrain' in self._yaml_config:
                        self.agent_loop.basal_forebrain = BasalForebrain.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.basal_forebrain = BasalForebrain()
                    print("[AgentLoop] BasalForebrain wired (ACh + Plasticity + Encoding/Retrieval)")
                except Exception as e:
                    print(f"[AgentLoop] BasalForebrain not available: {e}")

                # Septal Nuclei (theta rhythm, memory timing)
                try:
                    from core.septal_nuclei import SeptalNuclei
                    if self._yaml_config and 'septal_nuclei' in self._yaml_config:
                        self.agent_loop.septal_nuclei = SeptalNuclei.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.septal_nuclei = SeptalNuclei()
                    print("[AgentLoop] SeptalNuclei wired (Theta + Gamma + MemoryTiming)")
                except Exception as e:
                    print(f"[AgentLoop] SeptalNuclei not available: {e}")

                # Inferior Olive (error signal for cerebellum)
                try:
                    from core.inferior_olive import InferiorOlive
                    if self._yaml_config and 'inferior_olive' in self._yaml_config:
                        self.agent_loop.inferior_olive = InferiorOlive.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.inferior_olive = InferiorOlive()
                    print("[AgentLoop] InferiorOlive wired (ErrorSignal + Timing + Teaching)")
                except Exception as e:
                    print(f"[AgentLoop] InferiorOlive not available: {e}")

                # Mammillary Bodies (Papez circuit relay)
                try:
                    from core.mammillary_bodies import MammillaryBodies
                    if self._yaml_config and 'mammillary_bodies' in self._yaml_config:
                        self.agent_loop.mammillary_bodies = MammillaryBodies.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.mammillary_bodies = MammillaryBodies()
                    print("[AgentLoop] MammillaryBodies wired (PapezRelay + SpatialMemory + Consolidation)")
                except Exception as e:
                    print(f"[AgentLoop] MammillaryBodies not available: {e}")

                # BNST (sustained anxiety, chronic stress)
                try:
                    from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
                    if self._yaml_config and 'bnst' in self._yaml_config:
                        self.agent_loop.bnst = BedNucleusStriaTerminalis.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.bnst = BedNucleusStriaTerminalis()
                    print("[AgentLoop] BNST wired (SustainedAnxiety + ChronicStress + Vigilance)")
                except Exception as e:
                    print(f"[AgentLoop] BNST not available: {e}")

                # Parabrachial Nucleus (alarm relay)
                try:
                    from core.parabrachial_nucleus import ParabrachialNucleus
                    if self._yaml_config and 'parabrachial_nucleus' in self._yaml_config:
                        self.agent_loop.parabrachial_nucleus = ParabrachialNucleus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.parabrachial_nucleus = ParabrachialNucleus()
                    print("[AgentLoop] ParabrachialNucleus wired (Alarm + InteroceptiveThreat + Teaching)")
                except Exception as e:
                    print(f"[AgentLoop] ParabrachialNucleus not available: {e}")

                # Orbitofrontal Cortex (value computation, decision)
                try:
                    from core.orbitofrontal_cortex import OrbitofrontalCortex
                    if self._yaml_config and 'orbitofrontal_cortex' in self._yaml_config:
                        self.agent_loop.orbitofrontal_cortex = OrbitofrontalCortex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.orbitofrontal_cortex = OrbitofrontalCortex()
                    print("[AgentLoop] OrbitofrontalCortex wired (Value + OutcomePrediction + ReversalLearning)")
                except Exception as e:
                    print(f"[AgentLoop] OrbitofrontalCortex not available: {e}")

                # Wire Phase F: Tier 3 Brain Structures
                # Substantia Nigra (SNc dopamine + SNr GABAergic output)
                try:
                    from core.substantia_nigra import SubstantiaNigra
                    if self._yaml_config and 'substantia_nigra' in self._yaml_config:
                        self.agent_loop.substantia_nigra = SubstantiaNigra.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.substantia_nigra = SubstantiaNigra()
                    print("[AgentLoop] SubstantiaNigra wired (SNc DA + SNr GABA + Nigrostriatal)")
                except Exception as e:
                    print(f"[AgentLoop] SubstantiaNigra not available: {e}")

                # Zona Incerta (inhibitory gating hub)
                try:
                    from core.zona_incerta import ZonaIncerta
                    if self._yaml_config and 'zona_incerta' in self._yaml_config:
                        self.agent_loop.zona_incerta = ZonaIncerta.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.zona_incerta = ZonaIncerta()
                    print("[AgentLoop] ZonaIncerta wired (Inhibition + LimbicMotor + Visceral)")
                except Exception as e:
                    print(f"[AgentLoop] ZonaIncerta not available: {e}")

                # Red Nucleus (backup motor pathway)
                try:
                    from core.red_nucleus import RedNucleus
                    if self._yaml_config and 'red_nucleus' in self._yaml_config:
                        self.agent_loop.red_nucleus = RedNucleus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.red_nucleus = RedNucleus()
                    print("[AgentLoop] RedNucleus wired (Rubrospinal Backup Motor)")
                except Exception as e:
                    print(f"[AgentLoop] RedNucleus not available: {e}")

                # Tuberomammillary Nucleus (histamine, wakefulness)
                try:
                    from core.tuberomammillary_nucleus import TuberomammillaryNucleus
                    if self._yaml_config and 'tuberomammillary_nucleus' in self._yaml_config:
                        self.agent_loop.tuberomammillary_nucleus = TuberomammillaryNucleus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.tuberomammillary_nucleus = TuberomammillaryNucleus()
                    print("[AgentLoop] TuberomammillaryNucleus wired (Histamine + Wake)")
                except Exception as e:
                    print(f"[AgentLoop] TuberomammillaryNucleus not available: {e}")

                # Pedunculopontine Nucleus (locomotion + REM)
                try:
                    from core.pedunculopontine_nucleus import PedunculopontineNucleus
                    if self._yaml_config and 'pedunculopontine_nucleus' in self._yaml_config:
                        self.agent_loop.pedunculopontine_nucleus = PedunculopontineNucleus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.pedunculopontine_nucleus = PedunculopontineNucleus()
                    print("[AgentLoop] PedunculopontineNucleus wired (Locomotion + REM)")
                except Exception as e:
                    print(f"[AgentLoop] PedunculopontineNucleus not available: {e}")

                # Ventral Pallidum (hedonic hotspot, liking/wanting)
                try:
                    from core.ventral_pallidum import VentralPallidum
                    if self._yaml_config and 'ventral_pallidum' in self._yaml_config:
                        self.agent_loop.ventral_pallidum = VentralPallidum.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.ventral_pallidum = VentralPallidum()
                    print("[AgentLoop] VentralPallidum wired (HedonicHotspot + LimbicMotor)")
                except Exception as e:
                    print(f"[AgentLoop] VentralPallidum not available: {e}")

                # Nucleus Tractus Solitarius (visceral relay)
                try:
                    from core.nucleus_tractus_solitarius import NucleusTractSolitarius
                    if self._yaml_config and 'nts' in self._yaml_config:
                        self.agent_loop.nucleus_tractus_solitarius = NucleusTractSolitarius.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.nucleus_tractus_solitarius = NucleusTractSolitarius()
                    print("[AgentLoop] NTS wired (ViscereSensory + AutonomicReflex)")
                except Exception as e:
                    print(f"[AgentLoop] NTS not available: {e}")

                # Olfactory System (bulb + piriform cortex)
                try:
                    from core.olfactory_system import OlfactorySystem
                    if self._yaml_config and 'olfactory_system' in self._yaml_config:
                        self.agent_loop.olfactory_system = OlfactorySystem.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.olfactory_system = OlfactorySystem()
                    print("[AgentLoop] OlfactorySystem wired (Bulb + PiriformCortex)")
                except Exception as e:
                    print(f"[AgentLoop] OlfactorySystem not available: {e}")

                # Fusiform Gyrus (FFA face + VWFA text)
                try:
                    from core.fusiform_gyrus import FusiformGyrus
                    if self._yaml_config and 'fusiform_gyrus' in self._yaml_config:
                        self.agent_loop.fusiform_gyrus = FusiformGyrus.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.fusiform_gyrus = FusiformGyrus()
                    print("[AgentLoop] FusiformGyrus wired (FFA + VWFA)")
                except Exception as e:
                    print(f"[AgentLoop] FusiformGyrus not available: {e}")

                # Temporoparietal Junction (theory of mind + self-other)
                try:
                    from core.temporoparietal_junction import TemporoparietalJunction
                    if self._yaml_config and 'temporoparietal_junction' in self._yaml_config:
                        self.agent_loop.temporoparietal_junction = TemporoparietalJunction.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.temporoparietal_junction = TemporoparietalJunction()
                    print("[AgentLoop] TPJ wired (TheoryOfMind + SelfOther + Reorienting)")
                except Exception as e:
                    print(f"[AgentLoop] TPJ not available: {e}")

                # Posterior Parietal Cortex (spatial attention + action planning)
                try:
                    from core.posterior_parietal_cortex import PosteriorParietalCortex
                    if self._yaml_config and 'posterior_parietal_cortex' in self._yaml_config:
                        self.agent_loop.posterior_parietal_cortex = PosteriorParietalCortex.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.posterior_parietal_cortex = PosteriorParietalCortex()
                    print("[AgentLoop] PPC wired (SpatialAttention + ReferenceFrames + ActionPlan)")
                except Exception as e:
                    print(f"[AgentLoop] PPC not available: {e}")

                # Cortical Column (canonical microcircuit)
                try:
                    from core.cortical_column import CorticalColumn
                    if self._yaml_config and 'cortical_column' in self._yaml_config:
                        self.agent_loop.cortical_column = CorticalColumn.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.cortical_column = CorticalColumn()
                    print("[AgentLoop] CorticalColumn wired (6-Layer Canonical Microcircuit)")
                except Exception as e:
                    print(f"[AgentLoop] CorticalColumn not available: {e}")

                # Pineal Gland (melatonin + circadian)
                try:
                    from core.pineal_gland import PinealGland
                    if self._yaml_config and 'pineal_gland' in self._yaml_config:
                        self.agent_loop.pineal_gland = PinealGland.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.pineal_gland = PinealGland()
                    print("[AgentLoop] PinealGland wired (Melatonin + CircadianEntrainer)")
                except Exception as e:
                    print(f"[AgentLoop] PinealGland not available: {e}")

                # Corpus Callosum (interhemispheric transfer)
                try:
                    from core.corpus_callosum import CorpusCallosum
                    if self._yaml_config and 'corpus_callosum' in self._yaml_config:
                        self.agent_loop.corpus_callosum = CorpusCallosum.from_yaml(self._yaml_config)
                    else:
                        self.agent_loop.corpus_callosum = CorpusCallosum()
                    print("[AgentLoop] CorpusCallosum wired (Interhemispheric + Bilateral)")
                except Exception as e:
                    print(f"[AgentLoop] CorpusCallosum not available: {e}")

                # Radial Attention Network — learned intelligence core
                try:
                    from core.radial_attention import RadialAttentionNetwork, DualProcessRouter
                    from core.hebbian_plasticity import HebbianAttentionUpdate
                    from core.experience_buffer import ExperienceBuffer
                    from core.radial_sleep_trainer import RadialSleepTrainer

                    rc = self._yaml_config.get('radial_attention', {})
                    if rc.get('enable_radial', False):
                        self.agent_loop.radial_network = RadialAttentionNetwork.from_yaml(self._yaml_config)
                        self.agent_loop.dual_process = DualProcessRouter(
                            dim=128, conflict_threshold=rc.get('conflict_threshold', 0.3)
                        )
                        self.agent_loop.hebbian = HebbianAttentionUpdate(
                            learning_rate=rc.get('hebbian_learning_rate', 0.001),
                            decay=rc.get('hebbian_decay', 0.0001),
                        )
                        self.agent_loop.experience_buffer = ExperienceBuffer(
                            max_size=rc.get('experience_buffer_size', 5000)
                        )
                        self.agent_loop.radial_trainer = RadialSleepTrainer(
                            network=self.agent_loop.radial_network,
                            buffer=self.agent_loop.experience_buffer,
                            lr=rc.get('sleep_training_lr', 0.001),
                            ewc_lambda=rc.get('ewc_lambda', 100.0),
                        )
                        params = sum(p.numel() for p in self.agent_loop.radial_network.parameters())
                        print(f"[AgentLoop] RadialAttentionNetwork wired ({params:,} params)")

                        # SeedEncoder — task context -> 384-dim thalamic seed
                        try:
                            from core.seed_encoder import SeedEncoder
                            self.agent_loop.seed_encoder = SeedEncoder(
                                seed_dim=rc.get('seed_dim', 384),
                            )
                            print("[AgentLoop] SeedEncoder wired -> RadialAttentionNetwork")
                        except Exception as e:
                            print(f"[AgentLoop] SeedEncoder failed: {e}")

                        # Neuromodulation Bridge — connect brain modules to Radial Network
                        nm_cfg = self._yaml_config.get('neuromodulation_bridge', {})
                        if nm_cfg.get('enabled', False):
                            try:
                                from core.neuromodulation_bridge import NeuromodulationBridge
                                bridge = NeuromodulationBridge(
                                    vta=self.agent_loop.ventral_tegmental_area,
                                    lc=self.agent_loop.locus_coeruleus,
                                    raphe=self.agent_loop.raphe_nuclei,
                                    basal_forebrain=self.agent_loop.basal_forebrain,
                                    lateral_habenula=self.agent_loop.lateral_habenula,
                                )
                                self.agent_loop.radial_network.attach_neuromodulation(bridge)
                                self.agent_loop.neuromod_bridge = bridge
                                print("[AgentLoop] NeuromodulationBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] NeuromodulationBridge not available: {e}")

                        # Cortex Bridge — connect PFC + ACC + OFC to Radial Network
                        cx_cfg = self._yaml_config.get('cortex_bridge', {})
                        if cx_cfg.get('enabled', False):
                            try:
                                from core.cortex_bridge import CortexBridge
                                cortex_bridge = CortexBridge(
                                    pfc=self.agent_loop.prefrontal_cortex,
                                    acc=self.agent_loop.anterior_cingulate,
                                    ofc=self.agent_loop.orbitofrontal_cortex,
                                )
                                self.agent_loop.radial_network.attach_cortex(cortex_bridge)
                                self.agent_loop.cortex_bridge = cortex_bridge
                                print("[AgentLoop] CortexBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] CortexBridge not available: {e}")

                        # Limbic Bridge — connect Amygdala + NAcc + InsularCortex + Hypothalamus
                        lm_cfg = self._yaml_config.get('limbic_bridge', {})
                        if lm_cfg.get('enabled', False):
                            try:
                                from core.limbic_bridge import LimbicBridge
                                limbic_bridge = LimbicBridge(
                                    amygdala=self.agent_loop.amygdala,
                                    nucleus_accumbens=self.agent_loop.nucleus_accumbens,
                                    insular_cortex=self.agent_loop.insular_cortex,
                                    hypothalamus=self.agent_loop.hypothalamus,
                                )
                                self.agent_loop.radial_network.attach_limbic(limbic_bridge)
                                self.agent_loop.limbic_bridge = limbic_bridge
                                print("[AgentLoop] LimbicBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] LimbicBridge not available: {e}")

                        # SleepWake Bridge — RF + TMN + PG + PPN
                        sw_cfg = self._yaml_config.get('sleep_wake_bridge', {})
                        if sw_cfg.get('enabled', False):
                            try:
                                from core.sleep_wake_bridge import SleepWakeBridge
                                sleep_wake_bridge = SleepWakeBridge(
                                    reticular_formation=self.agent_loop.reticular_formation,
                                    tuberomammillary_nucleus=self.agent_loop.tuberomammillary_nucleus,
                                    pineal_gland=self.agent_loop.pineal_gland,
                                    pedunculopontine_nucleus=self.agent_loop.pedunculopontine_nucleus,
                                )
                                self.agent_loop.radial_network.attach_bridge('sleep_wake', sleep_wake_bridge)
                                self.agent_loop.sleep_wake_bridge = sleep_wake_bridge
                                print("[AgentLoop] SleepWakeBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] SleepWakeBridge not available: {e}")

                        # Motor Bridge — CB + SN + ZI + RN + PPC
                        mt_cfg = self._yaml_config.get('motor_bridge', {})
                        if mt_cfg.get('enabled', False):
                            try:
                                from core.motor_bridge import MotorBridge
                                motor_bridge = MotorBridge(
                                    cerebellum=self.agent_loop.cerebellum,
                                    substantia_nigra=self.agent_loop.substantia_nigra,
                                    zona_incerta=self.agent_loop.zona_incerta,
                                    red_nucleus=self.agent_loop.red_nucleus,
                                    posterior_parietal_cortex=self.agent_loop.posterior_parietal_cortex,
                                )
                                self.agent_loop.radial_network.attach_bridge('motor', motor_bridge)
                                self.agent_loop.motor_bridge = motor_bridge
                                print("[AgentLoop] MotorBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] MotorBridge not available: {e}")

                        # Defense Bridge — PBN + BNST + PAG
                        df_cfg = self._yaml_config.get('defense_bridge', {})
                        if df_cfg.get('enabled', False):
                            try:
                                from core.defense_bridge import DefenseBridge
                                defense_bridge = DefenseBridge(
                                    parabrachial_nucleus=self.agent_loop.parabrachial_nucleus,
                                    bnst=self.agent_loop.bnst,
                                    periaqueductal_gray=self.agent_loop.periaqueductal_gray,
                                )
                                self.agent_loop.radial_network.attach_bridge('defense', defense_bridge)
                                self.agent_loop.defense_bridge = defense_bridge
                                print("[AgentLoop] DefenseBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] DefenseBridge not available: {e}")

                        # Memory Bridge — SN (Septal) + EC + MB + IO
                        mem_cfg = self._yaml_config.get('memory_bridge', {})
                        if mem_cfg.get('enabled', False):
                            try:
                                from core.memory_bridge import MemoryBridge
                                memory_bridge = MemoryBridge(
                                    septal_nuclei=self.agent_loop.septal_nuclei,
                                    entorhinal_cortex=self.agent_loop.entorhinal_cortex,
                                    mammillary_bodies=self.agent_loop.mammillary_bodies,
                                    inferior_olive=self.agent_loop.inferior_olive,
                                )
                                self.agent_loop.radial_network.attach_bridge('memory', memory_bridge)
                                self.agent_loop.memory_bridge = memory_bridge
                                print("[AgentLoop] MemoryBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] MemoryBridge not available: {e}")

                        # Integration Bridge — SC + DMN + Claustrum + CorticalColumn + CC
                        ig_cfg = self._yaml_config.get('integration_bridge', {})
                        if ig_cfg.get('enabled', False):
                            try:
                                from core.integration_bridge import IntegrationBridge
                                integration_bridge = IntegrationBridge(
                                    superior_colliculus=self.agent_loop.superior_colliculus,
                                    default_mode_network=self.agent_loop.default_mode_network,
                                    claustrum=self.agent_loop.claustrum,
                                    cortical_column=self.agent_loop.cortical_column,
                                    corpus_callosum=self.agent_loop.corpus_callosum,
                                )
                                self.agent_loop.radial_network.attach_bridge('integration', integration_bridge)
                                self.agent_loop.integration_bridge = integration_bridge
                                print("[AgentLoop] IntegrationBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] IntegrationBridge not available: {e}")

                        # Visceral Bridge — NTS + VP
                        vs_cfg = self._yaml_config.get('visceral_bridge', {})
                        if vs_cfg.get('enabled', False):
                            try:
                                from core.visceral_bridge import VisceralBridge
                                visceral_bridge = VisceralBridge(
                                    nucleus_tractus_solitarius=self.agent_loop.nucleus_tractus_solitarius,
                                    ventral_pallidum=self.agent_loop.ventral_pallidum,
                                )
                                self.agent_loop.radial_network.attach_bridge('visceral', visceral_bridge)
                                self.agent_loop.visceral_bridge = visceral_bridge
                                print("[AgentLoop] VisceralBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] VisceralBridge not available: {e}")

                        # Social Perception Bridge — Olfactory + FG + TPJ
                        sp_cfg = self._yaml_config.get('social_perception_bridge', {})
                        if sp_cfg.get('enabled', False):
                            try:
                                from core.social_perception_bridge import SocialPerceptionBridge
                                social_perception_bridge = SocialPerceptionBridge(
                                    olfactory_system=self.agent_loop.olfactory_system,
                                    fusiform_gyrus=self.agent_loop.fusiform_gyrus,
                                    temporoparietal_junction=self.agent_loop.temporoparietal_junction,
                                )
                                self.agent_loop.radial_network.attach_bridge('social', social_perception_bridge)
                                self.agent_loop.social_perception_bridge = social_perception_bridge
                                print("[AgentLoop] SocialPerceptionBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] SocialPerceptionBridge not available: {e}")
                    else:
                        print("[AgentLoop] RadialAttention disabled in config")
                except Exception as e:
                    import traceback
                    print(f"[AgentLoop] RadialAttention not available: {e}")
                    traceback.print_exc()

                # ── Phase 10: Minibook + MCP ──

                # MinibookClient — REST API wrapper for Minibook collaboration
                minibook_cfg = self._yaml_config.get('minibook', {})
                if minibook_cfg.get('enabled', False):
                    try:
                        from core.minibook_client import MinibookClient
                        minibook_client = MinibookClient(
                            base_url=minibook_cfg.get('base_url', 'http://localhost:8800'),
                            api_key=minibook_cfg.get('api_key', ''),
                            agent_name=minibook_cfg.get('agent_name', 'Tahlamus'),
                        )
                        self.agent_loop.minibook_client = minibook_client
                        # Register with Minibook (non-blocking, graceful if offline)
                        minibook_client.register()
                        print(f"[AgentLoop] MinibookClient wired (online={minibook_client.is_online})")
                    except Exception as e:
                        print(f"[AgentLoop] MinibookClient not available: {e}")
                        minibook_client = None
                else:
                    minibook_client = None

                # MinibookSensor — polls Minibook for social signals
                if minibook_client is not None:
                    try:
                        from core.sensor_systems import MinibookSensor
                        minibook_sensor = MinibookSensor(
                            minibook_client=minibook_client,
                            poll_interval=minibook_cfg.get('poll_interval', 30.0),
                        )
                        self.agent_loop.minibook_sensor = minibook_sensor
                        # Register with sensor_registry if available
                        if hasattr(self.agent_loop, 'sensor_registry') and self.agent_loop.sensor_registry is not None:
                            self.agent_loop.sensor_registry.register('minibook', minibook_sensor)
                        print("[AgentLoop] MinibookSensor wired -> SensorRegistry")
                    except Exception as e:
                        print(f"[AgentLoop] MinibookSensor not available: {e}")

                # MCP Server — JSON-RPC 2.0 brain state exposure
                mcp_cfg = self._yaml_config.get('mcp_server', {})
                if mcp_cfg.get('enabled', False):
                    try:
                        from core.mcp_server import MCPServer

                        def _brain_state_fn():
                            """Collect current brain state for MCP."""
                            state = {}
                            if hasattr(self.agent_loop, 'radial_network') and self.agent_loop.radial_network is not None:
                                rn = self.agent_loop.radial_network
                                if hasattr(rn, '_last_output') and rn._last_output:
                                    state.update(rn._last_output)
                                if hasattr(rn, '_consciousness_loop') and rn._consciousness_loop is not None:
                                    cs = rn._consciousness_loop.get_stats()
                                    state['consciousness'] = cs
                            return state

                        def _bridge_state_fn(name):
                            """Get a specific bridge state for MCP."""
                            if hasattr(self.agent_loop, 'radial_network') and self.agent_loop.radial_network is not None:
                                rn = self.agent_loop.radial_network
                                bs = getattr(rn, '_bridge_states', {})
                                bridge_state = bs.get(name)
                                if bridge_state is not None and hasattr(bridge_state, '__dict__'):
                                    return bridge_state.__dict__
                            return {}

                        def _minibook_status_fn():
                            """Get Minibook status for MCP."""
                            if hasattr(self.agent_loop, 'minibook_client') and self.agent_loop.minibook_client is not None:
                                return self.agent_loop.minibook_client.get_status()
                            return {'online': False, 'note': 'MinibookClient not configured'}

                        mcp_server = MCPServer(
                            brain_state_fn=_brain_state_fn,
                            bridge_state_fn=_bridge_state_fn,
                            minibook_status_fn=_minibook_status_fn,
                            host=mcp_cfg.get('host', '127.0.0.1'),
                            port=mcp_cfg.get('port', 8900),
                        )
                        self.agent_loop.mcp_server = mcp_server
                        mcp_server.start()
                        print(f"[AgentLoop] MCPServer started on {mcp_cfg.get('host', '127.0.0.1')}:{mcp_cfg.get('port', 8900)}")
                    except Exception as e:
                        print(f"[AgentLoop] MCPServer not available: {e}")

                print("[AgentLoop] Autonomous agent loop ENABLED")
            except Exception as e:
                print(f"[AgentLoop] Failed to initialize: {e}")
                self.agent_loop = None

        # Sensory preprocessor (optional - for enriched feature extraction)
        self.sensory_preprocessor = None
        try:
            from core.sensory_preprocessor import SensoryPreprocessor
            self.sensory_preprocessor = SensoryPreprocessor()
            print("[Sensory] SensoryPreprocessor initialized")
        except ImportError:
            pass

        # Statistics
        self.total_predictions = 0
        self.total_feedback = 0
        self.feedback_buffer = []
        self.performance_log = []

        # Initialize subsystem registry (P4.51-54)
        self.registry = SubsystemRegistry()
        self._register_subsystems()

        # Initialize monitoring (P4.60-65)
        self.metrics = BrainMetrics.instance()
        self.audit_log = PredictionAuditLog(
            log_dir=self._yaml_config.get('directories', {}).get('session_logs', 'data/logs/sessions'),
            max_memory=500
        )
        self.loop_tracer = CognitiveLoopTracer(max_traces=100)
        self.error_tracker = ErrorRateTracker(window_seconds=300.0)
        self.activity_heatmap = ActivityHeatmap(max_snapshots=200)

        # Wire tracer into cognitive loop (P4.63)
        if self.cognitive_loop:
            self.cognitive_loop._tracer = self.loop_tracer

        print("Production planner ready!")
        print()

    def _register_subsystems(self):
        """Register all subsystems in the central registry (P4.51-54)."""
        p = self.planner

        # Core layers
        if hasattr(p, 'layer1'):
            self.registry.register('layer1', p.layer1)
        if hasattr(p, 'layer2'):
            self.registry.register('layer2', p.layer2)
        if hasattr(p, 'layer3'):
            self.registry.register('layer3', p.layer3)
        if hasattr(p, 'layer4') and p.layer4 is not None:
            self.registry.register('layer4', p.layer4)

        # Cognitive systems
        if hasattr(p, 'memory') and p.memory is not None:
            self.registry.register('memory', p.memory)
        if hasattr(p, 'attention') and p.attention is not None:
            self.registry.register('attention', p.attention)
        if hasattr(p, 'neuromodulation') and p.neuromodulation is not None:
            self.registry.register('neuromodulation', p.neuromodulation)
        if hasattr(p, 'predictive_coding') and p.predictive_coding is not None:
            self.registry.register('predictive_coding', p.predictive_coding)
        if hasattr(p, 'active_inference') and p.active_inference is not None:
            self.registry.register('active_inference', p.active_inference)
        if hasattr(p, 'consciousness') and p.consciousness is not None:
            self.registry.register('consciousness', p.consciousness)
        if hasattr(p, 'meta_learner') and p.meta_learner is not None:
            self.registry.register('meta_learner', p.meta_learner)
        if hasattr(p, 'dream_mode') and p.dream_mode is not None:
            self.registry.register('dream_mode', p.dream_mode)
        if hasattr(p, 'temporal_memory') and p.temporal_memory is not None:
            self.registry.register('temporal_memory', p.temporal_memory)

        # Goal graph
        if hasattr(p, 'goal_graph') and p.goal_graph is not None:
            self.registry.register('goal_graph', p.goal_graph)

        # Emotional system
        if hasattr(p, 'emotional_system') and p.emotional_system is not None:
            self.registry.register('emotional', p.emotional_system)

        # Homeostatic regulation
        if hasattr(p, 'homeostatic') and p.homeostatic is not None:
            self.registry.register('homeostatic', p.homeostatic)

        # CTM ensemble
        if hasattr(p, 'ctm_ensemble') and p.ctm_ensemble is not None:
            self.registry.register('ctm_ensemble', p.ctm_ensemble)

        # Optional systems
        if self.cognitive_loop is not None:
            self.registry.register('cognitive_loop', self.cognitive_loop)
        if self.sensory_preprocessor is not None:
            self.registry.register('sensory', self.sensory_preprocessor)
        if self.swarm is not None:
            self.registry.register('swarm', self.swarm,
                                   category='optional',
                                   description='MultiBrainSwarm: semantic coherence validation')

        # Brain monitor (lives on layer2)
        if hasattr(p, 'layer2') and hasattr(p.layer2, 'brain_monitor'):
            self.registry.register('brain_monitor', p.layer2.brain_monitor)

        logger.info(f"[Registry] Registered {len(self.registry.list_names())} subsystems")

    def _load_matrix(self, version: Optional[str] = None) -> str:
        """
        Load trained routing matrix

        Args:
            version: Specific version to load (None = latest)

        Returns:
            Loaded version string
        """
        # Find available matrices
        matrix_files = list(self.matrix_dir.glob("routing_matrix_v*.npy"))

        if not matrix_files:
            print("No trained matrix found, using random initialization")
            return "random_v0"

        if version is None:
            # Load latest
            matrix_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            matrix_path = matrix_files[0]
            version = matrix_path.stem.replace("routing_matrix_", "")
        else:
            # Load specific version
            matrix_path = self.matrix_dir / f"routing_matrix_{version}.npy"
            if not matrix_path.exists():
                print(f"Version {version} not found, using random")
                return "random_v0"

        # Load matrix
        matrix = np.load(matrix_path)
        self.planner.layer3.multi_target_router.set_routing_matrix(matrix)

        # Load metadata if available
        meta_path = matrix_path.with_suffix('.json')
        if meta_path.exists():
            with open(meta_path, 'r') as f:
                meta = json.load(f)
                print(f"Matrix metadata: {meta}")

        return version

    def predict(self, task: str) -> Dict:
        """
        Make prediction for a task

        Args:
            task: Task description

        Returns:
            Prediction dict with all info
        """
        import time as _time

        # Make prediction (cognitive loop or legacy pipeline)
        predict_start = _time.time()
        if self.cognitive_loop:
            prediction = self.cognitive_loop.process(task)
        else:
            prediction = self.planner.predict(task)
        predict_elapsed_ms = (_time.time() - predict_start) * 1000

        # Extract info
        result = {
            'task': task,
            'prediction': {
                'primary_action': prediction.actionable_decision.multi_target_decision['primary']['type'],
                'primary_weight': prediction.actionable_decision.multi_target_decision['primary']['weight'],
                'primary_reasoning': prediction.actionable_decision.multi_target_decision['primary']['reasoning'],
                'alternatives': [
                    {
                        'action': alt['type'],
                        'weight': alt['weight']
                    }
                    for alt in prediction.actionable_decision.multi_target_decision['alternatives'][:2]
                ],
                'confidence': prediction.confidence,
                'processing_mode': prediction.layer1_routing.processing_mode,
                'task_type': prediction.layer1_routing.features.task_type,
                'complexity': prediction.layer1_routing.features.complexity,
                'urgency': prediction.layer1_routing.features.urgency,
                'executable_tool_calls': None  # Will fill if execute intervention
            },
            'brain_state': {
                'dominant_modalities': prediction.dominant_modalities,
                'gates': None  # Will fill below
            },
            'reasoning_chain': prediction.actionable_decision.reasoning_chain,
            'latency': {
                'total_ms': round(predict_elapsed_ms, 2),
                'pipeline_mode': 'cognitive_loop' if self.cognitive_loop else 'legacy',
            }
        }

        # Add per-layer latency from planner (P4.55)
        if hasattr(self.planner, 'layer_timing') and self.planner.layer_timing:
            layer_latency = {}
            for layer_name, times in self.planner.layer_timing.items():
                if times:
                    layer_latency[layer_name] = round(times[-1] * 1000, 2)  # Last measurement in ms
            result['latency']['per_layer_ms'] = layer_latency

        # Add executable tool calls if intervention is 'execute'
        if prediction.actionable_decision.executable_tool_calls is not None:
            result['prediction']['executable_tool_calls'] = prediction.actionable_decision.executable_tool_calls

        # Get brain gates
        if hasattr(self.planner.layer2, 'brain_monitor') and self.planner.layer2.brain_monitor.gate_history:
            gates = list(self.planner.layer2.brain_monitor.gate_history)[-1]
            result['brain_state']['gates'] = gates.tolist()

        # Semantic coherence validation (Phase 13)
        if self.enable_semantic_coherence and self.swarm is not None:
            # Collect brain votes for semantic validation
            task_type = prediction.layer1_routing.features.task_type
            available_decisions = ['suggest', 'retry', 'wait', 'terminate', 'execute']

            swarm_decision = self.swarm.collect_brain_votes(
                task_description=task,
                task_type=task_type,
                available_decisions=available_decisions,
                brain_gates=None,
                brain_reasonings=None
            )

            # Add semantic coherence metrics to result
            result['semantic_coherence'] = {
                'coherence_K': float(swarm_decision.coherence_K),
                'disagreement_U': float(swarm_decision.disagreement_U),
                'truth_stability': float(swarm_decision.truth_stability),
                'semantic_status': swarm_decision.semantic_status,  # GREEN/YELLOW/RED
                'swarm_consensus': swarm_decision.consensus_decision,
                'swarm_confidence': float(swarm_decision.consensus_confidence)
            }

            # Add semantic reasoning to reasoning chain
            result['reasoning_chain'].append(
                f"[Semantic Coherence] {len(self.swarm.brains)} brains analyzed: "
                f"K={swarm_decision.coherence_K:.3f}, "
                f"truth_stability={swarm_decision.truth_stability:.3f}, "
                f"status={swarm_decision.semantic_status}"
            )
        else:
            result['semantic_coherence'] = None

        # ========== COGNITIVE SYSTEMS INTEGRATION (Phase 1-12) ==========

        # 1. MEMORY SYSTEMS (Phase 1) - Working/Episodic Memory
        if self.planner.enable_memory and self.planner.memory:
            try:
                # Get working memory buffer (already stored in hierarchical_planner)
                working_entries = self.planner.memory.working.get_recent(n=5)

                # Get important episodic memories
                episodic_entries = self.planner.memory.episodic.get_important_memories(top_k=5)

                result['memory_context'] = {
                    'working_memory': [entry.task for entry in working_entries],
                    'episodic_memories': [
                        {'task': e.task, 'decision': e.decision, 'outcome': e.outcome}
                        for e in episodic_entries
                    ],
                    'working_memory_size': len(self.planner.memory.working.buffer),
                    'episodic_memory_size': len(self.planner.memory.episodic.memories)
                }

                result['reasoning_chain'].append(
                    f"[Memory] Retrieved {len(working_entries)} working memories, {len(episodic_entries)} episodic memories"
                )
            except Exception as e:
                result['memory_context'] = {'error': str(e)}
        else:
            result['memory_context'] = None

        # 2. PREDICTIVE CODING (Phase 2) - Prediction errors & curiosity
        if hasattr(prediction, 'prediction_errors') and prediction.prediction_errors:
            try:
                result['predictive_coding'] = {
                    'prediction_errors': prediction.prediction_errors,
                    'curiosity_signal': prediction.curiosity_signal if hasattr(prediction, 'curiosity_signal') and prediction.curiosity_signal else None,
                    'novelty_detected': prediction.curiosity_signal.get('novelty_detected', False) if hasattr(prediction, 'curiosity_signal') and prediction.curiosity_signal else False
                }

                if result['predictive_coding']['novelty_detected']:
                    result['reasoning_chain'].append(
                        "[Predictive Coding] Novel situation detected - high curiosity signal"
                    )
            except Exception as e:
                result['predictive_coding'] = {'error': str(e)}
        else:
            result['predictive_coding'] = None

        # 3. ATTENTION MECHANISMS (Phase 3) - Selective focus
        if hasattr(prediction, 'attention_state') and prediction.attention_state:
            try:
                result['attention_state'] = {
                    'focused_modalities': prediction.attention_state.focused_modalities if hasattr(prediction.attention_state, 'focused_modalities') else [],
                    'attention_weights': prediction.attention_state.attention_weights.tolist() if hasattr(prediction.attention_state, 'attention_weights') else [],
                    'top_modality': prediction.dominant_modalities[0] if prediction.dominant_modalities else None
                }

                result['reasoning_chain'].append(
                    f"[Attention] Focused on {result['attention_state']['top_modality']}"
                )
            except Exception as e:
                result['attention_state'] = {'error': str(e)}
        else:
            result['attention_state'] = None

        # 4. META-LEARNING (Phase 4) - Adaptive learning rate
        if hasattr(prediction, 'meta_parameters') and prediction.meta_parameters:
            try:
                result['meta_learning'] = {
                    'adapted_learning_rate': prediction.meta_parameters.adapted_lr if hasattr(prediction.meta_parameters, 'adapted_lr') else None,
                    'task_similarity': prediction.meta_parameters.task_similarity if hasattr(prediction.meta_parameters, 'task_similarity') else None,
                    'exploration_rate': prediction.meta_parameters.exploration_rate if hasattr(prediction.meta_parameters, 'exploration_rate') else None
                }

                if result['meta_learning']['adapted_learning_rate']:
                    result['reasoning_chain'].append(
                        f"[Meta-Learning] Adapted LR to {result['meta_learning']['adapted_learning_rate']:.4f}"
                    )
            except Exception as e:
                result['meta_learning'] = {'error': str(e)}
        else:
            result['meta_learning'] = None

        # 5. NEUROMODULATION (Phase 6) - Dopamine/Serotonin/Noradrenaline
        if hasattr(prediction, 'neuromodulator_levels') and prediction.neuromodulator_levels:
            try:
                levels = prediction.neuromodulator_levels
                effects = prediction.neuromodulator_effects if hasattr(prediction, 'neuromodulator_effects') else None

                result['neuromodulation'] = {
                    'dopamine': levels.dopamine if hasattr(levels, 'dopamine') else None,
                    'serotonin': levels.serotonin if hasattr(levels, 'serotonin') else None,
                    'noradrenaline': levels.noradrenaline if hasattr(levels, 'noradrenaline') else None,
                    'effects': {
                        'learning_rate_boost': effects.learning_rate_boost if effects and hasattr(effects, 'learning_rate_boost') else 1.0,
                        'exploration_boost': effects.exploration_boost if effects and hasattr(effects, 'exploration_boost') else 1.0,
                        'focus_boost': effects.focus_boost if effects and hasattr(effects, 'focus_boost') else 1.0
                    } if effects else None
                }

                if result['neuromodulation']['dopamine'] and result['neuromodulation']['dopamine'] > 0.7:
                    result['reasoning_chain'].append(
                        f"[Neuromodulation] High dopamine ({result['neuromodulation']['dopamine']:.2f}) - increased learning"
                    )
            except Exception as e:
                result['neuromodulation'] = {'error': str(e)}
        else:
            result['neuromodulation'] = None

        # 6. TEMPORAL MEMORY (Phase 7) - Time-based patterns
        if hasattr(prediction, 'temporal_context') and prediction.temporal_context:
            try:
                result['temporal_context'] = {
                    'time_of_day': prediction.temporal_context.time_of_day if hasattr(prediction.temporal_context, 'time_of_day') else None,
                    'day_of_week': prediction.temporal_context.day_of_week if hasattr(prediction.temporal_context, 'day_of_week') else None,
                    'temporal_patterns': prediction.temporal_context.relevant_patterns if hasattr(prediction.temporal_context, 'relevant_patterns') else []
                }

                if result['temporal_context']['temporal_patterns']:
                    result['reasoning_chain'].append(
                        f"[Temporal Memory] {len(result['temporal_context']['temporal_patterns'])} time-based patterns detected"
                    )
            except Exception as e:
                result['temporal_context'] = {'error': str(e)}
        else:
            result['temporal_context'] = None

        # 7. ACTIVE INFERENCE (Phase 8) - Belief updating & questions
        if hasattr(prediction, 'inference_state') and prediction.inference_state:
            try:
                result['active_inference'] = {
                    'beliefs': prediction.inference_state.beliefs if hasattr(prediction.inference_state, 'beliefs') else {},
                    'free_energy': prediction.inference_state.free_energy if hasattr(prediction.inference_state, 'free_energy') else None,
                    'hypotheses': prediction.inference_state.hypotheses if hasattr(prediction.inference_state, 'hypotheses') else [],
                    'questions_to_ask': prediction.inference_state.questions if hasattr(prediction.inference_state, 'questions') else []
                }

                if result['active_inference']['questions_to_ask']:
                    result['reasoning_chain'].append(
                        f"[Active Inference] {len(result['active_inference']['questions_to_ask'])} clarification questions generated"
                    )
            except Exception as e:
                result['active_inference'] = {'error': str(e)}
        else:
            result['active_inference'] = None

        # 8. COMPOSITIONAL REASONING (Phase 9) - Task decomposition
        if hasattr(prediction, 'composition_result') and prediction.composition_result:
            try:
                result['composition'] = {
                    'subtasks': prediction.composition_result.subtasks if hasattr(prediction.composition_result, 'subtasks') else [],
                    'dependencies': prediction.composition_result.dependencies if hasattr(prediction.composition_result, 'dependencies') else [],
                    'composed_confidence': prediction.composition_result.composed_confidence if hasattr(prediction.composition_result, 'composed_confidence') else None
                }

                if result['composition']['subtasks']:
                    result['reasoning_chain'].append(
                        f"[Compositional Reasoning] Decomposed into {len(result['composition']['subtasks'])} subtasks"
                    )
            except Exception as e:
                result['composition'] = {'error': str(e)}
        else:
            result['composition'] = None

        # 9. TOOL CREATION (Phase 10) - Dynamic tool generation
        if hasattr(prediction, 'created_tools') and prediction.created_tools:
            try:
                result['tool_creation'] = {
                    'new_tools_created': prediction.created_tools if hasattr(prediction, 'created_tools') else [],
                    'reusable': len(prediction.created_tools) > 0 if hasattr(prediction, 'created_tools') else False
                }

                if result['tool_creation']['new_tools_created']:
                    result['reasoning_chain'].append(
                        f"[Tool Creation] Created {len(result['tool_creation']['new_tools_created'])} new tools"
                    )
            except Exception as e:
                result['tool_creation'] = {'error': str(e)}
        else:
            result['tool_creation'] = None

        # 10. CONSCIOUSNESS METRICS (Phase 11) - Global Workspace
        if hasattr(prediction, 'cognitive_state') and prediction.cognitive_state:
            try:
                cs = prediction.cognitive_state

                # Calculate integration level (based on attention + memory load)
                # High integration = focused attention + manageable memory load
                integration_level = (
                    (1.0 if cs.attention_focus == 'focused' else 0.5 if cs.attention_focus == 'distributed' else 0.3) *
                    (1.0 - cs.memory_load * 0.5)  # Less load = better integration
                )

                # Calculate broadcast strength (based on confidence + reasoning depth)
                # High broadcast = high confidence + deep reasoning
                broadcast_strength = (
                    cs.confidence_in_state * 0.7 +
                    (cs.reasoning_depth / 3.0) * 0.3  # Normalize reasoning depth (0-3 -> 0-1)
                )

                # Calculate awareness score (based on all factors)
                # Low uncertainty + focused attention + deep reasoning = high awareness
                awareness_score = (
                    (1.0 - cs.uncertainty_level) * 0.4 +  # Less uncertain = more aware
                    integration_level * 0.3 +
                    broadcast_strength * 0.3
                )

                # Determine global workspace state
                if awareness_score > 0.7:
                    workspace_state = 'conscious'  # High awareness
                elif awareness_score > 0.4:
                    workspace_state = 'semi-conscious'  # Medium awareness
                else:
                    workspace_state = 'unconscious'  # Low awareness (automatic processing)

                result['consciousness_metrics'] = {
                    'integration_level': round(integration_level, 3),
                    'broadcast_strength': round(broadcast_strength, 3),
                    'awareness_score': round(awareness_score, 3),
                    'global_workspace_state': workspace_state,
                    # Include raw state for debugging
                    'attention_focus': cs.attention_focus,
                    'memory_load': round(cs.memory_load, 3),
                    'reasoning_depth': cs.reasoning_depth,
                    'uncertainty_level': round(cs.uncertainty_level, 3),
                    'confidence_in_state': round(cs.confidence_in_state, 3)
                }

                result['reasoning_chain'].append(
                    f"[Consciousness] Awareness={awareness_score:.2f}, State={workspace_state}, "
                    f"Integration={integration_level:.2f}, Broadcast={broadcast_strength:.2f}"
                )
            except Exception as e:
                result['consciousness_metrics'] = {'error': str(e)}
        else:
            result['consciousness_metrics'] = None

        # 11. CTM ASYNC INSIGHTS (Phase 13) - Deep reasoning
        if hasattr(prediction, 'ctm_task_id') and prediction.ctm_task_id:
            result['ctm_task_id'] = prediction.ctm_task_id

        if hasattr(prediction, 'ctm_insights') and prediction.ctm_insights:
            result['ctm_insights'] = prediction.ctm_insights
            result['reasoning_chain'].append(
                "[CTM Async] Deep reasoning insights available"
            )
        else:
            result['ctm_insights'] = None

        # 12. INFINITE CHAT (Phase 12) - Automatic semantic memory
        if self.planner.user_id:
            result['infinite_chat'] = {
                'enabled': True,
                'user_id': self.planner.user_id,
                'automatic_memory': 'All predictions are automatically stored and retrieved via Supermemory'
            }
            # Note: Memory retrieval happens automatically in MultiLLMRouter
            # No explicit action needed here
        else:
            result['infinite_chat'] = None

        # ========== END COGNITIVE SYSTEMS INTEGRATION ==========

        # 13. SENSORY PREPROCESSING - Multi-channel feature extraction
        if self.sensory_preprocessor:
            try:
                sensory_features = self.sensory_preprocessor.extract(task)
                result['sensory_features'] = {
                    'detected_intent': sensory_features.detected_intent,
                    'detected_domain': sensory_features.detected_domain,
                    'overall_complexity': round(sensory_features.overall_complexity, 3),
                    'overall_urgency': round(sensory_features.overall_urgency, 3),
                    'overall_risk': round(sensory_features.overall_risk, 3),
                }
                if sensory_features.overall_urgency > 0.5:
                    result['reasoning_chain'].append(
                        f"[Sensory] High urgency detected ({sensory_features.overall_urgency:.2f}), "
                        f"domain={sensory_features.detected_domain}, intent={sensory_features.detected_intent}"
                    )
                if sensory_features.overall_risk > 0.5:
                    result['reasoning_chain'].append(
                        f"[Sensory] High risk detected ({sensory_features.overall_risk:.2f})"
                    )
            except Exception as e:
                result['sensory_features'] = {'error': str(e)}
        else:
            result['sensory_features'] = None

        self.total_predictions += 1

        # ========== MONITORING (P4.60-65) ==========
        try:
            # P4.61: Metrics
            self.metrics.increment('brain_predictions_total')
            self.metrics.observe_histogram('brain_prediction_latency_ms', predict_elapsed_ms)
            self.metrics.set_gauge('brain_confidence', result['prediction']['confidence'])
            self.metrics.set_gauge('brain_active_subsystems',
                                   len([s for s in self.registry.list_active()]))

            # P4.62: Audit trail
            loop_ctx = getattr(self.cognitive_loop, '_last_context', None) if self.cognitive_loop else None
            self.audit_log.record_from_prediction(task, result, predict_elapsed_ms, loop_ctx)

            # P4.65: Heatmap
            gates = result.get('brain_state', {}).get('gates')
            if gates:
                self.activity_heatmap.record_activation(
                    gates,
                    task_type=result['prediction'].get('task_type', 'unknown'),
                    extra={
                        'confidence': result['prediction'].get('confidence'),
                        'pipeline_mode': result['latency'].get('pipeline_mode'),
                    }
                )
        except Exception as e:
            logger.debug(f"Monitoring recording failed (non-fatal): {e}")

        return result

    def submit_feedback(
        self,
        task: str,
        prediction: Dict,
        actual_action: Optional[str] = None,
        success: bool = True,
        user_rating: Optional[float] = None,
        execution_time_ms: Optional[float] = None
    ):
        """
        Submit feedback for a prediction

        Args:
            task: Original task
            prediction: Prediction dict from predict()
            actual_action: What action was actually taken (None = same as predicted)
            success: Whether the action was successful
            user_rating: User satisfaction rating (0-1)
            execution_time_ms: How long the action took
        """
        # Get brain gates from prediction
        gates = prediction['brain_state']['gates']
        if gates is None:
            print("Warning: No brain gates available for learning")
            return

        gates = np.array(gates)

        # Determine correct action
        if actual_action is None:
            actual_action = prediction['prediction']['primary_action']

        # Create feedback entry
        feedback = FeedbackEntry(
            timestamp=datetime.now().isoformat(),
            task=task,
            predicted_action=prediction['prediction']['primary_action'],
            predicted_weight=prediction['prediction']['primary_weight'],
            actual_action=actual_action,
            success=success,
            user_rating=user_rating,
            brain_gates=gates.tolist(),
            execution_time_ms=execution_time_ms
        )

        # Save to buffer
        self.feedback_buffer.append(feedback)
        self.total_feedback += 1

        # Continuous learning - CLOSED FEEDBACK LOOP
        # Propagate learning across ALL layers, not just Layer 3
        if self.enable_continuous_learning:
            # Determine feedback strength based on multiple signals
            feedback_strength = 1.0
            if user_rating is not None:
                feedback_strength *= user_rating
            if not success:
                feedback_strength *= 0.5

            # 1. Layer 3: Update routing matrix (existing)
            self.planner.layer3.multi_target_router.update_routing_matrix(
                gates=gates,
                target_intervention=actual_action,
                feedback_strength=feedback_strength
            )

            # 2. Neuromodulation: Adjust neurotransmitters based on outcome
            if self.planner.enable_neuromodulation and self.planner.neuromodulation:
                try:
                    levels = self.planner.neuromodulation.levels
                    if success:
                        # Success → dopamine burst (reward signal)
                        levels.dopamine = min(1.0, levels.dopamine + 0.1 * feedback_strength)
                        # Success → serotonin boost (satisfaction)
                        levels.serotonin = min(1.0, levels.serotonin + 0.05 * feedback_strength)
                    else:
                        # Failure → dopamine dip (prediction error)
                        levels.dopamine = max(0.0, levels.dopamine - 0.1 * feedback_strength)
                        # Failure → norepinephrine surge (alertness)
                        levels.norepinephrine = min(1.0, levels.norepinephrine + 0.1 * feedback_strength)
                    logger.debug(f"Neuromod feedback applied: DA={levels.dopamine:.2f} NE={levels.norepinephrine:.2f} 5HT={levels.serotonin:.2f}")
                except Exception as e:
                    logger.error(f"Neuromodulation feedback failed: {e}")

            # 3. Memory: Update outcome for most recent matching task
            if self.planner.enable_memory and self.planner.memory:
                try:
                    outcome = 'success' if success else 'failure'
                    # Update working memory entry outcome
                    for entry in reversed(self.planner.memory.working.buffer):
                        if entry.task == task:
                            entry.outcome = outcome
                            break

                    # Consolidate to episodic memory with full context
                    self.planner.memory.consolidate_to_episodic(
                        task=task,
                        task_type=prediction.get('prediction', {}).get('task_type', 'unknown'),
                        decision=actual_action,
                        confidence=prediction.get('prediction', {}).get('confidence', 0.5),
                        outcome=outcome,
                        brain_gates=gates,
                        layer1_features={
                            'complexity': prediction.get('prediction', {}).get('complexity', 0.5),
                            'urgency': prediction.get('prediction', {}).get('urgency', 0.5),
                        },
                        layer2_sequence=prediction.get('reasoning_chain', []),
                        reasoning_chain=prediction.get('reasoning_chain', [])
                    )
                    logger.debug(f"Memory feedback applied: {outcome} for '{task[:50]}...'")
                except Exception as e:
                    logger.error(f"Memory feedback failed: {e}")

            # 4. Meta-learning: Update learning parameters from feedback
            if self.planner.enable_meta_learning and self.planner.meta_learner:
                try:
                    self.planner.meta_learner.update_from_feedback(
                        task_type=prediction.get('prediction', {}).get('task_type', 'unknown'),
                        success=success,
                        confidence=prediction.get('prediction', {}).get('confidence', 0.5)
                    )
                    logger.debug("Meta-learning feedback applied")
                except Exception as e:
                    logger.error(f"Meta-learning feedback failed: {e}")

            # 5. Layer 2: Adjust gate temperature based on feedback accuracy
            if hasattr(self.planner.layer2, 'provide_feedback'):
                try:
                    self.planner.layer2.provide_feedback(
                        task=task,
                        success=success,
                        user_rating=user_rating
                    )
                    logger.debug("Layer 2 gate temperature feedback applied")
                except Exception as e:
                    logger.error(f"Layer 2 feedback failed: {e}")

            # 6. Emotional system: learn emotional associations from outcome
            if self.cognitive_loop:
                try:
                    self.cognitive_loop.learn_from_feedback(
                        task=task,
                        success=success,
                        confidence=prediction.get('prediction', {}).get('confidence', 0.5)
                    )
                    logger.debug("Emotional system feedback applied")
                except Exception as e:
                    logger.error(f"Emotional system feedback failed: {e}")

        # Log performance
        self.performance_log.append({
            'timestamp': datetime.now().isoformat(),
            'predicted': prediction['prediction']['primary_action'],
            'actual': actual_action,
            'success': success,
            'rating': user_rating,
            'confidence': prediction['prediction']['confidence']
        })

        # Save feedback periodically (every 10)
        if len(self.feedback_buffer) >= 10:
            self._save_feedback_batch()

    def apply_puzzle_learning(
        self,
        transfer_learner: 'PuzzleTransferLearner',
        verbose: bool = True
    ) -> Dict:
        """
        Apply transfer learning from puzzle training to production routing matrix

        This method accepts a PuzzleTransferLearner that has accumulated patterns
        from puzzle training episodes, extracts the learned intervention weights,
        and applies them to the production routing matrix.

        Args:
            transfer_learner: PuzzleTransferLearner instance with accumulated patterns
            verbose: Whether to print transfer details

        Returns:
            Dictionary with transfer results:
                - transfer_applied: Whether transfer was successful
                - patterns_transferred: Number of puzzle patterns used
                - matrix_changes: List of matrix adjustments made
                - avg_efficiency: Average puzzle efficiency transferred
        """
        if not transfer_learner.should_transfer():
            if verbose:
                print(f"[TRANSFER] Not enough patterns ({len(transfer_learner.patterns)}/{transfer_learner.min_episodes})")
            return {
                'transfer_applied': False,
                'patterns_transferred': 0,
                'reason': 'Insufficient patterns'
            }

        # Get current routing matrix from decision router
        current_matrix = self.planner.layer3.multi_target_router.routing_matrix.copy()

        if verbose:
            print(f"\n{'='*70}")
            print(f"PUZZLE TO PRODUCTION TRANSFER LEARNING")
            print(f"{'='*70}")
            print(f"Patterns accumulated: {len(transfer_learner.patterns)}")
            print(f"Current matrix shape: {current_matrix.shape}")
            print(f"Transfer learning rate: {transfer_learner.transfer_lr}")

        # Apply transfer learning
        updated_matrix, transfer_info = transfer_learner.transfer_to_matrix(
            current_matrix=current_matrix,
            matrix_shape=current_matrix.shape
        )

        # Update the production routing matrix
        self.planner.layer3.multi_target_router.routing_matrix = updated_matrix

        if verbose:
            print(f"\n[TRANSFER COMPLETE]")
            print(f"  Matrix changes applied: {len(transfer_info['matrix_changes'])}")

            if transfer_info['matrix_changes']:
                print(f"\n[MATRIX ADJUSTMENTS]")
                for change in transfer_info['matrix_changes']:
                    print(f"  - Phase '{change['phase']}': {change['intervention']} column "
                          f"adjusted by {change['adjustment']:+.6f}")

            # Show statistics
            stats = transfer_learner.get_statistics()
            print(f"\n[TRANSFER STATISTICS]")
            print(f"  Total transfers: {stats['total_transfers']}")
            print(f"  Matrix updates: {stats['matrix_updates_applied']}")
            print(f"  Suggest increases: {stats['suggest_increases']}")
            print(f"  Retry increases: {stats['retry_increases']}")
            print(f"  Wait increases: {stats['wait_increases']}")
            print(f"  Avg efficiency: {stats['avg_efficiency']:.3f}")
            print(f"  Avg confidence gain: {stats['avg_confidence_gain']:+.3f}")

        # Save updated matrix as new version
        version_name = f"puzzle_transfer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.save_matrix(
            version_name=version_name,
            notes=f"Applied puzzle transfer learning: {len(transfer_learner.patterns)} patterns, "
                  f"avg_efficiency={stats['avg_efficiency']:.3f}"
        )

        if verbose:
            print(f"\n[SAVED] Updated matrix as version: {version_name}")
            print(f"{'='*70}\n")

        return transfer_info

    def _save_feedback_batch(self):
        """Save accumulated feedback to disk"""
        if not self.feedback_buffer:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        feedback_path = self.feedback_dir / f"feedback_{timestamp}.json"

        try:
            with open(feedback_path, 'w') as f:
                json.dump([asdict(fb) for fb in self.feedback_buffer], f, indent=2)
            logger.info(f"Saved {len(self.feedback_buffer)} feedback entries to {feedback_path}")
            self.feedback_buffer.clear()
        except (IOError, OSError) as e:
            logger.error(f"Failed to save feedback batch to {feedback_path}: {e}")

    def save_matrix(self, version_name: Optional[str] = None, notes: str = ""):
        """
        Save current routing matrix as new version

        Args:
            version_name: Name for this version (auto-generated if None)
            notes: Description of this version
        """
        if version_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            version_name = f"v{timestamp}"

        # Get current matrix
        matrix = self.planner.layer3.multi_target_router.get_routing_matrix()

        # Compute statistics
        accuracy = self._compute_recent_accuracy()
        avg_confidence = self._compute_avg_confidence()

        # Save matrix
        matrix_path = self.matrix_dir / f"routing_matrix_{version_name}.npy"
        np.save(matrix_path, matrix)

        # Save metadata
        meta = MatrixVersion(
            version=version_name,
            timestamp=datetime.now().isoformat(),
            accuracy=accuracy,
            num_predictions=self.total_predictions,
            avg_confidence=avg_confidence,
            notes=notes
        )

        meta_path = matrix_path.with_suffix('.json')
        try:
            with open(meta_path, 'w') as f:
                json.dump(asdict(meta), f, indent=2)
        except (IOError, OSError) as e:
            logger.error(f"Failed to save matrix metadata to {meta_path}: {e}")

        logger.info(f"Saved matrix version: {version_name}")
        print(f"  Accuracy: {accuracy:.1%}")
        print(f"  Avg Confidence: {avg_confidence:.3f}")
        print(f"  Total Predictions: {self.total_predictions}")

        return version_name

    def _compute_recent_accuracy(self, window: int = 100) -> float:
        """Compute accuracy over recent predictions"""
        if not self.performance_log:
            return 0.0

        recent = self.performance_log[-window:]
        correct = sum(1 for entry in recent if entry['predicted'] == entry['actual'] and entry['success'])
        return correct / len(recent)

    def _compute_avg_confidence(self, window: int = 100) -> float:
        """Compute average confidence over recent predictions"""
        if not self.performance_log:
            return 0.0

        recent = self.performance_log[-window:]
        return np.mean([entry['confidence'] for entry in recent])

    def get_statistics(self) -> Dict:
        """Get production statistics"""
        return {
            'total_predictions': self.total_predictions,
            'total_feedback': self.total_feedback,
            'current_matrix_version': self.current_version,
            'continuous_learning_enabled': self.enable_continuous_learning,
            'learning_rate': self.learning_rate,
            'recent_accuracy': self._compute_recent_accuracy(),
            'recent_avg_confidence': self._compute_avg_confidence(),
            'feedback_buffer_size': len(self.feedback_buffer)
        }

    def list_available_matrices(self) -> List[Dict]:
        """List all available matrix versions"""
        matrix_files = list(self.matrix_dir.glob("routing_matrix_v*.npy"))
        versions = []

        for matrix_path in sorted(matrix_files, key=lambda p: p.stat().st_mtime, reverse=True):
            version = matrix_path.stem.replace("routing_matrix_", "")

            meta_path = matrix_path.with_suffix('.json')
            if meta_path.exists():
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
            else:
                meta = {
                    'version': version,
                    'timestamp': 'unknown',
                    'accuracy': 0.0,
                    'num_predictions': 0,
                    'avg_confidence': 0.0,
                    'notes': ''
                }

            versions.append(meta)

        return versions


if __name__ == "__main__":
    print("=" * 70)
    print("PRODUCTION PLANNER DEMO")
    print("=" * 70)
    print()

    # Initialize production planner
    session_log_dir = os.environ.get(
        'SESSION_LOG_DIR',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'logs', 'sessions')
    )
    planner = ProductionPlanner(
        session_log_dir=session_log_dir,
        matrix_dir="production/trained_matrices",
        feedback_dir="production/feedback",
        enable_continuous_learning=True,
        learning_rate=0.005
    )

    print()
    print("=" * 70)
    print("MAKING PREDICTIONS")
    print("=" * 70)
    print()

    # Test tasks
    test_tasks = [
        "Deploy with Docker urgently",
        "Routine git commit and push",
        "Critical database failure"
    ]

    for task in test_tasks:
        print(f"Task: \"{task}\"")
        print("-" * 70)

        # Make prediction
        result = planner.predict(task)

        # Display
        pred = result['prediction']
        print(f"  Primary:    {pred['primary_action']} ({pred['primary_weight']:.1%})")
        print(f"  Confidence: {pred['confidence']:.1%}")
        print(f"  Mode:       {pred['processing_mode']}")
        print(f"  Reasoning:  {pred['primary_reasoning']}")

        print(f"\n  Alternatives:")
        for alt in pred['alternatives']:
            print(f"    {alt['action']:12s} {alt['weight']:.1%}")

        # Simulate feedback
        success = np.random.rand() > 0.3  # 70% success rate
        user_rating = np.random.uniform(0.6, 1.0) if success else np.random.uniform(0.2, 0.6)

        planner.submit_feedback(
            task=task,
            prediction=result,
            success=success,
            user_rating=user_rating
        )

        print(f"\n  Feedback: Success={success}, Rating={user_rating:.2f}")
        print()

    # Statistics
    print("=" * 70)
    print("STATISTICS")
    print("=" * 70)
    print()

    stats = planner.get_statistics()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")

    print()

    # Save matrix
    print("=" * 70)
    print("SAVING MATRIX")
    print("=" * 70)
    print()

    version = planner.save_matrix(notes="Demo production matrix with feedback")

    # List available matrices
    print()
    print("Available matrix versions:")
    for meta in planner.list_available_matrices():
        print(f"  {meta['version']}: Accuracy={meta['accuracy']:.1%}, Predictions={meta['num_predictions']}")

    print()
    print("=" * 70)
    print("PRODUCTION DEMO COMPLETE")
    print("=" * 70)

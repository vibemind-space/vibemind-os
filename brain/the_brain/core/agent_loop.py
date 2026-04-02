"""
Agent Loop - The Autonomous Will of Tahlamus (V2 Phase 3: P3.31-33)

This is the permanent background loop that gives Tahlamus agency.
Instead of only responding to /predict requests, Tahlamus now:
1. Continuously perceives its environment (sensor events)
2. Generates and prioritizes its own goals
3. Plans and executes actions
4. Observes outcomes and learns
5. Dreams/consolidates when idle

The loop integrates with:
- CognitiveLoop: For thinking/reasoning about tasks
- EventBus: For receiving sensor events and publishing state changes
- GoalGraph + AutonomousGoalGenerator: For goal management
- HomeostaticRegulation: For drive-based behavior (sleep, curiosity)
- MemoryManager: For learning from experience
- BrainSnapshot: For state persistence

Architecture:
    AgentLoop (this file)
    ├── AgentStateMachine (FSM with clean transitions)
    ├── InterruptHandler (user requests take priority)
    ├── TaskPriorityQueue (urgency × importance ranking)
    └── AgentLoopConfig (all tunable parameters)
"""

import logging
import time
import threading
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

logger = logging.getLogger('brain.agent_loop')


# ─── Agent States ────────────────────────────────────────────────────────

class AgentState(Enum):
    """States for the Agent State Machine (P3.32)."""
    IDLE = "idle"
    PERCEIVING = "perceiving"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING_APPROVAL = "waiting_approval"
    OBSERVING = "observing"
    LEARNING = "learning"
    DREAMING = "dreaming"
    STOPPED = "stopped"


# Valid state transitions
VALID_TRANSITIONS = {
    AgentState.STOPPED: {AgentState.IDLE},
    AgentState.IDLE: {AgentState.PERCEIVING, AgentState.DREAMING, AgentState.STOPPED},
    AgentState.PERCEIVING: {AgentState.THINKING, AgentState.IDLE, AgentState.STOPPED},
    AgentState.THINKING: {AgentState.ACTING, AgentState.IDLE, AgentState.STOPPED},
    AgentState.ACTING: {AgentState.WAITING_APPROVAL, AgentState.OBSERVING, AgentState.STOPPED},
    AgentState.WAITING_APPROVAL: {AgentState.ACTING, AgentState.IDLE, AgentState.STOPPED},
    AgentState.OBSERVING: {AgentState.LEARNING, AgentState.THINKING, AgentState.STOPPED},
    AgentState.LEARNING: {AgentState.IDLE, AgentState.PERCEIVING, AgentState.STOPPED},
    AgentState.DREAMING: {AgentState.IDLE, AgentState.PERCEIVING, AgentState.STOPPED},
}


# ─── Priority System ─────────────────────────────────────────────────────

class TaskPriority(Enum):
    """Priority levels for agent tasks (P3.33)."""
    USER_REQUEST = 0      # P0: User-initiated (via /predict or Clawdbot)
    ALARM = 1             # P1: System alarm (service down, critical error)
    SELF_INITIATED = 2    # P2: Self-generated goals (curiosity, proactive)
    BACKGROUND = 3        # P3: Background maintenance (consolidation, health)


@dataclass
class AgentTask:
    """A task in the agent's priority queue."""
    task_id: str
    description: str
    priority: TaskPriority
    source: str  # 'user', 'sensor', 'goal', 'schedule', 'curiosity'
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For urgency scoring
    urgency: float = 0.5       # 0-1, sensor-driven
    importance: float = 0.5    # 0-1, goal-alignment
    estimated_effort: float = 0.5  # 0-1, from experience

    def score(self) -> float:
        """Combined priority score (lower = higher priority)."""
        base = self.priority.value * 10.0
        urgency_bonus = (1.0 - self.urgency) * 3.0
        importance_bonus = (1.0 - self.importance) * 2.0
        age_bonus = min(5.0, (time.time() - self.created_at) / 300.0)  # Older tasks get slight boost
        return base + urgency_bonus + importance_bonus - age_bonus

    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'description': self.description,
            'priority': self.priority.name,
            'source': self.source,
            'urgency': self.urgency,
            'importance': self.importance,
            'score': round(self.score(), 3),
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


# ─── Configuration ────────────────────────────────────────────────────────

@dataclass
class AgentLoopConfig:
    """Configuration for the Agent Loop."""
    # Tick intervals (seconds)
    active_tick_interval: float = 1.0      # When there are pending tasks/events
    idle_tick_interval: float = 30.0       # When nothing is happening
    dream_tick_interval: float = 60.0      # During dream/consolidation mode

    # Idle behavior
    idle_threshold_seconds: float = 300.0  # 5 min idle => consider dreaming
    dream_duration_seconds: float = 120.0  # 2 min of dream mode
    dream_training_epochs: int = 3         # Radial sleep training epochs per dream

    # Homeostatic thresholds
    sleep_pressure_threshold: float = 0.7  # Force dream mode above this
    low_energy_threshold: float = 0.2      # Reduce activity below this

    # Task queue
    max_pending_tasks: int = 50
    max_concurrent_actions: int = 1  # Sequential for now (safety)
    task_timeout_seconds: float = 300.0  # 5 min max per task

    # Interrupt behavior
    interrupt_grace_period: float = 2.0  # Seconds to wait before interrupting

    # Safety
    max_autonomous_actions_per_hour: int = 50
    require_approval_above_risk: str = "high"  # 'low', 'medium', 'high', 'critical'

    # Loop control
    max_consecutive_errors: int = 5  # Stop after this many errors in a row
    error_cooldown_seconds: float = 30.0

    @classmethod
    def from_yaml(cls, config: Dict) -> 'AgentLoopConfig':
        """Create config from YAML dict."""
        section = config.get('agent_loop', {})
        return cls(
            active_tick_interval=section.get('active_tick_interval', cls.active_tick_interval),
            idle_tick_interval=section.get('idle_tick_interval', cls.idle_tick_interval),
            dream_tick_interval=section.get('dream_tick_interval', cls.dream_tick_interval),
            idle_threshold_seconds=section.get('idle_threshold_seconds', cls.idle_threshold_seconds),
            dream_duration_seconds=section.get('dream_duration_seconds', cls.dream_duration_seconds),
            sleep_pressure_threshold=section.get('sleep_pressure_threshold', cls.sleep_pressure_threshold),
            low_energy_threshold=section.get('low_energy_threshold', cls.low_energy_threshold),
            max_pending_tasks=section.get('max_pending_tasks', cls.max_pending_tasks),
            max_concurrent_actions=section.get('max_concurrent_actions', cls.max_concurrent_actions),
            task_timeout_seconds=section.get('task_timeout_seconds', cls.task_timeout_seconds),
            interrupt_grace_period=section.get('interrupt_grace_period', cls.interrupt_grace_period),
            max_autonomous_actions_per_hour=section.get('max_autonomous_actions_per_hour', cls.max_autonomous_actions_per_hour),
            require_approval_above_risk=section.get('require_approval_above_risk', cls.require_approval_above_risk),
            max_consecutive_errors=section.get('max_consecutive_errors', cls.max_consecutive_errors),
            error_cooldown_seconds=section.get('error_cooldown_seconds', cls.error_cooldown_seconds),
            dream_training_epochs=section.get('dream_training_epochs', cls.dream_training_epochs),
        )


# ─── Agent State Machine (P3.32) ─────────────────────────────────────────

class AgentStateMachine:
    """
    Finite State Machine for the Agent Loop.

    Enforces valid state transitions and tracks state history.
    Exposed via get_loop_state() for dashboard visibility.
    """

    def __init__(self):
        self._state: AgentState = AgentState.STOPPED
        self._state_entered_at: float = time.time()
        self._state_history: deque = deque(maxlen=100)
        self._lock = threading.Lock()
        self._transition_count: int = 0

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def time_in_state(self) -> float:
        return time.time() - self._state_entered_at

    def transition(self, new_state: AgentState) -> bool:
        """
        Attempt state transition. Returns True if valid, False otherwise.
        Thread-safe.
        """
        with self._lock:
            if new_state == self._state:
                return True  # Already in state

            valid_next = VALID_TRANSITIONS.get(self._state, set())
            if new_state not in valid_next:
                logger.warning(
                    f"Invalid state transition: {self._state.value} => {new_state.value}. "
                    f"Valid: {[s.value for s in valid_next]}"
                )
                return False

            old_state = self._state
            self._state_history.append({
                'from': old_state.value,
                'to': new_state.value,
                'timestamp': time.time(),
                'duration_in_prev': self.time_in_state,
            })
            self._state = new_state
            self._state_entered_at = time.time()
            self._transition_count += 1

            logger.debug(f"Agent state: {old_state.value} => {new_state.value}")
            return True

    def force_state(self, state: AgentState):
        """Force state without transition validation (for recovery/init)."""
        with self._lock:
            old = self._state
            self._state = state
            self._state_entered_at = time.time()
            logger.info(f"Agent state forced: {old.value} => {state.value}")

    def to_dict(self) -> Dict[str, Any]:
        """Get state machine info for dashboard."""
        return {
            'current_state': self._state.value,
            'time_in_state_seconds': round(self.time_in_state, 2),
            'transition_count': self._transition_count,
            'recent_transitions': list(self._state_history)[-10:],
        }


# ─── Interrupt Handler (P3.33) ────────────────────────────────────────────

class InterruptHandler:
    """
    Handles user interrupts and priority escalation.

    User requests (via /predict or Clawdbot) interrupt the current loop
    immediately. Alarms from sensors can also interrupt lower-priority work.
    """

    def __init__(self, config: AgentLoopConfig):
        self._config = config
        self._interrupt_queue: deque = deque(maxlen=20)
        self._lock = threading.Lock()
        self._interrupt_event = threading.Event()

    def submit_interrupt(self, task: AgentTask):
        """Submit a high-priority interrupt task."""
        with self._lock:
            self._interrupt_queue.append(task)
            self._interrupt_event.set()
            logger.info(
                f"Interrupt submitted: [{task.priority.name}] {task.description[:80]}"
            )

    def has_interrupt(self) -> bool:
        """Check if there are pending interrupts."""
        return len(self._interrupt_queue) > 0

    def get_interrupt(self) -> Optional[AgentTask]:
        """Get the highest-priority interrupt, or None."""
        with self._lock:
            if not self._interrupt_queue:
                self._interrupt_event.clear()
                return None
            # Sort by priority (lower value = higher priority)
            sorted_interrupts = sorted(self._interrupt_queue, key=lambda t: t.score())
            task = sorted_interrupts[0]
            self._interrupt_queue.remove(task)
            if not self._interrupt_queue:
                self._interrupt_event.clear()
            return task

    def wait_for_interrupt(self, timeout: float = None) -> bool:
        """Block until an interrupt arrives or timeout."""
        return self._interrupt_event.wait(timeout=timeout)

    def clear(self):
        """Clear all pending interrupts."""
        with self._lock:
            self._interrupt_queue.clear()
            self._interrupt_event.clear()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'pending_interrupts': len(self._interrupt_queue),
            'interrupts': [t.to_dict() for t in self._interrupt_queue],
        }


# ─── Autonomy Budget Tracker ──────────────────────────────────────────────

class AutonomyBudget:
    """
    Tracks and limits autonomous actions per time period (P3.44 preview).
    Prevents runaway autonomous behavior.
    """

    def __init__(self, max_per_hour: int = 50):
        self._max_per_hour = max_per_hour
        self._action_timestamps: deque = deque(maxlen=max_per_hour * 2)
        self._lock = threading.Lock()

    def can_act(self) -> bool:
        """Check if we're within budget."""
        with self._lock:
            self._prune_old()
            return len(self._action_timestamps) < self._max_per_hour

    def record_action(self):
        """Record an autonomous action."""
        with self._lock:
            self._action_timestamps.append(time.time())

    def remaining(self) -> int:
        """How many autonomous actions remain in the current window."""
        with self._lock:
            self._prune_old()
            return max(0, self._max_per_hour - len(self._action_timestamps))

    def _prune_old(self):
        """Remove actions older than 1 hour."""
        cutoff = time.time() - 3600
        while self._action_timestamps and self._action_timestamps[0] < cutoff:
            self._action_timestamps.popleft()

    def to_dict(self) -> Dict[str, Any]:
        self._prune_old()
        return {
            'max_per_hour': self._max_per_hour,
            'used_this_hour': len(self._action_timestamps),
            'remaining': self.remaining(),
        }


# ─── Agent Loop (P3.31) ──────────────────────────────────────────────────

class AgentLoop:
    """
    The autonomous agent loop that gives Tahlamus continuous agency.

    Main cycle:
        while running:
            1. Check for interrupts (user requests)
            2. Collect sensor events
            3. Generate/update goals
            4. Pick highest-priority task
            5. Think (cognitive loop)
            6. Act (via bridges - when available)
            7. Observe outcome
            8. Learn from result
            9. If idle long enough: dream/consolidate

    Integration:
        - Set `planner` to wire into ProductionPlanner.predict()
        - Set `event_bus` for sensor event reception
        - Set `homeostatic` for drive-based behavior
        - Set `goal_generator` for autonomous goal creation

    All integrations are optional - the loop runs in a degraded
    mode if subsystems aren't available.
    """

    def __init__(self, config: Optional[AgentLoopConfig] = None):
        self.config = config or AgentLoopConfig()
        self.fsm = AgentStateMachine()
        self.interrupt_handler = InterruptHandler(self.config)
        self.autonomy_budget = AutonomyBudget(self.config.max_autonomous_actions_per_hour)

        # Task queue (sorted by score on pop)
        self._task_queue: List[AgentTask] = []
        self._task_queue_lock = threading.Lock()
        self._task_counter: int = 0

        # Integration points (set by ProductionPlanner or UnifiedBrainService)
        self.planner = None           # ProductionPlanner
        self.event_bus = None         # EventBus
        self.homeostatic = None       # HomeostaticRegulation
        self.goal_generator = None    # AutonomousGoalGenerator
        self.memory = None            # MemoryManager
        self.cognitive_loop = None    # CognitiveLoop
        self.motivation = None        # MotivationSystem (P3.34-36)
        self.neuromodulation = None   # NeuromodulationSystem (for motivation drives)
        self.goal_manager = None      # GoalManager (P3.37-40)
        self.proactive = None         # ProactiveBehavior (P3.41-43)
        self.safety = None             # SafetyRegulation (P3.44-45)

        # Phase 1: Sensor Systems (P1.3-6, P1.9-15)
        self.system_vitals_sensor = None    # SystemVitalsSensor (P1.3)
        self.file_system_sensor = None      # FileSystemSensor (P1.4)
        self.process_sensor = None          # ProcessSensor (P1.5)
        self.log_sensor = None              # LogSensor (P1.6)
        self.git_activity_sensor = None     # GitActivitySensor (P1.9)
        self.sensor_registry = None         # SensorRegistry (P1.10)
        self.sensor_fusion = None           # SensorFusion (P1.11)
        self.perception_pipeline = None     # PerceptionPipeline (P1.12)
        self.attention_sampling = None      # AttentionDrivenSampling (P1.13)
        self.novelty_filter = None          # NoveltyFilter (P1.14)
        self.sensory_memory = None          # SensoryMemory (P1.15)

        # Phase 2: Action Systems (P2.18, P2.25-30)
        self.approval_gate = None           # ApprovalGate (P2.18)
        self.action_planner = None          # ActionPlanner (P2.25)
        self.action_validator = None        # ActionValidator (P2.26)
        self.action_monitor = None          # ActionMonitor (P2.27)
        self.action_outcome_detector = None # ActionOutcomeDetector (P2.28)
        self.action_replay_memory = None    # ActionReplayMemory (P2.29)
        self.action_learning = None         # ActionLearning (P2.30)

        # Phase 4: Language & Communication (P4.46-60)
        self.language_center = None    # BrainLanguageCenter (P4.46-48)
        self.personality = None        # PersonalityModel (P4.52)
        self.emotional_expression = None  # EmotionalExpression (P4.53)
        self.communication_style = None   # CommunicationStyle (P4.54)
        self.status_updater = None     # StatusUpdater (P4.55)
        self.explanation_system = None # ExplanationSystem (P4.56)
        self.suggestion_engine = None  # SuggestionEngine (P4.57)
        self.dialogue_manager = None   # DialogueManager (P4.58-60)

        # Phase 5: Learning Systems (P5.61-75)
        self.experience_replay = None   # ExperienceReplaySystem (P5.61)
        self.outcome_learning = None    # AutomaticOutcomeLearning (P5.62)
        self.transfer_learning = None   # TransferLearning (P5.63)
        self.skill_library = None       # SkillLibrary (P5.64)
        self.skill_composition = None   # SkillComposition (P5.65)
        self.skill_refinement = None    # SkillRefinement (P5.66)
        self.world_model = None         # WorldModel (P5.67)
        self.causal_world_model = None  # CausalWorldModel (P5.68)
        self.predictive_world_model = None  # PredictiveWorldModel (P5.69)
        self.self_awareness = None      # SelfAwarenessModule (P5.70)
        self.learning_diagnosis = None  # LearningDiagnosis (P5.71)
        self.knowledge_gaps = None      # KnowledgeGapDetection (P5.72)
        self.demonstration_learning = None  # LearningFromDemonstration (P5.73)
        self.feedback_interpretation = None  # FeedbackInterpretation (P5.74)
        self.collaborative_learning = None  # CollaborativeLearning (P5.75)

        # Phase 6: Identity Systems (P6.76-85)
        self.self_model = None              # SelfModel (P6.76)
        self.autobiographic_memory = None   # AutobiographicMemory (P6.77)
        self.value_system = None            # ValueSystem (P6.78)
        self.emotional_memory = None        # EmotionalMemorySystem (P6.79)
        self.mood_system = None             # MoodSystem (P6.80)
        self.stress_response = None         # StressResponse (P6.81)
        self.user_model = None              # UserModel (P6.82)
        self.trust_model = None             # TrustModel (P6.83)
        self.collaboration_patterns = None  # CollaborationPatterns (P6.84)
        self.relationship_history = None    # RelationshipHistory (P6.85)

        # Phase 6B: Deep Identity Systems (research-enhanced)
        self.core_affect_space = None         # CoreAffectSpace (valence x arousal primitive)
        self.agency_model = None              # AgencyModel (sense of agency comparator)
        self.identity_narrative = None        # IdentityNarrative (coherent self-story)
        self.moral_conscience = None          # MoralConscience (moral emotions + value conflict)
        self.existential_purpose = None       # ExistentialPurpose (meaning + purpose tracking)
        self.social_identity = None           # SocialIdentity (attachment + belonging)
        self.wisdom_module = None             # WisdomModule (cognition + affect + reflection)
        self.consciousness_gateway = None     # ConsciousnessGateway (GW broadcast + phi)

        # Moltbook System — Decentralized Knowledge & Thinking
        # Core Data Layer
        self.moltbook_store = None            # MoltbookStore (persistent knowledge store)
        self.semantic_index = None            # SemanticIndex (vector-based search)
        self.moltbook_graph = None            # MoltbookGraph (knowledge linkage)
        # Thinking Layer
        self.thought_stream = None            # ThoughtStream (continuous background thoughts)
        self.thought_buffer = None            # ThoughtBuffer (recent thoughts ring buffer)
        self.associative_thinking = None      # AssociativeThinking (semantic chain)
        self.meta_thinking = None             # MetaThinking (thinking about thinking)
        # Retrieval Layer
        self.markov_knowledge_chain = None    # MarkovKnowledgeChain (topic transitions)
        self.speculative_retrieval = None     # SpeculativeRetrieval (pre-fetch)
        self.context_predictor = None         # ContextPredictor (next-state prediction)
        self.relevance_scorer = None          # RelevanceScorer (real-time scoring)
        # Thinker-Talker Layer
        self.internal_monologue = None        # InternalMonologue (MIRROR-style 3-thread)
        self.cognitive_controller = None      # CognitiveController (thought synthesis)
        self.talker_module = None             # TalkerModule (thought -> human speech)
        self.think_talk_orchestrator = None   # ThinkTalkOrchestrator (main pipeline)
        # Realtime Response
        self.realtime_response_engine = None  # RealtimeResponseEngine (fast pipeline)
        self.input_analyzer = None            # InputAnalyzer (intent + complexity)
        # Learning
        self.moltbook_learner = None          # MoltbookLearner (feedback -> entry update)
        self.markov_learner = None            # MarkovLearner (transition matrix update)
        # Agent Ecosystem
        self.moltbook_feeder = None           # MoltbookFeeder (agent -> moltbook interface)
        self.evaluation_agent = None          # EvaluationAgent (quality scoring)

        # Phase 7: Resilience Systems (P7.86-92)
        self.graceful_degradation = None    # GracefulDegradationV2 (P7.86)
        self.self_healing = None            # SelfHealing (P7.87)
        self.adversarial_resilience = None  # AdversarialResilience (P7.88)
        self.uncertainty_handling = None    # UncertaintyHandling (P7.89)
        self.context_switching = None       # ContextSwitching (P7.90)
        self.long_running_tasks = None      # LongRunningTaskManager (P7.91)
        self.resource_awareness = None      # ResourceAwareness (P7.92)

        # Phase 8: Ecosystem Intelligence (P8.96-100)
        self.orchestrator_of_orchestrators = None  # OrchestratorOfOrchestrators (P8.96)
        self.synergy_learning = None               # SystemSynergyLearning (P8.97)
        self.knowledge_export = None               # KnowledgeExport (P8.98)
        self.evolutionary_growth = None            # EvolutionaryGrowth (P8.99)
        self.consciousness_evolution = None        # ConsciousnessEvolution (P8.100)

        # Neuroscience Architecture Extensions
        self.cerebellum = None                    # CerebellumModule (Prediction + Timing)
        self.prefrontal_cortex = None             # PrefrontalCortex (WM + Control)
        self.hypothalamus = None                  # HypothalamusModule (Drives + HPA)
        self.default_mode_network = None          # DefaultModeNetwork (Self-ref + Creativity)
        self.insular_cortex = None                # InsularCortex (Salience + Interoception)
        self.superior_colliculus = None            # SuperiorColliculus (Orienting + Multisensory)
        self.entorhinal_cortex = None             # EntorhinalCortex (Grid Cells + Gateway)
        self.nucleus_accumbens = None             # NucleusAccumbens (Reward Gateway)
        self.anterior_cingulate = None            # AnteriorCingulateCortex (Conflict + Effort)

        # Phase D: Tier 1 Brain Structures
        self.amygdala = None                      # AmygdalaComplex (Valence + Threat + Social)
        self.ventral_tegmental_area = None        # VentralTegmentalArea (RPE + Dopamine + Motivation)
        self.locus_coeruleus = None               # LocusCoeruleus (Arousal + Explore/Exploit)
        self.raphe_nuclei = None                  # RapheNuclei (Patience + Mood + 5-HT)
        self.lateral_habenula = None              # LateralHabenula (Anti-reward + Avoidance)
        self.periaqueductal_gray = None           # PeriaqueductalGray (Defense: Fight/Flight/Freeze)

        # Phase E: Tier 2 Brain Structures
        self.claustrum = None                     # Claustrum (Cross-modal Binding + Consciousness)
        self.reticular_formation = None           # ReticularFormation (ARAS + Arousal + Gating)
        self.basal_forebrain = None               # BasalForebrain (ACh + Plasticity + Encoding)
        self.septal_nuclei = None                 # SeptalNuclei (Theta + Gamma + Memory Timing)
        self.inferior_olive = None                # InferiorOlive (Error Signal + Timing + Teaching)
        self.mammillary_bodies = None             # MammillaryBodies (Papez Relay + Spatial Memory)
        self.bnst = None                          # BNST (Sustained Anxiety + Chronic Stress)
        self.parabrachial_nucleus = None          # ParabrachialNucleus (Alarm + Interoceptive)
        self.orbitofrontal_cortex = None          # OrbitofrontalCortex (Value + Decision)

        # Phase F: Tier 3 Brain Structures
        self.substantia_nigra = None              # SubstantiaNigra (SNc DA + SNr GABA + Nigrostriatal)
        self.zona_incerta = None                  # ZonaIncerta (Inhibition + Limbic-Motor + Visceral)
        self.red_nucleus = None                   # RedNucleus (Backup Motor / Rubrospinal)
        self.tuberomammillary_nucleus = None       # TuberomammillaryNucleus (Histamine + Wake)
        self.pedunculopontine_nucleus = None       # PedunculopontineNucleus (Locomotion + REM)
        self.ventral_pallidum = None              # VentralPallidum (Hedonic Hotspot + Liking)
        self.nucleus_tractus_solitarius = None    # NTS (Visceral Relay + Autonomic Reflex)
        self.olfactory_system = None              # OlfactorySystem (Bulb + Piriform Cortex)
        self.fusiform_gyrus = None                # FusiformGyrus (FFA + VWFA)
        self.temporoparietal_junction = None      # TPJ (Theory of Mind + Self-Other)
        self.posterior_parietal_cortex = None      # PPC (Spatial Attention + Reference Frames)
        self.cortical_column = None               # CorticalColumn (Canonical Microcircuit)
        self.pineal_gland = None                  # PinealGland (Melatonin + Circadian)
        self.corpus_callosum = None               # CorpusCallosum (Interhemispheric Transfer)

        # Radial Attention Network (set by ProductionPlanner)
        self.radial_network = None       # RadialAttentionNetwork
        self.seed_encoder = None         # SeedEncoder (task -> 384D)
        self.hebbian = None              # HebbianAttentionUpdate
        self.experience_buffer = None    # ExperienceBuffer (replay)
        self.radial_trainer = None       # RadialSleepTrainer
        self.dual_process = None         # DualProcessRouter
        self._last_radial_output = None  # Cache last forward() result

        # Loop control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_activity_time: float = time.time()
        self._consecutive_errors: int = 0
        self._total_ticks: int = 0
        self._total_tasks_processed: int = 0
        self._total_tasks_succeeded: int = 0
        self._total_tasks_failed: int = 0

        # Current task tracking
        self._current_task: Optional[AgentTask] = None
        self._current_task_start: float = 0.0

        # Dream mode tracking
        self._dream_start: float = 0.0
        self._total_dream_time: float = 0.0

        # Event subscriptions
        self._sensor_events: deque = deque(maxlen=500)

        logger.info("AgentLoop initialized")

    # ─── Task Queue Management ────────────────────────────────────────

    def submit_task(self, description: str, priority: TaskPriority = TaskPriority.SELF_INITIATED,
                    source: str = 'internal', urgency: float = 0.5, importance: float = 0.5,
                    metadata: Optional[Dict] = None) -> str:
        """
        Submit a task to the agent loop.
        Returns task_id.
        """
        self._task_counter += 1
        task = AgentTask(
            task_id=f"task_{self._task_counter}_{int(time.time())}",
            description=description,
            priority=priority,
            source=source,
            urgency=urgency,
            importance=importance,
            metadata=metadata or {},
        )

        if priority == TaskPriority.USER_REQUEST or priority == TaskPriority.ALARM:
            # High-priority: use interrupt handler
            self.interrupt_handler.submit_interrupt(task)
        else:
            # Normal priority: add to queue
            with self._task_queue_lock:
                if len(self._task_queue) < self.config.max_pending_tasks:
                    self._task_queue.append(task)
                else:
                    logger.warning(f"Task queue full ({self.config.max_pending_tasks}), dropping: {description[:60]}")

        return task.task_id

    def submit_user_request(self, description: str, metadata: Optional[Dict] = None) -> str:
        """Convenience: submit a user-initiated task (P0 priority)."""
        return self.submit_task(
            description=description,
            priority=TaskPriority.USER_REQUEST,
            source='user',
            urgency=1.0,
            importance=1.0,
            metadata=metadata,
        )

    def _get_next_task(self) -> Optional[AgentTask]:
        """Get the highest-priority task (interrupts first, then queue)."""
        # Check interrupts first
        interrupt = self.interrupt_handler.get_interrupt()
        if interrupt:
            return interrupt

        # Then regular queue
        with self._task_queue_lock:
            if not self._task_queue:
                return None
            # Sort by score (lower = higher priority)
            self._task_queue.sort(key=lambda t: t.score())
            return self._task_queue.pop(0)

    # ─── Event Handling ───────────────────────────────────────────────

    def _on_sensor_event(self, event):
        """Callback for sensor events from EventBus."""
        self._sensor_events.append(event)
        self._last_activity_time = time.time()

    def _collect_sensor_events(self) -> List[Any]:
        """Drain the sensor event buffer."""
        events = list(self._sensor_events)
        self._sensor_events.clear()
        return events

    def _subscribe_to_events(self):
        """Subscribe to relevant EventBus topics."""
        if self.event_bus:
            try:
                # Subscribe to sensor events (when sensors are implemented)
                self.event_bus.subscribe('sensor.*', self._on_sensor_event)
                # Subscribe to feedback for learning
                self.event_bus.subscribe('feedback.*', self._on_sensor_event)
                # Subscribe to goal events
                self.event_bus.subscribe('goal.*', self._on_sensor_event)
                logger.info("AgentLoop subscribed to EventBus topics")
            except Exception as e:
                logger.warning(f"Failed to subscribe to EventBus: {e}")

    # ─── Loop Control ─────────────────────────────────────────────────

    def start(self):
        """Start the agent loop in a background thread."""
        if self._running:
            logger.warning("AgentLoop already running")
            return

        self._running = True
        self.fsm.force_state(AgentState.IDLE)
        self._subscribe_to_events()
        self._last_activity_time = time.time()

        self._thread = threading.Thread(
            target=self._loop,
            name="AgentLoop",
            daemon=True,
        )
        self._thread.start()
        logger.info("AgentLoop started")

        # Emit startup event
        if self.event_bus:
            try:
                from core.event_bus import BrainEvent, EventPriority
                self.event_bus.publish(BrainEvent(
                    topic='agent.started',
                    data={'timestamp': time.time()},
                    source='agent_loop',
                    priority=EventPriority.NORMAL,
                ))
            except Exception:
                pass

    def stop(self):
        """Stop the agent loop gracefully."""
        if not self._running:
            return

        logger.info("AgentLoop stopping...")
        self._running = False
        self.interrupt_handler._interrupt_event.set()  # Wake up if sleeping

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10.0)

        self.fsm.transition(AgentState.STOPPED)
        logger.info("AgentLoop stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ─── Main Loop ────────────────────────────────────────────────────

    def _loop(self):
        """The main agent loop (runs in background thread)."""
        logger.info("AgentLoop main loop started")

        while self._running:
            try:
                self._total_ticks += 1
                tick_start = time.time()

                # Determine tick interval based on state
                if self.fsm.state == AgentState.DREAMING:
                    tick_interval = self.config.dream_tick_interval
                elif self._has_work():
                    tick_interval = self.config.active_tick_interval
                else:
                    tick_interval = self.config.idle_tick_interval

                # ── Phase 1: Check Interrupts ──
                if self.interrupt_handler.has_interrupt():
                    self._handle_interrupt()
                    continue

                # ── Phase 2: Perceive (collect events) ──
                events = self._collect_sensor_events()
                if events:
                    self.fsm.transition(AgentState.PERCEIVING)
                    self._process_sensor_events(events)
                    self._last_activity_time = time.time()

                # ── Phase 3: Check Homeostatic State ──
                if self._should_dream():
                    self._enter_dream_mode()
                    continue

                # ── Phase 3.5: Goal Management (generate & prioritize goals) ──
                if self.goal_manager and not self._has_work():
                    self._run_goal_management()

                # ── Phase 3.6: Proactive Behavior (generate tasks from signals) ──
                if self.proactive and not self._has_work():
                    self._run_proactive_behavior()

                # ── Phase 3.7: Motivation (generate impulses when idle) ──
                if not self._has_work() and self.motivation:
                    self._generate_motivation_tasks()

                # ── Phase 4: Pick and Execute Task ──
                task = self._get_next_task()
                if task:
                    self._execute_task(task)
                    self._last_activity_time = time.time()
                    self._consecutive_errors = 0
                else:
                    # Nothing to do
                    if self.fsm.state != AgentState.IDLE:
                        self.fsm.transition(AgentState.IDLE)

                # ── Phase 5: Check idle timeout ──
                idle_time = time.time() - self._last_activity_time
                if idle_time > self.config.idle_threshold_seconds:
                    self._enter_dream_mode()
                    continue

                # Sleep until next tick
                elapsed = time.time() - tick_start
                sleep_time = max(0.1, tick_interval - elapsed)

                # Use interrupt event for sleeping (can be woken up)
                self.interrupt_handler.wait_for_interrupt(timeout=sleep_time)

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"AgentLoop tick error ({self._consecutive_errors}): {e}", exc_info=True)

                if self._consecutive_errors >= self.config.max_consecutive_errors:
                    logger.critical(
                        f"AgentLoop: {self._consecutive_errors} consecutive errors, "
                        f"entering cooldown for {self.config.error_cooldown_seconds}s"
                    )
                    time.sleep(self.config.error_cooldown_seconds)
                    self._consecutive_errors = 0

        logger.info("AgentLoop main loop exited")

    # ─── Task Execution ───────────────────────────────────────────────

    def _execute_task(self, task: AgentTask):
        """Execute a single task through the think-act-observe cycle."""
        self._current_task = task
        self._current_task_start = time.time()

        logger.info(f"Executing task [{task.priority.name}]: {task.description[:80]}")

        # ── Safety Check (P3.44-45) ──
        if self.safety and task.priority != TaskPriority.USER_REQUEST:
            try:
                # Determine budget category from task metadata
                category = task.metadata.get('budget_category', 'task_execution')
                result = self.safety.check_and_record(
                    action_description=task.description,
                    category=category,
                    is_user_request=False,
                    file_path=task.metadata.get('file_path'),
                    host=task.metadata.get('host'),
                    estimated_cpu_seconds=task.metadata.get('cpu_seconds'),
                    content=task.metadata.get('content'),
                )
                if not result.approved:
                    if result.verdict.value == 'escalate':
                        logger.warning(
                            f"Safety ESCALATE: {task.description[:60]} — {result.reason}"
                        )
                        # Re-queue as user-request priority for human review
                        task.metadata['safety_escalated'] = True
                        task.metadata['escalation_reason'] = result.reason
                        self.submit_task(
                            description=f"[ESCALATED] {task.description}",
                            priority=TaskPriority.USER_REQUEST,
                            source=task.source,
                            urgency=task.urgency,
                            importance=task.importance,
                            metadata=task.metadata,
                        )
                    else:
                        logger.warning(
                            f"Safety DENIED: {task.description[:60]} — {result.reason}"
                        )
                    self._total_tasks_processed += 1
                    self._total_tasks_failed += 1
                    self._current_task = None
                    return
            except Exception as e:
                logger.debug(f"Safety check failed (allowing task): {e}")

        try:
            # ── Think ──
            self.fsm.transition(AgentState.THINKING)

            # Radial forward: bridge modulation + experience recording
            radial_result = self._radial_forward(task)

            prediction = self._think(task)

            if prediction is None:
                logger.warning(f"No prediction for task: {task.description[:60]}")
                self._total_tasks_failed += 1
                return

            # ── Act ──
            # For now, acting is limited to recording the prediction.
            # Bridge-based execution (Phase 2) will be added when bridges are validated.
            self.fsm.transition(AgentState.OBSERVING)
            outcome = self._observe(task, prediction)

            # Attach radial metadata to outcome for learning
            if radial_result is not None:
                outcome['radial_prediction_errors'] = radial_result['prediction_errors']
                outcome['radial_active'] = True
            else:
                outcome['radial_active'] = False

            # ── Learn ──
            self.fsm.transition(AgentState.LEARNING)
            self._learn(task, prediction, outcome)

            self._total_tasks_processed += 1
            self._total_tasks_succeeded += 1

        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            self._total_tasks_processed += 1
            self._total_tasks_failed += 1

        finally:
            self._current_task = None
            duration = time.time() - self._current_task_start
            logger.debug(f"Task completed in {duration:.2f}s")

            # Record action for autonomy budget (self-initiated only)
            if task.priority != TaskPriority.USER_REQUEST:
                self.autonomy_budget.record_action()
                # Also record in safety regulation budget if available
                if self.safety:
                    try:
                        category = task.metadata.get('budget_category', 'task_execution')
                        self.safety.budget.record_action(category)
                    except Exception:
                        pass

    def radial_tick(self, description: str, metadata: Optional[Dict] = None) -> Optional[Dict]:
        """Lightweight radial forward pass for continuous thinking integration.

        Called by ContinuousThinkingEngine on each think tick to keep bridges
        alive and the dashboard populated. Does NOT touch the FSM state machine
        — just encodes the description, runs the forward pass, records experience,
        and updates Hebbian weights.

        Args:
            description: Current thought/topic text (used as seed).
            metadata: Optional dict with 'routing_weights' etc.

        Returns:
            Forward pass result dict, or None if radial is unavailable.
        """
        if self.radial_network is None or self.seed_encoder is None:
            return None
        try:
            import torch
            seed_np = self.seed_encoder.encode_from_description(
                description,
                routing_weights=metadata.get('routing_weights') if metadata else None,
            )
            seed_tensor = torch.tensor(seed_np, dtype=torch.float32).unsqueeze(0)  # [1, 384]

            with torch.no_grad():
                result = self.radial_network.forward(seed_tensor)

            self._last_radial_output = result

            if self.experience_buffer is not None:
                self.experience_buffer.add(
                    input_embedding=seed_tensor,
                    ring_activations=result['ring_activations'],
                    ctm_trajectory=result['prediction_errors'],
                    kuro_reward=0.0,
                    outcome='thinking',
                )

            if self.hebbian is not None:
                rings = self.radial_network.rings
                activations = result['ring_activations']
                neuromod = result.get('neuromod_state')
                for i in range(len(rings) - 1):
                    self.hebbian.update(
                        rings[i + 1],
                        activations[i],
                        activations[i + 1],
                        neuromod=neuromod,
                    )

                # Apply reward-weighted Hebbian updates from ThoughtRadialBridge
                bridge_ref = getattr(self, '_thought_radial_bridge_ref', None)
                if bridge_ref is not None:
                    rewards = bridge_ref.drain_rewards()
                    if rewards:
                        avg_reward = sum(r['reward'] for r in rewards) / len(rewards)
                        for i in range(len(rings) - 1):
                            self.hebbian.update_with_reward(
                                rings[i + 1],
                                activations[i],
                                activations[i + 1],
                                reward=avg_reward,
                                neuromod=neuromod,
                            )

            return result
        except Exception as e:
            logger.warning(f"Radial tick failed: {e}")
            return None

    def _radial_forward(self, task: AgentTask) -> Optional[Dict]:
        """Run radial attention network on the current task.

        Builds a seed embedding from task context, runs the radial network
        forward pass (which triggers all bridge updates), and caches the
        result for downstream use and experience recording.

        Returns the forward() output dict, or None if radial is unavailable.
        """
        if self.radial_network is None or self.seed_encoder is None:
            return None

        try:
            import torch

            # Build seed from task context
            seed_np = self.seed_encoder.encode_from_description(
                task.description,
                routing_weights=task.metadata.get('routing_weights') if task.metadata else None,
            )
            seed_tensor = torch.tensor(seed_np, dtype=torch.float32).unsqueeze(0)  # [1, 384]

            # Forward pass — triggers all bridge updates (1-tick delay)
            with torch.no_grad():
                result = self.radial_network.forward(seed_tensor)

            self._last_radial_output = result

            # Record experience for sleep training
            if self.experience_buffer is not None:
                self.experience_buffer.add(
                    input_embedding=seed_tensor,
                    ring_activations=result['ring_activations'],
                    ctm_trajectory=result['prediction_errors'],
                    kuro_reward=0.0,  # Updated in _learn() with actual outcome
                    outcome='pending',
                )

            # Hebbian plasticity — live attention bias update
            if self.hebbian is not None:
                rings = self.radial_network.rings
                activations = result['ring_activations']
                neuromod = result.get('neuromod_state')
                for i in range(len(rings) - 1):
                    self.hebbian.update(
                        rings[i + 1],
                        activations[i],      # pre: current ring output
                        activations[i + 1],  # post: next ring output
                        neuromod=neuromod,
                    )

            return result

        except Exception as e:
            logger.warning(f"Radial forward failed: {e}")
            return None

    def _think(self, task: AgentTask) -> Optional[Any]:
        """Use CognitiveLoop or Planner to reason about the task."""
        if self.cognitive_loop:
            try:
                return self.cognitive_loop.process(task.description)
            except Exception as e:
                logger.warning(f"CognitiveLoop failed, falling back to planner: {e}")

        if self.planner:
            try:
                return self.planner.predict(task.description)
            except Exception as e:
                logger.error(f"Planner also failed: {e}")

        return None

    def _observe(self, task: AgentTask, prediction: Any) -> Dict[str, Any]:
        """
        Observe the outcome of a task.
        For now this is a basic outcome structure.
        When bridges are connected, this will include actual execution results.
        """
        outcome = {
            'task_id': task.task_id,
            'task_description': task.description,
            'source': task.source,
            'priority': task.priority.name,
            'prediction_available': prediction is not None,
            'duration': time.time() - self._current_task_start,
            'timestamp': time.time(),
        }

        # Extract confidence from prediction if available
        if prediction and hasattr(prediction, 'confidence'):
            outcome['confidence'] = float(prediction.confidence)
        if prediction and hasattr(prediction, 'brain_gates'):
            gates = prediction.brain_gates
            if hasattr(gates, 'tolist'):
                gates = gates.tolist()
            outcome['brain_gates'] = gates

        return outcome

    def _learn(self, task: AgentTask, prediction: Any, outcome: Dict):
        """Record the experience for learning."""
        if self.memory:
            try:
                # Use remember_task to store in working memory
                result = {
                    'task': task.description,
                    'outcome': 'success' if outcome.get('confidence', 0) > 0.5 else 'partial',
                    'source': task.source,
                    'duration': outcome.get('duration', 0),
                }
                if prediction and hasattr(prediction, 'brain_gates'):
                    gates = prediction.brain_gates
                    if hasattr(gates, 'tolist'):
                        gates = gates.tolist()
                    result['brain_gates'] = gates

                self.memory.remember_task(result)
            except Exception as e:
                logger.warning(f"Failed to store experience: {e}")

        # Feed motivation system (P3.34-36)
        if self.motivation:
            try:
                success = outcome.get('confidence', 0) > 0.5
                pe = outcome.get('prediction_error', 0.0)
                domain = task.metadata.get('domain', task.source)
                self.motivation.observe_task_outcome(
                    domain=domain,
                    success=success,
                    prediction_error=pe,
                    task_description=task.description,
                )
            except Exception as e:
                logger.debug(f"Motivation feedback failed: {e}")

        # Feed goal manager (P3.37-40)
        if self.goal_manager:
            try:
                goal_id = task.metadata.get('goal_id')
                if goal_id:
                    success = outcome.get('confidence', 0) > 0.5
                    reason = outcome.get('failure_reason', '')
                    self.goal_manager.record_task_outcome(goal_id, success, reason)
                elif not success:
                    # Record failures for failure tracker even without goal_id
                    domain = task.metadata.get('domain', task.source)
                    reason = task.metadata.get('failure_reason', task.description[:80])
                    self.goal_manager.generator.record_failure(domain, reason)
            except Exception as e:
                logger.debug(f"Goal management feedback failed: {e}")

        # Feed proactive behavior (P3.41-43)
        if self.proactive:
            try:
                success = outcome.get('confidence', 0) > 0.5
                if not success:
                    # Forward failures to proactive task generator
                    domain = task.metadata.get('domain', task.source)
                    error_msg = outcome.get('failure_reason', task.description[:80])
                    self.proactive.observe_job_failure(
                        job_name=task.description[:60],
                        error_message=error_msg,
                        domain=domain,
                    )
                    # Also observe error signal
                    confidence = outcome.get('confidence', 0.5)
                    self.proactive.observe_error(
                        error_signal=1.0 - confidence,
                        source=domain,
                        details=error_msg,
                    )
            except Exception as e:
                logger.debug(f"Proactive behavior feedback failed: {e}")

        # Update last experience buffer entry with actual outcome reward
        if self.experience_buffer is not None and outcome.get('radial_active'):
            try:
                success = outcome.get('confidence', 0) > 0.5
                reward = 1.0 if success else -0.5
                buf = self.experience_buffer._buffer
                if buf:
                    buf[-1]['kuro_reward'] = reward
                    buf[-1]['outcome'] = 'success' if success else 'failure'
            except Exception as e:
                logger.debug(f"Experience buffer reward update failed: {e}")

        # Emit learning event
        if self.event_bus:
            try:
                from core.event_bus import BrainEvent, EventPriority
                self.event_bus.publish(BrainEvent(
                    topic='agent.task_completed',
                    data=outcome,
                    source='agent_loop',
                    priority=EventPriority.NORMAL,
                ))
            except Exception:
                pass

    # ─── Motivation Drive Integration (P3.34-36) ─────────────────────

    def _generate_motivation_tasks(self):
        """
        Query the MotivationSystem for impulses and convert to tasks.
        Called when the loop is idle and no tasks are pending.
        """
        if not self.motivation:
            return

        try:
            # Get homeostatic and neuromodulator state
            h_state = None
            n_levels = None
            if self.homeostatic:
                h_state = self.homeostatic.state
            if self.neuromodulation:
                n_levels = getattr(self.neuromodulation, 'levels', None)

            impulses = self.motivation.generate_all_impulses(
                homeostatic_state=h_state,
                neuromodulator_levels=n_levels,
            )

            for impulse in impulses:
                # Convert DriveImpulse to AgentTask
                # Motivation-generated tasks are self-initiated (P2 priority)
                # except consolidation which is background (P3)
                if impulse.drive_type.value == 'consolidation':
                    priority = TaskPriority.BACKGROUND
                else:
                    priority = TaskPriority.SELF_INITIATED

                self.submit_task(
                    description=impulse.description,
                    priority=priority,
                    source=impulse.source_drive or 'motivation',
                    urgency=impulse.urgency,
                    importance=impulse.importance,
                    metadata={
                        'drive_type': impulse.drive_type.value,
                        **impulse.metadata,
                    },
                )
                logger.debug(
                    f"Motivation task: [{impulse.drive_type.value}] "
                    f"{impulse.description[:60]} (u={impulse.urgency:.2f})"
                )

        except Exception as e:
            logger.warning(f"Motivation drive error: {e}")

    # ─── Goal Management Integration (P3.37-40) ─────────────────────

    def _run_goal_management(self):
        """
        Run the GoalManager tick: generate, prioritize, and submit goal-derived tasks.
        Called when the loop is idle and no tasks are pending.
        """
        if not self.goal_manager:
            return

        try:
            # Gather prediction errors (from predictive coding if available)
            prediction_errors = None
            if hasattr(self, 'planner') and self.planner:
                try:
                    pc = getattr(self.planner, 'predictive_coding', None)
                    if pc is None:
                        # Try through the planner's internal planner
                        inner = getattr(self.planner, 'planner', None)
                        if inner:
                            pc = getattr(inner, 'predictive_coding', None)
                    if pc:
                        curiosity = pc.get_curiosity_signal()
                        prediction_errors = {
                            'layer1': curiosity.get('layer1_error', 0.0),
                            'layer3': curiosity.get('layer3_error', 0.0),
                        }
                except Exception:
                    pass

            # Get neuromodulation levels
            n_levels = None
            if self.neuromodulation:
                n_levels = getattr(self.neuromodulation, 'levels', None)

            # Convert sensor events to goal-manager format
            sensor_events = None
            raw_events = list(self._sensor_events)  # Don't drain - perceive phase does that
            if raw_events:
                sensor_events = []
                for evt in raw_events[-10:]:  # Last 10 events
                    if hasattr(evt, 'topic') and hasattr(evt, 'data'):
                        sensor_events.append({
                            'type': evt.topic,
                            'data': evt.data if isinstance(evt.data, dict) else {'message': str(evt.data)},
                        })

            # Run goal manager tick
            goal_tasks = self.goal_manager.tick(
                sensor_events=sensor_events,
                prediction_errors=prediction_errors,
                neuro_levels=n_levels,
            )

            # Convert GoalTasks to AgentTasks
            for gt in goal_tasks:
                self.submit_task(
                    description=gt.description,
                    priority=TaskPriority.SELF_INITIATED,
                    source='goal',
                    urgency=gt.metadata.get('urgency', 0.5),
                    importance=gt.metadata.get('importance', 0.5),
                    metadata={
                        'goal_id': gt.goal_id,
                        'domain': gt.domain,
                        'horizon': gt.horizon.value,
                        'goal_source': gt.source.value,
                    },
                )
                logger.debug(
                    f"Goal task: [{gt.horizon.value}] "
                    f"{gt.description[:60]} (score={gt.priority_score:.2f})"
                )

        except Exception as e:
            logger.warning(f"Goal management error: {e}")

    # ─── Proactive Behavior Integration (P3.41-43) ────────────────────

    def _run_proactive_behavior(self):
        """
        Run the ProactiveBehavior tick: generate tasks from errors, schedules, and reactive patterns.
        Called when the loop is idle and no tasks are pending.
        """
        if not self.proactive:
            return

        try:
            # Build system context for reactive pattern evaluation
            context = {}
            idle_seconds = time.time() - self._last_activity_time
            context['idle_time'] = idle_seconds

            # Add error signal from recent task failures
            if self._total_tasks_processed > 0:
                recent_fail_rate = self._total_tasks_failed / max(1, self._total_tasks_processed)
                context['error_signal'] = recent_fail_rate

            # Add homeostatic info for scheduler adaptation
            sleep_pressure = None
            system_load = None
            if self.homeostatic:
                try:
                    h_state = self.homeostatic.get_state() if hasattr(self.homeostatic, 'get_state') else None
                    if h_state:
                        sleep_pressure = getattr(h_state, 'sleep_pressure', None) or (
                            h_state.get('sleep_pressure') if isinstance(h_state, dict) else None
                        )
                except Exception:
                    pass

            # Derive activity level from recent task throughput
            activity_level = min(1.0, self._total_tasks_processed / max(1, self._total_ticks) * 10)

            # Get proactive tasks
            proactive_tasks = self.proactive.tick(
                context=context,
                system_load=system_load,
                activity_level=activity_level,
                sleep_pressure=sleep_pressure,
            )

            # Convert ProactiveTasks to AgentTasks
            for pt in proactive_tasks:
                # Scheduled tasks are background priority, others are self-initiated
                if pt.source.value == 'scheduled':
                    priority = TaskPriority.BACKGROUND
                else:
                    priority = TaskPriority.SELF_INITIATED

                self.submit_task(
                    description=pt.description,
                    priority=priority,
                    source=f'proactive:{pt.source.value}',
                    urgency=pt.urgency,
                    importance=pt.importance,
                    metadata={
                        'proactive_task_id': pt.task_id,
                        'proactive_source': pt.source.value,
                        'domain': pt.domain,
                        **pt.metadata,
                    },
                )
                logger.debug(
                    f"Proactive task: [{pt.source.value}] "
                    f"{pt.description[:60]} (u={pt.urgency:.2f})"
                )

        except Exception as e:
            logger.warning(f"Proactive behavior error: {e}")

    # ─── Interrupt Handling ───────────────────────────────────────────

    def _handle_interrupt(self):
        """Handle a pending interrupt by executing it immediately."""
        task = self.interrupt_handler.get_interrupt()
        if task:
            logger.info(f"Handling interrupt: {task.description[:80]}")
            # Suspend current work if needed
            if self._current_task:
                logger.info(f"Suspending current task: {self._current_task.description[:60]}")
                # Re-queue current task
                with self._task_queue_lock:
                    self._task_queue.append(self._current_task)
                self._current_task = None

            self._execute_task(task)

    # ─── Sensor Event Processing ──────────────────────────────────────

    def _process_sensor_events(self, events: List[Any]):
        """
        Convert sensor events into tasks if they warrant attention.
        This is the perception-to-action bridge.
        """
        for event in events:
            # For now, we log sensor events.
            # Full sensor -> task generation will come in Phase 1+3 integration.
            if hasattr(event, 'topic'):
                logger.debug(f"Sensor event: {event.topic}")

    # ─── Dream Mode ───────────────────────────────────────────────────

    def _should_dream(self) -> bool:
        """Check if we should enter dream mode."""
        if self.fsm.state == AgentState.DREAMING:
            # Already dreaming - check if dream is done
            dream_elapsed = time.time() - self._dream_start
            if dream_elapsed >= self.config.dream_duration_seconds:
                self.fsm.transition(AgentState.IDLE)
                return False
            return True

        # Check homeostatic sleep pressure
        if self.homeostatic:
            try:
                state = self.homeostatic.get_state()
                if hasattr(state, 'sleep_pressure') and state.sleep_pressure > self.config.sleep_pressure_threshold:
                    return True
            except Exception:
                pass

        return False

    def _enter_dream_mode(self):
        """Enter dream/consolidation mode.

        On first entry (FSM transition to DREAMING):
          1. Set SleepWake bridge to dream state (low arousal, high melatonin)
          2. Run RadialSleepTrainer for N epochs on experience buffer
          3. Register EWC anchor after training
          4. Log dream cycle metrics
        Subsequent calls just wait until the dream period expires.
        """
        if self.fsm.state != AgentState.DREAMING:
            if not self.fsm.transition(AgentState.DREAMING):
                return

            self._dream_start = time.time()
            logger.info("Entering dream mode (memory consolidation)")

            # Emit dream event
            if self.event_bus:
                try:
                    from core.event_bus import BrainEvent, EventPriority
                    self.event_bus.publish(BrainEvent(
                        topic='agent.dream_start',
                        data={'timestamp': time.time()},
                        source='agent_loop',
                        priority=EventPriority.LOW,
                    ))
                except Exception:
                    pass

            # ── Dream Bridge Modulation ──────────────────────────────
            # Set SleepWake bridge to sleep state: low arousal, high
            # melatonin, elevated REM probability.  Other bridges keep
            # their last waking values and respond naturally to replay.
            self._set_dream_bridge_state()

            # ── Radial Sleep Training ────────────────────────────────
            self._run_radial_dream_training()

        # Wait the dream tick interval
        time.sleep(min(self.config.dream_tick_interval, 5.0))

        # Check if dream period is over
        dream_elapsed = time.time() - self._dream_start
        if dream_elapsed >= self.config.dream_duration_seconds:
            self._total_dream_time += dream_elapsed
            self._restore_wake_bridge_state()
            self.fsm.transition(AgentState.IDLE)
            logger.info(f"Dream mode ended after {dream_elapsed:.1f}s")

    def _set_dream_bridge_state(self):
        """Set SleepWake bridge to sleep/dream state.

        Biologically: during sleep, arousal drops, melatonin rises,
        histamine is suppressed, and REM probability increases.
        This lets other bridges respond naturally to dream replay
        with appropriate sleep-mode modulation.
        """
        if self.radial_network is None:
            return

        mod_ctx = getattr(self.radial_network, '_modulation_context', None)
        if mod_ctx is None:
            return

        try:
            from core.sleep_wake_bridge import SleepWakeState

            # Cache previous state for restoration after dreaming
            self._pre_dream_sleep_state = getattr(mod_ctx, 'sleep_wake', None)

            # Set dream-mode sleep state
            mod_ctx.sleep_wake = SleepWakeState(
                arousal=0.15,            # Low arousal (sleeping)
                sensory_gain=0.1,        # Minimal sensory gating
                histamine=0.1,           # Suppressed wakefulness
                is_awake=False,          # Asleep
                wakefulness_drive=0.05,  # Very low wake drive
                melatonin=0.85,          # High melatonin
                sleep_pressure=0.9,      # High sleep pressure
                cholinergic_tone=0.7,    # Elevated for REM (ACh active)
                rem_probability=0.6,     # Moderate REM probability
            )

            logger.info("Dream bridge state: SleepWake set to dream mode "
                        "(arousal=0.15, melatonin=0.85, REM=0.6)")

        except Exception as e:
            logger.warning(f"Failed to set dream bridge state: {e}")

    def _restore_wake_bridge_state(self):
        """Restore SleepWake bridge to its pre-dream state."""
        if self.radial_network is None:
            return

        mod_ctx = getattr(self.radial_network, '_modulation_context', None)
        if mod_ctx is None:
            return

        pre = getattr(self, '_pre_dream_sleep_state', None)
        if pre is not None:
            mod_ctx.sleep_wake = pre
            logger.info("Dream bridge state restored to pre-dream values")
        else:
            # Fallback: set to default waking state
            try:
                from core.sleep_wake_bridge import SleepWakeState
                mod_ctx.sleep_wake = SleepWakeState()  # Default waking values
            except Exception:
                pass

    def _run_radial_dream_training(self):
        """Run RadialSleepTrainer on experience buffer during dream mode.

        Executes multiple training epochs with bridge-aware modulation
        (the ModulationContext is in sleep state during replay).  After
        training, registers an EWC anchor to protect learned weights and
        logs metrics.
        """
        if self.radial_trainer is None:
            return
        if self.experience_buffer is None or len(self.experience_buffer) == 0:
            logger.info("Dream training skipped: experience buffer empty")
            return

        train_start = time.time()
        buffer_size = len(self.experience_buffer)
        n_epochs = getattr(self.config, 'dream_training_epochs', 3)
        batch_size = min(32, buffer_size)

        losses = []
        try:
            for epoch in range(n_epochs):
                avg_loss = self.radial_trainer.train_epoch(batch_size=batch_size)
                losses.append(avg_loss)
                logger.info(
                    "Dream training epoch %d/%d: loss=%.4f (buffer=%d)",
                    epoch + 1, n_epochs, avg_loss, buffer_size,
                )

                # Hebbian alignment: nudge learned weights toward reward-shaped biases
                if self.radial_network is not None:
                    import torch
                    hebbian_targets = self.radial_network.get_hebbian_targets()
                    total_bias_energy = sum(t.abs().sum().item() for t in hebbian_targets)
                    if total_bias_energy > 1.0:  # Only if biases have been meaningfully shaped
                        hebbian_loss = sum(
                            torch.nn.functional.mse_loss(ring.attention_bias, target)
                            for ring, target in zip(self.radial_network.rings, hebbian_targets)
                            if target.abs().sum() > 1e-6
                        )
                        if isinstance(hebbian_loss, torch.Tensor):
                            (hebbian_loss * 0.1).backward()
                            logger.info(f"  Dream Hebbian alignment loss: {hebbian_loss.item():.6f}")

            # Register EWC anchor after training to protect learned weights
            self.radial_trainer.register_ewc_anchor()

            train_elapsed = time.time() - train_start
            avg_loss_all = sum(losses) / max(len(losses), 1)

            logger.info(
                "Dream training complete: %d epochs, avg_loss=%.4f, "
                "buffer=%d, elapsed=%.2fs",
                n_epochs, avg_loss_all, buffer_size, train_elapsed,
            )

            # ── Audit Log ────────────────────────────────────────────
            self._log_dream_cycle(
                n_epochs=n_epochs,
                losses=losses,
                buffer_size=buffer_size,
                elapsed_s=train_elapsed,
            )

            # Emit event
            if self.event_bus:
                try:
                    from core.event_bus import BrainEvent, EventPriority
                    self.event_bus.publish(BrainEvent(
                        topic='agent.dream_training_complete',
                        data={
                            'epochs': n_epochs,
                            'avg_loss': avg_loss_all,
                            'buffer_size': buffer_size,
                            'elapsed_s': train_elapsed,
                        },
                        source='agent_loop',
                        priority=EventPriority.LOW,
                    ))
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Dream training failed: {e}")

        # Consolidation: biases burned into weights, reduce by 50%
        if self.radial_network is not None:
            for ring in self.radial_network.rings:
                ring.attention_bias.mul_(0.5)
            logger.info("  Hebbian biases consolidated (50% reset)")

    def _log_dream_cycle(self, n_epochs: int, losses: list,
                          buffer_size: int, elapsed_s: float):
        """Log dream cycle metrics to PredictionAuditLog if available."""
        audit_log = getattr(self, 'audit_log', None)
        if audit_log is None:
            return

        try:
            from core.brain_monitoring import AuditEntry
            from datetime import datetime

            # Collect bridge states summary
            bridge_summary = {}
            mod_ctx = getattr(self.radial_network, '_modulation_context', None) if self.radial_network else None
            if mod_ctx is not None:
                bridge_summary = {
                    'attention_gain': getattr(mod_ctx, 'attention_gain', 1.0),
                    'precision_boost': getattr(mod_ctx, 'precision_boost', 1.0),
                    'ffn_throughput': getattr(mod_ctx, 'ffn_throughput', 1.0),
                    'threshold_mod': getattr(mod_ctx, 'threshold_mod', 1.0),
                }

            entry = AuditEntry(
                timestamp=datetime.now().isoformat(),
                task=f"dream_training:{n_epochs}ep",
                task_type='dream_cycle',
                pipeline_mode='radial_sleep',
                confidence=1.0 - (losses[-1] if losses else 0.0),
                success_probability=1.0 if all(l < 10.0 for l in losses) else 0.5,
                brain_gates=[],
                dominant_modalities=['sleep', 'consolidation'],
                latency_ms=elapsed_s * 1000,
                loop_iterations=n_epochs,
            )
            audit_log.record(entry)

        except Exception as e:
            logger.debug(f"Dream cycle audit log failed: {e}")

    # ─── Helper Methods ───────────────────────────────────────────────

    def _has_work(self) -> bool:
        """Check if there are pending tasks or interrupts."""
        if self.interrupt_handler.has_interrupt():
            return True
        with self._task_queue_lock:
            return len(self._task_queue) > 0

    # ─── State API ────────────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Get complete agent loop state for dashboard/API."""
        with self._task_queue_lock:
            queue_size = len(self._task_queue)
            queue_preview = [t.to_dict() for t in sorted(self._task_queue, key=lambda t: t.score())[:5]]

        idle_seconds = time.time() - self._last_activity_time

        return {
            'running': self._running,
            'state_machine': self.fsm.to_dict(),
            'task_queue': {
                'size': queue_size,
                'preview': queue_preview,
            },
            'interrupts': self.interrupt_handler.to_dict(),
            'autonomy_budget': self.autonomy_budget.to_dict(),
            'current_task': self._current_task.to_dict() if self._current_task else None,
            'stats': {
                'total_ticks': self._total_ticks,
                'total_tasks_processed': self._total_tasks_processed,
                'total_tasks_succeeded': self._total_tasks_succeeded,
                'total_tasks_failed': self._total_tasks_failed,
                'success_rate': (
                    round(self._total_tasks_succeeded / max(1, self._total_tasks_processed), 3)
                ),
                'total_dream_time_seconds': round(self._total_dream_time, 1),
                'idle_seconds': round(idle_seconds, 1),
                'consecutive_errors': self._consecutive_errors,
            },
            'motivation': self.motivation.get_state() if self.motivation else None,
            'goal_management': self.goal_manager.get_state() if self.goal_manager else None,
            'proactive_behavior': self.proactive.get_state() if self.proactive else None,
            'safety_regulation': self.safety.get_state() if self.safety else None,
            # Phase 1: Sensor Systems
            'system_vitals_sensor': self.system_vitals_sensor.get_state() if self.system_vitals_sensor else None,
            'file_system_sensor': self.file_system_sensor.get_state() if self.file_system_sensor else None,
            'process_sensor': self.process_sensor.get_state() if self.process_sensor else None,
            'log_sensor': self.log_sensor.get_state() if self.log_sensor else None,
            'git_activity_sensor': self.git_activity_sensor.get_state() if self.git_activity_sensor else None,
            'sensor_registry': self.sensor_registry.get_state() if self.sensor_registry else None,
            'sensor_fusion': self.sensor_fusion.get_state() if self.sensor_fusion else None,
            'perception_pipeline': self.perception_pipeline.get_state() if self.perception_pipeline else None,
            'attention_sampling': self.attention_sampling.get_state() if self.attention_sampling else None,
            'novelty_filter': self.novelty_filter.get_state() if self.novelty_filter else None,
            'sensory_memory': self.sensory_memory.get_state() if self.sensory_memory else None,
            # Phase 2: Action Systems
            'approval_gate': self.approval_gate.get_state() if self.approval_gate else None,
            'action_planner': self.action_planner.get_state() if self.action_planner else None,
            'action_validator': self.action_validator.get_state() if self.action_validator else None,
            'action_monitor': self.action_monitor.get_state() if self.action_monitor else None,
            'action_outcome_detector': self.action_outcome_detector.get_state() if self.action_outcome_detector else None,
            'action_replay_memory': self.action_replay_memory.get_state() if self.action_replay_memory else None,
            'action_learning': self.action_learning.get_state() if self.action_learning else None,
            # Phase 4: Language & Communication
            'language_center': self.language_center.get_state() if self.language_center else None,
            'personality': self.personality.get_state() if self.personality else None,
            'communication_style': self.communication_style.get_state() if self.communication_style else None,
            'status_updater': self.status_updater.get_state() if self.status_updater else None,
            'explanation_system': self.explanation_system.get_state() if self.explanation_system else None,
            'suggestion_engine': self.suggestion_engine.get_state() if self.suggestion_engine else None,
            'dialogue_manager': self.dialogue_manager.get_state() if self.dialogue_manager else None,
            # Phase 5: Learning Systems
            'experience_replay': self.experience_replay.get_state() if self.experience_replay else None,
            'outcome_learning': self.outcome_learning.get_state() if self.outcome_learning else None,
            'transfer_learning': self.transfer_learning.get_state() if self.transfer_learning else None,
            'skill_library': self.skill_library.get_state() if self.skill_library else None,
            'world_model': self.world_model.get_state() if self.world_model else None,
            'causal_world_model': self.causal_world_model.get_state() if self.causal_world_model else None,
            'predictive_world_model': self.predictive_world_model.get_state() if self.predictive_world_model else None,
            'self_awareness': self.self_awareness.get_state() if self.self_awareness else None,
            'learning_diagnosis': self.learning_diagnosis.get_state() if self.learning_diagnosis else None,
            'knowledge_gaps': self.knowledge_gaps.get_state() if self.knowledge_gaps else None,
            'feedback_interpretation': self.feedback_interpretation.get_state() if self.feedback_interpretation else None,
            'collaborative_learning': self.collaborative_learning.get_state() if self.collaborative_learning else None,
            # Phase 6: Identity Systems
            'self_model': self.self_model.get_state() if self.self_model else None,
            'autobiographic_memory': self.autobiographic_memory.get_state() if self.autobiographic_memory else None,
            'value_system': self.value_system.get_state() if self.value_system else None,
            'emotional_memory': self.emotional_memory.get_state() if self.emotional_memory else None,
            'mood_system': self.mood_system.get_state() if self.mood_system else None,
            'stress_response': self.stress_response.get_state() if self.stress_response else None,
            'user_model': self.user_model.get_state() if self.user_model else None,
            'trust_model': self.trust_model.get_state() if self.trust_model else None,
            'collaboration_patterns': self.collaboration_patterns.get_state() if self.collaboration_patterns else None,
            'relationship_history': self.relationship_history.get_state() if self.relationship_history else None,
            # Phase 7: Resilience Systems
            'graceful_degradation': self.graceful_degradation.get_state() if self.graceful_degradation else None,
            'self_healing': self.self_healing.get_state() if self.self_healing else None,
            'adversarial_resilience': self.adversarial_resilience.get_state() if self.adversarial_resilience else None,
            'uncertainty_handling': self.uncertainty_handling.get_state() if self.uncertainty_handling else None,
            'context_switching': self.context_switching.get_state() if self.context_switching else None,
            'long_running_tasks': self.long_running_tasks.get_state() if self.long_running_tasks else None,
            'resource_awareness': self.resource_awareness.get_state() if self.resource_awareness else None,
            # Phase 8: Ecosystem Intelligence
            'orchestrator_of_orchestrators': self.orchestrator_of_orchestrators.get_state() if self.orchestrator_of_orchestrators else None,
            'synergy_learning': self.synergy_learning.get_state() if self.synergy_learning else None,
            'knowledge_export': self.knowledge_export.get_state() if self.knowledge_export else None,
            'evolutionary_growth': self.evolutionary_growth.get_state() if self.evolutionary_growth else None,
            'consciousness_evolution': self.consciousness_evolution.get_state() if self.consciousness_evolution else None,
            # Neuroscience Architecture Extensions
            'cerebellum': self.cerebellum.get_state() if self.cerebellum else None,
            'prefrontal_cortex': self.prefrontal_cortex.get_state() if self.prefrontal_cortex else None,
            'hypothalamus': self.hypothalamus.get_state() if self.hypothalamus else None,
            'default_mode_network': self.default_mode_network.get_state() if self.default_mode_network else None,
            'insular_cortex': self.insular_cortex.get_state() if self.insular_cortex else None,
            'superior_colliculus': self.superior_colliculus.get_state() if self.superior_colliculus else None,
            'entorhinal_cortex': self.entorhinal_cortex.get_state() if self.entorhinal_cortex else None,
            'nucleus_accumbens': self.nucleus_accumbens.get_state() if self.nucleus_accumbens else None,
            'anterior_cingulate': self.anterior_cingulate.get_state() if self.anterior_cingulate else None,
            # Phase D: Tier 1 Brain Structures
            'amygdala': self.amygdala.get_state() if self.amygdala else None,
            'ventral_tegmental_area': self.ventral_tegmental_area.get_state() if self.ventral_tegmental_area else None,
            'locus_coeruleus': self.locus_coeruleus.get_state() if self.locus_coeruleus else None,
            'raphe_nuclei': self.raphe_nuclei.get_state() if self.raphe_nuclei else None,
            'lateral_habenula': self.lateral_habenula.get_state() if self.lateral_habenula else None,
            'periaqueductal_gray': self.periaqueductal_gray.get_state() if self.periaqueductal_gray else None,
            # Phase E: Tier 2 Brain Structures
            'claustrum': self.claustrum.get_state() if self.claustrum else None,
            'reticular_formation': self.reticular_formation.get_state() if self.reticular_formation else None,
            'basal_forebrain': self.basal_forebrain.get_state() if self.basal_forebrain else None,
            'septal_nuclei': self.septal_nuclei.get_state() if self.septal_nuclei else None,
            'inferior_olive': self.inferior_olive.get_state() if self.inferior_olive else None,
            'mammillary_bodies': self.mammillary_bodies.get_state() if self.mammillary_bodies else None,
            'bnst': self.bnst.get_state() if self.bnst else None,
            'parabrachial_nucleus': self.parabrachial_nucleus.get_state() if self.parabrachial_nucleus else None,
            'orbitofrontal_cortex': self.orbitofrontal_cortex.get_state() if self.orbitofrontal_cortex else None,
            # Phase F: Tier 3 Brain Structures
            'substantia_nigra': self.substantia_nigra.get_state() if self.substantia_nigra else None,
            'zona_incerta': self.zona_incerta.get_state() if self.zona_incerta else None,
            'red_nucleus': self.red_nucleus.get_state() if self.red_nucleus else None,
            'tuberomammillary_nucleus': self.tuberomammillary_nucleus.get_state() if self.tuberomammillary_nucleus else None,
            'pedunculopontine_nucleus': self.pedunculopontine_nucleus.get_state() if self.pedunculopontine_nucleus else None,
            'ventral_pallidum': self.ventral_pallidum.get_state() if self.ventral_pallidum else None,
            'nucleus_tractus_solitarius': self.nucleus_tractus_solitarius.get_state() if self.nucleus_tractus_solitarius else None,
            'olfactory_system': self.olfactory_system.get_state() if self.olfactory_system else None,
            'fusiform_gyrus': self.fusiform_gyrus.get_state() if self.fusiform_gyrus else None,
            'temporoparietal_junction': self.temporoparietal_junction.get_state() if self.temporoparietal_junction else None,
            'posterior_parietal_cortex': self.posterior_parietal_cortex.get_state() if self.posterior_parietal_cortex else None,
            'cortical_column': self.cortical_column.get_state() if self.cortical_column else None,
            'pineal_gland': self.pineal_gland.get_state() if self.pineal_gland else None,
            'corpus_callosum': self.corpus_callosum.get_state() if self.corpus_callosum else None,
        }

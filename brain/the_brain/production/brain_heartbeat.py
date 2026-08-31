"""
BrainHeartbeat - Autonomous Background Processing for Tahlamus

Provides continuous background activity for the brain, similar to how
real brains are always active - consolidating memories, regulating
neurotransmitters, and maintaining homeostasis.

Key Functions:
1. Neuromodulation decay (homeostasis)
2. Temporal memory updates
3. Dream mode triggers (offline consolidation)
4. Meta-learning checks
5. Health monitoring

Runs in a background thread with configurable interval (default 30s).
"""

import logging
import threading
import time
import numpy as np
from typing import Optional, Dict, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class BrainHeartbeatConfig:
    """Configuration for brain heartbeat"""

    def __init__(
        self,
        interval_seconds: float = 30.0,
        enable_dream_mode: bool = True,
        dream_idle_threshold_seconds: float = 300.0,  # 5 minutes
        enable_temporal_updates: bool = True,
        enable_neuromodulation_decay: bool = True,
        enable_meta_learning_checks: bool = True,
        enable_health_monitoring: bool = True,
        meta_learning_check_interval: int = 10,  # Every 10 heartbeats
    ):
        """
        Initialize heartbeat configuration

        Args:
            interval_seconds: Seconds between heartbeat ticks
            enable_dream_mode: Enable offline consolidation during idle
            dream_idle_threshold_seconds: Idle time before dream mode activates
            enable_temporal_updates: Enable temporal pattern updates
            enable_neuromodulation_decay: Enable homeostatic decay
            enable_meta_learning_checks: Enable periodic meta-learning analysis
            enable_health_monitoring: Enable system health monitoring
            meta_learning_check_interval: Heartbeats between meta-learning checks
        """
        self.interval_seconds = interval_seconds
        self.enable_dream_mode = enable_dream_mode
        self.dream_idle_threshold_seconds = dream_idle_threshold_seconds
        self.enable_temporal_updates = enable_temporal_updates
        self.enable_neuromodulation_decay = enable_neuromodulation_decay
        self.enable_meta_learning_checks = enable_meta_learning_checks
        self.enable_health_monitoring = enable_health_monitoring
        self.meta_learning_check_interval = meta_learning_check_interval


class BrainHeartbeat(threading.Thread):
    """
    Autonomous heartbeat thread for continuous brain activity

    Runs in background and performs regular maintenance:
    - Neuromodulation homeostasis (decay to baseline)
    - Temporal memory pattern updates
    - Dream mode consolidation (when idle)
    - Meta-learning trend analysis
    - System health monitoring
    """

    def __init__(
        self,
        planner,  # ProductionPlanner instance
        config: Optional[BrainHeartbeatConfig] = None,
        on_tick: Optional[Callable] = None,
        on_dream: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Initialize brain heartbeat

        Args:
            planner: ProductionPlanner instance with HierarchicalPlanner
            config: Heartbeat configuration
            on_tick: Optional callback after each tick
            on_dream: Optional callback when dream mode activates
            on_error: Optional callback when errors occur
        """
        super().__init__(daemon=True, name="BrainHeartbeat")

        self.planner = planner
        self.config = config or BrainHeartbeatConfig()

        # Callbacks
        self.on_tick = on_tick
        self.on_dream = on_dream
        self.on_error = on_error

        # State
        self.running = False
        self.tick_count = 0
        self.last_prediction_time = time.time()
        self.idle_time_seconds = 0.0
        self.total_dreams = 0
        self.errors = []

        # CTM dream training
        self._ctm_trainer = None
        self._ctm_training_cycle = 0  # Tracks which domain to train next
        self._ctm_training_interval = 3  # Train CTMs every N dream cycles
        try:
            from core.dream_mode_ctm_trainer import DreamModeCTMTrainer
            self._ctm_trainer = DreamModeCTMTrainer(
                checkpoint_dir="data/ctm_checkpoints",
                enable_cuda=False
            )
            logger.info("Dream-mode CTM trainer initialized")
        except Exception as e:
            logger.warning(f"Dream-mode CTM trainer not available: {e}")

        # Homeostatic regulation
        self._homeostatic = None
        try:
            from core.homeostatic_regulation import HomeostaticRegulator, HomeostaticConfig
            if hasattr(planner, '_yaml_config') and planner._yaml_config:
                h_config = HomeostaticConfig.from_yaml(planner._yaml_config)
            else:
                h_config = None
            self._homeostatic = HomeostaticRegulator(config=h_config)
            logger.info("Homeostatic regulation initialized")
        except ImportError:
            logger.warning("Homeostatic regulation not available")

        # Statistics
        self.heartbeat_history = []

    def run(self):
        """Main heartbeat loop (runs in background thread)"""
        self.running = True
        print(f"[BrainHeartbeat] Started (interval={self.config.interval_seconds}s)")

        while self.running:
            try:
                time.sleep(self.config.interval_seconds)
                self.tick()
            except Exception as e:
                self._handle_error(e)

    def tick(self):
        """Execute one heartbeat cycle"""
        start_time = time.time()
        actions_taken = []

        try:
            # Update idle time
            time_since_last_prediction = time.time() - self.last_prediction_time
            self.idle_time_seconds = time_since_last_prediction

            # === 1. NEUROMODULATION DECAY (Homeostasis) ===
            if self.config.enable_neuromodulation_decay:
                if self._apply_neuromodulation_decay():
                    actions_taken.append("neuromodulation_decay")

            # === 2. TEMPORAL MEMORY UPDATES ===
            if self.config.enable_temporal_updates:
                if self._update_temporal_memory():
                    actions_taken.append("temporal_memory_update")

            # === 3. DREAM MODE (if idle) ===
            if self.config.enable_dream_mode:
                if self.idle_time_seconds > self.config.dream_idle_threshold_seconds:
                    if self._trigger_dream_mode():
                        actions_taken.append("dream_mode_consolidation")

            # === 4. META-LEARNING CHECKS ===
            if self.config.enable_meta_learning_checks:
                if self.tick_count % self.config.meta_learning_check_interval == 0:
                    if self._check_meta_learning():
                        actions_taken.append("meta_learning_check")

            # === 5. HEALTH MONITORING ===
            if self.config.enable_health_monitoring:
                health = self._monitor_health()
                actions_taken.append("health_check")

            # === 6. HOMEOSTATIC REGULATION ===
            if self._homeostatic:
                is_idle = self.idle_time_seconds > 60
                self._homeostatic.tick(
                    dt_seconds=self.config.interval_seconds,
                    is_idle=is_idle
                )
                # Check if homeostatic sleep pressure forces dream mode
                if self._homeostatic.should_trigger_dream() and not any('dream' in a for a in actions_taken):
                    if self._trigger_dream_mode():
                        self._homeostatic.on_dream_mode()
                        actions_taken.append("homeostatic_forced_dream")
                actions_taken.append("homeostatic_tick")

            # Record tick
            self.tick_count += 1
            elapsed = time.time() - start_time

            tick_record = {
                'tick_number': self.tick_count,
                'timestamp': datetime.now().isoformat(),
                'idle_time_seconds': self.idle_time_seconds,
                'actions_taken': actions_taken,
                'elapsed_ms': elapsed * 1000
            }

            self.heartbeat_history.append(tick_record)

            # Keep only last 100 heartbeats
            if len(self.heartbeat_history) > 100:
                self.heartbeat_history.pop(0)

            # Callback
            if self.on_tick:
                self.on_tick(tick_record)

        except Exception as e:
            self._handle_error(e)

    def _apply_neuromodulation_decay(self) -> bool:
        """Apply homeostatic decay to neuromodulators"""
        try:
            planner = self.planner.planner  # HierarchicalPlanner

            if not planner.enable_neuromodulation or not planner.neuromodulation:
                return False

            # Apply decay
            planner.neuromodulation.apply_decay()

            return True
        except Exception as e:
            self._handle_error(e, context="neuromodulation_decay")
            return False

    def _update_temporal_memory(self) -> bool:
        """Monitor temporal memory health (patterns auto-update when events are added)"""
        try:
            planner = self.planner.planner  # HierarchicalPlanner

            if not planner.enable_temporal_memory or not planner.temporal_memory:
                return False

            # Temporal patterns are automatically updated when events are added via add_event()
            # Heartbeat just verifies the system is working
            stats = planner.temporal_memory.get_statistics()

            # Optional: Log statistics periodically
            if self.tick_count % 20 == 0 and stats.get('total_events', 0) > 0:
                print(f"[BrainHeartbeat] Temporal memory: {stats['total_events']} events, {stats.get('sequences_learned', 0)} sequences")

            return True
        except Exception as e:
            self._handle_error(e, context="temporal_memory_update")
            return False

    def _trigger_dream_mode(self) -> bool:
        """Trigger dream mode consolidation"""
        try:
            planner = self.planner.planner  # HierarchicalPlanner

            if not planner.enable_dream_mode or not planner.dream_mode:
                return False

            if not planner.enable_memory or not planner.memory:
                return False

            # Get episodic memories
            episodic_memories = planner.memory.episodic.memories

            if not episodic_memories:
                return False

            # Run dream cycle (5 dreams per cycle)
            dreams = planner.dream_mode.dream_cycle(
                episodic_memories=episodic_memories,
                possible_decisions=planner.layer3.intervention_types,
                num_dreams=5
            )

            self.total_dreams += len(dreams)

            # === CTM DREAM TRAINING (P2.22) ===
            # Every N dream cycles, train a specialized CTM domain
            if self._ctm_trainer and self.total_dreams % self._ctm_training_interval == 0:
                self._run_ctm_dream_training()

            # === RADIAL SLEEP TRAINING (Phase 3) ===
            # After episodic consolidation, train RadialAttentionNetwork
            # on experience buffer if the agent loop has a radial trainer.
            radial_trained = self._run_radial_dream_training()

            # Callback
            if self.on_dream:
                self.on_dream({
                    'num_dreams': len(dreams),
                    'total_dreams': self.total_dreams,
                    'idle_time': self.idle_time_seconds,
                    'ctm_training_cycle': self._ctm_training_cycle,
                    'radial_trained': radial_trained,
                })

            print(f"[BrainHeartbeat] Dream mode: {len(dreams)} dreams (total={self.total_dreams})")

            return True
        except Exception as e:
            self._handle_error(e, context="dream_mode")
            return False

    def _run_ctm_dream_training(self) -> bool:
        """
        Run one round of CTM dream training (P2.22).

        Cycles through domains: Logic -> Temporal -> Value -> Logic -> ...
        Uses lightweight training (5 epochs, small dataset) suitable for background.
        """
        if not self._ctm_trainer:
            return False

        try:
            from core.shared_enums import CTMDomain
            from core.dream_mode_ctm_trainer import TrainingConfig

            # Cycle through domains
            domain_cycle = [CTMDomain.LOGIC, CTMDomain.TEMPORAL, CTMDomain.VALUE]
            domain = domain_cycle[self._ctm_training_cycle % len(domain_cycle)]
            self._ctm_training_cycle += 1

            # Lightweight training config for background operation
            config = TrainingConfig(
                domain=domain,
                num_epochs=5,
                batch_size=16,
                learning_rate=5e-5,
                target_module_routing=self._ctm_trainer._get_default_config(domain).target_module_routing,
                dataset_size=200,
                validation_split=0.2,
                checkpoint_interval=5,
            )

            print(f"[BrainHeartbeat] CTM dream training: {domain.value} (cycle {self._ctm_training_cycle})")

            result = self._ctm_trainer.train_domain_ctm(domain=domain, config=config)

            status = result.get('status', 'unknown')
            convergence = result.get('best_convergence', 0)
            print(f"[BrainHeartbeat] CTM training result: {status} (convergence={convergence:.3f})")

            return True
        except Exception as e:
            self._handle_error(e, context="ctm_dream_training")
            return False

    def _run_radial_dream_training(self) -> bool:
        """
        Run RadialSleepTrainer on the experience buffer (Phase 3).

        Accesses the agent loop via self.planner to run sleep training
        after episodic memory consolidation.  Sets SleepWake bridge to
        dream state, runs N training epochs, then registers EWC anchor.

        This complements AgentLoop._run_radial_dream_training() — the
        heartbeat pathway is triggered by idle time, while the agent
        loop pathway is triggered by homeostatic sleep pressure.
        """
        try:
            agent_loop = getattr(self.planner, 'agent_loop', None)
            if agent_loop is None:
                return False

            trainer = getattr(agent_loop, 'radial_trainer', None)
            buf = getattr(agent_loop, 'experience_buffer', None)
            if trainer is None or buf is None or len(buf) == 0:
                return False

            # Set dream bridge state (if agent loop isn't already dreaming)
            if hasattr(agent_loop, '_set_dream_bridge_state'):
                agent_loop._set_dream_bridge_state()

            # Run training epochs
            n_epochs = 3
            batch_size = min(32, len(buf))
            losses = []

            for epoch in range(n_epochs):
                avg_loss = trainer.train_epoch(batch_size=batch_size)
                losses.append(avg_loss)

            # EWC anchor
            trainer.register_ewc_anchor()

            # Restore bridge state
            if hasattr(agent_loop, '_restore_wake_bridge_state'):
                agent_loop._restore_wake_bridge_state()

            avg_loss_all = sum(losses) / max(len(losses), 1)
            print(
                f"[BrainHeartbeat] Radial dream training: "
                f"{n_epochs} epochs, avg_loss={avg_loss_all:.4f}, buffer={len(buf)}"
            )

            return True
        except Exception as e:
            self._handle_error(e, context="radial_dream_training")
            return False

    def _check_meta_learning(self) -> bool:
        """Perform meta-learning check"""
        try:
            planner = self.planner.planner  # HierarchicalPlanner

            if not planner.enable_meta_learning or not planner.meta_learner:
                return False

            # Get meta-learning statistics
            stats = planner.meta_learner.get_statistics()

            # Log statistics periodically
            if self.tick_count % 20 == 0:  # Every 20 ticks (10 minutes at 30s interval)
                print(f"[BrainHeartbeat] Meta-learning: {stats.get('total_adaptations', 0)} adaptations, Success rate: {planner.meta_learner.performance.get_success_rate():.1%}")

            return True
        except Exception as e:
            self._handle_error(e, context="meta_learning_check")
            return False

    def _monitor_health(self) -> Dict:
        """Monitor system health"""
        try:
            try:
                import psutil
                memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                cpu_percent = psutil.Process().cpu_percent(interval=0.1)
            except ImportError:
                # psutil not installed - use basic metrics
                memory_mb = 0.0
                cpu_percent = 0.0

            health = {
                'memory_mb': memory_mb,
                'cpu_percent': cpu_percent,
                'tick_count': self.tick_count,
                'total_predictions': self.planner.total_predictions,
                'total_feedback': self.planner.total_feedback,
                'error_count': len(self.errors),
                'status': 'healthy'
            }

            # Check for issues
            if memory_mb > 0 and memory_mb > 500:
                health['status'] = 'warning:high_memory'

            if cpu_percent > 0 and cpu_percent > 50:
                health['status'] = 'warning:high_cpu'

            if len(self.errors) > 10:
                health['status'] = 'warning:high_errors'

            return health
        except Exception as e:
            self._handle_error(e, context="health_monitoring")
            return {'status': 'error', 'error': str(e)}

    def _handle_error(self, error: Exception, context: str = "unknown"):
        """Handle errors during heartbeat"""
        error_record = {
            'timestamp': datetime.now().isoformat(),
            'context': context,
            'error': str(error),
            'tick_number': self.tick_count
        }

        self.errors.append(error_record)

        # Keep only last 50 errors
        if len(self.errors) > 50:
            self.errors.pop(0)

        # Callback
        if self.on_error:
            self.on_error(error_record)

        print(f"[BrainHeartbeat] Error in {context}: {error}")

    def mark_prediction(self):
        """Mark that a prediction was just made (resets idle timer)"""
        self.last_prediction_time = time.time()
        self.idle_time_seconds = 0.0

    def stop(self):
        """Stop the heartbeat thread"""
        self.running = False
        print(f"[BrainHeartbeat] Stopped after {self.tick_count} ticks")

    def get_state(self) -> Dict:
        """Get current heartbeat state"""
        planner = self.planner.planner  # HierarchicalPlanner

        # Get neuromodulator levels
        neuro_levels = None
        neuro_effects = None
        if planner.enable_neuromodulation and planner.neuromodulation:
            neuro_levels = {
                'dopamine': float(planner.neuromodulation.levels.dopamine),
                'serotonin': float(planner.neuromodulation.levels.serotonin),
                'norepinephrine': float(planner.neuromodulation.levels.norepinephrine),
                'state_description': planner.neuromodulation.get_state_description()
            }
            effects = planner.neuromodulation.compute_effects()
            neuro_effects = {
                'learning_rate_multiplier': float(effects.learning_rate_multiplier),
                'exploration_boost': float(effects.exploration_boost),
                'attention_focus_multiplier': float(effects.attention_focus_multiplier),
                'confidence_threshold_delta': float(effects.confidence_threshold_delta),
                'response_urgency': float(effects.response_urgency)
            }

        # Get meta-learning state
        meta_state = None
        if planner.enable_meta_learning and planner.meta_learner:
            stats = planner.meta_learner.get_statistics()
            meta_state = {
                'prediction_learning_rate': float(planner.meta_learner.meta_params.prediction_learning_rate),
                'attention_learning_rate': float(planner.meta_learner.meta_params.attention_learning_rate),
                'memory_learning_rate': float(planner.meta_learner.meta_params.memory_learning_rate),
                'exploration_rate': float(planner.meta_learner.meta_params.exploration_rate),
                'recent_success_rate': float(planner.meta_learner.performance.get_success_rate()),
                'total_adaptations': stats.get('total_adaptations', 0)
            }

        # Get dream state
        dream_state = None
        if planner.enable_dream_mode and planner.dream_mode:
            dream_stats = planner.dream_mode.get_statistics()
            dream_state = {
                'is_dreaming': False,  # Would be true during dream cycle
                'idle_time_seconds': self.idle_time_seconds,
                'total_dreams': self.total_dreams,
                'patterns_discovered': dream_stats.get('total_patterns', 0),
                'last_dream': None  # Would be timestamp of last dream
            }

        # Get temporal memory state
        temporal_state = None
        if planner.enable_temporal_memory and planner.temporal_memory:
            temporal_stats = planner.temporal_memory.get_statistics()
            temporal_state = {
                'total_events': temporal_stats.get('total_events', 0),
                'sequences_learned': temporal_stats.get('total_sequences', 0),
                'time_of_day': datetime.now().strftime('%H:%M'),
                'day_of_week': datetime.now().strftime('%A').lower()
            }

        # Get performance metrics
        performance = {
            'total_predictions': self.planner.total_predictions,
            'total_feedback': self.planner.total_feedback,
            'success_rate': self.planner._compute_recent_accuracy() if hasattr(self.planner, '_compute_recent_accuracy') else 0.0,
            'avg_confidence': self.planner._compute_avg_confidence() if hasattr(self.planner, '_compute_avg_confidence') else 0.0
        }

        # Health
        health = self._monitor_health()

        # Get homeostatic state
        homeostatic_state = None
        if self._homeostatic:
            homeostatic_state = self._homeostatic.state.to_dict()

        # Get emotional state
        emotional_state = None
        if hasattr(self.planner, 'cognitive_loop') and self.planner.cognitive_loop:
            try:
                es = self.planner.cognitive_loop._emotional_system
                if es:
                    emotional_state = es.get_state_dict()
            except Exception:
                pass

        return {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': self.tick_count * self.config.interval_seconds,
            'tick_count': self.tick_count,
            'idle_time_seconds': self.idle_time_seconds,
            'state': 'idle' if self.idle_time_seconds > 60 else 'active',

            'neuromodulation': neuro_levels,
            'neuromodulation_effects': neuro_effects,
            'meta_learning': meta_state,
            'dream_state': dream_state,
            'temporal_memory': temporal_state,
            'homeostatic': homeostatic_state,
            'emotional': emotional_state,
            'performance': performance,
            'health': health,

            'config': {
                'interval_seconds': self.config.interval_seconds,
                'enable_dream_mode': self.config.enable_dream_mode,
                'dream_idle_threshold_seconds': self.config.dream_idle_threshold_seconds
            },

            'recent_heartbeats': self.heartbeat_history[-10:],  # Last 10 ticks
            'recent_errors': self.errors[-5:]  # Last 5 errors
        }


if __name__ == "__main__":
    print("=" * 70)
    print("BRAIN HEARTBEAT - Autonomous Background Processing")
    print("=" * 70)
    print()
    print("This module provides continuous background activity for the brain:")
    print("  1. Neuromodulation decay (homeostasis)")
    print("  2. Temporal memory updates")
    print("  3. Dream mode consolidation (when idle)")
    print("  4. Meta-learning checks")
    print("  5. Health monitoring")
    print()
    print("Usage:")
    print("  from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig")
    print("  from production.production_planner import ProductionPlanner")
    print()
    print("  # Initialize planner")
    print("  planner = ProductionPlanner(...)")
    print()
    print("  # Start heartbeat")
    print("  heartbeat = BrainHeartbeat(planner, config=BrainHeartbeatConfig())")
    print("  heartbeat.start()")
    print()
    print("  # Make predictions...")
    print("  result = planner.predict('Deploy with Docker')")
    print("  heartbeat.mark_prediction()  # Reset idle timer")
    print()
    print("  # Get brain state")
    print("  state = heartbeat.get_state()")
    print()
    print("  # Stop heartbeat")
    print("  heartbeat.stop()")
    print()
    print("=" * 70)

"""
Unified Brain Service
=====================

Central brain instance shared across all services.

This service provides a single ProductionPlanner instance that:
- Dashboard (port 5000) uses for visualization
- Production API (port 5001) uses for predictions
- Swarm (port 5002) uses for cognitive guidance
- Memory API (port 8001) provides storage backend

Architecture:
- Single source of truth for brain state
- Unified memory and learning across all services
- Coordinated feedback loops
- Real-time state synchronization

Usage:
    # Start unified brain service
    python production/unified_brain_service.py

    # Then start other services:
    python web/brain_dashboard_server.py
    python production/api_server.py
    python web/autonomous_swarm_server.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import logging
import signal
import atexit
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import threading
import json

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from production.production_planner import ProductionPlanner
from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig
from core.brain_frequency_controller import BrainFrequencyController, FrequencyMode, FrequencyMixer
from core.multi_ctm_ensemble import MultiCTMEnsemble, CTMDomain
from core.dream_mode_ctm_trainer import DreamModeCTMTrainer, TrainingConfig

# Layer 4 Temporal CTM endpoints (Phase 5)
try:
    from production.layer4_endpoints import layer4_bp, LAYER4_AVAILABLE, get_layer4_features
    LAYER4_ENDPOINTS_AVAILABLE = True
except ImportError as e:
    print(f"[UNIFIED BRAIN] Layer 4 endpoints not available: {e}")
    LAYER4_ENDPOINTS_AVAILABLE = False
    layer4_bp = None

# Brain Snapshot/Restore (Phase 7: P7.100)
try:
    from core.brain_snapshot import BrainSnapshot
    SNAPSHOT_AVAILABLE = True
except ImportError:
    SNAPSHOT_AVAILABLE = False
    print("[UNIFIED BRAIN] Brain snapshot module not available")

# Event Bus (Phase 7: P7.99)
try:
    from core.event_bus import get_event_bus, BrainTopics, EventPriority
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False
    print("[UNIFIED BRAIN] Event bus module not available")

# Agent Loop (V2 Phase 3: P3.31-33)
try:
    from core.agent_loop import AgentLoop, AgentLoopConfig, TaskPriority
    AGENT_LOOP_AVAILABLE = True
except ImportError:
    AGENT_LOOP_AVAILABLE = False
    print("[UNIFIED BRAIN] Agent loop module not available")

# Global CTM ensemble for GAMMA mode coordination
ctm_ensemble: Optional[MultiCTMEnsemble] = None
ctm_active_task: Optional[str] = None

# Global training state (protected by training_lock)
ctm_trainer: Optional[DreamModeCTMTrainer] = None
training_thread: Optional[threading.Thread] = None
training_stop_flag = False
training_lock = threading.Lock()

load_dotenv()

app = Flask(__name__)
CORS(app)

# Register Layer 4 Blueprint (Phase 5)
if LAYER4_ENDPOINTS_AVAILABLE and layer4_bp is not None:
    app.register_blueprint(layer4_bp)
    print("[UNIFIED BRAIN] Layer 4 endpoints registered at /layer4/*")

# Global unified brain instance
unified_brain: Optional[ProductionPlanner] = None
brain_heartbeat: Optional[BrainHeartbeat] = None
brain_snapshot_mgr: Optional['BrainSnapshot'] = None
brain_lock = threading.Lock()
shutdown_in_progress = False

# Global frequency controller instance
frequency_controller: Optional[BrainFrequencyController] = None
frequency_mixer: Optional[FrequencyMixer] = None

# Track active connections from services
connected_services = {
    'dashboard': {'connected': False, 'last_ping': None},
    'api': {'connected': False, 'last_ping': None},
    'swarm': {'connected': False, 'last_ping': None}
}


def get_ctm_ensemble() -> MultiCTMEnsemble:
    """Get or create the CTM ensemble for GAMMA mode reasoning"""
    global ctm_ensemble

    if ctm_ensemble is None:
        with brain_lock:
            if ctm_ensemble is None:
                print("[UNIFIED BRAIN] Initializing Multi-CTM Ensemble...")
                ctm_ensemble = MultiCTMEnsemble(
                    max_concurrent_per_ctm=2,
                    consciousness_threshold=0.85,
                    max_reasoning_steps=50,
                    enable_logic_ctm=True,
                    enable_temporal_ctm=True,
                    enable_value_ctm=True
                )
                print("[UNIFIED BRAIN] [OK] Multi-CTM Ensemble initialized (4 domains)")

    return ctm_ensemble


def gamma_mode_handler(mode: FrequencyMode):
    """Handler called when GAMMA mode is activated - triggers CTM reasoning"""
    global ctm_active_task

    print(f"[FREQUENCY-CTM] GAMMA mode activated - CTM reasoning enabled")

    # If there's a pending task, start CTM reasoning
    if ctm_active_task:
        ensemble = get_ctm_ensemble()
        task_id = ensemble.reason_async(
            task=ctm_active_task,
            brain_state={'modality_activations': {}},
            max_steps=50
        )
        print(f"[FREQUENCY-CTM] Started CTM reasoning for: {ctm_active_task[:50]}... (task_id: {task_id})")


def delta_mode_handler(mode: FrequencyMode):
    """Handler called when DELTA mode is activated - training/consolidation"""
    print(f"[FREQUENCY-DELTA] DELTA mode activated - Learning/consolidation mode")

    # Check if Layer 4 training is active
    if LAYER4_ENDPOINTS_AVAILABLE:
        from production.layer4_endpoints import layer4_training_thread
        if layer4_training_thread and layer4_training_thread.is_alive():
            print(f"[FREQUENCY-DELTA] Layer 4 training is active")


def get_frequency_controller() -> BrainFrequencyController:
    """Get or create the frequency controller instance"""
    global frequency_controller, frequency_mixer

    if frequency_controller is None:
        with brain_lock:
            if frequency_controller is None:
                print("[UNIFIED BRAIN] Initializing Frequency Controller...")
                frequency_controller = BrainFrequencyController(
                    default_mode=FrequencyMode.ALPHA,
                    enable_auto_switch=True,
                    marker_capacity=1000
                )
                frequency_mixer = FrequencyMixer(frequency_controller)

                # Register GAMMA mode handler for CTM coordination
                frequency_controller.register_handler(FrequencyMode.GAMMA, gamma_mode_handler)
                # Register DELTA mode handler for training (Phase 5)
                frequency_controller.register_handler(FrequencyMode.DELTA, delta_mode_handler)
                print("[UNIFIED BRAIN] [OK] Frequency Controller initialized (default: ALPHA)")
                print("[UNIFIED BRAIN] [OK] GAMMA-CTM coordination enabled")
                print("[UNIFIED BRAIN] [OK] DELTA-Training coordination enabled")

    return frequency_controller


def get_unified_brain() -> ProductionPlanner:
    """Get or create the unified brain instance"""
    global unified_brain

    if unified_brain is None:
        with brain_lock:
            if unified_brain is None:
                print("\n[UNIFIED BRAIN] Initializing ProductionPlanner with LLM support...")

                enable_cognitive_loop = os.getenv("ENABLE_COGNITIVE_LOOP", "false").lower() == "true"

                unified_brain = ProductionPlanner(
                    session_log_dir="data/logs",
                    user_id="unified_brain",
                    openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
                    enable_continuous_learning=True,
                    enable_semantic_coherence=True,
                    embedding_type="hash",
                    enable_cognitive_loop=enable_cognitive_loop
                )

                # Wire frequency controller into cognitive loop
                if enable_cognitive_loop and unified_brain.cognitive_loop:
                    try:
                        freq_ctrl = get_frequency_controller()
                        unified_brain.cognitive_loop._frequency_controller = freq_ctrl
                    except Exception:
                        pass

                print("[UNIFIED BRAIN] [OK] LLM-powered brain initialized")
                print("[UNIFIED BRAIN] [OK] Continuous learning enabled")
                print("[UNIFIED BRAIN] [OK] Semantic coherence enabled")
                if enable_cognitive_loop:
                    print("[UNIFIED BRAIN] [OK] Cognitive loop ENABLED")

                # Auto-start brain heartbeat for autonomous background processing
                _start_heartbeat(unified_brain)

                # Initialize snapshot manager (P7.100)
                _init_snapshot_manager()

                # Initialize event bus and emit startup event (P7.99)
                _init_event_bus()

                # Auto-start agent loop if enabled (V2 P3.31-33)
                _start_agent_loop(unified_brain)

                print("[UNIFIED BRAIN] Ready to serve all services!")

    return unified_brain


def _start_heartbeat(brain: ProductionPlanner):
    """Start brain heartbeat for autonomous background processing."""
    global brain_heartbeat

    if brain_heartbeat is not None and brain_heartbeat.is_alive():
        return  # Already running

    try:
        config = BrainHeartbeatConfig(
            interval_seconds=30.0,
            enable_dream_mode=True,
            dream_idle_threshold_seconds=300.0,
            enable_temporal_updates=True,
            enable_neuromodulation_decay=True,
            enable_meta_learning_checks=True,
            enable_health_monitoring=True
        )

        brain_heartbeat = BrainHeartbeat(
            planner=brain,
            config=config
        )
        brain_heartbeat.daemon = True  # Dies with main thread
        brain_heartbeat.start()
        print("[UNIFIED BRAIN] [OK] Brain heartbeat AUTO-STARTED (30s interval)")
        print("[UNIFIED BRAIN]      Neuromodulation decay, temporal updates, dream mode enabled")
    except Exception as e:
        print(f"[UNIFIED BRAIN] [WARN] Brain heartbeat failed to start: {e}")


def _init_snapshot_manager():
    """Initialize the brain snapshot manager (P7.100)."""
    global brain_snapshot_mgr
    if SNAPSHOT_AVAILABLE and brain_snapshot_mgr is None:
        try:
            brain_snapshot_mgr = BrainSnapshot(snapshot_dir="data/snapshots")
            print("[UNIFIED BRAIN] [OK] Brain snapshot manager initialized")
        except Exception as e:
            print(f"[UNIFIED BRAIN] [WARN] Snapshot manager failed: {e}")


def _init_event_bus():
    """Initialize the event bus and emit startup event (P7.99)."""
    if EVENT_BUS_AVAILABLE:
        try:
            bus = get_event_bus()
            bus.emit(
                topic=BrainTopics.SYSTEM_STARTUP,
                data={'service': 'unified_brain', 'port': int(os.environ.get('BRAIN_PORT', 5003))},
                source='unified_brain_service',
                priority=EventPriority.HIGH
            )
            print("[UNIFIED BRAIN] [OK] Event bus initialized")
        except Exception as e:
            print(f"[UNIFIED BRAIN] [WARN] Event bus failed: {e}")


def _start_agent_loop(brain: ProductionPlanner):
    """Start the autonomous agent loop if enabled (V2 P3.31-33)."""
    if not AGENT_LOOP_AVAILABLE:
        return

    enable_agent_loop = os.getenv("ENABLE_AGENT_LOOP", "false").lower() == "true"
    if not enable_agent_loop:
        return

    if not hasattr(brain, 'agent_loop') or brain.agent_loop is None:
        return

    try:
        agent_loop = brain.agent_loop

        # Wire event bus for sensor events
        if EVENT_BUS_AVAILABLE:
            try:
                bus = get_event_bus()
                agent_loop.event_bus = bus
                print("[UNIFIED BRAIN] [OK] Agent loop event bus wired")
            except Exception:
                pass

        # Start the agent loop background thread
        agent_loop.start()
        print("[UNIFIED BRAIN] [OK] Agent loop AUTO-STARTED (autonomous mode)")
    except Exception as e:
        print(f"[UNIFIED BRAIN] [WARN] Agent loop failed to start: {e}")


def graceful_shutdown(signum=None, frame=None):
    """
    Graceful shutdown handler (P7.96).

    Stops heartbeat, persists memory, saves final snapshot, emits shutdown event.
    """
    global shutdown_in_progress
    if shutdown_in_progress:
        return
    shutdown_in_progress = True

    sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
    print(f"\n[SHUTDOWN] Received {sig_name} - starting graceful shutdown...")

    # 0. Stop agent loop
    if unified_brain is not None and hasattr(unified_brain, 'agent_loop') and unified_brain.agent_loop:
        try:
            unified_brain.agent_loop.stop()
            print("[SHUTDOWN] [OK] Agent loop stopped")
        except Exception as e:
            print(f"[SHUTDOWN] [WARN] Agent loop stop failed: {e}")

    # 1. Stop heartbeat
    if brain_heartbeat is not None:
        try:
            brain_heartbeat.stop()
            print("[SHUTDOWN] [OK] Brain heartbeat stopped")
        except Exception as e:
            print(f"[SHUTDOWN] [WARN] Heartbeat stop failed: {e}")

    # 2. Save final snapshot
    if brain_snapshot_mgr is not None and unified_brain is not None:
        try:
            filepath = brain_snapshot_mgr.save(unified_brain, filename="brain_snapshot_shutdown.json")
            print(f"[SHUTDOWN] [OK] Final snapshot saved: {filepath}")
        except Exception as e:
            print(f"[SHUTDOWN] [WARN] Snapshot save failed: {e}")

    # 3. Persist memory
    if unified_brain is not None:
        try:
            if hasattr(unified_brain, 'planner') and hasattr(unified_brain.planner, 'memory'):
                memory = unified_brain.planner.memory
                if hasattr(memory, 'save_to_disk'):
                    memory.save_to_disk()
                    print("[SHUTDOWN] [OK] Memory persisted to disk")
        except Exception as e:
            print(f"[SHUTDOWN] [WARN] Memory persist failed: {e}")

    # 4. Emit shutdown event
    if EVENT_BUS_AVAILABLE:
        try:
            bus = get_event_bus()
            bus.emit(
                topic=BrainTopics.SYSTEM_SHUTDOWN,
                data={'reason': sig_name, 'timestamp': datetime.now().isoformat()},
                source='unified_brain_service',
                priority=EventPriority.CRITICAL
            )
            print("[SHUTDOWN] [OK] Shutdown event emitted")
        except Exception:
            pass

    # 5. Stop training threads
    global training_stop_flag
    training_stop_flag = True

    print("[SHUTDOWN] Graceful shutdown complete.")


# Register shutdown handlers
signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)
atexit.register(lambda: graceful_shutdown(signal.SIGTERM))


@app.route('/health')
def health():
    """Health check"""
    brain = get_unified_brain()

    # Check if LLM is enabled
    llm_enabled = False
    if hasattr(brain, 'planner') and hasattr(brain.planner, 'layer2'):
        layer2 = brain.planner.layer2
        llm_enabled = hasattr(layer2, 'meta_router') and hasattr(layer2.meta_router, 'multi_llm_router') and layer2.meta_router.multi_llm_router is not None

    # Check agent loop status
    agent_loop_active = False
    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        agent_loop_active = brain.agent_loop._running

    return jsonify({
        'status': 'operational',
        'service': 'unified_brain',
        'brain_type': 'ProductionPlanner',
        'llm_enabled': llm_enabled,
        'cognitive_loop_enabled': brain.cognitive_loop is not None if hasattr(brain, 'cognitive_loop') else False,
        'agent_loop_enabled': hasattr(brain, 'agent_loop') and brain.agent_loop is not None,
        'agent_loop_active': agent_loop_active,
        'continuous_learning': brain.enable_continuous_learning if hasattr(brain, 'enable_continuous_learning') else False,
        'heartbeat_active': brain_heartbeat is not None and brain_heartbeat.is_alive(),
        'connected_services': connected_services
    })


@app.route('/subsystem_health')
def subsystem_health():
    """Enhanced per-subsystem health with circuit breaker status (P4.54)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'registry'):
            return jsonify(brain.registry.get_health_report())
        return jsonify({'error': 'registry not available', 'overall_health': 'unknown'})
    except Exception as e:
        return jsonify({'error': str(e), 'overall_health': 'red'}), 500


@app.route('/subsystem_registry')
def subsystem_registry():
    """Full subsystem registry state including dependency graph (P4.51)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'registry'):
            return jsonify(brain.registry.to_dict())
        return jsonify({'error': 'registry not available'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics')
def get_metrics():
    """Prometheus-compatible metrics endpoint (P4.61)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'metrics'):
            return brain.metrics.to_prometheus(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
        return 'No metrics available\n', 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f'# Error: {e}\n', 500, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/metrics_json')
def get_metrics_json():
    """JSON metrics endpoint (P4.61)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'metrics'):
            return jsonify(brain.metrics.to_dict())
        return jsonify({'error': 'metrics not available'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/audit_trail')
def get_audit_trail():
    """Prediction audit trail (P4.62)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'audit_log'):
            return jsonify(brain.audit_log.to_dict())
        return jsonify({'error': 'audit log not available'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/loop_traces')
def get_loop_traces():
    """Cognitive loop tracing data (P4.63)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'loop_tracer'):
            return jsonify(brain.loop_tracer.to_dict())
        return jsonify({'error': 'loop tracer not available'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/error_rates')
def get_error_rates():
    """Per-subsystem error rates (P4.64)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'error_tracker'):
            return jsonify(brain.error_tracker.to_dict())
        return jsonify({'error': 'error tracker not available'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/brain_heatmap')
def get_brain_heatmap():
    """Brain gate/modality activity heatmap (P4.65)"""
    try:
        brain = get_unified_brain()
        if hasattr(brain, 'activity_heatmap'):
            return jsonify(brain.activity_heatmap.to_dict())
        return jsonify({'error': 'heatmap not available'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cognitive_loop_state')
def get_cognitive_loop_state():
    """Get current cognitive loop state for dashboard visualization"""
    brain = get_unified_brain()
    if hasattr(brain, 'cognitive_loop') and brain.cognitive_loop:
        return jsonify({
            'success': True,
            'enabled': True,
            'state': brain.cognitive_loop.get_loop_state()
        })
    return jsonify({
        'success': True,
        'enabled': False,
        'state': None
    })


@app.route('/agent_loop_state')
def get_agent_loop_state():
    """Get autonomous agent loop state (V2 P3.31-33)."""
    brain = get_unified_brain()
    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        return jsonify({
            'success': True,
            'enabled': True,
            'state': brain.agent_loop.get_state()
        })
    return jsonify({
        'success': True,
        'enabled': False,
        'state': None
    })


@app.route('/agent_loop/submit', methods=['POST'])
def agent_loop_submit():
    """Submit a task to the agent loop."""
    brain = get_unified_brain()
    if not hasattr(brain, 'agent_loop') or not brain.agent_loop:
        return jsonify({'error': 'Agent loop not enabled'}), 503

    data = request.json or {}
    task_desc = data.get('task', '')
    is_user_request = data.get('user_request', False)
    priority = data.get('priority', 'self_initiated')

    if not task_desc:
        return jsonify({'error': 'No task provided'}), 400

    try:
        if is_user_request:
            task_id = brain.agent_loop.submit_user_request(task_desc)
        else:
            # Map priority string to TaskPriority enum
            if AGENT_LOOP_AVAILABLE:
                prio_map = {
                    'user_request': TaskPriority.USER_REQUEST,
                    'alarm': TaskPriority.ALARM,
                    'self_initiated': TaskPriority.SELF_INITIATED,
                    'background': TaskPriority.BACKGROUND,
                }
                prio = prio_map.get(priority, TaskPriority.SELF_INITIATED)
            else:
                prio = None  # Should not reach here
            task_id = brain.agent_loop.submit_task(task_desc, priority=prio)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Task submitted: {task_desc[:80]}...'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/heartbeat_status')
def heartbeat_status():
    """Get brain heartbeat status"""
    if brain_heartbeat and brain_heartbeat.is_alive():
        stats = brain_heartbeat.get_stats() if hasattr(brain_heartbeat, 'get_stats') else {}
        return jsonify({
            'active': True,
            'tick_count': getattr(brain_heartbeat, 'tick_count', 0),
            'stats': stats
        })
    return jsonify({'active': False})


@app.route('/emotional_state')
def emotional_state():
    """Get emotional system state."""
    brain = get_unified_brain()
    if brain.cognitive_loop and hasattr(brain.cognitive_loop, '_emotional_system') and brain.cognitive_loop._emotional_system:
        try:
            return jsonify({
                'enabled': True,
                'state': brain.cognitive_loop._emotional_system.get_state_dict()
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False, 'state': None})


@app.route('/homeostatic_state')
def homeostatic_state():
    """Get homeostatic regulation state."""
    brain = get_unified_brain()
    if brain.cognitive_loop and hasattr(brain.cognitive_loop, '_homeostatic') and brain.cognitive_loop._homeostatic:
        try:
            h = brain.cognitive_loop._homeostatic
            return jsonify({
                'enabled': True,
                'state': {
                    'energy': h.state.energy,
                    'fatigue': h.state.fatigue,
                    'stress': h.state.stress,
                    'allostatic_load': h.state.allostatic_load,
                    'sleep_pressure': h.state.sleep_pressure,
                    'performance_factor': h.get_performance_factor(),
                    'temperature_adjustment': h.get_temperature_adjustment(),
                    'attention_degradation': h.get_attention_degradation(),
                    'should_dream': h.should_trigger_dream(),
                }
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False, 'state': None})


@app.route('/memory_state')
def memory_state():
    """Get memory system state."""
    brain = get_unified_brain()
    planner = brain.planner
    if hasattr(planner, 'memory') and planner.memory:
        try:
            mem = planner.memory
            # Get working memory stats directly (don't call get_context with wrong args)
            working_size = len(mem.working) if hasattr(mem, 'working') else 0
            episodic_size = len(mem.episodic) if hasattr(mem, 'episodic') else 0
            recent_tasks = []
            if hasattr(mem, 'working') and hasattr(mem.working, 'get_recent'):
                recent = mem.working.get_recent(n=5)
                recent_tasks = [e.to_dict() for e in recent]
            success_rate = None
            if hasattr(mem, 'working') and hasattr(mem.working, 'get_success_rate'):
                success_rate = mem.working.get_success_rate(last_n=10)
            return jsonify({
                'enabled': True,
                'state': {
                    'working_memory_size': working_size,
                    'episodic_memory_size': episodic_size,
                    'recent_tasks': recent_tasks,
                    'recent_success_rate': success_rate,
                }
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False, 'state': None})


@app.route('/sensory_extract', methods=['POST'])
def sensory_extract():
    """Extract sensory features from text (for dashboard/debugging)."""
    brain = get_unified_brain()
    if brain.sensory_preprocessor:
        try:
            data = request.json or {}
            text = data.get('text', '')
            features = brain.sensory_preprocessor.extract(text)
            return jsonify({
                'enabled': True,
                'features': {
                    'detected_intent': features.detected_intent,
                    'detected_domain': features.detected_domain,
                    'overall_complexity': round(features.overall_complexity, 3),
                    'overall_urgency': round(features.overall_urgency, 3),
                    'overall_risk': round(features.overall_risk, 3),
                }
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False})


@app.route('/goal_graph_state')
def goal_graph_state():
    """Get goal graph state from cognitive loop."""
    brain = get_unified_brain()
    planner = brain.planner
    if hasattr(planner, 'goal_graph') and planner.goal_graph:
        try:
            goals = planner.goal_graph.get_all_goals() if hasattr(planner.goal_graph, 'get_all_goals') else []
            active = [g for g in goals if getattr(g, 'status', '') == 'active'] if goals else []
            return jsonify({
                'enabled': True,
                'state': {
                    'total_goals': len(goals),
                    'active_goals': len(active),
                    'goals': [
                        {
                            'id': getattr(g, 'id', str(i)),
                            'description': getattr(g, 'description', ''),
                            'status': getattr(g, 'status', 'unknown'),
                            'priority': getattr(g, 'priority', 0.5),
                        }
                        for i, g in enumerate(goals[:10])  # Limit to 10
                    ]
                }
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False, 'state': None})


@app.route('/neuromodulation_state')
def neuromodulation_state():
    """Get neuromodulation system state (dopamine, serotonin, norepinephrine)."""
    brain = get_unified_brain()
    planner = brain.planner
    if getattr(planner, 'enable_neuromodulation', False) and getattr(planner, 'neuromodulation', None):
        try:
            levels = planner.neuromodulation.levels
            effects = planner.neuromodulation.compute_effects()
            return jsonify({
                'enabled': True,
                'state': {
                    'total_updates': planner.neuromodulation.total_updates,
                    'current_levels': levels.to_dict(),
                    'current_state': planner.neuromodulation.get_state_description(),
                    'current_effects': effects.to_dict(),
                    'expected_reward': float(planner.neuromodulation.expected_reward),
                }
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False, 'state': None})


@app.route('/consciousness_state')
def consciousness_state():
    """Get consciousness metrics state (awareness, integration, global workspace)."""
    brain = get_unified_brain()
    planner = brain.planner
    if getattr(planner, 'enable_consciousness', False) and getattr(planner, 'consciousness', None):
        try:
            cs = planner.consciousness.current_state
            state_data = {
                'total_states_tracked': planner.consciousness.total_states_tracked,
                'total_assessments': planner.consciousness.total_assessments,
                'self_awareness_events': planner.consciousness.self_awareness_events,
                'known_unknowns_count': len(planner.consciousness.known_unknowns),
                'detected_biases_count': len(planner.consciousness.detected_biases),
            }
            if cs:
                state_data['current_state'] = cs.to_dict()
            else:
                state_data['current_state'] = None
            return jsonify({
                'enabled': True,
                'state': state_data
            })
        except (AttributeError, TypeError) as e:
            return jsonify({'enabled': True, 'error': str(e)})
    return jsonify({'enabled': False, 'state': None})


@app.route('/register', methods=['POST'])
def register_service():
    """Register a service connection"""
    data = request.json
    service_name = data.get('service_name')

    if service_name in connected_services:
        connected_services[service_name]['connected'] = True
        connected_services[service_name]['last_ping'] = datetime.now().isoformat()

        print(f"[UNIFIED BRAIN] Service '{service_name}' connected")

        return jsonify({
            'success': True,
            'message': f'Service {service_name} registered',
            'brain_ready': True
        })

    return jsonify({
        'success': False,
        'message': f'Unknown service: {service_name}'
    }), 400


@app.route('/predict', methods=['POST'])
def predict():
    """Make a prediction using the unified brain"""
    data = request.json
    task = data.get('task', '')
    service_name = data.get('service_name', 'unknown')

    if not task:
        return jsonify({'error': 'No task provided'}), 400

    brain = get_unified_brain()

    print(f"[UNIFIED BRAIN] Prediction request from '{service_name}': {task[:50]}...")

    try:
        with brain_lock:
            result = brain.predict(task)

        print(f"[UNIFIED BRAIN] Prediction complete: {result['prediction']['primary_action']} (confidence: {result['prediction'].get('confidence', 0.0):.2f})")

        return jsonify({
            'success': True,
            'result': result,
            'service_name': service_name
        })

    except Exception as e:
        print(f"[UNIFIED BRAIN] Prediction error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/predict_batch', methods=['POST'])
def predict_batch():
    """Batch prediction for multiple tasks (P4.58)"""
    data = request.json
    tasks = data.get('tasks', [])

    if not tasks or not isinstance(tasks, list):
        return jsonify({'error': 'No tasks provided. Send {"tasks": ["task1", "task2"]}'}), 400

    if len(tasks) > 20:
        return jsonify({'error': 'Maximum 20 tasks per batch'}), 400

    brain = get_unified_brain()
    results = []

    for task_text in tasks:
        if not task_text or not isinstance(task_text, str):
            results.append({'error': 'Invalid task', 'task': str(task_text)})
            continue
        try:
            with brain_lock:
                result = brain.predict(task_text)
            results.append({'success': True, 'result': result})
        except Exception as e:
            results.append({'success': False, 'error': str(e), 'task': task_text[:100]})

    return jsonify({
        'success': True,
        'total': len(tasks),
        'completed': sum(1 for r in results if r.get('success')),
        'failed': sum(1 for r in results if not r.get('success')),
        'results': results
    })


@app.route('/feedback', methods=['POST'])
def submit_feedback():
    """Submit feedback to the unified brain"""
    data = request.json
    task = data.get('task', '')
    prediction = data.get('prediction', {})
    success = data.get('success', True)
    user_rating = data.get('user_rating', 0.5)
    execution_time_ms = data.get('execution_time_ms')
    service_name = data.get('service_name', 'unknown')

    if not task or not prediction:
        return jsonify({'error': 'Missing task or prediction'}), 400

    brain = get_unified_brain()

    print(f"[UNIFIED BRAIN] Feedback from '{service_name}': success={success}, rating={user_rating}")

    try:
        with brain_lock:
            brain.submit_feedback(
                task=task,
                prediction=prediction,
                success=success,
                user_rating=user_rating,
                execution_time_ms=execution_time_ms
            )

        print("[UNIFIED BRAIN] Feedback submitted, brain updated")

        return jsonify({
            'success': True,
            'message': 'Feedback submitted'
        })

    except Exception as e:
        print(f"[UNIFIED BRAIN] Feedback error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/statistics')
def get_statistics():
    """Get brain statistics"""
    brain = get_unified_brain()

    try:
        stats = brain.get_statistics()

        return jsonify({
            'success': True,
            'statistics': stats
        })

    except Exception as e:
        print(f"[UNIFIED BRAIN] Statistics error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/brain_state')
def get_brain_state():
    """Get current brain state for visualization"""
    brain = get_unified_brain()

    try:
        # Get state from planner
        state = {
            'total_predictions': brain.planner.layer2.total_predictions if hasattr(brain, 'planner') and hasattr(brain.planner, 'layer2') else 0,
            'routing_matrix': brain.planner.layer2.routing_matrix.tolist() if hasattr(brain, 'planner') and hasattr(brain.planner, 'layer2') and hasattr(brain.planner.layer2, 'routing_matrix') else None,
            'learning_enabled': brain.enable_continuous_learning if hasattr(brain, 'enable_continuous_learning') else False,
            'llm_enabled': False
        }

        # Check LLM status safely
        if hasattr(brain, 'planner') and hasattr(brain.planner, 'layer2'):
            layer2 = brain.planner.layer2
            if hasattr(layer2, 'meta_router') and hasattr(layer2.meta_router, 'multi_llm_router'):
                state['llm_enabled'] = layer2.meta_router.multi_llm_router is not None

        return jsonify({
            'success': True,
            'state': state
        })

    except Exception as e:
        print(f"[UNIFIED BRAIN] Brain state error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/feature_call', methods=['POST'])
def feature_call():
    """
    Call a specific brain feature as a tool.

    This is the endpoint for agents to invoke brain features.

    Available features:
    - memory_context: Get memory context for task
    - attention_state: Get attention focus
    - predictive_coding: Get prediction errors and curiosity
    - consciousness_metrics: Get awareness and workspace state
    - active_inference: Generate clarifying questions
    - compositional_reasoning: Break down task composition
    - tool_recommendations: Get tool suggestions
    - meta_learning: Get learning rate adjustments
    - neuromodulation: Get neuromodulator states
    - temporal_memory: Get temporal patterns
    - semantic_coherence: Check semantic consistency
    - ctm_insights: Get deep reasoning insights
    - infinite_chat_context: Get chat history context
    """
    data = request.json
    feature_name = data.get('feature', '')
    task = data.get('task', '')
    context = data.get('context', {})
    service_name = data.get('service_name', 'unknown')

    if not feature_name or not task:
        return jsonify({'error': 'Missing feature or task'}), 400

    brain = get_unified_brain()

    print(f"[UNIFIED BRAIN] Feature call '{feature_name}' from '{service_name}': {task[:50]}...")

    try:
        # First get a prediction to generate brain state
        with brain_lock:
            result = brain.predict(task)

        # Extract requested feature from the result
        feature_map = {
            'memory_context': result.get('memory_context', {}),
            'attention_state': result.get('attention_state', {}),
            'predictive_coding': result.get('predictive_coding', {}),
            'consciousness_metrics': result.get('consciousness_metrics', {}),
            'active_inference': result.get('active_inference', {}),
            'compositional_reasoning': result.get('composition', {}),
            'tool_recommendations': result.get('tool_recommendations', {}),
            'meta_learning': result.get('meta_learning', {}),
            'neuromodulation': result.get('neuromodulation', {}),
            'temporal_memory': result.get('temporal_memory', {}),
            'semantic_coherence': result.get('semantic_coherence', {}),
            'ctm_insights': result.get('ctm_insights', {}),
            'infinite_chat_context': result.get('infinite_chat_context', {})
        }

        # Layer 4 features (Phase 5)
        if LAYER4_ENDPOINTS_AVAILABLE:
            layer4_features = get_layer4_features()
            feature_map['temporal_routing'] = layer4_features
            feature_map['regime_state'] = layer4_features.get('regime', 'UNKNOWN')
            feature_map['phase_dynamics'] = layer4_features.get('state_summary', {})

        if feature_name not in feature_map:
            return jsonify({
                'error': f'Unknown feature: {feature_name}',
                'available_features': list(feature_map.keys())
            }), 400

        feature_data = feature_map[feature_name]

        print(f"[UNIFIED BRAIN] Feature '{feature_name}' returned: {str(feature_data)[:100]}...")

        return jsonify({
            'success': True,
            'feature': feature_name,
            'data': feature_data,
            'task': task
        })

    except Exception as e:
        print(f"[UNIFIED BRAIN] Feature call error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/available_features')
def available_features():
    """List all brain features available as tool calls, reflecting actual subsystem availability."""
    brain = get_unified_brain()
    planner = brain.planner if brain else None

    # Build feature list dynamically based on what's actually enabled
    features = {}

    # Core features (always available if brain exists)
    if planner:
        features['memory_context'] = {
            'description': 'Working, declarative, procedural memory',
            'enabled': hasattr(planner, 'memory') and planner.memory is not None
        }
        features['attention_state'] = {
            'description': 'Selective attention and focus',
            'enabled': hasattr(planner, 'attention') and planner.attention is not None
        }
        features['predictive_coding'] = {
            'description': 'Prediction errors and curiosity',
            'enabled': hasattr(planner, 'predictive_coding') and planner.predictive_coding is not None
        }
        features['consciousness_metrics'] = {
            'description': 'Awareness and global workspace',
            'enabled': getattr(planner, 'enable_consciousness', False)
        }
        features['active_inference'] = {
            'description': 'Clarifying questions generation',
            'enabled': hasattr(planner, 'active_inference') and planner.active_inference is not None
        }
        features['compositional_reasoning'] = {
            'description': 'Task decomposition',
            'enabled': True  # Always available via Layer 1
        }
        features['tool_recommendations'] = {
            'description': 'Suggested tools for task',
            'enabled': True
        }
        features['meta_learning'] = {
            'description': 'Learning rate adjustments',
            'enabled': hasattr(planner, 'meta_learner') and planner.meta_learner is not None
        }
        features['neuromodulation'] = {
            'description': 'Dopamine, serotonin, noradrenaline',
            'enabled': getattr(planner, 'enable_neuromodulation', False)
        }
        features['temporal_memory'] = {
            'description': 'Temporal patterns and sequences',
            'enabled': hasattr(planner, 'temporal_memory') and planner.temporal_memory is not None
        }
        features['semantic_coherence'] = {
            'description': 'Semantic consistency checking',
            'enabled': getattr(planner, 'enable_semantic_coherence', False)
        }
        features['ctm_insights'] = {
            'description': 'Deep reasoning insights',
            'enabled': getattr(planner, 'enable_ctm_async', False)
        }
        features['infinite_chat_context'] = {
            'description': 'Chat history and context',
            'enabled': hasattr(planner, 'infinite_context') and planner.infinite_context is not None
        }

    # Layer 4 features (Phase 5)
    if LAYER4_ENDPOINTS_AVAILABLE:
        features['temporal_routing'] = {
            'description': 'Layer 4 temporal tool control state and statistics',
            'enabled': True
        }
        features['regime_state'] = {
            'description': 'Current operational regime (EXPLOIT/EXPLORE/REPAIR/DEADLOCK/TRANSITION)',
            'enabled': True
        }
        features['phase_dynamics'] = {
            'description': 'Oscillator phases and synchrony vectors (3 coupled oscillators)',
            'enabled': True
        }

    enabled_count = sum(1 for f in features.values() if f.get('enabled', False))

    return jsonify({
        'success': True,
        'features': features,
        'total_features': len(features),
        'enabled_features': enabled_count,
        'layer4_available': LAYER4_ENDPOINTS_AVAILABLE,
        'cognitive_loop_enabled': brain.cognitive_loop is not None if brain else False
    })


# =============================================================================
# FREQUENCY CONTROLLER ENDPOINTS
# =============================================================================

@app.route('/frequency_mode')
def get_frequency_mode():
    """Get current frequency mode state"""
    controller = get_frequency_controller()
    state = controller.get_state()

    return jsonify({
        'success': True,
        'frequency_state': state,
        'bands': controller.get_all_bands()
    })


@app.route('/set_frequency_mode', methods=['POST'])
def set_frequency_mode():
    """
    Set brain frequency mode

    Body:
        mode: 'delta', 'theta', 'alpha', 'beta', 'gamma'
        activation: 0.0 to 1.0 (optional, default 1.0)
        suppress_others: boolean (optional, default false)
    """
    data = request.json
    mode_name = data.get('mode', 'alpha')
    activation = data.get('activation', 1.0)
    suppress_others = data.get('suppress_others', False)

    try:
        mode = FrequencyMode(mode_name)
    except ValueError:
        return jsonify({
            'error': f'Unknown mode: {mode_name}',
            'available_modes': [m.value for m in FrequencyMode]
        }), 400

    controller = get_frequency_controller()
    result = controller.set_mode(mode, activation, suppress_others)

    print(f"[UNIFIED BRAIN] Frequency mode set to: {mode.value} (activation={activation})")

    return jsonify({
        'success': True,
        'result': result
    })


@app.route('/auto_frequency', methods=['POST'])
def auto_frequency_switch():
    """
    Auto-switch frequency mode based on context

    Body:
        task_type: 'planning', 'execute', 'reasoning', etc.
        urgency: 0.0 to 1.0
        complexity: 0.0 to 1.0
        requires_learning: boolean
        requires_action: boolean
    """
    data = request.json

    controller = get_frequency_controller()
    result = controller.auto_switch(data)

    if result.get('switched') or result.get('auto_switched'):
        print(f"[UNIFIED BRAIN] Auto-switched to: {result.get('current_dominant', 'unknown')}")

    return jsonify({
        'success': True,
        'result': result
    })


@app.route('/markers')
def get_markers():
    """Get recent markers from the marker system"""
    count = request.args.get('count', 20, type=int)

    controller = get_frequency_controller()
    markers = controller.get_recent_markers(count)

    return jsonify({
        'success': True,
        'markers': [{
            'marker_id': m.marker_id,
            'timestamp': m.timestamp.isoformat(),
            'mode': m.mode.value,
            'decision_point': m.decision_point,
            'alternatives': m.alternatives,
            'confidence': m.confidence,
            'visited': m.visited
        } for m in markers],
        'total': len(markers)
    })


@app.route('/set_marker', methods=['POST'])
def set_marker():
    """
    Set a memory marker at current decision point

    Body:
        decision_point: string description
        context: dict (optional)
        alternatives: list of alternative paths (optional)
        confidence: 0.0 to 1.0 (optional)
    """
    data = request.json
    decision_point = data.get('decision_point', 'Unnamed decision')
    context = data.get('context', {})
    alternatives = data.get('alternatives', [])
    confidence = data.get('confidence', 0.5)

    controller = get_frequency_controller()
    marker = controller.set_marker(
        decision_point=decision_point,
        context=context,
        alternatives=alternatives,
        confidence=confidence
    )

    return jsonify({
        'success': True,
        'marker': {
            'marker_id': marker.marker_id,
            'decision_point': marker.decision_point,
            'alternatives': marker.alternatives,
            'confidence': marker.confidence
        }
    })


@app.route('/jump_to_marker', methods=['POST'])
def jump_to_marker():
    """
    Jump back to a previous marker for recovery

    Body:
        marker_id: marker ID to jump to
    """
    data = request.json
    marker_id = data.get('marker_id')

    if not marker_id:
        return jsonify({'error': 'No marker_id provided'}), 400

    controller = get_frequency_controller()
    result = controller.jump_to_marker(marker_id)

    if result:
        return jsonify({
            'success': True,
            'jumped': True,
            'marker': result
        })
    else:
        return jsonify({
            'success': False,
            'jumped': False,
            'error': f'Marker {marker_id} not found'
        }), 404


# =============================================================================
# CTM COORDINATION ENDPOINTS (Frequency-CTM Integration)
# =============================================================================

@app.route('/ctm/trigger', methods=['POST'])
def trigger_ctm():
    """
    Trigger CTM reasoning by switching to GAMMA mode

    Body:
        task: Task description for CTM to reason about
        domain_hint: Optional domain hint ('spatial', 'logic', 'temporal', 'value')
        max_steps: Optional max reasoning steps (default 50)
    """
    global ctm_active_task

    data = request.json
    task = data.get('task', '')
    domain_hint = data.get('domain_hint')
    max_steps = data.get('max_steps', 50)

    if not task:
        return jsonify({'error': 'No task provided'}), 400

    # Store task for GAMMA handler
    ctm_active_task = task

    # Switch to GAMMA mode (this triggers the GAMMA handler)
    controller = get_frequency_controller()
    result = controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)

    # Also start CTM reasoning directly
    ensemble = get_ctm_ensemble()
    task_id = ensemble.reason_async(
        task=task,
        brain_state={'modality_activations': {}},
        max_steps=max_steps,
        domain_hint=domain_hint
    )

    return jsonify({
        'success': True,
        'task_id': task_id,
        'frequency_mode': 'gamma',
        'message': f'CTM reasoning started for: {task[:50]}...'
    })


@app.route('/ctm/result/<task_id>')
def get_ctm_result(task_id):
    """
    Get CTM reasoning result

    Path:
        task_id: Task ID from /ctm/trigger response
    Query:
        wait: 'true' to wait for completion (default 'false')
        timeout: Seconds to wait (default 30)
    """
    wait = request.args.get('wait', 'false').lower() == 'true'
    timeout = request.args.get('timeout', 30, type=int)

    ensemble = get_ctm_ensemble()
    result = ensemble.get_result(task_id, wait=wait, timeout=timeout)

    if result:
        return jsonify({
            'success': True,
            'completed': True,
            'primary_domain': result.primary_domain.value,
            'secondary_domains': [d.value for d in result.secondary_domains],
            'aggregated_insights': result.aggregated_insights,
            'elapsed_time': result.elapsed_time,
            'ctm_results': {
                domain.value: {
                    'status': ctm_result.status.value if ctm_result else 'not_run',
                    'consciousness': ctm_result.ctm_insight.final_consciousness if ctm_result and ctm_result.ctm_insight else None
                }
                for domain, ctm_result in result.ctm_results.items()
                if ctm_result
            }
        })
    else:
        return jsonify({
            'success': True,
            'completed': False,
            'message': 'CTM reasoning still in progress'
        })


@app.route('/ctm/status')
def get_ctm_status():
    """Get CTM ensemble status"""
    ensemble = get_ctm_ensemble()
    stats = ensemble.get_stats()

    controller = get_frequency_controller()
    freq_state = controller.get_state()

    return jsonify({
        'success': True,
        'ctm_stats': stats,
        'frequency_mode': freq_state['dominant_mode'],
        'gamma_active': freq_state['dominant_mode'] == 'gamma',
        'active_task': ctm_active_task
    })


@app.route('/ctm/complete', methods=['POST'])
def complete_ctm():
    """
    Complete CTM reasoning and return to ALPHA mode

    This should be called when CTM reasoning is done to switch
    back to normal routing mode.
    """
    global ctm_active_task

    ctm_active_task = None

    # Switch back to ALPHA mode
    controller = get_frequency_controller()
    result = controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)

    print("[FREQUENCY-CTM] CTM reasoning complete - returning to ALPHA mode")

    return jsonify({
        'success': True,
        'frequency_mode': 'alpha',
        'message': 'CTM reasoning complete, returned to ALPHA mode'
    })


@app.route('/ctm/collaborate', methods=['POST'])
def ctm_collaborate():
    """
    Run collaborative cross-CTM reasoning

    Sequential execution: Spatial → Logic → Temporal → Value
    Each CTM passes context to the next, enabling deeper reasoning.

    Body:
        task: Task description (required)
        max_steps: Max reasoning steps per CTM (default 30)
        execution_order: Custom order ['spatial', 'logic', 'temporal', 'value']
    """
    data = request.get_json() or {}
    task = data.get('task')

    if not task:
        return jsonify({'success': False, 'error': 'task is required'}), 400

    max_steps = data.get('max_steps', 30)
    execution_order_strs = data.get('execution_order')

    # Parse execution order
    execution_order = None
    if execution_order_strs:
        try:
            execution_order = [CTMDomain(d) for d in execution_order_strs]
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid domain in execution_order: {e}'
            }), 400

    # Switch to GAMMA mode for reasoning
    controller = get_frequency_controller()
    controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)

    try:
        ensemble = get_ctm_ensemble()

        # Get brain state
        brain = get_unified_brain()
        brain_state = {}
        if brain:
            with brain_lock:
                # Try to get brain state if method exists
                if hasattr(brain, 'get_brain_state'):
                    brain_state = brain.get_brain_state()
                elif hasattr(brain, 'hierarchical_planner'):
                    brain_state = {'modality_activations': {'tool_trace': 0.7}}

        # Run collaborative reasoning (synchronous)
        result = ensemble.reason_with_collaboration(
            task=task,
            brain_state=brain_state,
            max_steps=max_steps,
            execution_order=execution_order
        )

        # Build response
        response = {
            'success': True,
            'task_id': result.task_id,
            'task': result.task,
            'primary_domain': result.primary_domain.value,
            'secondary_domains': [d.value for d in result.secondary_domains],
            'aggregated_insights': result.aggregated_insights,
            'reasoning_chain': result.reasoning_chain,
            'elapsed_time': result.elapsed_time,
            'cross_ctm_context': None
        }

        # Include cross-CTM context if available
        if result.cross_ctm_context:
            ctx = result.cross_ctm_context
            response['cross_ctm_context'] = {
                'shared_insights': ctx.shared_insights,
                'constraints': ctx.constraints,
                'temporal_factors': ctx.temporal_factors,
                'value_assessments': ctx.value_assessments,
                'spatial_structures': ctx.spatial_structures,
                'execution_order': ctx.execution_order,
                'conflict_resolutions': ctx.conflict_resolutions
            }

        # Include per-CTM results
        ctm_results = {}
        for domain, ctm_result in result.ctm_results.items():
            if ctm_result and ctm_result.ctm_insight:
                insight = ctm_result.ctm_insight
                ctm_results[domain.value] = {
                    'status': ctm_result.status.value,
                    'consciousness': insight.final_consciousness,
                    'converged': insight.converged,
                    'strategy': insight.suggested_strategy,
                    'confidence': insight.confidence,
                    'steps': insight.reasoning_steps
                }
            elif ctm_result:
                ctm_results[domain.value] = {
                    'status': ctm_result.status.value
                }
        response['ctm_results'] = ctm_results

        return jsonify(response)

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        # Return to ALPHA mode
        controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)


# =============================================================================
# CTM TRAINING ENDPOINTS
# =============================================================================

def get_ctm_trainer() -> DreamModeCTMTrainer:
    """Get or create the CTM trainer"""
    global ctm_trainer

    if ctm_trainer is None:
        with brain_lock:
            if ctm_trainer is None:
                print("[UNIFIED BRAIN] Initializing CTM Trainer...")
                ctm_trainer = DreamModeCTMTrainer(
                    klotski_brain_path='learning_engine/klotski/neurosymbolic',
                    checkpoint_dir='data/ctm_checkpoints',
                    enable_cuda=False  # Can be changed to True if GPU available
                )
                print("[UNIFIED BRAIN] [OK] CTM Trainer initialized")

    return ctm_trainer


def training_worker(domain: CTMDomain, config: TrainingConfig):
    """Background worker for CTM training"""
    global training_stop_flag

    trainer = get_ctm_trainer()

    # Switch to DELTA mode for training (meta-learning)
    controller = get_frequency_controller()
    controller.set_mode(FrequencyMode.DELTA, activation=1.0, suppress_others=True)
    print(f"[CTM TRAINING] Switched to DELTA mode for {domain.value} training")

    try:
        trainer.train_domain(domain, config)
    except Exception as e:
        print(f"[CTM TRAINING] Error training {domain.value}: {e}")
    finally:
        # Return to ALPHA mode after training
        controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)
        print(f"[CTM TRAINING] Training complete, returned to ALPHA mode")


@app.route('/ctm/training/start', methods=['POST'])
def start_ctm_training():
    """
    Start CTM training for a specific domain

    Body:
        domain: 'logic', 'temporal', or 'value'
        epochs: Number of epochs (default 20)
        batch_size: Batch size (default 32)
        learning_rate: Learning rate (default 0.001)
        dataset_size: Training dataset size (default 200)
    """
    global training_thread, training_stop_flag

    if training_thread and training_thread.is_alive():
        return jsonify({
            'error': 'Training already in progress',
            'hint': 'Use /ctm/training/stop to stop current training'
        }), 400

    data = request.json
    domain_name = data.get('domain', 'logic')
    epochs = data.get('epochs', 20)
    batch_size = data.get('batch_size', 32)
    learning_rate = data.get('learning_rate', 0.001)
    dataset_size = data.get('dataset_size', 200)

    # Map domain name to CTMDomain enum
    domain_map = {
        'logic': CTMDomain.LOGIC,
        'temporal': CTMDomain.TEMPORAL,
        'value': CTMDomain.VALUE,
        'spatial': CTMDomain.SPATIAL
    }

    if domain_name not in domain_map:
        return jsonify({
            'error': f'Unknown domain: {domain_name}',
            'available': list(domain_map.keys())
        }), 400

    domain = domain_map[domain_name]

    # Target routing for each domain
    target_routing = {
        CTMDomain.LOGIC: {'LAN': 0.70, 'DLPFC': 0.20, 'ACC': 0.10},
        CTMDomain.TEMPORAL: {'AUD': 0.60, 'MTL': 0.25, 'DLPFC': 0.15},
        CTMDomain.VALUE: {'OFC': 0.70, 'ACC': 0.20, 'DLPFC': 0.10},
        CTMDomain.SPATIAL: {'SOM': 0.60, 'DLPFC': 0.25, 'MTL': 0.15}
    }

    config = TrainingConfig(
        domain=domain,
        num_epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        target_module_routing=target_routing[domain],
        dataset_size=dataset_size
    )

    # Start training in background thread
    training_stop_flag = False
    training_thread = threading.Thread(
        target=training_worker,
        args=(domain, config),
        daemon=True
    )
    training_thread.start()

    print(f"[CTM TRAINING] Started {domain.value} training: {epochs} epochs, {dataset_size} samples")

    return jsonify({
        'success': True,
        'domain': domain.value,
        'epochs': epochs,
        'dataset_size': dataset_size,
        'message': f'Training started for {domain.value} CTM'
    })


@app.route('/ctm/training/status')
def get_training_status():
    """Get current CTM training status"""
    global training_thread

    trainer = get_ctm_trainer()
    progress = trainer.get_training_progress() if trainer else None

    is_running = training_thread and training_thread.is_alive()

    controller = get_frequency_controller()
    freq_state = controller.get_state()

    return jsonify({
        'success': True,
        'is_running': is_running,
        'frequency_mode': freq_state['dominant_mode'],
        'progress': progress if progress else None
    })


@app.route('/ctm/training/stop', methods=['POST'])
def stop_ctm_training():
    """Stop current CTM training"""
    global training_stop_flag, training_thread

    if not training_thread or not training_thread.is_alive():
        return jsonify({
            'success': False,
            'message': 'No training in progress'
        })

    training_stop_flag = True
    trainer = get_ctm_trainer()
    trainer.stop_training()

    # Return to ALPHA mode
    controller = get_frequency_controller()
    controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)

    return jsonify({
        'success': True,
        'message': 'Training stop requested'
    })


@app.route('/ctm/training/checkpoints')
def list_training_checkpoints():
    """List available training checkpoints"""
    import glob

    checkpoint_dir = 'data/ctm_checkpoints'
    checkpoints = []

    for domain in ['logic', 'temporal', 'value', 'spatial']:
        pattern = f"{checkpoint_dir}/{domain}_*.json"
        files = glob.glob(pattern)
        for f in files:
            try:
                with open(f, 'r') as fp:
                    data = json.load(fp)
                    checkpoints.append({
                        'domain': domain,
                        'epoch': data.get('epoch', 0),
                        'convergence': data.get('progress', {}).get('routing_convergence', 0),
                        'timestamp': data.get('timestamp', ''),
                        'file': os.path.basename(f)
                    })
            except (json.JSONDecodeError, IOError, KeyError) as e:
                logging.getLogger(__name__).warning(f"Skipping corrupt checkpoint {f}: {e}")

    return jsonify({
        'success': True,
        'checkpoints': sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)
    })


@app.route('/frequency_bands')
def get_frequency_bands():
    """Get information about all frequency bands"""
    controller = get_frequency_controller()

    return jsonify({
        'success': True,
        'bands': controller.get_all_bands()
    })


# ============================================================================
# SNAPSHOT ENDPOINTS (P7.100)
# ============================================================================

@app.route('/snapshot/save', methods=['POST'])
def snapshot_save():
    """Save current brain state snapshot."""
    if not SNAPSHOT_AVAILABLE or brain_snapshot_mgr is None:
        return jsonify({'error': 'Snapshot manager not available'}), 503

    try:
        brain = get_unified_brain()
        data = request.get_json() or {}
        filename = data.get('filename', None)

        filepath = brain_snapshot_mgr.save(brain, filename=filename)

        # Emit event
        if EVENT_BUS_AVAILABLE:
            bus = get_event_bus()
            bus.emit(BrainTopics.SYSTEM_SNAPSHOT, {'filepath': filepath}, source='snapshot')

        return jsonify({
            'success': True,
            'filepath': filepath,
            'statistics': brain_snapshot_mgr.get_statistics(),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/snapshot/restore', methods=['POST'])
def snapshot_restore():
    """Restore brain state from a snapshot."""
    if not SNAPSHOT_AVAILABLE or brain_snapshot_mgr is None:
        return jsonify({'error': 'Snapshot manager not available'}), 503

    try:
        brain = get_unified_brain()
        data = request.get_json() or {}
        filepath = data.get('filepath')

        if not filepath:
            return jsonify({'error': 'filepath is required'}), 400

        snapshot = brain_snapshot_mgr.load(filepath)
        results = brain_snapshot_mgr.restore(brain, snapshot)

        # Emit event
        if EVENT_BUS_AVAILABLE:
            bus = get_event_bus()
            bus.emit(BrainTopics.SYSTEM_RESTORE, {'filepath': filepath, 'results': results}, source='snapshot')

        return jsonify({
            'success': True,
            'restore_results': results,
            'snapshot_metadata': snapshot.get('metadata', {}),
            'timestamp': datetime.now().isoformat()
        })
    except FileNotFoundError:
        return jsonify({'error': f'Snapshot file not found: {filepath}'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/snapshot/list')
def snapshot_list():
    """List all available brain snapshots."""
    if not SNAPSHOT_AVAILABLE or brain_snapshot_mgr is None:
        return jsonify({'error': 'Snapshot manager not available'}), 503

    try:
        snapshots = brain_snapshot_mgr.list_snapshots()
        return jsonify({
            'snapshots': snapshots,
            'count': len(snapshots),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/snapshot/statistics')
def snapshot_statistics():
    """Get snapshot manager statistics."""
    if not SNAPSHOT_AVAILABLE or brain_snapshot_mgr is None:
        return jsonify({'error': 'Snapshot manager not available'}), 503

    return jsonify(brain_snapshot_mgr.get_statistics())


# ============================================================================
# EVENT BUS ENDPOINTS (P7.99)
# ============================================================================

@app.route('/event_bus/statistics')
def event_bus_statistics():
    """Get event bus statistics."""
    if not EVENT_BUS_AVAILABLE:
        return jsonify({'error': 'Event bus not available'}), 503

    bus = get_event_bus()
    return jsonify(bus.get_statistics())


@app.route('/event_bus/history')
def event_bus_history():
    """Get recent event history."""
    if not EVENT_BUS_AVAILABLE:
        return jsonify({'error': 'Event bus not available'}), 503

    bus = get_event_bus()
    topic = request.args.get('topic', None)
    limit = int(request.args.get('limit', 50))

    return jsonify({
        'events': bus.get_history(topic=topic, limit=limit),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/event_bus/subscribers')
def event_bus_subscribers():
    """Get event bus subscriber counts."""
    if not EVENT_BUS_AVAILABLE:
        return jsonify({'error': 'Event bus not available'}), 503

    bus = get_event_bus()
    return jsonify({
        'subscribers': bus.get_subscribers(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/event_bus/emit', methods=['POST'])
def event_bus_emit():
    """Emit a custom event to the event bus."""
    if not EVENT_BUS_AVAILABLE:
        return jsonify({'error': 'Event bus not available'}), 503

    data = request.get_json() or {}
    topic = data.get('topic')
    event_data = data.get('data', {})
    source = data.get('source', 'api')

    if not topic:
        return jsonify({'error': 'topic is required'}), 400

    bus = get_event_bus()
    dispatched = bus.emit(topic=topic, data=event_data, source=source)

    return jsonify({
        'success': True,
        'dispatched_to': dispatched,
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# SHUTDOWN ENDPOINT (P7.96)
# ============================================================================

@app.route('/shutdown', methods=['POST'])
def shutdown_endpoint():
    """Trigger graceful shutdown via API."""
    if shutdown_in_progress:
        return jsonify({'message': 'Shutdown already in progress'}), 409

    # Run shutdown in background thread to allow response to be sent
    def _do_shutdown():
        import time as _time
        _time.sleep(0.5)  # Let response be sent first
        graceful_shutdown(signal.SIGTERM)
        os._exit(0)

    threading.Thread(target=_do_shutdown, daemon=True).start()

    return jsonify({
        'message': 'Graceful shutdown initiated',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# MOLTBOOK KNOWLEDGE SYSTEM API
# ============================================================================

@app.route('/moltbook/state')
def moltbook_state():
    """Get Moltbook system state overview."""
    brain = get_unified_brain()
    result = {'enabled': False}

    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        al = brain.agent_loop
        store = getattr(al, 'moltbook_store', None)
        if store:
            result['enabled'] = True
            # Store stats
            all_entries = store.get_active_entries(top_k=500)
            result['store'] = {
                'total_entries': len(all_entries),
                'sources': {},
                'types': {},
                'avg_confidence': 0,
                'avg_relevance': 0,
            }
            if all_entries:
                for e in all_entries:
                    src = getattr(e, 'source_agent', 'unknown')
                    result['store']['sources'][src] = result['store']['sources'].get(src, 0) + 1
                    etype = getattr(e, 'entry_type', 'unknown')
                    result['store']['types'][etype] = result['store']['types'].get(etype, 0) + 1
                result['store']['avg_confidence'] = round(
                    sum(e.confidence for e in all_entries) / len(all_entries), 3)
                result['store']['avg_relevance'] = round(
                    sum(e.relevance_score for e in all_entries) / len(all_entries), 3)

            # Pipeline stats
            orch = getattr(al, 'think_talk_orchestrator', None)
            if orch:
                result['pipeline'] = orch.get_stats()

            # Agent stats
            feeder = getattr(al, 'moltbook_feeder', None)
            if feeder:
                result['feeder'] = feeder.get_stats()
            eval_agent = getattr(al, 'evaluation_agent', None)
            if eval_agent:
                result['evaluation'] = eval_agent.get_stats()
            curation = getattr(al, 'curation_agent', None)
            if curation:
                result['curation'] = curation.get_stats()
            research = getattr(al, 'research_agent', None)
            if research:
                result['research'] = research.get_stats()
            feedback = getattr(al, 'feedback_agent', None)
            if feedback:
                result['feedback'] = feedback.get_stats()

    result['timestamp'] = datetime.now().isoformat()
    return jsonify(result)


@app.route('/moltbook/entries')
def moltbook_entries():
    """Get recent Moltbook entries."""
    brain = get_unified_brain()
    top_k = request.args.get('top_k', 20, type=int)
    entries = []

    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        store = getattr(brain.agent_loop, 'moltbook_store', None)
        if store:
            raw = store.get_active_entries(top_k=min(top_k, 100))
            for e in raw:
                entries.append({
                    'id': e.id,
                    'content': e.content[:200],
                    'source': e.source_agent,
                    'type': e.entry_type,
                    'confidence': round(e.confidence, 3),
                    'relevance': round(e.relevance_score, 3),
                    'tags': e.tags[:5],
                    'accessed': e.accessed_count,
                    'age_hours': round((time.time() - e.created_at) / 3600, 1),
                })

    return jsonify({'entries': entries, 'count': len(entries)})


@app.route('/moltbook/search', methods=['POST'])
def moltbook_search():
    """Semantic search in Moltbook."""
    brain = get_unified_brain()
    data = request.json or {}
    query = data.get('query', '')
    top_k = data.get('top_k', 10)

    if not query:
        return jsonify({'error': 'No query provided'}), 400

    results = []
    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        store = getattr(brain.agent_loop, 'moltbook_store', None)
        if store:
            raw = store.query_semantic(query, top_k=top_k)
            for e in raw:
                results.append({
                    'id': e.id,
                    'content': e.content[:300],
                    'source': e.source_agent,
                    'confidence': round(e.confidence, 3),
                    'relevance': round(e.relevance_score, 3),
                    'tags': e.tags,
                })

    return jsonify({'query': query, 'results': results, 'count': len(results)})


@app.route('/moltbook/feed', methods=['POST'])
def moltbook_feed():
    """Feed new knowledge into Moltbook."""
    brain = get_unified_brain()
    data = request.json or {}
    content = data.get('content', '')
    tags = data.get('tags', [])
    confidence = data.get('confidence', 0.5)

    if not content:
        return jsonify({'error': 'No content provided'}), 400

    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        feeder = getattr(brain.agent_loop, 'moltbook_feeder', None)
        if feeder:
            entry = feeder.post(content=content, tags=tags, confidence=confidence)
            if entry:
                return jsonify({
                    'success': True,
                    'entry_id': entry.id,
                    'content': entry.content[:200],
                })
        # Fallback: direct store
        store = getattr(brain.agent_loop, 'moltbook_store', None)
        if store:
            entry = store.add_entry(content=content, tags=tags, confidence=confidence,
                                     source_agent='dashboard')
            return jsonify({
                'success': True,
                'entry_id': entry.id,
                'content': entry.content[:200],
            })

    return jsonify({'error': 'Moltbook not available'}), 503


@app.route('/moltbook/debug')
def moltbook_debug():
    """Get Moltbook debug stream output."""
    brain = get_unified_brain()
    n = request.args.get('n', 30, type=int)

    if hasattr(brain, 'agent_loop') and brain.agent_loop:
        debug = getattr(brain.agent_loop, 'debug_stream', None)
        if debug:
            return jsonify({
                'enabled': debug.enabled,
                'entries': debug.get_recent(n),
                'formatted': debug.get_formatted(n),
                'stats': debug.get_stats(),
            })

    return jsonify({'enabled': False, 'entries': [], 'formatted': ''})


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  UNIFIED BRAIN SERVICE")
    print("=" * 70)
    print("\nThis service provides a single brain instance for all services:")
    print("  - Dashboard (port 5000)")
    print("  - Production API (port 5001)")
    print("  - Swarm (port 5002)")
    print("\nInitializing unified brain...")

    # Initialize brain on startup
    brain = get_unified_brain()

    print("\n" + "=" * 70)
    print("  UNIFIED BRAIN READY")
    print("=" * 70)
    print("\nAvailable endpoints:")
    print("  POST /predict - Make prediction")
    print("  POST /feedback - Submit feedback")
    print("  GET  /statistics - Get brain stats")
    print("  GET  /brain_state - Get current state")
    print("  POST /feature_call - Call brain feature as tool")
    print("  GET  /available_features - List all features")
    print("  POST /register - Register service connection")
    print("  GET  /health - Health check")
    print("\nServer starting at: http://localhost:5003")
    print("Press Ctrl+C to stop\n")

    port = int(os.environ.get('BRAIN_PORT', 5003))
    app.run(host='0.0.0.0', port=port, debug=False)

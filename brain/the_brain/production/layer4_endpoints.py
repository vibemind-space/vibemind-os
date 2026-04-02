"""
Layer 4 Production Endpoints (Phase 5)

Flask Blueprint for Layer 4 Temporal CTM endpoints:
- Status and control
- Training (Phase 2/3/4)
- Inference and regime detection
- Checkpoint management

Integration with unified_brain_service.py via Blueprint pattern.
"""

from flask import Blueprint, jsonify, request
from typing import Optional, Dict, Any, List
from datetime import datetime
import threading
import glob
import json
import os
import traceback

# Layer 4 imports (conditional for graceful degradation)
try:
    from core.layer4_temporal_router import Layer4TemporalRouter, TemporalRoutingResult
    LAYER4_AVAILABLE = True
except ImportError:
    LAYER4_AVAILABLE = False
    Layer4TemporalRouter = None
    TemporalRoutingResult = None

# Training imports (conditional)
try:
    from training import (
        TrainingConfig,
        TemporalCTMTrainer,
        TemporalCTMModel,
        PHASE4_AVAILABLE
    )
    TRAINING_AVAILABLE = True
except ImportError:
    TRAINING_AVAILABLE = False
    TrainingConfig = None
    TemporalCTMTrainer = None
    TemporalCTMModel = None
    PHASE4_AVAILABLE = False


# Create Blueprint
layer4_bp = Blueprint('layer4', __name__, url_prefix='/layer4')

# Global instances (managed by unified_brain_service.py)
layer4_router: Optional['Layer4TemporalRouter'] = None
layer4_trainer: Optional['TemporalCTMTrainer'] = None
layer4_training_thread: Optional[threading.Thread] = None
layer4_training_stop_flag = False
layer4_training_metrics: Dict[str, Any] = {}

# Thread locks for safe access
layer4_lock = threading.Lock()
layer4_training_lock = threading.Lock()


def get_layer4_router() -> Optional['Layer4TemporalRouter']:
    """Get or create Layer 4 router instance (thread-safe singleton)"""
    global layer4_router

    if not LAYER4_AVAILABLE:
        return None

    if layer4_router is None:
        with layer4_lock:
            if layer4_router is None:
                print("[LAYER4] Initializing Temporal Router...")
                layer4_router = Layer4TemporalRouter(
                    strict_security=True,
                    timing_threshold=0.5,
                    enable_deep_reasoning=True
                )
                print("[LAYER4] [OK] Temporal Router initialized")

    return layer4_router


def get_layer4_trainer() -> Optional['TemporalCTMTrainer']:
    """Get or create Layer 4 trainer instance"""
    global layer4_trainer

    if not TRAINING_AVAILABLE:
        return None

    if layer4_trainer is None:
        with layer4_lock:
            if layer4_trainer is None:
                print("[LAYER4] Initializing Trainer...")
                config = TrainingConfig(
                    batch_size=16,
                    learning_rate=1e-4,
                    num_epochs=50,
                    checkpoint_dir='data/layer4_checkpoints',
                    enable_phase4=PHASE4_AVAILABLE
                )
                layer4_trainer = TemporalCTMTrainer(config)
                print("[LAYER4] [OK] Trainer initialized")

    return layer4_trainer


# =============================================================================
# STATUS & CONTROL ENDPOINTS
# =============================================================================

@layer4_bp.route('/status')
def layer4_status():
    """Get Layer 4 temporal router status and statistics"""
    if not LAYER4_AVAILABLE:
        return jsonify({
            'success': False,
            'enabled': False,
            'error': 'Layer 4 not available (import failed)'
        }), 503

    try:
        router = get_layer4_router()

        if router is None:
            return jsonify({
                'success': False,
                'enabled': False,
                'error': 'Router initialization failed'
            }), 503

        # Get statistics
        stats = router.get_statistics()
        state_summary = router.get_current_state_summary()

        return jsonify({
            'success': True,
            'enabled': True,
            'training_available': TRAINING_AVAILABLE,
            'phase4_available': PHASE4_AVAILABLE,
            'statistics': stats,
            'state_summary': state_summary,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[LAYER4] Status error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@layer4_bp.route('/route', methods=['POST'])
def layer4_route():
    """Direct routing through Layer 4 temporal system"""
    if not LAYER4_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Layer 4 not available'
        }), 503

    try:
        data = request.json
        raw_events = data.get('events', [])
        task_description = data.get('task_description', '')
        source_trusted = data.get('source_trusted', False)

        if not raw_events:
            return jsonify({
                'success': False,
                'error': 'No events provided'
            }), 400

        router = get_layer4_router()

        with layer4_lock:
            result = router.route(
                raw_events=raw_events,
                task_description=task_description,
                source_trusted=source_trusted
            )

        # Convert result to JSON-serializable format
        response = {
            'success': True,
            'should_execute': result.should_execute,
            'tool_name': result.tool_name,
            'tool_parameters': result.tool_parameters,
            'timing_confidence': result.decision.timing_confidence,
            'blocked': result.blocked,
            'block_reason': result.block_reason if result.blocked else None,
            'processing_time_ms': result.processing_time_ms,
            'timestamp': result.timestamp.isoformat()
        }

        # Add regime if available
        if hasattr(result, 'regime') and result.regime:
            response['regime'] = result.regime.value if hasattr(result.regime, 'value') else str(result.regime)

        return jsonify(response)

    except Exception as e:
        print(f"[LAYER4] Route error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@layer4_bp.route('/regime')
def get_layer4_regime():
    """Get current detected regime"""
    if not LAYER4_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Layer 4 not available'
        }), 503

    try:
        router = get_layer4_router()

        # Get current state summary which includes regime
        state_summary = router.get_current_state_summary()

        # Try to get regime from state summary
        regime = state_summary.get('current_regime', 'UNKNOWN')

        return jsonify({
            'success': True,
            'regime': regime,
            'stability': state_summary.get('overall_stability', 'UNKNOWN'),
            'safe_for_action': state_summary.get('safe_for_action', False),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[LAYER4] Regime error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# TRAINING ENDPOINTS
# =============================================================================

@layer4_bp.route('/training/start', methods=['POST'])
def start_layer4_training():
    """Start Phase 2/3/4 training for Temporal CTM"""
    global layer4_training_thread, layer4_training_stop_flag, layer4_training_metrics

    if not TRAINING_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Training infrastructure not available'
        }), 503

    if layer4_training_thread and layer4_training_thread.is_alive():
        return jsonify({
            'success': False,
            'error': 'Training already in progress'
        }), 409

    try:
        data = request.json or {}

        # Parse config from request
        epochs = data.get('epochs', 50)
        batch_size = data.get('batch_size', 16)
        learning_rate = data.get('learning_rate', 1e-4)
        enable_phase4 = data.get('enable_phase4', PHASE4_AVAILABLE)
        use_synthetic = data.get('use_synthetic', True)
        mix_real_logs = data.get('mix_real_logs', False)
        log_dir = data.get('log_dir', 'data/logs')

        # Reset stop flag (thread-safe)
        with layer4_training_lock:
            layer4_training_stop_flag = False
            layer4_training_metrics = {
                'started_at': datetime.now().isoformat(),
                'epochs': epochs,
                'current_epoch': 0,
                'status': 'initializing',
                'losses': []
            }

        def training_worker():
            """Background training worker"""
            global layer4_training_stop_flag, layer4_training_metrics

            try:
                print(f"[LAYER4] Training started: {epochs} epochs, batch_size={batch_size}")
                with layer4_training_lock:
                    layer4_training_metrics['status'] = 'running'

                trainer = get_layer4_trainer()

                # Create dataset
                from training import SyntheticDataGenerator, TemporalDataset, create_dataloader

                generator = SyntheticDataGenerator(seed=42)
                trajectories = generator.generate_full_training_set(
                    n_per_regime=50,
                    include_transitions=True
                )

                dataset = TemporalDataset(trajectories)
                dataloader = create_dataloader(dataset, batch_size=batch_size, shuffle=True)

                # Training loop
                for epoch in range(epochs):
                    with layer4_training_lock:
                        if layer4_training_stop_flag:
                            print("[LAYER4] Training stopped by user")
                            layer4_training_metrics['status'] = 'stopped'
                            break
                        layer4_training_metrics['current_epoch'] = epoch + 1

                    # Train epoch
                    metrics = trainer.train_epoch(dataloader, epoch)

                    with layer4_training_lock:
                        layer4_training_metrics['losses'].append({
                            'epoch': epoch + 1,
                            **metrics
                        })

                    # Save checkpoint every 10 epochs
                    if (epoch + 1) % 10 == 0:
                        trainer.save_checkpoint(f'layer4_epoch_{epoch+1}')
                        print(f"[LAYER4] Checkpoint saved: epoch {epoch+1}")

                with layer4_training_lock:
                    if not layer4_training_stop_flag:
                        layer4_training_metrics['status'] = 'completed'
                        trainer.save_checkpoint('layer4_final')
                        print("[LAYER4] Training completed")

            except Exception as e:
                print(f"[LAYER4] Training error: {e}")
                traceback.print_exc()
                with layer4_training_lock:
                    layer4_training_metrics['status'] = 'error'
                    layer4_training_metrics['error'] = str(e)

        # Start training thread
        layer4_training_thread = threading.Thread(target=training_worker, daemon=True)
        layer4_training_thread.start()

        return jsonify({
            'success': True,
            'message': f'Training started: {epochs} epochs',
            'config': {
                'epochs': epochs,
                'batch_size': batch_size,
                'learning_rate': learning_rate,
                'enable_phase4': enable_phase4
            }
        })

    except Exception as e:
        print(f"[LAYER4] Training start error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@layer4_bp.route('/training/status')
def layer4_training_status():
    """Get training progress and metrics"""
    global layer4_training_metrics

    if not TRAINING_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Training infrastructure not available'
        }), 503

    is_running = layer4_training_thread and layer4_training_thread.is_alive()

    with layer4_training_lock:
        response = {
            'success': True,
            'training_active': is_running,
            **layer4_training_metrics,
            'timestamp': datetime.now().isoformat()
        }

        # Add latest loss if available
        if layer4_training_metrics.get('losses'):
            response['latest_loss'] = layer4_training_metrics['losses'][-1]

    return jsonify(response)


@layer4_bp.route('/training/stop', methods=['POST'])
def stop_layer4_training():
    """Stop training and return to normal mode"""
    global layer4_training_stop_flag

    if not layer4_training_thread or not layer4_training_thread.is_alive():
        return jsonify({
            'success': False,
            'error': 'No training in progress'
        }), 409

    with layer4_training_lock:
        layer4_training_stop_flag = True

    return jsonify({
        'success': True,
        'message': 'Training stop requested',
        'timestamp': datetime.now().isoformat()
    })


@layer4_bp.route('/training/checkpoints')
def list_layer4_checkpoints():
    """List available Temporal CTM checkpoints"""
    checkpoint_dir = 'data/layer4_checkpoints'

    if not os.path.exists(checkpoint_dir):
        return jsonify({
            'success': True,
            'checkpoints': [],
            'count': 0
        })

    try:
        checkpoints = []

        # Find all checkpoint files
        for pattern in ['*.pt', '*.pth', '*.json']:
            files = glob.glob(os.path.join(checkpoint_dir, pattern))
            for f in files:
                stat = os.stat(f)
                checkpoints.append({
                    'filename': os.path.basename(f),
                    'path': f,
                    'size_bytes': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        # Sort by modification time (newest first)
        checkpoints.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({
            'success': True,
            'checkpoints': checkpoints,
            'count': len(checkpoints),
            'checkpoint_dir': checkpoint_dir
        })

    except Exception as e:
        print(f"[LAYER4] Checkpoint list error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# INFERENCE ENDPOINTS
# =============================================================================

@layer4_bp.route('/load', methods=['POST'])
def load_layer4_checkpoint():
    """Load a trained Temporal CTM checkpoint"""
    if not TRAINING_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Training infrastructure not available'
        }), 503

    try:
        data = request.json
        checkpoint_path = data.get('checkpoint_path')
        version = data.get('version')

        if not checkpoint_path and not version:
            return jsonify({
                'success': False,
                'error': 'Must provide checkpoint_path or version'
            }), 400

        trainer = get_layer4_trainer()

        # Determine path
        if version:
            checkpoint_path = f'data/layer4_checkpoints/layer4_{version}.pt'

        if not os.path.exists(checkpoint_path):
            return jsonify({
                'success': False,
                'error': f'Checkpoint not found: {checkpoint_path}'
            }), 404

        # Load checkpoint
        trainer.load_checkpoint(checkpoint_path)

        return jsonify({
            'success': True,
            'message': f'Checkpoint loaded: {checkpoint_path}',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[LAYER4] Load checkpoint error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@layer4_bp.route('/process', methods=['POST'])
def layer4_process():
    """Process tool events through trained model"""
    if not LAYER4_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Layer 4 not available'
        }), 503

    try:
        data = request.json
        events = data.get('events', [])
        return_timing = data.get('return_timing', True)
        return_regime = data.get('return_regime', True)
        return_phases = data.get('return_phases', False)

        if not events:
            return jsonify({
                'success': False,
                'error': 'No events provided'
            }), 400

        router = get_layer4_router()

        results = []
        with layer4_lock:
            for event in events:
                # Process each event incrementally
                result = router.route_incremental(event)

                entry = {
                    'should_execute': result.should_execute,
                    'tool_name': result.tool_name
                }

                if return_timing:
                    entry['timing_confidence'] = result.decision.timing_confidence
                    entry['wait_time_ms'] = result.decision.wait_time_ms

                if return_regime and hasattr(result, 'regime'):
                    entry['regime'] = str(result.regime) if result.regime else None

                if return_phases and hasattr(result.decision, 'phase_state'):
                    entry['phases'] = result.decision.phase_state

                results.append(entry)

        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[LAYER4] Process error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@layer4_bp.route('/reset', methods=['POST'])
def layer4_reset():
    """Reset Layer 4 router state"""
    if not LAYER4_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Layer 4 not available'
        }), 503

    try:
        router = get_layer4_router()

        with layer4_lock:
            router.reset()

        return jsonify({
            'success': True,
            'message': 'Layer 4 router state reset',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[LAYER4] Reset error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@layer4_bp.route('/record_result', methods=['POST'])
def layer4_record_result():
    """Record tool execution result for learning"""
    if not LAYER4_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Layer 4 not available'
        }), 503

    try:
        data = request.json
        tool_name = data.get('tool_name')
        success = data.get('success', True)
        duration_ms = data.get('duration_ms')
        result_data = data.get('result_data')

        if not tool_name:
            return jsonify({
                'success': False,
                'error': 'tool_name required'
            }), 400

        router = get_layer4_router()

        with layer4_lock:
            router.record_execution_result(
                tool_name=tool_name,
                success=success,
                duration_ms=duration_ms,
                result=result_data
            )

        return jsonify({
            'success': True,
            'message': f'Result recorded for {tool_name}',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[LAYER4] Record result error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# HEALTH CHECK
# =============================================================================

@layer4_bp.route('/health')
def layer4_health():
    """Health check for Layer 4 subsystem"""
    return jsonify({
        'success': True,
        'layer4_available': LAYER4_AVAILABLE,
        'training_available': TRAINING_AVAILABLE,
        'phase4_available': PHASE4_AVAILABLE,
        'router_initialized': layer4_router is not None,
        'trainer_initialized': layer4_trainer is not None,
        'timestamp': datetime.now().isoformat()
    })


# =============================================================================
# FEATURES FOR INTEGRATION WITH /feature_call
# =============================================================================

def get_layer4_features() -> Dict[str, Any]:
    """
    Get Layer 4 features for integration with /feature_call endpoint.
    Called by unified_brain_service.py
    """
    if not LAYER4_AVAILABLE or layer4_router is None:
        return {
            'available': False,
            'error': 'Layer 4 not initialized'
        }

    try:
        stats = layer4_router.get_statistics()
        state_summary = layer4_router.get_current_state_summary()

        return {
            'available': True,
            'statistics': stats,
            'state_summary': state_summary,
            'regime': state_summary.get('current_regime', 'UNKNOWN')
        }
    except Exception as e:
        return {
            'available': False,
            'error': str(e)
        }


# Feature definitions for /available_features
LAYER4_FEATURE_DEFINITIONS = {
    'temporal_routing': 'Layer 4 temporal tool control state and statistics',
    'regime_state': 'Current operational regime (EXPLOIT/EXPLORE/REPAIR/DEADLOCK/TRANSITION)',
    'phase_dynamics': 'Oscillator phases and synchrony vectors (3 coupled oscillators)',
    'timing_gate': 'Timing gate probability for action emission',
    'security_state': 'Security flags and block status from stream separation'
}


if __name__ == '__main__':
    # Standalone test
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(layer4_bp)

    print("=" * 70)
    print("LAYER 4 ENDPOINTS - Standalone Test")
    print("=" * 70)
    print()
    print(f"Layer 4 Available: {LAYER4_AVAILABLE}")
    print(f"Training Available: {TRAINING_AVAILABLE}")
    print(f"Phase 4 Available: {PHASE4_AVAILABLE}")
    print()
    print("Registered endpoints:")
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith('layer4'):
            print(f"  {rule.methods} {rule.rule}")
    print()

    # Test health endpoint
    with app.test_client() as client:
        response = client.get('/layer4/health')
        print(f"Health check: {response.json}")

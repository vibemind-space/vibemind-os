"""
Test Phase 3: Fine-Tuning on Real Logs

Tests the complete fine-tuning pipeline:
- Regime inference from tool patterns
- Log parsing to trajectories
- Fine-tuning pre-trained model
"""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("PHASE 3 TEST: Fine-Tuning on Real Logs")
print("=" * 70)
print()

# Test 1: Import all Phase 3 modules
print("[1] Testing imports...")
try:
    from training.regime_inference import (
        ToolCallInfo, SegmentFeatures, RegimeInference,
        classify_tool, infer_session_regimes, extract_segment_features
    )
    print("    [OK] regime_inference")
except ImportError as e:
    print(f"    [FAIL] regime_inference: {e}")
    sys.exit(1)

try:
    from training.log_parser import (
        ToolCallRecord, SessionTrajectory, LogParser
    )
    print("    [OK] log_parser")
except ImportError as e:
    print(f"    [FAIL] log_parser: {e}")
    sys.exit(1)

try:
    from training.fine_tune import (
        FineTuneConfig, FineTuner, fine_tune_from_logs
    )
    print("    [OK] fine_tune")
except ImportError as e:
    print(f"    [FAIL] fine_tune: {e}")
    sys.exit(1)

from training.temporal_dataset import Regime
print()

# Test 2: Tool classification
print("[2] Testing tool classification...")
test_tools = [
    ('search_files', {'is_search': True}),
    ('grep_code', {'is_search': True}),
    ('read_file', {'is_read': True}),
    ('write_file', {'is_write': True}),
    ('docker_run', {'is_docker': True}),
    ('git_commit', {'is_git': True}),
]
for tool, expected in test_tools:
    result = classify_tool(tool)
    for key, val in expected.items():
        assert result.get(key) == val, f"Tool {tool}: expected {key}={val}"
    print(f"    {tool}: {result}")
print("    [OK] Tool classification working")
print()

# Test 3: Regime inference
print("[3] Testing regime inference...")

# EXPLOIT pattern
exploit_tools = ['read_file', 'edit_file', 'write_file', 'bash_run']
exploit_success = [True, True, True, True]
regimes = infer_session_regimes(exploit_tools, exploit_success)
print(f"    EXPLOIT pattern: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
assert any(r == Regime.EXPLOIT for r, _ in regimes), "Should detect EXPLOIT"

# EXPLORE pattern
explore_tools = ['search_files', 'grep_code', 'list_dir', 'glob_files']
explore_success = [True, True, True, True]
regimes = infer_session_regimes(explore_tools, explore_success)
print(f"    EXPLORE pattern: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
assert any(r == Regime.EXPLORE for r, _ in regimes), "Should detect EXPLORE"

# REPAIR pattern
repair_tools = ['bash_run', 'bash_run', 'bash_run']
repair_success = [False, False, True]
regimes = infer_session_regimes(repair_tools, repair_success)
print(f"    REPAIR pattern: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
assert any(r == Regime.REPAIR for r, _ in regimes), "Should detect REPAIR"

# DEADLOCK pattern
deadlock_tools = ['bash_run', 'bash_run', 'bash_run', 'bash_run']
deadlock_success = [False, False, False, False]
regimes = infer_session_regimes(deadlock_tools, deadlock_success)
print(f"    DEADLOCK pattern: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
assert any(r == Regime.DEADLOCK for r, _ in regimes), "Should detect DEADLOCK"

print("    [OK] Regime inference working")
print()

# Test 4: Log parsing
print("[4] Testing log parsing...")

with tempfile.TemporaryDirectory() as tmpdir:
    # Create mock text log
    log_content = """2025-01-15 10:30:00 Starting task: Deploy container
2025-01-15 10:30:01 Calling tool: bash
2025-01-15 10:30:02 Tool bash completed successfully
2025-01-15 10:30:03 Executing tool: docker_ps
2025-01-15 10:30:04 Tool docker_ps success
2025-01-15 10:30:05 Running tool: docker_run
2025-01-15 10:30:06 Error: container failed to start
2025-01-15 10:30:07 Calling tool: docker_run
2025-01-15 10:30:08 Tool docker_run completed successfully
"""
    log_path = os.path.join(tmpdir, 'test_session.log')
    with open(log_path, 'w') as f:
        f.write(log_content)

    # Create mock JSON log
    json_content = {
        "timestamp": "2025-01-15T10:30:00",
        "task": "Build and test application",
        "tool_calls": [
            {"tool": "read_file", "success": True, "duration_ms": 50},
            {"tool": "edit_file", "success": True, "duration_ms": 100},
            {"tool": "bash_run", "success": False, "error": "Test failed"},
            {"tool": "bash_run", "success": True, "duration_ms": 200}
        ],
        "decision": {"status": "GREEN"}
    }
    json_path = os.path.join(tmpdir, 'test_session.json')
    with open(json_path, 'w') as f:
        json.dump(json_content, f)

    # Parse logs
    parser = LogParser(tmpdir)
    sessions = parser.parse_all()
    print(f"    Parsed {len(sessions)} sessions")
    assert len(sessions) >= 2, "Should parse both log files"

    for session in sessions:
        print(f"    Session {session.session_id}:")
        print(f"        Tool calls: {session.num_calls}")
        print(f"        Outcome: {session.outcome}")
        regimes = session.infer_regimes()
        print(f"        Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes[:2]]}...")

    # Convert to trajectories
    for session in sessions:
        traj = session.to_temporal_trajectory()
        assert traj is not None, "Should convert to trajectory"
        assert traj.num_steps > 0, "Should have steps"
        print(f"    Trajectory: {traj.num_steps} steps")

    # Create dataset
    dataset = parser.to_dataset()
    stats = dataset.get_statistics()
    print(f"    Dataset: {stats['num_trajectories']} trajectories")
    print("    [OK] Log parsing working")
print()

# Test 5: Session trajectory conversion
print("[5] Testing session trajectory conversion...")

session = SessionTrajectory(
    session_id="test_001",
    task="Test conversion",
    tool_calls=[
        ToolCallRecord(timestamp="", tool_name="read_file", success=True),
        ToolCallRecord(timestamp="", tool_name="edit_file", success=True),
        ToolCallRecord(timestamp="", tool_name="bash_run", success=False),
        ToolCallRecord(timestamp="", tool_name="bash_run", success=True),
    ],
    outcome="success"
)

traj = session.to_temporal_trajectory()
assert traj is not None, "Should create trajectory"
print(f"    Steps: {traj.num_steps}")
print(f"    Success: {traj.success}")
print(f"    State vector shape: {traj.state_vectors.shape}")
print(f"    Sync vector shape: {traj.sync_vectors.shape}")
print(f"    Target cells: {traj.target_cells.tolist()}")
print(f"    Target regimes: {[Regime(r).name for r in traj.target_regimes]}")
print("    [OK] Session trajectory conversion working")
print()

# Test 6: Fine-tuner (without pre-trained checkpoint)
print("[6] Testing FineTuner (no pre-trained checkpoint)...")

with tempfile.TemporaryDirectory() as log_dir:
    with tempfile.TemporaryDirectory() as output_dir:
        # Create mock data
        mock_log = {
            "task": "Fine-tune test",
            "tool_calls": [
                {"tool": "read", "success": True},
                {"tool": "write", "success": True},
            ],
            "decision": {"status": "GREEN"}
        }
        with open(os.path.join(log_dir, "test.json"), 'w') as f:
            json.dump(mock_log, f)

        config = FineTuneConfig(
            hidden_dim=32,
            num_epochs=2,
            batch_size=2,
            mix_synthetic=True,
            synthetic_ratio=0.5
        )

        tuner = FineTuner(
            pretrained_checkpoint=None,
            log_dir=log_dir,
            output_dir=output_dir,
            config=config
        )

        print(f"    Device: {tuner.device}")
        print(f"    Pre-trained: {tuner.pretrained_loaded}")

        # Prepare data
        tuner.prepare_data(val_split=0.2)
        print(f"    Data prepared")

        # Fine-tune
        history = tuner.fine_tune(num_epochs=2, verbose=False)
        print(f"    Final loss: {history['total_loss'][-1]:.4f}")

        # Evaluate
        eval_metrics = tuner.evaluate()
        print(f"    Eval loss: {eval_metrics.get('val_loss', 'N/A')}")

        # Save checkpoint
        tuner.save_checkpoint("test.pt")
        assert os.path.exists(os.path.join(output_dir, "test.pt")), "Checkpoint should exist"
        print("    [OK] FineTuner working")
print()

# Test 7: Transition detection
print("[7] Testing transition detection...")
inference = RegimeInference()

# Mixed regime sequence
mixed_tools = ['read_file', 'edit_file', 'search_files', 'grep_code', 'bash_run', 'bash_run']
mixed_success = [True, True, True, True, False, True]
regime_seq = infer_session_regimes(mixed_tools, mixed_success)

transitions = inference.detect_transitions(regime_seq)
print(f"    Tool sequence: {mixed_tools}")
print(f"    Regime sequence: {[r.name for r, _ in regime_seq]}")
print(f"    Transitions at: {transitions}")
print("    [OK] Transition detection working")
print()

# Test 8: End-to-end pipeline
print("[8] Testing end-to-end pipeline...")

with tempfile.TemporaryDirectory() as log_dir:
    with tempfile.TemporaryDirectory() as output_dir:
        # Create realistic mock session
        session_data = {
            "task": "Deploy web application",
            "tool_calls": [
                {"tool": "read_file", "success": True, "duration_ms": 10},
                {"tool": "edit_file", "success": True, "duration_ms": 50},
                {"tool": "bash_run", "success": True, "duration_ms": 100},
                {"tool": "docker_build", "success": False, "error": "Build failed"},
                {"tool": "edit_file", "success": True, "duration_ms": 30},
                {"tool": "docker_build", "success": True, "duration_ms": 200},
                {"tool": "docker_run", "success": True, "duration_ms": 50},
            ],
            "decision": {"status": "GREEN"}
        }

        with open(os.path.join(log_dir, "deploy_session.json"), 'w') as f:
            json.dump(session_data, f)

        # Use convenience function
        results = fine_tune_from_logs(
            log_dir=log_dir,
            pretrained_checkpoint=None,
            output_dir=output_dir,
            num_epochs=2,
            mix_synthetic=True
        )

        print(f"    History keys: {list(results['history'].keys())}")
        print(f"    Eval keys: {list(results['evaluation'].keys())}")
        print("    [OK] End-to-end pipeline working")
print()

# Summary
print("=" * 70)
print("PHASE 3 TEST COMPLETE")
print("=" * 70)
print()
print("All Phase 3 components working:")
print("  [OK] regime_inference.py - Tool pattern -> Regime classification")
print("  [OK] log_parser.py - .log/.json -> SessionTrajectory -> TemporalTrajectory")
print("  [OK] fine_tune.py - FineTuner with mixed synthetic+real training")
print()
print("Fine-tuning pipeline ready for:")
print("  - Parsing real session logs from data/logs/")
print("  - Inferring regimes from tool call patterns")
print("  - Fine-tuning pre-trained models on real data")
print("  - Mixed training (synthetic + real)")
print()
print("=" * 70)

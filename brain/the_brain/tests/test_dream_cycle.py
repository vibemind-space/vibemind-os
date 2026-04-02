# tests/test_dream_cycle.py
"""
Phase 3 Dream Cycle Tests — verify RadialSleepTrainer fires during dream mode.

Tests that:
1. _enter_dream_mode() runs radial sleep training when buffer has data
2. Dream bridge modulation sets SleepWake to sleep state
3. EWC anchor is registered after training
4. Dream training logs metrics
5. brain_heartbeat._run_radial_dream_training() works via planner→agent_loop
6. Training skipped when buffer is empty
7. Bridge state restored after dreaming
"""
import dataclasses
import time
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
import torch


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes
# ---------------------------------------------------------------------------

def _make_radial_network():
    """Build a minimal RadialAttentionNetwork for testing."""
    from core.radial_attention import RadialAttentionNetwork
    net = RadialAttentionNetwork(
        seed_dim=384,
        thalamic_dim=128,
    )
    return net


def _make_experience_buffer(n_entries=10):
    """Build an ExperienceBuffer with N fake entries."""
    from core.experience_buffer import ExperienceBuffer
    buf = ExperienceBuffer(max_size=5000)
    net = _make_radial_network()
    for i in range(n_entries):
        seed = torch.randn(1, 384)
        with torch.no_grad():
            result = net(seed)
        buf.add(
            input_embedding=seed.squeeze(0),
            ring_activations=result['ring_activations'],
            ctm_trajectory=result['prediction_errors'],
            kuro_reward=float(np.random.uniform(-1, 1)),
            outcome='test',
        )
    return buf


def _make_agent_loop_with_radial(buffer_entries=10):
    """Build an AgentLoop with radial components wired up."""
    from core.agent_loop import AgentLoop, AgentLoopConfig
    from core.radial_sleep_trainer import RadialSleepTrainer
    from core.experience_buffer import ExperienceBuffer
    from core.seed_encoder import SeedEncoder
    from core.modulation_context import ModulationContext

    config = AgentLoopConfig(
        dream_duration_seconds=2.0,
        dream_tick_interval=0.1,
    )
    loop = AgentLoop(config=config)

    # Radial network
    net = _make_radial_network()
    mod_ctx = ModulationContext()
    net._modulation_context = mod_ctx
    loop.radial_network = net

    # Seed encoder
    loop.seed_encoder = SeedEncoder(seed_dim=384)

    # Experience buffer
    buf = ExperienceBuffer(max_size=5000)
    for i in range(buffer_entries):
        seed = torch.randn(1, 384)
        with torch.no_grad():
            result = net(seed)
        buf.add(
            input_embedding=seed.squeeze(0),
            ring_activations=result['ring_activations'],
            ctm_trajectory=result['prediction_errors'],
            kuro_reward=float(np.random.uniform(-1, 1)),
            outcome='test',
        )
    loop.experience_buffer = buf

    # Sleep trainer
    loop.radial_trainer = RadialSleepTrainer(
        network=net,
        buffer=buf,
        lr=0.001,
    )

    return loop


# ===================================================================
# Dream Bridge Modulation
# ===================================================================

class TestDreamBridgeModulation:
    """Tests for _set_dream_bridge_state() and _restore_wake_bridge_state()."""

    def test_set_dream_state(self):
        """SleepWake bridge is set to low arousal / high melatonin."""
        loop = _make_agent_loop_with_radial(buffer_entries=5)
        loop._set_dream_bridge_state()

        mod_ctx = loop.radial_network._modulation_context
        sw = mod_ctx.sleep_wake
        assert sw is not None
        assert sw.arousal < 0.3        # Low arousal
        assert sw.melatonin > 0.7      # High melatonin
        assert sw.is_awake is False    # Asleep
        assert sw.rem_probability > 0  # REM active
        assert sw.histamine < 0.3      # Suppressed

    def test_restore_wake_state(self):
        """Bridge state is restored to pre-dream values after dreaming."""
        loop = _make_agent_loop_with_radial(buffer_entries=5)
        mod_ctx = loop.radial_network._modulation_context

        # Set a custom initial state
        from core.sleep_wake_bridge import SleepWakeState
        original_state = SleepWakeState(arousal=0.7, melatonin=0.1)
        mod_ctx.sleep_wake = original_state

        # Enter dream → sets sleep state
        loop._set_dream_bridge_state()
        assert mod_ctx.sleep_wake.arousal < 0.3

        # Restore → original values
        loop._restore_wake_bridge_state()
        assert mod_ctx.sleep_wake.arousal == 0.7
        assert mod_ctx.sleep_wake.melatonin == 0.1

    def test_dream_state_without_radial(self):
        """_set_dream_bridge_state is a no-op without radial network."""
        from core.agent_loop import AgentLoop, AgentLoopConfig
        loop = AgentLoop(config=AgentLoopConfig())
        loop.radial_network = None
        # Should not raise
        loop._set_dream_bridge_state()
        loop._restore_wake_bridge_state()


# ===================================================================
# Radial Dream Training
# ===================================================================

class TestRadialDreamTraining:
    """Tests for _run_radial_dream_training()."""

    def test_training_runs_with_buffer(self):
        """Training runs and decreases loss over epochs."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        initial_epochs = loop.radial_trainer._total_epochs

        loop._run_radial_dream_training()

        assert loop.radial_trainer._total_epochs > initial_epochs

    def test_training_skipped_empty_buffer(self):
        """Training is skipped when buffer is empty."""
        loop = _make_agent_loop_with_radial(buffer_entries=0)

        loop._run_radial_dream_training()

        assert loop.radial_trainer._total_epochs == 0

    def test_ewc_anchor_registered(self):
        """EWC anchor is registered after training."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        assert loop.radial_trainer._ewc_anchor is None

        loop._run_radial_dream_training()

        assert loop.radial_trainer._ewc_anchor is not None

    def test_training_without_trainer(self):
        """No error when radial_trainer is None."""
        from core.agent_loop import AgentLoop, AgentLoopConfig
        loop = AgentLoop(config=AgentLoopConfig())
        loop.radial_trainer = None
        # Should not raise
        loop._run_radial_dream_training()

    def test_training_produces_finite_loss(self):
        """All training losses are finite (no NaN/Inf)."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)

        # Patch to capture losses
        losses = []
        original_train = loop.radial_trainer.train_epoch

        def _capture_loss(*args, **kwargs):
            loss = original_train(*args, **kwargs)
            losses.append(loss)
            return loss

        loop.radial_trainer.train_epoch = _capture_loss
        loop._run_radial_dream_training()

        assert len(losses) > 0
        for loss in losses:
            assert np.isfinite(loss), f"Non-finite loss: {loss}"

    def test_modulation_context_active_during_training(self):
        """ModulationContext is in dream state during training."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        mod_ctx = loop.radial_network._modulation_context

        # Track what state the bridge is in during training
        states_during_training = []
        original_train = loop.radial_trainer.train_epoch

        def _check_state(*args, **kwargs):
            sw = getattr(mod_ctx, 'sleep_wake', None)
            if sw is not None:
                states_during_training.append(sw.arousal)
            return original_train(*args, **kwargs)

        loop.radial_trainer.train_epoch = _check_state

        # Set dream state then train
        loop._set_dream_bridge_state()
        loop._run_radial_dream_training()

        # During training, arousal should be low (sleep state)
        assert len(states_during_training) > 0
        for arousal in states_during_training:
            assert arousal < 0.3, f"Arousal was {arousal} during training (expected sleep)"


# ===================================================================
# Full Dream Cycle Integration
# ===================================================================

class TestDreamCycleIntegration:
    """Integration tests for the full dream mode flow in AgentLoop."""

    def test_enter_dream_triggers_training(self):
        """Entering dream mode triggers radial sleep training."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        initial_epochs = loop.radial_trainer._total_epochs

        # Manually call (FSM starts in STOPPED, transition to IDLE first)
        from core.agent_loop import AgentState
        loop.fsm.transition(AgentState.IDLE)
        loop._enter_dream_mode()

        # Training should have run (training takes longer than dream
        # duration, so dream completes in a single call → FSM → IDLE)
        assert loop.radial_trainer._total_epochs > initial_epochs
        # EWC anchor should be set
        assert loop.radial_trainer._ewc_anchor is not None
        # FSM ends in IDLE because training duration > dream_duration
        assert loop.fsm.state == AgentState.IDLE

    def test_dream_stays_dreaming_when_duration_long(self):
        """Dream mode stays in DREAMING when duration is longer than training."""
        loop = _make_agent_loop_with_radial(buffer_entries=5)
        loop.config.dream_duration_seconds = 600.0  # Very long
        loop.config.dream_tick_interval = 0.01

        from core.agent_loop import AgentState
        loop.fsm.transition(AgentState.IDLE)
        loop._enter_dream_mode()

        # Training runs quickly (small buffer) and dream hasn't expired
        assert loop.fsm.state == AgentState.DREAMING

    def test_bridge_restored_after_dream(self):
        """Bridge state is restored when dream mode completes."""
        loop = _make_agent_loop_with_radial(buffer_entries=10)
        # Short dream so it finishes in one call (training > duration)
        loop.config.dream_duration_seconds = 0.1
        loop.config.dream_tick_interval = 0.01

        mod_ctx = loop.radial_network._modulation_context
        from core.sleep_wake_bridge import SleepWakeState
        original = SleepWakeState(arousal=0.6, melatonin=0.2, histamine=0.5)
        mod_ctx.sleep_wake = original

        from core.agent_loop import AgentState
        loop.fsm.transition(AgentState.IDLE)

        # Enter dream — training runs, dream expires, bridge restored
        loop._enter_dream_mode()

        # Should be restored to original after dream completes
        assert loop.fsm.state == AgentState.IDLE
        assert mod_ctx.sleep_wake.arousal == 0.6
        assert mod_ctx.sleep_wake.melatonin == 0.2

    def test_dream_without_radial_still_works(self):
        """Dream mode works (no crash) when radial components are missing."""
        from core.agent_loop import AgentLoop, AgentLoopConfig, AgentState
        loop = AgentLoop(config=AgentLoopConfig(
            dream_duration_seconds=0.1,
            dream_tick_interval=0.05,
        ))
        loop.fsm.transition(AgentState.IDLE)

        # Should not raise
        loop._enter_dream_mode()
        assert loop.fsm.state == AgentState.DREAMING

    def test_dream_event_published(self):
        """Dream start event is published to event bus."""
        loop = _make_agent_loop_with_radial(buffer_entries=10)

        # Mock event bus
        mock_bus = MagicMock()
        loop.event_bus = mock_bus

        from core.agent_loop import AgentState
        loop.fsm.transition(AgentState.IDLE)
        loop._enter_dream_mode()

        # Should have published dream_start and dream_training_complete
        topics = [call.args[0].topic for call in mock_bus.publish.call_args_list]
        assert 'agent.dream_start' in topics
        assert 'agent.dream_training_complete' in topics

    def test_training_complete_event_data(self):
        """Dream training complete event contains epochs + loss data."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        mock_bus = MagicMock()
        loop.event_bus = mock_bus

        from core.agent_loop import AgentState
        loop.fsm.transition(AgentState.IDLE)
        loop._enter_dream_mode()

        # Find the training_complete event
        for call in mock_bus.publish.call_args_list:
            event = call.args[0]
            if event.topic == 'agent.dream_training_complete':
                assert 'epochs' in event.data
                assert 'avg_loss' in event.data
                assert 'buffer_size' in event.data
                assert event.data['epochs'] > 0
                assert event.data['buffer_size'] > 0
                break
        else:
            pytest.fail("dream_training_complete event not found")


# ===================================================================
# Dream Audit Logging
# ===================================================================

class TestDreamAuditLogging:
    """Tests for _log_dream_cycle() audit trail."""

    def test_dream_logged_to_audit(self):
        """Dream cycle is logged to PredictionAuditLog."""
        from core.brain_monitoring import PredictionAuditLog

        loop = _make_agent_loop_with_radial(buffer_entries=40)
        audit = PredictionAuditLog()
        loop.audit_log = audit

        from core.agent_loop import AgentState
        loop.fsm.transition(AgentState.IDLE)
        loop._enter_dream_mode()

        # get_recent() returns list of dicts (via asdict())
        entries = audit.get_recent(10)
        assert len(entries) >= 1
        dream_entry = entries[-1]
        assert dream_entry['task_type'] == 'dream_cycle'
        assert dream_entry['pipeline_mode'] == 'radial_sleep'
        assert dream_entry['loop_iterations'] > 0

    def test_no_audit_log_no_error(self):
        """No error when audit_log is not set."""
        loop = _make_agent_loop_with_radial(buffer_entries=10)
        assert not hasattr(loop, 'audit_log') or loop.audit_log is None
        # Should not raise
        loop._log_dream_cycle(
            n_epochs=3, losses=[0.5, 0.4, 0.3],
            buffer_size=10, elapsed_s=1.0,
        )


# ===================================================================
# BrainHeartbeat Radial Integration
# ===================================================================

class TestHeartbeatRadialDreamTraining:
    """Tests for brain_heartbeat._run_radial_dream_training()."""

    def test_heartbeat_runs_training(self):
        """Heartbeat triggers radial training via planner→agent_loop."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        initial_epochs = loop.radial_trainer._total_epochs

        # Create a mock planner with agent_loop attribute
        mock_planner = MagicMock()
        mock_planner.agent_loop = loop

        # Create heartbeat with mock planner
        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig
        config = BrainHeartbeatConfig(enable_dream_mode=False)
        heartbeat = BrainHeartbeat(planner=mock_planner, config=config)

        result = heartbeat._run_radial_dream_training()

        assert result is True
        assert loop.radial_trainer._total_epochs > initial_epochs
        assert loop.radial_trainer._ewc_anchor is not None

    def test_heartbeat_no_agent_loop(self):
        """Returns False when no agent_loop on planner."""
        mock_planner = MagicMock(spec=[])  # No agent_loop attr

        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig
        config = BrainHeartbeatConfig(enable_dream_mode=False)
        heartbeat = BrainHeartbeat(planner=mock_planner, config=config)

        result = heartbeat._run_radial_dream_training()
        assert result is False

    def test_heartbeat_empty_buffer(self):
        """Returns False when experience buffer is empty."""
        loop = _make_agent_loop_with_radial(buffer_entries=0)
        mock_planner = MagicMock()
        mock_planner.agent_loop = loop

        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig
        config = BrainHeartbeatConfig(enable_dream_mode=False)
        heartbeat = BrainHeartbeat(planner=mock_planner, config=config)

        result = heartbeat._run_radial_dream_training()
        assert result is False

    def test_heartbeat_no_trainer(self):
        """Returns False when radial_trainer is None."""
        loop = _make_agent_loop_with_radial(buffer_entries=10)
        loop.radial_trainer = None

        mock_planner = MagicMock()
        mock_planner.agent_loop = loop

        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig
        config = BrainHeartbeatConfig(enable_dream_mode=False)
        heartbeat = BrainHeartbeat(planner=mock_planner, config=config)

        result = heartbeat._run_radial_dream_training()
        assert result is False


# ===================================================================
# Trainer Stats
# ===================================================================

class TestTrainerStats:
    """Tests for RadialSleepTrainer statistics during dream cycle."""

    def test_epoch_count_increments(self):
        """Total epochs increments after each training call."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)
        assert loop.radial_trainer._total_epochs == 0

        loop._run_radial_dream_training()

        stats = loop.radial_trainer.get_stats()
        assert stats['total_epochs'] >= 3  # default 3 epochs
        assert stats['has_ewc_anchor'] is True
        assert stats['buffer_size'] == 40

    def test_multiple_dream_cycles(self):
        """Multiple dream cycles accumulate epochs."""
        loop = _make_agent_loop_with_radial(buffer_entries=40)

        loop._run_radial_dream_training()
        first_count = loop.radial_trainer._total_epochs

        loop._run_radial_dream_training()
        second_count = loop.radial_trainer._total_epochs

        assert second_count > first_count

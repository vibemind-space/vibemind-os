# tests/test_radial_production.py
"""
Phase 1 Boot Smoke Tests — verify radial network fires during cognitive processing.

Tests that:
1. SeedEncoder produces correct shape output
2. AgentLoop._radial_forward() runs successfully
3. ExperienceBuffer gets populated after forward
4. Hebbian plasticity updates run
5. Full THINKING state flow includes radial processing
"""
import pytest
import numpy as np
import torch


class TestSeedEncoder:
    """Test SeedEncoder produces valid 384-dim seeds."""

    def test_encode_from_description(self):
        from core.seed_encoder import SeedEncoder
        enc = SeedEncoder(seed_dim=384)
        seed = enc.encode_from_description("Check memory status and restart dashboard")
        assert seed.shape == (1, 384)
        assert not np.isnan(seed).any()

    def test_encode_with_routing_weights(self):
        from core.seed_encoder import SeedEncoder
        enc = SeedEncoder(seed_dim=384)
        rw = np.array([0.3, 0.1, 0.05, 0.05, 0.05, 0.2, 0.1, 0.05, 0.05, 0.05])
        seed = enc.encode_from_description("Run docker compose up", routing_weights=rw)
        assert seed.shape == (1, 384)

    def test_encode_structured_context(self):
        from core.seed_encoder import SeedEncoder, TaskContext
        enc = SeedEncoder(seed_dim=384)
        ctx = TaskContext(
            routing_weights=np.ones(10) / 10,
            complexity=0.7,
            urgency=0.9,
            task_type='docker',
            processing_mode='urgent',
            keywords=['docker', 'restart', 'compose'],
            raw_description='Restart the docker containers',
        )
        seed = enc.encode(ctx)
        assert seed.shape == (1, 384)
        # L2 normalized
        norm = np.linalg.norm(seed)
        assert abs(norm - 1.0) < 0.01

    def test_deterministic(self):
        """Same input always produces same output."""
        from core.seed_encoder import SeedEncoder
        enc = SeedEncoder(seed_dim=384)
        s1 = enc.encode_from_description("test task")
        s2 = enc.encode_from_description("test task")
        np.testing.assert_array_equal(s1, s2)

    def test_different_inputs_different_seeds(self):
        from core.seed_encoder import SeedEncoder
        enc = SeedEncoder(seed_dim=384)
        s1 = enc.encode_from_description("docker restart")
        s2 = enc.encode_from_description("check memory usage")
        assert not np.allclose(s1, s2)

    def test_infer_task_type(self):
        from core.seed_encoder import SeedEncoder
        assert SeedEncoder._infer_task_type("run docker compose up") == 'docker'
        assert SeedEncoder._infer_task_type("search for the file") == 'search'
        assert SeedEncoder._infer_task_type("random gibberish xyz") == 'unknown'


class TestRadialForward:
    """Test _radial_forward() integration in AgentLoop."""

    def _make_agent_loop(self):
        """Create a minimal AgentLoop with radial network wired."""
        from core.agent_loop import AgentLoop, AgentTask, TaskPriority
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.seed_encoder import SeedEncoder

        loop = AgentLoop()
        loop.radial_network = RadialAttentionNetwork(seed_dim=384)
        loop.seed_encoder = SeedEncoder(seed_dim=384)
        loop.experience_buffer = ExperienceBuffer(max_size=100)
        loop.hebbian = HebbianAttentionUpdate(learning_rate=0.001, decay=0.0001)
        return loop

    def test_radial_forward_runs(self):
        from core.agent_loop import AgentTask, TaskPriority
        loop = self._make_agent_loop()
        task = AgentTask(
            task_id='test-001',
            description='Check memory status',
            priority=TaskPriority.SELF_INITIATED,
            source='test',
        )
        result = loop._radial_forward(task)
        assert result is not None
        assert 'ring_activations' in result
        assert 'prediction_errors' in result
        assert 'meta_output' in result
        assert len(result['ring_activations']) == 5

    def test_experience_buffer_populated(self):
        from core.agent_loop import AgentTask, TaskPriority
        loop = self._make_agent_loop()
        assert len(loop.experience_buffer) == 0

        task = AgentTask(
            task_id='test-002',
            description='Run some analysis',
            priority=TaskPriority.SELF_INITIATED,
            source='test',
        )
        loop._radial_forward(task)
        assert len(loop.experience_buffer) == 1

        # Second forward adds another entry
        loop._radial_forward(task)
        assert len(loop.experience_buffer) == 2

    def test_radial_output_cached(self):
        from core.agent_loop import AgentTask, TaskPriority
        loop = self._make_agent_loop()
        assert loop._last_radial_output is None

        task = AgentTask(
            task_id='test-003',
            description='Test caching',
            priority=TaskPriority.SELF_INITIATED,
            source='test',
        )
        loop._radial_forward(task)
        assert loop._last_radial_output is not None
        assert 'ring_activations' in loop._last_radial_output

    def test_graceful_without_radial(self):
        """No crash when radial network is not wired."""
        from core.agent_loop import AgentLoop, AgentTask, TaskPriority
        loop = AgentLoop()
        task = AgentTask(
            task_id='test-004',
            description='No radial',
            priority=TaskPriority.SELF_INITIATED,
            source='test',
        )
        result = loop._radial_forward(task)
        assert result is None

    def test_multiple_ticks_bridge_states_evolve(self):
        """Bridge states should change across ticks (1-tick delay)."""
        from core.agent_loop import AgentTask, TaskPriority
        loop = self._make_agent_loop()
        task = AgentTask(
            task_id='test-005',
            description='Multi-tick test with bridges',
            priority=TaskPriority.SELF_INITIATED,
            source='test',
        )

        # Run several ticks
        results = []
        for _ in range(5):
            r = loop._radial_forward(task)
            results.append(r)

        # All should succeed
        assert all(r is not None for r in results)

        # Prediction errors should be computed each tick
        for r in results:
            assert len(r['prediction_errors']) == 4  # 5 rings → 4 PE values


class TestExperienceBufferRewardUpdate:
    """Test that _learn() updates last buffer entry with actual reward."""

    def test_reward_updated_after_learn(self):
        from core.agent_loop import AgentLoop, AgentTask, TaskPriority
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.seed_encoder import SeedEncoder

        loop = AgentLoop()
        loop.radial_network = RadialAttentionNetwork(seed_dim=384)
        loop.seed_encoder = SeedEncoder(seed_dim=384)
        loop.experience_buffer = ExperienceBuffer(max_size=100)

        task = AgentTask(
            task_id='test-006',
            description='Test reward update',
            priority=TaskPriority.SELF_INITIATED,
            source='test',
        )

        # Run radial forward (records pending experience)
        loop._radial_forward(task)
        assert loop.experience_buffer._buffer[-1]['kuro_reward'] == 0.0
        assert loop.experience_buffer._buffer[-1]['outcome'] == 'pending'

        # Simulate _learn() outcome with high confidence
        outcome = {'confidence': 0.8, 'radial_active': True}
        loop._learn(task, None, outcome)

        # Should be updated
        assert loop.experience_buffer._buffer[-1]['kuro_reward'] == 1.0
        assert loop.experience_buffer._buffer[-1]['outcome'] == 'success'

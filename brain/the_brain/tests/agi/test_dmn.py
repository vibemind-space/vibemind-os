"""
Default Mode Network Tests - Phase B1

Tests for self-referential processing, future simulation,
mind wandering, DMN/TPN switching, and full DMN integration.
"""

import pytest
import numpy as np


@pytest.fixture
def state_dim():
    return 16

@pytest.fixture
def sample_state(state_dim):
    np.random.seed(42)
    return np.random.randn(state_dim).astype(np.float32)

@pytest.fixture
def dmn(state_dim):
    from core.default_mode_network import DefaultModeNetwork
    return DefaultModeNetwork(
        state_dim=state_dim,
        activation_threshold=0.3,
        creativity_temperature=1.5,
        mind_wandering_rate=1.0,  # Always wander for testing
    )


class TestSelfReferentialProcessor:

    def test_reflect(self, state_dim):
        from core.default_mode_network import SelfReferentialProcessor
        srp = SelfReferentialProcessor(state_dim=state_dim)
        reflection = srp.reflect(np.random.randn(state_dim).astype(np.float32))
        assert reflection.shape == (state_dim,)

    def test_self_model_updates(self, state_dim):
        from core.default_mode_network import SelfReferentialProcessor
        srp = SelfReferentialProcessor(state_dim=state_dim)
        for _ in range(10):
            srp.reflect(np.ones(state_dim, dtype=np.float32))
        srp.update_self_model(learning_rate=0.5)
        # Self model should move toward ones
        assert srp._self_model.mean() > 0


class TestFutureSimulator:

    def test_simulate_empty(self, state_dim):
        from core.default_mode_network import FutureSimulator
        fs = FutureSimulator(state_dim=state_dim)
        result = fs.simulate_future()
        assert np.allclose(result, 0.0)

    def test_simulate_with_history(self, state_dim):
        from core.default_mode_network import FutureSimulator
        fs = FutureSimulator(state_dim=state_dim)
        fs.record_state(np.zeros(state_dim, dtype=np.float32))
        fs.record_state(np.ones(state_dim, dtype=np.float32))
        result = fs.simulate_future(n_steps=1)
        assert result.shape == (state_dim,)
        # Should extrapolate beyond ones
        assert result.mean() > 0.5


class TestMindWanderingGenerator:

    def test_generate_with_no_memory(self, state_dim):
        from core.default_mode_network import MindWanderingGenerator
        mw = MindWanderingGenerator(state_dim=state_dim)
        result = mw.generate_association()
        assert result.shape == (state_dim,)

    def test_generate_with_memories(self, state_dim):
        from core.default_mode_network import MindWanderingGenerator
        mw = MindWanderingGenerator(state_dim=state_dim)
        for _ in range(5):
            mw.store_experience(np.random.randn(state_dim).astype(np.float32))
        result = mw.generate_association()
        assert result.shape == (state_dim,)
        assert mw.association_count == 1


class TestDMN_TPN_Switch:

    def test_dmn_active_by_default(self):
        from core.default_mode_network import DMN_TPN_Switch
        switch = DMN_TPN_Switch(switch_threshold=0.3)
        assert switch.is_dmn_active

    def test_switch_to_tpn(self):
        from core.default_mode_network import DMN_TPN_Switch
        switch = DMN_TPN_Switch(switch_threshold=0.3)
        switch.update(task_load=0.8)
        assert not switch.is_dmn_active

    def test_switch_count(self):
        from core.default_mode_network import DMN_TPN_Switch
        switch = DMN_TPN_Switch(switch_threshold=0.5)
        switch.update(0.8)  # TPN
        switch.update(0.1)  # DMN
        assert switch.switch_count == 2


class TestDefaultModeNetwork:

    def test_instantiation(self, dmn):
        assert dmn is not None

    def test_process_idle(self, dmn, sample_state):
        output = dmn.process(sample_state, task_load=0.0)
        assert output.mode == "active"
        assert output.activation_level > 0.5
        assert output.self_reflection.shape == (16,)

    def test_process_busy(self, dmn, sample_state):
        output = dmn.process(sample_state, task_load=0.9)
        assert output.mode == "suppressed"
        assert np.allclose(output.self_reflection, 0.0)

    def test_creativity_output(self, dmn, sample_state):
        output = dmn.process(sample_state, task_load=0.0)
        # With mind_wandering_rate=1.0, should always generate
        assert output.creative_association.shape == (16,)

    def test_get_state(self, dmn, sample_state):
        dmn.process(sample_state)
        state = dmn.get_state()
        assert 'stats' in state
        assert 'switch' in state

    def test_reset(self, dmn, sample_state):
        dmn.process(sample_state)
        dmn.reset()
        assert dmn.get_stats().activations == 0

    def test_from_yaml(self):
        from core.default_mode_network import DefaultModeNetwork
        d = DefaultModeNetwork.from_yaml({
            'default_mode_network': {'activation_threshold': 0.5}
        })
        assert d.switch.switch_threshold == 0.5

    def test_from_yaml_defaults(self):
        from core.default_mode_network import DefaultModeNetwork
        d = DefaultModeNetwork.from_yaml({})
        assert d is not None

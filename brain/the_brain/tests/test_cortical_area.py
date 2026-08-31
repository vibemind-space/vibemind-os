"""
Tests for core.cortical_area — CorticalArea wrapping CanonicalMicrocircuit.
"""

import numpy as np
import pytest

from core.cortical_area import CorticalArea, CorticalAreaConfig


# ─── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def default_config():
    return CorticalAreaConfig(
        name="language",
        specialty=["syntax", "semantics"],
        layer_dim=8,
        decay_rate=0.05,
        max_thoughts=100,
    )


@pytest.fixture
def area(default_config):
    return CorticalArea(default_config)


@pytest.fixture
def random_input():
    """Random thalamic input of shape (8,)."""
    rng = np.random.default_rng(42)
    return rng.standard_normal(8)


# ─── Creation ────────────────────────────────────────────────────────────

class TestCreation:

    def test_create_with_config(self, default_config):
        area = CorticalArea(default_config)
        assert area.name == "language"
        assert area.specialty == ["syntax", "semantics"]
        assert area.activation == 0.0

    def test_initial_state_keys(self, area):
        state = area.get_state()
        expected_keys = {'name', 'activation', 'specialty', 'avg_error',
                         'avg_activity', 'thought_count'}
        assert set(state.keys()) == expected_keys

    def test_initial_thought_count_zero(self, area):
        assert area.get_state()['thought_count'] == 0
        assert area.get_recent_thoughts() == []

    def test_repr(self, area):
        r = repr(area)
        assert "CorticalArea" in r
        assert "language" in r


# ─── receive_input ───────────────────────────────────────────────────────

class TestReceiveInput:

    def test_returns_dict_with_expected_keys(self, area, random_input):
        result = area.receive_input(random_input)
        for key in ('output', 'prediction', 'error_signal',
                     'error_magnitude', 'layer_activations', 'activation'):
            assert key in result, f"Missing key: {key}"

    def test_activation_positive_after_input(self, area, random_input):
        area.receive_input(random_input)
        assert area.activation > 0.0

    def test_activation_field_matches_property(self, area, random_input):
        result = area.receive_input(random_input)
        assert result['activation'] == area.activation

    def test_thought_stored(self, area, random_input):
        area.receive_input(random_input)
        thoughts = area.get_recent_thoughts()
        assert len(thoughts) == 1
        assert 'output' in thoughts[0]
        assert 'prediction' in thoughts[0]
        assert 'error_magnitude' in thoughts[0]
        assert 'activation' in thoughts[0]

    def test_multiple_inputs_store_multiple_thoughts(self, area):
        rng = np.random.default_rng(123)
        for _ in range(5):
            area.receive_input(rng.standard_normal(8))
        assert len(area.get_recent_thoughts(10)) == 5

    def test_optional_cortical_and_feedback(self, area, random_input):
        """Providing cortical_input and feedback explicitly should not crash."""
        cortical = np.ones(8) * 0.5
        feedback = np.ones(8) * -0.3
        result = area.receive_input(random_input, cortical_input=cortical,
                                     feedback=feedback)
        assert 'output' in result

    def test_zero_input_does_not_crash(self, area):
        result = area.receive_input(np.zeros(8))
        assert 'output' in result
        # Activation should be non-negative
        assert area.activation >= 0.0


# ─── Activation bounds ───────────────────────────────────────────────────

class TestActivationBounds:

    def test_bounded_zero_one_after_many_inputs(self):
        cfg = CorticalAreaConfig(name="stress_test", layer_dim=8)
        area = CorticalArea(cfg)
        rng = np.random.default_rng(99)
        for _ in range(200):
            area.receive_input(rng.standard_normal(8) * 10)
        assert 0.0 <= area.activation <= 1.0

    def test_bounded_after_many_ticks(self, area, random_input):
        area.receive_input(random_input)
        for _ in range(1000):
            area.tick()
        assert area.activation >= 0.0


# ─── tick (decay) ────────────────────────────────────────────────────────

class TestTick:

    def test_activation_decays(self, area, random_input):
        area.receive_input(random_input)
        before = area.activation
        area.tick()
        assert area.activation < before

    def test_decay_by_correct_amount(self, area, random_input):
        area.receive_input(random_input)
        before = area.activation
        area.tick()
        expected = max(0.0, before - area.config.decay_rate)
        assert abs(area.activation - expected) < 1e-9

    def test_activation_floors_at_zero(self, area):
        # Without any input, activation is 0.  Tick should keep it at 0.
        area.tick()
        assert area.activation == 0.0

    def test_multiple_ticks_monotonic_decrease(self, area, random_input):
        area.receive_input(random_input)
        values = [area.activation]
        for _ in range(10):
            area.tick()
            values.append(area.activation)
        # Each value should be <= the previous
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1]


# ─── get_recent_thoughts ────────────────────────────────────────────────

class TestRecentThoughts:

    def test_returns_last_n(self, area):
        rng = np.random.default_rng(7)
        for _ in range(20):
            area.receive_input(rng.standard_normal(8))
        recent = area.get_recent_thoughts(5)
        assert len(recent) == 5
        all_thoughts = area.get_recent_thoughts(100)
        assert recent == all_thoughts[-5:]

    def test_fewer_than_n(self, area, random_input):
        area.receive_input(random_input)
        recent = area.get_recent_thoughts(50)
        assert len(recent) == 1

    def test_max_thoughts_bounded(self):
        cfg = CorticalAreaConfig(name="bounded", layer_dim=8, max_thoughts=5)
        area = CorticalArea(cfg)
        rng = np.random.default_rng(11)
        for _ in range(20):
            area.receive_input(rng.standard_normal(8))
        assert len(area.get_recent_thoughts(100)) == 5


# ─── get_state ───────────────────────────────────────────────────────────

class TestGetState:

    def test_state_values_after_input(self, area, random_input):
        area.receive_input(random_input)
        state = area.get_state()
        assert state['name'] == 'language'
        assert state['activation'] > 0.0
        assert state['specialty'] == ['syntax', 'semantics']
        assert state['thought_count'] == 1
        assert isinstance(state['avg_error'], float)
        assert isinstance(state['avg_activity'], float)

    def test_state_activation_matches(self, area, random_input):
        area.receive_input(random_input)
        state = area.get_state()
        assert abs(state['activation'] - area.activation) < 1e-6


# ─── reset ───────────────────────────────────────────────────────────────

class TestReset:

    def test_reset_zeros_activation(self, area, random_input):
        area.receive_input(random_input)
        assert area.activation > 0.0
        area.reset()
        assert area.activation == 0.0

    def test_reset_clears_thoughts(self, area, random_input):
        area.receive_input(random_input)
        area.reset()
        assert area.get_recent_thoughts() == []
        assert area.get_state()['thought_count'] == 0


# ─── Independence ────────────────────────────────────────────────────────

class TestIndependence:

    def test_multiple_areas_independent(self):
        cfg_a = CorticalAreaConfig(name="area_a", specialty=["vision"])
        cfg_b = CorticalAreaConfig(name="area_b", specialty=["audio"])
        area_a = CorticalArea(cfg_a)
        area_b = CorticalArea(cfg_b)

        rng = np.random.default_rng(55)
        inp = rng.standard_normal(8)
        area_a.receive_input(inp)

        assert area_a.activation > 0.0
        assert area_b.activation == 0.0
        assert area_a.get_state()['thought_count'] == 1
        assert area_b.get_state()['thought_count'] == 0

    def test_reset_one_does_not_affect_other(self):
        cfg_a = CorticalAreaConfig(name="area_a")
        cfg_b = CorticalAreaConfig(name="area_b")
        area_a = CorticalArea(cfg_a)
        area_b = CorticalArea(cfg_b)

        rng = np.random.default_rng(66)
        inp = rng.standard_normal(8)
        area_a.receive_input(inp)
        area_b.receive_input(inp)

        area_a.reset()
        assert area_a.activation == 0.0
        assert area_b.activation > 0.0


# ─── Edge cases ──────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_custom_layer_dim(self):
        cfg = CorticalAreaConfig(name="small", layer_dim=4)
        area = CorticalArea(cfg)
        result = area.receive_input(np.ones(4))
        assert 'output' in result
        assert len(result['output']) == 4

    def test_empty_specialty_list(self):
        cfg = CorticalAreaConfig(name="generic")
        area = CorticalArea(cfg)
        assert area.specialty == []
        assert area.get_state()['specialty'] == []

    def test_high_decay_rate(self):
        cfg = CorticalAreaConfig(name="volatile", decay_rate=0.5)
        area = CorticalArea(cfg)
        area.receive_input(np.ones(8))
        act_before = area.activation
        area.tick()
        # Should decay significantly
        assert area.activation < act_before
        assert area.activation == max(0.0, act_before - 0.5)

    def test_zero_decay_rate(self):
        cfg = CorticalAreaConfig(name="persistent", decay_rate=0.0)
        area = CorticalArea(cfg)
        area.receive_input(np.ones(8))
        act = area.activation
        area.tick()
        area.tick()
        area.tick()
        # No decay — activation unchanged
        assert area.activation == act

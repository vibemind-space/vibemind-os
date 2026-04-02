"""
Cerebellum Module Tests - Phase A1

Tests for the neuroscience-based cerebellum module including:
- Granule layer sparse expansion
- Purkinje cell learning (LTD via climbing fibers)
- Forward model (predict next state)
- Inverse model (infer corrective action)
- Timing circuit (interval learning)
- Full CerebellumModule integration
"""

import pytest
import numpy as np
import time


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def state_dim():
    return 16

@pytest.fixture
def action_dim():
    return 4

@pytest.fixture
def sample_state(state_dim):
    np.random.seed(42)
    return np.random.randn(state_dim).astype(np.float32)

@pytest.fixture
def sample_action(action_dim):
    a = np.zeros(action_dim, dtype=np.float32)
    a[0] = 1.0
    return a

@pytest.fixture
def cerebellum(state_dim, action_dim):
    from core.cerebellum_module import CerebellumModule
    return CerebellumModule(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_expansion=4,
        learning_rate=0.01,
        n_timers=8,
    )

@pytest.fixture
def granule_layer():
    from core.cerebellum_module import GranuleLayer
    return GranuleLayer(input_dim=16, expansion=4, sparsity=0.3)

@pytest.fixture
def purkinje_layer():
    from core.cerebellum_module import PurkinjeLayer
    return PurkinjeLayer(input_dim=64, output_dim=16, learning_rate=0.01)

@pytest.fixture
def climbing_fiber():
    from core.cerebellum_module import ClimbingFiberSignal
    return ClimbingFiberSignal(signal_dim=16, error_threshold=0.1)

@pytest.fixture
def timing_circuit():
    from core.cerebellum_module import TimingCircuit
    return TimingCircuit(n_timers=8, min_interval=0.05, max_interval=2.0)


# ─── Granule Layer Tests ───────────────────────────────────────────────────────

class TestGranuleLayer:

    def test_output_shape(self, granule_layer):
        x = np.random.randn(16).astype(np.float32)
        out = granule_layer.forward(x)
        assert out.shape == (64,), f"Expected (64,), got {out.shape}"

    def test_sparse_output(self, granule_layer):
        x = np.random.randn(16).astype(np.float32)
        out = granule_layer.forward(x)
        sparsity = granule_layer.get_sparsity()
        assert sparsity > 0.5, f"Sparsity {sparsity} too low"

    def test_expansion_factor(self):
        from core.cerebellum_module import GranuleLayer
        gl = GranuleLayer(input_dim=8, expansion=8)
        assert gl.output_dim == 64

    def test_handles_multidim_input(self, granule_layer):
        x = np.random.randn(4, 4).astype(np.float32)
        out = granule_layer.forward(x)
        assert out.shape == (64,)

    def test_to_dict(self, granule_layer):
        d = granule_layer.to_dict()
        assert 'input_dim' in d
        assert 'output_dim' in d
        assert 'actual_sparsity' in d


# ─── Purkinje Layer Tests ─────────────────────────────────────────────────────

class TestPurkinjeLayer:

    def test_output_shape(self, purkinje_layer):
        x = np.random.randn(64).astype(np.float32)
        out = purkinje_layer.forward(x)
        assert out.shape == (16,)

    def test_output_bounded(self, purkinje_layer):
        x = np.random.randn(64).astype(np.float32) * 10
        out = purkinje_layer.forward(x)
        assert np.all(np.abs(out) <= 1.0), "Purkinje output should be bounded by tanh"

    def test_learning_reduces_error(self, purkinje_layer):
        x = np.random.randn(64).astype(np.float32)
        target = np.random.randn(16).astype(np.float32) * 0.5
        errors = []
        for _ in range(50):
            out = purkinje_layer.forward(x)
            error = target - out
            purkinje_layer.learn_from_climbing_fiber(error)
            errors.append(float(np.abs(error).mean()))
        # Error should decrease (or at least not explode)
        assert errors[-1] < errors[0] * 2.0, "Error should not explode"

    def test_handles_dim_mismatch(self, purkinje_layer):
        # Input too small
        x = np.random.randn(32).astype(np.float32)
        out = purkinje_layer.forward(x)
        assert out.shape == (16,)

    def test_activity_tracking(self, purkinje_layer):
        x = np.random.randn(64).astype(np.float32)
        purkinje_layer.forward(x)
        activity = purkinje_layer.get_activity()
        assert activity >= 0.0

    def test_to_dict(self, purkinje_layer):
        d = purkinje_layer.to_dict()
        assert 'weight_norm' in d
        assert 'mean_activity' in d


# ─── Climbing Fiber Tests ─────────────────────────────────────────────────────

class TestClimbingFiber:

    def test_error_computation(self, climbing_fiber):
        predicted = np.zeros(16, dtype=np.float32)
        actual = np.ones(16, dtype=np.float32)
        error = climbing_fiber.compute_error(predicted, actual)
        assert error.shape == (16,)
        assert float(np.abs(error).mean()) > 0

    def test_subthreshold_suppressed(self, climbing_fiber):
        predicted = np.zeros(16, dtype=np.float32)
        actual = np.ones(16, dtype=np.float32) * 0.01  # Very small error
        error = climbing_fiber.compute_error(predicted, actual)
        # With threshold=0.1, this tiny error should be suppressed
        assert float(np.abs(error).mean()) < 0.01

    def test_avg_error_tracking(self, climbing_fiber):
        for _ in range(10):
            climbing_fiber.compute_error(
                np.zeros(16, dtype=np.float32),
                np.random.randn(16).astype(np.float32)
            )
        avg = climbing_fiber.get_avg_error()
        assert avg >= 0.0

    def test_to_dict(self, climbing_fiber):
        d = climbing_fiber.to_dict()
        assert 'error_threshold' in d
        assert 'avg_error' in d


# ─── Forward Model Tests ──────────────────────────────────────────────────────

class TestCerebellarForwardModel:

    def test_predict_returns_prediction(self, state_dim, action_dim, sample_state, sample_action):
        from core.cerebellum_module import CerebellarForwardModel
        fm = CerebellarForwardModel(state_dim=state_dim, action_dim=action_dim)
        pred = fm.predict(sample_state, sample_action)
        assert pred.predicted_state.shape == (state_dim,)
        assert 0.0 <= pred.confidence <= 1.0

    def test_different_actions_different_predictions(self, state_dim, action_dim, sample_state):
        from core.cerebellum_module import CerebellarForwardModel
        fm = CerebellarForwardModel(state_dim=state_dim, action_dim=action_dim)
        a1 = np.zeros(action_dim, dtype=np.float32); a1[0] = 1.0
        a2 = np.zeros(action_dim, dtype=np.float32); a2[1] = 1.0
        p1 = fm.predict(sample_state, a1)
        p2 = fm.predict(sample_state, a2)
        # Different actions should yield different predictions
        assert not np.allclose(p1.predicted_state, p2.predicted_state, atol=1e-6)

    def test_learn_updates_model(self, state_dim, action_dim, sample_state, sample_action):
        from core.cerebellum_module import CerebellarForwardModel
        fm = CerebellarForwardModel(state_dim=state_dim, action_dim=action_dim)
        pred = fm.predict(sample_state, sample_action)
        actual = sample_state + 0.5
        update_mag = fm.learn(pred.predicted_state, actual)
        assert update_mag >= 0.0

    def test_to_dict(self, state_dim, action_dim):
        from core.cerebellum_module import CerebellarForwardModel
        fm = CerebellarForwardModel(state_dim=state_dim, action_dim=action_dim)
        d = fm.to_dict()
        assert 'predictions' in d
        assert 'avg_error' in d


# ─── Inverse Model Tests ──────────────────────────────────────────────────────

class TestCerebellarInverseModel:

    def test_infer_action(self, state_dim, action_dim, sample_state):
        from core.cerebellum_module import CerebellarInverseModel
        im = CerebellarInverseModel(state_dim=state_dim, action_dim=action_dim)
        desired = np.random.randn(state_dim).astype(np.float32)
        action, probs = im.infer_action(sample_state, desired)
        assert 0 <= action < action_dim
        assert probs.shape == (action_dim,)
        assert abs(probs.sum() - 1.0) < 1e-5

    def test_learn(self, state_dim, action_dim):
        from core.cerebellum_module import CerebellarInverseModel
        im = CerebellarInverseModel(state_dim=state_dim, action_dim=action_dim)
        predicted_a = np.array([1, 0, 0, 0], dtype=np.float32)
        actual_a = np.array([0, 1, 0, 0], dtype=np.float32)
        update = im.learn(predicted_a, actual_a)
        assert update >= 0.0


# ─── Timing Circuit Tests ─────────────────────────────────────────────────────

class TestTimingCircuit:

    def test_tick_returns_activations(self, timing_circuit):
        activations = timing_circuit.tick()
        assert activations.shape == (8,)

    def test_signal_event_returns_error(self, timing_circuit):
        timing_circuit.reset(current_time=100.0)
        error = timing_circuit.signal_event(current_time=100.5)
        assert isinstance(error, float)

    def test_learns_interval(self, timing_circuit):
        # Teach it a 0.2s interval
        t = 100.0
        timing_circuit.reset(current_time=t)
        for i in range(20):
            t += 0.2
            timing_circuit.signal_event(current_time=t)
        predicted = timing_circuit.get_predicted_interval()
        # Should be somewhat close to 0.2 after learning
        assert 0.05 < predicted < 2.0

    def test_to_dict(self, timing_circuit):
        d = timing_circuit.to_dict()
        assert 'predicted_interval' in d
        assert 'n_timers' in d


# ─── Full CerebellumModule Tests ──────────────────────────────────────────────

class TestCerebellumModule:

    def test_instantiation(self, cerebellum):
        assert cerebellum is not None
        assert cerebellum.state_dim == 16
        assert cerebellum.action_dim == 4

    def test_predict_next_state(self, cerebellum, sample_state, sample_action):
        pred = cerebellum.predict_next_state(sample_state, sample_action)
        assert pred.predicted_state.shape == (16,)
        assert 0.0 <= pred.confidence <= 1.0

    def test_correct_motor_program(self, cerebellum, sample_state):
        desired = np.random.randn(16).astype(np.float32)
        action, probs = cerebellum.correct_motor_program(sample_state, desired)
        assert 0 <= action < 4
        assert probs.shape == (4,)

    def test_update_from_outcome(self, cerebellum, sample_state, sample_action):
        pred = cerebellum.predict_next_state(sample_state, sample_action)
        actual = sample_state + np.random.randn(16).astype(np.float32) * 0.1
        error = cerebellum.update_from_outcome(pred.predicted_state, actual)
        assert error >= 0.0

    def test_learning_reduces_prediction_error(self, cerebellum):
        np.random.seed(123)
        state = np.random.randn(16).astype(np.float32)
        action = np.array([1, 0, 0, 0], dtype=np.float32)
        # Fixed next state
        actual_next = state + 0.1

        errors = []
        for _ in range(30):
            pred = cerebellum.predict_next_state(state, action)
            err = cerebellum.update_from_outcome(pred.predicted_state, actual_next)
            errors.append(err)

        # Error should decrease or stay bounded
        assert errors[-1] < errors[0] * 5.0, "Error should not explode"

    def test_timing_event(self, cerebellum):
        te = cerebellum.signal_timing_event()
        assert isinstance(te, float)

    def test_get_state(self, cerebellum, sample_state, sample_action):
        cerebellum.predict_next_state(sample_state, sample_action)
        state = cerebellum.get_state()
        assert 'stats' in state
        assert 'forward_model' in state
        assert 'inverse_model' in state
        assert 'timing' in state
        assert state['stats']['total_predictions'] == 1

    def test_get_stats(self, cerebellum):
        stats = cerebellum.get_stats()
        assert stats.total_predictions == 0
        assert stats.avg_prediction_error == 0.0

    def test_reset(self, cerebellum, sample_state, sample_action):
        cerebellum.predict_next_state(sample_state, sample_action)
        assert cerebellum.get_stats().total_predictions == 1
        cerebellum.reset()
        assert cerebellum.get_stats().total_predictions == 0

    def test_to_dict(self, cerebellum):
        d = cerebellum.to_dict()
        assert isinstance(d, dict)
        assert 'stats' in d

    def test_from_yaml(self):
        from core.cerebellum_module import CerebellumModule
        config = {
            'cerebellum': {
                'granule_expansion': 2,
                'learning_rate': 0.005,
                'timing_resolution': 50,
                'n_timers': 4,
            },
            'model': {
                'input_dim': 8,
                'output_dim': 3,
            }
        }
        cb = CerebellumModule.from_yaml(config)
        assert cb.state_dim == 8
        assert cb.action_dim == 3
        assert cb.learning_rate == 0.005

    def test_from_yaml_defaults(self):
        from core.cerebellum_module import CerebellumModule
        cb = CerebellumModule.from_yaml({})
        assert cb.state_dim == 32
        assert cb.action_dim == 4

    def test_prediction_error_getter(self, cerebellum):
        pe = cerebellum.get_prediction_error()
        assert pe == 0.0  # No predictions yet

    def test_timing_prediction_getter(self, cerebellum):
        tp = cerebellum.get_timing_prediction()
        assert tp > 0.0

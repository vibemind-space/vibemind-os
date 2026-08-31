"""
Prefrontal Cortex Tests - Phase A2

Tests for working memory, cognitive control, value estimation,
reward prediction, inhibitory control, and PFC integration.
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
def pfc(state_dim):
    from core.prefrontal_cortex import PrefrontalCortex
    return PrefrontalCortex(state_dim=state_dim, working_memory_capacity=5)


class TestWorkingMemoryBuffer:

    def test_store_and_retrieve(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=5, state_dim=state_dim)
        content = np.random.randn(state_dim).astype(np.float32)
        wm.store(content, label="item1")
        items = wm.retrieve(top_k=1)
        assert len(items) == 1
        assert items[0].label == "item1"

    def test_capacity_limit(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=3, state_dim=state_dim)
        for i in range(5):
            wm.store(np.random.randn(state_dim).astype(np.float32), label=f"item{i}")
        assert wm.count <= 3

    def test_relevance_decay(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=5, state_dim=state_dim, decay_rate=0.5)
        wm.store(np.random.randn(state_dim).astype(np.float32), label="decaying")
        wm.tick()
        items = wm.retrieve(top_k=1)
        assert items[0].relevance < 1.0

    def test_query_retrieval(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=5, state_dim=state_dim)
        v1 = np.ones(state_dim, dtype=np.float32)
        v2 = -np.ones(state_dim, dtype=np.float32)
        wm.store(v1, label="positive")
        wm.store(v2, label="negative")
        result = wm.retrieve(query=np.ones(state_dim, dtype=np.float32), top_k=1)
        assert result[0].label == "positive"

    def test_contents_vector(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=5, state_dim=state_dim)
        wm.store(np.ones(state_dim, dtype=np.float32))
        vec = wm.get_contents_vector()
        assert vec.shape == (state_dim,)

    def test_refresh(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=5, state_dim=state_dim, decay_rate=0.5)
        wm.store(np.random.randn(state_dim).astype(np.float32), label="kept")
        wm.tick()
        wm.refresh("kept")
        items = wm.retrieve(top_k=1)
        assert items[0].relevance == 1.0

    def test_clear(self, state_dim):
        from core.prefrontal_cortex import WorkingMemoryBuffer
        wm = WorkingMemoryBuffer(capacity=5, state_dim=state_dim)
        wm.store(np.random.randn(state_dim).astype(np.float32))
        wm.clear()
        assert wm.count == 0


class TestCognitiveControlUnit:

    def test_register_and_select(self, state_dim):
        from core.prefrontal_cortex import CognitiveControlUnit
        ccu = CognitiveControlUnit(n_rules=5, state_dim=state_dim)
        rule = np.ones(state_dim, dtype=np.float32)
        ccu.register_task("task_a", rule, priority=1.0)
        name, bias = ccu.select_task(rule)
        assert name == "task_a"
        assert bias.shape[0] > 0

    def test_task_switching(self, state_dim):
        from core.prefrontal_cortex import CognitiveControlUnit
        ccu = CognitiveControlUnit(n_rules=5, state_dim=state_dim, switch_cost=0.0)
        ccu.register_task("a", np.array([1] * state_dim, dtype=np.float32))
        ccu.register_task("b", np.array([-1] * state_dim, dtype=np.float32))
        ccu.select_task(np.ones(state_dim, dtype=np.float32))
        ccu.select_task(-np.ones(state_dim, dtype=np.float32))
        assert ccu.switch_count >= 1

    def test_switch_cost(self, state_dim):
        from core.prefrontal_cortex import CognitiveControlUnit
        ccu = CognitiveControlUnit(n_rules=5, state_dim=state_dim, switch_cost=100.0)
        ccu.register_task("a", np.ones(state_dim, dtype=np.float32))
        ccu.register_task("b", np.ones(state_dim, dtype=np.float32) * 1.01)
        ccu.select_task(np.ones(state_dim, dtype=np.float32))
        # With huge switch cost, should prefer staying on same task
        name, _ = ccu.select_task(np.ones(state_dim, dtype=np.float32) * 1.01)
        assert ccu.switch_count <= 1


class TestValueEstimator:

    def test_estimate_value(self, state_dim):
        from core.prefrontal_cortex import ValueEstimator
        ve = ValueEstimator(state_dim=state_dim)
        v = ve.estimate_value(np.random.randn(state_dim).astype(np.float32))
        assert isinstance(v, float)

    def test_learning(self, state_dim):
        from core.prefrontal_cortex import ValueEstimator
        ve = ValueEstimator(state_dim=state_dim, learning_rate=0.1)
        state = np.ones(state_dim, dtype=np.float32)
        for _ in range(50):
            ve.update(state, target_value=1.0)
        v = ve.estimate_value(state)
        assert v > 0.5


class TestRewardPredictionUnit:

    def test_predict_reward(self, state_dim):
        from core.prefrontal_cortex import RewardPredictionUnit
        rpu = RewardPredictionUnit(state_dim=state_dim, n_outcomes=4)
        pred = rpu.predict_reward(np.random.randn(state_dim).astype(np.float32))
        assert pred.shape == (4,)

    def test_expectation_update(self, state_dim):
        from core.prefrontal_cortex import RewardPredictionUnit
        rpu = RewardPredictionUnit(state_dim=state_dim)
        state = np.random.randn(state_dim).astype(np.float32)
        rpe = rpu.update_expectation(state, outcome_idx=0, actual_reward=1.0)
        assert isinstance(rpe, float)


class TestInhibitoryControl:

    def test_inhibit_high_conflict(self):
        from core.prefrontal_cortex import InhibitoryControl
        ic = InhibitoryControl(threshold=0.5)
        assert ic.should_inhibit(action_urgency=0.3, conflict_level=0.8) is True

    def test_no_inhibit_low_conflict(self):
        from core.prefrontal_cortex import InhibitoryControl
        ic = InhibitoryControl(threshold=0.5)
        assert ic.should_inhibit(action_urgency=0.8, conflict_level=0.2) is False


class TestPrefrontalCortex:

    def test_instantiation(self, pfc):
        assert pfc is not None
        assert pfc.state_dim == 16

    def test_process(self, pfc, sample_state):
        result = pfc.process(sample_state)
        assert 'bias_signal' in result
        assert 'value' in result
        assert 'inhibit' in result

    def test_learn_from_outcome(self, pfc, sample_state):
        errors = pfc.learn_from_outcome(sample_state, reward=1.0)
        assert 'value_error' in errors
        assert 'reward_prediction_error' in errors

    def test_get_state(self, pfc, sample_state):
        pfc.process(sample_state)
        state = pfc.get_state()
        assert 'stats' in state
        assert 'working_memory' in state

    def test_reset(self, pfc, sample_state):
        pfc.process(sample_state)
        pfc.reset()
        assert pfc.working_memory.count == 0

    def test_from_yaml(self):
        from core.prefrontal_cortex import PrefrontalCortex
        pfc = PrefrontalCortex.from_yaml({
            'prefrontal_cortex': {'working_memory_capacity': 5}
        })
        assert pfc.working_memory.capacity == 5

    def test_from_yaml_defaults(self):
        from core.prefrontal_cortex import PrefrontalCortex
        pfc = PrefrontalCortex.from_yaml({})
        assert pfc.working_memory.capacity == 7

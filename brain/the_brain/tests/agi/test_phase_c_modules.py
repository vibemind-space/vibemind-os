"""
Phase C Module Tests - Entorhinal Cortex, Nucleus Accumbens, Anterior Cingulate

Tests for the three upgrade modules that complement existing
hippocampus, basal ganglia, and cortical feedback systems.
"""

import pytest
import numpy as np


# ─── Entorhinal Cortex Tests ──────────────────────────────────────────────────

class TestGridCellModule:

    def test_compute_activation(self):
        from core.entorhinal_cortex import GridCellModule
        gc = GridCellModule(module_id=0, grid_scale=1.0, dim=8)
        act = gc.compute_activation(np.array([0.5, 0.5]))
        assert act.shape == (8,)
        assert np.all(act >= 0) and np.all(act <= 1)

    def test_different_scales(self):
        from core.entorhinal_cortex import GridCellModule
        gc1 = GridCellModule(0, grid_scale=0.5, dim=8)
        gc2 = GridCellModule(1, grid_scale=2.0, dim=8)
        pos = np.array([1.0, 0.0])
        a1 = gc1.compute_activation(pos)
        a2 = gc2.compute_activation(pos)
        assert not np.allclose(a1, a2)

    def test_phase_update(self):
        from core.entorhinal_cortex import GridCellModule
        gc = GridCellModule(0, grid_scale=1.0, dim=8)
        gc.update_phase(np.array([0.1, 0.2]))
        assert not np.allclose(gc.phase, 0.0)


class TestBorderCellLayer:

    def test_detect_boundaries(self):
        from core.entorhinal_cortex import BorderCellLayer
        bc = BorderCellLayer(boundary_dim=4)
        act = bc.detect_boundaries(np.array([0.01, 0.5, 0.99, 0.3]))
        assert act.shape == (4,)


class TestHeadDirectionRing:

    def test_update(self):
        from core.entorhinal_cortex import HeadDirectionRing
        hd = HeadDirectionRing(n_directions=8)
        act = hd.update(angular_velocity=0.5)
        assert act.shape == (8,)
        assert act.max() > 0.5  # Should have a clear peak

    def test_direction_wraps(self):
        from core.entorhinal_cortex import HeadDirectionRing
        hd = HeadDirectionRing(n_directions=8)
        for _ in range(100):
            hd.update(angular_velocity=0.1)
        assert 0 <= hd.direction < 2 * np.pi


class TestMemoryGateway:

    def test_encode(self):
        from core.entorhinal_cortex import MemoryGateway
        mg = MemoryGateway(cortical_dim=16, hippocampal_dim=8)
        encoded = mg.encode(np.random.randn(16).astype(np.float32))
        assert encoded.shape == (8,)
        assert np.all(np.abs(encoded) <= 1.0)  # tanh bounded

    def test_retrieve(self):
        from core.entorhinal_cortex import MemoryGateway
        mg = MemoryGateway(cortical_dim=16, hippocampal_dim=8)
        retrieved = mg.retrieve(np.random.randn(8).astype(np.float32))
        assert retrieved.shape == (16,)


class TestEntorhinalCortex:

    def test_instantiation(self):
        from core.entorhinal_cortex import EntorhinalCortex
        ec = EntorhinalCortex(state_dim=16)
        assert ec is not None

    def test_process_input(self):
        from core.entorhinal_cortex import EntorhinalCortex
        ec = EntorhinalCortex(state_dim=16)
        encoded = ec.process_input(np.random.randn(16).astype(np.float32))
        assert encoded.shape == (8,)  # hippocampal_dim = state_dim // 2

    def test_update_spatial(self):
        from core.entorhinal_cortex import EntorhinalCortex
        ec = EntorhinalCortex(state_dim=16)
        result = ec.update_spatial(
            position=np.array([1.0, 2.0]),
            velocity=np.array([0.1, 0.2]),
        )
        assert 'grid_activations' in result
        assert 'head_direction' in result
        assert len(result['grid_activations']) == 4

    def test_get_state(self):
        from core.entorhinal_cortex import EntorhinalCortex
        ec = EntorhinalCortex()
        state = ec.get_state()
        assert 'stats' in state

    def test_from_yaml(self):
        from core.entorhinal_cortex import EntorhinalCortex
        ec = EntorhinalCortex.from_yaml({})
        assert ec is not None


# ─── Nucleus Accumbens Tests ──────────────────────────────────────────────────

class TestRewardGate:

    def test_process_dopamine(self):
        from core.nucleus_accumbens import RewardGate
        rg = RewardGate()
        go, nogo = rg.process_dopamine(0.8)
        assert go > nogo  # High DA = more Go
        go2, nogo2 = rg.process_dopamine(0.2)
        assert nogo2 > go2  # Low DA = more NoGo

    def test_avg_reward(self):
        from core.nucleus_accumbens import RewardGate
        rg = RewardGate()
        for _ in range(10):
            rg.process_dopamine(0.7)
        assert rg.get_avg_reward() > 0.5


class TestApproachAvoidanceBalance:

    def test_approach(self):
        from core.nucleus_accumbens import ApproachAvoidanceBalance
        ab = ApproachAvoidanceBalance()
        decision, val = ab.evaluate(reward_prediction=0.9, threat_level=0.1, effort_cost=0.1)
        assert decision == "approach"

    def test_avoid(self):
        from core.nucleus_accumbens import ApproachAvoidanceBalance
        ab = ApproachAvoidanceBalance()
        decision, val = ab.evaluate(reward_prediction=0.1, threat_level=0.9, effort_cost=0.9)
        assert decision == "avoid"


class TestEffortComputation:

    def test_effort_increases_with_complexity(self):
        from core.nucleus_accumbens import EffortComputation
        ec = EffortComputation()
        low = ec.compute_effort(0.2, current_energy=1.0)
        high = ec.compute_effort(0.8, current_energy=1.0)
        assert high > low

    def test_effort_increases_when_tired(self):
        from core.nucleus_accumbens import EffortComputation
        ec = EffortComputation()
        rested = ec.compute_effort(0.5, current_energy=1.0)
        tired = ec.compute_effort(0.5, current_energy=0.1)
        assert tired > rested


class TestNucleusAccumbens:

    def test_instantiation(self):
        from core.nucleus_accumbens import NucleusAccumbens
        nacc = NucleusAccumbens()
        assert nacc is not None

    def test_evaluate(self):
        from core.nucleus_accumbens import NucleusAccumbens
        nacc = NucleusAccumbens()
        result = nacc.evaluate(dopamine=0.8, reward_prediction=0.7)
        assert 'go_drive' in result
        assert 'decision' in result
        assert result['go_drive'] > result['nogo_drive']

    def test_get_state(self):
        from core.nucleus_accumbens import NucleusAccumbens
        nacc = NucleusAccumbens()
        nacc.evaluate()
        state = nacc.get_state()
        assert 'stats' in state

    def test_from_yaml(self):
        from core.nucleus_accumbens import NucleusAccumbens
        nacc = NucleusAccumbens.from_yaml({})
        assert nacc is not None


# ─── Anterior Cingulate Cortex Tests ──────────────────────────────────────────

class TestConflictMonitor:

    def test_low_conflict(self):
        from core.anterior_cingulate import ConflictMonitor
        cm = ConflictMonitor(n_channels=4)
        conflict = cm.compute_conflict(np.array([0.9, 0.01, 0.01, 0.01]))
        assert conflict < 0.5

    def test_high_conflict(self):
        from core.anterior_cingulate import ConflictMonitor
        cm = ConflictMonitor(n_channels=4)
        conflict = cm.compute_conflict(np.array([0.5, 0.5, 0.5, 0.5]))
        assert conflict > 0.8  # Uniform = max entropy

    def test_zero_activation(self):
        from core.anterior_cingulate import ConflictMonitor
        cm = ConflictMonitor(n_channels=4)
        conflict = cm.compute_conflict(np.zeros(4))
        assert conflict == 0.0


class TestErrorLikelihoodEstimator:

    def test_estimate_without_history(self):
        from core.anterior_cingulate import ErrorLikelihoodEstimator
        ele = ErrorLikelihoodEstimator()
        est = ele.estimate_error_likelihood(conflict=0.5)
        assert 0.0 <= est <= 1.0

    def test_estimate_with_errors(self):
        from core.anterior_cingulate import ErrorLikelihoodEstimator
        ele = ErrorLikelihoodEstimator()
        for _ in range(10):
            ele.record_outcome(True)
        est = ele.estimate_error_likelihood(conflict=0.5)
        assert est > 0.5


class TestCognitiveEffortAllocator:

    def test_allocate_effort(self):
        from core.anterior_cingulate import CognitiveEffortAllocator
        cea = CognitiveEffortAllocator()
        effort = cea.allocate_effort(conflict=0.8, error_likelihood=0.6, reward_magnitude=0.9)
        assert effort > 0.5

    def test_low_conflict_low_effort(self):
        from core.anterior_cingulate import CognitiveEffortAllocator
        cea = CognitiveEffortAllocator()
        effort = cea.allocate_effort(conflict=0.1, error_likelihood=0.1, reward_magnitude=0.1)
        assert effort < 0.3


class TestAnteriorCingulateCortex:

    def test_instantiation(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex()
        assert acc is not None

    def test_process(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex()
        result = acc.process(np.array([0.5, 0.5, 0.1, 0.1]))
        assert 'conflict' in result
        assert 'error_likelihood' in result
        assert 'effort' in result
        assert 'control_signal' in result

    def test_high_conflict_detection(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex(conflict_threshold=0.5)
        result = acc.process(np.array([0.5, 0.5, 0.5, 0.5]))
        assert result['is_high_conflict']

    def test_record_outcome(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex()
        acc.record_outcome(True)
        acc.record_outcome(False)
        assert acc.get_stats().total_errors_detected == 1

    def test_get_state(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex()
        acc.process(np.array([0.5, 0.5, 0.1, 0.1]))
        state = acc.get_state()
        assert 'stats' in state
        assert 'conflict' in state

    def test_from_yaml(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex.from_yaml({
            'anterior_cingulate': {'conflict_threshold': 0.7}
        })
        assert acc.conflict_monitor.conflict_threshold == 0.7

    def test_from_yaml_defaults(self):
        from core.anterior_cingulate import AnteriorCingulateCortex
        acc = AnteriorCingulateCortex.from_yaml({})
        assert acc is not None

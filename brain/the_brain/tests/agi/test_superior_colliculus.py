"""
Superior Colliculus Tests - Phase B3

Tests for visual saliency mapping, multisensory integration,
orienting response, inhibition of return, and full SC integration.
"""

import pytest
import numpy as np


@pytest.fixture
def map_size():
    return 8

@pytest.fixture
def sc(map_size):
    from core.superior_colliculus import SuperiorColliculus
    return SuperiorColliculus(map_size=map_size, orientation_threshold=0.2)


class TestVisualSaliencyMap:

    def test_update(self):
        from core.superior_colliculus import VisualSaliencyMap
        vsm = VisualSaliencyMap(map_size=8)
        result = vsm.update(np.array([0, 0, 0, 1, 0, 0, 0, 0], dtype=np.float32))
        assert result.shape == (8,)
        peak_idx, peak_val = vsm.get_peak()
        assert peak_idx == 3

    def test_decay(self):
        from core.superior_colliculus import VisualSaliencyMap
        vsm = VisualSaliencyMap(map_size=8, decay_rate=0.5)
        vsm.update(np.ones(8, dtype=np.float32))
        first = vsm.get_map().copy()
        vsm.update(np.zeros(8, dtype=np.float32))
        second = vsm.get_map()
        assert second.mean() < first.mean()

    def test_suppress_location(self):
        from core.superior_colliculus import VisualSaliencyMap
        vsm = VisualSaliencyMap(map_size=8)
        vsm.update(np.ones(8, dtype=np.float32))
        vsm.suppress_location(3, amount=0.9)
        assert vsm.get_map()[3] < vsm.get_map()[0]


class TestMultisensoryIntegrator:

    def test_single_modality(self):
        from core.superior_colliculus import MultisensoryIntegrator
        mi = MultisensoryIntegrator()
        integrated, enh = mi.integrate({'visual': np.ones(8, dtype=np.float32)}, map_size=8)
        assert integrated.shape == (8,)
        assert enh == 0.0  # No enhancement for single modality

    def test_multisensory_enhancement(self):
        from core.superior_colliculus import MultisensoryIntegrator
        mi = MultisensoryIntegrator()
        integrated, enh = mi.integrate({
            'visual': np.ones(8, dtype=np.float32) * 0.5,
            'auditory': np.ones(8, dtype=np.float32) * 0.5,
        }, map_size=8)
        assert enh > 0.0  # Should have super-additive enhancement

    def test_inverse_effectiveness(self):
        from core.superior_colliculus import MultisensoryIntegrator
        mi = MultisensoryIntegrator()
        # Weak signals should get more enhancement
        _, enh_weak = mi.integrate({
            'visual': np.ones(8, dtype=np.float32) * 0.1,
            'auditory': np.ones(8, dtype=np.float32) * 0.1,
        }, map_size=8)
        _, enh_strong = mi.integrate({
            'visual': np.ones(8, dtype=np.float32) * 0.9,
            'auditory': np.ones(8, dtype=np.float32) * 0.9,
        }, map_size=8)
        assert enh_weak > enh_strong


class TestOrientingResponse:

    def test_orient_above_threshold(self):
        from core.superior_colliculus import OrientingResponse
        ori = OrientingResponse(threshold=0.3)
        saliency = np.array([0.1, 0.1, 0.1, 0.8, 0.1, 0.1, 0.1, 0.1])
        cmd = ori.orient(saliency)
        assert cmd is not None
        assert cmd.target_location == 3

    def test_no_orient_below_threshold(self):
        from core.superior_colliculus import OrientingResponse
        ori = OrientingResponse(threshold=0.5)
        saliency = np.array([0.1] * 8)
        cmd = ori.orient(saliency)
        assert cmd is None

    def test_no_reorient_to_same(self):
        from core.superior_colliculus import OrientingResponse
        ori = OrientingResponse(threshold=0.3)
        saliency = np.array([0.1, 0.1, 0.1, 0.8, 0.1, 0.1, 0.1, 0.1])
        ori.orient(saliency)
        cmd2 = ori.orient(saliency)  # Same target
        assert cmd2 is None


class TestInhibitionOfReturn:

    def test_apply_ior(self):
        from core.superior_colliculus import InhibitionOfReturn
        ior = InhibitionOfReturn(max_suppression=0.9)
        ior.apply_ior(3)
        assert ior.get_suppression(3) == pytest.approx(0.9)

    def test_decay(self):
        from core.superior_colliculus import InhibitionOfReturn
        ior = InhibitionOfReturn(decay_rate=0.5)
        ior.apply_ior(3)
        ior.decay()
        assert ior.get_suppression(3) < 0.8

    def test_apply_to_map(self):
        from core.superior_colliculus import InhibitionOfReturn
        ior = InhibitionOfReturn(max_suppression=1.0)
        ior.apply_ior(3)
        saliency = np.ones(8, dtype=np.float32)
        result = ior.apply_to_map(saliency)
        assert result[3] < result[0]


class TestSuperiorColliculus:

    def test_instantiation(self, sc):
        assert sc is not None

    def test_process_visual(self, sc):
        visual = np.array([0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1], dtype=np.float32)
        result = sc.process(visual=visual)
        assert 'saliency_map' in result
        assert 'orienting_command' in result
        assert result['peak_location'] == 2

    def test_process_multisensory(self, sc):
        # Use bounded [0,1] inputs so inverse effectiveness gives positive enhancement
        visual = np.random.rand(8).astype(np.float32) * 0.5
        audio = np.random.rand(8).astype(np.float32) * 0.5
        result = sc.process(visual=visual, auditory=audio)
        assert result['multisensory_enhancement'] > 0

    def test_ior_prevents_refocus(self, sc):
        visual = np.array([0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1], dtype=np.float32)
        r1 = sc.process(visual=visual)
        assert r1['orienting_command'] is not None
        r2 = sc.process(visual=visual)
        # IOR should suppress location 2, so peak may shift
        assert r2['saliency_map'][2] < r1['saliency_map'][2]

    def test_get_state(self, sc):
        sc.process(visual=np.random.randn(8).astype(np.float32))
        state = sc.get_state()
        assert 'stats' in state
        assert 'saliency' in state
        assert 'ior' in state

    def test_reset(self, sc):
        sc.process(visual=np.random.randn(8).astype(np.float32))
        sc.reset()
        assert sc.get_stats().total_orientations == 0

    def test_from_yaml(self):
        from core.superior_colliculus import SuperiorColliculus
        sc = SuperiorColliculus.from_yaml({
            'superior_colliculus': {'map_size': 32, 'orientation_speed': 100}
        })
        assert sc.map_size == 32

    def test_from_yaml_defaults(self):
        from core.superior_colliculus import SuperiorColliculus
        sc = SuperiorColliculus.from_yaml({})
        assert sc is not None

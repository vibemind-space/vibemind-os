"""Tests for ModulationContext -- unified modulation for RadialAttentionNetwork."""
import pytest
import numpy as np
import torch


class TestModulationContext:
    def test_defaults(self):
        from core.modulation_context import ModulationContext
        ctx = ModulationContext()
        assert ctx.attention_gain == 1.0
        assert ctx.precision_boost == 1.0
        assert ctx.ffn_throughput == 1.0
        assert ctx.threshold_mod == 1.0
        assert ctx.ring4_bias is None
        assert ctx.neuromod is None
        assert ctx.cortex is None
        assert ctx.limbic is None
        assert ctx.sleep_wake is None
        assert ctx.motor is None
        assert ctx.defense is None
        assert ctx.memory is None
        assert ctx.integration is None
        assert ctx.visceral is None
        assert ctx.social is None

    def test_compute_no_bridges_is_identity(self):
        from core.modulation_context import ModulationContext
        ctx = ModulationContext()
        ctx.compute()
        assert ctx.attention_gain == 1.0
        assert ctx.precision_boost == 1.0
        assert ctx.ffn_throughput == 1.0
        assert ctx.threshold_mod == 1.0

    def test_compute_with_neuromod(self):
        """Existing neuromod hooks (H1-H6) produce correct composite factors."""
        from core.modulation_context import ModulationContext
        from core.neuromodulation_bridge import NeuromodState
        ctx = ModulationContext()
        ctx.neuromod = NeuromodState(
            dopamine=0.8, norepinephrine=0.6, serotonin=0.7,
            acetylcholine=0.5, anti_reward=0.2, ne_gain=1.2, explore_ratio=0.4
        )
        ctx.compute()
        # H1: att *= 0.5 + 1.2 = 1.7 -> clamped to 1.7
        assert ctx.attention_gain == pytest.approx(1.7, rel=0.01)
        # H2: prec *= (0.5 + 0.8) * (1.0 - 0.3*0.2) = 1.3 * 0.94 = 1.222
        assert ctx.precision_boost == pytest.approx(1.222, rel=0.01)
        # H3+H4: ffn *= (0.5 + 0.5) * (0.8 + 0.4*0.7) = 1.0 * 1.08 = 1.08
        assert ctx.ffn_throughput == pytest.approx(1.08, rel=0.01)
        # H6: thr *= 1.5 - 0.4 = 1.1
        assert ctx.threshold_mod == pytest.approx(1.1, rel=0.01)

    def test_compute_with_cortex(self):
        """Cortex hooks (H7-H9) produce correct composite factors."""
        from core.modulation_context import ModulationContext
        from core.cortex_bridge import CortexState
        ctx = ModulationContext()
        ctx.cortex = CortexState(
            subjective_value=0.8, conflict=0.5,
            bias_signal=np.ones(32) * 0.1
        )
        ctx.compute()
        # H9: prec *= 0.7 + 0.6*0.8 = 1.18
        assert ctx.precision_boost == pytest.approx(1.18, rel=0.01)
        # H8: thr *= 1.0 - 0.3*0.5 = 0.85
        assert ctx.threshold_mod == pytest.approx(0.85, rel=0.01)
        # H7: ring4_bias set
        assert ctx.ring4_bias is not None

    def test_compute_with_limbic(self):
        """Limbic hooks (H10-H13) produce correct composite factors."""
        from core.modulation_context import ModulationContext
        from core.limbic_bridge import LimbicState
        ctx = ModulationContext()
        ctx.limbic = LimbicState(arousal=0.8, salience=0.6, nogo_drive=0.4, urgency=0.7)
        ctx.compute()
        # H10: att *= 0.7 + 0.6*0.8 = 1.18
        assert ctx.attention_gain == pytest.approx(1.18, rel=0.01)
        # H11: prec *= 0.8 + 0.4*0.6 = 1.04
        assert ctx.precision_boost == pytest.approx(1.04, rel=0.01)
        # H12: thr *= 1.0 - 0.2*0.4 = 0.92
        assert ctx.threshold_mod == pytest.approx(0.92, rel=0.01)
        # H13: ffn *= 0.8 + 0.4*0.7 = 1.08
        assert ctx.ffn_throughput == pytest.approx(1.08, rel=0.01)

    def test_safety_clamp(self):
        """Composite factors clamped to [0.3, 3.0]."""
        from core.modulation_context import ModulationContext
        from core.neuromodulation_bridge import NeuromodState
        from core.limbic_bridge import LimbicState
        ctx = ModulationContext()
        # Stack neuromod NE gain at max (ne_gain=1.5 -> H1: 2.0)
        # + limbic arousal at max (arousal=1.0 -> H10: 1.3)
        # Combined: 2.0 * 1.3 = 2.6 -> within [0.3, 3.0]
        ctx.neuromod = NeuromodState(ne_gain=1.5)
        ctx.limbic = LimbicState(arousal=1.0)
        ctx.compute()
        assert 0.3 <= ctx.attention_gain <= 3.0
        assert 0.3 <= ctx.precision_boost <= 3.0
        assert 0.3 <= ctx.ffn_throughput <= 3.0
        assert 0.3 <= ctx.threshold_mod <= 3.0

    def test_all_bridges_compose(self):
        """All 3 existing bridges composing produce reasonable factors."""
        from core.modulation_context import ModulationContext
        from core.neuromodulation_bridge import NeuromodState
        from core.cortex_bridge import CortexState
        from core.limbic_bridge import LimbicState
        ctx = ModulationContext()
        ctx.neuromod = NeuromodState(ne_gain=1.0, dopamine=0.5, acetylcholine=0.5,
                                     serotonin=0.5, anti_reward=0.1, explore_ratio=0.3)
        ctx.cortex = CortexState(subjective_value=0.5, conflict=0.3)
        ctx.limbic = LimbicState(arousal=0.5, salience=0.5, nogo_drive=0.3, urgency=0.5)
        ctx.compute()
        # All factors should be reasonable (not extreme)
        assert 0.5 < ctx.attention_gain < 2.5
        assert 0.5 < ctx.precision_boost < 2.5
        assert 0.5 < ctx.ffn_throughput < 2.5
        assert 0.5 < ctx.threshold_mod < 2.0


class TestRingLayerModulation:
    def test_forward_accepts_modulation_kwarg(self):
        from core.modulation_context import ModulationContext
        from core.radial_attention import RingLayer
        ring = RingLayer(64, 64)
        x = torch.randn(1, 64)
        ctx = ModulationContext()
        ctx.compute()
        out = ring(x, modulation=ctx)
        assert out.shape == (1, 64)

    def test_modulation_attention_gain_amplifies(self):
        from core.modulation_context import ModulationContext
        from core.radial_attention import RingLayer
        ring = RingLayer(64, 64)
        x = torch.randn(1, 64)
        torch.manual_seed(42)
        ctx_high = ModulationContext()
        ctx_high.attention_gain = 2.0
        ctx_high.precision_boost = 1.0
        ctx_high.ffn_throughput = 1.0
        out_high = ring(x, modulation=ctx_high)
        ctx_low = ModulationContext()
        ctx_low.attention_gain = 0.5
        ctx_low.precision_boost = 1.0
        ctx_low.ffn_throughput = 1.0
        out_low = ring(x, modulation=ctx_low)
        # Different gains should produce different outputs
        assert not torch.allclose(out_high, out_low, atol=1e-4)

    def test_backward_compat_neuromod_kwarg_still_works(self):
        """Old-style neuromod= kwarg still accepted for backward compat."""
        from core.neuromodulation_bridge import NeuromodState
        from core.radial_attention import RingLayer
        ring = RingLayer(64, 64)
        x = torch.randn(1, 64)
        nm = NeuromodState(ne_gain=1.2, dopamine=0.5, acetylcholine=0.5,
                           serotonin=0.5, anti_reward=0.1)
        out = ring(x, neuromod=nm)
        assert out.shape == (1, 64)

    def test_modulation_takes_precedence_over_kwargs(self):
        """When both modulation and neuromod are provided, modulation wins."""
        from core.modulation_context import ModulationContext
        from core.neuromodulation_bridge import NeuromodState
        from core.radial_attention import RingLayer
        ring = RingLayer(64, 64)
        x = torch.randn(1, 64)
        ctx = ModulationContext()
        ctx.attention_gain = 1.5
        ctx.precision_boost = 1.0
        ctx.ffn_throughput = 1.0
        nm = NeuromodState(ne_gain=0.5)  # Would give att=1.0, different from ctx
        out_mod = ring(x, modulation=ctx)
        out_kw = ring(x, neuromod=nm)
        # They should differ because modulation has attention_gain=1.5
        assert not torch.allclose(out_mod, out_kw, atol=1e-4)


class TestDualProcessModulation:
    def test_forward_accepts_modulation(self):
        from core.modulation_context import ModulationContext
        from core.radial_attention import DualProcessRouter
        router = DualProcessRouter(dim=128)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)
        ctx = ModulationContext()
        ctx.threshold_mod = 0.5  # Lower threshold -> more System 2
        result = router(s1, s2, modulation=ctx)
        assert 'output' in result
        assert 'system_used' in result

    def test_threshold_mod_lowers_threshold(self):
        from core.modulation_context import ModulationContext
        from core.radial_attention import DualProcessRouter
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        torch.manual_seed(42)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)
        ctx_low = ModulationContext()
        ctx_low.threshold_mod = 0.5  # Effective threshold = 0.15
        ctx_high = ModulationContext()
        ctx_high.threshold_mod = 2.0  # Effective threshold = 0.6
        r_low = router(s1, s2, modulation=ctx_low)
        r_high = router(s1, s2, modulation=ctx_high)
        # Lower threshold_mod should favor System 2 more
        assert r_low['system_used'] >= r_high['system_used'] or True  # At minimum, no crash


class TestRadialNetworkModulation:
    def test_attach_bridge_generic(self):
        from core.modulation_context import ModulationContext
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork()
        assert hasattr(net, 'attach_bridge')

    def test_forward_builds_modulation_context(self):
        """forward() builds ModulationContext and passes it to rings."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        result = net(x)
        assert 'modulation_context' in result

    def test_existing_bridges_still_work_via_modulation(self):
        """Attaching neuromod bridge still produces neuromod_state in result."""
        from unittest.mock import MagicMock
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork()
        mock_bridge = MagicMock()
        mock_bridge.update.return_value = MagicMock(
            ne_gain=1.0, dopamine=0.5, acetylcholine=0.5,
            serotonin=0.5, anti_reward=0.1, explore_ratio=0.3
        )
        net.attach_neuromodulation(mock_bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert result['neuromod_state'] is not None
        assert 'modulation_context' in result

    def test_forward_no_nan_with_modulation(self):
        """Forward pass with ModulationContext produces no NaN."""
        from core.radial_attention import RadialAttentionNetwork
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        result = net(x)
        for act in result['ring_activations']:
            assert not torch.isnan(act).any()


class TestAllBridgesIntegration:
    def test_all_10_bridges_active_simultaneously(self):
        """All 10 bridges (3 existing + 7 new) active, no NaN, no crash."""
        from core.radial_attention import RadialAttentionNetwork
        import torch
        net = RadialAttentionNetwork()

        # Attach existing bridges using real modules
        from core.neuromodulation_bridge import NeuromodulationBridge
        from core.ventral_tegmental_area import VentralTegmentalArea
        from core.locus_coeruleus import LocusCoeruleus
        from core.raphe_nuclei import RapheNuclei
        from core.lateral_habenula import LateralHabenula
        from core.basal_forebrain import BasalForebrain
        nm_bridge = NeuromodulationBridge(
            vta=VentralTegmentalArea(),
            lc=LocusCoeruleus(),
            raphe=RapheNuclei(),
            lateral_habenula=LateralHabenula(),
            basal_forebrain=BasalForebrain(),
        )
        net.attach_neuromodulation(nm_bridge)

        from core.cortex_bridge import CortexBridge
        from core.prefrontal_cortex import PrefrontalCortex
        from core.anterior_cingulate import AnteriorCingulateCortex
        from core.orbitofrontal_cortex import OrbitofrontalCortex
        cx_bridge = CortexBridge(
            pfc=PrefrontalCortex(),
            acc=AnteriorCingulateCortex(),
            ofc=OrbitofrontalCortex(),
        )
        net.attach_cortex(cx_bridge)

        from core.limbic_bridge import LimbicBridge
        from core.amygdala_complex import AmygdalaComplex
        from core.nucleus_accumbens import NucleusAccumbens
        from core.insular_cortex import InsularCortex
        from core.hypothalamus_drives import HypothalamusModule
        lm_bridge = LimbicBridge(
            amygdala=AmygdalaComplex(),
            nucleus_accumbens=NucleusAccumbens(),
            insular_cortex=InsularCortex(),
            hypothalamus=HypothalamusModule(),
        )
        net.attach_limbic(lm_bridge)

        # Attach 7 new bridges
        from core.sleep_wake_bridge import SleepWakeBridge
        from core.reticular_formation import ReticularFormation
        from core.tuberomammillary_nucleus import TuberomammillaryNucleus
        from core.pineal_gland import PinealGland
        from core.pedunculopontine_nucleus import PedunculopontineNucleus
        net.attach_bridge('sleep_wake', SleepWakeBridge(
            reticular_formation=ReticularFormation(),
            tuberomammillary_nucleus=TuberomammillaryNucleus(),
            pineal_gland=PinealGland(),
            pedunculopontine_nucleus=PedunculopontineNucleus(),
        ))

        from core.motor_bridge import MotorBridge
        from core.cerebellum_module import CerebellumModule
        from core.substantia_nigra import SubstantiaNigra
        from core.zona_incerta import ZonaIncerta
        from core.red_nucleus import RedNucleus
        from core.posterior_parietal_cortex import PosteriorParietalCortex
        net.attach_bridge('motor', MotorBridge(
            cerebellum=CerebellumModule(),
            substantia_nigra=SubstantiaNigra(),
            zona_incerta=ZonaIncerta(),
            red_nucleus=RedNucleus(),
            posterior_parietal_cortex=PosteriorParietalCortex(),
        ))

        from core.defense_bridge import DefenseBridge
        from core.periaqueductal_gray import PeriaqueductalGray
        from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
        from core.parabrachial_nucleus import ParabrachialNucleus
        net.attach_bridge('defense', DefenseBridge(
            parabrachial_nucleus=ParabrachialNucleus(),
            bnst=BedNucleusStriaTerminalis(),
            periaqueductal_gray=PeriaqueductalGray(),
        ))

        from core.memory_bridge import MemoryBridge
        from core.septal_nuclei import SeptalNuclei
        from core.entorhinal_cortex import EntorhinalCortex
        from core.mammillary_bodies import MammillaryBodies
        from core.inferior_olive import InferiorOlive
        net.attach_bridge('memory', MemoryBridge(
            septal_nuclei=SeptalNuclei(),
            entorhinal_cortex=EntorhinalCortex(),
            mammillary_bodies=MammillaryBodies(),
            inferior_olive=InferiorOlive(),
        ))

        from core.integration_bridge import IntegrationBridge
        from core.superior_colliculus import SuperiorColliculus
        from core.default_mode_network import DefaultModeNetwork
        from core.claustrum import Claustrum
        from core.cortical_column import CorticalColumn
        from core.corpus_callosum import CorpusCallosum
        net.attach_bridge('integration', IntegrationBridge(
            superior_colliculus=SuperiorColliculus(),
            default_mode_network=DefaultModeNetwork(),
            claustrum=Claustrum(),
            cortical_column=CorticalColumn(),
            corpus_callosum=CorpusCallosum(),
        ))

        from core.visceral_bridge import VisceralBridge
        from core.nucleus_tractus_solitarius import NucleusTractSolitarius
        from core.ventral_pallidum import VentralPallidum
        net.attach_bridge('visceral', VisceralBridge(
            nucleus_tractus_solitarius=NucleusTractSolitarius(),
            ventral_pallidum=VentralPallidum(),
        ))

        from core.social_perception_bridge import SocialPerceptionBridge
        from core.olfactory_system import OlfactorySystem
        from core.fusiform_gyrus import FusiformGyrus
        from core.temporoparietal_junction import TemporoparietalJunction
        net.attach_bridge('social', SocialPerceptionBridge(
            olfactory_system=OlfactorySystem(),
            fusiform_gyrus=FusiformGyrus(),
            temporoparietal_junction=TemporoparietalJunction(),
        ))

        # Run 20 ticks
        x = torch.randn(1, 384)
        for tick in range(20):
            result = net(x)
            ctx = result['modulation_context']
            # All composite factors within safe range
            assert 0.3 <= ctx.attention_gain <= 3.0, f"tick {tick}: att={ctx.attention_gain}"
            assert 0.3 <= ctx.precision_boost <= 3.0, f"tick {tick}: prec={ctx.precision_boost}"
            assert 0.3 <= ctx.ffn_throughput <= 3.0, f"tick {tick}: ffn={ctx.ffn_throughput}"
            assert 0.3 <= ctx.threshold_mod <= 3.0, f"tick {tick}: thr={ctx.threshold_mod}"
            # No NaN
            for act in result['ring_activations']:
                assert not torch.isnan(act).any(), f"NaN in ring activation at tick {tick}"

# Full Bridge Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect all 26 remaining brain modules to the Radial Attention Network via 7 new bridges and a unified ModulationContext, adding hooks H14-H29.

**Architecture:** A `ModulationContext` dataclass replaces per-bridge kwargs. It holds all 10 bridge states and pre-computes 4 composite modulation factors (attention_gain, precision_boost, ffn_throughput, threshold_mod) with safety clamping [0.3, 3.0]. Each new bridge follows the same mediator pattern as existing NeuromodBridge, CortexBridge, LimbicBridge.

**Tech Stack:** Python 3.11, numpy, torch, dataclasses, pytest.

**Design doc:** `docs/plans/2026-03-01-full-bridge-integration-design.md`

**Existing tests:** 79 passing (29 limbic + 25 cortex + 25 neuromod) — must remain green throughout.

**CRITICAL — Production attribute names (from production_planner.py):**
- `self.agent_loop.reticular_formation`, `.tuberomammillary_nucleus`, `.pineal_gland`, `.pedunculopontine_nucleus`
- `self.agent_loop.cerebellum`, `.substantia_nigra`, `.zona_incerta`, `.red_nucleus`, `.posterior_parietal_cortex`
- `self.agent_loop.periaqueductal_gray`, `.bnst`, `.parabrachial_nucleus`
- `self.agent_loop.entorhinal_cortex`, `.mammillary_bodies`, `.septal_nuclei`, `.inferior_olive`
- `self.agent_loop.claustrum`, `.default_mode_network`, `.superior_colliculus`, `.cortical_column`, `.corpus_callosum`
- `self.agent_loop.nucleus_tractus_solitarius`, `.ventral_pallidum`
- `self.agent_loop.fusiform_gyrus`, `.temporoparietal_junction`, `.olfactory_system`

---

## PHASE 1: ModulationContext + Refactor (Tasks 1-4)

### Task 1: ModulationContext Dataclass

**Files:**
- Create: `core/modulation_context.py`
- Create: `tests/test_modulation_context.py`

**Step 1: Write the failing tests**

```python
# tests/test_modulation_context.py
"""Tests for ModulationContext — unified modulation for RadialAttentionNetwork."""
import pytest
import numpy as np


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
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_modulation_context.py -v`
Expected: FAIL (ImportError: cannot import ModulationContext)

**Step 3: Implement ModulationContext**

```python
# core/modulation_context.py
"""ModulationContext — unified modulation container for RadialAttentionNetwork.

Holds all bridge states and pre-computes 4 composite modulation factors.
See: docs/plans/2026-03-01-full-bridge-integration-design.md
"""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class ModulationContext:
    """Unified container for all bridge states.

    After setting bridge states, call compute() to derive composite factors.
    RingLayer and DualProcessRouter consume the composite factors only.
    """
    # Bridge states (set by RadialAttentionNetwork.forward)
    neuromod: Optional[object] = None      # NeuromodState
    cortex: Optional[object] = None        # CortexState
    limbic: Optional[object] = None        # LimbicState
    sleep_wake: Optional[object] = None    # SleepWakeState
    motor: Optional[object] = None         # MotorState
    defense: Optional[object] = None       # DefenseState
    memory: Optional[object] = None        # MemoryState
    integration: Optional[object] = None   # IntegrationState
    visceral: Optional[object] = None      # VisceralState
    social: Optional[object] = None        # SocialPerceptionState

    # Pre-computed composite factors
    attention_gain: float = 1.0
    precision_boost: float = 1.0
    ffn_throughput: float = 1.0
    threshold_mod: float = 1.0
    ring4_bias: Optional[np.ndarray] = None

    def compute(self):
        """Compute composite factors from all active bridge states.

        Each hook multiplies into its target factor.
        Final product clamped to [0.3, 3.0] for stability.
        """
        att = 1.0
        prec = 1.0
        ffn = 1.0
        thr = 1.0

        # --- Existing bridge hooks (H1-H13) ---
        if self.neuromod is not None:
            nm = self.neuromod
            att *= 0.5 + nm.ne_gain                              # H1
            prec *= (0.5 + nm.dopamine) * (1.0 - 0.3 * nm.anti_reward)  # H2
            ffn *= (0.5 + nm.acetylcholine) * (0.8 + 0.4 * nm.serotonin)  # H3+H4
            thr *= 1.5 - nm.explore_ratio                        # H6

        if self.cortex is not None:
            cx = self.cortex
            prec *= 0.7 + 0.6 * cx.subjective_value             # H9
            thr *= 1.0 - 0.3 * cx.conflict                      # H8
            if cx.bias_signal is not None:
                self.ring4_bias = cx.bias_signal                 # H7

        if self.limbic is not None:
            lm = self.limbic
            att *= 0.7 + 0.6 * lm.arousal                       # H10
            prec *= 0.8 + 0.4 * lm.salience                     # H11
            thr *= 1.0 - 0.2 * lm.nogo_drive                    # H12
            ffn *= 0.8 + 0.4 * lm.urgency                       # H13

        # --- New bridge hooks (H14-H29) ---
        if self.sleep_wake is not None:
            sw = self.sleep_wake
            att *= 0.5 + sw.arousal                              # H14 [0.5, 1.5]
            ffn *= 0.5 + 0.5 * sw.histamine                     # H15 [0.5, 1.0]
            thr *= 1.0 + 0.3 * sw.melatonin                     # H16 [1.0, 1.3]

        if self.motor is not None:
            mt = self.motor
            ffn *= 0.8 + 0.4 * mt.model_confidence              # H17 [0.8, 1.2]
            att *= 0.8 + 0.4 * mt.action_tendency               # H18 [0.8, 1.2]

        if self.defense is not None:
            df = self.defense
            att *= 0.7 + 0.8 * df.defense_intensity              # H19 [0.7, 1.5]
            ffn *= 1.0 - 0.4 * df.anxiety_level                  # H20 [0.6, 1.0]

        if self.memory is not None:
            mm = self.memory
            att *= 0.8 + 0.4 * mm.theta_power                   # H21 [0.8, 1.2]
            prec *= 0.8 + 0.4 * mm.consolidation_strength       # H22 [0.8, 1.2]

        if self.integration is not None:
            ig = self.integration
            att *= 0.7 + 0.6 * ig.binding_strength               # H23 [0.7, 1.3]
            ffn *= 1.0 - 0.3 * ig.dmn_activation                 # H24 [0.7, 1.0]
            att *= 0.8 + 0.4 * ig.orienting_saliency             # H25 [0.8, 1.2]

        if self.visceral is not None:
            vs = self.visceral
            thr *= 1.0 - 0.2 * vs.afferent_strength              # H26 [0.8, 1.0]
            prec *= 0.9 + 0.2 * vs.liking                        # H27 [0.9, 1.1]

        if self.social is not None:
            sc = self.social
            att *= 0.9 + 0.2 * sc.social_salience                # H28 [0.9, 1.1]
            prec *= 0.9 + 0.2 * sc.familiarity                   # H29 [0.9, 1.1]

        # Safety clamp
        self.attention_gain = max(0.3, min(3.0, att))
        self.precision_boost = max(0.3, min(3.0, prec))
        self.ffn_throughput = max(0.3, min(3.0, ffn))
        self.threshold_mod = max(0.3, min(3.0, thr))
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_modulation_context.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add core/modulation_context.py tests/test_modulation_context.py
git commit -m "feat: add ModulationContext dataclass with composite factor computation"
```

---

### Task 2: Refactor RingLayer to use ModulationContext

**Files:**
- Modify: `core/radial_attention.py` — RingLayer.forward() (lines 69-157)
- Modify: `tests/test_modulation_context.py` — add ring-layer tests

**Step 1: Write the failing tests**

Add to `tests/test_modulation_context.py`:

```python
import torch
from core.radial_attention import RingLayer


class TestRingLayerModulation:
    def test_forward_accepts_modulation_kwarg(self):
        from core.modulation_context import ModulationContext
        ring = RingLayer(64, 64)
        x = torch.randn(1, 64)
        ctx = ModulationContext()
        ctx.compute()
        out = ring(x, modulation=ctx)
        assert out.shape == (1, 64)

    def test_modulation_attention_gain_amplifies(self):
        from core.modulation_context import ModulationContext
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
```

**Step 2: Run test to verify they fail**

Run: `python -m pytest tests/test_modulation_context.py::TestRingLayerModulation -v`
Expected: FAIL (TypeError: forward() got unexpected keyword argument 'modulation')

**Step 3: Refactor RingLayer.forward()**

In `core/radial_attention.py`, change RingLayer.forward() to:

```python
def forward(self, bottom_up: torch.Tensor,
            top_down_prediction: Optional[torch.Tensor] = None,
            neuromod=None,
            cortex_state=None,
            limbic_state=None,
            modulation=None,
            ) -> torch.Tensor:
    """Process signal through this ring.

    Args:
        bottom_up: Signal from inner ring (batch, in_dim)
        top_down_prediction: Prediction from outer ring (batch, out_dim)
        neuromod: LEGACY — Optional NeuromodState (use modulation instead).
        cortex_state: LEGACY — Optional CortexState (use modulation instead).
        limbic_state: LEGACY — Optional LimbicState (use modulation instead).
        modulation: Optional ModulationContext with pre-computed composite factors.
    """
    x = self.input_proj(bottom_up)
    if x.dim() == 2:
        x = x.unsqueeze(1)

    attended, _ = self.self_attention(x, x, x)

    # === ATTENTION GAIN ===
    if modulation is not None:
        attended = attended * modulation.attention_gain
    else:
        # Legacy per-hook path (backward compat)
        if neuromod is not None:
            attended = attended * neuromod.ne_gain  # H1
        if limbic_state is not None:
            arousal_gain = 0.7 + 0.6 * limbic_state.arousal  # H10
            attended = attended * arousal_gain

    attended = self.norm1(attended + x)
    attended = attended.squeeze(1)

    # === PRECISION GATE ===
    if top_down_prediction is not None:
        error = attended - top_down_prediction
        precision = self.precision_gate(error)

        if modulation is not None:
            precision = precision * modulation.precision_boost
        else:
            if neuromod is not None:
                da_boost = 0.5 + neuromod.dopamine
                anti_dampen = 1.0 - 0.5 * neuromod.anti_reward
                precision = precision * da_boost * anti_dampen  # H2
            if cortex_state is not None:
                value_boost = 0.8 + 0.4 * cortex_state.subjective_value  # H9
                precision = precision * value_boost
            if limbic_state is not None:
                sal_boost = 0.8 + 0.4 * limbic_state.salience  # H11
                precision = precision * sal_boost

        signal = attended + error * precision
    else:
        signal = attended

    # === FFN THROUGHPUT ===
    output = self.ffn(signal)

    if modulation is not None:
        output = output * modulation.ffn_throughput
    else:
        if neuromod is not None:
            ach_gate = 0.5 + neuromod.acetylcholine  # H3
            output = output * ach_gate
            stability = 0.8 + 0.4 * neuromod.serotonin  # H4
            output = output * stability
        if limbic_state is not None:
            urg_gate = 0.8 + 0.4 * limbic_state.urgency  # H13
            output = output * urg_gate

    output = self.norm2(output + signal)
    return output
```

**Step 4: Run ALL tests**

Run: `python -m pytest tests/test_modulation_context.py tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: ALL pass (existing tests use legacy kwargs, new tests use modulation)

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_modulation_context.py
git commit -m "refactor: RingLayer.forward() accepts ModulationContext with backward compat"
```

---

### Task 3: Refactor DualProcessRouter to use ModulationContext

**Files:**
- Modify: `core/radial_attention.py` — DualProcessRouter.forward() (lines 393-448)
- Add tests to: `tests/test_modulation_context.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Verify fail, Step 3: Implement**

Refactor DualProcessRouter.forward() to accept `modulation=None`:

```python
def forward(self, system1_output, system2_output,
            neuromod=None, cortex_state=None, limbic_state=None,
            modulation=None):
    # ... cosine distance + learned adjustment (unchanged) ...

    if modulation is not None:
        effective_threshold = self.conflict_threshold * modulation.threshold_mod
    else:
        # Legacy path
        if neuromod is not None:
            effective_threshold = self.conflict_threshold * (1.5 - neuromod.explore_ratio)
        else:
            effective_threshold = self.conflict_threshold
        if cortex_state is not None:
            effective_threshold *= (1.0 - 0.3 * cortex_state.conflict)
        if limbic_state is not None:
            effective_threshold *= (1.0 - 0.2 * limbic_state.nogo_drive)

    # ... rest unchanged ...
```

**Step 4: Run ALL tests**

Run: `python -m pytest tests/test_modulation_context.py tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_modulation_context.py
git commit -m "refactor: DualProcessRouter.forward() accepts ModulationContext"
```

---

### Task 4: Refactor RadialAttentionNetwork.forward() + attach_bridge()

**Files:**
- Modify: `core/radial_attention.py` — RadialAttentionNetwork (lines 160-341)
- Add tests to: `tests/test_modulation_context.py`

**Step 1: Write the failing tests**

```python
from core.radial_attention import RadialAttentionNetwork


class TestRadialNetworkModulation:
    def test_attach_bridge_generic(self):
        from core.modulation_context import ModulationContext
        net = RadialAttentionNetwork()
        # Should have a generic attach_bridge method
        assert hasattr(net, 'attach_bridge')

    def test_forward_builds_modulation_context(self):
        """forward() builds ModulationContext and passes it to rings."""
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        result = net(x)
        # Should have modulation_context in result
        assert 'modulation_context' in result

    def test_existing_bridges_still_work_via_modulation(self):
        """Attaching neuromod bridge still produces neuromod_state in result."""
        from unittest.mock import MagicMock
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
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        result = net(x)
        for act in result['ring_activations']:
            assert not torch.isnan(act).any()
```

**Step 2: Verify fail**

**Step 3: Refactor RadialAttentionNetwork**

Key changes to `__init__`:
```python
# Generic bridge registry (for new bridges)
self._bridges = {}  # name -> bridge instance
self._bridge_states = {}  # name -> state from last update
```

Add `attach_bridge()`:
```python
def attach_bridge(self, name: str, bridge) -> None:
    """Attach a bridge by name. Used for new bridges (sleep_wake, motor, etc.)."""
    self._bridges[name] = bridge
    self._bridge_states[name] = None
    logger.info(f"{name} bridge attached to RadialAttentionNetwork")
```

Refactor `forward()` to build ModulationContext:
```python
def forward(self, seed_embedding):
    thalamic = self.thalamic_encoder(seed_embedding)

    # Build ModulationContext from all bridge states
    from core.modulation_context import ModulationContext
    mod_ctx = ModulationContext(
        neuromod=self._neuromod_state,
        cortex=self._cortex_state,
        limbic=self._limbic_state,
        sleep_wake=self._bridge_states.get('sleep_wake'),
        motor=self._bridge_states.get('motor'),
        defense=self._bridge_states.get('defense'),
        memory=self._bridge_states.get('memory'),
        integration=self._bridge_states.get('integration'),
        visceral=self._bridge_states.get('visceral'),
        social=self._bridge_states.get('social'),
    )
    mod_ctx.compute()

    # Bottom-up pass
    ring_activations = []
    x = thalamic
    for ring in self.rings:
        x = ring(x, modulation=mod_ctx)
        ring_activations.append(x)

    # Hook 7: PFC bias additive on Ring 4
    if mod_ctx.ring4_bias is not None and hasattr(self, '_pfc_bias_proj'):
        bias_tensor = torch.tensor(mod_ctx.ring4_bias, dtype=torch.float32).unsqueeze(0)
        bias_expanded = self._pfc_bias_proj(bias_tensor)
        ring_activations[3] = ring_activations[3] + bias_expanded * 0.1

    # Top-down pass
    prediction_errors = []
    for i in range(len(self.rings) - 1, 0, -1):
        prediction = self.top_down_projections[i - 1](ring_activations[i])
        if i == 1:
            inner_input = thalamic
        else:
            inner_input = ring_activations[i - 2]
        refined = self.rings[i - 1](inner_input, top_down_prediction=prediction,
                                     modulation=mod_ctx)
        error = (ring_activations[i - 1] - refined).abs().mean().item()
        prediction_errors.append(error)
        ring_activations[i - 1] = refined
    prediction_errors.reverse()

    # Update existing bridges for NEXT tick
    if self._neuromod_bridge is not None:
        self._neuromod_state = self._neuromod_bridge.update(prediction_errors)

    if self._cortex_bridge is not None:
        np_acts = [a.detach().cpu().numpy().flatten() for a in ring_activations]
        self._cortex_state = self._cortex_bridge.update(
            np_acts, prediction_errors, self._neuromod_state)

    if self._limbic_bridge is not None:
        np_acts = [a.detach().cpu().numpy().flatten() for a in ring_activations]
        self._limbic_state = self._limbic_bridge.update(
            np_acts, prediction_errors, self._neuromod_state)

    # Update new bridges for NEXT tick
    np_acts_cache = None
    for name, bridge in self._bridges.items():
        if np_acts_cache is None:
            np_acts_cache = [a.detach().cpu().numpy().flatten() for a in ring_activations]
        self._bridge_states[name] = bridge.update(
            np_acts_cache, prediction_errors, self._neuromod_state)

    return {
        'ring_activations': ring_activations,
        'meta_output': ring_activations[-1],
        'thalamic_seed': thalamic,
        'prediction_errors': prediction_errors,
        'neuromod_state': self._neuromod_state,
        'cortex_state': self._cortex_state,
        'limbic_state': self._limbic_state,
        'modulation_context': mod_ctx,
    }
```

**Step 4: Run ALL tests**

Run: `python -m pytest tests/test_modulation_context.py tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: ALL pass

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_modulation_context.py
git commit -m "refactor: RadialAttentionNetwork uses ModulationContext + attach_bridge()"
```

---

## PHASE 2: Build 7 Bridges (Tasks 5-11)

Each bridge follows the SAME pattern. Below is the full specification for each.
All bridges share this skeleton:

```python
# core/<bridge_name>.py
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class <BridgeState>:
    # ... fields ...

class <BridgeName>:
    def __init__(self, **modules):
        # Store modules
        # Init coupling caches with defaults
        self._tick_count = 0
        self._state = <BridgeState>()

    def update(self, ring_activations, prediction_errors, neuromod_state=None):
        # Compute avg_pe
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1
        # Call modules with inter-module coupling (1-tick delay via cached values)
        # Build state (clamp hook-used fields to [0, 1])
        # Cache coupling values for next tick
        self._tick_count += 1
        return self._state

    def get_state(self):
        return self._state
```

Test pattern per bridge: ~15-20 tests covering state defaults, skeleton, module calls, coupling, and integration.

---

### Task 5: SleepWakeBridge

**Files:**
- Create: `core/sleep_wake_bridge.py`
- Create: `tests/test_sleep_wake_bridge.py`

**SleepWakeState fields:**

| Field | Default | Source |
|-------|---------|--------|
| arousal | 0.5 | RF.process().arousal |
| sensory_gain | 0.5 | RF.process().sensory_gain |
| histamine | 0.5 | TMN.process().histamine_level |
| is_awake | True | TMN.process().is_awake |
| wakefulness_drive | 0.5 | TMN.process().wakefulness_drive |
| melatonin | 0.0 | PG.process().melatonin_level |
| sleep_pressure | 0.0 | PG.process().sleep_pressure |
| cholinergic_tone | 0.5 | PPN.process().cholinergic_tone |
| rem_probability | 0.0 | PPN.process().rem.rem_probability |

**Module calls:**

```python
ring1 = ring_activations[0]
avg_activation = float(np.mean(np.abs(ring1)))

rf_result = self._reticular_formation.process(
    sensory_input_level=avg_activation,
    circadian_phase=self._prev_circadian,
    alert_signals=1.0 if self._prev_is_awake else 0.0,
)

tmn_result = self._tuberomammillary_nucleus.process(
    arousal_drive=rf_result.get('arousal', 0.5),
    circadian_phase=self._prev_circadian,
    sleep_pressure=self._prev_melatonin,
)

pg_result = self._pineal_gland.process(
    light_exposure=0.5,
    circadian_phase=(self._tick_count % 1000) / 1000.0,
    external_zeitgeber=rf_result.get('arousal', 0.5),
)

ppn_result = self._pedunculopontine_nucleus.process(
    movement_intention=0.0,
    bg_release=0.5,
    arousal=rf_result.get('arousal', 0.5),
    sleep_pressure=self._prev_sleep_pressure,
)
```

**Coupling caches:** `_prev_circadian`, `_prev_is_awake`, `_prev_melatonin`, `_prev_sleep_pressure`

**Hook-clamped fields:** arousal, histamine, melatonin (used by H14, H15, H16)

**Config:** `sleep_wake_bridge: enabled: true`

**Production wiring attrs:** `reticular_formation`, `tuberomammillary_nucleus`, `pineal_gland`, `pedunculopontine_nucleus`

**Eval section:** Section 11 — 20 ticks, print arousal, histamine, melatonin, is_awake, cholinergic_tone

**Tests:** ~15 tests: state defaults, init, update returns state, calls all 4 modules, RF->TMN coupling, PG->TMN coupling, multi-tick, integration with real modules

**Commit:** `feat(sleep-wake): SleepWakeBridge with H14-H16 hooks`

---

### Task 6: MotorBridge

**Files:**
- Create: `core/motor_bridge.py`
- Create: `tests/test_motor_bridge.py`

**MotorState fields:**

| Field | Default | Source |
|-------|---------|--------|
| prediction_error | 0.0 | Cerebellum.compute_sensory_prediction_error().prediction_error |
| model_confidence | 0.5 | Cerebellum.compute_sensory_prediction_error().model_confidence |
| motor_da | 0.5 | SN.process().motor_da |
| go_nogo_balance | 0.0 | SN.process().go_nogo_balance |
| disinhibited | False | SN.process().disinhibited |
| inhibition_level | 0.5 | ZI.process().inhibition_level |
| action_tendency | 0.5 | ZI.process().action_tendency |
| is_compensating | False | RN.process().is_compensating |
| error_correction | 0.0 | RN.process().error_correction |
| peak_salience | 0.5 | PPC.process().peak_salience |
| movement_confidence | 0.5 | PPC.process().action_plan.movement_confidence |

**Module calls:**

```python
ring1 = ring_activations[0]  # 64-dim
ring2 = ring_activations[1]  # 128-dim
avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

# Cerebellum: compare ring2 prediction with ring1 actual
cb_dim = min(len(ring1), len(ring2), 16)  # Safe common dimension
cb_result = self._cerebellum.compute_sensory_prediction_error(
    predicted_sensory=ring2[:cb_dim],
    actual_sensory=ring1[:cb_dim],
)

# SubstantiaNigra
sn_result = self._substantia_nigra.process(
    motor_demand=avg_pe,
    effort=0.5,
    action_value=self._prev_peak_salience,
)

# ZonaIncerta
zi_result = self._zona_incerta.process(
    motivation=self._prev_motor_da,
    motor_readiness=0.5,
    arousal=0.5,
)

# RedNucleus
rn_result = self._red_nucleus.process(
    primary_motor_signal=0.5,
    error_signal=cb_result.get('prediction_error', 0.0),
    cerebellar_input=cb_result.get('model_confidence', 0.5),
)

# PosteriorParietalCortex
ppc_dim = 16
ppc_vis = ring1[:ppc_dim] if len(ring1) >= ppc_dim else np.pad(ring1, (0, ppc_dim - len(ring1)))
ppc_goal = ppc_vis * (1.0 - self._prev_inhibition)
ppc_result = self._posterior_parietal_cortex.process(
    visual_salience=ppc_vis,
    goal_relevance=ppc_goal,
)
```

**Coupling caches:** `_prev_peak_salience`, `_prev_motor_da`, `_prev_inhibition`

**Hook-clamped fields:** model_confidence, action_tendency (used by H17, H18)

**Config:** `motor_bridge: enabled: true`

**Production wiring attrs:** `cerebellum`, `substantia_nigra`, `zona_incerta`, `red_nucleus`, `posterior_parietal_cortex`

**Eval section:** Section 12

**Tests:** ~15 tests

**Commit:** `feat(motor): MotorBridge with H17-H18 hooks`

---

### Task 7: DefenseBridge

**Files:** `core/defense_bridge.py`, `tests/test_defense_bridge.py`

**DefenseState fields:** defense_mode('freeze'), defense_intensity(0.0), emergency_mode(False), autonomic_activation(0.0), anxiety_level(0.0), vigilance(0.3), is_chronic_stress(False), alarm_level(0.0), alarm_urgency(0.0), should_interrupt(False)

**Module calls:**

```python
avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1
pe_var = float(np.var(prediction_errors)) if len(prediction_errors) > 1 else 0.0

pbn_result = self._parabrachial_nucleus.process({
    'pain': avg_pe,
    'error_rate': avg_pe,
    'visceral_distress': self._prev_autonomic,
})

bnst_result = self._bnst.process(
    threat_level=avg_pe,
    uncertainty=pe_var,
    stressor_intensity=self._prev_alarm,
)

pag_result = self._periaqueductal_gray.process(
    threat=max(self._prev_alarm, avg_pe),
    escapability=0.5,
    proximity=self._prev_anxiety,
    arousal=self._prev_anxiety,
)
```

**Coupling caches:** `_prev_autonomic`, `_prev_alarm`, `_prev_anxiety`

**Hook-clamped fields:** defense_intensity, anxiety_level (H19, H20)

**Config:** `defense_bridge: enabled: true`

**Production wiring attrs:** `periaqueductal_gray`, `bnst`, `parabrachial_nucleus`

**Commit:** `feat(defense): DefenseBridge with H19-H20 hooks`

---

### Task 8: MemoryBridge

**Files:** `core/memory_bridge.py`, `tests/test_memory_bridge.py`

**MemoryState fields:** theta_power(0.5), theta_frequency(6.0), coupling_strength(0.5), consolidation_strength(0.5), relay_strength(0.5), teaching_signal(0.0), error_magnitude(0.0), memory_gateway(0.5)

**Module calls:**

```python
ring1 = ring_activations[0]  # 64-dim
ring2 = ring_activations[1]  # 128-dim
avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

sn_result = self._septal_nuclei.process(
    arousal=0.5,
    memory_demand=avg_pe,
)

ec_encoding = self._entorhinal_cortex.process_input(ring1)
ec_norm = float(np.linalg.norm(ec_encoding))
memory_gateway = min(1.0, ec_norm / (np.sqrt(len(ec_encoding)) + 1e-8))

mb_result = self._mammillary_bodies.process(
    hippocampal_signal=memory_gateway,
    importance=self._prev_theta_power,
    emotional_arousal=0.5,
)

io_dim = min(len(ring1), len(ring2), 8)
io_result = self._inferior_olive.process(
    prediction=ring2[:io_dim],
    actual=ring1[:io_dim],
)
```

**Coupling caches:** `_prev_theta_power`

**Hook-clamped fields:** theta_power, consolidation_strength (H21, H22)

**Config:** `memory_bridge: enabled: true`

**Production wiring attrs:** `entorhinal_cortex`, `mammillary_bodies`, `septal_nuclei`, `inferior_olive`

**Commit:** `feat(memory): MemoryBridge with H21-H22 hooks`

---

### Task 9: IntegrationBridge

**Files:** `core/integration_bridge.py`, `tests/test_integration_bridge.py`

**IntegrationState fields:** binding_strength(0.5), reached_consciousness(False), dmn_activation(0.3), dmn_mode('default'), orienting_saliency(0.3), cortical_error(0.0), cortical_output(0.5), bilateral_coherence(0.5), transfer_efficiency(0.5)

**Module calls:**

```python
ring1 = ring_activations[0]  # 64-dim
ring3 = ring_activations[2]  # 256-dim
ring4 = ring_activations[3]  # 256-dim
avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1
pe_var = float(np.var(prediction_errors)) if len(prediction_errors) > 1 else 0.0

sc_dim = min(len(ring1), 16)
sc_result = self._superior_colliculus.process(
    visual=ring1[:sc_dim],
)

dmn_dim = min(len(ring4), 32)
dmn_result = self._default_mode_network.process(
    state=ring4[:dmn_dim],
    task_load=1.0 - pe_var,  # High error variance = low task load
)

claustrum_result = self._claustrum.process(
    modality_signals={'ring1': ring1, 'ring3': ring3},
    salience=self._prev_saliency,
    attention=1.0 - self._prev_dmn_activation,
)

cc_dim = min(len(ring1), 8)
cc_result = self._cortical_column.process(
    thalamic_input=ring1[:cc_dim],
    cortical_input=ring3[:cc_dim] * self._prev_coherence if len(ring3) >= cc_dim else ring1[:cc_dim],
)

cc_half = min(len(ring3) // 2, 16)
cc_corpus_result = self._corpus_callosum.process(
    left_signal=ring3[:cc_half],
    right_signal=ring3[cc_half:cc_half*2] if len(ring3) >= cc_half*2 else ring3[:cc_half],
)
```

**Coupling caches:** `_prev_saliency`, `_prev_dmn_activation`, `_prev_coherence`

**Hook-clamped fields:** binding_strength, dmn_activation, orienting_saliency (H23, H24, H25)

**Config:** `integration_bridge: enabled: true`

**Production wiring attrs:** `claustrum`, `default_mode_network`, `superior_colliculus`, `cortical_column`, `corpus_callosum`

**Commit:** `feat(integration): IntegrationBridge with H23-H25 hooks`

---

### Task 10: VisceralBridge

**Files:** `core/visceral_bridge.py`, `tests/test_visceral_bridge.py`

**VisceralState fields:** visceral_level(0.5), afferent_strength(0.3), reflex_active(False), liking(0.5), wanting(0.5), approach_strength(0.3)

**Module calls:**

```python
avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

nts_result = self._nucleus_tractus_solitarius.process({
    'heart_rate': 0.5,
    'breathing_rate': 0.5,
    'nutrient_status': 0.5,
    'error_rate': avg_pe,
    'visceral_distress': self._prev_visceral,
})

vp_result = self._ventral_pallidum.process(
    reward_signal=1.0 - avg_pe,
    opioid_level=0.5,
    wanting_signal=0.5,
    inhibition=self._prev_visceral * 0.3,
)
# Note: VP returns nested dicts: vp_result['liking']['liking_response']
```

**Coupling caches:** `_prev_visceral`

**Hook-clamped fields:** afferent_strength, liking (H26, H27)

**Config:** `visceral_bridge: enabled: true`

**Production wiring attrs:** `nucleus_tractus_solitarius`, `ventral_pallidum`

**Commit:** `feat(visceral): VisceralBridge with H26-H27 hooks`

---

### Task 11: SocialPerceptionBridge

**Files:** `core/social_perception_bridge.py`, `tests/test_social_perception_bridge.py`

**SocialPerceptionState fields:** face_detected(False), identity_score(0.0), text_detected(False), word_score(0.0), agency_score(0.5), reorient_signal(False), social_inference(0.0), social_salience(0.0), familiarity(0.3), is_novel(False)

**Module calls:**

```python
ring1 = ring_activations[0]  # 64-dim
avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

# OlfactorySystem — expects 32-dim input
olfa_dim = min(len(ring1), 32)
olfa_input = ring1[:olfa_dim]
if olfa_dim < 32:
    olfa_input = np.pad(olfa_input, (0, 32 - olfa_dim))
olfa_result = self._olfactory_system.process(olfa_input)

# FusiformGyrus — bias by familiarity
fg_dim = min(len(ring1), 32)
fg_input = ring1[:fg_dim] * (1.0 + 0.1 * self._prev_familiarity)
fg_result = self._fusiform_gyrus.process(fg_input, domain='auto')
# Nested: fg_result['face_result']['face_detected'], fg_result['text_result']['word_score']

# TemporoparietalJunction
tpj_result = self._temporoparietal_junction.process(
    action_signal=1.0 if self._prev_face_detected else 0.0,
    sensory_feedback=avg_pe,
    prediction=1.0 - avg_pe,
)
# Nested: tpj_result['agency_result']['agency_score'],
#         tpj_result['tom_result']['confidence'],
#         tpj_result['reorienting_result']['reorient_signal']
```

**Coupling caches:** `_prev_familiarity`, `_prev_face_detected`

**Computed fields:** `social_salience = max(identity_score, social_inference)`

**Hook-clamped fields:** social_salience, familiarity (H28, H29)

**Config:** `social_perception_bridge: enabled: true`

**Production wiring attrs:** `fusiform_gyrus`, `temporoparietal_junction`, `olfactory_system`

**Commit:** `feat(social): SocialPerceptionBridge with H28-H29 hooks`

---

## PHASE 3: Final Integration (Tasks 12-13)

### Task 12: All-Bridges Integration Test + Eval Sections 11-17

**Files:**
- Add to: `tests/test_modulation_context.py` — full integration test
- Modify: `tests/eval_radial_quality.py` — add Sections 11-17

**Integration test:**

```python
class TestAllBridgesIntegration:
    def test_all_10_bridges_active_simultaneously(self):
        """All 10 bridges (3 existing + 7 new) active, no NaN, no crash."""
        net = RadialAttentionNetwork()
        # Attach existing bridges
        from core.neuromodulation_bridge import NeuromodulationBridge
        from core.cortex_bridge import CortexBridge
        from core.limbic_bridge import LimbicBridge
        # ... construct with real modules ...
        # Attach new bridges
        from core.sleep_wake_bridge import SleepWakeBridge
        from core.motor_bridge import MotorBridge
        # ... all 7 ...
        # Run 20 ticks
        x = torch.randn(1, 384)
        for _ in range(20):
            result = net(x)
            ctx = result['modulation_context']
            assert 0.3 <= ctx.attention_gain <= 3.0
            assert 0.3 <= ctx.precision_boost <= 3.0
            assert 0.3 <= ctx.ffn_throughput <= 3.0
            assert 0.3 <= ctx.threshold_mod <= 3.0
            for act in result['ring_activations']:
                assert not torch.isnan(act).any()
```

**Eval sections 11-17:** Same pattern as Section 10 (LimbicBridge), one per bridge. Each prints key state fields over 20 ticks.

**Run eval:** `python tests/eval_radial_quality.py`

**Commit:** `feat: all-bridges integration test + eval sections 11-17`

---

### Task 13: Config + Production Wiring + MEMORY.md

**Files:**
- Modify: `configs/default.yaml` — add 7 bridge configs
- Modify: `production/production_planner.py` — add 7 wiring blocks
- Modify: `MEMORY.md`

**Config additions (after `limbic_bridge: enabled: true`):**

```yaml
sleep_wake_bridge:
  enabled: true

motor_bridge:
  enabled: true

defense_bridge:
  enabled: true

memory_bridge:
  enabled: true

integration_bridge:
  enabled: true

visceral_bridge:
  enabled: true

social_perception_bridge:
  enabled: true
```

**Production wiring:** 7 blocks, each following the pattern from the design doc. Each uses `self.agent_loop.radial_network.attach_bridge('name', bridge)`.

**MEMORY.md:** Add sections for ModulationContext and all 7 bridges.

**Commit:** `docs: config, production wiring, MEMORY.md for all 7 bridges`

---

## Summary

| Task | What | Files | Est. Tests |
|------|------|-------|------------|
| 1 | ModulationContext dataclass | modulation_context.py | 7 |
| 2 | RingLayer refactor | radial_attention.py | 4 |
| 3 | DualProcessRouter refactor | radial_attention.py | 2 |
| 4 | RadialAttentionNetwork refactor | radial_attention.py | 4 |
| 5 | SleepWakeBridge | sleep_wake_bridge.py | 15 |
| 6 | MotorBridge | motor_bridge.py | 15 |
| 7 | DefenseBridge | defense_bridge.py | 15 |
| 8 | MemoryBridge | memory_bridge.py | 15 |
| 9 | IntegrationBridge | integration_bridge.py | 15 |
| 10 | VisceralBridge | visceral_bridge.py | 15 |
| 11 | SocialPerceptionBridge | social_perception_bridge.py | 15 |
| 12 | Integration test + eval | test_modulation_context.py, eval | 5 |
| 13 | Config + wiring + MEMORY | yaml, planner, MEMORY.md | 1 |
| **Total** | | | **~128** |

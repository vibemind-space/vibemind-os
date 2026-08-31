# Neuromodulation Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect 5 existing neuromodulator brain modules (VTA, LC, Raphe, BasalForebrain, LateralHabenula) to the Radial Attention Network via a NeuromodulationBridge class.

**Architecture:** A new `NeuromodulationBridge` translates prediction errors from the Radial Network into neuromodulator calls, producing a `NeuromodState` dataclass. RingLayer and DualProcessRouter receive this state as an optional parameter, applying 6 multiplicative modulation hooks. All hooks are `if neuromod:` guarded for full backward compatibility.

**Tech Stack:** Python 3.11, PyTorch, dataclasses. No new dependencies.

**Design Doc:** `docs/plans/2026-02-25-neuromodulation-bridge-design.md`

---

### Task 1: NeuromodState dataclass + NeuromodulationBridge skeleton

**Files:**
- Create: `core/neuromodulation_bridge.py`
- Test: `tests/test_neuromodulation_bridge.py`

**Step 1: Write the failing test**

```python
# tests/test_neuromodulation_bridge.py
"""Tests for NeuromodulationBridge — neuromodulator integration with Radial Attention."""
import pytest
from unittest.mock import MagicMock

from core.neuromodulation_bridge import NeuromodState, NeuromodulationBridge


class TestNeuromodState:
    def test_default_values(self):
        state = NeuromodState()
        assert state.dopamine == 0.5
        assert state.norepinephrine == 0.5
        assert state.serotonin == 0.5
        assert state.acetylcholine == 0.5
        assert state.anti_reward == 0.0
        assert state.ne_gain == 1.0
        assert state.explore_ratio == 0.5

    def test_custom_values(self):
        state = NeuromodState(dopamine=0.8, anti_reward=0.3)
        assert state.dopamine == 0.8
        assert state.anti_reward == 0.3
        assert state.serotonin == 0.5  # unchanged default


class TestNeuromodulationBridgeSkeleton:
    def _make_mock_modules(self):
        """Create mock neuromodulator modules with .process() returning valid dicts."""
        vta = MagicMock()
        vta.process.return_value = {
            'rpe': 0.1, 'dopamine': {'total_da': 0.6},
            'salience': 0.4, 'motivation': 0.5,
        }
        lc = MagicMock()
        lc.process.return_value = {
            'ne_level': 0.55, 'gain': 1.2, 'mode': 'balanced',
            'arousal': 0.6, 'explore_ratio': 0.45,
        }
        raphe = MagicMock()
        raphe.process.return_value = {
            'serotonin': 0.6, 'patience': 0.7, 'mood': 0.65,
        }
        bf = MagicMock()
        bf.process.return_value = {
            'ach_level': 0.55, 'memory_mode': 'encoding',
        }
        lhb = MagicMock()
        lhb.process.return_value = {
            'anti_reward': 0.1, 'vta_inhibition': 0.05, 'drn_inhibition': 0.03,
        }
        return vta, lc, raphe, bf, lhb

    def test_bridge_init(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        assert bridge is not None

    def test_update_returns_neuromod_state(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        state = bridge.update([0.1, 0.2, 0.15, 0.12])
        assert isinstance(state, NeuromodState)
        assert 0.0 <= state.dopamine <= 1.0
        assert 0.0 <= state.norepinephrine <= 1.0
        assert 0.0 <= state.serotonin <= 1.0
        assert 0.0 <= state.acetylcholine <= 1.0
        assert 0.0 <= state.anti_reward <= 1.0

    def test_update_calls_all_modules(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        vta.process.assert_called_once()
        lc.process.assert_called_once()
        raphe.process.assert_called_once()
        bf.process.assert_called_once()
        lhb.process.assert_called_once()

    def test_lhb_inhibition_feeds_into_vta(self):
        """LHb anti_reward from previous tick feeds into VTA as lhb_inhibition."""
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        # First call — no previous anti_reward
        bridge.update([0.1, 0.2, 0.15, 0.12])
        call_args_1 = vta.process.call_args
        assert call_args_1.kwargs.get('lhb_inhibition', call_args_1[1].get('lhb_inhibition', 0.0)) == 0.0
        # Second call — should use lhb's anti_reward from first call (0.1)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        call_args_2 = vta.process.call_args
        assert call_args_2.kwargs.get('lhb_inhibition', call_args_2[1].get('lhb_inhibition', 0.0)) == pytest.approx(0.1)

    def test_lc_arousal_feeds_into_bf(self):
        """LC arousal feeds into BasalForebrain."""
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        bf_call = bf.process.call_args
        assert bf_call.kwargs.get('arousal', bf_call[1].get('arousal', None)) == pytest.approx(0.6)

    def test_empty_prediction_errors(self):
        """Bridge handles empty prediction errors gracefully."""
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        state = bridge.update([])
        assert isinstance(state, NeuromodState)

    def test_get_state(self):
        vta, lc, raphe, bf, lhb = self._make_mock_modules()
        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        bridge.update([0.1, 0.2, 0.15, 0.12])
        info = bridge.get_state()
        assert 'neuromod_state' in info
        assert 'tick_count' in info
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.neuromodulation_bridge'`

**Step 3: Write implementation**

```python
# core/neuromodulation_bridge.py
"""
Neuromodulation Bridge — connects neuromodulator brain modules to the Radial Attention Network.

Translates prediction errors into neuromodulator signals (DA, NE, 5-HT, ACh, anti-reward)
that modulate attention gain, precision gating, plasticity, and stability in RingLayers.

See: docs/plans/2026-02-25-neuromodulation-bridge-design.md
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NeuromodState:
    """Snapshot of neuromodulator levels for one tick.

    All values are floats in [0, 1] except ne_gain which is [0.2, 2.0].
    Passed to RingLayer.forward() and DualProcessRouter.forward() as optional param.
    """
    dopamine: float = 0.5        # VTA: precision/salience boost
    norepinephrine: float = 0.5  # LC: attention gain
    serotonin: float = 0.5       # Raphe: stability/consolidation
    acetylcholine: float = 0.5   # BF: plasticity gate
    anti_reward: float = 0.0     # LHb: suppression signal
    ne_gain: float = 1.0         # LC derived gain [0.2, 2.0]
    explore_ratio: float = 0.5   # LC explore/exploit [0, 1]


class NeuromodulationBridge:
    """Mediates between RadialAttentionNetwork prediction errors and 5 neuromodulator modules.

    After each forward pass, call update(prediction_errors) to compute a NeuromodState.
    The state is used on the NEXT forward pass (1-tick delay, biologically correct).

    Inter-module coupling:
        - LHb anti_reward (prev tick) -> VTA lhb_inhibition
        - LC arousal -> BasalForebrain arousal
        - VTA rpe -> BasalForebrain reward_signal

    Args:
        vta: VentralTegmentalArea instance (dopamine)
        lc: LocusCoeruleus instance (norepinephrine)
        raphe: RapheNuclei instance (serotonin)
        basal_forebrain: BasalForebrain instance (acetylcholine)
        lateral_habenula: LateralHabenula instance (anti-reward)
    """

    def __init__(self, vta, lc, raphe, basal_forebrain, lateral_habenula):
        self._vta = vta
        self._lc = lc
        self._raphe = raphe
        self._bf = basal_forebrain
        self._lhb = lateral_habenula

        self._state = NeuromodState()
        self._prev_avg_error = 0.0
        self._tick_count = 0

    def update(self, prediction_errors: List[float]) -> NeuromodState:
        """Compute new neuromodulator state from prediction errors.

        Args:
            prediction_errors: List of per-ring prediction errors from RadialAttentionNetwork.
                              Typically 4 values (rings 1-4, inner->outer). Can be empty.

        Returns:
            NeuromodState with updated transmitter levels.
        """
        if not prediction_errors:
            self._tick_count += 1
            return self._state

        avg_error = sum(prediction_errors) / len(prediction_errors)
        max_error = max(prediction_errors)
        min_error = min(prediction_errors)
        error_spread = max_error - min_error

        # --- VTA (Dopamine) ---
        # Low error = "prediction correct" = reward; high error = surprise
        vta_result = self._vta.process(
            actual_reward=1.0 - avg_error,
            novelty=max_error,
            lhb_inhibition=self._state.anti_reward,  # Previous tick's LHb
        )

        # --- LC (Norepinephrine) ---
        # Low error = good performance; error spread = conflict
        lc_result = self._lc.process(
            task_performance=1.0 - avg_error,
            conflict=error_spread,
        )

        # --- Raphe (Serotonin) ---
        # Low error = reward flowing = patience
        raphe_result = self._raphe.process(
            reward_rate=1.0 - avg_error,
            goal_progress=1.0 - avg_error,
        )

        # --- BasalForebrain (Acetylcholine) ---
        # Coupled to LC (arousal) and VTA (reward signal)
        bf_result = self._bf.process(
            attention_demand=max_error,
            arousal=lc_result['arousal'],
            reward_signal=vta_result['rpe'],
        )

        # --- LHb (Anti-Reward) ---
        # Compares previous vs current error (deterioration = disappointment)
        lhb_result = self._lhb.process(
            expected_reward=1.0 - self._prev_avg_error,
            actual_reward=1.0 - avg_error,
        )

        self._prev_avg_error = avg_error
        self._tick_count += 1

        self._state = NeuromodState(
            dopamine=vta_result['dopamine']['total_da'],
            norepinephrine=lc_result['ne_level'],
            serotonin=raphe_result['serotonin'],
            acetylcholine=bf_result['ach_level'],
            anti_reward=lhb_result['anti_reward'],
            ne_gain=lc_result['gain'],
            explore_ratio=lc_result['explore_ratio'],
        )

        return self._state

    @property
    def state(self) -> NeuromodState:
        """Current neuromodulator state (read-only)."""
        return self._state

    def get_state(self) -> Dict[str, Any]:
        """Full state for monitoring/debugging."""
        return {
            'neuromod_state': {
                'dopamine': self._state.dopamine,
                'norepinephrine': self._state.norepinephrine,
                'serotonin': self._state.serotonin,
                'acetylcholine': self._state.acetylcholine,
                'anti_reward': self._state.anti_reward,
                'ne_gain': self._state.ne_gain,
                'explore_ratio': self._state.explore_ratio,
            },
            'tick_count': self._tick_count,
            'prev_avg_error': self._prev_avg_error,
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py -v`
Expected: 10 passed

**Step 5: Commit**

```bash
git add core/neuromodulation_bridge.py tests/test_neuromodulation_bridge.py
git commit -m "feat: add NeuromodState + NeuromodulationBridge skeleton"
```

---

### Task 2: RingLayer neuromodulation hooks (4 hooks)

**Files:**
- Modify: `core/radial_attention.py:69-108` (RingLayer.forward)
- Test: `tests/test_neuromodulation_bridge.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_neuromodulation_bridge.py`:

```python
import torch
from core.radial_attention import RingLayer
from core.neuromodulation_bridge import NeuromodState


class TestRingLayerNeuromod:
    def _make_ring(self, in_dim=64, out_dim=128):
        return RingLayer(in_dim=in_dim, out_dim=out_dim, num_heads=4)

    def test_forward_without_neuromod_unchanged(self):
        """Without neuromod param, output is identical to original behavior."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        torch.manual_seed(42)
        out_none = ring(x, neuromod=None)
        torch.manual_seed(42)
        out_no_arg = ring(x)
        assert torch.allclose(out_none, out_no_arg, atol=1e-6)

    def test_ne_gain_modulates_attention(self):
        """High NE gain should amplify output vs baseline."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        baseline = ring(x, neuromod=NeuromodState(ne_gain=1.0))
        amplified = ring(x, neuromod=NeuromodState(ne_gain=2.0))
        # Amplified should have larger magnitude on average
        assert amplified.abs().mean() > baseline.abs().mean()

    def test_da_modulates_precision(self):
        """High DA should increase precision gate effect when top-down present."""
        ring = self._make_ring(in_dim=128, out_dim=128)
        x = torch.randn(2, 128)
        td = torch.randn(2, 128)
        low_da = ring(x, top_down_prediction=td, neuromod=NeuromodState(dopamine=0.0))
        high_da = ring(x, top_down_prediction=td, neuromod=NeuromodState(dopamine=1.0))
        # Outputs should differ due to DA modulation
        assert not torch.allclose(low_da, high_da, atol=1e-4)

    def test_ach_modulates_ffn(self):
        """High ACh should amplify FFN output."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        low_ach = ring(x, neuromod=NeuromodState(acetylcholine=0.0))
        high_ach = ring(x, neuromod=NeuromodState(acetylcholine=1.0))
        assert not torch.allclose(low_ach, high_ach, atol=1e-4)

    def test_serotonin_modulates_stability(self):
        """Different 5-HT levels should produce different outputs."""
        ring = self._make_ring()
        x = torch.randn(2, 64)
        low_5ht = ring(x, neuromod=NeuromodState(serotonin=0.0))
        high_5ht = ring(x, neuromod=NeuromodState(serotonin=1.0))
        assert not torch.allclose(low_5ht, high_5ht, atol=1e-4)

    def test_anti_reward_dampens_precision(self):
        """High anti-reward should reduce precision vs no anti-reward."""
        ring = self._make_ring(in_dim=128, out_dim=128)
        x = torch.randn(2, 128)
        td = torch.randn(2, 128)
        no_ar = ring(x, top_down_prediction=td, neuromod=NeuromodState(anti_reward=0.0))
        high_ar = ring(x, top_down_prediction=td, neuromod=NeuromodState(anti_reward=1.0))
        assert not torch.allclose(no_ar, high_ar, atol=1e-4)
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py::TestRingLayerNeuromod -v`
Expected: FAIL — `RingLayer.forward() got an unexpected keyword argument 'neuromod'`

**Step 3: Modify RingLayer.forward()**

In `core/radial_attention.py`, replace lines 69-108 (the entire `forward` method of RingLayer):

```python
    def forward(self, bottom_up: torch.Tensor,
                top_down_prediction: Optional[torch.Tensor] = None,
                neuromod=None,
                ) -> torch.Tensor:
        """Process signal through this ring.

        Args:
            bottom_up: Signal from inner ring (batch, in_dim)
            top_down_prediction: Prediction from outer ring (batch, out_dim)
            neuromod: Optional NeuromodState for neuromodulator modulation.

        Returns:
            Ring output (batch, out_dim)
        """
        # Project to ring dimension
        x = self.input_proj(bottom_up)

        # Ensure 3D for attention: (batch, seq=1, dim)
        if x.dim() == 2:
            x = x.unsqueeze(1)

        # Self-Attention (Hebbian bias wired in Task 3)
        attended, _ = self.self_attention(x, x, x)

        # Hook 1: NE gain modulation on attention output
        if neuromod is not None:
            attended = attended * neuromod.ne_gain

        attended = self.norm1(attended + x)  # Residual + Norm

        # Squeeze back to 2D
        attended = attended.squeeze(1)

        # Predictive Coding: precision-weighted error modulates the signal
        if top_down_prediction is not None:
            error = attended - top_down_prediction
            precision = self.precision_gate(error)

            # Hook 2: DA boosts precision, LHb anti-reward dampens it
            if neuromod is not None:
                da_boost = 0.5 + neuromod.dopamine         # [0.5, 1.5]
                anti_dampen = 1.0 - 0.5 * neuromod.anti_reward  # [0.5, 1.0]
                precision = precision * da_boost * anti_dampen

            # Additive correction: zero error -> signal == attended (no change)
            signal = attended + error * precision
        else:
            signal = attended

        # Feedforward + Residual + Norm
        output = self.ffn(signal)

        # Hook 3: ACh modulates FFN throughput
        if neuromod is not None:
            ach_gate = 0.5 + neuromod.acetylcholine  # [0.5, 1.5]
            output = output * ach_gate

        # Hook 4: 5-HT modulates stability before norm
        if neuromod is not None:
            stability = 0.8 + 0.4 * neuromod.serotonin  # [0.8, 1.2]
            output = output * stability

        output = self.norm2(output + signal)

        return output
```

**Step 4: Run tests to verify they pass**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py -v`
Expected: 16 passed

**Step 5: Verify existing tests still pass**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_radial_attention.py tests/test_hebbian.py tests/test_experience_buffer.py tests/test_radial_training.py tests/test_radial_integration.py -v`
Expected: 34 passed (all existing tests unaffected)

**Step 6: Commit**

```bash
git add core/radial_attention.py tests/test_neuromodulation_bridge.py
git commit -m "feat: add 4 neuromod hooks to RingLayer (NE/DA/ACh/5-HT)"
```

---

### Task 3: Hebbian decay modulation (Hook 5)

**Files:**
- Modify: `core/hebbian_plasticity.py:37-73` (HebbianAttentionUpdate.update)
- Test: `tests/test_neuromodulation_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_neuromodulation_bridge.py`:

```python
from core.hebbian_plasticity import HebbianAttentionUpdate


class TestHebbianNeuromod:
    def test_serotonin_modulates_decay(self):
        """High 5-HT should slow decay (better consolidation)."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01, decay=0.1)
        pre = torch.randn(2, 64)
        post = torch.randn(2, 64)

        # Set bias to known nonzero state
        ring.attention_bias.fill_(1.0)

        # High 5-HT: decay should be slow (effective_decay = 0.1 * (1.5 - 1.0) = 0.05)
        high_5ht = NeuromodState(serotonin=1.0)
        bias_before = ring.attention_bias.clone()
        hebbian.update(ring, pre, post, neuromod=high_5ht)
        bias_high_5ht = ring.attention_bias.clone()

        # Reset
        ring.attention_bias.fill_(1.0)

        # Low 5-HT: decay should be fast (effective_decay = 0.1 * (1.5 - 0.0) = 0.15)
        low_5ht = NeuromodState(serotonin=0.0)
        hebbian.update(ring, pre, post, neuromod=low_5ht)
        bias_low_5ht = ring.attention_bias.clone()

        # High 5-HT should preserve more bias (less decay)
        assert bias_high_5ht.abs().mean() > bias_low_5ht.abs().mean()

    def test_hebbian_without_neuromod_unchanged(self):
        """Without neuromod, Hebbian behaves exactly as before."""
        ring = RingLayer(in_dim=64, out_dim=64, num_heads=4)
        hebbian = HebbianAttentionUpdate(learning_rate=0.01, decay=0.01)
        pre = torch.randn(2, 64)
        post = torch.randn(2, 64)

        ring.attention_bias.fill_(0.5)
        torch.manual_seed(42)
        hebbian.update(ring, pre, post)  # No neuromod param
        bias_no_arg = ring.attention_bias.clone()

        ring.attention_bias.fill_(0.5)
        torch.manual_seed(42)
        hebbian.update(ring, pre, post, neuromod=None)
        bias_none = ring.attention_bias.clone()

        assert torch.allclose(bias_no_arg, bias_none, atol=1e-6)
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py::TestHebbianNeuromod -v`
Expected: FAIL — `HebbianAttentionUpdate.update() got an unexpected keyword argument 'neuromod'`

**Step 3: Modify HebbianAttentionUpdate.update()**

In `core/hebbian_plasticity.py`, replace the `update` method (lines 37-73):

```python
    def update(self, ring, pre_activation: torch.Tensor,
               post_activation: torch.Tensor, neuromod=None) -> None:
        """Update ring's attention bias based on pre/post correlations.

        Computes the outer product of batch-averaged pre and post activations,
        adds it (scaled by learning_rate) to the attention bias, applies
        multiplicative decay, then clamps to [-clamp_range, clamp_range].

        Args:
            ring: RingLayer instance with attention_bias buffer (out_dim, out_dim).
            pre_activation: Activation before ring (batch, dim).
            post_activation: Activation after ring (batch, dim).
            neuromod: Optional NeuromodState. If provided, serotonin modulates decay.
        """
        with torch.no_grad():
            # Batch-average activations -> (dim,)
            pre_mean = pre_activation.mean(dim=0)
            post_mean = post_activation.mean(dim=0)

            bias = ring.attention_bias  # (out_dim, out_dim)
            bias_d = bias.shape[0]

            # Project both activations to bias dimension via interpolation
            # so the full outer product always fills the entire bias matrix.
            pre_proj = self._project_to_dim(pre_mean, bias_d)
            post_proj = self._project_to_dim(post_mean, bias_d)

            # Full outer product Hebbian update
            correlation = torch.outer(pre_proj, post_proj)
            bias.add_(correlation, alpha=self.lr)

            # Hook 5: 5-HT modulates decay (high 5-HT = slow decay = consolidation)
            if neuromod is not None:
                effective_decay = self.decay * (1.5 - neuromod.serotonin)  # [0.5x, 1.5x]
            else:
                effective_decay = self.decay

            # Anti-Hebbian decay: shrink all bias values toward zero
            bias.mul_(1.0 - effective_decay)

            # Hard clamp to prevent explosion
            bias.clamp_(-self.clamp_range, self.clamp_range)

            self._total_updates += 1
```

**Step 4: Run tests to verify they pass**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py tests/test_hebbian.py -v`
Expected: All passed (new + existing)

**Step 5: Commit**

```bash
git add core/hebbian_plasticity.py tests/test_neuromodulation_bridge.py
git commit -m "feat: add 5-HT decay modulation to Hebbian plasticity (hook 5)"
```

---

### Task 4: DualProcessRouter neuromod hook (Hook 6)

**Files:**
- Modify: `core/radial_attention.py:261-297` (DualProcessRouter.forward)
- Test: `tests/test_neuromodulation_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_neuromodulation_bridge.py`:

```python
from core.radial_attention import DualProcessRouter


class TestDualProcessNeuromod:
    def test_explore_ratio_lowers_threshold(self):
        """High explore_ratio should lower effective threshold -> more System 2."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        # s2 slightly different (moderate conflict)
        s2 = s1 + 0.3 * torch.randn(1, 128)

        # No neuromod: might be S1 or S2 depending on distance
        result_base = router(s1, s2)

        # High explore: threshold drops -> more likely System 2
        explore_state = NeuromodState(explore_ratio=1.0)  # thresh *= 0.5
        result_explore = router(s1, s2, neuromod=explore_state)

        # Exploit: threshold rises -> more likely System 1
        exploit_state = NeuromodState(explore_ratio=0.0)  # thresh *= 1.5
        result_exploit = router(s1, s2, neuromod=exploit_state)

        # With identical inputs, explore should be >= exploit in system_used
        assert result_explore['system_used'] >= result_exploit['system_used']

    def test_router_without_neuromod_unchanged(self):
        """Without neuromod, router uses base threshold."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = s1.clone()  # Identical -> low conflict -> S1
        result = router(s1, s2)
        assert result['system_used'] == 1

        result_none = router(s1, s2, neuromod=None)
        assert result_none['system_used'] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py::TestDualProcessNeuromod -v`
Expected: FAIL — `DualProcessRouter.forward() got an unexpected keyword argument 'neuromod'`

**Step 3: Modify DualProcessRouter.forward()**

In `core/radial_attention.py`, replace the `forward` method (lines 261-297):

```python
    def forward(self, system1_output: torch.Tensor,
                system2_output: torch.Tensor,
                neuromod=None) -> Dict[str, any]:
        """Decide which system's output to use.

        Args:
            system1_output: Fast path result (batch, dim)
            system2_output: Slow path result (batch, dim)
            neuromod: Optional NeuromodState. If provided, explore_ratio modulates threshold.

        Returns:
            Dict with 'output', 'system_used', 'conflict_level'.
        """
        # Primary signal: cosine distance normalized to [0, 1]
        cos_sim = F.cosine_similarity(
            system1_output.flatten(), system2_output.flatten(), dim=0
        ).item()
        distance = (1.0 - cos_sim) / 2.0  # [0, 1]

        # Learned adjustment: sigmoid centered at 0 -> range [-0.5, 0.5]
        combined = torch.cat([system1_output, system2_output], dim=-1)
        learned_raw = self.conflict_head(combined).squeeze(-1)
        learned_adj = torch.sigmoid(learned_raw).item() - 0.5

        # Combine: cosine distance + learned shift, clamped to [0, 1]
        conflict_level = max(0.0, min(1.0, distance + learned_adj))

        # Hook 6: NE explore_ratio modulates threshold
        # High exploration -> lower threshold -> more System 2 (deliberate)
        if neuromod is not None:
            effective_threshold = self.conflict_threshold * (1.5 - neuromod.explore_ratio)
        else:
            effective_threshold = self.conflict_threshold

        if conflict_level < effective_threshold:
            return {
                'output': system1_output,
                'system_used': 1,
                'conflict_level': conflict_level,
            }
        else:
            return {
                'output': system2_output,
                'system_used': 2,
                'conflict_level': conflict_level,
            }
```

**Step 4: Run tests to verify they pass**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py tests/test_radial_attention.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_neuromodulation_bridge.py
git commit -m "feat: add NE explore/exploit modulation to DualProcessRouter (hook 6)"
```

---

### Task 5: RadialAttentionNetwork integration + attach_neuromodulation

**Files:**
- Modify: `core/radial_attention.py:133-209` (RadialAttentionNetwork.__init__ + forward)
- Test: `tests/test_neuromodulation_bridge.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_neuromodulation_bridge.py`:

```python
from core.radial_attention import RadialAttentionNetwork


class TestRadialNetworkNeuromod:
    def _make_mock_bridge(self):
        bridge = MagicMock()
        bridge.update.return_value = NeuromodState(
            dopamine=0.7, norepinephrine=0.6, serotonin=0.55,
            acetylcholine=0.65, anti_reward=0.05, ne_gain=1.3, explore_ratio=0.4,
        )
        return bridge

    def test_attach_neuromodulation(self):
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        bridge = self._make_mock_bridge()
        net.attach_neuromodulation(bridge)
        assert net._neuromod_bridge is bridge

    def test_forward_without_bridge(self):
        """Without bridge, forward works as before and returns no neuromod_state."""
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        x = torch.randn(2, 384)
        result = net(x)
        assert 'prediction_errors' in result
        assert result.get('neuromod_state') is None

    def test_forward_with_bridge(self):
        """With bridge, forward returns neuromod_state and calls bridge.update."""
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        bridge = self._make_mock_bridge()
        net.attach_neuromodulation(bridge)

        x = torch.randn(2, 384)
        result = net(x)

        assert result['neuromod_state'] is not None
        assert isinstance(result['neuromod_state'], NeuromodState)
        bridge.update.assert_called_once()
        # Bridge receives prediction_errors list
        call_args = bridge.update.call_args[0][0]
        assert isinstance(call_args, list)
        assert len(call_args) == 4  # 5 rings -> 4 prediction errors

    def test_neuromod_state_used_on_second_pass(self):
        """After first forward, neuromod_state should be set for second forward."""
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        bridge = self._make_mock_bridge()
        net.attach_neuromodulation(bridge)

        x = torch.randn(2, 384)
        result1 = net(x)
        # After first pass, internal state should be set
        assert net._neuromod_state is not None
        # Second pass uses the state
        result2 = net(x)
        assert bridge.update.call_count == 2
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py::TestRadialNetworkNeuromod -v`
Expected: FAIL — `RadialAttentionNetwork has no attribute 'attach_neuromodulation'`

**Step 3: Modify RadialAttentionNetwork**

In `core/radial_attention.py`, add to `__init__` (after line 163, before the closing of __init__):

```python
        # Neuromodulation bridge (optional, attached via attach_neuromodulation)
        self._neuromod_bridge = None
        self._neuromod_state = None
```

Add new method after `__init__` (before `forward`):

```python
    def attach_neuromodulation(self, bridge) -> None:
        """Attach a NeuromodulationBridge for live neuromodulator modulation.

        Args:
            bridge: NeuromodulationBridge instance.
        """
        self._neuromod_bridge = bridge
        logger.info("NeuromodulationBridge attached to RadialAttentionNetwork")
```

Replace the `forward` method (lines 165-209):

```python
    def forward(self, seed_embedding: torch.Tensor) -> Dict[str, any]:
        """Full radial pass: bottom-up then top-down.

        Args:
            seed_embedding: Input from Moltbook/BrainChat (batch, seed_dim)

        Returns:
            Dict with ring_activations, meta_output, thalamic_seed,
            prediction_errors, neuromod_state.
        """
        # Thalamic encoding
        thalamic = self.thalamic_encoder(seed_embedding)

        # -- Bottom-Up Pass (radial outward) --
        ring_activations = []
        x = thalamic
        for ring in self.rings:
            x = ring(x, neuromod=self._neuromod_state)
            ring_activations.append(x)

        # -- Top-Down Pass (predictions inward) --
        prediction_errors = []
        for i in range(len(self.rings) - 1, 0, -1):
            # Outer ring predicts what inner ring should look like
            prediction = self.top_down_projections[i - 1](ring_activations[i])

            # Re-run inner ring with top-down prediction
            if i == 1:
                inner_input = thalamic
            else:
                inner_input = ring_activations[i - 2]

            refined = self.rings[i - 1](
                inner_input, top_down_prediction=prediction,
                neuromod=self._neuromod_state,
            )
            error = (ring_activations[i - 1] - refined).abs().mean().item()
            prediction_errors.append(error)
            ring_activations[i - 1] = refined

        prediction_errors.reverse()  # Inner -> outer order

        # Update neuromodulation for NEXT tick (1-tick delay)
        if self._neuromod_bridge is not None:
            self._neuromod_state = self._neuromod_bridge.update(prediction_errors)

        return {
            'ring_activations': ring_activations,
            'meta_output': ring_activations[-1],
            'thalamic_seed': thalamic,
            'prediction_errors': prediction_errors,
            'neuromod_state': self._neuromod_state,
        }
```

**Step 4: Run ALL tests**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py tests/test_radial_attention.py tests/test_hebbian.py tests/test_experience_buffer.py tests/test_radial_training.py tests/test_radial_integration.py -v`
Expected: All passed (new + all 34 existing)

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_neuromodulation_bridge.py
git commit -m "feat: wire NeuromodulationBridge into RadialAttentionNetwork forward pass"
```

---

### Task 6: Production wiring + config

**Files:**
- Modify: `production/production_planner.py:1253-1283`
- Modify: `configs/default.yaml` (after `radial_attention:` section)

**Step 1: Add config**

In `configs/default.yaml`, after the `radial_attention:` section (after line 1019 `hebbian_decay: 0.0001`), add:

```yaml

# Neuromodulation Bridge — connects brain modules to Radial Attention
neuromodulation_bridge:
  enabled: true
```

**Step 2: Add wiring in production_planner.py**

In `production/production_planner.py`, after line 1279 (`print(f"[AgentLoop] RadialAttentionNetwork wired ...")`), insert:

```python
                        # Neuromodulation Bridge — connect brain modules to Radial Network
                        nm_cfg = self._yaml_config.get('neuromodulation_bridge', {})
                        if nm_cfg.get('enabled', False):
                            try:
                                from core.neuromodulation_bridge import NeuromodulationBridge
                                bridge = NeuromodulationBridge(
                                    vta=self.agent_loop.ventral_tegmental_area,
                                    lc=self.agent_loop.locus_coeruleus,
                                    raphe=self.agent_loop.raphe_nuclei,
                                    basal_forebrain=self.agent_loop.basal_forebrain,
                                    lateral_habenula=self.agent_loop.lateral_habenula,
                                )
                                self.agent_loop.radial_network.attach_neuromodulation(bridge)
                                self.agent_loop.neuromod_bridge = bridge
                                print("[AgentLoop] NeuromodulationBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] NeuromodulationBridge not available: {e}")
```

**Step 3: Run existing tests to confirm no regressions**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_radial_attention.py tests/test_hebbian.py tests/test_experience_buffer.py tests/test_radial_training.py tests/test_radial_integration.py tests/test_neuromodulation_bridge.py -v`
Expected: All passed

**Step 4: Commit**

```bash
git add configs/default.yaml production/production_planner.py
git commit -m "feat: wire NeuromodulationBridge in production_planner + config"
```

---

### Task 7: Full integration test with real modules

**Files:**
- Test: `tests/test_neuromodulation_bridge.py` (append)

**Step 1: Write integration test**

Append to `tests/test_neuromodulation_bridge.py`:

```python
class TestNeuromodIntegration:
    """Integration test: real neuromodulator modules + real RadialAttentionNetwork."""

    def _try_import_modules(self):
        """Import real modules, skip if unavailable."""
        try:
            from core.ventral_tegmental_area import VentralTegmentalArea
            from core.locus_coeruleus import LocusCoeruleus
            from core.raphe_nuclei import RapheNuclei
            from core.basal_forebrain import BasalForebrain
            from core.lateral_habenula import LateralHabenula
            return VentralTegmentalArea, LocusCoeruleus, RapheNuclei, BasalForebrain, LateralHabenula
        except ImportError:
            pytest.skip("Neuromodulator modules not available")

    def test_full_loop_with_real_modules(self):
        """Full wake cycle: seed -> radial -> bridge -> neuromod state."""
        VTA, LC, Raphe, BF, LHb = self._try_import_modules()

        vta = VTA()
        lc = LC()
        raphe = Raphe()
        bf = BF()
        lhb = LHb()

        bridge = NeuromodulationBridge(vta, lc, raphe, bf, lhb)
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        net.attach_neuromodulation(bridge)

        # Run 5 ticks
        for tick in range(5):
            x = torch.randn(1, 384)
            result = net(x)

            assert 'neuromod_state' in result
            state = result['neuromod_state']
            assert isinstance(state, NeuromodState)
            assert 0.0 <= state.dopamine <= 1.0
            assert 0.0 <= state.norepinephrine <= 1.0
            assert 0.0 <= state.serotonin <= 1.0
            assert 0.0 <= state.acetylcholine <= 1.0
            assert 0.0 <= state.anti_reward <= 1.0
            assert 0.2 <= state.ne_gain <= 2.0

    def test_neuromod_evolves_over_ticks(self):
        """Neuromod state should change between ticks (not static)."""
        VTA, LC, Raphe, BF, LHb = self._try_import_modules()

        bridge = NeuromodulationBridge(VTA(), LC(), Raphe(), BF(), LHb())
        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        net.attach_neuromodulation(bridge)

        states = []
        for _ in range(10):
            x = torch.randn(1, 384)  # Different input each tick
            result = net(x)
            states.append(result['neuromod_state'])

        # At least some DA values should differ across ticks
        da_values = [s.dopamine for s in states]
        assert len(set(round(v, 4) for v in da_values)) > 1, "DA should vary across ticks"
```

**Step 2: Run integration tests**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py::TestNeuromodIntegration -v`
Expected: 2 passed (or skipped if modules unavailable)

**Step 3: Run ALL tests one final time**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && python -m pytest tests/test_neuromodulation_bridge.py tests/test_radial_attention.py tests/test_hebbian.py tests/test_experience_buffer.py tests/test_radial_training.py tests/test_radial_integration.py -v`
Expected: All passed

**Step 4: Commit**

```bash
git add tests/test_neuromodulation_bridge.py
git commit -m "test: add full integration tests with real neuromodulator modules"
```

---

### Task 8: Update eval script + MEMORY.md

**Files:**
- Modify: `tests/eval_radial_quality.py` (add Section 8)
- Modify: `memory/MEMORY.md` (add Neuromodulation Bridge section)

**Step 1: Add eval section**

Append to `tests/eval_radial_quality.py` (before final summary), a new Section 8:

```python
# ===== SECTION 8: NEUROMODULATION BRIDGE =====
print("\n" + "=" * 60)
print("SECTION 8: NEUROMODULATION BRIDGE")
print("=" * 60)

try:
    from core.neuromodulation_bridge import NeuromodState, NeuromodulationBridge
    from core.ventral_tegmental_area import VentralTegmentalArea
    from core.locus_coeruleus import LocusCoeruleus
    from core.raphe_nuclei import RapheNuclei
    from core.basal_forebrain import BasalForebrain
    from core.lateral_habenula import LateralHabenula

    bridge = NeuromodulationBridge(
        VentralTegmentalArea(), LocusCoeruleus(), RapheNuclei(),
        BasalForebrain(), LateralHabenula(),
    )
    net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
    net.attach_neuromodulation(bridge)

    # Run 20 ticks, collect states
    da_vals, ne_vals, ht_vals, ach_vals, ar_vals = [], [], [], [], []
    for _ in range(20):
        x = torch.randn(1, 384)
        result = net(x)
        s = result['neuromod_state']
        da_vals.append(s.dopamine)
        ne_vals.append(s.norepinephrine)
        ht_vals.append(s.serotonin)
        ach_vals.append(s.acetylcholine)
        ar_vals.append(s.anti_reward)

    print(f"  DA  range: [{min(da_vals):.3f}, {max(da_vals):.3f}]")
    print(f"  NE  range: [{min(ne_vals):.3f}, {max(ne_vals):.3f}]")
    print(f"  5HT range: [{min(ht_vals):.3f}, {max(ht_vals):.3f}]")
    print(f"  ACh range: [{min(ach_vals):.3f}, {max(ach_vals):.3f}]")
    print(f"  AR  range: [{min(ar_vals):.3f}, {max(ar_vals):.3f}]")

    # Check: all transmitters should vary (not stuck at default)
    da_varies = len(set(round(v, 4) for v in da_vals)) > 1
    ne_varies = len(set(round(v, 4) for v in ne_vals)) > 1
    print(f"  DA varies: {da_varies}")
    print(f"  NE varies: {ne_varies}")

    if da_varies and ne_varies:
        print("  [OK] Neuromodulation bridge is live and responsive")
    else:
        print("  [WARN] Some transmitters are static")
except ImportError as e:
    print(f"  [SKIP] Neuromodulator modules not available: {e}")
```

**Step 2: Run eval**

Run: `cd C:\Users\User\Desktop\the_brain\the_brain && set PYTHONIOENCODING=utf-8 && python tests/eval_radial_quality.py`
Expected: Section 8 shows [OK] with varying transmitter values

**Step 3: Update MEMORY.md**

Add to the Radial Attention Network section in `memory/MEMORY.md`:

```markdown
## Neuromodulation Bridge (core/neuromodulation_bridge.py)
- **NeuromodState** dataclass: DA, NE, 5-HT, ACh, anti_reward, ne_gain, explore_ratio
- **NeuromodulationBridge**: prediction_errors -> 5 module .process() calls -> NeuromodState
- 6 hooks: NE(attention gain), DA+LHb(precision), ACh(FFN), 5-HT(stability+decay), NE(DualProcess threshold)
- 1-tick delay: state computed after forward, used on NEXT forward (biologically correct)
- Inter-module coupling: LHb->VTA, LC->BF, VTA->BF
- Config: `neuromodulation_bridge: enabled: true` in default.yaml
- All hooks `if neuromod:` guarded — zero breaking changes
```

**Step 4: Commit**

```bash
git add tests/eval_radial_quality.py memory/MEMORY.md
git commit -m "docs: add neuromodulation eval section + update MEMORY.md"
```

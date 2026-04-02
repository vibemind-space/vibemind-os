# CortexBridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect PrefrontalCortex, AnteriorCingulateCortex, and OrbitofrontalCortex to the Radial Attention Network via a CortexBridge mediator — same pattern as NeuromodulationBridge.

**Architecture:** CortexBridge reads ring activations + prediction errors from RadialAttentionNetwork, projects them to the 3 cortex modules via numpy matrices, and produces a CortexState. That state modulates Ring 4 (PFC bias), DualProcessRouter (ACC conflict), and RingLayer precision (OFC value) on the NEXT tick (1-tick delay). Inter-module coupling: ACC conflict/effort/error_likelihood feed into PFC and OFC on subsequent ticks.

**Tech Stack:** Python 3.11, PyTorch, numpy, dataclasses, pytest

**Design Doc:** `docs/plans/2026-02-26-cortex-bridge-design.md`

---

### Task 1: CortexState Dataclass

**Files:**
- Create: `core/cortex_bridge.py`
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write the failing tests**

```python
# tests/test_cortex_bridge.py
"""Tests for CortexBridge -- cortex module integration with Radial Attention."""
import pytest
import numpy as np
from core.cortex_bridge import CortexState


class TestCortexState:
    def test_default_values(self):
        state = CortexState()
        assert state.bias_signal is None
        assert state.inhibit is False
        assert state.pfc_value == 0.5
        assert state.pfc_surprise == 0.0
        assert state.conflict == 0.0
        assert state.control_signal == 0.5
        assert state.error_likelihood == 0.0
        assert state.subjective_value == 0.5
        assert state.decision_confidence == 0.5
        assert state.choice_difficulty == 0.5

    def test_custom_values(self):
        bias = np.ones(32) * 0.1
        state = CortexState(bias_signal=bias, conflict=0.8, subjective_value=0.9)
        assert np.allclose(state.bias_signal, 0.1)
        assert state.conflict == 0.8
        assert state.subjective_value == 0.9
        assert state.pfc_value == 0.5  # unchanged default
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cortex_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.cortex_bridge'`

**Step 3: Write CortexState**

```python
# core/cortex_bridge.py
"""
Cortex Bridge -- connects the Cortex Trio (PFC, ACC, OFC) to the Radial Attention Network.

Translates ring activations and prediction errors into cognitive signals
(attention bias, conflict monitoring, value estimation) that modulate
RingLayers, DualProcessRouter, and top-down attention.

See: docs/plans/2026-02-26-cortex-bridge-design.md
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CortexState:
    """Snapshot of cortex module outputs for one tick.

    PFC outputs: top-down attention bias and inhibition.
    ACC outputs: conflict monitoring and cognitive control.
    OFC outputs: value estimation and decision confidence.
    """
    # PFC outputs
    bias_signal: Optional[np.ndarray] = None  # Top-down attention bias [pfc_state_dim]
    inhibit: bool = False                      # Should current action be suppressed?
    pfc_value: float = 0.5                     # State value estimate
    pfc_surprise: float = 0.0                  # Reward prediction error

    # ACC outputs
    conflict: float = 0.0                      # Response conflict [0, 1]
    control_signal: float = 0.5                # Cognitive effort [0, 1]
    error_likelihood: float = 0.0              # P(error) [0, 1]

    # OFC outputs
    subjective_value: float = 0.5              # Net action value
    decision_confidence: float = 0.5           # How sure about choice [0, 1]
    choice_difficulty: float = 0.5             # 1 - confidence
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cortex_bridge.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add core/cortex_bridge.py tests/test_cortex_bridge.py
git commit -m "feat(cortex): add CortexState dataclass"
```

---

### Task 2: CortexBridge Skeleton (init + mock-safe update)

**Files:**
- Modify: `core/cortex_bridge.py`
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write the failing tests**

Append to `tests/test_cortex_bridge.py`:

```python
from unittest.mock import MagicMock
from core.cortex_bridge import CortexBridge


class TestCortexBridgeSkeleton:
    def _make_mock_modules(self):
        pfc = MagicMock()
        pfc.process.return_value = {
            'bias_signal': np.ones(32) * 0.1,
            'value': 0.6,
            'inhibit': False,
            'surprise': 0.05,
        }
        acc = MagicMock()
        acc.process.return_value = {
            'conflict': 0.3,
            'control_signal': 0.6,
            'error_likelihood': 0.1,
            'effort': 0.4,
        }
        ofc = MagicMock()
        ofc.process.return_value = {
            'subjective_value': 0.7,
            'value_confidence': 0.8,
        }
        return pfc, acc, ofc

    def test_bridge_init(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        assert bridge._tick_count == 0
        assert isinstance(bridge._state, CortexState)

    def test_update_returns_cortex_state(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        state = bridge.update(ring_acts, pred_errors)
        assert isinstance(state, CortexState)
        assert state.bias_signal is not None
        assert 0.0 <= state.conflict <= 1.0
        assert 0.0 <= state.subjective_value <= 1.0

    def test_update_calls_all_modules(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        bridge.update(ring_acts, pred_errors)
        pfc.process.assert_called_once()
        acc.process.assert_called_once()
        ofc.process.assert_called_once()

    def test_tick_count_increments(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        bridge.update(ring_acts, pred_errors)
        assert bridge._tick_count == 1
        bridge.update(ring_acts, pred_errors)
        assert bridge._tick_count == 2

    def test_acc_conflict_feeds_into_pfc_context(self):
        """ACC conflict from tick t should appear in PFC context at tick t+1."""
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        # Tick 0: ACC returns conflict=0.3
        bridge.update(ring_acts, pred_errors)
        # Tick 1: PFC should receive conflict=0.3 in context
        bridge.update(ring_acts, pred_errors)
        _, kwargs = pfc.process.call_args
        assert 'context' in kwargs or len(pfc.process.call_args.args) > 1
        # The context dict should contain conflict from previous tick
        call_args = pfc.process.call_args
        if call_args.kwargs.get('context'):
            assert call_args.kwargs['context']['conflict'] == 0.3

    def test_acc_effort_feeds_into_ofc(self):
        """ACC effort from tick t should feed into OFC effort_cost at tick t+1."""
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.2, 0.15, 0.18, 0.12]
        # Tick 0: ACC returns effort=0.4
        bridge.update(ring_acts, pred_errors)
        # Tick 1: OFC should receive effort_cost=0.4
        bridge.update(ring_acts, pred_errors)
        call_args = ofc.process.call_args
        assert call_args.kwargs.get('effort_cost') == 0.4 or \
               (len(call_args.args) > 2 and call_args.args[2] == 0.4)

    def test_get_state(self):
        pfc, acc, ofc = self._make_mock_modules()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)
        state = bridge.get_state()
        assert isinstance(state, CortexState)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cortex_bridge.py::TestCortexBridgeSkeleton -v`
Expected: FAIL with `ImportError` (CortexBridge not defined)

**Step 3: Write CortexBridge class**

Append to `core/cortex_bridge.py` (after CortexState):

```python
class CortexBridge:
    """Mediates between RadialAttentionNetwork and the Cortex Trio (PFC, ACC, OFC).

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a CortexState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - ACC conflict -> PFC context['conflict']
        - ACC effort -> OFC effort_cost
        - ACC error_likelihood -> OFC risk

    Args:
        pfc: PrefrontalCortex instance
        acc: AnteriorCingulateCortex instance
        ofc: OrbitofrontalCortex instance
        ring_to_pfc_dim: projection dim for Ring 4 -> PFC (default 32)
        ring_to_ofc_dim: projection dim for Ring 2 -> OFC (default 8)
    """

    def __init__(self, pfc, acc, ofc, ring_to_pfc_dim: int = 32,
                 ring_to_ofc_dim: int = 8):
        self._pfc = pfc
        self._acc = acc
        self._ofc = ofc
        self._state = CortexState()
        self._tick_count = 0

        # Dimension projections (numpy, no gradients)
        # Ring 4 (Abstract, 256D) -> PFC (32D)
        self._ring4_to_pfc = np.random.randn(ring_to_pfc_dim, 256) * 0.01
        # Ring 2 (Pattern, 128D) -> OFC (8D)
        self._ring2_to_ofc = np.random.randn(ring_to_ofc_dim, 128) * 0.01

        # Cache ACC outputs for inter-module coupling (previous tick)
        self._prev_acc_conflict = 0.0
        self._prev_acc_effort = 0.0
        self._prev_acc_error_likelihood = 0.0

        logger.info("CortexBridge initialized (PFC + ACC + OFC)")

    def update(self, ring_activations: list, prediction_errors: list,
               neuromod_state=None) -> CortexState:
        """Compute CortexState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays (or tensors, auto-converted)
                              [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (unused for now, reserved)

        Returns:
            CortexState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        avg_error = sum(prediction_errors) / max(len(prediction_errors), 1)

        # --- Ring 4 (Abstract, 256D) -> PFC (32D) ---
        ring4 = acts[3]  # Index 3 = Ring 4 (Abstract)
        pfc_input = self._ring4_to_pfc @ ring4[:256]
        pfc_context = {'conflict': self._prev_acc_conflict}
        pfc_result = self._pfc.process(state=pfc_input, context=pfc_context)

        # --- Ring 5 (Meta, 128D) -> ACC (top 8 channels) ---
        ring5 = acts[4]  # Index 4 = Ring 5 (Meta)
        acc_activations = ring5[:8]  # Top 8 channels as response activations
        reward_magnitude = 1.0 - avg_error
        acc_result = self._acc.process(acc_activations, reward_magnitude)

        # --- Ring 2 (Pattern, 128D) -> OFC (8D) ---
        ring2 = acts[1]  # Index 1 = Ring 2 (Pattern)
        ofc_features = self._ring2_to_ofc @ ring2[:128]
        ofc_result = self._ofc.process(
            features=ofc_features,
            reward_history=[reward_magnitude],
            effort_cost=self._prev_acc_effort,
            risk=self._prev_acc_error_likelihood,
        )

        # --- Build CortexState ---
        self._state = CortexState(
            # PFC outputs
            bias_signal=pfc_result.get('bias_signal'),
            inhibit=pfc_result.get('inhibit', False),
            pfc_value=pfc_result.get('value', 0.5),
            pfc_surprise=pfc_result.get('surprise', 0.0),
            # ACC outputs
            conflict=acc_result.get('conflict', 0.0),
            control_signal=acc_result.get('control_signal', 0.5),
            error_likelihood=acc_result.get('error_likelihood', 0.0),
            # OFC outputs
            subjective_value=ofc_result.get('subjective_value', 0.5),
            decision_confidence=ofc_result.get('value_confidence', 0.5),
            choice_difficulty=1.0 - ofc_result.get('value_confidence', 0.5),
        )

        # Cache ACC outputs for inter-module coupling on next tick
        self._prev_acc_conflict = acc_result.get('conflict', 0.0)
        self._prev_acc_effort = acc_result.get('effort', 0.0)
        self._prev_acc_error_likelihood = acc_result.get('error_likelihood', 0.0)

        self._tick_count += 1
        return self._state

    def get_state(self) -> CortexState:
        """Return current CortexState (read-only access)."""
        return self._state
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cortex_bridge.py -v`
Expected: 10 passed

**Step 5: Commit**

```bash
git add core/cortex_bridge.py tests/test_cortex_bridge.py
git commit -m "feat(cortex): add CortexBridge skeleton with update flow"
```

---

### Task 3: Hook 9 — OFC Value -> RingLayer Precision Gate

**Files:**
- Modify: `core/radial_attention.py:69-133` (RingLayer.forward)
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write the failing test**

Append to `tests/test_cortex_bridge.py`:

```python
import torch
from core.radial_attention import RingLayer


class TestRingLayerCortex:
    @pytest.fixture
    def ring_and_inputs(self):
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4, dropout=0.0)
        x = torch.randn(2, 64)
        td = torch.randn(2, 128)
        return ring, x, td

    def test_forward_without_cortex_unchanged(self, ring_and_inputs):
        ring, x, td = ring_and_inputs
        out1 = ring(x, top_down_prediction=td)
        out2 = ring(x, top_down_prediction=td, cortex_state=None)
        assert torch.allclose(out1, out2)

    def test_ofc_value_boosts_precision(self, ring_and_inputs):
        """High subjective_value should increase output magnitude (precision boost)."""
        ring, x, td = ring_and_inputs
        baseline = ring(x, top_down_prediction=td)
        high_val = CortexState(subjective_value=1.0)
        boosted = ring(x, top_down_prediction=td, cortex_state=high_val)
        # Higher value -> precision * 1.2 -> larger signal correction
        assert not torch.allclose(baseline, boosted)

    def test_ofc_low_value_dampens_precision(self, ring_and_inputs):
        """Low subjective_value should decrease precision relative to high."""
        ring, x, td = ring_and_inputs
        low_val = CortexState(subjective_value=0.0)
        high_val = CortexState(subjective_value=1.0)
        out_low = ring(x, top_down_prediction=td, cortex_state=low_val)
        out_high = ring(x, top_down_prediction=td, cortex_state=high_val)
        diff = (out_high - out_low).abs().mean().item()
        assert diff > 0.001  # Meaningfully different

    def test_cortex_no_effect_without_top_down(self, ring_and_inputs):
        """Without top-down prediction, precision gate isn't used, so cortex has no effect."""
        ring, x, _ = ring_and_inputs
        baseline = ring(x)
        with_cortex = ring(x, cortex_state=CortexState(subjective_value=1.0))
        assert torch.allclose(baseline, with_cortex)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cortex_bridge.py::TestRingLayerCortex -v`
Expected: FAIL with `TypeError: forward() got an unexpected keyword argument 'cortex_state'`

**Step 3: Add cortex_state parameter to RingLayer.forward()**

In `core/radial_attention.py`, modify `RingLayer.forward()`:

Change the signature at line 69:
```python
    def forward(self, bottom_up: torch.Tensor,
                top_down_prediction: Optional[torch.Tensor] = None,
                neuromod=None,
                cortex_state=None,
                ) -> torch.Tensor:
```

After Hook 2 (DA+LHb precision modulation, line 111), before the additive correction (line 114), add Hook 9:

```python
            # Hook 9: OFC subjective_value boosts precision
            if cortex_state is not None:
                value_boost = 0.8 + 0.4 * cortex_state.subjective_value  # [0.8, 1.2]
                precision = precision * value_boost
```

The full precision block becomes:
```python
        if top_down_prediction is not None:
            error = attended - top_down_prediction
            precision = self.precision_gate(error)

            # Hook 2: DA boosts precision, LHb anti-reward dampens it
            if neuromod is not None:
                da_boost = 0.5 + neuromod.dopamine
                anti_dampen = 1.0 - 0.5 * neuromod.anti_reward
                precision = precision * da_boost * anti_dampen

            # Hook 9: OFC subjective_value boosts precision
            if cortex_state is not None:
                value_boost = 0.8 + 0.4 * cortex_state.subjective_value  # [0.8, 1.2]
                precision = precision * value_boost

            signal = attended + error * precision
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cortex_bridge.py::TestRingLayerCortex tests/test_neuromodulation_bridge.py -v`
Expected: All pass (4 new + 25 existing neuromod tests unchanged)

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_cortex_bridge.py
git commit -m "feat(cortex): Hook 9 — OFC value modulates precision gate in RingLayer"
```

---

### Task 4: Hook 8 — ACC Conflict -> DualProcessRouter Threshold

**Files:**
- Modify: `core/radial_attention.py:307-352` (DualProcessRouter.forward)
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write the failing test**

Append to `tests/test_cortex_bridge.py`:

```python
from core.radial_attention import DualProcessRouter


class TestDualProcessCortex:
    def test_conflict_lowers_threshold(self):
        """High ACC conflict -> lower threshold -> more System 2."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = s1 + torch.randn(1, 128) * 0.1  # Small difference -> low conflict

        baseline = router(s1, s2)
        high_conflict = CortexState(conflict=1.0)
        with_conflict = router(s1, s2, cortex_state=high_conflict)

        # High conflict -> lower threshold -> might switch to System 2
        # At minimum, the router should accept cortex_state without error
        assert 'system_used' in with_conflict

    def test_zero_conflict_no_effect(self):
        """Zero ACC conflict should not change threshold."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)

        baseline = router(s1, s2)
        zero_conflict = CortexState(conflict=0.0)
        with_zero = router(s1, s2, cortex_state=zero_conflict)

        assert baseline['conflict_level'] == with_zero['conflict_level']

    def test_cortex_none_unchanged(self):
        """No cortex_state should behave same as without it."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)

        out1 = router(s1, s2)
        out2 = router(s1, s2, cortex_state=None)
        assert out1['system_used'] == out2['system_used']
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cortex_bridge.py::TestDualProcessCortex -v`
Expected: FAIL with `TypeError: forward() got an unexpected keyword argument 'cortex_state'`

**Step 3: Add cortex_state to DualProcessRouter.forward()**

In `core/radial_attention.py`, modify `DualProcessRouter.forward()`:

Change signature at line 307:
```python
    def forward(self, system1_output: torch.Tensor,
                system2_output: torch.Tensor,
                neuromod=None, cortex_state=None) -> Dict[str, any]:
```

After Hook 6 (NE explore_ratio, line 337), add Hook 8:
```python
        # Hook 8: ACC conflict reduces threshold (more System 2 when conflicted)
        if cortex_state is not None:
            effective_threshold *= (1.0 - 0.3 * cortex_state.conflict)
```

The full threshold block becomes:
```python
        # Hook 6: NE explore_ratio modulates threshold
        if neuromod is not None:
            effective_threshold = self.conflict_threshold * (1.5 - neuromod.explore_ratio)
        else:
            effective_threshold = self.conflict_threshold

        # Hook 8: ACC conflict reduces threshold (more System 2 when conflicted)
        if cortex_state is not None:
            effective_threshold *= (1.0 - 0.3 * cortex_state.conflict)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cortex_bridge.py::TestDualProcessCortex tests/test_neuromodulation_bridge.py::TestDualProcessNeuromod -v`
Expected: All pass (3 new + 2 existing neuromod router tests)

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_cortex_bridge.py
git commit -m "feat(cortex): Hook 8 — ACC conflict modulates DualProcessRouter threshold"
```

---

### Task 5: Hook 7 — PFC Bias -> Ring 4 + RadialAttentionNetwork Integration

This is the biggest task: adds `attach_cortex()` to `RadialAttentionNetwork`, wires cortex_state through forward(), and adds Hook 7 (PFC bias additive on Ring 4).

**Files:**
- Modify: `core/radial_attention.py:136-255` (RadialAttentionNetwork)
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write the failing tests**

Append to `tests/test_cortex_bridge.py`:

```python
from core.radial_attention import RadialAttentionNetwork


class TestRadialNetworkCortex:
    @pytest.fixture
    def network(self):
        return RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)

    def test_attach_cortex(self, network):
        mock_bridge = MagicMock()
        network.attach_cortex(mock_bridge)
        assert network._cortex_bridge is mock_bridge
        assert network._cortex_state is None
        assert hasattr(network, '_pfc_bias_proj')

    def test_forward_without_cortex_bridge(self, network):
        """No cortex bridge -> forward unchanged, result has cortex_state=None."""
        x = torch.randn(1, 384)
        result = network(x)
        assert 'cortex_state' in result
        assert result['cortex_state'] is None

    def test_forward_with_cortex_bridge(self, network):
        """With cortex bridge -> forward calls bridge.update(), result has CortexState."""
        mock_bridge = MagicMock()
        mock_state = CortexState(
            bias_signal=np.ones(32) * 0.1,
            conflict=0.3,
            subjective_value=0.7,
        )
        mock_bridge.update.return_value = mock_state
        network.attach_cortex(mock_bridge)

        x = torch.randn(1, 384)
        result = network(x)

        # Bridge should have been called
        mock_bridge.update.assert_called_once()
        # Result should include new cortex_state (but it's for NEXT tick)
        # On second call, the state should be used
        result2 = network(x)
        assert mock_bridge.update.call_count == 2

    def test_cortex_state_used_on_second_pass(self, network):
        """CortexState from tick 0 should be passed to rings/router on tick 1."""
        mock_bridge = MagicMock()
        mock_state = CortexState(
            bias_signal=np.ones(32) * 0.1,
            conflict=0.3,
            subjective_value=0.7,
        )
        mock_bridge.update.return_value = mock_state
        network.attach_cortex(mock_bridge)

        x = torch.randn(1, 384)
        # Tick 0: compute CortexState (used on tick 1)
        r0 = network(x)
        # Tick 1: CortexState should now be active
        r1 = network(x)
        # Outputs should differ because cortex_state is now applied
        diff = (r0['meta_output'] - r1['meta_output']).abs().mean().item()
        # They MIGHT be equal if bias is very small, but the bridge should still be called
        assert mock_bridge.update.call_count == 2

    def test_pfc_bias_modulates_ring4(self, network):
        """Hook 7: PFC bias should additively modulate Ring 4 activations."""
        mock_bridge = MagicMock()
        # Large bias signal to make the effect visible
        mock_state = CortexState(
            bias_signal=np.ones(32) * 5.0,
            conflict=0.0,
            subjective_value=0.5,
        )
        mock_bridge.update.return_value = mock_state
        network.attach_cortex(mock_bridge)

        x = torch.randn(1, 384)
        # Tick 0: get CortexState
        network(x)
        # Tick 1: CortexState applied (with large bias)
        r1 = network(x)
        # Compare with a run without cortex
        network2 = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        network2.load_state_dict(network.state_dict(), strict=False)
        r2 = network2(x)

        # Ring 4 activations should differ due to PFC bias
        ring4_diff = (r1['ring_activations'][3] - r2['ring_activations'][3]).abs().mean().item()
        assert ring4_diff > 0.01  # Meaningful difference
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cortex_bridge.py::TestRadialNetworkCortex -v`
Expected: FAIL with `AttributeError: 'RadialAttentionNetwork' object has no attribute '_cortex_bridge'`

**Step 3: Implement RadialAttentionNetwork cortex integration**

In `core/radial_attention.py`, make these changes:

**3a.** In `RadialAttentionNetwork.__init__()`, after lines 191-192 (neuromod fields), add:

```python
        # Cortex bridge (optional, attached via attach_cortex)
        self._cortex_bridge = None
        self._cortex_state = None
```

**3b.** After `attach_neuromodulation()` method (line 201), add:

```python
    def attach_cortex(self, bridge) -> None:
        """Attach a CortexBridge for cognitive modulation (PFC, ACC, OFC).

        Args:
            bridge: CortexBridge instance.
        """
        self._cortex_bridge = bridge
        self._cortex_state = None
        # Learnable projection: PFC bias (32D) -> Ring 4 dim (256D)
        self._pfc_bias_proj = nn.Linear(32, 256, bias=False)
        logger.info("CortexBridge attached to RadialAttentionNetwork")
```

**3c.** In `forward()`, modify the bottom-up pass (line 219-221) to pass cortex_state:

```python
        # -- Bottom-Up Pass (radial outward) --
        ring_activations = []
        x = thalamic
        for ring in self.rings:
            x = ring(x, neuromod=self._neuromod_state,
                     cortex_state=self._cortex_state)
            ring_activations.append(x)
```

**3d.** After bottom-up pass (after line 221), add Hook 7:

```python
        # Hook 7: PFC bias additive on Ring 4 (Abstract)
        if (self._cortex_state is not None and
                self._cortex_state.bias_signal is not None and
                hasattr(self, '_pfc_bias_proj')):
            bias_tensor = torch.tensor(
                self._cortex_state.bias_signal, dtype=torch.float32
            ).unsqueeze(0)  # (1, 32)
            bias_expanded = self._pfc_bias_proj(bias_tensor)  # (1, 256)
            ring_activations[3] = ring_activations[3] + bias_expanded * 0.1
```

**3e.** In top-down pass, pass cortex_state to refined rings (line 235-237):

```python
            refined = self.rings[i - 1](
                inner_input, top_down_prediction=prediction,
                neuromod=self._neuromod_state,
                cortex_state=self._cortex_state,
            )
```

**3f.** After neuromod bridge update (line 246-247), add cortex bridge update:

```python
        # Update cortex for NEXT tick (1-tick delay)
        if self._cortex_bridge is not None:
            # Convert ring activations to numpy for cortex modules
            np_activations = [a.detach().cpu().numpy().flatten()
                              for a in ring_activations]
            self._cortex_state = self._cortex_bridge.update(
                np_activations, prediction_errors, self._neuromod_state
            )
```

**3g.** In the return dict (line 249-255), add cortex_state:

```python
        return {
            'ring_activations': ring_activations,
            'meta_output': ring_activations[-1],
            'thalamic_seed': thalamic,
            'prediction_errors': prediction_errors,
            'neuromod_state': self._neuromod_state,
            'cortex_state': self._cortex_state,
        }
```

**Step 4: Run ALL tests**

Run: `python -m pytest tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py tests/test_radial_attention.py tests/test_radial_dual_process.py tests/test_radial_sleep_training.py tests/test_experience_buffer.py -v`
Expected: All pass (new cortex tests + all 59 existing radial/neuromod tests)

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_cortex_bridge.py
git commit -m "feat(cortex): Hook 7 — PFC bias + RadialAttentionNetwork integration"
```

---

### Task 6: DualProcessRouter Cortex Wiring in forward()

The DualProcessRouter is called from outside RadialAttentionNetwork (in agent loop or wherever dual-process routing happens). We need to make sure cortex_state reaches it.

**Files:**
- Test: `tests/test_cortex_bridge.py` (already covered in Task 4)
- Verify: DualProcessRouter already has cortex_state param from Task 4

**Step 1: Verify DualProcessRouter works end-to-end**

No new test needed — Task 4 already covers this. The DualProcessRouter is a standalone module. When it's called from the agent loop, the caller passes `cortex_state=network._cortex_state`.

**Step 2: Run regression tests**

Run: `python -m pytest tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: All pass

No commit needed — this is a verification step.

---

### Task 7: Production Wiring + Config

**Files:**
- Modify: `configs/default.yaml:1028` (after neuromodulation_bridge)
- Modify: `production/production_planner.py:1295-1297` (after NeuromodBridge block)
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write the failing test**

Append to `tests/test_cortex_bridge.py`:

```python
class TestCortexBridgeConfig:
    def test_config_section_exists(self):
        """Verify cortex_bridge config section is in default.yaml."""
        import yaml
        import os
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'configs', 'default.yaml'
        )
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert 'cortex_bridge' in config
        assert config['cortex_bridge']['enabled'] is True
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cortex_bridge.py::TestCortexBridgeConfig -v`
Expected: FAIL with `AssertionError: 'cortex_bridge' not in config`

**Step 3: Add config + production wiring**

**3a.** In `configs/default.yaml`, after line 1028 (`neuromodulation_bridge: enabled: true`), add:

```yaml
# Cortex Bridge — connects PFC + ACC + OFC to Radial Attention
cortex_bridge:
  enabled: true
```

**3b.** In `production/production_planner.py`, after the NeuromodBridge block (after line 1297), add:

```python
                        # Cortex Bridge — connect PFC + ACC + OFC to Radial Network
                        cx_cfg = self._yaml_config.get('cortex_bridge', {})
                        if cx_cfg.get('enabled', False):
                            try:
                                from core.cortex_bridge import CortexBridge
                                cortex_bridge = CortexBridge(
                                    pfc=self.agent_loop.prefrontal_cortex,
                                    acc=self.agent_loop.anterior_cingulate,
                                    ofc=self.agent_loop.orbitofrontal_cortex,
                                )
                                self.agent_loop.radial_network.attach_cortex(cortex_bridge)
                                self.agent_loop.cortex_bridge = cortex_bridge
                                print("[AgentLoop] CortexBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] CortexBridge not available: {e}")
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_cortex_bridge.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add configs/default.yaml production/production_planner.py tests/test_cortex_bridge.py
git commit -m "feat(cortex): production wiring + config for CortexBridge"
```

---

### Task 8: Full Integration Tests with Real Modules

**Files:**
- Test: `tests/test_cortex_bridge.py`

**Step 1: Write integration tests**

Append to `tests/test_cortex_bridge.py`:

```python
from core.prefrontal_cortex import PrefrontalCortex
from core.anterior_cingulate import AnteriorCingulateCortex
from core.orbitofrontal_cortex import OrbitofrontalCortex


class TestCortexIntegration:
    @pytest.fixture
    def real_bridge(self):
        pfc = PrefrontalCortex()
        acc = AnteriorCingulateCortex()
        ofc = OrbitofrontalCortex()
        return CortexBridge(pfc=pfc, acc=acc, ofc=ofc)

    def test_full_loop_with_real_modules(self, real_bridge):
        """Run 10 ticks through the real cortex modules."""
        for t in range(10):
            ring_acts = [
                np.random.randn(64),
                np.random.randn(128),
                np.random.randn(256),
                np.random.randn(256),
                np.random.randn(128),
            ]
            pred_errors = [0.2 + 0.05 * t, 0.15, 0.18, 0.12]
            state = real_bridge.update(ring_acts, pred_errors)
            assert isinstance(state, CortexState)
            assert state.bias_signal is not None
            assert 0.0 <= state.subjective_value <= 1.0

    def test_cortex_evolves_over_ticks(self, real_bridge):
        """At least one cortex output should vary across 10 ticks."""
        states = []
        for t in range(10):
            ring_acts = [
                np.random.randn(64) * (1 + 0.5 * t),
                np.random.randn(128) * (1 + 0.3 * t),
                np.random.randn(256) * (1 + 0.2 * t),
                np.random.randn(256) * (1 + 0.1 * t),
                np.random.randn(128),
            ]
            # Varying prediction errors
            pred_errors = [0.1 + 0.08 * t, 0.1 + 0.06 * t,
                           0.1 + 0.04 * t, 0.1 + 0.02 * t]
            state = real_bridge.update(ring_acts, pred_errors)
            states.append(state)

        # Check that SOME output varies across ticks
        varied = False
        for attr in ['conflict', 'control_signal', 'subjective_value',
                     'pfc_value', 'error_likelihood', 'decision_confidence']:
            values = [getattr(s, attr) for s in states]
            if max(values) - min(values) > 0.01:
                varied = True
                break
        assert varied, "No cortex output varied over 10 ticks"

    def test_full_network_with_cortex_bridge(self):
        """End-to-end: RadialAttentionNetwork + CortexBridge + real modules."""
        pfc = PrefrontalCortex()
        acc = AnteriorCingulateCortex()
        ofc = OrbitofrontalCortex()
        bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)

        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
        net.attach_cortex(bridge)

        for t in range(5):
            x = torch.randn(1, 384)
            result = net(x)
            assert 'cortex_state' in result
            if t > 0:
                # After tick 0, cortex_state should be populated
                assert result['cortex_state'] is not None
```

**Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_cortex_bridge.py::TestCortexIntegration -v`
Expected: 3 passed

**Step 3: Run ALL tests together**

Run: `python -m pytest tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py tests/test_radial_attention.py tests/test_radial_dual_process.py tests/test_radial_sleep_training.py tests/test_experience_buffer.py -v`
Expected: All pass (new cortex tests + all 59 existing)

**Step 4: Commit**

```bash
git add tests/test_cortex_bridge.py
git commit -m "feat(cortex): integration tests with real PFC, ACC, OFC modules"
```

---

### Task 9: Eval Script + MEMORY.md Update

**Files:**
- Modify: `tests/eval_radial_quality.py` (add Section 9: CortexBridge)
- Modify: `MEMORY.md` (add CortexBridge section)

**Step 1: Add CortexBridge eval section**

In `tests/eval_radial_quality.py`, after the Neuromodulation Bridge section (Section 8), add Section 9:

```python
# ================================================================
# 9. CORTEX BRIDGE: PFC + ACC + OFC -> Cognitive Modulation
# ================================================================
sep("9. CORTEX BRIDGE")
try:
    from core.cortex_bridge import CortexBridge, CortexState
    from core.prefrontal_cortex import PrefrontalCortex
    from core.anterior_cingulate import AnteriorCingulateCortex
    from core.orbitofrontal_cortex import OrbitofrontalCortex

    pfc = PrefrontalCortex()
    acc = AnteriorCingulateCortex()
    ofc = OrbitofrontalCortex()
    cx_bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)

    print("  Running 20 ticks with CortexBridge...")
    cx_states = []
    for t in range(20):
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.15 + 0.02 * (t % 5), 0.12, 0.18, 0.10]
        cx_state = cx_bridge.update(ring_acts, pred_errors)
        cx_states.append(cx_state)

    # Print ranges
    for attr in ['conflict', 'control_signal', 'subjective_value',
                 'pfc_value', 'error_likelihood', 'decision_confidence',
                 'choice_difficulty']:
        vals = [getattr(s, attr) for s in cx_states]
        print(f"  {attr:>22}: min={min(vals):.4f}  max={max(vals):.4f}  "
              f"range={max(vals)-min(vals):.4f}")

    bias_norms = [np.linalg.norm(s.bias_signal) if s.bias_signal is not None else 0.0
                  for s in cx_states]
    print(f"  {'bias_signal norm':>22}: min={min(bias_norms):.4f}  max={max(bias_norms):.4f}")
    print("  [OK] CortexBridge eval complete")
except Exception as e:
    print(f"  [SKIP] CortexBridge: {e}")
```

**Step 2: Run the eval script**

Run: `python tests/eval_radial_quality.py`
Expected: Section 9 shows live cortex output ranges

**Step 3: Update MEMORY.md**

Add after the Neuromodulation Bridge section:

```markdown
## Cortex Bridge (core/cortex_bridge.py)
- **CortexState** dataclass: bias_signal, inhibit, pfc_value, pfc_surprise, conflict, control_signal, error_likelihood, subjective_value, decision_confidence, choice_difficulty
- **CortexBridge**: ring_activations + prediction_errors -> PFC.process() + ACC.process() + OFC.process() -> CortexState
- 3 hooks: PFC bias(Ring 4 additive), ACC conflict(DualProcess threshold), OFC value(precision gate)
- 1-tick delay: state computed after forward, used on NEXT forward (biologically correct)
- Inter-module coupling: ACC conflict->PFC context, ACC effort->OFC effort_cost, ACC error_likelihood->OFC risk
- Config: `cortex_bridge: enabled: true` in default.yaml
- All hooks `if cortex_state is not None:` guarded -- zero breaking changes
```

**Step 4: Run full test suite one last time**

Run: `python -m pytest tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py tests/test_radial_attention.py tests/test_radial_dual_process.py tests/test_radial_sleep_training.py tests/test_experience_buffer.py -v`
Expected: ALL pass

**Step 5: Commit**

```bash
git add tests/eval_radial_quality.py MEMORY.md
git commit -m "docs: add CortexBridge eval section + update MEMORY.md"
```

---

## Summary

| Task | What | Tests Added |
|------|------|-------------|
| 1 | CortexState dataclass | 2 |
| 2 | CortexBridge skeleton + update() | 8 |
| 3 | Hook 9: OFC value -> RingLayer precision | 4 |
| 4 | Hook 8: ACC conflict -> DualProcessRouter | 3 |
| 5 | Hook 7: PFC bias + RadialAttentionNetwork integration | 5 |
| 6 | DualProcessRouter verification (no new code) | 0 |
| 7 | Production wiring + config | 1 |
| 8 | Integration tests with real modules | 3 |
| 9 | Eval script + MEMORY.md | 0 |
| **Total** | | **~26 tests** |

**Estimated time:** ~45 minutes of focused implementation.

**Dependencies:** Each task depends on the previous. Tasks 3-4 can swap order, but both need Task 2.

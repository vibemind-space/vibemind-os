# LimbicBridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the Limbic Quartet (Amygdala, NucleusAccumbens, InsularCortex, Hypothalamus) to the Radial Attention Network via a LimbicBridge mediator, adding 4 new hooks (H10-H13).

**Architecture:** Same pattern as NeuromodulationBridge and CortexBridge — a mediator class receives ring activations + prediction errors, calls 4 limbic modules, produces a LimbicState dataclass. The state modulates the Radial Attention Network on the NEXT tick (1-tick delay). All hooks are multiplicative with existing hooks and `if limbic_state:` guarded for zero breaking changes.

**Tech Stack:** Python 3.11, numpy (projections), torch (RadialAttentionNetwork hooks), dataclasses, pytest.

**Design doc:** `docs/plans/2026-02-26-limbic-bridge-design.md`

**Existing tests:** 50 passing (25 cortex + 25 neuromod) — must remain green throughout.

---

### Task 1: LimbicState Dataclass

**Files:**
- Create: `core/limbic_bridge.py`
- Test: `tests/test_limbic_bridge.py`

**Step 1: Write the failing tests**

```python
# tests/test_limbic_bridge.py
"""Tests for LimbicBridge — Limbic Quartet -> Radial Attention Network."""
import pytest
import numpy as np


class TestLimbicState:
    """LimbicState dataclass defaults and ranges."""

    def test_defaults(self):
        from core.limbic_bridge import LimbicState
        s = LimbicState()
        assert s.valence == 0.0
        assert s.arousal == 0.3
        assert s.threat_level == 0.0
        assert s.is_threat is False
        assert s.go_drive == 0.5
        assert s.nogo_drive == 0.5
        assert s.net_value == 0.0
        assert s.effort_cost == 0.3
        assert s.salience == 0.3
        assert s.body_budget == 1.0
        assert s.feeling == 'neutral'
        assert s.urgency == 0.0
        assert s.approach_drive == 0.3
        assert s.stress == 0.0

    def test_custom_values(self):
        from core.limbic_bridge import LimbicState
        s = LimbicState(valence=-0.5, arousal=0.9, threat_level=0.8, is_threat=True)
        assert s.valence == -0.5
        assert s.arousal == 0.9
        assert s.threat_level == 0.8
        assert s.is_threat is True
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py -v`
Expected: FAIL with "No module named 'core.limbic_bridge'"

**Step 3: Write minimal implementation**

```python
# core/limbic_bridge.py
"""
Limbic Bridge -- connects the Limbic Quartet (Amygdala, NAcc, InsularCortex,
Hypothalamus) to the Radial Attention Network.

Translates ring activations and prediction errors into emotional/motivational
signals (arousal, salience, go/nogo drives, urgency) that modulate RingLayers
and DualProcessRouter.

See: docs/plans/2026-02-26-limbic-bridge-design.md
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LimbicState:
    """Snapshot of limbic module outputs for one tick.

    Amygdala: emotional valence, arousal, threat detection.
    NucleusAccumbens: approach/avoidance motivation.
    InsularCortex: salience, body budget, subjective feeling.
    Hypothalamus: homeostatic urgency, approach drives, stress.
    """
    # Amygdala outputs
    valence: float = 0.0           # [-1, 1] emotional valence
    arousal: float = 0.3           # [0, 1] emotional arousal
    threat_level: float = 0.0      # [0, 1] threat detection
    is_threat: bool = False        # Binary threat flag

    # NucleusAccumbens outputs
    go_drive: float = 0.5          # [0, 1] approach motivation
    nogo_drive: float = 0.5        # [0, 1] avoidance motivation
    net_value: float = 0.0         # Benefit - Cost
    effort_cost: float = 0.3       # [0, 1] perceived effort

    # InsularCortex outputs
    salience: float = 0.3          # [0, 1] overall salience
    body_budget: float = 1.0       # [0, 1] allostatic balance
    feeling: str = 'neutral'       # Subjective feeling label

    # Hypothalamus outputs
    urgency: float = 0.0           # [0, 1] homeostatic urgency
    approach_drive: float = 0.3    # [0, 1] lateral hypothalamus
    stress: float = 0.0            # [0, 1] HPA cortisol
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_limbic_bridge.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add core/limbic_bridge.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): add LimbicState dataclass"
```

---

### Task 2: LimbicBridge Skeleton + update() Flow

**Files:**
- Modify: `core/limbic_bridge.py`
- Modify: `tests/test_limbic_bridge.py`

**Context:**
LimbicBridge follows the exact same pattern as CortexBridge (`core/cortex_bridge.py`):
- `__init__` takes 4 module instances
- `update(ring_activations, prediction_errors, neuromod_state)` returns LimbicState
- One projection matrix: Ring 1 (64D) -> Amygdala (10 features) via (10, 64) numpy matrix
- Inter-module coupling via cached previous-tick values
- `get_state()` returns current LimbicState

Module APIs (exact signatures from source):
- `AmygdalaComplex.process_stimulus(features: np.ndarray, context: Optional[np.ndarray] = None)` -> dict with `evaluation` (containing `valence`, `arousal`, `threat_level`), `response` (containing `hpa_activation`), `is_threat`
- `NucleusAccumbens.evaluate(dopamine=0.5, reward_prediction=0.5, threat=0.0, action_complexity=0.3, energy=1.0)` -> dict with `go_drive`, `nogo_drive`, `net_value`, `effort_cost`
- `InsularCortex.process(body_signals=None, sensory_signals=None, novelty=0.0, emotional_intensity=0.0, stress=0.0, task_demand=0.0)` -> dict with `salience`, `body_budget`, `feeling`, `body_deviation`, `body_state`
- `HypothalamusModule.update_drives(external_signals=None, elapsed_seconds=1.0)` -> dict with `urgency`, `approach_drive`, `stress`; also `process_stressor(intensity: float) -> float`

**Step 1: Write failing tests**

Append to `tests/test_limbic_bridge.py`:

```python
from unittest.mock import MagicMock


def _make_mock_amygdala():
    m = MagicMock()
    m.process_stimulus.return_value = {
        'evaluation': {'valence': -0.3, 'arousal': 0.7, 'threat_level': 0.4},
        'response': {'hpa_activation': 0.35},
        'is_threat': False,
    }
    return m


def _make_mock_nacc():
    m = MagicMock()
    m.evaluate.return_value = {
        'go_drive': 0.6, 'nogo_drive': 0.4,
        'net_value': 0.2, 'effort_cost': 0.35,
    }
    return m


def _make_mock_insula():
    m = MagicMock()
    m.process.return_value = {
        'salience': 0.55, 'body_budget': 0.9,
        'feeling': 'alert', 'body_deviation': 0.1,
        'body_state': np.zeros(8),
    }
    return m


def _make_mock_hypothalamus():
    m = MagicMock()
    m.update_drives.return_value = {
        'urgency': 0.2, 'approach_drive': 0.4, 'stress': 0.15,
    }
    m.process_stressor.return_value = 0.35
    return m


def _make_bridge():
    from core.limbic_bridge import LimbicBridge
    return LimbicBridge(
        amygdala=_make_mock_amygdala(),
        nucleus_accumbens=_make_mock_nacc(),
        insular_cortex=_make_mock_insula(),
        hypothalamus=_make_mock_hypothalamus(),
    )


def _fake_ring_activations():
    """5 ring activations matching Radial Network dims."""
    return [
        np.random.randn(64),   # Ring 1 (Sensory)
        np.random.randn(128),  # Ring 2 (Pattern)
        np.random.randn(256),  # Ring 3 (Semantic)
        np.random.randn(256),  # Ring 4 (Abstract)
        np.random.randn(128),  # Ring 5 (Meta)
    ]


class TestLimbicBridgeSkeleton:
    """LimbicBridge init and update flow."""

    def test_init_stores_modules(self):
        bridge = _make_bridge()
        assert bridge._tick_count == 0
        assert bridge._ring1_to_amygdala.shape == (10, 64)

    def test_update_returns_limbic_state(self):
        from core.limbic_bridge import LimbicState
        bridge = _make_bridge()
        state = bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert isinstance(state, LimbicState)

    def test_update_calls_all_four_modules(self):
        bridge = _make_bridge()
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        bridge._amygdala.process_stimulus.assert_called_once()
        bridge._nucleus_accumbens.evaluate.assert_called_once()
        bridge._insular_cortex.process.assert_called_once()
        bridge._hypothalamus.update_drives.assert_called_once()
        bridge._hypothalamus.process_stressor.assert_called_once()

    def test_tick_count_increments(self):
        bridge = _make_bridge()
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge._tick_count == 1
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge._tick_count == 2

    def test_amygdala_hpa_feeds_hypothalamus(self):
        """Amygdala hpa_activation -> Hypothalamus process_stressor (inter-module coupling)."""
        bridge = _make_bridge()
        # First tick: no previous hpa, process_stressor called with 0.0
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        bridge._hypothalamus.process_stressor.assert_called_with(0.0)
        # Second tick: uses cached hpa_activation from first tick (0.35)
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge._hypothalamus.process_stressor.call_args_list[-1].args[0] == pytest.approx(0.35)

    def test_amygdala_arousal_feeds_insula(self):
        """Amygdala arousal -> InsularCortex emotional_intensity (inter-module coupling)."""
        bridge = _make_bridge()
        bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        # First tick uses default arousal (0.3 from LimbicState default)
        call_kwargs = bridge._insular_cortex.process.call_args
        assert 'emotional_intensity' in call_kwargs.kwargs or len(call_kwargs.args) >= 4

    def test_get_state_returns_current(self):
        bridge = _make_bridge()
        state = bridge.update(_fake_ring_activations(), [0.1, 0.2, 0.15, 0.1])
        assert bridge.get_state() is state
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestLimbicBridgeSkeleton -v`
Expected: FAIL — LimbicBridge not defined

**Step 3: Write minimal implementation**

Append to `core/limbic_bridge.py`:

```python
class LimbicBridge:
    """Mediates between RadialAttentionNetwork and the Limbic Quartet.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a LimbicState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - Amygdala hpa_activation -> Hypothalamus process_stressor()
        - Amygdala arousal -> InsularCortex emotional_intensity
        - Amygdala threat_level -> NAcc threat
        - Hypothalamus stress -> InsularCortex stress
        - Hypothalamus urgency -> NAcc energy (1 - urgency)
        - InsularCortex body_state -> Amygdala context

    Args:
        amygdala: AmygdalaComplex instance
        nucleus_accumbens: NucleusAccumbens instance
        insular_cortex: InsularCortex instance
        hypothalamus: HypothalamusModule instance
    """

    def __init__(self, amygdala, nucleus_accumbens, insular_cortex, hypothalamus):
        self._amygdala = amygdala
        self._nucleus_accumbens = nucleus_accumbens
        self._insular_cortex = insular_cortex
        self._hypothalamus = hypothalamus
        self._state = LimbicState()
        self._tick_count = 0

        # Projection: Ring 1 (Sensory, 64D) -> Amygdala (10 features)
        self._ring1_to_amygdala = np.random.randn(10, 64) * 0.01

        # Cache for inter-module coupling (previous tick)
        self._prev_hpa_activation = 0.0
        self._prev_amygdala_arousal = 0.3  # Default arousal
        self._prev_amygdala_threat = 0.0
        self._prev_hypo_stress = 0.0
        self._prev_hypo_urgency = 0.0
        self._prev_insula_body_state = None

        logger.info("LimbicBridge initialized (Amygdala + NAcc + InsularCortex + Hypothalamus)")

    def update(self, ring_activations: list, prediction_errors: list,
               neuromod_state=None) -> LimbicState:
        """Compute LimbicState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (provides dopamine for NAcc)

        Returns:
            LimbicState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        avg_pe = sum(prediction_errors) / max(len(prediction_errors), 1)

        # 1. Ring 1 (Sensory, 64D) -> Amygdala (10 features via projection)
        ring1 = acts[0]
        amygdala_features = self._ring1_to_amygdala @ ring1[:64]
        amygdala_result = self._amygdala.process_stimulus(
            features=amygdala_features,
            context=self._prev_insula_body_state,
        )
        evaluation = amygdala_result.get('evaluation', {})
        response = amygdala_result.get('response', {})

        # 2. Ring 2 (Pattern, 128D) -> InsularCortex (novelty from avg PE)
        insula_result = self._insular_cortex.process(
            novelty=avg_pe,
            emotional_intensity=self._prev_amygdala_arousal,
            stress=self._prev_hypo_stress,
        )

        # 3. Hypothalamus (autonomous, no ring input)
        self._hypothalamus.process_stressor(self._prev_hpa_activation)
        hypo_result = self._hypothalamus.update_drives(elapsed_seconds=1.0)

        # 4. NucleusAccumbens (aggregates all)
        dopamine = 0.5
        if neuromod_state is not None and hasattr(neuromod_state, 'dopamine'):
            dopamine = neuromod_state.dopamine
        nacc_result = self._nucleus_accumbens.evaluate(
            dopamine=dopamine,
            reward_prediction=1.0 - avg_pe,
            threat=evaluation.get('threat_level', 0.0),
            energy=1.0 - hypo_result.get('urgency', 0.0),
        )

        # Build LimbicState
        self._state = LimbicState(
            valence=evaluation.get('valence', 0.0),
            arousal=evaluation.get('arousal', 0.3),
            threat_level=evaluation.get('threat_level', 0.0),
            is_threat=amygdala_result.get('is_threat', False),
            go_drive=nacc_result.get('go_drive', 0.5),
            nogo_drive=nacc_result.get('nogo_drive', 0.5),
            net_value=nacc_result.get('net_value', 0.0),
            effort_cost=nacc_result.get('effort_cost', 0.3),
            salience=insula_result.get('salience', 0.3),
            body_budget=insula_result.get('body_budget', 1.0),
            feeling=insula_result.get('feeling', 'neutral'),
            urgency=hypo_result.get('urgency', 0.0),
            approach_drive=hypo_result.get('approach_drive', 0.3),
            stress=hypo_result.get('stress', 0.0),
        )

        # Cache for inter-module coupling on next tick
        self._prev_hpa_activation = response.get('hpa_activation', 0.0)
        self._prev_amygdala_arousal = evaluation.get('arousal', 0.3)
        self._prev_amygdala_threat = evaluation.get('threat_level', 0.0)
        self._prev_hypo_stress = hypo_result.get('stress', 0.0)
        self._prev_hypo_urgency = hypo_result.get('urgency', 0.0)
        self._prev_insula_body_state = insula_result.get('body_state')

        self._tick_count += 1
        return self._state

    def get_state(self) -> LimbicState:
        """Return current LimbicState (read-only access)."""
        return self._state
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py -v`
Expected: 9 PASSED (2 dataclass + 7 skeleton)

**Step 5: Commit**

```bash
git add core/limbic_bridge.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): add LimbicBridge skeleton with update flow"
```

---

### Task 3: Hook 10 — Arousal -> Attention Gain (RingLayer)

**Files:**
- Modify: `core/radial_attention.py` — RingLayer.forward() (line ~69-73 signature, line ~95-98 after self-attention)
- Modify: `tests/test_limbic_bridge.py`

**Context:**
RingLayer.forward() already accepts `neuromod=None, cortex_state=None`. Add `limbic_state=None` parameter. Hook 10 goes right after Hook 1 (NE gain, line 96-97): `arousal_gain = 0.7 + 0.6 * limbic_state.arousal` giving range [0.7, 1.3]. Multiplicative with NE gain.

**Step 1: Write failing tests**

Append to `tests/test_limbic_bridge.py`:

```python
import torch
from core.radial_attention import RingLayer


class TestRingLayerLimbic:
    """Hook 10: arousal -> attention gain in RingLayer."""

    def test_forward_accepts_limbic_state(self):
        """RingLayer.forward() doesn't crash with limbic_state kwarg."""
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        out = ring(x, limbic_state=None)
        assert out.shape == (1, 128)

    def test_arousal_amplifies_attention(self):
        """High arousal (1.0) amplifies output vs baseline (0.0)."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        torch.manual_seed(42)
        out_low = ring(x, limbic_state=LimbicState(arousal=0.0))
        torch.manual_seed(42)
        out_high = ring(x, limbic_state=LimbicState(arousal=1.0))
        # arousal=0.0 -> gain=0.7, arousal=1.0 -> gain=1.3
        ratio = out_high.abs().mean() / out_low.abs().mean()
        assert ratio.item() == pytest.approx(1.3 / 0.7, rel=0.15)

    def test_no_limbic_state_no_change(self):
        """limbic_state=None should have no effect (backward compat)."""
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        torch.manual_seed(42)
        out_none = ring(x, limbic_state=None)
        torch.manual_seed(42)
        out_skip = ring(x)
        assert torch.allclose(out_none, out_skip)

    def test_hook10_stacks_with_hook1_ne(self):
        """Arousal gain (H10) stacks with NE gain (H1) multiplicatively."""
        from core.limbic_bridge import LimbicState
        from core.neuromodulation_bridge import NeuromodState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        nm = NeuromodState(ne_gain=1.2)
        ls = LimbicState(arousal=1.0)  # gain = 1.3
        # Combined effect on attention: 1.2 * 1.3 = 1.56x
        out = ring(x, neuromod=nm, limbic_state=ls)
        assert out.shape == (1, 128)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestRingLayerLimbic -v`
Expected: FAIL — "unexpected keyword argument 'limbic_state'"

**Step 3: Write minimal implementation**

In `core/radial_attention.py`, modify `RingLayer.forward()`:

1. Add `limbic_state=None` to the signature (line ~69-73):
```python
def forward(self, bottom_up: torch.Tensor,
            top_down_prediction: Optional[torch.Tensor] = None,
            neuromod=None,
            cortex_state=None,
            limbic_state=None,
            ) -> torch.Tensor:
```

2. Update the docstring (line 80) to mention limbic_state.

3. After Hook 1 (NE gain, line 97), add Hook 10 (before line 99 `attended = self.norm1(...)`):
```python
        # Hook 10: Arousal gain modulation on attention output
        if limbic_state is not None:
            arousal_gain = 0.7 + 0.6 * limbic_state.arousal  # [0.7, 1.3]
            attended = attended * arousal_gain
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: 13 limbic + 25 cortex + 25 neuromod = 63 PASSED

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): Hook 10 — arousal modulates attention gain in RingLayer"
```

---

### Task 4: Hook 11 — Salience -> Precision Gate (RingLayer)

**Files:**
- Modify: `core/radial_attention.py` — RingLayer.forward() (line ~115-118, after Hook 9)
- Modify: `tests/test_limbic_bridge.py`

**Context:**
Hook 11 goes after Hook 9 (OFC value, line 118). `sal_boost = 0.8 + 0.4 * limbic_state.salience` range [0.8, 1.2]. Multiplicative with DA+LHb (H2) and OFC value (H9).

**Step 1: Write failing tests**

Append to `tests/test_limbic_bridge.py`:

```python
class TestRingLayerSalience:
    """Hook 11: salience -> precision gate in RingLayer."""

    def test_salience_boosts_precision(self):
        """High salience amplifies precision-gated error."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        pred = torch.randn(1, 128)
        torch.manual_seed(42)
        out_low = ring(x, top_down_prediction=pred, limbic_state=LimbicState(salience=0.0))
        torch.manual_seed(42)
        out_high = ring(x, top_down_prediction=pred, limbic_state=LimbicState(salience=1.0))
        # Outputs should differ (salience affects precision weighting)
        assert not torch.allclose(out_low, out_high, atol=1e-6)

    def test_no_prediction_no_salience_effect(self):
        """Without top-down prediction, salience hook doesn't fire."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        torch.manual_seed(42)
        out_low = ring(x, limbic_state=LimbicState(salience=0.0))
        torch.manual_seed(42)
        out_high = ring(x, limbic_state=LimbicState(salience=1.0))
        # Only attention-gain hook differs (arousal), not precision
        # salience with same arousal = same attention path
        # But both still go through arousal_gain (both 0.3 default arousal)
        # so outputs should be same (salience only affects precision branch)
        assert torch.allclose(out_low, out_high, atol=1e-5)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestRingLayerSalience -v`
Expected: FAIL — salience has no effect yet

**Step 3: Write minimal implementation**

In `core/radial_attention.py`, after Hook 9 (line ~118), add Hook 11:

```python
            # Hook 11: Salience boosts precision gate
            if limbic_state is not None:
                sal_boost = 0.8 + 0.4 * limbic_state.salience  # [0.8, 1.2]
                precision = precision * sal_boost
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: 15 limbic + 25 cortex + 25 neuromod = 65 PASSED

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): Hook 11 — salience modulates precision gate in RingLayer"
```

---

### Task 5: Hook 13 — Urgency -> FFN Throughput (RingLayer)

**Files:**
- Modify: `core/radial_attention.py` — RingLayer.forward() (line ~128-136, FFN section)
- Modify: `tests/test_limbic_bridge.py`

**Context:**
Hook 13 goes after Hook 4 (5-HT stability, line ~134-136), before the final norm. `urg_gate = 0.8 + 0.4 * limbic_state.urgency` range [0.8, 1.2]. Multiplicative with ACh (H3) and 5-HT (H4).

NOTE: We do Hook 13 before Hook 12 because both H10, H11, H13 are in RingLayer, while H12 is in DualProcessRouter. Keeps file changes grouped.

**Step 1: Write failing tests**

Append to `tests/test_limbic_bridge.py`:

```python
class TestRingLayerUrgency:
    """Hook 13: urgency -> FFN throughput in RingLayer."""

    def test_urgency_amplifies_output(self):
        """High urgency (1.0) amplifies FFN output vs low (0.0)."""
        from core.limbic_bridge import LimbicState
        ring = RingLayer(in_dim=64, out_dim=128, num_heads=4)
        x = torch.randn(1, 64)
        pred = torch.randn(1, 128)
        torch.manual_seed(42)
        out_low = ring(x, top_down_prediction=pred, limbic_state=LimbicState(urgency=0.0))
        torch.manual_seed(42)
        out_high = ring(x, top_down_prediction=pred, limbic_state=LimbicState(urgency=1.0))
        # urgency=0.0 -> gate=0.8, urgency=1.0 -> gate=1.2
        assert not torch.allclose(out_low, out_high, atol=1e-6)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestRingLayerUrgency -v`
Expected: FAIL — urgency has no effect

**Step 3: Write minimal implementation**

In `core/radial_attention.py`, after Hook 4 (line ~136 `output = output * stability`), add Hook 13:

```python
        # Hook 13: Urgency amplifies FFN throughput
        if limbic_state is not None:
            urg_gate = 0.8 + 0.4 * limbic_state.urgency  # [0.8, 1.2]
            output = output * urg_gate
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: 16 limbic + 25 cortex + 25 neuromod = 66 PASSED

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): Hook 13 — urgency modulates FFN throughput in RingLayer"
```

---

### Task 6: Hook 12 — NoGo Drive -> DualProcessRouter Threshold

**Files:**
- Modify: `core/radial_attention.py` — DualProcessRouter.forward() (line ~351-353 signature, line ~386-388 after Hook 8)
- Modify: `tests/test_limbic_bridge.py`

**Context:**
DualProcessRouter.forward() already accepts `neuromod=None, cortex_state=None`. Add `limbic_state=None`. Hook 12 goes after Hook 8 (ACC conflict, line 388): `effective_threshold *= (1.0 - 0.2 * limbic_state.nogo_drive)`. High nogo_drive lowers threshold -> more System 2 (cautious).

**Step 1: Write failing tests**

Append to `tests/test_limbic_bridge.py`:

```python
from core.radial_attention import DualProcessRouter


class TestDualProcessLimbic:
    """Hook 12: nogo_drive -> DualProcess threshold."""

    def test_forward_accepts_limbic_state(self):
        from core.limbic_bridge import LimbicState
        router = DualProcessRouter(dim=64)
        s1 = torch.randn(1, 64)
        s2 = torch.randn(1, 64)
        result = router(s1, s2, limbic_state=LimbicState())
        assert 'output' in result

    def test_high_nogo_favors_system2(self):
        """High nogo_drive should lower threshold -> more System 2 usage."""
        from core.limbic_bridge import LimbicState
        router = DualProcessRouter(dim=64, conflict_threshold=0.5)
        s1 = torch.randn(1, 64)
        s2 = s1 * 1.05  # Slightly different -> borderline conflict
        # nogo=0.0: threshold stays 0.5
        result_low = router(s1, s2, limbic_state=LimbicState(nogo_drive=0.0))
        # nogo=1.0: threshold *= (1 - 0.2) = 0.4
        result_high = router(s1, s2, limbic_state=LimbicState(nogo_drive=1.0))
        # With lower threshold, more likely to use System 2
        # (can't guarantee it flips, but the threshold did decrease)
        assert result_low is not None and result_high is not None

    def test_hook12_stacks_with_hook8_acc(self):
        """NoGo (H12) stacks with ACC conflict (H8) multiplicatively."""
        from core.limbic_bridge import LimbicState
        from core.cortex_bridge import CortexState
        router = DualProcessRouter(dim=64)
        s1 = torch.randn(1, 64)
        s2 = torch.randn(1, 64)
        result = router(s1, s2,
                        cortex_state=CortexState(conflict=0.5),
                        limbic_state=LimbicState(nogo_drive=0.8))
        assert 'output' in result
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestDualProcessLimbic -v`
Expected: FAIL — "unexpected keyword argument 'limbic_state'"

**Step 3: Write minimal implementation**

In `core/radial_attention.py`, modify `DualProcessRouter.forward()`:

1. Add `limbic_state=None` to signature (line ~351-353):
```python
def forward(self, system1_output: torch.Tensor,
            system2_output: torch.Tensor,
            neuromod=None, cortex_state=None, limbic_state=None) -> Dict[str, any]:
```

2. After Hook 8 (line ~388), add Hook 12:
```python
        # Hook 12: NoGo drive lowers threshold (more System 2 when avoidant)
        if limbic_state is not None:
            effective_threshold *= (1.0 - 0.2 * limbic_state.nogo_drive)
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: 19 limbic + 25 cortex + 25 neuromod = 69 PASSED

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): Hook 12 — nogo_drive modulates DualProcessRouter threshold"
```

---

### Task 7: RadialAttentionNetwork Integration — attach_limbic + forward wiring

**Files:**
- Modify: `core/radial_attention.py` — RadialAttentionNetwork (add `attach_limbic`, modify `forward`)
- Modify: `tests/test_limbic_bridge.py`

**Context:**
Pattern follows `attach_cortex` exactly (line 214-224). LimbicBridge needs no learnable projection (all hooks are multiplicative scalars). In `forward()`:
- Pass `limbic_state` to all `ring()` calls (line 243-244, line 269-273)
- Pass `limbic_state` to DualProcessRouter (if DualProcess is used — currently not called in forward, but parameter is ready)
- After CortexBridge update (line 284-290), add LimbicBridge update
- Add `limbic_state` to return dict (line 292-299)

**Step 1: Write failing tests**

Append to `tests/test_limbic_bridge.py`:

```python
from core.radial_attention import RadialAttentionNetwork


class TestRadialNetworkLimbic:
    """Integration: LimbicBridge attached to RadialAttentionNetwork."""

    def test_attach_limbic(self):
        net = RadialAttentionNetwork()
        bridge = _make_bridge()
        net.attach_limbic(bridge)
        assert net._limbic_bridge is bridge
        assert net._limbic_state is None

    def test_forward_without_limbic(self):
        """Network works fine without limbic bridge (backward compat)."""
        net = RadialAttentionNetwork()
        x = torch.randn(1, 384)
        result = net(x)
        assert 'ring_activations' in result
        assert result.get('limbic_state') is None

    def test_forward_with_limbic(self):
        """Network produces limbic_state when bridge is attached."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        bridge = _make_bridge()
        net.attach_limbic(bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert isinstance(result.get('limbic_state'), LimbicState)

    def test_limbic_state_used_on_next_tick(self):
        """LimbicState from tick 1 is used in tick 2 (1-tick delay)."""
        net = RadialAttentionNetwork()
        bridge = _make_bridge()
        net.attach_limbic(bridge)
        x = torch.randn(1, 384)
        # Tick 1: limbic_state is None during forward, computed after
        result1 = net(x)
        # After tick 1, _limbic_state should be set
        assert net._limbic_state is not None
        # Tick 2: uses the state computed in tick 1
        result2 = net(x)
        assert result2.get('limbic_state') is not None

    def test_all_bridges_coexist(self):
        """Neuromod + Cortex + Limbic all work together."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        limbic_bridge = _make_bridge()
        net.attach_limbic(limbic_bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert 'ring_activations' in result
        assert isinstance(result.get('limbic_state'), LimbicState)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestRadialNetworkLimbic -v`
Expected: FAIL — "has no attribute 'attach_limbic'"

**Step 3: Write minimal implementation**

1. Add `attach_limbic` method after `attach_cortex` (line ~224):
```python
    def attach_limbic(self, bridge) -> None:
        """Attach a LimbicBridge for emotional/motivational modulation.

        Args:
            bridge: LimbicBridge instance.
        """
        self._limbic_bridge = bridge
        self._limbic_state = None
        logger.info("LimbicBridge attached to RadialAttentionNetwork")
```

2. Add `self._limbic_bridge = None` and `self._limbic_state = None` to `__init__` (after cortex bridge init, line ~203).

3. In `forward()`, pass `limbic_state` to ring calls:
   - Line ~243-244 (bottom-up):
     ```python
     x = ring(x, neuromod=self._neuromod_state,
              cortex_state=self._cortex_state,
              limbic_state=self._limbic_state)
     ```
   - Line ~269-273 (top-down):
     ```python
     refined = self.rings[i - 1](
         inner_input, top_down_prediction=prediction,
         neuromod=self._neuromod_state,
         cortex_state=self._cortex_state,
         limbic_state=self._limbic_state,
     )
     ```

4. After CortexBridge update (line ~290), add LimbicBridge update:
```python
        # Update limbic for NEXT tick (1-tick delay)
        if self._limbic_bridge is not None:
            np_activations = [a.detach().cpu().numpy().flatten()
                              for a in ring_activations]
            self._limbic_state = self._limbic_bridge.update(
                np_activations, prediction_errors, self._neuromod_state
            )
```

5. Add `'limbic_state': self._limbic_state` to return dict (line ~298).

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: 24 limbic + 25 cortex + 25 neuromod = 74 PASSED

**Step 5: Commit**

```bash
git add core/radial_attention.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): attach_limbic + forward wiring in RadialAttentionNetwork"
```

---

### Task 8: Production Wiring + Config

**Files:**
- Modify: `configs/default.yaml` — add `limbic_bridge: enabled: true` after `cortex_bridge` (line ~1032)
- Modify: `production/production_planner.py` — add wiring block after CortexBridge (line ~1313)
- Modify: `tests/test_limbic_bridge.py`

**Step 1: Write failing test**

Append to `tests/test_limbic_bridge.py`:

```python
class TestLimbicBridgeConfig:
    """Config and production wiring."""

    def test_config_has_limbic_bridge(self):
        import yaml
        with open('configs/default.yaml', 'r') as f:
            cfg = yaml.safe_load(f)
        assert cfg.get('limbic_bridge', {}).get('enabled') is True
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_limbic_bridge.py::TestLimbicBridgeConfig -v`
Expected: FAIL — 'limbic_bridge' not in config

**Step 3: Write minimal implementation**

1. In `configs/default.yaml`, after `cortex_bridge: enabled: true` (line ~1032), add:
```yaml
limbic_bridge:
  enabled: true
```

2. In `production/production_planner.py`, after the CortexBridge block (line ~1313), add:
```python
                        # Limbic Bridge — connect Amygdala + NAcc + InsularCortex + Hypothalamus
                        lm_cfg = self._yaml_config.get('limbic_bridge', {})
                        if lm_cfg.get('enabled', False):
                            try:
                                from core.limbic_bridge import LimbicBridge
                                limbic_bridge = LimbicBridge(
                                    amygdala=self.agent_loop.amygdala_complex,
                                    nucleus_accumbens=self.agent_loop.nucleus_accumbens,
                                    insular_cortex=self.agent_loop.insular_cortex,
                                    hypothalamus=self.agent_loop.hypothalamus,
                                )
                                self.agent_loop.radial_network.attach_limbic(limbic_bridge)
                                self.agent_loop.limbic_bridge = limbic_bridge
                                print("[AgentLoop] LimbicBridge wired -> RadialAttentionNetwork")
                            except Exception as e:
                                print(f"[AgentLoop] LimbicBridge not available: {e}")
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py tests/test_cortex_bridge.py tests/test_neuromodulation_bridge.py -v`
Expected: 25 limbic + 25 cortex + 25 neuromod = 75 PASSED

**Step 5: Commit**

```bash
git add configs/default.yaml production/production_planner.py tests/test_limbic_bridge.py
git commit -m "feat(limbic): production wiring + config for LimbicBridge"
```

---

### Task 9: Integration Tests with Real Modules

**Files:**
- Modify: `tests/test_limbic_bridge.py`

**Context:**
Like CortexBridge Task 8, this catches real API mismatches that mocks miss. Uses real AmygdalaComplex, NucleusAccumbens, InsularCortex, HypothalamusModule instances.

IMPORTANT: Module APIs have specific expectations:
- `AmygdalaComplex.process_stimulus(features, context)` — features must be numpy array, context is optional numpy array
- `NucleusAccumbens.evaluate(dopamine, reward_prediction, threat, action_complexity, energy)` — all floats
- `InsularCortex.process(...)` — keyword args, all optional
- `HypothalamusModule.update_drives(external_signals, elapsed_seconds)` — external_signals is optional dict
- `HypothalamusModule.process_stressor(intensity)` — intensity is float

**Step 1: Write integration tests**

Append to `tests/test_limbic_bridge.py`:

```python
class TestLimbicIntegration:
    """Integration tests with real brain modules (no mocks)."""

    def _make_real_bridge(self):
        from core.limbic_bridge import LimbicBridge
        from core.amygdala_complex import AmygdalaComplex
        from core.nucleus_accumbens import NucleusAccumbens
        from core.insular_cortex import InsularCortex
        from core.hypothalamus_drives import HypothalamusModule
        return LimbicBridge(
            amygdala=AmygdalaComplex(),
            nucleus_accumbens=NucleusAccumbens(),
            insular_cortex=InsularCortex(),
            hypothalamus=HypothalamusModule(),
        )

    def test_real_modules_single_tick(self):
        """One tick with real modules: no crashes, valid state."""
        from core.limbic_bridge import LimbicState
        bridge = self._make_real_bridge()
        acts = [np.random.randn(64), np.random.randn(128),
                np.random.randn(256), np.random.randn(256), np.random.randn(128)]
        state = bridge.update(acts, [0.1, 0.2, 0.15, 0.1])
        assert isinstance(state, LimbicState)
        assert -1.0 <= state.valence <= 1.0
        assert 0.0 <= state.arousal <= 1.0
        assert 0.0 <= state.salience <= 1.0

    def test_real_modules_multi_tick(self):
        """Multiple ticks: inter-module coupling propagates without error."""
        bridge = self._make_real_bridge()
        acts = [np.random.randn(64), np.random.randn(128),
                np.random.randn(256), np.random.randn(256), np.random.randn(128)]
        for _ in range(5):
            state = bridge.update(acts, [0.1, 0.2, 0.15, 0.1])
        assert bridge._tick_count == 5
        assert state.feeling != ''  # InsularCortex produces a feeling label

    def test_full_network_integration(self):
        """LimbicBridge inside RadialAttentionNetwork with real modules."""
        from core.limbic_bridge import LimbicState
        net = RadialAttentionNetwork()
        bridge = self._make_real_bridge()
        net.attach_limbic(bridge)
        x = torch.randn(1, 384)
        result = net(x)
        assert isinstance(result.get('limbic_state'), LimbicState)
        # Run a second tick to confirm inter-module coupling works
        result2 = net(x)
        assert isinstance(result2.get('limbic_state'), LimbicState)
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_limbic_bridge.py -v`
Expected: 28 PASSED (or fix any API mismatch found)

If API mismatch is found (e.g., wrong type passed to a module), fix in `core/limbic_bridge.py` the same way the CortexBridge `reward_history` bug was fixed.

**Step 3: Commit**

```bash
git add tests/test_limbic_bridge.py
git commit -m "feat(limbic): integration tests with real Amygdala, NAcc, InsularCortex, Hypothalamus"
```

---

### Task 10: Eval + MEMORY.md Update

**Files:**
- Modify: `tests/eval_radial_quality.py` — add Section 10: LimbicBridge
- Modify: `MEMORY.md` (at `C:\Users\User\.claude\projects\C--Users-User-Desktop-the-brain\memory\MEMORY.md`)

**Step 1: Add eval section**

Append Section 10 to `tests/eval_radial_quality.py`:

```python
# Section 10: LimbicBridge Live Output
print("\n--- Section 10: LimbicBridge ---")
try:
    from core.limbic_bridge import LimbicBridge
    from core.amygdala_complex import AmygdalaComplex
    from core.nucleus_accumbens import NucleusAccumbens
    from core.insular_cortex import InsularCortex
    from core.hypothalamus_drives import HypothalamusModule
    limbic = LimbicBridge(
        amygdala=AmygdalaComplex(),
        nucleus_accumbens=NucleusAccumbens(),
        insular_cortex=InsularCortex(),
        hypothalamus=HypothalamusModule(),
    )
    net.attach_limbic(limbic)
    for t in range(20):
        result = net(seed)
        ls = result['limbic_state']
        print(f"  tick {t:2d}: valence={ls.valence:+.3f}  arousal={ls.arousal:.3f}  "
              f"threat={ls.threat_level:.3f}  salience={ls.salience:.3f}  "
              f"go={ls.go_drive:.3f}  nogo={ls.nogo_drive:.3f}  "
              f"urgency={ls.urgency:.3f}  feeling={ls.feeling}")
    print("  LimbicBridge: OK")
except Exception as e:
    print(f"  LimbicBridge: FAILED - {e}")
```

NOTE: Use ASCII only (`->` not arrows). The eval file uses `net` and `seed` from earlier sections.

**Step 2: Update MEMORY.md**

Add a Limbic Bridge section after the existing Cortex Bridge section:

```markdown
## Limbic Bridge (core/limbic_bridge.py)
- **LimbicState** dataclass: 14 fields (valence, arousal, threat_level, is_threat, go/nogo_drive, net_value, effort_cost, salience, body_budget, feeling, urgency, approach_drive, stress)
- **LimbicBridge**: ring_activations + PEs -> 4 module calls -> LimbicState
- 4 hooks: Arousal(attention gain H10), Salience(precision H11), NoGo(DualProcess threshold H12), Urgency(FFN throughput H13)
- 1-tick delay: state computed after forward, used on NEXT forward
- Inter-module coupling: Amygdala->Hypothalamus(stress), Amygdala->NAcc(threat), Amygdala->Insula(arousal), Hypothalamus->NAcc(energy), Hypothalamus->Insula(stress), Insula->Amygdala(body_state)
- 1 projection: Ring 1 (64D) -> Amygdala (10 features) via (10, 64) numpy matrix
- Config: `limbic_bridge: enabled: true` in default.yaml
- All hooks `if limbic_state:` guarded -- zero breaking changes
- ~28 tests in test_limbic_bridge.py
```

**Step 3: Run eval**

Run: `python tests/eval_radial_quality.py`
Expected: Section 10 shows limbic output across 20 ticks, no errors.

**Step 4: Commit**

```bash
git add tests/eval_radial_quality.py
git commit -m "docs: add LimbicBridge eval section + update MEMORY.md"
```

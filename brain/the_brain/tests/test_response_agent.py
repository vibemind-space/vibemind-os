"""
Tests for core/response_agent.py -- ResponseAgent reads cortical area activations
and produces structured deliberation output.

Covers:
  - select_active_areas: threshold filtering, descending sort, top_k cap
  - gather_thoughts: collects from selected areas, tags with name/activation
  - deliberate: full cycle with all required keys
  - deliberate: records to KotlinGraph memory when attached
  - deliberate: empty / inactive areas yield zero confidence
  - get_state: returns expected keys and values
  - multiple deliberations increment counter
  - no areas above threshold returns empty selection
"""

import numpy as np
import pytest
from typing import List

from core.cortical_area import CorticalArea, CorticalAreaConfig
from core.kotlin_graph import KotlinGraph
from core.response_agent import ResponseAgent, ResponseAgentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_area(name: str, specialty: List[str] | None = None, layer_dim: int = 8) -> CorticalArea:
    """Create a CorticalArea with a given name and specialty list."""
    return CorticalArea(CorticalAreaConfig(
        name=name,
        specialty=specialty or [],
        layer_dim=layer_dim,
    ))


def activate_area(area: CorticalArea, magnitude: float = 1.0, n_pulses: int = 5) -> None:
    """
    Drive an area's activation up by feeding it random inputs.

    By sending several pulses with ``magnitude``-scaled random vectors,
    the EMA inside CorticalArea (0.7 * old + 0.3 * new_mag) ramps up.
    Larger ``magnitude`` and more ``n_pulses`` produces higher activation.
    """
    dim = area.config.layer_dim
    for _ in range(n_pulses):
        vec = np.random.randn(dim) * magnitude
        area.receive_input(vec)


def make_activated_areas(n: int = 5, base_magnitude: float = 0.5) -> List[CorticalArea]:
    """
    Create n areas with differing activation levels.

    Area 0 gets the weakest signal, area n-1 gets the strongest.
    """
    names = ["area_a", "area_b", "area_c", "area_d", "area_e",
             "area_f", "area_g", "area_h"]
    areas = []
    for i in range(n):
        area = make_area(names[i], specialty=[f"spec_{i}"])
        # Scale magnitude so later areas are more activated
        activate_area(area, magnitude=base_magnitude * (i + 1), n_pulses=4)
        areas.append(area)
    return areas


# ===================================================================
# select_active_areas
# ===================================================================

class TestSelectActiveAreas:

    def test_filters_below_threshold(self):
        """Areas with activation < min_activation are excluded."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=5, min_activation=0.5))
        areas = make_activated_areas(5, base_magnitude=0.3)

        selected = agent.select_active_areas(areas)
        for area in selected:
            assert area.activation >= 0.5, (
                f"{area.name} activation {area.activation} below threshold 0.5"
            )

    def test_sorted_descending(self):
        """Selected areas are sorted by activation descending."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=10, min_activation=0.0))
        areas = make_activated_areas(5, base_magnitude=0.5)

        selected = agent.select_active_areas(areas)
        activations = [a.activation for a in selected]
        assert activations == sorted(activations, reverse=True)

    def test_top_k_cap(self):
        """At most top_k areas are returned."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=2, min_activation=0.0))
        areas = make_activated_areas(5, base_magnitude=0.5)

        selected = agent.select_active_areas(areas)
        assert len(selected) <= 2

    def test_empty_areas(self):
        """Empty list yields empty selection."""
        agent = ResponseAgent()
        assert agent.select_active_areas([]) == []

    def test_no_areas_above_threshold(self):
        """All areas below threshold yields empty selection."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=3, min_activation=999.0))
        areas = make_activated_areas(3, base_magnitude=0.5)

        selected = agent.select_active_areas(areas)
        assert selected == []

    def test_all_inactive_areas(self):
        """Areas with zero activation are excluded when min_activation > 0."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=3, min_activation=0.01))
        areas = [make_area("idle_a"), make_area("idle_b"), make_area("idle_c")]
        # These areas have activation 0.0 (no input received)

        selected = agent.select_active_areas(areas)
        assert selected == []


# ===================================================================
# gather_thoughts
# ===================================================================

class TestGatherThoughts:

    def test_collects_from_multiple_areas(self):
        """Thoughts are collected from every supplied area."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent()

        thoughts = agent.gather_thoughts(areas)
        # Each area received 4 pulses, so 4 thoughts each
        assert len(thoughts) >= 3  # at least one per area

        area_names_in_thoughts = {t['area_name'] for t in thoughts}
        expected_names = {a.name for a in areas}
        assert area_names_in_thoughts == expected_names

    def test_thoughts_tagged_with_name_and_activation(self):
        """Each thought dict has area_name and area_activation keys."""
        area = make_area("language", specialty=["lang"])
        activate_area(area, magnitude=1.0, n_pulses=3)
        agent = ResponseAgent()

        thoughts = agent.gather_thoughts([area])
        assert len(thoughts) > 0
        for t in thoughts:
            assert 'area_name' in t
            assert 'area_activation' in t
            assert t['area_name'] == "language"
            assert isinstance(t['area_activation'], float)

    def test_empty_areas_no_thoughts(self):
        """Areas with no thoughts produce empty list."""
        area = make_area("empty")
        # No input received, so no thoughts
        agent = ResponseAgent()

        thoughts = agent.gather_thoughts([area])
        assert thoughts == []

    def test_gather_preserves_thought_keys(self):
        """Original thought keys (output, prediction, error_magnitude, activation) are preserved."""
        area = make_area("reasoning")
        activate_area(area, magnitude=0.5, n_pulses=2)
        agent = ResponseAgent()

        thoughts = agent.gather_thoughts([area])
        assert len(thoughts) > 0
        for t in thoughts:
            assert 'output' in t
            assert 'prediction' in t
            assert 'error_magnitude' in t
            assert 'activation' in t


# ===================================================================
# deliberate
# ===================================================================

class TestDeliberate:

    def test_returns_all_required_keys(self):
        """deliberate() result has all five required top-level keys."""
        areas = make_activated_areas(4, base_magnitude=0.5)
        agent = ResponseAgent()

        result = agent.deliberate(areas)
        assert "summary" in result
        assert "selected_areas" in result
        assert "confidence" in result
        assert "thought_count" in result
        assert "area_activations" in result

    def test_selected_areas_is_name_list(self):
        """selected_areas is a list of strings (area names)."""
        areas = make_activated_areas(4, base_magnitude=0.5)
        agent = ResponseAgent(ResponseAgentConfig(top_k=2))

        result = agent.deliberate(areas)
        assert isinstance(result['selected_areas'], list)
        assert len(result['selected_areas']) <= 2
        for name in result['selected_areas']:
            assert isinstance(name, str)

    def test_confidence_between_zero_and_one(self):
        """Confidence is in [0.0, 1.0]."""
        areas = make_activated_areas(5, base_magnitude=0.8)
        agent = ResponseAgent()

        result = agent.deliberate(areas)
        assert 0.0 <= result['confidence'] <= 1.0

    def test_confidence_zero_when_no_active_areas(self):
        """Confidence is 0.0 when no areas are above threshold."""
        areas = [make_area("idle")]
        agent = ResponseAgent(ResponseAgentConfig(min_activation=0.5))

        result = agent.deliberate(areas)
        assert result['confidence'] == 0.0
        assert result['selected_areas'] == []
        assert result['thought_count'] == 0

    def test_confidence_with_empty_area_list(self):
        """Deliberating over an empty list produces zero confidence."""
        agent = ResponseAgent()
        result = agent.deliberate([])
        assert result['confidence'] == 0.0
        assert result['selected_areas'] == []

    def test_confidence_boost_from_spread(self):
        """When multiple areas are selected, std deviation boosts confidence."""
        # Create two areas with noticeably different activations
        area_high = make_area("high", specialty=["h"])
        area_low = make_area("low", specialty=["l"])
        activate_area(area_high, magnitude=3.0, n_pulses=10)
        activate_area(area_low, magnitude=0.5, n_pulses=10)

        agent = ResponseAgent(ResponseAgentConfig(top_k=5, min_activation=0.0))

        result = agent.deliberate([area_high, area_low])
        mean_act = float(np.mean([area_high.activation, area_low.activation]))
        # confidence should be >= mean because spread adds a boost
        assert result['confidence'] >= mean_act or abs(result['confidence'] - mean_act) < 1e-6

    def test_summary_entries_have_required_keys(self):
        """Each summary entry has name, activation, specialty, avg_prediction_error."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent()

        result = agent.deliberate(areas)
        for entry in result['summary']:
            assert 'name' in entry
            assert 'activation' in entry
            assert 'specialty' in entry
            assert 'avg_prediction_error' in entry
            assert isinstance(entry['specialty'], list)
            assert isinstance(entry['avg_prediction_error'], float)

    def test_area_activations_contains_all_areas(self):
        """area_activations map includes every input area, not just selected ones."""
        areas = make_activated_areas(5, base_magnitude=0.5)
        agent = ResponseAgent(ResponseAgentConfig(top_k=2))

        result = agent.deliberate(areas)
        assert len(result['area_activations']) == 5
        for area in areas:
            assert area.name in result['area_activations']

    def test_thought_count_matches(self):
        """thought_count equals the total number of gathered thoughts."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent(ResponseAgentConfig(top_k=10, min_activation=0.0))

        result = agent.deliberate(areas)
        # Each area got 4 pulses => 4 thoughts, gather_thoughts takes last 5 => 4 each
        # 3 areas * 4 thoughts = 12
        assert result['thought_count'] > 0


# ===================================================================
# Memory recording
# ===================================================================

class TestMemoryRecording:

    def test_records_to_kotlin_graph(self):
        """When memory is set, deliberate() records an event to KotlinGraph."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent(ResponseAgentConfig(top_k=2, min_activation=0.0))
        agent.memory = KotlinGraph()

        result = agent.deliberate(areas)

        stats = agent.memory.get_statistics()
        assert stats['total_events'] == 1
        assert stats['total_episodes'] == 1  # done=True increments episode

        # Verify the recorded event's structure
        event = agent.memory.get_event(0)
        assert 'areas' in event.state
        assert 'activations' in event.state
        assert event.action.startswith("deliberate_from_")
        assert event.next_state['confidence'] == result['confidence']
        assert event.next_state['thought_count'] == result['thought_count']
        assert event.reward == result['confidence']
        assert event.done is True
        assert event.consciousness == result['confidence']

    def test_no_recording_without_memory(self):
        """Without memory set, deliberate() does not error."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent()
        assert agent.memory is None

        result = agent.deliberate(areas)
        assert result['confidence'] > 0  # still works

    def test_no_recording_when_no_active_areas(self):
        """If no areas are selected, no event is recorded even if memory is set."""
        agent = ResponseAgent(ResponseAgentConfig(min_activation=999.0))
        agent.memory = KotlinGraph()

        areas = make_activated_areas(2, base_magnitude=0.5)
        agent.deliberate(areas)

        stats = agent.memory.get_statistics()
        assert stats['total_events'] == 0

    def test_multiple_deliberations_record_multiple_events(self):
        """Each deliberation adds a new event to KotlinGraph."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent(ResponseAgentConfig(top_k=2, min_activation=0.0))
        agent.memory = KotlinGraph()

        agent.deliberate(areas)
        agent.deliberate(areas)
        agent.deliberate(areas)

        stats = agent.memory.get_statistics()
        assert stats['total_events'] == 3


# ===================================================================
# get_state
# ===================================================================

class TestGetState:

    def test_returns_expected_keys(self):
        """get_state() has total_deliberations, top_k, min_activation, has_memory."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=5, min_activation=0.1))
        state = agent.get_state()

        assert 'total_deliberations' in state
        assert 'top_k' in state
        assert 'min_activation' in state
        assert 'has_memory' in state

    def test_initial_state(self):
        """Fresh agent has zero deliberations and no memory."""
        agent = ResponseAgent()
        state = agent.get_state()

        assert state['total_deliberations'] == 0
        assert state['has_memory'] is False

    def test_state_reflects_config(self):
        """get_state reflects the config values."""
        agent = ResponseAgent(ResponseAgentConfig(top_k=7, min_activation=0.42))
        state = agent.get_state()

        assert state['top_k'] == 7
        assert state['min_activation'] == 0.42

    def test_has_memory_true_after_attach(self):
        """has_memory becomes True when KotlinGraph is attached."""
        agent = ResponseAgent()
        assert agent.get_state()['has_memory'] is False

        agent.memory = KotlinGraph()
        assert agent.get_state()['has_memory'] is True

    def test_deliberation_counter_increments(self):
        """total_deliberations increments with each deliberate() call."""
        areas = make_activated_areas(3, base_magnitude=0.5)
        agent = ResponseAgent()

        assert agent.get_state()['total_deliberations'] == 0
        agent.deliberate(areas)
        assert agent.get_state()['total_deliberations'] == 1
        agent.deliberate(areas)
        assert agent.get_state()['total_deliberations'] == 2


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:

    def test_single_area_no_spread_boost(self):
        """With a single selected area, confidence == that area's activation (no spread)."""
        area = make_area("solo", specialty=["s"])
        activate_area(area, magnitude=2.0, n_pulses=8)

        agent = ResponseAgent(ResponseAgentConfig(top_k=1, min_activation=0.0))
        result = agent.deliberate([area])

        assert len(result['selected_areas']) == 1
        # With one area, confidence == mean == that area's activation
        assert abs(result['confidence'] - area.activation) < 1e-6

    def test_all_areas_same_activation(self):
        """When all areas have identical activation, spread is ~0 so confidence == mean."""
        areas = [make_area(f"same_{i}") for i in range(3)]
        for area in areas:
            activate_area(area, magnitude=1.0, n_pulses=20)

        # Activations should be very close to each other now
        agent = ResponseAgent(ResponseAgentConfig(top_k=3, min_activation=0.0))
        result = agent.deliberate(areas)

        acts = [a.activation for a in areas]
        mean_act = float(np.mean(acts))
        # Confidence should be very close to mean (spread ~ 0)
        assert abs(result['confidence'] - mean_act) < 0.1

    def test_deliberate_with_mixed_inactive_active(self):
        """Inactive areas are filtered out; only active ones contribute."""
        active = make_area("active", specialty=["x"])
        activate_area(active, magnitude=2.0, n_pulses=8)

        inactive = make_area("inactive", specialty=["y"])
        # inactive has activation == 0.0

        agent = ResponseAgent(ResponseAgentConfig(top_k=5, min_activation=0.01))
        result = agent.deliberate([active, inactive])

        assert result['selected_areas'] == ["active"]
        assert "inactive" not in result['selected_areas']
        # area_activations should still have both
        assert "active" in result['area_activations']
        assert "inactive" in result['area_activations']

    def test_top_k_less_than_available_above_threshold(self):
        """If more areas pass threshold than top_k, only top_k are returned."""
        areas = make_activated_areas(5, base_magnitude=1.0)
        # All 5 should have activation > 0.01
        agent = ResponseAgent(ResponseAgentConfig(top_k=2, min_activation=0.0))

        result = agent.deliberate(areas)
        assert len(result['selected_areas']) == 2
        assert len(result['summary']) == 2

    def test_default_config(self):
        """Default config is top_k=3, min_activation=0.01."""
        agent = ResponseAgent()
        assert agent.config.top_k == 3
        assert agent.config.min_activation == 0.01

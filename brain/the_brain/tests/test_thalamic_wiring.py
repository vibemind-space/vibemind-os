"""Tests for production wiring of thalamic components."""
import sys
import os
import pytest
from unittest.mock import MagicMock

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.thalamic_adapter import ThalamicAdapter
from core.cortical_area import CorticalArea, CorticalAreaConfig
from core.response_agent import ResponseAgent, ResponseAgentConfig
from core.dual_graph import DualGraph
from core.kotlin_graph import KotlinGraph
import numpy as np


class TestEndToEndWiring:
    """Test the full pipeline: input -> thalamus -> areas -> response agent."""

    def test_full_pipeline(self):
        """End-to-end: message -> ThalamoPC6 -> areas -> ResponseAgent -> result."""
        # 1. Create components
        adapter = ThalamicAdapter()
        memory = KotlinGraph()
        areas = [
            CorticalArea(CorticalAreaConfig(name="language", specialty=["lc"])),
            CorticalArea(CorticalAreaConfig(name="reasoning", specialty=["pfc"])),
            CorticalArea(CorticalAreaConfig(name="memory", specialty=["ec"])),
        ]
        agent = ResponseAgent(ResponseAgentConfig(top_k=2))
        agent.memory = memory

        # 2. Process through thalamus
        result = adapter.process("chat", {"message": "What is consciousness?"})

        # 3. Route to areas (weighted by gates)
        layer_dim = 8
        for area in areas:
            thalamic_vec = np.random.randn(layer_dim) * result['gates'].get('audio', 0.1)
            area.receive_input(thalamic_vec)

        # 4. Response agent deliberates
        deliberation = agent.deliberate(areas)

        assert deliberation['confidence'] > 0.0
        assert len(deliberation['selected_areas']) > 0
        assert memory.stats['total_events'] >= 1

    def test_areas_activate_differently(self):
        """Different areas activate to different levels based on input."""
        adapter = ThalamicAdapter()
        areas = [
            CorticalArea(CorticalAreaConfig(name="language")),
            CorticalArea(CorticalAreaConfig(name="executive")),
        ]

        result = adapter.process("chat", {"message": "hello"})

        # Give language area stronger input
        areas[0].receive_input(np.ones(8) * 2.0)
        areas[1].receive_input(np.ones(8) * 0.1)

        assert areas[0].activation > areas[1].activation

    def test_memory_records_across_interactions(self):
        """KotlinGraph accumulates events across interactions."""
        memory = KotlinGraph()
        agent = ResponseAgent()
        agent.memory = memory

        areas = [CorticalArea(CorticalAreaConfig(name="lang"))]

        for i in range(5):
            areas[0].receive_input(np.random.randn(8))
            agent.deliberate(areas)

        assert memory.stats['total_events'] == 5

    def test_dual_graph_records_events(self):
        """DualGraph record_event works in the pipeline."""
        dual = DualGraph()
        adapter = ThalamicAdapter()

        result = adapter.process("chat", {"message": "test"})

        event_id = dual.record_event(
            state={"gates": result["gates"]},
            action="chat_response",
            next_state={"active": result["active_modalities"]},
            reward=0.5,
            done=True,
        )

        assert event_id == 0
        assert dual.stats['total_events_recorded'] == 1

    def test_thalamic_adapter_creates_gates(self):
        """ThalamicAdapter.process returns valid gate dict."""
        adapter = ThalamicAdapter()
        result = adapter.process("chat", {"message": "hello world"})

        assert "gates" in result
        assert "routed_output" in result
        assert "active_modalities" in result
        assert "prediction_errors" in result
        assert "thalamic_state" in result
        assert "time_step" in result

        # Gates should sum to ~1.0
        gate_sum = sum(result["gates"].values())
        assert abs(gate_sum - 1.0) < 0.01

    def test_cortical_area_state(self):
        """CorticalArea.get_state() returns expected shape."""
        area = CorticalArea(CorticalAreaConfig(
            name="test_area",
            specialty=["pfc", "acc"],
        ))
        area.receive_input(np.random.randn(8))

        state = area.get_state()
        assert state['name'] == "test_area"
        assert state['activation'] > 0.0
        assert state['specialty'] == ["pfc", "acc"]
        assert state['thought_count'] == 1

    def test_response_agent_no_memory(self):
        """ResponseAgent works without KotlinGraph attached."""
        agent = ResponseAgent()
        assert agent.memory is None

        areas = [CorticalArea(CorticalAreaConfig(name="a"))]
        areas[0].receive_input(np.ones(8))

        result = agent.deliberate(areas)
        assert result['confidence'] > 0.0
        assert result['selected_areas'] == ["a"]

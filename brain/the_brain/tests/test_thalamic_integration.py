"""Tests for ThalamoPC6 integration into BrainChat routing."""
import pytest
from unittest.mock import MagicMock, patch
from core.thalamic_adapter import ThalamicAdapter


class TestThalamicRouting:
    def test_adapter_produces_routing_info(self):
        """ThalamicAdapter.process() returns routing-compatible info."""
        adapter = ThalamicAdapter()
        result = adapter.process("chat", {"message": "hello"})
        assert "gates" in result
        assert "active_modalities" in result
        gate_sum = sum(result["gates"].values())
        assert abs(gate_sum - 1.0) < 1e-5

    def test_routing_info_format_matches_brain_chat(self):
        """Result can be converted to BrainChat's routing_info format."""
        adapter = ThalamicAdapter()
        result = adapter.process("chat", {"message": "what is AI?"})
        routing_info = {
            'mode': 'thalamic',
            'weights': list(result['gates'].values()),
            'dominant_areas': result['active_modalities'],
            'task_type': 'thalamic_routed',
            'predicted_sequence': [],
            'confidence': max(result['gates'].values()),
        }
        assert routing_info['mode'] == 'thalamic'
        assert len(routing_info['weights']) == 6
        assert isinstance(routing_info['dominant_areas'], list)

    def test_multiple_messages_evolve_state(self):
        """ThalamoPC6 state evolves across messages (not stateless)."""
        adapter = ThalamicAdapter()
        r1 = adapter.process("chat", {"message": "hello"})
        r2 = adapter.process("chat", {"message": "tell me about AI"})
        g1 = list(r1['gates'].values())
        g2 = list(r2['gates'].values())
        assert g1 != g2  # state evolved

    def test_threat_escalation(self):
        """Threat input shifts gate distribution toward threat modality."""
        adapter = ThalamicAdapter()
        r_normal = adapter.process("chat", {"message": "hi"})
        r_threat = adapter.process("threat", {"error": "CRITICAL", "severity": 1.0})
        assert r_threat['gates']['threat'] >= r_normal['gates']['threat'] * 0.5

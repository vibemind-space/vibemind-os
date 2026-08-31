"""
Tests for Minibook Integration (Phase 10, Tasks 6-9, 13).

Covers:
    - MinibookClient: registration, heartbeat, notification polling,
      reply posting, offline graceful degradation
    - MinibookNotification: social signal conversion
    - MinibookSensor: poll cycle, event generation, rate limiting
    - SocialPerceptionBridge: external_signals blending
"""

import time
import pytest
import numpy as np

from core.minibook_client import MinibookClient, MinibookNotification
from core.sensor_systems import MinibookSensor, SensorEvent
from core.social_perception_bridge import SocialPerceptionBridge, SocialPerceptionState
from core.mcp_server import MCPServer


# ===========================================================================
# MinibookNotification Tests
# ===========================================================================

class TestMinibookNotification:
    def test_default_values(self):
        n = MinibookNotification()
        assert n.notification_type == 'mention'
        assert n.is_read is False
        assert n.content == ''

    def test_to_social_signals_mention(self):
        n = MinibookNotification(
            notification_type='mention',
            content='Hey @Tahlamus, what do you think?',
        )
        signals = n.to_social_signals()
        assert signals['social_salience'] == 0.8
        assert signals['agency_signal'] == 1.0
        assert 0.0 <= signals['content_novelty'] <= 1.0
        assert signals['sender_familiarity'] == 0.5

    def test_to_social_signals_reply(self):
        n = MinibookNotification(notification_type='reply')
        signals = n.to_social_signals()
        assert signals['social_salience'] == 0.6
        assert signals['agency_signal'] == 0.5

    def test_to_social_signals_thread_update(self):
        n = MinibookNotification(notification_type='thread_update')
        signals = n.to_social_signals()
        assert signals['social_salience'] == 0.4

    def test_to_social_signals_system(self):
        n = MinibookNotification(notification_type='system')
        signals = n.to_social_signals()
        assert signals['social_salience'] == 0.2

    def test_content_novelty_scales_with_length(self):
        short = MinibookNotification(content='Hi')
        long = MinibookNotification(content='x' * 500)
        assert short.to_social_signals()['content_novelty'] < long.to_social_signals()['content_novelty']

    def test_content_novelty_capped_at_1(self):
        huge = MinibookNotification(content='x' * 10000)
        assert huge.to_social_signals()['content_novelty'] == 1.0


# ===========================================================================
# MinibookClient Tests (offline/stub mode — no server needed)
# ===========================================================================

class TestMinibookClientOffline:
    def test_default_state(self):
        c = MinibookClient()
        assert c.is_online is False
        assert c.is_registered is False
        assert c.agent_id is None

    def test_register_fails_gracefully_offline(self):
        c = MinibookClient(base_url='http://localhost:99999')
        result = c.register()
        assert result is False
        assert c.is_online is False

    def test_heartbeat_returns_false_when_not_registered(self):
        c = MinibookClient()
        assert c.heartbeat() is False

    def test_check_notifications_returns_empty_offline(self):
        c = MinibookClient(base_url='http://localhost:99999')
        notifs = c.check_notifications()
        assert notifs == []

    def test_post_reply_returns_false_offline(self):
        c = MinibookClient(base_url='http://localhost:99999')
        assert c.post_reply('post-123', 'hello') is False

    def test_create_post_returns_none_offline(self):
        c = MinibookClient(base_url='http://localhost:99999')
        assert c.create_post('proj-1', 'Title', 'Body') is None

    def test_mark_read_returns_false_offline(self):
        c = MinibookClient(base_url='http://localhost:99999')
        assert c.mark_read('notif-1') is False

    def test_get_status(self):
        c = MinibookClient(agent_name='TestBrain')
        status = c.get_status()
        assert status['agent_name'] == 'TestBrain'
        assert status['online'] is False
        assert status['registered'] is False
        assert 'cached_notifications' in status

    def test_notifications_to_social_signals_empty(self):
        c = MinibookClient()
        signals = c.notifications_to_social_signals()
        assert signals['social_salience'] == 0.0
        assert signals['agency_signal'] == 0.0

    def test_notifications_to_social_signals_with_data(self):
        c = MinibookClient()
        notifs = [
            MinibookNotification(
                notification_type='mention',
                sender_id='agent-1',
                content='Hey there!',
            ),
            MinibookNotification(
                notification_type='reply',
                sender_id='agent-2',
                content='Thanks for the update.',
            ),
        ]
        signals = c.notifications_to_social_signals(notifs)
        assert signals['social_salience'] == 0.8  # Max of mention(0.8), reply(0.6)
        assert signals['agency_signal'] == 1.0  # Max of mention(1.0), reply(0.5)

    def test_familiarity_tracking(self):
        c = MinibookClient()
        # Default familiarity for unknown sender
        assert c.get_sender_familiarity('unknown') == 0.3

    def test_headers_with_api_key(self):
        c = MinibookClient(api_key='secret-key-123')
        headers = c._headers()
        assert headers['Authorization'] == 'Bearer secret-key-123'

    def test_headers_without_api_key(self):
        c = MinibookClient(api_key='')
        headers = c._headers()
        assert 'Authorization' not in headers


# ===========================================================================
# MinibookSensor Tests
# ===========================================================================

class FakeMiniClient:
    """Fake MinibookClient for testing MinibookSensor."""

    def __init__(self, notifications=None):
        self._notifications = notifications or []
        self.is_online = True
        self.poll_count = 0

    def check_notifications(self, since=None, limit=50):
        self.poll_count += 1
        return self._notifications


class TestMinibookSensor:
    def test_stub_mode_no_client(self):
        sensor = MinibookSensor(minibook_client=None)
        events = sensor.read()
        assert events == []

    def test_reads_notifications(self):
        notifs = [
            MinibookNotification(
                notification_id='n1',
                notification_type='mention',
                sender_name='Agent-X',
                sender_id='ax',
                content='@Tahlamus check this out',
                timestamp=time.time(),
            ),
        ]
        client = FakeMiniClient(notifs)
        sensor = MinibookSensor(minibook_client=client, poll_interval=0)
        events = sensor.read()
        assert len(events) == 1
        assert events[0].source == 'minibook'
        assert events[0].modality == 'social_signal'
        assert events[0].data['notification_type'] == 'mention'
        assert events[0].data['sender_name'] == 'Agent-X'
        assert 'social_signals' in events[0].data

    def test_poll_interval_respected(self):
        client = FakeMiniClient([MinibookNotification(timestamp=time.time())])
        sensor = MinibookSensor(minibook_client=client, poll_interval=60.0)
        # First read should poll
        events1 = sensor.read()
        assert client.poll_count == 1
        # Second read within interval should NOT poll
        events2 = sensor.read()
        assert client.poll_count == 1  # Still 1

    def test_mention_has_high_priority(self):
        notifs = [
            MinibookNotification(
                notification_type='mention',
                timestamp=time.time(),
            ),
        ]
        client = FakeMiniClient(notifs)
        sensor = MinibookSensor(minibook_client=client, poll_interval=0)
        events = sensor.read()
        assert events[0].priority == 0.7
        assert events[0].severity == 'warning'

    def test_thread_update_has_low_priority(self):
        notifs = [
            MinibookNotification(
                notification_type='thread_update',
                timestamp=time.time(),
            ),
        ]
        client = FakeMiniClient(notifs)
        sensor = MinibookSensor(minibook_client=client, poll_interval=0)
        events = sensor.read()
        assert events[0].priority == 0.3
        assert events[0].severity == 'info'

    def test_get_state(self):
        sensor = MinibookSensor(minibook_client=None, poll_interval=30.0)
        state = sensor.get_state()
        assert state['name'] == 'MinibookSensor'
        assert state['has_client'] is False
        assert state['poll_interval'] == 30.0

    def test_from_yaml(self):
        config = {'minibook': {'poll_interval': 15.0}}
        sensor = MinibookSensor.from_yaml(config)
        assert sensor.poll_interval == 15.0

    def test_content_truncated(self):
        long_content = 'x' * 1000
        notifs = [
            MinibookNotification(
                notification_type='mention',
                content=long_content,
                timestamp=time.time(),
            ),
        ]
        client = FakeMiniClient(notifs)
        sensor = MinibookSensor(minibook_client=client, poll_interval=0)
        events = sensor.read()
        assert len(events[0].data['content']) == 500  # Truncated


# ===========================================================================
# SocialPerceptionBridge external_signals Tests
# ===========================================================================

class TestSocialPerceptionExternalSignals:
    def _make_ring_activations(self):
        return [
            np.zeros(64),
            np.zeros(128),
            np.zeros(256),
            np.zeros(256),
            np.zeros(128),
        ]

    def test_update_without_external_signals(self):
        """Existing behavior: no external_signals parameter."""
        bridge = SocialPerceptionBridge()
        state = bridge.update(
            self._make_ring_activations(),
            [0.1, 0.1, 0.1, 0.1],
        )
        assert isinstance(state, SocialPerceptionState)
        # Default values without modules or external signals
        assert state.social_salience == 0.0
        assert state.familiarity == 0.3  # Default olfactory

    def test_external_signals_boost_salience(self):
        bridge = SocialPerceptionBridge()
        ext = {
            'social_salience': 0.8,
            'sender_familiarity': 0.7,
            'agency_signal': 0.9,
            'content_novelty': 0.6,
        }
        state = bridge.update(
            self._make_ring_activations(),
            [0.1, 0.1, 0.1, 0.1],
            external_signals=ext,
        )
        assert state.social_salience >= 0.8
        assert state.familiarity >= 0.7
        assert state.agency_score >= 0.9

    def test_external_signals_agency_boosts_social_inference(self):
        bridge = SocialPerceptionBridge()
        ext = {
            'social_salience': 0.0,
            'sender_familiarity': 0.0,
            'agency_signal': 0.8,  # > 0.5 threshold
            'content_novelty': 0.0,
        }
        state = bridge.update(
            self._make_ring_activations(),
            [0.1],
            external_signals=ext,
        )
        # agency > 0.5 should boost social_inference
        assert state.social_inference >= 0.8 * 0.7  # ext_agency * 0.7

    def test_external_novelty_boosts_identity(self):
        bridge = SocialPerceptionBridge()
        ext = {
            'social_salience': 0.0,
            'sender_familiarity': 0.0,
            'agency_signal': 0.0,
            'content_novelty': 0.8,
        }
        state = bridge.update(
            self._make_ring_activations(),
            [0.1],
            external_signals=ext,
        )
        # identity_score = max(0, 0.8 * 0.5) = 0.4
        assert state.identity_score >= 0.4 - 0.01

    def test_none_external_signals_is_safe(self):
        """Passing None should behave like no external signals."""
        bridge = SocialPerceptionBridge()
        state = bridge.update(
            self._make_ring_activations(),
            [0.1],
            external_signals=None,
        )
        assert isinstance(state, SocialPerceptionState)

    def test_empty_external_signals_is_safe(self):
        """Passing empty dict should not crash."""
        bridge = SocialPerceptionBridge()
        state = bridge.update(
            self._make_ring_activations(),
            [0.1],
            external_signals={},
        )
        assert isinstance(state, SocialPerceptionState)


# ===========================================================================
# Integration: Minibook -> SocialPerception pipeline
# ===========================================================================

class TestMinibookSocialPipeline:
    """End-to-end: MinibookNotification -> social_signals -> SocialPerceptionBridge."""

    def test_notification_to_bridge_pipeline(self):
        # Step 1: Create notification (simulating Minibook @mention)
        notif = MinibookNotification(
            notification_type='mention',
            sender_name='Agent-Y',
            sender_id='ay-001',
            content='@Tahlamus can you review the integration plan?',
        )

        # Step 2: Convert to social signals
        signals = notif.to_social_signals()
        assert signals['social_salience'] == 0.8
        assert signals['agency_signal'] == 1.0

        # Step 3: Feed to SocialPerceptionBridge
        bridge = SocialPerceptionBridge()
        ring_acts = [np.zeros(d) for d in [64, 128, 256, 256, 128]]
        state = bridge.update(
            ring_acts,
            [0.1, 0.1],
            external_signals=signals,
        )

        # Step 4: Verify bridge state reflects social engagement
        assert state.social_salience >= 0.8
        assert state.agency_score >= 1.0
        # Theory-of-mind engagement boosted (agency > 0.5)
        assert state.social_inference > 0.0

    def test_aggregated_signals_pipeline(self):
        """Multiple notifications aggregated by MinibookClient."""
        client = MinibookClient()
        notifs = [
            MinibookNotification(
                notification_type='mention',
                sender_id='a1',
                content='Hey!',
            ),
            MinibookNotification(
                notification_type='reply',
                sender_id='a2',
                content='Great work on the analysis.',
            ),
        ]
        signals = client.notifications_to_social_signals(notifs)

        bridge = SocialPerceptionBridge()
        ring_acts = [np.zeros(d) for d in [64, 128, 256, 256, 128]]
        state = bridge.update(
            ring_acts,
            [0.1],
            external_signals=signals,
        )
        assert state.social_salience >= 0.8  # mention dominates
        assert state.agency_score >= 1.0


# ===========================================================================
# MCP Server + Minibook Status Integration
# ===========================================================================

class TestMCPMinibookIntegration:
    def test_mcp_serves_minibook_status(self):
        """MCP server correctly proxies Minibook client status."""
        client = MinibookClient(agent_name='TestBrain')

        server = MCPServer(
            brain_state_fn=lambda: {},
            minibook_status_fn=client.get_status,
        )

        import json
        resp = json.loads(server.handle_request(json.dumps({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'tools/call',
            'params': {'name': 'get_minibook_status', 'arguments': {}},
        })))

        data = json.loads(resp['result']['content'][0]['text'])
        assert data['agent_name'] == 'TestBrain'
        assert data['online'] is False  # Not connected

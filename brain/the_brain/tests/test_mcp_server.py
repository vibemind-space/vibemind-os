"""
Tests for MCP Server (Phase 10, Tasks 10-11).

Covers:
    - JSON-RPC 2.0 request/response format
    - Resource listing and reading
    - Tool listing and invocation
    - Error handling (parse error, unknown method, unknown tool)
    - Ping endpoint
    - Server stats
"""

import json
import pytest

from core.mcp_server import MCPServer, MCPResource, MCPTool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_brain_state():
    """Fake brain state for testing."""
    return {
        'consciousness_level': 0.75,
        'tick_count': 42,
        'attention_gain': 1.2,
        'precision_boost': 1.1,
        'ffn_throughput': 1.0,
        'threshold_mod': 0.95,
        'consciousness': {
            'consciousness_level': 0.75,
            'integration_score': 0.6,
        },
    }


def _make_bridge_state(name):
    """Fake bridge state for testing."""
    return {
        'bridge_name': name,
        'active': True,
        'value': 0.5,
    }


def _make_scenario(name, ticks):
    """Fake scenario runner."""
    return {
        'scenario': name,
        'ticks': ticks,
        'completed': True,
        'final_state': {'consciousness_level': 0.8},
    }


def _make_minibook_status():
    return {
        'online': True,
        'registered': True,
        'agent_id': 'test-agent-123',
    }


@pytest.fixture
def server():
    """Create a test MCP server with all callbacks."""
    return MCPServer(
        brain_state_fn=_make_brain_state,
        bridge_state_fn=_make_bridge_state,
        scenario_fn=_make_scenario,
        minibook_status_fn=_make_minibook_status,
        host='127.0.0.1',
        port=0,  # Don't actually bind
    )


@pytest.fixture
def server_no_scenario():
    """MCP server without scenario engine."""
    return MCPServer(
        brain_state_fn=_make_brain_state,
        bridge_state_fn=_make_bridge_state,
    )


def _rpc(method, params=None, req_id=1):
    """Build a JSON-RPC 2.0 request string."""
    request = {
        'jsonrpc': '2.0',
        'id': req_id,
        'method': method,
    }
    if params is not None:
        request['params'] = params
    return json.dumps(request)


def _parse_response(raw):
    """Parse JSON-RPC response."""
    resp = json.loads(raw)
    assert resp['jsonrpc'] == '2.0'
    return resp


# ===========================================================================
# Test: MCPResource and MCPTool dataclasses
# ===========================================================================

class TestDataclasses:
    def test_mcp_resource_defaults(self):
        r = MCPResource(uri='test://foo', name='Foo', description='A foo')
        assert r.mime_type == 'application/json'
        assert r.uri == 'test://foo'

    def test_mcp_tool_fields(self):
        t = MCPTool(
            name='test_tool',
            description='A test tool',
            input_schema={'type': 'object', 'properties': {}},
        )
        assert t.name == 'test_tool'
        assert 'type' in t.input_schema


# ===========================================================================
# Test: resources/list
# ===========================================================================

class TestResourcesList:
    def test_list_returns_5_resources(self, server):
        resp = _parse_response(server.handle_request(_rpc('resources/list')))
        assert 'result' in resp
        resources = resp['result']['resources']
        assert len(resources) == 5

    def test_resource_uris(self, server):
        resp = _parse_response(server.handle_request(_rpc('resources/list')))
        uris = {r['uri'] for r in resp['result']['resources']}
        assert 'brain://state' in uris
        assert 'brain://bridges' in uris
        assert 'brain://modulation' in uris
        assert 'brain://consciousness' in uris
        assert 'brain://minibook' in uris


# ===========================================================================
# Test: resources/read
# ===========================================================================

class TestResourcesRead:
    def test_read_brain_state(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('resources/read', {'uri': 'brain://state'})
        ))
        contents = resp['result']['contents']
        assert len(contents) == 1
        data = json.loads(contents[0]['text'])
        assert data['consciousness_level'] == 0.75
        assert data['tick_count'] == 42

    def test_read_bridges(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('resources/read', {'uri': 'brain://bridges'})
        ))
        data = json.loads(resp['result']['contents'][0]['text'])
        assert 'neuromod' in data
        assert 'cortex' in data
        assert 'social' in data
        assert data['neuromod']['bridge_name'] == 'neuromod'

    def test_read_modulation(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('resources/read', {'uri': 'brain://modulation'})
        ))
        data = json.loads(resp['result']['contents'][0]['text'])
        assert data['attention_gain'] == 1.2
        assert data['consciousness_level'] == 0.75

    def test_read_consciousness(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('resources/read', {'uri': 'brain://consciousness'})
        ))
        data = json.loads(resp['result']['contents'][0]['text'])
        assert data['consciousness_level'] == 0.75

    def test_read_minibook(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('resources/read', {'uri': 'brain://minibook'})
        ))
        data = json.loads(resp['result']['contents'][0]['text'])
        assert data['online'] is True
        assert data['agent_id'] == 'test-agent-123'

    def test_read_unknown_resource(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('resources/read', {'uri': 'brain://nonexistent'})
        ))
        assert 'error' in resp
        assert resp['error']['code'] == -32602


# ===========================================================================
# Test: tools/list
# ===========================================================================

class TestToolsList:
    def test_list_with_scenario(self, server):
        resp = _parse_response(server.handle_request(_rpc('tools/list')))
        tools = resp['result']['tools']
        names = {t['name'] for t in tools}
        assert 'think' in names
        assert 'get_bridge_state' in names
        assert 'get_minibook_status' in names
        assert 'run_scenario' in names
        assert len(tools) == 4

    def test_list_without_scenario(self, server_no_scenario):
        resp = _parse_response(server_no_scenario.handle_request(
            _rpc('tools/list')
        ))
        tools = resp['result']['tools']
        names = {t['name'] for t in tools}
        assert 'run_scenario' not in names
        assert len(tools) == 3


# ===========================================================================
# Test: tools/call
# ===========================================================================

class TestToolsCall:
    def test_think(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('tools/call', {
                'name': 'think',
                'arguments': {'prompt': 'Hello brain'},
            })
        ))
        content = resp['result']['content']
        data = json.loads(content[0]['text'])
        assert data['status'] == 'received'
        assert data['prompt'] == 'Hello brain'

    def test_get_bridge_state(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('tools/call', {
                'name': 'get_bridge_state',
                'arguments': {'name': 'limbic'},
            })
        ))
        data = json.loads(resp['result']['content'][0]['text'])
        assert data['bridge_name'] == 'limbic'

    def test_run_scenario(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('tools/call', {
                'name': 'run_scenario',
                'arguments': {'name': 'threat_while_sleepy', 'ticks': 50},
            })
        ))
        data = json.loads(resp['result']['content'][0]['text'])
        assert data['scenario'] == 'threat_while_sleepy'
        assert data['ticks'] == 50
        assert data['completed'] is True

    def test_get_minibook_status(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('tools/call', {
                'name': 'get_minibook_status',
                'arguments': {},
            })
        ))
        data = json.loads(resp['result']['content'][0]['text'])
        assert data['online'] is True

    def test_unknown_tool(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('tools/call', {
                'name': 'nonexistent_tool',
                'arguments': {},
            })
        ))
        assert 'error' in resp
        assert resp['error']['code'] == -32602


# ===========================================================================
# Test: Error handling
# ===========================================================================

class TestErrorHandling:
    def test_parse_error(self, server):
        resp = _parse_response(server.handle_request('not valid json!!!'))
        assert 'error' in resp
        assert resp['error']['code'] == -32700
        assert 'Parse error' in resp['error']['message']

    def test_unknown_method(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('nonexistent/method')
        ))
        assert 'error' in resp
        assert resp['error']['code'] == -32601

    def test_request_id_preserved(self, server):
        resp = _parse_response(server.handle_request(
            _rpc('ping', req_id=42)
        ))
        assert resp['id'] == 42


# ===========================================================================
# Test: Ping
# ===========================================================================

class TestPing:
    def test_ping_response(self, server):
        resp = _parse_response(server.handle_request(_rpc('ping')))
        result = resp['result']
        assert result['status'] == 'ok'
        assert 'uptime' in result
        assert 'requests_served' in result


# ===========================================================================
# Test: Server stats
# ===========================================================================

class TestServerStats:
    def test_stats_before_start(self, server):
        stats = server.get_stats()
        assert stats['running'] is False
        assert stats['resources'] == 5
        assert stats['tools'] == 4  # with scenario

    def test_stats_without_scenario(self, server_no_scenario):
        stats = server_no_scenario.get_stats()
        assert stats['tools'] == 3  # without scenario

    def test_request_count_increments(self, server):
        assert server._request_count == 0
        server.handle_request(_rpc('ping'))
        assert server._request_count == 1
        server.handle_request(_rpc('ping'))
        assert server._request_count == 2

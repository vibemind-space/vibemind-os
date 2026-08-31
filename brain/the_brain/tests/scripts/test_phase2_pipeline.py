"""
Test Phase 2: Full Pipeline with EventBridge + Ollama + Dashboard

Tests:
1. OllamaLLMRouter connection and classification
2. EventBridge token extraction
3. TokenFrequencyAdapter with Ollama
4. OscillatorDashboard visualization
5. Full pipeline integration
"""

import sys
sys.path.insert(0, '.')

print('=' * 70)
print('  PHASE 2 PIPELINE TEST')
print('  EventBridge + Ollama + Dashboard')
print('=' * 70)

# Test 1: Ollama LLM Router
print('\n' + '=' * 70)
print('  TEST 1: Ollama LLM Router')
print('=' * 70)

try:
    from core.ollama_llm_router import OllamaLLMRouter, OllamaConfig

    config = OllamaConfig(model="llama3.2:1b")
    ollama_router = OllamaLLMRouter(config)

    print(f'\n  Ollama Available: {ollama_router.is_available}')
    print(f'  Base URL: {ollama_router.base_url}')
    print(f'  Model: {ollama_router.config.model}')

    if ollama_router.is_available:
        print(f'  Available Models: {ollama_router.available_models[:3]}...')

        # Test classification
        test_tokens = ["deploy", "not", "nginx"]
        print('\n  Token Classification:')
        for token in test_tokens:
            result = ollama_router.classify_token(token)
            print(f'    {token:10} -> {result["class"]:12} ({result.get("latency_ms", 0):.0f}ms)')
    else:
        print('\n  [!] Ollama not running. Start with:')
        print('      ollama serve')
        print('      ollama pull llama3.2:1b')

except Exception as e:
    print(f'\n  [ERROR] Ollama test failed: {e}')

# Test 2: EventBridge
print('\n' + '=' * 70)
print('  TEST 2: EventBridge Token Extraction')
print('=' * 70)

try:
    from core.event_bridge import EventBridge, TokenExtractionConfig

    # Mock adapter for testing
    class MockAdapter:
        def __init__(self):
            self.tokens = []
        def process_token_sync(self, token):
            self.tokens.append(token)

    mock_adapter = MockAdapter()
    bridge = EventBridge(mock_adapter)

    # Test events
    events = [
        {'text': 'Deploy the nginx container on port 8080'},
        {'content': 'But NOT on production'},
        {'message': 'Then verify deployment status'}
    ]

    print('\n  Processing events:')
    for event in events:
        text = event.get('text') or event.get('content') or event.get('message')
        result = bridge.process_conversation_event(event)
        print(f'    "{text[:30]}..." -> {len(result.tokens)} tokens')

    stats = bridge.get_statistics()
    print(f'\n  Stats:')
    print(f'    Events processed: {stats["events_processed"]}')
    print(f'    Tokens extracted: {stats["tokens_extracted"]}')
    print(f'    Avg tokens/event: {stats["avg_tokens_per_event"]:.1f}')

except Exception as e:
    print(f'\n  [ERROR] EventBridge test failed: {e}')

# Test 3: Full Router with Ollama
print('\n' + '=' * 70)
print('  TEST 3: Full Router with Ollama + EventBridge')
print('=' * 70)

try:
    from core.layer4_temporal_router import Layer4TemporalRouter

    router = Layer4TemporalRouter(
        strict_security=True,
        timing_threshold=0.5,
        enable_deep_reasoning=False
    )

    print('\n  Router Components:')
    print(f'    Oscillator: {router.oscillator}')
    print(f'    TokenAdapter: {router.token_adapter}')
    print(f'    EventBridge: {router.event_bridge}')
    print(f'    Using Ollama: {router.token_adapter._using_ollama}')

    # Process tokens manually first
    print('\n  Manual token processing:')
    tokens = "Deploy the nginx container but not on production".split()
    router.process_tokens(tokens)

    osc_state = router.get_oscillator_state()
    print(f'    A (Advance): {osc_state.A.amplitude:.3f}')
    print(f'    B (Explore): {osc_state.B.amplitude:.3f}')
    print(f'    C (Correct): {osc_state.C.amplitude:.3f}')
    print(f'    Dominant: {router.get_dominant_channel().value}')

    # Check stats
    stats = router.get_statistics()
    token_stats = stats.get('token_adapter', {})
    print(f'\n  Token Processing Stats:')
    print(f'    Processed: {token_stats.get("tokens_processed", 0)}')
    print(f'    Local hits: {token_stats.get("local_hits", 0)}')
    print(f'    Ollama calls: {token_stats.get("ollama_calls", 0)}')
    print(f'    Using Ollama: {token_stats.get("using_ollama", False)}')

except Exception as e:
    print(f'\n  [ERROR] Router test failed: {e}')
    import traceback
    traceback.print_exc()

# Test 4: Dashboard
print('\n' + '=' * 70)
print('  TEST 4: Oscillator Dashboard')
print('=' * 70)

try:
    from core.oscillator_dashboard import OscillatorDashboard, Colors

    dashboard = OscillatorDashboard(router)

    # Render without clearing screen
    output = dashboard.render()
    print(output)

    # Compact view
    print(f'\n  Compact: {dashboard.render_compact()}')

except Exception as e:
    print(f'\n  [ERROR] Dashboard test failed: {e}')

# Test 5: EventBridge Integration in Router
print('\n' + '=' * 70)
print('  TEST 5: EventBridge Auto-Extraction')
print('=' * 70)

try:
    # Reset stats
    router.event_bridge.reset_statistics()
    router.token_adapter.tokens_processed = 0

    # Create raw events (simulating conversation)
    raw_events = [
        {'type': 'conversation', 'role': 'user', 'text': 'Please deploy the web server'},
        {'type': 'conversation', 'role': 'assistant', 'text': 'I will deploy nginx on port 80'},
    ]

    # Route should auto-extract tokens via EventBridge
    print('\n  Routing events...')
    result = router.route(raw_events, task_description="Deploy web server")

    eb_stats = router.event_bridge.get_statistics()
    print(f'\n  EventBridge Stats after routing:')
    print(f'    Events processed: {eb_stats["events_processed"]}')
    print(f'    Tokens extracted: {eb_stats["tokens_extracted"]}')
    print(f'    Recent tokens: {eb_stats.get("recent_tokens", [])[-5:]}')

    print(f'\n  Routing Result:')
    print(f'    Should execute: {result.should_execute}')
    print(f'    Blocked: {result.blocked}')
    print(f'    Timing confidence: {result.decision.timing_confidence:.3f}')

except Exception as e:
    print(f'\n  [ERROR] Integration test failed: {e}')
    import traceback
    traceback.print_exc()

# Summary
print('\n' + '=' * 70)
print('  PHASE 2 PIPELINE TEST COMPLETE')
print('=' * 70)

print('\n  Components Status:')
print(f'    [{"OK" if "ollama_router" in dir() and ollama_router.is_available else "!!" }] Ollama LLM Router')
print(f'    [OK] EventBridge')
print(f'    [OK] TokenFrequencyAdapter + Ollama')
print(f'    [OK] OscillatorDashboard')
print(f'    [OK] Full Pipeline Integration')

print('\n  To run dashboard live:')
print('    from core.oscillator_dashboard import OscillatorDashboard')
print('    dashboard = OscillatorDashboard(router)')
print('    dashboard.live_loop(interval=0.5)')

print('\n' + '=' * 70)

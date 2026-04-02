"""
Live Pipeline Test: Real-time Event Stream Processing

Tests the full pipeline with:
1. Real-time token extraction via EventBridge
2. Ollama LLM classification
3. Mamba SSM latent dynamics
4. Oscillator visualization
5. Temporal routing decisions

Usage:
    python test_live_pipeline.py

    # Or in interactive mode:
    python test_live_pipeline.py --interactive
"""

import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, '.')

print('=' * 70)
print('  LIVE PIPELINE TEST')
print('  Token -> Frequency -> Oscillator -> CTM -> Decision')
print('=' * 70)


def create_router():
    """Create and configure the Layer4TemporalRouter."""
    from core.layer4_temporal_router import Layer4TemporalRouter

    print('\n[1] Creating Layer4TemporalRouter...')

    router = Layer4TemporalRouter(
        strict_security=True,
        timing_threshold=0.5,
        enable_deep_reasoning=False  # Faster for testing
    )

    print(f'    Oscillator: {router.oscillator}')
    print(f'    TokenAdapter: {router.token_adapter}')
    print(f'    EventBridge: {router.event_bridge}')
    print(f'    Using Mamba: {router.temporal_ctm.use_mamba}')
    print(f'    Using Ollama: {router.token_adapter._using_ollama}')

    return router


def print_oscillator_state(router, prefix=''):
    """Print current oscillator state."""
    osc = router.get_oscillator_state()
    sync = router.get_synchrony_vector()
    dominant = router.get_dominant_channel()

    print(f'{prefix}A (Advance): {osc.A.amplitude:.3f}  |  B (Explore): {osc.B.amplitude:.3f}  |  C (Correct): {osc.C.amplitude:.3f}')
    print(f'{prefix}Dominant: {dominant.value.upper():<10}  |  Coherence: {sync.mean_coherence:.3f}')


def print_bar(label: str, value: float, width: int = 30, color: str = '') -> str:
    """Create a text progress bar."""
    filled = int(value * width)
    empty = width - filled
    bar = '#' * filled + '-' * empty
    return f'{label:12} [{bar}] {value:.3f}'


def print_visual_state(router):
    """Print visual representation of oscillator state."""
    osc = router.get_oscillator_state()
    dominant = router.get_dominant_channel()

    print()
    print(print_bar('A (Advance)', osc.A.amplitude))
    print(print_bar('B (Explore)', osc.B.amplitude))
    print(print_bar('C (Correct)', osc.C.amplitude))
    print(f'\n  Dominant: {dominant.value.upper()}')


def simulate_conversation(router, conversation: List[Dict]) -> None:
    """Simulate a conversation with events."""
    print('\n[2] Simulating Conversation Events...')
    print('-' * 50)

    for i, event in enumerate(conversation, 1):
        role = event.get('role', 'user')
        text = event.get('text', '')

        print(f'\n  [{i}] {role.upper()}: "{text[:50]}..."')

        # Process through EventBridge
        result = router.event_bridge.process_text(text)
        print(f'      Tokens: {result[:8]}...' if len(result) > 8 else f'      Tokens: {result}')

        # Show oscillator state after each event
        print_oscillator_state(router, prefix='      ')

        time.sleep(0.3)  # Small delay for visualization


def run_full_route(router, events: List[Dict], task: str) -> Dict:
    """Run full routing pipeline."""
    print(f'\n[3] Running Full Route: "{task}"')
    print('-' * 50)

    result = router.route(events, task_description=task)

    print(f'    Should Execute: {result.should_execute}')
    print(f'    Tool: {result.tool_name}')
    print(f'    Blocked: {result.blocked}')
    print(f'    Block Reason: {result.block_reason}')
    print(f'    Timing Confidence: {result.decision.timing_confidence:.3f}')
    print(f'    Processing Time: {result.processing_time_ms:.1f}ms')

    return result


def print_statistics(router):
    """Print pipeline statistics."""
    print('\n[4] Pipeline Statistics')
    print('-' * 50)

    stats = router.get_statistics()

    # Token adapter stats
    token_stats = stats.get('token_adapter', {})
    print(f'    Tokens Processed: {token_stats.get("tokens_processed", 0)}')
    print(f'    Local Hits: {token_stats.get("local_hits", 0)}')
    print(f'    Ollama Calls: {token_stats.get("ollama_calls", 0)}')
    print(f'    Local Hit Rate: {token_stats.get("local_hit_rate", 0):.1%}')
    print(f'    Using Ollama: {token_stats.get("using_ollama", False)}')

    # EventBridge stats
    eb_stats = stats.get('event_bridge', {})
    print(f'\n    Events Processed: {eb_stats.get("events_processed", 0)}')
    print(f'    Tokens Extracted: {eb_stats.get("tokens_extracted", 0)}')
    print(f'    Avg Tokens/Event: {eb_stats.get("avg_tokens_per_event", 0):.1f}')

    # Router stats
    print(f'\n    Total Routes: {stats.get("total_routes", 0)}')
    print(f'    Total Executions: {stats.get("total_executions", 0)}')
    print(f'    Total Blocks: {stats.get("total_blocks", 0)}')


def run_test_scenarios(router):
    """Run predefined test scenarios."""
    print('\n' + '=' * 70)
    print('  TEST SCENARIOS')
    print('=' * 70)

    scenarios = [
        {
            'name': 'Deployment Flow',
            'conversation': [
                {'role': 'user', 'text': 'Deploy the nginx container on port 8080'},
                {'role': 'assistant', 'text': 'I will deploy nginx:latest on port 8080'},
            ],
            'task': 'Deploy nginx container'
        },
        {
            'name': 'Exploration Mode',
            'conversation': [
                {'role': 'user', 'text': 'Maybe we should try a different approach'},
                {'role': 'assistant', 'text': 'Perhaps we could explore alternatives'},
            ],
            'task': 'Explore options'
        },
        {
            'name': 'Error Correction',
            'conversation': [
                {'role': 'user', 'text': 'Stop! Do NOT delete the production database'},
                {'role': 'assistant', 'text': 'I will cancel the deletion immediately'},
            ],
            'task': 'Handle error'
        },
        {
            'name': 'Mixed Signals',
            'conversation': [
                {'role': 'user', 'text': 'Deploy nginx but not on production, maybe try staging'},
                {'role': 'assistant', 'text': 'I understand - deploy to staging, not production'},
            ],
            'task': 'Deploy with constraints'
        }
    ]

    for scenario in scenarios:
        print(f'\n\n{"=" * 70}')
        print(f'  SCENARIO: {scenario["name"]}')
        print('=' * 70)

        # Reset router state
        router.reset()

        # Simulate conversation
        simulate_conversation(router, scenario['conversation'])

        # Show visual state
        print_visual_state(router)

        # Run full route
        events = [{'role': e['role'], 'text': e['text'], 'timestamp': datetime.now()}
                  for e in scenario['conversation']]
        run_full_route(router, events, scenario['task'])

        time.sleep(0.5)

    # Final statistics
    print_statistics(router)


def interactive_mode(router):
    """Run interactive mode for manual testing."""
    print('\n' + '=' * 70)
    print('  INTERACTIVE MODE')
    print('  Enter text to process tokens, or commands:')
    print('    /state  - Show oscillator state')
    print('    /stats  - Show statistics')
    print('    /reset  - Reset router')
    print('    /route  - Run full routing')
    print('    /quit   - Exit')
    print('=' * 70)

    conversation_events = []

    while True:
        try:
            text = input('\n> ').strip()

            if not text:
                continue

            if text == '/quit':
                print('Exiting...')
                break

            elif text == '/state':
                print_visual_state(router)

            elif text == '/stats':
                print_statistics(router)

            elif text == '/reset':
                router.reset()
                conversation_events = []
                print('Router reset.')

            elif text == '/route':
                if not conversation_events:
                    print('No events to route. Enter some text first.')
                    continue

                result = run_full_route(router, conversation_events, 'Interactive test')
                print_visual_state(router)

            else:
                # Process as user text
                print(f'Processing: "{text}"')

                # Add to conversation events
                conversation_events.append({
                    'role': 'user',
                    'text': text,
                    'timestamp': datetime.now()
                })

                # Process through EventBridge
                tokens = router.event_bridge.process_text(text)
                print(f'Tokens: {tokens}')

                # Show state
                print_oscillator_state(router, prefix='  ')

        except KeyboardInterrupt:
            print('\n\nInterrupted. Exiting...')
            break
        except Exception as e:
            print(f'Error: {e}')


def main():
    parser = argparse.ArgumentParser(description='Live Pipeline Test')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Run in interactive mode')
    args = parser.parse_args()

    # Create router
    router = create_router()

    if args.interactive:
        interactive_mode(router)
    else:
        run_test_scenarios(router)

    print('\n' + '=' * 70)
    print('  LIVE PIPELINE TEST COMPLETE')
    print('=' * 70)


if __name__ == '__main__':
    main()

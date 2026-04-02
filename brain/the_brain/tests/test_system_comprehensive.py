"""
Comprehensive System Test
Tests all brain components and documents status
"""
import requests
import json
import sys
import io

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def test_system():
    print('='*80)
    print('TAHLAMUS BRAIN SYSTEM - COMPREHENSIVE TEST')
    print('='*80)

    # Test 1: Simple task
    print('\n' + '='*80)
    print('TEST 1: Simple Task (Low Complexity)')
    print('='*80)
    r1 = requests.post('http://localhost:5000/api/chat/send',
                        json={'message': 'List files'},
                        timeout=10)
    result1 = r1.json()['response']
    print(f'✓ Task: List files')
    print(f'  Type: {result1["task_type"]}')
    print(f'  Complexity: {result1["complexity"]:.2f}')
    print(f'  Action: {result1["action"]}')
    print(f'  Confidence: {result1["confidence"]:.1%}')
    print(f'  Brain areas: {", ".join(result1["brain_areas"])}')
    print(f'  Reasoning steps: {len(result1.get("reasoning_chain", []))}')

    # Test 2: Medium task
    print('\n' + '='*80)
    print('TEST 2: Medium Task (Medium Complexity)')
    print('='*80)
    r2 = requests.post('http://localhost:5000/api/chat/send',
                        json={'message': 'Build Docker image and run tests'},
                        timeout=10)
    result2 = r2.json()['response']
    print(f'✓ Task: Build Docker image and run tests')
    print(f'  Type: {result2["task_type"]}')
    print(f'  Complexity: {result2["complexity"]:.2f}')
    print(f'  Action: {result2["action"]}')
    print(f'  Confidence: {result2["confidence"]:.1%}')
    print(f'  Brain areas: {", ".join(result2["brain_areas"])}')
    print(f'  Predicted sequence: {" → ".join(result2.get("sequence", ["none"]))}')

    # Test 3: Complex task
    print('\n' + '='*80)
    print('TEST 3: Complex Task (High Complexity)')
    print('='*80)
    r3 = requests.post('http://localhost:5000/api/chat/send',
                        json={'message': 'Design distributed microservices with auto-scaling and fault tolerance'},
                        timeout=10)
    result3 = r3.json()['response']
    print(f'✓ Task: Design distributed microservices')
    print(f'  Type: {result3["task_type"]}')
    print(f'  Complexity: {result3["complexity"]:.2f}')
    print(f'  Action: {result3["action"]}')
    print(f'  Confidence: {result3["confidence"]:.1%}')
    print(f'  Brain areas: {", ".join(result3["brain_areas"])}')
    print(f'  Success probability: {result3.get("success_probability", 0):.1%}')
    if 'questions' in result3:
        print(f'  Generated questions: {len(result3["questions"])}')

    # Test 4: Urgent task
    print('\n' + '='*80)
    print('TEST 4: Urgent Task (High Urgency Detection)')
    print('='*80)
    r4 = requests.post('http://localhost:5000/api/chat/send',
                        json={'message': 'Deploy NOW - critical production bug URGENT!'},
                        timeout=10)
    result4 = r4.json()['response']
    print(f'✓ Task: Deploy NOW - critical bug')
    print(f'  Type: {result4["task_type"]}')
    print(f'  Complexity: {result4["complexity"]:.2f}')
    print(f'  Urgency: {result4["urgency"]:.2f}')
    print(f'  Action: {result4["action"]}')
    print(f'  Confidence: {result4["confidence"]:.1%}')

    # Test 5: Check LLM stats
    print('\n' + '='*80)
    print('TEST 5: LLM Integration Check')
    print('='*80)
    if 'llm_stats' in result1:
        stats = result1['llm_stats']
        print(f'✓ LLM Mode: {stats["mode"]}')
        print(f'  Total calls: {stats["total_calls"]}')
        print(f'  Total cost: ${stats["total_cost"]:.4f}')

    # Test 6: Dashboard endpoints
    print('\n' + '='*80)
    print('TEST 6: Dashboard API Endpoints')
    print('='*80)

    endpoints = [
        '/api/brain/gates',
        '/api/brain/activation',
        '/api/brain/state',
        '/api/brain/strategies',
        '/api/brain/interventions'
    ]

    for endpoint in endpoints:
        try:
            r = requests.get(f'http://localhost:5000{endpoint}', timeout=5)
            status = '✓' if r.status_code == 200 else '✗'
            print(f'{status} {endpoint}: {r.status_code}')
        except Exception as e:
            print(f'✗ {endpoint}: ERROR - {e}')

    # Summary
    print('\n' + '='*80)
    print('SUMMARY - Complexity Estimation')
    print('='*80)
    complexities = [
        ('Simple (list files)', result1["complexity"]),
        ('Medium (docker + tests)', result2["complexity"]),
        ('Complex (microservices)', result3["complexity"]),
        ('Urgent (deploy)', result4["complexity"])
    ]

    for name, comp in complexities:
        bar = '█' * int(comp * 50)
        print(f'{name:30s} {comp:0.2f} {"│" + bar}')

    min_comp = min(c[1] for c in complexities)
    max_comp = max(c[1] for c in complexities)
    range_comp = max_comp - min_comp

    print(f'\nComplexity range: {min_comp:.2f} - {max_comp:.2f} ({range_comp:.2f} spread)')

    # Urgency test
    print('\n' + '='*80)
    print('SUMMARY - Urgency Detection')
    print('='*80)
    print(f'Normal task urgency: {result1["urgency"]:.2f}')
    print(f'Urgent task urgency: {result4["urgency"]:.2f}')
    print(f'Urgency range: {result1["urgency"]:.2f} - {result4["urgency"]:.2f}')

    # Actions summary
    print('\n' + '='*80)
    print('SUMMARY - Action Decisions')
    print('='*80)
    print(f'Simple task → {result1["action"]} ({result1["confidence"]:.1%} confidence)')
    print(f'Medium task → {result2["action"]} ({result2["confidence"]:.1%} confidence)')
    print(f'Complex task → {result3["action"]} ({result3["confidence"]:.1%} confidence)')
    print(f'Urgent task → {result4["action"]} ({result4["confidence"]:.1%} confidence)')

    print('\n' + '='*80)
    print('TEST COMPLETE')
    print('='*80)

if __name__ == '__main__':
    try:
        test_system()
    except Exception as e:
        print(f'\n✗ ERROR: {e}')
        import traceback
        traceback.print_exc()

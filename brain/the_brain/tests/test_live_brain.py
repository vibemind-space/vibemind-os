"""Live Brain Chat endpoint test — run while server is up on :5006."""
import requests

BASE = 'http://localhost:5006'

def test_chat(msg):
    r = requests.post(f'{BASE}/api/brain/chat', json={'message': msg})
    d = r.json()
    tt = d.get('routing', {}).get('task_type', '?')
    resp = d.get('response', '')[:100]
    aug = d.get('augmented', False)
    src = d.get('augment_source', '')
    ms = d.get('timing', {}).get('total_ms', 0)
    print(f"  {tt:15s} aug={aug!s:6s} src={src:10s} {ms:7.0f}ms")
    print(f"  -> {resp}")
    return d

print("=" * 70)
print("BRAIN CHAT LIVE TESTS")
print("=" * 70)

print("\n--- Greetings (should be fast, no augmentation) ---")
for msg in ['Hello!', 'hello', 'Hi', 'Hey there', 'Hallo', 'Good morning']:
    print(f"\nQ: {msg}")
    d = test_chat(msg)
    assert d['routing']['task_type'] in ('greeting', 'identity'), f"FAIL: {msg} routed as {d['routing']['task_type']}"

print("\n--- Identity (should be fast, no augmentation) ---")
for msg in ['Who are you?', 'Wer bist du?', 'What is your name?']:
    print(f"\nQ: {msg}")
    d = test_chat(msg)
    assert 'Tahlamus' in d['response'] or 'tahlamus' in d['response'].lower(), f"FAIL: {msg} -> missing Tahlamus"

print("\n--- Knowledge questions (should use Wikipedia) ---")
for msg in ['What is quantum computing?', 'Tell me about photosynthesis', 'How does gravity work?']:
    print(f"\nQ: {msg}")
    d = test_chat(msg)
    assert d['augmented'], f"FAIL: {msg} not augmented"
    assert len(d['response']) > 30, f"FAIL: {msg} response too short"

print("\n--- Comparison question ---")
msg = 'What is the difference between DNA and RNA?'
print(f"\nQ: {msg}")
d = test_chat(msg)
assert d['augmented'], f"FAIL: {msg} not augmented"

print("\n--- Thought trace ---")
msg = 'Explain neural networks'
print(f"\nQ: {msg}")
d = test_chat(msg)
trace = d.get('thought_trace', [])
print(f"  Trace steps: {len(trace)}")
for step in trace:
    print(f"    [{step['category']}] {step['module']}: {step['content'][:60]}")
assert len(trace) >= 3, f"FAIL: trace too short ({len(trace)})"

print("\n--- Brain thoughts endpoint ---")
r = requests.get(f'{BASE}/api/brain/thoughts')
d = r.json()
print(f"  Thinking: {d['thinking']}, Mode: {d['mode']}")
print(f"  Total thoughts: {d['stats'].get('thought_count', 0)}")
print(f"  Recent: {len(d['thoughts'])} thoughts")
assert d['thinking'], "FAIL: brain not thinking!"

print("\n--- Brain state endpoint ---")
r = requests.get(f'{BASE}/api/brain/state')
d = r.json()
print(f"  CT running: {d['continuous_thinking']['running']}")
print(f"  CT mode: {d['continuous_thinking']['mode']}")
print(f"  Messages: {d['brain_chat']['total_messages']}")

print("\n" + "=" * 70)
print("ALL TESTS PASSED!")
print("=" * 70)

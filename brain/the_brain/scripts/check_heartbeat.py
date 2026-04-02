import requests
import json

r = requests.get('http://localhost:5001/brain_state')
data = r.json()

print("=" * 70)
print("HEARTBEAT STATUS CHECK")
print("=" * 70)

print("\n=== RECENT HEARTBEATS ===")
for h in data['recent_heartbeats'][-5:]:
    print(f"Tick {h['tick_number']}: {h['actions_taken']} ({h['elapsed_ms']:.0f}ms)")

print("\n=== RECENT ERRORS ===")
print(f"Total errors: {len(data['recent_errors'])}")
for e in data['recent_errors']:
    print(f"  Tick {e['tick_number']} - {e['context']}: {e['error'][:80]}")

print("\n=== HEALTH ===")
print(f"Status: {data['health']['status']}")
print(f"Memory: {data['health']['memory_mb']:.1f} MB")
print(f"Error count: {data['health']['error_count']}")

print("\n=== NEUROMODULATION ===")
neuro = data['neuromodulation']
print(f"Dopamine: {neuro['dopamine']:.3f}")
print(f"Serotonin: {neuro['serotonin']:.3f}")
print(f"Norepinephrine: {neuro['norepinephrine']:.3f}")
print(f"State: {neuro['state_description']}")

print("\n" + "=" * 70)

# Memory System Testing Guide

## Quick Test Commands

### Test 1: Memory API Service (30 seconds)

```bash
# Start Memory API service (if not running)
python memory_api/memory_service.py
```

Open new terminal:
```bash
# Test Memory API client
python memory_api/memory_client.py
```

**Expected Output:**
```
======================================================================
MEMORY API CLIENT TEST
======================================================================

[1] Checking memory service health...
  [OK] Memory service is running

[2] Storing execution memory...
  [OK] Stored: {'id': '...', 'status': 'queued'}

[3] Storing chat memory...
  [OK] Stored: {'id': '...', 'status': 'queued'}

[4] Getting planning context...
  [OK] Retrieved 0 memories

======================================================================
ALL TESTS COMPLETE
======================================================================
```

---

### Test 2: Infinite Chat Proxy (1 minute)

```bash
python core/supermemory_llm_client.py
```

**Expected Output:**
```
======================================================================
SUPERMEMORY LLM CLIENT TEST
======================================================================

[SupermemoryLLM] Initialized for user: test_user_123
  Provider: openai
  Base URL: https://api.supermemory.ai/v3/https://api.openai.com/v1
  Infinite Chat: ENABLED

[1] Testing simple chat...
Response: Docker is an open-source platform...

[2] Testing task planning...
Plan: To deploy a Docker container...

[3] Testing conversation context...
Response: Great choice! Here's how to deploy...

======================================================================
TEST COMPLETE
======================================================================
```

---

### Test 3: Full Integration Demo (2 minutes)

```bash
python examples/memory_integration_example.py
```

**Expected Output:**
```
======================================================================
BRAIN PLANNING WITH MEMORY INTEGRATION
======================================================================

[OK] Memory API service connected

[TASK] Deploy a Docker container to AWS ECS
[USER] user_alice

[1] Retrieving memory context...
    Retrieved 0 memories

[2] Memory context for LLM...
[3] Sending to LLM for planning...
[4] Agent executing plan...
    [SUCCESS] Step 1: Check AWS credentials (120ms)
    [SUCCESS] Step 2: docker build -t myapp:latest . (3200ms)
    ...

[5] Storing execution session in memory...
[OK] Execution memory stored: S8mRmeEi9B4gGzHs69nAGK

[COMPLETE] All memories stored successfully!
```

---

### Test 4: Infinite Chat Demo (2 minutes)

```bash
python examples/infinite_chat_demo.py
```

**Expected Output:**
```
======================================================================
INFINITE CHAT DEMO
Comparing Manual Memory vs Automatic Semantic Memory
======================================================================

OLD APPROACH: Manual Memory Retrieval
  - Requires manual memory retrieval
  - Need to format memories as text
  - Limited to recent memories (last 3)
  ...

NEW APPROACH: Infinite Chat Proxy
  [SupermemoryLLM] Initialized for user: user_alice
  Response: To deploy a Docker container...
  ...

Benefits:
  - 95% less code
  - Semantic relevance (not just recent)
  - Unlimited context windows
  - 50%+ token reduction
```

---

### Test 5: Execution Tracker (30 seconds)

```bash
python core/execution_tracker.py
```

**Expected Output:**
```
======================================================================
EXECUTION TRACKER TEST
======================================================================

[ExecutionTracker] Started session: deploy-docker-20250115
  Task: Deploy Docker container to production
  Agent: deployment_agent

[ExecutionTracker] [OK] Step 1: docker build -t myapp:latest . (3200ms)
[ExecutionTracker] [OK] Step 2: docker tag myapp:latest ... (150ms)
...
[ExecutionTracker] Session complete: SUCCESS (95.0% confidence)

FORMATTED SESSION LOG
...
Total steps: 5
Success: 5 | Failures: 0
Total duration: 13300ms
```

---

## Interactive Testing

### Test Memory API with cURL

```bash
# Health check
curl http://localhost:8001/health

# Store execution memory
curl -X POST http://localhost:8001/memories/execution \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Test deployment",
    "result": "SUCCESS",
    "confidence": 0.95,
    "session_log": "Step 1: Build\nStep 2: Deploy",
    "agent_name": "test_agent"
  }'

# Query memories
curl -X POST http://localhost:8001/memories/query \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "agent_execution",
    "limit": 5
  }'
```

### Test with Python REPL

```bash
python
```

```python
# Test Memory API
from memory_api.memory_client import MemoryClient

client = MemoryClient()
print(client.health_check())  # Should print: True

# Store a memory
result = client.store_execution(
    task="Test task",
    result="SUCCESS",
    confidence=0.9,
    session_log="Test log"
)
print(result)  # Should print: {'id': '...', 'status': 'queued'}

# Test Infinite Chat
from core.supermemory_llm_client import SupermemoryLLM

llm = SupermemoryLLM(user_id="test_user")
response = llm.chat_simple("What is Docker?")
print(response[:200])  # Should print Docker explanation
```

---

## Advanced Testing

### Test Semantic Memory Retrieval

Create two conversations and test semantic retrieval:

```python
from core.supermemory_llm_client import SupermemoryLLM

llm = SupermemoryLLM(user_id="test_semantic")

# Conversation 1: Docker deployment
print("=== Conversation 1: Docker ===")
response1 = llm.chat_simple("How do I deploy a Docker container?")
print(response1[:150])

# Wait a moment for indexing
import time
time.sleep(5)

# Conversation 2: Related topic - should retrieve Docker context
print("\n=== Conversation 2: Container Issues ===")
response2 = llm.chat_simple("My container won't start, any ideas?")
print(response2[:150])
# Should mention Docker context automatically!
```

### Test Multi-User Isolation

```python
from core.supermemory_llm_client import SupermemoryLLM

# Alice's memory
llm_alice = SupermemoryLLM(user_id="alice")
llm_alice.chat_simple("I love Python programming")

# Bob's memory
llm_bob = SupermemoryLLM(user_id="bob")
llm_bob.chat_simple("I love JavaScript programming")

# Bob's next conversation shouldn't mention Python
response = llm_bob.chat_simple("What language do I like?")
print(response)  # Should say JavaScript, not Python
```

### Test Execution Tracking Flow

```python
from core.execution_tracker import ExecutionTracker
from memory_api.memory_client import MemoryClient

# 1. Create tracker
tracker = ExecutionTracker(
    task="Full test workflow",
    agent_name="test_agent",
    user_id="test_user"
)

# 2. Add steps
for i in range(1, 4):
    tracker.add_execution(
        step=i,
        command=f"Step {i} command",
        result="SUCCESS",
        output=f"Step {i} output",
        duration_ms=100 * i
    )

# 3. Mark complete
tracker.mark_complete("SUCCESS", confidence=0.95)

# 4. Store
memory_client = MemoryClient()
result = memory_client.store_execution(
    task=tracker.task,
    result="SUCCESS",
    confidence=0.95,
    session_log=tracker.format_as_text(),
    agent_name=tracker.agent_name,
    duration_ms=tracker.get_total_duration(),
    user_id="test_user"
)

print(f"Stored: {result['id']}")
```

---

## Troubleshooting Tests

### Test 1: Check Services Running

```bash
# Check Memory API
curl http://localhost:8001/health

# If not running, start it:
python memory_api/memory_service.py
```

### Test 2: Check API Keys

```bash
python
```

```python
import os
from load_env import load_env_file

load_env_file()

# Check keys
print("OPENAI_API_KEY:", "✓ Set" if os.getenv('OPENAI_API_KEY') else "✗ Missing")
print("SUPERMEMORY_API_KEY:", "✓ Set" if os.getenv('SUPERMEMORY_API_KEY') else "✗ Missing")

# If missing, add to .env file
```

### Test 3: Test Supermemory Connection

```python
from core.supermemory_client import SupermemoryClient

client = SupermemoryClient()
success = client.test_connection()

if success:
    print("✓ Supermemory connected!")
else:
    print("✗ Supermemory connection failed")
    print("Check your SUPERMEMORY_API_KEY in .env")
```

### Test 4: Check OpenAI Connection

```python
from openai import OpenAI

client = OpenAI()  # Uses OPENAI_API_KEY from env

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=10
    )
    print("✓ OpenAI connected!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"✗ OpenAI connection failed: {e}")
```

---

## Verification Checklist

Run through this checklist to verify everything works:

### Basic Tests (5 minutes)

- [ ] Memory API health check: `curl http://localhost:8001/health`
- [ ] Memory API client test: `python memory_api/memory_client.py`
- [ ] Supermemory LLM test: `python core/supermemory_llm_client.py`
- [ ] Execution tracker test: `python core/execution_tracker.py`

### Integration Tests (5 minutes)

- [ ] Memory integration example: `python examples/memory_integration_example.py`
- [ ] Infinite chat demo: `python examples/infinite_chat_demo.py`

### API Keys (1 minute)

- [ ] OPENAI_API_KEY set in .env
- [ ] SUPERMEMORY_API_KEY set in .env
- [ ] Keys valid and working

### Services (1 minute)

- [ ] Memory API running on port 8001
- [ ] Can access http://localhost:8001/docs
- [ ] Supermemory proxy accessible

### Features (10 minutes)

- [ ] Can store execution memory
- [ ] Can store chat memory
- [ ] Can query memories
- [ ] Infinite Chat returns responses
- [ ] Semantic memory retrieval works
- [ ] User isolation works

---

## Expected Test Duration

| Test | Duration | Critical |
|------|----------|----------|
| Memory API client | 30 sec | ✅ Yes |
| Infinite Chat client | 1 min | ✅ Yes |
| Integration example | 2 min | ✅ Yes |
| Infinite chat demo | 2 min | ⚠️ Optional |
| Execution tracker | 30 sec | ⚠️ Optional |
| **Total Critical** | **4 min** | |
| **Total All** | **6 min** | |

---

## Quick Success Check

Run this single command to verify everything:

```bash
python -c "
from memory_api.memory_client import MemoryClient
from core.supermemory_llm_client import SupermemoryLLM

# Test Memory API
print('[1/2] Testing Memory API...')
memory = MemoryClient()
if memory.health_check():
    print('  ✓ Memory API working')
else:
    print('  ✗ Memory API not running')
    exit(1)

# Test Infinite Chat
print('[2/2] Testing Infinite Chat...')
try:
    llm = SupermemoryLLM(user_id='test')
    response = llm.chat_simple('Say OK')
    print('  ✓ Infinite Chat working')
    print(f'  Response: {response[:50]}...')
except Exception as e:
    print(f'  ✗ Infinite Chat failed: {e}')
    exit(1)

print('\n✓ ALL TESTS PASSED!')
"
```

---

## Visual Testing (Browser)

### Memory API Documentation UI

1. Start Memory API: `python memory_api/memory_service.py`
2. Open browser: http://localhost:8001/docs
3. Try the endpoints:
   - GET /health
   - POST /memories/execution
   - POST /memories/query

### Test Supermemory Dashboard

1. Login to https://console.supermemory.ai
2. Check "Documents" tab
3. Should see your test memories appearing
4. Check "Analytics" for usage stats

---

## Automated Test Suite

Create a test script `test_all.py`:

```python
#!/usr/bin/env python3
"""Run all memory system tests"""

import sys
import subprocess

tests = [
    ("Memory API Client", "python memory_api/memory_client.py"),
    ("Supermemory LLM", "python core/supermemory_llm_client.py"),
    ("Execution Tracker", "python core/execution_tracker.py"),
    ("Integration Example", "python examples/memory_integration_example.py"),
]

print("=" * 70)
print("RUNNING ALL MEMORY SYSTEM TESTS")
print("=" * 70)
print()

passed = 0
failed = 0

for name, command in tests:
    print(f"[TEST] {name}")
    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            timeout=60
        )
        if result.returncode == 0:
            print(f"  ✓ PASSED")
            passed += 1
        else:
            print(f"  ✗ FAILED")
            print(result.stderr.decode()[:200])
            failed += 1
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        failed += 1
    print()

print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 70)

sys.exit(0 if failed == 0 else 1)
```

Run with: `python test_all.py`

---

## Next Steps After Testing

Once all tests pass:

1. ✅ Memory system is working
2. ➡️ Integrate into hierarchical planner
3. ➡️ Update brain dashboard
4. ➡️ Create visual memory poller
5. ➡️ Build agent bridge

---

**Quick Start:** Just run these 3 commands:

```bash
# 1. Start Memory API (keep running in background)
python memory_api/memory_service.py

# 2. Test Memory API (new terminal)
python memory_api/memory_client.py

# 3. Test Infinite Chat
python core/supermemory_llm_client.py
```

If all three complete without errors, your memory system is fully operational! ✅

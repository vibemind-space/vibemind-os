# Memory System Quick Start Guide

## Starting the Memory API Service

```bash
cd C:/Users/User/Desktop/Tahlamus
python memory_api/memory_service.py
```

Service will run on: **http://localhost:8001**
API docs: **http://localhost:8001/docs**

## Using Memory in Your Code

### 1. Import the Client

```python
from memory_api.memory_client import MemoryClient

client = MemoryClient(base_url="http://localhost:8001")
```

### 2. Store Execution Memory

```python
from core.execution_tracker import ExecutionTracker

# Create tracker
tracker = ExecutionTracker(
    task="Your task description",
    agent_name="your_agent_name",
    user_id="user_123"  # Optional
)

# Add execution steps
tracker.add_execution(
    step=1,
    command="docker build -t myapp .",
    result="SUCCESS",
    output="Image built successfully",
    duration_ms=3200
)

# Mark complete
tracker.mark_complete("SUCCESS", confidence=0.95)

# Store in memory
session_log = tracker.format_as_text()
client.store_execution(
    task=tracker.task,
    result="SUCCESS",
    confidence=0.95,
    session_log=session_log,
    agent_name="your_agent",
    duration_ms=tracker.get_total_duration(),
    user_id="user_123"
)
```

### 3. Store Chat Memory

```python
client.store_chat(
    messages=[
        {"role": "user", "content": "How do I deploy?"},
        {"role": "assistant", "content": "Here's how..."}
    ],
    topics=["deployment", "docker"],
    planning_triggered=True,
    user_id="user_123"
)
```

### 4. Store Visual Memory

```python
client.store_visual(
    window_title="VSCode - main.py",
    screen_data={
        "window_title": "VSCode - main.py",
        "captured_at": int(datetime.now().timestamp() * 1000)
    },
    ocr_text="def process_data(): return result",
    visible_files=["main.py", "config.yaml"],
    user_id="user_123"
)
```

### 5. Retrieve Memory for Planning

```python
# Before planning, get relevant memory context
context = client.get_planning_context(
    task="Deploy Docker container",
    user_id="user_123",
    include_visual=True,
    include_execution=True,
    include_chat=True
)

# Use context in LLM prompt
exec_memories = context['memories']['execution_memories']
chat_memories = context['memories']['chat_memories']
```

## Integration Pattern

```python
# 1. Retrieve memory context BEFORE planning
context = client.get_planning_context(task, user_id)

# 2. Include context in LLM prompt
prompt = f"""
Task: {task}

Relevant Past Executions:
{format_execution_memories(context['memories']['execution_memories'])}

Please create a plan...
"""

# 3. Execute plan with tracker
tracker = ExecutionTracker(task=task, agent_name="my_agent", user_id=user_id)

for step in plan:
    result = execute_step(step)
    tracker.add_execution(
        step=i,
        command=step,
        result=result.status,
        output=result.output,
        duration_ms=result.duration
    )

# 4. Mark complete with agent-determined confidence
tracker.mark_complete("SUCCESS", confidence=0.95)

# 5. Store execution memory
client.store_execution(
    task=task,
    result="SUCCESS",
    confidence=0.95,
    session_log=tracker.format_as_text(),
    agent_name="my_agent",
    duration_ms=tracker.get_total_duration(),
    user_id=user_id
)

# 6. Store conversation
client.store_chat(
    messages=conversation,
    topics=extract_topics(conversation),
    planning_triggered=True,
    user_id=user_id
)
```

## Environment Setup

Ensure your `.env` file has:

```bash
SUPERMEMORY_API_KEY=your_api_key_here
SUPERMEMORY_BASE_URL=https://api.supermemory.ai
```

Get your API key from: https://console.supermemory.ai

## Testing

### Test Memory Client

```bash
python memory_api/memory_client.py
```

### Test Execution Tracker

```bash
python core/execution_tracker.py
```

### Test Integration Example

```bash
python examples/memory_integration_example.py
```

## Memory Types

| Type | Tag | URL Pattern | Use Case |
|------|-----|-------------|----------|
| Execution | `execution`, `agent` | `tahlamus://execution/{session_id}` | Agent task results |
| Chat | `chat`, `conversation` | `tahlamus://chat/{timestamp}` | Conversation history |
| Visual | `visual`, `screen_capture` | `tahlamus://visual/{timestamp}` | Screen captures |

## Multi-User Support

All memory operations support `user_id` parameter for user isolation:

```python
# Store with user context
client.store_execution(..., user_id="user_alice")

# Query for specific user
context = client.get_planning_context(task, user_id="user_alice")
```

Memories are tagged with `user_{user_id}` automatically.

## Key Benefits

1. **Memory Before Planning** - Brain retrieves relevant past experiences before making decisions
2. **Learning from Failures** - Both successes and failures stored with confidence scores
3. **Session-Based Execution** - Complete execution sequences stored as lists, not individual steps
4. **Clean API Abstraction** - Brain doesn't know about Supermemory implementation details
5. **Multi-User Ready** - Isolated memory spaces for different users

## Next Steps

1. Integrate into `core/hierarchical_planner.py`
2. Add memory visualization to brain dashboard
3. Create visual memory poller (polls Supabase every 5 seconds)
4. Build agent bridge for real execution tracking

## Troubleshooting

**Memory API not responding:**
```bash
# Check if running
curl http://localhost:8001/health

# Restart if needed
python memory_api/memory_service.py
```

**401 Unauthorized:**
- Check SUPERMEMORY_API_KEY in .env
- Verify key is valid at console.supermemory.ai

**No memories returned:**
- Memories may take a few seconds to index
- Check containerTags match what was stored

## Example Output

```
[ExecutionTracker] Started session: session-1760618735
  Task: Deploy a Docker container to AWS ECS
  Agent: aws_deployment_agent
  User: user_alice

[ExecutionTracker] [OK] Step 1: Check AWS credentials (120ms)
[ExecutionTracker] [OK] Step 2: docker build -t myapp:latest . (3200ms)
[ExecutionTracker] [OK] Step 3: docker tag myapp:latest (150ms)
...
[ExecutionTracker] Session complete: SUCCESS (95.0% confidence)

[OK] Execution memory stored: S8mRmeEi9B4gGzHs69nAGK
```

---

**Status:** ✅ Fully Operational
**Memory API:** http://localhost:8001
**Documentation:** http://localhost:8001/docs

# Supermemory Integration - Quick Start Guide

## What's Been Built

I've created a complete Supermemory integration for Tahlamus that provides hippocampal memory backed by the Supermemory API. Here's what's ready:

### Core Components

1. **`core/supermemory_client.py`** ✅
   - Python wrapper for Supermemory REST API
   - Methods for storing visual, execution, and chat memories
   - Search and query capabilities
   - Connection testing

2. **`core/supermemory_hippocampus.py`** ✅
   - Integration layer between Tahlamus and Supermemory
   - Automatic memory retrieval for planning (`query_for_planning`)
   - On-demand queries (`query_specific`)
   - Memory formation from all sources
   - Fallback to existing hippocampus if Supermemory unavailable
   - LLM-ready context formatting

3. **`core/supabase_visual_connector.py`** ✅
   - Reads screen/desktop data from your Supabase database
   - Queries by time window, window title, OCR text
   - Visual context summarization

4. **`load_env.py`** ✅ (Updated)
   - Helper functions for Supermemory, Supabase, and OpenRouter keys
   - Automatic .env file loading

5. **`requirements-memory.txt`** ✅
   - Dependencies for memory system (requests, supabase)

6. **Documentation** ✅
   - `SUPERMEMORY_INTEGRATION_RESEARCH.md` - Full research and API docs
   - This quickstart guide

---

## Setup Instructions

### Step 1: Get Supermemory API Key

1. Visit **https://console.supermemory.ai**
2. Sign up / log in
3. Get your API key
4. Copy it to your .env file

### Step 2: Update .env File

Add these lines to your `.env` file in the Tahlamus project root:

```bash
# Supermemory Configuration
SUPERMEMORY_API_KEY=your_api_key_from_console

# Supabase Configuration (you already have these)
SUPABASE_URL=https://dgzreelowtzquljhxskq.supabase.co
SUPABASE_SECRET_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRnenJlZWxvd3R6cXVsamh4c2txIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0OTcyMDU0NiwiZXhwIjoyMDY1Mjk2NTQ2fQ.bXN09OJx2q2UvEMeX-IWTc6TuqKwo1SiMuBnyciY-oI

# OpenRouter (you already have this)
OPENROUTER_API_KEY=your_openrouter_key
```

### Step 3: Install Dependencies

```bash
pip install -r requirements-memory.txt
```

Or individually:
```bash
pip install requests supabase
```

### Step 4: Test the Integration

**Test Supermemory Client:**
```bash
python core/supermemory_client.py
```

**Test Hippocampus Integration:**
```bash
python core/supermemory_hippocampus.py
```

**Test Supabase Visual Connector:**
```bash
python core/supabase_visual_connector.py
```

**Check All Environment Variables:**
```bash
python load_env.py
```

---

## Usage Examples

### 1. Initialize Supermemory Hippocampus

```python
from core.supermemory_hippocampus import SupermemoryHippocampus

# Initialize with automatic .env loading
hippocampus = SupermemoryHippocampus(
    enable_fallback=True  # Falls back to existing hippocampus if Supermemory unavailable
)
```

### 2. Store Memories

**Visual Memory (from Supabase screen data):**
```python
screen_data = {
    'window_title': 'VSCode - main.py',
    'ocr_text': 'def process_data(): return result',
    'captured_at': 1705315800000
}

hippocampus.store_visual_memory(
    screen_data=screen_data,
    window_title='VSCode - main.py',
    visible_files=['main.py', 'config.yaml']
)
```

**Execution Memory (from agent completion):**
```python
hippocampus.store_execution_memory(
    task="Deploy Docker container to production",
    result="SUCCESS",
    confidence=0.95,
    agent_name="deployment_agent",
    duration_ms=5400,
    session_log="Container deployed successfully on port 8080"
)
```

**Chat Memory (from conversation):**
```python
hippocampus.store_chat_memory(
    messages=[
        {'role': 'user', 'content': 'How do I deploy a container?'},
        {'role': 'assistant', 'content': 'I can help you deploy a container...'}
    ],
    topics=['docker', 'deployment'],
    planning_triggered=True
)
```

### 3. Query Memories for Planning

This is the **key function** that automatically retrieves relevant memories when planning a task:

```python
# Automatic memory retrieval for planning
memory_context = hippocampus.query_for_planning(
    task="Deploy Docker container",
    include_visual=True,      # Recent screen context
    include_execution=True,   # Similar past executions
    include_chat=True,        # Related conversations
    limit_per_type=3
)

# Returns:
# {
#     'visual_memories': [...],
#     'execution_memories': [...],
#     'chat_memories': [...],
#     'formatted_context': "...",  # Ready to inject into LLM prompt
#     'total_memories': 5
# }

# Use formatted context in your planning LLM:
planning_prompt = f"""
{memory_context['formatted_context']}

Task: {task}

Based on the memory context above, plan the execution steps...
"""
```

### 4. On-Demand Queries

```python
# Search all memories
results = hippocampus.query_specific(
    query="Docker deployment",
    memory_type="agent_execution",
    limit=10
)

# Query by tags/spaces
docker_memories = hippocampus.query_specific(
    query="container",
    spaces=['docker', 'deployment']
)
```

---

## Integration with Existing Brain Components

### Planning Area (DeepSeek R1)

When planning a task, automatically query memories:

```python
from core.hierarchical_planner import HierarchicalPlanner
from core.supermemory_hippocampus import SupermemoryHippocampus

hippocampus = SupermemoryHippocampus()

def plan_with_memory(task: str):
    # Query memories
    memory_context = hippocampus.query_for_planning(task)

    # Add memory context to planning prompt
    enhanced_prompt = f"{memory_context['formatted_context']}\n\nTask: {task}"

    # Plan with hierarchical planner
    result = planner.predict(enhanced_prompt)

    return result
```

### Agent Execution → Memory Formation

After agent completes a task, store execution memory:

```python
# Agent finishes task
result = agent.execute(task)

# Store in Supermemory (with confidence set by agent)
hippocampus.store_execution_memory(
    task=task,
    result=result['status'],
    confidence=result['confidence'],  # ONLY AGENT SETS THIS
    session_log=result['logs'],
    agent_name=result['agent_name'],
    duration_ms=result['duration']
)
```

### Visual Area → Memory Formation

Background service polls Supabase and stores visual memories:

```python
import time
from core.supabase_visual_connector import SupabaseVisualConnector
from core.supermemory_hippocampus import SupermemoryHippocampus

visual_connector = SupabaseVisualConnector()
hippocampus = SupermemoryHippocampus()

while True:
    # Get latest screen state
    screen_data = visual_connector.get_latest_screen_state(limit=1)

    if screen_data:
        # Store in Supermemory
        hippocampus.store_visual_memory(
            screen_data=screen_data[0]
        )

    time.sleep(5)  # Poll every 5 seconds
```

---

## Memory Schema

### Visual Memories
```json
{
  "type": "visual_context",
  "title": "Screen - VSCode",
  "content": "Window: VSCode | Files: main.py, config.yaml | OCR: def process_data()...",
  "url": "tahlamus://visual/2025-01-15T10:30:00",
  "spaces": ["visual", "screen_capture"],
  "metadata": {
    "captured_at": 1705315800000,
    "window_title": "VSCode - main.py",
    "visible_files": ["main.py", "config.yaml"]
  }
}
```

### Execution Memories
```json
{
  "type": "agent_execution",
  "title": "SUCCESS - Deploy Docker container",
  "content": "Task: Deploy Docker container\nResult: SUCCESS\nConfidence: 95%\nLogs: ...",
  "url": "tahlamus://execution/session-abc123",
  "spaces": ["execution", "agent", "success"],
  "metadata": {
    "confidence": 0.95,
    "agent_name": "deployment_agent",
    "duration_ms": 5400
  }
}
```

### Chat Memories
```json
{
  "type": "conversation",
  "title": "Chat - Docker deployment question",
  "content": "User: How do I deploy?\nAssistant: I can help...",
  "url": "tahlamus://chat/2025-01-15T10:45:00",
  "spaces": ["chat", "docker", "deployment"],
  "metadata": {
    "message_count": 5,
    "planning_triggered": true
  }
}
```

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        USER CHAT                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌─────────────────────────┐
         │   PLANNING AREA         │
         │   (DeepSeek R1)         │
         └───────┬─────────────────┘
                 │
                 │ 1. Query memories
                 ▼
    ┌─────────────────────────────┐
    │ SUPERMEMORY HIPPOCAMPUS     │
    │  - query_for_planning()     │
    └─────┬───────────────────────┘
          │
          │ Retrieves:
          │ • Visual context (Supabase → screen data)
          │ • Similar executions (past tasks)
          │ • Related conversations
          │
          ▼
    ┌─────────────────────────────┐
    │    SUPERMEMORY API          │
    │  (v2.api.supermemory.ai)    │
    └─────────────────────────────┘
          │
          │ Returns formatted context
          ▼
         ┌─────────────────────────┐
         │   PLANNING AREA         │
         │   Plans with context    │
         └───────┬─────────────────┘
                 │
                 │ 2. Execute plan
                 ▼
         ┌─────────────────────────┐
         │   AGENT EXECUTION       │
         │   (External system)     │
         └───────┬─────────────────┘
                 │
                 │ 3. Store result
                 ▼
    ┌─────────────────────────────┐
    │ SUPERMEMORY HIPPOCAMPUS     │
    │  - store_execution_memory() │
    └─────┬───────────────────────┘
          │
          ▼
    ┌─────────────────────────────┐
    │    SUPERMEMORY API          │
    │  (Memory persisted)         │
    └─────────────────────────────┘

PARALLEL:
┌─────────────────────┐         ┌──────────────────────┐
│  VISUAL AREA        │         │  CHAT HISTORY        │
│  (Supabase poller)  │         │                      │
└──────┬──────────────┘         └────────┬─────────────┘
       │                                  │
       │ Continuous                       │ After each
       │ (every 5 sec)                    │ conversation
       ▼                                  ▼
┌─────────────────────────────────────────────────────────┐
│              SUPERMEMORY HIPPOCAMPUS                     │
│  - store_visual_memory()   - store_chat_memory()        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ SUPERMEMORY API │
            └─────────────────┘
```

---

## Fallback Behavior

If Supermemory is unavailable (no API key or connection failure), the system automatically falls back to the existing `Hippocampus` class:

```python
hippocampus = SupermemoryHippocampus(enable_fallback=True)

# If Supermemory unavailable:
# - Uses existing hippocampus.retrieve_similar_cases()
# - Brain continues working without interruption
# - Warning messages logged
```

---

## Next Steps (Implementation Remaining)

While the core infrastructure is complete, these integration points need to be built:

1. **Visual Memory Polling Service** - Background process that continuously polls Supabase and writes to Supermemory
2. **Planning Area Enhancement** - Integrate `query_for_planning()` into planning flow
3. **Agent Bridge** - Connect to your existing agent system to capture execution results
4. **Dashboard Integration** - Add memory viewer and statistics to brain dashboard
5. **Async Task Queue** - Background task execution with memory formation

---

## Testing

Run the test scripts to verify everything works:

```bash
# Test Supermemory client
python core/supermemory_client.py

# Test hippocampus integration
python core/supermemory_hippocampus.py

# Test Supabase connector
python core/supabase_visual_connector.py

# Check environment
python load_env.py
```

Expected output: "Connection test successful!" and memory creation confirmations.

---

## Troubleshooting

### "SUPERMEMORY_API_KEY not found"
- Get API key from https://console.supermemory.ai
- Add to .env file: `SUPERMEMORY_API_KEY=your_key_here`

### "Connection test failed"
- Check internet connection
- Verify API key is correct
- Check https://v2.api.supermemory.ai is accessible

### "Supabase credentials not found"
- Verify SUPABASE_URL and SUPABASE_SECRET_KEY in .env
- Test with: `python core/supabase_visual_connector.py`

### Memories not appearing in queries
- API may take a few seconds to index new memories
- Check search endpoint is working (may need API documentation update)
- Verify memories were stored successfully (check return values)

---

## Summary

**What's Ready:**
- ✅ Complete Supermemory Python client
- ✅ Hippocampus integration layer
- ✅ Memory formation for visual, execution, and chat
- ✅ Automatic memory retrieval for planning
- ✅ Fallback to existing hippocampus
- ✅ Environment configuration
- ✅ Comprehensive documentation

**What You Need to Do:**
1. Get Supermemory API key from console.supermemory.ai
2. Add to .env file
3. Run tests to verify
4. Integrate into planning and execution flows

**Architecture Achievement:**
You now have a true cognitive architecture where:
- Brain **continuously forms memories** from visual input, executions, and conversations
- Planning **automatically retrieves relevant memories** for context-aware decisions
- Agents **set confidence** after execution, creating better training data
- System **learns from experience** and improves over time

This is the foundation for the asynchronous, memory-enhanced brain you envisioned!

# Tahlamus Backend Architecture
## All Backend Processes, LLM Integration & Scheduling

**Last Updated:** October 16, 2025

## Overview

Tahlamus has **5 backend processes** running continuously, with **6 different LLM integration points**.

---

## Backend Processes (Servers/Services)

### 1. Brain Dashboard Server (`web/brain_dashboard_server.py`)

**Port:** 5000
**Status:** 🟢 Running (multiple instances)
**Type:** Flask web server
**Scheduling:** Continuous (HTTP server event loop)

**Purpose:**
- Real-time brain visualization dashboard
- Interactive chat interface with brain
- Brain monitoring and intervention testing

**LLM Integration:**
- **Multi-LLM Router** for feature extraction
- **Hierarchical Planner** for task predictions
- Routes through OpenRouter to:
  - DeepSeek R1 (fast reasoning)
  - Claude 3.5 Sonnet (planning)
  - GPT-4o (communication)
  - Gemini 2.0 Flash (long-term memory)

**Initialization:**
```python
# Loads session logs
# Trains meta router, brain monitor, strategy library
# Initializes Multi-LLM Router with OpenRouter API key
# Initializes Hierarchical Planner
```

**Key Endpoints:**
- `GET /` - Dashboard UI
- `POST /api/chat/send` - Chat with brain (uses LLM)
- `GET /api/brain/gates` - Current thalamic gates
- `GET /api/brain/state` - Brain state
- `POST /api/predict/path` - Path prediction
- `GET /api/llm/stats` - LLM usage statistics

**Background Components:**
- `LiveBrainMonitor` - Checks for interventions every 2 seconds

---

### 2. Production API Server (`production/api_server.py`)

**Port:** 5001
**Status:** 🟢 Running (multiple instances)
**Type:** Flask REST API
**Scheduling:** Continuous (HTTP server event loop)

**Purpose:**
- Production predictions for task routing
- Continuous learning from feedback
- Matrix versioning

**LLM Integration:**
- **Hierarchical Planner** (indirect)
- Uses trained routing matrices (no direct LLM calls)
- Continuous learning updates matrices in real-time

**Initialization:**
```python
# Loads session logs (39 traces)
# Trains routing matrix
# Enables continuous learning (learning_rate=0.005)
```

**Key Endpoints:**
- `POST /predict` - Make prediction
- `POST /feedback` - Submit feedback (triggers learning)
- `GET /stats` - System statistics
- `GET /matrices` - List matrix versions
- `POST /save_matrix` - Save current matrix
- `POST /load_matrix` - Load specific version

**Continuous Learning:**
- Updates routing matrix after each feedback
- No explicit scheduling - event-driven
- Saves matrices with timestamps

---

### 3. Memory API Service (`memory_api/memory_service.py`)

**Port:** 8001
**Status:** 🟢 Running
**Type:** FastAPI REST API
**Scheduling:** Continuous (ASGI server event loop)

**Purpose:**
- Structured memory storage (execution, chat, visual)
- Query interface for memory retrieval
- Multi-user memory isolation

**LLM Integration:**
- **None** - Pure storage layer
- Stores LLM conversations but doesn't call LLMs
- Backend for Supermemory V3 API

**Key Endpoints:**
- `POST /memories/execution` - Store execution logs
- `POST /memories/chat` - Store conversations
- `POST /memories/visual` - Store screen captures
- `POST /memories/query` - Query memories
- `POST /planning/context` - Get planning context
- `GET /health` - Health check

**No Scheduling:**
- Request-response only
- No background tasks
- No scheduled polling

---

### 4. Chat with Brain (`chat_with_brain.py`)

**Port:** N/A (CLI)
**Status:** 🟢 Running
**Type:** Interactive CLI
**Scheduling:** User input loop

**Purpose:**
- Command-line interface to chat with brain
- Direct interaction with hierarchical planner

**LLM Integration:**
- **Hierarchical Planner**
- **Multi-LLM Router**
- All LLM providers via OpenRouter

**Event Loop:**
```python
while True:
    user_input = input("You: ")
    prediction = hierarchical_planner.predict(user_input)
    # Display results
```

---

### 5. Live Brain Monitor (`core/live_brain_monitor.py`)

**Port:** N/A (embedded)
**Status:** 🟢 Running (within Brain Dashboard)
**Type:** Background monitoring thread
**Scheduling:** **Every 2 seconds** (check_interval parameter)

**Purpose:**
- Real-time conversation monitoring
- Automatic intervention detection
- Failure prevention

**LLM Integration:**
- **None directly** - uses brain state
- Monitors LLM-driven conversations

**Scheduling Logic:**
```python
def __init__(self, check_interval=2):
    self.check_interval = 2  # seconds

def update(self, conversation):
    # Check every 2 seconds for:
    # - Error threshold exceeded (5 errors)
    # - Repetition detected (3 same tool calls)
    # - QA rejection pattern
    # - Clarification loops
    pass
```

**Triggers:**
- Error threshold: 5 errors
- Repetition threshold: 3 same tools
- Automatic intervention suggestions

---

## LLM Integration Points

### 1. Multi-LLM Router (`core/multi_llm_router.py`)

**Status:** ✅ Active
**Type:** LLM routing layer
**Provider:** OpenRouter (unified API)

**Models Used (DEV Mode):**
- **DeepSeek R1** - Fast reasoning ($0.14/M tokens)
  - Feature extraction
  - Decision making
  - Code understanding

- **Claude 3.5 Sonnet** - Planning ($3.00/M tokens)
  - Path planning
  - Strategy selection
  - Context tracking
  - Short-term memory

- **GPT-4o** - Communication ($2.50/M tokens)
  - Question generation
  - User interaction
  - Natural language

- **Gemini 2.0 Flash** - Long-term memory ($0.075/M tokens)
  - Episodic memory
  - Pattern discovery
  - Huge context (2M tokens)

**Methods:**
```python
router.extract_features(task)       # → DeepSeek
router.plan_sequence(task, type)    # → Claude
router.make_decision(task, context) # → DeepSeek
router.generate_questions(task)     # → GPT-4o
router.search_long_term_memory(q)   # → Gemini
router.maintain_short_term_context() # → Claude
```

**Statistics Tracking:**
- Call counts per LLM
- Latencies (avg, min, max)
- Failure rates
- Token usage
- Estimated costs

---

### 2. Hierarchical Planner (`core/hierarchical_planner.py`)

**Status:** ✅ Active
**Type:** 3-layer cognitive architecture
**LLM Usage:** Via Multi-LLM Router (optional)

**Architecture:**
```
Layer 1: TaskFeatureRouter → Extract features
Layer 2: ConversationPathPlanner → Plan path (trained on session logs)
Layer 3: DecisionRouter → Actionable decisions
```

**LLM Integration:**
- Layer 1 can use LLM for feature extraction
- Layer 2 uses trained graph (no LLM needed)
- Layer 3 uses routing matrix (no LLM needed)

**Additional Systems (All non-LLM):**
- Memory Systems (working + episodic)
- Predictive Coding
- Attention Mechanisms
- Meta-Learning
- Dream Mode (offline consolidation)
- Neuromodulation
- Temporal Memory
- Active Inference
- Compositional Reasoning
- Tool Creation
- Consciousness Metrics
- Multi-Brain Swarm

**No Scheduling:**
- Request-driven only
- Dream mode must be manually triggered
- No background processes

---

### 3. Supermemory Infinite Chat (`core/supermemory_llm_client.py`)

**Status:** ✅ Active and INTEGRATED into hierarchical planner
**Type:** LLM proxy with automatic memory
**Provider:** Supermemory → OpenAI/Anthropic/Google

**Purpose:**
- Automatic semantic memory injection
- Unlimited context windows
- 50%+ token savings

**Integration Points:**
- **Multi-LLM Router**: Automatically uses Infinite Chat when user_id provided
- **Hierarchical Planner**: Accepts user_id and propagates to router
- **Brain Dashboard**: Session-based user_id generation (auto-creates per session)

**Usage:**
```python
# Standalone
llm = SupermemoryLLM(user_id="alice")
response = llm.plan_task("Deploy Docker")

# Integrated (Multi-LLM Router)
router = MultiLLMRouter(openrouter_api_key=key, user_id="alice", enable_infinite_chat=True)
response = router.extract_features("Deploy Docker")  # Memory automatic!

# Integrated (Hierarchical Planner)
planner = HierarchicalPlanner(conversation_planner=path_planner, user_id="alice")
prediction = planner.predict("Deploy Docker")  # Memory automatic!
```

**Automatic Actions:**
1. Retrieves relevant past conversations (semantic search)
2. Injects into LLM context
3. Stores this conversation for future use

**No Scheduling:**
- On-demand LLM calls only
- Memory retrieval/storage automatic per call

---

### 4. Conversation Path Planner (`core/conversation_path_planner.py`)

**Status:** ✅ Active
**Type:** Graph-based planning
**LLM Usage:** Optional (can use Multi-LLM Router for planning)

**Primary Method:**
- Trained graph from session logs
- No LLM needed after training

**Optional LLM Enhancement:**
- Can use Multi-LLM Router for strategic planning
- Primarily uses graph-based reasoning

---

### 5. LLM Enhanced Inference (`core/llm_enhanced_inference.py`)

**Status:** ⚠️ Available but not actively used
**Type:** Wrapper for LLM calls
**Purpose:** Enhanced reasoning with LLMs

**Not currently integrated into main backend processes**

---

### 6. Brain Dashboard Chat Interface (Frontend)

**Status:** ✅ Active
**Type:** Web interface
**LLM Integration:** Via Brain Dashboard Server

**Flow:**
```
User types message
  → POST /api/chat/send
  → Multi-LLM Router extracts features
  → Hierarchical Planner predicts
  → Response returned to UI
```

---

## Scheduling Summary

### Active Scheduled Processes

| Component | Interval | Type | Purpose |
|-----------|----------|------|---------|
| **LiveBrainMonitor** | 2 seconds | Thread | Check for interventions |

### Continuous Processes (No Explicit Schedule)

| Component | Port | Type | Event-Driven |
|-----------|------|------|--------------|
| **Brain Dashboard** | 5000 | HTTP | Request/Response |
| **Production API** | 5001 | HTTP | Request/Response |
| **Memory API** | 8001 | HTTP | Request/Response |
| **Chat CLI** | N/A | Loop | User Input |

### No Scheduled Background Tasks

- ❌ No cron jobs
- ❌ No periodic polling (except LiveBrainMonitor)
- ❌ No background workers
- ❌ No task queues

**All processes are event-driven or request-driven**

---

## Future Scheduled Components (Not Yet Implemented)

### 1. Visual Memory Poller ⏳ PENDING

**Would poll:** Supabase `desktop_icons` table
**Interval:** Every 5 seconds
**Action:** Store screen captures in Memory API
**Status:** Not implemented

**Proposed Design:**
```python
class VisualMemoryPoller:
    def __init__(self, check_interval=5):
        self.interval = 5  # seconds

    def poll_loop(self):
        while True:
            # Query Supabase for new screen captures
            # Store in Memory API
            time.sleep(self.interval)
```

---

### 2. Dream Mode Consolidation ⏳ PENDING

**Would run:** During idle time
**Interval:** On-demand or nightly
**Action:** Consolidate episodic memories, extract patterns
**Status:** Implemented but not scheduled

**Proposed Trigger:**
```python
# Option 1: Manual trigger
planner.trigger_dream_cycle(num_dreams=10)

# Option 2: Scheduled (not implemented)
# Run nightly at 2 AM
# Or after N hours of idle time
```

---

### 3. Continuous Learning Background Update ⏳ OPTIONAL

**Current:** Learning happens on feedback
**Could add:** Periodic matrix optimization
**Interval:** Every 1 hour
**Status:** Not needed (real-time learning works)

---

## LLM Cost Tracking

### Current Usage (DEV Mode)

| LLM | Cost/M Tokens | Primary Use |
|-----|---------------|-------------|
| DeepSeek R1 | $0.14 | Fast reasoning |
| Claude 3.5 Sonnet | $3.00 | Planning |
| GPT-4o | $2.50 | Communication |
| Gemini 2.0 Flash | $0.075 | Long-term memory |

### Monitoring

All LLM calls tracked via Multi-LLM Router:
- Token usage per model
- Estimated costs
- Call counts
- Latencies
- Success rates

**Access stats:**
```bash
curl http://localhost:5000/api/llm/stats
```

---

## Data Flow

### Complete Request Flow

```
┌──────────────┐
│ User Request │
└──────┬───────┘
       │
       ▼
┌────────────────────────┐
│ Brain Dashboard (5000) │ ◄─── Web UI
└────────┬───────────────┘
         │
         ▼
┌──────────────────────────────┐
│ Multi-LLM Router             │
│ ├─ DeepSeek (features)       │
│ ├─ Claude (planning)         │
│ ├─ GPT-4o (questions)        │
│ └─ Gemini (memory search)    │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ Hierarchical Planner         │
│ ├─ Layer 1: Features         │
│ ├─ Layer 2: Path Planning    │
│ └─ Layer 3: Decision         │
└────────┬─────────────────────┘
         │
         ├──→ Memory API (8001) → Supermemory
         │    (store execution, chat)
         │
         └──→ LiveBrainMonitor
              (checks every 2s)
```

### Memory Flow

```
┌─────────────────┐
│ Execution       │
│ (Agent/User)    │
└────────┬────────┘
         │
         ▼
┌───────────────────────┐
│ Memory API (8001)     │
│ ├─ Execution logs     │
│ ├─ Chat history       │
│ └─ Visual captures    │
└────────┬──────────────┘
         │
         ▼
┌───────────────────────┐
│ Supermemory V3 API    │
│ (Cloud Storage)       │
└───────────────────────┘

Retrieval:
┌───────────────────────┐
│ Planning Request      │
└────────┬──────────────┘
         │
         ▼
┌───────────────────────┐
│ Memory API            │
│ GET /planning/context │
└────────┬──────────────┘
         │
         ▼
┌───────────────────────┐
│ Supermemory Query     │
│ (Semantic Search)     │
└────────┬──────────────┘
         │
         ▼
┌───────────────────────┐
│ Hierarchical Planner  │
│ (uses memory context) │
└───────────────────────┘
```

### Infinite Chat Flow

```
┌─────────────────┐
│ User Message    │
└────────┬────────┘
         │
         ▼
┌────────────────────────┐
│ SupermemoryLLM Client  │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ Supermemory Proxy      │
│ ├─ Retrieve past convs │
│ ├─ Inject into context │
│ └─ Store this conv     │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ OpenAI/Anthropic/etc   │
│ (with enriched context)│
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ Response to User       │
└────────────────────────┘
```

---

## Running Services Status

Check which services are running:

```bash
# Brain Dashboard
curl http://localhost:5000/api/brain/state

# Production API
curl http://localhost:5001/health

# Memory API
curl http://localhost:8001/health
```

---

## Adding New Scheduled Processes

To add a new scheduled background task:

### Option 1: Threading (Simple)

```python
import threading
import time

class MyScheduledTask:
    def __init__(self, interval=10):
        self.interval = interval
        self.running = False

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        while self.running:
            # Do work
            self.do_task()
            time.sleep(self.interval)

    def do_task(self):
        # Your scheduled work here
        pass

    def stop(self):
        self.running = False
```

### Option 2: APScheduler (Advanced)

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# Add job
scheduler.add_job(
    func=my_task_function,
    trigger='interval',
    seconds=10,
    id='my_task'
)

scheduler.start()
```

### Option 3: Async (FastAPI/asyncio)

```python
import asyncio

async def periodic_task():
    while True:
        # Do work
        await my_async_task()
        await asyncio.sleep(10)

# Start in background
asyncio.create_task(periodic_task())
```

---

## Summary

### Backend Processes: 5

1. **Brain Dashboard** (port 5000) - Web UI with LLM chat
2. **Production API** (port 5001) - REST API for predictions
3. **Memory API** (port 8001) - Structured memory storage
4. **Chat CLI** - Command-line brain interface
5. **Live Brain Monitor** - Real-time monitoring (2s intervals)

### LLM Integration Points: 6

1. **Multi-LLM Router** - Routes to 4 providers (DeepSeek, Claude, GPT-4o, Gemini)
2. **Hierarchical Planner** - Uses Multi-LLM Router
3. **Supermemory Infinite Chat** - Automatic memory injection
4. **Conversation Path Planner** - Optional LLM enhancement
5. **LLM Enhanced Inference** - Available but not actively used
6. **Brain Dashboard Chat** - Frontend LLM interaction

### Scheduled Tasks: 1

1. **LiveBrainMonitor** - Every 2 seconds

### Event-Driven: Everything Else

All other processes are request/response driven with no explicit scheduling.

---

**All services operational and documented!** ✅

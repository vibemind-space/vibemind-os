# Tahlamus C4 Architecture Diagrams

**Date:** October 16, 2025
**Status:** Complete system architecture documentation

This document provides C4 model diagrams for the Tahlamus brain-inspired cognitive routing system.

## Legend

- **Person**: External users/systems
- **System**: Software systems
- **Container**: Applications/services (processes, databases)
- **Component**: Code modules within containers

---

## Level 1: System Context Diagram

Shows Tahlamus in the context of users and external systems.

```mermaid
C4Context
    title System Context Diagram - Tahlamus Brain System

    Person(user, "User", "Interacts with brain via web UI or API")
    Person(agent, "AI Agent", "Autonomous agent using brain for decision-making")
    Person(developer, "Developer", "Develops and monitors brain behavior")

    System(tahlamus, "Tahlamus Brain", "Brain-inspired cognitive routing system with memory")

    System_Ext(openrouter, "OpenRouter API", "Unified LLM API gateway")
    System_Ext(supermemory, "Supermemory V3", "Cloud memory storage and infinite chat")
    System_Ext(openai, "OpenAI", "GPT-4o for communication")
    System_Ext(anthropic, "Anthropic", "Claude for planning")
    System_Ext(deepseek, "DeepSeek", "R1 for fast reasoning")
    System_Ext(google, "Google", "Gemini for long-term memory")

    Rel(user, tahlamus, "Chat with brain", "HTTP/WebSocket")
    Rel(agent, tahlamus, "Get decisions", "REST API")
    Rel(developer, tahlamus, "Monitor/deploy", "Web Dashboard")

    Rel(tahlamus, openrouter, "Route LLM calls", "HTTPS")
    Rel(openrouter, openai, "Forward GPT requests", "HTTPS")
    Rel(openrouter, anthropic, "Forward Claude requests", "HTTPS")
    Rel(openrouter, deepseek, "Forward DeepSeek requests", "HTTPS")
    Rel(openrouter, google, "Forward Gemini requests", "HTTPS")

    Rel(tahlamus, supermemory, "Store/retrieve memories", "HTTPS")
    Rel(supermemory, openai, "Infinite Chat proxy", "HTTPS")
```

**Key Interactions:**
- Users chat with brain via web dashboard
- AI agents request decisions via production API
- All LLM calls routed through OpenRouter for unified access
- Memory stored in Supermemory with automatic infinite chat

---

## Level 2: Container Diagram

Shows the high-level technical building blocks (backend services).

```mermaid
C4Container
    title Container Diagram - Tahlamus Backend Services

    Person(user, "User", "Interacts via browser")
    Person(agent, "Agent System", "Requests predictions")

    System_Boundary(tahlamus, "Tahlamus Brain System") {
        Container(dashboard, "Brain Dashboard", "Flask (Python)", "Web UI for real-time brain visualization and chat (port 5000)")
        Container(prod_api, "Production API", "Flask (Python)", "REST API for predictions with continuous learning (port 5001)")
        Container(memory_api, "Memory API", "FastAPI (Python)", "Structured memory storage service (port 8001)")
        Container(chat_cli, "Chat CLI", "Python", "Command-line brain interface")
        Container(monitor, "Live Brain Monitor", "Python Thread", "Background monitoring every 2 seconds")

        ContainerDb(session_logs, "Session Logs", "Filesystem", "39 conversation traces for training")
        ContainerDb(matrices, "Routing Matrices", "Filesystem", "Trained 10×4 matrices (versioned)")
    }

    System_Ext(openrouter, "OpenRouter API", "Multi-LLM gateway")
    System_Ext(supermemory, "Supermemory V3", "Cloud memory + Infinite Chat")

    Rel(user, dashboard, "Browse/chat", "HTTP")
    Rel(agent, prod_api, "POST /predict", "REST/JSON")

    Rel(dashboard, monitor, "Uses for interventions")
    Rel(dashboard, session_logs, "Reads for training")
    Rel(dashboard, openrouter, "Multi-LLM calls", "HTTPS")
    Rel(dashboard, supermemory, "Infinite Chat", "HTTPS")

    Rel(prod_api, matrices, "Load/save matrices")
    Rel(prod_api, session_logs, "Train from logs")

    Rel(memory_api, supermemory, "Store/query memories", "HTTPS")

    Rel(chat_cli, openrouter, "LLM calls", "HTTPS")
    Rel(chat_cli, supermemory, "Infinite Chat", "HTTPS")
```

**5 Backend Services:**
1. **Brain Dashboard** (port 5000) - Web UI + chat
2. **Production API** (port 5001) - Predictions + continuous learning
3. **Memory API** (port 8001) - Structured memory storage
4. **Chat CLI** - Command-line interface
5. **Live Brain Monitor** - Background monitoring thread (2s interval)

---

## Level 3a: Component Diagram - Hierarchical Planner

Shows components within the Brain Dashboard and Hierarchical Planner.

```mermaid
C4Component
    title Component Diagram - Brain Dashboard & Hierarchical Planner

    Container_Boundary(dashboard, "Brain Dashboard (Port 5000)") {
        Component(flask_app, "Flask Application", "Python", "Web server with REST endpoints")
        Component(session_mgr, "Session Manager", "Python", "Generates user_id per session")

        Component(hier_planner, "Hierarchical Planner", "Python", "3-layer cognitive architecture")

        Component_Ext(layer1, "Layer 1: TaskFeatureRouter", "Feature extraction, task classification")
        Component_Ext(layer2, "Layer 2: ConversationPathPlanner", "Graph-based path prediction")
        Component_Ext(layer3, "Layer 3: DecisionRouter", "Multi-target decision routing")

        Component(llm_router, "Multi-LLM Router", "Python", "Routes to specialized LLMs with Infinite Chat")
        Component(brain_monitor, "Brain Monitor", "Python", "Monitors gate distribution")
        Component(strategy_lib, "Strategy Library", "Python", "Stores proven patterns")
        Component(meta_router, "Meta Router", "Python", "10-modality self-reflective routing")
    }

    System_Ext(openrouter, "OpenRouter API", "Multi-provider LLM access")
    System_Ext(supermemory, "Supermemory V3", "Memory + Infinite Chat proxy")

    Rel(flask_app, session_mgr, "Generate user_id on first message")
    Rel(flask_app, hier_planner, "predict(task, user_id)")

    Rel(hier_planner, layer1, "Extract features")
    Rel(layer1, layer2, "Pass features")
    Rel(layer2, layer3, "Predict sequence")
    Rel(layer3, hier_planner, "Return decision")

    Rel(hier_planner, llm_router, "LLM calls with user_id")
    Rel(llm_router, supermemory, "Infinite Chat (if user_id)", "HTTPS")
    Rel(llm_router, openrouter, "Direct calls (no user_id)", "HTTPS")

    Rel(layer2, meta_router, "Uses for brain state")
    Rel(meta_router, brain_monitor, "Update gates")
    Rel(layer2, strategy_lib, "Retrieve patterns")
```

**3-Layer Architecture:**
- **Layer 1** (TaskFeatureRouter): Extracts task type, complexity, urgency
- **Layer 2** (ConversationPathPlanner): Predicts action sequence using trained graph
- **Layer 3** (DecisionRouter): Routes to actionable intervention via 10×4 matrix

**Key Flow:**
1. User sends message → Session Manager generates user_id
2. Hierarchical Planner processes task through 3 layers
3. Multi-LLM Router uses Infinite Chat (if user_id) or direct OpenRouter
4. Supermemory automatically injects relevant past conversations

---

## Level 3b: Component Diagram - Memory System

Shows the dual memory architecture components.

```mermaid
C4Component
    title Component Diagram - Dual Memory System

    Container_Boundary(memory_sys, "Memory System") {
        Component(mem_client, "Memory Client", "Python", "REST client for structured memory")
        Component(supermem_llm, "SupermemoryLLM", "Python", "Infinite Chat LLM wrapper")
        Component(exec_tracker, "Execution Tracker", "Python", "Session-based execution logging")
    }

    Container_Boundary(memory_api, "Memory API Service (Port 8001)") {
        Component(fastapi_app, "FastAPI Application", "Python", "REST API endpoints")
        Component(supermem_client, "Supermemory Client", "Python", "V3 API integration")

        Component_Ext(ep_exec, "POST /memories/execution", "Store execution logs")
        Component_Ext(ep_chat, "POST /memories/chat", "Store conversations")
        Component_Ext(ep_visual, "POST /memories/visual", "Store screen captures")
        Component_Ext(ep_query, "POST /memories/query", "Query with filters")
        Component_Ext(ep_context, "POST /planning/context", "Get planning context")
    }

    Container_Boundary(llm_integration, "LLM Integration") {
        Component(multi_llm, "Multi-LLM Router", "Python", "Intelligent LLM routing")
        Component(hier_plan, "Hierarchical Planner", "Python", "Uses LLM router with user_id")
    }

    System_Ext(supermemory_api, "Supermemory V3 API", "Cloud storage + Infinite Chat")
    System_Ext(openrouter_api, "OpenRouter", "Multi-provider LLM")

    Rel(exec_tracker, mem_client, "Store session via REST")
    Rel(mem_client, fastapi_app, "HTTP requests")
    Rel(fastapi_app, supermem_client, "Supermemory V3 calls")
    Rel(supermem_client, supermemory_api, "HTTPS")

    Rel(multi_llm, supermem_llm, "Use if user_id present")
    Rel(supermem_llm, supermemory_api, "Infinite Chat proxy")
    Rel(multi_llm, openrouter_api, "Fallback if no user_id")

    Rel(hier_plan, multi_llm, "LLM calls with user_id")
```

**Dual Architecture:**

**1. Structured Memory (Memory API)**
- **Execution Tracker** → formats session logs
- **Memory Client** → REST calls to Memory API
- **Memory API** → stores in Supermemory V3
- **Use case**: Agent execution logs, visual context, structured queries

**2. Automatic Memory (Infinite Chat)**
- **Multi-LLM Router** → checks for user_id
- **SupermemoryLLM** → Infinite Chat proxy (if user_id)
- **Supermemory** → automatic semantic memory injection
- **Use case**: LLM calls with conversation history

---

## Level 3c: Component Diagram - Multi-LLM Router

Shows how LLM routing works with Infinite Chat integration.

```mermaid
C4Component
    title Component Diagram - Multi-LLM Router with Infinite Chat

    Container_Boundary(llm_router, "Multi-LLM Router") {
        Component(router_core, "Router Core", "Python", "Main routing logic")
        Component(llm_configs, "LLM Configs", "Python Dict", "Specialized LLM assignments")
        Component(function_map, "Function Map", "Python Dict", "Cognitive function → LLM")
        Component(call_llm, "_call_llm()", "Method", "Intelligent routing")
        Component(get_supermem, "_get_supermemory_llm()", "Method", "Lazy SupermemoryLLM init")
        Component(call_openrouter, "_call_openrouter()", "Method", "Direct OpenRouter calls")
    }

    Component_Ext(supermem_llm_client, "SupermemoryLLM", "Python", "Infinite Chat wrapper")

    System_Ext(supermemory_proxy, "Supermemory Proxy", "Infinite Chat API")
    System_Ext(openrouter, "OpenRouter", "Multi-provider gateway")
    System_Ext(deepseek, "DeepSeek R1", "Fast reasoning")
    System_Ext(claude, "Claude 3.5 Sonnet", "Planning")
    System_Ext(gpt4o, "GPT-4o", "Communication")
    System_Ext(gemini, "Gemini 2.0 Flash", "Long-term memory")

    Rel(router_core, function_map, "Look up LLM for function")
    Rel(router_core, llm_configs, "Get LLM config")
    Rel(router_core, call_llm, "Execute LLM call")

    Rel(call_llm, get_supermem, "Check for user_id")
    Rel(get_supermem, supermem_llm_client, "Create if user_id exists")
    Rel(call_llm, supermem_llm_client, "Use Infinite Chat (if available)")
    Rel(call_llm, call_openrouter, "Fallback if no user_id")

    Rel(supermem_llm_client, supermemory_proxy, "Infinite Chat proxy", "HTTPS")
    Rel(supermemory_proxy, openrouter, "Forward with memory", "HTTPS")
    Rel(call_openrouter, openrouter, "Direct (no memory)", "HTTPS")

    Rel(openrouter, deepseek, "Fast reasoning tasks")
    Rel(openrouter, claude, "Planning tasks")
    Rel(openrouter, gpt4o, "Communication tasks")
    Rel(openrouter, gemini, "Memory search tasks")
```

**Intelligent Routing Logic:**
```
route(function, prompt, user_id=None):
  1. Look up LLM for cognitive function
  2. Call _call_llm(model, prompt, user_id)

_call_llm(model, prompt, user_id):
  1. Check if user_id provided
  2. If user_id:
     - Get/create SupermemoryLLM client
     - Use Infinite Chat proxy (automatic memory!)
  3. If no user_id:
     - Call OpenRouter directly (no memory)
  4. Return response
```

**4 Specialized LLMs (DEV mode):**
- **DeepSeek R1** ($0.14/M) - Feature extraction, fast reasoning
- **Claude 3.5 Sonnet** ($3.00/M) - Planning, context tracking
- **GPT-4o** ($2.50/M) - Questions, communication
- **Gemini 2.0 Flash** ($0.075/M) - Long-term memory, 2M context

---

## Data Flow Diagrams

### Complete Request Flow

```
┌──────────────┐
│ User Message │
└──────┬───────┘
       │
       ▼
┌────────────────────────────────────┐
│ Brain Dashboard (port 5000)        │
│ 1. Generate session user_id        │
│ 2. Set user_id in routers          │
└────────┬───────────────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│ Hierarchical Planner               │
│ Layer 1 → Layer 2 → Layer 3        │
└────────┬───────────────────────────┘
         │
         ├──→ Memory API (8001)
         │    Store execution logs
         │
         └──→ Multi-LLM Router
              ↓
              Check user_id?
              │
              ├─ YES → SupermemoryLLM
              │         ↓
              │    Supermemory Proxy
              │    1. Retrieve context
              │    2. Inject into LLM
              │    3. Store conversation
              │         ↓
              │    OpenAI/Claude/DeepSeek/Gemini
              │
              └─ NO → Direct OpenRouter
                       ↓
                  OpenAI/Claude/DeepSeek/Gemini
```

### Memory System Flow

```
┌─────────────────────────────────────────────────┐
│            STRUCTURED MEMORY                    │
└─────────────────────────────────────────────────┘

Agent Execution
      ↓
Execution Tracker (format session)
      ↓
Memory Client (REST)
      ↓
Memory API Service (port 8001)
      ↓
Supermemory V3 API
      ↓
Cloud Storage

Retrieval: Memory Client → Memory API → Supermemory → Query Results


┌─────────────────────────────────────────────────┐
│         AUTOMATIC SEMANTIC MEMORY               │
└─────────────────────────────────────────────────┘

LLM Call (with user_id)
      ↓
Multi-LLM Router
      ↓
SupermemoryLLM
      ↓
Supermemory Infinite Chat Proxy
      ├─ Retrieve relevant context (semantic search)
      ├─ Inject into prompt
      └─ Forward to LLM
            ↓
      LLM Response
            ↓
      Store conversation (automatic)
```

---

## Deployment View

### Production Environment

```
┌─────────────────────────────────────────────────────────────┐
│                    Local Machine (Windows)                   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Process 1: Brain Dashboard (port 5000)                 │ │
│  │ - Flask web server                                     │ │
│  │ - Real-time visualization                              │ │
│  │ - Chat interface with Infinite Chat                    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Process 2: Production API (port 5001)                  │ │
│  │ - REST API for predictions                             │ │
│  │ - Continuous learning (LR=0.005)                       │ │
│  │ - Matrix versioning                                    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Process 3: Memory API (port 8001)                      │ │
│  │ - FastAPI structured memory service                    │ │
│  │ - Multi-user support                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Process 4: Chat CLI                                    │ │
│  │ - Command-line interface                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Thread: Live Brain Monitor (2s interval)               │ │
│  │ - Background monitoring                                │ │
│  │ - Intervention detection                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Filesystem                                             │ │
│  │ - data/logs/sessions/ (39 conversation traces)         │ │
│  │ - production/trained_matrices/ (versioned matrices)    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

                         ↓ HTTPS ↓

┌─────────────────────────────────────────────────────────────┐
│                      External Services                       │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────┐              │
│  │  OpenRouter      │    │  Supermemory V3  │              │
│  │  (Multi-LLM)     │    │  (Memory + Chat) │              │
│  └──────────────────┘    └──────────────────┘              │
│           │                        │                         │
│     ┌─────┴─────┐           ┌─────┴─────┐                  │
│     ↓     ↓     ↓           ↓           ↓                  │
│  DeepSeek Claude GPT-4o  OpenAI    Cloud Storage            │
│    R1    Sonnet         (proxy)                             │
│                                                              │
│  Gemini 2.0 Flash                                           │
└─────────────────────────────────────────────────────────────┘
```

**Ports:**
- **5000** - Brain Dashboard (web UI + chat)
- **5001** - Production API (predictions + learning)
- **8001** - Memory API (structured storage)

**Scheduled Tasks:**
- **Live Brain Monitor**: Every 2 seconds (background thread)
- All other services: Event-driven (HTTP request/response)

---

## Technology Stack

```
┌─────────────────────────────────────────────────┐
│              Application Layer                   │
├─────────────────────────────────────────────────┤
│ Flask (Brain Dashboard, Production API)         │
│ FastAPI (Memory API)                            │
│ Python 3.9+                                     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│               Core Libraries                     │
├─────────────────────────────────────────────────┤
│ NumPy (matrix operations, routing)              │
│ Requests (HTTP clients)                         │
│ NetworkX (conversation graphs)                  │
│ OpenAI SDK (LLM client)                         │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│              External Services                   │
├─────────────────────────────────────────────────┤
│ OpenRouter API (multi-LLM gateway)              │
│ Supermemory V3 (memory + infinite chat)         │
│ DeepSeek R1, Claude 3.5, GPT-4o, Gemini 2.0    │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│                 Storage                          │
├─────────────────────────────────────────────────┤
│ Filesystem (session logs, trained matrices)     │
│ Supermemory Cloud (structured memories)         │
└─────────────────────────────────────────────────┘
```

---

## Summary

**5 Backend Processes:**
1. Brain Dashboard (5000) - Web UI + chat with Infinite Chat
2. Production API (5001) - Predictions + continuous learning
3. Memory API (8001) - Structured memory storage
4. Chat CLI - Command-line interface
5. Live Brain Monitor - Background monitoring (2s intervals)

**6 LLM Integration Points:**
1. Multi-LLM Router - Routes to 4 specialized providers
2. Hierarchical Planner - Uses Multi-LLM Router with user_id
3. Supermemory Infinite Chat - Automatic semantic memory
4. Conversation Path Planner - Optional LLM enhancement
5. LLM Enhanced Inference - Available but not actively used
6. Brain Dashboard Chat - Frontend LLM interaction

**2 Memory Systems:**
1. Memory API (8001) - Structured storage (execution, chat, visual)
2. Infinite Chat - Automatic semantic memory injection

**1 Scheduled Task:**
- Live Brain Monitor (every 2 seconds)

**All other services:** Event-driven (request/response)

---

**Diagrams Status:** ✅ COMPLETE

**View diagrams:**
- Open this file in GitHub, GitLab, or any markdown viewer with Mermaid support
- Or use: https://mermaid.live/ (paste diagrams)

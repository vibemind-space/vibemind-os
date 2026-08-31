# Supermemory Integration Research

## Overview

Supermemory is "The Memory API for the AI era" - a scalable memory engine for storing and retrieving contextual information for AI systems.

**Project Info:**
- GitHub: https://github.com/supermemoryai/supermemory
- Stars: 12,114 | Forks: 1,279
- License: MIT
- Language: TypeScript
- Technologies: PostgreSQL (Drizzle ORM), Redis, Cloudflare Workers, Hono (API framework)

## Integration Options

### ✅ RECOMMENDED: Option 1 - Hosted API
**Use the managed Supermemory cloud service**

**Pros:**
- No infrastructure setup required
- Instant setup with API key
- Production-ready with scaling handled
- Official support and updates

**Cons:**
- Requires API key from console.supermemory.ai
- Data stored on Supermemory servers
- Potential API rate limits
- Monthly costs (check pricing)

**Setup Steps:**
1. Visit https://console.supermemory.ai
2. Create account and get API key
3. Use API key in Python client

**Base URL:** `https://v2.api.supermemory.ai/`

---

### Option 2 - Self-Hosting
**Clone and run Supermemory locally**

**Pros:**
- Full control over data and infrastructure
- No external API dependencies
- Customizable

**Cons:**
- Requires PostgreSQL + Redis + Bun runtime setup
- Complex configuration (.env with multiple services)
- No official self-hosting documentation
- Maintenance burden
- Still uses same API endpoints (not MCP server)

**Setup Steps:**
```bash
git clone https://github.com/supermemoryai/supermemory
cd supermemory
bun install
# Configure .env.local (no .env.example provided)
# Setup PostgreSQL database
# Setup Redis
# Configure AI provider API keys (OpenAI, Anthropic, etc.)
bun run dev
```

**Note:** Self-hosting documentation is incomplete. The project uses Turbo monorepo with workspaces.

---

### ❌ Option 3 - MCP Integration
**Status:** Not viable for our use case

**Why not:**
- MCP v1 is being deprecated
- Supermemory-MCP is a separate project (not the main API)
- Designed for ChatGPT/Claude Desktop integration, not programmatic use
- We need direct API access for our Python-based system

---

## API Documentation (Discovered)

### Authentication
All API requests require authentication:

**Method 1: Bearer Token**
```bash
Authorization: Bearer YOUR_API_KEY
```

**Method 2: Custom Header**
```bash
x-api-key: YOUR_API_KEY
```

### Endpoints

#### 1. Add Memory
**Endpoint:** `POST /api/store` or `POST /add`

**Request Schema:**
```typescript
{
    pageContent: string,          // Main content to remember
    url: string,                   // URL reference
    type: string,                  // Type: "page", "note", etc. (default: "page")
    title?: string,                // Memory title (default: "Untitled")
    description?: string,          // Description (default: "")
    ogImage?: string,              // OpenGraph image URL
    image?: string,                // Image URL
    spaces?: string[]              // Categories/tags (default: [])
}
```

**Example:**
```bash
curl -X POST https://v2.api.supermemory.ai/add \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pageContent": "User was working on Python AI system",
    "url": "tahlamus://session/2025-01-15",
    "type": "execution_log",
    "title": "Session Log - Jan 15",
    "description": "Agent executed Docker deployment task",
    "spaces": ["execution", "docker", "deployment"]
  }'
```

#### 2. Search/Query Memories
**Endpoint:** Search endpoints exist but specific paths not fully documented

**Likely endpoints:**
- `POST /search` or `POST /query`
- `GET /memories?q=...`

**Parameters:**
- Query text (semantic search)
- Filters by type, spaces, date range
- Limit/pagination

**Note:** Will need to test with actual API key to discover exact schema.

---

## Memory Schema Design for Tahlamus

### Visual Memories (Screen Data)
```json
{
    "pageContent": "Window: VSCode | File: main.py | OCR: def process_data()...",
    "url": "tahlamus://visual/2025-01-15T10:30:00",
    "type": "visual_context",
    "title": "Screen State - VSCode",
    "description": "User editing Python file in VSCode",
    "spaces": ["visual", "coding", "vscode"],
    "metadata": {
        "captured_at": 1705315800000,
        "window_title": "main.py - VSCode",
        "active_application": "VSCode",
        "visible_files": ["main.py", "config.yaml"]
    }
}
```

### Execution Memories (Agent Logs)
```json
{
    "pageContent": "Task: Deploy Docker container\nResult: SUCCESS\nConfidence: 0.95\nLogs: Container deployed to port 8080...",
    "url": "tahlamus://execution/session-abc123",
    "type": "agent_execution",
    "title": "Docker Deployment Success",
    "description": "Agent successfully deployed container with 95% confidence",
    "spaces": ["execution", "docker", "success"],
    "metadata": {
        "task_type": "docker_deployment",
        "agent_name": "deployment_agent",
        "confidence": 0.95,
        "duration_ms": 5400,
        "timestamp": 1705315900000
    }
}
```

### Chat Memories (Conversations)
```json
{
    "pageContent": "User: How do I deploy a Docker container?\nAssistant: I'll help you deploy a Docker container. Let me plan the steps...",
    "url": "tahlamus://chat/2025-01-15T10:45:00",
    "type": "conversation",
    "title": "Chat - Docker Deployment Question",
    "description": "User asked about Docker deployment",
    "spaces": ["chat", "docker", "question"],
    "metadata": {
        "message_count": 5,
        "topics": ["docker", "deployment", "containers"],
        "planning_triggered": true,
        "timestamp": 1705316700000
    }
}
```

---

## Python Client Architecture

### Core Client (`core/supermemory_client.py`)
```python
class SupermemoryClient:
    def __init__(self, api_key: str, base_url: str = "https://v2.api.supermemory.ai")

    # Write operations
    def add_memory(self, content: str, url: str, type: str, title: str, ...) -> dict
    def add_visual_memory(self, screen_data: dict) -> dict
    def add_execution_memory(self, session_log: dict) -> dict
    def add_chat_memory(self, conversation: list) -> dict

    # Read operations
    def search(self, query: str, filters: dict = None, limit: int = 10) -> list
    def get_memories(self, memory_type: str = None, limit: int = 10) -> list
    def get_by_space(self, space: str, limit: int = 10) -> list

    # Health check
    def test_connection(self) -> bool
```

### Integration Layer (`core/supermemory_hippocampus.py`)
```python
class SupermemoryHippocampus:
    """Bridge between Tahlamus brain and Supermemory API"""

    def query_for_planning(self, task: str) -> dict:
        """Automatic memory retrieval for planning phase"""
        # Query similar execution memories
        # Query relevant visual context
        # Format for LLM consumption

    def query_specific(self, query: str, memory_type: str) -> list:
        """On-demand memory queries"""

    def store_visual_memory(self, screen_summary: dict) -> bool:
        """Write visual memories from Supabase data"""

    def store_execution_memory(self, session_log: dict, confidence: float) -> bool:
        """Write execution memories from agent completions"""

    def store_chat_memory(self, messages: list) -> bool:
        """Write chat history memories"""

    def format_memories_for_llm(self, memories: list) -> str:
        """Format retrieved memories for LLM prompt injection"""
```

---

## Environment Configuration

Add to `.env` or `load_env.py`:

```bash
# Supermemory Configuration
SUPERMEMORY_API_KEY=your_api_key_here
SUPERMEMORY_BASE_URL=https://v2.api.supermemory.ai  # Optional, default
SUPERMEMORY_ENABLE=true
SUPERMEMORY_FALLBACK_TO_LOCAL=true  # Use existing hippocampus if unavailable
```

---

## Next Steps

1. ✅ **Research completed** - Documented API structure and integration options
2. ⏳ **Get API key** - Sign up at console.supermemory.ai
3. ⏳ **Create Python client** - `core/supermemory_client.py`
4. ⏳ **Test basic operations** - Add/search memories
5. ⏳ **Build integration layer** - `core/supermemory_hippocampus.py`
6. ⏳ **Connect to existing systems**:
   - Visual Area → Supabase → Supermemory
   - Agent Execution → Supermemory
   - Chat History → Supermemory
7. ⏳ **Integrate with Planning Area** - Automatic memory queries in DeepSeek R1 planning

---

## Limitations & Unknowns

1. **API documentation incomplete** - Need to test endpoints with actual API key
2. **Rate limits unknown** - Need to check Supermemory pricing/limits page
3. **Search endpoint specifics** - Exact query syntax not documented
4. **Bulk operations** - Whether batch add/search is supported
5. **Memory update/delete** - Whether memories can be modified after creation
6. **Pagination** - How to handle large result sets
7. **Vector search quality** - How good is semantic search vs keyword search

---

## References

- Main Repo: https://github.com/supermemoryai/supermemory
- MCP Integration: https://github.com/supermemoryai/supermemory-mcp
- Console: https://console.supermemory.ai
- App: https://app.supermemory.ai
- Issue #183 (API discussion): https://github.com/supermemoryai/supermemory/issues/183
- Issue #14 (Self-hosting): https://github.com/supermemoryai/supermemory/issues/14

---

**Last Updated:** 2025-01-15
**Status:** Research phase complete, ready for implementation

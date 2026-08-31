# MCP Server Inventory

**Last Updated:** 2025-10-07
**Total Servers:** 24 (18 active, 6 inactive)

## Active MCP Servers (18)

All active servers have complete agent implementations with Society of Mind architecture.

### 1. **Playwright** - Browser Automation
- **Directory:** `playwright/`
- **Agent:** Browser_Operator + QA_Validator
- **Package:** `@playwright/mcp@latest`
- **Description:** Browser automation with Edge/Chrome, DOM interaction, screenshots

### 2. **GitHub** - Repository Management
- **Directory:** `github/`
- **Agent:** GitHub_Operator + QA_Validator
- **Package:** Docker container `ghcr.io/github/github-mcp-server`
- **Description:** Repository management, issues, PRs, code operations
- **Requires:** GITHUB_PERSONAL_ACCESS_TOKEN

### 3. **Docker** - Container Management
- **Directory:** `docker/`
- **Agent:** Docker_Operator + QA_Validator
- **Package:** `docker-mcp` (uvx)
- **Description:** Container operations, compose deployment, logs retrieval

### 4. **Desktop** - Terminal & System Control
- **Directory:** `desktop/`
- **Agent:** Desktop_Operator + QA_Validator
- **Package:** `@wonderwhy-er/desktop-commander@latest`
- **Description:** Terminal control, file system operations, process management

### 5. **Context7** - Code Documentation
- **Directory:** `context7/`
- **Agent:** Context7_Operator + QA_Validator
- **Package:** `@upstash/context7-mcp@latest`
- **Description:** Up-to-date code documentation and examples

### 6. **Redis** - Key-Value Store
- **Directory:** `redis/`
- **Agent:** Redis_Operator + QA_Validator
- **Package:** `@modelcontextprotocol/server-redis`
- **Description:** Key-value store operations, caching, vector search
- **Requires:** REDIS_URL

### 7. **Supabase** - PostgreSQL & BaaS
- **Directory:** `supabase/`
- **Agent:** Supabase_Operator + QA_Validator
- **Package:** `@supabase/mcp-server-supabase@latest`
- **Description:** PostgreSQL database, authentication, storage, real-time subscriptions

### 8. **Time** - Time Operations
- **Directory:** (Python module)
- **Agent:** Time_Operator + QA_Validator
- **Package:** `mcp_server_time` (Python)
- **Description:** Time operations, timezone conversions, scheduling

### 9. **TaskManager** - Task Tracking
- **Directory:** `taskmanager/`
- **Agent:** Task_Operator + QA_Validator
- **Package:** `@kazuph/mcp-taskmanager`
- **Description:** Task creation, tracking, and management with JSON storage

### 10. **Windows Core** - Windows System Tools
- **Directory:** `windows-core/`
- **Agent:** Windows_Operator + QA_Validator
- **Package:** Custom Python server
- **Description:** 25 essential tools for file operations, process management, system info

### 11. **Memory** - Knowledge Graph
- **Directory:** `memory/`
- **Agent:** Memory_Operator + QA_Validator
- **Package:** `@modelcontextprotocol/server-memory`
- **Description:** Knowledge graph management with entities and relations

### 12. **Filesystem** - File Operations
- **Directory:** `filesystem/`
- **Agent:** Filesystem_Operator + QA_Validator
- **Package:** `@modelcontextprotocol/server-filesystem`
- **Description:** File and directory operations with configurable allowed directories

### 13. **Brave Search** - Web Search
- **Directory:** `brave-search/`
- **Agent:** Search_Operator + QA_Validator
- **Package:** `@modelcontextprotocol/server-brave-search`
- **Description:** Privacy-focused web search with Brave API
- **Requires:** BRAVE_API_KEY

### 14. **Fetch** - HTTP Requests
- **Directory:** (No agent directory)
- **Agent:** Fetch_Operator + QA_Validator
- **Package:** `@modelcontextprotocol/server-fetch`
- **Description:** HTTP requests and web content retrieval

### 15. **YouTube** - Video Transcripts
- **Directory:** `youtube/`
- **Agent:** YouTube_Operator + QA_Validator
- **Package:** `youtube-transcript-mcp-server`
- **Description:** Video transcript and caption fetching

### 16. **n8n** - Workflow Automation
- **Directory:** `n8n/`
- **Agent:** N8N_Operator + QA_Validator
- **Package:** `n8n-mcp`
- **Description:** Workflow automation, node documentation, n8n API integration
- **Requires:** N8N_API_URL, N8N_API_KEY

### 17. **Sequential Thinking** - Problem Solving
- **Directory:** `sequential-thinking/`
- **Agent:** Thinker + QA_Validator
- **Package:** `@modelcontextprotocol/server-sequential-thinking`
- **Description:** Dynamic problem-solving through structured thought sequences

### 18. **Tavily** - Advanced Web Search
- **Directory:** `tavily/`
- **Agent:** Search_Operator + QA_Validator
- **Package:** `tavily-mcp@latest`
- **Description:** Real-time web search, data extraction, website mapping, web crawling
- **Requires:** TAVILY_API_KEY

---

## Inactive Servers (6)

These servers exist only as configuration entries in `servers.json`. They have no agent implementations.

### 1. **git** (Redundant)
- **Status:** Disabled - Using GitHub MCP instead
- **Package:** `@modelcontextprotocol/server-git`
- **Reason:** GitHub MCP provides more comprehensive functionality

### 2. **puppeteer** (Alternative)
- **Status:** Disabled - Using Playwright instead
- **Package:** `@modelcontextprotocol/server-puppeteer`
- **Reason:** Playwright is more actively maintained and feature-rich

### 3. **huggingface** (Package Not Found)
- **Status:** Inactive
- **Package:** `@modelcontextprotocol/server-huggingface`
- **Reason:** NPM package not found

### 4. **elevenlabs** (Package May Not Exist)
- **Status:** Inactive
- **Package:** `elevenlabs-mcp`
- **Reason:** NPM package may not exist

### 5. **mindsdb** (Package May Not Exist)
- **Status:** Inactive
- **Package:** `mindsdb-mcp-server`
- **Reason:** NPM package may not exist

### 6. **gpt-researcher** (Package May Not Exist)
- **Status:** Inactive
- **Package:** `gpt-researcher-mcp`
- **Reason:** NPM package may not exist

---

## Development Folder

**Location:** `dev/`

Contains experimental and archived MCP implementations:
- `mcp-gateway/` - Experimental gateway for routing MCP requests
- See [dev/README.md](dev/README.md) for details

---

## Architecture Overview

### Society of Mind Pattern

All active agents follow the Society of Mind architecture with specialized roles:

1. **Operator Agent** - Primary tool user with domain expertise
2. **QA_Validator** - Quality assurance and response validation
3. **User Interaction** - File-based polling for clarifications
4. **Event Streaming** - Real-time updates via Server-Sent Events

### Dynamic Discovery

The system automatically discovers new agents:
- Scans `src/MCP PLUGINS/servers/` for directories with `agent.py`
- Loads metadata from `servers.json`
- No manual configuration needed in `src/gui/config.py`

### Session Management

Centralized session lifecycle management via `MCPSessionManager`:
- Create → Spawn → Connect → Terminate → Delete
- PID tracking with platform-specific termination
- Dynamic event port discovery
- Per-session logging in `data/logs/sessions/`

---

## Adding New MCP Servers

1. Create directory: `src/MCP PLUGINS/servers/{server-name}/`
2. Implement files:
   - `agent.py` - Main agent with Society of Mind architecture
   - `constants.py` - Configuration and system prompts
   - `event_task.py` - Event server for real-time communication
   - `user_utils.py` - User interaction utilities
3. Add entry to `servers.json` with `"active": true`
4. System auto-discovers via dynamic detection

See existing agents for reference implementations.

---

## Configuration Files

- **servers.json** - Central registry of all MCP servers
- **secrets.json** - API keys and credentials (gitignored)
- **src/gui/config.py** - Dynamic agent discovery
- **src/ui/mcp_session_manager.py** - Session lifecycle management

---

## Testing

Test all agents: `python "src/MCP PLUGINS/servers/test_all_agents.py"`

Test specific agent: `python "src/MCP PLUGINS/servers/test_agents_execution.py"`

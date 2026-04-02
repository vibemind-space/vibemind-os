# Development & Experimental MCP Servers

This directory contains experimental, in-development, or archived MCP server implementations that are not currently active in production.

## Contents

### mcp-gateway
Experimental gateway for routing MCP requests across multiple servers.

**Original Purpose:** Testing the MCP_DOCKER Gateway for containerized MCP server execution through Docker's MCP gateway interface.

## Inactive Servers (Config-Only)

The following servers exist only as configuration entries in `servers.json` but have no agent implementations:

- **git** - Disabled (redundant with GitHub MCP which provides more comprehensive functionality)
- **puppeteer** - Disabled (using Playwright instead as it's more actively maintained)
- **huggingface** - Inactive (npm package `@modelcontextprotocol/server-huggingface` not found)
- **elevenlabs** - Inactive (npm package `elevenlabs-mcp` may not exist)
- **mindsdb** - Inactive (npm package `mindsdb-mcp-server` may not exist)
- **gpt-researcher** - Inactive (npm package `gpt-researcher-mcp` may not exist)

These inactive servers are marked with `"active": false` in servers.json and will not be loaded by the system.

---

## MCP_DOCKER Gateway (Archived)

### Gateway Purpose

The MCP_DOCKER Gateway allows running MCP servers through Docker's MCP gateway interface. This provides:
- Containerized MCP server execution
- Isolated environment for MCP operations
- Docker-based tool management

## Adding New MCP Servers

To add a new MCP server:

1. Create a new directory under `src/MCP PLUGINS/servers/{server-name}/`
2. Implement the required files:
   - `agent.py` - Main agent implementation with Society of Mind architecture
   - `constants.py` - Configuration and system prompts
   - `event_task.py` - Event server for real-time communication
   - `user_utils.py` - User interaction utilities (ask_user, clarification polling)
3. Add server entry to `servers.json` with `"active": true`
4. The system will auto-discover the agent via dynamic detection

See existing agents (playwright, github, docker, etc.) for reference implementations.

---

## Archived: MCP_DOCKER Gateway Configuration

**Note:** This configuration is archived for reference only. The gateway is not currently active.

Original MCP_DOCKER gateway configuration (from `claude_desktop_config.json`):

```json
{
  "MCP_DOCKER": {
    "command": "docker",
    "args": [
      "mcp",
      "gateway",
      "run"
    ],
    "env": {
      "LOCALAPPDATA": "C:\\Users\\User\\AppData\\Local",
      "ProgramData": "C:\\ProgramData",
      "ProgramFiles": "C:\\Program Files"
    }
  }
}
```

## Setup Steps

**Note:** This should be added as the **LAST STEP** after all other MCP servers have been tested and verified.

1. Create `servers.json` entry for MCP_DOCKER gateway
2. Test Docker MCP gateway functionality
3. Verify environment variable propagation
4. Test containerized MCP server execution

## Testing

- Test gateway initialization
- Test MCP server spawning through Docker
- Verify tool discovery and execution
- Monitor container lifecycle management

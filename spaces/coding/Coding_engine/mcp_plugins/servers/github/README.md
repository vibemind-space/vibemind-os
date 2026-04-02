# GitHub MCP Server Integration

This directory contains the GitHub MCP server integration for the Sakana Desktop Assistant.

## Overview

The GitHub MCP server provides AI agents with access to GitHub's API for repository management, issue tracking, pull requests, code search, and more.

## Prerequisites

1. **Docker** - The GitHub MCP server runs in a Docker container
2. **GitHub Personal Access Token (PAT)** - Required for authentication

### Creating a GitHub PAT

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Select minimum scopes:
   - `repo` (Full control of private repositories)
   - `read:packages` (Read packages)
   - `read:org` (Read organization data)
4. Copy the generated token

## Configuration

### Option 1: Using secrets.json (Recommended)

1. Navigate to `src/MCP PLUGINS/servers/`
2. Copy `secrets.example.json` to `secrets.json`:
   ```bash
   cp secrets.example.json secrets.json
   ```
3. Edit `secrets.json` and add your GitHub Personal Access Token:
   ```json
   {
     "github": {
       "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_actual_token_here"
     }
   }
   ```

### Option 2: Using Environment Variables

Set the GitHub Personal Access Token in your environment:

**Windows (PowerShell):**
```powershell
$env:GITHUB_PERSONAL_ACCESS_TOKEN="your_token_here"
```

**Windows (CMD):**
```cmd
set GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here
```

**Unix/Linux/Mac:**
```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here
```

**Note:** Environment variables take precedence over `secrets.json`.

### Server Configuration

The GitHub server is configured in `src/MCP PLUGINS/servers/servers.json`:

```json
{
  "name": "github",
  "active": true,
  "type": "stdio",
  "command": "docker",
  "args": [
    "run",
    "-i",
    "--rm",
    "-e",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "ghcr.io/github/github-mcp-server"
  ],
  "read_timeout_seconds": 120
}
```

## Usage

### Running the Agent Directly

```bash
cd "src/MCP PLUGINS/servers/github.repo"
python agent.py
```

### Through the Scheduler

The GitHub agent integrates with the Sakana assistant's task scheduler. Tasks with GitHub-related keywords are automatically routed to this server.

Example keywords that trigger GitHub routing:
- "repository", "repo"
- "github"
- "issue", "pr", "pull request"
- "commit", "branch"

## Available Operations

The GitHub MCP server typically provides tools for:

- **Repository Operations**: Clone, browse files, search code
- **Issue Management**: Create, list, update, close issues
- **Pull Requests**: Create, review, merge PRs
- **Branch Operations**: Create, delete, list branches
- **Commit Operations**: View commits, commit history
- **Workflow Management**: Trigger actions, view workflow runs

## Files

- `agent.py` - Main GitHub agent implementation using AutoGen + MCP
- `system_prompt.txt` - System prompt for the GitHub assistant
- `task_prompt.txt` - Task-specific prompt template
- `README.md` - This documentation file

## Troubleshooting

### Docker not found
Ensure Docker is installed and in your PATH:
```bash
docker --version
```

### Authentication errors
Verify your GitHub PAT is set correctly:
```bash
echo $GITHUB_PERSONAL_ACCESS_TOKEN
```

### Rate limiting
GitHub API has rate limits. If you encounter rate limit errors, wait a few minutes or use a token with higher limits.

## References

- [GitHub MCP Server Official Repository](https://github.com/github/github-mcp-server)
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [GitHub API Documentation](https://docs.github.com/en/rest)
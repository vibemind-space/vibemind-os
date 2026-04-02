# Docker MCP Server Integration

This directory contains the Docker MCP server integration for the Sakana Desktop Assistant.

## Overview

The Docker MCP server provides AI agents with access to Docker operations for container management, compose stack deployment, and log retrieval.

## Prerequisites

1. **UV Package Manager** - Python package installer and runner
   ```bash
   # Install UV (if not already installed)
   pip install uv
   ```

2. **Docker Desktop or Docker Engine** - Must be running
   ```bash
   # Verify Docker is running
   docker ps
   ```

3. **Python 3.12+** - Required for the docker-mcp package

## Installation

### Installing UV (Windows)

**PowerShell:**
```powershell
pip install uv
```

**Command Prompt:**
```cmd
pip install uv
```

### Installing docker-mcp

The docker-mcp package will be installed automatically via `uvx` when the MCP server starts.

## Configuration

### Credentials

Docker MCP server currently does not require any API credentials. It connects to your local Docker daemon. If future versions require credentials, they can be added to `secrets.json`:

```json
{
  "docker": {}
}
```

### Server Configuration

The Docker server is configured in `src/MCP PLUGINS/servers/servers.json`:

```json
{
  "name": "docker",
  "active": true,
  "type": "stdio",
  "command": "C:\\Windows\\System32\\cmd.exe",
  "args": [
    "/c",
    "uvx",
    "docker-mcp"
  ],
  "read_timeout_seconds": 120
}
```

### Docker Daemon

Ensure Docker Desktop (Windows/Mac) or Docker Engine (Linux) is running before using the Docker MCP server.

**Windows:**
- Start Docker Desktop from the Start menu
- Wait for the Docker icon in the system tray to show "Docker Desktop is running"

**Verify Docker is accessible:**
```bash
docker ps
```

## Usage

### Running the Agent Directly

```bash
cd "src/MCP PLUGINS/servers/docker.ops"
python agent.py
```

### Through the Scheduler

The Docker agent integrates with the Sakana assistant's task scheduler. Tasks with Docker-related keywords are automatically routed to this server.

Example keywords that trigger Docker routing:
- "docker", "container"
- "compose", "docker-compose"
- "image", "dockerfile"
- "logs"

## Available Operations

The Docker MCP server provides tools for:

- **Container Creation**: `create-container` - Spin up Docker containers from images
- **Compose Deployment**: `deploy-compose` - Deploy Docker Compose stacks
- **Log Retrieval**: `get-logs` - Retrieve container logs for debugging
- **Container Listing**: `list-containers` - List all containers and their status

## Current Limitations

Based on the docker-mcp implementation:
- No environment variable support in container creation
- No volume/network management
- No container health checks
- No restart policies
- No resource limit configurations

## Files

- `agent.py` - Main Docker agent implementation using AutoGen + MCP
- `system_prompt.txt` - System prompt for the Docker assistant
- `task_prompt.txt` - Task-specific prompt template
- `README.md` - This documentation file

## Troubleshooting

### UV not found
Ensure UV is installed and in your PATH:
```bash
pip install uv
```

### Docker daemon not running
Start Docker Desktop or Docker Engine:
```bash
# Windows: Start Docker Desktop from Start menu
# Linux: sudo systemctl start docker
```

Verify Docker is running:
```bash
docker ps
```

### Permission errors
On Linux, ensure your user is in the docker group:
```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Container creation fails
Check:
- Image name is correct (format: `image:tag`)
- Docker Hub is accessible for image pull
- Sufficient disk space for image and container

## Example Tasks

- "List all running Docker containers"
- "Create a container from nginx:latest"
- "Get logs for container web-server"
- "Deploy a Docker Compose stack from docker-compose.yml"

## References

- [docker-mcp GitHub Repository](https://github.com/QuantGeekDev/docker-mcp)
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Docker Documentation](https://docs.docker.com/)
- [UV Package Manager](https://github.com/astral-sh/uv)
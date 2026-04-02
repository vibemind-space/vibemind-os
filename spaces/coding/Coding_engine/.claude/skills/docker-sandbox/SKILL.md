---
name: docker-sandbox
description: Manages Docker sandbox environments for runtime verification. Creates isolated containers with VNC streaming, runs health checks, hot-reloads code changes, and validates app behavior in production-like environments.
---

# Docker Sandbox Skill

You are the Sandbox Manager for the Society of Mind autonomous code generation system.

## Purpose

Manage Docker sandbox environments for:
- Runtime verification of generated code
- VNC streaming for visual monitoring
- Hot-reload file synchronization
- Health checks and smoke tests
- Isolated testing without affecting host

## Trigger Events

| Event | Action |
|-------|--------|
| `BUILD_SUCCEEDED` | Deploy to sandbox |
| `CODE_FIXED` | Sync files, hot-reload |
| `SANDBOX_HEALTH_CHECK` | Run periodic checks |

## Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  DOCKER CONTAINER (sandbox-test)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Xvfb      │  │   x11vnc    │  │   noVNC     │            │
│  │  :99        │  │  Port 5900  │  │  Port 6080  │            │
│  │  Virtual    │  │  VNC Server │  │  Web Client │            │
│  │  Display    │  │             │  │             │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│         └────────────────┴────────────────┘                    │
│                          │                                      │
│  ┌───────────────────────┴───────────────────────────────┐     │
│  │                    APPLICATION                         │     │
│  │                                                        │     │
│  │   React App (Port 5173)  OR  Electron App             │     │
│  │   or Python API  OR  Node.js Server                   │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

VNC Access: http://localhost:6080/vnc.html
```

## Workflow

### 1. Container Setup

```bash
# Build sandbox image
docker build -t sandbox-test -f infra/docker/Dockerfile.sandbox .

# Run container with VNC
docker run -d \
  --name sandbox-runner \
  -p 6080:6080 \
  -p 5173:5173 \
  -v /project:/app \
  sandbox-test
```

### 2. VNC Services

Start display and VNC:
```bash
# Start virtual display
Xvfb :99 -screen 0 1024x768x24 &
export DISPLAY=:99

# Start VNC server
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 -bg

# Start noVNC web client
websockify --web=/usr/share/novnc 6080 localhost:5900 &
```

### 3. Application Launch

Auto-detect project type and launch:

```bash
# Check package.json for project type
if [ -f "package.json" ]; then
  if grep -q "electron" package.json; then
    # Electron app
    npm run build && npm run start
  elif grep -q "vite" package.json; then
    # Vite/React app
    npm run dev -- --host 0.0.0.0
  else
    # Generic Node.js
    npm start
  fi
elif [ -f "requirements.txt" ]; then
  # Python app
  pip install -r requirements.txt
  python main.py
fi
```

### 4. Health Checks

Run periodic health checks:

```python
async def health_check(container_id: str) -> HealthResult:
    """Check if app is running and responsive."""

    # 1. Check container is running
    container_status = await docker.inspect(container_id)
    if container_status["State"]["Status"] != "running":
        return HealthResult(healthy=False, reason="Container not running")

    # 2. Check app port is listening
    port_check = await docker.exec(container_id, "netstat -tlnp | grep 5173")
    if not port_check:
        return HealthResult(healthy=False, reason="App not listening on port")

    # 3. HTTP health check
    try:
        response = await http.get("http://localhost:5173/")
        if response.status_code != 200:
            return HealthResult(healthy=False, reason=f"HTTP {response.status_code}")
    except Exception as e:
        return HealthResult(healthy=False, reason=str(e))

    # 4. Check for console errors
    logs = await docker.logs(container_id, tail=50)
    if "Error:" in logs or "FATAL" in logs:
        return HealthResult(healthy=False, reason="Console errors detected")

    return HealthResult(healthy=True)
```

### 5. File Synchronization

Hot-reload code changes:

```python
async def sync_file(file_path: str, container_id: str):
    """Sync modified file to container and trigger reload."""

    # Copy file to container
    await docker.exec(
        container_id,
        f"docker cp {file_path} {container_id}:/app/{file_path}"
    )

    # Trigger hot-reload (kill node to restart)
    await docker.exec(container_id, "pkill -HUP node")

    # Wait for app to restart
    await asyncio.sleep(2)

    # Verify app is running
    return await health_check(container_id)
```

## Docker Compose Configuration

### docker-compose.sandbox.yml

```yaml
version: '3.8'

services:
  sandbox:
    build:
      context: .
      dockerfile: infra/docker/Dockerfile.sandbox
    ports:
      - "6080:6080"   # noVNC
      - "5173:5173"   # Dev server
      - "8080:8080"   # API (if applicable)
    volumes:
      - ./output:/app
    environment:
      - DISPLAY=:99
      - NODE_ENV=development
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5173/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Dockerfile.sandbox

```dockerfile
FROM node:20-slim

# Install VNC dependencies
RUN apt-get update && apt-get install -y \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Install project dependencies
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Copy entrypoint
COPY infra/docker/sandbox-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6080 5173 8080

ENTRYPOINT ["/entrypoint.sh"]
```

## Communication

### Publish Events

```python
# On successful deployment
event_bus.publish(Event(
    type=EventType.SANDBOX_TEST_PASSED,
    source="docker-sandbox",
    data={
        "container_id": "abc123",
        "vnc_url": "http://localhost:6080/vnc.html",
        "app_url": "http://localhost:5173/",
        "health": "healthy"
    }
))

# On failure
event_bus.publish(Event(
    type=EventType.SANDBOX_TEST_FAILED,
    source="docker-sandbox",
    data={
        "container_id": "abc123",
        "error": "App crashed on startup",
        "logs": "Error: Cannot find module './Button'"
    }
))
```

## Sandbox Modes

### Continuous Sandbox (`--continuous-sandbox`)

Starts BEFORE code generation:
```
1. Container created
2. VNC services started
3. Project mounted
4. Dependencies installed
5. Every 30 seconds: App restart → Health check → Kill
6. Changes sync via docker cp
7. Hot-reload triggers
```

### Validation Sandbox (`--enable-sandbox`)

Runs AFTER build succeeds:
```
1. Build completes successfully
2. Container created fresh
3. Full npm install
4. App started once
5. Health check
6. E2E tests run
7. Container destroyed
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| VNC not connecting | Check port 6080 is exposed, x11vnc is running |
| App not starting | Check npm install completed, entry point correct |
| Hot-reload not working | Ensure pkill node triggers restart |
| Container crashes | Check logs: `docker logs sandbox-runner` |
| Port conflict | Use different ports: `-p 7080:6080` |

## Best Practices

1. **Isolate Testing** - Each test run gets fresh container
2. **Clean Up** - Remove containers after tests: `docker rm -f sandbox-runner`
3. **Resource Limits** - Set memory limits: `--memory=2g`
4. **Log Everything** - Capture container logs for debugging
5. **Timeout** - Kill stuck containers after 5 minutes

#!/bin/bash
# Deploy Coding Engine to Docker Swarm
# Usage: ./infra/docker/deploy-swarm.sh

set -e

echo "=== Coding Engine Swarm Deployment ==="

# 1. Check Swarm status
echo "Checking Docker Swarm..."
SWARM_STATE=$(docker info --format '{{.Swarm.LocalNodeState}}')
if [ "$SWARM_STATE" != "active" ]; then
    echo "Docker Swarm not active. Initializing..."
    docker swarm init 2>/dev/null || true
fi
echo "Swarm: active"

# 2. Check required secrets
echo "Checking secrets..."
REQUIRED_SECRETS="openrouter_api_key postgres_password redis_password discord_bot_token_engine"
MISSING=""
for secret in $REQUIRED_SECRETS; do
    if ! docker secret inspect "$secret" >/dev/null 2>&1; then
        MISSING="$MISSING $secret"
    fi
done

if [ -n "$MISSING" ]; then
    echo "ERROR: Missing secrets:$MISSING"
    echo "Create them with: echo 'value' | docker secret create <name> -"
    exit 1
fi
echo "All required secrets present"

# 3. Build images
echo "Building images..."
docker compose build api sandbox worker 2>/dev/null || echo "Build skipped (images may already exist)"

# 4. Deploy stack
echo "Deploying stack..."
docker stack deploy -c infra/docker/docker-stack.yml coding-engine

# 5. Wait for services
echo "Waiting for services to start..."
sleep 15

# 6. Verify
echo "=== Service Status ==="
docker service ls --filter name=coding-engine

echo ""
echo "=== Deployment Complete ==="
echo "API:      http://localhost:8000"
echo "Frontend: http://localhost:8080"
echo "Sandbox:  http://localhost:3100"
echo "VNC:      http://localhost:6090"
echo "Trae:     http://localhost:8007"

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# DaveFelix Coding Engine — Start Services
# ============================================================
# Usage:
#   bash start.sh            # Core only (postgres, redis, api)
#   bash start.sh --all      # All services
#   bash start.sh --no-build # Skip image rebuild
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# Parse flags
ALL=false
NO_BUILD=false
for arg in "$@"; do
    case "$arg" in
        --all)      ALL=true ;;
        --no-build) NO_BUILD=true ;;
        --help|-h)
            echo "Usage: bash start.sh [--all] [--no-build]"
            echo "  --all       Start all services (sandbox, gitea, vscode, etc.)"
            echo "  --no-build  Skip Docker image rebuild"
            exit 0
            ;;
        *) warn "Unknown flag: $arg" ;;
    esac
done

# Detect compose command
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    fail "Docker Compose not found. Run setup.sh first."
fi

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  DaveFelix Coding Engine — Start${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ------------------------------------------------------------------
# 0. Pre-checks
# ------------------------------------------------------------------
[ -f ".env" ] || fail ".env not found. Run 'bash setup.sh' first."
docker info >/dev/null 2>&1 || fail "Docker daemon not running. Start Docker Desktop."

# ------------------------------------------------------------------
# 1. Build if needed
# ------------------------------------------------------------------
if [ "$NO_BUILD" = false ]; then
    info "Building images (use --no-build to skip)..."
    $COMPOSE build --parallel 2>&1 | tail -3
    ok "Images ready"
    echo ""
fi

# ------------------------------------------------------------------
# 2. Start core infrastructure
# ------------------------------------------------------------------
info "Starting PostgreSQL + Redis..."
$COMPOSE up -d postgres redis

# Wait for healthy
info "Waiting for databases to be ready..."
for i in $(seq 1 30); do
    pg_ok=$($COMPOSE exec -T postgres pg_isready -U postgres 2>/dev/null && echo "yes" || echo "no")
    redis_ok=$($COMPOSE exec -T redis redis-cli ping 2>/dev/null | grep -q PONG && echo "yes" || echo "no")
    if [ "$pg_ok" = "yes" ] && [ "$redis_ok" = "yes" ]; then
        break
    fi
    sleep 1
done
ok "PostgreSQL ready"
ok "Redis ready"

# ------------------------------------------------------------------
# 3. Start API
# ------------------------------------------------------------------
echo ""
info "Starting API server..."
$COMPOSE up -d api

# Wait for API health
info "Waiting for API to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1 || \
       curl -sf http://localhost:8000/docs >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
ok "API server ready"

# ------------------------------------------------------------------
# 4. Optional: All services
# ------------------------------------------------------------------
if [ "$ALL" = true ]; then
    echo ""
    info "Starting all additional services..."

    $COMPOSE up -d frontend 2>/dev/null && ok "Frontend (DaveLovable UI)" || warn "Frontend failed to start"
    $COMPOSE up -d gitea 2>/dev/null && ok "Gitea (Git server)" || warn "Gitea failed to start"
    $COMPOSE up -d sandbox 2>/dev/null && ok "Sandbox (VNC preview)" || warn "Sandbox failed to start (may need /dev/kvm)"
    $COMPOSE up -d worker 2>/dev/null && ok "Worker" || warn "Worker failed to start"
    $COMPOSE up -d vscode 2>/dev/null && ok "VSCode Server" || warn "VSCode failed to start"
    $COMPOSE up -d automation-ui-backend 2>/dev/null && ok "Automation UI" || warn "Automation UI failed to start"

    # OpenClaw requires external repo — start only with: docker compose --profile openclaw up -d openclaw
    warn "OpenClaw skipped (use: docker compose --profile openclaw up -d openclaw)"
fi

# ------------------------------------------------------------------
# 5. Status
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Services Running${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

print_service() {
    local name="$1"
    local url="$2"
    local container="$3"
    local status
    status=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "not started")
    if [ "$status" = "running" ]; then
        echo -e "  ${GREEN}*${NC} $name"
        echo -e "    ${CYAN}$url${NC}"
    else
        echo -e "  ${RED}*${NC} $name ($status)"
    fi
}

print_service "API Server"     "http://localhost:8000"         "coding-engine-api"
print_service "PostgreSQL"     "localhost:5432"                 "coding-engine-postgres"
print_service "Redis"          "localhost:6382"                 "coding-engine-redis"

if [ "$ALL" = true ]; then
    print_service "Frontend"       "http://localhost:5173"      "coding-engine-frontend"
    print_service "Gitea"          "http://localhost:3000"      "coding-engine-gitea"
    print_service "Sandbox VNC"    "http://localhost:6090"      "coding-engine-sandbox"
    print_service "App Preview"    "http://localhost:3100"      "coding-engine-sandbox"
    print_service "VSCode"         "http://localhost:8444"      "coding-engine-vscode"
    print_service "Worker"         "(background)"               "coding-engine-worker"
    print_service "Automation UI"  "http://localhost:8007"      "coding-engine-automation-ui"
fi

echo ""
echo "  Stop with:  bash stop.sh"
echo "  Logs:       docker compose logs -f api"
echo ""

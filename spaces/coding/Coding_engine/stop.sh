#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# DaveFelix Coding Engine — Stop Services
# ============================================================
# Usage:
#   bash stop.sh           # Stop all containers
#   bash stop.sh --clean   # Stop + remove volumes (fresh start)
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# Detect compose command
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    echo "Docker Compose not found."
    exit 1
fi

CLEAN=false
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=true ;;
        --help|-h)
            echo "Usage: bash stop.sh [--clean]"
            echo "  --clean   Also remove Docker volumes (database, redis, etc.)"
            exit 0
            ;;
    esac
done

echo ""
info "Stopping all Coding Engine services..."

if [ "$CLEAN" = true ]; then
    warn "Removing containers AND volumes (--clean)"
    $COMPOSE down -v --remove-orphans 2>/dev/null
    ok "All containers and volumes removed"
else
    $COMPOSE down --remove-orphans 2>/dev/null
    ok "All containers stopped (volumes preserved)"
fi

echo ""
echo "  Restart with:  bash start.sh"
echo ""

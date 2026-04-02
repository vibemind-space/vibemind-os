#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# DaveFelix Coding Engine — First-Time Setup
# ============================================================
# Run once after cloning the repo:
#   git clone --recursive https://github.com/Flissel/DaveFelix-Coding-Engine.git
#   cd DaveFelix-Coding-Engine
#   bash setup.sh
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

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  DaveFelix Coding Engine — Setup${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Check prerequisites
# ------------------------------------------------------------------
info "Checking prerequisites..."

command -v git >/dev/null 2>&1 || fail "Git is not installed. Install it from https://git-scm.com"
ok "Git $(git --version | awk '{print $3}')"

command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Install Docker Desktop from https://docker.com"
ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# Docker Compose v2 (docker compose) or v1 (docker-compose)
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
    ok "Docker Compose $(docker compose version --short 2>/dev/null || echo 'v2')"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
    ok "Docker Compose (v1 legacy)"
else
    fail "Docker Compose is not installed. Install Docker Desktop (includes Compose v2)."
fi

# Python 3.10+
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    fail "Python 3.10+ is not installed. Install from https://python.org"
fi
PY_VER=$($PY --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required, found $PY_VER"
fi
ok "Python $PY_VER"

# Node.js 18+
if command -v node >/dev/null 2>&1; then
    NODE_VER=$(node --version | tr -d 'v')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 18 ]; then
        fail "Node.js 18+ required, found v$NODE_VER"
    fi
    ok "Node.js v$NODE_VER"
else
    warn "Node.js not found — needed for dashboard-app (optional). Install from https://nodejs.org"
fi

# Docker daemon running?
docker info >/dev/null 2>&1 || fail "Docker daemon is not running. Start Docker Desktop."
ok "Docker daemon is running"

echo ""

# ------------------------------------------------------------------
# 2. Init git submodules
# ------------------------------------------------------------------
info "Initializing git submodules..."
git submodule update --init --recursive 2>/dev/null || warn "Submodule init had warnings (may be OK)"
ok "Submodules initialized"

# ------------------------------------------------------------------
# 3. Create .env from .env.example
# ------------------------------------------------------------------
ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    echo ""
    warn ".env already exists."
    read -rp "  Overwrite? (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        ok "Keeping existing .env"
    else
        rm "$ENV_FILE"
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    info "Creating .env from .env.example..."
    cp .env.example "$ENV_FILE"

    echo ""
    echo -e "${CYAN}--- API Keys Configuration ---${NC}"
    echo "  Press Enter to skip optional keys."
    echo ""

    # Helper: prompt for key and replace in .env
    prompt_key() {
        local key="$1"
        local label="$2"
        local required="${3:-false}"
        local tag=""
        if [ "$required" = "true" ]; then
            tag="${RED}[REQUIRED]${NC}"
        else
            tag="${YELLOW}[optional]${NC}"
        fi
        echo -ne "  $tag $label: "
        read -r value
        if [ -n "$value" ]; then
            # Platform-safe sed
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
            else
                sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
            fi
            ok "  $key set"
        elif [ "$required" = "true" ]; then
            warn "  $key skipped — you'll need to set it manually in .env"
        fi
    }

    # Required
    prompt_key "OPENAI_API_KEY"      "OpenAI API Key (sk-...)" false
    prompt_key "GITHUB_TOKEN"        "GitHub Token (ghp_...)"  false

    echo ""
    echo -e "  ${YELLOW}Optional keys (press Enter to skip):${NC}"
    prompt_key "ANTHROPIC_API_KEY"           "Anthropic API Key"
    prompt_key "OPENROUTER_API_KEY"          "OpenRouter API Key"
    prompt_key "DISCORD_BOT_TOKEN"           "Discord Bot Token"
    prompt_key "DISCORD_BOT_TOKEN_ANALYZER"  "Discord Analyzer Bot Token"
    prompt_key "SUPERMEMORY_API_KEY"         "Supermemory API Key"

    echo ""
    ok ".env created"
fi

# ------------------------------------------------------------------
# 4. Install Python dependencies
# ------------------------------------------------------------------
echo ""
info "Installing Python dependencies..."
$PY -m pip install -r requirements.txt --quiet 2>/dev/null && ok "Python dependencies installed" || warn "Some pip installs had issues (may need manual fix)"

# ------------------------------------------------------------------
# 5. Create directories
# ------------------------------------------------------------------
info "Creating output directories..."
mkdir -p Data/generated Data/artifacts
ok "Directories created"

# ------------------------------------------------------------------
# 6. Build Docker images
# ------------------------------------------------------------------
echo ""
info "Building Docker images (this may take a few minutes on first run)..."
$COMPOSE build --parallel 2>&1 | tail -5
ok "Docker images built"

# ------------------------------------------------------------------
# 7. Summary
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Next steps:"
echo "    1. Review your .env file and add any missing API keys"
echo "    2. Start the engine:"
echo ""
echo -e "       ${CYAN}bash start.sh${NC}          # Core services (API, DB, Redis)"
echo -e "       ${CYAN}bash start.sh --all${NC}    # All services (+ Sandbox, Gitea, VSCode)"
echo ""
echo "  Ports:"
echo "    API Server:    http://localhost:8000"
echo "    Sandbox VNC:   http://localhost:6090"
echo "    Gitea Git:     http://localhost:3000"
echo "    VSCode:        http://localhost:8444  (password: dev123)"
echo "    App Preview:   http://localhost:3100"
echo ""

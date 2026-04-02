#!/bin/bash
# start_workers.sh - Startet alle MCP Agents als gRPC Worker
# Usage: ./start_workers.sh [--all | --core | agent1 agent2 ...]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Worker Konfiguration (Name -> Port)
declare -A WORKER_PORTS=(
    # Core Agents
    ["filesystem"]=50072
    ["docker"]=50063
    ["redis"]=50066
    ["playwright"]=50061
    ["git"]=50079

    # Package Management
    ["npm"]=50080
    ["prisma"]=50081

    # Database
    ["postgres"]=50082
    ["supabase"]=50067
    ["qdrant"]=50083

    # Search & Web
    ["brave-search"]=50073
    ["tavily"]=50078
    ["fetch"]=50074

    # Utility
    ["memory"]=50071
    ["time"]=50068
    ["context7"]=50065
    ["taskmanager"]=50069
    ["desktop"]=50064
    ["windows-core"]=50070
    ["github"]=50062
    ["n8n"]=50076
    ["supermemory"]=50084
)

CORE_AGENTS=("filesystem" "docker" "redis" "playwright" "git" "postgres")

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

start_worker() {
    local name=$1
    local port=$2
    local agent_path="$SCRIPT_DIR/$name/agent.py"

    if [ ! -f "$agent_path" ]; then
        echo -e "  ${YELLOW}[SKIP]${NC} $name - agent.py nicht gefunden"
        return
    fi

    echo -e "  ${CYAN}[START]${NC} $name auf Port $port..."
    python "$agent_path" --grpc --grpc-port "$port" &
    local pid=$!
    echo -e "    ${GREEN}PID: $pid${NC}"

    # PID speichern für späteres Stoppen
    echo "$pid" >> /tmp/mcp_workers.pids
}

stop_all_workers() {
    echo -e "${YELLOW}Stoppe alle Worker...${NC}"
    if [ -f /tmp/mcp_workers.pids ]; then
        while read pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                echo -e "  Gestoppt: PID $pid"
            fi
        done < /tmp/mcp_workers.pids
        rm /tmp/mcp_workers.pids
    fi
    echo -e "${GREEN}Alle Worker gestoppt.${NC}"
}

show_help() {
    echo ""
    echo "Usage: $0 [OPTIONS] [AGENTS...]"
    echo ""
    echo "Options:"
    echo "  --all       Alle Workers starten"
    echo "  --core      Nur Core Workers (filesystem, docker, redis, playwright, git, postgres)"
    echo "  --stop      Alle Workers stoppen"
    echo "  --list      Verfügbare Workers auflisten"
    echo "  --help      Diese Hilfe anzeigen"
    echo ""
    echo "Examples:"
    echo "  $0 --core                    # Core Workers starten"
    echo "  $0 --all                     # Alle Workers starten"
    echo "  $0 filesystem docker redis   # Spezifische Workers starten"
    echo "  $0 --stop                    # Alle Workers stoppen"
    echo ""
}

list_workers() {
    echo ""
    echo "Verfügbare Workers:"
    echo ""
    for name in "${!WORKER_PORTS[@]}"; do
        echo "  $name -> Port ${WORKER_PORTS[$name]}"
    done | sort
    echo ""
}

# Hauptlogik
echo ""
echo -e "${MAGENTA}========================================${NC}"
echo -e "${MAGENTA}   MCP Agent gRPC Worker Launcher${NC}"
echo -e "${MAGENTA}========================================${NC}"
echo ""

# PID-Datei initialisieren
> /tmp/mcp_workers.pids

# Argumente parsen
AGENTS_TO_START=()

case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --list)
        list_workers
        exit 0
        ;;
    --stop)
        stop_all_workers
        exit 0
        ;;
    --all)
        AGENTS_TO_START=("${!WORKER_PORTS[@]}")
        echo -e "${YELLOW}Starte ALLE Workers (${#AGENTS_TO_START[@]})...${NC}"
        ;;
    --core)
        AGENTS_TO_START=("${CORE_AGENTS[@]}")
        echo -e "${YELLOW}Starte CORE Workers (${#AGENTS_TO_START[@]})...${NC}"
        ;;
    "")
        # Default: Core Agents
        AGENTS_TO_START=("${CORE_AGENTS[@]}")
        echo -e "${YELLOW}Starte CORE Workers (default, ${#AGENTS_TO_START[@]})...${NC}"
        echo ""
        echo -e "${NC}Optionen:${NC}"
        echo "  --all        Alle Workers starten"
        echo "  --core       Nur Core Workers (default)"
        echo "  --list       Verfügbare Workers auflisten"
        echo "  --stop       Workers stoppen"
        ;;
    *)
        # Spezifische Agents
        AGENTS_TO_START=("$@")
        echo -e "${YELLOW}Starte ausgewählte Workers (${#AGENTS_TO_START[@]})...${NC}"
        ;;
esac

echo ""

# Workers starten
for agent in "${AGENTS_TO_START[@]}"; do
    if [ -n "${WORKER_PORTS[$agent]:-}" ]; then
        start_worker "$agent" "${WORKER_PORTS[$agent]}"
    else
        echo -e "  ${YELLOW}[WARN]${NC} Unbekannter Agent: $agent"
    fi
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Workers gestartet!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Zum Stoppen: $0 --stop"
echo ""

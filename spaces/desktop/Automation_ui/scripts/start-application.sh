#!/bin/bash

# TRAE Unity AI Platform - Complete Application Startup Script
# This script starts all components of the desktop streaming application

# Default values
SHOW_LOGS=false
SKIP_DESKTOP_CLIENT=false
WEBSOCKET_PORT="8084"
FRONTEND_PORT="8081"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    echo -e "${1}${2}${NC}"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1  # Port is in use
    else
        return 0  # Port is available
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local url=$1
    local service_name=$2
    local timeout=${3:-30}
    
    print_color $YELLOW "⏳ Waiting for $service_name to be ready..."
    
    local count=0
    while [ $count -lt $timeout ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            print_color $GREEN "✅ $service_name is ready!"
            return 0
        fi
        sleep 2
        count=$((count + 2))
    done
    
    print_color $RED "⚠️  $service_name did not become ready within $timeout seconds"
    return 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --show-logs)
            SHOW_LOGS=true
            shift
            ;;
        --skip-desktop-client)
            SKIP_DESKTOP_CLIENT=true
            shift
            ;;
        --websocket-port)
            WEBSOCKET_PORT="$2"
            shift 2
            ;;
        --frontend-port)
            FRONTEND_PORT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --show-logs              Show real-time logs from all services"
            echo "  --skip-desktop-client    Start without desktop capture functionality"
            echo "  --websocket-port PORT    WebSocket server port (default: 8084)"
            echo "  --frontend-port PORT     Frontend server port (default: 8081)"
            echo "  -h, --help              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

print_color $GREEN "🚀 Starting TRAE Unity AI Platform..."
print_color $YELLOW "WebSocket Server Port: $WEBSOCKET_PORT"
print_color $YELLOW "Frontend Port: $FRONTEND_PORT"

# Get the root directory of the project
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Check prerequisites
print_color $CYAN "🔍 Checking prerequisites..."

# Check Node.js
if command_exists node; then
    NODE_VERSION=$(node --version)
    print_color $GREEN "✅ Node.js found: $NODE_VERSION"
else
    print_color $RED "❌ Node.js not found. Please install Node.js first."
    exit 1
fi

# Check npm
if command_exists npm; then
    NPM_VERSION=$(npm --version)
    print_color $GREEN "✅ npm found: $NPM_VERSION"
else
    print_color $RED "❌ npm not found. Please install npm first."
    exit 1
fi

# Check Python (only if not skipping desktop client)
if [ "$SKIP_DESKTOP_CLIENT" = false ]; then
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version)
        print_color $GREEN "✅ Python found: $PYTHON_VERSION"
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_VERSION=$(python --version)
        print_color $GREEN "✅ Python found: $PYTHON_VERSION"
        PYTHON_CMD="python"
    else
        print_color $RED "❌ Python not found. Please install Python first."
        print_color $YELLOW "   Or use --skip-desktop-client to start without desktop capture."
        exit 1
    fi
fi

# Check if ports are available
if ! check_port $WEBSOCKET_PORT; then
    print_color $RED "❌ Port $WEBSOCKET_PORT is already in use. Please stop the service using this port or choose a different port."
    exit 1
fi

print_color $GREEN "✅ All prerequisites met!"

echo ""

# Install frontend dependencies if needed
if [ ! -d "node_modules" ]; then
    print_color $CYAN "📦 Installing frontend dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        print_color $RED "❌ Failed to install frontend dependencies"
        exit 1
    fi
    print_color $GREEN "✅ Frontend dependencies installed!"
fi

# Install Python dependencies if needed (only if not skipping desktop client)
if [ "$SKIP_DESKTOP_CLIENT" = false ]; then
    DESKTOP_CLIENT_PATH="$PROJECT_ROOT/desktop-client"
    if [ -d "$DESKTOP_CLIENT_PATH" ]; then
        print_color $CYAN "📦 Installing Python dependencies for desktop client..."
        cd "$DESKTOP_CLIENT_PATH"
        
        # Check if requirements.txt exists
        if [ -f "requirements.txt" ]; then
            $PYTHON_CMD -m pip install -r requirements.txt
            if [ $? -ne 0 ]; then
                print_color $RED "❌ Failed to install Python dependencies"
                cd "$PROJECT_ROOT"
                exit 1
            fi
        else
            # Install common dependencies
            $PYTHON_CMD -m pip install websockets pillow pynput pyautogui
            if [ $? -ne 0 ]; then
                print_color $RED "❌ Failed to install Python dependencies"
                cd "$PROJECT_ROOT"
                exit 1
            fi
        fi
        
        cd "$PROJECT_ROOT"
        print_color $GREEN "✅ Python dependencies installed!"
    fi
fi

echo ""
print_color $GREEN "🚀 Starting services..."

# Array to store background process IDs
PIDS=()

# Function to cleanup background processes
cleanup() {
    echo ""
    print_color $RED "🛑 Stopping all services..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
        fi
    done
    wait
    print_color $GREEN "✅ All services stopped!"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# 1. Start WebSocket Server
print_color $CYAN "🌐 Starting WebSocket Server on port $WEBSOCKET_PORT..."
WS_SERVER_PATH="$PROJECT_ROOT/scripts/dev/local-websocket-server.js"

if [ -f "$WS_SERVER_PATH" ]; then
    WS_PORT=$WEBSOCKET_PORT node "$WS_SERVER_PATH" &
    WS_PID=$!
    PIDS+=($WS_PID)
    sleep 3
    
    if kill -0 "$WS_PID" 2>/dev/null; then
        print_color $GREEN "✅ WebSocket Server started successfully!"
    else
        print_color $RED "❌ Failed to start WebSocket Server"
        exit 1
    fi
else
    print_color $RED "❌ WebSocket server file not found at: $WS_SERVER_PATH"
    exit 1
fi

# 2. Start Desktop Spawner (only if not skipping desktop client)
if [ "$SKIP_DESKTOP_CLIENT" = false ]; then
    print_color $CYAN "🖥️  Starting Desktop Spawner Service..."
    SPAWNER_PATH="$PROJECT_ROOT/desktop-client/desktop_spawner.py"
    
    if [ -f "$SPAWNER_PATH" ]; then
        SERVER_URL="ws://localhost:$WEBSOCKET_PORT"
        $PYTHON_CMD "$SPAWNER_PATH" --server-url "$SERVER_URL" &
        SPAWNER_PID=$!
        PIDS+=($SPAWNER_PID)
        sleep 3
        
        if kill -0 "$SPAWNER_PID" 2>/dev/null; then
            print_color $GREEN "✅ Desktop Spawner Service started!"
        else
            print_color $YELLOW "⚠️  Desktop Spawner may not have started properly"
        fi
    else
        print_color $YELLOW "⚠️  Desktop spawner not found at: $SPAWNER_PATH"
        print_color $YELLOW "   Desktop capture functionality will not be available."
    fi
fi

# 3. Start Frontend Development Server
print_color $CYAN "🎨 Starting Frontend Development Server..."
PORT=$FRONTEND_PORT npm run dev &
FRONTEND_PID=$!
PIDS+=($FRONTEND_PID)
sleep 5

# Wait for frontend to be ready
if wait_for_service "http://localhost:$FRONTEND_PORT" "Frontend Server" 30; then
    print_color $GREEN "✅ Frontend Development Server started successfully!"
else
    print_color $YELLOW "⚠️  Frontend server may not have started properly. Check logs."
fi

echo ""
print_color $GREEN "🎉 TRAE Unity AI Platform is ready!"

echo ""
print_color $YELLOW "📊 Service Status:"
print_color $CYAN "  • WebSocket Server: ws://localhost:$WEBSOCKET_PORT"
print_color $CYAN "  • Frontend Application: http://localhost:$FRONTEND_PORT"
print_color $CYAN "  • Multi-Desktop Streams: http://localhost:$FRONTEND_PORT/multi-desktop"

if [ "$SKIP_DESKTOP_CLIENT" = false ]; then
    print_color $CYAN "  • Desktop Spawner: Connected to WebSocket server"
fi

echo ""
print_color $YELLOW "🔗 Quick Links:"
print_color $CYAN "  • Main Application: http://localhost:$FRONTEND_PORT"
print_color $CYAN "  • Desktop Streaming: http://localhost:$FRONTEND_PORT/multi-desktop"

if [ "$SHOW_LOGS" = true ]; then
    echo ""
    print_color $YELLOW "📋 Showing logs (Press Ctrl+C to stop all services)..."
    
    # Wait for all background processes
    wait
else
    echo ""
    print_color $BLUE "ℹ️  Services are running in background."
    print_color $CYAN "📋 Process IDs: ${PIDS[*]}"
    print_color $CYAN "🛑 Stop all services with: kill ${PIDS[*]}"
    echo ""
    print_color $YELLOW "💡 Tip: Use --show-logs to see real-time logs"
    print_color $YELLOW "💡 Tip: Use --skip-desktop-client to start without desktop capture"
    
    # Keep the script running to maintain the services
    echo ""
    print_color $BLUE "Press Ctrl+C to stop all services..."
    wait
fi
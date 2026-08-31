#!/bin/bash
# ============================================================================
# VibeMind-OS — Start all services
# ============================================================================
# Usage: ./start.sh
# Requires: .env file with API keys (copy from .env.example)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Load .env
if [ -f "$ROOT/.env" ]; then
    export $(grep -v '^#' "$ROOT/.env" | grep '=' | xargs)
    echo "[env] Loaded .env"
else
    echo "[env] WARNING: No .env file found. Copy .env.example to .env and add your API keys."
    exit 1
fi

# Check for at least one LLM key
if [ -z "$GROQ_API_KEY" ] && [ -z "$OPENROUTER_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[env] ERROR: No LLM API key found. Set at least one of: GROQ_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY"
    exit 1
fi

echo "============================================"
echo "  VibeMind-OS Starting..."
echo "============================================"

# 1. Brain (Tahlamus) — port 5000
echo ""
echo "[brain] Starting on :${BRAIN_PORT:-5000}..."
cd "$ROOT/brain/the_brain"
if [ ! -d ".venv" ]; then
    echo "[brain] Creating venv..."
    python -m venv .venv
    .venv/Scripts/pip install -r requirements-tahlamus.txt -q
fi
.venv/Scripts/python -m web.brain_server &
BRAIN_PID=$!
echo "[brain] PID: $BRAIN_PID"

# 2. OpenFang — port 50051
echo ""
echo "[openfang] Starting on :${OPENFANG_PORT:-50051}..."
cd "$ROOT/openfang"
if [ ! -f "target/release/openfang.exe" ]; then
    echo "[openfang] ERROR: Binary not found. Build first: cargo build --release -p openfang-cli"
    exit 1
fi
target/release/openfang.exe start &
OPENFANG_PID=$!
echo "[openfang] PID: $OPENFANG_PID"

# 3. Bridge — port 5100
echo ""
echo "[bridge] Starting on :${BRIDGE_PORT:-5100}..."
cd "$ROOT/bridge"
if [ ! -d ".venv" ]; then
    echo "[bridge] Creating venv..."
    python -m venv .venv
    .venv/Scripts/pip install -r requirements.txt -q
fi
PYTHONPATH=src OPENFANG_URL=http://localhost:${OPENFANG_PORT:-50051} \
    .venv/Scripts/python -m uvicorn bridge.main:app \
    --port ${BRIDGE_PORT:-5100} --host 127.0.0.1 &
BRIDGE_PID=$!
echo "[bridge] PID: $BRIDGE_PID"

# Wait for services
echo ""
echo "Waiting for services to start..."
sleep 15

# Health check
echo ""
echo "============================================"
echo "  Health Check"
echo "============================================"
BRAIN_OK=$(curl -s http://localhost:${BRAIN_PORT:-5000}/api/health 2>/dev/null | grep -c "alive" || echo 0)
OPENFANG_OK=$(curl -s http://localhost:${OPENFANG_PORT:-50051}/api/health 2>/dev/null | grep -c "ok" || echo 0)
BRIDGE_OK=$(curl -s http://localhost:${BRIDGE_PORT:-5100}/bridge/health 2>/dev/null | grep -c "ok" || echo 0)

[ "$BRAIN_OK" -gt 0 ] && echo "  Brain:    OK (:${BRAIN_PORT:-5000})" || echo "  Brain:    FAILED"
[ "$OPENFANG_OK" -gt 0 ] && echo "  OpenFang: OK (:${OPENFANG_PORT:-50051})" || echo "  OpenFang: FAILED"
[ "$BRIDGE_OK" -gt 0 ] && echo "  Bridge:   OK (:${BRIDGE_PORT:-5100})" || echo "  Bridge:   FAILED"

echo ""
echo "============================================"
echo "  VibeMind-OS Running"
echo "============================================"
echo ""
echo "  Bridge API:  http://localhost:${BRIDGE_PORT:-5100}"
echo "  Brain API:   http://localhost:${BRAIN_PORT:-5000}"
echo "  OpenFang UI: http://localhost:${OPENFANG_PORT:-50051}"
echo "  API Docs:    http://localhost:${BRIDGE_PORT:-5100}/docs"
echo ""
echo "  Test: curl -X POST http://localhost:${BRIDGE_PORT:-5100}/bridge/route \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"task\": \"Write a fibonacci function in Python\"}'"
echo ""
echo "Press Ctrl+C to stop all services."

# Wait for any child to exit
wait

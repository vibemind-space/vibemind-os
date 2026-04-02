#!/bin/bash
# Coding Engine Container Entrypoint
# Initializes environment and starts supervisord

set -e

echo "=========================================="
echo "  Coding Engine Container Starting"
echo "=========================================="

# ===== Directory Setup =====
echo "[INIT] Creating directories..."
mkdir -p /data/output /data/control /data/logs /tmp/.X11-unix
chmod -R 777 /data/output /data/control /data/logs 2>/dev/null || true

# ===== Log Initialization =====
echo "[INIT] Initializing logs..."
touch /data/logs/supervisord.log
touch /data/logs/xvfb.log
touch /data/logs/x11vnc.log
touch /data/logs/novnc.log
touch /data/logs/control-api.log
touch /data/logs/engine.log

# ===== Control State Initialization =====
echo "[INIT] Initializing control state..."
cat > /data/control/state.json << 'EOF'
{
    "status": "idle",
    "engine_running": false,
    "engine_pid": null,
    "started_at": null,
    "stopped_at": null,
    "requirements_file": null,
    "output_dir": null,
    "iterations": 0,
    "last_error": null
}
EOF

# ===== Environment Info =====
echo "[INIT] Environment:"
echo "  - Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}x${DISPLAY_DEPTH}"
echo "  - VNC Port: ${VNC_PORT}"
echo "  - noVNC Port: ${NOVNC_PORT}"
echo "  - Control API Port: ${CONTROL_PORT}"
echo "  - Preview Port: ${PREVIEW_PORT}"
echo "  - No Timeout: ${NO_TIMEOUT}"
echo "  - Max Iterations: ${MAX_ITERATIONS}"

# ===== Wait for VNC to be ready =====
wait_for_vnc() {
    echo "[INIT] Waiting for VNC server..."
    for i in {1..30}; do
        if nc -z localhost ${VNC_PORT} 2>/dev/null; then
            echo "[INIT] VNC server is ready!"
            return 0
        fi
        sleep 1
    done
    echo "[WARN] VNC server not responding after 30s"
    return 1
}

# ===== Signal Handlers =====
cleanup() {
    echo "[SHUTDOWN] Cleaning up..."
    
    # Update state
    if [ -f /data/control/state.json ]; then
        python3 -c "
import json
from datetime import datetime
with open('/data/control/state.json', 'r+') as f:
    state = json.load(f)
    state['status'] = 'stopped'
    state['stopped_at'] = datetime.now().isoformat()
    f.seek(0)
    json.dump(state, f)
    f.truncate()
"
    fi
    
    # Stop supervisor gracefully
    if [ -f /var/run/supervisord.pid ]; then
        kill -TERM $(cat /var/run/supervisord.pid) 2>/dev/null || true
    fi
    
    echo "[SHUTDOWN] Goodbye!"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

# ===== Custom Widget Injection =====
echo "[INIT] Injecting custom widget into noVNC..."
if [ -d /app/widget ] && [ -d /opt/novnc ]; then
    cp /app/widget/* /opt/novnc/ 2>/dev/null || true
    echo "[INIT] Widget files copied to noVNC"
fi

# ===== Start =====
echo "=========================================="
echo "  Starting Services via Supervisord"
echo "=========================================="
echo ""
echo "  Access Points:"
echo "  - VNC Stream: http://localhost:${NOVNC_PORT}/vnc.html"
echo "  - Widget: http://localhost:${NOVNC_PORT}/widget.html"
echo "  - Control API: http://localhost:${CONTROL_PORT}/api"
echo "  - API Docs: http://localhost:${CONTROL_PORT}/docs"
echo ""
echo "=========================================="

# Execute the command (usually supervisord)
exec "$@"
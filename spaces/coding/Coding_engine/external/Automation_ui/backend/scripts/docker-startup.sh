#!/bin/bash
set -e

# Create .Xauthority file to fix pyautogui X11 authentication
touch /root/.Xauthority

# Start Xvfb for headless display with no authentication required
Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99

# Wait for Xvfb to start
sleep 3

# Verify X11 display is accessible
echo "Testing X11 display connection..."
xdpyinfo -display :99 > /dev/null 2>&1 && echo "X11 display :99 is accessible" || echo "Warning: X11 display connection issue"

# Start the application
echo "Starting TRAE Backend Service..."
cd /app

# Run the FastAPI server
if [ "$SERVICE_TYPE" = "backend" ]; then
    # Use PORT environment variable (default to 8007 if not set)
    BACKEND_PORT=${PORT:-8007}
    echo "Starting backend service on port $BACKEND_PORT..."
    exec uvicorn server:app --host 0.0.0.0 --port $BACKEND_PORT --reload
else
    echo "Unknown service type: $SERVICE_TYPE"
    exit 1
fi
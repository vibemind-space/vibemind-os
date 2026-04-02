#!/bin/bash
# Dynamic Preview Starter
# Detects project type and starts appropriate preview

set -e

OUTPUT_DIR="${1:-/data/output}"
DISPLAY="${DISPLAY:-:99}"

echo "[PREVIEW] Starting preview for: ${OUTPUT_DIR}"

# ===== Helper Functions =====

detect_project_type() {
    local dir="$1"
    
    # Check for package.json
    if [ -f "${dir}/package.json" ]; then
        # Check for Electron
        if grep -q '"electron"' "${dir}/package.json" 2>/dev/null; then
            echo "electron"
            return
        fi
        
        # Check for React/Vue/Next.js (web apps)
        if grep -qE '"(react|vue|next|vite|webpack)"' "${dir}/package.json" 2>/dev/null; then
            echo "webapp"
            return
        fi
        
        # Generic Node.js
        echo "nodejs"
        return
    fi
    
    # Check for Python
    if [ -f "${dir}/requirements.txt" ] || [ -f "${dir}/setup.py" ] || [ -f "${dir}/pyproject.toml" ]; then
        # Check for Flask/FastAPI/Django
        if grep -qE '(flask|fastapi|django|streamlit|gradio)' "${dir}/requirements.txt" 2>/dev/null; then
            echo "python-web"
            return
        fi
        echo "python-cli"
        return
    fi
    
    # Check for Rust
    if [ -f "${dir}/Cargo.toml" ]; then
        # Check for Tauri
        if grep -q 'tauri' "${dir}/Cargo.toml" 2>/dev/null; then
            echo "tauri"
            return
        fi
        echo "rust-cli"
        return
    fi
    
    # Check for Go
    if [ -f "${dir}/go.mod" ]; then
        echo "go-cli"
        return
    fi
    
    # Default
    echo "unknown"
}

start_webapp_preview() {
    local dir="$1"
    local port="${PREVIEW_PORT:-5173}"
    
    echo "[PREVIEW] Starting web app preview on port ${port}..."
    
    cd "${dir}"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "[PREVIEW] Installing dependencies..."
        npm install --silent 2>/dev/null || yarn install --silent 2>/dev/null || true
    fi
    
    # Start dev server in background
    if grep -q '"dev"' package.json 2>/dev/null; then
        npm run dev &
    elif grep -q '"start"' package.json 2>/dev/null; then
        npm start &
    else
        npx vite --port ${port} &
    fi
    
    DEV_PID=$!
    echo $DEV_PID > /data/control/preview.pid
    
    # Wait for server
    echo "[PREVIEW] Waiting for dev server..."
    for i in {1..30}; do
        if nc -z localhost ${port} 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # Open browser
    echo "[PREVIEW] Opening browser..."
    chromium-browser --display=${DISPLAY} --no-sandbox --disable-gpu \
        --window-size=1280,800 --window-position=100,100 \
        "http://localhost:${port}" &
    
    echo "[PREVIEW] Web app preview started (PID: ${DEV_PID})"
}

start_electron_preview() {
    local dir="$1"
    
    echo "[PREVIEW] Starting Electron app preview..."
    
    cd "${dir}"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "[PREVIEW] Installing dependencies..."
        npm install --silent 2>/dev/null || true
    fi
    
    # Start Electron in dev mode
    if grep -q '"dev"' package.json 2>/dev/null; then
        npm run dev &
    elif grep -q '"start"' package.json 2>/dev/null; then
        npm start &
    else
        npx electron . &
    fi
    
    ELECTRON_PID=$!
    echo $ELECTRON_PID > /data/control/preview.pid
    
    echo "[PREVIEW] Electron app started (PID: ${ELECTRON_PID})"
}

start_cli_preview() {
    local dir="$1"
    local project_type="$2"
    
    echo "[PREVIEW] Starting CLI preview in terminal..."
    
    # Open terminal
    xfce4-terminal --display=${DISPLAY} \
        --geometry=120x40+50+50 \
        --title="Coding Engine - ${project_type}" \
        --working-directory="${dir}" &
    
    TERM_PID=$!
    echo $TERM_PID > /data/control/preview.pid
    
    echo "[PREVIEW] Terminal opened (PID: ${TERM_PID})"
}

start_python_web_preview() {
    local dir="$1"
    local port="${PREVIEW_PORT:-5173}"
    
    echo "[PREVIEW] Starting Python web app preview..."
    
    cd "${dir}"
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt --quiet 2>/dev/null || true
    fi
    
    # Detect framework and start
    if grep -q 'streamlit' requirements.txt 2>/dev/null; then
        streamlit run $(ls *.py | head -1) --server.port ${port} &
    elif grep -q 'gradio' requirements.txt 2>/dev/null; then
        python $(ls *.py | head -1) &
    elif grep -q 'fastapi' requirements.txt 2>/dev/null; then
        uvicorn main:app --port ${port} --reload &
    elif grep -q 'flask' requirements.txt 2>/dev/null; then
        FLASK_APP=$(ls *.py | head -1) flask run --port ${port} &
    elif grep -q 'django' requirements.txt 2>/dev/null; then
        python manage.py runserver 0.0.0.0:${port} &
    fi
    
    PY_PID=$!
    echo $PY_PID > /data/control/preview.pid
    
    # Wait and open browser
    sleep 3
    chromium-browser --display=${DISPLAY} --no-sandbox --disable-gpu \
        --window-size=1280,800 --window-position=100,100 \
        "http://localhost:${port}" &
    
    echo "[PREVIEW] Python web app started (PID: ${PY_PID})"
}

# ===== Main =====

if [ ! -d "${OUTPUT_DIR}" ]; then
    echo "[PREVIEW] Output directory not found: ${OUTPUT_DIR}"
    exit 1
fi

PROJECT_TYPE=$(detect_project_type "${OUTPUT_DIR}")
echo "[PREVIEW] Detected project type: ${PROJECT_TYPE}"

case "${PROJECT_TYPE}" in
    webapp|nodejs)
        start_webapp_preview "${OUTPUT_DIR}"
        ;;
    electron)
        start_electron_preview "${OUTPUT_DIR}"
        ;;
    python-web)
        start_python_web_preview "${OUTPUT_DIR}"
        ;;
    python-cli|rust-cli|go-cli|unknown)
        start_cli_preview "${OUTPUT_DIR}" "${PROJECT_TYPE}"
        ;;
    tauri)
        start_cli_preview "${OUTPUT_DIR}" "${PROJECT_TYPE}"
        echo "[PREVIEW] Note: Tauri preview requires cargo tauri dev"
        ;;
    *)
        echo "[PREVIEW] Unknown project type, opening terminal..."
        start_cli_preview "${OUTPUT_DIR}" "CLI"
        ;;
esac

echo "[PREVIEW] Preview started successfully"
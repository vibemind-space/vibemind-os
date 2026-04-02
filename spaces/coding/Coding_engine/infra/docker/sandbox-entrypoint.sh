#!/bin/bash
# sandbox-entrypoint.sh - Flexible entrypoint for sandbox testing
#
# Environment variables:
#   PROJECT_TYPE: electron, react, node_api, python_fastapi, python_flask, fullstack
#   INSTALL_CMD: Custom install command (default: auto-detected)
#   BUILD_CMD: Custom build command (default: auto-detected)
#   START_CMD: Custom start command (default: auto-detected)
#   HEALTH_URL: Custom health check URL
#   ENABLE_VNC: Enable VNC streaming (true/false)
#   VNC_PORT: VNC server port (default: 5900)
#   NOVNC_PORT: noVNC web port (default: 6080)

set +e  # Don't exit on errors — keep container alive for debugging

echo "=== Sandbox Test Starting ==="
echo "Project Type: ${PROJECT_TYPE:-auto}"
echo "Working Directory: $(pwd)"
echo "VNC Enabled: ${ENABLE_VNC:-false}"

# Store the app URL for browser opening
APP_URL=""

# Error reporting to Coding Engine API
# ENGINE_API_URL: URL of the Coding Engine API (default: host.docker.internal:8000)
# PROJECT_ID: Unique project identifier for error correlation
ENGINE_API_URL="${ENGINE_API_URL:-http://host.docker.internal:8000}"
PROJECT_ID="${PROJECT_ID:-$(basename $(pwd))}"
CONTAINER_NAME="${CONTAINER_NAME:-unknown}"

# Report errors to the Coding Engine for auto-fix
report_error() {
    local error_type="$1"
    local error_output="$2"
    local exit_code="${3:-1}"

    echo "=== Reporting Error to Coding Engine ==="
    echo "Error Type: $error_type"
    echo "Project ID: $PROJECT_ID"

    # Escape special characters for JSON
    local escaped_output=$(echo "$error_output" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')

    # Build JSON payload
    local payload=$(cat <<EOF
{
    "project_id": "$PROJECT_ID",
    "container_name": "$CONTAINER_NAME",
    "error_type": "$error_type",
    "build_output": "$escaped_output",
    "exit_code": $exit_code,
    "working_dir": "$(pwd)",
    "project_type": "$PROJECT_TYPE"
}
EOF
)

    # POST to the Engine API
    local response=$(curl -sf -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "${ENGINE_API_URL}/api/v1/dashboard/sandbox/report-error" 2>&1 || echo "CURL_FAILED")

    if [ "$response" = "CURL_FAILED" ]; then
        echo "Warning: Could not reach Coding Engine API at ${ENGINE_API_URL}"
        echo "Error reporting skipped - manual fix required"
    else
        echo "Error reported to Coding Engine"
        echo "Response: $response"
    fi
    echo "=================================="
}

# ============================================
# Package.json change detection for auto-reinstall
# ============================================
PACKAGE_JSON_CHECKSUM=""

# Compute and store package.json checksum
compute_package_checksum() {
    if [ -f "package.json" ]; then
        PACKAGE_JSON_CHECKSUM=$(md5sum package.json 2>/dev/null | cut -d' ' -f1)
        echo "Stored package.json checksum: $PACKAGE_JSON_CHECKSUM"
    fi
}

# Check if package.json has changed since last checksum
check_deps_changed() {
    if [ -f "package.json" ] && [ -n "$PACKAGE_JSON_CHECKSUM" ]; then
        local current_checksum=$(md5sum package.json 2>/dev/null | cut -d' ' -f1)
        if [ "$current_checksum" != "$PACKAGE_JSON_CHECKSUM" ]; then
            echo "package.json changed - dependencies need reinstall"
            echo "  Old checksum: $PACKAGE_JSON_CHECKSUM"
            echo "  New checksum: $current_checksum"
            return 0  # Changed
        fi
    fi
    return 1  # Not changed
}

# Reinstall dependencies if package.json changed
# Always returns 0 to avoid triggering set -e
reinstall_deps_if_changed() {
    if check_deps_changed; then
        echo "=== Reinstalling Dependencies (package.json changed) ==="
        rm -rf node_modules 2>/dev/null || true
        npm install --legacy-peer-deps 2>&1 || npm install 2>&1
        compute_package_checksum  # Update checksum after install
        echo "Dependencies reinstalled successfully"
    fi
    return 0  # Always succeed - no change needed is also success
}

# Start Xvfb if needed (for GUI apps or VNC browser display)
start_xvfb() {
    # Clean stale lock files from previous runs
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null
    if ! pgrep -x Xvfb > /dev/null; then
        echo "Starting Xvfb..."
        Xvfb :99 -screen 0 1280x800x24 &
        sleep 2
    fi
    export DISPLAY=:99
}

# Start VNC server for screen streaming (shares Xvfb display)
# This function is idempotent - safe to call multiple times
start_vnc() {
    if [ "$ENABLE_VNC" = "true" ]; then
        # Check if VNC is already running
        if pgrep -x "x11vnc" > /dev/null; then
            echo "VNC already running, skipping start"
            return 0
        fi

        echo "=== Starting VNC Screen Streaming ==="

        # Ensure Xvfb is running
        start_xvfb

        # Start x11vnc connected to Xvfb display :99
        x11vnc -display :99 -nopw -forever -shared -rfbport ${VNC_PORT:-5900} -bg -o /tmp/x11vnc.log
        sleep 1

        # Start noVNC websocket proxy for browser access
        websockify --web=/usr/share/novnc ${NOVNC_PORT:-6080} localhost:${VNC_PORT:-5900} &
        sleep 1

        echo "VNC server started on port ${VNC_PORT:-5900}"
        echo "noVNC available at: http://localhost:${NOVNC_PORT:-6080}/vnc.html"
        echo "=================================="
    fi
}

# Global variable to track loading browser PID
LOADING_BROWSER_PID=""

# Start a loading page browser early (before app is ready)
start_loading_browser() {
    if [ "$ENABLE_VNC" = "true" ] && [ "$PROJECT_TYPE" != "electron" ]; then
        echo "=== Starting Loading Browser for VNC Display ==="

        # Create a simple loading HTML page
        cat > /tmp/loading.html << 'LOADINGEOF'
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .spinner {
            width: 50px;
            height: 50px;
            border: 3px solid rgba(255,255,255,0.1);
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        h1 { font-size: 24px; font-weight: 300; margin: 0; }
        p { color: #888; margin-top: 10px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="spinner"></div>
    <h1>Building Application...</h1>
    <p>The live preview will appear when the app is ready</p>
</body>
</html>
LOADINGEOF

        # Start Chromium with loading page
        chromium \
            --no-sandbox \
            --disable-gpu \
            --disable-software-rasterizer \
            --disable-dev-shm-usage \
            --disable-extensions \
            --window-size=1280,800 \
            --window-position=0,0 \
            --start-maximized \
            --kiosk \
            --app="file:///tmp/loading.html" \
            --display=:99 \
            &

        LOADING_BROWSER_PID=$!
        echo "Loading browser started with PID: $LOADING_BROWSER_PID"
        echo "=================================="
    fi
}

# Start Chromium browser with app URL for VNC display (for web apps)
start_browser_for_vnc() {
    if [ "$ENABLE_VNC" = "true" ] && [ -n "$APP_URL" ] && [ "$PROJECT_TYPE" != "electron" ]; then
        echo "=== Starting Chromium Browser for VNC Display ==="
        echo "Opening: $APP_URL"

        # Kill the loading browser if it's running
        if [ -n "$LOADING_BROWSER_PID" ] && kill -0 "$LOADING_BROWSER_PID" 2>/dev/null; then
            echo "Killing loading browser (PID: $LOADING_BROWSER_PID)"
            kill "$LOADING_BROWSER_PID" 2>/dev/null || true
            sleep 1
        fi

        # Start Chromium in kiosk mode with the app URL
        chromium \
            --no-sandbox \
            --disable-gpu \
            --disable-software-rasterizer \
            --disable-dev-shm-usage \
            --disable-extensions \
            --window-size=1280,800 \
            --window-position=0,0 \
            --start-maximized \
            --kiosk \
            --app="$APP_URL" \
            --display=:99 \
            &

        BROWSER_PID=$!
        echo "Chromium started with PID: $BROWSER_PID"
        echo "Browser displaying app at: $APP_URL"
        echo "=================================="
    fi
}

# Auto-detect project type
detect_project_type() {
    # Check tech_stack.json first (generated by Coding Engine)
    TECH_STACK_FILE=$(find /workspace -maxdepth 5 -name "tech_stack.json" -path "*/tech_stack/*" 2>/dev/null | head -1)
    if [ -n "$TECH_STACK_FILE" ]; then
        FRONTEND_FW=$(python3 -c "import json; print(json.load(open('$TECH_STACK_FILE')).get('frontend_framework',''))" 2>/dev/null || echo "")
        BACKEND_FW=$(python3 -c "import json; print(json.load(open('$TECH_STACK_FILE')).get('backend_framework',''))" 2>/dev/null || echo "")
        echo "Tech stack detected: frontend=$FRONTEND_FW backend=$BACKEND_FW" >&2
        case "$FRONTEND_FW" in
            *"React Native"*|*"Expo"*)
                echo "mobile"
                return ;;
            *"Flutter"*)
                echo "flutter_web"
                return ;;
        esac
        case "$BACKEND_FW" in
            *"NestJS"*|*"Express"*|*"Fastify"*)
                echo "node_api"
                return ;;
            *"FastAPI"*|*"Django"*)
                echo "python_fastapi"
                return ;;
        esac
    fi

    # Check for fullstack: has both package.json (frontend) AND Python API
    if [ -f "package.json" ] && [ -f "requirements.txt" ]; then
        # Check if it's actually a React + Python API project
        if grep -q '"vite"' package.json 2>/dev/null || grep -q '"react"' package.json 2>/dev/null; then
            if grep -q "fastapi" requirements.txt 2>/dev/null || grep -q "flask" requirements.txt 2>/dev/null; then
                echo "fullstack"
                return
            fi
        fi
    fi

    # Also check for api/ subdirectory with Python
    if [ -f "package.json" ] && [ -d "api" ] && [ -f "api/requirements.txt" ]; then
        echo "fullstack"
        return
    fi

    if [ -f "package.json" ]; then
        if grep -q '"electron"' package.json 2>/dev/null; then
            echo "electron"
        # Node.js fullstack: has BOTH express/fastify AND vite/react in same package.json
        elif grep -q '"express"' package.json 2>/dev/null || grep -q '"fastify"' package.json 2>/dev/null; then
            if grep -q '"vite"' package.json 2>/dev/null || grep -q '"react"' package.json 2>/dev/null; then
                echo "node_fullstack"
                return
            fi
            echo "node_api"
        elif grep -q '"vite"' package.json 2>/dev/null || grep -q '"@vitejs"' package.json 2>/dev/null; then
            echo "react"
        elif grep -q '"next"' package.json 2>/dev/null; then
            echo "react"
        else
            echo "react"  # Default for npm projects
        fi
    elif [ -f "requirements.txt" ]; then
        if grep -q "fastapi" requirements.txt 2>/dev/null; then
            echo "python_fastapi"
        elif grep -q "flask" requirements.txt 2>/dev/null; then
            echo "python_flask"
        else
            echo "python_fastapi"  # Default for Python
        fi
    elif [ -f "pyproject.toml" ]; then
        echo "python_fastapi"
    else
        echo "unknown"
    fi
}

# Get project type
if [ -z "$PROJECT_TYPE" ]; then
    PROJECT_TYPE=$(detect_project_type)
    echo "Auto-detected project type: $PROJECT_TYPE"
fi

# Install dependencies
install_deps() {
    echo "=== Installing Dependencies ==="
    if [ -n "$INSTALL_CMD" ]; then
        echo "Running custom install: $INSTALL_CMD"
        eval $INSTALL_CMD
    elif [ "$PROJECT_TYPE" = "fullstack" ]; then
        # Fullstack: install BOTH npm and pip dependencies
        echo "Fullstack project detected - installing both npm and pip dependencies"

        # Install npm dependencies
        # IMPORTANT: Don't try to rm -rf node_modules on Windows mounts - it takes forever
        # Use --force to ignore platform-specific package errors (like @rollup/rollup-win32-x64-msvc)
        if [ -f "package.json" ]; then
            echo "Running npm install with platform compatibility flags..."
            npm install --force --legacy-peer-deps --no-optional 2>&1 || {
                echo "npm install with --force failed, trying minimal install..."
                npm install --ignore-scripts --legacy-peer-deps 2>&1 || {
                    echo "Warning: npm install had issues, continuing anyway..."
                }
            }

            # Fix platform-specific packages for Linux container
            echo "Installing Linux-specific platform packages..."
            if [ -d "node_modules/rollup" ]; then
                npm install @rollup/rollup-linux-x64-gnu --force --no-save 2>/dev/null || true
            fi
            if [ -d "node_modules/esbuild" ]; then
                npm install @esbuild/linux-x64 --force --no-save 2>/dev/null || true
            fi
            if [ -d "node_modules/@swc/core" ]; then
                npm install @swc/core-linux-x64-gnu --force --no-save 2>/dev/null || true
            fi
            echo "npm dependencies installed."
        fi

        # Install pip dependencies
        if [ -f "requirements.txt" ]; then
            pip3 install -q --break-system-packages -r requirements.txt
            echo "pip dependencies installed."
        elif [ -d "api" ] && [ -f "api/requirements.txt" ]; then
            pip3 install -q --break-system-packages -r api/requirements.txt
            echo "pip dependencies installed from api/."
        fi
    elif [ -f "package.json" ]; then
        # IMPORTANT: On Windows-mounted volumes, ANY file operation on node_modules is extremely slow
        # (rm, mv, even ls can take minutes). The solution is to NEVER touch existing node_modules.
        # Also, package.json may contain Windows-specific packages that fail on Linux.
        # Use --force to ignore platform mismatches (like @rollup/rollup-win32-x64-msvc)
        echo "Running npm install with platform compatibility flags..."
        # --force: ignore platform-specific package errors
        # --legacy-peer-deps: handle peer dependency conflicts
        # --no-optional: skip optional dependencies
        npm install --force --legacy-peer-deps --no-optional 2>&1 || {
            echo "npm install with --force failed, trying minimal install..."
            npm install --ignore-scripts --legacy-peer-deps 2>&1 || {
                echo "Warning: npm install had issues, continuing anyway..."
            }
        }

        # Fix platform-specific packages: Windows node_modules needs Linux binaries for rollup/esbuild
        # This is a common issue when mounting Windows project folders into Linux containers
        echo "Installing Linux-specific platform packages..."
        # Check if rollup is installed and install the correct platform package
        if [ -d "node_modules/rollup" ]; then
            npm install @rollup/rollup-linux-x64-gnu --force --no-save 2>/dev/null || true
        fi
        # Check if esbuild is installed and install the correct platform package
        if [ -d "node_modules/esbuild" ]; then
            npm install @esbuild/linux-x64 --force --no-save 2>/dev/null || true
        fi
        # Check if @swc/core is installed and install the correct platform package
        if [ -d "node_modules/@swc/core" ]; then
            npm install @swc/core-linux-x64-gnu --force --no-save 2>/dev/null || true
        fi
    elif [ -f "requirements.txt" ]; then
        pip3 install -q --break-system-packages -r requirements.txt
    elif [ -f "pyproject.toml" ]; then
        pip3 install -q --break-system-packages .
    fi

    # Store package.json checksum for change detection
    compute_package_checksum

    echo "Dependencies installed."
}

# Run database migrations (Prisma, Drizzle, etc.)
run_database_migrations() {
    echo "=== Running Database Migrations ==="
    local migration_output=""
    local migration_exit_code=0

    # Check for Prisma
    if [ -f "prisma/schema.prisma" ]; then
        echo "Prisma schema detected - running prisma db push..."

        # Wait for PostgreSQL to be ready (if DATABASE_URL is set)
        if [ -n "$DATABASE_URL" ]; then
            echo "Waiting for database to be ready..."
            local max_wait=30
            local waited=0
            while [ $waited -lt $max_wait ]; do
                if npx prisma db execute --stdin <<< "SELECT 1" 2>/dev/null; then
                    echo "Database is ready!"
                    break
                fi
                sleep 2
                waited=$((waited + 2))
                echo "Waiting for database... ($waited/$max_wait seconds)"
            done
        fi

        # Generate Prisma client
        echo "Generating Prisma client..."
        npx prisma generate 2>&1 || true

        # Push schema to database
        echo "Pushing schema to database..."
        migration_output=$(npx prisma db push --accept-data-loss 2>&1) || migration_exit_code=$?

        if [ $migration_exit_code -ne 0 ]; then
            echo "=== Prisma Migration FAILED ==="
            echo "$migration_output"
            report_error "database_migration_failed" "$migration_output" $migration_exit_code
            return 1
        fi

        echo "Prisma schema pushed successfully"
        echo "$migration_output"
    fi

    # Check for Drizzle
    if [ -f "drizzle.config.ts" ] || [ -f "drizzle.config.js" ]; then
        echo "Drizzle config detected - running drizzle push..."
        migration_output=$(npx drizzle-kit push 2>&1) || migration_exit_code=$?

        if [ $migration_exit_code -ne 0 ]; then
            echo "=== Drizzle Migration FAILED ==="
            echo "$migration_output"
            report_error "database_migration_failed" "$migration_output" $migration_exit_code
            return 1
        fi
        echo "Drizzle schema pushed successfully"
    fi

    echo "Database migrations complete."
    return 0
}

# Track reported errors to avoid duplicates
REPORTED_DB_ERRORS=""

# Monitor app output for database errors and report them
monitor_database_errors() {
    local log_file="/tmp/app_runtime.log"

    # Database error patterns
    local db_patterns=(
        "column .* does not exist"
        "relation .* does not exist"
        "ECONNREFUSED.*5432"
        "P1001.*Can't reach database"
        "P2002.*Unique constraint"
        "P2003.*Foreign key constraint"
        "P2025.*Record to .* not found"
        "PrismaClientKnownRequestError"
        "Invalid.*prisma.*invocation"
    )

    # Check app logs for database errors
    if [ -f "$log_file" ]; then
        for pattern in "${db_patterns[@]}"; do
            local matches=$(grep -iE "$pattern" "$log_file" 2>/dev/null | head -5)
            if [ -n "$matches" ]; then
                # Create a hash of the error to avoid duplicate reports
                local error_hash=$(echo "$matches" | md5sum | cut -d' ' -f1)

                # Check if already reported
                if [[ "$REPORTED_DB_ERRORS" != *"$error_hash"* ]]; then
                    echo "=== Database Runtime Error Detected ==="
                    echo "$matches"
                    report_error "database_runtime_error" "$matches" 1
                    REPORTED_DB_ERRORS="$REPORTED_DB_ERRORS $error_hash"
                fi
            fi
        done
    fi
}

# Build project (with error reporting to Coding Engine)
build_project() {
    echo "=== Building Project ==="
    local build_output=""
    local build_exit_code=0

    if [ -n "$BUILD_CMD" ]; then
        echo "Running custom build: $BUILD_CMD"
        # Capture build output and exit code
        build_output=$(eval $BUILD_CMD 2>&1) || build_exit_code=$?
    elif [ -f "package.json" ]; then
        if grep -q '"build"' package.json; then
            # Capture build output and exit code
            build_output=$(npm run build 2>&1) || build_exit_code=$?
        fi
    fi

    # Check if build failed
    if [ $build_exit_code -ne 0 ]; then
        echo "=== Build FAILED (exit code: $build_exit_code) ==="
        echo "$build_output"

        # Report error to Coding Engine for auto-fix
        report_error "build_failed" "$build_output" $build_exit_code

        # Don't exit - let the system try to fix it
        # The ContinuousDebugAgent will sync fixes and trigger rebuild
        echo "Waiting for auto-fix from Coding Engine..."
        return 1
    fi

    echo "$build_output"
    echo "Build complete."
    return 0
}

# Start mobile preview (Expo Web + Android Emulator)
# Smart detection: checks actual project structure, not just tech_stack.json
start_mobile_preview() {
    echo "=== Starting Mobile Preview ==="

    # Find the generated project directory
    PROJECT_DIR=$(find /workspace/app -maxdepth 2 -name "package.json" -not -path "*/node_modules/*" -exec dirname {} \; 2>/dev/null | head -1)
    if [ -z "$PROJECT_DIR" ]; then
        echo "No project found in /workspace/app"
        return 1
    fi
    cd "$PROJECT_DIR"
    echo "Project dir: $PROJECT_DIR"

    # Start VNC for emulator display
    start_vnc

    # ─── Detect actual frontend type ─────────────────────────────
    HAS_EXPO=false
    HAS_VITE_FRONTEND=false
    HAS_NESTJS=false
    FRONTEND_PORT=3100
    FRONTEND_URL=""

    # Check for Expo
    if [ -f "app.json" ] || [ -f "app.config.js" ]; then
        HAS_EXPO=true
    fi
    if grep -q '"expo"' package.json 2>/dev/null; then
        HAS_EXPO=true
    fi

    # Check for Vite frontend in /frontend subdirectory
    if [ -f "frontend/package.json" ] && [ -f "frontend/vite.config.ts" -o -f "frontend/vite.config.js" ]; then
        HAS_VITE_FRONTEND=true
    fi

    # Check for NestJS backend
    if grep -q '"@nestjs/core"' package.json 2>/dev/null; then
        HAS_NESTJS=true
    fi

    echo "Detected: expo=$HAS_EXPO vite_frontend=$HAS_VITE_FRONTEND nestjs=$HAS_NESTJS"

    # ─── Start NestJS Backend (port 3000 → mapped to 3201) ──────
    if [ "$HAS_NESTJS" = true ]; then
        echo "Installing NestJS backend dependencies..."
        npm install --legacy-peer-deps 2>&1 | tail -5

        # Generate Prisma client from schema (use prisma/ dir schema, not root)
        if [ -f "prisma/schema.prisma" ]; then
            echo "Running prisma generate..."
            npx prisma generate --schema=prisma/schema.prisma 2>&1 | tail -3

            # Auto-create app-specific DB if .env has a unique DATABASE_URL
            if grep -q 'DATABASE_URL' .env 2>/dev/null; then
                DB_NAME=$(grep 'DATABASE_URL' .env | head -1 | grep -oP '/(\w+)$' | tr -d '/' || echo "")
                if [ -n "$DB_NAME" ] && [ "$DB_NAME" != "coding_engine" ]; then
                    echo "Ensuring database '$DB_NAME' exists..."
                    PGPASSWORD=postgres psql -h postgres -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1 || \
                        PGPASSWORD=postgres psql -h postgres -U postgres -c "CREATE DATABASE $DB_NAME" 2>/dev/null
                    echo "Pushing Prisma schema to $DB_NAME..."
                    npx prisma db push --accept-data-loss 2>&1 | tail -3
                fi
            fi
        fi

        # Build first (nest start --watch doesn't work reliably on Docker volumes)
        echo "Building NestJS..."
        npm run build 2>&1 | tail -3

        echo "Starting NestJS backend on port 3000..."
        node dist/main.js 2>&1 | tee /tmp/nestjs.log &
        NEST_PID=$!
        echo "NestJS started (PID: $NEST_PID)"

        # Wait for NestJS to be ready
        for i in $(seq 1 15); do
            if curl -sf http://localhost:3000/health > /dev/null 2>&1 || curl -sf http://localhost:3000/ > /dev/null 2>&1; then
                echo "NestJS is ready!"
                break
            fi
            sleep 2
        done
    fi

    # ─── Start Frontend ──────────────────────────────────────────
    if [ "$HAS_VITE_FRONTEND" = true ]; then
        echo "=== Starting Vite Frontend ==="
        cd frontend
        echo "Installing frontend dependencies..."
        npm install --legacy-peer-deps 2>&1 | tail -5

        # Start Vite dev server on port 3100 (mapped to host)
        echo "Starting Vite dev server on port $FRONTEND_PORT..."
        npx vite --host 0.0.0.0 --port $FRONTEND_PORT 2>&1 | tee /tmp/frontend.log &
        FE_PID=$!
        FRONTEND_URL="http://localhost:$FRONTEND_PORT"
        echo "Vite frontend started (PID: $FE_PID)"
        cd "$PROJECT_DIR"

    elif [ "$HAS_EXPO" = true ]; then
        echo "=== Starting Expo Web ==="
        # Install deps + Expo Web requirements
        echo "Installing Expo dependencies..."
        npm install --legacy-peer-deps 2>&1 | tail -5
        npm install expo react-dom react-native-web @expo/metro-runtime 2>&1 | tail -3

        # Start Expo Web on port 3100
        echo "Starting Expo Web on port $FRONTEND_PORT..."
        npx expo start --web --port $FRONTEND_PORT --non-interactive 2>&1 | tee /tmp/expo.log &
        FE_PID=$!
        FRONTEND_URL="http://localhost:$FRONTEND_PORT"
        echo "Expo Web started (PID: $FE_PID)"

    else
        echo "No frontend detected — serving static files"
        npx serve -s /workspace/app -l $FRONTEND_PORT -C &
        FE_PID=$!
        FRONTEND_URL="http://localhost:$FRONTEND_PORT"
    fi

    # ─── Start Android Emulator (VNC) ───────────────────────────
    if [ -e /dev/kvm ] && [ -d "${ANDROID_HOME}/emulator" ]; then
        echo "Starting Android Emulator (KVM available)..."
        rm -rf /root/.android/avd/sandbox.avd/*.lock 2>/dev/null
        ${ANDROID_HOME}/emulator/emulator -avd sandbox \
            -no-audio -no-boot-anim -gpu swiftshader_indirect \
            -skin 1080x2340 -no-snapshot -read-only \
            2>&1 | tee /tmp/emulator.log &
        EMU_PID=$!

        echo "Waiting for emulator to boot..."
        ${ANDROID_HOME}/platform-tools/adb wait-for-device 2>/dev/null
        sleep 10

        # Unlock screen
        ${ANDROID_HOME}/platform-tools/adb shell input keyevent 82 2>/dev/null

        # Install Expo Go if APK exists and project is Expo
        if [ "$HAS_EXPO" = true ] && [ -f /opt/expo-go.apk ]; then
            echo "Installing Expo Go..."
            ${ANDROID_HOME}/platform-tools/adb install /opt/expo-go.apk 2>/dev/null || true
            ${ANDROID_HOME}/platform-tools/adb shell am start -a android.intent.action.VIEW \
                -d "exp://localhost:19000" 2>/dev/null || true
        fi

        # Open Chromium with the frontend URL in the emulator
        if [ -n "$FRONTEND_URL" ] && [ "$HAS_EXPO" = false ]; then
            echo "Opening Chromium in VNC with $FRONTEND_URL"
            # Point the kiosk browser at the app
            pkill -f "chromium.*kiosk" 2>/dev/null || true
            sleep 2
            chromium $CHROMIUM_FLAGS --kiosk --app="$FRONTEND_URL" --display=:99 &
        fi

        echo "Android Emulator started (PID: $EMU_PID)"
    else
        echo "KVM not available — Emulator skipped"
        # Point Chromium at the frontend
        if [ -n "$FRONTEND_URL" ]; then
            echo "Opening Chromium in VNC with $FRONTEND_URL"
            pkill -f "chromium.*kiosk" 2>/dev/null || true
            sleep 2
            chromium $CHROMIUM_FLAGS --kiosk --app="$FRONTEND_URL" --display=:99 &
        fi
    fi

    echo ""
    echo "=== Preview Ready ==="
    echo "  Frontend:  $FRONTEND_URL"
    if [ "$HAS_NESTJS" = true ]; then
        echo "  Backend:   http://localhost:3000 (API)"
    fi
    echo "  VNC:       http://localhost:${NOVNC_PORT}/vnc.html"
    echo ""

    # Keep container alive with status logging + auto-restart
    NEST_FAIL_COUNT=0
    FE_FAIL_COUNT=0
    while true; do
        sleep 30
        EMU_BOOT=$(${ANDROID_HOME}/platform-tools/adb shell getprop sys.boot_completed 2>/dev/null || echo "0")
        FE_UP=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null || echo "000")
        NEST_UP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
        echo "[status] emulator_booted=${EMU_BOOT} frontend=${FE_UP} nestjs=${NEST_UP}"

        # Auto-restart NestJS if crashed (3 consecutive failures)
        if [ "$HAS_NESTJS" = true ] && [ "$NEST_UP" = "000" ]; then
            NEST_FAIL_COUNT=$((NEST_FAIL_COUNT + 1))
            if [ $NEST_FAIL_COUNT -ge 3 ]; then
                echo "[health] NestJS down for 90s, restarting..."
                cd "$PROJECT_DIR"
                node dist/main.js 2>&1 | tee /tmp/nestjs.log &
                NEST_PID=$!
                NEST_FAIL_COUNT=0
            fi
        else
            NEST_FAIL_COUNT=0
        fi

        # Auto-restart Vite if crashed
        if [ "$HAS_VITE_FRONTEND" = true ] && [ "$FE_UP" = "000" ]; then
            FE_FAIL_COUNT=$((FE_FAIL_COUNT + 1))
            if [ $FE_FAIL_COUNT -ge 3 ]; then
                echo "[health] Vite frontend down for 90s, restarting..."
                cd "$PROJECT_DIR/frontend"
                npx vite --host 0.0.0.0 --port $FRONTEND_PORT 2>&1 | tee /tmp/frontend.log &
                FE_PID=$!
                cd "$PROJECT_DIR"
                FE_FAIL_COUNT=0
            fi
        else
            FE_FAIL_COUNT=0
        fi
    done
}

# Start application
start_app() {
    echo "=== Starting Application ==="

    case "$PROJECT_TYPE" in
        mobile)
            start_mobile_preview
            return
            ;;
        fullstack)
            echo "=== Starting Fullstack Application (Python API + React Frontend) ==="
            start_vnc  # Start VNC for browser display

            # Initialize log file for runtime error detection
            echo "=== Application Runtime Log ===" > /tmp/app_runtime.log
            echo "Started at: $(date)" >> /tmp/app_runtime.log

            # Step 1: Start the Python API backend first
            echo "Starting Python API backend..."
            if [ -f "main.py" ]; then
                uvicorn main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /tmp/app_runtime.log &
                API_PID=$!
            elif [ -f "app/main.py" ]; then
                uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /tmp/app_runtime.log &
                API_PID=$!
            elif [ -f "api/main.py" ]; then
                uvicorn api.main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /tmp/app_runtime.log &
                API_PID=$!
            elif [ -f "src/api/main.py" ]; then
                uvicorn src.api.main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /tmp/app_runtime.log &
                API_PID=$!
            fi
            echo "API started with PID: ${API_PID:-unknown}"

            # Give API time to start
            sleep 2

            # Step 2: Start the React/Vite frontend
            echo "Starting React frontend..."
            if grep -q '"dev"' package.json 2>/dev/null; then
                npm run dev -- --host 2>&1 | tee -a /tmp/app_runtime.log &
            elif grep -q '"preview"' package.json 2>/dev/null; then
                npm run preview -- --host 2>&1 | tee -a /tmp/app_runtime.log &
            elif grep -q '"start"' package.json 2>/dev/null; then
                npm start 2>&1 | tee -a /tmp/app_runtime.log &
            else
                npx serve -s dist -l 5173 2>&1 | tee -a /tmp/app_runtime.log &
            fi
            FRONTEND_PID=$!
            echo "Frontend started with PID: $FRONTEND_PID"

            # Set APP_URL to frontend (what user wants to see)
            APP_URL="http://localhost:5173"
            APP_PID=$FRONTEND_PID
            echo "API running at: http://localhost:8000"
            echo "Frontend running at: $APP_URL"
            ;;
        node_fullstack)
            echo "=== Starting Node.js Fullstack Application (Express + React) ==="
            start_vnc  # Start VNC for browser display

            # Initialize log file for runtime error detection
            echo "=== Application Runtime Log ===" > /tmp/app_runtime.log
            echo "Started at: $(date)" >> /tmp/app_runtime.log

            # For Node.js fullstack, prefer npm run dev which typically runs both
            # via concurrently or similar
            echo "Starting Node.js fullstack with npm run dev..."
            if grep -q '"dev"' package.json 2>/dev/null; then
                npm run dev -- --host 2>&1 | tee -a /tmp/app_runtime.log &
            elif grep -q '"start"' package.json 2>/dev/null; then
                npm start 2>&1 | tee -a /tmp/app_runtime.log &
            else
                # Fallback: try starting both manually
                echo "Fallback: starting express and vite separately..."
                if grep -q '"dev:backend"' package.json 2>/dev/null; then
                    npm run dev:backend 2>&1 | tee -a /tmp/app_runtime.log &
                fi
                sleep 2
                if grep -q '"dev:frontend"' package.json 2>/dev/null; then
                    npm run dev:frontend -- --host 2>&1 | tee -a /tmp/app_runtime.log &
                else
                    npm run dev -- --host 2>&1 | tee -a /tmp/app_runtime.log &
                fi
            fi
            APP_PID=$!
            echo "Node.js fullstack started with PID: $APP_PID"

            # For node_fullstack, frontend is typically on 5173
            APP_URL="http://localhost:5173"
            echo "Application URL: $APP_URL"
            ;;
        electron)
            start_xvfb
            start_vnc  # Start VNC streaming if enabled
            if [ -n "$START_CMD" ]; then
                eval $START_CMD &
            elif grep -q '"start"' package.json; then
                xvfb-run --auto-servernum npm start &
            elif grep -q '"preview"' package.json; then
                npm run preview -- --host &
            fi
            APP_URL=""  # Electron doesn't use HTTP URL
            ;;
        react)
            start_vnc  # Start VNC for browser display
            if [ -n "$START_CMD" ]; then
                eval $START_CMD &
            elif grep -q '"preview"' package.json; then
                npm run preview -- --host &
            elif grep -q '"start"' package.json; then
                npm start &
            else
                # Serve the build directory
                npx serve -s dist -l 5173 &
            fi
            APP_URL="http://localhost:5173"
            ;;
        node_api)
            start_vnc  # Start VNC for browser display
            if [ -n "$START_CMD" ]; then
                eval $START_CMD &
            elif grep -q '"start"' package.json; then
                npm start &
            else
                node index.js &
            fi
            APP_URL="http://localhost:3000"
            ;;
        python_fastapi)
            start_vnc  # Start VNC for browser display
            if [ -n "$START_CMD" ]; then
                eval $START_CMD &
            else
                # Find main app file
                if [ -f "main.py" ]; then
                    uvicorn main:app --host 0.0.0.0 --port 8000 &
                elif [ -f "app/main.py" ]; then
                    uvicorn app.main:app --host 0.0.0.0 --port 8000 &
                elif [ -f "src/api/main.py" ]; then
                    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
                elif [ -f "src/main.py" ]; then
                    uvicorn src.main:app --host 0.0.0.0 --port 8000 &
                fi
            fi
            APP_URL="http://localhost:8000"
            ;;
        python_flask)
            start_vnc  # Start VNC for browser display
            if [ -n "$START_CMD" ]; then
                eval $START_CMD &
            else
                if [ -f "app.py" ]; then
                    gunicorn -b 0.0.0.0:5000 app:app &
                elif [ -f "main.py" ]; then
                    gunicorn -b 0.0.0.0:5000 main:app &
                fi
            fi
            APP_URL="http://localhost:5000"
            ;;
        *)
            start_vnc  # Start VNC for browser display
            echo "Unknown project type, attempting generic start..."
            if [ -f "package.json" ] && grep -q '"start"' package.json; then
                npm start &
            fi
            APP_URL="http://localhost:3000"
            ;;
    esac

    APP_PID=$!
    echo "Application started with PID: $APP_PID"
    if [ -n "$APP_URL" ]; then
        echo "Application URL: $APP_URL"
    fi
}

# Health check
check_health() {
    echo "=== Health Check ==="
    local max_attempts=30
    local attempt=1
    local health_url="${HEALTH_URL:-}"

    # Default health URLs based on project type
    if [ -z "$health_url" ]; then
        case "$PROJECT_TYPE" in
            electron)
                # For Electron, just check if process is running
                health_url=""
                ;;
            fullstack)
                # For fullstack, check frontend first (user-facing)
                health_url="http://localhost:5173"
                ;;
            node_fullstack)
                # For Node.js fullstack, check frontend first (user-facing)
                health_url="http://localhost:5173"
                ;;
            react)
                health_url="http://localhost:5173"
                ;;
            node_api)
                health_url="http://localhost:3000/health"
                ;;
            python_fastapi)
                health_url="http://localhost:8000/health"
                ;;
            python_flask)
                health_url="http://localhost:5000/"
                ;;
            *)
                health_url="http://localhost:3000"
                ;;
        esac
    fi

    # For Electron, just check process
    if [ "$PROJECT_TYPE" = "electron" ]; then
        sleep 5
        if ps -p $APP_PID > /dev/null 2>&1; then
            echo "Electron app is running"
            return 0
        else
            echo "Electron app failed to start"
            return 1
        fi
    fi

    # For web apps, check HTTP endpoint
    while [ $attempt -le $max_attempts ]; do
        echo "Health check attempt $attempt/$max_attempts: $health_url"
        if curl -sf "$health_url" > /dev/null 2>&1; then
            echo "Health check PASSED!"
            # Store the working URL for browser
            APP_URL="$health_url"
            return 0
        fi

        # Also try common alternative URLs
        for alt_url in "http://localhost:5173" "http://localhost:3000" "http://localhost:4173" "http://localhost:8000" "http://localhost:5000"; do
            if [ "$alt_url" != "$health_url" ]; then
                if curl -sf "$alt_url" > /dev/null 2>&1; then
                    echo "Health check PASSED on $alt_url!"
                    # Store the working URL for browser
                    APP_URL="$alt_url"
                    return 0
                fi
            fi
        done

        sleep 2
        attempt=$((attempt + 1))
    done

    echo "Health check FAILED after $max_attempts attempts"
    return 1
}

# Main execution with auto-fix retry loop
main() {
    local max_fix_attempts=${MAX_FIX_ATTEMPTS:-10}
    local fix_attempt=0
    local build_success=false

    install_deps

    # Start VNC early so it's available for debugging even if build fails
    if [ "$ENABLE_VNC" = "true" ]; then
        echo "=== Starting VNC Early for Debug Access ==="
        start_vnc
        # Show loading page in browser so VNC isn't a black screen
        start_loading_browser
    fi

    # Build with retry loop for auto-fix
    while [ $fix_attempt -lt $max_fix_attempts ]; do
        fix_attempt=$((fix_attempt + 1))
        echo "=== Build Attempt $fix_attempt/$max_fix_attempts ==="

        # Check if package.json changed and reinstall if needed
        # This handles cases where the generation system adds missing dependencies
        reinstall_deps_if_changed

        if build_project; then
            build_success=true
            break
        fi

        # Build failed - wait for fix from Coding Engine
        echo "Build failed. Waiting for auto-fix (30 seconds)..."
        echo "The ContinuousDebugAgent will sync fixed files via docker cp"
        sleep 30

        # Check if files were modified (indicating a fix was applied)
        # This is a simple heuristic - real fix detection could be more sophisticated
        echo "Checking for updated files..."
    done

    if [ "$build_success" = "false" ]; then
        echo "=== Build FAILED after $max_fix_attempts attempts ==="
        echo "Manual intervention required."

        # Keep container running for debugging if VNC enabled
        if [ "$ENABLE_VNC" = "true" ]; then
            echo "VNC enabled - keeping container running for debugging"
            echo "Access via: http://localhost:${NOVNC_PORT:-6080}/vnc.html"
            tail -f /dev/null
        fi
        exit 1
    fi

    # Run database migrations before starting app
    run_database_migrations || {
        echo "Database migration failed - waiting for auto-fix (30 seconds)..."
        sleep 30
        # Retry migration once
        run_database_migrations || {
            echo "Migration still failing - continuing anyway (app may have runtime errors)"
        }
    }

    start_app

    sleep 3  # Give app time to initialize

    if check_health; then
        echo "=== Sandbox Test PASSED ==="

        # Start browser for VNC display after health check passes
        start_browser_for_vnc

        # Keep container running if VNC is enabled
        if [ "$ENABLE_VNC" = "true" ]; then
            echo "VNC enabled - keeping container running for screen streaming"
            echo "Access via: http://localhost:${NOVNC_PORT:-6080}/vnc.html"

            # Start background error monitor to detect runtime database errors
            echo "Starting background database error monitor..."
            while true; do
                sleep 10
                monitor_database_errors
            done &
            MONITOR_PID=$!
            echo "Error monitor started with PID: $MONITOR_PID"

            # Keep running indefinitely for VNC viewing
            tail -f /dev/null
        fi

        exit 0
    else
        echo "=== Sandbox Test FAILED ==="
        # Report runtime/health check failure
        report_error "test_failed" "Health check failed after app start. App may have runtime errors." 1

        # Dump logs if available
        if [ -f "npm-debug.log" ]; then
            echo "=== npm-debug.log ==="
            cat npm-debug.log
        fi

        # Keep container running for debugging if VNC enabled
        if [ "$ENABLE_VNC" = "true" ]; then
            echo "VNC enabled - keeping container running for debugging"
            tail -f /dev/null
        fi
        exit 1
    fi
}

# Run main or custom command
if [ "$1" = "test" ] || [ -z "$1" ]; then
    main
else
    exec "$@"
fi

#!/bin/bash
# ==============================================================================
# FULL AUTONOMOUS RUN - Standard Configuration
# ==============================================================================
# Aktiviert alle Features:
# - --autonomous: 100% Tests, 0 Fehler, 1 Stunde Timeout
# - --continuous-sandbox --enable-vnc: 30-Sekunden Docker Test-Zyklen mit VNC
# - --enable-validation: Test-Generierung + Debug Engine
# - --dashboard: Real-time Agent Monitoring
# ==============================================================================

# Default Werte
REQUIREMENTS="${1:-Data/todo_app_requirements.json}"
TECH_STACK="${2:-Data/todo_app_tech_stack.json}"
OUTPUT_DIR="${3:-./output_todo_app_$(date +%Y%m%d_%H%M%S)}"

# Prüfe ob Requirements existieren
if [ ! -f "$REQUIREMENTS" ]; then
    echo "ERROR: Requirements file not found: $REQUIREMENTS"
    exit 1
fi

# Prüfe ob Tech Stack existieren
if [ ! -f "$TECH_STACK" ]; then
    echo "WARNING: Tech stack file not found: $TECH_STACK"
    echo "Running without tech stack configuration..."
    TECH_STACK=""
fi

echo "============================================================"
echo "  FULL AUTONOMOUS CODE GENERATION"
echo "============================================================"
echo "  Requirements:    $REQUIREMENTS"
echo "  Tech Stack:      $TECH_STACK"
echo "  Output Dir:      $OUTPUT_DIR"
echo "============================================================"
echo ""
echo "  Features Enabled:"
echo "  ✓ Autonomous Mode (100% tests, 0 errors, 1h timeout)"
echo "  ✓ Continuous Sandbox Testing (30s cycles)"
echo "  ✓ VNC Streaming (http://localhost:6080/vnc.html)"
echo "  ✓ Validation Team (Test Generation + Debug Engine)"
echo "  ✓ Dashboard (http://localhost:8080)"
echo "  ✓ Live Preview (http://localhost:5173)"
echo "============================================================"
echo ""

# Build command
CMD="python run_society_hybrid.py \"$REQUIREMENTS\" \
    --output-dir \"$OUTPUT_DIR\" \
    --autonomous \
    --continuous-sandbox \
    --enable-vnc \
    --vnc-port 6080 \
    --enable-validation \
    --validation-team \
    --test-framework vitest \
    --validation-docker \
    --dashboard \
    --dashboard-port 8080 \
    --shell-stream \
    --max-iterations 200 \
    --max-time 3600"

# Add tech stack if provided
if [ -n "$TECH_STACK" ]; then
    CMD="$CMD --tech-stack \"$TECH_STACK\""
fi

# Execute
echo "Running: $CMD"
echo ""
eval $CMD

# Capture exit code
EXIT_CODE=$?

echo ""
echo "============================================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ✓ GENERATION COMPLETE"
    echo "  Output: $OUTPUT_DIR"
else
    echo "  ✗ GENERATION FAILED (Exit Code: $EXIT_CODE)"
fi
echo "============================================================"

exit $EXIT_CODE

#!/bin/bash
# Setup script for ATM-R virtual environment (Linux/Mac)

echo "========================================"
echo "ATM-R Virtual Environment Setup"
echo "========================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv is not installed!"
    echo "Install it with: pip install uv"
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment with uv..."
    uv venv .venv
fi

# Activate and install dependencies
echo ""
echo "Activating virtual environment..."
source .venv/bin/activate

echo ""
echo "Installing base dependencies..."
uv pip install -r requirements.txt

echo ""
echo "Installing ML frameworks and real-time deps..."
uv pip install torch torchvision opencv-python sounddevice pybind11 numba

echo ""
echo "========================================"
echo "Setup complete!"
echo "========================================"
echo ""
echo "To activate the environment, run:"
echo "  source .venv/bin/activate"
echo ""
echo "To run tests:"
echo "  pytest tests/test_core.py -v"
echo ""
echo "To run demo:"
echo "  python scripts/run_demo.py --adaptive --plot"

"""
MoireTracker_v2 gRPC HTTP Bridge - Main Entry Point

Usage:
    python -m worker_bridge       # Starts HTTP Bridge on :8766
    python -m worker_bridge.http_bridge  # Alternative
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker_bridge.http_bridge import main

if __name__ == "__main__":
    print("=" * 50)
    print("  MoireTracker_v2 - gRPC HTTP Bridge")
    print("=" * 50)
    print()
    asyncio.run(main())
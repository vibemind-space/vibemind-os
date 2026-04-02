"""Simple HTTP server to serve Vapi web interface and voice API.

Start with: python serve_vapi.py
Then open: http://localhost:8765
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Load .env from project root BEFORE any other imports
_project_root = Path(__file__).parent.parent.parent.parent  # Automation_ui/
_env_file = _project_root / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
        print(f"[ENV] Loaded .env from {_env_file}")
    except ImportError:
        # Manual .env parsing if dotenv not available
        with open(_env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        print(f"[ENV] Manually loaded .env from {_env_file}")

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import voice API router
from api_router import router as voice_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Moire Voice Control", version="1.0.0")

# CORS for Vapi web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include voice API router
app.include_router(voice_router)

# Serve static files
static_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """Serve Vapi web interface (no-cache for dev)."""
    return FileResponse(
        static_dir / "vapi_web.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    )


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "moire-voice-control"}


if __name__ == "__main__":
    print("\n" + "="*60)
    print("   Moire Voice Control - Vapi Interface")
    print("="*60)
    print("\n   Open in browser: http://localhost:8765")
    print("   API docs: http://localhost:8765/docs")
    print("\n   Press Ctrl+C to stop\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8765,
        log_level="info"
    )

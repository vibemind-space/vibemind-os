"""Run the engine with clean output (no httpx debug spam)."""
import logging
import sys
import os

# Suppress noisy loggers BEFORE any imports
for name in ['httpx', 'httpcore', 'src.engine.minibook_client', 'src.engine.minibook_agent', 'src.engine.ollama_client']:
    logging.getLogger(name).setLevel(logging.WARNING)

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

# Force UTF-8 output on Windows + unbuffered
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ["PYTHONUNBUFFERED"] = "1"

from src.engine.master_orchestrator import MasterOrchestrator

project = sys.argv[1] if len(sys.argv) > 1 else "Data/all_services/whatsapp"
output = sys.argv[2] if len(sys.argv) > 2 else f"output/{os.path.basename(project)}"

orch = MasterOrchestrator(project, output_dir=output)
success = orch.run()
sys.exit(0 if success else 1)

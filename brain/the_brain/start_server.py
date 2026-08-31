"""Quick start script for the Brain Nervous System server."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Phase 11.I — load .env so all LLM-using tools (idea_expand, classify, etc)
# inherit OPENROUTER_API_KEY / OPENAI_API_KEY / GROQ_API_KEY from the repo
# .env when brain is spawned without env inheritance (debug.ps1, electron).
try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    _candidates = [
        os.path.join(_here, ".env"),
        os.path.normpath(os.path.join(_here, "..", "..", "..", ".env")),
        os.path.normpath(os.path.join(_here, "..", "..", ".env")),
    ]
    for _envp in _candidates:
        if os.path.isfile(_envp):
            load_dotenv(_envp)
            print(f"[brain-start] loaded env from {_envp}")
            break
except Exception as _e:
    print(f"[brain-start] dotenv unavailable: {_e}")

import uvicorn
from web.brain_server import create_app

# Modul-Level-App nur fuer den Single-Process-Pfad (direktes App-Objekt) +
# fuer `python -m web.brain_server`-Importe. Bei BRAIN_HTTP_WORKERS>1 baut JEDER
# uvicorn-Worker die App selbst via Factory-Import-String — der Master-Prozess
# braucht sie dann NICHT (spart ~1.5GB + einen Embedder-Load im Master).
if int(os.environ.get("BRAIN_HTTP_WORKERS", "1")) > 1:
    app = None
else:
    app = create_app(testing=False)

if __name__ == "__main__":
    # Port is overridable via argv[1] or BRAIN_PORT so the debug launcher can
    # pass CONFIG.ports.brain_dashboard. Default 5000 keeps the documented
    # `python -m web.brain_server` / `python start_server.py` behaviour.
    # NOTE: the app object is passed to uvicorn.run() directly (not an import
    # string) on purpose — an import string makes uvicorn fork a worker that
    # re-resolves `python` via PATH (pyenv-3.11 instead of the active venv),
    # producing two competing processes that never bind the port cleanly.
    _port = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        _port = int(sys.argv[1])
    elif os.environ.get("BRAIN_PORT", "").isdigit():
        _port = int(os.environ["BRAIN_PORT"])

    # Multi-Worker (2026-06-09, struktureller Contention-Fix): der Single-Process-
    # async-Server staut bei JEDER synchronen schweren Handler-Op (Qwen-embed,
    # torch-route, serielle Qdrant-Sweeps) alle Requests. Mehrere uvicorn-Worker
    # halten dann nur EINEN Worker pro blockierendem Request, die anderen bedienen
    # weiter. Single-Writer bleibt erfuellt: brain-core laeuft BRAIN_BACKGROUND_LOOPS=0
    # + inference (NULL State-schreibende Loops im HTTP-Prozess; der brain-loops-
    # Worker ist der einzige Writer), also kollidieren N HTTP-Worker NICHT.
    #
    # workers>1 ERFORDERT einen Import-String (uvicorn forkt Worker-Prozesse, die
    # die App neu importieren) — NICHT das App-Objekt. Der frueher dokumentierte
    # venv-PATH-Konflikt galt nur fuer den lokalen debug.ps1-Start; IM CONTAINER
    # gibt es nur einen Python (kein pyenv), daher ist der Import-String hier sicher.
    # Default 1 (=lokales Verhalten unveraendert, direktes App-Objekt).
    _workers = int(os.environ.get("BRAIN_HTTP_WORKERS", "1"))
    if _workers > 1:
        print(f"[brain-start] starting uvicorn on 0.0.0.0:{_port} ({_workers} workers, factory)")
        uvicorn.run("web.brain_server:create_app", factory=True,
                    host="0.0.0.0", port=_port, workers=_workers)
    else:
        print(f"[brain-start] starting uvicorn on 0.0.0.0:{_port} (single process)")
        uvicorn.run(app, host="0.0.0.0", port=_port)

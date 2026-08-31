"""
Setup the persistent Brain-Self-Discourse Mirofish simulation — Phase R.2.

Walkthrough of the Mirofish setup flow with the 26 OpenFang agent
manifests as seed documents:

    1. POST /api/graph/ontology/generate  — uploads agent manifests +
       generates entity/edge ontology via Ollama
    2. POST /api/graph/build               — builds the Neo4j KG
    3. POST /api/simulation/create         — registers a simulation
    4. POST /api/simulation/prepare        — generates agent profiles
    5. POST /api/simulation/start          — starts the round-loop

Once started, Mirofish-Sim is "alive" and Brain can:
  - POST /api/simulation/{id}/interview   — query any agent
  - read posts via SQLite or /api/simulation/{id}/posts
  - rounds run continuously with our discourse-prompts

This script writes the simulation_id to
``vibemind-os/brain/the_brain/data/discourse_sim.json`` so the
DiscourseEngine (R.3) can pick it up without re-running setup.

Run::

    python setup_mirofish_brain_sim.py            # full setup (~30-45min on Ollama)
    python setup_mirofish_brain_sim.py --status   # show stored sim_id + state

Env::

    MIROFISH_URL                 default http://127.0.0.1:5101
    OPENFANG_AGENTS_DIR          default <repo>/vibemind-os/openfang/agents
    BRAIN_DATA_DIR               default <repo>/vibemind-os/brain/the_brain/data
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

MIROFISH_URL = os.environ.get("MIROFISH_URL", "http://127.0.0.1:5101").rstrip("/")
_REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
OPENFANG_AGENTS_DIR = Path(os.environ.get(
    "OPENFANG_AGENTS_DIR", _REPO / "vibemind-os" / "openfang" / "agents",
))
BRAIN_DATA_DIR = Path(os.environ.get(
    "BRAIN_DATA_DIR", _REPO / "vibemind-os" / "brain" / "the_brain" / "data",
))
SIM_STATE_FILE = BRAIN_DATA_DIR / "discourse_sim.json"


SIMULATION_REQUIREMENT = """\
VibeMind Self-Discourse Simulation.

This simulation models the inner discourse of the VibeMind cognitive
system. The 26 'agents' are real autonomous components (brain-coder,
rowboat-knowledge, vibemind-ideas, etc.) that exist in OpenFang. In
this simulation they reflect aloud about:

  - the contents of their respective knowledge graphs
  - what is fresh / what is stale
  - what other agents might have said yesterday
  - what they would do if asked
  - cross-cutting patterns they notice

Output is a continuous stream of short reflections (1-2 sentence
'tweets'), with occasional replies between agents that share a domain.

Goal: surface 'aha' moments and consolidation opportunities that the
system would otherwise miss. The Brain (Tahlamus) listens, aggregates
the discourse every 3 hours, and persists structured findings.
"""


def _save_state(d: Dict[str, Any]) -> None:
    BRAIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SIM_STATE_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print(f"[setup] state saved -> {SIM_STATE_FILE}")


def _load_state() -> Dict[str, Any]:
    if not SIM_STATE_FILE.exists():
        return {}
    try:
        return json.loads(SIM_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


DISCOURSE_AGENT_PREFIXES = ("brain-",)
DISCOURSE_AGENT_MAX_BYTES = int(os.environ.get("DISCOURSE_AGENT_MAX_BYTES", "1400"))


def collect_agent_manifests() -> List[Path]:
    """Discourse-relevant agent.toml files only.

    The full openfang/agents folder has ~48 manifests including many
    poc-* / coding-engine clones that don't make for interesting
    discourse personas. Big manifests (e.g. ``assistant`` at 6KB) also
    blow Groq Free Tier's 12K TPM limit when combined.

    Default: only ``brain-*`` agents, each manifest below 2.5KB. That
    yields ~12-18 personas at ~1KB each, comfortably under 10K tokens
    for the ontology prompt.

    Overrides:
      DISCOURSE_AGENT_PREFIXES  csv prefix list, default "brain-"
      DISCOURSE_AGENT_MAX_BYTES default 2500
    """
    prefixes = os.environ.get("DISCOURSE_AGENT_PREFIXES")
    if prefixes:
        wanted = tuple(p.strip() for p in prefixes.split(",") if p.strip())
    else:
        wanted = DISCOURSE_AGENT_PREFIXES
    out: List[Path] = []
    for m in sorted(OPENFANG_AGENTS_DIR.glob("*/agent.toml")):
        if not any(m.parent.name.startswith(p) for p in wanted):
            continue
        try:
            if m.stat().st_size > DISCOURSE_AGENT_MAX_BYTES:
                continue
        except Exception:
            continue
        out.append(m)
    return out


def project_alive(project_id: str) -> bool:
    """Check if Mirofish still has the project_id from a prior setup."""
    if not project_id:
        return False
    try:
        r = requests.get(f"{MIROFISH_URL}/api/graph/project/{project_id}", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def simulation_alive(simulation_id: str) -> bool:
    """Check if a simulation_id is still known to Mirofish."""
    if not simulation_id:
        return False
    try:
        r = requests.get(f"{MIROFISH_URL}/api/simulation/{simulation_id}", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def simulation_running(simulation_id: str) -> bool:
    """Check if the simulation is in running state."""
    if not simulation_id:
        return False
    try:
        r = requests.get(
            f"{MIROFISH_URL}/api/simulation/{simulation_id}/run-status",
            timeout=10,
        )
        if r.status_code != 200:
            return False
        d = (r.json() or {}).get("data") or {}
        return (d.get("status") or "").lower() in (
            "running", "started", "active", "in_progress",
        )
    except Exception:
        return False


def step1_ontology(manifests: List[Path]) -> Dict[str, Any]:
    """Upload all manifests (re-cast as .md) and have Mirofish derive
    an ontology. Mirofish only accepts pdf/md/txt — we wrap each TOML's
    content into a markdown agent-card."""
    print(f"[1/5] ontology — {len(manifests)} manifests -> Ollama LLM")
    files = []
    for m in manifests:
        agent_dirname = m.parent.name
        toml_text = m.read_text(encoding="utf-8")
        md = (
            f"# Agent: {agent_dirname}\n\n"
            f"This is an OpenFang/VibeMind agent. Below is its full "
            f"manifest (TOML format) describing its persona, "
            f"capabilities, and system prompt.\n\n"
            f"```toml\n{toml_text}\n```\n"
        )
        files.append((
            "files",
            (f"{agent_dirname}.md", md.encode("utf-8"), "text/markdown"),
        ))
    data = {
        "simulation_requirement": SIMULATION_REQUIREMENT,
        "project_name": "VibeMind-Self-Discourse",
        "additional_context": (
            "Each uploaded TOML file describes one VibeMind/OpenFang agent: "
            "name, persona, capabilities, system_prompt. Derive entity types "
            "for Agent, Capability, Domain (e.g., coding/security/knowledge), "
            "and edge types for cooperates_with, reflects_on, depends_on."
        ),
    }
    t0 = time.time()
    r = requests.post(
        f"{MIROFISH_URL}/api/graph/ontology/generate",
        files=files, data=data, timeout=600,
    )
    print(f"      done in {time.time()-t0:.1f}s, status={r.status_code}")
    if r.status_code >= 400:
        raise RuntimeError(f"ontology HTTP {r.status_code}: {r.text[:500]}")
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"ontology failed: {body}")
    out = body["data"]
    print(f"      project_id={out.get('project_id')} "
          f"entity_types={len(out.get('ontology',{}).get('entity_types',[]))} "
          f"edge_types={len(out.get('ontology',{}).get('edge_types',[]))}")
    return out


def step2_graph(project_id: str) -> Dict[str, Any]:
    """Build the Neo4j KG from the ontology."""
    print(f"[2/5] graph build — project={project_id}")
    t0 = time.time()
    r = requests.post(
        f"{MIROFISH_URL}/api/graph/build",
        json={"project_id": project_id, "force_rebuild": True},
        timeout=60,
    )
    print(f"      kicked off in {time.time()-t0:.1f}s, status={r.status_code}")
    if r.status_code >= 400:
        raise RuntimeError(f"build HTTP {r.status_code}: {r.text[:500]}")
    body = r.json()
    task_id = (body.get("data") or {}).get("task_id") or body.get("task_id")
    if not task_id:
        # synchronous response — body might already contain graph_id
        return body.get("data") or body
    # Poll until completed
    print(f"      polling task {task_id} ...")
    # Generous timeout: NER over 26 manifests on llama3.1 takes 60-90min
    deadline = time.time() + 7200
    while time.time() < deadline:
        time.sleep(10)
        s = requests.get(
            f"{MIROFISH_URL}/api/graph/task/{task_id}", timeout=10,
        ).json()
        st = (s.get("data") or s).get("status")
        prog = (s.get("data") or s).get("progress", "?")
        print(f"      [{int(time.time()-t0):4d}s] status={st} progress={prog}")
        if st in ("completed", "success", "done"):
            return s.get("data") or s
        if st in ("failed", "error"):
            raise RuntimeError(f"build failed: {s}")
    raise RuntimeError("build timed out after 30 min")


def step3_simulation_create(project_id: str, graph_id: Optional[str] = None) -> str:
    """Register a simulation."""
    print(f"[3/5] simulation create — project={project_id} graph={graph_id}")
    payload: Dict[str, Any] = {
        "project_id": project_id,
        "name": "VibeMind-Self-Discourse",
        "enable_twitter": True,
        "enable_reddit": False,
    }
    if graph_id:
        payload["graph_id"] = graph_id
    r = requests.post(
        f"{MIROFISH_URL}/api/simulation/create", json=payload, timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"create HTTP {r.status_code}: {r.text[:500]}")
    body = r.json()
    sid = (body.get("data") or {}).get("simulation_id") or body.get("simulation_id")
    if not sid:
        raise RuntimeError(f"no simulation_id: {body}")
    print(f"      simulation_id={sid}")
    return sid


def step4_prepare(simulation_id: str) -> Dict[str, Any]:
    """Have Mirofish auto-generate agent profiles for the sim."""
    print(f"[4/5] prepare — sim={simulation_id}")
    t0 = time.time()
    r = requests.post(
        f"{MIROFISH_URL}/api/simulation/prepare",
        json={
            "simulation_id": simulation_id,
            "agent_count": 26,
            "force_regenerate": False,
        },
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"prepare HTTP {r.status_code}: {r.text[:500]}")
    body = r.json()
    task_id = (body.get("data") or {}).get("task_id")
    if task_id:
        # poll status
        # 30min is plenty for prepare on Ollama
        deadline = time.time() + 1800
        while time.time() < deadline:
            time.sleep(10)
            s = requests.post(
                f"{MIROFISH_URL}/api/simulation/prepare/status",
                json={"task_id": task_id}, timeout=10,
            ).json()
            st = (s.get("data") or s).get("status")
            prog = (s.get("data") or s).get("progress", "?")
            print(f"      [{int(time.time()-t0):4d}s] prepare status={st} progress={prog}")
            if st in ("completed", "success", "done"):
                return s.get("data") or s
            if st in ("failed", "error"):
                raise RuntimeError(f"prepare failed: {s}")
        raise RuntimeError("prepare timed out")
    return body.get("data") or body


def step5_start(simulation_id: str) -> Dict[str, Any]:
    """Start the round-loop."""
    print(f"[5/5] start — sim={simulation_id}")
    r = requests.post(
        f"{MIROFISH_URL}/api/simulation/start",
        json={
            "simulation_id": simulation_id,
            "rounds": 0,    # 0 = unbounded / runs until stopped
            "enable_twitter": True,
            "enable_reddit": False,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"start HTTP {r.status_code}: {r.text[:500]}")
    body = r.json()
    print(f"      started: {body.get('data') or body}")
    return body.get("data") or body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true",
                    help="Show stored simulation state")
    ap.add_argument("--skip-build", action="store_true",
                    help="Reuse existing project + skip ontology+build")
    args = ap.parse_args()

    if args.status:
        state = _load_state()
        print(json.dumps(state, indent=2))
        return 0

    # Sanity: Mirofish reachable? Wait up to 60s (called from launcher
    # right after `docker compose up -d`, container needs to boot).
    deadline = time.time() + 60
    while True:
        try:
            r = requests.get(f"{MIROFISH_URL}/api/simulation/list", timeout=3)
            if r.status_code == 200:
                break
        except Exception:
            pass
        if time.time() > deadline:
            print(f"FAIL: mirofish not reachable at {MIROFISH_URL}", file=sys.stderr)
            return 1
        time.sleep(3)

    state = _load_state()
    project_id = state.get("project_id")
    graph_id = state.get("graph_id")
    sid = state.get("simulation_id")

    # ── Fast-path: prior state is still alive on Mirofish side ──
    if simulation_running(sid):
        print(f"[setup] simulation already running: {sid} — nothing to do")
        return 0

    if simulation_alive(sid):
        print(f"[setup] simulation exists but not running: {sid} — starting")
        try:
            step5_start(sid)
            _save_state({**state, "step": "running", "started_at": time.time()})
            print(f"[setup] resumed. simulation_id={sid}")
            return 0
        except Exception as e:
            print(f"[setup] resume failed ({e}); rebuilding from scratch")
            sid = None

    # If project no longer exists in Mirofish, drop stale ids
    if not project_alive(project_id):
        if project_id:
            print(f"[setup] project '{project_id}' no longer in Mirofish — wiping state")
        project_id = None
        graph_id = None
        sid = None
        _save_state({})

    if not args.skip_build and not project_id:
        manifests = collect_agent_manifests()
        if not manifests:
            print(f"FAIL: no agent manifests under {OPENFANG_AGENTS_DIR}", file=sys.stderr)
            return 1
        out1 = step1_ontology(manifests)
        project_id = out1["project_id"]
        _save_state({"project_id": project_id, "step": "ontology"})
        out2 = step2_graph(project_id)
        graph_id = out2.get("graph_id") or out2.get("id")
        _save_state({"project_id": project_id, "graph_id": graph_id, "step": "graph"})

    if not project_id:
        print("FAIL: no project_id (run without --skip-build first)", file=sys.stderr)
        return 1

    if not sid:
        sid = step3_simulation_create(project_id, graph_id)
        _save_state({"project_id": project_id, "graph_id": graph_id,
                     "simulation_id": sid, "step": "created"})

    step4_prepare(sid)
    _save_state({"project_id": project_id, "graph_id": graph_id,
                 "simulation_id": sid, "step": "prepared"})

    step5_start(sid)
    _save_state({"project_id": project_id, "graph_id": graph_id,
                 "simulation_id": sid, "step": "running",
                 "started_at": time.time()})

    print(f"\n[setup] DONE. simulation_id={sid}")
    print("        Brain DiscourseEngine can now post via /api/simulation/{id}/interview")
    return 0


if __name__ == "__main__":
    sys.exit(main())

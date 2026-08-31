"""
Clone OpenFang agents to phi3-Ollama variants — Phase R.1.

For every currently-registered OpenFang agent (via /api/agents), creates
a sibling agent with:
  - name              = "{original-name}-phi3"
  - model.provider    = "ollama"
  - model.model       = "ollama/phi3:mini"
  - same persona, system_prompt, tags, capabilities (so Zuständigkeit
    bleibt erhalten)

Output goes to a NEW directory ``vibemind-os/openfang/agents-phi3/`` so
the originals stay untouched and we can regenerate idempotently.

After file generation, optionally POST each clone-manifest to
/api/agents to spawn it in the running OpenFang daemon. If the daemon
auto-discovers from the agents directory, restart it.

Run::

    python clone_openfang_agents_phi3.py                # generate files
    python clone_openfang_agents_phi3.py --register     # generate + register

Env::

    OPENFANG_URL                 default http://127.0.0.1:4200
    OLLAMA_MODEL                 default phi3:mini
    OPENFANG_AGENTS_DIR          default <repo>/vibemind-os/openfang/agents
    OPENFANG_PHI3_DIR            default <repo>/vibemind-os/openfang/agents-phi3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

OPENFANG_URL = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")
# scripts/ → the_brain/ → brain/ → vibemind-os/  (4 levels up from this file)
_VIBEMIND_OS = Path(__file__).resolve().parent.parent.parent.parent
OPENFANG_AGENTS_DIR = Path(os.environ.get(
    "OPENFANG_AGENTS_DIR", _VIBEMIND_OS / "openfang" / "agents",
))
OPENFANG_PHI3_DIR = Path(os.environ.get(
    "OPENFANG_PHI3_DIR", _VIBEMIND_OS / "openfang" / "agents-phi3",
))


def fetch_agents() -> List[Dict[str, Any]]:
    r = requests.get(f"{OPENFANG_URL}/api/agents", timeout=10)
    r.raise_for_status()
    return r.json()


def read_existing_manifest(name: str) -> Optional[str]:
    """Try to read original TOML manifest. Returns text or None."""
    p = OPENFANG_AGENTS_DIR / name / "agent.toml"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _toml_str(v: str) -> str:
    """Escape a string for inline TOML (single-line)."""
    return v.replace("\\", "\\\\").replace('"', '\\"')


def build_clone_toml(agent: Dict[str, Any]) -> str:
    """Build a phi3 clone manifest. Prefer original-on-disk as base; fall
    back to a minimal manifest derived from the live agent profile."""
    original_name = agent.get("name") or "unnamed"
    if not original_name or original_name == "unnamed":
        return ""  # skip nameless

    clone_name = f"{original_name}-phi3"
    base = read_existing_manifest(original_name)

    if base:
        # Replace name + model section. Keep persona / capabilities / tags.
        text = re.sub(
            r'^name\s*=\s*"[^"]*"',
            f'name = "{_toml_str(clone_name)}"',
            base, count=1, flags=re.MULTILINE,
        )
        # Replace [model] section block: provider + model + (keep
        # max_tokens, temperature, system_prompt as they were)
        def repl_model_block(m: re.Match) -> str:
            block = m.group(0)
            block = re.sub(
                r'^provider\s*=\s*"[^"]*"',
                'provider = "ollama"',
                block, count=1, flags=re.MULTILINE,
            )
            # try existing model line first
            if re.search(r'^model\s*=', block, flags=re.MULTILINE):
                block = re.sub(
                    r'^model\s*=\s*"[^"]*"',
                    f'model = "ollama/{_toml_str(OLLAMA_MODEL)}"',
                    block, count=1, flags=re.MULTILINE,
                )
            else:
                # insert under [model]
                block = block.replace(
                    "[model]",
                    f'[model]\nmodel = "ollama/{_toml_str(OLLAMA_MODEL)}"',
                    1,
                )
            return block

        text = re.sub(
            r'\[model\][\s\S]*?(?=\n\[|\Z)',
            repl_model_block, text, count=1,
        )
        return text

    # Fall back: minimal manifest from live profile
    persona = (agent.get("profile") or {}).get("description") or agent.get("description") or ""
    system_prompt = (agent.get("profile") or {}).get("system_prompt") or persona
    tags = (agent.get("tags") or []) + ["phi3-clone"]
    return (
        f'name = "{_toml_str(clone_name)}"\n'
        f'version = "0.1.0"\n'
        f'description = "Phi3 ollama clone of {_toml_str(original_name)} for discourse simulation"\n'
        f'author = "vibemind"\n'
        f'module = "builtin:chat"\n'
        f'tags = {json.dumps(tags)}\n'
        f'\n'
        f'[model]\n'
        f'provider = "ollama"\n'
        f'model = "ollama/{_toml_str(OLLAMA_MODEL)}"\n'
        f'max_tokens = 1024\n'
        f'temperature = 0.7\n'
        f'system_prompt = """\n'
        f'You are {_toml_str(clone_name)}, a phi3 ollama clone of {_toml_str(original_name)} '
        f'inside the VibeMind discourse simulation. Stay in character.\n\n'
        f'{_toml_str(system_prompt)[:2000]}\n'
        f'"""\n'
        f'\n'
        f'[resources]\n'
        f'max_llm_tokens_per_hour = 50000\n'
        f'max_concurrent_tools = 3\n'
        f'\n'
        f'[capabilities]\n'
        f'tools = []\n'
        f'memory_read = ["self.*"]\n'
        f'memory_write = ["self.*"]\n'
    )


def write_clones() -> List[Path]:
    OPENFANG_PHI3_DIR.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    agents = fetch_agents()
    print(f"[clone] {len(agents)} registered agents")
    for a in agents:
        name = a.get("name") or ""
        if not name or name == "unnamed":
            print(f"[clone] skip nameless agent id={a.get('id')}")
            continue
        if name.endswith("-phi3"):
            print(f"[clone] skip already-clone {name}")
            continue
        toml = build_clone_toml(a)
        if not toml:
            continue
        out_dir = OPENFANG_PHI3_DIR / f"{name}-phi3"
        out_dir.mkdir(parents=True, exist_ok=True)
        f = out_dir / "agent.toml"
        f.write_text(toml, encoding="utf-8")
        written.append(f)
        print(f"[clone] wrote {f.relative_to(OPENFANG_PHI3_DIR.parent)}")
    return written


def register_clone(toml_path: Path) -> Optional[str]:
    """POST a manifest to OpenFang to spawn it. Returns new agent id or None."""
    try:
        r = requests.post(
            f"{OPENFANG_URL}/api/agents",
            json={"manifest_path": str(toml_path)},
            timeout=30,
        )
        if r.status_code >= 400:
            print(f"[register] {toml_path.name} failed: HTTP {r.status_code} {r.text[:200]}")
            return None
        d = r.json()
        return d.get("id")
    except Exception as e:
        print(f"[register] {toml_path.name} error: {e}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true",
                    help="POST each clone-manifest to OpenFang after writing")
    args = ap.parse_args()

    print(f"[clone] OpenFang URL: {OPENFANG_URL}")
    print(f"[clone] Output dir:   {OPENFANG_PHI3_DIR}")
    print(f"[clone] Ollama model: {OLLAMA_MODEL}")

    files = write_clones()
    print(f"\n[clone] wrote {len(files)} manifests")

    if args.register and files:
        print("\n[register] posting to OpenFang...")
        ok = 0
        for f in files:
            new_id = register_clone(f)
            if new_id:
                ok += 1
                print(f"[register] {f.parent.name} -> {new_id}")
            time.sleep(0.2)
        print(f"\n[register] {ok}/{len(files)} clones registered")

    return 0


if __name__ == "__main__":
    sys.exit(main())

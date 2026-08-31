"""Sync the skill library to a Qdrant collection.

Reads every SKILL.md via :mod:`_loader`, computes an OpenAI embedding for the
``embedding_text()``, and upserts a point into the ``vibemind_skills``
collection.

Usage::

    python vibemind-os/skills/_indexer.py --rebuild
    python vibemind-os/skills/_indexer.py --skill excel/fill-cell

The indexer is invoked manually after editing skills, and by the skill
coordinator agent after it persists a freshly-learned skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Allow running both as a script (``python _indexer.py``) and as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import Skill, discover_skills, parse_skill_file  # noqa: E402

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6340")
COLLECTION = os.environ.get("VIBEMIND_SKILLS_COLLECTION", "vibemind_skills")
EMBED_MODEL = os.environ.get("VIBEMIND_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = 1536  # text-embedding-3-small
OPENAI_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")


def _load_dotenv_into_env() -> None:
    """Best-effort load of repo-root .env so OPENAI_API_KEY is present."""
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv_into_env()


def _http_json(method: str, url: str, body: dict[str, Any] | None = None,
               headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url}: {e.read().decode('utf-8', 'ignore')[:300]}") from e


def ensure_collection() -> None:
    info_url = f"{QDRANT_URL}/collections/{COLLECTION}"
    try:
        _http_json("GET", info_url)
        return
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
    _http_json("PUT", info_url, {
        "vectors": {"size": EMBED_DIM, "distance": "Cosine"},
    })
    print(f"[indexer] created Qdrant collection {COLLECTION}")


def embed(text: str) -> list[float]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set; cannot compute embeddings")
    resp = _http_json(
        "POST",
        f"{OPENAI_BASE}/embeddings",
        {"model": EMBED_MODEL, "input": text},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return resp["data"][0]["embedding"]


def point_id_for(skill: Skill) -> int:
    """Stable numeric ID derived from skill path so re-indexing replaces in place."""
    digest = hashlib.sha1(str(skill.path.relative_to(skill.path.parents[2])).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False) >> 1  # 63-bit unsigned


def upsert_skill(skill: Skill) -> None:
    vector = embed(skill.embedding_text())
    payload = {
        "name": skill.name,
        "description": skill.description,
        "app": skill.app,
        "agents": skill.agents,
        "trigger": skill.trigger,
        "confidence": skill.confidence,
        "attempts": skill.attempts,
        "successes": skill.successes,
        "last_adjusted": skill.last_adjusted,
        "file_path": str(skill.path),
    }
    body = {
        "points": [
            {"id": point_id_for(skill), "vector": vector, "payload": payload}
        ]
    }
    _http_json("PUT", f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true", body)
    print(f"[indexer] upserted {skill.app}/{skill.name} (conf={skill.confidence:.2f})")


def search(query: str, agent: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    vector = embed(query)
    body: dict[str, Any] = {"vector": vector, "limit": limit, "with_payload": True}
    if agent:
        body["filter"] = {
            "should": [
                {"key": "agents", "match": {"value": agent}},
                {"key": "agents", "match": {"value": "*"}},
            ]
        }
    resp = _http_json("POST", f"{QDRANT_URL}/collections/{COLLECTION}/points/search", body)
    return resp.get("result", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="re-embed and upsert every skill")
    parser.add_argument("--skill", help="upsert just one skill (relative path under skills/)")
    parser.add_argument("--search", help="run a semantic search instead of indexing")
    parser.add_argument("--agent", help="restrict search to skills visible to this agent")
    args = parser.parse_args()

    ensure_collection()

    if args.search:
        results = search(args.search, agent=args.agent)
        print(f"top {len(results)} for: {args.search!r}")
        for r in results:
            p = r.get("payload", {})
            print(f"  [{p.get('app')}/{p.get('name')}] score={r.get('score'):.3f} conf={p.get('confidence',0):.2f}")
            print(f"    {p.get('description')}")
        return 0

    if args.skill:
        skill_path = Path(__file__).resolve().parent / args.skill
        if skill_path.is_dir():
            skill_path = skill_path / "SKILL.md"
        upsert_skill(parse_skill_file(skill_path))
        return 0

    if args.rebuild:
        skills = discover_skills()
        if not skills:
            print("[indexer] no skills found; nothing to do")
            return 0
        for s in skills:
            upsert_skill(s)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

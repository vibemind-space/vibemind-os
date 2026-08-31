"""Phase 11.U.C.9 — Async operations for the supabase: capability target.

Each operation:
  1. Resolves titles / IDs against canvas_nodes
  2. Mutates canvas_edges
  3. Publishes a brain space-event so the bridge -> Electron renderer
     sees the change live
  4. Returns a human-readable string (validator: rule:string_nonempty)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .supabase_ideas_client import SupabaseIdeasClient

logger = logging.getLogger(__name__)


# ─── intent re-extraction (Phase 11.P pattern) ────────────────────────


_CONNECT_INTENT_RE = re.compile(
    r"(?:connect|link|verbinde|verkn[uü]pfe|linke)\s+"
    r"(?:idea(?:s)?|idee(?:n)?\s+)?([\w\d_-]+)"
    r".+?(?:with|to|and|mit|und|zu)\s+"
    r"(?:idea\s+|idee\s+)?([\w\d_-]+)",
    re.IGNORECASE,
)
_DISCONNECT_INTENT_RE = re.compile(
    r"(?:disconnect|unlink|trenne|entferne)\s+"
    r"(?:the\s+|die\s+)?"
    r"(?:idea(?:s)?\s+|ideen\s+)?"
    r"([\w\d_-]+)"
    r"\s+(?:from|with|and|von|und|zu|mit)\s+"
    r"(?:idea\s+|the\s+)?([\w\d_-]+)",
    re.IGNORECASE,
)


def _extract_pair_from_params(
    params: Dict[str, Any], regex: re.Pattern,
) -> Tuple[str, str]:
    """Pull two idea titles out of the param-bag, falling back to _intent
    parsing if not enough explicit names are present. Tolerates the LLM
    planner using random key names like `idea1_name` / `source_node` /
    etc. — anything non-underscore key with a string value is a candidate.

    Phase 11.U.E — if `value` looks like a JSON dict (multi-arg arg_template
    that we JSON-encoded in plan_schema.from_dict), parse it and merge.
    """
    # Phase 0: JSON-encoded multi-arg payload
    if isinstance(params, dict):
        raw_value = params.get("value")
        if isinstance(raw_value, str) and raw_value.strip().startswith("{"):
            try:
                import json as _json
                decoded = _json.loads(raw_value)
                if isinstance(decoded, dict):
                    # Promote decoded keys to top-level params (so the rest
                    # of this function can pick them up)
                    for k, v in decoded.items():
                        params.setdefault(k, v)
            except Exception:
                pass

    # Phase 1: well-known keys (in priority order)
    known1 = (
        params.get("idea1") or params.get("source") or
        params.get("source_id") or params.get("from_idea") or
        params.get("von") or ""
    ).strip() if isinstance(params, dict) else ""
    known2 = (
        params.get("idea2") or params.get("target") or
        params.get("target_id") or params.get("to_idea") or
        params.get("zu") or ""
    ).strip() if isinstance(params, dict) else ""

    if known1 and known2:
        return known1, known2

    # Phase 2: any non-meta string param value as fallback for known1
    if not known1:
        for k, v in (params or {}).items():
            if k.startswith("_"):
                continue
            if k in {"idea1", "idea2", "source", "target", "source_id",
                     "target_id", "from_idea", "to_idea", "von", "zu"}:
                continue
            if isinstance(v, str) and v.strip():
                known1 = v.strip()
                break

    # Phase 3: re-extract from _intent text
    intent = (params.get("_intent") or "").strip() if isinstance(params, dict) else ""
    if intent:
        m = regex.search(intent)
        if m:
            a, b = m.group(1).strip(), m.group(2).strip()
            if not known1:
                return a, b
            if not known2:
                # Match the existing known1 against a/b so we pair correctly
                if a.lower() == known1.lower():
                    return known1, b
                if b.lower() == known1.lower():
                    return known1, a
                # Neither — override
                return a, b

    return known1, known2


# ─── publishing helper ────────────────────────────────────────────────


def _publish(event_id: str, params: Dict[str, Any], result: str, ok: bool) -> None:
    """Best-effort publish to the brain space-event bus. Never raises."""
    try:
        from .space_event_bus import get_bus
        bus = get_bus()
        bus.publish({
            "event_id": event_id,
            "params": params,
            "result": result,
            "ok": ok,
            "source": "supabase_ideas_ops",
        })
    except Exception as e:
        logger.debug(f"[supabase_ideas_ops] publish skipped: {e}")


# ─── operations ───────────────────────────────────────────────────────


async def connect_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    title1, title2 = _extract_pair_from_params(params, _CONNECT_INTENT_RE)
    if not title1 or not title2:
        return (
            f"Need two idea names to connect. "
            f"Got: idea1={title1!r}, idea2={title2!r}"
        )
    if title1.lower() == title2.lower():
        return f"'{title1}' cannot be connected to itself."

    hits1 = await client.find_canvas_node_by_title(title1, limit=1)
    hits2 = await client.find_canvas_node_by_title(title2, limit=1)
    if not hits1:
        return f"Idea '{title1}' not found in canvas."
    if not hits2:
        return f"Idea '{title2}' not found in canvas."

    a, b = hits1[0], hits2[0]
    edge = await client.create_edge(a["id"], b["id"], edge_type="related")
    if not edge:
        return f"Failed to create connection between '{title1}' and '{title2}'."

    _publish(
        event_id="idea.connect",
        params={
            "from_id": a["id"], "to_id": b["id"],
            "from_title": a.get("title", title1),
            "to_title": b.get("title", title2),
            "label": "related",
            "edge_id": edge.get("id"),
        },
        result=f"Connected '{title1}' to '{title2}'",
        ok=True,
    )
    return f"'{a.get('title', title1)}' and '{b.get('title', title2)}' are now connected."


async def disconnect_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    title1, title2 = _extract_pair_from_params(params, _DISCONNECT_INTENT_RE)
    if not title1 or not title2:
        return f"Need two idea names to disconnect. Got: idea1={title1!r}, idea2={title2!r}"

    hits1 = await client.find_canvas_node_by_title(title1, limit=1)
    hits2 = await client.find_canvas_node_by_title(title2, limit=1)
    if not hits1:
        return f"Idea '{title1}' not found in canvas."
    if not hits2:
        return f"Idea '{title2}' not found in canvas."

    a, b = hits1[0], hits2[0]
    edge = await client.find_edge_between(a["id"], b["id"])
    if edge is None:
        return f"'{title1}' and '{title2}' are not connected."

    ok = await client.delete_edge(edge["id"])
    if not ok:
        return f"Failed to remove connection between '{title1}' and '{title2}'."

    _publish(
        event_id="idea.disconnect",
        params={
            "from_id": a["id"], "to_id": b["id"],
            "from_title": a.get("title", title1),
            "to_title": b.get("title", title2),
            "edge_id": edge.get("id"),
        },
        result=f"Disconnected '{title1}' from '{title2}'",
        ok=True,
    )
    return f"Connection between '{a.get('title', title1)}' and '{b.get('title', title2)}' removed."


def _decode_multiarg(params: Dict[str, Any]) -> Dict[str, Any]:
    """The plan_schema JSON-encodes multi-arg arg_templates into params
    under 'value'. Promote those keys to top-level (same trick as
    _extract_pair_from_params Phase 0) so create/update can read them."""
    if not isinstance(params, dict):
        return {}
    raw = params.get("value")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            import json as _json
            decoded = _json.loads(raw)
            if isinstance(decoded, dict):
                for k, v in decoded.items():
                    params.setdefault(k, v)
        except Exception:
            pass
    return params


async def _resolve_bubble_id(
    client: SupabaseIdeasClient, bubble_arg: str,
) -> Optional[str]:
    """bubble_arg may be a title or already an id. Returns the id or None."""
    ba = (bubble_arg or "").strip()
    if not ba:
        return None
    bubbles = await client.list_bubbles(limit=200)
    for b in bubbles:
        if (b.get("title") or "").strip().lower() == ba.lower():
            return b.get("id")
    # Not a known title — assume it's already an id (8-hex like ff16dc78).
    return ba


async def enter_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    """supabase:bubble.enter — no-op "enter" for the DB-direct path.

    The planner habitually prefixes idea operations with a bubble_enter
    hop (legacy stateful model). The supabase: create/update ops address
    the bubble directly by id/title, so there is no session to enter —
    but s1 must still succeed or the whole plan cascades to failure.
    This just resolves+validates the bubble exists and returns a
    non-empty string for the rule:string_nonempty validator. Replaces
    the broken direct:spaces.ideas...:enter_bubble (swarm import chain).
    """
    params = _decode_multiarg(params)
    bubble_arg = (
        params.get("bubble_name") or params.get("bubble") or
        params.get("bubble_id") or params.get("title") or
        params.get("value") or ""
    ).strip() if isinstance(params, dict) else ""
    if not bubble_arg:
        it = (params.get("_intent") or "").strip() if isinstance(params, dict) else ""
        m = re.search(r'bubble\s+["„“»]?([\w\s.\-]+?)["“”«]?\s*[\(:"]', it, re.I)
        if m:
            bubble_arg = m.group(1).strip()
        if not bubble_arg:
            mid = re.search(r"db_id[=:\s]+([0-9a-f]{6,32})", it, re.I)
            if mid:
                bubble_arg = mid.group(1)
    if not bubble_arg:
        # Nothing to resolve — still return ok so downstream create_op
        # (which re-parses the intent itself) can proceed.
        return "entered (no explicit bubble; downstream op resolves it)"

    row = await client.find_bubble_by_title(bubble_arg)
    if row is None:
        row = await client.get_idea(bubble_arg)
    if row is None:
        # Don't hard-fail: create_op can still resolve by title/id from
        # the intent. A soft ok keeps the plan alive.
        return f"entered '{bubble_arg}' (unverified — downstream op will resolve)"
    return f"entered bubble '{row.get('title', bubble_arg)}' (id={row.get('id')})"


async def create_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    """supabase:idea.create — insert ONE node into a bubble's canvas.

    Param-bag tolerant (the LLM planner uses arbitrary key names): pulls
    bubble/title/content from well-known keys, JSON multi-arg payloads,
    and finally the _intent text. Idempotent on (bubble, title) via the
    client. Publishes a node_added-style space-event for the live UI.
    """
    params = _decode_multiarg(params)
    bubble_arg = (
        params.get("bubble") or params.get("bubble_id") or
        params.get("bubble_name") or params.get("bubble_title") or
        params.get("space") or params.get("parent") or ""
    ).strip() if isinstance(params, dict) else ""
    title = (
        params.get("title") or params.get("name") or
        params.get("node_title") or params.get("note_title") or
        params.get("idea") or ""
    ).strip() if isinstance(params, dict) else ""
    content = (
        params.get("content") or params.get("description") or
        params.get("body") or params.get("text") or ""
    )
    if isinstance(content, (dict, list)):
        import json as _json
        content = _json.dumps(content, ensure_ascii=False)
    content = (content or "").strip()

    # Fallback: re-extract a title from the raw intent if the planner only
    # wrapped the value (arg_template) without a clean key.
    if not title:
        val = (params.get("value") or "").strip() if isinstance(params, dict) else ""
        if val and not val.startswith("{"):
            title = val

    # ── title/content split ───────────────────────────────────────────
    # The idea_add capability only exposes arg_kwarg=title (single arg), so
    # the planner crams "Title: <full body>" into one string. A 3000-char
    # "title" overflows canvas_nodes.title and breaks the ilike dedup.
    # Split on the first ':' / newline: short head = title, rest = content.
    if title and len(title) > 90 and not content:
        sep_idx = -1
        for sep in (": ", ":\n", "\n", " - ", " — "):
            i = title.find(sep)
            if 0 < i <= 90:
                sep_idx = i
                break
        if sep_idx > 0:
            content = title[sep_idx:].lstrip(":-—\n ").strip()
            title = title[:sep_idx].strip()
        else:
            # No clean separator in the first 90 chars — take a sane title
            # prefix and keep the whole thing as content.
            content = title.strip()
            title = title[:80].rstrip() + ("…" if len(title) > 80 else "")
    # Hard cap: canvas_nodes.title must stay short regardless.
    if len(title) > 120:
        if not content:
            content = title
        title = title[:117].rstrip() + "…"

    # ── _intent fallback ──────────────────────────────────────────────
    # When the planner couldn't fit bubble/content into clean keys, the
    # executor still hands us the full plan intent under `_intent`. Mine
    # it for: (a) a bubble id (8-hex like ff16dc78) or db_id=… mention,
    # (b) a quoted bubble name, (c) a 'Titel "X"' node title, (d) the
    # 'Inhalt:' descriptive remainder as content.
    intent_txt = (params.get("_intent") or "").strip() if isinstance(params, dict) else ""
    if intent_txt:
        if not bubble_arg:
            m = re.search(r"db_id[=:\s]+([0-9a-f]{6,32})", intent_txt, re.I)
            if m:
                bubble_arg = m.group(1)
            else:
                # Phase 11.W2 (A.4) — the old pattern required a '(' or ':'
                # right after the bubble name, so "… in der Bubble Foo_Bar."
                # (trailing period / end-of-string) never matched and the op
                # early-returned. Accept quote-delimited, or a bare token up
                # to a terminator (punctuation / 'mit'/'with' / EOL).
                for pat in (
                    r'bubble\s+["„“»]([^"“”«]+)["“”«]',           # quoted
                    r'(?:bubble|space|raum)\s+([\w.\-]+)',         # bare token
                ):
                    mq = re.search(pat, intent_txt, re.I)
                    if mq:
                        bubble_arg = mq.group(1).strip().rstrip(".,;:")
                        break
        if not title:
            mt = re.search(
                r'(?:Titel|title|Note|Notiz)\s+["„“»]([^"“”«]+)',
                intent_txt, re.I,
            )
            if mt:
                title = mt.group(1).strip()[:120]
        if not content:
            mc = re.search(
                r"(?:Inhalt|content|body|text)\s*:?\s*[\"„“»]?([^\"“”«]+)",
                intent_txt, re.I | re.S,
            )
            if mc:
                content = mc.group(1).strip()

    if not bubble_arg:
        return {
            "ok": False,
            "error": (
                "Need a bubble (title or id) to create a node in. "
                f"Got params keys: "
                f"{sorted(params.keys()) if isinstance(params, dict) else params!r}"
            ),
        }
    if not title:
        return {
            "ok": False,
            "error": f"Need a node title. Got bubble={bubble_arg!r} but no title.",
        }

    bubble_id = await _resolve_bubble_id(client, bubble_arg)
    if not bubble_id:
        return {"ok": False, "error": f"Bubble {bubble_arg!r} not found."}

    node = await client.create_canvas_node(bubble_id, title, content)
    if not node or not node.get("id"):
        return {
            "ok": False,
            "error": f"Failed to create node '{title}' in bubble {bubble_arg!r}.",
        }

    # Phase 11.W2 (A.3) — read-back verify. create_canvas_node can return a
    # locally-built dict on an ambiguous POST response; the only honest
    # confirmation that the row is really persisted is to read it back from
    # the DB. The hard validator rule:canvas_node_persisted keys off the
    # `node_id` in this dict, so we MUST NOT report one we can't re-fetch.
    node_id = node.get("id")
    verified = await client.get_canvas_node_in_bubble(bubble_id, title)
    if not verified or not verified.get("id"):
        return {
            "ok": False,
            "error": (
                f"Node '{title}' POST returned id={node_id} but the row is "
                f"not readable back from bubble {bubble_arg!r} — treating as "
                f"NOT persisted."
            ),
        }
    node_id = verified.get("id") or node_id

    _publish(
        event_id="idea.create",
        params={
            "node_id": node_id,
            "bubble_id": bubble_id,
            "title": verified.get("title", title),
            "content": verified.get("content", content),
            "x": verified.get("x"), "y": verified.get("y"),
        },
        result=f"Created node '{title}' in bubble {bubble_arg}",
        ok=True,
    )
    return {
        "ok": True,
        "created": True,
        "node_id": node_id,
        "bubble_id": bubble_id,
        "title": verified.get("title", title),
        "message": (
            f"Node '{verified.get('title', title)}' (id={node_id}) "
            f"verified in bubble '{bubble_arg}'."
        ),
    }


async def update_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    """supabase:idea.update — patch an existing node's content/title.

    Resolves the node by title (within a bubble if given, else global),
    then PATCHes the supplied fields. Used as the 2nd hop after
    idea.create when the planner splits create-then-fill.
    """
    params = _decode_multiarg(params)
    title = (
        params.get("title") or params.get("name") or
        params.get("node_title") or params.get("idea") or
        params.get("target") or ""
    ).strip() if isinstance(params, dict) else ""
    new_content = (
        params.get("content") or params.get("description") or
        params.get("body") or params.get("text") or ""
    )
    if isinstance(new_content, (dict, list)):
        import json as _json
        new_content = _json.dumps(new_content, ensure_ascii=False)
    new_content = (new_content or "").strip()
    new_title = (params.get("new_title") or params.get("rename_to") or "").strip() \
        if isinstance(params, dict) else ""
    bubble_arg = (
        params.get("bubble") or params.get("bubble_id") or
        params.get("bubble_name") or ""
    ).strip() if isinstance(params, dict) else ""

    # If the planner only passed the value (the content) without a title,
    # we can't resolve which node — surface that clearly.
    if not title:
        return (
            "Need the node title to update. "
            f"Got params keys: {sorted(params.keys()) if isinstance(params, dict) else params!r}"
        )
    if not new_content and not new_title:
        return f"Nothing to update on '{title}' (no content/new_title given)."

    # Resolve node: prefer scoped-to-bubble if bubble given.
    node = None
    if bubble_arg:
        bubble_id = await _resolve_bubble_id(client, bubble_arg)
        if bubble_id:
            in_bubble = await client.list_canvas_nodes_in_bubble(bubble_id, limit=300)
            for n in in_bubble:
                if (n.get("title") or "").strip().lower() == title.lower():
                    node = await client.get_canvas_node(n["id"])
                    break
    if node is None:
        hits = await client.find_canvas_node_by_title(title, limit=1)
        if hits:
            node = await client.get_canvas_node(hits[0]["id"])
    if node is None:
        return f"Node '{title}' not found."

    fields: Dict[str, Any] = {}
    if new_content:
        fields["content"] = new_content
    if new_title:
        fields["title"] = new_title
    updated = await client.update_canvas_node(node["id"], fields)
    if not updated:
        return f"Failed to update node '{title}'."

    _publish(
        event_id="idea.update",
        params={
            "node_id": node["id"],
            "title": new_title or node.get("title", title),
            "content": new_content or node.get("content", ""),
        },
        result=f"Updated node '{title}'",
        ok=True,
    )
    return f"Node '{title}' updated ({', '.join(fields.keys())})."


_EVAL_PROMPT = """\
You are a project-readiness evaluator. Score this idea-bubble on FOUR
dimensions, each 0-10 (integer):

- completeness: are goals, requirements, scope clearly covered?
- structure:    is it logically organised and well connected?
- actionability: can it be turned into concrete tasks / deliverables?
- depth:        are the items detailed and thoroughly explored?

BUBBLE: {title}
NODE COUNT: {n}

NODE TITLES + CONTENT (truncated):
{nodes}

Return STRICT JSON only, no prose:
{{"completeness": <0-10>, "structure": <0-10>, "actionability": <0-10>,
"depth": <0-10>, "summary": "<=2 sentence honest assessment",
"recommendations": ["<concrete gap 1>", "<gap 2>", "<gap 3>"]}}"""


def _get_eval_router():
    """Build a MultiLLMRouter for the eval LLM call. Executor threads have
    no app.state, so we construct our own (it reads keys from os.environ,
    same as the server's). Cached on the module so repeated evals reuse it.
    """
    global _EVAL_ROUTER
    try:
        return _EVAL_ROUTER  # type: ignore[name-defined]
    except NameError:
        pass
    try:
        from .multi_llm_router import MultiLLMRouter
        from .subagent_dispatcher import SubagentDispatcher
        router = MultiLLMRouter()
        _EVAL_ROUTER = SubagentDispatcher(router)  # type: ignore[name-defined]
    except Exception as e:
        logger.warning(f"[evaluate_op] router build failed: {e}")
        _EVAL_ROUTER = None  # type: ignore[name-defined]
    return _EVAL_ROUTER  # type: ignore[name-defined]


def _llm_call(prompt: str, *, max_tokens: int = 700) -> Dict[str, Any]:
    """Groq-primary with OpenAI-direct fallback — same resilience the
    planner has. Groq's free-tier TPM trips on burst use (429); when it
    does, gpt-4o-mini via openai_subagent hits api.openai.com directly
    (NOT OpenRouter, so it survives the 402-credit-exhausted state)."""
    d = _get_eval_router()
    if d is None:
        return {"ok": False, "error": "LLM router unavailable"}
    r = d.dispatch("groq_subagent", prompt=prompt,
                   model="groq::llama-3.3-70b-versatile",
                   max_tokens=max_tokens)
    if r.get("ok"):
        return r
    err = str(r.get("error") or "")
    # Fall back on rate-limit / quota / transient errors only.
    if any(s in err for s in ("429", "Too Many Requests", "rate",
                              "ConnectError", "timeout", "5xx", "503")):
        logger.info(f"[llm] groq failed ({err[:60]}); OpenAI-direct fallback")
        fb = d.dispatch("openai_subagent", prompt=prompt,
                        model="gpt-4o-mini", max_tokens=max_tokens)
        if fb.get("ok"):
            return fb
        return fb  # surface the fallback error
    return r


async def evaluate_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    """supabase:bubble.evaluate — 4-dim readiness eval, no spaces/mirofish.

    Reads canvas_nodes via REST, scores via Brain's groq_subagent, writes
    metadata.ai_eval + score back to ideas, and publishes a
    `bubble_evolution_scored` space-event the renderer already handles.
    """
    params = _decode_multiarg(params)
    # db_id FIRST — the planner often sends arg_kwarg=db_id with the UUID.
    bubble_arg = (
        params.get("db_id") or params.get("bubble") or
        params.get("bubble_name") or params.get("bubble_id") or
        params.get("title") or params.get("value") or ""
    ).strip() if isinstance(params, dict) else ""
    # Guard: reject useless stop-words the regex/planner sometimes yields
    # ('the', 'die', 'this', 'a') so we fall through to the _intent parse.
    if bubble_arg.lower() in {"the", "die", "this", "a", "an", "bubble"}:
        bubble_arg = ""
    if not bubble_arg:
        it = (params.get("_intent") or "").strip() if isinstance(params, dict) else ""
        # 1) explicit db_id=<hex> in the intent text
        mid = re.search(r"db_id[=:\s]+([0-9a-f]{6,32})", it, re.I)
        if mid:
            bubble_arg = mid.group(1)
        else:
            # 2) a QUOTED bubble name wins (handles "evaluate the
            #    bubble \"E-Ticketing_DE\"" — the quotes are the signal,
            #    not the word order). Non-greedy + stop-word exclusion.
            mq = re.search(r'["„“»]([\w.\-]{2,80})["“”«»]', it)
            if mq:
                bubble_arg = mq.group(1).strip()
            else:
                # 3) 'evaluate <name> bubble' but require <name> to NOT be
                #    a stop-word and to look like a real title (letters).
                m = re.search(
                    r'(?:evaluate|bewerte|assess)\s+(?:the\s+|die\s+|this\s+)?'
                    r'(?:bubble\s+)?([A-Za-z][\w.\-]{1,79})', it, re.I)
                if m and m.group(1).lower() not in {
                        "the", "die", "this", "bubble", "a", "an"}:
                    bubble_arg = m.group(1).strip()
    if not bubble_arg:
        return "Need a bubble name/id to evaluate."

    # Resolve bubble (title or id)
    row = await client.find_bubble_by_title(bubble_arg)
    if row is None:
        row = await client.get_idea(bubble_arg)
    if row is None:
        return f"Bubble {bubble_arg!r} not found."
    bubble_id = row["id"]
    bubble_title = row.get("title", bubble_arg)

    nodes = await client.list_canvas_nodes_in_bubble(bubble_id, limit=300)
    if not nodes:
        return f"Bubble '{bubble_title}' has no nodes to evaluate."

    # Need content too — list_canvas_nodes_in_bubble only returns id/title.
    detailed: List[Dict[str, Any]] = []
    for n in nodes[:120]:  # cap so the prompt stays bounded
        full = await client.get_canvas_node(n["id"])
        if full:
            detailed.append(full)
    node_block = "\n".join(
        f"- {d.get('title','?')}: {((d.get('content') or '')[:240]).strip()}"
        for d in detailed
    )

    prompt = _EVAL_PROMPT.format(
        title=bubble_title, n=len(nodes), nodes=node_block[:12000],
    )
    resp = _llm_call(prompt, max_tokens=700)
    if not resp.get("ok"):
        return f"Eval LLM call failed: {resp.get('error')}"
    text = (resp.get("text") or "").strip()

    # Parse the JSON (tolerate fences / leading prose)
    import json as _json
    blob = None
    mfence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = mfence.group(1) if mfence else text[text.find("{"):] if "{" in text else ""
    for end in range(len(raw), 0, -1):
        if raw[end - 1] != "}":
            continue
        try:
            blob = _json.loads(raw[:end])
            break
        except _json.JSONDecodeError:
            continue
    if not isinstance(blob, dict):
        return f"Eval returned unparseable output: {text[:160]!r}"

    def _clamp(v: Any) -> int:
        try:
            return max(0, min(10, int(round(float(v)))))
        except Exception:
            return 0

    ai_eval = {
        "completeness": _clamp(blob.get("completeness")),
        "structure": _clamp(blob.get("structure")),
        "actionability": _clamp(blob.get("actionability")),
        "depth": _clamp(blob.get("depth")),
        "summary": str(blob.get("summary") or "")[:600],
        "recommendations": [
            str(r)[:300] for r in (blob.get("recommendations") or [])
        ][:5],
    }
    # Same 0-100 scaling the renderer expects (4 dims, ×2.5 → /25 bars,
    # overall = mean of dims scaled to 100).
    dims = [ai_eval["completeness"], ai_eval["structure"],
            ai_eval["actionability"], ai_eval["depth"]]
    score = round(sum(dims) / len(dims) * 10.0, 1)  # 0-10 mean → 0-100

    saved = await client.update_idea_eval(bubble_id, ai_eval, score)
    if not saved:
        return f"Eval computed (score {score}) but DB write failed."

    _publish(
        event_id="bubble_evolution_scored",
        params={
            "bubble_id": bubble_id,
            "title": bubble_title,
            "score": score,
            "details": {
                "completeness": ai_eval["completeness"],
                "structure": ai_eval["structure"],
                "actionability": ai_eval["actionability"],
                "depth": ai_eval["depth"],
                "summary": ai_eval["summary"],
                "recommendations": ai_eval["recommendations"],
            },
        },
        result=f"Evaluated '{bubble_title}': {score}/100",
        ok=True,
    )
    rec = "; ".join(ai_eval["recommendations"][:3]) or "—"
    return (
        f"'{bubble_title}' scored {score}/100 "
        f"(completeness {ai_eval['completeness']}, structure {ai_eval['structure']}, "
        f"actionability {ai_eval['actionability']}, depth {ai_eval['depth']}). "
        f"Top gaps: {rec}"
    )


async def auto_link_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> str:
    """Connect all nodes in a bubble that have similar titles.

    For now: pure title-based naive matching (jaccard on word-tokens).
    Embedding-based similarity is a fast follow once we wire the embedder
    cache into Brain. This still produces useful edges and validates the
    end-to-end pipeline.
    """
    bubble_arg = (
        params.get("bubble") or params.get("bubble_id") or
        params.get("bubble_name") or ""
    ).strip()
    threshold = float(params.get("threshold") or 0.30)
    max_links = int(params.get("max_links") or 20)

    logger.info(
        f"[auto_link] bubble_arg={bubble_arg!r} params_keys={list(params.keys())}"
    )

    # Resolve bubble ID. Empty bubble = scan top-level (parent_id IS NULL)
    bubble_id: Optional[str] = None
    if bubble_arg:
        bubbles = await client.list_bubbles(limit=200)
        logger.info(f"[auto_link] {len(bubbles)} bubbles found")
        for b in bubbles:
            if b.get("title", "").strip().lower() == bubble_arg.lower():
                bubble_id = b.get("id")
                break
        if bubble_id is None:
            # Maybe it's already an id
            bubble_id = bubble_arg
    logger.info(f"[auto_link] resolved bubble_id={bubble_id!r}")

    nodes = await client.list_canvas_nodes_in_bubble(bubble_id, limit=200)
    logger.info(f"[auto_link] found {len(nodes)} nodes in bubble {bubble_id!r}")
    if len(nodes) < 2:
        return f"Bubble {bubble_id!r} has {len(nodes)} nodes — need at least 2 to auto-link."

    def _tokens(title: str) -> set[str]:
        return {w for w in re.findall(r"\w+", (title or "").lower()) if len(w) > 2}

    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    # Existing edges so we skip already-connected pairs
    existing_edges = await client.list_edges(limit=500)
    existing_pairs = set()
    for e in existing_edges:
        f, t = e.get("from_node_id"), e.get("to_node_id")
        if f and t:
            existing_pairs.add(tuple(sorted([f, t])))

    candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
    for i in range(len(nodes)):
        ti = _tokens(nodes[i].get("title", ""))
        for j in range(i + 1, len(nodes)):
            pair = tuple(sorted([nodes[i]["id"], nodes[j]["id"]]))
            if pair in existing_pairs:
                continue
            sim = _jaccard(ti, _tokens(nodes[j].get("title", "")))
            if sim >= threshold:
                candidates.append((sim, nodes[i], nodes[j]))

    candidates.sort(key=lambda c: c[0], reverse=True)
    candidates = candidates[:max_links]

    if not candidates:
        return (
            f"No matching pairs found (threshold {threshold:.0%}, "
            f"{len(nodes)} nodes scanned)."
        )

    created: List[Dict[str, Any]] = []
    for sim, a, b in candidates:
        edge = await client.create_edge(a["id"], b["id"], edge_type="related")
        if edge:
            created.append({
                "from_id": a["id"], "to_id": b["id"],
                "from_title": a.get("title", ""), "to_title": b.get("title", ""),
                "score": round(sim, 3),
                "edge_id": edge.get("id"),
                "label": "related",
            })

    if created:
        _publish(
            event_id="idea.auto_link",
            params={
                "bubble_id": bubble_id,
                "edges": created,
                "count": len(created),
                "threshold": threshold,
            },
            result=f"auto-linked {len(created)} edges in bubble {bubble_id}",
            ok=True,
        )

    summary = (
        f"Auto-linked {len(created)} connections "
        f"(threshold {threshold:.0%}, scanned {len(nodes)} nodes)."
    )
    # Ground truth (Phase 1): name ONE concretely created pair, quoted. The
    # truth:supabase_edge validator fills {result_title}/{result_title2} from
    # the quoted substrings of this string and re-queries canvas_edges for that
    # pair. Without a quoted pair the postcondition keeps its placeholders and
    # capability_validator short-circuits to UNVERIFIED — the check could never
    # fire. If nothing was created there is nothing to verify, so we leave the
    # summary bare on purpose (UNVERIFIED is then the honest outcome).
    if created:
        first = created[0]
        summary += (
            f" first_pair='{first['from_title']}' <-> '{first['to_title']}'"
        )
    return summary


# ════════════════════════════════════════════════════════════════════════
# Phase 11.U.H — Full-cap migration. The 36 capabilities that pointed at
# direct:spaces.* (a code path that does NOT exist in the Brain container)
# now route here. All REST against Supabase, the single source of truth.
# ════════════════════════════════════════════════════════════════════════


def _arg(params: Dict[str, Any], *keys: str) -> str:
    """First non-empty string value among the given param keys, then a
    generic scan, then the _intent fallback. Mirrors the tolerant pattern
    used by create_op/_extract_pair_from_params."""
    params = _decode_multiarg(params)
    if not isinstance(params, dict):
        return ""
    for k in keys:
        v = params.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # generic: any non-meta string value
    for k, v in params.items():
        if k.startswith("_") or k in keys:
            continue
        if k in {"value"} and isinstance(v, str) and not v.strip().startswith("{"):
            return v.strip()
    return ""


def _intent_text(params: Dict[str, Any]) -> str:
    return (params.get("_intent") or "").strip() \
        if isinstance(params, dict) else ""


async def _resolve_bubble(client: SupabaseIdeasClient, params: Dict[str, Any],
                          *keys: str) -> Optional[Dict[str, Any]]:
    """Resolve a bubble row from param keys or the _intent (title or
    db_id=… or quoted name)."""
    arg = _arg(params, *(keys or ("bubble", "bubble_name", "bubble_id",
                                   "title", "name")))
    if not arg:
        it = _intent_text(params)
        m = re.search(r"db_id[=:\s]+([0-9a-f]{6,32})", it, re.I)
        if m:
            arg = m.group(1)
        else:
            mq = re.search(r'bubble\s+["„“»]?([\w\s.\-]+?)["“”«]?\s*[\(:"]',
                           it, re.I)
            if mq:
                arg = mq.group(1).strip()
    if not arg:
        return None
    row = await client.find_bubble_by_title(arg)
    if row is None:
        row = await client.get_idea(arg)
    return row


# ─── bubble_crud group ────────────────────────────────────────────────


async def bubble_create_op(client: SupabaseIdeasClient,
                            params: Dict[str, Any]) -> str:
    title = _arg(params, "title", "name", "bubble_name", "bubble")
    if not title:
        it = _intent_text(params)
        m = re.search(r'(?:bubble|space)\s+(?:called\s+|named\s+|["„“])?'
                      r'([\w .\-]{2,80})', it, re.I)
        if m:
            title = m.group(1).strip().strip('"„“”«»')
    # Strip an accidental "Title: <body>" — bubbles get a short title only.
    if len(title) > 90:
        title = title.split(":")[0].strip()[:80]
    if not title:
        return "Need a bubble title."
    desc = _arg(params, "description", "content", "body")
    row = await client.create_bubble(title, description=desc)
    if not row:
        return f"Failed to create bubble '{title}'."
    _publish("bubble.create",
             {"bubble_id": row.get("id"), "title": row.get("title", title)},
             f"Created bubble '{title}'", True)
    return f"Bubble '{row.get('title', title)}' (id={row.get('id')}) created."


async def bubble_list_op(client: SupabaseIdeasClient,
                         params: Dict[str, Any]) -> str:
    q = _arg(params, "query", "filter", "name")
    rows = (await client.find_bubbles_like(q)) if q \
        else (await client.list_top_bubbles())
    if not rows:
        return "No bubbles found."
    head = rows[:30]
    lines = [f"- {r.get('title','?')} (id={r.get('id')}, "
             f"score={r.get('score',0)})" for r in head]
    more = "" if len(rows) <= 30 else f"\n…(+{len(rows)-30} more)"
    return f"{len(rows)} bubbles:\n" + "\n".join(lines) + more


async def bubble_find_op(client: SupabaseIdeasClient,
                         params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "name", "bubble",
                                "bubble_name", "query", "title")
    if row is None:
        return "Bubble not found."
    return (f"Found '{row.get('title')}' (id={row.get('id')}, "
            f"score={row.get('score',0)}, status={row.get('status','')}).")


async def bubble_update_op(client: SupabaseIdeasClient,
                           params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble_name", "bubble",
                                "old_title", "name")
    if row is None:
        return "Bubble to update not found."
    fields: Dict[str, Any] = {}
    new_title = _arg(params, "new_title", "title", "rename_to")
    if new_title and new_title.lower() != (row.get("title") or "").lower():
        fields["title"] = new_title
    new_desc = _arg(params, "new_description", "description", "content")
    if new_desc:
        fields["description"] = new_desc
    if not fields:
        return f"Nothing to update on '{row.get('title')}'."
    ok = await client.update_idea(row["id"], fields)
    if not ok:
        return f"Failed to update bubble '{row.get('title')}'."
    _publish("bubble.update",
             {"bubble_id": row["id"], "new_title": fields.get("title"),
              "bubble_name": row.get("title")},
             f"Updated bubble '{row.get('title')}'", True)
    return f"Bubble '{row.get('title')}' updated ({', '.join(fields)})."


async def bubble_delete_op(client: SupabaseIdeasClient,
                           params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble_name", "bubble",
                                "name", "title")
    if row is None:
        return "Bubble to delete not found."
    ok = await client.delete_idea_row(row["id"])
    if not ok:
        return f"Failed to delete bubble '{row.get('title')}'."
    _publish("bubble.delete",
             {"bubble_id": row["id"], "bubble_name": row.get("title")},
             f"Deleted bubble '{row.get('title')}'", True)
    return f"Bubble '{row.get('title')}' deleted."


async def bubble_stats_op(client: SupabaseIdeasClient,
                          params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble_name", "bubble",
                                "name", "title")
    if row is None:
        return "Bubble not found."
    st = await client.bubble_node_stats(row["id"])
    types = ", ".join(f"{k}:{v}" for k, v in st["by_type"].items()) or "—"
    return (f"'{row.get('title')}' — {st['node_count']} nodes "
            f"({types}), {st['edge_count']} edges, "
            f"score {row.get('score',0)}.")


async def bubble_score_op(client: SupabaseIdeasClient,
                          params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble_name", "bubble",
                                "name", "title")
    if row is None:
        return "Bubble not found."
    return (f"'{row.get('title')}' readiness score: "
            f"{row.get('score',0)}/100 (status {row.get('status','')}). "
            f"Run bubble_evaluate for a fresh 4-dim assessment.")


async def bubble_promote_op(client: SupabaseIdeasClient,
                            params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble_name", "bubble",
                                "bubble_id", "name", "title")
    if row is None:
        return "Bubble to promote not found."
    project = await client.promote_bubble(row)
    if not project:
        return f"Failed to promote bubble '{row.get('title')}'."
    title = row.get("title") or project.get("name") or "?"
    project_id = project.get("id")
    _publish("bubble.promote",
             {"bubble_id": row.get("id"), "title": title,
              "project_id": project_id, "space": "bubbles"},
             f"Promoted bubble '{title}' to project {project_id}", True)
    return f"Bubble '{title}' promoted to project (id={project_id})."


async def bubble_noop_op(client: SupabaseIdeasClient,
                         params: Dict[str, Any]) -> str:
    """bubble_exit — stateless navigation, there is genuinely nothing to write.

    A no-op may ONLY back a capability where nothing is supposed to happen.
    For a write capability, a fabricated "ok" is a FAKE SIGNAL: the user
    believes the write happened and the diary learns "this capability works".
    The write-caps that used to route here lost their execution_target on
    2026-07-14 (see data/capabilities.yaml) so the planner routes elsewhere
    and the GapSentinel reports the real gap instead."""
    return "ok (no-op in supabase-direct mode — stateless or deferred)."


# ─── idea_crud group ──────────────────────────────────────────────────


async def idea_list_op(client: SupabaseIdeasClient,
                        params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble", "bubble_id",
                                "query", "bubble_name")
    if row is None:
        return "Specify a bubble to list ideas from."
    nodes = await client.list_canvas_nodes_in_bubble(row["id"], limit=300)
    if not nodes:
        return f"'{row.get('title')}' has no ideas yet."
    head = nodes[:40]
    lines = [f"- {n.get('title','?')}" for n in head]
    more = "" if len(nodes) <= 40 else f"\n…(+{len(nodes)-40} more)"
    return (f"{len(nodes)} ideas in '{row.get('title')}':\n"
            + "\n".join(lines) + more)


async def idea_count_op(client: SupabaseIdeasClient,
                         params: Dict[str, Any]) -> str:
    row = await _resolve_bubble(client, params, "bubble_id", "bubble",
                                "bubble_name")
    if row is None:
        return "Specify a bubble to count ideas in."
    nodes = await client.list_canvas_nodes_in_bubble(row["id"], limit=2000)
    return f"'{row.get('title')}' has {len(nodes)} ideas."


async def idea_find_op(client: SupabaseIdeasClient,
                        params: Dict[str, Any]) -> str:
    name = _arg(params, "name", "title", "idea", "query")
    if not name:
        return "Need an idea name to find."
    bubble = await _resolve_bubble(client, params, "bubble", "bubble_name")
    node = await client.find_node_by_title(
        name, bubble_id=(bubble or {}).get("id"))
    if node is None:
        return f"Idea '{name}' not found."
    return (f"Found '{node.get('title')}' (id={node.get('id')}) — "
            f"{(node.get('content') or '')[:160]}")


async def idea_delete_op(client: SupabaseIdeasClient,
                          params: Dict[str, Any]) -> str:
    name = _arg(params, "name", "title", "idea", "idea_id")
    if not name:
        return "Need an idea name/id to delete."
    bubble = await _resolve_bubble(client, params, "bubble", "bubble_name")
    node = await client.find_node_by_title(
        name, bubble_id=(bubble or {}).get("id"))
    if node is None:
        node = await client.get_canvas_node(name)  # maybe an id
    if node is None:
        return f"Idea '{name}' not found."
    ok = await client.delete_canvas_node(node["id"])
    if not ok:
        return f"Failed to delete idea '{node.get('title', name)}'."
    _publish("idea.delete",
             {"node_id": node["id"], "title": node.get("title")},
             f"Deleted idea '{node.get('title')}'", True)
    return f"Idea '{node.get('title', name)}' deleted."


async def idea_to_project_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> Dict[str, Any]:
    """Promote an idea/bubble to a Supabase project and verify persistence."""
    name = _arg(params, "name", "title", "idea", "idea_id")
    if not name:
        return {"ok": False, "verified": False,
                "error": "Need an idea name/id to create a project."}
    idea = await client.find_bubble_by_title(name)
    if idea is None:
        idea = await client.get_idea(name)
    if idea is None:
        return {"ok": False, "verified": False,
                "error": f"Idea {name!r} not found."}
    project = await client.create_project_from_idea(idea)
    project_id = str((project or {}).get("id") or "")
    if not project_id:
        return {"ok": False, "verified": False,
                "error": f"Failed to create project from idea {name!r}."}
    verified = await client.get_project(project_id)
    if verified is None or verified.get("from_idea_id") != idea.get("id"):
        return {"ok": False, "verified": False, "project_id": project_id,
                "idea_id": idea.get("id"),
                "error": "Project write could not be verified by read-back."}
    if not await client.mark_idea_promoted(idea["id"], project_id):
        return {"ok": False, "verified": False, "project_id": project_id,
                "idea_id": idea.get("id"),
                "error": "Project persisted but source idea promotion link failed."}
    result = {"ok": True, "project_id": project_id,
              "idea_id": idea["id"], "name": verified.get("name") or idea["title"],
              "verified": True}
    _publish("idea.to_project", result,
             f"Promoted idea '{idea.get('title')}' to project {project_id}", True)
    return result


async def idea_move_op(client: SupabaseIdeasClient,
                        params: Dict[str, Any]) -> str:
    name = _arg(params, "idea_name", "name", "idea", "title")
    if not name:
        return "Need an idea name to move."
    node = await client.find_node_by_title(name)
    if node is None:
        return f"Idea '{name}' not found."
    target = await _resolve_bubble(client, params, "target", "to",
                                   "target_bubble", "bubble", "to_bubble")
    if target is None:
        return f"Target bubble for moving '{name}' not found."
    upd = await client.update_canvas_node(
        node["id"], {})  # node stays; only linkage changes via PATCH below
    # linked_idea_id is the bubble pointer — patch it directly.
    res = await client._request(
        "PATCH", "/canvas_nodes",
        params={"id": f"eq.{node['id']}"},
        json={"linked_idea_id": target["id"]},
        prefer="return=representation",
    )
    if not res:
        return f"Failed to move '{name}'."
    _publish("idea.move",
             {"node_id": node["id"], "to_bubble": target["id"],
              "title": node.get("title")},
             f"Moved '{name}' to '{target.get('title')}'", True)
    return f"Idea '{name}' moved to bubble '{target.get('title')}'."


# ─── idea_format group (15 caps → one op, format from capability) ──────


_FORMAT_MAP = {
    "idea_format_table": "table", "idea_format_note": "note",
    "idea_format_action_list": "action_list",
    "idea_format_pros_cons": "pros_cons",
    "idea_format_hierarchy": "hierarchy",
    "idea_format_specs": "technical_specs",
    "idea_format_kanban": "kanban", "idea_format_mindmap": "mindmap",
    "idea_format_swot": "swot", "idea_format_user_story": "user_story",
    "idea_format_flowchart": "flowchart",
}


async def idea_format_op(client: SupabaseIdeasClient,
                         params: Dict[str, Any]) -> str:
    """One op for all idea_format_* + convert/revert/get/list. The desired
    format comes from the capability name (passed as _capability) or an
    explicit 'format' param."""
    cap = (params.get("_capability") or "").strip() \
        if isinstance(params, dict) else ""
    fmt = (params.get("format") or params.get("format_type") or "").strip() \
        if isinstance(params, dict) else ""
    if not fmt and cap in _FORMAT_MAP:
        fmt = _FORMAT_MAP[cap]
    if cap == "idea_format_list":
        return ("Available formats: " + ", ".join(sorted(
            set(_FORMAT_MAP.values()))) + ", revert.")
    name = _arg(params, "idea_name", "name", "title", "idea")
    if not name:
        return "Need an idea name to format."
    bubble = await _resolve_bubble(client, params, "bubble", "bubble_name")
    node = await client.find_node_by_title(
        name, bubble_id=(bubble or {}).get("id"))
    if node is None:
        return f"Idea '{name}' not found."
    if cap == "idea_format_get":
        cur = (node.get("format_schema") or {}).get("type") \
            or node.get("node_type", "note")
        return f"'{node.get('title')}' current format: {cur}"
    if cap == "idea_format_revert":
        prev = node.get("previous_content_json")
        if not prev:
            return f"No previous format to revert '{node.get('title')}' to."
        await client._request(
            "PATCH", "/canvas_nodes",
            params={"id": f"eq.{node['id']}"},
            json={"content_json": prev,
                  "format_schema": {"type": prev.get("type", "note")}},
            prefer="return=representation")
        _publish("idea.update", {"node_id": node["id"]},
                 f"Reverted '{node.get('title')}'", True)
        return f"'{node.get('title')}' reverted to previous format."
    if not fmt:
        fmt = "note"
    res = await client.format_canvas_node(node["id"], fmt)
    if not res:
        return f"Failed to format '{node.get('title')}' as {fmt}."
    _publish("idea.update",
             {"node_id": node["id"], "title": node.get("title"),
              "format": fmt},
             f"Formatted '{node.get('title')}' as {fmt}", True)
    return f"Idea '{node.get('title')}' formatted as {fmt}."


# ─── idea_advanced group (LLM-backed: expand/classify/explain) ─────────


async def idea_llm_op(client: SupabaseIdeasClient,
                       params: Dict[str, Any]) -> str:
    """expand / classify / explain — small LLM call via the shared eval
    router (groq, with the planner's OpenAI-direct fallback). link_to_root
    + analyze_links are graph ops handled here too."""
    cap = (params.get("_capability") or "").strip() \
        if isinstance(params, dict) else ""
    name = _arg(params, "idea_id", "idea", "name", "title")
    bubble = await _resolve_bubble(client, params, "bubble", "bubble_name")

    if cap == "idea_analyze_links":
        if bubble is None:
            return "Specify a bubble to analyze links in."
        # reuse auto_link's jaccard preview without writing edges
        nodes = await client.list_canvas_nodes_in_bubble(bubble["id"],
                                                         limit=300)
        return (f"'{bubble.get('title')}' has {len(nodes)} nodes. "
                f"Run idea_auto_link to create semantic edges.")

    node = await client.find_node_by_title(
        name, bubble_id=(bubble or {}).get("id")) if name else None
    if cap == "idea_link_to_root":
        if node is None or bubble is None:
            return "Need an idea + its bubble to link to root."
        # link to the first node in the bubble as a pragmatic 'root'
        siblings = await client.list_canvas_nodes_in_bubble(bubble["id"],
                                                            limit=2)
        root = next((s for s in siblings if s["id"] != node["id"]), None)
        if root is None:
            return "No root node to link to."
        await client.create_edge(root["id"], node["id"], "related")
        _publish("idea.connect",
                 {"from_id": root["id"], "to_id": node["id"]},
                 f"Linked '{node.get('title')}' to root", True)
        # Ground truth (Phase 1): quote BOTH edge endpoints — the resolved root's
        # title too, not just the idea's. truth:supabase_edge fills
        # {result_title}/{result_title2} from the quoted substrings in order; with
        # only one quoted title {result_title2} stayed unresolved and the check
        # short-circuited to UNVERIFIED, so it could never fire.
        return (f"Linked '{node.get('title')}' to root "
                f"'{root.get('title')}'.")

    if node is None:
        return f"Idea '{name}' not found."
    body = (node.get("content") or node.get("title") or "")[:2000]
    if cap == "idea_classify":
        prompt = (f"Classify this idea into ONE short category word.\n\n"
                  f"{node.get('title')}: {body}\n\nCategory:")
    elif cap == "idea_explain":
        prompt = (f"Explain this idea in 2-3 clear sentences.\n\n"
                  f"{node.get('title')}: {body}")
    else:  # idea_expand
        prompt = (f"Suggest 3 concrete sub-ideas for this. One per line.\n\n"
                  f"{node.get('title')}: {body}")
    resp = _llm_call(prompt, max_tokens=300)
    if not resp.get("ok"):
        return f"LLM call failed: {resp.get('error')}"
    txt = (resp.get("text") or "").strip()
    if cap == "idea_expand":
        # Create child nodes for each suggested line.
        created = 0
        for line in [l.strip("-• ").strip() for l in txt.splitlines()
                     if l.strip()][:3]:
            if not line:
                continue
            ch = await client.create_canvas_node(
                bubble["id"] if bubble else node.get("linked_idea_id", ""),
                line[:80], line)
            if ch:
                created += 1
        _publish("idea.create", {"parent": node["id"], "count": created},
                 f"Expanded '{node.get('title')}' into {created}", True)
        return (f"Expanded '{node.get('title')}' into {created} "
                f"sub-ideas:\n{txt[:400]}")
    return f"{cap.replace('idea_','').title()} of '{node.get('title')}': {txt[:400]}"

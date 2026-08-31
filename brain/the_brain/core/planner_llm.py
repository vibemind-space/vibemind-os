"""Planner LLM — Phase 6.

Decomposes a complex user intent into a multi-hop Plan via Groq
Llama-3.3-70b-versatile (cheap, fast, JSON-strong). Falls back to a
single-hop plan if the LLM call fails or returns un-parseable JSON.

Design:
  - prompt is hardcoded, lists the 15 capabilities + 7 target kinds + the
    JSON schema, with a single in-context example
  - LLM is asked for STRICT JSON; we tolerate ```json...``` fences and
    leading prose by extracting the first {...} that parses
  - one retry with errors-as-feedback when validate_plan rejects the plan
  - failure mode: return None — caller falls back to single-hop
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set

from .plan_schema import HopSpec, Plan, validate_plan

logger = logging.getLogger(__name__)


_PLAN_SCHEMA_DOC = """\
{
  "plan_id": "<auto>",
  "intent": "<copy user intent verbatim>",
  "rationale": "<one sentence why this decomposition>",
  "estimated_cost_usd": 0.05,
  "final_synthesis_prompt": "<optional override for final synth>",
  "hops": [
    {
      "step_id": "s1",
      "description": "<what this hop achieves>",
      "capability": "<name from registry, OR null if execution_target set>",
      "execution_target": "<optional Phase-4 target string, OR null>",
      "arg_kwarg": "<kwarg-name to wrap arg under, OR null>",
      "arg_template": "<value or '{{state.X}}' template; inside a 'repeat:' hop you may use '{{item}}', '{{loop.index}}' (1-based), '{{loop.index0}}' (0-based)>",
      "depends_on": [],
      "output_var": "<unique key under which result lands in state>",
      "on_fail": "abort | continue | replan",
      "timeout_s": 60,
      "retries": 1,
      "repeat": null
    }
  ]
}

ITERATION (very important — DO NOT generate N near-duplicate hops if you
mean "do X N times"):

If the intent says "add 10 ideas" / "create 5 events" / "send 3 emails":
DO NOT emit 10 separate hops with copy-pasted arg_templates. Instead use
the `repeat:` field on a SINGLE hop:

  {
    "step_id": "s2",
    "description": "add 10 example ideas about Python",
    "capability": "idea_add",
    "arg_kwarg": "title",
    "arg_template": "Idea {{loop.index}}: {{item}}",
    "depends_on": ["s1"],
    "output_var": "ideas",
    "on_fail": "continue",
    "repeat": {
      "items": [
        "list comprehensions for transforming data",
        "decorators for cross-cutting concerns",
        "async/await for IO concurrency",
        "dataclasses for typed records",
        "context managers for resource cleanup",
        "f-strings for readable formatting",
        "generators for streaming pipelines",
        "type hints for safer APIs",
        "pathlib for file operations",
        "argparse for CLI tools"
      ]
    }
  }

`repeat.items` MUST be a list of concrete, varied strings — one per
iteration. The executor expands this hop into N child-hops at runtime,
each rendering `{{item}}` to the corresponding entry. Use `repeat.items_from`
(e.g. "state.idea_titles") only when items come from a previous hop's
output. You can also use `repeat.count: <N>` if you genuinely need
numbered placeholders without specific content (rare).
"""


_TARGET_KINDS_DOC = """\
- `direct:<module.path>:<function>` — call a python function in-process (e.g. bubble lifecycle)
- `http:<METHOD>:<url>` — generic HTTP webhook
- `n8n:<workflow_id>` — trigger n8n workflow (if available)
- `coding-engine:<endpoint>` — Daves coding-engine
- `openfang:<agent_name>` — single-agent dispatch (Sonnet for high-confidence)
- `brain:<METHOD>:<route>` — call back into Brain's own API
- `mcp:<server>:<tool>` — MCP tool (advanced, often gated)
"""


_EXAMPLE_PLAN = """\
RULES:

1. ECHO THE USER INTENT EXACTLY in the `intent` field. Do not change it.
2. Use ONE of the registered capabilities (listed below) with `execution_target: null`.
3. Single-action intents = ONE hop.
4. Multi-step intents = multiple hops with `depends_on`.
5. Repeat-blocks (`repeat: {items: [...]}`) for "create N items" intents.
6. Format capabilities (`idea_format_*`) are TERMINAL — do not append bubble_evaluate.
7. NEVER fabricate execution_target URLs.

REGISTERED CAPABILITIES (exact names):
  Bubble: bubble_create, bubble_list, bubble_find, bubble_update, bubble_delete,
          bubble_delete_all, bubble_enter, bubble_exit, bubble_stats, bubble_score,
          bubble_evaluate, bubble_promote, bubble_generate_embeddings.
  Idea:   idea_add (alias idea_create), idea_create_batch, idea_list, idea_count,
          idea_find, idea_update, idea_delete, idea_explain, idea_classify, idea_expand,
          idea_connect, idea_disconnect, idea_link_to_root, idea_move, idea_auto_link,
          idea_analyze_links, idea_to_project.
  Format: idea_format_table, idea_format_note, idea_format_action_list,
          idea_format_pros_cons, idea_format_hierarchy, idea_format_specs,
          idea_format_kanban, idea_format_mindmap, idea_format_swot,
          idea_format_user_story, idea_format_flowchart, idea_convert_format,
          idea_format_revert, idea_format_list, idea_format_get.
  Exec:   coding_task (write/edit/run real code, git, github, vercel),
          desktop_skill (excel/word/hr/UI automation),
          browser_automation (navigate/scrape/fill web pages).
          These have a built-in execution_target — ALWAYS set
          execution_target:null for them; the router resolves the agent.
          arg_kwarg for all three is "task", arg_template = the user's
          full request verbatim (the executing agent reads natural language).

INTENT-TO-CAPABILITY HINTS:
  "schreib/erstelle <code/script/funktion>" / "fix bug in X.py"  → coding_task,  arg_kwarg=task,  arg_template=<full intent>
  "öffne excel/word, fülle zelle, hr checklist"                  → desktop_skill, arg_kwarg=task,  arg_template=<full intent>
  "navigiere zu URL, scrape, fülle web-formular"                 → browser_automation, arg_kwarg=task, arg_template=<full intent>
  "verlasse die bubble" / "exit bubble"               → bubble_exit (no arg)
  "geh in die bubble X" / "enter bubble X"            → bubble_enter, arg_kwarg=bubble_name, arg_template=X
  "wie reif ist bubble X" / "score bubble X"          → bubble_score,  arg_kwarg=bubble_name, arg_template=X
  "stats für bubble X"                                 → bubble_stats,  arg_kwarg=bubble_name, arg_template=X
  "lege bubble X an" / "create bubble X"              → bubble_create, arg_kwarg=title,        arg_template=X
  "lösche bubble X"                                    → bubble_delete, arg_kwarg=bubble_name, arg_template=X
  "lösche alle bubbles"                                → bubble_delete_all, no arg
  "benenne bubble X um nach Y"                         → bubble_update, arg_kwarg=title,        arg_template=Y
  "fuege idee X hinzu" / "add idea X"                  → idea_add,      arg_kwarg=title,        arg_template=X
  "such/finde/wo ist die idee X" / "find idea X"      → idea_find,     arg_kwarg=query,        arg_template=X
       (NICHT bubble_evaluate! "such die idee" = idea_find suchen,
        NICHT eine Bubble auf Projekt-Reife bewerten.)
  "bewerte/evaluate bubble X" / "ist X reif/ready"    → bubble_evaluate, arg_kwarg=bubble_name, arg_template=X
       (NUR bei expliziter Bewertungs-/Reife-/go-no-go-Absicht, NICHT beim Suchen.)
  "format idee X als Y"                                → idea_format_<Y>, arg_kwarg=idea_name,  arg_template=X

DECISION TREE (apply IN ORDER, take FIRST match):

  Step 1 — Does the intent contain MULTIPLE distinct verbs (e.g.
           "create AND add" / "lege AN UND fuege HINZU")?
            → YES: multi-hop plan (one hop per verb).
            → NO:  single-hop plan (one hop only). STOP HERE.

  Step 2 — Does the intent ask for "N items"
           (e.g. "3 ideas", "drei ideen", "5 entries")?
            → YES: ONE hop with repeat-block.
            → NO:  ONE plain hop, no repeat.

  Most user intents fall into Step 1=NO + Step 2=NO → ONE plain hop.

SHAPE REFERENCE (copy structure only, NEVER strings):

Single-hop (most common):
{
  "plan_id": "auto",
  "intent": "<echo user intent>",
  "rationale": "<one short sentence>",
  "estimated_cost_usd": 0.01,
  "final_synthesis_prompt": "",
  "hops": [
    {"step_id":"s1","description":"<short>","capability":"<from list>","execution_target":null,"arg_kwarg":"<from hints>","arg_template":"<extracted from intent>","depends_on":[],"output_var":"out","on_fail":"abort","timeout_s":30,"retries":1,"repeat":null}
  ]
}

Multi-hop (only when intent has multiple verbs):
{
  "plan_id": "auto",
  "intent": "<echo user intent>",
  "rationale": "Two hops: <action 1>, then <action 2>.",
  "estimated_cost_usd": 0.05,
  "final_synthesis_prompt": "",
  "hops": [
    {"step_id":"s1","description":"<verb 1>","capability":"<cap1>","execution_target":null,"arg_kwarg":"<key>","arg_template":"<value>","depends_on":[],"output_var":"r1","on_fail":"abort","timeout_s":30,"retries":1,"repeat":null},
    {"step_id":"s2","description":"<verb 2>","capability":"<cap2>","execution_target":null,"arg_kwarg":"<key>","arg_template":"<value>","depends_on":["s1"],"output_var":"r2","on_fail":"abort","timeout_s":30,"retries":1,"repeat":null}
  ]
}

Repeat (only when intent says "N items"):
   …a single hop with `repeat: {"items": ["a","b","c"]}` and arg_template "Idea {{loop.index}}: {{item}}".

REMEMBER:
- `intent` field = the user's exact text. Do NOT rephrase or substitute.
- `arg_template` = extracted from THE USER'S intent (a name, a title, a topic). Never use shape-reference placeholders like FOO/bar.
- Default to single-hop when in doubt.
"""


class PlannerLLM:
    def __init__(
        self,
        dispatcher: Any,
        capability_router: Any = None,
        *,
        model: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.1,
        fallback_model: Optional[str] = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.cap_router = capability_router
        # Primary model: env-overridable so we can swap to local Ollama or
        # OpenAI without code changes. Default Groq Llama-70b for prod.
        self.model = model or os.environ.get(
            "PLANNER_MODEL", "groq::llama-3.3-70b-versatile",
        )
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Fallback model used when primary returns 429/5xx — smaller/cheaper
        # so we don't deadlock the user on a hot Groq quota.
        self.fallback_model = fallback_model or os.environ.get(
            "PLANNER_FALLBACK_MODEL", "anthropic/claude-haiku-4.5",
        )
        self.stats: Dict[str, Any] = {
            "calls": 0,
            "successes": 0,
            "parse_errors": 0,
            "validation_errors": 0,
            "retries": 0,
            "fallback_failures": 0,
            "fallback_used": 0,
            "last_error": None,
            "last_latency_ms": 0.0,
            "total_latency_ms": 0.0,
        }

    # ── Public ──────────────────────────────────────────────────────────

    def plan(self, intent: str, *, context: Optional[Dict[str, Any]] = None) -> Optional[Plan]:
        """Returns a validated Plan, or None on irrecoverable failure."""
        if not intent or not intent.strip():
            self.stats["last_error"] = "empty intent"
            return None
        self.stats["calls"] += 1
        t0 = time.time()
        prompt = self._build_prompt(intent, context, retry_errors=None)

        # Primary attempt — configured model
        plan = self._call_and_parse(prompt, model=self.model)
        if plan is not None:
            errs = self._validate(plan)
            if not errs:
                self.stats["successes"] += 1
                self._record_latency(t0)
                return plan
            # Retry once with errors as feedback (same model)
            self.stats["validation_errors"] += 1
            self.stats["retries"] += 1
            retry_prompt = self._build_prompt(intent, context, retry_errors=errs)
            plan2 = self._call_and_parse(retry_prompt, model=self.model)
            if plan2 is not None and not self._validate(plan2):
                self.stats["successes"] += 1
                self._record_latency(t0)
                return plan2

        # Fallback model attempt — usually triggered when primary 429s or
        # is otherwise rate-limited. Different model so different quota.
        if self.fallback_model and self.fallback_model != self.model:
            logger.info(
                f"[planner] primary {self.model!r} failed, trying fallback "
                f"{self.fallback_model!r} ({self.stats.get('last_error')!r})"
            )
            plan_fb = self._call_and_parse(prompt, model=self.fallback_model)
            if plan_fb is not None and not self._validate(plan_fb):
                self.stats["successes"] += 1
                self.stats["fallback_used"] += 1
                self._record_latency(t0)
                return plan_fb

        # Last-resort: local Ollama. Quota-free, slower but always there.
        # Triggered when both primary AND fallback failed (typically both
        # cloud LLMs hit rate-limits or 402 payment issues simultaneously).
        ollama_model = os.environ.get("PLANNER_OLLAMA_FALLBACK", "llama3.1:latest")
        if ollama_model and ollama_model != self.model and ollama_model != self.fallback_model:
            logger.info(
                f"[planner] both cloud models failed; trying local Ollama "
                f"{ollama_model!r} as last resort"
            )
            plan_ol = self._call_and_parse(prompt, model=ollama_model)
            if plan_ol is not None and not self._validate(plan_ol):
                self.stats["successes"] += 1
                self.stats["fallback_used"] += 1
                self.stats["ollama_fallback_used"] = self.stats.get("ollama_fallback_used", 0) + 1
                self._record_latency(t0)
                return plan_ol

        self.stats["fallback_failures"] += 1
        self._record_latency(t0)
        return None

    # ─── Phase 11.T.3 — Async sibling ─────────────────────────────────────
    # aplan() lets endpoints await planning without burning a thread.
    # Same retry/fallback chain as plan(), just dispatcher.adispatch().

    async def aplan(self, intent: str, *, context: Optional[Dict[str, Any]] = None) -> Optional[Plan]:
        """Async version of plan() — uses adispatch()."""
        if not intent or not intent.strip():
            self.stats["last_error"] = "empty intent"
            return None
        self.stats["calls"] += 1
        t0 = time.time()
        prompt = self._build_prompt(intent, context, retry_errors=None)

        plan = await self._acall_and_parse(prompt, model=self.model)
        if plan is not None:
            errs = self._validate(plan)
            if not errs:
                self.stats["successes"] += 1
                self._record_latency(t0)
                return plan
            self.stats["validation_errors"] += 1
            self.stats["retries"] += 1
            retry_prompt = self._build_prompt(intent, context, retry_errors=errs)
            plan2 = await self._acall_and_parse(retry_prompt, model=self.model)
            if plan2 is not None and not self._validate(plan2):
                self.stats["successes"] += 1
                self._record_latency(t0)
                return plan2

        if self.fallback_model and self.fallback_model != self.model:
            logger.info(
                f"[planner async] primary {self.model!r} failed, trying fallback "
                f"{self.fallback_model!r} ({self.stats.get('last_error')!r})"
            )
            plan_fb = await self._acall_and_parse(prompt, model=self.fallback_model)
            if plan_fb is not None and not self._validate(plan_fb):
                self.stats["successes"] += 1
                self.stats["fallback_used"] += 1
                self._record_latency(t0)
                return plan_fb

        ollama_model = os.environ.get("PLANNER_OLLAMA_FALLBACK", "llama3.1:latest")
        if ollama_model and ollama_model != self.model and ollama_model != self.fallback_model:
            logger.info(
                f"[planner async] both cloud models failed; trying local Ollama "
                f"{ollama_model!r} as last resort"
            )
            plan_ol = await self._acall_and_parse(prompt, model=ollama_model)
            if plan_ol is not None and not self._validate(plan_ol):
                self.stats["successes"] += 1
                self.stats["fallback_used"] += 1
                self.stats["ollama_fallback_used"] = self.stats.get("ollama_fallback_used", 0) + 1
                self._record_latency(t0)
                return plan_ol

        self.stats["fallback_failures"] += 1
        self._record_latency(t0)
        return None

    async def _acall_and_parse(self, prompt: Dict[str, str], *, model: Optional[str] = None) -> Optional[Plan]:
        """Async _call_and_parse — uses dispatcher.adispatch() if available,
        otherwise falls back to running sync dispatch in a thread."""
        use_model = model or self.model
        lower = use_model.lower()
        if lower.startswith("ollama/") or lower.startswith("llama3") or lower.startswith("phi3") or lower.startswith("qwen2"):
            tool_name = "ollama_subagent"
        elif lower.startswith("openai/") or lower.startswith("gpt-") or lower.startswith("o1") or lower.startswith("o3"):
            tool_name = "openai_subagent"
        elif lower.startswith("anthropic/") or lower.startswith("claude") or "haiku" in lower or "sonnet" in lower or "opus" in lower:
            tool_name = "claude_subagent"
        else:
            tool_name = "groq_subagent"

        adispatch = getattr(self.dispatcher, "adispatch", None)
        try:
            if adispatch is not None:
                resp = await adispatch(
                    tool_name,
                    prompt=prompt["user"],
                    system=prompt["system"],
                    model=use_model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            else:
                import asyncio as _asyncio
                resp = await _asyncio.to_thread(
                    self.dispatcher.dispatch, tool_name,
                    prompt=prompt["user"],
                    system=prompt["system"],
                    model=use_model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
        except Exception as e:
            self.stats["last_error"] = f"dispatch ({tool_name}): {type(e).__name__}: {e}"
            return None
        if not resp.get("ok"):
            self.stats["last_error"] = f"{tool_name} error: {resp.get('error')}"
            return None
        text = (resp.get("text") or "").strip()
        if not text:
            self.stats["last_error"] = "empty response"
            return None
        plan_dict = self._extract_json(text)
        if plan_dict is None:
            self.stats["parse_errors"] += 1
            self.stats["last_error"] = "could not parse JSON from response"
            return None
        try:
            if not plan_dict.get("plan_id") or plan_dict.get("plan_id") in ("auto", "<auto>"):
                plan_dict["plan_id"] = Plan.make_id()
            return Plan.from_dict(plan_dict)
        except Exception as e:
            self.stats["parse_errors"] += 1
            self.stats["last_error"] = f"plan dataclass build: {e}"
            return None

    def stats_dict(self) -> Dict[str, Any]:
        s = dict(self.stats)
        if s["calls"] > 0:
            s["avg_latency_ms"] = round(s["total_latency_ms"] / s["calls"], 1)
        return s

    # ── Internals ───────────────────────────────────────────────────────

    def _build_prompt(
        self,
        intent: str,
        context: Optional[Dict[str, Any]],
        retry_errors: Optional[List[str]],
    ) -> Dict[str, str]:
        caps_block = self._render_capabilities()
        retry_block = ""
        if retry_errors:
            retry_block = (
                "\n\nYour PREVIOUS plan failed validation with these errors:\n"
                + "\n".join(f"  - {e}" for e in retry_errors[:10])
                + "\n\nProduce a CORRECTED plan that fixes all listed errors."
            )

        # Ground the plan in caller-supplied context (e.g. the bubble the
        # user is currently inside, its db_id, existing node titles). This
        # was previously accepted but silently discarded — a context-blind
        # planner can't resolve "evaluate THIS bubble" / "add to it" and is
        # forced to invent generic targets. We render only the few keys the
        # planner can act on, capped, so the prompt stays small.
        context_block = self._render_context(context)

        system = (
            "You decompose user intents into 2-5 step DAGs that Brain "
            "executes via its capability router and target executors. "
            "Output STRICT JSON ONLY — no markdown, no commentary. The "
            "JSON must validate against the schema shown."
        )
        user = (
            f"USER INTENT:\n{intent.strip()}\n\n"
            f"{context_block}"
            f"AVAILABLE CAPABILITIES:\n{caps_block}\n\n"
            f"AVAILABLE TARGET KINDS:\n{_TARGET_KINDS_DOC}\n\n"
            f"PLAN JSON SCHEMA (use exactly these fields):\n{_PLAN_SCHEMA_DOC}\n\n"
            f"{_EXAMPLE_PLAN}"
            f"{retry_block}\n\n"
            "Now produce the plan for the USER INTENT above. JSON only."
        )
        return {"system": system, "user": user}

    @staticmethod
    def _render_context(context: Optional[Dict[str, Any]]) -> str:
        """Render caller context as a compact, actionable prompt block.

        Returns "" when there is nothing useful, so the prompt is unchanged
        for context-free callers (the common path). Only whitelisted keys
        are surfaced and values are truncated — we never dump arbitrary
        state into the planner prompt.
        """
        if not context or not isinstance(context, dict):
            return ""
        lines: List[str] = []

        # Current bubble the user is inside — lets the planner target
        # "this bubble" by name/id instead of inventing one.
        cur = context.get("current_bubble") or context.get("bubble")
        if isinstance(cur, dict):
            title = str(cur.get("title") or cur.get("name") or "").strip()
            bid = str(cur.get("db_id") or cur.get("id") or "").strip()
            if title or bid:
                tag = f"{title!r}" if title else ""
                if bid:
                    tag += f" (db_id={bid})"
                lines.append(f"- The user is currently INSIDE bubble {tag}.")
                lines.append(
                    "  For intents like 'evaluate it' / 'add to this bubble' "
                    "use THIS bubble — do NOT create a new one."
                )

        # Existing node/idea titles in scope — prevents duplicate creation
        # and lets the planner reference real items.
        nodes = context.get("node_titles") or context.get("existing_titles")
        if isinstance(nodes, (list, tuple)) and nodes:
            sample = [str(n)[:60] for n in list(nodes)[:15] if n]
            if sample:
                more = "" if len(nodes) <= 15 else f" (+{len(nodes) - 15} more)"
                lines.append(
                    "- Existing items already in scope (do NOT recreate): "
                    + "; ".join(sample) + more
                )

        # Free-form hint the caller wants the planner to honour.
        hint = context.get("hint") or context.get("note")
        if isinstance(hint, str) and hint.strip():
            lines.append(f"- Caller hint: {hint.strip()[:200]}")

        if not lines:
            return ""
        return "EXECUTION CONTEXT (ground the plan in this — do not ignore):\n" + "\n".join(lines) + "\n\n"

    def _render_capabilities(self) -> str:
        if self.cap_router is None:
            return "(none — use execution_target on every hop)"
        try:
            caps = self.cap_router.list_capabilities()
        except Exception:
            caps = []
        if not caps:
            return "(none)"
        lines = []
        for c in caps:
            name = c.get("capability")
            desc = (c.get("description") or "")[:120]
            kind = c.get("execution_target_kind") or "broadcast"
            lines.append(f"  - {name}  (target_kind={kind})  {desc}")
        return "\n".join(lines)

    def _call_and_parse(self, prompt: Dict[str, str], *, model: Optional[str] = None) -> Optional[Plan]:
        use_model = model or self.model
        # Route to the right subagent kind based on model prefix.
        lower = use_model.lower()
        if lower.startswith("ollama/") or lower.startswith("llama3") or lower.startswith("phi3") or lower.startswith("qwen2"):
            tool_name = "ollama_subagent"
        elif lower.startswith("openai/") or lower.startswith("gpt-") or lower.startswith("o1") or lower.startswith("o3"):
            tool_name = "openai_subagent"
        elif lower.startswith("anthropic/") or lower.startswith("claude") or "haiku" in lower or "sonnet" in lower or "opus" in lower:
            tool_name = "claude_subagent"
        else:
            tool_name = "groq_subagent"
        try:
            resp = self.dispatcher.dispatch(
                tool_name,
                prompt=prompt["user"],
                system=prompt["system"],
                model=use_model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as e:
            self.stats["last_error"] = f"dispatch ({tool_name}): {type(e).__name__}: {e}"
            return None
        if not resp.get("ok"):
            self.stats["last_error"] = f"{tool_name} error: {resp.get('error')}"
            return None
        text = (resp.get("text") or "").strip()
        if not text:
            self.stats["last_error"] = "empty groq response"
            return None
        plan_dict = self._extract_json(text)
        if plan_dict is None:
            self.stats["parse_errors"] += 1
            self.stats["last_error"] = "could not parse JSON from groq response"
            return None
        try:
            if not plan_dict.get("plan_id") or plan_dict.get("plan_id") in ("auto", "<auto>"):
                plan_dict["plan_id"] = Plan.make_id()
            return Plan.from_dict(plan_dict)
        except Exception as e:
            self.stats["parse_errors"] += 1
            self.stats["last_error"] = f"plan dataclass build: {e}"
            return None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Tolerate ```json...``` fences and leading/trailing prose."""
        # strip markdown fences
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            candidate = m.group(1)
        else:
            # Find first { and try to parse from there
            i = text.find("{")
            if i < 0:
                return None
            candidate = text[i:]
        # Try direct parse, then progressively trim from the right until
        # JSON is balanced.
        for end in range(len(candidate), 0, -1):
            if candidate[end - 1] != "}":
                continue
            try:
                return json.loads(candidate[:end])
            except json.JSONDecodeError:
                continue
        return None

    def _validate(self, plan: Plan) -> List[str]:
        known_caps: Optional[Set[str]] = None
        if self.cap_router is not None:
            try:
                known_caps = {c["capability"] for c in self.cap_router.list_capabilities()}
            except Exception:
                known_caps = None
        return validate_plan(
            plan,
            known_capabilities=known_caps,
            known_target_kinds={"direct", "http", "n8n", "coding-engine", "openfang", "brain", "mcp"},
            max_hops=int_env_or("PLAN_MAX_HOPS", 5),
        )

    def _record_latency(self, t0: float) -> None:
        ms = (time.time() - t0) * 1000
        self.stats["last_latency_ms"] = round(ms, 1)
        self.stats["total_latency_ms"] += ms


def int_env_or(name: str, default: int) -> int:
    import os
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

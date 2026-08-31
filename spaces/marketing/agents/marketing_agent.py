"""Marketing Backend Agent.

Listens on the `events:tasks:marketing` Redis stream and dispatches
`marketing.*` event types to tools in `spaces.marketing.tools.marketing_tools`.

Follows the BaseBackendAgent pattern documented in
`vibemind-os/voice/CLAUDE.md` -> "Adding a Backend Agent".

Phase-1 event scope (read-only + lockout-safe writes; no real send):

  marketing.list_audiences
  marketing.list_templates
  marketing.list_campaigns
  marketing.inbox
  marketing.audience_count   {audience_id}
  marketing.stats
  marketing.create_audience  {name, filter_dsl}
  marketing.create_template  {name, subject, body_text, body_html?, channel?}
  marketing.send_campaign    {campaign_id, dry_run=true}   -- dry-run only

Two ways to drive this agent:

  1. STANDALONE RUNNER (Phase 1, default): `spaces.marketing.agents.runner`
     consumes the Redis stream directly. No voice-swarm import required.
     Launched from `Vibemind.debug.ps1` PHASE 4.5 alongside Worker A/B.

  2. VOICE-SWARM INTEGRATED (Phase 2+): when voice/swarm registers this
     agent via its own AgentPool. The shim BaseBackendAgent below makes
     this file importable WITHOUT the swarm runtime so the runner can
     use it standalone. The shim is overridden by the real
     `swarm.backend_agents.base_agent.BaseBackendAgent` whenever that
     module is on sys.path.

CUT-OVER RULE (very important):
  The standalone runner uses Redis consumer-group name
  `MARKETING_CONSUMER_GROUP` (defined below). When voice-swarm wiring
  lands in Phase 2, it MUST either:
    (a) reuse the same consumer-group name (only one consumer set
        delivers any given event -> events processed exactly once), or
    (b) explicitly disable the standalone runner via
        `vibemind.config.json` modules.marketing.runner_enabled=false
        before bringing the swarm consumer online.
  Skipping this step = double-execute (same event handled by both
  consumer groups). Document the cut-over in the PR that lands the
  swarm integration.

Path memo: spaces/marketing/ lives at the REPO ROOT, NOT in the
vibemind-os submodule. The submodule's `spaces/` symlink does NOT
reach this code; the standalone runner is the only Phase-1 way to
serve marketing.* events.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

# Redis consumer-group name shared by standalone runner + future swarm wiring.
# See CUT-OVER RULE in the module docstring.
MARKETING_CONSUMER_GROUP = "marketing-runner"


try:
    # Available when running inside the voice/swarm Python process
    from swarm.backend_agents.base_agent import BaseBackendAgent  # type: ignore
    HAS_SWARM = True
except ImportError:  # pragma: no cover - stand-alone usage
    HAS_SWARM = False

    class BaseBackendAgent:  # type: ignore
        """Minimal shim so the file is importable without the swarm runtime.

        Replicates the methods the standalone runner needs:
          - __init__ (private state)
          - _normalize_params (PARAM_MAPPING-aware param rewriter,
            copied verbatim from
            vibemind-os/voice/python/swarm/backend_agents/base_agent.py
            so behaviour stays in lockstep)
        The full lifecycle (Redis stream consumption, status publish)
        is implemented in spaces.marketing.agents.runner, which uses
        the shim's helpers via the agent instance.
        """

        PARAM_MAPPING: Dict[str, Dict[str, str]] = {}

        def __init__(self):
            self._tools: Dict[str, Callable] = {}

        def _normalize_params(self, event_type: str,
                              params: Dict[str, Any]) -> Dict[str, Any]:
            """Rewrite classifier-output param names to tool-expected ones.

            Behaviour-mirror of swarm.backend_agents.base_agent
            BaseBackendAgent._normalize_params (lines 96-137 in the
            submodule). When the real BaseBackendAgent is on the path,
            this shim is not used.
            """
            mapping = self.PARAM_MAPPING.get(event_type, {})
            if not mapping and "_inject" not in (params or {}):
                return params

            normalized: Dict[str, Any] = {}
            inject: Dict[str, Any] = {}
            for key, value in (params or {}).items():
                if key == "_inject" and isinstance(value, dict):
                    inject = value
                    continue
                new_key = mapping.get(key, key)
                normalized[new_key] = value
            for k, v in inject.items():
                normalized.setdefault(k, v)
            return normalized


logger = logging.getLogger(__name__)


class MarketingBackendAgent(BaseBackendAgent):
    """Backend agent for the Marketing-Ops Space."""

    EVENT_TO_TOOL: Dict[str, str] = {
        "marketing.list_audiences":  "list_audiences",
        "marketing.list_templates":  "list_templates",
        "marketing.list_campaigns":  "list_campaigns",
        "marketing.inbox":           "get_inbox_unread",
        "marketing.audience_count":  "audience_count",
        "marketing.stats":           "get_stats",
        "marketing.create_audience": "create_audience",
        "marketing.create_template": "create_template",
        "marketing.send_campaign":   "send_campaign",
        # Hand-bridge: OpenFang Hands publish proposals via event_publish.
        # The runner consumes them here and writes to audience_proposals
        # staging (NEVER directly to audiences/emails -- approval-gated).
        "marketing.audience_proposal": "propose_audience",
        "marketing.list_proposals":    "list_proposals",
        "marketing.get_proposal":      "get_proposal",
        # Hand-bridge subroutine: marketing -> OpenFang Hand task.
        "marketing.request_hand":      "request_hand_research",
    }

    PARAM_MAPPING: Dict[str, Dict[str, str]] = {
        "marketing.list_audiences": {
            "name": "name_contains",
            "filter": "name_contains",
            "suche": "name_contains",
        },
        "marketing.list_templates": {
            "name": "name_contains",
            "suche": "name_contains",
        },
        "marketing.list_campaigns": {
            "status": "status",
            "zustand": "status",
        },
        "marketing.audience_count": {
            "id": "audience_id",
            "audience": "audience_id",
        },
        "marketing.create_audience": {
            "title": "name",
            "filter": "filter_dsl",
            "spec": "filter_dsl",
            "definition": "filter_dsl",
        },
        "marketing.create_template": {
            "title": "name",
            "betreff": "subject",
            "body": "body_text",
            "text": "body_text",
            "html": "body_html",
            "kanal": "channel",
        },
        "marketing.send_campaign": {
            "id": "campaign_id",
            "campaign": "campaign_id",
            "preview": "dry_run",
        },
        # Hand-bridge: aliases for the keys a Hand prompt naturally emits.
        # Hand outputs typically use English natural keys like "icp_filter",
        # "audience", "candidates" -- normalise to propose_audience kwargs.
        "marketing.audience_proposal": {
            "title": "name",
            "audience": "name",
            "icp": "filter_dsl",
            "filter": "filter_dsl",
            "icp_filter": "filter_dsl",
            "candidates": "candidate_emails",
            "emails": "candidate_emails",
            "leads": "candidate_emails",
            "reasoning": "rationale",
            "notes": "hand_notes",
            "hand_id": "source",
            "by": "source",
        },
        "marketing.list_proposals": {
            "filter": "status",
            "zustand": "status",
        },
        "marketing.get_proposal": {
            "id": "proposal_id",
        },
        "marketing.request_hand": {
            "id": "hand_id",
            "hand": "hand_id",
            "kind": "hand_id",
            "country": "geo",
            "region": "geo",
            "branche": "industry",
            "rolle": "role",
            "anzahl": "n",
            "count": "n",
        },
    }

    @property
    def name(self) -> str:  # type: ignore[override]
        return "MarketingAgent"

    @property
    def stream(self) -> str:  # type: ignore[override]
        return "events:tasks:marketing"

    def _load_tools(self) -> Dict[str, Callable]:
        tools: Dict[str, Callable] = {}
        try:
            from spaces.marketing.tools.marketing_tools import (
                list_audiences, list_templates, list_campaigns,
                get_inbox_unread, audience_count, get_stats,
                create_audience, create_template, send_campaign,
                # Hand-bridge (Phase-2 staging)
                propose_audience, list_proposals, get_proposal,
            )
            tools.update({
                "list_audiences":   list_audiences,
                "list_templates":   list_templates,
                "list_campaigns":   list_campaigns,
                "get_inbox_unread": get_inbox_unread,
                "audience_count":   audience_count,
                "get_stats":        get_stats,
                "create_audience":  create_audience,
                "create_template":  create_template,
                "send_campaign":    send_campaign,
                # Hand-bridge -- staging only, NEVER touches send-pipeline.
                "propose_audience": propose_audience,
                "list_proposals":   list_proposals,
                "get_proposal":     get_proposal,
            })
            # Track C: hand_bridge.request_hand_research is a separate
            # module that only loads urllib (no smtp / no fastapi).
            from spaces.marketing.tools.hand_bridge import request_hand_research
            tools["request_hand_research"] = request_hand_research
            logger.info("%s: loaded %d tools", self.name, len(tools))
        except ImportError as e:
            logger.warning("%s: could not load tools: %s", self.name, e)
        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        return self.EVENT_TO_TOOL.get(event_type)


_marketing_agent: Optional[MarketingBackendAgent] = None


def get_marketing_agent() -> MarketingBackendAgent:
    global _marketing_agent
    if _marketing_agent is None:
        _marketing_agent = MarketingBackendAgent()
    return _marketing_agent


__all__ = ["MarketingBackendAgent", "get_marketing_agent"]

"""CompanyForge — self-orchestrating company builder.

OrgBoard plans which teams a company needs, GapAnalyzer compares against
the Registry, and CrossTeamLinker connects validated teams via Minibook.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from .constants import OUTPUT_DIR
from .llm import call_gpt4o_json, call_gpt4o
from .api_client import (
    api_get, api_post, register_agent_in_registry,
    ensure_community_project, COMMUNITY_GROUPS,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CompanyProfile:
    name: str
    industry: str
    size: str
    goals: list[str]
    departments: list[str]
    existing_tools: list[str]
    constraints: str
    raw_text: str  # original markdown


@dataclass
class TeamSpec:
    name: str               # human-readable, e.g. "Outreach Team"
    team_key: str           # slug for registry, e.g. "outreach"
    task_description: str   # full prompt for SwarmPipeline
    dependencies: list[str] = field(default_factory=list)  # team_keys that must exist first
    cascade_from: str | None = None  # output dir to extend (if extending existing team)


# ---------------------------------------------------------------------------
# Profile parsing
# ---------------------------------------------------------------------------

PROFILE_PARSE_PROMPT = """\
You are a structured data extractor. Given a company profile document,
extract the following fields as JSON:

{
  "name": "company name",
  "industry": "industry/sector",
  "size": "number of employees or team size description",
  "goals": ["goal1", "goal2"],
  "departments": ["dept1", "dept2"],
  "existing_tools": ["tool1", "tool2"],
  "constraints": "any budget/time/resource constraints"
}

Be precise. If a field is not mentioned, use an empty string or empty list."""


async def parse_company_profile(path: str) -> CompanyProfile:
    """Read a markdown company profile and LLM-extract structured data."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    data = await call_gpt4o_json(PROFILE_PARSE_PROMPT, raw, max_tokens=1500)
    return CompanyProfile(
        name=data.get("name", "Unknown Company"),
        industry=data.get("industry", ""),
        size=data.get("size", ""),
        goals=data.get("goals", []),
        departments=data.get("departments", []),
        existing_tools=data.get("existing_tools", []),
        constraints=data.get("constraints", ""),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# OrgBoard — strategic team planning
# ---------------------------------------------------------------------------

ORGBOARD_PLAN_PROMPT = """\
You are OrgBoard, the strategic planning agent for an autonomous company builder.
Given a company profile, decide which agent teams need to be built.

Return JSON:
{
  "teams": [
    {
      "name": "Human-readable team name",
      "team_key": "snake_case_slug",
      "task_description": "Detailed description of what this agent team should do. Include specifics about tools, workflows, and integration points.",
      "dependencies": ["team_key of teams that must be built first"]
    }
  ]
}

Rules:
- Order teams by priority (foundation teams first).
- team_key must be unique, lowercase, underscore-separated.
- task_description should be detailed enough for an AI system to build the team autonomously.
- Include the company context (industry, tools, goals) in each task_description.
- Keep total teams realistic (3-15 depending on company size).
- Dependencies reference other team_keys from this same list.
- Teams with no dependencies are foundations and should come first."""


ORGBOARD_GAP_PROMPT = """\
You are OrgBoard analyzing which teams still need to be built.

Company plan has these teams: {planned}

Already built and validated in the registry: {existing}

Return JSON:
{
  "gaps": ["team_key1", "team_key2"],
  "next": "team_key to build next (or null if complete)",
  "reason": "why this team is next",
  "complete": false
}

Rules:
- A team is "existing" only if it appears in the validated registry list.
- Respect dependency order: don't suggest a team whose dependencies aren't built yet.
- If all teams are built, set complete=true and next=null."""


class OrgBoard:
    """Strategic decision agent — plans and prioritizes team creation."""

    def __init__(self, profile: CompanyProfile):
        self.profile = profile
        self._team_specs: list[TeamSpec] | None = None

    async def plan_teams(self) -> list[TeamSpec]:
        """LLM call: determine which teams the company needs."""
        user_content = (
            f"Company: {self.profile.name}\n"
            f"Industry: {self.profile.industry}\n"
            f"Size: {self.profile.size}\n"
            f"Goals: {', '.join(self.profile.goals)}\n"
            f"Departments: {', '.join(self.profile.departments)}\n"
            f"Existing Tools: {', '.join(self.profile.existing_tools)}\n"
            f"Constraints: {self.profile.constraints}\n\n"
            f"Full profile:\n{self.profile.raw_text[:3000]}"
        )
        data = await call_gpt4o_json(ORGBOARD_PLAN_PROMPT, user_content, max_tokens=3000)
        teams = []
        for t in data.get("teams", []):
            teams.append(TeamSpec(
                name=t.get("name", ""),
                team_key=t.get("team_key", ""),
                task_description=t.get("task_description", ""),
                dependencies=t.get("dependencies", []),
            ))
        self._team_specs = teams
        return teams

    async def analyze_gaps(
        self, registry_entries: list[dict]
    ) -> tuple[list[str], TeamSpec | None, bool]:
        """Compare planned teams against registry. Returns (gaps, next_spec, is_complete)."""
        if not self._team_specs:
            await self.plan_teams()

        planned_keys = [t.team_key for t in self._team_specs]
        existing_keys = [
            e["team_key"] for e in registry_entries
            if e.get("status") == "validated"
        ]

        # Ask LLM for strategic gap analysis
        data = await call_gpt4o_json(
            ORGBOARD_GAP_PROMPT.format(
                planned=json.dumps(planned_keys),
                existing=json.dumps(existing_keys),
            ),
            f"Planned teams with dependencies:\n"
            + json.dumps([{"key": t.team_key, "deps": t.dependencies} for t in self._team_specs], indent=2),
            max_tokens=800,
        )

        gaps = data.get("gaps", [])
        is_complete = data.get("complete", False)
        next_key = data.get("next")

        next_spec = None
        if next_key:
            for t in self._team_specs:
                if t.team_key == next_key:
                    next_spec = t
                    break

        return gaps, next_spec, is_complete

    def get_spec(self, team_key: str) -> TeamSpec | None:
        """Look up a TeamSpec by key."""
        if not self._team_specs:
            return None
        for t in self._team_specs:
            if t.team_key == team_key:
                return t
        return None


# ---------------------------------------------------------------------------
# CrossTeamLinker — connect validated teams via Minibook
# ---------------------------------------------------------------------------

HANDOFF_PROMPT = """\
You are generating handoff definitions between agent teams in a company.

Given these validated teams and their capabilities, define how work flows between them.

Teams: {teams}

Return JSON:
{
  "handoffs": [
    {
      "from_team": "team_key",
      "to_team": "team_key",
      "trigger": "when this happens...",
      "data_passed": "what information is handed off"
    }
  ]
}

Only include handoffs that make business sense. Be specific about triggers."""


class CrossTeamLinker:
    """Links validated teams via Minibook community projects and handoff posts."""

    async def link_teams(
        self,
        session: aiohttp.ClientSession,
        registry_entries: list[dict],
        registry_agent_api_key: str | None,
    ):
        """Ensure all validated teams are in their correct Community Projects."""
        for entry in registry_entries:
            if entry.get("status") != "validated":
                continue
            team_key = entry.get("team_key", "")
            if team_key not in COMMUNITY_GROUPS:
                # Dynamic team — add to a generic community group
                continue
            if entry.get("community_project_id"):
                continue  # already linked
            try:
                project_id = await ensure_community_project(
                    session, team_key, registry_agent_api_key
                )
                if project_id:
                    print(f"  [CrossTeamLinker] Linked {team_key} to community project")
            except Exception as e:
                print(f"  [CrossTeamLinker] Link failed for {team_key}: {e}")

    async def post_handoffs(
        self,
        session: aiohttp.ClientSession,
        team_specs: list[TeamSpec],
        registry_entries: list[dict],
        project_id: str,
        api_key: str,
    ):
        """Generate and post handoff definitions between validated teams."""
        validated = [
            e for e in registry_entries if e.get("status") == "validated"
        ]
        if len(validated) < 2:
            return  # need at least 2 teams for handoffs

        teams_summary = json.dumps([
            {
                "team_key": e["team_key"],
                "capabilities": e.get("capabilities", []),
                "eval_reason": e.get("eval_reason", "")[:200],
            }
            for e in validated
        ], indent=2)

        data = await call_gpt4o_json(
            HANDOFF_PROMPT.format(teams=teams_summary),
            f"Define handoffs for {len(validated)} validated teams.",
            max_tokens=1500,
        )

        handoffs = data.get("handoffs", [])
        if not handoffs:
            return

        # Format as markdown and post
        lines = ["## Cross-Team Handoff Definitions\n"]
        for h in handoffs:
            lines.append(
                f"- **{h.get('from_team', '?')}** → **{h.get('to_team', '?')}**\n"
                f"  - Trigger: {h.get('trigger', 'N/A')}\n"
                f"  - Data: {h.get('data_passed', 'N/A')}\n"
            )

        content = "\n".join(lines)
        try:
            await api_post(
                session,
                f"/api/v1/projects/{project_id}/posts",
                {
                    "title": "Cross-Team Handoff Map",
                    "content": content,
                    "type": "plan",
                    "tags": ["company-forge", "handoffs"],
                },
                api_key=api_key,
            )
            print(f"  [CrossTeamLinker] Posted {len(handoffs)} handoff definitions")
        except Exception as e:
            print(f"  [CrossTeamLinker] Handoff post failed: {e}")

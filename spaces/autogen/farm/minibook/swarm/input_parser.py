"""Input file parser — LLM-based parsing of structured agent org docs into manifests + YAML."""

import asyncio
import json
import re
from pathlib import Path

import yaml

from .constants import DEFAULT_MODEL
from .llm import call_gpt4o_json, call_gpt4o_vision_json
from .todo_implementer import ask_user


# ── Rate limiter for parallel LLM calls ──────────────────────────────────────
_LLM_SEMAPHORE = asyncio.Semaphore(10)


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM PROMPTS FOR PARSING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

VISION_SYSTEM_PROMPT = """\
You are an expert organizational chart analyst. Analyze this image showing an \
agent hierarchy / org chart. Extract the complete structure as JSON.

Return JSON with this exact schema:
{
  "org_name": "Name of the organization",
  "teams": [
    {"name": "snake_case_team_name", "label": "Human Readable Team Name"}
  ],
  "agents": [
    {"name": "PascalCaseName", "team": "snake_case_team_name",
     "role": "executive|manager|specialist", "parent": "ParentAgentName or null"}
  ],
  "connections": [
    {"from": "AgentA", "to": "AgentB", "type": "manages|delegates|reports_to|handoff"}
  ]
}

Rules:
- "role" is inferred from position: top-level = executive, middle layer = manager, leaf = specialist
- "team" groups agents visually adjacent or under the same branch
- Use PascalCase for agent names (e.g. "EmailOutreachSpecialist")
- Use snake_case for team names (e.g. "outreach")
- Include ALL agents visible in the chart
"""

CLASSIFY_SYSTEM_PROMPT = """\
Classify each markdown heading as "agent" (describes a specific AI agent with \
a role, responsibilities, and possibly a prompt) or "non_agent" (introduction, \
overview, guide, team summary, table of contents, implementation guide, etc.).

Return JSON: {"classifications": {"heading_text": "agent"|"non_agent", ...}}
"""

EXTRACT_AGENT_SYSTEM_PROMPT = """\
You are an expert at parsing AI agent specifications from documentation. \
Extract structured info from this single agent section. Return JSON:

{
  "name": "PascalCaseName (e.g. EmailOutreachSpecialist)",
  "display_name": "Human-readable name",
  "role": "executive|manager|specialist",
  "team_hint": "snake_case team this agent likely belongs to (e.g. outreach, bdr, revops, research, qualification, callintel, workspace, content, intel)",
  "tools": ["internal_function_names"],
  "responsibilities": ["bullet1", "bullet2"],
  "handoff_hints": ["names of agents this should hand off to"],
  "manages": ["names of agents this manages, if any"],
  "reports_to": "name of manager/executive, if mentioned, else null",
  "language": "if language-specific agent, which language, else null"
}

Tool mapping rules — map mentioned product/platform names to function names:
- CRM tools (HubSpot, Salesforce, Close.io, GoHighLevel) → "crm_search"
- CRM logging → "crm_log_activity"
- CRM contacts → "crm_create_contact"
- CRM deals → "crm_update_deal"
- Email tools (Smartlead, Instantly, Lemlist, Apollo email) → "send_email"
- Email deliverability → "check_email_deliverability"
- Email copy generation → "generate_email_copy"
- SMS/Voice (Twilio, Vapi, Bland.ai, Retell, HeyGen) → "send_sms"
- Video (Loom, Vidyard, Tavus, SendSpark) → "create_video_message"
- Enrichment (Clearbit, ZoomInfo, Lusha, Findymail, Clay) → "enrich_contact"
- LinkedIn (LinkedIn, HeyReach, Sales Navigator) → "fetch_linkedin_profile"
- Intent (Bombora, G2, TrustRadius) → "analyze_intent_signals"
- Scheduling (Calendly, Cal.com, Chili Piper) → "schedule_meeting"
- Call recording (Gong, Fireflies, Otter.ai) → "analyze_call_transcript"
- Competitive (Crayon, Klue, Kompyte) → "search_competitors"
- Content/Docs (Highspot, Seismic, Notion, Canva) → "write_report"
- Data warehouse (Snowflake, BigQuery, Looker) → "query_data_warehouse"
- Monitoring (Datadog, New Relic, PagerDuty) → "check_system_health"
- Slack → "send_slack_message"
- Translation → "translate_text"
- Lead scoring (MadKudu) → "score_lead"
- ICP fit → "assess_icp_fit"
- BANT qualification → "qualify_bant"
- Battle cards → "create_battle_card"
- Reports → "generate_report"
- File reading → "read_file"
- Claude Code → "claude_code"

If a tool doesn't match any above, use a reasonable snake_case function name.
Always include "claude_code" for managers and executives.
"""

TEAM_TASK_SYSTEM_PROMPT = """\
Generate a concrete, actionable task description for an AI agent team. The task \
should exercise all agents in the team, use their tools, and produce output files.

Return JSON:
{
  "task": "Detailed task description with specific example data (names, companies, etc.). \
Must instruct agents to write output to /app/output/ incrementally."
}

Rules:
- Use realistic example data (names, company names, email addresses)
- Reference specific agents by name when helpful
- Instruct agents to write to /app/output/ INCREMENTALLY (file per agent or append)
- Keep under 300 words
"""


# ── Role fallback tools (used when LLM doesn't return tools) ────────────────
_GENERIC_FALLBACK_TOOLS = {
    "executive": ["crm_search", "generate_report", "write_report", "claude_code"],
    "manager": ["crm_search", "generate_report", "write_report", "claude_code"],
    "specialist": ["write_report", "read_file", "claude_code"],
}


# ── Prompt suffixes — delegation vs autonomy ─────────────────────────────────

# For executives/managers WITH handoffs — must delegate before doing own work
DELEGATION_SUFFIX = (
    "\n\nDELEGATION PROTOCOL (MANDATORY):\n"
    "- FIRST: Assess which of your delegatable agents best matches the current task.\n"
    "- If a match exists, hand off to them IMMEDIATELY before doing any work yourself.\n"
    "- Only use your own domain tools if NO delegatable agent is suitable.\n"
    "- After receiving results back from a delegate, synthesize and write to /app/output/.\n"
    "- If no input data is provided, generate realistic example data and proceed.\n"
    "- Write output files to /app/output/ INCREMENTALLY.\n"
    "- Only the lead agent should say TERMINATE. All others: hand back to your manager.\n"
)

# For specialists/leaf agents — act autonomously, hand back when done
AUTONOMY_SUFFIX = (
    "\n\nAUTONOMOUS OPERATION RULES:\n"
    "- If no input data is provided, generate realistic example data and proceed.\n"
    "- NEVER ask for clarification more than once. After one ask, proceed with defaults.\n"
    "- Use your domain tools immediately — do not wait for permission.\n"
    "- CRITICAL: Write output files to /app/output/ INCREMENTALLY. After processing EACH item "
    "(lead, contact, company), immediately append results to the output file. Do NOT wait "
    "until all items are processed — partial output is better than no output.\n"
    "- Use write_file tool to create /app/output/ files early and update them as you go.\n"
    "- When your task is complete, hand back to your manager (do NOT say TERMINATE).\n"
)


def _clean_prompt(text: str) -> str:
    """Strip citation artifacts and collapse excessive whitespace from LLM-extracted prompts."""
    text = re.sub(r'\[web:\d+\]', '', text)
    text = re.sub(r'\[source:\d+\]', '', text)
    text = re.sub(r'\[ref:\d+\]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _smart_truncate(prompt: str, max_len: int = 5000) -> str:
    """Truncate long prompts preserving start (context) and end (critical rules)."""
    if len(prompt) <= max_len:
        return prompt
    keep_start = int(max_len * 0.7)
    keep_end = max_len - keep_start - 30
    return prompt[:keep_start] + "\n...[truncated]...\n" + prompt[-keep_end:]


# ═══════════════════════════════════════════════════════════════════════════════
#  GENERIC TEXT HELPERS (not org-specific)
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_agent_name(raw: str) -> str:
    """Convert raw heading like '🙋🏼 Channel Outreach Manager' → 'ChannelOutreachManager'."""
    cleaned = re.sub(r':[a-z_\-]+:', '', raw)
    cleaned = re.sub(r'[^\w\s\-/()]', '', cleaned)
    cleaned = cleaned.strip()
    words = re.split(r'[\s\-/]+', cleaned)
    return "".join(w.capitalize() for w in words if w)


def _extract_prompt(section_text: str) -> str:
    """Extract the content between triple backticks after '### Agent Prompt'."""
    prompt_match = re.search(r'###\s*Agent Prompt\s*\n', section_text)
    if not prompt_match:
        return ""
    after_heading = section_text[prompt_match.end():]
    code_match = re.search(r'```[^\n]*\n(.*?)```', after_heading, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()
    return ""


def _extract_responsibilities(section_text: str) -> list:
    """Extract key responsibilities bullets."""
    resp_match = re.search(r'###\s*Key Responsibilities\s*\n', section_text)
    if not resp_match:
        return []
    after_heading = section_text[resp_match.end():]
    end_match = re.search(r'\n###', after_heading)
    resp_text = after_heading[:end_match.start()] if end_match else after_heading
    bullets = re.findall(r'^[-*]\s+(.+)$', resp_text, re.MULTILINE)
    return bullets[:8]


def _split_agent_sections(content: str) -> list:
    """Split input.md into sections by ## headings. Returns [(heading, body), ...]."""
    sections = []
    parts = re.split(r'\n(?=## (?!#))', content)
    for part in parts:
        match = re.match(r'## (.+)\n', part)
        if match:
            heading = match.group(1).strip()
            body = part[match.end():]
            sections.append((heading, body))
    return sections


def _fuzzy_match(name_a: str, name_b: str) -> bool:
    """Fuzzy match: check if significant parts overlap (strict)."""
    a_parts = set(re.findall(r'[A-Z][a-z]+', name_a))
    b_parts = set(re.findall(r'[A-Z][a-z]+', name_b))
    common = {"Agent", "Manager", "Lead", "Specialist", "The"}
    a_sig = a_parts - common
    b_sig = b_parts - common
    if not a_sig or not b_sig:
        return False
    overlap = a_sig & b_sig
    shorter = min(len(a_sig), len(b_sig))
    return len(overlap) >= shorter


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM-BASED PARSING PIPELINE (6 Steps)
# ═══════════════════════════════════════════════════════════════════════════════

async def _step_vision_analysis(image_path: Path) -> dict:
    """Step 1: Analyze org chart PNG → hierarchy skeleton."""
    if image_path is None or not image_path.exists():
        print("  [InputParser] No image provided — skipping vision analysis")
        return {"org_name": "", "teams": [], "agents": [], "connections": []}

    print(f"  [InputParser] Analyzing org chart image: {image_path.name}")
    skeleton = await call_gpt4o_vision_json(
        VISION_SYSTEM_PROMPT,
        "Analyze this organizational hierarchy chart and extract the complete agent structure.",
        image_path,
        max_tokens=4096,
    )
    if not skeleton or not skeleton.get("agents"):
        print("  [InputParser] Vision analysis returned empty — continuing with text only")
        return {"org_name": "", "teams": [], "agents": [], "connections": []}

    print(f"  [InputParser] Vision extracted: {len(skeleton.get('agents', []))} agents, "
          f"{len(skeleton.get('teams', []))} teams, {len(skeleton.get('connections', []))} connections")
    return skeleton


async def _step_chunk_and_classify(content: str) -> tuple:
    """Step 2: Split by ## headings, classify as agent vs non-agent.

    Returns (agent_chunks, non_agent_chunks) where each is [(heading, body, index), ...].
    """
    sections = _split_agent_sections(content)
    agent_chunks = []
    non_agent_chunks = []
    ambiguous = []

    for i, (heading, body) in enumerate(sections):
        # Cheap heuristic: sections with ### Purpose or ### Agent Prompt are agents
        if "### Purpose" in body and "### Agent Prompt" in body:
            agent_chunks.append((heading, body, i))
        elif "### Purpose" in body or "### Agent Prompt" in body:
            agent_chunks.append((heading, body, i))
        else:
            ambiguous.append((heading, body, i))

    # For ambiguous sections, ask LLM to classify in one batch call
    if ambiguous:
        headings_list = [h for h, _, _ in ambiguous]
        # Only classify if there are enough to justify the call
        if len(headings_list) > 0:
            user_msg = "Classify these headings:\n" + "\n".join(f"- {h}" for h in headings_list)
            result = await call_gpt4o_json(CLASSIFY_SYSTEM_PROMPT, user_msg, max_tokens=512)
            classifications = result.get("classifications", {})
            for heading, body, idx in ambiguous:
                if classifications.get(heading) == "agent":
                    agent_chunks.append((heading, body, idx))
                else:
                    non_agent_chunks.append((heading, body, idx))
        else:
            non_agent_chunks.extend(ambiguous)

    print(f"  [InputParser] Classified {len(agent_chunks)} agent sections, "
          f"{len(non_agent_chunks)} non-agent sections")
    return agent_chunks, non_agent_chunks


async def _extract_one_agent(heading: str, body: str) -> dict:
    """Step 3 (per-agent): Extract structured info from one document section."""
    async with _LLM_SEMAPHORE:
        # Truncate body to ~3000 chars to keep within token budget
        truncated_body = body[:6000] if len(body) > 6000 else body
        user_msg = f"## {heading}\n\n{truncated_body}"
        llm_result = await call_gpt4o_json(EXTRACT_AGENT_SYSTEM_PROMPT, user_msg, max_tokens=1024)

    if not llm_result or not llm_result.get("name"):
        # Fallback: use regex extraction
        name = _clean_agent_name(heading)
        return {
            "name": name,
            "display_name": heading,
            "role": "specialist",
            "team_hint": "",
            "tools": _GENERIC_FALLBACK_TOOLS["specialist"],
            "responsibilities": _extract_responsibilities(body),
            "handoff_hints": [],
            "manages": [],
            "reports_to": None,
            "language": None,
            "prompt": _extract_prompt(body),
        }

    # Merge: use regex-extracted prompt (exact text) over LLM summary
    llm_result["prompt"] = _extract_prompt(body) or llm_result.get("prompt", "")

    # Ensure required fields
    llm_result.setdefault("name", _clean_agent_name(heading))
    llm_result.setdefault("role", "specialist")
    llm_result.setdefault("tools", _GENERIC_FALLBACK_TOOLS.get(llm_result["role"], []))
    llm_result.setdefault("responsibilities", _extract_responsibilities(body))
    llm_result.setdefault("handoff_hints", [])
    llm_result.setdefault("manages", [])
    llm_result.setdefault("reports_to", None)
    llm_result.setdefault("language", None)
    llm_result.setdefault("team_hint", "")

    return llm_result


async def _step_extract_agents(agent_chunks: list) -> list:
    """Step 3: Extract all agents in parallel."""
    print(f"  [InputParser] Extracting {len(agent_chunks)} agents in parallel (semaphore=10)...")
    tasks = [_extract_one_agent(h, b) for h, b, _ in agent_chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    agents = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  [!] Agent extraction failed for chunk {i}: {result}")
            # Create fallback from heading
            heading = agent_chunks[i][0]
            agents.append({
                "name": _clean_agent_name(heading),
                "display_name": heading,
                "role": "specialist",
                "team_hint": "",
                "tools": _GENERIC_FALLBACK_TOOLS["specialist"],
                "responsibilities": [],
                "handoff_hints": [],
                "manages": [],
                "reports_to": None,
                "language": None,
                "prompt": "",
            })
        else:
            agents.append(result)

    print(f"  [InputParser] Extracted {len(agents)} agents successfully")
    return agents


async def _step_assemble(vision_skeleton: dict, agent_extractions: list) -> dict:
    """Step 4: Merge vision hierarchy + per-agent extractions into org structure."""
    print("  [InputParser] Assembling org structure...")

    # Build lookup from vision skeleton
    vision_agents = {a["name"]: a for a in vision_skeleton.get("agents", [])}
    vision_connections = vision_skeleton.get("connections", [])
    org_name = vision_skeleton.get("org_name", "")

    # Classify agents by role
    executives = []
    managers = []
    specialists = []

    for agent in agent_extractions:
        # Cross-reference with vision data
        vision_match = vision_agents.get(agent["name"])
        if vision_match:
            # Vision role overrides if text was ambiguous
            if not agent.get("team_hint"):
                agent["team_hint"] = vision_match.get("team", "")
            if vision_match.get("parent") and not agent.get("reports_to"):
                agent["reports_to"] = vision_match["parent"]

        role = agent.get("role", "specialist")
        if role == "executive":
            executives.append(agent)
        elif role == "manager":
            managers.append(agent)
        else:
            specialists.append(agent)

    # If no org_name from vision, infer from document
    if not org_name:
        org_name = "AI Agent Organisation"

    # Group specialists into teams
    # Strategy: use team_hint + reports_to + manages relationships
    teams = {}  # team_key → {"manager": name, "specialists": [agent_dicts]}

    # First, map managers to team keys
    manager_team_map = {}
    for mgr in managers:
        team_key = mgr.get("team_hint") or mgr["name"].lower().replace("manager", "").strip("_")
        # Deduplicate team keys
        base_key = re.sub(r'[^a-z0-9_]', '', team_key.lower().replace(" ", "_"))
        if not base_key:
            base_key = _clean_agent_name(mgr["name"]).lower()
        manager_team_map[mgr["name"]] = base_key
        teams[base_key] = {"manager": mgr["name"], "specialists": []}

    # Assign specialists to teams
    unassigned = []
    for spec in specialists:
        assigned = False
        # Try reports_to
        if spec.get("reports_to"):
            for mgr_name, team_key in manager_team_map.items():
                if _fuzzy_match(spec["reports_to"], mgr_name) or spec["reports_to"] == mgr_name:
                    teams[team_key]["specialists"].append(spec)
                    assigned = True
                    break
        # Try team_hint
        if not assigned and spec.get("team_hint"):
            hint = spec["team_hint"].lower().replace(" ", "_")
            for team_key in teams:
                if hint in team_key or team_key in hint:
                    teams[team_key]["specialists"].append(spec)
                    assigned = True
                    break
        # Try manages from managers
        if not assigned:
            for mgr in managers:
                managed = mgr.get("manages", [])
                for managed_name in managed:
                    if _fuzzy_match(spec["name"], managed_name) or spec["name"] == managed_name:
                        team_key = manager_team_map[mgr["name"]]
                        teams[team_key]["specialists"].append(spec)
                        assigned = True
                        break
                if assigned:
                    break
        if not assigned:
            unassigned.append(spec)

    # Assign remaining specialists to closest team by name similarity
    for spec in unassigned:
        best_team = None
        best_score = 0
        for team_key, team_info in teams.items():
            # Simple similarity: shared words
            spec_words = set(re.findall(r'[A-Z][a-z]+', spec["name"]))
            mgr_words = set(re.findall(r'[A-Z][a-z]+', team_info["manager"]))
            common = {"Agent", "Manager", "Lead", "Specialist", "The"}
            score = len((spec_words - common) & (mgr_words - common))
            if score > best_score:
                best_score = score
                best_team = team_key
        if best_team:
            teams[best_team]["specialists"].append(spec)
        elif teams:
            # Last resort: put in first team
            first_key = next(iter(teams))
            teams[first_key]["specialists"].append(spec)

    # Generate team tasks using LLM (sub-teams + core)
    print(f"  [InputParser] Generating tasks for {len(teams) + 1} teams...")
    task_calls = []
    task_keys = []

    # Core team task
    exec_names = [a["name"] for a in executives]
    mgr_names = [m["name"] for m in managers]
    core_tools = set()
    for a in executives + managers:
        core_tools.update(a.get("tools", []))
    core_user_msg = (
        f"Organization: {org_name}\n"
        f"Team: core (executive + managers)\n"
        f"Executive(s): {', '.join(exec_names)}\n"
        f"Managers: {', '.join(mgr_names)}\n"
        f"Available tools: {', '.join(sorted(core_tools))}\n"
    )
    task_calls.append(call_gpt4o_json(TEAM_TASK_SYSTEM_PROMPT, core_user_msg, max_tokens=2048))
    task_keys.append("__core__")

    # Sub-team tasks
    for team_key, team_info in teams.items():
        mgr_name = team_info["manager"]
        spec_names = [s["name"] for s in team_info["specialists"]]
        all_tools = set()
        for s in team_info["specialists"]:
            all_tools.update(s.get("tools", []))
        user_msg = (
            f"Organization: {org_name}\n"
            f"Team: {team_key}\n"
            f"Manager: {mgr_name}\n"
            f"Specialists: {', '.join(spec_names)}\n"
            f"Available tools: {', '.join(sorted(all_tools))}\n"
        )
        task_calls.append(call_gpt4o_json(TEAM_TASK_SYSTEM_PROMPT, user_msg, max_tokens=2048))
        task_keys.append(team_key)

    task_results = await asyncio.gather(*task_calls, return_exceptions=True)
    team_tasks = {}
    core_task = None
    for key, result in zip(task_keys, task_results):
        if isinstance(result, dict) and result.get("task"):
            if key == "__core__":
                core_task = result["task"]
            else:
                team_tasks[key] = result["task"]
        elif key != "__core__":
            mgr = teams[key]["manager"]
            team_tasks[key] = f"Complete tasks for {mgr}'s team and write results to /app/output/."

    # Build core_team dict (executive + managers)
    core_team = {}
    manager_names = list(manager_team_map.keys())

    for exec_agent in executives:
        name = exec_agent["name"]
        if not name.endswith("Agent"):
            name = name + "Agent"
        core_team[name] = {
            "role": "executive",
            "prompt": exec_agent.get("prompt") or f"You are the {name}, the strategic orchestrator.",
            "tools": exec_agent.get("tools", _GENERIC_FALLBACK_TOOLS["executive"]),
            "handoffs": manager_names,
            "responsibilities": exec_agent.get("responsibilities", []),
        }

    if not executives:
        # Create default executive
        core_team["CSOAgent"] = {
            "role": "executive",
            "prompt": "You are the CSO Agent, the strategic orchestrator. Delegate tasks to team managers.",
            "tools": _GENERIC_FALLBACK_TOOLS["executive"],
            "handoffs": manager_names,
            "responsibilities": ["Delegate tasks to managers", "Monitor pipeline health"],
        }

    for mgr in managers:
        team_key = manager_team_map[mgr["name"]]
        spec_names = [s["name"] for s in teams[team_key]["specialists"]]
        core_team[mgr["name"]] = {
            "role": "manager",
            "prompt": mgr.get("prompt") or f"You are the {mgr['name']}. Manage your team.",
            "tools": mgr.get("tools", _GENERIC_FALLBACK_TOOLS["manager"]),
            "handoffs": list(core_team.keys())[:1],  # Hand back to executive
            "responsibilities": mgr.get("responsibilities", []),
            "sub_team_key": team_key,
            "specialist_count": len(spec_names),
        }

    # Build sub_teams dict
    sub_teams = {}
    for team_key, team_info in teams.items():
        mgr_name = team_info["manager"]
        agents_dict = {}
        for spec in team_info["specialists"]:
            agents_dict[spec["name"]] = {
                "role": "specialist",
                "prompt": spec.get("prompt") or f"You are {spec['name']}. Complete your tasks and report back to {mgr_name}.",
                "tools": spec.get("tools", _GENERIC_FALLBACK_TOOLS["specialist"]),
                "handoffs": [mgr_name],
                "responsibilities": spec.get("responsibilities", []),
            }
        sub_teams[team_key] = {
            "manager": mgr_name,
            "agents": agents_dict,
            "task": team_tasks.get(team_key, f"Complete tasks for {mgr_name}'s team."),
        }

    # Count total agents
    total = len(core_team)
    for team in sub_teams.values():
        total += len(team["agents"])

    print(f"  [InputParser] Assembled: {len(core_team)} core, {len(sub_teams)} teams, {total} total")

    return {
        "org_name": org_name,
        "agent_count": total,
        "core_team": core_team,
        "sub_teams": sub_teams,
        "core_task": core_task,
    }


async def _step_user_review(assembled: dict) -> dict:
    """Step 5: Show assembled org structure in architecture_review modal."""
    # Build graph for React Flow visualization
    nodes = []
    edges = []
    groups = []

    # Add executive/input node
    exec_names = [n for n, info in assembled["core_team"].items() if info["role"] == "executive"]
    for name in exec_names:
        nodes.append({"id": name, "type": "manager", "label": name, "group": "executive"})

    # Add managers
    for name, info in assembled["core_team"].items():
        if info["role"] == "manager":
            nodes.append({"id": name, "type": "manager", "label": name, "group": info.get("sub_team_key", "")})
            # Edge from executive
            for exec_name in exec_names:
                edges.append({"source": exec_name, "target": name, "type": "delegation", "label": "manages"})

    # Add specialists
    for team_key, team_info in assembled["sub_teams"].items():
        groups.append({"id": team_key, "label": team_key.replace("_", " ").title()})
        for spec_name in team_info["agents"]:
            nodes.append({"id": spec_name, "type": "specialist", "label": spec_name, "group": team_key})
            edges.append({"source": team_info["manager"], "target": spec_name, "type": "handoff", "label": "handoff"})

    # Input/output nodes
    nodes.insert(0, {"id": "_input", "type": "input", "label": "Task Input"})
    nodes.append({"id": "_output", "type": "output", "label": "Output Files"})
    if exec_names:
        edges.insert(0, {"source": "_input", "target": exec_names[0], "type": "data", "label": "task"})
    edges.append({"source": nodes[-2]["id"], "target": "_output", "type": "data", "label": "results"})

    msg = (f"Review parsed org structure: {assembled['org_name']} "
           f"({assembled['agent_count']} agents, {len(assembled['sub_teams'])} teams)")

    answer = await ask_user(
        question_type="architecture_review",
        tool_name="InputParser",
        message=msg,
        metadata={"nodes": nodes, "edges": edges, "groups": groups},
        timeout=120,
    )

    if answer.get("action") == "reject":
        print("  [InputParser] User rejected org structure — aborting")
        raise RuntimeError("User rejected parsed org structure")

    print("  [InputParser] Org structure approved")
    return assembled


async def parse_input_file_llm(path: Path, image_path: Path = None) -> dict:
    """Parse any structured agent org document into a manifest using LLM analysis.

    6-step pipeline:
      1. Vision analysis of org chart image (optional)
      2. Chunk document and classify headings
      3. Extract agent info per-chunk in parallel
      4. Assemble into org structure (merge vision + text)
      5. User review via modal
      6. Return manifest

    Returns:
        {
            "org_name": str,
            "agent_count": int,
            "core_team": {agent_name: {role, prompt, tools, handoffs, responsibilities}},
            "sub_teams": {team_key: {manager, agents: {name: {role, prompt, tools, handoffs}}, task}},
        }
    """
    print(f"\n{'=' * 60}")
    print(f"  LLM-BASED INPUT PARSER")
    print(f"  Document: {path.name}")
    print(f"  Image: {image_path.name if image_path and image_path.exists() else 'none'}")
    print(f"{'=' * 60}\n")

    content = path.read_text(encoding="utf-8", errors="replace")

    # Steps 1 & 2 can run in parallel
    vision_task = _step_vision_analysis(image_path)
    classify_task = _step_chunk_and_classify(content)
    vision_skeleton, (agent_chunks, _non_agent_chunks) = await asyncio.gather(
        vision_task, classify_task
    )

    # Step 3: Extract agents in parallel
    agent_extractions = await _step_extract_agents(agent_chunks)

    # Step 4: Assemble
    assembled = await _step_assemble(vision_skeleton, agent_extractions)

    # Step 5: User review
    assembled = await _step_user_review(assembled)

    # Step 6: Return manifest
    print(f"\n  [InputParser] Final manifest: {assembled['agent_count']} agents, "
          f"{len(assembled['sub_teams'])} teams")
    return assembled


# ═══════════════════════════════════════════════════════════════════════════════
#  YAML GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_core_team_yamls(manifest: dict) -> dict:
    """Generate project.yml + agent.yml files for the CSO + Managers team.

    Returns: {"project.yml": yaml_str, "agents/CSOAgent/agent.yml": yaml_str, ...}
    """
    core = manifest["core_team"]
    files = {}

    # project.yml
    org_name = manifest.get("org_name", "AI Agent Organisation")
    # Sanitize org_name into a project slug
    slug = re.sub(r'[^a-zA-Z0-9]+', '', org_name.replace(" ", ""))
    core_task = manifest.get("core_task",
        f"Execute the {org_name} mission: coordinate all managers, "
        f"delegate tasks, and write results to /app/output/."
    )
    project = {
        "name": f"{slug}Core",
        "description": f"Core team: {len(core)} agents for the {org_name} Organization.",
        "autogen_version": ">=0.4",
        "pattern": "swarm",
        "termination": {"type": "max_messages", "value": 150},
        "lead_agent": next(iter(core)),
        "agents_total": len(core),
        "mcp_servers": ["filesystem", "fetch"],
        "task": core_task,
    }
    files["project.yml"] = yaml.dump(project, default_flow_style=False, allow_unicode=True)

    # Agent YAMLs
    for agent_name, info in core.items():
        handoffs = info.get("handoffs", [])
        prompt_text = _clean_prompt(info["prompt"])

        # Managers/executives with handoffs get delegation-first instructions
        if handoffs:
            delegation_list = ", ".join(handoffs)
            suffix = (
                f"\n\nYour delegatable agents: {delegation_list}\n"
                + DELEGATION_SUFFIX
            )
        else:
            suffix = AUTONOMY_SUFFIX

        agent_yml = {
            "name": agent_name,
            "model": DEFAULT_MODEL,
            "system_message": _smart_truncate(prompt_text) + suffix,
            "domain_tools": list(dict.fromkeys(info["tools"])),  # deduplicate, preserve order
            "handoffs": handoffs,
        }
        if info.get("responsibilities"):
            agent_yml["description"] = "; ".join(info["responsibilities"][:3])
        files[f"agents/{agent_name}/agent.yml"] = yaml.dump(
            agent_yml, default_flow_style=False, allow_unicode=True)

    return files


def generate_sub_team_yamls(manifest: dict, team_key: str) -> dict:
    """Generate project.yml + agent.yml files for one manager's sub-team.

    The manager becomes lead_agent; specialists are workers that hand back to manager.

    Returns: {"project.yml": yaml_str, "agents/<name>/agent.yml": yaml_str, ...}
    """
    sub = manifest["sub_teams"][team_key]
    manager_name = sub["manager"]
    agents = sub["agents"]
    manager_info = manifest["core_team"].get(manager_name, {})

    files = {}

    # Determine message budget based on team size
    agent_count = 1 + len(agents)  # manager + specialists
    msg_budget = max(150, agent_count * 30)

    # project.yml
    specialist_names = list(agents.keys())
    project = {
        "name": f"{re.sub(r'[^a-zA-Z0-9]+', '', manifest.get('org_name', 'AI').replace(' ', ''))}_{team_key.capitalize()}",
        "description": f"{manager_name}'s sub-team with {len(agents)} specialists.",
        "autogen_version": ">=0.4",
        "pattern": "swarm",
        "termination": {"type": "max_messages", "value": msg_budget},
        "lead_agent": manager_name,
        "agents_total": agent_count,
        "mcp_servers": ["filesystem", "fetch"],
        "task": sub.get("task",
            f"Complete tasks for {manager_name}'s team and write results to /app/output/."
        ),
    }
    files["project.yml"] = yaml.dump(project, default_flow_style=False, allow_unicode=True)

    # Manager agent.yml (lead) — delegation-first
    manager_tools = manager_info.get("tools", _GENERIC_FALLBACK_TOOLS["manager"])
    manager_prompt = _clean_prompt(manager_info.get("prompt", f"You are the {manager_name}."))
    delegation_list = ", ".join(specialist_names)
    manager_yml = {
        "name": manager_name,
        "model": "gpt-4o",
        "system_message": (
            _smart_truncate(manager_prompt)
            + f"\n\nYour delegatable agents: {delegation_list}\n"
            + DELEGATION_SUFFIX
        ),
        "domain_tools": list(dict.fromkeys(manager_tools)),  # deduplicate
        "handoffs": specialist_names,  # Manager delegates to specialists
    }
    files[f"agents/{manager_name}/agent.yml"] = yaml.dump(
        manager_yml, default_flow_style=False, allow_unicode=True)

    # Specialist agent.ymls — autonomous, hand back to manager
    for agent_name, info in agents.items():
        specialist_prompt = _clean_prompt(info["prompt"])
        agent_yml = {
            "name": agent_name,
            "model": DEFAULT_MODEL,
            "system_message": (
                _smart_truncate(specialist_prompt)
                + f"\n\nWhen done, hand back to your manager: {manager_name}\n"
                + AUTONOMY_SUFFIX
            ),
            "domain_tools": list(dict.fromkeys(info["tools"])),  # deduplicate
            "handoffs": [manager_name],  # Hand back to manager
        }
        files[f"agents/{agent_name}/agent.yml"] = yaml.dump(
            agent_yml, default_flow_style=False, allow_unicode=True)

    return files


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOLS.PY GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

# All sales mock tool implementations
SALES_TOOL_IMPLEMENTATIONS = {
    "crm_search": '''
async def crm_search(query: str, object_type: str = "contact") -> str:
    """Search CRM records by query string. Returns matching records as JSON.
    # TODO: integrate with actual CRM API (Close.io / HubSpot / GoHighLevel)
    """
    return json.dumps({"results": [{"id": f"crm_{hash(query) % 10000}", "name": query, "type": object_type, "status": "active", "last_activity": "2026-02-20"}], "total": 1})
''',
    "crm_create_contact": '''
async def crm_create_contact(name: str, email: str, company: str, title: str = "") -> str:
    """Create a new contact in CRM. Returns the created contact ID.
    # TODO: integrate with actual CRM API
    """
    contact_id = f"contact_{hash(email) % 100000}"
    return json.dumps({"id": contact_id, "name": name, "email": email, "company": company, "title": title, "created": True})
''',
    "crm_update_deal": '''
async def crm_update_deal(deal_id: str, stage: str, value: float = 0, notes: str = "") -> str:
    """Update a deal/opportunity in CRM. Returns updated deal info.
    # TODO: integrate with actual CRM API
    """
    return json.dumps({"deal_id": deal_id, "stage": stage, "value": value, "notes": notes, "updated": True})
''',
    "crm_log_activity": '''
async def crm_log_activity(contact_id: str, activity_type: str, notes: str) -> str:
    """Log an activity (call, email, meeting) in CRM for a contact.
    # TODO: integrate with actual CRM API
    """
    return json.dumps({"contact_id": contact_id, "activity_type": activity_type, "logged": True, "timestamp": "2026-02-24T10:00:00Z"})
''',
    "send_email": '''
async def send_email(to: str, subject: str, body: str, sequence_id: str = "") -> str:
    """Send an outbound email via sales engagement platform.
    # TODO: integrate with Smartlead / Instantly / Lemlist API
    """
    return json.dumps({"to": to, "subject": subject, "sent": True, "message_id": f"msg_{hash(to) % 100000}", "sequence_id": sequence_id})
''',
    "send_sms": '''
async def send_sms(to: str, message: str) -> str:
    """Send an SMS message via voice/SMS platform.
    # TODO: integrate with Twilio / Vapi API
    """
    return json.dumps({"to": to, "sent": True, "sms_id": f"sms_{hash(to) % 100000}"})
''',
    "check_email_deliverability": '''
async def check_email_deliverability(domain: str) -> str:
    """Check email deliverability score for a domain.
    # TODO: integrate with ZeroBounce / Mail-tester API
    """
    return json.dumps({"domain": domain, "score": 85, "status": "deliverable", "spf": True, "dkim": True, "dmarc": True})
''',
    "schedule_meeting": '''
async def schedule_meeting(attendees: str, topic: str, duration_min: int = 30, preferred_time: str = "") -> str:
    """Schedule a meeting via calendar integration.
    # TODO: integrate with Calendly / Cal.com / Chili Piper API
    """
    return json.dumps({"meeting_id": f"mtg_{hash(topic) % 10000}", "attendees": attendees, "topic": topic, "duration": duration_min, "status": "scheduled", "time": preferred_time or "2026-02-25T14:00:00Z"})
''',
    "get_calendar_availability": '''
async def get_calendar_availability(email: str, date_range: str = "next_7_days") -> str:
    """Check calendar availability for scheduling.
    # TODO: integrate with Google Calendar / Outlook API
    """
    return json.dumps({"email": email, "available_slots": ["2026-02-25T10:00", "2026-02-25T14:00", "2026-02-26T09:00"], "timezone": "UTC"})
''',
    "enrich_contact": '''
async def enrich_contact(email_or_company: str) -> str:
    """Enrich contact/company data with firmographics, tech stack, social profiles.
    # TODO: integrate with Clearbit / ZoomInfo / Apollo API
    """
    h = abs(hash(email_or_company))
    if "@" in email_or_company:
        domain = email_or_company.split("@")[1].split(".")[0].capitalize()
        company = f"{domain} Corp"
    else:
        company = email_or_company
    titles = ["VP Sales", "CTO", "Director of Engineering", "Head of Marketing", "CEO", "COO"]
    industries = ["SaaS", "FinTech", "HealthTech", "E-commerce", "Cybersecurity", "EdTech"]
    stacks = [["Salesforce","Slack","AWS"], ["HubSpot","Teams","GCP"], ["Pipedrive","Zoom","Azure"], ["Close.io","Discord","Heroku"]]
    contact_name = email_or_company.split("@")[0].replace("."," ").title() if "@" in email_or_company else f"{company} Contact"
    return json.dumps({"email": email_or_company, "name": contact_name, "company": company, "title": titles[h%len(titles)], "industry": industries[h%len(industries)], "employees": [50,250,500,1200,3000][h%5], "revenue": ["$5M","$25M","$50M","$120M","$500M"][h%5], "tech_stack": stacks[h%len(stacks)], "linkedin": f"https://linkedin.com/in/{email_or_company.split(chr(64))[0] if chr(64) in email_or_company else email_or_company.lower().replace(chr(32),chr(45))}"})
''',
    "fetch_linkedin_profile": '''
async def fetch_linkedin_profile(linkedin_url_or_name: str) -> str:
    """Fetch LinkedIn profile data for prospect research.
    # TODO: integrate with LinkedIn Sales Navigator / Heyreach API
    """
    h = abs(hash(linkedin_url_or_name))
    query = linkedin_url_or_name.strip("/").split("/")[-1].replace("-"," ").title() if "/" in linkedin_url_or_name else linkedin_url_or_name
    names = ["John Doe","Sarah Chen","Michael Brooks","Lisa Kumar","David Martinez","Emma Wilson"]
    titles = ["VP Engineering","Director of Sales","CTO","Head of Product","SVP Operations","Chief Revenue Officer"]
    posts_pool = [["Excited about AI trends...","Just launched our new platform"],["Hiring for 3 senior roles","Thoughts on sales automation"]]
    i = h % len(names)
    return json.dumps({"url": linkedin_url_or_name, "name": query, "title": titles[i], "company": query, "connections": [320,500,750,1200,2500][h%5], "recent_posts": posts_pool[i % len(posts_pool)]})
''',
    "search_competitors": '''
async def search_competitors(company: str, product: str = "") -> str:
    """Research competitor information and market positioning.
    # TODO: integrate with Crayon / Klue / Kompyte API
    """
    h = abs(hash(company))
    comp_sets = [
        [{"name":"Salesforce","market_share":"32%","pricing":"$150/user/mo"},{"name":"HubSpot","market_share":"18%","pricing":"$45/user/mo"}],
        [{"name":"Gong","market_share":"28%","pricing":"$100/user/mo"},{"name":"Chorus.ai","market_share":"12%","pricing":"$80/user/mo"}],
    ]
    i = h % len(comp_sets)
    return json.dumps({"company": company, "competitors": comp_sets[i]})
''',
    "analyze_intent_signals": '''
async def analyze_intent_signals(company: str) -> str:
    """Detect buying intent signals for a company.
    # TODO: integrate with Bombora / G2 / TrustRadius API
    """
    h = abs(hash(company))
    scores = [45, 62, 78, 84, 91]
    signals_pool = [
        ["Researching CRM tools","Visited pricing page","Downloaded whitepaper"],
        ["Hiring SDRs","Evaluating sales engagement platforms","G2 comparison activity"],
    ]
    i = h % len(scores)
    return json.dumps({"company": company, "intent_score": scores[i], "signals": signals_pool[i % len(signals_pool)]})
''',
    "score_lead": '''
async def score_lead(contact_data: str, scoring_model: str = "icp_v1") -> str:
    """Score a lead using ICP model. Returns score 0-100 and qualification status.
    # TODO: integrate with MadKudu / custom scoring model
    """
    h = abs(hash(contact_data))
    scores = [42, 58, 67, 72, 81, 89, 95]
    quals = ["Disqualified", "Cold", "MQL", "MQL", "SQL", "SQL", "Enterprise"]
    s = scores[h % len(scores)]
    return json.dumps({"score": s, "model": scoring_model, "qualification": quals[h % len(quals)]})
''',
    "assess_icp_fit": '''
async def assess_icp_fit(company_data: str) -> str:
    """Assess how well a company fits the Ideal Customer Profile.
    # TODO: integrate with enrichment data + ICP model
    """
    h = abs(hash(company_data))
    tiers = ["A", "A", "B", "B", "C", "D"]
    scores = [92, 85, 74, 68, 55, 38]
    i = h % len(tiers)
    return json.dumps({"fit_score": scores[i], "tier": tiers[i], "recommendation": "Proceed" if scores[i] > 60 else "Deprioritize"})
''',
    "qualify_bant": '''
async def qualify_bant(contact_id: str, budget: str = "", authority: str = "", need: str = "", timeline: str = "") -> str:
    """Run BANT qualification framework on a prospect.
    # TODO: integrate with CRM data + call intelligence
    """
    h = abs(hash(contact_id))
    statuses = ["Fully Qualified", "Partially Qualified", "Needs Nurturing", "Fully Qualified", "Disqualified"]
    return json.dumps({"contact_id": contact_id, "bant": {"budget": budget or "$50k-100k", "authority": authority or "Decision Maker", "need": need or "Active pain point", "timeline": timeline or "This quarter"}, "overall": statuses[h % len(statuses)]})
''',
    "analyze_call_transcript": '''
async def analyze_call_transcript(transcript: str, analysis_type: str = "full") -> str:
    """Analyze a sales call transcript for insights.
    # TODO: integrate with Gong.io / Fireflies.ai API
    """
    h = abs(hash(transcript[:100]))
    sentiments = ["positive","neutral","mixed","cautious","enthusiastic"]
    i = h % len(sentiments)
    return json.dumps({"analysis_type": analysis_type, "sentiment": sentiments[i], "key_topics": ["pricing","implementation"], "next_steps": ["Send proposal","Schedule follow-up"]})
''',
    "extract_action_items": '''
async def extract_action_items(transcript: str) -> str:
    """Extract action items from meeting notes or call transcript."""
    return json.dumps({"action_items": [{"owner":"rep","task":"Send pricing proposal","deadline":"2026-02-26"},{"owner":"prospect","task":"Review with team","deadline":"2026-02-28"}]})
''',
    "generate_report": '''
async def generate_report(report_type: str, data: str, format: str = "markdown") -> str:
    """Generate a structured report (pipeline, performance, competitive)."""
    report = f"# {report_type.replace('_', ' ').title()} Report\\n\\nGenerated: 2026-02-24\\n\\n## Summary\\n{data[:500]}\\n"
    path = OUTPUT_DIR / f"{report_type}_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return f"Report written to {path} ({len(report)} chars)"
''',
    "translate_text": '''
async def translate_text(text: str, target_language: str) -> str:
    """Translate text to target language for multilingual outreach."""
    return json.dumps({"original": text[:200], "translated": f"[{target_language}] {text[:200]}", "language": target_language, "confidence": 0.95})
''',
    "generate_email_copy": '''
async def generate_email_copy(prospect_data: str, template_type: str = "cold_outreach", language: str = "English") -> str:
    """Generate personalized email copy for outreach."""
    h = abs(hash(prospect_data + template_type))
    subjects = [f"Quick question about {template_type}", f"Idea for your team"]
    bodies = ["Hi,\\n\\nI noticed your company is growing rapidly. Would love to connect.\\n\\nBest", "Hi,\\n\\nAfter researching your team, I believe we could help.\\n\\nCheers"]
    return json.dumps({"subject": subjects[h%len(subjects)], "body": bodies[h%len(bodies)], "template": template_type, "language": language})
''',
    "create_battle_card": '''
async def create_battle_card(competitor: str, data: str = "") -> str:
    """Generate a competitive battle card for sales reps."""
    card = f"# Battle Card: vs {competitor}\\n\\n## Our Strengths\\n- AI-powered\\n- Fast onboarding\\n\\n## Their Weaknesses\\n- Legacy tech\\n"
    path = OUTPUT_DIR / f"battle_card_{competitor.lower().replace(' ', '_')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card, encoding="utf-8")
    return f"Battle card written to {path}"
''',
    "create_video_message": '''
async def create_video_message(recipient: str, topic: str, script: str = "") -> str:
    """Create a personalized video message for prospect outreach."""
    return json.dumps({"recipient": recipient, "topic": topic, "video_id": f"vid_{hash(recipient) % 10000}", "status": "created"})
''',
    "validate_json": '''
async def validate_json(data: str) -> str:
    """Validate JSON data structure and return analysis."""
    try:
        parsed = json.loads(data)
        return json.dumps({"valid": True, "type": type(parsed).__name__, "keys": list(parsed.keys()) if isinstance(parsed, dict) else None})
    except json.JSONDecodeError as e:
        return json.dumps({"valid": False, "error": str(e)})
''',
    "read_file": '''
async def read_file(filepath: str) -> str:
    """Read a file from the filesystem. Returns file content."""
    path = Path(filepath)
    if not path.exists():
        return f"Error: File not found: {filepath}"
    return path.read_text(encoding="utf-8", errors="replace")[:5000]
''',
    "write_report": '''
async def write_report(filename: str, content: str) -> str:
    """Write a report file to the output directory."""
    path = OUTPUT_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {path}"
''',
    "query_data_warehouse": '''
async def query_data_warehouse(query: str, source: str = "default") -> str:
    """Query the data warehouse for analytics data."""
    return json.dumps({"query": query[:200], "source": source, "rows": 42, "columns": ["metric", "value", "date"], "sample": [{"metric": "pipeline_value", "value": 1250000, "date": "2026-02-24"}]})
''',
    "check_system_health": '''
async def check_system_health(service: str = "all") -> str:
    """Check system health and operational metrics."""
    return json.dumps({"service": service, "status": "healthy", "uptime": "99.9%", "response_time_ms": 45})
''',
    "send_slack_message": '''
async def send_slack_message(channel: str, message: str) -> str:
    """Send a message to a Slack channel."""
    return json.dumps({"channel": channel, "sent": True, "timestamp": "2026-02-24T10:00:00Z"})
''',
    "claude_code": '''
async def claude_code(task: str, code: str = "", files: str = "", output_file: str = "") -> str:
    """Delegate a task to an AI assistant (LLM). Can generate content AND write it to a file.
    Use this to: write reports, generate markdown files, write code, analyze data,
    draft documentation, or any complex reasoning/generation task.
    Args:
        task: Description of what the AI should do
        code: Optional code to review/refactor/extend
        files: Optional comma-separated file paths for context
        output_file: Optional filename to write result to (e.g. '01_branch_strategy.md').
                     File is written to /app/output/<output_file>. Returns path on success.
    Returns: AI response text, or file path if output_file was specified."""
    parts = [task]
    if code:
        parts.append(f"\\n\\nCODE:\\n```\\n{code}\\n```")
    if files:
        parts.append(f"\\n\\nRelevant files: {files}")
    full_prompt = "\\n".join(parts)
    result_text = None
    _oai_key = os.environ.get("OPENAI_API_KEY", "")
    _oai_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    _oai_model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    if _oai_key:
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=120) as _client:
                for _params in [{"max_completion_tokens": 4000}, {"max_tokens": 4000}]:
                    _resp = await _client.post(
                        f"{_oai_base.rstrip(\'/\')}/chat/completions",
                        headers={"Authorization": f"Bearer {_oai_key}", "Content-Type": "application/json"},
                        json={"model": _oai_model, "messages": [
                            {"role": "system", "content": "You are an expert AI assistant. Produce complete, high-quality output."},
                            {"role": "user", "content": full_prompt}
                        ], **_params},
                    )
                    if _resp.status_code == 200:
                        result_text = _resp.json()["choices"][0]["message"]["content"].strip()
                        break
        except Exception:
            pass
    if not result_text:
        return "Error: claude_code failed — OPENAI_API_KEY not set or API unreachable"
    if output_file:
        _out_dir = Path("/app/output") if Path("/app").exists() else Path("output")
        _out_dir.mkdir(exist_ok=True)
        _out_path = _out_dir / output_file
        _out_path.parent.mkdir(parents=True, exist_ok=True)
        _out_path.write_text(result_text, encoding="utf-8")
        return f"Written {len(result_text)} chars to {_out_path}"
    return result_text
''',
}

# ── Real tool templates using httpx — used when env vars are available ────────
# Each returns JSON with "mock": false on success.
# Falls back to mock if API key not set.
REAL_TOOL_TEMPLATES = {
    "score_lead": '''
async def score_lead(company: str, title: str, industry: str = "", employee_count: int = 0) -> str:
    """Score a lead against ICP using algorithmic scoring (no API needed).
    Returns JSON with score 0-100 and breakdown.
    """
    score = 50
    breakdown = {}
    # Title seniority scoring
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["ceo", "cto", "cfo", "vp", "president", "chief"]):
        score += 25; breakdown["seniority"] = "C-level/VP (+25)"
    elif any(kw in title_lower for kw in ["director", "head", "senior"]):
        score += 15; breakdown["seniority"] = "Director/Senior (+15)"
    elif any(kw in title_lower for kw in ["manager", "lead"]):
        score += 10; breakdown["seniority"] = "Manager (+10)"
    else:
        breakdown["seniority"] = "Individual contributor (+0)"
    # Company size scoring
    if employee_count >= 1000:
        score += 15; breakdown["company_size"] = "Enterprise (+15)"
    elif employee_count >= 100:
        score += 10; breakdown["company_size"] = "Mid-market (+10)"
    elif employee_count > 0:
        score += 5; breakdown["company_size"] = "SMB (+5)"
    # Industry fit
    high_value = ["technology", "software", "saas", "fintech", "healthcare", "finance"]
    if any(ind in industry.lower() for ind in high_value):
        score += 10; breakdown["industry"] = f"{industry} — high value (+10)"
    return json.dumps({"score": min(score, 100), "breakdown": breakdown, "company": company, "mock": False})
''',

    "send_slack_message": '''
async def send_slack_message(channel: str, message: str) -> str:
    """Send a Slack message via webhook or API.
    Set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN env var for real delivery.
    """
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    if webhook:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook, json={"text": f"[#{channel}] {message}"})
            if resp.status_code == 200:
                return json.dumps({"sent": True, "channel": channel, "mock": False})
            return json.dumps({"error": f"Slack webhook returned {resp.status_code}", "mock": True})
    elif bot_token:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={"channel": channel, "text": message})
            data = resp.json()
            if data.get("ok"):
                return json.dumps({"sent": True, "channel": channel, "ts": data.get("ts"), "mock": False})
            return json.dumps({"error": data.get("error", "unknown"), "mock": True})
    return json.dumps({"sent": True, "channel": channel, "message_preview": message[:100], "mock": True,
                        "note": "Set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN for real delivery"})
''',

    "send_email": '''
async def send_email(to: str, subject: str, body: str, from_email: str = "") -> str:
    """Send email via Resend API.
    Set RESEND_API_KEY env var for real delivery.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if api_key:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"from": from_email or "noreply@example.com", "to": [to],
                      "subject": subject, "text": body})
            if resp.status_code in (200, 201):
                data = resp.json()
                return json.dumps({"sent": True, "id": data.get("id"), "to": to, "mock": False})
            return json.dumps({"error": f"Resend API returned {resp.status_code}", "mock": True})
    return json.dumps({"sent": True, "to": to, "subject": subject, "mock": True,
                        "note": "Set RESEND_API_KEY for real delivery"})
''',

    "search_competitors": '''
async def search_competitors(company: str, industry: str = "") -> str:
    """Search for competitor intelligence via SerpAPI or web search.
    Set SERPAPI_KEY env var for real search results.
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if api_key:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://serpapi.com/search", params={
                "api_key": api_key, "q": f"{company} competitors {industry}",
                "engine": "google", "num": 5})
            if resp.status_code == 200:
                data = resp.json()
                results = [{"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link")}
                           for r in data.get("organic_results", [])[:5]]
                return json.dumps({"company": company, "competitors": results, "mock": False})
    # Fallback mock
    return json.dumps({"company": company, "competitors": [
        {"name": f"{company}Rival1", "strength": "Market leader", "weakness": "Higher pricing"},
        {"name": f"{company}Rival2", "strength": "Better UX", "weakness": "Smaller team"},
    ], "mock": True, "note": "Set SERPAPI_KEY for real competitor data"})
''',

    "check_email_deliverability": '''
async def check_email_deliverability(email: str) -> str:
    """Check email deliverability via ZeroBounce API.
    Set ZEROBOUNCE_API_KEY env var for real validation.
    """
    api_key = os.environ.get("ZEROBOUNCE_API_KEY")
    if api_key:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://api.zerobounce.net/v2/validate", params={
                "api_key": api_key, "email": email})
            if resp.status_code == 200:
                data = resp.json()
                return json.dumps({"email": email, "status": data.get("status"),
                                    "sub_status": data.get("sub_status"),
                                    "deliverable": data.get("status") == "valid", "mock": False})
    # Fallback
    domain = email.split("@")[-1] if "@" in email else "unknown"
    return json.dumps({"email": email, "deliverable": True, "score": 85,
                        "domain": domain, "spf": True, "dkim": True, "dmarc": True,
                        "mock": True, "note": "Set ZEROBOUNCE_API_KEY for real validation"})
''',
}


async def review_tool_assignments(agents: dict) -> dict:
    """Let user review and modify tool assignments via the question modal."""
    agent_data = {}
    for name, info in agents.items():
        tools = info.get("tools", info.get("domain_tools", []))
        role = "manager" if any(kw in name.lower() for kw in ["manager", "lead", "vp", "cso", "director"]) else "specialist"
        agent_data[name] = {"tools": tools, "role": role}

    available = list(SALES_TOOL_IMPLEMENTATIONS.keys())

    answer = await ask_user(
        question_type="tool_assignment",
        tool_name="InputParser",
        message="Review tool assignments for agents",
        metadata={"agents": agent_data, "available_tools": available},
        timeout=60,
    )

    if answer["action"] == "reply" and answer["text"]:
        try:
            user_assignments = json.loads(answer["text"])
            user_agents = user_assignments.get("agents", {})
            for name, tools in user_agents.items():
                if name in agents and isinstance(tools, list):
                    if "tools" in agents[name]:
                        agents[name]["tools"] = tools
                    elif "domain_tools" in agents[name]:
                        agents[name]["domain_tools"] = tools
            print(f"[InputParser] User adjusted tool assignments for {len(user_agents)} agents")
        except (json.JSONDecodeError, KeyError):
            pass

    return agents


def generate_sales_tools_py(agents: dict) -> str:
    """Generate tools.py preferring real templates over mocks.

    Selection order per tool:
    1. REAL_TOOL_TEMPLATES — httpx-based, uses env vars, returns mock:false
    2. SALES_TOOL_IMPLEMENTATIONS — hash-based mocks with TODO markers
    3. Generic stub — catch-all for unknown tools
    """
    all_tools = set()
    for info in agents.values():
        for tool in info.get("tools", info.get("domain_tools", [])):
            all_tools.add(tool)

    all_tools.update(["write_report", "read_file", "claude_code"])

    real_count = 0
    mock_count = 0

    code = '"""Auto-generated sales domain tools.\n\n'
    code += 'Tools with real API integration will use env vars (e.g., RESEND_API_KEY).\n'
    code += 'Tools without API keys fall back to mock responses marked with "mock": true.\n'
    code += '"""\n'
    code += 'import asyncio\n'
    code += 'import json\n'
    code += 'import os\n'
    code += 'from pathlib import Path\n\n'
    code += 'OUTPUT_DIR = Path("/app/output") if Path("/app").exists() else Path("output")\n'
    code += 'OUTPUT_DIR.mkdir(exist_ok=True)\n\n'

    for tool_name in sorted(all_tools):
        # Prefer real template over mock
        if tool_name in REAL_TOOL_TEMPLATES:
            code += REAL_TOOL_TEMPLATES[tool_name].strip() + "\n\n"
            real_count += 1
        elif tool_name in SALES_TOOL_IMPLEMENTATIONS:
            code += SALES_TOOL_IMPLEMENTATIONS[tool_name].strip() + "\n\n"
            mock_count += 1
        else:
            code += f'async def {tool_name}(query: str = "") -> str:\n'
            code += f'    """Execute {tool_name} operation.\n'
            code += f'    # TODO: implement {tool_name}\n'
            code += f'    """\n'
            code += f'    return json.dumps({{"tool": "{tool_name}", "status": "mock", "mock": True, "query": query[:500]}})\n\n'
            mock_count += 1

    print(f"[ToolGen] {real_count} real templates, {mock_count} mocks out of {len(all_tools)} total tools")
    return code


# ═══════════════════════════════════════════════════════════════════════════════
#  WIRING GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_wiring_tools(sub_team_dirs: dict, manifest: dict) -> str:
    """Generate async CLI wiring tool functions for the core team.

    Each function invokes a sub-team's Docker project via async subprocess:
      docker compose run --rm app python main.py '<task>'

    Uses relative paths so the code works both on host and inside containers.
    """
    code = "\n# ═══ CLI Wiring — Sub-team invocation tools (async) ═══\n\n"
    code += "import asyncio as _asyncio\n"
    code += "from pathlib import Path as _Path\n\n"
    code += "# Resolve sub-team dirs relative to this project's parent\n"
    code += "_WIRING_BASE = _Path(__file__).parent.parent.parent\n\n"

    for team_key, output_dir in sub_team_dirs.items():
        team_info = manifest["sub_teams"].get(team_key, {})
        manager = team_info.get("manager", team_key)
        specialist_names = list(team_info.get("agents", {}).keys())
        func_name = f"run_{team_key}_team"

        # Calculate relative dir name (just the folder name, not full path)
        rel_dir = Path(output_dir).name

        code += f'async def {func_name}(task: str) -> str:\n'
        code += f'    """Invoke the {manager}\'s sub-team via async Docker CLI.\n'
        code += f'    Specialists: {", ".join(specialist_names)}\n'
        code += f'    """\n'
        code += f'    subteam_path = _WIRING_BASE / "{rel_dir}"\n'
        code += f'    if not subteam_path.exists():\n'
        code += f'        return f"ERROR: Sub-team directory not found: {{subteam_path}}"\n'
        code += f'    try:\n'
        code += f'        proc = await _asyncio.create_subprocess_exec(\n'
        code += f'            "docker", "compose", "run", "--rm", "app", "python", "main.py", task,\n'
        code += f'            cwd=str(subteam_path),\n'
        code += f'            stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.STDOUT\n'
        code += f'        )\n'
        code += f'        try:\n'
        code += f'            stdout, _ = await _asyncio.wait_for(proc.communicate(), timeout=300)\n'
        code += f'            output = stdout.decode()[-3000:] if proc.returncode == 0 else f"ERROR: {{stdout.decode()[-1000:]}}"\n'
        code += f'            return output\n'
        code += f'        except _asyncio.TimeoutError:\n'
        code += f'            proc.kill()\n'
        code += f'            return "ERROR: Sub-team execution timed out after 300s"\n'
        code += f'    except Exception as e:\n'
        code += f'        return f"ERROR: {{e}}"\n\n'

    return code


def get_wiring_tool_names(manifest: dict) -> list:
    """Return list of all wiring tool function names."""
    return [f"run_{key}_team" for key in manifest["sub_teams"]]

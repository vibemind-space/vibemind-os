"""InputDesignPipeline — 5-agent pipeline that generates input.md from a task description.

Flow: DomainResearcher → TechStackSpecialist → OrgArchitect → InputReviewer → InputWriter

User interaction happens at TechStack and OrgArchitect steps via Minibook comments.
"""

import asyncio
import json
import os
import time
import webbrowser
from pathlib import Path

from .constants import MINIBOOK_URL, OUTPUT_DIR, POLL_INTERVAL, STEP_TIMEOUT
from .knowledge import INPUT_DESIGN_ROLES, INPUT_DESIGN_FLOW
from .api_client import api_post, api_get
from .llm import call_gpt4o, call_gpt4o_json


# User feedback timeout (seconds) — auto-proceed after this
USER_FEEDBACK_TIMEOUT = 120
MINIBOOK_FRONTEND_URL = os.environ.get("MINIBOOK_FRONTEND_URL", "http://localhost:3457")


class InputDesignPipeline:
    """5-agent pipeline that generates input.md from a task description."""

    def __init__(self, agents: dict, project_id: str, task_description: str):
        self.agents = agents
        self.project_id = project_id
        self.task = task_description
        self.start_time = time.time()

        # Pipeline state
        self.domain_analysis = None
        self.tech_stack = None
        self.org_design = None
        self.review_result = None
        self.final_input_path = None
        self.completed_steps = set()

    def key(self, agent_name: str) -> str:
        """Get agent API key."""
        return self.agents[agent_name]["api_key"]

    async def post_as(self, session, agent_name, title, content,
                      post_type="discussion", tags=None):
        """Create a post as a specific agent."""
        return await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {"title": title, "content": content, "type": post_type, "tags": tags or []},
            api_key=self.key(agent_name),
        )

    async def comment_as(self, session, agent_name, post_id, content):
        """Add a comment as a specific agent."""
        return await api_post(
            session,
            f"/api/v1/posts/{post_id}/comments",
            {"content": content},
            api_key=self.key(agent_name),
        )

    async def poll_mention(self, session, agent_name, timeout=None):
        """Poll for @mention notifications."""
        api_key = self.key(agent_name)
        start = time.time()
        timeout = timeout or STEP_TIMEOUT

        while time.time() - start < timeout:
            try:
                notifications = await api_get(
                    session, "/api/v1/notifications",
                    api_key=api_key, params={"unread_only": "true"}
                )
                for notif in notifications:
                    if notif["type"] == "mention" and not notif["read"]:
                        post_id = notif.get("payload", {}).get("post_id")
                        comment_id = notif.get("payload", {}).get("comment_id")
                        await api_post(session, f"/api/v1/notifications/{notif['id']}/read",
                                       {}, api_key=api_key)
                        if comment_id:
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            comments = await api_get(session, f"/api/v1/posts/{post_id}/comments")
                            comment_content = ""
                            for c in comments:
                                if c["id"] == comment_id:
                                    comment_content = c["content"]
                                    break
                            return {"post": post, "comment": comment_content, "post_id": post_id}
                        elif post_id:
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            return {"post": post, "comment": None, "post_id": post_id}
            except Exception as e:
                print(f"  [{agent_name}] Poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)
        return None

    async def poll_user_feedback(self, session, post_id, timeout=USER_FEEDBACK_TIMEOUT):
        """Poll a post for new user comments. Returns comment text or None on timeout."""
        start = time.time()
        seen_comments = set()

        # Auto-open the post in the browser so user can review and comment
        try:
            post_url = f"{MINIBOOK_FRONTEND_URL}/post/{post_id}"
            webbrowser.open(post_url)
            print(f"  [Browser] Opened: {post_url}")
        except Exception:
            pass

        # Record existing comments
        try:
            existing = await api_get(session, f"/api/v1/posts/{post_id}/comments")
            for c in existing:
                seen_comments.add(c["id"])
        except Exception:
            pass

        while time.time() - start < timeout:
            await asyncio.sleep(3)
            try:
                comments = await api_get(session, f"/api/v1/posts/{post_id}/comments")
                for c in comments:
                    if c["id"] not in seen_comments:
                        # New comment found
                        text = c.get("content", "").strip()
                        author = c.get("author", {}).get("name", "user")
                        # Skip comments from our own agents
                        if author in INPUT_DESIGN_ROLES:
                            seen_comments.add(c["id"])
                            continue
                        print(f"  [User feedback] {author}: {text[:100]}")
                        return text
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Step 1: Domain Research
    # ------------------------------------------------------------------
    async def step_domain_research(self, session):
        """DomainResearcher: Analyze domain from task description."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[DomainResearcher] Analyzing domain... ({elapsed()})")

        prompt = INPUT_DESIGN_ROLES["DomainResearcher"]["prompt"]
        result = await call_gpt4o_json(
            prompt,
            f"Task description: {self.task}\n\nAnalyze this and produce the structured domain analysis.",
            max_tokens=2048
        )
        self.domain_analysis = result
        print(f"  [DomainResearcher] Domain: {result.get('industry', '?')}, "
              f"~{result.get('agent_count', '?')} agents, "
              f"~{result.get('team_count', '?')} teams")

        # Post to Minibook
        analysis_text = (
            f"## Domain Analysis\n\n"
            f"**Task:** {self.task}\n\n"
            f"**Industry:** {result.get('industry', 'Unknown')}\n"
            f"**Org Name:** {result.get('org_name', 'AgentOrg')}\n"
            f"**Estimated Size:** ~{result.get('agent_count', '?')} agents, "
            f"~{result.get('team_count', '?')} teams\n\n"
            f"### Workflows\n"
            + "\n".join(f"- {w}" for w in result.get("workflows", [])) + "\n\n"
            f"### Required Capabilities\n"
            + "\n".join(f"- {c}" for c in result.get("capabilities", [])) + "\n\n"
            f"### Constraints\n"
            + "\n".join(f"- {c}" for c in result.get("constraints", [])) + "\n\n"
            f"@TechStackSpecialist — domain analysis complete, map the tech stack."
        )
        await self.post_as(session, "DomainResearcher",
                           f"Domain Analysis: {result.get('industry', 'Unknown')}",
                           analysis_text, tags=["domain", "research", "input-design"])

        self.completed_steps.add("DomainResearcher")
        print(f"  [DomainResearcher] DONE ({elapsed()})")

    # ------------------------------------------------------------------
    # Step 2: Tech Stack
    # ------------------------------------------------------------------
    async def step_tech_stack(self, session):
        """TechStackSpecialist: Map capabilities to tools."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[TechStackSpecialist] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "TechStackSpecialist")
        if not trigger:
            print("[TechStackSpecialist] TIMEOUT")
            return

        prompt = INPUT_DESIGN_ROLES["TechStackSpecialist"]["prompt"]
        context = (
            f"Domain analysis:\n{json.dumps(self.domain_analysis, indent=2)}\n\n"
            f"Original task: {self.task}\n\n"
            f"Map the capabilities to concrete tools."
        )
        result = await call_gpt4o_json(prompt, context, max_tokens=2048)
        self.tech_stack = result

        # Format tool table for Minibook
        tool_lines = ["| Agent Role | Tools |", "|------------|-------|"]
        for role, tools in result.get("tool_assignments", {}).items():
            tool_lines.append(f"| {role} | {', '.join(tools)} |")

        custom = result.get("custom_tools", [])
        mcp = result.get("mcp_servers", [])
        platforms = result.get("platforms", {})

        tech_post = (
            f"## Proposed Tech Stack\n\n"
            + "\n".join(tool_lines) + "\n\n"
            + (f"### Custom Tools (new)\n" + "\n".join(f"- `{t}`" for t in custom) + "\n\n" if custom else "")
            + (f"### MCP Servers\n" + "\n".join(f"- {s}" for s in mcp) + "\n\n" if mcp else "")
            + (f"### Recommended Platforms\n" + "\n".join(f"- **{k}**: {v}" for k, v in platforms.items()) + "\n\n" if platforms else "")
            + "---\n"
            + "**Please review.** Comment with changes or reply 'ok' to proceed.\n"
            + f"(Auto-proceeding in {USER_FEEDBACK_TIMEOUT}s if no response)\n"
        )
        post = await self.post_as(session, "TechStackSpecialist",
                                  "Tech Stack Proposal",
                                  tech_post, tags=["techstack", "input-design"])
        post_id = post.get("id", "")

        # Wait for user feedback
        print(f"  [TechStackSpecialist] Waiting for user feedback ({USER_FEEDBACK_TIMEOUT}s)...")
        feedback = await self.poll_user_feedback(session, post_id)

        if feedback and feedback.lower() not in ("ok", "lgtm", "proceed", "yes", "gut", "passt"):
            # User gave changes — re-run with feedback
            print(f"  [TechStackSpecialist] Incorporating feedback: {feedback[:80]}")
            revision_ctx = (
                f"Previous tech stack:\n{json.dumps(result, indent=2)}\n\n"
                f"User feedback: {feedback}\n\n"
                f"Revise the tech stack based on feedback."
            )
            result = await call_gpt4o_json(prompt, revision_ctx, max_tokens=2048)
            self.tech_stack = result
            await self.comment_as(session, "TechStackSpecialist", post_id,
                                  f"Updated tech stack based on feedback.\n\n"
                                  f"@OrgArchitect — tech stack finalized, design the org.")
        else:
            await self.comment_as(session, "TechStackSpecialist", post_id,
                                  f"Tech stack confirmed.\n\n"
                                  f"@OrgArchitect — tech stack finalized, design the org.")

        self.completed_steps.add("TechStackSpecialist")
        print(f"  [TechStackSpecialist] DONE ({elapsed()})")

    # ------------------------------------------------------------------
    # Step 3: Org Architect
    # ------------------------------------------------------------------
    async def step_org_architect(self, session, revision_feedback=None):
        """OrgArchitect: Design agent hierarchy."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"

        if not revision_feedback:
            print(f"\n[OrgArchitect] Waiting for @mention... ({elapsed()})")
            trigger = await self.poll_mention(session, "OrgArchitect")
            if not trigger:
                print("[OrgArchitect] TIMEOUT")
                return

        prompt = INPUT_DESIGN_ROLES["OrgArchitect"]["prompt"]
        context = (
            f"Domain analysis:\n{json.dumps(self.domain_analysis, indent=2)}\n\n"
            f"Tech stack:\n{json.dumps(self.tech_stack, indent=2)}\n\n"
            f"Original task: {self.task}\n\n"
        )
        if revision_feedback:
            context += f"REVISION REQUESTED. Feedback:\n{revision_feedback}\n\nRevise the org design."
        else:
            context += "Design the agent organization."

        result = await call_gpt4o_json(prompt, context, max_tokens=4096)
        self.org_design = result

        # Build ASCII tree
        org_name = result.get("org_name", "AgentOrg")
        exec_info = result.get("executive", {})
        exec_name = exec_info.get("name", "LeadAgent")
        tree_lines = [f"  {exec_name} (executive)"]
        for tk, team in result.get("teams", {}).items():
            mgr = team.get("manager", tk)
            tree_lines.append(f"  ├── {mgr} ({tk} team)")
            specialists = team.get("specialists", [])
            for i, spec in enumerate(specialists):
                prefix = "│   └──" if i == len(specialists) - 1 else "│   ├──"
                tree_lines.append(f"  {prefix} {spec.get('name', '?')}")

        total_agents = 1 + sum(1 + len(t.get("specialists", [])) for t in result.get("teams", {}).values())

        org_post = (
            f"## Proposed Agent Organization: {org_name}\n\n"
            f"**Total agents:** {total_agents}\n\n"
            f"```\n" + "\n".join(tree_lines) + "\n```\n\n"
            f"### Teams\n\n"
        )
        for tk, team in result.get("teams", {}).items():
            specs = team.get("specialists", [])
            org_post += f"**{tk}** — {team.get('manager', '?')} + {len(specs)} specialists\n"
            for s in specs:
                org_post += f"  - {s.get('name', '?')}: {s.get('purpose', '')}\n"
            org_post += "\n"

        org_post += (
            "---\n"
            "**Please review.** Comment with changes or reply 'ok' to proceed.\n"
            f"(Auto-proceeding in {USER_FEEDBACK_TIMEOUT}s if no response)\n"
        )

        post = await self.post_as(session, "OrgArchitect",
                                  f"Org Design: {org_name}",
                                  org_post, tags=["org", "architecture", "input-design"])
        post_id = post.get("id", "")

        # Wait for user feedback
        print(f"  [OrgArchitect] Waiting for user feedback ({USER_FEEDBACK_TIMEOUT}s)...")
        feedback = await self.poll_user_feedback(session, post_id)

        if feedback and feedback.lower() not in ("ok", "lgtm", "proceed", "yes", "gut", "passt"):
            print(f"  [OrgArchitect] Incorporating feedback: {feedback[:80]}")
            # Revise org with feedback (max 1 revision to avoid loops)
            revision_ctx = (
                f"Previous org design:\n{json.dumps(result, indent=2)}\n\n"
                f"User feedback: {feedback}\n\n"
                f"Revise the org design based on feedback."
            )
            result = await call_gpt4o_json(prompt, revision_ctx, max_tokens=4096)
            self.org_design = result
            await self.comment_as(session, "OrgArchitect", post_id,
                                  f"Updated org design based on feedback.\n\n"
                                  f"@InputReviewer — org finalized, validate the input spec.")
        else:
            await self.comment_as(session, "OrgArchitect", post_id,
                                  f"Org design confirmed.\n\n"
                                  f"@InputReviewer — org finalized, validate the input spec.")

        self.completed_steps.add("OrgArchitect")
        print(f"  [OrgArchitect] DONE ({elapsed()})")

    # ------------------------------------------------------------------
    # Step 4: Input Reviewer
    # ------------------------------------------------------------------
    async def step_input_reviewer(self, session):
        """InputReviewer: Validate against input.md spec."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[InputReviewer] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "InputReviewer")
        if not trigger:
            print("[InputReviewer] TIMEOUT")
            return

        # Validate org design
        prompt = INPUT_DESIGN_ROLES["InputReviewer"]["prompt"]
        context = (
            f"Org design:\n{json.dumps(self.org_design, indent=2)}\n\n"
            f"Tech stack:\n{json.dumps(self.tech_stack, indent=2)}\n\n"
            f"Domain analysis:\n{json.dumps(self.domain_analysis, indent=2)}\n\n"
            f"Validate this against the input.md specification."
        )
        review = await call_gpt4o(prompt, context, max_tokens=1500)
        self.review_result = review

        is_pass = "PASS" in review.upper() and "NEEDS_REVISION" not in review.upper()

        if is_pass:
            await self.post_as(session, "InputReviewer",
                               "Input Validation: PASS",
                               f"## Validation Result: PASS\n\n{review}\n\n"
                               f"@InputWriter — all checks passed, generate the final input.md.",
                               tags=["review", "pass", "input-design"])
            print(f"  [InputReviewer] PASS ({elapsed()})")
        else:
            await self.post_as(session, "InputReviewer",
                               "Input Validation: NEEDS REVISION",
                               f"## Validation Result: NEEDS REVISION\n\n{review}\n\n"
                               f"@OrgArchitect — please fix the issues above.",
                               tags=["review", "revision", "input-design"])
            print(f"  [InputReviewer] NEEDS_REVISION — requesting OrgArchitect fix ({elapsed()})")
            # One revision cycle
            await self.step_org_architect(session, revision_feedback=review)
            # Re-validate (simplified — just proceed)

        self.completed_steps.add("InputReviewer")
        print(f"  [InputReviewer] DONE ({elapsed()})")

    # ------------------------------------------------------------------
    # Step 5: Input Writer
    # ------------------------------------------------------------------
    async def step_input_writer(self, session):
        """InputWriter: Generate final input.md."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[InputWriter] Generating input.md... ({elapsed()})")

        # Wait for @mention (from reviewer or direct)
        trigger = await self.poll_mention(session, "InputWriter", timeout=180)
        if not trigger:
            print("[InputWriter] TIMEOUT — generating anyway")

        prompt = INPUT_DESIGN_ROLES["InputWriter"]["prompt"]
        context = (
            f"Generate a complete input.md file for the pipeline.\n\n"
            f"IMPORTANT: Start output directly with `# OrgName`. No code fences, no ```markdown wrapper.\n\n"
            f"Original task: {self.task}\n\n"
            f"Domain analysis:\n{json.dumps(self.domain_analysis, indent=2)}\n\n"
            f"Tech stack:\n{json.dumps(self.tech_stack, indent=2)}\n\n"
            f"Org design:\n{json.dumps(self.org_design, indent=2)}\n\n"
            f"Generate the COMPLETE input.md content. Include ALL agents with full "
            f"### Purpose, ### Key Responsibilities, and ### Agent Prompt sections.\n\n"
            f"QUALITY REQUIREMENTS FOR EACH AGENT PROMPT:\n"
            f"- ROLE: AgentName\n"
            f"- [One-line system message in brackets]\n"
            f"- CORE OPERATIONAL FRAMEWORK: must have 8-15 concrete numbered steps.\n"
            f"  Each step must be domain-specific and actionable, NOT generic.\n"
            f"  BAD: '1. Monitor compliance.'\n"
            f"  GOOD: '1. Scan all repositories weekly for branches with no commits in 30+ days. "
            f"Flag stale branches and notify owners via send_slack_message.'\n"
            f"- TOOLS YOU CAN USE: list ONLY domain-relevant tools (2-8 per agent)\n"
            f"- Delegation/reporting instructions\n"
            f"- Write results to /app/output/ INCREMENTALLY\n\n"
            f"TOOL ASSIGNMENT:\n"
            f"- Do NOT give every agent all tools. Executives get 3-5 tools max.\n"
            f"- Managers get their domain tools + claude_code + send_slack_message.\n"
            f"- Specialists get ONLY their 1-3 specific operational tools.\n\n"
            f"Return the FULL markdown content. No wrapping in code fences."
        )

        # Use large token budget for the full input.md
        input_md = await call_gpt4o(prompt, context, max_tokens=16000)

        # Strip markdown code fences if the LLM wrapped the output
        input_md = input_md.strip()
        if input_md.startswith("```"):
            # Remove leading fence (```markdown, ```md, or just ```)
            first_newline = input_md.index("\n") if "\n" in input_md else len(input_md)
            input_md = input_md[first_newline + 1:]
        if input_md.rstrip().endswith("```"):
            input_md = input_md.rstrip()[:-3].rstrip()

        # Ensure last code block is closed (LLM may hit token limit)
        open_fences = input_md.count("```")
        if open_fences % 2 != 0:
            input_md = input_md.rstrip() + "\n```"

        # Write to disk
        output_dir = OUTPUT_DIR / "input_design"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "input.md"
        output_path.write_text(input_md, encoding="utf-8")
        self.final_input_path = output_path

        # Count agents in output
        agent_sections = input_md.count("### Purpose")
        char_count = len(input_md)

        # Post summary to Minibook
        org_name = self.org_design.get("org_name", "AgentOrg") if self.org_design else "AgentOrg"
        await self.post_as(session, "InputWriter",
                           f"Input Generated: {org_name}",
                           f"## Input.md Generated\n\n"
                           f"**File:** `{output_path}`\n"
                           f"**Size:** {char_count:,} characters\n"
                           f"**Agent sections:** {agent_sections}\n\n"
                           f"### Next Step\n"
                           f"```bash\n"
                           f"python minibook/autogen_swarm.py --input-file {output_path}\n"
                           f"```\n\n"
                           f"The pipeline will parse this input.md and generate all agent teams.",
                           tags=["output", "input-design"])

        self.completed_steps.add("InputWriter")
        print(f"  [InputWriter] DONE ({elapsed()}) — {output_path}")
        print(f"  [InputWriter] {agent_sections} agent sections, {char_count:,} chars")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    async def run(self, session) -> Path | None:
        """Run the full InputDesign pipeline."""
        total_start = time.time()
        print(f"\n{'=' * 60}")
        print(f"  INPUT DESIGN PIPELINE")
        print(f"  Task: {self.task[:80]}")
        print(f"  Agents: {', '.join(INPUT_DESIGN_ROLES.keys())}")
        print(f"{'=' * 60}\n")

        await self.step_domain_research(session)
        await self.step_tech_stack(session)
        await self.step_org_architect(session)
        await self.step_input_reviewer(session)
        await self.step_input_writer(session)

        total = time.time() - total_start
        print(f"\n{'=' * 60}")
        print(f"  INPUT DESIGN COMPLETE")
        print(f"  Steps: {len(self.completed_steps)}/5")
        print(f"  Time: {total:.1f}s")
        if self.final_input_path:
            print(f"  Output: {self.final_input_path}")
            print(f"\n  Run pipeline:")
            print(f"  python minibook/autogen_swarm.py --input-file {self.final_input_path}")
        print(f"{'=' * 60}")
        return self.final_input_path

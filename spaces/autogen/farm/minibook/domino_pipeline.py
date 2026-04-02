#!/usr/bin/env python3
"""
Domino Pipeline — 15-Agent Chain Execution via Minibook

Each agent triggers the next via @mentions. The pipeline transforms
a seed task through 15 specialized steps:
  Seed -> Analyze -> Research -> Design -> CodeGen -> Review ->
  Security -> Optimize -> TestGen -> TestRun -> Fix -> Document ->
  Summarize -> Score -> Publish (+ cross-project post)
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import aiohttp
from openai import AsyncOpenAI

# --- Config ---

MINIBOOK_URL = "http://localhost:3456"
AGENT_COUNT = 15
POLL_INTERVAL = 2          # seconds between notification checks
STEP_TIMEOUT = 90          # max seconds to wait for one step
MAX_RETRIES = 3            # retries per step on failure

# Load OpenAI key
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

openai_client = AsyncOpenAI()

# --- Agent Step Definitions ---

STEPS = {
    1:  {"role": "Seed Generator",
         "prompt": "You are the Seed Generator. Create an interesting, concrete coding task. "
                   "Output a clear problem statement with requirements (3-5 bullet points). "
                   "Topic: Build a small CLI tool. Be specific and creative."},
    2:  {"role": "Analyzer",
         "prompt": "You are the Analyzer. Read the coding task below and create a structured analysis: "
                   "1) Key requirements 2) Edge cases 3) Suggested approach. Be concise."},
    3:  {"role": "Researcher",
         "prompt": "You are the Researcher. Based on the analysis, identify relevant design patterns, "
                   "libraries, and best practices. List 3-5 specific recommendations."},
    4:  {"role": "Architect",
         "prompt": "You are the Architect. Design the solution architecture: modules, data flow, "
                   "and interfaces. Output a clear structure with file/class names."},
    5:  {"role": "Code Generator",
         "prompt": "You are the Code Generator. Write the core implementation code based on "
                   "the architecture. Output clean, working Python code."},
    6:  {"role": "Code Reviewer",
         "prompt": "You are the Code Reviewer. Review the code for bugs, logic errors, and "
                   "code quality issues. List findings as PASS/WARN/FAIL with explanations."},
    7:  {"role": "Security Analyst",
         "prompt": "You are the Security Analyst. Analyze the code for security vulnerabilities: "
                   "injection risks, input validation, dependency risks. Rate severity."},
    8:  {"role": "Optimizer",
         "prompt": "You are the Optimizer. Suggest performance improvements: algorithmic efficiency, "
                   "memory usage, I/O optimization. Provide specific refactored snippets."},
    9:  {"role": "Test Generator",
         "prompt": "You are the Test Generator. Write comprehensive unit tests (pytest style) "
                   "covering happy path, edge cases, and error scenarios."},
    10: {"role": "Test Runner",
         "prompt": "You are the Test Runner. Analyze the tests and predict which would pass/fail "
                   "based on the implementation. List expected results and coverage estimate."},
    11: {"role": "Bug Fixer",
         "prompt": "You are the Bug Fixer. Based on all reviews and test predictions, "
                   "fix any identified issues. Output corrected code snippets."},
    12: {"role": "Documenter",
         "prompt": "You are the Documenter. Write clear documentation: module docstring, "
                   "function docs, usage examples, and a brief README section."},
    13: {"role": "Summarizer",
         "prompt": "You are the Summarizer. Create a concise executive summary of the entire "
                   "pipeline: what was built, key decisions, quality assessment."},
    14: {"role": "Scorer",
         "prompt": "You are the Quality Scorer. Rate the final output on these dimensions "
                   "(1-10 each): Code Quality, Security, Performance, Test Coverage, "
                   "Documentation. Provide an overall score and brief justification."},
    15: {"role": "Publisher",
         "prompt": "You are the Publisher. Create the final publication-ready summary. "
                   "Format it nicely with sections: Overview, Implementation, Quality Scores, "
                   "and Conclusion. This is the final output of the pipeline."},
}

# --- Minibook API Helpers ---

async def api_post(session: aiohttp.ClientSession, path: str, data: dict, api_key: str = None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with session.post(f"{MINIBOOK_URL}{path}", json=data, headers=headers) as resp:
        if resp.status >= 400:
            body = await resp.text()
            raise Exception(f"API error {resp.status} on POST {path}: {body}")
        return await resp.json()


async def api_get(session: aiohttp.ClientSession, path: str, api_key: str = None, params: dict = None):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with session.get(f"{MINIBOOK_URL}{path}", headers=headers, params=params) as resp:
        if resp.status >= 400:
            body = await resp.text()
            raise Exception(f"API error {resp.status} on GET {path}: {body}")
        return await resp.json()


# --- Credential Storage ---

CREDS_FILE = Path(__file__).parent / "domino_agents.json"


def load_credentials() -> dict:
    """Load saved agent credentials from disk."""
    if CREDS_FILE.exists():
        return json.loads(CREDS_FILE.read_text())
    return {}


def save_credentials(creds: dict):
    """Save agent credentials to disk."""
    CREDS_FILE.write_text(json.dumps(creds, indent=2))


# --- Registration & Setup ---

async def register_agent(session: aiohttp.ClientSession, name: str, creds: dict) -> dict:
    """Register an agent, or load from saved credentials if already exists."""
    # Check saved credentials first
    if name in creds:
        print(f"  [=] Loaded {name} from saved credentials")
        return creds[name]

    try:
        result = await api_post(session, "/api/v1/agents", {"name": name})
        print(f"  [+] Registered {name} (id={result['id'][:8]}...)")
        creds[name] = result
        save_credentials(creds)
        return result
    except Exception as e:
        if "already taken" in str(e):
            print(f"  [!] {name} exists but no saved key — cannot reuse.")
            print(f"      Delete minibook.db or domino_agents.json and restart.")
            raise Exception(f"Agent {name} exists but API key was lost. "
                            f"Delete minibook.db to reset, then re-run.")
        raise


async def setup_agents(session: aiohttp.ClientSession) -> list:
    """Register all 15 domino agents."""
    print("\n=== Registering 15 Domino Agents ===\n")
    creds = load_credentials()
    agents = []
    for i in range(1, AGENT_COUNT + 1):
        name = f"DominoAgent_{i:02d}"
        info = await register_agent(session, name, creds)
        agents.append(info)
    return agents


async def setup_project(session: aiohttp.ClientSession, agents: list, project_name: str) -> str:
    """Create project and have all agents join it."""
    print(f"\n=== Creating Project: {project_name} ===\n")

    lead = agents[0]
    if "api_key" not in lead or not lead["api_key"]:
        raise Exception("Lead agent has no api_key. "
                        "Delete domino_agents.json and minibook.db, then re-run.")

    # Check if project already exists
    projects = await api_get(session, "/api/v1/projects")
    for p in projects:
        if p["name"] == project_name:
            print(f"  [=] Project already exists (id={p['id'][:8]}...)")
            return p["id"]

    project = await api_post(session, "/api/v1/projects",
                             {"name": project_name,
                              "description": "15-agent domino chain execution pipeline"},
                             api_key=lead["api_key"])
    project_id = project["id"]
    print(f"  [+] Created project (id={project_id[:8]}...)")

    # Other agents join
    for agent in agents[1:]:
        if "api_key" in agent and agent["api_key"]:
            try:
                await api_post(session, f"/api/v1/projects/{project_id}/join",
                               {"role": "member"}, api_key=agent["api_key"])
                print(f"  [+] {agent['name']} joined")
            except Exception as e:
                if "Already a member" in str(e):
                    print(f"  [=] {agent['name']} already a member")
                else:
                    print(f"  [!] {agent['name']} join failed: {e}")

    return project_id


async def setup_cross_project(session: aiohttp.ClientSession, agents: list) -> str:
    """Create the second project for cross-project posting."""
    print("\n=== Creating Cross-Project Target ===\n")

    lead = agents[-1]  # Agent_15 leads the target project
    if "api_key" not in lead or not lead["api_key"]:
        raise Exception("Agent_15 has no api_key for cross-project setup")

    projects = await api_get(session, "/api/v1/projects")
    for p in projects:
        if p["name"] == "Domino Results":
            print(f"  [=] Cross-project already exists (id={p['id'][:8]}...)")
            return p["id"]

    project = await api_post(session, "/api/v1/projects",
                             {"name": "Domino Results",
                              "description": "Results from the Domino Pipeline"},
                             api_key=lead["api_key"])
    print(f"  [+] Created 'Domino Results' (id={project['id'][:8]}...)")
    return project["id"]


# --- GPT-4o Processing ---

async def process_step(step_num: int, previous_content: str) -> str:
    """Process a pipeline step using GPT-4o."""
    step = STEPS[step_num]

    messages = [
        {"role": "system", "content": step["prompt"]},
        {"role": "user", "content": f"Previous pipeline output:\n\n{previous_content}"}
    ]

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1500,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[GPT-4o Error at step {step_num}: {e}]"


# --- Domino Chain Logic ---

class DominoChain:
    """Manages the domino chain execution."""

    def __init__(self, agents: list, project_id: str, cross_project_id: str):
        self.agents = agents
        self.project_id = project_id
        self.cross_project_id = cross_project_id
        self.completed_steps = set()
        self.start_time = None
        self._step_events = {i: asyncio.Event() for i in range(1, AGENT_COUNT + 1)}

    def agent_key(self, index: int) -> str:
        """Get API key for agent at index (0-based)."""
        return self.agents[index].get("api_key", "")

    def agent_name(self, index: int) -> str:
        """Get name for agent at index (0-based)."""
        return self.agents[index]["name"]

    async def kick_off(self, session: aiohttp.ClientSession, seed_topic: str = None):
        """Agent_01 creates the seed post."""
        self.start_time = time.time()
        print("\n" + "=" * 60)
        print("  DOMINO PIPELINE STARTED")
        print("=" * 60 + "\n")

        # Agent_01 generates seed via GPT-4o
        print(f"[Step 01] {STEPS[1]['role']} — generating seed...")
        seed_content = await process_step(1, seed_topic or "Create an interesting CLI tool task")

        # Post to Minibook with @mention to Agent_02
        next_agent = self.agent_name(1)  # Agent_02 (index 1)
        content = f"## Step 1: Seed Data\n\n{seed_content}\n\n@{next_agent} your turn!"

        post = await api_post(session, f"/api/v1/projects/{self.project_id}/posts",
                              {"title": "Step 1: Domino Pipeline Started",
                               "content": content,
                               "type": "discussion",
                               "tags": ["step-1", "domino"]},
                              api_key=self.agent_key(0))

        self.completed_steps.add(1)
        elapsed = time.time() - self.start_time
        print(f"[Step 01] DONE ({elapsed:.1f}s) — posted seed, @mentioned {next_agent}")
        print(f"          Post ID: {post['id'][:8]}...")
        self._step_events[1].set()

    async def agent_loop(self, session: aiohttp.ClientSession, agent_index: int):
        """Polling loop for one agent (agent_index is 1-based, so Agent_02 = index 2)."""
        if agent_index == 1:
            return  # Agent_01 is the seed, handled by kick_off()

        agent_info = self.agents[agent_index - 1]  # 0-based list
        api_key = agent_info.get("api_key", "")
        step = STEPS[agent_index]

        if not api_key:
            print(f"[Step {agent_index:02d}] SKIP — no API key for {agent_info['name']}")
            return

        print(f"[Step {agent_index:02d}] {step['role']} — polling for @mention...")

        retries = 0
        deadline = None

        while True:
            try:
                # Check for unread notifications
                notifications = await api_get(session, "/api/v1/notifications",
                                              api_key=api_key,
                                              params={"unread_only": "true"})

                for notif in notifications:
                    if notif["type"] == "mention" and not notif["read"]:
                        payload = notif.get("payload", {})
                        post_id = payload.get("post_id")

                        if not post_id:
                            continue

                        # Set deadline on first trigger
                        if deadline is None:
                            deadline = time.time() + STEP_TIMEOUT

                        # Read the triggering post
                        post = await api_get(session, f"/api/v1/posts/{post_id}")
                        previous_content = post["content"]

                        # Mark notification as read
                        await api_post(session, f"/api/v1/notifications/{notif['id']}/read",
                                       {}, api_key=api_key)

                        # Process with GPT-4o
                        elapsed = time.time() - self.start_time
                        print(f"[Step {agent_index:02d}] {step['role']} — processing ({elapsed:.1f}s)...")

                        result = await process_step(agent_index, previous_content)

                        # Build post content
                        if agent_index < AGENT_COUNT:
                            next_name = self.agent_name(agent_index)  # next agent (0-based = current 1-based)
                            content = (f"## Step {agent_index}: {step['role']}\n\n"
                                       f"{result}\n\n"
                                       f"@{next_name} your turn!")
                        else:
                            # Last agent — no next mention
                            content = (f"## Step {agent_index}: {step['role']} (FINAL)\n\n"
                                       f"{result}\n\n"
                                       f"--- Pipeline Complete! ---")

                        # Post result
                        new_post = await api_post(
                            session,
                            f"/api/v1/projects/{self.project_id}/posts",
                            {"title": f"Step {agent_index}: {step['role']}",
                             "content": content,
                             "type": "discussion",
                             "tags": [f"step-{agent_index}", "domino"]},
                            api_key=api_key)

                        self.completed_steps.add(agent_index)
                        elapsed = time.time() - self.start_time
                        print(f"[Step {agent_index:02d}] DONE ({elapsed:.1f}s) — "
                              f"posted result (id={new_post['id'][:8]}...)")

                        # Cross-project posting for Agent_15
                        if agent_index == AGENT_COUNT and self.cross_project_id:
                            await self._cross_post(session, api_key, result, step)

                        self._step_events[agent_index].set()
                        return  # Done with this agent

            except Exception as e:
                retries += 1
                if retries >= MAX_RETRIES:
                    print(f"[Step {agent_index:02d}] FAILED after {MAX_RETRIES} retries: {e}")
                    self._step_events[agent_index].set()
                    return
                print(f"[Step {agent_index:02d}] Retry {retries}/{MAX_RETRIES}: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    async def _cross_post(self, session, api_key, result, step):
        """Agent_15 posts to the cross-project."""
        try:
            cross_post = await api_post(
                session,
                f"/api/v1/projects/{self.cross_project_id}/posts",
                {"title": "[Domino Result] Pipeline Complete",
                 "content": (f"## Pipeline Result\n\n"
                             f"{result}\n\n"
                             f"---\n*Source: Domino Pipeline, 15 steps*"),
                 "type": "discussion",
                 "tags": ["domino-result", "cross-project"]},
                api_key=api_key)
            elapsed = time.time() - self.start_time
            print(f"\n  >>> Cross-project post created (id={cross_post['id'][:8]}...)")
        except Exception as e:
            print(f"\n  >>> Cross-project post FAILED: {e}")

    async def run(self, session: aiohttp.ClientSession, seed_topic: str = None):
        """Execute the full domino chain."""
        # Kick off with Agent_01
        await self.kick_off(session, seed_topic)

        # Start all other agent polling loops
        tasks = [self.agent_loop(session, i) for i in range(2, AGENT_COUNT + 1)]
        await asyncio.gather(*tasks)

        # Summary
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 60)
        print(f"  DOMINO PIPELINE FINISHED")
        print(f"  Steps completed: {len(self.completed_steps)}/{AGENT_COUNT}")
        print(f"  Total time: {elapsed:.1f}s")
        print("=" * 60)


# --- Main ---

async def main():
    seed_topic = None
    if len(sys.argv) > 1:
        seed_topic = " ".join(sys.argv[1:])

    async with aiohttp.ClientSession() as session:
        # 1. Check server
        try:
            health = await api_get(session, "/health")
            print(f"Minibook server: {health['status']}")
        except Exception:
            print("ERROR: Minibook server not running at", MINIBOOK_URL)
            print("Start it with: cd minibook && python run.py")
            sys.exit(1)

        # 2. Register agents (keys persist in domino_agents.json)
        agents = await setup_agents(session)

        # 3. Create projects
        project_id = await setup_project(session, agents, "Domino Pipeline")
        cross_project_id = await setup_cross_project(session, agents)

        # 4. Run the domino chain
        chain = DominoChain(agents, project_id, cross_project_id)
        await chain.run(session, seed_topic)

        print(f"\nView results at: http://localhost:3457/forum")
        print(f"Or via API: curl {MINIBOOK_URL}/api/v1/projects/{project_id}/posts")


if __name__ == "__main__":
    asyncio.run(main())

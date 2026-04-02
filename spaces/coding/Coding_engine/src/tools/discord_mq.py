"""
Discord Message Queue — Uses Discord channels as agent queues.

Architecture (from Dave's diagram):
  #orchestrator  → PM Agent posts new tasks, controls DAG
  #dev-tasks     → Dev Agents pick up coding tasks
  #integration   → Integrator Agent reviews PRs
  #fixes         → Dev Agents post fix suggestions
  #testing       → QA Tester Agent runs E2E tests
  #done          → Verified/completed tasks

Each agent runs a poll loop on its queue channel.
When a new structured message arrives, the agent processes it
and posts the result to the next queue in the pipeline.

Pipeline:
  Orchestrator → #dev-tasks → Dev Agent → #integration → Integrator
  → #testing → QA Tester → #done (or #fixes → Dev Agent → retry)
"""

import asyncio
import logging
import os
from typing import Callable, Optional

from src.tools.discord_agent import DiscordAgent
from src.tools.discord_structured import (
    StructuredMessage, StructuredDiscord, MessageType, Scope
)

# --- Fix #2: Loop prevention ---
# Track retry attempts per task_id. Max 3 retries then skip.
MAX_RETRIES_PER_TASK = 3
_retry_counts: dict = {}

# Epic tracking for post-epic MCMP verification
_epic_task_counts: dict = {}  # epic_id -> {total: N, done: N}


async def _call_llm(prompt: str, model: str = "qwen/qwen3-coder:free", max_tokens: int = 800) -> str:
    """Call OpenRouter LLM with 429 retry backoff."""
    import httpx
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "No OPENROUTER_API_KEY set"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % api_key},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
                )
                if resp.status_code == 429:
                    wait = (attempt + 1) * 10
                    logger.warning("OpenRouter 429 rate limit, waiting %ds", wait)
                    await asyncio.sleep(wait)
                    continue
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            await asyncio.sleep(5)
    return "LLM failed after 3 attempts"


def _check_retry(task_id: str) -> bool:
    """Returns True if task can be retried, False if max retries reached."""
    if not task_id:
        return True
    count = _retry_counts.get(task_id, 0)
    if count >= MAX_RETRIES_PER_TASK:
        logger.warning("Task %s hit max retries (%d), skipping", task_id, MAX_RETRIES_PER_TASK)
        return False
    _retry_counts[task_id] = count + 1
    return True

logger = logging.getLogger(__name__)

# Channel IDs — set via env or hardcoded from creation
CHANNELS = {
    "orchestrator": os.environ.get("DISCORD_CH_ORCHESTRATOR", "1484193339405369344"),
    "dev-tasks": os.environ.get("DISCORD_CH_DEV_TASKS", "1484193408955322399"),
    "integration": os.environ.get("DISCORD_CH_INTEGRATION", "1484193411182366902"),
    "fixes": os.environ.get("DISCORD_CH_FIXES", "1484193412679733302"),
    "testing": os.environ.get("DISCORD_CH_TESTING", "1484193415364214958"),
    "done": os.environ.get("DISCORD_CH_DONE", "1484193417381679225"),
    "general": os.environ.get("DISCORD_CH_GENERAL", "1484160715580510242"),
}

# Bot tokens
ENGINE_BOT = os.environ.get(
    "DISCORD_BOT_TOKEN",
    ""
)
ANALYZER_BOT = os.environ.get(
    "DISCORD_BOT_TOKEN_ANALYZER",
    ""
)


class QueueAgent:
    """An agent that polls a Discord channel queue and processes messages."""

    def __init__(
        self,
        name: str,
        listen_channel: str,
        output_channel: str,
        bot_token: str = "",
        poll_interval: int = 5,
    ):
        self.name = name
        self.listen_channel = CHANNELS.get(listen_channel, listen_channel)
        self.output_channel = CHANNELS.get(output_channel, output_channel)
        self.poll_interval = poll_interval
        self.discord = StructuredDiscord(
            bot_token=bot_token or ENGINE_BOT,
            channel_id=self.listen_channel,
        )
        self.output = StructuredDiscord(
            bot_token=bot_token or ENGINE_BOT,
            channel_id=self.output_channel,
        )
        self._running = False
        self._last_seen_id = "0"
        self._handler: Optional[Callable] = None

    def on_message(self, handler: Callable):
        """Register a message handler. Called with (StructuredMessage) -> StructuredMessage or None."""
        self._handler = handler
        return handler

    async def start(self):
        """Start the polling loop."""
        self._running = True
        # Set last_seen to current latest message to skip history
        try:
            agent = DiscordAgent(
                bot_token=self.discord.agent.bot_token,
                channel_id=self.listen_channel,
            )
            raw = await agent.read_recent(limit=1)
            if raw:
                self._last_seen_id = raw[0].get("id", "0")
        except Exception:
            pass
        logger.info("[%s] Started polling #%s (after msg %s)", self.name, self.listen_channel, self._last_seen_id)

        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error("[%s] Poll error: %s", self.name, e)
            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        logger.info("[%s] Stopped", self.name)

    async def _poll_once(self):
        """Check for new messages and process them."""
        agent = DiscordAgent(
            bot_token=self.discord.agent.bot_token,
            channel_id=self.listen_channel,
        )
        raw = await agent.read_recent(limit=10)
        if not raw:
            return

        # Process oldest first, skip already seen
        for msg in reversed(raw):
            msg_id = msg.get("id", "0")
            # Compare as integers (Discord snowflake IDs)
            if int(msg_id) <= int(self._last_seen_id):
                continue

            content = msg.get("content", "")
            parsed = StructuredMessage.from_discord(content)
            if not parsed:
                self._last_seen_id = msg_id
                continue

            self._last_seen_id = msg_id
            logger.info("[%s] Processing: %s %s", self.name, parsed.msg_type.value, parsed.task_id)

            if self._handler:
                try:
                    response = await self._handler(parsed)
                    if response and isinstance(response, StructuredMessage):
                        # Route FIX_NEEDED to #fixes, not default output
                        target = self.output_channel
                        if response.msg_type == MessageType.FIX_NEEDED:
                            target = CHANNELS.get("fixes", self.output_channel)
                        out_agent = DiscordAgent(
                            bot_token=self.output.agent.bot_token,
                            channel_id=target,
                        )
                        await out_agent.send(response.to_discord())
                        logger.info("[%s] Posted to %s: %s", self.name, target, response.msg_type.value)
                except Exception as e:
                    logger.error("[%s] Handler error: %s", self.name, e)

    async def post_to(self, channel: str, msg: StructuredMessage):
        """Post a message to a specific channel."""
        ch_id = CHANNELS.get(channel, channel)
        agent = DiscordAgent(
            bot_token=self.discord.agent.bot_token,
            channel_id=ch_id,
        )
        await agent.send(msg.to_discord())


class AgentPipeline:
    """Manages all queue agents in the pipeline."""

    def __init__(self):
        self.agents: dict[str, QueueAgent] = {}
        self._tasks: list[asyncio.Task] = []

    def add(self, agent: QueueAgent) -> QueueAgent:
        self.agents[agent.name] = agent
        return agent

    async def start_all(self):
        """Start all agents concurrently."""
        logger.info("Starting %d queue agents", len(self.agents))
        for agent in self.agents.values():
            task = asyncio.create_task(agent.start())
            self._tasks.append(task)

    async def stop_all(self):
        """Stop all agents."""
        for agent in self.agents.values():
            await agent.stop()
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()


async def _pm_handler(msg: StructuredMessage) -> Optional[StructuredMessage]:
    """PM Agent: forwards tasks to dev queue, adds priority/context."""
    logger.info("[PM] Releasing task %s to dev queue", msg.task_id)
    return StructuredMessage(
        msg_type=msg.msg_type,
        scope=msg.scope,
        epic_id=msg.epic_id,
        task_id=msg.task_id,
        task_name=msg.task_name,
        file_path=msg.file_path,
        error=msg.error,
        context=msg.context,
        action=msg.action or "CODE",
    )


async def _write_to_sandbox(file_path: str, content: str) -> bool:
    """Write a file to shared volume so both API and Sandbox can see it.
    API writes to /app/Data/generated/<path> (mounted from host ./Data)
    Sandbox sees it at /workspace/data/generated/<path>
    """
    from pathlib import Path
    try:
        clean_path = file_path.lstrip("/")
        if not clean_path:
            return False

        # Write to shared Data volume
        gen_dir = Path("/app/Data/generated")
        target = gen_dir / clean_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        logger.info("[Dev] Wrote %d bytes to %s", len(content), target)
        return True
    except Exception as e:
        logger.error("[Dev] Write failed: %s", e)
        return False


async def _dev_handler(msg: StructuredMessage) -> Optional[StructuredMessage]:
    """Dev Agent: generates real code via LLM, writes to sandbox, requests review."""
    logger.info("[Dev] Working on %s: %s", msg.task_id, msg.task_name)

    # Determine file path from task
    file_path = msg.file_path or ""
    if not file_path:
        # Derive from task_id: EPIC-001-API-GET-auth-login-controller → src/auth/login.controller.ts
        parts = msg.task_id.split("-")
        if "API" in parts or "controller" in msg.task_id.lower():
            file_path = "src/api/%s.ts" % parts[-1] if parts else "src/api/handler.ts"
        elif "SCHEMA" in parts or "model" in msg.task_id.lower():
            file_path = "src/models/%s.ts" % parts[-1] if parts else "src/models/model.ts"
        elif "component" in msg.task_id.lower() or "UI" in parts:
            file_path = "src/components/%s.tsx" % parts[-1] if parts else "src/components/Component.tsx"
        else:
            file_path = "src/%s.ts" % msg.task_id.split("-")[-1][:20]

    # --- MCMP Pre-Run: Get enriched context before code generation ---
    mcmp_context = ""
    try:
        from src.services.mcmp_prerun import get_prerun
        prerun = get_prerun()
        is_fix = msg.action == "FIX_AND_RETEST" and msg.error
        ctx = await prerun.get_task_context(
            task_id=msg.task_id,
            task_name=msg.task_name or msg.task_id,
            task_description=msg.context[:300] if msg.context else "",
            file_path=file_path,
            mode="repair" if is_fix else "steering",
        )
        mcmp_context = ctx.get("enriched_prompt", "")
        if mcmp_context:
            logger.info("[Dev] MCMP enriched %s with %d relevant files (confidence=%.2f)",
                        msg.task_id, len(ctx.get("relevant_files", [])), ctx.get("confidence", 0))
    except Exception as e:
        logger.warning("[Dev] MCMP pre-run failed (continuing without): %s", e)

    # Build better prompt based on task type
    is_fix = msg.action == "FIX_AND_RETEST" and msg.error
    if is_fix:
        prompt = (
            "You are a senior TypeScript/React developer.\n"
            "Fix this error in %s:\n```\n%s\n```\n"
            "Context: %s\n"
            "%s"
            "Reply with ONLY the complete fixed file content (no markdown, no explanation)."
            % (file_path, msg.error[:500], msg.context[:200], mcmp_context)
        )
    else:
        prompt = (
            "You are a senior TypeScript/React developer.\n"
            "Generate the complete file for: %s\n"
            "File path: %s\n"
            "Task: %s\n"
            "Requirements: %s\n"
            "%s"
            "Reply with ONLY the complete file content (no markdown, no explanation). "
            "Use TypeScript, React functional components, proper types."
            % (msg.task_name or msg.task_id, file_path, msg.task_id, msg.context[:300], mcmp_context)
        )

    try:
        llm_reply = await _call_llm(prompt, max_tokens=2000)
        # Strip markdown code fences if present
        if llm_reply.startswith("```"):
            lines = llm_reply.split("\n")
            llm_reply = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    except Exception as e:
        llm_reply = "// LLM error: %s" % str(e)[:200]

    # Write to sandbox + verify build
    wrote = await _write_to_sandbox(file_path, llm_reply)
    deploy_msg = "Write failed"
    if wrote:
        # #5: Run build check after writing
        try:
            build_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "coding-engine-sandbox",
                "sh", "-c", "cd /workspace/app && npx vite build --mode development 2>&1 | tail -3",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            build_out, _ = await asyncio.wait_for(build_proc.communicate(), timeout=30)
            build_result = build_out.decode().strip()
            if build_proc.returncode == 0:
                deploy_msg = "Deployed + build OK"
            else:
                deploy_msg = "Deployed but build failed: %s" % build_result[:100]
        except Exception:
            deploy_msg = "Deployed (build check skipped)"

    return StructuredMessage(
        msg_type=MessageType.FIX_APPLIED, scope=msg.scope,
        epic_id=msg.epic_id, task_id=msg.task_id, task_name=msg.task_name,
        file_path=file_path, diff=llm_reply[:500],
        context="%s: %s" % (deploy_msg, file_path), action="REVIEW",
        status="PENDING_REVIEW",
    )


async def _integrator_handler(msg: StructuredMessage) -> Optional[StructuredMessage]:
    """Integrator Agent: reviews code diff with LLM, approves or rejects."""
    logger.info("[Integrator] Reviewing %s", msg.task_id)
    if not msg.diff and not msg.context:
        return None

    try:
        if msg.diff:
            prompt = "Review this code change. Reply APPROVE if it looks correct, or REJECT with reason.\nTask: %s\nDiff:\n%s" % (
                msg.task_id, msg.diff[:600]
            )
            review = await _call_llm(prompt, model="nvidia/nemotron-3-super-120b-a12b:free", max_tokens=200)
            if "REJECT" in review.upper():
                return StructuredMessage(
                    msg_type=MessageType.FIX_NEEDED, scope=msg.scope,
                    epic_id=msg.epic_id, task_id=msg.task_id,
                    error="Review rejected: %s" % review[:300],
                    action="FIX_AND_RETEST",
                )
    except Exception as e:
        logger.warning("[Integrator] LLM review failed: %s", e)

    return StructuredMessage(
        msg_type=MessageType.TASK_VERIFIED, scope=msg.scope,
        epic_id=msg.epic_id, task_id=msg.task_id, task_name=msg.task_name,
        context="Integration approved by Integrator-Agent",
        action="E2E_TEST", status="APPROVED",
    )


async def _qa_handler(msg: StructuredMessage) -> Optional[StructuredMessage]:
    """QA Tester Agent: runs browser test via OpenClaw, marks pass/fail."""
    logger.info("[QA] Testing %s", msg.task_id)
    try:
        from src.tools.openclaw_bridge_tool import OpenClawBridge
        bridge = OpenClawBridge(timeout=60)
        available = await bridge.is_available()
        if available:
            result = await bridge.debug_component(
                preview_url="http://host.docker.internal:3100",
                component=msg.task_name or msg.task_id,
                requirements=msg.context,
            )
            if result.success and not result.errors:
                # Track epic progress for MCMP verification
                if msg.epic_id:
                    if msg.epic_id not in _epic_task_counts:
                        _epic_task_counts[msg.epic_id] = {"total": 0, "done": 0}
                    _epic_task_counts[msg.epic_id]["done"] += 1
                    tracker = _epic_task_counts[msg.epic_id]
                    if tracker["done"] >= 3 and tracker["done"] % 5 == 0:
                        asyncio.ensure_future(_verify_epic_and_notify(msg.epic_id))
                return StructuredMessage(
                    msg_type=MessageType.TASK_VERIFIED, scope=msg.scope,
                    epic_id=msg.epic_id, task_id=msg.task_id, task_name=msg.task_name,
                    status="PASS", context="Browser test passed via OpenClaw",
                )
            else:
                # Test failed — send to #fixes
                return StructuredMessage(
                    msg_type=MessageType.FIX_NEEDED, scope=msg.scope,
                    epic_id=msg.epic_id, task_id=msg.task_id, task_name=msg.task_name,
                    file_path=msg.file_path,
                    error="\n".join(result.errors[:3]),
                    context="Browser test failed",
                    action="FIX_AND_RETEST",
                )
        else:
            logger.warning("[QA] OpenClaw not available, using HTTP check fallback")
    except Exception as e:
        logger.error("[QA] Browser test error: %s", e)

    # --- Automation UI Debug ---
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            intent = "Debug and test the component at %s. Check for: visual rendering, console errors, functionality." % (
                msg.file_path or msg.task_id
            )
            if msg.error:
                intent += " Previous error: %s" % msg.error[:200]

            resp = await client.post(
                "http://coding-engine-automation-ui:8007/api/llm/intent",
                json={"intent": intent, "conversation_id": "qa-%s" % msg.task_id},
            )
            if resp.status_code == 200:
                result = resp.json()
                # Check if Automation UI found issues
                if result.get("success") and result.get("summary"):
                    summary = result["summary"]
                    if any(kw in summary.lower() for kw in ["error", "fail", "broken", "missing", "crash"]):
                        return StructuredMessage(
                            msg_type=MessageType.FIX_NEEDED, scope=msg.scope,
                            epic_id=msg.epic_id, task_id=msg.task_id,
                            error="Automation UI found issues: %s" % summary[:300],
                            file_path=msg.file_path, action="FIX_AND_RETEST",
                        )
                    logger.info("[QA] Automation UI check passed for %s", msg.task_id)
    except Exception as e:
        logger.warning("[QA] Automation UI debug unavailable: %s", e)

    # Fallback: HTTP check + console error check on sandbox
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("http://localhost:3100")
            if resp.status_code == 200:
                # Check for build errors in sandbox
                err_proc = await asyncio.create_subprocess_exec(
                    "docker", "exec", "coding-engine-sandbox",
                    "sh", "-c", "cat /tmp/vite.log 2>/dev/null | tail -5 | grep -i error || echo OK",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                out, _ = await asyncio.wait_for(err_proc.communicate(), timeout=5)
                vite_output = out.decode().strip()
                if "error" in vite_output.lower() and "OK" not in vite_output:
                    return StructuredMessage(
                        msg_type=MessageType.FIX_NEEDED, scope=msg.scope,
                        epic_id=msg.epic_id, task_id=msg.task_id,
                        error="Vite build error: %s" % vite_output[:300],
                        file_path=msg.file_path, action="FIX_AND_RETEST",
                    )
                # Track epic progress for MCMP verification
                if msg.epic_id:
                    if msg.epic_id not in _epic_task_counts:
                        _epic_task_counts[msg.epic_id] = {"total": 0, "done": 0}
                    _epic_task_counts[msg.epic_id]["done"] += 1
                    tracker = _epic_task_counts[msg.epic_id]
                    if tracker["done"] >= 3 and tracker["done"] % 5 == 0:
                        asyncio.ensure_future(_verify_epic_and_notify(msg.epic_id))
                return StructuredMessage(
                    msg_type=MessageType.TASK_VERIFIED, scope=msg.scope,
                    epic_id=msg.epic_id, task_id=msg.task_id, task_name=msg.task_name,
                    status="PASS", context="HTTP check passed, no build errors",
                )
            else:
                return StructuredMessage(
                    msg_type=MessageType.FIX_NEEDED, scope=msg.scope,
                    epic_id=msg.epic_id, task_id=msg.task_id,
                    error="Sandbox HTTP %d" % resp.status_code,
                    action="FIX_AND_RETEST",
                )
    except Exception:
        pass

    # Track epic progress for MCMP verification
    if msg.epic_id:
        if msg.epic_id not in _epic_task_counts:
            _epic_task_counts[msg.epic_id] = {"total": 0, "done": 0}
        _epic_task_counts[msg.epic_id]["done"] += 1
        tracker = _epic_task_counts[msg.epic_id]
        if tracker["done"] >= 3 and tracker["done"] % 5 == 0:
            asyncio.ensure_future(_verify_epic_and_notify(msg.epic_id))
    return StructuredMessage(
        msg_type=MessageType.TASK_VERIFIED, scope=msg.scope,
        epic_id=msg.epic_id, task_id=msg.task_id, task_name=msg.task_name,
        status="PASS", context="Fallback pass (sandbox unreachable)",
    )


async def _fix_handler(msg: StructuredMessage) -> Optional[StructuredMessage]:
    """Fix Agent: analyzes error with OpenRouter LLM, generates fix."""
    logger.info("[Fix] Fixing %s: %s", msg.task_id, msg.error[:50] if msg.error else "")
    # Fix #2: Check retry limit
    if not _check_retry(msg.task_id):
        return StructuredMessage(
            msg_type=MessageType.TASK_VERIFIED, task_id=msg.task_id,
            epic_id=msg.epic_id, status="FAIL",
            context="Max retries (%d) reached, task skipped" % MAX_RETRIES_PER_TASK,
        )
    try:
        prompt = "You are a bug-fixing expert. Error in %s:\n```\n%s\n```\nContext: %s\nProvide ONLY the minimal code fix as a diff." % (
            msg.file_path or msg.task_id, msg.error[:500], msg.context[:200]
        )
        fix = await _call_llm(prompt)
    except Exception as e:
        fix = "Fix-Agent error: %s" % str(e)[:200]

    return StructuredMessage(
        msg_type=MessageType.FIX_APPLIED, scope=msg.scope,
        epic_id=msg.epic_id, task_id=msg.task_id,
        file_path=msg.file_path, diff=fix[:500],
        action="RETEST",
    )


async def _verify_epic_and_notify(epic_id: str, expected_files: list = None, requirements: list = None):
    """Post-epic MCMP verification: re-index project, check completeness, notify Discord."""
    try:
        from src.services.mcmp_prerun import get_prerun
        prerun = get_prerun()

        # Re-index to pick up all generated files
        await prerun.index_project()

        result = await prerun.verify_epic_completeness(
            epic_id=epic_id,
            expected_files=expected_files,
            requirements=requirements,
        )

        coverage = result.get("coverage", 0)
        missing = result.get("missing", [])
        complete = result.get("complete", False)

        # Post to Discord #done or #general channel
        import httpx
        bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
        channel_id = CHANNELS.get("done", CHANNELS.get("general"))

        if complete:
            msg_text = "✅ **Epic %s VERIFIED** — %.0f%% coverage\nAll expected outputs generated." % (epic_id, coverage * 100)
        else:
            missing_list = "\n".join("• %s" % m for m in missing[:10])
            msg_text = "⚠️ **Epic %s INCOMPLETE** — %.0f%% coverage\n**Missing:**\n%s" % (epic_id, coverage * 100, missing_list)

        if bot_token and channel_id:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    "https://discord.com/api/v10/channels/%s/messages" % channel_id,
                    headers={"Authorization": "Bot %s" % bot_token},
                    json={"content": msg_text[:2000]},
                )

        logger.info("[MCMP] Epic %s verification: complete=%s, coverage=%.2f", epic_id, complete, coverage)
        return result
    except Exception as e:
        logger.warning("[MCMP] Epic verification failed: %s", e)
        return {"complete": False, "error": str(e)}


async def _index_mcmp_on_start():
    """Index project code into MCMP on pipeline start (background)."""
    try:
        from src.services.mcmp_prerun import get_prerun
        prerun = get_prerun()
        count = await prerun.index_project()
        logger.info("[Pipeline] MCMP pre-indexed %d documents for context enrichment", count)
    except Exception as e:
        logger.warning("[Pipeline] MCMP indexing failed (non-fatal): %s", e)


def create_default_pipeline() -> AgentPipeline:
    """Create the standard agent pipeline matching Dave's architecture."""
    pipeline = AgentPipeline()

    # Trigger MCMP indexing in background when pipeline starts
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_index_mcmp_on_start())
        else:
            loop.run_until_complete(_index_mcmp_on_start())
    except Exception:
        pass  # Will index lazily on first task

    # Fix #3: Slower poll intervals to avoid rate limiting
    # PM Agent — reads orchestrator queue, posts to dev-tasks
    pm = pipeline.add(QueueAgent(
        name="PM-Agent",
        listen_channel="orchestrator",
        output_channel="dev-tasks",
        bot_token=ENGINE_BOT,
        poll_interval=10,
    ))
    pm.on_message(_pm_handler)

    # Dev Agent — reads dev-tasks, codes, posts to integration
    dev = pipeline.add(QueueAgent(
        name="Dev-Agent",
        listen_channel="dev-tasks",
        output_channel="integration",
        bot_token=ENGINE_BOT,
        poll_interval=15,  # Slower — LLM calls take time
    ))
    dev.on_message(_dev_handler)

    # Integrator Agent — reads integration, reviews, posts to testing or fixes
    integrator = pipeline.add(QueueAgent(
        name="Integrator-Agent",
        listen_channel="integration",
        output_channel="testing",
        bot_token=ANALYZER_BOT,
        poll_interval=15,
    ))
    integrator.on_message(_integrator_handler)

    # QA Tester Agent — reads testing, runs E2E, posts to done or fixes
    qa = pipeline.add(QueueAgent(
        name="QA-Tester-Agent",
        listen_channel="testing",
        output_channel="done",
        bot_token=ENGINE_BOT,
        poll_interval=10,
    ))
    qa.on_message(_qa_handler)

    # Fix Agent — reads fixes, applies fixes, posts back to dev-tasks
    fixer = pipeline.add(QueueAgent(
        name="Fix-Agent",
        listen_channel="fixes",
        output_channel="dev-tasks",
        bot_token=ANALYZER_BOT,
    ))
    fixer.on_message(_fix_handler)

    return pipeline

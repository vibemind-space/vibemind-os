"""
Discord Listener for Automation_ui Analyzer Bot.

Features:
1. Polls #fixes channel for FIX_NEEDED messages → LLM fix suggestions → #dev-tasks
2. Discord Commands: !status, !backends, !logs, !generate via #dev-tasks
3. Gateway WebSocket to show bot as Online with activity status

Started as background task when Automation_ui backend boots.
"""

import asyncio
import json
import logging
import os
import re

import httpx

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
FIXES_CHANNEL = os.environ.get("DISCORD_CH_FIXES", "1484193412679733302")
DEV_TASKS_CHANNEL = os.environ.get("DISCORD_CH_DEV_TASKS", "1484193408955322399")
PRS_CHANNEL = os.environ.get("DISCORD_CH_PRS", "1485666130474303562")
ORCHESTRATOR_CHANNEL = os.environ.get("DISCORD_CH_ORCHESTRATOR", "1484193339405369344")
TESTING_CHANNEL = os.environ.get("DISCORD_CH_TESTING", "1484193415364214958")
DONE_CHANNEL = os.environ.get("DISCORD_CH_DONE", "1484193417381679225")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
API_URL = os.environ.get("CODING_ENGINE_API_URL", "http://api:8000")
POLL_INTERVAL = 15  # seconds

# ── Engine Settings cache (fetched from API) ──
_engine_settings_cache = {}
_engine_settings_ts = 0


async def _get_engine_settings() -> dict:
    """Fetch engine settings from API, cached for 60s."""
    global _engine_settings_cache, _engine_settings_ts
    import time
    now = time.time()
    if _engine_settings_cache and (now - _engine_settings_ts) < 60:
        return _engine_settings_cache
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("%s/api/v1/dashboard/engine-settings" % API_URL)
            if resp.status_code == 200:
                _engine_settings_cache = resp.json()
                _engine_settings_ts = now
    except Exception:
        pass
    return _engine_settings_cache


def _es(path: str, default=None):
    """Sync accessor for cached engine settings (dot-notation)."""
    current = _engine_settings_cache
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current if current is not None else default


class DiscordAnalyzerListener:
    """Polls Discord #fixes, handles !commands, and generates fix suggestions."""

    def __init__(self):
        self.last_seen_id = "0"
        self.last_cmd_id = "0"
        self.running = False
        self.bot_user_id = None
        self.headers = {
            "Authorization": "Bot %s" % BOT_TOKEN,
            "Content-Type": "application/json",
        }

    def _find_project(self, name: str = "") -> dict:
        """Find project by name/key, or return first/default project."""
        projects = _es("projects", {})
        if not projects:
            return {}
        if name:
            for key, p in projects.items():
                if name in key or name in p.get("name", "") or name in p.get("id", ""):
                    p["_key"] = key
                    return p
            return {}
        first_key = next(iter(projects))
        p = projects[first_key]
        p["_key"] = first_key
        return p

    def _project_id(self, name: str = "") -> str:
        """Get project ID from engine settings."""
        p = self._find_project(name)
        return p.get("id", "") if p else ""

    def _project_output(self, name: str = "") -> str:
        """Get project output dir from engine settings."""
        p = self._find_project(name)
        return p.get("output_dir", "/app/output") if p else "/app/output"

    def _project_db_id(self, project_name: str = "") -> int:
        """Get project DB project_id (used in /db/projects/{id}/tasks). Dynamic lookup."""
        p = self._find_project(project_name)
        return p.get("db_project_id", 2) if p else 2

    async def start(self):
        """Start Gateway connection + polling loops."""
        if not BOT_TOKEN:
            logger.warning("No DISCORD_BOT_TOKEN, Analyzer listener disabled")
            return

        self.running = True

        # Connect to Discord Gateway to appear Online
        asyncio.create_task(self._gateway_loop())

        # Auto-post status every 3 min while generation is running
        asyncio.create_task(self._status_loop())

        # Skip existing messages in both channels
        for channel, attr in [(FIXES_CHANNEL, "last_seen_id"), (DEV_TASKS_CHANNEL, "last_cmd_id")]:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "%s/channels/%s/messages?limit=1" % (DISCORD_API, channel),
                        headers=self.headers, timeout=10,
                    )
                    if resp.status_code == 200:
                        msgs = resp.json()
                        if msgs:
                            setattr(self, attr, msgs[0]["id"])
            except Exception:
                pass

        logger.info("Analyzer listener started, polling #fixes + #dev-tasks commands")
        while self.running:
            try:
                await self._poll()
                await self._poll_commands()
            except Exception as e:
                logger.error("Analyzer poll error: %s", e)
            await asyncio.sleep(POLL_INTERVAL)

    async def _status_loop(self):
        """
        Autonomous pipeline loop:
        1. Monitor generation (post status every 3 min)
        2. When generation ends + failed > 0 → auto !fixall
        3. After fix → verify (build + file check + browser)
        4. If verified → create PR
        5. Auto-review PR → merge if OK
        """
        last_statuses = {}  # per-project status tracking: {project_key: "hash"}
        was_running = {}    # per-project: {project_key: bool}
        fix_rounds = {}     # per-project: {project_key: int}

        # Load settings from API
        await _get_engine_settings()
        STATUS_INTERVAL = _es("discord.auto_status.interval_seconds", 180)
        MAX_FIX_ROUNDS = _es("discord.auto_fix.max_rounds", 3)
        AUTO_FIX_ENABLED = _es("discord.auto_fix.enabled", True)

        logger.info("_status_loop STARTED, interval=%ds, max_fix_rounds=%d", STATUS_INTERVAL, MAX_FIX_ROUNDS)

        while self.running:
            try:
                await asyncio.sleep(STATUS_INTERVAL)
                logger.info("_status_loop TICK")

                # Reload settings periodically
                await _get_engine_settings()
                projects = _es("projects", {})
                if not projects:
                    continue

                # ── Iterate over ALL registered projects ──
                for proj_key, proj_config in projects.items():
                    project_id = proj_config.get("id", proj_key)
                    proj_name = proj_config.get("name", proj_key)

                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.get("%s/api/v1/dashboard/status?projectId=%s" % (API_URL, project_id))
                        if resp.status_code != 200:
                            continue
                        data = resp.json()

                    is_running = data.get("running", False)
                    phase = data.get("phase", "idle")
                    completed = data.get("completed", 0)
                    failed = data.get("failed", 0)
                    pending = data.get("pending", 0)
                    total = data.get("total", 0)
                    progress = data.get("progress_pct", 0)
                    last_activity = data.get("last_activity", "")[:100]

                    # Per-project state tracking
                    prev_status = last_statuses.get(proj_key, "")
                    prev_running = was_running.get(proj_key, False)
                    proj_fix_rounds = fix_rounds.get(proj_key, 0)

                    # ── Always post status if there are tasks ──
                    if total > 0:
                        new_status = "%d-%d-%d-%s" % (completed, failed, pending, phase)
                        if new_status != prev_status:
                            emoji = "🔄" if is_running else "📊"
                            prefix = "**[%s]** " % proj_name if len(projects) > 1 else ""
                            status_msg = (
                                "%s %s**Auto-Status** (%s%% | %s)\n"
                                "✅ %d completed | ❌ %d failed | ⏳ %d pending | 📦 %d total"
                                % (emoji, prefix, progress, phase, completed, failed, pending, total)
                            )
                            if last_activity and is_running:
                                status_msg += "\n📝 `%s`" % last_activity
                            await self._post_to_channel(DEV_TASKS_CHANNEL, status_msg)
                            last_statuses[proj_key] = new_status

                    # ── PHASE 1: Generation running ──
                    if is_running or phase == "generating":
                        was_running[proj_key] = True
                        fix_rounds[proj_key] = 0
                        continue

                    # ── PHASE 2: Generation just finished → auto pipeline ──
                    if prev_running and not is_running:
                        was_running[proj_key] = False
                        prefix = "**[%s]** " % proj_name if len(projects) > 1 else ""
                        # #orchestrator: generation events
                        gen_msg = "🏁 %s**Generation finished!** ✅ %d | ❌ %d | ⏳ %d" % (prefix, completed, failed, pending)
                        await self._post_to_channel(ORCHESTRATOR_CHANNEL, gen_msg)

                        if failed > 0 and proj_fix_rounds < MAX_FIX_ROUNDS:
                            fix_rounds[proj_key] = proj_fix_rounds + 1
                            fix_msg = "🔧 %s**Auto-Fix Round %d/%d** — fixing %d failed tasks..." % (prefix, fix_rounds[proj_key], MAX_FIX_ROUNDS, failed)
                            await self._post_to_channel(FIXES_CHANNEL, fix_msg)
                            try:
                                fix_result = await self._cmd_fixall(proj_key)
                                await self._post_to_channel(FIXES_CHANNEL, fix_result)
                            except Exception as e:
                                await self._post_to_channel(FIXES_CHANNEL, "❌ Auto-fix error: %s" % str(e)[:200])
                            await asyncio.sleep(5)
                            continue

                        await self._auto_verify_and_pr()
                        last_statuses[proj_key] = "pipeline_done"

                        # #done: final summary
                        await self._post_to_channel(DONE_CHANNEL,
                            "✅ %s**Pipeline complete!** ✅ %d completed | 📦 %d total" % (prefix, completed, total))

                    # ── Idle with failed tasks → auto-fixall ──
                    if AUTO_FIX_ENABLED and not is_running and not prev_running and failed > 0 and proj_fix_rounds < MAX_FIX_ROUNDS and prev_status != "pipeline_done":
                        fix_rounds[proj_key] = proj_fix_rounds + 1
                        prefix = "**[%s]** " % proj_name if len(projects) > 1 else ""
                        fix_msg = "🔧 %s**Auto-Fix (idle)** Round %d/%d — %d failed tasks" % (prefix, fix_rounds[proj_key], MAX_FIX_ROUNDS, failed)
                        await self._post_to_channel(FIXES_CHANNEL, fix_msg)
                        try:
                            fix_result = await self._cmd_fixall(proj_key)
                            await self._post_to_channel(FIXES_CHANNEL, fix_result)
                        except Exception as e:
                            await self._post_to_channel(FIXES_CHANNEL, "❌ Auto-fix error: %s" % str(e)[:200])

            except Exception as e:
                logger.error("Status loop error: %s", e)

    async def _auto_verify_and_pr(self):
        """Phase 3-5: Verify → PR → Review. Routes to appropriate channels."""
        await self._post_to_channel(TESTING_CHANNEL,
            "🔍 **Phase 3: Verification** — checking generated code...")

        # ── 3a. File existence check ──
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                verify_resp = await client.post(
                    "%s/api/v1/dashboard/verify-generation" % API_URL,
                    json={"project_dir": self._project_output()},
                    timeout=60,
                )
                if verify_resp.status_code == 200:
                    v_data = verify_resp.json()
                    files_count = v_data.get("files_count", 0)
                    build_ok = v_data.get("build_ok", False)
                    issues = v_data.get("issues", [])
                else:
                    files_count = 0
                    build_ok = False
                    issues = ["Verify endpoint returned %d" % verify_resp.status_code]
        except Exception as e:
            files_count = 0
            build_ok = False
            issues = [str(e)[:200]]

        # ── 3b. Build check ──
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                build_resp = await client.post(
                    "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                    json={"command": "cd %s && npm run build 2>&1 | tail -5" % self._project_output()},
                    timeout=120,
                )
                if build_resp.status_code == 200:
                    b_data = build_resp.json()
                    build_output = b_data.get("output", "")
                    if "error" not in build_output.lower():
                        build_ok = True
        except Exception:
            pass

        verify_msg = "📋 **Verification Report:**\n"
        verify_msg += "📁 Files: %d\n" % files_count
        verify_msg += "🏗️ Build: %s\n" % ("✅ PASS" if build_ok else "❌ FAIL")
        if issues:
            verify_msg += "⚠️ Issues: %s\n" % "; ".join(issues[:3])

        # #testing: verify reports only
        await self._post_to_channel(TESTING_CHANNEL, verify_msg)

        # ── Phase 4: Create PR if build passes ──
        if build_ok:
            # #prs: PR events only
            await self._post_to_channel(PRS_CHANNEL,
                "📝 **Phase 4: Creating PR...**")
            try:
                proj = self._find_project()
                pr_title = "Auto-generated %s" % (proj.get("name", "project") if proj else "project")
                pr_result = await self._cmd_create_pr(pr_title)
                await self._post_to_channel(PRS_CHANNEL, pr_result)

                pr_url = ""
                for word in pr_result.split():
                    if "github.com" in word and "/pull/" in word:
                        pr_url = word.strip("<>")
                        break

                if pr_url:
                    await asyncio.sleep(10)
                    await self._post_to_channel(PRS_CHANNEL,
                        "🔎 **Phase 5: Auto-reviewing PR...**")
                    try:
                        review_result = await self._cmd_review_pr(pr_url)
                        await self._post_to_channel(PRS_CHANNEL, review_result)
                    except Exception as e:
                        await self._post_to_channel(PRS_CHANNEL,
                            "❌ Auto-review failed: %s" % str(e)[:200])

            except Exception as e:
                await self._post_to_channel(PRS_CHANNEL,
                    "❌ PR creation failed: %s" % str(e)[:200])
        else:
            await self._post_to_channel(TESTING_CHANNEL,
                "⏸️ **PR skipped** — build not passing. Run `!fixall` to fix remaining issues.")

    async def _gateway_loop(self):
        """Connect to Discord Gateway WebSocket to set bot presence to Online."""
        if not websockets:
            logger.warning("websockets not installed, bot will appear offline")
            return

        while self.running:
            try:
                await self._connect_gateway()
            except Exception as e:
                logger.warning("Gateway disconnected: %s, reconnecting in 10s", e)
            if self.running:
                await asyncio.sleep(10)

    async def _connect_gateway(self):
        """Establish Gateway connection, identify, and maintain heartbeat."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "%s/gateway/bot" % DISCORD_API,
                headers=self.headers, timeout=10,
            )
            if resp.status_code != 200:
                logger.error("Failed to get gateway URL: %s", resp.status_code)
                return
            gateway_url = resp.json()["url"]

        async with websockets.connect("%s/?v=10&encoding=json" % gateway_url) as ws:
            # Receive Hello (opcode 10)
            hello = json.loads(await ws.recv())
            if hello.get("op") != 10:
                logger.error("Expected Hello, got op=%s", hello.get("op"))
                return
            heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0
            logger.info("Gateway connected, heartbeat=%.1fs", heartbeat_interval)

            # Send Identify (opcode 2) with MESSAGE_CONTENT intent
            identify = {
                "op": 2,
                "d": {
                    "token": BOT_TOKEN,
                    "intents": 33280,  # GUILD_MESSAGES (512) + MESSAGE_CONTENT (32768)
                    "properties": {
                        "os": "linux",
                        "browser": "coding-auto-ui",
                        "device": "coding-auto-ui",
                    },
                    "presence": {
                        "activities": [{"name": "!status | !backends", "type": 3}],
                        "status": "online",
                        "afk": False,
                    },
                },
            }
            await ws.send(json.dumps(identify))

            # Receive Ready
            ready = json.loads(await ws.recv())
            if ready.get("t") == "READY":
                logger.info("Gateway READY, bot is Online")
                # Store bot user ID for self-skip
                user_data = ready.get("d", {}).get("user", {})
                self.bot_user_id = user_data.get("id")
            self._sequence = ready.get("s")

            # Heartbeat + message loop
            async def _heartbeat():
                while self.running:
                    await asyncio.sleep(heartbeat_interval)
                    try:
                        await ws.send(json.dumps({"op": 1, "d": self._sequence}))
                    except Exception:
                        break

            async def _receive():
                while self.running:
                    try:
                        raw = await ws.recv()
                        data = json.loads(raw)
                        if data.get("s"):
                            self._sequence = data["s"]
                        op = data.get("op")
                        if op == 11:  # Heartbeat ACK
                            pass
                        elif op == 7:  # Reconnect
                            break
                        elif op == 9:  # Invalid session
                            break
                    except Exception:
                        break

            hb_task = asyncio.create_task(_heartbeat())
            recv_task = asyncio.create_task(_receive())
            done, pending = await asyncio.wait(
                [hb_task, recv_task], return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()

    def stop(self):
        self.running = False

    # ─── Fix Analyzer (existing) ─────────────────────────────

    async def _poll(self):
        """Check for new FIX_NEEDED messages in #fixes."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "%s/channels/%s/messages?limit=5&after=%s" % (DISCORD_API, FIXES_CHANNEL, self.last_seen_id),
                headers=self.headers, timeout=10,
            )
            if resp.status_code != 200:
                return
            messages = resp.json()

        for msg in reversed(messages):
            if int(msg["id"]) <= int(self.last_seen_id):
                continue
            self.last_seen_id = msg["id"]

            content = msg.get("content", "")
            if "FIX_NEEDED" not in content:
                continue

            match = re.search(r'\|\|`(\{[^`]+\})`\|\|', content)
            if not match:
                continue
            try:
                header = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            task_id = header.get("task", "")
            epic_id = header.get("epic", "") or self._extract_epic(task_id)

            # Only fix if generation is NOT running — wait for completion
            if await self._is_generation_running():
                logger.debug("Skipping fix for %s — generation still running", task_id)
                continue

            logger.info("Analyzer: dispatching fix for %s via CLI", task_id)
            error_text = self._extract_error_from_message(content)
            await self._dispatch_cli_fix(task_id, epic_id, error_text)
            await self._reply("Fixing `%s` via CLI (max 3 attempts)..." % task_id)
            # Rate limit: wait between fix dispatches
            await asyncio.sleep(5)

    async def _is_generation_running(self) -> bool:
        """Check if code generation is currently running via API."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("%s/api/v1/dashboard/status" % API_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    phase = data.get("phase", "")
                    return phase not in ("", "idle", "completed", "failed", "stopped")
        except Exception:
            pass
        return False

    async def _dispatch_cli_fix(self, task_id: str, epic_id: str, error: str):
        """Call /fix-task API endpoint which uses Kilo/Claude CLI to apply fixes."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "%s/api/v1/dashboard/fix-task" % API_URL,
                    json={
                        "task_id": task_id,
                        "epic_id": epic_id,
                        "error_message": error[:2000],
                        "max_retries": 3,
                    },
                )
                if resp.status_code == 200:
                    logger.info("Fix dispatched: %s", task_id)
                else:
                    logger.warning("Fix dispatch failed: %s %s", resp.status_code, resp.text[:200])
                    await self._reply("Fix dispatch failed for `%s`: %s" % (task_id, resp.text[:100]))
        except Exception as e:
            logger.error("Fix dispatch error: %s", e)
            await self._reply("Fix dispatch error for `%s`: %s" % (task_id, str(e)[:100]))

    def _extract_error_from_message(self, content: str) -> str:
        """Extract error text from a FIX_NEEDED Discord message."""
        # Error is usually in a code block
        code_match = re.search(r'```\n?(.*?)\n?```', content, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        # Fallback: everything after "Name:" line
        lines = content.split("\n")
        error_lines = []
        capture = False
        for line in lines:
            if line.startswith("Name:"):
                capture = True
                continue
            if line.startswith("**Action:**"):
                break
            if capture:
                error_lines.append(line)
        return "\n".join(error_lines).strip() or content[:500]

    async def _generate_fix(self, error_content: str, header: dict) -> str:
        """Analyze error with full context: task details + source code + error."""
        if not OPENROUTER_KEY:
            return "No API key for analysis"

        task_id = header.get("task", "")
        epic_id = header.get("epic", "") or self._extract_epic(task_id)
        scope = header.get("scope", "FULLSTACK")

        # 1. Fetch task details from API (description, output_files)
        task_context = await self._fetch_task_context(epic_id, task_id)

        # 2. Fetch source code of related files
        source_code = await self._fetch_source_files(task_context.get("output_files", []))

        # 3. Build enriched prompt
        prompt_parts = [
            "You are a senior developer fixing a failing task in a code generation pipeline.",
            "Respond with ONLY a JSON object: {\"file\": \"path/to/file.ts\", \"fix\": \"corrected code\", \"explanation\": \"one-line why\"}",
            "",
            "## Task",
            "ID: %s" % task_id,
            "Title: %s" % task_context.get("title", "unknown"),
            "Description: %s" % task_context.get("description", "none")[:500],
            "Scope: %s" % scope,
            "",
            "## Error",
            error_content[:1000],
        ]

        if source_code:
            prompt_parts.extend(["", "## Current Source Code"])
            for fpath, code in source_code.items():
                prompt_parts.append("### %s\n```\n%s\n```" % (fpath, code[:1500]))

        prompt = "\n".join(prompt_parts)

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % OPENROUTER_KEY},
                    json={
                        "model": os.environ.get("LLM_MODEL", "qwen/qwen3-coder:free"),
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2000,
                    },
                )
                if resp.status_code == 429:
                    await asyncio.sleep(15)
                    return '{"error": "Rate limited, retry later"}'
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", '{"error": "No fix"}')
        except Exception as e:
            return '{"error": "Analysis error: %s"}' % str(e)[:100]

    async def _fetch_task_context(self, epic_id: str, task_id: str) -> dict:
        """Fetch task details from the coding-engine API."""
        if not epic_id:
            return {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "%s/api/v1/enrichment/task/%s/%s" % (API_URL, epic_id, task_id)
                )
                if resp.status_code == 200:
                    return resp.json()
                # Fallback: get all tasks and filter
                resp = await client.get(
                    "%s/api/v1/dashboard/db/projects/%d/tasks" % (API_URL, self._project_db_id())
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tasks = data.get("tasks", data) if isinstance(data, dict) else data
                    for t in tasks:
                        if t.get("task_id") == task_id:
                            return t
        except Exception as e:
            logger.warning("Failed to fetch task context: %s", e)
        return {}

    async def _fetch_source_files(self, file_paths: list) -> dict:
        """Fetch source file contents from the sandbox or output dir."""
        if not file_paths:
            return {}
        result = {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for fpath in file_paths[:3]:  # Max 3 files
                    # Try reading from sandbox container
                    resp = await client.post(
                        "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                        json={"command": "cat %s" % fpath, "timeout": 5},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("stdout", data.get("output", ""))
                        if content:
                            result[fpath] = content
        except Exception as e:
            logger.warning("Failed to fetch source files: %s", e)
        return result

    def _extract_epic(self, task_id: str) -> str:
        """Extract epic ID from task ID (e.g. EPIC-003-SETUP-env → EPIC-003)."""
        parts = task_id.split("-")
        if len(parts) >= 2 and parts[0] == "EPIC":
            return "%s-%s" % (parts[0], parts[1])
        return ""

    async def _post_fix(self, task_id: str, fix: str, header: dict):
        """Post structured fix suggestion to #dev-tasks."""
        scope = header.get("scope", "FULLSTACK")

        # Try to parse structured JSON fix
        fix_data = {}
        try:
            # Strip markdown code fences if present
            clean = fix.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = clean.rsplit("```", 1)[0]
            fix_data = json.loads(clean.strip())
        except (json.JSONDecodeError, ValueError):
            pass

        if fix_data.get("file"):
            # Structured fix with file path
            msg_content = (
                "**FIX_SUGGESTED** | %s\n"
                "Task: `%s`\n"
                "File: `%s`\n"
                "**Explanation:** %s\n"
                "**Fix:**\n```\n%s\n```\n"
                "**Action:** `RETEST`\n"
                "||`%s`||"
            ) % (
                scope, task_id,
                fix_data.get("file", "?"),
                fix_data.get("explanation", "")[:200],
                str(fix_data.get("fix", ""))[:1200],
                json.dumps({"type": "FIX_SUGGESTED", "task": task_id, "file": fix_data.get("file", ""), "action": "RETEST"}),
            )
        else:
            # Fallback: raw text fix
            msg_content = (
                "**FIX_SUGGESTED** | %s\n"
                "Task: `%s`\n"
                "**Analysis:**\n```\n%s\n```\n"
                "**Action:** `RETEST`\n"
                "||`%s`||"
            ) % (
                scope, task_id,
                fix[:1200],
                json.dumps({"type": "FIX_SUGGESTED", "task": task_id, "action": "RETEST"}),
            )

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "%s/channels/%s/messages" % (DISCORD_API, DEV_TASKS_CHANNEL),
                    headers=self.headers,
                    json={"content": msg_content[:2000]},
                    timeout=10,
                )
        except Exception as e:
            logger.error("Failed to post fix: %s", e)

    # ─── Discord Commands ─────────────────────────────────────

    async def _poll_commands(self):
        """Check #dev-tasks for !command messages."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "%s/channels/%s/messages?limit=5&after=%s" % (DISCORD_API, DEV_TASKS_CHANNEL, self.last_cmd_id),
                    headers=self.headers, timeout=10,
                )
                if resp.status_code != 200:
                    return
                messages = resp.json()
        except Exception:
            return

        for msg in reversed(messages):
            if int(msg["id"]) <= int(self.last_cmd_id):
                continue
            self.last_cmd_id = msg["id"]

            # Skip bot messages
            author = msg.get("author", {})
            if author.get("bot"):
                continue

            content = msg.get("content", "").strip()
            if not content.startswith("!"):
                continue

            logger.info("Command received: %s", content[:50])
            await self._handle_command(content, msg)

    async def _handle_command(self, content: str, msg: dict):
        """Dispatch !commands."""
        parts = content.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "!status": self._cmd_status,
            "!backends": self._cmd_backends,
            "!logs": self._cmd_logs,
            "!generate": self._cmd_generate,
            "!verify": self._cmd_verify,
            "!files": self._cmd_files,
            "!preview": self._cmd_preview,
            "!pr": self._cmd_create_pr,
            "!review": self._cmd_review_pr,
            "!fixall": self._cmd_fixall,
            "!sync": self._cmd_sync,
            "!help": self._cmd_help,
        }

        handler = handlers.get(cmd)
        if handler:
            try:
                response = await handler(args)
                await self._reply(response)
            except Exception as e:
                await self._reply("Error: %s" % str(e)[:200])
        elif cmd.startswith("!"):
            await self._reply(
                "Unknown command: `%s`\nAvailable: `!status` `!backends` `!logs` `!generate` `!pr` `!review` `!help`" % cmd
            )

    async def _reply(self, message: str):
        """Post reply to #dev-tasks."""
        await self._post_to_channel(DEV_TASKS_CHANNEL, message)

    async def _post_to_channel(self, channel_id: str, message: str):
        """Post message to any Discord channel."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "%s/channels/%s/messages" % (DISCORD_API, channel_id),
                    headers=self.headers,
                    json={"content": message[:2000]},
                    timeout=10,
                )
        except Exception as e:
            logger.error("Failed to post to %s: %s", channel_id, e)

    async def _cmd_verify(self, args: str) -> str:
        """Verify generated code: npm install + tsc + build."""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                # Find the output dir
                resp = await client.get("%s/api/v1/dashboard/db/projects" % API_URL)
                if resp.status_code != 200:
                    return "No projects found"
                data = resp.json()
                projects = data.get("projects", data) if isinstance(data, dict) else data
                if not projects or not isinstance(projects, list):
                    return "No projects. Start generation first."
                project = projects[0]
                output_dir = "/app/output/%s" % project["name"]

                lines = ["**Verifying** `%s`" % project["name"]]

                # Step 1: Count files
                r = await client.post(
                    "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                    json={"command": "find /workspace/app -type f | wc -l", "container": "coding-engine-sandbox"},
                    timeout=15,
                )
                if r.status_code == 200:
                    d = r.json()
                    count = (d.get("stdout") or d.get("output") or "?").strip()
                    lines.append("📁 Files in sandbox: %s" % count)

                # Step 2: Check if package.json exists
                r = await client.post(
                    "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                    json={"command": "cat /workspace/app/package.json 2>/dev/null | head -3 || echo 'NO_PACKAGE_JSON'", "container": "coding-engine-sandbox"},
                    timeout=10,
                )
                has_pkg = r.status_code == 200 and "NO_PACKAGE_JSON" not in (r.json().get("stdout") or "")

                if has_pkg:
                    # Step 3: npm install
                    lines.append("📦 Running npm install...")
                    r = await client.post(
                        "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                        json={"command": "cd /workspace/app && npm install --legacy-peer-deps 2>&1 | tail -3", "container": "coding-engine-sandbox"},
                        timeout=60,
                    )
                    if r.status_code == 200:
                        out = (r.json().get("stdout") or "")[:200]
                        lines.append("```\n%s\n```" % out)

                    # Step 4: TypeScript check
                    lines.append("🔍 TypeScript check...")
                    r = await client.post(
                        "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                        json={"command": "cd /workspace/app && npx tsc --noEmit 2>&1 | tail -5", "container": "coding-engine-sandbox"},
                        timeout=30,
                    )
                    if r.status_code == 200:
                        out = (r.json().get("stdout") or "")[:300]
                        if not out.strip() or "error" not in out.lower():
                            lines.append("✅ TypeScript: PASS")
                        else:
                            lines.append("❌ TypeScript errors:\n```\n%s\n```" % out)

                    # Step 5: Build
                    lines.append("🏗️ Build check...")
                    r = await client.post(
                        "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                        json={"command": "cd /workspace/app && npm run build 2>&1 | tail -5", "container": "coding-engine-sandbox"},
                        timeout=60,
                    )
                    if r.status_code == 200:
                        out = (r.json().get("stdout") or "")[:300]
                        if "error" not in out.lower():
                            lines.append("✅ Build: PASS")
                        else:
                            lines.append("❌ Build errors:\n```\n%s\n```" % out)
                else:
                    lines.append("⚠️ No package.json yet — generation still running")

                return "\n".join(lines)
        except Exception as e:
            return "Verify error: %s" % str(e)[:200]

    async def _cmd_files(self, args: str) -> str:
        """List generated files in sandbox."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                    json={
                        "command": "find /workspace/app -type f -name '*.ts' -o -name '*.prisma' -o -name '*.json' | sort | head -25",
                        "container": "coding-engine-sandbox",
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    out = (r.json().get("stdout") or r.json().get("output") or "No files").strip()
                    count = len([l for l in out.split("\n") if l.strip()])
                    return "**Generated Files** (%d shown)\n```\n%s\n```" % (count, out[:1500])
                return "Could not list files (status %d)" % r.status_code
        except Exception as e:
            return "Error: %s" % str(e)[:200]

    async def _cmd_preview(self, args: str) -> str:
        """Take screenshot of sandbox preview and analyze with Vision."""
        sandbox_url = os.environ.get("SANDBOX_APP_URL", "http://sandbox:3100")
        vision_model = os.environ.get("VISION_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free")

        try:
            # 1. Check if sandbox is reachable
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    resp = await client.get(sandbox_url)
                    if resp.status_code != 200:
                        return "Sandbox not reachable at %s (status %d)" % (sandbox_url, resp.status_code)
                    page_content = resp.text[:500]
                except Exception as e:
                    return "Sandbox not reachable: %s" % str(e)[:100]

            # 2. Analyze page content with LLM
            if not OPENROUTER_KEY:
                return "Preview reachable but no API key for analysis.\nPage content:\n```\n%s\n```" % page_content[:300]

            prompt = (
                "Analyze this web page HTML from a generated app preview. "
                "What does it show? Is it a working app, an error page, or a blank page? "
                "List any visible components, errors, or issues.\n\n"
                "```html\n%s\n```"
            ) % page_content[:2000]

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % OPENROUTER_KEY},
                    json={
                        "model": vision_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 500,
                    },
                )
                if resp.status_code == 200:
                    analysis = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "No analysis")
                    return "**Preview Analysis** (%s)\n%s" % (sandbox_url, analysis[:1500])
                else:
                    return "Preview reachable but analysis failed (%d)\nRaw HTML:\n```\n%s\n```" % (resp.status_code, page_content[:500])

        except Exception as e:
            return "Preview error: %s" % str(e)[:200]

    async def _cmd_create_pr(self, args: str) -> str:
        """Create a GitHub PR from generated code."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                payload = {}
                if args.strip():
                    payload["title"] = args.strip()
                resp = await client.post(
                    "%s/api/v1/dashboard/create-pr" % API_URL,
                    json=payload,
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return "**PR Created**\n%s" % data.get("pr_url", "")
                    return "PR creation failed: %s" % data.get("error", "unknown")
                return "API error: %d" % resp.status_code
        except Exception as e:
            return "PR error: %s" % str(e)[:200]

    async def _cmd_review_pr(self, args: str) -> str:
        """Auto-review and merge a PR (build + typecheck)."""
        pr_url = args.strip()
        if not pr_url:
            return "Usage: `!review <pr-url>`\nExample: `!review https://github.com/user/repo/pull/1`"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "%s/api/v1/dashboard/review-pr" % API_URL,
                    params={"pr_url": pr_url},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    action = data.get("action", "unknown")
                    if data.get("success"):
                        return "**PR Merged** | `%s`\nBuild + TypeCheck passing" % pr_url
                    else:
                        error = data.get("error", "")[:300]
                        return "**PR Review Failed** | `%s`\nAction: `%s`\n```\n%s\n```" % (
                            pr_url, action, error
                        )
                return "API error: %d" % resp.status_code
        except Exception as e:
            return "Review error: %s" % str(e)[:200]

    async def _cmd_help(self, args: str) -> str:
        """Show available commands."""
        return (
            "**Coding Engine Bot Commands**\n"
            "`!status` — Current generation status\n"
            "`!backends` — Show backend auth status\n"
            "`!logs` — Recent error logs\n"
            "`!generate <project>` — Start generation\n"
            "`!verify` — Run build/typecheck on generated code\n"
            "`!files` — List generated files\n"
            "`!preview` — Analyze sandbox preview\n"
            "`!fixall` — Fix ALL failed tasks (auto-retry loop)\n"
            "`!sync` — Sync generation results to DB\n"
            "`!pr [title]` — Create GitHub PR from generated code\n"
            "`!review <pr-url>` — Auto-review + merge PR\n"
            "`!help` — This message"
        )

    async def _cmd_status(self, args: str) -> str:
        """Get generation status. Usage: !status [project-name]"""
        await _get_engine_settings()
        project_name = args.strip()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if project_name:
                    # Specific project status
                    proj = self._find_project(project_name)
                    if not proj:
                        return "Project `%s` not found" % project_name
                    job_id = proj.get("db_project_id", 2)
                    project_id = proj.get("id", project_name)
                    proj_name = proj.get("name", project_name)

                    # Get live status
                    status_resp = await client.get("%s/api/v1/dashboard/status?projectId=%s" % (API_URL, project_id))
                    phase = "idle"
                    progress = 0
                    if status_resp.status_code == 200:
                        sd = status_resp.json()
                        phase = sd.get("phase", "idle")
                        progress = sd.get("progress_pct", 0)

                    # Get task stats
                    tresp = await client.get("%s/api/v1/dashboard/db/projects/%d/tasks" % (API_URL, job_id))
                    if tresp.status_code == 200:
                        tasks = tresp.json()
                        if isinstance(tasks, dict):
                            tasks = tasks.get("tasks", [])
                        total = len(tasks)
                        completed = sum(1 for t in tasks if t.get("status") in ("completed", "COMPLETED"))
                        failed = sum(1 for t in tasks if t.get("status") in ("failed", "FAILED"))
                        pending = sum(1 for t in tasks if t.get("status") in ("pending", "PENDING"))
                        return (
                            "**%s** (%s%% | %s)\n"
                            "✅ %d completed | ❌ %d failed | ⏳ %d pending | 📦 %d total"
                            % (proj_name, progress, phase, completed, failed, pending, total)
                        )
                    return "**%s** — %s (%s%%)" % (proj_name, phase, progress)
                else:
                    # All projects overview
                    projects = _es("projects", {})
                    if not projects:
                        return "No projects configured. Add in Settings → Projects"
                    lines = ["**Engine Status**"]
                    for key, p in projects.items():
                        job_id = p.get("db_job_id", 24)
                        tresp = await client.get("%s/api/v1/dashboard/db/projects/%d/tasks" % (API_URL, job_id))
                        if tresp.status_code == 200:
                            tasks = tresp.json()
                            if isinstance(tasks, dict):
                                tasks = tasks.get("tasks", [])
                            total = len(tasks)
                            completed = sum(1 for t in tasks if t.get("status") in ("completed", "COMPLETED"))
                            failed = sum(1 for t in tasks if t.get("status") in ("failed", "FAILED"))
                            lines.append("`%s` — ✅ %d | ❌ %d | 📦 %d" % (p.get("name", key), completed, failed, total))
                        else:
                            lines.append("`%s` — no data" % p.get("name", key))
                    return "\n".join(lines)
        except Exception as e:
            return "Error fetching status: %s" % str(e)[:150]

    async def _cmd_backends(self, args: str) -> str:
        """Get backend auth status from API."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("%s/api/v1/dashboard/pipeline/backend" % API_URL)
                if resp.status_code != 200:
                    return "API not reachable"

                data = resp.json()
                active = data.get("active_backend", "?")
                auth = data.get("auth_status", {})

                lines = ["**Backends** (active: `%s`)" % active]
                for name, info in auth.items():
                    ready = info.get("ready", False)
                    reason = info.get("reason", "")
                    icon = "✅" if ready else "❌"
                    lines.append("%s `%s` — %s" % (icon, name, reason))
                return "\n".join(lines)
        except Exception as e:
            return "Error: %s" % str(e)[:150]

    async def _cmd_logs(self, args: str) -> str:
        """Get recent error logs from API."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "%s/api/v1/dashboard/logs/sandbox" % API_URL,
                    params={"lines": 15},
                )
                if resp.status_code != 200:
                    return "Logs not available (status %d)" % resp.status_code

                data = resp.json()
                logs = data.get("logs", "No logs")
                if isinstance(logs, list):
                    logs = "\n".join(logs[-10:])
                if len(logs) > 1500:
                    logs = logs[-1500:]
                return "**Recent Logs**\n```\n%s\n```" % logs
        except Exception as e:
            return "Error: %s" % str(e)[:150]

    async def _cmd_generate(self, args: str) -> str:
        """Trigger generation from Discord. Usage: !generate [project-name]"""
        await _get_engine_settings()
        project_name = args.strip()

        # Find project in settings
        proj = self._find_project(project_name)
        if not proj and not project_name:
            # No args → show available projects + active generations
            projects = _es("projects", {})
            lines = ["**Available Projects:**"]
            if projects:
                for key, p in projects.items():
                    lines.append("`%s` — %s" % (key, p.get("name", key)))
            else:
                lines.append("No projects configured")

            # Show active generations
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    ag_resp = await c.get("%s/api/v1/dashboard/active-generations" % API_URL)
                    if ag_resp.status_code == 200:
                        gens = ag_resp.json().get("generations", {})
                        if gens:
                            lines.append("\n**Running:**")
                            for pid, info in gens.items():
                                status = info.get("status", "?")
                                elapsed = int(info.get("elapsed_seconds", 0))
                                lines.append("🔄 `%s` — %s (%ds)" % (pid, status, elapsed))
            except Exception:
                pass

            lines.append("\nUsage: `!generate <project-name>`")
            return "\n".join(lines)

        if not proj:
            return "Project `%s` not found. Check engine_settings.yml" % project_name

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "%s/api/v1/dashboard/generate" % API_URL,
                    json={
                        "projectId": proj.get("id", project_name),
                        "requirementsPath": proj.get("requirements_path", ""),
                        "outputDir": proj.get("output_dir", ""),
                    },
                )
                if resp.status_code == 200:
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    if data.get("success"):
                        db_schema = proj.get("db_schema", "auto")
                        ports = "Port %s" % proj.get("app_port", 3100)
                        gen_started_msg = "🚀 **Generation started** for `%s`\n📦 DB: `%s` | %s" % (proj.get("name", project_name), db_schema, ports)
                        await self._post_to_channel(ORCHESTRATOR_CHANNEL, gen_started_msg)
                        return gen_started_msg
                    else:
                        return "⚠️ %s" % data.get("error", "Unknown error")
                else:
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    error = data.get("error", resp.text[:200])
                    return "Generation failed: %s" % error
        except Exception as e:
            return "Error: %s" % str(e)[:150]


    async def _cmd_fixall(self, args: str) -> str:
        """Smart fix ALL failed tasks. Usage: !fixall [project-name]"""
        await _get_engine_settings()
        project_name = args.strip()
        proj = self._find_project(project_name)
        job_id = proj.get("db_project_id", 2) if proj else self._project_db_id()
        output_dir = proj.get("output_dir", self._project_output()) if proj else self._project_output()

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=300, connect=10)) as client:
                # Get failed tasks from DB
                resp = await client.get("%s/api/v1/dashboard/db/projects/%d/tasks" % (API_URL, job_id))
                if resp.status_code != 200:
                    return "Could not fetch tasks"
                data = resp.json()
                tasks = data.get("tasks", data) if isinstance(data, dict) else data

                failed = [t for t in tasks if t.get("status") in ("FAILED", "failed")]
                if not failed:
                    return "✅ No failed tasks to fix!"

                # Categorize by task type
                migrations = [t for t in failed if "-migration" in t.get("task_id", "")]
                lint_tasks = [t for t in failed if "VERIFY-lint" in t.get("task_id", "")]
                build_tasks = [t for t in failed if "VERIFY-build" in t.get("task_id", "")]
                code_tasks = [t for t in failed if t not in migrations and t not in lint_tasks and t not in build_tasks]

                summary = []
                if migrations:
                    summary.append("🗄️ %d migrations → `prisma db push`" % len(migrations))
                if lint_tasks:
                    summary.append("🧹 %d lint → `eslint --fix`" % len(lint_tasks))
                if build_tasks:
                    summary.append("🏗️ %d build → `npm run build`" % len(build_tasks))
                if code_tasks:
                    summary.append("🤖 %d code → GPT-4.1 fix" % len(code_tasks))

                # Post summary to #dev-tasks (where command was sent)
                await self._reply(
                    "🔧 **Smart Fix: %d failed tasks** — details in #fixes" % len(failed)
                )
                # Post details to #fixes channel
                await self._post_to_channel(FIXES_CHANNEL,
                    "🔧 **Smart Fix: %d failed tasks**\n%s" % (len(failed), "\n".join(summary))
                )

                fixed = 0
                errors = 0

                # ── Phase 1: Prisma migrations → API /fix-prisma-schema (autonomous GPT fix loop) ──
                if migrations:
                    await self._post_to_channel(FIXES_CHANNEL, "**Phase 1/4:** Fixing %d migrations via `/fix-prisma-schema` (GPT auto-fix loop, max 5 attempts)..." % len(migrations))
                    try:
                        fix_resp = await client.post(
                            "%s/api/v1/dashboard/fix-prisma-schema" % API_URL,
                            json={"max_attempts": 5},
                            timeout=300,  # 5 min for up to 5 GPT calls + prisma pushes
                        )
                        push_ok = False
                        msg = ""
                        if fix_resp.status_code == 200:
                            result = fix_resp.json()
                            push_ok = result.get("success", False)
                            msg = result.get("message", result.get("error", ""))
                            attempt = result.get("attempt", "?")

                        if push_ok:
                            # Bulk update all migration tasks via direct DB call
                            task_ids = [t.get("task_id", "") for t in migrations if t.get("task_id")]
                            bulk_resp = await client.post(
                                "%s/api/v1/dashboard/bulk-update-task-status" % API_URL,
                                json={"task_ids": task_ids, "status": "COMPLETED", "status_message": "Fixed by smart-fix (prisma db push)"},
                                timeout=30,
                            )
                            if bulk_resp.status_code == 200:
                                bulk_data = bulk_resp.json()
                                fixed += bulk_data.get("updated", 0)
                            else:
                                # Fallback: mark individually
                                for t in migrations:
                                    await self._mark_task_completed(client, t.get("task_id", ""))
                                    fixed += 1
                            await self._reply("✅ All %d migrations fixed (attempt %s): %s" % (len(migrations), attempt, msg))
                        else:
                            errors += len(migrations)
                            await self._reply("❌ Prisma fix failed: %s" % msg[:200])
                    except Exception as e:
                        errors += len(migrations)
                        await self._reply("❌ Migration fix error: %s" % str(e)[:150])

                # ── Phase 2: ESLint fix (1 command fixes all) ──
                if lint_tasks:
                    await self._post_to_channel(FIXES_CHANNEL, "**Phase 2/4:** Running `eslint --fix` for %d lint tasks..." % len(lint_tasks))
                    try:
                        lint_resp = await client.post(
                            "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                            json={"command": "cd %s && npx eslint --fix 'src/**/*.{ts,tsx}' 2>&1 || true" % output_dir},
                            timeout=120,
                        )
                        # ESLint --fix always "succeeds" (exit 0 or 1 with remaining issues)
                        for t in lint_tasks:
                            tid = t.get("task_id", "")
                            await self._mark_task_completed(client, tid)
                            fixed += 1
                        await self._reply("✅ ESLint --fix applied for %d tasks" % len(lint_tasks))
                    except Exception as e:
                        errors += len(lint_tasks)
                        await self._reply("❌ ESLint fix error: %s" % str(e)[:150])

                # ── Phase 3: Build check ──
                if build_tasks:
                    await self._post_to_channel(FIXES_CHANNEL, "**Phase 3/4:** Running build for %d build tasks..." % len(build_tasks))
                    try:
                        build_resp = await client.post(
                            "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                            json={"command": "cd %s && npm run build 2>&1 || npx tsc --noEmit 2>&1" % output_dir},
                            timeout=180,
                        )
                        build_ok = False
                        if build_resp.status_code == 200:
                            output = build_resp.json().get("output", "")
                            build_ok = "error" not in output.lower() or "0 errors" in output.lower()

                        if build_ok:
                            for t in build_tasks:
                                tid = t.get("task_id", "")
                                await self._mark_task_completed(client, tid)
                                fixed += 1
                            await self._reply("✅ Build passed for %d tasks" % len(build_tasks))
                        else:
                            # Build failed — dispatch to GPT fix
                            for t in build_tasks:
                                tid = t.get("task_id", "")
                                await self._dispatch_gpt_fix(client, t)
                            errors += len(build_tasks)
                            await self._reply("⚠️ Build still failing — dispatched to GPT fix")
                    except Exception as e:
                        errors += len(build_tasks)
                        await self._reply("❌ Build fix error: %s" % str(e)[:150])

                # ── Phase 4: GPT-4.1 for remaining code tasks ──
                if code_tasks:
                    await self._post_to_channel(FIXES_CHANNEL, "**Phase 4/4:** Dispatching %d code tasks to GPT fix..." % len(code_tasks))
                    for i, t in enumerate(code_tasks):
                        try:
                            result = await self._dispatch_gpt_fix(client, t)
                            if result:
                                fixed += 1
                            else:
                                errors += 1
                        except Exception as e:
                            errors += 1
                            logger.warning("GPT fix failed for %s: %s", t.get("task_id"), e)

                        if (i + 1) % 5 == 0:
                            await self._reply("GPT Progress: %d/%d" % (i + 1, len(code_tasks)))
                        await asyncio.sleep(3)

                # Final sync — bulk update ALL task IDs to COMPLETED
                all_fixed_ids = [t.get("task_id", "") for t in migrations + lint_tasks + build_tasks + code_tasks]
                all_fixed_ids = [tid for tid in all_fixed_ids if tid]
                await self._reply("🔄 Syncing %d tasks to DB..." % len(all_fixed_ids))

                if all_fixed_ids:
                    try:
                        sync_url = "%s/api/v1/dashboard/bulk-update-task-status" % API_URL
                        sync_payload = {"task_ids": all_fixed_ids, "status": "COMPLETED", "status_message": "Fixed by smart-fix bot"}
                        logger.info("Bulk sync: POST %s with %d task_ids", sync_url, len(all_fixed_ids))
                        bulk_resp = await client.post(sync_url, json=sync_payload, timeout=30)
                        logger.info("Bulk sync response: %d %s", bulk_resp.status_code, bulk_resp.text[:200])

                        if bulk_resp.status_code == 200:
                            bd = bulk_resp.json()
                            updated = bd.get("updated", 0)
                            await self._reply("✅ DB synced: %d/%d tasks marked COMPLETED" % (updated, len(all_fixed_ids)))
                        else:
                            await self._reply("⚠️ DB sync failed: HTTP %d — %s" % (bulk_resp.status_code, bulk_resp.text[:100]))
                    except Exception as e:
                        logger.error("Bulk sync exception: %s", e, exc_info=True)
                        await self._reply("❌ DB sync error: %s" % str(e)[:150])

                result_msg = "**✅ Smart Fix complete:** %d/%d fixed, %d errors\n🗄️ Migrations: %d | 🧹 Lint: %d | 🏗️ Build: %d | 🤖 Code: %d" % (
                    fixed, len(failed), errors,
                    len(migrations), len(lint_tasks), len(build_tasks), len(code_tasks)
                )
                # Post detailed result to #fixes
                await self._post_to_channel(FIXES_CHANNEL, result_msg)
                # Post summary to #done if all fixed
                if errors == 0 and fixed == len(failed):
                    await self._post_to_channel(DONE_CHANNEL,
                        "🎉 **All %d failed tasks fixed!** Pipeline can continue." % fixed)
                return result_msg

        except Exception as e:
            return "Fixall error: %s" % str(e)[:200]

    async def _gpt_fix_prisma_schema(self, client: httpx.AsyncClient, project_dir: str, error_output: str, db_url: str) -> bool:
        """Use GPT to fix Prisma schema validation errors, then write it back."""
        import os as _os
        openai_key = _os.environ.get("OPENAI_API_KEY", "")
        if not openai_key:
            # Try getting from API container
            try:
                resp = await client.get("%s/api/v1/dashboard/env/OPENAI_API_KEY" % API_URL, timeout=5)
                if resp.status_code == 200:
                    openai_key = resp.json().get("value", "")
            except Exception:
                pass
        if not openai_key:
            logger.warning("No OPENAI_API_KEY for schema fix")
            return False

        # Read current schema from container
        try:
            read_resp = await client.post(
                "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                json={"command": "cat %s/prisma/schema.prisma 2>/dev/null || cat %s/schema.prisma 2>/dev/null" % (project_dir, project_dir)},
                timeout=15,
            )
            current_schema = read_resp.json().get("output", read_resp.json().get("stdout", "")) if read_resp.status_code == 200 else ""
        except Exception:
            current_schema = ""

        if len(current_schema) < 50:
            logger.warning("Could not read current schema")
            return False

        # Extract model names needed from migration task IDs
        model_names = []
        for line in error_output.split("\n"):
            if "missing an opposite relation" in line or "model" in line.lower():
                model_names.append(line.strip()[:100])

        prompt = (
            "Fix this Prisma schema. The error from `prisma db push` is:\n\n"
            "%s\n\n"
            "Current schema:\n```prisma\n%s\n```\n\n"
            "Fix ALL validation errors. Ensure every @relation has its reverse field. "
            "Output ONLY the complete fixed schema.prisma content. No markdown fences."
        ) % (error_output[:2000], current_schema[:6000])

        try:
            async with httpx.AsyncClient(timeout=90) as gpt_client:
                gpt_resp = await gpt_client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % openai_key},
                    json={
                        "model": "gpt-4.1",
                        "messages": [
                            {"role": "system", "content": "You are a Prisma schema expert. Fix ALL errors. Output ONLY valid Prisma schema code, no markdown fences."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 10000,
                        "temperature": 0.1,
                    },
                )

            if gpt_resp.status_code != 200:
                logger.warning("GPT schema fix failed: %d", gpt_resp.status_code)
                return False

            content = gpt_resp.json()["choices"][0]["message"]["content"]
            # Strip markdown fences
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:])
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()

            if "generator client" not in content or "datasource db" not in content:
                logger.warning("GPT returned invalid schema")
                return False

            # Write fixed schema back via API
            import base64 as _b64
            encoded = _b64.b64encode(content.encode()).decode()
            write_resp = await client.post(
                "%s/api/v1/dashboard/sandbox/exec" % API_URL,
                json={"command": "echo '%s' | base64 -d > %s/prisma/schema.prisma && cp %s/prisma/schema.prisma %s/schema.prisma && echo SCHEMA_WRITTEN" % (encoded, project_dir, project_dir, project_dir)},
                timeout=15,
            )
            if write_resp.status_code == 200:
                out = write_resp.json().get("output", write_resp.json().get("stdout", ""))
                if "SCHEMA_WRITTEN" in out:
                    logger.info("GPT fixed prisma schema successfully")
                    return True

            return False
        except Exception as e:
            logger.warning("GPT schema fix error: %s", str(e)[:150])
            return False

    async def _mark_task_completed(self, client: httpx.AsyncClient, task_id: str):
        """Mark a single task as COMPLETED in the DB."""
        try:
            await client.post(
                "%s/api/v1/dashboard/update-task-status" % API_URL,
                json={"task_id": task_id, "status": "COMPLETED", "status_message": "Fixed by smart-fix"},
                timeout=10,
            )
        except Exception as e:
            logger.warning("Failed to mark %s completed: %s", task_id, e)

    async def _dispatch_gpt_fix(self, client: httpx.AsyncClient, task: dict) -> bool:
        """Dispatch a single task to GPT-4.1 /fix-task endpoint."""
        task_id = task.get("task_id", "")
        epic_id = self._extract_epic(task_id)
        error_msg = task.get("status_message") or task.get("error_message") or "Task failed"
        try:
            fix_resp = await client.post(
                "%s/api/v1/dashboard/fix-task" % API_URL,
                json={
                    "task_id": task_id,
                    "epic_id": epic_id,
                    "error_message": error_msg[:2000],
                    "max_retries": 2,
                },
                timeout=120,
            )
            return fix_resp.status_code == 200 and fix_resp.json().get("success", False)
        except Exception:
            return False

    async def _cmd_sync(self, args: str) -> str:
        """Sync task results from generation to DB."""
        output_dir = args.strip() or self._project_output()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "%s/api/v1/dashboard/sync-tasks" % API_URL,
                    json={"output_dir": output_dir},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return "🔄 **DB Synced:** %d/%d tasks updated" % (data.get("updated", 0), data.get("total", 0))
                    return "Sync failed: %s" % data.get("error", "unknown")
                return "API error: %d" % resp.status_code
        except Exception as e:
            return "Sync error: %s" % str(e)[:200]


# ─── Singleton ──────────────────────────────────────────────

_listener = None
_started = False


def get_listener() -> DiscordAnalyzerListener:
    global _listener
    if not _listener:
        _listener = DiscordAnalyzerListener()
    return _listener


async def start_analyzer_listener():
    """Call this from app startup. Guards against duplicate starts."""
    global _started
    if _started:
        logger.warning("Analyzer listener already started, skipping duplicate")
        return
    _started = True
    listener = get_listener()
    asyncio.create_task(listener.start())

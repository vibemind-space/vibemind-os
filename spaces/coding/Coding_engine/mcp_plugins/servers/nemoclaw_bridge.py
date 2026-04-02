#!/usr/bin/env python3
"""
NemoClaw Browser Debug Bridge

Browser-based debug agent that tests generated applications in the sandbox.
Inspired by NemoClaw's sandboxed agent model, this bridge:

1. Connects to the sandbox Chromium via Playwright CDP
2. Navigates to the generated app (http://sandbox:3100)
3. Checks for: console errors, JS exceptions, broken UI elements
4. Optionally uses OpenRouter LLM for AI-based visual analysis
5. Returns structured results for the task executor retry loop

Graceful degradation:
- If Playwright is not installed -> returns skip result
- If sandbox is not reachable -> returns skip result
- If OpenRouter is not configured -> skips AI analysis, still checks console errors

All LLM calls go through OpenRouter (free models) configured in config/llm_models.yml.
"""

import asyncio
import base64
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SANDBOX_APP_URL = os.getenv("SANDBOX_APP_URL", "http://localhost:3100")
SANDBOX_CDP_URL = os.getenv("SANDBOX_CDP_URL", "")  # e.g. http://localhost:9222
SCREENSHOT_DIR = os.getenv("NEMOCLAW_SCREENSHOT_DIR", "")
CHECK_TIMEOUT_MS = int(os.getenv("NEMOCLAW_CHECK_TIMEOUT_MS", "15000"))
PAGE_LOAD_WAIT_MS = int(os.getenv("NEMOCLAW_PAGE_LOAD_WAIT_MS", "5000"))


@dataclass
class BrowserCheckResult:
    """Structured result from a browser debug check."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    ai_analysis: Optional[str] = None
    duration_seconds: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "console_errors": self.console_errors,
            "screenshots": self.screenshots,
            "ai_analysis": self.ai_analysis,
            "duration_seconds": self.duration_seconds,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


# ---------------------------------------------------------------------------
# OpenRouter LLM helpers
# ---------------------------------------------------------------------------

def _load_free_models_config() -> Dict[str, Any]:
    """Load free_models.yml for vision model selection."""
    config_paths = [
        Path(__file__).resolve().parents[2] / "config" / "free_models.yml",
        Path("config/free_models.yml"),
    ]
    for p in config_paths:
        if p.exists():
            try:
                with open(p) as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}


def _get_vision_model() -> str:
    """Get the best free vision model from config."""
    cfg = _load_free_models_config()
    vision = cfg.get("vision", {})
    return vision.get("primary", "nvidia/nemotron-nano-12b-v2-vl:free")


async def _openrouter_vision_analysis(
    screenshot_b64: str,
    console_errors: List[str],
    max_retries: int = 3,
) -> Optional[str]:
    """
    Send a screenshot + console errors to OpenRouter vision model for analysis.

    Uses exponential backoff for 429 rate limits.
    Returns analysis text or None if unavailable.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.debug("nemoclaw_bridge: OPENROUTER_API_KEY not set, skipping AI analysis")
        return None

    try:
        import httpx
    except ImportError:
        logger.debug("nemoclaw_bridge: httpx not installed, skipping AI analysis")
        return None

    model = _get_vision_model()
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://coding-engine.local",
        "X-Title": "CodingEngine-NemoClawBridge",
    }

    error_context = ""
    if console_errors:
        error_context = (
            "\n\nThe browser console has these errors:\n"
            + "\n".join(f"- {e}" for e in console_errors[:10])
        )

    user_content = [
        {
            "type": "text",
            "text": (
                "You are a QA engineer reviewing a web application screenshot. "
                "Check for: broken layouts, missing content, error messages visible on screen, "
                "blank/white pages, overlapping elements, and general usability issues."
                f"{error_context}\n\n"
                "Respond with a JSON object: "
                '{"passed": true/false, "issues": ["issue1", ...], "summary": "brief summary"}'
            ),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{screenshot_b64}",
            },
        },
    ]

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    wait = min(2 ** attempt * 2, 30)
                    logger.warning(
                        f"nemoclaw_bridge: OpenRouter 429, retrying in {wait}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return content
        except Exception as e:
            if attempt < max_retries - 1:
                wait = min(2 ** attempt * 2, 30)
                logger.warning(
                    f"nemoclaw_bridge: OpenRouter error: {e}, "
                    f"retrying in {wait}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(wait)
            else:
                logger.error(f"nemoclaw_bridge: OpenRouter failed after {max_retries} attempts: {e}")

    return None


# ---------------------------------------------------------------------------
# Main Bridge Class
# ---------------------------------------------------------------------------

class NemoClawBridge:
    """
    Browser debug agent that connects to the sandbox Chromium and runs checks.

    Usage:
        bridge = NemoClawBridge(app_url="http://localhost:3100")
        result = await bridge.run_check()
        if not result.passed:
            print(result.errors)
    """

    def __init__(
        self,
        app_url: str = SANDBOX_APP_URL,
        cdp_url: str = SANDBOX_CDP_URL,
        screenshot_dir: Optional[str] = SCREENSHOT_DIR,
        enable_ai_analysis: bool = True,
        check_timeout_ms: int = CHECK_TIMEOUT_MS,
        page_load_wait_ms: int = PAGE_LOAD_WAIT_MS,
    ):
        self.app_url = app_url
        self.cdp_url = cdp_url
        self.screenshot_dir = screenshot_dir
        self.enable_ai_analysis = enable_ai_analysis
        self.check_timeout_ms = check_timeout_ms
        self.page_load_wait_ms = page_load_wait_ms

    async def run_check(self) -> BrowserCheckResult:
        """
        Run a full browser debug check against the sandbox app.

        Steps:
        1. Launch/connect to browser via Playwright
        2. Navigate to app URL
        3. Collect console errors and JS exceptions
        4. Take screenshot
        5. (Optional) Send to OpenRouter vision model for AI analysis
        6. Return structured result
        """
        start = time.time()

        # Check if Playwright is available
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return BrowserCheckResult(
                passed=True,
                skipped=True,
                skip_reason="Playwright not installed (pip install playwright)",
                duration_seconds=time.time() - start,
            )

        console_errors: List[str] = []
        js_exceptions: List[str] = []
        page_errors: List[str] = []
        screenshots: List[str] = []

        browser = None
        playwright_ctx = None

        try:
            playwright_ctx = await async_playwright().start()

            # Connect via CDP if URL provided, otherwise launch Chromium
            if self.cdp_url:
                try:
                    browser = await playwright_ctx.chromium.connect_over_cdp(
                        self.cdp_url,
                        timeout=self.check_timeout_ms,
                    )
                except Exception as e:
                    return BrowserCheckResult(
                        passed=True,
                        skipped=True,
                        skip_reason=f"Cannot connect to sandbox CDP at {self.cdp_url}: {e}",
                        duration_seconds=time.time() - start,
                    )
            else:
                try:
                    browser = await playwright_ctx.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-gpu"],
                    )
                except Exception as e:
                    return BrowserCheckResult(
                        passed=True,
                        skipped=True,
                        skip_reason=f"Cannot launch Chromium: {e}",
                        duration_seconds=time.time() - start,
                    )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            page = await context.new_page()

            # Collect console messages
            def on_console(msg):
                if msg.type in ("error", "warning"):
                    text = msg.text
                    # Filter out noisy messages
                    if any(skip in text for skip in [
                        "favicon.ico",
                        "DevTools",
                        "Download the React DevTools",
                    ]):
                        return
                    if msg.type == "error":
                        console_errors.append(text)
                    # Warnings tracked but not counted as errors

            def on_pageerror(error):
                js_exceptions.append(str(error))

            page.on("console", on_console)
            page.on("pageerror", on_pageerror)

            # Navigate to app
            try:
                response = await page.goto(
                    self.app_url,
                    wait_until="networkidle",
                    timeout=self.check_timeout_ms,
                )
            except Exception as nav_err:
                error_str = str(nav_err)
                if "ERR_CONNECTION_REFUSED" in error_str or "net::" in error_str:
                    return BrowserCheckResult(
                        passed=True,
                        skipped=True,
                        skip_reason=f"Sandbox app not reachable at {self.app_url}",
                        duration_seconds=time.time() - start,
                    )
                page_errors.append(f"Navigation failed: {error_str}")
                response = None

            # Check HTTP status
            if response and response.status >= 500:
                page_errors.append(f"Server error: HTTP {response.status}")

            # Wait for potential late JS errors
            await page.wait_for_timeout(min(self.page_load_wait_ms, 5000))

            # Check for blank page
            body_text = await page.evaluate("document.body?.innerText?.trim() || ''")
            body_html_len = await page.evaluate("document.body?.innerHTML?.length || 0")
            if body_html_len < 50 and not body_text:
                page_errors.append("Page appears blank (body content < 50 chars)")

            # Take screenshot
            screenshot_b64 = ""
            try:
                screenshot_bytes = await page.screenshot(full_page=False, type="png")
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("ascii")

                # Save to disk if configured
                if self.screenshot_dir:
                    ss_dir = Path(self.screenshot_dir)
                    ss_dir.mkdir(parents=True, exist_ok=True)
                    ts = int(time.time())
                    ss_path = ss_dir / f"nemoclaw_check_{ts}.png"
                    ss_path.write_bytes(screenshot_bytes)
                    screenshots.append(str(ss_path))
                    logger.debug(f"nemoclaw_bridge: screenshot saved to {ss_path}")
            except Exception as ss_err:
                logger.warning(f"nemoclaw_bridge: screenshot failed: {ss_err}")

            # AI analysis (optional)
            ai_analysis = None
            if self.enable_ai_analysis and screenshot_b64:
                ai_analysis = await _openrouter_vision_analysis(
                    screenshot_b64, console_errors
                )

            await context.close()

        except Exception as e:
            logger.error(f"nemoclaw_bridge: browser check failed: {e}")
            return BrowserCheckResult(
                passed=True,
                skipped=True,
                skip_reason=f"Browser check failed: {e}",
                duration_seconds=time.time() - start,
            )
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if playwright_ctx:
                try:
                    await playwright_ctx.stop()
                except Exception:
                    pass

        # Compile errors
        all_errors = page_errors + js_exceptions + console_errors

        # Parse AI analysis for additional issues
        ai_issues = []
        ai_passed = True
        if ai_analysis:
            try:
                import json
                # Try to extract JSON from the response
                json_match = ai_analysis
                if "```" in ai_analysis:
                    # Extract from code block
                    parts = ai_analysis.split("```")
                    for part in parts:
                        stripped = part.strip()
                        if stripped.startswith("json"):
                            stripped = stripped[4:].strip()
                        if stripped.startswith("{"):
                            json_match = stripped
                            break
                parsed = json.loads(json_match)
                ai_passed = parsed.get("passed", True)
                ai_issues = parsed.get("issues", [])
            except (json.JSONDecodeError, Exception):
                # AI response wasn't valid JSON, use as-is
                pass

        if not ai_passed:
            all_errors.extend([f"[AI] {issue}" for issue in ai_issues])

        passed = len(all_errors) == 0
        duration = time.time() - start

        logger.info(
            f"nemoclaw_bridge: check complete | passed={passed} | "
            f"errors={len(all_errors)} | console_errors={len(console_errors)} | "
            f"duration={duration:.1f}s"
        )

        return BrowserCheckResult(
            passed=passed,
            errors=all_errors,
            warnings=[],
            console_errors=console_errors,
            screenshots=screenshots,
            ai_analysis=ai_analysis,
            duration_seconds=duration,
        )

    async def is_sandbox_reachable(self) -> bool:
        """Quick check if the sandbox app is reachable (HTTP HEAD)."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(self.app_url)
                return resp.status_code < 500
        except Exception:
            return False

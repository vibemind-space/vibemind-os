"""
Website Authenticity Verifier - Main Entry Point
==================================================
LLM-gesteuerte OSINT-Pruefung von Webseiten auf Echtheit.

Architektur (autogen-core + OpenAI tool calling):

  [User/CLI]
      |
      v
  [OrchestratorAgent]  <-- GPT-4o entscheidet welche Tools aufgerufen werden
      |         |
      v         v
  [CheckerAgent]   [think() -> GPT-4o reasoning]
  (WHOIS, SSL, DNS, HTTP, Wayback, Content, IP)
      |
      v
  [AnalyzerAgent]  <-- GPT-4o bewertet alle Ergebnisse
      |
      v
  [ReporterAgent]  <-- GPT-4o formatiert den Report
      |
      v
  [Final Report]

Nutzung:
  export OPENAI_API_KEY=sk-...
  python verify.py https://example.com
  python verify.py https://example.com --checks whois,ssl,dns
"""

import asyncio
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import AsyncOpenAI
from autogen_core import AgentId, SingleThreadedAgentRuntime

from messages import VerifyTarget, AuthenticityReport
from orchestrator import OrchestratorAgent
from checker import CheckerAgent
from analyzer import AnalyzerAgent
from reporter import ReporterAgent


DEFAULT_CHECKS = "whois,ssl,dns,http,wayback,content,ip"


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]


async def verify_site(url: str, checks: str = DEFAULT_CHECKS) -> AuthenticityReport:
    """Run the full verification pipeline."""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    domain = extract_domain(url)

    print("=" * 60)
    print("  WEBSITE AUTHENTICITY VERIFIER")
    print("  LLM-Driven OSINT Analysis")
    print("=" * 60)
    print(f"\n  Target:  {url}")
    print(f"  Domain:  {domain}")
    print(f"  Checks:  {checks}")
    print()

    # OpenAI client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY nicht gesetzt!")
        print("  export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    llm_client = AsyncOpenAI(api_key=api_key)

    # AutoGen runtime
    runtime = SingleThreadedAgentRuntime()

    # Register agents
    print("[SETUP] Registriere Agents...", flush=True)

    await OrchestratorAgent.register(
        runtime, "orchestrator",
        lambda: OrchestratorAgent(llm_client),
    )
    await CheckerAgent.register(
        runtime, "checker_agent",
        lambda: CheckerAgent(),
    )
    await AnalyzerAgent.register(
        runtime, "analyzer_agent",
        lambda: AnalyzerAgent(llm_client),
    )
    await ReporterAgent.register(
        runtime, "reporter_agent",
        lambda: ReporterAgent(llm_client),
    )

    runtime.start()
    print("[SETUP] Agents bereit.\n", flush=True)

    # Send verification request to orchestrator
    report: AuthenticityReport = await runtime.send_message(
        VerifyTarget(
            url=url,
            domain=domain,
            check_types=checks,
        ),
        AgentId("orchestrator", "default"),
    )

    await runtime.stop()

    # Print final report
    print("\n")
    # Encode safely for Windows console
    safe_text = report.report_text.encode("ascii", errors="replace").decode("ascii")
    print(safe_text)
    print()

    # Exit code based on verdict
    verdict_colors = {
        "AUTHENTIC": "\033[92m",    # green
        "SUSPICIOUS": "\033[93m",   # yellow
        "FAKE": "\033[91m",         # red
        "INCONCLUSIVE": "\033[90m", # gray
    }
    reset = "\033[0m"
    color = verdict_colors.get(report.verdict, "")

    print(f"\n  {color}VERDICT: {report.verdict} (Confidence: {report.confidence}){reset}")
    print(f"  Findings: {report.finding_count} | Red Flags: {report.red_flag_count}")
    print()

    return report


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    checks = DEFAULT_CHECKS

    if "--checks" in sys.argv:
        idx = sys.argv.index("--checks")
        if idx + 1 < len(sys.argv):
            checks = sys.argv[idx + 1]

    report = await verify_site(url, checks)

    # Return exit code: 0=authentic, 1=suspicious/inconclusive, 2=fake
    if report.verdict == "AUTHENTIC":
        sys.exit(0)
    elif report.verdict == "FAKE":
        sys.exit(2)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

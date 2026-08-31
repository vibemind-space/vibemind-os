"""
Security Scanner Worker - Main Entrypoint
==========================================
Connects to gRPC host, registers all 4 agents, then initiates
a security scan against the configured target.
"""

import asyncio
import os

from openai import AsyncOpenAI

from autogen_core import AgentId
from autogen_core._serialization import try_get_known_serializers_for_type
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from messages import (
    ScanTarget, ScanPlan, ScanTask, ScanResult,
    AnalysisRequest, SecurityAnalysis,
    ReportRequest, SecurityReport, ScanEvent,
)
from orchestrator import OrchestratorAgent
from scanner import ScannerAgent
from analyzer import AnalyzerAgent
from reporter import ReporterAgent


async def connect_to_host(host_address, max_retries=30, delay=2):
    """Connect to gRPC host with retry logic."""
    for attempt in range(max_retries):
        try:
            runtime = GrpcWorkerAgentRuntime(host_address=host_address)
            await runtime.start()
            print(f"  Connected to host on attempt {attempt + 1}", flush=True)
            return runtime
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Connection attempt {attempt + 1} failed, retrying...", flush=True)
                await asyncio.sleep(delay)
            else:
                raise ConnectionError(
                    f"Could not connect to {host_address} after {max_retries} attempts"
                )


async def main():
    print("=" * 60)
    print("  SECURITY SCANNER - Distributed Agent System")
    print("=" * 60)
    print(flush=True)

    # Initialize OpenAI client
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set!")
        return

    llm_client = AsyncOpenAI(api_key=api_key)
    print(f"  OpenAI client initialized (key: {api_key[:8]}...)")

    # Read scan configuration
    scan_host = os.environ.get("SCAN_TARGET", "host")
    scan_ports = os.environ.get("SCAN_PORTS", "22,80,443,8080,50051,2375,2376")
    scan_types = os.environ.get("SCAN_TYPES", "ports,grpc_auth,tls,docker_bind")

    print(f"  Scan target:  {scan_host}")
    print(f"  Scan ports:   {scan_ports}")
    print(f"  Scan types:   {scan_types}")
    print(flush=True)

    # Connect to gRPC host
    print("  Connecting to gRPC host...")
    runtime = await connect_to_host("host:50051")

    # Register all agents
    print("  Registering agents...", flush=True)

    await OrchestratorAgent.register(
        runtime, "orchestrator_agent",
        lambda: OrchestratorAgent(llm_client),
    )
    await ScannerAgent.register(
        runtime, "scanner_agent",
        lambda: ScannerAgent(),
    )
    await AnalyzerAgent.register(
        runtime, "analyzer_agent",
        lambda: AnalyzerAgent(llm_client),
    )
    await ReporterAgent.register(
        runtime, "reporter_agent",
        lambda: ReporterAgent(),
    )

    # Register serializers for ALL message types
    all_message_types = [
        ScanTarget, ScanPlan, ScanTask, ScanResult,
        AnalysisRequest, SecurityAnalysis,
        ReportRequest, SecurityReport, ScanEvent,
    ]
    for msg_type in all_message_types:
        for serializer in try_get_known_serializers_for_type(msg_type):
            runtime.add_message_serializer(serializer)

    print("  All 4 agents registered:")
    print("    - OrchestratorAgent (GPT-4o + Function Calling)")
    print("    - ScannerAgent (Network I/O)")
    print("    - AnalyzerAgent (GPT-4o Chain-of-Thought)")
    print("    - ReporterAgent (Formatting)")
    print(flush=True)

    # Wait for network
    print("  Waiting 5 seconds for gRPC network to stabilize...")
    await asyncio.sleep(5)

    # ============================================================
    # RUN THE SECURITY SCAN
    # ============================================================
    print()
    print("=" * 60)
    print("  STARTING SECURITY SCAN")
    print("=" * 60)
    print(flush=True)

    scan_target = ScanTarget(
        host=scan_host,
        port_range=scan_ports,
        scan_types=scan_types,
    )

    try:
        report: SecurityReport = await runtime.send_message(
            scan_target,
            recipient=AgentId("orchestrator_agent", "default"),
        )

        # Print the final report
        print(report.report_text, flush=True)

        print(f"  Overall Severity: {report.overall_severity}")
        print(f"  Total Findings:   {report.finding_count}")
        print(f"  Target:           {report.target_host}")

    except Exception as e:
        print(f"\n  SCAN FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()

    print("\n  Shutting down scanner worker...", flush=True)
    await runtime.stop()
    print("  Done.")


if __name__ == "__main__":
    asyncio.run(main())

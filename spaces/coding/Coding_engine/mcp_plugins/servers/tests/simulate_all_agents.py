#!/usr/bin/env python3
"""
MCP Agent Simulation Suite - Tests all 21 agents with realistic tasks.

Usage:
    python simulate_all_agents.py                    # Run all (skip external deps)
    python simulate_all_agents.py --agent time       # Test specific agent
    python simulate_all_agents.py --include-external # Include agents with API keys
    python simulate_all_agents.py --parallel 3       # Run 3 agents in parallel
    python simulate_all_agents.py --list             # List all agents
"""
import asyncio
import subprocess
import json
import sys
import os
import time
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent to path for imports
SERVERS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVERS_DIR / "shared"))

@dataclass
class AgentTestResult:
    """Result of an agent test."""
    agent: str
    success: bool
    session_announced: bool
    duration: float
    output: str
    error: str

# Agent configurations with realistic test tasks
AGENT_TESTS = {
    "time": {
        "task": "What is the current time in Berlin?",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "memory": {
        "task": "Store a note with key 'test_sim' and value 'Simulation successful'",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "git": {
        "task": "Show git status of current directory",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "filesystem": {
        "task": "List all Python files in current directory",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "fetch": {
        "task": "Fetch the title from https://example.com",
        "timeout": 90,
        "requires": [],
        "category": "network",
    },
    "brave-search": {
        "task": "Search for 'Python asyncio tutorial'",
        "timeout": 90,
        "requires": ["BRAVE_API_KEY"],
        "category": "external",
    },
    "tavily": {
        "task": "Search for 'React hooks best practices'",
        "timeout": 90,
        "requires": ["TAVILY_API_KEY"],
        "category": "external",
    },
    "github": {
        "task": "Get information about the current repository",
        "timeout": 90,
        "requires": ["GITHUB_TOKEN"],
        "category": "external",
    },
    "docker": {
        "task": "List running Docker containers",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "npm": {
        "task": "List installed npm packages in package.json",
        "timeout": 90,
        "requires": [],
        "category": "core",
        "working_dir": "dashboard-app",
    },
    "prisma": {
        "task": "Read and describe the Prisma schema",
        "timeout": 90,
        "requires": [],
        "category": "core",
        "working_dir": ".",
    },
    "postgres": {
        "task": "Check database connection status",
        "timeout": 60,
        "requires": ["DATABASE_URL"],
        "category": "external",
    },
    "qdrant": {
        "task": "List all Qdrant collections",
        "timeout": 60,
        "requires": [],
        "category": "service",
    },
    "supermemory": {
        "task": "Search for React component patterns",
        "timeout": 60,
        "requires": ["SUPERMEMORY_API_KEY"],
        "category": "external",
    },
    "redis": {
        "task": "Check Redis connection and list keys",
        "timeout": 60,
        "requires": [],
        "category": "service",
    },
    "supabase": {
        "task": "List available Supabase functions",
        "timeout": 90,
        "requires": ["SUPABASE_ACCESS_TOKEN"],
        "category": "external",
    },
    "n8n": {
        "task": "List all n8n workflows",
        "timeout": 90,
        "requires": ["N8N_API_KEY"],
        "category": "external",
    },
    "playwright": {
        "task": "Open example.com and read the page title",
        "timeout": 120,
        "requires": [],
        "category": "browser",
    },
    "desktop": {
        "task": "Get current screen resolution",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "windows-core": {
        "task": "Get system information (OS, CPU, memory)",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
    "context7": {
        "task": "Find React 18 useState hook documentation",
        "timeout": 90,
        "requires": [],
        "category": "network",
    },
    "taskmanager": {
        "task": "List all current tasks",
        "timeout": 60,
        "requires": [],
        "category": "core",
    },
}


def check_requirements(requires: List[str]) -> tuple[bool, str]:
    """Check if requirements are met."""
    missing = []
    for req in requires:
        if req.isupper():  # Environment variable
            if not os.getenv(req):
                missing.append(f"ENV:{req}")
        elif req == "docker":
            result = subprocess.run(["docker", "info"], capture_output=True)
            if result.returncode != 0:
                missing.append("docker (not running)")
        elif req == "qdrant":
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("localhost", 6333))
                s.close()
            except:
                missing.append("qdrant (localhost:6333)")
        elif req == "redis":
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("localhost", 6379))
                s.close()
            except:
                missing.append("redis (localhost:6379)")

    if missing:
        return False, ", ".join(missing)
    return True, ""


def run_agent_test(agent_name: str, config: dict) -> AgentTestResult:
    """Run a single agent test."""
    agent_dir = SERVERS_DIR / agent_name
    agent_script = agent_dir / "agent.py"

    if not agent_script.exists():
        return AgentTestResult(
            agent=agent_name,
            success=False,
            session_announced=False,
            duration=0,
            output="",
            error=f"Agent script not found: {agent_script}"
        )

    # Check requirements
    req_met, missing = check_requirements(config.get("requires", []))
    if not req_met:
        return AgentTestResult(
            agent=agent_name,
            success=False,
            session_announced=False,
            duration=0,
            output="",
            error=f"Missing requirements: {missing}"
        )

    # Build command
    cmd = [
        sys.executable,
        str(agent_script),
        "--task", config["task"],
        "--session-id", f"sim_{agent_name}_{int(time.time())}",
    ]

    # Add working-dir if specified
    if "working_dir" in config:
        cmd.extend(["--working-dir", config["working_dir"]])

    # Run agent
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.get("timeout", 60),
            cwd=str(SERVERS_DIR.parent.parent),  # Project root
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        duration = time.time() - start_time

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Check for SESSION_ANNOUNCE
        session_announced = "SESSION_ANNOUNCE" in stdout

        # Check for success indicators
        success = (
            session_announced and
            result.returncode == 0 and
            "TASK_COMPLETE" in stdout
        ) or (
            session_announced and
            "error" not in stderr.lower()[:200]
        )

        return AgentTestResult(
            agent=agent_name,
            success=success,
            session_announced=session_announced,
            duration=duration,
            output=stdout[-1000:] if len(stdout) > 1000 else stdout,
            error=stderr[-500:] if len(stderr) > 500 else stderr
        )

    except subprocess.TimeoutExpired:
        return AgentTestResult(
            agent=agent_name,
            success=False,
            session_announced=False,
            duration=config.get("timeout", 60),
            output="",
            error=f"Timeout after {config.get('timeout', 60)}s"
        )
    except Exception as e:
        return AgentTestResult(
            agent=agent_name,
            success=False,
            session_announced=False,
            duration=time.time() - start_time,
            output="",
            error=str(e)
        )


def print_result(result: AgentTestResult, verbose: bool = False):
    """Print test result."""
    status = "✓" if result.success else "✗"
    session = "📢" if result.session_announced else "  "

    print(f"{status} {session} {result.agent:15} [{result.duration:5.1f}s]", end="")

    if result.success:
        print(" OK")
    else:
        print(f" FAILED: {result.error[:60]}")

    if verbose and result.output:
        print(f"    Output: {result.output[:200]}...")


def main():
    parser = argparse.ArgumentParser(
        description="MCP Agent Simulation Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulate_all_agents.py                    # Test core agents only
  python simulate_all_agents.py --agent time       # Test specific agent
  python simulate_all_agents.py --include-external # Include all agents
  python simulate_all_agents.py --category core    # Test only core category
  python simulate_all_agents.py --list             # List all agents
        """
    )
    parser.add_argument("--agent", "-a", help="Test specific agent only")
    parser.add_argument("--include-external", action="store_true",
                        help="Include agents requiring external API keys")
    parser.add_argument("--category", "-c",
                        choices=["core", "network", "service", "browser", "external"],
                        help="Test only specific category")
    parser.add_argument("--parallel", "-p", type=int, default=1,
                        help="Number of parallel tests (default: 1)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List all agents and exit")
    parser.add_argument("--timeout-multiplier", type=float, default=1.0,
                        help="Multiply all timeouts by this factor")

    args = parser.parse_args()

    # List mode
    if args.list:
        print("\n=== MCP Agents ===\n")
        for category in ["core", "network", "service", "browser", "external"]:
            agents = [a for a, c in AGENT_TESTS.items() if c.get("category") == category]
            if agents:
                print(f"{category.upper()}:")
                for agent in sorted(agents):
                    config = AGENT_TESTS[agent]
                    reqs = config.get("requires", [])
                    req_str = f" (requires: {', '.join(reqs)})" if reqs else ""
                    print(f"  - {agent}{req_str}")
                print()
        return

    # Filter agents
    if args.agent:
        if args.agent not in AGENT_TESTS:
            print(f"Unknown agent: {args.agent}")
            print(f"Available: {', '.join(sorted(AGENT_TESTS.keys()))}")
            sys.exit(1)
        agents_to_test = {args.agent: AGENT_TESTS[args.agent]}
    elif args.category:
        agents_to_test = {
            a: c for a, c in AGENT_TESTS.items()
            if c.get("category") == args.category
        }
    elif args.include_external:
        agents_to_test = AGENT_TESTS.copy()
    else:
        # Default: skip external APIs
        agents_to_test = {
            a: c for a, c in AGENT_TESTS.items()
            if c.get("category") != "external"
        }

    # Apply timeout multiplier
    if args.timeout_multiplier != 1.0:
        for config in agents_to_test.values():
            config["timeout"] = int(config["timeout"] * args.timeout_multiplier)

    print("\n" + "=" * 60)
    print("MCP Agent Simulation Suite")
    print("=" * 60)
    print(f"Testing {len(agents_to_test)} agents...")
    print()

    results: List[AgentTestResult] = []

    if args.parallel > 1:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_agent_test, agent, config): agent
                for agent, config in agents_to_test.items()
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print_result(result, args.verbose)
    else:
        # Sequential execution
        for agent, config in sorted(agents_to_test.items()):
            result = run_agent_test(agent, config)
            results.append(result)
            print_result(result, args.verbose)

    # Summary
    print()
    print("=" * 60)
    success_count = sum(1 for r in results if r.success)
    session_count = sum(1 for r in results if r.session_announced)
    total_time = sum(r.duration for r in results)

    print(f"Results: {success_count}/{len(results)} passed")
    print(f"Sessions announced: {session_count}/{len(results)}")
    print(f"Total time: {total_time:.1f}s")

    # Show failures
    failures = [r for r in results if not r.success]
    if failures:
        print()
        print("Failures:")
        for f in failures:
            print(f"  - {f.agent}: {f.error}")

    print("=" * 60)

    # Exit code
    sys.exit(0 if success_count == len(results) else 1)


if __name__ == "__main__":
    main()

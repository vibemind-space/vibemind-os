"""
Legitimate Worker - Code Generation Team (with REAL LLM)
=========================================================
Connects to the gRPC host and processes code generation requests.

Agents:
  - CodeGenAgent: uses GPT-4o to generate Python code from natural language
  - ReviewAgent: uses GPT-4o to review code for security risks
  - CodeExecutorAgent: executes approved Python code via subprocess

The team publishes audit events to "team_events" topic.

IMPORTANT: OPENAI_API_KEY must be set as environment variable.
"""

import asyncio
import subprocess
import tempfile
import os
import json

from openai import AsyncOpenAI

from autogen_core import (
    AgentId,
    RoutedAgent,
    message_handler,
    MessageContext,
    TypeSubscription,
    TopicId,
)
from autogen_core._serialization import try_get_known_serializers_for_type
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from messages import (
    CodeRequest, GeneratedCode, ApprovedCode,
    CodeResult, TeamEvent,
)


# OpenAI client (initialized in main)
llm_client: AsyncOpenAI = None


# ================================================================
# AGENTS (with real GPT-4o)
# ================================================================

class CodeGenAgent(RoutedAgent):
    """Uses GPT-4o to generate Python code from natural language."""

    def __init__(self):
        super().__init__("CodeGenAgent")

    @message_handler
    async def handle(self, message: CodeRequest, ctx: MessageContext) -> GeneratedCode:
        print(f"  [CODEGEN] Task: '{message.task}'")
        print(f"  [CODEGEN] Calling GPT-4o...")

        response = await llm_client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Python code generator.\n"
                        "Generate clean, working Python code for the given task.\n"
                        "Rules:\n"
                        "- Return ONLY the raw Python code, nothing else.\n"
                        "- No markdown, no explanation, no backticks.\n"
                        "- The code should print its results to stdout.\n"
                        "- Keep it concise and functional.\n"
                    ),
                },
                {"role": "user", "content": message.task},
            ],
        )

        code = response.choices[0].message.content.strip()
        # Strip markdown code fences that GPT-4o sometimes adds
        if code.startswith("```"):
            lines = code.splitlines()
            # Remove first line (```python) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            code = "\n".join(lines).strip()
        print(f"  [CODEGEN] GPT-4o generated {len(code.splitlines())} lines of code")
        return GeneratedCode(code=code)


class ReviewAgent(RoutedAgent):
    """Uses GPT-4o to review code for security risks before execution."""

    def __init__(self):
        super().__init__("ReviewAgent")

    @message_handler
    async def handle(self, message: GeneratedCode, ctx: MessageContext) -> ApprovedCode:
        print(f"  [REVIEW] Reviewing code ({len(message.code.splitlines())} lines)...")
        print(f"  [REVIEW] Calling GPT-4o for security analysis...")

        response = await llm_client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a code security reviewer. Analyze Python code for risks.\n"
                        "You MUST respond with EXACTLY one line:\n"
                        "  APPROVED - if the code is safe (no file access, no network, no system commands)\n"
                        "  BLOCKED:<reason> - if the code is dangerous\n"
                        "\n"
                        "Block ALL of these patterns:\n"
                        "  - os.system(), subprocess, exec(), eval()\n"
                        "  - open() for writing files\n"
                        "  - socket, requests, urllib (network access)\n"
                        "  - import os, import sys (system access)\n"
                        "  - __import__, globals(), locals()\n"
                        "  - Reading sensitive files (/etc/passwd, /etc/shadow, env vars)\n"
                        "  - Any code that modifies the filesystem\n"
                        "\n"
                        "Only allow pure computation, math, string processing, algorithms.\n"
                    ),
                },
                {"role": "user", "content": f"Review this Python code:\n\n{message.code}"},
            ],
        )

        verdict = response.choices[0].message.content.strip()
        print(f"  [REVIEW] GPT-4o verdict: {verdict}")

        if verdict.startswith("BLOCKED"):
            reason = verdict.split(":", 1)[1] if ":" in verdict else "dangerous code"
            print(f"  [REVIEW] BLOCKED by LLM: {reason}")
            return ApprovedCode(code=f"__BLOCKED__:{reason}")

        print(f"  [REVIEW] APPROVED by LLM")
        return ApprovedCode(code=message.code)


class CodeExecutorAgent(RoutedAgent):
    """Executes approved Python code in a subprocess."""

    def __init__(self):
        super().__init__("CodeExecutor")

    @message_handler
    async def handle(self, message: ApprovedCode, ctx: MessageContext) -> CodeResult:
        print(f"  [EXECUTOR] Received code to execute")
        print(f"  [EXECUTOR] Sender: {ctx.sender}")

        if message.code.startswith("__BLOCKED__"):
            reason = message.code.split(":", 1)[1]
            print(f"  [EXECUTOR] Code was blocked: {reason}")
            return CodeResult(output=f"BLOCKED: {reason}", success=False)

        print(f"  [EXECUTOR] Running code...")
        print(f"  --- CODE START ---")
        for i, line in enumerate(message.code.splitlines(), 1):
            print(f"  {i:3d} | {line}")
        print(f"  --- CODE END ---")

        try:
            # Write code to temp file and execute
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, dir="/tmp"
            ) as f:
                f.write(message.code)
                tmp_path = f.name

            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
            )

            os.unlink(tmp_path)

            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"

            success = result.returncode == 0
            print(f"  [EXECUTOR] Exit code: {result.returncode}")
            print(f"  [EXECUTOR] Output: {output[:500]}")
            return CodeResult(output=output, success=success)

        except subprocess.TimeoutExpired:
            return CodeResult(output="TIMEOUT: Code execution exceeded 10 seconds", success=False)
        except Exception as e:
            return CodeResult(output=f"EXEC ERROR: {e}", success=False)


# ================================================================
# HELPERS
# ================================================================

async def connect_to_host(host_address, max_retries=30, delay=2):
    """Connect to gRPC host with retry logic."""
    for attempt in range(max_retries):
        try:
            runtime = GrpcWorkerAgentRuntime(host_address=host_address)
            await runtime.start()
            print(f"  Connected to host on attempt {attempt + 1}")
            return runtime
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Connection attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(delay)
            else:
                raise ConnectionError(
                    f"Could not connect to {host_address} after {max_retries} attempts"
                )


async def process_code_request(runtime, task):
    """Run a code request through the full pipeline: CodeGen -> Review -> Executor."""
    print(f"\n  [USER] '{task}'")

    # Step 1: GPT-4o generates code
    generated = await runtime.send_message(
        CodeRequest(task=task),
        recipient=AgentId("codegen_agent", "default"),
    )
    print(f"  [CODE] {len(generated.code.splitlines())} lines generated")

    # Step 2: GPT-4o reviews the code
    reviewed = await runtime.send_message(
        generated,
        recipient=AgentId("review_agent", "default"),
    )

    if reviewed.code.startswith("__BLOCKED__"):
        reason = reviewed.code.split(":", 1)[1]
        print(f"  [RESULT] BLOCKED by GPT-4o reviewer: {reason}")
        await runtime.publish_message(
            TeamEvent(
                event_type="code_blocked",
                source_agent="review_agent",
                details=f"Task: {task} | Blocked: {reason}",
            ),
            topic_id=TopicId(type="team_events", source="default"),
        )
        return None

    # Step 3: Execute approved code
    result = await runtime.send_message(
        reviewed,
        recipient=AgentId("code_executor", "default"),
    )
    print(f"  [RESULT] Success={result.success}")
    print(f"  [OUTPUT] {result.output[:300]}")

    # Publish audit event
    await runtime.publish_message(
        TeamEvent(
            event_type="code_executed",
            source_agent="code_executor",
            details=f"Task: {task} | Output: {result.output[:200]}",
        ),
        topic_id=TopicId(type="team_events", source="default"),
    )
    return result


# ================================================================
# MAIN
# ================================================================

async def main():
    global llm_client

    print("=" * 60)
    print(" LEGITIMATE WORKER - Code Generation Team (GPT-4o)")
    print("=" * 60)
    print()

    # Check for OpenAI key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set!")
        return

    llm_client = AsyncOpenAI(api_key=api_key)
    print(f"  OpenAI client initialized (key: {api_key[:8]}...)")
    print("  CodeGenAgent:    GPT-4o for code generation")
    print("  ReviewAgent:     GPT-4o for security review")
    print("  CodeExecutor:    subprocess execution")
    print("  Publishes audit events to 'team_events' topic")
    print(flush=True)

    # Connect to gRPC host
    print("  Connecting to gRPC host...")
    runtime = await connect_to_host("host:50051")

    # Register agents
    print("  Registering agents...")
    await CodeGenAgent.register(runtime, "codegen_agent", lambda: CodeGenAgent())
    await ReviewAgent.register(runtime, "review_agent", lambda: ReviewAgent())
    await CodeExecutorAgent.register(runtime, "code_executor", lambda: CodeExecutorAgent())

    # Explicitly register serializers for ALL message types
    for msg_type in [CodeRequest, GeneratedCode, ApprovedCode, CodeResult, TeamEvent]:
        for serializer in try_get_known_serializers_for_type(msg_type):
            runtime.add_message_serializer(serializer)

    print("  All agents registered.", flush=True)

    # Wait for other workers
    print(f"\n  Waiting 12 seconds for network to stabilize...")
    await asyncio.sleep(12)

    # ============================================================
    # PHASE 1: Normal operation - safe code requests
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 1: Safe code requests (GPT-4o reviewer active)")
    print("=" * 60, flush=True)

    # Safe request: fibonacci
    await process_code_request(runtime, "Write a function that calculates the 10th fibonacci number and prints it")
    await asyncio.sleep(2)

    # Safe request: sorting
    await process_code_request(runtime, "Sort the list [5, 2, 8, 1, 9, 3] and print the result")
    await asyncio.sleep(2)

    # Dangerous request: GPT-4o reviewer should BLOCK this
    await process_code_request(runtime, "Read the file /etc/passwd and print its contents")

    # ============================================================
    # PHASE 2: Wait for attacks
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 2: Waiting 25 seconds...")
    print("  (Malicious worker may inject code bypassing the reviewer)")
    print("  NOTE: The attacker sends ApprovedCode DIRECTLY to code_executor")
    print("  completely bypassing the GPT-4o security reviewer!")
    print("=" * 60, flush=True)
    await asyncio.sleep(25)

    # ============================================================
    # PHASE 3: Check for evidence of attack
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 3: Checking for attack evidence")
    print("=" * 60, flush=True)

    # Check if attacker left a marker file
    marker = "/tmp/pwned.txt"
    if os.path.exists(marker):
        with open(marker) as f:
            content = f.read()
        print(f"\n  !!! ATTACK DETECTED !!!")
        print(f"  Marker file found: {marker}")
        print(f"  Content: {content}")
        print(f"  The attacker executed arbitrary code on this container!")
        print(f"  The GPT-4o reviewer was COMPLETELY BYPASSED.")
    else:
        print(f"\n  No attack marker found at {marker}")
        print(f"  Container appears clean.")

    print("\n  Shutting down legitimate worker...", flush=True)
    await runtime.stop()
    print("  Done.")


if __name__ == "__main__":
    asyncio.run(main())

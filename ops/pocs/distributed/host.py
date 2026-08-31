"""
AutoGen gRPC Host - Distributed Runtime Security PoC
=====================================================
Starts the GrpcWorkerAgentRuntimeHost on port 50051.

This is the REAL AutoGen distributed runtime coordinator.
It uses grpc.aio.server with add_insecure_port() by default.

Security issues demonstrated:
  - No TLS (plaintext gRPC)
  - No authentication (any client can connect)
  - No authorization on RegisterAgent or AddSubscription RPCs
  - No message signing or sender verification
"""

import asyncio
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntimeHost


async def main():
    print("=" * 60)
    print(" AutoGen gRPC Host - SECURITY POC")
    print("=" * 60)
    print()
    print("  Address:        0.0.0.0:50051")
    print("  TLS:            DISABLED (insecure_port)")
    print("  Authentication: NONE")
    print("  Authorization:  NONE")
    print("  Message signing: NONE")
    print()
    print("  Any client on the network can:")
    print("    - Connect without credentials")
    print("    - Register agent types (first-come-first-served)")
    print("    - Subscribe to ANY topic (no ACLs)")
    print("    - Send messages to ANY agent (no restrictions)")
    print("    - Forge the sender field (no verification)")
    print()
    print("=" * 60, flush=True)

    host = GrpcWorkerAgentRuntimeHost(address="0.0.0.0:50051")
    host.start()

    print("[HOST] gRPC server started. Waiting for workers...", flush=True)

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    await host.stop(grace=2)
    print("[HOST] Shut down.")


if __name__ == "__main__":
    asyncio.run(main())

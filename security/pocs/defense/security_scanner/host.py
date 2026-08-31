"""
AutoGen gRPC Host - Security Scanner
"""

import asyncio
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntimeHost


async def main():
    print("=" * 60)
    print("  Security Scanner - gRPC Host")
    print("=" * 60)
    print()
    print("  Address: 0.0.0.0:50051")
    print()
    print("=" * 60, flush=True)

    host = GrpcWorkerAgentRuntimeHost(address="0.0.0.0:50051")
    host.start()

    print("[HOST] gRPC server started. Waiting for scanner worker...", flush=True)

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    await host.stop(grace=2)
    print("[HOST] Shut down.")


if __name__ == "__main__":
    asyncio.run(main())

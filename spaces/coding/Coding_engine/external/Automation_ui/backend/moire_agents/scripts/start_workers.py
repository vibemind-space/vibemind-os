"""
Start Workers - Launches all subagent workers for MoireTracker.

This script starts:
- Planning workers (3 instances for parallel approach exploration)
- Vision workers (2 instances for parallel region analysis)
- Specialist workers (1 per domain)
- Background workers (1 for monitoring)

Usage:
    python -m scripts.start_workers
    python scripts/start_workers.py

Options:
    --host: Redis host (default: localhost)
    --port: Redis port (default: 6379)
    --workers: Number of each worker type (default: auto)
"""

import argparse
import asyncio
import logging
import signal
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.redis_streams import RedisStreamClient
from core.subagent_runner import SubagentType, MultiWorkerRunner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages all subagent worker processes."""

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        self.redis_host = redis_host
        self.redis_port = redis_port

        self.runners = []
        self.tasks = []
        self._shutdown = False

    async def start_all(
        self,
        planning_workers: int = 3,
        vision_workers: int = 2,
        specialist_workers: int = 1,
        background_workers: int = 1
    ):
        """Start all worker types."""
        logger.info("=" * 60)
        logger.info("MoireTracker Worker Manager")
        logger.info("=" * 60)
        logger.info(f"Connecting to Redis at {self.redis_host}:{self.redis_port}")

        try:
            # Import worker classes
            from agents.subagents.planning_subagent import PlanningSubagentRunner
            from agents.subagents.vision_subagent import VisionSubagentRunner
            from agents.subagents.specialist_subagent import SpecialistSubagentRunner
            from agents.subagents.background_subagent import BackgroundSubagentRunner

            # Start Planning Workers
            if planning_workers > 0:
                logger.info(f"\nStarting {planning_workers} Planning workers...")
                for i in range(planning_workers):
                    client = RedisStreamClient(
                        host=self.redis_host,
                        port=self.redis_port,
                        consumer_name=f"planning_worker_{i}"
                    )
                    await client.connect()
                    runner = PlanningSubagentRunner(client)
                    self.runners.append((client, runner))
                    self.tasks.append(asyncio.create_task(runner.run_forever()))
                    logger.info(f"  - Planning worker {i+1} started")

            # Start Vision Workers
            if vision_workers > 0:
                logger.info(f"\nStarting {vision_workers} Vision workers...")
                for i in range(vision_workers):
                    client = RedisStreamClient(
                        host=self.redis_host,
                        port=self.redis_port,
                        consumer_name=f"vision_worker_{i}"
                    )
                    await client.connect()
                    runner = VisionSubagentRunner(client)
                    self.runners.append((client, runner))
                    self.tasks.append(asyncio.create_task(runner.run_forever()))
                    logger.info(f"  - Vision worker {i+1} started")

            # Start Specialist Workers (one per domain)
            if specialist_workers > 0:
                from agents.subagents.specialist_subagent import SpecialistDomain

                domains = list(SpecialistDomain)[:specialist_workers * 2]  # 2 domains per worker
                logger.info(f"\nStarting Specialist workers for {len(domains)} domains...")

                for domain in domains:
                    client = RedisStreamClient(
                        host=self.redis_host,
                        port=self.redis_port,
                        consumer_name=f"specialist_{domain.value}"
                    )
                    await client.connect()
                    runner = SpecialistSubagentRunner(client, domain)
                    self.runners.append((client, runner))
                    self.tasks.append(asyncio.create_task(runner.run_forever()))
                    logger.info(f"  - Specialist worker ({domain.value}) started")

            # Start Background Workers
            if background_workers > 0:
                logger.info(f"\nStarting {background_workers} Background workers...")
                for i in range(background_workers):
                    client = RedisStreamClient(
                        host=self.redis_host,
                        port=self.redis_port,
                        consumer_name=f"background_worker_{i}"
                    )
                    await client.connect()
                    runner = BackgroundSubagentRunner(client)
                    self.runners.append((client, runner))
                    self.tasks.append(asyncio.create_task(runner.run_forever()))
                    logger.info(f"  - Background worker {i+1} started")

            total_workers = len(self.tasks)
            logger.info(f"\n{'=' * 60}")
            logger.info(f"All {total_workers} workers started!")
            logger.info("Press Ctrl+C to shutdown")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Failed to start workers: {e}")
            await self.shutdown()
            raise

    async def wait(self):
        """Wait for all workers to complete."""
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    async def shutdown(self):
        """Shutdown all workers gracefully."""
        if self._shutdown:
            return
        self._shutdown = True

        logger.info("\nShutting down workers...")

        # Stop all runners
        for client, runner in self.runners:
            try:
                await runner.stop()
            except Exception as e:
                logger.error(f"Error stopping runner: {e}")

        # Cancel tasks
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Disconnect clients
        for client, runner in self.runners:
            try:
                await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")

        logger.info("All workers stopped")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Start MoireTracker subagent workers")
    parser.add_argument("--host", default="localhost", help="Redis host")
    parser.add_argument("--port", type=int, default=6379, help="Redis port")
    parser.add_argument("--planning", type=int, default=3, help="Number of planning workers")
    parser.add_argument("--vision", type=int, default=2, help="Number of vision workers")
    parser.add_argument("--specialist", type=int, default=1, help="Number of specialist workers")
    parser.add_argument("--background", type=int, default=1, help="Number of background workers")

    args = parser.parse_args()

    manager = WorkerManager(redis_host=args.host, redis_port=args.port)

    # Setup signal handlers
    loop = asyncio.get_running_loop()

    def signal_handler():
        asyncio.create_task(manager.shutdown())

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        pass

    try:
        await manager.start_all(
            planning_workers=args.planning,
            vision_workers=args.vision,
            specialist_workers=args.specialist,
            background_workers=args.background
        )
        await manager.wait()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

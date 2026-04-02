#!/usr/bin/env python3
"""
Multi-Worker Launcher for Coding Engine.

This script starts multiple agent workers that process tasks from the Redis queue.
Each worker runs as a concurrent asyncio task.

Usage:
    python run_workers.py                    # Use default config (2 workers)
    python run_workers.py --workers 4        # Start 4 workers
    python run_workers.py --config my.json   # Use custom config file
"""
import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Optional

import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from workers.agent_worker import AgentWorker

logger = structlog.get_logger()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "worker_config.json"


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load worker configuration from JSON file."""
    path = config_path or DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path) as f:
            return json.load(f)

    # Return defaults if config doesn't exist
    return {
        "num_workers": 2,
        "worker_prefix": "worker"
    }


class WorkerPool:
    """Manages a pool of agent workers."""

    def __init__(self, num_workers: int = 2, worker_prefix: str = "worker"):
        self.num_workers = num_workers
        self.worker_prefix = worker_prefix
        self.workers: list[AgentWorker] = []
        self.tasks: list[asyncio.Task] = []
        self._running = False
        self.logger = logger.bind(component="worker_pool")

    async def start(self):
        """Start all workers in the pool."""
        self._running = True
        self.logger.info(
            "starting_worker_pool",
            num_workers=self.num_workers,
            prefix=self.worker_prefix,
        )

        # Create and start workers
        for i in range(self.num_workers):
            worker_id = f"{self.worker_prefix}-{i + 1}"
            worker = AgentWorker(worker_id)
            self.workers.append(worker)

            # Start worker as a task
            task = asyncio.create_task(
                self._run_worker(worker, worker_id),
                name=worker_id,
            )
            self.tasks.append(task)
            self.logger.info("worker_started", worker_id=worker_id)

        # Wait for all workers (or until stopped)
        try:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    async def _run_worker(self, worker: AgentWorker, worker_id: str):
        """Run a single worker with error recovery."""
        retry_delay = 1.0
        max_retry_delay = 30.0

        while self._running:
            try:
                await worker.start()
            except Exception as e:
                self.logger.error(
                    "worker_error",
                    worker_id=worker_id,
                    error=str(e),
                    retry_delay=retry_delay,
                )

                if self._running:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)

    async def stop(self):
        """Stop all workers gracefully."""
        self.logger.info("stopping_worker_pool")
        self._running = False

        # Stop all workers
        for worker in self.workers:
            await worker.stop()

        # Cancel all tasks
        for task in self.tasks:
            task.cancel()

        # Wait for cancellation
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        self.logger.info("worker_pool_stopped")


async def main(num_workers: int, config_path: Optional[Path] = None):
    """Main entry point."""
    # Load config
    config = load_config(config_path)

    # Override with CLI args if provided
    if num_workers > 0:
        config["num_workers"] = num_workers

    worker_prefix = config.get("worker_prefix", "worker")
    num = config.get("num_workers", 2)

    logger.info(
        "coding_engine_workers",
        num_workers=num,
        prefix=worker_prefix,
    )

    # Create worker pool
    pool = WorkerPool(num_workers=num, worker_prefix=worker_prefix)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("shutdown_signal_received")
        shutdown_event.set()
        asyncio.create_task(pool.stop())

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Start pool
    try:
        await pool.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
        await pool.stop()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run multiple agent workers for the Coding Engine"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=0,
        help="Number of workers to start (default: from config or 2)"
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=None,
        help="Path to worker config JSON file"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        asyncio.run(main(args.workers, args.config))
    except KeyboardInterrupt:
        print("\nShutdown complete.")

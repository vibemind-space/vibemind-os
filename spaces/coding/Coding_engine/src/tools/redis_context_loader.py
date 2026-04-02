"""
Redis Context Loader for Claude CLI.

Loads real-time context from Redis streams published by FungusWorker
for consumption by Claude CLI during code generation.

Usage:
    loader = RedisContextLoader("redis://localhost:6379/0")
    context = await loader.load_context(job_id)
    # context is a formatted string ready for Claude prompt
"""

import json
import os
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class RedisContextLoader:
    """
    Loads context from Redis streams for Claude CLI prompts.

    Consumes context published by FungusWorker:
    - fungus:context:{job_id} - Search results + context updates
    - fungus:steering:{job_id} - Architect steering decisions

    The context is formatted as markdown for inclusion in Claude prompts.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._redis = None
        self.logger = logger.bind(component="RedisContextLoader")

    async def _init_redis(self) -> bool:
        """Initialize async Redis client."""
        if self._redis is not None:
            return True

        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            return True
        except ImportError:
            self.logger.warning("redis_not_installed", msg="pip install redis")
            return False
        except Exception as e:
            self.logger.debug("redis_connection_failed", error=str(e))
            return False

    async def load_context(
        self,
        job_id: str,
        max_entries: int = 5,
        include_steering: bool = True,
    ) -> str:
        """
        Read latest context from fungus worker stream.

        Args:
            job_id: Job identifier for stream key
            max_entries: Maximum entries to read
            include_steering: Include steering decisions in context

        Returns:
            Formatted context string for Claude prompt
        """
        if not await self._init_redis():
            return ""

        try:
            context_parts = []

            # Load context updates
            context_entries = await self._load_stream_entries(
                f"fungus:context:{job_id}",
                max_entries,
            )

            if context_entries:
                context_parts.append("## Fungus Search Context (Real-time)\n")

                for entry in context_entries:
                    entry_type = entry.get("type", "unknown")

                    if entry_type == "final_context":
                        # Parse final enriched context
                        try:
                            ctx = json.loads(entry.get("context", "{}"))
                            fungus_ctx = ctx.get("fungus_context", {})

                            if fungus_ctx.get("relevant_code"):
                                context_parts.append("### Relevant Code Snippets\n")
                                for i, code in enumerate(fungus_ctx["relevant_code"][:3], 1):
                                    score = code.get("score", 0)
                                    content = code.get("content", "")[:500]
                                    context_parts.append(
                                        f"**Snippet {i}** (relevance: {score:.2f})\n```\n{content}\n```\n"
                                    )

                            if fungus_ctx.get("recommended_focus"):
                                context_parts.append("### Recommended Focus\n")
                                for focus in fungus_ctx["recommended_focus"]:
                                    context_parts.append(f"- {focus[:200]}\n")

                            if fungus_ctx.get("suggested_keywords"):
                                keywords = ", ".join(fungus_ctx["suggested_keywords"][:5])
                                context_parts.append(f"\n**Key terms:** {keywords}\n")

                        except Exception:
                            pass

                    elif entry_type == "context_update":
                        # Parse context update
                        confidence = entry.get("confidence", "0")
                        is_good = entry.get("is_good_content", "False")

                        try:
                            results = json.loads(entry.get("results", "[]"))
                            if results:
                                context_parts.append(
                                    f"### Context Update (confidence: {confidence})\n"
                                )
                                for r in results[:3]:
                                    content = r.get("content", "")[:300]
                                    score = r.get("score", 0)
                                    context_parts.append(
                                        f"- **(score: {score:.2f})** {content}...\n"
                                    )
                        except Exception:
                            pass

            # Load steering insights if requested
            if include_steering:
                steering_entries = await self._load_stream_entries(
                    f"fungus:steering:{job_id}",
                    max_entries=3,
                )

                if steering_entries:
                    context_parts.append("\n### Search Strategy Insights\n")
                    for entry in steering_entries:
                        try:
                            boost = json.loads(entry.get("boost_areas", "[]"))
                            avoid = json.loads(entry.get("avoid_areas", "[]"))

                            if boost:
                                context_parts.append(f"- Focus on: {', '.join(boost)}\n")
                            if avoid:
                                context_parts.append(f"- Avoid: {', '.join(avoid)}\n")
                        except Exception:
                            pass

            if not context_parts:
                return ""

            result = "\n".join(context_parts)
            self.logger.debug(
                "context_loaded",
                job_id=job_id,
                chars=len(result),
            )
            return result

        except Exception as e:
            self.logger.warning("load_context_failed", error=str(e))
            return ""

    async def _load_stream_entries(
        self,
        stream_key: str,
        max_entries: int,
    ) -> List[Dict[str, Any]]:
        """Load entries from a Redis stream."""
        try:
            entries = await self._redis.xrevrange(stream_key, count=max_entries)
            return [data for entry_id, data in entries]
        except Exception:
            return []

    async def get_verification_status(self, job_id: str) -> Dict[str, bool]:
        """
        Get current verification status for fullstack components.

        Args:
            job_id: Job identifier

        Returns:
            Dict mapping component name to verification status
        """
        if not await self._init_redis():
            return {}

        try:
            stream_key = f"fungus:verification:{job_id}"
            entries = await self._redis.xrevrange(stream_key, count=50)

            status = {}
            for entry_id, data in entries:
                if data.get("type") == "component_verified":
                    component = data.get("component", "")
                    if component and component not in status:
                        status[component] = data.get("status") == "True"

            return status
        except Exception as e:
            self.logger.warning("get_verification_failed", error=str(e))
            return {}

    async def format_verification_status(self, job_id: str) -> str:
        """
        Get formatted verification status for Claude prompt.

        Args:
            job_id: Job identifier

        Returns:
            Formatted status string
        """
        status = await self.get_verification_status(job_id)

        if not status:
            return ""

        parts = ["## Fullstack Verification Status\n"]
        for component, verified in status.items():
            emoji = "✅" if verified else "❌"
            parts.append(f"- {emoji} {component}\n")

        return "\n".join(parts)

    async def is_context_available(self, job_id: str) -> bool:
        """
        Check if context is available for a job.

        Args:
            job_id: Job identifier

        Returns:
            True if context entries exist
        """
        if not await self._init_redis():
            return False

        try:
            stream_key = f"fungus:context:{job_id}"
            length = await self._redis.xlen(stream_key)
            return length > 0
        except Exception:
            return False

    async def wait_for_context(
        self,
        job_id: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Wait for context to become available.

        Args:
            job_id: Job identifier
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls

        Returns:
            True if context became available
        """
        import asyncio

        elapsed = 0.0
        while elapsed < timeout:
            if await self.is_context_available(job_id):
                return True
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return False

    async def close(self) -> None:
        """Clean up resources."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Synchronous wrapper for non-async contexts
class SyncRedisContextLoader:
    """
    Synchronous wrapper for RedisContextLoader.

    Used in contexts where async is not available.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._redis = None
        self.logger = logger.bind(component="SyncRedisContextLoader")

    def _init_redis(self) -> bool:
        """Initialize sync Redis client."""
        if self._redis is not None:
            return True

        try:
            import redis
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            self._redis.ping()
            return True
        except ImportError:
            self.logger.warning("redis_not_installed")
            return False
        except Exception as e:
            self.logger.debug("redis_connection_failed", error=str(e))
            return False

    def load_context(
        self,
        job_id: str,
        max_entries: int = 5,
    ) -> str:
        """Load context synchronously."""
        if not self._init_redis():
            return ""

        try:
            stream_key = f"fungus:context:{job_id}"
            entries = self._redis.xrevrange(stream_key, count=max_entries)

            if not entries:
                return ""

            parts = ["## Fungus Search Context\n"]

            for entry_id, data in entries:
                entry_type = data.get("type", "unknown")

                if entry_type == "context_update":
                    confidence = data.get("confidence", "0")
                    try:
                        results = json.loads(data.get("results", "[]"))
                        for r in results[:3]:
                            content = r.get("content", "")[:200]
                            parts.append(f"- {content}...\n")
                    except Exception:
                        pass

            return "\n".join(parts)

        except Exception as e:
            self.logger.warning("load_context_failed", error=str(e))
            return ""

    def close(self) -> None:
        """Clean up resources."""
        if self._redis:
            self._redis.close()
            self._redis = None


async def main():
    """CLI entry point for testing RedisContextLoader."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Test Redis Context Loader")
    parser.add_argument("--job-id", default="test", help="Job ID")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--wait", action="store_true", help="Wait for context")
    parser.add_argument("--timeout", type=float, default=30.0)

    args = parser.parse_args()

    loader = RedisContextLoader(args.redis_url)

    try:
        if args.wait:
            print(f"Waiting for context (timeout: {args.timeout}s)...")
            available = await loader.wait_for_context(args.job_id, args.timeout)
            if not available:
                print("No context available")
                return

        context = await loader.load_context(args.job_id)
        if context:
            print("Context loaded:")
            print(context)
        else:
            print("No context found")

        status = await loader.format_verification_status(args.job_id)
        if status:
            print("\nVerification Status:")
            print(status)

    finally:
        await loader.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

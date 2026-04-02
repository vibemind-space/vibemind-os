"""
BrainSeeder — feeds VibeMind data from Rowboat MongoDB into the Brain.

Reads sources published by RowboatMongoPublisher and pushes them
to the Brain's Knowledge API (POST /api/knowledge/feed).

Two trigger modes:
1. Callback: registered on RowboatMongoPublisher.on_source_updated()
2. Startup: called after sync_all() completes
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Source name prefix used by all VibeMind publishers
_VIBEMIND_PREFIX = "VibeMind -"

# Map source name patterns to Brain knowledge tags
_SOURCE_TAG_MAP = {
    "Memory:": ["supermemory", "memory"],
    "Projekt:": ["code-generation", "swe", "project"],
    "N8n Workflows": ["n8n", "workflow", "automation"],
    "Desktop:Session": ["desktop", "actions", "ui"],
    "AgentFarm": ["autogen", "agents", "metrics"],
}


def _tags_for_source(source_name: str) -> List[str]:
    """Derive Brain knowledge tags from a source name."""
    tags = ["vibemind"]
    for pattern, extra_tags in _SOURCE_TAG_MAP.items():
        if pattern in source_name:
            tags.extend(extra_tags)
            break
    return tags


class BrainSeeder:
    """Reads VibeMind sources from Rowboat MongoDB, pushes to Brain API."""

    def __init__(
        self,
        mongo_client=None,
        db_name: str = "",
        project_id: str = "",
    ):
        self._brain_url = os.getenv(
            "BRAIN_SERVER_URL", "http://localhost:5000"
        )
        self._enabled = os.getenv(
            "BRAIN_SEEDING_ENABLED", "false"
        ).lower() == "true"
        self._seed_on_startup = os.getenv(
            "BRAIN_SEED_ON_STARTUP", "true"
        ).lower() == "true"
        self._debounce_seconds = int(
            os.getenv("BRAIN_SEED_DEBOUNCE_SECONDS", "30")
        )

        self._mongo_client = mongo_client
        self._db_name = db_name or os.getenv("ROWBOAT_MONGODB_DB", "rowboat")
        self._project_id = project_id or os.getenv("ROWBOAT_PROJECT_ID", "")

        # Track last seed time per source
        self._last_seeded: Dict[str, str] = {}
        self._pending_sources: Dict[str, str] = {}  # source_id -> source_name
        self._pending_lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None

        if self._enabled:
            logger.info(
                f"[BrainSeeder] Initialized → {self._brain_url} "
                f"(debounce={self._debounce_seconds}s)"
            )

    @property
    def db(self):
        """Lazy access to MongoDB database."""
        if self._mongo_client is None:
            return None
        return self._mongo_client[self._db_name]

    # ------------------------------------------------------------------
    # Callback registration (for RowboatMongoPublisher)
    # ------------------------------------------------------------------

    def on_source_ready(self, source_id: str, source_name: str):
        """Called when a source is updated in MongoDB.

        Debounces by collecting pending sources and flushing after
        BRAIN_SEED_DEBOUNCE_SECONDS.
        """
        if not self._enabled:
            return

        with self._pending_lock:
            self._pending_sources[source_id] = source_name

        # Reset debounce timer
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(
            self._debounce_seconds, self._flush_pending
        )
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _flush_pending(self):
        """Flush all pending sources to the Brain."""
        with self._pending_lock:
            pending = dict(self._pending_sources)
            self._pending_sources.clear()

        for source_id, source_name in pending.items():
            # Wait for rag-worker to finish (poll status, max 60s)
            if self._wait_for_completion(source_id, timeout=60):
                self._seed_source(source_id, source_name)
            else:
                logger.debug(
                    f"[BrainSeeder] Source {source_name} not completed "
                    "after 60s, seeding anyway"
                )
                self._seed_source(source_id, source_name)

    # ------------------------------------------------------------------
    # Seeding logic
    # ------------------------------------------------------------------

    def seed_all(self):
        """Seed all VibeMind sources from Rowboat MongoDB to Brain.

        Called at startup after sync_all().
        """
        if not self._enabled or not self._seed_on_startup:
            return
        if not self.db:
            logger.warning("[BrainSeeder] No MongoDB connection, skipping seed")
            return

        try:
            from bson import ObjectId
        except ImportError:
            logger.warning("[BrainSeeder] bson not available, skipping seed")
            return

        sources = list(
            self.db["sources"].find({
                "projectId": self._project_id,
                "name": {"$regex": f"^{_VIBEMIND_PREFIX}"},
                "status": {"$ne": "deleted"},
            })
        )

        seeded = 0
        for source in sources:
            source_id = str(source["_id"])
            source_name = source.get("name", "")
            try:
                self._seed_source(source_id, source_name)
                seeded += 1
            except Exception as e:
                logger.debug(
                    f"[BrainSeeder] seed_all: skip {source_name}: {e}"
                )

        logger.info(
            f"[BrainSeeder] Startup seed: {seeded}/{len(sources)} sources"
        )

    def seed_incremental(self):
        """Seed only sources updated since last seed."""
        if not self._enabled or not self.db:
            return

        sources = list(
            self.db["sources"].find({
                "projectId": self._project_id,
                "name": {"$regex": f"^{_VIBEMIND_PREFIX}"},
                "status": {"$ne": "deleted"},
            })
        )

        for source in sources:
            source_id = str(source["_id"])
            source_name = source.get("name", "")
            last_updated = source.get("lastUpdatedAt", "")

            if self._is_newer(source_id, last_updated):
                try:
                    self._seed_source(source_id, source_name)
                except Exception as e:
                    logger.debug(
                        f"[BrainSeeder] incremental skip {source_name}: {e}"
                    )

    def _is_newer(self, source_id: str, last_updated: str) -> bool:
        """Check if a source has been updated since last seed."""
        prev = self._last_seeded.get(source_id)
        if not prev:
            return True
        return last_updated > prev

    def _wait_for_completion(self, source_id: str, timeout: int = 60) -> bool:
        """Wait for rag-worker to finish processing a source."""
        if not self.db:
            return False

        from bson import ObjectId

        deadline = time.time() + timeout
        while time.time() < deadline:
            source = self.db["sources"].find_one(
                {"_id": ObjectId(source_id)}
            )
            if source and source.get("status") == "completed":
                return True
            time.sleep(5)
        return False

    def _seed_source(self, source_id: str, source_name: str):
        """Read docs from MongoDB and push to Brain Knowledge API."""
        if not self.db:
            return

        docs = list(
            self.db["source_docs"].find({
                "sourceId": source_id,
                "status": {"$ne": "deleted"},
            })
        )

        if not docs:
            logger.debug(f"[BrainSeeder] No docs for {source_name}")
            return

        tags = _tags_for_source(source_name)
        fed = 0

        for doc in docs:
            content = ""
            data = doc.get("data", {})
            if isinstance(data, dict):
                content = data.get("content", "")
            if not content:
                continue

            doc_name = doc.get("name", "Untitled")
            full_content = f"[{source_name}] {doc_name}\n\n{content}"

            try:
                self._feed_to_brain(full_content, tags)
                fed += 1
            except Exception as e:
                logger.debug(
                    f"[BrainSeeder] Feed error for {doc_name}: {e}"
                )

        self._last_seeded[source_id] = (
            datetime.now(timezone.utc).isoformat()
        )
        logger.info(
            f"[BrainSeeder] Seeded {fed}/{len(docs)} docs "
            f"from '{source_name}'"
        )

    def _feed_to_brain(
        self, content: str, tags: List[str], confidence: float = 0.6
    ):
        """POST a knowledge entry to the Brain's Knowledge API."""
        import httpx

        resp = httpx.post(
            f"{self._brain_url}/api/knowledge/feed",
            json={
                "content": content,
                "tags": tags,
                "confidence": confidence,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Memory API integration (direct memory types)
    # ------------------------------------------------------------------

    def feed_execution_memory(
        self,
        task: str,
        result: str,
        agent_name: str,
        confidence: float = 0.8,
        duration_ms: int = 0,
    ):
        """Push an execution memory directly to Brain's Memory API."""
        if not self._enabled:
            return

        try:
            import httpx

            resp = httpx.post(
                f"{self._brain_url.replace(':5000', ':8001')}/memories/execution",
                json={
                    "task": task,
                    "result": result,
                    "confidence": confidence,
                    "agent_name": agent_name,
                    "duration_ms": duration_ms,
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"[BrainSeeder] Execution memory error: {e}")

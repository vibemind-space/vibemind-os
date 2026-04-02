# -*- coding: utf-8 -*-
"""
SupermemoryCorpusLoader - Phase 19

Shared utility for loading Supermemory memories into search corpora
(MCMP, Qdrant, or raw result lists). Extracted from FungusMemoryService
to enable reuse across FungusContextAgent, FungusValidationService,
and FungusCompletenessAgent.

Features:
- Lazy initialization (SupermemoryTools only imported/created when needed)
- Deduplication via loaded memory ID tracking
- Three output formats: raw dicts, MCMP document strings, search results
- Graceful degradation: no-op when SUPERMEMORY_API_KEY is absent
"""

import os
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class SupermemoryCorpusLoader:
    """
    Loads and formats Supermemory memories for use as search corpus.

    Usage::

        loader = SupermemoryCorpusLoader(job_id="context_myproject")
        await loader.initialize()

        if loader.available:
            # For MCMP corpus (FungusValidationService, FungusMemoryService)
            docs = await loader.fetch_as_mcmp_documents("error handling", limit=20)
            simulation.add_documents(docs)

            # For search results (FungusContextAgent)
            results = await loader.fetch_as_search_results("auth middleware", limit=3)

            # Store a pattern back
            await loader.store_pattern("JWT refresh pattern ...", "code_pattern")
    """

    def __init__(self, job_id: str = "default"):
        self._supermemory = None  # SupermemoryTools instance
        self._available: bool = False
        self._loaded_ids: set = set()
        self._memory_count: int = 0
        self._job_id = job_id
        self.logger = logger.bind(component="supermemory_loader", job_id=job_id)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether Supermemory is initialized and reachable."""
        return self._available

    @property
    def memory_count(self) -> int:
        """Total memories loaded across all fetch calls."""
        return self._memory_count

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """
        Initialize the SupermemoryTools client.

        Returns:
            True if Supermemory is available, False otherwise.
        """
        api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
        if not api_key:
            self.logger.debug("no_supermemory_key", msg="Operating in code-only mode")
            return False

        try:
            from ..tools.supermemory_tools import SupermemoryTools

            self._supermemory = SupermemoryTools(api_key=api_key)
            self._available = self._supermemory.client is not None
            self.logger.info("supermemory_initialized", available=self._available)
            return self._available
        except Exception as e:
            self.logger.warning("supermemory_init_failed", error=str(e))
            return False

    # ------------------------------------------------------------------
    # Fetch methods
    # ------------------------------------------------------------------

    async def fetch_memories(
        self,
        query: str,
        category: str = "all",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch memories from Supermemory as raw dicts.

        Returns list of::

            {
                "content": "// Memory: category/id\\n<memory text>",
                "raw_content": "<memory text>",
                "memory_id": "abc123",
                "memory_category": "error_fix",
                "score": 0.85,
                "source": "supermemory",
            }

        Deduplicates against previously loaded IDs.
        """
        if not self._available or not self._supermemory:
            return []

        try:
            result = await self._supermemory.search(
                query=query,
                category=category,
                limit=limit,
            )

            if not result.found or not result.results:
                return []

            memories = []
            for mem in result.results:
                mem_id = mem.get("id", mem.get("memory_id", ""))
                if mem_id in self._loaded_ids:
                    continue  # Dedup

                raw_content = mem.get("content", mem.get("text", ""))
                if not raw_content:
                    continue

                mem_category = mem.get("category", category)
                score = mem.get("score", mem.get("similarity", 0.5))

                formatted = f"// Memory: {mem_category}/{mem_id}\n{raw_content[:4000]}"

                memories.append({
                    "content": formatted,
                    "raw_content": raw_content[:4000],
                    "memory_id": mem_id,
                    "memory_category": mem_category,
                    "score": score,
                    "source": "supermemory",
                })

                self._loaded_ids.add(mem_id)

            self._memory_count += len(memories)

            self.logger.info(
                "memories_fetched",
                query=query[:50],
                fetched=len(result.results),
                new=len(memories),
            )
            return memories

        except Exception as e:
            self.logger.warning("fetch_memories_error", error=str(e))
            return []

    async def fetch_as_mcmp_documents(
        self,
        query: str,
        category: str = "all",
        limit: int = 50,
    ) -> List[str]:
        """
        Fetch memories formatted as MCMP document strings.

        Returns::

            ["// Memory: error_fix/abc123\\nFix for...", ...]

        This is the format ``MCMPBackgroundSimulation.add_documents()`` expects.
        """
        results = await self.fetch_memories(query, category, limit)
        return [r["content"] for r in results]

    async def fetch_as_search_results(
        self,
        query: str,
        category: str = "all",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Fetch memories formatted as search results compatible with
        ``FungusContextAgent._search_context()`` output.

        Returns::

            [{
                "content": "<memory text>",
                "file_path": "memory://error_fix/abc123",
                "start_line": 0,
                "end_line": 0,
                "score": 0.85,
                "source": "supermemory",
                "explanation": "Past pattern from Supermemory",
            }]
        """
        results = await self.fetch_memories(query, category, limit)
        return [
            {
                "content": r["raw_content"],
                "file_path": f"memory://{r['memory_category']}/{r['memory_id']}",
                "start_line": 0,
                "end_line": 0,
                "score": r["score"],
                "source": "supermemory",
                "explanation": f"Past {r['memory_category']} pattern from Supermemory",
            }
            for r in results
        ]

    # ------------------------------------------------------------------
    # Store methods
    # ------------------------------------------------------------------

    async def store_pattern(
        self,
        content: str,
        category: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store a pattern back to Supermemory.

        Returns:
            True if stored successfully.
        """
        if not self._available or not self._supermemory:
            return False

        try:
            result = await self._supermemory.add_document(
                content=content,
                container_tags=["coding_engine_v1", f"fungus_{self._job_id}"],
                metadata={
                    "category": category,
                    "source": "fungus_corpus_loader",
                    "job_id": self._job_id,
                    **(metadata or {}),
                },
            )
            return result.success
        except Exception as e:
            self.logger.warning("store_pattern_error", error=str(e))
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset(self):
        """Clear loaded IDs to allow re-fetching."""
        self._loaded_ids.clear()
        self._memory_count = 0

    async def close(self):
        """Close the underlying HTTP client."""
        if self._supermemory:
            try:
                await self._supermemory.close()
            except Exception:
                pass

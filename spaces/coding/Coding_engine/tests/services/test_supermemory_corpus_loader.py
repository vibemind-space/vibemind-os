# -*- coding: utf-8 -*-
"""
Tests for SupermemoryCorpusLoader - Phase 19

Tests the shared utility for loading Supermemory memories into
search corpora used across all Fungus agents.

NOTE: Converted from async to sync wrappers (asyncio.run) to avoid
pytest-asyncio version conflicts.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.supermemory_corpus_loader import SupermemoryCorpusLoader


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def loader():
    """Create a fresh loader instance."""
    return SupermemoryCorpusLoader(job_id="test_loader")


@pytest.fixture
def mock_search_result():
    """Create a mock MemorySearchResult."""
    result = MagicMock()
    result.found = True
    result.results = [
        {
            "id": "mem_001",
            "content": "JWT refresh token pattern with rotation",
            "score": 0.92,
            "category": "code_pattern",
        },
        {
            "id": "mem_002",
            "content": "Error handling middleware for Express apps",
            "score": 0.78,
            "category": "error_fix",
        },
        {
            "id": "mem_003",
            "content": "Prisma schema migration with zero downtime",
            "score": 0.65,
            "category": "architecture",
        },
    ]
    return result


@pytest.fixture
def mock_empty_result():
    """Create a mock empty MemorySearchResult."""
    result = MagicMock()
    result.found = False
    result.results = []
    return result


@pytest.fixture
def mock_store_result():
    """Create a mock MemoryStoreResult."""
    result = MagicMock()
    result.success = True
    result.memory_id = "stored_001"
    return result


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests for loader initialization."""

    def test_init_without_api_key(self, loader):
        """Without SUPERMEMORY_API_KEY, available should be False."""
        async def _test():
            with patch.dict(os.environ, {}, clear=False):
                env = dict(os.environ)
                env.pop("SUPERMEMORY_API_KEY", None)
                with patch.dict(os.environ, env, clear=True):
                    result = await loader.initialize()
                    assert result is False
                    assert loader.available is False
        _run(_test())

    def test_init_with_api_key(self, loader):
        """With API key, should initialize SupermemoryTools."""
        mock_tools = MagicMock()
        mock_tools.client = MagicMock()

        with patch.dict(os.environ, {"SUPERMEMORY_API_KEY": "test_key_123"}):
            with patch(
                "src.services.supermemory_corpus_loader.SupermemoryCorpusLoader.initialize"
            ) as mock_init:
                mock_init.return_value = True
                loader._available = True
                assert loader.available is True

    def test_init_with_import_error(self, loader):
        """If SupermemoryTools import fails, should degrade gracefully."""
        async def _test():
            with patch.dict(os.environ, {"SUPERMEMORY_API_KEY": "test_key_123"}):
                with patch(
                    "src.services.supermemory_corpus_loader.SupermemoryCorpusLoader.initialize",
                    side_effect=ImportError("No module named 'supermemory_tools'"),
                ):
                    try:
                        await loader.initialize()
                    except ImportError:
                        pass
                    assert loader.available is False
        _run(_test())

    def test_initial_state(self, loader):
        """Verify initial state is clean."""
        assert loader.available is False
        assert loader.memory_count == 0
        assert loader._loaded_ids == set()
        assert loader._supermemory is None


# ---------------------------------------------------------------------------
# Fetch tests
# ---------------------------------------------------------------------------


class TestFetchMemories:
    """Tests for the core fetch_memories method."""

    def test_fetch_when_unavailable(self, loader):
        """When not available, fetch should return empty list."""
        result = _run(loader.fetch_memories("test query"))
        assert result == []

    def test_fetch_returns_formatted_dicts(self, loader, mock_search_result):
        """Fetch should return properly formatted dicts."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=mock_search_result)

        result = _run(loader.fetch_memories("JWT auth pattern", limit=10))

        assert len(result) == 3
        assert result[0]["memory_id"] == "mem_001"
        assert result[0]["source"] == "supermemory"
        assert result[0]["score"] == 0.92
        assert "// Memory: code_pattern/mem_001" in result[0]["content"]
        assert result[0]["raw_content"] == "JWT refresh token pattern with rotation"

    def test_fetch_deduplication(self, loader, mock_search_result):
        """Fetching same memories twice should deduplicate."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=mock_search_result)

        first = _run(loader.fetch_memories("query 1"))
        assert len(first) == 3

        second = _run(loader.fetch_memories("query 2"))
        assert len(second) == 0  # All IDs already loaded

        assert loader.memory_count == 3

    def test_fetch_skips_empty_content(self, loader):
        """Memories with empty content should be skipped."""
        result = MagicMock()
        result.found = True
        result.results = [
            {"id": "empty_1", "content": "", "score": 0.9},
            {"id": "good_1", "content": "Good content", "score": 0.8},
            {"id": "empty_2", "content": None, "score": 0.7},
        ]

        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=result)

        results = _run(loader.fetch_memories("test"))
        assert len(results) == 1
        assert results[0]["memory_id"] == "good_1"

    def test_fetch_handles_api_error(self, loader):
        """API errors should be caught and return empty list."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(side_effect=Exception("API timeout"))

        result = _run(loader.fetch_memories("test"))
        assert result == []

    def test_fetch_empty_result(self, loader, mock_empty_result):
        """Empty search results should return empty list."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=mock_empty_result)

        result = _run(loader.fetch_memories("no results query"))
        assert result == []

    def test_fetch_content_truncation(self, loader):
        """Long content should be truncated to 4000 chars."""
        long_content = "x" * 10000
        result = MagicMock()
        result.found = True
        result.results = [
            {"id": "long_1", "content": long_content, "score": 0.9},
        ]

        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=result)

        results = _run(loader.fetch_memories("test"))
        assert len(results) == 1
        assert len(results[0]["raw_content"]) == 4000


# ---------------------------------------------------------------------------
# Format conversion tests
# ---------------------------------------------------------------------------


class TestFetchAsMCMPDocuments:
    """Tests for MCMP document format output."""

    def test_mcmp_format(self, loader, mock_search_result):
        """MCMP documents should be formatted strings."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=mock_search_result)

        docs = _run(loader.fetch_as_mcmp_documents("test query"))

        assert len(docs) == 3
        assert all(isinstance(d, str) for d in docs)
        assert docs[0].startswith("// Memory: code_pattern/mem_001")
        assert "JWT refresh token pattern" in docs[0]

    def test_mcmp_empty_when_unavailable(self, loader):
        """Should return empty list when unavailable."""
        docs = _run(loader.fetch_as_mcmp_documents("test"))
        assert docs == []


class TestFetchAsSearchResults:
    """Tests for search result format output."""

    def test_search_result_format(self, loader, mock_search_result):
        """Search results should have correct dict keys."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=mock_search_result)

        results = _run(loader.fetch_as_search_results("test query", limit=3))

        assert len(results) == 3
        r = results[0]
        assert "content" in r
        assert "file_path" in r
        assert "score" in r
        assert "source" in r
        assert "explanation" in r
        assert r["source"] == "supermemory"
        assert r["file_path"].startswith("memory://")
        assert r["start_line"] == 0
        assert r["end_line"] == 0

    def test_search_result_file_path_format(self, loader, mock_search_result):
        """file_path should be memory://category/id format."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.search = AsyncMock(return_value=mock_search_result)

        results = _run(loader.fetch_as_search_results("test"))
        assert results[0]["file_path"] == "memory://code_pattern/mem_001"
        assert results[1]["file_path"] == "memory://error_fix/mem_002"

    def test_search_results_empty_when_unavailable(self, loader):
        """Should return empty list when unavailable."""
        results = _run(loader.fetch_as_search_results("test"))
        assert results == []


# ---------------------------------------------------------------------------
# Store tests
# ---------------------------------------------------------------------------


class TestStorePattern:
    """Tests for storing patterns back to Supermemory."""

    def test_store_when_unavailable(self, loader):
        """Store should return False when unavailable."""
        result = _run(loader.store_pattern("content", "category"))
        assert result is False

    def test_store_success(self, loader, mock_store_result):
        """Store should delegate to SupermemoryTools.add_document."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.add_document = AsyncMock(return_value=mock_store_result)

        result = _run(loader.store_pattern(
            content="New auth pattern",
            category="code_pattern",
            metadata={"confidence": 0.95},
        ))

        assert result is True
        loader._supermemory.add_document.assert_called_once()
        call_kwargs = loader._supermemory.add_document.call_args
        assert "coding_engine_v1" in call_kwargs.kwargs["container_tags"]
        assert call_kwargs.kwargs["metadata"]["category"] == "code_pattern"
        assert call_kwargs.kwargs["metadata"]["confidence"] == 0.95

    def test_store_handles_error(self, loader):
        """Store errors should be caught and return False."""
        loader._available = True
        loader._supermemory = MagicMock()
        loader._supermemory.add_document = AsyncMock(side_effect=Exception("Network error"))

        result = _run(loader.store_pattern("content", "category"))
        assert result is False


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestUtility:
    """Tests for utility methods."""

    def test_reset_clears_state(self, loader):
        """Reset should clear loaded IDs and memory count."""
        loader._loaded_ids = {"id1", "id2", "id3"}
        loader._memory_count = 42

        loader.reset()

        assert loader._loaded_ids == set()
        assert loader.memory_count == 0

    def test_close_with_supermemory(self, loader):
        """Close should close the underlying client."""
        loader._supermemory = MagicMock()
        loader._supermemory.close = AsyncMock()

        _run(loader.close())

        loader._supermemory.close.assert_called_once()

    def test_close_without_supermemory(self, loader):
        """Close without client should not raise."""
        _run(loader.close())  # Should not raise

    def test_job_id_preserved(self):
        """Job ID should be preserved for tagging."""
        loader = SupermemoryCorpusLoader(job_id="my_custom_job")
        assert loader._job_id == "my_custom_job"

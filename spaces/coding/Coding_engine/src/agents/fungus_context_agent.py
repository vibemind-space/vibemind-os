"""
Fungus Context Agent - Provides semantic code context via la_fungus_search.

This agent integrates la_fungus_search RAG system to provide:
1. Code search during generation - Find similar patterns
2. Error context enrichment - Add relevant code context to BUILD_FAILED events
3. Project indexing - Index generated files for search
4. Event metadata enrichment - Enhance events with semantic context

Embedding options:
- Local: sentence-transformers with all-MiniLM-L6-v2 (default, works on Windows)
- OpenAI: Set OPENAI_API_KEY and use embedding_model="openai:text-embedding-3-small"
- Gemma: Requires JAX (may have issues on Windows)
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Any, List, Dict
import structlog

# Disable JAX to prevent DLL errors on Windows
os.environ.setdefault('JAX_PLATFORMS', 'cpu')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from ..secrets import get_secret
from ..services.project_indexer import ProjectIndexer
from src.llm_config import get_model

logger = structlog.get_logger(__name__)


class OpenAIEmbeddingClient:
    """Standalone OpenAI/OpenRouter embedding client - no transformers dependency."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com"
    ):
        import requests
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/')
        self._requests = requests

    def encode(self, texts: List[str]) -> List[List[float]]:
        """Encode texts to embeddings via OpenAI-compatible API."""
        if not texts:
            return []

        url = f"{self.base_url}/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Process in batches
        batch_size = 64
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Truncate long texts
            batch = [t[:6000] if t else " " for t in batch]

            payload = {
                "model": self.model,
                "input": batch,
                "encoding_format": "float"
            }

            response = self._requests.post(url, json=payload, headers=headers, timeout=90)
            response.raise_for_status()

            data = response.json()
            embeddings = [item['embedding'] for item in data.get('data', [])]
            all_embeddings.extend(embeddings)

        return all_embeddings


class SimpleTFIDFEmbedder:
    """Simple TF-IDF-like embedder for fallback when no API available."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        import hashlib
        self._hashlib = hashlib

    def encode(self, texts: List[str]) -> List[List[float]]:
        """Generate simple hash-based embeddings."""
        embeddings = []
        for text in texts:
            # Create a simple hash-based embedding
            words = text.lower().split()
            embedding = [0.0] * self.dim

            for word in words:
                # Hash each word to a position and value
                h = int(self._hashlib.md5(word.encode()).hexdigest(), 16)
                pos = h % self.dim
                val = ((h >> 8) % 1000) / 1000.0 - 0.5
                embedding[pos] += val

            # Normalize
            norm = sum(x*x for x in embedding) ** 0.5
            if norm > 0:
                embedding = [x / norm for x in embedding]

            embeddings.append(embedding)

        return embeddings


class FungusContextAgent(AutonomousAgent):
    """
    Agent that provides semantic code context via la_fungus_search.

    Uses:
    - RAG (Hybrid Search) for finding relevant code snippets
    - MCMP (200-agent swarm) for multi-hop dependency discovery
    - Judge LLM for relevance scoring
    """

    # Events this agent subscribes to
    subscribed_events = [
        EventType.BUILD_FAILED,
        EventType.TYPE_ERROR,
        EventType.CODE_FIX_NEEDED,
        EventType.GENERATION_REQUESTED,
        EventType.E2E_TEST_FAILED,
        EventType.FILE_CREATED,
        EventType.FILE_MODIFIED,
    ]

    # Fallback embedding models in order of preference (no JAX dependency)
    FALLBACK_MODELS = [
        "all-MiniLM-L6-v2",  # Fast, 384-dim, works on Windows
        "all-mpnet-base-v2",  # Better quality, 768-dim
        "openai:text-embedding-3-small",  # OpenAI API fallback
    ]

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        qdrant_url: str = "http://localhost:6333",
        embedding_model: str = "all-MiniLM-L6-v2",  # Default to model that works on Windows
        num_agents: int = 200,
        max_iterations: int = 50,
        judge_provider: str = "openrouter",
        judge_model: str = None,
        enable_mcmp: bool = True,
        enable_indexing: bool = True,
        enable_supermemory: bool = True,
        mcmp_config: Optional[Any] = None,  # SimulationConfig from mcmp_background
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )

        self.qdrant_url = qdrant_url
        self.embedding_model = embedding_model

        # Use mcmp_config values if provided, otherwise use direct parameters
        if mcmp_config:
            self.num_agents = mcmp_config.num_agents
            self.max_iterations = mcmp_config.max_iterations
            self.judge_provider = mcmp_config.judge_provider
            self.judge_model = mcmp_config.judge_model
        else:
            self.num_agents = num_agents
            self.max_iterations = max_iterations
            self.judge_provider = judge_provider
            self.judge_model = judge_model or get_model("judge")

        self.enable_mcmp = enable_mcmp
        self.enable_indexing = enable_indexing
        self.enable_supermemory = enable_supermemory
        self.mcmp_config = mcmp_config

        # Lazy-loaded components
        self._retriever = None
        self._qdrant_client = None
        self._embedder = None
        self._index = None
        self._collection_name = None
        self._embedding_dim = None
        self._llm_search_service = None  # LLM-based intelligent search
        self._project_indexer = None  # Primary search with Two-Stage + Re-Ranking
        self._supermemory_loader = None  # Phase 19: Supermemory corpus search

        # Content hash tracking to skip unnecessary re-indexing
        self._file_hashes: Dict[str, str] = {}

        self.logger = logger.bind(agent=self.name)

    def _get_collection_name(self) -> str:
        """Get Qdrant collection name for current project."""
        if self._collection_name:
            return self._collection_name
        # Use working directory name as collection identifier
        project_name = Path(self.working_dir).name
        self._collection_name = f"project_{project_name.replace('-', '_')}"
        return self._collection_name

    def _compute_content_hash(self, content: str) -> str:
        """Compute MD5 hash of file content for change detection."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    async def _needs_reindex(self, file_path: str, content: str) -> bool:
        """
        Check if a file needs re-indexing.

        Skips re-indexing if:
        1. Content hash matches the previously indexed version
        2. File already has chunks in Qdrant with matching hash

        Returns True if re-indexing is needed, False to skip.
        """
        content_hash = self._compute_content_hash(content)

        # Check in-memory hash cache first (fast path)
        if file_path in self._file_hashes:
            if self._file_hashes[file_path] == content_hash:
                self.logger.debug("skip_reindex_hash_match", file=file_path)
                return False

        # Check if file has chunks in Qdrant with matching hash
        if self._qdrant_client:
            try:
                from qdrant_client import models

                # Search for existing chunks for this file
                result = self._qdrant_client.scroll(
                    collection_name=self._get_collection_name(),
                    scroll_filter=models.Filter(
                        must=[models.FieldCondition(
                            key="file_path",
                            match=models.MatchValue(value=file_path)
                        )]
                    ),
                    limit=1,
                    with_payload=["content_hash"]
                )

                existing_points, _ = result
                if existing_points:
                    # Check if stored hash matches
                    stored_hash = existing_points[0].payload.get("content_hash")
                    if stored_hash == content_hash:
                        # Update in-memory cache and skip
                        self._file_hashes[file_path] = content_hash
                        self.logger.debug("skip_reindex_qdrant_hash_match", file=file_path)
                        return False

            except Exception as e:
                # On error, proceed with re-indexing
                self.logger.debug("hash_check_failed", file=file_path, error=str(e))

        # Update hash cache for new/changed file
        self._file_hashes[file_path] = content_hash
        return True

    async def _load_existing_hashes(self) -> int:
        """
        Load existing file hashes from Qdrant into memory cache.

        Called on startup to avoid re-querying Qdrant for each file.
        Returns the number of unique files with cached hashes.
        """
        if not self._qdrant_client:
            return 0

        try:
            from qdrant_client import models

            collection_name = self._get_collection_name()

            # Check if collection exists
            collections = self._qdrant_client.get_collections().collections
            if collection_name not in [c.name for c in collections]:
                return 0

            # Scroll through all points and extract file_path -> content_hash
            offset = None
            loaded = 0

            while True:
                result = self._qdrant_client.scroll(
                    collection_name=collection_name,
                    scroll_filter=None,
                    limit=100,
                    offset=offset,
                    with_payload=["file_path", "content_hash"]
                )

                points, next_offset = result
                if not points:
                    break

                for point in points:
                    file_path = point.payload.get("file_path")
                    content_hash = point.payload.get("content_hash")
                    if file_path and content_hash and file_path not in self._file_hashes:
                        self._file_hashes[file_path] = content_hash
                        loaded += 1

                if next_offset is None:
                    break
                offset = next_offset

            if loaded > 0:
                self.logger.info("loaded_existing_hashes", count=loaded)

            return loaded

        except Exception as e:
            self.logger.debug("load_hashes_failed", error=str(e))
            return 0

    async def _init_retriever(self) -> None:
        """Lazy-initialize the MCMP retriever."""
        if self._retriever is not None:
            return

        try:
            # Import la_fungus_search components
            import sys
            fungus_path = Path(__file__).parent.parent.parent / "la_fungus_search" / "src"
            if str(fungus_path) not in sys.path:
                sys.path.insert(0, str(fungus_path))

            from embeddinggemma.mcmp_rag import MCPMRetriever

            self._retriever = MCPMRetriever(
                embedding_model_name=self.embedding_model,
                num_agents=self.num_agents,
                max_iterations=self.max_iterations,
            )
            self.logger.info("mcpm_retriever_initialized")

            # Feed documents to the retriever
            await self._load_documents_to_retriever()

        except ImportError as e:
            self.logger.warning("mcpm_retriever_import_failed", error=str(e))
            self._retriever = None
        except Exception as e:
            self.logger.error("mcpm_retriever_init_failed", error=str(e))
            self._retriever = None

    async def _load_documents_to_retriever(self) -> int:
        """
        Load project documents into the MCMP retriever.

        Scans the working directory for source files and adds them
        to the retriever for semantic search.

        Returns:
            Number of documents loaded
        """
        if not self._retriever:
            return 0

        doc_texts = []
        extensions = ('.ts', '.tsx', '.py', '.js', '.jsx')
        working_path = Path(self.working_dir)

        # Scan for source files
        for root, dirs, files in os.walk(working_path):
            # Skip non-code directories
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', 'dist', 'build', '__pycache__', '.next')]

            for file in files:
                if file.endswith(extensions):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='replace')
                        if len(content) > 100:  # Skip tiny files
                            rel_path = file_path.relative_to(working_path)
                            # Format with file path for context
                            doc_text = f"FILE: {rel_path}\n\n{content[:5000]}"  # Limit content size
                            doc_texts.append(doc_text)
                    except Exception as e:
                        self.logger.debug("file_read_error", file=str(file_path), error=str(e))

        if doc_texts:
            try:
                self._retriever.add_documents(doc_texts)
                self.logger.info("mcpm_documents_loaded", count=len(doc_texts))
            except Exception as e:
                self.logger.warning("mcpm_document_load_failed", error=str(e))
                return 0

        return len(doc_texts)

    def _get_vector_dim(self) -> int:
        """Get vector dimension based on current embedding model."""
        if self._embedding_dim:
            return self._embedding_dim
        # Default dimensions by model
        model = self.embedding_model.lower()
        if "minilm" in model or "l6" in model:
            return 384
        elif "mpnet" in model:
            return 768
        elif "openai:" in model:
            return 1536
        elif "gemma" in model:
            return 768
        return 384  # Safe default

    async def _init_qdrant(self) -> None:
        """Lazy-initialize Qdrant client."""
        if self._qdrant_client is not None:
            return

        # Initialize embedder first to get correct dimension
        await self._init_embedder()

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._qdrant_client = QdrantClient(url=self.qdrant_url)

            # Ensure collection exists
            collection_name = self._get_collection_name()
            collections = self._qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            vector_dim = self._get_vector_dim()

            if collection_name not in collection_names:
                self._qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
                )
                self.logger.info(
                    "qdrant_collection_created",
                    collection=collection_name,
                    dim=vector_dim
                )
            else:
                # Check if dimension matches
                try:
                    info = self._qdrant_client.get_collection(collection_name)
                    existing_dim = info.config.params.vectors.size
                    if existing_dim != vector_dim:
                        self.logger.warning(
                            "qdrant_dimension_mismatch",
                            collection=collection_name,
                            expected=vector_dim,
                            existing=existing_dim,
                        )
                        # Recreate collection with correct dimension
                        self._qdrant_client.delete_collection(collection_name)
                        self._qdrant_client.create_collection(
                            collection_name=collection_name,
                            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
                        )
                        self.logger.info(
                            "qdrant_collection_recreated",
                            collection=collection_name,
                            dim=vector_dim
                        )
                except Exception:
                    pass
                self.logger.info("qdrant_collection_exists", collection=collection_name)

        except Exception as e:
            self.logger.warning("qdrant_init_failed", error=str(e))
            self._qdrant_client = None

    async def _init_embedder(self) -> None:
        """Lazy-initialize embedding backend with fallback support."""
        if self._embedder is not None:
            return

        # Try OpenAI embeddings first (uses OPENAI_API_KEY — preferred)
        openai_key = get_secret("openai_api_key")
        if openai_key:
            try:
                self._embedder = OpenAIEmbeddingClient(
                    api_key=openai_key,
                    model="text-embedding-3-small",
                    base_url="https://api.openai.com"
                )
                self._embedding_dim = 1536
                self.embedding_model = "openai:text-embedding-3-small"
                self.logger.info("embedder_initialized", model="openai:text-embedding-3-small", dim=1536)
                return
            except Exception as e:
                self.logger.debug(f"openai_embedder_failed: {e}")

        # Fallback to OpenRouter embeddings (uses OPENROUTER_API_KEY)
        openrouter_key = get_secret("openrouter_api_key")
        if openrouter_key:
            try:
                self._embedder = OpenAIEmbeddingClient(
                    api_key=openrouter_key,
                    model="openai/text-embedding-3-small",
                    base_url="https://openrouter.ai/api"
                )
                self._embedding_dim = 1536
                self.embedding_model = "openrouter:text-embedding-3-small"
                self.logger.info("embedder_initialized", model="openrouter:text-embedding-3-small", dim=1536)
                return
            except Exception as e:
                self.logger.debug(f"openrouter_embedder_failed: {e}")

        # Try sentence-transformers as fallback
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            self._embedding_dim = self._embedder.get_sentence_embedding_dimension()
            self.embedding_model = "all-MiniLM-L6-v2"
            self.logger.info("embedder_initialized", model="all-MiniLM-L6-v2", dim=self._embedding_dim)
            return
        except Exception as e:
            self.logger.debug(f"sentence_transformers_failed: {e}")

        # Final fallback: use simple TF-IDF-like embeddings (no dependencies)
        try:
            self._embedder = SimpleTFIDFEmbedder()
            self._embedding_dim = 384  # Fixed dimension for simple embeddings
            self.embedding_model = "simple-tfidf"
            self.logger.info("embedder_initialized", model="simple-tfidf", dim=384)
            return
        except Exception as e:
            self.logger.debug(f"simple_embedder_failed: {e}")

        self.logger.warning("embedder_init_failed_all_backends")
        self._embedder = None

    async def should_act(self, events: List[Event]) -> bool:
        """Determine if agent should act on events."""
        # Act on any subscribed event
        for event in events:
            if event.type in self.subscribed_events:
                return True
        return False

    async def act(self, events: List[Event]) -> None:
        """Process events and provide context enrichment."""
        for event in events:
            await self._process_event(event)

    async def _process_event(self, event: Event) -> None:
        """Process a single event."""
        try:
            if event.type == EventType.BUILD_FAILED:
                await self._handle_build_failed(event)
            elif event.type == EventType.TYPE_ERROR:
                await self._handle_type_error(event)
            elif event.type == EventType.CODE_FIX_NEEDED:
                await self._handle_code_fix_needed(event)
            elif event.type == EventType.GENERATION_REQUESTED:
                await self._handle_generation_requested(event)
            elif event.type == EventType.E2E_TEST_FAILED:
                await self._handle_e2e_failed(event)
            elif event.type in (EventType.FILE_CREATED, EventType.FILE_MODIFIED):
                if self.enable_indexing:
                    await self._handle_file_change(event)
        except Exception as e:
            self.logger.error("event_processing_failed", event_type=event.type, error=str(e))

    async def _handle_build_failed(self, event: Event) -> None:
        """Enrich BUILD_FAILED event with relevant code context."""
        await self._init_retriever()
        if not self._retriever:
            return

        error_data = event.data or {}
        error_message = error_data.get("message", "Build failed")

        # Search for relevant context
        query = f"fix build error: {error_message}"
        context = await self._search_context(query, top_k=5, mode="repair")

        if context:
            # Enrich event data with context
            event.data = event.data or {}
            event.data["fungus_context"] = context
            self.logger.info(
                "build_failed_enriched",
                context_count=len(context),
            )

    async def _handle_type_error(self, event: Event) -> None:
        """Enrich TYPE_ERROR event with relevant context."""
        await self._init_retriever()
        if not self._retriever:
            return

        error_data = event.data or {}
        file_path = error_data.get("file", "")
        message = error_data.get("message", "Type error")

        query = f"fix typescript type error in {file_path}: {message}"
        context = await self._search_context(query, top_k=3, mode="repair")

        if context:
            event.data = event.data or {}
            event.data["fungus_context"] = context

    async def _handle_code_fix_needed(self, event: Event) -> None:
        """Enrich CODE_FIX_NEEDED with pattern context."""
        await self._init_retriever()
        if not self._retriever:
            return

        fix_data = event.data or {}
        description = fix_data.get("description", "")

        query = f"implementation pattern for: {description}"
        context = await self._search_context(query, top_k=5, mode="steering")

        if context:
            event.data = event.data or {}
            event.data["fungus_context"] = context

    async def _handle_generation_requested(self, event: Event) -> None:
        """Find similar patterns for new feature generation."""
        await self._init_retriever()
        if not self._retriever:
            return

        gen_data = event.data or {}
        feature = gen_data.get("feature", "")

        if feature:
            query = f"implementation of {feature}"
            context = await self._search_context(query, top_k=10, mode="structure")

            if context:
                event.data = event.data or {}
                event.data["fungus_context"] = context

    async def _handle_e2e_failed(self, event: Event) -> None:
        """Enrich E2E_TEST_FAILED with detailed analysis."""
        await self._init_retriever()
        if not self._retriever:
            return

        test_data = event.data or {}
        test_name = test_data.get("test", "")
        error = test_data.get("error", "")

        query = f"fix e2e test {test_name}: {error}"
        context = await self._search_context(query, top_k=5, mode="deep")

        if context:
            event.data = event.data or {}
            event.data["fungus_context"] = context

    def _has_git_changes(self, file_path: str) -> bool:
        """
        Check if a file has actual content changes using git.

        This is more accurate than mtime-based detection because:
        1. Git compares actual content, not timestamps
        2. Avoids re-indexing on file touch without content change
        3. Catches changes even if mtime wasn't updated

        Returns:
            True if file has changes (or git unavailable), False if unchanged
        """
        try:
            file_dir = os.path.dirname(file_path) or '.'

            # Check if this file has changes compared to git index
            diff_result = json.loads(self.tool_registry.call_tool(
                "git.diff", name_only=True, paths=file_path, cwd=file_dir
            ))
            if "error" not in diff_result and diff_result.get("count", 0) > 0:
                return True

            # Also check for untracked files (new files not in git)
            status_result = json.loads(self.tool_registry.call_tool(
                "git.status", paths=file_path, cwd=file_dir
            ))
            if "error" not in status_result and not status_result.get("clean", True):
                return True

            # No changes detected
            self.logger.debug("git_no_changes", file=file_path)
            return False

        except Exception as e:
            # Git not available or error - assume file changed (safe fallback)
            self.logger.debug("git_check_failed", file=file_path, error=str(e))
            return True

    async def _handle_file_change(self, event: Event) -> None:
        """Index new/modified file for search.

        Uses git-based change detection to avoid unnecessary re-indexing
        when files are touched but content is unchanged.
        """
        file_data = event.data or {}
        file_path = file_data.get("file_path", "") or getattr(event, 'file_path', '')

        if not file_path or not os.path.exists(file_path):
            return

        # Only index TypeScript/Python files
        if not file_path.endswith(('.ts', '.tsx', '.py', '.js', '.jsx')):
            return

        # Use git to check if file actually has content changes
        # This avoids re-indexing on mtime-only changes (file touch)
        if not self._has_git_changes(file_path):
            self.logger.debug("skipping_unchanged_file", file=file_path)
            return

        await self._index_file(file_path)

    async def _init_llm_search(self) -> None:
        """Initialize LLM-based search service if OpenRouter key is available."""
        if self._llm_search_service is not None:
            return

        if not get_secret("openrouter_api_key"):
            self.logger.debug("llm_search_disabled", reason="No OPENROUTER_API_KEY")
            return

        try:
            from ..services.llm_search_service import LLMSearchService
            self._llm_search_service = LLMSearchService(
                working_dir=self.working_dir,
                qdrant_url=self.qdrant_url,
            )
            self.logger.info("llm_search_service_initialized")
        except Exception as e:
            self.logger.debug(f"llm_search_init_failed: {e}")

    async def _init_project_indexer(self) -> None:
        """Initialize ProjectIndexer with Two-Stage Search + Re-Ranking."""
        if self._project_indexer is not None:
            return

        try:
            self._project_indexer = ProjectIndexer(
                project_dir=self.working_dir,
                qdrant_url=self.qdrant_url,
            )
            self.logger.info("project_indexer_initialized")
        except Exception as e:
            self.logger.debug(f"project_indexer_init_failed: {e}")

    async def _init_supermemory(self) -> None:
        """Lazy-initialize Supermemory corpus loader for memory search."""
        if self._supermemory_loader is not None:
            return
        if not self.enable_supermemory:
            return

        try:
            from ..services.supermemory_corpus_loader import SupermemoryCorpusLoader

            self._supermemory_loader = SupermemoryCorpusLoader(
                job_id=f"context_{Path(self.working_dir).name}"
            )
            await self._supermemory_loader.initialize()
        except Exception as e:
            self.logger.debug(f"supermemory_init_failed: {e}")

    async def _search_context(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "steering",
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant code context + Supermemory memories.

        Phase 19: Supermemory search runs in parallel with code search.
        Memory results are merged with code results and sorted by score.

        Uses LLM-based intelligent search when available, which:
        1. Classifies query as code-specific, conceptual, or mixed
        2. Routes to appropriate search strategy
        3. Uses LLM to rank and explain results

        Args:
            query: Search query
            top_k: Number of results to return
            mode: Judge mode (repair, steering, deep, structure)

        Returns:
            List of context results with content and metadata
        """
        # Phase 19: Launch Supermemory search in parallel with code search
        memory_task = None
        if self.enable_supermemory:
            await self._init_supermemory()
            if self._supermemory_loader and self._supermemory_loader.available:
                category = {
                    "repair": "error_fix",
                    "steering": "all",
                    "deep": "all",
                    "structure": "architecture",
                }.get(mode, "all")

                memory_task = asyncio.create_task(
                    self._supermemory_loader.fetch_as_search_results(
                        query=query,
                        category=category,
                        limit=min(3, top_k),
                    )
                )

        # PRIMARY: ProjectIndexer with Two-Stage Search + Re-Ranking
        # This uses our improved search that prioritizes implementation files
        # over marker files, with path matching and content analysis
        code_results = []
        await self._init_project_indexer()
        if self._project_indexer:
            try:
                results = await self._project_indexer.search(query, top_k=top_k, rerank=True)
                if results:
                    # Check if results are good quality (top score > 0.5)
                    top_score = results[0].get("score", 0) if results else 0
                    if top_score > 0.5:
                        self.logger.debug(
                            "project_indexer_search_success",
                            query=query[:50],
                            top_score=top_score,
                            count=len(results),
                        )
                        code_results = results
            except Exception as e:
                self.logger.debug(f"project_indexer_search_failed: {e}")

        # FALLBACK 1: LLM-powered search (if no good code results yet)
        if not code_results:
            await self._init_llm_search()
            if self._llm_search_service:
                try:
                    results = await self._llm_search_service.search(query, top_k=top_k)
                    if results:
                        code_results = [
                            {
                                "content": r.content,
                                "file_path": r.file_path,
                                "start_line": r.start_line,
                                "end_line": r.end_line,
                                "score": r.score,
                                "source": r.source,
                                "explanation": r.explanation,
                                "relationships": r.relationships,
                            }
                            for r in results
                        ]
                except Exception as e:
                    self.logger.debug(f"llm_search_failed: {e}")

        # FALLBACK 2: Direct Qdrant search (without re-ranking)
        if not code_results:
            await self._init_qdrant()
            if self._qdrant_client and self._embedder:
                try:
                    results = await self._qdrant_search(query, top_k)
                    if results:
                        code_results = results
                except Exception as e:
                    self.logger.debug(f"qdrant_search_failed: {e}")

        # FALLBACK 3: MCMP retriever
        if not code_results and self._retriever:
            try:
                if self.enable_mcmp:
                    self._retriever.initialize_simulation(query)
                    for _ in range(min(20, self.max_iterations)):
                        self._retriever.step(1)
                    results = self._retriever.search(query, top_k=top_k)
                else:
                    results = self._retriever.search(query, top_k=top_k)

                raw = results.get("results", results.get("documents", []))
                if raw:
                    code_results = raw
            except Exception as e:
                self.logger.warning("retriever_search_failed", query=query[:50], error=str(e))

        # Phase 19: Collect memory results (if task was started)
        memory_results = []
        if memory_task:
            try:
                memory_results = await asyncio.wait_for(memory_task, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.debug("supermemory_search_timeout", query=query[:50])
            except Exception as e:
                self.logger.debug("supermemory_search_error", error=str(e))

        # Merge code + memory results, sort by score
        if memory_results:
            merged = code_results + memory_results
            merged.sort(key=lambda x: x.get("score", 0), reverse=True)
            self.logger.debug(
                "search_context_merged",
                code_count=len(code_results),
                memory_count=len(memory_results),
                total=len(merged),
            )
            return merged[:top_k]

        return code_results

    async def _qdrant_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search Qdrant collection using embeddings."""
        if not self._qdrant_client or not self._embedder:
            return []

        try:
            # Embed the query
            query_embedding = self._embedder.encode([query])[0]

            # Search Qdrant
            results = self._qdrant_client.search(
                collection_name=self._get_collection_name(),
                query_vector=query_embedding,
                limit=top_k,
            )

            # Convert to dict format
            return [
                {
                    "content": hit.payload.get("content", ""),
                    "file_path": hit.payload.get("file_path", ""),
                    "start_line": hit.payload.get("start_line", 0),
                    "end_line": hit.payload.get("end_line", 0),
                    "score": hit.score,
                }
                for hit in results
            ]
        except Exception as e:
            self.logger.debug(f"qdrant_search_error: {e}")
            return []

    async def _index_file(self, file_path: str) -> None:
        """Index a single file to Qdrant."""
        await self._init_qdrant()
        await self._init_embedder()

        if not self._qdrant_client or not self._embedder:
            return

        try:
            # 1. Read file content first (need it for hash check)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Skip empty files
            if not content.strip():
                return

            # 2. Check if re-indexing is needed (hash comparison)
            if not await self._needs_reindex(file_path, content):
                return  # Skip - content unchanged

            # 3. DELETE old points for this file (prevents duplicates on re-index)
            from qdrant_client import models
            self._qdrant_client.delete(
                collection_name=self._get_collection_name(),
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[models.FieldCondition(
                            key="file_path",
                            match=models.MatchValue(value=file_path)
                        )]
                    )
                )
            )
            self.logger.debug("old_chunks_deleted", file=file_path)

            # 4. Chunk the content
            chunks = self._chunk_content(content, file_path)

            if not chunks:
                return

            # 5. Embed chunks
            texts = [c["content"] for c in chunks]
            embeddings = self._embedder.encode(texts)

            # 6. Store new chunks in Qdrant with content hash
            from qdrant_client.models import PointStruct
            import uuid

            content_hash = self._compute_content_hash(content)
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb.tolist() if hasattr(emb, 'tolist') else list(emb),
                    payload={
                        "file_path": file_path,
                        "content": chunk["content"],
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"],
                        "content_hash": content_hash,  # For skip-reindex check
                    }
                )
                for emb, chunk in zip(embeddings, chunks)
            ]

            self._qdrant_client.upsert(
                collection_name=self._get_collection_name(),
                points=points,
            )

            self.logger.debug(
                "file_indexed",
                file=file_path,
                chunks=len(chunks),
                content_hash=content_hash[:8],  # Log first 8 chars
            )

        except Exception as e:
            self.logger.warning("file_indexing_failed", file=file_path, error=str(e))

    def _chunk_content(self, content: str, file_path: str, lines_per_chunk: int = 30) -> List[Dict]:
        """Split content into chunks for indexing."""
        lines = content.splitlines()
        chunks = []

        for i in range(0, len(lines), lines_per_chunk):
            chunk_lines = lines[i:i + lines_per_chunk]
            chunk_content = "\n".join(chunk_lines)

            if chunk_content.strip():
                chunks.append({
                    "content": chunk_content,
                    "start_line": i + 1,
                    "end_line": min(i + lines_per_chunk, len(lines)),
                    "file": file_path,
                })

        return chunks

    async def index_project(self) -> int:
        """
        Index all project files.

        Uses content hash caching to skip unchanged files:
        1. Loads existing hashes from Qdrant on first call
        2. Compares file content hash before re-indexing
        3. Only re-indexes files with changed content

        Returns:
            Number of files processed (not necessarily re-indexed)
        """
        await self._init_qdrant()
        await self._init_embedder()

        if not self._qdrant_client or not self._embedder:
            return 0

        # Load existing hashes from Qdrant (fast path for unchanged files)
        cached_count = await self._load_existing_hashes()
        if cached_count > 0:
            self.logger.info("index_cache_loaded", cached_files=cached_count)

        processed_count = 0
        extensions = ('.ts', '.tsx', '.py', '.js', '.jsx')

        for root, dirs, files in os.walk(self.working_dir):
            # Skip common non-code directories
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', 'dist', 'build', '__pycache__')]

            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    await self._index_file(file_path)  # Will skip if hash unchanged
                    processed_count += 1

        self.logger.info(
            "project_indexed",
            processed=processed_count,
            cached=cached_count,
        )
        return processed_count

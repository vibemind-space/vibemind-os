"""
Project Indexer Service - Indexes generated projects into Qdrant.

Provides:
1. Full project indexing - Index all code files at project start
2. Incremental indexing - Re-index single files on change
3. AST-based chunking - Preserve function/class boundaries
4. Metadata enrichment - File paths, line numbers, AST node types
"""

import asyncio
import os
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CodeChunk:
    """A chunk of code with metadata."""
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str = "code"  # "function", "class", "file", "line_chunk"
    node_name: Optional[str] = None  # Function/class name if applicable
    metadata: Dict[str, Any] = field(default_factory=dict)


class ASTChunker:
    """AST-based code chunker for Python files."""

    def chunk_python_file(self, file_path: str, content: str) -> List[CodeChunk]:
        """Chunk a Python file using AST parsing."""
        try:
            tree = ast.parse(content)
            chunks = []
            lines = content.splitlines()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Get source segment
                    start_line = node.lineno
                    end_line = node.end_lineno or start_line

                    chunk_content = "\n".join(lines[start_line - 1:end_line])

                    node_type = type(node).__name__
                    chunk_type = "function" if "FunctionDef" in node_type else "class"

                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type=chunk_type,
                        node_name=node.name,
                        metadata={
                            "ast_type": node_type,
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                        }
                    ))

            # If no AST nodes found, fall back to line-based
            if not chunks:
                return self.chunk_by_lines(file_path, content)

            return chunks

        except SyntaxError:
            # Fall back to line-based chunking
            return self.chunk_by_lines(file_path, content)

    def chunk_by_lines(
        self,
        file_path: str,
        content: str,
        lines_per_chunk: int = 30,
    ) -> List[CodeChunk]:
        """Chunk content by fixed line count."""
        lines = content.splitlines()
        chunks = []

        for i in range(0, len(lines), lines_per_chunk):
            chunk_lines = lines[i:i + lines_per_chunk]
            chunk_content = "\n".join(chunk_lines)

            if chunk_content.strip():
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    start_line=i + 1,
                    end_line=min(i + lines_per_chunk, len(lines)),
                    chunk_type="line_chunk",
                ))

        return chunks


class TypeScriptChunker:
    """Simple chunker for TypeScript/JavaScript files."""

    def chunk_file(
        self,
        file_path: str,
        content: str,
        lines_per_chunk: int = 40,
    ) -> List[CodeChunk]:
        """
        Chunk TypeScript/JavaScript by function/component boundaries.

        Uses simple heuristics to find boundaries:
        - function declarations
        - arrow function assignments
        - class declarations
        - React component definitions
        """
        lines = content.splitlines()
        chunks = []
        current_chunk_start = 0

        # Patterns that likely indicate new logical units
        boundary_patterns = [
            "export function ",
            "export const ",
            "export default ",
            "function ",
            "const ",
            "class ",
            "interface ",
            "type ",
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check if this line starts a new logical unit
            is_boundary = any(stripped.startswith(p) for p in boundary_patterns)

            # If boundary found and we have accumulated lines, save chunk
            if is_boundary and i > current_chunk_start:
                chunk_content = "\n".join(lines[current_chunk_start:i])
                if chunk_content.strip():
                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=current_chunk_start + 1,
                        end_line=i,
                        chunk_type="code",
                    ))
                current_chunk_start = i

            # Also chunk if we've accumulated too many lines
            if i - current_chunk_start >= lines_per_chunk:
                chunk_content = "\n".join(lines[current_chunk_start:i])
                if chunk_content.strip():
                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=current_chunk_start + 1,
                        end_line=i,
                        chunk_type="line_chunk",
                    ))
                current_chunk_start = i

        # Don't forget the last chunk
        if current_chunk_start < len(lines):
            chunk_content = "\n".join(lines[current_chunk_start:])
            if chunk_content.strip():
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    start_line=current_chunk_start + 1,
                    end_line=len(lines),
                    chunk_type="code",
                ))

        return chunks


class ContentAnalyzer:
    """
    Analyzes code content for relevance signals.

    Used to distinguish implementation code from marker/declaration files
    and to detect HTTP fetch patterns for better search ranking.
    """

    # Patterns indicating marker/declaration content (less useful for implementation queries)
    MARKER_PATTERNS = [
        r'^\s*interface\s+\w+',           # interface Foo {
        r'^\s*type\s+\w+\s*=',             # type Foo =
        r'^\s*export\s+const\s+\w+\s*=\s*["\'{[]',  # export const X = '...' or [...] or {...}
        r'^\s*export\s+type\s+',           # export type
        r'^\s*export\s+interface\s+',      # export interface
        r'^\s*declare\s+',                 # declare module/const/etc
    ]

    # Patterns indicating implementation code (more useful)
    IMPL_PATTERNS = [
        r'\b(if|for|while|switch)\s*\(',   # Control flow
        r'\bawait\s+',                      # Async operations
        r'\bfetch\s*\(',                    # HTTP fetch
        r'\baxios\.',                       # Axios calls
        r'\breturn\s+\w',                   # Return statements
        r'\btry\s*\{',                      # Try blocks
        r'\bcatch\s*\(',                    # Catch blocks
        r'\bnew\s+\w+\(',                   # Object instantiation
        r'\.then\s*\(',                     # Promise chains
        r'\.map\s*\(',                      # Array operations
        r'\.filter\s*\(',
        r'\.reduce\s*\(',
    ]

    # HTTP call patterns for boosting API-related code
    FETCH_PATTERNS = [
        r'fetch\s*\(',
        r'axios\.',
        r'\.get\s*\(',
        r'\.post\s*\(',
        r'\.put\s*\(',
        r'\.delete\s*\(',
        r'useMutation',
        r'useQuery',
    ]

    @classmethod
    def implementation_score(cls, content: str) -> float:
        """
        Calculate implementation vs declaration score.

        Returns:
            Float from 0.0 to 1.0 where:
            - 0.0-0.3: Mostly markers/declarations
            - 0.3-0.7: Mixed content
            - 0.7-1.0: Mostly implementation
        """
        lines = content.splitlines()
        if not lines:
            return 0.5

        marker_count = 0
        impl_count = 0

        for line in lines:
            # Count marker patterns
            for pattern in cls.MARKER_PATTERNS:
                if re.match(pattern, line):
                    marker_count += 1
                    break

            # Count implementation patterns
            for pattern in cls.IMPL_PATTERNS:
                if re.search(pattern, line):
                    impl_count += 1
                    break

        total_lines = len(lines)
        marker_ratio = marker_count / total_lines if total_lines > 0 else 0
        impl_ratio = impl_count / total_lines if total_lines > 0 else 0

        # Heavy penalty for marker-dominated content
        if marker_ratio > 0.5:
            return max(0.1, impl_ratio * 0.5)

        # Reward implementation-heavy content
        if impl_ratio > 0.3:
            return min(1.0, 0.5 + impl_ratio)

        # Default: balanced score based on impl ratio
        return 0.3 + (impl_ratio * 0.7)

    @classmethod
    def has_fetch_pattern(cls, content: str) -> bool:
        """
        Check if content contains HTTP fetch/API call patterns.

        Returns:
            True if fetch patterns found
        """
        for pattern in cls.FETCH_PATTERNS:
            if re.search(pattern, content):
                return True
        return False

    @classmethod
    def is_marker_file(cls, content: str) -> bool:
        """
        Determine if content is primarily a marker/declaration file.

        Returns:
            True if content appears to be mostly declarations
        """
        lines = content.splitlines()
        if not lines:
            return False

        marker_count = sum(
            1 for line in lines
            if any(re.match(p, line) for p in cls.MARKER_PATTERNS)
        )

        return (marker_count / len(lines)) > 0.4


class ProjectIndexer:
    """
    Indexes generated projects into Qdrant vector store.

    Features:
    - AST-based chunking for Python
    - Heuristic chunking for TypeScript
    - Incremental re-indexing on file changes
    - Per-project collections
    """

    SUPPORTED_EXTENSIONS = {
        '.py': 'python',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.js': 'javascript',
        '.jsx': 'javascript',
    }

    SKIP_DIRS = {
        'node_modules', '.git', 'dist', 'build', '__pycache__',
        '.venv', 'venv', '.next', 'out', 'coverage', '.pytest_cache',
    }

    def __init__(
        self,
        project_dir: str,
        qdrant_url: str = "http://localhost:6333",
        collection_prefix: str = "project_",
        embedding_model: str = "openai:text-embedding-3-small",
    ):
        self.project_dir = Path(project_dir)
        self.qdrant_url = qdrant_url
        self.collection_prefix = collection_prefix
        self.embedding_model = embedding_model

        self._qdrant_client = None
        self._embedder = None
        self._python_chunker = ASTChunker()
        self._ts_chunker = TypeScriptChunker()

        self.logger = logger.bind(component="ProjectIndexer")

    def _get_collection_name(self) -> str:
        """Get Qdrant collection name for project."""
        project_name = self.project_dir.name.replace('-', '_')
        return f"{self.collection_prefix}{project_name}"

    async def _init_qdrant(self) -> bool:
        """Initialize Qdrant client and ensure collection exists."""
        if self._qdrant_client is not None:
            return True

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._qdrant_client = QdrantClient(url=self.qdrant_url)

            collection_name = self._get_collection_name()
            collections = self._qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if collection_name not in collection_names:
                self._qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
                self.logger.info("collection_created", name=collection_name)

            return True
        except Exception as e:
            self.logger.error("qdrant_init_failed", error=str(e))
            return False

    async def _init_embedder(self) -> bool:
        """Initialize embedding backend."""
        if self._embedder is not None:
            return True

        try:
            import os
            import sys

            # Disable JAX completely to avoid circular import issues with transformers
            os.environ["JAX_PLATFORMS"] = ""
            os.environ["USE_TORCH"] = "1"
            os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

            # Block JAX import entirely by adding a mock package
            if "jax" not in sys.modules:
                import types
                from importlib.machinery import ModuleSpec
                fake_jax = types.ModuleType("jax")
                fake_jax.__version__ = "0.0.0"
                fake_jax.__path__ = []  # Required: marks as package so submodule imports work
                fake_jax.__spec__ = ModuleSpec("jax", None, is_package=True)

                # Create submodules that transformers may try to import
                fake_jax_numpy = types.ModuleType("jax.numpy")
                fake_jax_numpy.__spec__ = ModuleSpec("jax.numpy", None)
                fake_jax.numpy = fake_jax_numpy

                fake_jax_version = types.ModuleType("jax.version")
                fake_jax_version.__version__ = "0.0.0"
                fake_jax_version.__spec__ = ModuleSpec("jax.version", None)
                fake_jax.version = fake_jax_version

                sys.modules["jax"] = fake_jax
                sys.modules["jax.numpy"] = fake_jax_numpy
                sys.modules["jax.version"] = fake_jax_version

            fungus_path = Path(__file__).parent.parent.parent / "la_fungus_search" / "src"
            if str(fungus_path) not in sys.path:
                sys.path.insert(0, str(fungus_path))

            # Try OpenAI embeddings first (most reliable)
            if self.embedding_model.startswith("openai:") and os.environ.get("OPENAI_API_KEY"):
                import httpx
                model_name = self.embedding_model.split(":", 1)[1]

                class OpenAIEmbedder:
                    """Lightweight OpenAI embedding wrapper."""
                    def __init__(self, model: str, api_key: str):
                        self.model = model
                        self.api_key = api_key
                        self.dim = 1536

                    def encode(self, texts, **kwargs):
                        import httpx as _httpx
                        if isinstance(texts, str):
                            texts = [texts]
                        resp = _httpx.post(
                            "https://api.openai.com/v1/embeddings",
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            json={"model": self.model, "input": texts[:20]},
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            return [d["embedding"] for d in data["data"]]
                        return [[0.0] * self.dim] * len(texts)

                self._embedder = OpenAIEmbedder(model_name, os.environ["OPENAI_API_KEY"])
                self.logger.info("embedder_initialized", model=self.embedding_model, provider="openai")
                return True

            # Fallback: try embeddinggemma
            from embeddinggemma.mcmp.embeddings import load_sentence_model
            self._embedder = load_sentence_model(self.embedding_model)
            return True
        except Exception as e:
            self.logger.warning("embedder_init_failed", error=str(e), hint="Continuing without semantic search")
            self._embedder = None
            return False

    def _chunk_file(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk a file based on its type."""
        ext = file_path.suffix.lower()
        lang = self.SUPPORTED_EXTENSIONS.get(ext)

        if lang == 'python':
            return self._python_chunker.chunk_python_file(str(file_path), content)
        elif lang in ('typescript', 'javascript'):
            return self._ts_chunker.chunk_file(str(file_path), content)
        else:
            # Fallback to line-based
            return self._python_chunker.chunk_by_lines(str(file_path), content)

    async def index_project(self) -> Dict[str, int]:
        """
        Index all supported files in the project.

        Returns:
            Dict with stats: files_indexed, chunks_indexed, errors
        """
        if not await self._init_qdrant():
            return {"files_indexed": 0, "chunks_indexed": 0, "errors": 1}

        if not await self._init_embedder():
            return {"files_indexed": 0, "chunks_indexed": 0, "errors": 1}

        stats = {"files_indexed": 0, "chunks_indexed": 0, "errors": 0}

        for root, dirs, files in os.walk(self.project_dir):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                file_path = Path(root) / file

                try:
                    indexed = await self.index_file(file_path)
                    if indexed > 0:
                        stats["files_indexed"] += 1
                        stats["chunks_indexed"] += indexed
                except Exception as e:
                    self.logger.warning("file_index_failed", file=str(file_path), error=str(e))
                    stats["errors"] += 1

        self.logger.info("project_indexed", **stats)
        return stats

    async def index_file(self, file_path: Path) -> int:
        """
        Index a single file.

        Returns:
            Number of chunks indexed
        """
        if not await self._init_qdrant():
            return 0

        if not await self._init_embedder():
            return 0

        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            self.logger.warning("file_read_failed", file=str(file_path), error=str(e))
            return 0

        if not content.strip():
            return 0

        # Chunk the file
        chunks = self._chunk_file(file_path, content)
        if not chunks:
            return 0

        # Embed chunks
        try:
            texts = [c.content for c in chunks]
            embeddings = self._embedder.encode(texts)
        except Exception as e:
            self.logger.warning("embedding_failed", file=str(file_path), error=str(e))
            return 0

        # Store in Qdrant
        try:
            from qdrant_client.models import PointStruct, FilterSelector, Filter, FieldCondition, MatchValue
            import uuid

            # Delete existing points for this file first
            collection_name = self._get_collection_name()
            try:
                self._qdrant_client.delete(
                    collection_name=collection_name,
                    points_selector=FilterSelector(
                        filter=Filter(
                            must=[
                                FieldCondition(
                                    key="file_path",
                                    match=MatchValue(value=str(file_path))
                                )
                            ]
                        )
                    )
                )
            except Exception:
                # Ignore delete errors - collection might be empty or fresh
                pass

            # Insert new points with enriched metadata
            points = []
            for emb, chunk in zip(embeddings, chunks):
                # Calculate content analysis scores
                impl_score = ContentAnalyzer.implementation_score(chunk.content)
                has_fetch = ContentAnalyzer.has_fetch_pattern(chunk.content)
                is_marker = ContentAnalyzer.is_marker_file(chunk.content)

                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb.tolist() if hasattr(emb, 'tolist') else list(emb),
                    payload={
                        "file_path": str(file_path),
                        "relative_path": str(file_path.relative_to(self.project_dir)),
                        "content": chunk.content,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "chunk_type": chunk.chunk_type,
                        "node_name": chunk.node_name,
                        # NEW: Pre-computed relevance signals
                        "impl_score": impl_score,
                        "has_fetch": has_fetch,
                        "is_marker": is_marker,
                    }
                ))

            self._qdrant_client.upsert(
                collection_name=collection_name,
                points=points,
            )

            return len(chunks)

        except Exception as e:
            self.logger.warning("qdrant_upsert_failed", file=str(file_path), error=str(e))
            return 0

    async def search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search indexed project for relevant code with optional re-ranking.

        Re-ranking uses multiple signals:
        - Embedding similarity (50% weight)
        - Implementation score (30% weight) - favors actual code over declarations
        - Fetch pattern presence (20% weight) - for API-related queries

        Args:
            query: Search query
            top_k: Number of results
            rerank: Whether to apply multi-signal re-ranking (default: True)

        Returns:
            List of matching chunks with metadata and scores
        """
        if not await self._init_qdrant():
            return []

        if not await self._init_embedder():
            return []

        try:
            # Embed query
            query_vec = self._embedder.encode([query])[0]
            if hasattr(query_vec, 'tolist'):
                query_vec = query_vec.tolist()

            # Get MANY more results for re-ranking - embedding model may not rank
            # implementation files highly even when they're most relevant
            fetch_limit = max(50, top_k * 10) if rerank else top_k

            # Search Qdrant - Stage 1: Pure embedding similarity
            results = self._qdrant_client.search(
                collection_name=self._get_collection_name(),
                query_vector=query_vec,
                limit=fetch_limit,
            )

            # Stage 2: Also search for files matching query terms in path
            # This compensates for embedding model limitations on code
            from qdrant_client.models import Filter, FieldCondition, MatchText

            path_filter_results = []
            significant_terms = [
                term for term in re.split(r'\W+', query.lower())
                if len(term) >= 3 and term not in (
                    'the', 'and', 'for', 'with', 'from', 'this', 'that', 'code', 'file'
                )
            ]

            # Search for individual terms with higher limit
            for term in significant_terms[:4]:
                try:
                    filtered = self._qdrant_client.search(
                        collection_name=self._get_collection_name(),
                        query_vector=query_vec,
                        limit=30,  # Increased from 15
                        query_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="relative_path",
                                    match=MatchText(text=term)
                                )
                            ]
                        )
                    )
                    path_filter_results.extend(filtered)
                except Exception:
                    pass

            # Also search for combined camelCase terms (e.g., "orderCrud" from "order" + "crud")
            # This helps find files like "orderCrudAPI.ts" that embedding model misses
            # Try all permutations of term pairs (limited to first 4 terms)
            from itertools import permutations
            for term1, term2 in permutations(significant_terms[:4], 2):
                combined = term1 + term2.capitalize()
                if len(combined) > 6:  # Only for meaningful combinations
                    try:
                        filtered = self._qdrant_client.search(
                            collection_name=self._get_collection_name(),
                            query_vector=query_vec,
                            limit=50,  # High limit to capture low-embedding files
                            query_filter=Filter(
                                must=[
                                    FieldCondition(
                                        key="relative_path",
                                        match=MatchText(text=combined)
                                    )
                                ]
                            )
                        )
                        path_filter_results.extend(filtered)
                    except Exception:
                        pass

            # Merge results, deduplicate by point ID
            seen_ids = {r.id for r in results}
            for r in path_filter_results:
                if r.id not in seen_ids:
                    results.append(r)
                    seen_ids.add(r.id)

            if not results:
                return []

            # Check if query is API/fetch related for bonus weighting
            query_lower = query.lower()
            is_api_query = any(
                term in query_lower
                for term in ['fetch', 'api', 'endpoint', 'crud', 'http', 'request', 'axios']
            )

            # Extract query terms for path matching bonus
            query_terms = [
                term for term in re.split(r'\W+', query_lower)
                if len(term) > 2 and term not in ('the', 'and', 'for', 'with')
            ]

            # Build result list with optional re-ranking
            scored_results = []
            for hit in results:
                content = hit.payload.get("content", "")

                # Get pre-computed scores or calculate on-the-fly
                impl_score = hit.payload.get("impl_score")
                has_fetch = hit.payload.get("has_fetch")
                is_marker = hit.payload.get("is_marker")

                # Calculate if not pre-computed (backward compat)
                if impl_score is None:
                    impl_score = ContentAnalyzer.implementation_score(content)
                if has_fetch is None:
                    has_fetch = ContentAnalyzer.has_fetch_pattern(content)
                if is_marker is None:
                    is_marker = ContentAnalyzer.is_marker_file(content)

                # Calculate composite score if re-ranking enabled
                path_bonus = 0.0
                if rerank:
                    embedding_score = hit.score

                    # Fetch bonus only applies for API-related queries
                    fetch_bonus = 0.3 if (has_fetch and is_api_query) else 0.0

                    # Marker penalty - heavier for marker-dominated files
                    marker_penalty = 0.6 if is_marker else 1.0

                    # Path matching bonus: boost files whose path contains query terms
                    rel_path = hit.payload.get("relative_path", "").lower()
                    path_match_count = sum(1 for term in query_terms if term in rel_path)
                    # Strong bonus for path matches (0.15 per term, max 0.45)
                    path_bonus = min(0.45, path_match_count * 0.15)

                    # Composite score (rebalanced):
                    # - 35% embedding similarity (reduced from 50%)
                    # - 25% implementation score
                    # - 30% fetch pattern bonus (increased for API queries)
                    # - Up to 45% path match bonus
                    composite_score = (
                        embedding_score * 0.35 +
                        impl_score * 0.25 +
                        fetch_bonus +
                        path_bonus
                    ) * marker_penalty
                else:
                    composite_score = hit.score

                scored_results.append({
                    "content": content,
                    "file_path": hit.payload.get("file_path", ""),
                    "relative_path": hit.payload.get("relative_path", ""),
                    "start_line": hit.payload.get("start_line", 0),
                    "end_line": hit.payload.get("end_line", 0),
                    "chunk_type": hit.payload.get("chunk_type", ""),
                    "node_name": hit.payload.get("node_name"),
                    "score": composite_score,
                    "embedding_score": hit.score,
                    "impl_score": impl_score,
                    "has_fetch": has_fetch,
                    "is_marker": is_marker,
                    "path_bonus": path_bonus,
                })

            # Sort by composite score and return top_k
            if rerank:
                scored_results.sort(key=lambda x: x["score"], reverse=True)

            return scored_results[:top_k]

        except Exception as e:
            self.logger.warning("search_failed", query=query[:50], error=str(e))
            return []

    async def delete_collection(self) -> bool:
        """Delete the project's Qdrant collection."""
        if not await self._init_qdrant():
            return False

        try:
            self._qdrant_client.delete_collection(self._get_collection_name())
            self.logger.info("collection_deleted", name=self._get_collection_name())
            return True
        except Exception as e:
            self.logger.error("collection_delete_failed", error=str(e))
            return False


async def main():
    """CLI entry point for indexing a project."""
    import argparse

    parser = argparse.ArgumentParser(description="Index a project for semantic search")
    parser.add_argument("project_dir", help="Project directory to index")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant URL")
    parser.add_argument("--search", type=str, help="Search query (optional)")

    args = parser.parse_args()

    indexer = ProjectIndexer(
        project_dir=args.project_dir,
        qdrant_url=args.qdrant_url,
    )

    if args.search:
        results = await indexer.search(args.search)
        print(f"\nSearch results for: {args.search}")
        for i, r in enumerate(results, 1):
            print(f"\n--- Result {i} (score: {r['score']:.3f}) ---")
            print(f"File: {r['relative_path']}:{r['start_line']}-{r['end_line']}")
            print(r['content'][:200] + "..." if len(r['content']) > 200 else r['content'])
    else:
        stats = await indexer.index_project()
        print(f"\nIndexing complete:")
        print(f"  Files indexed: {stats['files_indexed']}")
        print(f"  Chunks indexed: {stats['chunks_indexed']}")
        print(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    asyncio.run(main())

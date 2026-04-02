"""
LLM-powered intelligent code search service.

Provides:
- Query classification (code-specific, conceptual, mixed)
- LLM-steered MCMP simulation for conceptual queries
- Hybrid search combining Qdrant + MCMP
- Relevance judging with explanations
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import asyncio
import json
import os
import re
import structlog

logger = structlog.get_logger(__name__)

# Prompt limits for OpenRouter LLM calls
MAX_PROMPT_TOKENS = 4000  # Conservative limit for reliability
MAX_SNIPPETS_FOR_JUDGE = 8  # Reduced from 15
MAX_SNIPPET_CHARS = 300  # Reduced from 500
MAX_FINDINGS_CHARS = 80  # For steering guidance


class QueryType(Enum):
    """Type of search query."""
    CODE_SPECIFIC = "code"      # Direct code search (function names, errors)
    CONCEPTUAL = "conceptual"   # High-level understanding (how does X work)
    MIXED = "mixed"             # Both aspects needed


@dataclass
class QueryClassification:
    """Result of LLM query classification."""
    query_type: QueryType
    confidence: float
    suggested_hops: List[str]
    reasoning: str


@dataclass
class SearchResult:
    """A single search result with metadata."""
    content: str
    file_path: str
    start_line: int
    end_line: int
    score: float
    source: str  # "qdrant" | "mcmp" | "hybrid"
    explanation: Optional[str] = None
    relationships: Optional[List[str]] = None


@dataclass
class SteeringGuidance:
    """LLM guidance for MCMP agents."""
    boost_areas: List[str] = field(default_factory=list)
    avoid_areas: List[str] = field(default_factory=list)
    new_keywords: List[str] = field(default_factory=list)


class LLMSearchService:
    """
    LLM-powered intelligent code search.

    Uses LLMs to:
    1. Classify queries as code-specific, conceptual, or mixed
    2. Steer MCMP agents during simulation
    3. Judge and rank search results
    4. Discover code relationships
    """

    def __init__(
        self,
        working_dir: str,
        qdrant_url: str = "http://localhost:6333",
        haiku_model: str = None,
        sonnet_model: str = None,
    ):
        from src.llm_config import get_model
        self.working_dir = working_dir
        self.qdrant_url = qdrant_url
        self.haiku_model = haiku_model or get_model("judge")
        self.sonnet_model = sonnet_model or get_model("mcp_standard")

        self._qdrant_client = None
        self._embedder = None
        self._llm_client = None
        self._collection_name = None

        self.logger = logger.bind(service="llm_search")

    async def _init_llm(self) -> None:
        """Initialize LLM client — respects LLM_BACKEND env var."""
        if self._llm_client is not None:
            return

        import httpx
        backend = os.environ.get('LLM_BACKEND', 'openai')

        if backend == 'openai':
            api_key = os.environ.get('OPENAI_API_KEY', '')
            base_url = "https://api.openai.com/v1"
        else:
            api_key = os.environ.get('OPENROUTER_API_KEY', '')
            base_url = "https://openrouter.ai/api/v1"

        if not api_key:
            self.logger.warning("no_llm_key", msg="%s API key not set, LLM features disabled" % backend)
            return

        self._llm_client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        self.logger.info("llm_client_initialized", backend=backend)

    async def _init_qdrant(self) -> None:
        """Initialize Qdrant client."""
        if self._qdrant_client is not None:
            return

        try:
            from qdrant_client import QdrantClient
            self._qdrant_client = QdrantClient(url=self.qdrant_url)
            self.logger.info("qdrant_client_initialized", url=self.qdrant_url)
        except Exception as e:
            self.logger.warning("qdrant_init_failed", error=str(e))

    async def _init_embedder(self) -> None:
        """Initialize embedding client — respects LLM_BACKEND env var."""
        if self._embedder is not None:
            return

        backend = os.environ.get('LLM_BACKEND', 'openai')

        # Try OpenAI embeddings first (if backend=openai or key available)
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        if openai_key:
            try:
                from src.agents.fungus_context_agent import OpenAIEmbeddingClient
                self._embedder = OpenAIEmbeddingClient(
                    api_key=openai_key,
                    model="text-embedding-3-small",
                    base_url="https://api.openai.com/v1"
                )
                self.logger.info("embedder_initialized", model="openai/text-embedding-3-small")
                return
            except Exception as e:
                self.logger.debug(f"openai_embedder_failed: {e}")

        # Fallback to OpenRouter
        or_key = os.environ.get('OPENROUTER_API_KEY', '')
        if or_key:
            try:
                from src.agents.fungus_context_agent import OpenAIEmbeddingClient
                self._embedder = OpenAIEmbeddingClient(
                    api_key=or_key,
                    model="openai/text-embedding-3-small",
                    base_url="https://openrouter.ai/api"
                )
                self.logger.info("embedder_initialized", model="openrouter/text-embedding-3-small")
                return
            except Exception as e:
                self.logger.debug(f"openrouter_embedder_failed: {e}")

        # Fallback to simple embedder
        try:
            from src.agents.fungus_context_agent import SimpleTFIDFEmbedder
            self._embedder = SimpleTFIDFEmbedder()
            self.logger.info("embedder_initialized", model="simple-tfidf")
        except Exception as e:
            self.logger.warning("embedder_init_failed", error=str(e))

    async def _call_llm(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 500,
    ) -> Optional[str]:
        """Call LLM via OpenRouter."""
        await self._init_llm()

        if not self._llm_client:
            return None

        try:
            response = await self._llm_client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                }
            )

            if response.status_code != 200:
                error_body = ""
                try:
                    error_body = response.text[:500] if response.text else ""
                except Exception:
                    pass
                self.logger.warning(
                    "llm_call_failed",
                    status=response.status_code,
                    error=error_body,
                    prompt_length=len(prompt),
                    model=model,
                )
                return None

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            self.logger.warning("llm_call_error", error=str(e))
            return None

    async def classify_query(self, query: str) -> QueryClassification:
        """
        Use LLM to classify query type and suggest search strategy.

        Args:
            query: The search query to classify

        Returns:
            QueryClassification with type, confidence, and suggested hops
        """
        prompt = f"""Classify this code search query and suggest search strategy.

Query: "{query}"

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "query_type": "code" or "conceptual" or "mixed",
  "confidence": 0.0 to 1.0,
  "suggested_hops": ["keyword1", "keyword2"],
  "reasoning": "brief explanation"
}}

Rules:
- "code": Looking for specific code (function names, error messages, imports, specific syntax)
- "conceptual": Understanding how something works, architecture, relationships, flow
- "mixed": Both specific code AND understanding needed
- suggested_hops: 3-5 key terms to search for related code"""

        response = await self._call_llm(prompt, self.haiku_model, max_tokens=200)

        if not response:
            # Fallback: simple heuristics
            return self._classify_query_heuristic(query)

        try:
            # Parse JSON response
            data = json.loads(response.strip())
            query_type = QueryType(data.get("query_type", "mixed"))

            return QueryClassification(
                query_type=query_type,
                confidence=float(data.get("confidence", 0.5)),
                suggested_hops=data.get("suggested_hops", []),
                reasoning=data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.debug("classification_parse_failed", error=str(e))
            return self._classify_query_heuristic(query)

    def _classify_query_heuristic(self, query: str) -> QueryClassification:
        """Fallback heuristic-based query classification."""
        query_lower = query.lower()

        # Code-specific patterns
        code_patterns = [
            r"function\s+\w+",
            r"class\s+\w+",
            r"\.\w+\(",
            r"import\s+",
            r"error|bug|fix|undefined|null",
            r"TS\d{4}",  # TypeScript errors
            r"line\s+\d+",
        ]

        # Conceptual patterns
        conceptual_patterns = [
            r"how\s+does",
            r"how\s+to",
            r"explain",
            r"describe",
            r"architecture",
            r"relationship",
            r"what\s+is",
            r"where\s+is",
            r"flow",
            r"process",
        ]

        code_score = sum(1 for p in code_patterns if re.search(p, query_lower))
        concept_score = sum(1 for p in conceptual_patterns if re.search(p, query_lower))

        # Extract keywords for hops
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', query)
        hops = [w for w in words if len(w) > 3][:5]

        if code_score > concept_score:
            return QueryClassification(
                query_type=QueryType.CODE_SPECIFIC,
                confidence=0.7,
                suggested_hops=hops,
                reasoning="Heuristic: code patterns detected",
            )
        elif concept_score > code_score:
            return QueryClassification(
                query_type=QueryType.CONCEPTUAL,
                confidence=0.7,
                suggested_hops=hops,
                reasoning="Heuristic: conceptual patterns detected",
            )
        else:
            return QueryClassification(
                query_type=QueryType.MIXED,
                confidence=0.5,
                suggested_hops=hops,
                reasoning="Heuristic: mixed or unclear patterns",
            )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        force_mode: Optional[QueryType] = None,
    ) -> List[SearchResult]:
        """
        Intelligent search with automatic strategy selection.

        Args:
            query: Search query
            top_k: Number of results to return
            force_mode: Force specific search mode (for testing)

        Returns:
            List of SearchResult with content, metadata, and explanations
        """
        # 1. Classify query
        if force_mode:
            classification = QueryClassification(
                query_type=force_mode,
                confidence=1.0,
                suggested_hops=[],
                reasoning="Forced mode",
            )
        else:
            classification = await self.classify_query(query)

        self.logger.info(
            "query_classified",
            query=query[:50],
            type=classification.query_type.value,
            confidence=classification.confidence,
        )

        # 2. Route to appropriate search
        if classification.query_type == QueryType.CODE_SPECIFIC:
            results = await self._qdrant_search(query, top_k)

        elif classification.query_type == QueryType.CONCEPTUAL:
            results = await self._mcmp_search(
                query,
                top_k,
                initial_hops=classification.suggested_hops,
            )

        else:  # MIXED
            results = await self._hybrid_search(
                query,
                top_k,
                initial_hops=classification.suggested_hops,
            )

        return results

    async def _qdrant_search(
        self,
        query: str,
        top_k: int,
    ) -> List[SearchResult]:
        """Fast vector search via Qdrant."""
        await self._init_qdrant()
        await self._init_embedder()

        if not self._qdrant_client or not self._embedder:
            return []

        try:
            # Get collection name (matches FungusContextAgent naming)
            if not self._collection_name:
                from pathlib import Path
                project_name = Path(self.working_dir).name
                # Sanitize: replace hyphens with underscores for Qdrant compatibility
                self._collection_name = f"project_{project_name.replace('-', '_')}"

            # Embed query
            query_embedding = self._embedder.encode([query])[0]

            # Search
            results = self._qdrant_client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding,
                limit=top_k,
            )

            return [
                SearchResult(
                    content=hit.payload.get("content", ""),
                    file_path=hit.payload.get("file_path", ""),
                    start_line=hit.payload.get("start_line", 0),
                    end_line=hit.payload.get("end_line", 0),
                    score=hit.score,
                    source="qdrant",
                )
                for hit in results
            ]

        except Exception as e:
            self.logger.warning("qdrant_search_failed", error=str(e))
            return []

    async def _mcmp_search(
        self,
        query: str,
        top_k: int,
        initial_hops: List[str],
    ) -> List[SearchResult]:
        """LLM-steered MCMP swarm search for conceptual queries."""
        # First, do basic Qdrant search to seed MCMP
        initial_results = await self._qdrant_search(query, top_k * 2)

        if not initial_results:
            return []

        # Get steering guidance from LLM
        steering = await self._get_steering_guidance(
            query,
            initial_results,
            initial_hops,
        )

        # Expand search with steering keywords
        expanded_query = f"{query} {' '.join(steering.boost_areas)} {' '.join(steering.new_keywords)}"
        expanded_results = await self._qdrant_search(expanded_query, top_k * 2)

        # Combine and deduplicate
        all_results = initial_results + expanded_results
        seen_paths = set()
        unique_results = []
        for r in all_results:
            key = f"{r.file_path}:{r.start_line}"
            if key not in seen_paths:
                seen_paths.add(key)
                unique_results.append(r)

        # Use LLM to rank and explain
        return await self._judge_results(query, unique_results, top_k)

    async def _get_steering_guidance(
        self,
        query: str,
        current_results: List[SearchResult],
        initial_hops: List[str],
    ) -> SteeringGuidance:
        """Get LLM guidance for expanding search."""
        # Format current findings (limited to prevent "prompt too long" errors)
        findings = "\n".join([
            f"- {r.file_path}: {r.content[:MAX_FINDINGS_CHARS]}..."
            for r in current_results[:5]
        ])

        prompt = f"""You are guiding a code search for: "{query}"

Current findings:
{findings}

Initial keywords: {initial_hops}

Suggest how to expand the search. Respond ONLY with valid JSON:
{{
  "boost_areas": ["area1", "area2"],
  "avoid_areas": ["area3"],
  "new_keywords": ["kw1", "kw2"]
}}

- boost_areas: Code areas to explore more (related modules, patterns)
- avoid_areas: Areas to deprioritize (already covered, irrelevant)
- new_keywords: New search terms to try"""

        response = await self._call_llm(prompt, self.haiku_model, max_tokens=150)

        if not response:
            return SteeringGuidance(new_keywords=initial_hops)

        try:
            data = json.loads(response.strip())
            return SteeringGuidance(
                boost_areas=data.get("boost_areas", []),
                avoid_areas=data.get("avoid_areas", []),
                new_keywords=data.get("new_keywords", []),
            )
        except json.JSONDecodeError:
            return SteeringGuidance(new_keywords=initial_hops)

    async def _judge_results(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int,
    ) -> List[SearchResult]:
        """Use LLM to rank results and add explanations."""
        if not results:
            return []

        # Format snippets for LLM (limited to prevent "prompt too long" errors)
        snippets = "\n\n".join([
            f"[{i}] {r.file_path}:{r.start_line}-{r.end_line}\n```\n{r.content[:MAX_SNIPPET_CHARS]}\n```"
            for i, r in enumerate(results[:MAX_SNIPPETS_FOR_JUDGE])
        ])

        prompt = f"""Rank these code snippets by relevance to: "{query}"

{snippets}

Respond ONLY with valid JSON array (top {top_k}):
[
  {{"index": 0, "score": 0.95, "explanation": "why relevant", "relationships": ["file.ts"]}},
  ...
]

Rules:
- Only include indices that are actually relevant
- Explain WHY each result answers the query
- List related files/functions if you spot them"""

        response = await self._call_llm(prompt, self.sonnet_model, max_tokens=600)

        if not response:
            # Return top results without LLM ranking
            return results[:top_k]

        try:
            rankings = json.loads(response.strip())

            ranked_results = []
            for r in rankings[:top_k]:
                idx = r.get("index", 0)
                if idx < len(results):
                    result = results[idx]
                    result.score = r.get("score", result.score)
                    result.explanation = r.get("explanation")
                    result.relationships = r.get("relationships")
                    result.source = "mcmp"
                    ranked_results.append(result)

            return ranked_results

        except json.JSONDecodeError:
            return results[:top_k]

    async def _hybrid_search(
        self,
        query: str,
        top_k: int,
        initial_hops: List[str],
    ) -> List[SearchResult]:
        """Run Qdrant and MCMP in parallel, merge with LLM."""
        # Run both searches
        qdrant_task = asyncio.create_task(self._qdrant_search(query, top_k))
        mcmp_task = asyncio.create_task(
            self._mcmp_search(query, top_k, initial_hops)
        )

        qdrant_results, mcmp_results = await asyncio.gather(
            qdrant_task, mcmp_task
        )

        # Merge and deduplicate
        all_results = qdrant_results + mcmp_results
        seen_paths = set()
        unique_results = []
        for r in all_results:
            key = f"{r.file_path}:{r.start_line}"
            if key not in seen_paths:
                seen_paths.add(key)
                r.source = "hybrid"
                unique_results.append(r)

        # Sort by score
        unique_results.sort(key=lambda x: x.score, reverse=True)

        return unique_results[:top_k]

    async def close(self) -> None:
        """Clean up resources."""
        if self._llm_client:
            await self._llm_client.aclose()
            self._llm_client = None

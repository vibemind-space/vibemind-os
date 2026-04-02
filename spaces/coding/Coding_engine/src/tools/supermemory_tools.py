"""
Supermemory Tools - Integration with Supermemory for pattern learning.

This module provides tools to:
1. Search for similar code patterns from past projects
2. Store successful solutions for future reference
3. Build a learning feedback loop
"""
import json
import os
from dataclasses import dataclass, field
from typing import Optional, Any
import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class MemorySearchResult:
    """Result from searching memory."""
    found: bool
    results: list[dict] = field(default_factory=list)
    query: str = ""
    total_results: int = 0
    timing_ms: int = 0  # NEU: Timing für v4/search

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "query": self.query,
            "total_results": self.total_results,
            "results": self.results[:5],  # Limit to top 5
            "timing_ms": self.timing_ms,
        }


@dataclass
class MemoryStoreResult:
    """Result from storing in memory."""
    success: bool
    memory_id: Optional[str] = None
    status: str = ""  # NEU: "queued", "processing", etc.
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "memory_id": self.memory_id,
            "status": self.status,
            "error": self.error,
        }


class SupermemoryTools:
    """
    Tools for interacting with Supermemory.

    Supermemory provides:
    - Semantic search over stored patterns
    - Relationship tracking (updates, extends, derives)
    - Long-term memory for code patterns
    
    APIs:
    - v3/documents: Add/update documents
    - v3/search: Full-featured document search
    - v4/search: Speed-optimized memory search (recommended for parallel batches)
    """

    def __init__(self, api_key: Optional[str] = None, api_url: str = "https://api.supermemory.ai"):
        self.api_key = api_key or os.environ.get("SUPERMEMORY_API_KEY")
        self.api_url = api_url  # Base URL ohne /v3
        self.client = None
        self.logger = logger.bind(tool="supermemory")

        # Initialize HTTP client if API key available
        if self.api_key:
            self._init_client()

    def _init_client(self):
        """Initialize HTTP client for Supermemory REST API."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )
            self.logger.info("supermemory_client_initialized", api_url=self.api_url)
        except Exception as e:
            self.logger.error("supermemory_init_failed", error=str(e))
            self.client = None
    
    @property
    def enabled(self) -> bool:
        """Check if Supermemory is enabled and client is initialized."""
        return self.client is not None and self.api_key is not None

    # Search tool definition
    SEARCH_TOOL_DEFINITION = {
        "name": "search_memory",
        "description": """Search for similar code patterns, solutions, or errors in memory.
Use this to find past solutions to similar problems, or to check if a similar pattern exists.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for (e.g., 'authentication middleware fastapi')"
                },
                "category": {
                    "type": "string",
                    "enum": ["code_pattern", "error_fix", "architecture", "all"],
                    "description": "Category to search in"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return"
                }
            },
            "required": ["query"]
        }
    }

    # Store tool definition
    STORE_TOOL_DEFINITION = {
        "name": "store_memory",
        "description": """Store a successful code pattern or solution in memory for future reference.
Use this after successfully implementing a feature or fixing a bug.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The code or solution to store"
                },
                "description": {
                    "type": "string",
                    "description": "Description of what this code does"
                },
                "category": {
                    "type": "string",
                    "enum": ["code_pattern", "error_fix", "architecture"],
                    "description": "Category for this memory"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for easier retrieval"
                },
                "context": {
                    "type": "object",
                    "description": "Additional context (error message, requirement, etc.)"
                }
            },
            "required": ["content", "description", "category"]
        }
    }

    async def search(
        self,
        query: str,
        category: str = "all",
        limit: int = 5,
        container_tag: Optional[str] = None,
        rerank: bool = True,
    ) -> MemorySearchResult:
        """
        Search memory for similar patterns using Supermemory REST API.

        Args:
            query: What to search for
            category: Category filter
            limit: Max results
            container_tag: Optional container tag to filter by
            rerank: Enable reranking for better relevance (adds ~120ms, default: True)

        Returns:
            MemorySearchResult with matches
        """
        self.logger.info("searching_memory", query=query, category=category, rerank=rerank)

        if not self.client:
            # Return empty result if no client
            return MemorySearchResult(
                found=False,
                query=query,
                results=[],
                total_results=0,
            )

        try:
            # Build search query with category filter
            search_query = query
            if category != "all":
                search_query = f"{category}: {query}"

            # Execute search via REST API with reranking
            # POST /v3/search with JSON body
            payload = {
                "q": search_query,
                "rerank": rerank,  # Enable reranking for deeper semantic understanding
            }
            if container_tag:
                payload["containerTags"] = [container_tag]

            response = await self.client.post("/v3/search", json=payload)
            response.raise_for_status()

            data = response.json()

            # Process results
            results = []
            memories = data.get("data", {}).get("memories", []) if isinstance(data, dict) else []

            for item in memories[:limit]:
                results.append({
                    "id": item.get("id"),
                    "content": item.get("content", "")[:500],
                    "score": item.get("score", 0),
                    "metadata": item.get("metadata", {}),
                })

            # Enhanced logging for search results
            if len(results) > 0:
                self.logger.info(
                    "memory_search_results_found",
                    query=query[:100],
                    results_count=len(results),
                    top_scores=[r.get("score", 0) for r in results[:3]],
                    rerank_enabled=rerank,
                )
            else:
                self.logger.debug("memory_search_no_results", query=query[:100])

            return MemorySearchResult(
                found=len(results) > 0,
                query=query,
                results=results,
                total_results=len(results),
            )

        except httpx.HTTPStatusError as e:
            self.logger.error("search_http_error", status=e.response.status_code, error=str(e))
            return MemorySearchResult(
                found=False,
                query=query,
                results=[],
                total_results=0,
            )
        except Exception as e:
            self.logger.error("search_failed", error=str(e))
            return MemorySearchResult(
                found=False,
                query=query,
                results=[],
                total_results=0,
            )

    async def store(
        self,
        content: str,
        description: str,
        category: str,
        tags: Optional[list[str]] = None,
        context: Optional[dict] = None,
        container_tag: str = "coding_engine_v1",
        custom_id: Optional[str] = None,
    ) -> MemoryStoreResult:
        """
        Store a pattern in memory using Supermemory REST API.

        Args:
            content: The code/solution to store
            description: What it does
            category: Category (code_pattern, error_fix, architecture)
            tags: Tags for retrieval
            context: Additional context
            container_tag: Container tag (max 100 chars, alphanumeric)
            custom_id: Optional custom identifier (max 100 chars)

        Returns:
            MemoryStoreResult with status
        """
        self.logger.info(
            "storing_memory",
            category=category,
            tags=tags,
            content_length=len(content),
        )

        if not self.client:
            return MemoryStoreResult(
                success=False,
                error="Supermemory client not initialized",
            )

        try:
            # Build document content in markdown format
            document_content = f"""# {description}

**Category:** {category}
**Tags:** {', '.join(tags or [])}

## Code/Solution

```
{content}
```

## Context

{context or 'No additional context'}
"""

            # Prepare metadata for Supermemory (flatten complex values to JSON strings)
            flat_context = {}
            if context:
                for key, value in context.items():
                    if isinstance(value, (dict, list)):
                        # Convert complex values to JSON strings
                        flat_context[key] = json.dumps(value)
                    elif isinstance(value, (str, int, float, bool)) or value is None:
                        flat_context[key] = value
                    else:
                        # Convert other types to string
                        flat_context[key] = str(value)

            metadata = {
                "category": category,
                "tags": tags or [],
                "description": description,
                **flat_context,
            }

            # Store via REST API POST /documents
            payload = {
                "content": document_content,
                "containerTag": container_tag,
                "metadata": metadata
            }

            if custom_id:
                payload["customId"] = custom_id

            response = await self.client.post("/v3/documents", json=payload)
            response.raise_for_status()

            data = response.json()
            memory_id = data.get("id")

            # Enhanced logging for successful storage
            self.logger.info(
                "memory_stored_successfully",
                memory_id=memory_id,
                category=category,
                tags_count=len(tags or []),
                content_size=len(content),
                description=description[:100],
                container=container_tag,
            )

            return MemoryStoreResult(
                success=True,
                memory_id=memory_id,
            )

        except httpx.HTTPStatusError as e:
            self.logger.error("store_http_error", status=e.response.status_code, error=str(e))
            return MemoryStoreResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            self.logger.error("store_failed", error=str(e))
            return MemoryStoreResult(
                success=False,
                error=str(e),
            )

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()

    async def search_v4(
        self,
        query: str,
        container_tag: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.6,
        rerank: bool = True,
        filters: Optional[dict] = None,
        include_documents: bool = True,
        include_related: bool = False,
    ) -> MemorySearchResult:
        """
        Speed-optimized memory search using v4/search API.
        
        Ideal for parallel batch execution where speed is critical.

        Args:
            query: What to search for
            container_tag: Filter by container tag (project/batch scope)
            limit: Max results (default 10)
            threshold: Similarity threshold 0.0-1.0 (default 0.6)
            rerank: Enable reranking for better relevance (adds ~120ms)
            filters: Metadata filters with AND/OR logic:
                     {"AND": [{"key": "domain", "value": "frontend", "negate": False}]}
            include_documents: Include source documents in results
            include_related: Include related memories

        Returns:
            MemorySearchResult with matches and timing
        """
        self.logger.info("searching_memory_v4", query=query[:100], container_tag=container_tag)

        if not self.client:
            return MemorySearchResult(found=False, query=query)

        try:
            payload = {
                "q": query,
                "limit": limit,
                "threshold": threshold,
                "rerank": rerank,
            }
            
            if container_tag:
                payload["containerTag"] = container_tag
            
            if filters:
                payload["filters"] = filters
            
            if include_documents or include_related:
                payload["include"] = {}
                if include_documents:
                    payload["include"]["documents"] = True
                if include_related:
                    payload["include"]["relatedMemories"] = True

            response = await self.client.post("/v4/search", json=payload)
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", [])[:limit]:
                results.append({
                    "id": item.get("id"),
                    "memory": item.get("memory", "")[:1000],
                    "similarity": item.get("similarity", 0),
                    "title": item.get("title", ""),
                    "metadata": item.get("metadata", {}),
                })

            timing = data.get("timing", 0)

            self.logger.info(
                "memory_v4_search_complete",
                results_count=len(results),
                timing_ms=timing,
            )

            return MemorySearchResult(
                found=len(results) > 0,
                query=query,
                results=results,
                total_results=data.get("total", len(results)),
                timing_ms=timing,
            )

        except Exception as e:
            self.logger.error("search_v4_failed", error=str(e))
            return MemorySearchResult(found=False, query=query)

    async def add_document(
        self,
        content: str,
        container_tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        custom_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> MemoryStoreResult:
        """
        Add a document using v3/documents API with full containerTags support.
        
        Args:
            content: Text content, URL, or raw content to store
            container_tags: List of tags for grouping (e.g., ["project_42", "batch_1", "frontend"])
            metadata: Key-value metadata for filtering
            custom_id: Custom identifier for deduplication
            user_id: User ID for scoping

        Returns:
            MemoryStoreResult with memory_id and status
        """
        self.logger.info(
            "adding_document",
            content_length=len(content),
            container_tags=container_tags,
        )

        if not self.client:
            return MemoryStoreResult(success=False, error="Client not initialized")

        try:
            payload = {"content": content}
            
            if container_tags:
                payload["containerTags"] = container_tags
            
            if metadata:
                # Flatten complex metadata values to JSON strings
                flat_metadata = {}
                for key, value in metadata.items():
                    if isinstance(value, (dict, list)):
                        flat_metadata[key] = json.dumps(value)
                    elif isinstance(value, (str, int, float, bool)) or value is None:
                        flat_metadata[key] = value
                    else:
                        flat_metadata[key] = str(value)
                payload["metadata"] = flat_metadata
            
            if custom_id:
                payload["customId"] = custom_id
            
            if user_id:
                payload["userId"] = user_id

            response = await self.client.post("/v3/documents", json=payload)
            response.raise_for_status()
            data = response.json()

            self.logger.info(
                "document_added",
                memory_id=data.get("id"),
                status=data.get("status"),
            )

            return MemoryStoreResult(
                success=True,
                memory_id=data.get("id"),
                status=data.get("status", "queued"),
            )

        except Exception as e:
            self.logger.error("add_document_failed", error=str(e))
            return MemoryStoreResult(success=False, error=str(e))

    async def store_contracts(
        self,
        contracts_json: str,
        job_id: int,
        project_name: str,
    ) -> MemoryStoreResult:
        """
        Store InterfaceContracts in Supermemory for parallel batch context.
        
        Args:
            contracts_json: JSON-serialized InterfaceContracts
            job_id: Job ID for container tagging
            project_name: Project name for metadata

        Returns:
            MemoryStoreResult
        """
        return await self.add_document(
            content=contracts_json,
            container_tags=[
                f"project_{job_id}",
                "contracts",
                "architecture",
            ],
            metadata={
                "type": "interface_contracts",
                "project_name": project_name,
                "job_id": job_id,
            },
            custom_id=f"contracts_job_{job_id}",
        )

    async def store_generated_pattern(
        self,
        code: str,
        slice_id: str,
        domain: str,
        feature: Optional[str],
        job_id: int,
        success: bool,
    ) -> MemoryStoreResult:
        """
        Store a successfully generated code pattern for learning.
        
        Args:
            code: Generated code content
            slice_id: Slice identifier
            domain: Domain (frontend/backend/etc.)
            feature: Feature category (components/routes/etc.)
            job_id: Job ID
            success: Whether generation was successful

        Returns:
            MemoryStoreResult
        """
        container_tags = [
            f"project_{job_id}",
            f"domain_{domain}",
            "generated_pattern",
        ]
        if feature:
            container_tags.append(f"feature_{feature}")

        return await self.add_document(
            content=code,
            container_tags=container_tags,
            metadata={
                "type": "generated_code",
                "slice_id": slice_id,
                "domain": domain,
                "feature": feature,
                "success": success,
                "job_id": job_id,
            },
            custom_id=f"pattern_{slice_id}",
        )

    async def search_related_patterns(
        self,
        query: str,
        domain: str,
        job_id: Optional[int] = None,
        limit: int = 5,
    ) -> MemorySearchResult:
        """
        Search for related code patterns to use as context.
        
        Args:
            query: What to search for
            domain: Domain filter (frontend/backend/etc.)
            job_id: Optional job ID for project-specific search
            limit: Max results

        Returns:
            MemorySearchResult with relevant patterns
        """
        filters = {
            "AND": [
                {"key": "domain", "value": domain, "negate": False},
                {"key": "success", "value": "true", "negate": False},
            ]
        }
        
        container_tag = f"project_{job_id}" if job_id else None
        
        return await self.search_v4(
            query=query,
            container_tag=container_tag,
            limit=limit,
            threshold=0.6,
            rerank=True,
            filters=filters,
            include_related=True,
        )


# Convenience functions for direct tool use
async def supermemory_search(
    query: str,
    category: str = "all",
    limit: int = 5,
) -> MemorySearchResult:
    """
    Search Supermemory for similar patterns.

    Args:
        query: What to search for
        category: Category filter
        limit: Max results

    Returns:
        MemorySearchResult
    """
    tools = SupermemoryTools()
    return await tools.search(query, category, limit)


async def supermemory_store(
    content: str,
    description: str,
    category: str,
    tags: Optional[list[str]] = None,
    context: Optional[dict] = None,
) -> MemoryStoreResult:
    """
    Store a pattern in Supermemory.

    Args:
        content: Code/solution to store
        description: What it does
        category: Category
        tags: Tags
        context: Additional context

    Returns:
        MemoryStoreResult
    """
    tools = SupermemoryTools()
    return await tools.store(content, description, category, tags, context)


# Fallback local storage for when Supermemory is not available
class LocalMemoryFallback:
    """Simple local fallback when Supermemory is not configured."""

    def __init__(self, storage_path: str = ".memory"):
        self.storage_path = storage_path
        self.memories: list[dict] = []
        self._load()

    def _load(self):
        """Load memories from disk."""
        import json
        from pathlib import Path

        path = Path(self.storage_path) / "memories.json"
        if path.exists():
            with open(path, "r") as f:
                self.memories = json.load(f)

    def _save(self):
        """Save memories to disk."""
        import json
        from pathlib import Path

        path = Path(self.storage_path)
        path.mkdir(exist_ok=True)

        with open(path / "memories.json", "w") as f:
            json.dump(self.memories, f, indent=2)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Simple keyword search."""
        query_lower = query.lower()
        results = []

        for memory in self.memories:
            content = memory.get("content", "").lower()
            description = memory.get("description", "").lower()

            if query_lower in content or query_lower in description:
                results.append(memory)

            if len(results) >= limit:
                break

        return results

    def store(self, content: str, description: str, category: str, **kwargs) -> str:
        """Store a memory locally."""
        import uuid

        memory_id = str(uuid.uuid4())
        self.memories.append({
            "id": memory_id,
            "content": content,
            "description": description,
            "category": category,
            **kwargs,
        })
        self._save()
        return memory_id

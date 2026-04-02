"""
Architect Agent - Performs pre-analysis and generates interface contracts.

This agent is responsible for Phase 1 of the hybrid pipeline:
1. Analyzes all requirements
2. Identifies shared types and interfaces
3. Generates contracts for parallel agents
4. Defines file ownership
5. Supports parallel chunk analysis for large requirement sets
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import structlog
import uuid
from typing import TYPE_CHECKING

from src.engine.dag_parser import RequirementsData
from src.engine.contracts import InterfaceContracts
from src.engine.contract_generator import ContractGenerator
from src.engine.ai_contract_generator import HybridContractGenerator
from src.tools.claude_code_tool import ClaudeCodeTool
from src.tools.memory_tool import MemoryTool
from src.registry.document_registry import DocumentRegistry
from src.registry.documents import ImplementationPlan, PlannedFix, FileChange
from src.registry.document_types import DocumentStatus

if TYPE_CHECKING:
    from src.engine.tech_stack import TechStack
    from src.engine.slicer import TaskSlice, DomainChunk

logger = structlog.get_logger()


@dataclass
class ChunkAnalysisResult:
    """Result of analyzing a single chunk of requirements."""
    chunk_id: str
    contracts: InterfaceContracts
    domain: Optional[str] = None
    processing_time_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "domain": self.domain,
            "contracts_summary": {
                "types": len(self.contracts.types),
                "endpoints": len(self.contracts.endpoints),
                "components": len(self.contracts.components),
                "services": len(self.contracts.services),
            },
            "processing_time_ms": self.processing_time_ms,
            "success": self.success,
            "error": self.error,
        }


ARCHITECT_SYSTEM_PROMPT = """You are a Software Architect Agent.

Your role is to analyze requirements and design the system architecture BEFORE implementation begins.

You must:
1. Identify all shared data types and interfaces
2. Define API contracts between frontend and backend
3. Specify component interfaces for the UI
4. Assign file ownership to prevent conflicts
5. Identify dependencies between requirements

{tech_stack_context}

Output your analysis in a structured JSON format that other agents can use.

Be thorough but concise. Focus on interfaces, not implementation details."""


class ArchitectAgent:
    """
    Architect Agent for pre-analysis phase.

    This agent:
    1. Takes requirements as input
    2. Uses Claude to analyze and identify interfaces
    3. Generates InterfaceContracts for other agents
    4. Optionally searches memory for similar architectures
    5. Writes implementation plans to DocumentRegistry
    6. Supports parallel chunk analysis for scalability
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        use_memory: bool = True,
        memory_tool: Optional[Any] = None,
        max_parallel_chunks: int = 4,  # NEW: Limit parallel chunk analysis
        use_ai_contracts: bool = True,  # NEW: Use Claude-based contract generation
        context_provider: Optional[Any] = None,  # Phase 4: Rich context from SpecAdapter
    ):
        self.working_dir = working_dir
        self.use_memory = use_memory
        self.claude_tool = ClaudeCodeTool(working_dir=working_dir)
        # Accept memory_tool from caller, or initialize if use_memory=True
        self.memory_tool = memory_tool if memory_tool is not None else (MemoryTool(enabled=True) if use_memory else None)

        # Use HybridContractGenerator for AI-based contracts with heuristic fallback
        # Falls back to heuristic ContractGenerator if AI is disabled or fails
        # Pass working_dir to avoid CLAUDE.md context interference in Claude CLI
        self.contract_generator = (
            HybridContractGenerator(prefer_ai=use_ai_contracts, working_dir=working_dir)
            if use_ai_contracts
            else ContractGenerator(working_dir=working_dir)
        )
        self.use_ai_contracts = use_ai_contracts

        self.max_parallel_chunks = max_parallel_chunks
        self.logger = logger.bind(agent="architect")

        # Phase 4: Rich context provider from SpecAdapter
        self.context_provider = context_provider

        # Initialize DocumentRegistry for writing implementation plans
        self._doc_registry = DocumentRegistry(working_dir) if working_dir else None

        # Semaphore for limiting parallel chunk analysis
        self._chunk_semaphore = asyncio.Semaphore(max_parallel_chunks)

    async def analyze_chunk(
        self,
        chunk: "TaskSlice",
        req_data: RequirementsData,
        tech_stack: Optional[Any] = None,
    ) -> ChunkAnalysisResult:
        """
        Analyze a single chunk of requirements.
        
        This method analyzes one slice/chunk independently and can be called
        in parallel with other chunks using asyncio.gather.
        
        Args:
            chunk: TaskSlice containing requirement IDs to analyze
            req_data: Full requirements data (for context)
            tech_stack: Optional TechStack for technology context
            
        Returns:
            ChunkAnalysisResult with contracts for this chunk
        """
        start_time = asyncio.get_event_loop().time()
        
        async with self._chunk_semaphore:
            try:
                self.logger.info(
                    "analyzing_chunk",
                    chunk_id=chunk.slice_id,
                    requirements=len(chunk.requirements),
                    agent_type=chunk.agent_type,
                )
                
                # Filter requirements to only those in this chunk
                chunk_reqs = [
                    req for req in req_data.requirements
                    if (req.get("id") or req.get("req_id")) in chunk.requirements
                ]
                
                # Create a mini RequirementsData for this chunk
                chunk_req_data = RequirementsData(
                    success=True,
                    workflow_status="ready",
                    requirements=chunk_reqs,
                    nodes=[n for n in req_data.nodes if n.id in chunk.requirements],
                    edges=[],
                    summary={},
                )
                chunk_req_data.dag = req_data.dag  # Keep reference to full DAG

                # Generate contracts for this chunk
                # HybridContractGenerator is async, ContractGenerator is sync
                if hasattr(self.contract_generator, 'generate') and asyncio.iscoroutinefunction(self.contract_generator.generate):
                    contracts = await self.contract_generator.generate(
                        chunk_req_data,
                        project_name=f"Chunk-{chunk.slice_id}",
                        domain_hint=chunk.agent_type,
                    )
                else:
                    contracts = self.contract_generator.generate(
                        chunk_req_data,
                        project_name=f"Chunk-{chunk.slice_id}",
                    )

                # If complex chunk, enhance with Claude
                if self._needs_chunk_enhancement(contracts, chunk_reqs):
                    contracts = await self._enhance_chunk_with_claude(
                        contracts,
                        chunk_reqs,
                        chunk,
                        tech_stack,
                    )
                
                processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
                
                self.logger.info(
                    "chunk_analysis_complete",
                    chunk_id=chunk.slice_id,
                    types=len(contracts.types),
                    endpoints=len(contracts.endpoints),
                    components=len(contracts.components),
                    time_ms=processing_time,
                )
                
                # Get domain from chunk details if available
                domain = None
                if chunk.requirement_details and len(chunk.requirement_details) > 0:
                    domain = chunk.requirement_details[0].get("domain")
                
                return ChunkAnalysisResult(
                    chunk_id=chunk.slice_id,
                    contracts=contracts,
                    domain=domain or chunk.agent_type,
                    processing_time_ms=processing_time,
                    success=True,
                )
                
            except Exception as e:
                self.logger.error(
                    "chunk_analysis_failed",
                    chunk_id=chunk.slice_id,
                    error=str(e),
                )
                return ChunkAnalysisResult(
                    chunk_id=chunk.slice_id,
                    contracts=InterfaceContracts(project_name=f"Chunk-{chunk.slice_id}"),
                    success=False,
                    error=str(e),
                )

    async def analyze_parallel(
        self,
        chunks: list["TaskSlice"],
        req_data: RequirementsData,
        project_name: str = "Generated Project",
        tech_stack: Optional[Any] = None,
    ) -> tuple[InterfaceContracts, list[ChunkAnalysisResult]]:
        """
        Analyze multiple chunks in parallel and merge results.
        
        This method:
        1. Dispatches chunk analysis tasks in parallel (limited by semaphore)
        2. Collects all results
        3. Merges contracts from all chunks
        4. Writes combined implementation plan
        
        Args:
            chunks: List of TaskSlices to analyze
            req_data: Full requirements data
            project_name: Name for the project
            tech_stack: Optional TechStack for technology context
            
        Returns:
            Tuple of (merged InterfaceContracts, list of ChunkAnalysisResults)
        """
        self.logger.info(
            "starting_parallel_analysis",
            chunks=len(chunks),
            max_parallel=self.max_parallel_chunks,
        )
        
        start_time = asyncio.get_event_loop().time()
        
        # Store tech_stack for chunk enhancement
        self.tech_stack = tech_stack
        
        # Dispatch all chunk analyses in parallel
        tasks = [
            self.analyze_chunk(chunk, req_data, tech_stack)
            for chunk in chunks
        ]
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        chunk_results: list[ChunkAnalysisResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(
                    "chunk_task_exception",
                    chunk_index=i,
                    error=str(result),
                )
                chunk_results.append(ChunkAnalysisResult(
                    chunk_id=f"chunk-{i}",
                    contracts=InterfaceContracts(project_name=f"Chunk-{i}"),
                    success=False,
                    error=str(result),
                ))
            else:
                chunk_results.append(result)
        
        # Merge all contracts
        merged_contracts = self._merge_chunk_contracts(chunk_results, project_name)
        
        total_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        successful = sum(1 for r in chunk_results if r.success)
        
        self.logger.info(
            "parallel_analysis_complete",
            chunks_total=len(chunks),
            chunks_successful=successful,
            total_time_ms=total_time,
            types=len(merged_contracts.types),
            endpoints=len(merged_contracts.endpoints),
            components=len(merged_contracts.components),
        )
        
        # Write combined implementation plan
        await self._write_implementation_plan(merged_contracts, req_data, project_name)
        
        return merged_contracts, chunk_results

    def _needs_chunk_enhancement(
        self,
        contracts: InterfaceContracts,
        chunk_reqs: list[dict],
    ) -> bool:
        """Determine if a chunk needs Claude enhancement."""
        # Simpler threshold for chunks - enhance if:
        # - No contracts found but has requirements
        # - Complex requirements in chunk
        
        if len(chunk_reqs) > 0 and len(contracts.types) == 0 and len(contracts.endpoints) == 0:
            return True
        
        # Check for complex requirements
        complex_count = sum(1 for req in chunk_reqs if len(req.get("title", "").split()) > 8)
        return complex_count > len(chunk_reqs) * 0.5

    async def _enhance_chunk_with_claude(
        self,
        contracts: InterfaceContracts,
        chunk_reqs: list[dict],
        chunk: "TaskSlice",
        tech_stack: Optional[Any] = None,
    ) -> InterfaceContracts:
        """Enhance a single chunk's contracts with Claude."""
        # Build focused prompt for this chunk
        req_summary = "\n".join([
            f"- [{req.get('id') or req.get('req_id', '')}] {req.get('title', '')}"
            for req in chunk_reqs[:15]
        ])
        
        tech_context = ""
        if tech_stack:
            tech_context = tech_stack.to_prompt_context()
        
        prompt = f"""Analyze these requirements for domain: {chunk.agent_type}

## Requirements
{req_summary}

## Current Analysis
Types: {len(contracts.types)}, Endpoints: {len(contracts.endpoints)}, Components: {len(contracts.components)}

{f"## Tech Stack{chr(10)}{tech_context}" if tech_context else ""}

Output ONLY valid JSON with additional types/endpoints/components needed:
{{"types": [...], "endpoints": [...], "components": [...], "services": [...]}}
"""
        print(prompt)
        
        result = await self.claude_tool.execute(
            prompt=prompt,
            agent_type=chunk.agent_type,
        )
        
        if result.success and result.output:
            enhanced = self._parse_claude_response(result.output)
            if enhanced:
                # Ensure endpoints exist for all types (fallback if Claude returns 0 endpoints)
                enhanced = self._ensure_endpoints_for_types(enhanced)
                return self._merge_contracts(contracts, enhanced)

        return contracts

    def _merge_chunk_contracts(
        self,
        chunk_results: list[ChunkAnalysisResult],
        project_name: str,
    ) -> InterfaceContracts:
        """Merge contracts from multiple chunk analyses."""
        merged = InterfaceContracts(project_name=project_name)
        
        seen_types = set()
        seen_endpoints = set()
        seen_components = set()
        seen_services = set()
        
        for result in chunk_results:
            if not result.success:
                continue
            
            contracts = result.contracts
            
            # Merge types
            for t in contracts.types:
                if t.name not in seen_types:
                    merged.add_type(t)
                    seen_types.add(t.name)
            
            # Merge endpoints
            for e in contracts.endpoints:
                key = (e.path, e.method)
                if key not in seen_endpoints:
                    merged.add_endpoint(e)
                    seen_endpoints.add(key)
            
            # Merge components
            for c in contracts.components:
                if c.name not in seen_components:
                    merged.add_component(c)
                    seen_components.add(c.name)
            
            # Merge services
            for s in contracts.services:
                if s.name not in seen_services:
                    merged.add_service(s)
                    seen_services.add(s.name)
            
            # Merge file ownership
            for file_path, owner in contracts.file_ownership.items():
                if file_path not in merged.file_ownership:
                    merged.file_ownership[file_path] = owner
        
        return merged

    async def _write_implementation_plan(
        self,
        contracts: InterfaceContracts,
        req_data: RequirementsData,
        project_name: str,
    ) -> None:
        """
        Write an implementation plan to the DocumentRegistry.
        
        Args:
            contracts: Generated interface contracts
            req_data: Requirements data
            project_name: Name of the project
        """
        if not self._doc_registry:
            self.logger.debug("no_doc_registry_skipping_plan_write")
            return
            
        try:
            # Convert contracts to planned fixes
            fixes_planned = []
            
            # Add types as planned items
            for i, type_def in enumerate(contracts.types):
                fixes_planned.append(PlannedFix(
                    id=f"type_{i+1}",
                    description=f"Define type: {type_def.name}",
                    approach=f"Create TypeScript/Python type with fields: {list(type_def.fields.keys())[:5]}",
                    estimated_complexity="low" if len(type_def.fields) < 5 else "medium",
                ))
            
            # Add endpoints as planned items
            for i, endpoint in enumerate(contracts.endpoints):
                fixes_planned.append(PlannedFix(
                    id=f"endpoint_{i+1}",
                    description=f"Implement endpoint: {endpoint.method} {endpoint.path}",
                    approach=endpoint.description or "Implement API endpoint",
                    estimated_complexity="medium",
                ))
            
            # Add components as planned items
            for i, component in enumerate(contracts.components):
                fixes_planned.append(PlannedFix(
                    id=f"component_{i+1}",
                    description=f"Create component: {component.name}",
                    approach=f"React/Vue component with props: {list(component.props.keys())[:5]}",
                    estimated_complexity="medium" if len(component.props) < 5 else "high",
                ))
            
            # Add services as planned items
            for i, service in enumerate(contracts.services):
                fixes_planned.append(PlannedFix(
                    id=f"service_{i+1}",
                    description=f"Implement service: {service.name}",
                    approach=f"Service with methods: {list(service.methods.keys())[:5]}",
                    estimated_complexity="high",
                ))
            
            # Build file manifest from ownership
            file_manifest = {}
            for file_path, owner in contracts.file_ownership.items():
                file_manifest[file_path] = FileChange(
                    action="created",
                    lines_added=0,  # Will be updated during generation
                    lines_removed=0,
                    summary=f"Owned by {owner}",
                )
            
            # Create implementation plan
            plan = ImplementationPlan(
                id=f"impl_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                timestamp=datetime.now(),
                source_agent="ArchitectAgent",
                status=DocumentStatus.PENDING,
                responding_to=None,  # Initial architecture plan
                fixes_planned=fixes_planned,
                file_manifest=file_manifest,
                test_focus_areas=[
                    f"Type validation for {len(contracts.types)} types",
                    f"API endpoint testing for {len(contracts.endpoints)} endpoints",
                    f"Component rendering for {len(contracts.components)} components",
                    f"Service integration for {len(contracts.services)} services",
                ],
                expected_outcomes=[
                    f"All {len(contracts.types)} types properly defined",
                    f"All {len(contracts.endpoints)} API endpoints functional",
                    f"All {len(contracts.components)} components render correctly",
                    f"All {len(contracts.services)} services operational",
                ],
                verification_steps=[
                    "Run TypeScript/type checks",
                    "Execute API integration tests",
                    "Run component snapshot tests",
                    "Verify service method signatures",
                ],
                summary=f"Architecture plan for {project_name}: {len(contracts.types)} types, {len(contracts.endpoints)} endpoints, {len(contracts.components)} components, {len(contracts.services)} services",
                total_files_changed=len(file_manifest),
            )
            
            # Write to registry
            await self._doc_registry.write_document(plan, priority=1)
            
            self.logger.info(
                "implementation_plan_written",
                plan_id=plan.id,
                fixes_planned=len(fixes_planned),
                files=len(file_manifest),
            )
            
        except Exception as e:
            self.logger.warning("failed_to_write_implementation_plan", error=str(e))

    async def analyze(
        self,
        req_data: RequirementsData,
        project_name: str = "Generated Project",
        tech_stack: Optional[Any] = None,
    ) -> InterfaceContracts:
        """
        Analyze requirements and generate interface contracts.

        This is a two-phase process:
        1. Heuristic analysis (fast, rule-based)
        2. Claude enhancement (if needed for complex requirements)

        Args:
            req_data: Parsed requirements data
            project_name: Name of the project
            tech_stack: Optional TechStack instance for framework/technology context

        Returns:
            InterfaceContracts for use by other agents
        """
        self.logger.info(
            "starting_analysis",
            requirements=len(req_data.requirements),
            project_name=project_name,
            has_tech_stack=tech_stack is not None,
        )

        # Store tech_stack for use in other methods
        self.tech_stack = tech_stack

        # Phase 1: Generate contracts (AI-based with HybridContractGenerator or heuristic)
        # HybridContractGenerator is async, ContractGenerator is sync
        if hasattr(self.contract_generator, 'generate') and asyncio.iscoroutinefunction(self.contract_generator.generate):
            contracts = await self.contract_generator.generate(req_data, project_name)
        else:
            contracts = self.contract_generator.generate(req_data, project_name)

        # Phase 1.5: Enrich with pre-defined API specs from rich context (Phase 4 Fix)
        contracts = self._enrich_from_context_provider(contracts)

        # Phase 2: Search memory for similar architectures
        learned_context = ""
        if self.use_memory and self.memory_tool:
            learned_context = await self._enhance_from_memory(contracts, req_data)

        # Phase 3: Claude enhancement for complex cases
        if self._needs_claude_enhancement(contracts, req_data):
            contracts = await self._enhance_with_claude(contracts, req_data, learned_context)

        self.logger.info(
            "analysis_complete",
            types=len(contracts.types),
            endpoints=len(contracts.endpoints),
            components=len(contracts.components),
            services=len(contracts.services),
        )

        # Store successful architecture pattern in memory
        if self.use_memory and self.memory_tool:
            await self._store_architecture_pattern(contracts, req_data, project_name)

        # Write implementation plan to DocumentRegistry
        await self._write_implementation_plan(contracts, req_data, project_name)

        return contracts

    def _enrich_from_context_provider(
        self,
        contracts: InterfaceContracts,
    ) -> InterfaceContracts:
        """
        Enrich contracts with pre-defined API endpoints from ContextProvider.

        Phase 4 Fix 3: Uses rich context (api_specs, db_schema) from billing spec
        to pre-populate contracts before Claude analysis.
        """
        if not self.context_provider:
            return contracts

        try:
            arch_context = self.context_provider.for_architect()

            # Add pre-defined API endpoints
            existing_endpoints = {(e.path, e.method) for e in contracts.endpoints}
            api_endpoints = arch_context.get("api_endpoints", [])

            if api_endpoints:
                from src.engine.contracts import APIEndpoint

                added_count = 0
                for ep in api_endpoints:
                    key = (ep.get("path"), ep.get("method"))
                    if key not in existing_endpoints:
                        contracts.add_endpoint(APIEndpoint(
                            path=ep.get("path", "/api/unknown"),
                            method=ep.get("method", "GET"),
                            description=ep.get("description", ""),
                        ))
                        existing_endpoints.add(key)
                        added_count += 1

                if added_count > 0:
                    self.logger.info(
                        "rich_context_endpoints_added",
                        endpoints_from_spec=len(api_endpoints),
                        endpoints_added=added_count,
                    )

            # Add DB schema info to contracts metadata (if supported)
            db_schema = arch_context.get("db_schema", {})
            if db_schema:
                self.logger.info(
                    "rich_context_db_schema_available",
                    tables=len(db_schema.get("tables", [])),
                )

        except Exception as e:
            self.logger.warning("rich_context_enrichment_failed", error=str(e))

        return contracts

    def _needs_claude_enhancement(
        self,
        contracts: InterfaceContracts,
        req_data: RequirementsData,
    ) -> bool:
        """Determine if Claude analysis is needed."""
        # Use Claude if:
        # - Few contracts were found heuristically
        # - Requirements are complex (many dependencies)
        # - Requirements have ambiguous descriptions

        if len(contracts.types) < 3 and len(req_data.requirements) > 20:
            return True

        if len(contracts.endpoints) == 0 and len(contracts.components) == 0:
            return True

        # Check for complex requirements (many words, technical terms)
        complex_count = 0
        for req in req_data.requirements:
            title = req.get("title", "")
            if len(title.split()) > 10:
                complex_count += 1

        if complex_count > len(req_data.requirements) * 0.3:
            return True

        return False

    async def _enhance_from_memory(
        self,
        contracts: InterfaceContracts,
        req_data: RequirementsData,
        max_tokens: int = 1500,
    ) -> str:
        """
        Search memory for similar architectures and return learnings as context.

        Uses intelligent scoring + temporal decay + reranking to select most relevant patterns.

        Args:
            contracts: Current interface contracts
            req_data: Requirements data
            max_tokens: Maximum token budget for learned context (default: 1500)

        Returns:
            String containing learned patterns to use as context, or empty string
        """
        if not self.memory_tool or not self.memory_tool.enabled:
            return ""

        try:
            # Build search query from requirements
            sample_requirements = [
                req.get("title", "")
                for req in req_data.requirements[:5]
            ]
            query = " ".join(sample_requirements)

            self.logger.debug("searching_memory", query=query[:100])

            # Search with increased limit for better scoring + enable reranking
            result = await self.memory_tool.search_architecture_patterns(
                query=query,
                project_type=req_data.project_type if hasattr(req_data, 'project_type') else None,
                limit=5,  # Increased from 3 to get more candidates for scoring
                rerank=True,  # Enable reranking for deeper semantic understanding
            )

            if result.found:
                self.logger.info(
                    "found_similar_architectures",
                    count=result.total_results,
                )
                # Use smart selection with scoring + temporal decay
                context = self.memory_tool.select_top_memories(
                    search_results=result.results,
                    max_tokens=max_tokens,
                )

                if context:
                    # Add header for Claude to understand this is learned context
                    formatted_context = f"## Learned Architecture Patterns\n\n{context}"

                    # Log metrics
                    estimated_tokens = int(len(formatted_context) * 0.25)
                    self.logger.info(
                        "applying_learned_patterns",
                        context_length=len(formatted_context),
                        estimated_tokens=estimated_tokens,
                        budget_tokens=max_tokens,
                    )
                    return formatted_context
        except Exception as e:
            self.logger.warning("memory_search_failed", error=str(e))

        return ""

    async def _store_architecture_pattern(
        self,
        contracts: InterfaceContracts,
        req_data: RequirementsData,
        project_name: str,
    ) -> None:
        """
        Store successful architecture pattern in memory for future reference.

        Args:
            contracts: Generated interface contracts
            req_data: Requirements data
            project_name: Name of the project
        """
        if not self.memory_tool or not self.memory_tool.enabled:
            return

        try:
            # Build content for storage
            pattern_summary = {
                "project_name": project_name,
                "project_type": req_data.project_type if hasattr(req_data, 'project_type') else "unknown",
                "requirement_count": len(req_data.requirements),
                "contracts": {
                    "types": len(contracts.types),
                    "endpoints": len(contracts.endpoints),
                    "components": len(contracts.components),
                    "services": len(contracts.services),
                },
                "sample_types": [t.name for t in contracts.types[:5]],
                "sample_endpoints": [f"{e.method} {e.path}" for e in contracts.endpoints[:5]],
                "sample_components": [c.name for c in contracts.components[:5]],
            }

            # Create descriptive content for semantic search
            content_parts = [
                f"Architecture for {project_name}",
                f"Project type: {pattern_summary['project_type']}",
                f"Requirements: {pattern_summary['requirement_count']}",
                f"\nContracts generated:",
                f"- {len(contracts.types)} types",
                f"- {len(contracts.endpoints)} API endpoints",
                f"- {len(contracts.components)} components",
                f"- {len(contracts.services)} services",
            ]

            if contracts.types:
                content_parts.append(f"\nKey types: {', '.join([t.name for t in contracts.types[:5]])}")
            if contracts.endpoints:
                content_parts.append(f"\nKey endpoints: {', '.join([f'{e.method} {e.path}' for e in contracts.endpoints[:5]])}")
            if contracts.components:
                content_parts.append(f"\nKey components: {', '.join([c.name for c in contracts.components[:5]])}")

            content = "\n".join(content_parts)

            # Store pattern
            await self.memory_tool.store_architecture_pattern(
                content=content,
                metadata=pattern_summary,
                project_type=pattern_summary['project_type'],
            )

            self.logger.info(
                "stored_architecture_pattern",
                project_name=project_name,
                types=len(contracts.types),
                endpoints=len(contracts.endpoints),
                components=len(contracts.components),
            )

        except Exception as e:
            self.logger.warning("memory_storage_failed", error=str(e))

    async def _enhance_with_claude(
        self,
        contracts: InterfaceContracts,
        req_data: RequirementsData,
        learned_context: str = "",
    ) -> InterfaceContracts:
        """Use Claude to enhance contract analysis."""
        self.logger.info(
            "enhancing_with_claude",
            has_learned_context=bool(learned_context),
            has_tech_stack=self.tech_stack is not None,
        )

        # Build prompt for Claude
        requirements_summary = self._build_requirements_summary(req_data)
        current_contracts = contracts.to_json()

        # Include learned patterns if available
        learned_section = f"\n\n{learned_context}\n" if learned_context else ""

        # Build tech stack context for system prompt
        tech_stack_context = ""
        tech_stack_section = ""
        if self.tech_stack:
            tech_stack_context = self.tech_stack.to_prompt_context()
            tech_stack_section = f"""
## Technology Stack

{tech_stack_context}

IMPORTANT: All type definitions, API endpoints, and components MUST be designed 
to work with the specified technology stack above. Use appropriate patterns and 
conventions for the selected frameworks.
"""

        # Format system prompt with tech stack context
        system_prompt = ARCHITECT_SYSTEM_PROMPT.format(
            tech_stack_context=tech_stack_context if tech_stack_context else ""
        )

        prompt = f"""{system_prompt}

## Requirements Summary

{requirements_summary}

## Current Analysis (from heuristics)

```json
{current_contracts}
```
{tech_stack_section}{learned_section}
## Your Task

Review the requirements and enhance the interface contracts:

1. Add any missing shared types that multiple components will need
2. Define API endpoints for backend requirements
3. Specify component props for frontend requirements
4. Add service interfaces for business logic
5. Verify file ownership makes sense

Output ONLY a valid JSON object with this structure:
{{
    "types": [
        {{"name": "TypeName", "fields": {{"field": "type"}}, "description": "..."}}
    ],
    "endpoints": [
        {{"path": "/api/...", "method": "GET|POST|PUT|DELETE", "description": "..."}}
    ],
    "components": [
        {{"name": "ComponentName", "props": {{"prop": "type"}}, "description": "..."}}
    ],
    "services": [
        {{"name": "ServiceName", "methods": {{"method": {{"params": {{}}, "return_type": "type"}}}}, "description": "..."}}
    ]
}}
"""

        result = await self.claude_tool.execute(
            prompt=prompt,
            agent_type="general",
        )

        if result.success and result.output:
            # Try to extract JSON from output
            enhanced = self._parse_claude_response(result.output)
            if enhanced:
                # Ensure endpoints exist for all types (fallback if Claude returns 0 endpoints)
                enhanced = self._ensure_endpoints_for_types(enhanced)
                return self._merge_contracts(contracts, enhanced)

        return contracts

    def _build_requirements_summary(self, req_data: RequirementsData) -> str:
        """Build a summary of requirements for Claude."""
        lines = []

        # Group by tag if available
        by_tag: dict[str, list] = {}
        for req in req_data.requirements:
            tags = req.get("tags", ["general"])
            tag = tags[0] if tags else "general"
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(req)

        for tag, reqs in by_tag.items():
            lines.append(f"\n### {tag.upper()}")
            for req in reqs[:10]:  # Limit to 10 per tag
                lines.append(f"- [{req.get('id', '')}] {req.get('title', '')}")

        return "\n".join(lines)

    def _parse_claude_response(self, output: str) -> Optional[dict]:
        """Parse Claude's JSON response."""
        # Try to find JSON in the output
        import re

        # Look for JSON block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the whole output as JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        # Try finding JSON object in output
        json_match = re.search(r"\{.*\}", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        self.logger.warning("failed_to_parse_claude_response")
        return None

    def _ensure_endpoints_for_types(self, enhanced: dict) -> dict:
        """
        Ensure every type has at least basic CRUD endpoints.

        This is a fallback mechanism: if Claude generated types but 0 endpoints,
        we auto-generate standard REST CRUD endpoints for each type.

        Args:
            enhanced: The parsed Claude response dict

        Returns:
            Enhanced dict with auto-generated endpoints if needed
        """
        endpoints = enhanced.get("endpoints", [])
        types = enhanced.get("types", [])

        # Only intervene if we have types but 0 endpoints
        if len(endpoints) == 0 and len(types) > 0:
            self.logger.warning(
                "no_endpoints_generated_adding_fallback",
                types_count=len(types),
            )

            if "endpoints" not in enhanced:
                enhanced["endpoints"] = []

            for type_def in types:
                # Handle both dict and object formats
                if isinstance(type_def, dict):
                    type_name = type_def.get("name", "Resource")
                else:
                    type_name = getattr(type_def, "name", "Resource")

                # Generate resource name (lowercase plural)
                resource = type_name.lower()
                if not resource.endswith("s"):
                    resource = resource + "s"

                # Add standard CRUD endpoints
                crud_endpoints = [
                    {
                        "path": f"/api/v1/{resource}",
                        "method": "GET",
                        "description": f"List all {resource}",
                        "response_type": f"{type_name}[]",
                    },
                    {
                        "path": f"/api/v1/{resource}/{{id}}",
                        "method": "GET",
                        "description": f"Get {type_name} by ID",
                        "response_type": type_name,
                    },
                    {
                        "path": f"/api/v1/{resource}",
                        "method": "POST",
                        "description": f"Create new {type_name}",
                        "request_type": f"Create{type_name}Request",
                        "response_type": type_name,
                    },
                    {
                        "path": f"/api/v1/{resource}/{{id}}",
                        "method": "PUT",
                        "description": f"Update {type_name}",
                        "request_type": f"Update{type_name}Request",
                        "response_type": type_name,
                    },
                    {
                        "path": f"/api/v1/{resource}/{{id}}",
                        "method": "DELETE",
                        "description": f"Delete {type_name}",
                        "response_type": "void",
                    },
                ]

                enhanced["endpoints"].extend(crud_endpoints)

            self.logger.info(
                "fallback_endpoints_generated",
                endpoints_added=len(enhanced["endpoints"]),
            )

        return enhanced

    def _merge_contracts(
        self,
        base: InterfaceContracts,
        enhanced: dict,
    ) -> InterfaceContracts:
        """Merge enhanced contracts with base contracts."""
        from src.engine.contracts import (
            TypeDefinition,
            APIEndpoint,
            ComponentContract,
            ServiceContract,
        )

        # Add new types
        existing_type_names = {t.name for t in base.types}
        for type_data in enhanced.get("types", []):
            # Handle string format: convert to dict
            if isinstance(type_data, str):
                type_data = {"name": type_data, "fields": {}, "description": ""}
            if not isinstance(type_data, dict):
                continue
            if type_data.get("name") not in existing_type_names:
                base.add_type(TypeDefinition(
                    name=type_data.get("name", "Unknown"),
                    fields=type_data.get("fields", {}),
                    description=type_data.get("description", ""),
                ))

        # Add new endpoints
        existing_endpoints = {(e.path, e.method) for e in base.endpoints}
        for ep_data in enhanced.get("endpoints", []):
            # Handle string format: convert to dict
            if isinstance(ep_data, str):
                ep_data = {"path": ep_data, "method": "GET", "description": ""}
            if not isinstance(ep_data, dict):
                continue
            key = (ep_data.get("path"), ep_data.get("method"))
            if key not in existing_endpoints:
                base.add_endpoint(APIEndpoint(
                    path=ep_data.get("path", "/api/unknown"),
                    method=ep_data.get("method", "GET"),
                    description=ep_data.get("description", ""),
                ))

        # Add new components
        existing_components = {c.name for c in base.components}
        for comp_data in enhanced.get("components", []):
            # Handle string format: convert to dict
            if isinstance(comp_data, str):
                comp_data = {"name": comp_data, "props": {}, "description": ""}
            if not isinstance(comp_data, dict):
                continue
            if comp_data.get("name") not in existing_components:
                base.add_component(ComponentContract(
                    name=comp_data.get("name", "Unknown"),
                    props=comp_data.get("props", {}),
                    description=comp_data.get("description", ""),
                ))

        # Add new services
        existing_services = {s.name for s in base.services}
        for svc_data in enhanced.get("services", []):
            # Handle string format: convert to dict
            if isinstance(svc_data, str):
                svc_data = {"name": svc_data, "methods": {}, "description": ""}
            if not isinstance(svc_data, dict):
                continue
            if svc_data.get("name") not in existing_services:
                base.add_service(ServiceContract(
                    name=svc_data.get("name", "Unknown"),
                    methods=svc_data.get("methods", {}),
                    description=svc_data.get("description", ""),
                ))

        return base


async def analyze_requirements(
    req_data: RequirementsData,
    project_name: str = "Generated Project",
    working_dir: Optional[str] = None,
) -> InterfaceContracts:
    """
    Convenience function to analyze requirements.

    Args:
        req_data: Parsed requirements
        project_name: Project name
        working_dir: Working directory

    Returns:
        InterfaceContracts
    """
    agent = ArchitectAgent(working_dir=working_dir)
    return await agent.analyze(req_data, project_name)


async def analyze_requirements_parallel(
    chunks: list["TaskSlice"],
    req_data: RequirementsData,
    project_name: str = "Generated Project",
    working_dir: Optional[str] = None,
    tech_stack: Optional[Any] = None,
) -> tuple[InterfaceContracts, list[ChunkAnalysisResult]]:
    """
    Convenience function to analyze requirements in parallel chunks.
    
    Args:
        chunks: List of TaskSlices to analyze
        req_data: Full requirements data
        project_name: Project name
        working_dir: Working directory
        tech_stack: Optional TechStack
        
    Returns:
        Tuple of (merged contracts, chunk results)
    """
    agent = ArchitectAgent(working_dir=working_dir)
    return await agent.analyze_parallel(chunks, req_data, project_name, tech_stack)

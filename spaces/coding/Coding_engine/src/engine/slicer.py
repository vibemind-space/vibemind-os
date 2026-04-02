"""
Pre-Slicer - Groups requirements into parallelizable slices.

This module:
1. Analyzes the DAG structure
2. Groups requirements by depth level (parallel-safe)
3. Assigns agent types based on requirement content
4. Creates a slice manifest for parallel execution
5. Supports domain-based chunking for better parallelization
6. NEW: Feature-based grouping for larger, more coherent prompts
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from collections import defaultdict
from enum import Enum

import networkx as nx
import structlog

from src.engine.dag_parser import DAGParser, RequirementsData, DAGNode, NodeType
from src.utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

logger = structlog.get_logger()


class Domain(Enum):
    """Domain categories for requirement grouping."""
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    API = "api"
    AUTHENTICATION = "auth"
    INFRASTRUCTURE = "infra"
    TESTING = "testing"
    DOCUMENTATION = "docs"
    GENERAL = "general"


class FrontendFeature(Enum):
    """ARCH-38: Frontend feature categories for intelligent grouping."""
    COMPONENTS = "components"      # UI-Elemente (Button, Input, Card, etc.)
    PAGES = "pages"               # Page-Level Components (Dashboard, Settings)
    HOOKS = "hooks"               # React Hooks (useAuth, useFetch, etc.)
    SERVICES = "services"         # API Client, WebSocket, etc.
    STATE = "state"               # Redux/Zustand/Context
    STYLES = "styles"             # CSS/Tailwind/Themes
    UTILS = "utils"               # Helper Functions
    LAYOUT = "layout"             # Layout Components (Header, Sidebar, Footer)


class BackendFeature(Enum):
    """ARCH-39: Backend feature categories for intelligent grouping."""
    ROUTES = "routes"             # API Endpoints
    MODELS = "models"             # Pydantic/SQLAlchemy Models
    SERVICES = "services"         # Business Logic
    DATABASE = "database"         # Queries, Migrations
    AUTH = "auth"                 # Authentication/Authorization
    MIDDLEWARE = "middleware"     # Request Processing
    UTILS = "utils"               # Helper Functions
    CONFIG = "config"             # Configuration


@dataclass
class FeatureGroupConfig:
    """
    ARCH-43: Configuration for feature-based grouping with worker assignment.
    
    This allows much larger batch sizes for more coherent code generation.
    """
    # Frontend-Worker
    frontend_workers: int = 3
    max_components_per_worker: int = 20
    
    # Backend-Worker
    backend_workers: int = 2
    max_routes_per_worker: int = 15
    
    # DB-Worker
    db_workers: int = 1
    
    # ARCH-40: Größere Batch-Sizes (statt slice_size=3)
    frontend_batch_size: int = 50   # ALLE Components auf einmal!
    backend_batch_size: int = 30    # ALLE Routes auf einmal!
    db_batch_size: int = 20
    testing_batch_size: int = 25
    
    # Feature-spezifische Batch-Sizes
    frontend_feature_sizes: dict = field(default_factory=lambda: {
        FrontendFeature.COMPONENTS: 20,
        FrontendFeature.PAGES: 10,
        FrontendFeature.HOOKS: 15,
        FrontendFeature.SERVICES: 10,
        FrontendFeature.STATE: 8,
        FrontendFeature.STYLES: 5,
        FrontendFeature.UTILS: 15,
        FrontendFeature.LAYOUT: 8,
    })
    
    backend_feature_sizes: dict = field(default_factory=lambda: {
        BackendFeature.ROUTES: 15,
        BackendFeature.MODELS: 20,
        BackendFeature.SERVICES: 10,
        BackendFeature.DATABASE: 8,
        BackendFeature.AUTH: 5,
        BackendFeature.MIDDLEWARE: 5,
        BackendFeature.UTILS: 10,
        BackendFeature.CONFIG: 5,
    })


@dataclass
class DomainChunk:
    """A chunk of requirements belonging to a specific domain."""
    domain: Domain
    requirements: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    estimated_complexity: int = 0  # 1-10 scale
    suggested_agent: str = "general"


@dataclass
class FeatureChunk:
    """ARCH-37: A chunk of requirements for a specific feature within a domain."""
    domain: Domain
    feature: FrontendFeature | BackendFeature | None
    requirements: list[str] = field(default_factory=list)
    requirement_details: list[dict] = field(default_factory=list)
    estimated_complexity: int = 0
    suggested_agent: str = "general"
    worker_count: int = 1
    
    def to_dict(self) -> dict:
        return {
            "domain": self.domain.value,
            "feature": self.feature.value if self.feature else None,
            "requirement_count": len(self.requirements),
            "estimated_complexity": self.estimated_complexity,
            "suggested_agent": self.suggested_agent,
            "worker_count": self.worker_count,
        }


@dataclass
class TaskSlice:
    """A group of requirements that can be executed together."""
    slice_id: str
    depth: int
    agent_type: str
    requirements: list[str] = field(default_factory=list)
    requirement_details: list[dict] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    can_parallelize: bool = True
    estimated_tokens: int = 0
    priority: int = 0
    # NEW: Feature-based fields
    feature: Optional[str] = None
    worker_index: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SliceManifest:
    """Complete manifest of all slices for a job."""
    job_id: int
    total_requirements: int
    total_slices: int
    max_depth: int
    slices: list[TaskSlice] = field(default_factory=list)
    depth_groups: dict = field(default_factory=dict)
    agent_distribution: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "total_requirements": self.total_requirements,
            "total_slices": self.total_slices,
            "max_depth": self.max_depth,
            "slices": [s.to_dict() for s in self.slices],
            "depth_groups": self.depth_groups,
            "agent_distribution": self.agent_distribution,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class Slicer:
    """
    Pre-slices requirements into parallelizable groups.

    Slicing strategies:
    1. By depth - requirements at same DAG depth can run in parallel
    2. By type - group similar requirements for agent specialization
    3. Hybrid - combine depth and type for optimal parallelism
    4. Domain - group by functional domain (frontend, backend, etc.)
    5. TechStack - use TechStack configuration to determine domains
    6. feature_grouped - ARCH-37: Feature-based grouping for larger prompts
    7. documentation_epics - Epic-based slicing for Documentation format projects
    """

    # Epic dependency map for documentation_epics strategy
    # Epics at lower depths can run in parallel
    EPIC_DEPENDENCIES = {
        # Auth and Profiles are foundational - depth 0
        "EPIC-001": [],  # Identity, Authentication & Device Access
        "EPIC-002": [],  # User Profile, Contacts & Privacy Settings

        # Messaging and Groups depend on Auth/Profiles - depth 1
        "EPIC-003": ["EPIC-001", "EPIC-002"],  # Messaging, Media & Conversation
        "EPIC-004": ["EPIC-001", "EPIC-002"],  # Groups, Communities & Collaboration

        # Calling depends on Messaging - depth 2
        "EPIC-005": ["EPIC-003"],  # Calling & Real-Time Audio/Video

        # Status/Stories can run with Messaging - depth 1
        "EPIC-006": ["EPIC-001", "EPIC-002"],  # Status & Stories

        # Security requires Auth - depth 1
        "EPIC-007": ["EPIC-001"],  # Security & Privacy

        # Notifications require base features - depth 2
        "EPIC-008": ["EPIC-003", "EPIC-004"],  # Notifications & Presence

        # Business features require all core - depth 3
        "EPIC-009": ["EPIC-003", "EPIC-004", "EPIC-007"],  # Business Features

        # Data Management requires Auth - depth 1
        "EPIC-010": ["EPIC-001"],  # Data Management & Backup
    }

    # Epic to agent type mapping
    EPIC_AGENT_MAP = {
        "EPIC-001": "security",      # Auth
        "EPIC-002": "backend",       # Profiles
        "EPIC-003": "backend",       # Messaging
        "EPIC-004": "backend",       # Groups
        "EPIC-005": "backend",       # Calling
        "EPIC-006": "frontend",      # Status/Stories
        "EPIC-007": "security",      # Security
        "EPIC-008": "backend",       # Notifications
        "EPIC-009": "backend",       # Business
        "EPIC-010": "devops",        # Data/Backup
    }

    # ARCH-38: Frontend feature detection patterns
    FRONTEND_FEATURE_PATTERNS = {
        FrontendFeature.COMPONENTS: [
            r'\b(button|input|card|modal|dialog|toast|alert|badge|avatar)\b',
            r'\b(dropdown|select|checkbox|radio|toggle|switch|slider)\b',
            r'\b(table|list|grid|tree|accordion|tabs|carousel)\b',
            r'\b(tooltip|popover|menu|breadcrumb|pagination)\b',
        ],
        FrontendFeature.PAGES: [
            r'\b(page|view|screen|dashboard|home|landing)\b',
            r'\b(settings|profile|admin|login|register|signup)\b',
            r'\b(detail|list|create|edit|overview)\b',
        ],
        FrontendFeature.HOOKS: [
            r'\b(hook|use[A-Z]|useState|useEffect|useContext)\b',
            r'\b(useMemo|useCallback|useRef|useReducer)\b',
            r'\b(custom.?hook|react.?hook)\b',
        ],
        FrontendFeature.SERVICES: [
            r'\b(api.?client|http.?client|fetch|axios)\b',
            r'\b(websocket|socket|sse|realtime)\b',
            r'\b(service|client)\b',
        ],
        FrontendFeature.STATE: [
            r'\b(redux|zustand|mobx|recoil|jotai)\b',
            r'\b(store|state|context|provider)\b',
            r'\b(action|reducer|selector|slice)\b',
        ],
        FrontendFeature.STYLES: [
            r'\b(css|style|theme|color|font|spacing)\b',
            r'\b(tailwind|styled|emotion|sass|scss)\b',
            r'\b(dark.?mode|light.?mode|responsive)\b',
        ],
        FrontendFeature.LAYOUT: [
            r'\b(layout|header|footer|sidebar|navbar|nav)\b',
            r'\b(container|wrapper|grid|flex|section)\b',
        ],
        FrontendFeature.UTILS: [
            r'\b(helper|util|format|parse|validate)\b',
            r'\b(constant|config|env)\b',
        ],
    }
    
    # ARCH-39: Backend feature detection patterns
    BACKEND_FEATURE_PATTERNS = {
        BackendFeature.ROUTES: [
            r'\b(route|endpoint|api|rest|graphql)\b',
            r'\b(get|post|put|patch|delete|crud)\b',
            r'\b(controller|handler|view)\b',
        ],
        BackendFeature.MODELS: [
            r'\b(model|schema|entity|table)\b',
            r'\b(pydantic|sqlalchemy|orm|dataclass)\b',
            r'\b(field|column|relation|foreign.?key)\b',
        ],
        BackendFeature.SERVICES: [
            r'\b(service|business.?logic|domain)\b',
            r'\b(use.?case|command|query)\b',
        ],
        BackendFeature.DATABASE: [
            r'\b(database|db|sql|query|migration)\b',
            r'\b(repository|dao|crud)\b',
            r'\b(postgres|mysql|mongodb|redis|sqlite)\b',
        ],
        BackendFeature.AUTH: [
            r'\b(auth|login|logout|session|token|jwt|oauth)\b',
            r'\b(password|user|permission|role|access|security)\b',
        ],
        BackendFeature.MIDDLEWARE: [
            r'\b(middleware|interceptor|filter|guard)\b',
            r'\b(cors|rate.?limit|logging|error.?handling)\b',
        ],
        BackendFeature.CONFIG: [
            r'\b(config|setting|environment|env)\b',
            r'\b(secret|key|connection)\b',
        ],
        BackendFeature.UTILS: [
            r'\b(helper|util|format|parse|validate)\b',
        ],
    }

    # Domain detection patterns (existing)
    DOMAIN_PATTERNS = {
        Domain.FRONTEND: [
            r'\b(ui|frontend|component|react|vue|angular|css|style|render|display)\b',
            r'\b(button|form|input|layout|navigation|menu|modal|dialog)\b',
            r'\b(responsive|animation|transition|theme|dark.?mode)\b',
            r'\b(chart|pie|graph|visualization|dashboard|plot|diagram)\b',
            r'\b(keyboard|tab|enter|escape|shortcut|focus|click|hover)\b',
            r'\b(tablet|mobile|screen|resolution|pixel|width|height|viewport)\b',
            r'\b(browser|chrome|firefox|safari|edge|client|localstorage|sessionstorage|cache|offline)\b',
            r'\b(table|row|column|header|footer|sidebar|panel|overlay|popup|tooltip)\b',
        ],
        Domain.BACKEND: [
            r'\b(backend|server|api|endpoint|route|controller|service)\b',
            r'\b(business.?logic|process|workflow|handler)\b',
        ],
        Domain.DATABASE: [
            r'\b(database|db|sql|query|table|schema|migration)\b',
            r'\b(model|entity|relation|index|crud)\b',
            r'\b(postgres|mysql|mongodb|redis|sqlite)\b',
        ],
        Domain.API: [
            r'\b(api|rest|graphql|websocket|http|request|response)\b',
            r'\b(endpoint|route|json|xml|payload)\b',
        ],
        Domain.AUTHENTICATION: [
            r'\b(auth|login|logout|session|token|jwt|oauth)\b',
            r'\b(password|user|permission|role|access|security)\b',
        ],
        Domain.INFRASTRUCTURE: [
            r'\b(deploy|docker|kubernetes|ci.?cd|pipeline)\b',
            r'\b(config|environment|env|setting|infrastructure)\b',
            r'\b(monitor|log|metric|alert)\b',
        ],
        Domain.TESTING: [
            r'\b(test|spec|mock|stub|fixture|coverage)\b',
            r'\b(unit|integration|e2e|acceptance)\b',
        ],
        Domain.DOCUMENTATION: [
            r'\b(doc|readme|comment|annotation|swagger|openapi)\b',
        ],
    }

    # Domain to agent mapping
    DOMAIN_AGENT_MAP = {
        Domain.FRONTEND: "frontend",
        Domain.BACKEND: "backend",
        Domain.DATABASE: "backend",
        Domain.API: "backend",
        Domain.AUTHENTICATION: "security",
        Domain.INFRASTRUCTURE: "devops",
        Domain.TESTING: "testing",
        Domain.DOCUMENTATION: "general",
        Domain.GENERAL: "general",
    }

    # Target requirements per slice (balances parallelism vs context)
    DEFAULT_SLICE_SIZE = 3

    # Estimated tokens per requirement (for planning)
    TOKENS_PER_REQ = 500

    def __init__(
        self,
        slice_size: int = DEFAULT_SLICE_SIZE,
        tech_stack: Optional[Any] = None,
        feature_config: Optional[FeatureGroupConfig] = None,
        working_dir: str | None = None,
    ):
        """
        Initialize the slicer.

        Args:
            slice_size: Target requirements per slice
            tech_stack: TechStack configuration
            feature_config: Feature grouping configuration
            working_dir: Working directory for Claude CLI (avoids CLAUDE.md context interference)
        """
        self.slice_size = slice_size
        self.tech_stack = tech_stack
        self.feature_config = feature_config or FeatureGroupConfig()
        self.working_dir = working_dir
        self.parser = DAGParser()
        self.logger = logger.bind(component="slicer")

    def slice_requirements(
        self,
        req_data: RequirementsData,
        job_id: int,
        strategy: str = "hybrid",
        tech_stack: Optional[Any] = None,
    ) -> SliceManifest:
        """
        Slice requirements into parallelizable groups.

        Args:
            req_data: Parsed requirements data with DAG
            job_id: Job ID for tracking
            strategy: Slicing strategy:
                - "depth": by DAG depth
                - "type": by agent type
                - "hybrid": depth + type
                - "domain": by functional domain
                - "tech_stack": based on TechStack
                - "feature_grouped": ARCH-37 - Feature-based large batches

        Returns:
            SliceManifest with all slices
        """
        effective_tech_stack = tech_stack or self.tech_stack
        
        self.logger.info(
            "slicing_requirements",
            job_id=job_id,
            strategy=strategy,
            total_reqs=len(req_data.requirements),
            has_tech_stack=effective_tech_stack is not None,
        )

        dag = req_data.dag
        if dag is None:
            raise ValueError("Requirements data has no DAG")

        # Get requirement nodes
        req_nodes = {n.id: n for n in req_data.nodes if n.type == NodeType.REQUIREMENT}

        # Select strategy
        if strategy == "depth":
            slices = self._slice_by_depth(dag, req_nodes, job_id)
        elif strategy == "type":
            slices = self._slice_by_type(dag, req_nodes, job_id)
        elif strategy == "domain":
            slices = self._slice_by_domain(dag, req_nodes, job_id)
        elif strategy == "tech_stack":
            slices = self._slice_by_tech_stack(dag, req_nodes, job_id, effective_tech_stack)
        elif strategy == "feature_grouped":
            slices = self._slice_by_feature_grouped(dag, req_nodes, job_id, effective_tech_stack)
        elif strategy == "documentation_epics":
            slices = self._slice_by_documentation_epics(dag, req_nodes, job_id, req_data)
        else:  # hybrid (default)
            slices = self._slice_hybrid(dag, req_nodes, job_id)

        # Build manifest
        depth_groups = self._build_depth_groups(slices)
        agent_distribution = self._build_agent_distribution(slices)

        manifest = SliceManifest(
            job_id=job_id,
            total_requirements=len(req_nodes),
            total_slices=len(slices),
            max_depth=max(s.depth for s in slices) if slices else 0,
            slices=slices,
            depth_groups=depth_groups,
            agent_distribution=agent_distribution,
        )

        self.logger.info(
            "slicing_complete",
            total_slices=len(slices),
            max_depth=manifest.max_depth,
            agent_distribution=agent_distribution,
        )

        return manifest

    def _detect_domain(self, node: DAGNode) -> Domain:
        """Detect the domain of a requirement based on its content."""
        text = f"{node.id} {node.name}".lower()
        
        domain_scores = defaultdict(int)
        
        for domain, patterns in self.DOMAIN_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, text, re.IGNORECASE))
                domain_scores[domain] += matches
        
        if domain_scores:
            best_domain = max(domain_scores.items(), key=lambda x: x[1])
            if best_domain[1] > 0:
                return best_domain[0]
        
        return Domain.GENERAL

    def _detect_frontend_feature(self, node: DAGNode) -> FrontendFeature:
        """ARCH-38: Detect frontend feature category."""
        text = f"{node.id} {node.name}".lower()
        
        feature_scores = defaultdict(int)
        
        for feature, patterns in self.FRONTEND_FEATURE_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, text, re.IGNORECASE))
                feature_scores[feature] += matches
        
        if feature_scores:
            best_feature = max(feature_scores.items(), key=lambda x: x[1])
            if best_feature[1] > 0:
                return best_feature[0]
        
        return FrontendFeature.COMPONENTS

    def _detect_backend_feature(self, node: DAGNode) -> BackendFeature:
        """ARCH-39: Detect backend feature category."""
        text = f"{node.id} {node.name}".lower()
        
        feature_scores = defaultdict(int)
        
        for feature, patterns in self.BACKEND_FEATURE_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, text, re.IGNORECASE))
                feature_scores[feature] += matches
        
        if feature_scores:
            best_feature = max(feature_scores.items(), key=lambda x: x[1])
            if best_feature[1] > 0:
                return best_feature[0]
        
        return BackendFeature.ROUTES

    def _slice_by_feature_grouped(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
        tech_stack: Optional[Any] = None,
    ) -> list[TaskSlice]:
        """
        ARCH-37: Feature-based slicing strategy.
        
        Groups ALL components together, ALL routes together, etc.
        Uses much larger batch sizes for more coherent code generation.
        """
        self.logger.info("slice_by_feature_grouped_start", total_reqs=len(req_nodes))
        
        # Step 1: Categorize by domain and feature
        frontend_reqs: defaultdict[FrontendFeature, list[tuple[str, DAGNode]]] = defaultdict(list)
        backend_reqs: defaultdict[BackendFeature, list[tuple[str, DAGNode]]] = defaultdict(list)
        other_reqs: defaultdict[Domain, list[tuple[str, DAGNode]]] = defaultdict(list)
        
        for rid, node in req_nodes.items():
            domain = self._detect_domain(node)
            
            if domain == Domain.FRONTEND:
                feature = self._detect_frontend_feature(node)
                frontend_reqs[feature].append((rid, node))
            elif domain in [Domain.BACKEND, Domain.API]:
                feature = self._detect_backend_feature(node)
                backend_reqs[feature].append((rid, node))
            else:
                other_reqs[domain].append((rid, node))
        
        slices: list[TaskSlice] = []
        slice_idx = 0
        
        # Step 2: Create frontend slices by feature
        for feature, reqs in frontend_reqs.items():
            if not reqs:
                continue
                
            batch_size = self.feature_config.frontend_feature_sizes.get(
                feature, self.feature_config.frontend_batch_size
            )
            
            # Split into batches
            for i in range(0, len(reqs), batch_size):
                batch = reqs[i:i + batch_size]
                worker_idx = i // batch_size
                
                slice_id = f"fe-{feature.value}-{slice_idx:03d}"
                task_slice = TaskSlice(
                    slice_id=slice_id,
                    depth=0,  # Feature-based doesn’t use depth
                    agent_type="frontend",
                    requirements=[r[0] for r in batch],
                    requirement_details=[
                        {
                            "id": r[0],
                            "label": r[1].name,
                            "description": r[1].payload.get("text", "")
                        }
                        for r in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                    priority=self._get_feature_priority(feature),
                    feature=feature.value,
                    worker_index=worker_idx,
                )
                slices.append(task_slice)
                slice_idx += 1

                self.logger.debug(
                    "created_frontend_slice",
                    slice_id=slice_id,
                    feature=feature.value,
                    req_count=len(batch),
                )
        
        # Step 3: Create backend slices by feature
        for feature, reqs in backend_reqs.items():
            if not reqs:
                continue
                
            batch_size = self.feature_config.backend_feature_sizes.get(
                feature, self.feature_config.backend_batch_size
            )
            
            for i in range(0, len(reqs), batch_size):
                batch = reqs[i:i + batch_size]
                worker_idx = i // batch_size
                
                slice_id = f"be-{feature.value}-{slice_idx:03d}"
                task_slice = TaskSlice(
                    slice_id=slice_id,
                    depth=1,  # Backend comes after frontend structure
                    agent_type="backend",
                    requirements=[r[0] for r in batch],
                    requirement_details=[
                        {
                            "id": r[0],
                            "label": r[1].name,
                            "description": r[1].payload.get("text", "")
                        }
                        for r in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                    priority=self._get_feature_priority(feature),
                    feature=feature.value,
                    worker_index=worker_idx,
                )
                slices.append(task_slice)
                slice_idx += 1

                self.logger.debug(
                    "created_backend_slice",
                    slice_id=slice_id,
                    feature=feature.value,
                    req_count=len(batch),
                )
        
        # Step 4: Create other domain slices
        for domain, reqs in other_reqs.items():
            if not reqs:
                continue
                
            agent_type = self.DOMAIN_AGENT_MAP.get(domain, "general")
            batch_size = self._get_domain_batch_size(domain)
            
            for i in range(0, len(reqs), batch_size):
                batch = reqs[i:i + batch_size]
                
                slice_id = f"{domain.value}-{slice_idx:03d}"
                task_slice = TaskSlice(
                    slice_id=slice_id,
                    depth=2,  # Other domains come last
                    agent_type=agent_type,
                    requirements=[r[0] for r in batch],
                    requirement_details=[
                        {
                            "id": r[0],
                            "label": r[1].name,
                            "description": r[1].payload.get("text", "")
                        }
                        for r in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                    priority=10,  # Lower priority
                )
                slices.append(task_slice)
                slice_idx += 1
        
        self.logger.info(
            "slice_by_feature_grouped_complete",
            total_slices=len(slices),
            frontend_features=len(frontend_reqs),
            backend_features=len(backend_reqs),
            other_domains=len(other_reqs),
        )
        
        return slices

    def _get_feature_priority(self, feature: FrontendFeature | BackendFeature) -> int:
        """Get priority for a feature (lower = higher priority)."""
        frontend_priorities = {
            FrontendFeature.LAYOUT: 1,
            FrontendFeature.COMPONENTS: 2,
            FrontendFeature.PAGES: 3,
            FrontendFeature.STATE: 4,
            FrontendFeature.HOOKS: 5,
            FrontendFeature.SERVICES: 6,
            FrontendFeature.STYLES: 7,
            FrontendFeature.UTILS: 8,
        }
        backend_priorities = {
            BackendFeature.CONFIG: 1,
            BackendFeature.MODELS: 2,
            BackendFeature.DATABASE: 3,
            BackendFeature.AUTH: 4,
            BackendFeature.MIDDLEWARE: 5,
            BackendFeature.SERVICES: 6,
            BackendFeature.ROUTES: 7,
            BackendFeature.UTILS: 8,
        }
        
        if isinstance(feature, FrontendFeature):
            return frontend_priorities.get(feature, 5)
        elif isinstance(feature, BackendFeature):
            return backend_priorities.get(feature, 5)
        return 5

    def _get_domain_batch_size(self, domain: Domain) -> int:
        """Get batch size for a domain."""
        batch_sizes = {
            Domain.DATABASE: self.feature_config.db_batch_size,
            Domain.TESTING: self.feature_config.testing_batch_size,
            Domain.INFRASTRUCTURE: 10,
            Domain.DOCUMENTATION: 10,
            Domain.AUTHENTICATION: 10,
        }
        return batch_sizes.get(domain, 15)

    def _slice_by_depth(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
    ) -> list[TaskSlice]:
        """Slice by DAG depth level."""
        # Calculate depths
        depths = {}
        for node_id in nx.topological_sort(dag):
            if node_id not in req_nodes:
                continue
            predecessors = list(dag.predecessors(node_id))
            if not predecessors:
                depths[node_id] = 0
            else:
                depths[node_id] = max(depths.get(p, 0) for p in predecessors) + 1

        # Group by depth
        depth_groups: defaultdict[int, list[str]] = defaultdict(list)
        for node_id, depth in depths.items():
            depth_groups[depth].append(node_id)

        # Create slices
        slices = []
        for depth, nodes in sorted(depth_groups.items()):
            for i in range(0, len(nodes), self.slice_size):
                batch = nodes[i:i + self.slice_size]
                slice_id = f"d{depth}-{len(slices):03d}"
                
                agent_type = self._determine_agent_type(batch, req_nodes)
                
                slices.append(TaskSlice(
                    slice_id=slice_id,
                    depth=depth,
                    agent_type=agent_type,
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name,
                            "description": req_nodes[rid].payload.get("text", "")
                        }
                        for rid in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                ))

        return slices

    def _slice_by_type(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
    ) -> list[TaskSlice]:
        """Slice by agent type."""
        type_groups: defaultdict[str, list[str]] = defaultdict(list)
        
        for rid, node in req_nodes.items():
            agent_type = self._determine_single_agent_type(node)
            type_groups[agent_type].append(rid)

        slices = []
        for agent_type, nodes in type_groups.items():
            for i in range(0, len(nodes), self.slice_size):
                batch = nodes[i:i + self.slice_size]
                slice_id = f"{agent_type}-{len(slices):03d}"
                
                slices.append(TaskSlice(
                    slice_id=slice_id,
                    depth=0,
                    agent_type=agent_type,
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name,
                            "description": req_nodes[rid].payload.get("text", "")
                        }
                        for rid in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                ))

        return slices

    def _slice_hybrid(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
    ) -> list[TaskSlice]:
        """Hybrid slicing: depth + type."""
        # Calculate depths
        depths = {}
        for node_id in nx.topological_sort(dag):
            if node_id not in req_nodes:
                continue
            predecessors = list(dag.predecessors(node_id))
            if not predecessors:
                depths[node_id] = 0
            else:
                depths[node_id] = max(depths.get(p, 0) for p in predecessors) + 1

        # Group by depth and type
        hybrid_groups: defaultdict[tuple[int, str], list[str]] = defaultdict(list)
        for rid, node in req_nodes.items():
            depth = depths.get(rid, 0)
            agent_type = self._determine_single_agent_type(node)
            hybrid_groups[(depth, agent_type)].append(rid)

        slices = []
        for (depth, agent_type), nodes in sorted(hybrid_groups.items()):
            for i in range(0, len(nodes), self.slice_size):
                batch = nodes[i:i + self.slice_size]
                slice_id = f"h-d{depth}-{agent_type}-{len(slices):03d}"

                slices.append(TaskSlice(
                    slice_id=slice_id,
                    depth=depth,
                    agent_type=agent_type,
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name,
                            "description": req_nodes[rid].payload.get("text", "")
                        }
                        for rid in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                ))

        return slices

    def _slice_by_domain(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
    ) -> list[TaskSlice]:
        """Slice by functional domain."""
        domain_groups: defaultdict[Domain, list[str]] = defaultdict(list)
        
        for rid, node in req_nodes.items():
            domain = self._detect_domain(node)
            domain_groups[domain].append(rid)

        slices = []
        for domain, nodes in domain_groups.items():
            agent_type = self.DOMAIN_AGENT_MAP.get(domain, "general")

            for i in range(0, len(nodes), self.slice_size):
                batch = nodes[i:i + self.slice_size]
                slice_id = f"dom-{domain.value}-{len(slices):03d}"

                slices.append(TaskSlice(
                    slice_id=slice_id,
                    depth=0,
                    agent_type=agent_type,
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name,
                            "description": req_nodes[rid].payload.get("text", "")
                        }
                        for rid in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                ))

        return slices

    def _slice_by_tech_stack(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
        tech_stack: Optional[Any] = None,
    ) -> list[TaskSlice]:
        """Slice using TechStack configuration."""
        if tech_stack is None:
            self.logger.warning("tech_stack_not_provided_falling_back_to_domain")
            return self._slice_by_domain(dag, req_nodes, job_id)

        # Use tech stack to determine domain mapping
        stack_domains: defaultdict[str, list[str]] = defaultdict(list)
        
        for rid, node in req_nodes.items():
            domain = self._detect_domain(node)
            
            # Map to tech stack component
            if domain == Domain.FRONTEND:
                stack_key = "frontend"
            elif domain in [Domain.BACKEND, Domain.API]:
                stack_key = "backend"
            elif domain == Domain.DATABASE:
                stack_key = "database"
            else:
                stack_key = "general"
                
            stack_domains[stack_key].append(rid)

        slices = []
        for stack_key, nodes in stack_domains.items():
            for i in range(0, len(nodes), self.slice_size):
                batch = nodes[i:i + self.slice_size]
                slice_id = f"ts-{stack_key}-{len(slices):03d}"

                slices.append(TaskSlice(
                    slice_id=slice_id,
                    depth=0,
                    agent_type=stack_key if stack_key != "database" else "backend",
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name,
                            "description": req_nodes[rid].payload.get("text", "")
                        }
                        for rid in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                ))

        return slices

    def _slice_by_documentation_epics(
        self,
        dag: nx.DiGraph,
        req_nodes: dict[str, DAGNode],
        job_id: int,
        req_data: RequirementsData,
    ) -> list[TaskSlice]:
        """
        Slice by Epic structure from Documentation format.

        This strategy:
        1. Groups requirements by their source epic
        2. Uses epic dependencies to determine depth (parallel execution order)
        3. Epics at the same depth run in parallel
        4. Maps epics to appropriate agent types

        Returns slices organized by epic with proper dependency ordering.
        """
        # Group requirements by epic
        epic_groups: defaultdict[str, list[str]] = defaultdict(list)
        unassigned: list[str] = []

        for rid, node in req_nodes.items():
            # Try to extract epic from source field or requirement ID
            source = node.payload.get("source", "")
            epic_id = None

            # Check source field (e.g., "epic:EPIC-001")
            if "epic:" in source.lower():
                epic_match = re.search(r"epic:(EPIC-\d+)", source, re.IGNORECASE)
                if epic_match:
                    epic_id = epic_match.group(1).upper()

            # Check requirement ID prefix (e.g., "WA-AUTH-001" -> EPIC-001)
            if not epic_id:
                epic_id = self._infer_epic_from_requirement_id(rid)

            if epic_id:
                epic_groups[epic_id].append(rid)
            else:
                unassigned.append(rid)

        # Build epic depth graph using dependencies
        epic_depths = self._calculate_epic_depths()

        slices = []

        # Create slices per epic, ordered by depth
        for epic_id in sorted(epic_groups.keys(), key=lambda e: epic_depths.get(e, 99)):
            reqs = epic_groups[epic_id]
            depth = epic_depths.get(epic_id, 0)
            agent_type = self.EPIC_AGENT_MAP.get(epic_id, "backend")
            depends_on = self.EPIC_DEPENDENCIES.get(epic_id, [])

            # For large epics, split into sub-slices
            batch_size = max(10, self.slice_size * 3)  # Larger batches for epics

            for i in range(0, len(reqs), batch_size):
                batch = reqs[i:i + batch_size]
                slice_idx = i // batch_size
                slice_id = f"epic-{epic_id.lower()}-{slice_idx:03d}"

                # Calculate dependent slice IDs
                depends_on_slices = [
                    f"epic-{dep.lower()}-000"
                    for dep in depends_on
                    if dep in epic_groups
                ]

                slices.append(TaskSlice(
                    slice_id=slice_id,
                    depth=depth,
                    agent_type=agent_type,
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name if rid in req_nodes else rid,
                            "description": req_nodes[rid].payload.get("text", "") if rid in req_nodes else "",
                            "epic": epic_id,
                        }
                        for rid in batch
                    ],
                    depends_on=depends_on_slices if slice_idx == 0 else [],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                    feature=epic_id,
                ))

        # Handle unassigned requirements as general slice
        if unassigned:
            for i in range(0, len(unassigned), self.slice_size):
                batch = unassigned[i:i + self.slice_size]
                slices.append(TaskSlice(
                    slice_id=f"epic-general-{i // self.slice_size:03d}",
                    depth=max(epic_depths.values()) + 1 if epic_depths else 0,
                    agent_type="general",
                    requirements=batch,
                    requirement_details=[
                        {
                            "id": rid,
                            "label": req_nodes[rid].name if rid in req_nodes else rid,
                            "description": req_nodes[rid].payload.get("text", "") if rid in req_nodes else "",
                        }
                        for rid in batch
                    ],
                    can_parallelize=True,
                    estimated_tokens=len(batch) * self.TOKENS_PER_REQ,
                ))

        self.logger.info(
            "epic_slicing_complete",
            total_epics=len(epic_groups),
            total_slices=len(slices),
            epic_distribution={k: len(v) for k, v in epic_groups.items()},
            unassigned_count=len(unassigned),
        )

        return slices

    def _calculate_epic_depths(self) -> dict[str, int]:
        """Calculate depth levels for epics based on dependencies."""
        depths: dict[str, int] = {}

        def get_depth(epic_id: str, visited: set) -> int:
            if epic_id in depths:
                return depths[epic_id]

            if epic_id in visited:
                return 0  # Avoid cycles

            visited.add(epic_id)
            deps = self.EPIC_DEPENDENCIES.get(epic_id, [])

            if not deps:
                depths[epic_id] = 0
            else:
                max_dep_depth = max(
                    get_depth(dep, visited.copy())
                    for dep in deps
                )
                depths[epic_id] = max_dep_depth + 1

            return depths[epic_id]

        for epic_id in self.EPIC_DEPENDENCIES:
            get_depth(epic_id, set())

        return depths

    def _infer_epic_from_requirement_id(self, req_id: str) -> Optional[str]:
        """Infer epic from requirement ID pattern."""
        # Map requirement ID prefixes to epics
        prefix_map = {
            "WA-AUTH": "EPIC-001",
            "WA-PROF": "EPIC-002",
            "WA-CON": "EPIC-002",  # Contacts
            "WA-SET": "EPIC-002",  # Settings
            "WA-MSG": "EPIC-003",
            "WA-MED": "EPIC-003",  # Media
            "WA-GRP": "EPIC-004",
            "WA-CALL": "EPIC-005",
            "WA-STS": "EPIC-006",  # Status
            "WA-SEC": "EPIC-007",
            "WA-NOT": "EPIC-008",  # Notifications
            "WA-BUS": "EPIC-009",  # Business
            "WA-BAK": "EPIC-010",  # Backup
            "WA-ACC": "EPIC-002",  # Accessibility -> Profile
            "WA-PERF": "EPIC-007",  # Performance -> Security
            "WA-INT": "EPIC-009",  # Integration -> Business
            "WA-AI": "EPIC-009",   # AI -> Business
            "WA-LOC": "EPIC-002",  # Localization -> Profile
        }

        for prefix, epic_id in prefix_map.items():
            if req_id.upper().startswith(prefix):
                return epic_id

        return None

    def _determine_agent_type(self, batch: list[str], req_nodes: dict[str, DAGNode]) -> str:
        """Determine best agent type for a batch of requirements."""
        type_counts: defaultdict[str, int] = defaultdict(int)
        
        for rid in batch:
            if rid in req_nodes:
                agent_type = self._determine_single_agent_type(req_nodes[rid])
                type_counts[agent_type] += 1
        
        if type_counts:
            return max(type_counts.items(), key=lambda x: x[1])[0]
        return "general"

    def _determine_single_agent_type(self, node: DAGNode) -> str:
        """Determine agent type for a single requirement."""
        domain = self._detect_domain(node)
        return self.DOMAIN_AGENT_MAP.get(domain, "general")

    def _build_depth_groups(self, slices: list[TaskSlice]) -> dict:
        """Build depth group mapping."""
        groups: defaultdict[int, list[str]] = defaultdict(list)
        for s in slices:
            groups[s.depth].append(s.slice_id)
        return {k: v for k, v in sorted(groups.items())}

    def _build_agent_distribution(self, slices: list[TaskSlice]) -> dict:
        """Build agent distribution mapping."""
        dist: defaultdict[str, int] = defaultdict(int)
        for s in slices:
            dist[s.agent_type] += 1
        return dict(dist)

    def create_domain_chunks(
        self,
        req_data: RequirementsData,
        max_chunk_size: int = 10,
    ) -> list[DomainChunk]:
        """
        Create domain-based chunks for specialized processing.
        
        This creates larger chunks grouped by functional domain,
        useful for specialized agents.
        """
        req_nodes = {n.id: n for n in req_data.nodes if n.type == NodeType.REQUIREMENT}
        
        domain_reqs: defaultdict[Domain, list[tuple[str, DAGNode]]] = defaultdict(list)
        
        for rid, node in req_nodes.items():
            domain = self._detect_domain(node)
            domain_reqs[domain].append((rid, node))
        
        chunks = []
        for domain, reqs in domain_reqs.items():
            for i in range(0, len(reqs), max_chunk_size):
                batch = reqs[i:i + max_chunk_size]
                
                chunk = DomainChunk(
                    domain=domain,
                    requirements=[r[0] for r in batch],
                    estimated_complexity=self._estimate_chunk_complexity(batch),
                    suggested_agent=self.DOMAIN_AGENT_MAP.get(domain, "general"),
                )
                chunks.append(chunk)
        
        return chunks

    def _estimate_chunk_complexity(self, batch: list[tuple[str, DAGNode]]) -> int:
        """Estimate complexity of a chunk (1-10 scale)."""
        if not batch:
            return 1

        total_len = sum(len(node.name) for _, node in batch)
        avg_len = total_len / len(batch)

        # Simple heuristic: longer descriptions = more complex
        if avg_len > 200:
            return 8
        elif avg_len > 100:
            return 5
        else:
            return 3

    # =========================================================================
    # Phase 9: LLM-Enhanced Intelligent Requirement Chunking
    # =========================================================================

    async def chunk_requirements_with_llm(
        self,
        features: list[dict],
    ) -> list[dict]:
        """
        Use LLM to intelligently group requirements into parallel execution chunks.

        This method provides semantic understanding beyond keyword matching:
        1. Groups features that share entities together
        2. Respects dependencies (auth before protected routes)
        3. CRUD operations on same entity are chunked
        4. UI components can parallelize with backend
        5. Maximizes parallelism while respecting dependencies

        Args:
            features: List of feature dicts with id, name, description

        Returns:
            List of chunk dicts with:
            - chunk_id: int
            - features: list[str] (feature IDs)
            - depends_on: list[int] (chunk IDs this depends on)
            - domain: str
            - can_parallel: bool
            - estimated_complexity: int (1-10)
        """
        if not features:
            return []

        # Try LLM-based chunking first
        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            tool = ClaudeCodeTool(working_dir=self.working_dir or ".", timeout=60)

            features_json = json.dumps(features[:50], indent=2)  # Limit for token efficiency

            prompt = f"""Group these software requirements into parallel execution chunks:

## FEATURES:
{features_json}

## CHUNKING RULES:

1. **Entity Grouping**: Features that operate on the same entity (User, Product, Order) should be in the same chunk
2. **Dependency Order**: Authentication features must come BEFORE protected route features
3. **CRUD Bundling**: All CRUD operations (Create, Read, Update, Delete) for an entity go together
4. **Frontend/Backend Split**: UI components can parallelize with backend API
5. **Maximize Parallelism**: Independent chunks can run simultaneously

## DOMAIN CATEGORIES:
- `auth`: Authentication, login, registration, permissions
- `user`: User management, profiles, settings
- `data`: Core business entities (products, orders, etc.)
- `ui`: Frontend components, pages, layouts
- `api`: Backend routes, endpoints
- `db`: Database schemas, migrations
- `infra`: Infrastructure, deployment, config

## RESPONSE FORMAT:

```json
{{
  "chunks": [
    {{
      "chunk_id": 0,
      "features": ["feature_1", "feature_2"],
      "depends_on": [],
      "domain": "auth",
      "can_parallel": true,
      "estimated_complexity": 5,
      "rationale": "User authentication must be set up first"
    }},
    {{
      "chunk_id": 1,
      "features": ["feature_3", "feature_4", "feature_5"],
      "depends_on": [0],
      "domain": "data",
      "can_parallel": true,
      "estimated_complexity": 7,
      "rationale": "Product CRUD operations bundled together"
    }}
  ],
  "parallel_groups": [[0, 2], [1, 3]],
  "execution_order": [0, 1, 2, 3]
}}
```

IMPORTANT:
- Auth/setup chunks should have `depends_on: []` and come first
- Protected features should depend on auth chunks
- Maximize parallel_groups for faster execution
"""

            result = await tool.execute(
                prompt=prompt,
                context="Requirement chunking",
                agent_type="chunk_planner",
            )

            output = result.output if hasattr(result, 'output') else str(result)

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
                chunks = analysis.get("chunks", [])

                self.logger.info(
                    "llm_chunking_complete",
                    total_features=len(features),
                    chunks_created=len(chunks),
                    parallel_groups=len(analysis.get("parallel_groups", [])),
                )

                return chunks

        except Exception as e:
            self.logger.warning("llm_chunking_failed", error=str(e))

        # Fallback to rule-based chunking
        return self._fallback_chunk_requirements(features)

    def _fallback_chunk_requirements(self, features: list[dict]) -> list[dict]:
        """Simple rule-based chunking as fallback when LLM fails."""
        chunks = []
        chunk_id = 0

        # Group by detected domain
        domain_groups: defaultdict[str, list[str]] = defaultdict(list)

        for feature in features:
            feature_id = feature.get("id", str(len(domain_groups)))
            name = feature.get("name", "").lower()
            desc = feature.get("description", "").lower()
            text = name + " " + desc

            # Use pattern-based domain classification
            domain = self._classify_feature_domain(text)
            domain_groups[domain].append(feature_id)

        # Create chunks with dependencies
        auth_chunk_id = None

        for domain, feature_ids in domain_groups.items():
            if not feature_ids:
                continue

            depends_on = []
            if domain != "auth" and auth_chunk_id is not None:
                depends_on = [auth_chunk_id]

            chunk = {
                "chunk_id": chunk_id,
                "features": feature_ids,
                "depends_on": depends_on,
                "domain": domain,
                "can_parallel": domain != "auth",
                "estimated_complexity": min(len(feature_ids), 10),
                "rationale": f"Grouped {len(feature_ids)} {domain} features",
            }

            if domain == "auth":
                auth_chunk_id = chunk_id

            chunks.append(chunk)
            chunk_id += 1

        return chunks

    def _classify_feature_domain(self, text: str) -> str:
        """
        Classify feature into a domain using pattern-based detection.

        Uses comprehensive keyword patterns with priority ordering
        to assign features to the most appropriate domain.
        """
        text_lower = text.lower()

        # Domain patterns with priority order (first match wins)
        domain_patterns = [
            # Auth domain - highest priority for security-related features
            (["auth", "login", "logout", "register", "password", "permission", "role",
              "access control", "jwt", "oauth", "session", "token", "security"], "auth"),

            # Database domain - data persistence related
            (["database", "schema", "table", "migration", "query", "sql", "orm",
              "prisma", "postgresql", "mongodb", "redis", "model", "entity"], "db"),

            # API domain - backend endpoints and services
            (["api", "endpoint", "route", "rest", "graphql", "controller", "handler",
              "service", "backend", "middleware", "express", "fastapi"], "api"),

            # User domain - user management and profiles
            (["user", "profile", "account", "settings", "preferences", "avatar",
              "notification", "dashboard"], "user"),

            # UI domain - frontend components and pages
            (["page", "component", "button", "form", "ui", "layout", "navigation",
              "menu", "modal", "dialog", "input", "table", "list", "card",
              "sidebar", "header", "footer", "responsive", "mobile"], "ui"),

            # Infrastructure domain
            (["deploy", "docker", "kubernetes", "ci/cd", "pipeline", "config",
              "environment", "infrastructure", "monitoring", "logging"], "infra"),

            # Testing domain
            (["test", "spec", "unit test", "integration test", "e2e", "coverage",
              "mock", "fixture"], "testing"),
        ]

        for keywords, domain in domain_patterns:
            if any(kw in text_lower for kw in keywords):
                return domain

        # Default to data domain for unclassified features
        return "data"

    async def infer_routes_with_llm(
        self,
        requirements: list[dict],
    ) -> list[dict]:
        """
        Use LLM to extract UI routes/pages from requirements.

        This method understands navigation patterns beyond keyword matching:
        - Identifies implicit pages (dashboard implies /dashboard route)
        - Detects protected routes (requires auth)
        - Finds nested routes (users/:id/settings)
        - Infers route hierarchy

        Args:
            requirements: List of requirement dicts

        Returns:
            List of route dicts with:
            - path: str (e.g., /users, /dashboard)
            - component: str (UserList, Dashboard)
            - protected: bool
            - parent: str | None
            - params: list[str]
        """
        if not requirements:
            return []

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            tool = ClaudeCodeTool(working_dir=self.working_dir or ".", timeout=60)

            reqs_json = json.dumps(requirements[:30], indent=2)

            prompt = f"""Extract all UI routes/pages from these requirements:

## REQUIREMENTS:
{reqs_json}

## TASK:

Identify all pages/routes the application needs based on the requirements.

For each route determine:
1. **Path**: URL path (e.g., /users, /dashboard, /settings)
2. **Component**: React component name (UserList, Dashboard, Settings)
3. **Protected**: Does it require authentication?
4. **Parent**: Parent route for nested routes (null if top-level)
5. **Params**: Dynamic URL segments (e.g., /users/:id → ["id"])

## COMMON PATTERNS:

- "Dashboard" → /dashboard (protected)
- "User list" → /users (protected)
- "User details" → /users/:id (protected, parent: /users)
- "Login page" → /login (not protected)
- "Settings" → /settings (protected)
- "Admin panel" → /admin/* (protected, admin-only)

## RESPONSE FORMAT:

```json
{{
  "routes": [
    {{
      "path": "/dashboard",
      "component": "Dashboard",
      "protected": true,
      "parent": null,
      "params": []
    }},
    {{
      "path": "/users/:id",
      "component": "UserDetail",
      "protected": true,
      "parent": "/users",
      "params": ["id"]
    }}
  ],
  "auth_routes": ["/login", "/register", "/forgot-password"],
  "admin_routes": ["/admin", "/admin/users"]
}}
```
"""

            result = await tool.execute(
                prompt=prompt,
                context="Route discovery",
                agent_type="route_analyzer",
            )

            output = result.output if hasattr(result, 'output') else str(result)

            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
                routes = analysis.get("routes", [])

                self.logger.info(
                    "llm_route_discovery_complete",
                    routes_found=len(routes),
                    auth_routes=len(analysis.get("auth_routes", [])),
                    admin_routes=len(analysis.get("admin_routes", [])),
                )

                return routes

        except Exception as e:
            self.logger.warning("llm_route_discovery_failed", error=str(e))

        # Fallback to keyword-based route detection
        return self._fallback_infer_routes(requirements)

    def _fallback_infer_routes(self, requirements: list[dict]) -> list[dict]:
        """Simple keyword-based route inference as fallback."""
        routes = []

        # Keywords that suggest routes
        route_patterns = {
            "dashboard": ("/dashboard", "Dashboard", True),
            "home": ("/", "Home", False),
            "login": ("/login", "Login", False),
            "register": ("/register", "Register", False),
            "profile": ("/profile", "Profile", True),
            "settings": ("/settings", "Settings", True),
            "admin": ("/admin", "AdminPanel", True),
            "users": ("/users", "UserList", True),
            "products": ("/products", "ProductList", True),
            "orders": ("/orders", "OrderList", True),
        }

        found_routes = set()

        for req in requirements:
            text = (req.get("name", "") + " " + req.get("description", "")).lower()

            for keyword, (path, component, protected) in route_patterns.items():
                if keyword in text and path not in found_routes:
                    routes.append({
                        "path": path,
                        "component": component,
                        "protected": protected,
                        "parent": None,
                        "params": [],
                    })
                    found_routes.add(path)

        return routes
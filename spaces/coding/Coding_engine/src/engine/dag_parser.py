"""
DAG Parser - Parses requirements JSON and extracts a Directed Acyclic Graph.

This module handles:
1. Parsing the requirements JSON format
2. Extracting knowledge graph nodes and edges
3. Building a DAG for task scheduling
4. Inferring dependencies from requirement relationships
"""
import json
import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import networkx as nx
import structlog

logger = structlog.get_logger()


class NodeType(str, Enum):
    """Type of knowledge graph node."""
    REQUIREMENT = "Requirement"
    TAG = "Tag"
    ENTITY = "Entity"
    UNKNOWN = "Unknown"


class EdgeRelation(str, Enum):
    """Type of edge relationship."""
    HAS_TAG = "HAS_TAG"
    RELATED_TO = "relatedTo"
    DEPENDS_ON = "DEPENDS_ON"
    PARENT_OF = "PARENT_OF"
    UNKNOWN = "unknown"


@dataclass
class DAGNode:
    """Represents a node in the dependency graph."""
    id: str
    type: NodeType
    name: str
    tag: Optional[str] = None
    payload: dict = field(default_factory=dict)

    # Computed fields for task generation
    depth: int = 0
    task_type: Optional[str] = None


@dataclass
class DAGEdge:
    """Represents an edge in the dependency graph."""
    id: str
    from_node: str
    to_node: str
    relation: EdgeRelation
    payload: dict = field(default_factory=dict)


@dataclass
class RequirementsData:
    """Parsed requirements data with knowledge graph."""
    success: bool
    workflow_status: str
    requirements: list[dict]
    nodes: list[DAGNode]
    edges: list[DAGEdge]
    summary: dict

    # Computed DAG
    dag: Optional[nx.DiGraph] = None
    requirement_groups: dict = field(default_factory=dict)


class DAGParser:
    """
    Parses requirements JSON and builds a DAG for task scheduling.

    The parser:
    1. Loads and validates the JSON structure
    2. Extracts requirements and knowledge graph
    3. Infers dependencies between requirements
    4. Groups requirements by tag/type for agent assignment
    5. Computes topological order for execution
    """

    def __init__(self):
        self.logger = logger.bind(component="dag_parser")

    def parse_file(self, file_path: str) -> RequirementsData:
        """Parse requirements from a JSON file."""
        self.logger.info("parsing_file", path=file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return self.parse(data)

    def parse(self, data: dict) -> RequirementsData:
        """Parse requirements from a dictionary."""
        self.logger.info("parsing_requirements")

        # Validate structure
        if not isinstance(data, dict):
            raise ValueError("Requirements data must be a dictionary")

        # Extract basic fields
        success = data.get("success", False)
        workflow_status = data.get("workflow_status", "unknown")
        # Support both "requirements" and "features" keys for flexibility
        requirements = data.get("requirements", [])
        if not requirements:
            # Fall back to features key (common format from JSON requirements)
            features = data.get("features", [])
            if features:
                # Convert features to requirements format with DAG-compatible IDs
                requirements = []
                for i, feat in enumerate(features):
                    req = {
                        "id": feat.get("id", f"REQ-{i+1:03d}"),
                        "name": feat.get("name", f"Feature {i+1}"),
                        "description": feat.get("description", ""),
                        "priority": feat.get("priority", "medium"),
                        "type": "functional",
                    }
                    requirements.append(req)
        summary = data.get("summary", {})

        # Extract knowledge graph
        kg_data = data.get("kg_data", {})
        nodes = self._parse_nodes(kg_data.get("nodes", []))
        edges = self._parse_edges(kg_data.get("edges", []))

        # If no kg_data nodes but we have requirements, create nodes from them
        if not nodes and requirements:
            nodes = []
            for req in requirements:
                # Support both formats: "id"/"req_id" and "name"/"title"
                req_id = req.get("req_id") or req.get("id", "")
                req_name = req.get("title") or req.get("name", req_id)
                req_type = req.get("type", "functional")
                # Use tag from requirement if present, otherwise infer from priority
                tag = req.get("tag") or self._priority_to_tag(req.get("priority", "medium"), req_type)
                node = DAGNode(
                    id=req_id,
                    name=req_name,
                    type=NodeType.REQUIREMENT,
                    tag=tag,
                    depth=0,
                    payload=req,
                )
                nodes.append(node)

        self.logger.info(
            "parsed_requirements",
            num_requirements=len(requirements),
            num_nodes=len(nodes),
            num_edges=len(edges),
        )

        # Create RequirementsData
        req_data = RequirementsData(
            success=success,
            workflow_status=workflow_status,
            requirements=requirements,
            nodes=nodes,
            edges=edges,
            summary=summary,
        )

        # Build DAG
        req_data.dag = self._build_dag(req_data)
        req_data.requirement_groups = self._group_requirements(req_data)

        return req_data

    def _priority_to_tag(self, priority: str, req_type: str) -> str:
        """Convert priority and type to a tag for grouping."""
        # Map to standard groupings
        if req_type in ("security", "performance"):
            return req_type
        if priority == "high":
            return "functional"
        return "other"

    def _parse_nodes(self, raw_nodes: list[dict]) -> list[DAGNode]:
        """Parse knowledge graph nodes."""
        nodes = []
        for raw in raw_nodes:
            node_type = NodeType.UNKNOWN
            try:
                node_type = NodeType(raw.get("type", "Unknown"))
            except ValueError:
                pass

            payload = raw.get("payload", {})
            tag = payload.get("tag") if isinstance(payload, dict) else None

            node = DAGNode(
                id=raw.get("id", ""),
                type=node_type,
                name=raw.get("name", ""),
                tag=tag,
                payload=payload,
            )
            nodes.append(node)

        return nodes

    def _parse_edges(self, raw_edges: list[dict]) -> list[DAGEdge]:
        """Parse knowledge graph edges."""
        edges = []
        for raw in raw_edges:
            relation = EdgeRelation.UNKNOWN
            rel_str = raw.get("rel", "unknown")

            # Normalize relation names
            if rel_str.upper() == "HAS_TAG" or rel_str == "hasTag":
                relation = EdgeRelation.HAS_TAG
            elif rel_str == "relatedTo":
                relation = EdgeRelation.RELATED_TO
            elif rel_str.upper() == "DEPENDS_ON":
                relation = EdgeRelation.DEPENDS_ON

            edge = DAGEdge(
                id=raw.get("id", ""),
                from_node=raw.get("from", ""),
                to_node=raw.get("to", ""),
                relation=relation,
                payload=raw.get("payload", {}),
            )
            edges.append(edge)

        return edges

    def _build_dag(self, req_data: RequirementsData) -> nx.DiGraph:
        """
        Build a NetworkX DAG from requirements.

        Dependencies are inferred from:
        1. Explicit DEPENDS_ON edges (if present)
        2. Requirement ID hierarchy (REQ-xxx-000 -> REQ-xxx-000-a)
        3. Related entities (requirements sharing entities)
        """
        dag = nx.DiGraph()

        # Add requirement nodes
        req_nodes = {n.id: n for n in req_data.nodes if n.type == NodeType.REQUIREMENT}

        for node_id, node in req_nodes.items():
            dag.add_node(
                node_id,
                name=node.name,
                tag=node.tag,
                type=node.type.value,
                payload=node.payload,
            )

        # Add explicit dependency edges
        for edge in req_data.edges:
            if edge.relation == EdgeRelation.DEPENDS_ON:
                if edge.from_node in req_nodes and edge.to_node in req_nodes:
                    dag.add_edge(edge.to_node, edge.from_node)  # to_node must complete first

        # Infer dependencies from ID hierarchy
        # Pattern: REQ-xxx-000-a depends on REQ-xxx-000
        for node_id in req_nodes:
            parent_id = self._get_parent_req_id(node_id)
            if parent_id and parent_id in req_nodes:
                if not dag.has_edge(parent_id, node_id):
                    dag.add_edge(parent_id, node_id)

        # Group requirements that share entities
        entity_to_reqs = self._map_entities_to_requirements(req_data)

        # Compute depth levels (for parallel execution)
        self._compute_depths(dag, req_nodes)

        # Verify DAG is acyclic
        if not nx.is_directed_acyclic_graph(dag):
            self.logger.warning("cycle_detected", message="Graph has cycles, removing them")
            # Remove cycles by removing back edges
            while not nx.is_directed_acyclic_graph(dag):
                try:
                    cycle = nx.find_cycle(dag)
                    dag.remove_edge(*cycle[0])
                except nx.NetworkXNoCycle:
                    break

        self.logger.info(
            "dag_built",
            nodes=dag.number_of_nodes(),
            edges=dag.number_of_edges(),
        )

        return dag

    def _get_parent_req_id(self, req_id: str) -> Optional[str]:
        """
        Get parent requirement ID from hierarchy.

        Examples:
        - REQ-5ef27c-000-a -> REQ-5ef27c-000
        - REQ-5ef27c-001-b -> REQ-5ef27c-001
        - REQ-5ef27c-000 -> None (root)
        """
        # Pattern: REQ-{hash}-{num}-{letter}
        match = re.match(r'^(REQ-[a-f0-9]+-\d+)-[a-z]$', req_id)
        if match:
            return match.group(1)
        return None

    def _map_entities_to_requirements(self, req_data: RequirementsData) -> dict[str, list[str]]:
        """Map entities to the requirements that reference them."""
        entity_to_reqs: dict[str, list[str]] = {}

        for edge in req_data.edges:
            if edge.relation == EdgeRelation.RELATED_TO:
                if edge.from_node.startswith("REQ-"):
                    entity_id = edge.to_node
                    if entity_id not in entity_to_reqs:
                        entity_to_reqs[entity_id] = []
                    entity_to_reqs[entity_id].append(edge.from_node)

        return entity_to_reqs

    def _compute_depths(self, dag: nx.DiGraph, req_nodes: dict[str, DAGNode]):
        """Compute depth levels for parallel execution."""
        if dag.number_of_nodes() == 0:
            return

        # Find root nodes (no predecessors)
        roots = [n for n in dag.nodes() if dag.in_degree(n) == 0]

        # BFS to compute depths
        visited = set()
        current_depth = 0
        current_level = roots

        while current_level:
            next_level = []
            for node_id in current_level:
                if node_id in visited:
                    continue
                visited.add(node_id)

                # Update depth in DAGNode
                if node_id in req_nodes:
                    req_nodes[node_id].depth = current_depth

                # Update in DAG node attributes
                dag.nodes[node_id]['depth'] = current_depth

                # Add successors to next level
                for succ in dag.successors(node_id):
                    # Only add if all predecessors have been visited
                    if all(p in visited for p in dag.predecessors(succ)):
                        next_level.append(succ)

            current_level = next_level
            current_depth += 1

    def _group_requirements(self, req_data: RequirementsData) -> dict[str, list[str]]:
        """
        Group requirements by tag for agent assignment.

        Returns dict mapping tag -> list of requirement IDs
        """
        groups: dict[str, list[str]] = {
            "functional": [],
            "performance": [],
            "security": [],
            "other": [],
        }

        for node in req_data.nodes:
            if node.type == NodeType.REQUIREMENT:
                tag = node.tag or "other"
                if tag not in groups:
                    groups[tag] = []
                groups[tag].append(node.id)

        self.logger.info(
            "requirements_grouped",
            groups={k: len(v) for k, v in groups.items()},
        )

        return groups

    def get_execution_order(self, dag: nx.DiGraph) -> list[list[str]]:
        """
        Get execution order as layers that can run in parallel.

        Returns a list of lists, where each inner list contains
        requirement IDs that can be executed in parallel.
        """
        if dag.number_of_nodes() == 0:
            return []

        # Group by depth for parallel execution
        depth_groups: dict[int, list[str]] = {}
        for node_id in dag.nodes():
            depth = dag.nodes[node_id].get('depth', 0)
            if depth not in depth_groups:
                depth_groups[depth] = []
            depth_groups[depth].append(node_id)

        # Sort by depth
        max_depth = max(depth_groups.keys()) if depth_groups else 0
        layers = [depth_groups.get(d, []) for d in range(max_depth + 1)]

        self.logger.info(
            "execution_order_computed",
            num_layers=len(layers),
            layer_sizes=[len(l) for l in layers],
        )

        return layers

    def get_task_type_for_requirement(self, node: DAGNode) -> str:
        """
        Determine the agent/task type for a requirement.

        Uses heuristics based on requirement title and tag.
        """
        name_lower = node.name.lower()

        # UI-related keywords (expanded)
        if any(kw in name_lower for kw in [
            'ui', 'button', 'display', 'visual', 'render', 'overlay', 'panel', 'window',
            'chart', 'pie', 'graph', 'visualization', 'dashboard',
            'keyboard', 'tab', 'escape', 'shortcut', 'focus',
            'tablet', 'mobile', 'screen', 'resolution', 'pixel', 'responsive',
            'browser', 'chrome', 'firefox', 'safari', 'edge',
            'localstorage', 'cache', 'client', 'offline',
            'table', 'row', 'column', 'header', 'footer', 'sidebar',
            'modal', 'dialog', 'popup', 'tooltip', 'menu', 'navigation',
            'frontend', 'css', 'style', 'layout', 'component',
        ]):
            return 'frontend'

        # Backend-related keywords
        if any(kw in name_lower for kw in ['api', 'database', 'server', 'endpoint', 'query', 'storage', 'backend', 'route', 'service']):
            return 'backend'

        # Testing-related keywords
        if any(kw in name_lower for kw in ['test', 'validate', 'verify', 'check', 'assert']):
            return 'testing'

        # Security-related
        if node.tag == 'security' or any(kw in name_lower for kw in ['security', 'auth', 'permission', 'encrypt', 'token', 'password', 'login', 'logout']):
            return 'security'

        # Performance-related
        if node.tag == 'performance' or any(kw in name_lower for kw in ['performance', 'accuracy', 'precision', 'speed', 'latency', 'millisecond', 'second']):
            return 'backend'  # Performance usually involves backend optimization

        # DevOps-related
        if any(kw in name_lower for kw in ['deploy', 'docker', 'kubernetes', 'ci', 'cd', 'build', 'linux', 'macos', 'windows']):
            return 'devops'

        # Default to general
        return 'general'

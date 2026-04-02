"""
Package Dependency Resolver — Topological ordering for multi-package builds.

When the watch directory contains multiple packages that depend on each other
(e.g., a shared-lib that the API server needs), this module determines the
correct build order so dependencies are compiled before dependents.

Architecture::

    PackageDependencyResolver
        ├─ scan_dependencies()    → parse dependency declarations from each package
        ├─ resolve_build_order()  → topological sort via Kahn's algorithm
        ├─ detect_cycles()        → report circular dependency chains
        └─ get_dependency_graph() → full graph for visualization

Dependency declarations live in each package's tech_stack or a dedicated
``dependencies.json``::

    {
        "depends_on": ["shared-models", "auth-service"],
        "provides": ["user-service"]
    }

Usage::

    resolver = PackageDependencyResolver()
    order = resolver.resolve_build_order(packages)
    for batch in order:
        await asyncio.gather(*[build(pkg) for pkg in batch])
"""

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PackageDependency:
    """Dependency declaration for a single package."""
    package_name: str
    package_path: Path
    depends_on: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    optional_deps: List[str] = field(default_factory=list)
    version: str = "0.0.0"

    def to_dict(self) -> dict:
        return {
            "package_name": self.package_name,
            "package_path": str(self.package_path),
            "depends_on": self.depends_on,
            "provides": self.provides,
            "optional_deps": self.optional_deps,
            "version": self.version,
        }


@dataclass
class DependencyGraph:
    """Resolved dependency graph with build ordering."""
    nodes: Dict[str, PackageDependency] = field(default_factory=dict)
    edges: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    reverse_edges: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    build_order: List[List[str]] = field(default_factory=list)  # Batches of parallel builds
    cycles: List[List[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": {k: list(v) for k, v in self.edges.items()},
            "build_order": self.build_order,
            "cycles": self.cycles,
            "total_packages": len(self.nodes),
            "total_batches": len(self.build_order),
        }


class CyclicDependencyError(Exception):
    """Raised when circular dependencies are detected."""
    def __init__(self, cycles: List[List[str]]):
        self.cycles = cycles
        cycle_strs = [" -> ".join(c + [c[0]]) for c in cycles]
        super().__init__(f"Circular dependencies detected: {'; '.join(cycle_strs)}")


class PackageDependencyResolver:
    """
    Resolves build order for interdependent packages.

    Scans each package directory for dependency declarations and produces
    a topologically sorted build order, grouped into parallelizable batches.
    """

    def __init__(self, strict: bool = False):
        """
        Args:
            strict: If True, raise on missing dependencies.
                    If False, warn and skip missing deps.
        """
        self.strict = strict

    def scan_dependencies(self, packages: List[Any]) -> Dict[str, PackageDependency]:
        """
        Scan package manifests for dependency information.

        Looks for dependencies in:
        1. ``dependencies.json`` in the package root
        2. ``tech_stack.dependencies`` in the manifest
        3. ``MASTER_DOCUMENT.md`` for ``depends_on:`` annotations

        Args:
            packages: List of PackageManifest objects

        Returns:
            Dict mapping package name to PackageDependency
        """
        deps = {}

        for pkg in packages:
            pkg_name = pkg.project_name
            pkg_path = Path(pkg.package_path) if hasattr(pkg, "package_path") else Path(".")

            dep = PackageDependency(
                package_name=pkg_name,
                package_path=pkg_path,
                provides=[pkg_name],
            )

            # 1. Check dependencies.json
            deps_file = pkg_path / "dependencies.json"
            if deps_file.exists():
                try:
                    data = json.loads(deps_file.read_text(encoding="utf-8"))
                    dep.depends_on = data.get("depends_on", [])
                    dep.provides = data.get("provides", [pkg_name])
                    dep.optional_deps = data.get("optional", [])
                    dep.version = data.get("version", "0.0.0")
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("deps_json_parse_failed", package=pkg_name, error=str(e))

            # 2. Check tech_stack for dependency info
            tech_stack = getattr(pkg, "tech_stack", {})
            if isinstance(tech_stack, dict):
                stack_deps = tech_stack.get("dependencies", {})
                if isinstance(stack_deps, dict):
                    dep.depends_on.extend(stack_deps.get("internal", []))
                elif isinstance(stack_deps, list):
                    dep.depends_on.extend(stack_deps)

            # 3. Check MASTER_DOCUMENT.md for depends_on annotations
            master_doc = pkg_path / "MASTER_DOCUMENT.md"
            if master_doc.exists():
                try:
                    content = master_doc.read_text(encoding="utf-8")
                    for line in content.splitlines():
                        stripped = line.strip().lower()
                        if stripped.startswith("depends_on:") or stripped.startswith("depends-on:"):
                            parts = stripped.split(":", 1)[1].strip()
                            for d in parts.split(","):
                                d = d.strip().strip("`").strip('"').strip("'")
                                if d and d not in dep.depends_on:
                                    dep.depends_on.append(d)
                except OSError:
                    pass

            # Deduplicate
            dep.depends_on = list(dict.fromkeys(dep.depends_on))
            dep.provides = list(dict.fromkeys(dep.provides))
            deps[pkg_name] = dep

            logger.debug(
                "package_deps_scanned",
                package=pkg_name,
                depends_on=dep.depends_on,
                provides=dep.provides,
            )

        return deps

    def build_graph(self, deps: Dict[str, PackageDependency]) -> DependencyGraph:
        """
        Build a directed dependency graph.

        Args:
            deps: Package dependency declarations

        Returns:
            DependencyGraph with edges and reverse edges
        """
        graph = DependencyGraph()

        # Build provider index: "provides_name" -> package_name
        provider_index: Dict[str, str] = {}
        for pkg_name, dep in deps.items():
            graph.nodes[pkg_name] = dep
            for provided in dep.provides:
                provider_index[provided] = pkg_name

        # Build edges: dependency -> dependent
        for pkg_name, dep in deps.items():
            for needed in dep.depends_on:
                provider = provider_index.get(needed)
                if provider is None:
                    if self.strict:
                        raise ValueError(
                            f"Package '{pkg_name}' depends on '{needed}' which is not provided by any package"
                        )
                    logger.warning(
                        "missing_dependency",
                        package=pkg_name,
                        missing=needed,
                    )
                    continue
                if provider == pkg_name:
                    continue  # Self-dependency, skip
                # Edge: provider must be built before pkg_name
                graph.edges[provider].add(pkg_name)
                graph.reverse_edges[pkg_name].add(provider)

        return graph

    def detect_cycles(self, graph: DependencyGraph) -> List[List[str]]:
        """
        Detect circular dependencies using DFS.

        Returns:
            List of cycles (each cycle is a list of package names)
        """
        cycles = []
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str):
            visited.add(node)
            in_stack.add(node)
            path.append(node)

            for neighbor in graph.edges.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in in_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    cycles.append(list(cycle))

            path.pop()
            in_stack.discard(node)

        for node in graph.nodes:
            if node not in visited:
                dfs(node)

        graph.cycles = cycles
        return cycles

    def topological_sort_batched(self, graph: DependencyGraph) -> List[List[str]]:
        """
        Kahn's algorithm producing parallelizable batches.

        Each batch contains packages that can be built simultaneously
        because all their dependencies are in earlier batches.

        Returns:
            List of batches, where each batch is a list of package names.
            Packages within the same batch can be built in parallel.
        """
        # Calculate in-degrees (only counting edges within the graph)
        in_degree: Dict[str, int] = {n: 0 for n in graph.nodes}
        for node, deps in graph.reverse_edges.items():
            if node in in_degree:
                in_degree[node] = len([d for d in deps if d in graph.nodes])

        # Start with nodes that have no dependencies
        queue = deque([n for n, d in in_degree.items() if d == 0])
        batches: List[List[str]] = []
        processed = 0

        while queue:
            # All nodes currently in queue form one parallel batch
            batch = list(queue)
            batches.append(batch)
            queue.clear()

            for node in batch:
                processed += 1
                for dependent in graph.edges.get(node, set()):
                    if dependent in in_degree:
                        in_degree[dependent] -= 1
                        if in_degree[dependent] == 0:
                            queue.append(dependent)

        if processed < len(graph.nodes):
            # Some nodes couldn't be processed — there are cycles
            remaining = [n for n in graph.nodes if n not in {
                pkg for batch in batches for pkg in batch
            }]
            logger.error("topological_sort_incomplete", remaining=remaining)
            # Force remaining into a final batch (they have cycles)
            if remaining:
                batches.append(remaining)

        graph.build_order = batches
        return batches

    def resolve_build_order(
        self,
        packages: List[Any],
        fail_on_cycles: bool = False,
    ) -> DependencyGraph:
        """
        Full resolution: scan → build graph → detect cycles → sort.

        Args:
            packages: List of PackageManifest objects
            fail_on_cycles: If True, raise CyclicDependencyError on cycles

        Returns:
            DependencyGraph with build_order populated
        """
        # 1. Scan dependencies
        deps = self.scan_dependencies(packages)

        if not deps:
            return DependencyGraph()

        # 2. Build graph
        graph = self.build_graph(deps)

        # 3. Check for cycles
        cycles = self.detect_cycles(graph)
        if cycles:
            logger.warning("circular_dependencies_detected", cycles=cycles)
            if fail_on_cycles:
                raise CyclicDependencyError(cycles)

        # 4. Topological sort into batches
        batches = self.topological_sort_batched(graph)

        logger.info(
            "build_order_resolved",
            total_packages=len(deps),
            total_batches=len(batches),
            order=[pkg for batch in batches for pkg in batch],
            cycles=len(cycles),
        )

        return graph

    def get_affected_packages(
        self,
        graph: DependencyGraph,
        changed_package: str,
    ) -> List[str]:
        """
        Get all packages that need to be rebuilt when a package changes.

        Traverses the dependency graph forward from the changed package
        to find all transitive dependents.

        Args:
            graph: Resolved dependency graph
            changed_package: Name of the package that changed

        Returns:
            List of package names that need rebuilding (including the changed one)
        """
        affected: Set[str] = set()
        queue = deque([changed_package])

        while queue:
            current = queue.popleft()
            if current in affected:
                continue
            affected.add(current)
            for dependent in graph.edges.get(current, set()):
                if dependent not in affected:
                    queue.append(dependent)

        return sorted(affected)

    def get_build_plan_for(
        self,
        graph: DependencyGraph,
        target_package: str,
    ) -> List[List[str]]:
        """
        Get minimal build plan for a specific package and its dependencies.

        Returns only the batches needed to build the target package,
        not the entire graph.

        Args:
            graph: Resolved dependency graph
            target_package: Package to build

        Returns:
            Filtered build batches containing only required packages
        """
        # Find all transitive dependencies
        needed: Set[str] = set()
        queue = deque([target_package])

        while queue:
            current = queue.popleft()
            if current in needed:
                continue
            needed.add(current)
            for dep in graph.reverse_edges.get(current, set()):
                if dep not in needed:
                    queue.append(dep)

        # Filter build order to only include needed packages
        filtered_batches = []
        for batch in graph.build_order:
            filtered = [pkg for pkg in batch if pkg in needed]
            if filtered:
                filtered_batches.append(filtered)

        return filtered_batches

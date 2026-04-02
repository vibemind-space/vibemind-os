"""
Component Tree Tool - Generates hierarchical component structure for LLM context.

Parses React/Vue/Svelte component import relationships to build a tree showing:
- Parent -> Child component relationships
- File paths for each component
- Entry points (App.tsx, main.tsx, etc.)
- Orphan components (not imported anywhere)
- Circular dependencies

Used by ClaudeCodeTool to provide structural context during code generation.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

import structlog

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ImportInfo:
    """Information about a single import statement."""
    source_file: str      # File containing the import
    imported_name: str    # Component name (e.g., "Layout")
    import_path: str      # Relative path (e.g., "./components/Layout")
    resolved_path: Optional[str] = None  # Absolute resolved path
    is_component: bool = True  # True if it's a component (PascalCase)
    line_number: int = 0


@dataclass
class ComponentNode:
    """A component in the tree."""
    name: str
    file_path: str
    children: list["ComponentNode"] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # What this component imports
    imported_by: list[str] = field(default_factory=list)  # What imports this
    is_entry_point: bool = False
    framework: str = "react"


@dataclass
class ComponentTree:
    """Complete component tree for a project."""
    root_components: list[ComponentNode]  # Entry points (App, main, etc.)
    all_components: dict[str, ComponentNode]  # path -> node
    orphan_components: list[ComponentNode]  # Not imported anywhere
    circular_imports: list[tuple[str, str]]  # Detected cycles
    framework: str
    total_components: int
    max_depth: int


# =============================================================================
# Import Parsing Patterns
# =============================================================================

# React/TypeScript patterns
REACT_NAMED_IMPORT = re.compile(
    r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE
)
REACT_DEFAULT_IMPORT = re.compile(
    r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE
)
REACT_COMBINED_IMPORT = re.compile(
    r"import\s+(\w+)\s*,\s*\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE
)

# Vue patterns
VUE_IMPORT = re.compile(
    r"import\s+(\w+)\s+from\s+['\"]([^'\"]+\.vue)['\"]",
    re.MULTILINE
)

# Svelte patterns
SVELTE_IMPORT = re.compile(
    r"import\s+(\w+)\s+from\s+['\"]([^'\"]+\.svelte)['\"]",
    re.MULTILINE
)


# =============================================================================
# Component Tree Tool
# =============================================================================

class ComponentTreeTool:
    """
    Generates a hierarchical component tree from React/Vue/Svelte projects.

    Usage:
        tool = ComponentTreeTool("/path/to/project")
        tree = await tool.generate_tree()
        context = tool.format_as_context(tree)
    """

    # Entry point file patterns
    ENTRY_POINTS = {
        "react": ["App.tsx", "App.jsx", "App.ts", "App.js", "main.tsx", "main.jsx", "index.tsx", "index.jsx"],
        "vue": ["App.vue", "main.ts", "main.js"],
        "svelte": ["App.svelte", "main.ts", "main.js"],
    }

    # Directories to skip
    SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", "coverage", ".cache"}

    # File extensions by framework
    EXTENSIONS = {
        "react": {".tsx", ".jsx", ".ts", ".js"},
        "vue": {".vue", ".ts", ".js"},
        "svelte": {".svelte", ".ts", ".js"},
    }

    # Cache
    _cache: Optional[ComponentTree] = None
    _cache_mtime: dict[str, float] = {}

    def __init__(self, working_dir: str):
        """
        Initialize the component tree tool.

        Args:
            working_dir: Project root directory
        """
        self.working_dir = Path(working_dir)
        self.framework: Optional[str] = None
        self.logger = logger.bind(component="component_tree_tool")

    def is_applicable(self) -> bool:
        """Check if this project is a frontend project with components."""
        framework = self._detect_framework()
        if not framework:
            return False

        # Check for src directory with components
        src_dir = self.working_dir / "src"
        if not src_dir.exists():
            return False

        # Look for any component files
        extensions = self.EXTENSIONS.get(framework, set())
        for ext in extensions:
            if list(src_dir.rglob(f"*{ext}")):
                return True

        return False

    def _detect_framework(self) -> Optional[str]:
        """
        Detect the frontend framework from package.json.

        Returns:
            "react", "vue", "svelte", or None
        """
        if self.framework:
            return self.framework

        package_json = self.working_dir / "package.json"
        if not package_json.exists():
            return None

        try:
            with open(package_json, "r", encoding="utf-8") as f:
                pkg = json.load(f)

            deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {}),
            }

            # Check for frameworks
            if "react" in deps or "react-dom" in deps:
                self.framework = "react"
            elif "vue" in deps:
                self.framework = "vue"
            elif "svelte" in deps:
                self.framework = "svelte"

            return self.framework

        except Exception as e:
            self.logger.debug("framework_detection_failed", error=str(e))
            return None

    def _is_component_name(self, name: str) -> bool:
        """Check if a name looks like a component (PascalCase)."""
        if not name:
            return False
        # PascalCase: starts with uppercase, contains lowercase
        return name[0].isupper() and any(c.islower() for c in name)

    def _should_skip_import(self, import_path: str) -> bool:
        """Check if an import should be skipped (external packages, styles, etc.)."""
        # Skip external packages (no ./ or ../)
        if not import_path.startswith("."):
            return True

        # Skip style imports
        if any(import_path.endswith(ext) for ext in [".css", ".scss", ".less", ".sass", ".module.css"]):
            return True

        # Skip asset imports
        if any(import_path.endswith(ext) for ext in [".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico"]):
            return True

        # Skip JSON imports
        if import_path.endswith(".json"):
            return True

        return False

    def _resolve_import_path(self, import_path: str, source_file: Path) -> Optional[Path]:
        """
        Resolve a relative import path to an absolute file path.

        Args:
            import_path: The import path (e.g., "./components/Layout")
            source_file: The file containing the import

        Returns:
            Resolved absolute path or None if not found
        """
        source_dir = source_file.parent

        # Handle relative paths
        if import_path.startswith("./") or import_path.startswith("../"):
            base_path = source_dir / import_path
        else:
            return None

        # Try exact match first
        if base_path.exists() and base_path.is_file():
            return base_path

        # Try with extensions
        framework = self.framework or "react"
        extensions = self.EXTENSIONS.get(framework, {".tsx", ".jsx", ".ts", ".js"})

        for ext in extensions:
            candidate = base_path.with_suffix(ext)
            if candidate.exists():
                return candidate

            # Also try index files
            index_candidate = base_path / f"index{ext}"
            if index_candidate.exists():
                return index_candidate

        return None

    def _parse_imports(self, file_path: Path) -> list[ImportInfo]:
        """
        Parse import statements from a file.

        Args:
            file_path: Path to the file to parse

        Returns:
            List of ImportInfo objects
        """
        imports = []

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return imports

        # For Vue files, only parse the <script> section
        if file_path.suffix == ".vue":
            script_match = re.search(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
            if script_match:
                content = script_match.group(1)

        # For Svelte files, only parse the <script> section
        if file_path.suffix == ".svelte":
            script_match = re.search(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
            if script_match:
                content = script_match.group(1)

        # Parse combined imports: import Default, { Named } from '...'
        for match in REACT_COMBINED_IMPORT.finditer(content):
            default_name = match.group(1)
            named_imports = match.group(2)
            import_path = match.group(3)

            if self._should_skip_import(import_path):
                continue

            # Add default import
            if self._is_component_name(default_name):
                resolved = self._resolve_import_path(import_path, file_path)
                imports.append(ImportInfo(
                    source_file=str(file_path),
                    imported_name=default_name,
                    import_path=import_path,
                    resolved_path=str(resolved) if resolved else None,
                    is_component=True,
                ))

            # Add named imports
            for name in named_imports.split(","):
                name = name.strip()
                # Handle "as" aliases
                if " as " in name:
                    name = name.split(" as ")[0].strip()
                if self._is_component_name(name):
                    resolved = self._resolve_import_path(import_path, file_path)
                    imports.append(ImportInfo(
                        source_file=str(file_path),
                        imported_name=name,
                        import_path=import_path,
                        resolved_path=str(resolved) if resolved else None,
                        is_component=True,
                    ))

        # Parse named imports: import { X, Y } from '...'
        for match in REACT_NAMED_IMPORT.finditer(content):
            named_imports = match.group(1)
            import_path = match.group(2)

            if self._should_skip_import(import_path):
                continue

            for name in named_imports.split(","):
                name = name.strip()
                if " as " in name:
                    name = name.split(" as ")[0].strip()
                if self._is_component_name(name):
                    resolved = self._resolve_import_path(import_path, file_path)
                    imports.append(ImportInfo(
                        source_file=str(file_path),
                        imported_name=name,
                        import_path=import_path,
                        resolved_path=str(resolved) if resolved else None,
                        is_component=True,
                    ))

        # Parse default imports: import X from '...'
        for match in REACT_DEFAULT_IMPORT.finditer(content):
            name = match.group(1)
            import_path = match.group(2)

            if self._should_skip_import(import_path):
                continue

            # Skip if already captured by combined pattern
            if any(i.imported_name == name and i.import_path == import_path for i in imports):
                continue

            if self._is_component_name(name):
                resolved = self._resolve_import_path(import_path, file_path)
                imports.append(ImportInfo(
                    source_file=str(file_path),
                    imported_name=name,
                    import_path=import_path,
                    resolved_path=str(resolved) if resolved else None,
                    is_component=True,
                ))

        return imports

    def _scan_component_files(self) -> list[Path]:
        """Scan for all component files in the project."""
        files = []
        framework = self.framework or "react"
        extensions = self.EXTENSIONS.get(framework, {".tsx", ".jsx"})

        src_dir = self.working_dir / "src"
        if not src_dir.exists():
            src_dir = self.working_dir

        for file_path in src_dir.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip excluded directories
            if any(skip in file_path.parts for skip in self.SKIP_DIRS):
                continue

            # Only include component file extensions
            if file_path.suffix in extensions:
                files.append(file_path)

        return files

    def _find_entry_points(self, files: list[Path]) -> list[Path]:
        """Find entry point files (App.tsx, main.tsx, etc.)."""
        framework = self.framework or "react"
        entry_names = self.ENTRY_POINTS.get(framework, [])

        entry_points = []
        for file_path in files:
            if file_path.name in entry_names:
                entry_points.append(file_path)

        return entry_points

    def _build_graph(self, files: list[Path]) -> "nx.DiGraph":
        """
        Build a dependency graph of component imports.

        Args:
            files: List of component files

        Returns:
            NetworkX DiGraph with file paths as nodes
        """
        if not NETWORKX_AVAILABLE:
            raise ImportError("networkx is required for ComponentTreeTool")

        graph = nx.DiGraph()

        # Add all files as nodes
        for file_path in files:
            rel_path = str(file_path.relative_to(self.working_dir))
            graph.add_node(rel_path, name=file_path.stem, path=str(file_path))

        # Add edges for imports
        for file_path in files:
            imports = self._parse_imports(file_path)
            source_rel = str(file_path.relative_to(self.working_dir))

            for imp in imports:
                if imp.resolved_path:
                    try:
                        target_rel = str(Path(imp.resolved_path).relative_to(self.working_dir))
                        if target_rel in graph.nodes:
                            graph.add_edge(source_rel, target_rel)
                    except ValueError:
                        pass

        return graph

    def _detect_cycles(self, graph: "nx.DiGraph") -> list[tuple[str, str]]:
        """Detect circular dependencies in the graph."""
        if not NETWORKX_AVAILABLE:
            return []

        cycles = []
        try:
            for cycle in nx.simple_cycles(graph):
                if len(cycle) >= 2:
                    cycles.append((cycle[0], cycle[-1]))
        except Exception:
            pass

        return cycles

    def _build_tree_recursive(
        self,
        graph: "nx.DiGraph",
        node: str,
        visited: set[str],
        depth: int = 0,
        max_depth: int = 10,
    ) -> Optional[ComponentNode]:
        """
        Recursively build a tree from the graph.

        Args:
            graph: The dependency graph
            node: Current node
            visited: Set of visited nodes (for cycle detection)
            depth: Current depth
            max_depth: Maximum depth to traverse

        Returns:
            ComponentNode or None if already visited
        """
        if depth > max_depth:
            return None

        if node in visited:
            # Return a marker node for cycles
            return ComponentNode(
                name=f"[circular -> {Path(node).stem}]",
                file_path=node,
                is_entry_point=False,
            )

        visited = visited | {node}

        node_data = graph.nodes.get(node, {})
        component = ComponentNode(
            name=node_data.get("name", Path(node).stem),
            file_path=node,
            is_entry_point=False,
        )

        # Add children (components this one imports)
        for child in graph.successors(node):
            child_node = self._build_tree_recursive(graph, child, visited, depth + 1, max_depth)
            if child_node:
                component.children.append(child_node)

        return component

    async def generate_tree(self, use_cache: bool = True) -> ComponentTree:
        """
        Generate the component tree.

        Args:
            use_cache: Whether to use cached results

        Returns:
            ComponentTree with hierarchical structure
        """
        # Check cache
        if use_cache and self._cache and not self._is_cache_stale():
            return self._cache

        framework = self._detect_framework()
        if not framework:
            return ComponentTree(
                root_components=[],
                all_components={},
                orphan_components=[],
                circular_imports=[],
                framework="unknown",
                total_components=0,
                max_depth=0,
            )

        # Scan files
        files = self._scan_component_files()
        if not files:
            return ComponentTree(
                root_components=[],
                all_components={},
                orphan_components=[],
                circular_imports=[],
                framework=framework,
                total_components=0,
                max_depth=0,
            )

        # Build graph
        if not NETWORKX_AVAILABLE:
            self.logger.warning("networkx_not_available")
            return ComponentTree(
                root_components=[],
                all_components={},
                orphan_components=[],
                circular_imports=[],
                framework=framework,
                total_components=len(files),
                max_depth=0,
            )

        graph = self._build_graph(files)

        # Find entry points
        entry_points = self._find_entry_points(files)

        # Detect cycles
        circular = self._detect_cycles(graph)

        # Build trees from entry points
        root_components = []
        all_components: dict[str, ComponentNode] = {}
        visited_global: set[str] = set()
        max_depth = 0

        for entry in entry_points:
            entry_rel = str(entry.relative_to(self.working_dir))
            if entry_rel in graph.nodes:
                tree = self._build_tree_recursive(graph, entry_rel, set())
                if tree:
                    tree.is_entry_point = True
                    root_components.append(tree)
                    visited_global.add(entry_rel)

                    # Calculate max depth
                    def get_depth(node: ComponentNode, d: int = 0) -> int:
                        if not node.children:
                            return d
                        return max(get_depth(child, d + 1) for child in node.children)

                    max_depth = max(max_depth, get_depth(tree))

        # Find orphan components (not imported by anything)
        orphans = []
        for node in graph.nodes:
            if graph.in_degree(node) == 0 and node not in [str(e.relative_to(self.working_dir)) for e in entry_points]:
                node_data = graph.nodes.get(node, {})
                orphans.append(ComponentNode(
                    name=node_data.get("name", Path(node).stem),
                    file_path=node,
                ))

        # Build result
        tree = ComponentTree(
            root_components=root_components,
            all_components=all_components,
            orphan_components=orphans,
            circular_imports=circular,
            framework=framework,
            total_components=len(files),
            max_depth=max_depth,
        )

        # Update cache
        self._cache = tree
        self._update_cache_mtimes(files)

        return tree

    def _is_cache_stale(self) -> bool:
        """Check if any component files have changed since caching."""
        for path, mtime in self._cache_mtime.items():
            try:
                if Path(path).exists() and Path(path).stat().st_mtime > mtime:
                    return True
            except Exception:
                return True
        return False

    def _update_cache_mtimes(self, files: list[Path]) -> None:
        """Update cache modification times."""
        self._cache_mtime = {}
        for f in files:
            try:
                self._cache_mtime[str(f)] = f.stat().st_mtime
            except Exception:
                pass

    def format_as_context(self, tree: ComponentTree, max_components: int = 30) -> str:
        """
        Format the component tree as context for LLM.

        Args:
            tree: The component tree
            max_components: Maximum components to show

        Returns:
            Formatted string for LLM context
        """
        if not tree.root_components and not tree.orphan_components:
            return ""

        lines = [
            "## Component Tree",
            "",
            f"Framework: {tree.framework.title()}",
            f"Entry Points: {len(tree.root_components)} | Components: {tree.total_components} | Max Depth: {tree.max_depth}",
            "",
        ]

        def format_node(node: ComponentNode, prefix: str = "", is_last: bool = True, count: list = [0]) -> list[str]:
            """Format a single node and its children."""
            if count[0] >= max_components:
                return ["...truncated..."]

            count[0] += 1
            result = []

            connector = "└── " if is_last else "├── "
            entry_marker = " [ENTRY]" if node.is_entry_point else ""

            result.append(f"{prefix}{connector}{node.name} ({node.file_path}){entry_marker}")

            child_prefix = prefix + ("    " if is_last else "│   ")
            for i, child in enumerate(node.children):
                is_child_last = i == len(node.children) - 1
                result.extend(format_node(child, child_prefix, is_child_last, count))

            return result

        # Format root components
        component_count = [0]
        for i, root in enumerate(tree.root_components):
            is_last = i == len(tree.root_components) - 1
            lines.extend(format_node(root, "", is_last, component_count))

        # Show orphans
        if tree.orphan_components:
            lines.append("")
            orphan_names = [o.name for o in tree.orphan_components[:5]]
            if len(tree.orphan_components) > 5:
                orphan_names.append(f"...+{len(tree.orphan_components) - 5} more")
            lines.append(f"Orphans: {', '.join(orphan_names)}")

        # Show circular dependencies
        if tree.circular_imports:
            lines.append("")
            for a, b in tree.circular_imports[:3]:
                lines.append(f"Circular: {Path(a).stem} <-> {Path(b).stem}")

        return "\n".join(lines)

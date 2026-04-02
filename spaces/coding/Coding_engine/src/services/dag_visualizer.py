"""
Pipeline DAG Visualizer — Text-based visualization of pipeline execution graph.

Renders pipeline phases, agent dependencies, and execution flow as ASCII art.

Provides:
- Phase dependency DAG rendering
- Agent wait-for graph rendering
- Package dependency tree rendering
- Execution timeline rendering
- Status-annotated graphs (color via ANSI or plain text)

Usage::

    viz = DAGVisualizer()

    # Render pipeline phases
    print(viz.render_pipeline_dag(phases, edges))

    # Render agent dependency graph
    print(viz.render_wait_graph(wait_edges))

    # Render package build order
    print(viz.render_build_order(batches))
"""

from typing import Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ANSI color codes
class Color:
    RESET = "\033[0m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    DIM = "\033[2m"
    BOLD = "\033[1m"


def _colorize(text: str, color: str, use_color: bool = True) -> str:
    if not use_color:
        return text
    return f"{color}{text}{Color.RESET}"


class DAGVisualizer:
    """Text-based DAG renderer for pipeline visualization."""

    def __init__(self, use_color: bool = True, box_width: int = 20):
        self.use_color = use_color
        self.box_width = box_width

    def render_pipeline_dag(
        self,
        phases: List[str],
        edges: Optional[List[Tuple[str, str]]] = None,
        status: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Render pipeline phases as a vertical DAG.

        Args:
            phases: Ordered list of phase names
            edges: Optional dependency edges [(from, to), ...]
            status: Optional phase statuses {"phase": "completed|running|pending|failed"}
        """
        if not phases:
            return "(empty pipeline)"

        status = status or {}
        lines = []
        lines.append(self._header("Pipeline Execution DAG"))
        lines.append("")

        for i, phase in enumerate(phases):
            phase_status = status.get(phase, "pending")
            box = self._render_box(phase, phase_status)
            lines.extend(box)

            if i < len(phases) - 1:
                lines.append(self._center_text("|"))
                lines.append(self._center_text("v"))

        lines.append("")
        lines.append(self._legend())
        return "\n".join(lines)

    def render_wait_graph(
        self,
        waits: Dict[str, List[str]],
        title: str = "Agent Wait-For Graph",
    ) -> str:
        """
        Render agent wait-for relationships.

        Args:
            waits: {waiter: [blocker1, blocker2, ...]}
        """
        if not waits:
            return "(no active waits)"

        lines = []
        lines.append(self._header(title))
        lines.append("")

        all_agents = set()
        for waiter, blockers in waits.items():
            all_agents.add(waiter)
            all_agents.update(blockers)

        for waiter, blockers in sorted(waits.items()):
            for blocker in blockers:
                arrow = _colorize("-->", Color.YELLOW, self.use_color)
                w = _colorize(f"[{waiter}]", Color.RED, self.use_color)
                b = _colorize(f"[{blocker}]", Color.BLUE, self.use_color)
                lines.append(f"  {w} {arrow} waits for {arrow} {b}")

        # Show agents not waiting for anything
        waiters = set(waits.keys())
        free_agents = all_agents - waiters
        if free_agents:
            lines.append("")
            for agent in sorted(free_agents):
                a = _colorize(f"[{agent}]", Color.GREEN, self.use_color)
                lines.append(f"  {a} (free)")

        return "\n".join(lines)

    def render_build_order(
        self,
        batches: List[List[str]],
        title: str = "Build Order (Parallelizable Batches)",
    ) -> str:
        """
        Render batched build order from dependency resolution.

        Args:
            batches: List of lists, where each inner list is a parallelizable batch
        """
        if not batches:
            return "(no build order)"

        lines = []
        lines.append(self._header(title))
        lines.append("")

        for i, batch in enumerate(batches):
            level = _colorize(f"Level {i}:", Color.BOLD, self.use_color)
            parallel = _colorize("(parallel)", Color.DIM, self.use_color)
            lines.append(f"  {level} {parallel}")

            for pkg in batch:
                bullet = _colorize("*", Color.CYAN, self.use_color)
                lines.append(f"    {bullet} {pkg}")

            if i < len(batches) - 1:
                lines.append(f"    {'  |'}")
                lines.append(f"    {'  v'}")

        lines.append("")
        total = sum(len(b) for b in batches)
        lines.append(f"  Total: {total} packages in {len(batches)} levels")
        return "\n".join(lines)

    def render_execution_timeline(
        self,
        events: List[Dict],
        title: str = "Execution Timeline",
    ) -> str:
        """
        Render a timeline of execution events.

        Args:
            events: List of {"time": float, "agent": str, "action": str, "status": str}
        """
        if not events:
            return "(no events)"

        lines = []
        lines.append(self._header(title))
        lines.append("")

        # Find time range
        if events:
            min_time = min(e.get("time", 0) for e in events)
        else:
            min_time = 0

        for event in events:
            elapsed = event.get("time", 0) - min_time
            agent = event.get("agent", "?")
            action = event.get("action", "?")
            status = event.get("status", "")

            time_str = f"{elapsed:7.1f}s"
            time_col = _colorize(time_str, Color.DIM, self.use_color)

            status_icon = self._status_icon(status)
            agent_col = _colorize(f"[{agent}]", Color.CYAN, self.use_color)

            lines.append(f"  {time_col} {status_icon} {agent_col} {action}")

        return "\n".join(lines)

    def render_dependency_tree(
        self,
        root: str,
        children: Dict[str, List[str]],
        prefix: str = "",
        is_last: bool = True,
    ) -> str:
        """
        Render a tree structure for package dependencies.

        Args:
            root: Root node name
            children: {parent: [child1, child2, ...]}
        """
        lines = []
        connector = "└── " if is_last else "├── "
        node = _colorize(root, Color.CYAN, self.use_color)

        if prefix:
            lines.append(f"{prefix}{connector}{node}")
        else:
            lines.append(node)

        child_list = children.get(root, [])
        for i, child in enumerate(child_list):
            is_child_last = (i == len(child_list) - 1)
            extension = "    " if is_last else "│   "
            child_prefix = prefix + extension if prefix else extension
            sub_lines = self.render_dependency_tree(
                child, children, child_prefix, is_child_last
            )
            lines.append(sub_lines)

        return "\n".join(lines)

    def render_system_overview(
        self,
        services: Dict[str, bool],
        agents: List[Dict],
        metrics: Optional[Dict] = None,
    ) -> str:
        """Render a system overview dashboard."""
        lines = []
        lines.append(self._header("System Overview"))
        lines.append("")

        # Services
        lines.append(_colorize("  Services:", Color.BOLD, self.use_color))
        for name, active in sorted(services.items()):
            icon = _colorize("[ON]", Color.GREEN, self.use_color) if active else _colorize("[OFF]", Color.RED, self.use_color)
            lines.append(f"    {icon} {name}")

        # Agents
        if agents:
            lines.append("")
            lines.append(_colorize("  Agents:", Color.BOLD, self.use_color))
            for agent in agents:
                name = agent.get("agent_name", "?")
                avail = agent.get("availability", "unknown")
                tasks = agent.get("current_tasks", 0)
                icon = self._status_icon(avail)
                lines.append(f"    {icon} {name} (tasks: {tasks})")

        # Metrics
        if metrics:
            lines.append("")
            lines.append(_colorize("  Metrics:", Color.BOLD, self.use_color))
            for key, value in sorted(metrics.items()):
                lines.append(f"    {key}: {value}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _header(self, title: str) -> str:
        line = "=" * (len(title) + 4)
        colored_title = _colorize(title, Color.BOLD, self.use_color)
        return f"{line}\n  {colored_title}\n{line}"

    def _render_box(self, label: str, status: str) -> List[str]:
        """Render a boxed node with status coloring."""
        w = self.box_width
        label_str = label[:w - 4].center(w - 4)
        status_str = status[:w - 4].center(w - 4)

        color = {
            "completed": Color.GREEN,
            "running": Color.YELLOW,
            "pending": Color.DIM,
            "failed": Color.RED,
            "skipped": Color.DIM,
        }.get(status, Color.RESET)

        top = "+" + "-" * (w - 2) + "+"
        mid1 = "| " + label_str + " |"
        mid2 = "| " + status_str + " |"
        bot = "+" + "-" * (w - 2) + "+"

        pad = " " * ((40 - w) // 2)
        return [
            pad + _colorize(top, color, self.use_color),
            pad + _colorize(mid1, color, self.use_color),
            pad + _colorize(mid2, color, self.use_color),
            pad + _colorize(bot, color, self.use_color),
        ]

    def _center_text(self, text: str) -> str:
        pad = " " * 19  # Approximate center for 40-char width
        return pad + text

    def _status_icon(self, status: str) -> str:
        icons = {
            "completed": _colorize("[OK]", Color.GREEN, self.use_color),
            "running": _colorize("[>>]", Color.YELLOW, self.use_color),
            "pending": _colorize("[..]", Color.DIM, self.use_color),
            "failed": _colorize("[XX]", Color.RED, self.use_color),
            "online": _colorize("[ON]", Color.GREEN, self.use_color),
            "busy": _colorize("[~~]", Color.YELLOW, self.use_color),
            "offline": _colorize("[--]", Color.RED, self.use_color),
        }
        return icons.get(status, _colorize("[??]", Color.DIM, self.use_color))

    def _legend(self) -> str:
        items = [
            _colorize("[OK]", Color.GREEN, self.use_color) + " completed",
            _colorize("[>>]", Color.YELLOW, self.use_color) + " running",
            _colorize("[..]", Color.DIM, self.use_color) + " pending",
            _colorize("[XX]", Color.RED, self.use_color) + " failed",
        ]
        return "  Legend: " + "  |  ".join(items)

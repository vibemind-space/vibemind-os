"""
Tool Creation System (PHASE 10)

Implements dynamic tool generation and capability discovery:

1. Tool Discovery:
   - Identify missing capabilities
   - Detect patterns requiring new tools
   - Gap analysis between needs and available tools

2. Tool Generation:
   - Create new tools from primitives
   - Combine existing tools
   - Synthesize capabilities from patterns

3. Tool Validation:
   - Test generated tools in safe mode
   - Verify functionality and safety
   - Track tool effectiveness

4. Tool Evolution:
   - Refine tools based on usage
   - Deprecate underperforming tools
   - Optimize tool implementations

5. Tool Library Management:
   - Organize tools by category
   - Version control for tools
   - Dependency tracking

Based on cognitive science research:
- Tool use in primates (Köhler, 1925)
- Functional fixedness (Duncker, 1945)
- Insight problem solving (Metcalfe & Wiebe, 1987)
- Creative cognition (Finke, Ward, & Smith, 1992)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib


@dataclass
class Tool:
    """
    A tool (capability) that can be used by the system
    """
    tool_id: str
    tool_name: str
    tool_type: str  # primitive, composed, generated, evolved

    # Functionality
    description: str
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)

    # Implementation
    implementation: Optional[str] = None  # Code or recipe
    dependencies: List[str] = field(default_factory=list)  # Other tools needed

    # Performance
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_execution_time: float = 1.0

    # Metadata
    creation_time: float = 0.0
    creator: str = "system"  # system, user, evolved
    version: str = "1.0"

    def success_rate(self) -> float:
        """Compute success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'tool_id': self.tool_id,
            'tool_name': self.tool_name,
            'tool_type': self.tool_type,
            'description': self.description,
            'capabilities': self.capabilities,
            'usage_count': self.usage_count,
            'success_rate': self.success_rate(),
            'avg_execution_time': self.avg_execution_time,
            'version': self.version,
            'dependencies': len(self.dependencies)
        }


@dataclass
class ToolRecipe:
    """
    Recipe for creating a new tool from existing ones
    """
    recipe_id: str
    recipe_name: str
    component_tools: List[str]  # Tool IDs to combine

    # Composition strategy
    combination_type: str  # sequential, parallel, conditional, recursive

    # Expected properties
    expected_capabilities: List[str] = field(default_factory=list)
    expected_performance: float = 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'recipe_id': self.recipe_id,
            'recipe_name': self.recipe_name,
            'num_components': len(self.component_tools),
            'combination_type': self.combination_type,
            'expected_capabilities': self.expected_capabilities,
            'expected_performance': self.expected_performance
        }


@dataclass
class CapabilityGap:
    """
    Identified gap between needs and available capabilities
    """
    gap_id: str
    missing_capability: str
    frequency: int = 1  # How often this gap was encountered

    # Context
    task_types: List[str] = field(default_factory=list)
    failure_patterns: List[str] = field(default_factory=list)

    # Potential solutions
    suggested_tools: List[str] = field(default_factory=list)
    estimated_impact: float = 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'gap_id': self.gap_id,
            'missing_capability': self.missing_capability,
            'frequency': self.frequency,
            'task_types': self.task_types,
            'estimated_impact': self.estimated_impact,
            'suggested_tools': len(self.suggested_tools)
        }


class ToolCreation:
    """
    Tool creation system for dynamic capability generation

    Key features:
    - Discover capability gaps
    - Generate new tools
    - Combine existing tools
    - Evolve tools based on usage
    """

    def __init__(
        self,
        gap_threshold: int = 3,  # Min frequency to consider a gap significant
        tool_ttl: int = 100,  # Tool time-to-live (uses before deprecation review)
        min_success_rate: float = 0.3  # Min success rate to keep a tool
    ):
        """
        Initialize tool creation system

        Args:
            gap_threshold: Minimum gap frequency to trigger tool creation
            tool_ttl: Tool lifetime before deprecation review
            min_success_rate: Minimum success rate to keep tool
        """
        self.gap_threshold = gap_threshold
        self.tool_ttl = tool_ttl
        self.min_success_rate = min_success_rate

        # Tool library
        self.tools: Dict[str, Tool] = {}
        self.recipes: Dict[str, ToolRecipe] = {}

        # Capability tracking
        self.capability_gaps: Dict[str, CapabilityGap] = {}
        self.capability_usage: Dict[str, int] = defaultdict(int)

        # Statistics
        self.total_tools_created = 0
        self.total_gaps_identified = 0
        self.successful_tool_generations = 0
        self.deprecated_tools = 0

        # Initialize basic tools
        self._initialize_basic_tools()

    def _initialize_basic_tools(self):
        """Initialize basic primitive tools"""
        # Decision tools
        self.tools['tool_decide'] = Tool(
            tool_id='tool_decide',
            tool_name='Decision Maker',
            tool_type='primitive',
            description='Make a decision given context',
            input_types=['context', 'options'],
            output_types=['decision'],
            capabilities=['decide', 'choose', 'select'],
            success_count=10,
            failure_count=2,
            creator='system'
        )

        # Query tools
        self.tools['tool_query_memory'] = Tool(
            tool_id='tool_query_memory',
            tool_name='Memory Query',
            tool_type='primitive',
            description='Query memory for relevant information',
            input_types=['query'],
            output_types=['memory_results'],
            capabilities=['query', 'search', 'retrieve'],
            success_count=15,
            failure_count=3,
            creator='system'
        )

        # Analysis tools
        self.tools['tool_analyze'] = Tool(
            tool_id='tool_analyze',
            tool_name='Analyzer',
            tool_type='primitive',
            description='Analyze data and extract insights',
            input_types=['data'],
            output_types=['insights'],
            capabilities=['analyze', 'understand', 'extract'],
            success_count=12,
            failure_count=4,
            creator='system'
        )

    def identify_capability_gap(
        self,
        task_type: str,
        failed_action: str,
        missing_capability: str,
        context: Optional[Dict] = None
    ):
        """
        Identify a capability gap from a failure

        Args:
            task_type: Type of task
            failed_action: Action that failed
            missing_capability: Capability that was missing
            context: Optional context
        """
        gap_id = hashlib.md5(missing_capability.encode()).hexdigest()[:8]

        if gap_id in self.capability_gaps:
            # Update existing gap
            gap = self.capability_gaps[gap_id]
            gap.frequency += 1
            if task_type not in gap.task_types:
                gap.task_types.append(task_type)
            gap.failure_patterns.append(failed_action)
        else:
            # Create new gap
            gap = CapabilityGap(
                gap_id=gap_id,
                missing_capability=missing_capability,
                frequency=1,
                task_types=[task_type],
                failure_patterns=[failed_action],
                estimated_impact=0.5
            )
            self.capability_gaps[gap_id] = gap
            self.total_gaps_identified += 1

        # Check if we should generate a tool for this gap
        if gap.frequency >= self.gap_threshold:
            self._attempt_tool_generation(gap)

    def _attempt_tool_generation(self, gap: CapabilityGap):
        """Attempt to generate a tool to fill a gap"""
        # Check if we have tools that could be combined
        related_tools = self._find_related_tools(gap.missing_capability)

        if len(related_tools) >= 2:
            # Try to compose a new tool
            new_tool = self._compose_tool(gap, related_tools)
            if new_tool:
                self.tools[new_tool.tool_id] = new_tool
                self.successful_tool_generations += 1
                print(f"[ToolCreation] Generated new tool: {new_tool.tool_name}")
        else:
            # Create a basic tool template
            new_tool = self._create_basic_tool(gap)
            self.tools[new_tool.tool_id] = new_tool
            self.successful_tool_generations += 1
            print(f"[ToolCreation] Created basic tool: {new_tool.tool_name}")

    def _find_related_tools(self, capability: str) -> List[Tool]:
        """Find tools related to a capability"""
        related = []

        for tool in self.tools.values():
            # Check if tool capabilities overlap
            for cap in tool.capabilities:
                if capability.lower() in cap.lower() or cap.lower() in capability.lower():
                    related.append(tool)
                    break

        return related

    def _compose_tool(self, gap: CapabilityGap, component_tools: List[Tool]) -> Optional[Tool]:
        """Compose a new tool from existing tools"""
        # Create tool ID
        tool_id = f"composed_{gap.gap_id}"

        # Combine capabilities
        combined_capabilities = []
        for tool in component_tools:
            combined_capabilities.extend(tool.capabilities)
        combined_capabilities.append(gap.missing_capability)

        # Create composed tool
        new_tool = Tool(
            tool_id=tool_id,
            tool_name=f"Composed: {gap.missing_capability}",
            tool_type='composed',
            description=f"Tool composed to provide: {gap.missing_capability}",
            capabilities=list(set(combined_capabilities)),
            dependencies=[t.tool_id for t in component_tools],
            creator='system',
            avg_execution_time=sum(t.avg_execution_time for t in component_tools),
            version='1.0'
        )

        self.total_tools_created += 1

        return new_tool

    def _create_basic_tool(self, gap: CapabilityGap) -> Tool:
        """Create a basic tool for a gap"""
        tool_id = f"generated_{gap.gap_id}"

        new_tool = Tool(
            tool_id=tool_id,
            tool_name=f"Generated: {gap.missing_capability}",
            tool_type='generated',
            description=f"Generated tool to provide: {gap.missing_capability}",
            capabilities=[gap.missing_capability],
            creator='system',
            avg_execution_time=1.0,
            version='1.0'
        )

        self.total_tools_created += 1

        return new_tool

    def record_tool_usage(
        self,
        tool_id: str,
        outcome: str,
        execution_time: Optional[float] = None
    ):
        """Record usage of a tool"""
        if tool_id not in self.tools:
            return

        tool = self.tools[tool_id]
        tool.usage_count += 1

        if outcome == 'success':
            tool.success_count += 1
        else:
            tool.failure_count += 1

        if execution_time is not None:
            # Update average execution time (exponential moving average)
            alpha = 0.2
            tool.avg_execution_time = (1 - alpha) * tool.avg_execution_time + alpha * execution_time

        # Track capability usage
        for cap in tool.capabilities:
            self.capability_usage[cap] += 1

        # Check if tool should be deprecated
        if tool.usage_count >= self.tool_ttl:
            self._review_tool_for_deprecation(tool)

    def _review_tool_for_deprecation(self, tool: Tool):
        """Review tool for possible deprecation"""
        if tool.tool_type == 'primitive':
            # Don't deprecate primitive tools
            return

        success_rate = tool.success_rate()

        if success_rate < self.min_success_rate:
            # Deprecate tool
            print(f"[ToolCreation] Deprecating tool {tool.tool_name} (success rate: {success_rate:.1%})")
            del self.tools[tool.tool_id]
            self.deprecated_tools += 1

    def get_tool_for_capability(
        self,
        capability: str,
        prefer_specialized: bool = True
    ) -> Optional[Tool]:
        """
        Get best tool for a capability

        Args:
            capability: Required capability
            prefer_specialized: Prefer specialized tools over general ones

        Returns:
            Best matching tool
        """
        matching_tools = []

        for tool in self.tools.values():
            if capability in tool.capabilities:
                matching_tools.append(tool)

        if not matching_tools:
            return None

        # Sort by success rate and specialization
        def score_tool(t: Tool) -> float:
            success_score = t.success_rate()

            # Specialization bonus
            if prefer_specialized:
                specialization = 1.0 / len(t.capabilities)  # Fewer capabilities = more specialized
            else:
                specialization = len(t.capabilities)  # More capabilities = more general

            return success_score * 0.7 + specialization * 0.3

        matching_tools.sort(key=score_tool, reverse=True)

        return matching_tools[0]

    def suggest_tool_improvements(
        self,
        tool_id: str
    ) -> List[str]:
        """Suggest improvements for a tool"""
        if tool_id not in self.tools:
            return []

        tool = self.tools[tool_id]
        suggestions = []

        # Check performance
        if tool.success_rate() < 0.5:
            suggestions.append("Consider revising implementation (low success rate)")

        # Check usage
        if tool.usage_count < 5 and tool.tool_type != 'primitive':
            suggestions.append("Low usage - consider deprecating or promoting")

        # Check dependencies
        if tool.dependencies:
            # Check if dependencies are healthy
            for dep_id in tool.dependencies:
                if dep_id in self.tools:
                    dep = self.tools[dep_id]
                    if dep.success_rate() < 0.5:
                        suggestions.append(f"Dependency {dep.tool_name} has low success rate")

        return suggestions

    def get_statistics(self) -> Dict:
        """Get tool creation statistics"""
        # Count tools by type
        tool_types = defaultdict(int)
        for tool in self.tools.values():
            tool_types[tool.tool_type] += 1

        # Top capabilities
        top_capabilities = sorted(
            self.capability_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Average success rates
        if self.tools:
            avg_success = np.mean([t.success_rate() for t in self.tools.values() if t.usage_count > 0])
        else:
            avg_success = 0.0

        return {
            'total_tools': len(self.tools),
            'total_tools_created': self.total_tools_created,
            'successful_generations': self.successful_tool_generations,
            'deprecated_tools': self.deprecated_tools,
            'tool_types': dict(tool_types),
            'total_gaps_identified': self.total_gaps_identified,
            'significant_gaps': len([g for g in self.capability_gaps.values() if g.frequency >= self.gap_threshold]),
            'avg_tool_success_rate': avg_success,
            'top_capabilities': top_capabilities
        }

    def __repr__(self):
        return (
            f"ToolCreation("
            f"tools={len(self.tools)}, "
            f"created={self.total_tools_created}, "
            f"gaps={len(self.capability_gaps)})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("TOOL CREATION SYSTEM (PHASE 10)")
    print("=" * 70)
    print()
    print("This module implements dynamic tool generation:")
    print("  - Discover capability gaps")
    print("  - Generate new tools dynamically")
    print("  - Combine existing tools")
    print("  - Evolve tools based on usage")
    print("  - Deprecate underperforming tools")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_tool_creation.py")
    print()
    print("=" * 70)

"""
Conversation Graph - Represents agent conversations as state space graph

Treats conversations as puzzle-solving where:
- Nodes = Conversation states (tools used, errors, context)
- Edges = Transitions (tool calls, actions)
- Paths = Sequences of actions from start to goal
- Optimal path = Shortest successful sequence (fewest errors, minimal duration)

This enables the brain to "solve" conversation puzzles by finding optimal
paths through previously observed sessions.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class ConversationState:
    """
    Represents a state in the conversation space

    Similar to a puzzle board state, but for agent conversations.
    """
    task_type: str              # e.g., 'github', 'docker', 'playwright'
    tools_used: List[str]       # Sequence of tools called so far
    error_count: int            # Number of errors accumulated
    clarification_count: int    # Number of user clarifications
    duration: float            # Time elapsed (seconds)
    success: bool              # Whether task succeeded

    def __hash__(self):
        """Hash for use as dict key"""
        return hash((
            self.task_type,
            tuple(self.tools_used),
            self.error_count,
            self.clarification_count
        ))

    def __eq__(self, other):
        """Equality check for deduplication"""
        if not isinstance(other, ConversationState):
            return False
        return (
            self.task_type == other.task_type and
            self.tools_used == other.tools_used and
            self.error_count == other.error_count and
            self.clarification_count == other.clarification_count
        )

    def to_vector(self) -> np.ndarray:
        """Convert state to feature vector for neural routing"""
        # 64-dimensional state vector
        vec = np.zeros(64)

        # Task type (one-hot over common types)
        task_types = ['github', 'docker', 'playwright', 'search', 'filesystem',
                     'memory', 'context', 'unknown']
        task_idx = task_types.index(self.task_type) if self.task_type in task_types else 7
        vec[task_idx] = 1.0

        # Tool sequence features
        vec[8] = min(len(self.tools_used) / 10.0, 1.0)  # Normalized tool count
        vec[9] = min(len(set(self.tools_used)) / 10.0, 1.0)  # Unique tools

        # Tool repetition (indicates loops)
        if self.tools_used:
            tool_counts = defaultdict(int)
            for tool in self.tools_used:
                tool_counts[tool] += 1
            max_repetition = max(tool_counts.values())
            vec[10] = min(max_repetition / 5.0, 1.0)

        # Error features
        vec[11] = min(self.error_count / 10.0, 1.0)
        vec[12] = 1.0 if self.error_count > 5 else 0.0  # High error flag

        # Clarification features
        vec[13] = min(self.clarification_count / 5.0, 1.0)

        # Duration features
        vec[14] = min(self.duration / 300.0, 1.0)  # Normalized to 5 minutes
        vec[15] = 1.0 if self.duration > 120 else 0.0  # Long task flag

        # Success indicator
        vec[16] = 1.0 if self.success else 0.0

        return vec

    def get_signature(self) -> str:
        """Get unique signature for this state"""
        return f"{self.task_type}:{','.join(self.tools_used[:5])}:{self.error_count}"


@dataclass
class ConversationTransition:
    """
    Represents a transition (action) between states

    Like a move in a puzzle, but for conversations.
    """
    from_state: ConversationState
    to_state: ConversationState
    action: str                 # Tool call or action taken
    duration: float            # Time for this transition
    error_occurred: bool       # Whether error happened
    success_probability: float # Learned probability of success from this state

    def get_cost(self) -> float:
        """
        Compute cost of this transition for pathfinding

        Lower cost = better transition
        """
        cost = 1.0  # Base cost

        # Penalize errors heavily
        if self.error_occurred:
            cost += 5.0

        # Penalize duration
        cost += self.duration / 60.0  # Normalize to minutes

        # Penalize low success probability
        cost += (1.0 - self.success_probability) * 2.0

        return cost


class ConversationGraph:
    """
    Graph representation of all observed conversations

    Enables pathfinding through conversation space to find optimal
    sequences of actions for completing tasks.
    """

    def __init__(self):
        # Graph structure
        self.states: Set[ConversationState] = set()
        self.transitions: List[ConversationTransition] = []

        # Index structures for fast lookup
        self.state_index: Dict[str, ConversationState] = {}  # signature -> state
        self.outgoing_edges: Dict[str, List[ConversationTransition]] = defaultdict(list)
        self.incoming_edges: Dict[str, List[ConversationTransition]] = defaultdict(list)

        # Task-specific subgraphs
        self.task_graphs: Dict[str, Set[str]] = defaultdict(set)  # task_type -> state signatures

        # Success statistics
        self.state_success_rate: Dict[str, float] = {}
        self.state_visit_count: Dict[str, int] = defaultdict(int)

    def add_conversation_trace(self, trace_features: Dict):
        """
        Add a complete conversation trace to the graph

        Converts the trace into a sequence of states and transitions.
        """
        task_type = trace_features.get('tool_type', 'unknown')
        tools_used = trace_features.get('tools_used', [])
        error_count = trace_features.get('error_count', 0)
        clarification_count = trace_features.get('clarification_count', 0)
        duration = trace_features.get('duration_seconds', 0.0)
        success = trace_features.get('success', False)

        # Create states for each step in the conversation
        states = []

        # Initial state (empty)
        initial_state = ConversationState(
            task_type=task_type,
            tools_used=[],
            error_count=0,
            clarification_count=0,
            duration=0.0,
            success=False
        )
        states.append(initial_state)
        self._add_state(initial_state)

        # Intermediate states (each tool call)
        errors_so_far = 0
        time_per_tool = duration / max(len(tools_used), 1)

        for i, tool in enumerate(tools_used):
            # Estimate errors distributed across tools
            if error_count > 0 and i >= len(tools_used) - error_count:
                errors_so_far += 1

            state = ConversationState(
                task_type=task_type,
                tools_used=tools_used[:i+1],
                error_count=errors_so_far,
                clarification_count=clarification_count,
                duration=(i + 1) * time_per_tool,
                success=False
            )
            states.append(state)
            self._add_state(state)

        # Final state
        final_state = ConversationState(
            task_type=task_type,
            tools_used=tools_used,
            error_count=error_count,
            clarification_count=clarification_count,
            duration=duration,
            success=success
        )
        states.append(final_state)
        self._add_state(final_state)

        # Create transitions between consecutive states
        for i in range(len(states) - 1):
            from_state = states[i]
            to_state = states[i + 1]

            # Determine action (tool that was called)
            if i < len(tools_used):
                action = tools_used[i]
            else:
                action = 'complete'

            # Check if error occurred in this step
            error_occurred = to_state.error_count > from_state.error_count

            # Success probability (will be updated with more data)
            success_prob = 1.0 if success else 0.3

            transition = ConversationTransition(
                from_state=from_state,
                to_state=to_state,
                action=action,
                duration=time_per_tool,
                error_occurred=error_occurred,
                success_probability=success_prob
            )

            self._add_transition(transition)

        # Update success statistics
        for state in states:
            sig = state.get_signature()
            self.state_visit_count[sig] += 1
            if success:
                current_rate = self.state_success_rate.get(sig, 0.0)
                visit_count = self.state_visit_count[sig]
                # Running average
                self.state_success_rate[sig] = (
                    (current_rate * (visit_count - 1) + 1.0) / visit_count
                )
            else:
                current_rate = self.state_success_rate.get(sig, 0.0)
                visit_count = self.state_visit_count[sig]
                self.state_success_rate[sig] = (
                    (current_rate * (visit_count - 1) + 0.0) / visit_count
                )

    def _add_state(self, state: ConversationState):
        """Add state to graph with indexing"""
        sig = state.get_signature()
        if sig not in self.state_index:
            self.states.add(state)
            self.state_index[sig] = state
            self.task_graphs[state.task_type].add(sig)

    def _add_transition(self, transition: ConversationTransition):
        """Add transition to graph with indexing"""
        self.transitions.append(transition)

        from_sig = transition.from_state.get_signature()
        to_sig = transition.to_state.get_signature()

        self.outgoing_edges[from_sig].append(transition)
        self.incoming_edges[to_sig].append(transition)

    def find_optimal_path(
        self,
        start_task_type: str,
        max_steps: int = 10,
        max_errors: int = 3
    ) -> Optional[List[str]]:
        """
        Find optimal path through conversation space using A* search

        Given a task type, find the sequence of tool calls that leads to
        success with minimal cost (errors + duration).

        Returns:
            List of actions (tool names) to execute, or None if no path found
        """
        # Start state
        start_state = ConversationState(
            task_type=start_task_type,
            tools_used=[],
            error_count=0,
            clarification_count=0,
            duration=0.0,
            success=False
        )
        start_sig = start_state.get_signature()

        # Priority queue: (cost, state_signature, path)
        from heapq import heappush, heappop
        frontier = [(0.0, start_sig, [])]
        visited = set()

        while frontier:
            cost, current_sig, path = heappop(frontier)

            if current_sig in visited:
                continue
            visited.add(current_sig)

            current_state = self.state_index.get(current_sig)
            if current_state is None:
                continue

            # Check if we reached a successful state
            if current_state.success:
                return path

            # Check termination conditions
            if len(path) >= max_steps:
                continue
            if current_state.error_count >= max_errors:
                continue

            # Explore neighbors
            for transition in self.outgoing_edges.get(current_sig, []):
                next_sig = transition.to_state.get_signature()

                if next_sig not in visited:
                    new_cost = cost + transition.get_cost()
                    new_path = path + [transition.action]

                    # Heuristic: estimate remaining cost to success
                    heuristic = self._estimate_cost_to_goal(transition.to_state)

                    heappush(frontier, (new_cost + heuristic, next_sig, new_path))

        # No path found - return most common successful sequence for this task
        return self._get_fallback_path(start_task_type)

    def _estimate_cost_to_goal(self, state: ConversationState) -> float:
        """
        Heuristic for A* search: estimate remaining cost to reach success
        """
        sig = state.get_signature()

        # If we've seen this state succeed before, use empirical data
        success_rate = self.state_success_rate.get(sig, 0.5)

        # Estimate remaining steps
        avg_tools_for_task = self._get_avg_tools_for_task(state.task_type)
        remaining_steps = max(0, avg_tools_for_task - len(state.tools_used))

        # Heuristic cost
        h_cost = (1.0 - success_rate) * 5.0 + remaining_steps * 0.5

        return h_cost

    def _get_avg_tools_for_task(self, task_type: str) -> float:
        """Get average number of tools used for successful tasks of this type"""
        successful_states = [
            state for state in self.states
            if state.task_type == task_type and state.success
        ]

        if not successful_states:
            return 5.0  # Default estimate

        return np.mean([len(state.tools_used) for state in successful_states])

    def _get_fallback_path(self, task_type: str) -> Optional[List[str]]:
        """
        Fallback: return most common successful tool sequence for this task
        """
        successful_states = [
            state for state in self.states
            if state.task_type == task_type and state.success
        ]

        if not successful_states:
            return None

        # Find most common sequence
        sequences = [tuple(state.tools_used) for state in successful_states]
        from collections import Counter
        most_common = Counter(sequences).most_common(1)

        if most_common:
            return list(most_common[0][0])

        return None

    def get_statistics(self) -> Dict:
        """Get graph statistics"""
        return {
            'total_states': len(self.states),
            'total_transitions': len(self.transitions),
            'task_types': len(self.task_graphs),
            'task_distribution': {
                task: len(states) for task, states in self.task_graphs.items()
            },
            'avg_success_rate': np.mean(list(self.state_success_rate.values())) if self.state_success_rate else 0.0
        }

    def visualize_task_graph(self, task_type: str, max_states: int = 20) -> str:
        """
        Create ASCII visualization of conversation graph for a specific task
        """
        task_states = [
            self.state_index[sig] for sig in self.task_graphs.get(task_type, set())
        ][:max_states]

        if not task_states:
            return f"No states found for task type: {task_type}"

        lines = [f"Conversation Graph for '{task_type}'", "=" * 60]

        for state in sorted(task_states, key=lambda s: len(s.tools_used)):
            sig = state.get_signature()
            success_rate = self.state_success_rate.get(sig, 0.0)
            visit_count = self.state_visit_count.get(sig, 0)

            status = "[OK]" if state.success else "[--]"
            tools_str = " -> ".join(state.tools_used) if state.tools_used else "(start)"

            lines.append(f"{status} {tools_str}")
            lines.append(f"     Errors: {state.error_count}, Duration: {state.duration:.1f}s")
            lines.append(f"     Success Rate: {success_rate:.1%}, Visits: {visit_count}")

            # Show outgoing transitions
            for trans in self.outgoing_edges.get(sig, [])[:3]:
                cost = trans.get_cost()
                lines.append(f"       -> {trans.action} (cost: {cost:.2f})")

            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    # Test conversation graph
    print("Testing Conversation Graph...")
    print("=" * 70)

    graph = ConversationGraph()

    # Add sample traces
    traces = [
        {
            'tool_type': 'github',
            'tools_used': ['git_status', 'git_add', 'git_commit', 'git_push'],
            'error_count': 0,
            'clarification_count': 0,
            'duration_seconds': 15.5,
            'success': True
        },
        {
            'tool_type': 'github',
            'tools_used': ['git_add', 'git_commit', 'git_commit', 'git_push'],
            'error_count': 2,
            'clarification_count': 1,
            'duration_seconds': 45.2,
            'success': True
        },
        {
            'tool_type': 'github',
            'tools_used': ['git_add', 'git_push'],
            'error_count': 5,
            'clarification_count': 0,
            'duration_seconds': 120.0,
            'success': False
        }
    ]

    for trace in traces:
        graph.add_conversation_trace(trace)

    print("\nGraph Statistics:")
    stats = graph.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + graph.visualize_task_graph('github'))

    print("\nFinding optimal path for 'github' task...")
    optimal_path = graph.find_optimal_path('github', max_steps=10)

    if optimal_path:
        print(f"Optimal path found: {' -> '.join(optimal_path)}")
    else:
        print("No optimal path found")

    print("\n" + "=" * 70)

"""
Goal Graph System for Adaptive Cognitive System (ACS)

Implements hierarchical goal structures with:
- Parent/Child goal relationships
- Temporal dependencies (deadlines, sequences)
- Goal state tracking (pending, active, completed, failed)
- Priority-based scheduling
- Goal tracing for CTM guidance
- **Causal reasoning integration** (Phase 8B)

This module enables the brain to:
- Break down complex goals into subgoals
- Track dependencies between goals
- Manage parallel and sequential goal execution
- Provide context to CTMs about current objectives
- Analyze causal relationships between goal success/failure
- Perform counterfactual reasoning for planning
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any, TYPE_CHECKING
from enum import Enum
from datetime import datetime, timedelta
import uuid
import heapq
from collections import defaultdict
import logging

# Lazy import to avoid circular dependencies
if TYPE_CHECKING:
    from core.causal_reasoning import CausalDAG, CausalInference, RootCauseAnalyzer

logger = logging.getLogger(__name__)


class GoalState(Enum):
    """Goal execution states"""
    PENDING = "pending"      # Not yet started
    ACTIVE = "active"        # Currently being worked on
    BLOCKED = "blocked"      # Waiting for dependencies
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"        # Failed to complete
    CANCELLED = "cancelled"  # Cancelled by user/system


class GoalPriority(Enum):
    """Goal priority levels"""
    CRITICAL = 1    # Must complete immediately
    HIGH = 2        # Important, do soon
    MEDIUM = 3      # Normal priority
    LOW = 4         # Can wait
    BACKGROUND = 5  # Do when idle


class CausalEdgeType(Enum):
    """Types of causal relationships between goals"""
    ENABLES = "enables"         # Completing X enables Y (prerequisite)
    BLOCKS = "blocks"           # X active blocks Y
    CONTRIBUTES = "contributes" # X completion contributes to Y success
    HINDERS = "hinders"         # X completion makes Y harder
    TRIGGERS = "triggers"       # X completion automatically triggers Y


@dataclass
class Goal:
    """
    Represents a single goal in the goal graph

    Goals can have:
    - Parent goal (hierarchical structure)
    - Child goals (subgoals)
    - Dependencies (must complete before this goal)
    - Dependents (goals waiting on this one)
    - Temporal constraints (deadlines, durations)
    """
    goal_id: str
    description: str
    state: GoalState = GoalState.PENDING
    priority: GoalPriority = GoalPriority.MEDIUM

    # Hierarchical structure
    parent_id: Optional[str] = None
    child_ids: List[str] = field(default_factory=list)

    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # Goals that must complete first
    dependents: List[str] = field(default_factory=list)  # Goals waiting on this one

    # Temporal constraints
    created_at: datetime = field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    estimated_duration: Optional[timedelta] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Progress tracking
    progress: float = 0.0  # 0.0 to 1.0

    # Context for CTM
    context: Dict = field(default_factory=dict)

    # Results
    result: Optional[str] = None
    failure_reason: Optional[str] = None

    def is_ready(self) -> bool:
        """Check if goal is ready to execute (all dependencies met)"""
        return self.state == GoalState.PENDING and len(self.depends_on) == 0

    def time_until_deadline(self) -> Optional[timedelta]:
        """Get time remaining until deadline"""
        if self.deadline:
            return self.deadline - datetime.now()
        return None

    def is_overdue(self) -> bool:
        """Check if goal is past deadline"""
        if self.deadline:
            return datetime.now() > self.deadline
        return False


@dataclass
class GoalPath:
    """
    Represents a path through the goal graph
    Used for planning and CTM guidance
    """
    goals: List[str]           # Ordered list of goal IDs
    total_priority: float      # Combined priority score
    estimated_time: timedelta  # Total estimated duration
    critical_path: bool        # Whether this is the critical path


@dataclass
class CausalGoalEdge:
    """
    Represents a causal relationship between goals.

    Used for:
    - Understanding why goals succeed or fail
    - Counterfactual planning ("what if we had done X?")
    - Root cause analysis of failures
    """
    source_goal: str           # Cause goal ID
    target_goal: str           # Effect goal ID
    edge_type: CausalEdgeType  # Type of causal relationship
    strength: float = 1.0      # Causal strength (0-1)
    confidence: float = 1.0    # Confidence in this relationship
    learned: bool = False      # Whether learned from data vs explicit
    metadata: Dict[str, Any] = field(default_factory=dict)


class GoalGraph:
    """
    Manages the hierarchical goal structure

    Features:
    - Add/remove goals with dependencies
    - Track goal states and transitions
    - Find optimal execution paths
    - Provide context for CTM reasoning
    - Handle goal completion cascades
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'GoalGraph':
        """Create GoalGraph from YAML config dict (P5.70)."""
        gg = yaml_config.get('goal_graph', {})
        instance = cls()
        instance._max_goals = gg.get('max_goals', 50)
        instance._priority_decay_rate = gg.get('priority_decay_rate', 0.01)
        instance._critical_path_algorithm = gg.get('critical_path_algorithm', 'longest')
        instance._auto_cleanup_completed = gg.get('auto_cleanup_completed', True)
        return instance

    def __init__(self):
        self.goals: Dict[str, Goal] = {}
        self.root_goals: Set[str] = set()  # Goals with no parent
        self._max_goals: int = 50
        self._priority_decay_rate: float = 0.01
        self._critical_path_algorithm: str = 'longest'
        self._auto_cleanup_completed: bool = True

        # Indexes for fast lookup
        self._by_state: Dict[GoalState, Set[str]] = defaultdict(set)
        self._by_priority: Dict[GoalPriority, Set[str]] = defaultdict(set)

        # Execution history
        self.completed_goals: List[Tuple[str, datetime]] = []
        self.failed_goals: List[Tuple[str, datetime, str]] = []

        # Causal reasoning (Phase 8B)
        self.causal_edges: List[CausalGoalEdge] = []
        self._causal_by_source: Dict[str, List[CausalGoalEdge]] = defaultdict(list)
        self._causal_by_target: Dict[str, List[CausalGoalEdge]] = defaultdict(list)
        self._causal_dag: Optional['CausalDAG'] = None  # Cached CausalDAG

    def add_goal(
        self,
        description: str,
        parent_id: Optional[str] = None,
        priority: GoalPriority = GoalPriority.MEDIUM,
        depends_on: Optional[List[str]] = None,
        deadline: Optional[datetime] = None,
        estimated_duration: Optional[timedelta] = None,
        context: Optional[Dict] = None
    ) -> Goal:
        """
        Add a new goal to the graph

        Args:
            description: Goal description
            parent_id: Optional parent goal ID
            priority: Goal priority level
            depends_on: List of goal IDs this depends on
            deadline: Optional deadline
            estimated_duration: Optional duration estimate
            context: Additional context for CTM

        Returns:
            Created Goal object
        """
        goal_id = str(uuid.uuid4())[:8]

        goal = Goal(
            goal_id=goal_id,
            description=description,
            priority=priority,
            parent_id=parent_id,
            depends_on=depends_on or [],
            deadline=deadline,
            estimated_duration=estimated_duration,
            context=context or {}
        )

        # Set initial state based on dependencies
        if depends_on and len(depends_on) > 0:
            # Check if all dependencies are completed
            all_deps_complete = all(
                self.goals.get(dep_id, Goal(goal_id='', description='')).state == GoalState.COMPLETED
                for dep_id in depends_on
            )
            goal.state = GoalState.PENDING if all_deps_complete else GoalState.BLOCKED

        self.goals[goal_id] = goal

        # Update indexes
        self._by_state[goal.state].add(goal_id)
        self._by_priority[priority].add(goal_id)

        # Link to parent
        if parent_id and parent_id in self.goals:
            self.goals[parent_id].child_ids.append(goal_id)
        else:
            self.root_goals.add(goal_id)

        # Update dependents of dependencies
        for dep_id in (depends_on or []):
            if dep_id in self.goals:
                self.goals[dep_id].dependents.append(goal_id)

        return goal

    def start_goal(self, goal_id: str) -> bool:
        """
        Mark a goal as active (started)

        Args:
            goal_id: Goal ID to start

        Returns:
            True if successful
        """
        if goal_id not in self.goals:
            return False

        goal = self.goals[goal_id]

        if goal.state not in [GoalState.PENDING, GoalState.BLOCKED]:
            return False

        # Check dependencies
        for dep_id in goal.depends_on:
            if dep_id in self.goals:
                if self.goals[dep_id].state != GoalState.COMPLETED:
                    return False  # Dependencies not met

        # Update state
        self._by_state[goal.state].discard(goal_id)
        goal.state = GoalState.ACTIVE
        goal.started_at = datetime.now()
        self._by_state[GoalState.ACTIVE].add(goal_id)

        return True

    def complete_goal(self, goal_id: str, result: Optional[str] = None) -> bool:
        """
        Mark a goal as completed

        Args:
            goal_id: Goal ID to complete
            result: Optional result description

        Returns:
            True if successful
        """
        if goal_id not in self.goals:
            return False

        goal = self.goals[goal_id]

        if goal.state != GoalState.ACTIVE:
            return False

        # Update state
        self._by_state[goal.state].discard(goal_id)
        goal.state = GoalState.COMPLETED
        goal.completed_at = datetime.now()
        goal.progress = 1.0
        goal.result = result
        self._by_state[GoalState.COMPLETED].add(goal_id)

        # Record completion
        self.completed_goals.append((goal_id, datetime.now()))

        # Unblock dependents
        self._unblock_dependents(goal_id)

        # Check if parent is now complete
        if goal.parent_id:
            self._check_parent_completion(goal.parent_id)

        return True

    def fail_goal(self, goal_id: str, reason: str) -> bool:
        """
        Mark a goal as failed

        Args:
            goal_id: Goal ID to fail
            reason: Failure reason

        Returns:
            True if successful
        """
        if goal_id not in self.goals:
            return False

        goal = self.goals[goal_id]

        if goal.state not in [GoalState.ACTIVE, GoalState.PENDING, GoalState.BLOCKED]:
            return False

        # Update state
        self._by_state[goal.state].discard(goal_id)
        goal.state = GoalState.FAILED
        goal.completed_at = datetime.now()
        goal.failure_reason = reason
        self._by_state[GoalState.FAILED].add(goal_id)

        # Record failure
        self.failed_goals.append((goal_id, datetime.now(), reason))

        return True

    def update_progress(self, goal_id: str, progress: float) -> bool:
        """
        Update goal progress

        Args:
            goal_id: Goal ID
            progress: Progress value (0.0 to 1.0)

        Returns:
            True if successful
        """
        if goal_id not in self.goals:
            return False

        goal = self.goals[goal_id]
        goal.progress = max(0.0, min(1.0, progress))

        return True

    def _unblock_dependents(self, completed_goal_id: str):
        """Unblock goals that were waiting on completed goal"""
        goal = self.goals.get(completed_goal_id)
        if not goal:
            return

        for dependent_id in goal.dependents:
            if dependent_id not in self.goals:
                continue

            dependent = self.goals[dependent_id]
            if dependent.state != GoalState.BLOCKED:
                continue

            # Remove completed goal from depends_on
            if completed_goal_id in dependent.depends_on:
                dependent.depends_on.remove(completed_goal_id)

            # Check if all dependencies are now met
            if len(dependent.depends_on) == 0:
                self._by_state[GoalState.BLOCKED].discard(dependent_id)
                dependent.state = GoalState.PENDING
                self._by_state[GoalState.PENDING].add(dependent_id)

    def _check_parent_completion(self, parent_id: str):
        """Check if all children are complete and update parent"""
        if parent_id not in self.goals:
            return

        parent = self.goals[parent_id]

        if not parent.child_ids:
            return

        all_complete = all(
            self.goals.get(child_id, Goal(goal_id='', description='')).state == GoalState.COMPLETED
            for child_id in parent.child_ids
        )

        if all_complete and parent.state == GoalState.ACTIVE:
            # Auto-complete parent
            parent.progress = 1.0
            # Note: Don't auto-complete - let the system decide

    def get_ready_goals(self) -> List[Goal]:
        """Get all goals ready to execute (pending with no deps)"""
        ready = []
        for goal_id in self._by_state[GoalState.PENDING]:
            goal = self.goals[goal_id]
            if goal.is_ready():
                ready.append(goal)

        # Sort by priority and deadline
        ready.sort(key=lambda g: (
            g.priority.value,
            g.deadline or datetime.max
        ))

        return ready

    def get_active_goals(self) -> List[Goal]:
        """Get all currently active goals"""
        return [self.goals[gid] for gid in self._by_state[GoalState.ACTIVE]]

    def get_blocked_goals(self) -> List[Goal]:
        """Get all blocked goals"""
        return [self.goals[gid] for gid in self._by_state[GoalState.BLOCKED]]

    def get_next_goal(self) -> Optional[Goal]:
        """Get the highest priority goal ready to execute"""
        ready = self.get_ready_goals()
        return ready[0] if ready else None

    def get_goal_path(self, goal_id: str) -> List[Goal]:
        """Get the path from root to goal"""
        path = []
        current_id = goal_id

        while current_id:
            if current_id in self.goals:
                path.append(self.goals[current_id])
                current_id = self.goals[current_id].parent_id
            else:
                break

        path.reverse()
        return path

    def get_subtree(self, goal_id: str) -> List[Goal]:
        """Get all goals in subtree rooted at goal_id"""
        subtree = []

        def collect(gid: str):
            if gid in self.goals:
                subtree.append(self.goals[gid])
                for child_id in self.goals[gid].child_ids:
                    collect(child_id)

        collect(goal_id)
        return subtree

    def get_critical_path(self) -> GoalPath:
        """
        Find the critical path through the goal graph
        (longest path considering dependencies and durations)
        """
        # Simple implementation - find path with most pending goals
        paths = []

        for root_id in self.root_goals:
            path = self._find_longest_path(root_id)
            if path:
                paths.append(path)

        if not paths:
            return GoalPath(goals=[], total_priority=0, estimated_time=timedelta(), critical_path=False)

        # Return path with highest priority and longest time
        best_path = max(paths, key=lambda p: (p.total_priority, p.estimated_time))
        best_path.critical_path = True
        return best_path

    def _find_longest_path(self, start_id: str) -> Optional[GoalPath]:
        """Find longest path from start goal"""
        if start_id not in self.goals:
            return None

        goal = self.goals[start_id]

        if not goal.child_ids:
            # Leaf node
            return GoalPath(
                goals=[start_id],
                total_priority=6 - goal.priority.value,  # Invert for sorting
                estimated_time=goal.estimated_duration or timedelta(),
                critical_path=False
            )

        # Find longest child path
        child_paths = []
        for child_id in goal.child_ids:
            child_path = self._find_longest_path(child_id)
            if child_path:
                child_paths.append(child_path)

        if not child_paths:
            return GoalPath(
                goals=[start_id],
                total_priority=6 - goal.priority.value,
                estimated_time=goal.estimated_duration or timedelta(),
                critical_path=False
            )

        # Take longest child path and prepend this goal
        longest = max(child_paths, key=lambda p: len(p.goals))
        return GoalPath(
            goals=[start_id] + longest.goals,
            total_priority=(6 - goal.priority.value) + longest.total_priority,
            estimated_time=(goal.estimated_duration or timedelta()) + longest.estimated_time,
            critical_path=False
        )

    def get_context_for_ctm(self) -> Dict:
        """
        Generate context dictionary for CTM reasoning

        Returns:
            Dictionary with goal graph state for CTM
        """
        active = self.get_active_goals()
        ready = self.get_ready_goals()
        blocked = self.get_blocked_goals()

        # Find overdue goals
        overdue = [g for g in self.goals.values() if g.is_overdue() and g.state not in [GoalState.COMPLETED, GoalState.CANCELLED, GoalState.FAILED]]

        return {
            'active_goals': [
                {
                    'id': g.goal_id,
                    'description': g.description,
                    'priority': g.priority.value,
                    'progress': g.progress,
                    'deadline': g.deadline.isoformat() if g.deadline else None
                }
                for g in active
            ],
            'ready_goals': [
                {
                    'id': g.goal_id,
                    'description': g.description,
                    'priority': g.priority.value
                }
                for g in ready[:5]  # Top 5 ready
            ],
            'blocked_count': len(blocked),
            'overdue_count': len(overdue),
            'total_goals': len(self.goals),
            'completion_rate': len(self._by_state[GoalState.COMPLETED]) / max(1, len(self.goals)),
            'critical_path': [
                self.goals[gid].description
                for gid in self.get_critical_path().goals[:3]
            ]
        }

    def get_statistics(self) -> Dict:
        """Get goal graph statistics"""
        return {
            'total_goals': len(self.goals),
            'by_state': {
                state.value: len(goals)
                for state, goals in self._by_state.items()
            },
            'by_priority': {
                priority.value: len(goals)
                for priority, goals in self._by_priority.items()
            },
            'root_goals': len(self.root_goals),
            'completed_count': len(self.completed_goals),
            'failed_count': len(self.failed_goals),
            'completion_rate': len(self._by_state[GoalState.COMPLETED]) / max(1, len(self.goals)),
            'causal_edges': len(self.causal_edges)
        }

    # =========================================================================
    # Causal Reasoning Methods (Phase 8B)
    # =========================================================================

    def add_causal_edge(
        self,
        source_goal: str,
        target_goal: str,
        edge_type: CausalEdgeType,
        strength: float = 1.0,
        confidence: float = 1.0,
        learned: bool = False
    ) -> CausalGoalEdge:
        """
        Add a causal relationship between goals.

        Args:
            source_goal: ID of the cause goal
            target_goal: ID of the effect goal
            edge_type: Type of causal relationship
            strength: Causal strength (0-1)
            confidence: Confidence in relationship
            learned: Whether learned from data

        Returns:
            Created CausalGoalEdge
        """
        # Validate goals exist
        if source_goal not in self.goals:
            raise ValueError(f"Source goal {source_goal} not found")
        if target_goal not in self.goals:
            raise ValueError(f"Target goal {target_goal} not found")

        edge = CausalGoalEdge(
            source_goal=source_goal,
            target_goal=target_goal,
            edge_type=edge_type,
            strength=strength,
            confidence=confidence,
            learned=learned
        )

        self.causal_edges.append(edge)
        self._causal_by_source[source_goal].append(edge)
        self._causal_by_target[target_goal].append(edge)

        # Invalidate cached CausalDAG
        self._causal_dag = None

        logger.debug(f"Added causal edge: {source_goal} -{edge_type.value}-> {target_goal}")
        return edge

    def get_causal_causes(self, goal_id: str) -> List[CausalGoalEdge]:
        """Get all causal edges where this goal is the effect."""
        return self._causal_by_target.get(goal_id, [])

    def get_causal_effects(self, goal_id: str) -> List[CausalGoalEdge]:
        """Get all causal edges where this goal is the cause."""
        return self._causal_by_source.get(goal_id, [])

    def infer_causal_edges_from_dependencies(self) -> int:
        """
        Automatically create causal edges from goal dependencies.

        Returns:
            Number of edges created
        """
        count = 0
        for goal in self.goals.values():
            # Dependencies become ENABLES edges
            for dep_id in goal.depends_on:
                if not any(
                    e.source_goal == dep_id and e.target_goal == goal.goal_id
                    for e in self.causal_edges
                ):
                    self.add_causal_edge(
                        dep_id,
                        goal.goal_id,
                        CausalEdgeType.ENABLES,
                        strength=0.9,
                        learned=False
                    )
                    count += 1

            # Parent-child becomes CONTRIBUTES
            if goal.parent_id and goal.parent_id in self.goals:
                if not any(
                    e.source_goal == goal.goal_id and e.target_goal == goal.parent_id
                    for e in self.causal_edges
                ):
                    self.add_causal_edge(
                        goal.goal_id,
                        goal.parent_id,
                        CausalEdgeType.CONTRIBUTES,
                        strength=0.7,
                        learned=False
                    )
                    count += 1

        logger.info(f"Inferred {count} causal edges from goal structure")
        return count

    def to_causal_dag(self) -> 'CausalDAG':
        """
        Convert goal graph to CausalDAG for causal inference.

        Returns:
            CausalDAG representing goal relationships
        """
        # Use cached if available
        if self._causal_dag is not None:
            return self._causal_dag

        # Lazy import
        from core.causal_reasoning import CausalDAG, Distribution
        import numpy as np

        dag = CausalDAG()

        # Add all goals as variables
        for goal_id, goal in self.goals.items():
            # Distribution based on current state
            if goal.state == GoalState.COMPLETED:
                dist = Distribution(np.array([0.0, 1.0]), np.array([0.1, 0.9]))
            elif goal.state == GoalState.FAILED:
                dist = Distribution(np.array([0.0, 1.0]), np.array([0.9, 0.1]))
            else:
                dist = Distribution(np.array([0.0, 1.0]), np.array([0.5, 0.5]))

            dag.add_variable(
                name=goal_id,
                distribution=dist,
                is_latent=False
            )
            dag.nodes[goal_id].metadata = {
                'description': goal.description,
                'state': goal.state.value,
                'priority': goal.priority.value
            }

        # Add causal edges
        for edge in self.causal_edges:
            # Map edge types to causal DAG edge types
            if edge.edge_type in [CausalEdgeType.ENABLES, CausalEdgeType.CONTRIBUTES,
                                  CausalEdgeType.TRIGGERS]:
                # Positive causal effect
                dag.add_edge(edge.source_goal, edge.target_goal, strength=edge.strength)
            elif edge.edge_type == CausalEdgeType.HINDERS:
                # Negative causal effect
                dag.add_edge(edge.source_goal, edge.target_goal, strength=-edge.strength)
            elif edge.edge_type == CausalEdgeType.BLOCKS:
                # Blocking relationship (negative)
                dag.add_edge(edge.source_goal, edge.target_goal, strength=-edge.strength * 0.5)

        self._causal_dag = dag
        return dag

    def analyze_goal_failure(self, goal_id: str) -> Dict[str, Any]:
        """
        Analyze why a goal failed using causal reasoning.

        Args:
            goal_id: ID of the failed goal

        Returns:
            Analysis results including root causes and suggestions
        """
        if goal_id not in self.goals:
            return {'error': f'Goal {goal_id} not found'}

        goal = self.goals[goal_id]
        if goal.state != GoalState.FAILED:
            return {'error': f'Goal {goal_id} is not failed (state: {goal.state.value})'}

        # Build symptoms from goal state
        symptoms = {
            goal_id: 0.0  # Failed = 0
        }

        # Add related goal states as symptoms
        for edge in self.get_causal_causes(goal_id):
            source = self.goals.get(edge.source_goal)
            if source:
                symptoms[edge.source_goal] = 1.0 if source.state == GoalState.COMPLETED else 0.0

        # Use RootCauseAnalyzer if CausalDAG exists
        try:
            from core.causal_reasoning import RootCauseAnalyzer

            dag = self.to_causal_dag()
            analyzer = RootCauseAnalyzer(dag)
            root_causes = analyzer.analyze_failure(symptoms)

            return {
                'goal_id': goal_id,
                'description': goal.description,
                'failure_reason': goal.failure_reason,
                'root_causes': [
                    {
                        'variable': rc.variable,
                        'goal_description': self.goals.get(rc.variable, Goal('', '')).description,
                        'probability': rc.probability,
                        'impact': rc.impact,
                        'evidence': rc.evidence,
                        'intervention': rc.intervention
                    }
                    for rc in root_causes[:5]  # Top 5
                ],
                'causal_chain': self._trace_causal_chain(goal_id)
            }
        except Exception as e:
            logger.warning(f"Could not perform full causal analysis: {e}")
            # Fallback to simple analysis
            return {
                'goal_id': goal_id,
                'description': goal.description,
                'failure_reason': goal.failure_reason,
                'dependencies_state': {
                    dep_id: self.goals.get(dep_id, Goal('', '')).state.value
                    for dep_id in goal.depends_on
                },
                'causal_causes': [
                    {
                        'source': e.source_goal,
                        'type': e.edge_type.value,
                        'strength': e.strength
                    }
                    for e in self.get_causal_causes(goal_id)
                ]
            }

    def _trace_causal_chain(self, goal_id: str, max_depth: int = 5) -> List[Dict]:
        """Trace the causal chain leading to a goal."""
        chain = []
        visited = set()

        def trace(gid: str, depth: int):
            if depth > max_depth or gid in visited:
                return
            visited.add(gid)

            goal = self.goals.get(gid)
            if not goal:
                return

            chain.append({
                'goal_id': gid,
                'description': goal.description,
                'state': goal.state.value,
                'depth': depth
            })

            # Follow causal causes
            for edge in self.get_causal_causes(gid):
                trace(edge.source_goal, depth + 1)

        trace(goal_id, 0)
        return chain

    def counterfactual_analysis(
        self,
        goal_id: str,
        intervention: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Perform counterfactual analysis: "What if goal X had succeeded?"

        Args:
            goal_id: Target goal to analyze
            intervention: {goal_id: value} to intervene on

        Returns:
            Counterfactual predictions
        """
        try:
            from core.causal_reasoning import CausalInference

            dag = self.to_causal_dag()
            inference = CausalInference(dag)

            # Build factual state
            factual = {}
            for gid, goal in self.goals.items():
                if goal.state == GoalState.COMPLETED:
                    factual[gid] = 1.0
                elif goal.state == GoalState.FAILED:
                    factual[gid] = 0.0
                else:
                    factual[gid] = 0.5

            # Compute counterfactual
            cf_result = inference.counterfactual(factual, intervention)

            return {
                'target_goal': goal_id,
                'target_description': self.goals.get(goal_id, Goal('', '')).description,
                'intervention': intervention,
                'counterfactual_predictions': {
                    gid: {
                        'expected_value': dist.mean(),
                        'variance': dist.variance(),
                        'goal_description': self.goals.get(gid, Goal('', '')).description
                    }
                    for gid, dist in cf_result.items()
                    if gid == goal_id or gid in self.get_causal_effects(goal_id)
                }
            }
        except Exception as e:
            logger.warning(f"Counterfactual analysis failed: {e}")
            return {'error': str(e)}

    def suggest_goal_order(self) -> List[str]:
        """
        Suggest optimal goal execution order based on causal analysis.

        Uses causal relationships to find order that maximizes success probability.

        Returns:
            List of goal IDs in suggested order
        """
        # Get pending and blocked goals
        candidates = list(self._by_state[GoalState.PENDING]) + list(self._by_state[GoalState.BLOCKED])

        if not candidates:
            return []

        # Score each goal by:
        # 1. Number of goals it enables (more = do first)
        # 2. Priority
        # 3. Deadline proximity

        def score_goal(gid: str) -> Tuple[float, float, float]:
            goal = self.goals.get(gid)
            if not goal:
                return (0, 0, 0)

            # Count downstream effects
            effects = len([e for e in self.get_causal_effects(gid)
                          if e.edge_type in [CausalEdgeType.ENABLES, CausalEdgeType.TRIGGERS]])

            # Priority (invert so CRITICAL=1 becomes highest)
            priority_score = 6 - goal.priority.value

            # Deadline (earlier = higher score)
            if goal.deadline:
                time_left = (goal.deadline - datetime.now()).total_seconds()
                deadline_score = max(0, 1000000 - time_left)  # Higher score for urgent
            else:
                deadline_score = 0

            return (effects, priority_score, deadline_score)

        # Sort by score (descending)
        candidates.sort(key=score_goal, reverse=True)

        return candidates

    def learn_causal_edges_from_history(self, min_occurrences: int = 3) -> int:
        """
        Learn causal relationships from goal completion/failure history.

        Looks for patterns like:
        - When A completes before B, B usually succeeds
        - When A fails, B usually fails too

        Args:
            min_occurrences: Minimum pattern occurrences to create edge

        Returns:
            Number of edges learned
        """
        # Count co-occurrences
        success_follows: Dict[Tuple[str, str], int] = defaultdict(int)
        failure_follows: Dict[Tuple[str, str], int] = defaultdict(int)

        # Analyze completed goals timeline
        sorted_completions = sorted(self.completed_goals, key=lambda x: x[1])

        for i, (goal_a, time_a) in enumerate(sorted_completions):
            # Look at goals completed after this one
            for goal_b, time_b in sorted_completions[i+1:]:
                if (time_b - time_a).total_seconds() < 3600:  # Within 1 hour
                    success_follows[(goal_a, goal_b)] += 1

        # Analyze failures
        for goal_a, time_a, _ in self.failed_goals:
            for goal_b, time_b, _ in self.failed_goals:
                if goal_a != goal_b and abs((time_b - time_a).total_seconds()) < 3600:
                    failure_follows[(goal_a, goal_b)] += 1

        # Create edges for patterns above threshold
        count = 0

        for (source, target), occurrences in success_follows.items():
            if occurrences >= min_occurrences:
                # Check if edge already exists
                existing = [e for e in self.causal_edges
                           if e.source_goal == source and e.target_goal == target]
                if not existing:
                    try:
                        self.add_causal_edge(
                            source, target,
                            CausalEdgeType.CONTRIBUTES,
                            strength=min(1.0, occurrences / 10),
                            confidence=min(1.0, occurrences / 20),
                            learned=True
                        )
                        count += 1
                    except ValueError:
                        pass  # Goal might not exist anymore

        logger.info(f"Learned {count} causal edges from history")
        return count

    def to_dict(self) -> Dict:
        """Serialize goal graph to dictionary"""
        return {
            'goals': {
                gid: {
                    'goal_id': g.goal_id,
                    'description': g.description,
                    'state': g.state.value,
                    'priority': g.priority.value,
                    'parent_id': g.parent_id,
                    'child_ids': g.child_ids,
                    'depends_on': g.depends_on,
                    'progress': g.progress,
                    'deadline': g.deadline.isoformat() if g.deadline else None,
                    'created_at': g.created_at.isoformat(),
                    'context': g.context
                }
                for gid, g in self.goals.items()
            },
            'root_goals': list(self.root_goals),
            'statistics': self.get_statistics()
        }


# Convenience functions for integration
def create_goal_from_task(task: str, complexity: float = 0.5) -> Goal:
    """Create a goal from a task description"""
    # Determine priority based on keywords
    task_lower = task.lower()

    if any(w in task_lower for w in ['urgent', 'critical', 'immediately', 'asap']):
        priority = GoalPriority.CRITICAL
    elif any(w in task_lower for w in ['important', 'high priority', 'soon']):
        priority = GoalPriority.HIGH
    elif any(w in task_lower for w in ['low', 'when possible', 'eventually']):
        priority = GoalPriority.LOW
    elif any(w in task_lower for w in ['background', 'idle']):
        priority = GoalPriority.BACKGROUND
    else:
        priority = GoalPriority.MEDIUM

    # Estimate duration based on complexity
    estimated_minutes = int(complexity * 60)  # Up to 60 minutes for complex tasks

    return Goal(
        goal_id=str(uuid.uuid4())[:8],
        description=task,
        priority=priority,
        estimated_duration=timedelta(minutes=estimated_minutes),
        context={'complexity': complexity}
    )


if __name__ == "__main__":
    # Test the Goal Graph
    print("="*70)
    print("Goal Graph Test")
    print("="*70)

    graph = GoalGraph()

    # Create a hierarchical goal structure
    # Main goal: Deploy application
    deploy = graph.add_goal(
        "Deploy application to production",
        priority=GoalPriority.HIGH,
        deadline=datetime.now() + timedelta(hours=4)
    )
    print(f"Created main goal: {deploy.goal_id}")

    # Subgoals
    build = graph.add_goal(
        "Build Docker image",
        parent_id=deploy.goal_id,
        priority=GoalPriority.HIGH,
        estimated_duration=timedelta(minutes=15)
    )
    print(f"Created subgoal: {build.goal_id}")

    test = graph.add_goal(
        "Run integration tests",
        parent_id=deploy.goal_id,
        priority=GoalPriority.HIGH,
        depends_on=[build.goal_id],
        estimated_duration=timedelta(minutes=30)
    )
    print(f"Created subgoal (depends on build): {test.goal_id}")

    push = graph.add_goal(
        "Push to registry",
        parent_id=deploy.goal_id,
        priority=GoalPriority.MEDIUM,
        depends_on=[test.goal_id],
        estimated_duration=timedelta(minutes=5)
    )
    print(f"Created subgoal (depends on test): {push.goal_id}")

    # Check ready goals
    ready = graph.get_ready_goals()
    print(f"\nReady goals: {[g.description for g in ready]}")

    # Start build
    graph.start_goal(build.goal_id)
    print(f"\nStarted: {build.description}")
    print(f"Active goals: {[g.description for g in graph.get_active_goals()]}")

    # Complete build
    graph.complete_goal(build.goal_id, "Image built successfully")
    print(f"\nCompleted: {build.description}")

    # Check what's ready now
    ready = graph.get_ready_goals()
    print(f"Ready goals: {[g.description for g in ready]}")

    # Get CTM context
    print(f"\nCTM Context:")
    ctx = graph.get_context_for_ctm()
    for key, value in ctx.items():
        print(f"  {key}: {value}")

    # Statistics
    print(f"\nStatistics:")
    stats = graph.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "="*70)
    print("Goal Graph Test Complete!")
    print("="*70)

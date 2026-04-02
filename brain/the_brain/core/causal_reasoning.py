"""
Causal Reasoning Layer for The Brain

Provides causal inference capabilities using:
1. CausalDAG - Directed Acyclic Graph for causal relationships
2. CausalInference - Pearl's do-calculus for interventional queries
3. RootCauseAnalyzer - Automated root cause analysis for failures

Based on Judea Pearl's causal hierarchy:
- Level 1: Association (seeing) - P(Y|X)
- Level 2: Intervention (doing) - P(Y|do(X))
- Level 3: Counterfactual (imagining) - P(Y_x|X', Y')

Integration points:
- goal_graph.py: Extend DAG structure for causal edges
- active_inference.py: Bayesian updating for causal inference
- hierarchical_planner.py: Causal planning for goal achievement
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable, Set, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import json
import logging
from pathlib import Path
from datetime import datetime
import copy

logger = logging.getLogger(__name__)


class EdgeType(Enum):
    """Types of causal edges."""
    DIRECT = "direct"           # X -> Y (direct cause)
    CONFOUNDED = "confounded"   # X <-> Y (common cause)
    MEDIATED = "mediated"       # X -> M -> Y (mediated effect)
    INSTRUMENTAL = "instrumental"  # Z -> X -> Y (instrumental variable)


@dataclass
class Distribution:
    """Probability distribution over a variable."""
    values: np.ndarray          # Possible values
    probabilities: np.ndarray   # P(value)

    def __post_init__(self):
        """Normalize probabilities."""
        self.probabilities = self.probabilities / np.sum(self.probabilities)

    def mean(self) -> float:
        """Expected value."""
        return np.sum(self.values * self.probabilities)

    def variance(self) -> float:
        """Variance."""
        mu = self.mean()
        return np.sum(self.probabilities * (self.values - mu) ** 2)

    def sample(self, n: int = 1) -> np.ndarray:
        """Sample from distribution."""
        return np.random.choice(self.values, size=n, p=self.probabilities)

    def condition_on(self, value: float, epsilon: float = 0.1) -> 'Distribution':
        """Condition distribution on observed value."""
        # Find closest value and boost its probability
        distances = np.abs(self.values - value)
        weights = np.exp(-distances / epsilon)
        new_probs = self.probabilities * weights
        return Distribution(self.values.copy(), new_probs)


@dataclass
class CausalNode:
    """Node in causal DAG representing a variable."""
    name: str
    distribution: Optional[Distribution] = None
    observed_value: Optional[float] = None
    is_latent: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Structural equation: value = mechanism(parent_values) + noise
    mechanism: Optional[Callable[[Dict[str, float]], float]] = None
    noise_std: float = 0.1


@dataclass
class CausalEdge:
    """Edge in causal DAG representing causal relationship."""
    cause: str
    effect: str
    edge_type: EdgeType = EdgeType.DIRECT
    strength: float = 1.0  # Causal effect size
    confidence: float = 1.0  # Confidence in edge existence
    mechanism: Optional[Callable[[float], float]] = None  # Causal mechanism
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RootCause:
    """Identified root cause of a failure."""
    variable: str
    probability: float  # P(cause | symptoms)
    evidence: List[str]  # Supporting evidence
    intervention: Optional[str] = None  # Suggested fix
    impact: float = 0.0  # Expected impact if fixed


@dataclass
class FailureEvent:
    """Record of a failure event."""
    timestamp: datetime
    symptoms: Dict[str, Any]
    root_causes: List[RootCause]
    resolved: bool = False
    resolution: Optional[str] = None


class CausalDAG:
    """
    Directed Acyclic Graph for causal relationships.

    Supports:
    - Structure learning from observations (PC algorithm)
    - Causal effect identification
    - D-separation queries
    - Topological sorting for inference
    """

    def __init__(self):
        self.nodes: Dict[str, CausalNode] = {}
        self.edges: List[CausalEdge] = []
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)  # parent -> children
        self._reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)  # child -> parents
        self._edge_map: Dict[Tuple[str, str], CausalEdge] = {}

    def add_variable(self, name: str, distribution: Optional[Distribution] = None,
                     is_latent: bool = False, mechanism: Optional[Callable] = None,
                     noise_std: float = 0.1) -> None:
        """Add a variable to the DAG."""
        if name in self.nodes:
            logger.warning(f"Variable {name} already exists, updating")

        self.nodes[name] = CausalNode(
            name=name,
            distribution=distribution,
            is_latent=is_latent,
            mechanism=mechanism,
            noise_std=noise_std
        )
        logger.debug(f"Added variable: {name}")

    def add_edge(self, cause: str, effect: str,
                 edge_type: EdgeType = EdgeType.DIRECT,
                 strength: float = 1.0,
                 mechanism: Optional[Callable[[float], float]] = None) -> None:
        """Add a causal edge to the DAG."""
        # Validate nodes exist
        if cause not in self.nodes:
            self.add_variable(cause)
        if effect not in self.nodes:
            self.add_variable(effect)

        # Check for cycles
        if self._would_create_cycle(cause, effect):
            raise ValueError(f"Edge {cause} -> {effect} would create a cycle")

        edge = CausalEdge(
            cause=cause,
            effect=effect,
            edge_type=edge_type,
            strength=strength,
            mechanism=mechanism
        )

        self.edges.append(edge)
        self._adjacency[cause].add(effect)
        self._reverse_adjacency[effect].add(cause)
        self._edge_map[(cause, effect)] = edge

        logger.debug(f"Added edge: {cause} -> {effect} (strength={strength})")

    def _would_create_cycle(self, source: str, target: str) -> bool:
        """Check if adding edge source->target would create a cycle."""
        # BFS from target to see if we can reach source
        visited = set()
        queue = deque([target])

        while queue:
            node = queue.popleft()
            if node == source:
                return True
            if node in visited:
                continue
            visited.add(node)
            queue.extend(self._adjacency.get(node, set()))

        return False

    def get_parents(self, node: str) -> List[str]:
        """Get parent nodes (direct causes)."""
        return list(self._reverse_adjacency.get(node, set()))

    def get_children(self, node: str) -> List[str]:
        """Get child nodes (direct effects)."""
        return list(self._adjacency.get(node, set()))

    def get_ancestors(self, node: str) -> Set[str]:
        """Get all ancestors (all causes)."""
        ancestors = set()
        queue = deque(self.get_parents(node))

        while queue:
            ancestor = queue.popleft()
            if ancestor not in ancestors:
                ancestors.add(ancestor)
                queue.extend(self.get_parents(ancestor))

        return ancestors

    def get_descendants(self, node: str) -> Set[str]:
        """Get all descendants (all effects)."""
        descendants = set()
        queue = deque(self.get_children(node))

        while queue:
            descendant = queue.popleft()
            if descendant not in descendants:
                descendants.add(descendant)
                queue.extend(self.get_children(descendant))

        return descendants

    def topological_sort(self) -> List[str]:
        """Return nodes in topological order."""
        in_degree = defaultdict(int)
        for node in self.nodes:
            in_degree[node] = len(self._reverse_adjacency.get(node, set()))

        queue = deque([n for n in self.nodes if in_degree[n] == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            for child in self._adjacency.get(node, set()):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(result) != len(self.nodes):
            raise ValueError("Graph contains a cycle")

        return result

    def d_separated(self, x: str, y: str, z: Set[str]) -> bool:
        """
        Check if X and Y are d-separated given Z.

        D-separation implies conditional independence: X ⊥ Y | Z

        Uses the Bayes-Ball algorithm.
        """
        # Bayes-Ball algorithm
        visited_from_child = set()
        visited_from_parent = set()

        # Schedule: (node, came_from_child)
        queue = deque([(x, True), (x, False)])

        while queue:
            node, from_child = queue.popleft()

            if node == y:
                return False  # Path found, not d-separated

            # Check if already visited this way
            if from_child:
                if node in visited_from_child:
                    continue
                visited_from_child.add(node)
            else:
                if node in visited_from_parent:
                    continue
                visited_from_parent.add(node)

            # Determine allowed transitions based on conditioning set
            is_conditioned = node in z

            if from_child:
                # Arrived from child
                if not is_conditioned:
                    # Can go to parents
                    for parent in self.get_parents(node):
                        queue.append((parent, False))
                if is_conditioned:
                    # Can go to children (v-structure unblocked)
                    for child in self.get_children(node):
                        queue.append((child, True))
            else:
                # Arrived from parent
                if not is_conditioned:
                    # Can go to children
                    for child in self.get_children(node):
                        queue.append((child, True))
                if not is_conditioned:
                    # Can go to parents (chain)
                    for parent in self.get_parents(node):
                        queue.append((parent, False))

        return True  # No path found, d-separated

    def infer_structure(self, observations: np.ndarray,
                        variable_names: List[str],
                        alpha: float = 0.05) -> 'CausalDAG':
        """
        Infer causal structure from observational data using PC algorithm.

        Args:
            observations: N x D array of observations
            variable_names: Names for each variable
            alpha: Significance level for conditional independence tests

        Returns:
            CausalDAG with inferred structure
        """
        n_vars = len(variable_names)

        # Initialize complete undirected graph
        adjacency = {v: set(variable_names) - {v} for v in variable_names}

        # Add all variables
        for name in variable_names:
            if name not in self.nodes:
                self.add_variable(name)

        # Phase 1: Remove edges based on conditional independence
        for d in range(n_vars):  # Conditioning set size
            for x in variable_names:
                neighbors = list(adjacency[x])
                for y in neighbors:
                    if y not in adjacency[x]:
                        continue

                    # Find conditioning sets of size d
                    other_neighbors = [n for n in neighbors if n != y]
                    if len(other_neighbors) < d:
                        continue

                    # Test all conditioning sets of size d
                    from itertools import combinations
                    for z_set in combinations(other_neighbors, d):
                        z_set = set(z_set)

                        # Conditional independence test
                        if self._conditional_independence_test(
                            observations, variable_names, x, y, z_set, alpha
                        ):
                            adjacency[x].discard(y)
                            adjacency[y].discard(x)
                            break

        # Phase 2: Orient edges (simplified - using causal sufficiency assumption)
        # Find v-structures: X - Z - Y where X and Y not adjacent
        for z in variable_names:
            neighbors = list(adjacency[z])
            for i, x in enumerate(neighbors):
                for y in neighbors[i+1:]:
                    if y not in adjacency[x]:  # X and Y not adjacent
                        # X -> Z <- Y (v-structure)
                        self.add_edge(x, z)
                        self.add_edge(y, z)

        # Add remaining edges (orient consistently to avoid cycles)
        for x in variable_names:
            for y in adjacency[x]:
                if (x, y) not in self._edge_map and (y, x) not in self._edge_map:
                    # Orient based on topological order heuristic
                    if variable_names.index(x) < variable_names.index(y):
                        self.add_edge(x, y)
                    else:
                        self.add_edge(y, x)

        logger.info(f"Inferred DAG with {len(self.edges)} edges")
        return self

    def _conditional_independence_test(self, observations: np.ndarray,
                                       variable_names: List[str],
                                       x: str, y: str, z: Set[str],
                                       alpha: float) -> bool:
        """
        Test conditional independence X ⊥ Y | Z using partial correlation.

        Returns True if X and Y are conditionally independent given Z.
        """
        x_idx = variable_names.index(x)
        y_idx = variable_names.index(y)
        z_indices = [variable_names.index(z_var) for z_var in z]

        n = observations.shape[0]

        if len(z) == 0:
            # Simple correlation test
            corr = np.corrcoef(observations[:, x_idx], observations[:, y_idx])[0, 1]
            # Fisher z-transform for significance test
            z_stat = 0.5 * np.log((1 + corr) / (1 - corr + 1e-10))
            z_stat = z_stat * np.sqrt(n - 3)
            p_value = 2 * (1 - self._normal_cdf(abs(z_stat)))
        else:
            # Partial correlation
            corr = self._partial_correlation(observations, x_idx, y_idx, z_indices)
            # Fisher z-transform
            z_stat = 0.5 * np.log((1 + corr) / (1 - corr + 1e-10))
            z_stat = z_stat * np.sqrt(n - len(z) - 3)
            p_value = 2 * (1 - self._normal_cdf(abs(z_stat)))

        return p_value > alpha

    def _partial_correlation(self, data: np.ndarray, x: int, y: int,
                            z: List[int]) -> float:
        """Compute partial correlation between x and y given z."""
        if len(z) == 0:
            return np.corrcoef(data[:, x], data[:, y])[0, 1]

        # Residualize x and y on z
        z_data = data[:, z]

        # Linear regression: x = z @ beta_x + residual_x
        beta_x = np.linalg.lstsq(z_data, data[:, x], rcond=None)[0]
        residual_x = data[:, x] - z_data @ beta_x

        beta_y = np.linalg.lstsq(z_data, data[:, y], rcond=None)[0]
        residual_y = data[:, y] - z_data @ beta_y

        return np.corrcoef(residual_x, residual_y)[0, 1]

    def _normal_cdf(self, x: float) -> float:
        """Standard normal CDF approximation."""
        return 0.5 * (1 + np.tanh(np.sqrt(2/np.pi) * (x + 0.044715 * x**3)))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize DAG to dictionary."""
        return {
            'nodes': {
                name: {
                    'is_latent': node.is_latent,
                    'metadata': node.metadata
                }
                for name, node in self.nodes.items()
            },
            'edges': [
                {
                    'cause': e.cause,
                    'effect': e.effect,
                    'edge_type': e.edge_type.value,
                    'strength': e.strength,
                    'confidence': e.confidence
                }
                for e in self.edges
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CausalDAG':
        """Deserialize DAG from dictionary."""
        dag = cls()

        for name, node_data in data.get('nodes', {}).items():
            dag.add_variable(
                name=name,
                is_latent=node_data.get('is_latent', False)
            )
            dag.nodes[name].metadata = node_data.get('metadata', {})

        for edge_data in data.get('edges', []):
            dag.add_edge(
                cause=edge_data['cause'],
                effect=edge_data['effect'],
                edge_type=EdgeType(edge_data.get('edge_type', 'direct')),
                strength=edge_data.get('strength', 1.0)
            )

        return dag


class CausalInference:
    """
    Pearl's do-calculus for interventional and counterfactual queries.

    Implements:
    - Observational queries: P(Y|X)
    - Interventional queries: P(Y|do(X))
    - Counterfactual queries: P(Y_x|X', Y')
    """

    def __init__(self, dag: CausalDAG):
        self.dag = dag
        self._cache: Dict[str, Any] = {}

    def observe(self, evidence: Dict[str, float]) -> Dict[str, Distribution]:
        """
        Compute posterior distributions given observations.

        P(Y|X=x) for all Y not in evidence.
        """
        # Set observed values
        for var, value in evidence.items():
            if var in self.dag.nodes:
                self.dag.nodes[var].observed_value = value

        # Forward sampling with conditioning
        posteriors = {}
        n_samples = 1000

        for target in self.dag.nodes:
            if target in evidence:
                continue

            samples = []
            for _ in range(n_samples):
                sample = self._sample_given_evidence(target, evidence)
                if sample is not None:
                    samples.append(sample)

            if samples:
                samples = np.array(samples)
                values = np.linspace(samples.min(), samples.max(), 50)
                # Kernel density estimation
                probs = np.zeros(len(values))
                bandwidth = (samples.max() - samples.min()) / 10 + 0.01
                for s in samples:
                    probs += np.exp(-0.5 * ((values - s) / bandwidth) ** 2)
                posteriors[target] = Distribution(values, probs)

        return posteriors

    def do(self, intervention: Dict[str, float]) -> Dict[str, Distribution]:
        """
        Compute distributions under intervention (do-operator).

        P(Y|do(X=x)) - the causal effect of setting X to x.

        This is different from P(Y|X=x) because we break incoming edges to X.
        """
        # Create mutilated graph (remove edges into intervened variables)
        mutilated_dag = self._mutilate(intervention.keys())

        # Set intervention values
        for var, value in intervention.items():
            if var in mutilated_dag.nodes:
                mutilated_dag.nodes[var].observed_value = value

        # Forward sample from mutilated graph
        posteriors = {}
        n_samples = 1000

        for target in mutilated_dag.nodes:
            if target in intervention:
                continue

            samples = self._forward_sample(mutilated_dag, target, intervention, n_samples)

            if len(samples) > 0:
                values = np.linspace(min(samples), max(samples), 50)
                probs = np.zeros(len(values))
                bandwidth = (max(samples) - min(samples)) / 10 + 0.01
                for s in samples:
                    probs += np.exp(-0.5 * ((values - s) / bandwidth) ** 2)
                posteriors[target] = Distribution(values, probs)

        return posteriors

    def _mutilate(self, intervention_vars: Set[str]) -> CausalDAG:
        """Create mutilated graph by removing edges into intervention variables."""
        mutilated = CausalDAG()

        # Copy nodes
        for name, node in self.dag.nodes.items():
            mutilated.add_variable(
                name=name,
                distribution=node.distribution,
                is_latent=node.is_latent,
                mechanism=node.mechanism,
                noise_std=node.noise_std
            )

        # Copy edges except those into intervention variables
        for edge in self.dag.edges:
            if edge.effect not in intervention_vars:
                mutilated.add_edge(
                    cause=edge.cause,
                    effect=edge.effect,
                    edge_type=edge.edge_type,
                    strength=edge.strength,
                    mechanism=edge.mechanism
                )

        return mutilated

    def _forward_sample(self, dag: CausalDAG, target: str,
                       fixed_values: Dict[str, float],
                       n_samples: int) -> List[float]:
        """Forward sample target variable from DAG."""
        samples = []
        topo_order = dag.topological_sort()

        for _ in range(n_samples):
            values = {}

            for var in topo_order:
                if var in fixed_values:
                    values[var] = fixed_values[var]
                else:
                    # Sample from structural equation
                    node = dag.nodes[var]
                    parents = dag.get_parents(var)

                    if parents and node.mechanism:
                        parent_values = {p: values[p] for p in parents}
                        mean = node.mechanism(parent_values)
                    elif parents:
                        # Default: linear combination
                        mean = sum(
                            dag._edge_map.get((p, var), CausalEdge(p, var)).strength * values[p]
                            for p in parents
                        )
                    elif node.distribution:
                        mean = node.distribution.sample(1)[0]
                    else:
                        mean = 0.0

                    values[var] = mean + np.random.normal(0, node.noise_std)

            samples.append(values.get(target, 0.0))

        return samples

    def _sample_given_evidence(self, target: str,
                               evidence: Dict[str, float]) -> Optional[float]:
        """Sample target given evidence using rejection sampling."""
        topo_order = self.dag.topological_sort()
        values = {}

        for var in topo_order:
            node = self.dag.nodes[var]
            parents = self.dag.get_parents(var)

            if parents and node.mechanism:
                parent_values = {p: values[p] for p in parents}
                mean = node.mechanism(parent_values)
            elif parents:
                mean = sum(
                    self.dag._edge_map.get((p, var), CausalEdge(p, var)).strength * values[p]
                    for p in parents
                )
            elif node.distribution:
                mean = node.distribution.sample(1)[0]
            else:
                mean = 0.0

            values[var] = mean + np.random.normal(0, node.noise_std)

        # Check if evidence is satisfied (approximately)
        for var, obs_value in evidence.items():
            if var in values and abs(values[var] - obs_value) > 2 * self.dag.nodes[var].noise_std:
                return None  # Reject sample

        return values.get(target)

    def counterfactual(self, factual: Dict[str, float],
                       intervention: Dict[str, float]) -> Dict[str, Distribution]:
        """
        Compute counterfactual: "What would Y have been if X had been x?"

        Three-step process:
        1. Abduction: Infer latent noise from factual evidence
        2. Action: Intervene (do(X=x))
        3. Prediction: Compute Y under intervention with inferred noise

        Args:
            factual: Observed factual values {var: value}
            intervention: Counterfactual intervention {var: value}

        Returns:
            Counterfactual distributions for non-intervened variables
        """
        n_samples = 500
        counterfactual_samples = defaultdict(list)

        topo_order = self.dag.topological_sort()

        for _ in range(n_samples):
            # Step 1: Abduction - infer noise terms from factual evidence
            noise_terms = {}
            values = {}

            for var in topo_order:
                node = self.dag.nodes[var]
                parents = self.dag.get_parents(var)

                # Compute deterministic part
                if parents and node.mechanism:
                    parent_values = {p: values.get(p, factual.get(p, 0)) for p in parents}
                    deterministic = node.mechanism(parent_values)
                elif parents:
                    deterministic = sum(
                        self.dag._edge_map.get((p, var), CausalEdge(p, var)).strength *
                        values.get(p, factual.get(p, 0))
                        for p in parents
                    )
                else:
                    deterministic = 0.0

                if var in factual:
                    # Infer noise from factual observation
                    noise_terms[var] = factual[var] - deterministic
                    values[var] = factual[var]
                else:
                    # Sample noise
                    noise_terms[var] = np.random.normal(0, node.noise_std)
                    values[var] = deterministic + noise_terms[var]

            # Step 2 & 3: Action and Prediction in mutilated graph
            cf_values = {}

            for var in topo_order:
                if var in intervention:
                    cf_values[var] = intervention[var]
                else:
                    node = self.dag.nodes[var]
                    parents = self.dag.get_parents(var)

                    # Compute with intervention values and original noise
                    if parents and node.mechanism:
                        parent_values = {p: cf_values.get(p, values.get(p, 0)) for p in parents}
                        deterministic = node.mechanism(parent_values)
                    elif parents:
                        deterministic = sum(
                            self.dag._edge_map.get((p, var), CausalEdge(p, var)).strength *
                            cf_values.get(p, values.get(p, 0))
                            for p in parents
                        )
                    else:
                        deterministic = 0.0

                    cf_values[var] = deterministic + noise_terms.get(var, 0)

                counterfactual_samples[var].append(cf_values.get(var, 0))

        # Convert samples to distributions
        posteriors = {}
        for var, samples in counterfactual_samples.items():
            if var not in intervention:
                samples = np.array(samples)
                values = np.linspace(samples.min(), samples.max(), 50)
                probs = np.zeros(len(values))
                bandwidth = (samples.max() - samples.min()) / 10 + 0.01
                for s in samples:
                    probs += np.exp(-0.5 * ((values - s) / bandwidth) ** 2)
                posteriors[var] = Distribution(values, probs)

        return posteriors

    def identify_effect(self, treatment: str, outcome: str) -> bool:
        """
        Check if causal effect of treatment on outcome is identifiable.

        Uses the back-door criterion: effect is identifiable if there exists
        a set of variables Z that blocks all back-door paths from treatment
        to outcome.
        """
        # Find all back-door paths (paths from treatment to outcome
        # that start with an edge into treatment)
        parents_of_treatment = set(self.dag.get_parents(treatment))
        descendants_of_treatment = self.dag.get_descendants(treatment)

        # Potential adjustment sets: ancestors of treatment that are not descendants
        candidates = self.dag.get_ancestors(treatment) - descendants_of_treatment

        # Check if any subset of candidates blocks all back-door paths
        from itertools import combinations

        for size in range(len(candidates) + 1):
            for z_set in combinations(candidates, size):
                z_set = set(z_set)

                # Check back-door criterion:
                # 1. Z doesn't contain any descendant of treatment
                if z_set & descendants_of_treatment:
                    continue

                # 2. Z blocks all back-door paths
                if self.dag.d_separated(treatment, outcome, z_set | {treatment}):
                    return True

        return False

    def average_treatment_effect(self, treatment: str, outcome: str,
                                 treatment_values: Tuple[float, float] = (0.0, 1.0)) -> float:
        """
        Compute Average Treatment Effect (ATE).

        ATE = E[Y|do(T=1)] - E[Y|do(T=0)]
        """
        effect_0 = self.do({treatment: treatment_values[0]})
        effect_1 = self.do({treatment: treatment_values[1]})

        if outcome in effect_0 and outcome in effect_1:
            return effect_1[outcome].mean() - effect_0[outcome].mean()

        return 0.0


class RootCauseAnalyzer:
    """
    Automated root cause analysis for failures.

    Uses causal model to:
    1. Identify potential root causes from symptoms
    2. Rank causes by probability and impact
    3. Suggest interventions
    """

    def __init__(self, causal_model: CausalDAG):
        self.model = causal_model
        self.inference = CausalInference(causal_model)
        self.failure_history: List[FailureEvent] = []
        self._cause_priors: Dict[str, float] = defaultdict(lambda: 0.1)

    def analyze_failure(self, symptoms: Dict[str, Any]) -> List[RootCause]:
        """
        Identify root causes from observed symptoms.

        Args:
            symptoms: Dictionary of observed anomalies {variable: value}

        Returns:
            List of potential root causes ranked by probability
        """
        root_causes = []

        # Find potential causes (ancestors of symptomatic variables)
        potential_causes: Set[str] = set()
        for symptom in symptoms:
            if symptom in self.model.nodes:
                potential_causes.update(self.model.get_ancestors(symptom))

        # For each potential cause, compute P(cause | symptoms)
        for cause in potential_causes:
            # Skip if cause is also a symptom
            if cause in symptoms:
                continue

            probability = self._compute_cause_probability(cause, symptoms)
            evidence = self._gather_evidence(cause, symptoms)
            impact = self._estimate_impact(cause, symptoms)
            intervention = self._suggest_intervention(cause)

            root_causes.append(RootCause(
                variable=cause,
                probability=probability,
                evidence=evidence,
                intervention=intervention,
                impact=impact
            ))

        # Sort by probability * impact
        root_causes.sort(key=lambda x: x.probability * x.impact, reverse=True)

        # Record failure event
        self.failure_history.append(FailureEvent(
            timestamp=datetime.now(),
            symptoms=symptoms,
            root_causes=root_causes[:5]  # Top 5
        ))

        return root_causes

    def _compute_cause_probability(self, cause: str,
                                   symptoms: Dict[str, Any]) -> float:
        """Compute P(cause abnormal | symptoms) using Bayes' rule."""
        # Prior probability of cause being abnormal
        prior = self._cause_priors[cause]

        # Likelihood: P(symptoms | cause abnormal)
        # Estimate from causal structure
        descendants = self.model.get_descendants(cause)
        symptoms_explained = sum(1 for s in symptoms if s in descendants)
        total_symptoms = len(symptoms)

        likelihood = (symptoms_explained / total_symptoms) if total_symptoms > 0 else 0.5

        # Simple Bayesian update
        posterior = (likelihood * prior) / (
            likelihood * prior + (1 - likelihood) * (1 - prior) + 1e-10
        )

        return posterior

    def _gather_evidence(self, cause: str, symptoms: Dict[str, Any]) -> List[str]:
        """Gather evidence supporting this cause."""
        evidence = []

        descendants = self.model.get_descendants(cause)
        for symptom, value in symptoms.items():
            if symptom in descendants:
                evidence.append(f"{symptom} affected (value: {value})")

        # Check for typical patterns
        children = self.model.get_children(cause)
        affected_children = [c for c in children if c in symptoms]
        if len(affected_children) > 1:
            evidence.append(f"Multiple direct effects affected: {affected_children}")

        return evidence

    def _estimate_impact(self, cause: str, symptoms: Dict[str, Any]) -> float:
        """Estimate impact of fixing this cause."""
        # Impact = fraction of symptoms that would be resolved
        descendants = self.model.get_descendants(cause)
        resolvable = sum(1 for s in symptoms if s in descendants)

        return resolvable / len(symptoms) if symptoms else 0.0

    def _suggest_intervention(self, cause: str) -> str:
        """Suggest intervention for root cause."""
        node = self.model.nodes.get(cause)
        if node and node.metadata.get('fix_action'):
            return node.metadata['fix_action']

        return f"Investigate and normalize {cause}"

    def rank_causes(self, causes: List[RootCause]) -> List[Tuple[RootCause, float]]:
        """
        Rank root causes by combined score.

        Score = probability * impact * (1 + historical_frequency)
        """
        # Compute historical frequency from failure_history
        cause_frequency: Dict[str, int] = defaultdict(int)
        for event in self.failure_history:
            for rc in event.root_causes:
                cause_frequency[rc.variable] += 1

        total_failures = len(self.failure_history) + 1  # Avoid division by zero

        ranked = []
        for cause in causes:
            freq_factor = 1 + cause_frequency[cause.variable] / total_failures
            score = cause.probability * cause.impact * freq_factor
            ranked.append((cause, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def suggest_intervention(self, root_cause: RootCause) -> Dict[str, Any]:
        """
        Generate detailed intervention suggestion.

        Returns:
            Dictionary with intervention details
        """
        return {
            'cause': root_cause.variable,
            'action': root_cause.intervention,
            'expected_impact': root_cause.impact,
            'confidence': root_cause.probability,
            'evidence': root_cause.evidence,
            'counterfactual': f"If {root_cause.variable} were fixed, "
                             f"{root_cause.impact*100:.0f}% of symptoms would likely resolve"
        }

    def update_priors(self, resolution: Dict[str, bool]) -> None:
        """
        Update cause priors based on resolution outcomes.

        Args:
            resolution: {cause: was_actual_cause}
        """
        learning_rate = 0.1

        for cause, was_correct in resolution.items():
            current = self._cause_priors[cause]
            if was_correct:
                self._cause_priors[cause] = current + learning_rate * (1 - current)
            else:
                self._cause_priors[cause] = current - learning_rate * current

    def export_history(self, path: Path) -> None:
        """Export failure history to JSON."""
        data = []
        for event in self.failure_history:
            data.append({
                'timestamp': event.timestamp.isoformat(),
                'symptoms': event.symptoms,
                'root_causes': [
                    {
                        'variable': rc.variable,
                        'probability': rc.probability,
                        'evidence': rc.evidence,
                        'intervention': rc.intervention,
                        'impact': rc.impact
                    }
                    for rc in event.root_causes
                ],
                'resolved': event.resolved,
                'resolution': event.resolution
            })

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported {len(data)} failure events to {path}")


# Convenience functions
def create_simple_dag() -> CausalDAG:
    """Create a simple example DAG for testing."""
    dag = CausalDAG()

    # Variables
    dag.add_variable('weather', Distribution(np.array([0, 1]), np.array([0.7, 0.3])))
    dag.add_variable('sprinkler')
    dag.add_variable('rain')
    dag.add_variable('wet_grass')

    # Causal relationships
    dag.add_edge('weather', 'sprinkler', strength=-0.5)
    dag.add_edge('weather', 'rain', strength=0.8)
    dag.add_edge('sprinkler', 'wet_grass', strength=0.6)
    dag.add_edge('rain', 'wet_grass', strength=0.9)

    return dag


if __name__ == "__main__":
    # Demo
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Causal Reasoning Layer Demo")
    print("=" * 60)

    # Create example DAG
    dag = create_simple_dag()
    print(f"\nCreated DAG with {len(dag.nodes)} nodes and {len(dag.edges)} edges")
    print(f"Nodes: {list(dag.nodes.keys())}")
    print(f"Edges: {[(e.cause, e.effect) for e in dag.edges]}")

    # Test d-separation
    print("\n--- D-Separation Tests ---")
    print(f"sprinkler ⊥ rain | {{}}: {dag.d_separated('sprinkler', 'rain', set())}")
    print(f"sprinkler ⊥ rain | {{weather}}: {dag.d_separated('sprinkler', 'rain', {'weather'})}")

    # Causal inference
    inference = CausalInference(dag)

    print("\n--- Interventional Query ---")
    print("P(wet_grass | do(sprinkler=1)):")
    result = inference.do({'sprinkler': 1.0})
    if 'wet_grass' in result:
        print(f"  E[wet_grass] = {result['wet_grass'].mean():.3f}")

    print("\n--- Counterfactual Query ---")
    print("Factual: sprinkler=0, rain=1, wet_grass=0.9")
    print("Counterfactual: What if sprinkler=1?")
    cf_result = inference.counterfactual(
        factual={'sprinkler': 0, 'rain': 1, 'wet_grass': 0.9},
        intervention={'sprinkler': 1}
    )
    if 'wet_grass' in cf_result:
        print(f"  E[wet_grass | do(sprinkler=1)] = {cf_result['wet_grass'].mean():.3f}")

    # Root cause analysis
    print("\n--- Root Cause Analysis ---")
    analyzer = RootCauseAnalyzer(dag)

    symptoms = {'wet_grass': 1.0}
    causes = analyzer.analyze_failure(symptoms)

    print(f"Symptoms: {symptoms}")
    print("Potential root causes:")
    for cause in causes[:3]:
        print(f"  {cause.variable}: P={cause.probability:.3f}, impact={cause.impact:.3f}")
        print(f"    Evidence: {cause.evidence}")

    print("\n" + "=" * 60)
    print("Demo complete!")

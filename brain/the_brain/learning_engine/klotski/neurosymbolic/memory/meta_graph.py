"""
Meta-Graph for Transfer Learning

Tracks puzzle-to-puzzle knowledge transfer and enables curriculum learning.
Records which skills/strategies transfer between puzzle types.
"""

import networkx as nx
import numpy as np
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
import pickle
from pathlib import Path


@dataclass
class PuzzleNode:
    """Node representing a puzzle type"""
    puzzle_id: str
    puzzle_name: str
    difficulty: float  # Estimated difficulty (0-1)
    success_rate: float = 0.0  # Current solve rate
    avg_steps: float = 0.0  # Average steps to solve
    num_attempts: int = 0
    num_successes: int = 0
    emphasized_modules: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class TransferEdge:
    """Edge representing knowledge transfer between puzzles"""
    source_puzzle: str
    target_puzzle: str
    transfer_score: float  # How much knowledge transfers (0-1)
    shared_patterns: List[str] = field(default_factory=list)
    performance_gain: float = 0.0  # Performance improvement from transfer
    num_observations: int = 0


class MetaGraph:
    """
    Meta-Graph for puzzle knowledge and transfer learning

    Maintains a graph where:
    - Nodes = puzzle types
    - Edges = knowledge transfer relationships
    - Enables curriculum scheduling based on transfer paths
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self.puzzle_nodes: Dict[str, PuzzleNode] = {}
        self.transfer_edges: Dict[Tuple[str, str], TransferEdge] = {}

        # Pattern frequency tracking
        self.pattern_frequency: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add_puzzle(self, node: PuzzleNode):
        """Add puzzle type to meta-graph"""
        self.graph.add_node(node.puzzle_id, data=node)
        self.puzzle_nodes[node.puzzle_id] = node

    def add_transfer_edge(self, edge: TransferEdge):
        """Add knowledge transfer edge"""
        self.graph.add_edge(
            edge.source_puzzle,
            edge.target_puzzle,
            weight=edge.transfer_score,
            data=edge
        )
        self.transfer_edges[(edge.source_puzzle, edge.target_puzzle)] = edge

    def update_puzzle_stats(
        self,
        puzzle_id: str,
        success: bool,
        steps: int
    ):
        """Update puzzle statistics after episode"""
        if puzzle_id not in self.puzzle_nodes:
            return

        node = self.puzzle_nodes[puzzle_id]
        node.num_attempts += 1

        if success:
            node.num_successes += 1

        # Update success rate
        node.success_rate = node.num_successes / node.num_attempts

        # Update average steps (exponential moving average)
        alpha = 0.1
        node.avg_steps = alpha * steps + (1 - alpha) * node.avg_steps

    def record_pattern_usage(self, puzzle_id: str, pattern: str):
        """Record that a pattern was used in a puzzle"""
        self.pattern_frequency[puzzle_id][pattern] += 1

    def compute_transfer_score(
        self,
        source_puzzle: str,
        target_puzzle: str
    ) -> float:
        """
        Compute knowledge transfer score between puzzles

        Based on:
        - Shared patterns (higher overlap = more transfer)
        - Module emphasis overlap
        - Empirical performance gains

        Returns:
            transfer_score: 0-1 (0 = no transfer, 1 = perfect transfer)
        """
        if source_puzzle not in self.puzzle_nodes or target_puzzle not in self.puzzle_nodes:
            return 0.0

        source_node = self.puzzle_nodes[source_puzzle]
        target_node = self.puzzle_nodes[target_puzzle]

        # 1. Pattern overlap
        source_patterns = set(self.pattern_frequency[source_puzzle].keys())
        target_patterns = set(self.pattern_frequency[target_puzzle].keys())

        if len(source_patterns) == 0 or len(target_patterns) == 0:
            pattern_overlap = 0.0
        else:
            shared = source_patterns & target_patterns
            pattern_overlap = len(shared) / len(source_patterns | target_patterns)

        # 2. Module overlap
        source_modules = set(source_node.emphasized_modules)
        target_modules = set(target_node.emphasized_modules)

        if len(source_modules) == 0 or len(target_modules) == 0:
            module_overlap = 0.0
        else:
            shared_modules = source_modules & target_modules
            module_overlap = len(shared_modules) / len(source_modules | target_modules)

        # 3. Empirical performance (if edge exists)
        edge_key = (source_puzzle, target_puzzle)
        if edge_key in self.transfer_edges:
            empirical_gain = self.transfer_edges[edge_key].performance_gain
        else:
            empirical_gain = 0.0

        # Weighted combination
        transfer_score = (
            0.4 * pattern_overlap +
            0.3 * module_overlap +
            0.3 * empirical_gain
        )

        return min(1.0, max(0.0, transfer_score))

    def update_transfer_edges(self):
        """Recompute all transfer edges based on current data"""
        puzzles = list(self.puzzle_nodes.keys())

        for source in puzzles:
            for target in puzzles:
                if source == target:
                    continue

                # Compute transfer score
                score = self.compute_transfer_score(source, target)

                if score > 0.1:  # Only add meaningful edges
                    # Find shared patterns
                    source_patterns = set(self.pattern_frequency[source].keys())
                    target_patterns = set(self.pattern_frequency[target].keys())
                    shared = list(source_patterns & target_patterns)

                    edge = TransferEdge(
                        source_puzzle=source,
                        target_puzzle=target,
                        transfer_score=score,
                        shared_patterns=shared,
                        performance_gain=0.0,  # Updated empirically
                        num_observations=0
                    )

                    self.add_transfer_edge(edge)

    def get_curriculum_order(self, strategy: str = "transfer") -> List[str]:
        """
        Get recommended curriculum order

        Args:
            strategy: Ordering strategy
                - "difficulty": Easy to hard
                - "transfer": Maximize knowledge transfer
                - "modules": Balance module coverage

        Returns:
            List of puzzle IDs in recommended order
        """
        if strategy == "difficulty":
            # Sort by difficulty
            puzzles = sorted(
                self.puzzle_nodes.values(),
                key=lambda p: p.difficulty
            )
            return [p.puzzle_id for p in puzzles]

        elif strategy == "transfer":
            # Topological sort (if DAG) or greedy transfer path
            try:
                order = list(nx.topological_sort(self.graph))
            except nx.NetworkXError:
                # Graph has cycles, use greedy approach
                order = self._greedy_transfer_order()
            return order

        elif strategy == "modules":
            # Balance module coverage
            return self._balanced_module_order()

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _greedy_transfer_order(self) -> List[str]:
        """Greedy algorithm for transfer-optimal ordering"""
        puzzles = list(self.puzzle_nodes.keys())
        ordered = []
        remaining = set(puzzles)

        # Start with easiest
        current = min(
            remaining,
            key=lambda p: self.puzzle_nodes[p].difficulty
        )
        ordered.append(current)
        remaining.remove(current)

        # Greedily pick next puzzle with best transfer from current
        while remaining:
            best_next = max(
                remaining,
                key=lambda p: self.compute_transfer_score(current, p)
            )
            ordered.append(best_next)
            remaining.remove(best_next)
            current = best_next

        return ordered

    def _balanced_module_order(self) -> List[str]:
        """Order puzzles to balance module coverage"""
        puzzles = list(self.puzzle_nodes.values())

        # Track which modules have been covered
        covered_modules = set()
        ordered = []

        while puzzles:
            # Pick puzzle that adds most new modules
            best = max(
                puzzles,
                key=lambda p: len(set(p.emphasized_modules) - covered_modules)
            )

            ordered.append(best.puzzle_id)
            covered_modules.update(best.emphasized_modules)
            puzzles.remove(best)

        return ordered

    def get_transfer_path(self, source: str, target: str) -> List[str]:
        """Get optimal transfer path from source to target puzzle"""
        try:
            path = nx.shortest_path(
                self.graph,
                source,
                target,
                weight=lambda u, v, d: 1.0 - d['weight']  # Higher weight = shorter path
            )
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def visualize(self, output_path: str = "meta_graph.png"):
        """Visualize meta-graph (requires matplotlib, graphviz)"""
        import matplotlib.pyplot as plt

        pos = nx.spring_layout(self.graph, k=2, iterations=50)

        # Draw nodes
        node_colors = [
            self.puzzle_nodes[n].success_rate
            for n in self.graph.nodes()
        ]

        nx.draw_networkx_nodes(
            self.graph, pos,
            node_color=node_colors,
            node_size=1000,
            cmap=plt.cm.RdYlGn,
            vmin=0, vmax=1
        )

        # Draw edges
        edge_weights = [
            self.graph[u][v]['weight']
            for u, v in self.graph.edges()
        ]

        nx.draw_networkx_edges(
            self.graph, pos,
            width=[w*3 for w in edge_weights],
            alpha=0.6,
            edge_color=edge_weights,
            edge_cmap=plt.cm.Blues,
            edge_vmin=0, edge_vmax=1
        )

        # Draw labels
        labels = {n: self.puzzle_nodes[n].puzzle_name for n in self.graph.nodes()}
        nx.draw_networkx_labels(self.graph, pos, labels, font_size=8)

        plt.axis('off')
        plt.title("Meta-Graph: Puzzle Knowledge Transfer")
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"Meta-graph visualization saved: {output_path}")

    def save(self, path: str):
        """Save meta-graph to disk"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'graph': self.graph,
            'puzzle_nodes': self.puzzle_nodes,
            'transfer_edges': self.transfer_edges,
            'pattern_frequency': dict(self.pattern_frequency)
        }

        with open(path, 'wb') as f:
            pickle.dump(data, f)

        print(f"Meta-graph saved: {path}")

    def load(self, path: str):
        """Load meta-graph from disk"""
        with open(path, 'rb') as f:
            data = pickle.load(f)

        self.graph = data['graph']
        self.puzzle_nodes = data['puzzle_nodes']
        self.transfer_edges = data['transfer_edges']
        self.pattern_frequency = defaultdict(lambda: defaultdict(int), data['pattern_frequency'])

        print(f"Meta-graph loaded: {path}")
        print(f"  Puzzles: {len(self.puzzle_nodes)}")
        print(f"  Transfer edges: {len(self.transfer_edges)}")

    def get_statistics(self) -> Dict:
        """Get meta-graph statistics"""
        return {
            "num_puzzles": len(self.puzzle_nodes),
            "num_transfer_edges": len(self.transfer_edges),
            "avg_success_rate": np.mean([p.success_rate for p in self.puzzle_nodes.values()]),
            "total_attempts": sum(p.num_attempts for p in self.puzzle_nodes.values()),
            "graph_density": nx.density(self.graph),
            "num_patterns": sum(len(patterns) for patterns in self.pattern_frequency.values())
        }


if __name__ == "__main__":
    # Test meta-graph
    print("Testing Meta-Graph for Transfer Learning...")
    print("="*60)

    # Create meta-graph
    meta = MetaGraph()

    # Add puzzles
    puzzles = [
        PuzzleNode("p1", "Standard Klotski", 0.5, emphasized_modules=["VIS", "DLPFC"]),
        PuzzleNode("p2", "Visual Puzzle", 0.3, emphasized_modules=["VIS", "SOM", "AUD"]),
        PuzzleNode("p3", "Planning Puzzle", 0.7, emphasized_modules=["DLPFC", "OFC", "ACC"]),
        PuzzleNode("p4", "Memory Puzzle", 0.6, emphasized_modules=["MTL", "INS", "ACC"]),
        PuzzleNode("p5", "Integration Puzzle", 0.9, emphasized_modules=["DMN", "all"])
    ]

    for p in puzzles:
        meta.add_puzzle(p)

    print(f"Added {len(puzzles)} puzzles")

    # Simulate training episodes
    print("\nSimulating training...")
    for i in range(100):
        puzzle_id = f"p{(i % 5) + 1}"
        success = np.random.rand() < (1.0 - puzzles[i % 5].difficulty)
        steps = np.random.randint(10, 100)

        meta.update_puzzle_stats(puzzle_id, success, steps)

        # Record some patterns
        patterns = ["move_vertical", "move_horizontal", "corner_strategy"]
        for pattern in patterns:
            if np.random.rand() < 0.3:
                meta.record_pattern_usage(puzzle_id, pattern)

    # Compute transfer edges
    print("\nComputing transfer edges...")
    meta.update_transfer_edges()

    # Get curriculum order
    print("\nCurriculum orders:")
    for strategy in ["difficulty", "transfer", "modules"]:
        order = meta.get_curriculum_order(strategy)
        print(f"\n{strategy.capitalize()} strategy:")
        for i, pid in enumerate(order):
            p = meta.puzzle_nodes[pid]
            print(f"  {i+1}. {p.puzzle_name} (difficulty: {p.difficulty:.2f}, "
                  f"success: {p.success_rate:.2f})")

    # Statistics
    print("\nMeta-graph statistics:")
    stats = meta.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Save/load
    print("\nTesting save/load...")
    meta.save("test_meta_graph.pkl")

    meta2 = MetaGraph()
    meta2.load("test_meta_graph.pkl")

    print("\n" + "="*60)
    print("Meta-Graph test complete!")

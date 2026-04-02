"""
State-Graph Mapper

Maps puzzle board states to brain connectome graph representations.
Analyzes cognitive implications of piece configurations.

Key concepts:
- Each piece position represents a brain module state
- Piece adjacency maps to information flow in the connectome
- DMN reaching exit = conscious integration achieved
"""

from typing import Dict, List, Set, Tuple, Optional
import networkx as nx
import numpy as np

from neurosymbolic.core.brain_graph import BrainConnectomeGraph
from neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece


class StateGraphMapper:
    """
    Maps puzzle states to brain graph representations

    Analyzes:
    - Module activation patterns
    - Information flow between modules
    - Integration coherence
    - Cognitive metrics
    """

    def __init__(self, brain_graph: BrainConnectomeGraph):
        """
        Initialize mapper with brain connectome graph

        Args:
            brain_graph: BrainConnectomeGraph instance
        """
        self.brain_graph = brain_graph

        # Mapping from piece ID to module ID
        self.piece_to_module = {
            'G': 'DMN',    # Default Mode Network (2x2, goal piece)
            'V': 'VIS',    # Visual (1x2 vertical)
            'A': 'AUD',    # Auditory (1x2 vertical)
            'S': 'SOM',    # Somatosensory (1x2 vertical)
            'L': 'LAN',    # Language (1x2 vertical)
            'D': 'DLPFC',  # Dorsolateral PFC (2x1 horizontal)
            'C': 'ACC',    # Anterior Cingulate (1x1)
            'I': 'INS',    # Insula (1x1)
            'M': 'MTL',    # Medial Temporal Lobe (1x1)
            'O': 'OFC',    # Orbitofrontal Cortex (1x1)
        }

        self.module_to_piece = {v: k for k, v in self.piece_to_module.items()}

    def get_module_for_piece(self, piece_id: str) -> Optional[str]:
        """Get brain module for a puzzle piece"""
        return self.piece_to_module.get(piece_id)

    def get_piece_for_module(self, module_id: str) -> Optional[str]:
        """Get puzzle piece for a brain module"""
        return self.module_to_piece.get(module_id)

    def get_adjacent_pieces(self, puzzle: PuzzleState, piece_id: str) -> Set[str]:
        """
        Get pieces that are physically adjacent (touching) to given piece

        Adjacent means sharing an edge (not just corner)
        """
        if piece_id not in puzzle.pieces:
            return set()

        piece = puzzle.pieces[piece_id]
        occupied_cells = piece.get_occupied_cells()

        adjacent_pieces = set()

        for x, y in occupied_cells:
            # Check four directions: up, down, left, right
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                neighbor_cell = (x + dx, y + dy)
                neighbor_piece = puzzle.get_piece_at(*neighbor_cell)

                if neighbor_piece and neighbor_piece.piece_id != piece_id:
                    adjacent_pieces.add(neighbor_piece.piece_id)

        return adjacent_pieces

    def get_active_connections(self, puzzle: PuzzleState) -> List[Tuple[str, str]]:
        """
        Get active brain module connections based on piece adjacency

        Returns:
            List of (module1, module2) tuples for adjacent pieces
        """
        connections = []

        for piece_id in puzzle.pieces.keys():
            module_id = self.get_module_for_piece(piece_id)
            if not module_id:
                continue

            adjacent_pieces = self.get_adjacent_pieces(puzzle, piece_id)

            for adj_piece_id in adjacent_pieces:
                adj_module_id = self.get_module_for_piece(adj_piece_id)
                if not adj_module_id:
                    continue

                # Only add if connection exists in brain graph
                if self.brain_graph.graph.has_edge(module_id, adj_module_id):
                    # Avoid duplicates by sorting
                    edge = tuple(sorted([module_id, adj_module_id]))
                    if edge not in [tuple(sorted(c)) for c in connections]:
                        connections.append((module_id, adj_module_id))

        return connections

    def calculate_integration_score(self, puzzle: PuzzleState) -> float:
        """
        Calculate integration score based on active connections

        Higher score = more brain modules are communicating
        Range: 0.0 to 1.0
        """
        active_connections = self.get_active_connections(puzzle)
        total_possible_connections = self.brain_graph.graph.number_of_edges()

        if total_possible_connections == 0:
            return 0.0

        return len(active_connections) / total_possible_connections

    def calculate_coherence(self, puzzle: PuzzleState) -> float:
        """
        Calculate coherence metric (how well-connected the active network is)

        Uses clustering coefficient of active subgraph
        Range: 0.0 to 1.0
        """
        active_connections = self.get_active_connections(puzzle)

        if not active_connections:
            return 0.0

        # Create subgraph of active modules
        active_modules = set()
        for m1, m2 in active_connections:
            active_modules.add(m1)
            active_modules.add(m2)

        if len(active_modules) < 2:
            return 0.0

        subgraph = self.brain_graph.graph.subgraph(active_modules)

        # Calculate average clustering coefficient
        return nx.average_clustering(subgraph)

    def calculate_dmn_distance_to_exit(self, puzzle: PuzzleState) -> int:
        """
        Calculate how far DMN (piece 'G') is from the exit position

        Returns:
            Manhattan distance (number of moves needed if board was empty)
        """
        if 'G' not in puzzle.pieces:
            return 999

        dmn_piece = puzzle.pieces['G']

        # Target position for DMN is (1, 3) to reach exit at (1-2, 4)
        target_x, target_y = 1, 3
        distance = abs(dmn_piece.x - target_x) + abs(dmn_piece.y - target_y)

        return distance

    def calculate_consciousness_metric(self, puzzle: PuzzleState) -> float:
        """
        Calculate 'consciousness' metric

        Consciousness emerges when:
        1. DMN is near/at exit (integration goal)
        2. High coherence (modules working together)
        3. High integration (many connections active)

        Range: 0.0 to 1.0
        """
        # Component 1: DMN proximity to exit (0.4 weight)
        dmn_distance = self.calculate_dmn_distance_to_exit(puzzle)
        max_distance = 4  # Maximum possible distance on 4x5 board
        dmn_score = max(0.0, 1.0 - (dmn_distance / max_distance))

        # Component 2: Coherence (0.3 weight)
        coherence = self.calculate_coherence(puzzle)

        # Component 3: Integration (0.3 weight)
        integration = self.calculate_integration_score(puzzle)

        consciousness = (
            0.4 * dmn_score +
            0.3 * coherence +
            0.3 * integration
        )

        return consciousness

    def get_module_states(self, puzzle: PuzzleState) -> Dict[str, Dict]:
        """
        Get state information for each brain module

        Returns:
            Dict mapping module_id to state info
        """
        states = {}

        for piece_id, piece in puzzle.pieces.items():
            module_id = self.get_module_for_piece(piece_id)
            if not module_id:
                continue

            adjacent_pieces = self.get_adjacent_pieces(puzzle, piece_id)
            adjacent_modules = [
                self.get_module_for_piece(p)
                for p in adjacent_pieces
                if self.get_module_for_piece(p)
            ]

            states[module_id] = {
                'piece_id': piece_id,
                'position': (piece.x, piece.y),
                'size': (piece.w, piece.h),
                'adjacent_modules': adjacent_modules,
                'num_active_connections': len(adjacent_modules),
            }

        return states

    def analyze_state(self, puzzle: PuzzleState) -> Dict:
        """
        Comprehensive state analysis

        Returns:
            Dict with all cognitive metrics
        """
        return {
            'is_solved': puzzle.is_solved(),
            'integration_score': self.calculate_integration_score(puzzle),
            'coherence': self.calculate_coherence(puzzle),
            'consciousness_metric': self.calculate_consciousness_metric(puzzle),
            'dmn_distance_to_exit': self.calculate_dmn_distance_to_exit(puzzle),
            'active_connections': len(self.get_active_connections(puzzle)),
            'module_states': self.get_module_states(puzzle),
        }

    def get_information_flow_matrix(self, puzzle: PuzzleState) -> np.ndarray:
        """
        Get information flow matrix based on active connections

        Returns:
            10x10 adjacency matrix for active brain module connections
        """
        module_ids = sorted(self.brain_graph.MODULES.keys())
        n = len(module_ids)
        module_to_idx = {m: i for i, m in enumerate(module_ids)}

        matrix = np.zeros((n, n))

        active_connections = self.get_active_connections(puzzle)
        for m1, m2 in active_connections:
            i1 = module_to_idx[m1]
            i2 = module_to_idx[m2]
            matrix[i1, i2] = 1.0
            matrix[i2, i1] = 1.0  # Undirected

        return matrix

    def __repr__(self):
        return f"StateGraphMapper(modules={len(self.piece_to_module)})"


if __name__ == "__main__":
    # Test the mapper
    print("Initializing State-Graph Mapper...")

    brain_graph = BrainConnectomeGraph()
    mapper = StateGraphMapper(brain_graph)

    print(f"Mapper: {mapper}")
    print(f"Piece-to-Module mapping: {mapper.piece_to_module}")

    # Load puzzle
    layout_path = r"C:\Users\User\Downloads\Klotski_NeuroLayout.json"
    puzzle = PuzzleState(layout_file=layout_path)

    print("\nPuzzle Board:")
    print(puzzle.get_board_string())

    print("\nAnalyzing state...")
    analysis = mapper.analyze_state(puzzle)

    print("\nCognitive Metrics:")
    print(f"  Is Solved: {analysis['is_solved']}")
    print(f"  Integration Score: {analysis['integration_score']:.3f}")
    print(f"  Coherence: {analysis['coherence']:.3f}")
    print(f"  Consciousness Metric: {analysis['consciousness_metric']:.3f}")
    print(f"  DMN Distance to Exit: {analysis['dmn_distance_to_exit']}")
    print(f"  Active Connections: {analysis['active_connections']}")

    print("\nModule States:")
    for module_id, state in sorted(analysis['module_states'].items()):
        print(f"  {module_id:6} at {state['position']}: {state['num_active_connections']} active connections")
        print(f"         Adjacent: {', '.join(state['adjacent_modules'])}")

    print("\nActive Brain Connections:")
    connections = mapper.get_active_connections(puzzle)
    for m1, m2 in sorted(connections):
        print(f"  {m1} <-> {m2}")

    print("\nInformation Flow Matrix:")
    matrix = mapper.get_information_flow_matrix(puzzle)
    module_ids = sorted(brain_graph.MODULES.keys())
    print("      " + " ".join(f"{m:6}" for m in module_ids))
    for i, module in enumerate(module_ids):
        row_str = " ".join(f"{int(matrix[i, j]):6}" for j in range(len(module_ids)))
        print(f"  {module:6} {row_str}")

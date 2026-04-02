"""
Quick Klotski Puzzle Solver (BFS Search)

Uses BFS to guarantee shortest path solution.
Tests if puzzle is solvable and finds optimal solution.

Usage:
    python demos/quick_solve_klotski_bfs.py
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from collections import deque

# Add learning_engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'learning_engine', 'klotski'))

try:
    from neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece
    PUZZLE_STATE_AVAILABLE = True
except ImportError as e:
    print(f"[ERROR] Cannot import puzzle_state: {e}")
    PUZZLE_STATE_AVAILABLE = False
    sys.exit(1)


@dataclass
class BFSNode:
    """Node in BFS search tree"""
    state: PuzzleState
    parent: Optional['BFSNode']
    move: Optional[Tuple[str, int, int, str]]  # (piece_id, new_x, new_y, direction)
    depth: int


class KlotskiBFSSolver:
    """BFS solver for Klotski puzzle - guarantees shortest path"""

    def __init__(self, initial_state: PuzzleState):
        self.initial_state = initial_state
        self.visited_states: Dict[str, int] = {}  # state_hash -> depth
        self.nodes_explored = 0

    def solve(self, max_nodes: int = 30000) -> Optional[List[Tuple[str, int, int, str]]]:
        """
        Solve puzzle using BFS search

        BFS guarantees shortest path but explores all nodes at each depth level.
        More memory intensive than A* but finds optimal solution.

        Returns:
            List of moves [(piece_id, new_x, new_y, direction), ...] or None if no solution
        """
        print(f"[KlotskiBFSSolver] Starting BFS search...")
        print(f"[KlotskiBFSSolver] Initial state hash: {self.initial_state.get_state_hash()}")
        print(f"[KlotskiBFSSolver] Goal: DMN (G) at position (1, 3)")

        # BFS queue
        queue = deque()
        initial_node = BFSNode(
            state=self.initial_state.clone(),
            parent=None,
            move=None,
            depth=0
        )
        queue.append(initial_node)

        # Track visited states
        initial_hash = self.initial_state.get_state_hash()
        self.visited_states[initial_hash] = 0

        # Track max depth reached
        max_depth_reached = 0

        while queue and self.nodes_explored < max_nodes:
            # Get next node (FIFO - breadth first)
            current = queue.popleft()
            self.nodes_explored += 1

            # Update max depth
            if current.depth > max_depth_reached:
                max_depth_reached = current.depth
                print(f"[KlotskiBFSSolver] Depth {max_depth_reached}: "
                      f"{self.nodes_explored} nodes explored, "
                      f"queue size: {len(queue)}")

            # Check if solved
            if current.state.is_solved():
                print(f"[KlotskiBFSSolver] Solution found!")
                print(f"[KlotskiBFSSolver] Nodes explored: {self.nodes_explored}")
                print(f"[KlotskiBFSSolver] Solution length: {current.depth} moves (optimal)")
                print(f"[KlotskiBFSSolver] States visited: {len(self.visited_states)}")
                return self._reconstruct_path(current)

            # Expand neighbors
            for piece_id in current.state.pieces.keys():
                valid_moves = current.state.get_valid_moves(piece_id)

                for new_x, new_y, direction in valid_moves:
                    # Create new state
                    new_state = current.state.clone()
                    new_state.move_piece(piece_id, new_x, new_y)

                    # Check if already visited at same or better depth
                    state_hash = new_state.get_state_hash()
                    new_depth = current.depth + 1

                    if state_hash in self.visited_states:
                        # Already visited at same or better depth
                        if self.visited_states[state_hash] <= new_depth:
                            continue

                    # Mark as visited at this depth
                    self.visited_states[state_hash] = new_depth

                    # Create new node
                    new_node = BFSNode(
                        state=new_state,
                        parent=current,
                        move=(piece_id, new_x, new_y, direction),
                        depth=new_depth
                    )

                    # Add to queue
                    queue.append(new_node)

        print(f"[KlotskiBFSSolver] No solution found after {self.nodes_explored} nodes")
        print(f"[KlotskiBFSSolver] Max depth reached: {max_depth_reached}")
        print(f"[KlotskiBFSSolver] States visited: {len(self.visited_states)}")
        return None

    def _reconstruct_path(self, node: BFSNode) -> List[Tuple[str, int, int, str]]:
        """Reconstruct solution path from goal node"""
        path = []
        current = node

        while current.parent is not None:
            path.append(current.move)
            current = current.parent

        return list(reversed(path))


def visualize_solution(initial_state: PuzzleState, moves: List[Tuple[str, int, int, str]]):
    """Display solution step-by-step"""
    print("\n" + "="*70)
    print("SOLUTION VISUALIZATION")
    print("="*70)

    state = initial_state.clone()

    # Show initial state
    print(f"\nInitial State:")
    print(state.get_board_string())
    print(f"DMN (G) position: ({state.pieces['G'].x}, {state.pieces['G'].y})")

    # Show each move
    for i, (piece_id, new_x, new_y, direction) in enumerate(moves, 1):
        piece = state.pieces[piece_id]
        old_x, old_y = piece.x, piece.y

        state.move_piece(piece_id, new_x, new_y)

        # Get piece info
        module_name = piece.module if hasattr(piece, 'module') else piece_id

        print(f"\nMove {i}: {module_name} ({piece_id}) moves {direction}")
        print(f"  From: ({old_x}, {old_y}) -> To: ({new_x}, {new_y})")

        # Show board every 10 moves or at end
        if i % 10 == 0 or i == len(moves):
            print(state.get_board_string())
            print(f"  DMN (G) at: ({state.pieces['G'].x}, {state.pieces['G'].y})")

    # Show final state
    print(f"\n" + "="*70)
    print("FINAL STATE")
    print("="*70)
    print(state.get_board_string())
    print(f"DMN (G) position: ({state.pieces['G'].x}, {state.pieces['G'].y})")
    print(f"Puzzle solved: {state.is_solved()}")


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("KLOTSKI PUZZLE SOLVER (BFS Search)")
    print("="*70)
    print("\nBFS guarantees shortest path solution")
    print("More memory intensive than A* but finds optimal solution")

    # Find layout file
    layout_path = Path("C:/Users/User/Downloads/Klotski_NeuroLayout.json")

    if not layout_path.exists():
        print(f"\n[ERROR] Layout file not found: {layout_path}")
        print("Please ensure Klotski_NeuroLayout.json is in Downloads folder")
        return

    print(f"\n[INFO] Loading puzzle from: {layout_path}")

    # Load initial state
    initial_state = PuzzleState(layout_file=str(layout_path))

    print(f"[INFO] Puzzle loaded: {len(initial_state.pieces)} pieces")
    print(f"[INFO] Board size: {initial_state.board_width}x{initial_state.board_height}")
    print(f"[INFO] Empty cells: {len(initial_state.get_empty_cells())}")

    # Show initial board
    print("\nInitial Board Configuration:")
    print(initial_state.get_board_string())

    print("\nPieces:")
    for piece_id, piece in sorted(initial_state.pieces.items()):
        module_name = piece.module if hasattr(piece, 'module') else "Unknown"
        print(f"  {piece_id} ({module_name}): pos=({piece.x},{piece.y}), size={piece.w}x{piece.h}")

    # Create solver
    solver = KlotskiBFSSolver(initial_state)

    # Solve puzzle
    print("\n" + "="*70)
    print("SOLVING PUZZLE")
    print("="*70)

    # BFS needs to explore many nodes for this difficult puzzle
    # Optimal solution is ~81 moves, so we need significant depth
    moves = solver.solve(max_nodes=150000)

    if moves:
        print(f"\n[SUCCESS] Solution found: {len(moves)} moves (OPTIMAL)")
        print(f"[SUCCESS] Nodes explored: {solver.nodes_explored}")
        print(f"[SUCCESS] States visited: {len(solver.visited_states)}")

        # Visualize solution
        visualize_solution(initial_state, moves)

        # Summary
        print("\n" + "="*70)
        print("SOLUTION SUMMARY")
        print("="*70)
        print(f"Total moves: {len(moves)} (guaranteed optimal by BFS)")
        print(f"Nodes explored: {solver.nodes_explored}")
        print(f"Search efficiency: {len(moves) / solver.nodes_explored:.2%}")

        # Piece movement stats
        piece_moves = {}
        for piece_id, _, _, _ in moves:
            piece_moves[piece_id] = piece_moves.get(piece_id, 0) + 1

        print("\nMoves per piece:")
        for piece_id, count in sorted(piece_moves.items(), key=lambda x: -x[1]):
            piece = initial_state.pieces[piece_id]
            module_name = piece.module if hasattr(piece, 'module') else piece_id
            print(f"  {module_name} ({piece_id}): {count} moves")

    else:
        print(f"\n[FAILED] No solution found after {solver.nodes_explored} nodes")
        print(f"[FAILED] States visited: {len(solver.visited_states)}")
        print("\nThis may indicate:")
        print("  1. Puzzle requires > 30000 node explorations (try increasing limit)")
        print("  2. Puzzle configuration is unsolvable from this initial state")

    print("\n" + "="*70)
    print("DONE")
    print("="*70)


if __name__ == "__main__":
    main()

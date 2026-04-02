"""
Quick Klotski Puzzle Solver (A* Search)

Simple solver that finds a solution path without generating the full 25,955-node graph.
Uses A* search with Manhattan distance heuristic.

Usage:
    python demos/quick_solve_klotski.py
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass
import heapq
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
class SearchNode:
    """Node in A* search tree"""
    state: PuzzleState
    parent: Optional['SearchNode']
    move: Optional[Tuple[str, int, int, str]]  # (piece_id, new_x, new_y, direction)
    g_cost: int  # Cost from start
    h_cost: int  # Heuristic to goal

    @property
    def f_cost(self):
        return self.g_cost + self.h_cost

    def __lt__(self, other):
        return self.f_cost < other.f_cost


class KlotskiSolver:
    """Simple A* solver for Klotski puzzle"""

    def __init__(self, initial_state: PuzzleState):
        self.initial_state = initial_state
        self.visited_states: Set[str] = set()
        self.nodes_explored = 0

    def heuristic(self, state: PuzzleState) -> int:
        """
        Manhattan distance from DMN piece (G) to goal position

        Goal: DMN at (1, 3) to occupy cells (1,3), (2,3), (1,4), (2,4)
        """
        if 'G' not in state.pieces:
            return 999  # Invalid state

        dmn = state.pieces['G']
        goal_x, goal_y = 1, 3

        # Manhattan distance
        return abs(dmn.x - goal_x) + abs(dmn.y - goal_y)

    def solve(self, max_nodes: int = 50000) -> Optional[List[Tuple[str, int, int, str]]]:
        """
        Solve puzzle using A* search

        Returns:
            List of moves [(piece_id, new_x, new_y, direction), ...] or None if no solution
        """
        print(f"[KlotskiSolver] Starting A* search...")
        print(f"[KlotskiSolver] Initial state hash: {self.initial_state.get_state_hash()}")
        print(f"[KlotskiSolver] Initial heuristic: {self.heuristic(self.initial_state)}")

        # Priority queue: (f_cost, node)
        open_set = []
        initial_node = SearchNode(
            state=self.initial_state.clone(),
            parent=None,
            move=None,
            g_cost=0,
            h_cost=self.heuristic(self.initial_state)
        )
        heapq.heappush(open_set, (initial_node.f_cost, initial_node))

        # Track visited states
        self.visited_states.add(self.initial_state.get_state_hash())

        while open_set and self.nodes_explored < max_nodes:
            # Get node with lowest f_cost
            _, current = heapq.heappop(open_set)
            self.nodes_explored += 1

            # Progress update
            if self.nodes_explored % 1000 == 0:
                print(f"[KlotskiSolver] Explored {self.nodes_explored} nodes, "
                      f"queue size: {len(open_set)}, "
                      f"g_cost: {current.g_cost}, "
                      f"h_cost: {current.h_cost}")

            # Check if solved
            if current.state.is_solved():
                print(f"[KlotskiSolver] Solution found!")
                print(f"[KlotskiSolver] Nodes explored: {self.nodes_explored}")
                print(f"[KlotskiSolver] Solution length: {current.g_cost} moves")
                return self._reconstruct_path(current)

            # Expand neighbors
            for piece_id in current.state.pieces.keys():
                valid_moves = current.state.get_valid_moves(piece_id)

                for new_x, new_y, direction in valid_moves:
                    # Create new state
                    new_state = current.state.clone()
                    new_state.move_piece(piece_id, new_x, new_y)

                    # Check if already visited
                    state_hash = new_state.get_state_hash()
                    if state_hash in self.visited_states:
                        continue

                    # Mark as visited
                    self.visited_states.add(state_hash)

                    # Create new node
                    new_node = SearchNode(
                        state=new_state,
                        parent=current,
                        move=(piece_id, new_x, new_y, direction),
                        g_cost=current.g_cost + 1,
                        h_cost=self.heuristic(new_state)
                    )

                    # Add to open set
                    heapq.heappush(open_set, (new_node.f_cost, new_node))

        print(f"[KlotskiSolver] No solution found after {self.nodes_explored} nodes")
        return None

    def _reconstruct_path(self, node: SearchNode) -> List[Tuple[str, int, int, str]]:
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
        print(f"  From: ({old_x}, {old_y}) → To: ({new_x}, {new_y})")

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
    print("KLOTSKI PUZZLE SOLVER (A* Search)")
    print("="*70)

    # Find layout file
    layout_path = Path("C:/Users/User/Downloads/Klotski_NeuroLayout.json")

    if not layout_path.exists():
        print(f"[ERROR] Layout file not found: {layout_path}")
        print("Please ensure Klotski_NeuroLayout.json is in Downloads folder")
        return

    print(f"[INFO] Loading puzzle from: {layout_path}")

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
    solver = KlotskiSolver(initial_state)

    # Solve puzzle
    print("\n" + "="*70)
    print("SOLVING PUZZLE")
    print("="*70)

    moves = solver.solve(max_nodes=100000)

    if moves:
        print(f"\n[SUCCESS] Solution found: {len(moves)} moves")
        print(f"[SUCCESS] Nodes explored: {solver.nodes_explored}")
        print(f"[SUCCESS] States visited: {len(solver.visited_states)}")

        # Visualize solution
        visualize_solution(initial_state, moves)

        # Summary
        print("\n" + "="*70)
        print("SOLUTION SUMMARY")
        print("="*70)
        print(f"Total moves: {len(moves)}")
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
        print("\nTry increasing max_nodes parameter")

    print("\n" + "="*70)
    print("DONE")
    print("="*70)


if __name__ == "__main__":
    main()

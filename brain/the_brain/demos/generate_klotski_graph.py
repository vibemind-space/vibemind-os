"""
Full Klotski State Graph Generator

Generates the complete state graph for Klotski puzzle with:
- All 25,955 reachable states
- Optimal distances from initial state
- Bidirectional BFS for efficiency
- Graph saved as JSON for fast loading

This is a ONE-TIME generation (2-4 hours) that enables:
- Instant optimal distance lookup
- RL training environment
- Curriculum learning (easy → hard states)

Usage:
    python demos/generate_klotski_graph.py                    # Full graph
    python demos/generate_klotski_graph.py --max-depth 30     # Mini test graph
    python demos/generate_klotski_graph.py --output path.json # Custom output
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass, asdict
from collections import deque
from datetime import datetime
import time

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
class GraphNode:
    """Node in state graph"""
    state_hash: str
    distance_from_start: int
    distance_to_goal: Optional[int]  # Will be saved as 'solution_dist' in JSON
    representation: str  # Compact board string (no newlines)
    neighbors: List[Tuple[str, str, int, int, str]]  # [(next_hash, piece_id, new_x, new_y, direction), ...]
    is_goal: bool


class KlotskiGraphGenerator:
    """
    Generates complete Klotski state graph using bidirectional BFS

    Algorithm:
    1. Forward BFS from initial state (compute distance_from_start)
    2. Backward BFS from goal state (compute distance_to_goal)
    3. Store all reachable states with optimal distances
    4. Save as JSON for fast loading
    """

    def __init__(self, initial_state: PuzzleState, max_depth: Optional[int] = None):
        self.initial_state = initial_state
        self.max_depth = max_depth
        self.graph: Dict[str, GraphNode] = {}
        self.states_explored = 0
        self.start_time = time.time()
        # Cache for state hash -> representation
        self._representation_cache: Dict[str, str] = {}

    def _get_compact_representation(self, state: PuzzleState) -> str:
        """Get compact board representation (no newlines)"""
        board_str = state.get_board_string()
        # Remove newlines to get compact representation
        return board_str.replace('\n', '')

    def generate(self) -> Dict[str, GraphNode]:
        """
        Generate complete state graph

        Returns:
            Dictionary mapping state_hash -> GraphNode
        """
        print("\n" + "="*70)
        print("KLOTSKI STATE GRAPH GENERATOR")
        print("="*70)
        print("\nGenerating reachable state graph...")
        if self.max_depth:
            print(f"Max depth: {self.max_depth} (limited graph for testing)")
            print("Expected: ~2,000-5,000 states")
        else:
            print("Expected: ~25,955 states")
        print("Algorithm: Bidirectional BFS")
        print("Estimated time: 2-4 hours (full) / 5-10 min (limited)")
        print("\n" + "="*70)

        # Step 1: Forward BFS (distance from start)
        print("\n[STEP 1] Forward BFS: Computing distances from initial state...")
        self._forward_bfs()

        print(f"\n[RESULT] Forward BFS complete:")
        print(f"  States discovered: {len(self.graph)}")
        print(f"  States explored: {self.states_explored}")
        print(f"  Time elapsed: {time.time() - self.start_time:.1f}s")

        # Step 2: Backward BFS (distance to goal)
        print("\n[STEP 2] Backward BFS: Computing distances to goal state...")
        self._backward_bfs()

        print(f"\n[RESULT] Backward BFS complete:")
        print(f"  Goal states found: {sum(1 for n in self.graph.values() if n.is_goal)}")
        print(f"  States with goal distance: {sum(1 for n in self.graph.values() if n.distance_to_goal is not None)}")
        print(f"  Time elapsed: {time.time() - self.start_time:.1f}s")

        # Step 3: Statistics
        self._print_statistics()

        return self.graph

    def _forward_bfs(self):
        """Forward BFS from initial state"""
        initial_hash = self.initial_state.get_state_hash()
        initial_repr = self._get_compact_representation(self.initial_state)

        # Initialize queue
        queue = deque([self.initial_state.clone()])

        # Track visited
        visited = {initial_hash}

        # Create initial node
        self.graph[initial_hash] = GraphNode(
            state_hash=initial_hash,
            distance_from_start=0,
            distance_to_goal=None,
            representation=initial_repr,
            neighbors=[],
            is_goal=self.initial_state.is_solved()
        )

        depth = 0
        nodes_at_depth = {0: 1}
        last_report_time = time.time()

        while queue:
            current_state = queue.popleft()
            current_hash = current_state.get_state_hash()
            current_node = self.graph[current_hash]
            current_depth = current_node.distance_from_start

            self.states_explored += 1

            # Check max depth limit
            if self.max_depth and current_depth >= self.max_depth:
                continue

            # Report progress every 5 seconds
            if time.time() - last_report_time > 5:
                print(f"  Depth {current_depth}: "
                      f"{len(self.graph)} states, "
                      f"{len(queue)} in queue, "
                      f"{self.states_explored} explored")
                last_report_time = time.time()

            # Update depth tracking
            if current_depth > depth:
                depth = current_depth
                nodes_at_depth[depth] = 0

            # Expand neighbors
            for piece_id in current_state.pieces.keys():
                valid_moves = current_state.get_valid_moves(piece_id)

                for new_x, new_y, direction in valid_moves:
                    # Create new state
                    new_state = current_state.clone()
                    new_state.move_piece(piece_id, new_x, new_y)
                    new_hash = new_state.get_state_hash()

                    # Add neighbor to current node
                    current_node.neighbors.append((new_hash, piece_id, new_x, new_y, direction))

                    # Check if already visited
                    if new_hash in visited:
                        continue

                    # Mark as visited
                    visited.add(new_hash)

                    # Get compact representation
                    new_repr = self._get_compact_representation(new_state)

                    # Create new node
                    self.graph[new_hash] = GraphNode(
                        state_hash=new_hash,
                        distance_from_start=current_depth + 1,
                        distance_to_goal=None,
                        representation=new_repr,
                        neighbors=[],
                        is_goal=new_state.is_solved()
                    )

                    # Add to queue
                    queue.append(new_state)

                    # Update depth count
                    nodes_at_depth[current_depth + 1] = nodes_at_depth.get(current_depth + 1, 0) + 1

        # Final depth statistics
        print(f"\n  Depth distribution:")
        for d in sorted(nodes_at_depth.keys())[:10]:  # Show first 10 depths
            print(f"    Depth {d:2d}: {nodes_at_depth[d]:5d} states")
        if len(nodes_at_depth) > 10:
            print(f"    ... ({len(nodes_at_depth) - 10} more depths)")

    def _backward_bfs(self):
        """Backward BFS from goal states"""
        # Find all goal states
        goal_states = [hash for hash, node in self.graph.items() if node.is_goal]

        if not goal_states:
            print("  [WARNING] No goal states found in graph!")
            return

        print(f"  Starting from {len(goal_states)} goal state(s)")

        # Initialize queue with goal states
        queue = deque()
        visited = set()

        for goal_hash in goal_states:
            queue.append(goal_hash)
            visited.add(goal_hash)
            self.graph[goal_hash].distance_to_goal = 0

        last_report_time = time.time()
        depth = 0

        while queue:
            current_hash = queue.popleft()
            current_node = self.graph[current_hash]
            current_distance = current_node.distance_to_goal

            # Report progress
            if time.time() - last_report_time > 5:
                print(f"  Distance {current_distance}: "
                      f"{len(visited)} states visited, "
                      f"{len(queue)} in queue")
                last_report_time = time.time()

            # Find predecessors (states that lead to this state)
            for other_hash, other_node in self.graph.items():
                if other_hash in visited:
                    continue

                # Check if other_node has edge to current_node
                has_edge = any(next_hash == current_hash for next_hash, _, _, _, _ in other_node.neighbors)

                if has_edge:
                    # Set distance to goal
                    other_node.distance_to_goal = current_distance + 1
                    visited.add(other_hash)
                    queue.append(other_hash)

        print(f"  Backward BFS reached {len(visited)} states")

    def _print_statistics(self):
        """Print graph statistics"""
        print("\n" + "="*70)
        print("GRAPH STATISTICS")
        print("="*70)

        # Basic stats
        total_states = len(self.graph)
        goal_states = sum(1 for n in self.graph.values() if n.is_goal)
        states_with_goal_dist = sum(1 for n in self.graph.values() if n.distance_to_goal is not None)

        print(f"\nTotal states: {total_states}")
        print(f"Goal states: {goal_states}")
        print(f"States with goal distance: {states_with_goal_dist}")

        # Distance statistics
        max_dist_from_start = max((n.distance_from_start for n in self.graph.values()), default=0)
        max_dist_to_goal = max((n.distance_to_goal for n in self.graph.values() if n.distance_to_goal is not None), default=0)

        print(f"\nMax distance from start: {max_dist_from_start}")
        print(f"Max distance to goal: {max_dist_to_goal}")

        # Initial state distance to goal
        initial_hash = self.initial_state.get_state_hash()
        if initial_hash in self.graph:
            initial_node = self.graph[initial_hash]
            if initial_node.distance_to_goal is not None:
                print(f"\nOptimal solution length: {initial_node.distance_to_goal} moves")
            else:
                print("\n[WARNING] Initial state has no path to goal!")

        # Edge statistics
        total_edges = sum(len(n.neighbors) for n in self.graph.values())
        avg_degree = total_edges / total_states if total_states > 0 else 0

        print(f"\nTotal edges: {total_edges}")
        print(f"Average degree: {avg_degree:.2f}")

        # Time statistics
        elapsed = time.time() - self.start_time
        print(f"\nTotal time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"States per second: {total_states / elapsed:.1f}")

    def save_to_json(self, output_path: Path):
        """Save graph to JSON file"""
        print("\n" + "="*70)
        print("SAVING GRAPH")
        print("="*70)
        print(f"\nOutput file: {output_path}")

        # Convert to serializable format
        graph_data = {
            "metadata": {
                "total_states": len(self.graph),
                "goal_states": sum(1 for n in self.graph.values() if n.is_goal),
                "generated_at": datetime.now().isoformat(),
                "generation_time_seconds": time.time() - self.start_time,
                "initial_state_hash": self.initial_state.get_state_hash()
            },
            "states": {}
        }

        for state_hash, node in self.graph.items():
            graph_data["states"][state_hash] = {
                "solution_dist": node.distance_to_goal,  # Field name expected by environment
                "distance_from_start": node.distance_from_start,
                "representation": node.representation,  # Compact board string
                "is_goal": node.is_goal,
                "neighbors": [
                    {
                        "next_state": next_hash,
                        "piece_id": piece_id,
                        "new_x": new_x,
                        "new_y": new_y,
                        "direction": direction
                    }
                    for next_hash, piece_id, new_x, new_y, direction in node.neighbors
                ]
            }

        # Save to file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(graph_data, f, indent=2)

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"Graph saved: {file_size_mb:.2f} MB")
        print(f"States: {len(self.graph)}")
        print(f"File: {output_path}")


def main():
    """Main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Generate Klotski state graph for RL training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python demos/generate_klotski_graph.py                     # Full graph (~25,955 states)
    python demos/generate_klotski_graph.py --max-depth 30      # Mini test graph (~2,000 states)
    python demos/generate_klotski_graph.py --output data/mini.json --max-depth 20
        """
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum BFS depth (default: unlimited). Use 30 for ~2,000 states."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: learning_engine/klotski/Klotski-Webpage/data.json)"
    )
    parser.add_argument(
        "--layout",
        type=str,
        default=None,
        help="Layout JSON path (default: learning_engine/klotski/Klotski_NeuroLayout.json)"
    )
    args = parser.parse_args()

    print("\n" + "="*70)
    print("KLOTSKI STATE GRAPH GENERATOR")
    print("="*70)

    # Find layout file (relative to project root)
    project_root = Path(__file__).parent.parent
    if args.layout:
        layout_path = Path(args.layout)
    else:
        layout_path = project_root / "learning_engine" / "klotski" / "Klotski_NeuroLayout.json"

    if not layout_path.exists():
        print(f"\n[ERROR] Layout file not found: {layout_path}")
        print("Please run: python demos/generate_klotski_graph.py --layout path/to/layout.json")
        print("Or create the default layout at: learning_engine/klotski/Klotski_NeuroLayout.json")
        return

    print(f"\n[INFO] Loading puzzle from: {layout_path}")

    # Load initial state
    initial_state = PuzzleState(layout_file=str(layout_path))

    print(f"[INFO] Puzzle loaded: {len(initial_state.pieces)} pieces")
    print(f"[INFO] Board size: {initial_state.board_width}x{initial_state.board_height}")
    if args.max_depth:
        print(f"[INFO] Max depth: {args.max_depth} (limited graph)")

    # Show initial board
    print("\nInitial Board Configuration:")
    print(initial_state.get_board_string())

    # Create generator with optional max_depth
    generator = KlotskiGraphGenerator(initial_state, max_depth=args.max_depth)

    # Generate graph
    graph = generator.generate()

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    elif args.max_depth:
        # Use data/ for test graphs
        output_path = project_root / "data" / "mini_klotski_graph.json"
    else:
        # Full graph goes to Klotski-Webpage
        output_path = project_root / "learning_engine" / "klotski" / "Klotski-Webpage" / "data.json"

    generator.save_to_json(output_path)

    print("\n" + "="*70)
    print("COMPLETE")
    print("="*70)
    print("\nGraph generation successful!")
    print(f"Total states: {len(graph)}")
    print(f"Output file: {output_path}")
    print("\nNext steps:")
    print("1. Run integration test: python -m demos.run_evolutionary_training --neurosymbolic-mode")
    print("2. Start dashboard: python web/klotski_dashboard_server.py")
    print("3. Train brain with RL on puzzle")


if __name__ == "__main__":
    main()

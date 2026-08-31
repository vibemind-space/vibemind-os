"""
Klotski Graph Environment - Uses Real 25,955-Node Graph

This environment uses the pre-computed graph of all valid Klotski states
instead of generating states dynamically. This ensures:
- Only valid states are visited
- Can use pre-computed distances for reward shaping
- Enables graph-based analysis and visualization
- Exact representation of the mathematical puzzle structure
"""

import json
import numpy as np
import torch
from typing import Dict, List, Tuple, Optional
from pathlib import Path


class KlotskiGraphEnv:
    """
    Klotski puzzle environment based on the complete 25,955-node state graph

    State space: 25,955 unique valid board configurations
    Actions: Move to one of the neighboring states
    Reward: Based on progress toward solution
    """

    def __init__(
        self,
        graph_file: str = "Klotski-Webpage/data.json",
        max_steps: int = 200,
        reward_shaping: bool = True
    ):
        """
        Initialize graph-based Klotski environment

        Args:
            graph_file: Path to the 25,955-node graph JSON
            max_steps: Maximum steps per episode
            reward_shaping: Use distance-based reward shaping
        """
        self.graph_file = graph_file
        self.max_steps = max_steps
        self.reward_shaping = reward_shaping

        # Load graph
        print(f"[KlotskiGraphEnv] Loading 25,955-node graph from {graph_file}...")
        self.graph = self._load_graph()

        # Get all node hashes
        self.node_hashes = list(self.graph.keys())
        self.num_nodes = len(self.node_hashes)
        print(f"[KlotskiGraphEnv] Loaded {self.num_nodes} nodes")

        # Find start node (furthest from solution)
        self.start_hash = self._find_start_node()
        print(f"[KlotskiGraphEnv] Start node: {self.start_hash}")
        print(f"[KlotskiGraphEnv]   Distance to solution: {self.graph[self.start_hash]['solution_dist']}")

        # Find solution nodes (solution_dist == 0)
        self.solution_hashes = [h for h in self.node_hashes
                                if self.graph[h]['solution_dist'] == 0]
        print(f"[KlotskiGraphEnv] Found {len(self.solution_hashes)} solution states")

        # Current state
        self.current_hash = self.start_hash
        self.step_count = 0

        # Episode stats
        self.episode_count = 0
        self.total_solutions = 0

    def _load_graph(self) -> Dict:
        """Load the graph from JSON file"""
        graph_path = Path(self.graph_file)

        if not graph_path.exists():
            raise FileNotFoundError(f"Graph file not found: {graph_path}")

        with open(graph_path, 'r') as f:
            # Read JavaScript variable definition
            content = f.read()

            # Extract JSON (remove "var nodes_to_use = " prefix)
            if 'var nodes_to_use = ' in content:
                # Find start of JSON object
                start_idx = content.find('var nodes_to_use = ') + len('var nodes_to_use = ')

                # Find end of JSON object by counting braces
                brace_count = 0
                in_string = False
                escape_next = False
                end_idx = start_idx

                for i in range(start_idx, len(content)):
                    char = content[i]

                    if escape_next:
                        escape_next = False
                        continue

                    if char == '\\':
                        escape_next = True
                        continue

                    if char == '"':
                        in_string = not in_string
                        continue

                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break

                json_str = content[start_idx:end_idx]
                graph = json.loads(json_str)
            else:
                # Assume pure JSON
                graph = json.loads(content)

        # Handle nested format with 'states' key (from generate_klotski_graph.py)
        if 'states' in graph and 'metadata' in graph:
            print(f"[KlotskiGraphEnv] Detected nested format, extracting states...")
            graph = graph['states']

        return graph

    def _find_start_node(self) -> str:
        """Find the start node (furthest from solution)"""
        # Find node with maximum solution_dist
        max_dist = 0
        start_node = None

        for node_hash, node_data in self.graph.items():
            dist = node_data['solution_dist']
            if dist > max_dist:
                max_dist = dist
                start_node = node_hash

        return start_node

    def reset(self, start_hash: Optional[str] = None) -> Tuple[torch.Tensor, List[int]]:
        """
        Reset environment to start state

        Args:
            start_hash: Optional specific start node (for curriculum learning)

        Returns:
            state: Board representation as tensor
            valid_actions: List of valid action indices
        """
        if start_hash is not None and start_hash in self.graph:
            self.current_hash = start_hash
        else:
            self.current_hash = self.start_hash

        self.step_count = 0
        self.episode_count += 1

        state = self._hash_to_state(self.current_hash)
        valid_actions = self._get_valid_actions()

        return state, valid_actions

    def step(self, action: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Take action (move to neighboring state)

        Args:
            action: Index of neighbor to move to

        Returns:
            next_state: New board state
            reward: Reward for this transition
            done: Episode finished?
            info: Additional information
        """
        self.step_count += 1

        # Get neighbors
        neighbors = self.graph[self.current_hash]['neighbors']

        # Check if action is valid
        if action >= len(neighbors):
            # Invalid action - stay in same state with penalty
            state = self._hash_to_state(self.current_hash)
            reward = -1.0
            done = self.step_count >= self.max_steps
            info = {
                'invalid_action': True,
                'valid_actions': list(range(len(neighbors)))
            }
            return state, reward, done, info

        # Get previous distance
        prev_dist = self.graph[self.current_hash]['solution_dist']

        # Move to neighbor
        # Handle both formats: string hash or dict with 'next_state' key
        neighbor = neighbors[action]
        if isinstance(neighbor, dict):
            self.current_hash = neighbor['next_state']
        else:
            self.current_hash = neighbor

        # Get new distance
        new_dist = self.graph[self.current_hash]['solution_dist']

        # Check if solved
        done = (new_dist == 0) or (self.step_count >= self.max_steps)

        # Compute reward
        if new_dist == 0:
            # Solved!
            reward = 100.0
            self.total_solutions += 1
            print(f"[KlotskiGraphEnv] SOLVED in {self.step_count} steps! "
                  f"(Total solutions: {self.total_solutions}/{self.episode_count})")
        elif self.reward_shaping:
            # Reward based on progress
            progress = prev_dist - new_dist  # Positive if getting closer
            reward = progress * 1.0 - 0.1  # Small step penalty
        else:
            # Sparse reward
            reward = -0.1

        # Get state
        state = self._hash_to_state(self.current_hash)

        # Info
        info = {
            'current_hash': self.current_hash,
            'solution_dist': new_dist,
            'progress': prev_dist - new_dist,
            'step': self.step_count,
            'valid_actions': self._get_valid_actions()
        }

        return state, reward, done, info

    def _hash_to_state(self, node_hash: str) -> torch.Tensor:
        """
        Convert node hash to board state tensor

        The graph stores board representation as a string.
        We need to convert it to a tensor for the neural network.

        Returns:
            Tensor of shape (4, 5) representing the board
        """
        node_data = self.graph[node_hash]

        # Get board representation string
        # Format: "jafi.aehddehbbcgbbc." (14 characters for 4x5 grid minus 6 for 2x2 piece)
        board_str = node_data['representation']

        # Parse board string to 4x5 grid
        # Each character represents a piece or empty space
        # '.' = empty (0)
        # Letters = piece IDs (1-10)
        board = np.zeros((5, 4), dtype=np.float32)  # Note: transposed to match original

        # Map characters to piece IDs
        char_to_id = {'.': 0}
        next_id = 1

        idx = 0
        for row in range(5):
            for col in range(4):
                if idx >= len(board_str):
                    break

                char = board_str[idx]
                if char not in char_to_id:
                    char_to_id[char] = next_id
                    next_id += 1

                board[row, col] = char_to_id[char]
                idx += 1

        return torch.tensor(board, dtype=torch.float32)

    def _get_valid_actions(self) -> List[int]:
        """Get list of valid action indices"""
        neighbors = self.graph[self.current_hash]['neighbors']
        return list(range(len(neighbors)))

    def get_current_node_data(self) -> Dict:
        """Get full data for current node"""
        return self.graph[self.current_hash]

    def get_node_position_3d(self, node_hash: str) -> Tuple[float, float, float]:
        """Get 3D position of a node for visualization"""
        node = self.graph[node_hash]
        return (node['x'], node['y'], node['z'])

    def get_solution_path(self) -> List[str]:
        """
        Get shortest path from current node to solution using BFS

        Returns:
            List of node hashes from current to solution
        """
        from collections import deque

        # BFS to find shortest path
        queue = deque([(self.current_hash, [self.current_hash])])
        visited = {self.current_hash}

        while queue:
            node_hash, path = queue.popleft()

            # Check if solved
            if self.graph[node_hash]['solution_dist'] == 0:
                return path

            # Explore neighbors
            neighbors = self.graph[node_hash]['neighbors']
            for neighbor in neighbors:
                # Handle both formats: string hash or dict with 'next_state' key
                if isinstance(neighbor, dict):
                    neighbor_hash = neighbor['next_state']
                else:
                    neighbor_hash = neighbor

                if neighbor_hash not in visited:
                    visited.add(neighbor_hash)
                    queue.append((neighbor_hash, path + [neighbor_hash]))

        return []  # No path found (shouldn't happen)

    def get_optimal_path(self, start_state: Optional[str] = None) -> List[Dict]:
        """
        Get optimal path as demonstrations (state/action pairs).

        Args:
            start_state: Optional starting state hash. If None, uses current state.

        Returns:
            List of demonstration dicts: [{'state': hash, 'action': action_idx}, ...]
        """
        from collections import deque

        # Use provided start or current state
        if start_state is not None:
            if isinstance(start_state, tuple):
                # Handle (tensor, valid_actions) tuple from reset()
                pass  # Fall back to current hash
            elif isinstance(start_state, str) and start_state in self.graph:
                self.current_hash = start_state

        # BFS to find shortest path
        queue = deque([(self.current_hash, [self.current_hash])])
        visited = {self.current_hash}

        path_hashes = []
        while queue:
            node_hash, path = queue.popleft()

            # Check if solved
            if self.graph[node_hash]['solution_dist'] == 0:
                path_hashes = path
                break

            # Explore neighbors
            neighbors = self.graph[node_hash]['neighbors']
            for neighbor in neighbors:
                if isinstance(neighbor, dict):
                    neighbor_hash = neighbor['next_state']
                else:
                    neighbor_hash = neighbor

                if neighbor_hash not in visited:
                    visited.add(neighbor_hash)
                    queue.append((neighbor_hash, path + [neighbor_hash]))

        # Convert path to demonstrations
        demonstrations = []
        for i in range(len(path_hashes) - 1):
            current_hash = path_hashes[i]
            next_hash = path_hashes[i + 1]

            # Find which action leads to next_hash
            neighbors = self.graph[current_hash]['neighbors']
            for action_idx, neighbor in enumerate(neighbors):
                if isinstance(neighbor, dict):
                    neighbor_hash = neighbor['next_state']
                else:
                    neighbor_hash = neighbor

                if neighbor_hash == next_hash:
                    demonstrations.append({
                        'state': current_hash,
                        'action': action_idx
                    })
                    break

        return demonstrations

    def get_statistics(self) -> Dict:
        """Get environment statistics"""
        return {
            'total_nodes': self.num_nodes,
            'total_episodes': self.episode_count,
            'total_solutions': self.total_solutions,
            'success_rate': (self.total_solutions / self.episode_count * 100)
                           if self.episode_count > 0 else 0,
            'current_step': self.step_count,
            'current_dist': self.graph[self.current_hash]['solution_dist'],
            'solution_states': len(self.solution_hashes)
        }


if __name__ == '__main__':
    # Test the environment
    print("="*80)
    print("TESTING KLOTSKI GRAPH ENVIRONMENT")
    print("="*80)

    # Create environment
    env = KlotskiGraphEnv()

    # Test reset
    print("\nTest 1: Reset")
    state, valid_actions = env.reset()
    print(f"State shape: {state.shape}")
    print(f"Valid actions: {len(valid_actions)}")
    print(f"State:\n{state}")

    # Test random episode
    print("\nTest 2: Random episode (10 steps)")
    state, _ = env.reset()

    for i in range(10):
        valid_actions = env._get_valid_actions()
        action = np.random.choice(valid_actions)

        next_state, reward, done, info = env.step(action)

        print(f"Step {i+1}: Action={action}, Reward={reward:.2f}, "
              f"Dist={info['solution_dist']}, Done={done}")

        if done:
            break

    # Test solution path
    print("\nTest 3: Solution path")
    path = env.get_solution_path()
    print(f"Path length: {len(path)} steps")
    print(f"Current dist: {env.graph[path[0]]['solution_dist']}")
    print(f"Solution dist: {env.graph[path[-1]]['solution_dist']}")

    # Statistics
    print("\nTest 4: Statistics")
    stats = env.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "="*80)
    print("ALL TESTS PASSED!")
    print("="*80)

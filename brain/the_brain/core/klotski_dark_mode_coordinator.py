"""
Klotski Dark Mode Coordinator - Real Puzzle Edition

3-Agent romantic system with REAL Klotski puzzles (25,955-node state graph).
Each agent solves an identical 4x5 puzzle with 10 brain-module blocks.

User's Romantic Concept (now with REAL puzzles):
- "we all run in the dark" - 3 agents, 3 identical REAL Klotski puzzles
- "on match we have sex" - connection = all 3 solve their puzzle (G block at exit)
- "when we have sex we multiply the puzzle" - harder start state next generation
- "love is happening inbetween" - conversation penalties increase per generation

Blocks represent brain modules:
- G (DMN, 2x2): Default Mode Network - integration/consciousness
- V (VIS, 2x1): Visual cortex
- A (AUD, 1x1): Auditory cortex
- S (SOM, 1x1): Somatosensory cortex
- L (LAN, 1x1): Language cortex
- D (DLPFC, 2x1): Dorsolateral prefrontal cortex - planning
- C (ACC, 1x2): Anterior cingulate cortex - conflict
- I (INS, 1x1): Insula - interoception
- M (MTL, 2x1): Medial temporal lobe - memory
- O (OFC, 1x1): Orbitofrontal cortex - value/reward
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from copy import deepcopy

# Import real Klotski components
try:
    from learning_engine.klotski.neurosymbolic.environments.klotski_graph_env import KlotskiGraphEnv
    from learning_engine.klotski.neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece
    NEUROSYMBOLIC_AVAILABLE = True
except ImportError:
    NEUROSYMBOLIC_AVAILABLE = False
    logging.warning("[KlotskiDarkMode] Neurosymbolic components not available - using fallback mode")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """State of a single agent"""
    agent_name: str
    current_node_hash: str  # Current state in graph
    distance_to_solution: int  # Distance from graph
    episode_moves: int  # Moves made this episode
    total_moves: int  # Total moves across all episodes
    solved: bool  # Reached solution state
    last_action: Optional[Dict] = None  # Last action performed: {block_id, direction, from, to}


class KlotskiDarkModeCoordinator:
    """
    3-Agent Klotski Dark Mode Coordinator

    Each agent has their own REAL Klotski puzzle (identical start state).
    Agents can't see each other's puzzles (dark mode).
    Communication via messages (with conversation penalty).
    Connection = all 3 agents solve their puzzles.
    """

    def __init__(
        self,
        current_generation: int = 0,
        graph_file: str = "Klotski-Webpage/data.json",
        max_steps_per_episode: int = 200,
        conversation_penalty_base: float = -0.1
    ):
        """
        Initialize 3-agent Klotski system

        Args:
            current_generation: Current generation (affects conversation penalty)
            graph_file: Path to 25,955-node Klotski graph JSON
            max_steps_per_episode: Max moves per episode
            conversation_penalty_base: Base conversation penalty (increases with generation)
        """
        self.current_generation = current_generation
        self.graph_file = graph_file
        self.max_steps_per_episode = max_steps_per_episode

        # Conversation penalties increase with generation
        # Gen 0: -0.1, Gen 1: -0.5, Gen 2: -1.0, Gen 3: -2.0, Gen 4+: -5.0
        self.conversation_penalties = {
            0: -0.1,
            1: -0.5,
            2: -1.0,
            3: -2.0
        }
        self.conversation_penalty = self.conversation_penalties.get(
            current_generation, -5.0
        )

        # Initialize 3 identical Klotski environments
        self.envs: Dict[str, Any] = {}
        self.agent_states: Dict[str, AgentState] = {}

        if NEUROSYMBOLIC_AVAILABLE:
            self._initialize_real_puzzles()
        else:
            self._initialize_fallback_mode()

        # Communication history
        self.communication_history: List[Dict] = []
        self.conversation_cost_this_episode = 0.0

        # Episode tracking
        self.episode_count = 0
        self.step_count = 0

        logger.info(f"[KlotskiDarkMode] Initialized for Generation {current_generation}")
        logger.info(f"  Mode: {'REAL KLOTSKI' if NEUROSYMBOLIC_AVAILABLE else 'FALLBACK'}")
        logger.info(f"  Conversation penalty: {self.conversation_penalty}")
        logger.info(f"  Max steps: {max_steps_per_episode}")

    def _compute_optimal_path(self, env: Any) -> List[str]:
        """
        Compute the optimal solution path from start to goal using BFS

        Args:
            env: KlotskiGraphEnv instance

        Returns:
            List of node hashes from start (furthest) to solution (closest)
        """
        from collections import deque

        start_hash = env.start_hash
        graph = env.graph

        # BFS from start to find shortest path to any solution node
        queue = deque([(start_hash, [start_hash])])
        visited = {start_hash}

        while queue:
            node_hash, path = queue.popleft()

            # Check if this is a solution node
            if graph[node_hash]['solution_dist'] == 0:
                logger.info(f"[KlotskiDarkMode] Found optimal path with {len(path)} steps")
                return path

            # Explore neighbors in order of decreasing distance (moving toward solution)
            neighbors = graph[node_hash]['neighbors']
            neighbors_with_dist = [(n, graph[n]['solution_dist']) for n in neighbors]
            neighbors_with_dist.sort(key=lambda x: x[1])  # Sort by distance (ascending)

            for neighbor_hash, _ in neighbors_with_dist:
                if neighbor_hash not in visited:
                    visited.add(neighbor_hash)
                    queue.append((neighbor_hash, path + [neighbor_hash]))

        logger.warning("[KlotskiDarkMode] No solution path found! Using fallback")
        return [start_hash]  # Fallback

    def _initialize_real_puzzles(self):
        """Initialize 3 real Klotski puzzle environments with different starting states"""
        graph_path = Path(self.graph_file)

        if not graph_path.exists():
            logger.warning(f"[KlotskiDarkMode] Graph file not found: {graph_path}")
            logger.warning(f"[KlotskiDarkMode] Falling back to simple mode")
            self._initialize_fallback_mode()
            return

        logger.info(f"[KlotskiDarkMode] Loading real Klotski puzzles from {graph_path}")

        try:
            # Create one environment to compute optimal path
            temp_env = KlotskiGraphEnv(
                graph_file=str(graph_path),
                max_steps=self.max_steps_per_episode,
                reward_shaping=True
            )

            # Compute optimal solution path
            logger.info("[KlotskiDarkMode] Computing optimal solution path...")
            optimal_path = self._compute_optimal_path(temp_env)
            path_length = len(optimal_path)

            # Select three starting states along the path
            # BEGINNING: Start of path (furthest from solution)
            # MID: Middle of path (~50% progress)
            # END: Near end of path (~90% progress)
            beginning_idx = 0
            mid_idx = path_length // 2
            end_idx = int(path_length * 0.9)

            self.agent_start_hashes = {
                'beginning': optimal_path[beginning_idx],
                'mid': optimal_path[mid_idx],
                'end': optimal_path[end_idx]
            }

            logger.info(f"[KlotskiDarkMode] Selected start states:")
            logger.info(f"  BEGINNING: Step {beginning_idx}/{path_length} (distance={temp_env.graph[self.agent_start_hashes['beginning']]['solution_dist']})")
            logger.info(f"  MID: Step {mid_idx}/{path_length} (distance={temp_env.graph[self.agent_start_hashes['mid']]['solution_dist']})")
            logger.info(f"  END: Step {end_idx}/{path_length} (distance={temp_env.graph[self.agent_start_hashes['end']]['solution_dist']})")

            # Create 3 environments with their specific starting states
            for agent_name in ['beginning', 'mid', 'end']:
                env = KlotskiGraphEnv(
                    graph_file=str(graph_path),
                    max_steps=self.max_steps_per_episode,
                    reward_shaping=True
                )

                # Set initial state to agent-specific hash
                start_hash = self.agent_start_hashes[agent_name]
                env.current_hash = start_hash
                env.start_hash = start_hash  # Override default start

                self.envs[agent_name] = env

                # Initialize agent state
                self.agent_states[agent_name] = AgentState(
                    agent_name=agent_name,
                    current_node_hash=start_hash,
                    distance_to_solution=env.graph[start_hash]['solution_dist'],
                    episode_moves=0,
                    total_moves=0,
                    solved=False
                )

            logger.info(f"[KlotskiDarkMode] 3 real Klotski puzzles initialized with different starting states")
            logger.info(f"  BEGINNING distance: {self.agent_states['beginning'].distance_to_solution}")
            logger.info(f"  MID distance: {self.agent_states['mid'].distance_to_solution}")
            logger.info(f"  END distance: {self.agent_states['end'].distance_to_solution}")

        except Exception as e:
            logger.error(f"[KlotskiDarkMode] Failed to load real puzzles: {e}")
            logger.error(f"[KlotskiDarkMode] Falling back to simple mode")
            self._initialize_fallback_mode()

    def _initialize_fallback_mode(self):
        """Fallback mode when neurosymbolic components not available"""
        # Simple fallback: Track positions and distances
        for agent_name in ['beginning', 'mid', 'end']:
            self.agent_states[agent_name] = AgentState(
                agent_name=agent_name,
                current_node_hash=f"fallback_{agent_name}",
                distance_to_solution=81,  # Approximate Klotski optimal
                episode_moves=0,
                total_moves=0,
                solved=False
            )

        logger.info("[KlotskiDarkMode] Fallback mode initialized (no real puzzles)")

    def reset(self) -> Dict[str, Any]:
        """
        Reset all 3 puzzles for new episode
        Each agent resets to their designated starting state (not all to the same state!)

        Returns:
            Dict of initial states for each agent
        """
        self.episode_count += 1
        self.step_count = 0
        self.conversation_cost_this_episode = 0.0
        self.communication_history = []

        states = {}

        if NEUROSYMBOLIC_AVAILABLE and self.envs:
            # Reset real puzzles to agent-specific starting states
            for agent_name, env in self.envs.items():
                # Reset to agent-specific starting hash (not default start!)
                start_hash = self.agent_start_hashes.get(agent_name, env.start_hash)
                env.reset(start_hash=start_hash)

                self.agent_states[agent_name].current_node_hash = env.current_hash
                self.agent_states[agent_name].distance_to_solution = env.graph[env.current_hash]['solution_dist']
                self.agent_states[agent_name].episode_moves = 0
                self.agent_states[agent_name].solved = False

                states[agent_name] = {
                    'node_hash': env.current_hash,
                    'distance': env.graph[env.current_hash]['solution_dist'],
                    'moves': 0,
                    'solved': False
                }
        else:
            # Fallback mode
            for agent_name in ['beginning', 'mid', 'end']:
                self.agent_states[agent_name].episode_moves = 0
                self.agent_states[agent_name].solved = False
                self.agent_states[agent_name].distance_to_solution = 81

                states[agent_name] = {
                    'node_hash': f"fallback_{agent_name}",
                    'distance': 81,
                    'moves': 0,
                    'solved': False
                }

        logger.info(f"[KlotskiDarkMode] Episode {self.episode_count} reset")
        return states

    def _compute_action_details(self, prev_hash: str, next_hash: str, env: Any) -> Optional[Dict]:
        """
        Compute which block moved and in what direction

        Args:
            prev_hash: Previous node hash
            next_hash: Next node hash
            env: KlotskiGraphEnv instance

        Returns:
            Action dict: {block_id, direction, from_pos, to_pos} or None
        """
        if not env or prev_hash not in env.graph or next_hash not in env.graph:
            return None

        prev_repr = env.graph[prev_hash]['representation']
        next_repr = env.graph[next_hash]['representation']

        # Parse both representations into grids
        prev_grid = [['' for _ in range(4)] for _ in range(5)]
        next_grid = [['' for _ in range(4)] for _ in range(5)]

        for i in range(min(20, len(prev_repr))):
            row, col = divmod(i, 4)
            if row < 5: prev_grid[row][col] = prev_repr[i]

        for i in range(min(20, len(next_repr))):
            row, col = divmod(i, 4)
            if row < 5: next_grid[row][col] = next_repr[i]

        # Find which block changed position
        char_to_module = {
            'a': 'G', 'b': 'V', 'c': 'A', 'd': 'S', 'e': 'L',
            'f': 'D', 'g': 'C', 'h': 'I', 'i': 'M', 'j': 'O'
        }

        # Find positions of each character in both grids
        for char in char_to_module.keys():
            prev_positions = set()
            next_positions = set()

            for row in range(5):
                for col in range(4):
                    if prev_grid[row][col] == char:
                        prev_positions.add((col, row))
                    if next_grid[row][col] == char:
                        next_positions.add((col, row))

            # If positions differ, this block moved
            if prev_positions != next_positions and prev_positions and next_positions:
                # Calculate movement vector
                prev_center = (sum(x for x, y in prev_positions) / len(prev_positions),
                               sum(y for x, y in prev_positions) / len(prev_positions))
                next_center = (sum(x for x, y in next_positions) / len(next_positions),
                               sum(y for x, y in next_positions) / len(next_positions))

                dx = next_center[0] - prev_center[0]
                dy = next_center[1] - prev_center[1]

                # Determine direction
                if abs(dx) > abs(dy):
                    direction = 'right' if dx > 0 else 'left'
                else:
                    direction = 'down' if dy > 0 else 'up'

                return {
                    'block_id': char_to_module[char],
                    'direction': direction,
                    'from_pos': (int(prev_center[0]), int(prev_center[1])),
                    'to_pos': (int(next_center[0]), int(next_center[1]))
                }

        return None

    def step(self, actions: Dict[str, Any]) -> Tuple[Dict, float, bool, Dict]:
        """
        Execute actions for all 3 agents

        Args:
            actions: Dict of {agent_name: action}
                    action can be:
                    - int: move index (0-39 for real Klotski)
                    - str: "Talk: message" for communication
                    - str: "Move: direction" for fallback mode

        Returns:
            Tuple of (next_states, reward, done, info)
        """
        self.step_count += 1

        next_states = {}
        total_reward = 0.0
        episode_done = False
        info = {
            'connected': False,
            'path_quality': 0.0,
            'conversation_cost': self.conversation_cost_this_episode,
            'actions': actions.copy()
        }

        # Execute each agent's action
        for agent_name, action in actions.items():
            if agent_name not in self.agent_states:
                continue

            agent_state = self.agent_states[agent_name]

            # Handle communication (costs penalty!)
            if isinstance(action, str) and action.startswith("Talk:"):
                message = action[5:].strip()
                self.communication_history.append({
                    'agent': agent_name,
                    'message': message,
                    'step': self.step_count
                })
                self.conversation_cost_this_episode += self.conversation_penalty
                total_reward += self.conversation_penalty
                continue

            # Handle puzzle moves
            if NEUROSYMBOLIC_AVAILABLE and agent_name in self.envs:
                # Real Klotski move
                env = self.envs[agent_name]

                # Action should be move index (0-39)
                if isinstance(action, int):
                    # Store previous hash to compute action details
                    prev_hash = env.current_hash

                    next_state, reward, done, move_info = env.step(action)

                    # Compute action details (which block moved, direction)
                    action_details = self._compute_action_details(prev_hash, env.current_hash, env)
                    agent_state.last_action = action_details

                    # Update agent state
                    agent_state.current_node_hash = env.current_hash
                    agent_state.distance_to_solution = env.graph[env.current_hash]['solution_dist']
                    agent_state.episode_moves += 1
                    agent_state.total_moves += 1
                    agent_state.solved = env.graph[env.current_hash]['solution_dist'] == 0

                    total_reward += reward

                    next_states[agent_name] = {
                        'node_hash': env.current_hash,
                        'distance': agent_state.distance_to_solution,
                        'moves': agent_state.episode_moves,
                        'solved': agent_state.solved,
                        'action': action_details
                    }
            else:
                # Fallback mode - simulate progress
                if isinstance(action, str) and action.startswith("Move:"):
                    # Simulate distance decrease
                    if agent_state.distance_to_solution > 0:
                        agent_state.distance_to_solution -= 1
                        agent_state.episode_moves += 1
                        agent_state.total_moves += 1

                        if agent_state.distance_to_solution == 0:
                            agent_state.solved = True
                            total_reward += 1000  # Solved bonus

                        total_reward += 1  # Progress reward

                    next_states[agent_name] = {
                        'node_hash': f"fallback_{agent_name}_{agent_state.episode_moves}",
                        'distance': agent_state.distance_to_solution,
                        'moves': agent_state.episode_moves,
                        'solved': agent_state.solved
                    }

        # Check if all 3 agents connected (all solved)
        all_solved = all(state.solved for state in self.agent_states.values())

        if all_solved:
            # CONNECTION! All 3 puzzles solved
            info['connected'] = True

            # Calculate quality based on efficiency
            avg_moves = sum(s.episode_moves for s in self.agent_states.values()) / 3
            optimal_moves = 81  # Approximate optimal for Klotski

            # Quality = how close to optimal
            path_quality = min(1.0, optimal_moves / max(avg_moves, 1))
            info['path_quality'] = path_quality

            # Connection reward: 10,000 * quality^2 (exponential reward for efficiency)
            connection_reward = 10000 * (path_quality ** 2)
            total_reward += connection_reward

            episode_done = True

            logger.info(f"[KlotskiDarkMode] CONNECTION! All 3 agents solved their puzzles!")
            logger.info(f"  Average moves: {avg_moves:.1f}")
            logger.info(f"  Quality: {path_quality:.1%}")
            logger.info(f"  Reward: {connection_reward:,.0f}")

        # Check timeout
        if self.step_count >= self.max_steps_per_episode:
            episode_done = True
            logger.info(f"[KlotskiDarkMode] Episode timeout ({self.max_steps_per_episode} steps)")

        return next_states, total_reward, episode_done, info

    def is_path_connected(self) -> bool:
        """Check if all 3 agents have solved their puzzles"""
        return all(state.solved for state in self.agent_states.values())

    def get_states(self) -> Dict[str, Dict]:
        """
        Get current states for all agents

        Returns:
            Dict of {agent_name: state_dict}
        """
        states = {}

        for agent_name, agent_state in self.agent_states.items():
            states[agent_name] = {
                'node_hash': agent_state.current_node_hash,
                'distance': agent_state.distance_to_solution,
                'moves': agent_state.episode_moves,
                'solved': agent_state.solved,
                'total_moves': agent_state.total_moves
            }

        return states

    def get_puzzle_states(self) -> Dict[str, Any]:
        """
        Get detailed puzzle states (for web dashboard)

        Returns:
            Dict with block positions, board configurations
        """
        if not NEUROSYMBOLIC_AVAILABLE or not self.envs:
            return {}

        puzzle_states = {}

        for agent_name, env in self.envs.items():
            # Get current node from graph
            current_node = env.graph.get(env.current_hash, {})

            puzzle_states[agent_name] = {
                'node_hash': env.current_hash,
                'distance': current_node.get('solution_dist', 999),
                'solved': current_node.get('solution_dist', 999) == 0,
                'moves': self.agent_states[agent_name].episode_moves,
                'blocks': self._extract_blocks_from_hash(env.current_hash),
                'action': self.agent_states[agent_name].last_action  # Include action data
            }

        return puzzle_states

    def _extract_blocks_from_hash(self, node_hash: str) -> List[Dict]:
        """
        Extract block positions from node hash by parsing the representation string

        The representation is a 20-character string encoding the 4×5 grid (row-major order).
        Each character represents which piece occupies that cell:
        - '.' = empty
        - 'a' = the 2×2 main block (maps to 'G' for DMN)
        - Other letters = various 1×1, 1×2, 2×1 blocks

        Returns:
            List of block dicts with {id, x, y, w, h, module, color}
        """
        if not NEUROSYMBOLIC_AVAILABLE or not self.envs:
            # Fallback mode - return placeholder
            return [
                {'id': 'G', 'x': 1, 'y': 0, 'w': 2, 'h': 2, 'module': 'DMN', 'color': '#9b59b6'},
                {'id': 'V', 'x': 0, 'y': 0, 'w': 2, 'h': 1, 'module': 'VIS', 'color': '#3498db'},
                {'id': 'A', 'x': 0, 'y': 1, 'w': 1, 'h': 1, 'module': 'AUD', 'color': '#f39c12'},
                {'id': 'S', 'x': 3, 'y': 1, 'w': 1, 'h': 1, 'module': 'SOM', 'color': '#2ecc71'},
                {'id': 'L', 'x': 0, 'y': 2, 'w': 1, 'h': 1, 'module': 'LAN', 'color': '#e67e22'},
                {'id': 'D', 'x': 1, 'y': 2, 'w': 2, 'h': 1, 'module': 'DLPFC', 'color': '#e74c3c'},
                {'id': 'C', 'x': 3, 'y': 2, 'w': 1, 'h': 2, 'module': 'ACC', 'color': '#1abc9c'},
                {'id': 'I', 'x': 0, 'y': 3, 'w': 1, 'h': 1, 'module': 'INS', 'color': '#8e44ad'},
                {'id': 'M', 'x': 1, 'y': 3, 'w': 2, 'h': 1, 'module': 'MTL', 'color': '#16a085'},
                {'id': 'O', 'x': 0, 'y': 4, 'w': 1, 'h': 1, 'module': 'OFC', 'color': '#e91e63'}
            ]

        # Get representation string from graph
        # Try to find the environment (check all 3 agents)
        env = None
        for agent_env in self.envs.values():
            if hasattr(agent_env, 'graph') and node_hash in agent_env.graph:
                env = agent_env
                break

        if not env or node_hash not in env.graph:
            # Node not found, return placeholder
            return []

        representation = env.graph[node_hash]['representation']

        # Parse representation string using CORRECT algorithm from KlotskiGraphEnv
        # The string is COMPRESSED (~14 chars), not 20 chars!
        # Multi-cell pieces like 'a' (2×2) appear only once but occupy multiple cells

        # Build character-to-ID mapping dynamically (order matters!)
        char_to_id = {'.': 0}
        next_id = 1

        # Parse grid row-by-row, expanding multi-cell pieces
        grid = [['' for _ in range(4)] for _ in range(5)]
        idx = 0

        for row in range(5):
            for col in range(4):
                if idx >= len(representation):
                    break

                char = representation[idx]

                # Assign ID if new character
                if char not in char_to_id:
                    char_to_id[char] = next_id
                    next_id += 1

                grid[row][col] = char
                idx += 1

        # Find all unique pieces (excluding empty '.')
        pieces = {}
        for row in range(5):
            for col in range(4):
                char = grid[row][col]
                if char != '' and char != '.':
                    if char not in pieces:
                        pieces[char] = []
                    pieces[char].append((col, row))  # (x, y)

        # Map piece characters to brain modules
        # 'a' is the 2×2 main block (DMN)
        # Other blocks get assigned to remaining modules
        char_to_module = {
            'a': ('G', 'DMN', '#9b59b6'),   # Main 2×2 block
            'b': ('V', 'VIS', '#3498db'),
            'c': ('A', 'AUD', '#f39c12'),
            'd': ('S', 'SOM', '#2ecc71'),
            'e': ('L', 'LAN', '#e67e22'),
            'f': ('D', 'DLPFC', '#e74c3c'),
            'g': ('C', 'ACC', '#1abc9c'),
            'h': ('I', 'INS', '#8e44ad'),
            'i': ('M', 'MTL', '#16a085'),
            'j': ('O', 'OFC', '#e91e63')
        }

        # Convert pieces to block format
        blocks = []
        for char, cells in sorted(pieces.items()):
            if char not in char_to_module:
                continue

            block_id, module, color = char_to_module[char]

            # Calculate bounding box
            xs = [x for x, y in cells]
            ys = [y for x, y in cells]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)

            width = x_max - x_min + 1
            height = y_max - y_min + 1

            blocks.append({
                'id': block_id,
                'x': x_min,
                'y': y_min,
                'w': width,
                'h': height,
                'module': module,
                'color': color
            })

        # Debug logging
        logger.debug(f"[BlockParser] Representation: {representation}")
        logger.debug(f"[BlockParser] Found {len(blocks)} blocks")
        for block in blocks:
            logger.debug(f"  {block['id']} ({block['w']}×{block['h']}) at ({block['x']},{block['y']})")

        return blocks

    def calculate_quality(self) -> float:
        """
        Calculate path quality based on efficiency

        Returns:
            Quality score (0.0 - 1.0)
        """
        if not self.agent_states:
            return 0.0

        # Average distance decrease across all agents
        total_progress = 0
        for state in self.agent_states.values():
            initial_dist = 81  # Approximate start distance
            current_dist = state.distance_to_solution
            progress = (initial_dist - current_dist) / initial_dist
            total_progress += progress

        avg_progress = total_progress / len(self.agent_states)
        return max(0.0, min(1.0, avg_progress))


if __name__ == "__main__":
    # Test coordinator
    print("=" * 80)
    print("KLOTSKI DARK MODE COORDINATOR TEST")
    print("=" * 80)

    # Create coordinator
    coordinator = KlotskiDarkModeCoordinator(
        current_generation=0,
        graph_file="Klotski-Webpage/data.json",
        max_steps_per_episode=50
    )

    # Reset for episode
    states = coordinator.reset()
    print(f"\nInitial states:")
    for agent, state in states.items():
        print(f"  {agent}: distance={state['distance']}, solved={state['solved']}")

    # Simulate some moves
    print(f"\nSimulating 10 moves...")
    for step in range(10):
        # Random actions (in real system, these come from NeuroSymbolicBrain)
        actions = {
            'beginning': f"Move: Right",  # Fallback mode
            'mid': f"Move: Down",
            'end': f"Move: Left"
        }

        if step % 3 == 0:
            # Occasionally communicate
            actions['mid'] = f"Talk: I'm at distance {coordinator.agent_states['mid'].distance_to_solution}"

        next_states, reward, done, info = coordinator.step(actions)

        print(f"  Step {step+1}: reward={reward:.1f}, done={done}")

        if done:
            print(f"\nEpisode finished!")
            print(f"  Connected: {info['connected']}")
            print(f"  Quality: {info.get('path_quality', 0):.1%}")
            break

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

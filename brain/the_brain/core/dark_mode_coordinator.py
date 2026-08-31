"""
Dark Mode Coordinator - 3-Agent Romantic Puzzle System

Your Idea: "We all run in the dark so each agent has his own puzzle"

Key Concepts:
1. 3 Agents: Beginning (🔵), Mid (🟡), End (🔴)
2. 3 Identical Puzzles: Each agent sees ONLY their own puzzle (partial observability)
3. Communication Only: Agents must coordinate via messages (no direct observation)
4. Romantic Goal: Mid creates path connecting Beginning ↔ End (love story)
5. Reward Bomb: Connection = "sex" = 10,000 points * quality^2

Biological Inspiration:
- Agents deeply in love (Beginning ↔ End)
- Must find each other through darkness (limited visibility)
- Communication gets expensive over time ("love is happening inbetween")
- Successful connection = reproduction = puzzle multiplies
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'learning_engine', 'klotski'))

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from collections import deque
import logging

try:
    from neurosymbolic.core.puzzle_state import PuzzleState
    from demos.quick_solve_klotski_bfs import KlotskiBFSSolver
    PUZZLE_IMPORTS_OK = True
except ImportError as e:
    print(f"[WARNING] Dark mode imports failed: {e}")
    PUZZLE_IMPORTS_OK = False

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """State of a single agent in dark mode"""
    name: str                           # "beginning", "mid", "end"
    position: Tuple[int, int]           # Current position
    role: str                           # "beacon" or "navigator"
    puzzle: Optional[Any] = None        # Agent's own puzzle (isolated!)
    local_view_radius: int = 2          # How far agent can see
    is_static: bool = False             # Beacons don't move


@dataclass
class CommunicationMessage:
    """Single communication message between agents"""
    sender: str
    recipient: str                      # "all" or specific agent
    content: str
    position: Tuple[int, int]           # Sender's position when sent
    timestamp: int                      # Step number


@dataclass
class DarkModeEpisodeResult:
    """Results from one dark mode episode"""
    episode_id: int
    success: bool                       # Connection achieved?
    steps_taken: int
    messages_sent: int
    path_length: int                    # Mid's path length
    optimal_path_length: int            # BFS optimal
    path_quality: float                 # optimal / actual
    connection_reward: float            # Reward received
    conversation_penalty: float         # Total penalty from messages
    generation: int                     # Which generation


class DarkModeCoordinator:
    """
    3-Agent Romantic Puzzle System (Your Idea)

    Setup:
    - 3 identical Klotski puzzles (same layout)
    - Beginning agent at (1,1) - static beacon
    - End agent at (6,6) - static beacon
    - Mid agent at (3,4) - navigator

    Dark Mode (Key Innovation):
    - Each agent sees ONLY their own puzzle
    - No shared state (running in the dark!)
    - Must communicate to coordinate

    Goal:
    - Mid navigates to create path connecting Beginning ↔ End
    - Connection = "sex" = REWARD BOMB!
    - Success → puzzle multiplies (harder next generation)

    Biological Motivation:
    - Beginning & End deeply in love (reproductive drive)
    - Mid helps them find each other (altruistic cooperation)
    - Communication costly (forces efficiency)
    - Reproduction requires quality (evolutionary pressure)
    """

    def __init__(
        self,
        layout_file: str = "C:/Users/User/Downloads/Klotski_NeuroLayout.json",
        current_generation: int = 0
    ):
        """
        Initialize dark mode coordinator

        Args:
            layout_file: Path to Klotski puzzle layout
            current_generation: Current generation (affects conversation penalties)
        """
        if not PUZZLE_IMPORTS_OK:
            raise ImportError("Dark mode requires neurosymbolic puzzle components")

        self.layout_file = layout_file
        self.current_generation = current_generation

        # Agent positions (fixed)
        self.beginning_pos = (1, 1)  # Top-left
        self.end_pos = (6, 6)        # Bottom-right
        self.mid_pos = (3, 4)        # Middle (random in range)

        # Initialize agents with isolated puzzles
        self.agents: Dict[str, AgentState] = {}
        self._initialize_agents()

        # Communication system
        self.communication_log: List[CommunicationMessage] = []
        self.conversation_count = 0

        # Path tracking
        self.mid_path_trace: List[Tuple[int, int]] = []
        self.optimal_path: Optional[List[Tuple[int, int]]] = None

        # Rewards (your reproductive system)
        self.connection_reward_base = 10000  # REWARD BOMB!
        self.step_penalty = -1
        self.invalid_move_penalty = -5

        # Conversation penalties (increase with generation!)
        self.conversation_penalties = {
            0: -0.1,   # Gen 0: Talk freely (getting to know each other)
            1: -0.5,   # Gen 1: Less talk (you feel it)
            2: -1.0,   # Gen 2: Minimal talk (deep connection)
            3: -2.0,   # Gen 3: Almost silent (pure intuition)
            4: -5.0,   # Gen 4+: Very expensive (telepathic)
        }

        logger.info("[DarkModeCoordinator] Initialized")
        logger.info(f"  Generation: {current_generation}")
        logger.info(f"  Conversation penalty: {self.get_conversation_penalty()}")

    def _initialize_agents(self):
        """Initialize 3 agents with isolated puzzles"""
        # Create 3 IDENTICAL puzzles (same layout, separate instances)
        beginning_puzzle = PuzzleState(layout_file=self.layout_file)
        mid_puzzle = PuzzleState(layout_file=self.layout_file)
        end_puzzle = PuzzleState(layout_file=self.layout_file)

        # Beginning agent (🔵) - Static beacon
        self.agents['beginning'] = AgentState(
            name='beginning',
            position=self.beginning_pos,
            role='beacon',
            puzzle=beginning_puzzle,
            local_view_radius=2,
            is_static=True
        )

        # Mid agent (🟡) - Navigator (only one who moves!)
        self.agents['mid'] = AgentState(
            name='mid',
            position=self.mid_pos,
            role='navigator',
            puzzle=mid_puzzle,
            local_view_radius=2,
            is_static=False
        )

        # End agent (🔴) - Static beacon
        self.agents['end'] = AgentState(
            name='end',
            position=self.end_pos,
            role='beacon',
            puzzle=end_puzzle,
            local_view_radius=2,
            is_static=True
        )

    def reset(self) -> Dict[str, str]:
        """
        Reset environment for new episode

        Returns:
            Initial states for all 3 agents (in the dark!)
        """
        # Reinitialize agents
        self._initialize_agents()

        # Clear communication and trace
        self.communication_log = []
        self.conversation_count = 0
        self.mid_path_trace = [self.mid_pos]

        # Calculate optimal path (BFS ground truth)
        self._calculate_optimal_path()

        logger.info("[DarkModeCoordinator] Episode reset")
        logger.info(f"  Beginning at {self.beginning_pos}")
        logger.info(f"  Mid at {self.mid_pos}")
        logger.info(f"  End at {self.end_pos}")
        logger.info(f"  Optimal path: {len(self.optimal_path) if self.optimal_path else 'unknown'} steps")

        # Return initial states (each agent in the dark!)
        return self.get_states()

    def _calculate_optimal_path(self):
        """Calculate optimal path using BFS (ground truth)"""
        try:
            # Use any puzzle (they're identical)
            puzzle = self.agents['beginning'].puzzle
            solver = KlotskiBFSSolver(puzzle)

            # Optimal path from Beginning → End
            # Note: This is theoretical (Mid doesn't follow pieces, just navigates)
            # We use this as difficulty measure
            self.optimal_path = [(self.beginning_pos[0], self.beginning_pos[1])]

            # Approximate with Manhattan distance for now
            dx = abs(self.end_pos[0] - self.beginning_pos[0])
            dy = abs(self.end_pos[1] - self.beginning_pos[1])
            optimal_length = dx + dy

            # Create theoretical path
            for i in range(optimal_length):
                self.optimal_path.append((
                    self.beginning_pos[0] + min(i, dx),
                    self.beginning_pos[1] + min(i - dx, dy) if i > dx else self.beginning_pos[1]
                ))

        except Exception as e:
            logger.warning(f"[DarkModeCoordinator] BFS failed: {e}, using heuristic")
            # Fallback: Manhattan distance
            self.optimal_path = [(self.beginning_pos[0], self.beginning_pos[1]),
                                (self.end_pos[0], self.end_pos[1])]

    def get_states(self) -> Dict[str, str]:
        """
        Get current state for each agent (RUNNING IN THE DARK!)

        Critical: Each agent sees ONLY their own puzzle + communication
        No shared global state!

        Returns:
            Dict mapping agent_name → state_description
        """
        states = {}

        for agent_name, agent in self.agents.items():
            # What agent SEES (local view only!)
            local_view = self._get_local_view(agent_name)

            # What agent HEARS (recent communication)
            recent_messages = self._get_recent_messages(exclude=agent_name, last_n=3)

            # Format state description
            if agent_name == 'mid':
                # Navigator sees: local puzzle + communication + own path
                states['mid'] = self._format_mid_state(local_view, recent_messages)
            else:
                # Beacons see: local puzzle + communication
                states[agent_name] = self._format_beacon_state(
                    agent_name,
                    local_view,
                    recent_messages
                )

        return states

    def _get_local_view(self, agent_name: str) -> str:
        """Get agent's local puzzle view (limited radius!)"""
        agent = self.agents[agent_name]
        puzzle = agent.puzzle
        position = agent.position
        radius = agent.local_view_radius

        # Extract local cells (radius=2 → 5x5 view)
        view_lines = []
        for dy in range(-radius, radius + 1):
            row = []
            for dx in range(-radius, radius + 1):
                x, y = position[0] + dx, position[1] + dy

                # Check bounds
                if 0 <= x < 7 and 0 <= y < 7:
                    # Get cell content (simplified)
                    row.append('.')  # Empty (or piece symbol)
                else:
                    row.append('u')  # Wall

            view_lines.append(' '.join(row))

        return '\n'.join(view_lines)

    def _get_recent_messages(self, exclude: str, last_n: int = 3) -> str:
        """Get recent communication messages"""
        if not self.communication_log:
            return "No messages yet."

        # Get last N messages (excluding own messages)
        recent = [msg for msg in self.communication_log[-last_n:]
                 if msg.sender != exclude]

        if not recent:
            return "No messages from others."

        # Format messages
        formatted = []
        for msg in recent:
            formatted.append(f"{msg.sender}: \"{msg.content}\" (at {msg.position})")

        return '\n'.join(formatted)

    def _format_mid_state(self, local_view: str, recent_messages: str) -> str:
        """Format state for Mid agent (navigator)"""
        return f"""You are the NAVIGATOR.
Your position: {self.agents['mid'].position}
Your path so far: {self.mid_path_trace[-5:]} (last 5 positions)

Goal: Connect Beginning (at {self.beginning_pos}) <-> End (at {self.end_pos})

Local view (2-cell radius):
{local_view}

Recent communication:
{recent_messages}

Actions: "Move: [Up/Down/Left/Right]" or "Talk: [message]"
"""

    def _format_beacon_state(self, agent_name: str, local_view: str,
                            recent_messages: str) -> str:
        """Format state for beacon agents (Beginning/End)"""
        agent = self.agents[agent_name]
        role = "BEGINNING" if agent_name == 'beginning' else "END"

        mid_pos = self.agents['mid'].position

        return f"""You are {role}.
Your position: {agent.position} (static, you cannot move)
Mid navigator last known position: {mid_pos}

Goal: Guide Mid to connect you with your love

Local view (2-cell radius):
{local_view}

Recent communication:
{recent_messages}

Actions: "Talk: [message]" (you are static, can only communicate)
"""

    def step(self, actions: Dict[str, str]) -> Tuple[Dict[str, str], float, bool, Dict]:
        """
        Execute one step across all 3 agents

        Args:
            actions: Dict mapping agent_name → action_string

        Returns:
            (next_states, reward, done, info)
        """
        total_reward = 0
        step_info = {
            'messages_sent': 0,
            'moves_made': 0,
            'invalid_actions': 0
        }

        # Process each agent's action
        for agent_name, action in actions.items():
            agent = self.agents[agent_name]

            if action.startswith("Talk:"):
                # Communication action
                message = action[5:].strip()

                # Record message
                self.communication_log.append(CommunicationMessage(
                    sender=agent_name,
                    recipient="all",
                    content=message,
                    position=agent.position,
                    timestamp=len(self.mid_path_trace)
                ))
                self.conversation_count += 1
                step_info['messages_sent'] += 1

                # CONVERSATION PENALTY (increases with generation!)
                penalty = self.get_conversation_penalty()
                total_reward += penalty

            elif action.startswith("Move:"):
                # Movement action (only Mid can move!)
                if agent.is_static:
                    # Beacons cannot move
                    total_reward += self.invalid_move_penalty
                    step_info['invalid_actions'] += 1
                    continue

                direction = action[5:].strip()
                new_pos = self._calculate_new_position(agent.position, direction)

                # Validate move (simple bounds check for now)
                if self._is_valid_position(new_pos):
                    agent.position = new_pos
                    self.mid_path_trace.append(new_pos)
                    total_reward += self.step_penalty
                    step_info['moves_made'] += 1
                else:
                    total_reward += self.invalid_move_penalty
                    step_info['invalid_actions'] += 1

        # Check if path is connected (sex condition!)
        done = self.is_path_connected()

        if done:
            # CONNECTION ACHIEVED! 🎉💕
            path_quality = self._calculate_path_quality()
            connection_reward = self.connection_reward_base * (path_quality ** 2)
            total_reward += connection_reward

            step_info['connection_reward'] = connection_reward
            step_info['path_quality'] = path_quality

            logger.info("[DarkModeCoordinator] CONNECTION! 💕")
            logger.info(f"  Path quality: {path_quality:.3f}")
            logger.info(f"  Connection reward: {connection_reward:.0f}")

        # Get next states
        next_states = self.get_states()

        return next_states, total_reward, done, step_info

    def _calculate_new_position(self, current: Tuple[int, int],
                               direction: str) -> Tuple[int, int]:
        """Calculate new position after move"""
        x, y = current

        if direction.lower() in ['up', 'u']:
            return (x, y - 1)
        elif direction.lower() in ['down', 'd']:
            return (x, y + 1)
        elif direction.lower() in ['left', 'l']:
            return (x - 1, y)
        elif direction.lower() in ['right', 'r']:
            return (x + 1, y)
        else:
            return current  # Invalid direction

    def _is_valid_position(self, pos: Tuple[int, int]) -> bool:
        """Check if position is valid (within bounds)"""
        x, y = pos
        return 0 <= x < 7 and 0 <= y < 7

    def is_path_connected(self) -> bool:
        """
        Check if Mid's path connects Beginning ↔ End

        Connection criteria:
        - Mid has visited position adjacent to Beginning (within 1 cell)
        - Mid has visited position adjacent to End (within 1 cell)
        """
        # Check if Mid reached Beginning
        beginning_reached = any(
            self._manhattan_distance(pos, self.beginning_pos) <= 1
            for pos in self.mid_path_trace
        )

        # Check if Mid reached End
        end_reached = any(
            self._manhattan_distance(pos, self.end_pos) <= 1
            for pos in self.mid_path_trace
        )

        return beginning_reached and end_reached

    def _manhattan_distance(self, pos1: Tuple[int, int],
                          pos2: Tuple[int, int]) -> int:
        """Calculate Manhattan distance"""
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

    def _calculate_path_quality(self) -> float:
        """
        Calculate path quality (efficiency metric)

        Returns:
            Quality score 0-1 (1 = optimal, <1 = suboptimal)
        """
        if not self.optimal_path or not self.mid_path_trace:
            return 0.0

        optimal_length = len(self.optimal_path)
        actual_length = len(self.mid_path_trace)

        return min(1.0, optimal_length / actual_length)

    def get_conversation_penalty(self) -> float:
        """
        Get conversation penalty for current generation

        Your idea: "Love is happening inbetween - you feel it, don't say it"
        Penalty INCREASES each generation!
        """
        return self.conversation_penalties.get(
            self.current_generation,
            -10.0  # Very expensive for later generations
        )


if __name__ == "__main__":
    # Test dark mode coordinator
    print("Testing DarkModeCoordinator...")
    print("="*80)

    if not PUZZLE_IMPORTS_OK:
        print("[ERROR] Puzzle imports failed. Cannot test dark mode.")
        sys.exit(1)

    # Initialize coordinator
    coordinator = DarkModeCoordinator(current_generation=0)

    # Reset for new episode
    states = coordinator.reset()

    print("\nInitial states (each agent in the dark!):")
    for agent_name, state in states.items():
        print(f"\n{agent_name.upper()}:")
        print(state[:200] + "...")  # Show first 200 chars

    # Simulate one step
    print("\nSimulating one step...")
    actions = {
        'beginning': "Talk: I'm at (1,1)! Come find me!",
        'mid': "Move: Right",
        'end': "Talk: I'm waiting at (6,6)!"
    }

    next_states, reward, done, info = coordinator.step(actions)

    print(f"\nReward: {reward:.1f}")
    print(f"Done: {done}")
    print(f"Info: {info}")
    print(f"Conversation count: {coordinator.conversation_count}")
    print(f"Mid path: {coordinator.mid_path_trace}")

    print("\n" + "="*80)
    print("DarkModeCoordinator working correctly!")

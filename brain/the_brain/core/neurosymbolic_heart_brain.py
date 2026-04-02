"""
NeuroSymbolic Heart/Brain Dual System

Integrates the real NeuroSymbolicBrain (3.7M parameters, 10 modules) into the
romantic evolutionary training framework.

Key Concepts:
- Heart: Frozen pretrained brain (70% weight) - emotional guide, fast intuition
- Brain: Evolving brain (30% weight) - logical reasoning, learns each generation
- Dual System: Weighted voting between Heart and Brain for actions

Brain Modules (10 total):
- VIS (Visual): Spatial awareness
- AUD (Auditory): Pattern recognition
- SOM (Somatosensory): Tactile feedback
- LAN (Language): Symbolic reasoning
- DLPFC (Dorsolateral Prefrontal): Planning and working memory
- OFC (Orbitofrontal): Value and reward
- ACC (Anterior Cingulate): Conflict monitoring
- INS (Insula): Interoception and salience
- MTL (Medial Temporal): Episodic memory
- DMN (Default Mode): Integration and self-reference

Usage:
    from core.neurosymbolic_heart_brain import NeuroSymbolicHeartSystem, NeuroSymbolicBrainSystem, DualSystemAgent

    # Initialize systems
    heart = NeuroSymbolicHeartSystem(pretrained_path="path/to/pretrained.pth")
    brain = NeuroSymbolicBrainSystem()
    agent = DualSystemAgent(heart, brain, heart_weight=0.7, brain_weight=0.3)

    # Make decision
    action, info = agent.select_action(puzzle_state)

    # Train brain (heart stays frozen)
    agent.update_brain(reward, next_state)
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import logging
import copy

logger = logging.getLogger(__name__)

# Import MAML from meta_learning (Phase 8B)
try:
    from core.meta_learning import MAMLOptimizer, TaskDistribution, Task
    MAML_AVAILABLE = True
    logger.info("[NeuroSymbolicHeartBrain] MAML meta-learning imported successfully!")
except ImportError:
    MAML_AVAILABLE = False
    logger.warning("[NeuroSymbolicHeartBrain] MAML not available - meta-learning disabled")

# Try to import real NeuroSymbolicBrain
try:
    import sys
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    from learning_engine.klotski.neurosymbolic.core.neurosymbolic_brain import NeuroSymbolicBrain
    from learning_engine.klotski.neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece
    NEUROSYMBOLIC_AVAILABLE = True
    logger.info("[NeuroSymbolicHeartBrain] Real NeuroSymbolicBrain imported successfully!")
except ImportError as e:
    logger.warning(f"[NeuroSymbolicHeartBrain] Could not import NeuroSymbolicBrain: {e}")
    logger.warning("[NeuroSymbolicHeartBrain] Using fallback mode with simple heuristics")
    NEUROSYMBOLIC_AVAILABLE = False

    # Fallback: Simple mock class
    class NeuroSymbolicBrain(nn.Module):
        def __init__(self, feature_dim=256, num_actions=40, memory_size=100):
            super().__init__()
            self.feature_dim = feature_dim
            self.num_actions = num_actions
            self.fc = nn.Linear(20, num_actions)  # Accept flattened 20-dim boards

        def forward(self, state_features, return_activations=False, return_components=False):
            # Flatten if needed (for 5x4 board input)
            if state_features.dim() > 2:
                state_features = state_features.view(state_features.size(0), -1)
            action_logits = self.fc(state_features)

            if return_components:
                # Return dict format matching real NeuroSymbolicBrain
                return {
                    'action_logits': action_logits,
                    'consciousness': torch.tensor([0.5]),
                    'dmn_energy': torch.tensor([0.0]),
                    'error_magnitude': torch.tensor([0.0]),
                    'value': torch.tensor([[0.0]])
                }
            elif return_activations:
                # Mock 10 module activations (legacy format)
                activations = {
                    'VIS': torch.rand(1, 64).to(state_features.device),
                    'AUD': torch.rand(1, 64).to(state_features.device),
                    'SOM': torch.rand(1, 64).to(state_features.device),
                    'LAN': torch.rand(1, 64).to(state_features.device),
                    'DLPFC': torch.rand(1, 128).to(state_features.device),
                    'OFC': torch.rand(1, 64).to(state_features.device),
                    'ACC': torch.rand(1, 64).to(state_features.device),
                    'INS': torch.rand(1, 64).to(state_features.device),
                    'MTL': torch.rand(1, 128).to(state_features.device),
                    'DMN': torch.rand(1, 128).to(state_features.device)
                }
                return action_logits, activations
            return action_logits

    class PuzzleState:
        def __init__(self, blocks=None, hash_value=None):
            self.blocks = blocks or []
            self.hash = hash_value or "fallback_state"


class NeuroSymbolicHeartSystem:
    """
    The Heart: Frozen pretrained NeuroSymbolicBrain (70% weight)

    The heart represents emotional intelligence and fast intuition.
    It's been pretrained on BFS demonstrations and never changes during evolution.
    Like biological emotion, it provides stable, reliable guidance.

    Properties:
    - Frozen parameters (no gradient updates)
    - Fast inference (no backprop)
    - Pretrained on expert demonstrations
    - 70% voting weight in dual system
    """

    def __init__(
        self,
        pretrained_path: Optional[str] = None,
        feature_dim: int = 256,  # Internal feature dimension (NOT input dimension)
        num_actions: int = 40,
        memory_size: int = 100,
        device: str = 'cpu'
    ):
        """
        Initialize Heart System with frozen pretrained brain.

        Args:
            pretrained_path: Path to pretrained brain weights (.pth file)
            feature_dim: Feature dimension for brain input
            num_actions: Number of possible actions (40 for Klotski)
            memory_size: Size of episodic memory buffer
            device: 'cpu' or 'cuda'
        """
        self.device = torch.device(device)
        self.feature_dim = feature_dim
        self.num_actions = num_actions
        self.memory_size = memory_size
        self.using_real_brain = NEUROSYMBOLIC_AVAILABLE

        # Initialize frozen brain
        self.brain = NeuroSymbolicBrain(
            feature_dim=feature_dim,
            num_actions=num_actions,
            memory_size=memory_size
        ).to(self.device)

        # Freeze all parameters (heart never learns)
        for param in self.brain.parameters():
            param.requires_grad = False

        # Load pretrained weights if available
        if pretrained_path and Path(pretrained_path).exists():
            self._load_pretrained(pretrained_path)
            logger.info(f"[HeartSystem] Loaded pretrained weights from {pretrained_path}")
        else:
            logger.warning("[HeartSystem] No pretrained weights loaded - using random initialization")

        # Set to eval mode (no dropout, etc.)
        self.brain.eval()

        # Statistics
        self.total_decisions = 0
        self.confidence_scores = []

    def _load_pretrained(self, path: str):
        """Load pretrained weights from file."""
        try:
            checkpoint = torch.load(path, map_location=self.device, weights_only=False)
            if 'model_state_dict' in checkpoint:
                self.brain.load_state_dict(checkpoint['model_state_dict'])
            else:
                self.brain.load_state_dict(checkpoint)
            logger.info("[HeartSystem] Pretrained weights loaded successfully")
        except Exception as e:
            logger.error(f"[HeartSystem] Failed to load pretrained weights: {e}")

    def select_action(
        self,
        puzzle_state: Any,
        return_distribution: bool = False
    ) -> Tuple[int, Dict]:
        """
        Select action using frozen pretrained brain.

        Args:
            puzzle_state: Current puzzle state (hash or PuzzleState object)
            return_distribution: If True, return full action distribution

        Returns:
            action: Selected action index
            info: Dictionary with confidence, activations, etc.
        """
        with torch.no_grad():  # No gradients for frozen heart
            # Set to eval mode for inference (BatchNorm needs this for single samples)
            was_training = self.brain.training
            self.brain.eval()

            # Convert puzzle state to features
            state_features = self._state_to_features(puzzle_state)

            # Forward pass through brain (returns Dict)
            output = self.brain(state_features, return_components=True)

            # Restore training mode if it was training
            if was_training:
                self.brain.train()

            # Extract action logits from output dict
            action_logits = output['action_logits']

            # Create module activations from output (for monitoring)
            module_activations = {
                'consciousness': output.get('consciousness', torch.tensor([0.5])),
                'dmn_energy': output.get('dmn_energy', torch.tensor([0.0])),
                'error_magnitude': output.get('error_magnitude', torch.tensor([0.0])),
                'value': output.get('value', torch.tensor([[0.0]]))
            }

            # Compute action probabilities
            action_probs = torch.softmax(action_logits, dim=-1)

            # Select action (greedy for heart - stable and reliable)
            action = torch.argmax(action_probs, dim=-1).item()
            confidence = action_probs[0, action].item()

            # Extract module activation levels (for monitoring)
            module_levels = self._extract_module_levels(module_activations)

            # Update statistics
            self.total_decisions += 1
            self.confidence_scores.append(confidence)

            # Prepare info dictionary
            info = {
                'action': action,
                'confidence': confidence,
                'module_activations': module_levels,
                'action_distribution': action_probs[0].cpu().numpy() if return_distribution else None,
                'system': 'heart',
                'frozen': True
            }

            return action, info

    def _parse_representation_to_board(self, representation: str) -> np.ndarray:
        """
        Parse representation string to 4x5 board tensor.

        Args:
            representation: String like "jafi.aehddehbbcgbbc." (20 chars, 4×5 row-major)

        Returns:
            Board tensor of shape (20,) with values 0-10:
                0 = empty cell '.'
                1-10 = block IDs mapped from 'a'-'j'
        """
        # Character to ID mapping
        char_to_id = {
            '.': 0,  # Empty
            'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5,
            'f': 6, 'g': 7, 'h': 8, 'i': 9, 'j': 10
        }

        # Parse 20 characters into board
        board = np.zeros(20, dtype=np.float32)
        for idx in range(min(20, len(representation))):
            char = representation[idx]
            board[idx] = char_to_id.get(char, 0)

        # Normalize to [0, 1] range for neural network
        board = board / 10.0  # Max ID is 10

        return board

    def _state_to_features(self, puzzle_state: Any) -> torch.Tensor:
        """
        Convert puzzle state to board tensor.

        Args:
            puzzle_state: State hash string (representation) or board tensor

        Returns:
            Feature tensor of shape (1, 5, 4) for real brain, or (1, 20) for fallback
        """
        if isinstance(puzzle_state, str):
            # Parse representation string to 20-dim board
            board = self._parse_representation_to_board(puzzle_state)
        elif isinstance(puzzle_state, np.ndarray):
            # Already a board tensor
            board = puzzle_state.flatten()
            if len(board) != 20:
                # Fallback: zero-pad or truncate
                new_board = np.zeros(20, dtype=np.float32)
                new_board[:min(20, len(board))] = board[:min(20, len(board))]
                board = new_board
        else:
            # Unknown format - create empty board
            board = np.zeros(20, dtype=np.float32)

        # Convert to tensor
        board_tensor = torch.FloatTensor(board).to(self.device)

        if self.using_real_brain:
            # Real brain expects [batch, 5, 4] shape
            return board_tensor.view(1, 5, 4)
        else:
            # Fallback brain expects [batch, 20] shape
            return board_tensor.unsqueeze(0)

    def _extract_module_levels(self, module_activations: Dict) -> Dict[str, float]:
        """
        Extract activation levels for 10 brain modules.

        Args:
            module_activations: Dictionary of module tensors

        Returns:
            Dictionary mapping module names to activation levels [0, 1]
        """
        levels = {}
        for module_name, activation_tensor in module_activations.items():
            # Compute mean activation level
            level = float(torch.mean(torch.abs(activation_tensor)).item())
            # Normalize to [0, 1] range
            level = min(1.0, max(0.0, level))
            levels[module_name] = level

        return levels

    def get_statistics(self) -> Dict:
        """Get heart system statistics."""
        return {
            'total_decisions': self.total_decisions,
            'avg_confidence': np.mean(self.confidence_scores) if self.confidence_scores else 0.0,
            'frozen': True,
            'system': 'heart'
        }


class NeuroSymbolicBrainSystem:
    """
    The Brain: Evolving NeuroSymbolicBrain (30% weight)

    The brain represents logical reasoning and learning.
    It starts with random weights and evolves each generation through PPO training.
    Like biological cognition, it learns from experience but is slower and more deliberate.

    Properties:
    - Trainable parameters (gradient updates enabled)
    - Evolves each generation
    - Learns from rewards and failures
    - 30% voting weight in dual system
    """

    def __init__(
        self,
        feature_dim: int = 256,
        num_actions: int = 40,
        memory_size: int = 100,
        learning_rate: float = 1e-4,
        device: str = 'cpu'
    ):
        """
        Initialize Brain System with trainable brain.

        Args:
            feature_dim: Feature dimension for brain input
            num_actions: Number of possible actions (40 for Klotski)
            memory_size: Size of episodic memory buffer
            learning_rate: Learning rate for optimization
            device: 'cpu' or 'cuda'
        """
        self.device = torch.device(device)
        self.feature_dim = feature_dim
        self.num_actions = num_actions
        self.memory_size = memory_size
        self.learning_rate = learning_rate

        # Initialize trainable brain
        self.brain = NeuroSymbolicBrain(
            feature_dim=feature_dim,
            num_actions=num_actions,
            memory_size=memory_size
        ).to(self.device)

        # Optimizer for learning
        self.optimizer = torch.optim.Adam(self.brain.parameters(), lr=learning_rate)

        # Set to train mode
        self.brain.train()

        # Experience buffer for PPO
        self.experience_buffer = []

        # Statistics
        self.total_decisions = 0
        self.total_updates = 0
        self.confidence_scores = []
        self.loss_history = []

    def select_action(
        self,
        puzzle_state: Any,
        return_distribution: bool = False,
        sample: bool = True
    ) -> Tuple[int, Dict]:
        """
        Select action using evolving brain.

        Args:
            puzzle_state: Current puzzle state (hash or PuzzleState object)
            return_distribution: If True, return full action distribution
            sample: If True, sample from distribution; if False, take greedy action

        Returns:
            action: Selected action index
            info: Dictionary with confidence, activations, etc.
        """
        # Set to eval mode for inference (BatchNorm needs this for single samples)
        was_training = self.brain.training
        self.brain.eval()

        # Convert puzzle state to features
        state_features = self._state_to_features(puzzle_state)

        # Forward pass through brain (returns Dict)
        with torch.no_grad():  # No gradients during action selection
            output = self.brain(state_features, return_components=True)

        # Restore training mode
        if was_training:
            self.brain.train()

        # Extract action logits from output dict
        action_logits = output['action_logits']

        # Create module activations from output (for monitoring)
        module_activations = {
            'consciousness': output.get('consciousness', torch.tensor([0.5])),
            'dmn_energy': output.get('dmn_energy', torch.tensor([0.0])),
            'error_magnitude': output.get('error_magnitude', torch.tensor([0.0])),
            'value': output.get('value', torch.tensor([[0.0]]))
        }

        # Compute action probabilities
        action_probs = torch.softmax(action_logits, dim=-1)

        # Select action (sample for exploration during training)
        if sample:
            action_dist = torch.distributions.Categorical(action_probs)
            action = action_dist.sample().item()
        else:
            action = torch.argmax(action_probs, dim=-1).item()

        confidence = action_probs[0, action].item()

        # Extract module activation levels
        module_levels = self._extract_module_levels(module_activations)

        # Update statistics
        self.total_decisions += 1
        self.confidence_scores.append(confidence)

        # Prepare info dictionary
        info = {
            'action': action,
            'confidence': confidence,
            'module_activations': module_levels,
            'action_distribution': action_probs[0].detach().cpu().numpy() if return_distribution else None,
            'action_logits': action_logits[0].detach(),
            'system': 'brain',
            'trainable': True
        }

        return action, info

    def _state_to_features(self, puzzle_state: Any) -> torch.Tensor:
        """
        Convert puzzle state to board tensor for NeuroSymbolicBrain.

        The state hash is a 20-character string representing the 4x5 board.
        Each character represents a cell type:
        - '0' = empty
        - '1' = 1x1 piece
        - '2' = vertical 1x2 piece
        - '3' = horizontal 2x1 piece
        - '4' = 2x2 goal piece

        Returns:
            Board tensor of shape (1, 5, 4) for the brain
        """
        board = np.zeros((5, 4), dtype=np.float32)

        if isinstance(puzzle_state, str) and len(puzzle_state) == 20:
            # Parse the 20-character state hash as a board representation
            for i, char in enumerate(puzzle_state):
                row = i // 4
                col = i % 4
                try:
                    board[row, col] = float(char)
                except ValueError:
                    # Handle non-numeric characters (from old format)
                    board[row, col] = ord(char) % 5
        elif isinstance(puzzle_state, str):
            # Old format - generate deterministic features from hash
            hash_int = hash(puzzle_state)
            for row in range(5):
                for col in range(4):
                    board[row, col] = abs(hash_int + row * 4 + col) % 5
        elif hasattr(puzzle_state, 'blocks'):
            # PuzzleState object
            for i, block in enumerate(puzzle_state.blocks[:10]):
                if hasattr(block, 'x') and hasattr(block, 'y'):
                    x, y = int(block.x), int(block.y)
                    if 0 <= y < 5 and 0 <= x < 4:
                        board[y, x] = i + 1

        return torch.FloatTensor(board).unsqueeze(0).to(self.device)

    def _extract_module_levels(self, module_activations: Dict) -> Dict[str, float]:
        """Extract activation levels for 10 brain modules (same as Heart)."""
        levels = {}
        for module_name, activation_tensor in module_activations.items():
            level = float(torch.mean(torch.abs(activation_tensor)).item())
            level = min(1.0, max(0.0, level))
            levels[module_name] = level
        return levels

    def store_experience(
        self,
        state: Any,
        action: int,
        reward: float,
        next_state: Any,
        done: bool,
        action_logits: torch.Tensor
    ):
        """
        Store experience for PPO training.

        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Episode done flag
            action_logits: Action logits from brain
        """
        self.experience_buffer.append({
            'state': state,
            'action': action,
            'reward': reward,
            'next_state': next_state,
            'done': done,
            'action_logits': action_logits.detach()
        })

    def update(self, ppo_epochs: int = 4, clip_epsilon: float = 0.2) -> Dict:
        """
        Update brain using PPO on collected experiences.

        Args:
            ppo_epochs: Number of PPO update epochs
            clip_epsilon: PPO clipping parameter

        Returns:
            Dictionary with training metrics
        """
        if len(self.experience_buffer) == 0:
            return {'loss': 0.0, 'num_updates': 0}

        # Convert experience buffer to tensors
        states = [exp['state'] for exp in self.experience_buffer]
        actions = torch.LongTensor([exp['action'] for exp in self.experience_buffer]).to(self.device)
        rewards = torch.FloatTensor([exp['reward'] for exp in self.experience_buffer]).to(self.device)
        old_action_logits = torch.stack([exp['action_logits'] for exp in self.experience_buffer])

        # Compute returns (simple Monte Carlo for now)
        returns = torch.zeros_like(rewards)
        G = 0
        for t in reversed(range(len(rewards))):
            G = rewards[t] + 0.99 * G  # Gamma = 0.99
            returns[t] = G

        # Normalize returns
        returns = (returns - returns.mean()) / (returns.std() + 1e-8)

        # PPO update
        total_loss = 0.0
        for epoch in range(ppo_epochs):
            # Recompute action logits
            state_features_batch = torch.cat([self._state_to_features(s) for s in states])
            new_action_logits, _ = self.brain(state_features_batch, return_activations=True)

            # Compute probability ratios
            old_probs = torch.softmax(old_action_logits, dim=-1)
            new_probs = torch.softmax(new_action_logits, dim=-1)

            old_action_probs = old_probs.gather(1, actions.unsqueeze(1)).squeeze()
            new_action_probs = new_probs.gather(1, actions.unsqueeze(1)).squeeze()

            ratio = new_action_probs / (old_action_probs + 1e-8)

            # PPO clipped objective
            surr1 = ratio * returns
            surr2 = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon) * returns
            loss = -torch.min(surr1, surr2).mean()

            # Backprop and update
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.brain.parameters(), max_norm=0.5)
            self.optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / ppo_epochs
        self.loss_history.append(avg_loss)
        self.total_updates += 1

        # Clear experience buffer
        self.experience_buffer.clear()

        return {
            'loss': avg_loss,
            'num_updates': self.total_updates,
            'num_experiences': len(states)
        }

    def get_statistics(self) -> Dict:
        """Get brain system statistics."""
        return {
            'total_decisions': self.total_decisions,
            'total_updates': self.total_updates,
            'avg_confidence': np.mean(self.confidence_scores) if self.confidence_scores else 0.0,
            'avg_loss': np.mean(self.loss_history[-100:]) if self.loss_history else 0.0,
            'trainable': True,
            'system': 'brain'
        }

    def reset_for_new_generation(self):
        """
        Reset brain for new generation.

        Clears experience buffer and statistics but keeps learned weights.
        Called when reproduction creates a new generation.
        """
        self.experience_buffer.clear()
        self.confidence_scores.clear()
        self.loss_history.clear()
        self.total_decisions = 0
        self.total_updates = 0
        logger.info("[NeuroSymbolicBrainSystem] Reset for new generation")


class DualSystemAgent:
    """
    Dual System Agent: Weighted combination of Heart (70%) and Brain (30%)

    This agent combines the frozen pretrained Heart with the evolving Brain
    through weighted voting. The Heart provides stable emotional guidance while
    the Brain learns logical reasoning.

    Like humans, decisions are influenced by both emotion (heart) and logic (brain),
    with emotion typically being the stronger but slower-to-change guide.
    """

    def __init__(
        self,
        heart_system: NeuroSymbolicHeartSystem,
        brain_system: NeuroSymbolicBrainSystem,
        heart_weight: float = 0.7,
        brain_weight: float = 0.3
    ):
        """
        Initialize Dual System Agent.

        Args:
            heart_system: Frozen pretrained heart
            brain_system: Evolving brain
            heart_weight: Weight for heart decisions (default 0.7)
            brain_weight: Weight for brain decisions (default 0.3)
        """
        self.heart = heart_system
        self.brain = brain_system
        self.heart_weight = heart_weight
        self.brain_weight = brain_weight

        # Ensure weights sum to 1.0
        total = heart_weight + brain_weight
        self.heart_weight /= total
        self.brain_weight /= total

        # Decision tracking
        self.total_decisions = 0
        self.heart_dominant_count = 0
        self.brain_dominant_count = 0
        self.agreement_count = 0

    def select_action(
        self,
        puzzle_state: Any,
        sample: bool = True
    ) -> Tuple[int, Dict]:
        """
        Select action using weighted combination of heart and brain.

        Args:
            puzzle_state: Current puzzle state
            sample: If True, sample from combined distribution

        Returns:
            action: Selected action
            info: Dictionary with dual system details
        """
        # Get actions and info from both systems
        heart_action, heart_info = self.heart.select_action(puzzle_state, return_distribution=True)
        brain_action, brain_info = self.brain.select_action(puzzle_state, return_distribution=True, sample=False)

        # Get action distributions
        heart_dist = heart_info['action_distribution']
        brain_dist = brain_info['action_distribution']

        # Weighted combination
        combined_dist = self.heart_weight * heart_dist + self.brain_weight * brain_dist

        # Select action from combined distribution
        if sample:
            combined_dist_tensor = torch.FloatTensor(combined_dist)
            action_dist = torch.distributions.Categorical(combined_dist_tensor)
            action = action_dist.sample().item()
        else:
            action = int(np.argmax(combined_dist))

        # Determine agreement/disagreement
        agreement = (heart_action == brain_action)
        if agreement:
            self.agreement_count += 1

        # Determine which system is dominant for this action
        if combined_dist[heart_action] > combined_dist[brain_action]:
            dominant = 'heart'
            self.heart_dominant_count += 1
        else:
            dominant = 'brain'
            self.brain_dominant_count += 1

        self.total_decisions += 1

        # Combine module activations (weighted average)
        combined_modules = {}
        for module_name in heart_info['module_activations']:
            heart_level = heart_info['module_activations'][module_name]
            brain_level = brain_info['module_activations'][module_name]
            combined_modules[module_name] = (
                self.heart_weight * heart_level + self.brain_weight * brain_level
            )

        # Prepare info dictionary
        info = {
            'action': action,
            'heart_action': heart_action,
            'brain_action': brain_action,
            'heart_confidence': heart_info['confidence'],
            'brain_confidence': brain_info['confidence'],
            'agreement': agreement,
            'dominant_system': dominant,
            'heart_weight': self.heart_weight,
            'brain_weight': self.brain_weight,
            'combined_distribution': combined_dist,
            'module_activations': combined_modules,
            'brain_action_logits': brain_info['action_logits']  # For training
        }

        return action, info

    def update_brain(
        self,
        state: Any,
        action: int,
        reward: float,
        next_state: Any,
        done: bool,
        action_logits: torch.Tensor
    ):
        """
        Update the brain system (heart stays frozen).

        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Episode done flag
            action_logits: Action logits from brain
        """
        self.brain.store_experience(state, action, reward, next_state, done, action_logits)

    def train_brain(self, ppo_epochs: int = 4, clip_epsilon: float = 0.2) -> Dict:
        """
        Train the brain using collected experiences.

        Args:
            ppo_epochs: Number of PPO update epochs
            clip_epsilon: PPO clipping parameter

        Returns:
            Training metrics dictionary
        """
        return self.brain.update(ppo_epochs=ppo_epochs, clip_epsilon=clip_epsilon)

    def learn_from_episode(self, episode_data: Dict):
        """
        Learn from episode data (Brain only, Heart is frozen).

        Compatibility method for multi_generational_trainer.
        Extracts state-action-reward tuples and stores experiences for PPO.

        Args:
            episode_data: Dict with 'success', 'quality', 'path', 'actions'
        """
        if not episode_data.get('success', False):
            return

        path = episode_data.get('path', [])
        actions = episode_data.get('actions', [])
        quality = episode_data.get('quality', 0.0)

        if len(path) < 2 or len(actions) < 1:
            return

        # Store experiences for later PPO update
        for i, (state, action) in enumerate(zip(path[:-1], actions)):
            # Reward shaping: higher reward for later states in successful path
            reward = quality * (len(path) - i) / len(path)
            next_state = path[i + 1] if i + 1 < len(path) else state
            done = (i == len(path) - 2)

            # Get action logits for this state
            _, info = self.brain.select_action(state, sample=False)
            self.brain.store_experience(
                state, action, reward, next_state, done,
                info.get('action_logits')
            )

    def reset_for_new_generation(self):
        """
        Reset for new generation.

        Clears brain's experience buffer and resets decision tracking.
        Heart stays frozen (never changes). Called when reproduction
        triggers a new generation.
        """
        self.brain.reset_for_new_generation()
        self.total_decisions = 0
        self.heart_dominant_count = 0
        self.brain_dominant_count = 0
        self.agreement_count = 0
        logger.info("[DualSystemAgent] Reset for new generation")

    def get_statistics(self) -> Dict:
        """Get dual system statistics."""
        heart_stats = self.heart.get_statistics()
        brain_stats = self.brain.get_statistics()

        stats = {
            'total_decisions': self.total_decisions,
            'heart_dominant_rate': self.heart_dominant_count / max(1, self.total_decisions),
            'brain_dominant_rate': self.brain_dominant_count / max(1, self.total_decisions),
            'agreement_rate': self.agreement_count / max(1, self.total_decisions),
            'heart_weight': self.heart_weight,
            'brain_weight': self.brain_weight,
            'heart_stats': heart_stats,
            'brain_stats': brain_stats
        }

        # Add MAML stats if enabled
        if hasattr(self, 'maml_optimizer') and self.maml_optimizer is not None:
            stats['maml_enabled'] = True
            stats['maml_adaptations'] = getattr(self, '_maml_adaptation_count', 0)
        else:
            stats['maml_enabled'] = False

        return stats

    # =========================================================================
    # MAML Meta-Learning Methods (Phase 8B)
    # =========================================================================

    def enable_maml(
        self,
        inner_lr: float = 0.01,
        outer_lr: float = 0.001,
        inner_steps: int = 5,
        first_order: bool = True
    ) -> bool:
        """
        Enable MAML (Model-Agnostic Meta-Learning) for the brain system.

        This allows the brain to rapidly adapt to new task distributions
        using few-shot learning. The heart remains frozen.

        Args:
            inner_lr: Learning rate for inner loop (task adaptation)
            outer_lr: Learning rate for outer loop (meta-learning)
            inner_steps: Number of gradient steps in inner loop
            first_order: Use first-order MAML approximation (faster, ~same performance)

        Returns:
            True if MAML was enabled, False if MAML not available
        """
        if not MAML_AVAILABLE:
            logger.warning("[DualSystemAgent] MAML not available - install meta_learning module")
            return False

        self.maml_optimizer = MAMLOptimizer(
            model=self.brain.brain,  # The actual nn.Module
            inner_lr=inner_lr,
            outer_lr=outer_lr,
            inner_steps=inner_steps,
            first_order=first_order,
            device=str(self.brain.device)
        )

        self._maml_adaptation_count = 0
        self._task_distribution = TaskDistribution()

        logger.info(f"[DualSystemAgent] MAML enabled: inner_lr={inner_lr}, outer_lr={outer_lr}")
        return True

    def maml_adapt(
        self,
        support_states: List[Any],
        support_actions: List[int],
        support_rewards: List[float],
        adaptation_steps: int = 5
    ) -> Tuple[nn.Module, Dict]:
        """
        Perform MAML inner-loop adaptation to a new task.

        Given a small support set of (state, action, reward) examples,
        adapts the brain to this specific task. The adapted model can then
        be used for action selection on similar states.

        Args:
            support_states: List of puzzle states in support set
            support_actions: Optimal actions for support states
            support_rewards: Rewards for support actions
            adaptation_steps: Number of gradient steps for adaptation

        Returns:
            adapted_model: Task-adapted brain model
            info: Dictionary with adaptation metrics
        """
        if not hasattr(self, 'maml_optimizer') or self.maml_optimizer is None:
            logger.warning("[DualSystemAgent] MAML not enabled - call enable_maml() first")
            return self.brain.brain, {'adapted': False, 'error': 'MAML not enabled'}

        # Convert support set to tensors
        support_x = torch.cat([
            self.brain._state_to_features(s) for s in support_states
        ])
        support_y = torch.LongTensor(support_actions).to(self.brain.device)

        # Define loss function for adaptation
        # Note: inner_loop calls model(support_x) then loss_fn(predictions, targets)
        # For dict output, we need a wrapper that handles the model call
        def ce_loss_fn(predictions, targets):
            # Handle both dict and tensor outputs
            if isinstance(predictions, dict):
                logits = predictions['action_logits']
            else:
                logits = predictions
            return nn.functional.cross_entropy(logits, targets)

        # Perform inner-loop adaptation
        adapted_model, losses = self.maml_optimizer.inner_loop(
            support_x=support_x,
            support_y=support_y,
            loss_fn=ce_loss_fn,
            steps=adaptation_steps
        )

        self._maml_adaptation_count += 1

        info = {
            'adapted': True,
            'initial_loss': losses[0] if losses else 0.0,
            'final_loss': losses[-1] if losses else 0.0,
            'improvement': (losses[0] - losses[-1]) / (losses[0] + 1e-8) if losses else 0.0,
            'adaptation_steps': adaptation_steps,
            'support_size': len(support_states)
        }

        logger.info(f"[DualSystemAgent] MAML adapted: loss {losses[0]:.4f} → {losses[-1]:.4f}")
        return adapted_model, info

    def maml_select_action(
        self,
        puzzle_state: Any,
        adapted_model: nn.Module,
        sample: bool = True
    ) -> Tuple[int, Dict]:
        """
        Select action using a MAML-adapted brain model.

        Uses the adapted model for brain decisions while still combining
        with the frozen heart.

        Args:
            puzzle_state: Current puzzle state
            adapted_model: MAML-adapted brain from maml_adapt()
            sample: If True, sample from distribution

        Returns:
            action: Selected action
            info: Dictionary with dual system details
        """
        # Get heart action (frozen, same as always)
        heart_action, heart_info = self.heart.select_action(puzzle_state, return_distribution=True)

        # Get adapted brain action
        adapted_model.eval()
        with torch.no_grad():
            state_features = self.brain._state_to_features(puzzle_state)
            output = adapted_model(state_features, return_components=True)
            action_logits = output['action_logits']
            brain_probs = torch.softmax(action_logits, dim=-1)
            brain_action = torch.argmax(brain_probs, dim=-1).item()
            brain_confidence = brain_probs[0, brain_action].item()

        # Combine with heart (same weighted voting)
        heart_dist = heart_info['action_distribution']
        brain_dist = brain_probs[0].cpu().numpy()
        combined_dist = self.heart_weight * heart_dist + self.brain_weight * brain_dist

        # Select action
        if sample:
            combined_dist_tensor = torch.FloatTensor(combined_dist)
            action_dist = torch.distributions.Categorical(combined_dist_tensor)
            action = action_dist.sample().item()
        else:
            action = int(np.argmax(combined_dist))

        info = {
            'action': action,
            'heart_action': heart_action,
            'brain_action': brain_action,
            'heart_confidence': heart_info['confidence'],
            'brain_confidence': brain_confidence,
            'maml_adapted': True,
            'combined_distribution': combined_dist
        }

        return action, info

    def maml_meta_train(
        self,
        tasks: List[Dict],
        meta_batch_size: int = 4,
        meta_epochs: int = 10
    ) -> Dict:
        """
        Perform MAML outer-loop meta-training across multiple tasks.

        Each task should have support and query sets. The brain learns
        to quickly adapt to new tasks after meta-training.

        Args:
            tasks: List of task dictionaries with 'support_*' and 'query_*' keys
            meta_batch_size: Number of tasks per meta-update
            meta_epochs: Number of meta-training epochs

        Returns:
            Dictionary with meta-training metrics
        """
        if not hasattr(self, 'maml_optimizer') or self.maml_optimizer is None:
            logger.warning("[DualSystemAgent] MAML not enabled - call enable_maml() first")
            return {'success': False, 'error': 'MAML not enabled'}

        # Convert task dicts to Task objects
        task_objects = []
        for i, task_dict in enumerate(tasks):
            # Convert states to features
            support_x = torch.cat([
                self.brain._state_to_features(s) for s in task_dict['support_states']
            ])
            support_y = torch.LongTensor(task_dict['support_actions']).to(self.brain.device)
            query_x = torch.cat([
                self.brain._state_to_features(s) for s in task_dict['query_states']
            ])
            query_y = torch.LongTensor(task_dict['query_actions']).to(self.brain.device)

            task_obj = Task(
                task_id=f"task_{i}",
                domain=task_dict.get('domain', 'klotski'),
                support_x=support_x,
                support_y=support_y,
                query_x=query_x,
                query_y=query_y,
                metadata=task_dict.get('metadata', {})
            )
            task_objects.append(task_obj)

        # Define loss function (same signature as inner_loop expects)
        def ce_loss_fn(predictions, targets):
            # Handle both dict and tensor outputs
            if isinstance(predictions, dict):
                logits = predictions['action_logits']
            else:
                logits = predictions
            return nn.functional.cross_entropy(logits, targets)

        # Meta-training loop
        meta_losses = []
        for epoch in range(meta_epochs):
            # Sample task batch
            np.random.shuffle(task_objects)
            batch = task_objects[:meta_batch_size]

            # Outer loop update
            meta_loss = self.maml_optimizer.outer_loop(batch, loss_fn=ce_loss_fn)
            meta_losses.append(meta_loss)

            if (epoch + 1) % max(1, meta_epochs // 5) == 0:
                logger.info(f"[DualSystemAgent] Meta-epoch {epoch+1}/{meta_epochs}: loss={meta_loss:.4f}")

        results = {
            'success': True,
            'meta_epochs': meta_epochs,
            'num_tasks': len(tasks),
            'meta_batch_size': meta_batch_size,
            'initial_meta_loss': meta_losses[0] if meta_losses else 0.0,
            'final_meta_loss': meta_losses[-1] if meta_losses else 0.0,
            'meta_loss_history': meta_losses
        }

        logger.info(f"[DualSystemAgent] Meta-training complete: {results['initial_meta_loss']:.4f} → {results['final_meta_loss']:.4f}")
        return results

    def store_task_experience(self, state: Any, action: int, reward: float, domain: str = 'default'):
        """
        Store experience in task distribution for future meta-learning.

        Args:
            state: Puzzle state
            action: Action taken
            reward: Reward received
            domain: Task domain identifier
        """
        if hasattr(self, '_task_distribution'):
            self._task_distribution.add_experience({
                'state': state,
                'action': action,
                'reward': reward
            }, domain=domain)

    def sample_meta_task(self, domain: Optional[str] = None) -> Optional[Dict]:
        """
        Sample a meta-learning task from stored experiences.

        Args:
            domain: Optional domain to sample from

        Returns:
            Task dictionary with support/query sets, or None if insufficient data
        """
        if not hasattr(self, '_task_distribution'):
            return None

        try:
            task = self._task_distribution.sample_task(
                domain=domain,
                n_support=5,
                n_query=10
            )
            return {
                'support_states': task.support_x.tolist() if hasattr(task.support_x, 'tolist') else list(task.support_x),
                'support_actions': task.support_y.tolist() if hasattr(task.support_y, 'tolist') else list(task.support_y),
                'query_states': task.query_x.tolist() if hasattr(task.query_x, 'tolist') else list(task.query_x),
                'query_actions': task.query_y.tolist() if hasattr(task.query_y, 'tolist') else list(task.query_y),
                'domain': task.domain
            }
        except (ValueError, IndexError):
            return None

    def decide_action(
        self,
        current_pos: Tuple[int, int],
        goal_pos: Tuple[int, int],
        recent_messages: List[Any],
        generation: int
    ) -> Tuple[int, float, str]:
        """
        Wrapper method for compatibility with DarkModeCoordinator.

        This method adapts the select_action interface to the decide_action
        interface expected by the multi-generational trainer.

        Args:
            current_pos: Current position (used to create synthetic state)
            goal_pos: Goal position (unused, for compatibility)
            recent_messages: Recent communication (unused, for compatibility)
            generation: Current generation (unused, for compatibility)

        Returns:
            action: Selected action index
            confidence: Combined confidence score
            reasoning: Human-readable reasoning string
        """
        # Create a synthetic state from position
        # Using a hash-like string that encodes the position
        state_str = f"{current_pos[0]:02d}{current_pos[1]:02d}" * 5  # 20 chars

        # Use select_action
        action, info = self.select_action(state_str, sample=True)

        # Extract confidence and create reasoning
        heart_conf = info.get('heart_confidence', 0.5)
        brain_conf = info.get('brain_confidence', 0.5)
        confidence = self.heart_weight * heart_conf + self.brain_weight * brain_conf

        agreement = info.get('agreement', False)
        dominant = info.get('dominant_system', 'brain')

        if agreement:
            reasoning = f"Heart and brain agree on action {action} (confidence: {confidence:.2f})"
        else:
            reasoning = f"{dominant.title()} dominates: action {action} (H:{heart_conf:.2f}, B:{brain_conf:.2f})"

        return action, confidence, reasoning


# Module-level helper functions
def create_dual_system_agent(
    pretrained_heart_path: Optional[str] = None,
    heart_weight: float = 0.7,
    brain_weight: float = 0.3,
    device: str = 'cpu'
) -> DualSystemAgent:
    """
    Factory function to create a DualSystemAgent.

    Args:
        pretrained_heart_path: Path to pretrained heart weights
        heart_weight: Weight for heart (default 0.7)
        brain_weight: Weight for brain (default 0.3)
        device: 'cpu' or 'cuda'

    Returns:
        Initialized DualSystemAgent
    """
    heart = NeuroSymbolicHeartSystem(
        pretrained_path=pretrained_heart_path,
        device=device
    )

    brain = NeuroSymbolicBrainSystem(
        device=device
    )

    agent = DualSystemAgent(
        heart_system=heart,
        brain_system=brain,
        heart_weight=heart_weight,
        brain_weight=brain_weight
    )

    logger.info(f"[DualSystemAgent] Created with Heart={heart_weight:.1%}, Brain={brain_weight:.1%}")
    return agent


if __name__ == "__main__":
    # Test dual system
    print("\n" + "=" * 80)
    print("Testing NeuroSymbolic Heart/Brain Dual System")
    print("=" * 80)

    # Create agent
    agent = create_dual_system_agent(
        pretrained_heart_path=None,  # No pretrained for test
        heart_weight=0.7,
        brain_weight=0.3
    )

    # Test action selection
    test_state = "test_state_hash_12345"
    action, info = agent.select_action(test_state)

    print(f"\nTest State: {test_state}")
    print(f"Selected Action: {action}")
    print(f"Heart Action: {info['heart_action']} (confidence: {info['heart_confidence']:.3f})")
    print(f"Brain Action: {info['brain_action']} (confidence: {info['brain_confidence']:.3f})")
    print(f"Agreement: {info['agreement']}")
    print(f"Dominant System: {info['dominant_system']}")

    print("\nModule Activations:")
    for module, level in info['module_activations'].items():
        bar_length = int(level * 30)
        bar = '#' * bar_length + '.' * (30 - bar_length)
        print(f"  {module:6s}: [{bar}] {level:.3f}")

    # Test brain training
    print("\nTesting Brain Training...")
    for i in range(5):
        state = f"state_{i}"
        action, info = agent.select_action(state)
        reward = np.random.randn()  # Random reward
        next_state = f"state_{i+1}"
        done = (i == 4)

        agent.update_brain(state, action, reward, next_state, done, info['brain_action_logits'])

    train_result = agent.train_brain(ppo_epochs=2)
    print(f"Training Loss: {train_result['loss']:.4f}")

    # Statistics
    stats = agent.get_statistics()
    print("\nDual System Statistics:")
    print(f"  Total Decisions: {stats['total_decisions']}")
    print(f"  Heart Dominant: {stats['heart_dominant_rate']:.1%}")
    print(f"  Brain Dominant: {stats['brain_dominant_rate']:.1%}")
    print(f"  Agreement Rate: {stats['agreement_rate']:.1%}")

    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

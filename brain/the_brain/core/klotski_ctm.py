"""
KlotskiCTM - Klotski NeuroSymbolic Brain as Conscious Turing Machine

Integrates the Klotski neurosymbolic brain as the deep reasoning engine (CTM)
for the Tahlamus cognitive system.

Architecture Integration:
- Tahlamus: System 1 (fast, heuristic routing)
- Klotski CTM: System 2 (slow, deliberate reasoning)

The Klotski brain provides:
- 10 brain modules with Kuratowski graph connectivity
- Consciousness metric (DMN energy-based)
- Symbolic rule constraints (Allis rules)
- Iterative reasoning with convergence detection

Usage:
    from core.klotski_ctm import KlotskiCTM

    ctm = KlotskiCTM(feature_dim=256)
    insights = ctm.reason(task="Deploy Docker", brain_state={...}, max_steps=50)
"""

import sys
import os
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import torch
import torch.nn.functional as F

# Add learning_engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'learning_engine', 'klotski'))

try:
    from neurosymbolic.core.neurosymbolic_brain import NeuroSymbolicBrain
    from neurosymbolic.core.brain_graph import BrainConnectomeGraph
    KLOTSKI_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Klotski neurosymbolic brain not available: {e}")
    KLOTSKI_AVAILABLE = False


@dataclass
class CTMInsight:
    """
    Result of deep CTM reasoning

    Represents the insights gained from iterative reasoning through
    the Klotski neurosymbolic brain.
    """
    task: str
    reasoning_steps: int
    consciousness_trajectory: List[float]
    final_consciousness: float
    converged: bool
    module_activations: Dict[str, float]
    suggested_strategy: str
    confidence: float
    reasoning_trace: List[str]
    dmn_energy: float
    error_magnitude: float


class KlotskiCTM:
    """
    Klotski NeuroSymbolic Brain as Conscious Turing Machine

    This class wraps the Klotski neurosymbolic brain and provides a
    reasoning interface for the Tahlamus hierarchical planner.

    The CTM performs deep, iterative reasoning by:
    1. Encoding task into neural features
    2. Running through 10 brain modules iteratively
    3. Tracking consciousness convergence
    4. Extracting symbolic insights

    Key Innovation: Metaphorical Task-to-Puzzle Mapping
    - Complex tasks are treated as "puzzles" requiring iterative solution
    - Brain modules process different aspects (visual, spatial, planning, etc.)
    - Consciousness metric indicates when solution crystallizes
    """

    def __init__(
        self,
        feature_dim: int = 256,
        num_actions: int = 4,  # Changed from 40 to match trained checkpoint
        memory_size: int = 100,
        consciousness_threshold: float = 0.85,
        max_reasoning_steps: int = 50,
        device: str = 'cpu'
    ):
        """
        Initialize Klotski CTM

        Args:
            feature_dim: Internal feature dimension
            num_actions: Maximum number of actions/strategies
            memory_size: MTL memory capacity
            consciousness_threshold: Convergence threshold
            max_reasoning_steps: Maximum iterative reasoning steps
            device: torch device ('cpu' or 'cuda')
        """
        if not KLOTSKI_AVAILABLE:
            raise RuntimeError("Klotski neurosymbolic brain not available. Check installation.")

        self.feature_dim = feature_dim
        self.num_actions = num_actions
        self.consciousness_threshold = consciousness_threshold
        self.max_reasoning_steps = max_reasoning_steps
        self.device = device

        # Initialize Klotski neurosymbolic brain
        self.brain = NeuroSymbolicBrain(
            feature_dim=feature_dim,
            num_actions=num_actions,
            memory_size=memory_size,
            use_symbolic_rules=True
        ).to(device)

        # Set to eval mode (no training, batch_size=1 ok)
        self.brain.eval()

        # Brain connectivity graph
        self.brain_graph = BrainConnectomeGraph()

        # Module mapping for interpretation
        self.module_map = {
            'VIS': 'visual reasoning',
            'AUD': 'auditory/reward processing',
            'SOM': 'spatial reasoning',
            'LAN': 'language/symbolic reasoning',
            'DLPFC': 'planning and strategy',
            'OFC': 'value estimation',
            'ACC': 'conflict monitoring',
            'INS': 'internal dynamics',
            'MTL': 'memory and association',
            'DMN': 'consciousness integration'
        }

        print(f"[KlotskiCTM] Initialized with {self.brain.get_total_parameters():,} parameters")
        print(f"[KlotskiCTM] Consciousness threshold: {consciousness_threshold}")
        print(f"[KlotskiCTM] Max reasoning steps: {max_reasoning_steps}")

    def load_weights(self, checkpoint_path: str) -> bool:
        """
        Load trained weights from checkpoint file.

        Args:
            checkpoint_path: Path to .pth file with trained weights

        Returns:
            True if weights loaded successfully, False otherwise
        """
        try:
            import os
            if not os.path.exists(checkpoint_path):
                print(f"[KlotskiCTM] Checkpoint not found: {checkpoint_path}")
                return False

            state_dict = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
            self.brain.load_state_dict(state_dict)
            self.brain.eval()
            print(f"[KlotskiCTM] Loaded weights from: {checkpoint_path}")
            return True
        except Exception as e:
            print(f"[KlotskiCTM] Error loading weights: {e}")
            return False

    def _encode_task_to_puzzle(self, task: str, brain_state: Dict) -> torch.Tensor:
        """
        Encode task and brain state into puzzle-like board representation

        This is a metaphorical mapping where:
        - Task complexity → puzzle difficulty
        - Brain modalities → piece positions
        - Goal → solved state

        Args:
            task: Task description string
            brain_state: Current Tahlamus brain state

        Returns:
            Board tensor [batch=1, 5, 4] representing the "puzzle"
        """
        # Create a 5x4 board (like Klotski puzzle)
        board = torch.zeros(1, 5, 4, dtype=torch.long)

        # Encode task features into board positions
        # This is a simplified encoding - in production, use learned embeddings

        # Task complexity → spread of pieces
        task_length = len(task)
        complexity = min(task_length / 100.0, 1.0)

        # Brain modality activations → piece positions
        if 'modality_activations' in brain_state:
            activations = brain_state['modality_activations']
            for i, (mod, act) in enumerate(activations.items()):
                if i >= 20:  # 5x4 = 20 cells
                    break
                row, col = divmod(i, 4)
                board[0, row, col] = int(act * 10)  # Scale to 0-10
        else:
            # Random initialization if no modalities
            board = torch.randint(0, 11, (1, 5, 4))

        return board.to(self.device)

    def reason(
        self,
        task: str,
        brain_state: Dict,
        max_steps: Optional[int] = None,
        return_trajectory: bool = True
    ) -> CTMInsight:
        """
        Perform deep iterative reasoning using Klotski neurosymbolic brain

        This is the main reasoning loop that:
        1. Encodes task as puzzle
        2. Iteratively processes through brain modules
        3. Tracks consciousness convergence
        4. Extracts insights and strategies

        Args:
            task: Task description
            brain_state: Current Tahlamus brain state
            max_steps: Override max reasoning steps
            return_trajectory: Return full reasoning trace

        Returns:
            CTMInsight with reasoning results
        """
        steps = max_steps if max_steps else self.max_reasoning_steps

        print(f"\n[KlotskiCTM] Starting deep reasoning for: {task[:50]}...")
        print(f"[KlotskiCTM] Max steps: {steps}")

        # Reset brain state
        self.brain.reset_state()

        # Encode task to puzzle representation
        board = self._encode_task_to_puzzle(task, brain_state)

        # Reasoning loop
        consciousness_trajectory = []
        reasoning_trace = []
        module_activations = {mod: 0.0 for mod in self.module_map.keys()}

        converged = False
        final_consciousness = 0.0
        dmn_energy = 0.0
        error_magnitude = 0.0

        for step in range(steps):
            # Forward pass through neurosymbolic brain
            with torch.no_grad():
                output = self.brain.forward(
                    board,
                    valid_actions=None,
                    return_components=True
                )

            # Extract metrics
            consciousness = output['consciousness'].item()
            dmn_energy = output['dmn_energy'].item()
            error_magnitude = output['error_magnitude'].item()
            value = output['value'].item()

            # Track consciousness
            consciousness_trajectory.append(consciousness)
            final_consciousness = consciousness

            # Accumulate module activations
            if 'vis_features' in output:
                module_activations['VIS'] += torch.norm(output['vis_features']).item()
            if 'som_features' in output:
                module_activations['SOM'] += torch.norm(output['som_features']).item()
            if 'dlpfc_hidden' in output:
                module_activations['DLPFC'] += torch.norm(output['dlpfc_hidden']).item()
            if 'dmn_state' in output:
                module_activations['DMN'] += torch.norm(output['dmn_state']).item()

            # Generate reasoning trace
            dominant_module = max(
                [(mod, act) for mod, act in module_activations.items()],
                key=lambda x: x[1]
            )[0] if step > 0 else 'VIS'

            thought = (f"Step {step}: [{dominant_module}] "
                      f"Consciousness={consciousness:.3f}, "
                      f"Value={value:.3f}, "
                      f"Error={error_magnitude:.3f}")

            reasoning_trace.append(thought)

            if step % 10 == 0:
                print(f"[KlotskiCTM] {thought}")

            # Check convergence
            if consciousness >= self.consciousness_threshold:
                converged = True
                print(f"[KlotskiCTM] Converged at step {step}! Consciousness={consciousness:.3f}")
                break

            # Update board slightly for next iteration (simulate reasoning dynamics)
            board = board + torch.randint(-1, 2, board.shape).to(self.device)
            board = torch.clamp(board, 0, 10)

        # Normalize module activations
        total_activation = sum(module_activations.values())
        if total_activation > 0:
            module_activations = {
                mod: act / total_activation
                for mod, act in module_activations.items()
            }

        # Generate strategy based on dominant modules
        strategy = self._synthesize_strategy(module_activations, final_consciousness)

        # Compute confidence
        confidence = final_consciousness

        print(f"[KlotskiCTM] Reasoning complete!")
        print(f"[KlotskiCTM] Steps: {len(consciousness_trajectory)}")
        print(f"[KlotskiCTM] Final consciousness: {final_consciousness:.3f}")
        print(f"[KlotskiCTM] Converged: {converged}")
        print(f"[KlotskiCTM] Strategy: {strategy}")

        return CTMInsight(
            task=task,
            reasoning_steps=len(consciousness_trajectory),
            consciousness_trajectory=consciousness_trajectory,
            final_consciousness=final_consciousness,
            converged=converged,
            module_activations=module_activations,
            suggested_strategy=strategy,
            confidence=confidence,
            reasoning_trace=reasoning_trace if return_trajectory else [],
            dmn_energy=dmn_energy,
            error_magnitude=error_magnitude
        )

    def _synthesize_strategy(
        self,
        module_activations: Dict[str, float],
        consciousness: float
    ) -> str:
        """
        Synthesize a strategic recommendation based on module activations

        Args:
            module_activations: Normalized activations per module
            consciousness: Final consciousness score

        Returns:
            Strategy string
        """
        # Find top 3 modules
        top_modules = sorted(
            module_activations.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        # Generate strategy based on dominant modules
        strategies = {
            'DLPFC': 'Break task into sequential steps with clear goals',
            'OFC': 'Focus on value/reward optimization',
            'SOM': 'Consider spatial/topological relationships',
            'VIS': 'Visualize the problem space',
            'LAN': 'Apply symbolic rules and logical constraints',
            'MTL': 'Leverage similar past experiences',
            'ACC': 'Monitor for conflicts and adjust approach',
            'DMN': 'Take holistic, integrated perspective',
            'INS': 'Consider internal state and dynamics',
            'AUD': 'Use auditory/temporal patterns'
        }

        primary_module = top_modules[0][0]
        strategy = strategies.get(primary_module, 'Proceed methodically')

        # Add confidence qualifier
        if consciousness < 0.7:
            strategy = f"Uncertain, but try: {strategy}"
        elif consciousness >= self.consciousness_threshold:
            strategy = f"High confidence: {strategy}"

        return strategy

    def get_brain_stats(self) -> Dict:
        """Get statistics about the Klotski brain"""
        return {
            'total_parameters': self.brain.get_total_parameters(),
            'feature_dim': self.feature_dim,
            'num_actions': self.num_actions,
            'consciousness_threshold': self.consciousness_threshold,
            'graph_stats': self.brain_graph.get_graph_stats()
        }


# Fallback if Klotski not available
class MockKlotskiCTM:
    """
    Mock CTM that mimics the original simple CTM behavior
    Used when Klotski brain is not available
    """
    def __init__(self, **kwargs):
        print("[WARN] Using MockKlotskiCTM - Klotski brain not available")

    def reason(self, task: str, brain_state: Dict, **kwargs) -> CTMInsight:
        """Mock reasoning that returns simple insights"""
        return CTMInsight(
            task=task,
            reasoning_steps=10,
            consciousness_trajectory=[0.5] * 10,
            final_consciousness=0.5,
            converged=False,
            module_activations={'MOCK': 1.0},
            suggested_strategy="Proceed step by step",
            confidence=0.5,
            reasoning_trace=["[MOCK] Simple reasoning step"] * 10,
            dmn_energy=0.0,
            error_magnitude=0.0
        )

    def get_brain_stats(self) -> Dict:
        return {'mock': True}


# Export appropriate class
if KLOTSKI_AVAILABLE:
    CTM = KlotskiCTM
else:
    CTM = MockKlotskiCTM


if __name__ == "__main__":
    # Test KlotskiCTM
    print("="*70)
    print("Testing KlotskiCTM")
    print("="*70)

    if not KLOTSKI_AVAILABLE:
        print("Klotski brain not available, using mock")
        ctm = MockKlotskiCTM()
    else:
        ctm = KlotskiCTM(
            feature_dim=256,
            consciousness_threshold=0.85,
            max_reasoning_steps=30
        )

        print("\nBrain Stats:")
        stats = ctm.get_brain_stats()
        for key, value in stats.items():
            if key != 'graph_stats':
                print(f"  {key}: {value}")

    # Test reasoning
    print("\n" + "="*70)
    print("Testing Deep Reasoning")
    print("="*70)

    task = "Design distributed microservice architecture with auto-scaling and fault tolerance"
    brain_state = {
        'modality_activations': {
            'vision': 0.3,
            'audio': 0.2,
            'tool_trace': 0.8,
            'temporal_pattern': 0.6
        }
    }

    insight = ctm.reason(task, brain_state, max_steps=20)

    print("\n" + "="*70)
    print("CTM Insights")
    print("="*70)
    print(f"Task: {insight.task[:60]}...")
    print(f"Reasoning Steps: {insight.reasoning_steps}")
    print(f"Final Consciousness: {insight.final_consciousness:.3f}")
    print(f"Converged: {insight.converged}")
    print(f"Confidence: {insight.confidence:.3f}")
    print(f"Strategy: {insight.suggested_strategy}")

    print("\nModule Activations:")
    for mod, act in sorted(insight.module_activations.items(), key=lambda x: x[1], reverse=True):
        print(f"  {mod}: {act:.3f}")

    print("\nConsciousness Trajectory:")
    print(f"  {insight.consciousness_trajectory}")

    print("\n" + "="*70)
    print("KlotskiCTM Test Complete!")
    print("="*70)

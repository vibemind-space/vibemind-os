"""
Regime Detector - Classifies Operational Regime from Synchrony Vector

Detects distinct operational regimes based on synchrony patterns:

┌─────────────┬──────────────────────────────────────────┐
│ Regime      │ Synchrony Signature                      │
├─────────────┼──────────────────────────────────────────┤
│ EXPLOIT     │ A dominant, B/C suppressed, A-B locked   │
│ EXPLORE     │ B dominant, A-C anti-phase               │
│ REPAIR      │ C dominant, A-B-C converging             │
│ TRANSITION  │ No clear lock, high phase variance       │
│ DEADLOCK    │ All suppressed, phases drifting          │
└─────────────┴──────────────────────────────────────────┘

Each regime implies different tool-calling behavior:
    - EXPLOIT: Sequential, goal-directed actions
    - EXPLORE: Branching, alternative-seeking actions
    - REPAIR: Corrective, validation actions
    - TRANSITION: Waiting, evaluating state
    - DEADLOCK: Abort, reset, or escalate

The detector can use:
    1. Rule-based thresholds (fast, interpretable)
    2. Learned MLP classifier (flexible, trainable)
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.synchrony_encoder import SynchronyVector


class Regime(Enum):
    """Operational regimes"""
    EXPLOIT = "exploit"       # A dominant - goal-directed execution
    EXPLORE = "explore"       # B dominant - trying alternatives
    REPAIR = "repair"         # C dominant - correction/validation
    TRANSITION = "transition" # No clear dominant - state change
    DEADLOCK = "deadlock"     # All suppressed - stuck state


@dataclass
class RegimeClassification:
    """Result of regime classification"""
    regime: Regime
    confidence: float                       # [0, 1]
    regime_probabilities: Dict[str, float]  # All regime probs
    reasoning: str                          # Explanation
    beat_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    # Stability tracking
    consecutive_same_regime: int = 0
    is_stable: bool = False

    def to_dict(self) -> Dict:
        return {
            'regime': self.regime.value,
            'confidence': self.confidence,
            'probabilities': self.regime_probabilities,
            'reasoning': self.reasoning,
            'consecutive_same_regime': self.consecutive_same_regime,
            'is_stable': self.is_stable,
            'beat_index': self.beat_index
        }


class RegimeClassifierMLP(nn.Module):
    """
    Learned MLP classifier for regime detection

    Input: 9-D synchrony vector
    Output: 5-D regime probabilities
    """

    def __init__(self, hidden_dim: int = 32):
        super().__init__()

        self.classifier = nn.Sequential(
            nn.Linear(9, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, 5)  # 5 regimes
        )

    def forward(self, sync_vector: torch.Tensor) -> torch.Tensor:
        """
        Classify regime

        Args:
            sync_vector: [batch, 9] synchrony vector

        Returns:
            [batch, 5] regime logits
        """
        return self.classifier(sync_vector)

    def predict_proba(self, sync_vector: torch.Tensor) -> torch.Tensor:
        """Get regime probabilities"""
        logits = self.forward(sync_vector)
        return F.softmax(logits, dim=-1)


class RegimeDetector:
    """
    Detects operational regime from synchrony vectors

    Uses a combination of:
    1. Rule-based detection (interpretable, no training needed)
    2. Optional learned MLP (more flexible, needs training)

    The detector tracks regime history and detects:
    - Regime stability (same regime for N beats)
    - Regime transitions
    - Deadlock conditions
    """

    # Regime thresholds for rule-based detection
    DOMINANT_THRESHOLD = 0.6      # Amplitude to be considered dominant
    SUPPRESSED_THRESHOLD = 0.3    # Amplitude to be considered suppressed
    LOCKED_THRESHOLD = 0.7        # cos(Δ) for phase-locked
    ANTI_PHASE_THRESHOLD = -0.7   # cos(Δ) for anti-phase
    DEADLOCK_THRESHOLD = 0.25     # Max amplitude for deadlock

    # Regime index mapping for MLP
    REGIME_INDEX = {
        Regime.EXPLOIT: 0,
        Regime.EXPLORE: 1,
        Regime.REPAIR: 2,
        Regime.TRANSITION: 3,
        Regime.DEADLOCK: 4
    }
    INDEX_REGIME = {v: k for k, v in REGIME_INDEX.items()}

    def __init__(
        self,
        use_learned_classifier: bool = False,
        stability_window: int = 3,
        device: str = 'cpu'
    ):
        """
        Initialize detector

        Args:
            use_learned_classifier: Use MLP instead of rules
            stability_window: Beats needed for stable regime
            device: Torch device
        """
        self.use_learned_classifier = use_learned_classifier
        self.stability_window = stability_window
        self.device = device

        # Learned classifier (optional)
        if use_learned_classifier:
            self.classifier = RegimeClassifierMLP().to(device)
            self.classifier.eval()
        else:
            self.classifier = None

        # History tracking
        self.history: List[RegimeClassification] = []
        self.regime_sequence: List[Regime] = []

        # Current regime tracking
        self.current_regime: Regime = Regime.TRANSITION
        self.consecutive_count: int = 0

    def detect(self, sync: SynchronyVector) -> RegimeClassification:
        """
        Detect regime from synchrony vector

        Args:
            sync: 9-D synchrony vector

        Returns:
            RegimeClassification with regime and confidence
        """
        if self.use_learned_classifier and self.classifier:
            result = self._detect_learned(sync)
        else:
            result = self._detect_rules(sync)

        # Update regime tracking
        if result.regime == self.current_regime:
            self.consecutive_count += 1
        else:
            self.current_regime = result.regime
            self.consecutive_count = 1

        result.consecutive_same_regime = self.consecutive_count
        result.is_stable = self.consecutive_count >= self.stability_window

        # Add to history
        self.history.append(result)
        self.regime_sequence.append(result.regime)

        # Trim history
        if len(self.history) > 100:
            self.history = self.history[-100:]
            self.regime_sequence = self.regime_sequence[-100:]

        return result

    def _detect_rules(self, sync: SynchronyVector) -> RegimeClassification:
        """Rule-based regime detection"""
        amp_A, amp_B, amp_C = sync.amp_A, sync.amp_B, sync.amp_C
        cos_AB, cos_AC, cos_BC = sync.cos_AB, sync.cos_AC, sync.cos_BC

        # Initialize probabilities (heuristic scores)
        probs = {r.value: 0.0 for r in Regime}
        reasoning = []

        # Check for DEADLOCK first (all suppressed)
        if max(amp_A, amp_B, amp_C) < self.DEADLOCK_THRESHOLD:
            probs['deadlock'] = 0.9
            reasoning.append("All amplitudes suppressed (<0.25)")
        else:
            # Check for EXPLOIT (A dominant)
            if amp_A >= self.DOMINANT_THRESHOLD:
                if amp_B < self.SUPPRESSED_THRESHOLD and amp_C < self.SUPPRESSED_THRESHOLD:
                    probs['exploit'] = 0.85
                    reasoning.append("A dominant, B/C suppressed")
                elif cos_AB > self.LOCKED_THRESHOLD:
                    probs['exploit'] = 0.75
                    reasoning.append("A dominant, A-B locked")
                else:
                    probs['exploit'] = 0.6
                    reasoning.append("A dominant")

            # Check for EXPLORE (B dominant)
            if amp_B >= self.DOMINANT_THRESHOLD:
                if cos_AC < self.ANTI_PHASE_THRESHOLD:
                    probs['explore'] = 0.85
                    reasoning.append("B dominant, A-C anti-phase")
                elif amp_A < self.SUPPRESSED_THRESHOLD:
                    probs['explore'] = 0.75
                    reasoning.append("B dominant, A suppressed")
                else:
                    probs['explore'] = 0.6
                    reasoning.append("B dominant")

            # Check for REPAIR (C dominant)
            if amp_C >= self.DOMINANT_THRESHOLD:
                # Check for convergence (all pairs approaching in-phase)
                converging = (cos_AB > 0 and cos_AC > 0 and cos_BC > 0)
                if converging:
                    probs['repair'] = 0.85
                    reasoning.append("C dominant, A-B-C converging")
                else:
                    probs['repair'] = 0.7
                    reasoning.append("C dominant")

            # Check for TRANSITION (no clear dominant)
            total_dominant = sum([
                amp_A >= self.DOMINANT_THRESHOLD,
                amp_B >= self.DOMINANT_THRESHOLD,
                amp_C >= self.DOMINANT_THRESHOLD
            ])

            if total_dominant == 0:
                # No dominant but not deadlock (at least one above threshold)
                probs['transition'] = 0.7
                reasoning.append("No clear dominant channel")
            elif total_dominant >= 2:
                # Multiple dominant - competition
                probs['transition'] = 0.5
                reasoning.append("Multiple channels competing")

        # Normalize probabilities
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}
        else:
            probs['transition'] = 1.0

        # Find best regime
        best_regime = max(probs, key=probs.get)
        confidence = probs[best_regime]

        return RegimeClassification(
            regime=Regime(best_regime),
            confidence=confidence,
            regime_probabilities=probs,
            reasoning=" | ".join(reasoning) if reasoning else "Default transition",
            beat_index=sync.beat_index
        )

    def _detect_learned(self, sync: SynchronyVector) -> RegimeClassification:
        """Learned MLP regime detection"""
        # Convert to tensor
        sync_tensor = torch.tensor(
            sync.vector,
            dtype=torch.float32
        ).unsqueeze(0).to(self.device)

        # Get probabilities
        with torch.no_grad():
            probs_tensor = self.classifier.predict_proba(sync_tensor)
            probs_np = probs_tensor.squeeze(0).cpu().numpy()

        # Build probability dict
        probs = {r.value: float(probs_np[i]) for r, i in self.REGIME_INDEX.items()}

        # Find best
        best_idx = int(np.argmax(probs_np))
        best_regime = self.INDEX_REGIME[best_idx]
        confidence = float(probs_np[best_idx])

        return RegimeClassification(
            regime=best_regime,
            confidence=confidence,
            regime_probabilities=probs,
            reasoning=f"MLP classification (confidence={confidence:.3f})",
            beat_index=sync.beat_index
        )

    def get_regime_durations(self) -> Dict[str, int]:
        """Get total beats spent in each regime"""
        durations = {r.value: 0 for r in Regime}
        for r in self.regime_sequence:
            durations[r.value] += 1
        return durations

    def get_transition_count(self) -> int:
        """Count number of regime transitions"""
        if len(self.regime_sequence) < 2:
            return 0
        transitions = sum(
            1 for i in range(1, len(self.regime_sequence))
            if self.regime_sequence[i] != self.regime_sequence[i-1]
        )
        return transitions

    def get_transition_matrix(self) -> np.ndarray:
        """
        Get regime transition matrix

        M[i,j] = count of transitions from regime i to regime j
        """
        n_regimes = len(Regime)
        matrix = np.zeros((n_regimes, n_regimes), dtype=int)

        for i in range(1, len(self.regime_sequence)):
            from_idx = self.REGIME_INDEX[self.regime_sequence[i-1]]
            to_idx = self.REGIME_INDEX[self.regime_sequence[i]]
            matrix[from_idx, to_idx] += 1

        return matrix

    def is_stuck(self, threshold: int = 10) -> bool:
        """Check if stuck in DEADLOCK or TRANSITION for too long"""
        if self.current_regime in [Regime.DEADLOCK, Regime.TRANSITION]:
            return self.consecutive_count >= threshold
        return False

    def suggest_action(self, current: RegimeClassification) -> str:
        """Suggest action based on regime"""
        suggestions = {
            Regime.EXPLOIT: "Execute next goal-directed action",
            Regime.EXPLORE: "Try alternative approach or gather more info",
            Regime.REPAIR: "Validate or correct previous action",
            Regime.TRANSITION: "Wait and evaluate state before acting",
            Regime.DEADLOCK: "Reset or escalate - system may be stuck"
        }
        return suggestions.get(current.regime, "Continue observing")

    def get_statistics(self) -> Dict:
        """Get detector statistics"""
        stats = {
            'use_learned_classifier': self.use_learned_classifier,
            'stability_window': self.stability_window,
            'current_regime': self.current_regime.value,
            'consecutive_count': self.consecutive_count,
            'is_stable': self.consecutive_count >= self.stability_window,
            'history_length': len(self.history)
        }

        if self.history:
            stats['regime_durations'] = self.get_regime_durations()
            stats['transition_count'] = self.get_transition_count()
            stats['is_stuck'] = self.is_stuck()

        return stats

    def reset(self):
        """Reset detector state"""
        self.history.clear()
        self.regime_sequence.clear()
        self.current_regime = Regime.TRANSITION
        self.consecutive_count = 0


if __name__ == "__main__":
    print("=" * 70)
    print("REGIME DETECTOR - Classify Operational Regime from Synchrony")
    print("=" * 70)
    print()
    print("Regimes:")
    print("  EXPLOIT    - A dominant, goal-directed execution")
    print("  EXPLORE    - B dominant, trying alternatives")
    print("  REPAIR     - C dominant, correction/validation")
    print("  TRANSITION - No clear dominant, evaluating")
    print("  DEADLOCK   - All suppressed, stuck")
    print()

    # Create detector
    detector = RegimeDetector(use_learned_classifier=False)

    # Create test synchrony vectors
    from core.action_potential_oscillator import ActionPotentialOscillator
    from core.synchrony_encoder import SynchronyEncoder

    osc = ActionPotentialOscillator(use_neural_coupling=False)
    encoder = SynchronyEncoder()

    print("Testing regime detection across scenarios:")
    print("-" * 70)

    scenarios = [
        ("Exploit mode", {'advance': 0.9, 'explore': 0.1, 'correct': 0.05}),
        ("Exploit mode", {'advance': 0.9, 'explore': 0.1, 'correct': 0.05}),
        ("Exploit mode", {'advance': 0.9, 'explore': 0.1, 'correct': 0.05}),
        ("Transition", {'advance': 0.4, 'explore': 0.4, 'correct': 0.2}),
        ("Explore mode", {'advance': 0.1, 'explore': 0.9, 'correct': 0.1}),
        ("Explore mode", {'advance': 0.1, 'explore': 0.9, 'correct': 0.1}),
        ("Repair mode", {'advance': 0.1, 'explore': 0.1, 'correct': 0.9}),
        ("Repair mode", {'advance': 0.1, 'explore': 0.1, 'correct': 0.9}),
        ("Deadlock", {'advance': 0.05, 'explore': 0.05, 'correct': 0.05}),
        ("Recovery", {'advance': 0.5, 'explore': 0.3, 'correct': 0.2}),
    ]

    for name, scenario in scenarios:
        # Step oscillator
        osc_state = osc.step(external_input=scenario)

        # Encode synchrony
        sync = encoder.encode(osc_state)

        # Detect regime
        result = detector.detect(sync)

        print(f"\n{name}:")
        print(f"  Input: A={scenario['advance']:.2f}, B={scenario['explore']:.2f}, C={scenario['correct']:.2f}")
        print(f"  Detected: {result.regime.value} (conf={result.confidence:.2f})")
        print(f"  Stable: {result.is_stable} (consecutive={result.consecutive_same_regime})")
        print(f"  Reasoning: {result.reasoning}")
        print(f"  Suggestion: {detector.suggest_action(result)}")

    print()
    print("-" * 70)
    print("Statistics:", detector.get_statistics())
    print()
    print("Regime durations:", detector.get_regime_durations())
    print("Transition count:", detector.get_transition_count())
    print()
    print("Transition matrix:")
    print(detector.get_transition_matrix())
    print()
    print("=" * 70)

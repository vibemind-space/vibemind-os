"""
Allis Strategic Rules for NeuroSymbolic Control

Implements four strategic rules from Allis (Connect-4, 1988) adapted for
cognitive puzzle solving:

1. Follow-up: Maintain cognitive context (continue using same module)
2. Baseinverse: Prevent catastrophic failures (don't undo progress)
3. Claimeven: Force value assessment before major transitions
4. Zugzwang: Control turn-taking (force opponent to move first)

These rules act as symbolic constraints on neural network actions.

Reference: Victor Allis, "A Knowledge-based Approach of Connect-Four" (1988)
"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from abc import ABC, abstractmethod
import numpy as np


@dataclass
class Action:
    """Represents a puzzle action (moving a piece)"""
    piece_id: str           # Which piece to move
    from_pos: Tuple[int, int]  # (x, y) current position
    to_pos: Tuple[int, int]    # (x, y) target position
    direction: str          # "up", "down", "left", "right"
    module_id: str          # Brain module this piece represents


@dataclass
class Context:
    """Cognitive context for rule evaluation"""
    last_action: Optional[Action] = None
    last_module: Optional[str] = None
    recent_actions: List[Action] = None  # Last N actions
    value_since_last_assessment: int = 0  # Moves since value check
    consciousness_score: float = 0.0      # Current consciousness metric

    def __post_init__(self):
        if self.recent_actions is None:
            self.recent_actions = []


class AllisRule(ABC):
    """Base class for Allis strategic rules"""

    def __init__(self, name: str, weight: float = 1.0):
        """
        Initialize rule

        Args:
            name: Rule name
            weight: Rule importance weight (0.0 to 1.0)
        """
        self.name = name
        self.weight = weight

    @abstractmethod
    def evaluate(self, action: Action, context: Context, state_info: Dict) -> float:
        """
        Evaluate rule violation for an action

        Args:
            action: Proposed action
            context: Current cognitive context
            state_info: Additional state information

        Returns:
            Violation score (0.0 = no violation, 1.0 = max violation)
        """
        pass

    def get_mask_value(self, action: Action, context: Context, state_info: Dict) -> float:
        """
        Get mask value for this rule (0.0 = forbidden, 1.0 = allowed)

        Returns:
            Mask value in [0, 1]
        """
        violation = self.evaluate(action, context, state_info)
        # Convert violation to mask: low violation = high mask
        return max(0.0, 1.0 - violation * self.weight)


class FollowUpRule(AllisRule):
    """
    Follow-up Rule: Maintain cognitive context

    Prefer actions that use the same brain module as the previous action.
    This models cognitive continuity and attention maintenance.

    Violation: Switching to a different module without good reason.
    """

    def __init__(self, weight: float = 0.8):
        super().__init__("Follow-up", weight)
        self.context_window = 3  # Consider last 3 actions

    def evaluate(self, action: Action, context: Context, state_info: Dict) -> float:
        """
        Evaluate follow-up violation

        Returns:
            0.0 if action continues context, 1.0 if it breaks context
        """
        if context.last_module is None:
            return 0.0  # No previous context

        # Check if action uses same module as recent actions
        recent_modules = [a.module_id for a in context.recent_actions[-self.context_window:]]

        if action.module_id in recent_modules:
            # Good: continuing context
            return 0.0

        # Calculate violation based on how different the module is
        # Check if modules are connected in brain graph
        # (This would require brain_graph access - simplified here)

        # For now: simple binary - same module = 0.0, different = 1.0
        if action.module_id == context.last_module:
            return 0.0
        else:
            return 1.0


class BaseinverseRule(AllisRule):
    """
    Baseinverse Rule: Prevent catastrophic failures

    Don't undo recent progress by immediately reversing an action.
    This models avoiding "thrashing" and cognitive dead-ends.

    Violation: Immediately undoing a previous move.
    """

    def __init__(self, weight: float = 1.0):
        super().__init__("Baseinverse", weight)
        self.lookback = 2  # Check last 2 moves

    def evaluate(self, action: Action, context: Context, state_info: Dict) -> float:
        """
        Evaluate baseinverse violation

        Returns:
            1.0 if action directly undoes recent move, 0.0 otherwise
        """
        if not context.recent_actions:
            return 0.0

        # Check if this action reverses a recent action
        for recent_action in context.recent_actions[-self.lookback:]:
            if recent_action.piece_id == action.piece_id:
                # Same piece moved

                # Check if new position equals a recent previous position
                if action.to_pos == recent_action.from_pos:
                    # Moving back to where we came from - VIOLATION
                    return 1.0

                # Check if direction is opposite
                opposite_directions = {
                    "up": "down",
                    "down": "up",
                    "left": "right",
                    "right": "left"
                }

                if action.direction == opposite_directions.get(recent_action.direction):
                    # Opposite direction - likely undoing
                    return 0.8  # High but not max violation

        return 0.0


class ClaimevenRule(AllisRule):
    """
    Claimeven Rule: Force value assessment before major transitions

    Before switching cognitive context significantly, assess current value/progress.
    This models deliberate decision-making and prevents impulsive context switches.

    Violation: Switching modules too frequently without value assessment.
    """

    def __init__(self, weight: float = 0.6, assessment_threshold: int = 3):
        super().__init__("Claimeven", weight)
        self.assessment_threshold = assessment_threshold

    def evaluate(self, action: Action, context: Context, state_info: Dict) -> float:
        """
        Evaluate claimeven violation

        Returns:
            Violation based on moves since last value assessment
        """
        if context.last_module is None:
            return 0.0

        # If changing modules AND haven't assessed value recently
        if action.module_id != context.last_module:
            if context.value_since_last_assessment >= self.assessment_threshold:
                # VIOLATION: changing context without recent assessment
                # Violation increases with time since last assessment
                excess = context.value_since_last_assessment - self.assessment_threshold
                return min(1.0, 0.5 + (excess * 0.1))

        return 0.0


class ZugzwangRule(AllisRule):
    """
    Zugzwang Rule: Control turn-taking

    In chess/Connect-4, zugzwang is when being forced to move hurts your position.
    Here: control which module "moves" (gets attention) next.

    Prefer actions that improve position, not just respond to constraints.
    This models proactive vs reactive cognition.

    Violation: Making forced moves that don't improve consciousness metric.
    """

    def __init__(self, weight: float = 0.5):
        super().__init__("Zugzwang", weight)

    def evaluate(self, action: Action, context: Context, state_info: Dict) -> float:
        """
        Evaluate zugzwang violation

        Returns:
            Violation if action doesn't improve value
        """
        # Get current and predicted consciousness scores
        current_consciousness = context.consciousness_score
        predicted_consciousness = state_info.get('predicted_consciousness', current_consciousness)

        # If this is a "forced" move (only option) that decreases value
        num_valid_moves = state_info.get('num_valid_moves', 1)

        if num_valid_moves == 1:
            # Forced move
            if predicted_consciousness < current_consciousness:
                # Decreases value - VIOLATION
                decrease = current_consciousness - predicted_consciousness
                return min(1.0, decrease * 2.0)  # Scale violation

        return 0.0


class AllisRuleEngine:
    """
    Rule engine that combines all Allis rules

    Evaluates proposed actions against all rules and generates:
    - Violation scores
    - Mask values (for differentiable masking)
    - Rule explanations
    """

    def __init__(self, rules: Optional[List[AllisRule]] = None):
        """
        Initialize rule engine

        Args:
            rules: List of AllisRule instances (uses defaults if None)
        """
        if rules is None:
            self.rules = [
                FollowUpRule(weight=0.8),
                BaseinverseRule(weight=1.0),
                ClaimevenRule(weight=0.6),
                ZugzwangRule(weight=0.5),
            ]
        else:
            self.rules = rules

    def evaluate_action(self, action: Action, context: Context,
                       state_info: Dict) -> Dict[str, float]:
        """
        Evaluate action against all rules

        Returns:
            Dict mapping rule names to violation scores
        """
        violations = {}
        for rule in self.rules:
            violations[rule.name] = rule.evaluate(action, context, state_info)
        return violations

    def get_mask(self, action: Action, context: Context,
                 state_info: Dict) -> float:
        """
        Get combined mask value for action (0.0 = forbidden, 1.0 = allowed)

        Combines all rule masks using product (all rules must pass)

        Returns:
            Mask value in [0, 1]
        """
        mask = 1.0
        for rule in self.rules:
            rule_mask = rule.get_mask_value(action, context, state_info)
            mask *= rule_mask  # Product: all rules must allow

        return mask

    def get_action_masks(self, actions: List[Action], context: Context,
                        state_infos: List[Dict]) -> np.ndarray:
        """
        Get mask values for multiple actions

        Args:
            actions: List of proposed actions
            context: Current context
            state_infos: List of state info dicts (one per action)

        Returns:
            NumPy array of mask values [0, 1]
        """
        masks = []
        for action, state_info in zip(actions, state_infos):
            mask = self.get_mask(action, context, state_info)
            masks.append(mask)

        return np.array(masks)

    def explain_violations(self, action: Action, context: Context,
                          state_info: Dict) -> str:
        """
        Get human-readable explanation of rule violations

        Returns:
            String explaining which rules are violated and why
        """
        violations = self.evaluate_action(action, context, state_info)

        explanations = []
        for rule_name, violation in violations.items():
            if violation > 0.1:  # Threshold for reporting
                explanations.append(
                    f"{rule_name}: {violation:.2f} violation"
                )

        if not explanations:
            return "No significant rule violations"

        return "; ".join(explanations)

    def __repr__(self):
        return f"AllisRuleEngine(rules={len(self.rules)})"


if __name__ == "__main__":
    # Test the rule engine
    print("Testing Allis Rule Engine...")

    engine = AllisRuleEngine()
    print(f"Engine: {engine}")
    print(f"Rules: {[r.name for r in engine.rules]}")

    # Create test actions
    action1 = Action(
        piece_id='D',
        from_pos=(1, 2),
        to_pos=(1, 3),
        direction='down',
        module_id='DLPFC'
    )

    action2 = Action(
        piece_id='D',
        from_pos=(1, 3),
        to_pos=(1, 2),
        direction='up',
        module_id='DLPFC'
    )

    action3 = Action(
        piece_id='V',
        from_pos=(0, 0),
        to_pos=(0, 1),
        direction='down',
        module_id='VIS'
    )

    # Create context
    context = Context(
        last_action=action1,
        last_module='DLPFC',
        recent_actions=[action1],
        value_since_last_assessment=2,
        consciousness_score=0.5
    )

    state_info = {
        'predicted_consciousness': 0.55,
        'num_valid_moves': 3
    }

    print("\n" + "="*60)
    print("Test Action 1: Continue with DLPFC (follow-up)")
    print("="*60)
    violations1 = engine.evaluate_action(action1, context, state_info)
    for rule, violation in violations1.items():
        print(f"  {rule}: {violation:.3f}")
    mask1 = engine.get_mask(action1, context, state_info)
    print(f"  Combined Mask: {mask1:.3f}")
    print(f"  Explanation: {engine.explain_violations(action1, context, state_info)}")

    print("\n" + "="*60)
    print("Test Action 2: Undo previous move (baseinverse violation)")
    print("="*60)
    violations2 = engine.evaluate_action(action2, context, state_info)
    for rule, violation in violations2.items():
        print(f"  {rule}: {violation:.3f}")
    mask2 = engine.get_mask(action2, context, state_info)
    print(f"  Combined Mask: {mask2:.3f}")
    print(f"  Explanation: {engine.explain_violations(action2, context, state_info)}")

    print("\n" + "="*60)
    print("Test Action 3: Switch to VIS (follow-up violation)")
    print("="*60)
    violations3 = engine.evaluate_action(action3, context, state_info)
    for rule, violation in violations3.items():
        print(f"  {rule}: {violation:.3f}")
    mask3 = engine.get_mask(action3, context, state_info)
    print(f"  Combined Mask: {mask3:.3f}")
    print(f"  Explanation: {engine.explain_violations(action3, context, state_info)}")

    print("\n" + "="*60)
    print("Batch Mask Generation")
    print("="*60)
    actions = [action1, action2, action3]
    state_infos = [state_info, state_info, state_info]
    masks = engine.get_action_masks(actions, context, state_infos)
    print(f"  Masks: {masks}")
    print(f"  Best action: {['Action 1', 'Action 2', 'Action 3'][np.argmax(masks)]}")

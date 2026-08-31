"""
Regime Inference - Infer Operational Regimes from Tool Patterns

Maps tool call sequences to regimes:
- EXPLOIT: Sequential goal-directed actions (low errors, consistent tools)
- EXPLORE: Trying alternatives (tool variety, search patterns)
- REPAIR: Error correction loops (retries, same tool after error)
- TRANSITION: Regime changes
- DEADLOCK: Stuck state (high errors, no progress)
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter

# Import Regime from temporal_dataset
from .temporal_dataset import Regime


@dataclass
class ToolCallInfo:
    """Information about a single tool call"""
    tool_name: str
    success: bool
    is_search: bool = False
    is_write: bool = False
    is_read: bool = False
    error_message: Optional[str] = None


@dataclass
class SegmentFeatures:
    """Features extracted from a segment of tool calls"""
    # Tool counts
    total_calls: int = 0
    unique_tools: int = 0
    tool_repetition_max: int = 0  # Max times same tool repeated consecutively

    # Error metrics
    error_count: int = 0
    success_rate: float = 1.0

    # Pattern indicators
    has_search_pattern: bool = False  # search/list operations
    has_retry_pattern: bool = False   # same tool after error
    has_variety: bool = False         # >3 different tools
    is_sequential: bool = True        # consistent tool progression

    # Context switches
    context_switches: int = 0

    # Tool type distribution
    tool_type_counts: Dict[str, int] = field(default_factory=dict)


# Tool classification patterns
SEARCH_TOOLS = {'grep', 'find', 'glob', 'search', 'list', 'ls', 'dir'}
WRITE_TOOLS = {'write', 'edit', 'create', 'mkdir', 'touch', 'mv', 'cp'}
READ_TOOLS = {'read', 'cat', 'head', 'tail', 'less', 'more'}
SHELL_TOOLS = {'bash', 'shell', 'cmd', 'exec', 'run'}

# Tool name patterns for classification
TOOL_PATTERNS = {
    'search': re.compile(r'(search|find|grep|glob|list|ls|dir)', re.I),
    'write': re.compile(r'(write|edit|create|mkdir|touch|mv|cp|save)', re.I),
    'read': re.compile(r'(read|cat|head|tail|view|show|get)', re.I),
    'docker': re.compile(r'(docker|container|image|volume)', re.I),
    'git': re.compile(r'(git|github|commit|push|pull|branch)', re.I),
    'file': re.compile(r'(file|path|directory|folder)', re.I),
}


def classify_tool(tool_name: str) -> Dict[str, bool]:
    """Classify a tool by its type"""
    tool_lower = tool_name.lower()
    return {
        'is_search': bool(TOOL_PATTERNS['search'].search(tool_lower)),
        'is_write': bool(TOOL_PATTERNS['write'].search(tool_lower)),
        'is_read': bool(TOOL_PATTERNS['read'].search(tool_lower)),
        'is_docker': bool(TOOL_PATTERNS['docker'].search(tool_lower)),
        'is_git': bool(TOOL_PATTERNS['git'].search(tool_lower)),
    }


def extract_segment_features(
    tool_calls: List[ToolCallInfo],
    window_start: int = 0,
    window_end: Optional[int] = None
) -> SegmentFeatures:
    """
    Extract features from a segment of tool calls

    Args:
        tool_calls: List of tool call info
        window_start: Start index
        window_end: End index (None = end of list)

    Returns:
        SegmentFeatures for this segment
    """
    if window_end is None:
        window_end = len(tool_calls)

    segment = tool_calls[window_start:window_end]

    if not segment:
        return SegmentFeatures()

    features = SegmentFeatures()
    features.total_calls = len(segment)

    # Count tools
    tool_names = [tc.tool_name for tc in segment]
    tool_counter = Counter(tool_names)
    features.unique_tools = len(tool_counter)
    features.has_variety = features.unique_tools > 3

    # Tool type distribution
    for tool_name in tool_counter:
        classification = classify_tool(tool_name)
        for key, val in classification.items():
            if val:
                features.tool_type_counts[key] = features.tool_type_counts.get(key, 0) + tool_counter[tool_name]

    # Search pattern
    features.has_search_pattern = any(tc.is_search for tc in segment)

    # Error metrics
    errors = [tc for tc in segment if not tc.success]
    features.error_count = len(errors)
    features.success_rate = 1.0 - (features.error_count / features.total_calls) if features.total_calls > 0 else 1.0

    # Tool repetition (consecutive same tool)
    max_rep = 1
    current_rep = 1
    for i in range(1, len(segment)):
        if segment[i].tool_name == segment[i-1].tool_name:
            current_rep += 1
            max_rep = max(max_rep, current_rep)
        else:
            current_rep = 1
    features.tool_repetition_max = max_rep

    # Retry pattern: same tool used after an error
    features.has_retry_pattern = False
    for i in range(1, len(segment)):
        if not segment[i-1].success and segment[i].tool_name == segment[i-1].tool_name:
            features.has_retry_pattern = True
            break

    # Context switches (different tool categories)
    prev_category = None
    for tc in segment:
        classification = classify_tool(tc.tool_name)
        # Get primary category
        category = next((k for k, v in classification.items() if v), 'other')
        if prev_category is not None and category != prev_category:
            features.context_switches += 1
        prev_category = category

    # Sequential check (tools follow logical order)
    features.is_sequential = features.context_switches < 2 and features.tool_repetition_max < 3

    return features


class RegimeInference:
    """
    Infer operational regimes from tool call patterns

    Uses rule-based classification:
    - EXPLOIT: Sequential, low errors, consistent tools
    - EXPLORE: Tool variety, search patterns, context switches
    - REPAIR: Retries, errors, same tool repeated
    - DEADLOCK: High errors, no progress
    - TRANSITION: Between regimes
    """

    def __init__(
        self,
        exploit_error_threshold: float = 0.1,
        explore_variety_threshold: int = 3,
        repair_retry_threshold: int = 2,
        deadlock_error_threshold: int = 3,
        window_size: int = 5
    ):
        """
        Initialize regime inference

        Args:
            exploit_error_threshold: Max error rate for EXPLOIT
            explore_variety_threshold: Min unique tools for EXPLORE
            repair_retry_threshold: Min repetitions for REPAIR
            deadlock_error_threshold: Min errors for DEADLOCK
            window_size: Window size for regime detection
        """
        self.exploit_error_threshold = exploit_error_threshold
        self.explore_variety_threshold = explore_variety_threshold
        self.repair_retry_threshold = repair_retry_threshold
        self.deadlock_error_threshold = deadlock_error_threshold
        self.window_size = window_size

    def infer_regime_for_segment(self, features: SegmentFeatures) -> Tuple[Regime, float]:
        """
        Infer regime for a single segment

        Args:
            features: Extracted segment features

        Returns:
            (Regime, confidence) tuple
        """
        scores = {
            Regime.EXPLOIT: 0.0,
            Regime.EXPLORE: 0.0,
            Regime.REPAIR: 0.0,
            Regime.DEADLOCK: 0.0,
            Regime.TRANSITION: 0.0
        }

        # EXPLOIT scoring
        if features.success_rate >= (1.0 - self.exploit_error_threshold):
            scores[Regime.EXPLOIT] += 0.4
        if features.is_sequential:
            scores[Regime.EXPLOIT] += 0.3
        if features.tool_repetition_max < 2:
            scores[Regime.EXPLOIT] += 0.2
        if not features.has_search_pattern:
            scores[Regime.EXPLOIT] += 0.1
        # Penalty: Search patterns indicate exploration, not exploitation
        if features.has_search_pattern:
            scores[Regime.EXPLOIT] -= 0.3

        # EXPLORE scoring
        if features.has_variety:
            scores[Regime.EXPLORE] += 0.4
        if features.has_search_pattern:
            scores[Regime.EXPLORE] += 0.4  # Increased: search = exploration
        if features.context_switches > 2:
            scores[Regime.EXPLORE] += 0.2
        if features.success_rate > 0.5:
            scores[Regime.EXPLORE] += 0.1
        # Boost for search-heavy patterns
        search_count = features.tool_type_counts.get('is_search', 0)
        if search_count >= features.total_calls * 0.5:  # >50% search tools
            scores[Regime.EXPLORE] += 0.2

        # REPAIR scoring
        if features.has_retry_pattern:
            scores[Regime.REPAIR] += 0.4
        if features.tool_repetition_max >= self.repair_retry_threshold:
            scores[Regime.REPAIR] += 0.3
        if features.error_count > 0:
            scores[Regime.REPAIR] += 0.2
        if features.success_rate < 0.8 and features.success_rate > 0.2:
            scores[Regime.REPAIR] += 0.1
        # Penalty: Zero success = not repair (it's deadlock)
        if features.success_rate == 0:
            scores[Regime.REPAIR] -= 0.4

        # DEADLOCK scoring
        if features.error_count >= self.deadlock_error_threshold:
            scores[Regime.DEADLOCK] += 0.5
        if features.success_rate < 0.2:
            scores[Regime.DEADLOCK] += 0.3
        if features.total_calls >= 3 and features.unique_tools < 2:
            scores[Regime.DEADLOCK] += 0.2
        # Strong signal: complete failure (0% success rate)
        if features.success_rate == 0 and features.error_count >= 3:
            scores[Regime.DEADLOCK] += 0.3

        # Find best regime
        best_regime = max(scores, key=scores.get)
        best_score = scores[best_regime]

        # Check for TRANSITION
        sorted_scores = sorted(scores.values(), reverse=True)
        if sorted_scores[0] - sorted_scores[1] < 0.2:
            # Close scores indicate transition
            scores[Regime.TRANSITION] = (sorted_scores[0] + sorted_scores[1]) / 2
            if scores[Regime.TRANSITION] > best_score * 0.8:
                best_regime = Regime.TRANSITION
                best_score = scores[Regime.TRANSITION]

        # Normalize confidence
        confidence = min(best_score, 1.0)

        return best_regime, confidence

    def infer_regime_sequence(
        self,
        tool_calls: List[ToolCallInfo]
    ) -> List[Tuple[Regime, float]]:
        """
        Infer regime sequence for a list of tool calls

        Args:
            tool_calls: List of tool call info

        Returns:
            List of (Regime, confidence) for each tool call
        """
        if not tool_calls:
            return []

        regimes = []

        for i in range(len(tool_calls)):
            # Use sliding window centered on current position
            window_start = max(0, i - self.window_size // 2)
            window_end = min(len(tool_calls), i + self.window_size // 2 + 1)

            features = extract_segment_features(tool_calls, window_start, window_end)
            regime, confidence = self.infer_regime_for_segment(features)
            regimes.append((regime, confidence))

        return regimes

    def detect_transitions(
        self,
        regime_sequence: List[Tuple[Regime, float]]
    ) -> List[int]:
        """
        Detect transition points in regime sequence

        Args:
            regime_sequence: List of (Regime, confidence)

        Returns:
            List of indices where transitions occur
        """
        transitions = []
        prev_regime = None

        for i, (regime, _) in enumerate(regime_sequence):
            if prev_regime is not None and regime != prev_regime:
                transitions.append(i)
            prev_regime = regime

        return transitions

    def smooth_regime_sequence(
        self,
        regime_sequence: List[Tuple[Regime, float]],
        min_segment_length: int = 2
    ) -> List[Tuple[Regime, float]]:
        """
        Smooth regime sequence to remove noise

        Args:
            regime_sequence: Raw regime sequence
            min_segment_length: Minimum length for a regime segment

        Returns:
            Smoothed regime sequence
        """
        if len(regime_sequence) < 3:
            return regime_sequence

        smoothed = list(regime_sequence)

        # Remove single-step regime changes
        for i in range(1, len(smoothed) - 1):
            prev_regime = smoothed[i-1][0]
            curr_regime = smoothed[i][0]
            next_regime = smoothed[i+1][0]

            if prev_regime == next_regime and curr_regime != prev_regime:
                # Single outlier - smooth it out
                smoothed[i] = (prev_regime, (smoothed[i-1][1] + smoothed[i+1][1]) / 2)

        return smoothed


def infer_session_regimes(
    tool_names: List[str],
    success_flags: List[bool],
    error_messages: Optional[List[str]] = None
) -> List[Tuple[Regime, float]]:
    """
    Convenience function to infer regimes from session data

    Args:
        tool_names: List of tool names in order
        success_flags: List of success/failure flags
        error_messages: Optional list of error messages

    Returns:
        List of (Regime, confidence) for each step
    """
    # Build tool call info
    tool_calls = []
    for i, (name, success) in enumerate(zip(tool_names, success_flags)):
        classification = classify_tool(name)
        tc = ToolCallInfo(
            tool_name=name,
            success=success,
            is_search=classification.get('is_search', False),
            is_write=classification.get('is_write', False),
            is_read=classification.get('is_read', False),
            error_message=error_messages[i] if error_messages and i < len(error_messages) else None
        )
        tool_calls.append(tc)

    # Infer regimes
    inference = RegimeInference()
    regime_sequence = inference.infer_regime_sequence(tool_calls)

    # Smooth
    smoothed = inference.smooth_regime_sequence(regime_sequence)

    return smoothed


if __name__ == "__main__":
    print("=" * 70)
    print("REGIME INFERENCE - Testing")
    print("=" * 70)
    print()

    # Test 1: EXPLOIT pattern (sequential, no errors)
    print("[1] Testing EXPLOIT pattern...")
    exploit_tools = ['read_file', 'edit_file', 'write_file', 'bash_run']
    exploit_success = [True, True, True, True]
    regimes = infer_session_regimes(exploit_tools, exploit_success)
    print(f"    Tools: {exploit_tools}")
    print(f"    Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
    assert all(r == Regime.EXPLOIT for r, _ in regimes), "Expected all EXPLOIT"
    print("    [OK] EXPLOIT detected")
    print()

    # Test 2: EXPLORE pattern (variety, search)
    print("[2] Testing EXPLORE pattern...")
    explore_tools = ['search_files', 'grep_code', 'list_dir', 'read_file', 'glob_files', 'bash_find']
    explore_success = [True, True, True, True, True, True]
    regimes = infer_session_regimes(explore_tools, explore_success)
    print(f"    Tools: {explore_tools}")
    print(f"    Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
    assert any(r == Regime.EXPLORE for r, _ in regimes), "Expected some EXPLORE"
    print("    [OK] EXPLORE detected")
    print()

    # Test 3: REPAIR pattern (retries, errors)
    print("[3] Testing REPAIR pattern...")
    repair_tools = ['bash_run', 'bash_run', 'bash_run', 'edit_file', 'bash_run']
    repair_success = [False, False, True, True, True]
    regimes = infer_session_regimes(repair_tools, repair_success)
    print(f"    Tools: {repair_tools}")
    print(f"    Success: {repair_success}")
    print(f"    Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
    assert any(r == Regime.REPAIR for r, _ in regimes), "Expected some REPAIR"
    print("    [OK] REPAIR detected")
    print()

    # Test 4: DEADLOCK pattern (all errors)
    print("[4] Testing DEADLOCK pattern...")
    deadlock_tools = ['bash_run', 'bash_run', 'bash_run', 'bash_run', 'bash_run']
    deadlock_success = [False, False, False, False, False]
    regimes = infer_session_regimes(deadlock_tools, deadlock_success)
    print(f"    Tools: {deadlock_tools}")
    print(f"    Success: {deadlock_success}")
    print(f"    Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes]}")
    assert any(r == Regime.DEADLOCK for r, _ in regimes), "Expected some DEADLOCK"
    print("    [OK] DEADLOCK detected")
    print()

    # Test 5: Mixed pattern with transitions
    print("[5] Testing mixed pattern with transitions...")
    mixed_tools = [
        'read_file', 'edit_file',  # EXPLOIT
        'search_files', 'grep_code', 'list_dir', 'glob_files',  # EXPLORE
        'bash_run', 'bash_run', 'bash_run',  # REPAIR (retries)
        'edit_file', 'write_file'  # EXPLOIT
    ]
    mixed_success = [True, True, True, True, True, True, False, False, True, True, True]
    regimes = infer_session_regimes(mixed_tools, mixed_success)
    print(f"    Tools: {mixed_tools}")
    print(f"    Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes]}")

    inference = RegimeInference()
    transitions = inference.detect_transitions(regimes)
    print(f"    Transitions at indices: {transitions}")
    print("    [OK] Mixed pattern with transitions")
    print()

    print("=" * 70)
    print("REGIME INFERENCE TESTS COMPLETE")
    print("=" * 70)

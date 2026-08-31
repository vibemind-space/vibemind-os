"""
Stability Analyzer - Classify Variable Stability for Temporal State

Analyzes extracted variables to determine their stability classification:

1. STATIC: Stable across turns (anchors)
   - Value unchanged or identical mentions
   - High confidence anchors for reasoning
   - Example: container name mentioned consistently

2. DYNAMIC: Legitimate drift
   - Value changes within expected bounds
   - Normal conversation evolution
   - Example: retry count incrementing

3. CONFLICT: Contradictory statements
   - Incompatible values for same variable
   - BLOCKS tool execution (safety mechanism)
   - Example: "use port 8080" then "don't use port 8080"

Type-Specific Similarity Methods:
- IDs/Handles: Exact match
- Numeric: Relative deviation threshold (±10% default)
- Text/Constraints: Difflib sequence matcher + semantic checks
- Intent: State transition validation

Security Principle:
    Conflicts trigger threat modality / safety override to BLOCK action.
    "Besser zweimal fragen als einmal falsch handeln."
    (Better to ask twice than to act once wrongly.)
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from difflib import SequenceMatcher

from core.variable_extractor import ExtractedVariable, VariableType


class StabilityClass(Enum):
    """Classification of variable stability"""
    STATIC = "static"       # Stable anchor - safe to use
    DYNAMIC = "dynamic"     # Changing but valid - track carefully
    CONFLICT = "conflict"   # Contradictory - BLOCKS execution
    UNKNOWN = "unknown"     # Insufficient data


class ConflictType(Enum):
    """Types of detected conflicts"""
    VALUE_CONTRADICTION = "value_contradiction"     # Same var, incompatible values
    CONSTRAINT_VIOLATION = "constraint_violation"   # Value violates stated constraint
    INTENT_CONFLICT = "intent_conflict"             # Conflicting stated intents
    TEMPORAL_PARADOX = "temporal_paradox"           # Ordering contradiction
    SEMANTIC_OPPOSITION = "semantic_opposition"     # Semantically opposed statements


@dataclass
class StabilityReport:
    """Stability analysis for a single variable"""
    variable_name: str
    variable_type: VariableType
    stability_class: StabilityClass
    confidence: float

    # History analysis
    value_count: int = 0
    unique_values: int = 0
    first_value: Any = None
    current_value: Any = None

    # Stability metrics
    consistency_score: float = 1.0  # 1.0 = perfectly consistent
    drift_magnitude: float = 0.0    # How much has it changed

    # Conflict details (if any)
    conflict_type: Optional[ConflictType] = None
    conflict_description: str = ""
    conflicting_values: List[Any] = field(default_factory=list)

    # Timestamps
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_safe_to_use(self) -> bool:
        """Whether this variable is safe for tool parameter use"""
        return self.stability_class != StabilityClass.CONFLICT

    @property
    def blocks_execution(self) -> bool:
        """Whether this variable should block tool execution"""
        return self.stability_class == StabilityClass.CONFLICT

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'variable_name': self.variable_name,
            'variable_type': self.variable_type.value,
            'stability_class': self.stability_class.value,
            'confidence': self.confidence,
            'is_safe': self.is_safe_to_use,
            'blocks_execution': self.blocks_execution,
            'consistency_score': self.consistency_score,
            'drift_magnitude': self.drift_magnitude,
            'conflict_type': self.conflict_type.value if self.conflict_type else None,
            'conflict_description': self.conflict_description
        }


@dataclass
class OverallStabilityReport:
    """Overall stability analysis for all variables"""
    variable_reports: Dict[str, StabilityReport] = field(default_factory=dict)
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    @property
    def has_conflicts(self) -> bool:
        """Check if any conflicts exist"""
        return any(r.stability_class == StabilityClass.CONFLICT
                   for r in self.variable_reports.values())

    @property
    def conflict_count(self) -> int:
        """Number of conflicting variables"""
        return sum(1 for r in self.variable_reports.values()
                   if r.stability_class == StabilityClass.CONFLICT)

    @property
    def static_variables(self) -> Dict[str, StabilityReport]:
        """Get all static (stable) variables"""
        return {k: v for k, v in self.variable_reports.items()
                if v.stability_class == StabilityClass.STATIC}

    @property
    def dynamic_variables(self) -> Dict[str, StabilityReport]:
        """Get all dynamic variables"""
        return {k: v for k, v in self.variable_reports.items()
                if v.stability_class == StabilityClass.DYNAMIC}

    @property
    def conflicting_variables(self) -> Dict[str, StabilityReport]:
        """Get all conflicting variables"""
        return {k: v for k, v in self.variable_reports.items()
                if v.stability_class == StabilityClass.CONFLICT}

    @property
    def blocks_execution(self) -> bool:
        """Whether execution should be blocked"""
        return self.has_conflicts

    @property
    def overall_stability_score(self) -> float:
        """Overall stability score (0-1)"""
        if not self.variable_reports:
            return 1.0
        scores = [r.consistency_score for r in self.variable_reports.values()]
        return sum(scores) / len(scores)

    def get_conflict_summary(self) -> str:
        """Get human-readable conflict summary"""
        if not self.has_conflicts:
            return "No conflicts detected."

        lines = [f"CONFLICTS DETECTED ({self.conflict_count}):"]
        for name, report in self.conflicting_variables.items():
            lines.append(f"  - {name}: {report.conflict_description}")
        return "\n".join(lines)


class StabilityAnalyzer:
    """
    Analyze variable stability and detect conflicts

    Security-critical component:
    - Conflicts BLOCK tool execution
    - Static variables are safe anchors
    - Dynamic variables require tracking
    """

    # Thresholds for classification
    NUMERIC_TOLERANCE = 0.10  # 10% deviation allowed
    TEXT_SIMILARITY_THRESHOLD = 0.85  # 85% similarity for "same"
    MIN_MENTIONS_FOR_STATIC = 2  # Need at least 2 consistent mentions

    # Negation patterns for conflict detection
    NEGATION_PATTERNS = [
        r'\bnot\b', r'\bno\b', r'\bnever\b', r'\bdon\'?t\b',
        r'\bcannot\b', r'\bcan\'?t\b', r'\bwon\'?t\b', r'\bshouldn\'?t\b',
        r'\bwithout\b', r'\bexcept\b', r'\bunless\b', r'\bforbid\b',
    ]

    # Constraint keywords indicating requirements
    REQUIREMENT_KEYWORDS = ['must', 'should', 'require', 'need', 'have to']
    PROHIBITION_KEYWORDS = ['must not', 'cannot', 'should not', "don't", 'forbidden', 'prohibited']

    def __init__(
        self,
        numeric_tolerance: float = 0.10,
        text_similarity_threshold: float = 0.85,
        strict_mode: bool = True
    ):
        """
        Initialize stability analyzer

        Args:
            numeric_tolerance: Relative deviation allowed for numeric values
            text_similarity_threshold: Minimum similarity for text to be "same"
            strict_mode: If True, any conflict blocks execution
        """
        self.numeric_tolerance = numeric_tolerance
        self.text_similarity_threshold = text_similarity_threshold
        self.strict_mode = strict_mode

        # Compile negation patterns
        self.negation_regex = [re.compile(p, re.IGNORECASE) for p in self.NEGATION_PATTERNS]

        # Track constraints for conflict detection
        self.active_constraints: Dict[str, List[ExtractedVariable]] = defaultdict(list)
        self.active_prohibitions: Dict[str, List[ExtractedVariable]] = defaultdict(list)

    def analyze(
        self,
        variables: List[ExtractedVariable],
        existing_analysis: Optional[OverallStabilityReport] = None
    ) -> OverallStabilityReport:
        """
        Analyze stability of all variables

        Args:
            variables: List of extracted variables
            existing_analysis: Previous analysis to update (for incremental updates)

        Returns:
            OverallStabilityReport with all variable classifications
        """
        # Group variables by name
        by_name: Dict[str, List[ExtractedVariable]] = defaultdict(list)
        for var in variables:
            by_name[var.name].append(var)

        # Build constraints index
        self._index_constraints(variables)

        # Analyze each variable group
        report = OverallStabilityReport()

        for name, var_list in by_name.items():
            var_report = self._analyze_variable(name, var_list)
            report.variable_reports[name] = var_report

        # Check for cross-variable conflicts
        self._check_cross_variable_conflicts(report)

        return report

    def analyze_single(self, variable: ExtractedVariable) -> StabilityReport:
        """Analyze a single variable (for real-time checking)"""
        return self._analyze_variable(variable.name, [variable])

    def _analyze_variable(
        self,
        name: str,
        var_list: List[ExtractedVariable]
    ) -> StabilityReport:
        """Analyze stability of a single variable across all mentions"""
        if not var_list:
            return StabilityReport(
                variable_name=name,
                variable_type=VariableType.ID_HANDLE,  # Default
                stability_class=StabilityClass.UNKNOWN,
                confidence=0.0
            )

        # Get variable type from first instance
        var_type = var_list[0].var_type

        # Sort by turn ID (chronological)
        sorted_vars = sorted(var_list, key=lambda v: v.source_turn)

        # Extract all values
        values = [v.value for v in sorted_vars]
        unique_values = list(set(str(v) for v in values))

        # Calculate basic metrics
        first_value = values[0]
        current_value = values[-1]
        value_count = len(values)

        # Calculate consistency based on type
        consistency, drift = self._calculate_consistency(values, var_type)

        # Check for conflicts
        conflict_type, conflict_desc, conflicting = self._check_conflicts(
            name, sorted_vars, var_type
        )

        # Determine stability class
        if conflict_type is not None:
            stability_class = StabilityClass.CONFLICT
            confidence = 0.9  # High confidence in conflict detection
        elif len(unique_values) == 1 and value_count >= self.MIN_MENTIONS_FOR_STATIC:
            stability_class = StabilityClass.STATIC
            confidence = min(0.95, 0.7 + (value_count * 0.05))  # More mentions = higher confidence
        elif consistency >= self.text_similarity_threshold:
            stability_class = StabilityClass.STATIC
            confidence = consistency
        else:
            stability_class = StabilityClass.DYNAMIC
            confidence = 0.7

        return StabilityReport(
            variable_name=name,
            variable_type=var_type,
            stability_class=stability_class,
            confidence=confidence,
            value_count=value_count,
            unique_values=len(unique_values),
            first_value=first_value,
            current_value=current_value,
            consistency_score=consistency,
            drift_magnitude=drift,
            conflict_type=conflict_type,
            conflict_description=conflict_desc,
            conflicting_values=conflicting,
            first_seen=sorted_vars[0].timestamp,
            last_seen=sorted_vars[-1].timestamp
        )

    def _calculate_consistency(
        self,
        values: List[Any],
        var_type: VariableType
    ) -> Tuple[float, float]:
        """
        Calculate consistency score and drift magnitude

        Returns:
            (consistency_score, drift_magnitude)
        """
        if len(values) <= 1:
            return 1.0, 0.0

        if var_type == VariableType.ID_HANDLE:
            # Exact match required for IDs
            return self._id_consistency(values)

        elif var_type == VariableType.NUMERIC:
            # Numeric deviation check
            return self._numeric_consistency(values)

        elif var_type in (VariableType.CONSTRAINT, VariableType.INTENT_STATE):
            # Semantic similarity for text
            return self._text_consistency(values)

        else:
            # Default to text similarity
            return self._text_consistency(values)

    def _id_consistency(self, values: List[Any]) -> Tuple[float, float]:
        """Check ID consistency (exact match)"""
        str_values = [str(v) for v in values]
        unique = set(str_values)

        if len(unique) == 1:
            return 1.0, 0.0
        else:
            # Calculate what fraction of values match the most common
            from collections import Counter
            counts = Counter(str_values)
            most_common_count = counts.most_common(1)[0][1]
            consistency = most_common_count / len(str_values)
            drift = 1.0 - consistency
            return consistency, drift

    def _numeric_consistency(self, values: List[Any]) -> Tuple[float, float]:
        """Check numeric consistency (within tolerance)"""
        try:
            nums = [float(v) for v in values]
        except (ValueError, TypeError):
            return self._text_consistency(values)

        if not nums:
            return 1.0, 0.0

        mean_val = sum(nums) / len(nums)
        if mean_val == 0:
            # Check if all zeros
            if all(n == 0 for n in nums):
                return 1.0, 0.0
            mean_val = 1.0  # Avoid division by zero

        # Calculate relative deviations
        deviations = [abs(n - mean_val) / abs(mean_val) for n in nums]
        max_deviation = max(deviations)

        if max_deviation <= self.numeric_tolerance:
            consistency = 1.0 - (max_deviation / self.numeric_tolerance) * 0.2
            return consistency, max_deviation
        else:
            # Beyond tolerance - lower consistency
            consistency = max(0.0, 0.8 - (max_deviation - self.numeric_tolerance))
            return consistency, max_deviation

    def _text_consistency(self, values: List[Any]) -> Tuple[float, float]:
        """Check text consistency (sequence similarity)"""
        str_values = [str(v).lower() for v in values]

        if len(str_values) <= 1:
            return 1.0, 0.0

        # Compare all pairs
        similarities = []
        for i, v1 in enumerate(str_values):
            for v2 in str_values[i+1:]:
                sim = SequenceMatcher(None, v1, v2).ratio()
                similarities.append(sim)

        if not similarities:
            return 1.0, 0.0

        avg_similarity = sum(similarities) / len(similarities)
        min_similarity = min(similarities)

        drift = 1.0 - min_similarity
        return avg_similarity, drift

    def _check_conflicts(
        self,
        name: str,
        sorted_vars: List[ExtractedVariable],
        var_type: VariableType
    ) -> Tuple[Optional[ConflictType], str, List[Any]]:
        """
        Check for conflicts in variable values

        Returns:
            (conflict_type, description, conflicting_values) or (None, "", [])
        """
        if len(sorted_vars) <= 1:
            return None, "", []

        # Check for value contradictions
        values = [v.value for v in sorted_vars]
        contexts = [v.context for v in sorted_vars]

        # Check for negation patterns in contexts
        for i, ctx in enumerate(contexts):
            has_negation = any(p.search(ctx) for p in self.negation_regex)
            if has_negation:
                # Check if another context says the opposite
                for j, other_ctx in enumerate(contexts):
                    if i != j and not any(p.search(other_ctx) for p in self.negation_regex):
                        # Possible conflict: one negated, one not
                        if self._similar_subject(ctx, other_ctx, name):
                            return (
                                ConflictType.SEMANTIC_OPPOSITION,
                                f"Contradictory statements: '{ctx[:50]}...' vs '{other_ctx[:50]}...'",
                                [values[i], values[j]]
                            )

        # Check for constraint violations
        if var_type == VariableType.CONSTRAINT:
            conflict = self._check_constraint_conflicts(name, sorted_vars)
            if conflict:
                return conflict

        # Check for numeric contradictions (drastically different values)
        if var_type == VariableType.NUMERIC:
            try:
                nums = [float(v.value) for v in sorted_vars]
                if nums:
                    min_val, max_val = min(nums), max(nums)
                    if min_val > 0 and max_val / min_val > 10:  # 10x difference
                        return (
                            ConflictType.VALUE_CONTRADICTION,
                            f"Numeric values vary dramatically: {min_val} to {max_val}",
                            [min_val, max_val]
                        )
            except (ValueError, TypeError):
                pass

        # Check for ID contradictions (different IDs for same semantic role)
        if var_type == VariableType.ID_HANDLE:
            str_values = [str(v) for v in values]
            unique = set(str_values)
            if len(unique) > 2:  # More than 2 different values might indicate confusion
                # Check if values are semantically related but different
                if self._values_seem_contradictory(list(unique)):
                    return (
                        ConflictType.VALUE_CONTRADICTION,
                        f"Multiple different values for {name}: {', '.join(unique)}",
                        list(unique)
                    )

        return None, "", []

    def _similar_subject(self, ctx1: str, ctx2: str, var_name: str) -> bool:
        """Check if two contexts are about the same subject"""
        # Simple check: both mention the variable name or similar keywords
        ctx1_lower = ctx1.lower()
        ctx2_lower = ctx2.lower()

        # Check for variable name
        var_words = var_name.lower().split('_')
        matches = sum(1 for w in var_words if w in ctx1_lower and w in ctx2_lower)

        return matches >= 1 or SequenceMatcher(None, ctx1_lower, ctx2_lower).ratio() > 0.5

    def _values_seem_contradictory(self, values: List[str]) -> bool:
        """Check if a list of values seems contradictory"""
        # More than 2 very different values for an ID suggests confusion
        if len(values) > 2:
            similarities = []
            for i, v1 in enumerate(values):
                for v2 in values[i+1:]:
                    sim = SequenceMatcher(None, v1, v2).ratio()
                    similarities.append(sim)

            # If average similarity is low, these might be conflicting
            if similarities and sum(similarities) / len(similarities) < 0.3:
                return True

        return False

    def _check_constraint_conflicts(
        self,
        name: str,
        sorted_vars: List[ExtractedVariable]
    ) -> Optional[Tuple[ConflictType, str, List[Any]]]:
        """Check for conflicts between requirements and prohibitions"""
        requirements = []
        prohibitions = []

        for var in sorted_vars:
            value_str = str(var.value).lower()
            context_str = var.context.lower()

            # Categorize as requirement or prohibition
            is_prohibition = any(kw in value_str or kw in context_str
                                  for kw in self.PROHIBITION_KEYWORDS)
            is_requirement = any(kw in value_str or kw in context_str
                                  for kw in self.REQUIREMENT_KEYWORDS)

            if is_prohibition:
                prohibitions.append(var)
            elif is_requirement:
                requirements.append(var)

        # Check if same thing is required and prohibited
        for req in requirements:
            for prob in prohibitions:
                if self._constraints_conflict(req, prob):
                    return (
                        ConflictType.CONSTRAINT_VIOLATION,
                        f"Requirement conflicts with prohibition: '{req.value}' vs '{prob.value}'",
                        [req.value, prob.value]
                    )

        return None

    def _constraints_conflict(
        self,
        req: ExtractedVariable,
        prob: ExtractedVariable
    ) -> bool:
        """Check if a requirement and prohibition conflict"""
        req_str = str(req.value).lower()
        prob_str = str(prob.value).lower()

        # Remove negation words from prohibition to compare subjects
        for pattern in self.NEGATION_PATTERNS:
            prob_str = re.sub(pattern, '', prob_str, flags=re.IGNORECASE)

        # Check similarity of remaining content
        similarity = SequenceMatcher(None, req_str, prob_str.strip()).ratio()
        return similarity > 0.6

    def _index_constraints(self, variables: List[ExtractedVariable]):
        """Build index of constraints for cross-checking"""
        self.active_constraints.clear()
        self.active_prohibitions.clear()

        for var in variables:
            if var.var_type == VariableType.CONSTRAINT:
                value_str = str(var.value).lower()

                is_prohibition = any(kw in value_str for kw in self.PROHIBITION_KEYWORDS)

                if is_prohibition:
                    self.active_prohibitions[var.name].append(var)
                else:
                    self.active_constraints[var.name].append(var)

    def _check_cross_variable_conflicts(self, report: OverallStabilityReport):
        """Check for conflicts between different variables"""
        # Check if any prohibition conflicts with an ID/entity being used
        for prob_name, prob_vars in self.active_prohibitions.items():
            for prob in prob_vars:
                prob_value = str(prob.value).lower()

                # Check against all ID_HANDLE and ENTITY variables
                for name, var_report in report.variable_reports.items():
                    if var_report.variable_type in (VariableType.ID_HANDLE, VariableType.ENTITY):
                        var_value = str(var_report.current_value).lower()

                        # Check if prohibited value appears in variable
                        if var_value in prob_value or prob_value in var_value:
                            # Mark as conflict
                            var_report.stability_class = StabilityClass.CONFLICT
                            var_report.conflict_type = ConflictType.CONSTRAINT_VIOLATION
                            var_report.conflict_description = (
                                f"Value '{var_value}' may violate constraint: '{prob.value}'"
                            )
                            var_report.conflicting_values = [var_value, prob.value]

    def is_safe_to_execute(self, report: OverallStabilityReport) -> Tuple[bool, str]:
        """
        Check if it's safe to execute based on stability analysis

        Returns:
            (is_safe, reason)
        """
        if not report.has_conflicts:
            return True, "All variables are stable or dynamic within bounds."

        if self.strict_mode:
            return False, report.get_conflict_summary()

        # Non-strict: only block on critical conflicts
        critical_conflicts = [
            r for r in report.conflicting_variables.values()
            if r.conflict_type in (
                ConflictType.CONSTRAINT_VIOLATION,
                ConflictType.VALUE_CONTRADICTION
            )
        ]

        if critical_conflicts:
            return False, f"Critical conflicts detected: {len(critical_conflicts)}"

        return True, "Minor conflicts detected but not blocking."

    def get_safe_variables(
        self,
        report: OverallStabilityReport
    ) -> Dict[str, Any]:
        """
        Get dictionary of safe-to-use variables and their values

        Only returns STATIC and non-conflicting DYNAMIC variables.
        """
        safe_vars = {}

        for name, var_report in report.variable_reports.items():
            if var_report.is_safe_to_use:
                safe_vars[name] = var_report.current_value

        return safe_vars

    def get_statistics(self) -> Dict:
        """Get analyzer statistics"""
        return {
            'numeric_tolerance': self.numeric_tolerance,
            'text_similarity_threshold': self.text_similarity_threshold,
            'strict_mode': self.strict_mode,
            'active_constraints': len(self.active_constraints),
            'active_prohibitions': len(self.active_prohibitions)
        }


if __name__ == "__main__":
    print("=" * 70)
    print("STABILITY ANALYZER - Classify Variable Stability for Temporal State")
    print("=" * 70)
    print()
    print("Security Principle:")
    print('  "Besser zweimal fragen als einmal falsch handeln."')
    print('  (Better to ask twice than to act once wrongly.)')
    print()

    from core.variable_extractor import ExtractedVariable, VariableType

    analyzer = StabilityAnalyzer()

    # Test with sample variables
    test_variables = [
        # Consistent ID - should be STATIC
        ExtractedVariable(
            name="container_nginx",
            value="nginx:latest",
            var_type=VariableType.ID_HANDLE,
            confidence=0.9,
            source_turn=0,
            timestamp=datetime.now(),
            raw_match="container nginx:latest"
        ),
        ExtractedVariable(
            name="container_nginx",
            value="nginx:latest",
            var_type=VariableType.ID_HANDLE,
            confidence=0.9,
            source_turn=1,
            timestamp=datetime.now(),
            raw_match="container nginx:latest"
        ),

        # Changing port - should be DYNAMIC or CONFLICT
        ExtractedVariable(
            name="port",
            value=8080,
            var_type=VariableType.NUMERIC,
            confidence=0.85,
            source_turn=0,
            timestamp=datetime.now(),
            raw_match="port 8080",
            context="deploy on port 8080"
        ),
        ExtractedVariable(
            name="port",
            value=9000,
            var_type=VariableType.NUMERIC,
            confidence=0.85,
            source_turn=2,
            timestamp=datetime.now(),
            raw_match="port 9000",
            context="actually use port 9000 instead"
        ),

        # Conflicting constraint
        ExtractedVariable(
            name="requirement_1",
            value="must use SSL",
            var_type=VariableType.CONSTRAINT,
            confidence=0.7,
            source_turn=0,
            timestamp=datetime.now(),
            raw_match="must use SSL",
            context="security requires must use SSL"
        ),
        ExtractedVariable(
            name="prohibition_1",
            value="cannot use SSL on internal network",
            var_type=VariableType.CONSTRAINT,
            confidence=0.7,
            source_turn=1,
            timestamp=datetime.now(),
            raw_match="cannot use SSL",
            context="cannot use SSL on internal network"
        ),
    ]

    print("Analyzing test variables...")
    report = analyzer.analyze(test_variables)

    print(f"\nOverall Stability Score: {report.overall_stability_score:.2f}")
    print(f"Has Conflicts: {report.has_conflicts}")
    print(f"Blocks Execution: {report.blocks_execution}")
    print()

    print("Variable Reports:")
    print("-" * 70)
    for name, var_report in report.variable_reports.items():
        status = "BLOCKS" if var_report.blocks_execution else "OK"
        print(f"  [{status}] {name}: {var_report.stability_class.value}")
        print(f"       Value: {var_report.current_value}")
        print(f"       Consistency: {var_report.consistency_score:.2f}")
        if var_report.conflict_description:
            print(f"       Conflict: {var_report.conflict_description}")
        print()

    # Test execution safety
    is_safe, reason = analyzer.is_safe_to_execute(report)
    print(f"Safe to Execute: {is_safe}")
    print(f"Reason: {reason}")
    print()

    # Show safe variables
    safe_vars = analyzer.get_safe_variables(report)
    print(f"Safe Variables: {safe_vars}")
    print()
    print("=" * 70)

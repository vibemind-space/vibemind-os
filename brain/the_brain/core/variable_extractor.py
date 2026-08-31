"""
Variable Extractor - Extract Semantic Variables from Conversation

Extracts and tracks variables from conversation context, transforming
unstructured text into structured key-value pairs that can be tracked
over time for stability analysis.

Variable Types:
- IDs/References: Container names, file paths, URLs, ticket IDs
- Entities: Services, systems, resources, people
- Numeric Constraints: Limits, ports, timeouts, counts
- Policies/Constraints: "must be", "cannot", "before"
- Intent States: "want to", "trying to", "goal is"

Each variable is represented as:
    (key, value, type, timestamp, source_turn)

This enables:
- Tracking variable stability over conversation turns
- Detecting conflicts between statements
- Building structured state from unstructured text
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from core.stream_separator import ConversationEvent


class VariableType(Enum):
    """Types of extractable variables"""
    ID_HANDLE = "id_handle"       # Container names, file paths, URLs, ticket IDs
    ENTITY = "entity"             # Services, systems, resources, people
    NUMERIC = "numeric"           # Counts, ports, timeouts, limits
    CONSTRAINT = "constraint"     # "must be", "cannot", "before", policies
    INTENT_STATE = "intent_state" # "want to", "trying to", "goal is"
    GOAL = "goal"                 # Explicit goal statements
    PARAMETER = "parameter"       # Key-value parameters for tools


@dataclass
class ExtractedVariable:
    """Single extracted variable with full metadata"""
    name: str
    value: Any
    var_type: VariableType
    confidence: float
    source_turn: int
    timestamp: datetime
    raw_match: str  # The original text that was matched
    context: str = ""  # Surrounding context

    # Tracking fields (updated by stability analyzer)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    mention_count: int = 1
    value_history: List[Tuple[Any, int]] = field(default_factory=list)  # (value, turn_id)

    def __post_init__(self):
        if self.first_seen is None:
            self.first_seen = self.timestamp
        self.last_seen = self.timestamp
        if not self.value_history:
            self.value_history = [(self.value, self.source_turn)]

    def update(self, new_value: Any, turn_id: int, timestamp: datetime):
        """Update variable with new value"""
        self.value = new_value
        self.last_seen = timestamp
        self.mention_count += 1
        self.value_history.append((new_value, turn_id))

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'value': self.value,
            'type': self.var_type.value,
            'confidence': self.confidence,
            'source_turn': self.source_turn,
            'timestamp': self.timestamp.isoformat(),
            'mention_count': self.mention_count,
            'raw_match': self.raw_match
        }


class VariableExtractor:
    """
    Extract and track variables from conversation

    Uses regex patterns + simple NLP for extraction.
    Tracks variable mentions across conversation turns.
    """

    # === ID/HANDLE PATTERNS ===
    ID_PATTERNS = [
        # Container/image names
        (r'(?:container|image|service)[\s:]+["\']?([a-zA-Z0-9_\-\.:/]+)["\']?', 'container'),
        # File paths
        (r'(?:file|path)[\s:]+["\']?([/\\]?[a-zA-Z0-9_\-\./\\]+)["\']?', 'file_path'),
        (r'["\']([/\\][a-zA-Z0-9_\-\./\\]+)["\']', 'file_path'),
        # URLs
        (r'(https?://[^\s<>"\']+)', 'url'),
        # Git repos
        (r'(?:repo|repository)[\s:]+["\']?([a-zA-Z0-9_\-\./]+)["\']?', 'repo'),
        # Docker specific
        (r'(?:docker|kubectl)\s+\w+\s+([a-zA-Z0-9_\-\.:/]+)', 'docker_ref'),
        # Ticket IDs
        (r'(?:ticket|issue|bug|task)[\s#:]+([A-Z]+-\d+|#?\d+)', 'ticket_id'),
        # Branch names
        (r'(?:branch|checkout)[\s:]+["\']?([a-zA-Z0-9_\-/]+)["\']?', 'branch'),
    ]

    # === ENTITY PATTERNS ===
    ENTITY_PATTERNS = [
        # Service names
        (r'(?:service|server|system)[\s:]+["\']?([a-zA-Z0-9_\-]+)["\']?', 'service'),
        # Database names
        (r'(?:database|db|table)[\s:]+["\']?([a-zA-Z0-9_\-]+)["\']?', 'database'),
        # User/account names
        (r'(?:user|account|username)[\s:]+["\']?([a-zA-Z0-9_\-@\.]+)["\']?', 'user'),
        # Environment names
        (r'(?:env|environment)[\s:]+["\']?([a-zA-Z0-9_\-]+)["\']?', 'environment'),
        # Cluster/namespace
        (r'(?:cluster|namespace)[\s:]+["\']?([a-zA-Z0-9_\-]+)["\']?', 'cluster'),
    ]

    # === NUMERIC PATTERNS ===
    NUMERIC_PATTERNS = [
        # Port numbers
        (r'(?:port)[\s:]+(\d+)', 'port'),
        (r':(\d{2,5})(?:[/\s]|$)', 'port'),
        # Counts/limits
        (r'(\d+)\s*(?:replicas?|instances?|copies)', 'count'),
        (r'(?:limit|max|maximum)[\s:]+(\d+)', 'limit'),
        (r'(?:min|minimum)[\s:]+(\d+)', 'minimum'),
        # Timeouts/durations
        (r'(\d+)\s*(?:ms|milliseconds?)', 'timeout_ms'),
        (r'(\d+)\s*(?:s|seconds?)', 'timeout_sec'),
        (r'(\d+)\s*(?:m|minutes?)', 'timeout_min'),
        (r'(?:timeout|duration)[\s:]+(\d+)', 'timeout'),
        # Memory/size
        (r'(\d+)\s*(?:mb|gb|tb|ki|mi|gi)', 'memory'),
        (r'(?:memory|ram|size)[\s:]+(\d+\s*[kmgt]?[bi]?)', 'memory'),
        # Version numbers
        (r'(?:version|v)[\s:]+([0-9]+\.[0-9]+(?:\.[0-9]+)?)', 'version'),
    ]

    # === CONSTRAINT PATTERNS ===
    CONSTRAINT_PATTERNS = [
        # Must/should
        (r'(must\s+(?:be|have|use|run)\s+[^,.]+)', 'requirement'),
        (r'(should\s+(?:be|have|use|run)\s+[^,.]+)', 'recommendation'),
        # Cannot/must not
        (r'(cannot\s+[^,.]+)', 'prohibition'),
        (r'(must\s+not\s+[^,.]+)', 'prohibition'),
        (r"(don't\s+[^,.]+)", 'prohibition'),
        # Before/after ordering
        (r'(before\s+[^,.]+)', 'ordering'),
        (r'(after\s+[^,.]+)', 'ordering'),
        # Requires/depends
        (r'(requires?\s+[^,.]+)', 'dependency'),
        (r'(depends?\s+on\s+[^,.]+)', 'dependency'),
        # Only/exclusively
        (r'(only\s+[^,.]+)', 'exclusivity'),
        (r'(exclusively?\s+[^,.]+)', 'exclusivity'),
    ]

    # === INTENT STATE PATTERNS ===
    INTENT_PATTERNS = [
        # Want/need
        (r'(?:i\s+)?want\s+to\s+([^,.]+)', 'want'),
        (r'(?:i\s+)?need\s+to\s+([^,.]+)', 'need'),
        # Trying/attempting
        (r'(?:i\'?m\s+)?trying\s+to\s+([^,.]+)', 'trying'),
        (r'attempting\s+to\s+([^,.]+)', 'attempting'),
        # Goal/objective
        (r'(?:my\s+)?goal\s+is\s+(?:to\s+)?([^,.]+)', 'goal'),
        (r'(?:the\s+)?objective\s+is\s+(?:to\s+)?([^,.]+)', 'objective'),
        # Looking for/searching
        (r'looking\s+for\s+([^,.]+)', 'searching'),
        (r'searching\s+for\s+([^,.]+)', 'searching'),
        # Help with
        (r'help\s+(?:me\s+)?(?:with\s+)?([^,.]+)', 'help_request'),
    ]

    # === PARAMETER PATTERNS (key=value) ===
    PARAMETER_PATTERNS = [
        # key=value
        (r'(\w+)\s*=\s*["\']?([^"\'\s,]+)["\']?', None),
        # key: value
        (r'(\w+)\s*:\s*["\']?([^"\'\s,]+)["\']?', None),
        # --flag value
        (r'--(\w+)\s+["\']?([^"\'\s]+)["\']?', None),
        # -f value
        (r'-(\w)\s+["\']?([^"\'\s]+)["\']?', None),
    ]

    def __init__(self, confidence_threshold: float = 0.5):
        """
        Initialize variable extractor

        Args:
            confidence_threshold: Minimum confidence to include a variable
        """
        self.confidence_threshold = confidence_threshold

        # Compile all patterns
        self.id_patterns = [(re.compile(p, re.IGNORECASE), n) for p, n in self.ID_PATTERNS]
        self.entity_patterns = [(re.compile(p, re.IGNORECASE), n) for p, n in self.ENTITY_PATTERNS]
        self.numeric_patterns = [(re.compile(p, re.IGNORECASE), n) for p, n in self.NUMERIC_PATTERNS]
        self.constraint_patterns = [(re.compile(p, re.IGNORECASE), n) for p, n in self.CONSTRAINT_PATTERNS]
        self.intent_patterns = [(re.compile(p, re.IGNORECASE), n) for p, n in self.INTENT_PATTERNS]
        self.parameter_patterns = [(re.compile(p), n) for p, n in self.PARAMETER_PATTERNS]

        # Variable tracking
        self.known_variables: Dict[str, ExtractedVariable] = {}
        self.variable_history: List[ExtractedVariable] = []

    def extract(
        self,
        conversation_events: List[ConversationEvent]
    ) -> List[ExtractedVariable]:
        """
        Extract all variables from conversation history

        Args:
            conversation_events: List of conversation events

        Returns:
            List of extracted variables
        """
        all_variables = []

        for event in conversation_events:
            event_vars = self.extract_from_text(
                text=event.text,
                turn_id=event.turn_id,
                timestamp=event.timestamp
            )
            all_variables.extend(event_vars)

            # Update known variables
            for var in event_vars:
                self._update_known_variable(var)

        return all_variables

    def extract_from_text(
        self,
        text: str,
        turn_id: int = 0,
        timestamp: Optional[datetime] = None
    ) -> List[ExtractedVariable]:
        """
        Extract variables from a single text

        Args:
            text: Text to extract from
            turn_id: Turn ID for tracking
            timestamp: Timestamp for the extraction

        Returns:
            List of extracted variables
        """
        if timestamp is None:
            timestamp = datetime.now()

        variables = []

        # Extract by type
        variables.extend(self._extract_ids(text, turn_id, timestamp))
        variables.extend(self._extract_entities(text, turn_id, timestamp))
        variables.extend(self._extract_numerics(text, turn_id, timestamp))
        variables.extend(self._extract_constraints(text, turn_id, timestamp))
        variables.extend(self._extract_intents(text, turn_id, timestamp))
        variables.extend(self._extract_parameters(text, turn_id, timestamp))

        # Filter by confidence
        variables = [v for v in variables if v.confidence >= self.confidence_threshold]

        # Store in history
        self.variable_history.extend(variables)

        return variables

    def _extract_ids(
        self,
        text: str,
        turn_id: int,
        timestamp: datetime
    ) -> List[ExtractedVariable]:
        """Extract ID/handle variables"""
        variables = []

        for pattern, name_hint in self.id_patterns:
            for match in pattern.finditer(text):
                value = match.group(1)
                name = f"{name_hint}_{self._normalize_name(value)}"

                # Calculate confidence based on pattern specificity
                confidence = 0.8 if len(match.groups()) == 1 else 0.6

                variables.append(ExtractedVariable(
                    name=name,
                    value=value,
                    var_type=VariableType.ID_HANDLE,
                    confidence=confidence,
                    source_turn=turn_id,
                    timestamp=timestamp,
                    raw_match=match.group(0),
                    context=self._get_context(text, match.start(), match.end())
                ))

        return variables

    def _extract_entities(
        self,
        text: str,
        turn_id: int,
        timestamp: datetime
    ) -> List[ExtractedVariable]:
        """Extract entity variables"""
        variables = []

        for pattern, name_hint in self.entity_patterns:
            for match in pattern.finditer(text):
                value = match.group(1)
                name = f"{name_hint}_{self._normalize_name(value)}"

                variables.append(ExtractedVariable(
                    name=name,
                    value=value,
                    var_type=VariableType.ENTITY,
                    confidence=0.75,
                    source_turn=turn_id,
                    timestamp=timestamp,
                    raw_match=match.group(0),
                    context=self._get_context(text, match.start(), match.end())
                ))

        return variables

    def _extract_numerics(
        self,
        text: str,
        turn_id: int,
        timestamp: datetime
    ) -> List[ExtractedVariable]:
        """Extract numeric variables"""
        variables = []

        for pattern, name_hint in self.numeric_patterns:
            for match in pattern.finditer(text):
                value_str = match.group(1)
                try:
                    value = int(re.sub(r'[^\d]', '', value_str))
                except ValueError:
                    value = value_str

                name = f"{name_hint}"

                variables.append(ExtractedVariable(
                    name=name,
                    value=value,
                    var_type=VariableType.NUMERIC,
                    confidence=0.85,
                    source_turn=turn_id,
                    timestamp=timestamp,
                    raw_match=match.group(0),
                    context=self._get_context(text, match.start(), match.end())
                ))

        return variables

    def _extract_constraints(
        self,
        text: str,
        turn_id: int,
        timestamp: datetime
    ) -> List[ExtractedVariable]:
        """Extract constraint variables"""
        variables = []

        for pattern, name_hint in self.constraint_patterns:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                name = f"{name_hint}_{turn_id}"

                variables.append(ExtractedVariable(
                    name=name,
                    value=value,
                    var_type=VariableType.CONSTRAINT,
                    confidence=0.7,
                    source_turn=turn_id,
                    timestamp=timestamp,
                    raw_match=match.group(0),
                    context=self._get_context(text, match.start(), match.end())
                ))

        return variables

    def _extract_intents(
        self,
        text: str,
        turn_id: int,
        timestamp: datetime
    ) -> List[ExtractedVariable]:
        """Extract intent state variables"""
        variables = []

        for pattern, name_hint in self.intent_patterns:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                name = f"intent_{name_hint}"

                variables.append(ExtractedVariable(
                    name=name,
                    value=value,
                    var_type=VariableType.INTENT_STATE,
                    confidence=0.65,
                    source_turn=turn_id,
                    timestamp=timestamp,
                    raw_match=match.group(0),
                    context=self._get_context(text, match.start(), match.end())
                ))

        return variables

    def _extract_parameters(
        self,
        text: str,
        turn_id: int,
        timestamp: datetime
    ) -> List[ExtractedVariable]:
        """Extract key-value parameter variables"""
        variables = []

        for pattern, _ in self.parameter_patterns:
            for match in pattern.finditer(text):
                key = match.group(1)
                value = match.group(2)
                name = f"param_{key}"

                variables.append(ExtractedVariable(
                    name=name,
                    value=value,
                    var_type=VariableType.PARAMETER,
                    confidence=0.9,
                    source_turn=turn_id,
                    timestamp=timestamp,
                    raw_match=match.group(0),
                    context=self._get_context(text, match.start(), match.end())
                ))

        return variables

    def _update_known_variable(self, var: ExtractedVariable):
        """Update tracking for a known variable"""
        if var.name in self.known_variables:
            existing = self.known_variables[var.name]
            existing.update(var.value, var.source_turn, var.timestamp)
        else:
            self.known_variables[var.name] = var

    def _normalize_name(self, value: str) -> str:
        """Normalize a value into a valid variable name"""
        # Keep only alphanumeric and underscores
        name = re.sub(r'[^a-zA-Z0-9_]', '_', value)
        # Remove consecutive underscores
        name = re.sub(r'_+', '_', name)
        # Limit length
        return name[:30].strip('_').lower()

    def _get_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        """Get surrounding context for a match"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]

    def get_variables_by_type(self, var_type: VariableType) -> List[ExtractedVariable]:
        """Get all known variables of a specific type"""
        return [v for v in self.known_variables.values() if v.var_type == var_type]

    def get_variable_names(self) -> Set[str]:
        """Get all known variable names"""
        return set(self.known_variables.keys())

    def get_variable(self, name: str) -> Optional[ExtractedVariable]:
        """Get a specific variable by name"""
        return self.known_variables.get(name)

    def clear(self):
        """Clear all tracked variables"""
        self.known_variables.clear()
        self.variable_history.clear()

    def get_statistics(self) -> Dict:
        """Get extraction statistics"""
        type_counts = defaultdict(int)
        for var in self.known_variables.values():
            type_counts[var.var_type.value] += 1

        return {
            'total_variables': len(self.known_variables),
            'history_size': len(self.variable_history),
            'by_type': dict(type_counts),
            'confidence_threshold': self.confidence_threshold
        }


if __name__ == "__main__":
    print("=" * 70)
    print("VARIABLE EXTRACTOR - Extract Semantic Variables from Conversation")
    print("=" * 70)
    print()

    extractor = VariableExtractor()

    # Test extraction
    test_texts = [
        "I need to deploy container nginx:latest on port 8080",
        "The service database must be running before we start",
        "Please check file /var/log/app.log for errors",
        "I'm trying to debug the connection timeout issue, max 30 seconds",
        "Set replicas to 3 and memory limit to 512mb",
    ]

    print("Test Extractions:")
    print("-" * 70)

    for text in test_texts:
        print(f"\nInput: {text}")
        vars = extractor.extract_from_text(text, turn_id=test_texts.index(text))
        for v in vars:
            print(f"  [{v.var_type.value}] {v.name} = {v.value} (conf: {v.confidence:.2f})")

    print()
    print("Statistics:", extractor.get_statistics())
    print()
    print("=" * 70)

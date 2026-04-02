"""
AmbiguityDetector - Requirement Ambiguity Detection.

Detects unclear or ambiguous requirements before code generation
and suggests that clarification is needed.

Ambiguity Types:
1. VAGUE_TERM: Undefined terms like "user management", "good performance"
2. CONFLICT: Contradictory requirements
3. MISSING_DETAIL: Implied features without specification
4. UNCLEAR_SCOPE: Unbounded requirements like "handle all errors"
5. TECHNOLOGY_CHOICE: Multiple valid technical approaches
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import structlog

from src.utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

logger = structlog.get_logger(__name__)


class AmbiguityType(Enum):
    """Types of requirement ambiguity."""

    VAGUE_TERM = "vague_term"  # Undefined/unclear terms
    CONFLICT = "conflict"  # Contradictory requirements
    MISSING_DETAIL = "missing_detail"  # Implied but not specified
    UNCLEAR_SCOPE = "unclear_scope"  # Unbounded requirements
    TECHNOLOGY_CHOICE = "technology_choice"  # Multiple valid approaches


class AmbiguitySeverity(Enum):
    """Severity of detected ambiguity."""

    HIGH = "high"  # Must clarify before proceeding
    MEDIUM = "medium"  # Should clarify but can make assumptions
    LOW = "low"  # Minor, can proceed with default


@dataclass
class DetectedAmbiguity:
    """A single detected ambiguity in requirements."""

    id: str  # Unique identifier
    requirement_id: str  # Which requirement has the ambiguity
    requirement_text: str  # The requirement text
    ambiguity_type: AmbiguityType
    description: str  # What's ambiguous
    severity: AmbiguitySeverity
    detected_term: str = ""  # The specific term that triggered detection
    context: str = ""  # Additional context
    suggested_questions: list[str] = field(default_factory=list)


# Vague terms that typically need clarification
VAGUE_TERMS: dict[str, list[str]] = {
    "user_management": [
        "What user actions should be supported? (login, register, profile, roles?)",
        "Should there be admin vs regular users?",
    ],
    "authentication": [
        "What auth method? (JWT, OAuth, session-based?)",
        "Should there be password reset, MFA, social login?",
    ],
    "good performance": [
        "What's the target response time?",
        "How many concurrent users should it support?",
    ],
    "fast": [
        "What's acceptable latency (ms)?",
        "Under what load conditions?",
    ],
    "secure": [
        "What security standards? (OWASP, PCI-DSS, HIPAA?)",
        "What data needs protection?",
    ],
    "scalable": [
        "What's the expected growth? (10x, 100x?)",
        "Horizontal or vertical scaling?",
    ],
    "responsive": [
        "What breakpoints? (mobile, tablet, desktop?)",
        "Mobile-first approach?",
    ],
    "real-time": [
        "What latency is acceptable? (<100ms, <1s?)",
        "WebSocket or polling?",
    ],
    "intuitive": [
        "Any specific UX patterns to follow?",
        "Reference apps/designs?",
    ],
    "comprehensive": [
        "What specific features are included?",
        "What's the minimum viable scope?",
    ],
    "robust": [
        "What failure modes to handle?",
        "What's acceptable downtime?",
    ],
    "modern": [
        "What technologies are preferred?",
        "Any constraints on dependencies?",
    ],
    "handle errors": [
        "What error types? (validation, network, auth?)",
        "How should errors be displayed to users?",
    ],
    "notifications": [
        "What channels? (email, SMS, push, in-app?)",
        "What triggers notifications?",
    ],
    "dashboard": [
        "What metrics/data to display?",
        "Real-time or periodic refresh?",
    ],
    "reports": [
        "What report types? (PDF, CSV, charts?)",
        "What data to include?",
    ],
    "integration": [
        "Which external services?",
        "API keys or OAuth for third parties?",
    ],
    "admin panel": [
        "What admin actions? (CRUD, bulk operations, analytics?)",
        "Role-based access for admins?",
    ],
    "multi-tenant": [
        "Data isolation strategy? (schema, row-level?)",
        "Tenant-specific customization?",
    ],
}

# Patterns indicating unclear scope
UNCLEAR_SCOPE_PATTERNS: list[str] = [
    r"\ball\b.*\berrors?\b",  # "handle all errors"
    r"\bevery\b.*\bcase\b",  # "every case"
    r"\bany\b.*\bformat\b",  # "any format"
    r"\bfull\b.*\bfunctionality\b",  # "full functionality"
    r"\bcomplete\b.*\bsolution\b",  # "complete solution"
    r"\bunlimited\b",  # "unlimited"
    r"\beverything\b",  # "everything"
    r"\ball\b.*\btypes?\b",  # "all types"
]

# Patterns indicating missing details
MISSING_DETAIL_PATTERNS: list[tuple[str, str, list[str]]] = [
    # (pattern, what's missing, questions to ask)
    (
        r"\blogin\b",
        "session management",
        ["How long should sessions last?", "Allow multiple sessions?"],
    ),
    (
        r"\bpayment\b",
        "payment provider",
        ["Which payment gateway? (Stripe, PayPal?)", "What currencies?"],
    ),
    (
        r"\bemail\b(?!\s*validation)",
        "email provider",
        ["Which email service? (SendGrid, SES?)", "Transactional or marketing?"],
    ),
    (
        r"\bupload\b",
        "file storage",
        ["Max file size?", "Allowed file types?", "Storage location (S3, local?)"],
    ),
    (
        r"\bsearch\b",
        "search implementation",
        ["Full-text search needed?", "Filter/facets required?"],
    ),
    (
        r"\bi18n\b|\binternational\b|\blocalization\b",
        "language support",
        ["Which languages?", "RTL support needed?"],
    ),
    (
        r"\bnotif\w*\b",
        "notification delivery",
        ["Real-time or batch?", "Retry on failure?"],
    ),
    (
        r"\banalytics\b|\btracking\b",
        "analytics provider",
        ["Which analytics? (GA, Mixpanel?)", "What events to track?"],
    ),
    (
        r"\bexport\b",
        "export format",
        ["Which formats? (CSV, PDF, Excel?)", "Include all data or filtered?"],
    ),
    (
        r"\bimport\b",
        "import validation",
        ["What validation on import?", "Handle duplicates how?"],
    ),
]

# Technology choice patterns (multiple valid approaches)
TECHNOLOGY_CHOICES: list[tuple[str, str, list[str]]] = [
    # (trigger, choice description, options)
    (
        r"\bdatabase\b|\bdata\s*store\b",
        "database type",
        ["PostgreSQL (relational)", "MongoDB (document)", "SQLite (local)"],
    ),
    (
        r"\bstate\s*management\b|\bglobal\s*state\b",
        "state management approach",
        ["Zustand (simple)", "Redux (complex)", "React Context (minimal)"],
    ),
    (
        r"\bstyling\b|\bcss\b|\bui\b",
        "styling approach",
        ["Tailwind CSS", "CSS Modules", "Styled Components"],
    ),
    (
        r"\bapi\b(?!\s*key)",
        "API style",
        ["REST", "GraphQL", "tRPC"],
    ),
    (
        r"\btest\w*\b",
        "testing framework",
        ["Vitest (fast)", "Jest (mature)", "Playwright (e2e)"],
    ),
    (
        r"\bdeploy\w*\b|\bhost\w*\b",
        "deployment target",
        ["Docker container", "Serverless (AWS Lambda)", "Traditional server"],
    ),
]


class AmbiguityDetector:
    """
    Detects ambiguous requirements before code generation.

    Analyzes requirement text for:
    - Vague terms that need definition
    - Conflicting requirements
    - Missing implementation details
    - Unbounded scope
    - Technology choices
    """

    def __init__(self) -> None:
        self.logger = logger.bind(component="AmbiguityDetector")
        self._ambiguity_counter = 0

    def analyze(
        self,
        requirements: list[dict],
    ) -> list[DetectedAmbiguity]:
        """
        Analyze requirements for ambiguities.

        Args:
            requirements: List of requirement dicts with 'id', 'name', 'description'

        Returns:
            List of detected ambiguities
        """
        ambiguities: list[DetectedAmbiguity] = []

        for req in requirements:
            req_id = req.get("id", str(requirements.index(req)))
            req_name = req.get("name", "")
            req_desc = req.get("description", "")
            full_text = f"{req_name} {req_desc}".lower()

            # Check for vague terms
            ambiguities.extend(self._detect_vague_terms(req_id, full_text, req))

            # Check for unclear scope
            ambiguities.extend(self._detect_unclear_scope(req_id, full_text, req))

            # Check for missing details
            ambiguities.extend(self._detect_missing_details(req_id, full_text, req))

            # Check for technology choices
            ambiguities.extend(self._detect_technology_choices(req_id, full_text, req))

        # Check for conflicts across requirements
        ambiguities.extend(self._detect_conflicts(requirements))

        self.logger.info(
            "ambiguity_analysis_complete",
            total_requirements=len(requirements),
            ambiguities_found=len(ambiguities),
            high_severity=len([a for a in ambiguities if a.severity == AmbiguitySeverity.HIGH]),
        )

        return ambiguities

    def _generate_id(self) -> str:
        """Generate unique ambiguity ID."""
        self._ambiguity_counter += 1
        return f"AMB-{self._ambiguity_counter:04d}"

    def _detect_vague_terms(
        self,
        req_id: str,
        text: str,
        req: dict,
    ) -> list[DetectedAmbiguity]:
        """Detect vague terms that need clarification."""
        ambiguities = []

        for term, questions in VAGUE_TERMS.items():
            term_pattern = term.replace("_", r"[\s_-]?")
            if re.search(rf"\b{term_pattern}\b", text, re.IGNORECASE):
                ambiguities.append(
                    DetectedAmbiguity(
                        id=self._generate_id(),
                        requirement_id=req_id,
                        requirement_text=req.get("description", req.get("name", "")),
                        ambiguity_type=AmbiguityType.VAGUE_TERM,
                        description=f"'{term.replace('_', ' ')}' is vague and needs clarification",
                        severity=AmbiguitySeverity.MEDIUM,
                        detected_term=term,
                        suggested_questions=questions,
                    )
                )

        return ambiguities

    def _detect_unclear_scope(
        self,
        req_id: str,
        text: str,
        req: dict,
    ) -> list[DetectedAmbiguity]:
        """Detect unbounded/unclear scope patterns."""
        ambiguities = []

        for pattern in UNCLEAR_SCOPE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                matched_text = match.group()
                ambiguities.append(
                    DetectedAmbiguity(
                        id=self._generate_id(),
                        requirement_id=req_id,
                        requirement_text=req.get("description", req.get("name", "")),
                        ambiguity_type=AmbiguityType.UNCLEAR_SCOPE,
                        description=f"'{matched_text}' has unbounded scope",
                        severity=AmbiguitySeverity.HIGH,
                        detected_term=matched_text,
                        suggested_questions=[
                            "Can you list specific cases to handle?",
                            "What's the minimum viable scope?",
                            "Are there cases we can explicitly exclude?",
                        ],
                    )
                )

        return ambiguities

    def _detect_missing_details(
        self,
        req_id: str,
        text: str,
        req: dict,
    ) -> list[DetectedAmbiguity]:
        """Detect implied features missing details."""
        ambiguities = []

        for pattern, missing, questions in MISSING_DETAIL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                # Check if the detail is mentioned elsewhere in the text
                if missing.lower() not in text:
                    ambiguities.append(
                        DetectedAmbiguity(
                            id=self._generate_id(),
                            requirement_id=req_id,
                            requirement_text=req.get("description", req.get("name", "")),
                            ambiguity_type=AmbiguityType.MISSING_DETAIL,
                            description=f"'{missing}' is implied but not specified",
                            severity=AmbiguitySeverity.MEDIUM,
                            detected_term=missing,
                            suggested_questions=questions,
                        )
                    )

        return ambiguities

    def _detect_technology_choices(
        self,
        req_id: str,
        text: str,
        req: dict,
    ) -> list[DetectedAmbiguity]:
        """Detect places where technology choice is needed."""
        ambiguities = []

        for pattern, choice_desc, options in TECHNOLOGY_CHOICES:
            if re.search(pattern, text, re.IGNORECASE):
                # Check if a specific choice is already made
                specific_mentioned = any(
                    opt.lower().split()[0] in text for opt in options
                )
                if not specific_mentioned:
                    ambiguities.append(
                        DetectedAmbiguity(
                            id=self._generate_id(),
                            requirement_id=req_id,
                            requirement_text=req.get("description", req.get("name", "")),
                            ambiguity_type=AmbiguityType.TECHNOLOGY_CHOICE,
                            description=f"'{choice_desc}' has multiple valid approaches",
                            severity=AmbiguitySeverity.LOW,
                            detected_term=choice_desc,
                            suggested_questions=[
                                f"Which approach for {choice_desc}?",
                                "Any constraints or preferences?",
                            ],
                            context=f"Options: {', '.join(options)}",
                        )
                    )

        return ambiguities

    def _detect_conflicts(
        self,
        requirements: list[dict],
    ) -> list[DetectedAmbiguity]:
        """Detect conflicting requirements."""
        ambiguities = []

        # Known conflicting pairs
        conflict_pairs = [
            (r"real[\s-]?time", r"batch", "Real-time vs batch processing"),
            (r"simple", r"comprehensive", "Simple vs comprehensive"),
            (r"minimal", r"full[\s-]?featured", "Minimal vs full-featured"),
            (r"offline[\s-]?first", r"cloud[\s-]?native", "Offline-first vs cloud-native"),
            (r"no[\s-]?auth", r"authentication", "No auth vs authentication required"),
            (r"single[\s-]?page", r"ssr|server[\s-]?side", "SPA vs SSR"),
        ]

        all_text = " ".join(
            f"{r.get('name', '')} {r.get('description', '')}".lower()
            for r in requirements
        )

        for pattern1, pattern2, conflict_desc in conflict_pairs:
            if re.search(pattern1, all_text) and re.search(pattern2, all_text):
                ambiguities.append(
                    DetectedAmbiguity(
                        id=self._generate_id(),
                        requirement_id="GLOBAL",
                        requirement_text="Multiple requirements",
                        ambiguity_type=AmbiguityType.CONFLICT,
                        description=f"Potential conflict: {conflict_desc}",
                        severity=AmbiguitySeverity.HIGH,
                        suggested_questions=[
                            f"Which takes priority: {conflict_desc.split(' vs ')[0]} or {conflict_desc.split(' vs ')[1]}?",
                            "Can these requirements be reconciled?",
                        ],
                    )
                )

        return ambiguities

    def get_high_priority_ambiguities(
        self,
        ambiguities: list[DetectedAmbiguity],
    ) -> list[DetectedAmbiguity]:
        """Filter to only high priority ambiguities that need clarification."""
        return [a for a in ambiguities if a.severity == AmbiguitySeverity.HIGH]

    def should_pause_for_clarification(
        self,
        ambiguities: list[DetectedAmbiguity],
        threshold: int = 2,
    ) -> bool:
        """
        Determine if we should pause for user clarification.

        Returns True if:
        - Any HIGH severity ambiguities exist
        - More than threshold MEDIUM severity ambiguities exist
        """
        high_count = len([a for a in ambiguities if a.severity == AmbiguitySeverity.HIGH])
        medium_count = len([a for a in ambiguities if a.severity == AmbiguitySeverity.MEDIUM])

        return high_count > 0 or medium_count >= threshold

    def format_for_user(
        self,
        ambiguities: list[DetectedAmbiguity],
    ) -> str:
        """Format ambiguities as user-friendly text."""
        if not ambiguities:
            return "No ambiguities detected in requirements."

        lines = ["## Clarification Needed\n"]

        # Group by severity
        high = [a for a in ambiguities if a.severity == AmbiguitySeverity.HIGH]
        medium = [a for a in ambiguities if a.severity == AmbiguitySeverity.MEDIUM]
        low = [a for a in ambiguities if a.severity == AmbiguitySeverity.LOW]

        if high:
            lines.append("### Must Clarify (High Priority)\n")
            for a in high:
                lines.append(f"**{a.id}**: {a.description}")
                if a.suggested_questions:
                    lines.append("  Questions:")
                    for q in a.suggested_questions:
                        lines.append(f"  - {q}")
                lines.append("")

        if medium:
            lines.append("### Should Clarify (Medium Priority)\n")
            for a in medium:
                lines.append(f"**{a.id}**: {a.description}")
                if a.suggested_questions:
                    lines.append(f"  - {a.suggested_questions[0]}")
                lines.append("")

        if low:
            lines.append("### Optional (Low Priority)\n")
            for a in low:
                lines.append(f"**{a.id}**: {a.description}")
                if a.context:
                    lines.append(f"  {a.context}")
                lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # LLM-Enhanced Ambiguity Detection
    # -------------------------------------------------------------------------

    def _pattern_detect_ambiguity(self, req_text: str) -> ClassificationResult:
        """
        Pattern-based ambiguity detection.

        Args:
            req_text: Requirement text to analyze

        Returns:
            ClassificationResult with ambiguity type and confidence
        """
        text_lower = req_text.lower()
        detected = []
        scores = {
            "vague_term": 0,
            "unclear_scope": 0,
            "missing_detail": 0,
            "technology_choice": 0,
        }

        # Check vague terms
        for term in VAGUE_TERMS.keys():
            term_pattern = term.replace("_", r"[\s_-]?")
            if re.search(rf"\b{term_pattern}\b", text_lower):
                scores["vague_term"] += 1
                detected.append(f"vague:{term}")

        # Check unclear scope
        for pattern in UNCLEAR_SCOPE_PATTERNS:
            if re.search(pattern, text_lower):
                scores["unclear_scope"] += 1
                detected.append("unclear_scope")

        # Check missing details
        for pattern, missing, _ in MISSING_DETAIL_PATTERNS:
            if re.search(pattern, text_lower):
                if missing.lower() not in text_lower:
                    scores["missing_detail"] += 1
                    detected.append(f"missing:{missing}")

        # Check technology choices
        for pattern, choice, _ in TECHNOLOGY_CHOICES:
            if re.search(pattern, text_lower):
                scores["technology_choice"] += 1
                detected.append(f"tech:{choice}")

        # Determine primary ambiguity type
        if not detected:
            return ClassificationResult(
                category="none",
                confidence=0.9,
                source=ClassificationSource.PATTERN,
                metadata={"detected": [], "scores": scores},
            )

        # Get highest scoring type
        best_type = max(scores.keys(), key=lambda k: scores[k])
        total_score = sum(scores.values())
        confidence = min(0.9, 0.4 + (total_score * 0.15))

        return ClassificationResult(
            category=best_type,
            confidence=confidence,
            source=ClassificationSource.PATTERN,
            metadata={"detected": detected[:10], "scores": scores},
        )

    async def _llm_detect_ambiguity(self, req_text: str) -> ClassificationResult:
        """
        LLM-based context-aware ambiguity detection.

        Args:
            req_text: Requirement text to analyze

        Returns:
            ClassificationResult with ambiguity analysis
        """
        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            prompt = f"""Analyze this software requirement for ambiguities:

Requirement: {req_text[:600]}

Check for:
1. VAGUE_TERM: Undefined terms (e.g., "user management", "good performance")
2. UNCLEAR_SCOPE: Unbounded requirements (e.g., "handle all errors")
3. MISSING_DETAIL: Implied but unspecified features (e.g., payment without provider)
4. TECHNOLOGY_CHOICE: Multiple valid technical approaches
5. NONE: Requirement is clear and specific

Return JSON:
{{
  "ambiguity_type": "vague_term|unclear_scope|missing_detail|technology_choice|none",
  "confidence": 0.0-1.0,
  "detected_issues": ["list of specific issues found"],
  "suggested_questions": ["questions to clarify"]
}}
"""
            tool = ClaudeCodeTool(working_dir=".")
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.execute, prompt, skill_tier="minimal"),
                timeout=30.0,
            )

            if result:
                json_match = re.search(r'\{[^{}]*\}', str(result), re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    return ClassificationResult(
                        category=data.get("ambiguity_type", "none"),
                        confidence=data.get("confidence", 0.7),
                        source=ClassificationSource.LLM,
                        metadata={
                            "detected_issues": data.get("detected_issues", []),
                            "suggested_questions": data.get("suggested_questions", []),
                        },
                    )
        except Exception as e:
            self.logger.debug("llm_ambiguity_detection_failed", error=str(e))

        return ClassificationResult(
            category="none",
            confidence=0.3,
            source=ClassificationSource.LLM,
            metadata={"error": "LLM detection failed"},
        )

    async def analyze_requirement_async(
        self,
        req: dict,
        use_llm_fallback: bool = True,
    ) -> list[DetectedAmbiguity]:
        """
        Analyze a single requirement with LLM fallback.

        Args:
            req: Requirement dict with 'id', 'name', 'description'
            use_llm_fallback: Whether to use LLM for uncertain cases

        Returns:
            List of detected ambiguities
        """
        req_id = req.get("id", "unknown")
        req_name = req.get("name", "")
        req_desc = req.get("description", "")
        full_text = f"{req_name} {req_desc}"

        cache = get_classification_cache()
        key = cache._generate_key(full_text[:300], "ambiguity")

        # Check cache
        cached = await cache.get(key)
        if cached and cached.category == "none":
            return []

        # Pattern-based detection first
        pattern_result = self._pattern_detect_ambiguity(full_text)

        # If pattern detection has low confidence and LLM is enabled, use LLM
        if use_llm_fallback and pattern_result.confidence < 0.6 and pattern_result.category != "none":
            llm_result = await self._llm_detect_ambiguity(full_text)
            if llm_result.confidence > pattern_result.confidence:
                await cache.set(key, llm_result)
                return self._convert_llm_to_ambiguities(req, llm_result)

        await cache.set(key, pattern_result)

        # Convert to DetectedAmbiguity objects
        return self._convert_pattern_to_ambiguities(req, pattern_result)

    def _convert_pattern_to_ambiguities(
        self,
        req: dict,
        result: ClassificationResult,
    ) -> list[DetectedAmbiguity]:
        """Convert pattern classification result to DetectedAmbiguity list."""
        if result.category == "none":
            return []

        ambiguities = []
        detected = result.metadata.get("detected", [])

        for item in detected:
            if ":" in item:
                amb_type, term = item.split(":", 1)
            else:
                amb_type = item
                term = ""

            type_mapping = {
                "vague": AmbiguityType.VAGUE_TERM,
                "unclear_scope": AmbiguityType.UNCLEAR_SCOPE,
                "missing": AmbiguityType.MISSING_DETAIL,
                "tech": AmbiguityType.TECHNOLOGY_CHOICE,
            }

            amb_enum = type_mapping.get(amb_type, AmbiguityType.VAGUE_TERM)
            questions = VAGUE_TERMS.get(term, ["Please clarify this requirement."])

            ambiguities.append(
                DetectedAmbiguity(
                    id=self._generate_id(),
                    requirement_id=req.get("id", "unknown"),
                    requirement_text=req.get("description", req.get("name", "")),
                    ambiguity_type=amb_enum,
                    description=f"'{term}' needs clarification" if term else "Ambiguity detected",
                    severity=AmbiguitySeverity.MEDIUM,
                    detected_term=term,
                    suggested_questions=questions[:3],
                )
            )

        return ambiguities

    def _convert_llm_to_ambiguities(
        self,
        req: dict,
        result: ClassificationResult,
    ) -> list[DetectedAmbiguity]:
        """Convert LLM classification result to DetectedAmbiguity list."""
        if result.category == "none":
            return []

        type_mapping = {
            "vague_term": AmbiguityType.VAGUE_TERM,
            "unclear_scope": AmbiguityType.UNCLEAR_SCOPE,
            "missing_detail": AmbiguityType.MISSING_DETAIL,
            "technology_choice": AmbiguityType.TECHNOLOGY_CHOICE,
        }

        amb_type = type_mapping.get(result.category, AmbiguityType.VAGUE_TERM)
        detected_issues = result.metadata.get("detected_issues", [])
        suggested_questions = result.metadata.get("suggested_questions", [])

        ambiguities = []
        for issue in detected_issues[:5]:
            ambiguities.append(
                DetectedAmbiguity(
                    id=self._generate_id(),
                    requirement_id=req.get("id", "unknown"),
                    requirement_text=req.get("description", req.get("name", "")),
                    ambiguity_type=amb_type,
                    description=issue,
                    severity=AmbiguitySeverity.MEDIUM if result.confidence > 0.7 else AmbiguitySeverity.LOW,
                    detected_term="",
                    suggested_questions=suggested_questions[:3],
                )
            )

        return ambiguities if ambiguities else [
            DetectedAmbiguity(
                id=self._generate_id(),
                requirement_id=req.get("id", "unknown"),
                requirement_text=req.get("description", req.get("name", "")),
                ambiguity_type=amb_type,
                description=f"Detected {result.category.replace('_', ' ')}",
                severity=AmbiguitySeverity.MEDIUM,
                detected_term="",
                suggested_questions=suggested_questions[:3] or ["Please clarify this requirement."],
            )
        ]

    async def analyze_async(
        self,
        requirements: list[dict],
        use_llm_fallback: bool = True,
    ) -> list[DetectedAmbiguity]:
        """
        Analyze requirements for ambiguities with LLM enhancement.

        Args:
            requirements: List of requirement dicts
            use_llm_fallback: Whether to use LLM for uncertain cases

        Returns:
            List of detected ambiguities
        """
        ambiguities: list[DetectedAmbiguity] = []

        for req in requirements:
            req_ambiguities = await self.analyze_requirement_async(req, use_llm_fallback)
            ambiguities.extend(req_ambiguities)

        # Also run standard conflict detection
        ambiguities.extend(self._detect_conflicts(requirements))

        self.logger.info(
            "async_ambiguity_analysis_complete",
            total_requirements=len(requirements),
            ambiguities_found=len(ambiguities),
            high_severity=len([a for a in ambiguities if a.severity == AmbiguitySeverity.HIGH]),
        )

        return ambiguities

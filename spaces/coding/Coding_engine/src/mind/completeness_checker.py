"""
Completeness Checker - Verifies all requirements have been implemented.

Parses original requirements JSON and checks:
1. Each requirement has corresponding implementation (code exists)
2. Each requirement has test coverage (test exists)
3. Each requirement works (tests pass)

Generates a traceability matrix: requirement → code → test → status

LLM-Based Verification (NEW):
When enable_llm_verification=True, uses the VerificationDebateAgent with
Multi-Agent Debate pattern for more accurate verification.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class RequirementStatus(Enum):
    """Status of a requirement's implementation."""
    NOT_STARTED = "not_started"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    IMPLEMENTED = "implemented"
    TESTED = "tested"
    VERIFIED = "verified"  # Tests pass
    FAILED = "failed"      # Tests fail


@dataclass
class RequirementTrace:
    """Traceability for a single requirement."""
    requirement_id: str
    description: str
    status: RequirementStatus = RequirementStatus.NOT_STARTED

    # Implementation tracking
    related_files: list[str] = field(default_factory=list)
    related_functions: list[str] = field(default_factory=list)

    # Test tracking
    test_files: list[str] = field(default_factory=list)
    test_names: list[str] = field(default_factory=list)
    tests_passing: int = 0
    tests_failing: int = 0

    # Notes
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id,
            "description": self.description,
            "status": self.status.value,
            "related_files": self.related_files,
            "related_functions": self.related_functions,
            "test_files": self.test_files,
            "test_names": self.test_names,
            "tests_passing": self.tests_passing,
            "tests_failing": self.tests_failing,
            "notes": self.notes,
        }


@dataclass
class CompletenessResult:
    """Result of completeness check."""
    total_requirements: int = 0
    implemented: int = 0
    tested: int = 0
    verified: int = 0
    failed: int = 0
    not_started: int = 0

    completeness_score: float = 0.0  # 0-100

    traces: list[RequirementTrace] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_requirements": self.total_requirements,
            "implemented": self.implemented,
            "tested": self.tested,
            "verified": self.verified,
            "failed": self.failed,
            "not_started": self.not_started,
            "completeness_score": self.completeness_score,
            "missing_requirements": self.missing_requirements,
            "traces": [t.to_dict() for t in self.traces],
            "errors": self.errors,
        }


class CompletenessChecker:
    """
    Checks that all requirements have been implemented and tested.

    Works by:
    1. Parsing requirements from JSON
    2. Scanning code for implementation evidence
    3. Scanning tests for coverage
    4. Matching tests to requirements
    """

    def __init__(self, working_dir: str):
        self.working_dir = Path(working_dir)
        self.logger = logger.bind(component="completeness_checker")

    def check(
        self,
        requirements: dict,
        test_results: Optional[dict] = None,
    ) -> CompletenessResult:
        """
        Check completeness of implementation.

        Args:
            requirements: Parsed requirements dict
            test_results: Optional test execution results

        Returns:
            CompletenessResult with traceability info
        """
        result = CompletenessResult()

        try:
            # Extract all requirements
            req_items = self._extract_requirements(requirements)
            result.total_requirements = len(req_items)

            # Scan code files
            code_files = self._scan_code_files()

            # Scan test files
            test_files = self._scan_test_files()

            # Create traces for each requirement
            for req_id, req_desc in req_items:
                trace = RequirementTrace(
                    requirement_id=req_id,
                    description=req_desc,
                )

                # Find related code files
                self._find_related_code(trace, code_files)

                # Find related tests
                self._find_related_tests(trace, test_files)

                # Determine status
                self._determine_status(trace, test_results)

                result.traces.append(trace)

                # Update counts
                if trace.status == RequirementStatus.NOT_STARTED:
                    result.not_started += 1
                    result.missing_requirements.append(req_desc[:100])
                elif trace.status == RequirementStatus.VERIFIED:
                    result.verified += 1
                    result.implemented += 1
                    result.tested += 1
                elif trace.status == RequirementStatus.TESTED:
                    result.tested += 1
                    result.implemented += 1
                elif trace.status == RequirementStatus.IMPLEMENTED:
                    result.implemented += 1
                elif trace.status == RequirementStatus.FAILED:
                    result.failed += 1
                    result.implemented += 1
                    result.tested += 1

            # Calculate completeness score
            if result.total_requirements > 0:
                # Weight: verified=100%, implemented+tested=80%, implemented=50%, failed=30%
                score = (
                    result.verified * 100 +
                    (result.tested - result.verified - result.failed) * 80 +
                    (result.implemented - result.tested) * 50 +
                    result.failed * 30
                ) / result.total_requirements
                result.completeness_score = round(score, 1)

        except Exception as e:
            result.errors.append(str(e))
            self.logger.error("completeness_check_failed", error=str(e))

        self.logger.info(
            "completeness_check_complete",
            total=result.total_requirements,
            verified=result.verified,
            score=result.completeness_score,
        )

        return result

    def _extract_requirements(self, requirements: dict) -> list[tuple[str, str]]:
        """Extract requirement ID and description pairs."""
        items = []

        # Handle different requirement formats
        if "requirements" in requirements:
            reqs = requirements["requirements"]
            if isinstance(reqs, list):
                for i, req in enumerate(reqs):
                    if isinstance(req, str):
                        items.append((f"REQ-{i+1:03d}", req))
                    elif isinstance(req, dict):
                        req_id = req.get("id", f"REQ-{i+1:03d}")
                        desc = req.get("description", req.get("name", str(req)))
                        items.append((req_id, desc))
            elif isinstance(reqs, dict):
                for key, value in reqs.items():
                    if isinstance(value, str):
                        items.append((key, value))
                    elif isinstance(value, dict):
                        desc = value.get("description", str(value))
                        items.append((key, desc))

        # Also check for features, user_stories, etc.
        for key in ["features", "user_stories", "stories", "specs"]:
            if key in requirements:
                features = requirements[key]
                if isinstance(features, list):
                    for i, feat in enumerate(features):
                        if isinstance(feat, str):
                            items.append((f"FEAT-{i+1:03d}", feat))
                        elif isinstance(feat, dict):
                            feat_id = feat.get("id", f"FEAT-{i+1:03d}")
                            desc = feat.get("description", feat.get("name", str(feat)))
                            items.append((feat_id, desc))

        return items

    def _scan_code_files(self) -> dict[str, str]:
        """Scan code files and return path -> content mapping."""
        files = {}

        extensions = [".ts", ".tsx", ".js", ".jsx", ".py", ".java", ".go", ".rs"]
        exclude_dirs = ["node_modules", ".git", "dist", "build", "__pycache__"]

        for ext in extensions:
            for file_path in self.working_dir.rglob(f"*{ext}"):
                # Skip excluded directories
                if any(excl in str(file_path) for excl in exclude_dirs):
                    continue
                # Skip test files here
                if "test" in file_path.name.lower() or "spec" in file_path.name.lower():
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    rel_path = str(file_path.relative_to(self.working_dir))
                    files[rel_path] = content
                except Exception:
                    pass

        return files

    def _scan_test_files(self) -> dict[str, str]:
        """Scan test files and return path -> content mapping."""
        files = {}

        patterns = ["*test*.ts", "*test*.tsx", "*test*.js", "*test*.py",
                   "*spec*.ts", "*spec*.tsx", "*spec*.js"]
        exclude_dirs = ["node_modules", ".git", "dist", "build", "__pycache__"]

        for pattern in patterns:
            for file_path in self.working_dir.rglob(pattern):
                if any(excl in str(file_path) for excl in exclude_dirs):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    rel_path = str(file_path.relative_to(self.working_dir))
                    files[rel_path] = content
                except Exception:
                    pass

        return files

    def _find_related_code(
        self,
        trace: RequirementTrace,
        code_files: dict[str, str],
    ) -> None:
        """Find code files related to a requirement."""
        keywords = self._extract_keywords(trace.description)

        for file_path, content in code_files.items():
            content_lower = content.lower()

            # Check if any keyword appears in the file
            matches = sum(1 for kw in keywords if kw in content_lower)

            if matches >= 2 or (matches >= 1 and len(keywords) <= 3):
                trace.related_files.append(file_path)

                # Try to find related functions
                functions = self._find_functions(content, keywords)
                trace.related_functions.extend(functions)

    def _find_related_tests(
        self,
        trace: RequirementTrace,
        test_files: dict[str, str],
    ) -> None:
        """Find test files related to a requirement."""
        keywords = self._extract_keywords(trace.description)

        for file_path, content in test_files.items():
            content_lower = content.lower()

            # Check if any keyword appears in the test
            matches = sum(1 for kw in keywords if kw in content_lower)

            if matches >= 1:
                trace.test_files.append(file_path)

                # Extract test names
                test_names = self._extract_test_names(content)
                for name in test_names:
                    if any(kw in name.lower() for kw in keywords):
                        trace.test_names.append(name)

    def _extract_keywords(self, description: str) -> list[str]:
        """Extract meaningful keywords from a requirement description."""
        # Remove common words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "to", "of", "in", "for", "on", "with", "at",
            "by", "from", "as", "into", "through", "during", "before",
            "after", "above", "below", "between", "under", "again", "further",
            "then", "once", "here", "there", "when", "where", "why", "how",
            "all", "each", "few", "more", "most", "other", "some", "such",
            "no", "nor", "not", "only", "own", "same", "so", "than", "too",
            "very", "just", "and", "but", "if", "or", "because", "until",
            "while", "user", "users", "system", "application", "app",
            "feature", "functionality", "ability", "able", "allow", "allows",
        }

        # Extract words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', description.lower())

        # Filter and return unique keywords
        keywords = [w for w in words if w not in stop_words]
        return list(set(keywords))[:10]  # Max 10 keywords

    def _find_functions(self, content: str, keywords: list[str]) -> list[str]:
        """Find function names in code that match keywords."""
        functions = []

        # Match function/method definitions
        patterns = [
            r'function\s+(\w+)',           # JS function
            r'const\s+(\w+)\s*=\s*\(',     # JS arrow function
            r'def\s+(\w+)\s*\(',           # Python function
            r'async\s+(\w+)\s*\(',         # Async function
            r'(\w+)\s*\([^)]*\)\s*{',      # Method
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if any(kw in match.lower() for kw in keywords):
                    functions.append(match)

        return list(set(functions))[:5]

    def _extract_test_names(self, content: str) -> list[str]:
        """Extract test names from test file content."""
        test_names = []

        # Match test definitions
        patterns = [
            r'(?:it|test|describe)\s*\(\s*[\'"]([^\'"]+)[\'"]',  # Jest/Mocha
            r'def\s+(test_\w+)',                                  # Python pytest
            r'@Test.*?\n\s*(?:public\s+)?void\s+(\w+)',          # Java JUnit
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            test_names.extend(matches)

        return test_names

    def _determine_status(
        self,
        trace: RequirementTrace,
        test_results: Optional[dict],
    ) -> None:
        """Determine the implementation status of a requirement."""
        has_code = len(trace.related_files) > 0
        has_tests = len(trace.test_files) > 0 or len(trace.test_names) > 0

        if not has_code:
            trace.status = RequirementStatus.NOT_STARTED
            trace.notes.append("No related code files found")
            return

        if not has_tests:
            trace.status = RequirementStatus.IMPLEMENTED
            trace.notes.append("No tests found for this requirement")
            return

        # Check test results if available
        if test_results:
            passing = 0
            failing = 0

            for test_name in trace.test_names:
                if test_name in test_results.get("passed", []):
                    passing += 1
                elif test_name in test_results.get("failed", []):
                    failing += 1

            trace.tests_passing = passing
            trace.tests_failing = failing

            if failing > 0:
                trace.status = RequirementStatus.FAILED
                trace.notes.append(f"{failing} test(s) failing")
            elif passing > 0:
                trace.status = RequirementStatus.VERIFIED
                trace.notes.append(f"{passing} test(s) passing")
            else:
                trace.status = RequirementStatus.TESTED
                trace.notes.append("Tests exist but no results available")
        else:
            trace.status = RequirementStatus.TESTED
            trace.notes.append("Test results not provided")


    async def check_with_llm(
        self,
        requirements: dict,
        event_bus: Optional[Any] = None,
        shared_state: Optional[Any] = None,
        num_debate_rounds: int = 3,
    ) -> CompletenessResult:
        """
        Check completeness using LLM-based Multi-Agent Debate verification.

        This uses the VerificationDebateAgent to have multiple solver agents
        (Implementation, Testing, Deployment) debate each requirement's
        verification status.

        Args:
            requirements: Parsed requirements dict
            event_bus: Optional EventBus for agent communication
            shared_state: Optional SharedState for metrics
            num_debate_rounds: Number of debate rounds (default: 3)

        Returns:
            CompletenessResult with LLM-based verification
        """
        self.logger.info("starting_llm_verification")

        result = CompletenessResult()

        try:
            # Import here to avoid circular imports
            from ..agents.verification_debate_agent import (
                VerificationDebateAgent,
                VerificationVerdict,
            )
            from .event_bus import EventBus
            from .shared_state import SharedState

            # Create EventBus and SharedState if not provided
            if event_bus is None:
                event_bus = EventBus()
            if shared_state is None:
                shared_state = SharedState()

            # Extract requirements list
            req_items = self._extract_requirements(requirements)
            result.total_requirements = len(req_items)

            # Convert to dict format for VerificationDebateAgent
            req_dicts = [
                {"id": req_id, "description": req_desc}
                for req_id, req_desc in req_items
            ]

            # Create and run verification agent
            verification_agent = VerificationDebateAgent(
                name="CompletenessVerification",
                event_bus=event_bus,
                shared_state=shared_state,
                working_dir=str(self.working_dir),
                requirements=req_dicts,
                num_debate_rounds=num_debate_rounds,
            )

            # Start the agent
            await verification_agent.start()

            # Manually trigger verification
            from .event_bus import Event, EventType
            verification_event = Event(
                type=EventType.VERIFICATION_STARTED,
                source="CompletenessChecker",
                data={"requirements": req_dicts},
            )

            # Run the verification
            result_event = await verification_agent.act([verification_event])

            # Stop the agent
            await verification_agent.stop()

            # Process results
            if result_event and result_event.data:
                data = result_event.data
                result.verified = data.get("verified_count", 0)
                result.failed = data.get("failed_count", 0)

                # Map debate results to traces
                debate_results = data.get("results", [])
                for debate_result in debate_results:
                    req_id = debate_result.get("requirement_id", "")
                    verdict = debate_result.get("verdict", "")

                    # Find matching requirement
                    for req_id_orig, req_desc in req_items:
                        if req_id_orig == req_id or req_id in str(req_id_orig):
                            trace = RequirementTrace(
                                requirement_id=req_id_orig,
                                description=req_desc,
                            )

                            # Set status based on verdict
                            if verdict == "verified":
                                trace.status = RequirementStatus.VERIFIED
                            elif verdict == "failed":
                                trace.status = RequirementStatus.FAILED
                                result.missing_requirements.append(req_desc[:100])
                            elif verdict == "needs_more":
                                trace.status = RequirementStatus.PARTIALLY_IMPLEMENTED
                            else:
                                trace.status = RequirementStatus.NOT_STARTED

                            # Add LLM reasoning to notes
                            solver_responses = debate_result.get("solver_responses", [])
                            for solver_resp in solver_responses[:3]:  # Limit to first 3
                                trace.notes.append(
                                    f"[{solver_resp.get('perspective', 'Unknown')}]: "
                                    f"{solver_resp.get('reasoning', '')[:200]}..."
                                )

                            result.traces.append(trace)
                            break

                # Update counts
                result.implemented = result.verified
                result.tested = result.verified + result.failed
                result.not_started = result.total_requirements - result.verified - result.failed

            # Calculate score
            if result.total_requirements > 0:
                score = (result.verified * 100 + result.failed * 30) / result.total_requirements
                result.completeness_score = round(score, 1)

        except Exception as e:
            result.errors.append(f"LLM verification failed: {str(e)}")
            self.logger.error("llm_verification_failed", error=str(e))

            # Fallback to static check
            self.logger.info("falling_back_to_static_check")
            return self.check(requirements)

        self.logger.info(
            "llm_verification_complete",
            total=result.total_requirements,
            verified=result.verified,
            score=result.completeness_score,
        )

        return result


async def check_completeness(
    working_dir: str,
    requirements: dict,
    test_results: Optional[dict] = None,
    use_llm: bool = False,
    event_bus: Optional[Any] = None,
    shared_state: Optional[Any] = None,
    num_debate_rounds: int = 3,
) -> CompletenessResult:
    """
    Convenience function to check implementation completeness.

    Args:
        working_dir: Project working directory
        requirements: Parsed requirements dict
        test_results: Optional test execution results
        use_llm: Use LLM-based Multi-Agent Debate verification (default: False)
        event_bus: Optional EventBus for LLM verification
        shared_state: Optional SharedState for LLM verification
        num_debate_rounds: Number of debate rounds for LLM verification

    Returns:
        CompletenessResult with traceability
    """
    checker = CompletenessChecker(working_dir)

    if use_llm:
        return await checker.check_with_llm(
            requirements,
            event_bus=event_bus,
            shared_state=shared_state,
            num_debate_rounds=num_debate_rounds,
        )
    else:
        return checker.check(requirements, test_results)

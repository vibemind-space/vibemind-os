"""
Validation Team - Parallel Validation Society of Mind Pattern

A team agent that runs multiple validation agents in parallel
to verify actions and screen states from different perspectives.

Multiple validators checking the same thing increases confidence
and catches errors a single agent might miss.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseHandoffAgent, AgentConfig
from .messages import UserTask, AgentResponse
from .team_agent import TeamAgent, TeamConfig, SubAgentResult, SynthesisStrategy

logger = logging.getLogger(__name__)


class ElementFinderAgent(BaseHandoffAgent):
    """
    Agent that finds UI elements using OCR/text matching.

    Returns coordinates if found, or failure with details.
    """

    def __init__(self):
        config = AgentConfig(
            name="element_finder",
            description="Finds UI elements via text/OCR",
            topic_type="validation"
        )
        super().__init__(config)

    def _register_default_tools(self):
        pass

    async def _process_task(self, task: UserTask) -> Any:
        """Find a UI element."""
        target = task.context.get("find_target", "")
        method = task.context.get("find_method", "ocr")

        await self.report_progress(task, 50.0, f"Finding: {target}")

        # Simulate OCR-based finding (would connect to MoireServer)
        result = await self._find_element(target, method)

        await self.report_progress(task, 100.0, "Search complete")

        return result

    async def _find_element(self, target: str, method: str) -> Dict[str, Any]:
        """
        Find element by text using MoireServer OCR.

        No heuristic fallback - if we can't find it, we say so honestly.
        """
        try:
            from bridge.websocket_client import MoireWebSocketClient

            client = MoireWebSocketClient(host="localhost", port=8766)
            connected = await client.connect()

            if not connected:
                return {
                    "found": False,
                    "confidence": 0.0,
                    "method": "error",
                    "error": "MoireServer not available"
                }

            try:
                # Capture screen and wait for OCR
                result = await client.capture_and_wait_for_complete(timeout=30.0)

                if not result.success or not result.ui_context:
                    return {
                        "found": False,
                        "confidence": 0.0,
                        "method": "error",
                        "error": "Screen capture failed"
                    }

                # Search for element by text
                element = client.find_element_by_text(target, exact=False)

                if element:
                    x, y = client.get_clickable_center(element)
                    return {
                        "found": True,
                        "x": x,
                        "y": y,
                        "confidence": element.confidence,
                        "method": "moire_ocr",
                        "matched_text": element.text
                    }

                # Element not found - be honest about it
                return {
                    "found": False,
                    "confidence": 0.0,
                    "method": "not_found",
                    "error": f"No element matching '{target}' found on screen"
                }

            finally:
                await client.disconnect()

        except Exception as e:
            logger.warning(f"MoireServer find failed: {e}")
            return {
                "found": False,
                "confidence": 0.0,
                "method": "error",
                "error": str(e)
            }


class ScreenStateValidator(BaseHandoffAgent):
    """
    Agent that validates screen state matches expectations.

    Checks if expected elements are present and in expected states.
    """

    def __init__(self):
        config = AgentConfig(
            name="screen_validator",
            description="Validates screen state",
            topic_type="validation"
        )
        super().__init__(config)

    def _register_default_tools(self):
        pass

    async def _process_task(self, task: UserTask) -> Any:
        """Validate screen state."""
        expected = task.context.get("expected_state", {})
        screen_data = task.context.get("screen_data", {})

        await self.report_progress(task, 50.0, "Validating screen state...")

        validation = self._validate_state(expected, screen_data)

        await self.report_progress(task, 100.0, "Validation complete")

        return validation

    def _validate_state(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate that actual screen state matches expected.

        Args:
            expected: Expected state (elements, text, etc.)
            actual: Actual captured state

        Returns:
            Validation result with matches and mismatches
        """
        matches = []
        mismatches = []
        confidence = 1.0

        # Check expected elements
        expected_elements = expected.get("elements", [])
        actual_elements = actual.get("elements", [])

        for elem in expected_elements:
            elem_name = elem.get("name", "unknown")
            found = any(
                self._element_matches(elem, actual_elem)
                for actual_elem in actual_elements
            )

            if found:
                matches.append(f"Found: {elem_name}")
            else:
                mismatches.append(f"Missing: {elem_name}")
                confidence -= 0.2

        # Check expected text
        expected_text = expected.get("text", [])
        actual_text = actual.get("text", [])

        for text in expected_text:
            if any(text.lower() in t.lower() for t in actual_text):
                matches.append(f"Text found: {text}")
            else:
                mismatches.append(f"Text missing: {text}")
                confidence -= 0.15

        return {
            "valid": len(mismatches) == 0,
            "confidence": max(0.0, confidence),
            "matches": matches,
            "mismatches": mismatches,
            "checked_elements": len(expected_elements),
            "checked_text": len(expected_text)
        }

    def _element_matches(self, expected: Dict, actual: Dict) -> bool:
        """Check if an actual element matches expected criteria."""
        # Simple matching - could be more sophisticated
        if expected.get("type") and expected["type"] != actual.get("type"):
            return False
        if expected.get("text") and expected["text"].lower() not in actual.get("text", "").lower():
            return False
        return True


class ChangeDetector(BaseHandoffAgent):
    """
    Agent that detects changes between screen states.

    Compares before/after to verify actions had expected effect.
    """

    def __init__(self):
        config = AgentConfig(
            name="change_detector",
            description="Detects screen changes",
            topic_type="validation"
        )
        super().__init__(config)

    def _register_default_tools(self):
        pass

    async def _process_task(self, task: UserTask) -> Any:
        """Detect changes between states."""
        before = task.context.get("state_before", {})
        after = task.context.get("state_after", {})
        expected_change = task.context.get("expected_change", "")

        await self.report_progress(task, 50.0, "Detecting changes...")

        changes = self._detect_changes(before, after, expected_change)

        await self.report_progress(task, 100.0, "Detection complete")

        return changes

    def _detect_changes(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        expected: str
    ) -> Dict[str, Any]:
        """
        Detect what changed between before and after states.

        Args:
            before: Screen state before action
            after: Screen state after action
            expected: Description of expected change

        Returns:
            Change detection result
        """
        changes = []
        expected_detected = False

        # Compare text content
        before_text = set(before.get("text", []))
        after_text = set(after.get("text", []))

        added_text = after_text - before_text
        removed_text = before_text - after_text

        if added_text:
            changes.append(f"Text added: {list(added_text)[:3]}")
        if removed_text:
            changes.append(f"Text removed: {list(removed_text)[:3]}")

        # Compare element counts
        before_count = len(before.get("elements", []))
        after_count = len(after.get("elements", []))

        if after_count != before_count:
            diff = after_count - before_count
            changes.append(f"Element count changed: {'+' if diff > 0 else ''}{diff}")

        # Check if expected change detected
        expected_lower = expected.lower()
        if expected_lower:
            if "message sent" in expected_lower:
                # Look for sending indicators
                if added_text or after_count != before_count:
                    expected_detected = True
            elif "window opened" in expected_lower:
                if after_count > before_count:
                    expected_detected = True
            elif "text entered" in expected_lower:
                if added_text:
                    expected_detected = True

        return {
            "changes_detected": len(changes) > 0,
            "changes": changes,
            "expected_change": expected,
            "expected_detected": expected_detected,
            "added_text_count": len(added_text),
            "removed_text_count": len(removed_text)
        }


class ValidationTeam(TeamAgent):
    """
    Team that runs multiple validators in parallel.

    Combines:
    - ElementFinderAgent: Locates UI elements
    - ScreenStateValidator: Validates screen matches expectations
    - ChangeDetector: Detects changes after actions

    All run in parallel, then results are synthesized.
    Higher confidence when multiple validators agree.
    """

    def __init__(self, confidence_threshold: float = 0.7):
        config = TeamConfig(
            name="validation_team",
            description="Parallel validation team",
            topic_type="validation",
            synthesis_strategy=SynthesisStrategy.CUSTOM,  # Use our custom _synthesize
            parallel_execution=True,  # Run validators in parallel
            timeout_per_agent=15.0
        )
        super().__init__(config)

        self.confidence_threshold = confidence_threshold

        # Add validators
        self.element_finder = ElementFinderAgent()
        self.state_validator = ScreenStateValidator()
        self.change_detector = ChangeDetector()

        self.add_member(self.element_finder, weight=1.0)
        self.add_member(self.state_validator, weight=0.9)
        self.add_member(self.change_detector, weight=0.8)

        # Set custom synthesizer
        self.set_synthesizer(self._custom_validation_synthesize)

    async def _custom_validation_synthesize(
        self,
        results: List[SubAgentResult],
        task: UserTask
    ) -> Dict[str, Any]:
        """Custom synthesizer that wraps _synthesize."""
        return await self._synthesize(results)

    async def _synthesize(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """
        Synthesize validation results from all validators.

        Combines confidence scores and aggregates findings.
        """
        findings = {
            "element_finder": None,
            "screen_validator": None,
            "change_detector": None
        }

        total_confidence = 0.0
        total_weight = 0.0

        for result in results:
            if result.response.success:
                findings[result.agent_name] = result.response.result

                # Weight the confidence
                confidence = result.response.result.get("confidence", 0.5)
                total_confidence += confidence * result.weight
                total_weight += result.weight

        # Calculate overall confidence
        overall_confidence = total_confidence / total_weight if total_weight > 0 else 0.0

        # Determine validation success
        valid = overall_confidence >= self.confidence_threshold

        # Aggregate issues
        issues = []
        if findings["screen_validator"]:
            issues.extend(findings["screen_validator"].get("mismatches", []))

        # Get best element location
        element_location = None
        if findings["element_finder"] and findings["element_finder"].get("found"):
            element_location = {
                "x": findings["element_finder"]["x"],
                "y": findings["element_finder"]["y"]
            }

        # Check changes
        changes_detected = False
        if findings["change_detector"]:
            changes_detected = findings["change_detector"].get("changes_detected", False)

        return {
            "success": valid,
            "valid": valid,
            "overall_confidence": overall_confidence,
            "threshold": self.confidence_threshold,
            "element_location": element_location,
            "changes_detected": changes_detected,
            "issues": issues,
            "detailed_results": {
                name: findings[name]
                for name in findings if findings[name]
            },
            "validators_succeeded": sum(1 for r in results if r.response.success),
            "validators_total": len(results)
        }

    async def validate_element(
        self,
        target: str,
        expected_state: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Convenience method to validate an element exists.

        Args:
            target: Element to find
            expected_state: Optional expected screen state

        Returns:
            Validation result with location if found
        """
        task = UserTask(
            goal=f"Validate element: {target}",
            context={
                "find_target": target,
                "expected_state": expected_state or {}
            }
        )

        return await self._process_task(task)

    async def validate_action(
        self,
        before_state: Dict,
        after_state: Dict,
        expected_change: str
    ) -> Dict[str, Any]:
        """
        Validate that an action had the expected effect.

        Args:
            before_state: Screen state before action
            after_state: Screen state after action
            expected_change: Description of expected change

        Returns:
            Validation result
        """
        task = UserTask(
            goal=f"Validate action: {expected_change}",
            context={
                "state_before": before_state,
                "state_after": after_state,
                "expected_change": expected_change
            }
        )

        return await self._process_task(task)

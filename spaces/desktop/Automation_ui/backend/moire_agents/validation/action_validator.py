"""
Action Validator - Validiert Aktionsergebnisse mit Timeout

Workflow:
1. Screenshot vor der Aktion speichern
2. Aktion ausführen
3. In Loop bis Timeout: Screenshots vergleichen
4. Bei Änderung: Bestätigung
5. Bei Timeout: Fehlschlag melden
"""

import asyncio
import logging
import time
import sys
import os
from typing import Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation.state_comparator import StateComparator, ScreenState, ComparisonResult, ChangeType, get_state_comparator
from core.event_queue import ActionEvent, ValidationEvent
from core.openrouter_client import OpenRouterClient, get_openrouter_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Detailliertes Validierungsergebnis."""
    success: bool
    confidence: float
    description: str
    change_detected: bool
    change_type: ChangeType
    change_percentage: float
    duration_ms: float
    attempts: int
    screenshot_before: Optional[bytes] = None
    screenshot_after: Optional[bytes] = None


class ActionValidator:
    """
    Validiert ob eine Aktion das erwartete Ergebnis hatte.
    
    Features:
    - Timeout-basiertes Warten auf Bildschirmänderung
    - Pixel- und Element-basierter Vergleich
    - LLM-basierte semantische Validierung (optional)
    """
    
    def __init__(
        self,
        comparator: Optional[StateComparator] = None,
        openrouter_client: Optional[OpenRouterClient] = None,
        default_timeout: float = 5.0,
        check_interval: float = 0.3,
        use_llm_validation: bool = True
    ):
        self.comparator = comparator or get_state_comparator()
        self.client = openrouter_client or get_openrouter_client()
        self.default_timeout = default_timeout
        self.check_interval = check_interval
        self.use_llm_validation = use_llm_validation
        
        # Screenshot capture callback
        self._capture_screenshot: Optional[Callable[[], Awaitable[bytes]]] = None
        self._get_screen_state: Optional[Callable[[], Awaitable[Dict[str, Any]]]] = None
        
        # Stats
        self._validations_total = 0
        self._validations_success = 0
    
    def set_screenshot_callback(self, callback: Callable[[], Awaitable[bytes]]):
        """Setzt die Callback-Funktion für Screenshot-Capture."""
        self._capture_screenshot = callback
    
    def set_screen_state_callback(self, callback: Callable[[], Awaitable[Dict[str, Any]]]):
        """Setzt die Callback-Funktion für Screen-State."""
        self._get_screen_state = callback
    
    async def validate_action(
        self,
        action: ActionEvent,
        expected_change: Optional[str] = None,
        timeout: Optional[float] = None,
        require_change: bool = True
    ) -> ValidationResult:
        """
        Validiert eine ausgeführte Aktion.
        
        Args:
            action: Die ausgeführte Aktion
            expected_change: Beschreibung der erwarteten Änderung
            timeout: Timeout in Sekunden
            require_change: Ob eine Bildschirmänderung erforderlich ist
        
        Returns:
            ValidationResult
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()
        self._validations_total += 1
        
        # Bestimme erwartete Änderung basierend auf Aktion
        if not expected_change:
            expected_change = self._infer_expected_change(action)
        
        # Für wait-Aktionen: Kein Vergleich nötig
        if action.action_type == "wait":
            duration_ms = (time.time() - start_time) * 1000
            self._validations_success += 1
            return ValidationResult(
                success=True,
                confidence=1.0,
                description="Wait completed",
                change_detected=False,
                change_type=ChangeType.NO_CHANGE,
                change_percentage=0.0,
                duration_ms=duration_ms,
                attempts=0
            )
        
        # Capture Screenshot vor der Aktion (sollte bereits vorhanden sein)
        screenshot_before = action.screenshot_before
        if not screenshot_before and self._capture_screenshot:
            screenshot_before = await self._capture_screenshot()
        
        if not screenshot_before:
            logger.warning("No screenshot before action available")
            # Ohne Vorher-Screenshot können wir nur optimistisch validieren
            return ValidationResult(
                success=True,
                confidence=0.5,
                description="Validation skipped - no reference screenshot",
                change_detected=False,
                change_type=ChangeType.NO_CHANGE,
                change_percentage=0.0,
                duration_ms=(time.time() - start_time) * 1000,
                attempts=0
            )
        
        # Erstelle Referenz-State
        reference_state = ScreenState.from_screenshot(screenshot_before)
        
        # Warte auf Änderung mit Timeout
        attempts = 0
        last_comparison: Optional[ComparisonResult] = None
        screenshot_after: Optional[bytes] = None
        
        while time.time() - start_time < timeout:
            attempts += 1
            
            # Capture aktuellen Screenshot
            if self._capture_screenshot:
                screenshot_after = await self._capture_screenshot()
            else:
                # Ohne Capture-Callback können wir nicht validieren
                break
            
            # Vergleiche mit Referenz - nutze ROI wenn vorhanden
            roi = getattr(action, 'roi', None)

            if roi and screenshot_before:
                # ROI-basierter Vergleich für fokussierte Validierung
                last_comparison = self.comparator.compare_with_roi(
                    screenshot_before,
                    screenshot_after,
                    roi
                )
                logger.info(f"ROI-Validierung: zoom={roi.get('zoom', 1.5)} um ({roi.get('origin_x', 0)}, {roi.get('origin_y', 0)})")
            else:
                # Standard: Ganzer Screen-Vergleich
                last_comparison = self.comparator.has_state_changed_since(
                    reference_state,
                    screenshot_after
                )
            
            # Prüfe ob relevante Änderung erkannt wurde
            if last_comparison.changed:
                # Änderung erkannt!
                if self._is_relevant_change(last_comparison, action, expected_change):
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Optionale LLM-Validation
                    confidence = self._calculate_confidence(last_comparison)
                    description = last_comparison.description
                    
                    if self.use_llm_validation and confidence < 0.9:
                        llm_result = await self._llm_validate(
                            action,
                            expected_change,
                            screenshot_before,
                            screenshot_after
                        )
                        if llm_result:
                            confidence = max(confidence, llm_result.get("confidence", 0))
                            description = llm_result.get("description", description)
                    
                    self._validations_success += 1
                    
                    return ValidationResult(
                        success=True,
                        confidence=confidence,
                        description=description,
                        change_detected=True,
                        change_type=last_comparison.change_type,
                        change_percentage=last_comparison.change_percentage,
                        duration_ms=duration_ms,
                        attempts=attempts,
                        screenshot_before=screenshot_before,
                        screenshot_after=screenshot_after
                    )
            
            # Warte vor nächstem Check
            await asyncio.sleep(self.check_interval)
        
        # Timeout erreicht
        duration_ms = (time.time() - start_time) * 1000
        
        # Für Aktionen die keine Änderung brauchen
        if not require_change:
            self._validations_success += 1
            return ValidationResult(
                success=True,
                confidence=0.7,
                description="Action completed (no change required)",
                change_detected=False,
                change_type=ChangeType.NO_CHANGE,
                change_percentage=0.0,
                duration_ms=duration_ms,
                attempts=attempts,
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after
            )
        
        # Fehlschlag - keine relevante Änderung erkannt
        return ValidationResult(
            success=False,
            confidence=0.3,
            description=f"Timeout nach {timeout}s - keine erwartete Änderung erkannt",
            change_detected=last_comparison.changed if last_comparison else False,
            change_type=last_comparison.change_type if last_comparison else ChangeType.NO_CHANGE,
            change_percentage=last_comparison.change_percentage if last_comparison else 0.0,
            duration_ms=duration_ms,
            attempts=attempts,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after
        )
    
    def _infer_expected_change(self, action: ActionEvent) -> str:
        """Leitet erwartete Änderung aus Aktion ab."""
        action_type = action.action_type
        
        if action_type == "press_key":
            key = action.params.get("key", "")
            if key == "win":
                return "Startmenü öffnet sich"
            elif key == "enter":
                return "Aktion wird ausgeführt (Enter)"
            elif key in ["alt+f4", "escape"]:
                return "Fenster/Dialog schließt sich"
            elif key == "alt+tab":
                return "Fensterwechsel"
        
        elif action_type == "type":
            text = action.params.get("text", "")
            return f"Text '{text[:20]}...' erscheint"
        
        elif action_type == "click":
            return "UI reagiert auf Klick"
        
        elif action_type == "scroll":
            return "Inhalt scrollt"
        
        return "Bildschirm ändert sich"
    
    def _is_relevant_change(
        self,
        comparison: ComparisonResult,
        action: ActionEvent,
        expected_change: str
    ) -> bool:
        """Prüft ob die erkannte Änderung relevant ist."""
        # Sehr kleine Änderungen ignorieren (z.B. Cursor-Blink)
        if comparison.change_type == ChangeType.MINOR_CHANGE:
            if comparison.change_percentage < 0.02:  # < 2%
                return False
        
        # Für press_key:win erwarten wir signifikante Änderung
        if action.action_type == "press_key" and action.params.get("key") == "win":
            return comparison.change_type in [
                ChangeType.MAJOR_CHANGE,
                ChangeType.SIGNIFICANT_CHANGE,
                ChangeType.NEW_WINDOW,
                ChangeType.ELEMENT_APPEARED
            ]
        
        # Für type erwarten wir Text-Änderungen
        if action.action_type == "type":
            return (
                comparison.change_type == ChangeType.TEXT_CHANGED or
                len(comparison.text_changes) > 0 or
                comparison.change_percentage > 0.01
            )
        
        # Für Klicks reicht jede erkennbare Änderung
        if action.action_type == "click":
            return comparison.change_type != ChangeType.NO_CHANGE
        
        # Default: Jede signifikante Änderung ist relevant
        return comparison.change_type in [
            ChangeType.SIGNIFICANT_CHANGE,
            ChangeType.MAJOR_CHANGE,
            ChangeType.NEW_WINDOW,
            ChangeType.WINDOW_CLOSED,
            ChangeType.TEXT_CHANGED,
            ChangeType.ELEMENT_APPEARED,
            ChangeType.ELEMENT_DISAPPEARED
        ]
    
    def _calculate_confidence(self, comparison: ComparisonResult) -> float:
        """Berechnet Confidence-Score basierend auf Vergleich."""
        base_confidence = 0.5
        
        # Höhere Confidence bei größeren Änderungen
        if comparison.change_type == ChangeType.MAJOR_CHANGE:
            base_confidence = 0.9
        elif comparison.change_type == ChangeType.SIGNIFICANT_CHANGE:
            base_confidence = 0.8
        elif comparison.change_type == ChangeType.NEW_WINDOW:
            base_confidence = 0.95
        elif comparison.change_type == ChangeType.TEXT_CHANGED:
            base_confidence = 0.85
        
        # Bonus für viele geänderte Elemente
        if len(comparison.new_elements) > 3:
            base_confidence += 0.05
        
        return min(base_confidence, 1.0)
    
    async def _llm_validate(
        self,
        action: ActionEvent,
        expected_change: str,
        screenshot_before: bytes,
        screenshot_after: bytes
    ) -> Optional[Dict[str, Any]]:
        """LLM-basierte semantische Validierung."""
        try:
            result = await self.client.validate_action_result(
                action={
                    "type": action.action_type,
                    "params": action.params,
                    "description": action.description
                },
                before_screenshot=screenshot_before,
                after_screenshot=screenshot_after,
                expected_change=expected_change
            )
            return result
        except Exception as e:
            logger.warning(f"LLM validation failed: {e}")
            return None
    
    async def create_validation_event(
        self,
        action: ActionEvent,
        result: ValidationResult
    ) -> ValidationEvent:
        """Erstellt ValidationEvent aus ValidationResult."""
        return ValidationEvent(
            action_id=action.id,
            task_id=action.task_id,
            success=result.success,
            confidence=result.confidence,
            description=result.description,
            state_changed=result.change_detected
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        return {
            "validations_total": self._validations_total,
            "validations_success": self._validations_success,
            "success_rate": (
                self._validations_success / self._validations_total 
                if self._validations_total > 0 else 0
            )
        }


# Singleton
_validator_instance: Optional[ActionValidator] = None


def get_action_validator() -> ActionValidator:
    """Gibt Singleton-Instanz des ActionValidators zurück."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ActionValidator()
    return _validator_instance


def reset_action_validator():
    """Setzt ActionValidator zurück."""
    global _validator_instance
    _validator_instance = None
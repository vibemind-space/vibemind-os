"""
Localization Module - OS Language Detection and Multilingual Prompts

Detects the operating system language and provides prompts in the appropriate language.
Supports German (de) and English (en), with English as the default fallback.

Usage:
    from core.localization import L

    prompt = L.get('analyze_screenshot')
    prompt_with_var = L.get('image_dimensions', w=1920, h=1080)
"""

import locale
import ctypes
import platform
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class Localizer:
    """
    Provides localized prompts based on OS language detection.

    Supports:
    - German (de) - LCID 1031
    - English (en) - Default for all other languages
    """

    PROMPTS: Dict[str, Dict[str, str]] = {
        'de': {
            # Vision Agent - Element Finding
            'vision_find_element': '''Analysiere diesen Screenshot und finde das folgende UI-Element:

GESUCHTES ELEMENT: {element}
{context}

WICHTIG: Gib die EXAKTEN Pixel-Koordinaten zurück, wo ein Benutzer klicken sollte um mit diesem Element zu interagieren.

Das Bild hat die Dimensionen: {w}x{h} Pixel

Antworte NUR im folgenden JSON-Format:
{{
    "found": true/false,
    "x": <X-Koordinate des Klickpunkts>,
    "y": <Y-Koordinate des Klickpunkts>,
    "confidence": <Konfidenz 0.0-1.0>,
    "element_type": "<button/link/textfield/icon/menu/checkbox/other>",
    "description": "<kurze Beschreibung was gefunden wurde>"
}}

Wenn das Element NICHT gefunden wird:
{{
    "found": false,
    "x": 0,
    "y": 0,
    "confidence": 0,
    "element_type": "unknown",
    "description": "Element nicht gefunden: <Grund>"
}}''',

            # Vision Agent - Action Suggestion
            'vision_suggest_action': '''Analysiere diesen Screenshot und bestimme die beste Aktion für folgende Aufgabe:

AUFGABE: {task}

Bildgröße: {w}x{h} Pixel

Antworte als JSON:
{{
    "current_state": "<Was ist aktuell auf dem Bildschirm zu sehen>",
    "suggested_action": {{
        "type": "<click/type/press_key/scroll/wait>",
        "x": <X-Koordinate falls click>,
        "y": <Y-Koordinate falls click>,
        "text": "<Text falls type>",
        "key": "<Taste falls press_key>",
        "description": "<Beschreibung der Aktion>"
    }},
    "target_element": {{
        "description": "<Was wird angeklickt/interagiert>",
        "element_type": "<button/textfield/link/icon/etc>",
        "confidence": <0.0-1.0>
    }},
    "alternative_actions": [
        {{
            "type": "<Aktionstyp>",
            "description": "<Alternative Aktion>"
        }}
    ],
    "task_completable": true/false,
    "reason": "<Warum task_completable true/false>"
}}''',

            # Vision Agent - Desktop Analysis
            'vision_analyze_desktop': '''Analysiere diesen Desktop-Screenshot für UI-Automation.

Beschreibe:
1. **Anwendung/Fenster**: Welche Anwendung ist zu sehen?
2. **UI-Elemente**: Welche interaktiven Elemente sind sichtbar?
3. **Aktionsmöglichkeiten**: Was kann ein Benutzer hier tun?''',

            # Vision Agent - Reflection
            'vision_reflection': '''Du bist ein Reflection-Agent für Desktop-Automatisierung.
Analysiere diesen Screenshot und bewerte den Fortschritt.

Antworte EXAKT im folgenden Format:''',

            # OpenRouter - UI Expert
            'ui_expert_system': '''Du bist ein UI-Automation Experte. Analysiere das Ziel und erstelle einen Schritt-für-Schritt Plan.''',

            'ui_expert_plan': '''Antworte NUR mit einem JSON-Array:''',

            # OpenRouter - Analysis
            'analyze_screenshot': '''Du bist ein UI-Analyse-Experte. Analysiere den Screenshot und identifiziere UI-Elemente.''',

            # Reasoning - Error Recovery
            'error_recovery': '''Du bist ein UI-Automation Experte. Eine Aktion ist fehlgeschlagen.
Analysiere den Fehler und erstelle einen alternativen Plan.

Regeln:
- Vermeide die gleiche Fehlerquelle
- Nutze alternative Wege zum Ziel

Antworte als JSON-Array mit Aktionen.''',

            # OpenRouter - Plan Actions
            'plan_actions_system': '''Du bist ein UI-Automation Experte. Analysiere das Ziel und den Bildschirmzustand.
Erstelle einen präzisen Aktionsplan als JSON-Array.

Verfügbare Aktionen:
- press_key: Taste drücken (key: "win", "enter", "tab", "escape", etc.)
- type: Text eingeben (text: "...")
- click: Klick auf Position (x, y) oder Element-Beschreibung
- wait: Warten (duration: Sekunden)
- verify: Überprüfen ob Bedingung erfüllt (condition: "...")

Antworte NUR mit einem JSON-Array:
[
  {{"action": "press_key", "key": "win", "description": "Windows-Taste drücken"}},
  {{"action": "wait", "duration": 0.5, "description": "Warten auf Startmenü"}},
  ...
]''',

            'plan_actions_user': '''Ziel: {goal}

Bildschirmzustand:
{screen_state}
{history_text}

Erstelle den Aktionsplan als JSON-Array:''',

            # OpenRouter - Validate Action
            'validate_action': '''Vergleiche diese zwei Screenshots (vorher/nachher).

Ausgeführte Aktion: {action}
Erwartete Veränderung: {expected_change}

Analysiere:
1. Hat sich der Bildschirm verändert?
2. Entspricht die Veränderung der Erwartung?
3. War die Aktion erfolgreich?

Antworte als JSON:
{{"success": true/false, "confidence": 0.0-1.0, "description": "..."}}''',

            # Common
            'respond_json': 'Antworte als JSON:',
            'image_dimensions': 'Bildgröße: {w}x{h} Pixel',
            'element_not_found': 'Element nicht gefunden: {reason}',
            'error': 'Fehler',
            'window': 'Fenster',
            'size': 'Größe',
            'previous_actions': 'Bisherige Aktionen:',
            'goal': 'Ziel',
            'screen_state': 'Bildschirmzustand',
            'action_plan': 'Erstelle den Aktionsplan als JSON-Array:',
            'press_win_key': 'Windows-Taste drücken',
            'wait_for_start_menu': 'Warten auf Startmenü',
            'type_text': "'{text}' eingeben",
            'wait_for_search': 'Warten auf Suchergebnisse',
            'press_enter': 'Enter drücken zum Starten',
            'wait_for_app': 'Warten auf {app} Start',
            'click_on': 'Klick auf: {target}',
            'vision_action': 'Vision-basierte Aktion',
            'vision_click': 'Vision-basierter Klick auf: {target}',

            # Progress Agent
            'progress_analyzing': 'Analysiere Fortschritt...',
            'progress_adjustment': 'Passe Plan an: {reason}',
            'progress_goal_check': 'Prüfe ob Ziel erreicht',
            'action_skipped': 'Aktion übersprungen: {reason}',
            'action_retry': 'Wiederhole Aktion: {reason}',
            'progress_completed': 'Fortschritt: {completed}/{total} Aktionen',
            'goal_achieved': 'Ziel erreicht!',

            # Workflows
            'workflow_claude_open': 'Öffne Claude Desktop',
            'workflow_claude_send': 'Sende Aufgabe an Claude',
            'workflow_wait_response': 'Warte auf Claude Antwort',
            'workflow_step_start': 'Starte Schritt: {step}',
            'workflow_step_complete': 'Schritt abgeschlossen: {step}',
            'workflow_step_failed': 'Schritt fehlgeschlagen: {step}',
        },

        'en': {
            # Vision Agent - Element Finding
            'vision_find_element': '''Analyze this screenshot and find the following UI element:

TARGET ELEMENT: {element}
{context}

IMPORTANT: Return the EXACT pixel coordinates where a user should click to interact with this element.

Image dimensions: {w}x{h} pixels

Respond ONLY in the following JSON format:
{{
    "found": true/false,
    "x": <X coordinate of click point>,
    "y": <Y coordinate of click point>,
    "confidence": <confidence 0.0-1.0>,
    "element_type": "<button/link/textfield/icon/menu/checkbox/other>",
    "description": "<brief description of what was found>"
}}

If the element is NOT found:
{{
    "found": false,
    "x": 0,
    "y": 0,
    "confidence": 0,
    "element_type": "unknown",
    "description": "Element not found: <reason>"
}}''',

            # Vision Agent - Action Suggestion
            'vision_suggest_action': '''Analyze this screenshot and determine the best action for the following task:

TASK: {task}

Image size: {w}x{h} pixels

Respond as JSON:
{{
    "current_state": "<What is currently visible on screen>",
    "suggested_action": {{
        "type": "<click/type/press_key/scroll/wait>",
        "x": <X coordinate if click>,
        "y": <Y coordinate if click>,
        "text": "<text if type>",
        "key": "<key if press_key>",
        "description": "<description of the action>"
    }},
    "target_element": {{
        "description": "<What is being clicked/interacted with>",
        "element_type": "<button/textfield/link/icon/etc>",
        "confidence": <0.0-1.0>
    }},
    "alternative_actions": [
        {{
            "type": "<action type>",
            "description": "<alternative action>"
        }}
    ],
    "task_completable": true/false,
    "reason": "<Why task_completable is true/false>"
}}''',

            # Vision Agent - Desktop Analysis
            'vision_analyze_desktop': '''Analyze this desktop screenshot for UI automation.

Describe:
1. **Application/Window**: Which application is visible?
2. **UI Elements**: Which interactive elements are visible?
3. **Possible Actions**: What can a user do here?''',

            # Vision Agent - Reflection
            'vision_reflection': '''You are a Reflection Agent for desktop automation.
Analyze this screenshot and evaluate the progress.

Respond EXACTLY in the following format:''',

            # OpenRouter - UI Expert
            'ui_expert_system': '''You are a UI automation expert. Analyze the goal and create a step-by-step plan.''',

            'ui_expert_plan': '''Respond ONLY with a JSON array:''',

            # OpenRouter - Analysis
            'analyze_screenshot': '''You are a UI analysis expert. Analyze the screenshot and identify UI elements.''',

            # Reasoning - Error Recovery
            'error_recovery': '''You are a UI automation expert. An action has failed.
Analyze the error and create an alternative plan.

Rules:
- Avoid the same error source
- Use alternative paths to the goal

Respond as a JSON array with actions.''',

            # OpenRouter - Plan Actions
            'plan_actions_system': '''You are a UI automation expert. Analyze the goal and screen state.
Create a precise action plan as a JSON array.

Available actions:
- press_key: Press a key (key: "win", "enter", "tab", "escape", etc.)
- type: Type text (text: "...")
- click: Click on position (x, y) or element description
- wait: Wait (duration: seconds)
- verify: Verify if condition is met (condition: "...")

Respond ONLY with a JSON array:
[
  {{"action": "press_key", "key": "win", "description": "Press Windows key"}},
  {{"action": "wait", "duration": 0.5, "description": "Wait for start menu"}},
  ...
]''',

            'plan_actions_user': '''Goal: {goal}

Screen state:
{screen_state}
{history_text}

Create the action plan as JSON array:''',

            # OpenRouter - Validate Action
            'validate_action': '''Compare these two screenshots (before/after).

Executed action: {action}
Expected change: {expected_change}

Analyze:
1. Did the screen change?
2. Does the change match the expectation?
3. Was the action successful?

Respond as JSON:
{{"success": true/false, "confidence": 0.0-1.0, "description": "..."}}''',

            # Common
            'respond_json': 'Respond as JSON:',
            'image_dimensions': 'Image size: {w}x{h} pixels',
            'element_not_found': 'Element not found: {reason}',
            'error': 'Error',
            'window': 'Window',
            'size': 'Size',
            'previous_actions': 'Previous actions:',
            'goal': 'Goal',
            'screen_state': 'Screen state',
            'action_plan': 'Create the action plan as JSON array:',
            'press_win_key': 'Press Windows key',
            'wait_for_start_menu': 'Wait for start menu',
            'type_text': "Type '{text}'",
            'wait_for_search': 'Wait for search results',
            'press_enter': 'Press Enter to start',
            'wait_for_app': 'Wait for {app} to start',
            'click_on': 'Click on: {target}',
            'vision_action': 'Vision-based action',
            'vision_click': 'Vision-based click on: {target}',

            # Progress Agent
            'progress_analyzing': 'Analyzing progress...',
            'progress_adjustment': 'Adjusting plan: {reason}',
            'progress_goal_check': 'Checking if goal achieved',
            'action_skipped': 'Action skipped: {reason}',
            'action_retry': 'Retrying action: {reason}',
            'progress_completed': 'Progress: {completed}/{total} actions',
            'goal_achieved': 'Goal achieved!',

            # Workflows
            'workflow_claude_open': 'Open Claude Desktop',
            'workflow_claude_send': 'Send task to Claude',
            'workflow_wait_response': 'Wait for Claude response',
            'workflow_step_start': 'Starting step: {step}',
            'workflow_step_complete': 'Step completed: {step}',
            'workflow_step_failed': 'Step failed: {step}',
        }
    }

    def __init__(self, force_language: Optional[str] = None):
        """
        Initialize the Localizer.

        Args:
            force_language: Optional language code to force (e.g., 'en', 'de')
        """
        if force_language:
            self.lang = force_language
        else:
            self.lang = self._detect_os_language()

        logger.info(f"Localizer initialized with language: {self.lang}")

    def _detect_os_language(self) -> str:
        """
        Detect the operating system language.

        Returns:
            Language code ('de' for German, 'en' for English/default)
        """
        # Method 1: Windows LCID (most reliable on Windows)
        if platform.system() == "Windows":
            try:
                lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                # Common LCIDs:
                # 1031 = German
                # 1033 = English US
                # 2057 = English UK
                # 1036 = French
                # 1040 = Italian
                # 1034 = Spanish

                if lcid == 1031:
                    return 'de'
                else:
                    return 'en'
            except Exception as e:
                logger.warning(f"Could not detect Windows LCID: {e}")

        # Method 2: Python locale (fallback)
        try:
            lang, _ = locale.getdefaultlocale()
            if lang and lang.startswith('de'):
                return 'de'
        except Exception as e:
            logger.warning(f"Could not detect locale: {e}")

        # Default to English
        return 'en'

    def get(self, key: str, **kwargs) -> str:
        """
        Get a localized prompt by key.

        Args:
            key: The prompt key
            **kwargs: Variables to substitute in the prompt

        Returns:
            The localized prompt string
        """
        prompts = self.PROMPTS.get(self.lang, self.PROMPTS['en'])
        text = prompts.get(key)

        if text is None:
            # Fall back to English
            text = self.PROMPTS['en'].get(key, key)
            logger.warning(f"Prompt '{key}' not found for language '{self.lang}', using fallback")

        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing variable in prompt '{key}': {e}")
                return text

        return text

    def get_language(self) -> str:
        """Get the current language code."""
        return self.lang

    def set_language(self, lang: str):
        """
        Set the language manually.

        Args:
            lang: Language code ('de' or 'en')
        """
        if lang in self.PROMPTS:
            self.lang = lang
            logger.info(f"Language changed to: {lang}")
        else:
            logger.warning(f"Unknown language '{lang}', keeping '{self.lang}'")


# Global instance - auto-detects OS language
L = Localizer()


# Convenience function to get current language
def get_language() -> str:
    """Get the current localization language."""
    return L.get_language()


# Convenience function to set language
def set_language(lang: str):
    """Set the localization language."""
    L.set_language(lang)

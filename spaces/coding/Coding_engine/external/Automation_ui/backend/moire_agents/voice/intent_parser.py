"""Intent Parser for Voice-Controlled Desktop Automation.

Uses Claude API to understand natural language commands and convert them
to structured actions that can be executed by the command executor.

Example:
    "Öffne Anthropic Careers und finde Jobs für Python-Entwickler"
    ->
    {
        "actions": [
            {"type": "open_url", "url": "anthropic.com/careers"},
            {"type": "vision_analyze", "prompt": "Find job listings for Python developers"},
            {"type": "scroll_and_search", "query": "Python"}
        ],
        "context": "Job search at Anthropic for Python developer positions"
    }
"""

import os
import sys
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))

logger = logging.getLogger(__name__)


class LLMBackend(Enum):
    """LLM backend options for intent parsing."""
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class ActionType(Enum):
    """Types of actions the system can execute."""
    OPEN_URL = "open_url"
    CLICK = "click"
    TYPE_TEXT = "type_text"
    SCROLL = "scroll"
    VISION_ANALYZE = "vision_analyze"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    READ_SCREEN = "read_screen"
    FIND_ELEMENT = "find_element"
    KEY_PRESS = "key_press"
    SEARCH = "search"
    NAVIGATE = "navigate"
    UNKNOWN = "unknown"


@dataclass
class Action:
    """A single action to be executed."""
    type: ActionType
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ParsedIntent:
    """Result of intent parsing."""
    original_text: str
    actions: List[Action] = field(default_factory=list)
    context: str = ""
    language: str = "de"
    confidence: float = 1.0
    error: Optional[str] = None


class IntentParser:
    """Parse natural language commands into structured actions using Claude."""

    SYSTEM_PROMPT = """Du bist ein Desktop-Automatisierungs-Assistent. Deine Aufgabe ist es, natürliche Sprachbefehle in strukturierte Aktionen umzuwandeln.

Verfügbare Aktionen:
- open_url: Öffne eine URL im Browser (params: url)
- click: Klicke auf ein Element (params: target, x, y)
- type_text: Tippe Text ein (params: text, target)
- scroll: Scrolle auf der Seite (params: direction, amount)
- vision_analyze: Analysiere den Bildschirm (params: prompt)
- wait: Warte eine Zeit (params: seconds)
- screenshot: Mache einen Screenshot (params: filename)
- read_screen: Lese Text vom Bildschirm (params: region)
- find_element: Finde ein UI-Element (params: description)
- key_press: Drücke eine Taste (params: key, modifiers)
- search: Suche nach Text (params: query)
- navigate: Navigiere zu einem Ziel (params: target)

Antworte IMMER im JSON-Format:
{
    "actions": [
        {"type": "action_type", "params": {...}, "description": "Was diese Aktion tut"}
    ],
    "context": "Kurze Beschreibung des Gesamtziels"
}

Beispiel:
Eingabe: "Öffne Google und suche nach Wetter"
{
    "actions": [
        {"type": "open_url", "params": {"url": "https://google.com"}, "description": "Öffne Google"},
        {"type": "wait", "params": {"seconds": 2}, "description": "Warte auf Seitenladung"},
        {"type": "type_text", "params": {"text": "Wetter", "target": "search_box"}, "description": "Tippe Suchanfrage"},
        {"type": "key_press", "params": {"key": "enter"}, "description": "Starte Suche"}
    ],
    "context": "Google-Suche nach Wetter"
}

Wichtig:
- Füge immer wait-Aktionen nach URL-Öffnungen ein
- Verwende vision_analyze wenn der Benutzer etwas auf dem Bildschirm finden will
- Sei präzise mit URLs (immer mit https://)
- Bei unklaren Befehlen, verwende find_element + click"""

    def __init__(
        self,
        backend: LLMBackend = None,  # Auto-detect based on available API keys
        model: str = None,  # Model name (auto-selected based on backend)
        max_tokens: int = 1000,
        temperature: float = 0.3
    ):
        """Initialize IntentParser.

        Args:
            backend: LLM backend (anthropic or openrouter). Auto-detects if None.
            model: Model name. Auto-selected based on backend if None.
            max_tokens: Maximum response tokens
            temperature: Response temperature (lower = more deterministic)
        """
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Check available API keys
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")

        # Auto-detect backend
        if backend is None:
            if self.openrouter_key:
                backend = LLMBackend.OPENROUTER
                logger.info("Using OpenRouter backend (OPENROUTER_API_KEY found)")
            elif self.anthropic_key:
                backend = LLMBackend.ANTHROPIC
                logger.info("Using Anthropic backend (ANTHROPIC_API_KEY found)")
            else:
                logger.warning("No API key found (ANTHROPIC_API_KEY or OPENROUTER_API_KEY)")
                backend = LLMBackend.ANTHROPIC  # Default, will fail gracefully

        self.backend = backend

        # Set model based on backend
        if model is None:
            if self.backend == LLMBackend.OPENROUTER:
                self.model = "anthropic/claude-sonnet-4"  # OpenRouter format
            else:
                self.model = "claude-sonnet-4-20250514"  # Anthropic format
        else:
            self.model = model

        self._client = None
        self._openrouter_url = "https://openrouter.ai/api/v1/chat/completions"

    def _get_client(self):
        """Get or create Anthropic client."""
        if self.backend != LLMBackend.ANTHROPIC:
            return None

        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.anthropic_key)
            except ImportError:
                logger.error("anthropic package not installed. Run: pip install anthropic")
                return None
        return self._client

    async def _call_anthropic(self, user_prompt: str) -> Optional[str]:
        """Call Anthropic API."""
        client = self._get_client()
        if not client:
            return None

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=self.SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            return None

    async def _call_openrouter(self, user_prompt: str) -> Optional[str]:
        """Call OpenRouter API."""
        if not self.openrouter_key:
            logger.error("OPENROUTER_API_KEY not set")
            return None

        try:
            import aiohttp

            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://moire-automation.local",
                "X-Title": "Moire Voice Automation"
            }

            payload = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._openrouter_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                        return None

                    data = await response.json()
                    return data["choices"][0]["message"]["content"]

        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return None
        except Exception as e:
            logger.error(f"OpenRouter API call failed: {e}")
            return None

    async def parse(self, text: str, context: Optional[str] = None) -> ParsedIntent:
        """Parse natural language text into structured actions.

        Args:
            text: Natural language command
            context: Optional context from previous interactions

        Returns:
            ParsedIntent with list of actions
        """
        # Build prompt with optional context
        user_prompt = text
        if context:
            user_prompt = f"Kontext: {context}\n\nBefehl: {text}"

        try:
            if self.backend == LLMBackend.OPENROUTER:
                response_text = await self._call_openrouter(user_prompt)
            else:
                response_text = await self._call_anthropic(user_prompt)

            if response_text is None:
                return ParsedIntent(
                    original_text=text,
                    error="LLM client not available"
                )

            # Extract JSON from response
            parsed_json = self._extract_json(response_text)
            if not parsed_json:
                return ParsedIntent(
                    original_text=text,
                    error=f"Could not parse JSON from response: {response_text[:200]}"
                )

            # Convert to Action objects
            actions = []
            for action_data in parsed_json.get("actions", []):
                action_type = ActionType.UNKNOWN
                try:
                    action_type = ActionType(action_data.get("type", "unknown"))
                except ValueError:
                    action_type = ActionType.UNKNOWN

                actions.append(Action(
                    type=action_type,
                    params=action_data.get("params", {}),
                    description=action_data.get("description", "")
                ))

            return ParsedIntent(
                original_text=text,
                actions=actions,
                context=parsed_json.get("context", ""),
                language="de"
            )

        except Exception as e:
            logger.error(f"Intent parsing failed: {e}")
            return ParsedIntent(
                original_text=text,
                error=str(e)
            )

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON object from text response."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in text
        import re
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)

        for match in matches:
            try:
                parsed = json.loads(match)
                if "actions" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Try to find JSON block in markdown
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        return None

    async def parse_with_screen_context(
        self,
        text: str,
        screen_description: Optional[str] = None
    ) -> ParsedIntent:
        """Parse command with current screen context.

        Args:
            text: Natural language command
            screen_description: Description of current screen state

        Returns:
            ParsedIntent with contextual actions
        """
        context = None
        if screen_description:
            context = f"Aktueller Bildschirminhalt: {screen_description}"

        return await self.parse(text, context)


# Common intent patterns for quick matching (no API call needed)
QUICK_PATTERNS = {
    # German patterns - URLs
    "öffne google": [Action(ActionType.OPEN_URL, {"url": "https://google.com"}, "Öffne Google")],
    "öffne youtube": [Action(ActionType.OPEN_URL, {"url": "https://youtube.com"}, "Öffne YouTube")],
    "öffne anthropic": [Action(ActionType.OPEN_URL, {"url": "https://anthropic.com"}, "Öffne Anthropic")],
    "öffne anthropic careers": [Action(ActionType.OPEN_URL, {"url": "https://anthropic.com/careers"}, "Öffne Anthropic Careers")],

    # German patterns - Windows Apps (via Start menu search)
    "öffne whatsapp": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "WhatsApp"}, "WhatsApp suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "App starten")
    ],
    "oeffne whatsapp": [  # ASCII variant
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "WhatsApp"}, "WhatsApp suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "App starten")
    ],
    "whatsapp öffnen": [  # Reversed order
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "WhatsApp"}, "WhatsApp suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "App starten")
    ],
    "open whatsapp": [  # English variant
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "WhatsApp"}, "WhatsApp suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "App starten")
    ],
    "öffne notepad": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Notepad"}, "Notepad suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "App starten")
    ],
    "öffne explorer": [
        Action(ActionType.KEY_PRESS, {"key": "win", "modifiers": []}, "Windows-Taste"),
        Action(ActionType.KEY_PRESS, {"key": "e", "modifiers": ["win"]}, "Explorer öffnen")
    ],
    "öffne terminal": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "cmd"}, "Terminal suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Terminal starten")
    ],

    # More Windows Apps
    "öffne chrome": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Chrome"}, "Chrome suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Chrome starten")
    ],
    "oeffne chrome": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Chrome"}, "Chrome suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Chrome starten")
    ],
    "open chrome": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Chrome"}, "Chrome suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Chrome starten")
    ],
    "öffne word": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Word"}, "Word suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Word starten")
    ],
    "oeffne word": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Word"}, "Word suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Word starten")
    ],
    "open word": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Word"}, "Word suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Word starten")
    ],
    "öffne excel": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Excel"}, "Excel suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Excel starten")
    ],
    "öffne outlook": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Outlook"}, "Outlook suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Outlook starten")
    ],
    "öffne vscode": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Visual Studio Code"}, "VS Code suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "VS Code starten")
    ],
    "öffne vs code": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Visual Studio Code"}, "VS Code suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "VS Code starten")
    ],
    "öffne spotify": [
        Action(ActionType.KEY_PRESS, {"key": "win"}, "Windows-Taste drücken"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.TYPE_TEXT, {"text": "Spotify"}, "Spotify suchen"),
        Action(ActionType.WAIT, {"seconds": 0.5}, "Warten"),
        Action(ActionType.KEY_PRESS, {"key": "enter"}, "Spotify starten")
    ],

    # German patterns - Actions
    "scrolle nach unten": [Action(ActionType.SCROLL, {"direction": "down", "amount": 500}, "Scrolle nach unten")],
    "scrolle nach oben": [Action(ActionType.SCROLL, {"direction": "up", "amount": 500}, "Scrolle nach oben")],
    "scroll runter": [Action(ActionType.SCROLL, {"direction": "down", "amount": 500}, "Scrolle nach unten")],
    "scroll hoch": [Action(ActionType.SCROLL, {"direction": "up", "amount": 500}, "Scrolle nach oben")],
    "screenshot": [Action(ActionType.SCREENSHOT, {"filename": "screenshot.png"}, "Screenshot erstellen")],
    "was ist auf dem bildschirm": [Action(ActionType.VISION_ANALYZE, {"prompt": "Beschreibe was auf dem Bildschirm zu sehen ist"}, "Bildschirm analysieren")],

    # Keyboard shortcuts
    "drücke strg f": [Action(ActionType.KEY_PRESS, {"key": "f", "modifiers": ["ctrl"]}, "Suche öffnen (Strg+F)")],
    "drücke strg+f": [Action(ActionType.KEY_PRESS, {"key": "f", "modifiers": ["ctrl"]}, "Suche öffnen (Strg+F)")],
    "suche": [Action(ActionType.KEY_PRESS, {"key": "f", "modifiers": ["ctrl"]}, "Suche öffnen (Strg+F)")],
    "drücke strg c": [Action(ActionType.KEY_PRESS, {"key": "c", "modifiers": ["ctrl"]}, "Kopieren (Strg+C)")],
    "drücke strg v": [Action(ActionType.KEY_PRESS, {"key": "v", "modifiers": ["ctrl"]}, "Einfügen (Strg+V)")],
    "drücke strg z": [Action(ActionType.KEY_PRESS, {"key": "z", "modifiers": ["ctrl"]}, "Rückgängig (Strg+Z)")],
    "drücke strg s": [Action(ActionType.KEY_PRESS, {"key": "s", "modifiers": ["ctrl"]}, "Speichern (Strg+S)")],
    "drücke strg a": [Action(ActionType.KEY_PRESS, {"key": "a", "modifiers": ["ctrl"]}, "Alles auswählen (Strg+A)")],
    "drücke escape": [Action(ActionType.KEY_PRESS, {"key": "escape"}, "Escape drücken")],
    "drücke enter": [Action(ActionType.KEY_PRESS, {"key": "enter"}, "Enter drücken")],
    "drücke tab": [Action(ActionType.KEY_PRESS, {"key": "tab"}, "Tab drücken")],
    "kopieren": [Action(ActionType.KEY_PRESS, {"key": "c", "modifiers": ["ctrl"]}, "Kopieren (Strg+C)")],
    "einfügen": [Action(ActionType.KEY_PRESS, {"key": "v", "modifiers": ["ctrl"]}, "Einfügen (Strg+V)")],
    "rückgängig": [Action(ActionType.KEY_PRESS, {"key": "z", "modifiers": ["ctrl"]}, "Rückgängig (Strg+Z)")],
    "speichern": [Action(ActionType.KEY_PRESS, {"key": "s", "modifiers": ["ctrl"]}, "Speichern (Strg+S)")],
    "alles auswählen": [Action(ActionType.KEY_PRESS, {"key": "a", "modifiers": ["ctrl"]}, "Alles auswählen (Strg+A)")],

    # Window management
    "minimiere fenster": [Action(ActionType.KEY_PRESS, {"key": "down", "modifiers": ["win"]}, "Fenster minimieren")],
    "maximiere fenster": [Action(ActionType.KEY_PRESS, {"key": "up", "modifiers": ["win"]}, "Fenster maximieren")],
    "schließe fenster": [Action(ActionType.KEY_PRESS, {"key": "f4", "modifiers": ["alt"]}, "Fenster schließen (Alt+F4)")],
    "wechsle fenster": [Action(ActionType.KEY_PRESS, {"key": "tab", "modifiers": ["alt"]}, "Fenster wechseln (Alt+Tab)")],
    "zeige desktop": [Action(ActionType.KEY_PRESS, {"key": "d", "modifiers": ["win"]}, "Desktop anzeigen (Win+D)")],

    # English patterns
    "open google": [Action(ActionType.OPEN_URL, {"url": "https://google.com"}, "Open Google")],
    "open youtube": [Action(ActionType.OPEN_URL, {"url": "https://youtube.com"}, "Open YouTube")],
    "scroll down": [Action(ActionType.SCROLL, {"direction": "down", "amount": 500}, "Scroll down")],
    "scroll up": [Action(ActionType.SCROLL, {"direction": "up", "amount": 500}, "Scroll up")],
    "take screenshot": [Action(ActionType.SCREENSHOT, {"filename": "screenshot.png"}, "Take screenshot")],
    "press ctrl f": [Action(ActionType.KEY_PRESS, {"key": "f", "modifiers": ["ctrl"]}, "Open search (Ctrl+F)")],
    "copy": [Action(ActionType.KEY_PRESS, {"key": "c", "modifiers": ["ctrl"]}, "Copy (Ctrl+C)")],
    "paste": [Action(ActionType.KEY_PRESS, {"key": "v", "modifiers": ["ctrl"]}, "Paste (Ctrl+V)")],
    "undo": [Action(ActionType.KEY_PRESS, {"key": "z", "modifiers": ["ctrl"]}, "Undo (Ctrl+Z)")],
    "save": [Action(ActionType.KEY_PRESS, {"key": "s", "modifiers": ["ctrl"]}, "Save (Ctrl+S)")],
}


class QuickIntentParser:
    """Fast intent parser using pattern matching for common commands."""

    def __init__(self, fallback_parser: Optional[IntentParser] = None):
        """Initialize with optional fallback to Claude parser.

        Args:
            fallback_parser: IntentParser to use for complex commands
        """
        self.fallback_parser = fallback_parser
        self.patterns = QUICK_PATTERNS.copy()

    def add_pattern(self, pattern: str, actions: List[Action]):
        """Add a custom pattern.

        Args:
            pattern: Pattern text (lowercase)
            actions: Actions to execute for this pattern
        """
        self.patterns[pattern.lower()] = actions

    async def parse(self, text: str) -> ParsedIntent:
        """Parse text using quick patterns or fallback.

        Args:
            text: Natural language command

        Returns:
            ParsedIntent with actions
        """
        import re
        text_lower = text.lower().strip()
        words = text_lower.split()

        # Sort patterns by length (longest first) to prefer more specific matches
        sorted_patterns = sorted(self.patterns.items(), key=lambda x: len(x[0]), reverse=True)

        # Short patterns that should only match as EXACT commands (not within sentences)
        # These are single-word commands that could easily match within longer sentences
        exact_match_only = {
            "suche", "copy", "paste", "undo", "save", "kopieren", "einfügen",
            "rückgängig", "speichern", "screenshot"
        }

        # If the command has more than 4 words and contains context words,
        # it's likely a complex command that should go to LLM
        complex_indicators = ["in", "nach", "für", "an", "bei", "auf", "und", "dann", "dort", "hier"]
        is_complex = len(words) > 4 and any(w in complex_indicators for w in words)

        for pattern, actions in sorted_patterns:
            pattern_words = pattern.split()

            # For exact match patterns, only match if text is exactly the pattern
            if pattern in exact_match_only:
                if text_lower == pattern:
                    return ParsedIntent(
                        original_text=text,
                        actions=actions,
                        context=f"Quick pattern: {pattern}",
                        confidence=1.0
                    )
            # For app-opening patterns, allow if the text is short enough or matches closely
            elif pattern.startswith("öffne ") or pattern.startswith("oeffne ") or pattern.startswith("open "):
                # Extract app name from pattern
                # Only match if it's a simple "open X" command, not a complex instruction
                if not is_complex and pattern in text_lower:
                    # Make sure it's not embedded in a longer complex sentence
                    if len(words) <= 5:  # "öffne chrome und geh auf google" = 5 words
                        return ParsedIntent(
                            original_text=text,
                            actions=actions,
                            context=f"Quick pattern: {pattern}",
                            confidence=1.0
                        )
            else:
                # For other patterns (keyboard shortcuts, scroll, etc.)
                if pattern in text_lower and len(words) <= 6:
                    return ParsedIntent(
                        original_text=text,
                        actions=actions,
                        context=f"Quick pattern: {pattern}",
                        confidence=1.0
                    )

        # Fallback to Claude parser for complex commands
        if self.fallback_parser:
            return await self.fallback_parser.parse(text)

        # No match and no fallback
        return ParsedIntent(
            original_text=text,
            error="No pattern matched and no fallback available"
        )


# Test/demo code
if __name__ == "__main__":
    async def main():
        print("=== Intent Parser Test ===\n")

        # Test QuickIntentParser first
        quick_parser = QuickIntentParser()

        test_commands = [
            "Öffne Google",
            "Scrolle nach unten",
            "Was ist auf dem Bildschirm?",
        ]

        for cmd in test_commands:
            result = await quick_parser.parse(cmd)
            print(f"Input: {cmd}")
            if result.actions:
                for action in result.actions:
                    print(f"  -> {action.type.value}: {action.params}")
            else:
                print(f"  -> Error: {result.error}")
            print()

        # Test full parser if API key is available
        if os.getenv("ANTHROPIC_API_KEY"):
            print("Testing Claude-based parser...\n")
            parser = IntentParser()

            complex_commands = [
                "Öffne Anthropic Careers und finde Jobs für Python-Entwickler",
                "Finde den Login-Button und klicke drauf",
            ]

            for cmd in complex_commands:
                result = await parser.parse(cmd)
                print(f"Input: {cmd}")
                if result.actions:
                    for action in result.actions:
                        print(f"  -> {action.type.value}: {action.params}")
                    print(f"  Context: {result.context}")
                else:
                    print(f"  -> Error: {result.error}")
                print()
        else:
            print("ANTHROPIC_API_KEY not set, skipping Claude parser test")

    asyncio.run(main())

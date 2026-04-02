"""
Vision Agent - Analysiert Screenshots mit Multi-Modal Vision

Verantwortlich für:
- Screenshot-Analyse bei Hard Cases (niedrige OCR-Qualität)
- Multi-Modal Message Erstellung für AutoGen
- Element-Erkennung basierend auf Vision
- Fallback wenn normale OCR versagt
- NEU: UI-Element Lokalisierung mit gpt-4o
"""

import logging
import asyncio
import base64
import sys
import os
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Optional imports
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from autogen_agentchat.messages import MultiModalMessage
    from autogen_core import Image as AutoGenImage
    HAS_AUTOGEN_MULTIMODAL = True
except ImportError:
    HAS_AUTOGEN_MULTIMODAL = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Import OpenRouter client
try:
    from core.openrouter_client import OpenRouterClient, get_openrouter_client
    HAS_OPENROUTER = True
except ImportError:
    HAS_OPENROUTER = False

# Import Localization
try:
    from core.localization import L
    HAS_LOCALIZATION = True
except ImportError:
    HAS_LOCALIZATION = False
    L = None

if TYPE_CHECKING:
    from ..bridge.websocket_client import MoireWebSocketClient


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VisionAnalysisResult:
    """Ergebnis der Vision-Analyse."""
    success: bool
    description: str
    detected_elements: List[Dict[str, Any]]
    suggested_actions: List[Dict[str, Any]]
    raw_response: Optional[str] = None
    error: Optional[str] = None
    
    def to_context(self) -> str:
        """Erzeugt Kontext-String für andere Agents."""
        if not self.success:
            return f"Vision-Analyse fehlgeschlagen: {self.error}"
        
        lines = [
            "=== Vision-Analyse Ergebnis ===",
            "",
            self.description,
            "",
            "Erkannte Elemente:",
        ]
        
        for elem in self.detected_elements[:15]:
            elem_type = elem.get('type', 'unknown')
            text = elem.get('text', '')
            location = elem.get('location', 'unbekannt')
            lines.append(f"  • [{elem_type}] {text} @ {location}")
        
        if self.suggested_actions:
            lines.append("")
            lines.append("Vorgeschlagene Aktionen:")
            for action in self.suggested_actions[:5]:
                lines.append(f"  → {action.get('description', 'Unbekannt')}")
        
        return "\n".join(lines)


@dataclass
class ElementLocation:
    """Ergebnis der Element-Lokalisierung."""
    found: bool
    x: int
    y: int
    confidence: float
    description: str
    element_type: str
    error: Optional[str] = None


class VisionAnalystAgent:
    """
    Vision Agent für Multi-Modal Screenshot-Analyse.
    
    Verwendet gpt-4o via OpenRouter für:
    - Analyse von Screenshots bei niedriger OCR-Qualität
    - Erkennung von UI-Elementen die OCR nicht erfassen konnte
    - Kontextuelle Beschreibung des Bildschirminhalts
    - NEU: Lokalisierung von UI-Elementen anhand von Beschreibungen
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2000
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.client: Optional[anthropic.Anthropic] = None
        self.openrouter_client: Optional[OpenRouterClient] = None
        
        # Initialize Anthropic client (legacy)
        if HAS_ANTHROPIC:
            try:
                self.client = anthropic.Anthropic()
                logger.info("Vision Agent initialized with Anthropic Claude")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic: {e}")
        
        # Initialize OpenRouter client (preferred for gpt-4o)
        if HAS_OPENROUTER:
            try:
                self.openrouter_client = get_openrouter_client()
                logger.info(f"Vision Agent initialized with OpenRouter ({self.model})")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenRouter: {e}")
    
    def is_available(self) -> bool:
        """Prüft ob Vision-Analyse verfügbar ist."""
        return (self.openrouter_client is not None or self.client is not None) and HAS_PIL
    
    async def find_element(
        self,
        image: 'PILImage.Image',
        element_description: str,
        context: str = ""
    ) -> ElementLocation:
        """
        Findet ein UI-Element anhand einer Beschreibung.
        
        Verwendet gpt-4o für präzise Element-Lokalisierung.
        
        Args:
            image: PIL Image des Screenshots
            element_description: Beschreibung des gesuchten Elements
                z.B. "Leeres Dokument Button", "Schließen X", "Suche Textfeld"
            context: Zusätzlicher Kontext (z.B. welche App ist aktiv)
        
        Returns:
            ElementLocation mit Koordinaten oder Fehler
        """
        if not self.is_available():
            return ElementLocation(
                found=False,
                x=0, y=0,
                confidence=0,
                description="",
                element_type="unknown",
                error="Vision not available"
            )
        
        try:
            # Resize image if needed
            max_size = 1568
            original_size = image.size
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, PILImage.Resampling.LANCZOS)
            
            # Convert to base64
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Build prompt for element location (localized)
            if HAS_LOCALIZATION and L:
                context_str = f"CONTEXT: {context}" if context else ""
                prompt = L.get('vision_find_element',
                              element=element_description,
                              context=context_str,
                              w=image.size[0],
                              h=image.size[1])
            else:
                # Fallback to English if localization not available
                prompt = f"""Analyze this screenshot and find the following UI element:

TARGET ELEMENT: {element_description}
{f"CONTEXT: {context}" if context else ""}

IMPORTANT: Return the EXACT pixel coordinates where a user should click to interact with this element.

Image dimensions: {image.size[0]}x{image.size[1]} pixels

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
}}"""

            # Use OpenRouter with gpt-4o for vision
            if self.openrouter_client:
                response = await self.openrouter_client.chat_with_vision(
                    prompt=prompt,
                    image_data=base64_image,
                    json_mode=True
                )
                
                if response and response.content:
                    import json
                    try:
                        result = json.loads(response.content)
                        
                        # Scale coordinates back if image was resized
                        x = result.get('x', 0)
                        y = result.get('y', 0)
                        
                        if max(original_size) > max_size:
                            scale = original_size[0] / image.size[0]
                            x = int(x * scale)
                            y = int(y * scale)
                        
                        return ElementLocation(
                            found=result.get('found', False),
                            x=x,
                            y=y,
                            confidence=result.get('confidence', 0),
                            description=result.get('description', ''),
                            element_type=result.get('element_type', 'unknown')
                        )
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse vision response: {response.content[:200]}")
            
            # Fallback to Anthropic if available
            elif self.client:
                response = await asyncio.to_thread(
                    self._call_claude_vision,
                    base64_image,
                    prompt
                )
                
                import json
                try:
                    result = json.loads(response)
                    
                    x = result.get('x', 0)
                    y = result.get('y', 0)
                    
                    if max(original_size) > max_size:
                        scale = original_size[0] / image.size[0]
                        x = int(x * scale)
                        y = int(y * scale)
                    
                    return ElementLocation(
                        found=result.get('found', False),
                        x=x,
                        y=y,
                        confidence=result.get('confidence', 0),
                        description=result.get('description', ''),
                        element_type=result.get('element_type', 'unknown')
                    )
                except json.JSONDecodeError:
                    pass
            
            return ElementLocation(
                found=False,
                x=0, y=0,
                confidence=0,
                description="",
                element_type="unknown",
                error="No valid response from vision model"
            )
        
        except Exception as e:
            logger.error(f"find_element failed: {e}")
            return ElementLocation(
                found=False,
                x=0, y=0,
                confidence=0,
                description="",
                element_type="unknown",
                error=str(e)
            )
    
    async def find_element_from_screenshot(
        self,
        screenshot_bytes: bytes,
        element_description: str,
        context: str = ""
    ) -> ElementLocation:
        """
        Convenience-Methode: Findet Element direkt aus Screenshot-Bytes.
        
        Args:
            screenshot_bytes: PNG-Bytes des Screenshots
            element_description: Was gesucht werden soll
            context: Zusätzlicher Kontext
        
        Returns:
            ElementLocation
        """
        if not HAS_PIL:
            return ElementLocation(
                found=False, x=0, y=0, confidence=0,
                description="", element_type="unknown",
                error="PIL not available"
            )
        
        try:
            image = PILImage.open(BytesIO(screenshot_bytes))
            return await self.find_element(image, element_description, context)
        except Exception as e:
            return ElementLocation(
                found=False, x=0, y=0, confidence=0,
                description="", element_type="unknown",
                error=f"Failed to load image: {e}"
            )
    
    async def analyze_screen_for_task(
        self,
        image: 'PILImage.Image',
        task_description: str
    ) -> Dict[str, Any]:
        """
        Analysiert Screen für einen bestimmten Task.
        
        Findet relevante UI-Elemente für den Task und schlägt Aktionen vor.
        
        Args:
            image: Screenshot
            task_description: Was der Benutzer tun möchte
        
        Returns:
            Dict mit:
            - suggested_action: Vorgeschlagene nächste Aktion
            - target_element: Ziel-Element mit Koordinaten
            - alternative_actions: Alternative Vorschläge
        """
        if not self.is_available():
            return {"error": "Vision not available"}
        
        try:
            # Resize if needed
            max_size = 1568
            original_size = image.size
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, PILImage.Resampling.LANCZOS)
            
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Build prompt (localized)
            if HAS_LOCALIZATION and L:
                prompt = L.get('vision_suggest_action',
                              task=task_description,
                              w=image.size[0],
                              h=image.size[1])
            else:
                # Fallback to English
                prompt = f"""Analyze this screenshot and determine the best action for the following task:

TASK: {task_description}

Image size: {image.size[0]}x{image.size[1]} pixels

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
}}"""

            if self.openrouter_client:
                response = await self.openrouter_client.chat_with_vision(
                    prompt=prompt,
                    image_data=base64_image,
                    json_mode=True
                )
                
                if response and response.content:
                    import json
                    try:
                        result = json.loads(response.content)
                        
                        # Scale coordinates back
                        if 'suggested_action' in result and 'x' in result['suggested_action']:
                            if max(original_size) > max_size:
                                scale = original_size[0] / image.size[0]
                                result['suggested_action']['x'] = int(result['suggested_action']['x'] * scale)
                                result['suggested_action']['y'] = int(result['suggested_action']['y'] * scale)
                        
                        return result
                    except json.JSONDecodeError:
                        pass
            
            return {"error": "No valid response from vision model"}
        
        except Exception as e:
            logger.error(f"analyze_screen_for_task failed: {e}")
            return {"error": str(e)}
    
    async def analyze_screenshot(
        self,
        image: 'PILImage.Image',
        context: str = "",
        focus_area: Optional[Dict[str, int]] = None
    ) -> VisionAnalysisResult:
        """
        Analysiert einen Screenshot mit Vision.
        
        Args:
            image: PIL Image des Screenshots
            context: Optionaler Kontext (z.B. aktuelle Task)
            focus_area: Optionaler Fokusbereich {x, y, width, height}
        
        Returns:
            VisionAnalysisResult mit Beschreibung und Elementen
        """
        if not self.is_available():
            return VisionAnalysisResult(
                success=False,
                description="",
                detected_elements=[],
                suggested_actions=[],
                error="Vision not available (Anthropic or PIL missing)"
            )
        
        try:
            # Crop to focus area if specified
            if focus_area:
                image = image.crop((
                    focus_area['x'],
                    focus_area['y'],
                    focus_area['x'] + focus_area['width'],
                    focus_area['y'] + focus_area['height']
                ))
            
            # Resize large images for efficiency
            max_size = 1568  # Claude's max recommended size
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, PILImage.Resampling.LANCZOS)
            
            # Convert to base64
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Build prompt
            prompt = self._build_analysis_prompt(context)
            
            # Prefer OpenRouter with gpt-4o
            if self.openrouter_client:
                response = await self.openrouter_client.chat_with_vision(
                    prompt=prompt,
                    image_data=base64_image
                )
                if response and response.content:
                    return self._parse_vision_response(response.content)
            
            # Fallback to Claude Vision
            elif self.client:
                response = await asyncio.to_thread(
                    self._call_claude_vision,
                    base64_image,
                    prompt
                )
                return self._parse_vision_response(response)
            
            return VisionAnalysisResult(
                success=False,
                description="",
                detected_elements=[],
                suggested_actions=[],
                error="No vision backend available"
            )
        
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return VisionAnalysisResult(
                success=False,
                description="",
                detected_elements=[],
                suggested_actions=[],
                error=str(e)
            )
    
    def _build_analysis_prompt(self, context: str) -> str:
        """Erstellt den Analyse-Prompt."""
        prompt = """Analysiere diesen Desktop-Screenshot für UI-Automation.

Bitte identifiziere und beschreibe:

1. **Anwendung/Fenster**: Welche Anwendung ist zu sehen?

2. **UI-Elemente**: Liste alle sichtbaren UI-Elemente auf:
   - Buttons (mit Text wenn vorhanden)
   - Menüs und Menüpunkte
   - Textfelder und Eingabefelder
   - Icons und deren wahrscheinliche Funktion
   - Checkboxen, Dropdowns, etc.

3. **Texte**: Alle lesbaren Texte im Bild

4. **Aktionen**: Welche Aktionen sind möglich?
   - Was kann geklickt werden?
   - Wo kann Text eingegeben werden?
   - Welche Tastenkombinationen könnten verfügbar sein?

5. **Fokus**: Was ist aktuell im Fokus oder aktiv?

Formatiere die Antwort strukturiert mit klaren Abschnitten."""

        if context:
            prompt += f"\n\nKontext für diese Analyse: {context}"
        
        return prompt
    
    def _call_claude_vision(self, base64_image: str, prompt: str) -> str:
        """Ruft Claude Vision API auf."""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        return message.content[0].text
    
    def _parse_vision_response(self, response: str) -> VisionAnalysisResult:
        """Parst die Vision-Antwort in strukturiertes Format."""
        # Extract elements from response
        detected_elements = []
        suggested_actions = []
        
        # Simple parsing - look for patterns
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Detect sections
            if 'button' in line_lower or 'schaltfläche' in line_lower:
                current_section = 'button'
            elif 'menü' in line_lower or 'menu' in line_lower:
                current_section = 'menu'
            elif 'textfeld' in line_lower or 'eingabe' in line_lower or 'input' in line_lower:
                current_section = 'input'
            elif 'icon' in line_lower:
                current_section = 'icon'
            elif 'aktion' in line_lower or 'action' in line_lower:
                current_section = 'action'
            
            # Extract items
            if line.strip().startswith('-') or line.strip().startswith('•'):
                item_text = line.strip().lstrip('-•').strip()
                
                if current_section == 'action':
                    suggested_actions.append({
                        'description': item_text,
                        'confidence': 0.7
                    })
                elif current_section:
                    detected_elements.append({
                        'type': current_section,
                        'text': item_text,
                        'location': 'from vision',
                        'confidence': 0.7
                    })
        
        return VisionAnalysisResult(
            success=True,
            description=response[:500],  # First 500 chars as summary
            detected_elements=detected_elements,
            suggested_actions=suggested_actions,
            raw_response=response
        )

    async def analyze_from_client(
        self,
        client: 'MoireWebSocketClient',
        context: str = ""
    ) -> VisionAnalysisResult:
        """
        Analysiert Screenshot direkt vom WebSocket Client.
        
        Args:
            client: MoireWebSocketClient mit aktuellem Screenshot
            context: Optionaler Kontext
        
        Returns:
            VisionAnalysisResult
        """
        image = client.get_screenshot_as_pil()
        
        if image is None:
            return VisionAnalysisResult(
                success=False,
                description="",
                detected_elements=[],
                suggested_actions=[],
                error="No screenshot available"
            )
        
        return await self.analyze_screenshot(image, context)
    
    def create_multimodal_message(
        self,
        image: 'PILImage.Image',
        text: str = "Analysiere diesen Screenshot"
    ) -> Optional['MultiModalMessage']:
        """
        Erstellt eine MultiModalMessage für AutoGen AgentChat.
        
        Args:
            image: PIL Image
            text: Begleittext
        
        Returns:
            MultiModalMessage oder None wenn nicht verfügbar
        """
        if not HAS_AUTOGEN_MULTIMODAL or not HAS_PIL:
            logger.warning("AutoGen MultiModal not available")
            return None
        
        try:
            autogen_image = AutoGenImage(image)
            return MultiModalMessage(
                content=[text, autogen_image],
                source="vision_agent"
            )
        except Exception as e:
            logger.error(f"Failed to create MultiModalMessage: {e}")
            return None
    
    async def describe_element(
        self,
        image: 'PILImage.Image',
        element_bounds: Dict[str, int]
    ) -> str:
        """
        Beschreibt ein einzelnes UI-Element.
        
        Args:
            image: Vollständiger Screenshot
            element_bounds: Bounds des Elements {x, y, width, height}
        
        Returns:
            Beschreibung des Elements
        """
        # Crop to element with padding
        padding = 10
        x1 = max(0, element_bounds['x'] - padding)
        y1 = max(0, element_bounds['y'] - padding)
        x2 = min(image.width, element_bounds['x'] + element_bounds['width'] + padding)
        y2 = min(image.height, element_bounds['y'] + element_bounds['height'] + padding)
        
        element_image = image.crop((x1, y1, x2, y2))
        
        result = await self.analyze_screenshot(
            element_image,
            context="Beschleibe nur dieses einzelne UI-Element kurz und präzise."
        )
        
        if result.success:
            return result.description
        return f"Element bei ({element_bounds['x']}, {element_bounds['y']})"
    
    async def analyze_with_prompt(
        self,
        screenshot: bytes,
        prompt: str
    ) -> str:
        """
        Analysiert Screenshot mit benutzerdefiniertem Prompt.
        
        Dies ist die generische Methode für Vision-Analyse mit beliebigen Prompts.
        
        Args:
            screenshot: PNG-Bytes des Screenshots
            prompt: Der zu verwendende Prompt
        
        Returns:
            String mit der Analyse-Antwort
        """
        if not self.is_available():
            return "Vision-Analyse nicht verfügbar"
        
        if not HAS_PIL:
            return "PIL nicht verfügbar"
        
        try:
            # Load image from bytes
            image = PILImage.open(BytesIO(screenshot))
            
            # Resize if needed
            max_size = 1568
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, PILImage.Resampling.LANCZOS)
            
            # Convert to base64
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Try OpenRouter first
            if self.openrouter_client:
                response = await self.openrouter_client.chat_with_vision(
                    prompt=prompt,
                    image_data=base64_image
                )
                if response and response.content:
                    return response.content
            
            # Fallback to Claude
            if self.client:
                response = await asyncio.to_thread(
                    self._call_claude_vision,
                    base64_image,
                    prompt
                )
                return response
            
            return "Keine Vision-Backend verfügbar"
            
        except Exception as e:
            logger.error(f"analyze_with_prompt failed: {e}")
            return f"Analyse-Fehler: {e}"
    
    async def analyze_for_reflection(
        self,
        screenshot: bytes,
        goal: str,
        executed_actions: List[str],
        round_number: int
    ) -> Dict[str, Any]:
        """
        Spezialisierte Reflection-Analyse für den Orchestrator.
        
        Analysiert den Screenshot im Kontext der ausgeführten Aktionen
        und bestimmt ob das Ziel erreicht wurde.
        
        Args:
            screenshot: PNG-Bytes des Screenshots
            goal: Das ursprüngliche Ziel
            executed_actions: Liste der ausgeführten Aktionen
            round_number: Aktuelle Reflection-Runde
        
        Returns:
            Dict mit:
            - goal_achieved: bool
            - progress_score: float (0.0-1.0)
            - issues: List[str]
            - corrections: List[str]
            - analysis: str
        """
        if not self.is_available() or not HAS_PIL:
            return {
                "goal_achieved": False,
                "progress_score": 0.0,
                "issues": ["Vision nicht verfügbar"],
                "corrections": [],
                "analysis": "Vision-Analyse nicht möglich"
            }
        
        # Build reflection prompt
        actions_str = "\n".join(f"- {a}" for a in executed_actions[-10:])
        
        prompt = f"""Du bist ein Reflection-Agent für Desktop-Automatisierung.
Analysiere diesen Screenshot und bewerte den Fortschritt.

URSPRÜNGLICHES ZIEL: {goal}

AUSGEFÜHRTE AKTIONEN (letzte 10):
{actions_str}

REFLECTION-RUNDE: {round_number}

Bitte bewerte:
1. Ist das Ziel erreicht? (ja/nein)
2. Wie weit ist der Fortschritt? (0-100%)
3. Welche Probleme oder Hindernisse sind sichtbar?
4. Welche Korrekturen werden empfohlen?

Antworte EXAKT im folgenden Format:
ZIEL_ERREICHT: ja/nein
FORTSCHRITT: [0-100]
PROBLEME: Problem1 | Problem2 | Problem3
KORREKTUREN: Korrektur1 | Korrektur2
ANALYSE: Detaillierte Beschreibung des aktuellen Bildschirmzustands und warum das Ziel erreicht/nicht erreicht wurde."""

        try:
            response = await self.analyze_with_prompt(screenshot, prompt)
            
            # Parse response
            goal_achieved = False
            progress_score = 0.0
            issues = []
            corrections = []
            analysis = response
            
            lines = response.split('\n')
            for line in lines:
                line_lower = line.lower().strip()
                
                if line_lower.startswith("ziel_erreicht:"):
                    goal_achieved = "ja" in line_lower.split(":")[-1]
                
                elif line_lower.startswith("fortschritt:"):
                    try:
                        progress_str = line.split(":")[-1].strip().replace("%", "")
                        progress_score = float(progress_str) / 100.0
                        progress_score = max(0.0, min(1.0, progress_score))
                    except:
                        pass
                
                elif line_lower.startswith("probleme:"):
                    problems_str = line.split(":", 1)[-1].strip()
                    if problems_str and problems_str.lower() != "keine":
                        issues = [p.strip() for p in problems_str.split("|") if p.strip()]
                
                elif line_lower.startswith("korrekturen:"):
                    corrections_str = line.split(":", 1)[-1].strip()
                    if corrections_str and corrections_str.lower() != "keine":
                        corrections = [c.strip() for c in corrections_str.split("|") if c.strip()]
                
                elif line_lower.startswith("analyse:"):
                    analysis = line.split(":", 1)[-1].strip()
            
            return {
                "goal_achieved": goal_achieved,
                "progress_score": progress_score,
                "issues": issues,
                "corrections": corrections,
                "analysis": analysis
            }
            
        except Exception as e:
            logger.error(f"analyze_for_reflection failed: {e}")
            return {
                "goal_achieved": False,
                "progress_score": 0.0,
                "issues": [f"Analyse-Fehler: {e}"],
                "corrections": [],
                "analysis": f"Fehler bei der Reflection-Analyse: {e}"
            }


# Singleton
_vision_agent_instance: Optional[VisionAnalystAgent] = None


def get_vision_agent() -> VisionAnalystAgent:
    """Gibt Singleton-Instanz des Vision Agents zurück."""
    global _vision_agent_instance
    if _vision_agent_instance is None:
        _vision_agent_instance = VisionAnalystAgent()
    return _vision_agent_instance


def reset_vision_agent():
    """Setzt Vision Agent zurück."""
    global _vision_agent_instance
    _vision_agent_instance = None


async def test_vision_agent():
    """Test-Funktion für Vision Agent."""
    agent = get_vision_agent()
    
    print(f"Vision Agent available: {agent.is_available()}")
    print(f"OpenRouter client: {agent.openrouter_client is not None}")
    print(f"Anthropic client: {agent.client is not None}")
    
    if agent.is_available() and HAS_PIL:
        # Create test image
        test_image = PILImage.new('RGB', (800, 600), color='white')
        
        result = await agent.analyze_screenshot(
            test_image,
            context="Test screenshot"
        )
        
        print(f"Analysis result: {result.success}")
        print(f"Description: {result.description[:200] if result.description else 'None'}...")


if __name__ == "__main__":
    asyncio.run(test_vision_agent())
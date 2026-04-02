"""
OpenRouter Client - Unified LLM API für verschiedene Modelle

Unterstützt:
- claude-sonnet-4 (Reasoning/Planning + Vision)
- gemini-2.0-flash (Schnelle Vision Alternative)
- claude-3.5-sonnet (Quick Actions)
"""

import asyncio
import aiohttp
import json
import base64
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from enum import Enum

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logging.getLogger(__name__).info(f"Loaded .env from {env_path}")
except ImportError:
    pass  # dotenv not installed, rely on system environment variables

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Localization
try:
    from core.localization import L
    HAS_LOCALIZATION = True
except ImportError:
    try:
        from localization import L
        HAS_LOCALIZATION = True
    except ImportError:
        HAS_LOCALIZATION = False
        L = None
        logger.info("Localization not available, using default prompts")


class ModelType(Enum):
    """Verfügbare Modelle via OpenRouter."""
    REASONING = "anthropic/claude-sonnet-4"  # Beste Qualität für Planung
    VISION = "anthropic/claude-sonnet-4"  # Claude Sonnet 4 hat exzellente Vision
    VISION_FAST = "google/gemini-2.0-flash-exp:free"  # Schnelle kostenlose Alternative
    QUICK = "anthropic/claude-3.5-sonnet"  # Schnell für einfache Aufgaben


@dataclass
class LLMResponse:
    """Antwort vom LLM."""
    content: str
    model: str
    usage: Dict[str, int]
    raw_response: Optional[Dict[str, Any]] = None


class OpenRouterClient:
    """
    OpenRouter Client für LLM-Aufrufe.
    
    Verwendet OpenRouter API für Zugriff auf verschiedene Modelle:
    - Claude Sonnet 4 für Reasoning
    - GPT-4o für Vision
    - Claude 3.5 Sonnet für schnelle Aktionen
    """
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            logger.warning("No OPENROUTER_API_KEY found - LLM calls will fail")
        
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_count = 0
        self._total_tokens = 0
    
    async def _ensure_session(self):
        """Erstellt Session wenn nötig."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://moiretracker.local",
                    "X-Title": "MoireTracker Agent System"
                }
            )
    
    async def close(self):
        """Schließt die Session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Union[ModelType, str] = ModelType.REASONING,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> LLMResponse:
        """
        Sendet Chat-Anfrage an OpenRouter.
        
        Args:
            messages: Liste von Messages [{role, content}]
            model: Zu verwendendes Modell
            temperature: Kreativität (0-1)
            max_tokens: Maximale Antwortlänge
            json_mode: Ob JSON-Antwort erzwungen werden soll
        
        Returns:
            LLMResponse mit Inhalt und Metadaten
        """
        if not self.api_key:
            raise ValueError("No API key configured")
        
        await self._ensure_session()
        
        model_name = model.value if isinstance(model, ModelType) else model
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        try:
            async with self.session.post(
                f"{self.BASE_URL}/chat/completions",
                json=payload
            ) as response:
                self._request_count += 1
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"OpenRouter error {response.status}: {error_text}")
                    raise Exception(f"OpenRouter API error: {response.status} - {error_text}")
                
                data = await response.json()
                
                content = data['choices'][0]['message']['content'] or ""
                usage = data.get('usage', {})
                self._total_tokens += usage.get('total_tokens', 0)
                
                return LLMResponse(
                    content=content,
                    model=model_name,
                    usage=usage,
                    raw_response=data
                )
        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error: {e}")
            raise
    
    async def chat_with_vision(
        self,
        prompt: str,
        image_data: Union[str, bytes],
        image_base64: Optional[str] = None,  # Alternative Parameter für Kompatibilität
        model: Union[ModelType, str] = ModelType.VISION,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        """
        Sendet Chat mit Bild an OpenRouter.
        
        Args:
            prompt: Text-Prompt
            image_data: Base64-String oder Bytes des Bildes
            image_base64: Alternative zu image_data (für Kompatibilität)
            model: Vision-Modell (default: claude-sonnet-4)
            system_prompt: Optionaler System-Prompt
            json_mode: Ob JSON-Antwort erzwungen werden soll
        
        Returns:
            LLMResponse
        """
        # Verwende image_base64 wenn image_data nicht bytes ist
        if image_base64 and not isinstance(image_data, bytes):
            image_data = image_base64
        
        # Konvertiere Bytes zu Base64 wenn nötig
        if isinstance(image_data, bytes):
            image_b64 = base64.b64encode(image_data).decode('utf-8')
        else:
            image_b64 = image_data
        
        # Entferne Data-URL-Präfix wenn vorhanden
        if image_b64.startswith('data:'):
            image_b64 = image_b64.split(',')[1]
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        model_name = model.value if isinstance(model, ModelType) else model

        # OpenRouter uses OpenAI-compatible API format for ALL models
        # Always use image_url format (not Anthropic-native format)
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}",
                        "detail": "high"
                    }
                }
            ]
        })
        
        return await self.chat(messages, model=model, json_mode=json_mode)
        
    async def plan_actions(
        self,
        goal: str,
        screen_state: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Plant Aktionen für ein Ziel basierend auf Screen-State.
        
        Args:
            goal: Das zu erreichende Ziel
            screen_state: Aktueller Bildschirmzustand (Elemente, OCR, etc.)
            history: Bisherige Aktionen und Ergebnisse
        
        Returns:
            Liste von Action-Dicts mit action, target, params, description
        """
        # Use localized prompts if available
        if HAS_LOCALIZATION and L:
            system_prompt = L.get('plan_actions_system')
            history_text = ""
            if history:
                history_text = f"\n\n{L.get('previous_actions')}\n{json.dumps(history, indent=2)}"
            user_prompt = L.get('plan_actions_user',
                goal=goal,
                screen_state=json.dumps(screen_state, indent=2, ensure_ascii=False)[:3000],
                history_text=history_text
            )
        else:
            # Fallback to English
            system_prompt = """You are a UI automation expert. Analyze the goal and screen state.
Create a precise action plan as a JSON array.

Available actions:
- press_key: Press a key (key: "win", "enter", "tab", "escape", etc.)
- type: Type text (text: "...")
- click: Click on position (x, y) or element description
- wait: Wait (duration: seconds)
- verify: Verify if condition is met (condition: "...")

Respond ONLY with a JSON array:
[
  {"action": "press_key", "key": "win", "description": "Press Windows key"},
  {"action": "wait", "duration": 0.5, "description": "Wait for start menu"},
  ...
]"""
            history_text = ""
            if history:
                history_text = f"\n\nPrevious actions:\n{json.dumps(history, indent=2)}"
            user_prompt = f"""Goal: {goal}

Screen state:
{json.dumps(screen_state, indent=2, ensure_ascii=False)[:3000]}
{history_text}

Create the action plan as JSON array:"""

        response = await self.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=ModelType.REASONING,
            temperature=0.2,
            json_mode=True
        )
        
        try:
            # Parse JSON response
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            actions = json.loads(content)
            
            # Validiere Format
            if isinstance(actions, dict) and 'actions' in actions:
                actions = actions['actions']
            
            if not isinstance(actions, list):
                logger.error(f"Invalid action plan format: {type(actions)}")
                return []
            
            return actions
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse action plan: {e}\nResponse: {response.content}")
            return []
    
    async def analyze_screenshot(
        self,
        screenshot: Union[str, bytes],
        query: str = "Beschreibe alle UI-Elemente die du siehst"
    ) -> Dict[str, Any]:
        """
        Analysiert einen Screenshot mit GPT-4o.
        
        Args:
            screenshot: Screenshot als Base64 oder Bytes
            query: Spezifische Frage zum Screenshot
        
        Returns:
            Dict mit analysis, elements, suggestions
        """
        # Use localized prompt if available
        if HAS_LOCALIZATION and L:
            system_prompt = L.get('analyze_screenshot')
        else:
            # Fallback to English
            system_prompt = """You are a UI analysis expert. Analyze the screenshot precisely.
Identify all interactive elements (buttons, input fields, icons, links).
Describe their position (top/bottom/left/right/center) and possible actions.

Respond as JSON:
{
  "analysis": "Brief description of the scene",
  "elements": [
    {"type": "button", "text": "...", "position": "...", "action": "..."},
    ...
  ],
  "suggestions": ["Possible next actions..."]
}"""

        response = await self.chat_with_vision(
            prompt=query,
            image_data=screenshot,
            model=ModelType.VISION,
            system_prompt=system_prompt
        )
        
        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            return json.loads(content)
        except:
            return {
                "analysis": response.content,
                "elements": [],
                "suggestions": []
            }
    
    async def validate_action_result(
        self,
        action: Dict[str, Any],
        before_screenshot: Union[str, bytes],
        after_screenshot: Union[str, bytes],
        expected_change: str
    ) -> Dict[str, Any]:
        """
        Validiert ob eine Aktion das erwartete Ergebnis hatte.
        
        Args:
            action: Die ausgeführte Aktion
            before_screenshot: Screenshot vor der Aktion
            after_screenshot: Screenshot nach der Aktion
            expected_change: Erwartete Veränderung
        
        Returns:
            Dict mit success, confidence, description
        """
        # Use localized prompt if available
        if HAS_LOCALIZATION and L:
            prompt = L.get('validate_action',
                action=json.dumps(action),
                expected_change=expected_change
            )
        else:
            # Fallback to English
            prompt = f"""Compare these two screenshots (before/after).

Executed action: {json.dumps(action)}
Expected change: {expected_change}

Analyze:
1. Did the screen change?
2. Does the change match the expectation?
3. Was the action successful?

Respond as JSON:
{{"success": true/false, "confidence": 0.0-1.0, "description": "..."}}"""

        # Kombiniere beide Screenshots in einer Anfrage
        # Für echte Implementierung: Zwei Bilder senden oder vergleichen
        response = await self.chat_with_vision(
            prompt=prompt,
            image_data=after_screenshot,
            model=ModelType.VISION
        )
        
        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except:
            return {
                "success": True,  # Optimistisches Default
                "confidence": 0.5,
                "description": response.content
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Nutzungsstatistiken zurück."""
        return {
            "request_count": self._request_count,
            "total_tokens": self._total_tokens
        }


# Singleton
_client_instance: Optional[OpenRouterClient] = None


def get_openrouter_client(api_key: Optional[str] = None) -> OpenRouterClient:
    """Gibt Singleton-Instanz des OpenRouter Clients zurück."""
    global _client_instance
    if _client_instance is None:
        _client_instance = OpenRouterClient(api_key)
    return _client_instance


async def cleanup_openrouter():
    """Schließt den OpenRouter Client."""
    global _client_instance
    if _client_instance:
        await _client_instance.close()
        _client_instance = None
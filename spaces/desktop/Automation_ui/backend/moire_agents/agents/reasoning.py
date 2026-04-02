"""
Reasoning Agent - Task-Analyse und Action Planning mit Claude Sonnet 4

Verantwortlich für:
- Analyse von Benutzer-Tasks
- Erstellung von Action-Plänen
- Replanning bei Fehlern
- Kontextuelle Entscheidungen
- NEU: Vision-basierte Element-Lokalisierung für Klicks
"""

import asyncio
import logging
import time
import sys
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.openrouter_client import OpenRouterClient, ModelType, get_openrouter_client
from core.event_queue import TaskEvent, ActionEvent, ActionStatus

# Import Vision Agent für Element-Lokalisierung
try:
    from agents.vision_agent import VisionAnalystAgent, get_vision_agent, ElementLocation
    HAS_VISION = True
except ImportError:
    HAS_VISION = False
    ElementLocation = None

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


@dataclass
class ActionPlan:
    """Ein geplanter Aktionsplan."""
    task_id: str
    goal: str
    actions: List[ActionEvent]
    reasoning: str
    confidence: float
    created_at: float


class ReasoningAgent:
    """
    Reasoning Agent - Plant Aktionen für Tasks.
    
    Verwendet Claude Sonnet 4 via OpenRouter für:
    - Task-Analyse und Verständnis
    - Action-Sequenz Planung
    - Fehlerbehandlung und Replanning
    - NEU: Vision-basierte Click-Koordinaten
    """
    
    def __init__(self, openrouter_client: Optional[OpenRouterClient] = None):
        self.client = openrouter_client or get_openrouter_client()
        self.action_counter = 0
        self.plan_history: List[ActionPlan] = []
        
        # Vision Agent für Element-Lokalisierung
        self.vision_agent: Optional[VisionAnalystAgent] = None
        if HAS_VISION:
            try:
                self.vision_agent = get_vision_agent()
                logger.info("Reasoning Agent: Vision Agent verfügbar")
            except Exception as e:
                logger.warning(f"Vision Agent nicht verfügbar: {e}")
        
        # Domänenspezifisches Wissen
        self.domain_knowledge = {
            "windows_apps": {
                "league of legends": ["win", "League of Legends", "enter"],
                "chrome": ["win", "Chrome", "enter"],
                "discord": ["win", "Discord", "enter"],
                "spotify": ["win", "Spotify", "enter"],
                "steam": ["win", "Steam", "enter"],
                "visual studio code": ["win", "Visual Studio Code", "enter"],
                "notepad": ["win", "Notepad", "enter"],
                "word": ["win", "Word", "enter"],
                "excel": ["win", "Excel", "enter"],
                "explorer": ["win", "e"],
                "settings": ["win", "i"],
            },
            "common_patterns": {
                "start_app": ["press_key:win", "wait:0.5", "type:{app_name}", "wait:0.5", "press_key:enter"],
                "close_window": ["press_key:alt+f4"],
                "switch_window": ["press_key:alt+tab"],
                "search": ["press_key:ctrl+f", "type:{query}"],
            },
            # UI-Element Beschreibungen für Vision Agent
            "ui_elements": {
                "leeres dokument": "Blank document option or template",
                "neues dokument": "New document button or option",
                "speichern": "Save button or icon",
                "öffnen": "Open file button or option",
                "schließen": "Close button or X icon",
                "datei": "File menu",
                "bearbeiten": "Edit menu",
                "ansicht": "View menu",
            }
        }
    
    async def plan_task(
        self,
        task: Optional[TaskEvent] = None,
        screen_state: Optional[Dict[str, Any]] = None,
        screenshot_bytes: Optional[bytes] = None,
        # Aliase für flexible Aufrufe
        goal: Optional[str] = None,
        screenshot: Optional[bytes] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[ActionEvent]:
        """
        Plant Aktionen für einen Task.

        Akzeptiert entweder task (TaskEvent) oder goal (string).
        screenshot und screenshot_bytes sind Aliase.

        Args:
            task: Der zu planende Task (TaskEvent)
            screen_state: Aktueller Bildschirmzustand (OCR-Texte etc.)
            screenshot_bytes: Screenshot für Vision-Analyse
            goal: Alternativ zu task - Goal als String
            screenshot: Alias für screenshot_bytes
            context: Zusätzlicher Kontext

        Returns:
            Liste von ActionEvents
        """
        # Normalisiere Parameter
        if task is None and goal:
            task = TaskEvent(
                id=f"task_adhoc_{int(time.time())}",
                goal=goal,
                context=context or {}
            )

        if task is None:
            logger.error("plan_task: Weder task noch goal übergeben!")
            return []

        # Screenshot-Alias
        screenshot_data = screenshot_bytes or screenshot

        logger.info(f"Planning task: {task.goal}")
        
        # Zuerst: Schnelle Pattern-basierte Planung prüfen
        quick_actions = self._try_pattern_match(task.goal)
        if quick_actions:
            logger.info(f"Using pattern match for task: {len(quick_actions)} actions")
            return self._create_action_events(task.id, quick_actions)

        # NEU: Wenn Screenshot verfügbar, nutze Vision Agent für Task-Analyse
        if screenshot_data and self.vision_agent and self.vision_agent.is_available():
            vision_plan = await self._plan_with_vision(task, screenshot_data, screen_state)
            if vision_plan:
                logger.info(f"Using vision-based plan: {len(vision_plan)} actions")
                return vision_plan

        # LLM-basierte Planung mit Screen-State
        try:
            actions_data = await self.client.plan_actions(
                goal=task.goal,
                screen_state=screen_state or {},
                history=self._get_recent_history()
            )

            if actions_data:
                # NEU: Für click-Actions ohne Koordinaten, Vision Agent nutzen
                if screenshot_data:
                    actions_data = await self._enrich_click_actions_with_vision(
                        actions_data, screenshot_data
                    )
                
                actions = self._create_action_events(task.id, actions_data)
                
                # Speichere Plan
                plan = ActionPlan(
                    task_id=task.id,
                    goal=task.goal,
                    actions=actions,
                    reasoning="LLM-generated plan",
                    confidence=0.8,
                    created_at=time.time()
                )
                self.plan_history.append(plan)
                
                logger.info(f"LLM plan created: {len(actions)} actions")
                return actions
            
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
        
        # Fallback: Regelbasierte Planung
        return self._fallback_planning(task)
    
    async def _plan_with_vision(
        self,
        task: TaskEvent,
        screenshot_bytes: bytes,
        screen_state: Optional[Dict[str, Any]]
    ) -> Optional[List[ActionEvent]]:
        """
        Plant Task mit Vision Agent.
        
        Args:
            task: Task
            screenshot_bytes: Screenshot
            screen_state: OCR-State
        
        Returns:
            Liste von ActionEvents oder None
        """
        try:
            from PIL import Image
            from io import BytesIO
            
            image = Image.open(BytesIO(screenshot_bytes))
            
            # Analysiere Screen für Task
            analysis = await self.vision_agent.analyze_screen_for_task(
                image, task.goal
            )
            
            if 'error' in analysis:
                logger.warning(f"Vision analysis failed: {analysis['error']}")
                return None
            
            if not analysis.get('task_completable', False):
                logger.info(f"Vision: Task nicht ausführbar - {analysis.get('reason', 'unknown')}")
                return None
            
            # Baue Actions aus Vision-Analyse
            actions = []
            suggested = analysis.get('suggested_action', {})
            
            if suggested:
                action_type = suggested.get('type', 'wait')
                
                desc_vision = L.get('vision_action') if HAS_LOCALIZATION and L else "Vision-based action"
                action = {
                    "action": action_type,
                    "description": suggested.get('description', desc_vision)
                }
                
                if action_type == 'click':
                    action['x'] = suggested.get('x', 0)
                    action['y'] = suggested.get('y', 0)
                    action['target'] = analysis.get('target_element', {}).get('description', '')
                elif action_type == 'type':
                    action['text'] = suggested.get('text', '')
                elif action_type == 'press_key':
                    action['key'] = suggested.get('key', '')
                elif action_type == 'wait':
                    action['duration'] = suggested.get('duration', 1.0)
                
                actions.append(action)
            
            if actions:
                return self._create_action_events(task.id, actions)
            
            return None
        
        except Exception as e:
            logger.error(f"_plan_with_vision failed: {e}")
            return None
    
    async def _enrich_click_actions_with_vision(
        self,
        actions_data: List[Dict[str, Any]],
        screenshot_bytes: bytes
    ) -> List[Dict[str, Any]]:
        """
        Reichert click-Actions mit Vision-basierten Koordinaten an.
        
        Args:
            actions_data: Liste von Action-Dicts
            screenshot_bytes: Screenshot für Vision
        
        Returns:
            Angereicherte Actions
        """
        if not self.vision_agent or not self.vision_agent.is_available():
            return actions_data
        
        enriched = []
        
        for action in actions_data:
            if action.get('action') == 'click':
                # Prüfe ob Koordinaten fehlen oder auf Default stehen
                x = action.get('x')
                y = action.get('y')
                target = action.get('target', action.get('description', ''))
                
                needs_vision = (
                    x is None or y is None or
                    (x == 0 and y == 0) or
                    (x == 960 and y == 400)  # Bildschirmmitte = blind
                )
                
                if needs_vision and target:
                    logger.info(f"Using Vision to find: {target}")
                    
                    # Vision Agent für Element-Suche nutzen
                    location = await self.vision_agent.find_element_from_screenshot(
                        screenshot_bytes,
                        target
                    )
                    
                    if location.found and location.confidence > 0.5:
                        action['x'] = location.x
                        action['y'] = location.y
                        action['vision_confidence'] = location.confidence
                        action['vision_description'] = location.description

                        # ROI berechnen basierend auf Element-Typ
                        element_type = location.element_type or 'button'
                        action['roi'] = self._calculate_roi(
                            origin_x=location.x,
                            origin_y=location.y,
                            element_type=element_type
                        )
                        action['roi_description'] = location.description

                        logger.info(f"Vision found element at ({location.x}, {location.y}) with ROI zoom={action['roi']['zoom']}")
                    else:
                        logger.warning(f"Vision could not find: {target}")
            
            enriched.append(action)
        
        return enriched
    
    async def find_element_for_click(
        self,
        screenshot_bytes: bytes,
        element_description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Public method: Findet Element für Klick via Vision.
        
        Args:
            screenshot_bytes: Screenshot
            element_description: Was gesucht wird
        
        Returns:
            Dict mit x, y, confidence oder None
        """
        if not self.vision_agent or not self.vision_agent.is_available():
            return None
        
        location = await self.vision_agent.find_element_from_screenshot(
            screenshot_bytes,
            element_description
        )
        
        if location.found:
            return {
                'x': location.x,
                'y': location.y,
                'confidence': location.confidence,
                'description': location.description,
                'element_type': location.element_type
            }
        
        return None
    
    def _calculate_roi(
        self,
        origin_x: int,
        origin_y: int,
        element_type: str = "button",
        zoom: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Berechnet ROI für fokussierte Validierung.

        Args:
            origin_x: X-Koordinate des Elements (Zentrum)
            origin_y: Y-Koordinate des Elements (Zentrum)
            element_type: Typ des UI-Elements
            zoom: Optionaler Zoom-Faktor (überschreibt Default)

        Returns:
            ROI dict mit origin_x, origin_y, base_width, base_height, zoom
        """
        # Element-Größen nach Typ
        element_sizes = {
            "button": (100, 40),
            "text_field": (250, 35),
            "icon": (40, 40),
            "menu_item": (200, 30),
            "checkbox": (30, 30),
            "dropdown": (150, 35),
            "link": (100, 25),
            "tab": (120, 35),
            "slider": (200, 30),
            "default": (150, 60)
        }

        # Zoom-Empfehlungen nach Element-Typ
        zoom_recommendations = {
            "button": 1.5,
            "icon": 2.0,
            "text_field": 1.3,
            "dropdown": 2.5,
            "menu_item": 1.8,
            "checkbox": 2.0,
            "link": 1.5,
            "tab": 1.5,
            "slider": 1.5,
            "default": 1.5
        }

        base_w, base_h = element_sizes.get(element_type, element_sizes["default"])
        default_zoom = zoom_recommendations.get(element_type, 1.5)

        return {
            "origin_x": origin_x,
            "origin_y": origin_y,
            "base_width": base_w,
            "base_height": base_h,
            "zoom": zoom if zoom is not None else default_zoom
        }

    def _try_pattern_match(self, goal: str) -> Optional[List[Dict[str, Any]]]:
        """Versucht Pattern-basierte Planung."""
        goal_lower = goal.lower()
        
        # Check für App-Start
        if "starte" in goal_lower or "start" in goal_lower or "öffne" in goal_lower or "open" in goal_lower:
            # Extrahiere App-Name
            for app_name, keys in self.domain_knowledge["windows_apps"].items():
                if app_name in goal_lower:
                    actions = []

                    # Windows key - use localized descriptions
                    desc_win = L.get('press_win_key') if HAS_LOCALIZATION and L else "Press Windows key"
                    desc_wait_menu = L.get('wait_for_start_menu') if HAS_LOCALIZATION and L else "Wait for start menu"
                    desc_wait_search = L.get('wait_for_search') if HAS_LOCALIZATION and L else "Wait for search results"
                    desc_enter = L.get('press_enter') if HAS_LOCALIZATION and L else "Press Enter to start"

                    actions.append({
                        "action": "press_key",
                        "key": "win",
                        "description": desc_win
                    })
                    actions.append({
                        "action": "wait",
                        "duration": 0.7,
                        "description": desc_wait_menu
                    })

                    # Type app name
                    search_term = keys[1] if len(keys) > 1 else app_name
                    desc_type = L.get('type_text', text=search_term) if HAS_LOCALIZATION and L else f"Type '{search_term}'"
                    actions.append({
                        "action": "type",
                        "text": search_term,
                        "description": desc_type
                    })
                    actions.append({
                        "action": "wait",
                        "duration": 0.5,
                        "description": desc_wait_search
                    })

                    # Press Enter
                    actions.append({
                        "action": "press_key",
                        "key": "enter",
                        "description": desc_enter
                    })

                    # Wait for app start
                    desc_wait_app = L.get('wait_for_app', app=app_name) if HAS_LOCALIZATION and L else f"Wait for {app_name} to start"
                    actions.append({
                        "action": "wait",
                        "duration": 2.0,
                        "description": desc_wait_app
                    })

                    # WICHTIG: Für sequentielle Abläufe can_parallel=False setzen
                    # Win+Wait+Type+Wait+Enter müssen SEQUENTIELL laufen!
                    for action in actions:
                        action["can_parallel"] = False

                    return actions
        
        # Klick-Aktionen - brauchen IMMER Vision für Koordinaten
        if "klick" in goal_lower or "click" in goal_lower:
            # Extrahiere Ziel-Beschreibung
            target = goal_lower
            for word in ["klicke auf", "click on", "klick", "click", "drücke", "press"]:
                target = target.replace(word, "")
            target = target.strip()
            
            if target:
                # Create Click-Action with Target for Vision-Enrichment
                desc_click = L.get('click_on', target=target) if HAS_LOCALIZATION and L else f"Click on: {target}"
                return [{
                    "action": "click",
                    "target": target,
                    "x": None,  # Filled by Vision
                    "y": None,
                    "description": desc_click
                }]
        
        return None
    
    def _create_action_events(
        self,
        task_id: str,
        actions_data: List[Dict[str, Any]]
    ) -> List[ActionEvent]:
        """Erstellt ActionEvent-Objekte aus Action-Dicts."""
        events = []
        prev_action_id: Optional[str] = None
        prev_can_parallel: bool = True

        for i, action_dict in enumerate(actions_data):
            self.action_counter += 1

            action_type = action_dict.get("action", "unknown")
            params = {}
            
            # Extrahiere Parameter basierend auf Action-Typ
            if action_type == "press_key":
                params["key"] = action_dict.get("key", "")
            elif action_type == "type":
                params["text"] = action_dict.get("text", "")
            elif action_type == "click":
                params["x"] = action_dict.get("x")
                params["y"] = action_dict.get("y")
                params["target"] = action_dict.get("target")
                # Vision-Metadaten
                if "vision_confidence" in action_dict:
                    params["vision_confidence"] = action_dict["vision_confidence"]
                if "vision_description" in action_dict:
                    params["vision_description"] = action_dict["vision_description"]
            elif action_type == "wait":
                params["duration"] = action_dict.get("duration", 1.0)
            elif action_type == "scroll":
                params["direction"] = action_dict.get("direction", "down")
                params["amount"] = action_dict.get("amount", 3)
            
            # Kopiere alle anderen Parameter
            for key, value in action_dict.items():
                if key not in ["action", "description"] and key not in params:
                    params[key] = value
            
            # ROI extrahieren wenn vorhanden
            roi = action_dict.get("roi")
            roi_description = action_dict.get("roi_description")

            # can_parallel extrahieren (Default: True für Parallelisierung)
            can_parallel = action_dict.get("can_parallel", True)

            # Action ID generieren
            action_id = f"action_{self.action_counter}_{int(time.time())}"

            # Automatische Dependency-Kette: Wenn can_parallel=False,
            # hängt diese Action von der vorherigen ab
            depends_on = []
            if not can_parallel and prev_action_id is not None:
                depends_on = [prev_action_id]

            event = ActionEvent(
                id=action_id,
                task_id=task_id,
                action_type=action_type,
                params=params,
                description=action_dict.get("description", f"Schritt {i + 1}: {action_type}"),
                status=ActionStatus.PENDING,
                roi=roi,
                roi_description=roi_description,
                can_parallel=can_parallel,
                depends_on=depends_on
            )
            events.append(event)
            logger.info(f"📋 Created action {action_id}: type={action_type}, can_parallel={can_parallel}, depends_on={depends_on}")

            # Merke für nächste Iteration
            prev_action_id = action_id
            prev_can_parallel = can_parallel

        return events
    
    def _fallback_planning(self, task: TaskEvent) -> List[ActionEvent]:
        """Fallback-Planung ohne LLM."""
        goal_lower = task.goal.lower()
        actions = []
        
        # Generische App-Start Logik
        if any(word in goal_lower for word in ["starte", "start", "öffne", "open", "launch"]):
            # Extrahiere was gestartet werden soll
            app_name = goal_lower
            for word in ["starte", "start", "öffne", "open", "launch", "die app", "das programm"]:
                app_name = app_name.replace(word, "")
            app_name = app_name.strip()
            
            # Use localized descriptions
            if HAS_LOCALIZATION and L:
                actions = [
                    {"action": "press_key", "key": "win", "description": L.get('press_win_key'), "can_parallel": False},
                    {"action": "wait", "duration": 0.7, "description": L.get('wait_for_start_menu'), "can_parallel": False},
                    {"action": "type", "text": app_name, "description": L.get('type_text', text=app_name), "can_parallel": False},
                    {"action": "wait", "duration": 0.5, "description": L.get('wait_for_search'), "can_parallel": False},
                    {"action": "press_key", "key": "enter", "description": L.get('press_enter'), "can_parallel": False},
                    {"action": "wait", "duration": 2.0, "description": L.get('wait_for_app', app=app_name), "can_parallel": False}
                ]
            else:
                actions = [
                    {"action": "press_key", "key": "win", "description": "Press Windows key", "can_parallel": False},
                    {"action": "wait", "duration": 0.7, "description": "Wait for start menu", "can_parallel": False},
                    {"action": "type", "text": app_name, "description": f"Type '{app_name}'", "can_parallel": False},
                    {"action": "wait", "duration": 0.5, "description": "Wait for search results", "can_parallel": False},
                    {"action": "press_key", "key": "enter", "description": "Press Enter", "can_parallel": False},
                    {"action": "wait", "duration": 2.0, "description": f"Wait for {app_name} to start", "can_parallel": False}
                ]
        
        elif "schließe" in goal_lower or "close" in goal_lower:
            actions = [
                {"action": "press_key", "key": "alt+f4", "description": "Alt+F4 to close" if not (HAS_LOCALIZATION and L) else "Alt+F4 zum Schließen"}
            ]

        else:
            # Minimal plan: Screenshot and analysis
            actions = [
                {"action": "capture", "description": "Capture screenshot" if not (HAS_LOCALIZATION and L) else "Screenshot aufnehmen"},
                {"action": "wait", "duration": 1.0, "description": "Wait and analyze" if not (HAS_LOCALIZATION and L) else "Warten und analysieren"}
            ]
        
        return self._create_action_events(task.id, actions)
    
    async def replan_on_failure(
        self,
        task: TaskEvent,
        failed_action: ActionEvent,
        error: str,
        screen_state: Optional[Dict[str, Any]] = None,
        screenshot_bytes: Optional[bytes] = None
    ) -> List[ActionEvent]:
        """
        Plant bei Fehlschlag neu.
        
        Args:
            task: Der Task
            failed_action: Die fehlgeschlagene Aktion
            error: Fehlermeldung
            screen_state: Aktueller Bildschirmzustand
            screenshot_bytes: Screenshot für Vision-Analyse
        
        Returns:
            Neue Liste von ActionEvents
        """
        logger.warning(f"Replanning for task {task.id} after failure: {error}")
        
        # NEU: Bei click-Failures, versuche Vision-basierte Neuplanung
        if failed_action.action_type == "click" and screenshot_bytes and self.vision_agent:
            target = failed_action.params.get('target', failed_action.description)
            logger.info(f"Trying vision-based replan for click: {target}")
            
            location = await self.vision_agent.find_element_from_screenshot(
                screenshot_bytes, target
            )
            
            if location.found and location.confidence > 0.5:
                # New Click attempt with Vision coordinates
                desc_vision_click = L.get('vision_click', target=location.description) if HAS_LOCALIZATION and L else f"Vision-based click on: {location.description}"
                return self._create_action_events(task.id, [{
                    "action": "click",
                    "x": location.x,
                    "y": location.y,
                    "target": target,
                    "vision_confidence": location.confidence,
                    "description": desc_vision_click
                }])
        
        # Erstelle Kontext für Replanning
        context = {
            "original_goal": task.goal,
            "failed_action": {
                "type": failed_action.action_type,
                "params": failed_action.params,
                "error": error
            },
            "completed_actions": [
                {"type": a.action_type, "result": a.result}
                for a in task.actions if a.status == ActionStatus.COMPLETED
            ],
            "attempt": task.retry_count + 1
        }
        
        # LLM-basiertes Replanning
        try:
            # Use localized prompts if available
            if HAS_LOCALIZATION and L:
                system_prompt = L.get('error_recovery')
                user_prompt = f"""{L.get('goal')}: {task.goal}

{L.get('error')}:
- Type: {failed_action.action_type}
- Parameters: {failed_action.params}
- Error: {error}

Completed actions: {len(context['completed_actions'])}

{L.get('screen_state')}:
{screen_state if screen_state else 'Not available'}

{L.get('action_plan')}"""
            else:
                # Fallback to English
                system_prompt = """You are a UI automation expert. An action has failed.
Analyze the error and create an alternative plan.

Note:
- The previous attempt failed
- Try a different approach
- Avoid the same error source

Respond as a JSON array with actions."""

                user_prompt = f"""Original goal: {task.goal}

Failed action:
- Type: {failed_action.action_type}
- Parameters: {failed_action.params}
- Error: {error}

Already completed actions: {len(context['completed_actions'])}

Screen state:
{screen_state if screen_state else 'Not available'}

Create an alternative action plan:"""

            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=ModelType.REASONING,
                json_mode=True
            )
            
            import json
            actions_data = json.loads(response.content)
            if isinstance(actions_data, dict) and 'actions' in actions_data:
                actions_data = actions_data['actions']
            
            if actions_data:
                # Enriche click-Actions mit Vision
                if screenshot_bytes:
                    actions_data = await self._enrich_click_actions_with_vision(
                        actions_data, screenshot_bytes
                    )
                return self._create_action_events(task.id, actions_data)
        
        except Exception as e:
            logger.error(f"Replanning failed: {e}")
        
        # Einfaches Fallback: Nochmal versuchen mit längeren Wartezeiten
        alternative_actions = []
        for action in task.actions:
            if action.status != ActionStatus.COMPLETED:
                action_dict = {
                    "action": action.action_type,
                    **action.params,
                    "description": action.description
                }
                # Verdopple Wartezeiten
                if action.action_type == "wait":
                    action_dict["duration"] = action.params.get("duration", 1.0) * 2
                alternative_actions.append(action_dict)
        
        return self._create_action_events(task.id, alternative_actions)
    
    def _get_recent_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Gibt die letzten Plan-Historien zurück."""
        history = []
        for plan in self.plan_history[-limit:]:
            history.append({
                "goal": plan.goal,
                "actions_count": len(plan.actions),
                "success": all(a.status == ActionStatus.COMPLETED for a in plan.actions)
            })
        return history
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        total_plans = len(self.plan_history)
        successful_plans = sum(
            1 for p in self.plan_history
            if all(a.status == ActionStatus.COMPLETED for a in p.actions)
        )
        
        return {
            "total_plans": total_plans,
            "successful_plans": successful_plans,
            "success_rate": successful_plans / total_plans if total_plans > 0 else 0,
            "total_actions_created": self.action_counter,
            "vision_available": self.vision_agent is not None and self.vision_agent.is_available()
        }


# Singleton
_reasoning_instance: Optional[ReasoningAgent] = None


def get_reasoning_agent(client: Optional[OpenRouterClient] = None) -> ReasoningAgent:
    """Gibt Singleton-Instanz des Reasoning Agents zurück."""
    global _reasoning_instance
    if _reasoning_instance is None:
        _reasoning_instance = ReasoningAgent(client)
    return _reasoning_instance


def reset_reasoning_agent():
    """Setzt Reasoning Agent zurück."""
    global _reasoning_instance
    _reasoning_instance = None
"""
Desktop Client Tools für Voice Agent (Adam)

Diese Tools ermöglichen Adam, Desktop-Automation via externem MoireTracker v2 auszuführen.
Nutzt das originale MoireTracker v2 Projekt unter:
  C:/Users/User/Desktop/Moire_tracker_v1/MoireTracker_v2/python

Tools:
1. execute_desktop_task - Führt komplexen Task aus (öffne App, erstelle Dokument, etc.)
2. click_element - Klickt auf UI-Element anhand Beschreibung
3. type_text - Tippt Text ein
4. press_key - Drückt Taste(n)
5. take_screenshot - Macht Screenshot zur Analyse
6. scroll_screen - Scrollt den Bildschirm
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any, Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Import external MoireTracker bridge
import moire_external as moire


# ==================== Client Tool Functions ====================

async def execute_desktop_task(goal: str) -> Dict[str, Any]:
    """
    Führt einen komplexen Desktop-Task aus.
    
    Der Task wird vom ReasoningAgent analysiert und in mehrere Aktionen
    aufgeteilt, die dann automatisch ausgeführt werden.
    
    Args:
        goal: Beschreibung des Ziels
              Beispiele:
              - "Öffne Word und erstelle ein neues leeres Dokument"
              - "Starte Chrome und navigiere zu google.com"
              - "Öffne den Explorer und gehe zu Downloads"
    
    Returns:
        Dict mit:
        - success: bool
        - message: Beschreibung des Ergebnisses
        - actions_executed: Anzahl ausgeführter Aktionen
        - duration_seconds: Dauer in Sekunden
    """
    try:
        result = await moire.execute_task(goal, timeout=120.0)

        # Buffer action for Rowboat MongoDB (for Brain seeding)
        if result.success:
            try:
                from publishing import get_ideas_publisher
                pub = get_ideas_publisher()
                if hasattr(pub, 'buffer_desktop_action'):
                    pub.buffer_desktop_action(
                        result.task_id or "default",
                        {
                            "action_type": "execute_desktop_task",
                            "target": goal,
                            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
                            "duration_seconds": round(result.duration_seconds, 2),
                            "actions_executed": result.actions_executed,
                        },
                    )
            except Exception:
                pass

        return {
            "success": result.success,
            "message": result.message,
            "task_id": result.task_id,
            "actions_executed": result.actions_executed,
            "duration_seconds": round(result.duration_seconds, 2),
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"execute_desktop_task failed: {e}")
        return {
            "success": False,
            "message": f"Fehler bei Task-Ausführung: {str(e)}",
            "error": str(e)
        }


async def click_element(element_description: str) -> Dict[str, Any]:
    """
    Klickt auf ein UI-Element basierend auf seiner Beschreibung.
    
    Verwendet Vision AI um das Element auf dem Bildschirm zu finden
    und klickt dann darauf.
    
    Args:
        element_description: Beschreibung des Elements
                            Beispiele:
                            - "Speichern Button"
                            - "Datei Menü"
                            - "Suchfeld"
    
    Returns:
        Dict mit:
        - success: bool
        - message: Beschreibung der Aktion
        - error: Optional Fehlermeldung
    """
    try:
        # Click element wird als komplexer Task ausgeführt
        result = await moire.execute_task(f"Klicke auf: {element_description}", timeout=30.0)
        
        return {
            "success": result.success,
            "message": result.message,
            "action_type": "click_element",
            "duration_ms": result.duration_seconds * 1000,
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"click_element failed: {e}")
        return {
            "success": False,
            "message": f"Klick fehlgeschlagen: {str(e)}",
            "error": str(e)
        }


async def type_text(text: str) -> Dict[str, Any]:
    """
    Tippt den angegebenen Text ein.
    
    Der Text wird an der aktuellen Cursor-Position eingegeben.
    Stelle sicher, dass vorher das richtige Eingabefeld fokussiert ist.
    
    Args:
        text: Der einzugebende Text
    
    Returns:
        Dict mit:
        - success: bool
        - message: Bestätigung
        - error: Optional Fehlermeldung
    """
    try:
        result = await moire.type_text(text)
        
        return {
            "success": result.success,
            "message": result.message,
            "action_type": result.action_type,
            "duration_ms": round(result.duration_ms, 1),
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"type_text failed: {e}")
        return {
            "success": False,
            "message": f"Texteingabe fehlgeschlagen: {str(e)}",
            "error": str(e)
        }


async def press_key(key: str) -> Dict[str, Any]:
    """
    Drückt eine Taste oder Tastenkombination.
    
    Args:
        key: Die zu drückende Taste
             Einzelne Tasten: "enter", "tab", "escape", "space", etc.
             Kombinationen: "ctrl+c", "ctrl+v", "ctrl+s", "alt+tab", etc.
    
    Returns:
        Dict mit:
        - success: bool
        - message: Bestätigung
        - error: Optional Fehlermeldung
    """
    try:
        result = await moire.press_key(key)
        
        return {
            "success": result.success,
            "message": result.message,
            "action_type": result.action_type,
            "duration_ms": round(result.duration_ms, 1),
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"press_key failed: {e}")
        return {
            "success": False,
            "message": f"Tastendruck fehlgeschlagen: {str(e)}",
            "error": str(e)
        }


async def take_screenshot() -> Dict[str, Any]:
    """
    Macht einen Screenshot des aktuellen Bildschirms.
    
    Returns:
        Dict mit:
        - success: bool
        - message: Status
        - has_screenshot: bool - ob Screenshot verfügbar
        - screenshot_base64: Base64-encodierter Screenshot (wenn success)
    """
    try:
        success, screenshot_b64 = await moire.take_screenshot()
        
        if success and screenshot_b64:
            return {
                "success": True,
                "message": "Screenshot aufgenommen",
                "has_screenshot": True,
                "screenshot_base64": screenshot_b64
            }
        else:
            return {
                "success": False,
                "message": "Screenshot fehlgeschlagen",
                "has_screenshot": False
            }
    
    except Exception as e:
        logger.error(f"take_screenshot failed: {e}")
        return {
            "success": False,
            "message": f"Screenshot fehlgeschlagen: {str(e)}",
            "error": str(e)
        }


async def scroll_screen(direction: str = "down", amount: int = 3) -> Dict[str, Any]:
    """
    Scrollt den Bildschirm in die angegebene Richtung.
    
    Args:
        direction: "up" oder "down"
        amount: Anzahl der Scroll-Schritte (Standard: 3)
    
    Returns:
        Dict mit:
        - success: bool
        - message: Status
    """
    try:
        result = await moire.scroll(direction, amount)
        
        return {
            "success": result.success,
            "message": result.message,
            "action_type": result.action_type,
            "duration_ms": round(result.duration_ms, 1),
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"scroll_screen failed: {e}")
        return {
            "success": False,
            "message": f"Scroll fehlgeschlagen: {str(e)}",
            "error": str(e)
        }


# ==================== Tool Definitions ====================

DESKTOP_TOOLS = [
    {
        "name": "execute_desktop_task",
        "description": "Führt einen komplexen Desktop-Task aus. Der Task wird automatisch in einzelne Aktionen aufgeteilt und ausgeführt. Beispiele: 'Öffne Word', 'Starte Chrome und gehe zu google.com', 'Öffne Notepad und schreibe Hello World'",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Beschreibung des auszuführenden Tasks"
                }
            },
            "required": ["goal"]
        }
    },
    {
        "name": "click_element",
        "description": "Klickt auf ein UI-Element. Verwendet Vision AI um das Element zu finden. Beispiele: 'Speichern Button', 'Datei Menü', 'Schließen X'",
        "parameters": {
            "type": "object",
            "properties": {
                "element_description": {
                    "type": "string",
                    "description": "Beschreibung des UI-Elements das angeklickt werden soll"
                }
            },
            "required": ["element_description"]
        }
    },
    {
        "name": "type_text",
        "description": "Tippt Text an der aktuellen Cursor-Position ein",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Der einzugebende Text"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "press_key",
        "description": "Drückt eine Taste oder Tastenkombination. Einzelne Tasten: enter, tab, escape, win, f1-f12. Kombinationen: ctrl+c, ctrl+v, alt+tab, win+e",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string", 
                    "description": "Die Taste oder Kombination (z.B. 'enter', 'ctrl+s', 'alt+f4')"
                }
            },
            "required": ["key"]
        }
    },
    {
        "name": "take_screenshot",
        "description": "Macht einen Screenshot des aktuellen Bildschirms zur Analyse",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "scroll_screen",
        "description": "Scrollt den Bildschirm nach oben oder unten",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll-Richtung"
                },
                "amount": {
                    "type": "integer",
                    "description": "Anzahl der Scroll-Schritte",
                    "default": 3
                }
            },
            "required": ["direction"]
        }
    }
]


# ==================== Tool Handler ====================

async def handle_desktop_tool_call(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handler für Desktop Tool Calls.

    Diese Funktion wird vom Voice Client aufgerufen wenn
    Adam ein Desktop Tool nutzen will.
    
    Args:
        tool_name: Name des Tools
        parameters: Parameter für das Tool
    
    Returns:
        Tool-Ergebnis als Dict
    """
    tool_map = {
        "execute_desktop_task": lambda p: execute_desktop_task(p.get("goal", "")),
        "click_element": lambda p: click_element(p.get("element_description", "")),
        "type_text": lambda p: type_text(p.get("text", "")),
        "press_key": lambda p: press_key(p.get("key", "")),
        "take_screenshot": lambda p: take_screenshot(),
        "scroll_screen": lambda p: scroll_screen(
            p.get("direction", "down"),
            p.get("amount", 3)
        )
    }
    
    if tool_name not in tool_map:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }
    
    return await tool_map[tool_name](parameters)


# ==================== Cleanup ====================

async def cleanup_desktop_tools():
    """Bereinigt Ressourcen der Desktop Tools."""
    await moire.shutdown()
    logger.info("Desktop tools cleaned up")


# ==================== Registration for voice_dialog_main ====================

def register_desktop_tools(tools_manager) -> None:
    """
    Registriert Desktop Tools im ClientToolsManager.

    WICHTIG: Diese Funktion muss in voice_dialog_main.py aufgerufen werden,
    damit Adam's Desktop Tool Calls korrekt ausgeführt werden.

    Args:
        tools_manager: ClientToolsManager instance
    """
    logger.debug("register_desktop_tools called")
    print("Registering desktop tools...")
    
    # Wrapper functions that call async functions synchronously
    def execute_desktop_task_wrapper(params):
        goal = params.get("goal", "")
        if not goal:
            return {"success": False, "error": "No goal specified"}
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, create new loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, execute_desktop_task(goal))
                    return future.result()
            else:
                return asyncio.run(execute_desktop_task(goal))
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def click_element_wrapper(params):
        element_description = params.get("element_description", "")
        if not element_description:
            return {"success": False, "error": "No element description specified"}
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, click_element(element_description))
                    return future.result()
            else:
                return asyncio.run(click_element(element_description))
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def type_text_wrapper(params):
        text = params.get("text", "")
        if not text:
            return {"success": False, "error": "No text specified"}
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, type_text(text))
                    return future.result()
            else:
                return asyncio.run(type_text(text))
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def press_key_wrapper(params):
        key = params.get("key", "")
        if not key:
            return {"success": False, "error": "No key specified"}
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, press_key(key))
                    return future.result()
            else:
                return asyncio.run(press_key(key))
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def take_screenshot_wrapper(params):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, take_screenshot())
                    return future.result()
            else:
                return asyncio.run(take_screenshot())
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def scroll_screen_wrapper(params):
        direction = params.get("direction", "down")
        amount = params.get("amount", 3)
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, scroll_screen(direction, amount))
                    return future.result()
            else:
                return asyncio.run(scroll_screen(direction, amount))
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # Register all desktop tools
    tools_manager.register_with_observer("execute_desktop_task", execute_desktop_task_wrapper)
    print("  - execute_desktop_task")
    
    tools_manager.register_with_observer("click_element", click_element_wrapper)
    print("  - click_element")
    
    tools_manager.register_with_observer("type_text", type_text_wrapper)
    print("  - type_text")
    
    tools_manager.register_with_observer("press_key", press_key_wrapper)
    print("  - press_key")
    
    tools_manager.register_with_observer("take_screenshot", take_screenshot_wrapper)
    print("  - take_screenshot")
    
    tools_manager.register_with_observer("scroll_screen", scroll_screen_wrapper)
    print("  - scroll_screen")
    
    print(f"Desktop tools registered ({6} tools)")


# ==================== Test ====================

async def test_desktop_tools():
    """Test-Funktion für Desktop Tools."""
    logger.debug("test_desktop_tools called")
    print("Testing Desktop Tools (External MoireTracker v2)...")
    
    # Test press_key
    result = await press_key("win")
    print(f"Press Win: {result}")
    
    await asyncio.sleep(1)
    
    result = await press_key("escape")
    print(f"Press Escape: {result}")
    
    # Test screenshot
    result = await take_screenshot()
    print(f"Screenshot: success={result['success']}, has_screenshot={result.get('has_screenshot', False)}")
    
    # Cleanup
    await cleanup_desktop_tools()
    
    print("Desktop Tools test completed")


if __name__ == "__main__":
    asyncio.run(test_desktop_tools())
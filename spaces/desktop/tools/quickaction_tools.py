"""
Quick Action Tools für Desktop Automation

Schnelle Aktionen zum Öffnen und Verwenden von Apps.
Nutzt MoireTracker für die Ausführung.

Tools:
1. open_app - Öffnet eine Anwendung schnell
2. use_app - Interagiert mit einer laufenden App
"""

import asyncio
import logging
import os
import subprocess
import sys
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Common app shortcuts für Windows
APP_SHORTCUTS = {
    # Browser
    "chrome": "chrome",
    "google chrome": "chrome", 
    "firefox": "firefox",
    "edge": "msedge",
    "microsoft edge": "msedge",
    
    # Microsoft Office
    "word": "winword",
    "microsoft word": "winword",
    "excel": "excel",
    "microsoft excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "teams": "msteams",
    
    # Development
    "vscode": "code",
    "visual studio code": "code",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "terminal": "cmd",
    "cmd": "cmd",
    "powershell": "powershell",
    
    # Media
    "spotify": "spotify",
    "vlc": "vlc",
    
    # Communication
    "slack": "slack",
    "discord": "discord",
    "zoom": "zoom",
    
    # Utilities
    "explorer": "explorer",
    "file explorer": "explorer",
    "calculator": "calc",
    "task manager": "taskmgr",
    "settings": "ms-settings:",
    "control panel": "control"
}


async def open_app(app_name: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Öffnet eine Anwendung schnell.
    
    Unterstützt bekannte Apps wie Chrome, Word, VSCode etc.
    Bei Browsern kann optional eine URL mitgegeben werden.
    
    Args:
        app_name: Name der App (z.B. "chrome", "word", "vscode")
        url: Optional - URL für Browser
    
    Returns:
        Dict mit Erfolg und Info
    """
    try:
        app_lower = app_name.lower().strip()
        
        # Bekannte App?
        if app_lower in APP_SHORTCUTS:
            executable = APP_SHORTCUTS[app_lower]
        else:
            # Versuche direkt
            executable = app_name
        
        # Browser mit URL?
        is_browser = app_lower in ["chrome", "google chrome", "firefox", 
                                    "edge", "microsoft edge"]
        
        if sys.platform == "win32":
            if is_browser and url:
                # Browser mit URL öffnen
                subprocess.Popen(
                    ["start", "", executable, url],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif executable.startswith("ms-"):
                # Windows URI scheme
                os.startfile(executable)
            else:
                # Normale App
                subprocess.Popen(
                    ["start", "", executable],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        else:
            # Linux/Mac
            if is_browser and url:
                subprocess.Popen([executable, url])
            else:
                subprocess.Popen([executable])
        
        message = f"App '{app_name}' geöffnet"
        if url:
            message += f" mit URL: {url}"
        
        logger.info(message)
        
        return {
            "success": True,
            "message": message,
            "app": app_name,
            "executable": executable,
            "url": url
        }
        
    except Exception as e:
        logger.error(f"open_app failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "app": app_name
        }


async def use_app(
    app_name: str,
    action: str,
    parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Führt eine Aktion in einer laufenden App aus.
    
    Nutzt MoireTracker für komplexe Interaktionen.
    
    Args:
        app_name: Name der App (z.B. "chrome", "word")
        action: Aktion wie "type", "click", "navigate", "save"
        parameters: Parameter für die Aktion
    
    Returns:
        Dict mit Ergebnis
    
    Beispiele:
        use_app("chrome", "navigate", {"url": "google.com"})
        use_app("word", "type", {"text": "Hello World"})
        use_app("word", "save", {"filename": "document.docx"})
    """
    try:
        params = parameters or {}
        
        # Import MoireTracker wenn vorhanden
        try:
            from moire_external import execute_task
            has_moire = True
        except ImportError:
            has_moire = False
        
        # Aktion zu Task-Beschreibung konvertieren
        app_lower = app_name.lower()
        action_lower = action.lower()
        
        if action_lower == "navigate" and "url" in params:
            if has_moire:
                goal = f"In {app_name}: Navigiere zu {params['url']}"
                result = await execute_task(goal, timeout=30.0)
                return {
                    "success": result.success,
                    "message": f"Navigiert zu {params['url']}",
                    "moire_result": result.to_dict() if hasattr(result, 'to_dict') else str(result)
                }
            else:
                # Fallback: Browser öffnen mit URL
                return await open_app(app_name, params['url'])
        
        elif action_lower == "type" and "text" in params:
            if has_moire:
                goal = f"In {app_name}: Tippe den Text '{params['text']}'"
                result = await execute_task(goal, timeout=30.0)
                return {
                    "success": result.success,
                    "message": f"Text getippt in {app_name}",
                    "text": params['text']
                }
            else:
                # Fallback: PyAutoGUI direkt
                try:
                    import pyautogui
                    pyautogui.write(params['text'])
                    return {
                        "success": True,
                        "message": f"Text getippt: {params['text'][:50]}...",
                        "method": "pyautogui"
                    }
                except ImportError:
                    return {
                        "success": False,
                        "error": "PyAutoGUI nicht verfügbar"
                    }
        
        elif action_lower == "click" and "element" in params:
            if has_moire:
                goal = f"In {app_name}: Klicke auf '{params['element']}'"
                result = await execute_task(goal, timeout=30.0)
                return {
                    "success": result.success,
                    "message": f"Geklickt auf {params['element']}"
                }
            else:
                return {
                    "success": False,
                    "error": "MoireTracker benötigt für Klick-Aktionen"
                }
        
        elif action_lower == "save":
            filename = params.get("filename", "")
            if has_moire:
                goal = f"In {app_name}: Speichere Datei"
                if filename:
                    goal += f" als '{filename}'"
                result = await execute_task(goal, timeout=30.0)
                return {
                    "success": result.success,
                    "message": f"Datei gespeichert in {app_name}",
                    "filename": filename
                }
            else:
                # Fallback: Strg+S
                try:
                    import pyautogui
                    pyautogui.hotkey('ctrl', 's')
                    return {
                        "success": True,
                        "message": "Strg+S gedrückt",
                        "method": "pyautogui"
                    }
                except ImportError:
                    return {
                        "success": False,
                        "error": "PyAutoGUI nicht verfügbar"
                    }
        
        elif action_lower == "close":
            if has_moire:
                goal = f"Schließe {app_name}"
                result = await execute_task(goal, timeout=15.0)
                return {
                    "success": result.success,
                    "message": f"{app_name} geschlossen"
                }
            else:
                try:
                    import pyautogui
                    pyautogui.hotkey('alt', 'F4')
                    return {
                        "success": True,
                        "message": "Alt+F4 gedrückt",
                        "method": "pyautogui"
                    }
                except ImportError:
                    return {
                        "success": False,
                        "error": "PyAutoGUI nicht verfügbar"
                    }
        
        else:
            # Generische Aktion via MoireTracker
            if has_moire:
                goal = f"In {app_name}: {action}"
                if params:
                    goal += f" mit {params}"
                result = await execute_task(goal, timeout=60.0)
                return {
                    "success": result.success,
                    "message": f"Aktion '{action}' ausgeführt in {app_name}",
                    "moire_result": str(result)
                }
            else:
                return {
                    "success": False,
                    "error": f"Aktion '{action}' benötigt MoireTracker"
                }
        
    except Exception as e:
        logger.error(f"use_app failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "app": app_name,
            "action": action
        }


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

QUICKACTION_TOOLS = [
    {
        "name": "open_app",
        "description": "Öffnet eine Anwendung schnell. Unterstützt Chrome, Word, Excel, VSCode, Notepad, Terminal und viele mehr. Bei Browsern kann eine URL mitgegeben werden.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name der App: chrome, word, excel, vscode, notepad, terminal, spotify, slack, discord, etc."
                },
                "url": {
                    "type": "string",
                    "description": "Optional: URL für Browser (z.B. 'google.com')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "use_app",
        "description": "Führt eine Aktion in einer laufenden App aus. Aktionen: navigate (Browser), type (Text eingeben), click (Element klicken), save (Speichern), close (Schließen).",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name der App"
                },
                "action": {
                    "type": "string",
                    "enum": ["navigate", "type", "click", "save", "close"],
                    "description": "Aktion: navigate, type, click, save, close"
                },
                "parameters": {
                    "type": "object",
                    "description": "Action-Parameter: url (für navigate), text (für type), element (für click), filename (für save)"
                }
            },
            "required": ["app_name", "action"]
        }
    }
]


# =============================================================================
# REGISTRATION
# =============================================================================

def register_quickaction_tools(tools_manager) -> None:
    """Registriert Quick Action Tools im ClientToolsManager."""
    print("Registering quick action tools...")
    
    def open_app_wrapper(params):
        return _run_async(open_app(
            params.get("app_name", ""),
            params.get("url")
        ))
    
    def use_app_wrapper(params):
        return _run_async(use_app(
            params.get("app_name", ""),
            params.get("action", ""),
            params.get("parameters")
        ))
    
    tools_manager.register_with_observer("open_app", open_app_wrapper)
    tools_manager.register_with_observer("use_app", use_app_wrapper)
    
    print("Quick action tools registered (2 tools)")


def _run_async(coro):
    """Helper um async functions synchron auszuführen."""
    import concurrent.futures
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "open_app",
    "use_app",
    "QUICKACTION_TOOLS",
    "register_quickaction_tools",
    "APP_SHORTCUTS"
]
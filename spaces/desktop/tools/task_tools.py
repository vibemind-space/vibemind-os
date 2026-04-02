"""
Task Management Tools für Desktop Automation To-Do Widget

Diese Tools ermöglichen das Erstellen und Verwalten von Desktop-Tasks
als Canvas-Nodes, die im To-Do Widget angezeigt werden.

Tools:
1. create_task_node - Erstellt einen Task als Canvas-Node
2. update_task_status - Aktualisiert den Task-Status
3. get_task_list - Holt alle Tasks für Widget-Anzeige
4. mark_task_complete - Markiert Task als erledigt
5. watch_task_progress - Überwacht Task bis Abschluss
"""

import asyncio
import logging
import uuid
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# Module-level state
_electron_sender: Optional[Callable[[dict], None]] = None
_task_store: Dict[str, 'DesktopTask'] = {}


class TaskStatus(str, Enum):
    """Status eines Desktop-Tasks."""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DesktopTask:
    """Ein Desktop-Automation Task."""
    id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    agent: str = "Adam"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result": self.result,
            "agent": self.agent
        }


def set_electron_sender(sender: Callable[[dict], None]):
    """Setzt die Funktion zum Senden von Nachrichten an Electron."""
    global _electron_sender
    _electron_sender = sender


def _notify_electron(message: dict):
    """Sendet Nachricht an Electron wenn verfügbar."""
    if _electron_sender:
        _electron_sender(message)


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def create_task_node(goal: str, agent: str = "Adam") -> Dict[str, Any]:
    """
    Erstellt einen neuen Desktop-Task als Canvas-Node.
    
    Dieser Task erscheint im To-Do Widget und kann überwacht werden.
    
    Args:
        goal: Beschreibung des Tasks (z.B. "Öffne Chrome und navigiere zu Google")
        agent: Name des ausführenden Agents (default: Adam)
    
    Returns:
        Dict mit task_id und Status
    """
    try:
        task_id = str(uuid.uuid4())[:8]
        task = DesktopTask(
            id=task_id,
            goal=goal,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            agent=agent
        )
        
        # In Store speichern
        _task_store[task_id] = task
        
        # Electron benachrichtigen
        _notify_electron({
            "type": "task_created",
            "task": task.to_dict()
        })
        
        logger.info(f"Task erstellt: {task_id} - {goal}")
        
        return {
            "success": True,
            "task_id": task_id,
            "message": f"Task '{goal}' erstellt und wartet auf Ausführung",
            "status": TaskStatus.PENDING.value
        }
        
    except Exception as e:
        logger.error(f"create_task_node failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def update_task_status(
    task_id: str, 
    status: str,
    progress: Optional[float] = None,
    error: Optional[str] = None,
    result: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Aktualisiert den Status eines Tasks.
    
    Args:
        task_id: ID des Tasks
        status: Neuer Status (pending, running, completed, failed, cancelled)
        progress: Optional - Fortschritt 0.0 bis 1.0
        error: Optional - Fehlermeldung bei status=failed
        result: Optional - Ergebnis bei status=completed
    
    Returns:
        Dict mit Bestätigung
    """
    try:
        if task_id not in _task_store:
            return {
                "success": False,
                "error": f"Task {task_id} nicht gefunden"
            }
        
        task = _task_store[task_id]
        
        # Status aktualisieren
        try:
            task.status = TaskStatus(status)
        except ValueError:
            return {
                "success": False,
                "error": f"Ungültiger Status: {status}"
            }
        
        # Timestamps setzen
        if status == TaskStatus.RUNNING.value and not task.started_at:
            task.started_at = time.time()
        elif status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
            task.completed_at = time.time()
        
        # Optionale Felder
        if progress is not None:
            task.progress = max(0.0, min(1.0, progress))
        if error:
            task.error = error
        if result:
            task.result = result
        
        # Electron benachrichtigen
        _notify_electron({
            "type": "task_updated",
            "task": task.to_dict()
        })
        
        logger.info(f"Task {task_id} Status: {status}")
        
        return {
            "success": True,
            "task_id": task_id,
            "status": task.status.value,
            "message": f"Task Status auf '{status}' gesetzt"
        }
        
    except Exception as e:
        logger.error(f"update_task_status failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def get_task_list(
    status_filter: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Holt alle Tasks für die Widget-Anzeige.
    
    Args:
        status_filter: Optional - Nur Tasks mit diesem Status
        limit: Maximale Anzahl (default: 20)
    
    Returns:
        Dict mit Liste aller Tasks
    """
    try:
        tasks = list(_task_store.values())
        
        # Filter anwenden
        if status_filter:
            try:
                filter_status = TaskStatus(status_filter)
                tasks = [t for t in tasks if t.status == filter_status]
            except ValueError:
                pass
        
        # Nach Erstellung sortieren (neueste zuerst)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        # Limit anwenden
        tasks = tasks[:limit]
        
        return {
            "success": True,
            "tasks": [t.to_dict() for t in tasks],
            "total": len(_task_store),
            "filtered": len(tasks)
        }
        
    except Exception as e:
        logger.error(f"get_task_list failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "tasks": []
        }


async def mark_task_complete(
    task_id: str,
    success: bool = True,
    result_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Markiert einen Task als erledigt (Checkbox im Widget).
    
    Args:
        task_id: ID des Tasks
        success: True für completed, False für failed
        result_message: Optional - Beschreibung des Ergebnisses
    
    Returns:
        Dict mit Bestätigung
    """
    try:
        status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        result = {"message": result_message} if result_message else None
        error = result_message if not success else None
        
        return await update_task_status(
            task_id=task_id,
            status=status.value,
            progress=1.0 if success else None,
            error=error,
            result=result
        )
        
    except Exception as e:
        logger.error(f"mark_task_complete failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def watch_task_progress(
    task_id: str,
    check_interval: float = 0.5,
    timeout: float = 120.0,
    progress_callback: Optional[Callable[[Dict], None]] = None
) -> Dict[str, Any]:
    """
    Überwacht einen Task bis zum Abschluss.
    
    Sendet regelmäßige Progress-Updates an Electron.
    
    Args:
        task_id: ID des Tasks
        check_interval: Prüfintervall in Sekunden
        timeout: Maximale Wartezeit
        progress_callback: Optional - Wird bei jedem Update aufgerufen
    
    Returns:
        Dict mit finalem Status
    """
    try:
        if task_id not in _task_store:
            return {
                "success": False,
                "error": f"Task {task_id} nicht gefunden"
            }
        
        start_time = time.time()
        
        while True:
            # Timeout check
            if time.time() - start_time > timeout:
                await update_task_status(task_id, TaskStatus.FAILED.value, 
                                        error="Timeout")
                return {
                    "success": False,
                    "error": "Timeout beim Warten auf Task",
                    "task_id": task_id
                }
            
            task = _task_store[task_id]
            
            # Progress Update senden
            _notify_electron({
                "type": "task_progress",
                "task_id": task_id,
                "progress": task.progress,
                "status": task.status.value
            })
            
            if progress_callback:
                progress_callback(task.to_dict())
            
            # Fertig?
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, 
                              TaskStatus.CANCELLED]:
                return {
                    "success": task.status == TaskStatus.COMPLETED,
                    "task_id": task_id,
                    "status": task.status.value,
                    "duration": time.time() - start_time,
                    "result": task.result,
                    "error": task.error
                }
            
            await asyncio.sleep(check_interval)
            
    except Exception as e:
        logger.error(f"watch_task_progress failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

TASK_TOOLS = [
    {
        "name": "create_task_node",
        "description": "Erstellt einen neuen Desktop-Task der im To-Do Widget erscheint. Benutze dies um Tasks zu tracken die du ausführst.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Beschreibung des Tasks (z.B. 'Öffne Chrome und navigiere zu Google')"
                },
                "agent": {
                    "type": "string",
                    "description": "Name des ausführenden Agents",
                    "default": "Adam"
                }
            },
            "required": ["goal"]
        }
    },
    {
        "name": "update_task_status",
        "description": "Aktualisiert den Status eines Tasks. Status kann sein: pending, running, completed, failed, cancelled",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID des Tasks"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "completed", "failed", "cancelled"],
                    "description": "Neuer Status"
                },
                "progress": {
                    "type": "number",
                    "description": "Fortschritt 0.0 bis 1.0"
                },
                "error": {
                    "type": "string",
                    "description": "Fehlermeldung wenn failed"
                }
            },
            "required": ["task_id", "status"]
        }
    },
    {
        "name": "get_task_list",
        "description": "Holt alle Tasks für die Widget-Anzeige. Optional nach Status filtern.",
        "parameters": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["pending", "running", "completed", "failed", "cancelled"],
                    "description": "Nur Tasks mit diesem Status anzeigen"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximale Anzahl",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "mark_task_complete",
        "description": "Markiert einen Task als erledigt. Wie eine Checkbox im To-Do Widget.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID des Tasks"
                },
                "success": {
                    "type": "boolean",
                    "description": "True für erfolgreich, False für fehlgeschlagen",
                    "default": True
                },
                "result_message": {
                    "type": "string",
                    "description": "Beschreibung des Ergebnisses"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "watch_task_progress", 
        "description": "Überwacht einen Task bis zum Abschluss und sendet Progress-Updates.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID des Tasks"
                },
                "timeout": {
                    "type": "number",
                    "description": "Maximale Wartezeit in Sekunden",
                    "default": 120
                }
            },
            "required": ["task_id"]
        }
    }
]


# =============================================================================
# REGISTRATION for voice_dialog_main
# =============================================================================

def register_task_tools(tools_manager) -> None:
    """
    Registriert Task Tools im ClientToolsManager.
    """
    logger.debug("register_task_tools called")
    print("Registering task tools...")
    
    def create_task_wrapper(params):
        goal = params.get("goal", "")
        agent = params.get("agent", "Adam")
        return _run_async(create_task_node(goal, agent))
    
    def update_status_wrapper(params):
        return _run_async(update_task_status(
            params.get("task_id", ""),
            params.get("status", ""),
            params.get("progress"),
            params.get("error"),
            params.get("result")
        ))
    
    def get_list_wrapper(params):
        return _run_async(get_task_list(
            params.get("status_filter"),
            params.get("limit", 20)
        ))
    
    def mark_complete_wrapper(params):
        return _run_async(mark_task_complete(
            params.get("task_id", ""),
            params.get("success", True),
            params.get("result_message")
        ))
    
    def watch_progress_wrapper(params):
        return _run_async(watch_task_progress(
            params.get("task_id", ""),
            timeout=params.get("timeout", 120.0)
        ))
    
    tools_manager.register_with_observer("create_task_node", create_task_wrapper)
    tools_manager.register_with_observer("update_task_status", update_status_wrapper)
    tools_manager.register_with_observer("get_task_list", get_list_wrapper)
    tools_manager.register_with_observer("mark_task_complete", mark_complete_wrapper)
    tools_manager.register_with_observer("watch_task_progress", watch_progress_wrapper)
    
    print(f"Task tools registered (5 tools)")


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
    "create_task_node",
    "update_task_status", 
    "get_task_list",
    "mark_task_complete",
    "watch_task_progress",
    "TASK_TOOLS",
    "register_task_tools",
    "set_electron_sender",
    "TaskStatus",
    "DesktopTask"
]
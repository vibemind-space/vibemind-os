"""
Client Manager Router für TRAE Backend

Stellt API-Endpoints zur Steuerung des Desktop Capture Clients bereit:
- POST /start - Startet den Client
- POST /stop - Stoppt den Client
- GET /status - Gibt aktuellen Status zurück
- POST /heartbeat - Empfängt Heartbeat vom Client

Author: TRAE Development Team
Version: 1.0.0
"""

from typing import Dict, Any, Optional, Union
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from ..services.client_manager_service import get_client_manager, ClientStatus
from ..logger_config import get_logger

logger = get_logger("client_manager_router")

router = APIRouter()


# ============================================================================Get Text:  Vimeo Post Text Setzt einen Vimeo Tag unter YouTube Vorspann (single)

class StartClientRequest(BaseModel):
    """Request-Model für Client-Start"""
    auto_restart: bool = Field(default=True, description="Automatischer Neustart bei Problemen")
    server_url: Optional[str] = Field(default=None, description="Optionale Server-URL Überschreibung")


class StopClientRequest(BaseModel):
    """Request-Model für Client-Stop"""
    force: bool = Field(default=False, description="Erzwingt sofortiges Beenden")


class HeartbeatRequest(BaseModel):
    """Request-Model für Heartbeats vom Client"""
    client_id: str = Field(..., description="Client-Identifier")
    timestamp: Optional[Union[str, float, int]] = Field(default=None, description="Timestamp (ISO-String oder Unix-Zeit)")
    frames_sent: Optional[int] = Field(default=None, description="Anzahl gesendeter Frames")
    monitors: Optional[int] = Field(default=None, description="Anzahl aktiver Monitore")
    fps: Optional[float] = Field(default=None, description="Aktuelle FPS")
    status: Optional[str] = Field(default=None, description="Client-Status")
    error: Optional[str] = Field(default=None, description="Letzte Fehlermeldung")
    
    @field_validator('timestamp', mode='before')
    @classmethod
    def convert_timestamp(cls, v):
        """Konvertiert timestamp zu ISO-String wenn nötig"""
        if v is None:
            return datetime.now().isoformat()
        if isinstance(v, (int, float)):
            # Unix-Timestamp zu ISO-String konvertieren
            return datetime.fromtimestamp(v).isoformat()
        return v


class ClientStatusResponse(BaseModel):
    """Response-Model für Client-Status"""
    success: bool
    status: str
    is_running: bool
    pid: Optional[int] = None
    start_time: Optional[str] = None
    uptime_seconds: float = 0
    last_heartbeat: Optional[str] = None
    last_heartbeat_ago_seconds: Optional[float] = None
    restart_count: int = 0
    script_path: str
    script_exists: bool
    watchdog_active: bool
    stats: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================Get Text:  Vimeo Post Text Setzt einen Vimeo Tag unter YouTube Vorspann (single)

# API ENDPOINTS
# ============================================================================

@router.post("/start")
async def start_client(request: StartClientRequest = StartClientRequest()):
    """
    Startet den Desktop Capture Client.
    
    Der Client wird als Subprocess gestartet und durch einen Watchdog überwacht.
    Bei Problemen erfolgt automatischer Neustart (wenn aktiviert).
    
    Returns:
        Status-Dictionary mit Ergebnis der Start-Operation
    """
    logger.info(f"[API] Start-Request empfangen: auto_restart={request.auto_restart}")
    
    try:
        client_manager = get_client_manager()
        result = await client_manager.start_client(
            auto_restart=request.auto_restart,
            server_url=request.server_url
        )
        
        if result["success"]:
            logger.info(f"[API] Client erfolgreich gestartet. PID: {result.get('pid')}")
            return JSONResponse(
                content=result,
                status_code=200
            )
        else:
            logger.warning(f"[API] Client-Start fehlgeschlagen: {result.get('error')}")
            return JSONResponse(
                content=result,
                status_code=400
            )
            
    except Exception as e:
        logger.error(f"[API] Fehler beim Starten: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_client(request: StopClientRequest = StopClientRequest()):
    """
    Stoppt den Desktop Capture Client.
    
    Sendet zunächst SIGTERM für graceful shutdown.
    Bei force=True wird sofort SIGKILL gesendet.
    
    Returns:
        Status-Dictionary mit Ergebnis der Stop-Operation
    """
    logger.info(f"[API] Stop-Request empfangen: force={request.force}")
    
    try:
        client_manager = get_client_manager()
        result = await client_manager.stop_client(force=request.force)
        
        if result["success"]:
            logger.info("[API] Client erfolgreich gestoppt")
            return JSONResponse(
                content=result,
                status_code=200
            )
        else:
            logger.warning(f"[API] Client-Stop fehlgeschlagen: {result.get('error')}")
            return JSONResponse(
                content=result,
                status_code=400
            )
            
    except Exception as e:
        logger.error(f"[API] Fehler beim Stoppen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_client_status():
    """
    Gibt den aktuellen Status des Desktop Capture Clients zurück.
    
    Enthält:
    - Laufzeit-Status (running/stopped/error)
    - PID des Prozesses
    - Uptime
    - Letzter Heartbeat
    - Statistiken
    
    Returns:
        Detaillierte Status-Informationen
    """
    try:
        client_manager = get_client_manager()
        status_info = client_manager.get_status_info()
        
        return JSONResponse(
            content={
                "success": True,
                **status_info
            },
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"[API] Fehler beim Status-Abruf: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat")
async def receive_heartbeat(request: HeartbeatRequest):
    """
    Empfängt einen Heartbeat vom Desktop Capture Client.
    
    Der Client sollte alle 5 Sekunden einen Heartbeat senden.
    Bei Ausbleiben für 30 Sekunden wird der Client automatisch neu gestartet.
    
    Returns:
        Acknowledgment mit Server-Timestamp
    """
    logger.debug(f"[API] Heartbeat von {request.client_id}")
    
    try:
        client_manager = get_client_manager()
        
        # Client-Info für Heartbeat zusammenstellen
        client_info = {
            "client_id": request.client_id,
            "timestamp": request.timestamp,
            "frames_sent": request.frames_sent,
            "monitors": request.monitors,
            "fps": request.fps,
            "status": request.status,
            "error": request.error
        }
        
        result = client_manager.receive_heartbeat(client_info)
        
        return JSONResponse(
            content=result,
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"[API] Fehler beim Heartbeat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart")
async def restart_client():
    """
    Startet den Desktop Capture Client neu.
    
    Stoppt zunächst den laufenden Client und startet ihn dann neu.
    
    Returns:
        Status-Dictionary mit Ergebnis der Restart-Operation
    """
    logger.info("[API] Restart-Request empfangen")
    
    try:
        client_manager = get_client_manager()
        
        # Erst stoppen
        stop_result = await client_manager.stop_client(force=False)
        if not stop_result["success"] and stop_result.get("status") != ClientStatus.STOPPED.value:
            logger.warning(f"[API] Stop vor Restart fehlgeschlagen: {stop_result.get('error')}")
        
        # Kurz warten
        import asyncio
        await asyncio.sleep(1)
        
        # Dann starten
        start_result = await client_manager.start_client(auto_restart=True)
        
        if start_result["success"]:
            logger.info(f"[API] Client erfolgreich neugestartet. PID: {start_result.get('pid')}")
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Client erfolgreich neugestartet",
                    **start_result
                },
                status_code=200
            )
        else:
            logger.warning(f"[API] Client-Restart fehlgeschlagen: {start_result.get('error')}")
            return JSONResponse(
                content=start_result,
                status_code=400
            )
            
    except Exception as e:
        logger.error(f"[API] Fehler beim Restart: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
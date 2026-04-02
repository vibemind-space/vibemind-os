"""FastAPI Router for Voice Control API.

Endpoints:
- POST /api/voice/command: Process text command (via interactive_mcp.py)
- POST /api/voice/command-legacy: Process text command (legacy executor)
- POST /api/voice/audio: Process audio file
- POST /api/voice/start: Start real-time listening
- POST /api/voice/stop: Stop real-time listening
- GET /api/voice/status: Get current status
- GET /api/voice/microphones: List available microphones

Integration:
- Voice commands are proxied to interactive_mcp.py for:
  - Pattern matching (fast, learned patterns)
  - LLM Task Planning (complex tasks)
  - Vision Validation (before/after comparison)
  - Learning System (pattern store)
"""

import os
import sys
import asyncio
import logging
import base64
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from uuid import uuid4

# FastAPI imports
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add moire_tracker to path for interactive_mcp
MOIRE_TRACKER_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "moire_tracker", "python"
))
if MOIRE_TRACKER_PATH not in sys.path:
    sys.path.insert(0, MOIRE_TRACKER_PATH)

# Handle both module and standalone imports
try:
    from .speech_to_text import SpeechToText, STTBackend, RealtimeSpeechToText
    from .intent_parser import IntentParser, QuickIntentParser, ParsedIntent, ActionType
    from .command_executor import CommandExecutor, VoiceAutomationPipeline, ExecutionReport
    from .text_to_speech import TextToSpeech, TTSConfig, TTSBackend, VoiceFeedback
except ImportError:
    from speech_to_text import SpeechToText, STTBackend, RealtimeSpeechToText
    from intent_parser import IntentParser, QuickIntentParser, ParsedIntent, ActionType
    from command_executor import CommandExecutor, VoiceAutomationPipeline, ExecutionReport
    from text_to_speech import TextToSpeech, TTSConfig, TTSBackend, VoiceFeedback

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/voice", tags=["Voice Control"])


# === Pydantic Models ===

class TextCommandRequest(BaseModel):
    """Request for text command processing."""
    text: str = Field(..., description="Text command to process")
    use_quick_parser: bool = Field(True, description="Use quick pattern matching first")
    execute: bool = Field(True, description="Execute the parsed actions")
    voice_feedback: bool = Field(False, description="Enable voice feedback")


class TextCommandResponse(BaseModel):
    """Response from text command processing."""
    success: bool
    original_text: str
    parsed_context: Optional[str] = None
    actions: List[Dict[str, Any]] = []
    execution_results: List[Dict[str, Any]] = []
    feedback_message: Optional[str] = None
    duration_ms: float = 0


class MCPCommandResponse(BaseModel):
    """Response from MCP-based command processing."""
    success: bool
    task_id: str
    original_text: str
    route: str = ""  # LEARNED_PATTERN, DIRECT, LLM_PLANNER, CLAUDE_CLI
    execution_success: bool = False
    validation: Optional[Dict[str, Any]] = None
    learned: bool = False
    pattern_confidence: Optional[float] = None
    feedback_message: str = ""
    duration_ms: float = 0
    error: Optional[str] = None


class AudioCommandRequest(BaseModel):
    """Request for audio command processing."""
    audio_base64: str = Field(..., description="Base64-encoded audio data")
    format: str = Field("wav", description="Audio format (wav, mp3)")
    sample_rate: int = Field(16000, description="Audio sample rate")
    execute: bool = Field(True, description="Execute the parsed actions")
    voice_feedback: bool = Field(False, description="Enable voice feedback")


class ListeningStatus(BaseModel):
    """Real-time listening status."""
    is_listening: bool
    wake_word: Optional[str] = None
    started_at: Optional[str] = None
    commands_processed: int = 0


class StartListeningRequest(BaseModel):
    """Request to start real-time listening."""
    wake_word: Optional[str] = Field(None, description="Wake word (e.g., 'Hey Moire')")
    voice_feedback: bool = Field(True, description="Enable voice feedback")


class MicrophoneInfo(BaseModel):
    """Microphone information."""
    index: int
    name: str
    channels: int
    sample_rate: float


# === Global State ===

class VoiceServiceState:
    """Global state for voice service."""

    def __init__(self):
        self.stt: Optional[SpeechToText] = None
        self.intent_parser: Optional[QuickIntentParser] = None
        self.executor: Optional[CommandExecutor] = None
        self.tts: Optional[TextToSpeech] = None
        self.realtime_stt: Optional[RealtimeSpeechToText] = None
        self.pipeline: Optional[VoiceAutomationPipeline] = None

        self.is_listening = False
        self.listening_started_at: Optional[datetime] = None
        self.commands_processed = 0
        self.wake_word: Optional[str] = None

        # Command history
        self.history: List[Dict[str, Any]] = []

    def initialize(self):
        """Initialize all components."""
        if self.stt is None:
            self.stt = SpeechToText(backend=STTBackend.OPENAI_WHISPER, language="de")
            self.intent_parser = QuickIntentParser(fallback_parser=IntentParser())
            self.executor = CommandExecutor()
            self.tts = TextToSpeech(TTSConfig(backend=TTSBackend.PYTTSX3))
            self.pipeline = VoiceAutomationPipeline()
            logger.info("Voice service initialized")

    def add_to_history(self, text: str, result: ExecutionReport):
        """Add command to history."""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "success": result.success,
            "context": result.intent.context,
            "feedback": result.feedback_message
        })
        # Keep only last 100 commands
        if len(self.history) > 100:
            self.history = self.history[-100:]


# Global state instance
_state = VoiceServiceState()


def get_state() -> VoiceServiceState:
    """Get or initialize global state."""
    if _state.stt is None:
        _state.initialize()
    return _state


# === Redis PubSub Integration ===

_redis_pubsub = None

async def get_redis_pubsub():
    """Get Redis PubSub instance for task events."""
    global _redis_pubsub
    if _redis_pubsub is None:
        try:
            # Add backend path for redis_pubsub import
            backend_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", ".."
            ))
            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)

            from app.services.redis_pubsub import redis_pubsub
            if not redis_pubsub.is_connected:
                redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
                await redis_pubsub.connect(redis_url)
            _redis_pubsub = redis_pubsub
            logger.info("Redis PubSub connected for task events")
        except Exception as e:
            logger.warning(f"Redis PubSub not available: {e}")
            _redis_pubsub = None
    return _redis_pubsub


# === MCPAutomation Handler ===

class MCPAutomationHandler:
    """Handler for MCPAutomation integration.

    Provides Voice → interactive_mcp.py proxy with:
    - Pattern matching (fast, learned patterns)
    - LLM Task Planning (complex tasks)
    - Vision Validation (before/after comparison)
    - Learning System (pattern store)
    - Redis event publishing for UI updates
    """

    _instance = None
    _mcp = None

    @classmethod
    def get_mcp(cls):
        """Get or create MCPAutomation instance (singleton)."""
        if cls._mcp is None:
            try:
                from interactive_mcp import MCPAutomation
                cls._mcp = MCPAutomation()
                logger.info("MCPAutomation instance created")
            except ImportError as e:
                logger.error(f"Failed to import MCPAutomation: {e}")
                logger.error(f"MOIRE_TRACKER_PATH: {MOIRE_TRACKER_PATH}")
                raise
        return cls._mcp

    @classmethod
    async def execute_task(cls, task: str, task_id: str, source: str = "voice") -> Dict[str, Any]:
        """Execute task via MCPAutomation with Redis event publishing.

        Args:
            task: Natural language task
            task_id: Unique task identifier
            source: Source of the task (voice, text, api)

        Returns:
            Dict with execution results, validation, and learning info
        """
        import time
        start_time = time.time()

        mcp = cls.get_mcp()
        redis = await get_redis_pubsub()

        result = {
            "task_id": task_id,
            "success": False,
            "route": "UNKNOWN",
            "execution_success": False,
            "validation": None,
            "learned": False,
            "pattern_confidence": None,
            "error": None
        }

        try:
            # Publish task:created event
            if redis:
                await redis.publish_task_created(task_id, task, source)

            # Capture routing info from logs
            original_log = []
            original_log_method = mcp.log

            def capture_log(msg):
                original_log.append(msg)
                original_log_method(msg)

            mcp.log = capture_log

            # Execute via MCP - now returns result dict
            mcp_result = await mcp.run_task(task)

            # Restore log method
            mcp.log = original_log_method

            # Parse routing from logs
            for log_line in original_log:
                if "[ROUTE]" in log_line:
                    if "LEARNED PATTERN" in log_line:
                        result["route"] = "LEARNED_PATTERN"
                        if "conf=" in log_line:
                            try:
                                conf_str = log_line.split("conf=")[1].split(")")[0].replace("%", "")
                                result["pattern_confidence"] = float(conf_str) / 100
                            except:
                                pass
                    elif "DIRECT" in log_line:
                        result["route"] = "DIRECT"
                    elif "LLM PLANNER" in log_line:
                        result["route"] = "LLM_PLANNER"
                    elif "CLAUDE CLI" in log_line:
                        result["route"] = "CLAUDE_CLI"

            # Publish task:started event once route is determined
            if redis and result["route"] != "UNKNOWN":
                await redis.publish_task_started(task_id, result["route"])

            # Use returned result from run_task
            if mcp_result:
                result["success"] = mcp_result.get("success", False)
                result["execution_success"] = mcp_result.get("execution_success", False)
                result["validation"] = mcp_result.get("validation")

                # Publish validation event if available
                if redis and result["validation"]:
                    await redis.publish_task_validation(
                        task_id=task_id,
                        success=result["validation"].get("success", False),
                        confidence=result["validation"].get("confidence", 0),
                        method=result["validation"].get("method", "unknown"),
                        reason=result["validation"].get("reason", ""),
                        observed_changes=result["validation"].get("observed_changes")
                    )
            else:
                # Fallback: parse from logs if no result returned
                result["execution_success"] = not any("Error" in log or "failed" in log.lower()
                                                       for log in original_log)
                result["success"] = result["execution_success"]

            # Check memory collector for learning
            if mcp.memory_collector and mcp.memory_collector.episodes:
                last_episode = mcp.memory_collector.episodes[-1]
                result["learned"] = last_episode.get("success", False)

                # Publish task:learned event if pattern was learned
                if result["learned"] and redis:
                    await redis.publish_task_learned(
                        task_id=task_id,
                        pattern_id=f"pattern_{task_id[:8]}",
                        task_text=task,
                        confidence=result["pattern_confidence"] or 0.8,
                        actions=[]  # Would need to capture from MCP
                    )

            result["duration_ms"] = (time.time() - start_time) * 1000

            # Publish task:completed event
            if redis:
                await redis.publish_task_completed(
                    task_id=task_id,
                    success=result["success"],
                    route=result["route"],
                    duration_ms=result["duration_ms"],
                    validation=result["validation"],
                    learned=result["learned"]
                )

        except Exception as e:
            logger.error(f"MCP execution failed: {e}")
            result["error"] = str(e)
            result["success"] = False
            result["duration_ms"] = (time.time() - start_time) * 1000

            # Publish task:failed event
            if redis:
                await redis.publish_task_failed(
                    task_id=task_id,
                    error=str(e),
                    route=result["route"],
                    duration_ms=result["duration_ms"]
                )

        return result


# === API Endpoints ===

@router.post("/command", response_model=MCPCommandResponse)
async def process_text_command_mcp(request: TextCommandRequest) -> MCPCommandResponse:
    """Process a text command via MCPAutomation.

    This endpoint proxies commands to interactive_mcp.py which provides:
    - Pattern matching (fast, learned patterns)
    - LLM Task Planning (complex tasks)
    - Vision Validation (before/after comparison)
    - Learning System (pattern store)

    Example:
        POST /api/voice/command
        {"text": "Öffne WhatsApp", "execute": true}

    Response includes:
        - route: How the command was processed (LEARNED_PATTERN, DIRECT, LLM_PLANNER, CLAUDE_CLI)
        - validation: Vision validation results (if enabled)
        - learned: Whether a new pattern was learned
    """
    import time
    start_time = time.time()

    task_id = str(uuid4())

    try:
        # Execute via MCPAutomation
        if request.execute:
            result = await MCPAutomationHandler.execute_task(request.text, task_id)

            response = MCPCommandResponse(
                success=result["success"],
                task_id=task_id,
                original_text=request.text,
                route=result["route"],
                execution_success=result["execution_success"],
                validation=result.get("validation"),
                learned=result.get("learned", False),
                pattern_confidence=result.get("pattern_confidence"),
                feedback_message=f"Ausgeführt via {result['route']}" if result["success"] else f"Fehler: {result.get('error', 'Unbekannt')}",
                duration_ms=result["duration_ms"],
                error=result.get("error")
            )
        else:
            # Just parse, don't execute
            response = MCPCommandResponse(
                success=True,
                task_id=task_id,
                original_text=request.text,
                route="NOT_EXECUTED",
                execution_success=False,
                feedback_message="Befehl nicht ausgeführt (execute=false)",
                duration_ms=(time.time() - start_time) * 1000
            )

        # Voice feedback
        if request.voice_feedback:
            state = get_state()
            if state.tts:
                await state.tts.speak_async(response.feedback_message)

        return response

    except Exception as e:
        logger.error(f"MCP command processing failed: {e}")
        return MCPCommandResponse(
            success=False,
            task_id=task_id,
            original_text=request.text,
            route="ERROR",
            execution_success=False,
            feedback_message=f"Fehler: {str(e)}",
            duration_ms=(time.time() - start_time) * 1000,
            error=str(e)
        )


@router.post("/command-legacy", response_model=TextCommandResponse)
async def process_text_command_legacy(request: TextCommandRequest) -> TextCommandResponse:
    """Process a text command (legacy executor).

    Uses the original QuickIntentParser and CommandExecutor.
    Kept for backwards compatibility.

    Example:
        POST /api/voice/command-legacy
        {"text": "Öffne Anthropic Careers", "execute": true}
    """
    import time
    start_time = time.time()

    state = get_state()

    try:
        # Parse intent
        if request.use_quick_parser:
            intent = await state.intent_parser.parse(request.text)
        else:
            intent = await state.intent_parser.fallback_parser.parse(request.text)

        # Prepare response
        response = TextCommandResponse(
            success=not bool(intent.error),
            original_text=request.text,
            parsed_context=intent.context,
            actions=[
                {
                    "type": action.type.value,
                    "params": action.params,
                    "description": action.description
                }
                for action in intent.actions
            ]
        )

        # Execute if requested
        if request.execute and not intent.error and intent.actions:
            report = await state.executor.execute(intent)
            response.success = report.success
            response.feedback_message = report.feedback_message
            response.execution_results = [
                {
                    "action": r.action.description,
                    "success": r.success,
                    "error": r.error,
                    "duration_ms": r.duration_ms
                }
                for r in report.results
            ]

            # Voice feedback
            if request.voice_feedback and state.tts:
                await state.tts.speak_async(report.feedback_message)

            # Add to history
            state.add_to_history(request.text, report)
            state.commands_processed += 1

        response.duration_ms = (time.time() - start_time) * 1000
        return response

    except Exception as e:
        logger.error(f"Command processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audio")
async def process_audio_command(
    file: UploadFile = File(...),
    execute: bool = True,
    voice_feedback: bool = False
) -> MCPCommandResponse:
    """Process an audio file command via MCPAutomation.

    Upload an audio file (WAV or MP3) to be transcribed and executed.

    Example:
        POST /api/voice/audio
        Content-Type: multipart/form-data
        file: [audio file]
    """
    import time
    start_time = time.time()

    state = get_state()

    try:
        # Read audio file
        audio_data = await file.read()

        # Transcribe
        transcription = await state.stt.transcribe_audio(audio_data)

        if not transcription.text:
            raise HTTPException(status_code=400, detail="No speech detected in audio")

        # Process as text command via MCP
        request = TextCommandRequest(
            text=transcription.text,
            execute=execute,
            voice_feedback=voice_feedback
        )

        response = await process_text_command_mcp(request)
        response.duration_ms = (time.time() - start_time) * 1000
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audio-base64")
async def process_audio_base64(request: AudioCommandRequest) -> MCPCommandResponse:
    """Process base64-encoded audio command via MCPAutomation.

    Alternative to file upload for audio processing.
    """
    import time
    start_time = time.time()

    state = get_state()

    try:
        # Decode audio
        audio_data = base64.b64decode(request.audio_base64)

        # Transcribe
        transcription = await state.stt.transcribe_audio(
            audio_data,
            sample_rate=request.sample_rate
        )

        if not transcription.text:
            raise HTTPException(status_code=400, detail="No speech detected in audio")

        # Process as text command via MCP
        text_request = TextCommandRequest(
            text=transcription.text,
            execute=request.execute,
            voice_feedback=request.voice_feedback
        )

        response = await process_text_command_mcp(text_request)
        response.duration_ms = (time.time() - start_time) * 1000
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audio processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_listening(
    request: StartListeningRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Start real-time voice listening.

    Starts continuous listening with optional wake word detection.
    """
    state = get_state()

    if state.is_listening:
        raise HTTPException(status_code=400, detail="Already listening")

    try:
        # Create realtime STT if not exists
        if state.realtime_stt is None:
            state.realtime_stt = RealtimeSpeechToText(
                stt=state.stt,
                on_transcription=lambda text: asyncio.create_task(
                    _handle_realtime_transcription(text, request.voice_feedback)
                )
            )

        # Start listening in background
        state.is_listening = True
        state.listening_started_at = datetime.now()
        state.wake_word = request.wake_word

        background_tasks.add_task(
            state.realtime_stt.start_listening,
            wake_word=request.wake_word
        )

        # Voice feedback
        if request.voice_feedback and state.tts:
            await state.tts.speak_async("Ich höre zu.")

        return {
            "success": True,
            "message": "Listening started",
            "wake_word": request.wake_word
        }

    except Exception as e:
        state.is_listening = False
        logger.error(f"Failed to start listening: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_realtime_transcription(text: str, voice_feedback: bool):
    """Handle transcription from real-time STT via MCPAutomation."""
    state = get_state()
    logger.info(f"Real-time transcription: {text}")

    # Process command via MCPAutomation
    task_id = str(uuid4())
    try:
        result = await MCPAutomationHandler.execute_task(text, task_id)
        state.commands_processed += 1

        feedback = f"Ausgeführt via {result['route']}" if result["success"] else f"Fehler: {result.get('error', 'Unbekannt')}"

        if voice_feedback and state.tts:
            await state.tts.speak_async(feedback)

        logger.info(f"Real-time command result: success={result['success']}, route={result['route']}")

    except Exception as e:
        logger.error(f"Real-time command failed: {e}")
        if voice_feedback and state.tts:
            await state.tts.speak_async(f"Fehler: {str(e)}")


@router.post("/stop")
async def stop_listening() -> Dict[str, Any]:
    """Stop real-time voice listening."""
    state = get_state()

    if not state.is_listening:
        return {"success": True, "message": "Not listening"}

    try:
        if state.realtime_stt:
            await state.realtime_stt.stop_listening()

        state.is_listening = False
        state.listening_started_at = None
        state.wake_word = None

        return {
            "success": True,
            "message": "Listening stopped",
            "commands_processed": state.commands_processed
        }

    except Exception as e:
        logger.error(f"Failed to stop listening: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ListeningStatus)
async def get_status() -> ListeningStatus:
    """Get current listening status."""
    state = get_state()

    return ListeningStatus(
        is_listening=state.is_listening,
        wake_word=state.wake_word,
        started_at=state.listening_started_at.isoformat() if state.listening_started_at else None,
        commands_processed=state.commands_processed
    )


@router.get("/microphones", response_model=List[MicrophoneInfo])
async def list_microphones() -> List[MicrophoneInfo]:
    """List available microphone devices."""
    mics = RealtimeSpeechToText.list_microphones()
    return [
        MicrophoneInfo(
            index=m['index'],
            name=m['name'],
            channels=m['channels'],
            sample_rate=m['sample_rate']
        )
        for m in mics
    ]


@router.get("/history")
async def get_history(limit: int = 20) -> List[Dict[str, Any]]:
    """Get command history."""
    state = get_state()
    return state.history[-limit:]


@router.post("/speak")
async def speak_text(text: str, voice_feedback: bool = True) -> Dict[str, Any]:
    """Speak text using TTS.

    Example:
        POST /api/voice/speak?text=Hello%20World
    """
    state = get_state()

    if not state.tts:
        raise HTTPException(status_code=500, detail="TTS not available")

    try:
        await state.tts.speak_async(text)
        return {"success": True, "text": text}
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Health Check ===

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check voice service health."""
    state = get_state()

    return {
        "status": "healthy",
        "stt_backend": state.stt.backend.value if state.stt else None,
        "tts_backend": state.tts.config.backend.value if state.tts else None,
        "is_listening": state.is_listening,
        "commands_processed": state.commands_processed
    }


# === Integration Helper ===

def include_voice_router(app):
    """Include voice router in FastAPI app.

    Usage:
        from voice.api_router import include_voice_router
        include_voice_router(app)
    """
    app.include_router(router)
    logger.info("Voice control API router included")

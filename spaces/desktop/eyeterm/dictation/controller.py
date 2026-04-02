"""DictationController — orchestrates voice-to-text with AI enhancement.

Flow:
    1. Head-nod triggers DICTATION_START
    2. STT partials accumulate into raw_transcript
    3. 2s silence → DICTATION_STOP → LLM enhancement
    4. Enhanced text shown in PREVIEWING state
    5. Wink gestures: left=toggle, right=insert, both=accept
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("eyeterm.dictation")

_DICTATION_PROMPT = """Fix grammar, add punctuation, improve clarity.
Preserve the original meaning exactly. Keep the original language.
Do NOT add content, remove content, or change the intent.

Raw transcript:
{transcript}

Polished text:"""


class DictationController:
    """Orchestrate the voice dictation → enhancement → insertion flow.

    Parameters
    ----------
    polisher : TranscriptPolisher
        LLM polisher for text enhancement.
    on_state_event : callable
        Called with (event_name, payload) to drive the state machine.
    on_insert_text : callable
        Called with (text) to insert at cursor position.
    silence_timeout_s : float
        Seconds of silence before auto-triggering enhancement (default 2.0).
    """

    def __init__(
        self,
        polisher,
        on_state_event: Callable[[str, Optional[str]], None],
        on_insert_text: Callable[[str], None],
        silence_timeout_s: float = 2.0,
    ) -> None:
        self._polisher = polisher
        self._on_state_event = on_state_event
        self._on_insert_text = on_insert_text
        self._silence_timeout = silence_timeout_s

        self._lock = threading.Lock()
        self._raw_parts: list[str] = []
        self._raw_transcript: str = ""
        self._enhanced_transcript: Optional[str] = None
        self._showing_raw: bool = False
        self._active: bool = False
        self._silence_timer: Optional[threading.Timer] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_dictation(self) -> None:
        """Enter dictation mode — begin accumulating STT output."""
        with self._lock:
            self._raw_parts = []
            self._raw_transcript = ""
            self._enhanced_transcript = None
            self._showing_raw = False
            self._active = True
        logger.info("Dictation started")

    def cancel(self) -> None:
        """Cancel dictation, discard everything."""
        self._cancel_silence_timer()
        with self._lock:
            self._active = False
            self._raw_parts = []
            self._raw_transcript = ""
            self._enhanced_transcript = None
        if self._polisher:
            self._polisher.cancel()
        logger.info("Dictation cancelled")

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def raw_transcript(self) -> str:
        with self._lock:
            return self._raw_transcript

    @property
    def enhanced_transcript(self) -> Optional[str]:
        with self._lock:
            return self._enhanced_transcript

    # ------------------------------------------------------------------
    # STT callbacks (called from STT thread)
    # ------------------------------------------------------------------

    def on_stt_partial(self, text: str) -> None:
        """Receive a partial STT result (live, may change)."""
        if not self._active:
            return
        # Reset silence timer on every partial
        self._restart_silence_timer()

    def on_stt_final(self, text: str) -> None:
        """Receive a final STT segment."""
        if not self._active:
            return
        with self._lock:
            self._raw_parts.append(text)
            self._raw_transcript = " ".join(self._raw_parts)
        self._restart_silence_timer()
        logger.debug("Dictation segment: '%s'", text)

    # ------------------------------------------------------------------
    # Silence detection
    # ------------------------------------------------------------------

    def _restart_silence_timer(self) -> None:
        """Reset the silence timer — fires enhancement after timeout."""
        self._cancel_silence_timer()
        self._silence_timer = threading.Timer(
            self._silence_timeout, self._on_silence_timeout
        )
        self._silence_timer.daemon = True
        self._silence_timer.start()

    def _cancel_silence_timer(self) -> None:
        if self._silence_timer is not None:
            self._silence_timer.cancel()
            self._silence_timer = None

    def _on_silence_timeout(self) -> None:
        """Called when user stops speaking for silence_timeout seconds."""
        with self._lock:
            if not self._active or not self._raw_transcript.strip():
                return
        logger.info("Silence detected — triggering enhancement")
        self._on_state_event("dictation_stop", None)

    # ------------------------------------------------------------------
    # Enhancement
    # ------------------------------------------------------------------

    def start_enhancement(self, gaze_context: Optional[dict] = None) -> None:
        """Start AI enhancement — routes to Agent Team with gaze context.

        Falls back to TranscriptPolisher if Automation UI is unreachable.

        Args:
            gaze_context: Dict from UIElementContext.to_orchestrator_context()
                          with gaze_app, gaze_element, gaze_value etc.
        """
        with self._lock:
            raw = self._raw_transcript
        if not raw.strip():
            self._on_state_event("enhance_complete", raw)
            return

        logger.info("Enhancing: '%s' (gaze: %s)", raw[:80],
                     gaze_context.get("gaze_app", "?") if gaze_context else "none")

        def _on_enhanced(polished: str) -> None:
            with self._lock:
                self._enhanced_transcript = polished
            logger.info("Enhanced: '%s'", polished[:80])
            self._on_state_event("enhance_complete", polished)

        # Try Agent Team first (context-aware), fall back to simple polisher
        import threading
        threading.Thread(
            target=self._enhance_via_agent_team,
            args=(raw, gaze_context, _on_enhanced),
            daemon=True,
            name="DictationEnhance",
        ).start()

    def _enhance_via_agent_team(
        self, raw: str, gaze_context: Optional[dict], on_complete
    ) -> None:
        """Background: try Agent Team, fall back to polisher."""
        try:
            from spaces.desktop.automation_ui_client import get_automation_client
            client = get_automation_client()

            if client.is_available():
                # Build context-aware prompt
                ctx_lines = []
                if gaze_context:
                    app = gaze_context.get("gaze_app", "")
                    elem = gaze_context.get("gaze_element", "")
                    val = gaze_context.get("gaze_value", "")[:200]
                    if app:
                        ctx_lines.append(f"App: {app}")
                    if elem:
                        ctx_lines.append(f"Element: {elem}")
                    if val:
                        ctx_lines.append(f"Current value: {val}")

                context_block = "\n".join(ctx_lines) if ctx_lines else "No specific UI context"

                prompt = (
                    f"The user dictated the following text while looking at:\n"
                    f"{context_block}\n\n"
                    f"Polish this dictated text for the context above. "
                    f"Fix grammar, add punctuation, improve clarity. "
                    f"Keep the original language. Do NOT add content or change intent. "
                    f"Return ONLY the polished text.\n\n"
                    f"Raw transcript:\n{raw}"
                )

                result = client.llm_intent(prompt, conversation_id="dictation")
                if result.get("success") and result.get("summary"):
                    on_complete(result["summary"])
                    return

            logger.info("Agent Team unavailable, falling back to polisher")
        except Exception as e:
            logger.warning("Agent Team enhancement failed: %s, using polisher", e)

        # Fallback: simple polisher
        if self._polisher:
            self._polisher.polish(
                transcript=raw,
                element_context=gaze_context or {"dictation_mode": True},
                on_complete=on_complete,
            )
        else:
            on_complete(raw)

    # ------------------------------------------------------------------
    # Wink actions
    # ------------------------------------------------------------------

    def toggle_view(self) -> str:
        """Toggle between raw and enhanced view. Returns 'raw' or 'enhanced'."""
        with self._lock:
            self._showing_raw = not self._showing_raw
            mode = "raw" if self._showing_raw else "enhanced"
        logger.info("Dictation view toggled to: %s", mode)
        return mode

    def get_displayed_text(self) -> str:
        """Return the currently displayed text (based on toggle state)."""
        with self._lock:
            if self._showing_raw or self._enhanced_transcript is None:
                return self._raw_transcript
            return self._enhanced_transcript

    def insert_at_cursor(self) -> None:
        """Insert the currently displayed text at cursor position."""
        text = self.get_displayed_text()
        if text.strip():
            logger.info("Inserting at cursor: '%s'", text[:80])
            self._on_insert_text(text)
        self._finish()

    def insert_raw(self) -> None:
        """Insert raw (unenhanced) transcript at cursor."""
        with self._lock:
            text = self._raw_transcript
        if text.strip():
            logger.info("Inserting raw: '%s'", text[:80])
            self._on_insert_text(text)
        self._finish()

    def accept_enhanced(self) -> None:
        """Accept and insert the enhanced version."""
        with self._lock:
            text = self._enhanced_transcript or self._raw_transcript
        if text.strip():
            logger.info("Accepting enhanced: '%s'", text[:80])
            self._on_insert_text(text)
        self._finish()

    def _finish(self) -> None:
        """Clean up after insertion."""
        self._cancel_silence_timer()
        with self._lock:
            self._active = False
            self._raw_parts = []
            self._raw_transcript = ""
            self._enhanced_transcript = None
            self._showing_raw = False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "raw_length": len(self._raw_transcript),
                "enhanced": self._enhanced_transcript is not None,
                "showing_raw": self._showing_raw,
            }

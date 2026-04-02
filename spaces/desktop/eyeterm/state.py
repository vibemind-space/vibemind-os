"""eyeTerm state machine — 6 states for look + speak + polish + preview + dictation UX.

States:
  IDLE       — no focus (gaze not dwelling)
  FOCUSED    — element highlighted, voice dictation active
  POLISHING  — AI is refining the transcript (left wink triggered)
  PREVIEWING — polished text shown, awaiting confirm/reject wink
  DICTATING  — capturing voice input (system-wide dictation mode)
  ENHANCING  — AI is enhancing dictated text
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = "idle"
    FOCUSED = "focused"
    POLISHING = "polishing"
    PREVIEWING = "previewing"
    DICTATING = "dictating"
    ENHANCING = "enhancing"


class Event(Enum):
    GAZE_DWELL = "gaze_dwell"
    GAZE_LOST = "gaze_lost"
    LEFT_WINK = "left_wink"
    RIGHT_WINK = "right_wink"
    BOTH_CLOSED = "both_closed"
    SPEECH_FINAL = "speech_final"
    POLISH_COMPLETE = "polish_complete"
    PREVIEW_TIMEOUT = "preview_timeout"
    DICTATION_START = "dictation_start"
    DICTATION_STOP = "dictation_stop"
    ENHANCE_COMPLETE = "enhance_complete"


# Transition table: (current_state, event) -> (new_state, action_or_none)
_TRANSITIONS = {
    # IDLE
    (State.IDLE, Event.GAZE_DWELL): (State.FOCUSED, "focus_pane"),

    # FOCUSED
    (State.FOCUSED, Event.GAZE_LOST): (State.IDLE, "unfocus"),
    (State.FOCUSED, Event.GAZE_DWELL): (State.FOCUSED, "update_focus"),
    (State.FOCUSED, Event.LEFT_WINK): (State.FOCUSED, "start_polish_or_escape"),
    (State.FOCUSED, Event.RIGHT_WINK): (State.FOCUSED, "send_escape"),
    (State.FOCUSED, Event.SPEECH_FINAL): (State.FOCUSED, "send_text"),

    # POLISHING (AI is working — limited interactions)
    (State.POLISHING, Event.POLISH_COMPLETE): (State.PREVIEWING, "show_preview"),
    (State.POLISHING, Event.LEFT_WINK): (State.FOCUSED, "cancel_polish"),
    (State.POLISHING, Event.GAZE_LOST): (State.IDLE, "cancel_polish_and_unfocus"),
    (State.POLISHING, Event.GAZE_DWELL): (State.POLISHING, None),  # ignore, stay

    # PREVIEWING (polished text shown — confirm or reject)
    (State.PREVIEWING, Event.RIGHT_WINK): (State.FOCUSED, "submit_polished"),
    (State.PREVIEWING, Event.LEFT_WINK): (State.FOCUSED, "reject_polished"),
    (State.PREVIEWING, Event.BOTH_CLOSED): (State.IDLE, "accept_enhanced"),
    (State.PREVIEWING, Event.PREVIEW_TIMEOUT): (State.FOCUSED, "dismiss_preview"),
    (State.PREVIEWING, Event.GAZE_LOST): (State.IDLE, "dismiss_preview_and_unfocus"),
    (State.PREVIEWING, Event.GAZE_DWELL): (State.PREVIEWING, None),  # ignore, stay

    # --- Dictation mode (system-wide voice-to-text with AI enhancement) ---

    # Enter dictation via head nod (from IDLE or FOCUSED)
    (State.IDLE, Event.DICTATION_START): (State.DICTATING, "start_dictation"),
    (State.FOCUSED, Event.DICTATION_START): (State.DICTATING, "start_dictation"),

    # DICTATING (capturing voice)
    (State.DICTATING, Event.DICTATION_STOP): (State.ENHANCING, "start_enhancement"),
    (State.DICTATING, Event.LEFT_WINK): (State.IDLE, "cancel_dictation"),
    (State.DICTATING, Event.RIGHT_WINK): (State.IDLE, "insert_raw"),

    # ENHANCING (LLM processing)
    (State.ENHANCING, Event.ENHANCE_COMPLETE): (State.PREVIEWING, "show_dictation_preview"),
    (State.ENHANCING, Event.LEFT_WINK): (State.IDLE, "cancel_enhancement"),

    # PREVIEWING reuses existing transitions + adds BOTH_CLOSED for dictation accept
    # (BOTH_CLOSED already added above)
}


@dataclass
class StateMachine:
    """Pure state machine for eyeTerm control flow."""

    state: State = State.IDLE
    focused_pane: Optional[int] = None
    pending_transcript: Optional[str] = None
    polished_text: Optional[str] = None
    # Dictation mode fields
    raw_transcript: Optional[str] = None
    enhanced_transcript: Optional[str] = None
    showing_raw: bool = False  # toggle between raw/enhanced in PREVIEWING
    history: list = field(default_factory=list)

    def transition(self, event: Event, payload: Any = None) -> Tuple[State, Optional[str]]:
        """Process event, return (new_state, action_name_or_none).

        The caller is responsible for executing the action.
        """
        logger.debug("transition called: state=%s event=%s", self.state, event)
        # Special handling: LEFT_WINK in FOCUSED depends on pending_transcript
        if self.state == State.FOCUSED and event == Event.LEFT_WINK:
            if self.pending_transcript:
                # Has transcript → start polishing
                old_state = self.state
                self.state = State.POLISHING
                action = "start_polish"
                self.history.append((old_state, event, self.state, action))
                return self.state, action
            else:
                # No transcript → fallback escape
                old_state = self.state
                action = "send_escape"
                self.history.append((old_state, event, self.state, action))
                return self.state, action

        key = (self.state, event)
        if key not in _TRANSITIONS:
            return self.state, None

        new_state, action = _TRANSITIONS[key]
        old_state = self.state
        self.state = new_state

        # Store payload based on event
        if event == Event.GAZE_DWELL and isinstance(payload, int):
            self.focused_pane = payload

        if event == Event.SPEECH_FINAL and isinstance(payload, str):
            self.pending_transcript = payload

        if event == Event.POLISH_COMPLETE and isinstance(payload, str):
            self.polished_text = payload

        if event == Event.ENHANCE_COMPLETE and isinstance(payload, str):
            self.enhanced_transcript = payload

        # Clear focus on IDLE
        if new_state == State.IDLE:
            self.focused_pane = None
            self.pending_transcript = None
            self.polished_text = None
            self.raw_transcript = None
            self.enhanced_transcript = None
            self.showing_raw = False

        # Clear polish state when returning to FOCUSED from PREVIEWING
        if old_state == State.PREVIEWING and new_state == State.FOCUSED:
            if action in ("reject_polished", "dismiss_preview"):
                self.polished_text = None
            elif action == "submit_polished":
                # polished_text stays for the submit handler to consume
                pass

        # Clear polish state when cancelling
        if old_state == State.POLISHING and new_state == State.FOCUSED:
            self.pending_transcript = None

        self.history.append((old_state, event, new_state, action))
        return new_state, action

    def reset(self):
        """Reset to IDLE."""
        self.state = State.IDLE
        self.focused_pane = None
        self.pending_transcript = None
        self.polished_text = None
        self.raw_transcript = None
        self.enhanced_transcript = None
        self.showing_raw = False

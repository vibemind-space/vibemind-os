"""Voice transcript → structured command via regex grammar."""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedCommand:
    """A parsed voice command."""
    action: str  # ask, edit, click, type, read, select, run_tests, apply, cancel, recalibrate, switch
    prompt: Optional[str] = None
    file_path: Optional[str] = None
    line_range: Optional[Tuple[int, int]] = None
    instruction: Optional[str] = None
    target: Optional[str] = None  # element description for click/type


# Pattern definitions: (regex, action, group_mapping)
# Group mapping: {group_index: field_name}
_PATTERNS = [
    # Control commands (highest priority)
    (r"^(?:apply|anwenden|bestätigen)$", "apply", {}),
    (r"^(?:cancel|abbrechen|stopp?)$", "cancel", {}),
    (r"^(?:recalibrate|kalibrieren|calibrate)$", "recalibrate", {}),
    (r"^(?:undo|rückgängig|zurück)$", "undo", {}),

    # Read element under gaze
    (r"^(?:read|lies|lies\s*vor|vorlesen)(?:\s+(?:this|das|hier))?$", "read", {}),

    # Click (with optional target description)
    (r"^(?:click|klick|klicke?)\s*(?:on\s+|auf\s+)?(.+)$", "click", {1: "target"}),
    (r"^(?:click|klick|klicke?)$", "click", {}),

    # Complex tasks — route to agent team (BEFORE type/edit to catch "schreibe 20 Seiten...")
    (r"^(?:schreibe?|write)\s+\d+\s+(?:seiten?|pages?)\s+(.+)$", "complex_task", {1: "prompt"}),
    (r"^(?:erstelle|create|erzeuge|generiere|generate)\s+.{15,}$", "complex_task", {0: "prompt"}),
    (r"^(?:plane?|planen?|design)\s+(.{10,})$", "complex_task", {1: "prompt"}),
    (r"^(?:analysiere?|analyze|analyse)\s+(.{10,})$", "complex_task", {1: "prompt"}),
    (r"^(?:recherchiere?|research)\s+(.{10,})$", "complex_task", {1: "prompt"}),
    (r"^(?:baue?|build|implementiere?|implement)\s+(.{15,})$", "complex_task", {1: "prompt"}),

    # Type text
    (r"^(?:type|tippe?|schreibe?|eingeben?)\s+(.+)$", "type", {1: "prompt"}),

    # Select
    (r"^(?:select|markiere?|auswählen)\s*(?:this|das|hier)?$", "select", {}),
    (r"^(?:select|markiere?|auswählen)\s+(.+)$", "select", {1: "target"}),

    # Edit with file + line range + instruction
    (r"^(?:edit|bearbeite?|ändere?)\s+(\S+)\s+lines?\s+(\d+)\s*[-–to]+\s*(\d+)\s*[:\s]+(.+)$",
     "edit", {1: "file_path", 2: "_line_start", 3: "_line_end", 4: "instruction"}),

    # Edit without file (uses gazed element context)
    (r"^(?:edit|bearbeite?|ändere?)\s*[:\s]+(.+)$", "edit", {1: "instruction"}),

    # Run tests
    (r"^(?:run\s+tests?|tests?\s+(?:ausführen|laufen)|teste?)$", "run_tests", {}),

    # Ask / general prompt (lowest priority — catches everything else prefixed with ask/frag)
    (r"^(?:ask|frag|frage)\s+(.+)$", "ask", {1: "prompt"}),

    # Switch pane
    (r"^(?:switch|wechsle?)\s+(?:to\s+)?(?:pane\s+)?(\d+)$", "switch", {1: "target"}),

    # Scroll
    (r"^(?:scroll)\s+(up|down|left|right|hoch|runter)(?:\s+(\d+))?$", "scroll", {1: "target", 2: "prompt"}),
]


class CommandParser:
    """Parse voice transcripts into structured commands."""

    def parse(self, transcript: str) -> Optional[ParsedCommand]:
        """Match transcript against grammar. Returns None if no match."""
        text = transcript.strip()
        if not text:
            return None

        for pattern, action, group_map in _PATTERNS:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                cmd = ParsedCommand(action=action)
                for group_idx, field_name in group_map.items():
                    value = match.group(group_idx)
                    if value is None:
                        continue
                    if field_name == "_line_start":
                        start = int(value)
                        end_val = match.group(group_idx + 1) if group_idx + 1 <= match.lastindex else None
                        cmd.line_range = (start, int(end_val) if end_val else start)
                    elif field_name == "_line_end":
                        continue  # handled by _line_start
                    else:
                        setattr(cmd, field_name, value.strip())
                return cmd

        # No pattern matched — treat as freeform prompt for AI intent resolution
        return ParsedCommand(action="freeform", prompt=text.strip())

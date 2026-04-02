#!/usr/bin/env python3
"""
Smart Agent Selector - Iteration 2

Intelligente Agent-Auswahl basierend auf Kontext und Fehler-Patterns.
Ersetzt RoundRobinGroupChat durch dynamische Selektion.

Features:
- Erkennt Error-Patterns in Messages
- Wechselt zu FixSuggestionAgent bei Fehlern
- Erkennt Stagnation (wiederholte gleiche Aktionen)
- Fallback-Logik für festgefahrene Situationen
"""

import re
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Rollen für Agents im System"""
    REASONING = "reasoning"        # Hauptagent: analysiert und führt aus
    FIX_SUGGESTION = "fix_suggestion"  # Hilfsagent: analysiert Fehler, schlägt Fixes vor
    VALIDATOR = "validator"        # Prüfagent: validiert Ergebnisse


# Error Patterns die einen Agent-Wechsel auslösen
ERROR_PATTERNS = [
    r"error[:\s]",
    r"failed",
    r"cannot\s",
    r"unable\s+to",
    r"exception",
    r"not\s+found",
    r"permission\s+denied",
    r"timeout",
    r"TS\d{4}:",  # TypeScript errors
    r"SyntaxError",
    r"TypeError",
    r"ReferenceError",
    r"Module\s+not\s+found",
    r"npm\s+ERR",
    r"ENOENT",
    r"EACCES",
    r"ECONNREFUSED",
]

# Stagnation Patterns
STAGNATION_PATTERNS = [
    r"I'll try again",
    r"Let me retry",
    r"attempting again",
    r"same error",
    r"still failing",
]


@dataclass
class AgentContext:
    """Kontext für Agent-Selektion"""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    error_count: int = 0
    stagnation_count: int = 0
    last_tool_call: Optional[str] = None
    consecutive_errors: int = 0
    switch_count: int = 0  # Wie oft wurde Agent gewechselt


@dataclass
class SelectionResult:
    """Ergebnis der Agent-Selektion"""
    selected_agent: str
    role: AgentRole
    reason: str
    confidence: float  # 0.0 - 1.0
    should_inject_guidance: bool = False
    guidance_text: Optional[str] = None


class SmartAgentSelector:
    """
    Intelligente Agent-Auswahl basierend auf Kontext.

    Analysiert Messages und entscheidet:
    - Welcher Agent als nächstes aktiv sein soll
    - Ob Guidance injiziert werden soll
    - Ob ein Agent-Wechsel sinnvoll ist
    """

    def __init__(
        self,
        reasoning_agent_name: str = "ReasoningAgent",
        fix_agent_name: str = "FixSuggestionAgent",
        validator_agent_name: str = "ValidatorAgent",
        max_consecutive_errors: int = 3,
        stagnation_threshold: int = 3
    ):
        """
        Args:
            reasoning_agent_name: Name des Haupt-Agents
            fix_agent_name: Name des Fix-Suggestion Agents
            validator_agent_name: Name des Validator Agents
            max_consecutive_errors: Nach X Fehlern zu FixAgent wechseln
            stagnation_threshold: Nach X gleichen Actions zu FixAgent wechseln
        """
        self.reasoning_agent = reasoning_agent_name
        self.fix_agent = fix_agent_name
        self.validator_agent = validator_agent_name

        self.max_consecutive_errors = max_consecutive_errors
        self.stagnation_threshold = stagnation_threshold

        # Compiled patterns for efficiency
        self._error_patterns = [re.compile(p, re.IGNORECASE) for p in ERROR_PATTERNS]
        self._stagnation_patterns = [re.compile(p, re.IGNORECASE) for p in STAGNATION_PATTERNS]

        # Context tracking
        self._context = AgentContext()
        self._recent_tool_calls: List[str] = []

        logger.info(f"SmartAgentSelector initialized (error_threshold={max_consecutive_errors})")

    def reset(self):
        """Reset den Selector-State"""
        self._context = AgentContext()
        self._recent_tool_calls = []

    def analyze_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analysiert eine einzelne Message auf Patterns.

        Args:
            message: Message dict mit content, source, etc.

        Returns:
            Dict mit has_error, has_stagnation, patterns_found
        """
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        # Error detection
        error_found = []
        for pattern in self._error_patterns:
            if pattern.search(content):
                error_found.append(pattern.pattern)

        # Stagnation detection
        stagnation_found = []
        for pattern in self._stagnation_patterns:
            if pattern.search(content):
                stagnation_found.append(pattern.pattern)

        return {
            "has_error": len(error_found) > 0,
            "has_stagnation": len(stagnation_found) > 0,
            "error_patterns": error_found,
            "stagnation_patterns": stagnation_found,
            "content_length": len(content)
        }

    def update_context(self, message: Dict[str, Any], tool_call: Optional[str] = None):
        """
        Aktualisiert den internen Kontext basierend auf einer neuen Message.

        Args:
            message: Neue Message
            tool_call: Name des Tool-Calls falls vorhanden
        """
        self._context.messages.append(message)

        # Analyse durchführen
        analysis = self.analyze_message(message)

        if analysis["has_error"]:
            self._context.error_count += 1
            self._context.consecutive_errors += 1
        else:
            self._context.consecutive_errors = 0

        if analysis["has_stagnation"]:
            self._context.stagnation_count += 1

        # Tool-Call tracking für Stagnation
        if tool_call:
            self._recent_tool_calls.append(tool_call)
            if len(self._recent_tool_calls) > 10:
                self._recent_tool_calls.pop(0)
            self._context.last_tool_call = tool_call

    def _detect_tool_stagnation(self) -> bool:
        """Erkennt ob die gleichen Tools wiederholt aufgerufen werden"""
        if len(self._recent_tool_calls) < self.stagnation_threshold:
            return False

        recent = self._recent_tool_calls[-self.stagnation_threshold:]
        return len(set(recent)) == 1  # Alle gleich

    def select_next_agent(
        self,
        current_agent: str,
        messages: Optional[List[Dict[str, Any]]] = None
    ) -> SelectionResult:
        """
        Wählt den nächsten Agent basierend auf Kontext.

        Args:
            current_agent: Aktueller Agent-Name
            messages: Optionale zusätzliche Messages für Analyse

        Returns:
            SelectionResult mit ausgewähltem Agent und Begründung
        """
        # Messages aktualisieren wenn gegeben
        if messages:
            for msg in messages:
                self.update_context(msg)

        # Default: Round-Robin zwischen Reasoning und Validator
        if current_agent == self.reasoning_agent:
            next_default = self.validator_agent
            next_role = AgentRole.VALIDATOR
        elif current_agent == self.validator_agent:
            next_default = self.reasoning_agent
            next_role = AgentRole.REASONING
        else:
            next_default = self.reasoning_agent
            next_role = AgentRole.REASONING

        # Check 1: Viele konsekutive Fehler -> FixSuggestionAgent
        if self._context.consecutive_errors >= self.max_consecutive_errors:
            self._context.switch_count += 1

            guidance = self._generate_error_guidance()
            return SelectionResult(
                selected_agent=self.fix_agent,
                role=AgentRole.FIX_SUGGESTION,
                reason=f"{self._context.consecutive_errors} consecutive errors detected",
                confidence=0.9,
                should_inject_guidance=True,
                guidance_text=guidance
            )

        # Check 2: Tool-Stagnation -> FixSuggestionAgent
        if self._detect_tool_stagnation():
            self._context.switch_count += 1

            tool = self._recent_tool_calls[-1] if self._recent_tool_calls else "unknown"
            guidance = f"The ReasoningAgent appears stuck calling '{tool}' repeatedly. Please analyze the situation and suggest an alternative approach."

            return SelectionResult(
                selected_agent=self.fix_agent,
                role=AgentRole.FIX_SUGGESTION,
                reason=f"Repeated tool calls to '{tool}'",
                confidence=0.85,
                should_inject_guidance=True,
                guidance_text=guidance
            )

        # Check 3: FixAgent war aktiv -> zurück zu Reasoning
        if current_agent == self.fix_agent:
            # Reset error counter nach Fix-Vorschlag
            self._context.consecutive_errors = 0

            return SelectionResult(
                selected_agent=self.reasoning_agent,
                role=AgentRole.REASONING,
                reason="Returning to ReasoningAgent after fix suggestion",
                confidence=0.95
            )

        # Default: Standard Round-Robin
        return SelectionResult(
            selected_agent=next_default,
            role=next_role,
            reason="Standard round-robin progression",
            confidence=1.0
        )

    def _generate_error_guidance(self) -> str:
        """Generiert Guidance-Text für den FixSuggestionAgent"""
        recent_errors = []

        # Letzte Messages auf Fehler durchsuchen
        for msg in self._context.messages[-5:]:
            analysis = self.analyze_message(msg)
            if analysis["has_error"]:
                content = msg.get("content", "")[:300]
                recent_errors.append(content)

        error_summary = "\n".join(recent_errors) if recent_errors else "Multiple errors occurred"

        return f"""The ReasoningAgent has encountered {self._context.consecutive_errors} consecutive errors.

Recent error context:
{error_summary}

Please analyze these errors and suggest specific fixes. Focus on:
1. What is the root cause?
2. Which file(s) need to be modified?
3. What exact changes should be made?

Format your response as:
FIX_SUGGESTION:
- File: [path]
- Problem: [description]
- Solution: [specific code changes]
"""

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken über die Selektion zurück"""
        return {
            "total_messages": len(self._context.messages),
            "error_count": self._context.error_count,
            "stagnation_count": self._context.stagnation_count,
            "consecutive_errors": self._context.consecutive_errors,
            "switch_count": self._context.switch_count,
            "recent_tools": self._recent_tool_calls[-5:],
        }

    def should_switch_to_fix_agent(self, messages: List[Dict[str, Any]]) -> bool:
        """
        Quick-Check ob zu FixAgent gewechselt werden sollte.

        Args:
            messages: Aktuelle Message-Liste

        Returns:
            True wenn Switch sinnvoll
        """
        error_count = 0
        for msg in messages[-5:]:  # Letzte 5 Messages
            analysis = self.analyze_message(msg)
            if analysis["has_error"]:
                error_count += 1

        return error_count >= self.max_consecutive_errors


# =============================================================================
# FixSuggestionAgent Prompt
# =============================================================================

FIX_SUGGESTION_AGENT_PROMPT = """Du bist ein Fix Suggestion Agent.

## Deine Rolle:

Du analysierst Fehler die der ReasoningAgent nicht lösen konnte und schlägst
KONKRETE Fixes vor. Du darfst KEINE Dateien schreiben - nur analysieren und Vorschläge machen.

## Verfügbare Tools:

Du hast nur READ-ONLY Tools:
- read_file: Dateien lesen
- list_directory: Verzeichnisse auflisten
- search_files: Dateien suchen

## Arbeitsweise:

1. Analysiere den Fehler-Kontext
2. Lese relevante Dateien um das Problem zu verstehen
3. Identifiziere die Root Cause
4. Formuliere einen konkreten Fix-Vorschlag

## Output Format:

Wenn du einen Fix vorschlägst, nutze IMMER dieses Format:

```
FIX_SUGGESTION:
- File: [vollständiger Pfad zur Datei]
- Problem: [kurze Beschreibung des Problems]
- Line: [betroffene Zeile(n) wenn bekannt]
- Solution: [konkreter Code oder Änderung]
```

## Wichtige Regeln:

- Du darfst KEINE write_file oder ähnliche Tools nutzen
- Deine Vorschläge werden vom ReasoningAgent umgesetzt
- Sei präzise und konkret - kein "könnte" oder "vielleicht"
- Wenn du mehrere Fixes brauchst, liste sie alle auf
- Nach deinem Vorschlag gibt der ReasoningAgent die Kontrolle weiter
"""


# =============================================================================
# Agent Factory
# =============================================================================

def create_fix_suggestion_agent(
    model_client,
    read_tools: List[Any],
    buffer_size: int = 10
):
    """
    Factory-Funktion um einen FixSuggestionAgent zu erstellen.

    Args:
        model_client: Der Model-Client für den Agent
        read_tools: Liste von read-only Tools
        buffer_size: Größe des Message-Buffers

    Returns:
        AssistantAgent konfiguriert als FixSuggestionAgent
    """
    # Import hier um zirkuläre Imports zu vermeiden
    from autogen_agentchat.agents import AssistantAgent
    from autogen_core.model_context import BufferedChatCompletionContext

    # Nur read-only Tools erlauben
    safe_tools = []
    read_only_patterns = ['read', 'list', 'get', 'search', 'find', 'describe', 'show']

    for tool in read_tools:
        tool_name = getattr(tool, "name", "").lower()
        if any(pattern in tool_name for pattern in read_only_patterns):
            safe_tools.append(tool)

    logger.info(f"Creating FixSuggestionAgent with {len(safe_tools)} read-only tools")

    return AssistantAgent(
        name="FixSuggestionAgent",
        model_client=model_client,
        tools=safe_tools,
        system_message=FIX_SUGGESTION_AGENT_PROMPT,
        model_context=BufferedChatCompletionContext(buffer_size=buffer_size),
    )


# =============================================================================
# Custom GroupChat Selector Function
# =============================================================================

def create_selector_function(
    selector: SmartAgentSelector,
    agents: List[Any]
) -> Callable:
    """
    Erstellt eine Selector-Funktion für SelectorGroupChat.

    Args:
        selector: SmartAgentSelector Instanz
        agents: Liste der verfügbaren Agents

    Returns:
        Callable für SelectorGroupChat
    """
    agent_map = {agent.name: agent for agent in agents}

    def select_speaker(last_speaker: Any, messages: List[Any]) -> Any:
        """Wählt den nächsten Speaker basierend auf SmartAgentSelector"""
        last_name = last_speaker.name if last_speaker else "unknown"

        # Messages für Analyse konvertieren
        msg_dicts = []
        for msg in messages[-5:]:  # Letzte 5
            content = getattr(msg, 'content', '')
            if isinstance(content, list):
                content = ' '.join(str(c) for c in content)
            msg_dicts.append({
                "content": content,
                "source": getattr(msg, 'source', 'unknown')
            })

        # Selektion durchführen
        result = selector.select_next_agent(last_name, msg_dicts)

        logger.debug(f"Agent selection: {last_name} -> {result.selected_agent} ({result.reason})")

        return agent_map.get(result.selected_agent, agents[0])

    return select_speaker


# =============================================================================
# Test
# =============================================================================

def test_selector():
    """Test der SmartAgentSelector Logik"""
    print("=== SmartAgentSelector Test ===\n")

    selector = SmartAgentSelector(max_consecutive_errors=2)

    # Test 1: Normal progression
    print("1. Normal progression (no errors):")
    result = selector.select_next_agent("ReasoningAgent")
    print(f"   {result.selected_agent} (reason: {result.reason})")

    result = selector.select_next_agent("ValidatorAgent")
    print(f"   {result.selected_agent} (reason: {result.reason})")

    # Test 2: Error detection
    print("\n2. Error detection:")
    selector.reset()

    error_msgs = [
        {"content": "Error: Cannot read file", "source": "tool"},
        {"content": "Failed to write file: permission denied", "source": "tool"},
    ]

    for msg in error_msgs:
        selector.update_context(msg)
        print(f"   Added: '{msg['content'][:40]}...'")

    result = selector.select_next_agent("ReasoningAgent")
    print(f"   Selected: {result.selected_agent}")
    print(f"   Reason: {result.reason}")
    print(f"   Guidance: {result.should_inject_guidance}")

    # Test 3: Stagnation detection
    print("\n3. Stagnation detection:")
    selector.reset()

    for _ in range(3):
        selector.update_context({"content": "Trying again...", "source": "agent"}, "read_file")

    result = selector.select_next_agent("ReasoningAgent")
    print(f"   Selected: {result.selected_agent}")
    print(f"   Reason: {result.reason}")

    # Stats
    print("\n4. Stats:")
    print(f"   {selector.get_stats()}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_selector()

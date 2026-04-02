#!/usr/bin/env python3
"""
Adaptive Prompts - Iteration 5

Generiert dynamische Prompts basierend auf historischen Learnings.

Features:
- Erfolgreiche Tool-Sequenzen einbinden
- Häufige Fehler als Warnung
- Task-spezifische Empfehlungen
- Performance-Hinweise
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

# Optional imports - graceful degradation wenn nicht verfügbar
try:
    from execution_history import ExecutionHistoryStore, ToolStats
    HISTORY_AVAILABLE = True
except ImportError:
    HISTORY_AVAILABLE = False

try:
    from tool_category_filter import ToolCategoryFilter
    FILTER_AVAILABLE = True
except ImportError:
    FILTER_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PromptContext:
    """Kontext für Prompt-Generierung"""
    task_type: str
    task_description: str
    available_tools: List[str]
    recommended_tools: List[str] = None
    common_errors: List[str] = None
    successful_patterns: List[List[str]] = None
    performance_hints: List[str] = None


class AdaptivePromptGenerator:
    """
    Generiert dynamische Prompts mit historischen Learnings.

    Nutzt Ausführungshistorie um Prompts zu optimieren.
    """

    BASE_REASONING_PROMPT = """Du bist ein Reasoning Agent für das EventFix Team.
Deine Aufgabe: Analysiere Anfragen und löse sie durch gezielte Tool Calls.

{tools_section}

{recommendations_section}

{warnings_section}

{patterns_section}

## Arbeitsweise:

1. **Analyse**: Verstehe was die Aufgabe erfordert
2. **Planung**: Identifiziere die nötigen Tools und ihre Reihenfolge
3. **Ausführung**: Rufe Tools auf und verarbeite Ergebnisse
4. **Validierung**: Prüfe ob das Ergebnis korrekt ist
5. **Abschluss**: Sage TASK_COMPLETE wenn fertig

## Regeln:

- Führe nur die nötigen Tool Calls aus
- Prüfe Ergebnisse bevor du weitermachst
- Bei Fehlern: Analysiere und versuche Alternative
- Dokumentiere wichtige Schritte
- Sage TASK_COMPLETE nur wenn die Aufgabe wirklich erledigt ist
"""

    def __init__(
        self,
        history_store: Optional['ExecutionHistoryStore'] = None,
        tool_filter: Optional['ToolCategoryFilter'] = None
    ):
        """
        Args:
            history_store: Optional ExecutionHistoryStore für Learnings
            tool_filter: Optional ToolCategoryFilter für Tool-Kategorisierung
        """
        self.history = history_store
        self.filter = tool_filter

        logger.info(f"AdaptivePromptGenerator initialized (history={history_store is not None})")

    def generate_reasoning_prompt(
        self,
        task_type: str,
        task: str,
        available_tools: List[str]
    ) -> str:
        """
        Generiert einen adaptiven Reasoning-Prompt.

        Args:
            task_type: Art der Aufgabe
            task: Aufgabenbeschreibung
            available_tools: Liste verfügbarer Tools

        Returns:
            Generierter Prompt
        """
        context = self._build_context(task_type, task, available_tools)

        # Sections generieren
        tools_section = self._generate_tools_section(context)
        recommendations_section = self._generate_recommendations_section(context)
        warnings_section = self._generate_warnings_section(context)
        patterns_section = self._generate_patterns_section(context)

        return self.BASE_REASONING_PROMPT.format(
            tools_section=tools_section,
            recommendations_section=recommendations_section,
            warnings_section=warnings_section,
            patterns_section=patterns_section
        )

    def _build_context(
        self,
        task_type: str,
        task: str,
        available_tools: List[str]
    ) -> PromptContext:
        """Baut den Kontext für die Prompt-Generierung"""
        context = PromptContext(
            task_type=task_type,
            task_description=task,
            available_tools=available_tools,
            recommended_tools=[],
            common_errors=[],
            successful_patterns=[],
            performance_hints=[]
        )

        # Historische Daten laden wenn verfügbar
        if self.history and HISTORY_AVAILABLE:
            try:
                # Empfohlene Tools
                recs = self.history.get_recommendations(task_type, limit=5)
                context.recommended_tools = [r["tool_name"] for r in recs]

                # Erfolgreiche Patterns
                patterns = self.history.get_successful_patterns(task_type, min_occurrences=2)
                context.successful_patterns = [p.tools_sequence for p in patterns[:3]]

                # Tool-Stats für Warnungen
                for tool in available_tools[:10]:  # Nur top 10 prüfen
                    stats = self.history.get_tool_stats(tool)
                    if stats.common_errors:
                        context.common_errors.extend(stats.common_errors[:2])

                    # Performance-Hinweise
                    if stats.avg_duration_ms > 5000:
                        context.performance_hints.append(
                            f"{tool} ist langsam (avg {stats.avg_duration_ms:.0f}ms)"
                        )

            except Exception as e:
                logger.warning(f"Could not load history data: {e}")

        return context

    def _generate_tools_section(self, context: PromptContext) -> str:
        """Generiert die Tools-Sektion"""
        if not context.available_tools:
            return "## Keine Tools verfügbar"

        # Tools nach Kategorie gruppieren wenn Filter verfügbar
        if self.filter and FILTER_AVAILABLE:
            categories: Dict[str, List[str]] = {}

            for tool in context.available_tools:
                cat = self.filter.categorize_tool(tool).value.capitalize()
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(tool)

            lines = ["## Verfügbare Tools:"]
            for cat, tools in sorted(categories.items()):
                lines.append(f"\n### {cat}")
                for tool in tools[:10]:  # Max 10 pro Kategorie
                    marker = " ⭐" if tool in context.recommended_tools else ""
                    lines.append(f"- {tool}{marker}")
                if len(tools) > 10:
                    lines.append(f"- ... und {len(tools) - 10} weitere")

            return "\n".join(lines)
        else:
            # Einfache Liste
            tools_list = "\n".join(f"- {t}" for t in context.available_tools[:30])
            return f"## Verfügbare Tools:\n\n{tools_list}"

    def _generate_recommendations_section(self, context: PromptContext) -> str:
        """Generiert die Empfehlungs-Sektion"""
        if not context.recommended_tools:
            return ""

        lines = ["## Empfohlene Tools (basierend auf Historie):", ""]
        for tool in context.recommended_tools[:5]:
            lines.append(f"- ⭐ {tool}")

        lines.append("")
        lines.append("Diese Tools hatten die höchste Erfolgsrate bei ähnlichen Aufgaben.")

        return "\n".join(lines)

    def _generate_warnings_section(self, context: PromptContext) -> str:
        """Generiert Warnungen basierend auf häufigen Fehlern"""
        if not context.common_errors:
            return ""

        lines = ["## ⚠️ Häufige Fehler (vermeide diese):", ""]

        # Deduplizieren
        unique_errors = list(dict.fromkeys(context.common_errors))[:5]

        for error in unique_errors:
            lines.append(f"- {error[:100]}")

        return "\n".join(lines)

    def _generate_patterns_section(self, context: PromptContext) -> str:
        """Generiert Sektion mit erfolgreichen Patterns"""
        if not context.successful_patterns:
            return ""

        lines = ["## Bewährte Vorgehensweisen:", ""]

        for i, pattern in enumerate(context.successful_patterns[:3], 1):
            sequence = " → ".join(pattern[:5])
            if len(pattern) > 5:
                sequence += f" → ... ({len(pattern)} Tools)"
            lines.append(f"{i}. {sequence}")

        return "\n".join(lines)

    def generate_fix_suggestion_prompt(
        self,
        error_context: str,
        failed_tools: List[str],
        task_type: str
    ) -> str:
        """
        Generiert einen Prompt für den FixSuggestionAgent.

        Args:
            error_context: Beschreibung der Fehler
            failed_tools: Liste fehlgeschlagener Tools
            task_type: Art der Aufgabe

        Returns:
            Angepasster FixSuggestion Prompt
        """
        # Historische Fehler für diese Tools
        similar_errors = []
        if self.history and HISTORY_AVAILABLE:
            for tool in failed_tools[:3]:
                stats = self.history.get_tool_stats(tool)
                if stats.common_errors:
                    similar_errors.extend(stats.common_errors[:2])

        similar_section = ""
        if similar_errors:
            errors_list = "\n".join(f"- {e[:80]}" for e in similar_errors[:5])
            similar_section = f"""
## Ähnliche Fehler aus der Historie:

{errors_list}

Diese Fehler wurden bei ähnlichen Tasks beobachtet. Prüfe ob einer davon relevant ist.
"""

        return f"""Du bist ein Fix Suggestion Agent.

Analysiere den folgenden Fehler-Kontext und schlage konkrete Fixes vor.

## Fehler-Kontext:

{error_context}

## Fehlgeschlagene Tools:

{', '.join(failed_tools)}

{similar_section}

## Deine Aufgabe:

1. Analysiere die Root Cause
2. Lese relevante Dateien mit read_file
3. Formuliere einen konkreten Fix

## Output Format:

FIX_SUGGESTION:
- File: [Pfad]
- Problem: [Beschreibung]
- Solution: [Konkrete Änderung]
"""

    def generate_compact_prompt(
        self,
        task_type: str,
        available_tools: List[str]
    ) -> str:
        """
        Generiert einen kompakten Prompt für Token-Optimierung.

        Args:
            task_type: Art der Aufgabe
            available_tools: Verfügbare Tools

        Returns:
            Kompakter Prompt
        """
        recommended = []
        if self.history and HISTORY_AVAILABLE:
            try:
                recs = self.history.get_recommendations(task_type, limit=3)
                recommended = [r["tool_name"] for r in recs]
            except Exception:
                pass

        rec_hint = ""
        if recommended:
            rec_hint = f"\n\nEmpfohlen: {', '.join(recommended)}"

        return f"""Du bist ein Reasoning Agent. Nutze diese Tools:

{', '.join(available_tools[:20])}
{rec_hint}

Arbeitsweise: Analyse → Plan → Execute → Verify → TASK_COMPLETE

Sage TASK_COMPLETE nur wenn die Aufgabe erledigt ist.
"""

    def get_tool_tip(self, tool_name: str) -> Optional[str]:
        """
        Gibt einen Tipp für ein spezifisches Tool.

        Args:
            tool_name: Name des Tools

        Returns:
            Tipp-String oder None
        """
        if not self.history or not HISTORY_AVAILABLE:
            return None

        try:
            stats = self.history.get_tool_stats(tool_name)

            tips = []

            if stats.success_rate < 70 and stats.total_calls >= 5:
                tips.append(f"Niedrige Erfolgsrate ({stats.success_rate:.0f}%)")

            if stats.avg_duration_ms > 5000:
                tips.append(f"Langsam (avg {stats.avg_duration_ms:.0f}ms)")

            if stats.common_errors:
                tips.append(f"Häufiger Fehler: {stats.common_errors[0][:50]}")

            return " | ".join(tips) if tips else None

        except Exception:
            return None


# =============================================================================
# Test
# =============================================================================

def test_adaptive_prompts():
    """Test der AdaptivePromptGenerator"""
    print("=== Adaptive Prompts Test ===\n")

    # Ohne Historie (Fallback-Modus)
    generator = AdaptivePromptGenerator()

    tools = [
        "filesystem_read_file",
        "filesystem_write_file",
        "filesystem_list_directory",
        "docker_container_logs",
        "git_status",
        "git_commit",
    ]

    # Test 1: Basic prompt
    print("1. Basic reasoning prompt:")
    prompt = generator.generate_reasoning_prompt("write_code", "Erstelle eine Datei", tools)
    print(f"   Length: {len(prompt)} chars")
    print(f"   First 500 chars:\n{prompt[:500]}...")

    # Test 2: Compact prompt
    print("\n2. Compact prompt:")
    compact = generator.generate_compact_prompt("write_code", tools)
    print(compact)

    # Test 3: Fix suggestion prompt
    print("\n3. Fix suggestion prompt:")
    fix_prompt = generator.generate_fix_suggestion_prompt(
        "Error: Cannot write file - permission denied",
        ["filesystem_write_file"],
        "write_code"
    )
    print(f"   Length: {len(fix_prompt)} chars")
    print(f"   First 400 chars:\n{fix_prompt[:400]}...")

    # Test 4: Mit Mock-Filter
    print("\n4. With tool filter:")
    if FILTER_AVAILABLE:
        from tool_category_filter import ToolCategoryFilter
        filter = ToolCategoryFilter()
        generator_with_filter = AdaptivePromptGenerator(tool_filter=filter)

        prompt = generator_with_filter.generate_reasoning_prompt("write_code", "Test", tools)
        print(f"   Has categorized tools: {'### Filesystem' in prompt}")
    else:
        print("   Filter not available")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_adaptive_prompts()

#!/usr/bin/env python3
"""
Tool Category Filter - Iteration 1

Reduziert kognitiven Overload der Agents durch intelligente Tool-Filterung.
Statt 128 Tools werden nur ~15-30 kontextrelevante Tools geladen.

Features:
- Kategorisierung aller MCP Tools nach Typ
- Task-basierte Filterung (write_code, debug_docker, etc.)
- Priorisierung häufig genutzter Tools
- Max-Tool-Limit pro Task (default: 30)
"""

import re
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Kategorien für MCP Tools"""
    FILESYSTEM = "filesystem"
    DOCKER = "docker"
    DATABASE = "database"
    BROWSER = "browser"
    PACKAGE = "package"
    GIT = "git"
    WEB = "web"
    TIME = "time"
    MEMORY = "memory"
    SYSTEM = "system"
    UNKNOWN = "unknown"


# Tool-Name-Pattern zu Kategorie Mapping
TOOL_PATTERNS: Dict[str, ToolCategory] = {
    # Filesystem
    r"^filesystem[_\-]": ToolCategory.FILESYSTEM,
    r"read_file": ToolCategory.FILESYSTEM,
    r"write_file": ToolCategory.FILESYSTEM,
    r"list_directory": ToolCategory.FILESYSTEM,
    r"create_directory": ToolCategory.FILESYSTEM,
    r"delete_file": ToolCategory.FILESYSTEM,
    r"move_file": ToolCategory.FILESYSTEM,
    r"copy_file": ToolCategory.FILESYSTEM,
    r"search_files": ToolCategory.FILESYSTEM,
    r"get_file_info": ToolCategory.FILESYSTEM,
    r"file_": ToolCategory.FILESYSTEM,
    r"_file$": ToolCategory.FILESYSTEM,
    r"directory": ToolCategory.FILESYSTEM,

    # Docker
    r"^docker[_\-]": ToolCategory.DOCKER,
    r"container_": ToolCategory.DOCKER,
    r"compose_": ToolCategory.DOCKER,
    r"image_": ToolCategory.DOCKER,
    r"_container$": ToolCategory.DOCKER,
    r"docker": ToolCategory.DOCKER,

    # Database
    r"^postgres[_\-]": ToolCategory.DATABASE,
    r"^prisma[_\-]": ToolCategory.DATABASE,
    r"^redis[_\-]": ToolCategory.DATABASE,
    r"^supabase[_\-]": ToolCategory.DATABASE,
    r"query": ToolCategory.DATABASE,
    r"table": ToolCategory.DATABASE,
    r"database": ToolCategory.DATABASE,
    r"migrate": ToolCategory.DATABASE,
    r"schema": ToolCategory.DATABASE,

    # Browser
    r"^playwright[_\-]": ToolCategory.BROWSER,
    r"navigate": ToolCategory.BROWSER,
    r"click": ToolCategory.BROWSER,
    r"screenshot": ToolCategory.BROWSER,
    r"browser": ToolCategory.BROWSER,
    r"page_": ToolCategory.BROWSER,

    # Package
    r"^npm[_\-]": ToolCategory.PACKAGE,
    r"install": ToolCategory.PACKAGE,
    r"package": ToolCategory.PACKAGE,
    r"dependency": ToolCategory.PACKAGE,

    # Git
    r"^git[_\-]": ToolCategory.GIT,
    r"commit": ToolCategory.GIT,
    r"branch": ToolCategory.GIT,
    r"push": ToolCategory.GIT,
    r"pull": ToolCategory.GIT,
    r"merge": ToolCategory.GIT,
    r"status": ToolCategory.GIT,
    r"diff": ToolCategory.GIT,

    # Web/HTTP
    r"^fetch[_\-]": ToolCategory.WEB,
    r"^tavily[_\-]": ToolCategory.WEB,
    r"^brave[_\-]": ToolCategory.WEB,
    r"http": ToolCategory.WEB,
    r"request": ToolCategory.WEB,
    r"search": ToolCategory.WEB,
    r"web": ToolCategory.WEB,

    # Time
    r"^time[_\-]": ToolCategory.TIME,
    r"get_current_time": ToolCategory.TIME,
    r"convert_time": ToolCategory.TIME,

    # Memory
    r"^memory[_\-]": ToolCategory.MEMORY,
    r"store_": ToolCategory.MEMORY,
    r"retrieve_": ToolCategory.MEMORY,
    r"entity": ToolCategory.MEMORY,
    r"relation": ToolCategory.MEMORY,
    r"knowledge": ToolCategory.MEMORY,

    # System
    r"system": ToolCategory.SYSTEM,
    r"process": ToolCategory.SYSTEM,
    r"windows": ToolCategory.SYSTEM,
}


# Task-Typ zu Kategorien Mapping
TASK_TOOL_MAPPING: Dict[str, List[ToolCategory]] = {
    # Code-Aufgaben
    "write_code": [ToolCategory.FILESYSTEM],
    "fix_code": [ToolCategory.FILESYSTEM, ToolCategory.GIT],
    "read_code": [ToolCategory.FILESYSTEM],
    "refactor": [ToolCategory.FILESYSTEM, ToolCategory.GIT],

    # Debugging
    "debug_docker": [ToolCategory.DOCKER, ToolCategory.FILESYSTEM],
    "debug_runtime": [ToolCategory.DOCKER, ToolCategory.FILESYSTEM, ToolCategory.BROWSER],
    "debug_database": [ToolCategory.DATABASE, ToolCategory.DOCKER, ToolCategory.FILESYSTEM],

    # Database
    "database_query": [ToolCategory.DATABASE],
    "database_migrate": [ToolCategory.DATABASE, ToolCategory.FILESYSTEM],
    "database_setup": [ToolCategory.DATABASE, ToolCategory.DOCKER],

    # Testing
    "run_tests": [ToolCategory.FILESYSTEM, ToolCategory.PACKAGE],
    "e2e_test": [ToolCategory.BROWSER, ToolCategory.FILESYSTEM],
    "integration_test": [ToolCategory.BROWSER, ToolCategory.DATABASE, ToolCategory.DOCKER],

    # DevOps
    "deploy": [ToolCategory.DOCKER, ToolCategory.FILESYSTEM, ToolCategory.GIT],
    "container_management": [ToolCategory.DOCKER],
    "infrastructure": [ToolCategory.DOCKER, ToolCategory.FILESYSTEM],

    # Research
    "research": [ToolCategory.WEB, ToolCategory.FILESYSTEM],
    "web_search": [ToolCategory.WEB],
    "documentation": [ToolCategory.FILESYSTEM, ToolCategory.WEB],

    # General
    "general": [ToolCategory.FILESYSTEM, ToolCategory.GIT, ToolCategory.TIME],
    "any": [cat for cat in ToolCategory if cat != ToolCategory.UNKNOWN],
}


# Prioritäts-Scores für häufig genutzte Tools (höher = wichtiger)
TOOL_PRIORITY: Dict[str, int] = {
    # High priority - meist genutzt
    "filesystem_read_file": 100,
    "filesystem_write_file": 100,
    "filesystem_list_directory": 90,
    "filesystem_create_directory": 80,
    "filesystem_search_files": 85,

    # Medium priority
    "docker_container_logs": 70,
    "docker_compose_up": 70,
    "docker_container_stats": 60,

    "git_status": 65,
    "git_diff": 65,
    "git_commit": 60,

    "postgres_query": 70,
    "prisma_generate": 65,

    # Lower priority
    "fetch_request": 50,
    "time_get_current_time": 40,
}


@dataclass
class FilteredToolSet:
    """Ergebnis der Tool-Filterung"""
    tools: List[Any]  # Die gefilterten Tools
    categories: Set[ToolCategory]  # Aktive Kategorien
    total_available: int  # Ursprüngliche Anzahl
    filtered_count: int  # Nach Filterung
    task_type: str
    max_tools: int

    def __repr__(self) -> str:
        cats = ", ".join(c.value for c in self.categories)
        return f"FilteredToolSet({self.filtered_count}/{self.total_available} tools, categories=[{cats}])"


class ToolCategoryFilter:
    """
    Intelligenter Tool-Filter für MCP Agents.

    Reduziert die Tool-Anzahl basierend auf:
    1. Task-Typ (write_code, debug_docker, etc.)
    2. Tool-Kategorie (filesystem, docker, etc.)
    3. Prioritäts-Score (häufig genutzte Tools bevorzugen)
    """

    def __init__(
        self,
        max_tools: int = 30,
        always_include: Optional[List[str]] = None,
        always_exclude: Optional[List[str]] = None
    ):
        """
        Args:
            max_tools: Maximale Anzahl Tools nach Filterung
            always_include: Tool-Namen die immer inkludiert werden
            always_exclude: Tool-Namen die immer exkludiert werden
        """
        self.max_tools = max_tools
        self.always_include = set(always_include or [])
        self.always_exclude = set(always_exclude or [])

        # Cache für Tool-Kategorien
        self._category_cache: Dict[str, ToolCategory] = {}

        logger.info(f"ToolCategoryFilter initialized (max_tools={max_tools})")

    def categorize_tool(self, tool_name: str) -> ToolCategory:
        """
        Ermittelt die Kategorie eines Tools anhand seines Namens.

        Args:
            tool_name: Name des Tools (z.B. "filesystem_read_file")

        Returns:
            ToolCategory
        """
        # Cache check
        if tool_name in self._category_cache:
            return self._category_cache[tool_name]

        # Lowercase für Pattern-Matching
        name_lower = tool_name.lower()

        # Pattern-basierte Erkennung
        for pattern, category in TOOL_PATTERNS.items():
            if re.search(pattern, name_lower):
                self._category_cache[tool_name] = category
                return category

        # Fallback: Präfix-basierte Erkennung
        prefix = name_lower.split("_")[0] if "_" in name_lower else name_lower
        prefix_mapping = {
            "filesystem": ToolCategory.FILESYSTEM,
            "docker": ToolCategory.DOCKER,
            "postgres": ToolCategory.DATABASE,
            "prisma": ToolCategory.DATABASE,
            "redis": ToolCategory.DATABASE,
            "supabase": ToolCategory.DATABASE,
            "playwright": ToolCategory.BROWSER,
            "npm": ToolCategory.PACKAGE,
            "git": ToolCategory.GIT,
            "fetch": ToolCategory.WEB,
            "tavily": ToolCategory.WEB,
            "brave": ToolCategory.WEB,
            "time": ToolCategory.TIME,
            "memory": ToolCategory.MEMORY,
            "windows": ToolCategory.SYSTEM,
        }

        if prefix in prefix_mapping:
            category = prefix_mapping[prefix]
            self._category_cache[tool_name] = category
            return category

        # Unknown
        self._category_cache[tool_name] = ToolCategory.UNKNOWN
        return ToolCategory.UNKNOWN

    def get_tool_priority(self, tool_name: str) -> int:
        """
        Gibt die Priorität eines Tools zurück (höher = wichtiger).

        Args:
            tool_name: Tool-Name

        Returns:
            Prioritäts-Score (0-100)
        """
        # Exakte Match
        if tool_name in TOOL_PRIORITY:
            return TOOL_PRIORITY[tool_name]

        # Partial match
        for key, priority in TOOL_PRIORITY.items():
            if key in tool_name or tool_name in key:
                return priority

        # Default basierend auf Kategorie
        category = self.categorize_tool(tool_name)
        category_defaults = {
            ToolCategory.FILESYSTEM: 50,
            ToolCategory.DOCKER: 45,
            ToolCategory.DATABASE: 45,
            ToolCategory.GIT: 40,
            ToolCategory.BROWSER: 40,
            ToolCategory.PACKAGE: 35,
            ToolCategory.WEB: 30,
            ToolCategory.TIME: 25,
            ToolCategory.MEMORY: 30,
            ToolCategory.SYSTEM: 20,
            ToolCategory.UNKNOWN: 10,
        }
        return category_defaults.get(category, 10)

    def filter_for_task(
        self,
        all_tools: List[Any],
        task_type: str = "general",
        additional_categories: Optional[List[ToolCategory]] = None,
        max_override: Optional[int] = None
    ) -> FilteredToolSet:
        """
        Filtert Tools basierend auf Task-Typ.

        Args:
            all_tools: Liste aller verfügbaren Tools (AutoGen Tool-Objekte)
            task_type: Art der Aufgabe (write_code, debug_docker, etc.)
            additional_categories: Zusätzliche Kategorien die inkludiert werden
            max_override: Überschreibt max_tools für diesen Aufruf

        Returns:
            FilteredToolSet mit gefilterten Tools
        """
        max_tools = max_override or self.max_tools

        # Kategorien für diesen Task
        allowed_categories = set(TASK_TOOL_MAPPING.get(task_type, TASK_TOOL_MAPPING["general"]))
        if additional_categories:
            allowed_categories.update(additional_categories)

        # Filter und Scoring
        candidates: List[tuple] = []  # (priority, tool)

        for tool in all_tools:
            # Tool-Name extrahieren
            tool_name = getattr(tool, "name", None) or str(tool)

            # Always exclude
            if tool_name in self.always_exclude:
                continue

            # Always include
            if tool_name in self.always_include:
                candidates.append((200, tool))  # Höchste Priorität
                continue

            # Kategorie prüfen
            category = self.categorize_tool(tool_name)
            if category not in allowed_categories and category != ToolCategory.UNKNOWN:
                continue

            # Priorität ermitteln
            priority = self.get_tool_priority(tool_name)
            candidates.append((priority, tool))

        # Nach Priorität sortieren und begrenzen
        candidates.sort(key=lambda x: x[0], reverse=True)
        filtered_tools = [tool for _, tool in candidates[:max_tools]]

        # Statistiken sammeln
        actual_categories = set()
        for tool in filtered_tools:
            tool_name = getattr(tool, "name", None) or str(tool)
            actual_categories.add(self.categorize_tool(tool_name))

        result = FilteredToolSet(
            tools=filtered_tools,
            categories=actual_categories,
            total_available=len(all_tools),
            filtered_count=len(filtered_tools),
            task_type=task_type,
            max_tools=max_tools
        )

        logger.info(f"Tool filtering: {result}")
        return result

    def get_categories_for_task(self, task_type: str) -> List[ToolCategory]:
        """Gibt die empfohlenen Kategorien für einen Task-Typ zurück."""
        return TASK_TOOL_MAPPING.get(task_type, TASK_TOOL_MAPPING["general"])

    def list_all_categories(self) -> List[str]:
        """Gibt alle verfügbaren Kategorien zurück."""
        return [cat.value for cat in ToolCategory if cat != ToolCategory.UNKNOWN]

    def list_all_task_types(self) -> List[str]:
        """Gibt alle konfigurierten Task-Typen zurück."""
        return list(TASK_TOOL_MAPPING.keys())

    def analyze_tools(self, tools: List[Any]) -> Dict[str, Any]:
        """
        Analysiert eine Tool-Liste und gibt Statistiken zurück.

        Args:
            tools: Liste von Tools

        Returns:
            Dict mit Kategorie-Verteilung und Top-Tools
        """
        category_counts: Dict[str, int] = {}
        tool_priorities: List[tuple] = []

        for tool in tools:
            tool_name = getattr(tool, "name", None) or str(tool)
            category = self.categorize_tool(tool_name)

            cat_name = category.value
            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

            priority = self.get_tool_priority(tool_name)
            tool_priorities.append((tool_name, priority, cat_name))

        # Sortieren nach Priorität
        tool_priorities.sort(key=lambda x: x[1], reverse=True)

        return {
            "total_tools": len(tools),
            "category_distribution": category_counts,
            "top_10_by_priority": tool_priorities[:10],
            "bottom_10_by_priority": tool_priorities[-10:] if len(tool_priorities) >= 10 else tool_priorities,
        }


# =============================================================================
# Prompt Generator
# =============================================================================

class DynamicPromptGenerator:
    """
    Generiert dynamische System-Prompts basierend auf verfügbaren Tools.

    Statt einem statischen Prompt mit allen 100+ Tools wird der Prompt
    dynamisch generiert mit nur den relevanten Tools.
    """

    BASE_PROMPT = """Du bist ein Reasoning Agent für das EventFix Team.
Deine Aufgabe: Analysiere Anfragen und löse sie durch gezielte Tool Calls.

## Verfügbare Tools für diese Aufgabe:

{tool_sections}

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

{task_specific_hints}
"""

    TASK_HINTS = {
        "write_code": """
## Hinweise für Code-Aufgaben:

- Lese zuerst existierende Dateien um den Kontext zu verstehen
- Prüfe Imports und Dependencies bevor du schreibst
- Teste nach dem Schreiben durch Lesen der Datei
""",
        "fix_code": """
## Hinweise für Code-Fixes:

- Lese die fehlerhaften Dateien vollständig
- Verstehe den Error-Kontext (Zeile, Import, Typ)
- Schreibe nur die minimale Änderung
- Verifiziere nach dem Fix durch erneutes Lesen
""",
        "debug_docker": """
## Hinweise für Docker-Debugging:

- Prüfe Container-Status und Logs
- Überprüfe Environment-Variablen
- Bei Netzwerk-Problemen: ports und networks checken
""",
        "database_query": """
## Hinweise für Datenbank-Aufgaben:

- Nutze EXPLAIN für Query-Analyse
- Bei Schema-Änderungen: erst list_tables
- Transaktionen für destruktive Operationen
""",
    }

    def __init__(self, filter_instance: ToolCategoryFilter):
        self.filter = filter_instance

    def generate_prompt(
        self,
        filtered_tools: FilteredToolSet,
        task_type: str = "general"
    ) -> str:
        """
        Generiert einen dynamischen Prompt basierend auf gefilterten Tools.

        Args:
            filtered_tools: FilteredToolSet vom ToolCategoryFilter
            task_type: Task-Typ für spezifische Hints

        Returns:
            Generierter System-Prompt
        """
        # Tools nach Kategorie gruppieren
        tools_by_category: Dict[str, List[str]] = {}

        for tool in filtered_tools.tools:
            tool_name = getattr(tool, "name", None) or str(tool)
            category = self.filter.categorize_tool(tool_name)
            cat_name = category.value.capitalize()

            if cat_name not in tools_by_category:
                tools_by_category[cat_name] = []

            # Tool-Beschreibung wenn verfügbar
            description = getattr(tool, "description", "")
            if description:
                tools_by_category[cat_name].append(f"- {tool_name}: {description[:100]}")
            else:
                tools_by_category[cat_name].append(f"- {tool_name}")

        # Sections generieren
        sections = []
        for category, tools in sorted(tools_by_category.items()):
            section = f"### {category}\n"
            section += "\n".join(tools[:15])  # Max 15 Tools pro Kategorie anzeigen
            if len(tools) > 15:
                section += f"\n... und {len(tools) - 15} weitere"
            sections.append(section)

        tool_sections = "\n\n".join(sections)

        # Task-spezifische Hints
        task_hints = self.TASK_HINTS.get(task_type, "")

        # Prompt zusammenbauen
        return self.BASE_PROMPT.format(
            tool_sections=tool_sections,
            task_specific_hints=task_hints
        )

    def generate_compact_prompt(self, filtered_tools: FilteredToolSet) -> str:
        """
        Generiert einen kompakten Prompt für Token-Optimierung.
        Listet nur die Tool-Namen ohne Beschreibungen.
        """
        tool_names = [
            getattr(tool, "name", str(tool))
            for tool in filtered_tools.tools
        ]

        return f"""Du bist ein Reasoning Agent. Nutze diese Tools:

{', '.join(tool_names)}

Arbeitsweise: Analyse → Plan → Execute → Verify → TASK_COMPLETE

Sage TASK_COMPLETE nur wenn die Aufgabe erledigt ist.
"""


# =============================================================================
# Test
# =============================================================================

def test_filter():
    """Test der Tool-Filterung"""
    print("=== Tool Category Filter Test ===\n")

    # Mock Tools
    class MockTool:
        def __init__(self, name, description=""):
            self.name = name
            self.description = description

    mock_tools = [
        MockTool("filesystem_read_file", "Read a file"),
        MockTool("filesystem_write_file", "Write a file"),
        MockTool("filesystem_list_directory", "List directory"),
        MockTool("filesystem_create_directory", "Create directory"),
        MockTool("filesystem_delete_file", "Delete file"),
        MockTool("filesystem_search_files", "Search files"),
        MockTool("docker_container_logs", "Get logs"),
        MockTool("docker_container_stats", "Get stats"),
        MockTool("docker_compose_up", "Start compose"),
        MockTool("docker_compose_down", "Stop compose"),
        MockTool("postgres_query", "Execute query"),
        MockTool("postgres_list_tables", "List tables"),
        MockTool("prisma_generate", "Generate client"),
        MockTool("git_status", "Git status"),
        MockTool("git_diff", "Git diff"),
        MockTool("git_commit", "Git commit"),
        MockTool("playwright_navigate", "Navigate browser"),
        MockTool("playwright_click", "Click element"),
        MockTool("npm_install", "Install packages"),
        MockTool("npm_run", "Run script"),
        MockTool("fetch_request", "HTTP request"),
        MockTool("tavily_search", "Web search"),
        MockTool("time_get_current_time", "Get time"),
        MockTool("memory_store_entity", "Store entity"),
        MockTool("windows_core_exec", "Execute command"),
    ]

    filter = ToolCategoryFilter(max_tools=30)

    # Test verschiedene Task-Typen
    print("1. Task: write_code")
    result = filter.filter_for_task(mock_tools, "write_code")
    print(f"   {result}")
    print(f"   Tools: {[t.name for t in result.tools]}\n")

    print("2. Task: debug_docker")
    result = filter.filter_for_task(mock_tools, "debug_docker")
    print(f"   {result}")
    print(f"   Tools: {[t.name for t in result.tools]}\n")

    print("3. Task: database_query")
    result = filter.filter_for_task(mock_tools, "database_query")
    print(f"   {result}")
    print(f"   Tools: {[t.name for t in result.tools]}\n")

    print("4. Task: general (max 10)")
    result = filter.filter_for_task(mock_tools, "general", max_override=10)
    print(f"   {result}")
    print(f"   Tools: {[t.name for t in result.tools]}\n")

    # Analyze
    print("5. Tool Analysis:")
    analysis = filter.analyze_tools(mock_tools)
    print(f"   Total: {analysis['total_tools']}")
    print(f"   Categories: {analysis['category_distribution']}")
    print(f"   Top 5: {analysis['top_10_by_priority'][:5]}")

    # Dynamic Prompt
    print("\n6. Dynamic Prompt (write_code):")
    prompt_gen = DynamicPromptGenerator(filter)
    result = filter.filter_for_task(mock_tools, "write_code")
    prompt = prompt_gen.generate_prompt(result, "write_code")
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   First 500 chars:\n{prompt[:500]}...")


if __name__ == "__main__":
    test_filter()

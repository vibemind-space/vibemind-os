"""
Task-spezifische Prompts für den EventFix Orchestrator

Dieses Modul enthält spezialisierte Prompts für verschiedene Task-Typen,
die den ReasoningAgent bei der Ausführung unterstützen.
"""
from typing import Dict, Any

# ============================================================================
# Task-Type Prompts
# ============================================================================

TASK_PROMPTS: Dict[str, str] = {

    # -------------------------------------------------------------------------
    # Code & File Operations
    # -------------------------------------------------------------------------

    "write_code": """
## Aufgabe: Code schreiben

Schreibe Code in die angegebene Datei.

**Schritte:**
1. Prüfe ob das Verzeichnis existiert (filesystem.list_directory)
2. Falls nötig, erstelle das Verzeichnis (filesystem.create_directory)
3. Schreibe die Datei (filesystem.write_file)
4. Verifiziere den Inhalt (filesystem.read_file)

**Parameter:**
- Datei: {file_path}
- Inhalt: {content}

**Erfolgskriterium:** Datei existiert mit korrektem Inhalt.
""",

    "read_code": """
## Aufgabe: Code lesen

Lese den Inhalt einer Datei und analysiere ihn.

**Schritte:**
1. Lese die Datei (filesystem.read_file)
2. Analysiere den Inhalt
3. Fasse wichtige Informationen zusammen

**Parameter:**
- Datei: {file_path}

**Erfolgskriterium:** Dateiinhalt erfolgreich gelesen und analysiert.
""",

    "fix_code": """
## Aufgabe: Code-Fehler beheben

Behebe den beschriebenen Fehler im Code.

**Schritte:**
1. Lese die betroffene Datei (filesystem.read_file)
2. Analysiere den Fehler und finde die Ursache
3. Erstelle den korrigierten Code
4. Schreibe die Korrektur (filesystem.write_file)
5. Validiere die Änderung (z.B. npm.run für Tests)

**Parameter:**
- Datei: {file_path}
- Fehler: {error_description}

**Erfolgskriterium:** Fehler behoben, Code funktioniert.
""",

    "create_files": """
## Aufgabe: Mehrere Dateien erstellen

Erstelle mehrere Dateien mit dem angegebenen Inhalt.

**Schritte:**
1. Für jede Datei in der Liste:
   a. Erstelle Verzeichnis falls nötig
   b. Schreibe die Datei
   c. Verifiziere den Inhalt
2. Bestätige alle erstellten Dateien

**Parameter:**
- Dateien: {files}

**Erfolgskriterium:** Alle Dateien erfolgreich erstellt.
""",

    # -------------------------------------------------------------------------
    # Docker Operations
    # -------------------------------------------------------------------------

    "debug_docker": """
## Aufgabe: Docker Container debuggen

Analysiere den Docker Container und finde Probleme.

**Schritte:**
1. Hole Container-Logs (docker.container_logs)
2. Prüfe Container-Stats (docker.container_stats)
3. Analysiere die Ausgabe auf Fehler
4. Identifiziere die Ursache
5. Schlage Lösung vor

**Parameter:**
- Container: {container_name}
- Tail: {tail}

**Erfolgskriterium:** Problem identifiziert und Lösung vorgeschlagen.
""",

    "container_restart": """
## Aufgabe: Container neu starten

Starte den Docker Container neu.

**Schritte:**
1. Stoppe den Container (docker.container_stop)
2. Warte kurz
3. Starte den Container (docker.container_start)
4. Prüfe den Status (docker.container_logs)

**Parameter:**
- Container: {container_name}

**Erfolgskriterium:** Container läuft wieder.
""",

    "docker_compose_up": """
## Aufgabe: Docker Compose starten

Starte alle Services via Docker Compose.

**Schritte:**
1. Führe docker-compose up aus (docker.compose_up)
2. Warte auf Service-Start
3. Prüfe alle Container-Status
4. Verifiziere Connectivity

**Parameter:**
- Compose-Datei: {compose_file}
- Services: {services}

**Erfolgskriterium:** Alle Services laufen.
""",

    # -------------------------------------------------------------------------
    # Database Operations
    # -------------------------------------------------------------------------

    "database_query": """
## Aufgabe: Datenbank-Query ausführen

Führe eine SQL-Query auf der Datenbank aus.

**Schritte:**
1. Validiere die Query-Syntax
2. Führe die Query aus (postgres.query)
3. Formatiere das Ergebnis
4. Analysiere bei Bedarf

**Parameter:**
- Query: {query}
- Datenbank: {database}

**Erfolgskriterium:** Query erfolgreich ausgeführt.
""",

    "debug_postgres": """
## Aufgabe: PostgreSQL debuggen

Analysiere PostgreSQL-Probleme.

**Schritte:**
1. Liste Tabellen auf (postgres.list_tables)
2. Prüfe Verbindungsstatus
3. Analysiere langsame Queries (postgres.explain_query)
4. Prüfe Table-Stats (postgres.get_table_stats)

**Parameter:**
- Datenbank: {database}
- Query: {query}

**Erfolgskriterium:** Problem identifiziert und analysiert.
""",

    "migrate_database": """
## Aufgabe: Datenbank-Migration

Führe eine Datenbank-Migration aus.

**Schritte:**
1. Prüfe aktuellen Status (prisma.migrate_status)
2. Validiere Schema (prisma.validate)
3. Erstelle Migration (prisma.migrate)
4. Wende Migration an (prisma.db_push)
5. Verifiziere Ergebnis

**Parameter:**
- Migration: {migration_name}
- Schema: {schema_file}

**Erfolgskriterium:** Migration erfolgreich angewendet.
""",

    # -------------------------------------------------------------------------
    # Testing Operations
    # -------------------------------------------------------------------------

    "playwright_tests": """
## Aufgabe: E2E Tests mit Playwright

Führe End-to-End Tests im Browser aus.

**Schritte:**
1. Navigiere zur URL (playwright.navigate)
2. Führe die Test-Aktionen aus:
   - Klicken (playwright.click)
   - Eingaben (playwright.type)
   - Warten (playwright.wait)
3. Mache Screenshots bei wichtigen Schritten
4. Validiere das Ergebnis

**Parameter:**
- URL: {url}
- Test: {test_description}
- Aktionen: {actions}

**Erfolgskriterium:** Alle Tests bestanden.
""",

    "run_tests": """
## Aufgabe: Tests ausführen

Führe die Test-Suite aus.

**Schritte:**
1. Führe Tests aus (npm.run mit test-Script)
2. Analysiere Ergebnisse
3. Identifiziere fehlgeschlagene Tests
4. Schlage Fixes vor bei Fehlern

**Parameter:**
- Test-Befehl: {test_command}
- Verzeichnis: {working_dir}

**Erfolgskriterium:** Tests erfolgreich oder Fehler dokumentiert.
""",

    # -------------------------------------------------------------------------
    # Git Operations
    # -------------------------------------------------------------------------

    "git_status": """
## Aufgabe: Git-Status prüfen

Prüfe den aktuellen Git-Status.

**Schritte:**
1. Hole Git-Status (git.status)
2. Zeige Änderungen (git.diff)
3. Liste Branches (git.branch)
4. Fasse zusammen

**Parameter:**
- Repository: {repo_path}

**Erfolgskriterium:** Status vollständig erfasst.
""",

    "git_commit": """
## Aufgabe: Git Commit erstellen

Erstelle einen Git-Commit mit den aktuellen Änderungen.

**Schritte:**
1. Prüfe Status (git.status)
2. Stage Änderungen (git.add)
3. Erstelle Commit (git.commit)
4. Verifiziere (git.log)

**Parameter:**
- Nachricht: {commit_message}
- Dateien: {files}

**Erfolgskriterium:** Commit erfolgreich erstellt.
""",

    # -------------------------------------------------------------------------
    # Package Management
    # -------------------------------------------------------------------------

    "npm_install": """
## Aufgabe: NPM Pakete installieren

Installiere NPM-Pakete.

**Schritte:**
1. Lese package.json (npm.read_package_json)
2. Installiere Pakete (npm.install)
3. Prüfe auf Vulnerabilities (npm.audit)
4. Verifiziere Installation (npm.list)

**Parameter:**
- Pakete: {packages}
- Dev: {dev_dependency}

**Erfolgskriterium:** Pakete erfolgreich installiert.
""",

    "npm_run": """
## Aufgabe: NPM Script ausführen

Führe ein NPM-Script aus.

**Schritte:**
1. Prüfe verfügbare Scripts (npm.read_package_json)
2. Führe Script aus (npm.run)
3. Analysiere Output
4. Handle Fehler

**Parameter:**
- Script: {script_name}
- Args: {script_args}

**Erfolgskriterium:** Script erfolgreich ausgeführt.
""",

    # -------------------------------------------------------------------------
    # Web/Search Operations
    # -------------------------------------------------------------------------

    "web_search": """
## Aufgabe: Web-Suche durchführen

Suche im Web nach Informationen.

**Schritte:**
1. Formuliere Suchanfrage
2. Führe Suche aus (tavily.search oder brave-search)
3. Analysiere Ergebnisse
4. Fasse relevante Informationen zusammen

**Parameter:**
- Suchanfrage: {query}
- Max Ergebnisse: {max_results}

**Erfolgskriterium:** Relevante Informationen gefunden.
""",

    "fetch_url": """
## Aufgabe: URL abrufen

Rufe Inhalt von einer URL ab.

**Schritte:**
1. Sende HTTP-Request (fetch.fetch)
2. Parse Response
3. Extrahiere relevante Daten

**Parameter:**
- URL: {url}
- Methode: {method}

**Erfolgskriterium:** Daten erfolgreich abgerufen.
""",

    # -------------------------------------------------------------------------
    # General/Fallback
    # -------------------------------------------------------------------------

    "general": """
## Aufgabe: Allgemeine Aufgabe

Analysiere die Anfrage und führe die nötigen Schritte aus.

**Hinweise:**
- Identifiziere welche Tools benötigt werden
- Plane die Schritte in der richtigen Reihenfolge
- Führe aus und verifiziere

**Beschreibung:** {description}

**Erfolgskriterium:** Aufgabe wie beschrieben erledigt.
""",

    "analyze": """
## Aufgabe: Analyse durchführen

Analysiere den beschriebenen Sachverhalt.

**Schritte:**
1. Sammle relevante Informationen
2. Analysiere Zusammenhänge
3. Identifiziere Muster oder Probleme
4. Erstelle Zusammenfassung

**Gegenstand:** {subject}

**Erfolgskriterium:** Analyse vollständig und nachvollziehbar.
""",

    "debug_redis": """
## Aufgabe: Redis debuggen

Analysiere Redis-Status und -Probleme.

**Schritte:**
1. Prüfe Redis-Info (redis.info)
2. Liste Keys (redis.keys)
3. Analysiere Speichernutzung
4. Identifiziere Probleme

**Parameter:**
- Pattern: {key_pattern}

**Erfolgskriterium:** Redis-Status analysiert.
""",

}


# ============================================================================
# Helper Functions
# ============================================================================

def get_task_prompt(task_type: str, parameters: Dict[str, Any]) -> str:
    """
    Erstellt den vollständigen Prompt für einen Task-Typ

    Args:
        task_type: Typ des Tasks (z.B. "write_code", "debug_docker")
        parameters: Parameter für den Prompt

    Returns:
        Formatierter Prompt-String
    """
    template = TASK_PROMPTS.get(task_type)

    if template is None:
        # Fallback auf general
        template = TASK_PROMPTS.get("general", "Führe die Aufgabe aus: {description}")

    try:
        # Parameter einsetzen (fehlende werden ignoriert)
        return template.format_map(SafeDict(parameters))
    except Exception:
        # Bei Fehlern: Template unverändert zurückgeben
        return template


class SafeDict(dict):
    """Dict das fehlende Keys als {key} zurückgibt statt KeyError"""

    def __missing__(self, key):
        return f"{{{key}}}"


def list_task_types() -> list:
    """Gibt alle verfügbaren Task-Typen zurück"""
    return list(TASK_PROMPTS.keys())


def get_task_type_description(task_type: str) -> str:
    """
    Gibt eine kurze Beschreibung eines Task-Typs zurück

    Args:
        task_type: Task-Typ

    Returns:
        Erste Zeile des Prompts als Beschreibung
    """
    template = TASK_PROMPTS.get(task_type, "")
    if template:
        # Erste nicht-leere Zeile nach ## als Beschreibung
        for line in template.split("\n"):
            line = line.strip()
            if line.startswith("## Aufgabe:"):
                return line.replace("## Aufgabe:", "").strip()
    return task_type


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    print("=== Task Prompts ===\n")

    print("Verfügbare Task-Typen:")
    for task_type in list_task_types():
        desc = get_task_type_description(task_type)
        print(f"  - {task_type}: {desc}")

    print("\n=== Beispiel: write_code ===")
    prompt = get_task_prompt("write_code", {
        "file_path": "src/hello.py",
        "content": "print('Hello World')"
    })
    print(prompt)

    print("\n=== Beispiel: debug_docker ===")
    prompt = get_task_prompt("debug_docker", {
        "container_name": "my-app",
        "tail": 100
    })
    print(prompt)

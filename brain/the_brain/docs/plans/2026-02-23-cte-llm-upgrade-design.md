# CTE LLM-Upgrade + User-Awareness Design

## Problem

Die ContinuousThinkingEngine (CTE) hat 7 `_think_*` Methoden, davon sind 6 Template-basiert (String-Interpolation). Nur `_think_refine()` nutzt echte LLM-Agents via MicroAgentPool. Die Gedanken klingen repetitiv und oberflächlich — keine echte Intelligenz.

Zusätzlich fehlt jegliche User-Awareness: Die CTE denkt über Wissen nach, aber nicht über den User (Stimmung, Bedürfnisse, Interessen).

## Lösung

1. **Alle 6 Template-basierten `_think_*` Methoden durch LLM-Agent-Aufrufe ersetzen** — mit Fallback auf Templates bei Rate-Limit/Fehler
2. **Neue `_think_user()` Methode** — analysiert Conversation-History für User-Awareness
3. **User-Profil persistent in Rowboat** — `People/User_Profile.md` im Rowboat Knowledge Graph

## Architektur

```
_think_tick()
├── _think_active()     →  pool.analyze(topic)           # "analyst" Agent (NEU)
├── _think_reflect()    →  pool.reflect(query+knowledge)  # "reflector" Agent (NEU)
├── _think_knowledge()  →  pool.summarize(entry)          # "summarizer" (EXISTIERT)
├── _think_connect()    →  pool.find_connection(a, b)     # "connector" (EXISTIERT)
├── _think_explore()    →  pool.explore(topic)            # "explorer" Agent (NEU)
├── _think_refine()     →  pool.run_background_cycle()    # (wie bisher)
├── _think_synthesize() →  Neuroscience-Module            # (kein Umbau)
└── _think_user()       →  pool.analyze_user(history)     # "user_analyst" Agent (NEU)
                              ↓
                         People/User_Profile.md (Rowboat)
```

## Neue Agents (4 Stück, Pool 6→10)

| Agent | Modell | System-Prompt Fokus | Cooldown | Cap |
|-------|--------|---------------------|----------|-----|
| `reflector` | `google/gemma-3-27b-it:free` | "Warum hat der User das gefragt? Was steckt dahinter?" | 45s | 15/hr |
| `explorer` | `stepfun/step-3.5-flash:free` | "Was wäre spannend zu untersuchen? Kreative Neugier." | 60s | 12/hr |
| `analyst` | `nousresearch/hermes-3-llama-3.1-405b:free` | "Tiefenanalyse: Implikationen, Zusammenhänge, Bedeutung." | 60s | 12/hr |
| `user_analyst` | `openai/gpt-oss-120b:free` | "Analysiere User-Stimmung, Bedürfnisse, Interessen aus Conversation-History." | 120s | 8/hr |

## Existierende Agents umleiten

| Agent | Bisher genutzt von | Jetzt auch von |
|-------|--------------------|--------------------|
| `summarizer` | `_think_refine()` (random) | `_think_knowledge()` (direkt) |
| `connector` | `_think_refine()` (random) | `_think_connect()` (direkt) |

## Think-Methoden Mapping

| Methode | Template heute | LLM-Output morgen | Fallback |
|---------|---------------|-------------------|----------|
| `_think_knowledge()` | `"Worth noting: {fact}..."` | summarizer extrahiert echtes Insight | altes Template |
| `_think_connect()` | `"Interesting parallel: {A} and {B}..."` | connector findet echte Verbindungen | altes Template |
| `_think_reflect()` | `"One underappreciated aspect..."` | reflector analysiert Query+Knowledge Kontext | altes Template |
| `_think_explore()` | `"I wonder about {topic}..."` | explorer generiert kreative Exploration | altes Template |
| `_think_active()` | `"Focusing on '{topic}'..."` | analyst macht echte Tiefenanalyse | altes Template |
| `_think_user()` | *(existiert nicht)* | user_analyst → Stimmung/Bedürfnisse/Interessen | None (kein Fallback) |

## Graceful Degradation

Jede upgraded `_think_*` Methode folgt dem Pattern:
```python
def _think_knowledge(self):
    # Versuch LLM
    if self._micro_agent_pool:
        result = self._micro_agent_pool.summarize(entry)
        if result:
            return ContinuousThought(content=result.refined, category="knowledge", ...)
    # Fallback: altes Template
    return ContinuousThought(content=f"Worth noting: {entry}...", category="knowledge", ...)
```

Ohne API-Key oder bei Rate-Limit → exakt gleiches Verhalten wie vorher.

## User-Awareness: _think_user()

### Input
- `_recent_queries` (letzte 20 User-Fragen)
- `_conversation_history` (letzte 50 Turns)
- `_learned_knowledge` (was die Brain weiß)

### Output
- `ContinuousThought(category="user_insight", ...)`
- Persistent: schreibt nach `C:\Users\User\.rowboat\knowledge\People\User_Profile.md`

### Rowboat User_Profile.md Format
```markdown
# User Profile

## Aktuelle Stimmung
- [2026-02-23 14:30] Neugierig und technisch fokussiert — fragt viel über Architektur-Entscheidungen

## Interessen
- AI/ML Architektur (hoch)
- Neuroscience-inspiriertes Computing (hoch)
- Multi-Agent-Systeme (mittel)
- Voice-First Interfaces (mittel)

## Erkannte Bedürfnisse
- Braucht Feedback-Loop für Designentscheidungen
- Bevorzugt iteratives Vorgehen ("Stück für Stück")
- Schätzt visuelle Bestätigung (Dashboard-Checks)

## Gesprächsmuster
- Wechselt zwischen Deutsch und Englisch
- Bevorzugt kurze, direkte Antworten
- Testet gerne live bevor er weitergeht
```

### Update-Strategie
- `_think_user()` wird ca. alle 2-3 Minuten getriggert (via `_think_tick()`)
- User_Profile.md wird NUR aktualisiert wenn sich etwas ÄNDERT (diff-check)
- Append-only für Stimmungs-History, Replace für Interessen/Bedürfnisse

## Rate-Limiting

Global cap bleibt 60/hr. Neue Agents teilen sich das Budget:
- Alte 6 Agents: ~40 calls/hr
- Neue 4 Agents: ~20 calls/hr
- Nicht jeder Tick geht durch LLM — nur wenn Agent verfügbar (not rate-limited)

## Dateien die geändert werden

| Datei | Änderungen |
|-------|-----------|
| `core/brain_chat.py` | 4 neue Agent-Configs, 4 neue Pool-Methoden, 6 `_think_*` Upgrades, neues `_think_user()` |
| `tests/test_brain_chat_quick.py` | ~25 neue Tests |
| `web/templates/moltbook_dashboard.html` | CSS für `user_insight` Badge |

## Nicht im Scope
- Proaktive Suggestions (kommt später, aufbauend auf User-Profil)
- Rowboat-API-Integration (erstmal nur File-Write)
- Voice/WebSocket Bridges

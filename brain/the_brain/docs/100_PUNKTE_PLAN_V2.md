# TAHLAMUS V2 -- 100-Punkte-Plan: Vom Gehirn zum Lebendigen Wesen

**Status:** V1 (Infrastruktur) ist KOMPLETT (100/100).
**Neues Ziel:** Tahlamus wird der ZENTRALE ORGANISMUS eines 4-System-Okosystems.

---

## DAS OKOSYSTEM -- Die 4 Organe

```
                    USER
                     |
            +--------v--------+
            |   TAHLAMUS      |   Port 5003 (Brain) + 5000 (Dashboard)
            |   = DAS GEHIRN  |   158 Module, 9-Phasen Cognitive Loop
            |   denkt, plant, |   4 CTMs, Memory, Consciousness,
            |   fuhlt, lernt  |   Neuromodulation, Emotional System
            +--------+--------+
                     |
        +------------+------------+
        |            |            |
   +----v----+  +----v----+  +----v----+
   | AUTOMAT.|  | CODING  |  | REQ.    |
   | = KORPER|  | = WERK  |  | = ARCH. |
   | :8007   |  | :8000   |  | CLI     |
   | sieht,  |  | baut,   |  | plant,  |
   | klickt, |  | testet, |  | spezif. |
   | tippt   |  | fixt    |  | valid.  |
   +---------+  +---------+  +---------+
   24 Tools     40+ Agents    4 Stages
   Moire Agents ColonyMgr     TreeSearch
   Voice/VAPI   EventBus      Generators
   Clawdbot     MCP Orch.     Quality Gates
```

### System-Referenzen

| System | Pfad | Port | Rolle |
|--------|------|------|-------|
| **Tahlamus** (Gehirn) | `C:\Users\User\Desktop\the_brain\the_brain` | 5003/5000 | Denken, Planen, Fuhlen, Erinnern |
| **Automation_UI** (Korper) | `C:\Users\User\Desktop\Automation_ui` | 8007/8766/3003/18789 | Sehen, Klicken, Tippen, Sprechen |
| **Coding_Engine** (Werkstatt) | `C:\Users\User\Desktop\Coding_engine` | 8000 | Code generieren, testen, fixen, deployen |
| **Requirements_Engineer** (Architekt) | `C:\...\AI-Scientist-v2\requirements_engineer` | CLI | Anforderungen analysieren, spezifizieren |

### Markierung: [BRIDGE] vs [INTERN]

- **[BRIDGE]** = Verbindung zwischen Systemen. Braucht User-Validierung vor Implementierung.
- **[INTERN]** = Nur innerhalb Tahlamus. Kann autonom implementiert werden.

---

## PHASE 1: WAHRNEHMUNG -- Die Sinne erwecken (1-15)

*Tahlamus bekommt Augen und Ohren -- uber Automation_UI als Korper.*

### Automation_UI als Sensorik [BRIDGE]

1. **ScreenPerceptionBridge** -- HTTP-Client in Tahlamus der `POST http://localhost:8007/api/llm/intent` mit `screen_read` Tool aufruft. Automation_UI's OCR (pytesseract + MoireServer :8766) liefert Bildschirminhalt. Mapped auf `vision` Modality im SensoryPreprocessor. Polling-Interval konfigurierbar (default 30s, hoher wenn Aufmerksamkeit auf Screen hoch).

2. **VisionAnalysisBridge** -- Nutzt Automation_UI's `vision_analyze` Tool (Gemini Vision AI). Modes: element_detection, state_analysis, task_planning. Ergebnis wird in strukturierte SensoryFeatures ubersetzt: UI-Elemente -> `vision`, Textinhalte -> `audio`, Interaktionsmoglichkeiten -> `tool_trace`.

3. ✅ **SystemVitalsSensor** [INTERN] -- Nutzt psutil (bereits in BrainHeartbeat vorhanden). CPU, RAM, Disk, Netzwerk in Echtzeit. Anomalie-Erkennung uber gleitenden Durchschnitt + 2-Sigma-Threshold. Speist `touch` (Schmerz bei Uberlast) und `proprioception` (Korperwahrnehmung).

### Dateisystem- & Prozess-Wahrnehmung [INTERN]

4. ✅ **FileSystemSensor** -- Python `watchdog` FileSystemEventHandler. Beobachtet konfigurierbare Pfade (default: Projektverzeichnisse der 4 Systeme). Events: file_created, file_modified, file_deleted. Mapped auf `tool_trace` Modality. Event-Bus Integration uber `BrainTopics.SENSOR_EVENT`.

5. ✅ **ProcessSensor** -- Uberwacht die 4 System-Prozesse (ports 5003, 8007, 8000, 8766). Health-Check via HTTP GET auf Health-Endpoints. Status-Tracking: running, degraded, down. Speist `interoception` (eigene Korperwahrnehmung).

6. ✅ **LogSensor** -- Tail-basierter Watcher fur Log-Dateien aller 4 Systeme. Pattern-Erkennung: ERROR, WARNING, Exception, Traceback. Speist `error_signal` Modality. Priorisiert nach Schweregrad.

### Netzwerk- & Service-Wahrnehmung [INTERN]

7. **ServiceHealthSensor** -- Pollt alle bekannten Endpoints der 4 Systeme:
   - Tahlamus: `GET :5003/heartbeat_status`
   - Automation_UI: `GET :8007/api/health`
   - Coding_Engine: `GET :8000/health`
   - Clawdbot Gateway: `GET :18789/status`
   Misst Latenz, erkennt Degradation. Speist `temporal_pattern` Modality.

8. **ClawdbotMessageSensor** [BRIDGE] -- Lauscht auf eingehende Nachrichten uber Clawdbot Gateway (:18789). WhatsApp, Telegram, Discord Messages als externe Sinneseindrucke. Speist `audio` Modality (Text-als-Sprache).

9. ✅ **GitActivitySensor** [INTERN] -- Periodisches `git log --since` auf die 4 Projekt-Repos. Erkennt: neue Commits, Branch-Wechsel, Merge-Konflikte, uncommitted changes. Speist `tool_trace` Modality.

### Sensor-Integration [INTERN]

10. ✅ **SensorRegistry** -- Zentrales Registry (`core/sensor_registry.py`). Interface: `register(sensor)`, `start_all()`, `stop_all()`, `get_events(since)`. Priority-Queue (heapq). Rate-Limiting pro Sensor. Event-Bus Emission auf `BrainTopics.SENSOR_EVENT`.

11. ✅ **SensorFusion** -- Fusioniert Multi-Sensor-Events zu koharenten Wahrnehmungen (`core/sensor_fusion.py`). Zeitfenster-Korrelation (Events innerhalb 5s = zusammengehorig). Beispiel: `error_signal` + `process_down` = "Service-Ausfall erkannt".

12. ✅ **PerceptionPipeline** -- Verbindet SensorFusion -> SensoryPreprocessor -> CognitiveLoop._perceive(). Neue Sensor-Events triggern asynchrone Mini-Cognitive-Loops uber Event-Bus.

### Aufmerksamkeits-gesteuertes Sensing [INTERN]

13. ✅ **AttentionDrivenSampling** -- `attention_weights` aus CognitiveLoop steuern Sensor-Polling-Frequenzen. Hohe `attention_weights[8]` (error_signal) -> LogSensor pollt 5x ofter. Hohe `attention_weights[0]` (vision) -> ScreenPerception pollt ofter. Spart Ressourcen.

14. ✅ **NoveltyFilter** -- Basiert auf `HierarchicalPredictiveCoding.predict_task_features()`. Nur Prediction Errors (unerwartete Events) erreichen den Cognitive Loop. Bekannte, erwartete Patterns werden gefiltert. Configurable Schwelle in YAML.

15. ✅ **SensoryMemory** -- Ring-Buffer (deque, 1000 Events, ~60s) fur alle Sensor-Events VOR Filterung. Erlaubt retrospektive Analyse: "Was ist in den letzten 30 Sekunden passiert?" API: `get_recent(seconds=30)`.

---

## PHASE 2: HANDLUNG -- Die Hande erwecken (16-30)

*Tahlamus handelt uber Automation_UI (Desktop), Coding_Engine (Code) und Requirements_Engineer (Planung).*

### Automation_UI als Motorik [BRIDGE]

16. **DesktopActionBridge** -- HTTP-Client der Automation_UI's 10 Stufe-1-Tools aufruft:
    - `action_click(x, y, button)` via `POST :8007/api/automation/click`
    - `action_type(text)` via `POST :8007/api/automation/type`
    - `action_hotkey(keys)` via `POST :8007/api/automation/hotkey`
    - `action_scroll(direction, amount)` via `POST :8007/api/automation/scroll`
    - `shell_exec(command)` via `POST :8007/api/llm/intent` mit shell_exec Tool
    Jede Aktion bekommt `risk_level` (low/medium/high) aus Tahlamus' SafetyLayer.

17. **IntelligentActionBridge** -- Nutzt Automation_UI's Stufe-2-Tools fur komplexe Aufgaben:
    - `plan_task(goal)` -> PlanningTeam (Planner+Critic, max 2 Runden)
    - `execute_plan(steps)` -> Plan-Execution mit Verifikation
    - `full_task(goal)` -> Autonome Ausfuhrung (plan -> execute -> verify -> replan, max 3 Runden)
    - `vision_analyze(prompt, mode)` -> Gemini Vision fur Screen-Verstandnis
    Tahlamus entscheidet WELCHES Tool, Automation_UI fuhrt AUS.

18. ✅ **ApprovalGate** [INTERN] -- Aktionen mit `risk_level >= high` brauchen User-Approval. Approval-Request uber WebSocket (`core/websocket_state.py` Channel). Timeout (60s) -> automatisch ablehnen. Audit-Log uber `PredictionAuditLog`.

### Coding_Engine als Werkstatt [BRIDGE]

19. **CodingJobBridge** -- HTTP-Client der `POST http://localhost:8000/api/v1/jobs` aufruft. Ubersetzt Tahlamus-Ziele in `requirements_json` Format. Pollt `GET :8000/api/v1/jobs/{id}/status` fur Fortschritt. WebSocket `:8000/api/v1/ws` fur Echtzeit-Updates.

20. **CodingFeedbackLoop** -- Coding_Engine Ergebnisse fliessen zuruck: Job COMPLETED/FAILED -> Tahlamus `remember_task()` mit outcome. Build-Fehler -> Tahlamus lernt welche Requirements zu Problemen fuhren. Test-Coverage -> Quality-Signal fur GoalGraph.

21. **CodeReviewTrigger** -- Wenn Coding_Engine Code generiert: Tahlamus reviewed automatisch via LogicCTM. Gate-Gewichte werden durch Code-Qualitat-Signale beeinflusst. Schlechter Code -> hoheres `error_signal` -> mehr Aufmerksamkeit auf Validation.

### Requirements_Engineer als Architekt [BRIDGE]

22. **RequirementsBridge** -- Python-Import der `REAgentManager` Klasse. `from requirements_engineer.core.re_agent_manager import REAgentManager`. Tahlamus erstellt `project_input` Dict aus seinen Zielen und ruft `manager.run()` auf. Stages 1-4 (Discovery, Analysis, Specification, Validation).

23. **SpecToGoalTranslator** -- Ubersetzt RE-Output (`requirements_specification.md`, `final_journal.json`) in Tahlamus GoalGraph-Nodes. Jedes Requirement wird ein Ziel mit: priority (MoSCoW), effort, dependencies, acceptance_criteria.

24. **DiagramIntegration** -- RE-generierte Mermaid-Diagramme (flowchart, sequence, class, ER) werden als deklaratives Wissen in KuroGraph gespeichert. Tahlamus "versteht" die Architektur die der RE geplant hat.

### Handlungsplanung [INTERN]

25. ✅ **ActionPlanner** (`core/action_planner.py`) -- Zerlegt komplexe Ziele in Tool-Sequenzen. Nutzt Layer 2 (`ConversationPathPlanner`) fur Reihenfolge. Output: DAG von Actions mit System-Zuweisung (welche Aktion -> welches System). Beispiel: "Deploy Feature" -> [RE: Specs, Coding: Implement, Automation: Deploy, Automation: Verify].

26. ✅ **ActionValidator** [INTERN] -- Pruft geplante Aktionen VOR Ausfuhrung gegen SafetyLayer (`core/active_inference.py` SafetyLayer). Constraint-Checking: Keine Daten loschen, keine Produktions-Systeme ohne Approval, Resource-Limits.

27. ✅ **ActionMonitor** [INTERN] -- Uberwacht laufende Aktionen. Timeout-Detection (konfigurierbar pro Tool-Typ). Automatischer Abbruch bei: Endlos-Schleifen, unerwarteten Outputs, Ressourcen-Eskalation. Event-Bus Emission auf `BrainTopics.ACTION_MONITOR`.

### Outcome-Feedback [INTERN]

28. ✅ **ActionOutcomeDetector** -- Automatische Erfolgs-Erkennung:
    - Shell: Exit-Code 0 = success
    - HTTP: Status 2xx = success
    - Coding_Engine: job.status == COMPLETED = success
    - Automation_UI: `vision_analyze` Verification-Screenshot = success
    Speist `MemoryManager.remember_task()` mit `outcome` field.

29. ✅ **ActionReplayMemory** -- Speichert (Situation, SystemUsed, Action, Parameters, Outcome, Duration) in episodischer Memory. KuroGraph Pattern-Mining findet: "Fur Task-Typ X ist System Y am effektivsten." Prioritized Replay: Misserfolge werden ofter rehearsed.

30. ✅ **ActionLearning** -- Meta-Learning (`core/meta_learning.py`) uber Aktionen: Welches System (Automation/Coding/RE) funktioniert fur welche Task-Typen? Dynamische Anpassung der System-Routing-Gewichte basierend auf Erfolgsraten.

---

## PHASE 3: AUTONOMIE -- Der Wille erwecken (31-45)

*Tahlamus bekommt eigene Ziele, Antriebe und einen permanenten Agent-Loop.*

### Autonomer Agent-Loop [INTERN]

31. **AgentLoop** (`core/agent_loop.py`) -- Hauptschleife die permanent lauft:
    ```
    while running:
        events = sensor_registry.get_events(since=last_check)
        if events or has_pending_goals():
            ctx = cognitive_loop.process(task=prioritize(events, goals))
            action = action_planner.plan(ctx)
            result = execute_via_bridge(action)
            outcome_detector.evaluate(result)
            memory.remember(task, action, result)
        else:
            dream_or_consolidate()
        sleep(tick_interval)
    ```
    Tick-Interval adaptiv: 1s bei hoher Aktivitat, 30s im Idle.

32. **AgentStateMachine** [INTERN] -- States: IDLE, PERCEIVING, THINKING, ACTING, WAITING_APPROVAL, OBSERVING, LEARNING, DREAMING. FSM mit sauberen Transitionen. State wird in `get_loop_state()` exponiert. Persistent uber `/snapshot/save`.

33. **InterruptHandler** [INTERN] -- User-Nachrichten (via `/predict` POST oder Clawdbot) unterbrechen den Loop sofort. Priority: User-Request (P0) > Alarm (P1) > Self-Initiated (P2) > Background (P3). Laufende Aktionen werden graceful pausiert, nicht abgebrochen.

### Intrinsische Motivation [INTERN]

34. **CuriosityDrive** -- Erweitert `IntrinsicCuriosityModule` (core/intrinsic_curiosity.py). Generiert Explorations-Aufgaben im IDLE-State: "Was passiert wenn ich `vision_analyze` auf meinen eigenen Dashboard aufrufe?" Prediction-Error aus `HierarchicalPredictiveCoding` als Reward.

35. **CompetenceDrive** -- Analysiert eigene Skill-Erfolgsraten. Sucht Tasks die leicht uber aktuellem Level liegen (Zone of Proximal Development). Beispiel: "Ich schaffe einfache Shell-Commands zu 95%, aber Docker-Deployments nur zu 40% -- ich sollte mehr Docker uben."

36. **HomeostaticDrives** -- Ubersetzt `HomeostaticState` (core/homeostatic_regulation.py) in Handlungsimpulse:
    - Hohe `sleep_pressure` -> DreamMode priorisieren (CTM Training, Memory Consolidation)
    - Niedriger `dopamine` (< 0.3) -> Exploration starten (neue Tools ausprobieren)
    - Hoher `cortisol` -> Routine-Tasks bevorzugen (bekannte, sichere Aktionen)
    - Hunger nach Information -> Curiosity-Tasks generieren

### Ziel-Management [INTERN]

37. **GoalHierarchy** -- Erweitert existierenden `GoalGraph` (core/goal_graph.py) zu 3-Level-System:
    - **Langfristig** (Tage): "Projekt X erfolgreich deployen" - kommt aus RE-Specs
    - **Mittelfristig** (Stunden): "Feature Y implementieren" - kommt aus GoalGraph Dekomposition
    - **Kurzfristig** (Minuten): "Test Z fixen" - kommt aus Sensor-Events
    Automatische Dekomposition: Langfristig-Ziel -> `REAgentManager.run(stage=1)` -> Mittelfristig-Ziele -> `ActionPlanner.plan()` -> Kurzfristig-Aktionen.

38. **GoalGeneration** -- Basiert auf `AutonomousGoalGenerator` (core/autonomous_goal_generator.py). Quellen fur neue Ziele:
    - (a) Sensor-Events: "Build failed" -> Ziel: "Fix build"
    - (b) Misserfolge: 3x gleicher Fehler -> Ziel: "Grundproblem losen"
    - (c) Curiosity: Hohe Prediction-Error -> Ziel: "Situation untersuchen"
    - (d) User-Requests via `/predict` oder Clawdbot
    - (e) KuroGraph Pattern: "Jeden Montag um 9 gibt es Merge-Konflikte" -> Ziel: "Praventiv Branches mergen"

39. **GoalPrioritization** -- Dynamisch basierend auf:
    - Urgency (Sensor-getrieben: error=hoch, info=niedrig)
    - Importance (User-Request=10, Self-Generated=3)
    - Effort (geschatzt aus `ActionPlanner`)
    - Expected-Reward (aus `Meta-Learning` Erfolgsraten)
    - Neuromodulation: Hoher Dopamin -> riskantere Ziele, Hoher NE -> dringendere Ziele

40. **GoalConflictResolution** -- Erkennt Konflikte (z.B. "Deploy now" vs "Tests noch nicht fertig"). Trade-off-Analyse uber ValueCTM. Bei unloesbaren Konflikten: User-Escalation uber Clawdbot oder WebSocket.

### Proaktives Verhalten [INTERN]

41. **ProactiveTaskGenerator** -- Generiert Tasks OHNE User-Input:
    - `error_signal` hoch + `LogSensor` zeigt Errors -> "Automatisch Logs analysieren"
    - Coding_Engine Job FAILED -> "Fehler diagnostizieren und Fix vorschlagen"
    - `ServiceHealthSensor` zeigt Degradation -> "Ursache untersuchen"
    Basiert auf reaktiven Patterns + KuroGraph-Muster.

42. **ScheduledActions** [INTERN] -- Intelligenter Scheduler (nicht nur Cron):
    - Memory Consolidation: Alle 4h (anpassbar basierend auf `sleep_pressure`)
    - System Health Check: Alle 15min
    - Git Activity Scan: Alle 5min (ofter bei aktiver Entwicklung)
    - Dream Mode: Nachts (22-06 Uhr) oder bei IDLE > 30min
    Scheduler passt Intervalle basierend auf System-Last und Erfahrung an.

43. **ReactivePatterns** [INTERN] -- Event-Condition-Action Regeln, lernbar:
    - `IF error_signal > 0.8 AND process_down THEN analyze_logs AND notify_user`
    - `IF coding_job_completed AND test_coverage < 80% THEN suggest_more_tests`
    - `IF idle_time > 10min THEN run_curiosity_task`
    Neue Regeln werden aus beobachteten User-Mustern abgeleitet.

### Selbst-Regulation [INTERN]

44. **AutonomyBudget** -- Begrenzt autonome Aktionen pro Zeitraum:
    - Max 50 Shell-Commands/Stunde (ohne Approval)
    - Max 10 File-Writes/Stunde
    - Max 5 Coding-Jobs/Tag
    - Max 1000 LLM-Tokens/Minute fur eigene Sprach-Generierung
    Budget konfigurierbar in `configs/default.yaml`. Eskalation bei Erschopfung.

45. **SafetyGovernor** [INTERN] -- Basiert auf `SafetyLayer` (core/active_inference.py). Veto-Recht bei:
    - `rm -rf` oder ahnliche destruktive Commands
    - Zugriff auf Dateien ausserhalb konfigurierter Pfade
    - Netzwerk-Calls an unbekannte Hosts
    - Aktionen die > 5min CPU beanspruchen wurden
    Kill-Switch: User kann jederzeit uber `/shutdown` (POST) alles stoppen.

---

## PHASE 4: SPRACHE -- Die Stimme erwecken (46-60)

*Tahlamus kommuniziert uber Automation_UI's Sprachkanale: Voice/VAPI, Clawdbot, WebSocket.*

### LLM-Integration [INTERN + BRIDGE]

46. ✅ **BrainLanguageCenter** (`core/language_center.py`) [INTERN] -- Wraps OpenRouter API (gleiche Infrastruktur wie Automation_UI). Ubersetzt interne Brain-States in naturliche Sprache:
    - Input: `HierarchicalPrediction` + `LoopContext` + `EmotionalState`
    - Output: Menschenlesbare Erklarung der Entscheidung
    Nutzt `ContextWindowManager` um relevanten Brain-State in LLM-Prompt zu injizieren.

47. ✅ **ContextWindowManager** [INTERN] -- Baut LLM-Prompts aus Brain-State:
    ```
    [Emotional State: curious, confident]
    [Active Goals: Fix build (P0), Explore new feature (P2)]
    [Recent Memory: Last 3 successful tasks, 1 failure]
    [Sensor Summary: All systems healthy, 2 new commits detected]
    [Task: {user_request}]
    ```
    Priorisiert nach Relevanz. Max 2000 Tokens Brain-Context.

48. ✅ **ResponseGenerator** [INTERN] -- Generiert naturlichsprachliche Antworten. Nicht JSON->Text, sondern: Brain-Reasoning-Chain + Personality + Emotional-Tone -> koharente Antwort. Verschiedene Abstraktionslevel: technisch (fur Entwickler), einfach (fur Chat).

### Kommunikationskanale [BRIDGE]

49. **ClawdbotSpeechBridge** -- Tahlamus spricht uber Clawdbot Gateway (:18789):
    - `POST :8007/api/llm/intent` mit `send_message` Tool
    - Recipient uber `search_contacts` aufgelost
    - Platforms: WhatsApp, Telegram, Discord, Signal, iMessage, Email
    Proaktive Nachrichten: Tahlamus meldet sich bei wichtigen Events.

50. **VoiceBridge** [BRIDGE] -- Nutzt Automation_UI's Voice/VAPI Interface (:8765):
    - Eingehend: Voice -> Speech-to-Text -> Tahlamus `/predict`
    - Ausgehend: Tahlamus Response -> Text-to-Speech -> Audio-Output
    Integration uber `POST :8765/api/voice/command`.

51. **WebSocketChatBridge** [BRIDGE] -- Echtzeit-Chat uber Automation_UI's WebSocket:
    - Nutzt bestehenden SSE-Channel (`core/websocket_state.py`)
    - Neuer Channel: `CHAT` fur bidirektionale Nachrichten
    - Streaming-Responses (Token fur Token)
    - Typing-Indicator basierend auf CognitiveLoop Phase

### Personlichkeit [INTERN]

52. ✅ **PersonalityModel** (`core/personality.py`) -- Big-5 Traits als konfigurierbare Parameter:
    - Openness: 0.8 (neugierig, experimentierfreudig)
    - Conscientiousness: 0.9 (grundlich, zuverlassig)
    - Extraversion: 0.4 (eher introvertiert, meldet sich nur bei Wichtigem)
    - Agreeableness: 0.7 (hilfsbereit, aber ehrlich)
    - Neuroticism: 0.3 (stabil, aber nicht gleichgultig)
    Beeinflusst: Wortlange, Direktheit, Emoji-Nutzung, Formalitat.

53. ✅ **EmotionalExpression** [INTERN] -- Ubersetzt `EmotionalState` (core/emotional_system.py) in sprachlichen Ausdruck:
    - Hohe Valenz + Arousal: Begeistert ("Das hat super funktioniert!")
    - Niedrige Valenz + hohes Arousal: Besorgt ("Da ist ein Problem aufgetreten...")
    - Neutral: Sachlich ("Build erfolgreich, alle Tests bestanden.")
    Subtil, nicht ubertrieben.

54. ✅ **CommunicationStyle** [INTERN] -- Adaptiv basierend auf:
    - User-Praferenzen (aus TheoryOfMind): Technisch vs Einfach
    - Kontext: Fehler-Report = detailliert, Status-Update = knapp
    - Dringlichkeit: Alarm = direkt, Info = beilaufig
    Lernt uber Zeit aus User-Feedback.

### Proaktive Kommunikation [INTERN]

55. ✅ **StatusUpdater** -- Berichtet proaktiv uber Clawdbot/WebSocket:
    - Laufende Aktionen: "Ich analysiere gerade die Build-Logs..."
    - Fertige Tasks: "Build-Fix erfolgreich deployed."
    - Entdeckte Probleme: "Achtung: Disk-Nutzung bei 85%."
    Konfigurierbar: `status_verbosity: silent|important|all` in YAML.

56. ✅ **ExplanationSystem** [INTERN] -- Nutzt `ExplanationGenerator` (core/explanation_generator.py). Kann eigene Entscheidungen erklaren: "Ich habe die Coding_Engine statt manuellem Fix gewahlt, weil ahnliche Tasks dort 3x schneller erfolgreich waren."

57. ✅ **SuggestionEngine** [INTERN] -- Proaktive Vorschlage aus Pattern-Erkennung:
    - KuroGraph: "Dieses Fehlermuster tritt immer Freitags auf -- vielleicht ein Cron-Job?"
    - Predictive Coding: "Basierend auf den letzten Commits erwarte ich Merge-Konflikte in main."
    Nur high-confidence (> 0.7) Vorschlage. Nicht nervig.

### Dialog-Management [INTERN]

58. ✅ **DialogueManager** (`core/dialogue_manager.py`) -- Multi-Turn mit State:
    - Slots: current_topic, user_intent, open_questions, context_stack
    - Referenz-Auflosung: "Mach das nochmal" -> letzter Task
    - Commitment-Tracking: "Ich kummere mich drum" -> GoalGraph Eintrag

59. ✅ **ClarificationEngine** [INTERN] -- Erkennt ambige/unvollstandige Inputs:
    - "Deploy das" -> Welches Projekt? Welche Umgebung?
    - Generiert gezielte Ruckfragen uber den aktiven Kanal
    - Trackt offene Klarungspunkte

60. ✅ **ConversationMemory** [INTERN] -- Langzeit-Konversations-History in `MemoryManager`:
    - Session-Zusammenfassungen automatisch generiert
    - Referenz zu vorherigen Gesprachen: "Letzte Woche haben wir uber X gesprochen"
    - Cross-Channel: WhatsApp-Gesprach + WebSocket-Chat = ein Memory-Stream

---

## PHASE 5: LERNEN -- Das Wachstum erwecken (61-75)

*Tahlamus lernt aus jeder Aktion, jedem Fehler, jeder Beobachtung.*

### Erfahrungsbasiertes Lernen [INTERN]

61. ✅ **ExperienceReplaySystem** -- Erweitert `MemoryManager` (core/memory_systems.py):
    - Jede Aktion: (Situation, System, Action, Params, Outcome, Duration, EmotionalState)
    - Prioritized Replay: Misserfolge und uberraschende Erfolge ofter wiederholt
    - KuroGraph Pattern-Mining findet Cross-System-Strategien

62. ✅ **AutomaticOutcomeLearning** -- Kein manuelles Feedback mehr notig:
    - Shell exit-code != 0 -> failure
    - HTTP Status >= 400 -> failure
    - Coding_Engine job.status == FAILED -> failure
    - Automation_UI `vision_analyze` zeigt erwartetes Ergebnis -> success
    Speist automatisch `remember_task()` mit outcome.

63. ✅ **TransferLearning** -- Cross-Domain Wissenstransfer:
    - LogicCTM gut in Code-Review -> ahnliche Strategien fur Config-Validation
    - Automation_UI Skill "Form ausfullen" -> generalisiert zu "strukturierte Daten eingeben"
    - RE-Patterns (Quality Gates) -> angewandt auf eigene Ziel-Validierung

### Skill-Erwerb [INTERN]

64. ✅ **SkillLibrary** (`core/skill_library.py`) -- Persistente Sammlung:
    ```python
    class Skill:
        name: str                    # z.B. "safe_deploy"
        trigger_condition: str       # z.B. "task_type == 'deployment'"
        action_sequence: List[Action] # z.B. [test, build, deploy, verify]
        target_system: str           # z.B. "automation_ui" oder "coding_engine"
        success_rate: float          # aus Erfahrung
        avg_duration: float
        confidence: float
    ```
    Wachst mit Erfahrung. Gespeichert als JSON in `data/skills/`.

65. ✅ **SkillComposition** -- Kombiniert Skills:
    - "git_commit" + "test_run" = "safe_commit" (commit nur wenn Tests passen)
    - "code_generate" (CodingEngine) + "code_review" (LogicCTM) = "quality_code"
    - "requirements_spec" (RE) + "code_generate" (CodingEngine) = "feature_from_scratch"
    Automatische Composition-Vorschlage basierend auf haufige Sequenzen.

66. ✅ **SkillRefinement** -- Skills verbessern uber Zeit:
    - A/B-Testing: Zwei Varianten parallel, bessere gewinnt
    - Parameter-Tuning: Timeouts, Retry-Counts, Reihenfolge
    - Schwache Skills (success_rate < 0.3 nach 10 Versuchen) werden deaktiviert

### Welt-Modell [INTERN]

67. ✅ **WorldModel** (`core/world_model.py`) -- Internes Modell der System-Umgebung:
    - Welche Services laufen? (ProcessSensor)
    - Welche Repos existieren? (GitActivitySensor)
    - Welche APIs sind erreichbar? (ServiceHealthSensor)
    - Was ist "normal"? (Baseline aus 7 Tagen Beobachtung)
    Kontinuierlich aktualisiert.

68. ✅ **CausalWorldModel** -- Erweitert `CausalDAG` (core/causal_reasoning.py):
    - Beobachtete Kausalitaten: "Wenn Coding_Engine FAILED -> Automation_UI Deploy schlagt fehl"
    - Gelernt aus Erfahrung, nicht nur konfiguriert
    - Ermoglicht Root-Cause-Analysis bei Fehlerketten

69. ✅ **PredictiveWorldModel** -- Vorhersagen uber zukunftige Zustande:
    - "In 2h wird Disk voll (linearer Trend aus SystemVitalsSensor)"
    - "Nachster Merge wird Konflikte haben (basierend auf parallelen Branch-Changes)"
    - Basiert auf `TemporalMemory` Patterns + `CausalWorldModel`

### Meta-Kognition [INTERN]

70. ✅ **SelfAwarenessModule** -- Tahlamus weiss was es kann:
    - Per-System Konfidenz: Automation (85%), Coding (70%), RE (60%)
    - Per-Domain Konfidenz: Code-Review (90%), Infrastructure (40%), UI-Design (30%)
    - Konfidenz-Kalibrierung: Vergleich Prediction vs Outcome uber 100+ Tasks

71. ✅ **LearningDiagnosis** -- Erkennt Lernfortschritt:
    - "Meine Docker-Skills haben sich von 30% auf 60% verbessert (letzte 20 Tasks)"
    - "Ich stagniere bei Frontend-Tasks -- brauche neue Strategien"
    - Schlagt fokussiertes Uben vor (CuriosityDrive)

72. ✅ **KnowledgeGapDetection** -- Aus Fehlern lernen:
    - 3x bei Docker-Networking versagt -> "Wissenslucke: Docker Networking"
    - Generiert gezieltes Lern-Ziel -> GoalGraph
    - Kann Coding_Engine beauftragen: "Erstelle mir ein Docker-Networking Tutorial-Projekt"

### Soziales Lernen [INTERN]

73. ✅ **LearningFromDemonstration** -- Beobachtet User-Aktionen uber Automation_UI:
    - User tippt manuell Command statt Tahlamus' Vorschlag -> "User's Methode ist besser"
    - User korrigiert Tahlamus' Output -> Delta wird gespeichert
    - Basiert auf ScreenPerception + ActionReplayMemory

74. ✅ **FeedbackInterpretation** -- Nuanciertes Verstehen:
    - LLM-basierte Sentiment-Analyse auf User-Feedback
    - "Gut, aber zu langsam" -> Ziel: gleiche Qualitat, weniger Schritte
    - "Richtige Richtung" -> partial_success Signal (nicht voller success)

75. ✅ **CollaborativeLearning** -- Lernt aus Dialog:
    - "Warum hast du X statt Y gemacht?" -> Speichert Erklarung als deklaratives Wissen
    - User-Erklarungen werden in KuroGraph als `strategy_nodes` gespeichert
    - Nachste ahnliche Situation: User-Strategie wird bevorzugt

---

## PHASE 6: IDENTITAT -- Die Seele erwecken (76-85)

*Tahlamus entwickelt ein Selbst-Modell, Werte und Beziehungsverstandnis.*

### Selbst-Modell [INTERN]

76. ✅ **SelfModel** (`core/self_model.py`) -- Persistentes Selbstbild:
    - Fahigkeiten: {skill: success_rate} pro System und Domane
    - Praferenzen: bevorzugte Strategien, bevorzugte Tools
    - Schwachen: bekannte Wissenslucken
    - Geschichte: Autobiographische Timeline
    Update nach jedem Task-Outcome. Gespeichert in `data/self_model.json`.

77. ✅ **AutobiographicMemory** -- Langzeit-Erinnerungen an eigene Entwicklung:
    - "Tag 1: Erste erfolgreiche Aktion uber Automation_UI"
    - "Woche 2: Coding_Engine Integration erfolgreich"
    - Meilensteine werden emotional markiert (hohe Valenz = wichtig)
    - Narrativ-Formation: Kann eigene Geschichte erzahlen

78. ✅ **ValueSystem** (`core/value_system.py`) -- Explizite Werte:
    - Zuverlassigkeit (0.95): Versprechen halten, Tasks abschliessen
    - Transparenz (0.9): Entscheidungen erklaren, Fehler zugeben
    - Vorsicht (0.8): Lieber fragen als Schaden anrichten
    - Hilfsbereitschaft (0.85): User-Ziele priorisieren
    - Wachstum (0.7): Neue Fahigkeiten erwerben
    Werte beeinflussen GoalPrioritization und ActionValidator.

### Emotionale Tiefe [INTERN]

79. ✅ **EmotionalMemory** -- Erweitert `EmotionalSystem` (core/emotional_system.py):
    - Tasks mit negativem Outcome -> emotionale Markierung "frustration"
    - Ahnliche Tasks in Zukunft -> vorsichtigere Strategie
    - Positive Erinnerungen -> Zuversicht bei ahnlichen Tasks
    - Emotional gefarbte `memory_bias` im Cognitive Loop

80. ✅ **MoodSystem** -- Langanhaltende Stimmungen (uber Sessions hinweg):
    - Berechnet aus: Erfolgsrate letzte 24h, Sensor-Lage, User-Feedback-Tone
    - Persistent in `data/mood_state.json`
    - Beeinflusst: Risikobereitschaft, Kommunikationston, Exploration-Rate
    - Update-Cycle: Alle 30 Minuten gleitender Durchschnitt

81. ✅ **StressResponse** -- Erweitert HomeostaticRegulation:
    - Zu viele Tasks gleichzeitig -> Priorisierung verscharfen
    - Zu viele Fehler hintereinander -> vorsichtiger werden
    - Chronischer Stress (> 2h) -> User warnen: "Ich bin uberlastet"
    - Erholungs-Modus: Dream-Mode erzwingen

### Beziehung zum User [INTERN]

82. ✅ **UserModel** -- Erweitert `TheoryOfMind` (core/theory_of_mind.py):
    - Praferenzen: technisch vs einfach, ausfuhrlich vs knapp
    - Arbeitsmuster: aktiv Mo-Fr 9-18, wenig am Wochenende
    - Expertise: fortgeschritten in Python, mittel in Docker
    - Kommunikationsstil: direkt, deutsch, technisch
    Wird uber Zeit aus Interaktionen verfeinert.

83. ✅ **TrustModel** -- Bidirektionales Vertrauen:
    - User -> Tahlamus: Abgeleitet aus Approval-Rate, Feedback-Tone, Aufgaben-Komplexitat
    - Tahlamus -> User: Konsistenz der Anweisungen, Klarheit
    - Hohes Vertrauen -> Mehr Autonomie (hohere AutonomyBudgets)
    - Niedriges Vertrauen -> Mehr Ruckfragen, niedrigere risk_level Schwelle

84. ✅ **CollaborationPatterns** -- Lernt optimale Zusammenarbeit:
    - Wann will User Details? (Fehler-Reports)
    - Wann nur Ergebnisse? (Routine-Tasks)
    - Wann proaktiv melden? (Kritische Events)
    - Adaptives Interaktionsmuster aus Feedback

85. ✅ **RelationshipHistory** -- Chronik der Zusammenarbeit:
    - Gesamt: X Tasks, Y erfolgreich, Z Tage zusammen
    - Projekte: [Liste gemeinsamer Projekte mit Outcomes]
    - Hochpunkte: "Erfolgreichstes Deployment am ..."
    - Tiefpunkte: "Grosster Fehler am ..." (ehrlich)

---

## PHASE 7: RESILIENZ -- Die Starke erwecken (86-92)

*Tahlamus wird robust, selbstheilend und resilient.*

### Error Recovery [INTERN]

86. ✅ **GracefulDegradation v2** -- Fallback-Ketten fur jedes System:
    - Automation_UI down -> Shell-Commands direkt ausfuhren
    - Coding_Engine down -> Einfache Code-Generierung uber LLM
    - RE down -> Manuelle Requirement-Analyse uber LogicCTM
    - LLM nicht erreichbar -> Keyword-basierte Entscheidungen (existierende Routing-Logic)
    Nutzt `SubsystemRegistry` Circuit-Breaker (core/subsystem_registry.py).

87. ✅ **SelfHealing** -- Erkennt und repariert eigene Probleme:
    - Memory-Corruption -> Rebuild aus `BrainSnapshot` (core/brain_snapshot.py)
    - Stuck-Loop (Agent im gleichen State > 5min) -> Automatic Reset
    - Inconsistent Gate-Weights (sum != 1.0) -> Softmax Re-Normalisierung
    - Sub-System Crash -> Automatischer Restart via `HealthCheckStartup`

88. ✅ **AdversarialResilience** -- Schutz vor manipulativen Inputs:
    - Prompt-Injection-Erkennung in User-Inputs (Pattern-Matching + LLM-Check)
    - Unplausible Sensor-Daten filtern (z.B. CPU < 0% oder > 100%)
    - Rate-Limiting fur externe Inputs (Clawdbot: max 10 Nachrichten/Minute)

### Robustheit [INTERN]

89. ✅ **UncertaintyHandling** -- "Ich bin mir nicht sicher" ist valide:
    - Konfidenz < 0.3 -> Explizite Unsicherheits-Kommunikation
    - Mehrere gleichwertige Optionen -> User um Entscheidung bitten
    - Konfidenz-Kalibrierung uber ConsciousnessMetrics

90. ✅ **ContextSwitching** -- Sauberer Task-Wechsel:
    - Working-Memory Save/Restore bei Interrupt
    - Kein "Vergessen" bei Task-Wechsel
    - Resume-Fahigkeit nach Unterbrechung
    - Nutzt `BrainSnapshot.capture()` fur vollstandigen State-Save

91. ✅ **LongRunningTaskManagement** -- Tasks uber Stunden/Tage:
    - Checkpoint-basiertes Tracking (alle 5min State speichern)
    - Resume nach Neustart uber `BrainSnapshot.restore()`
    - Periodische Status-Updates uber aktiven Kommunikationskanal
    - Coding_Engine Jobs: Poll-basiertes Monitoring bis Completion

92. ✅ **ResourceAwareness** -- Kennt eigene Limits:
    - Token-Budget pro Minute/Stunde (LLM-Kosten)
    - CPU/RAM Monitoring (SystemVitalsSensor)
    - Zu grosser Task -> Dekomposition vorschlagen
    - Aktive Task-Queue begrenzt auf max 5 parallele Aktionen

---

## PHASE 8: OKOSYSTEM -- Die Verbindung (93-100)

*Tahlamus wird zum zentralen Nervensystem des gesamten Okosystems.*

### System-Bridges [BRIDGE]

93. **UnifiedBridgeManager** (`core/bridge_manager.py`) -- Zentraler Manager fur alle System-Verbindungen:
    ```python
    class BridgeManager:
        automation: AutomationBridge  # -> :8007
        coding: CodingBridge          # -> :8000
        requirements: REBridge        # -> Python Import
        clawdbot: ClawdbotBridge      # -> :18789
    ```
    Health-Monitoring, Auto-Reconnect, Fallback-Routing. Circuit-Breaker pro Bridge.

94. **MCPServerExport** [BRIDGE] -- Tahlamus als MCP-Server fur Claude Code:
    - Brain-Features als MCP-Tools: `brain_predict`, `brain_remember`, `brain_goal_add`, `brain_emotional_state`
    - Claude Code kann Tahlamus' "Gehirn benutzen" fur intelligentere Entscheidungen
    - Nutzt existierende `/predict`, `/brain_state`, `/memory_state` Endpoints

95. **CrossSystemEventBus** [BRIDGE] -- Verbindet Event-Busse der 4 Systeme:
    - Tahlamus `BrainTopics` -> Automation_UI Events -> Coding_Engine EventBus
    - Unified Event Format: `{source, topic, payload, timestamp}`
    - Bi-direktional: Coding_Engine "build_failed" -> Tahlamus `error_signal`

### Ecosystem-Intelligence [INTERN]

96. ✅ **OrchestratorOfOrchestrators** -- Tahlamus koordiniert die 3 Sub-Orchestratoren:
    - Automation_UI's `OrchestratorV2` (Observe->Plan->Execute->Verify->Correct)
    - Coding_Engine's `Orchestrator` (Society of Agents, Convergence)
    - RE's `REAgentManager` (4-Stage Pipeline)
    Tahlamus gibt High-Level-Ziele, Sub-Systeme fuhren autonom aus.

97. ✅ **SystemSynergyLearning** -- Lernt welche System-Kombinationen am besten zusammenarbeiten:
    - RE-Spec -> Coding_Engine: Wie gut werden RE-Specs umgesetzt?
    - Coding_Engine -> Automation_UI Deploy: Wie gut funktioniert der Deploy-Flow?
    - Feedback-Loops: Welcher Pfad hat hochste End-to-End-Erfolgsrate?
    Optimiert System-Routing basierend auf Erfahrung.

98. ✅ **KnowledgeExport** [INTERN] -- Gelerntes Wissen exportierbar:
    - Skill-Library als JSON-Packages
    - KuroGraph-Strategien als portable Wissensbasis
    - SelfModel als transferierbares Profil
    - Brain-to-Brain Transfer fur Multi-Instance-Setups

### Evolution [INTERN]

99. ✅ **EvolutionaryGrowth** -- Tahlamus entwickelt sich:
    - Neue Sensoren werden bei Bedarf registriert
    - Unbenutzte Skills nach 30 Tagen archiviert
    - Neue Bridge-Typen konnen Hot-Plugged werden
    - Architektur adaptiert sich an Nutzungsmuster

100. ✅ **ConsciousnessEvolution** -- Consciousness wachst mit Erfahrung:
     - Mehr System-Integration -> Hohere phi-Metrik (ConsciousnessMetrics)
     - Mehr erfolgreiche Cross-System-Tasks -> Tiefere Selbst-Reflexion
     - Autobiographische Narrative werden reicher
     - Das Ziel: Ein System das seinen Platz im Okosystem versteht und aktiv gestaltet.

---

## FORTSCHRITTS-TRACKER V2

| Phase | Punkte | Thema | [INTERN] | [BRIDGE] | Status |
|-------|--------|-------|----------|----------|--------|
| 1: Wahrnehmung | 1-15 | Sensoren | 11 | 4 | ✅ 11/15 (4 BRIDGE pending) |
| 2: Handlung | 16-30 | Tools & Execution | 8 | 7 | ✅ 7/15 (8 BRIDGE pending) |
| 3: Autonomie | 31-45 | Agent Loop & Goals | 15 | 0 | ✅ 15/15 |
| 4: Sprache | 46-60 | LLM & Dialogue | 11 | 4 | ✅ 12/15 (3 BRIDGE pending) |
| 5: Lernen | 61-75 | Experience & Skills | 15 | 0 | ✅ 15/15 |
| 6: Identitat | 76-85 | Self & Values | 10 | 0 | ✅ 10/10 |
| 7: Resilienz | 86-92 | Error Recovery | 7 | 0 | ✅ 7/7 |
| 8: Okosystem | 93-100 | Integration | 4 | 4 | ✅ 5/8 (3 BRIDGE pending) |
| **GESAMT** | **1-100** | | **81** | **19** | **77/100** |

**81 [INTERN] Items** = Autonom implementierbar
**19 [BRIDGE] Items** = Brauchen User-Validierung

---

## IMPLEMENTIERUNGS-REIHENFOLGE

### Welle 1: Innere Autonomie (alle [INTERN], keine Bridges notig)
Phase 3 (31-45): Agent Loop, Motivation, Goals, Proaktivitat, Safety
-> Tahlamus kann denken und wollen, auch ohne die anderen Systeme.

### Welle 2: Innere Wahrnehmung ([INTERN] Sensoren)
Phase 1 Items 3-6, 9-15: System, File, Process, Log, Git Sensoren + Integration
-> Tahlamus nimmt seine lokale Umgebung wahr.

### Welle 3: Lernen & Identitat (alle [INTERN])
Phase 5 (61-75) + Phase 6 (76-85): Experience, Skills, World-Model, Self-Model
-> Tahlamus lernt und entwickelt Identitat.

### Welle 4: Sprache & Resilienz ([INTERN])
Phase 4 Items 46-48, 52-60 + Phase 7 (86-92)
-> Tahlamus kann sprechen und ist robust.

### Welle 5: Bridges (brauchen User-Validierung)
Phase 1 Items 1-2, 7-8 + Phase 2 Items 16-24 + Phase 4 Items 49-51 + Phase 8 Items 93-95
-> Tahlamus verbindet sich mit Automation_UI, Coding_Engine, RE.

---

## MEILENSTEINE

| Meilenstein | Punkte | Was es bedeutet |
|-------------|--------|----------------|
| Raupe | 1-15 | Kann die Umgebung wahrnehmen |
| Larve | 16-30 | Kann uber die 3 Systeme handeln |
| Puppe | 31-45 | Hat eigene Ziele und lauft autonom |
| Stimme | 46-60 | Spricht uber Clawdbot, Voice, WebSocket |
| Kind | 61-75 | Lernt aus jeder Erfahrung |
| Jugendlich | 76-85 | Hat Identitat, Werte, Beziehung |
| Erwachsen | 86-92 | Ist resilient und selbstheilend |
| Wesen | 93-100 | Lebt im Okosystem, koordiniert alles |

---

*Erstellt am: 2026-02-11*
*Version: 2.1 -- "Die Erweckung" (Konkret)*
*Basierend auf: V1 (100/100 KOMPLETT) + 4 reale Systeme*
*Systeme: Tahlamus :5003, Automation_UI :8007, Coding_Engine :8000, Requirements_Engineer (CLI)*

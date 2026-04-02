# Society of Mind - Codegenerierung Übersicht

## Gesamtübersicht

Das **Society of Mind** System ist eine vollautonome Codegenerierungs-Engine, die mehrere spezialisierte KI-Agenten koordiniert, um aus JSON-Anforderungen vollständige Softwareprojekte zu erstellen.

```text
┌─────────────────────────────────────────────────────────────────┐
│                    run_society_hybrid.py                        │
├─────────────────────────────────────────────────────────────────┤
│  Phase 0: Projektgerüst erstellen                               │
│  Phase 1: Architektur-Analyse (Contracts)                       │
│  Phase 2: Code-Generierung (parallel)                           │
│  Phase 3: Society of Mind Loop (Build → Test → Fix → Repeat)    │
│  Phase 4: Vollständigkeitsprüfung (LLM-basiert)                 │
├─────────────────────────────────────────────────────────────────┤
│  ASYNC SERVICES (laufen kontinuierlich parallel zu Phase 3):    │
│  • VNC Sandbox Streaming (--continuous-sandbox)                 │
│  • E2E-Tests (--async-e2e)                                      │
│  • UX-Review (--async-ux)                                       │
│  → Berichten an Event-Stream → Fixes automatisch oder Meldung   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phasen im Detail

### Phase 0: Projekt-Scaffolding

**Trigger:** Skript-Start

**Was passiert:**

- Erstellt Projektstruktur (src/, components/, hooks/, utils/, tests/)
- Generiert Basis-Konfigurationsdateien (package.json, tsconfig.json, vite.config.ts)
- Führt `npm install` aus
- Erstellt initiale App.tsx und main.tsx

**Dateien:**

- `src/scaffolding/project_initializer.py`

---

### Phase 1: Architektur-Analyse (Architect Agent)

**Trigger:** Nach Phase 0

**Was passiert:**

- Parst die Requirements-JSON in einen DAG (Directed Acyclic Graph)
- Gruppiert Requirements nach Domänen (backend, frontend, security, etc.)
- Generiert "Contracts" - TypeScript-Interfaces und API-Endpunkte
- Analysiert Projekttyp (React, Electron, API-Server, etc.)

**Dateien:**

- `src/engine/hybrid_pipeline.py` → `_phase_1_architect()`
- `src/engine/dag_parser.py`
- `src/engine/contract_generator.py`

---

### Phase 2: Code-Generierung (Builder Agent)

**Trigger:** Nach Phase 1

**Was passiert:**

- Sliced Requirements in kleinere Chunks (3 Requirements pro Chunk)
- Generiert Code parallel mit max_concurrent Workers
- Nutzt Claude API/SDK für die Codegenerierung
- Merged generierten Code zurück ins Projekt

**Dateien:**

- `src/engine/hybrid_pipeline.py` → `_phase_2_build()`
- `src/tools/claude_code_tool.py`
- `src/tools/claude_agent_tool.py`

---

### Phase 3: Society of Mind Loop

**Trigger:** Nach Phase 2 (läuft kontinuierlich bis Konvergenz)

Dies ist das **Herzstück** des Systems - ein Event-gesteuerter Loop mit mehreren Agenten.

#### 3.1 EventBus (Nachrichtensystem)

```text
Agenten kommunizieren über Events:
  BUILD_SUCCEEDED → DeploymentTeam startet
  BUILD_FAILED → GeneratorAgent fixt
  TEST_FAILED → ContinuousDebugAgent analysiert
  CODE_FIXED → ValidationTeam testet
  E2E_TEST_FAILED → GeneratorAgent fixt (Async Service)
  UX_ISSUE_FOUND → GeneratorAgent fixt (Async Service)
```

#### 3.2 Aktive Agenten

| Agent | Trigger Event | Aktion |
|-------|--------------|--------|
| **GeneratorAgent** | BUILD_FAILED, CODE_FIX_NEEDED, E2E_TEST_FAILED, UX_ISSUE_FOUND | Fixt Code mit Claude |
| **TesterTeamAgent** | BUILD_SUCCEEDED, E2E_TEST_STARTED | Führt E2E-Tests aus |
| **ValidationTeamAgent** | GENERATION_COMPLETE | Generiert Tests, Debug-Loop |
| **DeploymentTeamAgent** | BUILD_SUCCEEDED | Docker-Sandbox-Verifikation |
| **ContinuousDebugAgent** | SANDBOX_TEST_FAILED | Analysiert Fehler, synct Fixes |
| **UXDesignAgent** | E2E_SCREENSHOT_TAKEN | Prüft UI mit Claude Vision |

#### 3.3 Konvergenz-Kriterien

Der Loop stoppt, wenn ALLE Kriterien erfüllt sind:

- Tests bestehen: 100%
- Type-Errors: 0
- Build erfolgreich
- Sandbox-Test bestanden

**Dateien:**

- `src/mind/orchestrator.py`
- `src/mind/event_bus.py`
- `src/agents/autonomous_base.py`

---

### Phase 4: Vollständigkeitsprüfung (LLM-basiert)

**Trigger:** Nach Konvergenz

**Was passiert:**

- Prüft ob ALLE Requirements implementiert wurden
- **NEU: Multi-Agent Debate Verifizierung** (AutoGen 0.4 Pattern)
- Drei Solver analysieren jedes Requirement aus verschiedenen Perspektiven:
  - **ImplementationSolver**: Prüft Code-Vollständigkeit
  - **TestingSolver**: Prüft Test-Coverage
  - **DeploymentSolver**: Prüft Runtime-Verhalten
- Mehrere Debate-Runden mit Peer-Feedback
- Aggregation via Majority Voting
- Bei FAILED: Zurück zu Phase 3 Loop

```text
┌─────────────────────────────────────────────────────────────┐
│  MULTI-AGENT DEBATE (pro Requirement)                      │
│                                                            │
│     ┌──────────┐   ┌──────────┐   ┌──────────┐           │
│     │ Impl.    │◄─►│ Testing  │◄─►│ Deploy   │           │
│     │ Solver   │   │ Solver   │   │ Solver   │           │
│     └────┬─────┘   └────┬─────┘   └────┬─────┘           │
│          │              │              │                  │
│          └──────────────┼──────────────┘                  │
│                         │                                 │
│                         ▼                                 │
│              ┌──────────────────┐                        │
│              │   AGGREGATOR     │                        │
│              │ (Majority Vote)  │                        │
│              └──────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

**Dateien:**

- `src/mind/completeness_checker.py`
- `src/agents/verification_debate_agent.py`

---

## Async Services (Kontinuierlich)

### E2E-Tests, UX-Review & VNC Streaming

**WICHTIG:** Diese sind KEINE separaten Phasen, sondern laufen **kontinuierlich asynchron** parallel zu Phase 3!

```text
┌────────────────────────────────────────────────────────────────┐
│  ASYNC EVENT STREAM                                            │
│                                                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │ VNC Sandbox  │    │ E2E Tests    │    │ UX Review    │     │
│  │ (Continuous) │    │ (Playwright) │    │ (Vision)     │     │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘     │
│         │                   │                   │              │
│         └───────────────────┴───────────────────┘              │
│                             │                                  │
│                             ▼                                  │
│                    EVENT BUS BERICHTE                          │
│                             │                                  │
│         ┌───────────────────┼───────────────────┐              │
│         │                   │                   │              │
│         ▼                   ▼                   ▼              │
│    SANDBOX_FAILED      E2E_FAILED         UX_ISSUE            │
│         │                   │                   │              │
│         └───────────────────┴───────────────────┘              │
│                             │                                  │
│                             ▼                                  │
│              ZURÜCK ZU PHASE 3 LOOP (Fix → Build → Test)      │
└────────────────────────────────────────────────────────────────┘
```

**Verhalten:**

- Starten SOFORT bei entsprechenden Flags
- Laufen PARALLEL zur Code-Generierung
- Berichten Fehler an den Event-Stream
- GeneratorAgent fixt automatisch ODER meldet Problem
- Folgen dem Phase 3 Loop (Build → Test → Fix → Repeat)

### Async Service Flags

| Flag | Beschreibung | Interval |
|------|-------------|----------|
| `--continuous-sandbox` | VNC Sandbox parallel starten | 30s |
| `--async-e2e` | E2E-Tests kontinuierlich ausführen | 60s |
| `--async-ux` | UX-Review kontinuierlich ausführen | 120s |
| `--async-services` | Alle async Services aktivieren | - |

---

## Sandbox & VNC Streaming

### Continuous Sandbox Mode (`--continuous-sandbox`)

**Trigger:** Sofort bei Start (vor Code-Generierung!)

```text
┌────────────────────────────────────────────────────────────┐
│  1. Container erstellen (sandbox-test Image)               │
│  2. VNC-Services starten (Xvfb + x11vnc + noVNC)          │
│  3. Projekt in Container kopieren                          │
│  4. Dependencies installieren                              │
│  5. Alle 30 Sekunden: Start App → Health Check → Kill     │
└────────────────────────────────────────────────────────────┘

VNC Stream: http://localhost:6080/vnc.html
```

### File Sync während Generierung

```text
GeneratorAgent schreibt Code
       ↓
ContinuousDebugAgent erkennt Änderung
       ↓
docker cp sync_file.tsx container:/app/src/
       ↓
Hot-Reload triggert (pkill node)
       ↓
App startet mit neuem Code
       ↓
VNC zeigt Live-Update
```

---

## Event-Flow Diagramm

```text
START
  │
  ▼
[Phase 0: Scaffold] ─────────────────────────────────────┐
  │                                                       │
  ▼                                                       │
[Phase 1: Architect] ── Contracts generiert              │
  │                                                       │
  ▼                                                       │
[Phase 2: Build] ── Code generiert                       │
  │                                                       │
  ▼                                                       │
╔═══════════════════════════════════════════════════════╗│
║  SOCIETY OF MIND LOOP + ASYNC SERVICES                ║│
║  ┌─────────────────────────────────────────────────┐  ║│
║  │                                                 │  ║│
║  │  BUILD_STARTED ──► npm run build               │  ║│
║  │       │                                         │  ║│
║  │       ▼                                         │  ║│
║  │  ┌─────────┐     ┌──────────────┐              │  ║│
║  │  │ SUCCESS │ ──► │ DeploymentTeam│              │  ║│
║  │  └─────────┘     │ (Sandbox+VNC) │              │  ║│
║  │       │          └──────────────┘              │  ║│
║  │       │                │                        │  ║│
║  │  ┌─────────┐          │                        │  ║│
║  │  │ FAILED  │◄─────────┘                        │  ║│
║  │  └─────────┘     ◄── E2E_FAILED (Async)        │  ║│
║  │       │          ◄── UX_ISSUE_FOUND (Async)    │  ║│
║  │       ▼                                         │  ║│
║  │  GeneratorAgent ── fixt Code                   │  ║│
║  │       │                                         │  ║│
║  │       ▼                                         │  ║│
║  │  CODE_FIXED ──────────────────────────────┐    │  ║│
║  │       │                                    │    │  ║│
║  │       ▼                                    ▼    │  ║│
║  │  ValidationTeam              ContinuousDebug   │  ║│
║  │  (Tests generieren)          (File Sync)       │  ║│
║  │       │                                         │  ║│
║  │       └────────────► ZURÜCK ZU BUILD ──────────┘  ║│
║  │                                                 │  ║│
║  └─────────────────────────────────────────────────┘  ║│
║                         │                             ║│
║                         ▼                             ║│
║              KONVERGENZ ERREICHT?                     ║│
║                    │                                  ║│
╚════════════════════│══════════════════════════════════╝│
                     │                                    │
                     ▼                                    │
[Phase 4: LLM-Verifizierung (Multi-Agent Debate)] ◄──────┘
                     │
                     ▼
              FERTIG ✅
```

---

## Standard-Konfiguration

Mit `config/society_defaults.json` werden diese Flags automatisch aktiviert:

| Flag | Beschreibung |
|------|-------------|
| `autonomous` | Volle Autonomie bis 100% fertig |
| `continuous_sandbox` | VNC-Sandbox parallel starten |
| `enable_vnc` | VNC-Streaming aktivieren |
| `enable_sandbox` | Docker-Sandbox-Tests |
| `enable_validation` | ValidationTeam aktivieren |
| `dashboard` | Echtzeit-Dashboard |
| `persistent_deploy` | VNC nach Fertigstellung behalten |
| `async_e2e` | Kontinuierliche E2E-Tests |
| `async_ux` | Kontinuierliche UX-Reviews |
| `llm_verification` | Multi-Agent Debate Verifizierung |

---

## Wichtige Dateien

| Datei | Zweck |
|-------|-------|
| `run_society_hybrid.py` | Haupteinstiegspunkt |
| `src/mind/orchestrator.py` | Agent-Koordination + Async Services |
| `src/mind/event_bus.py` | Event-Pub/Sub-System |
| `src/agents/deployment_team_agent.py` | Sandbox + VNC |
| `src/agents/verification_debate_agent.py` | Multi-Agent Debate (Phase 4) |
| `src/mind/completeness_checker.py` | LLM-basierte Verifizierung |
| `src/tools/sandbox_tool.py` | Docker-Container-Management |
| `src/tools/claude_code_tool.py` | Claude API Integration |

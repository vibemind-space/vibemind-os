# Konfiguration & Verwendung

## Standard-Konfiguration

Mit `config/society_defaults.json` werden diese Flags automatisch aktiviert:

```json
{
  "autonomous": true,
  "continuous_sandbox": true,
  "enable_vnc": true,
  "vnc_port": 6080,
  "enable_sandbox": true,
  "enable_validation": true,
  "validation_docker": true,
  "dashboard": true,
  "dashboard_port": 8080,
  "persistent_deploy": true,
  "verbose": true,
  "max_concurrent": 2,
  "sandbox_interval": 30,
  "async_e2e": true,
  "async_ux": true,
  "async_e2e_interval": 60,
  "async_ux_interval": 120,
  "llm_verification": true,
  "verification_debate_rounds": 3
}
```

---

## Flags Übersicht

### Basis-Flags

| Flag | Beschreibung | Default |
|------|-------------|---------|
| `--autonomous` | Volle Autonomie bis 100% fertig | true |
| `--continuous-sandbox` | VNC-Sandbox VOR Codegen starten | true |
| `--enable-vnc` | VNC-Streaming aktivieren | true |
| `--enable-sandbox` | Docker-Sandbox-Tests | true |
| `--enable-validation` | ValidationTeam aktivieren | true |
| `--dashboard` | Echtzeit-Dashboard | true |
| `--persistent-deploy` | VNC nach Fertigstellung behalten | true |
| `--verbose` | Detaillierte Logs | true |

### Async Services Flags (NEU)

| Flag | Beschreibung | Default | Interval |
|------|-------------|---------|----------|
| `--async-e2e` | E2E-Tests kontinuierlich parallel ausführen | true | 60s |
| `--async-ux` | UX-Review kontinuierlich parallel ausführen | true | 120s |
| `--async-services` | Alle async Services aktivieren | false | - |
| `--async-e2e-interval` | Interval zwischen E2E-Zyklen (Sekunden) | 60 | - |
| `--async-ux-interval` | Interval zwischen UX-Review-Zyklen (Sekunden) | 120 | - |

### LLM-Verifizierung Flags (NEU)

| Flag | Beschreibung | Default |
|------|-------------|---------|
| `--llm-verification` | Multi-Agent Debate Verifizierung aktivieren | false |
| `--verification-debate-rounds` | Anzahl der Debate-Runden | 3 |

### Legacy Flags (Abwärtskompatibilität)

| Flag | Beschreibung | Mapped zu |
|------|-------------|-----------|
| `--e2e-testing` | E2E-Tests aktivieren | `--async-e2e` |
| `--ux-review` | UX-Review aktivieren | `--async-ux` |
| `--phase5` | Phase 5 Features aktivieren | `--async-e2e` + `--async-ux` |

---

## Output-Verzeichnis Format

Das System generiert automatisch eindeutige Output-Verzeichnisse:

```text
output_001_a3f2b1c8/   # Erster Run
output_002_7d4e9f12/   # Zweiter Run
output_003_b8c3a5d6/   # Dritter Run
```

**Format:** `output_{incremental_id}_{short_uuid}`

Die Historie wird in `Data/run_history.json` gespeichert.

---

## Verwendungsbeispiele

### Einfachste Verwendung (alle Defaults)

```bash
python run_society_hybrid.py requirements.json
```

Erstellt automatisch: `output_001_xxxxxxxx/`

### Mit explizitem Output-Verzeichnis

```bash
python run_society_hybrid.py requirements.json -o ./mein-projekt
```

### Ohne Dashboard

```bash
python run_society_hybrid.py requirements.json --no-dashboard
```

### Schneller Modus (weniger strikt)

```bash
python run_society_hybrid.py requirements.json --fast
```

### Strikter Modus (100% alles)

```bash
python run_society_hybrid.py requirements.json --strict
```

### Mit Async Services

```bash
# Alle async Services aktivieren
python run_society_hybrid.py requirements.json --async-services

# Nur E2E async aktivieren mit kürzerem Interval
python run_society_hybrid.py requirements.json --async-e2e --async-e2e-interval 30

# Nur UX async aktivieren
python run_society_hybrid.py requirements.json --async-ux --async-ux-interval 60
```

### Mit LLM-Verifizierung

```bash
# Multi-Agent Debate für Phase 4 aktivieren
python run_society_hybrid.py requirements.json --llm-verification

# Mit mehr Debate-Runden
python run_society_hybrid.py requirements.json --llm-verification --verification-debate-rounds 5
```

---

## Services & URLs

Nach dem Start sind folgende Services verfügbar:

| Service | URL | Beschreibung |
|---------|-----|--------------|
| **VNC Stream** | http://localhost:6080/vnc.html | Live-Ansicht der App |
| **Dashboard** | http://localhost:8080 | Agent-Aktivität |
| **Live Preview** | http://localhost:5173 | Dev-Server (Vite) |
| **API** | http://localhost:8000 | Coding Engine API |

---

## Konvergenz-Modi

### Autonomous (Standard)

- Max Iterations: 200
- Max Time: 60 Minuten
- Min Test Rate: 100%
- Min Confidence: 95%

### Strict

- Max Iterations: 50
- Max Time: 10 Minuten
- Min Test Rate: 100%
- Type Errors: 0

### Relaxed

- Max Iterations: 30
- Max Time: 15 Minuten
- Min Test Rate: 80%

### Fast

- Max Iterations: 10
- Max Time: 5 Minuten
- Min Test Rate: 50%

---

## Async Services Architektur

Die Async Services laufen **kontinuierlich parallel** zum Phase 3 Loop:

```text
┌────────────────────────────────────────────────────────────┐
│  Phase 3: Society of Mind Loop                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  BUILD → TEST → FIX → REPEAT                          │  │
│  │                                                       │  │
│  │  ASYNC SERVICES (parallel):                           │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐        │  │
│  │  │VNC Sandbox│  │Async E2E  │  │Async UX   │        │  │
│  │  │(30s cycle)│  │(60s cycle)│  │(120s cycle)│        │  │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘        │  │
│  │        │              │              │               │  │
│  │        └──────────────┴──────────────┘               │  │
│  │                       │                              │  │
│  │                       ▼                              │  │
│  │              EVENT BUS BERICHTE                      │  │
│  │                       │                              │  │
│  │  ┌────────────────────┴────────────────────┐        │  │
│  │  │ E2E_FAILED, UX_ISSUE → GeneratorAgent   │        │  │
│  │  │ SANDBOX_FAILED → ContinuousDebugAgent   │        │  │
│  │  └─────────────────────────────────────────┘        │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Service-Verhalten

| Service | Trigger | Fehler-Event | Behandelt durch |
|---------|---------|--------------|-----------------|
| VNC Sandbox | `--continuous-sandbox` | SANDBOX_TEST_FAILED | ContinuousDebugAgent |
| Async E2E | `--async-e2e` | E2E_TEST_FAILED | GeneratorAgent |
| Async UX | `--async-ux` | UX_ISSUE_FOUND | GeneratorAgent |

---

## LLM-basierte Verifizierung (Phase 4)

Mit `--llm-verification` wird die Vollständigkeitsprüfung LLM-basiert durchgeführt:

```text
┌─────────────────────────────────────────────────────────────┐
│  MULTI-AGENT DEBATE (pro Requirement)                      │
│                                                            │
│  1. Initial: Drei Solver analysieren unabhängig            │
│     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│     │Implementation│ │   Testing    │ │  Deployment  │    │
│     │   Solver     │ │   Solver     │ │   Solver     │    │
│     └──────────────┘ └──────────────┘ └──────────────┘    │
│                                                            │
│  2. Debate: N Runden Peer-Feedback                        │
│     Solver A ◄──► Solver B ◄──► Solver C                  │
│                                                            │
│  3. Aggregation: Majority Voting                          │
│     ┌──────────────────────────────────────┐              │
│     │ VERIFIED | FAILED | NEEDS_MORE       │              │
│     │ (gewichtet nach Confidence)          │              │
│     └──────────────────────────────────────┘              │
│                                                            │
│  4. Bei FAILED: Zurück zu Phase 3 Loop                    │
└─────────────────────────────────────────────────────────────┘
```

### Solver-Perspektiven

| Solver | Perspektive | Prüft |
|--------|-------------|-------|
| **ImplementationSolver** | Code-Qualität | Sind alle Features implementiert? |
| **TestingSolver** | Test-Coverage | Sind alle Edge-Cases getestet? |
| **DeploymentSolver** | Runtime-Verhalten | Funktioniert es in Produktion? |

---

## Umgebungsvariablen

| Variable | Beschreibung | Erforderlich |
|----------|-------------|--------------|
| `ANTHROPIC_API_KEY` | Claude API Schlüssel | Ja |
| `GITHUB_TOKEN` | Für Cloud-Tests | Optional |
| `DATABASE_URL` | PostgreSQL Verbindung | Optional |
| `REDIS_URL` | Redis Verbindung | Optional |

---

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `config/society_defaults.json` | Standard-Konfiguration |
| `Data/run_history.json` | Run-Historie (auto-generiert) |
| `run_society_hybrid.py` | Hauptskript |
| `src/mind/orchestrator.py` | Orchestrator mit Async Services |
| `src/agents/verification_debate_agent.py` | Multi-Agent Debate Agent |
| `src/mind/completeness_checker.py` | LLM-basierte Verifizierung |

# Continuous Sandbox Testing Implementation

## Overview

Diese Dokumentation beschreibt die Implementierung des kontinuierlichen Sandbox-Testing-Systems, das alle 30 Sekunden das generierte Projekt in einem Docker-Container startet, testet und wieder beendet.

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Hybrid Society of Mind                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Generator   │  │ Tester      │  │ Builder     │  │ DeploymentTeam      │ │
│  │ Agent       │  │ Agent       │  │ Agent       │  │ Agent (Continuous)  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                │                     │           │
│         └────────────────┴────────────────┴─────────────────────┤           │
│                                                                 │           │
│  ┌──────────────────────────────────────────────────────────────┴────────┐  │
│  │                            EventBus                                   │  │
│  │  Events: BUILD_SUCCEEDED, CODE_FIXED, SANDBOX_TEST_PASSED/FAILED,    │  │
│  │          SCREEN_STREAM_READY, CONVERGENCE_UPDATE                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Docker Sandbox (Continuous Loop)                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  30-Second Cycle:                                                     │   │
│  │    1. Start App (npm start / uvicorn / etc.)                         │   │
│  │    2. Health Check (curl / process check)                            │   │
│  │    3. Kill App Process                                               │   │
│  │    4. Report Result → EventBus                                       │   │
│  │    5. Wait for next cycle                                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                        │
│                    │      VNC Streaming (6080)      │                        │
│                    │   http://localhost:6080/vnc.html│                       │
│                    └───────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Implementierte Komponenten

### 1. SandboxTool (`src/tools/sandbox_tool.py`)

**Neue Features:**
- `ContinuousSandboxCycle` Dataclass für einzelne Zyklus-Ergebnisse
- `run_continuous_tests()` async Generator für kontinuierliches Testen
- `_setup_continuous_container()` für einmaliges Container-Setup
- `_run_single_cycle()` für einzelne Test-Zyklen
- `stop_continuous()` Methode zum Stoppen

**Neue Parameter:**
```python
SandboxTool(
    project_dir="./output",
    cycle_interval=30,      # Sekunden zwischen Zyklen
    enable_vnc=True,        # VNC-Streaming aktivieren
    vnc_port=6080,          # noVNC Webport
)
```

### 2. DeploymentTeamAgent (`src/agents/deployment_team_agent.py`)

**Neue Features:**
- `enable_continuous` Parameter für kontinuierlichen Modus
- `start_continuous_loop()` und `stop_continuous_loop()` Methoden
- `_continuous_loop()` Hintergrund-Task
- `get_continuous_status()` für Status-Abfrage
- Automatischer Start bei Agent-Start wenn aktiviert

**Neue Parameter:**
```python
DeploymentTeamAgent(
    enable_continuous=True,           # Kontinuierlichen Modus aktivieren
    cycle_interval=30,                # 30 Sekunden zwischen Tests
    start_continuous_immediately=True # Sofort starten ohne BUILD_SUCCEEDED
)
```

### 3. HybridSocietyConfig (`src/mind/integration.py`)

**Neue Konfigurationsoptionen:**
```python
HybridSocietyConfig(
    enable_continuous_sandbox=True,    # Kontinuierlichen Sandbox-Modus aktivieren
    sandbox_cycle_interval=30,         # Zyklusintervall in Sekunden
    start_sandbox_immediately=True,    # Sofort starten
)
```

### 4. CLI-Argumente (`run_society_hybrid.py`)

**Neue Flags:**
```bash
# Kontinuierliches Sandbox-Testing aktivieren
python run_society_hybrid.py requirements.json --continuous-sandbox

# Mit benutzerdefiniertem Intervall
python run_society_hybrid.py requirements.json --continuous-sandbox --sandbox-interval 15

# Mit VNC-Streaming
python run_society_hybrid.py requirements.json --continuous-sandbox --enable-vnc

# Verzögerter Start (wartet auf BUILD_SUCCEEDED)
python run_society_hybrid.py requirements.json --continuous-sandbox --no-start-sandbox-immediately
```

## Verwendung

### Basis-Verwendung

```bash
# Standard: Kontinuierliche Sandbox alle 30 Sekunden
python run_society_hybrid.py requirements.json \
    --output-dir ./output \
    --continuous-sandbox \
    --enable-vnc
```

### Programmatische Verwendung

```python
from src.mind.integration import HybridSocietyConfig, HybridSocietyRunner

config = HybridSocietyConfig(
    requirements_path="requirements.json",
    output_dir="./output",
    enable_continuous_sandbox=True,
    sandbox_cycle_interval=30,
    enable_vnc_streaming=True,
    vnc_port=6080,
)

runner = HybridSocietyRunner(config)
result = await runner.run()

# Ergebnisse
print(f"Sandbox Cycles: {result.sandbox_cycles_completed}")
print(f"Last Success: {result.sandbox_last_success}")
print(f"VNC URL: {result.vnc_url}")
```

### Direkte SandboxTool Verwendung

```python
from src.tools.sandbox_tool import run_continuous_sandbox_tests

async for cycle in run_continuous_sandbox_tests(
    project_dir="./my-project",
    cycle_interval=30,
    enable_vnc=True,
):
    print(f"Cycle {cycle.cycle_number}: {'✓' if cycle.success else '✗'}")
    print(f"  App Started: {cycle.app_started}")
    print(f"  Responsive: {cycle.app_responsive}")
    print(f"  Duration: {cycle.duration_ms}ms")
    
    if cycle.success:
        print("Project works! Stopping.")
        break
```

## Event Flow

1. **SANDBOX_TEST_STARTED** - Kontinuierlicher Loop gestartet
2. **SANDBOX_TEST_PASSED** / **SANDBOX_TEST_FAILED** - Nach jedem Zyklus
3. **SCREEN_STREAM_READY** - VNC-URL verfügbar (bei Electron)

## VNC-Streaming

Für Electron-Apps wird automatisch VNC-Streaming aktiviert:

```
┌─────────────────────────────────────────────┐
│  Browser: http://localhost:6080/vnc.html    │
│  ┌───────────────────────────────────────┐  │
│  │         Electron App View              │  │
│  │                                        │  │
│  │    ┌─────────────────────────────┐     │  │
│  │    │     Counter: 42             │     │  │
│  │    │       [+]  [-]  [Reset]     │     │  │
│  │    └─────────────────────────────┘     │  │
│  │                                        │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Unterstützte Projekttypen

| Projekttyp | Start-Befehl | Health-Check |
|------------|--------------|--------------|
| Electron | `npm run start` | `pgrep electron` |
| React/Vite | `npm run preview` | `curl :4173` |
| Node.js API | `npm start` | `curl :3000` |
| FastAPI | `uvicorn` | `curl :8000` |
| Flask | `flask run` | `curl :5000` |

## Tests

Alle 21 Unit-Tests bestanden:

```
tests/test_system_validation.py::TestScaffolding::test_project_initializer_creates_structure PASSED
tests/test_system_validation.py::TestScaffolding::test_electron_project_detection PASSED
tests/test_system_validation.py::TestHybridPipeline::test_pipeline_initialization PASSED
tests/test_system_validation.py::TestHybridPipeline::test_requirements_parsing PASSED
tests/test_system_validation.py::TestSocietyAgents::test_agent_creation PASSED
tests/test_system_validation.py::TestSocietyAgents::test_deployment_team_agent PASSED
tests/test_system_validation.py::TestEventBus::test_event_publish_subscribe PASSED
tests/test_system_validation.py::TestEventBus::test_event_types_exist PASSED
tests/test_system_validation.py::TestClaudeCLI::test_claude_tool_initialization PASSED
tests/test_system_validation.py::TestClaudeCLI::test_claude_tool_exists PASSED
tests/test_system_validation.py::TestSandboxDeployment::test_project_type_detection PASSED
tests/test_system_validation.py::TestSandboxDeployment::test_sandbox_tool_initialization PASSED
tests/test_system_validation.py::TestSandboxDeployment::test_continuous_sandbox_cycle_dataclass PASSED
tests/test_system_validation.py::TestVNCStreaming::test_vnc_url_generation PASSED
tests/test_system_validation.py::TestVNCStreaming::test_vnc_port_configuration PASSED
tests/test_system_validation.py::TestConvergenceCriteria::test_default_criteria PASSED
tests/test_system_validation.py::TestConvergenceCriteria::test_autonomous_criteria PASSED
tests/test_system_validation.py::TestConvergenceCriteria::test_convergence_check PASSED
tests/test_system_validation.py::TestIntegrationConfig::test_config_defaults PASSED
tests/test_system_validation.py::TestIntegrationConfig::test_config_with_continuous_sandbox PASSED
tests/test_system_validation.py::TestResultDataclasses::test_hybrid_society_result PASSED

========================== 21 passed ==========================
```

## Dateien geändert

1. `src/tools/sandbox_tool.py` - Kontinuierliche Test-Methoden hinzugefügt
2. `src/agents/deployment_team_agent.py` - Continuous Mode implementiert
3. `src/mind/orchestrator.py` - Neue Parameter für kontinuierliche Sandbox
4. `src/mind/integration.py` - Konfiguration und Result-Erweiterungen
5. `run_society_hybrid.py` - CLI-Argumente hinzugefügt
6. `tests/validation_requirements.json` - Test-Requirements erstellt
7. `tests/test_system_validation.py` - Umfassende Unit-Tests
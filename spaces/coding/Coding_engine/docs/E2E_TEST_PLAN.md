# End-to-End Test Plan für Coding Engine Pipeline

## Erstelldatum: 2025-12-02

---

## 1. CLI-Optionen Dokumentation

### 1.1 run_hybrid.py (Basic Pipeline)

| Option | Default | Beschreibung |
|--------|---------|--------------|
| `requirements_file` | (required) | Pfad zur Requirements JSON Datei |
| `--output-dir` | `./output` | Output-Verzeichnis für generierte Dateien |
| `--job-id` | `1` | Job-ID für Tracking |
| `--max-concurrent` | `5` | Maximale parallele CLI-Aufrufe |
| `--max-iterations` | `3` | Maximale Recovery-Iterationen |
| `--slice-size` | `3` | Requirements pro Slice |
| `--quiet` | `false` | Unterdrückt Progress-Output |

### 1.2 run_job.py (Simple Job Runner)

| Option | Default | Beschreibung |
|--------|---------|--------------|
| `requirements_file` | (required) | Pfad zur Requirements JSON Datei |
| `--output-dir` | `./output` | Output-Verzeichnis |
| `--job-id` | `1` | Job-ID |
| `--max-concurrent` | `5` | Maximale parallele Aufrufe |
| `--slice-size` | `10` | Requirements pro Slice |
| `--quiet` | `false` | Quiet-Modus |

### 1.3 run_society_hybrid.py (Full Autonomous)

#### Execution Modes
| Mode | Tests Rate | Errors | Timeout | Iterations |
|------|------------|--------|---------|------------|
| `--autonomous` | 100% | 0 | 1 hour | max |
| `--strict` | 100% | 0 | 10 min | high |
| `--relaxed` | 80% | allowed | medium | medium |
| `--fast` | low | allowed | 5 min | few |

#### Core Options
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `requirements` | (required) | Requirements JSON Pfad |
| `--tech-stack`, `-t` | None | Tech-Stack JSON Datei |
| `--output-dir`, `-o` | `./output` | Output-Verzeichnis |
| `--max-iterations` | mode-specific | Max Iterationen |
| `--max-time` | mode-specific | Max Zeit in Sekunden |
| `--min-test-rate` | mode-specific | Min Test-Erfolgsrate % |
| `--min-confidence` | mode-specific | Min Confidence 0-1 |

#### Pipeline Options
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `--no-scaffold` | false | Projekt-Scaffolding überspringen |
| `--no-install` | false | Dependency-Installation überspringen |
| `--max-concurrent` | 2 | Max parallele Code-Gen Tasks |
| `--slice-size` | 3 | Requirements Slice Größe |

#### Preview Options
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `--no-preview` | false | Live Preview deaktivieren |
| `--port` | 5173 | Preview Port |
| `--no-open-browser` | false | Browser nicht auto-öffnen |

#### Validation Options
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `--check-completeness` | true | Vollständigkeitsprüfung |
| `--no-completeness-check` | false | Prüfung überspringen |
| `--e2e-testing` | false | Phase 5 E2E Testing |
| `--ux-review` | false | Phase 5 UX Review |
| `--phase5` | false | Alle Phase 5 Features |

#### Sandbox Options
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `--enable-sandbox` | false | Docker Sandbox Testing |
| `--enable-cloud-tests` | false | GitHub Actions Tests |
| `--deployment-team` | false | Full Deployment Team |
| `--enable-vnc` | false | VNC Streaming für Electron |
| `--vnc-port` | 6080 | noVNC Port |
| `--continuous-sandbox` | false | Continuous Sandbox Testing |
| `--sandbox-interval` | 30 | Sekunden zwischen Tests |
| `--start-sandbox-immediately` | true | Sofort starten |

#### Dashboard Options
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `--dashboard` | false | Real-time Dashboard |
| `--dashboard-port` | 8080 | Dashboard Port |
| `--no-docs` | false | CLAUDE.md nicht generieren |
| `--verbose`, `-v` | false | Verbose Output |

---

## 2. Test-Szenarien

### 2.1 Konfigurationsvalidierung (E2E-3)

```bash
# Test 1: Fehlende Requirements-Datei
python run_hybrid.py nonexistent.json 2>&1

# Test 2: Ungültiges JSON
python run_hybrid.py tests/fixtures/invalid.json 2>&1

# Test 3: Leere Requirements
python run_hybrid.py tests/fixtures/empty_requirements.json 2>&1

# Test 4: Gültiger Minimal-Test
python run_hybrid.py tests/fixtures/minimal_requirements.json --output-dir output_e2e_test --quiet 2>&1
```

### 2.2 Datenfluss-Tests (E2E-4)

```bash
# Pipeline-Phasen einzeln testen
python -c "
from src.engine.dag_parser import DAGParser
from src.engine.slicer import Slicer
import json

# Phase 0: DAG Parsing
parser = DAGParser()
with open('tests/fixtures/minimal_requirements.json') as f:
    reqs = json.load(f)
result = parser.parse_requirements(reqs['requirements'])
print(f'Phase 0: {len(result.nodes)} nodes parsed')

# Phase 1: Slicing
slicer = Slicer()
manifest = slicer.slice_requirements(result, job_id=1)
print(f'Phase 1: {manifest.total_slices} slices created')
"
```

### 2.3 Slicer-Strategien (E2E-5)

```bash
# Test verschiedene Slicing-Strategien
python -c "
from src.engine.dag_parser import DAGParser
from src.engine.slicer import Slicer
import json

parser = DAGParser()
with open('Data/requirements.json') as f:
    reqs = json.load(f)
result = parser.parse_requirements(reqs['requirements'])

slicer = Slicer()

# Hybrid Strategy
manifest = slicer.slice_requirements(result, job_id=1, strategy='hybrid')
print(f'Hybrid: {manifest.total_slices} slices')

# Domain Strategy
manifest = slicer.slice_requirements(result, job_id=2, strategy='domain')
print(f'Domain: {manifest.total_slices} slices')

# Feature-Grouped Strategy  
manifest = slicer.slice_requirements(result, job_id=3, strategy='feature_grouped')
print(f'Feature-Grouped: {manifest.total_slices} slices')
"
```

### 2.4 Feature-Erkennung (E2E-6)

```bash
# Test Feature-Detection für verschiedene Requirements
python -c "
from src.engine.slicer import Slicer, Domain
from dataclasses import dataclass

@dataclass
class MockNode:
    id: str
    name: str

slicer = Slicer()

test_cases = [
    ('REQ-001', 'Create React button component'),
    ('REQ-002', 'Implement REST API endpoint'),
    ('REQ-003', 'Setup PostgreSQL database schema'),
    ('REQ-004', 'Add JWT authentication'),
    ('REQ-005', 'Create user login page'),
]

for req_id, name in test_cases:
    node = MockNode(id=req_id, name=name)
    domain = slicer._detect_domain(node)
    print(f'{req_id}: {name[:40]} -> {domain.value}')
"
```

### 2.5 Fehlerbehandlung (E2E-7)

```bash
# Test 1: Ungültiger Slice-Size
python run_hybrid.py Data/requirements.json --slice-size -1 2>&1

# Test 2: Ungültige Job-ID
python run_hybrid.py Data/requirements.json --job-id abc 2>&1

# Test 3: Nicht existierendes Output-Dir (sollte erstellt werden)
python run_hybrid.py Data/requirements.json --output-dir /nonexistent/path --quiet 2>&1
```

### 2.6 Ressourcenmanagement (E2E-8)

```bash
# Test Cleanup nach Run
python -c "
import os
import shutil
import tempfile

test_dir = tempfile.mkdtemp(prefix='e2e_test_')
print(f'Test directory: {test_dir}')

# Run würde hier starten
# Nach Cleanup sollte Verzeichnis leer sein
"
```

---

## 3. Test-Fixtures

### 3.1 minimal_requirements.json

```json
{
  "requirements": [
    {
      "id": "REQ-E2E-001",
      "name": "E2E Test Requirement",
      "description": "Test requirement for E2E validation"
    }
  ]
}
```

### 3.2 invalid.json

```text
{ invalid json content
```

### 3.3 empty_requirements.json

```json
{
  "requirements": []
}
```

---

## 4. Ausführungsreihenfolge

1. **Vorbereitung**
   - [ ] Test-Fixtures erstellen
   - [ ] Output-Verzeichnis bereinigen

2. **Konfigurationsvalidierung (E2E-3)**
   - [ ] Fehlende Datei testen
   - [ ] Ungültiges JSON testen
   - [ ] Leere Requirements testen
   - [ ] Minimal-Run testen

3. **Datenfluss (E2E-4)**
   - [ ] DAG Parser testen
   - [ ] Slicer Output validieren
   - [ ] Pipeline-Übergänge prüfen

4. **Slicer-Strategien (E2E-5)**
   - [ ] Hybrid Strategy
   - [ ] Domain Strategy
   - [ ] Feature-Grouped Strategy

5. **Feature-Erkennung (E2E-6)**
   - [ ] Frontend-Features
   - [ ] Backend-Features
   - [ ] Database-Features

6. **Fehlerbehandlung (E2E-7)**
   - [ ] Ungültige Parameter
   - [ ] Grenzwerte
   - [ ] Recovery

7. **Ressourcen (E2E-8)**
   - [ ] Memory Usage
   - [ ] File Cleanup
   - [ ] Process Termination

---

## 5. Metriken

| Metrik | Ziel | Messmethode |
|--------|------|-------------|
| Startup Time | < 2s | time.time() |
| Phase 0 (Parse) | < 1s | Timer |
| Phase 1 (Slice) | < 0.5s | Timer |
| Memory Peak | < 500MB | psutil |
| Cleanup Complete | 100% | File check |
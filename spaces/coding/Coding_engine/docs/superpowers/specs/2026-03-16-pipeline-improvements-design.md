# Pipeline Improvements Design — DaveFelix Coding Engine

**Date:** 2026-03-16
**Status:** Reviewed (Issues fixed)
**Approach:** B — Service-by-Service Pipeline mit Hybrid Skeleton + Agent Fill

---

## 1. Problem Statement

Die aktuelle Pipeline (`HybridPipeline`) hat 6 kritische Luecken:

1. **Spec-Parsing**: Requirements werden als rohe Textstrings geladen (~2000 Zeichen, abgeschnitten)
2. **Traceability**: Keine Verlinkung Requirement -> generierter Code
3. **Contract Coverage**: Unbekannt ob alle 418 Endpoints abgedeckt sind
4. **Context Injection**: Agents bekommen statischen, generischen Context
5. **Consistency Checks**: Nur Regex-Fixes (NestJS-Module), kein Spec<->Code Abgleich
6. **Validators**: Nur File-Level (tsc, build), keine Cross-File oder Requirement-Coverage Checks

## 2. Design Goals

| Goal | Metric |
|------|--------|
| **Qualitaet** | Generierter Code baut + Tests laufen fuer jeden Service |
| **Vollstaendigkeit** | 418/418 Endpoints implementiert (100% Coverage) |
| **Inkrementell** | Einzelne Services unabhaengig generierbar/re-generierbar |
| **Debugbar** | Jeder Fehler ist einem Service + Datei zuordbar |
| **Token-effizient** | ~75% weniger Tokens pro Agent-Call durch fokussierten Context |

## 3. Architecture Overview

```
whatsapp-messaging-service_20260211_025459/
    |
    v
[Prio 1] SpecParser
    | ParsedSpec (strukturiert, maschinenlesbar)
    v
[Prio 2] SkeletonGenerator
    | Code-Geruest (alle Dateien, alle Methoden, 0% Logik)
    v
[Prio 3] ServiceOrchestrator -> ServicePipeline (pro Service)
    |   +-- [Prio 5] ContextInjector (pro Datei)
    |   +-- Agent Fill (Logik implementieren)
    |   +-- [Prio 4] ValidationEngine (Spec<->Code Check)
    |   +-- [Prio 6] TraceabilityTracker (Req->Code Mapping)
    v
Output: Code + Validation Report + Traceability Matrix
```

## 4. Approach: B — Service-by-Service Pipeline

Gewaehlt gegenueber:
- **A) Pipeline Extension** — abgelehnt weil Monolith-Risiko bei 17 Services
- **C) Layered Generation** — abgelehnt weil zu komplex zu orchestrieren

Approach B kombiniert das Beste aus B + C:
- Phase 0 (Global Shared Layer) aus Approach C
- Service-by-Service linear aus Approach B
- Dependency-Graph-basierte Reihenfolge

---

## 5. Component Designs

### 5.1 Prio 1: Structured Spec Parser (`src/engine/spec_parser.py`)

**Purpose:** Alle Artefakte aus dem Service-Ordner in maschinenlesbare Datenstrukturen konvertieren.

**Inputs:**
- `api/api_documentation.md` -> ParsedEndpoint[] (418 Endpoints)
- `api/openapi_spec.yaml` -> ParsedEndpoint[] (Validierung)
- `data/data_dictionary.md` -> ParsedEntity[] (48 Entities)
- `architecture/architecture.md` -> ParsedService[] (17 Services)
- `user_stories/user_stories.md` -> ParsedUserStory[] (126 Stories)
- `state_machines/*.mmd` -> StateMachine[] (per Service)
- `user_stories.json` -> Cross-Referenz Req<->Story

**Relationship to Existing Models:**

`SpecParser` **replaces** `DocumentationLoader` and the loading part of `SpecAdapter`. The existing `NormalizedSpec` becomes a thin wrapper that delegates to `ParsedSpec`:
- `DocumentationLoader` is deprecated — its parsing logic migrates into `SpecParser`
- `SpecAdapter.load()` calls `SpecParser.parse()` internally and returns a `NormalizedSpec` for backward compatibility
- `ParsedSpec` is the new canonical model; `NormalizedSpec` adapts from it

**Core Data Structures:**

```python
@dataclass
class Field:
    name: str            # id, phoneNumber, createdAt
    type: str            # uuid, string, datetime, int, boolean
    nullable: bool       # default False
    unique: bool         # default False
    default: str | None  # e.g. "uuid()", "now()", None

@dataclass
class Relation:
    target: str          # Target entity name, e.g. "Message"
    type: str            # one-to-one, one-to-many, many-to-many
    field: str           # Foreign key field, e.g. "userId"
    inverse: str | None  # Inverse relation name, e.g. "messages"

@dataclass
class StateTransition:
    from_state: str      # e.g. "pending_verification"
    to_state: str        # e.g. "verified"
    trigger: str         # e.g. "verify_code_success"
    guard: str | None    # e.g. "code_not_expired"

@dataclass
class StateMachine:
    name: str            # e.g. "UserRegistration"
    entity: str          # e.g. "User"
    states: list[str]    # ["unregistered", "pending_verification", "verified", "active"]
    initial_state: str   # "unregistered"
    terminal_states: list[str]  # ["active", "banned"]
    transitions: list[StateTransition]

@dataclass
class ParsedEndpoint:
    method: str          # GET, POST, PUT, DELETE
    path: str            # /api/v1/auth/register
    service: str         # auth-service
    request_dto: str     # RegisterRequestDto
    response_dto: str    # RegisterResponseDto
    auth_required: bool
    linked_stories: list[str]  # ["US-001", "US-002"]
    status_codes: dict[int, str]  # {200: "Success", 409: "Conflict"}

@dataclass
class ParsedEntity:
    name: str            # User
    fields: list[Field]
    relations: list[Relation]
    service: str         # auth-service

@dataclass
class ParsedUserStory:
    id: str              # US-001
    epic: str            # EPIC-001
    title: str
    acceptance_criteria: list[str]
    linked_requirements: list[str]  # ["WA-AUTH-001"]
    linked_endpoints: list[str]     # ["/api/v1/auth/register"]

@dataclass
class ParsedService:
    name: str            # auth-service
    port: int            # 3001
    technology: str      # NestJS 10.3.2
    dependencies: list[str]  # ["postgres-auth", "redis-cache"]
    service_dependencies: list[str]  # ["auth-service"] — other API services
    endpoints: list[ParsedEndpoint]
    entities: list[ParsedEntity]
    stories: list[ParsedUserStory]
    state_machines: list[StateMachine]

@dataclass
class ParsedSpec:
    services: dict[str, ParsedService]  # 17 Services
    shared_entities: list[ParsedEntity]
    dependency_graph: dict[str, list[str]]
    generation_order: list[str]  # Topologisch sortiert
    openapi_version: str  # "3.0.3" — parsed from openapi_spec.yaml
```

**Dependency Graph:** Automatisch aus `architecture.md` extrahiert, topologisch sortiert:
```
auth-service          -> [] (zuerst)
user-profile-service  -> [auth-service]
media-service         -> [auth-service]
websocket-service     -> [auth-service]
messaging-service     -> [auth-service, websocket-service]
chat-service          -> [messaging-service]
notification-worker   -> [messaging-service, chat-service, media-service]
```

---

### 5.2 Prio 2: Skeleton Generator (`src/engine/skeleton_generator.py`)

**Purpose:** Deterministisches (kein LLM!) Code-Geruest aus ParsedSpec generieren. Garantiert 100% Endpoint-Coverage.

**Output pro Service (Beispiel auth-service):**

```
output/auth-service/
+-- prisma/schema.prisma              <- Aus ParsedEntity[]
+-- src/
|   +-- main.ts                       <- Boilerplate (Port aus ParsedService)
|   +-- app.module.ts                 <- Importiert alle Feature-Module
|   +-- auth/
|   |   +-- auth.module.ts            <- NestJS Module
|   |   +-- auth.controller.ts        <- ALLE Endpoints als leere Methoden
|   |   +-- auth.service.ts           <- ALLE Service-Methoden als Stubs
|   |   +-- dto/
|   |   |   +-- register.dto.ts       <- Request/Response DTOs aus Spec
|   |   |   +-- login.dto.ts
|   |   |   +-- verify-2fa.dto.ts
|   |   +-- entities/
|   |   |   +-- user.entity.ts        <- Aus ParsedEntity
|   |   |   +-- device.entity.ts
|   |   +-- guards/
|   |       +-- jwt-auth.guard.ts     <- Stub
|   +-- shared/types/                  <- Cross-Service Interfaces
+-- test/auth.e2e-spec.ts             <- Test-Stubs pro Endpoint
+-- package.json                       <- Korrekte Deps aus Tech Stack
+-- tsconfig.json
+-- nest-cli.json
+-- Dockerfile
```

**Key Design Decisions:**
- Controller-Methoden enthalten `// TODO: Implement` + Acceptance Criteria als Kommentare
- Service-Methoden werfen `NotImplementedException` als Platzhalter
- Methodennamen in Controller und Service sind 1:1 identisch (deterministisch)
- Prisma Schema wird direkt aus ParsedEntity[] generiert (Felder, Typen, Relations)
- DTOs enthalten alle Felder aus der OpenAPI-Spec
- package.json enthaelt alle Dependencies aus tech_stack.md

**Was das Skeleton NICHT macht:**
- Keine Business-Logik
- Keine komplexen Validierungen (nur DTO-Struktur)
- Keine Error Handling Details
- Keine Tests mit Assertions (nur `it('should ...')` Stubs)

---

### 5.3 Prio 3: Service-by-Service Pipeline (`src/engine/service_orchestrator.py` + `src/engine/service_pipeline.py`)

**Purpose:** Services in Dependency-Reihenfolge generieren. Ein Service nach dem anderen, linear, debugbar.

**ServiceOrchestrator Flow:**

```
Phase 0: Global Shared Layer (einmal)
  +-- shared/types/
  +-- shared/events/ (Kafka Event Schemas)
  +-- shared/prisma-base/

Phase 1: Unabhaengige Services (parallel moeglich)
  +-- auth-service
  +-- media-service

Phase 2: Erste Abhaengigkeiten
  +-- user-profile-service (braucht auth Types)
  +-- websocket-service (braucht auth Types)

Phase 3: Core Services
  +-- messaging-service (braucht auth + websocket)
  +-- chat-service (braucht messaging)

Phase 4: Abhaengige Workers
  +-- notification-worker (braucht Events von allen)

Phase 5: Integration
  +-- API Gateway Config (Kong)
  +-- Docker Compose
  +-- Cross-Service Integration Tests
```

**Agent Interface:**

The `ServicePipeline` uses a `CodeFillAgent` that wraps the existing `ClaudeCodeTool`:

```python
@dataclass
class FillResult:
    file_path: Path
    content: str          # The generated file content
    tokens_used: int
    success: bool
    error: str | None     # LLM error message if failed

class CodeFillAgent:
    """Wraps ClaudeCodeTool for skeleton-fill operations."""
    def __init__(self, tool: ClaudeCodeTool):
        self.tool = tool

    async def fill(self, skeleton_file: Path, context: str) -> FillResult:
        """Fill a single skeleton file with implementation logic."""
        prompt = self._build_fill_prompt(skeleton_file, context)
        result = await self.tool.execute(prompt=prompt, context=context)
        return FillResult(
            file_path=skeleton_file,
            content=result.code,
            tokens_used=result.tokens_used,
            success=not result.error,
            error=result.error,
        )
```

**ServicePipeline pro Service:**

```python
class ServicePipeline:
    def __init__(self, agent: CodeFillAgent, context_injector: ContextInjector,
                 validation_engine: ValidationEngine, tracker: TraceabilityTracker):
        self.agent = agent
        self.context_injector = context_injector
        self.validation_engine = validation_engine
        self.tracker = tracker

    async def execute(self, service: ParsedService, skeleton_dir: Path) -> ServiceResult:
        # 1. Skeleton verifizieren
        self.verify_skeleton(skeleton_dir)
        # 2. File-by-File Agent Fill
        for file in self.get_fill_order(skeleton_dir):
            context = self.context_injector.get_context_for(file, service)
            result = await self.agent.fill(file, context)
            self.tracker.update(file, result)
            self.validation_engine.validate_file(file, result)
        # 3. Service-Level Validation
        await self.run_build(skeleton_dir)
        await self.run_tests(skeleton_dir)
        report = await self.validation_engine.validate_service(service, skeleton_dir)
        # 4. Recovery Loop (max 3x)
        if report.has_errors():
            await self.recovery_loop(report.errors, max_iterations=3)
        return ServiceResult(service.name, files, report, self.tracker.get_entries(service.name))
```

**Fill-Order Algorithm (`get_fill_order`):**

The fill-order is computed generically, not hardcoded per service:

```python
def get_fill_order(self, skeleton_dir: Path) -> list[Path]:
    """Compute fill order for any service based on file types."""
    files = list(skeleton_dir.rglob("*.ts"))
    order = []

    # Priority 1: Schema files (already in skeleton, skip unless incomplete)
    order += sorted(f for f in files if "schema.prisma" in str(f))
    # Priority 2: Shared types
    order += sorted(f for f in files if "/shared/" in str(f))
    # Priority 3: Services (one per feature module, sorted alphabetically)
    order += sorted(f for f in files if f.name.endswith(".service.ts"))
    # Priority 4: Controllers (after their service exists)
    order += sorted(f for f in files if f.name.endswith(".controller.ts"))
    # Priority 5: DTOs
    order += sorted(f for f in files if "/dto/" in str(f))
    # Priority 6: Guards/Middleware
    order += sorted(f for f in files if "/guards/" in str(f) or "/middleware/" in str(f))
    # Priority 7: Modules (after all providers exist)
    order += sorted(f for f in files if f.name.endswith(".module.ts") and "app.module" not in f.name)
    # Priority 8: app.module.ts (last module, imports all feature modules)
    order += sorted(f for f in files if "app.module" in f.name)
    # Priority 9: Tests
    order += sorted(f for f in files if f.name.endswith(".spec.ts"))

    return deduplicate(order)
```

This handles services with **multiple feature modules** (e.g. messaging-service with `message/`, `conversation/`, `reaction/` sub-modules) — each sub-module's service.ts comes before its controller.ts.

**CLI Interface:**
```bash
python run_pipeline.py --service auth-service            # Nur einen Service
python run_pipeline.py --service auth-service --refill   # Re-generieren
python run_pipeline.py --all                             # Alle in Dep-Reihenfolge
python run_pipeline.py --from messaging-service          # Ab einem Service
python run_pipeline.py --skeleton-only                   # Nur Skeleton, kein Agent Fill
python run_pipeline.py --validate-only                   # Nur Validation auf existierendem Code
python run_pipeline.py --service auth-service --resume   # Resume via CheckpointManager
```

**Checkpoint Integration:** The `ServiceOrchestrator` uses the existing `CheckpointManager` (`src/engine/checkpoint_manager.py`) to save state after each completed service. If the pipeline is interrupted, `--resume` picks up from the last completed service.

---

### 5.4 Prio 4: Validation Engine (`src/engine/validation_engine.py`)

**Purpose:** Modulare Validatoren die pruefen ob generierter Code mit Specs uebereinstimmt. Inspiriert von Continue "Checks-as-Code".

**Relationship to Existing Validators:**

New validators extend the existing `src/validators/base_validator.py:BaseValidator` and use its `ValidationFailure` + `ValidationSeverity` types. The `ValidationEngine` discovers validators dynamically via a `SpecValidator` protocol:

```python
class SpecValidator(ABC):
    """All new validators implement this protocol."""
    name: str
    severity: ValidationSeverity  # Uses existing enum from base_validator.py

    @abstractmethod
    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]: ...
```

New validators live under `src/engine/validators/` (not `src/validators/`) to separate spec-level validation from build-level validation. The `ValidationEngine` runs both systems: existing build validators + new spec validators.

**9 Validatoren (8 per-service + 1 cross-service):**

| Validator | Prueft | Severity |
|-----------|--------|----------|
| `endpoint_coverage` | Alle 418 Endpoints haben Controller-Methoden | ERROR |
| `entity_schema` | Prisma Schema <-> Data Dictionary identisch | ERROR |
| `method_consistency` | Controller ruft exakt existierende Service-Methoden | ERROR |
| `import_integrity` | Keine Phantom Imports (alle Zieldateien existieren) | ERROR |
| `dto_completeness` | DTOs haben alle Felder aus OpenAPI Spec | WARNING |
| `dependency_check` | package.json enthaelt alle genutzten Packages | WARNING |
| `state_machine` | Code implementiert definierte State-Uebergaenge | WARNING |
| `acceptance_criteria` | Heuristischer Check ob ACs wahrscheinlich erfuellt | INFO |
| `cross_service` | Kafka Events, Shared Types, Gateway Routes konsistent | ERROR |

The `cross_service` validator runs in Phase 5 (Integration) after all services are generated.

**Validation Report Output:** `output/{service}/validation_report.json`

```json
{
  "service": "auth-service",
  "summary": {
    "endpoint_coverage": "38/38 (100%)",
    "entity_coverage": "4/4 (100%)",
    "method_consistency": "36/38 (94.7%)",
    "import_integrity": "PASS",
    "dto_completeness": "35/38 (92.1%)",
    "dependencies": "PASS",
    "state_machines": "3/4 (75%)",
    "acceptance_criteria": "28/34 LIKELY, 6 UNLIKELY"
  },
  "issues": [...],
  "score": "87/100"
}
```

**Auto-Fix Policy:**
- ERROR -> Auto-Retry: Agent bekommt Issue + betroffene Datei
- WARNING -> Auto-Retry mit spezifischem Fix-Prompt
- INFO -> Nur Report, kein Auto-Fix

---

### 5.5 Prio 5: Smart Context Injection (`src/engine/context_injector.py`)

**Purpose:** Pro Datei den optimalen Context zusammenstellen. Kein generischer Textblock mehr.

**Context-Scopes:**
1. FILE — Die Datei selbst (Skeleton mit TODOs)
2. SIBLING — Andere Dateien im gleichen Feature-Modul
3. SERVICE — Bereits generierte Dateien dieses Service
4. DEPENDENCY — Exports der Dependency-Services
5. SPEC — Relevante Specs (nur die fuer diese Datei)

**Context Rules pro Dateityp:**

| Dateityp | must_include | spec_include | max_tokens |
|----------|-------------|-------------|------------|
| `*.service.ts` | prisma/schema, dto/*.dto.ts | User Stories, State Machines | 8000 |
| `*.controller.ts` | *.service.ts, dto/*.dto.ts, guards/*.guard.ts | Endpoint Definitions | 6000 |
| `*.dto.ts` | prisma/schema | OpenAPI Schema | 3000 |
| `*.guard.ts` | auth.service.ts | — | 2000 |
| `*.module.ts` | *.controller.ts, *.service.ts | — | 2000 |
| `*.e2e-spec.ts` | *.controller.ts, *.service.ts, dto/*.dto.ts | Acceptance Criteria, Endpoints | 10000 |

**Cross-Service Context:** Nur public API (Interfaces + DTOs) der Dependency-Services, nicht deren Implementierung.

**Token Budget Enforcement:**
Token counting uses character-based estimation (1 token ~ 4 chars). When assembled context exceeds `max_tokens` for a file type, the injector **prioritizes** in this order:
1. FILE (always included in full)
2. must_include files (truncate longest first)
3. spec_include (truncate or omit least relevant)
4. DEPENDENCY exports (summarize to interfaces only)

If context still exceeds budget after prioritization, a warning is logged and the agent receives a `// CONTEXT_TRUNCATED` marker so it knows some context was omitted.

**Token-Einsparung:** ~50.000 -> ~8.000-12.000 Tokens pro Agent-Call (~75% Reduktion)

---

### 5.6 Prio 6: Traceability Tracker (`src/engine/traceability_tracker.py`)

**Purpose:** Waehrend der Generation mitschreiben welcher Code welche Requirement erfuellt. Lebendige Req<->Code Matrix.

**Data Structure:**

```python
@dataclass
class TraceEntry:
    requirement_id: str       # WA-AUTH-001
    user_story_id: str        # US-001
    epic: str                 # EPIC-001
    endpoint: str             # POST /api/v1/auth/register
    service: str              # auth-service
    files: list[str]          # [auth.controller.ts, auth.service.ts, register.dto.ts]
    test_file: str            # auth.e2e-spec.ts
    validation_score: float   # 0.87
    status: str               # IMPLEMENTED | PARTIAL | MISSING
    acceptance_criteria: list[ACStatus]
```

**Output Formate:**
1. `output/traceability.json` — Maschinenlesbar
2. `output/TRACEABILITY.md` — Human-readable Markdown Tabelle
3. Dashboard-Daten fuer spaetere UI-Integration

**Tracking Timeline:**
- Skeleton-Phase: Tracker registriert alle erwarteten Entries
- Agent Fill: Tracker aktualisiert Status (SKELETON -> IMPLEMENTED)
- Validation: Tracker uebernimmt Scores + Issues
- Final: Gesamtreport ueber alle 17 Services

---

## 6. Failure Modes

Each component has defined behavior for failure scenarios:

### SpecParser Failures

| Failure | Behavior |
|---------|----------|
| Malformed markdown (unparseable section) | Log warning, skip section, continue parsing. Report missing data in ParsedSpec summary. |
| Missing file (e.g. no `openapi_spec.yaml`) | Use `api_documentation.md` as primary source. Log that cross-validation is unavailable. |
| Dependency graph cycle detected | Raise `CyclicDependencyError` with cycle path. User must fix architecture.md before continuing. |
| Inconsistent data (endpoint in API docs but not in architecture) | Add to ParsedSpec with `status: "unresolved"`. Validation Engine flags it later. |

### SkeletonGenerator Failures

| Failure | Behavior |
|---------|----------|
| Entity with unknown field type | Map to `String` with a `// WARN: unknown type` comment. |
| Endpoint with no DTO definition | Generate empty DTO stub with `// TODO: define fields from spec`. |

### ServicePipeline Failures

| Failure | Behavior |
|---------|----------|
| Agent Fill returns error (LLM failure) | Retry once. If still failing, mark file as `UNFILLED` and continue to next file. |
| Build fails after Agent Fill | Enter recovery loop (max 3 iterations). Agent gets error + file. |
| Recovery loop exhausted (3x failed) | Mark service as `NEEDS_REVIEW`. Save partial output. Continue to next service. |
| Dependency service failed | **Still attempt** downstream services — they may partially succeed. Log warning that dependency is incomplete. |

### ValidationEngine Failures

| Failure | Behavior |
|---------|----------|
| Validator crashes (bug in validator code) | Catch exception, log, skip validator. Report as `VALIDATOR_ERROR` in report. |

---

## 7. New Files Summary

| File | Type | Purpose |
|------|------|---------|
| `src/engine/spec_parser.py` | NEW | Structured Spec Parser |
| `src/engine/skeleton_generator.py` | NEW | Deterministic Code Skeleton |
| `src/engine/service_orchestrator.py` | NEW | Multi-Service Orchestration |
| `src/engine/service_pipeline.py` | NEW | Single-Service Pipeline |
| `src/engine/validation_engine.py` | NEW | Modular Validation |
| `src/engine/validators/endpoint_coverage.py` | NEW | Endpoint Coverage Check |
| `src/engine/validators/entity_schema.py` | NEW | Entity Schema Check |
| `src/engine/validators/method_consistency.py` | NEW | Method Consistency Check |
| `src/engine/validators/import_integrity.py` | NEW | Import Integrity Check |
| `src/engine/validators/dto_completeness.py` | NEW | DTO Completeness Check |
| `src/engine/validators/dependency_check.py` | NEW | Dependency Check |
| `src/engine/validators/state_machine.py` | NEW | State Machine Check |
| `src/engine/validators/acceptance_criteria.py` | NEW | Acceptance Criteria Check |
| `src/engine/validators/cross_service.py` | NEW | Cross-Service Consistency Check |
| `src/engine/code_fill_agent.py` | NEW | Agent wrapper for skeleton fill |
| `src/engine/context_injector.py` | NEW | Smart Context per File |
| `src/engine/traceability_tracker.py` | NEW | Req<->Code Matrix |
| `run_pipeline.py` | NEW | CLI Entry Point |

**Modified Files:**
- `src/engine/hybrid_pipeline.py` — Refactored to delegate to ServiceOrchestrator
- `src/agents/coordinator_agent.py` — Simplified to use ContextInjector

---

## 8. Migration Strategy

Die bestehende Pipeline bleibt funktionsfaehig. Neue Module werden parallel aufgebaut:

1. `SpecParser` kann standalone getestet werden (Input: Service-Ordner, Output: ParsedSpec JSON)
2. `SkeletonGenerator` kann standalone getestet werden (Input: ParsedSpec, Output: Dateien)
3. `ServicePipeline` ersetzt schrittweise den `CoordinatorAgent`
4. `ValidationEngine` laeuft zusaetzlich zu bestehenden Checks
5. Alte Pipeline bleibt als Fallback erhalten bis neue Pipeline stabiler ist

---

## 9. Success Criteria

| Criterion | Target |
|-----------|--------|
| Endpoint Coverage | 418/418 (100%) |
| Entity Coverage | 48/48 (100%) |
| Build Success | Jeder Service baut einzeln |
| Test Stubs | Jeder Endpoint hat mindestens einen Test |
| Validation Score | > 85/100 pro Service |
| Token Efficiency | < 12.000 Tokens pro Agent-Call |
| Traceability | 126/126 Requirements getracked |
| Single-Service Run | < 5 min pro Service |

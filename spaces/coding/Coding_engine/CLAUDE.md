# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## For Claude Code - Read This First

When starting work on this codebase:

1. **Understand the Architecture** - This is a "Society of Mind" system with 37+ autonomous agents communicating via events.
2. **Key files to review:**
   - `src/mind/event_bus.py` - EventBus pub/sub system (all agent communication)
   - `src/mind/orchestrator.py` - Agent lifecycle and convergence loop
   - `src/agents/autonomous_base.py` - Base class for all autonomous agents
   - `src/engine/hybrid_pipeline.py` - Core code generation pipeline

3. **Key concepts:**
   - **EventBus**: Agents publish/subscribe to events (BUILD_FAILED, CODE_FIXED, etc.)
   - **Push Architecture**: Events delivered via async queues (not polling)
   - **Convergence**: System iterates until metrics meet criteria
   - **SharedState**: Agents share metrics via SharedState singleton
   - **Document Registry**: Agents communicate via typed documents
   - **Skills**: Specialized instruction sets for agent tasks
   - **No-Mocks Policy**: All tests must use real integrations

4. **When adding new agents:**
   - Extend `AutonomousAgent` from `src/agents/autonomous_base.py`
   - Define `subscribed_events` property
   - Implement `should_act()` and `act()` methods
   - Register in `src/mind/orchestrator.py`

## Project Overview

**Name:** Coding Engine
**Type:** Python (Autonomous Code Generation System)
**Description:** A "Society of Mind" autonomous code generation system that generates complete production-ready projects from JSON requirements using 37+ specialized AI agents.

## Commands

```bash
# Run Full Autonomous Generation
python run_society_hybrid.py requirements.json --output-dir ./output

# Fast Mode (minimal iterations)
python run_society_hybrid.py requirements.json --output-dir ./output --fast

# Autonomous Mode (runs until 100% complete)
python run_society_hybrid.py requirements.json --autonomous

# Run Basic Hybrid Pipeline
python run_hybrid.py requirements.json --output-dir ./output

# Install Dependencies
pip install -r requirements.txt

# Run Tests
pytest

# Run specific test file
pytest tests/mind/test_push_architecture.py -v

# Run tests by marker
pytest -m e2e          # End-to-end tests
pytest -m integration  # Integration tests
```

---

## System Architecture Overview (3 Layers)

```
┌──────────────────────────────────────────────────────────────────────┐
│  ENTRY POINTS                                                        │
│  run_society_hybrid.py  → Layer 1 (Society of Mind pipeline)         │
│  run_epic001_live.py    → Layer 2+3 (Epic Orchestrator pipeline)     │
│  run_differential_pipeline.py → Differential Analysis→Fix→Verify     │
└────────────────────┬─────────────────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 1: Code Generation Pipeline (37+ Agents)                      │
│                                                                      │
│  Skills (12)           Engine (6-phase)        Agents (37+)          │
│  .claude/skills/       src/engine/             src/agents/           │
│  SKILL.md files        hybrid_pipeline.py      autonomous_base.py   │
│                        slicer.py, merger.py    + 31 specialized      │
│                                                                      │
│  EventBus (push)       SharedState             Convergence Loop      │
│  src/mind/event_bus    src/mind/shared_state   src/mind/orchestrator │
└────────────────────┬─────────────────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 2: MCP Orchestrator (55+ Tools)                               │
│                                                                      │
│  EventFixOrchestrator          AutoGen 0.4+ Teams                    │
│  autogen_orchestrator.py       RoundRobinGroupChat                   │
│  - ReasoningAgent (tools)      (1 fresh team per parallel task)      │
│  - ValidatorAgent (review)     autogen-agentchat 0.7.5               │
│  - FixSuggestionAgent                                                │
│                                                                      │
│  Epic Orchestrator             TaskExecutor                          │
│  epic_orchestrator.py          task_executor.py                      │
│  - Parallel pipeline           - Routes to Claude CLI or AutoGen     │
│  - File-conflict scheduling    - Fail-forward (skip_failed_deps)     │
│  - SoM Bridge integration      - Differential Analysis trigger       │
│                                                                      │
│  Differential Pipeline         Cross-Layer Validation                │
│  DifferentialAnalysisAgent     CrossLayerValidationAgent             │
│  DifferentialFixAgent          (FE<>BE consistency, static)          │
│  MCPAgentPool routing                                                │
└────────────────────┬─────────────────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 3: MCP Plugin Agents (20+ Servers)                            │
│                                                                      │
│  mcp_plugins/servers/          Each server has:                      │
│  filesystem/ playwright/       - agent.py (AutoGen tool adapter)     │
│  docker/ redis/ github/        - MCP protocol (stdio/SSE)            │
│  prisma/ npm/ postgres/        - Tool definitions                    │
│  brave-search/ fetch/                                                │
│  supabase/ memory/ n8n/        Fungus Stack (RAG validation):        │
│  context7/ tavily/ time/       - FungusValidationAgent               │
│  claude-code/ git/             - FungusMemoryAgent                   │
│  windows-core/ desktop/        - FungusContextAgent                  │
│  qdrant/ supermemory/          - la_fungus_search/ (submodule)       │
└────────────────────┬─────────────────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  OUTPUT                                                              │
│  Complete production-ready project with:                             │
│  - TypeScript/NestJS code    - Database schemas (Prisma)             │
│  - REST APIs with auth       - Real integration tests                │
│  - Docker configs            - CI/CD pipelines                       │
│  - Differential validation   - Cross-layer consistency checks        │
└──────────────────────────────────────────────────────────────────────┘
```

> **Layer status**: Layer 1 runs standalone via `run_society_hybrid.py`. Layers 2+3 run via `run_epic001_live.py` (Epic Orchestrator). Connection of Layer 1 events into Layer 2+3 is via SoM Bridge (`som_bridge.py`).

---

## Source Directory Structure

| Directory | Purpose |
|-----------|---------|
| `src/agents/` | 37+ autonomous AI agents |
| `src/mind/` | EventBus, SharedState, Orchestrator |
| `src/engine/` | HybridPipeline, Slicer, Merger, Contracts |
| `src/tools/` | 20+ execution tools (Claude CLI, sandbox, etc.) |
| `src/validators/` | Build, TypeScript, NoMock validators |
| `src/monitoring/` | ClaudeMonitor, CLITracker, dashboards |
| `src/security/` | Prompt injection, secrets, supply chain |
| `src/colony/` | Distributed cell architecture (K8s) |
| `src/api/` | FastAPI REST/WebSocket API |
| `src/scaffolding/` | Project structure initialization |
| `src/registry/` | Document Registry for inter-agent communication |
| `.claude/skills/` | 12 skill definitions |
| `infra/docker/` | Docker/K8s configurations |
| `dashboard-app/` | Electron/React dashboard |

### Entry Points

- `run_society_hybrid.py` - Main entry point for full autonomous generation
- `run_hybrid.py` - Basic hybrid pipeline runner
- `run_job.py` - Single job execution
- `src/api/main.py` - FastAPI server

---

## Skills System (12 Skills)

Skills provide specialized instructions for autonomous agents. Located in `.claude/skills/{skill-name}/SKILL.md`.

| Skill | Agent | Purpose | Trigger Events |
|-------|-------|---------|----------------|
| **code-generation** | GeneratorAgent | Generate/fix TypeScript/React code | BUILD_FAILED, CODE_FIX_NEEDED, E2E_TEST_FAILED, UX_ISSUE_FOUND |
| **test-generation** | ValidationTeamAgent | Create Vitest/Jest test suites (NO MOCKS) | GENERATION_COMPLETE, BUILD_SUCCEEDED |
| **chunk-planning** | ChunkPlannerAgent | Plan parallel code generation | REQUIREMENTS_LOADED, PLANNING_REQUESTED |
| **database-schema-generation** | DatabaseAgent | Generate Prisma/SQLAlchemy schemas | CONTRACTS_GENERATED, SCHEMA_UPDATE_NEEDED |
| **api-generation** | APIAgent | Generate REST APIs from contracts | CONTRACTS_GENERATED, DATABASE_SCHEMA_GENERATED |
| **auth-setup** | AuthAgent | Implement JWT/OAuth2/RBAC | CONTRACTS_GENERATED, AUTH_REQUIRED |
| **environment-config** | InfrastructureAgent | Generate .env, Docker, CI/CD | PROJECT_SCAFFOLDED, DATABASE_SCHEMA_GENERATED |
| **docker-sandbox** | DeploymentTeamAgent | Manage Docker containers with VNC | BUILD_SUCCEEDED, CODE_FIXED |
| **e2e-testing** | TesterTeamAgent | Execute Playwright browser tests | DEPLOY_SUCCEEDED, APP_LAUNCHED |
| **ux-review** | UXDesignAgent | Analyze UI with Claude Vision | E2E_SCREENSHOT_TAKEN, APP_LAUNCHED |
| **debugging** | ContinuousDebugAgent | Trace build/runtime errors | BUILD_FAILED, SANDBOX_TEST_FAILED |
| **validation** | ValidationTeamAgent | Multi-Agent Debate verification | TEST_PASSED, E2E_TEST_PASSED |

### Tier-Based Skill Loading (v2.0)

Skills support 3-tier progressive loading for token efficiency:

| Tier | Tokens | Content | Use Case |
|------|--------|---------|----------|
| Minimal | ~200 | Trigger events + critical rules | Single type error, import fix |
| Standard | ~800 | + Workflow + error patterns | Multi-file fix, component creation |
| Full | ~1600 | + Code examples | New feature, architecture change |

**Tier Markers in SKILL.md:**
```markdown
<!-- END_TIER_MINIMAL -->
<!-- END_TIER_STANDARD -->
```

**Automatic Tier Selection:**
- `ComplexityDetector` analyzes prompt, error count, file scope
- Simple errors → minimal tier (87% token savings)
- Medium tasks → standard tier (50% token savings)
- Complex features → full tier (full context needed)

**Key Files:**
- `src/skills/skill.py` - `get_tier_content()`, `get_tier_prompt()`, `has_tier_support()`
- `src/skills/loader.py` - `_parse_tier_boundaries()` extracts markers
- `src/utils/complexity_detector.py` - `detect_complexity()` determines tier
- `src/tools/claude_code_tool.py` - `skill_tier` parameter for override

### Critical Policies (Enforced in All Skills)

1. **NO MOCKS**: Real integration tests, real database connections, real HTTP
2. **Admin Seeding**: Auth must generate admin user at startup
3. **Permission Checking**: Direct permission checks, not just role-based
4. **No TODOs**: Production-ready code only

---

## Agents (~29 Aktiv von 57 Definierten)

> **Hinweis:** Von 57 definierten Agent-Klassen werden ~29 tatsächlich instantiiert. Viele sind feature-flag-gesteuert oder legacy/geplant.

### Core Agents - Immer Aktiv (Built into autonomous_base.py)

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **BuilderAgent** | FILE_CREATED, FILE_MODIFIED, CODE_FIXED | BUILD_SUCCEEDED, BUILD_FAILED | Runs build command |
| **TesterAgent** | BUILD_SUCCEEDED, CODE_GENERATED | TEST_SUITE_COMPLETE | Runs test suite |
| **ValidatorAgent** | BUILD_SUCCEEDED, CODE_GENERATED | TYPE_CHECK_PASSED, TYPE_ERROR | TypeScript checking |
| **FixerAgent** | TEST_FAILED, BUILD_FAILED, TYPE_ERROR | CODE_FIXED, FILE_CREATED | Error recovery |

### Code Generation & Fixing

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **GeneratorAgent** | CODE_FIX_NEEDED, BUILD_FAILED, DEBUG_REPORT_CREATED, UX_ISSUE_FOUND | CODE_GENERATED, CODE_FIXED, IMPLEMENTATION_PLAN_CREATED | Main code generation with Claude |
| **BugFixerAgent** | VALIDATION_ERROR, BROWSER_ERROR | CODE_FIXED | Code-level bug fixing |

### E2E Testing & Quality

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **TesterTeamAgent** | BUILD_SUCCEEDED, APP_LAUNCHED, E2E_TEST_FAILED | E2E_TEST_PASSED/FAILED, TEST_SPEC_CREATED | E2E testing with Playwright |
| **PlaywrightE2EAgent** | DEPLOY_SUCCEEDED | PLAYWRIGHT_E2E_*, DEBUG_REPORT_CREATED | Visual E2E with Claude Vision |
| **ValidationTeamAgent** | GENERATION_COMPLETE, BUILD_SUCCEEDED | TESTS_PASSED/FAILED, MOCK_DETECTED | NoMock validation + test gen |
| **CodeQualityAgent** | TEST_SPEC_CREATED | QUALITY_REPORT_CREATED, CODE_FIX_NEEDED | Cleanup, refactoring analysis |
| **ContinuousE2EAgent** | PREVIEW_READY, BUILD_SUCCEEDED | E2E_TEST_* | Periodic E2E during generation |
| **E2EIntegrationTeamAgent** | BUILD_SUCCEEDED, DEPLOY_SUCCEEDED | CRUD_TEST_* | CRUD endpoint verification |
| **RequirementsPlaywrightAgent** | BUILD_SUCCEEDED, DEPLOY_SUCCEEDED | Requirements verification | LLM-guided E2E testing |

### Deployment & Debugging

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **DeploymentTeamAgent** | BUILD_SUCCEEDED, CODE_FIXED | SANDBOX_TEST_*, DEPLOY_SUCCEEDED, SCREEN_STREAM_* | Docker sandbox + VNC streaming |
| **ContinuousDebugAgent** | SANDBOX_TEST_FAILED, BUILD_FAILED, SCREEN_STREAM_READY | DEBUG_STARTED/COMPLETE | Real-time debugging with hot reload |
| **DeployAgent** | Various | DEPLOY_SUCCEEDED, DEPLOY_LOGS_COLLECTED | Deploy and collect logs |
| **RuntimeDebugAgent** | Various | Runtime events | Automatic runtime debugging |

### UX & Documentation

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **UXDesignAgent** | E2E_SCREENSHOT_TAKEN | UX_ISSUE_FOUND, UX_RECOMMENDATION | Claude Vision UI analysis |
| **DocumentationAgent** | BUILD_SUCCEEDED, TEST_SUITE_COMPLETE | DOCS_GENERATED, DOCS_UPDATED | Auto-generates CLAUDE.md |

### Backend Generation Chain

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **DatabaseAgent** | CONTRACTS_GENERATED | DATABASE_SCHEMA_GENERATED/FAILED | Prisma/SQLAlchemy schemas |
| **APIAgent** | DATABASE_SCHEMA_GENERATED | API_ROUTES_GENERATED/FAILED | REST API generation |
| **AuthAgent** | API_ROUTES_GENERATED | AUTH_SETUP_COMPLETE/FAILED | JWT/OAuth2 + RBAC |
| **InfrastructureAgent** | AUTH_SETUP_COMPLETE | ENV_CONFIG_GENERATED, DOCKER_CONFIG_GENERATED | .env, Docker, CI/CD |
| **DatabaseSchemaAgent** | FILE_CREATED, GENERATION_COMPLETE | Migration events | Auto-migration |
| **DatabaseDockerAgent** | VALIDATION_ERROR | Container events | Auto-starts PostgreSQL |

### Security & Dependencies

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **SecurityScannerAgent** | BUILD_SUCCEEDED, GENERATION_COMPLETE | Security scan results | npm audit, pip audit, secrets |
| **DependencyManagerAgent** | PROJECT_SCAFFOLDED, DEPENDENCY_VULNERABILITY | Dependency events | Package management |

### UI Integration

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **UIIntegrationAgent** | FILE_CREATED, CODE_GENERATED | Component integration | Auto-imports to App.tsx |
| **BrowserConsoleAgent** | DEPLOY_SUCCEEDED, APP_LAUNCHED | BROWSER_ERROR, BROWSER_CONSOLE_ERROR | Console error detection |

### Performance & Accessibility

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **PerformanceAgent** | BUILD_SUCCEEDED, E2E_TEST_PASSED | Performance reports | Lighthouse, bundle optimization |
| **AccessibilityAgent** | E2E_TEST_PASSED, UX_REVIEW_PASSED | Accessibility reports | WCAG compliance (Axe Core) |

### Documentation & Localization

| Agent | Subscribed Events | Publishes | Purpose |
|-------|-------------------|-----------|---------|
| **APIDocumentationAgent** | API_ROUTES_GENERATED | OpenAPI/Swagger | API docs generation |
| **MigrationAgent** | DATABASE_SCHEMA_GENERATED | Migration events | DB migration execution |
| **LocalizationAgent** | CONTRACTS_GENERATED | i18n events | Internationalization setup |

### Specialized Agents

| Agent | Status | Purpose |
|-------|--------|---------|
| **ArchitectAgent** | Aktiv | TypeScript contract generation from requirements |
| **CoordinatorAgent** | Aktiv | Multi-agent coordination |
| **BrowserConsoleAgent** | Aktiv | Real-time browser console error detection |
| **ValidationRecoveryAgent** | Aktiv | Automatic validation failure recovery |
| **EventInterpreterAgent** | Optional (`--enable-event-interpreter`) | Intelligent event routing |
| **ChunkPlannerAgent** | Nicht Aktiv | Parallel execution planning |
| **DevContainerAgent** | Nicht Aktiv | Dev container lifecycle |
| **FrontendValidatorAgent** | Optional (`--enable-frontend-validation`) | UI validation via Playwright |

### Nicht Instantiierte Agents (Legacy/Geplant)

Die folgenden Agents sind definiert aber werden nicht in der aktiven Pipeline verwendet:
- BackendAgent, FrontendAgent, TestingAgent, SecurityAgent
- DevOpsAgent, RecoveryAgent, PreviewAgent, RuntimeTestAgent
- DockerSecretsTeam, EnvironmentReportAgent, VerificationDebateAgent
- DockerOrchestratorAgent, GordonBuildAgent, DeployTestTeam

---

## Tools System (20+ Tools)

Located in `src/tools/`:

### Core Tools

| Tool | Purpose |
|------|---------|
| **claude_code_tool.py** | Wraps Claude CLI/Agent SDK for code generation with skill-aware prompts |
| **claude_agent_tool.py** | Claude Agent SDK integration (primary) with CLI fallback |
| **test_runner_tool.py** | Runs Vitest/Jest tests, captures coverage |
| **sandbox_tool.py** | Manages Docker containers, executes tests in isolation |
| **deploy_tool.py** | Orchestrates deployment workflows |
| **project_validator_tool.py** | Validates generated projects against requirements |
| **vision_analysis_tool.py** | Claude Vision integration for UI/UX analysis |

### Integration Tools

| Tool | Purpose |
|------|---------|
| **supermemory_tools.py** | Batch context loading for parallel agents |
| **component_tree_tool.py** | Analyzes React component hierarchy |
| **crud_endpoint_detector.py** | Detects and validates CRUD endpoints |
| **api_verification_tool.py** | Validates API correctness |
| **completeness_checker.py** | Verifies requirement implementation |

### Infrastructure Tools

| Tool | Purpose |
|------|---------|
| **docker_swarm_tool.py** | Manages multiple container instances |
| **microservice_orchestrator.py** | Coordinates microservice deployment |
| **dev_container_tool.py** | Dev container lifecycle management |
| **file_lock_manager.py** | Prevents race conditions in file operations |

### Other Tools

| Tool | Purpose |
|------|---------|
| **memory_tool.py** | Agent memory and context management |
| **ollama_tool.py** | Local LLM integration |
| **cloud_test_tool.py** | Cloud-based testing infrastructure |

---

## Engine System (6-Phase Pipeline)

Located in `src/engine/`:

### Pipeline Phases

1. **Architecture Analysis** - Generate TypeScript contracts from requirements
2. **Parallel Code Generation** - Slice requirements, generate in parallel
3. **Merge & Validate** - Merge chunks, run validators
4. **Test & Debug** - Run tests, debug failures
5. **Deploy & E2E** - Docker sandbox, Playwright E2E
6. **Full Validation** - Multi-agent debate verification

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **HybridPipeline** | `hybrid_pipeline.py` | Main 6-phase orchestration |
| **Slicer** | `slicer.py` | Domain-based parallel chunking |
| **Merger** | `merger.py` | Merge sliced outputs |
| **Contracts** | `contracts.py` | TypeScript interface generation |
| **ProjectAnalyzer** | `project_analyzer.py` | Tech stack detection |
| **PlanningEngine** | `planning_engine.py` | Execution planning |
| **ExecutionPlan** | `execution_plan.py` | Chunk/wave/worker assignments |
| **CheckpointManager** | `checkpoint_manager.py` | Resume capability |
| **RateLimiter** | `rate_limit_handler.py` | API rate limit management |

---

## Validators System

Located in `src/validators/`:

| Validator | Purpose |
|-----------|---------|
| **BaseValidator** | Abstract interface, structured failure reporting |
| **BuildValidator** | npm/vite build success checking |
| **TypeScriptValidator** | TypeScript type checking |
| **ElectronValidator** | Electron app specific validation |
| **RuntimeValidator** | Runtime error detection |
| **NoMockValidator** | **CRITICAL**: Rejects all mocking patterns |
| **CompletenessValidator** | Verifies requirements implementation |

### ValidationFailure Format

```python
ValidationFailure(
    check_type="typescript",
    error_message="Property 'x' does not exist",
    severity="ERROR",
    file_path="src/App.tsx",
    line_number=42,
    error_code="TS2339",
    suggested_fix="Add 'x' to interface",
    related_files=["src/types.ts"]
)
```

---

## Push Architecture (v2.0)

The system uses push-based event delivery instead of polling:

- **Async Queues**: Each agent has an `asyncio.Queue` for receiving events
- **Event Batching**: Events batched within 0.5s windows for efficiency
- **Idle Detection**: Convergence checked only when system is idle
- **Queue Timeout**: 5.0 seconds between checks

---

## Event Types (Complete)

**File:** FILE_CREATED, FILE_MODIFIED, FILE_DELETED
**Code:** CODE_GENERATED, CODE_FIXED, CODE_FIX_NEEDED, GENERATION_COMPLETE, GENERATION_REQUESTED
**Build:** BUILD_STARTED, BUILD_SUCCEEDED, BUILD_FAILED, BUILD_COMPLETED
**Test:** TEST_STARTED, TEST_PASSED, TEST_FAILED, TEST_SUITE_COMPLETE, TEST_SPEC_CREATED
**E2E:** E2E_TEST_PASSED, E2E_TEST_FAILED, E2E_SCREENSHOT_TAKEN, APP_LAUNCHED, APP_CRASHED
**Sandbox:** SANDBOX_TEST_STARTED, SANDBOX_TEST_PASSED, SANDBOX_TEST_FAILED, SANDBOX_LOGS_COLLECTED
**Deployment:** DEPLOY_STARTED, DEPLOY_SUCCEEDED, DEPLOY_FAILED, DEPLOY_LOGS_COLLECTED
**VNC:** SCREEN_STREAM_STARTED, SCREEN_STREAM_READY, SCREEN_STREAM_ERROR, SERVER_PORT_DETECTED
**Quality:** QUALITY_REPORT_CREATED, DEBUG_REPORT_CREATED, IMPLEMENTATION_PLAN_CREATED
**Validation:** TYPE_ERROR, TYPE_CHECK_PASSED, VALIDATION_ERROR, MOCK_DETECTED
**CRUD:** CRUD_ENDPOINT_DETECTED, CRUD_TEST_PASSED, CRUD_TEST_FAILED, INTEGRATION_ERROR
**Browser:** BROWSER_ERROR, BROWSER_CONSOLE_ERROR, BROWSER_NETWORK_ERROR
**UX:** UX_REVIEW_STARTED, UX_REVIEW_PASSED, UX_ISSUE_FOUND, UX_RECOMMENDATION
**Docs:** DOCS_GENERATION_STARTED, DOCS_GENERATED, DOCS_UPDATED
**Agent:** AGENT_STARTED, AGENT_ACTING, AGENT_COMPLETED, AGENT_ERROR
**Document:** DOCUMENT_CREATED, DOCUMENT_CONSUMED, DOCUMENT_ARCHIVED
**System:** CONVERGENCE_UPDATE, CONVERGENCE_ACHIEVED, PREVIEW_READY, SYSTEM_READY, SYSTEM_ERROR
**Review:** REVIEW_PAUSE_REQUESTED, REVIEW_PAUSED, REVIEW_FEEDBACK_SUBMITTED, REVIEW_RESUME_REQUESTED, REVIEW_RESUMED
**Recovery:** RECOVERY_STARTED, RECOVERY_COMPLETE, RECOVERY_FAILED
**Database:** DATABASE_SCHEMA_GENERATED, DATABASE_SCHEMA_FAILED, CONTRACTS_GENERATED
**API:** API_ROUTES_GENERATED, API_GENERATION_FAILED, API_ENDPOINT_CREATED
**Auth:** AUTH_SETUP_COMPLETE, AUTH_SETUP_FAILED, AUTH_REQUIRED
**Infra:** ENV_CONFIG_GENERATED, DOCKER_CONFIG_GENERATED, CI_CONFIG_GENERATED

---

## Document Registry (Inter-Agent Communication)

Agents communicate structured data via typed documents:

| Document | Producer | Consumer | Purpose |
|----------|----------|----------|---------|
| `ImplementationPlan` | GeneratorAgent | ValidationTeamAgent | Fix strategy |
| `TestSpec` | TesterTeamAgent | CodeQualityAgent | Test specifications |
| `QualityReport` | CodeQualityAgent | GeneratorAgent | Refactoring suggestions |
| `DebugReport` | PlaywrightE2EAgent | GeneratorAgent | Visual/functional issues |
| `UXReport` | UXDesignAgent | GeneratorAgent | UI/UX improvements |

**Document Lifecycle:** `CREATED` → `PENDING` → `IN_PROGRESS` → `CONSUMED` → `ARCHIVED`

**Storage Structure:**
```
output_dir/
  reports/
    debug/           # DebugReport JSON files
    implementation/  # ImplementationPlan JSON files
    tests/           # TestSpec JSON files
    quality/         # QualityReport JSON files
    archive/         # Expired documents (24h TTL)
  .registry/
    index.json       # Central document index
```

---

## Monitoring System

Located in `src/monitoring/`:

| Component | Status | Purpose |
|-----------|--------|---------|
| **ClaudeMonitor** | Optional (`--enable-monitor`) | AI-powered error analysis using Claude API |
| **CLITracker** | Nicht Aktiv | Tracks Claude CLI calls (tokens, latency, success) |
| **PreviewMonitor** | Aktiv | Monitors live preview server health |
| **ConsoleDashboard** | Aktiv | Real-time agent activity dashboard |
| **BrowserErrorDetector** | Aktiv | Detects console errors in running apps |

---

## Security System (Geplant - Nicht Aktiv)

Located in `src/security/`:

> **Status:** Infrastruktur vorhanden, aber noch nicht in die Generation-Pipeline integriert. Diese Module sind für zukünftige Nutzung vorbereitet.

| Component | Purpose |
|-----------|---------|
| **llm_security.py** | Prompt injection detection, dangerous patterns, secret exposure |
| **supply_chain.py** | Dependency vulnerability scanning |
| **vault_client.py** | Secrets management integration |
| **runtime_security.py** | Runtime sandboxing and isolation |

**Security Finding Types:**
- PROMPT_INJECTION, DANGEROUS_IMPORT, SHELL_COMMAND
- SECRET_EXPOSURE, NETWORK_ACCESS, FILE_SYSTEM_ACCESS
- CODE_EXECUTION, MALICIOUS_PATTERN, UNSAFE_DESERIALIZATION

---

## Colony System (Geplant - Nicht Aktiv)

Located in `src/colony/`:

> **Status:** API-Endpoints existieren, aber nicht in der aktiven Generation-Pipeline integriert. Infrastruktur für zukünftige Multi-Projekt-Orchestrierung.

Enterprise-scale multi-project management with Kubernetes integration.

**Cell**: Self-contained autonomous microservice project
- Isolated container with resource limits
- Health checks and metrics
- Can mutate, recover, or terminate autonomously

**Cell Lifecycle:**
```
PENDING → INITIALIZING → BUILDING → DEPLOYING → HEALTHY
HEALTHY ↔ DEGRADED ↔ RECOVERING
Any → TERMINATING → TERMINATED
```

**Key Components:**
- **Cell** - Core dataclass for microservice unit
- **CellAgent** - Autonomous agent managing a cell
- **ColonyManager** - Orchestrates multiple cells
- **LifecycleController** - State transitions
- **SecurityGateway** - Security policy enforcement

**Kubernetes Integration** (`src/colony/k8s/`):
- kubectl_tool.py - Execute kubectl commands
- operator.py - K8s operator for cell lifecycle
- resource_generator.py - Generate K8s YAML

---

## API Routes

Located in `src/api/routes/`:

| Route | Purpose |
|-------|---------|
| **dashboard.py** | Generation status, pause/resume, metrics |
| **vision.py** | Claude Vision UI feedback analysis |
| **colony.py** | Cell management API |
| **portal/** | Portal/tenant management |

### Dashboard Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/dashboard/generation/{id}/pause` | POST | Pause generation |
| `/api/v1/dashboard/generation/{id}/resume` | POST | Resume with feedback |
| `/api/v1/dashboard/generation/{id}/review-status` | GET | Get pause status |
| `/api/v1/vision/analyze-ui-feedback` | POST | Analyze screenshot |

---

## Review Gate (User Feedback During Generation)

The system supports pausing generation for manual user review:

- **Pause**: User clicks "Pause for Review" → Generation halts at next checkpoint
- **Chat Feedback**: User describes issues via chat interface
- **Vision Analysis**: Claude Vision analyzes VNC screenshots with user feedback
- **Resume**: User clicks "Continue" → Generation resumes with feedback context

### SharedState Methods

- `pause_for_review()` - Block agents at checkpoint
- `resume_from_review(feedback)` - Unblock with feedback context
- `get_review_status()` - Check pause state

---

## Docker Infrastructure

Located in `infra/docker/`:

| File | Purpose |
|------|---------|
| `docker-compose.customer-deploy.yml` | Live deployment with hot reload |
| `docker-compose.validation.yml` | Port-isolated validation (3100/8100) |
| `Dockerfile.sandbox` | Universal sandbox with VNC support |
| `Dockerfile.validation` | Multi-stage (React + FastAPI) |
| `sandbox-entrypoint.sh` | Auto-detects project type (electron, react, node, python) |

### VNC Streaming

- **Xvfb**: Virtual display (:99)
- **x11vnc**: VNC server (port 5900)
- **noVNC**: Web client (port 6080)
- Dashboard streams to http://localhost:6080/vnc.html

---

## Dashboard Application

Located in `dashboard-app/`:

### Key Components

| Component | Purpose |
|-----------|---------|
| `src/main/main.ts` | Electron main process, IPC handlers |
| `src/main/docker-manager.ts` | Docker container lifecycle, VNC streaming |
| `src/main/port-allocator.ts` | Dynamic port allocation |
| `src/renderer/components/LivePreview/VNCViewer.tsx` | VNC iframe with health check |
| `src/renderer/components/ReviewChat/ReviewChat.tsx` | Chat UI for Review Gate |
| `src/renderer/components/ProjectSpace/ProjectSpace.tsx` | Generation workspace |
| `src/renderer/stores/projectStore.ts` | Zustand state management |
| `src/renderer/api/visionAPI.ts` | Vision API client |

### Running the Dashboard

```bash
cd dashboard-app
npm install
npm run build
npm run dev        # Development mode
```

### Windows/Git Bash Notes

- Linux paths in Docker commands use `//` prefix to prevent Git Bash mangling
- Example: `//usr/local/bin/sandbox-entrypoint.sh` instead of `/usr/local/bin/...`

---

## Testing

```bash
pytest                                    # Run all tests
pytest tests/mind/ -v                     # Test push architecture
pytest tests/orchestrator/ -v             # Test orchestrator phases
pytest -m e2e                             # End-to-end tests only
pytest -m integration                     # Integration tests only
```

Test organization:

| Directory | Purpose |
|-----------|---------|
| `tests/mind/` | Society of Mind architecture tests |
| `tests/orchestrator/` | Phase-based orchestrator tests |
| `tests/teams/` | Team-specific tests (ValidationTeam, etc.) |
| `tests/agents/` | Individual agent tests |
| `tests/integration/` | Integration tests |
| `tests/security/` | Security tests |
| `tests/colony/` | Colony/cell tests |
| `tests/e2e/` | End-to-end pipeline tests |

---

## Convergence Criteria

| Mode | Purpose |
|------|---------|
| `DEFAULT_CRITERIA` | Standard thresholds |
| `STRICT_CRITERIA` | 100% test pass, 0 type errors |
| `RELAXED_CRITERIA` | Quick iterations |
| `FAST_ITERATION_CRITERIA` | Minimal checks |
| `AUTONOMOUS_CRITERIA` | Full autonomous with completeness checks |

---

## Requirements JSON Format

```json
{
  "name": "project-name",
  "type": "electron",
  "description": "Project description",
  "features": [
    {
      "id": "feature_1",
      "name": "Feature Name",
      "description": "What it does",
      "priority": "high"
    }
  ]
}
```

---

## CLI Flags

| Flag | Description |
|------|-------------|
| `--output-dir` | Output directory for generated project |
| `--fast` | Use fast iteration criteria |
| `--strict` | Use strict convergence criteria |
| `--autonomous` | Run until 100% complete |
| `--no-preview` | Disable live preview server |
| `--no-install` | Skip npm install |
| `--no-docs` | Disable auto-generation of CLAUDE.md |
| `--max-iterations` | Maximum convergence iterations |
| `--preview-port` | Port for dev server (default: 5173) |

---

## Key Dependencies

- `anthropic` - Claude API SDK
- `autogen-agentchat` - Multi-agent orchestration (AutoGen 0.4+)
- `fastapi` - REST/WebSocket API
- `structlog` - Structured logging
- `networkx` - DAG operations for task scheduling
- `docker` - Docker SDK for container management
- `playwright` - Browser automation for E2E testing

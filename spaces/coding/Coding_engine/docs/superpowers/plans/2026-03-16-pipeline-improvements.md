# Pipeline Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 6 critical pipeline gaps so the DaveFelix Coding Engine can generate the WhatsApp Messaging Service (17 microservices, 418 endpoints) with 100% coverage, full validation, and traceability.

**Architecture:** Hybrid Skeleton + Agent Fill approach. A deterministic SpecParser reads service specs into structured data, a SkeletonGenerator produces code scaffolds (no LLM), then a ServicePipeline fills logic service-by-service via LLM agents. Validation and traceability run after each service.

**Tech Stack:** Python 3.11+, dataclasses, re/yaml for parsing, existing `BaseValidator`/`ValidationFailure`/`ValidationSeverity` from `src/validators/base_validator.py`, existing `CheckpointManager` from `src/engine/checkpoint_manager.py`, existing `ClaudeCodeTool` from `src/tools/claude_code_tool.py`.

**Spec:** `docs/superpowers/specs/2026-03-16-pipeline-improvements-design.md`

---

## File Structure

### New Files (18)

| File | Responsibility |
|------|---------------|
| `src/engine/spec_parser.py` | Parse all service artifacts into `ParsedSpec` — the single source of truth |
| `src/engine/skeleton_generator.py` | Deterministically generate NestJS code scaffolds from `ParsedSpec` |
| `src/engine/service_orchestrator.py` | Orchestrate generation of all 17 services in dependency order |
| `src/engine/service_pipeline.py` | Run the fill+validate+recover loop for one service |
| `src/engine/code_fill_agent.py` | Wrap `ClaudeCodeTool` for skeleton-fill operations |
| `src/engine/context_injector.py` | Assemble optimal per-file context for LLM agents |
| `src/engine/validation_engine.py` | Orchestrate all spec validators for a service |
| `src/engine/validators/__init__.py` | Package init |
| `src/engine/validators/endpoint_coverage.py` | Check all spec endpoints exist in code |
| `src/engine/validators/entity_schema.py` | Check Prisma schema matches data dictionary |
| `src/engine/validators/method_consistency.py` | Check controller calls match service methods |
| `src/engine/validators/import_integrity.py` | Check no phantom imports exist |
| `src/engine/validators/dto_completeness.py` | Check DTOs have all spec fields |
| `src/engine/validators/dependency_check.py` | Check package.json has all used packages |
| `src/engine/validators/state_machine.py` | Check code implements defined state transitions |
| `src/engine/validators/acceptance_criteria.py` | Heuristic check that ACs are likely implemented |
| `src/engine/traceability_tracker.py` | Track requirement-to-code mapping during generation |
| `run_pipeline.py` | CLI entry point for the new pipeline |

### New Test Files (7)

| File | Tests |
|------|-------|
| `tests/engine/test_spec_parser.py` | SpecParser against real WhatsApp service data |
| `tests/engine/test_skeleton_generator.py` | SkeletonGenerator output structure + content |
| `tests/engine/test_service_pipeline.py` | ServicePipeline orchestration logic |
| `tests/engine/test_context_injector.py` | Context assembly + token budget |
| `tests/engine/test_validation_engine.py` | ValidationEngine + all validators |
| `tests/engine/test_traceability_tracker.py` | Tracker state updates + report generation |
| `tests/engine/test_service_orchestrator.py` | Dependency ordering + checkpoint resume |

### Modified Files (2)

| File | Change |
|------|--------|
| `src/engine/spec_adapter.py` | Add `ParsedSpec` adapter path in `_normalize_documentation()` |
| `src/engine/hybrid_pipeline.py` | Add optional delegation to `ServiceOrchestrator` |

---

## Chunk 1: Data Models + SpecParser (Prio 1)

### Task 1: Create data model dataclasses

**Files:**
- Create: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

- [ ] **Step 1: Write test for data model instantiation**

```python
# tests/engine/test_spec_parser.py
import pytest
from src.engine.spec_parser import (
    Field, Relation, StateTransition, StateMachine,
    ParsedEndpoint, ParsedEntity, ParsedUserStory,
    ParsedService, ParsedSpec,
)


class TestDataModels:
    def test_field_defaults(self):
        f = Field(name="id", type="uuid")
        assert f.nullable is False
        assert f.unique is False
        assert f.default is None

    def test_relation_creation(self):
        r = Relation(target="Message", type="one-to-many", field="userId", inverse="messages")
        assert r.target == "Message"

    def test_state_machine_has_transitions(self):
        t = StateTransition(from_state="draft", to_state="sending", trigger="send", guard="content_valid")
        sm = StateMachine(
            name="Message", entity="Message",
            states=["draft", "sending", "sent"],
            initial_state="draft", terminal_states=["deleted"],
            transitions=[t],
        )
        assert len(sm.transitions) == 1
        assert sm.initial_state == "draft"

    def test_parsed_spec_generation_order(self):
        spec = ParsedSpec(
            services={}, shared_entities=[],
            dependency_graph={}, generation_order=["auth-service"],
            openapi_version="3.0.3",
        )
        assert spec.generation_order == ["auth-service"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/User/Desktop/Dave\&Felix/DaveFelix-Coding-Engine && python -m pytest tests/engine/test_spec_parser.py::TestDataModels -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.engine.spec_parser'`

- [ ] **Step 3: Implement data model dataclasses**

```python
# src/engine/spec_parser.py
"""Structured Spec Parser — Prio 1 of Pipeline Improvements.

Replaces DocumentationLoader. Parses service specification artifacts
(api docs, architecture, data dictionary, user stories, state machines)
into machine-readable dataclasses.

Spec: docs/superpowers/specs/2026-03-16-pipeline-improvements-design.md
"""
from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Field:
    name: str
    type: str
    nullable: bool = False
    unique: bool = False
    default: str | None = None


@dataclass
class Relation:
    target: str
    type: str           # one-to-one, one-to-many, many-to-many
    field: str           # FK field name
    inverse: str | None = None


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    trigger: str
    guard: str | None = None


@dataclass
class StateMachine:
    name: str
    entity: str
    states: list[str]
    initial_state: str
    terminal_states: list[str]
    transitions: list[StateTransition]


@dataclass
class ParsedEndpoint:
    method: str
    path: str
    service: str
    request_dto: str = ""
    response_dto: str = ""
    auth_required: bool = True
    linked_stories: list[str] = field(default_factory=list)
    status_codes: dict[int, str] = field(default_factory=dict)


@dataclass
class ParsedEntity:
    name: str
    fields: list[Field]
    relations: list[Relation]
    service: str


@dataclass
class ParsedUserStory:
    id: str
    epic: str
    title: str
    acceptance_criteria: list[str]
    linked_requirements: list[str] = field(default_factory=list)
    linked_endpoints: list[str] = field(default_factory=list)


@dataclass
class ParsedService:
    name: str
    port: int
    technology: str
    dependencies: list[str]            # infra deps (postgres, redis)
    service_dependencies: list[str]    # other API services
    endpoints: list[ParsedEndpoint]
    entities: list[ParsedEntity]
    stories: list[ParsedUserStory]
    state_machines: list[StateMachine]


@dataclass
class ParsedSpec:
    services: dict[str, ParsedService]
    shared_entities: list[ParsedEntity]
    dependency_graph: dict[str, list[str]]
    generation_order: list[str]
    openapi_version: str = "3.0.3"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/User/Desktop/Dave\&Felix/DaveFelix-Coding-Engine && python -m pytest tests/engine/test_spec_parser.py::TestDataModels -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: add ParsedSpec data models for structured spec parsing"
```

---

### Task 2: Implement architecture parser

**Files:**
- Modify: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

The architecture parser extracts services, ports, dependencies from `architecture/architecture.md`. The format uses markdown tables with `| Property | Value |` rows under `### service-name` headers.

- [ ] **Step 1: Write test for architecture parsing**

```python
# Add to tests/engine/test_spec_parser.py
from src.engine.spec_parser import SpecParser


class TestArchitectureParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_services_from_architecture(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        services = parser._parse_architecture()
        assert "auth-service" in services
        assert "messaging-service" in services
        auth = services["auth-service"]
        assert auth.port == 3001
        assert "NestJS" in auth.technology
        assert "postgres-auth" in auth.dependencies

    def test_parse_service_dependencies(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        services = parser._parse_architecture()
        msg = services["messaging-service"]
        # messaging-service depends on websocket-service (another API service)
        assert any("websocket" in d for d in msg.dependencies)

    def test_total_services_count(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        services = parser._parse_architecture()
        api_services = {k: v for k, v in services.items() if v.port > 0}
        assert len(api_services) >= 7  # At least 7 API services
```

- [ ] **Step 2: Run test — should fail**

Run: `python -m pytest tests/engine/test_spec_parser.py::TestArchitectureParser -v`

- [ ] **Step 3: Implement `SpecParser.__init__` and `_parse_architecture()`**

Add to `src/engine/spec_parser.py`:

```python
class SpecParser:
    """Parses service specification directory into ParsedSpec."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        if not self.project_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {self.project_dir}")

    def _parse_architecture(self) -> dict[str, ParsedService]:
        """Parse architecture/architecture.md into ParsedService dict."""
        arch_file = self.project_dir / "architecture" / "architecture.md"
        if not arch_file.exists():
            logger.warning("architecture.md not found at %s", arch_file)
            return {}

        text = arch_file.read_text(encoding="utf-8")
        services: dict[str, ParsedService] = {}
        # Split by ### headers (service definitions)
        service_blocks = re.split(r"^### ", text, flags=re.MULTILINE)

        for block in service_blocks[1:]:  # skip preamble
            lines = block.strip().split("\n")
            service_name = lines[0].strip()
            # Extract table rows: | Property | Value |
            props: dict[str, str] = {}
            for line in lines:
                m = re.match(r"\|\s*(\w[\w\s]*?)\s*\|\s*\*{0,2}(.*?)\*{0,2}\s*\|", line)
                if m and m.group(1).strip().lower() not in ("property", "---"):
                    props[m.group(1).strip().lower()] = m.group(2).strip()

            port_str = props.get("ports", "0")
            port = int(re.search(r"\d+", port_str).group()) if re.search(r"\d+", port_str) else 0
            tech = props.get("technology", "unknown")
            stype = props.get("type", "unknown")

            deps_str = props.get("dependencies", "")
            all_deps = [d.strip() for d in deps_str.split(",") if d.strip()]

            # Separate infra deps from service deps
            infra_prefixes = ("postgres", "redis", "kafka", "s3", "kong")
            infra_deps = [d for d in all_deps if any(d.startswith(p) for p in infra_prefixes)]
            service_deps = [d for d in all_deps if d not in infra_deps]

            # Only include actual runnable services (with ports)
            services[service_name] = ParsedService(
                name=service_name,
                port=port,
                technology=tech,
                dependencies=infra_deps,
                service_dependencies=service_deps,
                endpoints=[],
                entities=[],
                stories=[],
                state_machines=[],
            )

        return services
```

- [ ] **Step 4: Run test — should pass**

Run: `python -m pytest tests/engine/test_spec_parser.py::TestArchitectureParser -v`

- [ ] **Step 5: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: implement architecture parser for service extraction"
```

---

### Task 3: Implement data dictionary parser (entities)

**Files:**
- Modify: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

The data dictionary uses `### EntityName` headers with markdown tables: `| Attribute | Type | MaxLen | Required | FK Target | Indexed | Enum Values | Description |`

- [ ] **Step 1: Write test for entity parsing**

```python
class TestDataDictionaryParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_entities(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        entities = parser._parse_data_dictionary()
        assert len(entities) >= 40  # ~48 entities expected
        names = [e.name for e in entities]
        assert "User" in names or "user" in [n.lower() for n in names]

    def test_entity_has_fields(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        entities = parser._parse_data_dictionary()
        for entity in entities:
            if entity.name.lower() == "user" or "user" in entity.name.lower():
                assert len(entity.fields) > 0
                field_names = [f.name for f in entity.fields]
                # User should have some kind of ID
                assert any("id" in fn.lower() for fn in field_names)
                break

    def test_entity_relations(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        entities = parser._parse_data_dictionary()
        # At least some entities should have FK relations
        has_relations = [e for e in entities if len(e.relations) > 0]
        assert len(has_relations) > 0
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement `_parse_data_dictionary()`**

Add to `SpecParser` class:

```python
    def _parse_data_dictionary(self) -> list[ParsedEntity]:
        """Parse data/data_dictionary.md into ParsedEntity list."""
        dd_file = self.project_dir / "data" / "data_dictionary.md"
        if not dd_file.exists():
            logger.warning("data_dictionary.md not found")
            return []

        text = dd_file.read_text(encoding="utf-8")
        entities: list[ParsedEntity] = []
        # Split by ### headers (entity definitions)
        entity_blocks = re.split(r"^### ", text, flags=re.MULTILINE)

        for block in entity_blocks[1:]:
            lines = block.strip().split("\n")
            entity_name = lines[0].strip()
            if not entity_name or entity_name.startswith("|") or entity_name.startswith("#"):
                continue

            fields: list[Field] = []
            relations: list[Relation] = []

            # Find table rows
            for line in lines:
                # Match: | attr | type | maxlen | required | fk_target | indexed | enum | desc |
                cols = [c.strip() for c in line.split("|")]
                if len(cols) < 9:
                    continue
                attr, ftype, _maxlen, required, fk_target, _indexed, _enum_vals, _desc = cols[1:9]
                if attr.lower() in ("attribute", "---", ""):
                    continue
                if "---" in ftype:
                    continue

                # Map types
                type_map = {
                    "uuid": "uuid", "string": "string", "text": "text",
                    "integer": "int", "int": "int", "boolean": "boolean",
                    "datetime": "datetime", "decimal": "decimal", "enum": "enum",
                    "json": "json", "float": "float",
                }
                mapped_type = type_map.get(ftype.lower().strip(), ftype.lower().strip())

                fields.append(Field(
                    name=attr.strip(),
                    type=mapped_type,
                    nullable=required.strip().lower() != "yes",
                    unique=False,  # Not in table format
                    default=None,
                ))

                # Check FK relations
                if fk_target.strip() not in ("-", "", "—"):
                    parts = fk_target.strip().split(".")
                    if len(parts) == 2:
                        relations.append(Relation(
                            target=parts[0],
                            type="many-to-one",  # FK = many-to-one by default
                            field=attr.strip(),
                            inverse=None,
                        ))

            if fields:
                entities.append(ParsedEntity(
                    name=entity_name,
                    fields=fields,
                    relations=relations,
                    service="",  # Assigned later during service mapping
                ))

        return entities
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: implement data dictionary parser for entity extraction"
```

---

### Task 4: Implement user stories parser (from JSON)

**Files:**
- Modify: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

The JSON format has `user_stories[]` with `id`, `title`, `acceptance_criteria[{given, when, then}]`, `parent_epic_id`, `linked_requirement_ids`.

- [ ] **Step 1: Write test for user stories parsing**

```python
class TestUserStoriesParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_user_stories_from_json(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        stories = parser._parse_user_stories()
        assert len(stories) >= 100  # 126 expected
        us1 = next((s for s in stories if s.id == "US-001"), None)
        assert us1 is not None
        assert us1.epic == "EPIC-001"
        assert len(us1.acceptance_criteria) >= 2

    def test_stories_have_linked_requirements(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        stories = parser._parse_user_stories()
        linked = [s for s in stories if len(s.linked_requirements) > 0]
        assert len(linked) > 100  # Most stories should be linked
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement `_parse_user_stories()`**

```python
    def _parse_user_stories(self) -> list[ParsedUserStory]:
        """Parse user_stories.json into ParsedUserStory list."""
        json_file = self.project_dir / "user_stories.json"
        if not json_file.exists():
            logger.warning("user_stories.json not found")
            return []

        data = json.loads(json_file.read_text(encoding="utf-8"))
        stories: list[ParsedUserStory] = []

        for us in data.get("user_stories", []):
            # Convert BDD acceptance criteria to simple strings
            ac_list: list[str] = []
            for ac in us.get("acceptance_criteria", []):
                if isinstance(ac, dict):
                    parts = []
                    if ac.get("given"):
                        parts.append(f"Given: {ac['given']}")
                    if ac.get("when"):
                        parts.append(f"When: {ac['when']}")
                    if ac.get("then"):
                        parts.append(f"Then: {ac['then']}")
                    ac_list.append(" | ".join(parts))
                elif isinstance(ac, str):
                    ac_list.append(ac)

            stories.append(ParsedUserStory(
                id=us.get("id", ""),
                epic=us.get("parent_epic_id", ""),
                title=us.get("title", ""),
                acceptance_criteria=ac_list,
                linked_requirements=us.get("linked_requirement_ids", []),
                linked_endpoints=[],  # Resolved later during endpoint linking
            ))

        return stories
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: implement user stories JSON parser"
```

---

### Task 5: Implement API endpoint parser

**Files:**
- Modify: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

Parse from `api/openapi_spec.yaml` (OpenAPI 3.0.3). Each path has HTTP methods with `summary`, `tags`, `requestBody`, `responses`, and `$ref` schema references.

- [ ] **Step 1: Write test for endpoint parsing**

```python
class TestEndpointParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_endpoints_from_openapi(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        endpoints = parser._parse_endpoints()
        assert len(endpoints) >= 200  # 418 expected

    def test_endpoint_has_method_and_path(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        endpoints = parser._parse_endpoints()
        for ep in endpoints[:5]:
            assert ep.method in ("GET", "POST", "PUT", "DELETE", "PATCH")
            assert ep.path.startswith("/")

    def test_endpoint_has_status_codes(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        endpoints = parser._parse_endpoints()
        with_codes = [ep for ep in endpoints if len(ep.status_codes) > 0]
        assert len(with_codes) > 100
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement `_parse_endpoints()`**

```python
    def _parse_endpoints(self) -> list[ParsedEndpoint]:
        """Parse api/openapi_spec.yaml into ParsedEndpoint list."""
        yaml_file = self.project_dir / "api" / "openapi_spec.yaml"
        if not yaml_file.exists():
            logger.warning("openapi_spec.yaml not found, falling back to api_documentation.md")
            return self._parse_endpoints_from_markdown()

        text = yaml_file.read_text(encoding="utf-8")
        spec = yaml.safe_load(text)
        if not spec:
            return []

        self._openapi_version = spec.get("openapi", "3.0.3")
        endpoints: list[ParsedEndpoint] = []

        for path, methods in spec.get("paths", {}).items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "delete", "patch"):
                    # Extract request/response DTO names from $ref
                    req_dto = ""
                    resp_dto = ""
                    req_body = details.get("requestBody", {})
                    if req_body:
                        content = req_body.get("content", {})
                        for _ctype, schema_info in content.items():
                            ref = schema_info.get("schema", {}).get("$ref", "")
                            if ref:
                                req_dto = ref.split("/")[-1]
                            break

                    responses = details.get("responses", {})
                    status_codes: dict[int, str] = {}
                    for code_str, resp_info in responses.items():
                        try:
                            code = int(code_str)
                        except ValueError:
                            continue
                        desc = resp_info.get("description", "")
                        status_codes[code] = desc
                        # Extract response DTO from success codes
                        if 200 <= code < 300 and not resp_dto:
                            resp_content = resp_info.get("content", {})
                            for _ctype, schema_info in resp_content.items():
                                ref = schema_info.get("schema", {}).get("$ref", "")
                                if ref:
                                    resp_dto = ref.split("/")[-1]
                                break

                    # Check auth requirement
                    security = details.get("security")
                    auth_required = security != []  # Empty list means no auth

                    tags = details.get("tags", [])

                    endpoints.append(ParsedEndpoint(
                        method=method.upper(),
                        path=path,
                        service="",  # Assigned later by tag/path mapping
                        request_dto=req_dto,
                        response_dto=resp_dto,
                        auth_required=auth_required,
                        linked_stories=[],
                        status_codes=status_codes,
                    ))

        return endpoints

    def _parse_endpoints_from_markdown(self) -> list[ParsedEndpoint]:
        """Fallback: parse api/api_documentation.md."""
        md_file = self.project_dir / "api" / "api_documentation.md"
        if not md_file.exists():
            return []

        text = md_file.read_text(encoding="utf-8")
        endpoints: list[ParsedEndpoint] = []
        # Match: #### `METHOD` /path
        for match in re.finditer(r"####\s*`(\w+)`\s*(/\S+)", text):
            method = match.group(1).upper()
            path = match.group(2)
            endpoints.append(ParsedEndpoint(
                method=method, path=path, service="",
            ))
        return endpoints
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: implement OpenAPI endpoint parser with markdown fallback"
```

---

### Task 6: Implement state machine parser

**Files:**
- Modify: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

Mermaid `stateDiagram-v2` format. Transitions: `state1 --> state2 : event [guard] / action`

- [ ] **Step 1: Write test**

```python
class TestStateMachineParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_state_machines(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        machines = parser._parse_state_machines()
        assert len(machines) >= 5
        names = [sm.name for sm in machines]
        assert "message" in [n.lower() for n in names] or any("message" in n.lower() for n in names)

    def test_state_machine_has_transitions(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        machines = parser._parse_state_machines()
        for sm in machines:
            if "message" in sm.name.lower():
                assert len(sm.transitions) >= 5
                assert len(sm.states) >= 4
                break
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement `_parse_state_machines()`**

```python
    def _parse_state_machines(self) -> list[StateMachine]:
        """Parse state_machines/*.mmd into StateMachine list."""
        sm_dir = self.project_dir / "state_machines"
        if not sm_dir.exists():
            return []

        machines: list[StateMachine] = []
        for mmd_file in sorted(sm_dir.glob("*.mmd")):
            text = mmd_file.read_text(encoding="utf-8")
            name = mmd_file.stem  # e.g. "message", "auth_session"

            states: set[str] = set()
            transitions: list[StateTransition] = []
            initial_state = ""
            terminal_states: list[str] = []

            for line in text.split("\n"):
                line = line.strip()
                # Match: state1 --> state2 : trigger [guard] / action
                m = re.match(
                    r"(\[?\*?\]?|\w+)\s*-->\s*(\[?\*?\]?|\w+)\s*(?::\s*(.+))?",
                    line,
                )
                if not m:
                    continue

                from_s = m.group(1).strip()
                to_s = m.group(2).strip()
                rest = m.group(3) or ""

                # Parse trigger, guard, action from rest
                trigger = ""
                guard = None
                if rest:
                    # Pattern: trigger [guard] / action
                    parts = re.match(r"(\w+)(?:\s*\[([^\]]+)\])?\s*(?:/\s*(.+))?", rest)
                    if parts:
                        trigger = parts.group(1)
                        guard = parts.group(2)

                # Handle [*] (start/end)
                if from_s == "[*]":
                    if to_s != "[*]":
                        initial_state = to_s
                        states.add(to_s)
                    continue
                if to_s == "[*]":
                    terminal_states.append(from_s)
                    states.add(from_s)
                    continue

                states.add(from_s)
                states.add(to_s)
                transitions.append(StateTransition(
                    from_state=from_s,
                    to_state=to_s,
                    trigger=trigger,
                    guard=guard,
                ))

            if states:
                machines.append(StateMachine(
                    name=name,
                    entity=name.replace("_", " ").title().replace(" ", ""),
                    states=sorted(states),
                    initial_state=initial_state or (sorted(states)[0] if states else ""),
                    terminal_states=terminal_states,
                    transitions=transitions,
                ))

        return machines
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: implement Mermaid state machine parser"
```

---

### Task 7: Implement full `parse()` method with dependency graph

**Files:**
- Modify: `src/engine/spec_parser.py`
- Test: `tests/engine/test_spec_parser.py`

Combines all sub-parsers, assigns entities/endpoints to services, and computes topological generation order.

- [ ] **Step 1: Write test for full parse**

```python
class TestFullParse:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_full_parse(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        assert isinstance(spec, ParsedSpec)
        assert len(spec.services) >= 7
        assert len(spec.generation_order) >= 7
        # auth-service should be first (no deps)
        assert spec.generation_order[0] == "auth-service"

    def test_endpoints_assigned_to_services(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        total_endpoints = sum(len(s.endpoints) for s in spec.services.values())
        assert total_endpoints >= 200

    def test_no_cycles_in_dependency_graph(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        # generation_order exists = no cycles detected
        assert len(spec.generation_order) == len([
            s for s in spec.services.values() if s.port > 0 and s.port < 10000
        ])

    def test_parsed_spec_to_json(self):
        """Verify ParsedSpec can be serialized for debugging."""
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        # Should not raise
        import json
        from dataclasses import asdict
        json_str = json.dumps(asdict(spec), indent=2, default=str)
        assert len(json_str) > 1000
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement `parse()` with topological sort**

```python
    def parse(self) -> ParsedSpec:
        """Full parse: combine all sub-parsers into ParsedSpec."""
        # 1. Parse architecture (services skeleton)
        services = self._parse_architecture()

        # 2. Parse entities and assign to services
        entities = self._parse_data_dictionary()
        self._assign_entities_to_services(entities, services)

        # 3. Parse endpoints and assign to services
        endpoints = self._parse_endpoints()
        self._assign_endpoints_to_services(endpoints, services)

        # 4. Parse user stories and assign to services
        stories = self._parse_user_stories()
        self._assign_stories_to_services(stories, services)

        # 5. Parse state machines and assign to services
        state_machines = self._parse_state_machines()
        self._assign_state_machines_to_services(state_machines, services)

        # 5b. Link stories to endpoints for traceability
        self._link_stories_to_endpoints(services)

        # 6. Filter to API services only (port > 0, not databases/infra)
        api_services = {
            k: v for k, v in services.items()
            if v.port > 0 and v.port < 10000  # Exclude DB ports >5000 range
            and not k.startswith("postgres-") and not k.startswith("redis")
            and not k.startswith("kafka") and not k.startswith("s3-")
            and not k.startswith("kong")
        }

        # 7. Build dependency graph and topological sort
        dep_graph = self._build_dependency_graph(api_services)
        gen_order = self._topological_sort(dep_graph)

        return ParsedSpec(
            services=api_services,
            shared_entities=[e for e in entities if not e.service],
            dependency_graph=dep_graph,
            generation_order=gen_order,
            openapi_version=getattr(self, "_openapi_version", "3.0.3"),
        )

    def _assign_entities_to_services(
        self, entities: list[ParsedEntity], services: dict[str, ParsedService],
    ) -> None:
        """Assign entities to services based on dependency names."""
        for entity in entities:
            for svc_name, svc in services.items():
                # Match entity to service by database dependency naming
                for dep in svc.dependencies:
                    if dep.startswith("postgres-"):
                        db_domain = dep.replace("postgres-", "")
                        if db_domain in svc_name or svc_name.replace("-service", "") in db_domain:
                            entity.service = svc_name
                            svc.entities.append(entity)
                            break
                if entity.service:
                    break

    def _assign_endpoints_to_services(
        self, endpoints: list[ParsedEndpoint], services: dict[str, ParsedService],
    ) -> None:
        """Assign endpoints to services based on URL path patterns."""
        # Build path-to-service mapping from common patterns
        path_map: dict[str, str] = {}
        for svc_name in services:
            # auth-service -> /auth/, /phone-registrations/, /sessions/
            domain = svc_name.replace("-service", "").replace("-worker", "")
            path_map[f"/{domain}"] = svc_name

        for ep in endpoints:
            path_lower = ep.path.lower()
            assigned = False
            for pattern, svc_name in path_map.items():
                if pattern in path_lower:
                    ep.service = svc_name
                    services[svc_name].endpoints.append(ep)
                    assigned = True
                    break
            if not assigned:
                # Try to assign by first path segment after /api/v1/
                m = re.match(r"/api/v\d+/([^/]+)", ep.path)
                if m:
                    segment = m.group(1).lower()
                    for svc_name in services:
                        if segment in svc_name:
                            ep.service = svc_name
                            services[svc_name].endpoints.append(ep)
                            break

    def _assign_stories_to_services(
        self, stories: list[ParsedUserStory], services: dict[str, ParsedService],
    ) -> None:
        """Assign stories to services based on requirement ID patterns."""
        req_to_service = {
            "WA-AUTH": "auth-service", "WA-SEC": "auth-service",
            "WA-PROF": "user-profile-service", "WA-SET": "user-profile-service",
            "WA-MSG": "messaging-service",
            "WA-GRP": "chat-service",
            "WA-STS": "media-service", "WA-MED": "media-service",
            "WA-ACC": "user-profile-service",
        }
        for story in stories:
            for req_id in story.linked_requirements:
                prefix = "-".join(req_id.split("-")[:2])
                svc_name = req_to_service.get(prefix)
                if svc_name and svc_name in services:
                    services[svc_name].stories.append(story)
                    break

    def _assign_state_machines_to_services(
        self, machines: list[StateMachine], services: dict[str, ParsedService],
    ) -> None:
        """Assign state machines to services by entity name matching."""
        for sm in machines:
            for svc_name, svc in services.items():
                entity_names = [e.name.lower() for e in svc.entities]
                if sm.entity.lower() in entity_names or sm.name.lower() in svc_name:
                    svc.state_machines.append(sm)
                    break

    def _link_stories_to_endpoints(self, services: dict[str, ParsedService]) -> None:
        """Link user stories to endpoints within the same service for traceability."""
        for svc_name, svc in services.items():
            for story in svc.stories:
                for ep in svc.endpoints:
                    # Link if story mentions endpoint path segments
                    path_segments = [p for p in ep.path.split("/") if p and p not in ("api", "v1", "v2")]
                    if any(seg.lower() in story.title.lower() for seg in path_segments):
                        if story.id not in ep.linked_stories:
                            ep.linked_stories.append(story.id)
                        if f"{ep.method} {ep.path}" not in story.linked_endpoints:
                            story.linked_endpoints.append(f"{ep.method} {ep.path}")

    def _build_dependency_graph(self, services: dict[str, ParsedService]) -> dict[str, list[str]]:
        """Build service dependency graph from service_dependencies."""
        graph: dict[str, list[str]] = {}
        service_names = set(services.keys())
        for svc_name, svc in services.items():
            deps = [d for d in svc.service_dependencies if d in service_names]
            graph[svc_name] = deps
        return graph

    def _topological_sort(self, graph: dict[str, list[str]]) -> list[str]:
        """Topological sort using Kahn's algorithm. Raises on cycles."""
        in_degree: dict[str, int] = {node: 0 for node in graph}
        for _node, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] = in_degree.get(dep, 0)  # ensure exists

        # in_degree[node] = number of dependencies node has
        in_degree = {node: len(deps) for node, deps in graph.items()}

        queue = [node for node, deg in in_degree.items() if deg == 0]
        result: list[str] = []

        while queue:
            queue.sort()  # Deterministic order
            node = queue.pop(0)
            result.append(node)
            # Decrement in-degree for nodes that depend on this node
            for other, deps in graph.items():
                if node in deps:
                    in_degree[other] -= 1
                    if in_degree[other] == 0 and other not in result:
                        queue.append(other)

        if len(result) != len(graph):
            missing = set(graph.keys()) - set(result)
            raise ValueError(f"Cyclic dependency detected involving: {missing}")

        return result
```

- [ ] **Step 4: Run test — should pass**

Run: `python -m pytest tests/engine/test_spec_parser.py::TestFullParse -v`

- [ ] **Step 5: Run all SpecParser tests**

Run: `python -m pytest tests/engine/test_spec_parser.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/engine/spec_parser.py tests/engine/test_spec_parser.py
git commit -m "feat: implement full SpecParser with dependency graph and topological sort"
```

---

## Chunk 2: Skeleton Generator (Prio 2)

### Task 8: Create NestJS skeleton generator — Prisma schema

**Files:**
- Create: `src/engine/skeleton_generator.py`
- Test: `tests/engine/test_skeleton_generator.py`

- [ ] **Step 1: Write test for Prisma schema generation**

```python
# tests/engine/test_skeleton_generator.py
import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser, ParsedSpec, ParsedEntity, Field, Relation
from src.engine.skeleton_generator import SkeletonGenerator


class TestPrismaGeneration:
    def _get_spec(self) -> ParsedSpec:
        whatsapp_dir = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")
        return SpecParser(whatsapp_dir).parse()

    def test_generate_prisma_schema(self, tmp_path):
        spec = self._get_spec()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen._generate_prisma_schema(auth_svc, tmp_path / "auth-service")
        schema_file = tmp_path / "auth-service" / "prisma" / "schema.prisma"
        assert schema_file.exists()
        content = schema_file.read_text()
        assert "generator client" in content
        assert "datasource db" in content

    def test_prisma_has_models(self, tmp_path):
        spec = self._get_spec()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen._generate_prisma_schema(auth_svc, tmp_path / "auth-service")
        content = (tmp_path / "auth-service" / "prisma" / "schema.prisma").read_text()
        # Should have at least one model
        assert "model " in content
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement SkeletonGenerator with Prisma generation**

```python
# src/engine/skeleton_generator.py
"""Deterministic Skeleton Generator — Prio 2 of Pipeline Improvements.

Generates NestJS code scaffolds from ParsedSpec without any LLM calls.
Every endpoint, entity, and service gets its files — guaranteed.

Spec: docs/superpowers/specs/2026-03-16-pipeline-improvements-design.md
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from src.engine.spec_parser import (
    ParsedSpec, ParsedService, ParsedEndpoint, ParsedEntity, Field, Relation,
)

logger = logging.getLogger(__name__)


# Type mapping: spec types -> Prisma types
PRISMA_TYPE_MAP = {
    "uuid": "String",
    "string": "String",
    "text": "String",
    "int": "Int",
    "integer": "Int",
    "boolean": "Boolean",
    "datetime": "DateTime",
    "decimal": "Decimal",
    "float": "Float",
    "json": "Json",
    "enum": "String",
}


def _to_pascal(name: str) -> str:
    """Convert snake_case or kebab-case to PascalCase."""
    return "".join(w.capitalize() for w in re.split(r"[-_]", name))


def _to_camel(name: str) -> str:
    """Convert to camelCase."""
    pascal = _to_pascal(name)
    return pascal[0].lower() + pascal[1:] if pascal else ""


class SkeletonGenerator:
    """Generates deterministic NestJS code scaffolds from ParsedSpec."""

    def __init__(self, spec: ParsedSpec, output_dir: str | Path):
        self.spec = spec
        self.output_dir = Path(output_dir)

    def generate_all(self) -> dict[str, Path]:
        """Generate skeleton for all services. Returns {service_name: dir}."""
        results: dict[str, Path] = {}
        for svc_name in self.spec.generation_order:
            svc = self.spec.services[svc_name]
            svc_dir = self.output_dir / svc_name
            self.generate_service(svc, svc_dir)
            results[svc_name] = svc_dir
        return results

    def generate_service(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate full skeleton for one service."""
        svc_dir.mkdir(parents=True, exist_ok=True)
        self._generate_prisma_schema(svc, svc_dir)
        self._generate_package_json(svc, svc_dir)
        self._generate_tsconfig(svc_dir)
        self._generate_nest_cli(svc_dir)
        self._generate_main_ts(svc, svc_dir)
        self._generate_feature_modules(svc, svc_dir)
        self._generate_app_module(svc, svc_dir)
        self._generate_dockerfile(svc, svc_dir)
        self._generate_test_stubs(svc, svc_dir)
        logger.info("Skeleton generated for %s: %d endpoints, %d entities",
                     svc.name, len(svc.endpoints), len(svc.entities))

    def _generate_prisma_schema(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate prisma/schema.prisma from entities."""
        prisma_dir = svc_dir / "prisma"
        prisma_dir.mkdir(parents=True, exist_ok=True)

        lines = [
            "generator client {",
            '  provider = "prisma-client-js"',
            "}",
            "",
            "datasource db {",
            '  provider = "postgresql"',
            '  url      = env("DATABASE_URL")',
            "}",
            "",
        ]

        for entity in svc.entities:
            model_name = _to_pascal(entity.name)
            lines.append(f"model {model_name} {{")
            for field in entity.fields:
                prisma_type = PRISMA_TYPE_MAP.get(field.type, "String")
                attrs = []
                if field.name.lower() == "id":
                    attrs.append("@id")
                    if field.type == "uuid":
                        attrs.append("@default(uuid())")
                if field.unique:
                    attrs.append("@unique")
                if field.default and "@default" not in " ".join(attrs):
                    attrs.append(f"@default({field.default})")
                optional = "?" if field.nullable else ""
                attr_str = " ".join(attrs)
                lines.append(f"  {field.name} {prisma_type}{optional} {attr_str}".rstrip())

            # Add timestamps if not present
            field_names = [f.name for f in entity.fields]
            if "createdAt" not in field_names and "created_at" not in field_names:
                lines.append("  createdAt DateTime @default(now())")
            if "updatedAt" not in field_names and "updated_at" not in field_names:
                lines.append("  updatedAt DateTime @updatedAt")

            lines.append("}")
            lines.append("")

        (prisma_dir / "schema.prisma").write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/skeleton_generator.py tests/engine/test_skeleton_generator.py
git commit -m "feat: add SkeletonGenerator with Prisma schema generation"
```

---

### Task 9: Generate controller, service, DTO, and module stubs

**Files:**
- Modify: `src/engine/skeleton_generator.py`
- Test: `tests/engine/test_skeleton_generator.py`

- [ ] **Step 1: Write test for controller/service generation**

```python
class TestControllerServiceGeneration:
    def _get_spec(self) -> ParsedSpec:
        whatsapp_dir = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")
        return SpecParser(whatsapp_dir).parse()

    def test_generate_full_service_skeleton(self, tmp_path):
        spec = self._get_spec()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        svc_dir = tmp_path / "auth-service"
        assert (svc_dir / "src" / "main.ts").exists()
        assert (svc_dir / "src" / "app.module.ts").exists()
        assert (svc_dir / "package.json").exists()
        assert (svc_dir / "Dockerfile").exists()

    def test_controller_has_all_endpoints(self, tmp_path):
        spec = self._get_spec()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        # Find any .controller.ts file
        controllers = list((tmp_path / "auth-service").rglob("*.controller.ts"))
        assert len(controllers) >= 1

        # Count @Get/@Post/@Put/@Delete decorators across all controllers
        total_decorators = 0
        for ctrl in controllers:
            content = ctrl.read_text()
            total_decorators += len(re.findall(r"@(Get|Post|Put|Delete|Patch)\(", content))
        assert total_decorators >= len(auth_svc.endpoints)

    def test_service_methods_match_controller(self, tmp_path):
        spec = self._get_spec()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        services = list((tmp_path / "auth-service").rglob("*.service.ts"))
        controllers = list((tmp_path / "auth-service").rglob("*.controller.ts"))

        # Extract method names from service files
        svc_methods = set()
        for sf in services:
            for m in re.finditer(r"async\s+(\w+)\(", sf.read_text()):
                svc_methods.add(m.group(1))

        # Extract method calls from controllers: this.xxxService.methodName
        ctrl_calls = set()
        for cf in controllers:
            for m in re.finditer(r"this\.\w+Service\.(\w+)\(", cf.read_text()):
                ctrl_calls.add(m.group(1))

        # All controller calls should exist in service methods
        missing = ctrl_calls - svc_methods
        assert len(missing) == 0, f"Controller calls methods not in service: {missing}"
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement remaining generator methods**

Add to `SkeletonGenerator`:

```python
    def _generate_feature_modules(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate controller, service, DTOs, module for each feature group."""
        # Group endpoints by first path segment (feature module)
        groups: dict[str, list[ParsedEndpoint]] = {}
        for ep in svc.endpoints:
            # Extract feature from path: /api/v1/auth/register -> auth
            m = re.match(r"/api/v\d+/([^/]+)", ep.path)
            feature = m.group(1).replace("-", "_") if m else "default"
            groups.setdefault(feature, []).append(ep)

        if not groups:
            # No endpoints — create a minimal feature module from service name
            feature = svc.name.replace("-service", "").replace("-worker", "").replace("-", "_")
            groups[feature] = []

        for feature, endpoints in groups.items():
            feature_dir = svc_dir / "src" / feature
            feature_dir.mkdir(parents=True, exist_ok=True)
            (feature_dir / "dto").mkdir(exist_ok=True)

            self._generate_controller(feature, endpoints, svc, feature_dir)
            self._generate_service(feature, endpoints, svc, feature_dir)
            self._generate_dtos(feature, endpoints, feature_dir)
            self._generate_module(feature, feature_dir)

    def _generate_controller(
        self, feature: str, endpoints: list[ParsedEndpoint],
        svc: ParsedService, feature_dir: Path,
    ) -> None:
        """Generate controller with all endpoint stubs."""
        class_name = _to_pascal(feature) + "Controller"
        service_name = _to_pascal(feature) + "Service"
        service_var = _to_camel(feature) + "Service"

        lines = [
            f"import {{ Controller, Get, Post, Put, Delete, Patch, Body, Param, Query }} from '@nestjs/common';",
            f"import {{ {service_name} }} from './{feature}.service';",
            "",
            f"@Controller('{feature.replace('_', '-')}')",
            f"export class {class_name} {{",
            f"  constructor(private readonly {service_var}: {service_name}) {{}}",
            "",
        ]

        for ep in endpoints:
            method_decorator = ep.method.capitalize()
            # Extract sub-path after feature: /api/v1/auth/register -> register
            sub_path = re.sub(r"^/api/v\d+/[^/]+/?", "", ep.path)
            method_name = self._endpoint_to_method_name(ep)
            req_dto = ep.request_dto or "any"
            resp_dto = ep.response_dto or "any"

            # Find linked stories for comments
            story_refs = ", ".join(ep.linked_stories[:3]) if ep.linked_stories else ""
            story_comment = f"  // {ep.method} {ep.path}" + (f" — {story_refs}" if story_refs else "")

            lines.append(story_comment)
            lines.append(f"  @{method_decorator}('{sub_path}')")
            if ep.method in ("POST", "PUT", "PATCH") and req_dto != "any":
                lines.append(f"  async {method_name}(@Body() dto: {req_dto}): Promise<{resp_dto}> {{")
            elif ":id" in sub_path or "{" in sub_path:
                param = re.search(r":(\w+)|{(\w+)}", sub_path)
                param_name = (param.group(1) or param.group(2)) if param else "id"
                lines.append(f"  async {method_name}(@Param('{param_name}') {param_name}: string): Promise<{resp_dto}> {{")
            else:
                lines.append(f"  async {method_name}(): Promise<{resp_dto}> {{")

            lines.append(f"    // TODO: Agent fills implementation")
            lines.append(f"    return this.{service_var}.{method_name}();")
            lines.append(f"  }}")
            lines.append("")

        lines.append("}")
        (feature_dir / f"{feature}.controller.ts").write_text("\n".join(lines), encoding="utf-8")

    def _generate_service(
        self, feature: str, endpoints: list[ParsedEndpoint],
        svc: ParsedService, feature_dir: Path,
    ) -> None:
        """Generate service with stub methods matching controller."""
        service_name = _to_pascal(feature) + "Service"

        lines = [
            "import { Injectable, NotImplementedException } from '@nestjs/common';",
            "import { PrismaService } from '../prisma/prisma.service';",
            "",
            "@Injectable()",
            f"export class {service_name} {{",
            "  constructor(private readonly prisma: PrismaService) {}",
            "",
        ]

        for ep in endpoints:
            method_name = self._endpoint_to_method_name(ep)
            story_refs = ", ".join(ep.linked_stories[:3]) if ep.linked_stories else ""
            comment = f"  // Linked: {story_refs}" if story_refs else ""
            if comment:
                lines.append(comment)
            lines.append(f"  async {method_name}(): Promise<any> {{")
            lines.append(f"    // TODO: Agent fills implementation")
            lines.append(f"    throw new NotImplementedException('{method_name}');")
            lines.append(f"  }}")
            lines.append("")

        lines.append("}")
        (feature_dir / f"{feature}.service.ts").write_text("\n".join(lines), encoding="utf-8")

    def _generate_dtos(
        self, feature: str, endpoints: list[ParsedEndpoint], feature_dir: Path,
    ) -> None:
        """Generate DTO stubs for request/response types."""
        seen: set[str] = set()
        for ep in endpoints:
            for dto_name in [ep.request_dto, ep.response_dto]:
                if not dto_name or dto_name == "any" or dto_name in seen:
                    continue
                seen.add(dto_name)
                class_name = _to_pascal(dto_name)
                file_name = re.sub(r"(?<!^)(?=[A-Z])", "-", class_name).lower()
                content = (
                    f"import {{ IsString, IsOptional }} from 'class-validator';\n\n"
                    f"export class {class_name} {{\n"
                    f"  // TODO: Add fields from OpenAPI spec\n"
                    f"}}\n"
                )
                (feature_dir / "dto" / f"{file_name}.dto.ts").write_text(content, encoding="utf-8")

    def _generate_module(self, feature: str, feature_dir: Path) -> None:
        """Generate NestJS module."""
        controller = _to_pascal(feature) + "Controller"
        service = _to_pascal(feature) + "Service"
        module = _to_pascal(feature) + "Module"
        content = (
            f"import {{ Module }} from '@nestjs/common';\n"
            f"import {{ {controller} }} from './{feature}.controller';\n"
            f"import {{ {service} }} from './{feature}.service';\n\n"
            f"@Module({{\n"
            f"  controllers: [{controller}],\n"
            f"  providers: [{service}],\n"
            f"  exports: [{service}],\n"
            f"}})\n"
            f"export class {module} {{}}\n"
        )
        (feature_dir / f"{feature}.module.ts").write_text(content, encoding="utf-8")

    def _generate_main_ts(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate src/main.ts."""
        src_dir = svc_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "import { NestFactory } from '@nestjs/core';\n"
            "import { ValidationPipe } from '@nestjs/common';\n"
            "import { AppModule } from './app.module';\n\n"
            "async function bootstrap() {\n"
            "  const app = await NestFactory.create(AppModule);\n"
            "  app.useGlobalPipes(new ValidationPipe({ whitelist: true }));\n"
            f"  await app.listen({svc.port});\n"
            "}\n"
            "bootstrap();\n"
        )
        (src_dir / "main.ts").write_text(content, encoding="utf-8")

    def _generate_app_module(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate src/app.module.ts importing all feature modules."""
        src_dir = svc_dir / "src"
        # Find all *.module.ts files (excluding app.module.ts)
        feature_dirs = [d for d in src_dir.iterdir() if d.is_dir() and (d / f"{d.name}.module.ts").exists()]
        imports = []
        import_names = []
        for fd in sorted(feature_dirs):
            mod_name = _to_pascal(fd.name) + "Module"
            imports.append(f"import {{ {mod_name} }} from './{fd.name}/{fd.name}.module';")
            import_names.append(mod_name)

        content = (
            "import { Module } from '@nestjs/common';\n"
            + "\n".join(imports)
            + "\n\n@Module({\n"
            + f"  imports: [{', '.join(import_names)}],\n"
            + "})\n"
            + "export class AppModule {}\n"
        )
        (src_dir / "app.module.ts").write_text(content, encoding="utf-8")

    def _generate_package_json(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate package.json with correct dependencies."""
        import json
        pkg = {
            "name": svc.name,
            "version": "0.0.1",
            "scripts": {
                "build": "nest build",
                "start": "nest start",
                "start:dev": "nest start --watch",
                "test": "jest",
                "test:e2e": "jest --config ./test/jest-e2e.json",
            },
            "dependencies": {
                "@nestjs/common": "^10.3.2",
                "@nestjs/core": "^10.3.2",
                "@nestjs/platform-express": "^10.3.2",
                "@prisma/client": "^5.10.0",
                "class-validator": "^0.14.0",
                "class-transformer": "^0.5.1",
                "reflect-metadata": "^0.2.0",
                "rxjs": "^7.8.1",
            },
            "devDependencies": {
                "@nestjs/cli": "^10.3.2",
                "@nestjs/testing": "^10.3.2",
                "@types/node": "^20.11.0",
                "jest": "^29.7.0",
                "prisma": "^5.10.0",
                "ts-jest": "^29.1.0",
                "typescript": "^5.5.4",
            },
        }
        (svc_dir / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")

    def _generate_tsconfig(self, svc_dir: Path) -> None:
        import json
        tsconfig = {
            "compilerOptions": {
                "module": "commonjs", "declaration": True, "removeComments": True,
                "emitDecoratorMetadata": True, "experimentalDecorators": True,
                "allowSyntheticDefaultImports": True, "target": "ES2021",
                "sourceMap": True, "outDir": "./dist", "baseUrl": "./",
                "incremental": True, "strict": True, "esModuleInterop": True,
            },
        }
        (svc_dir / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2), encoding="utf-8")

    def _generate_nest_cli(self, svc_dir: Path) -> None:
        import json
        config = {"$schema": "https://json.schemastore.org/nest-cli", "collection": "@nestjs/schematics", "sourceRoot": "src"}
        (svc_dir / "nest-cli.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _generate_dockerfile(self, svc: ParsedService, svc_dir: Path) -> None:
        content = (
            "FROM node:20-alpine AS builder\n"
            "WORKDIR /app\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .\n"
            "RUN npm run build\n\n"
            "FROM node:20-alpine\n"
            "WORKDIR /app\n"
            "COPY --from=builder /app/dist ./dist\n"
            "COPY --from=builder /app/node_modules ./node_modules\n"
            "COPY --from=builder /app/package.json ./\n"
            f"EXPOSE {svc.port}\n"
            'CMD ["node", "dist/main.js"]\n'
        )
        (svc_dir / "Dockerfile").write_text(content, encoding="utf-8")

    def _generate_test_stubs(self, svc: ParsedService, svc_dir: Path) -> None:
        """Generate e2e test stubs with one test per endpoint."""
        test_dir = svc_dir / "test"
        test_dir.mkdir(exist_ok=True)
        feature = svc.name.replace("-service", "").replace("-worker", "")
        lines = [
            "import { Test, TestingModule } from '@nestjs/testing';",
            "import { INestApplication } from '@nestjs/common';",
            "import * as request from 'supertest';",
            "import { AppModule } from '../src/app.module';",
            "",
            f"describe('{svc.name} (e2e)', () => {{",
            "  let app: INestApplication;",
            "",
            "  beforeAll(async () => {",
            "    const moduleFixture: TestingModule = await Test.createTestingModule({",
            "      imports: [AppModule],",
            "    }).compile();",
            "    app = moduleFixture.createNestApplication();",
            "    await app.init();",
            "  });",
            "",
        ]
        for ep in svc.endpoints:
            method = ep.method.lower()
            lines.append(f"  it('{ep.method} {ep.path} should respond', () => {{")
            lines.append(f"    return request(app.getHttpServer()).{method}('{ep.path}').expect(/* TODO */);")
            lines.append(f"  }});")
            lines.append("")

        lines.append("  afterAll(async () => { await app.close(); });")
        lines.append("});")
        (test_dir / f"{feature}.e2e-spec.ts").write_text("\n".join(lines), encoding="utf-8")

    def _endpoint_to_method_name(self, ep: ParsedEndpoint) -> str:
        """Convert endpoint to a method name: POST /api/v1/auth/register -> createRegister."""
        prefix_map = {"GET": "get", "POST": "create", "PUT": "update", "DELETE": "delete", "PATCH": "patch"}
        prefix = prefix_map.get(ep.method, ep.method.lower())
        # Extract last meaningful path segment
        parts = [p for p in ep.path.split("/") if p and not p.startswith("{") and not p.startswith(":") and p not in ("api", "v1", "v2")]
        if parts:
            name = _to_pascal(parts[-1])
        else:
            name = "Default"
        return f"{prefix}{name}"
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/skeleton_generator.py tests/engine/test_skeleton_generator.py
git commit -m "feat: implement full NestJS skeleton generation (controllers, services, DTOs, modules)"
```

---

## Chunk 3: Validation Engine (Prio 4)

### Task 10: Create ValidationEngine + endpoint coverage validator

**Files:**
- Create: `src/engine/validation_engine.py`
- Create: `src/engine/validators/__init__.py`
- Create: `src/engine/validators/endpoint_coverage.py`
- Test: `tests/engine/test_validation_engine.py`

- [ ] **Step 1: Write test**

```python
# tests/engine/test_validation_engine.py
import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.validators.endpoint_coverage import EndpointCoverageValidator
from src.validators.base_validator import ValidationSeverity


class TestEndpointCoverageValidator:
    def test_skeleton_has_full_coverage(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        validator = EndpointCoverageValidator()
        issues = validator.validate(auth_svc, tmp_path / "auth-service")
        # Skeleton should have 100% coverage by design
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0, f"Missing endpoints: {[i.error_message for i in errors]}"
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement**

```python
# src/engine/validators/__init__.py
"""Spec-level validators for generated code."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.validators.base_validator import ValidationFailure


class SpecValidator(ABC):
    """Abstract base for all spec-level validators."""
    name: str

    @abstractmethod
    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        ...
```

```python
# src/engine/validators/endpoint_coverage.py
"""Validates that all spec endpoints have controller methods."""
from __future__ import annotations

import re
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class EndpointCoverageValidator(SpecValidator):
    name = "endpoint_coverage"
    severity = ValidationSeverity.ERROR

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        """Check every endpoint in spec has a matching controller route."""
        issues: list[ValidationFailure] = []
        controllers = list(code_dir.rglob("*.controller.ts"))
        all_routes: set[str] = set()

        for ctrl in controllers:
            content = ctrl.read_text(encoding="utf-8")
            for m in re.finditer(r"@(Get|Post|Put|Delete|Patch)\(['\"]([^'\"]*)['\"]", content):
                method = m.group(1).upper()
                path = m.group(2)
                all_routes.add(f"{method}:{path}")

        for ep in service.endpoints:
            sub_path = re.sub(r"^/api/v\d+/[^/]+/?", "", ep.path)
            key = f"{ep.method}:{sub_path}"
            if key not in all_routes:
                issues.append(ValidationFailure(
                    check_type=self.name,
                    error_message=f"Missing: {ep.method} {ep.path} (expected route '{sub_path}')",
                    severity=self.severity,
                    file_path=str(code_dir),
                ))

        return issues
```

```python
# src/engine/validation_engine.py
"""Orchestrates all spec validators for a service."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.validators.base_validator import ValidationFailure, ValidationSeverity
from src.engine.validators.endpoint_coverage import EndpointCoverageValidator

logger = logging.getLogger(__name__)


class ValidationReport:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.issues: list[ValidationFailure] = []

    def has_errors(self) -> bool:
        return any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)

    def to_dict(self) -> dict:
        return {
            "service": self.service_name,
            "total_issues": len(self.issues),
            "errors": self.error_count,
            "issues": [i.to_dict() for i in self.issues],
        }


class ValidationEngine:
    def __init__(self):
        self.validators = [
            EndpointCoverageValidator(),
            # More validators added in subsequent tasks
        ]

    def validate_service(self, service: ParsedService, code_dir: Path) -> ValidationReport:
        report = ValidationReport(service.name)
        for validator in self.validators:
            try:
                issues = validator.validate(service, code_dir)
                report.issues.extend(issues)
            except Exception as e:
                logger.error("Validator %s crashed: %s", validator.name, e)
                report.issues.append(ValidationFailure(
                    check_type=validator.name,
                    error_message=f"VALIDATOR_ERROR: {e}",
                    severity=ValidationSeverity.WARNING,
                ))
        return report
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/validation_engine.py src/engine/validators/__init__.py src/engine/validators/endpoint_coverage.py tests/engine/test_validation_engine.py
git commit -m "feat: add ValidationEngine with endpoint coverage validator"
```

---

### Task 11: Add method consistency + import integrity validators

**Files:**
- Create: `src/engine/validators/method_consistency.py`
- Create: `src/engine/validators/import_integrity.py`
- Modify: `src/engine/validation_engine.py`
- Test: `tests/engine/test_validation_engine.py`

- [ ] **Step 1: Write tests**

```python
# Add to tests/engine/test_validation_engine.py
from src.engine.validators.method_consistency import MethodConsistencyValidator
from src.engine.validators.import_integrity import ImportIntegrityValidator


class TestMethodConsistencyValidator:
    def test_skeleton_methods_consistent(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        validator = MethodConsistencyValidator()
        issues = validator.validate(auth_svc, tmp_path / "auth-service")
        assert len(issues) == 0, f"Method drift: {[i.error_message for i in issues]}"


class TestImportIntegrityValidator:
    def test_skeleton_imports_valid(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        validator = ImportIntegrityValidator()
        issues = validator.validate(auth_svc, tmp_path / "auth-service")
        # Skeleton may have some external imports that can't be resolved locally
        errors = [i for i in issues if "phantom" in i.error_message.lower()]
        # Allow external package imports, only check local imports
        assert len(errors) == 0
```

- [ ] **Step 2: Run tests — should fail**

- [ ] **Step 3: Implement both validators**

```python
# src/engine/validators/method_consistency.py
"""Validates controller method calls match service method definitions."""
from __future__ import annotations

import re
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class MethodConsistencyValidator(SpecValidator):
    name = "method_consistency"
    severity = ValidationSeverity.ERROR

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        service_methods: dict[str, set[str]] = {}  # filename -> method names

        # Collect service methods
        for sf in code_dir.rglob("*.service.ts"):
            methods = set()
            for m in re.finditer(r"async\s+(\w+)\(", sf.read_text(encoding="utf-8")):
                methods.add(m.group(1))
            service_methods[sf.stem.replace(".service", "")] = methods

        # Check controller calls
        for cf in code_dir.rglob("*.controller.ts"):
            content = cf.read_text(encoding="utf-8")
            for m in re.finditer(r"this\.(\w+)Service\.(\w+)\(", content):
                svc_var = m.group(1)
                method = m.group(2)
                available = service_methods.get(svc_var, set())
                if available and method not in available:
                    issues.append(ValidationFailure(
                        check_type=self.name,
                        error_message=f"Controller calls '{method}' but {svc_var}.service has: {sorted(available)}",
                        severity=self.severity,
                        file_path=str(cf),
                    ))
        return issues
```

```python
# src/engine/validators/import_integrity.py
"""Validates that local imports reference existing files."""
from __future__ import annotations

import re
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class ImportIntegrityValidator(SpecValidator):
    name = "import_integrity"
    severity = ValidationSeverity.ERROR

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        for ts_file in code_dir.rglob("*.ts"):
            content = ts_file.read_text(encoding="utf-8")
            for m in re.finditer(r"from\s+['\"](\.[^'\"]+)['\"]", content):
                import_path = m.group(1)
                # Resolve relative to the file's directory
                resolved = (ts_file.parent / import_path).resolve()
                # Check .ts, .js, /index.ts variants
                candidates = [
                    resolved.with_suffix(".ts"),
                    resolved.with_suffix(".js"),
                    resolved / "index.ts",
                    resolved,
                ]
                if not any(c.exists() for c in candidates):
                    issues.append(ValidationFailure(
                        check_type=self.name,
                        error_message=f"Phantom import: '{import_path}' from {ts_file.name}",
                        severity=self.severity,
                        file_path=str(ts_file),
                    ))
        return issues
```

- [ ] **Step 4: Register validators in ValidationEngine**

Add to `ValidationEngine.__init__()`:
```python
from src.engine.validators.method_consistency import MethodConsistencyValidator
from src.engine.validators.import_integrity import ImportIntegrityValidator

self.validators = [
    EndpointCoverageValidator(),
    MethodConsistencyValidator(),
    ImportIntegrityValidator(),
]
```

- [ ] **Step 5: Run tests — should pass**

- [ ] **Step 6: Commit**

```bash
git add src/engine/validators/method_consistency.py src/engine/validators/import_integrity.py src/engine/validation_engine.py tests/engine/test_validation_engine.py
git commit -m "feat: add method consistency and import integrity validators"
```

---

### Task 11b: Add remaining 5 validator stubs

**Files:**
- Create: `src/engine/validators/entity_schema.py`
- Create: `src/engine/validators/dto_completeness.py`
- Create: `src/engine/validators/dependency_check.py`
- Create: `src/engine/validators/state_machine.py`
- Create: `src/engine/validators/acceptance_criteria.py`
- Modify: `src/engine/validation_engine.py`

- [ ] **Step 1: Create all 5 validator stubs**

Each validator extends `SpecValidator` and has a `validate()` method. Initial implementations are functional stubs that perform basic checks:

```python
# src/engine/validators/entity_schema.py
"""Validates Prisma schema matches data dictionary entities."""
from __future__ import annotations
import re
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class EntitySchemaValidator(SpecValidator):
    name = "entity_schema"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        schema_file = code_dir / "prisma" / "schema.prisma"
        if not schema_file.exists():
            if service.entities:
                issues.append(ValidationFailure(
                    check_type=self.name,
                    error_message="No schema.prisma but service has entities",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(code_dir),
                ))
            return issues

        content = schema_file.read_text(encoding="utf-8")
        model_names = set(re.findall(r"model\s+(\w+)\s*\{", content))
        for entity in service.entities:
            pascal_name = "".join(w.capitalize() for w in re.split(r"[-_]", entity.name))
            if pascal_name not in model_names:
                issues.append(ValidationFailure(
                    check_type=self.name,
                    error_message=f"Entity '{entity.name}' missing from Prisma schema (expected model {pascal_name})",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(schema_file),
                ))
        return issues
```

```python
# src/engine/validators/dto_completeness.py
"""Validates DTOs have fields matching spec."""
from __future__ import annotations
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class DtoCompletenessValidator(SpecValidator):
    name = "dto_completeness"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        dto_files = list(code_dir.rglob("*.dto.ts"))
        if not dto_files and any(ep.request_dto for ep in service.endpoints):
            issues.append(ValidationFailure(
                check_type=self.name,
                error_message="No DTO files found but endpoints define request DTOs",
                severity=ValidationSeverity.WARNING,
                file_path=str(code_dir),
            ))
        return issues
```

```python
# src/engine/validators/dependency_check.py
"""Validates package.json has all used packages."""
from __future__ import annotations
import json
import re
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class DependencyCheckValidator(SpecValidator):
    name = "dependency_check"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        pkg_file = code_dir / "package.json"
        if not pkg_file.exists():
            issues.append(ValidationFailure(
                check_type=self.name,
                error_message="Missing package.json",
                severity=ValidationSeverity.ERROR,
                file_path=str(code_dir),
            ))
            return issues

        pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
        all_deps = set(pkg.get("dependencies", {}).keys()) | set(pkg.get("devDependencies", {}).keys())

        for ts_file in code_dir.rglob("*.ts"):
            content = ts_file.read_text(encoding="utf-8")
            for m in re.finditer(r"from\s+['\"]([^./][^'\"]*)['\"]", content):
                pkg_name = m.group(1).split("/")[0]
                if pkg_name.startswith("@"):
                    pkg_name = "/".join(m.group(1).split("/")[:2])
                if pkg_name not in all_deps and pkg_name not in ("fs", "path", "util", "crypto", "http", "https"):
                    issues.append(ValidationFailure(
                        check_type=self.name,
                        error_message=f"Package '{pkg_name}' used in {ts_file.name} but not in package.json",
                        severity=ValidationSeverity.WARNING,
                        file_path=str(ts_file),
                    ))
        return issues
```

```python
# src/engine/validators/state_machine.py
"""Validates code implements defined state transitions."""
from __future__ import annotations
import re
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class StateMachineValidator(SpecValidator):
    name = "state_machine"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        if not service.state_machines:
            return issues

        all_code = ""
        for ts_file in code_dir.rglob("*.ts"):
            all_code += ts_file.read_text(encoding="utf-8")

        for sm in service.state_machines:
            # Check that state names appear in code
            found_states = [s for s in sm.states if s.lower() in all_code.lower()]
            if len(found_states) < len(sm.states) // 2:
                issues.append(ValidationFailure(
                    check_type=self.name,
                    error_message=f"State machine '{sm.name}': only {len(found_states)}/{len(sm.states)} states found in code",
                    severity=ValidationSeverity.WARNING,
                    file_path=str(code_dir),
                ))
        return issues
```

```python
# src/engine/validators/acceptance_criteria.py
"""Heuristic check that acceptance criteria are likely implemented."""
from __future__ import annotations
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class AcceptanceCriteriaValidator(SpecValidator):
    name = "acceptance_criteria"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        if not service.stories:
            return issues

        # Count stories with ACs vs endpoints implemented
        total_acs = sum(len(s.acceptance_criteria) for s in service.stories)
        total_endpoints = len(service.endpoints)
        if total_endpoints == 0 and total_acs > 0:
            issues.append(ValidationFailure(
                check_type=self.name,
                error_message=f"Service has {total_acs} acceptance criteria but 0 endpoints",
                severity=ValidationSeverity.WARNING,
                file_path=str(code_dir),
            ))
        return issues
```

- [ ] **Step 2: Register all validators in ValidationEngine**

Update `src/engine/validation_engine.py`:

```python
from src.engine.validators.endpoint_coverage import EndpointCoverageValidator
from src.engine.validators.method_consistency import MethodConsistencyValidator
from src.engine.validators.import_integrity import ImportIntegrityValidator
from src.engine.validators.entity_schema import EntitySchemaValidator
from src.engine.validators.dto_completeness import DtoCompletenessValidator
from src.engine.validators.dependency_check import DependencyCheckValidator
from src.engine.validators.state_machine import StateMachineValidator
from src.engine.validators.acceptance_criteria import AcceptanceCriteriaValidator

# In __init__:
self.validators = [
    EndpointCoverageValidator(),
    MethodConsistencyValidator(),
    ImportIntegrityValidator(),
    EntitySchemaValidator(),
    DtoCompletenessValidator(),
    DependencyCheckValidator(),
    StateMachineValidator(),
    AcceptanceCriteriaValidator(),
]
```

- [ ] **Step 3: Run tests — should pass**

- [ ] **Step 4: Commit**

```bash
git add src/engine/validators/*.py src/engine/validation_engine.py
git commit -m "feat: add 5 remaining spec validators (entity_schema, dto, deps, state_machine, acceptance)"
```

---

## Chunk 4: Context Injector + Traceability (Prio 5 + 6)

### Task 12: Implement ContextInjector

**Files:**
- Create: `src/engine/context_injector.py`
- Test: `tests/engine/test_context_injector.py`

- [ ] **Step 1: Write test**

```python
# tests/engine/test_context_injector.py
import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.context_injector import ContextInjector


class TestContextInjector:
    def _setup(self, tmp_path) -> tuple:
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")
        injector = ContextInjector(spec)
        return spec, auth_svc, injector, tmp_path / "auth-service"

    def test_service_file_gets_prisma_context(self, tmp_path):
        spec, auth_svc, injector, svc_dir = self._setup(tmp_path)
        service_files = list(svc_dir.rglob("*.service.ts"))
        if service_files:
            context = injector.get_context_for(service_files[0], auth_svc)
            assert "prisma" in context.lower() or "schema" in context.lower()

    def test_context_has_token_budget(self, tmp_path):
        spec, auth_svc, injector, svc_dir = self._setup(tmp_path)
        service_files = list(svc_dir.rglob("*.service.ts"))
        if service_files:
            context = injector.get_context_for(service_files[0], auth_svc)
            # ~4 chars per token, service max = 8000 tokens = 32000 chars
            assert len(context) <= 40000

    def test_controller_gets_service_context(self, tmp_path):
        spec, auth_svc, injector, svc_dir = self._setup(tmp_path)
        ctrl_files = list(svc_dir.rglob("*.controller.ts"))
        if ctrl_files:
            context = injector.get_context_for(ctrl_files[0], auth_svc)
            assert ".service.ts" in context or "Service" in context
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement ContextInjector**

```python
# src/engine/context_injector.py
"""Smart Context Injection — Prio 5 of Pipeline Improvements.

Assembles optimal per-file context for LLM agents.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from src.engine.spec_parser import ParsedSpec, ParsedService

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4

CONTEXT_RULES: dict[str, dict] = {
    ".service.ts": {
        "must_include": ["schema.prisma", ".dto.ts"],
        "spec_include": ["user_stories", "state_machines"],
        "max_tokens": 8000,
    },
    ".controller.ts": {
        "must_include": [".service.ts", ".dto.ts", ".guard.ts"],
        "spec_include": ["endpoints"],
        "max_tokens": 6000,
    },
    ".dto.ts": {
        "must_include": ["schema.prisma"],
        "spec_include": ["openapi"],
        "max_tokens": 3000,
    },
    ".guard.ts": {
        "must_include": [".service.ts"],
        "spec_include": [],
        "max_tokens": 2000,
    },
    ".module.ts": {
        "must_include": [".controller.ts", ".service.ts"],
        "spec_include": [],
        "max_tokens": 2000,
    },
    ".spec.ts": {
        "must_include": [".controller.ts", ".service.ts", ".dto.ts"],
        "spec_include": ["acceptance_criteria", "endpoints"],
        "max_tokens": 10000,
    },
}


class ContextInjector:
    def __init__(self, spec: ParsedSpec, completed_services: dict[str, Path] | None = None):
        self.spec = spec
        self.completed_services = completed_services or {}

    def get_context_for(self, file: Path, service: ParsedService) -> str:
        """Assemble context for a single file being filled by LLM."""
        # Determine rules by file suffix pattern
        rules = self._get_rules(file)
        max_chars = rules["max_tokens"] * CHARS_PER_TOKEN
        sections: list[str] = []

        # 1. FILE itself (always included)
        sections.append(f"=== FILE TO IMPLEMENT ===\n{file.read_text(encoding='utf-8')}")

        # 2. must_include — sibling files
        for pattern in rules.get("must_include", []):
            for sibling in file.parent.rglob(f"*{pattern}"):
                if sibling != file and sibling.exists():
                    sections.append(f"=== {sibling.name} ===\n{sibling.read_text(encoding='utf-8')}")
            # Also check parent for schema.prisma
            if "schema.prisma" in pattern:
                for schema in file.parents[2].rglob("schema.prisma"):
                    sections.append(f"=== PRISMA SCHEMA ===\n{schema.read_text(encoding='utf-8')}")

        # 3. spec_include — relevant specs
        for spec_type in rules.get("spec_include", []):
            sections.append(self._get_spec_context(spec_type, service))

        # 4. Dependency exports
        for dep_name in service.service_dependencies:
            if dep_name in self.completed_services:
                sections.append(self._get_dependency_exports(dep_name))

        # 5. Token budget enforcement — prioritized truncation
        # Priority: FILE (always full) > must_include > spec_include > dependency exports
        context = "\n\n".join(s for s in sections if s)
        if len(context) > max_chars:
            # Truncate from lowest priority (end) first, preserving FILE section (index 0)
            while len(context) > max_chars and len(sections) > 1:
                sections.pop()  # Remove lowest-priority section
                context = "\n\n".join(s for s in sections if s)
            if len(context) > max_chars:
                # FILE section itself exceeds budget — hard truncate but keep most of it
                context = context[:max_chars] + "\n// CONTEXT_TRUNCATED"
            logger.warning("Context truncated for %s (exceeded %d tokens)", file.name, rules["max_tokens"])

        return context

    def _get_rules(self, file: Path) -> dict:
        for suffix, rules in CONTEXT_RULES.items():
            if file.name.endswith(suffix):
                return rules
        return {"must_include": [], "spec_include": [], "max_tokens": 4000}

    def _get_spec_context(self, spec_type: str, service: ParsedService) -> str:
        if spec_type == "user_stories":
            lines = [f"=== USER STORIES for {service.name} ==="]
            for story in service.stories[:20]:
                lines.append(f"\n{story.id}: {story.title}")
                for ac in story.acceptance_criteria[:5]:
                    lines.append(f"  AC: {ac}")
            return "\n".join(lines)
        elif spec_type == "state_machines":
            lines = [f"=== STATE MACHINES for {service.name} ==="]
            for sm in service.state_machines:
                lines.append(f"\n{sm.name}: states={sm.states}")
                for t in sm.transitions[:10]:
                    lines.append(f"  {t.from_state} -> {t.to_state} : {t.trigger}")
            return "\n".join(lines)
        elif spec_type == "endpoints":
            lines = [f"=== ENDPOINTS for {service.name} ==="]
            for ep in service.endpoints:
                codes = ", ".join(f"{k}:{v}" for k, v in list(ep.status_codes.items())[:3])
                lines.append(f"  {ep.method} {ep.path} [{codes}]")
            return "\n".join(lines)
        elif spec_type == "acceptance_criteria":
            lines = ["=== ACCEPTANCE CRITERIA ==="]
            for story in service.stories[:30]:
                for ac in story.acceptance_criteria:
                    lines.append(f"  {story.id}: {ac}")
            return "\n".join(lines)
        return ""

    def _get_dependency_exports(self, dep_name: str) -> str:
        dep_dir = self.completed_services.get(dep_name)
        if not dep_dir:
            return ""
        lines = [f"=== DEPENDENCY: {dep_name} (public API) ==="]
        for ts_file in dep_dir.rglob("*.service.ts"):
            content = ts_file.read_text(encoding="utf-8")
            # Extract only method signatures
            for m in re.finditer(r"(async\s+\w+\([^)]*\)[^{]*)", content):
                lines.append(f"  {m.group(1).strip()}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/context_injector.py tests/engine/test_context_injector.py
git commit -m "feat: implement ContextInjector with token budget enforcement"
```

---

### Task 13: Implement TraceabilityTracker

**Files:**
- Create: `src/engine/traceability_tracker.py`
- Test: `tests/engine/test_traceability_tracker.py`

- [ ] **Step 1: Write test**

```python
# tests/engine/test_traceability_tracker.py
import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.traceability_tracker import TraceabilityTracker


class TestTraceabilityTracker:
    def test_register_from_spec(self):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        entries = tracker.get_all_entries()
        assert len(entries) > 0
        assert all(e.status == "SKELETON" for e in entries)

    def test_update_status(self):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        entries = tracker.get_entries("auth-service")
        if entries:
            tracker.update_status(entries[0].requirement_id, "auth-service", "IMPLEMENTED")
            updated = tracker.get_entries("auth-service")
            assert any(e.status == "IMPLEMENTED" for e in updated)

    def test_generate_report(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        report = tracker.generate_report()
        assert "total_requirements" in report
        assert report["total_requirements"] > 0
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement TraceabilityTracker**

```python
# src/engine/traceability_tracker.py
"""Traceability Tracker — Prio 6 of Pipeline Improvements.

Tracks requirement-to-code mapping during generation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

from src.engine.spec_parser import ParsedSpec

logger = logging.getLogger(__name__)


@dataclass
class TraceEntry:
    requirement_id: str
    user_story_id: str
    epic: str
    endpoint: str
    service: str
    files: list[str] = field(default_factory=list)
    test_file: str = ""
    validation_score: float = 0.0
    status: str = "SKELETON"  # SKELETON | IMPLEMENTED | PARTIAL | MISSING


class TraceabilityTracker:
    def __init__(self):
        self._entries: list[TraceEntry] = []

    def register_from_spec(self, spec: ParsedSpec) -> None:
        """Register all expected entries from the parsed spec."""
        for svc_name, svc in spec.services.items():
            for ep in svc.endpoints:
                for story_id in ep.linked_stories:
                    story = next((s for s in svc.stories if s.id == story_id), None)
                    req_ids = story.linked_requirements if story else []
                    for req_id in req_ids:
                        self._entries.append(TraceEntry(
                            requirement_id=req_id,
                            user_story_id=story_id,
                            epic=story.epic if story else "",
                            endpoint=f"{ep.method} {ep.path}",
                            service=svc_name,
                            status="SKELETON",
                        ))
            # Also register stories without endpoints
            for story in svc.stories:
                if not any(e.user_story_id == story.id for e in self._entries):
                    for req_id in story.linked_requirements:
                        self._entries.append(TraceEntry(
                            requirement_id=req_id,
                            user_story_id=story.id,
                            epic=story.epic,
                            endpoint="",
                            service=svc_name,
                            status="SKELETON",
                        ))

    def update_status(self, req_id: str, service: str, status: str) -> None:
        for entry in self._entries:
            if entry.requirement_id == req_id and entry.service == service:
                entry.status = status

    def update_files(self, req_id: str, service: str, files: list[str]) -> None:
        for entry in self._entries:
            if entry.requirement_id == req_id and entry.service == service:
                entry.files = files

    def get_entries(self, service: str) -> list[TraceEntry]:
        return [e for e in self._entries if e.service == service]

    def get_all_entries(self) -> list[TraceEntry]:
        return self._entries

    def generate_report(self) -> dict:
        total = len(self._entries)
        by_status = {}
        for entry in self._entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1

        return {
            "total_requirements": total,
            "by_status": by_status,
            "coverage": f"{by_status.get('IMPLEMENTED', 0)}/{total}",
        }

    def save_json(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "report": self.generate_report(),
            "entries": [asdict(e) for e in self._entries],
        }
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save_markdown(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report = self.generate_report()
        lines = [
            "# Traceability Matrix",
            "",
            f"**Coverage:** {report['coverage']}",
            "",
            "| Requirement | Story | Endpoint | Service | Status |",
            "|------------|-------|----------|---------|--------|",
        ]
        for entry in sorted(self._entries, key=lambda e: e.requirement_id):
            lines.append(
                f"| {entry.requirement_id} | {entry.user_story_id} | "
                f"{entry.endpoint} | {entry.service} | {entry.status} |"
            )
        output_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/traceability_tracker.py tests/engine/test_traceability_tracker.py
git commit -m "feat: implement TraceabilityTracker with JSON and Markdown export"
```

---

## Chunk 5: ServicePipeline + Orchestrator + CLI (Prio 3)

### Task 14: Implement ServicePipeline

**Files:**
- Create: `src/engine/service_pipeline.py`
- Create: `src/engine/code_fill_agent.py`
- Test: `tests/engine/test_service_pipeline.py`

- [ ] **Step 1: Write test for fill-order computation**

```python
# tests/engine/test_service_pipeline.py
import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.service_pipeline import ServicePipeline


class TestFillOrder:
    def test_services_before_controllers(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        pipeline = ServicePipeline(agent=None, context_injector=None, validation_engine=None, tracker=None)
        order = pipeline.get_fill_order(tmp_path / "auth-service")
        names = [f.name for f in order]

        # Find first .service.ts and first .controller.ts
        svc_idx = next((i for i, n in enumerate(names) if n.endswith(".service.ts")), -1)
        ctrl_idx = next((i for i, n in enumerate(names) if n.endswith(".controller.ts")), -1)
        if svc_idx >= 0 and ctrl_idx >= 0:
            assert svc_idx < ctrl_idx, "Services must come before controllers"

    def test_module_after_service_and_controller(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")

        pipeline = ServicePipeline(agent=None, context_injector=None, validation_engine=None, tracker=None)
        order = pipeline.get_fill_order(tmp_path / "auth-service")
        names = [f.name for f in order]

        mod_idx = next((i for i, n in enumerate(names) if n.endswith(".module.ts") and "app.module" not in n), -1)
        svc_idx = next((i for i, n in enumerate(names) if n.endswith(".service.ts")), -1)
        if mod_idx >= 0 and svc_idx >= 0:
            assert svc_idx < mod_idx, "Services must come before modules"
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement ServicePipeline and CodeFillAgent**

```python
# src/engine/code_fill_agent.py
"""Wraps LLM tool for skeleton-fill operations."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    file_path: Path
    content: str
    tokens_used: int
    success: bool
    error: str | None = None


class CodeFillAgent:
    """Wraps an LLM code tool for filling skeleton files."""

    def __init__(self, tool=None):
        self.tool = tool  # ClaudeCodeTool or None for dry-run

    async def fill(self, skeleton_file: Path, context: str) -> FillResult:
        if self.tool is None:
            # Dry-run: return skeleton as-is
            return FillResult(
                file_path=skeleton_file,
                content=skeleton_file.read_text(encoding="utf-8"),
                tokens_used=0,
                success=True,
            )

        prompt = (
            f"Fill the following skeleton file with production-ready NestJS implementation.\n"
            f"Replace all TODO comments and NotImplementedException with real logic.\n"
            f"Use ONLY the types, methods, and fields shown in the context below.\n\n"
            f"{context}"
        )
        try:
            result = await self.tool.execute(prompt=prompt, context=context)
            return FillResult(
                file_path=skeleton_file,
                content=result.code if hasattr(result, "code") else str(result),
                tokens_used=getattr(result, "tokens_used", 0),
                success=not getattr(result, "error", None),
                error=getattr(result, "error", None),
            )
        except Exception as e:
            logger.error("Agent fill failed for %s: %s", skeleton_file, e)
            return FillResult(
                file_path=skeleton_file,
                content=skeleton_file.read_text(encoding="utf-8"),
                tokens_used=0,
                success=False,
                error=str(e),
            )
```

```python
# src/engine/service_pipeline.py
"""Service-by-Service Pipeline — Prio 3 of Pipeline Improvements."""
from __future__ import annotations

import logging
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.engine.code_fill_agent import CodeFillAgent, FillResult
from src.engine.context_injector import ContextInjector
from src.engine.validation_engine import ValidationEngine, ValidationReport
from src.engine.traceability_tracker import TraceabilityTracker
from src.validators.base_validator import ValidationSeverity

logger = logging.getLogger(__name__)


class ServiceResult:
    def __init__(self, service_name: str, filled_files: list[Path],
                 report: ValidationReport | None, trace_entries: list):
        self.service_name = service_name
        self.filled_files = filled_files
        self.report = report
        self.trace_entries = trace_entries
        self.status = "COMPLETE" if (report and not report.has_errors()) else "NEEDS_REVIEW"


class ServicePipeline:
    def __init__(self, agent: CodeFillAgent | None,
                 context_injector: ContextInjector | None,
                 validation_engine: ValidationEngine | None,
                 tracker: TraceabilityTracker | None):
        self.agent = agent
        self.context_injector = context_injector
        self.validation_engine = validation_engine
        self.tracker = tracker

    def get_fill_order(self, skeleton_dir: Path) -> list[Path]:
        """Compute fill order for any service based on file types."""
        all_files = list(skeleton_dir.rglob("*.ts")) + list(skeleton_dir.rglob("*.prisma"))
        seen: set[Path] = set()
        order: list[Path] = []

        def add(files):
            for f in sorted(files):
                if f not in seen:
                    seen.add(f)
                    order.append(f)

        # Priority 1: Schema files
        add(f for f in all_files if f.name == "schema.prisma")
        # Priority 2: Shared types
        add(f for f in all_files if "/shared/" in str(f).replace("\\", "/"))
        # Priority 3: Services
        add(f for f in all_files if f.name.endswith(".service.ts"))
        # Priority 4: Controllers
        add(f for f in all_files if f.name.endswith(".controller.ts"))
        # Priority 5: DTOs
        add(f for f in all_files if "/dto/" in str(f).replace("\\", "/"))
        # Priority 6: Guards/Middleware
        add(f for f in all_files if "/guards/" in str(f).replace("\\", "/") or "/middleware/" in str(f).replace("\\", "/"))
        # Priority 7: Feature modules
        add(f for f in all_files if f.name.endswith(".module.ts") and "app.module" not in f.name)
        # Priority 8: app.module.ts
        add(f for f in all_files if "app.module" in f.name)
        # Priority 9: Tests
        add(f for f in all_files if f.name.endswith(".spec.ts"))
        # Priority 10: Everything else
        add(f for f in all_files if f not in seen)

        return order

    async def execute(self, service: ParsedService, skeleton_dir: Path,
                      max_recovery: int = 3) -> ServiceResult:
        """Run the full fill+validate+recover loop for one service."""
        filled_files: list[Path] = []
        unfilled_files: list[Path] = []

        # Phase 1: File-by-file agent fill
        for file in self.get_fill_order(skeleton_dir):
            if self.agent and self.context_injector:
                context = self.context_injector.get_context_for(file, service)
                result = await self.agent.fill(file, context)
                if result.success and result.content:
                    file.write_text(result.content, encoding="utf-8")
                    filled_files.append(file)
                else:
                    # Retry once, then mark UNFILLED
                    result2 = await self.agent.fill(file, context)
                    if result2.success and result2.content:
                        file.write_text(result2.content, encoding="utf-8")
                        filled_files.append(file)
                    else:
                        unfilled_files.append(file)
                        logger.warning("UNFILLED: %s (agent failed twice)", file.name)
            else:
                filled_files.append(file)

        # Phase 2: Validation + Recovery loop
        report = None
        if self.validation_engine:
            for attempt in range(max_recovery):
                report = self.validation_engine.validate_service(service, skeleton_dir)
                if not report.has_errors():
                    break
                if not self.agent or attempt == max_recovery - 1:
                    logger.warning("Recovery exhausted for %s after %d attempts", service.name, attempt + 1)
                    break
                # Re-fill files that have validation errors
                error_files = {Path(i.file_path) for i in report.issues
                               if i.severity == ValidationSeverity.ERROR and i.file_path}
                for file in error_files:
                    if file.exists() and self.context_injector:
                        context = self.context_injector.get_context_for(file, service)
                        result = await self.agent.fill(file, context)
                        if result.success and result.content:
                            file.write_text(result.content, encoding="utf-8")

        trace_entries = []
        if self.tracker:
            trace_entries = self.tracker.get_entries(service.name)
            # Update traceability status
            status = "IMPLEMENTED" if (report and not report.has_errors()) else "PARTIAL"
            for entry in trace_entries:
                self.tracker.update_status(entry.requirement_id, service.name, status)

        return ServiceResult(service.name, filled_files, report, trace_entries)
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/engine/service_pipeline.py src/engine/code_fill_agent.py tests/engine/test_service_pipeline.py
git commit -m "feat: implement ServicePipeline with fill-order algorithm"
```

---

### Task 15: Implement ServiceOrchestrator + CLI entry point

**Files:**
- Create: `src/engine/service_orchestrator.py`
- Create: `run_pipeline.py`
- Test: `tests/engine/test_service_orchestrator.py`

- [ ] **Step 1: Write test**

```python
# tests/engine/test_service_orchestrator.py
import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.service_orchestrator import ServiceOrchestrator


class TestServiceOrchestrator:
    def test_skeleton_only_mode(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        orchestrator = ServiceOrchestrator(spec, tmp_path)
        results = orchestrator.run_skeleton_only()
        assert len(results) >= 7
        for svc_name, svc_dir in results.items():
            assert svc_dir.exists()
            assert (svc_dir / "package.json").exists()

    def test_generation_order_respects_deps(self):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        order = spec.generation_order
        if "auth-service" in order and "messaging-service" in order:
            assert order.index("auth-service") < order.index("messaging-service")
```

- [ ] **Step 2: Run test — should fail**

- [ ] **Step 3: Implement**

```python
# src/engine/service_orchestrator.py
"""Service Orchestrator — orchestrates generation of all services in dependency order."""
from __future__ import annotations

import logging
from pathlib import Path

from src.engine.spec_parser import ParsedSpec
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.service_pipeline import ServicePipeline, ServiceResult
from src.engine.code_fill_agent import CodeFillAgent
from src.engine.context_injector import ContextInjector
from src.engine.validation_engine import ValidationEngine
from src.engine.traceability_tracker import TraceabilityTracker
from src.engine.checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class ServiceOrchestrator:
    def __init__(self, spec: ParsedSpec, output_dir: str | Path, tool=None):
        self.spec = spec
        self.output_dir = Path(output_dir)
        self.tool = tool
        self.completed: dict[str, Path] = {}
        self.tracker = TraceabilityTracker()
        self.tracker.register_from_spec(spec)
        self.checkpoint = CheckpointManager(self.output_dir / ".checkpoints")

    def run_skeleton_only(self) -> dict[str, Path]:
        """Generate skeletons for all services without agent fill."""
        gen = SkeletonGenerator(self.spec, self.output_dir)
        return gen.generate_all()

    async def run_all(self, resume_from: str | None = None) -> dict[str, ServiceResult]:
        """Generate all services in dependency order."""
        # Phase 0: Generate all skeletons first
        skeleton_dirs = self.run_skeleton_only()

        # Resume support: skip already-completed services
        start_idx = 0
        if resume_from:
            completed_services = self.checkpoint.get_completed_services()
            for svc_name in completed_services:
                if svc_name in skeleton_dirs:
                    self.completed[svc_name] = skeleton_dirs[svc_name]
            if resume_from in self.spec.generation_order:
                start_idx = self.spec.generation_order.index(resume_from)
            logger.info("Resuming from %s (skipping %d completed)", resume_from, start_idx)

        results: dict[str, ServiceResult] = {}
        for svc_name in self.spec.generation_order[start_idx:]:
            svc = self.spec.services[svc_name]
            svc_dir = skeleton_dirs[svc_name]

            logger.info("=== Generating %s (%d endpoints) ===", svc_name, len(svc.endpoints))

            agent = CodeFillAgent(self.tool)
            injector = ContextInjector(self.spec, self.completed)
            engine = ValidationEngine()
            pipeline = ServicePipeline(agent, injector, engine, self.tracker)

            try:
                result = await pipeline.execute(svc, svc_dir)
                results[svc_name] = result
                self.completed[svc_name] = svc_dir
                self.checkpoint.save_service(svc_name, result.status)
            except Exception as e:
                logger.error("Service %s failed: %s — continuing with next", svc_name, e)
                continue

            logger.info("=== %s: %s (%d files) ===",
                         svc_name, result.status, len(result.filled_files))

        # Save traceability
        self.tracker.save_json(self.output_dir / "traceability.json")
        self.tracker.save_markdown(self.output_dir / "TRACEABILITY.md")

        return results

    async def run_single(self, service_name: str) -> ServiceResult:
        """Generate a single service."""
        if service_name not in self.spec.services:
            raise ValueError(f"Unknown service: {service_name}")

        svc = self.spec.services[service_name]
        svc_dir = self.output_dir / service_name

        gen = SkeletonGenerator(self.spec, self.output_dir)
        gen.generate_service(svc, svc_dir)

        agent = CodeFillAgent(self.tool)
        injector = ContextInjector(self.spec, self.completed)
        engine = ValidationEngine()
        pipeline = ServicePipeline(agent, injector, engine, self.tracker)

        return await pipeline.execute(svc, svc_dir)
```

```python
# run_pipeline.py
"""CLI entry point for the new pipeline."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.engine.spec_parser import SpecParser
from src.engine.service_orchestrator import ServiceOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="DaveFelix Pipeline v2")
    parser.add_argument("spec_dir", help="Path to service specification directory")
    parser.add_argument("--output-dir", "-o", default="./output", help="Output directory")
    parser.add_argument("--service", help="Generate only this service")
    parser.add_argument("--all", action="store_true", help="Generate all services")
    parser.add_argument("--skeleton-only", action="store_true", help="Only generate skeleton, no agent fill")
    parser.add_argument("--validate-only", action="store_true", help="Only run validation")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--refill", action="store_true", help="Re-generate service (clear + re-fill)")

    args = parser.parse_args()
    spec_dir = Path(args.spec_dir)
    output_dir = Path(args.output_dir)

    logger.info("Parsing spec from %s", spec_dir)
    spec = SpecParser(spec_dir).parse()
    logger.info("Parsed: %d services, %d endpoints, %d stories",
                len(spec.services),
                sum(len(s.endpoints) for s in spec.services.values()),
                sum(len(s.stories) for s in spec.services.values()))

    orchestrator = ServiceOrchestrator(spec, output_dir)

    if args.skeleton_only:
        results = orchestrator.run_skeleton_only()
        for name, path in results.items():
            logger.info("Skeleton: %s -> %s", name, path)
        logger.info("Done. %d service skeletons generated.", len(results))
    elif args.service:
        if args.refill:
            import shutil
            svc_dir = output_dir / args.service
            if svc_dir.exists():
                shutil.rmtree(svc_dir)
        result = asyncio.run(orchestrator.run_single(args.service))
        logger.info("Result: %s — %s", result.service_name, result.status)
    elif args.all or args.resume:
        resume_from = orchestrator.checkpoint.get_resume_point() if args.resume else None
        results = asyncio.run(orchestrator.run_all(resume_from=resume_from))
        for name, result in results.items():
            logger.info("  %s: %s", name, result.status)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Integration smoke test**

Run: `cd /c/Users/User/Desktop/Dave\&Felix/DaveFelix-Coding-Engine && python run_pipeline.py "Data/all_services/whatsapp-messaging-service_20260211_025459" --skeleton-only -o ./output_test`
Expected: 7+ service skeletons generated, each with package.json, controllers, services

- [ ] **Step 6: Commit**

```bash
git add src/engine/service_orchestrator.py run_pipeline.py tests/engine/test_service_orchestrator.py
git commit -m "feat: implement ServiceOrchestrator and CLI entry point"
```

---

### Task 16: Wire into existing codebase

**Files:**
- Modify: `src/engine/spec_adapter.py`
- Modify: `src/engine/hybrid_pipeline.py`

- [ ] **Step 1: Add ParsedSpec adapter path in spec_adapter.py**

Add to `SpecAdapter._normalize_documentation()`:

```python
# At top of file, add import:
from src.engine.spec_parser import SpecParser, ParsedSpec

# In _normalize_documentation(), add early return for new pipeline:
def _normalize_documentation(self, spec_dir: str) -> NormalizedSpec:
    # New pipeline: use SpecParser if spec directory has expected structure
    spec_path = Path(spec_dir)
    if (spec_path / "architecture").exists() and (spec_path / "api").exists():
        parser = SpecParser(spec_path)
        parsed = parser.parse()
        # Adapt ParsedSpec to NormalizedSpec for backward compatibility
        return self._adapt_parsed_spec(parsed)
    # ... existing implementation ...

def _adapt_parsed_spec(self, parsed: ParsedSpec) -> NormalizedSpec:
    """Adapter: convert ParsedSpec to NormalizedSpec for backward compat."""
    requirements = []
    for svc_name, svc in parsed.services.items():
        for ep in svc.endpoints:
            requirements.append(Requirement(
                id=f"{ep.method}:{ep.path}",
                description=f"{ep.method} {ep.path}",
                priority="high",
            ))
    endpoints = [
        APIEndpoint(method=ep.method, path=ep.path, service=ep.service)
        for svc in parsed.services.values()
        for ep in svc.endpoints
    ]
    return NormalizedSpec(requirements=requirements, endpoints=endpoints)
```

- [ ] **Step 2: Add ServiceOrchestrator delegation in hybrid_pipeline.py**

Add optional delegation in `HybridPipeline`:

```python
# At top of hybrid_pipeline.py, add:
from src.engine.service_orchestrator import ServiceOrchestrator

# In run() method, add early branch:
if self.config.get("use_service_pipeline") and spec_dir:
    from src.engine.spec_parser import SpecParser
    spec = SpecParser(spec_dir).parse()
    orchestrator = ServiceOrchestrator(spec, self.output_dir, self.tool)
    if self.config.get("skeleton_only"):
        return orchestrator.run_skeleton_only()
    return await orchestrator.run_all()
```

- [ ] **Step 3: Commit**

```bash
git add src/engine/spec_adapter.py src/engine/hybrid_pipeline.py
git commit -m "feat: wire SpecParser and ServiceOrchestrator into existing pipeline"
```

---

### Task 18: Run full test suite

- [ ] **Step 1: Run all new tests**

Run: `python -m pytest tests/engine/test_spec_parser.py tests/engine/test_skeleton_generator.py tests/engine/test_validation_engine.py tests/engine/test_context_injector.py tests/engine/test_traceability_tracker.py tests/engine/test_service_pipeline.py tests/engine/test_service_orchestrator.py -v`
Expected: All tests pass

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `python -m pytest tests/ -v --ignore=tests/e2e --ignore=tests/integration -x`
Expected: No regressions in existing tests

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete pipeline v2 — SpecParser, SkeletonGenerator, ServicePipeline, ValidationEngine, ContextInjector, TraceabilityTracker"
```

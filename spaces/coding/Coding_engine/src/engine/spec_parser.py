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


class CyclicDependencyError(ValueError):
    """Raised when a cyclic dependency is detected in the service graph."""


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
    description: str
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
    project_name: str
    services: dict[str, ParsedService]
    shared_entities: list[ParsedEntity]
    dependency_graph: dict[str, list[str]]
    generation_order: list[str]
    openapi_version: str = "3.0.3"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

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

            deps_str = props.get("dependencies", "")
            all_deps = [d.strip() for d in deps_str.split(",") if d.strip()]

            # Separate infra deps from service deps
            infra_prefixes = ("postgres", "redis", "kafka", "s3", "kong", "websocket")
            infra_deps = [d for d in all_deps if any(d.startswith(p) for p in infra_prefixes)]
            service_deps = [d for d in all_deps if d not in infra_deps]

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

    def _parse_data_dictionary(self) -> list[ParsedEntity]:
        """Parse data/data_dictionary.md into ParsedEntity list."""
        dd_file = self.project_dir / "data" / "data_dictionary.md"
        if not dd_file.exists():
            logger.warning("data_dictionary.md not found")
            return []

        text = dd_file.read_text(encoding="utf-8")
        entities: list[ParsedEntity] = []
        entity_blocks = re.split(r"^### ", text, flags=re.MULTILINE)

        for block in entity_blocks[1:]:
            lines = block.strip().split("\n")
            entity_name = lines[0].strip()
            if not entity_name or entity_name.startswith("|") or entity_name.startswith("#"):
                continue

            fields: list[Field] = []
            relations: list[Relation] = []

            for line in lines:
                cols = [c.strip() for c in line.split("|")]
                if len(cols) < 9:
                    continue
                attr, ftype, _maxlen, required, fk_target, _indexed, _enum_vals, _desc = cols[1:9]
                if attr.lower() in ("attribute", "---", ""):
                    continue
                if "---" in ftype:
                    continue

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
                    unique=False,
                    default=None,
                ))

                if fk_target.strip() not in ("-", "", "—"):
                    parts = fk_target.strip().split(".")
                    if len(parts) == 2:
                        relations.append(Relation(
                            target=parts[0],
                            type="many-to-one",
                            field=attr.strip(),
                            inverse=None,
                        ))

            if fields:
                entities.append(ParsedEntity(
                    name=entity_name,
                    fields=fields,
                    relations=relations,
                    service="",
                ))

        return entities

    def _parse_user_stories(self) -> list[ParsedUserStory]:
        """Parse user_stories.json into ParsedUserStory list."""
        json_file = self.project_dir / "user_stories.json"
        if not json_file.exists():
            logger.warning("user_stories.json not found")
            return []

        data = json.loads(json_file.read_text(encoding="utf-8"))
        stories: list[ParsedUserStory] = []

        for us in data.get("user_stories", []):
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
                description=us.get("description", ""),
                acceptance_criteria=ac_list,
                linked_requirements=us.get("linked_requirement_ids", []),
                linked_endpoints=[],
            ))

        return stories

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
                        if 200 <= code < 300 and not resp_dto:
                            resp_content = resp_info.get("content", {})
                            for _ctype, schema_info in resp_content.items():
                                ref = schema_info.get("schema", {}).get("$ref", "")
                                if ref:
                                    resp_dto = ref.split("/")[-1]
                                break

                    security = details.get("security")
                    auth_required = security != []

                    endpoints.append(ParsedEndpoint(
                        method=method.upper(),
                        path=path,
                        service="",
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
        for match in re.finditer(r"####\s*`(\w+)`\s*(/\S+)", text):
            method = match.group(1).upper()
            path = match.group(2)
            endpoints.append(ParsedEndpoint(
                method=method, path=path, service="",
            ))
        return endpoints

    def _parse_state_machines(self) -> list[StateMachine]:
        """Parse state_machines/*.mmd into StateMachine list."""
        sm_dir = self.project_dir / "state_machines"
        if not sm_dir.exists():
            return []

        machines: list[StateMachine] = []
        for mmd_file in sorted(sm_dir.glob("*.mmd")):
            text = mmd_file.read_text(encoding="utf-8")
            name = mmd_file.stem

            states: set[str] = set()
            transitions: list[StateTransition] = []
            initial_state = ""
            terminal_states: list[str] = []

            for line in text.split("\n"):
                line = line.strip()
                m = re.match(
                    r"(\[?\*?\]?|\w+)\s*-->\s*(\[?\*?\]?|\w+)\s*(?::\s*(.+))?",
                    line,
                )
                if not m:
                    continue

                from_s = m.group(1).strip()
                to_s = m.group(2).strip()
                rest = m.group(3) or ""

                trigger = ""
                guard = None
                if rest:
                    parts = re.match(r"(\w+)(?:\s*\[([^\]]+)\])?\s*(?:/\s*(.+))?", rest)
                    if parts:
                        trigger = parts.group(1)
                        guard = parts.group(2)

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

    def parse(self) -> ParsedSpec:
        """Full parse: combine all sub-parsers into ParsedSpec."""
        services = self._parse_architecture()
        entities = self._parse_data_dictionary()
        self._assign_entities_to_services(entities, services)
        endpoints = self._parse_endpoints()
        self._assign_endpoints_to_services(endpoints, services)
        stories = self._parse_user_stories()
        self._assign_stories_to_services(stories, services)
        state_machines = self._parse_state_machines()
        self._assign_state_machines_to_services(state_machines, services)
        self._link_stories_to_endpoints(services)

        api_services = {
            k: v for k, v in services.items()
            if v.port > 0 and v.port < 10000
            and not k.startswith("postgres-") and not k.startswith("redis")
            and not k.startswith("kafka") and not k.startswith("s3-")
            and not k.startswith("kong")
        }

        dep_graph = self._build_dependency_graph(api_services)
        gen_order = self._topological_sort(dep_graph)

        return ParsedSpec(
            project_name=self.project_dir.name,
            services=api_services,
            shared_entities=[e for e in entities if not e.service],
            dependency_graph=dep_graph,
            generation_order=gen_order,
            openapi_version=getattr(self, "_openapi_version", "3.0.3"),
        )

    def _assign_entities_to_services(
        self, entities: list[ParsedEntity], services: dict[str, ParsedService],
    ) -> None:
        for entity in entities:
            for svc_name, svc in services.items():
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
        # Build path map from service names (strip -service/-worker suffixes)
        path_map: dict[str, str] = {}
        for svc_name in services:
            domain = svc_name.replace("-service", "").replace("-worker", "")
            path_map[f"/{domain}"] = svc_name

        # Additional keyword-to-service mapping for common REST resource names
        keyword_map: dict[str, str] = {}
        for svc_name in services:
            # map "user-profile" -> users, profiles, qr-codes, passkeys, devices, biometric
            # map "messaging" -> messages, conversations, reactions, forwards
            # map "chat" -> chats, groups, communities, broadcast
            # map "media" -> media, statuses, storage
            # map "auth" -> auth, phone-registrations, 2fa, biometric, passkeys
            pass

        # Extended semantic mapping based on common REST resource segments
        semantic_map: dict[str, str] = {
            "users": "user-profile-service",
            "profiles": "user-profile-service",
            "qr-codes": "user-profile-service",
            "passkeys": "auth-service",
            "biometric": "auth-service",
            "devices": "auth-service",
            "phone-registrations": "auth-service",
            "2fa": "auth-service",
            "messages": "messaging-service",
            "conversations": "messaging-service",
            "reactions": "messaging-service",
            "chats": "chat-service",
            "groups": "chat-service",
            "communities": "chat-service",
            "broadcast-lists": "chat-service",
            "broadcast-channels": "chat-service",
            "contacts": "user-profile-service",
            "calls": "chat-service",
            "group-calls": "chat-service",
            "media": "media-service",
            "storage": "media-service",
            "statuses": "media-service",
            "businesses": "user-profile-service",
            "integrations": "user-profile-service",
            "backups": "media-service",
            "chat-history-transfer-sessions": "chat-service",
            "watch-devices": "auth-service",
            "unknown-senders": "chat-service",
            "offline-queues": "messaging-service",
            "share-extensions": "media-service",
            "notifications": "notification-worker",
        }

        # Only use semantic_map entries where the service exists
        effective_semantic_map = {
            k: v for k, v in semantic_map.items() if v in services
        }

        for ep in endpoints:
            path_lower = ep.path.lower()
            assigned = False

            # 1. Try direct path pattern match (service name in path)
            for pattern, svc_name in path_map.items():
                if pattern in path_lower:
                    ep.service = svc_name
                    services[svc_name].endpoints.append(ep)
                    assigned = True
                    break

            if not assigned:
                # 2. Extract first meaningful segment after /api/vN/
                m = re.match(r"/api/v\d+/([^/]+)", ep.path)
                if m:
                    segment = m.group(1).lower()

                    # Try semantic map first
                    svc_name = effective_semantic_map.get(segment)
                    if svc_name:
                        ep.service = svc_name
                        services[svc_name].endpoints.append(ep)
                        assigned = True
                    else:
                        # Try substring match against service names
                        for svc_name in services:
                            if segment in svc_name or svc_name.replace("-service", "").replace("-worker", "") in segment:
                                ep.service = svc_name
                                services[svc_name].endpoints.append(ep)
                                assigned = True
                                break

    def _assign_stories_to_services(
        self, stories: list[ParsedUserStory], services: dict[str, ParsedService],
    ) -> None:
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
        for sm in machines:
            for svc_name, svc in services.items():
                entity_names = [e.name.lower() for e in svc.entities]
                if sm.entity.lower() in entity_names or sm.name.lower() in svc_name:
                    svc.state_machines.append(sm)
                    break

    def _link_stories_to_endpoints(self, services: dict[str, ParsedService]) -> None:
        for svc_name, svc in services.items():
            for story in svc.stories:
                for ep in svc.endpoints:
                    path_segments = [p for p in ep.path.split("/") if p and p not in ("api", "v1", "v2")]
                    if any(seg.lower() in story.title.lower() for seg in path_segments):
                        if story.id not in ep.linked_stories:
                            ep.linked_stories.append(story.id)
                        if f"{ep.method} {ep.path}" not in story.linked_endpoints:
                            story.linked_endpoints.append(f"{ep.method} {ep.path}")

    def _build_dependency_graph(self, services: dict[str, ParsedService]) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        service_names = set(services.keys())
        for svc_name, svc in services.items():
            deps = [d for d in svc.service_dependencies if d in service_names]
            graph[svc_name] = deps
        return graph

    def _topological_sort(self, graph: dict[str, list[str]]) -> list[str]:
        """Topological sort using Kahn's algorithm. Raises on cycles."""
        in_degree = {node: len(deps) for node, deps in graph.items()}

        queue = [node for node, deg in in_degree.items() if deg == 0]
        result: list[str] = []

        while queue:
            queue.sort()
            node = queue.pop(0)
            result.append(node)
            for other, deps in graph.items():
                if node in deps:
                    in_degree[other] -= 1
                    if in_degree[other] == 0 and other not in result:
                        queue.append(other)

        if len(result) != len(graph):
            missing = set(graph.keys()) - set(result)
            raise CyclicDependencyError(f"Cyclic dependency detected involving: {missing}")

        return result

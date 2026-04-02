# tests/engine/test_spec_parser.py
import pytest
from pathlib import Path
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
            project_name="test-project",
            services={}, shared_entities=[],
            dependency_graph={}, generation_order=["auth-service"],
            openapi_version="3.0.3",
        )
        assert spec.generation_order == ["auth-service"]


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
        assert any("websocket" in d for d in msg.dependencies) or any("websocket" in d for d in msg.service_dependencies)

    def test_total_services_count(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        services = parser._parse_architecture()
        api_services = {k: v for k, v in services.items() if v.port > 0}
        assert len(api_services) >= 7


class TestDataDictionaryParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_entities(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        entities = parser._parse_data_dictionary()
        assert len(entities) >= 40
        names = [e.name for e in entities]
        assert "User" in names or "user" in [n.lower() for n in names]

    def test_entity_has_fields(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        entities = parser._parse_data_dictionary()
        for entity in entities:
            if entity.name.lower() == "user" or "user" in entity.name.lower():
                assert len(entity.fields) > 0
                field_names = [f.name for f in entity.fields]
                assert any("id" in fn.lower() for fn in field_names)
                break

    def test_entity_relations(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        entities = parser._parse_data_dictionary()
        has_relations = [e for e in entities if len(e.relations) > 0]
        assert len(has_relations) > 0


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
        assert len(linked) > 100


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


class TestStateMachineParser:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_parse_state_machines(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        machines = parser._parse_state_machines()
        assert len(machines) >= 5
        names = [sm.name for sm in machines]
        assert any("message" in n.lower() for n in names)

    def test_state_machine_has_transitions(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        machines = parser._parse_state_machines()
        for sm in machines:
            if "message" in sm.name.lower():
                assert len(sm.transitions) >= 5
                assert len(sm.states) >= 4
                break


class TestFullParse:
    WHATSAPP_DIR = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")

    def test_full_parse(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        assert isinstance(spec, ParsedSpec)
        assert len(spec.services) >= 7
        assert len(spec.generation_order) >= 7

    def test_endpoints_assigned_to_services(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        total_endpoints = sum(len(s.endpoints) for s in spec.services.values())
        assert total_endpoints >= 200

    def test_no_cycles_in_dependency_graph(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        assert len(spec.generation_order) == len(spec.services)

    def test_parsed_spec_to_json(self):
        parser = SpecParser(self.WHATSAPP_DIR)
        spec = parser.parse()
        import json
        from dataclasses import asdict
        json_str = json.dumps(asdict(spec), indent=2, default=str)
        assert len(json_str) > 1000

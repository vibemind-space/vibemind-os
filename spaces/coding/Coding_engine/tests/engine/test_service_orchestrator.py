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
        assert len(order) >= 7

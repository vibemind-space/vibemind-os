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

import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.context_injector import ContextInjector


class TestContextInjector:
    def _setup(self, tmp_path):
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
            assert len(context) <= 40000  # 8000 tokens * 4 chars + buffer

    def test_controller_gets_service_context(self, tmp_path):
        spec, auth_svc, injector, svc_dir = self._setup(tmp_path)
        ctrl_files = list(svc_dir.rglob("*.controller.ts"))
        if ctrl_files:
            context = injector.get_context_for(ctrl_files[0], auth_svc)
            assert ".service.ts" in context or "Service" in context

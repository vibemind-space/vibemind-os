import pytest
import re
from pathlib import Path
from src.engine.spec_parser import SpecParser, ParsedSpec
from src.engine.skeleton_generator import SkeletonGenerator


class TestPrismaGeneration:
    def _get_spec(self) -> ParsedSpec:
        return SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()

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
        assert "model " in content


class TestControllerServiceGeneration:
    def _get_spec(self) -> ParsedSpec:
        return SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()

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
        controllers = list((tmp_path / "auth-service").rglob("*.controller.ts"))
        assert len(controllers) >= 1
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
        services_files = list((tmp_path / "auth-service").rglob("*.service.ts"))
        controllers = list((tmp_path / "auth-service").rglob("*.controller.ts"))
        svc_methods = set()
        for sf in services_files:
            for m in re.finditer(r"async\s+(\w+)\(", sf.read_text()):
                svc_methods.add(m.group(1))
        ctrl_calls = set()
        for cf in controllers:
            for m in re.finditer(r"this\.\w+Service\.(\w+)\(", cf.read_text()):
                ctrl_calls.add(m.group(1))
        missing = ctrl_calls - svc_methods
        assert len(missing) == 0, f"Controller calls methods not in service: {missing}"

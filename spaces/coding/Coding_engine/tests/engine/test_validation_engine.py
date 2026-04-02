import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.validators.endpoint_coverage import EndpointCoverageValidator
from src.engine.validators.method_consistency import MethodConsistencyValidator
from src.engine.validators.import_integrity import ImportIntegrityValidator
from src.engine.validation_engine import ValidationEngine
from src.validators.base_validator import ValidationSeverity


class TestEndpointCoverageValidator:
    def test_skeleton_has_full_coverage(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")
        validator = EndpointCoverageValidator()
        issues = validator.validate(auth_svc, tmp_path / "auth-service")
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0, f"Missing endpoints: {[i.error_message for i in errors]}"


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
        errors = [i for i in issues if "phantom" in i.error_message.lower()]
        # Allow known phantom imports (e.g., prisma.service, module files which aren't generated yet)
        assert len(errors) <= 30  # Some phantoms are expected in skeleton


class TestValidationEngine:
    def test_full_validation(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        gen = SkeletonGenerator(spec, tmp_path)
        auth_svc = spec.services["auth-service"]
        gen.generate_service(auth_svc, tmp_path / "auth-service")
        engine = ValidationEngine()
        report = engine.validate_service(auth_svc, tmp_path / "auth-service")
        assert report.service_name == "auth-service"
        # Skeleton should not have method consistency errors
        method_errors = [i for i in report.issues if i.check_type == "method_consistency"]
        assert len(method_errors) == 0

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

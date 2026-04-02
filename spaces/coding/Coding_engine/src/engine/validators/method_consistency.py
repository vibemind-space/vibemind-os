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
        service_methods: dict[str, set[str]] = {}
        for sf in code_dir.rglob("*.service.ts"):
            methods = set()
            for m in re.finditer(r"async\s+(\w+)\(", sf.read_text(encoding="utf-8")):
                methods.add(m.group(1))
            service_methods[sf.stem.replace(".service", "")] = methods
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

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

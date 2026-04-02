"""Heuristic check that acceptance criteria are likely implemented."""
from __future__ import annotations
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class AcceptanceCriteriaValidator(SpecValidator):
    name = "acceptance_criteria"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        if not service.stories:
            return issues
        total_acs = sum(len(s.acceptance_criteria) for s in service.stories)
        total_endpoints = len(service.endpoints)
        if total_endpoints == 0 and total_acs > 0:
            issues.append(ValidationFailure(check_type=self.name, error_message=f"Service has {total_acs} acceptance criteria but 0 endpoints", severity=ValidationSeverity.WARNING, file_path=str(code_dir)))
        return issues

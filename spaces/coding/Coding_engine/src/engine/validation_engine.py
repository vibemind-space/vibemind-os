"""Orchestrates all spec validators for a service."""
from __future__ import annotations
import logging
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.validators.base_validator import ValidationFailure, ValidationSeverity
from src.engine.validators.endpoint_coverage import EndpointCoverageValidator
from src.engine.validators.method_consistency import MethodConsistencyValidator
from src.engine.validators.import_integrity import ImportIntegrityValidator
from src.engine.validators.entity_schema import EntitySchemaValidator
from src.engine.validators.dto_completeness import DtoCompletenessValidator
from src.engine.validators.dependency_check import DependencyCheckValidator
from src.engine.validators.state_machine import StateMachineValidator
from src.engine.validators.acceptance_criteria import AcceptanceCriteriaValidator

logger = logging.getLogger(__name__)


class ValidationReport:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.issues: list[ValidationFailure] = []

    def has_errors(self) -> bool:
        return any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)

    def to_dict(self) -> dict:
        return {"service": self.service_name, "total_issues": len(self.issues), "errors": self.error_count}


class ValidationEngine:
    def __init__(self):
        self.validators = [
            EndpointCoverageValidator(),
            MethodConsistencyValidator(),
            ImportIntegrityValidator(),
            EntitySchemaValidator(),
            DtoCompletenessValidator(),
            DependencyCheckValidator(),
            StateMachineValidator(),
            AcceptanceCriteriaValidator(),
        ]

    def validate_service(self, service: ParsedService, code_dir: Path) -> ValidationReport:
        report = ValidationReport(service.name)
        for validator in self.validators:
            try:
                issues = validator.validate(service, code_dir)
                report.issues.extend(issues)
            except Exception as e:
                logger.error("Validator %s crashed: %s", validator.name, e)
                report.issues.append(ValidationFailure(
                    check_type=validator.name,
                    error_message=f"VALIDATOR_ERROR: {e}",
                    severity=ValidationSeverity.WARNING,
                ))
        return report

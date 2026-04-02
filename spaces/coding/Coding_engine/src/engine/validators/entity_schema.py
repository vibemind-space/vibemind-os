"""Validates Prisma schema matches data dictionary entities."""
from __future__ import annotations
import re
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class EntitySchemaValidator(SpecValidator):
    name = "entity_schema"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        schema_file = code_dir / "prisma" / "schema.prisma"
        if not schema_file.exists():
            if service.entities:
                issues.append(ValidationFailure(
                    check_type=self.name,
                    error_message="No schema.prisma but service has entities",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(code_dir),
                ))
            return issues
        content = schema_file.read_text(encoding="utf-8")
        model_names = set(re.findall(r"model\s+(\w+)\s*\{", content))
        for entity in service.entities:
            pascal_name = "".join(w.capitalize() for w in re.split(r"[-_]", entity.name))
            if pascal_name not in model_names:
                issues.append(ValidationFailure(
                    check_type=self.name,
                    error_message=f"Entity '{entity.name}' missing from Prisma schema (expected model {pascal_name})",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(schema_file),
                ))
        return issues

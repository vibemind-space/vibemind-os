"""Validates that local imports reference existing files."""
from __future__ import annotations
import re
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class ImportIntegrityValidator(SpecValidator):
    name = "import_integrity"
    severity = ValidationSeverity.ERROR

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        for ts_file in code_dir.rglob("*.ts"):
            content = ts_file.read_text(encoding="utf-8")
            for m in re.finditer(r"from\s+['\"](\.[^'\"]+)['\"]", content):
                import_path = m.group(1)
                resolved = (ts_file.parent / import_path).resolve()
                candidates = [resolved.with_suffix(".ts"), resolved.with_suffix(".js"), resolved / "index.ts", resolved]
                if not any(c.exists() for c in candidates):
                    issues.append(ValidationFailure(
                        check_type=self.name,
                        error_message=f"Phantom import: '{import_path}' from {ts_file.name}",
                        severity=self.severity,
                        file_path=str(ts_file),
                    ))
        return issues

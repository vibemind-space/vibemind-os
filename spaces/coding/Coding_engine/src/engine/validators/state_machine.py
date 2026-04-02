"""Validates code implements defined state transitions."""
from __future__ import annotations
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class StateMachineValidator(SpecValidator):
    name = "state_machine"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        if not service.state_machines:
            return issues
        all_code = ""
        for ts_file in code_dir.rglob("*.ts"):
            all_code += ts_file.read_text(encoding="utf-8")
        for sm in service.state_machines:
            found_states = [s for s in sm.states if s.lower() in all_code.lower()]
            if len(found_states) < len(sm.states) // 2:
                issues.append(ValidationFailure(check_type=self.name, error_message=f"State machine '{sm.name}': only {len(found_states)}/{len(sm.states)} states found in code", severity=ValidationSeverity.WARNING, file_path=str(code_dir)))
        return issues

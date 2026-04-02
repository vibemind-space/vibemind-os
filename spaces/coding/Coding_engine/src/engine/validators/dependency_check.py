"""Validates package.json has all used packages."""
from __future__ import annotations
import json
import re
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.engine.validators import SpecValidator
from src.validators.base_validator import ValidationFailure, ValidationSeverity


class DependencyCheckValidator(SpecValidator):
    name = "dependency_check"

    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        issues: list[ValidationFailure] = []
        pkg_file = code_dir / "package.json"
        if not pkg_file.exists():
            issues.append(ValidationFailure(check_type=self.name, error_message="Missing package.json", severity=ValidationSeverity.ERROR, file_path=str(code_dir)))
            return issues
        pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
        all_deps = set(pkg.get("dependencies", {}).keys()) | set(pkg.get("devDependencies", {}).keys())
        for ts_file in code_dir.rglob("*.ts"):
            content = ts_file.read_text(encoding="utf-8")
            for m in re.finditer(r"from\s+['\"]([^./][^'\"]*)['\"]", content):
                pkg_name = m.group(1).split("/")[0]
                if pkg_name.startswith("@"):
                    pkg_name = "/".join(m.group(1).split("/")[:2])
                if pkg_name not in all_deps and pkg_name not in ("fs", "path", "util", "crypto", "http", "https"):
                    issues.append(ValidationFailure(check_type=self.name, error_message=f"Package '{pkg_name}' used in {ts_file.name} but not in package.json", severity=ValidationSeverity.WARNING, file_path=str(ts_file)))
        return issues

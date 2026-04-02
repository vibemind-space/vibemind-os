"""
ContainerValidator - Validiert Fixes in isolierten Docker Containern

Dieser Modul stellt sicher, dass Code-Änderungen production-ready sind,
indem sie in isolierten Docker Containern validiert werden.

Features:
- Isolierte Validierung (keine lokale Umgebung-Kontamination)
- TypeScript/Node.js Build-Validierung
- Test-Ausführung in Containern
- Lint-Checks
"""

import asyncio
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ContainerResult:
    """Ergebnis einer Container-Ausführung"""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int = 0


@dataclass
class ValidationResult:
    """Ergebnis einer Validierung"""
    success: bool
    validation_type: str  # "typescript", "test", "lint", "docker_build"
    exit_code: int = 0
    output: str = ""
    errors: str = ""
    error_count: int = 0
    warning_count: int = 0
    duration_ms: int = 0
    container_name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ValidationConfig:
    """Konfiguration für Validierung"""
    project_path: str
    image: str = "node:18-alpine"
    timeout_seconds: int = 300
    install_deps: bool = True
    working_dir: str = "/app"


# ============================================================================
# Container Validator
# ============================================================================

class ContainerValidator:
    """
    Validiert Code-Änderungen in isolierten Docker Containern.

    Bietet:
    - TypeScript Kompilierung
    - Test-Ausführung
    - Lint-Checks
    - Docker Build Tests
    """

    # Build-Commands für verschiedene Validierungstypen
    VALIDATION_COMMANDS = {
        "typescript": "npm run build:server",
        "typescript_full": "npm run build",
        "test": "npm test",
        "test_unit": "npm run test:unit",
        "lint": "npm run lint",
        "typecheck": "npx tsc --noEmit",
        "prisma_generate": "npx prisma generate",
        "prisma_validate": "npx prisma validate"
    }

    def __init__(
        self,
        project_path: str,
        image: str = "node:18-alpine",
        timeout_seconds: int = 300
    ):
        """
        Initialisiert den ContainerValidator.

        Args:
            project_path: Pfad zum Projekt
            image: Docker Image für Container
            timeout_seconds: Timeout für Container-Operationen
        """
        self.project_path = Path(project_path).resolve()
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.container_name = f"validator-{uuid.uuid4().hex[:8]}"

        self._container_id: Optional[str] = None
        self._stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "total_duration_ms": 0
        }

        logger.info(f"ContainerValidator initialisiert: {self.project_path}")

    def _docker_available(self) -> bool:
        """Prüft ob Docker verfügbar ist"""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _convert_path_for_docker(self, path: Path) -> str:
        """Konvertiert Windows-Pfad für Docker Mount"""
        path_str = str(path.resolve())

        # Windows: C:\Users\... -> /c/Users/...
        if os.name == 'nt' and len(path_str) >= 2 and path_str[1] == ':':
            drive = path_str[0].lower()
            rest = path_str[2:].replace('\\', '/')
            return f"/{drive}{rest}"

        return path_str

    async def _run_docker_command(
        self,
        command: List[str],
        timeout: Optional[int] = None
    ) -> ContainerResult:
        """Führt Docker-Befehl aus"""
        timeout = timeout or self.timeout_seconds
        start_time = datetime.now()

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return ContainerResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode('utf-8', errors='replace'),
                stderr=stderr.decode('utf-8', errors='replace'),
                duration_ms=duration_ms
            )

        except asyncio.TimeoutError:
            # Kill container on timeout
            try:
                await asyncio.create_subprocess_exec(
                    "docker", "kill", self.container_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
            except Exception:
                pass

            return ContainerResult(
                exit_code=-1,
                stdout="",
                stderr=f"Timeout after {timeout} seconds",
                duration_ms=timeout * 1000
            )

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return ContainerResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms
            )

    async def validate_fix(
        self,
        validation_type: str = "typescript",
        custom_command: Optional[str] = None,
        install_deps: bool = True
    ) -> ValidationResult:
        """
        Validiert einen Fix in einem isolierten Container.

        Args:
            validation_type: Art der Validierung (typescript, test, lint, etc.)
            custom_command: Optionaler benutzerdefinierter Befehl
            install_deps: Ob npm install ausgeführt werden soll

        Returns:
            ValidationResult mit Details
        """
        self._stats["total_validations"] += 1
        start_time = datetime.now()

        # Docker verfügbar?
        if not self._docker_available():
            logger.warning("Docker nicht verfügbar - Fallback zu lokaler Validierung")
            return await self._local_validation(validation_type, custom_command)

        # Command bestimmen
        if custom_command:
            build_command = custom_command
        elif validation_type in self.VALIDATION_COMMANDS:
            build_command = self.VALIDATION_COMMANDS[validation_type]
        else:
            return ValidationResult(
                success=False,
                validation_type=validation_type,
                errors=f"Unbekannter Validierungstyp: {validation_type}"
            )

        try:
            # Container-Pfad für Mount
            mount_path = self._convert_path_for_docker(self.project_path)

            # Full command: Install + Build
            if install_deps:
                full_command = f"npm ci --legacy-peer-deps 2>/dev/null || npm install && {build_command}"
            else:
                full_command = build_command

            # Docker run command
            docker_cmd = [
                "docker", "run",
                "--rm",  # Auto-remove container
                "--name", self.container_name,
                "-v", f"{mount_path}:/app",
                "-w", "/app",
                "--network", "none",  # Isolation
                self.image,
                "sh", "-c", full_command
            ]

            logger.info(f"Running validation: {validation_type}")
            logger.debug(f"Command: {' '.join(docker_cmd)}")

            result = await self._run_docker_command(docker_cmd)

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._stats["total_duration_ms"] += duration_ms

            # Errors zählen (TypeScript-spezifisch)
            error_count = 0
            warning_count = 0

            if validation_type.startswith("typescript"):
                # TypeScript Errors zählen
                combined_output = result.stdout + result.stderr
                error_count = combined_output.count("error TS")
                warning_count = combined_output.count("warning TS")

            success = result.exit_code == 0

            if success:
                self._stats["successful_validations"] += 1
                logger.info(f"Validation successful: {validation_type}")
            else:
                self._stats["failed_validations"] += 1
                logger.warning(f"Validation failed: {validation_type} ({error_count} errors)")

            return ValidationResult(
                success=success,
                validation_type=validation_type,
                exit_code=result.exit_code,
                output=result.stdout,
                errors=result.stderr,
                error_count=error_count,
                warning_count=warning_count,
                duration_ms=duration_ms,
                container_name=self.container_name
            )

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._stats["failed_validations"] += 1

            logger.error(f"Validation error: {e}")

            return ValidationResult(
                success=False,
                validation_type=validation_type,
                exit_code=-1,
                errors=str(e),
                duration_ms=duration_ms
            )

    async def _local_validation(
        self,
        validation_type: str,
        custom_command: Optional[str] = None
    ) -> ValidationResult:
        """Fallback: Lokale Validierung ohne Docker"""
        start_time = datetime.now()

        # Command bestimmen
        if custom_command:
            build_command = custom_command
        elif validation_type in self.VALIDATION_COMMANDS:
            build_command = self.VALIDATION_COMMANDS[validation_type]
        else:
            return ValidationResult(
                success=False,
                validation_type=validation_type,
                errors=f"Unbekannter Validierungstyp: {validation_type}"
            )

        try:
            # Use shell=True for npm commands on Windows
            process = await asyncio.create_subprocess_shell(
                build_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path)
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')

            # Errors zählen
            combined = stdout_str + stderr_str
            error_count = combined.count("error TS")
            warning_count = combined.count("warning TS")

            success = process.returncode == 0

            if success:
                self._stats["successful_validations"] += 1
            else:
                self._stats["failed_validations"] += 1

            return ValidationResult(
                success=success,
                validation_type=f"{validation_type}_local",
                exit_code=process.returncode or 0,
                output=stdout_str,
                errors=stderr_str,
                error_count=error_count,
                warning_count=warning_count,
                duration_ms=duration_ms
            )

        except asyncio.TimeoutError:
            return ValidationResult(
                success=False,
                validation_type=f"{validation_type}_local",
                exit_code=-1,
                errors=f"Timeout after {self.timeout_seconds} seconds"
            )

        except Exception as e:
            return ValidationResult(
                success=False,
                validation_type=f"{validation_type}_local",
                exit_code=-1,
                errors=str(e)
            )

    async def validate_typescript(self, install_deps: bool = True) -> ValidationResult:
        """Validiert TypeScript-Kompilierung"""
        return await self.validate_fix("typescript", install_deps=install_deps)

    async def validate_tests(self, install_deps: bool = True) -> ValidationResult:
        """Führt Tests aus"""
        return await self.validate_fix("test", install_deps=install_deps)

    async def validate_lint(self, install_deps: bool = True) -> ValidationResult:
        """Führt Lint-Check aus"""
        return await self.validate_fix("lint", install_deps=install_deps)

    async def full_validation(self, install_deps: bool = True) -> Dict[str, ValidationResult]:
        """
        Führt vollständige Validierung durch (TypeScript + Tests + Lint).

        Returns:
            Dict mit Ergebnissen für jeden Validierungstyp
        """
        results = {}

        # TypeScript zuerst (kritisch)
        results["typescript"] = await self.validate_fix("typescript", install_deps=install_deps)

        if not results["typescript"].success:
            # Bei TypeScript-Fehlern abbrechen
            return results

        # Tests
        results["test"] = await self.validate_fix("test", install_deps=False)

        # Lint (optional)
        results["lint"] = await self.validate_fix("lint", install_deps=False)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            **self._stats,
            "success_rate": (
                self._stats["successful_validations"] /
                max(1, self._stats["total_validations"])
            )
        }

    def extract_typescript_errors(self, validation_result: ValidationResult) -> List[Dict[str, Any]]:
        """
        Extrahiert strukturierte TypeScript-Fehler aus dem Validierungsergebnis.

        Returns:
            Liste von Fehlern mit file, line, code, message
        """
        errors = []
        combined = validation_result.output + validation_result.errors

        # Pattern: src/file.ts(10,5): error TS2339: Property 'x' does not exist
        import re
        pattern = r"([^\s]+\.tsx?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)"

        for match in re.finditer(pattern, combined):
            errors.append({
                "file": match.group(1),
                "line": int(match.group(2)),
                "column": int(match.group(3)),
                "severity": match.group(4),
                "code": match.group(5),
                "message": match.group(6).strip()
            })

        return errors


# ============================================================================
# Test
# ============================================================================

async def test_container_validator():
    """Test-Funktion"""
    print("=== ContainerValidator Test ===\n")

    # Pfad zum Test-Projekt
    test_project = "c:/Users/User/Desktop/Coding_engine/autonomes_billing_v1"

    if not Path(test_project).exists():
        print(f"Test-Projekt nicht gefunden: {test_project}")
        return

    validator = ContainerValidator(
        project_path=test_project,
        timeout_seconds=300
    )

    print(f"Project: {validator.project_path}")
    print(f"Docker available: {validator._docker_available()}")
    print()

    # Test 1: TypeScript Validation
    print("Test 1: TypeScript Validation")
    result = await validator.validate_typescript(install_deps=True)
    print(f"  Success: {result.success}")
    print(f"  Exit code: {result.exit_code}")
    print(f"  Error count: {result.error_count}")
    print(f"  Duration: {result.duration_ms}ms")

    if not result.success:
        errors = validator.extract_typescript_errors(result)
        print(f"  Extracted errors: {len(errors)}")
        for err in errors[:5]:
            print(f"    {err['file']}:{err['line']} - {err['code']}: {err['message'][:50]}")
    print()

    # Stats
    print("Stats:")
    stats = validator.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(test_container_validator())

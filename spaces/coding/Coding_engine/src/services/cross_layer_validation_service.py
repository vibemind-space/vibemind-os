# -*- coding: utf-8 -*-
"""
Cross-Layer Validation Service - Phase 23

Pure static analysis that validates frontend-backend consistency:
1. API Route Alignment - FE fetch/axios URLs match BE controller routes
2. DTO Field Alignment - FE TypeScript interfaces match BE DTOs
3. Security Consistency - Hash functions match their compare functions
4. Import Resolution - FE imports resolve to existing files

No LLM/MCMP needed - regex-based source scanning. Fast and deterministic.
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------


class CrossLayerCheckMode(str, Enum):
    """Validation check modes."""
    API_ROUTE_ALIGNMENT = "api_route_alignment"
    DTO_FIELD_ALIGNMENT = "dto_field_alignment"
    SECURITY_CONSISTENCY = "security_consistency"
    IMPORT_RESOLUTION = "import_resolution"
    FULL = "full"


class FindingSeverity(str, Enum):
    """Severity of a cross-layer finding."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class CrossLayerFinding:
    """A single cross-layer validation finding."""
    check_mode: CrossLayerCheckMode
    severity: str
    frontend_file: str
    backend_file: str
    description: str
    suggestion: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_mode": self.check_mode.value if isinstance(self.check_mode, Enum) else self.check_mode,
            "severity": self.severity,
            "frontend_file": self.frontend_file,
            "backend_file": self.backend_file,
            "description": self.description,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class CrossLayerReport:
    """Aggregated cross-layer validation report."""
    findings: List[CrossLayerFinding] = field(default_factory=list)
    routes_checked: int = 0
    routes_aligned: int = 0
    dtos_checked: int = 0
    dtos_aligned: int = 0
    security_issues: int = 0
    import_issues: int = 0
    alignment_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "routes_checked": self.routes_checked,
            "routes_aligned": self.routes_aligned,
            "dtos_checked": self.dtos_checked,
            "dtos_aligned": self.dtos_aligned,
            "security_issues": self.security_issues,
            "import_issues": self.import_issues,
            "alignment_score": self.alignment_score,
            "total_findings": len(self.findings),
            "critical_count": sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL),
            "high_count": sum(1 for f in self.findings if f.severity == FindingSeverity.HIGH),
        }


# ---------------------------------------------------------------------------
# Regex Patterns for TypeScript/NestJS Source Scanning
# ---------------------------------------------------------------------------

# Frontend: fetch('/api/...') or axios.get('/api/...') etc.
RE_FETCH_URL = re.compile(
    r"""(?:fetch|axios\.(?:get|post|put|patch|delete))\s*\(\s*[`'"](\/api\/[^`'"]+)[`'"]""",
    re.MULTILINE,
)

# Frontend: template literal fetch(`/api/v1/users/${userId}/pin`)
RE_FETCH_TEMPLATE = re.compile(
    r"""(?:fetch|axios\.(?:get|post|put|patch|delete))\s*\(\s*`(\/api\/[^`]+)`""",
    re.MULTILINE,
)

# Backend NestJS: @Controller('prefix')
RE_CONTROLLER_PREFIX = re.compile(
    r"""@Controller\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# Backend NestJS: @Get('path'), @Post('path'), @Put('path'), @Delete('path'), @Patch('path')
RE_ROUTE_DECORATOR = re.compile(
    r"""@(Get|Post|Put|Delete|Patch)\s*\(\s*(?:['"]([^'"]*)['"]\s*)?\)""",
    re.MULTILINE,
)

# TypeScript interface fields: fieldName: Type or fieldName?: Type
RE_TS_INTERFACE_FIELD = re.compile(
    r"""^\s+(\w+)\s*(\?)?\s*:\s*([^;/\n]+)""",
    re.MULTILINE,
)

# TypeScript interface declaration
RE_TS_INTERFACE = re.compile(
    r"""(?:export\s+)?(?:interface|type)\s+(\w+)(?:\s+extends\s+\w+)?\s*\{([^}]+)\}""",
    re.DOTALL,
)

# class-validator DTO fields: @IsString() \n fieldName: string
RE_DTO_FIELD = re.compile(
    r"""@Is\w+\([^)]*\).*?\n\s+(\w+)\s*(\?)?\s*:\s*([^;/\n]+)""",
    re.DOTALL,
)

# DTO class declaration
RE_DTO_CLASS = re.compile(
    r"""export\s+class\s+(\w+(?:Dto|DTO|Request|Response))\s*(?:extends\s+\w+\s*)?\{""",
    re.MULTILINE,
)

# bcrypt hash/compare
RE_BCRYPT_HASH = re.compile(r"""bcrypt\.hash\s*\(""", re.MULTILINE)
RE_BCRYPT_COMPARE = re.compile(r"""bcrypt\.compare\s*\(""", re.MULTILINE)

# Plain text comparison for sensitive fields (pin, password, secret, token)
RE_PLAIN_COMPARE = re.compile(
    r"""(?:\.(?:pinCode|password|secret|token|hash|pin))\s*(!==|===|!=|==)\s*""",
    re.MULTILINE,
)

# crypto.createHash / timingSafeEqual
RE_CRYPTO_HASH = re.compile(r"""crypto\.createHash\s*\(\s*['"](\w+)['"]\s*\)""")
RE_TIMING_SAFE = re.compile(r"""timingSafeEqual\s*\(""")

# TypeScript imports
RE_TS_IMPORT = re.compile(
    r"""import\s+(?:\{[^}]+\}|\w+|\*\s+as\s+\w+)\s+from\s+['"](\.[^'"]+)['"]""",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CrossLayerValidationService:
    """
    Validates cross-layer consistency between frontend and backend code.

    Pure static analysis - no LLM or API keys required.
    """

    def __init__(
        self,
        project_dir: str,
        event_bus: Optional[Any] = None,
        enable_supermemory: bool = False,
    ):
        self._project_dir = Path(project_dir)
        self._event_bus = event_bus
        self._running = False

        # Source file caches
        self._frontend_files: List[Path] = []
        self._backend_files: List[Path] = []
        self._all_ts_files: List[Path] = []

    async def start(self) -> bool:
        """Initialize the service and index project files."""
        if not self._project_dir.exists():
            logger.warning("project_dir_not_found", path=str(self._project_dir))
            return False

        self._index_files()
        self._running = True
        logger.info(
            "cross_layer_service_started",
            project_dir=str(self._project_dir),
            frontend_files=len(self._frontend_files),
            backend_files=len(self._backend_files),
        )
        return True

    async def stop(self) -> None:
        """Stop the service."""
        self._running = False
        self._frontend_files.clear()
        self._backend_files.clear()
        self._all_ts_files.clear()

    async def run_validation(
        self,
        mode: CrossLayerCheckMode = CrossLayerCheckMode.FULL,
    ) -> CrossLayerReport:
        """Run cross-layer validation checks."""
        if not self._running:
            await self.start()

        report = CrossLayerReport()

        if mode in (CrossLayerCheckMode.FULL, CrossLayerCheckMode.API_ROUTE_ALIGNMENT):
            self._check_api_routes(report)

        if mode in (CrossLayerCheckMode.FULL, CrossLayerCheckMode.DTO_FIELD_ALIGNMENT):
            self._check_dto_alignment(report)

        if mode in (CrossLayerCheckMode.FULL, CrossLayerCheckMode.SECURITY_CONSISTENCY):
            self._check_security_consistency(report)

        if mode in (CrossLayerCheckMode.FULL, CrossLayerCheckMode.IMPORT_RESOLUTION):
            self._check_import_resolution(report)

        # Compute alignment score
        total_checks = (
            report.routes_checked
            + report.dtos_checked
            + (1 if report.security_issues == 0 else 0)
        )
        aligned = (
            report.routes_aligned
            + report.dtos_aligned
            + (1 if report.security_issues == 0 else 0)
        )
        report.alignment_score = (aligned / total_checks * 100) if total_checks > 0 else 100.0

        logger.info(
            "cross_layer_validation_complete",
            findings=len(report.findings),
            alignment_score=f"{report.alignment_score:.1f}%",
            critical=sum(1 for f in report.findings if f.severity == FindingSeverity.CRITICAL),
        )
        return report

    # ------------------------------------------------------------------
    # File Indexing
    # ------------------------------------------------------------------

    def _index_files(self) -> None:
        """Index frontend and backend TypeScript files."""
        src_dir = self._project_dir / "src"
        if not src_dir.exists():
            return

        self._all_ts_files = []
        self._frontend_files = []
        self._backend_files = []

        fe_dirs = {"api", "components", "hooks", "pages", "stores", "views"}
        be_dirs = {"modules", "guards", "lib", "middleware", "interceptors"}

        for ts_file in src_dir.rglob("*.ts"):
            if "node_modules" in str(ts_file) or "generated" in str(ts_file):
                continue
            self._all_ts_files.append(ts_file)
            rel = ts_file.relative_to(src_dir)
            top_dir = rel.parts[0] if len(rel.parts) > 1 else ""
            if top_dir in fe_dirs:
                self._frontend_files.append(ts_file)
            elif top_dir in be_dirs:
                self._backend_files.append(ts_file)

        for tsx_file in src_dir.rglob("*.tsx"):
            if "node_modules" in str(tsx_file) or "generated" in str(tsx_file):
                continue
            self._all_ts_files.append(tsx_file)
            self._frontend_files.append(tsx_file)

    def _read_file(self, path: Path) -> str:
        """Read file content safely."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            return ""

    # ------------------------------------------------------------------
    # Check 1: API Route Alignment
    # ------------------------------------------------------------------

    def _check_api_routes(self, report: CrossLayerReport) -> None:
        """Check that frontend API calls match backend controller routes."""
        fe_routes = self._extract_frontend_routes()
        be_routes = self._extract_backend_routes()

        report.routes_checked = len(fe_routes)
        matched = 0

        for fe_route, fe_file in fe_routes.items():
            # Normalize: strip trailing slashes, normalize param placeholders
            normalized_fe = self._normalize_route(fe_route)

            found = False
            for be_route in be_routes:
                normalized_be = self._normalize_route(be_route)
                if normalized_fe == normalized_be:
                    found = True
                    break

            if found:
                matched += 1
            else:
                # Find closest backend route for suggestion
                closest = self._find_closest_route(normalized_fe, be_routes.keys())
                suggestion = f"Update to '{closest}'" if closest else "No matching backend route found"

                report.findings.append(CrossLayerFinding(
                    check_mode=CrossLayerCheckMode.API_ROUTE_ALIGNMENT,
                    severity=FindingSeverity.CRITICAL,
                    frontend_file=str(fe_file.relative_to(self._project_dir)),
                    backend_file="(no match)",
                    description=f"Frontend calls '{fe_route}' but no backend route matches",
                    suggestion=suggestion,
                    confidence=0.95,
                ))

        report.routes_aligned = matched

    def _extract_frontend_routes(self) -> Dict[str, Path]:
        """Extract API routes from frontend files."""
        routes: Dict[str, Path] = {}
        for f in self._frontend_files:
            content = self._read_file(f)
            for match in RE_FETCH_URL.finditer(content):
                url = match.group(1)
                routes[url] = f
            for match in RE_FETCH_TEMPLATE.finditer(content):
                # Normalize template literals: /api/v1/users/${userId} → /api/v1/users/:param
                url = re.sub(r'\$\{[^}]+\}', ':param', match.group(1))
                routes[url] = f
        return routes

    def _extract_backend_routes(self) -> Dict[str, Path]:
        """Extract routes from NestJS controllers."""
        routes: Dict[str, Path] = {}
        for f in self._backend_files:
            if not f.name.endswith(".controller.ts"):
                continue
            content = self._read_file(f)

            # Find controller prefix
            prefix_match = RE_CONTROLLER_PREFIX.search(content)
            prefix = prefix_match.group(1) if prefix_match else ""

            # Find route decorators
            for match in RE_ROUTE_DECORATOR.finditer(content):
                path = match.group(2) or ""
                # Build full route
                full = f"/api/v1/{prefix}"
                if path:
                    full = f"{full}/{path}"
                # Clean double slashes
                full = re.sub(r'/+', '/', full)
                # NestJS params :id → :param for comparison
                full = re.sub(r':(\w+)', ':param', full)
                routes[full] = f

        return routes

    def _normalize_route(self, route: str) -> str:
        """Normalize a route for comparison."""
        route = route.rstrip("/")
        route = re.sub(r':(\w+)', ':param', route)
        route = re.sub(r'/+', '/', route)
        return route.lower()

    def _find_closest_route(self, target: str, candidates: Any) -> Optional[str]:
        """Find the most similar route from candidates."""
        target_parts = target.split("/")
        best_match = None
        best_score = 0

        for candidate in candidates:
            candidate_parts = self._normalize_route(candidate).split("/")
            # Count matching segments
            score = sum(
                1 for a, b in zip(target_parts, candidate_parts) if a == b
            )
            if score > best_score:
                best_score = score
                best_match = candidate

        return best_match if best_score >= 2 else None

    # ------------------------------------------------------------------
    # Check 2: DTO Field Alignment
    # ------------------------------------------------------------------

    def _check_dto_alignment(self, report: CrossLayerReport) -> None:
        """Check that frontend interfaces match backend DTOs."""
        fe_interfaces = self._extract_frontend_interfaces()
        be_dtos = self._extract_backend_dtos()

        report.dtos_checked = 0
        report.dtos_aligned = 0

        # Match FE interfaces to BE DTOs by name similarity
        for fe_name, fe_fields in fe_interfaces.items():
            for be_name, (be_fields, be_file) in be_dtos.items():
                if not self._names_match(fe_name, be_name):
                    continue

                report.dtos_checked += 1
                fe_field_names = set(fe_fields.keys())
                be_field_names = set(be_fields.keys())

                missing_in_fe = be_field_names - fe_field_names
                missing_in_be = fe_field_names - be_field_names

                if not missing_in_fe and not missing_in_be:
                    report.dtos_aligned += 1
                    continue

                # Check type mismatches for common fields
                common = fe_field_names & be_field_names
                type_mismatches = []
                for fname in common:
                    fe_type = fe_fields[fname].strip()
                    be_type = be_fields[fname].strip()
                    if not self._types_compatible(fe_type, be_type):
                        type_mismatches.append(f"{fname}: FE={fe_type} vs BE={be_type}")

                if missing_in_fe or missing_in_be or type_mismatches:
                    parts = []
                    if missing_in_fe:
                        parts.append(f"FE missing fields: {missing_in_fe}")
                    if missing_in_be:
                        parts.append(f"BE missing fields: {missing_in_be}")
                    if type_mismatches:
                        parts.append(f"Type mismatches: {type_mismatches}")

                    severity = FindingSeverity.HIGH if missing_in_fe or missing_in_be else FindingSeverity.MEDIUM
                    report.findings.append(CrossLayerFinding(
                        check_mode=CrossLayerCheckMode.DTO_FIELD_ALIGNMENT,
                        severity=severity,
                        frontend_file=fe_name,
                        backend_file=str(be_file.relative_to(self._project_dir)) if isinstance(be_file, Path) else be_name,
                        description=f"DTO mismatch between {fe_name} and {be_name}: {'; '.join(parts)}",
                        suggestion=f"Align fields between frontend interface and backend DTO",
                        confidence=0.85,
                    ))

    def _extract_frontend_interfaces(self) -> Dict[str, Dict[str, str]]:
        """Extract TypeScript interfaces from frontend files."""
        interfaces: Dict[str, Dict[str, str]] = {}
        for f in self._frontend_files:
            content = self._read_file(f)
            for match in RE_TS_INTERFACE.finditer(content):
                name = match.group(1)
                body = match.group(2)
                fields = {}
                for field_match in RE_TS_INTERFACE_FIELD.finditer(body):
                    fields[field_match.group(1)] = field_match.group(3).strip()
                if fields:
                    interfaces[name] = fields
        return interfaces

    def _extract_backend_dtos(self) -> Dict[str, Tuple[Dict[str, str], Path]]:
        """Extract DTO classes from backend files."""
        dtos: Dict[str, Tuple[Dict[str, str], Path]] = {}
        for f in self._backend_files:
            if "dto" not in str(f):
                continue
            content = self._read_file(f)

            # Find DTO class names
            for class_match in RE_DTO_CLASS.finditer(content):
                class_name = class_match.group(1)
                # Extract fields after class declaration
                class_start = class_match.end()
                # Find matching closing brace
                brace_count = 1
                pos = class_start
                while pos < len(content) and brace_count > 0:
                    if content[pos] == "{":
                        brace_count += 1
                    elif content[pos] == "}":
                        brace_count -= 1
                    pos += 1
                class_body = content[class_start:pos]

                fields = {}
                for field_match in RE_TS_INTERFACE_FIELD.finditer(class_body):
                    fields[field_match.group(1)] = field_match.group(3).strip()

                if fields:
                    dtos[class_name] = (fields, f)

        return dtos

    def _names_match(self, fe_name: str, be_name: str) -> bool:
        """Check if a frontend interface name matches a backend DTO name."""
        fe_lower = fe_name.lower().replace("interface", "").replace("type", "")
        be_lower = be_name.lower().replace("dto", "").replace("request", "req").replace("response", "res")

        # Reject very short names (too generic to match meaningfully)
        if len(fe_lower) <= 3 or len(be_lower) <= 3:
            return False

        # Direct substring match
        if fe_lower in be_lower or be_lower in fe_lower:
            return True

        # Strip common suffixes and compare
        fe_core = re.sub(r'(request|response|input|output|data|props)$', '', fe_lower)
        be_core = re.sub(r'(request|response|input|output|data)$', '', be_lower)

        return fe_core == be_core and len(fe_core) > 3

    def _types_compatible(self, fe_type: str, be_type: str) -> bool:
        """Check if TypeScript types are compatible."""
        fe = fe_type.strip().lower().rstrip(";")
        be = be_type.strip().lower().rstrip(";")
        if fe == be:
            return True
        # Common equivalences
        equivalences = {
            "number": {"number", "int", "integer", "float", "double"},
            "string": {"string", "text", "varchar", "uuid"},
            "boolean": {"boolean", "bool"},
            "date": {"date", "datetime", "string"},
        }
        for group in equivalences.values():
            if fe in group and be in group:
                return True
        return False

    # ------------------------------------------------------------------
    # Check 3: Security Consistency
    # ------------------------------------------------------------------

    def _check_security_consistency(self, report: CrossLayerReport) -> None:
        """Check that hash and compare operations are consistent."""
        issues = 0

        for f in self._backend_files:
            content = self._read_file(f)
            rel_path = str(f.relative_to(self._project_dir))

            has_bcrypt_hash = bool(RE_BCRYPT_HASH.search(content))
            has_bcrypt_compare = bool(RE_BCRYPT_COMPARE.search(content))
            has_plain_compare = bool(RE_PLAIN_COMPARE.search(content))
            has_crypto_hash = bool(RE_CRYPTO_HASH.search(content))
            has_timing_safe = bool(RE_TIMING_SAFE.search(content))

            # Issue: bcrypt hash used somewhere but plain comparison in this file
            if has_plain_compare and not has_bcrypt_compare:
                # Find the exact plain comparison for context
                for match in RE_PLAIN_COMPARE.finditer(content):
                    report.findings.append(CrossLayerFinding(
                        check_mode=CrossLayerCheckMode.SECURITY_CONSISTENCY,
                        severity=FindingSeverity.CRITICAL,
                        frontend_file="(n/a)",
                        backend_file=rel_path,
                        description=f"Plain-text comparison of sensitive field found: '{match.group(0).strip()}'. Should use bcrypt.compare() or timingSafeEqual()",
                        suggestion="Replace direct comparison with bcrypt.compare() for hashed fields or crypto.timingSafeEqual() for HMAC",
                        confidence=1.0,
                    ))
                    issues += 1

            # Issue: crypto hash without timing-safe comparison
            if has_crypto_hash and not has_timing_safe:
                report.findings.append(CrossLayerFinding(
                    check_mode=CrossLayerCheckMode.SECURITY_CONSISTENCY,
                    severity=FindingSeverity.HIGH,
                    frontend_file="(n/a)",
                    backend_file=rel_path,
                    description="crypto.createHash() used without timingSafeEqual() - vulnerable to timing attacks",
                    suggestion="Use crypto.timingSafeEqual() instead of === for hash comparison",
                    confidence=0.9,
                ))
                issues += 1

        # Cross-file check: find files that hash but never compare with bcrypt
        hashers: List[str] = []
        comparers: List[str] = []
        for f in self._backend_files:
            content = self._read_file(f)
            if RE_BCRYPT_HASH.search(content):
                hashers.append(str(f.relative_to(self._project_dir)))
            if RE_BCRYPT_COMPARE.search(content):
                comparers.append(str(f.relative_to(self._project_dir)))

        if hashers and not comparers:
            report.findings.append(CrossLayerFinding(
                check_mode=CrossLayerCheckMode.SECURITY_CONSISTENCY,
                severity=FindingSeverity.CRITICAL,
                frontend_file="(n/a)",
                backend_file=", ".join(hashers),
                description=f"bcrypt.hash() used in {hashers} but bcrypt.compare() not found in any backend file",
                suggestion="Add bcrypt.compare() in authentication service to verify hashed values",
                confidence=0.9,
            ))
            issues += 1

        report.security_issues = issues

    # ------------------------------------------------------------------
    # Check 4: Import Resolution
    # ------------------------------------------------------------------

    def _check_import_resolution(self, report: CrossLayerReport) -> None:
        """Check that TypeScript imports resolve to existing files."""
        issues = 0

        for f in self._all_ts_files:
            content = self._read_file(f)
            for match in RE_TS_IMPORT.finditer(content):
                import_path = match.group(1)
                if not self._resolve_import(f, import_path):
                    report.findings.append(CrossLayerFinding(
                        check_mode=CrossLayerCheckMode.IMPORT_RESOLUTION,
                        severity=FindingSeverity.HIGH,
                        frontend_file=str(f.relative_to(self._project_dir)),
                        backend_file="(n/a)",
                        description=f"Import '{import_path}' cannot be resolved to an existing file",
                        suggestion=f"Create the missing file or fix the import path",
                        confidence=1.0,
                    ))
                    issues += 1

        report.import_issues = issues

    def _resolve_import(self, source_file: Path, import_path: str) -> bool:
        """Try to resolve a relative import to an existing file."""
        # Strip .js/.ts extension if present
        import_path = re.sub(r'\.(js|ts|tsx)$', '', import_path)

        base_dir = source_file.parent
        target = (base_dir / import_path).resolve()

        # Try exact file with extensions
        for ext in [".ts", ".tsx", ".js", ".jsx", ".d.ts"]:
            if (target.parent / (target.name + ext)).exists():
                return True

        # Try index file
        if target.is_dir():
            for ext in [".ts", ".tsx", ".js"]:
                if (target / f"index{ext}").exists():
                    return True

        # Try as directory with index
        target_as_dir = target
        for ext in [".ts", ".tsx", ".js"]:
            if (target_as_dir / f"index{ext}").exists():
                return True

        return False

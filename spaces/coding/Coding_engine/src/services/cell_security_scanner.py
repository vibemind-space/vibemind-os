"""
Cell Security Scanner Service - Comprehensive security scanning for cells.

Provides automated security analysis:
- Static Application Security Testing (SAST)
- Dependency vulnerability scanning
- Secret/credential detection
- Sandbox behavior analysis
- Risk score calculation
- OWASP Top 10 pattern detection
"""

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

import structlog

from src.security.supply_chain import SupplyChainSecurity, SBOMGenerator, VulnerabilityScanner, CVE, SBOM, SeverityLevel
from src.mind.event_bus import EventBus, Event

logger = structlog.get_logger()


class ScanType(str, Enum):
    """Types of security scans."""
    SAST = "sast"  # Static Application Security Testing
    DEPENDENCY = "dependency"  # Dependency vulnerability scan
    SECRET = "secret"  # Secret/credential detection
    BEHAVIOR = "behavior"  # Runtime behavior analysis
    LICENSE = "license"  # License compliance
    FULL = "full"  # All scan types


class FindingSeverity(str, Enum):
    """Severity levels for security findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(str, Enum):
    """Categories of security findings (OWASP-aligned)."""
    INJECTION = "injection"  # A03:2021
    BROKEN_AUTH = "broken_auth"  # A07:2021
    SENSITIVE_DATA = "sensitive_data"  # A02:2021
    XXE = "xxe"  # A05:2021
    BROKEN_ACCESS = "broken_access"  # A01:2021
    MISCONFIG = "misconfig"  # A05:2021
    XSS = "xss"  # A03:2021
    INSECURE_DESERIALIZATION = "insecure_deserialization"  # A08:2021
    VULNERABLE_COMPONENT = "vulnerable_component"  # A06:2021
    LOGGING_FAILURE = "logging_failure"  # A09:2021
    SSRF = "ssrf"  # A10:2021
    HARDCODED_SECRET = "hardcoded_secret"
    INSECURE_DEPENDENCY = "insecure_dependency"
    LICENSE_VIOLATION = "license_violation"
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior"


@dataclass
class SecurityFinding:
    """Represents a single security finding."""
    id: str
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    cwe_id: Optional[str] = None  # Common Weakness Enumeration ID
    owasp_category: Optional[str] = None
    remediation: Optional[str] = None
    confidence: float = 1.0  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
            "remediation": self.remediation,
            "confidence": self.confidence,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class ScanResult:
    """Result of a security scan."""
    scan_id: str
    cell_id: str
    scan_type: ScanType
    started_at: datetime
    completed_at: Optional[datetime] = None
    findings: List[SecurityFinding] = field(default_factory=list)
    risk_score: float = 0.0  # 0-100
    summary: Dict[str, int] = field(default_factory=dict)
    passed: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return len([f for f in self.findings if f.severity == FindingSeverity.CRITICAL])

    @property
    def high_count(self) -> int:
        return len([f for f in self.findings if f.severity == FindingSeverity.HIGH])

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scan_id": self.scan_id,
            "cell_id": self.cell_id,
            "scan_type": self.scan_type.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "findings": [f.to_dict() for f in self.findings],
            "risk_score": self.risk_score,
            "summary": self.summary,
            "passed": self.passed,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


class SASTScanner:
    """Static Application Security Testing scanner."""

    # OWASP-aligned vulnerability patterns
    VULNERABILITY_PATTERNS = {
        # SQL Injection patterns
        FindingCategory.INJECTION: [
            (r"execute\s*\(\s*['\"].*%s", "SQL Injection via string formatting", "CWE-89"),
            (r"cursor\.execute\s*\(\s*f['\"]", "SQL Injection via f-string", "CWE-89"),
            (r"\.raw\s*\(\s*['\"].*\+", "Raw SQL with concatenation", "CWE-89"),
            (r"SELECT.*\+\s*request\.", "SQL query with user input concatenation", "CWE-89"),
            (r"subprocess\.(run|call|Popen)\s*\(.*shell\s*=\s*True", "Command Injection", "CWE-78"),
            (r"eval\s*\(\s*request\.", "Code Injection via eval", "CWE-94"),
            (r"exec\s*\(\s*request\.", "Code Injection via exec", "CWE-94"),
        ],
        # XSS patterns
        FindingCategory.XSS: [
            (r"\.innerHTML\s*=\s*(?!['\"<])", "Potential XSS via innerHTML", "CWE-79"),
            (r"document\.write\s*\(", "XSS via document.write", "CWE-79"),
            (r"\{\{\s*.*\s*\|\s*safe\s*\}\}", "Unsafe template rendering", "CWE-79"),
            (r"dangerouslySetInnerHTML", "React dangerouslySetInnerHTML usage", "CWE-79"),
        ],
        # Broken Authentication
        FindingCategory.BROKEN_AUTH: [
            (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password", "CWE-798"),
            (r"jwt\.decode\s*\(.*verify\s*=\s*False", "JWT verification disabled", "CWE-347"),
            (r"session\s*\[\s*['\"].*['\"]\s*\]\s*=\s*True", "Insecure session handling", "CWE-384"),
        ],
        # Sensitive Data Exposure
        FindingCategory.SENSITIVE_DATA: [
            (r"logging\.(debug|info|warning|error)\s*\(.*password", "Password in logs", "CWE-532"),
            (r"console\.log\s*\(.*password", "Password in console output", "CWE-532"),
            (r"http://(?!localhost|127\.0\.0\.1)", "HTTP URL (not HTTPS)", "CWE-319"),
        ],
        # Broken Access Control
        FindingCategory.BROKEN_ACCESS: [
            (r"@app\.route.*methods=\[.*\](?!.*@login_required)", "Unprotected route", "CWE-862"),
            (r"os\.chmod\s*\(.*0o777", "Overly permissive file permissions", "CWE-732"),
        ],
        # Security Misconfiguration
        FindingCategory.MISCONFIG: [
            (r"DEBUG\s*=\s*True", "Debug mode enabled", "CWE-489"),
            (r"CORS\s*\(.*origins\s*=\s*['\"]?\*", "CORS allows all origins", "CWE-942"),
            (r"verify\s*=\s*False", "SSL verification disabled", "CWE-295"),
            (r"ssl_verify\s*=\s*False", "SSL verification disabled", "CWE-295"),
        ],
        # Insecure Deserialization
        FindingCategory.INSECURE_DESERIALIZATION: [
            (r"pickle\.load[s]?\s*\(", "Unsafe pickle deserialization", "CWE-502"),
            (r"yaml\.load\s*\((?!.*Loader=yaml\.SafeLoader)", "Unsafe YAML loading", "CWE-502"),
            (r"json\.loads?\s*\(.*encoding", "Potential JSON deserialization issue", "CWE-502"),
        ],
        # SSRF
        FindingCategory.SSRF: [
            (r"requests\.(get|post|put|delete)\s*\(\s*request\.", "SSRF via user-controlled URL", "CWE-918"),
            (r"urllib\.request\.urlopen\s*\(\s*request\.", "SSRF via urllib", "CWE-918"),
        ],
    }

    # Secret patterns
    SECRET_PATTERNS = [
        (r"['\"](?:sk_live_|sk_test_)[a-zA-Z0-9]{24,}['\"]", "Stripe API Key", FindingSeverity.CRITICAL),
        (r"['\"]AKIA[0-9A-Z]{16}['\"]", "AWS Access Key ID", FindingSeverity.CRITICAL),
        (r"['\"][0-9a-zA-Z/+]{40}['\"]", "AWS Secret Access Key (potential)", FindingSeverity.HIGH),
        (r"['\"]ghp_[a-zA-Z0-9]{36}['\"]", "GitHub Personal Access Token", FindingSeverity.CRITICAL),
        (r"['\"]gho_[a-zA-Z0-9]{36}['\"]", "GitHub OAuth Token", FindingSeverity.CRITICAL),
        (r"['\"]xox[baprs]-[a-zA-Z0-9-]+['\"]", "Slack Token", FindingSeverity.CRITICAL),
        (r"['\"]-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "Private Key", FindingSeverity.CRITICAL),
        (r"['\"]AIza[0-9A-Za-z\-_]{35}['\"]", "Google API Key", FindingSeverity.HIGH),
        (r"api[_-]?key['\"]?\s*[:=]\s*['\"][a-zA-Z0-9]{16,}['\"]", "Generic API Key", FindingSeverity.MEDIUM),
        (r"bearer\s+[a-zA-Z0-9\-._~+/]+=*", "Bearer Token", FindingSeverity.HIGH),
        (r"password['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]", "Hardcoded Password", FindingSeverity.HIGH),
    ]

    def __init__(self):
        self.logger = logger.bind(component="SASTScanner")

    async def scan(self, project_path: Path) -> List[SecurityFinding]:
        """Scan project for SAST vulnerabilities."""
        self.logger.info("Starting SAST scan", path=str(project_path))
        findings: List[SecurityFinding] = []

        # Supported file extensions
        extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php"}

        # Walk through all files
        for root, dirs, files in os.walk(project_path):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in {
                "node_modules", ".git", "venv", ".venv", "__pycache__",
                "dist", "build", ".next", "coverage"
            }]

            for file in files:
                if Path(file).suffix not in extensions:
                    continue

                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    file_findings = await self._scan_file(file_path, content)
                    findings.extend(file_findings)
                except Exception as e:
                    self.logger.warning("Failed to scan file", file=str(file_path), error=str(e))

        self.logger.info("SAST scan complete", findings=len(findings))
        return findings

    async def _scan_file(self, file_path: Path, content: str) -> List[SecurityFinding]:
        """Scan a single file for vulnerabilities."""
        findings: List[SecurityFinding] = []
        lines = content.split("\n")

        # Check vulnerability patterns
        for category, patterns in self.VULNERABILITY_PATTERNS.items():
            for pattern, title, cwe_id in patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(SecurityFinding(
                            id=str(uuid.uuid4()),
                            category=category,
                            severity=self._categorize_severity(category),
                            title=title,
                            description=f"Potential {category.value} vulnerability detected",
                            file_path=str(file_path),
                            line_number=i,
                            code_snippet=line.strip()[:200],
                            cwe_id=cwe_id,
                            remediation=self._get_remediation(category),
                        ))

        # Check secret patterns
        for pattern, title, severity in self.SECRET_PATTERNS:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    # Mask the actual secret in the snippet
                    masked_line = re.sub(pattern, "[REDACTED]", line)
                    findings.append(SecurityFinding(
                        id=str(uuid.uuid4()),
                        category=FindingCategory.HARDCODED_SECRET,
                        severity=severity,
                        title=title,
                        description="Hardcoded secret or credential detected",
                        file_path=str(file_path),
                        line_number=i,
                        code_snippet=masked_line.strip()[:200],
                        cwe_id="CWE-798",
                        remediation="Move secrets to environment variables or a secrets manager",
                    ))

        return findings

    def _categorize_severity(self, category: FindingCategory) -> FindingSeverity:
        """Map category to default severity."""
        critical = {FindingCategory.INJECTION, FindingCategory.BROKEN_AUTH}
        high = {FindingCategory.XSS, FindingCategory.SENSITIVE_DATA, FindingCategory.INSECURE_DESERIALIZATION}
        medium = {FindingCategory.BROKEN_ACCESS, FindingCategory.SSRF}

        if category in critical:
            return FindingSeverity.CRITICAL
        elif category in high:
            return FindingSeverity.HIGH
        elif category in medium:
            return FindingSeverity.MEDIUM
        return FindingSeverity.LOW

    def _get_remediation(self, category: FindingCategory) -> str:
        """Get remediation advice for category."""
        remediations = {
            FindingCategory.INJECTION: "Use parameterized queries or ORM methods. Never concatenate user input into queries.",
            FindingCategory.XSS: "Sanitize and encode all user input. Use Content Security Policy headers.",
            FindingCategory.BROKEN_AUTH: "Use secure authentication mechanisms. Never hardcode credentials.",
            FindingCategory.SENSITIVE_DATA: "Encrypt sensitive data. Use HTTPS. Never log credentials.",
            FindingCategory.BROKEN_ACCESS: "Implement proper authorization checks on all endpoints.",
            FindingCategory.MISCONFIG: "Review and harden security configuration. Disable debug mode in production.",
            FindingCategory.INSECURE_DESERIALIZATION: "Use safe deserialization methods. Validate input before deserializing.",
            FindingCategory.SSRF: "Validate and sanitize user-provided URLs. Use allowlists for external requests.",
        }
        return remediations.get(category, "Review and fix the identified security issue.")


class BehaviorAnalyzer:
    """Analyze runtime behavior of cells for suspicious activity."""

    # Suspicious behavior patterns
    SUSPICIOUS_PATTERNS = {
        "network": [
            "connect_to_external_ip",
            "dns_exfiltration",
            "reverse_shell",
            "crypto_mining_pool",
        ],
        "filesystem": [
            "write_to_sensitive_path",
            "read_ssh_keys",
            "modify_crontab",
            "access_password_file",
        ],
        "process": [
            "spawn_shell",
            "privilege_escalation",
            "disable_security",
        ],
    }

    def __init__(self):
        self.logger = logger.bind(component="BehaviorAnalyzer")

    async def analyze(
        self,
        cell_id: str,
        logs: List[str],
        network_connections: List[Dict[str, Any]],
        file_accesses: List[Dict[str, Any]],
    ) -> List[SecurityFinding]:
        """Analyze cell behavior for suspicious activity."""
        findings: List[SecurityFinding] = []

        # Analyze network connections
        for conn in network_connections:
            if self._is_suspicious_connection(conn):
                findings.append(SecurityFinding(
                    id=str(uuid.uuid4()),
                    category=FindingCategory.SUSPICIOUS_BEHAVIOR,
                    severity=FindingSeverity.HIGH,
                    title="Suspicious Network Connection",
                    description=f"Connection to suspicious destination: {conn.get('destination')}",
                    metadata=conn,
                ))

        # Analyze file accesses
        for access in file_accesses:
            if self._is_suspicious_file_access(access):
                findings.append(SecurityFinding(
                    id=str(uuid.uuid4()),
                    category=FindingCategory.SUSPICIOUS_BEHAVIOR,
                    severity=FindingSeverity.CRITICAL,
                    title="Suspicious File Access",
                    description=f"Access to sensitive file: {access.get('path')}",
                    metadata=access,
                ))

        # Analyze logs for suspicious patterns
        for log in logs:
            finding = self._analyze_log_line(log)
            if finding:
                findings.append(finding)

        return findings

    def _is_suspicious_connection(self, conn: Dict[str, Any]) -> bool:
        """Check if network connection is suspicious."""
        destination = conn.get("destination", "")
        port = conn.get("port", 0)

        # Known suspicious ports
        suspicious_ports = {4444, 5555, 6666, 7777, 8888, 9999}  # Common reverse shell ports
        crypto_ports = {3333, 14444, 45560}  # Mining pool ports

        if port in suspicious_ports or port in crypto_ports:
            return True

        # Check for crypto mining pool domains
        mining_domains = ["pool.", "mining.", "stratum."]
        if any(domain in destination.lower() for domain in mining_domains):
            return True

        return False

    def _is_suspicious_file_access(self, access: Dict[str, Any]) -> bool:
        """Check if file access is suspicious."""
        path = access.get("path", "").lower()
        operation = access.get("operation", "")

        sensitive_paths = [
            "/etc/shadow",
            "/etc/passwd",
            "/.ssh/",
            "/root/",
            "/etc/crontab",
            "id_rsa",
            "id_ed25519",
        ]

        return any(s in path for s in sensitive_paths) and operation in ("read", "write")

    def _analyze_log_line(self, log: str) -> Optional[SecurityFinding]:
        """Analyze a log line for suspicious patterns."""
        suspicious_keywords = [
            ("reverse shell", FindingSeverity.CRITICAL),
            ("privilege escalation", FindingSeverity.CRITICAL),
            ("password dump", FindingSeverity.CRITICAL),
            ("cryptominer", FindingSeverity.HIGH),
            ("unauthorized access", FindingSeverity.HIGH),
        ]

        log_lower = log.lower()
        for keyword, severity in suspicious_keywords:
            if keyword in log_lower:
                return SecurityFinding(
                    id=str(uuid.uuid4()),
                    category=FindingCategory.SUSPICIOUS_BEHAVIOR,
                    severity=severity,
                    title=f"Suspicious Log Entry: {keyword}",
                    description=log[:500],
                )

        return None


class CellSecurityScanner:
    """
    Comprehensive security scanner for cells.

    Integrates multiple scanning capabilities:
    - SAST scanning for code vulnerabilities
    - Dependency vulnerability scanning
    - Secret detection
    - Behavior analysis
    - License compliance checking
    - Risk scoring
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
    ):
        self.logger = logger.bind(component="CellSecurityScanner")
        self.event_bus = event_bus
        self.sast_scanner = SASTScanner()
        self.behavior_analyzer = BehaviorAnalyzer()

        # Risk score weights
        self._severity_weights = {
            FindingSeverity.CRITICAL: 25,
            FindingSeverity.HIGH: 15,
            FindingSeverity.MEDIUM: 5,
            FindingSeverity.LOW: 1,
            FindingSeverity.INFO: 0,
        }

        # Thresholds for pass/fail
        self._max_critical = 0
        self._max_high = 3
        self._max_risk_score = 50

    async def scan_cell(
        self,
        cell_id: str,
        project_path: Path,
        scan_type: ScanType = ScanType.FULL,
    ) -> ScanResult:
        """
        Perform security scan on a cell.

        Args:
            cell_id: Cell identifier
            project_path: Path to cell's code
            scan_type: Type of scan to perform

        Returns:
            ScanResult with findings and risk score
        """
        self.logger.info("Starting cell security scan", cell_id=cell_id, type=scan_type.value)

        result = ScanResult(
            scan_id=str(uuid.uuid4()),
            cell_id=cell_id,
            scan_type=scan_type,
            started_at=datetime.now(timezone.utc),
        )

        try:
            all_findings: List[SecurityFinding] = []

            # SAST scan
            if scan_type in (ScanType.FULL, ScanType.SAST, ScanType.SECRET):
                sast_findings = await self.sast_scanner.scan(project_path)
                all_findings.extend(sast_findings)

            # Dependency scan
            if scan_type in (ScanType.FULL, ScanType.DEPENDENCY):
                dep_findings = await self._scan_dependencies(project_path)
                all_findings.extend(dep_findings)

            # License check
            if scan_type in (ScanType.FULL, ScanType.LICENSE):
                license_findings = await self._check_licenses(project_path)
                all_findings.extend(license_findings)

            # Calculate results
            result.findings = all_findings
            result.risk_score = self._calculate_risk_score(all_findings)
            result.summary = self._summarize_findings(all_findings)
            result.passed = self._evaluate_pass_fail(all_findings, result.risk_score)
            result.completed_at = datetime.now(timezone.utc)

            # Emit event
            if self.event_bus:
                await self.event_bus.publish(Event(
                    type="SECURITY_SCAN_COMPLETED",
                    source=f"scanner:{cell_id}",
                    data=result.to_dict(),
                ))

            self.logger.info(
                "Security scan complete",
                cell_id=cell_id,
                findings=len(all_findings),
                risk_score=result.risk_score,
                passed=result.passed,
            )

        except Exception as e:
            result.error = str(e)
            result.passed = False
            result.completed_at = datetime.now(timezone.utc)
            self.logger.error("Security scan failed", cell_id=cell_id, error=str(e))

        return result

    async def _scan_dependencies(self, project_path: Path) -> List[SecurityFinding]:
        """Scan dependencies for vulnerabilities."""
        findings: List[SecurityFinding] = []

        try:
            supply_chain = SupplyChainSecurity(project_path)
            sbom = await supply_chain.generate_sbom()
            cves = await supply_chain.scan_dependencies(sbom)

            for cve in cves:
                severity = self._map_cve_severity(cve.severity)
                findings.append(SecurityFinding(
                    id=str(uuid.uuid4()),
                    category=FindingCategory.VULNERABLE_COMPONENT,
                    severity=severity,
                    title=f"{cve.id}: {cve.package_name}",
                    description=cve.summary,
                    cwe_id="CWE-1035",  # Vulnerable Third-Party Component
                    owasp_category="A06:2021",
                    remediation=f"Update {cve.package_name} to version {cve.fixed_version}" if cve.fixed_version else "Update to latest version",
                    metadata={
                        "cve_id": cve.id,
                        "cvss_score": cve.score,
                        "vulnerable_versions": cve.vulnerable_versions,
                        "fixed_version": cve.fixed_version,
                    },
                ))

        except Exception as e:
            self.logger.warning("Dependency scan failed", error=str(e))

        return findings

    async def _check_licenses(self, project_path: Path) -> List[SecurityFinding]:
        """Check license compliance."""
        findings: List[SecurityFinding] = []

        try:
            supply_chain = SupplyChainSecurity(project_path)
            sbom = await supply_chain.generate_sbom()
            result = await supply_chain.check_license_compliance(sbom)

            for violation in result.violations:
                findings.append(SecurityFinding(
                    id=str(uuid.uuid4()),
                    category=FindingCategory.LICENSE_VIOLATION,
                    severity=FindingSeverity.HIGH,
                    title=f"License Violation: {violation['package']}",
                    description=violation["reason"],
                    metadata=violation,
                    remediation="Replace dependency or obtain proper license",
                ))

            for warning in result.warnings:
                findings.append(SecurityFinding(
                    id=str(uuid.uuid4()),
                    category=FindingCategory.LICENSE_VIOLATION,
                    severity=FindingSeverity.MEDIUM,
                    title=f"License Warning: {warning['package']}",
                    description=warning["reason"],
                    metadata=warning,
                    remediation="Review license compatibility",
                ))

        except Exception as e:
            self.logger.warning("License check failed", error=str(e))

        return findings

    async def analyze_behavior(
        self,
        cell_id: str,
        logs: List[str],
        network_connections: Optional[List[Dict[str, Any]]] = None,
        file_accesses: Optional[List[Dict[str, Any]]] = None,
    ) -> ScanResult:
        """
        Analyze cell runtime behavior.

        Args:
            cell_id: Cell identifier
            logs: Container logs
            network_connections: Observed network connections
            file_accesses: Observed file system accesses

        Returns:
            ScanResult with behavior findings
        """
        result = ScanResult(
            scan_id=str(uuid.uuid4()),
            cell_id=cell_id,
            scan_type=ScanType.BEHAVIOR,
            started_at=datetime.now(timezone.utc),
        )

        findings = await self.behavior_analyzer.analyze(
            cell_id,
            logs,
            network_connections or [],
            file_accesses or [],
        )

        result.findings = findings
        result.risk_score = self._calculate_risk_score(findings)
        result.summary = self._summarize_findings(findings)
        result.passed = self._evaluate_pass_fail(findings, result.risk_score)
        result.completed_at = datetime.now(timezone.utc)

        return result

    def _calculate_risk_score(self, findings: List[SecurityFinding]) -> float:
        """Calculate overall risk score from findings."""
        score = 0.0

        for finding in findings:
            weight = self._severity_weights.get(finding.severity, 0)
            score += weight * finding.confidence

        return min(100.0, score)

    def _summarize_findings(self, findings: List[SecurityFinding]) -> Dict[str, int]:
        """Summarize findings by severity."""
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
            "total": len(findings),
        }

        for finding in findings:
            summary[finding.severity.value] += 1

        return summary

    def _evaluate_pass_fail(self, findings: List[SecurityFinding], risk_score: float) -> bool:
        """Evaluate if scan passes based on thresholds."""
        critical_count = len([f for f in findings if f.severity == FindingSeverity.CRITICAL])
        high_count = len([f for f in findings if f.severity == FindingSeverity.HIGH])

        if critical_count > self._max_critical:
            return False
        if high_count > self._max_high:
            return False
        if risk_score > self._max_risk_score:
            return False

        return True

    def _map_cve_severity(self, severity: SeverityLevel) -> FindingSeverity:
        """Map CVE severity to finding severity."""
        mapping = {
            SeverityLevel.CRITICAL: FindingSeverity.CRITICAL,
            SeverityLevel.HIGH: FindingSeverity.HIGH,
            SeverityLevel.MEDIUM: FindingSeverity.MEDIUM,
            SeverityLevel.LOW: FindingSeverity.LOW,
            SeverityLevel.UNKNOWN: FindingSeverity.INFO,
        }
        return mapping.get(severity, FindingSeverity.INFO)

    def set_thresholds(
        self,
        max_critical: int = 0,
        max_high: int = 3,
        max_risk_score: float = 50,
    ) -> None:
        """Configure pass/fail thresholds."""
        self._max_critical = max_critical
        self._max_high = max_high
        self._max_risk_score = max_risk_score

    async def quick_scan(self, project_path: Path) -> Tuple[bool, float, Dict[str, int]]:
        """
        Perform a quick security check.

        Returns:
            Tuple of (passed, risk_score, summary)
        """
        result = await self.scan_cell("quick", project_path, ScanType.SAST)
        return result.passed, result.risk_score, result.summary

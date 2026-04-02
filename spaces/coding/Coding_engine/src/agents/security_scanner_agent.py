"""
Security Scanner Agent - Autonomous agent for security vulnerability detection.

Scans generated code for:
- OWASP Top 10 vulnerabilities (SQL Injection, XSS, CSRF, etc.)
- Hardcoded secrets (API keys, passwords, tokens)
- Dependency vulnerabilities (npm audit, pip-audit)
- Insecure patterns (eval, innerHTML, etc.)

Publishes:
- SECURITY_SCAN_PASSED: No vulnerabilities found
- SECURITY_SCAN_FAILED: Critical vulnerabilities found
- VULNERABILITY_DETECTED: Individual vulnerability reports
- SECRET_LEAKED: API key/password found in code
- SECURITY_FIX_NEEDED: Fix request sent to GeneratorAgent
"""

import asyncio
import os
import re
import json
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    security_scan_started_event,
    security_scan_passed_event,
    security_scan_failed_event,
    vulnerability_detected_event,
    secret_leaked_event,
    security_fix_needed_event,
    dependency_vulnerability_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin


logger = structlog.get_logger(__name__)


# Regex patterns for secret detection
SECRET_PATTERNS = {
    "aws_access_key": r"(?:AKIA|A3T|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
    "aws_secret_key": r"(?i)aws[_-]?secret[_-]?(?:access[_-]?)?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})",
    "github_token": r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}",
    "generic_api_key": r"(?i)(?:api[_-]?key|apikey|api_secret)['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})",
    "generic_secret": r"(?i)(?:secret|password|passwd|pwd)['\"]?\s*[:=]\s*['\"]?([^\s'\"]{8,})",
    "jwt_token": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    "private_key": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    "database_url": r"(?i)(?:postgres|mysql|mongodb|redis)://[^\s]+@[^\s]+",
    "slack_webhook": r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
    "stripe_key": r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{24,}",
    "openai_key": r"sk-[A-Za-z0-9]{48}",
    "anthropic_key": r"sk-ant-[A-Za-z0-9_-]{95}",
}

# Dangerous code patterns (OWASP-related)
DANGEROUS_PATTERNS = {
    "sql_injection": {
        "pattern": r"(?i)(?:execute|query|raw)\s*\(\s*['\"`].*?\$\{|(?:execute|query)\s*\(\s*.*?\+",
        "severity": "critical",
        "description": "Potential SQL injection vulnerability - use parameterized queries",
    },
    "xss_innerhtml": {
        "pattern": r"\.innerHTML\s*=|dangerouslySetInnerHTML",
        "severity": "high",
        "description": "XSS vulnerability - avoid innerHTML with user input, sanitize content",
    },
    "eval_usage": {
        "pattern": r"\beval\s*\(|\bnew\s+Function\s*\(",
        "severity": "critical",
        "description": "Code injection risk - avoid eval() and new Function()",
    },
    "command_injection": {
        "pattern": r"(?:child_process\.exec|subprocess\.(?:call|run|Popen))\s*\([^)]*(?:\+|`|\$\{)",
        "severity": "critical",
        "description": "Command injection vulnerability - use parameterized commands",
    },
    "hardcoded_credentials": {
        "pattern": r"(?i)(?:password|secret|api_key)\s*=\s*['\"][^'\"]{8,}['\"]",
        "severity": "high",
        "description": "Hardcoded credentials - use environment variables",
    },
    "insecure_random": {
        "pattern": r"Math\.random\(\)|random\.random\(\)",
        "severity": "medium",
        "description": "Insecure randomness for security operations - use crypto.randomBytes",
    },
    "cors_wildcard": {
        "pattern": r"(?i)(?:Access-Control-Allow-Origin|cors)['\"]?\s*[:=]\s*['\"]?\*",
        "severity": "medium",
        "description": "CORS wildcard allows any origin - restrict to specific domains",
    },
    "insecure_cookie": {
        "pattern": r"(?i)cookie.*(?:httpOnly|secure)\s*[:=]\s*false",
        "severity": "high",
        "description": "Insecure cookie settings - enable httpOnly and secure flags",
    },
    "prototype_pollution": {
        "pattern": r"\[(?:__proto__|constructor|prototype)\]",
        "severity": "high",
        "description": "Prototype pollution risk - validate object keys",
    },
    "path_traversal": {
        "pattern": r"(?:path\.join|readFile|writeFile)\s*\([^)]*(?:req\.|params\.|query\.)",
        "severity": "high",
        "description": "Path traversal vulnerability - validate and sanitize file paths",
    },
}

# Files to skip
SKIP_PATTERNS = {
    "node_modules", ".git", "dist", "build", "out", "__pycache__",
    ".venv", "venv", ".next", "coverage", ".nyc_output",
}

# Extensions to scan
CODE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java",
    ".rs", ".rb", ".php", ".vue", ".svelte",
}


class SecurityScannerAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent that scans code for security vulnerabilities.

    Subscribes to:
    - BUILD_SUCCEEDED: Scan after successful build
    - CODE_GENERATED: Scan newly generated code
    - GENERATION_COMPLETE: Full scan after initial generation

    Publishes:
    - SECURITY_SCAN_STARTED: Scan began
    - SECURITY_SCAN_PASSED: No critical vulnerabilities
    - SECURITY_SCAN_FAILED: Critical vulnerabilities found
    - VULNERABILITY_DETECTED: Individual vulnerability report
    - SECRET_LEAKED: Hardcoded secret detected
    - SECURITY_FIX_NEEDED: Request fix from GeneratorAgent

    Workflow:
    1. Triggered after build succeeds or code is generated
    2. Runs dependency audit (npm audit / pip-audit)
    3. Scans source files for dangerous patterns
    4. Detects hardcoded secrets
    5. Reports vulnerabilities to event bus
    6. Sends fix requests to GeneratorAgent
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        run_npm_audit: bool = True,
        run_pip_audit: bool = True,
        fail_on_critical: bool = True,
        scan_for_secrets: bool = True,
        scan_patterns: bool = True,
        timeout: int = 300,
    ):
        """
        Initialize the SecurityScannerAgent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project working directory
            run_npm_audit: Run npm audit for Node.js projects
            run_pip_audit: Run pip-audit for Python projects
            fail_on_critical: Mark scan as failed if critical vulnerabilities found
            scan_for_secrets: Scan for hardcoded secrets
            scan_patterns: Scan for dangerous code patterns
            timeout: Timeout for external commands
        """
        super().__init__(name, event_bus, shared_state, working_dir)
        self.run_npm_audit = run_npm_audit
        self.run_pip_audit = run_pip_audit
        self.fail_on_critical = fail_on_critical
        self.scan_for_secrets = scan_for_secrets
        self.scan_patterns = scan_patterns
        self.timeout = timeout
        self._last_scan_time: Optional[float] = None
        self._scan_cooldown = 30.0  # Minimum seconds between scans
        self._vulnerabilities: list[dict] = []
        self._secrets_found: list[dict] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.CODE_GENERATED,
            EventType.GENERATION_COMPLETE,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if we should run security scan.

        Acts when:
        - BUILD_SUCCEEDED event received
        - CODE_GENERATED event received
        - Not in cooldown period
        """
        import time

        # Check cooldown
        if self._last_scan_time:
            elapsed = time.time() - self._last_scan_time
            if elapsed < self._scan_cooldown:
                return False

        # Check for relevant events
        relevant_events = [
            e for e in events
            if e.type in [
                EventType.BUILD_SUCCEEDED,
                EventType.CODE_GENERATED,
                EventType.GENERATION_COMPLETE,
            ]
        ]

        return len(relevant_events) > 0

    async def act(self, events: list[Event]) -> None:
        """
        Execute security scan.

        Uses autogen team (SecurityOperator + SecurityValidator) if available,
        falls back to direct scanning for legacy mode.
        """
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> None:
        """Run security scan using autogen SecurityOperator + SecurityValidator team."""
        import time

        self._last_scan_time = time.time()
        self._vulnerabilities = []
        self._secrets_found = []

        await self.event_bus.publish(security_scan_started_event(
            source=self.name,
            working_dir=self.working_dir,
        ))

        try:
            task = self.build_task_prompt(events, extra_context=f"""
## Security Scan Task

Scan the project at {self.working_dir} for security vulnerabilities:

1. Run `npm audit` to check dependency vulnerabilities
2. Scan source files for OWASP Top 10 patterns (SQL injection, XSS, eval, command injection)
3. Scan for hardcoded secrets (API keys, passwords, JWT tokens, private keys)
4. Check for insecure patterns (CORS wildcard, insecure cookies, prototype pollution)

Report all findings with file path, line number, severity (critical/high/medium/low), and description.
""")

            team = self.create_team(
                operator_name="SecurityOperator",
                operator_prompt="""You are a security scanning expert (OWASP, SAST).

Your role is to scan project code for security vulnerabilities:
- Run npm audit / pip-audit for dependency vulnerabilities
- Search for hardcoded secrets (API keys, passwords, tokens)
- Detect dangerous code patterns (eval, innerHTML, SQL injection, command injection)
- Check for insecure configuration (CORS, cookies, headers)

Report each finding with: file, line, severity, description, and suggested fix.
When done scanning, say TASK_COMPLETE.""",
                validator_name="SecurityValidator",
                validator_prompt="""You are a security review validator.

Review the security scan results and verify:
1. No false positives (e.g., secrets in .env.example are OK)
2. Severity ratings are accurate
3. All OWASP Top 10 categories were checked
4. Suggested fixes are actionable

If the scan is comprehensive, say TASK_COMPLETE.
If areas were missed, describe what needs additional scanning.""",
                tool_categories=["npm", "pip", "filesystem", "search"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                await self.event_bus.publish(security_scan_passed_event(
                    source=self.name,
                    vulnerabilities_total=0,
                    secrets_found=0,
                    critical=0, high=0, medium=0, low=0,
                ))
                self.logger.info("security_scan_passed", mode="autogen")
            else:
                await self.event_bus.publish(security_scan_failed_event(
                    source=self.name,
                    error_message=result["result_text"][:500],
                ))
                self.logger.warning("security_scan_failed", mode="autogen")

        except Exception as e:
            self.logger.error("security_scan_autogen_error", error=str(e))
            await self.event_bus.publish(security_scan_failed_event(
                source=self.name,
                error_message=str(e),
            ))

    async def _act_legacy(self, events: list[Event]) -> None:
        """Execute security scan using direct scanning (legacy)."""
        import time

        self._last_scan_time = time.time()
        self._vulnerabilities = []
        self._secrets_found = []

        # Publish scan started
        await self.event_bus.publish(security_scan_started_event(
            source=self.name,
            working_dir=self.working_dir,
        ))

        self.logger.info("security_scan_started", working_dir=self.working_dir)

        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0

        try:
            # 1. Run dependency audit
            if self.run_npm_audit:
                npm_vulns = await self._run_npm_audit()
                for vuln in npm_vulns:
                    self._vulnerabilities.append(vuln)
                    if vuln["severity"] == "critical":
                        critical_count += 1
                    elif vuln["severity"] == "high":
                        high_count += 1
                    elif vuln["severity"] == "medium":
                        medium_count += 1
                    else:
                        low_count += 1

            if self.run_pip_audit:
                pip_vulns = await self._run_pip_audit()
                for vuln in pip_vulns:
                    self._vulnerabilities.append(vuln)
                    if vuln["severity"] == "critical":
                        critical_count += 1
                    elif vuln["severity"] == "high":
                        high_count += 1

            # 2. Scan for dangerous code patterns
            if self.scan_patterns:
                pattern_vulns = await self._scan_dangerous_patterns()
                for vuln in pattern_vulns:
                    self._vulnerabilities.append(vuln)
                    await self.event_bus.publish(vulnerability_detected_event(
                        source=self.name,
                        file_path=vuln.get("file"),
                        vuln_type=vuln.get("type"),
                        severity=vuln.get("severity", "medium"),
                        description=vuln.get("description"),
                        line=vuln.get("line"),
                        extra_data={"pattern": vuln.get("pattern"), "match": vuln.get("match")},
                    ))
                    if vuln["severity"] == "critical":
                        critical_count += 1
                    elif vuln["severity"] == "high":
                        high_count += 1
                    elif vuln["severity"] == "medium":
                        medium_count += 1

            # 3. Scan for secrets
            if self.scan_for_secrets:
                secrets = await self._scan_secrets()
                for secret in secrets:
                    self._secrets_found.append(secret)
                    await self.event_bus.publish(secret_leaked_event(
                        source=self.name,
                        file_path=secret.get("file"),
                        secret_type=secret.get("secret_type"),
                        line=secret.get("line"),
                        description=secret.get("description"),
                    ))
                    critical_count += 1  # Secrets are always critical

            # 4. Determine scan result
            has_critical = critical_count > 0
            has_failures = has_critical if self.fail_on_critical else False

            if has_failures:
                await self.event_bus.publish(security_scan_failed_event(
                    source=self.name,
                    error_message=f"Found {critical_count} critical, {high_count} high severity issues",
                    vulnerabilities_total=len(self._vulnerabilities),
                    secrets_found=len(self._secrets_found),
                    critical=critical_count,
                    high=high_count,
                    medium=medium_count,
                    low=low_count,
                ))

                for vuln in self._vulnerabilities:
                    if vuln["severity"] in ["critical", "high"]:
                        await self.event_bus.publish(security_fix_needed_event(
                            source=self.name,
                            file_path=vuln.get("file"),
                            vulnerability=vuln,
                            fix_suggestion=vuln.get("description"),
                        ))

                self.logger.warning(
                    "security_scan_failed",
                    critical=critical_count,
                    high=high_count,
                    medium=medium_count,
                    secrets=len(self._secrets_found),
                )
            else:
                await self.event_bus.publish(security_scan_passed_event(
                    source=self.name,
                    vulnerabilities_total=len(self._vulnerabilities),
                    secrets_found=len(self._secrets_found),
                    critical=critical_count,
                    high=high_count,
                    medium=medium_count,
                    low=low_count,
                ))

                self.logger.info(
                    "security_scan_passed",
                    vulnerabilities=len(self._vulnerabilities),
                    medium=medium_count,
                    low=low_count,
                )

        except Exception as e:
            self.logger.error("security_scan_error", error=str(e))
            await self.event_bus.publish(security_scan_failed_event(
                source=self.name,
                error_message=str(e),
            ))

    async def _run_npm_audit(self) -> list[dict]:
        """Run npm audit and parse results."""
        vulnerabilities = []
        package_json = Path(self.working_dir) / "package.json"

        if not package_json.exists():
            return vulnerabilities

        try:
            result = await self.call_tool("npm.audit", cwd=str(self.working_dir))
            audit_data = result if isinstance(result, dict) else {}

            # call_tool may return raw JSON string as {"result": str}
            if "result" in result and isinstance(result["result"], str):
                try:
                    audit_data = json.loads(result["result"])
                except json.JSONDecodeError:
                    audit_data = result

            if "vulnerabilities" in audit_data:
                for pkg_name, vuln_info in audit_data["vulnerabilities"].items():
                    vulnerabilities.append({
                        "type": "dependency",
                        "source": "npm_audit",
                        "package": pkg_name,
                        "severity": vuln_info.get("severity", "unknown"),
                        "description": vuln_info.get("title", "Vulnerability in dependency"),
                        "fix_available": vuln_info.get("fixAvailable", False),
                    })

                    await self.event_bus.publish(dependency_vulnerability_event(
                        source=self.name,
                        package=pkg_name,
                        severity=vuln_info.get("severity"),
                        fix_available=vuln_info.get("fixAvailable", False),
                    ))

        except Exception as e:
            self.logger.warning("npm_audit_error", error=str(e))

        return vulnerabilities

    async def _run_pip_audit(self) -> list[dict]:
        """Run pip-audit and parse results."""
        vulnerabilities = []
        requirements = Path(self.working_dir) / "requirements.txt"
        pyproject = Path(self.working_dir) / "pyproject.toml"

        if not requirements.exists() and not pyproject.exists():
            return vulnerabilities

        try:
            result = await self.call_tool("pip.audit", cwd=str(self.working_dir))
            audit_data = result if isinstance(result, dict) else {}

            # call_tool may return raw JSON string as {"result": str}
            if "result" in result and isinstance(result["result"], str):
                try:
                    audit_data = json.loads(result["result"])
                except json.JSONDecodeError:
                    audit_data = result

            if isinstance(audit_data, list):
                for vuln in audit_data:
                    vulnerabilities.append({
                        "type": "dependency",
                        "source": "pip_audit",
                        "package": vuln.get("name"),
                        "severity": "high",
                        "description": vuln.get("vulns", [{}])[0].get("id", "Vulnerability"),
                        "fix_available": vuln.get("fix_versions") is not None,
                    })

        except Exception as e:
            self.logger.warning("pip_audit_error", error=str(e))

        return vulnerabilities

    async def _scan_dangerous_patterns(self) -> list[dict]:
        """Scan source files for dangerous code patterns."""
        vulnerabilities = []
        working_path = Path(self.working_dir)

        for file_path in working_path.rglob("*"):
            # Skip directories and non-code files
            if file_path.is_dir():
                continue
            if file_path.suffix not in CODE_EXTENSIONS:
                continue
            if any(skip in str(file_path) for skip in SKIP_PATTERNS):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                relative_path = str(file_path.relative_to(working_path))

                for pattern_name, pattern_info in DANGEROUS_PATTERNS.items():
                    matches = re.finditer(pattern_info["pattern"], content)
                    for match in matches:
                        # Get line number
                        line_num = content[:match.start()].count("\n") + 1

                        vulnerabilities.append({
                            "type": "code_pattern",
                            "pattern": pattern_name,
                            "file": relative_path,
                            "line": line_num,
                            "severity": pattern_info["severity"],
                            "description": pattern_info["description"],
                            "match": match.group()[:100],  # Limit match length
                        })

            except Exception as e:
                self.logger.debug("file_scan_error", file=str(file_path), error=str(e))

        return vulnerabilities

    async def _scan_secrets(self) -> list[dict]:
        """Scan source files for hardcoded secrets."""
        secrets = []
        working_path = Path(self.working_dir)

        # Files that may legitimately contain secret-like patterns
        false_positive_files = {
            ".env.example", ".env.template", ".env.sample",
            "test", "spec", "mock", "__test__", "__mock__",
        }

        for file_path in working_path.rglob("*"):
            if file_path.is_dir():
                continue
            if any(skip in str(file_path) for skip in SKIP_PATTERNS):
                continue

            # Skip likely false positive files
            file_name_lower = file_path.name.lower()
            if any(fp in file_name_lower for fp in false_positive_files):
                continue

            # Only scan relevant file types
            if file_path.suffix not in CODE_EXTENSIONS and file_path.suffix not in {".json", ".yaml", ".yml", ".env"}:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                relative_path = str(file_path.relative_to(working_path))

                for secret_type, pattern in SECRET_PATTERNS.items():
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        # Get line number
                        line_num = content[:match.start()].count("\n") + 1

                        secrets.append({
                            "type": "secret",
                            "secret_type": secret_type,
                            "file": relative_path,
                            "line": line_num,
                            "severity": "critical",
                            "description": f"Potential {secret_type.replace('_', ' ')} detected",
                            "match_preview": match.group()[:20] + "...",  # Show only first 20 chars
                        })

            except Exception as e:
                self.logger.debug("secret_scan_error", file=str(file_path), error=str(e))

        return secrets

    def get_scan_summary(self) -> dict:
        """Get summary of last scan results."""
        return {
            "vulnerabilities": len(self._vulnerabilities),
            "secrets": len(self._secrets_found),
            "critical": sum(1 for v in self._vulnerabilities if v.get("severity") == "critical"),
            "high": sum(1 for v in self._vulnerabilities if v.get("severity") == "high"),
            "by_type": {
                "dependency": sum(1 for v in self._vulnerabilities if v.get("type") == "dependency"),
                "code_pattern": sum(1 for v in self._vulnerabilities if v.get("type") == "code_pattern"),
                "secret": len(self._secrets_found),
            },
        }

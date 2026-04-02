"""
LLM Security Middleware - Protection for LLM-based code generation.

Provides comprehensive security for LLM interactions:
- Prompt injection detection and sanitization
- Output validation for generated code
- Dangerous pattern detection (system commands, secrets)
- Audit logging for all LLM interactions

Used by CellAgent and other LLM-consuming components to ensure
secure code generation and mutation.
"""

import asyncio
import json
import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import structlog

logger = structlog.get_logger(__name__)

# Lazy import to avoid circular dependency
_claude_tool = None

def _get_claude_tool():
    """Lazily import ClaudeCodeTool to avoid circular imports."""
    global _claude_tool
    if _claude_tool is None:
        try:
            from src.tools.claude_code_tool import ClaudeCodeTool
            _claude_tool = ClaudeCodeTool()
        except ImportError:
            pass
    return _claude_tool


class SecurityFindingSeverity(str, Enum):
    """Severity levels for security findings."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityFindingType(str, Enum):
    """Types of security findings."""
    PROMPT_INJECTION = "prompt_injection"
    DANGEROUS_IMPORT = "dangerous_import"
    SHELL_COMMAND = "shell_command"
    SECRET_EXPOSURE = "secret_exposure"
    NETWORK_ACCESS = "network_access"
    FILE_SYSTEM_ACCESS = "file_system_access"
    CODE_EXECUTION = "code_execution"
    MALICIOUS_PATTERN = "malicious_pattern"
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"


@dataclass
class SecurityFinding:
    """A security issue found during analysis."""
    type: SecurityFindingType
    severity: SecurityFindingSeverity
    message: str
    line_number: Optional[int] = None
    pattern_matched: Optional[str] = None
    recommendation: Optional[str] = None
    context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "message": self.message,
            "line_number": self.line_number,
            "pattern_matched": self.pattern_matched,
            "recommendation": self.recommendation,
        }


@dataclass
class ValidationResult:
    """Result of code validation."""
    valid: bool
    findings: List[SecurityFinding] = field(default_factory=list)
    sanitized_code: Optional[str] = None
    blocked: bool = False
    block_reason: Optional[str] = None

    @property
    def critical_findings(self) -> List[SecurityFinding]:
        return [f for f in self.findings if f.severity == SecurityFindingSeverity.CRITICAL]

    @property
    def high_findings(self) -> List[SecurityFinding]:
        return [f for f in self.findings if f.severity == SecurityFindingSeverity.HIGH]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "findings_count": len(self.findings),
            "critical_count": len(self.critical_findings),
            "high_count": len(self.high_findings),
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class LLMInteraction:
    """Record of an LLM interaction for audit purposes."""
    id: str
    timestamp: datetime
    cell_id: Optional[str]
    prompt_hash: str  # Hash of prompt for privacy
    prompt_length: int
    output_length: int
    sanitized: bool
    blocked: bool
    findings_count: int
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "cell_id": self.cell_id,
            "prompt_hash": self.prompt_hash,
            "prompt_length": self.prompt_length,
            "output_length": self.output_length,
            "sanitized": self.sanitized,
            "blocked": self.blocked,
            "findings_count": self.findings_count,
            "duration_ms": self.duration_ms,
        }


class LLMSecurityMiddleware:
    """
    Security middleware for LLM-based code generation.

    Provides protection against:
    - Prompt injection attacks
    - Dangerous code patterns
    - Secret/credential exposure
    - Malicious imports and system access

    Usage:
        middleware = LLMSecurityMiddleware()

        # Sanitize prompt before sending to LLM
        safe_prompt = middleware.sanitize_prompt(user_prompt)

        # Validate LLM output
        result = middleware.validate_output(generated_code, cell)

        if result.blocked:
            raise SecurityError(result.block_reason)
    """

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?previous\s+instructions?",
        r"ignore\s+(?:all\s+)?above\s+instructions?",
        r"disregard\s+(?:all\s+)?previous",
        r"forget\s+(?:all\s+)?instructions",
        r"system\s+prompt",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<SYS>>",
        r"<</SYS>>",
        r"###\s*(?:System|Human|Assistant):",
        r"You\s+are\s+now\s+(?:in\s+)?developer\s+mode",
        r"pretend\s+(?:you\s+are|to\s+be)\s+a",
        r"jailbreak",
        r"DAN\s+mode",
    ]

    # Dangerous Python imports
    DANGEROUS_PYTHON_IMPORTS = {
        "os": ["system", "popen", "spawn", "exec"],
        "subprocess": ["*"],
        "pickle": ["*"],
        "marshal": ["*"],
        "shelve": ["*"],
        "pty": ["*"],
        "commands": ["*"],
        "pdb": ["*"],
        "code": ["interact", "compile_command"],
        "codeop": ["*"],
        "__builtins__": ["eval", "exec", "compile", "__import__"],
        "builtins": ["eval", "exec", "compile", "__import__"],
        "importlib": ["*"],
        "ctypes": ["*"],
    }

    # Dangerous JavaScript/TypeScript patterns
    DANGEROUS_JS_PATTERNS = [
        r"child_process",
        r"require\s*\(\s*['\"]child_process['\"]",
        r"require\s*\(\s*['\"]fs['\"]",
        r"eval\s*\(",
        r"Function\s*\(",
        r"new\s+Function\s*\(",
        r"setTimeout\s*\(\s*['\"]",
        r"setInterval\s*\(\s*['\"]",
        r"document\.write",
        r"innerHTML\s*=",
        r"outerHTML\s*=",
        r"__proto__",
        r"constructor\s*\[",
    ]

    # Secret patterns
    SECRET_PATTERNS = [
        (r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"][^'\"]{10,}['\"]", "API Key"),
        (r"(?:secret|password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{6,}['\"]", "Password/Secret"),
        (r"(?:token|auth[_-]?token)\s*[:=]\s*['\"][^'\"]{20,}['\"]", "Token"),
        (r"(?:aws[_-]?access[_-]?key[_-]?id)\s*[:=]\s*['\"]AKIA[A-Z0-9]{16}['\"]", "AWS Access Key"),
        (r"(?:aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9/+=]{40}['\"]", "AWS Secret Key"),
        (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "Private Key"),
        (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
        (r"github[_-]?token\s*[:=]\s*['\"][^'\"]{30,}['\"]", "GitHub Token"),
        (r"sk-[A-Za-z0-9]{48}", "OpenAI API Key"),
        (r"sk-ant-[A-Za-z0-9-]{80,}", "Anthropic API Key"),
    ]

    # Shell command patterns
    SHELL_PATTERNS = [
        r";\s*(?:rm|del|rmdir)\s+-",
        r"&&\s*(?:rm|del|rmdir)\s+-",
        r"\|\s*(?:sh|bash|cmd|powershell)",
        r"`[^`]*(?:rm|del|curl|wget|nc)[^`]*`",
        r"\$\([^)]*(?:rm|del|curl|wget|nc)[^)]*\)",
    ]

    def __init__(
        self,
        block_on_critical: bool = True,
        block_on_high: bool = False,
        enable_audit_logging: bool = True,
        max_prompt_length: int = 100000,
        allowed_imports: Optional[Set[str]] = None,
    ):
        """
        Initialize the security middleware.

        Args:
            block_on_critical: Block code with critical findings
            block_on_high: Block code with high severity findings
            enable_audit_logging: Log all LLM interactions
            max_prompt_length: Maximum allowed prompt length
            allowed_imports: Set of explicitly allowed dangerous imports
        """
        self.block_on_critical = block_on_critical
        self.block_on_high = block_on_high
        self.enable_audit_logging = enable_audit_logging
        self.max_prompt_length = max_prompt_length
        self.allowed_imports = allowed_imports or set()

        # Compile patterns for efficiency
        self._injection_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]
        self._secret_patterns = [
            (re.compile(p, re.IGNORECASE), name) for p, name in self.SECRET_PATTERNS
        ]
        self._shell_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.SHELL_PATTERNS
        ]
        self._js_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_JS_PATTERNS
        ]

        # Audit log
        self._audit_log: List[LLMInteraction] = []

        self.logger = logger.bind(component="llm_security")

    def sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize a prompt before sending to the LLM.

        Removes or neutralizes potential injection attacks.

        Args:
            prompt: Raw prompt from user/system

        Returns:
            Sanitized prompt
        """
        if len(prompt) > self.max_prompt_length:
            self.logger.warning(
                "prompt_truncated",
                original_length=len(prompt),
                max_length=self.max_prompt_length,
            )
            prompt = prompt[:self.max_prompt_length]

        sanitized = prompt

        # Check for injection patterns
        for pattern in self._injection_patterns:
            match = pattern.search(sanitized)
            if match:
                self.logger.warning(
                    "prompt_injection_detected",
                    pattern=pattern.pattern,
                    matched=match.group(0),
                )
                # Replace the injection with a warning comment
                sanitized = pattern.sub("[REDACTED: potential injection]", sanitized)

        return sanitized

    def validate_output(
        self,
        code: str,
        cell_id: Optional[str] = None,
        language: str = "auto",
    ) -> ValidationResult:
        """
        Validate LLM-generated code for security issues.

        Args:
            code: Generated code to validate
            cell_id: ID of the cell (for context)
            language: Programming language (auto-detect if not specified)

        Returns:
            ValidationResult with findings
        """
        findings: List[SecurityFinding] = []

        # Auto-detect language
        if language == "auto":
            language = self._detect_language(code)

        # Check for dangerous imports
        if language in ("python", "py"):
            findings.extend(self._check_python_imports(code))
        elif language in ("javascript", "typescript", "js", "ts"):
            findings.extend(self._check_js_patterns(code))

        # Check for secrets
        findings.extend(self._check_secrets(code))

        # Check for shell commands
        findings.extend(self._check_shell_patterns(code))

        # Determine if code should be blocked
        blocked = False
        block_reason = None

        if self.block_on_critical and any(
            f.severity == SecurityFindingSeverity.CRITICAL for f in findings
        ):
            blocked = True
            critical_finding = next(
                f for f in findings if f.severity == SecurityFindingSeverity.CRITICAL
            )
            block_reason = f"Critical security issue: {critical_finding.message}"

        if self.block_on_high and any(
            f.severity == SecurityFindingSeverity.HIGH for f in findings
        ):
            blocked = True
            high_finding = next(
                f for f in findings if f.severity == SecurityFindingSeverity.HIGH
            )
            block_reason = f"High severity security issue: {high_finding.message}"

        # Log findings
        if findings:
            self.logger.warning(
                "security_findings_detected",
                cell_id=cell_id,
                total_findings=len(findings),
                critical_count=len([f for f in findings if f.severity == SecurityFindingSeverity.CRITICAL]),
                high_count=len([f for f in findings if f.severity == SecurityFindingSeverity.HIGH]),
                blocked=blocked,
            )

        return ValidationResult(
            valid=not blocked,
            findings=findings,
            sanitized_code=code if not blocked else None,
            blocked=blocked,
            block_reason=block_reason,
        )

    def _detect_language(self, code: str) -> str:
        """Detect programming language from code."""
        # Simple heuristics
        if re.search(r"^import\s+|^from\s+\w+\s+import", code, re.MULTILINE):
            return "python"
        if re.search(r"^(?:const|let|var|function|import|export)", code, re.MULTILINE):
            return "javascript"
        if re.search(r"^(?:interface|type|class)\s+\w+", code, re.MULTILINE):
            return "typescript"
        return "unknown"

    def _check_python_imports(self, code: str) -> List[SecurityFinding]:
        """Check for dangerous Python imports."""
        findings = []

        # Find all imports
        import_pattern = re.compile(
            r"(?:^|\n)\s*(?:import\s+(\w+)|from\s+(\w+)\s+import\s+(.+))",
            re.MULTILINE
        )

        for match in import_pattern.finditer(code):
            module = match.group(1) or match.group(2)
            imports = match.group(3) or ""

            if module in self.DANGEROUS_PYTHON_IMPORTS:
                dangerous_funcs = self.DANGEROUS_PYTHON_IMPORTS[module]

                if "*" in dangerous_funcs:
                    # Entire module is dangerous
                    if module not in self.allowed_imports:
                        findings.append(SecurityFinding(
                            type=SecurityFindingType.DANGEROUS_IMPORT,
                            severity=SecurityFindingSeverity.HIGH,
                            message=f"Dangerous module import: {module}",
                            pattern_matched=match.group(0).strip(),
                            recommendation=f"Avoid using {module} in generated code",
                        ))
                else:
                    # Check for specific dangerous functions
                    for func in dangerous_funcs:
                        if func in imports:
                            findings.append(SecurityFinding(
                                type=SecurityFindingType.DANGEROUS_IMPORT,
                                severity=SecurityFindingSeverity.HIGH,
                                message=f"Dangerous function import: {module}.{func}",
                                pattern_matched=match.group(0).strip(),
                                recommendation=f"Avoid using {module}.{func}",
                            ))

        # Check for eval/exec usage
        eval_pattern = re.compile(r"\b(eval|exec|compile)\s*\(", re.MULTILINE)
        for match in eval_pattern.finditer(code):
            findings.append(SecurityFinding(
                type=SecurityFindingType.CODE_EXECUTION,
                severity=SecurityFindingSeverity.CRITICAL,
                message=f"Dynamic code execution detected: {match.group(1)}()",
                pattern_matched=match.group(0),
                recommendation="Remove dynamic code execution",
            ))

        return findings

    def _check_js_patterns(self, code: str) -> List[SecurityFinding]:
        """Check for dangerous JavaScript/TypeScript patterns."""
        findings = []

        for pattern in self._js_patterns:
            for match in pattern.finditer(code):
                # Determine severity based on pattern
                pattern_str = pattern.pattern

                if "eval" in pattern_str or "Function" in pattern_str:
                    severity = SecurityFindingSeverity.CRITICAL
                    finding_type = SecurityFindingType.CODE_EXECUTION
                elif "child_process" in pattern_str:
                    severity = SecurityFindingSeverity.HIGH
                    finding_type = SecurityFindingType.SHELL_COMMAND
                elif "innerHTML" in pattern_str or "outerHTML" in pattern_str:
                    severity = SecurityFindingSeverity.MEDIUM
                    finding_type = SecurityFindingType.MALICIOUS_PATTERN
                else:
                    severity = SecurityFindingSeverity.MEDIUM
                    finding_type = SecurityFindingType.DANGEROUS_IMPORT

                findings.append(SecurityFinding(
                    type=finding_type,
                    severity=severity,
                    message=f"Dangerous pattern detected: {match.group(0)[:50]}",
                    pattern_matched=match.group(0)[:100],
                    recommendation="Review and remove if not necessary",
                ))

        return findings

    def _check_secrets(self, code: str) -> List[SecurityFinding]:
        """Check for exposed secrets."""
        findings = []

        for pattern, secret_type in self._secret_patterns:
            for match in pattern.finditer(code):
                findings.append(SecurityFinding(
                    type=SecurityFindingType.SECRET_EXPOSURE,
                    severity=SecurityFindingSeverity.CRITICAL,
                    message=f"Potential {secret_type} exposed in code",
                    pattern_matched=match.group(0)[:20] + "...[REDACTED]",
                    recommendation=f"Move {secret_type} to environment variables or secret manager",
                ))

        return findings

    def _check_shell_patterns(self, code: str) -> List[SecurityFinding]:
        """Check for dangerous shell command patterns."""
        findings = []

        for pattern in self._shell_patterns:
            for match in pattern.finditer(code):
                findings.append(SecurityFinding(
                    type=SecurityFindingType.SHELL_COMMAND,
                    severity=SecurityFindingSeverity.HIGH,
                    message="Potentially dangerous shell command pattern",
                    pattern_matched=match.group(0)[:50],
                    recommendation="Review shell command for security implications",
                ))

        return findings

    def audit_log(
        self,
        prompt: str,
        output: str,
        cell_id: Optional[str] = None,
        validation_result: Optional[ValidationResult] = None,
        duration_ms: int = 0,
    ) -> LLMInteraction:
        """
        Log an LLM interaction for audit purposes.

        Args:
            prompt: Original prompt (will be hashed)
            output: LLM output
            cell_id: ID of the cell
            validation_result: Validation result if available
            duration_ms: Interaction duration

        Returns:
            LLMInteraction record
        """
        import uuid

        interaction = LLMInteraction(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            cell_id=cell_id,
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:16],
            prompt_length=len(prompt),
            output_length=len(output),
            sanitized=True,  # Assume sanitized if logged
            blocked=validation_result.blocked if validation_result else False,
            findings_count=len(validation_result.findings) if validation_result else 0,
            duration_ms=duration_ms,
        )

        if self.enable_audit_logging:
            self._audit_log.append(interaction)
            self.logger.info(
                "llm_interaction_logged",
                interaction_id=interaction.id,
                cell_id=cell_id,
                blocked=interaction.blocked,
            )

        return interaction

    def get_audit_log(
        self,
        cell_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[LLMInteraction]:
        """
        Get audit log entries.

        Args:
            cell_id: Filter by cell ID
            limit: Maximum entries to return

        Returns:
            List of LLMInteraction records
        """
        log = self._audit_log

        if cell_id:
            log = [entry for entry in log if entry.cell_id == cell_id]

        return log[-limit:]

    def clear_audit_log(self) -> int:
        """Clear the audit log. Returns number of entries cleared."""
        count = len(self._audit_log)
        self._audit_log = []
        return count

    async def analyze_security_context(
        self,
        code: str,
        file_type: str = "auto",
        context: Optional[str] = None,
    ) -> dict:
        """
        Use LLM to analyze code for security vulnerabilities with semantic understanding.

        This provides context-aware vulnerability detection beyond regex patterns,
        understanding code intent to find semantic vulnerabilities.

        Args:
            code: Code to analyze
            file_type: File type (ts, tsx, py, js, etc.) or "auto" for detection
            context: Additional context about the code's purpose

        Returns:
            Dict with vulnerabilities, each containing type, line, severity, fix
        """
        claude_tool = _get_claude_tool()
        if not claude_tool:
            self.logger.warning("llm_security_analysis_unavailable", reason="claude_tool_not_found")
            return self._fallback_security_analysis(code, file_type)

        # Auto-detect file type if needed
        if file_type == "auto":
            file_type = self._detect_language(code)

        # Truncate very long code to avoid token issues
        code_to_analyze = code[:6000] if len(code) > 6000 else code

        prompt = f"""Analyze this code for security vulnerabilities with full context understanding:

FILE TYPE: {file_type}
{f"CONTEXT: {context}" if context else ""}

CODE:
```{file_type}
{code_to_analyze}
```

Check for these vulnerability categories:
1. SQL injection (even with ORMs - check raw queries, query builders)
2. XSS (user input rendered in HTML without proper sanitization)
3. SSRF (user-controlled URLs in fetch/axios/requests)
4. Insecure deserialization (JSON.parse/pickle of untrusted input)
5. Auth bypass (missing role checks, improper token validation)
6. Information disclosure (stack traces, debug info, internal errors)
7. Path traversal (user input in file paths without validation)
8. Command injection (user input in shell commands)
9. Insecure crypto (weak algorithms, hardcoded keys)
10. Race conditions (TOCTOU, unprotected shared state)

For each vulnerability found:
- Identify the exact line number
- Explain WHY it's vulnerable (not just WHAT pattern it matches)
- Provide a specific fix

Return ONLY valid JSON in this exact format:
{{"vulnerabilities": [{{"type": "string", "line": 0, "severity": "critical|high|medium|low", "explanation": "string", "fix": "string"}}], "safe_patterns_used": ["list of security patterns correctly implemented"], "overall_risk": "high|medium|low"}}"""

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    claude_tool.execute,
                    prompt,
                    skill="code-generation",
                ),
                timeout=60.0,
            )

            if result and isinstance(result, str):
                # Extract JSON from response
                json_match = re.search(r'\{[\s\S]*"vulnerabilities"[\s\S]*\}', result)
                if json_match:
                    parsed = json.loads(json_match.group())
                    vuln_count = len(parsed.get("vulnerabilities", []))
                    self.logger.info(
                        "llm_security_analysis_complete",
                        vulnerabilities_found=vuln_count,
                        overall_risk=parsed.get("overall_risk", "unknown"),
                    )
                    return parsed

            self.logger.warning("llm_security_analysis_parse_failed", result_preview=str(result)[:200])
            return self._fallback_security_analysis(code, file_type)

        except asyncio.TimeoutError:
            self.logger.warning("llm_security_analysis_timeout")
            return self._fallback_security_analysis(code, file_type)
        except Exception as e:
            self.logger.warning("llm_security_analysis_error", error=str(e))
            return self._fallback_security_analysis(code, file_type)

    def _fallback_security_analysis(self, code: str, file_type: str) -> dict:
        """
        Rule-based security analysis as fallback when LLM is unavailable.

        Uses the existing regex-based validation and converts to standard format.
        """
        result = {
            "vulnerabilities": [],
            "safe_patterns_used": [],
            "overall_risk": "low",
        }

        # Use existing validation
        validation_result = self.validate_output(code, language=file_type)

        # Convert findings to standard format
        severity_map = {
            SecurityFindingSeverity.CRITICAL: "critical",
            SecurityFindingSeverity.HIGH: "high",
            SecurityFindingSeverity.MEDIUM: "medium",
            SecurityFindingSeverity.LOW: "low",
            SecurityFindingSeverity.INFO: "low",
        }

        for finding in validation_result.findings:
            result["vulnerabilities"].append({
                "type": finding.type.value,
                "line": finding.line_number or 0,
                "severity": severity_map.get(finding.severity, "medium"),
                "explanation": finding.message,
                "fix": finding.recommendation or "Review and fix manually",
            })

        # Determine overall risk
        if any(v["severity"] == "critical" for v in result["vulnerabilities"]):
            result["overall_risk"] = "high"
        elif any(v["severity"] == "high" for v in result["vulnerabilities"]):
            result["overall_risk"] = "high"
        elif any(v["severity"] == "medium" for v in result["vulnerabilities"]):
            result["overall_risk"] = "medium"

        # Detect safe patterns
        safe_patterns = []
        if "helmet" in code.lower():
            safe_patterns.append("helmet security headers")
        if "csurf" in code.lower() or "csrf" in code.lower():
            safe_patterns.append("CSRF protection")
        if "bcrypt" in code.lower() or "argon2" in code.lower():
            safe_patterns.append("secure password hashing")
        if "sanitize" in code.lower() or "escape" in code.lower():
            safe_patterns.append("input sanitization")
        if "rateLimit" in code.lower() or "rate_limit" in code.lower():
            safe_patterns.append("rate limiting")
        if "cors" in code.lower() and "origin" in code.lower():
            safe_patterns.append("CORS configuration")

        result["safe_patterns_used"] = safe_patterns

        self.logger.info(
            "fallback_security_analysis_complete",
            vulnerabilities_found=len(result["vulnerabilities"]),
            overall_risk=result["overall_risk"],
        )
        return result

    async def analyze_security_batch(
        self,
        files: Dict[str, str],
        stop_on_critical: bool = False,
    ) -> dict:
        """
        Analyze multiple files for security vulnerabilities.

        Args:
            files: Dict mapping file paths to code content
            stop_on_critical: Stop analysis early if critical vulnerability found

        Returns:
            Dict with file-level results and summary
        """
        results = {
            "files": {},
            "summary": {
                "total_files": len(files),
                "files_with_issues": 0,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
            },
            "critical_files": [],
        }

        for file_path, code in files.items():
            # Detect file type from extension
            file_type = "auto"
            if file_path.endswith((".ts", ".tsx")):
                file_type = "typescript"
            elif file_path.endswith((".js", ".jsx")):
                file_type = "javascript"
            elif file_path.endswith(".py"):
                file_type = "python"

            analysis = await self.analyze_security_context(code, file_type)
            results["files"][file_path] = analysis

            # Update summary
            vulns = analysis.get("vulnerabilities", [])
            if vulns:
                results["summary"]["files_with_issues"] += 1

            for vuln in vulns:
                severity = vuln.get("severity", "low")
                if severity == "critical":
                    results["summary"]["critical_count"] += 1
                    results["critical_files"].append(file_path)
                    if stop_on_critical:
                        self.logger.warning(
                            "security_batch_stopped_on_critical",
                            file=file_path,
                        )
                        return results
                elif severity == "high":
                    results["summary"]["high_count"] += 1
                elif severity == "medium":
                    results["summary"]["medium_count"] += 1
                else:
                    results["summary"]["low_count"] += 1

        self.logger.info(
            "security_batch_analysis_complete",
            total_files=results["summary"]["total_files"],
            files_with_issues=results["summary"]["files_with_issues"],
            critical_count=results["summary"]["critical_count"],
        )
        return results

    def generate_security_report(self, batch_results: dict) -> str:
        """
        Generate a human-readable security report from batch analysis results.

        Args:
            batch_results: Results from analyze_security_batch()

        Returns:
            Markdown-formatted security report
        """
        summary = batch_results.get("summary", {})
        files = batch_results.get("files", {})

        report_lines = [
            "# Security Analysis Report",
            "",
            "## Summary",
            f"- **Files Analyzed:** {summary.get('total_files', 0)}",
            f"- **Files with Issues:** {summary.get('files_with_issues', 0)}",
            "",
            "### Vulnerability Counts",
            f"- 🔴 Critical: {summary.get('critical_count', 0)}",
            f"- 🟠 High: {summary.get('high_count', 0)}",
            f"- 🟡 Medium: {summary.get('medium_count', 0)}",
            f"- 🟢 Low: {summary.get('low_count', 0)}",
            "",
        ]

        # Critical files section
        critical_files = batch_results.get("critical_files", [])
        if critical_files:
            report_lines.extend([
                "## ⚠️ Critical Files Requiring Immediate Attention",
                "",
            ])
            for f in critical_files:
                report_lines.append(f"- `{f}`")
            report_lines.append("")

        # Detailed findings
        report_lines.extend([
            "## Detailed Findings",
            "",
        ])

        for file_path, analysis in files.items():
            vulns = analysis.get("vulnerabilities", [])
            if not vulns:
                continue

            report_lines.extend([
                f"### `{file_path}`",
                "",
            ])

            # Safe patterns if any
            safe_patterns = analysis.get("safe_patterns_used", [])
            if safe_patterns:
                report_lines.append(f"✅ Safe patterns detected: {', '.join(safe_patterns)}")
                report_lines.append("")

            for i, vuln in enumerate(vulns, 1):
                severity = vuln.get("severity", "unknown")
                severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    severity, "⚪"
                )
                report_lines.extend([
                    f"**{i}. {severity_emoji} {vuln.get('type', 'Unknown')}** (Line {vuln.get('line', '?')})",
                    "",
                    f"> {vuln.get('explanation', 'No explanation provided')}",
                    "",
                    f"**Fix:** {vuln.get('fix', 'No fix provided')}",
                    "",
                ])

        return "\n".join(report_lines)

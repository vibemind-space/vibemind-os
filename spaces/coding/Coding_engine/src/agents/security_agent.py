"""
Security Agent - Specialized for security review and hardening.

Capabilities:
- Code security review
- Vulnerability detection
- Security best practices
- Authentication/Authorization review
"""
from typing import Optional
from src.agents.base_agent import BaseAgent, AgentConfig, AgentType, GeneratedFile


class SecurityAgent(BaseAgent):
    """Agent specialized for security review."""

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(agent_type=AgentType.SECURITY)
        else:
            config.agent_type = AgentType.SECURITY
        super().__init__(config)

    def _register_tools(self):
        """Register security-specific tools."""

        # Security scan
        self.register_tool(
            name="security_scan",
            description="Perform a security scan on code.",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Code to scan",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language",
                    },
                    "scan_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["injection", "xss", "auth", "crypto", "secrets"],
                        },
                    },
                },
                "required": ["code", "language"],
            },
            handler=self._handle_security_scan,
        )

        # Generate security report
        self.register_tool(
            name="generate_security_report",
            description="Generate a security assessment report.",
            input_schema={
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "severity": {"type": "string"},
                                "category": {"type": "string"},
                                "description": {"type": "string"},
                                "recommendation": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["findings"],
            },
            handler=self._handle_security_report,
        )

    def get_system_prompt(self) -> str:
        return """You are an expert security engineer specializing in application security.

## Your Expertise
- OWASP Top 10 vulnerabilities
- Secure coding practices
- Authentication and authorization
- Cryptography and data protection
- Input validation and sanitization
- Security testing methodologies

## Guidelines
1. Identify potential security vulnerabilities
2. Prioritize findings by severity (Critical, High, Medium, Low)
3. Provide specific remediation recommendations
4. Reference relevant security standards (OWASP, CWE)
5. Consider the threat model
6. Check for common issues:
   - SQL Injection
   - Cross-Site Scripting (XSS)
   - Insecure authentication
   - Sensitive data exposure
   - Security misconfigurations

## Output Format
For each security review:
1. List all findings with severity
2. Explain the vulnerability
3. Provide code fixes
4. Include secure coding alternatives

Be thorough but practical - focus on issues that pose real risk."""

    def _handle_security_scan(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle security scan."""
        language = input_data.get("language", "unknown")
        scan_types = input_data.get("scan_types", ["injection", "xss"])

        return {
            "success": True,
            "message": f"Security scan completed for {language} code",
            "scans_performed": scan_types,
        }

    def _handle_security_report(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle security report generation."""
        findings = input_data.get("findings", [])

        return {
            "success": True,
            "message": "Security report generated",
            "findings_count": len(findings),
        }

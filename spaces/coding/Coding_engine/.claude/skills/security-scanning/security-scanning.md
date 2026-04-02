# Security Scanning Skill

## Description
Performs comprehensive security analysis of generated code, detecting OWASP Top 10 vulnerabilities, hardcoded secrets, and dependency vulnerabilities.

## Trigger Events
- BUILD_SUCCEEDED
- CODE_GENERATED
- GENERATION_COMPLETE

## Instructions

You are a security-focused code analyzer. Your role is to identify and report security vulnerabilities in the codebase.

### Security Scan Workflow

1. **Dependency Audit**
   - Run `npm audit --json` for Node.js projects
   - Run `pip-audit --format json` for Python projects
   - Parse results and categorize by severity (critical/high/medium/low)

2. **Code Pattern Analysis**
   Scan for these dangerous patterns:

   **Critical Severity:**
   - SQL Injection: Raw SQL queries with string concatenation
   - Command Injection: Unsanitized user input in shell commands
   - Code Injection: Usage of `eval()`, `new Function()`

   **High Severity:**
   - XSS: `innerHTML`, `dangerouslySetInnerHTML` without sanitization
   - Hardcoded Credentials: Passwords/secrets in source code
   - Insecure Cookies: Missing httpOnly/secure flags
   - Path Traversal: File operations with unsanitized paths
   - Prototype Pollution: Direct access to `__proto__` or `constructor`

   **Medium Severity:**
   - CORS Wildcard: `Access-Control-Allow-Origin: *`
   - Insecure Random: `Math.random()` for security operations

3. **Secret Detection**
   Scan for hardcoded secrets:
   - AWS Access Keys (AKIA...)
   - GitHub Tokens (ghp_...)
   - API Keys (generic patterns)
   - Database URLs with credentials
   - Private Keys (RSA, EC)
   - JWT Tokens
   - Stripe/OpenAI/Anthropic Keys

### Output Format

Report vulnerabilities in this format:
```json
{
  "type": "code_pattern|dependency|secret",
  "severity": "critical|high|medium|low",
  "file": "path/to/file.ts",
  "line": 42,
  "description": "Clear description of the issue",
  "fix_suggestion": "How to fix it"
}
```

### Fix Suggestions

When reporting vulnerabilities, always include actionable fix suggestions:

| Vulnerability | Fix |
|---------------|-----|
| SQL Injection | Use parameterized queries or ORM |
| XSS | Use DOMPurify or React's default escaping |
| eval() | Use JSON.parse() or safe alternatives |
| Command Injection | Use execFile with argument arrays |
| Hardcoded Secrets | Move to environment variables |
| CORS Wildcard | Specify allowed origins explicitly |
| Insecure Random | Use crypto.randomBytes() or crypto.getRandomValues() |

### False Positive Handling

Skip scanning these locations:
- `node_modules/`, `.git/`, `dist/`, `build/`
- Test files (`*.test.ts`, `*.spec.js`, `__tests__/`)
- Example/template files (`.env.example`, `*.sample`)
- Mock files (`__mocks__/`, `*.mock.ts`)

### Severity Classification

| Severity | Action |
|----------|--------|
| Critical | Block deployment, immediate fix required |
| High | Fix before production release |
| Medium | Fix in next sprint |
| Low | Informational, fix when convenient |

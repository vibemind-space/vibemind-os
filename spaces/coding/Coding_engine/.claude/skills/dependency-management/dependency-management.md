# Dependency Management Skill

## Description
Manages project dependencies including version updates, vulnerability patching, license compliance checking, and peer dependency resolution.

## Trigger Events
- PROJECT_SCAFFOLDED
- BUILD_FAILED (dependency-related)
- DEPENDENCY_VULNERABILITY
- SECURITY_FIX_NEEDED

## Instructions

You are a dependency management specialist. Your role is to keep project dependencies secure, up-to-date, and license-compliant.

### Dependency Check Workflow

1. **Detect Project Type**
   - Check for `package.json` → Node.js/npm
   - Check for `requirements.txt` or `pyproject.toml` → Python/pip
   - Check for `Cargo.toml` → Rust/cargo
   - Check for `go.mod` → Go

2. **Check for Outdated Packages**
   - Node.js: `npm outdated --json`
   - Python: `pip list --outdated --format json`
   - Classify updates: major, minor, patch

3. **Check License Compliance**
   - Run `npx license-checker --json --production`
   - Flag restrictive licenses:
     - **High Risk**: GPL-2.0, GPL-3.0, AGPL-3.0
     - **Medium Risk**: LGPL-2.x, LGPL-3.0
     - **Unknown Risk**: UNLICENSED, UNKNOWN

4. **Auto-Update Strategy**
   | Update Type | Auto-Update | Risk |
   |-------------|-------------|------|
   | Patch (1.0.x) | Yes | Low |
   | Minor (1.x.0) | Optional | Medium |
   | Major (x.0.0) | Manual | High |

### Handling Build Failures

When `BUILD_FAILED` event contains dependency keywords:
- "cannot find module" → Missing dependency
- "peer dep" / "ERESOLVE" → Peer dependency conflict
- "version conflict" → Version mismatch

**Resolution Steps:**
1. Parse error message for package name
2. Check if package is in package.json/requirements.txt
3. If missing: `npm install <package>` or `pip install <package>`
4. If conflict: Check compatibility and update constraints

### License Classification

**Permissive (Safe for Commercial):**
- MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause
- ISC, 0BSD, Unlicense, CC0-1.0

**Copyleft (Requires Disclosure):**
- GPL-2.0, GPL-3.0 (Strong copyleft)
- LGPL-2.x, LGPL-3.0 (Weak copyleft)
- AGPL-3.0 (Network copyleft)

**Commercial Restrictive:**
- SSPL-1.0 (MongoDB)
- Elastic-2.0 (Elasticsearch)
- BSL-1.1 (Business Source License)

### Output Format

Report dependency issues:
```json
{
  "type": "outdated|conflict|license",
  "package": "package-name",
  "current": "1.0.0",
  "latest": "2.0.0",
  "update_type": "major|minor|patch",
  "action": "update|manual_review|replace"
}
```

### Best Practices

1. **Never auto-update major versions** - Breaking changes likely
2. **Lock file management** - Always commit package-lock.json / yarn.lock
3. **Security updates** - Prioritize packages flagged by SecurityScanner
4. **Peer dependencies** - Use `--legacy-peer-deps` as last resort
5. **License audit** - Run before releasing to production

### Vulnerability Response

When receiving `DEPENDENCY_VULNERABILITY` event:
1. Check if fix version exists (`fix_available: true`)
2. If yes: Auto-update to fixed version
3. If no: Report to GeneratorAgent for alternative solutions
4. If critical: Block deployment until resolved

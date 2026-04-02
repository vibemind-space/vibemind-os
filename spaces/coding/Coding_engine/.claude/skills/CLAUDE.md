# Skills Directory - CLAUDE.md

This directory contains Claude Code skills for the Society of Mind autonomous code generation system.
Each skill provides specialized instructions for agents to execute specific tasks.

## For Agents - READ THIS FIRST

**Follow this CLAUDE.md to fulfill your job.**

1. Find your skill in the table below based on your agent type
2. Load the skill from `.claude/skills/{skill-name}/SKILL.md`
3. Follow the skill instructions exactly to complete your task
4. Adhere to all Critical Policies (NO MOCKS, Admin Seeding, Permission Checking)

**Your skill contains:**

- Trigger events that activate you
- Step-by-step implementation guidance
- Code templates and examples
- Anti-mock policy requirements

---

## Skills Overview

| Skill | Agent | Purpose | Trigger Events |
|-------|-------|---------|----------------|
| `code-generation` | GeneratorAgent | Generate/fix TypeScript/React code | BUILD_FAILED, CODE_FIX_NEEDED, E2E_TEST_FAILED, UX_ISSUE_FOUND |
| `database-schema-generation` | DatabaseAgent | Generate Prisma/SQLAlchemy schemas | CONTRACTS_GENERATED, SCHEMA_UPDATE_NEEDED |
| `api-generation` | APIAgent | Generate REST APIs from contracts | CONTRACTS_GENERATED, DATABASE_SCHEMA_GENERATED |
| `auth-setup` | AuthAgent | Implement JWT, OAuth2, RBAC | CONTRACTS_GENERATED, AUTH_REQUIRED, ROLE_DEFINITION_NEEDED |
| `environment-config` | InfrastructureAgent | Generate .env, Docker, CI/CD | PROJECT_SCAFFOLDED, DATABASE_SCHEMA_GENERATED, AUTH_SETUP_COMPLETE |
| `test-generation` | ValidationTeamAgent | Generate Vitest/Jest test suites | GENERATION_COMPLETE, BUILD_SUCCEEDED |
| `e2e-testing` | TesterTeamAgent | Execute Playwright E2E tests | DEPLOY_SUCCEEDED, APP_LAUNCHED |
| `ux-review` | UXDesignAgent | Analyze UI with Claude Vision | E2E_SCREENSHOT_TAKEN, APP_LAUNCHED |
| `debugging` | ContinuousDebugAgent | Analyze errors, trace issues | BUILD_FAILED, SANDBOX_TEST_FAILED, RUNTIME_ERROR |
| `validation` | ValidationTeamAgent | Multi-Agent Debate verification | TEST_PASSED, E2E_TEST_PASSED, CONVERGENCE_CHECK |
| `chunk-planning` | ChunkPlannerAgent | Plan parallel code generation | REQUIREMENTS_LOADED, PLANNING_REQUESTED |
| `docker-sandbox` | DeploymentTeamAgent | Manage Docker containers/VNC | BUILD_SUCCEEDED, DEPLOY_REQUESTED |

## How Skills Work

### Loading Skills

Agents load skills using `SkillLoader`:

```python
from src.skills.loader import SkillLoader

# Load from engine's .claude/skills/ directory
loader = SkillLoader(engine_root)
skill = loader.load_skill("auth-setup")

if skill:
    # Skill loaded successfully
    print(f"Loaded: {skill.name}, {skill.instruction_tokens} tokens")
```

### Using Skills with ClaudeCodeTool

Pass the skill to ClaudeCodeTool for progressive disclosure:

```python
from src.tools.claude_code_tool import ClaudeCodeTool

tool = ClaudeCodeTool(
    working_dir="/path/to/project",
    timeout=300,
    skill=skill  # Skill instructions included in prompts
)

result = await tool.execute(
    prompt="Generate auth middleware",
    context="Setting up JWT authentication",
    agent_type="auth"
)
```

### Progressive Disclosure

Skills support progressive disclosure to manage token usage:

1. **Metadata Only** (small): `skill.get_metadata_prompt()` - Name + description
2. **Full Instructions** (larger): `skill.get_full_prompt()` - Complete skill content

### Tier-Based Loading (v2.0)

Skills can define 3 content tiers for optimal token efficiency:

| Tier | Tokens | Content | When Used |
|------|--------|---------|-----------|
| **Minimal** | ~200 | Trigger events + critical rules | Single type error, import fix |
| **Standard** | ~800 | + Workflow + error patterns | Multi-file fix, component creation |
| **Full** | ~1600 | + Code examples | New feature, architecture change |

**Adding Tier Support to Skills:**

1. Add `tier_tokens` to YAML frontmatter:
```yaml
---
name: code-generation
description: Generate/fix TypeScript/React code
tier_tokens:
  minimal: 200
  standard: 800
  full: 1600
---
```

2. Insert tier markers in content:
```markdown
# Skill Title

[Minimal content: trigger events, critical rules]

<!-- END_TIER_MINIMAL -->

[Standard content: workflow, error patterns]

<!-- END_TIER_STANDARD -->

[Full content: code examples, advanced patterns]
```

**Tier API:**

```python
skill = loader.load_skill("code-generation")

# Check tier support
if skill.has_tier_support():
    # Get tier-specific content
    minimal = skill.get_tier_content("minimal")   # ~200 tokens
    standard = skill.get_tier_content("standard") # ~800 tokens
    full = skill.get_tier_content("full")         # ~1600 tokens

    # Get formatted prompt for tier
    prompt = skill.get_tier_prompt("minimal")

    # Check estimated tokens
    estimates = skill.tier_token_estimate
    # {'minimal': 200, 'standard': 800, 'full': 1600}
```

**Automatic Tier Selection:**

`ClaudeCodeTool` uses `ComplexityDetector` to auto-select tiers:

```python
from src.utils.complexity_detector import detect_complexity

result = detect_complexity(
    prompt="Fix the type error",
    error_messages=["Property 'foo' does not exist"],
    error_count=1
)
# result.tier = "minimal", result.confidence = 0.9
```

Or override manually:

```python
tool = ClaudeCodeTool(
    working_dir="./project",
    skill_tier="minimal"  # Force minimal tier
)
```

## Skill File Structure

Each skill is in its own directory with a `SKILL.md` file:

```
.claude/skills/
  auth-setup/
    SKILL.md          # YAML frontmatter + markdown instructions
  code-generation/
    SKILL.md
  database-schema-generation/
    SKILL.md
  ...
```

### SKILL.md Format

```markdown
---
name: skill-name
description: Short description for agent matching
trigger_events: [EVENT_A, EVENT_B]
---

# Skill Title

## Purpose
What this skill does...

## Trigger Events
| Event | Action |
|-------|--------|
| `EVENT_A` | Do X |
| `EVENT_B` | Do Y |

## Implementation Details
...
```

## Agent-Skill Mapping

### Backend Chain (1 -> 4)

1. **DatabaseAgent** -> `database-schema-generation`
   - Generates Prisma/SQLAlchemy schemas from contracts
   - Creates migrations and seed data

2. **APIAgent** -> `api-generation`
   - Generates REST endpoints from schemas
   - Creates Zod validation and API clients

3. **AuthAgent** -> `auth-setup`
   - Implements JWT/OAuth2 authentication
   - Sets up RBAC with roles/permissions
   - Creates admin user seeding

4. **InfrastructureAgent** -> `environment-config`
   - Generates .env files with real secrets
   - Creates Docker Compose configurations
   - Sets up CI/CD pipelines

### Code Generation

- **GeneratorAgent** -> `code-generation`
  - Generates/fixes TypeScript/React code
  - Handles build errors and E2E failures

### Testing & Validation

- **ValidationTeamAgent** -> `test-generation`, `validation`
  - Generates test suites
  - Verifies completeness via Multi-Agent Debate

- **TesterTeamAgent** -> `e2e-testing`
  - Runs Playwright E2E tests
  - Captures screenshots for UX review

### Quality & Review

- **UXDesignAgent** -> `ux-review`
  - Analyzes UI screenshots
  - Provides visual feedback

- **ContinuousDebugAgent** -> `debugging`
  - Analyzes build/runtime errors
  - Syncs fixes to containers

### Infrastructure

- **DeploymentTeamAgent** -> `docker-sandbox`
  - Manages Docker containers
  - Streams VNC for visual monitoring

- **ChunkPlannerAgent** -> `chunk-planning`
  - Plans parallel execution waves
  - Detects dependencies between features

## Critical Policies

All skills enforce these policies:

### NO MOCKS Policy

Skills NEVER generate:
- Hardcoded data arrays as "database"
- TODO/FIXME placeholder comments
- Fake API responses
- Mock authentication (return true)

Skills ALWAYS generate:
- Real database connections (Prisma, SQLAlchemy)
- Real cryptographic operations (bcrypt, JWT)
- Environment variables for secrets
- Production-ready code

### Admin Seeding (auth-setup)

The auth-setup skill MUST generate admin user seeding:
- Create seed script with admin user
- Use bcrypt for password hashing (cost 12)
- Include in prisma/seed.ts or equivalent

### Permission Checking (auth-setup)

The auth-setup skill MUST implement direct permission checks:
```typescript
// Check permission directly, not role-to-permission mapping
const hasPermission = userPermissions.includes(requiredPermission);
```

## Adding New Skills

1. Create directory: `.claude/skills/new-skill/`
2. Create `SKILL.md` with YAML frontmatter
3. Define trigger events for agent matching
4. Update agent to load and use the skill

See existing skills for examples.

# Open-Source Release Checklist — vibemind-os

Step-by-step guide to prepare the repo for a public release. Each step has a verifying command.

---

## Phase 1 — Secrets

### 1.1 Audit `.env` files

```bash
cd vibemind-os
python shared/scripts/sanitize_env.py --root . --report SECRETS_REPORT.md
```

Review `SECRETS_REPORT.md`. You should see ~6 files with ~22 secrets.

### 1.2 Sanitize in-place

**WARNING:** This rewrites the real `.env` files. Back them up first.

```bash
cp .env ~/.vibemind-secrets-backup.env
cp brain/the_brain/.env ~/.vibemind-secrets-backup-brain.env
cp coding-engine/.env ~/.vibemind-secrets-backup-coding.env
cp voice/.env ~/.vibemind-secrets-backup-voice.env
cp openclaw/.env ~/.vibemind-secrets-backup-openclaw.env
cp openfang/.env ~/.vibemind-secrets-backup-openfang.env

python shared/scripts/sanitize_env.py --root . --in-place
```

### 1.3 Verify zero leaked keys remain

```bash
git grep -nE "sk-or-v[0-9]+|sk-proj-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{20,}|sm_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}"
```

Must return **zero lines**. If any match, manually clean and re-run.

### 1.4 Check-mode for CI

```bash
python shared/scripts/sanitize_env.py --root . --check-only
```

Exit code 0 = clean. This is what CI should run on every PR.

---

## Phase 2 — `.gitignore`

Add to `vibemind-os/.gitignore`:

```
# Secrets
.env
.env.local
*.sanitized
~/.vibemind-secrets-backup-*

# LLM config (only .example is tracked)
llm_config.yml
!llm_config.yml.example

# Audit/report artifacts
LLM_AUDIT_REPORT.md
SECRETS_REPORT.md
LLM_AUDIT_BRAIN.md

# Caches
.fungus_cache/
```

Verify nothing sensitive is staged:

```bash
git status --ignored
```

---

## Phase 3 — LLM Config Migration

### 3.1 Inventory direct LLM usage

```bash
python shared/scripts/audit_llm_usage.py --root . --out LLM_AUDIT_REPORT.md
```

Current state: **398 files** with direct LLM clients, **8 files** already migrated.

### 3.2 Migrate one service at a time

Use the `llm-config-migration` skill in Claude Code:

```
/llm-config-migration
```

The skill will read `LLM_AUDIT_REPORT.md`, pick a service, and walk through each file.

**Recommended order** (smallest to biggest):
1. `business/` (1 file)
2. `brain/` (10 files)
3. `coding-engine/` (~30 files)
4. `voice/` (varies)
5. `spaces/` (largest)

### 3.3 Acceptance criteria per service

After migrating a service:
- `audit_llm_usage.py --root <service>` shows that service in "Already migrated"
- `grep -rn "from openai import\|from anthropic import" <service>/` returns only `vibemind_shared/llm_client.py`
- Tests pass (run service-specific test suite)
- The service-local `llm_config.yml` can be deleted (functionality moved to root config)

### 3.4 Goal state

```bash
python shared/scripts/audit_llm_usage.py --root . --out _final.md
# Migration targets: < 50 (acceptable: build artifacts, tests, demo scripts)
# Already migrated: > 350
```

---

## Phase 4 — `vibemind-shared` package release

### 4.1 Verify the package builds

```bash
cd vibemind-os/shared
python -m build
ls dist/
# Should contain vibemind_shared-0.1.0-py3-none-any.whl
```

### 4.2 Test install in a clean venv

```bash
python -m venv /tmp/test_vbs && source /tmp/test_vbs/bin/activate
pip install dist/vibemind_shared-0.1.0-py3-none-any.whl
python -c "from vibemind_shared import get_client; print('OK')"
```

### 4.3 Publish to PyPI (when ready)

```bash
twine upload dist/*
```

Or keep it monorepo-local — every dependent service uses `pip install -e shared/`.

---

## Phase 5 — Documentation

### 5.1 Each top-level service needs a README with

- One-paragraph description
- Setup steps (env vars, llm_config.yml location)
- Run command
- Link to canonical `llm_config.yml.example`

### 5.2 Root README should explain

- Architecture overview (which service does what)
- The `llm_config.yml` system + how to switch providers
- How to install `vibemind-shared`
- Quickstart: 3-command install + run

### 5.3 Create `CONTRIBUTING.md`

- Code style
- How to add a new role (`llm_config.yml.example` first, then code)
- How to add a new provider (touches `vibemind_shared/llm_client.py`)
- Pre-commit hook: `sanitize_env.py --check-only`

---

## Phase 6 — License & Legal

- [ ] Confirm `LICENSE` is MIT (or chosen license) at repo root
- [ ] Each subproject has its own LICENSE if licensed differently
- [ ] Third-party model weights (`la-fungus-search/models/`) — check redistribution rights or remove from repo
- [ ] Add `NOTICE` file if any dependencies require attribution
- [ ] Verify no proprietary code is included (check `_archive/`, `tosort/`)

---

## Phase 7 — Pre-flight

```bash
# 1. Secrets
python shared/scripts/sanitize_env.py --root . --check-only

# 2. LLM config migration progress
python shared/scripts/audit_llm_usage.py --root . --out LLM_AUDIT_REPORT.md
grep "Migration targets" LLM_AUDIT_REPORT.md

# 3. No tracked secrets
git ls-files | xargs -I{} sh -c 'grep -lE "sk-or-v[0-9]|sk-proj-|gsk_" {} 2>/dev/null' | head

# 4. Git status clean
git status

# 5. Build vibemind-shared
cd shared && python -m build && cd ..
```

When all 5 commands return clean: **ready to publish.**

---

## Quick reference — commands

| Command | Purpose |
|---------|---------|
| `python shared/scripts/audit_llm_usage.py --root . --out R.md` | Inventory direct LLM client usage |
| `python shared/scripts/sanitize_env.py --root . --check-only` | CI check for leaked secrets |
| `python shared/scripts/sanitize_env.py --root . --in-place` | Rewrite real `.env` files (DANGER) |
| `git grep -nE "sk-or-v[0-9]|sk-proj-"` | Final grep for raw keys |
| `pip install -e shared/` | Install vibemind-shared editable |

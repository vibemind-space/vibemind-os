# Contributing to vibemind-os

Thanks for your interest. Here's what you need to know before opening a PR.

## Quick start

```bash
git clone https://github.com/Flissel/vibemind-os.git
cd vibemind-os
pip install -e shared/                          # install vibemind_shared
cp llm_config.yml.example llm_config.yml        # create your config
cp .env.example .env                            # add your API keys
python shared/scripts/validate_config.py        # verify config
python shared/scripts/health_check.py           # verify keys work
```

## Project layout

| Path | What it does |
|------|--------------|
| `shared/` | The `vibemind_shared` LLM factory package (pip-installable) |
| `brain/the_brain/` | Tahlamus cognitive system |
| `coding-engine/` | Autonomous code generation pipeline |
| `voice/` | Voice/realtime interaction layer |
| `la-fungus-search/` | Semantic code search (MCMP-RAG) |
| `openfang/` | Rust-based agent runtime |
| `openclaude/` | Claude Code fork with multi-LLM support |
| `openclaw/` | Multi-channel agent gateway (Discord, Telegram, etc.) |
| `security/` | Red/blue team agents |

## The LLM configuration system

**One file controls every LLM call: `llm_config.yml`**

Five providers are supported (and only five):

- `openai` — gpt-4o, gpt-4o-mini, gpt-4o-realtime
- `anthropic` — Claude Sonnet/Opus/Haiku
- `openrouter` — gateway to 100+ models, free tier
- `google` — Gemini 2.0 Flash, Gemini 1.5 Pro
- `ollama` — local LLMs (homelab default)

Code never instantiates clients directly — everything goes through:

```python
from vibemind_shared import get_client, get_model

client = get_client("coding_planner")
response = await client.chat.completions.create(
    model=get_model("coding_planner"),
    messages=[...],
)
```

To switch a component to a different model, edit `llm_config.yml` — never the code.

### Adding a new role

1. Edit `llm_config.yml.example` (the tracked template)
2. Add your role under `roles:` with `provider`, `model`, `temperature`
3. Run `python shared/scripts/validate_config.py` — must pass
4. Use `get_client("your_new_role")` in your code
5. Document the role in your PR description

### Adding a new provider (rare)

The factory only handles `type: openai` and `type: anthropic`. If you need a fundamentally different auth model (Bedrock SigV4, Vertex AI service accounts, etc.):

1. Open an issue first to discuss
2. Add the new branch in `shared/src/vibemind_shared/llm_client.py:get_client`
3. Add tests in `shared/tests/test_factory.py`
4. Update `llm_config.yml.example` with the new provider
5. Update this CONTRIBUTING.md

**We deliberately keep the supported set small to minimize complexity.**

## Pre-commit checklist

Before pushing:

```bash
# 1. No leaked secrets
python shared/scripts/sanitize_env.py --root . --check-only

# 2. Config is valid
python shared/scripts/validate_config.py

# 3. Tests pass
python -m pytest shared/tests/

# 4. No new direct LLM client instantiations
python shared/scripts/audit_llm_usage.py --root . --out _audit.md
# Check that your changes did not increase the count
```

If `sanitize_env.py --check-only` fails, **do not commit.** Run it without `--check-only` to see what would be redacted, then either rotate the leaked keys or use environment variable references instead.

## Using the LLM migration skill

If you're migrating an existing service that uses direct LLM clients, invoke the skill:

```
/llm-config-migration
```

This walks you through file-by-file migration with the recommended pattern. See `.claude/skills/llm-config-migration/SKILL.md` for the full workflow.

## Code style

- **Python**: PEP 8, type hints encouraged but not enforced
- **Comments**: explain *why*, not *what*
- **No emojis** in code or commit messages (only in docs if useful)
- **Commit messages**: imperative mood, present tense ("Add x" not "Added x")

## Testing

- Unit tests live next to the code: `shared/tests/`, `coding-engine/tests/`, etc.
- Use `pytest` with `pytest.fixture` for test setup
- Mock LLM calls — never make real API requests in tests
- Use the `setup_test_config` fixture pattern from `shared/tests/test_factory.py`

## Reporting bugs

Open a GitHub issue with:
- What you expected
- What actually happened
- A minimal reproduction (config + code snippet)
- Your `llm_config.yml` (redact the keys section!)
- Output of `python shared/scripts/validate_config.py`

## License

MIT — see [LICENSE](LICENSE).

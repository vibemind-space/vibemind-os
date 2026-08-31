"""Contract tests for subscription-backed coding routes and agent manifests."""

from __future__ import annotations

import importlib
import re
import sys
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
CAPABILITIES_PATH = ROOT / "brain" / "the_brain" / "data" / "capabilities.yaml"
AGENTS_ROOT = ROOT / "openfang" / "agents"
_BRAIN_ROOT = ROOT / "brain" / "the_brain"
if str(_BRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAIN_ROOT))

CapabilityRouter = importlib.import_module("core.capability_router").CapabilityRouter

OPENAI_AGENT = "brain-coder-openai"
ANTHROPIC_AGENT = "brain-coder-anthropic"


def _capabilities() -> list[dict[str, object]]:
    result = yaml.safe_load(CAPABILITIES_PATH.read_text(encoding="utf-8"))
    assert isinstance(result, list)
    return result


def _capability(name: str) -> dict[str, object]:
    for capability in _capabilities():
        if capability.get("capability") == name:
            return capability
    raise AssertionError(f"capability {name!r} is missing")


def _template(agent_name: str) -> tuple[str, dict[str, object]]:
    path = AGENTS_ROOT / agent_name / "agent.toml.tmpl"
    assert path.is_file(), f"missing agent template: {path}"
    raw = path.read_text(encoding="utf-8")
    return raw, tomllib.loads(raw)


def _matches(capability: dict[str, object], text: str) -> bool:
    patterns = capability.get("match_patterns")
    assert isinstance(patterns, list)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _first_matching_capability(text: str) -> str | None:
    for capability in _capabilities():
        if _matches(capability, text):
            name = capability.get("capability")
            assert isinstance(name, str)
            return name
    return None


def test_coding_routes_are_provider_explicit_without_cross_provider_fallbacks():
    default = _capability("coding_task")
    anthropic = _capability("coding_task_anthropic")

    assert default["execution_target"] == "openfang:brain-coder-openai"
    assert anthropic["execution_target"] == "openfang:brain-coder-anthropic"
    assert anthropic["validator"] == default["validator"]
    assert "openclaude" not in str(default["description"]).lower()

    for route in (default, anthropic):
        assert "fallback" not in route
        assert "fallback_target" not in route
        assert "fallbacks" not in route


def test_anthropic_selectors_are_explicit_and_openai_is_the_deterministic_default():
    for phrase in (
        "use Claude to fix the failing test in tests/test_foo.py",
        "bitte mit Anthropic die Funktion in src/main.py schreiben",
        "Claude Code verwenden und den Fehler in app.py beheben",
    ):
        assert _first_matching_capability(phrase) == "coding_task_anthropic"

    assert _first_matching_capability(
        "fix the failing test in tests/test_foo.py"
    ) == "coding_task"


def test_actual_router_prefers_each_explicit_anthropic_selector_without_cross_route_fallback():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude to fix the failing test in tests/test_foo.py",
        "use Anthropic to fix tests/test_foo.py",
        "bitte mit Anthropic die Funktion in src/main.py schreiben",
        "mit Claude die Funktion in src/main.py schreiben",
        "Claude Code verwenden und den Fehler in app.py beheben",
        "Anthropic verwenden und app.py reparieren",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase
        assert match.match_method == "regex", phrase

    default_match = router.route("fix the failing test in tests/test_foo.py")
    assert default_match is not None
    assert default_match.capability == "coding_task"
    assert default_match.execution_target == "openfang:brain-coder-openai"


def test_actual_router_keeps_explicit_anthropic_operational_requests_off_openai():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude to run tests/test_foo.py",
        "use Anthropic to review src/main.py",
        "mit Claude nach src/main.py suchen",
        "use Claude to delete obsolete.py",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase

    unsupported = router.route("use Claude to summarize src/main.py")
    assert unsupported is None or unsupported.execution_target != "openfang:brain-coder-openai"


def test_actual_router_keeps_all_explicit_anthropic_coding_operations_off_openai():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Anthropic to fix the bug in auth",
        "use Claude to refactor this function",
        "use Anthropic to implement an API",
        "use Claude to create a github repo",
        "use Anthropic to deploy to vercel",
        "use Claude to commit these changes",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase


def test_actual_router_accepts_bounded_anthropic_selector_variants():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "ask Claude to fix the bug in app.py",
        "Claude, fix the bug in app.py",
        "have Anthropic refactor app.py",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase


def test_actual_router_resolves_modified_provider_selectors_before_coding_match():
    router = CapabilityRouter(CAPABILITIES_PATH)
    expected = {
        "use the Claude model to fix app.py": "coding_task_anthropic",
        "ask the Anthropic agent to fix app.py": "coding_task_anthropic",
        "use the OpenAI model to fix app.py": "coding_task",
        "ask the OpenAI agent to fix app.py": "coding_task",
    }

    for phrase, capability in expected.items():
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == capability, phrase


def test_actual_router_resolves_provider_negation_and_conflicts_fail_closed():
    router = CapabilityRouter(CAPABILITIES_PATH)
    expected = {
        "do not use Claude; fix app.py with the default provider": "coding_task",
        "use OpenAI, not Claude, to fix app.py": "coding_task",
        "do not use OpenAI; use Claude to fix app.py": "coding_task_anthropic",
        "use Claude, not OpenAI, to fix app.py": "coding_task_anthropic",
    }

    for phrase, capability in expected.items():
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == capability, phrase

    for phrase in (
        "do not use Claude; fix app.py",
        "do not use OpenAI; fix app.py",
        "use Claude to fix app.py\nuse OpenAI for this task",
        "use Claude and OpenAI to fix app.py",
    ):
        assert router.route(phrase) is None, phrase


def test_actual_router_handles_provider_modifiers_without_cross_provider_fallback():
    router = CapabilityRouter(CAPABILITIES_PATH)
    expected = {
        "use only Claude to fix app.py": "coding_task_anthropic",
        "use only Anthropic to refactor app.py": "coding_task_anthropic",
        "do not ever use Claude; fix app.py": None,
        "do not use Claude or OpenAI; fix app.py": None,
        "do not use Claude\nor OpenAI; fix app.py": None,
        "use both Claude and OpenAI to fix app.py": None,
        "use either Claude or OpenAI to fix app.py": None,
    }

    actual = {}
    for phrase in expected:
        match = router.route(phrase)
        actual[phrase] = match.capability if match is not None else None

    assert actual == expected


def test_actual_router_accepts_postfix_and_multiline_anthropic_selectors():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "fix app.py with Claude",
        "fix app.py using Claude",
        "fix app.py via Claude",
        "fix app.py through Claude",
        "refactor app.py through Anthropic",
        "use Claude.\nFix app.py.",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase


def test_actual_router_blocks_unaccepted_provider_mentions_fail_closed():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "without OpenAI, fix app.py",
        "use neither Claude nor OpenAI to fix app.py",
        "avoid Claude; fix app.py",
        "fix app.py with any provider except Anthropic",
        "do not use Claude nor OpenAI to fix app.py",
        "Claude is unavailable; fix app.py",
    ):
        match = router.route(phrase)
        assert match is None or match.capability not in {
            "coding_task",
            "coding_task_anthropic",
        }, phrase


def test_semantic_routing_applies_the_same_provider_filter(tmp_path: Path):
    registry_path = tmp_path / "semantic_provider_routes.yaml"
    registry_path.write_text(
        yaml.safe_dump(
            [
                {
                    "capability": "semantic_anthropic",
                    "description": "Anthropic semantic target",
                    "coding_provider": "anthropic",
                    "match_patterns": ["(?!)"],
                },
                {
                    "capability": "semantic_openai",
                    "description": "OpenAI semantic target",
                    "coding_provider": "openai",
                    "match_patterns": ["(?!)"],
                },
            ]
        ),
        encoding="utf-8",
    )

    class _Embedder:
        def embed(self, text: str) -> list[float]:
            if text == "Anthropic semantic target":
                return [0.8, 0.6]
            return [1.0, 0.0]

    router = CapabilityRouter(registry_path)
    router.set_embedder(_Embedder())
    router._embedding_thread.join(timeout=2)
    assert not router._embedding_thread.is_alive()

    match = router.route("fix app.py through Claude")
    assert match is not None
    assert match.capability == "semantic_anthropic"
    assert match.match_method == "semantic"

    assert router.route("fix app.py without Claude") is None


def test_actual_router_accepts_extensionless_anthropic_coding_operations():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude to run tests",
        "ask Claude to review source code",
        "Claude, search source code",
        "have Anthropic delete the obsolete file",
        "use Claude to create a git branch",
        "ask Anthropic to merge the git branch",
        "have Claude deploy to Cloudflare",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase


def test_actual_router_accepts_anthropic_file_git_and_deployment_operations():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude to rename src/main.py",
        "ask Anthropic to move the source file",
        "Claude, checkout the feature branch",
        "have Anthropic rebase the git branch",
        "use Claude to clone the repository",
        "ask Anthropic to pull the repository",
        "have Claude deploy to DigitalOcean",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase


def test_explicit_anthropic_business_writing_requests_do_not_route_coding():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude to write a project update",
        "ask Anthropic to create a job application",
        "Claude, edit the service agreement",
        "have Claude write a test email",
    ):
        match = router.route(phrase)
        assert match is None or match.capability not in {
            "coding_task",
            "coding_task_anthropic",
        }, phrase


def test_explicit_anthropic_domain_defects_do_not_route_coding_without_code_context():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude to fix the employment contract issue",
        "ask Anthropic to write an app store description",
        "Claude, fix the car bug",
        "use Claude to write a movie script",
        "ask Anthropic to create a yoga class",
        "Claude, edit the employee job function",
        "have Claude create a training module",
    ):
        match = router.route(phrase)
        assert match is None or match.capability not in {
            "coding_task",
            "coding_task_anthropic",
        }, phrase


def test_explicit_anthropic_non_coding_requests_never_route_to_a_coding_agent():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "ask Claude to summarize this document",
        "Claude, explain quantum mechanics",
        "have Anthropic draft an email",
        "use Claude to translate this paragraph",
        "ask Claude to summarize app.py",
    ):
        match = router.route(phrase)
        assert match is None or match.capability not in {
            "coding_task",
            "coding_task_anthropic",
        }, phrase


def test_explicit_anthropic_selector_preserves_non_coding_collision_routes():
    router = CapabilityRouter(CAPABILITIES_PATH)
    expected = {
        "use Claude to open https://example.com": "browser_automation",
        "use Anthropic for a security scan": "security_scan",
        "use Anthropic to review this pull request": "code_review",
        "use Claude to find the function": "code_search",
    }

    for phrase, capability in expected.items():
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == capability, phrase
        assert match.execution_target != "openfang:brain-coder-openai", phrase


def test_actual_router_requires_provider_selection_and_concrete_coding_mutation_for_anthropic():
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "use Claude",
        "use Anthropic to summarize this document",
        "mit Claude die GitHub-Seite im Browser öffnen",
        "use Anthropic to review this pull request",
        "mit Claude nach einer Funktion im Code suchen",
        "use Anthropic for a security scan",
        "Claude is the name of this code subject",
    ):
        match = router.route(phrase)
        assert match is None or match.capability != "coding_task_anthropic", phrase

    for phrase in (
        "use Claude to fix tests/test_foo.py",
        "use Anthropic to fix tests/test_foo.py",
        "mit Claude die Funktion in src/main.py schreiben",
        "mit Anthropic die Funktion in src/main.py schreiben",
        "Claude Code verwenden und app.py reparieren",
        "Anthropic verwenden und app.py reparieren",
    ):
        match = router.route(phrase)
        assert match is not None, phrase
        assert match.capability == "coding_task_anthropic", phrase
        assert match.execution_target == "openfang:brain-coder-anthropic", phrase

    default_match = router.route("fix tests/test_foo.py")
    assert default_match is not None
    assert default_match.capability == "coding_task"
    assert default_match.execution_target == "openfang:brain-coder-openai"


def test_subscription_agent_templates_preserve_coding_restrictions_and_use_matching_wrappers():
    base_raw, base = _template("brain-coder")
    assert "{{MEMORY}}" in base_raw

    expected = {
        OPENAI_AGENT: {
            "description": "VibeMind coding agent using the ChatGPT subscription through OpenCode.",
            "wrapper": "openfang_opencode_wrapper.cmd",
        },
        ANTHROPIC_AGENT: {
            "description": "VibeMind coding agent using the Claude Pro/Max subscription through official Claude Code.",
            "wrapper": "openfang_claude_subscription_wrapper.cmd",
        },
    }

    for name, contract in expected.items():
        raw, manifest = _template(name)
        model = manifest.get("model")
        assert isinstance(model, dict)

        assert manifest["name"] == name
        assert manifest["description"] == contract["description"]
        assert model["provider"] == "claude-code"
        assert model["base_url"] == contract["wrapper"]
        assert "{{MEMORY}}" in raw
        assert manifest["capabilities"] == base["capabilities"]
        assert manifest["mcp_servers"] == base["mcp_allowed"]["servers"]
        assert manifest["resources"] == base["resources"]
        assert "fallback_models" not in manifest
        assert "api_key_env" not in model
        assert "openrouter" not in raw.lower()
        assert "api.openai.com" not in raw.lower()
        assert "api.anthropic.com" not in raw.lower()


def test_actual_router_blocks_unsupported_third_party_providers_fail_closed():
    """Runbook §7.5: selecting an unsupported provider must never reach a
    coding lane — neither the Anthropic route nor the OpenAI default."""
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "Use Gemini to inspect tests/subscription_fixture_accept.py and report the MARKER value.",
        "use Gemini to fix app.py",
        "fix app.py with Grok",
        "fix the bug in utils.py using Copilot",
        "mit Mistral die Funktion in src/main.py schreiben",
        "refactor the parse_url function in utils.py via DeepSeek",
        "use ollama to fix app.py",
        "fix app.py through OpenRouter",
        "use the Gemini model to fix app.py",
        "Qwen verwenden und den Fehler in app.py beheben",
    ):
        match = router.route(phrase)
        assert match is None or match.capability not in {
            "coding_task",
            "coding_task_anthropic",
        }, phrase


def test_third_party_tool_filenames_do_not_block_the_default_coding_route():
    """Mentioning a provider-named FILE is not a provider selection — the
    deterministic OpenAI default must keep working for such intents."""
    router = CapabilityRouter(CAPABILITIES_PATH)

    for phrase in (
        "fix the failing test in tests/test_ollama_tool.py",
        "refactor the parse_url function in gemini_client.py to handle edge cases",
    ):
        match = router.route(phrase)
        assert match is not None and match.capability == "coding_task", phrase

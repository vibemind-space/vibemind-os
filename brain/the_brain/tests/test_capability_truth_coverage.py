"""Phase 1 — Ground-Truth-Coverage-Ratchet (Reward-Coverage).

Zählt Caps mit truth:-Validator in capabilities.yaml. Der Ratchet darf NUR
steigen — sinkt er, hat jemand Ground-Truth entfernt (Reward-Blindheit).
Ziel-Trajektorie: 22 -> 27 (dieser Task; component_note_write behält seinen
blockierenden rule-Validator, siehe YAML) -> >=53 (~80%, braucht das
openfang:-Default-Contract-Design, eigener Plan).
"""
from pathlib import Path

import yaml

CAPS_PATH = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"
MIN_TRUTH_VALIDATORS = 27
EXPECTED_NEW = {
    "idea_add", "idea_create_batch",
    "bubble_evaluate", "idea_auto_link", "idea_link_to_root",
}


def _truth_coverage():
    caps = yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8"))
    covered = {
        c["capability"] for c in caps
        if isinstance(c.get("validator"), dict)
        and str(c["validator"].get("kind", "")).startswith("truth:")
    }
    return covered, len(caps)


def test_truth_coverage_ratchet():
    covered, total = _truth_coverage()
    assert len(covered) >= MIN_TRUTH_VALIDATORS, (
        f"truth coverage regressed: {len(covered)}/{total} < {MIN_TRUTH_VALIDATORS}"
    )


def test_the_six_new_write_caps_are_covered():
    covered, _ = _truth_coverage()
    missing = EXPECTED_NEW - covered
    assert not missing, f"write caps still without ground truth: {missing}"


def test_yaml_still_parses_and_has_120_caps():
    # 121 caps from the space-wiring union + coding_task_anthropic from the
    # subscription line (coding_task was rewritten in place, not added).
    caps = yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8"))
    assert isinstance(caps, list) and len(caps) == 120

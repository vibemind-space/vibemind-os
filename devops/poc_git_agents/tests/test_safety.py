import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.safety import SafetyGuard, OpType


class TestOpClassification:
    def test_list_is_autonomous(self):
        guard = SafetyGuard()
        assert guard.classify("list") == OpType.AUTONOMOUS

    def test_merge_needs_confirmation(self):
        guard = SafetyGuard()
        assert guard.classify("merge") == OpType.CONFIRM

    def test_delete_needs_delete_check(self):
        guard = SafetyGuard()
        assert guard.classify("delete") == OpType.DELETE


class TestDeleteWhitelist:
    def test_delete_blocked_if_not_whitelisted(self):
        guard = SafetyGuard(delete_whitelist=[])
        allowed, reason = guard.check_delete("Flissel/some-repo")
        assert allowed is False
        assert "not in delete whitelist" in reason

    def test_delete_allowed_if_whitelisted(self):
        guard = SafetyGuard(delete_whitelist=["Flissel/some-repo"])
        allowed, reason = guard.check_delete("Flissel/some-repo")
        assert allowed is True


class TestConfirmation:
    @patch("builtins.input", return_value="y")
    def test_confirm_yes(self, mock_input):
        guard = SafetyGuard()
        assert guard.confirm("Merge PR #5 in Flissel/repo?") is True

    @patch("builtins.input", return_value="n")
    def test_confirm_no(self, mock_input):
        guard = SafetyGuard()
        assert guard.confirm("Merge PR #5 in Flissel/repo?") is False

    @patch("builtins.input", return_value="")
    def test_confirm_default_no(self, mock_input):
        guard = SafetyGuard()
        assert guard.confirm("Merge PR #5?") is False


class TestAutoApprove:
    def test_auto_approve_skips_prompt(self):
        guard = SafetyGuard(auto_approve=True)
        assert guard.confirm("anything") is True


class TestDryRun:
    def test_dry_run_blocks_writes(self):
        guard = SafetyGuard(dry_run=True)
        assert guard.can_execute("merge", "Flissel/repo") is False

    def test_dry_run_allows_reads(self):
        guard = SafetyGuard(dry_run=True)
        assert guard.can_execute("list", "Flissel/repo") is True

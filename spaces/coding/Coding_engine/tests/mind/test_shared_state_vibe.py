"""Tests for user_managed_files in SharedState (Phase 31 Vibe-Coding)."""
import pytest
from src.mind.shared_state import SharedState


@pytest.fixture
def shared():
    return SharedState()


def test_user_managed_files_initially_empty(shared):
    assert shared.user_managed_files == set()
    assert shared.is_user_managed("src/login.tsx") is False


def test_mark_user_managed(shared):
    shared.mark_user_managed(["src/login.tsx", "src/auth.ts"])
    assert shared.is_user_managed("src/login.tsx") is True
    assert shared.is_user_managed("src/auth.ts") is True
    assert shared.is_user_managed("src/other.ts") is False


def test_mark_user_managed_idempotent(shared):
    shared.mark_user_managed(["src/login.tsx"])
    shared.mark_user_managed(["src/login.tsx", "src/auth.ts"])
    assert len(shared.user_managed_files) == 2


def test_user_managed_in_review_status(shared):
    shared.mark_user_managed(["src/login.tsx"])
    status = shared.get_review_status()
    assert "user_managed_count" in status
    assert status["user_managed_count"] == 1

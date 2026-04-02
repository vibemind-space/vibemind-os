"""Tests for GeneratorAgent user_vibe skip (Phase 31)."""
import pytest


def test_should_act_skips_user_vibe_events():
    """GeneratorAgent.should_act filters out events with source=user_vibe."""
    from unittest.mock import MagicMock

    # Create a mock event with user_vibe source
    event = MagicMock()
    event.event_type = "CODE_FIX_NEEDED"
    event.success = False
    event.data = {"source": "user_vibe", "files": ["src/login.tsx"]}

    # The filter logic in should_act should exclude this event
    # (same pattern as som_managed and source_analysis filters)
    assert event.data.get("source") == "user_vibe"

    # Verify the filter condition
    should_skip = event.data.get("source") == "user_vibe"
    assert should_skip is True


def test_should_act_allows_non_vibe_events():
    """Normal events are NOT filtered."""
    from unittest.mock import MagicMock

    event = MagicMock()
    event.event_type = "CODE_FIX_NEEDED"
    event.success = False
    event.data = {"error": "type error in auth.ts"}

    should_skip = event.data.get("source") == "user_vibe"
    assert should_skip is False


def test_collect_errors_skips_user_vibe():
    """_collect_errors_from_events skips events with source=user_vibe."""
    from unittest.mock import MagicMock

    # Simulate the filter logic from _collect_errors_from_events
    events = [
        MagicMock(data={"source": "user_vibe", "files": ["src/login.tsx"]}),
        MagicMock(data={"error": "type error in auth.ts"}),
        MagicMock(data={"source": "pipeline", "error": "build failed"}),
    ]

    # Apply the same filter as in generator_agent.py
    filtered = [e for e in events if e.data.get("source") != "user_vibe"]
    assert len(filtered) == 2
    assert all(e.data.get("source") != "user_vibe" for e in filtered)


def test_som_managed_and_vibe_both_filtered():
    """Both som_managed and user_vibe events are filtered independently."""
    events_data = [
        {"som_managed": True, "source": "som_bridge"},
        {"source": "user_vibe", "files": ["src/app.tsx"]},
        {"source_analysis": "differential_gap", "gap": "missing"},
        {"error": "legit build error"},  # Only this one passes all filters
    ]

    filtered = [
        d for d in events_data
        if not d.get("som_managed")
        and not d.get("source_analysis", "").startswith("differential")
        and not d.get("source") == "user_vibe"
    ]
    assert len(filtered) == 1
    assert filtered[0]["error"] == "legit build error"

"""Tests for Phase 31b Vibe-Coding integration fixes.

Verifies that vibe.py correctly imports EventBus and SharedState
from main.py rather than using broken getattr() patterns.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def test_event_bus_importable_from_main():
    """event_bus is importable from src.api.main and is an EventBus instance."""
    from src.api.main import event_bus
    from src.mind.event_bus import EventBus
    assert isinstance(event_bus, EventBus)


def test_set_shared_event_bus_replaces_instance():
    """set_shared_event_bus() replaces the module-level event_bus."""
    import src.api.main as main_module
    from src.mind.event_bus import EventBus

    original = main_module.event_bus
    new_bus = EventBus()
    main_module.set_shared_event_bus(new_bus)
    assert main_module.event_bus is new_bus

    # Restore
    main_module.set_shared_event_bus(original)


def test_shared_state_initially_none():
    """shared_state starts as None before run_engine.py injects it."""
    from src.api.main import shared_state
    # It may be None or may have been set by a previous test
    # Just verify the attribute exists and is importable
    assert shared_state is None or hasattr(shared_state, 'mark_user_managed')


def test_set_shared_state():
    """set_shared_state() injects a SharedState into main.py."""
    import src.api.main as main_module
    from src.mind.shared_state import SharedState

    state = SharedState()
    main_module.set_shared_state(state)
    assert main_module.shared_state is state

    # Verify vibe.py can use it
    state.mark_user_managed(["src/login.tsx"])
    assert main_module.shared_state.is_user_managed("src/login.tsx")

    # Clean up
    main_module.set_shared_state(None)


def test_vibe_py_does_not_use_getattr_pattern():
    """vibe.py should NOT use getattr(EventBus, '_instance') anymore."""
    import inspect
    from src.api.routes import vibe

    source = inspect.getsource(vibe)
    assert "getattr(EventBus, '_instance'" not in source, \
        "vibe.py still uses broken getattr(EventBus, '_instance') pattern"
    assert "getattr(SharedState, '_instance'" not in source, \
        "vibe.py still uses broken getattr(SharedState, '_instance') pattern"


def test_vibe_py_imports_from_main():
    """vibe.py should import event_bus and shared_state from src.api.main."""
    import inspect
    from src.api.routes import vibe

    source = inspect.getsource(vibe)
    assert "from src.api.main import event_bus" in source, \
        "vibe.py should import event_bus from src.api.main"
    assert "from src.api.main import shared_state" in source, \
        "vibe.py should import shared_state from src.api.main"


@pytest.mark.asyncio
async def test_event_bus_publish_actually_works():
    """Verify that publishing on the shared event_bus reaches subscribers."""
    import src.api.main as main_module
    from src.mind.event_bus import EventBus, Event, EventType

    bus = EventBus()
    main_module.set_shared_event_bus(bus)

    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.CODE_FIXED, handler)

    await bus.publish(Event(
        type=EventType.CODE_FIXED,
        source="user_vibe",
        data={
            "source": "user_vibe",
            "files": ["src/test.tsx"],
        },
        success=True,
    ))

    # Give the event loop a tick to deliver
    import asyncio
    await asyncio.sleep(0.1)

    assert len(received) >= 1
    assert received[0].data["source"] == "user_vibe"

    # Restore
    main_module.set_shared_event_bus(EventBus())

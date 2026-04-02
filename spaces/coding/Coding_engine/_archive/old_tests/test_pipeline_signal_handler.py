"""Test pipeline signal handler."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_signal_handler import PipelineSignalHandler


def test_register_handler():
    """Register and retrieve handler."""
    sh = PipelineSignalHandler()
    hid = sh.register_handler("deploy", "worker", tags=["prod"])
    assert hid.startswith("hdl-")

    h = sh.get_handler(hid)
    assert h is not None
    assert h["signal_name"] == "deploy"
    assert h["component"] == "worker"
    assert h["active"] is True

    assert sh.remove_handler(hid) is True
    assert sh.remove_handler(hid) is False
    print("OK: register handler")


def test_invalid_handler():
    """Invalid handler rejected."""
    sh = PipelineSignalHandler()
    assert sh.register_handler("", "comp") == ""
    assert sh.register_handler("sig", "") == ""
    print("OK: invalid handler")


def test_duplicate():
    """Duplicate signal+component rejected."""
    sh = PipelineSignalHandler()
    sh.register_handler("deploy", "worker")
    assert sh.register_handler("deploy", "worker") == ""
    print("OK: duplicate")


def test_max_handlers():
    """Max handlers enforced."""
    sh = PipelineSignalHandler(max_handlers=2)
    sh.register_handler("a", "c1")
    sh.register_handler("b", "c2")
    assert sh.register_handler("c", "c3") == ""
    print("OK: max handlers")


def test_emit_signal():
    """Emit signal invokes handlers."""
    sh = PipelineSignalHandler()
    received = []
    sh.register_handler("deploy", "worker",
                         handler_fn=lambda name, payload: received.append(payload))

    count = sh.emit("deploy", source="ci", payload={"version": "1.0"})
    assert count == 1
    assert len(received) == 1
    assert received[0]["version"] == "1.0"
    print("OK: emit signal")


def test_emit_no_handlers():
    """Emit with no handlers returns 0."""
    sh = PipelineSignalHandler()
    count = sh.emit("unknown")
    assert count == 0
    print("OK: emit no handlers")


def test_one_shot():
    """One-shot handler auto-deregisters."""
    sh = PipelineSignalHandler()
    received = []
    sh.register_handler("deploy", "worker", one_shot=True,
                         handler_fn=lambda n, p: received.append(1))

    sh.emit("deploy")
    assert len(received) == 1

    # handler should be gone
    sh.emit("deploy")
    assert len(received) == 1  # not called again
    print("OK: one shot")


def test_disable_enable():
    """Disable and enable handler."""
    sh = PipelineSignalHandler()
    hid = sh.register_handler("deploy", "worker",
                               handler_fn=lambda n, p: None)

    assert sh.disable_handler(hid) is True
    assert sh.get_handler(hid)["active"] is False
    assert sh.disable_handler(hid) is False

    count = sh.emit("deploy")
    assert count == 0  # disabled

    assert sh.enable_handler(hid) is True
    assert sh.get_handler(hid)["active"] is True

    count = sh.emit("deploy")
    assert count == 1
    print("OK: disable enable")


def test_multiple_handlers():
    """Multiple handlers for same signal."""
    sh = PipelineSignalHandler()
    r = []
    sh.register_handler("deploy", "worker1",
                         handler_fn=lambda n, p: r.append("w1"))
    sh.register_handler("deploy", "worker2",
                         handler_fn=lambda n, p: r.append("w2"))

    count = sh.emit("deploy")
    assert count == 2
    assert "w1" in r and "w2" in r
    print("OK: multiple handlers")


def test_signal_history():
    """Signal history is recorded."""
    sh = PipelineSignalHandler()
    sh.emit("deploy", source="ci", payload={"v": 1})
    sh.emit("build", source="ci")
    sh.emit("deploy", source="cd")

    history = sh.get_signal_history()
    assert len(history) == 3

    deploy_only = sh.get_signal_history(signal_name="deploy")
    assert len(deploy_only) == 2

    by_source = sh.get_signal_history(source="ci")
    assert len(by_source) == 2
    print("OK: signal history")


def test_list_handlers():
    """List handlers with filters."""
    sh = PipelineSignalHandler()
    sh.register_handler("deploy", "worker", tags=["prod"])
    hid2 = sh.register_handler("build", "builder")
    sh.disable_handler(hid2)

    all_h = sh.list_handlers()
    assert len(all_h) == 2

    by_signal = sh.list_handlers(signal_name="deploy")
    assert len(by_signal) == 1

    by_component = sh.list_handlers(component="builder")
    assert len(by_component) == 1

    by_active = sh.list_handlers(active=True)
    assert len(by_active) == 1

    by_tag = sh.list_handlers(tag="prod")
    assert len(by_tag) == 1
    print("OK: list handlers")


def test_callback():
    """Callback fires on events."""
    sh = PipelineSignalHandler()
    fired = []
    sh.on_change("mon", lambda a, d: fired.append(a))

    sh.register_handler("deploy", "worker")
    assert "handler_registered" in fired

    sh.emit("deploy")
    assert "signal_emitted" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    sh = PipelineSignalHandler()
    assert sh.on_change("mon", lambda a, d: None) is True
    assert sh.on_change("mon", lambda a, d: None) is False
    assert sh.remove_callback("mon") is True
    assert sh.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sh = PipelineSignalHandler()
    sh.register_handler("deploy", "worker")
    sh.emit("deploy")
    sh.emit("build")

    stats = sh.get_stats()
    assert stats["total_handlers"] == 1
    assert stats["total_signals"] == 2
    assert stats["total_deliveries"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sh = PipelineSignalHandler()
    sh.register_handler("deploy", "worker")
    sh.emit("deploy")

    sh.reset()
    assert sh.list_handlers() == []
    assert sh.get_signal_history() == []
    stats = sh.get_stats()
    assert stats["current_handlers"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Signal Handler Tests ===\n")
    test_register_handler()
    test_invalid_handler()
    test_duplicate()
    test_max_handlers()
    test_emit_signal()
    test_emit_no_handlers()
    test_one_shot()
    test_disable_enable()
    test_multiple_handlers()
    test_signal_history()
    test_list_handlers()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    main()

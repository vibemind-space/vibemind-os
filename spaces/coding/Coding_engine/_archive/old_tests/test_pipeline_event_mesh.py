"""Test pipeline event mesh -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_mesh import PipelineEventMesh


def test_create_topic():
    em = PipelineEventMesh()
    tid = em.create_topic("pipeline.build", tags=["ci"])
    assert tid.startswith("top-")
    t = em.get_topic("pipeline.build")
    assert t["name"] == "pipeline.build"
    assert t["subscriber_count"] == 0
    assert em.create_topic("pipeline.build") == ""  # dup
    print("OK: create topic")


def test_subscribe():
    em = PipelineEventMesh()
    em.create_topic("builds")
    sid = em.subscribe("builds", "agent-1")
    assert sid.startswith("sub-")
    t = em.get_topic("builds")
    assert t["subscriber_count"] == 1
    print("OK: subscribe")


def test_unsubscribe():
    em = PipelineEventMesh()
    em.create_topic("builds")
    sid = em.subscribe("builds", "agent-1")
    assert em.unsubscribe(sid) is True
    assert em.unsubscribe(sid) is False
    assert em.get_topic("builds")["subscriber_count"] == 0
    print("OK: unsubscribe")


def test_publish():
    em = PipelineEventMesh()
    em.create_topic("builds")
    received = []
    em.subscribe("builds", "agent-1", handler=lambda data: received.append(data))
    eid = em.publish("builds", {"status": "success"}, publisher="ci")
    assert eid.startswith("evt-")
    assert len(received) == 1
    assert received[0]["status"] == "success"
    print("OK: publish")


def test_publish_with_filter():
    em = PipelineEventMesh()
    em.create_topic("events")
    received = []
    em.subscribe("events", "a1", handler=lambda d: received.append(d),
                 filter_fn=lambda d: d.get("severity") == "high")
    em.publish("events", {"severity": "low", "msg": "skip"})
    em.publish("events", {"severity": "high", "msg": "catch"})
    assert len(received) == 1
    assert received[0]["msg"] == "catch"
    print("OK: publish with filter")


def test_publish_pattern():
    em = PipelineEventMesh()
    em.create_topic("pipeline.build")
    em.create_topic("pipeline.test")
    em.create_topic("alerts.critical")
    received = []
    em.subscribe("pipeline.build", "a1", handler=lambda d: received.append(("build", d)))
    em.subscribe("pipeline.test", "a1", handler=lambda d: received.append(("test", d)))
    em.subscribe("alerts.critical", "a1", handler=lambda d: received.append(("alert", d)))
    count = em.publish_pattern("pipeline.*", {"event": "deploy"})
    assert count == 2
    assert len(received) == 2
    print("OK: publish pattern")


def test_dead_letters():
    em = PipelineEventMesh()
    em.create_topic("builds")
    def bad_handler(data):
        raise RuntimeError("handler crashed")
    em.subscribe("builds", "crashy", handler=bad_handler)
    em.publish("builds", {"status": "ok"})
    dl = em.get_dead_letters()
    assert len(dl) >= 1
    assert "handler crashed" in dl[0].get("error", "")
    print("OK: dead letters")


def test_list_topics():
    em = PipelineEventMesh()
    em.create_topic("a", tags=["ci"])
    em.create_topic("b")
    assert len(em.list_topics()) == 2
    assert len(em.list_topics(tag="ci")) == 1
    print("OK: list topics")


def test_list_subscriptions():
    em = PipelineEventMesh()
    em.create_topic("builds")
    em.subscribe("builds", "a1")
    em.subscribe("builds", "a2")
    subs = em.list_subscriptions(topic_name="builds")
    assert len(subs) == 2
    print("OK: list subscriptions")


def test_remove_topic():
    em = PipelineEventMesh()
    em.create_topic("builds")
    assert em.remove_topic("builds") is True
    assert em.remove_topic("builds") is False
    print("OK: remove topic")


def test_history():
    em = PipelineEventMesh()
    em.create_topic("builds")
    em.publish("builds", {"x": 1})
    hist = em.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    em = PipelineEventMesh()
    fired = []
    em.on_change("mon", lambda a, d: fired.append(a))
    em.create_topic("builds")
    assert len(fired) >= 1
    assert em.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    em = PipelineEventMesh()
    em.create_topic("builds")
    em.publish("builds", {})
    stats = em.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    em = PipelineEventMesh()
    em.create_topic("builds")
    em.reset()
    assert em.list_topics() == []
    print("OK: reset")


def main():
    print("=== Pipeline Event Mesh Tests ===\n")
    test_create_topic()
    test_subscribe()
    test_unsubscribe()
    test_publish()
    test_publish_with_filter()
    test_publish_pattern()
    test_dead_letters()
    test_list_topics()
    test_list_subscriptions()
    test_remove_topic()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()

"""Tests for PipelineStepRateLimiter."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_rate_limiter import PipelineStepRateLimiter


def test_register_limiter():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_a", 10.0, 20)
    assert lid.startswith("psrl-")
    assert len(lid) == 5 + 16


def test_register_creates_entry():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_b", 5.0, 10)
    info = rl.get_limiter(lid)
    assert info["step_name"] == "step_b"
    assert info["max_per_second"] == 5.0
    assert info["burst"] == 10
    assert info["tokens"] == 10.0
    assert info["total_allowed"] == 0
    assert info["total_denied"] == 0


def test_allow_first_call():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_c", 10.0, 5)
    assert rl.allow(lid) is True


def test_allow_depletes_tokens():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_d", 0.1, 3)
    assert rl.allow(lid) is True
    assert rl.allow(lid) is True
    assert rl.allow(lid) is True
    assert rl.allow(lid) is False


def test_allow_refills_tokens():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_e", 100.0, 1)
    assert rl.allow(lid) is True
    assert rl.allow(lid) is False
    time.sleep(0.05)
    assert rl.allow(lid) is True


def test_allow_invalid_id():
    rl = PipelineStepRateLimiter()
    assert rl.allow("psrl-nonexistent12345") is False


def test_allow_tracks_allowed():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_f", 10.0, 5)
    rl.allow(lid)
    rl.allow(lid)
    info = rl.get_limiter(lid)
    assert info["total_allowed"] == 2


def test_allow_tracks_denied():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("step_g", 0.1, 1)
    rl.allow(lid)
    rl.allow(lid)
    info = rl.get_limiter(lid)
    assert info["total_allowed"] == 1
    assert info["total_denied"] == 1


def test_get_limiter_not_found():
    rl = PipelineStepRateLimiter()
    assert rl.get_limiter("psrl-nope") == {}


def test_get_limiters_all():
    rl = PipelineStepRateLimiter()
    rl.register_limiter("s1")
    rl.register_limiter("s2")
    rl.register_limiter("s3")
    assert len(rl.get_limiters()) == 3


def test_get_limiters_filtered():
    rl = PipelineStepRateLimiter()
    rl.register_limiter("alpha")
    rl.register_limiter("beta")
    rl.register_limiter("alpha")
    results = rl.get_limiters(step_name="alpha")
    assert len(results) == 2
    assert all(r["step_name"] == "alpha" for r in results)


def test_get_limiter_count():
    rl = PipelineStepRateLimiter()
    assert rl.get_limiter_count() == 0
    rl.register_limiter("x")
    rl.register_limiter("y")
    assert rl.get_limiter_count() == 2


def test_remove_limiter():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("rem")
    assert rl.remove_limiter(lid) is True
    assert rl.get_limiter_count() == 0
    assert rl.remove_limiter(lid) is False


def test_reset_limiter():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("rst", 0.1, 3)
    rl.allow(lid)
    rl.allow(lid)
    info = rl.get_limiter(lid)
    assert info["tokens"] < 3.0
    assert rl.reset_limiter(lid) is True
    info = rl.get_limiter(lid)
    assert info["tokens"] == 3.0


def test_reset_limiter_invalid_id():
    rl = PipelineStepRateLimiter()
    assert rl.reset_limiter("psrl-nonexistent12345") is False


def test_get_stats():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("stat_step", 0.1, 2)
    rl.allow(lid)
    rl.allow(lid)
    rl.allow(lid)
    stats = rl.get_stats()
    assert stats["total_limiters"] == 1
    assert stats["total_allowed"] == 2
    assert stats["total_denied"] == 1
    assert stats["denial_rate"] == 1.0 / 3.0


def test_get_stats_empty():
    rl = PipelineStepRateLimiter()
    stats = rl.get_stats()
    assert stats["denial_rate"] == 0


def test_reset():
    rl = PipelineStepRateLimiter()
    rl.register_limiter("r1")
    rl.register_limiter("r2")
    rl.reset()
    assert rl.get_limiter_count() == 0
    assert rl.get_stats()["total_allowed"] == 0


def test_on_change_property():
    rl = PipelineStepRateLimiter()
    events = []
    rl.on_change = lambda e, data: events.append(e)
    rl.register_limiter("oc_step")
    assert len(events) == 1
    assert events[0] == "limiter_registered"


def test_callbacks_and_remove():
    rl = PipelineStepRateLimiter()
    events = []
    rl._callbacks["my_cb"] = lambda e, data: events.append(e)
    rl.register_limiter("cb_step")
    assert len(events) == 1
    assert rl.remove_callback("my_cb") is True
    assert rl.remove_callback("my_cb") is False
    rl.register_limiter("cb_step2")
    assert len(events) == 1


def test_unique_ids():
    rl = PipelineStepRateLimiter()
    ids = set()
    for i in range(50):
        ids.add(rl.register_limiter(f"step_{i}"))
    assert len(ids) == 50


def test_callback_exception_handled():
    rl = PipelineStepRateLimiter()

    def bad_cb(event, data):
        raise ValueError("boom")

    rl._callbacks["bad"] = bad_cb
    lid = rl.register_limiter("safe_step")
    assert lid.startswith("psrl-")


def test_tokens_capped_at_burst():
    rl = PipelineStepRateLimiter()
    lid = rl.register_limiter("cap", 1000.0, 5)
    time.sleep(0.05)
    rl.allow(lid)
    info = rl.get_limiter(lid)
    assert info["tokens"] <= 5.0


if __name__ == "__main__":
    tests = [
        test_register_limiter,
        test_register_creates_entry,
        test_allow_first_call,
        test_allow_depletes_tokens,
        test_allow_refills_tokens,
        test_allow_invalid_id,
        test_allow_tracks_allowed,
        test_allow_tracks_denied,
        test_get_limiter_not_found,
        test_get_limiters_all,
        test_get_limiters_filtered,
        test_get_limiter_count,
        test_remove_limiter,
        test_reset_limiter,
        test_reset_limiter_invalid_id,
        test_get_stats,
        test_get_stats_empty,
        test_reset,
        test_on_change_property,
        test_callbacks_and_remove,
        test_unique_ids,
        test_callback_exception_handled,
        test_tokens_capped_at_burst,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")

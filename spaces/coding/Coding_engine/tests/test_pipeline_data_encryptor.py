"""Tests for PipelineDataEncryptor service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_encryptor import PipelineDataEncryptor


# -- ID generation ----------------------------------------------------------


def test_generate_id_has_prefix():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("pipe1", "key1")
    assert rid.startswith("pden-")


def test_generate_id_length():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("pipe1", "key1")
    # PREFIX (5) + 12 hex chars = 17
    assert len(rid) == 17


def test_generate_id_uniqueness():
    enc = PipelineDataEncryptor()
    ids = set()
    for i in range(100):
        rid = enc.encrypt(f"pipe{i}", f"key{i}")
        ids.add(rid)
    assert len(ids) == 100


# -- encrypt basic ----------------------------------------------------------


def test_encrypt_returns_id():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("pipeline_a", "secret_key")
    assert isinstance(rid, str)
    assert len(rid) > 0


def test_encrypt_stores_fields():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("pipeline_a", "secret_key", algorithm="rsa2048")
    entry = enc.get_encryption(rid)
    assert entry["record_id"] == rid
    assert entry["pipeline_id"] == "pipeline_a"
    assert entry["data_key"] == "secret_key"
    assert entry["algorithm"] == "rsa2048"


def test_encrypt_default_algorithm():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("p1", "k1")
    entry = enc.get_encryption(rid)
    assert entry["algorithm"] == "aes256"


def test_encrypt_metadata_deepcopy():
    enc = PipelineDataEncryptor()
    meta = {"level": 5, "tags": ["a", "b"]}
    rid = enc.encrypt("p1", "k1", metadata=meta)
    meta["level"] = 999
    meta["tags"].append("c")
    entry = enc.get_encryption(rid)
    assert entry["metadata"]["level"] == 5
    assert entry["metadata"]["tags"] == ["a", "b"]


def test_encrypt_created_at():
    enc = PipelineDataEncryptor()
    before = time.time()
    rid = enc.encrypt("p1", "k1")
    after = time.time()
    entry = enc.get_encryption(rid)
    assert before <= entry["created_at"] <= after


def test_encrypt_empty_pipeline_id_returns_empty():
    enc = PipelineDataEncryptor()
    assert enc.encrypt("", "key1") == ""


def test_encrypt_empty_data_key_returns_empty():
    enc = PipelineDataEncryptor()
    assert enc.encrypt("pipe1", "") == ""


def test_encrypt_whitespace_pipeline_id_returns_empty():
    enc = PipelineDataEncryptor()
    assert enc.encrypt("   ", "key1") == ""


def test_encrypt_whitespace_data_key_returns_empty():
    enc = PipelineDataEncryptor()
    assert enc.encrypt("pipe1", "   ") == ""


def test_encrypt_none_metadata():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("p1", "k1")
    entry = enc.get_encryption(rid)
    assert entry["metadata"] is None


# -- get_encryption ----------------------------------------------------------


def test_get_encryption_found():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("p1", "k1")
    entry = enc.get_encryption(rid)
    assert entry is not None
    assert entry["record_id"] == rid


def test_get_encryption_not_found():
    enc = PipelineDataEncryptor()
    assert enc.get_encryption("pden-nonexistent") is None


def test_get_encryption_returns_copy():
    enc = PipelineDataEncryptor()
    rid = enc.encrypt("p1", "k1", metadata={"x": 1})
    entry1 = enc.get_encryption(rid)
    entry1["metadata"]["x"] = 999
    entry2 = enc.get_encryption(rid)
    assert entry2["metadata"]["x"] == 1


# -- get_encryptions --------------------------------------------------------


def test_get_encryptions_all():
    enc = PipelineDataEncryptor()
    enc.encrypt("p1", "k1")
    enc.encrypt("p2", "k2")
    enc.encrypt("p3", "k3")
    results = enc.get_encryptions()
    assert len(results) == 3


def test_get_encryptions_filter_by_pipeline():
    enc = PipelineDataEncryptor()
    enc.encrypt("alpha", "k1")
    enc.encrypt("beta", "k2")
    enc.encrypt("alpha", "k3")
    results = enc.get_encryptions(pipeline_id="alpha")
    assert len(results) == 2
    for r in results:
        assert r["pipeline_id"] == "alpha"


def test_get_encryptions_newest_first():
    enc = PipelineDataEncryptor()
    r1 = enc.encrypt("p1", "k1")
    r2 = enc.encrypt("p1", "k2")
    r3 = enc.encrypt("p1", "k3")
    results = enc.get_encryptions()
    assert results[0]["record_id"] == r3
    assert results[2]["record_id"] == r1


def test_get_encryptions_limit():
    enc = PipelineDataEncryptor()
    for i in range(10):
        enc.encrypt("p1", f"k{i}")
    results = enc.get_encryptions(limit=3)
    assert len(results) == 3


def test_get_encryptions_empty():
    enc = PipelineDataEncryptor()
    results = enc.get_encryptions()
    assert results == []


# -- get_encryption_count ----------------------------------------------------


def test_get_encryption_count_total():
    enc = PipelineDataEncryptor()
    enc.encrypt("p1", "k1")
    enc.encrypt("p2", "k2")
    assert enc.get_encryption_count() == 2


def test_get_encryption_count_filtered():
    enc = PipelineDataEncryptor()
    enc.encrypt("alpha", "k1")
    enc.encrypt("beta", "k2")
    enc.encrypt("alpha", "k3")
    assert enc.get_encryption_count(pipeline_id="alpha") == 2
    assert enc.get_encryption_count(pipeline_id="beta") == 1


def test_get_encryption_count_empty():
    enc = PipelineDataEncryptor()
    assert enc.get_encryption_count() == 0


# -- get_stats ---------------------------------------------------------------


def test_get_stats_empty():
    enc = PipelineDataEncryptor()
    stats = enc.get_stats()
    assert stats["total_encryptions"] == 0
    assert stats["unique_pipelines"] == 0


def test_get_stats_with_data():
    enc = PipelineDataEncryptor()
    enc.encrypt("p1", "k1")
    enc.encrypt("p2", "k2")
    enc.encrypt("p1", "k3")
    stats = enc.get_stats()
    assert stats["total_encryptions"] == 3
    assert stats["unique_pipelines"] == 2


# -- callbacks ---------------------------------------------------------------


def test_on_change_fires():
    events = []
    enc = PipelineDataEncryptor()
    enc.on_change = lambda action, data: events.append((action, data))
    enc.encrypt("p1", "k1")
    assert len(events) == 1
    assert events[0][0] == "encrypted"


def test_on_change_property():
    enc = PipelineDataEncryptor()
    assert enc.on_change is None
    cb = lambda a, d: None
    enc.on_change = cb
    assert enc.on_change is cb


def test_callback_fires():
    events = []
    enc = PipelineDataEncryptor()
    enc._state.callbacks["my_cb"] = lambda action, data: events.append(action)
    enc.encrypt("p1", "k1")
    assert "encrypted" in events


def test_remove_callback_true():
    enc = PipelineDataEncryptor()
    enc._state.callbacks["my_cb"] = lambda a, d: None
    assert enc.remove_callback("my_cb") is True
    assert "my_cb" not in enc._state.callbacks


def test_remove_callback_false():
    enc = PipelineDataEncryptor()
    assert enc.remove_callback("nonexistent") is False


# -- prune -------------------------------------------------------------------


def test_prune_removes_oldest_quarter():
    enc = PipelineDataEncryptor()
    enc.MAX_ENTRIES = 5
    for i in range(8):
        enc.encrypt(f"p{i}", f"k{i}")
    assert enc.get_encryption_count() < 8


# -- reset -------------------------------------------------------------------


def test_reset_clears_entries():
    enc = PipelineDataEncryptor()
    enc.encrypt("p1", "k1")
    enc.encrypt("p2", "k2")
    enc.reset()
    assert enc.get_encryption_count() == 0


def test_reset_clears_callbacks():
    enc = PipelineDataEncryptor()
    enc._state.callbacks["cb1"] = lambda a, d: None
    enc.reset()
    assert len(enc._state.callbacks) == 0


def test_reset_resets_seq():
    enc = PipelineDataEncryptor()
    enc.encrypt("p1", "k1")
    enc.reset()
    assert enc._state._seq == 0


def test_reset_clears_on_change():
    enc = PipelineDataEncryptor()
    enc.on_change = lambda a, d: None
    enc.reset()
    assert enc.on_change is None


if __name__ == "__main__":
    tests = [
        test_generate_id_has_prefix,
        test_generate_id_length,
        test_generate_id_uniqueness,
        test_encrypt_returns_id,
        test_encrypt_stores_fields,
        test_encrypt_default_algorithm,
        test_encrypt_metadata_deepcopy,
        test_encrypt_created_at,
        test_encrypt_empty_pipeline_id_returns_empty,
        test_encrypt_empty_data_key_returns_empty,
        test_encrypt_whitespace_pipeline_id_returns_empty,
        test_encrypt_whitespace_data_key_returns_empty,
        test_encrypt_none_metadata,
        test_get_encryption_found,
        test_get_encryption_not_found,
        test_get_encryption_returns_copy,
        test_get_encryptions_all,
        test_get_encryptions_filter_by_pipeline,
        test_get_encryptions_newest_first,
        test_get_encryptions_limit,
        test_get_encryptions_empty,
        test_get_encryption_count_total,
        test_get_encryption_count_filtered,
        test_get_encryption_count_empty,
        test_get_stats_empty,
        test_get_stats_with_data,
        test_on_change_fires,
        test_on_change_property,
        test_callback_fires,
        test_remove_callback_true,
        test_remove_callback_false,
        test_prune_removes_oldest_quarter,
        test_reset_clears_entries,
        test_reset_clears_callbacks,
        test_reset_resets_seq,
        test_reset_clears_on_change,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"{passed}/{passed + failed} tests passed")

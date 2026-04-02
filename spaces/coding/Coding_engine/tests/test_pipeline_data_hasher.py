"""Tests for PipelineDataHasher service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_hasher import PipelineDataHasher


def test_hash_data_sha256():
    h = PipelineDataHasher()
    result = h.hash_data("hello")
    assert isinstance(result, str)
    assert len(result) == 64  # SHA256 hex length


def test_hash_data_md5():
    h = PipelineDataHasher()
    result = h.hash_data("hello", algorithm="md5")
    assert isinstance(result, str)
    assert len(result) == 32  # MD5 hex length


def test_hash_data_sha1():
    h = PipelineDataHasher()
    result = h.hash_data("hello", algorithm="sha1")
    assert isinstance(result, str)
    assert len(result) == 40  # SHA1 hex length


def test_hash_data_unsupported_algorithm():
    h = PipelineDataHasher()
    try:
        h.hash_data("hello", algorithm="sha512")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_register_hash():
    h = PipelineDataHasher()
    hash_id = h.register_hash("test_entry", "some data")
    assert hash_id.startswith("pdha-")
    assert h.get_hash_count() == 1


def test_get_hash():
    h = PipelineDataHasher()
    hash_id = h.register_hash("my_hash", "payload")
    entry = h.get_hash(hash_id)
    assert entry["name"] == "my_hash"
    assert entry["algorithm"] == "sha256"
    assert entry["data_length"] == len("payload")
    assert "data_hash" in entry
    assert "created_at" in entry


def test_get_hash_not_found():
    h = PipelineDataHasher()
    assert h.get_hash("pdha-nonexistent") == {}


def test_verify_correct():
    h = PipelineDataHasher()
    hash_id = h.register_hash("v1", "test data")
    assert h.verify(hash_id, "test data") is True


def test_verify_incorrect():
    h = PipelineDataHasher()
    hash_id = h.register_hash("v2", "test data")
    assert h.verify(hash_id, "wrong data") is False


def test_verify_missing_id():
    h = PipelineDataHasher()
    assert h.verify("pdha-missing", "data") is False


def test_get_hashes():
    h = PipelineDataHasher()
    h.register_hash("a", "data1")
    h.register_hash("b", "data2")
    hashes = h.get_hashes()
    assert len(hashes) == 2


def test_find_duplicates():
    h = PipelineDataHasher()
    h.register_hash("first", "same content")
    h.register_hash("second", "same content")
    h.register_hash("third", "different content")
    dupes = h.find_duplicates("same content")
    assert len(dupes) == 2


def test_find_duplicates_none():
    h = PipelineDataHasher()
    h.register_hash("entry", "original")
    dupes = h.find_duplicates("no match")
    assert len(dupes) == 0


def test_remove_hash():
    h = PipelineDataHasher()
    hash_id = h.register_hash("rem", "remove me")
    assert h.remove_hash(hash_id) is True
    assert h.get_hash_count() == 0
    assert h.remove_hash(hash_id) is False


def test_get_stats():
    h = PipelineDataHasher()
    h.register_hash("s1", "data1")
    h.register_hash("s2", "data1")
    h.verify(h.register_hash("s3", "data3"), "data3")
    h.find_duplicates("data1")
    stats = h.get_stats()
    assert stats["total_hashes"] == 3
    assert stats["total_verifications"] == 1
    assert stats["total_duplicates_found"] == 2


def test_reset():
    h = PipelineDataHasher()
    h.register_hash("r1", "reset data")
    h.reset()
    assert h.get_hash_count() == 0
    assert h.get_hashes() == []


def test_on_change_callback():
    events = []
    h = PipelineDataHasher()
    h.on_change = lambda e, d: events.append(e)
    h.register_hash("cb", "callback data")
    assert "register" in events


def test_remove_callback():
    h = PipelineDataHasher()
    h._callbacks["my_cb"] = lambda e, d: None
    assert h.remove_callback("my_cb") is True
    assert h.remove_callback("my_cb") is False


def test_generate_id_uniqueness():
    h = PipelineDataHasher()
    ids = set()
    for i in range(100):
        hash_id = h.register_hash(f"u{i}", f"data{i}")
        ids.add(hash_id)
    assert len(ids) == 100


if __name__ == "__main__":
    tests = [
        test_hash_data_sha256,
        test_hash_data_md5,
        test_hash_data_sha1,
        test_hash_data_unsupported_algorithm,
        test_register_hash,
        test_get_hash,
        test_get_hash_not_found,
        test_verify_correct,
        test_verify_incorrect,
        test_verify_missing_id,
        test_get_hashes,
        test_find_duplicates,
        test_find_duplicates_none,
        test_remove_hash,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_generate_id_uniqueness,
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

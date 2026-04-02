import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_decryptor import PipelineDataDecryptor


def _make():
    return PipelineDataDecryptor()


# --- prefix and ID ---

def test_prefix():
    s = _make()
    rid = s.decrypt("p1", "k1")
    assert rid.startswith("pddy-")


def test_id_length():
    s = _make()
    rid = s.decrypt("p1", "k1")
    assert len(rid) == len("pddy-") + 12


def test_uniqueness():
    s = _make()
    ids = {s.decrypt("p1", f"k{i}") for i in range(20)}
    assert len(ids) == 20


# --- stores fields ---

def test_stores_pipeline_id():
    s = _make()
    rid = s.decrypt("pipe-a", "key-b", algorithm="rsa")
    entry = s.get_decryption(rid)
    assert entry["pipeline_id"] == "pipe-a"
    assert entry["data_key"] == "key-b"
    assert entry["algorithm"] == "rsa"


def test_default_algorithm():
    s = _make()
    rid = s.decrypt("p1", "k1")
    assert s.get_decryption(rid)["algorithm"] == "aes256"


def test_metadata_stored():
    s = _make()
    rid = s.decrypt("p1", "k1", metadata={"x": 1})
    assert s.get_decryption(rid)["metadata"] == {"x": 1}


def test_metadata_deepcopy():
    s = _make()
    meta = {"nested": [1, 2]}
    rid = s.decrypt("p1", "k1", metadata=meta)
    meta["nested"].append(3)
    assert s.get_decryption(rid)["metadata"]["nested"] == [1, 2]


def test_created_at():
    s = _make()
    before = time.time()
    rid = s.decrypt("p1", "k1")
    after = time.time()
    entry = s.get_decryption(rid)
    assert before <= entry["created_at"] <= after


# --- empty validation ---

def test_empty_pipeline_id_returns_empty():
    s = _make()
    assert s.decrypt("", "k1") == ""


def test_empty_data_key_returns_empty():
    s = _make()
    assert s.decrypt("p1", "") == ""


def test_both_empty_returns_empty():
    s = _make()
    assert s.decrypt("", "") == ""


# --- get_decryption ---

def test_get_found():
    s = _make()
    rid = s.decrypt("p1", "k1")
    assert s.get_decryption(rid) is not None


def test_get_not_found():
    s = _make()
    assert s.get_decryption("pddy-nonexistent") is None


def test_get_returns_copy():
    s = _make()
    rid = s.decrypt("p1", "k1")
    a = s.get_decryption(rid)
    b = s.get_decryption(rid)
    assert a == b
    assert a is not b


# --- get_decryptions list ---

def test_list_all():
    s = _make()
    s.decrypt("p1", "k1")
    s.decrypt("p2", "k2")
    assert len(s.get_decryptions()) == 2


def test_list_filter():
    s = _make()
    s.decrypt("p1", "k1")
    s.decrypt("p2", "k2")
    s.decrypt("p1", "k3")
    result = s.get_decryptions(pipeline_id="p1")
    assert len(result) == 2
    assert all(r["pipeline_id"] == "p1" for r in result)


def test_list_newest_first():
    s = _make()
    r1 = s.decrypt("p1", "k1")
    r2 = s.decrypt("p1", "k2")
    result = s.get_decryptions()
    assert result[0]["record_id"] == r2
    assert result[1]["record_id"] == r1


def test_list_limit():
    s = _make()
    for i in range(10):
        s.decrypt("p1", f"k{i}")
    assert len(s.get_decryptions(limit=3)) == 3


# --- count ---

def test_count_total():
    s = _make()
    s.decrypt("p1", "k1")
    s.decrypt("p2", "k2")
    assert s.get_decryption_count() == 2


def test_count_filtered():
    s = _make()
    s.decrypt("p1", "k1")
    s.decrypt("p2", "k2")
    s.decrypt("p1", "k3")
    assert s.get_decryption_count(pipeline_id="p1") == 2


def test_count_empty():
    s = _make()
    assert s.get_decryption_count() == 0


# --- stats ---

def test_stats_empty():
    s = _make()
    st = s.get_stats()
    assert st["total_decryptions"] == 0
    assert st["unique_pipelines"] == 0


def test_stats_with_data():
    s = _make()
    s.decrypt("p1", "k1")
    s.decrypt("p2", "k2")
    s.decrypt("p1", "k3")
    st = s.get_stats()
    assert st["total_decryptions"] == 3
    assert st["unique_pipelines"] == 2


# --- callbacks ---

def test_on_change_called():
    s = _make()
    calls = []
    s.on_change = lambda action, data: calls.append((action, data))
    s.decrypt("p1", "k1")
    assert len(calls) == 1
    assert calls[0][0] == "decrypted"


def test_callback_called():
    s = _make()
    calls = []
    s._state.callbacks["cb1"] = lambda action, data: calls.append((action, data))
    s.decrypt("p1", "k1")
    assert len(calls) == 1
    assert calls[0][0] == "decrypted"


def test_remove_callback_true():
    s = _make()
    s._state.callbacks["cb1"] = lambda a, d: None
    assert s.remove_callback("cb1") is True
    assert "cb1" not in s._state.callbacks


def test_remove_callback_false():
    s = _make()
    assert s.remove_callback("nope") is False


def test_callback_exception_does_not_crash():
    s = _make()
    s.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
    rid = s.decrypt("p1", "k1")
    assert rid != ""


# --- prune ---

def test_prune():
    s = _make()
    s.MAX_ENTRIES = 5
    for i in range(8):
        s.decrypt("p1", f"k{i}")
    assert s.get_decryption_count() < 8


# --- reset ---

def test_reset_clears_entries():
    s = _make()
    s.decrypt("p1", "k1")
    s.reset()
    assert s.get_decryption_count() == 0


def test_reset_clears_callbacks():
    s = _make()
    s._state.callbacks["cb1"] = lambda a, d: None
    s.reset()
    assert len(s._state.callbacks) == 0


def test_reset_clears_seq():
    s = _make()
    s.decrypt("p1", "k1")
    s.reset()
    assert s._state._seq == 0

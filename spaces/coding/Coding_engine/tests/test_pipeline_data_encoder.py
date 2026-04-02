"""Tests for PipelineDataEncoder service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_encoder import PipelineDataEncoder


def test_encode_base64():
    enc = PipelineDataEncoder()
    result = enc.encode("hello world")
    assert result == "aGVsbG8gd29ybGQ="


def test_decode_base64():
    enc = PipelineDataEncoder()
    result = enc.decode("aGVsbG8gd29ybGQ=")
    assert result == "hello world"


def test_encode_hex():
    enc = PipelineDataEncoder()
    result = enc.encode("hello", encoding="hex")
    assert result == "68656c6c6f"


def test_decode_hex():
    enc = PipelineDataEncoder()
    result = enc.decode("68656c6c6f", encoding="hex")
    assert result == "hello"


def test_encode_url():
    enc = PipelineDataEncoder()
    result = enc.encode("hello world&foo=bar", encoding="url")
    assert "hello" in result
    assert "%20" in result or "+" in result


def test_decode_url():
    enc = PipelineDataEncoder()
    encoded = enc.encode("hello world&foo=bar", encoding="url")
    decoded = enc.decode(encoded, encoding="url")
    assert decoded == "hello world&foo=bar"


def test_encode_unsupported():
    enc = PipelineDataEncoder()
    try:
        enc.encode("data", encoding="rot13")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_decode_unsupported():
    enc = PipelineDataEncoder()
    try:
        enc.decode("data", encoding="rot13")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_roundtrip_base64():
    enc = PipelineDataEncoder()
    original = "The quick brown fox jumps over the lazy dog!"
    assert enc.decode(enc.encode(original)) == original


def test_roundtrip_hex():
    enc = PipelineDataEncoder()
    original = "binary-like data: \x01\x02\x03"
    assert enc.decode(enc.encode(original, "hex"), "hex") == original


def test_register_encoding():
    enc = PipelineDataEncoder()
    config_id = enc.register_encoding("my_config", encoding="hex")
    assert config_id.startswith("pden-")
    assert enc.get_encoding_count() == 1


def test_get_encoding():
    enc = PipelineDataEncoder()
    config_id = enc.register_encoding("test_enc", encoding="base64", metadata={"purpose": "test"})
    entry = enc.get_encoding(config_id)
    assert entry["name"] == "test_enc"
    assert entry["encoding"] == "base64"
    assert entry["metadata"] == {"purpose": "test"}
    assert entry["usage_count"] == 0
    assert "created_at" in entry


def test_get_encoding_not_found():
    enc = PipelineDataEncoder()
    assert enc.get_encoding("pden-nonexistent") == {}


def test_apply_encoding():
    enc = PipelineDataEncoder()
    config_id = enc.register_encoding("apply_test", encoding="hex")
    result = enc.apply_encoding(config_id, "hello")
    assert result["config_id"] == config_id
    assert result["encoded"] == "68656c6c6f"
    assert result["original_length"] == 5
    assert result["encoded_length"] == 10
    # usage_count should have incremented
    assert enc.get_encoding(config_id)["usage_count"] == 1


def test_apply_encoding_missing():
    enc = PipelineDataEncoder()
    result = enc.apply_encoding("pden-missing", "data")
    assert result == {}


def test_get_encodings():
    enc = PipelineDataEncoder()
    enc.register_encoding("a", encoding="base64")
    enc.register_encoding("b", encoding="hex")
    encodings = enc.get_encodings()
    assert len(encodings) == 2


def test_remove_encoding():
    enc = PipelineDataEncoder()
    config_id = enc.register_encoding("removable", encoding="url")
    assert enc.remove_encoding(config_id) is True
    assert enc.get_encoding_count() == 0
    assert enc.remove_encoding(config_id) is False


def test_get_stats():
    enc = PipelineDataEncoder()
    c1 = enc.register_encoding("s1", encoding="base64")
    c2 = enc.register_encoding("s2", encoding="hex")
    enc.apply_encoding(c1, "data1")
    enc.apply_encoding(c1, "data2")
    enc.apply_encoding(c2, "data3")
    stats = enc.get_stats()
    assert stats["total_encodings"] == 2
    assert stats["total_operations"] == 3


def test_reset():
    enc = PipelineDataEncoder()
    enc.register_encoding("r1", encoding="base64")
    enc.reset()
    assert enc.get_encoding_count() == 0
    assert enc.get_encodings() == []


def test_on_change_callback():
    events = []
    enc = PipelineDataEncoder()
    enc.on_change = lambda e, d: events.append(e)
    enc.register_encoding("cb", encoding="base64")
    assert "register" in events


def test_remove_callback():
    enc = PipelineDataEncoder()
    enc._callbacks["my_cb"] = lambda e, d: None
    assert enc.remove_callback("my_cb") is True
    assert enc.remove_callback("my_cb") is False


def test_generate_id_uniqueness():
    enc = PipelineDataEncoder()
    ids = set()
    for i in range(100):
        config_id = enc.register_encoding(f"u{i}", encoding="base64")
        ids.add(config_id)
    assert len(ids) == 100


if __name__ == "__main__":
    tests = [
        test_encode_base64,
        test_decode_base64,
        test_encode_hex,
        test_decode_hex,
        test_encode_url,
        test_decode_url,
        test_encode_unsupported,
        test_decode_unsupported,
        test_roundtrip_base64,
        test_roundtrip_hex,
        test_register_encoding,
        test_get_encoding,
        test_get_encoding_not_found,
        test_apply_encoding,
        test_apply_encoding_missing,
        test_get_encodings,
        test_remove_encoding,
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

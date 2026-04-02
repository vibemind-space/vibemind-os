import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_tokenizer import PipelineDataTokenizer


def test_register_tokenizer():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("words")
    assert tid.startswith("pdt2-")
    assert len(tid) == 5 + 16


def test_get_tokenizer():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("words", mode="word")
    info = t.get_tokenizer(tid)
    assert info["name"] == "words"
    assert info["mode"] == "word"
    assert info["usage_count"] == 0


def test_get_tokenizer_not_found():
    t = PipelineDataTokenizer()
    try:
        t.get_tokenizer("pdt2-nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_tokenize_word_mode():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("w", mode="word")
    result = t.tokenize(tid, "hello world foo bar")
    assert result["tokens"] == ["hello", "world", "foo", "bar"]
    assert result["token_count"] == 4
    assert result["original_length"] == 19
    assert result["tokenizer_id"] == tid


def test_tokenize_sentence_mode():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("s", mode="sentence")
    result = t.tokenize(tid, "Hello world. This is a test. Done")
    assert result["token_count"] == 3
    assert "Hello world" in result["tokens"][0]


def test_tokenize_custom_mode():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("c", delimiter="|", mode="custom")
    result = t.tokenize(tid, "a|b|c|d")
    assert result["tokens"] == ["a", "b", "c", "d"]
    assert result["token_count"] == 4


def test_tokenize_not_found():
    t = PipelineDataTokenizer()
    try:
        t.tokenize("pdt2-fake", "text")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_tokenize_field():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("w", mode="word")
    records = [
        {"id": 1, "text": "hello world"},
        {"id": 2, "text": "foo bar baz"},
    ]
    results = t.tokenize_field(tid, records, "text")
    assert len(results) == 2
    assert results[0]["text_tokens"] == ["hello", "world"]
    assert results[1]["text_tokens"] == ["foo", "bar", "baz"]
    assert results[0]["id"] == 1


def test_get_tokenizers():
    t = PipelineDataTokenizer()
    t.register_tokenizer("a")
    t.register_tokenizer("b")
    assert len(t.get_tokenizers()) == 2


def test_get_tokenizer_count():
    t = PipelineDataTokenizer()
    assert t.get_tokenizer_count() == 0
    t.register_tokenizer("a")
    assert t.get_tokenizer_count() == 1
    t.register_tokenizer("b")
    assert t.get_tokenizer_count() == 2


def test_remove_tokenizer():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("x")
    assert t.remove_tokenizer(tid) is True
    assert t.get_tokenizer_count() == 0
    assert t.remove_tokenizer(tid) is False


def test_get_stats():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("w", mode="word")
    t.tokenize(tid, "a b c")
    t.tokenize(tid, "d e")
    stats = t.get_stats()
    assert stats["total_tokenizers"] == 1
    assert stats["total_tokenizations"] == 2
    assert stats["total_tokens_generated"] == 5


def test_reset():
    t = PipelineDataTokenizer()
    t.register_tokenizer("x")
    t.reset()
    assert t.get_tokenizer_count() == 0
    assert t.get_stats()["total_tokens_generated"] == 0


def test_on_change_callback():
    t = PipelineDataTokenizer()
    events = []
    t.on_change = lambda e, d: events.append(e)
    t.register_tokenizer("x")
    assert "register_tokenizer" in events


def test_remove_callback():
    t = PipelineDataTokenizer()
    t._callbacks["cb1"] = lambda e, d: None
    assert t.remove_callback("cb1") is True
    assert t.remove_callback("cb1") is False


def test_callback_error_handling():
    t = PipelineDataTokenizer()
    t.on_change = lambda e, d: (_ for _ in ()).throw(ValueError("boom"))
    # Should not raise, error is caught
    tid = t.register_tokenizer("x")
    assert tid.startswith("pdt2-")


def test_generate_id_unique():
    t = PipelineDataTokenizer()
    id1 = t._generate_id("same")
    id2 = t._generate_id("same")
    assert id1 != id2


def test_usage_count_increments():
    t = PipelineDataTokenizer()
    tid = t.register_tokenizer("w", mode="word")
    t.tokenize(tid, "a b")
    t.tokenize(tid, "c d")
    info = t.get_tokenizer(tid)
    assert info["usage_count"] == 2


if __name__ == "__main__":
    tests = [
        test_register_tokenizer,
        test_get_tokenizer,
        test_get_tokenizer_not_found,
        test_tokenize_word_mode,
        test_tokenize_sentence_mode,
        test_tokenize_custom_mode,
        test_tokenize_not_found,
        test_tokenize_field,
        test_get_tokenizers,
        test_get_tokenizer_count,
        test_remove_tokenizer,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_callback_error_handling,
        test_generate_id_unique,
        test_usage_count_increments,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")

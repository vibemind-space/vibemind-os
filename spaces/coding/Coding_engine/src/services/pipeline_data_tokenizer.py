import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataTokenizerState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineDataTokenizer:
    PREFIX = "pdt2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataTokenizerState()
        self._callbacks = {}
        self._on_change = None
        self._total_tokens_generated = 0

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hex_digest = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + hex_digest[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", "")
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    def _fire(self, event, data):
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error(f"on_change callback error: {e}")
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error(f"Callback '{name}' error: {e}")

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, value):
        self._on_change = value

    def remove_callback(self, name) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def register_tokenizer(self, name, delimiter=" ", mode="word") -> str:
        tid = self._generate_id(name)
        self._state.entries[tid] = {
            "id": tid,
            "name": name,
            "delimiter": delimiter,
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "usage_count": 0,
        }
        self._prune()
        self._fire("register_tokenizer", {"id": tid, "name": name})
        return tid

    def tokenize(self, tokenizer_id, text: str) -> dict:
        if tokenizer_id not in self._state.entries:
            raise KeyError(f"Tokenizer '{tokenizer_id}' not found")
        entry = self._state.entries[tokenizer_id]
        mode = entry["mode"]
        delimiter = entry["delimiter"]

        if mode == "word":
            tokens = text.split()
        elif mode == "sentence":
            tokens = [s.strip() for s in text.split(". ") if s.strip()]
        elif mode == "custom":
            tokens = [t for t in text.split(delimiter) if t != ""]
        else:
            tokens = text.split()

        entry["usage_count"] += 1
        self._total_tokens_generated += len(tokens)

        result = {
            "tokenizer_id": tokenizer_id,
            "tokens": tokens,
            "token_count": len(tokens),
            "original_length": len(text),
        }
        self._fire("tokenize", result)
        return result

    def tokenize_field(self, tokenizer_id, records: list, field_name: str) -> list:
        results = []
        for record in records:
            new_record = dict(record)
            text = record.get(field_name, "")
            tok_result = self.tokenize(tokenizer_id, text)
            new_record[f"{field_name}_tokens"] = tok_result["tokens"]
            results.append(new_record)
        return results

    def get_tokenizer(self, tokenizer_id) -> dict:
        if tokenizer_id not in self._state.entries:
            raise KeyError(f"Tokenizer '{tokenizer_id}' not found")
        return dict(self._state.entries[tokenizer_id])

    def get_tokenizers(self) -> list:
        return [dict(v) for v in self._state.entries.values()]

    def get_tokenizer_count(self) -> int:
        return len(self._state.entries)

    def remove_tokenizer(self, tokenizer_id) -> bool:
        if tokenizer_id in self._state.entries:
            del self._state.entries[tokenizer_id]
            self._fire("remove_tokenizer", {"id": tokenizer_id})
            return True
        return False

    def get_stats(self) -> dict:
        total_tokenizations = sum(
            e["usage_count"] for e in self._state.entries.values()
        )
        return {
            "total_tokenizers": len(self._state.entries),
            "total_tokenizations": total_tokenizations,
            "total_tokens_generated": self._total_tokens_generated,
        }

    def reset(self):
        self._state = PipelineDataTokenizerState()
        self._callbacks = {}
        self._on_change = None
        self._total_tokens_generated = 0
        self._fire("reset", {})

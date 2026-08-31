"""
TriBE v2 Inference Wrapper for Brain.

Wraps Meta's TriBE v2 fMRI encoder (facebook/tribev2) so Brain can produce
a biologically-plausible neural signature for any piece of text — a vector
of predicted cortical activation across ~20k fsaverage5 vertices.

Two use sites:
  1) qdrant_kg.py — writes the neural signature alongside the semantic
     embedding for every Brain thought, enabling cross-retrieval by
     "would resonate in similar brain regions".
  2) brain_chat.py bridges — limbic, defense, cortex etc. can read
     ROI-specific activation levels and modulate without the current
     heuristic state machine.

Design:
  - Model is **lazy-loaded** on first predict() call. The first call pulls
    ~GB of weights from huggingface_hub — blocking. Brain startup is not
    blocked.
  - Thread-safe. One model lives in memory, predict() holds a lock.
  - Graceful degradation: if TriBE fails to load (no disk, no network,
    version mismatch), predict() returns None instead of crashing Brain.
  - Text input only. Audio/video paths exist in TriBE but are heavy
    pipelines (TTS + transcription) unsuited to every-thought embedding.

Environment variables:
  TRIBE_CHECKPOINT     — default "facebook/tribev2" (HF Hub id) or local path
  TRIBE_DEVICE         — "auto" | "cpu" | "cuda" (default auto)
  TRIBE_CACHE_FOLDER   — where TriBE caches features (default ~/.cache/tribev2)
  TRIBE_ENABLED        — "1"/"true" to actually load (default "1"; set "0"
                         to run Brain with TriBE-disabled / dummy vectors).

Public API:
  encoder = TribeEncoder.get()
  vec = encoder.predict(text) -> Optional[np.ndarray]  # shape (~20484,) or None
  rois = encoder.aggregate_roi(vec) -> dict[str, float]
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import sys as _sys

import numpy as np

logger = logging.getLogger(__name__)

# Make the vendored TriBE checkout importable without a pip install.
# Structure: vibemind-os/brain/the_brain/tribe/tribev2/  (the package)
_TRIBE_VENDOR_DIR = Path(__file__).resolve().parent.parent / "tribe"
if _TRIBE_VENDOR_DIR.is_dir() and str(_TRIBE_VENDOR_DIR) not in _sys.path:
    _sys.path.insert(0, str(_TRIBE_VENDOR_DIR))


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

TRIBE_CHECKPOINT = os.environ.get("TRIBE_CHECKPOINT", "facebook/tribev2")
TRIBE_DEVICE = os.environ.get("TRIBE_DEVICE", "auto")
TRIBE_CACHE_FOLDER = os.environ.get(
    "TRIBE_CACHE_FOLDER",
    str(Path.home() / ".cache" / "tribev2"),
)
TRIBE_ENABLED = os.environ.get("TRIBE_ENABLED", "1").lower() in ("1", "true", "yes")

# Dummy mode: skip real model load, return deterministic fake vectors so
# downstream wiring (bridge mapping, HTTP endpoints, Brain chat hooks) can
# be developed and tested without gated Llama-3.2-3B weights.
TRIBE_DUMMY = os.environ.get("TRIBE_DUMMY", "0").lower() in ("1", "true", "yes")

# fsaverage5 mesh has ~20484 vertices. Actual model output may vary; we
# expose whatever shape the model produces.
EXPECTED_VERTEX_COUNT = 20484


# ──────────────────────────────────────────────────────────────────────
# ROI Mapping — coarse vertex-index ranges per cortical region.
# ──────────────────────────────────────────────────────────────────────
#
# These ranges are approximate. Real vertex-to-ROI mapping uses the
# Destrieux or Schaefer atlas (shipped with nilearn). For v1 we use
# coarse left/right hemisphere splits and rough regional slices on
# fsaverage5. Swap in a proper atlas via roi_bridge_mapper.py later.

DEFAULT_ROI_RANGES: Dict[str, slice] = {
    # Left hemisphere: 0..10242
    "prefrontal_L":  slice(0, 1500),     # ~cortex, DMN anterior
    "motor_L":       slice(1500, 2500),  # M1/premotor
    "somatosensory_L": slice(2500, 3500),  # visceral/touch
    "temporal_L":    slice(3500, 5500),   # auditory + social STS
    "parietal_L":    slice(5500, 7500),   # integration, DMN
    "occipital_L":   slice(7500, 9000),   # visual
    "insula_L":      slice(9000, 9700),   # limbic/defense
    "cingulate_L":   slice(9700, 10242),  # salience/defense
    # Right hemisphere: 10242..20484
    "prefrontal_R":  slice(10242, 11742),
    "motor_R":       slice(11742, 12742),
    "somatosensory_R": slice(12742, 13742),
    "temporal_R":    slice(13742, 15742),
    "parietal_R":    slice(15742, 17742),
    "occipital_R":   slice(17742, 19242),
    "insula_R":      slice(19242, 19942),
    "cingulate_R":   slice(19942, 20484),
}


# Mapping Brain-bridges → ROI aggregation spec.
# Values are list of (roi_name, weight). Aggregated as weighted mean.
BRIDGE_ROI_MAP: Dict[str, list] = {
    "cortex":      [("prefrontal_L", 1.0), ("prefrontal_R", 1.0),
                    ("parietal_L", 0.5), ("parietal_R", 0.5)],
    "limbic":      [("insula_L", 1.0), ("insula_R", 1.0),
                    ("cingulate_L", 0.8), ("cingulate_R", 0.8)],
    "defense":     [("insula_L", 0.7), ("insula_R", 0.7),
                    ("cingulate_L", 1.0), ("cingulate_R", 1.0)],
    "motor":       [("motor_L", 1.0), ("motor_R", 1.0)],
    "visceral":    [("somatosensory_L", 1.0), ("somatosensory_R", 1.0)],
    "social":      [("temporal_L", 1.0), ("temporal_R", 1.0)],
    "integration": [("parietal_L", 1.0), ("parietal_R", 1.0),
                    ("prefrontal_L", 0.5), ("prefrontal_R", 0.5)],
    "memory":      [("temporal_L", 0.7), ("temporal_R", 0.7),
                    ("parietal_L", 0.5), ("parietal_R", 0.5)],
    # sleep_wake + neuromod: no cortex correlate, kept heuristic elsewhere.
}


# ──────────────────────────────────────────────────────────────────────
# In-process transcription (robust whisperx replacement for real audio)
# ──────────────────────────────────────────────────────────────────────

# faster-whisper model name for transcribing REAL audio/video (multimodal path).
# Default "small" balances speed/accuracy; override via env. Loaded once, cached.
TRIBE_WHISPER_MODEL = os.environ.get("TRIBE_WHISPER_MODEL", "small")
_FW_MODEL = None
_FW_LOCK = threading.Lock()

# TriBE language name -> whisper language code
_WHISPER_LANG = {
    "english": "en", "french": "fr", "spanish": "es",
    "dutch": "nl", "chinese": "zh", "german": "de",
}


def _faster_whisper_transcript(wav_filename, language):
    """Transcribe a wav to a TriBE word-events DataFrame, IN-PROCESS.

    Replaces TriBE's `uvx whisperx` subprocess (which dies on Windows via the
    torchcodec/FFmpeg DLL chain). Uses faster-whisper with word timestamps and
    returns the same columns the original produced:
    {text, start, duration, sequence_id, sentence}.
    """
    import pandas as _pd
    global _FW_MODEL
    try:
        from pathlib import Path as _Path
        if _FW_MODEL is None:
            with _FW_LOCK:
                if _FW_MODEL is None:
                    from faster_whisper import WhisperModel
                    import torch as _torch
                    dev = "cuda" if _torch.cuda.is_available() else "cpu"
                    ctype = "float16" if dev == "cuda" else "int8"
                    logger.info("[TriBE] loading faster-whisper '%s' on %s",
                                TRIBE_WHISPER_MODEL, dev)
                    _FW_MODEL = WhisperModel(TRIBE_WHISPER_MODEL, device=dev,
                                             compute_type=ctype)
        lang = _WHISPER_LANG.get(language)  # None → auto-detect
        segments, _info = _FW_MODEL.transcribe(
            str(wav_filename), language=lang, word_timestamps=True,
        )
        rows = []
        for i, seg in enumerate(segments):
            sentence = (seg.text or "").replace('"', "")[:500]
            for w in (seg.words or []):
                if w.start is None:
                    continue
                rows.append({
                    "text": (w.word or "").replace('"', "").strip(),
                    "start": float(w.start),
                    "duration": float(w.end) - float(w.start),
                    "sequence_id": i,
                    "sentence": sentence,
                })
        return _pd.DataFrame(rows)
    except Exception as e:
        logger.warning("[TriBE] faster-whisper transcript failed: %s", e)
        return _pd.DataFrame(
            columns=["text", "start", "duration", "sequence_id", "sentence"]
        )


# ──────────────────────────────────────────────────────────────────────
# Encoder
# ──────────────────────────────────────────────────────────────────────

class TribeEncoder:
    """Singleton lazy-loaded TriBE inference wrapper."""

    _instance: Optional["TribeEncoder"] = None
    _instance_lock = threading.Lock()

    # ── Singleton ────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "TribeEncoder":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._model = None
        self._model_lock = threading.Lock()
        self._load_error: Optional[str] = None
        self._load_attempted = False
        self._text_to_events = None

        # Stats
        self.stats = {
            "predictions": 0,
            "failures": 0,
            "last_error": None,
            "last_predict_ms": None,
            "model_loaded": False,
        }

    # ── Lazy load ────────────────────────────────────────────────────

    def _ensure_loaded(self) -> bool:
        """Load TriBE model on first use. Returns True on success."""
        if self._model is not None:
            return True
        if self._load_attempted and self._load_error:
            return False
        if not TRIBE_ENABLED:
            self._load_error = "TRIBE_ENABLED=false"
            return False

        with self._model_lock:
            if self._model is not None:
                return True
            self._load_attempted = True
            try:
                t0 = time.time()
                logger.info(
                    "[TriBE] loading model from %s (first call may download ~GB)",
                    TRIBE_CHECKPOINT,
                )
                Path(TRIBE_CACHE_FOLDER).mkdir(parents=True, exist_ok=True)
                # Import here so Brain startup doesn't pay import cost.
                import torch  # noqa: F401

                # Windows shim for TriBE's YAML configs that contain
                # !!python/object/apply:pathlib.PosixPath. Without this,
                # YAML.UnsafeLoader crashes with
                # "NotImplementedError: cannot instantiate 'PosixPath'".
                import pathlib as _pathlib
                import sys as _sys
                if _sys.platform == "win32" and not hasattr(_pathlib, "_PosixPath_patched"):
                    _pathlib.PosixPath = _pathlib.WindowsPath  # type: ignore[misc]
                    _pathlib._PosixPath_patched = True  # type: ignore[attr-defined]

                # Windows bypass for whisperx subprocess.  TriBE calls
                # `uvx whisperx` as an external process, which needs
                # torchcodec + FFmpeg DLLs linked correctly inside its own
                # venv — a minefield on Windows. Since we already hold the
                # source text (we gave it to TTS), we can synthesise the
                # transcript directly from that text with fake per-word
                # timestamps. Accurate enough for TriBE's encoder since it
                # chunks on TR=1.5s anyway.
                from tribev2 import eventstransforms as _et
                if not hasattr(_et, "_brain_transcript_patched"):
                    import pandas as _pd
                    _original = _et.ExtractWordsFromAudio._get_transcript_from_audio

                    def _synth_transcript(wav_filename, language):
                        """Build word-level events.

                        Two cases:
                          1. We already hold the source text (gTTS/text path):
                             synthesise fake per-word timestamps — fast, no model.
                          2. Real audio/video (we don't know the words): transcribe
                             the wav IN-PROCESS with faster-whisper (no uvx subprocess,
                             no torchcodec DLL hell) to get real word timings.
                        """
                        src_text = getattr(
                            _et.ExtractWordsFromAudio, "_brain_current_text", None
                        )
                        if src_text:
                            # Fake a reading pace: ~2.5 words/sec (typical TTS)
                            words = [w for w in src_text.split() if w.strip()]
                            dur = 1.0 / 2.5
                            sentence = src_text[:500]
                            return _pd.DataFrame([{
                                "text": w, "start": i * dur, "duration": dur,
                                "sequence_id": 0, "sentence": sentence,
                            } for i, w in enumerate(words)])
                        # Case 2 — real audio: in-process faster-whisper.
                        return _faster_whisper_transcript(wav_filename, language)

                    _et.ExtractWordsFromAudio._get_transcript_from_audio = (
                        staticmethod(_synth_transcript)
                    )
                    _et._brain_transcript_patched = True
                    logger.info("[TriBE] patched ExtractWordsFromAudio to bypass whisperx")

                from tribev2.demo_utils import TribeModel, TextToEvents
                device = TRIBE_DEVICE
                if device == "auto":
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"

                # Workaround for TriBE's Windows-unsafe from_pretrained:
                # it wraps the arg in Path() before deciding HF vs local,
                # which mangles "facebook/tribev2" into "facebook\\tribev2".
                # Pre-download to a local dir and hand TriBE the real path.
                checkpoint_arg = TRIBE_CHECKPOINT
                if "/" in TRIBE_CHECKPOINT and not Path(TRIBE_CHECKPOINT).exists():
                    from huggingface_hub import hf_hub_download
                    local_dir = Path(TRIBE_CACHE_FOLDER) / TRIBE_CHECKPOINT.replace("/", "--")
                    local_dir.mkdir(parents=True, exist_ok=True)
                    logger.info("[TriBE] pre-downloading config.yaml + best.ckpt to %s", local_dir)
                    hf_hub_download(
                        TRIBE_CHECKPOINT, "config.yaml",
                        local_dir=str(local_dir),
                    )
                    hf_hub_download(
                        TRIBE_CHECKPOINT, "best.ckpt",
                        local_dir=str(local_dir),
                    )
                    checkpoint_arg = str(local_dir)
                    logger.info("[TriBE] checkpoint ready at %s", checkpoint_arg)

                self._model = TribeModel.from_pretrained(
                    checkpoint_arg,
                    cache_folder=TRIBE_CACHE_FOLDER,
                    device=device,
                )
                # Disable DataLoader multiprocessing workers — they crash
                # under uvicorn / Brain server because Windows multiprocessing
                # tries to re-import the FastAPI module in each worker.
                try:
                    if hasattr(self._model, "data"):
                        self._model.data.num_workers = 0
                except Exception as _e:
                    logger.debug("[TriBE] could not pin num_workers=0: %s", _e)
                self._text_to_events = TextToEvents
                dt = time.time() - t0
                self.stats["model_loaded"] = True
                logger.info("[TriBE] loaded in %.1fs on device=%s", dt, device)
                return True
            except Exception as e:
                self._load_error = f"{type(e).__name__}: {e}"
                self.stats["last_error"] = self._load_error
                logger.warning("[TriBE] load failed: %s", self._load_error)
                return False

    # ── Predict ──────────────────────────────────────────────────────

    @staticmethod
    def _build_word_events(
        text: str, words_per_sec: float = 2.5,
    ) -> "pd.DataFrame":
        """Build a TriBE-compatible Word-events DataFrame from raw text.

        Bypasses TTS + whisperx entirely. Synthetic per-word timestamps
        at the supplied reading pace. TriBE's encoder chunks on TR=1.5s
        anyway, so word-level timing precision below ~100ms doesn't
        matter much for the cortical aggregation.
        """
        import pandas as pd  # local import, kept lightweight

        # Tokenize naively on whitespace; strip punctuation off ends only
        raw_words = [w for w in text.split() if w.strip()]
        if not raw_words:
            return pd.DataFrame()

        dur = 1.0 / float(words_per_sec)
        # Sentence segmentation (cheap): split on . ! ? — preserve original
        # ordering for sequence_id.
        import re
        sentences = re.split(r"(?<=[\.!?])\s+", text.strip())
        # Map word_index → (sentence_index, sentence_text)
        sent_index_per_word: List[int] = []
        sent_text_per_word: List[str] = []
        word_cursor = 0
        for sent_idx, sent in enumerate(sentences):
            sent_words = sent.split()
            for _ in sent_words:
                sent_index_per_word.append(sent_idx)
                sent_text_per_word.append(sent[:500])
                word_cursor += 1
        # Pad if mismatch (whitespace edge cases)
        while len(sent_index_per_word) < len(raw_words):
            sent_index_per_word.append(0)
            sent_text_per_word.append(text[:500])

        rows = []
        for i, w in enumerate(raw_words):
            sent_text = sent_text_per_word[i]
            rows.append({
                "type": "Word",
                "text": w,
                "context": sent_text,    # neuralset's text-extractor reads this
                "start": float(i) * dur,
                "duration": dur,
                "sequence_id": int(sent_index_per_word[i]),
                "sentence": sent_text,
                "language": "en",        # TriBE supports en/fr/es/nl/zh — default en
                "timeline": "default",
                "subject": "default",
            })
        return pd.DataFrame(rows)

    def predict(self, text: str) -> Optional[np.ndarray]:
        """Direct-events predict (no TTS, no whisperx).

        Builds synthetic Word events from `text`, hands them straight to
        TriBE's model. Returns averaged fMRI vector across TRs (or None
        on failure).

        If TRIBE_DUMMY=1 (or the real model can't load), returns a
        deterministic hashed pseudo-vector so downstream wiring stays
        functional without gated weights.
        """
        if not text or len(text.strip()) < 3:
            return None
        if TRIBE_DUMMY or not self._ensure_loaded():
            return self._dummy_predict(text)
        t0 = time.time()
        try:
            with self._model_lock:
                events = self._build_word_events(text)
                if len(events) == 0:
                    return None
                preds, _segments = self._model.predict(events, verbose=False)
            if preds is None or len(preds) == 0:
                self.stats["failures"] += 1
                return None
            vec = np.asarray(preds, dtype=np.float32).mean(axis=0)
            dt_ms = (time.time() - t0) * 1000
            self.stats["predictions"] += 1
            self.stats["last_predict_ms"] = dt_ms
            return vec
        except Exception as e:
            self.stats["failures"] += 1
            self.stats["last_error"] = f"predict: {type(e).__name__}: {e}"
            import traceback as _tb
            logger.warning("[TriBE] predict failed:\n%s", _tb.format_exc())
            return None

    def predict_via_tts(self, text: str) -> Optional[np.ndarray]:
        """Legacy TTS+whisperx path. Kept for parity / debugging.

        Triggers gTTS → audio → whisperx → TriBE. Heavy + Windows-fragile.
        Use predict() (direct events) for normal Brain operation; this
        method exists for rare cases where TTS-realistic timing matters.
        """
        if not text or len(text.strip()) < 3:
            return None
        if not self._ensure_loaded():
            return None
        t0 = time.time()
        try:
            with self._model_lock:
                from tribev2 import eventstransforms as _et
                _et.ExtractWordsFromAudio._brain_current_text = text
                tts_folder = str(Path(TRIBE_CACHE_FOLDER) / "tts")
                Path(tts_folder).mkdir(parents=True, exist_ok=True)
                tte = self._text_to_events(
                    text=text,
                    infra={"folder": tts_folder, "mode": "retry"},
                )
                events = tte.get_events()
                preds, _segments = self._model.predict(events, verbose=False)
            if preds is None or len(preds) == 0:
                self.stats["failures"] += 1
                return None
            vec = np.asarray(preds, dtype=np.float32).mean(axis=0)
            dt_ms = (time.time() - t0) * 1000
            self.stats["predictions"] += 1
            self.stats["last_predict_ms"] = dt_ms
            return vec
        except Exception as e:
            self.stats["failures"] += 1
            self.stats["last_error"] = f"predict_via_tts: {type(e).__name__}: {e}"
            logger.debug("[TriBE] predict_via_tts failed: %s", self.stats["last_error"])
            return None

    # ── ROI aggregation ──────────────────────────────────────────────

    def _dummy_predict(self, text: str) -> np.ndarray:
        """Deterministic pseudo-fMRI vector from a text hash.

        Not biologically meaningful — just enough variance so bridge
        levels differ per input and downstream code paths execute."""
        import hashlib
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        vec = rng.normal(loc=0.0, scale=0.2, size=EXPECTED_VERTEX_COUNT).astype(np.float32)
        self.stats["predictions"] += 1
        self.stats["last_predict_ms"] = 0.1
        self.stats["last_mode"] = "dummy"
        return vec

    def aggregate_roi(
        self, vec: np.ndarray, ranges: Optional[Dict[str, slice]] = None
    ) -> Dict[str, float]:
        """Reduce a dense cortical vector to per-ROI mean activations."""
        if vec is None:
            return {}
        ranges = ranges or DEFAULT_ROI_RANGES
        result: Dict[str, float] = {}
        n = len(vec)
        for name, sl in ranges.items():
            start = min(sl.start or 0, n)
            stop = min(sl.stop or n, n)
            if stop <= start:
                result[name] = 0.0
                continue
            result[name] = float(vec[start:stop].mean())
        return result

    def bridge_levels(self, vec: np.ndarray) -> Dict[str, float]:
        """Map a cortical vector to Brain-bridge activation levels.

        Returns dict with keys like {"cortex", "limbic", "defense", ...}
        with scalar activation. Used by ROI-grounded bridge update path
        in brain_chat.py.
        """
        if vec is None:
            return {}
        rois = self.aggregate_roi(vec)
        out: Dict[str, float] = {}
        for bridge, weights in BRIDGE_ROI_MAP.items():
            total_w = sum(w for _, w in weights) or 1.0
            out[bridge] = sum(rois.get(roi, 0.0) * w for roi, w in weights) / total_w
        return out

    # ── Introspection ────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Snapshot for diagnostic endpoint."""
        return {
            "enabled": TRIBE_ENABLED,
            "checkpoint": TRIBE_CHECKPOINT,
            "device": TRIBE_DEVICE,
            "loaded": self._model is not None,
            "load_error": self._load_error,
            "stats": dict(self.stats),
        }


# ──────────────────────────────────────────────────────────────────────
# Module-level convenience
# ──────────────────────────────────────────────────────────────────────

def predict_text(text: str) -> Optional[np.ndarray]:
    """Shortcut for single calls. Uses the singleton."""
    return TribeEncoder.get().predict(text)


def bridge_levels_for_text(text: str) -> Dict[str, float]:
    """Shortcut: text -> per-bridge activation levels."""
    vec = predict_text(text)
    if vec is None:
        return {}
    return TribeEncoder.get().bridge_levels(vec)


def describe_profile(bridge_levels: Dict[str, float], top_k: int = 3) -> str:
    """Human-readable summary of a thought's neural bridge-profile.

    Turns the 8 raw bridge activations into a sentence like
    "high social + memory, low defense" — the interpretable face of TriBE.
    Returns "" when no profile is available.
    """
    if not bridge_levels:
        return ""
    items = sorted(bridge_levels.items(), key=lambda kv: kv[1], reverse=True)
    if not items:
        return ""
    high = [name for name, _ in items[:top_k]]
    low = items[-1][0] if len(items) > top_k else None
    txt = "high " + " + ".join(high)
    if low and low not in high:
        txt += f", low {low}"
    return txt

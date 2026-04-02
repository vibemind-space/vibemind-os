"""Vosk offline streaming STT using sounddevice."""

import json
import logging
import queue
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class VoskSTT:
    """Offline speech-to-text via Vosk + sounddevice streaming."""

    def __init__(self, model_path: str, sample_rate: int = 16000):
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError:
            raise ImportError(
                "vosk is not installed. Install with: pip install vosk\n"
                "Then download a model from https://alphacephei.com/vosk/models"
            )

        if not model_path:
            raise ValueError(
                "model_path is required. Set VOSK_MODEL_PATH or place a model "
                "in eyeterm/models/vosk-model-small-en-us"
            )

        self._sample_rate = sample_rate
        self._model = Model(model_path)
        self._recognizer = KaldiRecognizer(self._model, sample_rate)
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._on_partial: Optional[Callable[[str], None]] = None
        self._on_final: Optional[Callable[[str], None]] = None

    def start(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
    ) -> None:
        """Start streaming STT.

        Args:
            on_partial: Called with partial recognition results.
            on_final: Called with final recognition results.
        """
        try:
            import sounddevice as sd
        except ImportError:
            raise ImportError(
                "sounddevice is not installed. Install with: pip install sounddevice"
            )

        if self._running:
            logger.warning("VoskSTT already running, ignoring start()")
            return

        self._on_partial = on_partial
        self._on_final = on_final
        self._running = True

        # Clear any stale data
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        # Open mic stream: mono, 16-bit PCM
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=4000,  # ~250ms chunks at 16kHz
            callback=self._audio_callback,
        )
        self._stream.start()

        # Background processing thread
        self._thread = threading.Thread(
            target=self._process_loop, name="vosk-stt", daemon=True
        )
        self._thread.start()
        logger.info("VoskSTT started (sample_rate=%d)", self._sample_rate)

    def stop(self) -> None:
        """Stop streaming, flush final result, join thread."""
        if not self._running:
            return

        self._running = False

        # Stop audio stream
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("Error stopping audio stream: %s", e)
            self._stream = None

        # Signal processing thread to exit
        self._audio_queue.put(None)

        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        # Flush any remaining recognition
        try:
            final_json = self._recognizer.FinalResult()
            result = json.loads(final_json)
            text = result.get("text", "").strip()
            if text and self._on_final:
                self._on_final(text)
        except Exception as e:
            logger.debug("Error flushing final result: %s", e)

        logger.info("VoskSTT stopped")

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice callback: push raw bytes to queue."""
        if status:
            logger.debug("Audio status: %s", status)
        if self._running:
            self._audio_queue.put(bytes(indata))

    def _process_loop(self):
        """Background thread: drain queue, feed recognizer, emit callbacks."""
        while self._running:
            try:
                data = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if data is None:
                break

            try:
                if self._recognizer.AcceptWaveform(data):
                    # Final result for this utterance segment
                    result_json = self._recognizer.Result()
                    result = json.loads(result_json)
                    text = result.get("text", "").strip()
                    if text and self._on_final:
                        self._on_final(text)
                else:
                    # Partial result
                    partial_json = self._recognizer.PartialResult()
                    result = json.loads(partial_json)
                    text = result.get("partial", "").strip()
                    if text and self._on_partial:
                        self._on_partial(text)
            except Exception as e:
                logger.error("Vosk processing error: %s", e)

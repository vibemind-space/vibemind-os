"""Speech-to-Text Service for Voice-Controlled Desktop Automation.

Supports multiple backends:
- Vapi AI (recommended for production)
- OpenAI Whisper API
- Local Whisper model

Sources:
- https://docs.vapi.ai/
- https://github.com/VapiAI/server-sdk-python
"""

import os
import sys
import asyncio
import logging
import wave
import io
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))

logger = logging.getLogger(__name__)


class STTBackend(Enum):
    """Speech-to-text backend options."""
    VAPI = "vapi"
    OPENAI_WHISPER = "openai_whisper"
    GROQ_WHISPER = "groq_whisper"  # Free, fast Whisper via Groq
    LOCAL_WHISPER = "local_whisper"


@dataclass
class TranscriptionResult:
    """Result from speech transcription."""
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    duration_seconds: Optional[float] = None
    backend: Optional[str] = None


class SpeechToText:
    """Speech-to-Text service with multiple backend support."""

    def __init__(
        self,
        backend: STTBackend = None,  # Auto-detect based on available API keys
        language: str = "de",  # German default for user
        model: str = None  # Auto-selected based on backend
    ):
        """Initialize Speech-to-Text service.

        Args:
            backend: Which STT backend to use (auto-detects if None)
            language: Language code (e.g., 'de', 'en')
            model: Model name for the backend
        """
        self.language = language

        # API keys
        self.vapi_token = os.getenv("VAPI_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")

        # Auto-detect backend based on available API keys
        if backend is None:
            if self.groq_key:
                backend = STTBackend.GROQ_WHISPER
                logger.info("Using Groq Whisper backend (GROQ_API_KEY found)")
            elif self.openai_key:
                backend = STTBackend.OPENAI_WHISPER
                logger.info("Using OpenAI Whisper backend (OPENAI_API_KEY found)")
            elif self.vapi_token:
                backend = STTBackend.VAPI
                logger.info("Using Vapi backend (VAPI_API_KEY found)")
            else:
                backend = STTBackend.LOCAL_WHISPER
                logger.warning("No STT API key found, falling back to local Whisper")

        self.backend = backend

        # Set model based on backend
        if model is None:
            if self.backend == STTBackend.GROQ_WHISPER:
                self.model = "whisper-large-v3"
            else:
                self.model = "whisper-1"
        else:
            self.model = model

        # State
        self._is_listening = False
        self._audio_buffer: list = []

        # Initialize backend
        self._init_backend()

    def _init_backend(self):
        """Initialize the selected backend."""
        if self.backend == STTBackend.VAPI:
            if not self.vapi_token:
                logger.warning("VAPI_API_KEY not set, falling back to Groq Whisper")
                self.backend = STTBackend.GROQ_WHISPER
            else:
                try:
                    from vapi import Vapi
                    self.vapi_client = Vapi(token=self.vapi_token)
                    logger.info("Vapi client initialized")
                except ImportError:
                    logger.warning("vapi package not installed, falling back to Groq Whisper")
                    self.backend = STTBackend.GROQ_WHISPER

        if self.backend == STTBackend.GROQ_WHISPER:
            if not self.groq_key:
                logger.warning("GROQ_API_KEY not set, falling back to OpenAI Whisper")
                self.backend = STTBackend.OPENAI_WHISPER
            else:
                # Groq uses OpenAI-compatible API
                self.groq_url = "https://api.groq.com/openai/v1/audio/transcriptions"
                logger.info("Groq Whisper initialized (fast & free)")

        if self.backend == STTBackend.OPENAI_WHISPER:
            if not self.openai_key:
                logger.warning("OPENAI_API_KEY not set, falling back to local Whisper")
                self.backend = STTBackend.LOCAL_WHISPER
            else:
                try:
                    import openai
                    self.openai_client = openai.OpenAI(api_key=self.openai_key)
                    logger.info("OpenAI Whisper client initialized")
                except ImportError:
                    logger.warning("openai package not installed, falling back to local Whisper")
                    self.backend = STTBackend.LOCAL_WHISPER

        if self.backend == STTBackend.LOCAL_WHISPER:
            try:
                import whisper
                self.whisper_model = whisper.load_model("base")
                logger.info("Local Whisper model loaded")
            except ImportError:
                logger.error("whisper package not installed. Run: pip install openai-whisper")
                self.whisper_model = None

    async def transcribe_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        channels: int = 1
    ) -> TranscriptionResult:
        """Transcribe audio data to text.

        Args:
            audio_data: Raw audio bytes (PCM or WAV)
            sample_rate: Audio sample rate
            channels: Number of audio channels

        Returns:
            TranscriptionResult with transcribed text
        """
        if self.backend == STTBackend.GROQ_WHISPER:
            return await self._transcribe_groq(audio_data, sample_rate, channels)
        elif self.backend == STTBackend.OPENAI_WHISPER:
            return await self._transcribe_openai(audio_data, sample_rate, channels)
        elif self.backend == STTBackend.LOCAL_WHISPER:
            return await self._transcribe_local(audio_data, sample_rate, channels)
        elif self.backend == STTBackend.VAPI:
            # Vapi handles real-time transcription differently
            return await self._transcribe_openai(audio_data, sample_rate, channels)
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    async def _transcribe_openai(
        self,
        audio_data: bytes,
        sample_rate: int,
        channels: int
    ) -> TranscriptionResult:
        """Transcribe using OpenAI Whisper API."""
        # Convert raw audio to WAV format
        wav_buffer = self._create_wav(audio_data, sample_rate, channels)

        try:
            # Use async thread pool for sync API call
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.openai_client.audio.transcriptions.create(
                    model=self.model,
                    file=("audio.wav", wav_buffer, "audio/wav"),
                    language=self.language,
                    response_format="verbose_json"
                )
            )

            return TranscriptionResult(
                text=response.text,
                language=response.language,
                duration_seconds=response.duration,
                backend="openai_whisper"
            )
        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}")
            return TranscriptionResult(text="", backend="openai_whisper")

    async def _transcribe_groq(
        self,
        audio_data: bytes,
        sample_rate: int,
        channels: int
    ) -> TranscriptionResult:
        """Transcribe using Groq Whisper API (fast & free)."""
        wav_buffer = self._create_wav(audio_data, sample_rate, channels)

        try:
            import aiohttp

            # Groq uses multipart form data
            data = aiohttp.FormData()
            data.add_field('file', wav_buffer.read(), filename='audio.wav', content_type='audio/wav')
            data.add_field('model', self.model)
            data.add_field('language', self.language)
            data.add_field('response_format', 'json')

            headers = {
                "Authorization": f"Bearer {self.groq_key}"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.groq_url,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Groq transcription failed: {response.status} - {error_text}")
                        return TranscriptionResult(text="", backend="groq_whisper")

                    result = await response.json()
                    return TranscriptionResult(
                        text=result.get("text", ""),
                        language=self.language,
                        backend="groq_whisper"
                    )

        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return TranscriptionResult(text="", backend="groq_whisper")
        except Exception as e:
            logger.error(f"Groq transcription failed: {e}")
            return TranscriptionResult(text="", backend="groq_whisper")

    async def _transcribe_local(
        self,
        audio_data: bytes,
        sample_rate: int,
        channels: int
    ) -> TranscriptionResult:
        """Transcribe using local Whisper model."""
        if not self.whisper_model:
            return TranscriptionResult(text="", backend="local_whisper")

        import numpy as np
        import tempfile

        # Convert bytes to numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Save to temp file (Whisper requires file input)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            wav_buffer = self._create_wav(audio_data, sample_rate, channels)
            f.write(wav_buffer.read())

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.whisper_model.transcribe(
                    temp_path,
                    language=self.language,
                    fp16=False
                )
            )

            return TranscriptionResult(
                text=result["text"].strip(),
                language=result.get("language"),
                backend="local_whisper"
            )
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _create_wav(self, audio_data: bytes, sample_rate: int, channels: int) -> io.BytesIO:
        """Create WAV file from raw audio data."""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(audio_data)
        buffer.seek(0)
        return buffer

    async def transcribe_file(self, file_path: str) -> TranscriptionResult:
        """Transcribe audio from file.

        Args:
            file_path: Path to audio file (WAV, MP3, etc.)

        Returns:
            TranscriptionResult with transcribed text
        """
        if self.backend == STTBackend.OPENAI_WHISPER:
            try:
                with open(file_path, 'rb') as f:
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.openai_client.audio.transcriptions.create(
                            model=self.model,
                            file=f,
                            language=self.language,
                            response_format="verbose_json"
                        )
                    )

                    return TranscriptionResult(
                        text=response.text,
                        language=response.language,
                        duration_seconds=response.duration,
                        backend="openai_whisper"
                    )
            except Exception as e:
                logger.error(f"File transcription failed: {e}")
                return TranscriptionResult(text="", backend="openai_whisper")

        elif self.backend == STTBackend.LOCAL_WHISPER:
            if not self.whisper_model:
                return TranscriptionResult(text="", backend="local_whisper")

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.whisper_model.transcribe(
                    file_path,
                    language=self.language,
                    fp16=False
                )
            )

            return TranscriptionResult(
                text=result["text"].strip(),
                language=result.get("language"),
                backend="local_whisper"
            )

        return TranscriptionResult(text="", backend="unknown")


class RealtimeSpeechToText:
    """Real-time speech recognition with microphone input."""

    def __init__(
        self,
        stt: SpeechToText,
        on_transcription: Optional[Callable[[str], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        silence_threshold: float = 0.5,  # seconds
        min_speech_duration: float = 0.3  # seconds
    ):
        """Initialize real-time STT.

        Args:
            stt: SpeechToText instance for transcription
            on_transcription: Callback for final transcription
            on_partial: Callback for partial results
            silence_threshold: Seconds of silence before processing
            min_speech_duration: Minimum speech duration to process
        """
        self.stt = stt
        self.on_transcription = on_transcription
        self.on_partial = on_partial
        self.silence_threshold = silence_threshold
        self.min_speech_duration = min_speech_duration

        self._is_listening = False
        self._audio_buffer = []
        self._stream = None

        # Audio settings
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024

    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream."""
        if status:
            logger.warning(f"Audio status: {status}")
        if self._is_listening:
            self._audio_buffer.append(indata.copy())

    async def start_listening(self, wake_word: Optional[str] = None):
        """Start listening for speech.

        Args:
            wake_word: Optional wake word to listen for (e.g., "Hey Moire")
        """
        try:
            import sounddevice as sd
        except ImportError:
            logger.error("sounddevice not installed. Run: pip install sounddevice")
            return

        self._is_listening = True
        self._audio_buffer = []

        logger.info(f"Starting microphone listening (wake_word={wake_word})")

        # Start audio stream
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.chunk_size,
            callback=self._audio_callback
        )
        self._stream.start()

        # Process audio in background
        asyncio.create_task(self._process_audio_loop(wake_word))

    async def _process_audio_loop(self, wake_word: Optional[str] = None):
        """Process audio buffer and detect speech."""
        import numpy as np

        while self._is_listening:
            await asyncio.sleep(0.1)

            if len(self._audio_buffer) < 10:  # Wait for enough audio
                continue

            # Combine audio chunks
            audio_data = np.concatenate(self._audio_buffer)

            # Simple voice activity detection (energy-based)
            energy = np.sqrt(np.mean(audio_data ** 2))

            if energy > 0.01:  # Speech detected
                # Accumulate more audio
                continue
            else:
                # Silence detected - process if we have speech
                if len(self._audio_buffer) > int(self.min_speech_duration * self.sample_rate / self.chunk_size):
                    # Convert to bytes and transcribe
                    audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()

                    result = await self.stt.transcribe_audio(
                        audio_bytes,
                        sample_rate=self.sample_rate,
                        channels=self.channels
                    )

                    if result.text:
                        # Check for wake word if specified
                        if wake_word:
                            if wake_word.lower() in result.text.lower():
                                # Remove wake word and process command
                                command = result.text.lower().replace(wake_word.lower(), "").strip()
                                if self.on_transcription and command:
                                    self.on_transcription(command)
                        else:
                            if self.on_transcription:
                                self.on_transcription(result.text)

                # Clear buffer
                self._audio_buffer = []

    async def stop_listening(self):
        """Stop listening for speech."""
        self._is_listening = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Stopped microphone listening")

    @staticmethod
    def list_microphones() -> list:
        """List available microphone devices."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            microphones = []
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    microphones.append({
                        'index': i,
                        'name': dev['name'],
                        'channels': dev['max_input_channels'],
                        'sample_rate': dev['default_samplerate']
                    })
            return microphones
        except ImportError:
            return []


# Test/demo code
if __name__ == "__main__":
    async def main():
        print("=== Speech-to-Text Test ===\n")

        # List microphones
        mics = RealtimeSpeechToText.list_microphones()
        print("Available microphones:")
        for mic in mics:
            print(f"  [{mic['index']}] {mic['name']}")

        # Initialize STT
        stt = SpeechToText(backend=STTBackend.OPENAI_WHISPER, language="de")
        print(f"\nUsing backend: {stt.backend.value}")

        # Test with a file if available
        test_file = "test_audio.wav"
        if os.path.exists(test_file):
            print(f"\nTranscribing {test_file}...")
            result = await stt.transcribe_file(test_file)
            print(f"Result: {result.text}")
        else:
            print(f"\nNo test file found. Create {test_file} to test file transcription.")

        print("\nSpeech-to-Text service ready!")

    asyncio.run(main())

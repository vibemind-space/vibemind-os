"""Text-to-Speech Service for Voice Feedback.

Supports multiple TTS backends:
- pyttsx3 (offline, cross-platform)
- OpenAI TTS API
- Edge TTS (Microsoft, free)
"""

import os
import sys
import asyncio
import logging
import tempfile
from typing import Optional, Callable
from enum import Enum
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))

logger = logging.getLogger(__name__)


class TTSBackend(Enum):
    """Text-to-speech backend options."""
    PYTTSX3 = "pyttsx3"
    OPENAI = "openai"
    EDGE_TTS = "edge_tts"


@dataclass
class TTSConfig:
    """TTS configuration."""
    backend: TTSBackend = TTSBackend.PYTTSX3
    voice: Optional[str] = None  # Voice ID or name
    rate: int = 150  # Words per minute
    volume: float = 1.0  # 0.0 to 1.0
    language: str = "de"  # Language code


class TextToSpeech:
    """Text-to-Speech service with multiple backend support."""

    def __init__(self, config: Optional[TTSConfig] = None):
        """Initialize TTS service.

        Args:
            config: TTS configuration (uses defaults if None)
        """
        self.config = config or TTSConfig()
        self._engine = None
        self._is_speaking = False

        self._init_backend()

    def _init_backend(self):
        """Initialize the selected backend."""
        if self.config.backend == TTSBackend.PYTTSX3:
            try:
                import pyttsx3
                self._engine = pyttsx3.init()

                # Configure voice
                self._engine.setProperty('rate', self.config.rate)
                self._engine.setProperty('volume', self.config.volume)

                # Try to find German voice
                voices = self._engine.getProperty('voices')
                for voice in voices:
                    if self.config.language in voice.languages or 'german' in voice.name.lower():
                        self._engine.setProperty('voice', voice.id)
                        break

                logger.info("pyttsx3 TTS initialized")
            except ImportError:
                logger.warning("pyttsx3 not installed. Run: pip install pyttsx3")
                self._engine = None

        elif self.config.backend == TTSBackend.OPENAI:
            self.openai_key = os.getenv("OPENAI_API_KEY")
            if not self.openai_key:
                logger.warning("OPENAI_API_KEY not set")
            else:
                try:
                    import openai
                    self._openai_client = openai.OpenAI(api_key=self.openai_key)
                    logger.info("OpenAI TTS initialized")
                except ImportError:
                    logger.warning("openai package not installed")

        elif self.config.backend == TTSBackend.EDGE_TTS:
            try:
                import edge_tts
                logger.info("Edge TTS initialized")
            except ImportError:
                logger.warning("edge-tts not installed. Run: pip install edge-tts")

    def speak(self, text: str):
        """Speak text synchronously.

        Args:
            text: Text to speak
        """
        if self._is_speaking:
            logger.warning("Already speaking, ignoring new request")
            return

        self._is_speaking = True
        try:
            if self.config.backend == TTSBackend.PYTTSX3:
                self._speak_pyttsx3(text)
            elif self.config.backend == TTSBackend.OPENAI:
                asyncio.run(self._speak_openai(text))
            elif self.config.backend == TTSBackend.EDGE_TTS:
                asyncio.run(self._speak_edge_tts(text))
        finally:
            self._is_speaking = False

    async def speak_async(self, text: str):
        """Speak text asynchronously.

        Args:
            text: Text to speak
        """
        if self._is_speaking:
            logger.warning("Already speaking, ignoring new request")
            return

        self._is_speaking = True
        try:
            if self.config.backend == TTSBackend.PYTTSX3:
                # Run pyttsx3 in thread pool (it's blocking)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: self._speak_pyttsx3(text))
            elif self.config.backend == TTSBackend.OPENAI:
                await self._speak_openai(text)
            elif self.config.backend == TTSBackend.EDGE_TTS:
                await self._speak_edge_tts(text)
        finally:
            self._is_speaking = False

    def _speak_pyttsx3(self, text: str):
        """Speak using pyttsx3."""
        if not self._engine:
            logger.warning("pyttsx3 not available")
            return

        logger.info(f"Speaking: {text[:50]}...")
        self._engine.say(text)
        self._engine.runAndWait()

    async def _speak_openai(self, text: str):
        """Speak using OpenAI TTS API."""
        if not hasattr(self, '_openai_client'):
            logger.warning("OpenAI client not available")
            return

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._openai_client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",  # Options: alloy, echo, fable, onyx, nova, shimmer
                    input=text
                )
            )

            # Save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(response.content)
                temp_path = f.name

            await self._play_audio(temp_path)

            # Clean up
            os.unlink(temp_path)

        except Exception as e:
            logger.error(f"OpenAI TTS failed: {e}")

    async def _speak_edge_tts(self, text: str):
        """Speak using Microsoft Edge TTS (free)."""
        try:
            import edge_tts

            # German voice
            voice = "de-DE-ConradNeural"  # or "de-DE-KatjaNeural" for female

            communicate = edge_tts.Communicate(text, voice)

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name

            await communicate.save(temp_path)
            await self._play_audio(temp_path)

            # Clean up
            os.unlink(temp_path)

        except ImportError:
            logger.error("edge-tts not installed")
        except Exception as e:
            logger.error(f"Edge TTS failed: {e}")

    async def _play_audio(self, file_path: str):
        """Play audio file."""
        try:
            # Try playsound (simple cross-platform)
            from playsound import playsound
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: playsound(file_path))
            return
        except ImportError:
            pass

        try:
            # Try pygame
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
            return
        except ImportError:
            pass

        # Fallback: system command
        import subprocess
        import platform

        system = platform.system()
        if system == "Windows":
            subprocess.run(["start", file_path], shell=True)
        elif system == "Darwin":  # macOS
            subprocess.run(["afplay", file_path])
        else:  # Linux
            subprocess.run(["aplay", file_path])

        # Wait for playback (estimate)
        await asyncio.sleep(2)

    def list_voices(self) -> list:
        """List available voices for current backend."""
        if self.config.backend == TTSBackend.PYTTSX3 and self._engine:
            voices = self._engine.getProperty('voices')
            return [
                {
                    'id': v.id,
                    'name': v.name,
                    'languages': v.languages,
                    'gender': v.gender
                }
                for v in voices
            ]

        elif self.config.backend == TTSBackend.EDGE_TTS:
            # Edge TTS voices can be listed with edge_tts.list_voices()
            try:
                import edge_tts
                voices = asyncio.run(edge_tts.list_voices())
                return [
                    {
                        'id': v['ShortName'],
                        'name': v['FriendlyName'],
                        'language': v['Locale'],
                        'gender': v['Gender']
                    }
                    for v in voices
                    if v['Locale'].startswith('de')  # German voices only
                ]
            except ImportError:
                return []

        elif self.config.backend == TTSBackend.OPENAI:
            # OpenAI voices are fixed
            return [
                {'id': 'alloy', 'name': 'Alloy', 'description': 'Neutral'},
                {'id': 'echo', 'name': 'Echo', 'description': 'Male'},
                {'id': 'fable', 'name': 'Fable', 'description': 'British'},
                {'id': 'onyx', 'name': 'Onyx', 'description': 'Deep male'},
                {'id': 'nova', 'name': 'Nova', 'description': 'Female'},
                {'id': 'shimmer', 'name': 'Shimmer', 'description': 'Female'},
            ]

        return []

    def stop(self):
        """Stop current speech."""
        self._is_speaking = False
        if self.config.backend == TTSBackend.PYTTSX3 and self._engine:
            self._engine.stop()


class VoiceFeedback:
    """Convenience class for voice feedback in automation."""

    # Pre-defined feedback messages (German)
    MESSAGES = {
        'listening': "Ich höre zu...",
        'thinking': "Moment, ich denke nach...",
        'executing': "Wird ausgeführt...",
        'done': "Fertig!",
        'error': "Da ist ein Fehler aufgetreten.",
        'not_understood': "Das habe ich nicht verstanden.",
        'ready': "Bereit für den nächsten Befehl.",
    }

    def __init__(self, tts: Optional[TextToSpeech] = None):
        """Initialize voice feedback.

        Args:
            tts: TextToSpeech instance (creates default if None)
        """
        self.tts = tts or TextToSpeech()

    async def say(self, key_or_text: str):
        """Say a feedback message.

        Args:
            key_or_text: Message key (from MESSAGES) or custom text
        """
        message = self.MESSAGES.get(key_or_text, key_or_text)
        await self.tts.speak_async(message)

    def say_sync(self, key_or_text: str):
        """Say a feedback message synchronously.

        Args:
            key_or_text: Message key or custom text
        """
        message = self.MESSAGES.get(key_or_text, key_or_text)
        self.tts.speak(message)


# Test/demo code
if __name__ == "__main__":
    async def main():
        print("=== Text-to-Speech Test ===\n")

        # Try different backends
        backends = [TTSBackend.PYTTSX3, TTSBackend.EDGE_TTS]

        for backend in backends:
            print(f"\nTesting {backend.value}...")

            tts = TextToSpeech(TTSConfig(backend=backend, language="de"))

            # List voices
            voices = tts.list_voices()
            if voices:
                print(f"  Available voices: {len(voices)}")
                for v in voices[:3]:
                    print(f"    - {v.get('name', v.get('id'))}")

            # Test speaking
            try:
                await tts.speak_async("Hallo, ich bin dein Desktop-Assistent.")
                print("  Speaking: OK")
            except Exception as e:
                print(f"  Speaking: FAILED - {e}")

        print("\n=== Voice Feedback Test ===")
        feedback = VoiceFeedback()
        await feedback.say('ready')

    asyncio.run(main())

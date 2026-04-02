"""Voice-Controlled Desktop Automation - Main Entry Point.

This script provides a command-line interface for voice-controlled
desktop automation.

Usage:
    python main.py --mode interactive    # Interactive text mode
    python main.py --mode listen         # Real-time voice listening
    python main.py --mode command "..."  # Single command execution

Examples:
    python main.py --mode command "Öffne Anthropic Careers"
    python main.py --mode listen --wake-word "Hey Moire"
    python main.py --mode interactive
"""

import os
import sys
import asyncio
import argparse
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_interactive_mode():
    """Run interactive text command mode."""
    from speech_to_text import SpeechToText, STTBackend
    from intent_parser import QuickIntentParser, IntentParser
    from command_executor import CommandExecutor
    from text_to_speech import TextToSpeech, TTSConfig, TTSBackend, VoiceFeedback

    print("\n" + "="*60)
    print("   Voice-Controlled Desktop Automation")
    print("   Interactive Mode")
    print("="*60)
    print("\nGib Befehle ein (z.B. 'Öffne Google', 'Scrolle nach unten')")
    print("Tippe 'quit' oder 'exit' zum Beenden.\n")

    # Initialize components
    parser = QuickIntentParser(fallback_parser=IntentParser())
    executor = CommandExecutor()

    # Try to initialize TTS
    tts = None
    try:
        tts = TextToSpeech(TTSConfig(backend=TTSBackend.PYTTSX3))
        feedback = VoiceFeedback(tts)
        print("[TTS] Sprachausgabe aktiviert\n")
    except Exception as e:
        print(f"[TTS] Nicht verfügbar: {e}\n")

    while True:
        try:
            # Get user input
            command = input(">>> ").strip()

            if not command:
                continue

            if command.lower() in ['quit', 'exit', 'beenden', 'q']:
                print("\nAuf Wiedersehen!")
                break

            # Parse intent
            print(f"\n[Parsing] {command}...")
            intent = await parser.parse(command)

            if intent.error:
                print(f"[Error] {intent.error}")
                continue

            if not intent.actions:
                print("[Info] Keine Aktionen erkannt")
                continue

            # Show parsed actions
            print(f"[Context] {intent.context}")
            print(f"[Actions] {len(intent.actions)} Aktionen:")
            for i, action in enumerate(intent.actions, 1):
                print(f"  {i}. {action.type.value}: {action.description}")

            # Execute
            print("\n[Executing]...")
            report = await executor.execute(intent)

            # Show results
            print(f"\n[Result] {'Erfolgreich' if report.success else 'Fehlgeschlagen'}")
            print(f"[Feedback] {report.feedback_message}")
            print(f"[Duration] {report.total_duration_ms:.0f}ms\n")

            # Voice feedback
            if tts and report.feedback_message:
                try:
                    await tts.speak_async(report.feedback_message)
                except Exception as e:
                    logger.debug(f"TTS error: {e}")

        except KeyboardInterrupt:
            print("\n\nUnterbrochen. Auf Wiedersehen!")
            break
        except Exception as e:
            print(f"\n[Error] {e}\n")


async def run_listen_mode(wake_word: str = None, voice_feedback: bool = True):
    """Run real-time voice listening mode."""
    from speech_to_text import SpeechToText, STTBackend, RealtimeSpeechToText
    from intent_parser import QuickIntentParser, IntentParser
    from command_executor import CommandExecutor
    from text_to_speech import TextToSpeech, TTSConfig, TTSBackend

    print("\n" + "="*60)
    print("   Voice-Controlled Desktop Automation")
    print("   Listening Mode")
    print("="*60)

    if wake_word:
        print(f"\nWake Word: '{wake_word}'")
        print("Sage das Wake Word gefolgt von deinem Befehl.")
    else:
        print("\nKein Wake Word - alle Sprache wird verarbeitet.")

    print("\nDrücke Ctrl+C zum Beenden.\n")

    # Initialize components
    stt = SpeechToText(backend=STTBackend.OPENAI_WHISPER, language="de")
    parser = QuickIntentParser(fallback_parser=IntentParser())
    executor = CommandExecutor()

    tts = None
    if voice_feedback:
        try:
            tts = TextToSpeech(TTSConfig(backend=TTSBackend.PYTTSX3))
            await tts.speak_async("Ich höre zu.")
        except Exception as e:
            logger.warning(f"TTS not available: {e}")

    async def on_transcription(text: str):
        """Handle transcribed text."""
        print(f"\n[Transcribed] {text}")

        # Parse and execute
        intent = await parser.parse(text)
        if intent.actions:
            print(f"[Executing] {intent.context}")
            report = await executor.execute(intent)
            print(f"[Result] {report.feedback_message}")

            if tts:
                await tts.speak_async(report.feedback_message)

    # Create realtime STT
    realtime = RealtimeSpeechToText(
        stt=stt,
        on_transcription=lambda t: asyncio.create_task(on_transcription(t))
    )

    try:
        await realtime.start_listening(wake_word=wake_word)

        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n\nStopping...")
        await realtime.stop_listening()
        print("Auf Wiedersehen!")


async def run_single_command(command: str, voice_feedback: bool = False):
    """Execute a single command."""
    from intent_parser import QuickIntentParser, IntentParser
    from command_executor import CommandExecutor
    from text_to_speech import TextToSpeech, TTSConfig, TTSBackend

    print(f"\n[Command] {command}")

    parser = QuickIntentParser(fallback_parser=IntentParser())
    executor = CommandExecutor()

    # Parse
    intent = await parser.parse(command)

    if intent.error:
        print(f"[Error] {intent.error}")
        return

    print(f"[Context] {intent.context}")
    print(f"[Actions] {len(intent.actions)}")

    # Execute
    report = await executor.execute(intent)

    print(f"[Result] {'Success' if report.success else 'Failed'}")
    print(f"[Feedback] {report.feedback_message}")
    print(f"[Duration] {report.total_duration_ms:.0f}ms")

    # Voice feedback
    if voice_feedback:
        try:
            tts = TextToSpeech(TTSConfig(backend=TTSBackend.PYTTSX3))
            tts.speak(report.feedback_message)
        except Exception as e:
            logger.debug(f"TTS error: {e}")


def main():
    """Main entry point."""
    argparser = argparse.ArgumentParser(
        description="Voice-Controlled Desktop Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode interactive
  python main.py --mode listen --wake-word "Hey Moire"
  python main.py --mode command "Öffne Google"
  python main.py --mode command "Scrolle nach unten" --voice-feedback
        """
    )

    argparser.add_argument(
        '--mode', '-m',
        choices=['interactive', 'listen', 'command'],
        default='interactive',
        help='Operation mode (default: interactive)'
    )

    argparser.add_argument(
        '--command', '-c',
        type=str,
        help='Command to execute (for command mode)'
    )

    argparser.add_argument(
        '--wake-word', '-w',
        type=str,
        default=None,
        help='Wake word for listening mode (e.g., "Hey Moire")'
    )

    argparser.add_argument(
        '--voice-feedback', '-v',
        action='store_true',
        help='Enable voice feedback'
    )

    argparser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = argparser.parse_args()

    # Set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle command mode
    if args.mode == 'command':
        if args.command:
            command = args.command
        else:
            print("Error: --mode command requires --command 'Your command'")
            print("Usage: python main.py --mode command --command \"Öffne Google\"")
            sys.exit(1)

        asyncio.run(run_single_command(command, args.voice_feedback))

    elif args.mode == 'listen':
        asyncio.run(run_listen_mode(args.wake_word, args.voice_feedback))

    else:  # interactive
        asyncio.run(run_interactive_mode())


if __name__ == "__main__":
    main()

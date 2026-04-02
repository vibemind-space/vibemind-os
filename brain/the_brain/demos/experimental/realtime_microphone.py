"""
Real-time microphone demo for ATM-R.

Captures audio from microphone, extracts features, and routes through ATM-R.
Displays gate dynamics and audio feature visualization.

Usage:
    python demos/realtime_microphone.py --adaptive --show-spectrogram

Requirements:
    - sounddevice
    - numpy
    - scipy
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import sounddevice as sd
import argparse
import time
from collections import deque
from scipy import signal as scipy_signal
from scipy.fft import fft

from thalamo_pc_adaptive import ThalamoPC6Adaptive
from config_loader import load_config, create_model_from_config

try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Install for visualization.")


class MicrophoneATMR:
    """Real-time ATM-R with microphone input."""

    def __init__(
        self,
        config_path='configs/default.yaml',
        adaptive=True,
        sample_rate=44100,
        frame_size=2048
    ):
        """
        Initialize microphone ATM-R.

        Args:
            config_path: Path to config
            adaptive: Use adaptive model
            sample_rate: Audio sample rate (Hz)
            frame_size: Frame size for FFT
        """
        self.config = load_config(config_path)
        self.config['dimensions']['audio'] = 64
        self.atmr = create_model_from_config(self.config, adaptive=adaptive)
        self.adaptive = adaptive

        self.sample_rate = sample_rate
        self.frame_size = frame_size

        # Audio buffer
        self.audio_buffer = deque(maxlen=frame_size * 4)

        # Gate history
        self.gate_history = deque(maxlen=100)

        # Feature history for visualization
        self.feature_history = deque(maxlen=50)

    def extract_audio_features(self, audio_chunk):
        """
        Extract audio features (mel spectrogram, MFCCs, etc.).

        Args:
            audio_chunk: 1-D audio samples

        Returns:
            features: 64-dim feature vector
        """
        # Compute FFT
        fft_out = fft(audio_chunk)
        fft_mag = np.abs(fft_out[:len(fft_out)//2])

        # Compute mel-scale filterbank
        n_mels = 64
        fft_freqs = np.fft.rfftfreq(len(audio_chunk), 1.0/self.sample_rate)

        # Simple mel filterbank (log-spaced frequencies)
        mel_filters = np.zeros((n_mels, len(fft_mag)))
        mel_min = 0
        mel_max = 2595 * np.log10(1 + (self.sample_rate / 2) / 700)
        mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_points = 700 * (10**(mel_points / 2595) - 1)
        bin_points = np.floor((len(audio_chunk) + 1) * hz_points / self.sample_rate).astype(int)

        for i in range(1, n_mels + 1):
            left = bin_points[i - 1]
            center = bin_points[i]
            right = bin_points[i + 1]

            for j in range(left, center):
                if center != left:
                    mel_filters[i - 1, j] = (j - left) / (center - left)
            for j in range(center, right):
                if right != center:
                    mel_filters[i - 1, j] = (right - j) / (right - center)

        # Apply filters
        mel_spec = mel_filters @ fft_mag

        # Log scale
        mel_spec = np.log(mel_spec + 1e-10)

        # Normalize
        mel_spec = (mel_spec - np.mean(mel_spec)) / (np.std(mel_spec) + 1e-6)

        return mel_spec[:64]

    def step(self, audio_chunk, ctx=None, hazard=None):
        """
        Process one audio chunk through ATM-R.

        Args:
            audio_chunk: Audio samples
            ctx: Context vector
            hazard: Hazard signals

        Returns:
            out: ATM-R output dict
        """
        # Extract audio features
        audio_feats = self.extract_audio_features(audio_chunk)

        # Store for visualization
        self.feature_history.append(audio_feats)

        # Prepare multimodal input (only audio active)
        x_t = {
            'vision': np.zeros(self.atmr.d['vision']),
            'audio': audio_feats,
            'touch': np.zeros(self.atmr.d['touch']),
            'taste': np.zeros(self.atmr.d['taste']),
            'vestibular': np.zeros(self.atmr.d['vestibular']),
            'threat': np.zeros(self.atmr.d['threat'])
        }

        # Default context: prefer audio
        if ctx is None:
            ctx = np.zeros(self.atmr.M)
            ctx[self.atmr.modalities.index('audio')] = 1.0

        # Step
        if self.adaptive:
            out = self.atmr.step(x_t, ctx=ctx, hazard=hazard, adapt=True)
        else:
            out = self.atmr.step(x_t, ctx=ctx)

        # Store gate history
        self.gate_history.append(out['g'])

        return out

    def audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice audio stream."""
        if status:
            print(f"Audio status: {status}")

        # Add to buffer
        self.audio_buffer.extend(indata[:, 0])  # mono

    def start_stream(self):
        """Start audio stream."""
        self.stream = sd.InputStream(
            channels=1,
            samplerate=self.sample_rate,
            callback=self.audio_callback,
            blocksize=512
        )
        self.stream.start()
        print(f"Audio stream started (sample rate: {self.sample_rate} Hz)")

    def stop_stream(self):
        """Stop audio stream."""
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
            print("Audio stream stopped")


def run_terminal_mode(mic_atmr, duration=60):
    """Run in terminal mode (no GUI)."""
    print("\n" + "=" * 60)
    print("Running in terminal mode (no visualization)")
    print(f"Recording for {duration} seconds...")
    print("Press Ctrl+C to stop early")
    print("=" * 60)

    mic_atmr.start_stream()

    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            # Wait for buffer to fill
            if len(mic_atmr.audio_buffer) >= mic_atmr.frame_size:
                # Get audio chunk
                chunk = np.array(list(mic_atmr.audio_buffer)[-mic_atmr.frame_size:])

                # Process
                out = mic_atmr.step(chunk)

                # Print gates
                gates_str = " | ".join([f"{m[:3]}: {g:.2f}" for m, g in zip(mic_atmr.atmr.modalities, out['g'])])
                print(f"\r{gates_str}", end='', flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        mic_atmr.stop_stream()


def run_visual_mode(mic_atmr):
    """Run with matplotlib visualization."""
    if not MATPLOTLIB_AVAILABLE:
        print("ERROR: matplotlib required for visual mode")
        return

    print("\n" + "=" * 60)
    print("Running with visualization")
    print("Close window to stop")
    print("=" * 60)

    mic_atmr.start_stream()

    # Set up figure
    fig, (ax_gates, ax_spec) = plt.subplots(2, 1, figsize=(10, 8))
    fig.suptitle('ATM-R Real-Time Microphone', fontsize=14, fontweight='bold')

    # Initialize plots
    modalities = mic_atmr.atmr.modalities
    bar_colors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6', '#34495e']
    bars = ax_gates.bar(modalities, np.zeros(len(modalities)), color=bar_colors)
    ax_gates.set_ylabel('Gate Weight')
    ax_gates.set_ylim([0, 1])
    ax_gates.set_title('ATM-R Gates')
    ax_gates.grid(alpha=0.3)

    # Spectrogram
    im = ax_spec.imshow(
        np.zeros((64, 50)),
        aspect='auto',
        origin='lower',
        cmap='viridis'
    )
    ax_spec.set_title('Audio Features (Mel Spectrogram)')
    ax_spec.set_ylabel('Mel Frequency Bins')
    ax_spec.set_xlabel('Time')
    plt.colorbar(im, ax=ax_spec)

    def update_plot(frame):
        """Update plot animation."""
        # Wait for buffer
        if len(mic_atmr.audio_buffer) >= mic_atmr.frame_size:
            chunk = np.array(list(mic_atmr.audio_buffer)[-mic_atmr.frame_size:])
            out = mic_atmr.step(chunk)

            # Update gate bars
            for bar, g in zip(bars, out['g']):
                bar.set_height(g)

            # Update spectrogram
            if len(mic_atmr.feature_history) > 0:
                spec_data = np.array(list(mic_atmr.feature_history)).T
                im.set_data(spec_data)
                im.set_clim(vmin=spec_data.min(), vmax=spec_data.max())

        return bars, im

    ani = animation.FuncAnimation(
        fig, update_plot,
        interval=100,  # 100ms = 10 FPS
        blit=False
    )

    plt.tight_layout()
    plt.show()

    mic_atmr.stop_stream()


def main():
    parser = argparse.ArgumentParser(description='Real-time microphone ATM-R demo')
    parser.add_argument('--config', type=str, default='configs/default.yaml', help='Config file')
    parser.add_argument('--adaptive', action='store_true', help='Use adaptive model')
    parser.add_argument('--visual', action='store_true', help='Enable visualization (requires matplotlib)')
    parser.add_argument('--duration', type=int, default=60, help='Duration in seconds (terminal mode)')
    parser.add_argument('--sample-rate', type=int, default=44100, help='Audio sample rate')
    parser.add_argument('--list-devices', action='store_true', help='List audio devices and exit')

    args = parser.parse_args()

    if args.list_devices:
        print("\nAvailable audio devices:")
        print(sd.query_devices())
        return

    print("=" * 60)
    print("ATM-R Real-Time Microphone Demo")
    print("=" * 60)
    print(f"Using {'adaptive' if args.adaptive else 'standard'} model")
    print(f"Sample rate: {args.sample_rate} Hz")

    # Initialize
    print("\nInitializing ATM-R...")
    mic_atmr = MicrophoneATMR(
        config_path=args.config,
        adaptive=args.adaptive,
        sample_rate=args.sample_rate
    )

    # Run
    if args.visual:
        run_visual_mode(mic_atmr)
    else:
        run_terminal_mode(mic_atmr, duration=args.duration)

    print("\nDemo complete!")


if __name__ == "__main__":
    main()

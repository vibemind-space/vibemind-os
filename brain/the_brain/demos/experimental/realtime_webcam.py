"""
Real-time webcam demo for ATM-R.

Captures webcam video, extracts features, and routes through ATM-R in real-time.
Displays gate dynamics and attention visualization.

Usage:
    python demos/realtime_webcam.py --adaptive --show-gates

Requirements:
    - opencv-python
    - torch (for feature extraction)
    - webcam
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import cv2
import numpy as np
import argparse
import time
from collections import deque

import torch
import torchvision.transforms as transforms
from torchvision.models import mobilenet_v2

from thalamo_pc_adaptive import ThalamoPC6Adaptive
from config_loader import load_config, create_model_from_config


class WebcamATMR:
    """Real-time ATM-R with webcam input."""

    def __init__(self, config_path='configs/default.yaml', adaptive=True):
        """
        Initialize webcam ATM-R.

        Args:
            config_path: Path to config
            adaptive: Use adaptive model
        """
        self.config = load_config(config_path)
        self.config['dimensions']['vision'] = 128  # project features to this
        self.atmr = create_model_from_config(self.config, adaptive=adaptive)
        self.adaptive = adaptive

        # Feature extractor (MobileNetV2 for speed)
        self.feature_extractor = mobilenet_v2(pretrained=True)
        self.feature_extractor.eval()
        self.feature_extractor = torch.nn.Sequential(
            *list(self.feature_extractor.children())[:-1]  # remove classifier
        )

        # Projection: 1280 (MobileNetV2) → 128
        self.proj = torch.nn.Linear(1280, 128)

        # Image preprocessing
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        # Gate history for visualization
        self.gate_history = deque(maxlen=100)

        # FPS counter
        self.frame_times = deque(maxlen=30)

    def extract_features(self, frame):
        """
        Extract CNN features from frame.

        Args:
            frame: OpenCV BGR image

        Returns:
            features: 128-dim feature vector
        """
        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Preprocess
        img_tensor = self.transform(rgb).unsqueeze(0)

        # Extract features
        with torch.no_grad():
            features = self.feature_extractor(img_tensor)
            features = features.squeeze()
            features = self.proj(features).numpy()

        return features

    def step(self, frame, ctx=None, hazard=None):
        """
        Process one frame through ATM-R.

        Args:
            frame: OpenCV image
            ctx: Context vector
            hazard: Hazard signals

        Returns:
            out: ATM-R output dict
        """
        # Extract vision features
        vis_feats = self.extract_features(frame)

        # Prepare multimodal input (only vision active for webcam demo)
        x_t = {
            'vision': vis_feats,
            'audio': np.zeros(self.atmr.d['audio']),
            'touch': np.zeros(self.atmr.d['touch']),
            'taste': np.zeros(self.atmr.d['taste']),
            'vestibular': np.zeros(self.atmr.d['vestibular']),
            'threat': np.zeros(self.atmr.d['threat'])
        }

        # Default context: prefer vision
        if ctx is None:
            ctx = np.zeros(self.atmr.M)
            ctx[self.atmr.modalities.index('vision')] = 1.0

        # Step
        if self.adaptive:
            out = self.atmr.step(x_t, ctx=ctx, hazard=hazard, adapt=True)
        else:
            out = self.atmr.step(x_t, ctx=ctx)

        # Store gate history
        self.gate_history.append(out['g'])

        return out

    def visualize(self, frame, out, show_gates=True):
        """
        Visualize ATM-R state on frame.

        Args:
            frame: OpenCV image
            out: ATM-R output
            show_gates: Display gate bars

        Returns:
            vis_frame: Annotated frame
        """
        vis = frame.copy()
        h, w = vis.shape[:2]

        # Display FPS
        if len(self.frame_times) > 1:
            fps = 1.0 / np.mean(self.frame_times)
            cv2.putText(vis, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        if show_gates:
            # Display gate bars
            gates = out['g']
            bar_h = 20
            bar_w = 150
            start_y = 60

            for i, (mod, g_val) in enumerate(zip(self.atmr.modalities, gates)):
                y = start_y + i * (bar_h + 10)

                # Background bar
                cv2.rectangle(vis, (10, y), (10 + bar_w, y + bar_h), (50, 50, 50), -1)

                # Filled bar (gate value)
                fill_w = int(bar_w * g_val)
                color = self._get_color_for_modality(mod)
                cv2.rectangle(vis, (10, y), (10 + fill_w, y + bar_h), color, -1)

                # Label
                cv2.putText(vis, f"{mod}: {g_val:.2f}", (bar_w + 20, y + 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Gate history plot (mini timeline)
            if len(self.gate_history) > 1:
                plot_h = 80
                plot_w = 200
                plot_x = w - plot_w - 10
                plot_y = h - plot_h - 10

                # Background
                cv2.rectangle(vis, (plot_x, plot_y), (plot_x + plot_w, plot_y + plot_h),
                              (30, 30, 30), -1)

                # Plot each modality
                history_array = np.array(self.gate_history)
                for i, mod in enumerate(self.atmr.modalities):
                    if i < len(self.atmr.modalities) - 1:  # skip threat for clarity
                        values = history_array[:, i]
                        color = self._get_color_for_modality(mod)

                        for j in range(1, len(values)):
                            x1 = plot_x + int((j - 1) / len(values) * plot_w)
                            y1 = plot_y + plot_h - int(values[j - 1] * plot_h)
                            x2 = plot_x + int(j / len(values) * plot_w)
                            y2 = plot_y + plot_h - int(values[j] * plot_h)
                            cv2.line(vis, (x1, y1), (x2, y2), color, 1)

        return vis

    def _get_color_for_modality(self, modality):
        """Get BGR color for modality."""
        colors = {
            'vision': (255, 100, 100),    # blue
            'audio': (100, 255, 100),     # green
            'touch': (100, 100, 255),     # red
            'taste': (255, 255, 100),     # cyan
            'vestibular': (255, 100, 255), # magenta
            'threat': (50, 50, 255)       # dark red
        }
        return colors.get(modality, (200, 200, 200))


def main():
    parser = argparse.ArgumentParser(description='Real-time webcam ATM-R demo')
    parser.add_argument('--config', type=str, default='configs/default.yaml', help='Config file')
    parser.add_argument('--adaptive', action='store_true', help='Use adaptive model')
    parser.add_argument('--show-gates', action='store_true', default=True, help='Show gate visualization')
    parser.add_argument('--camera', type=int, default=0, help='Camera ID')
    parser.add_argument('--width', type=int, default=640, help='Frame width')
    parser.add_argument('--height', type=int, default=480, help='Frame height')

    args = parser.parse_args()

    print("=" * 60)
    print("ATM-R Real-Time Webcam Demo")
    print("=" * 60)
    print(f"Using {'adaptive' if args.adaptive else 'standard'} model")
    print("\nControls:")
    print("  q - Quit")
    print("  t - Trigger threat (increases threat priority)")
    print("  r - Reset state")
    print("=" * 60)

    # Initialize
    print("\nInitializing ATM-R...")
    webcam_atmr = WebcamATMR(config_path=args.config, adaptive=args.adaptive)

    # Open camera
    print(f"Opening camera {args.camera}...")
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not cap.isOpened():
        print("ERROR: Could not open camera!")
        return

    print("Camera opened successfully!")
    print("\nStarting real-time processing...")

    threat_active = False
    frame_count = 0

    try:
        while True:
            t_start = time.time()

            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break

            # Hazard signal (triggered by 't' key)
            hazard = {'threat': 1.0} if threat_active else None

            # Process frame
            out = webcam_atmr.step(frame, hazard=hazard)

            # Visualize
            vis_frame = webcam_atmr.visualize(frame, out, show_gates=args.show_gates)

            # Display
            cv2.imshow('ATM-R Webcam Demo', vis_frame)

            # Update FPS
            frame_time = time.time() - t_start
            webcam_atmr.frame_times.append(frame_time)

            # Handle keys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\nQuitting...")
                break
            elif key == ord('t'):
                threat_active = not threat_active
                print(f"Threat: {'ACTIVE' if threat_active else 'INACTIVE'}")
            elif key == ord('r'):
                webcam_atmr.atmr.reset_state()
                print("State reset")

            frame_count += 1

            # Reset threat after 30 frames
            if threat_active and frame_count % 30 == 0:
                threat_active = False
                print("Threat auto-deactivated")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"\nProcessed {frame_count} frames")
        print("Demo complete!")


if __name__ == "__main__":
    main()

"""eyeTerm configuration via dataclasses + environment variables."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PaneConfig:
    """A Claude Code session pane."""
    name: str
    workdir: str
    session_name: Optional[str] = None


@dataclass
class GazeConfig:
    dwell_ms: int = 300
    ema_alpha: float = 0.3       # kept for compat, unused by OneEuroFilter
    calibration_points: int = 5
    # One-Euro filter params (replace EMA)
    min_cutoff: float = 0.15     # low = more smoothing at rest (was 0.4)
    beta: float = 0.001          # speed-adaptive gain (was 0.003)
    # Auto-range defaults (iris ratio range — tighter = more screen coverage)
    # Y range is narrower because looking down is physically limited
    range_x_min: float = 0.25
    range_x_max: float = 0.75
    range_y_min: float = 0.30
    range_y_max: float = 0.65
    # Confidence gate — skip frames with poor face detection
    min_confidence: float = 0.8
    # Adaptive head-eye fusion (speed-dependent)
    head_weight_min: float = 0.3    # head weight when still (more eye precision)
    head_weight_max: float = 0.7    # head weight when moving (more stability)
    head_speed_threshold: float = 0.03  # speed at which max weight kicks in


@dataclass
class WinkConfig:
    ear_threshold: float = 0.21
    min_frames: int = 3
    cooldown_ms: int = 600
    # IntentionalWinkDetector params
    use_intentional_detector: bool = True
    velocity_threshold: float = 1.5      # EAR/s — below = intentional
    asymmetry_min_ms: int = 150           # ms asymmetry needed for wink
    both_closed_min_ms: int = 400         # ms — intentional both-closed
    both_closed_max_ms: int = 2000        # ms — beyond = resting, not gesture
    intentional_cooldown_ms: int = 800    # cooldown for intentional detector
    baseline_ema_alpha: float = 0.01      # adaptive baseline speed


@dataclass
class DictationConfig:
    enabled: bool = True
    silence_timeout_s: float = 2.0          # seconds of silence before auto-enhance
    preview_timeout_s: float = 15.0         # auto-dismiss preview
    use_agent_team: bool = True             # route enhancement via Agent Team
    use_clipboard_paste: bool = True        # clipboard vs typewrite for insertion


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 4000  # 250ms chunks at 16kHz
    vosk_model_path: str = ""


@dataclass
class CursorConfig:
    enabled: bool = True        # Gaze controls real cursor
    deadzone_px: int = 60       # Ignore jitter below this threshold (was 50)
    require_face: bool = True   # Only move cursor when face detected
    max_speed_px: int = 400     # Velocity clamp — max px per frame (was 800)
    dwell_lock_frames: int = 5  # Frames in deadzone before locking position
    # AccuracyGate
    accuracy_threshold: float = 0.95
    accuracy_off_threshold: float = 0.70
    accuracy_radius_frac: float = 0.05   # fraction of screen diagonal
    drift_threshold_frac: float = 0.07
    accuracy_min_clicks: int = 20
    # ResidualGrid
    grid_size: int = 5
    # ClickCollector
    click_buffer_size: int = 500
    click_max_age_ms: int = 200
    click_max_residual_frac: float = 0.25
    # Polynomial
    poly_ridge_lambda: float = 0.01


@dataclass
class StreamConfig:
    enabled: bool = True        # MJPEG stream for Electron PiP
    port: int = 8099


@dataclass
class AppConfig:
    panes: List[PaneConfig] = field(default_factory=list)
    gaze: GazeConfig = field(default_factory=GazeConfig)
    wink: WinkConfig = field(default_factory=WinkConfig)
    dictation: DictationConfig = field(default_factory=DictationConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    camera_index: int = 0
    window_width: int = 1280
    window_height: int = 720
    target_fps: int = 30
    claude_cli_path: str = "claude"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build config from EYETERM_* environment variables."""
        logger.debug("from_env called")
        panes: List[PaneConfig] = []
        for i in range(4):
            workdir = os.environ.get(f"EYETERM_PANE_{i}_DIR", "")
            if workdir:
                name = os.environ.get(f"EYETERM_PANE_{i}_NAME", f"Pane {i}")
                session = os.environ.get(f"EYETERM_PANE_{i}_SESSION")
                panes.append(PaneConfig(name=name, workdir=workdir, session_name=session))

        vosk_model = os.environ.get("VOSK_MODEL_PATH", "")
        if not vosk_model:
            default_path = Path(__file__).parent / "models" / "vosk-model-small-en-us"
            if default_path.exists():
                vosk_model = str(default_path)

        cursor_enabled = os.environ.get("EYETERM_CURSOR_ENABLED", "true").lower() == "true"
        stream_enabled = os.environ.get("EYETERM_STREAM_ENABLED", "true").lower() == "true"
        deadzone = int(os.environ.get("EYETERM_DEADZONE_PX", "60"))
        max_speed = int(os.environ.get("EYETERM_MAX_SPEED_PX", "400"))
        dwell_lock = int(os.environ.get("EYETERM_DWELL_LOCK_FRAMES", "5"))

        # One-Euro filter tuning
        min_cutoff = float(os.environ.get("EYETERM_GAZE_MIN_CUTOFF", "0.15"))
        beta = float(os.environ.get("EYETERM_GAZE_BETA", "0.001"))

        # Confidence gate
        min_confidence = float(os.environ.get("EYETERM_MIN_CONFIDENCE", "0.8"))

        # Adaptive head-eye fusion
        hw_min = float(os.environ.get("EYETERM_HEAD_WEIGHT_MIN", "0.3"))
        hw_max = float(os.environ.get("EYETERM_HEAD_WEIGHT_MAX", "0.7"))
        hw_speed = float(os.environ.get("EYETERM_HEAD_SPEED_THRESH", "0.03"))

        # AccuracyGate + ResidualGrid + ClickCollector + Polynomial
        acc_thresh = float(os.environ.get("EYETERM_ACCURACY_THRESHOLD", "0.75"))
        acc_off = float(os.environ.get("EYETERM_ACCURACY_OFF", "0.50"))
        acc_radius = float(os.environ.get("EYETERM_ACCURACY_RADIUS_FRAC", "0.05"))
        drift_frac = float(os.environ.get("EYETERM_DRIFT_THRESHOLD_FRAC", "0.07"))
        acc_min_clicks = int(os.environ.get("EYETERM_ACCURACY_MIN_CLICKS", "20"))
        grid_size = int(os.environ.get("EYETERM_GRID_SIZE", "5"))
        click_buffer = int(os.environ.get("EYETERM_CLICK_BUFFER", "500"))
        click_age = int(os.environ.get("EYETERM_CLICK_MAX_AGE", "200"))
        click_res_frac = float(os.environ.get("EYETERM_CLICK_MAX_RESIDUAL_FRAC", "0.25"))
        poly_ridge = float(os.environ.get("EYETERM_POLY_RIDGE_LAMBDA", "0.01"))

        # Gaze range (auto-range uses these as initial defaults)
        range_x_min = float(os.environ.get("EYETERM_GAZE_RANGE_X_MIN", "0.20"))
        range_x_max = float(os.environ.get("EYETERM_GAZE_RANGE_X_MAX", "0.80"))
        range_y_min = float(os.environ.get("EYETERM_GAZE_RANGE_Y_MIN", "0.25"))
        range_y_max = float(os.environ.get("EYETERM_GAZE_RANGE_Y_MAX", "0.75"))

        return cls(
            panes=panes if panes else [PaneConfig(name="Default", workdir=os.getcwd())],
            audio=AudioConfig(vosk_model_path=vosk_model),
            cursor=CursorConfig(
                enabled=cursor_enabled,
                deadzone_px=deadzone,
                max_speed_px=max_speed,
                dwell_lock_frames=dwell_lock,
                accuracy_threshold=acc_thresh,
                accuracy_off_threshold=acc_off,
                accuracy_radius_frac=acc_radius,
                drift_threshold_frac=drift_frac,
                accuracy_min_clicks=acc_min_clicks,
                grid_size=grid_size,
                click_buffer_size=click_buffer,
                click_max_age_ms=click_age,
                click_max_residual_frac=click_res_frac,
                poly_ridge_lambda=poly_ridge,
            ),
            stream=StreamConfig(enabled=stream_enabled),
            gaze=GazeConfig(
                min_cutoff=min_cutoff,
                beta=beta,
                range_x_min=range_x_min,
                range_x_max=range_x_max,
                range_y_min=range_y_min,
                range_y_max=range_y_max,
                min_confidence=min_confidence,
                head_weight_min=hw_min,
                head_weight_max=hw_max,
                head_speed_threshold=hw_speed,
            ),
            camera_index=int(os.environ.get("EYETERM_CAMERA_INDEX", "0")),
            claude_cli_path=os.environ.get("EYETERM_CLAUDE_CLI", "claude"),
        )

    @classmethod
    def from_dirs(cls, dirs: List[str], camera_index: int = 0) -> "AppConfig":
        """Build config from a list of working directories."""
        panes = [PaneConfig(name=f"Pane {i}", workdir=d) for i, d in enumerate(dirs)]
        return cls(panes=panes, camera_index=camera_index)

"""eyeTerm vision pipeline — camera capture, gaze estimation, wink detection, calibration."""


def __getattr__(name):
    """Lazy import — avoid loading cv2/mediapipe at package import."""
    if name == "CameraCapture":
        from .camera import CameraCapture
        return CameraCapture
    if name in ("GazeEstimator", "GazeSmoother", "GazeToScreen", "FocusRouter"):
        from .gaze import GazeEstimator, GazeSmoother, GazeToScreen, FocusRouter
        return locals()[name]
    if name == "WinkDetector":
        from .wink import WinkDetector
        return WinkDetector
    if name == "CalibrationRunner":
        from .calibrate import CalibrationRunner
        return CalibrationRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CameraCapture",
    "GazeEstimator",
    "GazeSmoother",
    "GazeToScreen",
    "FocusRouter",
    "WinkDetector",
    "CalibrationRunner",
]

"""eyeTerm - Hands-free screen understanding + action controller.

4-Layer Architecture:
  A: Gaze     - webcam → screen point
  B: Hit-Test - screen point → UI element (Windows UI Automation)
  C: AI       - element + voice → intended action
  D: Action   - UIA pattern > keyboard > OCR fallback
"""
def __getattr__(name):
    """Lazy import — avoid loading heavy deps (cv2, mediapipe) at package import."""
    if name == "EyeTermApp":
        from .app import EyeTermApp
        return EyeTermApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["EyeTermApp"]

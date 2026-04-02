"""eyeterm.screen — Screen understanding via UI Automation and OCR fallback."""


def __getattr__(name):
    """Lazy import — avoid loading comtypes/pyautogui at package import."""
    if name == "UIElementContext":
        from .element_context import UIElementContext
        return UIElementContext
    if name == "UIAInspector":
        from .uia_inspector import UIAInspector
        return UIAInspector
    if name == "OCRFallback":
        from .fallback_ocr import OCRFallback
        return OCRFallback
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["UIElementContext", "UIAInspector", "OCRFallback"]

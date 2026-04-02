"""eyeTerm cursor control components."""


def __getattr__(name):
    if name == "CursorDriver":
        from .cursor_driver import CursorDriver
        return CursorDriver
    if name == "ClickCollector":
        from .click_collector import ClickCollector
        return ClickCollector
    if name == "ResidualGrid":
        from .residual_grid import ResidualGrid
        return ResidualGrid
    if name == "AccuracyGate":
        from .accuracy_gate import AccuracyGate
        return AccuracyGate
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""
MoireTracker gRPC Workers

Worker-Implementierungen für:
- ClassificationWorker: Parallele LLM Icon-Klassifizierung
- VisionValidationWorker: CNN-LLM Vergleich
- ExecutionWorker: Desktop Actions mit Validation-Loop
- DesktopTools: Desktop-Automation Tool-Definitionen
"""

from .classification_worker import ClassificationWorker
from .validation_worker import VisionValidationWorker

# NEW: Tool-Using Agent Workers
try:
    from .execution_worker import (
        ExecutionWorker,
        ExecutionWorkerConfig,
        get_execution_worker
    )
    from .desktop_tools import (
        DesktopToolExecutor,
        SizeValidator,
        get_tool_executor,
        get_tool_functions_schema,
        DESKTOP_TOOLS
    )
    HAS_EXECUTION_WORKER = True
except ImportError:
    HAS_EXECUTION_WORKER = False
    ExecutionWorker = None
    ExecutionWorkerConfig = None
    get_execution_worker = None
    DesktopToolExecutor = None
    SizeValidator = None
    get_tool_executor = None
    get_tool_functions_schema = None
    DESKTOP_TOOLS = {}

__all__ = [
    'ClassificationWorker',
    'VisionValidationWorker',
    # Tool-Using Agent
    'ExecutionWorker',
    'ExecutionWorkerConfig',
    'get_execution_worker',
    'DesktopToolExecutor',
    'SizeValidator',
    'get_tool_executor',
    'get_tool_functions_schema',
    'DESKTOP_TOOLS',
    'HAS_EXECUTION_WORKER'
]
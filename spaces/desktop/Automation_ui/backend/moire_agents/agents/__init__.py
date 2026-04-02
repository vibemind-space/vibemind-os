"""
MoireTracker_v2 - Agent System

Enthält:
- OrchestratorV2: Event-driven Agent Koordination mit Reflection-Loop
- SocietyOfMindOrchestrator: AutoGen SocietyOfMind Pattern
- ReasoningAgent: Task-Planung mit LLM
- VisionAgent: Element-Lokalisierung via Claude Vision
- InteractionAgent: Desktop-Automation mit pyautogui
"""

from agents.orchestrator_v2 import (
    OrchestratorV2,
    get_orchestrator_v2,
    shutdown_orchestrator,
    ReflectionRequest,
    ReflectionResult,
    ReflectionStatus
)

from agents.reasoning import (
    ReasoningAgent,
    get_reasoning_agent
)

from agents.interaction import (
    InteractionAgent,
    get_interaction_agent
)

# Optional: VisionAgent (benötigt OpenRouter Key)
try:
    from agents.vision_agent import (
        VisionAnalystAgent,
        get_vision_agent,
        ElementLocation,
        VisionAnalysis
    )
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

# Optional: SocietyOfMindOrchestrator (benötigt autogen-agentchat)
try:
    from agents.society_orchestrator import (
        SocietyOfMindOrchestrator,
        get_society_orchestrator,
        DesktopTools
    )
    HAS_SOCIETY = True
except ImportError:
    HAS_SOCIETY = False

# Optional: SocietyOfMindOrchestrator (benötigt autogen-agentchat)
try:
    from agents.society_orchestrator_v2 import (
        SocietyOfMindOrchestratorV2,
        DesktopToolsV2,
        ExecutionRecord,
        TaskContext,
        get_society_orchestrator_v2,
        create_society_orchestrator_v2,
        shutdown_society_orchestrator_v2
    )
    HAS_SOCIETY_V2 = True
except ImportError:
    HAS_SOCIETY_V2 = False

# Optional: RL-Agent (benötigt StableDiffusion oder OpenRouter-Key)
try:
    from agents.rl_agent import (
        RLAgent,
        RLEnhancedOrchestrator,
        ActionSuggestion,
        get_rl_agent
    )
    HAS_RL = True
except ImportError:
    HAS_RL = False

# Optional: KI-basierte Validierung von CNN-Klassifizierungen
try:
    from agents.classification_agent import (
        ClassificationValidationAgent,
        get_classification_agent
    )
    HAS_CLASSIFICATION = True
except ImportError:
    HAS_CLASSIFICATION = False

__all__ = [
    # Core Orchestrator
    "OrchestratorV2",
    "get_orchestrator_v2",
    "shutdown_orchestrator",
    
    # Reflection Types
    "ReflectionRequest",
    "ReflectionResult", 
    "ReflectionStatus",
    
    # Agents
    "ReasoningAgent",
    "get_reasoning_agent",
    "InteractionAgent",
    "get_interaction_agent",
    
    # Feature Flags
    "HAS_VISION",
    "HAS_SOCIETY",
    "HAS_SOCIETY_V2",
    "HAS_RL",
    "HAS_CLASSIFICATION",
]

# Conditional exports
if HAS_VISION:
    __all__.extend([
        "VisionAnalystAgent",
        "get_vision_agent",
        "ElementLocation",
        "VisionAnalysis"
    ])

if HAS_SOCIETY:
    __all__.extend([
        "SocietyOfMindOrchestrator",
        "get_society_orchestrator",
        "DesktopTools"
    ])

if HAS_SOCIETY_V2:
    __all__.extend([
        "SocietyOfMindOrchestratorV2",
        "get_society_orchestrator_v2",
        "DesktopToolsV2",
        "ExecutionRecord",
        "TaskContext",
        "create_society_orchestrator_v2",
        "shutdown_society_orchestrator_v2"
    ])

if HAS_RL:
    __all__.extend([
        "RLAgent",
        "RLEnhancedOrchestrator",
        "ActionSuggestion",
        "get_rl_agent"
    ])

if HAS_CLASSIFICATION:
    __all__.extend([
        "ClassificationValidationAgent",
        "get_classification_agent"
    ])
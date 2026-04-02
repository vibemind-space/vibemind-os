"""
Idea Explorer - AI-Scientist-inspired Tree Search for Idea Connections

This module adapts AI-Scientist-v2's Best-First Tree Search (BFTS) for
discovering connections between ideas/bubbles in VibeMind.

Components:
- IdeaNode: Single discovered connection between bubbles
- IdeaJournal: Collection of explored connections
- IdeaTreeSearch: 4-stage exploration using BFTS algorithm
- ConnectionEvaluator: Scores connections using embedding + LLM
- ExplorationClarificationAgent: Human-in-the-loop interaction
"""

from .idea_node import IdeaNode, ConnectionType
from .idea_journal import IdeaJournal, ExplorationSession
from .connection_evaluator import ConnectionEvaluator, EvaluationResult
from .exploration_repository import ExplorationRepository
from .idea_tree_search import IdeaTreeSearch, ExplorationConfig, ExplorationStage
from .exploration_clarification import (
    ExplorationClarificationAgent,
    ExplorationMode,
    QuestionType,
    ClarificationQuestion,
    ClarificationResponse,
    InteractiveExplorationConfig,
    classify_voice_response,
)

__all__ = [
    # Core components
    "IdeaNode",
    "IdeaJournal",
    "ExplorationSession",
    "ConnectionType",
    "ConnectionEvaluator",
    "EvaluationResult",
    "ExplorationRepository",
    "IdeaTreeSearch",
    "ExplorationConfig",
    "ExplorationStage",
    # Human-in-the-loop
    "ExplorationClarificationAgent",
    "ExplorationMode",
    "QuestionType",
    "ClarificationQuestion",
    "ClarificationResponse",
    "InteractiveExplorationConfig",
    "classify_voice_response",
]

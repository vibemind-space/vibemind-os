"""
Context Module - Tracks cursor, selection, and app state for precise UI operations.

Provides "Feingefühl" (fine-control) for text operations like formatting in Word.
"""

from .selection_manager import SelectionManager, ClipboardState, get_selection_manager
from .context_tracker import ContextTracker, CursorPosition, SelectionState, AppContext, get_context_tracker
from .word_helper import WordHelper, FormattingState, get_word_helper

__all__ = [
    # Selection Manager
    'SelectionManager',
    'ClipboardState', 
    'get_selection_manager',
    
    # Context Tracker
    'ContextTracker',
    'CursorPosition',
    'SelectionState',
    'AppContext',
    'get_context_tracker',
    
    # Word Helper
    'WordHelper',
    'FormattingState',
    'get_word_helper',
]
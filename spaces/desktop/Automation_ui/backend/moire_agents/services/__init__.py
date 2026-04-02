"""
MoireTracker_v2 Python Services

- DesktopAnalyzer: DataFrame Export für UI-Analyse
"""

from .desktop_analyzer import (
    DesktopAnalyzer,
    AnalysisResult,
    AnalyzedElement,
    scan_desktop_to_dataframe
)

__all__ = [
    'DesktopAnalyzer',
    'AnalysisResult',
    'AnalyzedElement',
    'scan_desktop_to_dataframe'
]
"""Test that all modules load correctly with localization."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print('Testing imports...')

# Test localization
from core.localization import L, get_language
print(f'  Localization: OK (language: {get_language()})')

# Test openrouter_client
from core.openrouter_client import HAS_LOCALIZATION as OR_LOC
print(f'  OpenRouter: OK (localization={OR_LOC})')

# Test vision_agent
from agents.vision_agent import HAS_LOCALIZATION as VA_LOC
print(f'  VisionAgent: OK (localization={VA_LOC})')

# Test reasoning
from agents.reasoning import HAS_LOCALIZATION as RA_LOC
print(f'  Reasoning: OK (localization={RA_LOC})')

print()
print('All modules loaded successfully with localization support!')

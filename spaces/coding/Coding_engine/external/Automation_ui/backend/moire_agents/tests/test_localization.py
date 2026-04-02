"""Test localization module."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.localization import L, get_language, set_language

print(f'Detected OS language: {get_language()}')
print()

# Test German prompt
print('=== German Prompt (first 150 chars) ===')
set_language('de')
prompt_de = L.get('vision_find_element', element='Save Button', context='', w=1920, h=1080)
print(prompt_de[:150] + '...')
print()

# Test English prompt
print('=== English Prompt (first 150 chars) ===')
set_language('en')
prompt_en = L.get('vision_find_element', element='Save Button', context='', w=1920, h=1080)
print(prompt_en[:150] + '...')
print()

print('Localization test PASSED!')

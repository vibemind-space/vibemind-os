"""Test screen reading with OCR."""
import pyautogui
import pytesseract
from PIL import Image

# Screenshot aufnehmen
screenshot = pyautogui.screenshot()
print(f'Screenshot size: {screenshot.width}x{screenshot.height}')

# OCR durchfuehren
try:
    text = pytesseract.image_to_string(screenshot)
    print('=== OCR TEXT ===')
    print(text[:3000] if len(text) > 3000 else text)
    print(f'\n=== Total characters: {len(text)} ===')
except Exception as e:
    print(f'OCR Error: {e}')

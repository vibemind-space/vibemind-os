"""
Quick screenshot of live dashboard
"""

from playwright.sync_api import sync_playwright
import time

def capture_dashboard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("http://localhost:5004", wait_until="networkidle")
        time.sleep(2)
        page.screenshot(path="klotski_live_training.png", full_page=True)
        print("[OK] Screenshot saved: klotski_live_training.png")
        time.sleep(3)
        browser.close()

if __name__ == '__main__':
    capture_dashboard()

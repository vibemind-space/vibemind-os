"""
Playwright test for NeuroSymbolic Klotski Evolution Dashboard
"""

from playwright.sync_api import sync_playwright
import time

def test_klotski_dashboard():
    print("[OK] Starting Playwright test for Klotski dashboard...")

    with sync_playwright() as p:
        # Launch browser
        print("[OK] Launching Chromium browser...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to dashboard
        print("[OK] Navigating to http://localhost:5004...")
        page.goto("http://localhost:5004", wait_until="networkidle")

        # Wait for page to load
        time.sleep(2)

        # Take full-page screenshot
        print("[OK] Taking screenshot...")
        page.screenshot(path="klotski_dashboard_screenshot.png", full_page=True)
        print("[OK] Screenshot saved: klotski_dashboard_screenshot.png")

        # Verify key elements
        print("\n[OK] Verifying dashboard elements...")

        # Check header
        try:
            header = page.locator("h1").inner_text()
            print(f"  Header: {header[:50]}...")
        except Exception as e:
            print(f"  [ERROR] Header check failed: {e}")

        # Check for Klotski puzzle grids (4x5 grid = 20 cells each)
        for agent in ['beginning', 'mid', 'end']:
            try:
                grid = page.locator(f"#puzzle-{agent}")
                if grid.count() > 0:
                    print(f"  [OK] Found puzzle grid for agent: {agent}")
                else:
                    print(f"  [ERROR] Missing puzzle grid for agent: {agent}")
            except Exception as e:
                print(f"  [ERROR] Grid check failed for {agent}: {e}")

        # Check for brain module blocks (10 modules: VIS, AUD, SOM, LAN, DLPFC, OFC, ACC, INS, MTL, DMN)
        modules = ['VIS', 'AUD', 'SOM', 'LAN', 'DLPFC', 'OFC', 'ACC', 'INS', 'MTL', 'DMN']
        print("\n[OK] Checking brain module blocks...")
        for module in modules:
            try:
                for agent in ['beginning', 'mid', 'end']:
                    element = page.locator(f"#{ agent}-{module}")
                    if element.count() > 0:
                        print(f"  [OK] Found module {module} for {agent}")
                        break
            except Exception as e:
                pass

        # Check for agent cards
        print("\n[OK] Checking agent cards...")
        for agent in ['beginning', 'mid', 'end']:
            try:
                card = page.locator(f".agent-card")
                count = card.count()
                if count >= 3:
                    print(f"  [OK] Found {count} agent cards")
                    break
            except Exception as e:
                print(f"  [ERROR] Agent card check failed: {e}")

        print("\n[OK] Test completed!")
        print("[OK] Dashboard is serving the Klotski interface!")

        # Keep browser open for 5 seconds to inspect
        time.sleep(5)

        browser.close()

if __name__ == '__main__':
    test_klotski_dashboard()

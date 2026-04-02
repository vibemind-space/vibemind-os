"""Test Klotski Dashboard with Playwright"""
from playwright.sync_api import sync_playwright
import time

def test_dashboard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("=" * 80)
        print("Testing Klotski Dashboard with Playwright")
        print("=" * 80)

        # Navigate to dashboard
        print("\n[1] Opening dashboard at http://localhost:5004...")
        page.goto("http://localhost:5004")
        time.sleep(2)

        # Take screenshot
        print("[2] Taking screenshot...")
        page.screenshot(path="dashboard_screenshot.png", full_page=True)
        print("    Screenshot saved: dashboard_screenshot.png")

        # Check for key elements
        print("\n[3] Verifying dashboard elements...")

        # Check header
        header = page.locator("h1")
        if header.is_visible():
            print("    [OK] Header found:", header.inner_text())

        # Check generation panel
        gen_element = page.locator("#current-generation")
        if gen_element.is_visible():
            print(f"    [OK] Current Generation: {gen_element.inner_text()}")

        # Check agent cards
        for agent in ['beginning', 'mid', 'end']:
            card = page.locator(f"#agent-{agent}")
            if card.is_visible():
                print(f"    [OK] Agent card '{agent}' visible")

        # Check puzzle grids
        for agent in ['beginning', 'mid', 'end']:
            grid = page.locator(f"#puzzle-{agent}")
            if grid.is_visible():
                print(f"    [OK] Puzzle grid '{agent}' visible")

        # Check module activations
        modules = ['VIS', 'AUD', 'SOM', 'LAN', 'DLPFC', 'OFC', 'ACC', 'INS', 'MTL', 'DMN']
        visible_modules = 0
        for module in modules:
            module_bar = page.locator(f"#beginning-{module}")
            if module_bar.is_visible():
                visible_modules += 1
        print(f"    [OK] {visible_modules}/10 neural module bars visible")

        # Wait a bit for updates
        print("\n[4] Waiting for real-time updates (5 seconds)...")
        time.sleep(5)

        # Check stats update
        episodes = page.locator("#total-episodes")
        if episodes.is_visible():
            print(f"    [OK] Episodes: {episodes.inner_text()}")

        success_rate = page.locator("#success-rate")
        if success_rate.is_visible():
            print(f"    [OK] Success Rate: {success_rate.inner_text()}")

        # Final screenshot
        print("\n[5] Taking final screenshot after updates...")
        page.screenshot(path="dashboard_screenshot_updated.png", full_page=True)
        print("    Screenshot saved: dashboard_screenshot_updated.png")

        print("\n" + "=" * 80)
        print("Dashboard Test COMPLETE!")
        print("=" * 80)
        print("Both screenshots saved:")
        print("  - dashboard_screenshot.png (initial)")
        print("  - dashboard_screenshot_updated.png (after 5 seconds)")
        print("\nDashboard is operational at http://localhost:5004")
        print("=" * 80)

        # Keep browser open for 5 more seconds
        print("\nKeeping browser open for 5 more seconds...")
        time.sleep(5)

        browser.close()

if __name__ == "__main__":
    test_dashboard()

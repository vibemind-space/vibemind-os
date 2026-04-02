"""
PlaywrightAgent - Spezialisiert für Playwright-Operationen

Dieser Agent ist verantwortlich für:
- Browser starten
- Browser steuern
- Screenshots erstellen
- Tests ausführen
- Logs erhalten
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path
from enum import Enum

try:
    from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BrowserType(Enum):
    """Browser-Typen"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class ScreenshotFormat(Enum):
    """Screenshot-Formate"""
    PNG = "png"
    JPEG = "jpeg"


class PlaywrightAgent:
    """Agent für Playwright-Operationen"""
    
    def __init__(
        self,
        browser_type: BrowserType = BrowserType.CHROMIUM,
        headless: bool = True,
        screenshot_dir: str = "screenshots"
    ):
        """
        Initialisiert den PlaywrightAgent
        
        Args:
            browser_type: Browser-Typ
            headless: Headless-Modus
            screenshot_dir: Verzeichnis für Screenshots
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright-Paket ist nicht installiert. "
                "Installiere es mit: pip install playwright && playwright install"
            )
        
        self.browser_type = browser_type
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        self.started = False
        
        self.stats = {
            "operations": [],
            "pages_visited": 0,
            "screenshots_taken": 0,
            "tests_run": 0,
            "errors": 0
        }
        
        logger.info(f"PlaywrightAgent initialisiert: {browser_type.value}, headless={headless}")
    
    def start(self) -> Dict[str, Any]:
        """
        Startet den Browser
        
        Returns:
            Dict mit Status
        """
        try:
            self.playwright = sync_playwright().start()
            
            if self.browser_type == BrowserType.CHROMIUM:
                self.browser = self.playwright.chromium.launch(headless=self.headless)
            elif self.browser_type == BrowserType.FIREFOX:
                self.browser = self.playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == BrowserType.WEBKIT:
                self.browser = self.playwright.webkit.launch(headless=self.headless)
            
            self.context = self.browser.new_context()
            self.page = self.context.new_page()
            
            self.started = True
            
            self._log_operation(
                "start",
                {
                    "browser_type": self.browser_type.value,
                    "headless": self.headless
                }
            )
            
            return {
                "status": "success",
                "message": "Browser gestartet"
            }
        except Exception as e:
            logger.error(f"Fehler beim Starten des Browsers: {e}")
            self.started = False
            return {
                "status": "error",
                "error": str(e)
            }
    
    def stop(self) -> Dict[str, Any]:
        """
        Stoppt den Browser
        
        Returns:
            Dict mit Status
        """
        try:
            if self.page:
                self.page.close()
                self.page = None
            
            if self.context:
                self.context.close()
                self.context = None
            
            if self.browser:
                self.browser.close()
                self.browser = None
            
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
            
            self.started = False
            
            self._log_operation(
                "stop",
                {}
            )
            
            return {
                "status": "success",
                "message": "Browser gestoppt"
            }
        except Exception as e:
            logger.error(f"Fehler beim Stoppen des Browsers: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _ensure_started(self) -> bool:
        """Stellt sicher, dass der Browser gestartet ist"""
        if not self.started:
            result = self.start()
            return result["status"] == "success"
        return True
    
    def _log_operation(
        self,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Protokolliert eine Operation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "details": details or {}
        }
        
        self.stats["operations"].append(log_entry)
        logger.info(f"{operation}: {details}")
    
    def goto(
        self,
        url: str,
        wait_until: str = "load"
    ) -> Dict[str, Any]:
        """
        Navigiert zu einer URL
        
        Args:
            url: URL
            wait_until: Warten bis (load, domcontentloaded, networkidle)
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            self.page.goto(url, wait_until=wait_until)
            
            self.stats["pages_visited"] += 1
            
            self._log_operation(
                "goto",
                {"url": url}
            )
            
            return {
                "status": "success",
                "url": url
            }
        except Exception as e:
            logger.error(f"Fehler beim Navigieren: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def click(
        self,
        selector: str,
        timeout: int = 30000
    ) -> Dict[str, Any]:
        """
        Klickt auf ein Element
        
        Args:
            selector: CSS-Selector
            timeout: Timeout in ms
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            self.page.click(selector, timeout=timeout)
            
            self._log_operation(
                "click",
                {"selector": selector}
            )
            
            return {
                "status": "success",
                "selector": selector
            }
        except Exception as e:
            logger.error(f"Fehler beim Klicken: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def fill(
        self,
        selector: str,
        value: str,
        timeout: int = 30000
    ) -> Dict[str, Any]:
        """
        Füllt ein Eingabefeld
        
        Args:
            selector: CSS-Selector
            value: Wert
            timeout: Timeout in ms
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            self.page.fill(selector, value, timeout=timeout)
            
            self._log_operation(
                "fill",
                {"selector": selector}
            )
            
            return {
                "status": "success",
                "selector": selector
            }
        except Exception as e:
            logger.error(f"Fehler beim Füllen: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_text(
        self,
        selector: str,
        timeout: int = 30000
    ) -> Dict[str, Any]:
        """
        Liest Text eines Elements
        
        Args:
            selector: CSS-Selector
            timeout: Timeout in ms
            
        Returns:
            Dict mit Status und Text
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            text = self.page.text_content(selector, timeout=timeout)
            
            self._log_operation(
                "get_text",
                {"selector": selector}
            )
            
            return {
                "status": "success",
                "selector": selector,
                "text": text
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen des Texts: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def screenshot(
        self,
        filename: Optional[str] = None,
        format: ScreenshotFormat = ScreenshotFormat.PNG,
        full_page: bool = False
    ) -> Dict[str, Any]:
        """
        Erstellt einen Screenshot
        
        Args:
            filename: Dateiname
            format: Format
            full_page: Ganze Seite
            
        Returns:
            Dict mit Status und Pfad
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.{format.value}"
            
            filepath = self.screenshot_dir / filename
            
            self.page.screenshot(
                path=str(filepath),
                type=format.value,
                full_page=full_page
            )
            
            self.stats["screenshots_taken"] += 1
            
            self._log_operation(
                "screenshot",
                {
                    "filename": filename,
                    "format": format.value,
                    "full_page": full_page
                }
            )
            
            return {
                "status": "success",
                "filename": filename,
                "path": str(filepath)
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Screenshots: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def wait_for_selector(
        self,
        selector: str,
        timeout: int = 30000
    ) -> Dict[str, Any]:
        """
        Wartet auf ein Element
        
        Args:
            selector: CSS-Selector
            timeout: Timeout in ms
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            self.page.wait_for_selector(selector, timeout=timeout)
            
            self._log_operation(
                "wait_for_selector",
                {"selector": selector}
            )
            
            return {
                "status": "success",
                "selector": selector
            }
        except Exception as e:
            logger.error(f"Fehler beim Warten auf Element: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def wait_for_timeout(
        self,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Wartet eine bestimmte Zeit
        
        Args:
            timeout: Timeout in ms
            
        Returns:
            Dict mit Status
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            self.page.wait_for_timeout(timeout)
            
            self._log_operation(
                "wait_for_timeout",
                {"timeout": timeout}
            )
            
            return {
                "status": "success",
                "timeout": timeout
            }
        except Exception as e:
            logger.error(f"Fehler beim Warten: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def evaluate(
        self,
        script: str
    ) -> Dict[str, Any]:
        """
        Führt JavaScript aus
        
        Args:
            script: JavaScript-Code
            
        Returns:
            Dict mit Status und Ergebnis
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            result = self.page.evaluate(script)
            
            self._log_operation(
                "evaluate",
                {"script": script[:100]}
            )
            
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen von JavaScript: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_url(self) -> Dict[str, Any]:
        """
        Holt die aktuelle URL
        
        Returns:
            Dict mit Status und URL
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            url = self.page.url
            
            self._log_operation(
                "get_url",
                {}
            )
            
            return {
                "status": "success",
                "url": url
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen der URL: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_title(self) -> Dict[str, Any]:
        """
        Holt den Titel der Seite
        
        Returns:
            Dict mit Status und Titel
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            title = self.page.title()
            
            self._log_operation(
                "get_title",
                {}
            )
            
            return {
                "status": "success",
                "title": title
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen des Titels: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_console_logs(self) -> Dict[str, Any]:
        """
        Holt die Console-Logs
        
        Returns:
            Dict mit Status und Logs
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            logs = []
            
            def on_console(msg):
                logs.append({
                    "type": msg.type,
                    "text": msg.text,
                    "timestamp": datetime.now().isoformat()
                })
            
            self.page.on("console", on_console)
            
            self._log_operation(
                "get_console_logs",
                {}
            )
            
            return {
                "status": "success",
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen der Console-Logs: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_network_logs(self) -> Dict[str, Any]:
        """
        Holt die Network-Logs
        
        Returns:
            Dict mit Status und Logs
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            logs = []
            
            def on_response(response):
                logs.append({
                    "url": response.url,
                    "status": response.status,
                    "method": response.request.method,
                    "timestamp": datetime.now().isoformat()
                })
            
            self.page.on("response", on_response)
            
            self._log_operation(
                "get_network_logs",
                {}
            )
            
            return {
                "status": "success",
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Holen der Network-Logs: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def run_test(
        self,
        test_name: str,
        steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Führt einen Test aus
        
        Args:
            test_name: Test-Name
            steps: Test-Schritte
            
        Returns:
            Dict mit Status und Ergebnis
        """
        try:
            if not self._ensure_started():
                return {
                    "status": "error",
                    "error": "Browser nicht gestartet"
                }
            
            results = []
            passed = True
            
            for step in steps:
                step_type = step.get("type")
                
                if step_type == "goto":
                    result = self.goto(step["url"])
                elif step_type == "click":
                    result = self.click(step["selector"])
                elif step_type == "fill":
                    result = self.fill(step["selector"], step["value"])
                elif step_type == "wait_for_selector":
                    result = self.wait_for_selector(step["selector"])
                elif step_type == "wait_for_timeout":
                    result = self.wait_for_timeout(step["timeout"])
                elif step_type == "screenshot":
                    result = self.screenshot(step.get("filename"))
                elif step_type == "get_text":
                    result = self.get_text(step["selector"])
                elif step_type == "evaluate":
                    result = self.evaluate(step["script"])
                else:
                    result = {
                        "status": "error",
                        "error": f"Unbekannter Schritt-Typ: {step_type}"
                    }
                
                results.append({
                    "step": step,
                    "result": result
                })
                
                if result["status"] != "success":
                    passed = False
                    break
            
            self.stats["tests_run"] += 1
            
            self._log_operation(
                "run_test",
                {
                    "test_name": test_name,
                    "passed": passed,
                    "steps": len(steps)
                }
            )
            
            return {
                "status": "success",
                "test_name": test_name,
                "passed": passed,
                "results": results
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen des Tests: {e}")
            self.stats["errors"] += 1
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            "status": "success",
            "stats": self.stats
        }
    
    def get_operations_log(
        self,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Gibt das Operations-Log zurück"""
        operations = self.stats["operations"]
        
        if limit:
            operations = operations[-limit:]
        
        return {
            "status": "success",
            "operations": operations
        }
    
    def health_check(self) -> bool:
        """Health Check"""
        try:
            return self.started and self.browser is not None
        except Exception:
            return False


def main():
    """Test-Implementierung"""
    try:
        agent = PlaywrightAgent(headless=True)
        
        # Start
        print(f"Start: {agent.start()}")
        
        # Goto
        print(f"Goto: {agent.goto('https://example.com')}")
        
        # Get Title
        print(f"Get Title: {agent.get_title()}")
        
        # Screenshot
        print(f"Screenshot: {agent.screenshot()}")
        
        # Stats
        stats = agent.get_stats()
        print(f"Stats: {stats}")
        
        # Stop
        print(f"Stop: {agent.stop()}")
    except Exception as e:
        print(f"Fehler: {e}")


if __name__ == "__main__":
    main()

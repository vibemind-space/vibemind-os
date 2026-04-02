"""
Playwright Tool für EventFixTeam
Bietet Funktionen für E2E-Testing und Browser-Automatisierung
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

logger = logging.getLogger(__name__)


class PlaywrightTool:
    """Tool für Playwright-Operationen"""
    
    def __init__(self, base_dir: str = ".", headless: bool = True, browser_type: str = "chromium"):
        """
        Playwright Tool initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
            headless: Headless-Modus
            browser_type: Browser-Typ (chromium, firefox, webkit)
        """
        self.base_dir = Path(base_dir)
        self.playwright_dir = self.base_dir / "playwright"
        self.playwright_dir.mkdir(exist_ok=True)
        self.headless = headless
        self.browser_type = browser_type
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        logger.info(f"Playwright Tool initialisiert mit Browser: {browser_type}, Headless: {headless}")
    
    async def start(self) -> Dict[str, Any]:
        """
        Playwright starten
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            self.playwright = await async_playwright().start()
            
            # Browser starten
            if self.browser_type == "chromium":
                self.browser = await self.playwright.chromium.launch(headless=self.headless)
            elif self.browser_type == "firefox":
                self.browser = await self.playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == "webkit":
                self.browser = await self.playwright.webkit.launch(headless=self.headless)
            else:
                raise ValueError(f"Unbekannter Browser-Typ: {self.browser_type}")
            
            # Context erstellen
            self.context = await self.browser.new_context()
            
            # Page erstellen
            self.page = await self.context.new_page()
            
            logger.info(f"Playwright gestartet: {self.browser_type}")
            return {
                "success": True,
                "output": f"Playwright gestartet: {self.browser_type}",
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Starten von Playwright: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def stop(self) -> Dict[str, Any]:
        """
        Playwright stoppen
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            logger.info("Playwright gestoppt")
            return {
                "success": True,
                "output": "Playwright gestoppt",
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Stoppen von Playwright: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def navigate(self, url: str) -> Dict[str, Any]:
        """
        Zu URL navigieren
        
        Args:
            url: Ziel-URL
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Navigiere zu: {url}")
            await self.page.goto(url)
            
            # Screenshot speichern
            screenshot_path = self._save_screenshot(f"navigate_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            
            return {
                "success": True,
                "output": f"Navigiert zu: {url}",
                "screenshot": screenshot_path,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Navigieren: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def click(self, selector: str) -> Dict[str, Any]:
        """
        Element klicken
        
        Args:
            selector: CSS-Selector
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Klicke auf: {selector}")
            await self.page.click(selector)
            
            # Screenshot speichern
            screenshot_path = self._save_screenshot(f"click_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            
            return {
                "success": True,
                "output": f"Geklickt auf: {selector}",
                "screenshot": screenshot_path,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Klicken: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """
        Element ausfüllen
        
        Args:
            selector: CSS-Selector
            value: Wert
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Fülle {selector} mit: {value}")
            await self.page.fill(selector, value)
            
            # Screenshot speichern
            screenshot_path = self._save_screenshot(f"fill_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            
            return {
                "success": True,
                "output": f"Ausgefüllt: {selector}",
                "screenshot": screenshot_path,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausfüllen: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def get_text(self, selector: str) -> Dict[str, Any]:
        """
        Text von Element abrufen
        
        Args:
            selector: CSS-Selector
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Hole Text von: {selector}")
            text = await self.page.text_content(selector)
            
            return {
                "success": True,
                "output": text,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Texts: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def get_attribute(self, selector: str, attribute: str) -> Dict[str, Any]:
        """
        Attribut von Element abrufen
        
        Args:
            selector: CSS-Selector
            attribute: Attributname
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Hole Attribut {attribute} von: {selector}")
            value = await self.page.get_attribute(selector, attribute)
            
            return {
                "success": True,
                "output": value,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Attributs: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> Dict[str, Any]:
        """
        Auf Selector warten
        
        Args:
            selector: CSS-Selector
            timeout: Timeout in ms
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Warte auf Selector: {selector}")
            await self.page.wait_for_selector(selector, timeout=timeout)
            
            return {
                "success": True,
                "output": f"Selector gefunden: {selector}",
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Warten auf Selector: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def screenshot(self, filename: str = None) -> Dict[str, Any]:
        """
        Screenshot erstellen
        
        Args:
            filename: Dateiname (optional)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            screenshot_path = self._save_screenshot(filename)
            await self.page.screenshot(path=screenshot_path)
            
            logger.info(f"Screenshot erstellt: {screenshot_path}")
            return {
                "success": True,
                "output": f"Screenshot erstellt: {screenshot_path}",
                "screenshot": screenshot_path,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Screenshots: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def _save_screenshot(self, filename: str) -> str:
        """
        Screenshot speichern
        
        Args:
            filename: Dateiname
        
        Returns:
            Pfad zum Screenshot
        """
        try:
            if not filename.endswith('.png'):
                filename += '.png'
            screenshot_path = self.playwright_dir / filename
            return str(screenshot_path)
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Screenshots: {e}")
            return ""
    
    async def execute_script(self, script: str) -> Dict[str, Any]:
        """
        JavaScript ausführen
        
        Args:
            script: JavaScript-Code
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Führe JavaScript aus: {script[:100]}...")
            result = await self.page.evaluate(script)
            
            return {
                "success": True,
                "output": result,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen von JavaScript: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def get_url(self) -> Dict[str, Any]:
        """
        Aktuelle URL abrufen
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            url = self.page.url
            logger.info(f"Aktuelle URL: {url}")
            
            return {
                "success": True,
                "output": url,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der URL: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def get_title(self) -> Dict[str, Any]:
        """
        Seitentitel abrufen
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            title = await self.page.title()
            logger.info(f"Seitentitel: {title}")
            
            return {
                "success": True,
                "output": title,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Titels: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def wait_for_load_state(self, state: str = "load", timeout: int = 30000) -> Dict[str, Any]:
        """
        Auf Load-State warten
        
        Args:
            state: Load-State (load, domcontentloaded, networkidle)
            timeout: Timeout in ms
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "error": "Playwright nicht gestartet",
                    "logs": ""
                }
            
            logger.info(f"Warte auf Load-State: {state}")
            await self.page.wait_for_load_state(state, timeout=timeout)
            
            return {
                "success": True,
                "output": f"Load-State erreicht: {state}",
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Warten auf Load-State: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    async def run_test(self, test_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Test-Schritte ausführen
        
        Args:
            test_steps: Liste von Test-Schritten
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            results = []
            
            for step in test_steps:
                action = step.get("action")
                params = step.get("params", {})
                
                if action == "navigate":
                    result = await self.navigate(params.get("url"))
                elif action == "click":
                    result = await self.click(params.get("selector"))
                elif action == "fill":
                    result = await self.fill(params.get("selector"), params.get("value"))
                elif action == "get_text":
                    result = await self.get_text(params.get("selector"))
                elif action == "wait_for_selector":
                    result = await self.wait_for_selector(params.get("selector"), params.get("timeout", 30000))
                elif action == "screenshot":
                    result = await self.screenshot(params.get("filename"))
                elif action == "execute_script":
                    result = await self.execute_script(params.get("script"))
                else:
                    result = {
                        "success": False,
                        "error": f"Unbekannte Action: {action}",
                        "logs": ""
                    }
                
                results.append({
                    "step": step,
                    "result": result
                })
                
                # Wenn ein Schritt fehlschlägt, abbrechen
                if not result.get("success"):
                    break
            
            # Test-Report speichern
            report_path = self._save_test_report(results)
            
            return {
                "success": True,
                "output": f"Test abgeschlossen: {len(results)} Schritte",
                "results": results,
                "report": report_path,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen des Tests: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def _save_test_report(self, results: List[Dict[str, Any]]) -> str:
        """
        Test-Report speichern
        
        Args:
            results: Test-Ergebnisse
        
        Returns:
            Pfad zum Report
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = self.playwright_dir / f"test_report_{timestamp}.json"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Test-Report gespeichert: {report_file}")
            return str(report_file)
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Test-Reports: {e}")
            return ""

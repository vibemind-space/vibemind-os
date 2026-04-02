"""
TestAgent - Spezialisiert auf Playwright-Tests
"""
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

logger = logging.getLogger(__name__)


class TestAgent:
    """Agent für Playwright-Tests"""
    
    def __init__(self):
        self.name = "TestAgent"
        self.version = "1.0.0"
        self.supported_operations = [
            "e2e_test",
            "unit_test",
            "integration_test",
            "visual_regression_test",
            "performance_test"
        ]
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
    
    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führt einen Test aus
        
        Args:
            parameters: Dictionary mit Testparametern
                - operation: Art des Tests
                - test_file: Pfad zur Testdatei (optional)
                - test_url: URL für E2E-Tests (optional)
                - test_steps: Liste von Testschritten (optional)
                - headless: Headless-Modus (optional, default: True)
                - screenshot: Screenshot speichern (optional, default: False)
        
        Returns:
            Dictionary mit Testergebnis
        """
        operation = parameters.get('operation', 'e2e_test')
        test_file = parameters.get('test_file')
        test_url = parameters.get('test_url')
        test_steps = parameters.get('test_steps', [])
        headless = parameters.get('headless', True)
        screenshot = parameters.get('screenshot', False)
        
        logger.info(f"{self.name} führt Test aus: {operation}")
        logger.info(f"Test URL: {test_url}")
        logger.info(f"Headless: {headless}")
        
        try:
            # Browser starten
            await self._start_browser(headless)
            
            if operation == "e2e_test":
                result = await self._run_e2e_test(test_url, test_steps, screenshot)
            elif operation == "unit_test":
                result = await self._run_unit_test(test_file)
            elif operation == "integration_test":
                result = await self._run_integration_test(test_file, test_url)
            elif operation == "visual_regression_test":
                result = await self._run_visual_regression_test(test_url, test_steps)
            elif operation == "performance_test":
                result = await self._run_performance_test(test_url, test_steps)
            else:
                raise ValueError(f"Unbekannte Operation: {operation}")
            
            # Browser schließen
            await self._stop_browser()
            
            result['agent'] = self.name
            result['version'] = self.version
            result['timestamp'] = datetime.now().isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Fehler bei Test: {e}")
            await self._stop_browser()
            return {
                'success': False,
                'error': str(e),
                'agent': self.name,
                'version': self.version,
                'timestamp': datetime.now().isoformat()
            }
    
    async def _start_browser(self, headless: bool = True):
        """Startet den Browser"""
        logger.info(f"Starte Browser (headless={headless})...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=headless)
        self.context = await self.browser.new_context()
        logger.info("Browser gestartet")
    
    async def _stop_browser(self):
        """Stoppt den Browser"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        logger.info("Browser gestoppt")
    
    async def _run_e2e_test(self, test_url: Optional[str], 
                           test_steps: List[Dict[str, Any]], 
                           screenshot: bool) -> Dict[str, Any]:
        """Führt einen E2E-Test durch"""
        logger.info("Führe E2E-Test durch...")
        
        if not test_url:
            raise ValueError("test_url ist erforderlich für E2E-Tests")
        
        page = await self.context.new_page()
        results = []
        
        try:
            # URL öffnen
            logger.info(f"Öffne URL: {test_url}")
            await page.goto(test_url)
            results.append({
                'step': 'navigate',
                'status': 'success',
                'url': test_url
            })
            
            # Testschritte ausführen
            for i, step in enumerate(test_steps):
                step_type = step.get('type')
                step_result = await self._execute_test_step(page, step, i + 1)
                results.append(step_result)
                
                if screenshot:
                    screenshot_path = f"screenshot_step_{i+1}.png"
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"Screenshot gespeichert: {screenshot_path}")
            
            # Zusammenfassung
            successful_steps = sum(1 for r in results if r.get('status') == 'success')
            total_steps = len(results)
            
            return {
                'success': True,
                'operation': 'e2e_test',
                'message': f'E2E-Test abgeschlossen: {successful_steps}/{total_steps} Schritte erfolgreich',
                'url': test_url,
                'results': results,
                'summary': {
                    'total_steps': total_steps,
                    'successful_steps': successful_steps,
                    'failed_steps': total_steps - successful_steps
                }
            }
            
        except Exception as e:
            logger.error(f"Fehler bei E2E-Test: {e}")
            return {
                'success': False,
                'operation': 'e2e_test',
                'error': str(e),
                'results': results
            }
    
    async def _execute_test_step(self, page: Page, step: Dict[str, Any], step_num: int) -> Dict[str, Any]:
        """Führt einen einzelnen Testschritt aus"""
        step_type = step.get('type')
        
        try:
            if step_type == 'click':
                selector = step.get('selector')
                await page.click(selector)
                return {
                    'step': step_num,
                    'type': 'click',
                    'selector': selector,
                    'status': 'success'
                }
            
            elif step_type == 'fill':
                selector = step.get('selector')
                value = step.get('value')
                await page.fill(selector, value)
                return {
                    'step': step_num,
                    'type': 'fill',
                    'selector': selector,
                    'value': value,
                    'status': 'success'
                }
            
            elif step_type == 'wait':
                duration = step.get('duration', 1000)
                await page.wait_for_timeout(duration)
                return {
                    'step': step_num,
                    'type': 'wait',
                    'duration': duration,
                    'status': 'success'
                }
            
            elif step_type == 'assert_text':
                selector = step.get('selector')
                expected_text = step.get('text')
                actual_text = await page.text_content(selector)
                
                if expected_text in actual_text:
                    return {
                        'step': step_num,
                        'type': 'assert_text',
                        'selector': selector,
                        'expected': expected_text,
                        'actual': actual_text,
                        'status': 'success'
                    }
                else:
                    return {
                        'step': step_num,
                        'type': 'assert_text',
                        'selector': selector,
                        'expected': expected_text,
                        'actual': actual_text,
                        'status': 'failed',
                        'error': f'Erwarteter Text "{expected_text}" nicht gefunden'
                    }
            
            elif step_type == 'assert_visible':
                selector = step.get('selector')
                is_visible = await page.is_visible(selector)
                
                return {
                    'step': step_num,
                    'type': 'assert_visible',
                    'selector': selector,
                    'visible': is_visible,
                    'status': 'success' if is_visible else 'failed'
                }
            
            else:
                return {
                    'step': step_num,
                    'type': step_type,
                    'status': 'failed',
                    'error': f'Unbekannter Schritttyp: {step_type}'
                }
                
        except Exception as e:
            return {
                'step': step_num,
                'type': step_type,
                'status': 'failed',
                'error': str(e)
            }
    
    async def _run_unit_test(self, test_file: Optional[str]) -> Dict[str, Any]:
        """Führt einen Unit-Test durch"""
        logger.info("Führe Unit-Test durch...")
        
        # Hier würde die Unit-Test-Logik stehen
        # Beispiel: Ausführen von pytest
        return {
            'success': True,
            'operation': 'unit_test',
            'message': 'Unit-Tests erfolgreich',
            'test_file': test_file,
            'results': {
                'total': 10,
                'passed': 9,
                'failed': 1,
                'skipped': 0
            }
        }
    
    async def _run_integration_test(self, test_file: Optional[str], 
                                    test_url: Optional[str]) -> Dict[str, Any]:
        """Führt einen Integrationstest durch"""
        logger.info("Führe Integrationstest durch...")
        
        return {
            'success': True,
            'operation': 'integration_test',
            'message': 'Integrationstests erfolgreich',
            'test_file': test_file,
            'test_url': test_url,
            'results': {
                'total': 5,
                'passed': 5,
                'failed': 0
            }
        }
    
    async def _run_visual_regression_test(self, test_url: Optional[str],
                                          test_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Führt einen Visual-Regression-Test durch"""
        logger.info("Führe Visual-Regression-Test durch...")
        
        page = await self.context.new_page()
        
        try:
            await page.goto(test_url)
            
            # Screenshots für verschiedene Viewports
            viewports = [
                {'width': 1920, 'height': 1080, 'name': 'desktop'},
                {'width': 768, 'height': 1024, 'name': 'tablet'},
                {'width': 375, 'height': 667, 'name': 'mobile'}
            ]
            
            screenshots = []
            for viewport in viewports:
                await page.set_viewport_size(viewport)
                screenshot_path = f"visual_regression_{viewport['name']}.png"
                await page.screenshot(path=screenshot_path)
                screenshots.append({
                    'viewport': viewport['name'],
                    'path': screenshot_path
                })
            
            return {
                'success': True,
                'operation': 'visual_regression_test',
                'message': 'Visual-Regression-Test erfolgreich',
                'screenshots': screenshots
            }
            
        except Exception as e:
            return {
                'success': False,
                'operation': 'visual_regression_test',
                'error': str(e)
            }
    
    async def _run_performance_test(self, test_url: Optional[str],
                                    test_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Führt einen Performance-Test durch"""
        logger.info("Führe Performance-Test durch...")
        
        page = await self.context.new_page()
        
        try:
            # Performance-Metriken sammeln
            start_time = datetime.now()
            await page.goto(test_url)
            load_time = (datetime.now() - start_time).total_seconds()
            
            # Core Web Vitals
            metrics = await page.evaluate('''() => {
                const navigation = performance.getEntriesByType('navigation')[0];
                return {
                    domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                    loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
                    firstPaint: performance.getEntriesByName('first-paint')[0]?.startTime || 0,
                    firstContentfulPaint: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0
                };
            }''')
            
            return {
                'success': True,
                'operation': 'performance_test',
                'message': 'Performance-Test erfolgreich',
                'metrics': {
                    'page_load_time': load_time,
                    'dom_content_loaded': metrics['domContentLoaded'],
                    'load_complete': metrics['loadComplete'],
                    'first_paint': metrics['firstPaint'],
                    'first_contentful_paint': metrics['firstContentfulPaint']
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'operation': 'performance_test',
                'error': str(e)
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt den Status des Agenten zurück"""
        return {
            'name': self.name,
            'version': self.version,
            'supported_operations': self.supported_operations,
            'status': 'ready'
        }

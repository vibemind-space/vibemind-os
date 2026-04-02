"""
PlaywrightTestTools - Playwright-Tools für E2E-Tests.

Verantwortlichkeiten:
- E2E-Tests ausführen
- Screenshots aufnehmen
- Page-Metrics holen
- Visual-Regression-Tests durchführen
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class PlaywrightTestTools:
    """
    Playwright Test Tools - Bietet Funktionen für E2E-Testing.
    
    Verwendet Playwright CLI für Browser-Automatisierung.
    """
    
    def __init__(self, headless: bool = True, browser: str = "chromium"):
        self.headless = headless
        self.browser = browser
        self.logger = logger.bind(
            component="playwright_test_tools",
            headless=headless,
            browser=browser,
        )
    
    async def run_e2e_test(
        self,
        test_file: str,
        headless: bool = None,
    ) -> Dict[str, Any]:
        """
        Führt einen E2E-Test aus.
        
        Args:
            test_file: Pfad zur Test-Datei
            headless: Ob headless Modus verwendet werden soll
            
        Returns:
            Dict mit success, result, metadata
        """
        self.logger.info(
            "running_e2e_test",
            test_file=test_file,
            headless=headless if headless is not None else self.headless,
        )
        
        try:
            # Playwright test command
            cmd = ["npx", "playwright", "test"]
            
            if headless is not None:
                if headless:
                    cmd.append("--headed")
                else:
                    cmd.append("--headless")
            
            cmd.append(test_file)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                
                # Test-Ergebnis parsen
                test_result = self._parse_test_output(output)
                
                return {
                    "success": True,
                    "result": test_result,
                    "test_file": test_file,
                    "headless": headless if headless is not None else self.headless,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "test_file": test_file,
                }
                
        except Exception as e:
            self.logger.error(
                "run_e2e_test_failed",
                test_file=test_file,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "test_file": test_file,
            }
    
    def _parse_test_output(self, output: str) -> Dict[str, Any]:
        """
        Parst Playwright Test-Output.
        
        Args:
            output: Test-Output als String
            
        Returns:
            Geparstes Test-Ergebnis
        """
        result = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration_ms": 0,
            "tests": [],
        }
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Test-Status parsen
            if "✓" in line or "PASS" in line or "passed" in line.lower():
                result["passed"] += 1
            elif "✗" in line or "FAIL" in line or "failed" in line.lower():
                result["failed"] += 1
            elif "⊘" in line or "SKIP" in line or "skipped" in line.lower():
                result["skipped"] += 1
            
            # Test-Name extrahieren
            if "›" in line or "should" in line.lower():
                test_name = line.strip()
                result["tests"].append({
                    "name": test_name,
                    "status": "passed" if "✓" in line or "PASS" in line else "failed" if "✗" in line or "FAIL" in line else "skipped",
                "line": line,
                })
        
        # Duration extrahieren
        for line in lines:
            if "Duration:" in line or "Time:" in line:
                try:
                    duration_str = line.split(":")[-1].strip().replace("ms", "").replace("s", "").strip()
                    result["duration_ms"] = int(float(duration_str) * 1000) if duration_str.replace('.', '').isdigit() else 0
                    break
                except:
                    pass
        
        return result
    
    async def capture_screenshot(
        self,
        url: str,
        selector: Optional[str] = None,
        full_page: bool = False,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Captures einen Screenshot.
        
        Args:
            url: URL der Seite
            selector: Optionaler CSS-Selector
            full_page: Ob ganze Seite aufgenommen werden soll
            output_path: Optionaler Ausgabepfad
            
        Returns:
            Dict mit success, screenshot_path, metadata
        """
        self.logger.info(
            "capturing_screenshot",
            url=url,
            selector=selector,
            full_page=full_page,
        )
        
        try:
            # Playwright screenshot command
            cmd = ["npx", "playwright", "screenshot"]
            
            if full_page:
                cmd.append("--full-page")
            
            if selector:
                cmd.extend(["--selector", selector])
            
            cmd.append(url)
            
            if output_path:
                cmd.extend(["-o", output_path])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace').strip()
                
                # Output-Pfad extrahieren
                screenshot_path = output_path or output.split("saved to ")[-1].strip() if "saved to " in output else output
                
                return {
                    "success": True,
                    "screenshot_path": screenshot_path,
                    "url": url,
                    "selector": selector,
                    "full_page": full_page,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "url": url,
                }
                
        except Exception as e:
            self.logger.error(
                "capture_screenshot_failed",
                url=url,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "url": url,
            }
    
    async def get_page_metrics(
        self,
        url: str,
        wait_for: str = "load",
    ) -> Dict[str, Any]:
        """
        Holt Page-Metrics (LCP, FID, CLS).
        
        Args:
            url: URL der Seite
            wait_for: Worauf gewartet werden soll (z.B. "load", "networkidle")
            
        Returns:
            Dict mit success, metrics, metadata
        """
        self.logger.info(
            "getting_page_metrics",
            url=url,
            wait_for=wait_for,
        )
        
        try:
            # Playwright metrics command
            cmd = ["npx", "playwright", "show-metrics"]
            
            cmd.extend(["--wait-for", wait_for])
            cmd.append(url)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                
                # Metrics parsen
                metrics = self._parse_metrics(output)
                
                return {
                    "success": True,
                    "metrics": metrics,
                    "url": url,
                    "wait_for": wait_for,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "url": url,
                }
                
        except Exception as e:
            self.logger.error(
                "get_page_metrics_failed",
                url=url,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "url": url,
            }
    
    def _parse_metrics(self, output: str) -> Dict[str, Any]:
        """
        Parst Page-Metrics.
        
        Args:
            output: Metrics-Output als String
            
        Returns:
            Geparste Metrics
        """
        metrics = {
            "lcp_ms": 0,
            "fid_ms": 0,
            "cls_ms": 0,
            "fcp_ms": 0,
            "ttfb_ms": 0,
            "tbt_ms": 0,
        }
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # LCP (Largest Contentful Paint)
            if "LCP:" in line:
                try:
                    lcp_str = line.split(":")[-1].strip().replace("ms", "").strip()
                    metrics["lcp_ms"] = int(float(lcp_str) * 1000) if lcp_str.replace('.', '').isdigit() else 0
                except:
                    pass
            
            # FID (First Input Delay)
            elif "FID:" in line:
                try:
                    fid_str = line.split(":")[-1].strip().replace("ms", "").strip()
                    metrics["fid_ms"] = int(float(fid_str) * 1000) if fid_str.replace('.', '').isdigit() else 0
                except:
                    pass
            
            # CLS (Cumulative Layout Shift)
            elif "CLS:" in line:
                try:
                    cls_str = line.split(":")[-1].strip().replace("ms", "").strip()
                    metrics["cls_ms"] = int(float(cls_str) * 1000) if cls_str.replace('.', '').isdigit() else 0
                except:
                    pass
            
            # FCP (First Contentful Paint)
            elif "FCP:" in line:
                try:
                    fcp_str = line.split(":")[-1].strip().replace("ms", "").strip()
                    metrics["fcp_ms"] = int(float(fcp_str) * 1000) if fcp_str.replace('.', '').isdigit() else 0
                except:
                    pass
            
            # TTFB (Time to First Byte)
            elif "TTFB:" in line:
                try:
                    ttfb_str = line.split(":")[-1].strip().replace("ms", "").strip()
                    metrics["ttfb_ms"] = int(float(ttfb_str) * 1000) if ttfb_str.replace('.', '').isdigit() else 0
                except:
                    pass
            
            # TBT (Total Blocking Time)
            elif "TBT:" in line:
                try:
                    tbt_str = line.split(":")[-1].strip().replace("ms", "").strip()
                    metrics["tbt_ms"] = int(float(tbt_str) * 1000) if tbt_str.replace('.', '').isdigit() else 0
                except:
                    pass
        
        return metrics
    
    async def run_visual_regression_test(
        self,
        baseline_screenshot: str,
        current_screenshot: str,
        comparison_type: str = "pixelmatch",
    ) -> Dict[str, Any]:
        """
        Führt einen Visual-Regression-Test durch.
        
        Args:
            baseline_screenshot: Pfad zum Baseline-Screenshot
            current_screenshot: Pfad zum aktuellen Screenshot
            comparison_type: Vergleichstyp (pixelmatch, layout, content)
            
        Returns:
            Dict mit success, result, metadata
        """
        self.logger.info(
            "running_visual_regression_test",
            baseline=baseline_screenshot,
            current=current_screenshot,
            comparison_type=comparison_type,
        )
        
        try:
            # Playwright visual regression command
            cmd = ["npx", "playwright", "test"]
            
            cmd.extend(["--compare", baseline_screenshot, current_screenshot])
            cmd.extend(["--comparison", comparison_type])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                
                # Ergebnis parsen
                result = self._parse_visual_regression_output(output)
                
                return {
                    "success": True,
                    "result": result,
                    "baseline": baseline_screenshot,
                    "current": current_screenshot,
                    "comparison_type": comparison_type,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "baseline": baseline_screenshot,
                    "current": current_screenshot,
                }
                
        except Exception as e:
            self.logger.error(
                "run_visual_regression_test_failed",
                baseline=baseline_screenshot,
                current=current_screenshot,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "baseline": baseline_screenshot,
                "current": current_screenshot,
            }
    
    def _parse_visual_regression_output(self, output: str) -> Dict[str, Any]:
        """
        Parst Visual-Regression-Test-Output.
        
        Args:
            output: Test-Output als String
            
        Returns:
            Geparstes Test-Ergebnis
        """
        result = {
            "passed": False,
            "diff_pixels": 0,
            "diff_percentage": 0.0,
            "mismatched_regions": [],
        }
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Status parsen
            if "PASS" in line or "passed" in line.lower():
                result["passed"] = True
            elif "FAIL" in line or "failed" in line.lower():
                result["passed"] = False
            
            # Diff-Pixel parsen
            if "diff pixels:" in line.lower():
                try:
                    diff_str = line.split(":")[-1].strip()
                    result["diff_pixels"] = int(diff_str.replace(",", "").strip())
                except:
                    pass
            
            # Diff-Percentage parsen
            if "diff percentage:" in line.lower():
                try:
                    diff_pct_str = line.split(":")[-1].strip().replace("%", "").strip()
                    result["diff_percentage"] = float(diff_pct_str) / 100.0
                except:
                    pass
            
            # Mismatched Regions parsen
            if "mismatched regions:" in line.lower():
                try:
                    regions_str = line.split(":")[-1].strip()
                    result["mismatched_regions"] = regions_str.split(",")
                except:
                    pass
        
        return result
    
    async def get_test_coverage(
        self,
        test_files: List[str],
    ) -> Dict[str, Any]:
        """
        Holt Test-Coverage.
        
        Args:
            test_files: Liste von Test-Dateien
            
        Returns:
            Dict mit success, coverage, metadata
        """
        self.logger.info(
            "getting_test_coverage",
            files=len(test_files),
        )
        
        try:
            # Playwright coverage command
            cmd = ["npx", "playwright", "test", "--coverage"]
            
            for test_file in test_files:
                cmd.append(test_file)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                
                # Coverage parsen
                coverage = self._parse_coverage_output(output)
                
                return {
                    "success": True,
                    "coverage": coverage,
                    "test_files": test_files,
                }
            else:
                error = stderr.decode('utf-8', errors='replace')
                return {
                    "success": False,
                    "error": error,
                    "test_files": test_files,
                }
                
        except Exception as e:
            self.logger.error(
                "get_test_coverage_failed",
                files=len(test_files),
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "test_files": test_files,
            }
    
    def _parse_coverage_output(self, output: str) -> Dict[str, Any]:
        """
        Parst Coverage-Output.
        
        Args:
            output: Coverage-Output als String
            
        Returns:
            Geparste Coverage
        """
        coverage = {
            "total_lines": 0,
            "covered_lines": 0,
            "coverage_percent": 0.0,
            "files": [],
        }
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Total Lines parsen
            if "total lines:" in line.lower():
                try:
                    total_str = line.split(":")[-1].strip()
                    coverage["total_lines"] = int(total_str.replace(",", "").strip())
                except:
                    pass
            
            # Covered Lines parsen
            elif "covered lines:" in line.lower():
                try:
                    covered_str = line.split(":")[-1].strip()
                    coverage["covered_lines"] = int(covered_str.replace(",", "").strip())
                except:
                    pass
            
            # Coverage-Percentage parsen
            elif "coverage:" in line.lower():
                try:
                    coverage_str = line.split(":")[-1].strip().replace("%", "").strip()
                    coverage["coverage_percent"] = float(coverage_str) / 100.0
                except:
                    pass
            
            # File-Informationen parsen
            if "file:" in line.lower():
                file_info = line.split(":", 1)[-1].strip()
                coverage["files"].append(file_info)
        
        # Coverage-Percentage berechnen
        if coverage["total_lines"] > 0:
            coverage["coverage_percent"] = (coverage["covered_lines"] / coverage["total_lines"] * 100)
        
        return coverage

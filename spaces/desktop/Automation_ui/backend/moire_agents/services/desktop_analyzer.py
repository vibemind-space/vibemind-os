"""
Desktop Analyzer Service - DataFrame Export für UI-Analyse

Kombiniert:
- MoireServer Detection + OCR (WebSocket :8765)
- LLM Classification für semantische Namen (HTTP Bridge :8766)
- Pandas DataFrame mit exakten Bezeichnungen

Beispiel-Output:
| element_id | name           | category | ocr_text | x   | y   | width | height | confidence |
|------------|----------------|----------|----------|-----|-----|-------|--------|------------|
| box_0      | Chrome Browser | browser  |          | 50  | 100 | 32    | 32     | 0.95       |
| box_1      | VS Code Editor | editor   |          | 100 | 100 | 32    | 32     | 0.92       |

Usage:
    from services.desktop_analyzer import DesktopAnalyzer
    
    analyzer = DesktopAnalyzer()
    df = await analyzer.scan_and_analyze()
    df.to_csv("desktop_elements.csv")
"""

import asyncio
import aiohttp
import json
import logging
import os
import sys
import base64
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Add parent path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Pandas für DataFrame
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("WARNING: pandas not installed. Run: pip install pandas")

# AgentDataFrame import
try:
    from services.agent_dataframe import AgentDataFrame, make_agent_df
    HAS_AGENT_DF = True
except ImportError:
    HAS_AGENT_DF = False

# PIL für Screenshots
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# WebSocket Client
from bridge.websocket_client import MoireWebSocketClient, UIElement, UIContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AnalyzedElement:
    """Ein analysiertes UI-Element mit semantischem Namen."""
    element_id: str
    name: str  # Semantischer Name (z.B. "Chrome Browser")
    category: str  # Kategorie (z.B. "browser")
    ocr_text: Optional[str]
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    confidence: float
    llm_reasoning: Optional[str] = None
    crop_base64: Optional[str] = None


@dataclass
class AnalysisResult:
    """Ergebnis der Desktop-Analyse."""
    success: bool
    elements: List[AnalyzedElement]
    total_elements: int
    named_elements: int
    processing_time_ms: float
    screenshot_base64: Optional[str] = None
    error: Optional[str] = None
    
    def to_dataframe(self) -> 'pd.DataFrame':
        """Konvertiert zu Pandas DataFrame."""
        if not HAS_PANDAS:
            raise ImportError("pandas not installed")
        
        data = []
        for elem in self.elements:
            data.append({
                'element_id': elem.element_id,
                'name': elem.name,
                'category': elem.category,
                'ocr_text': elem.ocr_text or '',
                'x': elem.x,
                'y': elem.y,
                'width': elem.width,
                'height': elem.height,
                'center_x': elem.center_x,
                'center_y': elem.center_y,
                'confidence': elem.confidence
            })
        
        return pd.DataFrame(data)
    
    def to_agent_dataframe(self) -> 'AgentDataFrame':
        """
        Konvertiert zu AgentDataFrame mit schnellen Lookup-Indizes.
        
        Returns:
            AgentDataFrame für Desktop Automation Agents
        """
        if not HAS_PANDAS:
            raise ImportError("pandas not installed")
        if not HAS_AGENT_DF:
            raise ImportError("AgentDataFrame not available")
        
        df = self.to_dataframe()
        return make_agent_df(df)


class DesktopAnalyzer:
    """
    Desktop Analyzer - Scannt Desktop und erstellt DataFrame mit semantischen Namen.
    
    Verbindet sich zu:
    - MoireServer (:8765) für Detection + OCR
    - HTTP Bridge (:8766) für LLM Classification
    """
    
    def __init__(
        self,
        moire_host: str = "localhost",
        moire_port: int = 8765,
        bridge_host: str = "localhost",
        bridge_port: int = 8766,
        batch_size: int = 10
    ):
        self.moire_host = moire_host
        self.moire_port = moire_port
        self.bridge_url = f"http://{bridge_host}:{bridge_port}"
        self.batch_size = batch_size
        
        self.moire_client: Optional[MoireWebSocketClient] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"DesktopAnalyzer initialisiert")
        logger.info(f"  MoireServer: ws://{moire_host}:{moire_port}")
        logger.info(f"  HTTP Bridge: {self.bridge_url}")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, *args):
        await self.disconnect()
    
    async def connect(self) -> bool:
        """Verbindet zu MoireServer und erstellt HTTP Session."""
        try:
            # WebSocket Client
            self.moire_client = MoireWebSocketClient(
                host=self.moire_host,
                port=self.moire_port
            )
            connected = await self.moire_client.connect()
            
            if not connected:
                logger.error("MoireServer nicht erreichbar!")
                return False
            
            logger.info("✓ MoireServer verbunden")
            
            # HTTP Session für Bridge
            self._session = aiohttp.ClientSession()
            
            # Test Bridge Connection
            async with self._session.get(f"{self.bridge_url}/status") as resp:
                if resp.status == 200:
                    logger.info("✓ HTTP Bridge verbunden")
                else:
                    logger.warning("HTTP Bridge nicht erreichbar - nur OCR, keine LLM Names")
            
            return True
            
        except Exception as e:
            logger.error(f"Verbindungsfehler: {e}")
            return False
    
    async def disconnect(self):
        """Trennt Verbindungen."""
        if self.moire_client:
            await self.moire_client.disconnect()
        if self._session:
            await self._session.close()
    
    async def scan_and_analyze(
        self,
        use_llm_names: bool = True,
        timeout: float = 120.0
    ) -> AnalysisResult:
        """
        Scannt Desktop und analysiert alle UI-Elemente.
        
        Args:
            use_llm_names: Ob LLM für semantische Namen verwendet werden soll
            timeout: Timeout für Detection + OCR
            
        Returns:
            AnalysisResult mit allen Elementen und DataFrame
        """
        start_time = asyncio.get_event_loop().time()
        
        if not self.moire_client:
            return AnalysisResult(
                success=False,
                elements=[],
                total_elements=0,
                named_elements=0,
                processing_time_ms=0,
                error="Nicht verbunden - zuerst connect() aufrufen"
            )
        
        # 1. Capture Desktop mit Detection + OCR
        logger.info("📸 Capture Desktop...")
        capture_result = await self.moire_client.capture_and_wait_for_complete(
            timeout=timeout
        )
        
        if not capture_result.success:
            return AnalysisResult(
                success=False,
                elements=[],
                total_elements=0,
                named_elements=0,
                processing_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                error=f"Capture fehlgeschlagen: {capture_result.error}"
            )
        
        logger.info(f"✓ {capture_result.boxes_count} Elemente erkannt, {capture_result.texts_count} mit OCR")
        
        # 2. Extrahiere UI-Elemente
        ui_context = capture_result.ui_context
        screenshot_base64 = capture_result.screenshot_base64
        
        elements: List[AnalyzedElement] = []
        
        for ui_elem in ui_context.elements:
            # Erstelle Basis-Element
            elem = AnalyzedElement(
                element_id=ui_elem.id,
                name=ui_elem.text or f"Element_{ui_elem.id}",  # Fallback
                category=ui_elem.category or "unknown",
                ocr_text=ui_elem.text,
                x=ui_elem.bounds.get('x', 0),
                y=ui_elem.bounds.get('y', 0),
                width=ui_elem.bounds.get('width', 0),
                height=ui_elem.bounds.get('height', 0),
                center_x=ui_elem.center.get('x', 0),
                center_y=ui_elem.center.get('y', 0),
                confidence=ui_elem.confidence
            )
            elements.append(elem)
        
        # 3. LLM Classification für semantische Namen
        if use_llm_names and self._session:
            logger.info("🧠 LLM Classification für semantische Namen...")
            elements = await self._classify_elements_with_llm(
                elements,
                screenshot_base64
            )
        
        processing_time = (asyncio.get_event_loop().time() - start_time) * 1000
        named_count = sum(1 for e in elements if e.name != f"Element_{e.element_id}")
        
        logger.info(f"✓ Analyse abgeschlossen: {len(elements)} Elemente, {named_count} benannt")
        
        return AnalysisResult(
            success=True,
            elements=elements,
            total_elements=len(elements),
            named_elements=named_count,
            processing_time_ms=processing_time,
            screenshot_base64=screenshot_base64
        )
    
    async def _classify_elements_with_llm(
        self,
        elements: List[AnalyzedElement],
        screenshot_base64: Optional[str]
    ) -> List[AnalyzedElement]:
        """Klassifiziert Elemente mit LLM für semantische Namen."""
        if not self._session:
            return elements
        
        # Extrahiere Crops und sende an HTTP Bridge
        batch_icons = []
        element_map = {}
        
        for elem in elements:
            # Crop extrahieren wenn Screenshot vorhanden
            crop_base64 = None
            if screenshot_base64 and HAS_PIL:
                crop_base64 = self._extract_crop(
                    screenshot_base64,
                    elem.x, elem.y, elem.width, elem.height
                )
            
            batch_icons.append({
                "boxId": elem.element_id,
                "cropBase64": crop_base64 or "",
                "cnnCategory": elem.category,
                "cnnConfidence": elem.confidence,
                "ocrText": elem.ocr_text
            })
            element_map[elem.element_id] = elem
        
        # Sende in Batches zur HTTP Bridge
        for i in range(0, len(batch_icons), self.batch_size):
            batch = batch_icons[i:i + self.batch_size]
            
            try:
                async with self._session.post(
                    f"{self.bridge_url}/classify_batch",
                    json={
                        "batchId": f"desktop_scan_{datetime.now().strftime('%H%M%S')}_{i}",
                        "icons": batch
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        for result in data.get("results", []):
                            box_id = result.get("boxId")
                            if box_id in element_map:
                                elem = element_map[box_id]
                                
                                # Get semantic name from LLM response (NEW!)
                                semantic_name = result.get("semanticName")
                                llm_category = result.get("llmCategory", "unknown")
                                final_category = result.get("finalCategory", elem.category)
                                reasoning = result.get("validationReasoning", "")
                                
                                # Use semantic_name from LLM if available
                                if semantic_name:
                                    elem.name = semantic_name
                                else:
                                    # Fallback: Generate semantic name
                                    elem.name = self._generate_semantic_name(
                                        llm_category=llm_category,
                                        ocr_text=elem.ocr_text,
                                        category=final_category
                                    )
                                
                                elem.category = final_category
                                elem.llm_reasoning = reasoning
                        
                        logger.info(f"  Batch {i//self.batch_size + 1}: {len(batch)} klassifiziert")
                    else:
                        logger.warning(f"  Batch {i//self.batch_size + 1} fehlgeschlagen: {resp.status}")
                        
            except Exception as e:
                logger.error(f"  LLM Batch Fehler: {e}")
        
        return elements
    
    def _generate_semantic_name(
        self,
        llm_category: str,
        ocr_text: Optional[str],
        category: str
    ) -> str:
        """Generiert einen semantischen Namen aus LLM-Ergebnis und OCR."""
        # Wenn OCR Text vorhanden, benutze ihn
        if ocr_text and len(ocr_text) > 1:
            # Kombiniere mit Kategorie für Klarheit
            return f"{ocr_text} ({category})"
        
        # Bekannte Icon-Namen mapping
        icon_names = {
            "chrome": "Chrome Browser",
            "google_chrome": "Chrome Browser",
            "firefox": "Firefox Browser",
            "edge": "Microsoft Edge",
            "vscode": "VS Code Editor",
            "visual_studio_code": "VS Code Editor",
            "explorer": "File Explorer",
            "file_explorer": "File Explorer",
            "recycle_bin": "Recycle Bin",
            "trash": "Recycle Bin",
            "settings": "Windows Settings",
            "control_panel": "Control Panel",
            "cmd": "Command Prompt",
            "terminal": "Terminal",
            "powershell": "PowerShell",
            "notepad": "Notepad",
            "word": "Microsoft Word",
            "excel": "Microsoft Excel",
            "outlook": "Microsoft Outlook",
            "teams": "Microsoft Teams",
            "slack": "Slack",
            "discord": "Discord",
            "spotify": "Spotify",
            "steam": "Steam",
            "button": "Button",
            "text_field": "Text Field",
            "checkbox": "Checkbox",
            "radio_button": "Radio Button",
            "dropdown": "Dropdown Menu",
            "menu_item": "Menu Item",
            "icon": "Application Icon",
            "system_tray": "System Tray Icon",
            "taskbar": "Taskbar Item"
        }
        
        # Suche nach bekanntem Namen
        llm_lower = llm_category.lower().replace(" ", "_")
        for key, name in icon_names.items():
            if key in llm_lower or llm_lower in key:
                return name
        
        # Fallback: Formatiere Kategorie als Name
        return llm_category.replace("_", " ").title()
    
    def _extract_crop(
        self,
        screenshot_base64: str,
        x: int, y: int, width: int, height: int
    ) -> Optional[str]:
        """Extrahiert einen Crop aus dem Screenshot."""
        if not HAS_PIL:
            return None
        
        try:
            # Decode base64
            if screenshot_base64.startswith('data:'):
                _, data = screenshot_base64.split(',', 1)
            else:
                data = screenshot_base64
            
            image_bytes = base64.b64decode(data)
            image = Image.open(BytesIO(image_bytes))
            
            # Crop extrahieren (mit Padding)
            padding = 2
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(image.width, x + width + padding)
            y2 = min(image.height, y + height + padding)
            
            crop = image.crop((x1, y1, x2, y2))
            
            # Encode zurück zu base64
            buffer = BytesIO()
            crop.save(buffer, format='PNG')
            crop_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return crop_base64
            
        except Exception as e:
            logger.debug(f"Crop extraction failed: {e}")
            return None
    
    async def quick_scan(self) -> 'pd.DataFrame':
        """
        Schneller Scan ohne LLM - nur Detection + OCR.
        
        Returns:
            Pandas DataFrame mit Basis-Informationen
        """
        result = await self.scan_and_analyze(use_llm_names=False)
        return result.to_dataframe()
    
    async def full_scan(self) -> 'pd.DataFrame':
        """
        Vollständiger Scan mit LLM für semantische Namen.
        
        Returns:
            Pandas DataFrame mit semantischen Namen
        """
        result = await self.scan_and_analyze(use_llm_names=True)
        return result.to_dataframe()


# ==================== Standalone Functions ====================

async def scan_desktop_to_dataframe(
    use_llm: bool = True,
    output_csv: Optional[str] = None,
    output_json: Optional[str] = None
) -> 'pd.DataFrame':
    """
    Convenience-Funktion: Scannt Desktop und gibt DataFrame zurück.
    
    Args:
        use_llm: Ob LLM für semantische Namen verwendet werden soll
        output_csv: Optional - Pfad für CSV Export
        output_json: Optional - Pfad für JSON Export
        
    Returns:
        Pandas DataFrame mit allen UI-Elementen
    """
    async with DesktopAnalyzer() as analyzer:
        result = await analyzer.scan_and_analyze(use_llm_names=use_llm)
        
        if not result.success:
            logger.error(f"Scan fehlgeschlagen: {result.error}")
            return pd.DataFrame()
        
        df = result.to_dataframe()
        
        # Export
        if output_csv:
            df.to_csv(output_csv, index=False)
            logger.info(f"✓ CSV exportiert: {output_csv}")
        
        if output_json:
            df.to_json(output_json, orient='records', indent=2)
            logger.info(f"✓ JSON exportiert: {output_json}")
        
        return df


async def main():
    """Test-Funktion."""
    print("\n" + "="*60)
    print("Desktop Analyzer - DataFrame Export")
    print("="*60 + "\n")
    
    # Prüfe ob pandas installiert ist
    if not HAS_PANDAS:
        print("FEHLER: pandas nicht installiert!")
        print("Installieren mit: pip install pandas")
        return
    
    try:
        async with DesktopAnalyzer() as analyzer:
            print("Starte Desktop-Scan...")
            
            # Vollständiger Scan mit LLM
            result = await analyzer.scan_and_analyze(use_llm_names=True)
            
            if result.success:
                df = result.to_dataframe()
                
                print(f"\n{'='*60}")
                print(f"ERGEBNIS: {result.total_elements} Elemente, {result.named_elements} benannt")
                print(f"Zeit: {result.processing_time_ms:.0f}ms")
                print(f"{'='*60}\n")
                
                # Zeige DataFrame
                print("DataFrame Preview:")
                print(df.to_string(max_rows=20))
                
                # Export
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = f"desktop_analysis_{timestamp}.csv"
                df.to_csv(csv_path, index=False)
                print(f"\n✓ Exportiert: {csv_path}")
                
            else:
                print(f"FEHLER: {result.error}")
                
    except Exception as e:
        print(f"Fehler: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
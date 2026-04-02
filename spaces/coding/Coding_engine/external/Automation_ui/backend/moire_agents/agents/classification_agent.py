"""
Classification Validation Agent - LLM-basierte Validierung von CNN-Klassifizierungen

Dieser Agent:
1. Erhält unsichere UI-Element-Crops vom MoireServer
2. Verwendet ein LLM (via OpenRouter) um die Klassifizierung zu validieren
3. Korrigiert oder bestätigt die Kategorie
4. Sendet das Ergebnis zurück zum DatasetManager
"""

import asyncio
import base64
import logging
import os
import sys
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.openrouter_client import OpenRouterClient, get_openrouter_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# UI Categories matching TypeScript
UI_CATEGORIES = [
    'button', 'icon', 'input', 'text', 'image',
    'checkbox', 'radio', 'dropdown', 'link',
    'container', 'header', 'footer', 'menu', 'toolbar', 'unknown'
]

CLASSIFICATION_SYSTEM_PROMPT = """You are a UI element classifier. Your task is to identify what type of UI element is shown in an image.

Available categories:
- button: Clickable buttons, submit buttons, action buttons
- icon: Small graphical symbols, icons, emojis
- input: Text input fields, search boxes, text areas
- text: Static text, labels, paragraphs
- image: Photos, pictures, large graphics
- checkbox: Checkboxes, toggle switches
- radio: Radio buttons
- dropdown: Dropdown menus, select boxes, combo boxes
- link: Hyperlinks, clickable text links
- container: Panels, cards, grouping elements
- header: Page headers, title bars
- footer: Page footers
- menu: Navigation menus, menu bars
- toolbar: Toolbars, button bars
- unknown: Cannot determine the type

Respond with ONLY the category name, nothing else."""


@dataclass
class ClassificationResult:
    """Ergebnis einer Klassifizierungs-Validierung."""
    box_id: str
    original_category: str
    validated_category: str
    confidence: float
    is_correction: bool
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class UncertainElement:
    """Ein unsicheres Element zur Validierung."""
    box_id: str
    suggested_category: str
    confidence: float
    crop_path: str
    text: Optional[str] = None


class ClassificationValidationAgent:
    """
    Agent der CNN-Klassifizierungen mit LLM validiert.
    
    Workflow:
    1. Erhält UncertainElement mit Crop-Bild
    2. Sendet Bild an LLM zur Klassifizierung
    3. Vergleicht LLM-Antwort mit CNN-Vorschlag
    4. Gibt validiertes/korrigiertes Ergebnis zurück
    """
    
    def __init__(
        self,
        model: str = "google/gemini-2.0-flash-001",
        max_concurrent: int = 5
    ):
        self.model = model
        self.max_concurrent = max_concurrent
        self.openrouter_client: Optional[OpenRouterClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        
        # Statistics
        self.stats = {
            'total_validated': 0,
            'corrections': 0,
            'confirmations': 0,
            'errors': 0
        }
    
    async def initialize(self) -> bool:
        """Initialisiert den OpenRouter Client."""
        try:
            self.openrouter_client = get_openrouter_client()
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
            logger.info(f"[ClassificationAgent] Initialized with model: {self.model}")
            return True
        except Exception as e:
            logger.error(f"[ClassificationAgent] Init failed: {e}")
            return False
    
    async def validate_classification(
        self,
        element: UncertainElement
    ) -> ClassificationResult:
        """
        Validiert eine einzelne CNN-Klassifizierung mit LLM.
        """
        if not self.openrouter_client:
            await self.initialize()
        
        async with self._semaphore:
            try:
                # Load and encode crop image
                image_base64 = self._load_image_base64(element.crop_path)
                if not image_base64:
                    return self._create_error_result(element, "Failed to load image")
                
                # Call LLM with image
                llm_category = await self._classify_with_llm(image_base64, element.text)
                
                # Compare with CNN suggestion
                is_correction = llm_category != element.suggested_category
                
                # Determine final category
                if llm_category in UI_CATEGORIES:
                    validated_category = llm_category
                else:
                    validated_category = element.suggested_category
                    is_correction = False
                
                # Update stats
                self.stats['total_validated'] += 1
                if is_correction:
                    self.stats['corrections'] += 1
                else:
                    self.stats['confirmations'] += 1
                
                reasoning = f"LLM: {llm_category}, CNN: {element.suggested_category}"
                if is_correction:
                    reasoning = f"CORRECTED: CNN said '{element.suggested_category}', LLM validated as '{llm_category}'"
                else:
                    reasoning = f"CONFIRMED: Both CNN and LLM agree on '{validated_category}'"
                
                logger.info(f"[ClassificationAgent] {element.box_id}: {reasoning}")
                
                return ClassificationResult(
                    box_id=element.box_id,
                    original_category=element.suggested_category,
                    validated_category=validated_category,
                    confidence=1.0 if not is_correction else 0.9,
                    is_correction=is_correction,
                    reasoning=reasoning
                )
                
            except Exception as e:
                logger.error(f"[ClassificationAgent] Validation failed for {element.box_id}: {e}")
                self.stats['errors'] += 1
                return self._create_error_result(element, str(e))
    
    async def validate_batch(
        self,
        elements: List[UncertainElement]
    ) -> List[ClassificationResult]:
        """
        Validiert mehrere Elemente parallel.
        """
        if not elements:
            return []
        
        logger.info(f"[ClassificationAgent] Validating batch of {len(elements)} elements...")
        
        tasks = [self.validate_classification(elem) for elem in elements]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[ClassificationAgent] Batch item {i} failed: {result}")
                valid_results.append(self._create_error_result(
                    elements[i],
                    str(result)
                ))
            else:
                valid_results.append(result)
        
        corrections = sum(1 for r in valid_results if r.is_correction)
        logger.info(f"[ClassificationAgent] Batch complete: {corrections} corrections, {len(valid_results) - corrections} confirmations")
        
        return valid_results
    
    async def _classify_with_llm(
        self,
        image_base64: str,
        context_text: Optional[str] = None
    ) -> str:
        """Ruft LLM auf um Bild zu klassifizieren."""
        
        user_content = []
        
        # Add context if available
        if context_text:
            user_content.append({
                "type": "text",
                "text": f"The element contains the text: '{context_text}'\nWhat type of UI element is this?"
            })
        else:
            user_content.append({
                "type": "text",
                "text": "What type of UI element is shown in this image?"
            })
        
        # Add image
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_base64}",
                "detail": "low"
            }
        })
        
        response = await self.openrouter_client.chat(
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            model=self.model
        )
        
        if response and response.content:
            # Extract category from response
            category = response.content.strip().lower()
            
            # Clean up response (sometimes LLM adds extra text)
            for cat in UI_CATEGORIES:
                if cat in category:
                    return cat
            
            return category if category in UI_CATEGORIES else 'unknown'
        
        return 'unknown'
    
    def _load_image_base64(self, path: str) -> Optional[str]:
        """Lädt Bild und gibt Base64 zurück."""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                logger.error(f"[ClassificationAgent] Image not found: {path}")
                return None
            
            with open(path_obj, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"[ClassificationAgent] Failed to load image {path}: {e}")
            return None
    
    def _create_error_result(
        self,
        element: UncertainElement,
        error: str
    ) -> ClassificationResult:
        """Erstellt Error-Ergebnis."""
        return ClassificationResult(
            box_id=element.box_id,
            original_category=element.suggested_category,
            validated_category=element.suggested_category,  # Keep original on error
            confidence=element.confidence,
            is_correction=False,
            reasoning=f"ERROR: {error}"
        )
    
    def get_stats(self) -> Dict[str, int]:
        """Gibt Statistiken zurück."""
        return dict(self.stats)
    
    def reset_stats(self) -> None:
        """Setzt Statistiken zurück."""
        self.stats = {
            'total_validated': 0,
            'corrections': 0,
            'confirmations': 0,
            'errors': 0
        }


# ==================== Standalone Runner ====================

async def validate_uncertain_from_server(
    server_url: str = "ws://localhost:8765"
) -> None:
    """
    Verbindet zum MoireServer und validiert unsichere Elemente.
    """
    from bridge.websocket_client import MoireWebSocketClient
    
    agent = ClassificationValidationAgent()
    await agent.initialize()
    
    client = MoireWebSocketClient(host="localhost", port=8765)
    await client.connect()
    
    logger.info("[ClassificationAgent] Connected to MoireServer")
    
    # Request uncertain elements
    # Note: This requires MoireServer to implement the endpoint
    await client.send_message({
        "type": "get_uncertain_elements",
        "limit": 10
    })
    
    # In a real implementation, we'd listen for the response
    # and process elements as they come in
    
    await client.disconnect()


async def main():
    """Test-Funktion."""
    agent = ClassificationValidationAgent()
    await agent.initialize()
    
    # Test mit einem Beispiel-Element
    test_element = UncertainElement(
        box_id="test_001",
        suggested_category="button",
        confidence=0.65,
        crop_path="./detection_results/crops/test.png",
        text="OK"
    )
    
    # Check if test image exists
    if not os.path.exists(test_element.crop_path):
        logger.warning(f"Test image not found: {test_element.crop_path}")
        logger.info("Run detection first to generate crops")
        return
    
    result = await agent.validate_classification(test_element)
    
    print(f"\nValidation Result:")
    print(f"  Box ID: {result.box_id}")
    print(f"  Original: {result.original_category}")
    print(f"  Validated: {result.validated_category}")
    print(f"  Is Correction: {result.is_correction}")
    print(f"  Reasoning: {result.reasoning}")
    
    print(f"\nStats: {agent.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
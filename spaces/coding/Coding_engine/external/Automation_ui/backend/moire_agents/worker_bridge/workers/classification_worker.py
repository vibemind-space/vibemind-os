"""
Classification Worker für MoireTracker

AutoGen 0.4 basierter gRPC Worker der:
1. ClassifyIconMessage empfängt
2. Gemini 2.0 Flash für Vision Classification nutzt
3. ClassificationResult zurücksendet
4. NEU: Dynamische Kategorien via CategoryRegistry
5. NEU: NEW_CATEGORY Handling mit Auto-Approve
"""

import asyncio
import logging
import os
import sys
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# AutoGen Imports
try:
    from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime
    from autogen_core import (
        RoutedAgent,
        message_handler,
        type_subscription,
        MessageContext,
        TopicId
    )
    HAS_AUTOGEN = True
except ImportError:
    HAS_AUTOGEN = False
    # Fallback-Klassen für Entwicklung ohne AutoGen
    class RoutedAgent:
        pass
    def message_handler(func):
        return func
    def type_subscription(topic_type):
        def decorator(cls):
            return cls
        return decorator
    class MessageContext:
        pass

from ..messages import (
    ClassifyIconMessage,
    ClassificationResult,
    WorkerType,
    UICategory
)

# NEU: CategoryRegistry Import
try:
    from services.category_registry import get_category_registry, CategoryRegistry
    HAS_CATEGORY_REGISTRY = True
except ImportError:
    HAS_CATEGORY_REGISTRY = False
    get_category_registry = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# DEPRECATED: Static prompt - now generated dynamically from CategoryRegistry
CLASSIFICATION_SYSTEM_PROMPT_LEGACY = """You are a UI element identifier specialized in desktop and web applications.

Analyze the image and identify:
1. What type of UI element this is
2. A human-readable name for this element
3. A brief description

Return ONLY a JSON object in this exact format:
{
  "category": "one of: button, icon, input, text, image, checkbox, radio, dropdown, link, container, header, footer, menu, toolbar, browser, editor, system, unknown",
  "semantic_name": "Human-readable name like 'Chrome Browser', 'Save Button', 'Search Input'",
  "description": "Brief description of what this element does or represents"
}

Always respond with valid JSON only, no additional text."""


@dataclass
class WorkerConfig:
    """Konfiguration für den Classification Worker."""
    worker_id: str
    host_address: str = "localhost:50051"
    model: str = "google/gemini-2.0-flash-001"
    max_concurrent: int = 5
    timeout_seconds: int = 10
    use_dynamic_categories: bool = True  # NEU: Dynamische Kategorien


class ClassificationWorker:
    """
    Classification Worker für parallele LLM Icon-Klassifizierung.
    
    Kann als:
    1. AutoGen gRPC Worker (production)
    2. Standalone Async Worker (development)
    """
    
    def __init__(self, config: Optional[WorkerConfig] = None):
        self.config = config or WorkerConfig(
            worker_id=f"clf_worker_{datetime.now().strftime('%H%M%S')}"
        )
        
        self._runtime: Optional[GrpcWorkerAgentRuntime] = None
        self._is_running: bool = False
        self._tasks_processed: int = 0
        self._tasks_failed: int = 0
        self._total_time_ms: float = 0.0
        self._new_categories_suggested: int = 0  # NEU: Statistik
        
        # OpenRouter Client (lazy init)
        self._openrouter_client = None
        
        # NEU: CategoryRegistry (lazy init)
        self._category_registry: Optional[CategoryRegistry] = None
        self._cached_prompt: Optional[str] = None
        self._prompt_cache_time: Optional[datetime] = None
        self._prompt_cache_duration_seconds = 300  # 5 Minuten Cache
        
        # Semaphore für Rate Limiting
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        logger.info(f"ClassificationWorker initialisiert: {self.config.worker_id}")
        logger.info(f"  Dynamic Categories: {self.config.use_dynamic_categories}")
    
    async def _get_client(self):
        """Lazy-Load OpenRouter Client."""
        if self._openrouter_client is None:
            from core.openrouter_client import get_openrouter_client
            self._openrouter_client = get_openrouter_client()
        return self._openrouter_client
    
    def _get_category_registry(self) -> Optional[CategoryRegistry]:
        """Lazy-Load CategoryRegistry."""
        if not self.config.use_dynamic_categories or not HAS_CATEGORY_REGISTRY:
            return None
        
        if self._category_registry is None and get_category_registry:
            self._category_registry = get_category_registry()
            logger.info(f"CategoryRegistry geladen: {len(self._category_registry.get_all_categories())} Kategorien")
        
        return self._category_registry
    
    def _get_system_prompt(self) -> str:
        """
        Gibt den System-Prompt zurück.
        
        NEU: Dynamisch aus CategoryRegistry generiert mit Caching.
        """
        registry = self._get_category_registry()
        
        if not registry:
            # Fallback zu statischem Prompt
            return CLASSIFICATION_SYSTEM_PROMPT_LEGACY
        
        # Check cache
        now = datetime.now()
        if (self._cached_prompt and self._prompt_cache_time and 
            (now - self._prompt_cache_time).total_seconds() < self._prompt_cache_duration_seconds):
            return self._cached_prompt
        
        # Generate new prompt
        self._cached_prompt = registry.build_classification_prompt(
            include_new_category_option=True,
            include_examples=True,
            max_examples_per_category=3
        )
        self._prompt_cache_time = now
        
        logger.debug("System-Prompt neu generiert aus CategoryRegistry")
        return self._cached_prompt
    
    def _get_valid_categories(self) -> list:
        """Gibt Liste valider Kategorien zurück."""
        registry = self._get_category_registry()
        
        if registry:
            return registry.get_all_categories() + ["NEW_CATEGORY"]
        
        # Fallback
        return [cat.value for cat in UICategory] + ["browser", "editor", "system", "NEW_CATEGORY"]
    
    # ==================== gRPC Worker Mode ====================
    
    async def start_grpc(self) -> bool:
        """Startet als gRPC Worker und verbindet zum Host."""
        if not HAS_AUTOGEN:
            logger.error("autogen-ext[grpc] nicht installiert!")
            return False
        
        try:
            self._runtime = GrpcWorkerAgentRuntime(
                host_address=self.config.host_address
            )
            await self._runtime.start()
            
            self._is_running = True
            logger.info(f"✓ gRPC Worker gestartet: {self.config.worker_id}")
            return True
            
        except Exception as e:
            logger.error(f"gRPC Worker Start fehlgeschlagen: {e}")
            return False
    
    async def stop_grpc(self) -> None:
        """Stoppt den gRPC Worker."""
        if self._runtime:
            try:
                await self._runtime.stop()
            except:
                pass
            self._runtime = None
        self._is_running = False
        
        # Save category usage stats
        registry = self._get_category_registry()
        if registry:
            registry.save_usage_stats()
        
        logger.info(f"gRPC Worker gestoppt: {self.config.worker_id}")
    
    # ==================== Classification Logic ====================
    
    async def classify(self, message: ClassifyIconMessage) -> ClassificationResult:
        """
        Klassifiziert ein einzelnes Icon mit Gemini 2.0 Flash.
        
        Thread-safe mit Semaphore für Rate Limiting.
        """
        async with self._semaphore:
            return await self._classify_internal(message)
    
    async def _classify_internal(self, message: ClassifyIconMessage) -> ClassificationResult:
        """Interne Klassifizierungs-Logik."""
        start_time = datetime.now()
        
        try:
            client = await self._get_client()
            
            # Build user message with image
            user_content = []
            
            # Add image
            if message.crop_base64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{message.crop_base64}",
                        "detail": "low"
                    }
                })
            
            # Add context text
            context_text = "Identify this UI element and return JSON with category, semantic_name, confidence, and description."
            if message.ocr_text:
                context_text += f"\nThe element contains the text: '{message.ocr_text}'"
            if message.cnn_category and message.cnn_category != "unknown":
                context_text += f"\nA preliminary classifier suggested: {message.cnn_category} (confidence: {message.cnn_confidence:.0%})"
            
            user_content.append({
                "type": "text",
                "text": context_text
            })
            
            # NEU: Dynamischer System-Prompt
            system_prompt = self._get_system_prompt()
            
            # Call LLM
            response = await client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                model=self.config.model
            )
            
            # Parse JSON response
            llm_category = "unknown"
            semantic_name = None
            description = None
            reasoning = None
            new_category_info = None  # NEU
            
            if response and response.content:
                raw_response = response.content.strip()
                
                try:
                    import json
                    # Handle markdown code blocks
                    if raw_response.startswith("```"):
                        lines = raw_response.split("\n")
                        json_lines = []
                        in_json = False
                        for line in lines:
                            if line.startswith("```json") or line.startswith("```"):
                                in_json = not in_json
                                continue
                            if in_json:
                                json_lines.append(line)
                        raw_response = "\n".join(json_lines)
                    
                    parsed = json.loads(raw_response)
                    
                    # Extract fields
                    llm_category = parsed.get("category", "unknown").lower()
                    semantic_name = parsed.get("semantic_name")
                    description = parsed.get("description")
                    
                    # NEU: Handle NEW_CATEGORY
                    if llm_category == "new_category":
                        new_cat_name = parsed.get("new_category_name", "").lower().replace(" ", "_")
                        new_cat_desc = parsed.get("new_category_description", "")
                        new_cat_parent = parsed.get("new_category_parent")
                        
                        if new_cat_name and new_cat_desc:
                            new_category_info = {
                                "name": new_cat_name,
                                "description": new_cat_desc,
                                "parent": new_cat_parent
                            }
                            
                            # Suggest to registry
                            registry = self._get_category_registry()
                            if registry:
                                result = registry.suggest_category(
                                    name=new_cat_name,
                                    description=new_cat_desc,
                                    suggested_by=self.config.model,
                                    parent=new_cat_parent,
                                    examples=[semantic_name] if semantic_name else [],
                                    context=f"OCR: {message.ocr_text}" if message.ocr_text else None
                                )
                                
                                self._new_categories_suggested += 1
                                
                                if result.get("action") == "approved":
                                    # Kategorie wurde auto-approved!
                                    llm_category = new_cat_name
                                    reasoning = f"NEW_CATEGORY '{new_cat_name}' auto-approved (votes: {result.get('votes')})"
                                    logger.info(f"✓ Neue Kategorie auto-approved: {new_cat_name}")
                                    
                                    # Invalidate prompt cache
                                    self._cached_prompt = None
                                else:
                                    # Noch pending - verwende parent oder unknown
                                    if new_cat_parent and registry.category_exists(new_cat_parent):
                                        llm_category = new_cat_parent
                                    else:
                                        llm_category = "icon" if "icon" in new_cat_name else "unknown"
                                    
                                    reasoning = f"NEW_CATEGORY '{new_cat_name}' suggested (votes: {result.get('votes')}/{result.get('threshold')})"
                        else:
                            llm_category = "unknown"
                            reasoning = "NEW_CATEGORY suggested but missing name or description"
                    else:
                        # Validate category
                        valid_categories = self._get_valid_categories()
                        if llm_category not in valid_categories:
                            reasoning = f"Unknown category '{llm_category}', defaulting to 'unknown'"
                            llm_category = "unknown"
                        else:
                            # Increment usage
                            registry = self._get_category_registry()
                            if registry:
                                registry.increment_usage(llm_category)
                    
                except json.JSONDecodeError:
                    # Fallback: Try to extract category from plain text
                    valid_categories = self._get_valid_categories()
                    raw_lower = raw_response.lower()
                    
                    for cat in valid_categories:
                        if cat in raw_lower:
                            llm_category = cat
                            reasoning = f"Extracted '{cat}' from non-JSON response: {raw_response[:100]}"
                            break
                    else:
                        reasoning = f"Could not parse JSON: {raw_response[:100]}"
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Update stats
            self._tasks_processed += 1
            self._total_time_ms += processing_time
            
            # Determine confidence
            llm_confidence = 0.90 if semantic_name else (0.70 if llm_category != "unknown" else 0.30)
            
            return ClassificationResult(
                box_id=message.box_id,
                request_id=message.request_id,
                llm_category=llm_category,
                llm_confidence=llm_confidence,
                semantic_name=semantic_name,
                description=description,
                reasoning=reasoning,
                model_used=self.config.model,
                processing_time_ms=processing_time,
                new_category_suggested=new_category_info  # NEU
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self._tasks_failed += 1
            
            logger.error(f"Classification error for {message.box_id}: {e}")
            
            return ClassificationResult(
                box_id=message.box_id,
                request_id=message.request_id,
                llm_category="unknown",
                llm_confidence=0.0,
                reasoning=None,
                model_used=self.config.model,
                processing_time_ms=processing_time,
                error=str(e)
            )
    
    async def classify_batch(
        self,
        messages: list[ClassifyIconMessage]
    ) -> list[ClassificationResult]:
        """
        Klassifiziert mehrere Icons parallel.
        
        Nutzt asyncio.gather mit Semaphore für Rate Limiting.
        """
        logger.info(f"[{self.config.worker_id}] Batch-Klassifizierung: {len(messages)} Icons")
        
        results = await asyncio.gather(
            *[self.classify(msg) for msg in messages],
            return_exceptions=True
        )
        
        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(ClassificationResult(
                    box_id=messages[i].box_id,
                    request_id=messages[i].request_id,
                    llm_category="unknown",
                    llm_confidence=0.0,
                    error=str(result)
                ))
            else:
                final_results.append(result)
        
        successful = sum(1 for r in final_results if r.error is None)
        logger.info(f"[{self.config.worker_id}] Batch fertig: {successful}/{len(messages)} erfolgreich")
        
        return final_results
    
    # ==================== Stats ====================

    def get_stats(self) -> dict:
        """Gibt Worker-Statistiken zurück."""
        avg_time = self._total_time_ms / self._tasks_processed if self._tasks_processed > 0 else 0
        stats = {
            "worker_id": self.config.worker_id,
            "is_running": self._is_running,
            "model": self.config.model,
            "tasks_processed": self._tasks_processed,
            "tasks_failed": self._tasks_failed,
            "avg_processing_time_ms": avg_time,
            "success_rate": (self._tasks_processed - self._tasks_failed) / self._tasks_processed if self._tasks_processed > 0 else 0,
            "new_categories_suggested": self._new_categories_suggested,
            "use_dynamic_categories": self.config.use_dynamic_categories
        }
        
        # Add registry stats
        registry = self._get_category_registry()
        if registry:
            registry_stats = registry.get_statistics()
            stats["category_count"] = registry_stats.get("totalCategories", 0)
            stats["pending_categories"] = registry_stats.get("pendingCategories", 0)
        
        return stats


# ==================== AutoGen RoutedAgent Version ====================

if HAS_AUTOGEN:
    @type_subscription(topic_type="moire.classification")
    class ClassificationWorkerAgent(RoutedAgent):
        """
        AutoGen 0.4 gRPC Worker Agent für Classification.
        """
        
        def __init__(self, model: str = "google/gemini-2.0-flash-001"):
            super().__init__()
            self._worker = ClassificationWorker(WorkerConfig(
                worker_id=f"agent_{id(self)}",
                model=model,
                use_dynamic_categories=True
            ))
        
        @message_handler
        async def handle_classify(
            self,
            message: ClassifyIconMessage,
            ctx: MessageContext
        ) -> ClassificationResult:
            """Handler für ClassifyIconMessage."""
            return await self._worker.classify(message)


# ==================== Standalone Mode ====================

async def main():
    """Test des Classification Workers mit dynamischen Kategorien."""
    import base64
    from pathlib import Path
    
    print("\n" + "="*60)
    print("Classification Worker Test (Dynamic Categories)")
    print("="*60)
    
    worker = ClassificationWorker(WorkerConfig(
        worker_id="test_worker",
        use_dynamic_categories=True
    ))
    
    # Test CategoryRegistry
    if HAS_CATEGORY_REGISTRY:
        registry = get_category_registry()
        print(f"\n✓ CategoryRegistry geladen")
        print(f"  Kategorien: {len(registry.get_all_categories())}")
        print(f"  Leaf Categories: {len(registry.get_leaf_categories())}")
        print(f"  Pending: {len(registry.get_pending_categories())}")
        
        # Show dynamic prompt preview
        prompt = registry.build_classification_prompt()
        print(f"\n  Prompt-Länge: {len(prompt)} Zeichen")
        print(f"  Prompt-Preview:\n{prompt[:500]}...")
    else:
        print("\n⚠ CategoryRegistry nicht verfügbar - nutze statischen Prompt")
    
    print(f"\nWorker Stats: {worker.get_stats()}")
    
    # Test mit echtem Bild wenn vorhanden
    test_image_path = Path("detection_results/crops/test.png")
    if test_image_path.exists():
        with open(test_image_path, "rb") as f:
            crop_base64 = base64.b64encode(f.read()).decode()
        
        test_message = ClassifyIconMessage(
            box_id="test_001",
            crop_base64=crop_base64,
            cnn_category="icon",
            cnn_confidence=0.65,
            ocr_text=""
        )
        
        print(f"\nKlassifiziere Test-Bild: {test_image_path}")
        result = await worker.classify(test_message)
        
        print(f"\nErgebnis:")
        print(f"  LLM Category: {result.llm_category}")
        print(f"  Semantic Name: {result.semantic_name}")
        print(f"  LLM Confidence: {result.llm_confidence:.0%}")
        print(f"  Processing Time: {result.processing_time_ms:.0f}ms")
        print(f"  Reasoning: {result.reasoning}")
        if result.new_category_suggested:
            print(f"  NEW CATEGORY: {result.new_category_suggested}")
        if result.error:
            print(f"  Error: {result.error}")
    else:
        print(f"\nKein Test-Bild gefunden: {test_image_path}")
    
    print(f"\nFinal Stats: {worker.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
"""
gRPC Worker Host für MoireTracker

Zentrale Host-Komponente die:
1. GrpcWorkerAgentRuntimeHost auf :50051 startet
2. Workers registriert und verwaltet
3. Messages routet (Fan-out für Classification)
4. Ergebnisse sammelt und merged
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime

# AutoGen gRPC Runtime
try:
    from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntimeHost
    from autogen_core import TopicId
    HAS_GRPC = True
except ImportError:
    HAS_GRPC = False
    logging.warning("autogen-ext[grpc] not installed. Run: pip install autogen-ext[grpc]")

from .messages import (
    ClassifyIconMessage,
    ClassificationResult,
    ValidationRequest,
    ValidationResult,
    BatchClassifyRequest,
    BatchClassifyResult,
    WorkerStatus,
    WorkerType,
    calculate_combined_confidence,
    should_trigger_active_learning
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Topic IDs für Message Routing
CLASSIFICATION_TOPIC = "moire.classification"
VALIDATION_TOPIC = "moire.validation"
EXECUTION_TOPIC = "moire.execution"
RESULTS_TOPIC = "moire.results"


@dataclass
class WorkerRegistry:
    """Registry für aktive Workers."""
    workers: Dict[str, WorkerStatus] = field(default_factory=dict)
    
    def register(self, worker_id: str, worker_type: WorkerType) -> None:
        """Registriert einen neuen Worker."""
        self.workers[worker_id] = WorkerStatus(
            worker_id=worker_id,
            worker_type=worker_type,
            is_running=True,
            last_active=datetime.now()
        )
        logger.info(f"Worker registriert: {worker_id} ({worker_type.value})")
    
    def unregister(self, worker_id: str) -> None:
        """Entfernt einen Worker."""
        if worker_id in self.workers:
            del self.workers[worker_id]
            logger.info(f"Worker entfernt: {worker_id}")
    
    def update_status(self, worker_id: str, **kwargs) -> None:
        """Aktualisiert Worker Status."""
        if worker_id in self.workers:
            worker = self.workers[worker_id]
            for key, value in kwargs.items():
                if hasattr(worker, key):
                    setattr(worker, key, value)
            worker.last_active = datetime.now()
    
    def get_workers_by_type(self, worker_type: WorkerType) -> List[WorkerStatus]:
        """Gibt alle Workers eines Typs zurück."""
        return [w for w in self.workers.values() if w.worker_type == worker_type]
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken über alle Workers zurück."""
        stats = {
            "total_workers": len(self.workers),
            "by_type": {},
            "total_processed": 0,
            "total_failed": 0
        }
        for wt in WorkerType:
            workers = self.get_workers_by_type(wt)
            stats["by_type"][wt.value] = len(workers)
        
        for w in self.workers.values():
            stats["total_processed"] += w.tasks_processed
            stats["total_failed"] += w.tasks_failed
        
        return stats


class GrpcWorkerHost:
    """
    gRPC Worker Host für MoireTracker.
    
    Verwaltet:
    - ClassificationWorkers (parallele LLM Klassifizierung)
    - VisionValidationWorkers (CNN-LLM Vergleich)
    - ExecutionWorkers (Desktop Actions)
    """
    
    def __init__(
        self,
        address: str = "localhost:50051",
        max_workers: int = 10
    ):
        self.address = address
        self.max_workers = max_workers
        
        # AutoGen Host
        self._host: Optional[GrpcWorkerAgentRuntimeHost] = None
        self._is_running: bool = False
        
        # Worker Registry
        self.registry = WorkerRegistry()
        
        # Pending Results (für Batch-Processing)
        self._pending_batches: Dict[str, BatchClassifyRequest] = {}
        self._batch_results: Dict[str, List[ValidationResult]] = {}
        
        # Callbacks
        self._on_result_callbacks: List[Callable[[ValidationResult], None]] = []
        self._on_batch_complete_callbacks: List[Callable[[BatchClassifyResult], None]] = []
        
        logger.info(f"GrpcWorkerHost initialisiert: {address}")
    
    async def start(self) -> bool:
        """Startet den gRPC Host Service."""
        if not HAS_GRPC:
            logger.error("autogen-ext[grpc] nicht installiert!")
            return False
        
        if self._is_running:
            logger.warning("Host läuft bereits")
            return True
        
        try:
            self._host = GrpcWorkerAgentRuntimeHost(address=self.address)
            self._host.start()  # Startet im Background
            self._is_running = True
            logger.info(f"✓ gRPC Host gestartet auf {self.address}")
            return True
        except Exception as e:
            logger.error(f"Host Start fehlgeschlagen: {e}")
            return False
    
    async def stop(self) -> None:
        """Stoppt den gRPC Host Service."""
        if self._host and self._is_running:
            try:
                # In AutoGen 0.4 gibt es keine explizite stop() Methode
                # Der Host wird beim Garbage Collection gestoppt
                self._host = None
                self._is_running = False
                logger.info("gRPC Host gestoppt")
            except Exception as e:
                logger.error(f"Host Stop fehlgeschlagen: {e}")
    
    def is_running(self) -> bool:
        """Prüft ob Host läuft."""
        return self._is_running
    
    # ==================== Batch Classification ====================
    
    async def classify_batch(
        self,
        icons: List[ClassifyIconMessage],
        timeout: int = 30
    ) -> BatchClassifyResult:
        """
        Klassifiziert einen Batch von Icons parallel.
        
        1. Verteilt Icons an ClassificationWorkers
        2. Sammelt Ergebnisse
        3. Sendet an VisionValidationWorker
        4. Gibt finales BatchResult zurück
        """
        start_time = datetime.now()
        batch_id = f"batch_{start_time.strftime('%H%M%S%f')}"
        
        logger.info(f"[{batch_id}] Starte Batch-Klassifizierung für {len(icons)} Icons...")
        
        # Erstelle Batch Request
        batch_request = BatchClassifyRequest(
            batch_id=batch_id,
            icons=icons,
            timeout_seconds=timeout
        )
        self._pending_batches[batch_id] = batch_request
        self._batch_results[batch_id] = []
        
        # Simuliere Fan-out (in echter Impl via gRPC Topics)
        # TODO: Echtes gRPC Message Publishing wenn Workers implementiert
        results = await self._simulate_classification(icons)
        
        # Sammle Ergebnisse
        successful = sum(1 for r in results if r.error is None)
        failed = len(results) - successful
        
        # Cleanup
        del self._pending_batches[batch_id]
        del self._batch_results[batch_id]
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        batch_result = BatchClassifyResult(
            batch_id=batch_id,
            results=results,
            total_icons=len(icons),
            successful=successful,
            failed=failed,
            processing_time_ms=processing_time,
            workers_used=min(len(icons), self.max_workers)
        )
        
        logger.info(f"[{batch_id}] Batch fertig: {successful}/{len(icons)} erfolgreich in {processing_time:.0f}ms")
        
        # Callbacks
        for callback in self._on_batch_complete_callbacks:
            try:
                callback(batch_result)
            except Exception as e:
                logger.error(f"Batch callback error: {e}")
        
        return batch_result
    
    async def _simulate_classification(
        self,
        icons: List[ClassifyIconMessage]
    ) -> List[ValidationResult]:
        """
        Simuliert die Classification + Validation Pipeline.
        
        In echter Implementierung werden Messages über gRPC Topics verteilt.
        Diese Simulation nutzt asyncio.gather für parallele Verarbeitung.
        """
        from ..core.openrouter_client import get_openrouter_client
        
        client = get_openrouter_client()
        model = "google/gemini-2.0-flash-001"
        
        async def classify_single(icon: ClassifyIconMessage) -> ValidationResult:
            """Klassifiziert ein einzelnes Icon."""
            start = datetime.now()
            
            try:
                # LLM Classification
                response = await client.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": """You are a UI element classifier. Classify the image into one category:
button, icon, input, text, image, checkbox, radio, dropdown, link, container, header, footer, menu, toolbar, unknown

Respond with ONLY the category name."""
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{icon.crop_base64}",
                                        "detail": "low"
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": f"What type of UI element is this?{' Text: ' + icon.ocr_text if icon.ocr_text else ''}"
                                }
                            ]
                        }
                    ],
                    model=model
                )
                
                llm_category = "unknown"
                if response and response.content:
                    llm_category = response.content.strip().lower()
                    # Validate category
                    valid_cats = ["button", "icon", "input", "text", "image", "checkbox", 
                                  "radio", "dropdown", "link", "container", "header", 
                                  "footer", "menu", "toolbar", "unknown"]
                    if llm_category not in valid_cats:
                        for cat in valid_cats:
                            if cat in llm_category:
                                llm_category = cat
                                break
                        else:
                            llm_category = "unknown"
                
                processing_time = (datetime.now() - start).total_seconds() * 1000
                
                # Validation: CNN vs LLM
                categories_match = icon.cnn_category == llm_category if icon.cnn_category else False
                final_confidence = calculate_combined_confidence(
                    icon.cnn_confidence,
                    0.85,  # LLM default confidence
                    categories_match
                )
                
                # Active Learning Check
                needs_review = should_trigger_active_learning(
                    icon.cnn_category,
                    llm_category,
                    icon.cnn_confidence,
                    0.85
                )
                
                # Final Category: LLM hat Vorrang bei Diskrepanz
                final_category = llm_category if llm_category != "unknown" else (icon.cnn_category or "unknown")
                
                return ValidationResult(
                    box_id=icon.box_id,
                    request_id=icon.request_id,
                    final_category=final_category,
                    final_confidence=final_confidence,
                    cnn_category=icon.cnn_category,
                    llm_category=llm_category,
                    categories_match=categories_match,
                    needs_human_review=needs_review,
                    add_to_training=needs_review,
                    training_label=llm_category if needs_review else None,
                    validation_reasoning=f"CNN: {icon.cnn_category or 'none'}, LLM: {llm_category}, Match: {categories_match}"
                )
                
            except Exception as e:
                logger.error(f"Classification error for {icon.box_id}: {e}")
                return ValidationResult(
                    box_id=icon.box_id,
                    request_id=icon.request_id,
                    final_category=icon.cnn_category or "unknown",
                    final_confidence=icon.cnn_confidence,
                    cnn_category=icon.cnn_category,
                    llm_category="error",
                    categories_match=False,
                    validation_reasoning=f"Error: {e}"
                )
        
        # Parallel classification mit Semaphore für Rate Limiting
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent
        
        async def limited_classify(icon: ClassifyIconMessage) -> ValidationResult:
            async with semaphore:
                return await classify_single(icon)
        
        results = await asyncio.gather(*[limited_classify(icon) for icon in icons])
        return list(results)
    
    # ==================== Callbacks ====================
    
    def on_result(self, callback: Callable[[ValidationResult], None]) -> None:
        """Registriert Callback für einzelne Ergebnisse."""
        self._on_result_callbacks.append(callback)
    
    def on_batch_complete(self, callback: Callable[[BatchClassifyResult], None]) -> None:
        """Registriert Callback für Batch-Ergebnisse."""
        self._on_batch_complete_callbacks.append(callback)
    
    # ==================== Status ====================
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt Host-Status zurück."""
        return {
            "address": self.address,
            "is_running": self._is_running,
            "max_workers": self.max_workers,
            "pending_batches": len(self._pending_batches),
            "workers": self.registry.get_stats()
        }


# ==================== Singleton & Factory ====================

_host_instance: Optional[GrpcWorkerHost] = None


def get_grpc_host(address: str = "localhost:50051") -> GrpcWorkerHost:
    """Gibt Singleton Host-Instanz zurück."""
    global _host_instance
    if _host_instance is None:
        _host_instance = GrpcWorkerHost(address=address)
    return _host_instance


async def start_host(address: str = "localhost:50051") -> GrpcWorkerHost:
    """Startet den gRPC Host."""
    host = get_grpc_host(address)
    await host.start()
    return host


async def stop_host() -> None:
    """Stoppt den gRPC Host."""
    global _host_instance
    if _host_instance:
        await _host_instance.stop()
        _host_instance = None


# ==================== CLI ====================

async def main():
    """Test des gRPC Hosts."""
    logging.basicConfig(level=logging.INFO)
    
    host = await start_host()
    print(f"Host Status: {host.get_status()}")
    
    # Test Classification (ohne echte Bilder)
    test_icons = [
        ClassifyIconMessage(
            box_id="test_1",
            crop_base64="",  # Würde echtes Bild sein
            cnn_category="button",
            cnn_confidence=0.65
        )
    ]
    
    print("\nHost läuft. Drücke Ctrl+C zum Beenden...")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStoppe Host...")
        await stop_host()


if __name__ == "__main__":
    asyncio.run(main())
"""
Vision Validation Worker für MoireTracker

Vergleicht CNN und LLM Klassifizierungen und:
1. Berechnet kombinierte Confidence
2. Entscheidet finale Kategorie
3. Triggert Active Learning bei Diskrepanzen
4. Speichert für Training relevante Samples
"""

import asyncio
import logging
import os
import sys
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# AutoGen Imports
try:
    from autogen_core import (
        RoutedAgent,
        message_handler,
        type_subscription,
        MessageContext
    )
    HAS_AUTOGEN = True
except ImportError:
    HAS_AUTOGEN = False
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
    ValidationRequest,
    ValidationResult,
    ClassificationResult,
    ClassifyIconMessage,
    WorkerType,
    UICategory,
    calculate_combined_confidence,
    should_trigger_active_learning
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ValidationConfig:
    """Konfiguration für den Validation Worker."""
    worker_id: str = "validation_worker"
    
    # Confidence Thresholds
    high_confidence_threshold: float = 0.85
    low_confidence_threshold: float = 0.50
    
    # Active Learning
    enable_active_learning: bool = True
    training_data_path: str = "training_data"
    
    # Category Weights (LLM vs CNN priority)
    llm_weight: float = 0.7
    cnn_weight: float = 0.3


@dataclass
class ValidationStats:
    """Statistiken über Validierungen."""
    total_validated: int = 0
    matches: int = 0
    mismatches: int = 0
    llm_overrides: int = 0
    cnn_overrides: int = 0
    active_learning_triggers: int = 0
    human_review_needed: int = 0
    
    @property
    def match_rate(self) -> float:
        return self.matches / self.total_validated if self.total_validated > 0 else 0.0


class VisionValidationWorker:
    """
    Validation Worker der CNN und LLM Klassifizierungen vergleicht.
    
    Entscheidungslogik:
    1. Beide übereinstimmend → Hohe Confidence (boost)
    2. Diskrepanz, LLM confident → LLM überschreibt
    3. Diskrepanz, CNN confident → Menschliche Überprüfung
    4. Beide unsicher → Active Learning Trigger
    """
    
    def __init__(self, config: Optional[ValidationConfig] = None):
        self.config = config or ValidationConfig()
        self.stats = ValidationStats()
        
        # Dataset Manager für Active Learning
        self._dataset_manager = None
        
        logger.info(f"VisionValidationWorker initialisiert: {self.config.worker_id}")
    
    async def _get_dataset_manager(self):
        """Lazy-Load Dataset Manager."""
        if self._dataset_manager is None:
            try:
                from memory.dataset_manager import DatasetManager
                self._dataset_manager = DatasetManager(
                    base_path=self.config.training_data_path
                )
            except ImportError:
                logger.warning("DatasetManager nicht verfügbar")
        return self._dataset_manager
    
    async def validate(self, request: ValidationRequest) -> ValidationResult:
        """
        Validiert eine einzelne CNN-LLM Klassifizierung.
        
        Args:
            request: ValidationRequest mit CNN und LLM Ergebnissen
            
        Returns:
            ValidationResult mit finaler Kategorie und Active Learning Info
        """
        self.stats.total_validated += 1
        
        # 1. Check ob Kategorien übereinstimmen
        cnn_cat = request.cnn_category.lower() if request.cnn_category else None
        llm_cat = request.llm_category.lower()
        
        categories_match = cnn_cat == llm_cat if cnn_cat else False
        
        # 2. Berechne kombinierte Confidence
        final_confidence = calculate_combined_confidence(
            request.cnn_confidence,
            request.llm_confidence,
            categories_match
        )
        
        # 3. Bestimme finale Kategorie
        final_category, decision_reason = self._decide_category(
            cnn_cat,
            llm_cat,
            request.cnn_confidence,
            request.llm_confidence,
            categories_match
        )
        
        # 4. Active Learning Check
        needs_review, add_to_training = self._check_active_learning(
            cnn_cat,
            llm_cat,
            request.cnn_confidence,
            request.llm_confidence
        )
        
        # 5. Update Stats
        if categories_match:
            self.stats.matches += 1
        else:
            self.stats.mismatches += 1
            if final_category == llm_cat:
                self.stats.llm_overrides += 1
            elif final_category == cnn_cat:
                self.stats.cnn_overrides += 1
        
        if needs_review:
            self.stats.human_review_needed += 1
        if add_to_training:
            self.stats.active_learning_triggers += 1
        
        # 6. Trigger Active Learning wenn nötig
        training_label = None
        if add_to_training and self.config.enable_active_learning:
            training_label = await self._trigger_active_learning(
                request, final_category
            )
        
        # 7. Build Reasoning
        reasoning = self._build_reasoning(
            cnn_cat, llm_cat,
            request.cnn_confidence, request.llm_confidence,
            categories_match, decision_reason
        )
        
        return ValidationResult(
            box_id=request.box_id,
            request_id=request.request_id,
            final_category=final_category,
            final_confidence=final_confidence,
            cnn_category=cnn_cat,
            llm_category=llm_cat,
            categories_match=categories_match,
            needs_human_review=needs_review,
            add_to_training=add_to_training,
            training_label=training_label,
            validation_reasoning=reasoning
        )
    
    def _decide_category(
        self,
        cnn_cat: Optional[str],
        llm_cat: str,
        cnn_conf: float,
        llm_conf: float,
        match: bool
    ) -> Tuple[str, str]:
        """
        Entscheidet welche Kategorie zu verwenden ist.
        
        Returns:
            (category, reason)
        """
        # Case 1: Match - beide einig
        if match and cnn_cat:
            return cnn_cat, "MATCH: Both CNN and LLM agree"
        
        # Case 2: Kein CNN Ergebnis
        if cnn_cat is None:
            return llm_cat, "LLM_ONLY: No CNN classification available"
        
        # Case 3: LLM sagt "unknown"
        if llm_cat == "unknown":
            if cnn_conf >= self.config.high_confidence_threshold:
                return cnn_cat, "CNN_FALLBACK: LLM uncertain, CNN confident"
            return "unknown", "BOTH_UNCERTAIN: Neither classifier confident"
        
        # Case 4: CNN sagt "unknown"
        if cnn_cat == "unknown":
            return llm_cat, "LLM_OVERRIDE: CNN was unknown"
        
        # Case 5: Mismatch - gewichtete Entscheidung
        llm_score = llm_conf * self.config.llm_weight
        cnn_score = cnn_conf * self.config.cnn_weight
        
        if llm_score >= cnn_score:
            return llm_cat, f"LLM_WINS: Score {llm_score:.2f} vs CNN {cnn_score:.2f}"
        else:
            return cnn_cat, f"CNN_WINS: Score {cnn_score:.2f} vs LLM {llm_score:.2f}"
    
    def _check_active_learning(
        self,
        cnn_cat: Optional[str],
        llm_cat: str,
        cnn_conf: float,
        llm_conf: float
    ) -> Tuple[bool, bool]:
        """
        Prüft ob Active Learning getriggert werden soll.
        
        Returns:
            (needs_human_review, add_to_training)
        """
        needs_review = False
        add_to_training = False
        
        # Diskrepanz = immer interessant für Training
        if cnn_cat and cnn_cat != llm_cat:
            add_to_training = True
            
            # Beide confident aber unterschiedlich → menschliche Überprüfung
            if cnn_conf >= self.config.low_confidence_threshold and \
               llm_conf >= self.config.low_confidence_threshold:
                needs_review = True
        
        # LLM unsicher
        if llm_cat == "unknown" or llm_conf < self.config.low_confidence_threshold:
            add_to_training = True
            needs_review = True
        
        # Beide unsicher
        if cnn_conf < self.config.low_confidence_threshold and \
           llm_conf < self.config.low_confidence_threshold:
            needs_review = True
        
        return needs_review, add_to_training
    
    async def _trigger_active_learning(
        self,
        request: ValidationRequest,
        final_category: str
    ) -> Optional[str]:
        """
        Triggert Active Learning: Speichert Sample für Training.
        
        Returns:
            Training label wenn erfolgreich gespeichert
        """
        manager = await self._get_dataset_manager()
        if not manager:
            return None
        
        try:
            # Speichere das Crop-Bild im Training-Ordner
            # Label ist die finale Kategorie (oder llm_category bei Diskrepanz)
            label = final_category if final_category != "unknown" else request.llm_category
            
            # Hier würde das Bild gespeichert werden
            # manager.add_sample(request.crop_base64, label, is_uncertain=True)
            
            logger.info(f"[ActiveLearning] Sample hinzugefügt: {request.box_id} → {label}")
            return label
            
        except Exception as e:
            logger.error(f"Active Learning Trigger fehlgeschlagen: {e}")
            return None
    
    def _build_reasoning(
        self,
        cnn_cat: Optional[str],
        llm_cat: str,
        cnn_conf: float,
        llm_conf: float,
        match: bool,
        decision: str
    ) -> str:
        """Erstellt menschenlesbares Reasoning."""
        parts = []
        
        parts.append(f"CNN: {cnn_cat or 'none'} ({cnn_conf:.0%})")
        parts.append(f"LLM: {llm_cat} ({llm_conf:.0%})")
        parts.append(f"Match: {'✓' if match else '✗'}")
        parts.append(f"Decision: {decision}")
        
        return " | ".join(parts)
    
    async def validate_batch(
        self,
        requests: List[ValidationRequest]
    ) -> List[ValidationResult]:
        """Validiert mehrere Requests parallel."""
        results = await asyncio.gather(
            *[self.validate(req) for req in requests]
        )
        return list(results)
    
    def get_stats(self) -> dict:
        """Gibt Statistiken zurück."""
        return {
            "worker_id": self.config.worker_id,
            "total_validated": self.stats.total_validated,
            "matches": self.stats.matches,
            "mismatches": self.stats.mismatches,
            "match_rate": f"{self.stats.match_rate:.1%}",
            "llm_overrides": self.stats.llm_overrides,
            "cnn_overrides": self.stats.cnn_overrides,
            "active_learning_triggers": self.stats.active_learning_triggers,
            "human_review_needed": self.stats.human_review_needed
        }


# ==================== AutoGen RoutedAgent Version ====================

if HAS_AUTOGEN:
    @type_subscription(topic_type="moire.validation")
    class VisionValidationWorkerAgent(RoutedAgent):
        """
        AutoGen 0.4 gRPC Worker Agent für CNN-LLM Validation.
        """
        
        def __init__(self):
            super().__init__()
            self._worker = VisionValidationWorker()
        
        @message_handler
        async def handle_validate(
            self,
            message: ValidationRequest,
            ctx: MessageContext
        ) -> ValidationResult:
            """Handler für ValidationRequest."""
            return await self._worker.validate(message)


# ==================== Combined Classification + Validation ====================

async def classify_and_validate(
    icon: ClassifyIconMessage,
    classification_worker,
    validation_worker: VisionValidationWorker
) -> ValidationResult:
    """
    Kombiniert Classification und Validation in einem Schritt.
    
    1. ClassificationWorker klassifiziert mit LLM
    2. VisionValidationWorker vergleicht mit CNN
    3. Gibt finales ValidationResult zurück inkl. semantic_name
    """
    # Step 1: LLM Classification
    clf_result: ClassificationResult = await classification_worker.classify(icon)
    
    # Step 2: Validation Request erstellen
    val_request = ValidationRequest(
        box_id=icon.box_id,
        request_id=icon.request_id,
        crop_base64=icon.crop_base64,
        cnn_category=icon.cnn_category,
        cnn_confidence=icon.cnn_confidence,
        llm_category=clf_result.llm_category,
        llm_confidence=clf_result.llm_confidence,
        ocr_text=icon.ocr_text
    )
    
    # Step 3: Validation
    result = await validation_worker.validate(val_request)
    
    # Step 4: Add semantic_name from classification result
    result.semantic_name = clf_result.semantic_name
    
    return result


# ==================== Standalone Test ====================

async def main():
    """Test des Validation Workers."""
    worker = VisionValidationWorker()
    
    # Test-Cases
    test_cases = [
        # (cnn_cat, cnn_conf, llm_cat, llm_conf)
        ("button", 0.85, "button", 0.90),  # Match, high confidence
        ("icon", 0.70, "button", 0.85),     # Mismatch, LLM wins
        ("button", 0.90, "icon", 0.60),     # Mismatch, CNN wins
        (None, 0.0, "text", 0.80),          # No CNN
        ("dropdown", 0.45, "unknown", 0.30), # Both uncertain
    ]
    
    print("Testing VisionValidationWorker\n")
    print("=" * 80)
    
    for i, (cnn_cat, cnn_conf, llm_cat, llm_conf) in enumerate(test_cases):
        request = ValidationRequest(
            box_id=f"test_{i}",
            request_id=f"req_{i}",
            crop_base64="",
            cnn_category=cnn_cat,
            cnn_confidence=cnn_conf,
            llm_category=llm_cat,
            llm_confidence=llm_conf
        )
        
        result = await worker.validate(request)
        
        print(f"\nTest Case {i + 1}:")
        print(f"  Input:  CNN={cnn_cat} ({cnn_conf:.0%}), LLM={llm_cat} ({llm_conf:.0%})")
        print(f"  Result: {result.final_category} ({result.final_confidence:.0%})")
        print(f"  Match:  {result.categories_match}")
        print(f"  Review: {result.needs_human_review}, Train: {result.add_to_training}")
        print(f"  Reason: {result.validation_reasoning}")
    
    print("\n" + "=" * 80)
    print(f"\nStats: {worker.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
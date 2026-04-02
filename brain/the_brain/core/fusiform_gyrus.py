"""
Fusiform Gyrus - FFA/VWFA (Fusiform Face Area + Visual Word Form Area)

Specialized cortical areas for domain-specific visual recognition:
- Kanwisher et al. (1997): FFA selectively responds to faces
- Cohen et al. (2000): VWFA selectively responds to written words/symbols
- Domain-specific processing modules with rapid, expert-level recognition
"""

import time
import logging
import numpy as np
from typing import Dict, List, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.fusiform')


@dataclass
class FusiformGyrusStats:
    """Aggregate statistics for the fusiform gyrus."""
    total_recognitions: int = 0
    face_detections: int = 0
    text_detections: int = 0
    avg_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_recognitions': self.total_recognitions,
            'face_detections': self.face_detections,
            'text_detections': self.text_detections,
            'avg_confidence': round(self.avg_confidence, 4),
        }


# ─── Domain-Specific Recognizer ─────────────────────────────────────────

class DomainSpecificRecognizer:
    """Base recognizer with template matching via cosine similarity."""

    def __init__(self, n_features: int = 16):
        self.n_features = n_features
        self._templates: Dict[str, List[tuple]] = {}  # domain -> [(label, vec)]

    def _normalize(self, features: np.ndarray) -> np.ndarray:
        vec = np.array(features, dtype=np.float64).flatten()[:self.n_features]
        if len(vec) < self.n_features:
            vec = np.pad(vec, (0, self.n_features - len(vec)))
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def learn_template(self, features: np.ndarray, label: str, domain: str) -> None:
        """Store a new template for a domain."""
        self._templates.setdefault(domain, []).append((label, self._normalize(features)))
        logger.debug("Learned template '%s' in domain '%s'", label, domain)

    def recognize(self, input_features: np.ndarray, domain: str) -> Dict[str, Any]:
        """Match input against templates in the given domain."""
        vec = self._normalize(input_features)
        templates = self._templates.get(domain, [])
        if not templates:
            return {'recognition_score': 0.0, 'best_match': None,
                    'confidence': 0.0, 'is_expert_domain': False}
        best_score, best_label = -1.0, None
        for label, tmpl in templates:
            score = float(np.dot(vec, tmpl))
            if score > best_score:
                best_score, best_label = score, label
        confidence = max(0.0, min(1.0, best_score))
        return {'recognition_score': round(best_score, 4), 'best_match': best_label,
                'confidence': round(confidence, 4), 'is_expert_domain': len(templates) >= 3}

    def template_count(self, domain: str) -> int:
        return len(self._templates.get(domain, []))


# ─── FFA: Face Processor ────────────────────────────────────────────────

class FaceProcessor:
    """Fusiform Face Area - face detection and recognition."""

    def __init__(self, recognizer: DomainSpecificRecognizer, threshold: float = 0.5):
        self._recognizer = recognizer
        self._threshold = threshold

    def process_face(self, features: np.ndarray) -> Dict[str, Any]:
        """Process features for face-related information."""
        result = self._recognizer.recognize(features, domain='face')
        score = result['recognition_score']
        vec = np.array(features, dtype=np.float64).flatten()
        energy = float(np.mean(np.abs(vec))) if len(vec) > 0 else 0.0
        return {
            'face_detected': score >= self._threshold,
            'identity_score': round(max(0.0, score), 4),
            'expression_estimate': round(min(1.0, energy), 4),
            'familiarity': round(result['confidence'], 4),
        }


# ─── VWFA: Text Processor ──────────────────────────────────────────────

class TextProcessor:
    """Visual Word Form Area - text and symbol recognition."""

    def __init__(self, recognizer: DomainSpecificRecognizer, threshold: float = 0.5):
        self._recognizer = recognizer
        self._threshold = threshold

    def process_text(self, features: np.ndarray) -> Dict[str, Any]:
        """Process features for text/symbol-related information."""
        result = self._recognizer.recognize(features, domain='text')
        score = result['recognition_score']
        text_detected = score >= self._threshold
        fluency = min(1.0, self._recognizer.template_count('text') / 10.0)
        if text_detected and result['best_match']:
            symbol_type = 'word'
        elif score > 0.2:
            symbol_type = 'symbol'
        else:
            symbol_type = 'unknown'
        return {
            'text_detected': text_detected,
            'word_score': round(max(0.0, score), 4),
            'symbol_type': symbol_type,
            'reading_fluency': round(fluency, 4),
        }


# ─── Main Class: Fusiform Gyrus ─────────────────────────────────────────

class FusiformGyrus:
    """
    Fusiform Gyrus combining FFA (face) and VWFA (text) processing.

    Routes input to the appropriate domain-specific processor based on
    auto-detection or an explicit domain hint.
    """

    def __init__(self, n_features: int = 16,
                 face_threshold: float = 0.5,
                 text_threshold: float = 0.5):
        self.n_features = n_features
        self._recognizer = DomainSpecificRecognizer(n_features=n_features)
        self._face_proc = FaceProcessor(self._recognizer, threshold=face_threshold)
        self._text_proc = TextProcessor(self._recognizer, threshold=text_threshold)
        self._stats = FusiformGyrusStats()
        self._confidence_history: deque = deque(maxlen=200)
        self._last_result: Dict[str, Any] = {}
        logger.info("FusiformGyrus initialised (n_features=%d)", n_features)

    def process(self, input_features: np.ndarray, domain: str = 'auto') -> Dict[str, Any]:
        """Process input through FFA and VWFA, choosing the best domain."""
        face_result = self._face_proc.process_face(input_features)
        text_result = self._text_proc.process_text(input_features)

        if domain == 'face':
            chosen = 'face'
        elif domain == 'text':
            chosen = 'text'
        else:
            chosen = 'face' if face_result['identity_score'] >= text_result['word_score'] else 'text'

        self._stats.total_recognitions += 1
        if face_result['face_detected']:
            self._stats.face_detections += 1
        if text_result['text_detected']:
            self._stats.text_detections += 1

        conf = face_result['familiarity'] if chosen == 'face' else text_result['word_score']
        self._confidence_history.append(conf)
        self._stats.avg_confidence = float(np.mean(list(self._confidence_history)))

        self._last_result = {
            'domain': chosen, 'face_result': face_result,
            'text_result': text_result, 'chosen_domain': chosen,
            'timestamp': time.time(),
        }
        logger.debug("FusiformGyrus processed domain=%s conf=%.3f", chosen, conf)
        return self._last_result

    def update(self, features: np.ndarray, label: str, domain: str) -> None:
        """Learn a new template from labelled input."""
        self._recognizer.learn_template(features, label, domain)

    def reset(self) -> None:
        """Reset all internal state."""
        self._recognizer._templates.clear()
        self._stats = FusiformGyrusStats()
        self._confidence_history.clear()
        self._last_result = {}
        logger.info("FusiformGyrus reset")

    def expertise_modulated_recognition(self, category: str, experience_level: float = 0.5) -> Dict[str, float]:
        """
        Experience-dependent perceptual expertise (Gauthier et al., 1999).

        The FFA isn't face-specific — it's an expertise module. With enough
        training, it processes any category at expert level (cars, birds,
        Greebles). Expertise shifts processing from feature-based to
        holistic, matching the configural processing seen for faces.

        Args:
            category: Category being processed (face, text, trained, novel)
            experience_level: Training level for this category [0, 1]

        Returns:
            Dict with processing_mode, recognition_speed, accuracy_boost
        """
        # High expertise -> holistic (fast, configural)
        # Low expertise -> featural (slow, part-based)
        if experience_level > 0.6:
            mode = 'holistic'
            speed = 0.8 + experience_level * 0.2
            accuracy_boost = experience_level * 0.5
        elif experience_level > 0.3:
            mode = 'mixed'
            speed = 0.5 + experience_level * 0.3
            accuracy_boost = experience_level * 0.3
        else:
            mode = 'featural'
            speed = 0.3 + experience_level * 0.2
            accuracy_boost = experience_level * 0.1

        # Faces and text always get expertise-level processing
        if category in ('face', 'text'):
            mode = 'holistic'
            speed = max(speed, 0.85)
            accuracy_boost = max(accuracy_boost, 0.4)

        return {
            'processing_mode': mode,
            'recognition_speed': round(min(1.0, speed), 4),
            'accuracy_boost': round(accuracy_boost, 4),
            'category': category,
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current state snapshot."""
        return {
            'stats': self._stats.to_dict(),
            'template_counts': {
                'face': self._recognizer.template_count('face'),
                'text': self._recognizer.template_count('text'),
            },
            'last_result': self._last_result,
        }

    def get_stats(self) -> 'FusiformGyrusStats':
        """Return stats dataclass."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable representation."""
        return {
            'n_features': self.n_features,
            'stats': self._stats.to_dict(),
            'template_counts': {
                d: len(ts) for d, ts in self._recognizer._templates.items()
            },
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'FusiformGyrus':
        section = cfg.get('fusiform_gyrus', {})
        return cls(
            n_features=section.get('n_features', 16),
            face_threshold=section.get('face_threshold', 0.5),
            text_threshold=section.get('text_threshold', 0.5),
        )

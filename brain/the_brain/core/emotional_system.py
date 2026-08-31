"""
Emotional System - Amygdala-like Valence/Arousal for Tahlamus

Real brains don't make decisions without emotional coloring. The amygdala
assigns valence (positive/negative) and arousal (calm/excited) to every
experience, which then biases attention, memory retrieval, and routing.

This module implements a simplified Russell circumplex model:
- Valence: -1.0 (fear/disgust) to +1.0 (joy/reward)
- Arousal: 0.0 (calm/sleep) to 1.0 (alert/panic)

Key functions:
1. Assign emotional state to incoming tasks (based on keywords + memory)
2. Modulate routing weights (high arousal + negative valence → threat bias)
3. Bias memory retrieval (emotional congruence effect)
4. Feed into neuromodulation (emotion → neurotransmitter mapping)
5. Emotional learning from feedback (association between tasks and outcomes)

Integration with cognitive loop:
- Called between PERCEIVE and REMEMBER
- Valence/arousal stored in LoopContext
- Affects attention gating strength and memory bias
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime


@dataclass
class EmotionalState:
    """Current emotional state in Russell circumplex model."""
    valence: float = 0.0    # -1 (negative) to +1 (positive)
    arousal: float = 0.0    # 0 (calm) to 1 (aroused)
    dominant_emotion: str = "neutral"
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return {
            'valence': round(self.valence, 3),
            'arousal': round(self.arousal, 3),
            'dominant_emotion': self.dominant_emotion,
            'timestamp': self.timestamp
        }


@dataclass
class EmotionalMemory:
    """Association between a task pattern and its emotional outcome."""
    task_pattern: str
    valence: float
    arousal: float
    strength: float = 1.0  # Decays over time
    timestamp: str = ""


class EmotionalSystemConfig:
    """Configuration for the emotional system."""

    def __init__(
        self,
        valence_decay_rate: float = 0.05,
        arousal_decay_rate: float = 0.1,
        emotional_memory_weight: float = 0.3,
        fear_threshold: float = 0.7,
        reward_threshold: float = 0.7,
        memory_capacity: int = 200,
        learning_rate: float = 0.1
    ):
        self.valence_decay_rate = valence_decay_rate
        self.arousal_decay_rate = arousal_decay_rate
        self.emotional_memory_weight = emotional_memory_weight
        self.fear_threshold = fear_threshold
        self.reward_threshold = reward_threshold
        self.memory_capacity = memory_capacity
        self.learning_rate = learning_rate

    @classmethod
    def from_yaml(cls, yaml_config: Dict) -> 'EmotionalSystemConfig':
        """Create config from YAML config dict (emotional_system section)."""
        es_cfg = yaml_config.get('emotional_system', {})
        return cls(
            valence_decay_rate=es_cfg.get('valence_decay_rate', 0.05),
            arousal_decay_rate=es_cfg.get('arousal_decay_rate', 0.1),
            emotional_memory_weight=es_cfg.get('emotional_memory_weight', 0.3),
            fear_threshold=es_cfg.get('fear_threshold', 0.7),
            reward_threshold=es_cfg.get('reward_threshold', 0.7),
            memory_capacity=es_cfg.get('memory_capacity', 200),
            learning_rate=es_cfg.get('learning_rate', 0.1),
        )


class EmotionalSystem:
    """
    Amygdala-like emotional processing for Tahlamus.

    Maintains a continuous emotional state that influences:
    - Routing weights (threat bias under fear)
    - Memory retrieval (emotional congruence)
    - Attention strength (arousal modulates focus)
    - Neuromodulation (emotion → neurotransmitter mapping)
    """

    # Keyword → (valence, arousal) associations
    EMOTIONAL_KEYWORDS = {
        # Negative valence, high arousal (fear/anger)
        'error': (-0.6, 0.7), 'fail': (-0.7, 0.8), 'crash': (-0.8, 0.9),
        'bug': (-0.5, 0.6), 'broken': (-0.6, 0.7), 'urgent': (-0.3, 0.9),
        'critical': (-0.4, 0.9), 'danger': (-0.8, 0.9), 'attack': (-0.9, 1.0),
        'vulnerability': (-0.7, 0.8), 'threat': (-0.8, 0.9), 'delete': (-0.4, 0.6),
        'destroy': (-0.7, 0.8), 'lost': (-0.6, 0.5), 'timeout': (-0.4, 0.6),
        'emergency': (-0.5, 0.9),

        # Negative valence, low arousal (sadness/boredom)
        'deprecated': (-0.3, 0.2), 'obsolete': (-0.3, 0.2), 'slow': (-0.3, 0.3),
        'boring': (-0.2, 0.1),

        # Positive valence, high arousal (excitement/joy)
        'success': (0.8, 0.7), 'deploy': (0.5, 0.6), 'launch': (0.6, 0.7),
        'new': (0.4, 0.5), 'create': (0.5, 0.5), 'build': (0.5, 0.5),
        'improve': (0.6, 0.5), 'optimize': (0.5, 0.5), 'upgrade': (0.5, 0.6),
        'achieve': (0.7, 0.7), 'complete': (0.6, 0.5), 'solved': (0.8, 0.6),

        # Positive valence, low arousal (contentment/calm)
        'stable': (0.4, 0.2), 'clean': (0.3, 0.2), 'simple': (0.3, 0.2),
        'ready': (0.3, 0.3), 'healthy': (0.5, 0.2), 'safe': (0.5, 0.1),

        # Neutral but high arousal
        'complex': (0.0, 0.6), 'investigate': (0.1, 0.5), 'analyze': (0.1, 0.4),
        'debug': (-0.2, 0.5), 'test': (0.1, 0.3),
    }

    def __init__(self, config: Optional[EmotionalSystemConfig] = None):
        self._config = config or EmotionalSystemConfig()
        self._state = EmotionalState(timestamp=datetime.now().isoformat())
        self._emotional_memories: List[EmotionalMemory] = []
        self._history: List[EmotionalState] = []

    @property
    def state(self) -> EmotionalState:
        return self._state

    def appraise_task(self, task_description: str, task_features: Optional[Dict] = None) -> EmotionalState:
        """
        Appraise a task and update emotional state.
        Combines keyword analysis, memory associations, and task features.
        """
        # 1. Keyword-based appraisal
        kw_valence, kw_arousal = self._keyword_appraisal(task_description)

        # 2. Memory-based appraisal (emotional congruence)
        mem_valence, mem_arousal = self._memory_appraisal(task_description)

        # 3. Feature-based appraisal
        feat_valence, feat_arousal = 0.0, 0.0
        if task_features:
            complexity = task_features.get('complexity', 0.5)
            urgency = task_features.get('urgency', 0.5)
            # High complexity → slight negative valence, high arousal
            feat_valence = -0.2 * (complexity - 0.5)
            feat_arousal = 0.3 * urgency + 0.2 * complexity

        # Combine with weights
        mem_weight = self._config.emotional_memory_weight
        new_valence = (1 - mem_weight) * (kw_valence + feat_valence) + mem_weight * mem_valence
        new_arousal = (1 - mem_weight) * max(kw_arousal, feat_arousal) + mem_weight * mem_arousal

        # Blend with current state (emotional inertia)
        inertia = 0.3
        self._state.valence = np.clip(
            (1 - inertia) * new_valence + inertia * self._state.valence, -1.0, 1.0
        )
        self._state.arousal = np.clip(
            (1 - inertia) * new_arousal + inertia * self._state.arousal, 0.0, 1.0
        )

        # Determine dominant emotion
        self._state.dominant_emotion = self._classify_emotion(
            self._state.valence, self._state.arousal
        )
        self._state.timestamp = datetime.now().isoformat()

        # Store in history
        self._history.append(EmotionalState(
            valence=self._state.valence,
            arousal=self._state.arousal,
            dominant_emotion=self._state.dominant_emotion,
            timestamp=self._state.timestamp
        ))
        if len(self._history) > 100:
            self._history = self._history[-100:]

        return self._state

    def modulate_routing_weights(self, weights: np.ndarray) -> np.ndarray:
        """
        Modulate routing weights based on emotional state.

        High arousal + negative valence → boost threat channel (index 5)
        High arousal + positive valence → boost success/reward channels
        Low arousal → more uniform distribution (less decisive)
        """
        modulated = weights.copy()
        v, a = self._state.valence, self._state.arousal

        if a > self._config.fear_threshold and v < -0.3:
            # Fear response: boost threat modality (index 5 in 6-modality, or related)
            if len(modulated) >= 6:
                threat_boost = a * abs(v) * 0.15
                modulated[5] += threat_boost  # threat channel

        elif a > self._config.reward_threshold and v > 0.3:
            # Reward response: boost success signal if available
            if len(modulated) >= 10:
                reward_boost = a * v * 0.1
                modulated[9] += reward_boost  # success_signal channel

        # Arousal affects distribution sharpness
        if a < 0.2:
            # Very calm → more uniform (less decisive)
            uniform = np.ones_like(modulated) / len(modulated)
            modulated = 0.85 * modulated + 0.15 * uniform

        # Re-normalize to maintain gate sum invariant
        weight_sum = np.sum(modulated)
        if weight_sum > 1e-8:
            modulated = modulated / weight_sum

        return modulated

    def modulate_attention_strength(self, base_strength: float) -> float:
        """Arousal increases attention gating strength."""
        # High arousal → sharper attention
        return base_strength * (1.0 + 0.3 * self._state.arousal)

    def get_neuromodulation_bias(self) -> Dict[str, float]:
        """
        Map emotional state to neurotransmitter biases.
        Returns delta adjustments (not absolute levels).
        """
        v, a = self._state.valence, self._state.arousal

        return {
            # Positive valence → dopamine boost (reward prediction)
            'dopamine_delta': np.clip(v * 0.1 * a, -0.1, 0.1),
            # Arousal → norepinephrine boost (alertness)
            'norepinephrine_delta': np.clip((a - 0.5) * 0.1, -0.05, 0.1),
            # Negative valence → serotonin decrease (distress)
            'serotonin_delta': np.clip(v * 0.05, -0.05, 0.05)
        }

    def learn_from_outcome(self, task_description: str, success: bool, confidence: float):
        """
        Learn emotional associations from task outcomes.
        Creates emotional memories that bias future appraisals.
        """
        if success:
            valence = 0.5 + 0.5 * confidence
            arousal = 0.3 + 0.3 * confidence
        else:
            valence = -0.5 - 0.3 * (1.0 - confidence)
            arousal = 0.5 + 0.3 * (1.0 - confidence)

        # Check for existing association
        for mem in self._emotional_memories:
            if self._task_similarity(task_description, mem.task_pattern) > 0.5:
                lr = self._config.learning_rate
                mem.valence = (1 - lr) * mem.valence + lr * valence
                mem.arousal = (1 - lr) * mem.arousal + lr * arousal
                mem.strength = min(1.0, mem.strength + 0.1)
                mem.timestamp = datetime.now().isoformat()
                return

        # New association
        self._emotional_memories.append(EmotionalMemory(
            task_pattern=task_description,
            valence=valence,
            arousal=arousal,
            timestamp=datetime.now().isoformat()
        ))

        # Capacity management
        if len(self._emotional_memories) > self._config.memory_capacity:
            # Remove weakest associations
            self._emotional_memories.sort(key=lambda m: m.strength, reverse=True)
            self._emotional_memories = self._emotional_memories[:self._config.memory_capacity]

    def decay(self):
        """Apply homeostatic decay toward neutral state."""
        self._state.valence *= (1.0 - self._config.valence_decay_rate)
        self._state.arousal *= (1.0 - self._config.arousal_decay_rate)

        # Decay emotional memory strengths
        for mem in self._emotional_memories:
            mem.strength *= 0.999  # Very slow decay

    def get_state_dict(self) -> Dict:
        """Get emotional system state for dashboard."""
        return {
            'current_state': self._state.to_dict(),
            'emotional_memories_count': len(self._emotional_memories),
            'history_length': len(self._history),
            'recent_emotions': [
                s.dominant_emotion for s in self._history[-5:]
            ]
        }

    # ========== Private Methods ==========

    def _keyword_appraisal(self, text: str) -> Tuple[float, float]:
        """Extract emotional valence/arousal from task keywords."""
        words = text.lower().split()
        total_valence, total_arousal = 0.0, 0.0
        count = 0

        for word in words:
            # Check exact match and partial matches
            for keyword, (v, a) in self.EMOTIONAL_KEYWORDS.items():
                if keyword in word:
                    total_valence += v
                    total_arousal += a
                    count += 1

        if count > 0:
            return (
                np.clip(total_valence / count, -1.0, 1.0),
                np.clip(total_arousal / count, 0.0, 1.0)
            )
        return 0.0, 0.2  # Slightly above zero arousal as default

    def _memory_appraisal(self, text: str) -> Tuple[float, float]:
        """Retrieve emotional associations from memory."""
        if not self._emotional_memories:
            return 0.0, 0.0

        total_v, total_a, total_w = 0.0, 0.0, 0.0
        for mem in self._emotional_memories:
            sim = self._task_similarity(text, mem.task_pattern)
            if sim > 0.2:
                w = sim * mem.strength
                total_v += w * mem.valence
                total_a += w * mem.arousal
                total_w += w

        if total_w > 0:
            return total_v / total_w, total_a / total_w
        return 0.0, 0.0

    def _task_similarity(self, text1: str, text2: str) -> float:
        """Simple word-overlap similarity."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0

    def _classify_emotion(self, valence: float, arousal: float) -> str:
        """Classify emotional state using Russell circumplex quadrants."""
        if arousal > 0.5:
            if valence > 0.3:
                return "excited" if arousal > 0.7 else "happy"
            elif valence < -0.3:
                return "fearful" if arousal > 0.7 else "angry"
            else:
                return "alert"
        else:
            if valence > 0.3:
                return "content" if valence > 0.5 else "relaxed"
            elif valence < -0.3:
                return "sad" if valence < -0.5 else "bored"
            else:
                return "neutral"

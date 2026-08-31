"""
Emotional Memory System (V2 PHASE 6: P6.79-81)

P6.79: EmotionalMemorySystem
  - Links emotions to task outcomes
  - Negative outcomes create "frustration" markers
  - Positive outcomes create "confidence" markers
  - Future similar tasks get emotional bias (caution or confidence)

P6.80: MoodSystem
  - Long-lasting moods that persist across sessions
  - Computed from: success rate, sensor health, user feedback
  - Influences: risk tolerance, communication tone, exploration rate

P6.81: StressResponse
  - Extends homeostatic regulation with stress detection
  - Too many concurrent tasks → sharpen prioritization
  - Too many consecutive errors → become more cautious
  - Chronic stress (>2h) → warn user "I'm overloaded"
  - Recovery mode: force dream-mode
"""

import time
import math
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum

logger = logging.getLogger('brain.emotional_memory')


# ─── P6.79: Emotional Memory System ─────────────────────────────────────

@dataclass
class EmotionalExperience:
    """A recorded emotional experience tied to a task outcome."""
    task_desc: str
    domain: str
    outcome: str             # "success", "failure", "partial"
    emotional_valence: float  # -1 (negative) to +1 (positive)
    emotional_arousal: float  # 0 (calm) to 1 (aroused)
    marker: str = ""          # e.g. "frustration", "confidence", "anxiety"
    strength: float = 1.0     # Decays over time
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if not self.marker:
            self.marker = self._compute_marker()

    def _compute_marker(self) -> str:
        """Derive emotional marker from valence/arousal and outcome."""
        if self.outcome == "failure":
            if self.emotional_arousal > 0.6:
                return "frustration"
            else:
                return "disappointment"
        elif self.outcome == "success":
            if self.emotional_valence > 0.3:
                return "confidence"
            else:
                return "relief"
        else:
            # partial
            if self.emotional_valence < 0:
                return "anxiety"
            else:
                return "cautious_optimism"

    def get_decayed_strength(self, now: float = 0.0) -> float:
        """Get strength with exponential time decay (half-life: 24h)."""
        if now == 0.0:
            now = time.time()
        hours_elapsed = (now - self.timestamp) / 3600.0
        half_life_hours = 24.0
        decay = math.exp(-0.693 * hours_elapsed / half_life_hours)
        return self.strength * decay

    def to_dict(self) -> Dict:
        return {
            'task_desc': self.task_desc[:100],
            'domain': self.domain,
            'outcome': self.outcome,
            'valence': round(self.emotional_valence, 3),
            'arousal': round(self.emotional_arousal, 3),
            'marker': self.marker,
            'strength': round(self.strength, 3),
            'timestamp': self.timestamp,
        }


class EmotionalMemorySystem:
    """
    P6.79: Links emotions to task outcomes for future bias.

    Tasks with negative outcomes get emotional markers like "frustration"
    which make the system more cautious on similar future tasks.
    Positive memories create confidence for similar tasks.
    """

    def __init__(self, max_memories: int = 500,
                 similarity_threshold: float = 0.3,
                 caution_decay_hours: float = 24.0):
        self.max_memories = max_memories
        self.similarity_threshold = similarity_threshold
        self.caution_decay_hours = caution_decay_hours

        self._memories: deque = deque(maxlen=max_memories)
        self._domain_index: Dict[str, List[int]] = defaultdict(list)
        self._total_recorded = 0
        self._marker_counts: Dict[str, int] = defaultdict(int)

    def record_emotional_experience(self, task_desc: str, domain: str,
                                     outcome: str, emotional_valence: float,
                                     emotional_arousal: float) -> EmotionalExperience:
        """
        Record an emotional experience linked to a task outcome.

        Args:
            task_desc: Description of the task
            domain: Domain of the task (e.g., "deployment", "coding")
            outcome: "success", "failure", or "partial"
            emotional_valence: -1 (negative) to +1 (positive)
            emotional_arousal: 0 (calm) to 1 (aroused)

        Returns:
            The recorded EmotionalExperience
        """
        valence = max(-1.0, min(1.0, emotional_valence))
        arousal = max(0.0, min(1.0, emotional_arousal))

        exp = EmotionalExperience(
            task_desc=task_desc,
            domain=domain,
            outcome=outcome,
            emotional_valence=valence,
            emotional_arousal=arousal,
        )

        idx = self._total_recorded
        self._memories.append(exp)
        self._domain_index[domain].append(idx)
        self._total_recorded += 1
        self._marker_counts[exp.marker] += 1

        logger.debug(f"Recorded emotional experience: {exp.marker} for "
                     f"'{task_desc[:40]}' in domain '{domain}' (outcome={outcome})")

        return exp

    def get_emotional_bias(self, task_desc: str, domain: str) -> Dict:
        """
        Get emotional bias for a task based on past emotional memories.

        Returns a dict with:
          - valence_bias: weighted average of past valences for similar tasks
          - arousal_bias: weighted average of past arousals
          - caution_level: 0-1, higher = more cautious (based on negative memories)
          - strategy_hint: "cautious", "confident", or "neutral"
        """
        now = time.time()
        relevant = self._find_similar_memories(task_desc, domain)

        if not relevant:
            return {
                'valence_bias': 0.0,
                'arousal_bias': 0.3,
                'caution_level': 0.0,
                'strategy_hint': 'neutral',
                'matching_memories': 0,
            }

        # Weighted averages by decayed strength
        total_weight = 0.0
        valence_sum = 0.0
        arousal_sum = 0.0
        negative_weight = 0.0
        positive_weight = 0.0

        for mem in relevant:
            w = mem.get_decayed_strength(now)
            total_weight += w
            valence_sum += mem.emotional_valence * w
            arousal_sum += mem.emotional_arousal * w
            if mem.outcome == "failure":
                negative_weight += w
            elif mem.outcome == "success":
                positive_weight += w

        if total_weight < 1e-6:
            return {
                'valence_bias': 0.0,
                'arousal_bias': 0.3,
                'caution_level': 0.0,
                'strategy_hint': 'neutral',
                'matching_memories': len(relevant),
            }

        valence_bias = valence_sum / total_weight
        arousal_bias = arousal_sum / total_weight
        caution_level = negative_weight / (negative_weight + positive_weight + 1e-6)
        caution_level = min(1.0, caution_level)

        # Strategy hint
        if caution_level > 0.6:
            strategy_hint = 'cautious'
        elif caution_level < 0.3 and valence_bias > 0.2:
            strategy_hint = 'confident'
        else:
            strategy_hint = 'neutral'

        return {
            'valence_bias': round(valence_bias, 3),
            'arousal_bias': round(arousal_bias, 3),
            'caution_level': round(caution_level, 3),
            'strategy_hint': strategy_hint,
            'matching_memories': len(relevant),
        }

    def get_emotional_history(self, domain: Optional[str] = None) -> List[Dict]:
        """
        Get emotional memory history, optionally filtered by domain.

        Returns list of emotional memory dicts, most recent first.
        """
        memories = list(self._memories)
        if domain:
            memories = [m for m in memories if m.domain == domain]
        memories.reverse()
        return [m.to_dict() for m in memories[:50]]

    def _find_similar_memories(self, task_desc: str, domain: str) -> List[EmotionalExperience]:
        """Find memories similar to the given task by domain + keyword overlap."""
        candidates = []
        task_words = set(task_desc.lower().split())

        for mem in self._memories:
            # Domain match is the primary filter
            domain_match = (mem.domain == domain)
            # Keyword overlap as secondary similarity
            mem_words = set(mem.task_desc.lower().split())
            if not task_words or not mem_words:
                overlap = 0.0
            else:
                overlap = len(task_words & mem_words) / max(len(task_words | mem_words), 1)

            if domain_match and overlap >= self.similarity_threshold:
                candidates.append(mem)
            elif overlap >= self.similarity_threshold * 2:
                # High keyword match even without domain match
                candidates.append(mem)

        return candidates

    def get_state(self) -> Dict:
        return {
            'total_recorded': self._total_recorded,
            'buffer_size': len(self._memories),
            'marker_counts': dict(self._marker_counts),
            'domains': list(self._domain_index.keys()),
            'recent_memories': [m.to_dict() for m in list(self._memories)[-5:]],
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'EmotionalMemorySystem':
        section = cfg.get('emotional_memory_system', {})
        return cls(
            max_memories=section.get('max_memories', 500),
            similarity_threshold=section.get('similarity_threshold', 0.3),
            caution_decay_hours=section.get('caution_decay_hours', 24.0),
        )


# ─── Core Affect Space (Barrett & Bliss-Moreau 2009) ────────────────────

class CoreAffectSpace:
    """Continuous valence×arousal representation as psychological primitive.

    Based on Russell's circumplex model and Barrett's constructed emotion theory.
    Core affect is the irreducible feeling tone underlying ALL emotional experience.
    Every moment has a core affect position; discrete emotions are constructed from it.

    Research basis:
    - Barrett & Bliss-Moreau (2009): Core affect as psychological primitive, 248 citations
    - Russell (2003): Core affect circumplex model
    - Malézieux, Klein & Gogolla (2023): Neural circuits for emotion, 104 citations
    """

    def __init__(self, inertia: float = 0.85, homeostatic_valence: float = 0.1,
                 homeostatic_arousal: float = 0.3):
        self.valence: float = homeostatic_valence   # -1 (negative) to +1 (positive)
        self.arousal: float = homeostatic_arousal    # 0 (calm) to 1 (activated)
        self.inertia = max(0.0, min(1.0, inertia))
        self.homeostatic_valence = homeostatic_valence
        self.homeostatic_arousal = homeostatic_arousal
        self._history: deque = deque(maxlen=500)
        self._affect_trajectory: deque = deque(maxlen=100)  # short-term trajectory
        self._trait_valence: float = homeostatic_valence  # dispositional baseline
        self._trait_arousal: float = homeostatic_arousal

    def update(self, valence_input: float, arousal_input: float,
               intensity: float = 1.0) -> Dict[str, float]:
        """Update core affect with new input, respecting inertia.

        Args:
            valence_input: Incoming valence signal (-1 to +1)
            arousal_input: Incoming arousal signal (0 to 1)
            intensity: How strongly this input affects core affect (0 to 1)
        """
        v_in = max(-1.0, min(1.0, valence_input))
        a_in = max(0.0, min(1.0, arousal_input))
        intensity = max(0.0, min(1.0, intensity))

        effective_inertia = self.inertia * (1.0 - intensity * 0.3)

        self.valence = effective_inertia * self.valence + (1 - effective_inertia) * v_in
        self.arousal = effective_inertia * self.arousal + (1 - effective_inertia) * a_in

        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))

        now = time.time()
        self._history.append({
            'time': now, 'valence': round(self.valence, 4),
            'arousal': round(self.arousal, 4), 'input_v': round(v_in, 4),
            'input_a': round(a_in, 4)
        })
        self._affect_trajectory.append((now, self.valence, self.arousal))

        return self.get_current()

    def get_current(self) -> Dict[str, float]:
        """Current core affect position."""
        return {
            'valence': round(self.valence, 4),
            'arousal': round(self.arousal, 4),
            'affect_intensity': round(math.sqrt(self.valence**2 + self.arousal**2), 4),
            'quadrant': self._classify_quadrant()
        }

    def construct_emotion(self, context: str = '') -> Dict[str, Any]:
        """Construct a discrete emotion label from current core affect + context.

        Based on Barrett's Theory of Constructed Emotion:
        Core affect + conceptual knowledge + context → emotion category.
        """
        v, a = self.valence, self.arousal

        if v > 0.3 and a > 0.5:
            emotion = 'excitement'
        elif v > 0.3 and a <= 0.5:
            emotion = 'contentment'
        elif v > 0.1 and a > 0.3:
            emotion = 'interest'
        elif v < -0.3 and a > 0.6:
            emotion = 'anxiety'
        elif v < -0.3 and a > 0.3:
            emotion = 'frustration'
        elif v < -0.3 and a <= 0.3:
            emotion = 'sadness'
        elif v < -0.1 and a > 0.5:
            emotion = 'irritation'
        elif abs(v) <= 0.1 and a < 0.2:
            emotion = 'boredom'
        else:
            emotion = 'neutral'

        confidence = min(1.0, math.sqrt(v**2 + (a - 0.3)**2) * 1.5)

        return {
            'emotion': emotion,
            'valence': round(v, 4),
            'arousal': round(a, 4),
            'confidence': round(confidence, 4),
            'context': context
        }

    def get_emotional_disposition(self) -> Dict[str, float]:
        """Trait-level emotional identity — stable affective baseline.

        This represents WHO the agent IS emotionally, not just how it feels now.
        """
        if len(self._history) < 10:
            return {
                'trait_valence': round(self._trait_valence, 4),
                'trait_arousal': round(self._trait_arousal, 4),
                'emotional_stability': 0.5,
                'predominant_affect': 'developing'
            }

        recent = list(self._history)[-100:]
        avg_v = sum(r['valence'] for r in recent) / len(recent)
        avg_a = sum(r['arousal'] for r in recent) / len(recent)

        self._trait_valence = 0.95 * self._trait_valence + 0.05 * avg_v
        self._trait_arousal = 0.95 * self._trait_arousal + 0.05 * avg_a

        v_var = sum((r['valence'] - avg_v)**2 for r in recent) / len(recent)
        a_var = sum((r['arousal'] - avg_a)**2 for r in recent) / len(recent)
        stability = max(0.0, 1.0 - math.sqrt(v_var + a_var))

        if self._trait_valence > 0.2:
            predominant = 'positive'
        elif self._trait_valence < -0.2:
            predominant = 'negative'
        else:
            predominant = 'neutral'

        return {
            'trait_valence': round(self._trait_valence, 4),
            'trait_arousal': round(self._trait_arousal, 4),
            'emotional_stability': round(stability, 4),
            'predominant_affect': predominant
        }

    def homeostatic_drift(self) -> None:
        """Slowly return toward homeostatic baseline (allostatic regulation)."""
        drift_rate = 0.02
        self.valence += (self.homeostatic_valence - self.valence) * drift_rate
        self.arousal += (self.homeostatic_arousal - self.arousal) * drift_rate

    def _classify_quadrant(self) -> str:
        """Classify current affect into circumplex quadrant."""
        if self.valence >= 0 and self.arousal >= 0.4:
            return 'high_energy_pleasant'
        elif self.valence >= 0 and self.arousal < 0.4:
            return 'low_energy_pleasant'
        elif self.valence < 0 and self.arousal >= 0.4:
            return 'high_energy_unpleasant'
        else:
            return 'low_energy_unpleasant'

    def get_state(self) -> Dict[str, Any]:
        return {
            'current': self.get_current(),
            'disposition': self.get_emotional_disposition(),
            'history_length': len(self._history),
            'homeostatic_target': {
                'valence': self.homeostatic_valence,
                'arousal': self.homeostatic_arousal
            }
        }


# ─── P6.80: Mood System ─────────────────────────────────────────────────

class MoodLabel(Enum):
    """Mood labels based on valence-arousal quadrants."""
    CONTENT = "content"       # positive valence, low arousal
    ENERGIZED = "energized"   # positive valence, high arousal
    STRESSED = "stressed"     # negative valence, high arousal
    DRAINED = "drained"       # negative valence, low arousal
    NEUTRAL = "neutral"       # near-zero valence and arousal


@dataclass
class MoodState:
    """Current mood state."""
    valence: float = 0.0      # -1 (negative) to +1 (positive)
    arousal: float = 0.3      # 0 (calm) to 1 (aroused)
    label: str = "neutral"
    stability: float = 0.5    # 0 (volatile) to 1 (stable)
    last_updated: float = 0.0

    def __post_init__(self):
        if self.last_updated == 0.0:
            self.last_updated = time.time()

    def to_dict(self) -> Dict:
        return {
            'valence': round(self.valence, 3),
            'arousal': round(self.arousal, 3),
            'label': self.label,
            'stability': round(self.stability, 3),
            'last_updated': self.last_updated,
        }


class MoodSystem:
    """
    P6.80: Long-lasting moods that persist across sessions.

    Mood is computed from:
      - success_rate over the last 24h
      - sensor/system health status
      - user feedback tone (positive/negative)

    Mood influences:
      - risk_tolerance (0-1): how willing to try risky strategies
      - communication_tone: "positive", "neutral", "cautious"
      - exploration_rate (0-1): how much to explore vs exploit
    """

    def __init__(self, inertia: float = 0.85,
                 valence_sensitivity: float = 0.5,
                 arousal_sensitivity: float = 0.4,
                 history_window: int = 100):
        self.inertia = inertia  # How much previous mood carries forward (0-1)
        self.valence_sensitivity = valence_sensitivity
        self.arousal_sensitivity = arousal_sensitivity
        self.history_window = history_window

        self._mood = MoodState()
        self._mood_history: deque = deque(maxlen=history_window)
        self._update_count = 0

    def update_mood(self, success_rate_24h: float,
                    sensor_health: float,
                    user_feedback_score: float) -> MoodState:
        """
        Update the mood based on current signals.

        Args:
            success_rate_24h: 0-1, proportion of successful tasks in last 24h
            sensor_health: 0-1, overall system health (1 = all green)
            user_feedback_score: -1 to +1, average recent user feedback tone

        Returns:
            Updated MoodState
        """
        # Compute target valence from signals
        # success_rate maps 0-1 to valence -0.5..+1.0
        success_valence = (success_rate_24h - 0.5) * 2.0
        # sensor_health maps 0-1 to valence -0.3..+0.3
        health_valence = (sensor_health - 0.5) * 0.6
        # user_feedback_score is already -1..+1
        feedback_valence = user_feedback_score

        # Weighted combination
        target_valence = (
            0.4 * success_valence +
            0.2 * health_valence +
            0.4 * feedback_valence
        )
        target_valence = max(-1.0, min(1.0, target_valence))

        # Compute target arousal
        # Low success + bad health = high arousal (stress)
        # High success + good health = moderate arousal (contentment)
        stress_signal = (1.0 - success_rate_24h) * (1.0 - sensor_health)
        engagement_signal = success_rate_24h * 0.5
        target_arousal = 0.3 + stress_signal * 0.5 + engagement_signal * 0.3
        target_arousal = max(0.0, min(1.0, target_arousal))

        # Apply inertia: mood changes slowly
        new_valence = (self.inertia * self._mood.valence +
                       (1.0 - self.inertia) * target_valence * self.valence_sensitivity +
                       (1.0 - self.inertia) * (1.0 - self.valence_sensitivity) * target_valence)
        new_arousal = (self.inertia * self._mood.arousal +
                       (1.0 - self.inertia) * target_arousal * self.arousal_sensitivity +
                       (1.0 - self.inertia) * (1.0 - self.arousal_sensitivity) * target_arousal)

        new_valence = max(-1.0, min(1.0, new_valence))
        new_arousal = max(0.0, min(1.0, new_arousal))

        # Compute label from valence-arousal quadrant
        label = self._compute_label(new_valence, new_arousal)

        # Stability: how consistent has mood been recently?
        stability = self._compute_stability(new_valence, new_arousal)

        self._mood = MoodState(
            valence=new_valence,
            arousal=new_arousal,
            label=label,
            stability=stability,
        )
        self._mood_history.append(self._mood)
        self._update_count += 1

        logger.debug(f"Mood updated: {label} (v={new_valence:.2f}, a={new_arousal:.2f})")

        return self._mood

    def get_mood(self) -> MoodState:
        """Get the current mood state."""
        return self._mood

    def get_behavioral_modifiers(self) -> Dict:
        """
        Get behavioral modifiers derived from current mood.

        Returns:
            dict with:
              - risk_tolerance (0-1): higher when positive mood
              - communication_tone: "positive", "neutral", "cautious"
              - exploration_rate (0-1): higher when energized
        """
        v = self._mood.valence
        a = self._mood.arousal

        # Risk tolerance: positive mood + moderate arousal = more risk-tolerant
        risk_tolerance = 0.5 + v * 0.3 + (0.5 - abs(a - 0.5)) * 0.2
        risk_tolerance = max(0.1, min(0.95, risk_tolerance))

        # Communication tone
        if v > 0.3:
            communication_tone = 'positive'
        elif v < -0.3:
            communication_tone = 'cautious'
        else:
            communication_tone = 'neutral'

        # Exploration rate: high when energized, low when drained
        exploration_rate = 0.5 + v * 0.2 + a * 0.2
        exploration_rate = max(0.1, min(0.9, exploration_rate))

        return {
            'risk_tolerance': round(risk_tolerance, 3),
            'communication_tone': communication_tone,
            'exploration_rate': round(exploration_rate, 3),
        }

    def save_state(self) -> Dict:
        """Save mood state for persistence across sessions."""
        return {
            'valence': self._mood.valence,
            'arousal': self._mood.arousal,
            'label': self._mood.label,
            'stability': self._mood.stability,
            'update_count': self._update_count,
        }

    def load_state(self, state: Dict) -> None:
        """Load mood state from a previously saved state."""
        self._mood = MoodState(
            valence=state.get('valence', 0.0),
            arousal=state.get('arousal', 0.3),
            label=state.get('label', 'neutral'),
            stability=state.get('stability', 0.5),
        )
        self._update_count = state.get('update_count', 0)
        logger.info(f"Mood state loaded: {self._mood.label}")

    def _compute_label(self, valence: float, arousal: float) -> str:
        """Compute mood label from valence-arousal coordinates."""
        if abs(valence) < 0.15 and abs(arousal - 0.3) < 0.15:
            return MoodLabel.NEUTRAL.value
        if valence >= 0:
            if arousal >= 0.5:
                return MoodLabel.ENERGIZED.value
            else:
                return MoodLabel.CONTENT.value
        else:
            if arousal >= 0.5:
                return MoodLabel.STRESSED.value
            else:
                return MoodLabel.DRAINED.value

    def _compute_stability(self, new_v: float, new_a: float) -> float:
        """Compute mood stability from recent history."""
        if len(self._mood_history) < 3:
            return 0.5

        recent = list(self._mood_history)[-10:]
        valences = [m.valence for m in recent] + [new_v]
        arousals = [m.arousal for m in recent] + [new_a]

        # Variance-based stability (low variance = high stability)
        v_mean = sum(valences) / len(valences)
        a_mean = sum(arousals) / len(arousals)
        v_var = sum((v - v_mean) ** 2 for v in valences) / len(valences)
        a_var = sum((a - a_mean) ** 2 for a in arousals) / len(arousals)

        # Convert variance to stability: high variance = low stability
        combined_var = (v_var + a_var) / 2.0
        stability = max(0.0, min(1.0, 1.0 - combined_var * 4.0))
        return stability

    def get_state(self) -> Dict:
        return {
            'mood': self._mood.to_dict(),
            'behavioral_modifiers': self.get_behavioral_modifiers(),
            'update_count': self._update_count,
            'history_size': len(self._mood_history),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'MoodSystem':
        section = cfg.get('mood_system', {})
        instance = cls(
            inertia=section.get('inertia', 0.85),
            valence_sensitivity=section.get('valence_sensitivity', 0.5),
            arousal_sensitivity=section.get('arousal_sensitivity', 0.4),
            history_window=section.get('history_window', 100),
        )
        # Load persisted state if provided
        persisted = section.get('persisted_state', None)
        if persisted:
            instance.load_state(persisted)
        return instance


# ─── P6.81: Stress Response ──────────────────────────────────────────────

class StressLevel(Enum):
    """Stress level categories."""
    CALM = "calm"                # 0.0 - 0.2
    MILD = "mild"                # 0.2 - 0.4
    MODERATE = "moderate"        # 0.4 - 0.6
    HIGH = "high"                # 0.6 - 0.8
    EXTREME = "extreme"          # 0.8 - 1.0


@dataclass
class StressEvent:
    """A recorded stress event."""
    event_type: str    # 'task_start', 'task_complete', 'task_error', 'user_feedback'
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class StressResponse:
    """
    P6.81: Extends homeostatic regulation with stress detection.

    Monitors:
      - concurrent task load (too many tasks → stress)
      - consecutive errors (too many errors → caution)
      - chronic stress duration (>2h sustained high stress → warn user)

    Responses:
      - Sharpen prioritization under load
      - Become more cautious after errors
      - Warn user about overload
      - Force dream-mode for recovery
    """

    def __init__(self, max_concurrent_tasks: int = 10,
                 error_window_minutes: float = 30.0,
                 chronic_threshold_hours: float = 2.0,
                 recovery_threshold: float = 0.85,
                 event_buffer_size: int = 1000):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.error_window_minutes = error_window_minutes
        self.chronic_threshold_hours = chronic_threshold_hours
        self.recovery_threshold = recovery_threshold  # Stress level above which recovery is needed

        self._events: deque = deque(maxlen=event_buffer_size)
        self._active_tasks: int = 0
        self._consecutive_errors: int = 0
        self._stress_level: float = 0.0
        self._high_stress_start: Optional[float] = None  # When sustained high stress began
        self._total_events: int = 0
        self._total_warnings: int = 0
        self._total_recoveries: int = 0
        self._last_stress_update: float = time.time()

    def record_event(self, event_type: str) -> None:
        """
        Record a stress event.

        Args:
            event_type: One of 'task_start', 'task_complete', 'task_error', 'user_feedback'
        """
        valid_types = ('task_start', 'task_complete', 'task_error', 'user_feedback')
        if event_type not in valid_types:
            logger.warning(f"Unknown stress event type: {event_type}")
            return

        event = StressEvent(event_type=event_type)
        self._events.append(event)
        self._total_events += 1

        # Update task tracking
        if event_type == 'task_start':
            self._active_tasks += 1
            self._consecutive_errors = 0  # Starting new task resets error streak
        elif event_type == 'task_complete':
            self._active_tasks = max(0, self._active_tasks - 1)
            self._consecutive_errors = 0
        elif event_type == 'task_error':
            self._active_tasks = max(0, self._active_tasks - 1)
            self._consecutive_errors += 1
        elif event_type == 'user_feedback':
            # User feedback is a mild stress reducer (someone is paying attention)
            pass

        # Recompute stress level
        self._update_stress_level()

    def get_stress_level(self) -> float:
        """
        Get current stress level (0-1).

        Combines:
          - Task load stress
          - Error stress
          - Time-based stress accumulation
        """
        return self._stress_level

    def should_warn_user(self) -> bool:
        """
        Check if chronic stress warrants warning the user.

        Returns True if stress has been above 0.6 for longer than
        chronic_threshold_hours (default 2h).
        """
        if self._stress_level < 0.6:
            return False

        if self._high_stress_start is None:
            return False

        now = time.time()
        duration_hours = (now - self._high_stress_start) / 3600.0
        if duration_hours >= self.chronic_threshold_hours:
            self._total_warnings += 1
            logger.warning(f"Chronic stress detected: {duration_hours:.1f}h "
                           f"at stress level {self._stress_level:.2f}")
            return True

        return False

    def should_enter_recovery(self) -> bool:
        """
        Check if stress is extreme enough to force dream-mode recovery.

        Returns True if stress is above recovery_threshold (default 0.85).
        """
        if self._stress_level >= self.recovery_threshold:
            self._total_recoveries += 1
            logger.warning(f"Extreme stress {self._stress_level:.2f} — "
                           f"recommending recovery mode")
            return True
        return False

    def get_behavioral_adjustments(self) -> Dict:
        """
        Get behavioral adjustments based on current stress.

        Returns:
            dict with:
              - caution_multiplier (1.0-2.0): multiply caution by this
              - priority_strictness (0-1): how strict prioritization should be
              - max_concurrent_tasks: adjusted max concurrent tasks
        """
        stress = self._stress_level

        # Caution multiplier: more cautious under stress
        caution_multiplier = 1.0 + stress * 1.0  # 1.0 at calm, 2.0 at extreme
        caution_multiplier = min(2.0, caution_multiplier)

        # Priority strictness: stricter under load
        priority_strictness = min(1.0, 0.3 + stress * 0.7)

        # Reduce max concurrent tasks under stress
        stress_factor = max(0.3, 1.0 - stress * 0.5)
        adjusted_max = max(1, int(self.max_concurrent_tasks * stress_factor))

        return {
            'caution_multiplier': round(caution_multiplier, 3),
            'priority_strictness': round(priority_strictness, 3),
            'max_concurrent_tasks': adjusted_max,
        }

    def _update_stress_level(self) -> None:
        """Recompute the stress level from all signals."""
        now = time.time()

        # Component 1: Task load stress (0-1)
        load_stress = min(1.0, self._active_tasks / max(1, self.max_concurrent_tasks))

        # Component 2: Error stress (0-1)
        # Based on consecutive errors (sigmoid-like curve)
        error_stress = min(1.0, self._consecutive_errors / 5.0)

        # Component 3: Error rate in recent window
        window_start = now - self.error_window_minutes * 60.0
        recent_events = [e for e in self._events if e.timestamp >= window_start]
        recent_errors = sum(1 for e in recent_events if e.event_type == 'task_error')
        recent_total = sum(1 for e in recent_events
                           if e.event_type in ('task_complete', 'task_error'))
        if recent_total > 0:
            error_rate_stress = recent_errors / recent_total
        else:
            error_rate_stress = 0.0

        # Combine stress signals (weighted)
        self._stress_level = (
            0.35 * load_stress +
            0.35 * error_stress +
            0.30 * error_rate_stress
        )
        self._stress_level = max(0.0, min(1.0, self._stress_level))

        # Track chronic stress duration
        if self._stress_level >= 0.6:
            if self._high_stress_start is None:
                self._high_stress_start = now
        else:
            self._high_stress_start = None

        self._last_stress_update = now

    def get_stress_category(self) -> str:
        """Get the stress category label."""
        s = self._stress_level
        if s < 0.2:
            return StressLevel.CALM.value
        elif s < 0.4:
            return StressLevel.MILD.value
        elif s < 0.6:
            return StressLevel.MODERATE.value
        elif s < 0.8:
            return StressLevel.HIGH.value
        else:
            return StressLevel.EXTREME.value

    def get_state(self) -> Dict:
        chronic_duration = 0.0
        if self._high_stress_start is not None:
            chronic_duration = (time.time() - self._high_stress_start) / 3600.0

        return {
            'stress_level': round(self._stress_level, 3),
            'stress_category': self.get_stress_category(),
            'active_tasks': self._active_tasks,
            'consecutive_errors': self._consecutive_errors,
            'chronic_stress_hours': round(chronic_duration, 2),
            'should_warn_user': self.should_warn_user(),
            'should_enter_recovery': self.should_enter_recovery(),
            'behavioral_adjustments': self.get_behavioral_adjustments(),
            'total_events': self._total_events,
            'total_warnings': self._total_warnings,
            'total_recoveries': self._total_recoveries,
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'StressResponse':
        section = cfg.get('stress_response', {})
        return cls(
            max_concurrent_tasks=section.get('max_concurrent_tasks', 10),
            error_window_minutes=section.get('error_window_minutes', 30.0),
            chronic_threshold_hours=section.get('chronic_threshold_hours', 2.0),
            recovery_threshold=section.get('recovery_threshold', 0.85),
            event_buffer_size=section.get('event_buffer_size', 1000),
        )

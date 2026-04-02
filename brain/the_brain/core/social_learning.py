"""
Social Learning System (V2 PHASE 5: P5.73-75)

P5.73: LearningFromDemonstration
  - Observes user actions and learns from them
  - User corrections are recorded as preference signals
  - Tracks when user's method differs from system's suggestion

P5.74: FeedbackInterpretation
  - Nuanced understanding of user feedback
  - Sentiment analysis on feedback text
  - Maps feedback to partial success/failure signals

P5.75: CollaborativeLearning
  - Learns from dialogue and user explanations
  - Stores user strategies as declarative knowledge
  - Prefers user strategies in similar future situations
"""

import time
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.social_learning')


# ─── P5.73: Learning From Demonstration ─────────────────────────────────

@dataclass
class DemonstrationRecord:
    """A recorded user demonstration (action they took instead of system's)."""
    context: str                 # What task was being done
    system_suggestion: str       # What the system suggested
    user_action: str             # What the user actually did
    domain: str = ""
    was_correction: bool = False  # True if user corrected system output
    user_succeeded: bool = True   # Whether user's approach succeeded
    timestamp: float = 0.0
    learned: bool = False         # Whether this has been incorporated

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        return {
            'context': self.context,
            'system_suggestion': self.system_suggestion,
            'user_action': self.user_action,
            'domain': self.domain,
            'was_correction': self.was_correction,
            'user_succeeded': self.user_succeeded,
            'timestamp': self.timestamp,
            'learned': self.learned,
        }


class LearningFromDemonstration:
    """
    P5.73: Learns from observing user actions.

    When a user takes an action different from the system's suggestion,
    or corrects the system's output, it's recorded as a learning signal.
    Over time, preferred user patterns are identified.
    """

    def __init__(self, max_demonstrations: int = 500,
                 preference_threshold: int = 3):
        self.max_demonstrations = max_demonstrations
        self.preference_threshold = preference_threshold  # Min times to establish preference
        self._demonstrations: deque = deque(maxlen=max_demonstrations)
        self._user_preferences: Dict[str, Dict] = {}  # context_key -> preference
        self._total_demonstrations = 0
        self._total_preferences_learned = 0

    def record_demonstration(self, context: str, system_suggestion: str,
                              user_action: str, domain: str = "",
                              was_correction: bool = False,
                              user_succeeded: bool = True) -> None:
        """Record a user demonstration."""
        demo = DemonstrationRecord(
            context=context,
            system_suggestion=system_suggestion,
            user_action=user_action,
            domain=domain,
            was_correction=was_correction,
            user_succeeded=user_succeeded,
        )
        self._demonstrations.append(demo)
        self._total_demonstrations += 1

        # Check for preference patterns
        if user_action != system_suggestion and user_succeeded:
            self._update_preference(context, domain, user_action)

    def _update_preference(self, context: str, domain: str, user_action: str) -> None:
        """Track user preference for a context."""
        # Simple key: first 3 significant words of context
        words = [w for w in context.lower().split() if len(w) > 3][:3]
        key = "_".join(words) if words else context[:30]

        if key not in self._user_preferences:
            self._user_preferences[key] = {
                'domain': domain,
                'actions': defaultdict(int),
                'total': 0,
                'preferred_action': '',
            }

        pref = self._user_preferences[key]
        pref['actions'][user_action] += 1
        pref['total'] += 1

        # Check if any action has enough occurrences
        for action, count in pref['actions'].items():
            if count >= self.preference_threshold:
                if pref['preferred_action'] != action:
                    pref['preferred_action'] = action
                    self._total_preferences_learned += 1

    def get_user_preference(self, context: str) -> Optional[str]:
        """Get the user's preferred action for a context, if known."""
        words = [w for w in context.lower().split() if len(w) > 3][:3]
        key = "_".join(words) if words else context[:30]
        pref = self._user_preferences.get(key)
        if pref and pref['preferred_action']:
            return pref['preferred_action']
        return None

    def get_recent_demonstrations(self, n: int = 10) -> List[Dict]:
        """Get recent demonstrations."""
        return [d.to_dict() for d in list(self._demonstrations)[-n:]]

    def get_state(self) -> Dict:
        return {
            'total_demonstrations': self._total_demonstrations,
            'buffer_size': len(self._demonstrations),
            'preferences_learned': self._total_preferences_learned,
            'tracked_contexts': len(self._user_preferences),
        }


# ─── P5.74: Feedback Interpretation ────────────────────────────────────

class FeedbackSentiment(Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


@dataclass
class InterpretedFeedback:
    """Interpreted user feedback with nuance."""
    raw_text: str
    sentiment: FeedbackSentiment
    confidence: float            # How confident in the interpretation
    outcome_signal: float        # -1 (failure) to 1 (success), can be partial
    aspects: Dict[str, float]    # Aspect-level feedback, e.g. {"speed": -0.5, "accuracy": 0.8}
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        return {
            'raw_text': self.raw_text[:100],
            'sentiment': self.sentiment.value,
            'confidence': round(self.confidence, 3),
            'outcome_signal': round(self.outcome_signal, 3),
            'aspects': {k: round(v, 3) for k, v in self.aspects.items()},
        }


class FeedbackInterpretation:
    """
    P5.74: Nuanced understanding of user feedback.

    Analyzes feedback text to extract sentiment, partial success
    signals, and aspect-level feedback.
    """

    # Sentiment keyword lists
    POSITIVE_WORDS = {
        'good', 'great', 'nice', 'excellent', 'perfect', 'correct', 'right',
        'awesome', 'helpful', 'thanks', 'thank', 'well', 'done', 'yes',
        'exactly', 'super', 'works', 'working', 'fixed', 'solved',
        'gut', 'prima', 'richtig', 'danke', 'perfekt', 'toll', 'super',
    }

    NEGATIVE_WORDS = {
        'wrong', 'bad', 'no', 'incorrect', 'error', 'broken', 'fail',
        'slow', 'ugly', 'worse', 'terrible', 'awful', 'not', 'don\'t',
        'never', 'stop', 'mistake', 'issue', 'problem', 'bug',
        'falsch', 'schlecht', 'nein', 'fehler', 'kaputt', 'langsam',
    }

    PARTIAL_WORDS = {
        'but', 'however', 'almost', 'close', 'partly', 'partially',
        'direction', 'heading', 'kinda', 'sort of', 'mostly',
        'aber', 'fast', 'teilweise', 'richtung', 'ungefähr',
    }

    ASPECT_KEYWORDS = {
        'speed': ['fast', 'slow', 'quick', 'long', 'time', 'schnell', 'langsam'],
        'accuracy': ['correct', 'wrong', 'right', 'error', 'accurate', 'richtig', 'falsch'],
        'completeness': ['missing', 'incomplete', 'partial', 'full', 'complete', 'fehlt'],
        'clarity': ['clear', 'confusing', 'understandable', 'unclear', 'klar', 'unklar'],
        'helpfulness': ['helpful', 'useful', 'useless', 'unhelpful', 'hilfreich', 'nutzlos'],
    }

    def __init__(self):
        self._history: deque = deque(maxlen=200)
        self._total_interpreted = 0
        self._sentiment_counts: Dict[str, int] = defaultdict(int)

    def interpret(self, feedback_text: str) -> InterpretedFeedback:
        """Interpret a piece of user feedback."""
        text_lower = feedback_text.lower()
        words = set(re.findall(r'\w+', text_lower))

        # Count sentiment words
        positive_count = len(words & self.POSITIVE_WORDS)
        negative_count = len(words & self.NEGATIVE_WORDS)
        partial_count = len(words & self.PARTIAL_WORDS)

        # Determine sentiment
        net = positive_count - negative_count
        has_partial = partial_count > 0

        if net >= 2:
            sentiment = FeedbackSentiment.VERY_POSITIVE
            outcome = 1.0
        elif net >= 1:
            sentiment = FeedbackSentiment.POSITIVE
            outcome = 0.7
        elif net <= -2:
            sentiment = FeedbackSentiment.VERY_NEGATIVE
            outcome = -1.0
        elif net <= -1:
            sentiment = FeedbackSentiment.NEGATIVE
            outcome = -0.7
        else:
            sentiment = FeedbackSentiment.NEUTRAL
            outcome = 0.0

        # Partial modifier: "good but slow" -> partial success
        if has_partial and outcome > 0:
            outcome *= 0.5
            sentiment = FeedbackSentiment.POSITIVE  # Downgrade from very positive
        elif has_partial and net == 0 and positive_count > 0:
            # Mixed sentiment with partial words: "good direction, but too slow"
            # Positive intent qualified by criticism → slight positive
            sentiment = FeedbackSentiment.POSITIVE
            outcome = 0.3

        # Aspect-level analysis
        aspects = {}
        for aspect, keywords in self.ASPECT_KEYWORDS.items():
            aspect_positive = sum(1 for k in keywords
                                  if k in text_lower and k in self.POSITIVE_WORDS)
            aspect_negative = sum(1 for k in keywords
                                  if k in text_lower and k in self.NEGATIVE_WORDS)
            has_mention = any(k in text_lower for k in keywords)
            if has_mention:
                aspects[aspect] = (aspect_positive - aspect_negative) / max(1, aspect_positive + aspect_negative)

        # Confidence based on how much signal we found
        total_signal = positive_count + negative_count + partial_count
        confidence = min(0.95, 0.3 + total_signal * 0.15)

        result = InterpretedFeedback(
            raw_text=feedback_text,
            sentiment=sentiment,
            confidence=confidence,
            outcome_signal=outcome,
            aspects=aspects,
        )

        self._history.append(result)
        self._total_interpreted += 1
        self._sentiment_counts[sentiment.value] += 1

        return result

    def get_average_sentiment(self, window: int = 20) -> float:
        """Get average outcome signal from recent feedback."""
        recent = list(self._history)[-window:]
        if not recent:
            return 0.0
        return sum(f.outcome_signal for f in recent) / len(recent)

    def get_aspect_trends(self) -> Dict[str, float]:
        """Get average aspect ratings from recent feedback."""
        recent = list(self._history)[-50:]
        if not recent:
            return {}

        aspect_sums: Dict[str, List[float]] = defaultdict(list)
        for fb in recent:
            for aspect, value in fb.aspects.items():
                aspect_sums[aspect].append(value)

        return {k: round(sum(v) / len(v), 3) for k, v in aspect_sums.items() if v}

    def get_state(self) -> Dict:
        return {
            'total_interpreted': self._total_interpreted,
            'sentiment_distribution': dict(self._sentiment_counts),
            'average_sentiment': round(self.get_average_sentiment(), 3),
            'aspect_trends': self.get_aspect_trends(),
        }


# ─── P5.75: Collaborative Learning ─────────────────────────────────────

@dataclass
class StrategyNode:
    """A learned strategy from user explanation."""
    strategy_id: str
    context: str              # When to use this strategy
    description: str          # What the strategy is
    source: str               # "user_explanation", "user_correction", "dialogue"
    domain: str = ""
    usage_count: int = 0
    success_count: int = 0
    confidence: float = 0.5
    created_at: float = 0.0
    last_used_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def record_usage(self, success: bool) -> None:
        self.usage_count += 1
        if success:
            self.success_count += 1
        self.confidence = self.success_count / max(self.usage_count, 1)
        self.last_used_at = time.time()

    def to_dict(self) -> Dict:
        return {
            'strategy_id': self.strategy_id,
            'context': self.context,
            'description': self.description,
            'source': self.source,
            'domain': self.domain,
            'usage_count': self.usage_count,
            'success_rate': round(self.success_count / max(self.usage_count, 1), 3),
            'confidence': round(self.confidence, 3),
        }


class CollaborativeLearning:
    """
    P5.75: Learns from dialogue and user explanations.

    When a user explains why they prefer a certain approach,
    the explanation is stored as declarative knowledge and
    preferred in future similar situations.
    """

    def __init__(self, max_strategies: int = 200,
                 min_confidence_to_apply: float = 0.4):
        self.max_strategies = max_strategies
        self.min_confidence_to_apply = min_confidence_to_apply
        self._strategies: Dict[str, StrategyNode] = {}
        self._domain_index: Dict[str, List[str]] = defaultdict(list)
        self._total_learned = 0
        self._strategy_counter = 0

    def learn_from_explanation(self, context: str, explanation: str,
                                domain: str = "") -> StrategyNode:
        """
        Learn a strategy from user explanation.

        E.g., user says "I prefer X because Y" — store as strategy.
        """
        self._strategy_counter += 1
        strategy_id = f"strat_{self._strategy_counter}"

        node = StrategyNode(
            strategy_id=strategy_id,
            context=context,
            description=explanation,
            source="user_explanation",
            domain=domain,
            confidence=0.7,  # User explanations start with decent confidence
        )

        self._add_strategy(node)
        return node

    def learn_from_correction(self, context: str, wrong_action: str,
                               correct_action: str, domain: str = "") -> StrategyNode:
        """
        Learn from a user correction.

        E.g., system did X, user corrected to Y.
        """
        self._strategy_counter += 1
        strategy_id = f"strat_{self._strategy_counter}"

        node = StrategyNode(
            strategy_id=strategy_id,
            context=context,
            description=f"Prefer '{correct_action}' over '{wrong_action}'",
            source="user_correction",
            domain=domain,
            confidence=0.8,  # Corrections are high confidence
        )

        self._add_strategy(node)
        return node

    def learn_from_dialogue(self, context: str, user_statement: str,
                             domain: str = "") -> Optional[StrategyNode]:
        """
        Extract strategy from dialogue context.

        Looks for strategy signals like "because", "instead", "prefer".
        """
        lower = user_statement.lower()
        strategy_signals = ['because', 'instead', 'prefer', 'better',
                            'should', 'always', 'never', 'weil', 'stattdessen',
                            'lieber', 'besser', 'immer', 'nie']

        has_signal = any(s in lower for s in strategy_signals)
        if not has_signal:
            return None

        self._strategy_counter += 1
        strategy_id = f"strat_{self._strategy_counter}"

        node = StrategyNode(
            strategy_id=strategy_id,
            context=context,
            description=user_statement,
            source="dialogue",
            domain=domain,
            confidence=0.5,  # Dialogue strategies need validation
        )

        self._add_strategy(node)
        return node

    def get_applicable_strategies(self, context: str, domain: str = "",
                                    top_k: int = 5) -> List[StrategyNode]:
        """Find strategies applicable to the current context."""
        # Search by domain first
        candidates = []
        if domain:
            for sid in self._domain_index.get(domain, []):
                if sid in self._strategies:
                    candidates.append(self._strategies[sid])

        # Also search by context keyword overlap
        context_words = set(context.lower().split())
        for strategy in self._strategies.values():
            if strategy.confidence < self.min_confidence_to_apply:
                continue
            strat_words = set(strategy.context.lower().split())
            overlap = len(context_words & strat_words)
            if overlap >= 2 and strategy not in candidates:
                candidates.append(strategy)

        # Sort: user_explanation > user_correction > dialogue, then by confidence
        source_priority = {'user_correction': 3, 'user_explanation': 2, 'dialogue': 1}
        candidates.sort(
            key=lambda s: (source_priority.get(s.source, 0), s.confidence),
            reverse=True
        )
        return candidates[:top_k]

    def record_strategy_outcome(self, strategy_id: str, success: bool) -> None:
        """Record outcome when a strategy was applied."""
        strategy = self._strategies.get(strategy_id)
        if strategy:
            strategy.record_usage(success)

    def _add_strategy(self, node: StrategyNode) -> None:
        if len(self._strategies) >= self.max_strategies:
            self._evict_weakest()
        self._strategies[node.strategy_id] = node
        if node.domain:
            self._domain_index[node.domain].append(node.strategy_id)
        self._total_learned += 1

    def _evict_weakest(self) -> None:
        if self._strategies:
            worst = min(self._strategies.values(), key=lambda s: s.confidence)
            del self._strategies[worst.strategy_id]

    def get_state(self) -> Dict:
        by_source = defaultdict(int)
        for s in self._strategies.values():
            by_source[s.source] += 1

        return {
            'total_strategies': len(self._strategies),
            'total_learned': self._total_learned,
            'by_source': dict(by_source),
            'domains': list(self._domain_index.keys()),
            'top_strategies': [s.to_dict() for s in
                               sorted(self._strategies.values(),
                                      key=lambda s: s.confidence, reverse=True)[:5]],
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'CollaborativeLearning':
        section = cfg.get('collaborative_learning', {})
        return cls(
            max_strategies=section.get('max_strategies', 200),
            min_confidence_to_apply=section.get('min_confidence_to_apply', 0.4),
        )

"""
Sensory Preprocessing Pipeline - Feature Extraction for Tahlamus

Real brains don't process raw sensory data at the thalamus - the input
goes through layers of preprocessing first (retina → LGN → V1, etc.).

This module extracts structured features from raw text input before
it reaches the thalamic routing system, making the 10 modalities
more meaningful than simple random projections.

Feature channels extracted:
1. Lexical features    - word count, vocabulary richness, sentence structure
2. Semantic features   - topic keywords, named entities, domain signals
3. Syntactic features  - question marks, imperatives, code blocks
4. Temporal features   - time references, urgency signals, deadlines
5. Emotional features  - valence/arousal from keywords (feeds emotional system)
6. Complexity features - nested clauses, technical jargon, abstraction level
7. Intent features     - action verbs, question types, request patterns
8. Domain features     - coding, deployment, analysis, communication signals
9. Risk features       - destructive operations, security concerns, data loss
10. Social features    - mentions of users, teams, collaboration signals

Integration:
- Called at the beginning of PERCEIVE phase in cognitive loop
- Output feeds into Layer 1 (TaskFeatureRouter) as enriched input
- Risk features feed into Layer 4 (Temporal Router) for safety checks
"""

import re
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class SensoryFeatures:
    """Extracted sensory features from raw text input."""

    # Per-channel feature vectors (normalized 0-1)
    lexical: np.ndarray = field(default_factory=lambda: np.zeros(8))
    semantic: np.ndarray = field(default_factory=lambda: np.zeros(8))
    syntactic: np.ndarray = field(default_factory=lambda: np.zeros(8))
    temporal: np.ndarray = field(default_factory=lambda: np.zeros(8))
    emotional: np.ndarray = field(default_factory=lambda: np.zeros(8))
    complexity: np.ndarray = field(default_factory=lambda: np.zeros(8))
    intent: np.ndarray = field(default_factory=lambda: np.zeros(8))
    domain: np.ndarray = field(default_factory=lambda: np.zeros(8))
    risk: np.ndarray = field(default_factory=lambda: np.zeros(8))
    social: np.ndarray = field(default_factory=lambda: np.zeros(8))

    # Summary scalars
    overall_complexity: float = 0.5
    overall_urgency: float = 0.3
    overall_risk: float = 0.0
    detected_domain: str = "general"
    detected_intent: str = "unknown"

    def to_flat_vector(self) -> np.ndarray:
        """Flatten all channels into single feature vector."""
        return np.concatenate([
            self.lexical, self.semantic, self.syntactic, self.temporal,
            self.emotional, self.complexity, self.intent, self.domain,
            self.risk, self.social
        ])

    def to_dict(self) -> Dict:
        return {
            'overall_complexity': round(self.overall_complexity, 3),
            'overall_urgency': round(self.overall_urgency, 3),
            'overall_risk': round(self.overall_risk, 3),
            'detected_domain': self.detected_domain,
            'detected_intent': self.detected_intent,
        }


class SensoryPreprocessor:
    """
    Multi-channel feature extraction from raw text input.

    Converts unstructured text into structured feature vectors across
    10 sensory channels, analogous to early sensory cortex processing.
    """

    # Domain signal words
    DOMAIN_SIGNALS = {
        'coding': ['code', 'function', 'class', 'variable', 'import', 'module',
                    'python', 'javascript', 'typescript', 'api', 'endpoint', 'refactor',
                    'debug', 'compile', 'lint', 'test', 'unit', 'integration'],
        'deployment': ['deploy', 'docker', 'kubernetes', 'ci', 'cd', 'pipeline',
                       'production', 'staging', 'server', 'cloud', 'aws', 'gcp'],
        'analysis': ['analyze', 'data', 'chart', 'graph', 'metric', 'statistics',
                     'report', 'dashboard', 'trend', 'correlation', 'pattern'],
        'communication': ['email', 'message', 'slack', 'notify', 'tell', 'ask',
                          'meeting', 'present', 'share', 'collaborate', 'review'],
        'security': ['security', 'auth', 'token', 'password', 'encrypt', 'ssl',
                     'vulnerability', 'permission', 'access', 'firewall'],
    }

    # Intent patterns
    INTENT_PATTERNS = {
        'create': ['create', 'make', 'build', 'generate', 'add', 'new', 'write'],
        'modify': ['update', 'change', 'edit', 'modify', 'fix', 'patch', 'refactor'],
        'delete': ['delete', 'remove', 'drop', 'clean', 'purge', 'destroy'],
        'query': ['find', 'search', 'list', 'show', 'get', 'fetch', 'check'],
        'analyze': ['analyze', 'explain', 'why', 'how', 'understand', 'investigate'],
    }

    # Risk signals
    RISK_WORDS = {
        'high': ['delete', 'drop', 'destroy', 'purge', 'force', 'override',
                 'production', 'database', 'credentials', 'root', 'admin', 'sudo'],
        'medium': ['modify', 'update', 'change', 'reset', 'restart', 'migrate'],
        'low': ['read', 'list', 'check', 'view', 'analyze', 'test'],
    }

    # Urgency signals
    URGENCY_WORDS = ['urgent', 'asap', 'immediately', 'critical', 'emergency',
                     'now', 'hurry', 'deadline', 'overdue', 'blocking']

    # Temporal references
    TEMPORAL_WORDS = ['today', 'tomorrow', 'yesterday', 'week', 'month',
                      'schedule', 'deadline', 'before', 'after', 'when',
                      'until', 'soon', 'later', 'ago']

    def __init__(self):
        pass

    def extract(self, text: str) -> SensoryFeatures:
        """
        Extract multi-channel sensory features from raw text.

        Args:
            text: Raw input text (task description)

        Returns:
            SensoryFeatures with all channels populated
        """
        features = SensoryFeatures()
        words = text.lower().split()
        word_count = len(words)

        if word_count == 0:
            return features

        # 1. Lexical features
        features.lexical = self._extract_lexical(text, words, word_count)

        # 2. Semantic features
        features.semantic = self._extract_semantic(words)

        # 3. Syntactic features
        features.syntactic = self._extract_syntactic(text)

        # 4. Temporal features
        features.temporal = self._extract_temporal(words)

        # 5. Emotional features (simple keyword match)
        features.emotional = self._extract_emotional(words)

        # 6. Complexity features
        features.complexity = self._extract_complexity(text, words, word_count)

        # 7. Intent features
        features.intent, features.detected_intent = self._extract_intent(words)

        # 8. Domain features
        features.domain, features.detected_domain = self._extract_domain(words)

        # 9. Risk features
        features.risk, features.overall_risk = self._extract_risk(words)

        # 10. Social features
        features.social = self._extract_social(text, words)

        # Summary scalars
        features.overall_complexity = float(np.mean(features.complexity))
        features.overall_urgency = self._compute_urgency(words)

        return features

    def _extract_lexical(self, text: str, words: List[str], word_count: int) -> np.ndarray:
        """Word count, vocabulary richness, sentence length, etc."""
        v = np.zeros(8)
        v[0] = min(1.0, word_count / 50.0)  # Normalized word count
        v[1] = len(set(words)) / max(word_count, 1)  # Vocabulary richness
        sentences = text.split('.')
        v[2] = min(1.0, len(sentences) / 10.0)  # Sentence count
        avg_word_len = np.mean([len(w) for w in words]) if words else 0
        v[3] = min(1.0, avg_word_len / 10.0)  # Average word length
        v[4] = 1.0 if any(w[0].isupper() for w in text.split() if w) else 0.0  # Has proper nouns
        v[5] = min(1.0, text.count(',') / 5.0)  # Comma density
        v[6] = min(1.0, len(text) / 500.0)  # Character count
        v[7] = 1.0 if '\n' in text else 0.0  # Multi-line
        return v

    def _extract_semantic(self, words: List[str]) -> np.ndarray:
        """Topic keywords and semantic signals."""
        v = np.zeros(8)
        # Technical vocabulary density
        tech_words = {'api', 'function', 'class', 'variable', 'database', 'server',
                      'algorithm', 'interface', 'module', 'protocol'}
        v[0] = min(1.0, sum(1 for w in words if w in tech_words) / 3.0)

        # Abstract concepts
        abstract_words = {'system', 'architecture', 'design', 'pattern', 'strategy',
                          'framework', 'model', 'concept', 'principle'}
        v[1] = min(1.0, sum(1 for w in words if w in abstract_words) / 2.0)

        # Concrete actions
        action_words = {'run', 'start', 'stop', 'open', 'close', 'click',
                        'type', 'write', 'read', 'send', 'receive'}
        v[2] = min(1.0, sum(1 for w in words if w in action_words) / 2.0)

        # Quantitative terms
        v[3] = min(1.0, sum(1 for w in words if w.isdigit()) / 3.0)

        # Negation
        neg_words = {'not', 'no', "don't", "doesn't", "can't", "won't", 'never'}
        v[4] = min(1.0, sum(1 for w in words if w in neg_words) / 2.0)

        # Conjunction density (complex sentences)
        conj = {'and', 'or', 'but', 'then', 'also', 'however'}
        v[5] = min(1.0, sum(1 for w in words if w in conj) / 3.0)

        # Pronouns (personalization)
        pronouns = {'i', 'we', 'you', 'my', 'our', 'your'}
        v[6] = min(1.0, sum(1 for w in words if w in pronouns) / 2.0)

        # Question words
        q_words = {'what', 'why', 'how', 'where', 'when', 'who', 'which'}
        v[7] = min(1.0, sum(1 for w in words if w in q_words) / 2.0)

        return v

    def _extract_syntactic(self, text: str) -> np.ndarray:
        """Punctuation, structure, code blocks, etc."""
        v = np.zeros(8)
        v[0] = 1.0 if '?' in text else 0.0
        v[1] = 1.0 if '!' in text else 0.0
        v[2] = 1.0 if '```' in text else 0.0  # Code block
        v[3] = 1.0 if re.search(r'https?://', text) else 0.0  # URL
        v[4] = 1.0 if re.search(r'\b[A-Z]{2,}\b', text) else 0.0  # Acronyms
        v[5] = min(1.0, text.count('(') / 3.0)  # Parenthetical nesting
        v[6] = 1.0 if any(c in text for c in ['{', '}', '[', ']']) else 0.0  # Brackets
        v[7] = 1.0 if re.search(r'\d+\.\d+', text) else 0.0  # Decimal numbers
        return v

    def _extract_temporal(self, words: List[str]) -> np.ndarray:
        """Time references and scheduling signals."""
        v = np.zeros(8)
        temporal_count = sum(1 for w in words if w in self.TEMPORAL_WORDS)
        v[0] = min(1.0, temporal_count / 3.0)
        v[1] = 1.0 if any(w in words for w in ['deadline', 'due', 'overdue']) else 0.0
        v[2] = 1.0 if any(w in words for w in ['schedule', 'plan', 'timeline']) else 0.0
        v[3] = 1.0 if any(w in words for w in ['today', 'now', 'immediately']) else 0.0
        v[4] = 1.0 if any(w in words for w in ['tomorrow', 'next', 'upcoming']) else 0.0
        v[5] = 1.0 if any(w in words for w in ['yesterday', 'previous', 'last']) else 0.0
        v[6] = 1.0 if any(w in words for w in ['before', 'until', 'by']) else 0.0
        v[7] = 1.0 if any(w in words for w in ['after', 'then', 'once']) else 0.0
        return v

    def _extract_emotional(self, words: List[str]) -> np.ndarray:
        """Emotional signal strength per quadrant."""
        v = np.zeros(8)
        pos_hi = ['success', 'great', 'excellent', 'amazing', 'perfect', 'achieve']
        neg_hi = ['error', 'fail', 'crash', 'broken', 'critical', 'emergency']
        pos_lo = ['stable', 'clean', 'simple', 'healthy', 'safe', 'ready']
        neg_lo = ['boring', 'slow', 'deprecated', 'obsolete']

        v[0] = min(1.0, sum(1 for w in words if w in pos_hi) / 2.0)  # Positive high arousal
        v[1] = min(1.0, sum(1 for w in words if w in neg_hi) / 2.0)  # Negative high arousal
        v[2] = min(1.0, sum(1 for w in words if w in pos_lo) / 2.0)  # Positive low arousal
        v[3] = min(1.0, sum(1 for w in words if w in neg_lo) / 2.0)  # Negative low arousal
        v[4] = v[0] - v[1]  # Net valence (clamped later)
        v[5] = max(v[0], v[1])  # Peak arousal
        v[6] = max(v[0] + v[2], 0) - max(v[1] + v[3], 0)  # Overall sentiment
        v[7] = 1.0 if (v[1] > 0.5) else 0.0  # Alarm signal
        return np.clip(v, -1.0, 1.0)

    def _extract_complexity(self, text: str, words: List[str], word_count: int) -> np.ndarray:
        """Estimated task complexity signals."""
        v = np.zeros(8)
        v[0] = min(1.0, word_count / 30.0)  # Length-based complexity
        unique_ratio = len(set(words)) / max(word_count, 1)
        v[1] = unique_ratio  # Vocabulary diversity
        v[2] = min(1.0, text.count(' and ') / 3.0)  # Conjunction complexity
        v[3] = min(1.0, len(re.findall(r'\b\w{10,}\b', text)) / 3.0)  # Long word count
        v[4] = min(1.0, text.count(',') / 5.0)  # Comma complexity
        v[5] = 1.0 if any(w in words for w in ['complex', 'complicated', 'advanced']) else 0.0
        v[6] = 1.0 if '```' in text else 0.0  # Code presence
        steps = len(re.findall(r'\b(?:step|first|then|next|finally)\b', text.lower()))
        v[7] = min(1.0, steps / 3.0)  # Multi-step indicator
        return v

    def _extract_intent(self, words: List[str]) -> Tuple[np.ndarray, str]:
        """Detect user intent category."""
        v = np.zeros(8)
        scores = {}
        for i, (intent, patterns) in enumerate(self.INTENT_PATTERNS.items()):
            count = sum(1 for w in words if w in patterns)
            score = min(1.0, count / 2.0)
            if i < 5:
                v[i] = score
            scores[intent] = count

        # Determine dominant intent
        v[5] = 1.0 if '?' in ' '.join(words) else 0.0  # Question
        v[6] = 1.0 if any(w in words for w in ['please', 'help', 'can']) else 0.0  # Request
        v[7] = 1.0 if any(w in words for w in ['must', 'should', 'need']) else 0.0  # Obligation

        detected = max(scores, key=scores.get) if any(scores.values()) else 'unknown'
        return v, detected

    def _extract_domain(self, words: List[str]) -> Tuple[np.ndarray, str]:
        """Detect task domain."""
        v = np.zeros(8)
        scores = {}
        for i, (domain, signals) in enumerate(self.DOMAIN_SIGNALS.items()):
            count = sum(1 for w in words if w in signals)
            score = min(1.0, count / 3.0)
            if i < 5:
                v[i] = score
            scores[domain] = count

        v[5] = 1.0 if any(w in words for w in ['file', 'folder', 'directory', 'path']) else 0.0
        v[6] = 1.0 if any(w in words for w in ['config', 'setting', 'option', 'parameter']) else 0.0
        v[7] = 1.0 if any(w in words for w in ['log', 'monitor', 'trace', 'debug']) else 0.0

        detected = max(scores, key=scores.get) if any(scores.values()) else 'general'
        return v, detected

    def _extract_risk(self, words: List[str]) -> Tuple[np.ndarray, float]:
        """Detect risk level of the task."""
        v = np.zeros(8)
        high_count = sum(1 for w in words if w in self.RISK_WORDS['high'])
        med_count = sum(1 for w in words if w in self.RISK_WORDS['medium'])
        low_count = sum(1 for w in words if w in self.RISK_WORDS['low'])

        v[0] = min(1.0, high_count / 2.0)  # High risk signals
        v[1] = min(1.0, med_count / 2.0)   # Medium risk signals
        v[2] = min(1.0, low_count / 2.0)   # Low risk signals
        v[3] = 1.0 if any(w in words for w in ['irreversible', 'permanent', 'cannot undo']) else 0.0
        v[4] = 1.0 if any(w in words for w in ['backup', 'rollback', 'restore']) else 0.0
        v[5] = 1.0 if 'production' in words else 0.0
        v[6] = 1.0 if any(w in words for w in ['all', 'everything', 'entire']) else 0.0  # Scope
        v[7] = 1.0 if any(w in words for w in ['sudo', 'root', 'admin', 'force']) else 0.0

        # Compute overall risk score
        overall = np.clip(
            0.8 * v[0] + 0.4 * v[1] + 0.1 * v[2] + 0.3 * v[3] + 0.3 * v[6] + 0.4 * v[7],
            0.0, 1.0
        )
        return v, float(overall)

    def _extract_social(self, text: str, words: List[str]) -> np.ndarray:
        """Social/collaboration signals."""
        v = np.zeros(8)
        v[0] = 1.0 if '@' in text else 0.0  # Mentions
        v[1] = 1.0 if any(w in words for w in ['team', 'group', 'together']) else 0.0
        v[2] = 1.0 if any(w in words for w in ['review', 'approve', 'feedback']) else 0.0
        v[3] = 1.0 if any(w in words for w in ['share', 'publish', 'broadcast']) else 0.0
        v[4] = 1.0 if any(w in words for w in ['user', 'customer', 'client']) else 0.0
        v[5] = 1.0 if any(w in words for w in ['help', 'support', 'assist']) else 0.0
        v[6] = 1.0 if any(w in words for w in ['meeting', 'call', 'discussion']) else 0.0
        v[7] = 1.0 if any(w in words for w in ['we', 'us', 'our']) else 0.0  # Collective
        return v

    def _compute_urgency(self, words: List[str]) -> float:
        """Compute overall urgency score."""
        count = sum(1 for w in words if w in self.URGENCY_WORDS)
        return min(1.0, count / 2.0)

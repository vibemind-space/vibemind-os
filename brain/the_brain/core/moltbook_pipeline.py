"""
Moltbook Pipeline — Thinker-Talker Orchestration System

Provides:
  - InputAnalyzer:          Analyzes user input (intent, complexity, topics)
  - ThinkingBudget:         ACC-driven: how much thinking to invest
  - ThinkTalkOrchestrator:  Main pipeline: Input → Retrieve → Think → Speak
  - RealtimeResponseEngine: Fast pipeline connecting all Moltbook components
  - DebugStream:            Optional internal thought transparency
  - PerformanceMonitor:     Latency, hit-rate, quality tracking

Architecture Inspirations:
  - MIRROR (arxiv 2506.00430) — Thinker/Talker separation pipeline
  - Speculative Decoding — Draft-Verify pattern for response generation
  - Predictive Coding (Friston) — Prediction error drives processing depth
  - ACC Expected Value of Control — Effort/reward tradeoff for thinking depth
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('brain.moltbook.pipeline')


# ═══════════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class InputAnalysis:
    """Result of analyzing user input."""
    raw_input: str = ""
    intent: str = "unknown"          # question/instruction/greeting/clarification/creative
    complexity: float = 0.5          # 0 (trivial) to 1 (very complex)
    topics: List[str] = field(default_factory=list)
    emotional_tone: float = 0.0      # -1 to +1
    urgency: float = 0.5             # 0 (relaxed) to 1 (urgent)
    expected_length: str = "medium"  # short/medium/long
    requires_knowledge: bool = True
    requires_reasoning: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'intent': self.intent,
            'complexity': self.complexity,
            'topics': self.topics,
            'emotional_tone': self.emotional_tone,
            'urgency': self.urgency,
            'expected_length': self.expected_length,
            'requires_knowledge': self.requires_knowledge,
            'requires_reasoning': self.requires_reasoning,
        }


@dataclass
class PipelineResult:
    """Full pipeline output with timing and metadata."""
    response_text: str = ""
    confidence: float = 0.5
    sources: List[str] = field(default_factory=list)
    input_analysis: Optional[InputAnalysis] = None
    think_time_ms: float = 0.0
    speak_time_ms: float = 0.0
    retrieve_time_ms: float = 0.0
    total_time_ms: float = 0.0
    entries_retrieved: int = 0
    speculative_hits: int = 0
    thoughts_consulted: int = 0
    quality_passed: bool = True
    debug_log: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'response': self.response_text,
            'confidence': self.confidence,
            'sources': self.sources,
            'analysis': self.input_analysis.to_dict() if self.input_analysis else None,
            'timing': {
                'think_ms': self.think_time_ms,
                'speak_ms': self.speak_time_ms,
                'retrieve_ms': self.retrieve_time_ms,
                'total_ms': self.total_time_ms,
            },
            'entries_retrieved': self.entries_retrieved,
            'speculative_hits': self.speculative_hits,
            'thoughts_consulted': self.thoughts_consulted,
            'quality_passed': self.quality_passed,
        }


# ═══════════════════════════════════════════════════════════════════
# [46+] InputAnalyzer — User Input Analysis
# ═══════════════════════════════════════════════════════════════════

class InputAnalyzer:
    """
    Analyzes user input to determine intent, complexity, and topics.

    This drives the pipeline: simple greetings skip deep thinking,
    complex technical questions trigger full retrieval + reasoning.
    """

    # Intent detection keywords
    _QUESTION_MARKERS = {'?', 'what', 'how', 'why', 'when', 'where', 'who',
                         'which', 'can', 'could', 'would', 'should', 'is', 'are',
                         'do', 'does', 'did', 'was', 'were', 'explain', 'describe'}
    _INSTRUCTION_MARKERS = {'do', 'make', 'create', 'build', 'write', 'generate',
                            'implement', 'fix', 'update', 'change', 'add', 'remove',
                            'delete', 'run', 'execute', 'deploy', 'install', 'setup'}
    _GREETING_MARKERS = {'hi', 'hello', 'hey', 'hallo', 'moin', 'servus',
                         'good morning', 'good evening', 'yo', 'sup', 'greetings'}
    _CREATIVE_MARKERS = {'imagine', 'story', 'poem', 'creative', 'brainstorm',
                         'invent', 'design', 'dream', 'fantasize', 'what if'}

    def __init__(self):
        self._total_analyzed = 0
        logger.info("InputAnalyzer initialized")

    def analyze(self, user_input: str) -> InputAnalysis:
        """
        Analyze user input to determine processing strategy.

        Returns InputAnalysis with intent, complexity, topics, etc.
        """
        self._total_analyzed += 1
        analysis = InputAnalysis(raw_input=user_input)

        if not user_input.strip():
            analysis.intent = "empty"
            analysis.complexity = 0.0
            analysis.requires_knowledge = False
            analysis.requires_reasoning = False
            return analysis

        text_lower = user_input.lower().strip()
        words = text_lower.split()
        word_set = set(words)

        # Intent detection
        analysis.intent = self._detect_intent(text_lower, word_set)

        # Complexity estimation
        analysis.complexity = self._estimate_complexity(user_input, words)

        # Topic extraction (simple keyword-based for Phase A)
        analysis.topics = self._extract_topics(words)

        # Emotional tone
        analysis.emotional_tone = self._detect_emotion(text_lower)

        # Urgency
        analysis.urgency = self._detect_urgency(text_lower)

        # Expected length
        if analysis.complexity < 0.3:
            analysis.expected_length = "short"
        elif analysis.complexity > 0.7:
            analysis.expected_length = "long"
        else:
            analysis.expected_length = "medium"

        # Whether knowledge/reasoning needed
        if analysis.intent == "greeting":
            analysis.requires_knowledge = False
            analysis.requires_reasoning = False
        # clarification still benefits from knowledge retrieval

        return analysis

    # Identity-related patterns (questions about who the system is)
    _IDENTITY_PATTERNS = {'wer bist du', 'who are you', 'what are you',
                          'tell me about yourself', 'introduce yourself',
                          'was bist du', 'stell dich vor', 'your name'}

    def _detect_intent(self, text: str, word_set: set) -> str:
        """Detect the primary intent of the input."""
        # Strip punctuation from words for matching
        clean_words = {w.strip('.,!?;:') for w in text.split()}

        # Identity questions → treat as greeting (triggers self-introduction)
        text_nopunct = text.replace('?', '').replace('!', '').replace(',', '').strip()
        if any(pattern in text_nopunct for pattern in self._IDENTITY_PATTERNS):
            return "greeting"

        # Greeting check — strip punctuation for matching
        if len(clean_words) <= 6 and clean_words & self._GREETING_MARKERS:
            return "greeting"

        # Question check
        if '?' in text or (clean_words & self._QUESTION_MARKERS and len(clean_words) > 2):
            return "question"

        # Creative check
        if clean_words & self._CREATIVE_MARKERS:
            return "creative"

        # Instruction check
        first_word = text_nopunct.split()[0] if text_nopunct.split() else ""
        if first_word in self._INSTRUCTION_MARKERS or clean_words & self._INSTRUCTION_MARKERS:
            return "instruction"

        # Clarification (short follow-ups)
        if len(clean_words) <= 3:
            return "clarification"

        return "question"  # Default to question

    def _estimate_complexity(self, text: str, words: List[str]) -> float:
        """Estimate query complexity (0-1)."""
        score = 0.0

        # Length factor
        word_count = len(words)
        if word_count > 50:
            score += 0.3
        elif word_count > 20:
            score += 0.2
        elif word_count > 10:
            score += 0.1

        # Technical indicators
        technical_words = {'algorithm', 'architecture', 'implementation', 'optimize',
                          'performance', 'design', 'pattern', 'abstract', 'interface',
                          'database', 'concurrency', 'async', 'distributed', 'neural',
                          'model', 'training', 'deploy', 'kubernetes', 'microservice'}
        tech_overlap = len(set(w.lower() for w in words) & technical_words)
        score += min(0.3, tech_overlap * 0.1)

        # Multiple questions
        question_marks = text.count('?')
        if question_marks > 1:
            score += 0.15

        # Code indicators
        if any(c in text for c in ['```', 'def ', 'class ', 'import ', 'function']):
            score += 0.15

        # Multi-part requests
        if any(marker in text.lower() for marker in ['and also', 'additionally', 'furthermore',
                                                       'as well as', 'plus']):
            score += 0.1

        return min(1.0, score)

    # Extended stopwords for both English and German
    _STOPWORDS = frozenset({
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'can', 'shall',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'up', 'about', 'into', 'through', 'during', 'before', 'after',
        'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'both',
        'it', 'its', 'my', 'your', 'his', 'her', 'our', 'their',
        'this', 'that', 'these', 'those', 'i', 'me', 'you', 'he',
        'she', 'we', 'they', 'what', 'how', 'why', 'when', 'where',
        'who', 'which', 'if', 'then', 'else', 'than', 'too', 'very',
        'just', 'also', 'please', 'help', 'want', 'need', 'like',
        # German stopwords
        'der', 'die', 'das', 'ein', 'eine', 'und', 'oder', 'aber',
        'ist', 'sind', 'war', 'hat', 'haben', 'nicht', 'mit', 'auf',
        'für', 'von', 'zu', 'den', 'dem', 'des', 'im', 'ich', 'du',
        'er', 'sie', 'es', 'wir', 'ihr', 'was', 'wie', 'wenn',
        'noch', 'schon', 'mal', 'auch', 'nur', 'dann', 'wird', 'kann',
        'muss', 'soll', 'doch', 'mehr', 'hier', 'dort', 'nach', 'bei',
        'über', 'unter', 'durch', 'aus', 'vor', 'als', 'bis', 'um',
    })

    def _extract_topics(self, words: List[str]) -> List[str]:
        """Extract main topics from input — filters stopwords and scores by significance."""
        # Filter stopwords and short words
        candidates = [w for w in words if w.lower() not in self._STOPWORDS and len(w) > 2]

        # Score candidates: longer words and less common English words score higher
        scored = []
        for w in candidates:
            score = 0.0
            wl = w.lower()
            # Length bonus (longer = more specific)
            score += min(1.0, len(wl) / 10.0)
            # Capitalization bonus (likely proper noun or technical term)
            if w[0].isupper() and len(w) > 1:
                score += 0.3
            # Compound/technical indicators
            if '_' in w or '-' in w or any(c.isupper() for c in w[1:]):
                score += 0.4  # camelCase, snake_case, hyphenated
            # Numeric content (version numbers, IDs)
            if any(c.isdigit() for c in w):
                score += 0.2
            scored.append((wl, score))

        # Sort by score descending, deduplicate
        scored.sort(key=lambda x: x[1], reverse=True)
        seen = set()
        topics = []
        for word, _ in scored:
            if word not in seen:
                seen.add(word)
                topics.append(word)
            if len(topics) >= 10:
                break

        return topics

    def _detect_emotion(self, text: str) -> float:
        """Simple emotional tone detection (-1 to +1)."""
        positive = {'great', 'awesome', 'amazing', 'love', 'thank', 'thanks',
                    'perfect', 'excellent', 'wonderful', 'fantastic', 'happy',
                    'glad', 'nice', 'cool', 'good', 'super', 'brilliant'}
        negative = {'bad', 'terrible', 'horrible', 'hate', 'frustrated',
                    'angry', 'annoyed', 'confused', 'stuck', 'broken',
                    'failing', 'error', 'bug', 'wrong', 'problem', 'issue'}

        words = set(text.split())
        pos = len(words & positive)
        neg = len(words & negative)

        if pos == 0 and neg == 0:
            return 0.0
        return (pos - neg) / max(pos + neg, 1)

    def _detect_urgency(self, text: str) -> float:
        """Detect urgency level (0-1)."""
        urgent_markers = {'urgent', 'asap', 'immediately', 'right now', 'critical',
                         'emergency', 'deadline', 'hurry', 'quick', 'fast',
                         'wichtig', 'dringend', 'sofort', 'schnell'}
        words = set(text.split())
        overlap = len(words & urgent_markers)
        if overlap > 0:
            return min(1.0, 0.5 + 0.2 * overlap)
        if text.endswith('!') or text.endswith('!!'):
            return 0.6
        return 0.3

    def get_stats(self) -> Dict[str, Any]:
        return {'total_analyzed': self._total_analyzed}


# ═══════════════════════════════════════════════════════════════════
# [47] ThinkingBudget — ACC-driven Thinking Depth
# ═══════════════════════════════════════════════════════════════════

class ThinkingBudget:
    """
    Determines how much "thinking effort" to invest.

    Simple question → minimal thinking (fast response)
    Complex question → deep thinking (longer latency acceptable)

    Uses ACC Expected Value of Control for effort/reward tradeoff.
    Learns from user feedback which question types need more thinking.
    """

    def __init__(self, acc=None):
        self._acc = acc                  # AnteriorCingulateCortex (optional)
        self._complexity_history: deque = deque(maxlen=200)
        self._feedback_map: Dict[str, float] = {}  # intent → avg needed depth
        self._total_budgets = 0
        logger.info("ThinkingBudget initialized")

    def allocate(self, analysis: InputAnalysis) -> Dict[str, Any]:
        """
        Allocate thinking budget based on input analysis.

        Returns dict with:
          - depth: 'minimal' / 'standard' / 'deep'
          - max_think_ms: Maximum thinking time allowed
          - retrieval_depth: How many entries to retrieve
          - use_speculative: Whether to use speculative retrieval
          - use_thought_stream: Whether to consult background thoughts
        """
        self._total_budgets += 1
        complexity = analysis.complexity
        intent = analysis.intent

        # Get EVC from ACC if available
        evc = 0.5
        if self._acc:
            try:
                evc_result = self._acc.process({
                    'task_type': 'thinking_budget',
                    'complexity': complexity,
                    'effort': complexity,
                    'expected_reward': 1.0 - complexity * 0.3,  # Complex = less certain reward
                })
                if isinstance(evc_result, dict):
                    evc = evc_result.get('evc',
                                         evc_result.get('expected_value_of_control', 0.5))
                    if isinstance(evc, (int, float)):
                        evc = float(evc)
                    else:
                        evc = 0.5
            except Exception:
                pass

        # Adjust complexity based on learned feedback
        if intent in self._feedback_map:
            learned_depth = self._feedback_map[intent]
            complexity = 0.7 * complexity + 0.3 * learned_depth

        # Determine depth
        if complexity < 0.25 or intent in ('greeting', 'clarification'):
            depth = 'minimal'
            max_think_ms = 50
            retrieval_depth = 3
            use_speculative = False
            use_thought_stream = False
        elif complexity > 0.65 or intent == 'creative':
            depth = 'deep'
            max_think_ms = 500
            retrieval_depth = 15
            use_speculative = True
            use_thought_stream = True
        else:
            depth = 'standard'
            max_think_ms = 200
            retrieval_depth = 7
            use_speculative = True
            use_thought_stream = True

        # EVC modulation: high EVC → invest more, low → cut short
        if evc > 0.7 and depth != 'deep':
            depth = 'deep' if depth == 'standard' else 'standard'
            max_think_ms = int(max_think_ms * 1.5)
            retrieval_depth = min(20, int(retrieval_depth * 1.5))

        budget = {
            'depth': depth,
            'max_think_ms': max_think_ms,
            'retrieval_depth': retrieval_depth,
            'use_speculative': use_speculative,
            'use_thought_stream': use_thought_stream,
            'evc': evc,
            'complexity': complexity,
        }

        self._complexity_history.append(complexity)
        return budget

    def record_feedback(self, intent: str, was_sufficient: bool) -> None:
        """Learn from feedback whether thinking depth was sufficient."""
        current = self._feedback_map.get(intent, 0.5)
        if was_sufficient:
            self._feedback_map[intent] = current * 0.9  # Can reduce thinking
        else:
            self._feedback_map[intent] = min(1.0, current * 1.1 + 0.05)  # Need more

    def get_stats(self) -> Dict[str, Any]:
        history = list(self._complexity_history)
        return {
            'total_budgets': self._total_budgets,
            'avg_complexity': sum(history) / max(1, len(history)),
            'feedback_intents': len(self._feedback_map),
        }


# ═══════════════════════════════════════════════════════════════════
# [49] DebugStream — Internal Thought Transparency
# ═══════════════════════════════════════════════════════════════════

class DebugStream:
    """
    Optional display of internal thoughts for debugging.

    Format:
      [THINK] Hmm, the user asks about X. I remember Y...
      [FEEL] CoreAffect: valence=0.6, arousal=0.3 → interested
      [RETRIEVE] Moltbook Entry #4521 (relevance: 0.89)
      [SPEAK] Formulating response with confidence 0.82

    Only active when MOLTBOOK_DEBUG=true or explicitly enabled.
    """

    def __init__(self, enabled: Optional[bool] = None):
        if enabled is None:
            self._enabled = os.environ.get('MOLTBOOK_DEBUG', '').lower() in ('true', '1', 'yes')
        else:
            self._enabled = enabled
        self._log: deque = deque(maxlen=500)
        self._total_entries = 0
        logger.info(f"DebugStream initialized (enabled={self._enabled})")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def log(self, category: str, message: str) -> None:
        """Log a debug entry."""
        if not self._enabled:
            return
        entry = {
            'timestamp': time.time(),
            'category': category,
            'message': message,
        }
        self._log.append(entry)
        self._total_entries += 1
        # Also log to Python logger at DEBUG level
        logger.debug(f"[{category}] {message}")

    def think(self, message: str) -> None:
        """Log a thinking event."""
        self.log('THINK', message)

    def feel(self, valence: float, arousal: float, label: str = "") -> None:
        """Log an emotional state."""
        self.log('FEEL', f"valence={valence:.2f}, arousal={arousal:.2f}"
                        + (f" → {label}" if label else ""))

    def retrieve(self, entry_id: str, relevance: float) -> None:
        """Log a retrieval event."""
        self.log('RETRIEVE', f"Entry {entry_id} (relevance: {relevance:.2f})")

    def speak(self, confidence: float, length: str = "") -> None:
        """Log a speaking event."""
        self.log('SPEAK', f"Formulating response (confidence={confidence:.2f}"
                         + (f", length={length}" if length else "") + ")")

    def budget(self, depth: str, max_ms: int) -> None:
        """Log thinking budget allocation."""
        self.log('BUDGET', f"Depth={depth}, max_think_ms={max_ms}")

    def get_recent(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get recent debug entries."""
        entries = list(self._log)
        return entries[-n:]

    def get_formatted(self, n: int = 20) -> str:
        """Get formatted debug output."""
        entries = self.get_recent(n)
        lines = []
        for e in entries:
            lines.append(f"[{e['category']}] {e['message']}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._log.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            'enabled': self._enabled,
            'total_entries': self._total_entries,
            'buffer_size': len(self._log),
        }


# ═══════════════════════════════════════════════════════════════════
# [50] PerformanceMonitor — Latency & Quality Tracking
# ═══════════════════════════════════════════════════════════════════

class PerformanceMonitor:
    """
    Tracks pipeline performance: latency, hit-rate, quality.

    Alerts when:
      - Total latency > 2s
      - Speculative hit-rate < 40%
      - Average confidence < 0.3
    """

    def __init__(self, max_latency_ms: float = 2000.0,
                 min_hit_rate: float = 0.4,
                 min_confidence: float = 0.3):
        self._max_latency_ms = max_latency_ms
        self._min_hit_rate = min_hit_rate
        self._min_confidence = min_confidence

        self._latencies: deque = deque(maxlen=200)
        self._confidences: deque = deque(maxlen=200)
        self._hit_rates: deque = deque(maxlen=200)
        self._alerts: deque = deque(maxlen=50)
        self._total_monitored = 0

        logger.info("PerformanceMonitor initialized")

    def record(self, result: PipelineResult) -> List[str]:
        """
        Record a pipeline result and return any alerts.
        """
        self._total_monitored += 1
        self._latencies.append(result.total_time_ms)
        self._confidences.append(result.confidence)

        if result.entries_retrieved > 0:
            hit_rate = result.speculative_hits / max(1, result.entries_retrieved)
            self._hit_rates.append(hit_rate)

        # Check for alerts
        alerts = []
        if result.total_time_ms > self._max_latency_ms:
            alert = f"High latency: {result.total_time_ms:.0f}ms > {self._max_latency_ms:.0f}ms"
            alerts.append(alert)

        if len(self._confidences) >= 10:
            avg_conf = sum(self._confidences) / len(self._confidences)
            if avg_conf < self._min_confidence:
                alerts.append(f"Low avg confidence: {avg_conf:.2f} < {self._min_confidence}")

        if len(self._hit_rates) >= 10:
            avg_hit = sum(self._hit_rates) / len(self._hit_rates)
            if avg_hit < self._min_hit_rate:
                alerts.append(f"Low hit-rate: {avg_hit:.2f} < {self._min_hit_rate}")

        for a in alerts:
            self._alerts.append({'time': time.time(), 'alert': a})

        return alerts

    def get_stats(self) -> Dict[str, Any]:
        lat = list(self._latencies)
        conf = list(self._confidences)
        hr = list(self._hit_rates)
        return {
            'total_monitored': self._total_monitored,
            'avg_latency_ms': sum(lat) / max(1, len(lat)),
            'avg_confidence': sum(conf) / max(1, len(conf)),
            'avg_hit_rate': sum(hr) / max(1, len(hr)),
            'recent_alerts': len(self._alerts),
            'p95_latency_ms': sorted(lat)[int(len(lat) * 0.95)] if len(lat) >= 20 else 0,
        }


# ═══════════════════════════════════════════════════════════════════
# [46] RealtimeResponseEngine — Fast Pipeline
# ═══════════════════════════════════════════════════════════════════

class KnowledgeAugmentor:
    """
    Phase C Intelligence: Augments internal knowledge with external sources.

    When internal MoltbookStore knowledge is insufficient (low similarity,
    too few entries, or question needs factual depth), this module fetches
    knowledge from Wikipedia and web search via ToolUniverse.

    Also stores fetched knowledge back into MoltbookStore for future use.
    """

    def __init__(self, moltbook=None, feeder=None):
        self._moltbook = moltbook
        self._feeder = feeder          # MoltbookFeeder (to store new knowledge)
        self._wiki_available = None    # Lazy-checked
        self._web_available = None
        self._cache: Dict[str, str] = {}   # query → answer cache
        self._cache_max = 200
        self._total_augments = 0
        self._total_wiki = 0
        self._total_web = 0
        logger.info("KnowledgeAugmentor initialized")

    def augment(self, query: str, topics: List[str],
                internal_entries: list,
                max_similarity: float = 0.0,
                intent: str = "question") -> Dict[str, Any]:
        """
        Augment knowledge if internal entries are insufficient.

        Returns dict with:
          - augmented: bool (whether external knowledge was fetched)
          - wiki_summary: str (Wikipedia summary if found)
          - web_results: list of str (web search snippets)
          - combined_answer: str (synthesized answer from all sources)
        """
        result = {
            'augmented': False,
            'wiki_summary': '',
            'web_results': [],
            'combined_answer': '',
            'source': 'internal',
        }

        # Don't augment greetings or simple clarifications
        if intent in ('greeting', 'clarification', 'empty'):
            return result

        # Determine if we need external knowledge
        # Comparison/difference questions always benefit from augmentation
        is_comparison = any(w in query.lower() for w in [
            'unterschied', 'difference', 'compare', 'versus', 'vs',
            'vergleich', 'unterscheiden',
        ])
        needs_augment = (
            max_similarity < 0.4 or           # Internal knowledge is weak
            len(internal_entries) == 0 or      # No internal knowledge at all
            (intent in ('question', 'knowledge') and max_similarity < 0.65) or  # Q/K with mediocre match
            is_comparison                      # Comparisons always need depth
        )

        if not needs_augment:
            return result

        self._total_augments += 1

        # Build search query — extract the core topic for better Wikipedia results
        # Strip conversational preamble like "tell me about", "what is", etc.
        search_query = self._extract_search_topic(query, topics)

        # Check cache first
        cache_key = search_query.lower().strip()
        if cache_key in self._cache:
            result['combined_answer'] = self._cache[cache_key]
            result['augmented'] = True
            result['source'] = 'cache'
            return result

        # Try Wikipedia first (fast, reliable, factual)
        wiki_text = self._fetch_wikipedia(search_query)
        if wiki_text:
            result['wiki_summary'] = wiki_text
            result['augmented'] = True
            result['source'] = 'wikipedia'
            self._total_wiki += 1

        # Try web search if Wikipedia didn't help enough
        if not wiki_text or len(wiki_text) < 50:
            web_results = self._fetch_web(search_query)
            if web_results:
                result['web_results'] = web_results
                result['augmented'] = True
                if not wiki_text:
                    result['source'] = 'web'
                self._total_web += 1

        # Synthesize combined answer
        if result['augmented']:
            combined = self._synthesize(query, result['wiki_summary'],
                                         result['web_results'], internal_entries)
            result['combined_answer'] = combined

            # Cache it
            if len(self._cache) < self._cache_max:
                self._cache[cache_key] = combined

            # Store new knowledge back into Moltbook for future use
            stored_id = self._store_knowledge(result, topics)
            if stored_id:
                result['stored_id'] = stored_id

        return result

    def _extract_search_topic(self, query: str, topics: list) -> str:
        """
        Extract the core topic from a user query for Wikipedia/web search.

        Strips conversational fluff like "tell me about", "what is", "explain".
        For comparisons ("difference between X and Y"), searches for "X and Y".
        """
        import re
        q = query.strip()

        # Handle comparison queries: "difference between X and Y"
        comp_match = re.search(
            r'(?:difference|differences|comparison|compare|versus|vs)\s+'
            r'(?:between\s+)?(.+?)(?:\?|$)',
            q, re.IGNORECASE
        )
        if comp_match:
            return comp_match.group(1).strip()[:100]

        # Strip common conversational preambles
        preambles = [
            r'^(?:tell\s+me\s+(?:about|more\s+about))\s+',
            r'^(?:what\s+(?:is|are|was|were|does|do))\s+',
            r'^(?:how\s+(?:does|do|is|are|can|could))\s+',
            r'^(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+)?',
            r'^(?:who\s+(?:is|are|was|were))\s+',
            r'^(?:where\s+(?:is|are|was|were))\s+',
            r'^(?:when\s+(?:is|are|was|were|did))\s+',
            r'^(?:why\s+(?:is|are|was|were|does|do))\s+',
            r'^(?:can\s+you\s+(?:tell|explain|describe))\s+(?:me\s+)?(?:about\s+)?',
            r'^(?:i\s+(?:want|need)\s+(?:to\s+)?(?:know|learn)\s+(?:about\s+)?)',
        ]

        cleaned = q
        for pattern in preambles:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()

        # Remove trailing question mark and common suffixes
        cleaned = re.sub(r'\?\s*$', '', cleaned).strip()
        cleaned = re.sub(r'\s+(?:please|thanks|thank\s+you)$', '', cleaned, flags=re.IGNORECASE).strip()
        # Remove trailing verb noise: "work", "function", "operate"
        cleaned = re.sub(r'\s+(?:work|works|function|functions|operate|operates)$', '', cleaned, flags=re.IGNORECASE).strip()
        # Remove leading "the" if followed by a real topic
        cleaned = re.sub(r'^the\s+', '', cleaned, flags=re.IGNORECASE).strip()

        # If we extracted something meaningful, use it
        if len(cleaned) > 5:
            return cleaned[:100]

        # Fallback to topics
        if topics and len(topics) >= 2:
            return ' '.join(topics[:4])

        # Fallback to original query
        return q[:100]

    def _fetch_wikipedia(self, query: str) -> str:
        """Fetch Wikipedia summary via ToolUniverse."""
        try:
            from mcp__ToolUniverse import execute_tool  # noqa — not a real import
        except ImportError:
            pass

        # Direct Wikipedia API call (no ToolUniverse dependency)
        try:
            import urllib.request
            import urllib.parse
            import json as _json

            # Use Wikipedia REST API for summary
            safe_query = urllib.parse.quote(query.replace(' ', '_'))
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_query}"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'TheBrain/1.0 (Tahlamus AI Project)',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
                extract = data.get('extract', '')
                if extract and len(extract) > 30:
                    return extract[:800]
        except Exception:
            pass

        # Fallback: try search endpoint
        try:
            import urllib.request
            import urllib.parse
            import json as _json

            safe_q = urllib.parse.quote(query)
            url = (f"https://en.wikipedia.org/w/api.php?action=query&list=search"
                   f"&srsearch={safe_q}&utf8=&format=json&srlimit=1")
            req = urllib.request.Request(url, headers={
                'User-Agent': 'TheBrain/1.0',
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
                results = data.get('query', {}).get('search', [])
                if results:
                    title = results[0].get('title', '')
                    # Fetch the summary of the found article
                    safe_title = urllib.parse.quote(title.replace(' ', '_'))
                    url2 = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
                    req2 = urllib.request.Request(url2, headers={
                        'User-Agent': 'TheBrain/1.0',
                        'Accept': 'application/json',
                    })
                    with urllib.request.urlopen(req2, timeout=5) as resp2:
                        data2 = _json.loads(resp2.read().decode('utf-8'))
                        extract = data2.get('extract', '')
                        if extract and len(extract) > 30:
                            return extract[:800]
        except Exception:
            pass

        return ''

    def _fetch_web(self, query: str) -> List[str]:
        """Fetch web search results via duckduckgo_search."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=3))
            results = []
            for r in raw:
                title = r.get('title', '')
                body = r.get('body', '')
                snippet = f"{title}: {body}"[:300] if body else title
                if snippet.strip():
                    results.append(snippet)
            return results
        except Exception:
            return []

    def _synthesize(self, query: str, wiki: str, web: List[str],
                    internal: list) -> str:
        """
        Synthesize a combined answer from all sources.

        Priority: Wikipedia > Web > Internal (only if relevant)
        Internal knowledge is only included if it's topically related
        to the query — not just the "best" entry by score.
        """
        parts = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Wikipedia FIRST (most authoritative for factual questions)
        if wiki:
            # Extract first 3 sentences for depth
            sentences = wiki.split('. ')
            wiki_short = '. '.join(sentences[:3])
            if wiki_short and not wiki_short.endswith('.'):
                wiki_short += '.'
            parts.append(wiki_short)

        # Web search (if no wiki)
        if web and not wiki:
            parts.append(web[0][:300])

        # Internal knowledge ONLY if topically relevant to the query
        if internal and not parts:
            # Only use internal if we have nothing from external sources
            best_content = internal[0].content if hasattr(internal[0], 'content') else str(internal[0])
            if len(best_content) > 20:
                parts.append(best_content[:200])
        elif internal and parts:
            # Check if best internal entry is actually about the same topic
            best_content = internal[0].content if hasattr(internal[0], 'content') else str(internal[0])
            best_lower = best_content.lower()
            # Count how many query words appear in the internal entry
            overlap = sum(1 for w in query_words if len(w) > 3 and w in best_lower)
            if overlap >= 2 and len(best_content) > 20:
                # Topically relevant — append as supplementary
                parts.append(best_content[:200])

        if not parts:
            return ''

        # Deduplicate: remove near-duplicate sentences
        seen_starts = set()
        unique_parts = []
        for p in parts:
            start = p[:40].lower()
            if start not in seen_starts:
                seen_starts.add(start)
                unique_parts.append(p)

        return ' '.join(unique_parts)

    @staticmethod
    def _extract_subject(text: str) -> str:
        """Extract the core subject/noun-phrase from the first sentence.

        Uses a simple heuristic: the main subject is typically the noun phrase
        before the first verb ('is', 'are', 'was', 'refers', 'describes', etc.).

        Examples:
            "In physics, gravity is a fundamental..." → "gravity"
            "The gravitational constant is an empirical..." → "gravitational constant"
            "Newton's law of universal gravitation describes..." → "newton law universal gravitation"
            "Deoxyribonucleic acid is a polymer..." → "deoxyribonucleic acid"
        """
        import re
        # Take first sentence only
        first_sent = text.split('.')[0] if '.' in text else text
        first_sent = first_sent.strip().lower()

        # Remove common intro phrases
        for prefix in ['in physics,', 'in mathematics,', 'in biology,',
                       'in chemistry,', 'in science,', 'in computing,',
                       'in computer science,']:
            if first_sent.startswith(prefix):
                first_sent = first_sent[len(prefix):].strip()

        # Split at verb boundary — subject is before the verb
        verb_pattern = r'\b(is|are|was|were|refers|describes|denotes|represents|involves|means|has been|can be|may be)\b'
        parts = re.split(verb_pattern, first_sent, maxsplit=1)
        subject_part = parts[0].strip() if parts else first_sent[:60]

        # If subject has "also known as" or appositive, take the part BEFORE comma
        # "gravity, also known as gravitation" → take "gravity"
        if ',' in subject_part:
            before_comma = subject_part.split(',')[0].strip()
            # Use the shorter pre-comma part only if it has real words
            pre_words = [w for w in before_comma.split()
                         if len(w) > 1 and w.isalpha()]
            if pre_words:
                subject_part = before_comma

        # Remove parenthetical abbreviations: "Machine learning (ML)" → "machine learning"
        subject_part = re.sub(r'\([^)]*\)', '', subject_part).strip()

        # Clean: remove articles, determiners, possessives
        stop = {'the', 'a', 'an', 'this', 'that', 'these', 'those',
                'also', 'known', 'as', 'or', 'and', 'of', 'for',
                'called', 'named', 'termed', 'commonly', 'in'}
        # Keep possessive names like "Newton's" → "newton"
        subject_part = re.sub(r"'s\b", '', subject_part)
        words = [w for w in subject_part.split()
                 if w not in stop and len(w) > 1 and w.isalpha()]

        return ' '.join(words[-4:])  # last 4 significant words

    @staticmethod
    def _subjects_match(subj_a: str, subj_b: str) -> bool:
        """Check if two subjects refer to the same core entity.

        Returns True if they share significant words, indicating they're
        about the same topic (should be enriched, not split).

        Examples:
            ("gravity", "gravity") → True
            ("gravity", "gravitational constant") → True  (share 'gravit*')
            ("gravity", "newton law") → False (different entity)
            ("dna", "deoxyribonucleic acid") → True (if we stem)
        """
        if not subj_a or not subj_b:
            return False

        words_a = set(subj_a.lower().split())
        words_b = set(subj_b.lower().split())

        # Exact word overlap
        overlap = words_a & words_b
        if overlap:
            return True

        # Stem-level overlap: check if word stems match
        # Simple: first 5 chars of each word (catches gravity/gravitational)
        stems_a = {w[:5] for w in words_a if len(w) > 3}
        stems_b = {w[:5] for w in words_b if len(w) > 3}
        stem_overlap = stems_a & stems_b
        if stem_overlap:
            return True

        return False

    def _create_entry(self, content: str, topics: List[str],
                      source: str = 'external') -> Optional[str]:
        """Create a new MoltbookEntry via the feeder. Returns entry ID."""
        if not self._feeder:
            return None
        try:
            entry = self._feeder.post(
                content=content,
                tags=topics[:5],
                entry_type="knowledge",
                metadata={'source': source},
            )
            if entry and hasattr(entry, 'id'):
                return entry.id
        except Exception as e:
            logger.debug(f"_create_entry failed: {e}")
        return None

    def _store_knowledge(self, result: Dict[str, Any],
                         topics: List[str]) -> Optional[str]:
        """Store or enrich knowledge in MoltbookStore.

        Strategy:
        - similarity > 0.95: Nearly identical → skip (return existing ID)
        - similarity > 0.70: Same topic, new details → ENRICH existing entry
        - similarity < 0.70: New topic → create new entry

        This makes knowledge entries GROW per entity instead of creating
        many small fragments about the same topic.

        Returns:
            The stored/enriched entry's ID, or None if storage failed.
        """
        if not self._feeder:
            return None

        content = result.get('wiki_summary', '') or ''
        if not content and result.get('web_results'):
            content = result['web_results'][0]

        if not content or len(content) <= 30:
            return None

        content = content[:500]

        # ── Intelligent routing: enrich, link-as-new, or create ──
        # Strategy:
        #   sim > 0.90          → skip (identical)
        #   same subject + related → ENRICH existing entry
        #   different subject + related → CREATE new + LINK to existing
        #   unrelated           → CREATE new standalone entry
        try:
            if self._moltbook:
                existing = self._moltbook.query_semantic(
                    content, top_k=3, threshold=0.35,
                    return_scores=True,
                )
                if existing:
                    new_subject = self._extract_subject(content)
                    topic_words = set()
                    for t in topics:
                        for w in t.lower().replace('?', '').replace('!', '').split():
                            if len(w) > 2:
                                topic_words.add(w)

                    best_match = None
                    best_score = 0.0

                    for entry, sim, _ in existing:
                        entry_words = set()
                        for tag in entry.tags:
                            for w in tag.lower().replace('?', '').split():
                                if len(w) > 2:
                                    entry_words.add(w)
                        for w in entry.content[:200].lower().split():
                            if len(w) > 3:
                                entry_words.add(w)

                        topic_overlap = len(topic_words & entry_words)
                        combined = sim + (0.15 * min(topic_overlap, 3))

                        if combined > best_score:
                            best_score = combined
                            best_match = (entry, sim, combined)

                    if best_match:
                        entry, sim, combined = best_match

                        if sim > 0.90:
                            # Nearly identical — skip
                            logger.debug(
                                f"Skipping identical knowledge (sim={sim:.2f}): "
                                f"{content[:60]}..."
                            )
                            return entry.id

                        elif combined > 0.55:
                            # Related — but is it the SAME subject?
                            existing_subject = self._extract_subject(entry.content)
                            same_subject = self._subjects_match(
                                new_subject, existing_subject
                            )

                            if same_subject:
                                # Same subject → ENRICH
                                enriched = self._moltbook.enrich_entry(
                                    entry_id=entry.id,
                                    new_content=content,
                                    new_tags=topics[:5],
                                )
                                if enriched:
                                    logger.debug(
                                        f"Enriched entry {entry.id} "
                                        f"(sim={sim:.2f}, subj='{existing_subject}'): "
                                        f"+{content[:60]}..."
                                    )
                                    return entry.id
                            else:
                                # Different subject → CREATE new + LINK
                                new_id = self._create_entry(
                                    content, topics,
                                    result.get('source', 'external'),
                                )
                                if new_id:
                                    self._moltbook.link_entries(
                                        new_id, entry.id, "extends"
                                    )
                                    logger.debug(
                                        f"New entry {new_id} "
                                        f"(subj='{new_subject}') "
                                        f"linked to {entry.id} "
                                        f"(subj='{existing_subject}')"
                                    )
                                    return new_id
        except Exception as e:
            logger.debug(f"_store_knowledge routing failed: {e}")

        # ── Completely new topic — create standalone entry ──
        return self._create_entry(content, topics, result.get('source', 'external'))

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_augments': self._total_augments,
            'total_wiki': self._total_wiki,
            'total_web': self._total_web,
            'cache_size': len(self._cache),
        }


class RealtimeResponseEngine:
    """
    Fast response generation pipeline connecting all Moltbook components.

    Flow:
      1. Retrieve entries (Moltbook + Speculative)
      1b. KnowledgeAugmentor (Wikipedia/Web if internal knowledge insufficient)
      2. Consult ThoughtStream (background thoughts)
      3. InternalMonologue (3-thread thinking)
      4. TalkerModule (thought → speech) with intent-aware synthesis

    Each step is optional — graceful degradation if components unavailable.
    """

    # Self-knowledge: who the system is
    _IDENTITY = {
        'name': 'Tahlamus',
        'description': 'an AI brain system inspired by neuroscience',
        'capabilities': 'learning, reasoning, and discussing knowledge',
        'greeting_responses': [
            "Hello! I'm Tahlamus, an AI brain system. I can discuss topics, answer questions, and learn new things. What would you like to talk about?",
            "Hi there! I'm Tahlamus — a neuroscience-inspired AI. Ask me anything or share something interesting!",
            "Hey! I'm Tahlamus, your knowledge companion. What's on your mind?",
        ],
    }

    def __init__(self, moltbook=None, thought_stream=None,
                 internal_monologue=None, talker=None,
                 speculative=None, relevance_scorer=None,
                 meta_thinking=None, knowledge_augmentor=None):
        self._moltbook = moltbook                    # MoltbookStore
        self._thought_stream = thought_stream        # ThoughtStream
        self._internal_monologue = internal_monologue  # InternalMonologue
        self._talker = talker                        # TalkerModule
        self._speculative = speculative              # SpeculativeRetrieval
        self._relevance_scorer = relevance_scorer    # RelevanceScorer
        self._meta_thinking = meta_thinking          # MetaThinking
        self._augmentor = knowledge_augmentor        # KnowledgeAugmentor
        self._total_responses = 0
        logger.info("RealtimeResponseEngine initialized")

    def generate(self, user_input: str, analysis: InputAnalysis,
                 budget: Dict[str, Any],
                 debug: Optional['DebugStream'] = None) -> PipelineResult:
        """
        Generate a response through the full pipeline.

        Phase C: Intent-aware generation with knowledge augmentation.
        Greetings get identity responses, questions get augmented answers.
        """
        t0 = time.time()
        self._total_responses += 1
        result = PipelineResult(input_analysis=analysis)

        # ── Short-circuit: Greetings ──
        if analysis.intent == 'greeting':
            import random
            result.response_text = random.choice(self._IDENTITY['greeting_responses'])
            result.confidence = 0.95
            result.total_time_ms = (time.time() - t0) * 1000
            return result

        # ── Step 1: Retrieve knowledge ──
        t_retrieve = time.time()
        entries = []
        scored_entries = []  # (entry, similarity, combined)
        max_similarity = 0.0
        speculative_hits = 0

        if self._moltbook and analysis.requires_knowledge:
            try:
                top_k = budget.get('retrieval_depth', 7)
                scored_entries = self._moltbook.query_semantic(
                    user_input, top_k=top_k, threshold=0.15,
                    return_scores=True,
                )
                if scored_entries:
                    entries = [e for e, _, _ in scored_entries]
                    max_similarity = max(sim for _, sim, _ in scored_entries)
                else:
                    entries = self._moltbook.get_active_entries(top_k=min(top_k, 5))
                result.entries_retrieved = len(entries)

                if debug:
                    for e in entries[:3]:
                        debug.retrieve(e.id, getattr(e, 'relevance_score', 0.5))
            except Exception as e:
                logger.warning(f"Retrieval failed: {e}")

        # Check speculative buffer
        if self._speculative and entries:
            for entry in entries:
                if self._speculative.check_hit(entry.id):
                    speculative_hits += 1
            result.speculative_hits = speculative_hits

        # Score and rank
        if self._relevance_scorer and entries:
            try:
                entries = self._relevance_scorer.score(
                    entries, user_input,
                    emotional_valence=analysis.emotional_tone
                )
            except Exception:
                pass

        result.retrieve_time_ms = (time.time() - t_retrieve) * 1000

        # ── Step 1b: Knowledge Augmentation ──
        augmented = {'augmented': False, 'combined_answer': ''}
        if self._augmentor:
            try:
                augmented = self._augmentor.augment(
                    query=user_input,
                    topics=analysis.topics,
                    internal_entries=entries,
                    max_similarity=max_similarity,
                    intent=analysis.intent,
                )
                if augmented.get('augmented') and debug:
                    debug.think(f"Knowledge augmented from {augmented.get('source', '?')}")
            except Exception as e:
                logger.warning(f"Augmentation failed: {e}")

        # ── Step 2: Consult ThoughtStream ──
        thoughts = []
        if self._thought_stream and budget.get('use_thought_stream', True):
            try:
                thoughts = self._thought_stream.get_relevant_thoughts(
                    user_input, top_k=5
                )
                result.thoughts_consulted = len(thoughts)

                if debug and thoughts:
                    debug.think(f"Found {len(thoughts)} relevant background thoughts")
            except Exception:
                pass

        # ── Step 3: Think (InternalMonologue) ──
        t_think = time.time()
        unified_thought = None

        if self._internal_monologue and analysis.requires_reasoning:
            try:
                unified_thought = self._internal_monologue.think(
                    user_input,
                    moltbook_entries=entries,
                    affect={'valence': analysis.emotional_tone},
                )
                result.confidence = unified_thought.confidence
                result.quality_passed = unified_thought.quality_passed
                result.sources = unified_thought.source_entry_ids

                if debug:
                    debug.think(f"Unified thought: confidence={unified_thought.confidence:.2f}")
            except Exception as e:
                logger.warning(f"Thinking failed: {e}")

        # MetaThinking quality check
        if self._meta_thinking and thoughts:
            try:
                quality = self._meta_thinking.evaluate(thoughts=thoughts,
                                                        unified_thought=unified_thought)
                if debug:
                    debug.think(f"Thought quality: productivity={quality.productivity:.2f}, "
                               f"recommendation={quality.recommendation}")
            except Exception:
                pass

        result.think_time_ms = (time.time() - t_think) * 1000

        # ── Step 4: Speak (intent-aware synthesis) ──
        t_speak = time.time()

        # If we augmented knowledge, inject it into the thought/talker flow
        augmented_answer = augmented.get('combined_answer', '')

        if self._talker:
            try:
                thought_input = unified_thought if unified_thought else {
                    'narrative': f"The user asks: {user_input[:200]}",
                    'confidence': result.confidence,
                    'emotional_tone': analysis.emotional_tone,
                    'key_facts': [e.content[:100] for e in entries[:3]] if entries else [],
                    'source_entry_ids': [e.id for e in entries[:5]] if entries else [],
                    'processing_time_ms': result.think_time_ms,
                }

                # Inject augmented knowledge into the thought
                if augmented_answer:
                    if isinstance(thought_input, dict):
                        thought_input['augmented_answer'] = augmented_answer
                        thought_input['confidence'] = max(
                            thought_input.get('confidence', 0.5), 0.7
                        )
                    else:
                        # UnifiedThought object — set augmented_answer attribute
                        thought_input.augmented_answer = augmented_answer
                        thought_input.confidence = max(thought_input.confidence, 0.7)

                talker_response = self._talker.speak(
                    thought_input,
                    context=user_input,
                    complexity=analysis.complexity,
                )
                result.response_text = talker_response.text
                result.confidence = talker_response.confidence

                if debug:
                    debug.speak(talker_response.confidence,
                               talker_response.response_plan.length if talker_response.response_plan else "")
            except Exception as e:
                logger.warning(f"Speaking failed: {e}")
                result.response_text = f"I understand your query about: {', '.join(analysis.topics[:3])}"
        else:
            # Fallback: no talker — use augmented answer or assemble from entries
            if augmented_answer:
                result.response_text = augmented_answer
                result.confidence = 0.7
            elif unified_thought:
                result.response_text = unified_thought.narrative
            elif entries:
                best = entries[0]
                result.response_text = best.content
                result.confidence = best.confidence
                result.sources = [e.id for e in entries[:5]]
                if len(entries) > 1:
                    extra = [e.content[:120] for e in entries[1:3]]
                    result.response_text += "\n\n" + "\n".join(f"- {c}" for c in extra)
            else:
                topic_str = ', '.join(analysis.topics[:3]) if analysis.topics else user_input[:100]
                result.response_text = f"I don't have specific knowledge about {topic_str} yet, but I'm always learning!"

        result.speak_time_ms = (time.time() - t_speak) * 1000
        result.total_time_ms = (time.time() - t0) * 1000

        # Update speculative retrieval for next call
        if self._speculative and analysis.topics:
            try:
                self._speculative.prefetch(analysis.topics)
            except Exception:
                pass

        return result

    def get_stats(self) -> Dict[str, Any]:
        return {'total_responses': self._total_responses}


# ═══════════════════════════════════════════════════════════════════
# [46] ThinkTalkOrchestrator — Main Pipeline Coordinator
# ═══════════════════════════════════════════════════════════════════

class ThinkTalkOrchestrator:
    """
    Main pipeline: coordinates Input → Retrieve → Think → Speak.

    This is the top-level entry point for the Moltbook response system.

    Flow:
      1. InputAnalyzer → determine intent, complexity, topics
      2. ThinkingBudget → allocate effort
      3. RealtimeResponseEngine → full pipeline
      4. PerformanceMonitor → track quality
      5. DebugStream → optional transparency

    Integration with AgentLoop:
      - Called from AgentLoop when user input arrives
      - Can short-circuit for simple greetings/acknowledgements
      - Safety check via SafetyGovernor before final output
    """

    def __init__(self, engine: Optional[RealtimeResponseEngine] = None,
                 analyzer: Optional[InputAnalyzer] = None,
                 budget_allocator: Optional[ThinkingBudget] = None,
                 safety=None):
        self._engine = engine or RealtimeResponseEngine()
        self._analyzer = analyzer or InputAnalyzer()
        self._budget = budget_allocator or ThinkingBudget()
        self._safety = safety                         # SafetyGovernor (optional)
        self._monitor = PerformanceMonitor()
        self._debug = DebugStream()
        self._total_orchestrated = 0
        logger.info("ThinkTalkOrchestrator initialized")

    @property
    def debug_stream(self) -> DebugStream:
        return self._debug

    @property
    def performance_monitor(self) -> PerformanceMonitor:
        return self._monitor

    def process(self, user_input: str) -> PipelineResult:
        """
        Process user input through the full Moltbook pipeline.

        This is the main entry point — call this with user text,
        get back a PipelineResult with response + metadata.
        """
        self._total_orchestrated += 1
        t0 = time.time()

        # Step 1: Analyze input
        analysis = self._analyzer.analyze(user_input)

        if self._debug.enabled:
            self._debug.log('INPUT', f"Intent={analysis.intent}, "
                           f"complexity={analysis.complexity:.2f}, "
                           f"topics={analysis.topics[:5]}")

        # Step 2: Allocate thinking budget
        budget = self._budget.allocate(analysis)

        if self._debug.enabled:
            self._debug.budget(budget['depth'], budget['max_think_ms'])

        # Step 3: Generate response
        result = self._engine.generate(
            user_input, analysis, budget, debug=self._debug
        )

        # Step 4: Safety check (optional)
        if self._safety and result.response_text:
            try:
                safety_result = self._safety.check_action({
                    'type': 'response',
                    'content': result.response_text[:500],
                }) if hasattr(self._safety, 'check_action') else None
                if safety_result and isinstance(safety_result, dict):
                    if safety_result.get('blocked', False):
                        result.response_text = ("I need to be careful with this response. "
                                                "Let me provide a safer answer.")
                        result.quality_passed = False
            except Exception:
                pass

        result.total_time_ms = (time.time() - t0) * 1000

        # Step 5: Monitor
        alerts = self._monitor.record(result)
        if alerts and self._debug.enabled:
            for a in alerts:
                self._debug.log('ALERT', a)

        return result

    def enable_debug(self) -> None:
        """Enable debug stream."""
        self._debug.enable()

    def disable_debug(self) -> None:
        """Disable debug stream."""
        self._debug.disable()

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_orchestrated': self._total_orchestrated,
            'engine': self._engine.get_stats(),
            'analyzer': self._analyzer.get_stats(),
            'budget': self._budget.get_stats(),
            'monitor': self._monitor.get_stats(),
            'debug': self._debug.get_stats(),
        }

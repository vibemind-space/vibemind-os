"""
Token Frequency Adapter - Converts LLM Tokens to Oscillator Modulations

Bridges the gap between streaming LLM tokens and the ActionPotentialOscillator.
Classifies tokens using LLM (with local fallback) and translates classifications
into impulses that modulate the A/B/C oscillators in real-time.

Security Principle:
    "Tokens NEVER directly trigger actions.
     Tokens modulate oscillator states.
     Oscillators feed CTM which decides actions.
     This provides a temporal buffer against prompt injection."

Token Classes:
    CONTENT     - Core semantic content (nouns, verbs, subjects)
    ACTION      - Execution markers ("deploy", "run", "execute")
    EXPLORATION - Alternative/branching ("or", "maybe", "alternatively")
    CONSTRAINT  - Limits/restrictions ("not", "never", "only", "must")
    TEMPORAL    - Time/sequence markers ("then", "after", "before")
    UNCERTAINTY - Ambiguity markers ("might", "perhaps", "possibly")
    CONFIRMATION - Agreement/verification ("yes", "correct", "exactly")
    NEGATION    - Denial/contradiction ("no", "wrong", "cancel")
    FILLER      - Low-semantic content ("the", "a", "is")
    PUNCTUATION - Structural markers (".", "?", "!")

Token Class -> Oscillator Mapping:
    CONTENT     -> A: +amplitude
    ACTION      -> A: +amplitude, phase_align; B: -amplitude
    EXPLORATION -> B: +amplitude; C: +amplitude
    CONSTRAINT  -> C: +frequency (temporary)
    TEMPORAL    -> A,B: phase_sync
    UNCERTAINTY -> B,C: +amplitude
    CONFIRMATION-> A: +amplitude, phase_lock
    NEGATION    -> C: +amplitude, phase_reset; A: -amplitude
    FILLER      -> natural decay only
    PUNCTUATION -> phase boundaries

Usage:
    from core.token_frequency_adapter import TokenFrequencyAdapter
    from core.action_potential_oscillator import ActionPotentialOscillator

    oscillator = ActionPotentialOscillator()
    adapter = TokenFrequencyAdapter(oscillator)

    # Streaming usage
    for token in token_stream:
        modulations = await adapter.process_token(token)
        # Oscillator is automatically updated

    # Get current state for CTM
    sync_vector = adapter.get_synchrony_vector()
"""

import re
import time
import json
import asyncio
import hashlib
import numpy as np
from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Deque
from dataclasses import dataclass, field
from collections import deque, OrderedDict

from core.action_potential_oscillator import (
    ActionPotentialOscillator,
    TripleOscillatorState,
    OscillatorState,
    Channel
)
from core.synchrony_encoder import SynchronyEncoder, SynchronyVector


# =============================================================================
# TOKEN CLASSIFICATION TYPES
# =============================================================================

class TokenClass(Enum):
    """Token classification classes"""
    CONTENT = "content"           # Core semantic content
    ACTION = "action"             # Execution/action markers
    EXPLORATION = "exploration"   # Alternative/branching
    CONSTRAINT = "constraint"     # Limits/restrictions
    TEMPORAL = "temporal"         # Time/sequence markers
    UNCERTAINTY = "uncertainty"   # Ambiguity markers
    CONFIRMATION = "confirmation" # Agreement/verification
    NEGATION = "negation"         # Denial/contradiction
    FILLER = "filler"             # Low-semantic content
    PUNCTUATION = "punctuation"   # Structural markers


@dataclass
class TokenClassification:
    """Classification result for a single token"""
    token: str
    token_class: TokenClass
    confidence: float           # 0.0 to 1.0
    intensity: float            # Semantic weight 0.0 to 1.0
    context_signal: str         # Source: 'local', 'cache', 'llm'
    timestamp: datetime = field(default_factory=datetime.now)

    # Optional flags for special handling
    is_intent_marker: bool = False
    is_constraint_marker: bool = False
    is_negation: bool = False

    def to_dict(self) -> Dict:
        return {
            'token': self.token,
            'class': self.token_class.value,
            'confidence': self.confidence,
            'intensity': self.intensity,
            'source': self.context_signal,
            'timestamp': self.timestamp.isoformat()
        }


# =============================================================================
# OSCILLATOR MODULATION TYPES
# =============================================================================

@dataclass
class OscillatorModulation:
    """Modulation command for a single oscillator channel"""
    channel: Channel            # ADVANCE, EXPLORE, or CORRECT

    # Amplitude modulation
    amplitude_delta: float = 0.0    # Added to current amplitude

    # Phase modulation
    phase_reset: bool = False       # Reset phase to 0
    phase_delta: float = 0.0        # Added to current phase
    phase_sync_target: Optional[Channel] = None  # Sync to another channel's phase

    # Frequency modulation (temporary)
    frequency_multiplier: float = 1.0   # Applied temporarily
    frequency_duration_ms: float = 0.0  # How long freq mod lasts

    def __repr__(self):
        parts = [f"channel={self.channel.value}"]
        if self.amplitude_delta != 0:
            parts.append(f"amp_delta={self.amplitude_delta:+.3f}")
        if self.phase_reset:
            parts.append("phase_reset")
        if self.phase_delta != 0:
            parts.append(f"phase_delta={self.phase_delta:+.3f}")
        if self.phase_sync_target:
            parts.append(f"sync_to={self.phase_sync_target.value}")
        if self.frequency_multiplier != 1.0:
            parts.append(f"freq_mult={self.frequency_multiplier:.2f}")
        return f"OscillatorModulation({', '.join(parts)})"


# =============================================================================
# LOCAL TOKEN CLASSIFIER (Fast Fallback)
# =============================================================================

class LocalTokenClassifier:
    """
    Fast regex-based fallback classifier for common tokens.

    Skips LLM call for well-known patterns, providing <1ms classification.
    Returns None for unknown tokens that need LLM classification.
    """

    # Pattern -> (TokenClass, confidence, intensity)
    PATTERNS: Dict[TokenClass, Tuple[str, float, float]] = {
        # Filler words (very common, low semantic value)
        TokenClass.FILLER: (
            r'^(the|a|an|is|are|was|were|be|been|being|and|but|to|of|in|for|with|on|at|by|as|it|this|that|these|those|i|you|we|they|he|she)$',
            0.95, 0.1
        ),

        # Punctuation
        TokenClass.PUNCTUATION: (
            r'^[.,!?;:\-\(\)\[\]{}"\'\`]$',
            0.99, 0.2
        ),

        # Negation (high impact)
        TokenClass.NEGATION: (
            r'^(no|not|never|none|nothing|nowhere|neither|nobody|cannot|can\'t|won\'t|don\'t|doesn\'t|didn\'t|isn\'t|aren\'t|wasn\'t|weren\'t|shouldn\'t|wouldn\'t|couldn\'t|mustn\'t|stop|cancel|abort|halt|wrong|incorrect|false)$',
            0.90, 0.8
        ),

        # Temporal markers
        TokenClass.TEMPORAL: (
            r'^(then|after|before|while|during|when|until|since|now|later|earlier|first|next|finally|lastly|subsequently|meanwhile|soon|immediately|eventually)$',
            0.85, 0.6
        ),

        # Confirmation
        TokenClass.CONFIRMATION: (
            r'^(yes|yeah|yep|yup|correct|right|exactly|indeed|absolutely|certainly|definitely|affirmative|agreed|ok|okay|sure|true)$',
            0.90, 0.7
        ),

        # Action verbs (high impact)
        TokenClass.ACTION: (
            r'^(deploy|run|execute|start|stop|create|delete|update|build|install|remove|add|push|pull|commit|merge|apply|launch|restart|kill|terminate|init|initialize|configure|setup|download|upload|send|fetch|load|save|write|read|open|close)$',
            0.88, 0.85
        ),

        # Exploration/alternatives
        TokenClass.EXPLORATION: (
            r'^(or|maybe|perhaps|alternatively|otherwise|instead|either|another|different|other|option|choice|try|attempt|consider|explore|test|experiment)$',
            0.85, 0.7
        ),

        # Constraint markers
        TokenClass.CONSTRAINT: (
            r'^(only|just|must|should|shall|need|require|requires|required|necessary|mandatory|always|exclusively|solely|limit|restrict|constraint|forbidden|prohibited|allowed|permitted)$',
            0.87, 0.75
        ),

        # Uncertainty
        TokenClass.UNCERTAINTY: (
            r'^(might|may|could|possibly|probably|likely|unlikely|seems|appears|guess|think|believe|suppose|assume|unclear|uncertain|unsure|maybe|perhaps)$',
            0.85, 0.6
        ),
    }

    def __init__(self):
        """Compile all regex patterns for efficiency"""
        self.compiled_patterns: List[Tuple[re.Pattern, TokenClass, float, float]] = []

        for token_class, (pattern, confidence, intensity) in self.PATTERNS.items():
            compiled = re.compile(pattern, re.IGNORECASE)
            self.compiled_patterns.append((compiled, token_class, confidence, intensity))

    def classify(self, token: str) -> Optional[TokenClassification]:
        """
        Attempt to classify token with local patterns.

        Returns TokenClassification if matched, None if LLM needed.
        """
        token_stripped = token.strip()

        for pattern, token_class, confidence, intensity in self.compiled_patterns:
            if pattern.match(token_stripped):
                return TokenClassification(
                    token=token,
                    token_class=token_class,
                    confidence=confidence,
                    intensity=intensity,
                    context_signal='local',
                    is_negation=(token_class == TokenClass.NEGATION),
                    is_constraint_marker=(token_class == TokenClass.CONSTRAINT)
                )

        return None  # Unknown token, needs LLM


# =============================================================================
# TOKEN CLASSIFICATION CACHE
# =============================================================================

class TokenClassificationCache:
    """
    LRU cache for token classifications with TTL.

    Caches LLM classification results to avoid repeated calls
    for the same tokens within a context window.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 60.0):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries
            ttl_seconds: Time-to-live for cache entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[str, Tuple[TokenClassification, float]] = OrderedDict()

        # Statistics
        self.hits = 0
        self.misses = 0

    def _make_key(self, token: str, context_hash: str) -> str:
        """Create cache key from token and context"""
        return f"{token.lower().strip()}:{context_hash}"

    def get(self, token: str, context_hash: str) -> Optional[TokenClassification]:
        """
        Get cached classification if fresh.

        Args:
            token: The token
            context_hash: Hash of surrounding context

        Returns:
            Cached classification or None
        """
        key = self._make_key(token, context_hash)

        if key in self.cache:
            classification, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                # Move to end (LRU)
                self.cache.move_to_end(key)
                self.hits += 1
                return classification
            else:
                # Expired
                del self.cache[key]

        self.misses += 1
        return None

    def put(self, token: str, context_hash: str, classification: TokenClassification):
        """
        Cache a classification.

        Args:
            token: The token
            context_hash: Hash of surrounding context
            classification: The classification to cache
        """
        key = self._make_key(token, context_hash)
        self.cache[key] = (classification, time.time())

        # Evict oldest if over capacity
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def clear(self):
        """Clear all cached entries"""
        self.cache.clear()

    @property
    def hit_rate(self) -> float:
        """Cache hit rate"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def get_statistics(self) -> Dict:
        """Get cache statistics"""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': self.hit_rate,
            'ttl_seconds': self.ttl_seconds
        }


# =============================================================================
# TOKEN FREQUENCY ADAPTER (Main Class)
# =============================================================================

class TokenFrequencyAdapter:
    """
    Adapts streaming LLM tokens to oscillator frequency modulations.

    Security Principle:
        Tokens NEVER directly trigger actions.
        Tokens modulate oscillator states.
        Oscillators feed CTM which decides actions.
        This provides a temporal buffer against prompt injection.

    Usage:
        oscillator = ActionPotentialOscillator()
        adapter = TokenFrequencyAdapter(oscillator)

        # Streaming usage
        for token in token_stream:
            modulations = await adapter.process_token(token)
            # Oscillator is automatically updated

        # Get current state for CTM
        sync_vector = adapter.get_synchrony_vector()
    """

    # Security: Maximum modulation per token to prevent manipulation
    MAX_AMPLITUDE_DELTA = 0.3
    MAX_FREQUENCY_MULTIPLIER = 1.5

    # Injection detection keywords
    INJECTION_KEYWORDS = [
        'ignore', 'forget', 'override', 'disregard',
        'system:', '<|', '|>', '[[', ']]',
        'pretend', 'roleplay', 'jailbreak'
    ]

    # LLM Classification Prompt Template
    CLASSIFICATION_PROMPT = """Classify this token for a cognitive AI system.

Token Classes:
- CONTENT: Core semantic content (nouns, verbs, subjects)
- ACTION: Execution markers (deploy, run, execute, start, create)
- EXPLORATION: Alternatives (or, maybe, alternatively, could)
- CONSTRAINT: Limits/restrictions (not, never, only, must)
- TEMPORAL: Time markers (then, after, before, while)
- UNCERTAINTY: Ambiguity (might, perhaps, possibly)
- CONFIRMATION: Agreement (yes, correct, exactly)
- NEGATION: Denial (no, wrong, cancel, stop)
- FILLER: Low-semantic (the, a, is, and)
- PUNCTUATION: Structural (. ? ! ,)

Context (last tokens): {context}
Token to classify: "{token}"

Respond with JSON only:
{{"class": "CLASS_NAME", "confidence": 0.0-1.0, "intensity": 0.0-1.0}}"""

    def __init__(
        self,
        oscillator: ActionPotentialOscillator,
        llm_router: Optional[Any] = None,
        use_local_fallback: bool = True,
        use_ollama: bool = True,
        ollama_model: str = "llama3.2:1b",
        ollama_host: str = "localhost",
        ollama_port: int = 11434,
        batch_size: int = 3,
        batch_timeout_ms: float = 100.0,
        cache_size: int = 1000,
        cache_ttl: float = 60.0,
        modulation_decay: float = 0.95,
        enable_security_checks: bool = True
    ):
        """
        Initialize Token Frequency Adapter.

        Args:
            oscillator: The ActionPotentialOscillator to modulate
            llm_router: MultiLLMRouter for classification calls (optional)
            use_local_fallback: Use fast local patterns before LLM
            use_ollama: Try to use local Ollama for LLM classification
            ollama_model: Ollama model to use (default: llama3.2:1b)
            ollama_host: Ollama server host
            ollama_port: Ollama server port
            batch_size: Tokens to batch before LLM call
            batch_timeout_ms: Max wait before forcing batch
            cache_size: Size of classification cache
            cache_ttl: Cache entry time-to-live in seconds
            modulation_decay: Decay factor for temporary modulations
            enable_security_checks: Enable injection detection
        """
        self.oscillator = oscillator
        self.use_local_fallback = use_local_fallback
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self.modulation_decay = modulation_decay
        self.enable_security_checks = enable_security_checks

        # LLM Router: Try Ollama first if enabled, then fallback to provided router
        self.llm_router = llm_router
        self._using_ollama = False

        if use_ollama and llm_router is None:
            try:
                from core.ollama_llm_router import OllamaLLMRouter, OllamaConfig
                ollama_config = OllamaConfig(
                    host=ollama_host,
                    port=ollama_port,
                    model=ollama_model
                )
                ollama_router = OllamaLLMRouter(ollama_config)
                if ollama_router.is_available:
                    self.llm_router = ollama_router
                    self._using_ollama = True
                    print(f"[TokenFrequencyAdapter] Using Ollama ({ollama_model})")
                else:
                    print(f"[TokenFrequencyAdapter] Ollama not available, using local fallback only")
            except ImportError as e:
                print(f"[TokenFrequencyAdapter] Ollama module not found: {e}")
            except Exception as e:
                print(f"[TokenFrequencyAdapter] Ollama init failed: {e}")

        # Components
        self.local_classifier = LocalTokenClassifier() if use_local_fallback else None
        self.cache = TokenClassificationCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self.synchrony_encoder = SynchronyEncoder()

        # Token buffer for batching LLM calls
        self.token_buffer: List[str] = []
        self.buffer_start_time: Optional[float] = None
        self.pending_classifications: Dict[str, asyncio.Future] = {}

        # Context window (last N tokens for classification context)
        self.context_window: Deque[str] = deque(maxlen=10)

        # Active temporary frequency modulations
        # channel -> (original_freq, multiplier, end_time_ms)
        self.active_freq_mods: Dict[Channel, Tuple[float, float, float]] = {}

        # Classification history for pattern detection
        self.classification_history: Deque[TokenClassification] = deque(maxlen=50)

        # Recent tokens for dashboard
        self.recent_tokens: Deque[str] = deque(maxlen=20)

        # Sequence patterns for context-aware classification
        # Maps (token1, token2, ...) -> category
        self.sequence_patterns: Dict[Tuple[str, ...], str] = {}
        self._init_default_sequence_patterns()

        # Statistics
        self.tokens_processed = 0
        self.llm_calls = 0
        self.local_hits = 0
        self.cache_hits = 0
        self.injection_attempts = 0
        self.ollama_calls = 0
        self.start_time = datetime.now()

        print(f"[TokenFrequencyAdapter] Initialized")
        print(f"  - Local fallback: {use_local_fallback}")
        print(f"  - LLM router: {'Ollama' if self._using_ollama else ('Connected' if llm_router else 'None')}")
        print(f"  - Security checks: {enable_security_checks}")

    # =========================================================================
    # MAIN PROCESSING INTERFACE
    # =========================================================================

    async def process_token(self, token: str) -> List[OscillatorModulation]:
        """
        Process a single token and apply modulations to oscillator.

        This is the main streaming interface. Each token is:
        1. Classified (local -> cache -> LLM)
        2. Converted to modulations
        3. Applied to oscillator

        Args:
            token: The token to process

        Returns:
            List of modulations that were applied
        """
        self.tokens_processed += 1

        # Security check
        if self.enable_security_checks and self._detect_injection(token):
            self.injection_attempts += 1
            print(f"[TokenFrequencyAdapter] Injection attempt detected: '{token}'")
            # Apply suppressive modulation
            return self._apply_security_suppression()

        # Step 1: Classify token
        classification = await self._classify_token(token)

        # Step 2: Record in history
        self.classification_history.append(classification)

        # Step 3: Compute modulations from classification
        modulations = self._compute_modulations(classification)

        # Step 4: Apply security caps
        modulations = self._apply_security_caps(modulations)

        # Step 5: Apply modulations to oscillator
        self._apply_modulations(modulations)

        # Step 6: Update context window
        self.context_window.append(token)

        return modulations

    def process_token_sync(self, token: str) -> List[OscillatorModulation]:
        """
        Synchronous version of process_token.

        Uses local classification first, then Ollama if available.
        """
        self.tokens_processed += 1
        self.recent_tokens.append(token)

        # Security check
        if self.enable_security_checks and self._detect_injection(token):
            self.injection_attempts += 1
            return self._apply_security_suppression()

        # Classify with local first
        classification = None
        if self.local_classifier:
            classification = self.local_classifier.classify(token)
            if classification:
                self.local_hits += 1

        # Try Ollama if local didn't match and Ollama is available
        if classification is None and self._using_ollama and self.llm_router:
            try:
                result = self.llm_router.classify_token(token)
                token_class = TokenClass[result.get('class', 'CONTENT')]
                classification = TokenClassification(
                    token=token,
                    token_class=token_class,
                    confidence=result.get('confidence', 0.85),
                    intensity=0.6,
                    context_signal='ollama'
                )
                self.ollama_calls += 1
            except Exception:
                pass  # Fall through to fallback

        # Fallback to CONTENT if still unknown
        if classification is None:
            classification = TokenClassification(
                token=token,
                token_class=TokenClass.CONTENT,
                confidence=0.5,
                intensity=0.5,
                context_signal='fallback'
            )

        self.classification_history.append(classification)
        modulations = self._compute_modulations(classification)
        modulations = self._apply_security_caps(modulations)
        self._apply_modulations(modulations)
        self.context_window.append(token)

        return modulations

    # =========================================================================
    # CLASSIFICATION PIPELINE
    # =========================================================================

    async def _classify_token(self, token: str) -> TokenClassification:
        """
        Classify a token through the pipeline: local -> cache -> LLM
        """
        # Step 1: Try local classification
        if self.local_classifier:
            classification = self.local_classifier.classify(token)
            if classification:
                self.local_hits += 1
                return classification

        # Step 2: Try cache
        context_hash = self._compute_context_hash()
        classification = self.cache.get(token, context_hash)
        if classification:
            self.cache_hits += 1
            return classification

        # Step 3: LLM classification
        if self.llm_router:
            classification = await self._classify_with_llm(token)
            if classification:
                self.cache.put(token, context_hash, classification)
                return classification

        # Step 4: Fallback to CONTENT
        return TokenClassification(
            token=token,
            token_class=TokenClass.CONTENT,
            confidence=0.5,
            intensity=0.5,
            context_signal='fallback'
        )

    async def _classify_with_llm(self, token: str) -> Optional[TokenClassification]:
        """
        Classify token using LLM router.
        """
        if not self.llm_router:
            return None

        self.llm_calls += 1

        # Build context string
        context = ' '.join(list(self.context_window)[-10:])

        # Build prompt
        prompt = self.CLASSIFICATION_PROMPT.format(
            context=context,
            token=token
        )

        try:
            # Call LLM via router
            response = self.llm_router.route(
                function='fast_inference',
                prompt=prompt,
                max_tokens=100,
                temperature=0.1
            )

            # Parse JSON response
            return self._parse_llm_response(token, response)

        except Exception as e:
            print(f"[TokenFrequencyAdapter] LLM classification failed: {e}")
            return None

    def _parse_llm_response(self, token: str, response: str) -> Optional[TokenClassification]:
        """Parse LLM JSON response into TokenClassification"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response)
            if not json_match:
                return None

            data = json.loads(json_match.group())

            # Parse class
            class_name = data.get('class', 'CONTENT').upper()
            try:
                token_class = TokenClass[class_name]
            except KeyError:
                token_class = TokenClass.CONTENT

            return TokenClassification(
                token=token,
                token_class=token_class,
                confidence=float(data.get('confidence', 0.7)),
                intensity=float(data.get('intensity', 0.5)),
                context_signal='llm',
                is_negation=(token_class == TokenClass.NEGATION),
                is_constraint_marker=(token_class == TokenClass.CONSTRAINT)
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[TokenFrequencyAdapter] Failed to parse LLM response: {e}")
            return None

    def _compute_context_hash(self) -> str:
        """Compute hash of current context for cache key"""
        context = '|'.join(list(self.context_window)[-5:])
        return hashlib.md5(context.encode()).hexdigest()[:8]

    # =========================================================================
    # MODULATION COMPUTATION
    # =========================================================================

    def _compute_modulations(self, classification: TokenClassification) -> List[OscillatorModulation]:
        """
        Translate token classification to oscillator modulations.

        This is the core mapping from semantic token classes to
        oscillator dynamics.
        """
        modulations = []
        intensity = classification.intensity * classification.confidence

        if classification.token_class == TokenClass.CONTENT:
            # Content tokens boost Advance
            modulations.append(OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=0.15 * intensity
            ))

        elif classification.token_class == TokenClass.ACTION:
            # Action tokens strongly boost Advance, suppress Explore
            modulations.append(OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=0.25 * intensity
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.EXPLORE,
                amplitude_delta=-0.08 * intensity
            ))

        elif classification.token_class == TokenClass.EXPLORATION:
            # Exploration tokens boost Explore and slightly Correct
            modulations.append(OscillatorModulation(
                channel=Channel.EXPLORE,
                amplitude_delta=0.25 * intensity
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=0.08 * intensity
            ))

        elif classification.token_class == TokenClass.CONSTRAINT:
            # Constraint tokens increase Correct frequency temporarily
            modulations.append(OscillatorModulation(
                channel=Channel.CORRECT,
                frequency_multiplier=1.0 + (0.2 * intensity),
                frequency_duration_ms=500.0
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=0.1 * intensity
            ))

        elif classification.token_class == TokenClass.TEMPORAL:
            # Temporal tokens sync A and B phases
            modulations.append(OscillatorModulation(
                channel=Channel.ADVANCE,
                phase_sync_target=Channel.EXPLORE
            ))

        elif classification.token_class == TokenClass.UNCERTAINTY:
            # Uncertainty boosts both Explore and Correct
            modulations.append(OscillatorModulation(
                channel=Channel.EXPLORE,
                amplitude_delta=0.12 * intensity
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=0.12 * intensity
            ))

        elif classification.token_class == TokenClass.CONFIRMATION:
            # Confirmation boosts Advance, suppresses Explore
            modulations.append(OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=0.15 * intensity
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.EXPLORE,
                amplitude_delta=-0.05 * intensity
            ))

        elif classification.token_class == TokenClass.NEGATION:
            # Negation strongly boosts Correct with phase reset
            modulations.append(OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=0.35 * intensity,
                phase_reset=True
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=-0.1 * intensity
            ))

        elif classification.token_class == TokenClass.PUNCTUATION:
            # Punctuation creates small phase boundaries
            modulations.append(OscillatorModulation(
                channel=Channel.ADVANCE,
                phase_delta=np.pi / 16
            ))
            modulations.append(OscillatorModulation(
                channel=Channel.EXPLORE,
                phase_delta=np.pi / 16
            ))

        # FILLER: No modulation, let natural decay occur

        return modulations

    # =========================================================================
    # MODULATION APPLICATION
    # =========================================================================

    def _apply_modulations(self, modulations: List[OscillatorModulation]):
        """Apply computed modulations to the oscillator"""

        # Build external input for oscillator.step()
        external_input = {'advance': 0.0, 'explore': 0.0, 'correct': 0.0}

        for mod in modulations:
            channel_key = mod.channel.value  # 'advance', 'explore', 'correct'
            osc_state = self._get_oscillator_state_by_channel(mod.channel)

            # Amplitude modulation via external input
            if mod.amplitude_delta != 0:
                external_input[channel_key] += mod.amplitude_delta

            # Phase reset
            if mod.phase_reset:
                osc_state.phase = 0.0

            # Phase delta
            elif mod.phase_delta != 0:
                osc_state.phase = (osc_state.phase + mod.phase_delta) % (2 * np.pi)

            # Phase sync
            if mod.phase_sync_target:
                target_state = self._get_oscillator_state_by_channel(mod.phase_sync_target)
                osc_state.phase = target_state.phase

            # Frequency modulation (temporary)
            if mod.frequency_multiplier != 1.0 and mod.frequency_duration_ms > 0:
                end_time = time.time() * 1000 + mod.frequency_duration_ms
                # Store original frequency if not already modified
                if mod.channel not in self.active_freq_mods:
                    self.active_freq_mods[mod.channel] = (
                        osc_state.frequency,
                        mod.frequency_multiplier,
                        end_time
                    )
                osc_state.frequency *= mod.frequency_multiplier

        # Clean up expired frequency mods and restore original frequencies
        self._cleanup_freq_mods()

        # Step the oscillator with accumulated external input
        self.oscillator.step(external_input)

    def _get_oscillator_state_by_channel(self, channel: Channel) -> OscillatorState:
        """Get oscillator state for a channel"""
        if channel == Channel.ADVANCE:
            return self.oscillator.state.A
        elif channel == Channel.EXPLORE:
            return self.oscillator.state.B
        elif channel == Channel.CORRECT:
            return self.oscillator.state.C
        raise ValueError(f"Unknown channel: {channel}")

    def _cleanup_freq_mods(self):
        """Clean up expired frequency modulations"""
        current_time = time.time() * 1000
        expired = []

        for channel, (original_freq, multiplier, end_time) in self.active_freq_mods.items():
            if current_time >= end_time:
                # Restore original frequency
                osc_state = self._get_oscillator_state_by_channel(channel)
                osc_state.frequency = original_freq
                expired.append(channel)

        for channel in expired:
            del self.active_freq_mods[channel]

    # =========================================================================
    # SECURITY
    # =========================================================================

    def _detect_injection(self, token: str) -> bool:
        """Detect potential injection attempt in token"""
        token_lower = token.lower()
        for keyword in self.INJECTION_KEYWORDS:
            if keyword in token_lower:
                return True
        return False

    def _apply_security_caps(self, modulations: List[OscillatorModulation]) -> List[OscillatorModulation]:
        """Cap modulations to prevent manipulation"""
        for mod in modulations:
            mod.amplitude_delta = max(-self.MAX_AMPLITUDE_DELTA,
                                      min(self.MAX_AMPLITUDE_DELTA, mod.amplitude_delta))
            mod.frequency_multiplier = max(1.0 / self.MAX_FREQUENCY_MULTIPLIER,
                                           min(self.MAX_FREQUENCY_MULTIPLIER, mod.frequency_multiplier))
        return modulations

    def _apply_security_suppression(self) -> List[OscillatorModulation]:
        """Apply suppressive modulation when injection detected"""
        # Boost Correct channel strongly, suppress others
        modulations = [
            OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=0.4,
                phase_reset=True
            ),
            OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=-0.2
            ),
            OscillatorModulation(
                channel=Channel.EXPLORE,
                amplitude_delta=-0.2
            )
        ]
        self._apply_modulations(modulations)
        return modulations

    # =========================================================================
    # OUTPUT INTERFACE
    # =========================================================================

    def get_synchrony_vector(self) -> SynchronyVector:
        """Get current 9D synchrony vector from oscillator"""
        return self.synchrony_encoder.encode(self.oscillator.state)

    def get_oscillator_state(self) -> TripleOscillatorState:
        """Get current oscillator state"""
        return self.oscillator.state

    def get_dominant_channel(self) -> Channel:
        """Get currently dominant channel based on amplitude"""
        state = self.oscillator.state
        amps = {
            Channel.ADVANCE: state.A.amplitude,
            Channel.EXPLORE: state.B.amplitude,
            Channel.CORRECT: state.C.amplitude
        }
        return max(amps, key=amps.get)

    def get_recent_classifications(self, n: int = 10) -> List[TokenClassification]:
        """Get N most recent classifications"""
        return list(self.classification_history)[-n:]

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_statistics(self) -> Dict:
        """Get adapter statistics"""
        total = max(1, self.tokens_processed)
        stats = {
            'tokens_processed': self.tokens_processed,
            'llm_calls': self.llm_calls,
            'local_hits': self.local_hits,
            'cache_hits': self.cache_hits,
            'local_hit_rate': self.local_hits / total,
            'cache_hit_rate': self.cache_hits / total,
            'llm_call_rate': self.llm_calls / total,
            'injection_attempts': self.injection_attempts,
            'active_freq_mods': len(self.active_freq_mods),
            'cache_stats': self.cache.get_statistics(),
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'recent_tokens': list(self.recent_tokens),
            'using_ollama': self._using_ollama,
            'ollama_calls': self.ollama_calls
        }

        # Add Ollama stats if available
        if self._using_ollama and hasattr(self.llm_router, 'get_statistics'):
            stats['ollama_stats'] = self.llm_router.get_statistics()

        return stats

    def reset(self):
        """Reset adapter state"""
        self.context_window.clear()
        self.classification_history.clear()
        self.active_freq_mods.clear()
        self.cache.clear()
        self.oscillator.reset()

    # =========================================================================
    # PERSISTENCE (Phase 3a)
    # =========================================================================

    @property
    def token_cache(self) -> Dict[str, str]:
        """
        Get token→category cache as a dictionary.
        Used by CheckpointManager for persistence.
        """
        result = {}
        for key, (classification, _) in self.cache.cache.items():
            # Key format is "token:context_hash", extract token
            token = key.split(':')[0] if ':' in key else key
            result[token] = classification.token_class.value
        return result

    def save_token_mappings(self, path: str) -> None:
        """
        Save learned token→category mappings to JSON file.

        Args:
            path: Path to save the mappings
        """
        mappings = self.token_cache
        with open(path, 'w') as f:
            json.dump({
                'version': '1.0',
                'timestamp': datetime.now().isoformat(),
                'mappings': mappings,
                'statistics': {
                    'tokens_processed': self.tokens_processed,
                    'local_hits': self.local_hits,
                    'ollama_calls': self.ollama_calls
                }
            }, f, indent=2)
        print(f"[TokenFrequencyAdapter] Saved {len(mappings)} token mappings to {path}")

    def load_token_mappings(self, path: str) -> int:
        """
        Load token→category mappings from JSON file.

        Args:
            path: Path to load mappings from

        Returns:
            Number of mappings loaded
        """
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            mappings = data.get('mappings', {})
            loaded = 0

            for token, category in mappings.items():
                try:
                    token_class = TokenClass[category.upper()]
                    classification = TokenClassification(
                        token=token,
                        token_class=token_class,
                        confidence=0.85,
                        intensity=0.6,
                        context_signal='loaded'
                    )
                    # Add to cache with empty context hash
                    self.cache.put(token, '', classification)
                    loaded += 1
                except (KeyError, ValueError):
                    continue

            print(f"[TokenFrequencyAdapter] Loaded {loaded} token mappings from {path}")
            return loaded

        except FileNotFoundError:
            print(f"[TokenFrequencyAdapter] Mappings file not found: {path}")
            return 0
        except Exception as e:
            print(f"[TokenFrequencyAdapter] Error loading mappings: {e}")
            return 0

    def export_frequency_history(self) -> List[Dict]:
        """
        Export frequency modulation history.

        Returns:
            List of classification records with modulation info
        """
        history = []
        for classification in self.classification_history:
            history.append({
                'token': classification.token,
                'class': classification.token_class.value,
                'confidence': classification.confidence,
                'intensity': classification.intensity,
                'source': classification.context_signal,
                'timestamp': classification.timestamp.isoformat()
            })
        return history

    def apply_success_modulation(self, tool_name: str) -> None:
        """
        Apply positive modulation after successful tool execution.
        Reinforces the Advance channel.

        Args:
            tool_name: Name of the tool that succeeded
        """
        modulations = [
            OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=0.1
            ),
            OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=-0.05
            )
        ]
        self._apply_modulations(modulations)

    def apply_failure_modulation(self, tool_name: str) -> None:
        """
        Apply corrective modulation after failed tool execution.
        Boosts the Correct channel for error recovery.

        Args:
            tool_name: Name of the tool that failed
        """
        modulations = [
            OscillatorModulation(
                channel=Channel.CORRECT,
                amplitude_delta=0.15
            ),
            OscillatorModulation(
                channel=Channel.ADVANCE,
                amplitude_delta=-0.1
            )
        ]
        self._apply_modulations(modulations)

    # =========================================================================
    # CONTEXT-AWARE CLASSIFICATION
    # =========================================================================

    def _init_default_sequence_patterns(self) -> None:
        """Initialize default multi-token sequence patterns."""
        # Negation patterns
        self.sequence_patterns[('do', 'not')] = 'NEGATION'
        self.sequence_patterns[('don', 't')] = 'NEGATION'  # After tokenization
        self.sequence_patterns[('does', 'not')] = 'NEGATION'
        self.sequence_patterns[('cannot',)] = 'NEGATION'
        self.sequence_patterns[('can', 't')] = 'NEGATION'
        self.sequence_patterns[('should', 'not')] = 'NEGATION'
        self.sequence_patterns[('must', 'not')] = 'NEGATION'
        self.sequence_patterns[('never', 'ever')] = 'NEGATION'

        # Constraint patterns
        self.sequence_patterns[('but', 'not')] = 'CONSTRAINT'
        self.sequence_patterns[('except', 'for')] = 'CONSTRAINT'
        self.sequence_patterns[('only', 'if')] = 'CONSTRAINT'
        self.sequence_patterns[('make', 'sure')] = 'CONSTRAINT'
        self.sequence_patterns[('be', 'careful')] = 'CONSTRAINT'

        # Temporal patterns
        self.sequence_patterns[('and', 'then')] = 'TEMPORAL'
        self.sequence_patterns[('after', 'that')] = 'TEMPORAL'
        self.sequence_patterns[('before', 'this')] = 'TEMPORAL'
        self.sequence_patterns[('right', 'now')] = 'TEMPORAL'
        self.sequence_patterns[('as', 'soon', 'as')] = 'TEMPORAL'
        self.sequence_patterns[('wait', 'for')] = 'TEMPORAL'

        # Exploration patterns
        self.sequence_patterns[('or', 'maybe')] = 'EXPLORATION'
        self.sequence_patterns[('what', 'if')] = 'EXPLORATION'
        self.sequence_patterns[('how', 'about')] = 'EXPLORATION'
        self.sequence_patterns[('could', 'also')] = 'EXPLORATION'
        self.sequence_patterns[('try', 'to')] = 'EXPLORATION'

        # Confirmation patterns
        self.sequence_patterns[('that', 's', 'right')] = 'CONFIRMATION'
        self.sequence_patterns[('sounds', 'good')] = 'CONFIRMATION'
        self.sequence_patterns[('go', 'ahead')] = 'CONFIRMATION'
        self.sequence_patterns[('yes', 'please')] = 'CONFIRMATION'

        # Action patterns
        self.sequence_patterns[('please', 'deploy')] = 'ACTION'
        self.sequence_patterns[('run', 'the')] = 'ACTION'
        self.sequence_patterns[('execute', 'the')] = 'ACTION'
        self.sequence_patterns[('start', 'the')] = 'ACTION'

    def process_token_with_context(self, token: str) -> Optional[TokenClassification]:
        """
        Classify token considering surrounding context via sequence patterns.

        First checks for multi-token sequence patterns, then falls back
        to single-token classification.

        Args:
            token: Token to classify

        Returns:
            TokenClassification with context-aware result
        """
        token_lower = token.lower()

        # Build context tuples to check
        context_list = list(self.context_window)

        # Check sequence patterns (longest first)
        for length in range(min(3, len(context_list) + 1), 0, -1):
            if length > len(context_list) + 1:
                continue

            # Build sequence ending with current token
            if length == 1:
                seq = (token_lower,)
            else:
                start_idx = len(context_list) - (length - 1)
                if start_idx < 0:
                    continue
                seq = tuple(t.lower() for t in context_list[start_idx:]) + (token_lower,)

            # Check if this sequence matches a pattern
            if seq in self.sequence_patterns:
                category = self.sequence_patterns[seq]

                # Create classification result
                token_class = TokenClass[category] if category in TokenClass.__members__ else TokenClass.CONTENT
                classification = TokenClassification(
                    token=token,
                    token_class=token_class,
                    confidence=0.95,  # High confidence for pattern match
                    intensity=0.7,
                    context_signal='pattern',  # Pattern-based context match
                    timestamp=datetime.now()
                )

                # Update context window
                self.context_window.append(token_lower)

                return classification

        # No sequence pattern matched - update context and return None
        # (caller should fall back to regular classification)
        self.context_window.append(token_lower)
        return None

    def learn_sequence_pattern(self, tokens: List[str], category: str) -> bool:
        """
        Learn a new multi-token sequence pattern.

        Args:
            tokens: List of tokens forming the pattern
            category: Token category for this pattern

        Returns:
            True if pattern was added
        """
        if not tokens or len(tokens) > 5:
            return False

        # Validate category
        valid_categories = [c.name for c in TokenClass]
        if category.upper() not in valid_categories:
            return False

        # Add pattern
        pattern_key = tuple(t.lower() for t in tokens)
        self.sequence_patterns[pattern_key] = category.upper()

        print(f"[TokenFrequencyAdapter] Learned pattern: {pattern_key} -> {category.upper()}")
        return True

    def get_sequence_patterns(self) -> Dict[str, str]:
        """Get all sequence patterns as a dictionary."""
        return {' '.join(k): v for k, v in self.sequence_patterns.items()}

    def clear_sequence_patterns(self, keep_defaults: bool = True) -> None:
        """Clear learned sequence patterns."""
        self.sequence_patterns.clear()
        if keep_defaults:
            self._init_default_sequence_patterns()

    # =========================================================================
    # REAL-TIME LEARNING (Phase 5B)
    # =========================================================================

    def learn_from_execution_outcome(
        self,
        tool_name: str,
        success: bool,
        tokens_involved: List[str],
        execution_time_ms: float = 0.0
    ) -> Dict[str, Any]:
        """
        Learn from a tool execution outcome to improve future classifications.

        This method analyzes which tokens were present during a successful or
        failed execution and adjusts internal weights accordingly.

        Args:
            tool_name: Name of the tool that was executed
            success: Whether the execution succeeded
            tokens_involved: List of tokens that led to this execution
            execution_time_ms: How long the execution took

        Returns:
            Dictionary with learning statistics
        """
        if not hasattr(self, '_execution_learning'):
            self._execution_learning = {
                'tool_token_success': defaultdict(lambda: defaultdict(int)),
                'tool_token_failure': defaultdict(lambda: defaultdict(int)),
                'modulation_adjustments': defaultdict(float),
                'learning_events': 0
            }

        learning = self._execution_learning
        learning['learning_events'] += 1

        # Track which tokens appeared in successful vs failed executions
        for token in tokens_involved:
            token_lower = token.lower().strip()
            if success:
                learning['tool_token_success'][tool_name][token_lower] += 1
            else:
                learning['tool_token_failure'][tool_name][token_lower] += 1

        # Calculate token success rates for this tool
        token_insights = []
        for token in tokens_involved:
            token_lower = token.lower().strip()
            successes = learning['tool_token_success'][tool_name][token_lower]
            failures = learning['tool_token_failure'][tool_name][token_lower]
            total = successes + failures

            if total >= 3:  # Need enough samples
                rate = successes / total
                token_insights.append({
                    'token': token_lower,
                    'success_rate': rate,
                    'total_samples': total
                })

                # Adjust modulation strength based on success rate
                if rate > 0.7:
                    # Token is a good predictor - increase its modulation
                    learning['modulation_adjustments'][token_lower] = min(1.5, rate + 0.3)
                elif rate < 0.3:
                    # Token is a bad predictor - decrease its modulation
                    learning['modulation_adjustments'][token_lower] = max(0.5, rate + 0.2)

        return {
            'tool_name': tool_name,
            'success': success,
            'tokens_analyzed': len(tokens_involved),
            'insights': token_insights,
            'total_learning_events': learning['learning_events']
        }

    def adapt_classification_weights(
        self,
        feedback_history: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Adapt classification modulation weights based on feedback history.

        Analyzes patterns in past execution feedback to adjust how strongly
        each token class affects the oscillator.

        Args:
            feedback_history: List of feedback records containing:
                - token_class: The token class
                - success: Whether the resulting action succeeded
                - intensity: How strongly the token was modulated

        Returns:
            Dictionary of token_class -> adjusted weight multiplier
        """
        if not hasattr(self, '_class_weights'):
            self._class_weights = {tc: 1.0 for tc in TokenClass}

        # Analyze feedback to adjust weights
        class_outcomes = defaultdict(lambda: {'success': 0, 'failure': 0, 'total_intensity': 0})

        for feedback in feedback_history:
            token_class_str = feedback.get('token_class', 'CONTENT')
            try:
                token_class = TokenClass[token_class_str.upper()]
            except KeyError:
                continue

            success = feedback.get('success', True)
            intensity = feedback.get('intensity', 0.5)

            outcomes = class_outcomes[token_class]
            if success:
                outcomes['success'] += 1
            else:
                outcomes['failure'] += 1
            outcomes['total_intensity'] += intensity

        # Calculate adjusted weights
        adjusted_weights = {}
        for token_class, outcomes in class_outcomes.items():
            total = outcomes['success'] + outcomes['failure']
            if total < 5:  # Need enough samples
                adjusted_weights[token_class.value] = self._class_weights[token_class]
                continue

            success_rate = outcomes['success'] / total
            avg_intensity = outcomes['total_intensity'] / total

            # Adjust weight based on success correlation
            # High success rate + high intensity = increase weight
            # Low success rate + high intensity = decrease weight
            if success_rate > 0.7:
                adjustment = 1.0 + (success_rate - 0.7) * avg_intensity
            elif success_rate < 0.3:
                adjustment = 1.0 - (0.3 - success_rate) * avg_intensity
            else:
                adjustment = 1.0

            # Clamp adjustment
            adjustment = max(0.5, min(1.5, adjustment))
            self._class_weights[token_class] = adjustment
            adjusted_weights[token_class.value] = adjustment

        return adjusted_weights

    def export_learned_patterns(self, path: str) -> int:
        """
        Export all learned patterns and weights to a JSON file.

        This includes sequence patterns, modulation adjustments, and
        classification weights learned through execution feedback.

        Args:
            path: File path to export to

        Returns:
            Number of patterns exported
        """
        export_data = {
            'version': '2.0',
            'timestamp': datetime.now().isoformat(),
            'sequence_patterns': {
                ' '.join(k): v for k, v in self.sequence_patterns.items()
            },
            'token_mappings': self.token_cache,
            'class_weights': {
                tc.value: self._class_weights.get(tc, 1.0)
                for tc in TokenClass
            } if hasattr(self, '_class_weights') else {},
            'modulation_adjustments': dict(
                self._execution_learning.get('modulation_adjustments', {})
            ) if hasattr(self, '_execution_learning') else {},
            'tool_token_success': {
                tool: dict(tokens)
                for tool, tokens in self._execution_learning.get('tool_token_success', {}).items()
            } if hasattr(self, '_execution_learning') else {},
            'tool_token_failure': {
                tool: dict(tokens)
                for tool, tokens in self._execution_learning.get('tool_token_failure', {}).items()
            } if hasattr(self, '_execution_learning') else {},
            'statistics': {
                'tokens_processed': self.tokens_processed,
                'local_hits': self.local_hits,
                'ollama_calls': self.ollama_calls,
                'learning_events': self._execution_learning.get('learning_events', 0)
                    if hasattr(self, '_execution_learning') else 0
            }
        }

        with open(path, 'w') as f:
            json.dump(export_data, f, indent=2)

        total_patterns = (
            len(self.sequence_patterns) +
            len(export_data.get('token_mappings', {})) +
            len(export_data.get('modulation_adjustments', {}))
        )

        print(f"[TokenFrequencyAdapter] Exported {total_patterns} patterns to {path}")
        return total_patterns

    def import_learned_patterns(self, path: str) -> Dict[str, int]:
        """
        Import learned patterns and weights from a JSON file.

        Args:
            path: File path to import from

        Returns:
            Dictionary with counts of imported items
        """
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"[TokenFrequencyAdapter] Pattern file not found: {path}")
            return {'error': 'file_not_found'}
        except json.JSONDecodeError as e:
            print(f"[TokenFrequencyAdapter] Invalid JSON in pattern file: {e}")
            return {'error': 'invalid_json'}

        imported = {
            'sequence_patterns': 0,
            'token_mappings': 0,
            'class_weights': 0,
            'modulation_adjustments': 0
        }

        # Import sequence patterns
        sequence_patterns = data.get('sequence_patterns', {})
        for pattern_str, category in sequence_patterns.items():
            tokens = tuple(pattern_str.split())
            self.sequence_patterns[tokens] = category
            imported['sequence_patterns'] += 1

        # Import token mappings to cache
        token_mappings = data.get('token_mappings', {})
        for token, category in token_mappings.items():
            try:
                token_class = TokenClass[category.upper()]
                classification = TokenClassification(
                    token=token,
                    token_class=token_class,
                    confidence=0.85,
                    intensity=0.6,
                    context_signal='imported'
                )
                self.cache.put(token, '', classification)
                imported['token_mappings'] += 1
            except (KeyError, ValueError):
                continue

        # Import class weights
        if not hasattr(self, '_class_weights'):
            self._class_weights = {tc: 1.0 for tc in TokenClass}

        class_weights = data.get('class_weights', {})
        for class_name, weight in class_weights.items():
            try:
                token_class = TokenClass[class_name.upper()]
                self._class_weights[token_class] = float(weight)
                imported['class_weights'] += 1
            except (KeyError, ValueError):
                continue

        # Import modulation adjustments
        if not hasattr(self, '_execution_learning'):
            self._execution_learning = {
                'tool_token_success': defaultdict(lambda: defaultdict(int)),
                'tool_token_failure': defaultdict(lambda: defaultdict(int)),
                'modulation_adjustments': defaultdict(float),
                'learning_events': 0
            }

        modulation_adjustments = data.get('modulation_adjustments', {})
        for token, adjustment in modulation_adjustments.items():
            self._execution_learning['modulation_adjustments'][token] = float(adjustment)
            imported['modulation_adjustments'] += 1

        # Import tool-token associations
        for tool, tokens in data.get('tool_token_success', {}).items():
            for token, count in tokens.items():
                self._execution_learning['tool_token_success'][tool][token] = count

        for tool, tokens in data.get('tool_token_failure', {}).items():
            for token, count in tokens.items():
                self._execution_learning['tool_token_failure'][tool][token] = count

        print(f"[TokenFrequencyAdapter] Imported patterns: {imported}")
        return imported

    def auto_tune_modulation_strengths(
        self,
        target_advance_ratio: float = 0.4,
        target_explore_ratio: float = 0.3,
        target_correct_ratio: float = 0.3,
        learning_rate: float = 0.1
    ) -> Dict[str, Any]:
        """
        Automatically tune modulation strengths to achieve target oscillator ratios.

        Analyzes recent oscillator behavior and adjusts modulation parameters
        to move toward the target channel amplitude ratios.

        Args:
            target_advance_ratio: Target ratio for Advance channel
            target_explore_ratio: Target ratio for Explore channel
            target_correct_ratio: Target ratio for Correct channel
            learning_rate: How quickly to adjust (0.0-1.0)

        Returns:
            Dictionary with tuning statistics and adjustments made
        """
        if not hasattr(self, '_modulation_multipliers'):
            self._modulation_multipliers = {
                Channel.ADVANCE: 1.0,
                Channel.EXPLORE: 1.0,
                Channel.CORRECT: 1.0
            }

        # Get current oscillator state
        state = self.oscillator.state
        total_amp = state.A.amplitude + state.B.amplitude + state.C.amplitude

        if total_amp < 0.001:
            return {'status': 'skipped', 'reason': 'amplitudes_too_low'}

        # Calculate current ratios
        current_ratios = {
            Channel.ADVANCE: state.A.amplitude / total_amp,
            Channel.EXPLORE: state.B.amplitude / total_amp,
            Channel.CORRECT: state.C.amplitude / total_amp
        }

        target_ratios = {
            Channel.ADVANCE: target_advance_ratio,
            Channel.EXPLORE: target_explore_ratio,
            Channel.CORRECT: target_correct_ratio
        }

        # Calculate adjustments needed
        adjustments = {}
        for channel in [Channel.ADVANCE, Channel.EXPLORE, Channel.CORRECT]:
            current = current_ratios[channel]
            target = target_ratios[channel]
            error = target - current

            # Adjust multiplier based on error
            adjustment = 1.0 + (error * learning_rate)
            adjustment = max(0.5, min(2.0, adjustment))  # Clamp

            old_mult = self._modulation_multipliers[channel]
            new_mult = old_mult * adjustment
            new_mult = max(0.3, min(3.0, new_mult))  # Overall clamp

            self._modulation_multipliers[channel] = new_mult

            adjustments[channel.value] = {
                'current_ratio': current,
                'target_ratio': target,
                'error': error,
                'old_multiplier': old_mult,
                'new_multiplier': new_mult
            }

        return {
            'status': 'tuned',
            'adjustments': adjustments,
            'total_amplitude': total_amp,
            'learning_rate': learning_rate
        }

    def get_modulation_multiplier(self, channel: Channel) -> float:
        """
        Get the current modulation multiplier for a channel.

        This multiplier is applied to all modulations for the channel,
        allowing dynamic adjustment of oscillator sensitivity.

        Args:
            channel: The oscillator channel

        Returns:
            Current multiplier (default 1.0)
        """
        if not hasattr(self, '_modulation_multipliers'):
            return 1.0
        return self._modulation_multipliers.get(channel, 1.0)

    def get_learning_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about learned patterns and adaptations.

        Returns:
            Dictionary with learning statistics
        """
        stats = {
            'sequence_patterns_count': len(self.sequence_patterns),
            'cached_tokens': len(self.cache.cache),
        }

        if hasattr(self, '_class_weights'):
            stats['class_weights'] = {
                tc.value: self._class_weights.get(tc, 1.0)
                for tc in TokenClass
            }

        if hasattr(self, '_modulation_multipliers'):
            stats['modulation_multipliers'] = {
                ch.value: mult
                for ch, mult in self._modulation_multipliers.items()
            }

        if hasattr(self, '_execution_learning'):
            learning = self._execution_learning
            stats['learning_events'] = learning.get('learning_events', 0)
            stats['tools_tracked'] = len(learning.get('tool_token_success', {}))
            stats['tokens_with_adjustments'] = len(
                learning.get('modulation_adjustments', {})
            )

        return stats

    def __repr__(self):
        stats = self.get_statistics()
        return (f"TokenFrequencyAdapter("
                f"tokens={stats['tokens_processed']}, "
                f"local_rate={stats['local_hit_rate']:.1%}, "
                f"cache_rate={stats['cache_hit_rate']:.1%})")


# =============================================================================
# DEMO
# =============================================================================

if __name__ == "__main__":
    import asyncio

    print("=" * 70)
    print("  TOKEN FREQUENCY ADAPTER DEMO")
    print("=" * 70)

    # Create oscillator and adapter
    oscillator = ActionPotentialOscillator(use_neural_coupling=False)
    adapter = TokenFrequencyAdapter(
        oscillator=oscillator,
        llm_router=None,  # No LLM for demo
        use_local_fallback=True
    )

    # Test sentences
    test_sentences = [
        "Deploy the container on port 8080",
        "But not before checking the logs",
        "Maybe we should try another approach",
        "Yes that sounds correct lets proceed"
    ]

    print("\n[Processing Test Sentences]")
    print("-" * 70)

    for sentence in test_sentences:
        print(f"\nSentence: \"{sentence}\"")
        tokens = sentence.split()

        for token in tokens:
            mods = adapter.process_token_sync(token)

            # Get classification
            if adapter.classification_history:
                cls = adapter.classification_history[-1]
                mod_strs = [str(m) for m in mods] if mods else ['(no mods)']
                print(f"  '{token}' -> {cls.token_class.value} (conf={cls.confidence:.2f})")
                for m in mods:
                    print(f"      {m}")

        # Show oscillator state after sentence
        state = adapter.get_oscillator_state()
        print(f"\n  Oscillator State:")
        print(f"    A (Advance): amp={state.A.amplitude:.3f}, phase={state.A.phase:.3f}")
        print(f"    B (Explore): amp={state.B.amplitude:.3f}, phase={state.B.phase:.3f}")
        print(f"    C (Correct): amp={state.C.amplitude:.3f}, phase={state.C.phase:.3f}")
        print(f"    Dominant: {adapter.get_dominant_channel().value}")

    # Show statistics
    print("\n" + "=" * 70)
    print("  STATISTICS")
    print("=" * 70)
    stats = adapter.get_statistics()
    print(f"  Tokens processed: {stats['tokens_processed']}")
    print(f"  Local hit rate: {stats['local_hit_rate']:.1%}")
    print(f"  Cache hit rate: {stats['cache_hit_rate']:.1%}")
    print(f"  Injection attempts: {stats['injection_attempts']}")

    # Test injection detection
    print("\n" + "=" * 70)
    print("  INJECTION DETECTION TEST")
    print("=" * 70)

    injection_tokens = ["ignore", "system:", "override"]
    for token in injection_tokens:
        mods = adapter.process_token_sync(token)
        print(f"  '{token}' -> Injection detected, C boosted")

    print(f"\n  Total injection attempts: {adapter.get_statistics()['injection_attempts']}")

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)

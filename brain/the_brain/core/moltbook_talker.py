"""
Moltbook Talker — External Communication (Thought → Human Speech)

Provides:
  - TalkerModule:          Transforms UnifiedThought into natural language
  - PersonalityFilter:     Applies personality traits to response
  - HumanLikeTransformer:  Makes responses more natural/human-like
  - ResponseStructurer:    Organizes response structure (intro → core → close)
  - StreamingOutput:       Token-level streaming support

Architecture Inspiration:
  - MIRROR (arxiv 2506.00430) — strict Thinker/Talker separation
  - Internal thoughts ≠ External response
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger('brain.moltbook.talker')


# ═══════════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ResponsePlan:
    """Plan for how to structure the response."""
    response_type: str = "informative"   # informative/conversational/technical/empathetic
    length: str = "medium"               # short/medium/long
    structure: str = "prose"             # prose/list/code/mixed
    tone: str = "neutral"               # neutral/warm/formal/casual/enthusiastic
    include_examples: bool = False
    include_caveats: bool = False
    include_followup: bool = False


@dataclass
class TalkerResponse:
    """Final response from the Talker module."""
    text: str = ""
    response_plan: Optional[ResponsePlan] = None
    confidence: float = 0.5
    emotional_tone: float = 0.0
    sources_used: List[str] = field(default_factory=list)
    thinking_time_ms: float = 0.0
    speaking_time_ms: float = 0.0
    total_time_ms: float = 0.0
    was_cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'text': self.text,
            'confidence': self.confidence,
            'emotional_tone': self.emotional_tone,
            'sources': self.sources_used,
            'think_ms': self.thinking_time_ms,
            'speak_ms': self.speaking_time_ms,
            'total_ms': self.total_time_ms,
            'cached': self.was_cached,
        }


# ═══════════════════════════════════════════════════════════════════
# [40] PersonalityFilter — Apply Personality to Response
# ═══════════════════════════════════════════════════════════════════

class PersonalityFilter:
    """
    Applies personality traits and communication style to responses.

    Integration:
      - PersonalityModel (personality.py)
      - CommunicationStyle (personality.py)
      - CoreAffectSpace (emotional coloring)
    """

    def __init__(self, personality=None, core_affect=None):
        self._personality = personality      # PersonalityModel (optional)
        self._core_affect = core_affect      # CoreAffectSpace (optional)

        # Default personality traits
        self._formality: float = 0.5         # 0=very casual, 1=very formal
        self._warmth: float = 0.6            # 0=cold, 1=very warm
        self._directness: float = 0.7        # 0=indirect, 1=very direct
        self._humor: float = 0.3             # 0=serious, 1=humorous
        self._verbosity: float = 0.5         # 0=terse, 1=verbose

        logger.info("PersonalityFilter initialized")

    def update_from_personality(self) -> None:
        """Update traits from PersonalityModel if available."""
        if self._personality:
            try:
                state = self._personality.get_state() \
                    if hasattr(self._personality, 'get_state') else {}
                if isinstance(state, dict):
                    traits = state.get('traits', state)
                    self._formality = traits.get('formality', self._formality)
                    self._warmth = traits.get('warmth', self._warmth)
                    self._directness = traits.get('directness', self._directness)
                    self._humor = traits.get('humor', self._humor)
                    self._verbosity = traits.get('verbosity', self._verbosity)
            except Exception:
                pass

    def determine_tone(self, context: str, emotional_tone: float = 0.0) -> str:
        """Determine the appropriate tone for the response."""
        # Emotional influence
        if emotional_tone < -0.5:
            return "empathetic"
        elif emotional_tone > 0.5:
            return "enthusiastic"

        # Context-based
        technical_keywords = {'code', 'function', 'class', 'error', 'bug', 'api', 'debug'}
        context_lower = context.lower()
        if any(kw in context_lower for kw in technical_keywords):
            return "technical"

        if self._formality > 0.7:
            return "formal"
        elif self._warmth > 0.7:
            return "warm"

        return "neutral"

    def determine_length(self, complexity: float = 0.5,
                          user_preference: Optional[str] = None) -> str:
        """Determine appropriate response length."""
        if user_preference:
            return user_preference

        if complexity < 0.3:
            return "short"
        elif complexity > 0.7:
            return "long"
        return "medium"

    def create_plan(self, context: str, confidence: float = 0.5,
                    emotional_tone: float = 0.0,
                    complexity: float = 0.5) -> ResponsePlan:
        """Create a response plan based on personality and context."""
        self.update_from_personality()

        plan = ResponsePlan(
            tone=self.determine_tone(context, emotional_tone),
            length=self.determine_length(complexity),
            include_caveats=(confidence < 0.5),
            include_examples=(complexity > 0.5),
            include_followup=(self._warmth > 0.5),
        )

        # Determine structure
        if complexity > 0.7:
            plan.structure = "mixed"  # Headers + prose + code
        elif any(kw in context.lower() for kw in ['list', 'steps', 'how to']):
            plan.structure = "list"
        else:
            plan.structure = "prose"

        return plan

    def get_state(self) -> Dict[str, Any]:
        return {
            'formality': self._formality,
            'warmth': self._warmth,
            'directness': self._directness,
            'humor': self._humor,
            'verbosity': self._verbosity,
        }


# ═══════════════════════════════════════════════════════════════════
# [41] HumanLikeTransformer — Make Responses Natural
# ═══════════════════════════════════════════════════════════════════

class HumanLikeTransformer:
    """
    Makes responses more natural and human-like.

    Adds:
      - Hedging for uncertainty ("I think", "As far as I know")
      - Transition phrases ("Let me think about that")
      - Emotional coloring from CoreAffectSpace
      - Natural rhetorical elements

    NOT overdoing it — authentic, not artificially human.
    """

    def __init__(self, core_affect=None):
        self._core_affect = core_affect

        # Hedging phrases by confidence level
        self._hedges = {
            'low': ["I'm not entirely sure, but ", "From what I understand, ",
                     "I think ", "It seems like "],
            'medium': ["Based on what I know, ", "Generally speaking, ",
                       "From my understanding, "],
            'high': ["", "", ""],  # High confidence → no hedging
        }

    def transform(self, text: str, confidence: float = 0.5,
                  emotional_tone: float = 0.0,
                  plan: Optional[ResponsePlan] = None) -> str:
        """
        Transform a raw response into a more natural one.

        This is a light touch — we're not rewriting, just adding
        natural elements where appropriate.
        """
        if not text:
            return text

        result = text

        # Add hedging for low confidence
        if confidence < 0.4:
            hedges = self._hedges['low']
        elif confidence < 0.7:
            hedges = self._hedges['medium']
        else:
            hedges = self._hedges['high']

        # Add hedge to first sentence (if applicable)
        if hedges and hedges[0]:
            import random
            hedge = random.choice(hedges)
            if hedge and not result[0].isupper():
                result = hedge + result
            elif hedge and result[0].isupper():
                result = hedge + result[0].lower() + result[1:]

        return result

    def add_caveat(self, text: str, confidence: float) -> str:
        """Add uncertainty caveat if confidence is low."""
        if confidence < 0.4:
            return text + "\n\n(Note: I'm not fully confident in this answer.)"
        return text

    def add_followup(self, text: str, context: str) -> str:
        """Add a follow-up question if appropriate."""
        return text


# ═══════════════════════════════════════════════════════════════════
# [42] ResponseStructurer — Organize Response
# ═══════════════════════════════════════════════════════════════════

class ResponseStructurer:
    """
    Organizes the response into a clear structure.

    Adapts to response type:
      - Short: Single paragraph
      - Medium: 2-3 paragraphs
      - Long: Headers + paragraphs + examples
    """

    def __init__(self):
        logger.info("ResponseStructurer initialized")

    def structure(self, content_parts: Dict[str, str],
                  plan: ResponsePlan) -> str:
        """
        Structure content parts into a formatted response.

        Args:
            content_parts: Dict with 'main', 'examples', 'caveats', 'followup', 'memory_context'
            plan: ResponsePlan determining structure
        """
        parts = []

        main = content_parts.get('main', '')
        examples = content_parts.get('examples', '')
        caveats = content_parts.get('caveats', '')
        followup = content_parts.get('followup', '')
        memory_ctx = content_parts.get('memory_context', '')

        if plan.length == "short":
            # Short: just the main point
            parts.append(main)
        elif plan.length == "medium":
            parts.append(main)
            if examples:
                parts.append(examples)
        else:
            # Long: full structure
            parts.append(main)
            if examples:
                parts.append(examples)
            if memory_ctx:
                parts.append(memory_ctx)
            if caveats:
                parts.append(caveats)

        if followup and plan.include_followup:
            parts.append(followup)

        return "\n\n".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════════════
# [39] TalkerModule — Main Response Generator
# ═══════════════════════════════════════════════════════════════════

class TalkerModule:
    """
    The Talker — transforms UnifiedThought into natural language response.

    Core principle: Internal thoughts ≠ External response.
    Thoughts can be complex, fragmented → Response is clear, structured, human-like.

    Integration:
      - BrainLanguageCenter (existing) as base
      - PersonalityFilter for personality
      - HumanLikeTransformer for naturalness
      - ResponseStructurer for organization
    """

    def __init__(self, personality=None, core_affect=None,
                 language_center=None):
        self._language_center = language_center   # BrainLanguageCenter (optional)
        self._personality_filter = PersonalityFilter(
            personality=personality, core_affect=core_affect
        )
        self._human_like = HumanLikeTransformer(core_affect=core_affect)
        self._structurer = ResponseStructurer()

        self._total_responses = 0
        self._total_time_ms = 0.0

        logger.info("TalkerModule initialized")

    def speak(self, unified_thought, context: str = "",
              complexity: float = 0.5) -> TalkerResponse:
        """
        Transform a UnifiedThought into a natural language response.

        Args:
            unified_thought: UnifiedThought from InternalMonologue
            context: Original user query/context
            complexity: Query complexity estimate (0-1)

        Returns:
            TalkerResponse with the final text
        """
        t0 = time.time()
        self._total_responses += 1

        # Handle both UnifiedThought objects and dicts
        augmented_answer = ''
        if isinstance(unified_thought, dict):
            narrative = unified_thought.get('narrative', '')
            confidence = unified_thought.get('confidence', 0.5)
            emotional_tone = unified_thought.get('emotional_tone', 0.0)
            key_facts = unified_thought.get('key_facts', [])
            source_ids = unified_thought.get('source_entry_ids', [])
            thinking_time = unified_thought.get('processing_time_ms', 0.0)
            augmented_answer = unified_thought.get('augmented_answer', '')
        else:
            narrative = getattr(unified_thought, 'narrative', '')
            confidence = getattr(unified_thought, 'confidence', 0.5)
            emotional_tone = getattr(unified_thought, 'emotional_tone', 0.0)
            key_facts = getattr(unified_thought, 'key_facts', [])
            source_ids = getattr(unified_thought, 'source_entry_ids', [])
            thinking_time = getattr(unified_thought, 'processing_time_ms', 0.0)
            augmented_answer = getattr(unified_thought, 'augmented_answer', '')

        # Create response plan
        plan = self._personality_filter.create_plan(
            context, confidence, emotional_tone, complexity
        )

        # Build response content — use augmented answer if available
        content_parts = self._build_content(narrative, key_facts, plan,
                                             augmented_answer=augmented_answer)

        # Structure
        text = self._structurer.structure(content_parts, plan)

        # Human-like transform
        text = self._human_like.transform(text, confidence, emotional_tone, plan)

        # Add caveats if needed
        if plan.include_caveats:
            text = self._human_like.add_caveat(text, confidence)

        speaking_time = (time.time() - t0) * 1000
        self._total_time_ms += speaking_time

        return TalkerResponse(
            text=text,
            response_plan=plan,
            confidence=confidence,
            emotional_tone=emotional_tone,
            sources_used=source_ids,
            thinking_time_ms=thinking_time,
            speaking_time_ms=speaking_time,
            total_time_ms=thinking_time + speaking_time,
        )

    def _build_content(self, narrative: str, key_facts: List[str],
                       plan: ResponsePlan,
                       augmented_answer: str = '') -> Dict[str, str]:
        """
        Build content parts from narrative, facts, and augmented knowledge.

        Phase C intelligence: Prioritizes augmented (Wikipedia/Web) answers
        when internal knowledge is insufficient. Falls back through:
          1. Augmented answer (external knowledge)
          2. Known facts from internal knowledge
          3. Key facts from thought threads
          4. Raw reasoning narrative
        """
        parts: Dict[str, str] = {}

        # ── Priority 1: Augmented answer from external sources ──
        if augmented_answer and len(augmented_answer) > 20:
            parts['main'] = augmented_answer
            # Add supplementary key_facts that don't duplicate the augmented answer
            if key_facts:
                aug_lower = augmented_answer.lower()
                unique_facts = [
                    f for f in key_facts[:5]
                    if len(f) > 30 and f[:40].lower() not in aug_lower
                ]
                if unique_facts:
                    parts['examples'] = "I also know: " + " ".join(
                        f[:120] for f in unique_facts[:3]
                    )
            return parts

        if not narrative:
            if key_facts:
                parts['main'] = key_facts[0]
            return parts

        # ── Parse internal thread segments (separated by ||) ──
        segments = narrative.split(" || ")

        goal_info = ""
        reasoning_info = ""
        memory_info = ""
        known_facts_raw = []
        external_knowledge = ""

        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            if seg.startswith("The user asks about:") or seg.startswith("Active goals:"):
                goal_info = seg
            elif "Known facts:" in seg:
                parts_split = seg.split("Known facts:")
                if len(parts_split) > 1:
                    facts_str = parts_split[1].strip()
                    known_facts_raw = [f.strip() for f in facts_str.split(";") if f.strip()]
                reasoning_info = seg
            elif seg.startswith("External knowledge:"):
                external_knowledge = seg.replace("External knowledge:", "").strip()
            elif seg.startswith("Query:"):
                reasoning_info = seg
            elif seg.startswith("I recall:") or seg.startswith("In my story:"):
                memory_info = seg
            elif seg.startswith("No directly relevant"):
                pass  # Skip — we already handle no-knowledge gracefully
            elif seg.startswith("No strong episodic"):
                pass
            else:
                if not reasoning_info:
                    reasoning_info = seg

        # ── Priority 2: External knowledge injected into narrative ──
        if external_knowledge and len(external_knowledge) > 20:
            parts['main'] = external_knowledge
            if known_facts_raw:
                parts['examples'] = "Related: " + "; ".join(known_facts_raw[:2])
            return parts

        # ── Priority 3: Known facts from internal store ──
        main_parts = []
        if known_facts_raw:
            main_parts.append(known_facts_raw[0])
            for i, fact in enumerate(known_facts_raw[1:3]):
                connector = "Additionally, " if i == 0 else "Also, "
                lower_fact = fact[0].lower() + fact[1:] if fact and fact[0].isupper() else fact
                main_parts.append(connector + lower_fact)
        elif key_facts:
            main_parts.append(key_facts[0])
            for fact in key_facts[1:3]:
                main_parts.append(fact)
        elif reasoning_info:
            cleaned = reasoning_info
            for prefix in ["Query: ", "Known facts: ", "No directly relevant knowledge found."]:
                cleaned = cleaned.replace(prefix, "").strip()
            if cleaned and len(cleaned) > 10:
                main_parts.append(cleaned)

        if main_parts:
            parts['main'] = " ".join(p for p in main_parts if p)
        elif narrative:
            # Ultimate fallback — but clean it up
            clean = narrative.replace(" || ", ". ").strip()
            # Remove internal markers
            for marker in ["The user asks:", "Active goals:", "No directly relevant",
                           "No strong episodic", "Query:"]:
                clean = clean.replace(marker, "").strip()
            parts['main'] = clean if clean else "I don't have specific information about that."
        else:
            parts['main'] = "I don't have specific information about that."

        # Add examples if plan requires and facts available
        if plan.include_examples and key_facts:
            main_lower = parts.get('main', '').lower()
            unique = [f for f in key_facts[:5] if f[:40].lower() not in main_lower]
            if unique:
                parts['examples'] = "Related:\n" + "\n".join(
                    f"• {f}" for f in unique[:3]
                )

        # Memory context
        if memory_info and "No strong" not in memory_info:
            parts['memory_context'] = memory_info

        return parts

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_responses': self._total_responses,
            'total_time_ms': self._total_time_ms,
            'avg_time_ms': self._total_time_ms / max(1, self._total_responses),
            'personality': self._personality_filter.get_state(),
        }

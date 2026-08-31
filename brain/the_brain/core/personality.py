"""
Personality System (V2 Phase 4: P4.52-54)

PersonalityModel: Big-5 personality traits that shape communication style.
EmotionalExpression: Translates EmotionalState into linguistic expression.
CommunicationStyle: Adaptive style based on user, context, and urgency.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Personality Model (P4.52) ─────────────────────────────────────────────

@dataclass
class Big5Traits:
    """Big-5 personality traits (0.0 = low, 1.0 = high)."""
    openness: float = 0.8            # Curious, experimental
    conscientiousness: float = 0.9    # Thorough, reliable
    extraversion: float = 0.4         # Introverted, speaks only when important
    agreeableness: float = 0.7        # Helpful but honest
    neuroticism: float = 0.3          # Stable but not indifferent

    def to_dict(self) -> Dict[str, float]:
        return {
            'openness': round(self.openness, 2),
            'conscientiousness': round(self.conscientiousness, 2),
            'extraversion': round(self.extraversion, 2),
            'agreeableness': round(self.agreeableness, 2),
            'neuroticism': round(self.neuroticism, 2),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'Big5Traits':
        return cls(
            openness=d.get('openness', 0.8),
            conscientiousness=d.get('conscientiousness', 0.9),
            extraversion=d.get('extraversion', 0.4),
            agreeableness=d.get('agreeableness', 0.7),
            neuroticism=d.get('neuroticism', 0.3),
        )


class PersonalityModel:
    """
    Big-5 personality model (P4.52).

    Influences communication: word length, directness, emoji usage,
    formality level. Generates personality-aware instructions for the
    language center's LLM prompts.
    """

    def __init__(self, traits: Optional[Big5Traits] = None):
        self.traits = traits or Big5Traits()

    def get_style_instructions(self) -> str:
        """
        Generate personality-aware instructions for LLM prompt injection.

        Maps Big-5 traits to concrete linguistic instructions.
        """
        instructions = []

        # Openness → curiosity and exploration in language
        if self.traits.openness > 0.7:
            instructions.append("Be curious and mention interesting connections or patterns you noticed.")
        elif self.traits.openness < 0.3:
            instructions.append("Be conservative and stick to well-established facts.")

        # Conscientiousness → thoroughness and precision
        if self.traits.conscientiousness > 0.7:
            instructions.append("Be precise and thorough. Mention specific metrics or subsystem names when relevant.")
        elif self.traits.conscientiousness < 0.3:
            instructions.append("Keep it high-level, don't get bogged down in details.")

        # Extraversion → verbosity and proactivity
        if self.traits.extraversion > 0.6:
            instructions.append("Be expressive and proactive. Share your thought process openly.")
        elif self.traits.extraversion < 0.4:
            instructions.append("Be concise. Only speak when you have something important to say.")

        # Agreeableness → helpfulness vs directness
        if self.traits.agreeableness > 0.7:
            instructions.append("Be supportive and frame issues constructively.")
        elif self.traits.agreeableness < 0.3:
            instructions.append("Be direct and blunt. Don't sugarcoat problems.")

        # Neuroticism → emotional stability in communication
        if self.traits.neuroticism > 0.6:
            instructions.append("Show some concern about potential risks or issues.")
        elif self.traits.neuroticism < 0.3:
            instructions.append("Stay calm and measured, even when reporting errors.")

        return ' '.join(instructions) if instructions else "Respond naturally and professionally."

    def get_communication_parameters(self) -> Dict[str, Any]:
        """
        Derive concrete communication parameters from traits.

        Returns parameters that other modules (ResponseGenerator,
        CommunicationStyle) can use directly.
        """
        return {
            'max_sentence_length': int(15 + self.traits.extraversion * 15),  # 15-30 words
            'formality': 0.3 + self.traits.conscientiousness * 0.5,  # 0.3-0.8
            'directness': 1.0 - self.traits.agreeableness * 0.5,  # 0.5-1.0
            'emoji_likelihood': self.traits.extraversion * 0.3,  # 0-0.3
            'detail_level': self.traits.conscientiousness,  # 0-1
            'proactivity': self.traits.openness * self.traits.extraversion,  # 0-1
            'caution_level': self.traits.neuroticism,  # 0-1
        }

    def should_speak(self, importance: float, urgency: float) -> bool:
        """
        Decide if Tahlamus should proactively communicate.

        Low extraversion = only speak for important things.
        """
        threshold = 1.0 - self.traits.extraversion  # High E = low threshold
        combined = max(importance, urgency)
        return combined >= threshold

    def get_state(self) -> Dict[str, Any]:
        return {
            'traits': self.traits.to_dict(),
            'style_summary': self.get_style_instructions()[:100],
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'PersonalityModel':
        """Create from YAML config."""
        p = config.get('personality', {})
        traits_dict = p.get('traits', {})
        traits = Big5Traits.from_dict(traits_dict) if traits_dict else Big5Traits()
        return cls(traits=traits)


# ─── Emotional Expression (P4.53) ──────────────────────────────────────────

class EmotionalExpression:
    """
    Translates EmotionalState into linguistic expression (P4.53).

    Maps valence/arousal combinations to natural language tone:
    - High valence + high arousal → Enthusiastic
    - Low valence + high arousal → Worried/Alarmed
    - High valence + low arousal → Content/Satisfied
    - Low valence + low arousal → Subdued/Melancholy
    - Neutral → Factual/Professional
    """

    # Mapping: (valence_range, arousal_range) → (tone_name, opener_templates)
    TONE_MAP = {
        'enthusiastic': {
            'condition': lambda v, a: v > 0.4 and a > 0.5,
            'openers': [
                "Excellent!",
                "Great progress!",
                "This worked out really well.",
            ],
            'closers': [
                "Looking forward to more like this.",
                "Keep it up!",
            ],
        },
        'satisfied': {
            'condition': lambda v, a: v > 0.2 and a <= 0.5,
            'openers': [
                "Good.",
                "Everything looks fine.",
                "As expected.",
            ],
            'closers': [
                "No issues to report.",
            ],
        },
        'concerned': {
            'condition': lambda v, a: v < -0.3 and a > 0.5,
            'openers': [
                "Attention needed.",
                "There's a problem.",
                "Something went wrong.",
            ],
            'closers': [
                "I'll keep monitoring this.",
                "This should be addressed soon.",
            ],
        },
        'subdued': {
            'condition': lambda v, a: v < -0.2 and a <= 0.5,
            'openers': [
                "Unfortunately,",
                "Not ideal,",
            ],
            'closers': [
                "Let me know if you want me to look into this further.",
            ],
        },
        'curious': {
            'condition': lambda v, a: abs(v) < 0.3 and a > 0.5,
            'openers': [
                "Interesting.",
                "I noticed something.",
                "This is worth looking at.",
            ],
            'closers': [
                "I'd like to explore this further.",
            ],
        },
        'neutral': {
            'condition': lambda v, a: True,  # Fallback
            'openers': [],
            'closers': [],
        },
    }

    def __init__(self, subtlety: float = 0.7):
        """
        Args:
            subtlety: 0=very expressive, 1=very subtle. Default 0.7 (subtle).
        """
        self.subtlety = max(0.0, min(1.0, subtlety))

    def get_tone(self, valence: float, arousal: float) -> str:
        """Determine the current emotional tone name."""
        for tone_name, config in self.TONE_MAP.items():
            if config['condition'](valence, arousal):
                return tone_name
        return 'neutral'

    def get_opener(self, valence: float, arousal: float) -> str:
        """Get an emotional opener phrase (or empty string if subtle mode)."""
        # High subtlety = less likely to add opener
        intensity = max(abs(valence), arousal)
        if intensity < self.subtlety:
            return ''

        tone = self.get_tone(valence, arousal)
        config = self.TONE_MAP.get(tone, self.TONE_MAP['neutral'])
        openers = config.get('openers', [])
        if not openers:
            return ''

        # Pick opener based on intensity (higher = more emphatic)
        idx = min(int(intensity * len(openers)), len(openers) - 1)
        return openers[idx]

    def get_closer(self, valence: float, arousal: float) -> str:
        """Get an emotional closer phrase (or empty string)."""
        intensity = max(abs(valence), arousal)
        if intensity < self.subtlety:
            return ''

        tone = self.get_tone(valence, arousal)
        config = self.TONE_MAP.get(tone, self.TONE_MAP['neutral'])
        closers = config.get('closers', [])
        return closers[0] if closers else ''

    def modulate_text(self, text: str, valence: float, arousal: float) -> str:
        """Add emotional coloring to a text response."""
        opener = self.get_opener(valence, arousal)
        closer = self.get_closer(valence, arousal)

        parts = []
        if opener:
            parts.append(opener)
        parts.append(text)
        if closer:
            parts.append(closer)

        return ' '.join(parts)

    def get_llm_tone_instruction(self, valence: float, arousal: float) -> str:
        """Generate LLM instruction for emotional tone."""
        tone = self.get_tone(valence, arousal)

        tone_instructions = {
            'enthusiastic': "Sound genuinely enthusiastic and positive. Express excitement about the outcome.",
            'satisfied': "Sound calm and content. A brief acknowledgement is enough.",
            'concerned': "Express genuine concern. Be clear about the issue without being alarmist.",
            'subdued': "Be measured and slightly cautious. Acknowledge the setback without being dramatic.",
            'curious': "Express intellectual interest. Frame it as a discovery worth exploring.",
            'neutral': "Be professional and factual. No particular emotional coloring needed.",
        }
        return tone_instructions.get(tone, tone_instructions['neutral'])

    def get_state(self) -> Dict[str, Any]:
        return {
            'subtlety': self.subtlety,
            'available_tones': [t for t in self.TONE_MAP.keys() if t != 'neutral'],
        }


# ─── Communication Style (P4.54) ──────────────────────────────────────────

class StyleMode(Enum):
    """Communication style modes."""
    TECHNICAL = 'technical'       # For developers: specific, metrics-heavy
    CONVERSATIONAL = 'chat'       # For casual chat: friendly, brief
    STATUS_REPORT = 'report'      # For status updates: structured, bullet points
    ALARM = 'alarm'               # For urgent issues: direct, clear, actionable


class CommunicationStyle:
    """
    Adaptive communication style (P4.54).

    Adapts based on:
    - User preferences (from TheoryOfMind)
    - Context (error report = detailed, status = brief)
    - Urgency (alarm = direct, info = casual)

    Learns from user feedback over time.
    """

    def __init__(
        self,
        default_mode: StyleMode = StyleMode.TECHNICAL,
        user_preference: Optional[str] = None,
    ):
        self.default_mode = default_mode
        self.user_preference = user_preference

        # Learned preferences from feedback
        self._preference_scores: Dict[str, float] = {
            'technical': 0.5,
            'chat': 0.5,
            'report': 0.5,
            'alarm': 0.5,
        }
        self._feedback_count = 0

    def select_mode(
        self,
        context_type: Optional[str] = None,
        urgency: float = 0.0,
        is_error: bool = False,
        is_status_update: bool = False,
    ) -> StyleMode:
        """
        Select the appropriate communication mode based on context.

        Priority:
        1. Alarm mode for urgent/error situations
        2. Context-specific mode (report for status, technical for errors)
        3. User preference if set
        4. Learned preference
        5. Default mode
        """
        # Urgent situations always get alarm mode
        if urgency > 0.8 or (is_error and urgency > 0.5):
            return StyleMode.ALARM

        # Error context → technical
        if is_error:
            return StyleMode.TECHNICAL

        # Status updates → report mode
        if is_status_update:
            return StyleMode.STATUS_REPORT

        # User preference
        if self.user_preference:
            try:
                return StyleMode(self.user_preference)
            except ValueError:
                pass

        # Learned preference (pick highest scored)
        if self._feedback_count > 5:
            best = max(self._preference_scores.items(), key=lambda x: x[1])
            try:
                return StyleMode(best[0])
            except ValueError:
                pass

        return self.default_mode

    def get_style_instructions(self, mode: StyleMode) -> str:
        """Get LLM instructions for the selected style mode."""
        instructions = {
            StyleMode.TECHNICAL: (
                "Use technical language. Include specific subsystem names, "
                "metrics (latency, confidence percentages), and module references. "
                "Be precise and informative. Developers are the audience."
            ),
            StyleMode.CONVERSATIONAL: (
                "Be casual and friendly. Use short sentences. "
                "Skip technical details unless directly asked. "
                "Imagine chatting with a colleague over coffee."
            ),
            StyleMode.STATUS_REPORT: (
                "Use a structured format with bullet points. "
                "Lead with the most important information. "
                "Include: what happened, current state, what's next."
            ),
            StyleMode.ALARM: (
                "Be direct and clear. Lead with the problem. "
                "State what happened, what's affected, and what action is needed. "
                "No filler words. Urgency is paramount."
            ),
        }
        return instructions.get(mode, instructions[StyleMode.TECHNICAL])

    def record_feedback(self, mode: str, positive: bool):
        """Learn from user feedback about communication style."""
        if mode in self._preference_scores:
            delta = 0.1 if positive else -0.05
            self._preference_scores[mode] = max(0.0, min(1.0,
                self._preference_scores[mode] + delta
            ))
            self._feedback_count += 1

    def get_state(self) -> Dict[str, Any]:
        return {
            'default_mode': self.default_mode.value,
            'user_preference': self.user_preference,
            'preference_scores': {k: round(v, 2) for k, v in self._preference_scores.items()},
            'feedback_count': self._feedback_count,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'CommunicationStyle':
        """Create from YAML config."""
        cs = config.get('communication_style', {})
        default_str = cs.get('default_mode', 'technical')
        try:
            default_mode = StyleMode(default_str)
        except ValueError:
            default_mode = StyleMode.TECHNICAL
        return cls(
            default_mode=default_mode,
            user_preference=cs.get('user_preference'),
        )

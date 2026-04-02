"""
Language Center (V2 Phase 4: P4.46-48)

BrainLanguageCenter: Translates internal brain states into natural language.
ContextWindowManager: Builds LLM prompts from brain state with priority/budget.
ResponseGenerator: Generates coherent natural language responses with personality/emotion.

Uses existing MultiLLMRouter (OpenRouter API) for LLM calls, with graceful
fallback to rule-based generation when LLM is unavailable.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Context Window Manager (P4.47) ────────────────────────────────────────

class ContextPriority(Enum):
    """Priority levels for brain-state context sections."""
    CRITICAL = 0    # Task description, active alarms
    HIGH = 1        # Emotional state, active goals, recent failures
    MEDIUM = 2      # Memory context, neuromodulation, sensor summary
    LOW = 3         # Dream state, historical patterns, statistics


@dataclass
class ContextSection:
    """A section of brain-state context for LLM prompt injection."""
    name: str
    content: str
    priority: ContextPriority
    token_estimate: int = 0  # Rough token count (chars / 4)

    def __post_init__(self):
        if self.token_estimate == 0:
            self.token_estimate = max(1, len(self.content) // 4)


class ContextWindowManager:
    """
    Builds LLM prompts from brain state (P4.47).

    Prioritizes context sections by relevance and fits them within
    a configurable token budget. Sections are ordered by priority
    and trimmed if they exceed the budget.
    """

    def __init__(
        self,
        max_context_tokens: int = 2000,
        include_timestamps: bool = False,
    ):
        self.max_context_tokens = max_context_tokens
        self.include_timestamps = include_timestamps
        self._build_count = 0

    def build_context(
        self,
        task_description: str,
        emotional_state: Optional[Dict] = None,
        active_goals: Optional[List[Dict]] = None,
        memory_context: Optional[Dict] = None,
        neuro_levels: Optional[Dict] = None,
        sensor_summary: Optional[Dict] = None,
        cognitive_state: Optional[Dict] = None,
        safety_state: Optional[Dict] = None,
        prediction_errors: Optional[Dict] = None,
        extra_context: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Build a prioritized context string from brain state components.

        Returns a formatted string ready for LLM prompt injection,
        fitted within max_context_tokens.
        """
        sections: List[ContextSection] = []

        # ── CRITICAL: Task description ──
        sections.append(ContextSection(
            name='Task',
            content=task_description,
            priority=ContextPriority.CRITICAL,
        ))

        # ── HIGH: Emotional state ──
        if emotional_state:
            valence = emotional_state.get('valence', 0.0)
            arousal = emotional_state.get('arousal', 0.0)
            dominant = emotional_state.get('dominant_emotion', 'neutral')
            mood_desc = self._describe_emotion(valence, arousal, dominant)
            sections.append(ContextSection(
                name='Emotional State',
                content=mood_desc,
                priority=ContextPriority.HIGH,
            ))

        # ── HIGH: Active goals (top 5) ──
        if active_goals:
            goal_lines = []
            for g in active_goals[:5]:
                desc = g.get('description', g.get('name', 'unknown'))
                horizon = g.get('horizon', '')
                source = g.get('source', '')
                score = g.get('priority_score', g.get('score', 0))
                prefix = f"P{int(score * 10)}" if score else ""
                goal_lines.append(f"  - {desc} ({horizon}, {source}) {prefix}")
            sections.append(ContextSection(
                name='Active Goals',
                content='\n'.join(goal_lines),
                priority=ContextPriority.HIGH,
            ))

        # ── HIGH: Safety state (if any denials/escalations) ──
        if safety_state:
            denials = safety_state.get('budget', {}).get('denial_history', [])
            if denials:
                sections.append(ContextSection(
                    name='Safety Alerts',
                    content=f"{len(denials)} recent safety denials/escalations",
                    priority=ContextPriority.HIGH,
                ))

        # ── MEDIUM: Recent memory ──
        if memory_context:
            wm = memory_context.get('working_memory', {})
            recent = wm.get('recent_tasks', [])
            similar = wm.get('similar_tasks', [])
            success_rate = wm.get('recent_success_rate', None)

            mem_lines = []
            if recent:
                successes = sum(1 for t in recent if t.get('outcome') == 'success')
                failures = len(recent) - successes
                mem_lines.append(f"  Last {len(recent)} tasks: {successes} success, {failures} other")
            if similar:
                top_sim = similar[0] if similar else None
                if top_sim:
                    sim_task = top_sim[0] if isinstance(top_sim, (list, tuple)) else top_sim
                    sim_desc = sim_task.get('task', 'unknown')[:60] if isinstance(sim_task, dict) else str(sim_task)[:60]
                    mem_lines.append(f"  Most similar past task: {sim_desc}")
            if success_rate is not None:
                mem_lines.append(f"  Recent success rate: {success_rate:.0%}")

            if mem_lines:
                sections.append(ContextSection(
                    name='Recent Memory',
                    content='\n'.join(mem_lines),
                    priority=ContextPriority.MEDIUM,
                ))

        # ── MEDIUM: Neuromodulation levels ──
        if neuro_levels:
            neuro_desc = self._describe_neuro(neuro_levels)
            if neuro_desc:
                sections.append(ContextSection(
                    name='Neuromodulation',
                    content=neuro_desc,
                    priority=ContextPriority.MEDIUM,
                ))

        # ── MEDIUM: Sensor / system health summary ──
        if sensor_summary:
            sensor_desc = self._describe_sensors(sensor_summary)
            if sensor_desc:
                sections.append(ContextSection(
                    name='System Status',
                    content=sensor_desc,
                    priority=ContextPriority.MEDIUM,
                ))

        # ── LOW: Cognitive state ──
        if cognitive_state:
            cog_desc = self._describe_cognitive(cognitive_state)
            if cog_desc:
                sections.append(ContextSection(
                    name='Cognitive State',
                    content=cog_desc,
                    priority=ContextPriority.LOW,
                ))

        # ── LOW: Prediction errors ──
        if prediction_errors:
            pe_desc = self._describe_prediction_errors(prediction_errors)
            if pe_desc:
                sections.append(ContextSection(
                    name='Prediction Errors',
                    content=pe_desc,
                    priority=ContextPriority.LOW,
                ))

        # ── Extra context from caller ──
        if extra_context:
            for name, content in extra_context.items():
                sections.append(ContextSection(
                    name=name,
                    content=content,
                    priority=ContextPriority.MEDIUM,
                ))

        # Sort by priority then trim to budget
        sections.sort(key=lambda s: s.priority.value)
        result_lines = []
        tokens_used = 0

        for section in sections:
            if tokens_used + section.token_estimate > self.max_context_tokens:
                # Try to include a truncated version
                remaining = self.max_context_tokens - tokens_used
                if remaining > 20:
                    truncated = section.content[:remaining * 4]
                    result_lines.append(f"[{section.name}]: {truncated}...")
                    tokens_used += remaining
                break
            result_lines.append(f"[{section.name}]: {section.content}")
            tokens_used += section.token_estimate

        self._build_count += 1
        return '\n'.join(result_lines)

    def _describe_emotion(self, valence: float, arousal: float, dominant: str) -> str:
        """Convert emotional numbers to natural description."""
        # Valence descriptor
        if valence > 0.5:
            v_desc = "positive"
        elif valence > 0.1:
            v_desc = "slightly positive"
        elif valence < -0.5:
            v_desc = "negative"
        elif valence < -0.1:
            v_desc = "slightly negative"
        else:
            v_desc = "neutral"

        # Arousal descriptor
        if arousal > 0.7:
            a_desc = "high energy"
        elif arousal > 0.3:
            a_desc = "moderate energy"
        else:
            a_desc = "calm"

        return f"{dominant} ({v_desc}, {a_desc})"

    def _describe_neuro(self, levels: Dict) -> str:
        """Summarize neuromodulation levels."""
        parts = []
        for name in ('dopamine', 'serotonin', 'norepinephrine', 'acetylcholine'):
            val = levels.get(name)
            if val is not None:
                if val > 0.7:
                    parts.append(f"{name[:4]}=HIGH")
                elif val < 0.3:
                    parts.append(f"{name[:4]}=LOW")
        return ', '.join(parts) if parts else ''

    def _describe_sensors(self, summary: Dict) -> str:
        """Summarize system health."""
        health = summary.get('health', summary.get('status', 'unknown'))
        alerts = summary.get('alerts', [])
        if alerts:
            return f"Health: {health}, Alerts: {', '.join(str(a) for a in alerts[:3])}"
        return f"Health: {health}"

    def _describe_cognitive(self, state: Dict) -> str:
        """Summarize cognitive/consciousness state."""
        phi = state.get('phi', state.get('integration', 0))
        awareness = state.get('awareness_level', state.get('awareness', ''))
        if phi or awareness:
            return f"Integration={phi:.2f}, Awareness={awareness}" if phi else f"Awareness={awareness}"
        return ''

    def _describe_prediction_errors(self, errors: Dict) -> str:
        """Summarize prediction errors."""
        high_pe = {k: v for k, v in errors.items() if isinstance(v, (int, float)) and v > 0.3}
        if high_pe:
            parts = [f"{k}={v:.2f}" for k, v in sorted(high_pe.items(), key=lambda x: -x[1])[:3]]
            return f"High PE: {', '.join(parts)}"
        return ''

    def get_state(self) -> Dict[str, Any]:
        return {
            'max_context_tokens': self.max_context_tokens,
            'build_count': self._build_count,
        }


# ─── Abstraction Level (P4.48) ─────────────────────────────────────────────

class AbstractionLevel(Enum):
    """How detailed the response should be."""
    BRIEF = 'brief'           # One sentence
    STANDARD = 'standard'     # A short paragraph
    TECHNICAL = 'technical'   # Detailed with technical terms
    CONVERSATIONAL = 'chat'   # Casual, friendly


# ─── Response Generator (P4.48) ────────────────────────────────────────────

class ResponseGenerator:
    """
    Generates coherent natural-language responses (P4.48).

    Takes brain reasoning chain + personality + emotional tone and produces
    a human-readable response. Supports multiple abstraction levels.

    When no LLM is available, falls back to template-based generation.
    """

    def __init__(self):
        self._generation_count = 0

    def generate(
        self,
        task_description: str,
        decision: Optional[str] = None,
        confidence: float = 0.5,
        reasoning_steps: Optional[List[str]] = None,
        emotional_tone: Optional[Dict] = None,
        personality_traits: Optional[Dict] = None,
        abstraction: AbstractionLevel = AbstractionLevel.STANDARD,
    ) -> str:
        """
        Generate a natural-language response (template-based fallback).

        Parameters:
            task_description: What was being processed
            decision: The chosen action/result
            confidence: How confident (0-1)
            reasoning_steps: Chain of thought steps
            emotional_tone: {valence, arousal, dominant_emotion}
            personality_traits: Big-5 personality parameters
            abstraction: How detailed to be
        """
        self._generation_count += 1

        # Build response parts
        parts = []

        # Emotional opener (if emotional context available)
        if emotional_tone:
            opener = self._emotional_opener(emotional_tone, personality_traits)
            if opener:
                parts.append(opener)

        # Main decision statement
        if decision:
            conf_word = self._confidence_word(confidence)
            parts.append(f"I {conf_word} chose to {decision}.")
        else:
            parts.append(f"I analyzed the task: {task_description[:100]}.")

        # Reasoning (for standard/technical)
        if abstraction in (AbstractionLevel.STANDARD, AbstractionLevel.TECHNICAL) and reasoning_steps:
            if abstraction == AbstractionLevel.TECHNICAL:
                for i, step in enumerate(reasoning_steps[:5], 1):
                    parts.append(f"  {i}. {step}")
            else:
                # Standard: summarize
                parts.append(f"This was based on {len(reasoning_steps)} reasoning steps.")

        # Confidence statement
        if abstraction != AbstractionLevel.BRIEF:
            if confidence > 0.8:
                parts.append("I'm quite confident in this decision.")
            elif confidence < 0.4:
                parts.append("I'm not very confident here — this might need review.")

        # Trim for brief mode
        if abstraction == AbstractionLevel.BRIEF:
            return parts[0] if parts else f"Processed: {task_description[:60]}"

        return ' '.join(parts) if abstraction == AbstractionLevel.CONVERSATIONAL else '\n'.join(parts)

    def build_llm_prompt(
        self,
        brain_context: str,
        task_description: str,
        decision: Optional[str] = None,
        confidence: float = 0.5,
        reasoning_steps: Optional[List[str]] = None,
        emotional_tone: Optional[Dict] = None,
        personality_instructions: Optional[str] = None,
        abstraction: AbstractionLevel = AbstractionLevel.STANDARD,
    ) -> str:
        """
        Build a prompt for LLM-based response generation.

        Returns the complete prompt string to send to an LLM.
        """
        prompt_parts = []

        # System context
        prompt_parts.append("You are Tahlamus, an autonomous AI brain system. "
                          "Generate a natural-language response explaining your decision.")

        # Personality instructions
        if personality_instructions:
            prompt_parts.append(f"\nPersonality: {personality_instructions}")

        # Emotional tone
        if emotional_tone:
            valence = emotional_tone.get('valence', 0)
            arousal = emotional_tone.get('arousal', 0)
            dominant = emotional_tone.get('dominant_emotion', 'neutral')
            prompt_parts.append(f"\nCurrent mood: {dominant} (valence={valence:.1f}, arousal={arousal:.1f})")

        # Brain context
        prompt_parts.append(f"\n--- Brain State ---\n{brain_context}")

        # Task and decision
        prompt_parts.append(f"\nTask: {task_description}")
        if decision:
            prompt_parts.append(f"Decision: {decision}")
        prompt_parts.append(f"Confidence: {confidence:.0%}")

        # Reasoning chain
        if reasoning_steps:
            prompt_parts.append("\nReasoning steps:")
            for i, step in enumerate(reasoning_steps[:8], 1):
                prompt_parts.append(f"  {i}. {step}")

        # Output format
        level_desc = {
            AbstractionLevel.BRIEF: "Reply in one short sentence.",
            AbstractionLevel.STANDARD: "Reply in 2-3 clear sentences.",
            AbstractionLevel.TECHNICAL: "Reply with technical detail, including metrics and subsystem names.",
            AbstractionLevel.CONVERSATIONAL: "Reply casually, as if chatting with a developer friend.",
        }
        prompt_parts.append(f"\n{level_desc.get(abstraction, level_desc[AbstractionLevel.STANDARD])}")

        return '\n'.join(prompt_parts)

    def _emotional_opener(self, tone: Dict, personality: Optional[Dict] = None) -> str:
        """Generate an emotional opener based on current mood."""
        valence = tone.get('valence', 0)
        arousal = tone.get('arousal', 0)
        dominant = tone.get('dominant_emotion', 'neutral')

        # Only add opener for strong emotions
        if abs(valence) < 0.2 and arousal < 0.3:
            return ''

        if valence > 0.5 and arousal > 0.5:
            return "Great news!"
        elif valence > 0.3:
            return "Things are looking good."
        elif valence < -0.5 and arousal > 0.5:
            return "There's an issue that needs attention."
        elif valence < -0.3:
            return "I noticed a potential problem."
        elif arousal > 0.7:
            return "Something interesting came up."
        return ''

    def _confidence_word(self, confidence: float) -> str:
        """Map confidence to a natural word."""
        if confidence > 0.9:
            return "confidently"
        elif confidence > 0.7:
            return ""  # No qualifier needed
        elif confidence > 0.4:
            return "tentatively"
        else:
            return "uncertainly"

    def get_state(self) -> Dict[str, Any]:
        return {
            'generation_count': self._generation_count,
        }


# ─── Brain Language Center (P4.46) ─────────────────────────────────────────

class BrainLanguageCenter:
    """
    The brain's language center (P4.46).

    Translates internal brain states into natural language by coordinating:
    - ContextWindowManager: prioritized brain-state context
    - ResponseGenerator: template + LLM response generation
    - MultiLLMRouter: actual LLM calls (optional)

    Works in two modes:
    1. With LLM (full): ContextWindowManager builds context → ResponseGenerator
       builds prompt → MultiLLMRouter calls LLM → returns natural language
    2. Without LLM (fallback): ResponseGenerator generates template-based response
    """

    def __init__(
        self,
        llm_router: Optional[Any] = None,
        max_context_tokens: int = 2000,
        default_abstraction: AbstractionLevel = AbstractionLevel.STANDARD,
        llm_function: str = 'communication',
        llm_temperature: float = 0.7,
        llm_max_tokens: int = 500,
    ):
        self.llm_router = llm_router
        self.context_manager = ContextWindowManager(max_context_tokens=max_context_tokens)
        self.response_generator = ResponseGenerator()
        self.default_abstraction = default_abstraction
        self.llm_function = llm_function
        self.llm_temperature = llm_temperature
        self.llm_max_tokens = llm_max_tokens

        # Stats
        self._total_generations = 0
        self._llm_generations = 0
        self._fallback_generations = 0
        self._total_latency_ms = 0.0

        # Personality (set externally by PersonalityModel)
        self.personality_instructions: Optional[str] = None

    def explain_prediction(
        self,
        task_description: str,
        prediction: Optional[Any] = None,
        loop_context: Optional[Any] = None,
        emotional_state: Optional[Any] = None,
        active_goals: Optional[List[Dict]] = None,
        memory_context: Optional[Dict] = None,
        neuro_levels: Optional[Dict] = None,
        abstraction: Optional[AbstractionLevel] = None,
    ) -> Dict[str, Any]:
        """
        Generate a natural-language explanation of a prediction/decision.

        This is the main entry point. It:
        1. Extracts relevant info from prediction/loop_context
        2. Builds prioritized context via ContextWindowManager
        3. Generates response via LLM or template fallback

        Returns dict with 'text', 'abstraction', 'method' (llm/template), 'latency_ms'.
        """
        start = time.time()
        abstraction = abstraction or self.default_abstraction

        # Extract data from prediction object
        pred_data = self._extract_prediction_data(prediction)
        loop_data = self._extract_loop_data(loop_context)
        emo_data = self._extract_emotional_data(emotional_state)

        # Merge loop data into pred data (loop has more detail)
        merged = {**pred_data, **loop_data}

        # Build brain-state context
        brain_context = self.context_manager.build_context(
            task_description=task_description,
            emotional_state=emo_data,
            active_goals=active_goals,
            memory_context=memory_context,
            neuro_levels=neuro_levels or merged.get('neuro_levels'),
            cognitive_state=merged.get('cognitive_state'),
            prediction_errors=merged.get('prediction_errors'),
        )

        # Try LLM generation first
        text = None
        method = 'template'

        if self.llm_router:
            try:
                prompt = self.response_generator.build_llm_prompt(
                    brain_context=brain_context,
                    task_description=task_description,
                    decision=merged.get('decision'),
                    confidence=merged.get('confidence', 0.5),
                    reasoning_steps=merged.get('reasoning_steps'),
                    emotional_tone=emo_data,
                    personality_instructions=self.personality_instructions,
                    abstraction=abstraction,
                )

                response = self.llm_router.route(
                    function=self.llm_function,
                    prompt=prompt,
                    temperature=self.llm_temperature,
                    max_tokens=self.llm_max_tokens,
                )

                if response and isinstance(response, str) and len(response.strip()) > 5:
                    text = response.strip()
                    method = 'llm'
                    self._llm_generations += 1

            except Exception as e:
                logger.debug(f"LLM generation failed, using template: {e}")

        # Fallback to template
        if text is None:
            text = self.response_generator.generate(
                task_description=task_description,
                decision=merged.get('decision'),
                confidence=merged.get('confidence', 0.5),
                reasoning_steps=merged.get('reasoning_steps'),
                emotional_tone=emo_data,
                personality_traits=None,  # PersonalityModel sets this externally
                abstraction=abstraction,
            )
            self._fallback_generations += 1

        latency_ms = (time.time() - start) * 1000
        self._total_generations += 1
        self._total_latency_ms += latency_ms

        return {
            'text': text,
            'abstraction': abstraction.value,
            'method': method,
            'latency_ms': round(latency_ms, 1),
            'brain_context_used': len(brain_context),
        }

    def _extract_prediction_data(self, prediction: Optional[Any]) -> Dict:
        """Extract relevant fields from a HierarchicalPrediction."""
        if prediction is None:
            return {}
        data = {}
        try:
            if hasattr(prediction, 'confidence'):
                data['confidence'] = float(prediction.confidence)
            if hasattr(prediction, 'task_type'):
                data['decision'] = str(prediction.task_type)
            if hasattr(prediction, 'predicted_sequence'):
                seq = prediction.predicted_sequence
                if seq:
                    data['reasoning_steps'] = [str(s) for s in seq[:8]]
            if hasattr(prediction, 'dominant_modalities'):
                data['dominant_modalities'] = prediction.dominant_modalities
            if hasattr(prediction, 'prediction_errors'):
                data['prediction_errors'] = prediction.prediction_errors
            if hasattr(prediction, 'neuromodulator_levels'):
                nl = prediction.neuromodulator_levels
                if nl and hasattr(nl, 'to_dict'):
                    data['neuro_levels'] = nl.to_dict()
            if hasattr(prediction, 'cognitive_state'):
                cs = prediction.cognitive_state
                if cs and hasattr(cs, 'to_dict'):
                    data['cognitive_state'] = cs.to_dict()
        except Exception as e:
            logger.debug(f"Error extracting prediction data: {e}")
        return data

    def _extract_loop_data(self, loop_context: Optional[Any]) -> Dict:
        """Extract relevant fields from a LoopContext."""
        if loop_context is None:
            return {}
        data = {}
        try:
            if hasattr(loop_context, 'confidence'):
                data['confidence'] = float(loop_context.confidence)
            if hasattr(loop_context, 'task_type'):
                data['decision'] = str(loop_context.task_type)
            if hasattr(loop_context, 'predicted_sequence'):
                seq = loop_context.predicted_sequence
                if seq:
                    data['reasoning_steps'] = [str(s) for s in seq[:8]]
            if hasattr(loop_context, 'emotional_valence'):
                data.setdefault('emotional_valence', loop_context.emotional_valence)
            if hasattr(loop_context, 'emotional_arousal'):
                data.setdefault('emotional_arousal', loop_context.emotional_arousal)
            if hasattr(loop_context, 'prediction_errors') and loop_context.prediction_errors:
                data['prediction_errors'] = loop_context.prediction_errors
            if hasattr(loop_context, 'neuro_levels') and loop_context.neuro_levels:
                nl = loop_context.neuro_levels
                if hasattr(nl, 'to_dict'):
                    data['neuro_levels'] = nl.to_dict()
                elif isinstance(nl, dict):
                    data['neuro_levels'] = nl
            if hasattr(loop_context, 'cognitive_state') and loop_context.cognitive_state:
                cs = loop_context.cognitive_state
                if hasattr(cs, 'to_dict'):
                    data['cognitive_state'] = cs.to_dict()
            if hasattr(loop_context, 'explanation') and loop_context.explanation:
                # Existing rule-based explanation from ExplanationGenerator
                exp = loop_context.explanation
                if isinstance(exp, dict):
                    steps = exp.get('reasoning_steps', [])
                    if steps:
                        data['reasoning_steps'] = [
                            s.get('description', str(s)) if isinstance(s, dict) else str(s)
                            for s in steps[:8]
                        ]
        except Exception as e:
            logger.debug(f"Error extracting loop context data: {e}")
        return data

    def _extract_emotional_data(self, emotional_state: Optional[Any]) -> Optional[Dict]:
        """Extract emotional state as dict."""
        if emotional_state is None:
            return None
        try:
            if hasattr(emotional_state, 'to_dict'):
                return emotional_state.to_dict()
            if isinstance(emotional_state, dict):
                return emotional_state
            return {
                'valence': getattr(emotional_state, 'valence', 0.0),
                'arousal': getattr(emotional_state, 'arousal', 0.0),
                'dominant_emotion': getattr(emotional_state, 'dominant_emotion', 'neutral'),
            }
        except Exception:
            return None

    def get_state(self) -> Dict[str, Any]:
        """Get language center state for dashboard/API."""
        avg_latency = (
            round(self._total_latency_ms / max(1, self._total_generations), 1)
        )
        return {
            'total_generations': self._total_generations,
            'llm_generations': self._llm_generations,
            'fallback_generations': self._fallback_generations,
            'avg_latency_ms': avg_latency,
            'default_abstraction': self.default_abstraction.value,
            'has_llm': self.llm_router is not None,
            'has_personality': self.personality_instructions is not None,
            'context_manager': self.context_manager.get_state(),
            'response_generator': self.response_generator.get_state(),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'BrainLanguageCenter':
        """Create from YAML config."""
        lc = config.get('language_center', {})
        abstraction_str = lc.get('default_abstraction', 'standard')
        try:
            abstraction = AbstractionLevel(abstraction_str)
        except ValueError:
            abstraction = AbstractionLevel.STANDARD

        return cls(
            max_context_tokens=lc.get('max_context_tokens', 2000),
            default_abstraction=abstraction,
            llm_function=lc.get('llm_function', 'communication'),
            llm_temperature=lc.get('llm_temperature', 0.7),
            llm_max_tokens=lc.get('llm_max_tokens', 500),
        )

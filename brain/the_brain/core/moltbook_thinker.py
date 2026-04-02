"""
Moltbook Thinker — MIRROR-inspired Internal Reasoning System

Provides:
  - GoalThread:           "What do I want to achieve?" (goal awareness)
  - ReasoningThread:      "What do I know? What do I conclude?" (logic)
  - MemoryThread:         "What have I experienced before?" (episodic recall)
  - InternalMonologue:    Orchestrates 3 threads into unified thought
  - CognitiveController:  Synthesizes threads into UnifiedThought
  - ConfidenceEstimator:  How sure am I about this answer?
  - ThoughtQualityGate:   Safety/coherence check before output

Architecture Inspiration:
  - MIRROR (arxiv 2506.00430) — Thinker/Talker separation
  - First-person internal narration, regenerated each tick
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger('brain.moltbook.thinker')


# ═══════════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ThreadOutput:
    """Output from one thinking thread."""
    thread_name: str = ""
    content: str = ""
    key_points: List[str] = field(default_factory=list)
    confidence: float = 0.5
    source_ids: List[str] = field(default_factory=list)
    emotional_tone: float = 0.0
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'thread': self.thread_name,
            'content': self.content,
            'key_points': self.key_points,
            'confidence': self.confidence,
            'sources': self.source_ids,
            'emotional_tone': self.emotional_tone,
            'time_ms': self.processing_time_ms,
        }


@dataclass
class UnifiedThought:
    """
    Synthesized thought from all three threads.

    This is the main output of the Thinker — a coherent first-person
    narration combining goal awareness, reasoning, and memory.
    """
    narrative: str = ""                  # First-person narration
    goal_summary: str = ""               # What am I trying to do?
    reasoning_summary: str = ""          # What do I conclude?
    memory_summary: str = ""             # What do I remember?
    key_facts: List[str] = field(default_factory=list)
    confidence: float = 0.5
    coherence: float = 0.5
    emotional_tone: float = 0.0
    source_entry_ids: List[str] = field(default_factory=list)
    thread_outputs: List[ThreadOutput] = field(default_factory=list)
    processing_time_ms: float = 0.0
    quality_passed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'narrative': self.narrative,
            'goal_summary': self.goal_summary,
            'reasoning_summary': self.reasoning_summary,
            'memory_summary': self.memory_summary,
            'key_facts': self.key_facts,
            'confidence': self.confidence,
            'coherence': self.coherence,
            'emotional_tone': self.emotional_tone,
            'sources': self.source_entry_ids,
            'threads': [t.to_dict() for t in self.thread_outputs],
            'time_ms': self.processing_time_ms,
            'quality_passed': self.quality_passed,
        }


# ═══════════════════════════════════════════════════════════════════
# [32] GoalThread — Goal Awareness
# ═══════════════════════════════════════════════════════════════════

class GoalThread:
    """
    "What do I want to achieve right now?"

    Reads from:
      - GoalManager.get_active_goals()
      - ExistentialPurpose.get_existential_status()
      - NAcc.effort_reward_tradeoff()

    Produces goal-aware thoughts:
      "I should help the user with X, and Y is important to me."
    """

    def __init__(self, goal_manager=None, existential_purpose=None,
                 nucleus_accumbens=None):
        self._goal_manager = goal_manager
        self._existential_purpose = existential_purpose
        self._nacc = nucleus_accumbens
        logger.info("GoalThread initialized")

    def think(self, context: str, **kwargs) -> ThreadOutput:
        """Generate goal-aware thought for the current context."""
        t0 = time.time()
        output = ThreadOutput(thread_name="goal")

        goals = []
        purpose = ""

        # Get active goals
        if self._goal_manager:
            try:
                state = self._goal_manager.get_state() if hasattr(self._goal_manager, 'get_state') else {}
                active = state.get('active_goals', [])
                if isinstance(active, list):
                    goals = [g.get('description', str(g)) if isinstance(g, dict) else str(g)
                             for g in active[:3]]
            except Exception:
                pass

        # Get existential purpose
        if self._existential_purpose:
            try:
                status = self._existential_purpose.get_existential_status() \
                    if hasattr(self._existential_purpose, 'get_existential_status') else {}
                if isinstance(status, dict):
                    purpose = status.get('current_purpose', '')
            except Exception:
                pass

        # Compose goal thought
        parts = []
        if context:
            parts.append(f"The user asks about: {context[:100]}")
        if goals:
            parts.append(f"Active goals: {'; '.join(goals[:3])}")
        if purpose:
            parts.append(f"My purpose: {purpose[:100]}")

        output.content = " | ".join(parts) if parts else "No specific goal context."
        output.key_points = goals[:3]
        output.confidence = 0.7 if goals else 0.4

        # Effort-reward from NAcc
        if self._nacc:
            try:
                nacc_result = self._nacc.process({
                    'reward_magnitude': output.confidence,
                    'effort_required': 0.5,
                })
                if isinstance(nacc_result, dict):
                    tradeoff = nacc_result.get('effort_reward_tradeoff',
                                                nacc_result.get('approach_tendency', 0.5))
                    output.confidence *= float(tradeoff) if isinstance(tradeoff, (int, float)) else 0.5
            except Exception:
                pass

        output.processing_time_ms = (time.time() - t0) * 1000
        return output


# ═══════════════════════════════════════════════════════════════════
# [33] ReasoningThread — Logical Thinking
# ═══════════════════════════════════════════════════════════════════

class ReasoningThread:
    """
    "What do I know about this? What do I conclude?"

    Reads from:
      - Moltbook relevant entries
      - PrefrontalCortex.hierarchical_control_signal()
      - CTM ensemble for domain-specific reasoning

    Multi-step: Premise → Conclusion → Counter-check.
    """

    def __init__(self, moltbook=None, prefrontal=None):
        self._moltbook = moltbook
        self._prefrontal = prefrontal
        logger.info("ReasoningThread initialized")

    def think(self, context: str, moltbook_entries: Optional[List] = None,
              **kwargs) -> ThreadOutput:
        """Generate reasoning about the current context."""
        t0 = time.time()
        output = ThreadOutput(thread_name="reasoning")

        entries = moltbook_entries or []

        # Extract knowledge from entries
        facts = []
        source_ids = []
        for entry in entries[:5]:
            if hasattr(entry, 'content'):
                facts.append(entry.content[:150])
                source_ids.append(entry.id if hasattr(entry, 'id') else 'unknown')

        output.source_ids = source_ids

        # Build reasoning chain
        parts = []
        if context:
            parts.append(f"Query: {context[:100]}")
        if facts:
            parts.append(f"Known facts: {'; '.join(facts[:3])}")
            # Simple reasoning: if we have relevant facts, confidence is higher
            output.confidence = min(0.9, 0.3 + 0.15 * len(facts))
        else:
            output.confidence = 0.3
            parts.append("No directly relevant knowledge found.")

        output.content = " | ".join(parts)
        output.key_points = facts[:5]

        # Abstraction level from PFC
        if self._prefrontal:
            try:
                pfc_result = self._prefrontal.process({
                    'task_type': 'reasoning',
                    'query': context[:50]
                })
                if isinstance(pfc_result, dict):
                    abstraction = pfc_result.get('abstraction_level', 0.5)
                    if isinstance(abstraction, (int, float)):
                        output.content += f" [abstraction={float(abstraction):.2f}]"
            except Exception:
                pass

        output.processing_time_ms = (time.time() - t0) * 1000
        return output


# ═══════════════════════════════════════════════════════════════════
# [34] MemoryThread — Episodic Recall
# ═══════════════════════════════════════════════════════════════════

class MemoryThread:
    """
    "What have I experienced in similar situations before?"

    Reads from:
      - AutobiographicMemory (life events)
      - EmotionalMemorySystem.get_emotional_bias()
      - IdentityNarrative (self-story)

    Provides experiential context for the current situation.
    """

    def __init__(self, identity_narrative=None, emotional_memory=None,
                 autobiographic_memory=None):
        self._identity_narrative = identity_narrative
        self._emotional_memory = emotional_memory
        self._autobiographic = autobiographic_memory
        logger.info("MemoryThread initialized")

    def think(self, context: str, affect: Optional[Dict] = None,
              **kwargs) -> ThreadOutput:
        """Generate memory-based thought for the current context."""
        t0 = time.time()
        output = ThreadOutput(thread_name="memory")

        memories = []

        # Get autobiographic memories
        if self._autobiographic:
            try:
                if hasattr(self._autobiographic, 'recall'):
                    recalled = self._autobiographic.recall(context[:50])
                    if isinstance(recalled, list):
                        memories.extend(str(m)[:100] for m in recalled[:3])
                elif hasattr(self._autobiographic, 'get_state'):
                    state = self._autobiographic.get_state()
                    if isinstance(state, dict):
                        events = state.get('recent_events', [])
                        memories.extend(str(e)[:100] for e in events[:3])
            except Exception:
                pass

        # Get identity narrative context
        narrative_context = ""
        if self._identity_narrative:
            try:
                if hasattr(self._identity_narrative, 'get_current_narrative'):
                    narrative = self._identity_narrative.get_current_narrative()
                    narrative_context = str(narrative)[:150] if narrative else ""
                elif hasattr(self._identity_narrative, 'get_state'):
                    state = self._identity_narrative.get_state()
                    if isinstance(state, dict):
                        narrative_context = state.get('narrative', '')[:150]
            except Exception:
                pass

        # Emotional bias
        emotional_bias = 0.0
        if self._emotional_memory:
            try:
                if hasattr(self._emotional_memory, 'get_emotional_bias'):
                    bias = self._emotional_memory.get_emotional_bias()
                    if isinstance(bias, (int, float)):
                        emotional_bias = float(bias)
                    elif isinstance(bias, dict):
                        emotional_bias = bias.get('valence_bias', 0.0)
            except Exception:
                pass

        # Compose memory thought
        parts = []
        if memories:
            parts.append(f"I recall: {'; '.join(memories[:3])}")
        if narrative_context:
            parts.append(f"In my story: {narrative_context[:100]}")
        if not parts:
            parts.append("No strong episodic memories for this context.")

        output.content = " | ".join(parts)
        output.key_points = memories[:3]
        output.confidence = min(0.8, 0.2 + 0.2 * len(memories))
        output.emotional_tone = emotional_bias

        output.processing_time_ms = (time.time() - t0) * 1000
        return output


# ═══════════════════════════════════════════════════════════════════
# [36] ConfidenceEstimator
# ═══════════════════════════════════════════════════════════════════

class ConfidenceEstimator:
    """
    Estimates how confident the brain should be in its answer.

    Factors:
      - Moltbook entry confidence scores
      - Reasoning chain coherence
      - Memory match quality
      - Self-awareness calibration
    """

    def __init__(self, self_awareness=None):
        self._self_awareness = self_awareness  # SelfAwarenessModule (optional)

    def estimate(self, thread_outputs: List[ThreadOutput],
                 moltbook_entries: Optional[List] = None) -> float:
        """Estimate confidence for the combined thought."""
        if not thread_outputs:
            return 0.3

        # Average thread confidence
        avg_confidence = sum(t.confidence for t in thread_outputs) / len(thread_outputs)

        # Moltbook entry confidence boost
        entry_confidence = 0.0
        if moltbook_entries:
            entry_confidence = sum(
                e.confidence for e in moltbook_entries if hasattr(e, 'confidence')
            ) / max(1, len(moltbook_entries))

        # Combined (weighted)
        combined = 0.5 * avg_confidence + 0.3 * entry_confidence + 0.2 * 0.5

        # Calibration from self-awareness
        if self._self_awareness:
            try:
                if hasattr(self._self_awareness, 'get_overall_calibration'):
                    cal = self._self_awareness.get_overall_calibration()
                    if isinstance(cal, (int, float)):
                        combined *= float(cal)
            except Exception:
                pass

        return max(0.0, min(1.0, combined))


# ═══════════════════════════════════════════════════════════════════
# [37] ThoughtQualityGate
# ═══════════════════════════════════════════════════════════════════

class ThoughtQualityGate:
    """
    Quality check before thoughts reach the Talker.

    Checks:
      - Coherence: Are the threads consistent?
      - Ethics: Does the thought align with values?
      - Safety: Any safety concerns?
      - Relevance: Is this actually about the user's question?
    """

    def __init__(self, value_system=None, safety_governor=None):
        self._value_system = value_system
        self._safety = safety_governor
        self._total_checked = 0
        self._total_blocked = 0

    def check(self, unified_thought: UnifiedThought) -> bool:
        """
        Check if a unified thought passes quality gate.

        Returns True if passed, False if blocked.
        Also sets unified_thought.quality_passed.
        """
        self._total_checked += 1

        # Check coherence
        if unified_thought.coherence < 0.2:
            unified_thought.quality_passed = False
            self._total_blocked += 1
            return False

        # Check confidence (very low = probably wrong)
        if unified_thought.confidence < 0.1:
            unified_thought.quality_passed = False
            self._total_blocked += 1
            return False

        # Value alignment check
        if self._value_system:
            try:
                if hasattr(self._value_system, 'evaluate_action'):
                    eval_result = self._value_system.evaluate_action(
                        unified_thought.narrative[:100]
                    )
                    if isinstance(eval_result, dict):
                        alignment = eval_result.get('alignment', 1.0)
                        if isinstance(alignment, (int, float)) and float(alignment) < 0.3:
                            unified_thought.quality_passed = False
                            self._total_blocked += 1
                            return False
            except Exception:
                pass

        # Safety check
        if self._safety:
            try:
                if hasattr(self._safety, 'check'):
                    safe = self._safety.check(unified_thought.narrative[:200])
                    if safe is False:
                        unified_thought.quality_passed = False
                        self._total_blocked += 1
                        return False
            except Exception:
                pass

        unified_thought.quality_passed = True
        return True

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_checked': self._total_checked,
            'total_blocked': self._total_blocked,
            'block_rate': self._total_blocked / max(1, self._total_checked),
        }


# ═══════════════════════════════════════════════════════════════════
# [35] CognitiveController — Thought Synthesis
# ═══════════════════════════════════════════════════════════════════

class CognitiveController:
    """
    Synthesizes GoalThread + ReasoningThread + MemoryThread outputs
    into a unified first-person narration.

    Like MIRROR: regenerates COMPLETELY each tick (episodic principle).
    """

    def __init__(self):
        self._total_syntheses = 0
        logger.info("CognitiveController initialized")

    def synthesize(self, thread_outputs: List[ThreadOutput],
                   confidence: float = 0.5) -> UnifiedThought:
        """
        Combine thread outputs into a single UnifiedThought.

        Args:
            thread_outputs: Outputs from GoalThread, ReasoningThread, MemoryThread
            confidence: Overall confidence estimate

        Returns:
            UnifiedThought with synthesized narrative
        """
        self._total_syntheses += 1
        t0 = time.time()

        thought = UnifiedThought(
            confidence=confidence,
            thread_outputs=thread_outputs,
        )

        # Extract summaries from each thread
        for output in thread_outputs:
            if output.thread_name == "goal":
                thought.goal_summary = output.content
            elif output.thread_name == "reasoning":
                thought.reasoning_summary = output.content
                thought.source_entry_ids.extend(output.source_ids)
            elif output.thread_name == "memory":
                thought.memory_summary = output.content
                thought.emotional_tone = output.emotional_tone

        # Collect all key facts
        for output in thread_outputs:
            thought.key_facts.extend(output.key_points)
        # Deduplicate key facts
        seen = set()
        unique_facts = []
        for fact in thought.key_facts:
            if fact not in seen:
                seen.add(fact)
                unique_facts.append(fact)
        thought.key_facts = unique_facts[:10]

        # Compute coherence: how consistent are the threads?
        if len(thread_outputs) >= 2:
            conf_spread = max(t.confidence for t in thread_outputs) - \
                          min(t.confidence for t in thread_outputs)
            thought.coherence = max(0.0, 1.0 - conf_spread)
        else:
            thought.coherence = 0.5

        # Build narrative
        narrative_parts = []
        if thought.goal_summary:
            narrative_parts.append(thought.goal_summary)
        if thought.reasoning_summary:
            narrative_parts.append(thought.reasoning_summary)
        if thought.memory_summary:
            narrative_parts.append(thought.memory_summary)

        thought.narrative = " || ".join(narrative_parts)

        thought.processing_time_ms = (time.time() - t0) * 1000
        return thought

    def get_stats(self) -> Dict[str, Any]:
        return {'total_syntheses': self._total_syntheses}


# ═══════════════════════════════════════════════════════════════════
# [31] InternalMonologue — The Thinker (MIRROR)
# ═══════════════════════════════════════════════════════════════════

class InternalMonologue:
    """
    The brain's internal monologue — "speaking with itself".

    Orchestrates three parallel thinking threads:
      1. GoalThread:      "What do I want?"
      2. ReasoningThread:  "What do I know?"
      3. MemoryThread:     "What have I experienced?"

    Synthesizes via CognitiveController into UnifiedThought,
    then passes through ThoughtQualityGate.

    Inspired by MIRROR (arxiv 2506.00430):
      - Private conversation strand (not shown to user)
      - Regenerated completely each tick
      - First-person perspective
    """

    def __init__(self, goal_manager=None, existential_purpose=None,
                 moltbook=None, prefrontal=None,
                 identity_narrative=None, emotional_memory=None,
                 autobiographic_memory=None, nucleus_accumbens=None,
                 self_awareness=None, value_system=None,
                 safety_governor=None):
        # Threads
        self._goal_thread = GoalThread(
            goal_manager=goal_manager,
            existential_purpose=existential_purpose,
            nucleus_accumbens=nucleus_accumbens,
        )
        self._reasoning_thread = ReasoningThread(
            moltbook=moltbook,
            prefrontal=prefrontal,
        )
        self._memory_thread = MemoryThread(
            identity_narrative=identity_narrative,
            emotional_memory=emotional_memory,
            autobiographic_memory=autobiographic_memory,
        )

        # Synthesis & quality
        self._controller = CognitiveController()
        self._confidence_estimator = ConfidenceEstimator(self_awareness=self_awareness)
        self._quality_gate = ThoughtQualityGate(
            value_system=value_system,
            safety_governor=safety_governor,
        )

        self._total_thoughts = 0
        self._total_passed = 0
        logger.info("InternalMonologue initialized (3-thread MIRROR)")

    def think(self, context: str,
              moltbook_entries: Optional[List] = None,
              affect: Optional[Dict] = None,
              memory_context: Optional[List] = None) -> UnifiedThought:
        """
        Run the full thinking cycle.

        Args:
            context: Current task/query context
            moltbook_entries: Retrieved entries from Moltbook
            affect: Current emotional state dict
            memory_context: Additional episodic memories

        Returns:
            UnifiedThought — the synthesized internal thought
        """
        t0 = time.time()
        self._total_thoughts += 1

        # Run all three threads
        goal_output = self._goal_thread.think(context)
        reasoning_output = self._reasoning_thread.think(
            context, moltbook_entries=moltbook_entries
        )
        memory_output = self._memory_thread.think(
            context, affect=affect
        )

        thread_outputs = [goal_output, reasoning_output, memory_output]

        # Estimate confidence
        confidence = self._confidence_estimator.estimate(
            thread_outputs, moltbook_entries
        )

        # Synthesize
        unified = self._controller.synthesize(thread_outputs, confidence)
        unified.processing_time_ms = (time.time() - t0) * 1000

        # Quality gate
        passed = self._quality_gate.check(unified)
        if passed:
            self._total_passed += 1

        return unified

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_thoughts': self._total_thoughts,
            'total_passed': self._total_passed,
            'pass_rate': self._total_passed / max(1, self._total_thoughts),
            'controller': self._controller.get_stats(),
            'quality_gate': self._quality_gate.get_stats(),
        }

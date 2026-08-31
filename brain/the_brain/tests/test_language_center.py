"""
Tests for Language Center (P4.46-48).

Covers: ContextWindowManager, ResponseGenerator, BrainLanguageCenter.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.language_center import (
    ContextPriority,
    ContextSection,
    ContextWindowManager,
    AbstractionLevel,
    ResponseGenerator,
    BrainLanguageCenter,
)


# ─── ContextSection Tests ─────────────────────────────────────────────────

class TestContextSection:
    def test_auto_token_estimate(self):
        """Token estimate computed from content length."""
        section = ContextSection(name='test', content='hello world', priority=ContextPriority.HIGH)
        assert section.token_estimate > 0
        assert section.token_estimate == max(1, len('hello world') // 4)

    def test_manual_token_estimate(self):
        """Manual token estimate overrides auto."""
        section = ContextSection(name='test', content='x', priority=ContextPriority.LOW, token_estimate=50)
        assert section.token_estimate == 50

    def test_priority_ordering(self):
        """CRITICAL < HIGH < MEDIUM < LOW in value."""
        assert ContextPriority.CRITICAL.value < ContextPriority.HIGH.value
        assert ContextPriority.HIGH.value < ContextPriority.MEDIUM.value
        assert ContextPriority.MEDIUM.value < ContextPriority.LOW.value


# ─── ContextWindowManager Tests ───────────────────────────────────────────

class TestContextWindowManager:
    def test_basic_build(self):
        """Build context with just a task description."""
        mgr = ContextWindowManager(max_context_tokens=500)
        ctx = mgr.build_context(task_description="Run unit tests")
        assert "[Task]: Run unit tests" in ctx
        assert mgr._build_count == 1

    def test_with_emotional_state(self):
        """Emotional state appears in context."""
        mgr = ContextWindowManager()
        ctx = mgr.build_context(
            task_description="test",
            emotional_state={'valence': 0.8, 'arousal': 0.6, 'dominant_emotion': 'curious'},
        )
        assert "Emotional State" in ctx
        assert "curious" in ctx

    def test_with_active_goals(self):
        """Active goals appear in context."""
        mgr = ContextWindowManager()
        goals = [
            {'description': 'Fix build', 'horizon': 'short', 'source': 'user', 'score': 0.9},
            {'description': 'Explore feature', 'horizon': 'medium', 'source': 'curiosity', 'score': 0.5},
        ]
        ctx = mgr.build_context(task_description="test", active_goals=goals)
        assert "Active Goals" in ctx
        assert "Fix build" in ctx

    def test_with_memory_context(self):
        """Memory context appears."""
        mgr = ContextWindowManager()
        mem = {
            'working_memory': {
                'recent_tasks': [
                    {'outcome': 'success'}, {'outcome': 'success'}, {'outcome': 'failure'},
                ],
                'similar_tasks': [
                    ({'task': 'deploy api v2', 'outcome': 'success'}, 0.85),
                ],
            }
        }
        ctx = mgr.build_context(task_description="test", memory_context=mem)
        assert "Recent Memory" in ctx
        assert "deploy api v2" in ctx

    def test_with_neuro_levels(self):
        """Neuromodulation extremes show up."""
        mgr = ContextWindowManager()
        ctx = mgr.build_context(
            task_description="test",
            neuro_levels={'dopamine': 0.1, 'serotonin': 0.9, 'norepinephrine': 0.5},
        )
        assert "Neuromodulation" in ctx
        assert "dopa=LOW" in ctx
        assert "sero=HIGH" in ctx

    def test_budget_truncation(self):
        """Sections beyond token budget are truncated."""
        mgr = ContextWindowManager(max_context_tokens=10)
        ctx = mgr.build_context(
            task_description="a short task",
            emotional_state={'valence': 0.5, 'arousal': 0.5, 'dominant_emotion': 'curious'},
            neuro_levels={'dopamine': 0.1},
        )
        # Should have task but may truncate later sections
        assert "[Task]" in ctx

    def test_priority_ordering_in_output(self):
        """CRITICAL sections appear before LOW sections."""
        mgr = ContextWindowManager(max_context_tokens=5000)
        ctx = mgr.build_context(
            task_description="important task",
            emotional_state={'valence': 0.5, 'arousal': 0.8, 'dominant_emotion': 'curious'},
            cognitive_state={'phi': 0.42, 'awareness': 'high'},
        )
        # Task (CRITICAL) should appear before Cognitive (LOW)
        task_pos = ctx.index("[Task]")
        if "[Cognitive State]" in ctx:
            cog_pos = ctx.index("[Cognitive State]")
            assert task_pos < cog_pos

    def test_safety_alerts(self):
        """Safety denials show up as HIGH priority."""
        mgr = ContextWindowManager()
        ctx = mgr.build_context(
            task_description="test",
            safety_state={'budget': {'denial_history': [{'reason': 'destructive'}]}},
        )
        assert "Safety Alerts" in ctx

    def test_prediction_errors(self):
        """High prediction errors show up."""
        mgr = ContextWindowManager()
        ctx = mgr.build_context(
            task_description="test",
            prediction_errors={'logic': 0.9, 'temporal': 0.1},
        )
        assert "Prediction Errors" in ctx
        assert "logic" in ctx

    def test_extra_context(self):
        """Extra context dict included."""
        mgr = ContextWindowManager()
        ctx = mgr.build_context(
            task_description="test",
            extra_context={'Custom Info': 'some custom data'},
        )
        assert "Custom Info" in ctx
        assert "some custom data" in ctx

    def test_get_state(self):
        """State dict is valid."""
        mgr = ContextWindowManager(max_context_tokens=1000)
        mgr.build_context(task_description="test")
        state = mgr.get_state()
        assert state['max_context_tokens'] == 1000
        assert state['build_count'] == 1

    def test_empty_neuro_no_section(self):
        """Normal neuro levels don't add a section."""
        mgr = ContextWindowManager()
        ctx = mgr.build_context(
            task_description="test",
            neuro_levels={'dopamine': 0.5, 'serotonin': 0.5},
        )
        assert "Neuromodulation" not in ctx

    def test_emotion_descriptions(self):
        """Different valence/arousal combos produce different descriptions."""
        mgr = ContextWindowManager()
        # Positive high energy
        ctx1 = mgr.build_context(task_description="t", emotional_state={'valence': 0.8, 'arousal': 0.9, 'dominant_emotion': 'joy'})
        assert "positive" in ctx1 and "high energy" in ctx1

        # Negative calm
        ctx2 = mgr.build_context(task_description="t", emotional_state={'valence': -0.7, 'arousal': 0.1, 'dominant_emotion': 'sadness'})
        assert "negative" in ctx2 and "calm" in ctx2


# ─── ResponseGenerator Tests ─────────────────────────────────────────────

class TestResponseGenerator:
    def test_basic_generation(self):
        """Generate a basic template response."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="Run unit tests",
            decision="run pytest on core module",
            confidence=0.85,
        )
        assert "run pytest" in text
        assert gen._generation_count == 1

    def test_brief_mode(self):
        """Brief mode returns short response."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="Deploy service",
            decision="deploy",
            confidence=0.9,
            abstraction=AbstractionLevel.BRIEF,
        )
        # Brief should be one part
        assert len(text.split('\n')) == 1

    def test_technical_mode_with_reasoning(self):
        """Technical mode includes numbered reasoning steps."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="Analyze logs",
            decision="investigate error pattern",
            confidence=0.7,
            reasoning_steps=["Detected 5 error spikes", "Correlated with deploy event", "Root cause: config mismatch"],
            abstraction=AbstractionLevel.TECHNICAL,
        )
        assert "1." in text
        assert "error spikes" in text

    def test_emotional_opener_positive(self):
        """Positive valence adds a positive opener."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="test",
            decision="proceed",
            confidence=0.9,
            emotional_tone={'valence': 0.8, 'arousal': 0.8, 'dominant_emotion': 'joy'},
        )
        assert "Great news" in text or "looking good" in text

    def test_emotional_opener_negative(self):
        """Negative valence adds a concern opener."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="test",
            decision="investigate",
            confidence=0.4,
            emotional_tone={'valence': -0.7, 'arousal': 0.8, 'dominant_emotion': 'concern'},
        )
        assert "issue" in text or "problem" in text

    def test_low_confidence_note(self):
        """Low confidence produces a review note."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="test",
            decision="maybe deploy",
            confidence=0.2,
            abstraction=AbstractionLevel.STANDARD,
        )
        assert "not very confident" in text or "review" in text

    def test_build_llm_prompt(self):
        """LLM prompt is well-structured."""
        gen = ResponseGenerator()
        prompt = gen.build_llm_prompt(
            brain_context="[Task]: Deploy service\n[Emotional State]: confident",
            task_description="Deploy the API service",
            decision="deploy to production",
            confidence=0.85,
            reasoning_steps=["All tests passed", "Staging OK"],
            personality_instructions="Be concise and precise.",
            abstraction=AbstractionLevel.STANDARD,
        )
        assert "Tahlamus" in prompt
        assert "Deploy the API" in prompt
        assert "Be concise" in prompt
        assert "85%" in prompt
        assert "2-3 clear sentences" in prompt

    def test_llm_prompt_different_abstractions(self):
        """Different abstraction levels produce different instructions."""
        gen = ResponseGenerator()
        brief = gen.build_llm_prompt("ctx", "task", abstraction=AbstractionLevel.BRIEF)
        tech = gen.build_llm_prompt("ctx", "task", abstraction=AbstractionLevel.TECHNICAL)
        assert "one short sentence" in brief
        assert "technical detail" in tech

    def test_confidence_word_mapping(self):
        """Confidence maps to correct words."""
        gen = ResponseGenerator()
        assert gen._confidence_word(0.95) == "confidently"
        assert gen._confidence_word(0.75) == ""  # No qualifier
        assert gen._confidence_word(0.5) == "tentatively"
        assert gen._confidence_word(0.2) == "uncertainly"

    def test_conversational_joins_with_spaces(self):
        """Conversational mode joins with spaces, not newlines."""
        gen = ResponseGenerator()
        text = gen.generate(
            task_description="Test",
            decision="proceed",
            confidence=0.9,
            abstraction=AbstractionLevel.CONVERSATIONAL,
        )
        assert '\n' not in text

    def test_get_state(self):
        gen = ResponseGenerator()
        gen.generate(task_description="t")
        assert gen.get_state()['generation_count'] == 1


# ─── BrainLanguageCenter Tests ───────────────────────────────────────────

class TestBrainLanguageCenter:
    def test_template_fallback(self):
        """Without LLM, uses template fallback."""
        lc = BrainLanguageCenter()
        result = lc.explain_prediction(
            task_description="Run tests",
            prediction=None,
        )
        assert result['method'] == 'template'
        assert len(result['text']) > 0
        assert result['latency_ms'] >= 0
        assert lc._fallback_generations == 1

    def test_with_prediction_object(self):
        """Extracts data from prediction-like object."""
        class FakePrediction:
            confidence = 0.8
            task_type = 'coding'
            predicted_sequence = ['analyze', 'fix', 'test']
            dominant_modalities = ['tool_trace']
            prediction_errors = {'logic': 0.3}
            neuromodulator_levels = None
            cognitive_state = None

        lc = BrainLanguageCenter()
        result = lc.explain_prediction(
            task_description="Fix build error",
            prediction=FakePrediction(),
        )
        assert result['method'] == 'template'
        assert 'coding' in result['text'] or 'Fix build' in result['text']

    def test_with_loop_context(self):
        """Extracts data from loop context object."""
        class FakeContext:
            confidence = 0.6
            task_type = 'analysis'
            predicted_sequence = ['step1', 'step2']
            emotional_valence = 0.5
            emotional_arousal = 0.3
            prediction_errors = None
            neuro_levels = None
            cognitive_state = None
            explanation = {
                'reasoning_steps': [
                    {'description': 'Analyzed error logs'},
                    {'description': 'Found root cause'},
                ]
            }

        lc = BrainLanguageCenter()
        result = lc.explain_prediction(
            task_description="Analyze system",
            loop_context=FakeContext(),
        )
        assert result['method'] == 'template'
        assert len(result['text']) > 5

    def test_with_emotional_state_dict(self):
        """Handles emotional state as dict."""
        lc = BrainLanguageCenter()
        result = lc.explain_prediction(
            task_description="test",
            emotional_state={'valence': 0.7, 'arousal': 0.8, 'dominant_emotion': 'joy'},
        )
        assert result['text']

    def test_with_emotional_state_object(self):
        """Handles emotional state as object."""
        class FakeEmotion:
            valence = -0.5
            arousal = 0.7
            dominant_emotion = 'concern'
            def to_dict(self):
                return {'valence': self.valence, 'arousal': self.arousal, 'dominant_emotion': self.dominant_emotion}

        lc = BrainLanguageCenter()
        result = lc.explain_prediction(
            task_description="test",
            emotional_state=FakeEmotion(),
        )
        assert result['text']

    def test_personality_instructions(self):
        """Personality instructions are passed to LLM prompt."""
        lc = BrainLanguageCenter()
        lc.personality_instructions = "Be concise and thorough."
        # Template mode won't show personality, but it should not crash
        result = lc.explain_prediction(task_description="test")
        assert result['text']

    def test_abstraction_override(self):
        """Abstraction level can be overridden per call."""
        lc = BrainLanguageCenter(default_abstraction=AbstractionLevel.STANDARD)
        result = lc.explain_prediction(
            task_description="test",
            abstraction=AbstractionLevel.BRIEF,
        )
        assert result['abstraction'] == 'brief'

    def test_with_mock_llm(self):
        """LLM router is called when available."""
        class MockRouter:
            def route(self, function, prompt, temperature, max_tokens):
                return "This is the LLM-generated response."

        lc = BrainLanguageCenter(llm_router=MockRouter())
        result = lc.explain_prediction(task_description="test")
        assert result['method'] == 'llm'
        assert "LLM-generated" in result['text']
        assert lc._llm_generations == 1

    def test_llm_failure_fallback(self):
        """Falls back to template when LLM fails."""
        class FailingRouter:
            def route(self, **kwargs):
                raise Exception("LLM unavailable")

        lc = BrainLanguageCenter(llm_router=FailingRouter())
        result = lc.explain_prediction(task_description="test")
        assert result['method'] == 'template'
        assert lc._fallback_generations == 1

    def test_get_state(self):
        """State dict is comprehensive."""
        lc = BrainLanguageCenter()
        lc.explain_prediction(task_description="test")
        state = lc.get_state()
        assert state['total_generations'] == 1
        assert state['has_llm'] is False
        assert 'context_manager' in state
        assert 'response_generator' in state

    def test_from_yaml(self):
        """Creates from YAML config."""
        config = {
            'language_center': {
                'max_context_tokens': 1500,
                'default_abstraction': 'technical',
                'llm_function': 'test_func',
                'llm_temperature': 0.5,
                'llm_max_tokens': 300,
            }
        }
        lc = BrainLanguageCenter.from_yaml(config)
        assert lc.context_manager.max_context_tokens == 1500
        assert lc.default_abstraction == AbstractionLevel.TECHNICAL
        assert lc.llm_function == 'test_func'
        assert lc.llm_temperature == 0.5

    def test_from_yaml_defaults(self):
        """YAML with empty config uses defaults."""
        lc = BrainLanguageCenter.from_yaml({})
        assert lc.context_manager.max_context_tokens == 2000
        assert lc.default_abstraction == AbstractionLevel.STANDARD

    def test_from_yaml_invalid_abstraction(self):
        """Invalid abstraction falls back to STANDARD."""
        config = {'language_center': {'default_abstraction': 'invalid'}}
        lc = BrainLanguageCenter.from_yaml(config)
        assert lc.default_abstraction == AbstractionLevel.STANDARD


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

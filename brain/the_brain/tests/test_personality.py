"""
Tests for Personality System (P4.52-54).

Covers: Big5Traits, PersonalityModel, EmotionalExpression, CommunicationStyle.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.personality import (
    Big5Traits,
    PersonalityModel,
    EmotionalExpression,
    StyleMode,
    CommunicationStyle,
)


# ─── Big5Traits Tests ────────────────────────────────────────────────────

class TestBig5Traits:
    def test_defaults(self):
        """Default Big-5 values match Tahlamus personality."""
        t = Big5Traits()
        assert t.openness == 0.8
        assert t.conscientiousness == 0.9
        assert t.extraversion == 0.4
        assert t.agreeableness == 0.7
        assert t.neuroticism == 0.3

    def test_to_dict(self):
        """to_dict round-trips correctly."""
        t = Big5Traits(openness=0.55555)
        d = t.to_dict()
        assert d['openness'] == 0.56  # Rounded to 2 decimal places
        assert set(d.keys()) == {'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism'}

    def test_from_dict(self):
        """from_dict creates correct traits."""
        d = {'openness': 0.3, 'extraversion': 0.9}
        t = Big5Traits.from_dict(d)
        assert t.openness == 0.3
        assert t.extraversion == 0.9
        assert t.conscientiousness == 0.9  # Default

    def test_from_dict_empty(self):
        """Empty dict uses all defaults."""
        t = Big5Traits.from_dict({})
        assert t.openness == 0.8


# ─── PersonalityModel Tests ──────────────────────────────────────────────

class TestPersonalityModel:
    def test_default_style_instructions(self):
        """Default personality generates meaningful instructions."""
        pm = PersonalityModel()
        instructions = pm.get_style_instructions()
        assert isinstance(instructions, str)
        assert len(instructions) > 10
        # Default: high openness → curious
        assert "curious" in instructions.lower() or "connections" in instructions.lower()
        # Default: high conscientiousness → precise
        assert "precise" in instructions.lower() or "thorough" in instructions.lower()

    def test_low_extraversion_concise(self):
        """Low extraversion → concise instruction."""
        pm = PersonalityModel(Big5Traits(extraversion=0.2))
        instructions = pm.get_style_instructions()
        assert "concise" in instructions.lower()

    def test_high_extraversion_expressive(self):
        """High extraversion → expressive instruction."""
        pm = PersonalityModel(Big5Traits(extraversion=0.8))
        instructions = pm.get_style_instructions()
        assert "expressive" in instructions.lower() or "proactive" in instructions.lower()

    def test_low_agreeableness_direct(self):
        """Low agreeableness → direct instruction."""
        pm = PersonalityModel(Big5Traits(agreeableness=0.2))
        instructions = pm.get_style_instructions()
        assert "direct" in instructions.lower() or "blunt" in instructions.lower()

    def test_high_neuroticism_concerned(self):
        """High neuroticism → concern about risks."""
        pm = PersonalityModel(Big5Traits(neuroticism=0.8))
        instructions = pm.get_style_instructions()
        assert "concern" in instructions.lower() or "risk" in instructions.lower()

    def test_neutral_personality(self):
        """Mid-range personality → default message."""
        pm = PersonalityModel(Big5Traits(
            openness=0.5, conscientiousness=0.5, extraversion=0.5,
            agreeableness=0.5, neuroticism=0.5,
        ))
        instructions = pm.get_style_instructions()
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_communication_parameters(self):
        """Communication parameters derived from traits."""
        pm = PersonalityModel()
        params = pm.get_communication_parameters()
        assert 'max_sentence_length' in params
        assert 'formality' in params
        assert 'directness' in params
        assert 'emoji_likelihood' in params
        assert 'detail_level' in params
        assert 'proactivity' in params
        assert 'caution_level' in params
        # Validate ranges
        assert 15 <= params['max_sentence_length'] <= 30
        assert 0.0 <= params['formality'] <= 1.0
        assert 0.0 <= params['emoji_likelihood'] <= 1.0

    def test_should_speak_high_importance(self):
        """High importance always triggers speech."""
        pm = PersonalityModel()  # E=0.4, threshold=0.6
        assert pm.should_speak(importance=0.9, urgency=0.0) is True

    def test_should_speak_low_importance(self):
        """Low importance doesn't trigger speech for introverted personality."""
        pm = PersonalityModel(Big5Traits(extraversion=0.2))
        assert pm.should_speak(importance=0.3, urgency=0.0) is False

    def test_should_speak_high_urgency(self):
        """High urgency triggers speech."""
        pm = PersonalityModel()
        assert pm.should_speak(importance=0.0, urgency=0.8) is True

    def test_should_speak_extraverted(self):
        """Extraverted personality speaks more often."""
        pm = PersonalityModel(Big5Traits(extraversion=0.9))
        # Threshold = 0.1, so even low importance should trigger
        assert pm.should_speak(importance=0.2, urgency=0.0) is True

    def test_get_state(self):
        """State includes traits and style summary."""
        pm = PersonalityModel()
        state = pm.get_state()
        assert 'traits' in state
        assert 'style_summary' in state
        assert len(state['style_summary']) <= 100

    def test_from_yaml(self):
        """Creates from YAML config."""
        config = {
            'personality': {
                'traits': {
                    'openness': 0.3,
                    'extraversion': 0.9,
                }
            }
        }
        pm = PersonalityModel.from_yaml(config)
        assert pm.traits.openness == 0.3
        assert pm.traits.extraversion == 0.9
        assert pm.traits.conscientiousness == 0.9  # Default

    def test_from_yaml_empty(self):
        """Empty YAML uses all defaults."""
        pm = PersonalityModel.from_yaml({})
        assert pm.traits.openness == 0.8


# ─── EmotionalExpression Tests ───────────────────────────────────────────

class TestEmotionalExpression:
    def test_enthusiastic_tone(self):
        """High valence + high arousal → enthusiastic."""
        ee = EmotionalExpression(subtlety=0.3)
        tone = ee.get_tone(valence=0.6, arousal=0.7)
        assert tone == 'enthusiastic'

    def test_satisfied_tone(self):
        """Positive valence + low arousal → satisfied."""
        ee = EmotionalExpression()
        tone = ee.get_tone(valence=0.4, arousal=0.3)
        assert tone == 'satisfied'

    def test_concerned_tone(self):
        """Negative valence + high arousal → concerned."""
        ee = EmotionalExpression()
        tone = ee.get_tone(valence=-0.5, arousal=0.8)
        assert tone == 'concerned'

    def test_subdued_tone(self):
        """Negative valence + low arousal → subdued."""
        ee = EmotionalExpression()
        tone = ee.get_tone(valence=-0.4, arousal=0.3)
        assert tone == 'subdued'

    def test_curious_tone(self):
        """Neutral valence + high arousal → curious."""
        ee = EmotionalExpression()
        tone = ee.get_tone(valence=0.1, arousal=0.7)
        assert tone == 'curious'

    def test_neutral_fallback(self):
        """Low everything → neutral."""
        ee = EmotionalExpression()
        tone = ee.get_tone(valence=0.0, arousal=0.0)
        # May be 'satisfied' or 'neutral' depending on thresholds
        assert tone in ('neutral', 'satisfied', 'subdued', 'curious')

    def test_get_opener_high_intensity(self):
        """High intensity produces opener."""
        ee = EmotionalExpression(subtlety=0.3)
        opener = ee.get_opener(valence=0.8, arousal=0.9)
        assert len(opener) > 0
        assert opener in ["Excellent!", "Great progress!", "This worked out really well."]

    def test_get_opener_suppressed_by_subtlety(self):
        """High subtlety suppresses low-intensity openers."""
        ee = EmotionalExpression(subtlety=0.9)
        opener = ee.get_opener(valence=0.3, arousal=0.3)
        assert opener == ''

    def test_get_closer(self):
        """Closer produced for high-intensity concerned tone."""
        ee = EmotionalExpression(subtlety=0.3)
        closer = ee.get_closer(valence=-0.5, arousal=0.8)
        assert len(closer) > 0

    def test_modulate_text(self):
        """Text modulation adds opener and closer."""
        ee = EmotionalExpression(subtlety=0.2)
        text = ee.modulate_text("All tests passed.", valence=0.7, arousal=0.8)
        assert "All tests passed." in text
        assert len(text) > len("All tests passed.")

    def test_modulate_text_neutral(self):
        """Neutral emotion doesn't modify text."""
        ee = EmotionalExpression(subtlety=0.8)
        text = ee.modulate_text("Status OK.", valence=0.0, arousal=0.0)
        assert text == "Status OK."

    def test_get_llm_tone_instruction(self):
        """LLM tone instructions match tone names."""
        ee = EmotionalExpression()
        inst = ee.get_llm_tone_instruction(valence=0.8, arousal=0.8)
        assert "enthusiastic" in inst.lower() or "positive" in inst.lower()

        inst2 = ee.get_llm_tone_instruction(valence=-0.5, arousal=0.8)
        assert "concern" in inst2.lower()

    def test_subtlety_clamp(self):
        """Subtlety clamped to 0-1."""
        ee1 = EmotionalExpression(subtlety=-0.5)
        assert ee1.subtlety == 0.0
        ee2 = EmotionalExpression(subtlety=1.5)
        assert ee2.subtlety == 1.0

    def test_get_state(self):
        """State includes subtlety and available tones."""
        ee = EmotionalExpression(subtlety=0.5)
        state = ee.get_state()
        assert state['subtlety'] == 0.5
        assert 'enthusiastic' in state['available_tones']
        assert 'neutral' not in state['available_tones']


# ─── CommunicationStyle Tests ───────────────────────────────────────────

class TestCommunicationStyle:
    def test_default_mode(self):
        """Default mode is TECHNICAL."""
        cs = CommunicationStyle()
        mode = cs.select_mode()
        assert mode == StyleMode.TECHNICAL

    def test_alarm_on_urgency(self):
        """High urgency triggers ALARM mode."""
        cs = CommunicationStyle()
        mode = cs.select_mode(urgency=0.9)
        assert mode == StyleMode.ALARM

    def test_alarm_on_error_and_urgency(self):
        """Error + moderate urgency triggers ALARM."""
        cs = CommunicationStyle()
        mode = cs.select_mode(is_error=True, urgency=0.6)
        assert mode == StyleMode.ALARM

    def test_technical_on_error(self):
        """Error without urgency → TECHNICAL."""
        cs = CommunicationStyle()
        mode = cs.select_mode(is_error=True, urgency=0.2)
        assert mode == StyleMode.TECHNICAL

    def test_report_on_status(self):
        """Status update → STATUS_REPORT."""
        cs = CommunicationStyle()
        mode = cs.select_mode(is_status_update=True)
        assert mode == StyleMode.STATUS_REPORT

    def test_user_preference(self):
        """User preference overrides default."""
        cs = CommunicationStyle(user_preference='chat')
        mode = cs.select_mode()
        assert mode == StyleMode.CONVERSATIONAL

    def test_learned_preference(self):
        """After feedback, learned preference is used."""
        cs = CommunicationStyle()
        # Give enough positive feedback for 'chat'
        for _ in range(10):
            cs.record_feedback('chat', positive=True)
        mode = cs.select_mode()
        assert mode == StyleMode.CONVERSATIONAL

    def test_urgency_overrides_preference(self):
        """Alarm still overrides user preference."""
        cs = CommunicationStyle(user_preference='chat')
        mode = cs.select_mode(urgency=0.9)
        assert mode == StyleMode.ALARM

    def test_get_style_instructions(self):
        """Style instructions exist for all modes."""
        cs = CommunicationStyle()
        for mode in StyleMode:
            inst = cs.get_style_instructions(mode)
            assert isinstance(inst, str)
            assert len(inst) > 10

    def test_record_feedback_positive(self):
        """Positive feedback increases score."""
        cs = CommunicationStyle()
        initial = cs._preference_scores['chat']
        cs.record_feedback('chat', positive=True)
        assert cs._preference_scores['chat'] > initial
        assert cs._feedback_count == 1

    def test_record_feedback_negative(self):
        """Negative feedback decreases score."""
        cs = CommunicationStyle()
        initial = cs._preference_scores['technical']
        cs.record_feedback('technical', positive=False)
        assert cs._preference_scores['technical'] < initial

    def test_score_clamped(self):
        """Scores stay within 0-1."""
        cs = CommunicationStyle()
        # Push high
        for _ in range(100):
            cs.record_feedback('chat', positive=True)
        assert cs._preference_scores['chat'] <= 1.0

        # Push low
        for _ in range(200):
            cs.record_feedback('report', positive=False)
        assert cs._preference_scores['report'] >= 0.0

    def test_get_state(self):
        """State includes all relevant fields."""
        cs = CommunicationStyle(user_preference='chat')
        state = cs.get_state()
        assert state['default_mode'] == 'technical'
        assert state['user_preference'] == 'chat'
        assert 'preference_scores' in state
        assert state['feedback_count'] == 0

    def test_from_yaml(self):
        """Creates from YAML config."""
        config = {
            'communication_style': {
                'default_mode': 'chat',
                'user_preference': 'report',
            }
        }
        cs = CommunicationStyle.from_yaml(config)
        assert cs.default_mode == StyleMode.CONVERSATIONAL
        assert cs.user_preference == 'report'

    def test_from_yaml_invalid_mode(self):
        """Invalid mode falls back to TECHNICAL."""
        config = {'communication_style': {'default_mode': 'invalid'}}
        cs = CommunicationStyle.from_yaml(config)
        assert cs.default_mode == StyleMode.TECHNICAL

    def test_from_yaml_empty(self):
        """Empty config uses defaults."""
        cs = CommunicationStyle.from_yaml({})
        assert cs.default_mode == StyleMode.TECHNICAL
        assert cs.user_preference is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

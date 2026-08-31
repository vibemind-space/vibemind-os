"""
Unit tests for Sensory Preprocessor (core/sensory_preprocessor.py)

Tests cover:
- SensoryFeatures defaults and serialization
- Empty input handling
- Lexical feature extraction (word count, vocabulary richness)
- Semantic feature extraction (tech words, abstractions)
- Syntactic features (questions, code blocks, URLs)
- Temporal features (time references, urgency)
- Emotional features (positive/negative signals)
- Complexity features (multi-step, long words)
- Intent detection (create, modify, delete, query, analyze)
- Domain detection (coding, deployment, analysis, communication, security)
- Risk assessment (high, medium, low risk words)
- Social features (mentions, collaboration)
- Overall urgency computation
- to_flat_vector shape
- to_dict completeness
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from core.sensory_preprocessor import SensoryPreprocessor, SensoryFeatures


@pytest.fixture
def sp():
    return SensoryPreprocessor()


class TestSensoryFeaturesDataclass:
    """Tests for SensoryFeatures defaults."""

    def test_defaults(self):
        f = SensoryFeatures()
        assert f.overall_complexity == 0.5
        assert f.overall_urgency == 0.3
        assert f.overall_risk == 0.0
        assert f.detected_domain == "general"
        assert f.detected_intent == "unknown"

    def test_to_flat_vector_shape(self):
        f = SensoryFeatures()
        vec = f.to_flat_vector()
        assert vec.shape == (80,)  # 10 channels * 8 dims

    def test_to_dict_keys(self):
        f = SensoryFeatures()
        d = f.to_dict()
        assert 'overall_complexity' in d
        assert 'overall_urgency' in d
        assert 'overall_risk' in d
        assert 'detected_domain' in d
        assert 'detected_intent' in d


class TestEmptyInput:
    """Tests for empty/minimal input."""

    def test_empty_string(self, sp):
        f = sp.extract("")
        # Empty input returns default SensoryFeatures (early return)
        assert f.detected_intent == "unknown"
        assert f.detected_domain == "general"
        assert np.allclose(f.lexical, 0)

    def test_single_word(self, sp):
        f = sp.extract("hello")
        assert f.lexical[0] > 0  # Word count > 0


class TestLexicalFeatures:
    """Tests for lexical extraction."""

    def test_word_count_scales(self, sp):
        short = sp.extract("hello world")
        long = sp.extract("this is a much longer sentence with many words for testing purposes")
        assert long.lexical[0] > short.lexical[0]

    def test_vocabulary_richness(self, sp):
        repetitive = sp.extract("the the the the the")
        diverse = sp.extract("apple banana cherry date elderberry")
        assert diverse.lexical[1] > repetitive.lexical[1]

    def test_multiline_detected(self, sp):
        f = sp.extract("line one\nline two")
        assert f.lexical[7] == 1.0

    def test_comma_density(self, sp):
        f = sp.extract("one, two, three, four, five")
        assert f.lexical[5] > 0.0


class TestSemanticFeatures:
    """Tests for semantic extraction."""

    def test_technical_vocabulary(self, sp):
        f = sp.extract("implement the api function for the database server")
        assert f.semantic[0] > 0.0  # Technical words detected

    def test_abstract_concepts(self, sp):
        f = sp.extract("the system architecture follows a design pattern")
        assert f.semantic[1] > 0.0

    def test_question_words(self, sp):
        f = sp.extract("what is the problem and how do we fix it")
        assert f.semantic[7] > 0.0


class TestSyntacticFeatures:
    """Tests for syntactic extraction."""

    def test_question_mark(self, sp):
        f = sp.extract("Is this working?")
        assert f.syntactic[0] == 1.0

    def test_exclamation(self, sp):
        f = sp.extract("This is urgent!")
        assert f.syntactic[1] == 1.0

    def test_code_block(self, sp):
        f = sp.extract("Here is code: ```python\nprint('hello')\n```")
        assert f.syntactic[2] == 1.0

    def test_url_detected(self, sp):
        f = sp.extract("Check https://example.com for details")
        assert f.syntactic[3] == 1.0

    def test_acronym_detected(self, sp):
        f = sp.extract("The API returns JSON data")
        assert f.syntactic[4] == 1.0


class TestTemporalFeatures:
    """Tests for temporal extraction."""

    def test_deadline_detected(self, sp):
        f = sp.extract("This needs to be done before the deadline")
        assert f.temporal[0] > 0.0  # temporal count
        assert f.temporal[1] == 1.0  # deadline signal

    def test_today_reference(self, sp):
        f = sp.extract("complete this today")
        assert f.temporal[3] == 1.0

    def test_no_temporal(self, sp):
        f = sp.extract("write a function")
        assert f.temporal[0] == 0.0


class TestEmotionalFeatures:
    """Tests for emotional extraction."""

    def test_positive_signals(self, sp):
        f = sp.extract("great success with the perfect deployment")
        assert f.emotional[0] > 0.0  # Positive high arousal

    def test_negative_signals(self, sp):
        f = sp.extract("critical error crash in the system")
        assert f.emotional[1] > 0.0  # Negative high arousal

    def test_alarm_signal(self, sp):
        f = sp.extract("error error crash crash critical emergency")
        assert f.emotional[7] == 1.0  # Alarm

    def test_neutral_input(self, sp):
        f = sp.extract("the weather is nice")
        assert f.emotional[0] == 0.0
        assert f.emotional[1] == 0.0


class TestComplexityFeatures:
    """Tests for complexity extraction."""

    def test_simple_task(self, sp):
        f = sp.extract("check status")
        assert f.overall_complexity < 0.3

    def test_complex_task(self, sp):
        f = sp.extract(
            "first analyze the architecture, then refactor the authentication module, "
            "next implement the new database migration, and finally run the integration tests"
        )
        assert f.complexity[7] > 0.0  # Multi-step indicator

    def test_code_presence(self, sp):
        f = sp.extract("fix this ```python\ndef foo():\n  pass\n```")
        assert f.complexity[6] == 1.0


class TestIntentDetection:
    """Tests for intent detection."""

    def test_create_intent(self, sp):
        f = sp.extract("create a new function to build the feature")
        assert f.detected_intent == "create"

    def test_modify_intent(self, sp):
        f = sp.extract("update and fix the existing code")
        assert f.detected_intent == "modify"

    def test_delete_intent(self, sp):
        f = sp.extract("delete and remove the old files")
        assert f.detected_intent == "delete"

    def test_query_intent(self, sp):
        f = sp.extract("find and list all the available files")
        assert f.detected_intent == "query"

    def test_analyze_intent(self, sp):
        f = sp.extract("explain why this is happening and investigate the cause")
        assert f.detected_intent == "analyze"

    def test_unknown_intent(self, sp):
        f = sp.extract("hello world")
        assert f.detected_intent == "unknown"


class TestDomainDetection:
    """Tests for domain detection."""

    def test_coding_domain(self, sp):
        f = sp.extract("refactor the python function and add unit tests")
        assert f.detected_domain == "coding"

    def test_deployment_domain(self, sp):
        f = sp.extract("deploy the docker container to the production server")
        assert f.detected_domain == "deployment"

    def test_analysis_domain(self, sp):
        f = sp.extract("analyze the data and create a chart of the metrics")
        assert f.detected_domain == "analysis"

    def test_communication_domain(self, sp):
        f = sp.extract("send a message to the team about the meeting")
        assert f.detected_domain == "communication"

    def test_security_domain(self, sp):
        f = sp.extract("check the authentication token and firewall permissions")
        assert f.detected_domain == "security"

    def test_general_domain(self, sp):
        f = sp.extract("hello world")
        assert f.detected_domain == "general"


class TestRiskAssessment:
    """Tests for risk assessment."""

    def test_high_risk(self, sp):
        f = sp.extract("delete everything from the production database with sudo")
        assert f.overall_risk > 0.5

    def test_medium_risk(self, sp):
        f = sp.extract("modify and update the configuration")
        assert 0.0 < f.overall_risk < 0.8

    def test_low_risk(self, sp):
        f = sp.extract("read and check the test results")
        assert f.overall_risk < 0.3

    def test_zero_risk(self, sp):
        f = sp.extract("hello world")
        assert f.overall_risk == 0.0


class TestSocialFeatures:
    """Tests for social features."""

    def test_mention_detected(self, sp):
        f = sp.extract("ask @john about this")
        assert f.social[0] == 1.0

    def test_team_collaboration(self, sp):
        f = sp.extract("share this with the team for review")
        assert f.social[1] == 1.0
        assert f.social[2] == 1.0  # review
        assert f.social[3] == 1.0  # share

    def test_user_reference(self, sp):
        f = sp.extract("the customer needs help with support")
        assert f.social[4] == 1.0  # customer
        assert f.social[5] == 1.0  # help


class TestUrgency:
    """Tests for overall urgency computation."""

    def test_urgent_task(self, sp):
        f = sp.extract("this is urgent and critical, we need it now asap")
        assert f.overall_urgency > 0.5

    def test_no_urgency(self, sp):
        f = sp.extract("write a function when you have time")
        assert f.overall_urgency == 0.0


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_very_long_input(self, sp):
        f = sp.extract("error " * 500)
        assert f.emotional[1] > 0.0
        # Should not crash

    def test_special_characters(self, sp):
        f = sp.extract("fix the #1 bug: error@line:42!")
        assert f.detected_intent is not None

    def test_all_caps(self, sp):
        f = sp.extract("URGENT FIX NEEDED ASAP")
        assert f.syntactic[4] == 1.0  # Acronyms detected

    def test_numeric_input(self, sp):
        f = sp.extract("42 99 100 0.5 3.14")
        assert f.semantic[3] > 0.0  # Quantitative terms


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

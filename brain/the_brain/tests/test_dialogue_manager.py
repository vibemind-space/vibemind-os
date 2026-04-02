"""
Tests for Dialogue Management (P4.58-60).

Covers: ConversationMemory, ClarificationEngine, DialogueManager.
"""

import pytest
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.dialogue_manager import (
    ConversationTurn,
    SessionSummary,
    ConversationMemory,
    ClarificationRequest,
    ClarificationEngine,
    DialogueState,
    DialogueSlots,
    DialogueManager,
)


# ─── ConversationTurn Tests ──────────────────────────────────────────────

class TestConversationTurn:
    def test_auto_timestamp(self):
        """Timestamp auto-generated."""
        t = ConversationTurn(role='user', content='hello')
        assert t.timestamp > 0

    def test_to_dict(self):
        """Serializes correctly."""
        t = ConversationTurn(role='brain', content='response', channel='websocket')
        d = t.to_dict()
        assert d['role'] == 'brain'
        assert d['channel'] == 'websocket'

    def test_content_truncated_in_dict(self):
        """Long content truncated in to_dict."""
        t = ConversationTurn(role='user', content='x' * 500)
        d = t.to_dict()
        assert len(d['content']) == 200


# ─── ConversationMemory Tests ───────────────────────────────────────────

class TestConversationMemory:
    def test_add_turn(self):
        """Turns are recorded."""
        cm = ConversationMemory()
        turn = cm.add_turn('user', 'hello')
        assert turn.role == 'user'
        assert turn.content == 'hello'
        assert len(cm._current_turns) == 1

    def test_get_recent_turns(self):
        """Recent turns returned in order."""
        cm = ConversationMemory()
        cm.add_turn('user', 'msg1')
        cm.add_turn('brain', 'resp1')
        cm.add_turn('user', 'msg2')
        recent = cm.get_recent_turns(2)
        assert len(recent) == 2
        assert recent[0].content == 'resp1'
        assert recent[1].content == 'msg2'

    def test_get_context_for_llm(self):
        """LLM context formatted correctly."""
        cm = ConversationMemory()
        cm.add_turn('user', 'Deploy the service')
        cm.add_turn('brain', 'I will deploy to staging first.')
        ctx = cm.get_context_for_llm(max_turns=5)
        assert "[User]: Deploy the service" in ctx
        assert "[Brain]: I will deploy to staging first." in ctx

    def test_get_context_for_llm_empty(self):
        """Empty conversation returns empty string."""
        cm = ConversationMemory()
        assert cm.get_context_for_llm() == ""

    def test_end_session(self):
        """End session creates summary."""
        cm = ConversationMemory()
        cm.add_turn('user', 'Fix the build')
        cm.add_turn('brain', 'I will analyze the error logs.')
        cm.add_turn('user', 'What did you find?')
        summary = cm.end_session()
        assert summary.turn_count == 3
        assert summary.session_id == 'session_1'
        assert len(summary.topics) > 0

    def test_end_session_clears_turns(self):
        """Turns cleared after session end."""
        cm = ConversationMemory()
        cm.add_turn('user', 'hello')
        cm.end_session()
        assert len(cm._current_turns) == 0

    def test_multiple_sessions(self):
        """Multiple sessions tracked."""
        cm = ConversationMemory()
        cm.add_turn('user', 'session 1')
        cm.end_session()
        cm.add_turn('user', 'session 2')
        cm.end_session()
        assert len(cm._session_summaries) == 2
        assert cm._session_counter == 2

    def test_max_sessions(self):
        """Old sessions pruned."""
        cm = ConversationMemory(max_sessions=3)
        for i in range(5):
            cm.add_turn('user', f'session {i}')
            cm.end_session()
        assert len(cm._session_summaries) == 3

    def test_search_history(self):
        """Search finds relevant sessions."""
        cm = ConversationMemory()
        cm.add_turn('user', 'Deploy the API')
        cm.end_session(topics=['deploy', 'api'], summary='Discussed API deployment strategy')
        cm.add_turn('user', 'Fix build error')
        cm.end_session(topics=['build', 'error'], summary='Fixed compilation issue')

        results = cm.search_history('deploy')
        assert len(results) >= 1
        assert 'deploy' in results[0].topics or 'deploy' in results[0].summary.lower()

    def test_search_history_no_match(self):
        """Search with no match returns empty."""
        cm = ConversationMemory()
        cm.add_turn('user', 'hello')
        cm.end_session(topics=['greeting'])
        results = cm.search_history('database migration')
        assert len(results) == 0

    def test_auto_summarize(self):
        """Auto-summary includes turn count and first message."""
        cm = ConversationMemory()
        cm.add_turn('user', 'Fix the critical bug')
        cm.add_turn('brain', 'Investigating now.')
        summary = cm.end_session()
        assert '2 turns' in summary.summary
        assert 'Fix the critical bug' in summary.summary

    def test_extract_decisions(self):
        """Key decisions extracted from brain turns."""
        cm = ConversationMemory()
        cm.add_turn('user', 'What should we do?')
        cm.add_turn('brain', "I'll deploy the fix to staging first.")
        cm.add_turn('brain', 'Status check looks fine.')
        summary = cm.end_session()
        # "I'll" should be detected as commitment
        assert len(summary.key_decisions) >= 1

    def test_cross_channel(self):
        """Different channels tracked."""
        cm = ConversationMemory()
        cm.add_turn('user', 'hello', channel='websocket')
        cm.add_turn('user', 'fix build', channel='whatsapp')
        recent = cm.get_recent_turns(5)
        assert recent[0].channel == 'websocket'
        assert recent[1].channel == 'whatsapp'

    def test_get_state(self):
        """State dict is correct."""
        cm = ConversationMemory()
        cm.add_turn('user', 'hello')
        state = cm.get_state()
        assert state['current_session_turns'] == 1
        assert state['total_sessions'] == 0


# ─── ClarificationRequest Tests ─────────────────────────────────────────

class TestClarificationRequest:
    def test_to_dict(self):
        """Serializes correctly."""
        cr = ClarificationRequest(
            question='Which project?',
            reason='missing_target',
            slot_name='target',
            options=['api', 'web'],
        )
        d = cr.to_dict()
        assert d['question'] == 'Which project?'
        assert d['options'] == ['api', 'web']


# ─── ClarificationEngine Tests ──────────────────────────────────────────

class TestClarificationEngine:
    def test_ambiguous_reference(self):
        """Short input with pronoun triggers clarification."""
        ce = ClarificationEngine()
        reqs = ce.check_input("Deploy that")
        assert len(reqs) >= 1
        assert any(r.slot_name in ('target', 'deploy_target') for r in reqs)

    def test_clear_input_no_clarification(self):
        """Clear input doesn't trigger clarification."""
        ce = ClarificationEngine()
        reqs = ce.check_input("Deploy the api service to staging environment")
        assert len(reqs) == 0

    def test_deploy_without_target(self):
        """'Deploy' without project/service triggers question."""
        ce = ClarificationEngine()
        reqs = ce.check_input("deploy now")
        deploy_reqs = [r for r in reqs if r.slot_name == 'deploy_target']
        assert len(deploy_reqs) >= 1

    def test_deploy_with_target(self):
        """'Deploy' with explicit target is fine."""
        ce = ClarificationEngine()
        reqs = ce.check_input("deploy the service")
        deploy_reqs = [r for r in reqs if r.slot_name == 'deploy_target']
        assert len(deploy_reqs) == 0

    def test_fix_without_context(self):
        """'Fix' without specifying what triggers question."""
        ce = ClarificationEngine()
        reqs = ce.check_input("fix it")
        # Should trigger either target or fix_target
        assert len(reqs) >= 1

    def test_long_input_not_flagged(self):
        """Long inputs (>8 words) are not flagged."""
        ce = ClarificationEngine()
        reqs = ce.check_input("run the test suite for the api module in staging environment please")
        assert len(reqs) == 0

    def test_filled_slots_skip(self):
        """Already-filled slots not asked again."""
        ce = ClarificationEngine()
        reqs = ce.check_input("deploy now", filled_slots={'deploy_target': 'api'})
        deploy_reqs = [r for r in reqs if r.slot_name == 'deploy_target']
        assert len(deploy_reqs) == 0

    def test_resolve_clarification(self):
        """Resolving removes open clarification."""
        ce = ClarificationEngine()
        ce.check_input("deploy now")
        assert ce.get_open_clarifications()
        resolved = ce.resolve_clarification('deploy_target', 'api-service')
        assert resolved is True
        assert ce._total_resolved == 1

    def test_resolve_nonexistent(self):
        """Resolving nonexistent slot returns False."""
        ce = ClarificationEngine()
        resolved = ce.resolve_clarification('nonexistent', 'value')
        assert resolved is False

    def test_max_open_clarifications(self):
        """Open clarifications capped at max."""
        ce = ClarificationEngine(max_open_clarifications=2)
        for i in range(5):
            ce.check_input(f"fix it")  # Will add fix_target or target
        assert len(ce._open_clarifications) <= 2

    def test_get_state(self):
        """State dict correct."""
        ce = ClarificationEngine()
        ce.check_input("deploy now")
        state = ce.get_state()
        assert state['total_requests'] >= 1
        assert state['open_count'] >= 1


# ─── DialogueSlots Tests ────────────────────────────────────────────────

class TestDialogueSlots:
    def test_to_dict(self):
        """Serializes correctly."""
        slots = DialogueSlots(current_topic='deploy', user_intent='deploy')
        d = slots.to_dict()
        assert d['current_topic'] == 'deploy'
        assert d['user_intent'] == 'deploy'


# ─── DialogueManager Tests ──────────────────────────────────────────────

class TestDialogueManager:
    def test_process_clear_input(self):
        """Clear input processes without clarification."""
        dm = DialogueManager()
        result = dm.process_user_input("Please run the pytest test suite on the core module for me now")
        assert result['needs_clarification'] is False
        assert dm._total_turns == 1

    def test_process_ambiguous_input(self):
        """Ambiguous input triggers clarification."""
        dm = DialogueManager()
        result = dm.process_user_input("Deploy that")
        assert result['needs_clarification'] is True
        assert len(result['clarification_requests']) >= 1

    def test_record_response(self):
        """Brain response recorded in memory."""
        dm = DialogueManager()
        dm.process_user_input("What's the status?")
        dm.record_response("All systems are operational.")
        recent = dm.memory.get_recent_turns(5)
        assert len(recent) == 2
        assert recent[0].role == 'user'
        assert recent[1].role == 'brain'

    def test_commitment_tracking(self):
        """Commitments detected in responses."""
        dm = DialogueManager()
        dm.process_user_input("Can you fix the build?")
        dm.record_response("I'll investigate and fix the build error.")
        assert len(dm._slots.commitments) >= 1
        assert any("I'll" in c for c in dm._slots.commitments)

    def test_explicit_commitment(self):
        """Explicit commitment parameter tracked."""
        dm = DialogueManager()
        dm.process_user_input("Fix the build")
        dm.record_response("Working on it.", commitment="Fix build error #42")
        assert "Fix build error #42" in dm._slots.commitments

    def test_reference_resolution_repeat(self):
        """'Do that again' resolves to last user message."""
        dm = DialogueManager()
        dm.process_user_input("Run the test suite")
        dm.record_response("Tests passed.")
        result = dm.process_user_input("Do that again")
        assert result['resolved_input'] == "Run the test suite"

    def test_reference_resolution_again(self):
        """'again' resolves to last user message."""
        dm = DialogueManager()
        dm.process_user_input("Deploy to staging")
        dm.record_response("Deployed.")
        result = dm.process_user_input("again")
        assert result['resolved_input'] == "Deploy to staging"

    def test_intent_detection(self):
        """Intents correctly detected."""
        dm = DialogueManager()
        r1 = dm.process_user_input("Deploy the new version to production")
        assert r1['intent'] == 'deploy'

        r2 = dm.process_user_input("Fix the broken authentication module")
        assert r2['intent'] == 'fix'

        r3 = dm.process_user_input("How is the build status looking right now")
        assert r3['intent'] == 'status'

        r4 = dm.process_user_input("Explain why you chose this approach over others")
        assert r4['intent'] == 'explain'

    def test_topic_tracking(self):
        """Topics tracked across turns."""
        dm = DialogueManager()
        dm.process_user_input("Deploy the API service to staging")
        assert dm._slots.current_topic is not None

    def test_context_stack(self):
        """Context stack grows as topics change."""
        dm = DialogueManager()
        dm.process_user_input("Deploy the service")
        first_topic = dm._slots.current_topic
        dm.record_response("OK")
        dm.process_user_input("Now fix the authentication bug")
        # First topic should be in context stack
        if first_topic:
            assert first_topic in dm._slots.context_stack

    def test_provide_clarification(self):
        """User provides clarification for open question."""
        dm = DialogueManager()
        dm.process_user_input("Deploy that")
        # Provide clarification
        filled = dm.provide_clarification('deploy_target', 'api-service')
        # Slot should be filled
        assert 'deploy_target' in dm._slots.filled

    def test_end_session(self):
        """End session creates summary and resets state."""
        dm = DialogueManager()
        dm.process_user_input("Hello")
        dm.record_response("Hi there!")
        summary = dm.end_session()
        assert summary is not None
        assert summary['turn_count'] == 2
        assert dm._slots.current_topic is None
        assert dm._state == DialogueState.IDLE

    def test_get_state(self):
        """State dict is comprehensive."""
        dm = DialogueManager()
        dm.process_user_input("test")
        state = dm.get_state()
        assert state['state'] in ('idle', 'processing', 'awaiting_clarification', 'responding')
        assert state['total_turns'] == 1
        assert 'slots' in state
        assert 'clarification' in state
        assert 'memory' in state

    def test_from_yaml(self):
        """Creates from YAML config."""
        config = {
            'dialogue_manager': {
                'max_context_depth': 20,
                'conversation_memory': {
                    'max_turns_per_session': 50,
                    'max_sessions': 25,
                },
                'clarification': {
                    'max_open_clarifications': 3,
                },
            }
        }
        dm = DialogueManager.from_yaml(config)
        assert dm.max_context_depth == 20
        assert dm.memory.max_turns_per_session == 50
        assert dm.clarification.max_open_clarifications == 3

    def test_from_yaml_empty(self):
        """Empty config uses defaults."""
        dm = DialogueManager.from_yaml({})
        assert dm.max_context_depth == 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

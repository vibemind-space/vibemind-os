"""Tests for Experience Learning (P5.61-63) and Skill Library (P5.64-66)."""

import time
import pytest
from core.experience_learning import (
    Experience, ExperienceReplaySystem, OutcomeType,
    AutomaticOutcomeLearning, OutcomeSignal,
    TransferLearning, DomainMapping,
)
from core.skill_library import (
    Skill, Action, SkillLibrary, SkillStatus,
    SkillComposition, SkillRefinement, ABTest,
)


# ═══════════════════════════════════════════════════════════════════
# P5.61: Experience Replay System
# ═══════════════════════════════════════════════════════════════════

class TestExperience:
    def test_creation(self):
        exp = Experience(
            situation="Deploy app", system="shell", action="deploy",
            params={"env": "prod"}, outcome=OutcomeType.SUCCESS,
            duration_ms=5000.0, emotional_valence=0.5, emotional_arousal=0.3,
        )
        assert exp.outcome == OutcomeType.SUCCESS
        assert exp.timestamp > 0

    def test_priority_failure_higher(self):
        success = Experience(
            situation="Test", system="shell", action="test",
            params={}, outcome=OutcomeType.SUCCESS,
            duration_ms=1000, emotional_valence=0.3, emotional_arousal=0.2,
        )
        failure = Experience(
            situation="Test", system="shell", action="test",
            params={}, outcome=OutcomeType.FAILURE,
            duration_ms=1000, emotional_valence=-0.5, emotional_arousal=0.7,
        )
        assert failure.priority > success.priority

    def test_to_from_dict(self):
        exp = Experience(
            situation="Build", system="coding", action="build",
            params={"target": "main"}, outcome=OutcomeType.PARTIAL,
            duration_ms=3000, emotional_valence=0.0, emotional_arousal=0.1,
            domain="deployment",
        )
        d = exp.to_dict()
        restored = Experience.from_dict(d)
        assert restored.situation == "Build"
        assert restored.outcome == OutcomeType.PARTIAL
        assert restored.domain == "deployment"

    def test_prediction_error_boosts_priority(self):
        low_pe = Experience(
            situation="A", system="s", action="a", params={},
            outcome=OutcomeType.SUCCESS, duration_ms=100,
            emotional_valence=0.0, emotional_arousal=0.0,
            prediction_error=0.1,
        )
        high_pe = Experience(
            situation="A", system="s", action="a", params={},
            outcome=OutcomeType.SUCCESS, duration_ms=100,
            emotional_valence=0.0, emotional_arousal=0.0,
            prediction_error=0.9,
        )
        assert high_pe.priority > low_pe.priority


class TestExperienceReplaySystem:
    def test_record_and_retrieve(self):
        ers = ExperienceReplaySystem(max_buffer=100)
        exp = Experience(
            situation="Deploy", system="shell", action="deploy",
            params={}, outcome=OutcomeType.SUCCESS, duration_ms=1000,
            emotional_valence=0.5, emotional_arousal=0.3, domain="deployment",
        )
        ers.record(exp)
        assert ers._total_stored == 1
        assert len(ers._buffer) == 1

    def test_sample_batch(self):
        ers = ExperienceReplaySystem(max_buffer=100, batch_size=5)
        for i in range(20):
            ers.record(Experience(
                situation=f"Task {i}", system="shell", action="run",
                params={}, outcome=OutcomeType.SUCCESS if i % 2 == 0 else OutcomeType.FAILURE,
                duration_ms=100, emotional_valence=0.0, emotional_arousal=0.0,
                domain="testing",
            ))
        batch = ers.sample_batch()
        assert len(batch) == 5
        assert ers._total_replayed == 5

    def test_sample_batch_by_domain(self):
        ers = ExperienceReplaySystem(max_buffer=100, batch_size=3)
        for domain in ["deploy", "test", "deploy", "build", "deploy"]:
            ers.record(Experience(
                situation=f"Task in {domain}", system="shell", action="run",
                params={}, outcome=OutcomeType.SUCCESS, duration_ms=100,
                emotional_valence=0.0, emotional_arousal=0.0, domain=domain,
            ))
        batch = ers.sample_batch(domain="deploy")
        for exp in batch:
            assert exp.domain == "deploy"

    def test_max_buffer_eviction(self):
        ers = ExperienceReplaySystem(max_buffer=5)
        for i in range(10):
            ers.record(Experience(
                situation=f"T{i}", system="s", action="a", params={},
                outcome=OutcomeType.SUCCESS, duration_ms=100,
                emotional_valence=0.0, emotional_arousal=0.0,
            ))
        assert len(ers._buffer) == 5

    def test_get_similar_experiences(self):
        ers = ExperienceReplaySystem()
        ers.record(Experience(
            situation="Deploy flask app to production", system="shell",
            action="deploy", params={}, outcome=OutcomeType.SUCCESS,
            duration_ms=5000, emotional_valence=0.5, emotional_arousal=0.3,
        ))
        ers.record(Experience(
            situation="Run unit tests for flask", system="shell",
            action="test", params={}, outcome=OutcomeType.SUCCESS,
            duration_ms=2000, emotional_valence=0.1, emotional_arousal=0.1,
        ))
        similar = ers.get_similar_experiences("Deploy flask service")
        assert len(similar) >= 1
        assert "deploy" in similar[0].situation.lower() or "flask" in similar[0].situation.lower()

    def test_domain_stats(self):
        ers = ExperienceReplaySystem()
        for i in range(5):
            ers.record(Experience(
                situation=f"Test {i}", system="shell", action="test",
                params={}, outcome=OutcomeType.SUCCESS if i < 3 else OutcomeType.FAILURE,
                duration_ms=1000, emotional_valence=0.0, emotional_arousal=0.0,
                domain="testing",
            ))
        stats = ers.get_domain_stats()
        assert "testing" in stats
        assert stats["testing"]["total"] == 5
        assert stats["testing"]["success_rate"] == 0.6

    def test_find_patterns(self):
        ers = ExperienceReplaySystem()
        for i in range(5):
            ers.record(Experience(
                situation=f"Deploy {i}", system="shell", action="deploy",
                params={}, outcome=OutcomeType.SUCCESS,
                duration_ms=1000, emotional_valence=0.0, emotional_arousal=0.0,
                domain="deployment",
            ))
        patterns = ers.find_patterns(min_occurrences=3)
        assert len(patterns) >= 1
        assert patterns[0]['action'] == "deploy"

    def test_get_state(self):
        ers = ExperienceReplaySystem()
        state = ers.get_state()
        assert 'buffer_size' in state
        assert 'total_stored' in state

    def test_from_yaml(self):
        cfg = {'experience_replay': {'max_buffer': 1000, 'batch_size': 32}}
        ers = ExperienceReplaySystem.from_yaml(cfg)
        assert ers.max_buffer == 1000
        assert ers.batch_size == 32


# ═══════════════════════════════════════════════════════════════════
# P5.62: Automatic Outcome Learning
# ═══════════════════════════════════════════════════════════════════

class TestAutomaticOutcomeLearning:
    def test_shell_success(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'exit_code': 0}, source='shell')
        assert signal is not None
        assert signal.outcome == OutcomeType.SUCCESS

    def test_shell_failure(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'exit_code': 1}, source='shell')
        assert signal is not None
        assert signal.outcome == OutcomeType.FAILURE

    def test_http_success(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'status_code': 200}, source='http')
        assert signal is not None
        assert signal.outcome == OutcomeType.SUCCESS

    def test_http_client_error(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'status_code': 404}, source='http')
        assert signal is not None
        assert signal.outcome == OutcomeType.FAILURE

    def test_http_server_error(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'status_code': 500}, source='http')
        assert signal is not None
        assert signal.outcome == OutcomeType.FAILURE
        assert signal.confidence >= 0.9

    def test_job_completed(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'status': 'completed'}, source='job')
        assert signal is not None
        assert signal.outcome == OutcomeType.SUCCESS

    def test_job_failed(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'status': 'failed'}, source='job')
        assert signal is not None
        assert signal.outcome == OutcomeType.FAILURE

    def test_timeout(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'timed_out': True}, source='any')
        assert signal is not None
        assert signal.outcome == OutcomeType.TIMEOUT

    def test_unknown_source(self):
        aol = AutomaticOutcomeLearning()
        signal = aol.detect_outcome({'foo': 'bar'}, source='unknown')
        assert signal is None

    def test_custom_rule(self):
        aol = AutomaticOutcomeLearning()
        aol.add_rule('custom', 'result', 'eq', 'pass', OutcomeType.SUCCESS)
        signal = aol.detect_outcome({'result': 'pass'}, source='custom')
        assert signal is not None
        assert signal.outcome == OutcomeType.SUCCESS

    def test_recent_success_rate(self):
        aol = AutomaticOutcomeLearning()
        for i in range(10):
            aol.detect_outcome({'exit_code': 0 if i < 7 else 1}, source='shell')
        rate = aol.get_recent_success_rate(10)
        assert rate == 0.7

    def test_get_state(self):
        aol = AutomaticOutcomeLearning()
        aol.detect_outcome({'exit_code': 0}, source='shell')
        state = aol.get_state()
        assert state['total_detections'] == 1


# ═══════════════════════════════════════════════════════════════════
# P5.63: Transfer Learning
# ═══════════════════════════════════════════════════════════════════

class TestDomainMapping:
    def test_record_outcome(self):
        dm = DomainMapping(
            source_domain="code_review", target_domain="testing",
            strategy="shell:review", source_success_rate=0.9,
        )
        dm.record_transfer_outcome(True)
        dm.record_transfer_outcome(True)
        dm.record_transfer_outcome(False)
        assert dm.transfer_attempts == 3
        assert dm.transfer_successes == 2
        assert dm.transfer_success_rate == pytest.approx(2/3, abs=0.01)


class TestTransferLearning:
    def test_discover_transfers(self):
        ers = ExperienceReplaySystem()
        for i in range(10):
            ers.record(Experience(
                situation=f"Review {i}", system="shell", action="review",
                params={}, outcome=OutcomeType.SUCCESS,
                duration_ms=1000, emotional_valence=0.0, emotional_arousal=0.0,
                domain="code_review",
            ))
        tl = TransferLearning(min_source_experiences=5)
        mappings = tl.discover_transfers(ers)
        assert len(mappings) > 0
        targets = [m.target_domain for m in mappings]
        # code_review maps to: config_validation, testing, documentation
        assert any(t in targets for t in ['config_validation', 'testing', 'documentation'])

    def test_suggest_strategy(self):
        tl = TransferLearning()
        tl._add_mapping(DomainMapping(
            source_domain="code_review", target_domain="testing",
            strategy="shell:review", source_success_rate=0.9,
            confidence=0.7,
        ))
        suggestions = tl.suggest_strategy("testing")
        assert len(suggestions) == 1
        assert suggestions[0].source_domain == "code_review"

    def test_record_transfer_outcome(self):
        tl = TransferLearning()
        tl._add_mapping(DomainMapping(
            source_domain="A", target_domain="B",
            strategy="s:a", source_success_rate=0.8,
        ))
        tl.record_transfer_outcome("A", "B", "s:a", True)
        assert tl._total_transfers == 1
        assert tl._successful_transfers == 1

    def test_get_state(self):
        tl = TransferLearning()
        state = tl.get_state()
        assert 'total_mappings' in state

    def test_from_yaml(self):
        cfg = {'transfer_learning': {'min_source_success_rate': 0.8}}
        tl = TransferLearning.from_yaml(cfg)
        assert tl.min_source_success_rate == 0.8


# ═══════════════════════════════════════════════════════════════════
# P5.64: Skill Library
# ═══════════════════════════════════════════════════════════════════

class TestAction:
    def test_to_from_dict(self):
        a = Action(system="shell", command="pytest", params={"verbose": True})
        d = a.to_dict()
        restored = Action.from_dict(d)
        assert restored.system == "shell"
        assert restored.command == "pytest"


class TestSkill:
    def test_record_outcome_transitions(self):
        s = Skill(name="test_skill", trigger_condition="test",
                  action_sequence=[], target_system="shell")
        assert s.status == SkillStatus.LEARNING
        for _ in range(5):
            s.record_outcome(True, 1000)
        assert s.status == SkillStatus.ACTIVE
        assert s.success_rate == 1.0

    def test_deprecation_on_low_success(self):
        s = Skill(name="bad_skill", trigger_condition="test",
                  action_sequence=[], target_system="shell")
        for _ in range(10):
            s.record_outcome(False, 1000)
        assert s.status == SkillStatus.DEPRECATED
        assert s.success_rate == 0.0

    def test_to_from_dict(self):
        s = Skill(name="deploy", trigger_condition="deployment",
                  action_sequence=[Action(system="shell", command="deploy")],
                  target_system="shell", domain="ops")
        d = s.to_dict()
        restored = Skill.from_dict(d)
        assert restored.name == "deploy"
        assert restored.domain == "ops"
        assert len(restored.action_sequence) == 1


class TestSkillLibrary:
    def test_register_and_get(self):
        lib = SkillLibrary(max_skills=100)
        s = Skill(name="test", trigger_condition="testing",
                  action_sequence=[], target_system="shell", domain="test")
        lib.register_skill(s)
        assert lib.get_skill("test") is not None

    def test_find_matching(self):
        lib = SkillLibrary()
        s = Skill(name="deploy", trigger_condition="deployment",
                  action_sequence=[], target_system="shell",
                  domain="ops", status=SkillStatus.ACTIVE, confidence=0.8)
        lib.register_skill(s)
        matches = lib.find_matching_skills(task_type="deployment", domain="ops")
        assert len(matches) == 1
        assert matches[0].name == "deploy"

    def test_record_execution(self):
        lib = SkillLibrary()
        s = Skill(name="test", trigger_condition="testing",
                  action_sequence=[], target_system="shell")
        lib.register_skill(s)
        lib.record_execution("test", True, 500)
        assert lib._total_executions == 1
        assert lib.get_skill("test").total_attempts == 1

    def test_max_capacity(self):
        lib = SkillLibrary(max_skills=3)
        for i in range(5):
            lib.register_skill(Skill(
                name=f"skill_{i}", trigger_condition="test",
                action_sequence=[], target_system="shell",
            ))
        assert len(lib._skills) <= 3

    def test_get_state(self):
        lib = SkillLibrary()
        state = lib.get_state()
        assert 'total_skills' in state

    def test_from_yaml(self):
        cfg = {'skill_library': {'max_skills': 200}}
        lib = SkillLibrary.from_yaml(cfg)
        assert lib.max_skills == 200


# ═══════════════════════════════════════════════════════════════════
# P5.65: Skill Composition
# ═══════════════════════════════════════════════════════════════════

class TestSkillComposition:
    def test_record_sequence(self):
        sc = SkillComposition()
        sc.record_skill_sequence(["test", "commit"])
        assert len(sc._sequence_buffer) == 1

    def test_discover_compositions(self):
        sc = SkillComposition(min_co_occurrences=3)
        lib = SkillLibrary()
        # Register skills
        for name in ["test", "commit"]:
            lib.register_skill(Skill(
                name=name, trigger_condition=name,
                action_sequence=[Action(system="shell", command=name)],
                target_system="shell", domain="dev",
                success_rate=0.9, total_attempts=10, total_successes=9,
                status=SkillStatus.ACTIVE,
            ))
        # Record sequences
        for _ in range(5):
            sc.record_skill_sequence(["test", "commit"])
        proposals = sc.discover_compositions(lib)
        assert len(proposals) >= 1
        assert "test+commit" == proposals[0]['name']

    def test_create_composite(self):
        sc = SkillComposition()
        s1 = Skill(name="test", trigger_condition="testing",
                    action_sequence=[Action(system="shell", command="pytest")],
                    target_system="shell", domain="dev")
        s2 = Skill(name="commit", trigger_condition="committing",
                    action_sequence=[Action(system="shell", command="git commit")],
                    target_system="shell", domain="dev")
        composite = sc.create_composite_skill("safe_commit", [s1, s2])
        assert composite.name == "safe_commit"
        assert len(composite.action_sequence) == 2
        assert "test" in composite.parent_skills


# ═══════════════════════════════════════════════════════════════════
# P5.66: Skill Refinement
# ═══════════════════════════════════════════════════════════════════

class TestABTest:
    def test_record_outcomes(self):
        ab = ABTest(original_name="a", variant_name="a_v1",
                    parameter_changes={"retry": 1}, min_samples=3)
        ab.record_outcome(False, True)   # original success
        ab.record_outcome(True, True)    # variant success
        ab.record_outcome(False, False)  # original failure
        ab.record_outcome(True, True)    # variant success
        assert ab.original_attempts == 2
        assert ab.variant_attempts == 2
        assert not ab.is_conclusive()  # need min_samples=3 each

    def test_conclusive_winner(self):
        ab = ABTest(original_name="a", variant_name="a_v1",
                    parameter_changes={}, min_samples=3)
        for _ in range(3):
            ab.record_outcome(False, True)   # original: all success
        for _ in range(3):
            ab.record_outcome(True, True)    # variant: all success
        assert ab.is_conclusive()
        winner = ab.get_winner()
        assert winner == "a"  # Variant didn't improve by >5%, original wins


class TestSkillRefinement:
    def test_check_deactivation(self):
        sr = SkillRefinement()
        lib = SkillLibrary()
        bad_skill = Skill(
            name="bad", trigger_condition="test",
            action_sequence=[], target_system="shell",
            total_attempts=15, total_successes=2,
            success_rate=2/15, status=SkillStatus.ACTIVE,
        )
        lib.register_skill(bad_skill)
        deactivated = sr.check_for_deactivation(lib)
        assert "bad" in deactivated
        assert lib.get_skill("bad").status == SkillStatus.DEPRECATED

    def test_propose_variant(self):
        sr = SkillRefinement()
        skill = Skill(
            name="deploy", trigger_condition="deployment",
            action_sequence=[Action(system="shell", command="deploy", retry_count=0)],
            target_system="shell",
            total_attempts=10, total_successes=6, success_rate=0.6,
        )
        result = sr.propose_variant(skill)
        assert result is not None
        variant, ab_test = result
        assert variant.variant_of == "deploy"
        assert len(sr._active_tests) == 1

    def test_resolve_tests(self):
        sr = SkillRefinement()
        lib = SkillLibrary()
        # Create original and variant
        original = Skill(name="orig", trigger_condition="t",
                         action_sequence=[], target_system="shell",
                         status=SkillStatus.ACTIVE)
        variant = Skill(name="orig_v10", trigger_condition="t",
                        action_sequence=[], target_system="shell",
                        variant_of="orig")
        lib.register_skill(original)
        lib.register_skill(variant)

        ab = ABTest(original_name="orig", variant_name="orig_v10",
                    parameter_changes={}, min_samples=3)
        sr._active_tests.append(ab)

        # Variant wins
        for _ in range(3):
            ab.record_outcome(False, False)  # original fails
        for _ in range(3):
            ab.record_outcome(True, True)    # variant wins

        resolved = sr.resolve_tests(lib)
        assert len(resolved) == 1
        assert resolved[0]['winner'] == "orig_v10"

    def test_get_state(self):
        sr = SkillRefinement()
        state = sr.get_state()
        assert 'active_tests' in state

"""
Tests for Motivation Drives (V2 Phase 3: P3.34-36)

Tests cover:
- CuriosityDrive: PE tracking, impulse generation, cooldowns
- CompetenceDrive: Skill profiles, ZPD detection, practice impulses
- HomeostaticDrives: State-to-impulse translation for all triggers
- MotivationSystem: Combined impulse generation, outcome recording
- DriveImpulse: Serialization, field ranges
"""

import time
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from core.motivation_drives import (
    DriveType,
    DriveImpulse,
    CuriosityDrive,
    CompetenceDrive,
    HomeostaticDrives,
    MotivationSystem,
    SkillProfile,
)


# ─── DriveImpulse Tests ─────────────────────────────────────────────────────

class TestDriveImpulse:
    def test_to_dict(self):
        impulse = DriveImpulse(
            drive_type=DriveType.CURIOSITY,
            description="Test impulse",
            urgency=0.7,
            importance=0.5,
            confidence=0.8,
            source_drive='curiosity',
            metadata={'key': 'value'},
        )
        d = impulse.to_dict()
        assert d['drive_type'] == 'curiosity'
        assert d['description'] == 'Test impulse'
        assert d['urgency'] == 0.7
        assert d['source_drive'] == 'curiosity'
        assert d['metadata'] == {'key': 'value'}

    def test_drive_types(self):
        """All drive types have string values."""
        for dt in DriveType:
            assert isinstance(dt.value, str)
            assert len(dt.value) > 0

    def test_default_values(self):
        impulse = DriveImpulse(drive_type=DriveType.EXPLORATION, description="test")
        assert impulse.urgency == 0.5
        assert impulse.importance == 0.5
        assert impulse.confidence == 0.5
        assert impulse.metadata == {}


# ─── CuriosityDrive Tests ──────────────────────────────────────────────────

class TestCuriosityDrive:
    def test_init_defaults(self):
        drive = CuriosityDrive()
        assert drive.exploration_threshold == 0.3
        assert drive.cooldown_seconds == 120.0

    def test_observe_prediction_error(self):
        drive = CuriosityDrive()
        drive.observe_prediction_error(0.5, domain='logic', task_description='test task')
        assert drive._total_observations == 1
        assert 'logic' in drive._domain_errors
        assert len(drive._domain_errors['logic']) == 1

    def test_observe_multiple_domains(self):
        drive = CuriosityDrive()
        drive.observe_prediction_error(0.3, domain='logic')
        drive.observe_prediction_error(0.7, domain='temporal')
        drive.observe_prediction_error(0.1, domain='logic')
        assert drive._total_observations == 3
        assert len(drive._domain_errors['logic']) == 2
        assert len(drive._domain_errors['temporal']) == 1

    def test_no_impulses_without_enough_data(self):
        drive = CuriosityDrive()
        # Too few observations for baseline
        drive.observe_prediction_error(0.5, domain='logic')
        impulses = drive.generate_impulses()
        assert len(impulses) == 0

    def test_generates_impulse_for_high_pe(self):
        drive = CuriosityDrive(
            exploration_threshold=0.2,
            cooldown_seconds=0,  # No cooldown for test
        )
        # Build baseline
        for _ in range(10):
            drive.observe_prediction_error(0.1, domain='baseline')
        # High PE domain
        for _ in range(10):
            drive.observe_prediction_error(0.8, domain='logic')

        impulses = drive.generate_impulses()
        assert len(impulses) >= 1
        logic_impulses = [i for i in impulses if i.metadata.get('domain') == 'logic']
        assert len(logic_impulses) == 1
        assert logic_impulses[0].drive_type == DriveType.CURIOSITY
        assert logic_impulses[0].urgency > 0

    def test_no_impulse_below_threshold(self):
        drive = CuriosityDrive(
            exploration_threshold=0.9,
            cooldown_seconds=0,
        )
        for _ in range(10):
            drive.observe_prediction_error(0.5, domain='logic')
        impulses = drive.generate_impulses()
        # 0.5 < 0.9 threshold → no impulse
        assert len(impulses) == 0

    def test_cooldown_prevents_repeat(self):
        drive = CuriosityDrive(
            exploration_threshold=0.2,
            cooldown_seconds=999,  # Very long cooldown
        )
        for _ in range(10):
            drive.observe_prediction_error(0.1, domain='baseline')
        for _ in range(10):
            drive.observe_prediction_error(0.8, domain='logic')

        # First call generates
        impulses1 = drive.generate_impulses()
        logic1 = [i for i in impulses1 if i.metadata.get('domain') == 'logic']
        assert len(logic1) == 1

        # Second call blocked by cooldown
        impulses2 = drive.generate_impulses()
        logic2 = [i for i in impulses2 if i.metadata.get('domain') == 'logic']
        assert len(logic2) == 0

    def test_get_state(self):
        drive = CuriosityDrive()
        for _ in range(5):
            drive.observe_prediction_error(0.5, domain='test')
        state = drive.get_state()
        assert state['name'] == 'CuriosityDrive'
        assert state['total_observations'] == 5
        assert 'test' in state['domains']
        assert 'global_pe_baseline' in state

    def test_impulse_urgency_bounded(self):
        drive = CuriosityDrive(
            exploration_threshold=0.1,
            cooldown_seconds=0,
        )
        for _ in range(10):
            drive.observe_prediction_error(0.05, domain='baseline')
        for _ in range(10):
            drive.observe_prediction_error(0.99, domain='extreme')

        impulses = drive.generate_impulses()
        for imp in impulses:
            assert 0 <= imp.urgency <= 1.0
            assert 0 <= imp.importance <= 1.0
            assert 0 <= imp.confidence <= 1.0


# ─── SkillProfile Tests ───────────────────────────────────────────────────

class TestSkillProfile:
    def test_initial_state(self):
        sp = SkillProfile(domain='test')
        assert sp.success_rate == 0.0
        assert sp.recent_success_rate == 0.0
        assert sp.learning_progress == 0.0

    def test_record_outcomes(self):
        sp = SkillProfile(domain='test')
        sp.record_outcome(True)
        sp.record_outcome(True)
        sp.record_outcome(False)
        assert sp.total_attempts == 3
        assert sp.total_successes == 2
        assert abs(sp.success_rate - 2/3) < 0.01

    def test_recent_success_rate(self):
        sp = SkillProfile(domain='test', max_recent=10)
        for _ in range(10):
            sp.record_outcome(True)
        assert sp.recent_success_rate == 1.0

        # Add failures
        for _ in range(5):
            sp.record_outcome(False)
        # Recent should reflect more failures (window of 10, last 10 are 5T+5F)
        assert sp.recent_success_rate < 1.0

    def test_learning_progress(self):
        sp = SkillProfile(domain='test', max_recent=20)
        # First half: all failures
        for _ in range(10):
            sp.record_outcome(False)
        # Second half: all successes
        for _ in range(10):
            sp.record_outcome(True)
        # Learning progress should be positive
        assert sp.learning_progress > 0

    def test_learning_progress_negative(self):
        sp = SkillProfile(domain='test', max_recent=20)
        # First half: all successes
        for _ in range(10):
            sp.record_outcome(True)
        # Second half: all failures
        for _ in range(10):
            sp.record_outcome(False)
        assert sp.learning_progress < 0

    def test_to_dict(self):
        sp = SkillProfile(domain='test')
        sp.record_outcome(True)
        d = sp.to_dict()
        assert d['domain'] == 'test'
        assert d['total_attempts'] == 1
        assert d['success_rate'] == 1.0

    def test_max_recent_truncation(self):
        sp = SkillProfile(domain='test', max_recent=5)
        for _ in range(20):
            sp.record_outcome(True)
        assert len(sp.recent_outcomes) == 5


# ─── CompetenceDrive Tests ────────────────────────────────────────────────

class TestCompetenceDrive:
    def test_init_defaults(self):
        drive = CompetenceDrive()
        assert drive.zpd_lower == 0.40
        assert drive.zpd_upper == 0.70
        assert drive.mastery_threshold == 0.95

    def test_record_outcome(self):
        drive = CompetenceDrive()
        drive.record_outcome('shell', True)
        drive.record_outcome('shell', False)
        assert drive._total_skill_updates == 2
        assert 'shell' in drive._skills
        assert drive._skills['shell'].total_attempts == 2

    def test_no_impulse_too_few_attempts(self):
        drive = CompetenceDrive(min_attempts_for_zpd=10)
        for _ in range(5):
            drive.record_outcome('shell', True)
        impulses = drive.generate_impulses()
        assert len(impulses) == 0  # Only 5 attempts, need 10

    def test_zpd_detection(self):
        drive = CompetenceDrive(min_attempts_for_zpd=5, cooldown_seconds=0)
        # Create domain with 50% success rate (in ZPD: 40-70%)
        for i in range(20):
            drive.record_outcome('docker', i % 2 == 0)  # 50% success

        zpd = drive.get_zpd_domains()
        assert len(zpd) >= 1
        docker_zpd = [z for z in zpd if z['domain'] == 'docker']
        assert len(docker_zpd) == 1
        assert abs(docker_zpd[0]['success_rate'] - 0.5) < 0.1

    def test_generates_impulse_for_zpd_domain(self):
        drive = CompetenceDrive(min_attempts_for_zpd=5, cooldown_seconds=0)
        # 60% success rate → in ZPD
        for i in range(20):
            drive.record_outcome('reasoning', i % 5 != 0)  # ~80% → too high

        # Let's make it exactly in ZPD range
        drive2 = CompetenceDrive(min_attempts_for_zpd=5, cooldown_seconds=0)
        for i in range(20):
            drive2.record_outcome('reasoning', i < 10)  # First 10 success, last 10 fail → 50%

        impulses = drive2.generate_impulses()
        assert len(impulses) >= 1
        assert impulses[0].drive_type == DriveType.COMPETENCE

    def test_mastered_skill_no_impulse(self):
        drive = CompetenceDrive(min_attempts_for_zpd=5, cooldown_seconds=0)
        # 100% success → mastered
        for _ in range(20):
            drive.record_outcome('simple_task', True)
        impulses = drive.generate_impulses()
        # Mastered skills should not generate impulses
        simple_impulses = [i for i in impulses if 'simple_task' in str(i.metadata)]
        assert len(simple_impulses) == 0

    def test_cooldown_prevents_repeat(self):
        drive = CompetenceDrive(min_attempts_for_zpd=5, cooldown_seconds=999)
        for i in range(20):
            drive.record_outcome('docker', i < 10)

        impulses1 = drive.generate_impulses()
        impulses2 = drive.generate_impulses()
        # Second call should be blocked by cooldown
        docker2 = [i for i in impulses2 if 'docker' in str(i.metadata)]
        assert len(docker2) == 0

    def test_max_3_impulses(self):
        drive = CompetenceDrive(min_attempts_for_zpd=5, cooldown_seconds=0)
        # Create many domains in ZPD
        for domain in ['a', 'b', 'c', 'd', 'e']:
            for i in range(20):
                drive.record_outcome(domain, i < 10)

        impulses = drive.generate_impulses()
        assert len(impulses) <= 3

    def test_get_state(self):
        drive = CompetenceDrive()
        drive.record_outcome('test', True)
        state = drive.get_state()
        assert state['name'] == 'CompetenceDrive'
        assert 'skills' in state
        assert 'test' in state['skills']
        assert 'config' in state


# ─── HomeostaticDrives Tests ─────────────────────────────────────────────

@dataclass
class MockHomeostaticState:
    energy: float = 1.0
    fatigue: float = 0.0
    sleep_pressure: float = 0.0
    allostatic_load: float = 0.0

@dataclass
class MockNeuromodLevels:
    dopamine: float = 0.5
    serotonin: float = 0.5
    norepinephrine: float = 0.5


class TestHomeostaticDrives:
    def test_init_defaults(self):
        drives = HomeostaticDrives()
        assert drives.sleep_pressure_threshold == 0.6
        assert drives.low_dopamine_threshold == 0.3

    def test_no_impulse_at_baseline(self):
        """Normal state should produce no impulses."""
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(energy=1.0, fatigue=0.0, sleep_pressure=0.0, allostatic_load=0.0)
        n = MockNeuromodLevels(dopamine=0.5, serotonin=0.5, norepinephrine=0.5)
        impulses = drives.generate_impulses(h, n)
        assert len(impulses) == 0

    def test_high_sleep_pressure_triggers_consolidation(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(sleep_pressure=0.8)
        n = MockNeuromodLevels()
        impulses = drives.generate_impulses(h, n)
        sleep_impulses = [i for i in impulses if i.metadata.get('trigger') == 'sleep_pressure']
        assert len(sleep_impulses) == 1
        assert sleep_impulses[0].drive_type == DriveType.CONSOLIDATION
        assert sleep_impulses[0].urgency >= 0.6

    def test_low_dopamine_triggers_exploration(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState()
        n = MockNeuromodLevels(dopamine=0.1)
        impulses = drives.generate_impulses(h, n)
        dopa_impulses = [i for i in impulses if i.metadata.get('trigger') == 'low_dopamine']
        assert len(dopa_impulses) == 1
        assert dopa_impulses[0].drive_type == DriveType.EXPLORATION

    def test_high_stress_triggers_routine(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(allostatic_load=0.7)
        n = MockNeuromodLevels()
        impulses = drives.generate_impulses(h, n)
        stress_impulses = [i for i in impulses if i.metadata.get('trigger') == 'high_stress']
        assert len(stress_impulses) == 1
        assert stress_impulses[0].drive_type == DriveType.HOMEOSTATIC

    def test_low_energy_triggers_rest(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(energy=0.1)
        n = MockNeuromodLevels()
        impulses = drives.generate_impulses(h, n)
        energy_impulses = [i for i in impulses if i.metadata.get('trigger') == 'low_energy']
        assert len(energy_impulses) == 1

    def test_high_fatigue_triggers_break(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(fatigue=0.9)
        n = MockNeuromodLevels()
        impulses = drives.generate_impulses(h, n)
        fatigue_impulses = [i for i in impulses if i.metadata.get('trigger') == 'high_fatigue']
        assert len(fatigue_impulses) == 1

    def test_information_hunger(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(energy=0.8, fatigue=0.2)  # Good condition
        n = MockNeuromodLevels(dopamine=0.2)  # But low dopamine
        impulses = drives.generate_impulses(h, n)
        hunger_impulses = [i for i in impulses if i.metadata.get('trigger') == 'information_hunger']
        assert len(hunger_impulses) == 1
        assert hunger_impulses[0].drive_type == DriveType.CURIOSITY

    def test_multiple_triggers_simultaneously(self):
        """Multiple conditions can trigger simultaneously."""
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(
            energy=0.1,
            fatigue=0.9,
            sleep_pressure=0.8,
            allostatic_load=0.7,
        )
        n = MockNeuromodLevels(dopamine=0.1)
        impulses = drives.generate_impulses(h, n)
        # Should have multiple impulses
        assert len(impulses) >= 3

    def test_impulses_sorted_by_urgency(self):
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(
            energy=0.1,
            fatigue=0.9,
            sleep_pressure=0.9,
        )
        n = MockNeuromodLevels(dopamine=0.1)
        impulses = drives.generate_impulses(h, n)
        # Should be sorted descending by urgency
        for i in range(len(impulses) - 1):
            assert impulses[i].urgency >= impulses[i + 1].urgency

    def test_cooldown_prevents_repeat(self):
        drives = HomeostaticDrives(cooldown_seconds=999)
        h = MockHomeostaticState(sleep_pressure=0.9)
        n = MockNeuromodLevels()

        impulses1 = drives.generate_impulses(h, n)
        assert len(impulses1) >= 1
        impulses2 = drives.generate_impulses(h, n)
        # Cooldown should block
        sleep2 = [i for i in impulses2 if i.metadata.get('trigger') == 'sleep_pressure']
        assert len(sleep2) == 0

    def test_dict_input(self):
        """Should accept dict instead of dataclass."""
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = {'energy': 0.1, 'fatigue': 0.0, 'sleep_pressure': 0.0, 'allostatic_load': 0.0}
        n = {'dopamine': 0.5, 'serotonin': 0.5, 'norepinephrine': 0.5}
        impulses = drives.generate_impulses(h, n)
        energy_impulses = [i for i in impulses if i.metadata.get('trigger') == 'low_energy']
        assert len(energy_impulses) == 1

    def test_none_inputs(self):
        """Should handle None gracefully (use defaults)."""
        drives = HomeostaticDrives(cooldown_seconds=0)
        impulses = drives.generate_impulses(None, None)
        assert len(impulses) == 0  # All at baseline

    def test_get_state(self):
        drives = HomeostaticDrives()
        state = drives.get_state()
        assert state['name'] == 'HomeostaticDrives'
        assert 'impulse_counts' in state
        assert 'config' in state

    def test_urgency_bounded(self):
        """All generated urgencies should be in [0, 1]."""
        drives = HomeostaticDrives(cooldown_seconds=0)
        h = MockHomeostaticState(
            energy=0.0,
            fatigue=1.0,
            sleep_pressure=1.0,
            allostatic_load=1.0,
        )
        n = MockNeuromodLevels(dopamine=0.0)
        impulses = drives.generate_impulses(h, n)
        for imp in impulses:
            assert 0 <= imp.urgency <= 1.0
            assert 0 <= imp.importance <= 1.0
            assert 0 <= imp.confidence <= 1.0


# ─── MotivationSystem Tests ──────────────────────────────────────────────

class TestMotivationSystem:
    def test_init_defaults(self):
        ms = MotivationSystem()
        assert ms.curiosity is not None
        assert ms.competence is not None
        assert ms.homeostatic is not None

    def test_generate_all_impulses_empty(self):
        ms = MotivationSystem()
        impulses = ms.generate_all_impulses()
        # No data → no impulses
        assert isinstance(impulses, list)

    def test_generate_all_impulses_with_homeostatic(self):
        ms = MotivationSystem(
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
        )
        h = MockHomeostaticState(sleep_pressure=0.9)
        n = MockNeuromodLevels()
        impulses = ms.generate_all_impulses(
            homeostatic_state=h,
            neuromodulator_levels=n,
        )
        assert len(impulses) >= 1

    def test_max_impulses_per_tick(self):
        ms = MotivationSystem(
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
            max_impulses_per_tick=2,
        )
        h = MockHomeostaticState(
            energy=0.1, fatigue=0.9, sleep_pressure=0.9, allostatic_load=0.9
        )
        n = MockNeuromodLevels(dopamine=0.1)
        impulses = ms.generate_all_impulses(h, n)
        assert len(impulses) <= 2

    def test_observe_task_outcome(self):
        ms = MotivationSystem()
        ms.observe_task_outcome(
            domain='logic',
            success=True,
            prediction_error=0.5,
            task_description='test task',
        )
        assert ms.curiosity._total_observations == 1
        assert ms.competence._total_skill_updates == 1

    def test_get_state(self):
        ms = MotivationSystem()
        state = ms.get_state()
        assert 'curiosity' in state
        assert 'competence' in state
        assert 'homeostatic' in state
        assert 'total_impulses_generated' in state

    def test_combined_sorted_output(self):
        """Impulses from all drives are sorted by urgency."""
        ms = MotivationSystem(
            curiosity_drive=CuriosityDrive(
                exploration_threshold=0.1, cooldown_seconds=0
            ),
            competence_drive=CompetenceDrive(
                min_attempts_for_zpd=5, cooldown_seconds=0
            ),
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
        )

        # Feed curiosity
        for _ in range(10):
            ms.curiosity.observe_prediction_error(0.1, 'baseline')
        for _ in range(10):
            ms.curiosity.observe_prediction_error(0.8, 'logic')

        # Feed competence
        for i in range(20):
            ms.competence.record_outcome('docker', i < 10)

        # Homeostatic trigger
        h = MockHomeostaticState(sleep_pressure=0.9)
        n = MockNeuromodLevels()

        impulses = ms.generate_all_impulses(h, n)
        assert len(impulses) >= 1

        # Check sorted by urgency descending
        for i in range(len(impulses) - 1):
            assert impulses[i].urgency >= impulses[i + 1].urgency

    def test_error_resilience(self):
        """System continues if one drive fails."""
        ms = MotivationSystem(
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
        )
        # Break curiosity drive
        ms.curiosity.generate_impulses = MagicMock(side_effect=RuntimeError("broken"))

        h = MockHomeostaticState(sleep_pressure=0.9)
        n = MockNeuromodLevels()
        # Should still get homeostatic impulses
        impulses = ms.generate_all_impulses(h, n)
        assert len(impulses) >= 1


# ─── Integration-style Tests ────────────────────────────────────────────

class TestDriveIntegration:
    def test_full_lifecycle(self):
        """Test a full observe→generate→observe cycle."""
        ms = MotivationSystem(
            curiosity_drive=CuriosityDrive(
                exploration_threshold=0.2, cooldown_seconds=0
            ),
            competence_drive=CompetenceDrive(
                min_attempts_for_zpd=3, cooldown_seconds=0
            ),
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
        )

        # Simulate several task outcomes
        for i in range(10):
            ms.observe_task_outcome(
                domain='code_analysis',
                success=i < 5,  # 50% success rate
                prediction_error=0.5 + 0.1 * i,
                task_description=f'task {i}',
            )

        # Generate impulses
        h = MockHomeostaticState(energy=0.5, fatigue=0.3, sleep_pressure=0.2)
        n = MockNeuromodLevels(dopamine=0.4)
        impulses = ms.generate_all_impulses(h, n)

        # Should have at least competence impulses (50% success rate = in ZPD)
        state = ms.get_state()
        assert state['curiosity']['total_observations'] == 10
        assert state['competence']['total_skill_updates'] == 10

    def test_all_impulses_serializable(self):
        """All impulses should be JSON-serializable via to_dict."""
        ms = MotivationSystem(
            curiosity_drive=CuriosityDrive(
                exploration_threshold=0.1, cooldown_seconds=0
            ),
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
        )
        for _ in range(10):
            ms.curiosity.observe_prediction_error(0.1, 'baseline')
        for _ in range(10):
            ms.curiosity.observe_prediction_error(0.8, 'logic')

        h = MockHomeostaticState(sleep_pressure=0.9, energy=0.1)
        n = MockNeuromodLevels(dopamine=0.1)
        impulses = ms.generate_all_impulses(h, n)

        for imp in impulses:
            d = imp.to_dict()
            assert isinstance(d, dict)
            assert isinstance(d['drive_type'], str)
            assert isinstance(d['urgency'], float)
            assert isinstance(d['description'], str)

    def test_drive_types_diverse(self):
        """Combined system should produce diverse drive types."""
        ms = MotivationSystem(
            curiosity_drive=CuriosityDrive(
                exploration_threshold=0.1, cooldown_seconds=0
            ),
            competence_drive=CompetenceDrive(
                min_attempts_for_zpd=3, cooldown_seconds=0
            ),
            homeostatic_drives=HomeostaticDrives(cooldown_seconds=0),
            max_impulses_per_tick=20,
        )

        # Feed curiosity
        for _ in range(10):
            ms.curiosity.observe_prediction_error(0.05, 'baseline')
        for _ in range(10):
            ms.curiosity.observe_prediction_error(0.9, 'logic')

        # Feed competence
        for i in range(10):
            ms.competence.record_outcome('docker', i < 5)

        h = MockHomeostaticState(sleep_pressure=0.9, energy=0.1)
        n = MockNeuromodLevels(dopamine=0.1)
        impulses = ms.generate_all_impulses(h, n)

        drive_types = {i.drive_type for i in impulses}
        # Should have at least 2 different types
        assert len(drive_types) >= 2


# ─── YAML Configuration Tests ────────────────────────────────────────────

class TestMotivationYAML:
    def test_from_yaml_with_full_config(self):
        """MotivationSystem.from_yaml loads all parameters."""
        cfg = {
            'motivation': {
                'curiosity_exploration_threshold': 0.5,
                'curiosity_cooldown_seconds': 60.0,
                'curiosity_novelty_weight': 0.7,
                'curiosity_surprise_weight': 0.3,
                'competence_zpd_lower': 0.30,
                'competence_zpd_upper': 0.80,
                'competence_mastery_threshold': 0.90,
                'competence_min_attempts': 10,
                'competence_cooldown_seconds': 300.0,
                'homeostatic_sleep_threshold': 0.5,
                'homeostatic_low_dopamine': 0.25,
                'homeostatic_high_stress': 0.6,
                'homeostatic_low_energy': 0.4,
                'homeostatic_high_fatigue': 0.8,
                'homeostatic_cooldown_seconds': 90.0,
                'max_impulses_per_tick': 3,
            }
        }
        ms = MotivationSystem.from_yaml(cfg)
        assert ms.curiosity.exploration_threshold == 0.5
        assert ms.curiosity.cooldown_seconds == 60.0
        assert ms.curiosity.novelty_weight == 0.7
        assert ms.competence.zpd_lower == 0.30
        assert ms.competence.zpd_upper == 0.80
        assert ms.competence.mastery_threshold == 0.90
        assert ms.competence.min_attempts == 10
        assert ms.homeostatic.sleep_pressure_threshold == 0.5
        assert ms.homeostatic.low_dopamine_threshold == 0.25
        assert ms.homeostatic.high_stress_threshold == 0.6
        assert ms.max_impulses_per_tick == 3

    def test_from_yaml_empty_config(self):
        """from_yaml with empty config uses defaults."""
        ms = MotivationSystem.from_yaml({})
        assert ms.curiosity.exploration_threshold == 0.3
        assert ms.competence.zpd_lower == 0.40
        assert ms.homeostatic.sleep_pressure_threshold == 0.6
        assert ms.max_impulses_per_tick == 5

    def test_from_yaml_partial_config(self):
        """from_yaml with partial config merges with defaults."""
        cfg = {
            'motivation': {
                'curiosity_exploration_threshold': 0.9,
                # Leave everything else at defaults
            }
        }
        ms = MotivationSystem.from_yaml(cfg)
        assert ms.curiosity.exploration_threshold == 0.9
        assert ms.curiosity.cooldown_seconds == 120.0  # default
        assert ms.competence.zpd_lower == 0.40  # default

    def test_from_yaml_functional(self):
        """from_yaml creates a functional system."""
        cfg = {
            'motivation': {
                'homeostatic_sleep_threshold': 0.5,
                'homeostatic_cooldown_seconds': 0,
            }
        }
        ms = MotivationSystem.from_yaml(cfg)
        h = MockHomeostaticState(sleep_pressure=0.6)
        n = MockNeuromodLevels()
        impulses = ms.generate_all_impulses(h, n)
        assert len(impulses) >= 1

"""
Unit tests for Homeostatic Regulation (core/homeostatic_regulation.py)

Tests cover:
- HomeostaticState defaults and to_dict
- HomeostaticConfig defaults and from_yaml
- Energy depletion on task processing
- Fatigue accumulation
- Allostatic load from failure stress
- Tick recovery (idle)
- Sleep pressure accumulation
- Dream mode recovery
- should_trigger_dream threshold
- Temperature adjustment for low energy/high fatigue
- Attention degradation
- Performance factor computation
- Circadian rhythm phase update
- Edge cases (extreme values, zero complexity)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from core.homeostatic_regulation import (
    HomeostaticRegulator,
    HomeostaticConfig,
    HomeostaticState,
)


class TestHomeostaticState:
    """Tests for the HomeostaticState dataclass."""

    def test_defaults(self):
        state = HomeostaticState()
        assert state.energy == 1.0
        assert state.fatigue == 0.0
        assert state.sleep_pressure == 0.0
        assert state.allostatic_load == 0.0
        assert state.performance_factor == 1.0
        assert state.tasks_since_rest == 0

    def test_to_dict(self):
        state = HomeostaticState(energy=0.7777, fatigue=0.3333)
        d = state.to_dict()
        assert d['energy'] == 0.778
        assert d['fatigue'] == 0.333
        assert 'tasks_since_rest' in d
        assert 'uptime_seconds' in d


class TestHomeostaticConfig:
    """Tests for HomeostaticConfig."""

    def test_defaults(self):
        config = HomeostaticConfig()
        assert config.energy_per_task == 0.02
        assert config.fatigue_per_task == 0.015
        assert config.sleep_threshold == 0.8
        assert config.low_energy_threshold == 0.3
        assert config.high_fatigue_threshold == 0.7

    def test_from_yaml(self):
        yaml = {
            'homeostatic': {
                'energy_per_task': 0.05,
                'sleep_threshold': 0.9,
            }
        }
        config = HomeostaticConfig.from_yaml(yaml)
        assert config.energy_per_task == 0.05
        assert config.sleep_threshold == 0.9
        # Unspecified fields keep defaults
        assert config.fatigue_per_task == 0.015

    def test_from_yaml_empty(self):
        config = HomeostaticConfig.from_yaml({})
        assert config.energy_per_task == 0.02  # Default


class TestEnergyDepletion:
    """Tests for energy depletion on task processing."""

    def test_energy_decreases_on_task(self):
        reg = HomeostaticRegulator()
        initial = reg.state.energy
        reg.on_task_processed(complexity=0.5)
        assert reg.state.energy < initial

    def test_complex_tasks_cost_more_energy(self):
        reg1 = HomeostaticRegulator()
        reg2 = HomeostaticRegulator()

        reg1.on_task_processed(complexity=0.2)
        reg2.on_task_processed(complexity=0.9)

        # More complex task should drain more energy
        assert reg2.state.energy < reg1.state.energy

    def test_energy_never_negative(self):
        reg = HomeostaticRegulator()
        for _ in range(200):
            reg.on_task_processed(complexity=1.0)
        assert reg.state.energy >= 0.0

    def test_task_counter_increments(self):
        reg = HomeostaticRegulator()
        for i in range(5):
            reg.on_task_processed()
        assert reg.state.tasks_since_rest == 5


class TestFatigue:
    """Tests for fatigue accumulation."""

    def test_fatigue_increases_on_task(self):
        reg = HomeostaticRegulator()
        reg.on_task_processed(complexity=0.5)
        assert reg.state.fatigue > 0.0

    def test_high_complexity_fatigues_more(self):
        config = HomeostaticConfig(fatigue_complexity_multiplier=2.0)
        reg = HomeostaticRegulator(config=config)
        reg.on_task_processed(complexity=0.8)
        fatigue_complex = reg.state.fatigue

        reg2 = HomeostaticRegulator(config=config)
        reg2.on_task_processed(complexity=0.3)

        assert fatigue_complex > reg2.state.fatigue

    def test_fatigue_capped_at_one(self):
        reg = HomeostaticRegulator()
        for _ in range(200):
            reg.on_task_processed(complexity=1.0)
        assert reg.state.fatigue <= 1.0


class TestAllostaticLoad:
    """Tests for stress/allostatic load."""

    def test_failure_increases_stress(self):
        reg = HomeostaticRegulator()
        reg.on_task_processed(success=False)
        assert reg.state.allostatic_load > 0.0

    def test_success_does_not_increase_stress(self):
        reg = HomeostaticRegulator()
        reg.on_task_processed(success=True)
        assert reg.state.allostatic_load == 0.0

    def test_stress_capped_at_one(self):
        reg = HomeostaticRegulator()
        for _ in range(200):
            reg.on_task_processed(success=False)
        assert reg.state.allostatic_load <= 1.0


class TestTickRecovery:
    """Tests for idle tick recovery."""

    def test_idle_tick_recovers_energy(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.5
        reg.tick(dt_seconds=30.0, is_idle=True)
        assert reg.state.energy > 0.5

    def test_idle_tick_reduces_fatigue(self):
        reg = HomeostaticRegulator()
        reg._state.fatigue = 0.5
        reg.tick(dt_seconds=30.0, is_idle=True)
        assert reg.state.fatigue < 0.5

    def test_idle_tick_reduces_allostatic_load(self):
        reg = HomeostaticRegulator()
        reg._state.allostatic_load = 0.5
        reg.tick(dt_seconds=30.0, is_idle=True)
        assert reg.state.allostatic_load < 0.5

    def test_active_tick_increases_allostatic_load(self):
        reg = HomeostaticRegulator()
        initial = reg.state.allostatic_load
        reg.tick(dt_seconds=30.0, is_idle=False)
        assert reg.state.allostatic_load >= initial


class TestSleepPressure:
    """Tests for sleep pressure and dream triggering."""

    def test_sleep_pressure_accumulates(self):
        reg = HomeostaticRegulator()
        for _ in range(10):
            reg.tick(dt_seconds=30.0, is_idle=True)
        assert reg.state.sleep_pressure > 0.0

    def test_should_trigger_dream_when_above_threshold(self):
        reg = HomeostaticRegulator()
        reg._state.sleep_pressure = 0.9
        assert reg.should_trigger_dream()

    def test_should_not_trigger_dream_when_below(self):
        reg = HomeostaticRegulator()
        reg._state.sleep_pressure = 0.3
        assert not reg.should_trigger_dream()


class TestDreamMode:
    """Tests for dream mode recovery."""

    def test_dream_recovers_energy(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.3
        reg.on_dream_mode()
        assert reg.state.energy > 0.3

    def test_dream_reduces_sleep_pressure(self):
        reg = HomeostaticRegulator()
        reg._state.sleep_pressure = 0.9
        reg.on_dream_mode()
        assert reg.state.sleep_pressure < 0.9

    def test_dream_reduces_fatigue(self):
        reg = HomeostaticRegulator()
        reg._state.fatigue = 0.8
        reg.on_dream_mode()
        assert reg.state.fatigue < 0.8

    def test_dream_resets_task_counter(self):
        reg = HomeostaticRegulator()
        reg._state.tasks_since_rest = 50
        reg.on_dream_mode()
        assert reg.state.tasks_since_rest == 0


class TestTemperatureAdjustment:
    """Tests for gating temperature modulation."""

    def test_full_energy_no_adjustment(self):
        reg = HomeostaticRegulator()
        assert reg.get_temperature_adjustment() == 0.0

    def test_low_energy_increases_temperature(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.1
        adj = reg.get_temperature_adjustment()
        assert adj > 0.0

    def test_high_fatigue_increases_temperature(self):
        reg = HomeostaticRegulator()
        reg._state.fatigue = 0.9
        adj = reg.get_temperature_adjustment()
        assert adj > 0.0

    def test_both_low_energy_and_high_fatigue(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.1
        reg._state.fatigue = 0.9
        adj = reg.get_temperature_adjustment()
        # Should be larger than either alone
        reg2 = HomeostaticRegulator()
        reg2._state.energy = 0.1
        assert adj > reg2.get_temperature_adjustment()


class TestAttentionDegradation:
    """Tests for attention degradation."""

    def test_fresh_attention_near_one(self):
        reg = HomeostaticRegulator()
        factor = reg.get_attention_degradation()
        assert 0.9 <= factor <= 1.0

    def test_exhausted_attention_below_one(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.1
        reg._state.fatigue = 0.9
        reg._update_performance_factor()
        factor = reg.get_attention_degradation()
        assert factor < 0.8

    def test_attention_bounded(self):
        reg = HomeostaticRegulator()
        # Even at worst state
        reg._state.energy = 0.0
        reg._state.fatigue = 1.0
        reg._state.allostatic_load = 1.0
        reg._update_performance_factor()
        factor = reg.get_attention_degradation()
        assert 0.3 <= factor <= 1.0


class TestPerformanceFactor:
    """Tests for performance factor computation."""

    def test_fresh_performance_is_one(self):
        reg = HomeostaticRegulator()
        assert reg.state.performance_factor == 1.0

    def test_low_energy_degrades_performance(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.2
        reg._update_performance_factor()
        assert reg.state.performance_factor < 1.0

    def test_high_fatigue_degrades_performance(self):
        reg = HomeostaticRegulator()
        reg._state.fatigue = 0.8
        reg._update_performance_factor()
        assert reg.state.performance_factor < 1.0

    def test_performance_floor(self):
        reg = HomeostaticRegulator()
        reg._state.energy = 0.0
        reg._state.fatigue = 1.0
        reg._state.allostatic_load = 1.0
        reg._update_performance_factor()
        assert reg.state.performance_factor >= 0.2


class TestCircadianRhythm:
    """Tests for circadian phase."""

    def test_phase_updates_on_tick(self):
        reg = HomeostaticRegulator()
        reg.tick(dt_seconds=30.0, is_idle=True)
        # Phase should have been updated based on uptime
        assert reg.state.circadian_phase >= 0.0
        assert reg.state.circadian_phase < 2 * np.pi


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_zero_complexity_task(self):
        reg = HomeostaticRegulator()
        reg.on_task_processed(complexity=0.0)
        # Should still deplete some energy
        assert reg.state.energy < 1.0

    def test_max_complexity_task(self):
        reg = HomeostaticRegulator()
        reg.on_task_processed(complexity=1.0)
        assert reg.state.energy < 1.0
        assert reg.state.fatigue > 0.0

    def test_many_sequential_tasks(self):
        reg = HomeostaticRegulator()
        for _ in range(100):
            reg.on_task_processed(complexity=0.5, success=True)
        # Energy should be significantly depleted
        assert reg.state.energy < 0.5
        assert reg.state.fatigue > 0.5

    def test_full_lifecycle(self):
        """Full work → exhaust → dream → recover cycle."""
        reg = HomeostaticRegulator()
        # Work until low energy
        for _ in range(30):
            reg.on_task_processed(complexity=0.7)
        assert reg.state.energy < 0.5
        # Dream mode recovery
        reg.on_dream_mode()
        recovered_energy = reg.state.energy
        assert recovered_energy >= 0.3  # Partial recovery
        # More work
        for _ in range(10):
            reg.on_task_processed(complexity=0.3)
        assert reg.state.energy < recovered_energy


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

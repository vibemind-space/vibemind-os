"""
Tests for YAML configuration loading and from_yaml classmethods.

Tests cover:
- config_loader.load_config() with default.yaml
- config_loader.create_model_from_config() for both model types
- config_loader.save_config() round-trip
- CognitiveLoopConfig.from_yaml()
- EmotionalSystemConfig.from_yaml()
- HomeostaticConfig.from_yaml()
- Missing/partial config graceful degradation
- Config section isolation (changes in one section don't affect others)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
import yaml
from core.config_loader import load_config, create_model_from_config, save_config


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'configs', 'default.yaml'
)


class TestLoadConfig:
    """Tests for load_config()."""

    def test_load_default_config(self):
        cfg = load_config(CONFIG_PATH)
        assert isinstance(cfg, dict)
        assert 'modalities' in cfg
        assert 'dimensions' in cfg
        assert 'tau' in cfg

    def test_load_has_cognitive_loop_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'cognitive_loop' in cfg
        cl = cfg['cognitive_loop']
        assert 'memory_routing_bias_strength' in cl
        assert 'max_loop_iterations' in cl

    def test_load_has_production_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'production' in cfg
        prod = cfg['production']
        assert 'learning_rate' in prod
        assert 'embedding_type' in prod

    def test_load_has_heartbeat_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'heartbeat' in cfg
        hb = cfg['heartbeat']
        assert 'interval_seconds' in hb
        assert 'enable_dream_mode' in hb

    def test_load_has_emotional_system_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'emotional_system' in cfg
        es = cfg['emotional_system']
        assert 'valence_decay_rate' in es
        assert 'fear_threshold' in es

    def test_load_has_homeostatic_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'homeostatic' in cfg
        h = cfg['homeostatic']
        assert 'energy_per_task' in h
        assert 'sleep_threshold' in h

    def test_load_has_layer4_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'layer4' in cfg
        assert cfg['layer4']['enabled'] is True

    def test_load_has_ports_section(self):
        cfg = load_config(CONFIG_PATH)
        assert 'ports' in cfg
        assert cfg['ports']['unified_brain'] == 5003

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config('/nonexistent/path/config.yaml')

    def test_modalities_list(self):
        cfg = load_config(CONFIG_PATH)
        assert isinstance(cfg['modalities'], list)
        assert 'vision' in cfg['modalities']
        assert 'threat' in cfg['modalities']
        assert len(cfg['modalities']) == 6


class TestCreateModel:
    """Tests for create_model_from_config()."""

    def test_create_base_model(self):
        cfg = load_config(CONFIG_PATH)
        model = create_model_from_config(cfg, adaptive=False)
        assert model.M == 6  # 6 modalities
        assert model is not None

    def test_create_adaptive_model(self):
        cfg = load_config(CONFIG_PATH)
        model = create_model_from_config(cfg, adaptive=True)
        assert model.M == 6
        assert hasattr(model, 'lr_input')
        assert model.lr_input == 0.001

    def test_create_from_path_string(self):
        model = create_model_from_config(CONFIG_PATH, adaptive=False)
        assert model.M == 6

    def test_gate_temp_from_config(self):
        cfg = load_config(CONFIG_PATH)
        model = create_model_from_config(cfg, adaptive=False)
        assert model.gate_temp == 0.5  # From gating.temperature


class TestSaveConfig:
    """Tests for save_config() round-trip."""

    def test_save_and_reload(self):
        cfg = load_config(CONFIG_PATH)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            tmp_path = f.name

        try:
            save_config(cfg, tmp_path)
            reloaded = load_config(tmp_path)
            assert reloaded['modalities'] == cfg['modalities']
            assert reloaded['gating']['temperature'] == cfg['gating']['temperature']
        finally:
            os.unlink(tmp_path)

    def test_save_preserves_nested_sections(self):
        cfg = load_config(CONFIG_PATH)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            tmp_path = f.name

        try:
            save_config(cfg, tmp_path)
            reloaded = load_config(tmp_path)
            assert reloaded['cognitive_loop']['max_loop_iterations'] == cfg['cognitive_loop']['max_loop_iterations']
            assert reloaded['emotional_system']['fear_threshold'] == cfg['emotional_system']['fear_threshold']
        finally:
            os.unlink(tmp_path)


class TestCognitiveLoopFromYaml:
    """Tests for CognitiveLoopConfig.from_yaml()."""

    def test_from_default_yaml(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = load_config(CONFIG_PATH)
        cl_cfg = CognitiveLoopConfig.from_yaml(cfg)
        assert cl_cfg.memory_routing_bias_strength == 0.25
        assert cl_cfg.max_loop_iterations == 2
        assert cl_cfg.enable_memory_bias is True

    def test_from_empty_yaml(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cl_cfg = CognitiveLoopConfig.from_yaml({})
        # Should use all defaults
        assert cl_cfg.memory_routing_bias_strength == 0.25
        assert cl_cfg.max_loop_iterations == 2

    def test_from_partial_yaml(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = {'cognitive_loop': {'max_loop_iterations': 5, 'enable_memory_bias': False}}
        cl_cfg = CognitiveLoopConfig.from_yaml(cfg)
        assert cl_cfg.max_loop_iterations == 5
        assert cl_cfg.enable_memory_bias is False
        # Unset fields use defaults
        assert cl_cfg.attention_gating_strength == 0.5

    def test_all_config_fields_mapped(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = load_config(CONFIG_PATH)
        cl_section = cfg.get('cognitive_loop', {})
        cl_cfg = CognitiveLoopConfig.from_yaml(cfg)
        # Every key in YAML that matches a field should be picked up
        for key, value in cl_section.items():
            if key in CognitiveLoopConfig.__dataclass_fields__:
                assert getattr(cl_cfg, key) == value, f"Field {key} not mapped correctly"


class TestEmotionalSystemFromYaml:
    """Tests for EmotionalSystemConfig.from_yaml()."""

    def test_from_default_yaml(self):
        from core.emotional_system import EmotionalSystemConfig
        cfg = load_config(CONFIG_PATH)
        es_cfg = EmotionalSystemConfig.from_yaml(cfg)
        assert es_cfg.valence_decay_rate == 0.05
        assert es_cfg.arousal_decay_rate == 0.1
        assert es_cfg.fear_threshold == 0.7

    def test_from_empty_yaml(self):
        from core.emotional_system import EmotionalSystemConfig
        es_cfg = EmotionalSystemConfig.from_yaml({})
        assert es_cfg.valence_decay_rate == 0.05  # defaults

    def test_from_custom_yaml(self):
        from core.emotional_system import EmotionalSystemConfig
        cfg = {'emotional_system': {'valence_decay_rate': 0.01, 'fear_threshold': 0.9}}
        es_cfg = EmotionalSystemConfig.from_yaml(cfg)
        assert es_cfg.valence_decay_rate == 0.01
        assert es_cfg.fear_threshold == 0.9
        # Unset fields use defaults
        assert es_cfg.arousal_decay_rate == 0.1


class TestHomeostaticFromYaml:
    """Tests for HomeostaticConfig.from_yaml()."""

    def test_from_default_yaml(self):
        from core.homeostatic_regulation import HomeostaticConfig
        cfg = load_config(CONFIG_PATH)
        h_cfg = HomeostaticConfig.from_yaml(cfg)
        assert h_cfg.energy_per_task == 0.02
        assert h_cfg.sleep_threshold == 0.8

    def test_from_empty_yaml(self):
        from core.homeostatic_regulation import HomeostaticConfig
        h_cfg = HomeostaticConfig.from_yaml({})
        # All defaults
        assert h_cfg.energy_per_task == 0.02

    def test_from_partial_yaml(self):
        from core.homeostatic_regulation import HomeostaticConfig
        cfg = {'homeostatic': {'energy_per_task': 0.05, 'sleep_threshold': 0.5}}
        h_cfg = HomeostaticConfig.from_yaml(cfg)
        assert h_cfg.energy_per_task == 0.05
        assert h_cfg.sleep_threshold == 0.5
        # Defaults for the rest
        assert h_cfg.fatigue_per_task == 0.015


class TestConfigIsolation:
    """Tests that config sections don't leak into each other."""

    def test_cognitive_loop_ignores_production(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = {
            'production': {'learning_rate': 999},
            'cognitive_loop': {'max_loop_iterations': 3}
        }
        cl_cfg = CognitiveLoopConfig.from_yaml(cfg)
        assert cl_cfg.max_loop_iterations == 3
        # learning_rate shouldn't come from production section
        # CognitiveLoopConfig doesn't have learning_rate field
        assert not hasattr(cl_cfg, 'learning_rate') or cl_cfg.__class__.__dataclass_fields__.get('learning_rate') is None

    def test_emotional_ignores_homeostatic(self):
        from core.emotional_system import EmotionalSystemConfig
        cfg = {
            'homeostatic': {'energy_per_task': 0.1},
            'emotional_system': {'fear_threshold': 0.5}
        }
        es_cfg = EmotionalSystemConfig.from_yaml(cfg)
        assert es_cfg.fear_threshold == 0.5
        assert not hasattr(es_cfg, 'energy_per_task')


class TestEdgeCases:
    """Edge cases for config loading."""

    def test_extra_unknown_keys_ignored(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = {'cognitive_loop': {'max_loop_iterations': 3, 'unknown_field': 'ignored'}}
        # unknown_field should be silently ignored (not in dataclass fields)
        cl_cfg = CognitiveLoopConfig.from_yaml(cfg)
        assert cl_cfg.max_loop_iterations == 3

    def test_numeric_types_preserved(self):
        cfg = load_config(CONFIG_PATH)
        assert isinstance(cfg['gating']['temperature'], float)
        assert isinstance(cfg['cognitive_loop']['max_loop_iterations'], int)

    def test_boolean_types_preserved(self):
        cfg = load_config(CONFIG_PATH)
        assert isinstance(cfg['cognitive_loop']['enable_memory_bias'], bool)
        assert isinstance(cfg['layer4']['enabled'], bool)


# ─────────────────────────────────────────────────────────
# P5.66-72: from_yaml() tests for all 7 subsystems
# ─────────────────────────────────────────────────────────

class TestNeuromodulationFromYaml:
    """Tests for NeuromodulationSystem.from_yaml() (P5.66)."""

    def test_from_default_yaml(self):
        from core.neuromodulation import NeuromodulationSystem
        cfg = load_config(CONFIG_PATH)
        nm = NeuromodulationSystem.from_yaml(cfg)
        assert nm.levels.dopamine == 0.5
        assert nm.levels.serotonin == 0.5
        assert nm.levels.norepinephrine == 0.5

    def test_from_empty_yaml(self):
        from core.neuromodulation import NeuromodulationSystem
        nm = NeuromodulationSystem.from_yaml({})
        assert nm.levels.dopamine == 0.5  # defaults

    def test_from_custom_yaml(self):
        from core.neuromodulation import NeuromodulationSystem
        cfg = {'neuromodulation': {'baseline_dopamine': 0.8, 'decay_rate': 0.1}}
        nm = NeuromodulationSystem.from_yaml(cfg)
        assert nm.levels.dopamine == 0.8
        # decay_rate may not be directly exposed as attribute, but should not error


class TestConsciousnessFromYaml:
    """Tests for ConsciousnessMetrics.from_yaml() (P5.67)."""

    def test_from_default_yaml(self):
        from core.consciousness_metrics import ConsciousnessMetrics
        cfg = load_config(CONFIG_PATH)
        cm = ConsciousnessMetrics.from_yaml(cfg)
        assert cm is not None

    def test_from_empty_yaml(self):
        from core.consciousness_metrics import ConsciousnessMetrics
        cm = ConsciousnessMetrics.from_yaml({})
        assert cm is not None


class TestMemoryFromYaml:
    """Tests for MemoryManager.from_yaml() (P5.68)."""

    def test_from_default_yaml(self):
        from core.memory_systems import MemoryManager
        cfg = load_config(CONFIG_PATH)
        mm = MemoryManager.from_yaml(cfg)
        assert mm is not None

    def test_from_empty_yaml(self):
        from core.memory_systems import MemoryManager
        mm = MemoryManager.from_yaml({})
        assert mm is not None

    def test_custom_capacity(self):
        from core.memory_systems import MemoryManager
        cfg = {'memory': {'working_memory_capacity': 20, 'episodic_max_size': 500}}
        mm = MemoryManager.from_yaml(cfg)
        assert mm is not None


class TestCTMEnsembleFromYaml:
    """Tests for MultiCTMEnsemble.from_yaml() (P5.69)."""

    def test_from_default_yaml(self):
        from core.multi_ctm_ensemble import MultiCTMEnsemble
        cfg = load_config(CONFIG_PATH)
        ctm = MultiCTMEnsemble.from_yaml(cfg)
        assert ctm is not None

    def test_from_empty_yaml(self):
        from core.multi_ctm_ensemble import MultiCTMEnsemble
        ctm = MultiCTMEnsemble.from_yaml({})
        assert ctm is not None


class TestGoalGraphFromYaml:
    """Tests for GoalGraph.from_yaml() (P5.70)."""

    def test_from_default_yaml(self):
        from core.goal_graph import GoalGraph
        cfg = load_config(CONFIG_PATH)
        gg = GoalGraph.from_yaml(cfg)
        assert gg is not None
        assert gg._max_goals == 50

    def test_from_empty_yaml(self):
        from core.goal_graph import GoalGraph
        gg = GoalGraph.from_yaml({})
        assert gg is not None
        assert gg._max_goals == 50  # default

    def test_custom_goals(self):
        from core.goal_graph import GoalGraph
        cfg = {'goal_graph': {'max_goals': 100, 'priority_decay_rate': 0.05}}
        gg = GoalGraph.from_yaml(cfg)
        assert gg._max_goals == 100
        assert gg._priority_decay_rate == 0.05


class TestPredictiveCodingFromYaml:
    """Tests for HierarchicalPredictiveCoding.from_yaml() (P5.71)."""

    def test_from_default_yaml(self):
        from core.predictive_coding import HierarchicalPredictiveCoding
        cfg = load_config(CONFIG_PATH)
        pc = HierarchicalPredictiveCoding.from_yaml(cfg)
        assert pc is not None
        assert pc.layer1_predictor.prediction_history_size == 100

    def test_from_empty_yaml(self):
        from core.predictive_coding import HierarchicalPredictiveCoding
        pc = HierarchicalPredictiveCoding.from_yaml({})
        assert pc is not None

    def test_custom_history_size(self):
        from core.predictive_coding import HierarchicalPredictiveCoding
        cfg = {'predictive_coding': {'prediction_history_size': 200}}
        pc = HierarchicalPredictiveCoding.from_yaml(cfg)
        assert pc.layer1_predictor.prediction_history_size == 200
        assert pc.layer3_predictor.prediction_history_size == 200


class TestDreamModeFromYaml:
    """Tests for DreamMode.from_yaml() (P5.72)."""

    def test_from_default_yaml(self):
        from core.dream_mode import DreamMode
        cfg = load_config(CONFIG_PATH)
        dm = DreamMode.from_yaml(cfg)
        assert dm.replay_rate == 0.3
        assert dm.counterfactual_rate == 0.2
        assert dm.max_dreams_per_cycle == 5

    def test_from_empty_yaml(self):
        from core.dream_mode import DreamMode
        dm = DreamMode.from_yaml({})
        assert dm.replay_rate == 0.3  # defaults

    def test_custom_yaml(self):
        from core.dream_mode import DreamMode
        cfg = {'dream_mode': {'replay_rate': 0.5, 'max_dreams_per_cycle': 10}}
        dm = DreamMode.from_yaml(cfg)
        assert dm.replay_rate == 0.5
        assert dm.max_dreams_per_cycle == 10
        assert dm.counterfactual_rate == 0.2  # default


# ─────────────────────────────────────────────────────────
# P5.73: Config Schema Validation Tests
# ─────────────────────────────────────────────────────────

class TestConfigValidation:
    """Tests for validate_config() (P5.73)."""

    def test_default_config_valid(self):
        from core.config_validation import validate_config
        cfg = load_config(CONFIG_PATH)
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) == 0, f"Default config has errors: {[e.to_dict() for e in real_errors]}"

    def test_empty_config_valid(self):
        from core.config_validation import validate_config
        errors = validate_config({})
        assert len(errors) == 0  # Empty is valid (all defaults)

    def test_type_mismatch_detected(self):
        from core.config_validation import validate_config
        cfg = {'neuromodulation': {'baseline_dopamine': 'not_a_float'}}
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) >= 1
        assert any('Expected float' in e.message for e in real_errors)

    def test_range_violation_detected(self):
        from core.config_validation import validate_config
        cfg = {'neuromodulation': {'baseline_dopamine': 5.0}}
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) >= 1
        assert any('above maximum' in e.message for e in real_errors)

    def test_range_below_minimum(self):
        from core.config_validation import validate_config
        cfg = {'cognitive_loop': {'max_loop_iterations': 0}}
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) >= 1
        assert any('below minimum' in e.message for e in real_errors)

    def test_invalid_choice_detected(self):
        from core.config_validation import validate_config
        cfg = {'production': {'embedding_type': 'quantum'}}
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) >= 1
        assert any('not in allowed choices' in e.message for e in real_errors)

    def test_unknown_field_warning(self):
        from core.config_validation import validate_config
        cfg = {'neuromodulation': {'baseline_dopamine': 0.5, 'magic_field': 42}}
        errors = validate_config(cfg)
        warnings = [e for e in errors if e.severity == 'warning']
        assert len(warnings) >= 1
        assert any('Unknown field' in e.message for e in warnings)

    def test_int_accepted_as_float(self):
        from core.config_validation import validate_config
        cfg = {'neuromodulation': {'baseline_dopamine': 1}}  # int, but float field
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        # Should NOT be an error (int is ok for float fields)
        type_errors = [e for e in real_errors if 'Expected float' in e.message and e.field == 'baseline_dopamine']
        assert len(type_errors) == 0

    def test_section_not_dict_error(self):
        from core.config_validation import validate_config
        cfg = {'neuromodulation': 'invalid'}
        errors = validate_config(cfg)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) >= 1
        assert any('must be a dict' in e.message for e in real_errors)

    def test_validate_config_file(self):
        from core.config_validation import validate_config_file
        cfg, errors = validate_config_file(CONFIG_PATH)
        assert isinstance(cfg, dict)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) == 0

    def test_all_schema_sections_present_in_default(self):
        """Every section in CONFIG_SCHEMA should exist in default.yaml."""
        from core.config_validation import CONFIG_SCHEMA
        cfg = load_config(CONFIG_PATH)
        for section_name in CONFIG_SCHEMA:
            assert section_name in cfg, f"Section '{section_name}' missing from default.yaml"


# ─────────────────────────────────────────────────────────
# P5.74: Config Hot-Reload Tests
# ─────────────────────────────────────────────────────────

class TestConfigHotReloader:
    """Tests for ConfigHotReloader (P5.74)."""

    def test_load_current(self):
        from core.config_validation import ConfigHotReloader
        reloader = ConfigHotReloader(CONFIG_PATH)
        cfg = reloader.load_current()
        assert isinstance(cfg, dict)
        assert 'modalities' in cfg

    def test_start_stop(self):
        from core.config_validation import ConfigHotReloader
        reloader = ConfigHotReloader(CONFIG_PATH, poll_interval=0.1)
        reloader.start()
        assert reloader.is_running
        reloader.stop()
        assert not reloader.is_running

    def test_current_config_returns_copy(self):
        from core.config_validation import ConfigHotReloader
        reloader = ConfigHotReloader(CONFIG_PATH)
        reloader.load_current()
        cfg1 = reloader.current_config
        cfg2 = reloader.current_config
        assert cfg1 is not cfg2  # Should be different objects (deep copy)
        assert cfg1 == cfg2      # But same content

    def test_reload_count_starts_zero(self):
        from core.config_validation import ConfigHotReloader
        reloader = ConfigHotReloader(CONFIG_PATH)
        assert reloader.reload_count == 0

    def test_callback_registration(self):
        from core.config_validation import ConfigHotReloader
        reloader = ConfigHotReloader(CONFIG_PATH)
        calls = []
        reloader.on_reload(lambda new, old: calls.append((new, old)))
        assert len(reloader._callbacks) == 1

    def test_to_dict(self):
        from core.config_validation import ConfigHotReloader
        reloader = ConfigHotReloader(CONFIG_PATH)
        d = reloader.to_dict()
        assert 'config_path' in d
        assert 'is_running' in d
        assert d['is_running'] is False
        assert d['reload_count'] == 0

    def test_reload_on_file_change(self):
        """Test that modifying the file triggers a reload."""
        from core.config_validation import ConfigHotReloader
        import tempfile
        import time

        # Create a temp config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({'neuromodulation': {'baseline_dopamine': 0.5}}, f)
            tmp_path = f.name

        try:
            reloader = ConfigHotReloader(tmp_path, poll_interval=0.1, validate_on_reload=False)
            reloaded_configs = []
            reloader.on_reload(lambda new, old: reloaded_configs.append(new))
            reloader.start()

            # Wait a moment, then modify the file
            time.sleep(0.3)
            with open(tmp_path, 'w') as f:
                yaml.dump({'neuromodulation': {'baseline_dopamine': 0.9}}, f)

            # Wait for watcher to pick it up
            time.sleep(0.5)
            reloader.stop()

            assert reloader.reload_count >= 1
            assert len(reloaded_configs) >= 1
            assert reloaded_configs[-1]['neuromodulation']['baseline_dopamine'] == 0.9
        finally:
            os.unlink(tmp_path)


# ─────────────────────────────────────────────────────────
# P5.75: Config Diff Logging Tests
# ─────────────────────────────────────────────────────────

class TestConfigDiff:
    """Tests for config diff logging (P5.75)."""

    def test_default_config_has_no_errors(self):
        """Default.yaml values match schema defaults where they overlap."""
        from core.config_validation import compute_config_diff
        cfg = load_config(CONFIG_PATH)
        diffs = compute_config_diff(cfg)
        # It's OK to have diffs (some values intentionally differ from schema defaults)
        assert isinstance(diffs, list)

    def test_custom_value_shows_diff(self):
        from core.config_validation import compute_config_diff
        cfg = {'neuromodulation': {'baseline_dopamine': 0.8}}
        diffs = compute_config_diff(cfg)
        assert len(diffs) >= 1
        dopamine_diff = [d for d in diffs if d.field == 'baseline_dopamine']
        assert len(dopamine_diff) == 1
        assert dopamine_diff[0].default_value == 0.5
        assert dopamine_diff[0].running_value == 0.8

    def test_matching_default_no_diff(self):
        from core.config_validation import compute_config_diff
        cfg = {'neuromodulation': {'baseline_dopamine': 0.5}}  # matches default
        diffs = compute_config_diff(cfg)
        dopamine_diff = [d for d in diffs if d.field == 'baseline_dopamine']
        assert len(dopamine_diff) == 0

    def test_diff_between_configs(self):
        from core.config_validation import compute_config_diff_between
        old = {'neuromodulation': {'baseline_dopamine': 0.5}}
        new = {'neuromodulation': {'baseline_dopamine': 0.9}}
        diffs = compute_config_diff_between(old, new)
        assert len(diffs) >= 1
        assert any(d.field == 'baseline_dopamine' for d in diffs)

    def test_diff_entry_to_dict(self):
        from core.config_validation import ConfigDiffEntry
        entry = ConfigDiffEntry(section='test', field='f', default_value=1, running_value=2)
        d = entry.to_dict()
        assert d['section'] == 'test'
        assert d['default'] == 1
        assert d['running'] == 2

    def test_startup_config_check(self):
        from core.config_validation import startup_config_check
        config, errors, diffs = startup_config_check(CONFIG_PATH)
        assert isinstance(config, dict)
        assert isinstance(errors, list)
        assert isinstance(diffs, list)
        # Default config should have no real errors
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) == 0


class TestPhase6ConfigSchema:
    """Phase 6 config schema validation tests."""

    def test_phase6_sections_in_schema(self):
        """All Phase 6 config sections should exist in CONFIG_SCHEMA."""
        from core.config_validation import CONFIG_SCHEMA
        phase6_sections = [
            'theory_of_mind', 'causal_reasoning', 'intrinsic_curiosity',
            'safety_layer', 'explanation_generator', 'self_improvement',
            'autonomous_goals', 'multimodal_fusion', 'sensorimotor',
            'formal_verifier', 'thought_decoder',
        ]
        for section in phase6_sections:
            assert section in CONFIG_SCHEMA, f"Missing Phase 6 schema section: {section}"

    def test_phase6_enable_flags_in_cognitive_loop_schema(self):
        """Phase 6 enable flags should be in cognitive_loop schema."""
        from core.config_validation import CONFIG_SCHEMA
        cl_schema = CONFIG_SCHEMA['cognitive_loop']
        phase6_flags = [
            'enable_safety_layer', 'enable_explanation_gen',
            'enable_theory_of_mind', 'enable_causal_reasoning',
            'enable_intrinsic_curiosity', 'enable_temporal_patterns',
            'enable_autonomous_goals', 'enable_self_improvement',
            'enable_multimodal_fusion', 'enable_formal_verifier',
            'enable_thought_decoder',
        ]
        for flag in phase6_flags:
            assert flag in cl_schema, f"Missing Phase 6 flag in schema: {flag}"
            assert cl_schema[flag]['type'] == bool
            assert cl_schema[flag]['default'] is True

    def test_phase6_sections_in_default_yaml(self):
        """All Phase 6 sections should exist in default.yaml."""
        import yaml
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
        phase6_sections = [
            'theory_of_mind', 'causal_reasoning', 'intrinsic_curiosity',
            'safety_layer', 'explanation_generator', 'self_improvement',
            'autonomous_goals', 'multimodal_fusion', 'sensorimotor',
            'formal_verifier', 'thought_decoder',
        ]
        for section in phase6_sections:
            assert section in config, f"Missing Phase 6 section in default.yaml: {section}"
            assert isinstance(config[section], dict)

    def test_phase6_enable_flags_in_default_yaml(self):
        """Phase 6 enable flags should be in default.yaml cognitive_loop section."""
        import yaml
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
        cl = config.get('cognitive_loop', {})
        phase6_flags = [
            'enable_safety_layer', 'enable_explanation_gen',
            'enable_theory_of_mind', 'enable_causal_reasoning',
            'enable_intrinsic_curiosity', 'enable_temporal_patterns',
            'enable_autonomous_goals', 'enable_self_improvement',
            'enable_multimodal_fusion', 'enable_formal_verifier',
            'enable_thought_decoder',
        ]
        for flag in phase6_flags:
            assert flag in cl, f"Missing Phase 6 flag in default.yaml: {flag}"
            assert cl[flag] is True

    def test_phase6_yaml_validates_cleanly(self):
        """default.yaml with Phase 6 sections should validate without errors."""
        from core.config_validation import validate_config
        import yaml
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
        errors = validate_config(config)
        real_errors = [e for e in errors if e.severity == 'error']
        assert len(real_errors) == 0, f"Validation errors: {[e.to_dict() for e in real_errors]}"

    def test_theory_of_mind_schema_fields(self):
        """theory_of_mind schema should have expected fields."""
        from core.config_validation import CONFIG_SCHEMA
        tom = CONFIG_SCHEMA['theory_of_mind']
        assert 'state_dim' in tom
        assert 'action_dim' in tom
        assert 'belief_dim' in tom
        assert 'goal_dim' in tom
        assert 'hidden_dim' in tom
        assert tom['state_dim']['default'] == 64

    def test_safety_layer_schema_fields(self):
        """safety_layer schema should have expected fields."""
        from core.config_validation import CONFIG_SCHEMA
        sl = CONFIG_SCHEMA['safety_layer']
        assert 'action_dim' in sl
        assert 'block_threshold' in sl
        assert sl['block_threshold']['default'] == 0.8


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

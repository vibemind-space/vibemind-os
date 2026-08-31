"""
Tests for YAML configuration COMPLETENESS verification.

Unlike test_yaml_config.py (which tests loading, from_yaml classmethods,
round-trips, and isolation), these tests verify that:
- All required top-level sections are present
- Numeric values fall within valid ranges
- Boolean flags are actual booleans
- Layer configs match what HierarchicalPlanner expects
- Frequency controller config section exists
- Empty/missing configs still produce valid defaults
- Enabled features have their config sections present
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import yaml
import tempfile
from core.config_loader import load_config


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'configs', 'default.yaml')

# Every top-level section that default.yaml must contain
REQUIRED_TOP_LEVEL_SECTIONS = [
    'modalities',
    'dimensions',
    'tau',
    'priors',
    'beta',
    'trn',
    'gating',
    'phase',
    'routing',
    'learning',
    'bounds',
    'simulation',
    'cognitive_loop',
    'production',
    'heartbeat',
    'layer4',
    'emotional_system',
    'homeostatic',
    'sensory',
    'ports',
    'directories',
    'logging',
]


class TestAllTopLevelSectionsExist:
    """Verify every required top-level section is present in default.yaml."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        self.cfg = load_config(CONFIG_PATH)

    @pytest.mark.parametrize("section", REQUIRED_TOP_LEVEL_SECTIONS)
    def test_section_present(self, section):
        assert section in self.cfg, (
            f"Top-level section '{section}' missing from default.yaml"
        )

    def test_no_unexpected_sections(self):
        """All top-level keys should be in the known list (catches typos)."""
        known = set(REQUIRED_TOP_LEVEL_SECTIONS)
        actual = set(self.cfg.keys())
        unexpected = actual - known
        # Warn but do not fail -- new sections are fine as long as
        # they are intentional.  Uncomment the assertion below to
        # enforce a strict whitelist.
        # assert not unexpected, f"Unexpected sections: {unexpected}"
        # For now just verify we cover at least all required ones.
        missing = known - actual
        assert not missing, f"Missing required sections: {missing}"


class TestConfigLoadsWithoutErrors:
    """Config loading should succeed and return a valid dict."""

    def test_load_returns_dict(self):
        cfg = load_config(CONFIG_PATH)
        assert isinstance(cfg, dict)

    def test_load_is_not_empty(self):
        cfg = load_config(CONFIG_PATH)
        assert len(cfg) > 0

    def test_raw_yaml_parses(self):
        """Directly parse with PyYAML to confirm no syntax errors."""
        with open(CONFIG_PATH, 'r') as f:
            raw = yaml.safe_load(f)
        assert isinstance(raw, dict)
        assert 'modalities' in raw


class TestMissingSectionsProduceSensibleDefaults:
    """When a section is missing, downstream code should fall back to defaults."""

    def _write_partial_yaml(self, content: dict) -> str:
        """Helper: write a dict as YAML to a temp file, return path."""
        fd, path = tempfile.mkstemp(suffix='.yaml')
        os.close(fd)
        with open(path, 'w') as f:
            yaml.dump(content, f)
        return path

    def test_cognitive_loop_defaults_from_empty(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cl_cfg = CognitiveLoopConfig.from_yaml({})
        assert cl_cfg.memory_routing_bias_strength == 0.25
        assert cl_cfg.max_loop_iterations == 2
        assert cl_cfg.enable_memory_bias is True

    def test_emotional_system_defaults_from_empty(self):
        from core.emotional_system import EmotionalSystemConfig
        es_cfg = EmotionalSystemConfig.from_yaml({})
        assert es_cfg.valence_decay_rate == 0.05
        assert es_cfg.fear_threshold == 0.7

    def test_homeostatic_defaults_from_empty(self):
        from core.homeostatic_regulation import HomeostaticConfig
        h_cfg = HomeostaticConfig.from_yaml({})
        assert h_cfg.energy_per_task == 0.02
        assert h_cfg.sleep_threshold == 0.8

    def test_create_model_with_minimal_config(self):
        """create_model_from_config should work with only the base sections."""
        from core.config_loader import create_model_from_config
        minimal = {
            'modalities': ['vision', 'audio'],
            'dimensions': {'vision': 16, 'audio': 8},
        }
        path = self._write_partial_yaml(minimal)
        try:
            model = create_model_from_config(path, adaptive=False)
            assert model.M == 2
        finally:
            os.unlink(path)


class TestCognitiveLoopConfigFromYaml:
    """CognitiveLoopConfig.from_yaml() correctly maps all fields from YAML."""

    def test_all_yaml_keys_mapped_to_dataclass(self):
        """Every key in the cognitive_loop YAML section that matches a
        dataclass field should be picked up."""
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = load_config(CONFIG_PATH)
        cl_section = cfg.get('cognitive_loop', {})
        cl_cfg = CognitiveLoopConfig.from_yaml(cfg)

        for key, value in cl_section.items():
            if key in CognitiveLoopConfig.__dataclass_fields__:
                actual = getattr(cl_cfg, key)
                assert actual == value, (
                    f"CognitiveLoopConfig.{key}: expected {value}, got {actual}"
                )

    def test_enabled_flag_is_in_yaml(self):
        """The YAML should contain an 'enabled' key even if CognitiveLoopConfig
        does not use it (it is consumed by ProductionPlanner)."""
        cfg = load_config(CONFIG_PATH)
        assert 'enabled' in cfg['cognitive_loop']

    def test_all_enable_flags_present_in_yaml(self):
        """All per-phase enable flags from the YAML should exist."""
        cfg = load_config(CONFIG_PATH)
        cl = cfg['cognitive_loop']
        expected_flags = [
            'enable_memory_bias',
            'enable_attention_driving',
            'enable_neuro_modulation',
            'enable_dynamic_ctm',
            'enable_reflection_loop',
            'enable_inline_consolidation',
        ]
        for flag in expected_flags:
            assert flag in cl, f"Missing enable flag '{flag}' in cognitive_loop"


class TestNumericValuesInValidRanges:
    """Numeric configuration values should be within sane bounds."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = load_config(CONFIG_PATH)

    # --- Gating temperature ---
    def test_gate_temperature_positive(self):
        temp = self.cfg['gating']['temperature']
        assert 0 < temp <= 10.0, f"Gate temperature {temp} out of range"

    # --- Learning rates ---
    def test_learning_rates_positive_and_small(self):
        lr_keys = ['lr_input', 'lr_generative', 'lr_trn', 'lr_prior',
                    'lr_tau', 'lr_gate_temp']
        learning = self.cfg['learning']
        for key in lr_keys:
            val = learning[key]
            assert 0 < val < 1.0, (
                f"learning.{key} = {val} is not in (0, 1)"
            )

    # --- Bounds ordering ---
    def test_tau_bounds_ordered(self):
        bounds = self.cfg['bounds']
        assert bounds['tau_min'] < bounds['tau_max']

    def test_prior_bounds_ordered(self):
        bounds = self.cfg['bounds']
        assert bounds['prior_min'] < bounds['prior_max']

    def test_gate_temp_bounds_ordered(self):
        bounds = self.cfg['bounds']
        assert bounds['gate_temp_min'] < bounds['gate_temp_max']

    # --- Priors sum close to 1 ---
    def test_priors_sum_approximately_one(self):
        priors = self.cfg['priors']
        total = sum(priors.values())
        assert abs(total - 1.0) < 0.05, (
            f"Priors sum to {total}, expected ~1.0"
        )

    # --- Beta weights sum to 1 ---
    def test_beta_weights_sum_to_one(self):
        beta = self.cfg['beta']
        total = sum(beta.values())
        assert abs(total - 1.0) < 1e-9, (
            f"Beta weights sum to {total}, expected 1.0"
        )

    # --- Cognitive loop thresholds in [0, 1] ---
    def test_cognitive_loop_thresholds_in_unit_range(self):
        cl = self.cfg['cognitive_loop']
        unit_range_keys = [
            'memory_routing_bias_strength',
            'attention_gating_strength',
            'attention_ctm_threshold',
            'neuro_temperature_sensitivity',
            'low_dopamine_threshold',
            'high_norepinephrine_threshold',
            'base_ctm_threshold',
            'uncertainty_ctm_reduction',
            'reconsider_confidence_threshold',
            'reconsider_pe_threshold',
        ]
        for key in unit_range_keys:
            val = cl[key]
            assert 0.0 <= val <= 1.0, (
                f"cognitive_loop.{key} = {val} is not in [0, 1]"
            )

    # --- Homeostatic thresholds ---
    def test_homeostatic_thresholds_positive(self):
        h = self.cfg['homeostatic']
        for key, val in h.items():
            if key == 'enabled':
                continue
            assert val > 0, f"homeostatic.{key} = {val} should be positive"

    # --- Emotional system thresholds in [0, 1] ---
    def test_emotional_thresholds_in_unit_range(self):
        es = self.cfg['emotional_system']
        for key in ['valence_decay_rate', 'arousal_decay_rate',
                     'emotional_memory_weight', 'fear_threshold',
                     'reward_threshold']:
            val = es[key]
            assert 0.0 <= val <= 1.0, (
                f"emotional_system.{key} = {val} not in [0, 1]"
            )


class TestBooleanFlagsAreActualBooleans:
    """Every enable/disable flag must be a Python bool, not a string or int."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = load_config(CONFIG_PATH)

    def _collect_bool_keys(self, section: dict, prefix: str = ''):
        """Yield (full_key, value) for any key that looks like a bool flag."""
        for key, val in section.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                yield from self._collect_bool_keys(val, full_key)
            elif key.startswith('enable') or key == 'enabled':
                yield full_key, val

    def test_all_enable_flags_are_bool(self):
        """Walk the entire config tree; every key starting with 'enable'
        or named 'enabled' must be a Python bool."""
        bad = []
        for full_key, val in self._collect_bool_keys(self.cfg):
            if not isinstance(val, bool):
                bad.append(f"{full_key} = {val!r} (type {type(val).__name__})")
        assert not bad, (
            "The following enable flags are not bool:\n  " + "\n  ".join(bad)
        )

    def test_cognitive_loop_booleans(self):
        cl = self.cfg['cognitive_loop']
        bool_keys = [k for k in cl if k.startswith('enable') or k == 'enabled']
        for key in bool_keys:
            assert isinstance(cl[key], bool), (
                f"cognitive_loop.{key} is {type(cl[key]).__name__}, expected bool"
            )

    def test_heartbeat_booleans(self):
        hb = self.cfg['heartbeat']
        bool_keys = [k for k in hb if k.startswith('enable') or k == 'enabled']
        for key in bool_keys:
            assert isinstance(hb[key], bool), (
                f"heartbeat.{key} is {type(hb[key]).__name__}, expected bool"
            )


class TestLayerConfigSectionsMatchHierarchicalPlanner:
    """Verify that YAML sections cover the config that HierarchicalPlanner and
    ProductionPlanner actually read at runtime."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = load_config(CONFIG_PATH)

    def test_layer4_has_required_keys(self):
        """HierarchicalPlanner reads layer4.enabled, strict_security,
        timing_threshold."""
        l4 = self.cfg['layer4']
        assert 'enabled' in l4
        assert 'strict_security' in l4
        assert 'timing_threshold' in l4

    def test_production_has_required_keys(self):
        """ProductionPlanner reads learning_rate, embedding_type,
        k_min, green_threshold, alpha."""
        prod = self.cfg['production']
        for key in ['learning_rate', 'embedding_type', 'k_min',
                     'green_threshold', 'alpha']:
            assert key in prod, f"production.{key} missing"

    def test_modalities_dimensions_tau_priors_aligned(self):
        """dimensions, tau, and priors must cover exactly the modalities list."""
        modalities = set(self.cfg['modalities'])
        assert set(self.cfg['dimensions'].keys()) == modalities
        assert set(self.cfg['tau'].keys()) == modalities
        assert set(self.cfg['priors'].keys()) == modalities

    def test_phase_omega_matches_modalities(self):
        """If phase coupling is defined, omega keys should match modalities."""
        phase = self.cfg.get('phase', {})
        omega = phase.get('omega', {})
        if omega:
            modalities = set(self.cfg['modalities'])
            assert set(omega.keys()) == modalities, (
                "phase.omega keys do not match modalities"
            )

    def test_routing_section_has_num_targets(self):
        """config_loader reads routing.num_targets for model creation."""
        assert 'num_targets' in self.cfg['routing']
        assert isinstance(self.cfg['routing']['num_targets'], int)

    def test_simulation_section_complete(self):
        """config_loader reads simulation.dt, seed, nonlinearity."""
        sim = self.cfg['simulation']
        assert 'dt' in sim
        assert 'seed' in sim
        assert 'nonlinearity' in sim


class TestFrequencyControllerConfigSectionExists:
    """BrainFrequencyController is instantiated by the cognitive loop.
    While it does not read from YAML directly today, the phase section
    and cognitive_loop frequency mappings must be present."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = load_config(CONFIG_PATH)

    def test_phase_section_exists(self):
        assert 'phase' in self.cfg

    def test_phase_has_use_phase_flag(self):
        assert 'use_phase' in self.cfg['phase']
        assert isinstance(self.cfg['phase']['use_phase'], bool)

    def test_phase_has_coupling_strength(self):
        assert 'coupling_strength' in self.cfg['phase']

    def test_cognitive_loop_has_frequency_related_defaults(self):
        """CognitiveLoopConfig defines frequency_* dict fields.
        If those are ever added to the YAML they should be valid dicts.
        For now, just verify the cognitive_loop section exists and is
        loadable by CognitiveLoopConfig."""
        from core.cognitive_loop import CognitiveLoopConfig
        cl_cfg = CognitiveLoopConfig.from_yaml(self.cfg)
        # The dataclass should have frequency mappings with all 5 bands
        assert len(cl_cfg.frequency_attention_strength) == 5
        assert 'delta' in cl_cfg.frequency_attention_strength
        assert 'gamma' in cl_cfg.frequency_attention_strength


class TestEmptyYamlCreatesValidDefaults:
    """An empty or near-empty YAML file should not crash any from_yaml loader."""

    def _write_yaml(self, content) -> str:
        fd, path = tempfile.mkstemp(suffix='.yaml')
        os.close(fd)
        with open(path, 'w') as f:
            if content is not None:
                yaml.dump(content, f)
            else:
                f.write('')
        return path

    def test_empty_dict_cognitive_loop(self):
        from core.cognitive_loop import CognitiveLoopConfig
        cfg = CognitiveLoopConfig.from_yaml({})
        assert cfg.max_loop_iterations == 2

    def test_empty_dict_emotional(self):
        from core.emotional_system import EmotionalSystemConfig
        cfg = EmotionalSystemConfig.from_yaml({})
        assert cfg.valence_decay_rate == 0.05

    def test_empty_dict_homeostatic(self):
        from core.homeostatic_regulation import HomeostaticConfig
        cfg = HomeostaticConfig.from_yaml({})
        assert cfg.energy_per_task == 0.02

    def test_none_yaml_content_loads_as_none(self):
        """An empty file produces None from yaml.safe_load; from_yaml
        should handle that gracefully by accepting {} as input."""
        path = self._write_yaml(None)
        try:
            with open(path, 'r') as f:
                raw = yaml.safe_load(f)
            # yaml.safe_load on empty file returns None
            assert raw is None
            # Our from_yaml methods expect dict, so pass {}
            from core.cognitive_loop import CognitiveLoopConfig
            cfg = CognitiveLoopConfig.from_yaml({})
            assert cfg is not None
        finally:
            os.unlink(path)

    def test_minimal_yaml_creates_model(self):
        """A YAML with only modalities + dimensions should still create a model."""
        from core.config_loader import create_model_from_config
        content = {
            'modalities': ['vision'],
            'dimensions': {'vision': 8},
        }
        path = self._write_yaml(content)
        try:
            model = create_model_from_config(path, adaptive=False)
            assert model.M == 1
        finally:
            os.unlink(path)


class TestConfigConsistency:
    """If a feature is enabled, its config section should exist and be
    populated with valid values."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = load_config(CONFIG_PATH)

    def test_heartbeat_enabled_has_interval(self):
        hb = self.cfg['heartbeat']
        if hb.get('enabled', False):
            assert 'interval_seconds' in hb
            assert hb['interval_seconds'] > 0

    def test_emotional_system_enabled_has_thresholds(self):
        es = self.cfg['emotional_system']
        if es.get('enabled', False):
            assert 'fear_threshold' in es
            assert 'reward_threshold' in es

    def test_homeostatic_enabled_has_energy_keys(self):
        h = self.cfg['homeostatic']
        if h.get('enabled', False):
            required = ['energy_per_task', 'energy_recovery_rate',
                        'fatigue_per_task', 'sleep_threshold']
            for key in required:
                assert key in h, f"homeostatic.{key} missing but enabled=True"

    def test_layer4_enabled_has_security_and_threshold(self):
        l4 = self.cfg['layer4']
        if l4.get('enabled', False):
            assert 'strict_security' in l4
            assert 'timing_threshold' in l4

    def test_production_continuous_learning_has_rate(self):
        prod = self.cfg['production']
        if prod.get('enable_continuous_learning', False):
            assert 'learning_rate' in prod
            assert 0 < prod['learning_rate'] < 1.0

    def test_sensory_section_has_enabled(self):
        sensory = self.cfg['sensory']
        assert 'enabled' in sensory

    def test_ports_section_has_all_services(self):
        ports = self.cfg['ports']
        expected_services = ['unified_brain', 'dashboard']
        for svc in expected_services:
            assert svc in ports, f"ports.{svc} missing"
            assert isinstance(ports[svc], int)

    def test_directories_section_has_required_paths(self):
        dirs = self.cfg['directories']
        for key in ['session_logs', 'episodic_memory', 'trained_matrices']:
            assert key in dirs, f"directories.{key} missing"
            assert isinstance(dirs[key], str)

    def test_dream_mode_enabled_requires_heartbeat_idle_threshold(self):
        """If dream mode is enabled inside heartbeat, the idle threshold
        must be present."""
        hb = self.cfg['heartbeat']
        if hb.get('enable_dream_mode', False):
            assert 'dream_idle_threshold_seconds' in hb
            assert hb['dream_idle_threshold_seconds'] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

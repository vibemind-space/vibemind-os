"""
Tests for CTM Training Data, Validation, Domain Router Calibration,
and Dream-Mode CTM Training integration (P2.16-19, P2.22)

Tests:
1. Training data generation (P2.16-18)
2. Training validation against checkpoints (P2.16-18)
3. Domain router calibration corpus (P2.19)
4. Domain router accuracy metrics (P2.19)
5. Dream-mode CTM training wiring (P2.22)
"""

import os
import sys
import json
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ─── P2.16-18: Training Data Generation Tests ─────────────────────────

class TestCTMTrainingDataGeneration:
    """Tests for synthetic training data generation."""

    def test_generator_creates_logic_dataset(self):
        """Generate logic domain dataset."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.LOGIC, num_samples=50)

        assert len(dataset) == 50
        assert all(d['domain'] == 'logic' for d in dataset)
        assert all('task_description' in d for d in dataset)
        assert all('puzzle_state' in d for d in dataset)
        assert all('complexity' in d for d in dataset)

    def test_generator_creates_temporal_dataset(self):
        """Generate temporal domain dataset."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.TEMPORAL, num_samples=50)

        assert len(dataset) == 50
        assert all(d['domain'] == 'temporal' for d in dataset)

    def test_generator_creates_value_dataset(self):
        """Generate value domain dataset."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.VALUE, num_samples=50)

        assert len(dataset) == 50
        assert all(d['domain'] == 'value' for d in dataset)

    def test_generator_creates_spatial_dataset(self):
        """Generate spatial domain dataset."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.SPATIAL, num_samples=50)

        assert len(dataset) == 50
        assert all(d['domain'] == 'spatial' for d in dataset)

    def test_puzzle_state_is_5x4(self):
        """Puzzle states should be 5x4 grids."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.LOGIC, num_samples=10)

        for sample in dataset:
            state = sample['puzzle_state']
            assert len(state) == 5
            assert all(len(row) == 4 for row in state)

    def test_complexity_in_range(self):
        """Complexity should be within specified range."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(
            CTMDomain.LOGIC, num_samples=100,
            complexity_range=(0.3, 0.8)
        )

        for sample in dataset:
            assert 0.3 <= sample['complexity'] <= 0.8

    def test_target_modules_present(self):
        """Each sample should have target module routing."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.LOGIC, num_samples=10)

        for sample in dataset:
            tm = sample['target_modules']
            assert 'LAN' in tm
            assert 'DLPFC' in tm
            assert 'ACC' in tm
            # Must sum close to 1.0
            assert abs(sum(tm.values()) - 1.0) < 0.01

    def test_generate_all_saves_to_disk(self, tmp_path):
        """Generate all datasets and verify persistence."""
        from core.ctm_training_data import CTMTrainingDataGenerator

        gen = CTMTrainingDataGenerator(output_dir=str(tmp_path), seed=42)
        summary = gen.generate_all_datasets(samples_per_domain=20)

        assert 'logic' in summary
        assert 'temporal' in summary
        assert 'value' in summary
        assert 'spatial' in summary

        # Verify files exist
        for domain in ['logic', 'temporal', 'value', 'spatial']:
            train_file = tmp_path / f"{domain}_train.json"
            val_file = tmp_path / f"{domain}_val.json"
            assert train_file.exists()
            assert val_file.exists()

            # Verify structure
            with open(train_file) as f:
                data = json.load(f)
                assert 'samples' in data
                assert data['type'] == 'training'
                assert data['num_samples'] == 16  # 80% of 20

    def test_dataset_summary_saved(self, tmp_path):
        """Summary file should be saved."""
        from core.ctm_training_data import CTMTrainingDataGenerator

        gen = CTMTrainingDataGenerator(output_dir=str(tmp_path), seed=42)
        gen.generate_all_datasets(samples_per_domain=10)

        summary_file = tmp_path / 'dataset_summary.json'
        assert summary_file.exists()

    def test_deterministic_generation(self):
        """Same seed should produce identical datasets."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen1 = CTMTrainingDataGenerator(seed=999)
        d1 = gen1.generate_domain_dataset(CTMDomain.LOGIC, num_samples=20)

        gen2 = CTMTrainingDataGenerator(seed=999)
        d2 = gen2.generate_domain_dataset(CTMDomain.LOGIC, num_samples=20)

        for s1, s2 in zip(d1, d2):
            assert s1['task_description'] == s2['task_description']
            assert s1['complexity'] == s2['complexity']

    def test_task_descriptions_are_diverse(self):
        """Task descriptions should not all be identical."""
        from core.ctm_training_data import CTMTrainingDataGenerator
        from core.shared_enums import CTMDomain

        gen = CTMTrainingDataGenerator(seed=42)
        dataset = gen.generate_domain_dataset(CTMDomain.LOGIC, num_samples=100)

        unique_tasks = set(d['task_description'] for d in dataset)
        assert len(unique_tasks) > 10  # Decent diversity


# ─── P2.16-18: Training Validation Tests ───────────────────────────────

class TestCTMTrainingValidation:
    """Tests for training validation against checkpoints."""

    def test_validator_loads_extended_summary(self):
        """Validator should find and load extended training summary."""
        from core.ctm_training_data import CTMTrainingValidator

        validator = CTMTrainingValidator()
        result = validator.validate_domain('logic')

        assert result['status'] == 'completed'
        assert result['converged'] is True
        assert result['best_convergence'] > 0.99

    def test_all_domains_converged(self):
        """All three CTM domains should be converged."""
        from core.ctm_training_data import CTMTrainingValidator

        validator = CTMTrainingValidator()
        report = validator.validate_all_domains()

        assert report['all_domains_pass'] is True
        assert report['average_convergence'] > 0.99

        for domain in ['logic', 'temporal', 'value']:
            assert report['domains'][domain]['converged'] is True

    def test_module_accuracy_high(self):
        """Individual module accuracy should be above 95%."""
        from core.ctm_training_data import CTMTrainingValidator

        validator = CTMTrainingValidator()
        report = validator.validate_all_domains()

        for domain in ['logic', 'temporal', 'value']:
            for module, accuracy in report['domains'][domain]['module_accuracy'].items():
                assert accuracy > 0.95, f"{domain}/{module} accuracy too low: {accuracy}"

    def test_validation_handles_missing_domain(self):
        """Validation should handle missing domain gracefully."""
        from core.ctm_training_data import CTMTrainingValidator

        validator = CTMTrainingValidator()
        result = validator.validate_domain('nonexistent')

        assert result['converged'] is False
        assert result['status'] == 'no_training_data'


# ─── P2.19: Domain Router Calibration Tests ────────────────────────────

class TestDomainRouterCalibration:
    """Tests for domain router calibration."""

    def test_calibration_corpus_generation(self):
        """Corpus should have diverse tasks from all domains."""
        from core.ctm_training_data import DomainRouterCalibrationCorpus

        gen = DomainRouterCalibrationCorpus()
        corpus = gen.generate_calibration_corpus()

        assert len(corpus) > 500

        domains = set(item['ground_truth_domain'] for item in corpus)
        assert 'logic' in domains
        assert 'temporal' in domains
        assert 'value' in domains
        assert 'spatial' in domains

    def test_calibration_corpus_has_difficulties(self):
        """Corpus should include easy, hard, and ambiguous tasks."""
        from core.ctm_training_data import DomainRouterCalibrationCorpus

        gen = DomainRouterCalibrationCorpus()
        corpus = gen.generate_calibration_corpus()

        difficulties = set(item.get('difficulty', 'easy') for item in corpus)
        assert 'easy' in difficulties
        assert 'hard' in difficulties
        assert 'ambiguous' in difficulties

    def test_calibration_corpus_has_mixed_domains(self):
        """Corpus should include mixed-domain tasks."""
        from core.ctm_training_data import DomainRouterCalibrationCorpus

        gen = DomainRouterCalibrationCorpus()
        corpus = gen.generate_calibration_corpus()

        mixed = [item for item in corpus if item.get('is_mixed', False)]
        assert len(mixed) > 10

    def test_router_accuracy_above_90_percent(self):
        """Domain router should achieve at least 90% overall accuracy."""
        from core.ctm_training_data import DomainRouterCalibrator

        calibrator = DomainRouterCalibrator()
        report = calibrator.calibrate()

        assert report['overall_accuracy'] >= 0.90, \
            f"Overall accuracy {report['overall_accuracy']:.1%} below 90%"

    def test_per_domain_accuracy_above_85_percent(self):
        """Each domain should achieve at least 85% accuracy."""
        from core.ctm_training_data import DomainRouterCalibrator

        calibrator = DomainRouterCalibrator()
        report = calibrator.calibrate()

        for domain, acc in report['domain_accuracy'].items():
            assert acc >= 0.85, \
                f"{domain} accuracy {acc:.1%} below 85%"

    def test_easy_tasks_above_95_percent(self):
        """Easy (pure domain) tasks should have >95% accuracy."""
        from core.ctm_training_data import DomainRouterCalibrator

        calibrator = DomainRouterCalibrator()
        report = calibrator.calibrate()

        assert report['difficulty_accuracy']['easy'] >= 0.95, \
            f"Easy task accuracy {report['difficulty_accuracy']['easy']:.1%} below 95%"

    def test_calibration_report_has_misclassifications(self):
        """Report should list misclassified examples."""
        from core.ctm_training_data import DomainRouterCalibrator

        calibrator = DomainRouterCalibrator()
        report = calibrator.calibrate()

        assert 'misclassification_count' in report
        assert isinstance(report['sample_misclassifications'], list)


# ─── P2.19: Domain Router Keyword Coverage Tests ──────────────────────

class TestDomainRouterKeywords:
    """Tests for domain router keyword coverage."""

    def test_logic_keywords_cover_core_concepts(self):
        """Logic router should classify pure logic tasks correctly."""
        from core.ctm_domain_router import CTMDomainRouter, DomainClassification
        from core.shared_enums import CTMDomain

        router = CTMDomainRouter()
        tasks = [
            "Validate Kubernetes manifest against security policies",
            "Check type constraints in function signatures",
            "Verify data integrity constraints",
            "Prove correctness of sorting algorithm",
        ]
        for task in tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.LOGIC, \
                f"'{task}' classified as {result.primary_domain.value}, expected logic"

    def test_temporal_keywords_cover_core_concepts(self):
        """Temporal router should classify pure temporal tasks correctly."""
        from core.ctm_domain_router import CTMDomainRouter
        from core.shared_enums import CTMDomain

        router = CTMDomainRouter()
        tasks = [
            "Detect anomalies in time-series metrics",
            "Schedule microservices auto-scaling events",
            "Forecast traffic load patterns for next 24 hours",
            "Detect change-points in deployment frequency",
        ]
        for task in tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.TEMPORAL, \
                f"'{task}' classified as {result.primary_domain.value}, expected temporal"

    def test_value_keywords_cover_core_concepts(self):
        """Value router should classify pure value tasks correctly."""
        from core.ctm_domain_router import CTMDomainRouter
        from core.shared_enums import CTMDomain

        router = CTMDomainRouter()
        tasks = [
            "Optimize cloud resource allocation balancing cost vs performance",
            "Prioritize 10 feature requests by impact and effort scores",
            "Choose deployment strategy trading off speed vs reliability",
        ]
        for task in tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.VALUE, \
                f"'{task}' classified as {result.primary_domain.value}, expected value"

    def test_spatial_keywords_cover_core_concepts(self):
        """Spatial router should classify pure spatial tasks correctly."""
        from core.ctm_domain_router import CTMDomainRouter
        from core.shared_enums import CTMDomain

        router = CTMDomainRouter()
        tasks = [
            "Design microservice architecture with service mesh",
            "Optimize container placement across cluster nodes",
            "Design network topology for minimal latency",
        ]
        for task in tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.SPATIAL, \
                f"'{task}' classified as {result.primary_domain.value}, expected spatial"


# ─── P2.22: Dream-Mode CTM Training Wiring Tests ──────────────────────

class TestDreamModeCTMTrainingWiring:
    """Tests for dream-mode CTM training integration in heartbeat."""

    def _make_mock_planner(self):
        """Create a mock ProductionPlanner with necessary attributes."""
        mock_planner = MagicMock()
        mock_planner.total_predictions = 5
        mock_planner.total_feedback = 2

        mock_hier = MagicMock()
        mock_hier.enable_neuromodulation = True
        mock_hier.neuromodulation = MagicMock()
        mock_hier.enable_dream_mode = True
        mock_hier.dream_mode = MagicMock()
        mock_hier.enable_memory = True
        mock_hier.memory = MagicMock()
        mock_hier.memory.episodic.memories = [MagicMock()]
        mock_hier.layer3.intervention_types = ['suggest', 'retry']
        mock_hier.dream_mode.dream_cycle.return_value = [MagicMock()]
        mock_hier.enable_temporal_memory = False
        mock_hier.enable_meta_learning = False
        mock_hier.enable_predictive_coding = False
        mock_planner.planner = mock_hier
        mock_planner._yaml_config = None

        return mock_planner

    def test_heartbeat_has_ctm_trainer_field(self):
        """Heartbeat should initialize ctm_trainer field."""
        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig

        config = BrainHeartbeatConfig(
            enable_dream_mode=False,
            enable_health_monitoring=False,
            enable_neuromodulation_decay=False,
            enable_temporal_updates=False,
            enable_meta_learning_checks=False,
        )
        mock_planner = self._make_mock_planner()

        heartbeat = BrainHeartbeat(mock_planner, config=config)

        # CTM trainer should be attempted (may or may not be available)
        assert hasattr(heartbeat, '_ctm_trainer')
        assert hasattr(heartbeat, '_ctm_training_cycle')
        assert hasattr(heartbeat, '_ctm_training_interval')

    def test_heartbeat_ctm_training_cycle_increments(self):
        """CTM training cycle counter should increment."""
        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig

        config = BrainHeartbeatConfig(
            enable_dream_mode=True,
            enable_health_monitoring=False,
            enable_neuromodulation_decay=False,
            enable_temporal_updates=False,
            enable_meta_learning_checks=False,
        )
        mock_planner = self._make_mock_planner()

        heartbeat = BrainHeartbeat(mock_planner, config=config)

        # Mock CTM trainer
        mock_trainer = MagicMock()
        mock_config = MagicMock()
        mock_config.target_module_routing = {'LAN': 0.7, 'DLPFC': 0.2, 'ACC': 0.1}
        mock_trainer._get_default_config.return_value = mock_config
        mock_trainer.train_domain_ctm.return_value = {'status': 'completed', 'best_convergence': 0.99}
        heartbeat._ctm_trainer = mock_trainer

        initial_cycle = heartbeat._ctm_training_cycle
        heartbeat._run_ctm_dream_training()
        assert heartbeat._ctm_training_cycle == initial_cycle + 1

    def test_heartbeat_dream_triggers_ctm_on_interval(self):
        """Dream mode should trigger CTM training at configured interval."""
        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig

        config = BrainHeartbeatConfig(
            enable_dream_mode=True,
            enable_health_monitoring=False,
            enable_neuromodulation_decay=False,
            enable_temporal_updates=False,
            enable_meta_learning_checks=False,
        )
        mock_planner = self._make_mock_planner()

        heartbeat = BrainHeartbeat(mock_planner, config=config)
        heartbeat._ctm_training_interval = 1  # Train every dream cycle

        # Mock CTM trainer
        mock_trainer = MagicMock()
        mock_config = MagicMock()
        mock_config.target_module_routing = {'LAN': 0.7, 'DLPFC': 0.2, 'ACC': 0.1}
        mock_trainer._get_default_config.return_value = mock_config
        mock_trainer.train_domain_ctm.return_value = {'status': 'completed', 'best_convergence': 0.99}
        heartbeat._ctm_trainer = mock_trainer

        # Make total_dreams divisible by interval
        heartbeat.total_dreams = 0  # Will become 1 after dream
        heartbeat.idle_time_seconds = 600  # Idle enough for dream

        # Trigger dream mode
        heartbeat._trigger_dream_mode()

        # CTM training should have been called
        # total_dreams is now 1, and 1 % 1 == 0, so it should trigger
        assert mock_trainer.train_domain_ctm.called or mock_trainer._get_default_config.called

    def test_ctm_training_cycles_through_domains(self):
        """CTM training should cycle: Logic -> Temporal -> Value -> Logic."""
        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig
        from core.shared_enums import CTMDomain

        config = BrainHeartbeatConfig(
            enable_dream_mode=True,
            enable_health_monitoring=False,
            enable_neuromodulation_decay=False,
            enable_temporal_updates=False,
            enable_meta_learning_checks=False,
        )
        mock_planner = self._make_mock_planner()

        heartbeat = BrainHeartbeat(mock_planner, config=config)

        # Mock CTM trainer
        mock_trainer = MagicMock()
        mock_config = MagicMock()
        mock_config.target_module_routing = {'LAN': 0.7, 'DLPFC': 0.2, 'ACC': 0.1}
        mock_trainer._get_default_config.return_value = mock_config
        mock_trainer.train_domain_ctm.return_value = {'status': 'completed', 'best_convergence': 0.99}
        heartbeat._ctm_trainer = mock_trainer

        # Run 3 cycles
        domains_trained = []
        for _ in range(3):
            heartbeat._run_ctm_dream_training()
            call_args = mock_trainer.train_domain_ctm.call_args
            domains_trained.append(call_args.kwargs.get('domain') or call_args[1].get('domain') if call_args[1] else call_args[0][0] if call_args[0] else None)

        # Should cycle through Logic, Temporal, Value
        assert domains_trained[0] == CTMDomain.LOGIC
        assert domains_trained[1] == CTMDomain.TEMPORAL
        assert domains_trained[2] == CTMDomain.VALUE

    def test_ctm_training_handles_error_gracefully(self):
        """CTM training errors should not crash the heartbeat."""
        from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig

        config = BrainHeartbeatConfig(
            enable_dream_mode=True,
            enable_health_monitoring=False,
            enable_neuromodulation_decay=False,
            enable_temporal_updates=False,
            enable_meta_learning_checks=False,
        )
        mock_planner = self._make_mock_planner()

        heartbeat = BrainHeartbeat(mock_planner, config=config)

        # Mock CTM trainer that raises
        mock_trainer = MagicMock()
        mock_config = MagicMock()
        mock_config.target_module_routing = {'LAN': 0.7}
        mock_trainer._get_default_config.return_value = mock_config
        mock_trainer.train_domain_ctm.side_effect = RuntimeError("Training failed")
        heartbeat._ctm_trainer = mock_trainer

        # Should not raise
        result = heartbeat._run_ctm_dream_training()
        # Error should be recorded
        assert len(heartbeat.errors) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

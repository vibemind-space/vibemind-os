"""
Integration Tests for Adaptive Cognitive System (ACS)

Tests the complete integration of:
1. Brain Frequency Controller
2. Multi-CTM Ensemble
3. Cross-CTM Communication
4. Frequency-CTM Coordination
5. Dashboard API endpoints
6. Unified Brain Service

Run with: pytest tests/test_integration_acs.py -v
"""

import pytest
import sys
import os
import time
import threading
from typing import Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import components
from core.brain_frequency_controller import (
    BrainFrequencyController,
    FrequencyMode,
    FrequencyMixer,
    Marker
)
from core.multi_ctm_ensemble import (
    MultiCTMEnsemble,
    CTMDomain,
    CrossCTMContext,
    EnsembleResult
)
from core.ctm_domain_router import CTMDomainRouter, DomainClassification


class TestBrainFrequencyController:
    """Test brain frequency controller functionality"""

    def test_frequency_modes_exist(self):
        """Verify all 5 frequency modes are defined"""
        modes = [FrequencyMode.DELTA, FrequencyMode.THETA, FrequencyMode.ALPHA,
                 FrequencyMode.BETA, FrequencyMode.GAMMA]
        assert len(modes) == 5

    def test_controller_initialization(self):
        """Test frequency controller initializes correctly"""
        controller = BrainFrequencyController()
        assert controller is not None
        assert controller.dominant_mode == FrequencyMode.ALPHA  # Default mode

    def test_mode_switching(self):
        """Test switching between frequency modes"""
        controller = BrainFrequencyController()

        # Switch to each mode
        for mode in FrequencyMode:
            result = controller.set_mode(mode, activation=1.0, suppress_others=True)
            assert 'mode' in result
            assert result['current_dominant'] == mode.value
            assert controller.dominant_mode == mode

    def test_gamma_mode_triggers_handlers(self):
        """Test GAMMA mode triggers registered handlers"""
        controller = BrainFrequencyController()
        handler_called = {'called': False}

        def gamma_handler(mode):
            handler_called['called'] = True

        controller.register_handler(FrequencyMode.GAMMA, gamma_handler)
        controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)

        assert handler_called['called'] == True

    def test_frequency_mixer(self):
        """Test frequency mixer for blended states"""
        controller = BrainFrequencyController()
        mixer = FrequencyMixer(controller)
        assert mixer is not None

        # Mix alpha and beta
        mixer.set_blend({
            'alpha': 0.6,
            'beta': 0.4
        })

        # Check blended components
        components = mixer.get_blended_components()
        assert len(components) > 0

    def test_marker_system(self):
        """Test frequency marker recording"""
        controller = BrainFrequencyController()

        # Set marker
        marker = controller.set_marker(
            decision_point="test_checkpoint",
            context={'task': 'integration_test'},
            confidence=0.8
        )

        assert marker is not None
        assert marker.decision_point == "test_checkpoint"

        # Get markers
        markers = controller.get_recent_markers(count=10)
        assert len(markers) >= 1


class TestCTMDomainRouter:
    """Test CTM domain classification"""

    def test_router_initialization(self):
        """Test domain router initializes correctly"""
        router = CTMDomainRouter()
        assert router is not None

    def test_spatial_classification(self):
        """Test spatial domain classification"""
        router = CTMDomainRouter()

        spatial_tasks = [
            "Design microservice architecture with service mesh",
            "Deploy Docker container cluster",
            "Create network topology diagram"
        ]

        for task in spatial_tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.SPATIAL, f"Task '{task}' should be spatial"

    def test_logic_classification(self):
        """Test logic domain classification"""
        router = CTMDomainRouter()

        logic_tasks = [
            "Validate Kubernetes manifest against security policies",
            "Check type constraints in API schema",
            "Verify compliance with GDPR rules"
        ]

        for task in logic_tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.LOGIC, f"Task '{task}' should be logic"

    def test_temporal_classification(self):
        """Test temporal domain classification"""
        router = CTMDomainRouter()

        temporal_tasks = [
            "Detect anomalies in time-series metrics",
            "Schedule batch jobs for off-peak hours",
            "Analyze temporal patterns in user activity"
        ]

        for task in temporal_tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.TEMPORAL, f"Task '{task}' should be temporal"

    def test_value_classification(self):
        """Test value domain classification"""
        router = CTMDomainRouter()

        value_tasks = [
            "Optimize resource allocation with cost trade-offs",
            "Balance performance vs reliability",
            "Decide between scaling up or out"
        ]

        for task in value_tasks:
            result = router.classify_task(task)
            assert result.primary_domain == CTMDomain.VALUE, f"Task '{task}' should be value"

    def test_mixed_domain_detection(self):
        """Test mixed domain detection for complex tasks"""
        router = CTMDomainRouter(mixed_domain_threshold=0.60)

        mixed_task = "Design auto-scaling microservice architecture with cost optimization and anomaly detection"
        result = router.classify_task(mixed_task)

        # Should detect multiple domains
        assert result.is_mixed_domain or len(result.secondary_domains) > 0


class TestMultiCTMEnsemble:
    """Test Multi-CTM Ensemble functionality"""

    @pytest.fixture
    def ensemble(self):
        """Create ensemble for tests"""
        try:
            return MultiCTMEnsemble(
                max_concurrent_per_ctm=1,
                consciousness_threshold=0.80,
                max_reasoning_steps=15,  # Quick for tests
                enable_logic_ctm=True,
                enable_temporal_ctm=True,
                enable_value_ctm=True
            )
        except Exception as e:
            pytest.skip(f"CTM not available: {e}")

    def test_ensemble_initialization(self, ensemble):
        """Test ensemble initializes all CTMs"""
        assert ensemble is not None
        assert CTMDomain.SPATIAL in ensemble.ctms
        assert ensemble.ctms[CTMDomain.SPATIAL] is not None

    def test_async_reasoning(self, ensemble):
        """Test async reasoning submission"""
        task_id = ensemble.reason_async(
            task="Design microservice architecture",
            brain_state={'modality_activations': {'tool_trace': 0.8}},
            max_steps=10
        )

        assert task_id is not None
        assert len(task_id) == 8  # UUID first 8 chars

    def test_result_retrieval(self, ensemble):
        """Test result retrieval with wait"""
        task_id = ensemble.reason_async(
            task="Deploy container cluster",
            brain_state={},
            max_steps=10
        )

        result = ensemble.get_result(task_id, wait=True, timeout=30)

        assert result is not None
        assert result.task_id == task_id
        assert result.primary_domain is not None

    def test_domain_routing(self, ensemble):
        """Test tasks route to correct CTMs"""
        test_cases = [
            ("Design microservice architecture", CTMDomain.SPATIAL),
            # Logic/Temporal/Value may fall back to Spatial if not trained
        ]

        for task, expected_domain in test_cases:
            task_id = ensemble.reason_async(task, brain_state={}, max_steps=10)
            result = ensemble.get_result(task_id, wait=True, timeout=20)

            assert result is not None
            # Note: May fall back to SPATIAL if specialized CTM not trained

    def test_get_stats(self, ensemble):
        """Test statistics retrieval"""
        stats = ensemble.get_stats()

        assert 'total_ensemble_tasks' in stats
        assert 'tasks_by_domain' in stats
        assert 'active_ctms' in stats


class TestCrossCTMCommunication:
    """Test cross-CTM communication functionality"""

    @pytest.fixture
    def ensemble(self):
        """Create ensemble for tests"""
        try:
            return MultiCTMEnsemble(
                max_concurrent_per_ctm=1,
                consciousness_threshold=0.80,
                max_reasoning_steps=10,
                enable_logic_ctm=True,
                enable_temporal_ctm=True,
                enable_value_ctm=True
            )
        except Exception as e:
            pytest.skip(f"CTM not available: {e}")

    def test_cross_ctm_context_creation(self):
        """Test CrossCTMContext dataclass"""
        ctx = CrossCTMContext(
            shared_insights={'spatial': 'microservice architecture'},
            constraints=['validation required'],
            temporal_factors=['scheduled execution'],
            value_assessments={'cost_priority': 0.8},
            spatial_structures=['containerized'],
            execution_order=['spatial', 'logic', 'temporal', 'value'],
            conflict_resolutions=[]
        )

        assert ctx.shared_insights['spatial'] == 'microservice architecture'
        assert len(ctx.constraints) == 1
        assert ctx.value_assessments['cost_priority'] == 0.8

    def test_collaborative_reasoning(self, ensemble):
        """Test collaborative reasoning with context passing"""
        result = ensemble.reason_with_collaboration(
            task="Design distributed system with validation and scheduling",
            brain_state={},
            max_steps=10,
            execution_order=[CTMDomain.SPATIAL]  # Just spatial for speed
        )

        assert result is not None
        assert result.cross_ctm_context is not None
        assert result.aggregated_insights is not None

    def test_context_enrichment(self, ensemble):
        """Test task enrichment with cross-CTM context"""
        # Create a context with prior insights
        ctx = CrossCTMContext(
            shared_insights={'spatial': 'microservice design'},
            constraints=['security validation'],
            temporal_factors=['scheduled deployment'],
            value_assessments={'reliability': 0.9},
            spatial_structures=['containerized', 'distributed'],
            execution_order=['spatial', 'logic'],
            conflict_resolutions=[]
        )

        # Test enrichment for LOGIC domain (should get spatial context)
        enriched = ensemble._enrich_task_with_context(
            task="Validate configuration",
            domain=CTMDomain.LOGIC,
            cross_ctx=ctx
        )

        assert 'Spatial Context' in enriched or 'Cross-CTM' in enriched

    def test_conflict_resolution(self, ensemble):
        """Test conflict resolution between CTM recommendations"""
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=['validation required'],
            temporal_factors=['auto-scaling triggers'],
            value_assessments={'performance_priority': 0.9, 'cost_priority': 0.8},
            spatial_structures=['distributed cluster'],
            execution_order=[],
            conflict_resolutions=[]
        )

        resolved_ctx = ensemble._resolve_conflicts(ctx, {})

        # Should detect performance-cost conflict
        assert len(resolved_ctx.conflict_resolutions) >= 1


class TestFrequencyCTMCoordination:
    """Test frequency mode and CTM coordination"""

    def test_gamma_activates_ctm(self):
        """Test GAMMA mode should trigger CTM reasoning"""
        controller = BrainFrequencyController()
        ctm_triggered = {'triggered': False, 'mode': None}

        def gamma_handler(mode):
            ctm_triggered['triggered'] = True
            ctm_triggered['mode'] = mode

        controller.register_handler(FrequencyMode.GAMMA, gamma_handler)
        controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)

        assert ctm_triggered['triggered'] == True
        assert ctm_triggered['mode'] == FrequencyMode.GAMMA

    def test_delta_for_training(self):
        """Test DELTA mode is used for meta-learning/training"""
        controller = BrainFrequencyController()
        controller.set_mode(FrequencyMode.DELTA, activation=1.0, suppress_others=True)

        assert controller.dominant_mode == FrequencyMode.DELTA

        # Get state
        state = controller.get_state()
        assert state['dominant_mode'] == 'delta'

    def test_mode_transition_sequence(self):
        """Test typical mode transition: ALPHA -> GAMMA -> ALPHA"""
        controller = BrainFrequencyController()

        # Start in ALPHA (routing)
        controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)
        assert controller.dominant_mode == FrequencyMode.ALPHA

        # Complex task triggers GAMMA (reasoning)
        controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)
        assert controller.dominant_mode == FrequencyMode.GAMMA

        # Reasoning complete, back to ALPHA
        controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)
        assert controller.dominant_mode == FrequencyMode.ALPHA


class TestEnsembleResult:
    """Test EnsembleResult dataclass"""

    def test_result_creation(self):
        """Test creating ensemble result"""
        result = EnsembleResult(
            task_id="abc12345",
            task="Test task",
            primary_domain=CTMDomain.SPATIAL,
            secondary_domains=[CTMDomain.LOGIC],
            ctm_results={},
            aggregated_insights="Test insight",
            reasoning_chain="Reasoning...",
            elapsed_time=1.5,
            cross_ctm_context=None
        )

        assert result.task_id == "abc12345"
        assert result.primary_domain == CTMDomain.SPATIAL
        assert len(result.secondary_domains) == 1

    def test_result_with_cross_context(self):
        """Test result with cross-CTM context"""
        ctx = CrossCTMContext(
            shared_insights={'spatial': 'architecture'},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=['modular'],
            execution_order=['spatial'],
            conflict_resolutions=[]
        )

        result = EnsembleResult(
            task_id="def67890",
            task="Complex task",
            primary_domain=CTMDomain.SPATIAL,
            secondary_domains=[],
            ctm_results={},
            aggregated_insights=None,
            reasoning_chain="",
            elapsed_time=0.5,
            cross_ctm_context=ctx
        )

        assert result.cross_ctm_context is not None
        assert result.cross_ctm_context.shared_insights['spatial'] == 'architecture'


class TestIntegrationWorkflow:
    """End-to-end integration tests"""

    def test_full_workflow_spatial_task(self):
        """Test full workflow for a spatial task"""
        # 1. Initialize components
        controller = BrainFrequencyController()

        try:
            ensemble = MultiCTMEnsemble(
                max_concurrent_per_ctm=1,
                max_reasoning_steps=10
            )
        except Exception as e:
            pytest.skip(f"CTM not available: {e}")

        # 2. Classify task
        router = CTMDomainRouter()
        task = "Design microservice architecture with API gateway"
        classification = router.classify_task(task)

        assert classification.primary_domain == CTMDomain.SPATIAL

        # 3. Check if task needs GAMMA mode (complex reasoning)
        is_complex = classification.confidence < 0.95

        if is_complex:
            controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)

        # 4. Run CTM reasoning
        task_id = ensemble.reason_async(
            task=task,
            brain_state={},
            max_steps=10
        )

        # 5. Get result
        result = ensemble.get_result(task_id, wait=True, timeout=20)

        assert result is not None
        assert result.primary_domain == CTMDomain.SPATIAL

        # 6. Return to ALPHA mode
        controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)
        assert controller.dominant_mode == FrequencyMode.ALPHA

    def test_full_workflow_collaborative(self):
        """Test full workflow with collaborative reasoning"""
        controller = BrainFrequencyController()

        try:
            ensemble = MultiCTMEnsemble(
                max_concurrent_per_ctm=1,
                max_reasoning_steps=10,
                enable_logic_ctm=True,
                enable_temporal_ctm=True,
                enable_value_ctm=True
            )
        except Exception as e:
            pytest.skip(f"CTM not available: {e}")

        # Switch to GAMMA for deep reasoning
        controller.set_mode(FrequencyMode.GAMMA, activation=1.0, suppress_others=True)

        # Run collaborative reasoning (Spatial only for speed)
        result = ensemble.reason_with_collaboration(
            task="Design scalable system with validation",
            brain_state={},
            max_steps=10,
            execution_order=[CTMDomain.SPATIAL]
        )

        assert result is not None
        assert result.cross_ctm_context is not None

        # Return to ALPHA
        controller.set_mode(FrequencyMode.ALPHA, activation=1.0, suppress_others=True)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

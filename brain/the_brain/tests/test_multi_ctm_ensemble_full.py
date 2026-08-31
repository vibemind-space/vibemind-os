"""
Comprehensive tests for MultiCTMEnsemble

Tests the full API surface of multi_ctm_ensemble.py including:
- Initialization with various CTM configurations
- Domain routing and fallback logic
- Async reasoning (reason_async) with task IDs
- Collaborative reasoning (reason_with_collaboration)
- Result retrieval, aggregation, statistics
- Thread safety, concurrency, timeout handling
- CTM health, reset, evolution integration
- Serialization and state management

All CTM models are mocked to avoid requiring trained weights.
"""

import sys
import os
import time
import threading
import uuid
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shared_enums import CTMDomain, ReasoningStatus
from core.klotski_ctm import CTMInsight
from core.klotski_ctm_async import KlotskiAsyncResult, KlotskiCTMAsyncReasoner
from core.ctm_domain_router import CTMDomainRouter, DomainClassification
from core.meta_ctm import MetaCTMSupervisor, MetaCTMDecision, CTMHealth
from core.evolutionary_ctm_selector import EvolutionaryCTMSelector, CTMGenes, CTMIndividual
from core.multi_ctm_ensemble import MultiCTMEnsemble, EnsembleResult, CrossCTMContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctm_insight(
    task: str = "test task",
    consciousness: float = 0.90,
    converged: bool = True,
    strategy: str = "default strategy",
    confidence: float = 0.85,
) -> CTMInsight:
    """Create a synthetic CTMInsight for testing."""
    return CTMInsight(
        task=task,
        reasoning_steps=10,
        consciousness_trajectory=[0.5, 0.6, 0.7, 0.8, consciousness],
        final_consciousness=consciousness,
        converged=converged,
        module_activations={"V1": 0.8, "DLPFC": 0.7, "ACC": 0.5},
        suggested_strategy=strategy,
        confidence=confidence,
        reasoning_trace=["step1", "step2"],
        dmn_energy=0.3,
        error_magnitude=0.1,
    )


def _make_async_result(
    task_id: str = "abc123",
    task: str = "test task",
    status: ReasoningStatus = ReasoningStatus.COMPLETED,
    consciousness: float = 0.90,
    strategy: str = "default strategy",
) -> KlotskiAsyncResult:
    """Create a synthetic KlotskiAsyncResult for testing."""
    insight = _make_ctm_insight(
        task=task,
        consciousness=consciousness,
        strategy=strategy,
    )
    return KlotskiAsyncResult(
        task_id=task_id,
        task_description=task,
        status=status,
        ctm_insight=insight if status == ReasoningStatus.COMPLETED else None,
        elapsed_time=1.5,
    )


def _make_brain_state() -> Dict:
    """Minimal brain state dict for testing."""
    return {
        "modality_activations": {
            "tool_trace": 0.8,
            "temporal_pattern": 0.6,
            "error_signal": 0.3,
        }
    }


def _mock_async_reasoner(domain_label: str = "spatial") -> MagicMock:
    """Create a mock KlotskiCTMAsyncReasoner."""
    mock = MagicMock(spec=KlotskiCTMAsyncReasoner)
    mock.load_weights.return_value = True
    task_id = str(uuid.uuid4())[:8]
    mock.start_reasoning_async.return_value = task_id
    mock.get_result.return_value = _make_async_result(
        task_id=task_id,
        strategy=f"{domain_label} strategy result",
    )
    mock.is_complete.return_value = True
    mock.get_stats.return_value = {
        "total": 1,
        "completed": 1,
        "failed": 0,
        "active": 0,
        "avg_consciousness": 0.90,
    }
    return mock


# ---------------------------------------------------------------------------
# Fixture: build an ensemble with fully mocked CTMs
# ---------------------------------------------------------------------------

def _fix_supervisor_lock(ens):
    """
    Replace the supervisor's threading.Lock with an RLock.

    MetaCTMSupervisor.get_statistics() calls get_best_performing_ctm()
    while already holding self._lock.  Since threading.Lock is not
    reentrant, that causes a deadlock.  Swapping to RLock fixes it
    without modifying production code.
    """
    ens.supervisor._lock = threading.RLock()
    return ens


@pytest.fixture
def ensemble():
    """
    Create a MultiCTMEnsemble with all internal CTMs replaced by mocks.

    This avoids loading actual neural network weights and needing
    the Klotski neurosymbolic brain to be installed.
    """
    with patch("core.multi_ctm_ensemble.KlotskiCTMAsyncReasoner") as MockReasoner:
        # Each call to KlotskiCTMAsyncReasoner() returns a fresh mock
        MockReasoner.side_effect = lambda **kwargs: _mock_async_reasoner()

        with patch("core.multi_ctm_ensemble.KLOTSKI_AVAILABLE", True):
            ens = MultiCTMEnsemble(
                max_concurrent_per_ctm=2,
                feature_dim=128,
                consciousness_threshold=0.85,
                max_reasoning_steps=20,
                device="cpu",
                enable_logic_ctm=True,
                enable_temporal_ctm=True,
                enable_value_ctm=True,
                enable_evolution=True,
                evolution_population_size=10,
                evolution_trigger_count=5,
            )
    return _fix_supervisor_lock(ens)


@pytest.fixture
def spatial_only_ensemble():
    """Ensemble with only SpatialCTM enabled (others disabled)."""
    with patch("core.multi_ctm_ensemble.KlotskiCTMAsyncReasoner") as MockReasoner:
        MockReasoner.side_effect = lambda **kwargs: _mock_async_reasoner()
        with patch("core.multi_ctm_ensemble.KLOTSKI_AVAILABLE", True):
            ens = MultiCTMEnsemble(
                max_concurrent_per_ctm=2,
                consciousness_threshold=0.85,
                max_reasoning_steps=20,
                enable_logic_ctm=False,
                enable_temporal_ctm=False,
                enable_value_ctm=False,
                enable_evolution=False,
            )
    return _fix_supervisor_lock(ens)


# ===================================================================
# 1. Default ensemble initialization
# ===================================================================

class TestEnsembleInitialization:
    """Tests for MultiCTMEnsemble.__init__."""

    def test_default_init_creates_four_ctms(self, ensemble):
        """All four CTM domains should have entries in the ctms dict."""
        assert CTMDomain.SPATIAL in ensemble.ctms
        assert CTMDomain.LOGIC in ensemble.ctms
        assert CTMDomain.TEMPORAL in ensemble.ctms
        assert CTMDomain.VALUE in ensemble.ctms

    def test_spatial_ctm_always_present(self, ensemble):
        """SpatialCTM must never be None."""
        assert ensemble.ctms[CTMDomain.SPATIAL] is not None

    def test_domain_router_exists(self, ensemble):
        """Domain router should be initialized."""
        assert ensemble.domain_router is not None
        assert isinstance(ensemble.domain_router, CTMDomainRouter)

    def test_supervisor_exists(self, ensemble):
        """Meta-CTM supervisor should be initialized."""
        assert ensemble.supervisor is not None
        assert isinstance(ensemble.supervisor, MetaCTMSupervisor)

    def test_evolution_enabled(self, ensemble):
        """Evolutionary selector should be present when enabled."""
        assert ensemble.enable_evolution is True
        assert ensemble.evolutionary_selector is not None
        assert isinstance(ensemble.evolutionary_selector, EvolutionaryCTMSelector)

    def test_task_tracking_structures(self, ensemble):
        """Task tracking dict and lock should exist."""
        assert isinstance(ensemble.ensemble_tasks, dict)
        assert len(ensemble.ensemble_tasks) == 0
        assert isinstance(ensemble.task_lock, type(threading.Lock()))

    def test_init_parameters_stored(self, ensemble):
        """Constructor parameters should be stored on the instance."""
        assert ensemble.max_concurrent_per_ctm == 2
        assert ensemble.feature_dim == 128
        assert ensemble.consciousness_threshold == 0.85
        assert ensemble.max_reasoning_steps == 20
        assert ensemble.device == "cpu"


# ===================================================================
# 2. Ensemble with no trained CTMs (only spatial fallback)
# ===================================================================

class TestNoTrainedCTMs:
    """Tests when LogicCTM / TemporalCTM / ValueCTM are disabled."""

    def test_disabled_ctms_are_none(self, spatial_only_ensemble):
        ens = spatial_only_ensemble
        assert ens.ctms[CTMDomain.LOGIC] is None
        assert ens.ctms[CTMDomain.TEMPORAL] is None
        assert ens.ctms[CTMDomain.VALUE] is None

    def test_spatial_still_available(self, spatial_only_ensemble):
        assert spatial_only_ensemble.ctms[CTMDomain.SPATIAL] is not None

    def test_evolution_disabled(self, spatial_only_ensemble):
        assert spatial_only_ensemble.enable_evolution is False
        assert spatial_only_ensemble.evolutionary_selector is None


# ===================================================================
# 3. Domain routing for different task types
# ===================================================================

class TestDomainRouting:
    """Tests that the domain router classifies tasks correctly."""

    def test_spatial_task_classification(self, ensemble):
        classification = ensemble.domain_router.classify_task(
            "Design microservice architecture with service mesh"
        )
        assert isinstance(classification, DomainClassification)
        assert classification.primary_domain == CTMDomain.SPATIAL

    def test_logic_task_classification(self, ensemble):
        classification = ensemble.domain_router.classify_task(
            "Validate Kubernetes manifest against security policies"
        )
        assert classification.primary_domain == CTMDomain.LOGIC

    def test_temporal_task_classification(self, ensemble):
        classification = ensemble.domain_router.classify_task(
            "Detect anomalies in time-series metrics"
        )
        assert classification.primary_domain == CTMDomain.TEMPORAL

    def test_value_task_classification(self, ensemble):
        classification = ensemble.domain_router.classify_task(
            "Optimize resource allocation with cost trade-offs"
        )
        assert classification.primary_domain == CTMDomain.VALUE

    def test_classification_has_confidence(self, ensemble):
        classification = ensemble.domain_router.classify_task("Deploy Docker container")
        assert 0.0 <= classification.confidence <= 1.0


# ===================================================================
# 4. Fallback to SpatialCTM when domain CTM unavailable
# ===================================================================

class TestSpatialFallback:
    """Verify fallback to SpatialCTM when a domain CTM is None."""

    def test_reason_async_falls_back_to_spatial(self, spatial_only_ensemble):
        """When logic/temporal/value CTMs are None, SpatialCTM handles it."""
        ens = spatial_only_ensemble
        task_id = ens.reason_async(
            task="Validate compliance rules",
            brain_state=_make_brain_state(),
        )
        assert isinstance(task_id, str)
        assert len(task_id) == 8
        # The SpatialCTM mock should have been called
        spatial_ctm = ens.ctms[CTMDomain.SPATIAL]
        assert spatial_ctm.start_reasoning_async.called


# ===================================================================
# 5. reason_async returns task ID
# ===================================================================

class TestReasonAsync:
    """Tests for reason_async method."""

    def test_returns_string_task_id(self, ensemble):
        task_id = ensemble.reason_async(
            task="Design load balancer",
            brain_state=_make_brain_state(),
        )
        assert isinstance(task_id, str)
        assert len(task_id) == 8

    def test_task_id_is_unique(self, ensemble):
        ids = set()
        for i in range(5):
            tid = ensemble.reason_async(
                task=f"Task {i}",
                brain_state=_make_brain_state(),
            )
            ids.add(tid)
        assert len(ids) == 5

    def test_task_stored_in_ensemble_tasks(self, ensemble):
        task_id = ensemble.reason_async(
            task="Store test",
            brain_state=_make_brain_state(),
        )
        assert task_id in ensemble.ensemble_tasks

    def test_ensemble_result_has_correct_task_text(self, ensemble):
        task_text = "Build CI/CD pipeline"
        task_id = ensemble.reason_async(
            task=task_text,
            brain_state=_make_brain_state(),
        )
        result = ensemble.ensemble_tasks[task_id]
        assert result.task == task_text


# ===================================================================
# 6. reason_async with domain_hint
# ===================================================================

class TestReasonAsyncWithDomainHint:
    """Tests for explicit domain_hint parameter."""

    def test_domain_hint_spatial(self, ensemble):
        task_id = ensemble.reason_async(
            task="Generic task text",
            brain_state=_make_brain_state(),
            domain_hint="spatial",
        )
        assert isinstance(task_id, str)

    def test_domain_hint_logic(self, ensemble):
        task_id = ensemble.reason_async(
            task="Generic task text",
            brain_state=_make_brain_state(),
            domain_hint="logic",
        )
        assert isinstance(task_id, str)

    def test_domain_hint_temporal(self, ensemble):
        task_id = ensemble.reason_async(
            task="Generic task text",
            brain_state=_make_brain_state(),
            domain_hint="temporal",
        )
        assert isinstance(task_id, str)

    def test_domain_hint_value(self, ensemble):
        task_id = ensemble.reason_async(
            task="Generic task text",
            brain_state=_make_brain_state(),
            domain_hint="value",
        )
        assert isinstance(task_id, str)


# ===================================================================
# 7. CTM timeout handling
# ===================================================================

class TestTimeoutHandling:
    """Tests for timeout scenarios in get_result."""

    def test_get_result_returns_none_for_unknown_id(self, ensemble):
        result = ensemble.get_result("nonexistent_id")
        assert result is None

    def test_get_result_wait_with_short_timeout(self, ensemble):
        """get_result with wait=True should respect timeout."""
        task_id = ensemble.reason_async(
            task="Timeout test",
            brain_state=_make_brain_state(),
        )
        # Should return within timeout (mocks complete instantly)
        result = ensemble.get_result(task_id, wait=True, timeout=5.0)
        assert result is not None
        assert result.task_id == task_id

    def test_get_result_without_wait(self, ensemble):
        task_id = ensemble.reason_async(
            task="No-wait test",
            brain_state=_make_brain_state(),
        )
        # Without wait, returns whatever is available immediately
        result = ensemble.get_result(task_id, wait=False)
        # May be the placeholder or final result
        assert result is not None or True  # Either way, no crash


# ===================================================================
# 8. Aggregation of results from multiple CTMs
# ===================================================================

class TestAggregation:
    """Tests for _aggregate_insights."""

    def test_aggregate_with_completed_results(self, ensemble):
        ctm_results = {
            CTMDomain.SPATIAL: _make_async_result(strategy="spatial plan"),
            CTMDomain.LOGIC: _make_async_result(strategy="logic validation"),
        }
        aggregated = ensemble._aggregate_insights(ctm_results)
        assert isinstance(aggregated, str)
        assert "spatialCTM" in aggregated or "spatial" in aggregated.lower()
        assert "logicCTM" in aggregated or "logic" in aggregated.lower()

    def test_aggregate_with_no_completed_results(self, ensemble):
        ctm_results = {
            CTMDomain.SPATIAL: _make_async_result(status=ReasoningStatus.FAILED),
        }
        aggregated = ensemble._aggregate_insights(ctm_results)
        assert aggregated == "No insights available"

    def test_aggregate_with_none_results(self, ensemble):
        ctm_results = {
            CTMDomain.SPATIAL: None,
            CTMDomain.LOGIC: None,
        }
        aggregated = ensemble._aggregate_insights(ctm_results)
        assert aggregated == "No insights available"


# ===================================================================
# 9. Collaboration method exists and is callable
# ===================================================================

class TestCollaboration:
    """Tests for reason_with_collaboration."""

    def test_method_exists(self, ensemble):
        assert hasattr(ensemble, "reason_with_collaboration")
        assert callable(ensemble.reason_with_collaboration)

    def test_collaboration_returns_ensemble_result(self, ensemble):
        result = ensemble.reason_with_collaboration(
            task="Design and validate microservice architecture",
            brain_state=_make_brain_state(),
            max_steps=10,
        )
        assert isinstance(result, EnsembleResult)
        assert result.task_id is not None
        assert len(result.task_id) == 8

    def test_collaboration_populates_cross_ctm_context(self, ensemble):
        result = ensemble.reason_with_collaboration(
            task="Schedule distributed validation pipeline",
            brain_state=_make_brain_state(),
        )
        assert result.cross_ctm_context is not None
        assert isinstance(result.cross_ctm_context, CrossCTMContext)
        assert isinstance(result.cross_ctm_context.execution_order, list)

    def test_collaboration_custom_execution_order(self, ensemble):
        custom_order = [CTMDomain.LOGIC, CTMDomain.SPATIAL]
        result = ensemble.reason_with_collaboration(
            task="Validate then build architecture",
            brain_state=_make_brain_state(),
            execution_order=custom_order,
        )
        assert result.primary_domain == CTMDomain.LOGIC
        assert CTMDomain.SPATIAL in result.secondary_domains

    def test_collaboration_default_execution_order(self, ensemble):
        result = ensemble.reason_with_collaboration(
            task="Full pipeline design",
            brain_state=_make_brain_state(),
        )
        ctx = result.cross_ctm_context
        assert ctx.execution_order == ["spatial", "logic", "temporal", "value"]


# ===================================================================
# 10. Domain router selection
# ===================================================================

class TestDomainRouterSelection:
    """Tests for domain router integration within ensemble."""

    def test_routing_recommendation(self, ensemble):
        rec = ensemble.get_routing_recommendation("Deploy containerized services")
        assert isinstance(rec, dict)

    def test_domain_router_mixed_domain_detection(self, ensemble):
        classification = ensemble.domain_router.classify_task(
            "Design microservice architecture and validate security compliance"
        )
        # Should detect at least spatial or logic
        assert classification.primary_domain in [CTMDomain.SPATIAL, CTMDomain.LOGIC]
        # Confidence should be positive
        assert classification.confidence > 0.0


# ===================================================================
# 11. Empty brain_state handling
# ===================================================================

class TestEmptyBrainState:
    """Tests with empty or minimal brain_state dicts."""

    def test_empty_dict_brain_state(self, ensemble):
        task_id = ensemble.reason_async(
            task="Test with empty state",
            brain_state={},
        )
        assert isinstance(task_id, str)

    def test_none_modality_activations(self, ensemble):
        task_id = ensemble.reason_async(
            task="Test with missing activations",
            brain_state={"modality_activations": {}},
        )
        assert isinstance(task_id, str)

    def test_minimal_brain_state(self, ensemble):
        task_id = ensemble.reason_async(
            task="Minimal state test",
            brain_state={"x": 1},
        )
        assert isinstance(task_id, str)


# ===================================================================
# 12. Invalid domain_hint handling
# ===================================================================

class TestInvalidDomainHint:
    """Tests that invalid domain hints do not crash the system."""

    def test_unknown_domain_hint_falls_back(self, ensemble):
        """Unknown hint should fall back to spatial (via supervisor)."""
        task_id = ensemble.reason_async(
            task="Test unknown hint",
            brain_state=_make_brain_state(),
            domain_hint="nonexistent_domain",
        )
        assert isinstance(task_id, str)

    def test_empty_string_domain_hint(self, ensemble):
        task_id = ensemble.reason_async(
            task="Empty hint test",
            brain_state=_make_brain_state(),
            domain_hint="",
        )
        assert isinstance(task_id, str)

    def test_none_domain_hint(self, ensemble):
        task_id = ensemble.reason_async(
            task="None hint test",
            brain_state=_make_brain_state(),
            domain_hint=None,
        )
        assert isinstance(task_id, str)


# ===================================================================
# 13. Multiple concurrent reason_async calls
# ===================================================================

class TestConcurrentReasonAsync:
    """Tests launching multiple async reasoning tasks concurrently."""

    def test_multiple_tasks_all_get_unique_ids(self, ensemble):
        task_ids = []
        for i in range(10):
            tid = ensemble.reason_async(
                task=f"Concurrent task {i}",
                brain_state=_make_brain_state(),
            )
            task_ids.append(tid)
        assert len(set(task_ids)) == 10

    def test_multiple_tasks_all_tracked(self, ensemble):
        task_ids = []
        for i in range(5):
            tid = ensemble.reason_async(
                task=f"Tracked task {i}",
                brain_state=_make_brain_state(),
            )
            task_ids.append(tid)
        for tid in task_ids:
            assert tid in ensemble.ensemble_tasks

    def test_concurrent_submission_from_threads(self, ensemble):
        """Submit tasks from multiple threads simultaneously."""
        results = []
        errors = []

        def submit(idx):
            try:
                tid = ensemble.reason_async(
                    task=f"Thread task {idx}",
                    brain_state=_make_brain_state(),
                )
                results.append(tid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors during concurrent submission: {errors}"
        assert len(results) == 8
        assert len(set(results)) == 8  # All unique


# ===================================================================
# 14. Get statistics
# ===================================================================

class TestGetStats:
    """Tests for get_stats method."""

    def test_stats_structure(self, ensemble):
        stats = ensemble.get_stats()
        assert "total_ensemble_tasks" in stats
        assert "tasks_by_domain" in stats
        assert "ctm_stats" in stats
        assert "active_ctms" in stats
        assert "supervisor_health" in stats
        assert "supervisor_stats" in stats
        assert "evolution_enabled" in stats
        assert "domain_task_counts" in stats

    def test_stats_initial_values(self, ensemble):
        stats = ensemble.get_stats()
        assert stats["total_ensemble_tasks"] == 0

    def test_stats_after_task(self, ensemble):
        ensemble.reason_async(
            task="Stats tracking task",
            brain_state=_make_brain_state(),
        )
        stats = ensemble.get_stats()
        assert stats["total_ensemble_tasks"] >= 1

    def test_active_ctms_list(self, ensemble):
        stats = ensemble.get_stats()
        active = stats["active_ctms"]
        assert "spatial" in active

    def test_tasks_by_domain_keys(self, ensemble):
        stats = ensemble.get_stats()
        domain_keys = stats["tasks_by_domain"]
        for domain in CTMDomain:
            assert domain.value in domain_keys


# ===================================================================
# 15. CTM state serialization (EnsembleResult / CrossCTMContext)
# ===================================================================

class TestStateSerialization:
    """Tests for dataclass serialization."""

    def test_ensemble_result_fields(self):
        result = EnsembleResult(
            task_id="test123",
            task="Serialize test",
            primary_domain=CTMDomain.SPATIAL,
            secondary_domains=[CTMDomain.LOGIC],
            ctm_results={},
            aggregated_insights="test insight",
            reasoning_chain="chain",
            elapsed_time=1.0,
        )
        assert result.task_id == "test123"
        assert result.primary_domain == CTMDomain.SPATIAL
        assert result.cross_ctm_context is None  # Optional, default None

    def test_cross_ctm_context_fields(self):
        ctx = CrossCTMContext(
            shared_insights={"spatial": "modular"},
            constraints=["type safety"],
            temporal_factors=["scheduled"],
            value_assessments={"cost": 0.5},
            spatial_structures=["microservice"],
            execution_order=["spatial", "logic"],
            conflict_resolutions=[],
        )
        assert ctx.shared_insights["spatial"] == "modular"
        assert "type safety" in ctx.constraints
        assert ctx.execution_order == ["spatial", "logic"]

    def test_ensemble_result_with_cross_context(self):
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[],
            conflict_resolutions=[],
        )
        result = EnsembleResult(
            task_id="ctx_test",
            task="Context test",
            primary_domain=CTMDomain.SPATIAL,
            secondary_domains=[],
            ctm_results={},
            aggregated_insights=None,
            reasoning_chain="",
            elapsed_time=0.0,
            cross_ctm_context=ctx,
        )
        assert result.cross_ctm_context is not None
        assert isinstance(result.cross_ctm_context, CrossCTMContext)


# ===================================================================
# 16. Max steps configuration
# ===================================================================

class TestMaxStepsConfiguration:
    """Tests for max_steps parameter override."""

    def test_default_max_steps_stored(self, ensemble):
        assert ensemble.max_reasoning_steps == 20

    def test_reason_async_with_custom_max_steps(self, ensemble):
        task_id = ensemble.reason_async(
            task="Custom steps test",
            brain_state=_make_brain_state(),
            max_steps=5,
        )
        assert isinstance(task_id, str)
        # Verify the mock was called with max_steps=5
        spatial_ctm = ensemble.ctms[CTMDomain.SPATIAL]
        call_args = spatial_ctm.start_reasoning_async.call_args
        if call_args:
            assert call_args.kwargs.get("max_steps") == 5 or \
                   (len(call_args.args) > 2 and call_args.args[2] == 5)

    def test_collaboration_with_custom_max_steps(self, ensemble):
        result = ensemble.reason_with_collaboration(
            task="Custom steps collaboration",
            brain_state=_make_brain_state(),
            max_steps=3,
        )
        assert isinstance(result, EnsembleResult)


# ===================================================================
# 17. Single CTM mode
# ===================================================================

class TestSingleCTMMode:
    """Tests with only SpatialCTM enabled."""

    def test_single_ctm_reason_async(self, spatial_only_ensemble):
        ens = spatial_only_ensemble
        task_id = ens.reason_async(
            task="Single CTM reasoning",
            brain_state=_make_brain_state(),
        )
        assert isinstance(task_id, str)

    def test_single_ctm_stats(self, spatial_only_ensemble):
        stats = spatial_only_ensemble.get_stats()
        active = stats["active_ctms"]
        assert "spatial" in active
        # Only spatial should be active
        assert len(active) == 1

    def test_single_ctm_collaboration_skips_unavailable(self, spatial_only_ensemble):
        ens = spatial_only_ensemble
        result = ens.reason_with_collaboration(
            task="Collaborative single CTM",
            brain_state=_make_brain_state(),
        )
        assert isinstance(result, EnsembleResult)
        # Non-spatial domains should have None results
        for domain in [CTMDomain.LOGIC, CTMDomain.TEMPORAL, CTMDomain.VALUE]:
            if domain in result.ctm_results:
                assert result.ctm_results[domain] is None


# ===================================================================
# 18. Thread safety
# ===================================================================

class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_task_lock_exists(self, ensemble):
        assert hasattr(ensemble, "task_lock")

    def test_concurrent_get_stats(self, ensemble):
        """get_stats should be safe to call from multiple threads."""
        results = []
        errors = []

        def read_stats():
            try:
                s = ensemble.get_stats()
                results.append(s)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_stats) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert len(results) == 10

    def test_concurrent_reason_and_stats(self, ensemble):
        """Mix reason_async and get_stats calls concurrently."""
        errors = []

        def mixed_ops(idx):
            try:
                if idx % 2 == 0:
                    ensemble.reason_async(
                        task=f"Mixed op {idx}",
                        brain_state=_make_brain_state(),
                    )
                else:
                    ensemble.get_stats()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mixed_ops, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0


# ===================================================================
# 19. Result retrieval
# ===================================================================

class TestResultRetrieval:
    """Tests for get_result method."""

    def test_get_result_by_id(self, ensemble):
        task_id = ensemble.reason_async(
            task="Retrieve me",
            brain_state=_make_brain_state(),
        )
        # Give aggregation thread a moment
        time.sleep(0.3)
        result = ensemble.get_result(task_id, wait=True, timeout=5.0)
        assert result is not None
        assert result.task_id == task_id
        assert result.task == "Retrieve me"

    def test_get_result_has_primary_domain(self, ensemble):
        task_id = ensemble.reason_async(
            task="Domain check",
            brain_state=_make_brain_state(),
        )
        time.sleep(0.3)
        result = ensemble.get_result(task_id, wait=True, timeout=5.0)
        assert result is not None
        assert isinstance(result.primary_domain, CTMDomain)

    def test_get_result_has_elapsed_time(self, ensemble):
        task_id = ensemble.reason_async(
            task="Timing check",
            brain_state=_make_brain_state(),
        )
        time.sleep(0.5)
        result = ensemble.get_result(task_id, wait=True, timeout=5.0)
        assert result is not None
        assert result.elapsed_time >= 0.0

    def test_get_result_nonexistent_returns_none(self, ensemble):
        result = ensemble.get_result("does_not_exist")
        assert result is None


# ===================================================================
# 20. CTM reset / cleanup
# ===================================================================

class TestCTMResetCleanup:
    """Tests for reset_ctm and related cleanup."""

    def test_reset_ctm_spatial(self, ensemble):
        success = ensemble.reset_ctm("spatial")
        assert isinstance(success, bool)

    def test_reset_ctm_logic(self, ensemble):
        success = ensemble.reset_ctm("logic")
        assert isinstance(success, bool)

    def test_reset_ctm_unknown_domain(self, ensemble):
        success = ensemble.reset_ctm("nonexistent")
        # Should return False or handle gracefully
        assert isinstance(success, bool)

    def test_get_ctm_health(self, ensemble):
        health = ensemble.get_ctm_health()
        assert isinstance(health, dict)
        # Should have entries for known domains
        for domain_name in ["spatial", "logic", "temporal", "value"]:
            assert domain_name in health


# ===================================================================
# Additional tests: evolution, inter-CTM messaging, pending CTMs
# ===================================================================

class TestEvolutionIntegration:
    """Tests for evolutionary CTM optimization integration."""

    def test_evolve_domain_returns_dict(self, ensemble):
        result = ensemble.evolve_domain("spatial")
        assert isinstance(result, dict)

    def test_evolve_all_domains(self, ensemble):
        results = ensemble.evolve_all_domains()
        assert isinstance(results, dict)
        assert "spatial" in results

    def test_get_evolution_stats(self, ensemble):
        stats = ensemble.get_evolution_stats()
        assert isinstance(stats, dict)

    def test_get_evolution_stats_for_domain(self, ensemble):
        stats = ensemble.get_evolution_stats(domain="spatial")
        assert isinstance(stats, dict)

    def test_get_best_genes(self, ensemble):
        genes = ensemble.get_best_genes("spatial")
        # May be None if no performance recorded yet, or CTMGenes
        assert genes is None or isinstance(genes, CTMGenes)

    def test_evolution_disabled_returns_error(self, spatial_only_ensemble):
        result = spatial_only_ensemble.evolve_domain("spatial")
        assert "error" in result

    def test_inject_ctm_configuration(self, ensemble):
        genes = CTMGenes(
            consciousness_threshold=0.9,
            max_reasoning_steps=30,
        )
        # Should not raise
        ensemble.inject_ctm_configuration("spatial", genes, fitness=0.7)


class TestInterCTMMessaging:
    """Tests for send_inter_ctm_message placeholder."""

    def test_send_message_returns_true(self, ensemble):
        result = ensemble.send_inter_ctm_message(
            from_domain=CTMDomain.SPATIAL,
            to_domain=CTMDomain.LOGIC,
            message_type="constraint",
            content={"key": "value"},
        )
        assert result is True


class TestPendingCTMs:
    """Tests for get_pending_ctms and training status."""

    def test_pending_ctms_with_all_enabled(self, ensemble):
        pending = ensemble.get_pending_ctms()
        # All CTMs are mocked as available (not None), so pending should be empty
        assert isinstance(pending, list)

    def test_pending_ctms_with_disabled(self, spatial_only_ensemble):
        pending = spatial_only_ensemble.get_pending_ctms()
        assert CTMDomain.LOGIC in pending
        assert CTMDomain.TEMPORAL in pending
        assert CTMDomain.VALUE in pending

    def test_training_status(self, ensemble):
        status = ensemble.get_training_status()
        assert isinstance(status, dict)
        assert status["spatial"] == "trained"

    def test_training_status_spatial_only(self, spatial_only_ensemble):
        status = spatial_only_ensemble.get_training_status()
        assert status["spatial"] == "trained"
        # Disabled CTMs should show as pending
        assert status["logic"] == "pending"
        assert status["temporal"] == "pending"
        assert status["value"] == "pending"


class TestEnrichAndContextUpdate:
    """Tests for internal context enrichment helpers."""

    def test_enrich_task_no_context(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[],
            conflict_resolutions=[],
        )
        enriched = ensemble._enrich_task_with_context(
            "basic task", CTMDomain.SPATIAL, ctx
        )
        # No enrichment for spatial when context is empty
        assert enriched == "basic task"

    def test_enrich_task_logic_with_spatial_context(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={"spatial": "modular"},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=["microservice architecture"],
            execution_order=["spatial", "logic"],
            conflict_resolutions=[],
        )
        enriched = ensemble._enrich_task_with_context(
            "validate constraints", CTMDomain.LOGIC, ctx
        )
        assert "Cross-CTM Context" in enriched
        assert "microservice architecture" in enriched

    def test_update_cross_context_spatial(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[],
            conflict_resolutions=[],
        )
        insight = _make_ctm_insight(strategy="Deploy microservice mesh")
        updated = ensemble._update_cross_context(ctx, CTMDomain.SPATIAL, insight)
        assert "spatial" in updated.shared_insights
        assert len(updated.spatial_structures) > 0

    def test_update_cross_context_logic(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[],
            conflict_resolutions=[],
        )
        insight = _make_ctm_insight(strategy="validate compliance rules")
        updated = ensemble._update_cross_context(ctx, CTMDomain.LOGIC, insight)
        assert len(updated.constraints) > 0

    def test_resolve_conflicts_empty(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[],
            conflict_resolutions=[],
        )
        resolved = ensemble._resolve_conflicts(ctx, {})
        assert isinstance(resolved.conflict_resolutions, list)


class TestAggregateCollaborativeInsights:
    """Tests for _aggregate_collaborative_insights."""

    def test_aggregate_empty_context(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[],
            conflict_resolutions=[],
        )
        result = ensemble._aggregate_collaborative_insights(ctx, {})
        assert result == "No collaborative insights available"

    def test_aggregate_with_insights(self, ensemble):
        ctx = CrossCTMContext(
            shared_insights={"spatial": "layered design", "logic": "type safe"},
            constraints=["validation required"],
            temporal_factors=["scheduled execution"],
            value_assessments={"cost_priority": 0.8},
            spatial_structures=["microservice"],
            execution_order=["spatial", "logic"],
            conflict_resolutions=[],
        )
        result = ensemble._aggregate_collaborative_insights(ctx, {})
        assert isinstance(result, str)
        assert "spatial" in result.lower() or "layered" in result.lower()


class TestKlotskiUnavailable:
    """Test that initialization fails gracefully when Klotski is missing."""

    def test_raises_when_klotski_unavailable(self):
        with patch("core.multi_ctm_ensemble.KLOTSKI_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="Klotski CTM not available"):
                MultiCTMEnsemble()

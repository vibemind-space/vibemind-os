"""
Tests for SubsystemRegistry (P4.51-54)
Covers: registry, circuit breaker, health reporting, dependency graph.
"""

import sys
import os
import time
import threading
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.subsystem_registry import (
    SubsystemRegistry, SubsystemStatus, HealthLevel,
    CircuitBreakerState, SubsystemInfo, DEFAULT_DEPENDENCY_GRAPH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeSubsystem:
    """A minimal fake subsystem for testing."""
    def __init__(self, name="fake"):
        self.name = name
        self.call_count = 0

    def do_work(self):
        self.call_count += 1
        return f"done:{self.name}"


class FailingSubsystem:
    """A subsystem that always raises."""
    def do_work(self):
        raise RuntimeError("subsystem crashed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    return SubsystemRegistry(circuit_breaker_threshold=3,
                             circuit_breaker_reset_seconds=0.5)


@pytest.fixture
def populated_registry(registry):
    """Registry with several subsystems registered."""
    registry.register('layer1', FakeSubsystem('layer1'), category='core')
    registry.register('layer2', FakeSubsystem('layer2'), depends_on=['layer1'], category='core')
    registry.register('layer3', FakeSubsystem('layer3'), depends_on=['layer2'], category='core')
    registry.register('memory', FakeSubsystem('memory'), category='cognitive')
    registry.register('attention', FakeSubsystem('attention'), category='cognitive')
    registry.register('neuromod', FakeSubsystem('neuromod'), category='cognitive')
    registry.register('consciousness', FakeSubsystem('consciousness'), category='monitoring')
    registry.register('dream_mode', FakeSubsystem('dream'), depends_on=['memory'], category='optional')
    return registry


# ===========================================================================
# P4.52: SubsystemRegistry - Registration & Access
# ===========================================================================

class TestRegistryBasics:

    def test_register_and_get(self, registry):
        sub = FakeSubsystem('test')
        registry.register('test', sub)
        assert registry.get('test') is sub

    def test_get_unregistered_returns_none(self, registry):
        assert registry.get('nonexistent') is None

    def test_is_active_registered(self, registry):
        registry.register('test', FakeSubsystem())
        assert registry.is_active('test') is True

    def test_is_active_unregistered(self, registry):
        assert registry.is_active('nonexistent') is False

    def test_is_registered(self, registry):
        registry.register('test', FakeSubsystem())
        assert registry.is_registered('test') is True
        assert registry.is_registered('other') is False

    def test_unregister(self, registry):
        registry.register('test', FakeSubsystem())
        registry.unregister('test')
        assert registry.get('test') is None
        assert registry.is_registered('test') is False

    def test_unregister_nonexistent_no_error(self, registry):
        registry.unregister('nonexistent')  # Should not raise

    def test_use_count_increments(self, registry):
        registry.register('test', FakeSubsystem())
        registry.get('test')
        registry.get('test')
        registry.get('test')
        info = registry._subsystems['test']
        assert info.use_count == 3

    def test_last_used_updated(self, registry):
        registry.register('test', FakeSubsystem())
        before = time.time()
        registry.get('test')
        info = registry._subsystems['test']
        assert info.last_used >= before

    def test_register_with_defaults_from_graph(self, registry):
        """Dependencies and category auto-filled from DEFAULT_DEPENDENCY_GRAPH."""
        registry.register('memory', FakeSubsystem())
        info = registry._subsystems['memory']
        assert info.category == 'cognitive'
        assert 'MemoryManager' in info.description

    def test_register_override_defaults(self, registry):
        """Explicit args override defaults from dependency graph."""
        registry.register('memory', FakeSubsystem(), depends_on=['layer1'],
                          category='optional', description='custom')
        info = registry._subsystems['memory']
        assert info.depends_on == ['layer1']
        assert info.category == 'optional'
        assert info.description == 'custom'


class TestRegistryListing:

    def test_list_names_all(self, populated_registry):
        names = populated_registry.list_names()
        assert len(names) == 8
        assert 'layer1' in names
        assert 'memory' in names

    def test_list_names_by_category(self, populated_registry):
        core_names = populated_registry.list_names(category='core')
        assert set(core_names) == {'layer1', 'layer2', 'layer3'}

    def test_list_names_by_status(self, populated_registry):
        populated_registry.disable('memory')
        active = populated_registry.list_names(status=SubsystemStatus.ACTIVE)
        assert 'memory' not in active
        disabled = populated_registry.list_names(status=SubsystemStatus.DISABLED)
        assert disabled == ['memory']

    def test_get_all_active(self, populated_registry):
        all_active = populated_registry.get_all()
        assert len(all_active) == 8
        assert isinstance(all_active['layer1'], FakeSubsystem)

    def test_get_all_by_category(self, populated_registry):
        cognitive = populated_registry.get_all(category='cognitive')
        assert set(cognitive.keys()) == {'memory', 'attention', 'neuromod'}


# ===========================================================================
# P4.52: Status Management
# ===========================================================================

class TestStatusManagement:

    def test_disable_subsystem(self, registry):
        registry.register('test', FakeSubsystem())
        registry.disable('test')
        assert registry.is_active('test') is False
        assert registry.get('test') is None

    def test_enable_subsystem(self, registry):
        registry.register('test', FakeSubsystem())
        registry.disable('test')
        registry.enable('test')
        assert registry.is_active('test') is True
        assert registry.get('test') is not None

    def test_set_status_degraded(self, registry):
        registry.register('test', FakeSubsystem())
        registry.set_status('test', SubsystemStatus.DEGRADED)
        assert registry.is_active('test') is True  # Degraded is still active
        info = registry._subsystems['test']
        assert info.status == SubsystemStatus.DEGRADED

    def test_set_status_failed(self, registry):
        registry.register('test', FakeSubsystem())
        registry.set_status('test', SubsystemStatus.FAILED)
        assert registry.is_active('test') is False
        assert registry.get('test') is None

    def test_set_status_nonexistent(self, registry):
        registry.set_status('nonexistent', SubsystemStatus.ACTIVE)  # No error


# ===========================================================================
# P4.53: Circuit Breaker
# ===========================================================================

class TestCircuitBreakerState:

    def test_initial_state(self):
        cb = CircuitBreakerState(failure_threshold=3)
        assert cb.failure_count == 0
        assert cb.is_open is False
        assert cb.should_attempt() is True

    def test_failures_below_threshold(self):
        cb = CircuitBreakerState(failure_threshold=3)
        cb.record_failure(RuntimeError("err1"))
        cb.record_failure(RuntimeError("err2"))
        assert cb.failure_count == 2
        assert cb.is_open is False
        assert cb.should_attempt() is True

    def test_circuit_opens_at_threshold(self):
        cb = CircuitBreakerState(failure_threshold=3)
        cb.record_failure(RuntimeError("err1"))
        cb.record_failure(RuntimeError("err2"))
        just_opened = cb.record_failure(RuntimeError("err3"))
        assert just_opened is True
        assert cb.is_open is True
        assert cb.should_attempt() is False

    def test_circuit_stays_open_after_threshold(self):
        cb = CircuitBreakerState(failure_threshold=3)
        for i in range(5):
            cb.record_failure(RuntimeError(f"err{i}"))
        assert cb.is_open is True
        assert cb.failure_count == 5

    def test_half_open_after_reset_timeout(self):
        cb = CircuitBreakerState(failure_threshold=2, reset_timeout_seconds=0.1)
        cb.record_failure(RuntimeError("err1"))
        cb.record_failure(RuntimeError("err2"))
        assert cb.is_open is True
        assert cb.should_attempt() is False
        time.sleep(0.15)
        assert cb.should_attempt() is True  # Half-open

    def test_success_closes_circuit(self):
        cb = CircuitBreakerState(failure_threshold=2)
        cb.record_failure(RuntimeError("err1"))
        cb.record_failure(RuntimeError("err2"))
        assert cb.is_open is True
        cb.record_success()
        assert cb.is_open is False
        assert cb.failure_count == 0

    def test_to_dict(self):
        cb = CircuitBreakerState(failure_threshold=3)
        cb.record_failure(RuntimeError("test error"))
        d = cb.to_dict()
        assert d['failure_count'] == 1
        assert d['is_open'] is False
        assert 'test error' in d['last_failure_error']


class TestCircuitBreakerInRegistry:

    def test_record_failure_increments(self, registry):
        registry.register('test', FakeSubsystem())
        registry.record_failure('test', RuntimeError("oops"))
        info = registry._subsystems['test']
        assert info.circuit_breaker.failure_count == 1

    def test_circuit_opens_after_threshold(self, registry):
        registry.register('test', FakeSubsystem())
        registry.record_failure('test', RuntimeError("err1"))
        registry.record_failure('test', RuntimeError("err2"))
        opened = registry.record_failure('test', RuntimeError("err3"))
        assert opened is True
        assert registry._subsystems['test'].status == SubsystemStatus.CIRCUIT_OPEN
        assert registry.is_active('test') is False

    def test_circuit_open_blocks_get(self, registry):
        registry.register('test', FakeSubsystem())
        for i in range(3):
            registry.record_failure('test', RuntimeError(f"err{i}"))
        assert registry.get('test') is None

    def test_circuit_half_open_after_timeout(self, registry):
        """After reset timeout, subsystem becomes accessible again (half-open)."""
        registry.register('test', FakeSubsystem())
        for i in range(3):
            registry.record_failure('test', RuntimeError(f"err{i}"))
        assert registry.get('test') is None
        time.sleep(0.6)  # Wait for reset timeout (0.5s)
        # Half-open: should allow one attempt
        assert registry.get('test') is not None

    def test_record_success_closes_circuit(self, registry):
        registry.register('test', FakeSubsystem())
        for i in range(3):
            registry.record_failure('test', RuntimeError(f"err{i}"))
        assert registry.is_active('test') is False
        registry.record_success('test')
        assert registry.is_active('test') is True
        assert registry._subsystems['test'].status == SubsystemStatus.ACTIVE

    def test_error_log_maintained(self, registry):
        registry.register('test', FakeSubsystem())
        registry.record_failure('test', ValueError("bad value"))
        info = registry._subsystems['test']
        assert len(info.error_log) == 1
        assert 'bad value' in info.error_log[0]['error']
        assert info.error_log[0]['error_type'] == 'ValueError'

    def test_error_log_capped_at_20(self, registry):
        registry.register('test', FakeSubsystem())
        for i in range(25):
            registry.record_failure('test', RuntimeError(f"err{i}"))
        info = registry._subsystems['test']
        assert len(info.error_log) == 20

    def test_record_failure_nonexistent(self, registry):
        result = registry.record_failure('nonexistent', RuntimeError("oops"))
        assert result is False

    def test_record_success_nonexistent(self, registry):
        registry.record_success('nonexistent')  # Should not raise


# ===========================================================================
# P4.54: Health Reporting
# ===========================================================================

class TestHealthReporting:

    def test_subsystem_health_green(self, registry):
        registry.register('test', FakeSubsystem())
        health = registry.get_subsystem_health('test')
        assert health['health'] == 'green'
        assert health['status'] == 'active'

    def test_subsystem_health_yellow_with_failures(self, registry):
        registry.register('test', FakeSubsystem())
        registry.record_failure('test', RuntimeError("oops"))
        health = registry.get_subsystem_health('test')
        assert health['health'] == 'yellow'
        assert '1 recent failures' in health['reason']

    def test_subsystem_health_red_circuit_open(self, registry):
        registry.register('test', FakeSubsystem())
        for i in range(3):
            registry.record_failure('test', RuntimeError(f"err{i}"))
        health = registry.get_subsystem_health('test')
        assert health['health'] == 'red'
        assert 'circuit open' in health['reason']

    def test_subsystem_health_offline_disabled(self, registry):
        registry.register('test', FakeSubsystem())
        registry.disable('test')
        health = registry.get_subsystem_health('test')
        assert health['health'] == 'offline'

    def test_subsystem_health_unregistered(self, registry):
        health = registry.get_subsystem_health('nonexistent')
        assert health['health'] == 'offline'
        assert 'not registered' in health['reason']

    def test_subsystem_health_degraded(self, registry):
        registry.register('test', FakeSubsystem())
        registry.set_status('test', SubsystemStatus.DEGRADED)
        health = registry.get_subsystem_health('test')
        assert health['health'] == 'yellow'

    def test_health_report_all_green(self, populated_registry):
        report = populated_registry.get_health_report()
        assert report['overall_health'] == 'green'
        assert report['active'] == 8
        assert report['circuit_open'] == 0
        assert report['total_subsystems'] == 8

    def test_health_report_with_failure(self, populated_registry):
        for i in range(3):
            populated_registry.record_failure('memory', RuntimeError(f"err{i}"))
        report = populated_registry.get_health_report()
        assert report['overall_health'] == 'red'
        assert report['circuit_open'] == 1

    def test_health_report_with_degraded(self, populated_registry):
        populated_registry.set_status('attention', SubsystemStatus.DEGRADED)
        report = populated_registry.get_health_report()
        assert report['overall_health'] == 'yellow'
        assert report['degraded'] == 1

    def test_health_report_uptime(self, registry):
        registry.register('test', FakeSubsystem())
        report = registry.get_health_report()
        assert report['uptime_seconds'] >= 0

    def test_health_report_dependency_issues(self, registry):
        """Dependency on missing subsystem shows in report."""
        registry.register('dream', FakeSubsystem(), depends_on=['memory'])
        report = registry.get_health_report()
        assert len(report['dependency_issues']) > 0
        assert 'memory' in report['dependency_issues'][0]

    def test_health_report_dependency_circuit_open(self, populated_registry):
        """Dependency on circuit-open subsystem shows in report."""
        for i in range(3):
            populated_registry.record_failure('memory', RuntimeError(f"err{i}"))
        report = populated_registry.get_health_report()
        issues = report['dependency_issues']
        # dream_mode depends on memory which is now circuit_open
        assert any('dream_mode' in issue and 'memory' in issue for issue in issues)

    def test_health_report_subsystems_dict(self, populated_registry):
        report = populated_registry.get_health_report()
        assert 'layer1' in report['subsystems']
        assert report['subsystems']['layer1']['health'] == 'green'


# ===========================================================================
# P4.51: Dependency Graph
# ===========================================================================

class TestDependencyGraph:

    def test_dependency_graph_structure(self, populated_registry):
        graph = populated_registry.get_dependency_graph()
        assert 'layer1' in graph
        assert graph['layer2']['depends_on'] == ['layer1']
        assert graph['layer3']['depends_on'] == ['layer2']

    def test_reverse_dependencies(self, populated_registry):
        graph = populated_registry.get_dependency_graph()
        assert 'layer2' in graph['layer1']['depended_by']
        assert 'layer3' in graph['layer2']['depended_by']
        assert 'dream_mode' in graph['memory']['depended_by']

    def test_initialization_order(self, populated_registry):
        order = populated_registry.get_initialization_order()
        assert len(order) == 8
        # layer1 must come before layer2
        assert order.index('layer1') < order.index('layer2')
        # layer2 must come before layer3
        assert order.index('layer2') < order.index('layer3')
        # memory must come before dream_mode
        assert order.index('memory') < order.index('dream_mode')

    def test_check_dependencies_satisfied(self, populated_registry):
        satisfied, issues = populated_registry.check_dependencies('layer2')
        assert satisfied is True
        assert issues == []

    def test_check_dependencies_missing(self, registry):
        registry.register('dream', FakeSubsystem(), depends_on=['memory'])
        satisfied, issues = registry.check_dependencies('dream')
        assert satisfied is False
        assert len(issues) == 1
        assert 'memory' in issues[0]

    def test_check_dependencies_inactive(self, populated_registry):
        populated_registry.disable('memory')
        satisfied, issues = populated_registry.check_dependencies('dream_mode')
        assert satisfied is False
        assert any('memory' in i for i in issues)

    def test_check_dependencies_unregistered_subsystem(self, registry):
        satisfied, issues = registry.check_dependencies('nonexistent')
        assert satisfied is False

    def test_initialization_order_no_deps(self, registry):
        registry.register('a', FakeSubsystem())
        registry.register('b', FakeSubsystem())
        order = registry.get_initialization_order()
        assert set(order) == {'a', 'b'}

    def test_default_dependency_graph_completeness(self):
        """DEFAULT_DEPENDENCY_GRAPH should cover all major subsystems."""
        expected = {'layer1', 'layer2', 'layer3', 'memory', 'attention',
                    'neuromodulation', 'predictive_coding', 'consciousness',
                    'emotional', 'goal_graph', 'ctm_ensemble', 'dream_mode',
                    'cognitive_loop', 'heartbeat', 'brain_monitor'}
        actual = set(DEFAULT_DEPENDENCY_GRAPH.keys())
        for name in expected:
            assert name in actual, f"Missing from DEFAULT_DEPENDENCY_GRAPH: {name}"


# ===========================================================================
# Thread Safety
# ===========================================================================

class TestThreadSafety:

    def test_concurrent_register_and_get(self, registry):
        """Concurrent register + get should not crash."""
        errors = []

        def register_worker(n):
            try:
                for i in range(20):
                    registry.register(f'sub_{n}_{i}', FakeSubsystem(f'{n}_{i}'))
            except Exception as e:
                errors.append(e)

        def get_worker():
            try:
                for _ in range(100):
                    registry.get('sub_0_5')
                    registry.is_active('sub_1_10')
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_worker, args=(0,)),
            threading.Thread(target=register_worker, args=(1,)),
            threading.Thread(target=get_worker),
            threading.Thread(target=get_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0

    def test_concurrent_failure_recording(self, registry):
        """Concurrent failure recording should not corrupt state."""
        registry.register('test', FakeSubsystem())
        errors = []

        def fail_worker():
            try:
                for i in range(10):
                    registry.record_failure('test', RuntimeError(f"err_{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        info = registry._subsystems['test']
        assert info.circuit_breaker.failure_count == 40
        assert info.circuit_breaker.is_open is True


# ===========================================================================
# Summary & Serialization
# ===========================================================================

class TestSummaryAndSerialization:

    def test_summary_nonempty(self, populated_registry):
        summary = populated_registry.summary()
        assert 'BRAIN SUBSYSTEM REGISTRY' in summary
        assert 'layer1' in summary
        assert 'CORE' in summary

    def test_summary_shows_status(self, populated_registry):
        populated_registry.disable('memory')
        summary = populated_registry.summary()
        assert 'disabled' in summary

    def test_to_dict_structure(self, populated_registry):
        d = populated_registry.to_dict()
        assert 'subsystems' in d
        assert 'health' in d
        assert 'dependency_graph' in d
        assert 'initialization_order' in d
        assert 'layer1' in d['subsystems']

    def test_to_dict_serializable(self, populated_registry):
        """to_dict output should be JSON-serializable."""
        import json
        d = populated_registry.to_dict()
        json_str = json.dumps(d)  # Should not raise
        assert len(json_str) > 0

    def test_subsystem_info_to_dict(self, populated_registry):
        info = populated_registry._subsystems['layer1']
        d = info.to_dict()
        assert d['name'] == 'layer1'
        assert d['status'] == 'active'
        assert 'circuit_breaker' in d


# ===========================================================================
# Edge Cases
# ===========================================================================

class TestEdgeCases:

    def test_empty_registry_health(self, registry):
        report = registry.get_health_report()
        assert report['overall_health'] == 'green'
        assert report['total_subsystems'] == 0

    def test_empty_registry_summary(self, registry):
        summary = registry.summary()
        assert 'BRAIN SUBSYSTEM REGISTRY' in summary

    def test_empty_registry_to_dict(self, registry):
        d = registry.to_dict()
        assert d['subsystems'] == {}

    def test_register_same_name_overwrites(self, registry):
        sub1 = FakeSubsystem('first')
        sub2 = FakeSubsystem('second')
        registry.register('test', sub1)
        registry.register('test', sub2)
        assert registry.get('test') is sub2

    def test_none_instance_registered(self, registry):
        registry.register('test', None)
        assert registry.get('test') is None
        assert registry.is_active('test') is True  # Status is active even if instance is None

    def test_enable_resets_circuit_breaker(self, registry):
        registry.register('test', FakeSubsystem())
        for i in range(3):
            registry.record_failure('test', RuntimeError(f"err{i}"))
        assert registry._subsystems['test'].circuit_breaker.is_open is True
        registry.enable('test')
        assert registry._subsystems['test'].circuit_breaker.is_open is False
        assert registry._subsystems['test'].circuit_breaker.failure_count == 0

    def test_get_disabled_returns_none(self, registry):
        registry.register('test', FakeSubsystem())
        registry.disable('test')
        assert registry.get('test') is None

    def test_multiple_categories(self, populated_registry):
        """All four categories present."""
        core = populated_registry.list_names(category='core')
        cognitive = populated_registry.list_names(category='cognitive')
        monitoring = populated_registry.list_names(category='monitoring')
        optional = populated_registry.list_names(category='optional')
        assert len(core) > 0
        assert len(cognitive) > 0
        assert len(monitoring) > 0
        assert len(optional) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

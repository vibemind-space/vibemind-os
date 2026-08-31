"""
Test Ecosystem Intelligence Modules (V2 Phase 8: P8.96-100)

Tests for:
  - OrchestratorOfOrchestrators (P8.96)
  - SystemSynergyLearning (P8.97)
  - KnowledgeExport (P8.98)
  - EvolutionaryGrowth (P8.99)
  - ConsciousnessEvolution (P8.100)
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.ecosystem_intelligence import (
    OrchestratorOfOrchestrators,
    SystemSynergyLearning,
    KnowledgeExport,
    EvolutionaryGrowth,
    ConsciousnessEvolution,
)


# ═══════════════════════════════════════════════════════════════════════
# OrchestratorOfOrchestrators (P8.96)
# ═══════════════════════════════════════════════════════════════════════

class TestOrchestratorOfOrchestrators:
    """Tests for the meta-orchestrator coordinating sub-orchestrators."""

    def test_register_and_assign(self):
        oo = OrchestratorOfOrchestrators()
        oo.register_orchestrator(
            'code_gen', 'http://localhost:6001', ['coding', 'testing']
        )
        assignment = oo.assign_goal(
            'Write unit tests', required_capabilities=['coding']
        )
        assert assignment['status'] == 'assigned'
        assert assignment['orchestrator_name'] == 'code_gen'

    def test_assign_no_match(self):
        oo = OrchestratorOfOrchestrators()
        oo.register_orchestrator(
            'code_gen', 'http://localhost:6001', ['coding']
        )
        assignment = oo.assign_goal(
            'Deploy to cloud', required_capabilities=['cloud_deploy']
        )
        assert assignment['status'] == 'no_match'
        assert assignment['orchestrator_name'] is None

    def test_record_outcome_updates_stats(self):
        oo = OrchestratorOfOrchestrators()
        oo.register_orchestrator(
            'deploy_bot', 'http://localhost:6002', ['deployment']
        )
        oo.record_outcome('deploy_bot', 'goal_1', success=True, duration_ms=500)
        stats = oo.get_orchestrator_stats()
        assert stats['deploy_bot']['total_goals'] == 1
        assert stats['deploy_bot']['successful_goals'] == 1

    def test_degraded_on_low_success(self):
        oo = OrchestratorOfOrchestrators(degraded_threshold=0.3)
        oo.register_orchestrator(
            'bad_bot', 'http://localhost:6003', ['testing']
        )
        # Record 5 failures to cross the degraded threshold
        for i in range(5):
            oo.record_outcome('bad_bot', f'goal_{i}', success=False, duration_ms=100)
        stats = oo.get_orchestrator_stats()
        assert stats['bad_bot']['status'] == 'degraded'

    def test_from_yaml(self):
        oo = OrchestratorOfOrchestrators.from_yaml({
            'ecosystem_intelligence': {
                'orchestrator_of_orchestrators': {
                    'max_history': 100,
                    'degraded_threshold': 0.5,
                }
            }
        })
        assert oo.max_history == 100
        assert oo.degraded_threshold == 0.5

    def test_get_state(self):
        oo = OrchestratorOfOrchestrators()
        state = oo.get_state()
        assert isinstance(state, dict)
        assert 'total_orchestrators' in state
        assert 'total_goals_assigned' in state

    def test_best_orchestrator_selection(self):
        oo = OrchestratorOfOrchestrators()
        oo.register_orchestrator('a', 'http://a', ['coding'])
        oo.register_orchestrator('b', 'http://b', ['coding'])
        # Give 'a' better stats
        oo.record_outcome('a', 'g1', True, 100)
        oo.record_outcome('a', 'g2', True, 100)
        oo.record_outcome('b', 'g3', False, 100)
        best = oo.get_best_orchestrator('coding')
        assert best == 'a'

    def test_multi_capability_assignment(self):
        oo = OrchestratorOfOrchestrators()
        oo.register_orchestrator('code', 'http://code', ['coding', 'testing'])
        oo.register_orchestrator('deploy', 'http://deploy', ['deployment'])
        assignment = oo.assign_goal(
            'Code and deploy',
            required_capabilities=['coding', 'deployment']
        )
        assert assignment['status'] == 'assigned'
        # Should have a delegation plan with multiple entries
        assert len(assignment['delegation_plan']) >= 1


# ═══════════════════════════════════════════════════════════════════════
# SystemSynergyLearning (P8.97)
# ═══════════════════════════════════════════════════════════════════════

class TestSystemSynergyLearning:
    """Tests for learning which system combinations work best."""

    def test_record_pipeline(self):
        ssl = SystemSynergyLearning()
        ssl.record_pipeline_execution(
            ['preprocessor', 'analyzer', 'reporter'], True, 500
        )
        stats = ssl.get_pipeline_stats(['preprocessor', 'analyzer', 'reporter'])
        assert stats['executions'] == 1
        assert stats['success_rate'] == 1.0

    def test_get_best_pipeline_default(self):
        ssl = SystemSynergyLearning()
        # No data: should return [start, end]
        best = ssl.get_best_pipeline('start_sys', 'end_sys')
        assert best == ['start_sys', 'end_sys']

    def test_get_best_pipeline_learned(self):
        ssl = SystemSynergyLearning()
        ssl.record_pipeline_execution(['A', 'B', 'C'], True, 300)
        ssl.record_pipeline_execution(['A', 'B', 'C'], True, 200)
        ssl.record_pipeline_execution(['A', 'C'], False, 100)
        best = ssl.get_best_pipeline('A', 'C')
        # The pipeline A->B->C has 100% success, A->C has 0%
        assert best == ['A', 'B', 'C']

    def test_synergy_matrix(self):
        ssl = SystemSynergyLearning()
        # Record several pipeline executions to build pair stats
        for _ in range(5):
            ssl.record_pipeline_execution(['X', 'Y'], True, 100)
        for _ in range(3):
            ssl.record_pipeline_execution(['X', 'Y'], False, 100)
        synergy = ssl.get_synergy_matrix()
        assert isinstance(synergy, dict)
        # Should have at least one entry for X->Y
        assert len(synergy) > 0

    def test_get_state(self):
        ssl = SystemSynergyLearning()
        state = ssl.get_state()
        assert isinstance(state, dict)
        assert 'total_executions' in state
        assert 'tracked_pipelines' in state

    def test_pipeline_eviction(self):
        ssl = SystemSynergyLearning(max_pipelines=2)
        ssl.record_pipeline_execution(['A', 'B'], True, 100)
        ssl.record_pipeline_execution(['C', 'D'], True, 100)
        # Third pipeline should evict least-used
        ssl.record_pipeline_execution(['E', 'F'], True, 100)
        assert ssl._total_executions == 3
        # One of the first two pipelines should have been evicted
        assert len(ssl._pipelines) <= 2


# ═══════════════════════════════════════════════════════════════════════
# KnowledgeExport (P8.98)
# ═══════════════════════════════════════════════════════════════════════

class TestKnowledgeExport:
    """Tests for exporting and importing learned knowledge."""

    def test_export_skills(self):
        ke = KnowledgeExport()
        skill_data = {'python': {'level': 'advanced'}, 'docker': {'level': 'intermediate'}}
        package = ke.export_skills(skill_data)
        assert package['type'] == 'skills'
        assert 'data' in package
        assert 'export_id' in package

    def test_export_full(self):
        ke = KnowledgeExport()
        components = {
            'skills': {'python': 'advanced'},
            'strategies': {'incremental': 0.9},
            'self_model': {'strengths': ['coding']},
        }
        package = ke.export_full_knowledge(components)
        assert package['type'] == 'full_knowledge'
        assert package['component_count'] == 3
        assert 'skills' in package['components']

    def test_import_knowledge(self):
        ke = KnowledgeExport()
        package = {
            'type': 'skills',
            'version': '1.0.0',
            'data': {'a': 1, 'b': 2, 'c': 3},
        }
        result = ke.import_knowledge(package)
        assert result['status'] == 'success'
        assert result['package_type'] == 'skills'
        assert result['items_imported'] == 3

    def test_round_trip(self):
        ke = KnowledgeExport()
        original = {
            'skills': {'coding': 'expert', 'testing': 'advanced'},
            'strategies': {'tdd': 0.95},
        }
        exported = ke.export_full_knowledge(original)
        imported = ke.import_knowledge(exported)
        assert imported['status'] == 'success'
        assert imported['components_imported'] == 2

    def test_get_state(self):
        ke = KnowledgeExport()
        state = ke.get_state()
        assert isinstance(state, dict)
        assert 'total_exports' in state
        assert 'total_imports' in state

    def test_export_with_get_state_object(self):
        """Test export from an object with get_state()."""
        ke = KnowledgeExport()

        class MockSystem:
            def get_state(self):
                return {'metric': 42, 'status': 'ok'}

        package = ke.export_skills(MockSystem())
        assert package['data']['metric'] == 42

    def test_export_with_to_dict_object(self):
        """Test export from an object with to_dict()."""
        ke = KnowledgeExport()

        class MockRecord:
            def to_dict(self):
                return {'field': 'value'}

        package = ke.export_self_model(MockRecord())
        assert package['data']['field'] == 'value'


# ═══════════════════════════════════════════════════════════════════════
# EvolutionaryGrowth (P8.99)
# ═══════════════════════════════════════════════════════════════════════

class TestEvolutionaryGrowth:
    """Tests for tracking system evolution and capability growth."""

    def test_register_capability(self):
        eg = EvolutionaryGrowth()
        eg.register_capability('code_gen', 'coding', '1.0')
        state = eg.get_state()
        assert 'code_gen' in state['capabilities']

    def test_record_usage(self):
        eg = EvolutionaryGrowth()
        eg.register_capability('code_gen', 'coding')
        eg.record_usage('code_gen')
        eg.record_usage('code_gen')
        assert eg._capabilities['code_gen'].usage_count == 2

    def test_unused_capabilities(self):
        eg = EvolutionaryGrowth(archive_after_days=30)
        eg.register_capability('old_cap', 'legacy')
        # Simulate old registration by modifying timestamp
        eg._capabilities['old_cap'].registered_at = time.time() - (31 * 86400)
        eg._capabilities['old_cap'].last_used_at = 0.0

        unused = eg.get_unused_capabilities(days_threshold=30)
        assert 'old_cap' in unused

    def test_recently_used_not_unused(self):
        eg = EvolutionaryGrowth()
        eg.register_capability('active_cap', 'coding')
        eg.record_usage('active_cap')
        unused = eg.get_unused_capabilities(days_threshold=30)
        assert 'active_cap' not in unused

    def test_growth_metrics(self):
        eg = EvolutionaryGrowth()
        eg.register_capability('cap_a', 'coding')
        eg.register_capability('cap_b', 'testing')
        metrics = eg.get_growth_metrics()
        assert isinstance(metrics, dict)
        assert metrics['total_capabilities'] == 2
        assert metrics['active'] == 2
        assert 'categories' in metrics

    def test_get_state(self):
        eg = EvolutionaryGrowth()
        state = eg.get_state()
        assert isinstance(state, dict)
        assert 'growth_metrics' in state

    def test_suggest_improvements_archive(self):
        eg = EvolutionaryGrowth(archive_after_days=1)
        eg.register_capability('stale', 'old')
        eg._capabilities['stale'].registered_at = time.time() - (2 * 86400)
        eg._capabilities['stale'].last_used_at = 0.0
        suggestions = eg.suggest_improvements()
        archive_suggestions = [s for s in suggestions if s['type'] == 'archive']
        assert len(archive_suggestions) >= 1

    def test_reactivation_on_usage(self):
        eg = EvolutionaryGrowth()
        eg.register_capability('dormant', 'legacy')
        from core.ecosystem_intelligence import CapabilityStatus
        eg._capabilities['dormant'].status = CapabilityStatus.ARCHIVED
        eg.record_usage('dormant')
        assert eg._capabilities['dormant'].status == CapabilityStatus.ACTIVE


# ═══════════════════════════════════════════════════════════════════════
# ConsciousnessEvolution (P8.100)
# ═══════════════════════════════════════════════════════════════════════

class TestConsciousnessEvolution:
    """Tests for tracking consciousness growth with experience."""

    def test_integration_event(self):
        ce = ConsciousnessEvolution()
        ce.record_integration_event(['memory', 'attention', 'reasoning'], True)
        state = ce.get_state()
        assert state['total_integration_events'] == 1
        assert 'memory' in state['systems_ever_seen']

    def test_self_reflection(self):
        ce = ConsciousnessEvolution()
        ce.record_self_reflection(0.8, "I learned that caution pays off")
        ce.record_self_reflection(0.5, "Feedback improves routing")
        state = ce.get_state()
        assert state['total_reflections'] == 2

    def test_consciousness_level(self):
        ce = ConsciousnessEvolution()
        # Record many successful integration events across multiple systems
        for _ in range(20):
            ce.record_integration_event(
                ['memory', 'attention', 'reasoning', 'emotion'], True
            )
        level = ce.get_consciousness_level()
        assert level['phi_estimate'] > 0
        assert level['integration_score'] > 0

    def test_consciousness_level_empty(self):
        ce = ConsciousnessEvolution()
        level = ce.get_consciousness_level()
        assert level['phi_estimate'] == 0.0
        assert level['integration_score'] == 0.0

    def test_evolution_timeline(self):
        ce = ConsciousnessEvolution()
        # Timeline snapshots are recorded every 10 events
        for i in range(20):
            ce.record_integration_event(['sys_a', 'sys_b'], True)
        timeline = ce.get_evolution_timeline()
        assert isinstance(timeline, list)
        # Should have at least 1 snapshot (at event 10, 20)
        assert len(timeline) >= 1

    def test_get_state(self):
        ce = ConsciousnessEvolution()
        state = ce.get_state()
        assert isinstance(state, dict)
        assert 'current_level' in state
        assert 'systems_ever_seen' in state

    def test_narrative_richness_increases(self):
        ce = ConsciousnessEvolution()
        # Record many unique reflections
        for i in range(30):
            ce.record_self_reflection(0.7, f"Insight number {i}")
        level = ce.get_consciousness_level()
        assert level['narrative_richness'] > 0

    def test_reflection_depth_tracking(self):
        ce = ConsciousnessEvolution()
        ce.record_self_reflection(0.9, "Deep insight about system integration")
        ce.record_self_reflection(0.3, "Shallow observation")
        level = ce.get_consciousness_level()
        # Average depth should be between 0.3 and 0.9
        assert 0.3 <= level['reflection_depth'] <= 0.9

    def test_multiple_system_breadth(self):
        ce = ConsciousnessEvolution()
        ce.record_integration_event(['a'], True)
        ce.record_integration_event(['a', 'b', 'c', 'd', 'e'], True)
        state = ce.get_state()
        seen = state['systems_ever_seen']
        assert len(seen) == 5

    def test_failed_integration_lowers_phi(self):
        ce = ConsciousnessEvolution()
        # All failures
        for _ in range(20):
            ce.record_integration_event(['a', 'b'], False)
        level_bad = ce.get_consciousness_level()

        ce2 = ConsciousnessEvolution()
        # All successes
        for _ in range(20):
            ce2.record_integration_event(['a', 'b'], True)
        level_good = ce2.get_consciousness_level()

        assert level_good['phi_estimate'] > level_bad['phi_estimate']

"""
Integration Tests for Adaptive Cognitive System (ACS)

Tests the integration of:
- Phase 5: Meta-CTM Supervisor in Multi-CTM Ensemble
- Phase 6: Goal Graph in Hierarchical Planner
- Phase 7: Evolutionary CTM Selector in Multi-CTM Ensemble
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest


class TestMetaCTMIntegration:
    """Test Meta-CTM Supervisor integration into Multi-CTM Ensemble"""

    def test_import_meta_ctm(self):
        """Test that Meta-CTM modules can be imported"""
        from core.meta_ctm import MetaCTMSupervisor, CTMHealth, MetaCTMDecision
        assert MetaCTMSupervisor is not None
        assert CTMHealth is not None

    def test_meta_ctm_initialization(self):
        """Test Meta-CTM Supervisor initialization"""
        from core.meta_ctm import MetaCTMSupervisor

        supervisor = MetaCTMSupervisor(
            consciousness_threshold=0.7,
            max_consecutive_failures=3
        )

        # Should have 4 domains
        assert len(supervisor.ctm_metrics) == 4
        assert 'spatial' in supervisor.ctm_metrics
        assert 'logic' in supervisor.ctm_metrics
        assert 'temporal' in supervisor.ctm_metrics
        assert 'value' in supervisor.ctm_metrics

    def test_meta_ctm_task_selection(self):
        """Test task selection with Meta-CTM"""
        from core.meta_ctm import MetaCTMSupervisor

        supervisor = MetaCTMSupervisor()

        # Test spatial task
        decision = supervisor.select_ctm(
            task="Design microservice architecture",
            domain_hint="spatial"
        )
        assert decision.selected_ctm == 'spatial'
        assert decision.confidence > 0

    def test_meta_ctm_health_status(self):
        """Test health status retrieval"""
        from core.meta_ctm import MetaCTMSupervisor

        supervisor = MetaCTMSupervisor()
        health = supervisor.get_health_status()

        assert 'spatial' in health
        assert 'health' in health['spatial']
        assert health['spatial']['health'] == 'healthy'


class TestGoalGraphIntegration:
    """Test Goal Graph integration into Hierarchical Planner"""

    def test_import_goal_graph(self):
        """Test that Goal Graph modules can be imported"""
        from core.goal_graph import GoalGraph, Goal, GoalState, GoalPriority
        assert GoalGraph is not None
        assert Goal is not None

    def test_goal_graph_initialization(self):
        """Test Goal Graph initialization"""
        from core.goal_graph import GoalGraph

        graph = GoalGraph()
        assert graph is not None
        assert len(graph.goals) == 0

    def test_goal_creation(self):
        """Test goal creation"""
        from core.goal_graph import GoalGraph, GoalPriority

        graph = GoalGraph()
        goal = graph.add_goal(
            description="Test goal",
            priority=GoalPriority.HIGH
        )

        assert goal is not None
        assert goal.description == "Test goal"
        assert goal.priority == GoalPriority.HIGH
        assert len(graph.goals) == 1

    def test_goal_hierarchy(self):
        """Test goal hierarchy (parent-child)"""
        from core.goal_graph import GoalGraph

        graph = GoalGraph()

        # Create parent goal
        parent = graph.add_goal(description="Parent goal")

        # Create child goal
        child = graph.add_goal(
            description="Child goal",
            parent_id=parent.goal_id
        )

        assert child.parent_id == parent.goal_id
        assert parent.goal_id in [g.goal_id for g in graph.goals.values()]

    def test_goal_completion(self):
        """Test goal completion"""
        from core.goal_graph import GoalGraph, GoalState

        graph = GoalGraph()
        goal = graph.add_goal(description="Test goal")

        # First activate the goal (required before completion)
        graph.start_goal(goal.goal_id)
        assert graph.goals[goal.goal_id].state == GoalState.ACTIVE

        # Then complete the goal
        graph.complete_goal(goal.goal_id)
        assert graph.goals[goal.goal_id].state == GoalState.COMPLETED


class TestEvolutionaryIntegration:
    """Test Evolutionary CTM Selector integration"""

    def test_import_evolutionary(self):
        """Test that Evolutionary modules can be imported"""
        from core.evolutionary_ctm_selector import (
            EvolutionaryCTMSelector, CTMGenes, CTMIndividual
        )
        assert EvolutionaryCTMSelector is not None
        assert CTMGenes is not None

    def test_evolutionary_initialization(self):
        """Test Evolutionary Selector initialization"""
        from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

        selector = EvolutionaryCTMSelector(
            population_size=10,
            elite_count=2
        )

        # Should have 4 domain populations
        assert len(selector.populations) == 4
        assert len(selector.populations['spatial']) == 10

    def test_population_stats(self):
        """Test population statistics"""
        from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

        selector = EvolutionaryCTMSelector(population_size=10)
        stats = selector.get_all_stats()

        assert 'spatial' in stats
        assert 'logic' in stats
        assert 'temporal' in stats
        assert 'value' in stats
        assert stats['spatial']['population_size'] == 10

    def test_evolution_cycle(self):
        """Test evolution cycle"""
        from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

        selector = EvolutionaryCTMSelector(population_size=10)

        # Run evolution
        result = selector.evolve_population('spatial')

        assert 'generation' in result
        assert result['generation'] == 1
        assert 'pre_evolution' in result
        assert 'post_evolution' in result

    def test_best_genes_retrieval(self):
        """Test best genes retrieval"""
        from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

        selector = EvolutionaryCTMSelector(population_size=10)
        genes = selector.get_best_genes('spatial')

        assert genes is not None
        assert hasattr(genes, 'consciousness_threshold')
        assert hasattr(genes, 'max_reasoning_steps')


class TestFullIntegration:
    """Test all systems working together"""

    def test_combined_imports(self):
        """Test that all integration modules can be imported together"""
        from core.meta_ctm import MetaCTMSupervisor
        from core.goal_graph import GoalGraph
        from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

        # Create instances
        supervisor = MetaCTMSupervisor()
        graph = GoalGraph()
        selector = EvolutionaryCTMSelector(population_size=5)

        assert supervisor is not None
        assert graph is not None
        assert selector is not None

    def test_multi_ctm_ensemble_with_all_features(self):
        """Test that Multi-CTM Ensemble integrates all features"""
        # This is a light test that doesn't load neural networks
        from core.meta_ctm import MetaCTMSupervisor
        from core.evolutionary_ctm_selector import EvolutionaryCTMSelector

        # Create supervisor and selector
        supervisor = MetaCTMSupervisor()
        selector = EvolutionaryCTMSelector(population_size=5)

        # Record some performance data
        supervisor.record_task_result(
            task_id="test1",
            domain="spatial",
            consciousness=0.9,
            response_time=1.5,
            success=True,
            task_description="Test task"
        )

        selector.record_performance(
            domain="spatial",
            individual_id=selector.populations['spatial'][0].id,
            consciousness=0.9,
            response_time=1.5,
            success=True
        )

        # Check that both recorded
        assert supervisor.ctm_metrics['spatial'].total_tasks == 1
        assert selector.populations['spatial'][0].total_tasks == 1

    def test_hierarchical_planner_features(self):
        """Test HierarchicalPlanner has goal graph methods"""
        from core.hierarchical_planner import HierarchicalPlanner

        # Just check the class has the new methods
        assert hasattr(HierarchicalPlanner, 'add_goal')
        assert hasattr(HierarchicalPlanner, 'get_goals')
        assert hasattr(HierarchicalPlanner, 'complete_goal')
        assert hasattr(HierarchicalPlanner, 'fail_goal')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

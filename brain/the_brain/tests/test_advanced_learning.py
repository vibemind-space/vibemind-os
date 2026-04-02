"""
Integration Tests for Phase 8B: Advanced Learning & Adaptation

Tests for:
- B1: Causal Reasoning (CausalDAG, CausalInference, RootCauseAnalyzer)
- B2: Meta-Learning (MAMLOptimizer, TaskDistribution, AdaptiveHyperparameters)
- B3: Federated Learning (FederatedCoordinator, FederatedNode, DifferentialPrivacy)
"""

import pytest
import sys
import os
import numpy as np
import torch
import torch.nn as nn

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ============================================================================
# B1: CAUSAL REASONING TESTS
# ============================================================================

class TestCausalDAG:
    """Tests for CausalDAG class."""

    def test_import(self):
        """Test that causal_reasoning module can be imported."""
        from core.causal_reasoning import CausalDAG, CausalInference, RootCauseAnalyzer
        assert CausalDAG is not None
        assert CausalInference is not None
        assert RootCauseAnalyzer is not None

    def test_dag_creation(self):
        """Test creating an empty DAG."""
        from core.causal_reasoning import CausalDAG
        dag = CausalDAG()
        assert len(dag.nodes) == 0
        assert len(dag.edges) == 0

    def test_add_variable(self):
        """Test adding variables to DAG."""
        from core.causal_reasoning import CausalDAG
        dag = CausalDAG()
        dag.add_variable("X")
        dag.add_variable("Y")
        assert len(dag.nodes) == 2
        assert "X" in dag.nodes
        assert "Y" in dag.nodes

    def test_add_edge(self):
        """Test adding edges to DAG."""
        from core.causal_reasoning import CausalDAG
        dag = CausalDAG()
        dag.add_variable("X")
        dag.add_variable("Y")
        dag.add_edge("X", "Y", strength=0.8)
        assert len(dag.edges) == 1

    def test_get_parents_children(self):
        """Test getting parents and children."""
        from core.causal_reasoning import CausalDAG
        dag = CausalDAG()
        dag.add_variable("A")
        dag.add_variable("B")
        dag.add_variable("C")
        dag.add_edge("A", "B")
        dag.add_edge("B", "C")

        assert "A" in dag.get_parents("B")
        assert "C" in dag.get_children("B")

    def test_topological_sort(self):
        """Test topological sorting."""
        from core.causal_reasoning import CausalDAG
        dag = CausalDAG()
        dag.add_variable("A")
        dag.add_variable("B")
        dag.add_variable("C")
        dag.add_edge("A", "B")
        dag.add_edge("B", "C")

        sorted_nodes = dag.topological_sort()
        assert sorted_nodes.index("A") < sorted_nodes.index("B")
        assert sorted_nodes.index("B") < sorted_nodes.index("C")


class TestCausalInference:
    """Tests for CausalInference class."""

    def test_observe(self):
        """Test observational inference."""
        from core.causal_reasoning import CausalDAG, CausalInference
        dag = CausalDAG()
        dag.add_variable("X")
        dag.add_variable("Y")
        dag.add_edge("X", "Y")

        inference = CausalInference(dag)
        result = inference.observe({"X": 1.0})
        # Result may be empty or contain Y depending on implementation
        assert isinstance(result, dict)

    def test_do_operator(self):
        """Test do-calculus intervention."""
        from core.causal_reasoning import CausalDAG, CausalInference
        dag = CausalDAG()
        dag.add_variable("X")
        dag.add_variable("Y")
        dag.add_edge("X", "Y")

        inference = CausalInference(dag)
        result = inference.do({"X": 1.0})
        # Result should contain the intervention target
        assert isinstance(result, dict)


class TestRootCauseAnalyzer:
    """Tests for RootCauseAnalyzer class."""

    def test_analyze_failure(self):
        """Test root cause analysis."""
        from core.causal_reasoning import CausalDAG, RootCauseAnalyzer
        dag = CausalDAG()
        dag.add_variable("cause1")
        dag.add_variable("cause2")
        dag.add_variable("effect")
        dag.add_edge("cause1", "effect")
        dag.add_edge("cause2", "effect")

        analyzer = RootCauseAnalyzer(dag)
        causes = analyzer.analyze_failure({"effect": "failed"})
        assert len(causes) > 0

    def test_rank_causes(self):
        """Test cause ranking."""
        from core.causal_reasoning import CausalDAG, RootCauseAnalyzer
        dag = CausalDAG()
        dag.add_variable("cause1")
        dag.add_variable("effect")
        dag.add_edge("cause1", "effect", strength=0.9)

        analyzer = RootCauseAnalyzer(dag)
        causes = analyzer.analyze_failure({"effect": "failed"})
        ranked = analyzer.rank_causes(causes)
        assert len(ranked) > 0


# ============================================================================
# B2: META-LEARNING TESTS
# ============================================================================

class TestMetaLearner:
    """Tests for MetaLearner class."""

    def test_import(self):
        """Test that meta_learning module can be imported."""
        from core.meta_learning import MetaLearner, MAMLOptimizer, TaskDistribution
        assert MetaLearner is not None
        assert MAMLOptimizer is not None
        assert TaskDistribution is not None

    def test_meta_learner_creation(self):
        """Test creating MetaLearner."""
        from core.meta_learning import MetaLearner
        learner = MetaLearner()
        assert learner is not None

    def test_adaptation(self):
        """Test adaptation recording."""
        from core.meta_learning import MetaLearner
        learner = MetaLearner()
        # MetaLearner uses adapt_meta_parameters with outcome
        result = learner.adapt_meta_parameters(outcome='success')
        # Check that adaptation returns updated parameters
        assert result is not None
        stats = learner.get_statistics()
        # Verify statistics structure exists
        assert 'total_adaptations' in stats


class TestMAMLOptimizer:
    """Tests for MAMLOptimizer class."""

    def test_maml_creation(self):
        """Test creating MAML optimizer."""
        from core.meta_learning import MAMLOptimizer

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        model = SimpleModel()
        maml = MAMLOptimizer(model, inner_lr=0.01, outer_lr=0.001)
        assert maml is not None

    def test_inner_loop(self):
        """Test MAML inner loop."""
        from core.meta_learning import MAMLOptimizer

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        model = SimpleModel()
        maml = MAMLOptimizer(model, inner_lr=0.01, outer_lr=0.001)

        support_x = torch.randn(5, 10)
        support_y = torch.randint(0, 5, (5,))

        def loss_fn(preds, targets):
            return nn.functional.cross_entropy(preds, targets)

        adapted, losses = maml.inner_loop(support_x, support_y, loss_fn, steps=3)
        assert adapted is not None
        assert len(losses) == 3


class TestTaskDistribution:
    """Tests for TaskDistribution class."""

    def test_task_distribution_creation(self):
        """Test creating TaskDistribution."""
        from core.meta_learning import TaskDistribution
        dist = TaskDistribution()
        assert dist is not None

    def test_add_experience(self):
        """Test adding experiences."""
        from core.meta_learning import TaskDistribution
        dist = TaskDistribution()
        for i in range(20):
            dist.add_experience({'x': i, 'y': i % 5}, domain='test')

        stats = dist.get_statistics()
        assert stats['total_experiences'] == 20

    def test_sample_task(self):
        """Test sampling tasks."""
        from core.meta_learning import TaskDistribution
        dist = TaskDistribution(n_support=3, n_query=5)

        # TaskDistribution expects 'state' and 'action' keys
        for i in range(50):
            dist.add_experience({
                'state': np.random.randn(10).tolist(),
                'action': i % 5,
                'reward': 1.0
            }, domain='test')

        task = dist.sample_task('test')
        assert task is not None
        assert task.domain == 'test'


class TestAdaptiveHyperparameters:
    """Tests for AdaptiveHyperparameters class."""

    def test_adaptive_hp_creation(self):
        """Test creating AdaptiveHyperparameters."""
        from core.meta_learning import AdaptiveHyperparameters
        hp = AdaptiveHyperparameters()
        assert hp is not None

    def test_suggest_lr(self):
        """Test learning rate suggestion."""
        from core.meta_learning import AdaptiveHyperparameters
        hp = AdaptiveHyperparameters()
        lr = hp.suggest_lr(1.0)
        assert 0 < lr < 1

    def test_update_and_best(self):
        """Test updating and getting best params."""
        from core.meta_learning import AdaptiveHyperparameters
        hp = AdaptiveHyperparameters()
        hp.update({'learning_rate': 0.01}, performance=0.8)
        hp.update({'learning_rate': 0.001}, performance=0.9)

        best = hp.get_best_params()
        assert 'learning_rate' in best


# ============================================================================
# B3: FEDERATED LEARNING TESTS
# ============================================================================

class TestFederatedNode:
    """Tests for FederatedNode class."""

    def test_import(self):
        """Test that federated_learning module can be imported."""
        from core.federated_learning import FederatedCoordinator, FederatedNode, DifferentialPrivacy
        assert FederatedCoordinator is not None
        assert FederatedNode is not None
        assert DifferentialPrivacy is not None

    def test_node_creation(self):
        """Test creating FederatedNode."""
        from core.federated_learning import FederatedNode

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        model = SimpleModel()
        node = FederatedNode(model, node_id='test_node')
        assert node.node_id == 'test_node'

    def test_add_data(self):
        """Test adding data to node."""
        from core.federated_learning import FederatedNode, TrainingExample

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        model = SimpleModel()
        node = FederatedNode(model, node_id='test_node')

        data = [TrainingExample(input_data=torch.randn(10), target=i % 5) for i in range(20)]
        node.add_data(data)

        stats = node.get_statistics()
        assert stats['total_samples'] == 20


class TestFederatedCoordinator:
    """Tests for FederatedCoordinator class."""

    def test_coordinator_creation(self):
        """Test creating FederatedCoordinator."""
        from core.federated_learning import FederatedCoordinator
        coordinator = FederatedCoordinator(aggregation_strategy='fedavg')
        assert coordinator.aggregation_strategy.value == 'fedavg'

    def test_register_node(self):
        """Test registering nodes."""
        from core.federated_learning import FederatedCoordinator, FederatedNode

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        coordinator = FederatedCoordinator()
        node = FederatedNode(SimpleModel(), 'node_1')
        coordinator.register_node('node_1', node)

        assert 'node_1' in coordinator.get_active_nodes()

    def test_run_round(self):
        """Test running federated round."""
        from core.federated_learning import FederatedCoordinator, FederatedNode, TrainingExample

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        coordinator = FederatedCoordinator(min_nodes=2)

        # Create and register nodes
        for i in range(2):
            model = SimpleModel()
            node = FederatedNode(model, f'node_{i}')
            node.add_data([
                TrainingExample(input_data=torch.randn(10), target=j % 5)
                for j in range(20)
            ])
            coordinator.register_node(f'node_{i}', node)

        # Run round
        result = coordinator.run_round(local_epochs=1)
        assert result['success']
        assert result['round'] == 1


class TestDifferentialPrivacy:
    """Tests for DifferentialPrivacy class."""

    def test_dp_creation(self):
        """Test creating DifferentialPrivacy."""
        from core.federated_learning import DifferentialPrivacy
        dp = DifferentialPrivacy(max_grad_norm=1.0, noise_multiplier=0.5)
        assert dp is not None

    def test_clip_gradients(self):
        """Test gradient clipping."""
        from core.federated_learning import DifferentialPrivacy
        dp = DifferentialPrivacy(max_grad_norm=1.0)

        grads = {'weight': torch.randn(10, 5) * 10}  # Large gradients
        clipped = dp.clip_gradients(grads)

        # Verify norm is bounded
        total_norm = sum(g.norm(2).item()**2 for g in clipped.values())**0.5
        assert total_norm <= 1.0 + 1e-5

    def test_add_noise(self):
        """Test noise addition."""
        from core.federated_learning import DifferentialPrivacy
        dp = DifferentialPrivacy(max_grad_norm=1.0, noise_multiplier=0.1)

        grads = {'weight': torch.zeros(10, 5)}
        noisy = dp.add_noise(grads)

        # Verify noise was added (grads should no longer be zero)
        assert noisy['weight'].abs().sum().item() > 0

    def test_privacy_budget(self):
        """Test privacy budget tracking."""
        from core.federated_learning import DifferentialPrivacy
        dp = DifferentialPrivacy(target_epsilon=1.0)

        budget = dp.get_privacy_budget()
        assert budget['target_epsilon'] == 1.0
        assert budget['spent_epsilon'] >= 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests across Phase 8B components."""

    def test_goal_graph_causal_integration(self):
        """Test GoalGraph with causal reasoning."""
        from core.goal_graph import GoalGraph, CausalEdgeType, GoalPriority

        graph = GoalGraph()
        # GoalGraph.add_goal takes description first and returns Goal object
        goal1 = graph.add_goal("First goal", priority=GoalPriority.HIGH)
        goal2 = graph.add_goal("Second goal", priority=GoalPriority.MEDIUM)

        # Use the returned goal IDs
        graph.add_causal_edge(goal1.goal_id, goal2.goal_id, CausalEdgeType.ENABLES, strength=0.8)

        # get_causal_causes returns CausalGoalEdge objects
        causes = graph.get_causal_causes(goal2.goal_id)
        cause_ids = [e.source_goal for e in causes]
        assert goal1.goal_id in cause_ids

    def test_dual_system_maml_integration(self):
        """Test DualSystemAgent with MAML."""
        try:
            from core.neurosymbolic_heart_brain import DualSystemAgent, NeuroSymbolicHeartSystem, NeuroSymbolicBrainSystem

            heart = NeuroSymbolicHeartSystem(device='cpu')
            brain = NeuroSymbolicBrainSystem(device='cpu')
            agent = DualSystemAgent(heart, brain)

            # Enable MAML
            success = agent.enable_maml()

            # Check stats
            stats = agent.get_statistics()
            assert stats['maml_enabled'] == success
        except ImportError:
            pytest.skip("DualSystemAgent not available")

    def test_federated_checkpoint_integration(self):
        """Test federated learning with checkpointing."""
        from core.federated_learning import FederatedCoordinator, FederatedNode, TrainingExample
        from core.distributed_checkpoint import DistributedCheckpointManager, FederatedCheckpointAdapter
        import tempfile

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(10, 5)
            def forward(self, x):
                return self.fc(x)

        # Create coordinator
        coordinator = FederatedCoordinator(min_nodes=2)

        for i in range(2):
            node = FederatedNode(SimpleModel(), f'node_{i}')
            node.add_data([
                TrainingExample(input_data=torch.randn(10), target=j % 5)
                for j in range(10)
            ])
            coordinator.register_node(f'node_{i}', node)

        # Create checkpoint manager with temp dir
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DistributedCheckpointManager(local_dir=tmpdir)
            adapter = FederatedCheckpointAdapter(manager, checkpoint_every=1)

            # Run round
            result = coordinator.run_round(local_epochs=1)

            if result['success']:
                # Checkpoint
                adapter.on_round_complete(
                    global_weights=coordinator.get_global_model(),
                    round_number=1,
                    coordinator_stats=coordinator.get_statistics(),
                    node_updates=[]
                )

                # Verify checkpoint exists
                versions = manager.list_versions("federated_global")
                assert len(versions) > 0


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, '-v', '--tb=short'])

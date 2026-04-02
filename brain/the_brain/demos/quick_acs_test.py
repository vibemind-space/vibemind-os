"""Quick lightweight ACS test."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Test 1: Meta-CTM Supervisor
from core.meta_ctm import MetaCTMSupervisor
supervisor = MetaCTMSupervisor()
decision = supervisor.select_ctm('Design microservice architecture', domain_hint='spatial')
assert decision.selected_ctm == 'spatial'
print('[PASS] Test 1: Meta-CTM Supervisor')

# Test 2: Goal Graph
from core.goal_graph import GoalGraph, GoalPriority, GoalState
graph = GoalGraph()
goal = graph.add_goal('Test goal', GoalPriority.HIGH)
graph.start_goal(goal.goal_id)
graph.complete_goal(goal.goal_id)
stats = graph.get_statistics()
assert stats['total_goals'] == 1
assert stats['completed_count'] == 1
print('[PASS] Test 2: Goal Graph')

# Test 3: Evolutionary Selector
from core.evolutionary_ctm_selector import EvolutionaryCTMSelector
selector = EvolutionaryCTMSelector(population_size=5)
genes = selector.get_best_genes('spatial')
assert hasattr(genes, 'consciousness_threshold')
assert hasattr(genes, 'learning_rate')
print('[PASS] Test 3: Evolutionary Selector')

# Test 4: Domain Router (without heavy neural networks)
from core.ctm_domain_router import CTMDomainRouter
router = CTMDomainRouter()
classification = router.classify_task('Design microservice architecture')
assert classification.primary_domain.value == 'spatial'
print('[PASS] Test 4: Domain Router')

print('')
print('[SUCCESS] All lightweight ACS tests passed!')

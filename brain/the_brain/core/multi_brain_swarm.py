"""
Multi-Brain Swarm System (PHASE 13 - Semantic Coherence Enhanced)

Implements collaborative intelligence with semantic truth dynamics:

1. Brain Specialization:
   - Create multiple brain instances with different expertise
   - Specialize by domain (docker, github, filesystem, etc.)
   - Adapt specialization through experience

2. Task Decomposition:
   - Break complex tasks into subtasks
   - Assign subtasks to specialized brains
   - Track dependencies between subtasks

3. Consensus Mechanisms:
   - Majority voting for decisions
   - Confidence-weighted voting
   - Expert opinion (defer to specialists)
   - Bayesian aggregation

4. Semantic Coherence (NEW):
   - Measure meaning convergence across brain answers
   - Truth stability = voting_score × coherence_K
   - Traffic light system (GREEN/YELLOW/RED)
   - Clarification subtasks for low coherence

5. Result Aggregation:
   - Combine results from multiple brains
   - Resolve conflicts with semantic validation
   - Synthesize recommendations

6. Swarm Intelligence:
   - Emergent behavior from collaboration
   - Collective problem solving
   - Load balancing across brains
   - Adaptive task allocation

Based on:
- Swarm Intelligence (Kennedy & Eberhart, 1995; Dorigo et al., 1996)
- Collective Intelligence (Woolley et al., 2010)
- Multi-Agent Systems (Wooldridge, 2009)
- Coherence Theory of Truth (Rescher, 1973)
- Gödel's incompleteness → meta-level validation
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib

# Import semantic coherence layer
try:
    from .semantic_coherence import (
        SemanticCoherenceLayer,
        SemanticEncoder,
        BrainAnswer,
        SemanticConsensus
    )
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False


@dataclass
class BrainInstance:
    """
    A specialized brain instance in the swarm
    """
    brain_id: str
    brain_name: str

    # Specialization
    primary_domain: str  # docker, github, filesystem, etc.
    expertise_level: float = 0.5  # 0-1

    # Performance tracking
    tasks_completed: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_confidence: float = 0.5

    # Capabilities
    supported_domains: List[str] = field(default_factory=list)
    preferred_modalities: List[str] = field(default_factory=list)  # vision, audio, etc.

    # State
    current_load: float = 0.0  # 0-1 (how busy)
    is_available: bool = True

    def success_rate(self) -> float:
        """Compute success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    def expertise_in_domain(self, domain: str) -> float:
        """Get expertise level for a specific domain"""
        if domain == self.primary_domain:
            return self.expertise_level
        elif domain in self.supported_domains:
            return self.expertise_level * 0.5
        else:
            return 0.1  # Minimal baseline expertise

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'brain_id': self.brain_id,
            'brain_name': self.brain_name,
            'primary_domain': self.primary_domain,
            'expertise_level': self.expertise_level,
            'tasks_completed': self.tasks_completed,
            'success_rate': self.success_rate(),
            'current_load': self.current_load,
            'is_available': self.is_available
        }


@dataclass
class SubTask:
    """
    A subtask assigned to a brain
    """
    subtask_id: str
    description: str
    domain: str

    # Assignment
    assigned_brain_id: Optional[str] = None

    # Status
    status: str = 'pending'  # pending, in_progress, completed, failed

    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # Other subtask IDs

    # Result
    result: Optional[Dict] = None
    confidence: float = 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'subtask_id': self.subtask_id,
            'description': self.description,
            'domain': self.domain,
            'assigned_brain_id': self.assigned_brain_id,
            'status': self.status,
            'depends_on': len(self.depends_on),
            'confidence': self.confidence
        }


@dataclass
class SwarmDecision:
    """
    A decision made by the swarm through consensus (with semantic coherence)
    """
    decision_id: str
    task_description: str

    # Voting results
    votes: Dict[str, int] = field(default_factory=dict)  # decision_type -> vote count
    brain_votes: Dict[str, str] = field(default_factory=dict)  # brain_id -> decision_type
    confidence_weights: Dict[str, float] = field(default_factory=dict)  # brain_id -> confidence

    # Final decision
    consensus_decision: str = 'wait'
    consensus_confidence: float = 0.5
    consensus_mechanism: str = 'majority'  # majority, weighted, expert

    # Participation
    participating_brains: List[str] = field(default_factory=list)
    agreement_level: float = 0.5  # How much brains agreed

    # Semantic coherence (NEW - Phase 13)
    coherence_K: float = 0.5  # Average pairwise semantic similarity
    disagreement_U: float = 0.5  # Variance of similarities
    truth_stability: float = 0.5  # Final score: K × voting_score
    semantic_status: str = 'YELLOW'  # GREEN, YELLOW, RED

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'decision_id': self.decision_id,
            'task_description': self.task_description,
            'consensus_decision': self.consensus_decision,
            'consensus_confidence': self.consensus_confidence,
            'consensus_mechanism': self.consensus_mechanism,
            'participating_brains': len(self.participating_brains),
            'agreement_level': self.agreement_level,
            'votes': self.votes,
            # Semantic coherence
            'coherence_K': self.coherence_K,
            'disagreement_U': self.disagreement_U,
            'truth_stability': self.truth_stability,
            'semantic_status': self.semantic_status
        }


class MultiBrainSwarm:
    """
    Multi-brain swarm system for collaborative intelligence

    Key features:
    - Multiple specialized brain instances
    - Task decomposition and allocation
    - Consensus mechanisms
    - Result aggregation
    - Swarm intelligence
    """

    def __init__(
        self,
        num_brains: int = 5,
        consensus_threshold: float = 0.6,
        load_balance: bool = True,
        enable_semantic_coherence: bool = True,
        k_min: float = 0.55,  # Adjusted for neural embeddings (was 0.72)
        green_threshold: float = 0.75,  # Adjusted for neural embeddings (was 0.82)
        alpha: float = 0.5
    ):
        """
        Initialize multi-brain swarm

        Args:
            num_brains: Number of brain instances in swarm
            consensus_threshold: Minimum agreement for consensus
            load_balance: Enable load balancing across brains
            enable_semantic_coherence: Enable semantic coherence layer
            k_min: Minimum coherence threshold (RED below this)
            green_threshold: GREEN status threshold
            alpha: Weight for voting_score vs K (0=pure K, 1=pure voting)
        """
        self.num_brains = num_brains
        self.consensus_threshold = consensus_threshold
        self.load_balance = load_balance
        self.enable_semantic_coherence = enable_semantic_coherence and SEMANTIC_AVAILABLE

        # Swarm brains
        self.brains: Dict[str, BrainInstance] = {}

        # Task management
        self.active_tasks: Dict[str, List[SubTask]] = {}  # task_id -> subtasks

        # Decision history
        self.swarm_decisions: List[SwarmDecision] = []

        # Statistics
        self.total_tasks_processed = 0
        self.total_consensus_reached = 0
        self.total_disagreements = 0

        # Semantic coherence layer (Phase 13)
        self.semantic_layer = None
        if self.enable_semantic_coherence:
            self.semantic_layer = SemanticCoherenceLayer(
                k_min=k_min,
                green_threshold=green_threshold,
                alpha=alpha
            )
            print(f"[+] Semantic Coherence enabled (K_min={k_min}, GREEN={green_threshold}, alpha={alpha})")
        else:
            if not SEMANTIC_AVAILABLE:
                print("[!] Semantic Coherence unavailable (semantic_coherence module not found)")

        # Initialize specialized brains
        self._initialize_brains()

    def _initialize_brains(self):
        """Initialize specialized brain instances"""
        # Domain specializations
        domains = ['docker', 'github', 'filesystem', 'terminal', 'network']

        for i in range(self.num_brains):
            primary_domain = domains[i % len(domains)]

            # Create brain with random expertise
            expertise = np.random.uniform(0.6, 0.9)

            brain = BrainInstance(
                brain_id=f"brain_{i}",
                brain_name=f"Brain-{i} ({primary_domain.title()} Specialist)",
                primary_domain=primary_domain,
                expertise_level=expertise,
                supported_domains=[primary_domain] + [d for d in domains if d != primary_domain][:2],
                preferred_modalities=['vision', 'audio'],  # Could vary per brain
                is_available=True
            )

            self.brains[brain.brain_id] = brain

    def decompose_task(
        self,
        task_description: str,
        task_type: str,
        complexity: float = 0.5
    ) -> List[SubTask]:
        """
        Decompose complex task into subtasks

        Args:
            task_description: Task description
            task_type: Task type/domain
            complexity: Task complexity (0-1)

        Returns:
            List of subtasks
        """
        subtasks = []

        # Simple decomposition based on complexity
        if complexity < 0.3:
            # Simple task - single subtask
            subtask = SubTask(
                subtask_id=f"subtask_0",
                description=task_description,
                domain=task_type
            )
            subtasks.append(subtask)

        elif complexity < 0.7:
            # Medium complexity - 2-3 subtasks
            num_subtasks = 2 if complexity < 0.5 else 3

            for i in range(num_subtasks):
                subtask = SubTask(
                    subtask_id=f"subtask_{i}",
                    description=f"{task_description} (part {i+1}/{num_subtasks})",
                    domain=task_type,
                    depends_on=[f"subtask_{i-1}"] if i > 0 else []
                )
                subtasks.append(subtask)

        else:
            # High complexity - 4-5 subtasks with dependencies
            num_subtasks = 4 if complexity < 0.85 else 5

            for i in range(num_subtasks):
                # Create dependency on previous subtask
                depends = []
                if i > 0:
                    depends.append(f"subtask_{i-1}")
                if i > 1 and i % 2 == 0:
                    # Some subtasks also depend on earlier ones
                    depends.append(f"subtask_{i-2}")

                subtask = SubTask(
                    subtask_id=f"subtask_{i}",
                    description=f"{task_description} (step {i+1}/{num_subtasks})",
                    domain=task_type,
                    depends_on=depends
                )
                subtasks.append(subtask)

        return subtasks

    def create_clarification_subtasks(
        self,
        original_task: str,
        swarm_decision: SwarmDecision,
        brain_answers: List
    ) -> List[SubTask]:
        """
        Create clarification subtasks when semantic coherence is low

        Args:
            original_task: Original task description
            swarm_decision: Swarm decision with low coherence
            brain_answers: Brain answers showing disagreement

        Returns:
            List of clarification subtasks
        """
        clarification_subtasks = []

        # Identify disagreement points
        decision_types = set(a.decision_type for a in brain_answers)

        if len(decision_types) > 1:
            # Multiple different decisions → need clarification
            subtask = SubTask(
                subtask_id=f"clarify_{swarm_decision.decision_id}_0",
                description=f"Clarify requirements for: {original_task} (conflicting decisions: {decision_types})",
                domain="clarification"
            )
            clarification_subtasks.append(subtask)

        # Low coherence K → need more evidence
        if swarm_decision.coherence_K < self.semantic_layer.k_min if self.semantic_layer else 0.72:
            subtask = SubTask(
                subtask_id=f"clarify_{swarm_decision.decision_id}_1",
                description=f"Gather additional evidence for: {original_task}",
                domain="evidence_gathering"
            )
            clarification_subtasks.append(subtask)

        # High disagreement U → need perspective diversification
        if swarm_decision.disagreement_U > 0.3:
            subtask = SubTask(
                subtask_id=f"clarify_{swarm_decision.decision_id}_2",
                description=f"Generate counter-hypothesis for: {original_task}",
                domain="counter_hypothesis"
            )
            clarification_subtasks.append(subtask)

        return clarification_subtasks

    def assign_subtask_to_brain(
        self,
        subtask: SubTask
    ) -> Optional[BrainInstance]:
        """
        Assign subtask to most suitable brain

        Args:
            subtask: Subtask to assign

        Returns:
            Assigned brain instance
        """
        # Find available brains
        available_brains = [b for b in self.brains.values() if b.is_available]

        if not available_brains:
            return None  # All busy

        # Score brains for this subtask
        def score_brain(brain: BrainInstance) -> float:
            # Expertise in domain
            expertise_score = brain.expertise_in_domain(subtask.domain)

            # Success rate
            success_score = brain.success_rate()

            # Load balancing (prefer less loaded brains)
            load_score = 1.0 - brain.current_load if self.load_balance else 0.5

            # Combine scores
            total_score = expertise_score * 0.5 + success_score * 0.3 + load_score * 0.2

            return total_score

        # Select best brain
        best_brain = max(available_brains, key=score_brain)

        # Assign subtask
        subtask.assigned_brain_id = best_brain.brain_id
        subtask.status = 'in_progress'

        # Update brain load
        best_brain.current_load = min(1.0, best_brain.current_load + 0.2)

        return best_brain

    def collect_brain_votes(
        self,
        task_description: str,
        task_type: str,
        available_decisions: List[str],
        brain_gates: Optional[np.ndarray] = None,
        brain_reasonings: Optional[Dict[str, str]] = None
    ) -> SwarmDecision:
        """
        Collect votes from all brains and reach consensus (with semantic coherence)

        Args:
            task_description: Task description
            task_type: Task type/domain
            available_decisions: List of possible decisions
            brain_gates: Optional brain activation pattern
            brain_reasonings: Optional dict of brain_id -> reasoning text

        Returns:
            Swarm decision with consensus and semantic coherence metrics
        """
        decision_id = hashlib.md5(task_description.encode()).hexdigest()[:8]

        swarm_decision = SwarmDecision(
            decision_id=decision_id,
            task_description=task_description
        )

        # Collect brain answers for semantic analysis
        brain_answers = []

        # Collect votes from each brain
        for brain in self.brains.values():
            # Get brain's expertise in this domain
            expertise = brain.expertise_in_domain(task_type)

            # Brain makes a decision (simulated based on expertise)
            # In real system, each brain would run full inference
            decision_weights = np.random.dirichlet(np.ones(len(available_decisions)) * expertise)
            brain_decision = available_decisions[np.argmax(decision_weights)]

            # Confidence based on expertise and success rate
            confidence = (expertise * 0.6 + brain.success_rate() * 0.4)
            confidence += np.random.uniform(-0.1, 0.1)  # Add noise
            confidence = np.clip(confidence, 0.0, 1.0)

            # Record vote
            swarm_decision.brain_votes[brain.brain_id] = brain_decision
            swarm_decision.confidence_weights[brain.brain_id] = confidence
            swarm_decision.participating_brains.append(brain.brain_id)

            # Count vote
            if brain_decision not in swarm_decision.votes:
                swarm_decision.votes[brain_decision] = 0
            swarm_decision.votes[brain_decision] += 1

            # Create BrainAnswer for semantic coherence
            if self.enable_semantic_coherence:
                reasoning = brain_reasonings.get(brain.brain_id, "") if brain_reasonings else ""
                if not reasoning:
                    # Generate synthetic reasoning text
                    reasoning = f"{brain_decision} because {task_type} requires expertise in {brain.primary_domain}"

                brain_answer = BrainAnswer(
                    brain_id=brain.brain_id,
                    text=reasoning,
                    confidence=confidence,
                    domain=task_type,
                    decision_type=brain_decision
                )
                brain_answers.append(brain_answer)

        # Reach consensus using different mechanisms
        swarm_decision = self._reach_consensus(swarm_decision, task_type, brain_answers)

        self.swarm_decisions.append(swarm_decision)
        self.total_consensus_reached += 1

        return swarm_decision

    def _reach_consensus(
        self,
        swarm_decision: SwarmDecision,
        task_type: str,
        brain_answers: Optional[List] = None
    ) -> SwarmDecision:
        """
        Reach consensus from collected votes (with semantic coherence)

        Args:
            swarm_decision: Swarm decision with votes
            task_type: Task type for expert selection
            brain_answers: Brain answers for semantic coherence

        Returns:
            Updated swarm decision with consensus and semantic metrics
        """
        # Try different consensus mechanisms

        # 1. Majority voting
        majority_decision = max(swarm_decision.votes.items(), key=lambda x: x[1])
        majority_agreement = majority_decision[1] / len(swarm_decision.participating_brains)

        if majority_agreement >= self.consensus_threshold:
            # Strong majority - use majority vote
            swarm_decision.consensus_decision = majority_decision[0]
            swarm_decision.consensus_confidence = majority_agreement
            swarm_decision.consensus_mechanism = 'majority'
            swarm_decision.agreement_level = majority_agreement
            # Apply semantic coherence before returning
            swarm_decision = self._apply_semantic_coherence(swarm_decision, brain_answers)
            return swarm_decision

        # 2. Confidence-weighted voting
        weighted_scores = defaultdict(float)
        total_confidence = 0.0

        for brain_id, decision in swarm_decision.brain_votes.items():
            confidence = swarm_decision.confidence_weights[brain_id]
            weighted_scores[decision] += confidence
            total_confidence += confidence

        if total_confidence > 0:
            weighted_decision = max(weighted_scores.items(), key=lambda x: x[1])
            weighted_agreement = weighted_decision[1] / total_confidence

            if weighted_agreement >= self.consensus_threshold:
                # Weighted consensus reached
                swarm_decision.consensus_decision = weighted_decision[0]
                swarm_decision.consensus_confidence = weighted_agreement
                swarm_decision.consensus_mechanism = 'weighted'
                swarm_decision.agreement_level = weighted_agreement
                # Apply semantic coherence before returning
                swarm_decision = self._apply_semantic_coherence(swarm_decision, brain_answers)
                return swarm_decision

        # 3. Expert opinion (defer to domain specialist)
        expert_brains = [
            (brain_id, brain)
            for brain_id, brain in self.brains.items()
            if brain.primary_domain == task_type
        ]

        if expert_brains:
            # Get expert's vote
            expert_brain_id, expert_brain = expert_brains[0]
            expert_decision = swarm_decision.brain_votes[expert_brain_id]
            expert_confidence = swarm_decision.confidence_weights[expert_brain_id]

            swarm_decision.consensus_decision = expert_decision
            swarm_decision.consensus_confidence = expert_confidence
            swarm_decision.consensus_mechanism = 'expert'
            swarm_decision.agreement_level = 0.5  # Medium (deferred to expert)
            # Apply semantic coherence before returning
            swarm_decision = self._apply_semantic_coherence(swarm_decision, brain_answers)
            return swarm_decision

        # 4. Fallback: Use weighted decision with lower confidence
        swarm_decision.consensus_decision = weighted_decision[0] if weighted_scores else 'wait'
        swarm_decision.consensus_confidence = 0.3  # Low confidence (no clear consensus)
        swarm_decision.consensus_mechanism = 'fallback'
        swarm_decision.agreement_level = majority_agreement
        self.total_disagreements += 1

        # Apply semantic coherence
        swarm_decision = self._apply_semantic_coherence(swarm_decision, brain_answers)
        return swarm_decision

    def _apply_semantic_coherence(
        self,
        swarm_decision: SwarmDecision,
        brain_answers: Optional[List]
    ) -> SwarmDecision:
        """
        Apply semantic coherence metrics to swarm decision

        Args:
            swarm_decision: Swarm decision
            brain_answers: Brain answers for semantic analysis

        Returns:
            Updated swarm decision with semantic metrics
        """
        # === PHASE 13: Semantic Coherence Integration ===
        if self.enable_semantic_coherence and brain_answers and len(brain_answers) >= 2:
            # Compute semantic coherence
            K, U, sim_matrix = self.semantic_layer.compute_coherence(brain_answers)

            # Compute truth stability
            voting_score = swarm_decision.consensus_confidence
            truth_stability = self.semantic_layer.compute_truth_stability(voting_score, K)

            # Update swarm decision with semantic metrics
            swarm_decision.coherence_K = K
            swarm_decision.disagreement_U = U
            swarm_decision.truth_stability = truth_stability

            # Determine status
            if truth_stability >= self.semantic_layer.green_threshold:
                swarm_decision.semantic_status = 'GREEN'
            elif truth_stability >= self.semantic_layer.k_min:
                swarm_decision.semantic_status = 'YELLOW'
            else:
                swarm_decision.semantic_status = 'RED'

            # Log semantic consensus
            semantic_consensus = self.semantic_layer.create_semantic_consensus(
                task_description=swarm_decision.task_description,
                brain_answers=brain_answers,
                decision=swarm_decision.consensus_decision,
                voting_score=voting_score,
                mechanism=swarm_decision.consensus_mechanism
            )
            # Don't double-append (already done in create_semantic_consensus)

        return swarm_decision

    def record_brain_outcome(
        self,
        brain_id: str,
        outcome: str,
        confidence: float
    ):
        """
        Record outcome for a brain

        Args:
            brain_id: Brain ID
            outcome: 'success' or 'failure'
            confidence: Confidence in the decision
        """
        if brain_id not in self.brains:
            return

        brain = self.brains[brain_id]
        brain.tasks_completed += 1

        if outcome == 'success':
            brain.success_count += 1
        else:
            brain.failure_count += 1

        # Update average confidence (exponential moving average)
        alpha = 0.2
        brain.avg_confidence = (1 - alpha) * brain.avg_confidence + alpha * confidence

        # Adapt expertise based on performance
        success_rate = brain.success_rate()
        if success_rate > 0.7:
            # Increase expertise slightly
            brain.expertise_level = min(1.0, brain.expertise_level + 0.01)
        elif success_rate < 0.3:
            # Decrease expertise slightly
            brain.expertise_level = max(0.1, brain.expertise_level - 0.01)

        # Reduce load
        brain.current_load = max(0.0, brain.current_load - 0.2)

    def get_swarm_intelligence_metrics(self) -> Dict:
        """Get metrics about swarm behavior"""
        # Diversity (how different are the brains)
        expertise_levels = [b.expertise_level for b in self.brains.values()]
        diversity = np.std(expertise_levels)

        # Average performance
        avg_success = np.mean([b.success_rate() for b in self.brains.values()])

        # Load distribution
        loads = [b.current_load for b in self.brains.values()]
        load_balance_metric = 1.0 - np.std(loads)  # 1.0 = perfectly balanced

        # Consensus quality
        if self.swarm_decisions:
            avg_agreement = np.mean([d.agreement_level for d in self.swarm_decisions])
            avg_consensus_confidence = np.mean([d.consensus_confidence for d in self.swarm_decisions])
        else:
            avg_agreement = 0.5
            avg_consensus_confidence = 0.5

        return {
            'diversity': diversity,
            'avg_success_rate': avg_success,
            'load_balance': load_balance_metric,
            'avg_agreement': avg_agreement,
            'avg_consensus_confidence': avg_consensus_confidence,
            'disagreement_rate': self.total_disagreements / max(1, self.total_consensus_reached)
        }

    def get_statistics(self) -> Dict:
        """Get swarm statistics"""
        # Brain performance
        brain_stats = {
            brain.brain_id: brain.to_dict()
            for brain in self.brains.values()
        }

        # Consensus mechanisms used
        consensus_mechanisms = defaultdict(int)
        for decision in self.swarm_decisions:
            consensus_mechanisms[decision.consensus_mechanism] += 1

        # Swarm intelligence metrics
        swarm_metrics = self.get_swarm_intelligence_metrics()

        return {
            'num_brains': len(self.brains),
            'total_tasks_processed': self.total_tasks_processed,
            'total_consensus_reached': self.total_consensus_reached,
            'total_disagreements': self.total_disagreements,
            'consensus_mechanisms': dict(consensus_mechanisms),
            'swarm_intelligence': swarm_metrics,
            'top_brains': sorted(
                brain_stats.items(),
                key=lambda x: x[1]['success_rate'],
                reverse=True
            )[:3]
        }

    def __repr__(self):
        return (
            f"MultiBrainSwarm("
            f"brains={len(self.brains)}, "
            f"tasks={self.total_tasks_processed}, "
            f"consensus={self.total_consensus_reached})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("MULTI-BRAIN SWARM SYSTEM (PHASE 12 - FINAL)")
    print("=" * 70)
    print()
    print("This module implements collaborative intelligence:")
    print("  - Multiple specialized brain instances")
    print("  - Task decomposition and allocation")
    print("  - Consensus mechanisms (majority, weighted, expert)")
    print("  - Result aggregation")
    print("  - Swarm intelligence patterns")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_multi_brain_swarm.py")
    print()
    print("=" * 70)

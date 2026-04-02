"""
Multi-CTM Ensemble - Manage Specialized Conscious Turing Machines

Coordinates routing between four specialized CTMs:
1. SpatialCTM: Architecture, infrastructure, topology (Klotski brain)
2. LogicCTM: Verification, constraints, compliance
3. TemporalCTM: Patterns, scheduling, time-series
4. ValueCTM: Decisions, trade-offs, optimization

Usage:
    ensemble = MultiCTMEnsemble()
    result = ensemble.reason_async(
        task="Design microservice architecture",
        brain_state={...}
    )
    # Automatically routes to SpatialCTM
"""

import threading
import uuid
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from core.klotski_ctm import KlotskiCTM, CTMInsight, KLOTSKI_AVAILABLE
    from core.klotski_ctm_async import KlotskiCTMAsyncReasoner, KlotskiAsyncResult, ReasoningStatus
    from core.ctm_domain_router import CTMDomainRouter, CTMDomain, DomainClassification
    from core.meta_ctm import MetaCTMSupervisor, CTMHealth, MetaCTMDecision
    from core.evolutionary_ctm_selector import EvolutionaryCTMSelector, CTMGenes, CTMIndividual
    from core.dream_mode_ctm_trainer import DreamModeCTMTrainer
    DREAM_TRAINER_AVAILABLE = True
except ImportError:
    from klotski_ctm import KlotskiCTM, CTMInsight, KLOTSKI_AVAILABLE
    from klotski_ctm_async import KlotskiCTMAsyncReasoner, KlotskiAsyncResult, ReasoningStatus
    from ctm_domain_router import CTMDomainRouter, CTMDomain, DomainClassification
    from meta_ctm import MetaCTMSupervisor, CTMHealth, MetaCTMDecision
    from evolutionary_ctm_selector import EvolutionaryCTMSelector, CTMGenes, CTMIndividual
    DREAM_TRAINER_AVAILABLE = False


@dataclass
class CrossCTMContext:
    """
    Shared context for inter-CTM communication

    Used for sequential CTM chaining where output from one CTM
    informs the next CTM's reasoning.
    """
    shared_insights: Dict[str, str]  # Domain -> insight
    constraints: List[str]  # Constraints from LogicCTM
    temporal_factors: List[str]  # Time-related factors from TemporalCTM
    value_assessments: Dict[str, float]  # Value assessments from ValueCTM
    spatial_structures: List[str]  # Structure info from SpatialCTM
    execution_order: List[str]  # Recommended execution order
    conflict_resolutions: List[str]  # Resolved conflicts


@dataclass
class EnsembleResult:
    """
    Result from Multi-CTM Ensemble reasoning

    Attributes:
        task_id: Ensemble task identifier
        task: Task description
        primary_domain: Primary CTM domain used
        secondary_domains: Additional domains (for mixed tasks)
        ctm_results: Dict mapping domain to KlotskiAsyncResult
        aggregated_insights: Combined insights if multi-CTM
        reasoning_chain: Explanation of routing decisions
        elapsed_time: Total time (max of all CTMs)
        cross_ctm_context: Shared context from CTM collaboration
    """
    task_id: str
    task: str
    primary_domain: CTMDomain
    secondary_domains: List[CTMDomain]
    ctm_results: Dict[CTMDomain, Optional[KlotskiAsyncResult]]
    aggregated_insights: Optional[str]
    reasoning_chain: str
    elapsed_time: float
    cross_ctm_context: Optional[CrossCTMContext] = None


class MultiCTMEnsemble:
    """
    Multi-CTM Ensemble Manager

    Manages four specialized CTMs and routes tasks based on domain analysis.

    Architecture:
    1. Task arrives → CTMDomainRouter classifies domain
    2. Launch appropriate specialized CTM(s) asynchronously
    3. For mixed-domain tasks, run multiple CTMs in parallel
    4. Aggregate insights from multiple CTMs if needed
    5. Return unified result with reasoning chain

    Current Status:
    - SpatialCTM: ✅ TRAINED (Klotski puzzle brain, SOM-dominant)
    - LogicCTM: ⏸️ PENDING (will be trained in Dream Mode)
    - TemporalCTM: ⏸️ PENDING (will be trained in Dream Mode)
    - ValueCTM: ⏸️ PENDING (will be trained in Dream Mode)
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'MultiCTMEnsemble':
        """Create MultiCTMEnsemble from YAML config dict (P5.69)."""
        ctm = yaml_config.get('ctm_ensemble', {})
        return cls(
            max_concurrent_per_ctm=ctm.get('max_concurrent_per_ctm', 2),
            feature_dim=ctm.get('feature_dim', 256),
            consciousness_threshold=ctm.get('consciousness_threshold', 0.85),
            max_reasoning_steps=ctm.get('max_reasoning_steps', 50),
            enable_logic_ctm=ctm.get('enable_logic_ctm', True),
            enable_temporal_ctm=ctm.get('enable_temporal_ctm', True),
            enable_value_ctm=ctm.get('enable_value_ctm', True),
            enable_evolution=ctm.get('enable_evolution', True),
            evolution_population_size=ctm.get('evolution_population_size', 20),
            evolution_trigger_count=ctm.get('evolution_trigger_count', 10),
        )

    def __init__(
        self,
        max_concurrent_per_ctm: int = 2,
        feature_dim: int = 256,
        consciousness_threshold: float = 0.85,
        max_reasoning_steps: int = 50,
        device: str = 'cpu',
        enable_logic_ctm: bool = True,       # Trained to ~77% convergence
        enable_temporal_ctm: bool = True,    # Trained to ~77% convergence
        enable_value_ctm: bool = True,       # Trained to ~78% convergence
        enable_evolution: bool = True,       # Enable evolutionary optimization
        evolution_population_size: int = 20,
        evolution_trigger_count: int = 10    # Evolve after N tasks per domain
    ):
        """
        Initialize Multi-CTM Ensemble

        Args:
            max_concurrent_per_ctm: Max tasks per CTM simultaneously
            feature_dim: Klotski brain feature dimension
            consciousness_threshold: Convergence threshold
            max_reasoning_steps: Max CTM reasoning steps
            device: torch device ('cpu' or 'cuda')
            enable_logic_ctm: Enable LogicCTM (checkpoint: logic_brain_epoch_24.pth, 99.70%)
            enable_temporal_ctm: Enable TemporalCTM (checkpoint: temporal_brain_epoch_46.pth, 99.73%)
            enable_value_ctm: Enable ValueCTM (checkpoint: value_brain_epoch_30.pth, 99.86%)
            enable_evolution: Enable evolutionary CTM optimization
            evolution_population_size: Population size for evolution
            evolution_trigger_count: Tasks before triggering evolution
        """
        if not KLOTSKI_AVAILABLE:
            raise RuntimeError("Klotski CTM not available. Install neurosymbolic brain.")

        self.max_concurrent_per_ctm = max_concurrent_per_ctm
        self.feature_dim = feature_dim
        self.consciousness_threshold = consciousness_threshold
        self.max_reasoning_steps = max_reasoning_steps
        self.device = device

        # Domain router
        self.domain_router = CTMDomainRouter(
            mixed_domain_threshold=0.70,
            confidence_min=0.50
        )

        # Initialize CTMs (only Spatial for now)
        self.ctms: Dict[CTMDomain, Optional[KlotskiCTMAsyncReasoner]] = {}

        # SpatialCTM (always available)
        print("[MultiCTMEnsemble] Initializing SpatialCTM (Klotski brain)...")
        self.ctms[CTMDomain.SPATIAL] = KlotskiCTMAsyncReasoner(
            max_concurrent_tasks=max_concurrent_per_ctm,
            feature_dim=feature_dim,
            consciousness_threshold=consciousness_threshold,
            max_reasoning_steps=max_reasoning_steps,
            device=device
        )

        # LogicCTM (trained)
        if enable_logic_ctm:
            print("[MultiCTMEnsemble] Initializing LogicCTM...")
            self.ctms[CTMDomain.LOGIC] = KlotskiCTMAsyncReasoner(
                max_concurrent_tasks=max_concurrent_per_ctm,
                feature_dim=feature_dim,
                consciousness_threshold=0.90,  # Higher for logical certainty
                max_reasoning_steps=max_reasoning_steps,
                device=device
            )
            # Load trained weights
            logic_weights_path = "data/ctm_checkpoints/logic_brain_epoch_24.pth"
            if self.ctms[CTMDomain.LOGIC].load_weights(logic_weights_path):
                print("[MultiCTMEnsemble] LogicCTM weights loaded successfully")
            else:
                print("[MultiCTMEnsemble] LogicCTM using default initialization")
        else:
            self.ctms[CTMDomain.LOGIC] = None
            print("[MultiCTMEnsemble] LogicCTM disabled")

        # TemporalCTM (trained)
        if enable_temporal_ctm:
            print("[MultiCTMEnsemble] Initializing TemporalCTM...")
            self.ctms[CTMDomain.TEMPORAL] = KlotskiCTMAsyncReasoner(
                max_concurrent_tasks=max_concurrent_per_ctm,
                feature_dim=feature_dim,
                consciousness_threshold=0.80,  # Lower for fuzzy patterns
                max_reasoning_steps=max_reasoning_steps,
                device=device
            )
            # Load trained weights
            temporal_weights_path = "data/ctm_checkpoints/temporal_brain_epoch_46.pth"
            if self.ctms[CTMDomain.TEMPORAL].load_weights(temporal_weights_path):
                print("[MultiCTMEnsemble] TemporalCTM weights loaded successfully")
            else:
                print("[MultiCTMEnsemble] TemporalCTM using default initialization")
        else:
            self.ctms[CTMDomain.TEMPORAL] = None
            print("[MultiCTMEnsemble] TemporalCTM disabled")

        # ValueCTM (trained)
        if enable_value_ctm:
            print("[MultiCTMEnsemble] Initializing ValueCTM...")
            self.ctms[CTMDomain.VALUE] = KlotskiCTMAsyncReasoner(
                max_concurrent_tasks=max_concurrent_per_ctm,
                feature_dim=feature_dim,
                consciousness_threshold=0.85,
                max_reasoning_steps=max_reasoning_steps,
                device=device
            )
            # Load trained weights
            value_weights_path = "data/ctm_checkpoints/value_brain_epoch_30.pth"
            if self.ctms[CTMDomain.VALUE].load_weights(value_weights_path):
                print("[MultiCTMEnsemble] ValueCTM weights loaded successfully")
            else:
                print("[MultiCTMEnsemble] ValueCTM using default initialization")
        else:
            self.ctms[CTMDomain.VALUE] = None
            print("[MultiCTMEnsemble] ValueCTM disabled")

        # Task tracking
        self.ensemble_tasks: Dict[str, EnsembleResult] = {}
        self.task_lock = threading.Lock()

        # Meta-CTM Supervisor for intelligent CTM selection and monitoring
        self.supervisor = MetaCTMSupervisor(
            consciousness_threshold=consciousness_threshold,
            max_consecutive_failures=3,
            reset_cooldown=60.0,
            enable_auto_reset=True,
            enable_load_balancing=True
        )
        print("[MultiCTMEnsemble] Meta-CTM Supervisor initialized")

        # Evolutionary CTM Selector for hyperparameter optimization
        self.enable_evolution = enable_evolution
        self.evolution_trigger_count = evolution_trigger_count
        self.domain_task_counts: Dict[str, int] = {
            'spatial': 0, 'logic': 0, 'temporal': 0, 'value': 0
        }

        if enable_evolution:
            self.evolutionary_selector = EvolutionaryCTMSelector(
                population_size=evolution_population_size,
                elite_count=2,
                mutation_rate=0.15,
                crossover_rate=0.7,
                enable_adaptive_mutation=True
            )
            print("[MultiCTMEnsemble] Evolutionary CTM Selector initialized")
        else:
            self.evolutionary_selector = None
            print("[MultiCTMEnsemble] Evolutionary optimization disabled")

        print(f"[MultiCTMEnsemble] Initialized with {sum(1 for c in self.ctms.values() if c is not None)} active CTMs")

    def reason_async(
        self,
        task: str,
        brain_state: Dict,
        max_steps: Optional[int] = None,
        domain_hint: Optional[str] = None
    ) -> str:
        """
        Start asynchronous multi-CTM reasoning

        Args:
            task: Task description
            brain_state: Current Tahlamus brain state
            max_steps: Override max reasoning steps
            domain_hint: Optional domain hint (bypass router)

        Returns:
            Ensemble task ID for later retrieval
        """
        ensemble_task_id = str(uuid.uuid4())[:8]

        # Step 1: Domain Router classifies task (comprehensive keyword analysis)
        classification = self.domain_router.classify_task(task)

        # Step 2: Use router classification as domain_hint for supervisor
        # Supervisor adds health monitoring and performance history
        effective_hint = domain_hint or classification.primary_domain.value
        supervisor_decision = self.supervisor.select_ctm(
            task=task,
            domain_hint=effective_hint,
            require_healthy=True
        )

        # Map supervisor selection to CTMDomain
        domain_map = {
            'spatial': CTMDomain.SPATIAL,
            'logic': CTMDomain.LOGIC,
            'temporal': CTMDomain.TEMPORAL,
            'value': CTMDomain.VALUE
        }
        primary_domain = domain_map.get(supervisor_decision.selected_ctm, CTMDomain.SPATIAL)
        secondary_domains = [domain_map[d] for d in supervisor_decision.alternatives if d in domain_map]

        # Add router's secondary domains if supervisor agrees on primary
        if classification.primary_domain == primary_domain and classification.secondary_domains:
            for sec_domain in classification.secondary_domains:
                if sec_domain not in secondary_domains:
                    secondary_domains.append(sec_domain)

        print(f"\n[MultiCTMEnsemble] Task {ensemble_task_id}")
        print(f"[MultiCTMEnsemble] Task: {task[:60]}...")
        print(f"[MultiCTMEnsemble] Router classified: {classification.primary_domain.value} (conf: {classification.confidence:.2f})")
        print(f"[MultiCTMEnsemble] Supervisor selected: {primary_domain.value} (conf: {supervisor_decision.confidence:.2f})")
        print(f"[MultiCTMEnsemble] Combined reasoning: {supervisor_decision.reasoning}")
        if secondary_domains:
            print(f"[MultiCTMEnsemble] Secondary domains: {[d.value for d in secondary_domains]}")

        # Launch CTM(s)
        ctm_task_ids: Dict[CTMDomain, Optional[str]] = {}
        domains_to_run = [primary_domain] + secondary_domains

        for domain in domains_to_run:
            ctm = self.ctms.get(domain)

            if ctm is None:
                print(f"[MultiCTMEnsemble] {domain.value}CTM not available (not trained yet)")
                print(f"[MultiCTMEnsemble] Falling back to SpatialCTM (most general)")
                # Fallback to SpatialCTM
                ctm = self.ctms[CTMDomain.SPATIAL]
                domain = CTMDomain.SPATIAL

            if ctm:
                print(f"[MultiCTMEnsemble] Starting {domain.value}CTM reasoning...")
                ctm_task_id = ctm.start_reasoning_async(
                    task=task,
                    brain_state=brain_state,
                    max_steps=max_steps
                )
                ctm_task_ids[domain] = ctm_task_id
            else:
                ctm_task_ids[domain] = None

        # Create ensemble result placeholder
        with self.task_lock:
            self.ensemble_tasks[ensemble_task_id] = EnsembleResult(
                task_id=ensemble_task_id,
                task=task,
                primary_domain=primary_domain,
                secondary_domains=secondary_domains,
                ctm_results={},
                aggregated_insights=None,
                reasoning_chain=classification.reasoning,
                elapsed_time=0.0
            )

        # Store CTM task IDs for retrieval
        self.ensemble_tasks[ensemble_task_id].ctm_results = {
            domain: None for domain in ctm_task_ids.keys()
        }

        # Start background aggregation thread
        thread = threading.Thread(
            target=self._aggregation_worker,
            args=(ensemble_task_id, ctm_task_ids),
            daemon=True
        )
        thread.start()

        return ensemble_task_id

    def _aggregation_worker(
        self,
        ensemble_task_id: str,
        ctm_task_ids: Dict[CTMDomain, Optional[str]]
    ):
        """
        Worker thread to collect and aggregate CTM results

        Args:
            ensemble_task_id: Ensemble task identifier
            ctm_task_ids: Dict mapping domain to CTM task ID
        """
        start_time = time.time()

        # Wait for all CTMs to complete
        ctm_results: Dict[CTMDomain, Optional[KlotskiAsyncResult]] = {}

        for domain, ctm_task_id in ctm_task_ids.items():
            if ctm_task_id is None:
                ctm_results[domain] = None
                continue

            ctm = self.ctms[domain]
            if ctm:
                # Wait for result (with timeout)
                result = ctm.get_result(ctm_task_id, wait=True, timeout=30)
                ctm_results[domain] = result
            else:
                ctm_results[domain] = None

        elapsed = time.time() - start_time

        # Aggregate insights if multi-CTM
        aggregated_insights = None
        if len([r for r in ctm_results.values() if r and r.status == ReasoningStatus.COMPLETED]) > 1:
            aggregated_insights = self._aggregate_insights(ctm_results)

        # Record results with Meta-CTM Supervisor for learning
        task_description = ""
        with self.task_lock:
            if ensemble_task_id in self.ensemble_tasks:
                task_description = self.ensemble_tasks[ensemble_task_id].task

        for domain, result in ctm_results.items():
            if result and result.ctm_insight:
                # Record performance metrics with supervisor
                self.supervisor.record_task_result(
                    task_id=f"{ensemble_task_id}_{domain.value}",
                    domain=domain.value,
                    consciousness=result.ctm_insight.final_consciousness,
                    response_time=elapsed,
                    success=(result.status == ReasoningStatus.COMPLETED),
                    task_description=task_description
                )

                # Record with evolutionary selector for fitness evaluation
                if self.enable_evolution and self.evolutionary_selector:
                    # Get the best individual for this domain to record performance
                    best_ind = self.evolutionary_selector.select_best_ctm(domain.value)
                    if best_ind:
                        self.evolutionary_selector.record_performance(
                            domain=domain.value,
                            individual_id=best_ind.id,
                            consciousness=result.ctm_insight.final_consciousness,
                            response_time=elapsed,
                            success=(result.status == ReasoningStatus.COMPLETED),
                            complexity=0.7  # Could be derived from task analysis
                        )

                    # Track task count and trigger evolution if threshold reached
                    self.domain_task_counts[domain.value] += 1
                    if self.domain_task_counts[domain.value] >= self.evolution_trigger_count:
                        self._trigger_evolution(domain.value)
                        self.domain_task_counts[domain.value] = 0

        # Update ensemble result
        with self.task_lock:
            if ensemble_task_id in self.ensemble_tasks:
                self.ensemble_tasks[ensemble_task_id].ctm_results = ctm_results
                self.ensemble_tasks[ensemble_task_id].aggregated_insights = aggregated_insights
                self.ensemble_tasks[ensemble_task_id].elapsed_time = elapsed

        print(f"[MultiCTMEnsemble] Task {ensemble_task_id} aggregation complete in {elapsed:.1f}s")

    def _aggregate_insights(
        self,
        ctm_results: Dict[CTMDomain, Optional[KlotskiAsyncResult]]
    ) -> str:
        """
        Aggregate insights from multiple CTMs

        Args:
            ctm_results: Results from each CTM

        Returns:
            Aggregated insight string
        """
        insights = []

        for domain, result in ctm_results.items():
            if result and result.status == ReasoningStatus.COMPLETED and result.ctm_insight:
                insight = result.ctm_insight
                insights.append(
                    f"[{domain.value}CTM] {insight.suggested_strategy} "
                    f"(consciousness: {insight.final_consciousness:.2f}, "
                    f"confidence: {insight.confidence:.0%})"
                )

        if not insights:
            return "No insights available"

        return "\n".join(insights)

    def get_result(
        self,
        ensemble_task_id: str,
        wait: bool = False,
        timeout: float = 30.0
    ) -> Optional[EnsembleResult]:
        """
        Get ensemble result

        Args:
            ensemble_task_id: Ensemble task identifier
            wait: If True, block until complete
            timeout: Max time to wait (seconds)

        Returns:
            EnsembleResult or None if not found
        """
        if wait:
            start_time = time.time()

            while ensemble_task_id in self.ensemble_tasks:
                result = self.ensemble_tasks[ensemble_task_id]

                # Check if all CTMs have completed
                all_complete = all(
                    ctm_result is not None or domain not in result.ctm_results
                    for domain, ctm_result in result.ctm_results.items()
                )

                if all_complete:
                    break

                if time.time() - start_time > timeout:
                    print(f"[MultiCTMEnsemble] Task {ensemble_task_id} TIMEOUT after {timeout}s")
                    break

                time.sleep(0.1)

        with self.task_lock:
            return self.ensemble_tasks.get(ensemble_task_id)

    def get_stats(self) -> Dict:
        """Get ensemble statistics"""
        with self.task_lock:
            total_tasks = len(self.ensemble_tasks)

            # Count tasks by primary domain
            domain_counts = {domain: 0 for domain in CTMDomain}
            for result in self.ensemble_tasks.values():
                domain_counts[result.primary_domain] += 1

            # Get per-CTM stats
            ctm_stats = {}
            for domain, ctm in self.ctms.items():
                if ctm:
                    ctm_stats[domain.value] = ctm.get_stats()

        # Get evolution stats if enabled
        evolution_stats = None
        if self.enable_evolution and self.evolutionary_selector:
            evolution_stats = self.evolutionary_selector.get_all_stats()

        return {
            'total_ensemble_tasks': total_tasks,
            'tasks_by_domain': {d.value: c for d, c in domain_counts.items()},
            'ctm_stats': ctm_stats,
            'active_ctms': [d.value for d, c in self.ctms.items() if c is not None],
            'supervisor_health': self.supervisor.get_health_status(),
            'supervisor_stats': self.supervisor.get_statistics(),
            'evolution_enabled': self.enable_evolution,
            'evolution_stats': evolution_stats,
            'domain_task_counts': self.domain_task_counts
        }

    def get_ctm_health(self) -> Dict:
        """
        Get health status of all CTMs from supervisor

        Returns:
            Dict with health metrics for each CTM domain
        """
        return self.supervisor.get_health_status()

    def get_routing_recommendation(self, task: str) -> Dict:
        """
        Get routing recommendation from supervisor without executing

        Args:
            task: Task description

        Returns:
            Routing recommendation with CTM selection and context
        """
        return self.supervisor.get_routing_recommendation(task)

    def reset_ctm(self, domain: str) -> bool:
        """
        Reset a specific CTM's performance metrics

        Args:
            domain: CTM domain to reset (spatial/logic/temporal/value)

        Returns:
            True if reset successful
        """
        return self.supervisor.reset_ctm(domain)

    def _trigger_evolution(self, domain: str):
        """
        Trigger evolution for a domain (internal method)

        Args:
            domain: Domain to evolve
        """
        if not self.evolutionary_selector:
            return

        print(f"[MultiCTMEnsemble] Triggering evolution for {domain}CTM...")
        result = self.evolutionary_selector.evolve_population(domain)

        if 'error' not in result:
            print(f"[MultiCTMEnsemble] {domain}CTM evolved to generation {result['generation']}")
            print(f"[MultiCTMEnsemble]   Fitness: {result['pre_evolution']['best_fitness']:.3f} -> {result['post_evolution']['best_fitness']:.3f}")
            print(f"[MultiCTMEnsemble]   Diversity: {result['post_evolution']['diversity']:.3f}")

    def evolve_domain(self, domain: str) -> Dict:
        """
        Manually trigger evolution for a domain

        Args:
            domain: Domain to evolve (spatial/logic/temporal/value)

        Returns:
            Evolution statistics
        """
        if not self.evolutionary_selector:
            return {'error': 'Evolution disabled'}

        return self.evolutionary_selector.evolve_population(domain)

    def evolve_all_domains(self) -> Dict[str, Dict]:
        """
        Trigger evolution for all domains

        Returns:
            Dict mapping domain to evolution statistics
        """
        if not self.evolutionary_selector:
            return {'error': 'Evolution disabled'}

        results = {}
        for domain in ['spatial', 'logic', 'temporal', 'value']:
            results[domain] = self.evolutionary_selector.evolve_population(domain)
        return results

    def get_evolution_stats(self, domain: Optional[str] = None) -> Dict:
        """
        Get evolutionary optimization statistics

        Args:
            domain: Specific domain or None for all

        Returns:
            Evolution statistics
        """
        if not self.evolutionary_selector:
            return {'error': 'Evolution disabled'}

        if domain:
            return self.evolutionary_selector.get_population_stats(domain)
        return self.evolutionary_selector.get_all_stats()

    def get_best_genes(self, domain: str) -> Optional[CTMGenes]:
        """
        Get the best evolved genes for a domain

        Args:
            domain: Domain to get genes for

        Returns:
            CTMGenes configuration or None
        """
        if not self.evolutionary_selector:
            return None
        return self.evolutionary_selector.get_best_genes(domain)

    def inject_ctm_configuration(self, domain: str, genes: CTMGenes, fitness: float = 0.5):
        """
        Inject a custom CTM configuration into the population

        Useful for seeding with pre-trained configurations.

        Args:
            domain: Target domain
            genes: Gene configuration to inject
            fitness: Initial fitness estimate
        """
        if self.evolutionary_selector:
            self.evolutionary_selector.inject_individual(domain, genes, fitness)

    def reason_with_collaboration(
        self,
        task: str,
        brain_state: Dict,
        max_steps: Optional[int] = None,
        execution_order: Optional[List[CTMDomain]] = None
    ) -> EnsembleResult:
        """
        Sequential CTM reasoning with cross-CTM communication

        Unlike reason_async (parallel), this method executes CTMs sequentially,
        passing context from one CTM to the next. Each CTM's insights inform
        subsequent CTMs, enabling deeper collaborative reasoning.

        Default execution order: Spatial → Logic → Temporal → Value
        - Spatial: Establishes structure/architecture
        - Logic: Validates constraints against structure
        - Temporal: Plans timing/scheduling
        - Value: Optimizes trade-offs given all context

        Args:
            task: Task description
            brain_state: Current brain state
            max_steps: Override max reasoning steps per CTM
            execution_order: Custom CTM execution order

        Returns:
            EnsembleResult with cross_ctm_context populated
        """
        ensemble_task_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Default execution order: Spatial → Logic → Temporal → Value
        if execution_order is None:
            execution_order = [
                CTMDomain.SPATIAL,
                CTMDomain.LOGIC,
                CTMDomain.TEMPORAL,
                CTMDomain.VALUE
            ]

        print(f"\n[MultiCTMEnsemble] Collaborative Task {ensemble_task_id}")
        print(f"[MultiCTMEnsemble] Task: {task[:60]}...")
        print(f"[MultiCTMEnsemble] Execution order: {[d.value for d in execution_order]}")

        # Initialize cross-CTM context
        cross_ctx = CrossCTMContext(
            shared_insights={},
            constraints=[],
            temporal_factors=[],
            value_assessments={},
            spatial_structures=[],
            execution_order=[d.value for d in execution_order],
            conflict_resolutions=[]
        )

        # Track results from each CTM
        ctm_results: Dict[CTMDomain, Optional[KlotskiAsyncResult]] = {}
        reasoning_chain_parts = [f"Collaborative reasoning for: {task[:50]}..."]

        # Execute CTMs sequentially with context passing
        for domain in execution_order:
            ctm = self.ctms.get(domain)

            # Skip if CTM not available (not trained)
            if ctm is None:
                print(f"[MultiCTMEnsemble] {domain.value}CTM not available, skipping")
                ctm_results[domain] = None
                continue

            # Enrich task with cross-CTM context
            enriched_task = self._enrich_task_with_context(task, domain, cross_ctx)

            print(f"[MultiCTMEnsemble] Starting {domain.value}CTM with context...")

            # Start reasoning (blocking wait for sequential execution)
            ctm_task_id = ctm.start_reasoning_async(
                task=enriched_task,
                brain_state=brain_state,
                max_steps=max_steps
            )

            # Wait for result
            result = ctm.get_result(ctm_task_id, wait=True, timeout=30)
            ctm_results[domain] = result

            # Extract insights and update cross-CTM context
            if result and result.status == ReasoningStatus.COMPLETED and result.ctm_insight:
                insight = result.ctm_insight
                cross_ctx = self._update_cross_context(cross_ctx, domain, insight)

                reasoning_chain_parts.append(
                    f"[{domain.value}CTM] {insight.suggested_strategy} "
                    f"(consciousness: {insight.final_consciousness:.2f})"
                )

                print(f"[MultiCTMEnsemble] {domain.value}CTM complete: {insight.suggested_strategy[:50]}...")
            else:
                reasoning_chain_parts.append(f"[{domain.value}CTM] No insight available")

        # Resolve any conflicts between CTMs
        cross_ctx = self._resolve_conflicts(cross_ctx, ctm_results)

        elapsed = time.time() - start_time

        # Aggregate final insights
        aggregated_insights = self._aggregate_collaborative_insights(cross_ctx, ctm_results)

        # Build result
        primary_domain = execution_order[0] if execution_order else CTMDomain.SPATIAL
        secondary_domains = execution_order[1:] if len(execution_order) > 1 else []

        result = EnsembleResult(
            task_id=ensemble_task_id,
            task=task,
            primary_domain=primary_domain,
            secondary_domains=secondary_domains,
            ctm_results=ctm_results,
            aggregated_insights=aggregated_insights,
            reasoning_chain="\n".join(reasoning_chain_parts),
            elapsed_time=elapsed,
            cross_ctm_context=cross_ctx
        )

        # Store result
        with self.task_lock:
            self.ensemble_tasks[ensemble_task_id] = result

        print(f"[MultiCTMEnsemble] Collaborative reasoning complete in {elapsed:.1f}s")

        return result

    def _enrich_task_with_context(
        self,
        task: str,
        domain: CTMDomain,
        cross_ctx: CrossCTMContext
    ) -> str:
        """
        Enrich task description with insights from previous CTMs

        Args:
            task: Original task
            domain: Current CTM domain
            cross_ctx: Cross-CTM context with previous insights

        Returns:
            Enriched task string
        """
        enrichments = []

        # Add relevant context based on domain
        if domain == CTMDomain.LOGIC and cross_ctx.spatial_structures:
            enrichments.append(f"[Spatial Context: {'; '.join(cross_ctx.spatial_structures[:3])}]")

        elif domain == CTMDomain.TEMPORAL:
            if cross_ctx.spatial_structures:
                enrichments.append(f"[Structure: {'; '.join(cross_ctx.spatial_structures[:2])}]")
            if cross_ctx.constraints:
                enrichments.append(f"[Constraints: {'; '.join(cross_ctx.constraints[:2])}]")

        elif domain == CTMDomain.VALUE:
            if cross_ctx.spatial_structures:
                enrichments.append(f"[Architecture: {cross_ctx.spatial_structures[0] if cross_ctx.spatial_structures else 'N/A'}]")
            if cross_ctx.constraints:
                enrichments.append(f"[Must satisfy: {'; '.join(cross_ctx.constraints[:2])}]")
            if cross_ctx.temporal_factors:
                enrichments.append(f"[Timing: {'; '.join(cross_ctx.temporal_factors[:2])}]")

        if enrichments:
            return f"{task}\n\nCross-CTM Context:\n" + "\n".join(enrichments)
        return task

    def _update_cross_context(
        self,
        cross_ctx: CrossCTMContext,
        domain: CTMDomain,
        insight: CTMInsight
    ) -> CrossCTMContext:
        """
        Update cross-CTM context with insights from completed CTM

        Args:
            cross_ctx: Current cross-CTM context
            domain: Domain of completed CTM
            insight: Insight from completed CTM

        Returns:
            Updated CrossCTMContext
        """
        # Store the insight
        cross_ctx.shared_insights[domain.value] = insight.suggested_strategy

        # Extract domain-specific information
        strategy = insight.suggested_strategy.lower()

        if domain == CTMDomain.SPATIAL:
            # Extract structural information
            structures = []
            if 'microservice' in strategy or 'service' in strategy:
                structures.append("microservice architecture")
            if 'layer' in strategy or 'tier' in strategy:
                structures.append("layered design")
            if 'mesh' in strategy or 'network' in strategy:
                structures.append("service mesh")
            if 'container' in strategy or 'docker' in strategy:
                structures.append("containerized deployment")
            if 'cluster' in strategy or 'distributed' in strategy:
                structures.append("distributed cluster")
            cross_ctx.spatial_structures.extend(structures if structures else ["modular structure"])

        elif domain == CTMDomain.LOGIC:
            # Extract constraints
            constraints = []
            if 'valid' in strategy or 'compliance' in strategy:
                constraints.append("validation required")
            if 'security' in strategy or 'auth' in strategy:
                constraints.append("security constraints")
            if 'policy' in strategy or 'rule' in strategy:
                constraints.append("policy enforcement")
            if 'type' in strategy or 'schema' in strategy:
                constraints.append("type safety")
            cross_ctx.constraints.extend(constraints if constraints else ["logical consistency"])

        elif domain == CTMDomain.TEMPORAL:
            # Extract temporal factors
            temporal = []
            if 'schedule' in strategy or 'timing' in strategy:
                temporal.append("scheduled execution")
            if 'sequence' in strategy or 'order' in strategy:
                temporal.append("sequential dependencies")
            if 'pattern' in strategy or 'trend' in strategy:
                temporal.append("pattern-based timing")
            if 'scale' in strategy or 'auto' in strategy:
                temporal.append("auto-scaling triggers")
            cross_ctx.temporal_factors.extend(temporal if temporal else ["time-aware"])

        elif domain == CTMDomain.VALUE:
            # Extract value assessments
            if 'cost' in strategy:
                cross_ctx.value_assessments['cost_priority'] = 0.8
            if 'performance' in strategy or 'speed' in strategy:
                cross_ctx.value_assessments['performance_priority'] = 0.9
            if 'reliability' in strategy or 'robust' in strategy:
                cross_ctx.value_assessments['reliability_priority'] = 0.85
            if 'trade' in strategy or 'balance' in strategy:
                cross_ctx.value_assessments['balanced_approach'] = 0.7
            if not cross_ctx.value_assessments:
                cross_ctx.value_assessments['general_optimization'] = 0.75

        return cross_ctx

    def _resolve_conflicts(
        self,
        cross_ctx: CrossCTMContext,
        ctm_results: Dict[CTMDomain, Optional[KlotskiAsyncResult]]
    ) -> CrossCTMContext:
        """
        Resolve conflicts between CTM recommendations

        Args:
            cross_ctx: Cross-CTM context
            ctm_results: Results from all CTMs

        Returns:
            Updated context with conflict resolutions
        """
        resolutions = []

        # Check for common conflicts

        # Conflict: Performance vs Cost
        if (cross_ctx.value_assessments.get('performance_priority', 0) > 0.8 and
            cross_ctx.value_assessments.get('cost_priority', 0) > 0.7):
            resolutions.append(
                "Performance-Cost trade-off: Prioritize critical path performance, "
                "optimize cost on non-critical paths"
            )

        # Conflict: Speed vs Reliability
        if ('auto-scaling triggers' in cross_ctx.temporal_factors and
            'validation required' in cross_ctx.constraints):
            resolutions.append(
                "Speed-Safety trade-off: Apply fast-path for validated requests, "
                "full validation for new patterns"
            )

        # Conflict: Distributed vs Simple
        if ('distributed cluster' in cross_ctx.spatial_structures and
            'logical consistency' in cross_ctx.constraints):
            resolutions.append(
                "Complexity trade-off: Use eventual consistency for non-critical data, "
                "strong consistency for critical transactions"
            )

        cross_ctx.conflict_resolutions = resolutions
        return cross_ctx

    def _aggregate_collaborative_insights(
        self,
        cross_ctx: CrossCTMContext,
        ctm_results: Dict[CTMDomain, Optional[KlotskiAsyncResult]]
    ) -> str:
        """
        Aggregate insights from collaborative reasoning

        Args:
            cross_ctx: Cross-CTM context with all insights
            ctm_results: Results from all CTMs

        Returns:
            Aggregated insight string
        """
        sections = []

        # Summary of each CTM's contribution
        for domain_name, insight in cross_ctx.shared_insights.items():
            sections.append(f"[{domain_name}] {insight}")

        # Key structures identified
        if cross_ctx.spatial_structures:
            sections.append(f"\nArchitecture: {', '.join(set(cross_ctx.spatial_structures))}")

        # Constraints to honor
        if cross_ctx.constraints:
            sections.append(f"Constraints: {', '.join(set(cross_ctx.constraints))}")

        # Temporal considerations
        if cross_ctx.temporal_factors:
            sections.append(f"Timing: {', '.join(set(cross_ctx.temporal_factors))}")

        # Value priorities
        if cross_ctx.value_assessments:
            priorities = [f"{k}: {v:.0%}" for k, v in cross_ctx.value_assessments.items()]
            sections.append(f"Priorities: {', '.join(priorities)}")

        # Conflict resolutions
        if cross_ctx.conflict_resolutions:
            sections.append(f"\nConflict Resolutions:")
            for resolution in cross_ctx.conflict_resolutions:
                sections.append(f"  • {resolution}")

        return "\n".join(sections) if sections else "No collaborative insights available"

    def send_inter_ctm_message(
        self,
        from_domain: CTMDomain,
        to_domain: CTMDomain,
        message_type: str,
        content: Dict
    ) -> bool:
        """
        Send a message between CTMs (for future real-time communication)

        Args:
            from_domain: Source CTM domain
            to_domain: Target CTM domain
            message_type: Type of message (constraint, insight, query, response)
            content: Message content

        Returns:
            True if message sent successfully
        """
        # This is a placeholder for future inter-CTM messaging
        # Currently, context passing happens through CrossCTMContext

        print(f"[MultiCTMEnsemble] Message {from_domain.value} → {to_domain.value}: {message_type}")

        # In future: Could implement async message queues between CTMs
        # For now, this records the intent for logging/debugging

        return True

    # =========================================================================
    # DREAM MODE TRAINING INTEGRATION
    # =========================================================================

    def get_pending_ctms(self) -> List[CTMDomain]:
        """
        Get list of CTM domains that need training.

        Returns:
            List of CTMDomain values for untrained CTMs
        """
        pending = []
        for domain in [CTMDomain.LOGIC, CTMDomain.TEMPORAL, CTMDomain.VALUE]:
            if self.ctms.get(domain) is None:
                pending.append(domain)
        return pending

    def train_ctm_async(
        self,
        domain: CTMDomain,
        num_epochs: int = 10,
        checkpoint_dir: str = "data/ctm_checkpoints"
    ) -> Optional[str]:
        """
        Start background training for a pending CTM using Dream Mode.

        Args:
            domain: CTM domain to train (LOGIC, TEMPORAL, or VALUE)
            num_epochs: Number of training epochs
            checkpoint_dir: Directory to save checkpoints

        Returns:
            Training task ID or None if training unavailable
        """
        if not DREAM_TRAINER_AVAILABLE:
            print("[MultiCTMEnsemble] Dream Mode training not available")
            return None

        if domain == CTMDomain.SPATIAL:
            print("[MultiCTMEnsemble] SpatialCTM is already trained")
            return None

        # Initialize trainer if needed
        if not hasattr(self, '_dream_trainer'):
            self._dream_trainer = DreamModeCTMTrainer(
                checkpoint_dir=checkpoint_dir
            )

        # Define target module routing per domain
        target_routing = {
            CTMDomain.LOGIC: {'LAN': 0.70, 'DLPFC': 0.20, 'ACC': 0.10},
            CTMDomain.TEMPORAL: {'AUD': 0.60, 'MTL': 0.25, 'DLPFC': 0.15},
            CTMDomain.VALUE: {'OFC': 0.70, 'ACC': 0.20, 'DLPFC': 0.10}
        }

        # Start training in background thread
        training_id = str(uuid.uuid4())[:8]

        def _train_worker():
            try:
                print(f"[MultiCTMEnsemble] Starting {domain.value}CTM training (epochs={num_epochs})...")
                result = self._dream_trainer.train_domain_ctm(
                    domain=domain,
                    num_epochs=num_epochs,
                    target_module_routing=target_routing.get(domain, {})
                )

                if result and result.get('success'):
                    # Reload the trained CTM
                    print(f"[MultiCTMEnsemble] {domain.value}CTM training completed, reloading...")
                    self._reload_ctm(domain, checkpoint_dir)
                else:
                    print(f"[MultiCTMEnsemble] {domain.value}CTM training did not converge")
            except Exception as e:
                print(f"[MultiCTMEnsemble] Training error for {domain.value}CTM: {e}")

        training_thread = threading.Thread(target=_train_worker, daemon=True)
        training_thread.start()

        return training_id

    def _reload_ctm(self, domain: CTMDomain, checkpoint_dir: str):
        """
        Reload a CTM after training completes.

        Args:
            domain: CTM domain to reload
            checkpoint_dir: Directory with checkpoints
        """
        weight_paths = {
            CTMDomain.LOGIC: f"{checkpoint_dir}/logic_brain_epoch_24.pth",
            CTMDomain.TEMPORAL: f"{checkpoint_dir}/temporal_brain_epoch_46.pth",
            CTMDomain.VALUE: f"{checkpoint_dir}/value_brain_epoch_30.pth"
        }

        path = weight_paths.get(domain)
        if not path:
            return

        # Create CTM if not exists
        if self.ctms.get(domain) is None:
            self.ctms[domain] = KlotskiCTMAsyncReasoner(
                max_concurrent_tasks=2,
                consciousness_threshold=0.85,
                max_reasoning_steps=20
            )

        # Load weights
        if self.ctms[domain].load_weights(path):
            print(f"[MultiCTMEnsemble] {domain.value}CTM reloaded successfully")
            # Update supervisor metrics
            self.supervisor.update_metrics(
                domain.value,
                consciousness=0.8,
                response_time=5.0,
                success=True
            )

    def get_training_status(self) -> Dict[str, str]:
        """
        Get training status for all CTM domains.

        Returns:
            Dict mapping domain name to status (trained/pending/training)
        """
        status = {}
        for domain in CTMDomain:
            if domain == CTMDomain.SPATIAL:
                status[domain.value] = "trained"
            elif self.ctms.get(domain) is not None:
                status[domain.value] = "trained"
            elif hasattr(self, '_dream_trainer') and self._dream_trainer.is_training(domain):
                status[domain.value] = "training"
            else:
                status[domain.value] = "pending"
        return status


if __name__ == "__main__":
    # Test Multi-CTM Ensemble
    print("="*70)
    print("Testing Multi-CTM Ensemble")
    print("="*70)

    ensemble = MultiCTMEnsemble(
        max_concurrent_per_ctm=2,
        consciousness_threshold=0.85,
        max_reasoning_steps=20,
        enable_logic_ctm=True,      # Trained ~77% convergence
        enable_temporal_ctm=True,   # Trained ~77% convergence
        enable_value_ctm=True       # Trained ~78% convergence
    )

    # Test tasks across domains
    test_tasks = [
        ("Design microservice architecture with service mesh", None),
        ("Validate Kubernetes manifest against security policies", None),
        ("Detect anomalies in time-series metrics", None),
        ("Optimize resource allocation with cost trade-offs", None),
    ]

    task_ids = []

    for task, hint in test_tasks:
        print(f"\n{'='*70}")
        print(f"Submitting: {task}")
        print('='*70)

        brain_state = {
            'modality_activations': {
                'tool_trace': 0.8,
                'temporal_pattern': 0.6,
                'error_signal': 0.3
            }
        }

        ensemble_task_id = ensemble.reason_async(
            task=task,
            brain_state=brain_state,
            max_steps=15,
            domain_hint=hint
        )

        task_ids.append(ensemble_task_id)
        time.sleep(0.5)  # Stagger submissions

    # Wait for results
    print("\n" + "="*70)
    print("Waiting for ensemble results...")
    print("="*70)

    for task_id in task_ids:
        result = ensemble.get_result(task_id, wait=True, timeout=25)

        if result:
            print(f"\n[Ensemble Task {task_id}]")
            print(f"Task: {result.task[:60]}...")
            print(f"Primary Domain: {result.primary_domain.value}")
            if result.secondary_domains:
                print(f"Secondary Domains: {[d.value for d in result.secondary_domains]}")
            print(f"Elapsed: {result.elapsed_time:.1f}s")

            # Show CTM results
            for domain, ctm_result in result.ctm_results.items():
                if ctm_result:
                    print(f"\n  [{domain.value}CTM Result]")
                    if ctm_result.status == ReasoningStatus.COMPLETED and ctm_result.ctm_insight:
                        insight = ctm_result.ctm_insight
                        print(f"    Consciousness: {insight.final_consciousness:.3f}")
                        print(f"    Converged: {insight.converged}")
                        print(f"    Strategy: {insight.suggested_strategy}")
                        print(f"    Confidence: {insight.confidence:.0%}")
                    else:
                        print(f"    Status: {ctm_result.status.value}")

            if result.aggregated_insights:
                print(f"\n  [Aggregated Insights]")
                print(f"    {result.aggregated_insights}")

    # Show stats
    print("\n" + "="*70)
    print("Ensemble Statistics")
    print("="*70)
    stats = ensemble.get_stats()
    print(f"Total tasks: {stats['total_ensemble_tasks']}")
    print(f"Tasks by domain: {stats['tasks_by_domain']}")
    print(f"Active CTMs: {stats['active_ctms']}")

    print("\n" + "="*70)
    print("Multi-CTM Ensemble Test Complete!")
    print("="*70)

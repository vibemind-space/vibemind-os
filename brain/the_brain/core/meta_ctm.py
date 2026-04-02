"""
Meta-CTM Supervisor for Adaptive Cognitive System (ACS)

A higher-level controller that monitors and manages the Multi-CTM Ensemble:
- Performance monitoring across all CTMs
- Dynamic CTM selection based on task characteristics
- CTM reset/restart logic when performance degrades
- Load balancing between CTMs
- Learning from CTM successes/failures

The Meta-CTM acts as a "supervisor" that doesn't do reasoning itself,
but orchestrates which CTMs should reason and evaluates their outputs.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
import threading
from collections import deque
import statistics


class CTMHealth(Enum):
    """CTM health states"""
    HEALTHY = "healthy"           # Performing well
    DEGRADED = "degraded"         # Performance below threshold
    OVERLOADED = "overloaded"     # Too many concurrent tasks
    UNRESPONSIVE = "unresponsive" # Not responding
    RESET_PENDING = "reset_pending"  # Awaiting reset


@dataclass
class CTMPerformanceMetrics:
    """Performance metrics for a single CTM"""
    domain: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_consciousness: float = 0.0
    avg_response_time: float = 0.0  # seconds
    recent_consciousnesses: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_response_times: deque = field(default_factory=lambda: deque(maxlen=20))
    last_task_time: Optional[datetime] = None
    consecutive_failures: int = 0
    health: CTMHealth = CTMHealth.HEALTHY

    def record_task(self, consciousness: float, response_time: float, success: bool):
        """Record a task result"""
        self.total_tasks += 1
        self.last_task_time = datetime.now()
        self.recent_consciousnesses.append(consciousness)
        self.recent_response_times.append(response_time)

        if success:
            self.successful_tasks += 1
            self.consecutive_failures = 0
        else:
            self.failed_tasks += 1
            self.consecutive_failures += 1

        # Update averages
        if len(self.recent_consciousnesses) > 0:
            self.avg_consciousness = statistics.mean(self.recent_consciousnesses)
        if len(self.recent_response_times) > 0:
            self.avg_response_time = statistics.mean(self.recent_response_times)

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks

    def update_health(
        self,
        consciousness_threshold: float = 0.7,
        max_consecutive_failures: int = 3,
        max_response_time: float = 30.0
    ):
        """Update health status based on metrics"""
        if self.consecutive_failures >= max_consecutive_failures:
            self.health = CTMHealth.DEGRADED
        elif self.avg_consciousness < consciousness_threshold:
            self.health = CTMHealth.DEGRADED
        elif self.avg_response_time > max_response_time:
            self.health = CTMHealth.OVERLOADED
        else:
            self.health = CTMHealth.HEALTHY


@dataclass
class MetaCTMDecision:
    """Decision made by Meta-CTM"""
    selected_ctm: str
    confidence: float
    reasoning: str
    alternatives: List[str]
    should_parallelize: bool = False


class MetaCTMSupervisor:
    """
    Meta-level CTM supervisor that orchestrates the Multi-CTM Ensemble

    Responsibilities:
    1. Monitor CTM performance metrics
    2. Select optimal CTM for tasks
    3. Detect and handle CTM failures
    4. Reset underperforming CTMs
    5. Balance load across CTMs
    6. Learn from outcomes
    """

    def __init__(
        self,
        consciousness_threshold: float = 0.7,
        max_consecutive_failures: int = 3,
        reset_cooldown: float = 60.0,  # seconds
        enable_auto_reset: bool = True,
        enable_load_balancing: bool = True
    ):
        """
        Initialize Meta-CTM Supervisor

        Args:
            consciousness_threshold: Minimum acceptable consciousness
            max_consecutive_failures: Failures before marking unhealthy
            reset_cooldown: Minimum time between resets
            enable_auto_reset: Auto-reset underperforming CTMs
            enable_load_balancing: Balance load across CTMs
        """
        self.consciousness_threshold = consciousness_threshold
        self.max_consecutive_failures = max_consecutive_failures
        self.reset_cooldown = reset_cooldown
        self.enable_auto_reset = enable_auto_reset
        self.enable_load_balancing = enable_load_balancing

        # CTM performance tracking
        self.ctm_metrics: Dict[str, CTMPerformanceMetrics] = {
            'spatial': CTMPerformanceMetrics(domain='spatial'),
            'logic': CTMPerformanceMetrics(domain='logic'),
            'temporal': CTMPerformanceMetrics(domain='temporal'),
            'value': CTMPerformanceMetrics(domain='value')
        }

        # Task history for learning
        self.task_history: deque = deque(maxlen=100)

        # Reset tracking
        self.last_reset_time: Dict[str, datetime] = {}

        # Current task assignments
        self.active_tasks: Dict[str, str] = {}  # task_id -> ctm_domain

        # Lock for thread safety
        self._lock = threading.Lock()

        # Domain-task type affinities (learned over time)
        self.domain_affinities: Dict[str, Dict[str, float]] = {
            'spatial': {'architecture': 0.9, 'infrastructure': 0.85, 'deployment': 0.8, 'topology': 0.9},
            'logic': {'validation': 0.9, 'security': 0.85, 'compliance': 0.8, 'rules': 0.9},
            'temporal': {'scheduling': 0.9, 'patterns': 0.85, 'timeseries': 0.8, 'anomaly': 0.85},
            'value': {'optimization': 0.9, 'tradeoff': 0.85, 'cost': 0.8, 'decision': 0.9}
        }

    def select_ctm(
        self,
        task: str,
        domain_hint: Optional[str] = None,
        require_healthy: bool = True
    ) -> MetaCTMDecision:
        """
        Select the optimal CTM for a task

        Args:
            task: Task description
            domain_hint: Optional domain hint from domain router
            require_healthy: Only select healthy CTMs

        Returns:
            MetaCTMDecision with selected CTM and reasoning
        """
        with self._lock:
            task_lower = task.lower()

            # Calculate scores for each CTM
            scores: Dict[str, float] = {}

            for domain, metrics in self.ctm_metrics.items():
                # Skip unhealthy CTMs if required
                if require_healthy and metrics.health != CTMHealth.HEALTHY:
                    scores[domain] = 0.0
                    continue

                # Base score from domain hint
                if domain_hint and domain_hint == domain:
                    base_score = 0.8
                else:
                    base_score = 0.3

                # Add affinity score from keywords
                affinity_score = 0.0
                for keyword, weight in self.domain_affinities.get(domain, {}).items():
                    if keyword in task_lower:
                        affinity_score = max(affinity_score, weight)

                # Add performance bonus
                performance_score = metrics.success_rate * 0.3 + metrics.avg_consciousness * 0.2

                # Calculate total score
                scores[domain] = base_score + affinity_score * 0.3 + performance_score

            # Select best CTM
            if not scores or max(scores.values()) == 0:
                # Fallback to spatial
                selected = 'spatial'
                confidence = 0.5
                reasoning = "Fallback to SpatialCTM (no healthy alternatives)"
            else:
                selected = max(scores, key=scores.get)
                confidence = scores[selected]
                reasoning = f"Selected {selected}CTM based on domain match and performance"

            # Determine alternatives
            alternatives = sorted(
                [d for d, s in scores.items() if d != selected and s > 0],
                key=lambda d: scores[d],
                reverse=True
            )

            # Check if parallelization would help
            should_parallelize = len([s for s in scores.values() if s > 0.5]) > 1

            return MetaCTMDecision(
                selected_ctm=selected,
                confidence=confidence,
                reasoning=reasoning,
                alternatives=alternatives[:2],
                should_parallelize=should_parallelize
            )

    def record_task_result(
        self,
        task_id: str,
        domain: str,
        consciousness: float,
        response_time: float,
        success: bool,
        task_description: str = ""
    ):
        """
        Record the result of a CTM task

        Args:
            task_id: Task identifier
            domain: CTM domain that processed the task
            consciousness: Final consciousness level
            response_time: Time taken (seconds)
            success: Whether task succeeded
            task_description: Task description for learning
        """
        with self._lock:
            if domain in self.ctm_metrics:
                self.ctm_metrics[domain].record_task(consciousness, response_time, success)
                self.ctm_metrics[domain].update_health(
                    self.consciousness_threshold,
                    self.max_consecutive_failures
                )

                # Record in history for learning
                self.task_history.append({
                    'task_id': task_id,
                    'domain': domain,
                    'task': task_description,
                    'consciousness': consciousness,
                    'response_time': response_time,
                    'success': success,
                    'timestamp': datetime.now()
                })

                # Check if reset is needed
                if self.enable_auto_reset:
                    self._check_reset_needed(domain)

                # Update affinities based on success
                if success and task_description:
                    self._update_affinities(domain, task_description, consciousness)

    def _check_reset_needed(self, domain: str):
        """Check if a CTM needs to be reset"""
        metrics = self.ctm_metrics.get(domain)
        if not metrics:
            return

        if metrics.health in [CTMHealth.DEGRADED, CTMHealth.UNRESPONSIVE]:
            last_reset = self.last_reset_time.get(domain)
            if last_reset is None or (datetime.now() - last_reset).total_seconds() > self.reset_cooldown:
                metrics.health = CTMHealth.RESET_PENDING
                print(f"[MetaCTM] {domain}CTM marked for reset (consecutive failures: {metrics.consecutive_failures})")

    def _update_affinities(self, domain: str, task: str, consciousness: float):
        """Update domain-task affinities based on successful tasks"""
        task_lower = task.lower()

        # Extract keywords
        keywords = set()
        for existing_keywords in self.domain_affinities.values():
            keywords.update(existing_keywords.keys())

        for keyword in keywords:
            if keyword in task_lower:
                # Update affinity with exponential moving average
                current = self.domain_affinities.get(domain, {}).get(keyword, 0.5)
                new_affinity = current * 0.9 + consciousness * 0.1

                if domain not in self.domain_affinities:
                    self.domain_affinities[domain] = {}
                self.domain_affinities[domain][keyword] = new_affinity

    def reset_ctm(self, domain: str) -> bool:
        """
        Reset a CTM (clear its metrics and mark as healthy)

        Args:
            domain: CTM domain to reset

        Returns:
            True if reset successful
        """
        with self._lock:
            if domain not in self.ctm_metrics:
                return False

            # Reset metrics
            self.ctm_metrics[domain] = CTMPerformanceMetrics(domain=domain)
            self.last_reset_time[domain] = datetime.now()

            print(f"[MetaCTM] {domain}CTM reset complete")
            return True

    def get_ctm_to_reset(self) -> Optional[str]:
        """Get a CTM that needs resetting"""
        with self._lock:
            for domain, metrics in self.ctm_metrics.items():
                if metrics.health == CTMHealth.RESET_PENDING:
                    return domain
            return None

    def get_health_status(self) -> Dict[str, Dict]:
        """Get health status of all CTMs"""
        with self._lock:
            return {
                domain: {
                    'health': metrics.health.value,
                    'success_rate': metrics.success_rate,
                    'avg_consciousness': metrics.avg_consciousness,
                    'avg_response_time': metrics.avg_response_time,
                    'total_tasks': metrics.total_tasks,
                    'consecutive_failures': metrics.consecutive_failures
                }
                for domain, metrics in self.ctm_metrics.items()
            }

    def get_best_performing_ctm(self) -> str:
        """Get the best performing CTM"""
        with self._lock:
            best = max(
                self.ctm_metrics.items(),
                key=lambda x: x[1].success_rate * x[1].avg_consciousness
            )
            return best[0]

    def get_statistics(self) -> Dict:
        """Get comprehensive statistics"""
        with self._lock:
            total_tasks = sum(m.total_tasks for m in self.ctm_metrics.values())
            total_success = sum(m.successful_tasks for m in self.ctm_metrics.values())

            return {
                'total_tasks': total_tasks,
                'total_success': total_success,
                'overall_success_rate': total_success / max(1, total_tasks),
                'ctm_health': {
                    domain: metrics.health.value
                    for domain, metrics in self.ctm_metrics.items()
                },
                'best_performing': self.get_best_performing_ctm(),
                'resets_pending': sum(
                    1 for m in self.ctm_metrics.values()
                    if m.health == CTMHealth.RESET_PENDING
                )
            }

    def get_routing_recommendation(self, task: str) -> Dict:
        """
        Get a complete routing recommendation for a task

        Args:
            task: Task description

        Returns:
            Routing recommendation with CTM selection and context
        """
        decision = self.select_ctm(task)
        health = self.get_health_status()

        return {
            'selected_ctm': decision.selected_ctm,
            'confidence': decision.confidence,
            'reasoning': decision.reasoning,
            'alternatives': decision.alternatives,
            'should_parallelize': decision.should_parallelize,
            'ctm_health': health,
            'statistics': self.get_statistics()
        }


if __name__ == "__main__":
    # Test Meta-CTM Supervisor
    print("="*70)
    print("Meta-CTM Supervisor Test")
    print("="*70)

    supervisor = MetaCTMSupervisor()

    # Test task selection
    tasks = [
        ("Design microservice architecture with API gateway", "spatial"),
        ("Validate security policies and compliance rules", "logic"),
        ("Detect anomalies in time-series metrics", "temporal"),
        ("Optimize cost vs performance tradeoffs", "value"),
        ("Deploy Docker container cluster", None),
    ]

    print("\nTask Selection:")
    for task, hint in tasks:
        decision = supervisor.select_ctm(task, domain_hint=hint)
        print(f"  Task: {task[:50]}...")
        print(f"    Selected: {decision.selected_ctm}CTM (confidence: {decision.confidence:.2f})")
        print(f"    Reasoning: {decision.reasoning}")
        print()

    # Simulate task results
    print("Recording task results...")
    supervisor.record_task_result("task1", "spatial", 0.92, 1.5, True, "Design microservice architecture")
    supervisor.record_task_result("task2", "spatial", 0.88, 1.2, True, "Deploy container")
    supervisor.record_task_result("task3", "logic", 0.65, 2.0, False, "Validate config")
    supervisor.record_task_result("task4", "logic", 0.55, 2.5, False, "Check security")
    supervisor.record_task_result("task5", "logic", 0.50, 3.0, False, "Verify compliance")

    # Check health
    print("\nCTM Health Status:")
    health = supervisor.get_health_status()
    for domain, status in health.items():
        print(f"  {domain}CTM: {status['health']} (success: {status['success_rate']:.1%}, consciousness: {status['avg_consciousness']:.2f})")

    # Check if any need reset
    to_reset = supervisor.get_ctm_to_reset()
    if to_reset:
        print(f"\nCTM needing reset: {to_reset}")

    # Get statistics
    print("\nStatistics:")
    stats = supervisor.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "="*70)
    print("Meta-CTM Supervisor Test Complete!")
    print("="*70)

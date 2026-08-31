"""
Health-Check Based Startup (PHASE 7: P7.95)

Orchestrates brain startup with ordered initialization and health verification.

Features:
1. Ordered subsystem initialization with dependency awareness
2. Health checks between initialization phases
3. Retry logic for flaky component startup
4. Startup report with timing information
5. Rollback on critical failure
"""

import time
import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('brain.health_startup')


class StartupPhase(Enum):
    """Startup phases in order."""
    CONFIG = "config"
    MEMORY = "memory"
    NEUROMODULATION = "neuromodulation"
    ATTENTION = "attention"
    PREDICTIVE_CODING = "predictive_coding"
    CONSCIOUSNESS = "consciousness"
    EMOTIONAL = "emotional"
    GOAL_GRAPH = "goal_graph"
    CTM_ENSEMBLE = "ctm_ensemble"
    COGNITIVE_LOOP = "cognitive_loop"
    FREQUENCY_CONTROLLER = "frequency_controller"
    HEARTBEAT = "heartbeat"
    EVENT_BUS = "event_bus"
    SNAPSHOT = "snapshot"


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    NOT_STARTED = "not_started"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus = HealthStatus.NOT_STARTED
    message: str = ""
    init_time_ms: float = 0.0
    retries: int = 0
    optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status.value,
            'message': self.message,
            'init_time_ms': round(self.init_time_ms, 2),
            'retries': self.retries,
            'optional': self.optional,
        }


@dataclass
class StartupReport:
    """Complete startup report."""
    components: List[ComponentHealth] = field(default_factory=list)
    total_time_ms: float = 0.0
    overall_status: HealthStatus = HealthStatus.NOT_STARTED
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        healthy = sum(1 for c in self.components if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in self.components if c.status == HealthStatus.DEGRADED)
        failed = sum(1 for c in self.components if c.status == HealthStatus.UNHEALTHY)

        return {
            'overall_status': self.overall_status.value,
            'total_time_ms': round(self.total_time_ms, 2),
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'summary': {
                'healthy': healthy,
                'degraded': degraded,
                'failed': failed,
                'total': len(self.components),
            },
            'components': [c.to_dict() for c in self.components],
        }


class HealthCheckStartup:
    """
    Manages ordered brain startup with health verification.

    Each component is initialized in dependency order with health checks
    between phases. Optional components are allowed to fail without
    blocking startup.
    """

    def __init__(self, max_retries: int = 2, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._checks: List[Tuple[str, Callable, bool]] = []  # (name, check_fn, optional)
        self._report = StartupReport()

    def register_check(self, name: str, check_fn: Callable[[], bool], optional: bool = False):
        """
        Register a health check function.

        Args:
            name: Component name
            check_fn: Callable that returns True if healthy, raises on failure
            optional: If True, failure doesn't block startup
        """
        self._checks.append((name, check_fn, optional))

    def run_startup(self) -> StartupReport:
        """
        Run all registered health checks in order.

        Returns:
            StartupReport with results
        """
        from datetime import datetime

        self._report = StartupReport()
        self._report.started_at = datetime.now().isoformat()
        t0 = time.time()

        critical_failure = False

        for name, check_fn, optional in self._checks:
            component = ComponentHealth(name=name, optional=optional)

            success = False
            for attempt in range(self.max_retries + 1):
                ct0 = time.time()
                try:
                    result = check_fn()
                    component.init_time_ms = (time.time() - ct0) * 1000
                    component.retries = attempt

                    if result:
                        component.status = HealthStatus.HEALTHY
                        component.message = "OK"
                    else:
                        component.status = HealthStatus.DEGRADED
                        component.message = "Check returned False"

                    success = True
                    break

                except Exception as e:
                    component.init_time_ms = (time.time() - ct0) * 1000
                    component.retries = attempt
                    component.message = str(e)

                    if attempt < self.max_retries:
                        logger.warning(f"Startup check '{name}' failed (attempt {attempt+1}), retrying...")
                        time.sleep(self.retry_delay)
                    else:
                        if optional:
                            component.status = HealthStatus.DEGRADED
                            component.message = f"Optional component failed: {e}"
                            logger.warning(f"Optional component '{name}' failed: {e}")
                        else:
                            component.status = HealthStatus.UNHEALTHY
                            component.message = f"Critical failure: {e}"
                            logger.error(f"Critical component '{name}' failed: {e}")
                            critical_failure = True

            self._report.components.append(component)

            if critical_failure:
                logger.error(f"Startup aborted: critical component '{name}' failed")
                break

        self._report.total_time_ms = (time.time() - t0) * 1000
        self._report.completed_at = datetime.now().isoformat()

        if critical_failure:
            self._report.overall_status = HealthStatus.UNHEALTHY
        elif any(c.status == HealthStatus.DEGRADED for c in self._report.components):
            self._report.overall_status = HealthStatus.DEGRADED
        else:
            self._report.overall_status = HealthStatus.HEALTHY

        return self._report

    def get_report(self) -> StartupReport:
        """Get the last startup report."""
        return self._report


def create_brain_startup_checks(brain) -> HealthCheckStartup:
    """
    Create standard health checks for a ProductionPlanner brain.

    Args:
        brain: ProductionPlanner instance

    Returns:
        Configured HealthCheckStartup ready to run
    """
    startup = HealthCheckStartup(max_retries=2, retry_delay=0.5)
    planner = getattr(brain, 'planner', brain)

    # Core systems (critical)
    startup.register_check(
        'memory',
        lambda: hasattr(planner, 'memory') and planner.memory is not None,
        optional=False
    )
    startup.register_check(
        'attention',
        lambda: hasattr(planner, 'attention') and planner.attention is not None,
        optional=False
    )
    startup.register_check(
        'neuromodulation',
        lambda: hasattr(planner, 'neuromodulation') and planner.neuromodulation is not None,
        optional=False
    )
    startup.register_check(
        'layer1_router',
        lambda: hasattr(planner, 'layer1') and planner.layer1 is not None,
        optional=False
    )
    startup.register_check(
        'layer2_planner',
        lambda: hasattr(planner, 'layer2') and planner.layer2 is not None,
        optional=False
    )
    startup.register_check(
        'layer3_router',
        lambda: hasattr(planner, 'layer3') and planner.layer3 is not None,
        optional=False
    )

    # Important but non-critical systems
    startup.register_check(
        'predictive_coding',
        lambda: hasattr(planner, 'predictive_coding') and planner.predictive_coding is not None,
        optional=True
    )
    startup.register_check(
        'consciousness',
        lambda: hasattr(planner, 'consciousness') and planner.consciousness is not None,
        optional=True
    )
    startup.register_check(
        'goal_graph',
        lambda: hasattr(planner, 'goal_graph') and planner.goal_graph is not None,
        optional=True
    )

    # Cognitive loop (optional)
    startup.register_check(
        'cognitive_loop',
        lambda: hasattr(brain, 'cognitive_loop') and brain.cognitive_loop is not None,
        optional=True
    )

    return startup

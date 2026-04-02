"""
Subsystem Registry: Centralized tracking of brain subsystem lifecycle.

Provides:
- SubsystemRegistry: Central registry for all optional brain subsystems
- CircuitBreaker: Auto-disable subsystems after repeated failures
- SubsystemHealth: Per-subsystem health reporting
- Dependency graph: Documents which subsystems depend on which others

Replaces scattered hasattr() checks with a single source of truth.

Usage:
    from core.subsystem_registry import SubsystemRegistry, SubsystemStatus

    registry = SubsystemRegistry()
    registry.register('memory', memory_manager, depends_on=['layer1'])
    registry.register('attention', attention_mechanism, depends_on=['memory'])

    # Safe access (replaces hasattr + getattr)
    mem = registry.get('memory')  # Returns instance or None
    if registry.is_active('memory'):
        mem.get_context(...)

    # Health reporting
    health = registry.get_health_report()

    # Circuit breaker: auto-trips after N failures
    registry.record_failure('ctm_ensemble', error)
    # After 3 failures -> subsystem marked CIRCUIT_OPEN
"""

import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime


class SubsystemStatus(Enum):
    """Lifecycle status of a subsystem."""
    REGISTERED = "registered"       # Known but not yet initialized
    ACTIVE = "active"               # Fully operational
    DEGRADED = "degraded"           # Operational with reduced functionality
    CIRCUIT_OPEN = "circuit_open"   # Auto-disabled due to repeated failures
    DISABLED = "disabled"           # Manually disabled
    FAILED = "failed"               # Failed to initialize


class HealthLevel(Enum):
    """Health level for subsystem and aggregate health reporting."""
    GREEN = "green"     # Fully healthy
    YELLOW = "yellow"   # Operational but degraded
    RED = "red"         # Failing or circuit-open
    OFFLINE = "offline" # Not available


@dataclass
class CircuitBreakerState:
    """Tracks circuit breaker state for a subsystem."""
    failure_count: int = 0
    failure_threshold: int = 3
    last_failure_time: Optional[float] = None
    last_failure_error: Optional[str] = None
    reset_timeout_seconds: float = 60.0
    is_open: bool = False

    def record_failure(self, error: Exception) -> bool:
        """Record a failure. Returns True if circuit just opened."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.last_failure_error = str(error)[:200]
        if self.failure_count >= self.failure_threshold and not self.is_open:
            self.is_open = True
            return True
        return False

    def should_attempt(self) -> bool:
        """Check if we should attempt to use this subsystem (half-open check)."""
        if not self.is_open:
            return True
        # Allow retry after reset_timeout_seconds (half-open state)
        if self.last_failure_time and \
           (time.time() - self.last_failure_time) > self.reset_timeout_seconds:
            return True
        return False

    def record_success(self):
        """Record a success, potentially closing the circuit."""
        if self.is_open:
            self.is_open = False
        self.failure_count = 0
        self.last_failure_error = None

    def to_dict(self) -> Dict:
        return {
            'failure_count': self.failure_count,
            'failure_threshold': self.failure_threshold,
            'is_open': self.is_open,
            'last_failure_error': self.last_failure_error,
            'last_failure_time': datetime.fromtimestamp(self.last_failure_time).isoformat()
                if self.last_failure_time else None,
            'reset_timeout_seconds': self.reset_timeout_seconds,
        }


@dataclass
class SubsystemInfo:
    """Metadata about a registered subsystem."""
    name: str
    instance: Any
    status: SubsystemStatus = SubsystemStatus.ACTIVE
    depends_on: List[str] = field(default_factory=list)
    category: str = "core"  # core, cognitive, monitoring, optional
    description: str = ""
    registered_at: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    use_count: int = 0
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)
    error_log: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'status': self.status.value,
            'category': self.category,
            'description': self.description,
            'depends_on': self.depends_on,
            'use_count': self.use_count,
            'last_used': datetime.fromtimestamp(self.last_used).isoformat()
                if self.last_used else None,
            'circuit_breaker': self.circuit_breaker.to_dict(),
            'recent_errors': self.error_log[-5:] if self.error_log else [],
        }


# ---------------------------------------------------------------------------
# Dependency Graph: Documents which subsystems need which others
# ---------------------------------------------------------------------------

# Default dependency graph for the brain's subsystems
DEFAULT_DEPENDENCY_GRAPH = {
    # Layer 1 - no dependencies (foundational)
    'layer1': {
        'depends_on': [],
        'category': 'core',
        'description': 'TaskFeatureRouter: extracts 10-modality feature vectors from task text',
    },
    # Layer 2 - depends on Layer 1
    'layer2': {
        'depends_on': ['layer1'],
        'category': 'core',
        'description': 'ConversationPathPlanner: plans conversation strategy from routing state',
    },
    # Layer 3 - depends on Layer 2
    'layer3': {
        'depends_on': ['layer2'],
        'category': 'core',
        'description': 'DecisionRouter: makes final execute/suggest/clarify decision',
    },
    # Memory - independent (enhances routing but not required)
    'memory': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'MemoryManager: working + episodic memory with similarity search',
    },
    # Attention - enhances routing (optional)
    'attention': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'AttentionMechanism: computes attention weights over modalities',
    },
    # Neuromodulation - independent
    'neuromodulation': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'NeuromodulationSystem: dopamine/serotonin/NE dynamics for exploration-exploitation',
    },
    # Predictive Coding - enhances routing
    'predictive_coding': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'HierarchicalPredictiveCoding: prediction errors + curiosity signals',
    },
    # Active Inference - uses predictive coding
    'active_inference': {
        'depends_on': ['predictive_coding'],
        'category': 'cognitive',
        'description': 'ActiveInference: active inference for adaptive behavior',
    },
    # Consciousness Metrics - monitors reasoning quality
    'consciousness': {
        'depends_on': [],
        'category': 'monitoring',
        'description': 'ConsciousnessMetrics: tracks awareness, confidence, known unknowns',
    },
    # Meta-Learner - adapts learning rates
    'meta_learner': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'MetaLearner: adapts learning parameters based on performance',
    },
    # Emotional System - task appraisal
    'emotional': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'EmotionalSystem: appraises tasks for emotional valence/arousal',
    },
    # Homeostatic Regulation - energy/fatigue management
    'homeostatic': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'HomeostaticRegulation: manages energy, fatigue, stress, sleep pressure',
    },
    # Goal Graph - tracks hierarchical goals
    'goal_graph': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'GoalGraph: hierarchical goal management with critical path analysis',
    },
    # CTM Ensemble - advanced reasoning
    'ctm_ensemble': {
        'depends_on': ['layer1'],
        'category': 'cognitive',
        'description': 'MultiCTMEnsemble: multi-domain conscious reasoning (Spatial/Logic/Temporal/Value)',
    },
    # Dream Mode - offline consolidation
    'dream_mode': {
        'depends_on': ['memory'],
        'category': 'optional',
        'description': 'DreamMode: offline memory consolidation and pattern replay',
    },
    # Temporal Memory - event sequences
    'temporal_memory': {
        'depends_on': [],
        'category': 'cognitive',
        'description': 'TemporalMemory: tracks event sequences and temporal patterns',
    },
    # Sensory Preprocessor - text feature extraction
    'sensory': {
        'depends_on': [],
        'category': 'optional',
        'description': 'SensoryPreprocessor: extracts multi-channel features from text',
    },
    # Layer 4 - temporal routing
    'layer4': {
        'depends_on': ['layer3'],
        'category': 'core',
        'description': 'Layer4TemporalRouter: temporal context + security checks on decisions',
    },
    # Brain Activity Monitor
    'brain_monitor': {
        'depends_on': [],
        'category': 'monitoring',
        'description': 'BrainActivityMonitor: tracks gate history, activations, and anomalies',
    },
    # Brain Heartbeat
    'heartbeat': {
        'depends_on': [],
        'category': 'monitoring',
        'description': 'BrainHeartbeat: periodic tick for idle detection, dream triggers, health',
    },
    # Cognitive Loop (wraps everything)
    'cognitive_loop': {
        'depends_on': ['layer1', 'layer2', 'layer3', 'memory', 'attention', 'neuromodulation'],
        'category': 'core',
        'description': 'CognitiveLoop: 9-phase perceive→reason→reflect cycle integrating all subsystems',
    },
    # Frequency Controller
    'frequency_controller': {
        'depends_on': [],
        'category': 'monitoring',
        'description': 'BrainFrequencyController: manages delta/theta/alpha/beta/gamma brain modes',
    },
    # Sleep Consolidation
    'sleep_consolidation': {
        'depends_on': ['memory', 'dream_mode'],
        'category': 'optional',
        'description': 'SleepConsolidation: consolidates memories during low-activity periods',
    },
}


class SubsystemRegistry:
    """
    Centralized registry for brain subsystems.

    Replaces scattered hasattr() checks with a single source of truth.
    Provides circuit breaker, health reporting, and dependency tracking.
    """

    def __init__(self, circuit_breaker_threshold: int = 3,
                 circuit_breaker_reset_seconds: float = 60.0):
        self._subsystems: Dict[str, SubsystemInfo] = {}
        self._lock = threading.RLock()
        self._cb_threshold = circuit_breaker_threshold
        self._cb_reset = circuit_breaker_reset_seconds
        self._creation_time = time.time()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, instance: Any,
                 depends_on: Optional[List[str]] = None,
                 category: str = "core",
                 description: str = "") -> None:
        """Register a subsystem instance."""
        with self._lock:
            # Use default dependency graph info if available
            defaults = DEFAULT_DEPENDENCY_GRAPH.get(name, {})
            deps = depends_on if depends_on is not None else defaults.get('depends_on', [])
            cat = category if category != "core" else defaults.get('category', category)
            desc = description or defaults.get('description', '')

            cb = CircuitBreakerState(
                failure_threshold=self._cb_threshold,
                reset_timeout_seconds=self._cb_reset,
            )

            info = SubsystemInfo(
                name=name,
                instance=instance,
                status=SubsystemStatus.ACTIVE,
                depends_on=deps,
                category=cat,
                description=desc,
                circuit_breaker=cb,
            )
            self._subsystems[name] = info

    def unregister(self, name: str) -> None:
        """Remove a subsystem from the registry."""
        with self._lock:
            self._subsystems.pop(name, None)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def is_active(self, name: str) -> bool:
        """Check if a subsystem is active (registered and not disabled/failed/circuit-open)."""
        with self._lock:
            info = self._subsystems.get(name)
            if info is None:
                return False
            if info.status in (SubsystemStatus.ACTIVE, SubsystemStatus.DEGRADED):
                return True
            if info.status == SubsystemStatus.CIRCUIT_OPEN:
                return info.circuit_breaker.should_attempt()
            return False

    def is_registered(self, name: str) -> bool:
        """Check if a subsystem is registered (regardless of status)."""
        return name in self._subsystems

    def get_all(self, category: Optional[str] = None) -> Dict[str, Any]:
        """Get all active subsystem instances, optionally filtered by category."""
        with self._lock:
            result = {}
            for name, info in self._subsystems.items():
                if category and info.category != category:
                    continue
                if info.status in (SubsystemStatus.ACTIVE, SubsystemStatus.DEGRADED):
                    result[name] = info.instance
            return result

    def list_names(self, category: Optional[str] = None,
                   status: Optional[SubsystemStatus] = None) -> List[str]:
        """List registered subsystem names, optionally filtered."""
        with self._lock:
            result = []
            for name, info in self._subsystems.items():
                if category and info.category != category:
                    continue
                if status and info.status != status:
                    continue
                result.append(name)
            return result

    # ------------------------------------------------------------------
    # Status Management
    # ------------------------------------------------------------------

    def set_status(self, name: str, status: SubsystemStatus) -> None:
        """Manually set subsystem status."""
        with self._lock:
            if name in self._subsystems:
                self._subsystems[name].status = status

    def disable(self, name: str) -> None:
        """Manually disable a subsystem."""
        self.set_status(name, SubsystemStatus.DISABLED)

    def enable(self, name: str) -> None:
        """Re-enable a subsystem."""
        with self._lock:
            if name in self._subsystems:
                self._subsystems[name].status = SubsystemStatus.ACTIVE
                self._subsystems[name].circuit_breaker.record_success()

    # ------------------------------------------------------------------
    # Circuit Breaker
    # ------------------------------------------------------------------

    def record_failure(self, name: str, error: Exception) -> bool:
        """
        Record a subsystem failure. Returns True if circuit just opened.

        Usage:
            try:
                result = subsystem.do_something()
                registry.record_success(name)
            except Exception as e:
                registry.record_failure(name, e)
        """
        with self._lock:
            info = self._subsystems.get(name)
            if info is None:
                return False

            # Log the error
            error_record = {
                'timestamp': datetime.now().isoformat(),
                'error': str(error)[:200],
                'error_type': type(error).__name__,
            }
            info.error_log.append(error_record)
            # Keep only last 20 errors
            if len(info.error_log) > 20:
                info.error_log = info.error_log[-20:]

            just_opened = info.circuit_breaker.record_failure(error)
            if just_opened:
                info.status = SubsystemStatus.CIRCUIT_OPEN
            return just_opened

    def record_success(self, name: str) -> None:
        """Record a subsystem success (closes circuit if open)."""
        with self._lock:
            info = self._subsystems.get(name)
            if info is None:
                return
            was_open = info.circuit_breaker.is_open
            info.circuit_breaker.record_success()
            if was_open:
                info.status = SubsystemStatus.ACTIVE

    # ------------------------------------------------------------------
    # Health Reporting (P4.54)
    # ------------------------------------------------------------------

    def get_subsystem_health(self, name: str) -> Dict:
        """Get detailed health for a single subsystem."""
        with self._lock:
            info = self._subsystems.get(name)
            if info is None:
                return {'name': name, 'health': HealthLevel.OFFLINE.value, 'reason': 'not registered'}

            health = HealthLevel.GREEN
            reason = 'operational'

            if info.status == SubsystemStatus.CIRCUIT_OPEN:
                health = HealthLevel.RED
                reason = f'circuit open after {info.circuit_breaker.failure_count} failures'
            elif info.status == SubsystemStatus.DISABLED:
                health = HealthLevel.OFFLINE
                reason = 'manually disabled'
            elif info.status == SubsystemStatus.FAILED:
                health = HealthLevel.RED
                reason = 'initialization failed'
            elif info.status == SubsystemStatus.DEGRADED:
                health = HealthLevel.YELLOW
                reason = 'degraded functionality'
            elif info.circuit_breaker.failure_count > 0:
                health = HealthLevel.YELLOW
                reason = f'{info.circuit_breaker.failure_count} recent failures'

            return {
                'name': name,
                'health': health.value,
                'status': info.status.value,
                'reason': reason,
                'category': info.category,
                'use_count': info.use_count,
                'last_used': datetime.fromtimestamp(info.last_used).isoformat()
                    if info.last_used else None,
                'circuit_breaker': info.circuit_breaker.to_dict(),
                'recent_errors': info.error_log[-3:] if info.error_log else [],
            }

    def get_health_report(self) -> Dict:
        """
        Get aggregate health report for all subsystems.

        Returns:
            {
                'overall_health': 'green'|'yellow'|'red',
                'total_subsystems': 12,
                'active': 10,
                'degraded': 1,
                'circuit_open': 1,
                'disabled': 0,
                'subsystems': { name: health_dict, ... },
                'dependency_issues': [...],
                'uptime_seconds': 3600.0,
            }
        """
        with self._lock:
            report = {
                'overall_health': HealthLevel.GREEN.value,
                'total_subsystems': len(self._subsystems),
                'active': 0,
                'degraded': 0,
                'circuit_open': 0,
                'disabled': 0,
                'failed': 0,
                'subsystems': {},
                'dependency_issues': [],
                'uptime_seconds': time.time() - self._creation_time,
            }

            worst_health = HealthLevel.GREEN

            for name, info in self._subsystems.items():
                sub_health = self.get_subsystem_health(name)
                report['subsystems'][name] = sub_health

                # Count by status
                if info.status == SubsystemStatus.ACTIVE:
                    report['active'] += 1
                elif info.status == SubsystemStatus.DEGRADED:
                    report['degraded'] += 1
                elif info.status == SubsystemStatus.CIRCUIT_OPEN:
                    report['circuit_open'] += 1
                elif info.status == SubsystemStatus.DISABLED:
                    report['disabled'] += 1
                elif info.status == SubsystemStatus.FAILED:
                    report['failed'] += 1

                # Track worst health
                level = HealthLevel(sub_health['health'])
                if level == HealthLevel.RED:
                    worst_health = HealthLevel.RED
                elif level == HealthLevel.YELLOW and worst_health == HealthLevel.GREEN:
                    worst_health = HealthLevel.YELLOW

            # Check dependency issues
            for name, info in self._subsystems.items():
                for dep in info.depends_on:
                    if dep not in self._subsystems:
                        report['dependency_issues'].append(
                            f'{name} depends on {dep} which is not registered')
                    elif self._subsystems[dep].status in (
                        SubsystemStatus.CIRCUIT_OPEN,
                        SubsystemStatus.FAILED,
                        SubsystemStatus.DISABLED,
                    ):
                        report['dependency_issues'].append(
                            f'{name} depends on {dep} which is {self._subsystems[dep].status.value}')
                        if worst_health != HealthLevel.RED:
                            worst_health = HealthLevel.YELLOW

            report['overall_health'] = worst_health.value
            return report

    # ------------------------------------------------------------------
    # Dependency Graph (P4.51)
    # ------------------------------------------------------------------

    def get_dependency_graph(self) -> Dict:
        """
        Get the dependency graph for all registered subsystems.

        Returns dict with adjacency lists and metadata.
        """
        with self._lock:
            graph = {}
            for name, info in self._subsystems.items():
                graph[name] = {
                    'depends_on': info.depends_on,
                    'depended_by': [],
                    'category': info.category,
                    'status': info.status.value,
                }

            # Compute reverse dependencies
            for name, info in self._subsystems.items():
                for dep in info.depends_on:
                    if dep in graph:
                        graph[dep]['depended_by'].append(name)

            return graph

    def get_initialization_order(self) -> List[str]:
        """
        Get topological sort of subsystems for safe initialization order.

        Returns list of subsystem names ordered so dependencies come first.
        """
        with self._lock:
            # Kahn's algorithm for topological sort
            in_degree: Dict[str, int] = {}
            adj: Dict[str, List[str]] = {}

            for name, info in self._subsystems.items():
                in_degree.setdefault(name, 0)
                adj.setdefault(name, [])
                for dep in info.depends_on:
                    if dep in self._subsystems:
                        in_degree[name] = in_degree.get(name, 0) + 1
                        adj.setdefault(dep, []).append(name)

            queue = [n for n, d in in_degree.items() if d == 0]
            result = []

            while queue:
                node = queue.pop(0)
                result.append(node)
                for neighbor in adj.get(node, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            # If result doesn't contain all nodes, there's a cycle
            remaining = set(self._subsystems.keys()) - set(result)
            if remaining:
                result.extend(sorted(remaining))  # Add cyclic nodes at end

            return result

    def check_dependencies(self, name: str) -> Tuple[bool, List[str]]:
        """
        Check if all dependencies of a subsystem are satisfied.

        Returns (all_satisfied, list_of_missing_or_inactive).
        """
        with self._lock:
            info = self._subsystems.get(name)
            if info is None:
                return False, [f'{name} is not registered']

            issues = []
            for dep in info.depends_on:
                if dep not in self._subsystems:
                    issues.append(f'{dep}: not registered')
                elif not self.is_active(dep):
                    issues.append(f'{dep}: {self._subsystems[dep].status.value}')

            return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Summary / Debug
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Get a human-readable summary of all subsystems."""
        with self._lock:
            lines = ["=== BRAIN SUBSYSTEM REGISTRY ===", ""]

            by_category: Dict[str, List[SubsystemInfo]] = {}
            for info in self._subsystems.values():
                by_category.setdefault(info.category, []).append(info)

            for cat in ['core', 'cognitive', 'monitoring', 'optional']:
                items = by_category.get(cat, [])
                if not items:
                    continue
                lines.append(f"[{cat.upper()}]")
                for info in sorted(items, key=lambda x: x.name):
                    status_icon = {
                        SubsystemStatus.ACTIVE: '✅',
                        SubsystemStatus.DEGRADED: '🟡',
                        SubsystemStatus.CIRCUIT_OPEN: '🔴',
                        SubsystemStatus.DISABLED: '⏹️',
                        SubsystemStatus.FAILED: '❌',
                        SubsystemStatus.REGISTERED: '📋',
                    }.get(info.status, '?')
                    cb_info = ""
                    if info.circuit_breaker.failure_count > 0:
                        cb_info = f" (failures: {info.circuit_breaker.failure_count})"
                    lines.append(f"  {status_icon} {info.name}: {info.status.value}{cb_info}")
                lines.append("")

            report = self.get_health_report()
            lines.append(f"Overall Health: {report['overall_health'].upper()}")
            lines.append(f"Active: {report['active']}/{report['total_subsystems']}")
            if report['dependency_issues']:
                lines.append(f"Dependency Issues: {len(report['dependency_issues'])}")
                for issue in report['dependency_issues']:
                    lines.append(f"  ⚠️ {issue}")

            return "\n".join(lines)

    # ------------------------------------------------------------------
    # Lazy Initialization (P4.59)
    # ------------------------------------------------------------------

    def register_lazy(self, name: str, factory: callable,
                      depends_on: Optional[List[str]] = None,
                      category: str = "core",
                      description: str = "") -> None:
        """
        Register a subsystem factory for lazy initialization.

        The factory will be called on first `get()` access. Until then,
        the subsystem is in REGISTERED status.

        Args:
            name: Subsystem name
            factory: Callable that returns the subsystem instance
            depends_on: List of dependency names
            category: Subsystem category
            description: Human-readable description
        """
        with self._lock:
            defaults = DEFAULT_DEPENDENCY_GRAPH.get(name, {})
            deps = depends_on if depends_on is not None else defaults.get('depends_on', [])
            cat = category if category != "core" else defaults.get('category', category)
            desc = description or defaults.get('description', '')

            cb = CircuitBreakerState(
                failure_threshold=self._cb_threshold,
                reset_timeout_seconds=self._cb_reset,
            )

            info = SubsystemInfo(
                name=name,
                instance=None,  # Will be populated on first access
                status=SubsystemStatus.REGISTERED,
                depends_on=deps,
                category=cat,
                description=desc,
                circuit_breaker=cb,
            )
            # Store factory as a private attribute on the info object
            info._factory = factory  # type: ignore
            self._subsystems[name] = info

    def _lazy_init(self, name: str) -> Any:
        """Initialize a lazy-registered subsystem on first access."""
        info = self._subsystems.get(name)
        if info is None:
            return None
        factory = getattr(info, '_factory', None)
        if factory is None:
            return info.instance
        try:
            info.instance = factory()
            info.status = SubsystemStatus.ACTIVE
            info._factory = None  # type: ignore  # Clear factory after init
            return info.instance
        except Exception as e:
            info.status = SubsystemStatus.FAILED
            info.circuit_breaker.record_failure(e)
            info.error_log.append({
                'timestamp': datetime.now().isoformat(),
                'error': f'Lazy init failed: {str(e)[:200]}',
                'error_type': type(e).__name__,
            })
            return None

    def get(self, name: str) -> Any:
        """
        Get a subsystem instance. Returns None if not registered,
        disabled, or circuit-open.

        This is the primary replacement for hasattr() + getattr() patterns.
        Supports lazy initialization (P4.59).
        """
        with self._lock:
            info = self._subsystems.get(name)
            if info is None:
                return None
            if info.status in (SubsystemStatus.DISABLED, SubsystemStatus.FAILED):
                return None
            if info.status == SubsystemStatus.CIRCUIT_OPEN:
                if not info.circuit_breaker.should_attempt():
                    return None
            # Lazy init if needed
            if info.status == SubsystemStatus.REGISTERED and hasattr(info, '_factory') and info._factory:
                instance = self._lazy_init(name)
                if instance is None:
                    return None
            info.last_used = time.time()
            info.use_count += 1
            return info.instance

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        """Full serializable state of the registry."""
        with self._lock:
            return {
                'subsystems': {
                    name: info.to_dict()
                    for name, info in self._subsystems.items()
                },
                'health': self.get_health_report(),
                'dependency_graph': self.get_dependency_graph(),
                'initialization_order': self.get_initialization_order(),
            }

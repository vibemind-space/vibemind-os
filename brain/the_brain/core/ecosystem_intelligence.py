"""
Ecosystem Intelligence (V2 Phase 8: P8.96-100)

Five systems that enable Tahlamus to grow beyond a single brain
into an orchestrated, evolving ecosystem:

1. OrchestratorOfOrchestrators (P8.96):
   Coordinates sub-orchestrators — each specialised in a domain.
   Tracks capabilities, assigns goals, records outcomes, picks
   the best orchestrator for a given capability.

2. SystemSynergyLearning (P8.97):
   Learns which system-pipeline combinations produce the best
   results. Records pipeline executions, computes synergy scores
   between system pairs, and recommends optimal pipelines.

3. KnowledgeExport (P8.98):
   Exports and imports learned knowledge (skills, strategies,
   self-models) as portable, JSON-serializable packages so that
   knowledge can be transferred between brain instances.

4. EvolutionaryGrowth (P8.99):
   Tracks capability registration and usage over time, detects
   unused capabilities for archival, and suggests improvements
   based on usage patterns and growth metrics.

5. ConsciousnessEvolution (P8.100):
   Monitors how consciousness grows with experience: integration
   events across sub-systems, self-reflection depth, narrative
   richness, and an approximate phi estimate inspired by IIT.
"""

import time
import logging
import uuid
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.ecosystem_intelligence')


# ─── P8.96: Orchestrator of Orchestrators ─────────────────────────────────


class OrchestratorStatus(Enum):
    """Status of a registered sub-orchestrator."""
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass
class SubOrchestratorRecord:
    """Tracks a registered sub-orchestrator."""
    name: str
    endpoint: str
    capabilities: List[str]
    status: OrchestratorStatus = OrchestratorStatus.ACTIVE
    registered_at: float = 0.0
    total_goals: int = 0
    successful_goals: int = 0
    total_duration_ms: int = 0

    def __post_init__(self):
        if self.registered_at == 0.0:
            self.registered_at = time.time()

    @property
    def success_rate(self) -> float:
        if self.total_goals == 0:
            return 0.0
        return self.successful_goals / self.total_goals

    @property
    def avg_duration_ms(self) -> float:
        if self.total_goals == 0:
            return 0.0
        return self.total_duration_ms / self.total_goals

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'endpoint': self.endpoint,
            'capabilities': self.capabilities,
            'status': self.status.value,
            'registered_at': self.registered_at,
            'total_goals': self.total_goals,
            'successful_goals': self.successful_goals,
            'success_rate': round(self.success_rate, 3),
            'avg_duration_ms': round(self.avg_duration_ms, 1),
        }


class OrchestratorOfOrchestrators:
    """
    P8.96: Coordinates sub-orchestrators.

    Each sub-orchestrator is a specialist — one for code generation,
    another for deployment, another for monitoring, etc. This meta-
    orchestrator assigns goals to the best sub-orchestrator based
    on required capabilities and historical performance.
    """

    def __init__(
        self,
        max_history: int = 500,
        degraded_threshold: float = 0.3,
    ):
        """
        Args:
            max_history: Maximum outcome records to keep per orchestrator.
            degraded_threshold: Success rate below this marks orchestrator degraded.
        """
        self.max_history = max_history
        self.degraded_threshold = degraded_threshold

        self._orchestrators: Dict[str, SubOrchestratorRecord] = {}
        self._goal_counter: int = 0
        self._assignment_history: deque = deque(maxlen=max_history)

        logger.info("OrchestratorOfOrchestrators initialised (max_history=%d)", max_history)

    def register_orchestrator(
        self,
        name: str,
        endpoint: str,
        capabilities: List[str],
    ) -> None:
        """Register a sub-orchestrator with its capabilities."""
        self._orchestrators[name] = SubOrchestratorRecord(
            name=name,
            endpoint=endpoint,
            capabilities=list(capabilities),
        )
        logger.info("Registered sub-orchestrator '%s' with capabilities %s", name, capabilities)

    def assign_goal(
        self,
        goal_description: str,
        required_capabilities: List[str],
    ) -> Dict[str, Any]:
        """
        Assign a goal to the best available sub-orchestrator.

        Returns an assignment dict with orchestrator_name and delegation_plan.
        If no orchestrator can handle all required capabilities, returns
        a multi-orchestrator delegation plan.
        """
        self._goal_counter += 1
        goal_id = f"goal_{self._goal_counter}"

        # Find orchestrators that cover at least one required capability
        candidates: List[Tuple[str, SubOrchestratorRecord, int]] = []
        for name, orch in self._orchestrators.items():
            if orch.status == OrchestratorStatus.OFFLINE:
                continue
            overlap = len(set(orch.capabilities) & set(required_capabilities))
            if overlap > 0:
                candidates.append((name, orch, overlap))

        if not candidates:
            logger.warning("No orchestrator found for capabilities %s", required_capabilities)
            return {
                'goal_id': goal_id,
                'goal_description': goal_description,
                'orchestrator_name': None,
                'delegation_plan': [],
                'status': 'no_match',
            }

        # Sort by: coverage desc, then success rate desc
        candidates.sort(key=lambda c: (c[2], c[1].success_rate), reverse=True)

        best_name, best_orch, best_overlap = candidates[0]
        covered = set(best_orch.capabilities) & set(required_capabilities)
        uncovered = set(required_capabilities) - covered

        delegation_plan = [{
            'orchestrator': best_name,
            'capabilities_handled': sorted(covered),
        }]

        # If not all capabilities are covered, add secondary orchestrators
        for cap in sorted(uncovered):
            secondary = self.get_best_orchestrator(cap)
            if secondary:
                delegation_plan.append({
                    'orchestrator': secondary,
                    'capabilities_handled': [cap],
                })

        assignment = {
            'goal_id': goal_id,
            'goal_description': goal_description,
            'orchestrator_name': best_name,
            'delegation_plan': delegation_plan,
            'status': 'assigned',
            'timestamp': time.time(),
        }
        self._assignment_history.append(assignment)

        logger.info("Assigned goal '%s' → orchestrator '%s'", goal_id, best_name)
        return assignment

    def record_outcome(
        self,
        orchestrator_name: str,
        goal_id: str,
        success: bool,
        duration_ms: int,
    ) -> None:
        """Record the outcome of a goal executed by a sub-orchestrator."""
        orch = self._orchestrators.get(orchestrator_name)
        if orch is None:
            logger.warning("Unknown orchestrator '%s' in record_outcome", orchestrator_name)
            return

        orch.total_goals += 1
        if success:
            orch.successful_goals += 1
        orch.total_duration_ms += duration_ms

        # Update status based on recent success rate
        if orch.total_goals >= 5 and orch.success_rate < self.degraded_threshold:
            orch.status = OrchestratorStatus.DEGRADED
            logger.warning("Orchestrator '%s' degraded (success_rate=%.2f)", orchestrator_name, orch.success_rate)
        elif orch.status == OrchestratorStatus.DEGRADED and orch.success_rate >= self.degraded_threshold:
            orch.status = OrchestratorStatus.ACTIVE

    def get_orchestrator_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats dict per orchestrator."""
        return {
            name: orch.to_dict()
            for name, orch in self._orchestrators.items()
        }

    def get_best_orchestrator(self, capability: str) -> Optional[str]:
        """Get the name of the best-performing orchestrator for a capability."""
        best_name = None
        best_score = -1.0

        for name, orch in self._orchestrators.items():
            if orch.status == OrchestratorStatus.OFFLINE:
                continue
            if capability in orch.capabilities:
                # Score: success rate, tie-break by experience
                score = orch.success_rate + (orch.total_goals * 0.001)
                if score > best_score:
                    best_score = score
                    best_name = name

        return best_name

    @classmethod
    def from_yaml(cls, config: Dict) -> 'OrchestratorOfOrchestrators':
        """Create from YAML config dict."""
        ec = config.get('ecosystem_intelligence', {})
        oo = ec.get('orchestrator_of_orchestrators', {})
        return cls(
            max_history=oo.get('max_history', 500),
            degraded_threshold=oo.get('degraded_threshold', 0.3),
        )

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'OrchestratorOfOrchestrators',
            'total_orchestrators': len(self._orchestrators),
            'total_goals_assigned': self._goal_counter,
            'orchestrators': self.get_orchestrator_stats(),
            'recent_assignments': len(self._assignment_history),
        }


# ─── P8.97: System Synergy Learning ──────────────────────────────────────


@dataclass
class PipelineRecord:
    """Tracks execution results for a specific pipeline."""
    total_executions: int = 0
    successful_executions: int = 0
    total_duration_ms: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def avg_duration_ms(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions


class SystemSynergyLearning:
    """
    P8.97: Learns which system combinations work best.

    Tracks ordered pipelines (sequences of systems) and their outcomes.
    Computes pairwise synergy scores between systems based on how often
    they succeed when used together versus individually.
    """

    def __init__(self, max_pipelines: int = 200):
        """
        Args:
            max_pipelines: Maximum distinct pipelines to track.
        """
        self.max_pipelines = max_pipelines

        # pipeline key = tuple of system names → PipelineRecord
        self._pipelines: Dict[tuple, PipelineRecord] = {}

        # Pairwise co-occurrence tracking: (a, b) → {successes, failures}
        self._pair_stats: Dict[tuple, Dict[str, int]] = defaultdict(
            lambda: {'successes': 0, 'failures': 0}
        )

        # Individual system stats
        self._system_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {'successes': 0, 'failures': 0}
        )

        self._total_executions = 0

        logger.info("SystemSynergyLearning initialised (max_pipelines=%d)", max_pipelines)

    @staticmethod
    def _pipeline_key(pipeline: List[str]) -> tuple:
        """Convert pipeline list to hashable key."""
        return tuple(pipeline)

    def record_pipeline_execution(
        self,
        pipeline: List[str],
        success: bool,
        duration_ms: int,
    ) -> None:
        """Record the result of executing a system pipeline."""
        key = self._pipeline_key(pipeline)
        self._total_executions += 1

        # Create or update pipeline record
        if key not in self._pipelines:
            if len(self._pipelines) >= self.max_pipelines:
                # Evict least-used pipeline
                least_used = min(self._pipelines, key=lambda k: self._pipelines[k].total_executions)
                del self._pipelines[least_used]
            self._pipelines[key] = PipelineRecord()

        record = self._pipelines[key]
        record.total_executions += 1
        if success:
            record.successful_executions += 1
        record.total_duration_ms += duration_ms

        # Update pair stats for all adjacent pairs in the pipeline
        for i in range(len(pipeline) - 1):
            pair = (pipeline[i], pipeline[i + 1])
            outcome_key = 'successes' if success else 'failures'
            self._pair_stats[pair][outcome_key] += 1

        # Update individual system stats
        for system in pipeline:
            outcome_key = 'successes' if success else 'failures'
            self._system_stats[system][outcome_key] += 1

    def get_pipeline_stats(self, pipeline: List[str]) -> Dict[str, Any]:
        """Get statistics for a specific pipeline."""
        key = self._pipeline_key(pipeline)
        record = self._pipelines.get(key)
        if record is None:
            return {
                'pipeline': pipeline,
                'success_rate': 0.0,
                'avg_duration_ms': 0.0,
                'executions': 0,
            }
        return {
            'pipeline': list(key),
            'success_rate': round(record.success_rate, 3),
            'avg_duration_ms': round(record.avg_duration_ms, 1),
            'executions': record.total_executions,
        }

    def get_best_pipeline(
        self,
        start_system: str,
        end_system: str,
    ) -> List[str]:
        """
        Get the best-performing pipeline from start_system to end_system.

        Returns the pipeline with the highest success rate among those
        that start with start_system and end with end_system. Falls back
        to [start_system, end_system] if none found.
        """
        best_pipeline = None
        best_score = -1.0

        for key, record in self._pipelines.items():
            if not key or key[0] != start_system or key[-1] != end_system:
                continue
            if record.total_executions < 1:
                continue
            score = record.success_rate
            if score > best_score:
                best_score = score
                best_pipeline = list(key)

        if best_pipeline is None:
            return [start_system, end_system]

        return best_pipeline

    def get_synergy_matrix(self) -> Dict[str, float]:
        """
        Get pairwise synergy scores between systems.

        Synergy is computed as the pair's success rate minus the average
        of the individual systems' success rates. Positive = synergistic,
        negative = antagonistic.

        Returns dict with keys like "system_a->system_b" → synergy_score.
        """
        synergy = {}
        for (a, b), stats in self._pair_stats.items():
            total = stats['successes'] + stats['failures']
            if total < 2:
                continue

            pair_rate = stats['successes'] / total

            # Individual rates
            a_stats = self._system_stats.get(a, {'successes': 0, 'failures': 0})
            b_stats = self._system_stats.get(b, {'successes': 0, 'failures': 0})
            a_total = a_stats['successes'] + a_stats['failures']
            b_total = b_stats['successes'] + b_stats['failures']

            a_rate = a_stats['successes'] / max(a_total, 1)
            b_rate = b_stats['successes'] / max(b_total, 1)

            avg_individual = (a_rate + b_rate) / 2.0
            synergy_score = pair_rate - avg_individual

            synergy[f"{a}->{b}"] = round(synergy_score, 4)

        return synergy

    def get_state(self) -> Dict[str, Any]:
        top_pipelines = sorted(
            self._pipelines.items(),
            key=lambda kv: kv[1].success_rate * kv[1].total_executions,
            reverse=True,
        )[:10]

        return {
            'name': 'SystemSynergyLearning',
            'total_executions': self._total_executions,
            'tracked_pipelines': len(self._pipelines),
            'tracked_pairs': len(self._pair_stats),
            'tracked_systems': len(self._system_stats),
            'top_pipelines': [
                {
                    'pipeline': list(k),
                    'success_rate': round(v.success_rate, 3),
                    'executions': v.total_executions,
                }
                for k, v in top_pipelines
            ],
            'synergy_matrix': self.get_synergy_matrix(),
        }


# ─── P8.98: Knowledge Export ──────────────────────────────────────────────


class KnowledgeExport:
    """
    P8.98: Export and import learned knowledge.

    Packages internal knowledge (skills, strategies, self-models) into
    portable, JSON-serializable dicts that can be saved to disk or
    transferred to another brain instance.
    """

    VERSION = "1.0.0"

    def __init__(self):
        self._exports_count = 0
        self._imports_count = 0
        self._last_export_time: float = 0.0
        self._last_import_time: float = 0.0

        logger.info("KnowledgeExport initialised")

    def export_skills(self, skill_library: Any) -> Dict[str, Any]:
        """
        Export skills from a skill library / procedural memory.

        Accepts any object that has a get_state() or to_dict() method,
        or a plain dict. Returns a JSON-serializable skill package.
        """
        self._exports_count += 1
        self._last_export_time = time.time()

        skills_data = self._extract_state(skill_library)

        return {
            'type': 'skills',
            'version': self.VERSION,
            'exported_at': self._last_export_time,
            'export_id': str(uuid.uuid4()),
            'data': skills_data,
        }

    def export_strategies(self, collaborative_learning: Any) -> Dict[str, Any]:
        """
        Export learned strategies from a collaborative learning system.

        Accepts any object with get_state()/to_dict() or a plain dict.
        """
        self._exports_count += 1
        self._last_export_time = time.time()

        strategies_data = self._extract_state(collaborative_learning)

        return {
            'type': 'strategies',
            'version': self.VERSION,
            'exported_at': self._last_export_time,
            'export_id': str(uuid.uuid4()),
            'data': strategies_data,
        }

    def export_self_model(self, self_model: Any) -> Dict[str, Any]:
        """
        Export a self-model / personality profile.

        Accepts any object with get_state()/to_dict() or a plain dict.
        """
        self._exports_count += 1
        self._last_export_time = time.time()

        model_data = self._extract_state(self_model)

        return {
            'type': 'self_model',
            'version': self.VERSION,
            'exported_at': self._last_export_time,
            'export_id': str(uuid.uuid4()),
            'data': model_data,
        }

    def export_full_knowledge(self, components: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export a combined knowledge package from multiple components.

        Args:
            components: Dict mapping component names to their objects.
                        e.g. {'skills': skill_lib, 'strategies': collab, 'self_model': model}
        """
        self._exports_count += 1
        self._last_export_time = time.time()

        package = {
            'type': 'full_knowledge',
            'version': self.VERSION,
            'exported_at': self._last_export_time,
            'export_id': str(uuid.uuid4()),
            'components': {},
        }

        for name, component in components.items():
            package['components'][name] = self._extract_state(component)

        package['component_count'] = len(package['components'])

        return package

    def import_knowledge(self, package: Dict[str, Any]) -> Dict[str, Any]:
        """
        Import a previously exported knowledge package.

        Validates the package structure and returns import summary
        with counts of imported items. The caller is responsible for
        actually applying the data to the target systems.
        """
        self._imports_count += 1
        self._last_import_time = time.time()

        pkg_type = package.get('type', 'unknown')
        pkg_version = package.get('version', 'unknown')

        result = {
            'status': 'success',
            'package_type': pkg_type,
            'package_version': pkg_version,
            'imported_at': self._last_import_time,
        }

        if pkg_type == 'full_knowledge':
            components = package.get('components', {})
            result['components_imported'] = len(components)
            result['component_names'] = list(components.keys())
            total_items = 0
            for comp_data in components.values():
                total_items += self._count_items(comp_data)
            result['total_items'] = total_items
        else:
            data = package.get('data', {})
            items = self._count_items(data)
            result['items_imported'] = items

        logger.info(
            "Imported knowledge package type='%s' version='%s'",
            pkg_type, pkg_version,
        )

        return result

    @staticmethod
    def _extract_state(obj: Any) -> Dict[str, Any]:
        """Extract state from an object using get_state(), to_dict(), or as-is."""
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, 'get_state'):
            return obj.get_state()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        # Fallback: wrap as string representation
        return {'raw': str(obj)}

    @staticmethod
    def _count_items(data: Any) -> int:
        """Count the number of items in a data structure."""
        if isinstance(data, dict):
            return len(data)
        if isinstance(data, (list, tuple)):
            return len(data)
        return 1

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'KnowledgeExport',
            'version': self.VERSION,
            'total_exports': self._exports_count,
            'total_imports': self._imports_count,
            'last_export_time': self._last_export_time,
            'last_import_time': self._last_import_time,
        }


# ─── P8.99: Evolutionary Growth ──────────────────────────────────────────


class CapabilityStatus(Enum):
    """Status of a registered capability."""
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class CapabilityRecord:
    """Tracks a registered capability and its usage."""
    name: str
    category: str
    version: str = "1.0"
    status: CapabilityStatus = CapabilityStatus.ACTIVE
    registered_at: float = 0.0
    last_used_at: float = 0.0
    usage_count: int = 0

    def __post_init__(self):
        if self.registered_at == 0.0:
            self.registered_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'category': self.category,
            'version': self.version,
            'status': self.status.value,
            'registered_at': self.registered_at,
            'last_used_at': self.last_used_at,
            'usage_count': self.usage_count,
        }


class EvolutionaryGrowth:
    """
    P8.99: System evolves over time.

    Tracks registered capabilities, monitors usage patterns, detects
    stale capabilities for archival, and suggests improvements based
    on growth metrics.
    """

    def __init__(
        self,
        archive_after_days: int = 30,
        max_capabilities: int = 500,
    ):
        """
        Args:
            archive_after_days: Days of inactivity before a capability is
                                suggested for archiving.
            max_capabilities: Maximum tracked capabilities.
        """
        self.archive_after_days = archive_after_days
        self.max_capabilities = max_capabilities

        self._capabilities: Dict[str, CapabilityRecord] = {}
        self._growth_events: deque = deque(maxlen=1000)

        logger.info(
            "EvolutionaryGrowth initialised (archive_after=%d days)",
            archive_after_days,
        )

    def register_capability(
        self,
        name: str,
        category: str,
        version: str = '1.0',
    ) -> None:
        """Register a new capability."""
        now = time.time()
        self._capabilities[name] = CapabilityRecord(
            name=name,
            category=category,
            version=version,
            registered_at=now,
        )
        self._growth_events.append({
            'event': 'registered',
            'capability': name,
            'category': category,
            'timestamp': now,
        })
        logger.info("Registered capability '%s' (category=%s, version=%s)", name, category, version)

    def record_usage(self, capability_name: str) -> None:
        """Record that a capability was used."""
        cap = self._capabilities.get(capability_name)
        if cap is None:
            logger.debug("Usage recorded for unknown capability '%s'", capability_name)
            return

        now = time.time()
        cap.usage_count += 1
        cap.last_used_at = now

        # Reactivate if it was archived but is being used
        if cap.status == CapabilityStatus.ARCHIVED:
            cap.status = CapabilityStatus.ACTIVE
            self._growth_events.append({
                'event': 'reactivated',
                'capability': capability_name,
                'timestamp': now,
            })

    def get_unused_capabilities(self, days_threshold: int = 30) -> List[str]:
        """Get capabilities not used within days_threshold days."""
        now = time.time()
        cutoff = now - (days_threshold * 86400)
        unused = []

        for name, cap in self._capabilities.items():
            if cap.status != CapabilityStatus.ACTIVE:
                continue
            # If never used and registered before cutoff, or last used before cutoff
            effective_time = cap.last_used_at if cap.last_used_at > 0 else cap.registered_at
            if effective_time < cutoff:
                unused.append(name)

        return unused

    def get_growth_metrics(self) -> Dict[str, Any]:
        """Get overall growth metrics."""
        total = len(self._capabilities)
        active = sum(
            1 for c in self._capabilities.values()
            if c.status == CapabilityStatus.ACTIVE
        )
        archived = sum(
            1 for c in self._capabilities.values()
            if c.status == CapabilityStatus.ARCHIVED
        )

        # Growth rate: new registrations in the last 7 days
        now = time.time()
        week_ago = now - (7 * 86400)
        recent_events = [
            e for e in self._growth_events
            if e['event'] == 'registered' and e['timestamp'] > week_ago
        ]
        growth_rate = len(recent_events) / 7.0  # per day

        # Category distribution
        categories: Dict[str, int] = defaultdict(int)
        for cap in self._capabilities.values():
            categories[cap.category] += 1

        return {
            'total_capabilities': total,
            'active': active,
            'archived': archived,
            'growth_rate': round(growth_rate, 2),
            'categories': dict(categories),
        }

    def suggest_improvements(self) -> List[Dict[str, Any]]:
        """
        Suggest improvements based on usage patterns.

        Analyses capability usage to identify:
        - Underused capabilities that could be promoted
        - Overloaded categories that need decomposition
        - Version staleness
        """
        suggestions = []
        now = time.time()

        # 1. Suggest archiving unused capabilities
        unused = self.get_unused_capabilities(self.archive_after_days)
        if unused:
            suggestions.append({
                'type': 'archive',
                'description': f"Archive {len(unused)} unused capabilities",
                'capabilities': unused[:10],  # Cap to 10 for readability
                'priority': 'low',
            })

        # 2. Detect overloaded categories (> 20 capabilities)
        categories: Dict[str, int] = defaultdict(int)
        for cap in self._capabilities.values():
            if cap.status == CapabilityStatus.ACTIVE:
                categories[cap.category] += 1

        for cat, count in categories.items():
            if count > 20:
                suggestions.append({
                    'type': 'decompose_category',
                    'description': f"Category '{cat}' has {count} capabilities — consider splitting",
                    'category': cat,
                    'priority': 'medium',
                })

        # 3. Detect heavily used capabilities that might need scaling
        heavy_use = [
            cap for cap in self._capabilities.values()
            if cap.usage_count > 100 and cap.status == CapabilityStatus.ACTIVE
        ]
        if heavy_use:
            top = sorted(heavy_use, key=lambda c: c.usage_count, reverse=True)[:5]
            suggestions.append({
                'type': 'scale_up',
                'description': f"{len(heavy_use)} capabilities have high usage — consider optimization",
                'capabilities': [c.name for c in top],
                'priority': 'medium',
            })

        # 4. Detect stale versions (registered > 90 days, version still 1.0)
        ninety_days_ago = now - (90 * 86400)
        stale = [
            cap.name for cap in self._capabilities.values()
            if cap.registered_at < ninety_days_ago
            and cap.version == '1.0'
            and cap.status == CapabilityStatus.ACTIVE
        ]
        if stale:
            suggestions.append({
                'type': 'version_update',
                'description': f"{len(stale)} capabilities still at v1.0 after 90+ days",
                'capabilities': stale[:10],
                'priority': 'low',
            })

        return suggestions

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'EvolutionaryGrowth',
            'growth_metrics': self.get_growth_metrics(),
            'improvement_suggestions': len(self.suggest_improvements()),
            'recent_events': len(self._growth_events),
            'capabilities': {
                name: cap.to_dict()
                for name, cap in self._capabilities.items()
            },
        }


# ─── P8.100: Consciousness Evolution ─────────────────────────────────────


@dataclass
class IntegrationEvent:
    """Records an integration event across subsystems."""
    systems_involved: List[str]
    success: bool
    timestamp: float = 0.0
    integration_breadth: int = 0  # Number of distinct systems

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        self.integration_breadth = len(set(self.systems_involved))


@dataclass
class ReflectionRecord:
    """Records a self-reflection event."""
    depth: float       # 0.0–1.0, how deep was the reflection
    insight: str        # What was learned
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ConsciousnessEvolution:
    """
    P8.100: Consciousness grows with experience.

    Tracks how integrated the brain's subsystems become over time.
    Inspired loosely by Integrated Information Theory (IIT):
    - Phi estimate: how much information is generated above and
      beyond independent subsystems.
    - Integration score: how many distinct subsystems participate
      in coherent processing.
    - Reflection depth: how deep self-reflection reaches.
    - Narrative richness: how much insight is accumulated.
    """

    def __init__(
        self,
        max_events: int = 1000,
        max_reflections: int = 500,
        timeline_resolution: int = 100,
    ):
        """
        Args:
            max_events: Maximum integration events to track.
            max_reflections: Maximum reflection records.
            timeline_resolution: Maximum timeline snapshots to keep.
        """
        self.max_events = max_events
        self.max_reflections = max_reflections
        self.timeline_resolution = timeline_resolution

        self._integration_events: deque = deque(maxlen=max_events)
        self._reflections: deque = deque(maxlen=max_reflections)
        self._timeline: deque = deque(maxlen=timeline_resolution)

        # Tracking
        self._total_events = 0
        self._total_reflections = 0
        self._all_systems_seen: set = set()

        logger.info("ConsciousnessEvolution initialised")

    def record_integration_event(
        self,
        systems_involved: List[str],
        success: bool,
    ) -> None:
        """Record an integration event across subsystems."""
        event = IntegrationEvent(
            systems_involved=list(systems_involved),
            success=success,
        )
        self._integration_events.append(event)
        self._total_events += 1
        self._all_systems_seen.update(systems_involved)

        # Snapshot timeline periodically
        if self._total_events % 10 == 0:
            level = self.get_consciousness_level()
            self._timeline.append((time.time(), level))

    def record_self_reflection(
        self,
        depth: float,
        insight: str,
    ) -> None:
        """Record a self-reflection event."""
        depth = max(0.0, min(1.0, depth))
        reflection = ReflectionRecord(depth=depth, insight=insight)
        self._reflections.append(reflection)
        self._total_reflections += 1

    def get_consciousness_level(self) -> Dict[str, Any]:
        """
        Compute the current consciousness level.

        Returns:
            phi_estimate: Approximate integrated information (0.0-1.0).
            integration_score: How broadly systems integrate (0.0-1.0).
            reflection_depth: Average reflection depth (0.0-1.0).
            narrative_richness: Insight accumulation metric (0.0-1.0).
        """
        # --- Phi estimate ---
        # Approximate: ratio of successful multi-system integrations
        # to total events, weighted by breadth
        recent_events = list(self._integration_events)[-100:]
        if recent_events:
            weighted_sum = 0.0
            for ev in recent_events:
                if ev.success:
                    # More systems = higher integration
                    weighted_sum += min(1.0, ev.integration_breadth / 5.0)
            phi = weighted_sum / len(recent_events)
        else:
            phi = 0.0

        # --- Integration score ---
        # How many distinct systems have participated recently
        if recent_events:
            recent_systems = set()
            for ev in recent_events:
                recent_systems.update(ev.systems_involved)
            total_known = max(len(self._all_systems_seen), 1)
            integration_score = min(1.0, len(recent_systems) / total_known)
        else:
            integration_score = 0.0

        # --- Reflection depth ---
        recent_reflections = list(self._reflections)[-50:]
        if recent_reflections:
            reflection_depth = sum(r.depth for r in recent_reflections) / len(recent_reflections)
        else:
            reflection_depth = 0.0

        # --- Narrative richness ---
        # Based on unique insights and their depth
        if self._reflections:
            unique_insights = len(set(r.insight for r in self._reflections))
            # Log scale: more unique insights = richer narrative
            narrative_richness = min(1.0, math.log1p(unique_insights) / math.log1p(100))
        else:
            narrative_richness = 0.0

        return {
            'phi_estimate': round(phi, 4),
            'integration_score': round(integration_score, 4),
            'reflection_depth': round(reflection_depth, 4),
            'narrative_richness': round(narrative_richness, 4),
        }

    def get_evolution_timeline(self) -> List[Tuple[float, Dict[str, Any]]]:
        """Get the timeline of consciousness level snapshots."""
        return list(self._timeline)

    def get_state(self) -> Dict[str, Any]:
        level = self.get_consciousness_level()
        return {
            'name': 'ConsciousnessEvolution',
            'total_integration_events': self._total_events,
            'total_reflections': self._total_reflections,
            'systems_ever_seen': sorted(self._all_systems_seen),
            'current_level': level,
            'timeline_snapshots': len(self._timeline),
        }

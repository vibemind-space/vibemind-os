"""
Self-Model System (V2 Phase 6: P6.76-78)

Three components that give Tahlamus a persistent sense of identity:

P6.76: SelfModel
  - Persistent self-image: capabilities, preferences, weaknesses
  - Per-system, per-domain success rate tracking
  - Preferred strategies and tools from successful outcomes
  - Known weaknesses from KnowledgeGapDetection integration
  - Updates after each task outcome

P6.77: AutobiographicMemory
  - Long-term memories of development milestones
  - Records emotionally significant events (with valence)
  - Daily summaries of accomplishments
  - Narrative generation: story-like retelling of development

P6.78: ValueSystem
  - Explicit values that influence decision-making
  - Default values: reliability, transparency, caution, helpfulness, growth
  - Action evaluation against values (ValueAssessment)
  - Goal priority weighting based on value alignment
  - Adjustable within 0-1 bounds
"""

import time
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.self_model')


# ─── P6.76: Self Model ───────────────────────────────────────────────────

@dataclass
class CapabilityRecord:
    """Tracks success rate for a system-domain pair."""
    system: str
    domain: str
    total_attempts: int = 0
    total_successes: int = 0
    recent_outcomes: List[bool] = field(default_factory=list)
    max_recent: int = 50
    last_updated: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.total_successes / self.total_attempts

    @property
    def recent_success_rate(self) -> float:
        if not self.recent_outcomes:
            return 0.0
        return sum(self.recent_outcomes) / len(self.recent_outcomes)

    def record(self, success: bool) -> None:
        self.total_attempts += 1
        if success:
            self.total_successes += 1
        self.recent_outcomes.append(success)
        if len(self.recent_outcomes) > self.max_recent:
            self.recent_outcomes.pop(0)
        self.last_updated = time.time()

    def to_dict(self) -> Dict:
        return {
            'system': self.system,
            'domain': self.domain,
            'success_rate': round(self.success_rate, 3),
            'recent_success_rate': round(self.recent_success_rate, 3),
            'total_attempts': self.total_attempts,
        }


@dataclass
class StrategyPreference:
    """Tracks preference for a strategy based on usage and success."""
    strategy: str
    usage_count: int = 0
    success_count: int = 0
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    def record(self, success: bool) -> None:
        self.usage_count += 1
        if success:
            self.success_count += 1
        self.last_used = time.time()

    def to_dict(self) -> Dict:
        return {
            'strategy': self.strategy,
            'usage_count': self.usage_count,
            'success_rate': round(self.success_rate, 3),
        }


@dataclass
class ToolPreference:
    """Tracks preference for a tool based on usage and success."""
    tool: str
    usage_count: int = 0
    success_count: int = 0
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    def record(self, success: bool) -> None:
        self.usage_count += 1
        if success:
            self.success_count += 1
        self.last_used = time.time()

    def to_dict(self) -> Dict:
        return {
            'tool': self.tool,
            'usage_count': self.usage_count,
            'success_rate': round(self.success_rate, 3),
        }


@dataclass
class Weakness:
    """A known weakness or knowledge gap."""
    area: str
    description: str
    severity: float = 0.5        # 0-1
    failure_count: int = 0
    first_detected: float = 0.0
    last_observed: float = 0.0
    resolved: bool = False

    def __post_init__(self):
        if self.first_detected == 0.0:
            self.first_detected = time.time()

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_observed = time.time()
        self._update_severity()

    def _update_severity(self) -> None:
        frequency_factor = min(1.0, self.failure_count / 10.0)
        recency_hours = (time.time() - self.last_observed) / 3600.0
        recency_factor = max(0.1, 1.0 / (1.0 + recency_hours * 0.1))
        self.severity = round(frequency_factor * recency_factor, 3)

    def to_dict(self) -> Dict:
        return {
            'area': self.area,
            'description': self.description,
            'severity': self.severity,
            'failure_count': self.failure_count,
            'resolved': self.resolved,
        }


class SelfModel:
    """
    P6.76: Persistent self-image of Tahlamus.

    Tracks what the brain can and cannot do, which strategies work,
    which tools it prefers, and where its weaknesses lie. Updated
    after each task outcome to maintain an accurate self-portrait.

    Integration points:
    - AgentLoop calls record_outcome() after each task
    - KnowledgeGapDetection feeds weaknesses via record_weakness()
    - Language center queries get_capabilities() for self-description
    - Goal system queries get_weaknesses() to generate improvement goals
    """

    def __init__(
        self,
        max_capabilities: int = 200,
        max_strategies: int = 100,
        max_tools: int = 50,
        max_weaknesses: int = 100,
        weakness_auto_resolve_threshold: int = 5,
    ):
        """
        Args:
            max_capabilities: Max system-domain pairs to track
            max_strategies: Max strategies to remember
            max_tools: Max tools to remember
            max_weaknesses: Max weaknesses to track
            weakness_auto_resolve_threshold: Consecutive successes to resolve a weakness
        """
        self.max_capabilities = max_capabilities
        self.max_strategies = max_strategies
        self.max_tools = max_tools
        self.max_weaknesses = max_weaknesses
        self.weakness_auto_resolve_threshold = weakness_auto_resolve_threshold

        # Capabilities: {system: {domain: CapabilityRecord}}
        self._capabilities: Dict[str, Dict[str, CapabilityRecord]] = defaultdict(dict)

        # Preferred strategies: {strategy_name: StrategyPreference}
        self._strategies: Dict[str, StrategyPreference] = {}

        # Preferred tools: {tool_name: ToolPreference}
        self._tools: Dict[str, ToolPreference] = {}

        # Known weaknesses: {area: Weakness}
        self._weaknesses: Dict[str, Weakness] = {}

        # Consecutive success counter for weakness resolution
        self._success_streak: Dict[str, int] = defaultdict(int)

        # Statistics
        self._total_outcomes: int = 0
        self._total_successes: int = 0

    def record_outcome(
        self,
        system: str,
        domain: str,
        success: bool,
        strategy: Optional[str] = None,
        tools_used: Optional[List[str]] = None,
    ) -> None:
        """
        Record a task outcome to update self-model.

        Args:
            system: System that performed the task (e.g. 'Coding_Engine', 'Shell')
            domain: Task domain (e.g. 'python', 'docker', 'git')
            success: Whether the task succeeded
            strategy: Strategy used (e.g. 'incremental', 'brute_force')
            tools_used: List of tools used (e.g. ['grep', 'pytest'])
        """
        self._total_outcomes += 1
        if success:
            self._total_successes += 1

        # ── Update capability record ──
        if domain not in self._capabilities[system]:
            # Capacity check
            total_caps = sum(len(d) for d in self._capabilities.values())
            if total_caps >= self.max_capabilities:
                self._evict_oldest_capability()
            self._capabilities[system][domain] = CapabilityRecord(
                system=system, domain=domain
            )
        self._capabilities[system][domain].record(success)

        # ── Update strategy preference ──
        if strategy:
            if strategy not in self._strategies:
                if len(self._strategies) >= self.max_strategies:
                    self._evict_weakest_strategy()
                self._strategies[strategy] = StrategyPreference(strategy=strategy)
            self._strategies[strategy].record(success)

        # ── Update tool preferences ──
        if tools_used:
            for tool in tools_used:
                if tool not in self._tools:
                    if len(self._tools) >= self.max_tools:
                        self._evict_weakest_tool()
                    self._tools[tool] = ToolPreference(tool=tool)
                self._tools[tool].record(success)

        # ── Weakness tracking ──
        key = f"{system}:{domain}"
        if not success:
            self._success_streak[key] = 0
            if key in self._weaknesses and not self._weaknesses[key].resolved:
                self._weaknesses[key].record_failure()
            else:
                # Check if capability record shows persistent low rate
                cap = self._capabilities[system][domain]
                if cap.total_attempts >= 3 and cap.recent_success_rate < 0.5:
                    self._register_weakness(
                        key,
                        f"Low success rate in {system}/{domain}: "
                        f"{cap.recent_success_rate:.0%}"
                    )
        else:
            self._success_streak[key] = self._success_streak.get(key, 0) + 1
            # Auto-resolve weakness on streak
            if (key in self._weaknesses
                    and not self._weaknesses[key].resolved
                    and self._success_streak[key] >= self.weakness_auto_resolve_threshold):
                self._weaknesses[key].resolved = True
                logger.info(f"Weakness auto-resolved: {key}")

    def record_weakness(self, area: str, description: str,
                        severity: float = 0.5) -> None:
        """
        Record a weakness from external source (e.g. KnowledgeGapDetection).

        Args:
            area: Weakness area identifier
            description: Human-readable description
            severity: 0-1 severity rating
        """
        if area in self._weaknesses:
            self._weaknesses[area].record_failure()
            if description:
                self._weaknesses[area].description = description
        else:
            if len(self._weaknesses) >= self.max_weaknesses:
                self._evict_resolved_weaknesses()
            self._weaknesses[area] = Weakness(
                area=area,
                description=description,
                severity=severity,
                failure_count=1,
                last_observed=time.time(),
            )

    def _register_weakness(self, area: str, description: str) -> None:
        """Internal: register a weakness detected from low success rates."""
        if area not in self._weaknesses:
            if len(self._weaknesses) >= self.max_weaknesses:
                self._evict_resolved_weaknesses()
            self._weaknesses[area] = Weakness(
                area=area,
                description=description,
                failure_count=1,
                last_observed=time.time(),
            )
        else:
            self._weaknesses[area].record_failure()

    def get_capabilities(self) -> Dict[str, Dict[str, Dict]]:
        """
        Get all tracked capabilities organized by system and domain.

        Returns:
            {system: {domain: {success_rate, recent_success_rate, total_attempts}}}
        """
        result = {}
        for system, domains in self._capabilities.items():
            result[system] = {}
            for domain, cap in domains.items():
                result[system][domain] = cap.to_dict()
        return result

    def get_system_summary(self, system: str) -> Dict:
        """Get aggregated capability summary for a specific system."""
        domains = self._capabilities.get(system, {})
        if not domains:
            return {'system': system, 'known': False}

        rates = [cap.success_rate for cap in domains.values()]
        attempts = [cap.total_attempts for cap in domains.values()]
        return {
            'system': system,
            'known': True,
            'domains_tracked': len(domains),
            'avg_success_rate': round(sum(rates) / len(rates), 3) if rates else 0.0,
            'total_attempts': sum(attempts),
            'strongest_domain': max(domains.keys(), key=lambda d: domains[d].success_rate) if domains else None,
            'weakest_domain': min(domains.keys(), key=lambda d: domains[d].success_rate) if domains else None,
        }

    def get_preferences(self) -> Dict:
        """
        Get preferred strategies and tools.

        Returns dict with top strategies and tools sorted by success rate.
        """
        # Top strategies by success rate (min 2 uses)
        qualified_strategies = [
            s for s in self._strategies.values() if s.usage_count >= 2
        ]
        qualified_strategies.sort(key=lambda s: s.success_rate, reverse=True)

        # Top tools by success rate (min 2 uses)
        qualified_tools = [
            t for t in self._tools.values() if t.usage_count >= 2
        ]
        qualified_tools.sort(key=lambda t: t.success_rate, reverse=True)

        return {
            'preferred_strategies': [s.to_dict() for s in qualified_strategies[:10]],
            'preferred_tools': [t.to_dict() for t in qualified_tools[:10]],
            'all_strategies': len(self._strategies),
            'all_tools': len(self._tools),
        }

    def get_weaknesses(self) -> List[Dict]:
        """
        Get known weaknesses, sorted by severity (highest first).

        Returns list of unresolved weaknesses.
        """
        active = [w for w in self._weaknesses.values() if not w.resolved]
        active.sort(key=lambda w: w.severity, reverse=True)
        return [w.to_dict() for w in active]

    def get_strength_domains(self, min_rate: float = 0.8,
                              min_attempts: int = 5) -> List[Dict]:
        """Get domains where the brain excels."""
        strengths = []
        for system, domains in self._capabilities.items():
            for domain, cap in domains.items():
                if cap.total_attempts >= min_attempts and cap.success_rate >= min_rate:
                    strengths.append(cap.to_dict())
        strengths.sort(key=lambda s: s['success_rate'], reverse=True)
        return strengths

    def _evict_oldest_capability(self) -> None:
        """Remove the least recently updated capability."""
        oldest_time = float('inf')
        oldest_key = (None, None)
        for system, domains in self._capabilities.items():
            for domain, cap in domains.items():
                if cap.last_updated < oldest_time:
                    oldest_time = cap.last_updated
                    oldest_key = (system, domain)
        if oldest_key[0] is not None:
            del self._capabilities[oldest_key[0]][oldest_key[1]]
            if not self._capabilities[oldest_key[0]]:
                del self._capabilities[oldest_key[0]]

    def _evict_weakest_strategy(self) -> None:
        """Remove strategy with fewest uses."""
        if self._strategies:
            weakest = min(self._strategies.values(), key=lambda s: s.usage_count)
            del self._strategies[weakest.strategy]

    def _evict_weakest_tool(self) -> None:
        """Remove tool with fewest uses."""
        if self._tools:
            weakest = min(self._tools.values(), key=lambda t: t.usage_count)
            del self._tools[weakest.tool]

    def _evict_resolved_weaknesses(self) -> None:
        """Remove oldest resolved weaknesses."""
        resolved = [(k, w) for k, w in self._weaknesses.items() if w.resolved]
        resolved.sort(key=lambda x: x[1].first_detected)
        for key, _ in resolved[:10]:
            del self._weaknesses[key]
        # If still over capacity, remove oldest unresolved with lowest severity
        if len(self._weaknesses) >= self.max_weaknesses:
            active = [(k, w) for k, w in self._weaknesses.items() if not w.resolved]
            active.sort(key=lambda x: x[1].severity)
            if active:
                del self._weaknesses[active[0][0]]

    def get_state(self) -> Dict:
        total_caps = sum(len(d) for d in self._capabilities.values())
        active_weaknesses = [w for w in self._weaknesses.values() if not w.resolved]
        return {
            'total_outcomes': self._total_outcomes,
            'total_successes': self._total_successes,
            'overall_success_rate': round(
                self._total_successes / max(self._total_outcomes, 1), 3
            ),
            'tracked_capabilities': total_caps,
            'tracked_systems': list(self._capabilities.keys()),
            'tracked_strategies': len(self._strategies),
            'tracked_tools': len(self._tools),
            'active_weaknesses': len(active_weaknesses),
            'top_weaknesses': [w.to_dict() for w in
                               sorted(active_weaknesses,
                                      key=lambda w: w.severity, reverse=True)[:5]],
            'strengths': self.get_strength_domains()[:5],
            'preferences': self.get_preferences(),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'SelfModel':
        """Create SelfModel from YAML config dict."""
        section = cfg.get('self_model', {})
        return cls(
            max_capabilities=section.get('max_capabilities', 200),
            max_strategies=section.get('max_strategies', 100),
            max_tools=section.get('max_tools', 50),
            max_weaknesses=section.get('max_weaknesses', 100),
            weakness_auto_resolve_threshold=section.get(
                'weakness_auto_resolve_threshold', 5
            ),
        )


# ─── Agency Model (Seth et al. 2012; Hallett 2007; Safron 2021) ─────────

class AgencyModel:
    """Sense of Agency (SoA) — the experience of controlling one's actions.

    Implements a comparator model: predicted outcomes vs actual outcomes.
    When they match → strong sense of agency. When they diverge → reduced agency.

    Research basis:
    - Seth, Suzuki & Critchley (2012): Interoceptive predictive coding, 950 citations
    - Hallett (2007): Physiology of free will, 109 citations
    - Safron (2021): Embodied Self-Models as agentic controllers, 50 citations
    - Moccia et al. (2023): Intentional binding review, 22 citations
    """

    def __init__(self, prediction_window: int = 50,
                 agency_threshold: float = 0.6):
        self._predictions: deque = deque(maxlen=prediction_window)
        self._outcomes: deque = deque(maxlen=prediction_window)
        self._agency_history: deque = deque(maxlen=200)
        self._agency_threshold = agency_threshold
        self._baseline_agency: float = 0.7
        self._current_agency: float = 0.7
        self._total_actions: int = 0
        self._matched_actions: int = 0
        self._voluntary_count: int = 0
        self._involuntary_count: int = 0

    def predict_outcome(self, action_id: str, predicted_result: str,
                        confidence: float = 0.7) -> Dict[str, Any]:
        """Register a predicted outcome before action execution.

        This is the efference copy — what we EXPECT to happen.
        """
        confidence = max(0.0, min(1.0, confidence))
        prediction = {
            'action_id': action_id,
            'predicted_result': predicted_result,
            'confidence': confidence,
            'timestamp': time.time(),
            'resolved': False
        }
        self._predictions.append(prediction)
        return {
            'action_id': action_id,
            'prediction_registered': True,
            'confidence': round(confidence, 4)
        }

    def register_outcome(self, action_id: str, actual_result: str,
                         was_voluntary: bool = True) -> Dict[str, Any]:
        """Register actual outcome and compute agency for this action.

        Compares prediction (efference copy) with outcome (reafference).
        Match → high agency. Mismatch → low agency.
        """
        self._total_actions += 1
        if was_voluntary:
            self._voluntary_count += 1
        else:
            self._involuntary_count += 1

        prediction = None
        for p in reversed(list(self._predictions)):
            if p['action_id'] == action_id and not p['resolved']:
                prediction = p
                p['resolved'] = True
                break

        if prediction is None:
            match_score = 0.3 if was_voluntary else 0.1
            agency_for_action = match_score
        else:
            if prediction['predicted_result'] == actual_result:
                match_score = 1.0
                self._matched_actions += 1
            else:
                match_score = 0.2
            agency_for_action = match_score * prediction['confidence']
            if was_voluntary:
                agency_for_action = min(1.0, agency_for_action + 0.2)

        self._outcomes.append({
            'action_id': action_id,
            'actual_result': actual_result,
            'match_score': match_score,
            'agency': agency_for_action,
            'voluntary': was_voluntary,
            'timestamp': time.time()
        })

        self._current_agency = (0.8 * self._current_agency +
                                0.2 * agency_for_action)
        self._agency_history.append({
            'time': time.time(),
            'agency': round(self._current_agency, 4)
        })

        return {
            'action_id': action_id,
            'match_score': round(match_score, 4),
            'agency_for_action': round(agency_for_action, 4),
            'current_agency': round(self._current_agency, 4),
            'was_voluntary': was_voluntary,
            'prediction_found': prediction is not None
        }

    def get_sense_of_agency(self) -> Dict[str, Any]:
        """Current sense of agency — am I in control of my actions?

        Returns composite agency score integrating:
        - Prediction accuracy (comparator model)
        - Voluntary action ratio
        - Agency stability over time
        """
        if self._total_actions == 0:
            return {
                'agency_score': round(self._baseline_agency, 4),
                'prediction_accuracy': 0.0,
                'voluntary_ratio': 1.0,
                'agency_stability': 0.5,
                'agency_level': 'baseline',
                'total_actions': 0
            }

        pred_accuracy = (self._matched_actions / max(1, self._total_actions))
        vol_ratio = (self._voluntary_count / max(1, self._total_actions))

        if len(self._agency_history) >= 5:
            recent = list(self._agency_history)[-20:]
            mean_a = sum(r['agency'] for r in recent) / len(recent)
            var_a = sum((r['agency'] - mean_a)**2 for r in recent) / len(recent)
            stability = max(0.0, 1.0 - math.sqrt(var_a) * 2)
        else:
            stability = 0.5

        if self._current_agency > 0.8:
            level = 'strong_agency'
        elif self._current_agency > 0.5:
            level = 'moderate_agency'
        elif self._current_agency > 0.3:
            level = 'weak_agency'
        else:
            level = 'loss_of_agency'

        return {
            'agency_score': round(self._current_agency, 4),
            'prediction_accuracy': round(pred_accuracy, 4),
            'voluntary_ratio': round(vol_ratio, 4),
            'agency_stability': round(stability, 4),
            'agency_level': level,
            'total_actions': self._total_actions
        }

    def detect_agency_disruption(self) -> Dict[str, Any]:
        """Detect if agency is disrupted — similar to depersonalization.

        Inspired by Moccia et al. (2023) on IB disruptions in neuropsychiatric
        disorders. Low agency may indicate need for intervention.
        """
        soa = self.get_sense_of_agency()
        disrupted = soa['agency_score'] < self._agency_threshold
        severity = max(0.0, self._agency_threshold - soa['agency_score'])

        if len(self._agency_history) >= 10:
            recent = list(self._agency_history)[-10:]
            trend = recent[-1]['agency'] - recent[0]['agency']
            declining = trend < -0.15
        else:
            trend = 0.0
            declining = False

        return {
            'disrupted': disrupted,
            'severity': round(severity, 4),
            'declining': declining,
            'trend': round(trend, 4),
            'current_agency': soa['agency_score'],
            'should_intervene': disrupted and declining
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'sense_of_agency': self.get_sense_of_agency(),
            'disruption': self.detect_agency_disruption(),
            'total_predictions': len(self._predictions),
            'total_outcomes': len(self._outcomes),
            'baseline_agency': self._baseline_agency
        }


# ─── P6.77: Autobiographic Memory ────────────────────────────────────────

class MilestoneCategory(Enum):
    """Categories of autobiographic milestones."""
    FIRST_SUCCESS = "first_success"       # First time succeeding at something
    INTEGRATION = "integration"           # New subsystem wired in
    LEARNING = "learning"                 # Significant learning event
    FAILURE_RECOVERY = "failure_recovery" # Recovered from a significant failure
    USER_PRAISE = "user_praise"           # Positive user feedback
    CAPABILITY_GAIN = "capability_gain"   # New capability unlocked
    PERFORMANCE = "performance"           # Performance milestone (e.g. 1000th task)
    SYSTEM_EVENT = "system_event"         # System-level event (startup, upgrade)


@dataclass
class Milestone:
    """A significant event in the brain's development."""
    event: str
    category: MilestoneCategory
    emotional_valence: float = 0.5       # 0 = negative, 0.5 = neutral, 1 = positive
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        self.emotional_valence = max(0.0, min(1.0, self.emotional_valence))

    def to_dict(self) -> Dict:
        return {
            'event': self.event,
            'category': self.category.value,
            'emotional_valence': round(self.emotional_valence, 3),
            'timestamp': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass
class DailySummary:
    """Summary of a day's activities."""
    date_str: str                         # YYYY-MM-DD
    tasks_completed: int = 0
    success_rate: float = 0.0
    highlights: List[str] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        return {
            'date': self.date_str,
            'tasks_completed': self.tasks_completed,
            'success_rate': round(self.success_rate, 3),
            'highlights': self.highlights[:5],
        }


class AutobiographicMemory:
    """
    P6.77: Long-term memory of the brain's own development.

    Records significant milestones, daily summaries, and can produce
    a narrative of its own growth. This gives Tahlamus a sense of
    personal history and developmental trajectory.

    Integration points:
    - AgentLoop calls record_milestone() on significant events
    - Heartbeat calls record_daily_summary() at end of day
    - Language center queries get_narrative() for self-description
    - Dashboard displays milestones on a timeline
    """

    def __init__(self, max_milestones: int = 500,
                 max_daily_summaries: int = 365):
        """
        Args:
            max_milestones: Maximum milestones to retain
            max_daily_summaries: Maximum daily summaries to retain
        """
        self.max_milestones = max_milestones
        self.max_daily_summaries = max_daily_summaries

        self._milestones: deque = deque(maxlen=max_milestones)
        self._daily_summaries: deque = deque(maxlen=max_daily_summaries)

        # Track "firsts" to avoid duplicating first-success milestones
        self._firsts: set = set()

        # Statistics
        self._total_milestones: int = 0
        self._total_summaries: int = 0

    def record_milestone(self, event: str, category: str,
                         emotional_valence: float = 0.5,
                         metadata: Optional[Dict] = None) -> Milestone:
        """
        Record a significant milestone in the brain's development.

        Args:
            event: Description of the milestone (e.g. "First successful Docker deployment")
            category: Category string matching MilestoneCategory values
            emotional_valence: 0 (very negative) to 1 (very positive)
            metadata: Optional additional data

        Returns:
            The created Milestone
        """
        # Parse category
        try:
            cat = MilestoneCategory(category)
        except ValueError:
            cat = MilestoneCategory.SYSTEM_EVENT
            logger.warning(f"Unknown milestone category '{category}', "
                           f"defaulting to system_event")

        milestone = Milestone(
            event=event,
            category=cat,
            emotional_valence=emotional_valence,
            metadata=metadata or {},
        )

        self._milestones.append(milestone)
        self._total_milestones += 1

        logger.info(f"Milestone recorded: [{cat.value}] {event} "
                    f"(valence={emotional_valence:.2f})")

        return milestone

    def record_first(self, event: str, domain: str,
                     emotional_valence: float = 0.8) -> Optional[Milestone]:
        """
        Record a "first time" milestone, only if not already recorded.

        Args:
            event: Description of the first-time event
            domain: Domain key to prevent duplicate firsts
            emotional_valence: Typically high (0.7-1.0) for firsts

        Returns:
            Milestone if this was truly a first, None if already recorded
        """
        key = f"first:{domain}"
        if key in self._firsts:
            return None

        self._firsts.add(key)
        return self.record_milestone(
            event=event,
            category=MilestoneCategory.FIRST_SUCCESS.value,
            emotional_valence=emotional_valence,
            metadata={'domain': domain, 'is_first': True},
        )

    def record_daily_summary(self, tasks_completed: int,
                              success_rate: float,
                              highlights: Optional[List[str]] = None) -> DailySummary:
        """
        Record a daily summary of activities.

        Args:
            tasks_completed: Number of tasks completed today
            success_rate: Overall success rate for the day (0-1)
            highlights: List of notable accomplishments

        Returns:
            The created DailySummary
        """
        import datetime
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')

        summary = DailySummary(
            date_str=date_str,
            tasks_completed=tasks_completed,
            success_rate=success_rate,
            highlights=highlights or [],
        )

        self._daily_summaries.append(summary)
        self._total_summaries += 1

        logger.info(f"Daily summary recorded: {date_str} - "
                    f"{tasks_completed} tasks, {success_rate:.0%} success")

        return summary

    def get_narrative(self, period: str = 'all') -> str:
        """
        Generate a story-like narrative of the brain's development.

        Args:
            period: 'all', 'recent' (last 7 days), or 'today'

        Returns:
            Human-readable narrative text
        """
        milestones = list(self._milestones)
        summaries = list(self._daily_summaries)

        if period == 'today':
            import datetime
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            cutoff = time.time() - 86400
            milestones = [m for m in milestones if m.timestamp > cutoff]
            summaries = [s for s in summaries if s.date_str == today]
        elif period == 'recent':
            cutoff = time.time() - 7 * 86400
            milestones = [m for m in milestones if m.timestamp > cutoff]
            summaries = list(summaries)[-7:]

        if not milestones and not summaries:
            return "No recorded history yet. The journey is just beginning."

        # Build narrative
        parts = []
        parts.append("=== Development Narrative ===\n")

        # Opening statement
        if self._total_milestones > 0:
            parts.append(
                f"Over the course of my development, I have recorded "
                f"{self._total_milestones} milestone(s) and "
                f"{self._total_summaries} daily summary(ies).\n"
            )

        # Key milestones by category
        by_category: Dict[str, List[Milestone]] = defaultdict(list)
        for m in milestones:
            by_category[m.category.value].append(m)

        if MilestoneCategory.FIRST_SUCCESS.value in by_category:
            firsts = by_category[MilestoneCategory.FIRST_SUCCESS.value]
            parts.append("Firsts:")
            for m in firsts:
                parts.append(f"  - {m.event}")

        if MilestoneCategory.CAPABILITY_GAIN.value in by_category:
            gains = by_category[MilestoneCategory.CAPABILITY_GAIN.value]
            parts.append("\nCapabilities gained:")
            for m in gains:
                parts.append(f"  - {m.event}")

        if MilestoneCategory.LEARNING.value in by_category:
            learnings = by_category[MilestoneCategory.LEARNING.value]
            parts.append("\nLearning milestones:")
            for m in learnings:
                parts.append(f"  - {m.event}")

        if MilestoneCategory.FAILURE_RECOVERY.value in by_category:
            recoveries = by_category[MilestoneCategory.FAILURE_RECOVERY.value]
            parts.append("\nChallenges overcome:")
            for m in recoveries:
                parts.append(f"  - {m.event}")

        # Remaining categories
        shown_categories = {
            MilestoneCategory.FIRST_SUCCESS.value,
            MilestoneCategory.CAPABILITY_GAIN.value,
            MilestoneCategory.LEARNING.value,
            MilestoneCategory.FAILURE_RECOVERY.value,
        }
        for cat, ms in by_category.items():
            if cat not in shown_categories:
                parts.append(f"\n{cat.replace('_', ' ').title()}:")
                for m in ms:
                    parts.append(f"  - {m.event}")

        # Recent summaries
        if summaries:
            recent = summaries[-3:]
            parts.append("\nRecent activity:")
            for s in recent:
                parts.append(
                    f"  {s.date_str}: {s.tasks_completed} tasks, "
                    f"{s.success_rate:.0%} success"
                )
                if s.highlights:
                    for h in s.highlights[:2]:
                        parts.append(f"    - {h}")

        # Emotional tone
        if milestones:
            avg_valence = sum(m.emotional_valence for m in milestones) / len(milestones)
            if avg_valence > 0.7:
                parts.append("\nOverall trajectory: Positive growth and development.")
            elif avg_valence > 0.4:
                parts.append("\nOverall trajectory: Steady progress with mixed experiences.")
            else:
                parts.append("\nOverall trajectory: Challenging period requiring resilience.")

        return '\n'.join(parts)

    def get_milestones(self, min_valence: float = 0.0) -> List[Dict]:
        """
        Get milestones sorted by emotional valence (highest first).

        Args:
            min_valence: Minimum valence threshold (0-1)

        Returns:
            List of milestone dicts
        """
        filtered = [m for m in self._milestones
                    if m.emotional_valence >= min_valence]
        filtered.sort(key=lambda m: m.emotional_valence, reverse=True)
        return [m.to_dict() for m in filtered]

    def get_recent_milestones(self, n: int = 10) -> List[Dict]:
        """Get the most recent milestones."""
        recent = list(self._milestones)[-n:]
        recent.reverse()
        return [m.to_dict() for m in recent]

    def get_state(self) -> Dict:
        milestones = list(self._milestones)
        avg_valence = 0.0
        if milestones:
            avg_valence = sum(m.emotional_valence for m in milestones) / len(milestones)

        # Category distribution
        by_cat: Dict[str, int] = defaultdict(int)
        for m in milestones:
            by_cat[m.category.value] += 1

        return {
            'total_milestones': self._total_milestones,
            'total_daily_summaries': self._total_summaries,
            'buffer_milestones': len(milestones),
            'buffer_summaries': len(self._daily_summaries),
            'firsts_recorded': len(self._firsts),
            'avg_emotional_valence': round(avg_valence, 3),
            'category_distribution': dict(by_cat),
            'recent_milestones': self.get_recent_milestones(5),
        }


# ─── Identity Narrative (Smallwood & Schooler 2014; Simony 2016) ─────────

class IdentityNarrative:
    """Coherent self-story constructed from autobiographic events.

    The narrative self is WHO you are across time — a temporally extended
    identity that integrates past experiences, current state, and future goals
    into a coherent story.

    Research basis:
    - Smallwood & Schooler (2014): Mind-wandering as self-narrative engine, 1657 citations
    - Simony et al. (2016): DMN reconfiguration during narrative, 662 citations
    - Vago & Silbersweig (2012): S-ART framework, 1275 citations
    """

    def __init__(self, max_themes: int = 20, coherence_window: int = 50):
        self._life_themes: Dict[str, Dict[str, Any]] = {}
        self._identity_statements: deque = deque(maxlen=100)
        self._coherence_history: deque = deque(maxlen=200)
        self._max_themes = max_themes
        self._coherence_window = coherence_window
        self._self_concept: Dict[str, float] = {
            'competence': 0.5,
            'warmth': 0.5,
            'autonomy': 0.5,
            'growth': 0.5,
            'resilience': 0.5,
        }

    def integrate_experience(self, event: str, domain: str,
                              valence: float, significance: float = 0.5
                              ) -> Dict[str, Any]:
        """Integrate a new experience into the narrative self.

        Significant events update life themes and self-concept.
        """
        significance = max(0.0, min(1.0, significance))
        valence = max(-1.0, min(1.0, valence))

        if domain not in self._life_themes:
            if len(self._life_themes) >= self._max_themes:
                oldest = min(self._life_themes,
                             key=lambda k: self._life_themes[k].get('last_updated', 0))
                del self._life_themes[oldest]
            self._life_themes[domain] = {
                'event_count': 0, 'avg_valence': 0.0,
                'significance_sum': 0.0, 'last_updated': time.time(),
                'narrative_thread': ''
            }

        theme = self._life_themes[domain]
        n = theme['event_count']
        theme['avg_valence'] = (theme['avg_valence'] * n + valence) / (n + 1)
        theme['event_count'] = n + 1
        theme['significance_sum'] += significance
        theme['last_updated'] = time.time()

        if significance > 0.7:
            theme['narrative_thread'] = event

        if significance > 0.5:
            self._update_self_concept(domain, valence, significance)

        return {
            'integrated': True,
            'domain': domain,
            'theme_strength': round(theme['significance_sum'] / max(1, theme['event_count']), 4),
            'self_concept': dict(self._self_concept)
        }

    def _update_self_concept(self, domain: str, valence: float,
                              significance: float) -> None:
        """Update self-concept dimensions based on experience."""
        delta = valence * significance * 0.05

        if domain in ('task', 'coding', 'analysis', 'problem_solving'):
            self._self_concept['competence'] = max(0, min(1,
                self._self_concept['competence'] + delta))
        elif domain in ('social', 'communication', 'user_interaction'):
            self._self_concept['warmth'] = max(0, min(1,
                self._self_concept['warmth'] + delta))
        elif domain in ('decision', 'initiative', 'planning'):
            self._self_concept['autonomy'] = max(0, min(1,
                self._self_concept['autonomy'] + delta))
        elif domain in ('learning', 'exploration', 'curiosity'):
            self._self_concept['growth'] = max(0, min(1,
                self._self_concept['growth'] + delta))

        if valence < -0.3 and significance > 0.5:
            self._self_concept['resilience'] = max(0, min(1,
                self._self_concept['resilience'] + 0.02))

    def get_identity_summary(self) -> Dict[str, Any]:
        """Who am I? — A narrative summary of self-identity."""
        top_themes = sorted(
            self._life_themes.items(),
            key=lambda x: x[1]['significance_sum'],
            reverse=True
        )[:5]

        strengths = [k for k, v in self._self_concept.items() if v > 0.6]
        growth_areas = [k for k, v in self._self_concept.items() if v < 0.4]

        return {
            'self_concept': dict(self._self_concept),
            'core_themes': [{'domain': d, 'strength': round(t['significance_sum'], 3),
                            'valence': round(t['avg_valence'], 3)}
                           for d, t in top_themes],
            'strengths': strengths,
            'growth_areas': growth_areas,
            'theme_count': len(self._life_themes),
            'identity_coherence': self._compute_coherence()
        }

    def _compute_coherence(self) -> float:
        """How coherent is the self-narrative? High = consistent identity."""
        if not self._life_themes:
            return 0.5

        valences = [t['avg_valence'] for t in self._life_themes.values()
                    if t['event_count'] > 0]
        if len(valences) < 2:
            return 0.5

        mean_v = sum(valences) / len(valences)
        variance = sum((v - mean_v)**2 for v in valences) / len(valences)
        coherence = max(0.0, 1.0 - math.sqrt(variance))

        concept_values = list(self._self_concept.values())
        concept_variance = sum((v - sum(concept_values)/len(concept_values))**2
                              for v in concept_values) / len(concept_values)
        concept_coherence = max(0.0, 1.0 - math.sqrt(concept_variance) * 2)

        return round((coherence + concept_coherence) / 2, 4)

    def get_state(self) -> Dict[str, Any]:
        return self.get_identity_summary()


# ─── P6.78: Value System ─────────────────────────────────────────────────

@dataclass
class ValueAssessment:
    """Result of evaluating an action against the value system."""
    action: str
    overall_score: float              # 0-1, how aligned with values
    concerns: List[str]               # Specific concerns raised
    supporting_values: List[str]      # Values that support this action
    conflicting_values: List[str]     # Values that oppose this action
    risk_adjusted_score: float = 0.0  # Score after risk adjustment
    recommendation: str = ""          # "proceed", "caution", "reconsider"

    def __post_init__(self):
        if not self.recommendation:
            if self.risk_adjusted_score >= 0.7:
                self.recommendation = "proceed"
            elif self.risk_adjusted_score >= 0.4:
                self.recommendation = "caution"
            else:
                self.recommendation = "reconsider"

    def to_dict(self) -> Dict:
        return {
            'action': self.action[:200],
            'overall_score': round(self.overall_score, 3),
            'risk_adjusted_score': round(self.risk_adjusted_score, 3),
            'recommendation': self.recommendation,
            'concerns': self.concerns,
            'supporting_values': self.supporting_values,
            'conflicting_values': self.conflicting_values,
        }


# Goal type to value mapping for priority weighting
GOAL_VALUE_MAPPING: Dict[str, List[str]] = {
    'reliability': ['reliability', 'caution'],
    'fix': ['reliability', 'helpfulness'],
    'deploy': ['reliability', 'caution'],
    'explore': ['growth', 'transparency'],
    'learn': ['growth', 'transparency'],
    'optimize': ['reliability', 'growth'],
    'monitor': ['reliability', 'transparency'],
    'help': ['helpfulness', 'transparency'],
    'explain': ['transparency', 'helpfulness'],
    'experiment': ['growth', 'caution'],
    'automate': ['helpfulness', 'growth'],
    'refactor': ['reliability', 'growth'],
    'test': ['reliability', 'caution'],
    'document': ['transparency', 'helpfulness'],
}

# Risk keywords for action evaluation
RISK_KEYWORDS: Dict[str, float] = {
    'delete': 0.8,
    'remove': 0.6,
    'drop': 0.9,
    'format': 0.9,
    'overwrite': 0.7,
    'force': 0.6,
    'shutdown': 0.7,
    'restart': 0.5,
    'modify': 0.4,
    'deploy': 0.5,
    'production': 0.6,
    'execute': 0.3,
    'install': 0.4,
    'upgrade': 0.5,
    'migrate': 0.6,
    'rollback': 0.5,
}


class ValueSystem:
    """
    P6.78: Explicit values that influence decision-making.

    Tahlamus has core values that shape its behavior:
    - reliability: Prefer safe, tested approaches
    - transparency: Explain reasoning, don't hide problems
    - caution: Be careful with destructive or risky actions
    - helpfulness: Prioritize user needs
    - growth: Seek improvement and learning opportunities

    Values influence:
    - Goal prioritization (via get_priority_weight)
    - Action evaluation (via evaluate_action)
    - Communication style (via get_value_instructions)

    Integration points:
    - SafetyGovernor queries evaluate_action() for value-based checks
    - GoalPrioritizer queries get_priority_weight() for goal ordering
    - Language center queries get_value_instructions() for LLM prompts
    """

    DEFAULT_VALUES: Dict[str, float] = {
        'reliability': 0.95,
        'transparency': 0.90,
        'caution': 0.80,
        'helpfulness': 0.85,
        'growth': 0.70,
    }

    def __init__(self, values: Optional[Dict[str, float]] = None,
                 min_value: float = 0.0, max_value: float = 1.0):
        """
        Args:
            values: Initial value weights (0-1), defaults provided
            min_value: Minimum allowed value weight
            max_value: Maximum allowed value weight
        """
        self.min_value = min_value
        self.max_value = max_value

        # Initialize with defaults, then overlay provided values
        self._values: Dict[str, float] = dict(self.DEFAULT_VALUES)
        if values:
            for k, v in values.items():
                self._values[k] = max(min_value, min(max_value, v))

        # Track value adjustments
        self._adjustment_history: deque = deque(maxlen=200)
        self._total_evaluations: int = 0
        self._total_adjustments: int = 0

    def evaluate_action(self, action_description: str,
                        risk_level: float = 0.5) -> ValueAssessment:
        """
        Evaluate an action against the value system.

        Args:
            action_description: What the action does
            risk_level: 0 (safe) to 1 (very risky)

        Returns:
            ValueAssessment with score, concerns, and recommendation
        """
        self._total_evaluations += 1
        action_lower = action_description.lower()

        supporting = []
        conflicting = []
        concerns = []

        # ── Check each value ──

        # Reliability: penalize risky, reward tested/safe
        if risk_level > 0.6:
            conflicting.append('reliability')
            concerns.append(
                f"High risk ({risk_level:.0%}) conflicts with "
                f"reliability value ({self._values['reliability']:.0%})"
            )
        elif risk_level < 0.3:
            supporting.append('reliability')

        # Caution: penalize destructive keywords
        detected_risk = 0.0
        for keyword, weight in RISK_KEYWORDS.items():
            if keyword in action_lower:
                detected_risk = max(detected_risk, weight)

        if detected_risk > 0.5:
            conflicting.append('caution')
            concerns.append(
                f"Detected risky keyword(s) in action "
                f"(risk={detected_risk:.0%})"
            )
        else:
            supporting.append('caution')

        # Helpfulness: reward user-facing, helping keywords
        helpful_keywords = ['help', 'fix', 'solve', 'assist', 'respond',
                            'answer', 'explain', 'support']
        if any(kw in action_lower for kw in helpful_keywords):
            supporting.append('helpfulness')
        else:
            # Not conflicting, just neutral
            pass

        # Growth: reward learning, exploration keywords
        growth_keywords = ['learn', 'explore', 'improve', 'optimize',
                           'experiment', 'practice', 'discover', 'analyze']
        if any(kw in action_lower for kw in growth_keywords):
            supporting.append('growth')

        # Transparency: reward explicit, explain keywords
        transparency_keywords = ['explain', 'log', 'report', 'document',
                                  'describe', 'show', 'clarify', 'trace']
        if any(kw in action_lower for kw in transparency_keywords):
            supporting.append('transparency')

        # ── Compute scores ──

        # Base score from value alignment
        support_weight = sum(self._values.get(v, 0.5) for v in supporting)
        conflict_weight = sum(self._values.get(v, 0.5) for v in conflicting)

        if supporting or conflicting:
            total_weight = support_weight + conflict_weight
            overall_score = support_weight / max(total_weight, 0.01)
        else:
            overall_score = 0.5  # Neutral if no values triggered

        # Risk adjustment
        caution_value = self._values.get('caution', 0.8)
        risk_penalty = risk_level * caution_value
        risk_adjusted = max(0.0, overall_score - risk_penalty * 0.5)

        # Additional risk from detected keywords
        if detected_risk > 0:
            keyword_penalty = detected_risk * caution_value * 0.3
            risk_adjusted = max(0.0, risk_adjusted - keyword_penalty)

        assessment = ValueAssessment(
            action=action_description,
            overall_score=overall_score,
            concerns=concerns,
            supporting_values=supporting,
            conflicting_values=conflicting,
            risk_adjusted_score=risk_adjusted,
        )

        return assessment

    def get_priority_weight(self, goal_type: str) -> float:
        """
        Get a priority weight for a goal type based on values.

        Args:
            goal_type: Type of goal (e.g. 'fix', 'explore', 'deploy')

        Returns:
            Float weight (0-1) for prioritization
        """
        goal_lower = goal_type.lower()

        # Check exact match first
        relevant_values = GOAL_VALUE_MAPPING.get(goal_lower, [])

        # Fuzzy match: check if goal_type contains any mapped key
        if not relevant_values:
            for key, values in GOAL_VALUE_MAPPING.items():
                if key in goal_lower:
                    relevant_values = values
                    break

        if not relevant_values:
            # Unknown goal type: use average of all values
            return round(sum(self._values.values()) / len(self._values), 3)

        # Weight is the average of relevant values
        weight = sum(self._values.get(v, 0.5) for v in relevant_values) / len(relevant_values)
        return round(weight, 3)

    def adjust_value(self, name: str, delta: float) -> bool:
        """
        Adjust a value by delta, clamped to [min_value, max_value].

        Args:
            name: Value name (e.g. 'caution', 'growth')
            delta: Change amount (positive or negative)

        Returns:
            True if value existed and was adjusted
        """
        if name not in self._values:
            logger.warning(f"Unknown value '{name}' — cannot adjust")
            return False

        old = self._values[name]
        new = max(self.min_value, min(self.max_value, old + delta))
        self._values[name] = new

        self._adjustment_history.append({
            'value': name,
            'old': round(old, 3),
            'new': round(new, 3),
            'delta': round(delta, 3),
            'timestamp': time.time(),
        })
        self._total_adjustments += 1

        logger.info(f"Value '{name}' adjusted: {old:.3f} -> {new:.3f} "
                    f"(delta={delta:+.3f})")
        return True

    def get_value(self, name: str) -> float:
        """Get current weight for a specific value."""
        return self._values.get(name, 0.5)

    def get_all_values(self) -> Dict[str, float]:
        """Get all current values."""
        return {k: round(v, 3) for k, v in self._values.items()}

    def get_value_instructions(self) -> str:
        """
        Generate value-aware instructions for LLM prompt injection.

        Similar to PersonalityModel.get_style_instructions().
        """
        instructions = []

        if self._values.get('reliability', 0) > 0.8:
            instructions.append(
                "Prioritize reliability and correctness over speed."
            )
        if self._values.get('transparency', 0) > 0.8:
            instructions.append(
                "Always explain your reasoning and be transparent about uncertainties."
            )
        if self._values.get('caution', 0) > 0.7:
            instructions.append(
                "Be cautious with potentially destructive operations. "
                "Verify before executing risky actions."
            )
        if self._values.get('helpfulness', 0) > 0.8:
            instructions.append(
                "Focus on being helpful and addressing the user's actual needs."
            )
        if self._values.get('growth', 0) > 0.6:
            instructions.append(
                "Look for learning opportunities and suggest improvements."
            )

        return ' '.join(instructions) if instructions else \
            "Act responsibly and helpfully."

    def get_state(self) -> Dict:
        recent_adjustments = list(self._adjustment_history)[-5:]
        return {
            'values': self.get_all_values(),
            'total_evaluations': self._total_evaluations,
            'total_adjustments': self._total_adjustments,
            'recent_adjustments': recent_adjustments,
            'value_instructions': self.get_value_instructions(),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'ValueSystem':
        """Create ValueSystem from YAML config dict."""
        section = cfg.get('value_system', {})

        values = {}
        values_cfg = section.get('values', {})
        for name in cls.DEFAULT_VALUES:
            if name in values_cfg:
                values[name] = values_cfg[name]

        # Also allow custom values
        for name, val in values_cfg.items():
            if name not in values:
                values[name] = val

        return cls(
            values=values if values else None,
            min_value=section.get('min_value', 0.0),
            max_value=section.get('max_value', 1.0),
        )


# ─── Moral Conscience (Greene 2001; Moll 2005; Van Overwalle 2008) ──────

class MoralConscience:
    """Moral emotion generation and value conflict resolution.

    Implements dual-process moral cognition:
    - Fast emotional path (vmPFC/amygdala) → gut moral feelings
    - Slow rational path (dlPFC) → reasoned moral judgment

    Research basis:
    - Greene et al. (2001): Dual-process moral judgment
    - Moll et al. (2005): Neural correlates of moral sensitivity
    - Van Overwalle (2008): Social cognition meta-analysis, 1781 citations
    """

    MORAL_EMOTIONS = {
        'guilt': {'valence': -0.7, 'arousal': 0.4, 'self_directed': True},
        'shame': {'valence': -0.8, 'arousal': 0.5, 'self_directed': True},
        'pride': {'valence': 0.7, 'arousal': 0.5, 'self_directed': True},
        'compassion': {'valence': 0.3, 'arousal': 0.3, 'self_directed': False},
        'indignation': {'valence': -0.6, 'arousal': 0.7, 'self_directed': False},
        'gratitude': {'valence': 0.8, 'arousal': 0.3, 'self_directed': False},
    }

    def __init__(self, value_system: Optional['ValueSystem'] = None):
        self._value_system = value_system
        self._moral_history: deque = deque(maxlen=200)
        self._guilt_accumulator: float = 0.0
        self._pride_accumulator: float = 0.0
        self._conflicts_resolved: int = 0
        self._integrity_score: float = 0.8

    def evaluate_moral_weight(self, action: str,
                               affected_values: Dict[str, float]
                               ) -> Dict[str, Any]:
        """Generate moral emotions for an action based on value alignment.

        Args:
            action: Description of the action
            affected_values: Dict mapping value names to impact scores (-1 to +1)
                            Positive = supports that value, negative = violates

        Returns:
            Moral assessment with emotional response
        """
        violations = {k: v for k, v in affected_values.items() if v < -0.1}
        affirmations = {k: v for k, v in affected_values.items() if v > 0.1}

        moral_emotions = []
        overall_moral_score = 0.0

        for value, impact in violations.items():
            weight = 1.0
            if self._value_system:
                weight = self._value_system.get_value(value)
            severity = abs(impact) * weight
            if severity > 0.5:
                moral_emotions.append({
                    'emotion': 'guilt',
                    'intensity': round(min(1.0, severity), 4),
                    'trigger': f'violation of {value}',
                    'value_weight': round(weight, 3)
                })
                self._guilt_accumulator += severity * 0.1
            overall_moral_score -= severity

        for value, impact in affirmations.items():
            weight = 1.0
            if self._value_system:
                weight = self._value_system.get_value(value)
            strength = impact * weight
            if strength > 0.5:
                moral_emotions.append({
                    'emotion': 'pride',
                    'intensity': round(min(1.0, strength), 4),
                    'trigger': f'affirmation of {value}',
                    'value_weight': round(weight, 3)
                })
                self._pride_accumulator += strength * 0.1
            overall_moral_score += strength

        overall_moral_score = max(-1.0, min(1.0, overall_moral_score))
        self._integrity_score = (0.95 * self._integrity_score +
                                 0.05 * (overall_moral_score + 1) / 2)

        self._moral_history.append({
            'time': time.time(),
            'action': action,
            'score': round(overall_moral_score, 4),
            'emotions': moral_emotions
        })

        return {
            'action': action,
            'moral_score': round(overall_moral_score, 4),
            'moral_emotions': moral_emotions,
            'violations': list(violations.keys()),
            'affirmations': list(affirmations.keys()),
            'integrity_score': round(self._integrity_score, 4)
        }

    def resolve_value_conflict(self, value_a: str, value_b: str,
                                context: str = '') -> Dict[str, Any]:
        """Resolve a conflict between two competing values.

        Uses value hierarchy + moral emotion intensity to decide.
        """
        weight_a = 0.5
        weight_b = 0.5
        if self._value_system:
            weight_a = self._value_system.get_value(value_a)
            weight_b = self._value_system.get_value(value_b)

        winner = value_a if weight_a >= weight_b else value_b
        margin = abs(weight_a - weight_b)

        if margin < 0.1:
            confidence = 'low'
            resolution = 'compromise'
        elif margin < 0.3:
            confidence = 'moderate'
            resolution = 'lean_toward'
        else:
            confidence = 'high'
            resolution = 'clear_priority'

        self._conflicts_resolved += 1

        return {
            'value_a': value_a,
            'weight_a': round(weight_a, 4),
            'value_b': value_b,
            'weight_b': round(weight_b, 4),
            'winner': winner,
            'margin': round(margin, 4),
            'confidence': confidence,
            'resolution': resolution,
            'context': context,
            'conflicts_resolved_total': self._conflicts_resolved
        }

    def get_moral_health(self) -> Dict[str, Any]:
        """Overall moral health — conscience status."""
        chronic_guilt = self._guilt_accumulator > 1.0
        self._guilt_accumulator *= 0.95
        self._pride_accumulator *= 0.95

        return {
            'integrity_score': round(self._integrity_score, 4),
            'guilt_level': round(min(1.0, self._guilt_accumulator), 4),
            'pride_level': round(min(1.0, self._pride_accumulator), 4),
            'chronic_guilt': chronic_guilt,
            'moral_decisions_made': len(self._moral_history),
            'conflicts_resolved': self._conflicts_resolved
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'moral_health': self.get_moral_health(),
            'recent_decisions': [h for h in list(self._moral_history)[-5:]]
        }

"""
User Relationship System (V2 PHASE 6: P6.82-85)

P6.82: UserModel
  - Tracks user preferences (technical vs simple, verbose vs brief)
  - Work patterns: active hours, active days
  - Per-domain expertise level (beginner/intermediate/advanced/expert)
  - Communication style: direct/indirect, language, detail level

P6.83: TrustModel
  - Bidirectional trust tracking (user trust in system, system trust in user)
  - Approval rate, feedback tone, task complexity signals
  - Instruction clarity, consistency of user commands
  - Trust drives autonomy: high trust = more autonomy, low trust = more questions

P6.84: CollaborationPatterns
  - Learns when user wants detailed reports vs just results
  - Context-sensitive notification preferences
  - Proactive alert thresholds per event type/severity

P6.85: RelationshipHistory
  - Chronicle of collaboration: total tasks, success rate, days together
  - Highlights and lowpoints for honest self-awareness
  - Joint project tracking with outcomes
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.user_relationship')


# ─── P6.82: User Model ──────────────────────────────────────────────────

class ExpertiseLevel(Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


@dataclass
class InteractionRecord:
    """A single recorded interaction with the user."""
    timestamp: float
    domain: str
    complexity: float           # 0-1
    user_feedback_score: Optional[float] = None  # -1 to 1 if provided
    hour_of_day: int = 0
    day_of_week: int = 0       # 0=Monday, 6=Sunday

    def __post_init__(self):
        if self.timestamp > 0:
            import datetime
            dt = datetime.datetime.fromtimestamp(self.timestamp)
            self.hour_of_day = dt.hour
            self.day_of_week = dt.weekday()

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'domain': self.domain,
            'complexity': round(self.complexity, 3),
            'user_feedback_score': round(self.user_feedback_score, 3) if self.user_feedback_score is not None else None,
            'hour_of_day': self.hour_of_day,
            'day_of_week': self.day_of_week,
        }


class UserModel:
    """
    P6.82: Model of user preferences and behavioral patterns.

    Tracks how the user interacts with the system over time to
    build a nuanced understanding of their preferences, expertise,
    work schedule, and communication style.
    """

    EXPERTISE_THRESHOLDS = {
        'beginner': (0.0, 0.3),
        'intermediate': (0.3, 0.6),
        'advanced': (0.6, 0.85),
        'expert': (0.85, 1.0),
    }

    def __init__(self,
                 max_interactions: int = 1000,
                 expertise_window: int = 50,
                 activity_smoothing: float = 0.1):
        self.max_interactions = max_interactions
        self.expertise_window = expertise_window
        self.activity_smoothing = activity_smoothing

        # Interaction history
        self._interactions: deque = deque(maxlen=max_interactions)
        self._total_interactions = 0

        # Preferences (updated incrementally)
        self._preference_technical: float = 0.5   # 0=simple, 1=technical
        self._preference_verbose: float = 0.5     # 0=brief, 1=verbose
        self._preference_direct: float = 0.5      # 0=indirect, 1=direct
        self._preferred_language: str = "en"
        self._preferred_detail_level: str = "standard"  # minimal, standard, detailed

        # Per-domain expertise tracking
        self._domain_complexity: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=expertise_window)
        )
        self._domain_success: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=expertise_window)
        )

        # Activity tracking per hour (24 bins) and day (7 bins)
        self._hourly_activity: List[float] = [0.0] * 24
        self._daily_activity: List[float] = [0.0] * 7
        self._activity_total: float = 0.0

    def record_interaction(self, timestamp: float, domain: str,
                           complexity: float,
                           user_feedback_score: Optional[float] = None) -> None:
        """Record a user interaction for pattern learning."""
        record = InteractionRecord(
            timestamp=timestamp,
            domain=domain,
            complexity=max(0.0, min(1.0, complexity)),
            user_feedback_score=user_feedback_score,
        )
        self._interactions.append(record)
        self._total_interactions += 1

        # Update domain expertise signals
        self._domain_complexity[domain].append(complexity)
        if user_feedback_score is not None:
            success = user_feedback_score > 0.0
            self._domain_success[domain].append(success)

        # Update activity patterns (exponential moving average)
        hour = record.hour_of_day
        day = record.day_of_week
        alpha = self.activity_smoothing
        self._hourly_activity[hour] = (1 - alpha) * self._hourly_activity[hour] + alpha * 1.0
        self._daily_activity[day] = (1 - alpha) * self._daily_activity[day] + alpha * 1.0
        self._activity_total += 1.0

        # Update preference signals from feedback
        if user_feedback_score is not None:
            self._update_preferences_from_feedback(complexity, user_feedback_score)

        logger.debug(
            "Recorded interaction: domain=%s complexity=%.2f hour=%d",
            domain, complexity, hour
        )

    def _update_preferences_from_feedback(self, complexity: float,
                                           feedback: float) -> None:
        """Infer preferences from complexity level and feedback."""
        alpha = 0.05  # Slow adaptation

        # If user gives positive feedback to complex tasks, they prefer technical
        if feedback > 0.3 and complexity > 0.6:
            self._preference_technical = (
                (1 - alpha) * self._preference_technical + alpha * 1.0
            )
        elif feedback > 0.3 and complexity < 0.3:
            self._preference_technical = (
                (1 - alpha) * self._preference_technical + alpha * 0.0
            )

    def set_preference(self, key: str, value: Any) -> None:
        """Explicitly set a user preference."""
        if key == 'technical':
            self._preference_technical = max(0.0, min(1.0, float(value)))
        elif key == 'verbose':
            self._preference_verbose = max(0.0, min(1.0, float(value)))
        elif key == 'direct':
            self._preference_direct = max(0.0, min(1.0, float(value)))
        elif key == 'language':
            self._preferred_language = str(value)
        elif key == 'detail_level':
            if value in ('minimal', 'standard', 'detailed'):
                self._preferred_detail_level = value
        else:
            logger.warning("Unknown preference key: %s", key)

    def get_preferences(self) -> Dict:
        """Get current user preference profile."""
        return {
            'technical_vs_simple': round(self._preference_technical, 3),
            'verbose_vs_brief': round(self._preference_verbose, 3),
            'direct_vs_indirect': round(self._preference_direct, 3),
            'language': self._preferred_language,
            'detail_level': self._preferred_detail_level,
        }

    def get_expertise(self, domain: str) -> str:
        """
        Get estimated expertise level for a domain.

        Based on average task complexity the user handles in that domain
        and their success rate.
        """
        complexities = list(self._domain_complexity.get(domain, []))
        successes = list(self._domain_success.get(domain, []))

        if len(complexities) < 3:
            return ExpertiseLevel.BEGINNER.value

        avg_complexity = sum(complexities) / len(complexities)
        success_rate = sum(successes) / len(successes) if successes else 0.5

        # Expertise = complexity they handle * their success rate
        expertise_score = avg_complexity * (0.5 + 0.5 * success_rate)

        for level, (low, high) in self.EXPERTISE_THRESHOLDS.items():
            if low <= expertise_score < high:
                return level
        return ExpertiseLevel.EXPERT.value

    def get_active_hours(self) -> List[Tuple[int, float]]:
        """
        Get activity level per hour of day.

        Returns list of (hour, activity_level) tuples sorted by activity.
        """
        if self._activity_total < 1.0:
            return [(h, 0.0) for h in range(24)]

        max_val = max(self._hourly_activity) if max(self._hourly_activity) > 0 else 1.0
        result = [
            (h, round(self._hourly_activity[h] / max_val, 3))
            for h in range(24)
        ]
        return result

    def is_likely_active(self) -> bool:
        """
        Check if the user is likely active right now based on patterns.

        Returns True if current hour has above-median activity level.
        """
        if self._activity_total < 5.0:
            # Not enough data, assume active during business hours
            import datetime
            hour = datetime.datetime.now().hour
            return 8 <= hour <= 22

        import datetime
        current_hour = datetime.datetime.now().hour
        current_activity = self._hourly_activity[current_hour]

        sorted_activities = sorted(self._hourly_activity)
        median_idx = len(sorted_activities) // 2
        median_activity = sorted_activities[median_idx]

        return current_activity > median_activity

    def get_state(self) -> Dict:
        """Get full model state."""
        domains = list(self._domain_complexity.keys())
        expertise_map = {d: self.get_expertise(d) for d in domains}

        # Find peak hours (top 5)
        active_hours = self.get_active_hours()
        peak_hours = sorted(active_hours, key=lambda x: x[1], reverse=True)[:5]

        return {
            'total_interactions': self._total_interactions,
            'preferences': self.get_preferences(),
            'domains_tracked': len(domains),
            'domain_expertise': expertise_map,
            'peak_hours': peak_hours,
            'is_likely_active': self.is_likely_active(),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'UserModel':
        """Create UserModel from YAML config."""
        section = cfg.get('user_model', {})
        instance = cls(
            max_interactions=section.get('max_interactions', 1000),
            expertise_window=section.get('expertise_window', 50),
            activity_smoothing=section.get('activity_smoothing', 0.1),
        )
        # Apply initial preferences from config
        prefs = section.get('default_preferences', {})
        if 'technical' in prefs:
            instance._preference_technical = float(prefs['technical'])
        if 'verbose' in prefs:
            instance._preference_verbose = float(prefs['verbose'])
        if 'direct' in prefs:
            instance._preference_direct = float(prefs['direct'])
        if 'language' in prefs:
            instance._preferred_language = str(prefs['language'])
        if 'detail_level' in prefs:
            instance._preferred_detail_level = str(prefs['detail_level'])
        return instance


# ─── P6.83: Trust Model ─────────────────────────────────────────────────

class TrustModel:
    """
    P6.83: Bidirectional trust between system and user.

    user_trust_in_system: How much the user trusts us (derived from
    their approval rate, feedback tone, and task complexity they give us).

    system_trust_in_user: How much we trust the user's instructions
    (derived from instruction clarity and consistency).

    Trust levels modulate autonomy: high trust -> more self-initiated
    actions with higher budgets; low trust -> more questions asked,
    lower risk thresholds.
    """

    def __init__(self,
                 approval_window: int = 100,
                 tone_window: int = 50,
                 clarity_window: int = 50,
                 trust_floor: float = 0.1,
                 trust_ceiling: float = 0.95,
                 autonomy_min: float = 0.5,
                 autonomy_max: float = 2.0):
        self.trust_floor = trust_floor
        self.trust_ceiling = trust_ceiling
        self.autonomy_min = autonomy_min
        self.autonomy_max = autonomy_max

        # User trust signals
        self._approvals: deque = deque(maxlen=approval_window)
        self._feedback_tones: deque = deque(maxlen=tone_window)
        self._task_complexities: deque = deque(maxlen=approval_window)

        # System trust signals
        self._instruction_clarity: deque = deque(maxlen=clarity_window)

        # Computed trust levels (cached, updated on each signal)
        self._user_trust: float = 0.5
        self._system_trust: float = 0.5

        # Counters
        self._total_approvals = 0
        self._total_denials = 0
        self._total_feedback = 0
        self._total_clarity_checks = 0

    def record_approval(self, approved: bool) -> None:
        """Record whether the user approved a proposed action."""
        self._approvals.append(approved)
        if approved:
            self._total_approvals += 1
        else:
            self._total_denials += 1
        self._recompute_user_trust()

    def record_feedback_tone(self, score: float) -> None:
        """
        Record feedback tone from user. Score from -1 (very negative)
        to 1 (very positive).
        """
        score = max(-1.0, min(1.0, score))
        self._feedback_tones.append(score)
        self._total_feedback += 1
        self._recompute_user_trust()

    def record_task_complexity(self, complexity: float) -> None:
        """
        Record complexity of tasks the user gives us.
        Higher complexity tasks = more trust in our capabilities.
        """
        complexity = max(0.0, min(1.0, complexity))
        self._task_complexities.append(complexity)
        self._recompute_user_trust()

    def record_instruction_clarity(self, clear: bool) -> None:
        """
        Record whether user instructions were clear and unambiguous.
        Clear instructions = higher system trust in user.
        """
        self._instruction_clarity.append(clear)
        self._total_clarity_checks += 1
        self._recompute_system_trust()

    def _recompute_user_trust(self) -> None:
        """Recompute user_trust_in_system from signals."""
        signals = []

        # Approval rate (strongest signal)
        approvals = list(self._approvals)
        if approvals:
            approval_rate = sum(1 for a in approvals if a) / len(approvals)
            signals.append(('approval', approval_rate, 0.5))

        # Feedback tone (normalized from [-1,1] to [0,1])
        tones = list(self._feedback_tones)
        if tones:
            avg_tone = sum(tones) / len(tones)
            tone_normalized = (avg_tone + 1.0) / 2.0
            signals.append(('tone', tone_normalized, 0.3))

        # Task complexity (users give harder tasks when they trust)
        complexities = list(self._task_complexities)
        if complexities:
            avg_complexity = sum(complexities) / len(complexities)
            signals.append(('complexity', avg_complexity, 0.2))

        if not signals:
            self._user_trust = 0.5
            return

        # Weighted average
        total_weight = sum(w for _, _, w in signals)
        weighted_sum = sum(val * w for _, val, w in signals)
        raw = weighted_sum / total_weight

        self._user_trust = max(self.trust_floor, min(self.trust_ceiling, raw))

    def _recompute_system_trust(self) -> None:
        """Recompute system_trust_in_user from instruction clarity."""
        clarity_records = list(self._instruction_clarity)
        if not clarity_records:
            self._system_trust = 0.5
            return

        clarity_rate = sum(1 for c in clarity_records if c) / len(clarity_records)
        self._system_trust = max(self.trust_floor, min(self.trust_ceiling, clarity_rate))

    def get_trust_levels(self) -> Dict:
        """Get current bidirectional trust levels."""
        return {
            'user_trust': round(self._user_trust, 3),
            'system_trust': round(self._system_trust, 3),
        }

    def get_autonomy_modifier(self) -> float:
        """
        Get a multiplier for the autonomy budget based on trust.

        High mutual trust -> higher multiplier (up to autonomy_max).
        Low trust -> lower multiplier (down to autonomy_min).
        """
        combined_trust = (self._user_trust * 0.6 + self._system_trust * 0.4)
        modifier = self.autonomy_min + (self.autonomy_max - self.autonomy_min) * combined_trust
        return round(modifier, 3)

    def get_state(self) -> Dict:
        """Get full trust model state."""
        return {
            'user_trust_in_system': round(self._user_trust, 3),
            'system_trust_in_user': round(self._system_trust, 3),
            'autonomy_modifier': self.get_autonomy_modifier(),
            'total_approvals': self._total_approvals,
            'total_denials': self._total_denials,
            'total_feedback': self._total_feedback,
            'total_clarity_checks': self._total_clarity_checks,
            'approval_rate': round(
                self._total_approvals / max(1, self._total_approvals + self._total_denials), 3
            ),
        }


# ─── P6.84: Collaboration Patterns ──────────────────────────────────────

class CollaborationPatterns:
    """
    P6.84: Learns optimal collaboration style with the user.

    Tracks when the user wants detailed information (error reports,
    critical events) vs when they just want results (routine tasks,
    successful completions). Also learns proactive notification
    preferences.
    """

    CONTEXT_TYPES = ('error', 'success', 'routine', 'critical', 'status')
    DETAIL_LEVELS = ('minimal', 'standard', 'detailed')

    def __init__(self, history_window: int = 100,
                 proactive_default: bool = True,
                 severity_threshold: float = 0.6):
        self.proactive_default = proactive_default
        self.severity_threshold = severity_threshold

        # Per context-type: track what detail level the user prefers
        self._detail_preferences: Dict[str, deque] = {
            ct: deque(maxlen=history_window) for ct in self.CONTEXT_TYPES
        }

        # Proactive notification preferences per event type
        self._notification_preferences: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=history_window)
        )

        self._total_preferences_recorded = 0

    def record_preference(self, context_type: str,
                          detail_level_requested: str) -> None:
        """
        Record what detail level the user requested for a context type.

        Args:
            context_type: One of 'error', 'success', 'routine', 'critical', 'status'
            detail_level_requested: One of 'minimal', 'standard', 'detailed'
        """
        if context_type not in self.CONTEXT_TYPES:
            logger.warning("Unknown context type: %s", context_type)
            return
        if detail_level_requested not in self.DETAIL_LEVELS:
            logger.warning("Unknown detail level: %s", detail_level_requested)
            return

        self._detail_preferences[context_type].append(detail_level_requested)
        self._total_preferences_recorded += 1

    def record_notification_feedback(self, event_type: str,
                                      was_wanted: bool) -> None:
        """
        Record whether a proactive notification was appreciated.

        Args:
            event_type: Type of event that triggered the notification
            was_wanted: True if user found the notification useful
        """
        self._notification_preferences[event_type].append(was_wanted)

    def get_recommended_detail_level(self, context_type: str) -> str:
        """
        Get the recommended detail level for a context type.

        Based on majority vote of recent user preferences.
        Falls back to sensible defaults if no data.
        """
        if context_type not in self.CONTEXT_TYPES:
            return 'standard'

        preferences = list(self._detail_preferences.get(context_type, []))
        if not preferences:
            # Sensible defaults
            defaults = {
                'error': 'detailed',
                'success': 'minimal',
                'routine': 'minimal',
                'critical': 'detailed',
                'status': 'standard',
            }
            return defaults.get(context_type, 'standard')

        # Majority vote
        counts = defaultdict(int)
        for pref in preferences:
            counts[pref] += 1
        return max(counts, key=counts.get)

    def should_notify_proactively(self, event_type: str,
                                   severity: float) -> bool:
        """
        Decide whether to send a proactive notification.

        Args:
            event_type: Type of event
            severity: 0-1, how severe/important the event is

        Returns:
            True if the system should proactively notify the user.
        """
        # Always notify for high-severity events
        if severity >= 0.9:
            return True

        # Check learned preferences for this event type
        feedback_history = list(self._notification_preferences.get(event_type, []))
        if feedback_history:
            approval_rate = sum(1 for w in feedback_history if w) / len(feedback_history)
            # Notify if user usually wants these, or if severity is high enough
            if approval_rate > 0.5:
                return True
            if approval_rate < 0.3 and severity < self.severity_threshold:
                return False

        # Default: notify if severity exceeds threshold
        return severity >= self.severity_threshold

    def get_state(self) -> Dict:
        """Get collaboration patterns state."""
        detail_summary = {}
        for ct in self.CONTEXT_TYPES:
            detail_summary[ct] = {
                'recommended': self.get_recommended_detail_level(ct),
                'samples': len(self._detail_preferences.get(ct, [])),
            }

        notification_summary = {}
        for event_type, history in self._notification_preferences.items():
            history_list = list(history)
            if history_list:
                notification_summary[event_type] = {
                    'approval_rate': round(
                        sum(1 for w in history_list if w) / len(history_list), 3
                    ),
                    'samples': len(history_list),
                }

        return {
            'total_preferences_recorded': self._total_preferences_recorded,
            'detail_preferences': detail_summary,
            'notification_preferences': notification_summary,
        }


# ─── P6.85: Relationship History ────────────────────────────────────────

@dataclass
class TaskRecord:
    """A single recorded task in the collaboration history."""
    description: str
    domain: str
    success: bool
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        return {
            'description': self.description[:100],
            'domain': self.domain,
            'success': self.success,
            'timestamp': self.timestamp,
        }


@dataclass
class ProjectRecord:
    """A recorded joint project."""
    name: str
    outcome: str = 'ongoing'  # 'ongoing', 'success', 'failed'
    started_at: float = 0.0
    completed_at: float = 0.0
    task_count: int = 0
    success_count: int = 0

    def __post_init__(self):
        if self.started_at == 0.0:
            self.started_at = time.time()

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'outcome': self.outcome,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'task_count': self.task_count,
            'success_count': self.success_count,
            'success_rate': round(
                self.success_count / max(1, self.task_count), 3
            ),
        }


class RelationshipHistory:
    """
    P6.85: Chronicle of the collaboration between system and user.

    Maintains an honest record of the partnership including total
    tasks completed, success rate, highlights, lowpoints, and
    joint projects with their outcomes.
    """

    def __init__(self, max_tasks: int = 5000, max_projects: int = 100):
        self.max_tasks = max_tasks
        self.max_projects = max_projects

        self._tasks: deque = deque(maxlen=max_tasks)
        self._projects: Dict[str, ProjectRecord] = {}
        self._first_interaction: float = 0.0
        self._total_tasks: int = 0
        self._total_successes: int = 0
        self._domain_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {'total': 0, 'success': 0}
        )

        # Highlights and lowpoints (tracked as notable events)
        self._highlights: List[Dict] = []  # Best moments
        self._lowpoints: List[Dict] = []   # Honest failures
        self._max_notable: int = 20

    def record_task(self, task_desc: str, domain: str, success: bool,
                    timestamp: Optional[float] = None) -> None:
        """Record a completed task."""
        ts = timestamp if timestamp is not None else time.time()

        if self._first_interaction == 0.0:
            self._first_interaction = ts

        record = TaskRecord(
            description=task_desc,
            domain=domain,
            success=success,
            timestamp=ts,
        )
        self._tasks.append(record)
        self._total_tasks += 1
        if success:
            self._total_successes += 1

        # Domain stats
        self._domain_stats[domain]['total'] += 1
        if success:
            self._domain_stats[domain]['success'] += 1

        # Update associated project if any
        for project in self._projects.values():
            if project.outcome == 'ongoing':
                project.task_count += 1
                if success:
                    project.success_count += 1

        # Check for notable events
        self._check_for_highlights(task_desc, domain, success, ts)

    def _check_for_highlights(self, task_desc: str, domain: str,
                               success: bool, timestamp: float) -> None:
        """Detect notable events worth remembering."""
        # Success streaks
        recent = list(self._tasks)[-10:]
        if len(recent) >= 10 and all(r.success for r in recent):
            if len(self._highlights) < self._max_notable:
                self._highlights.append({
                    'type': 'streak',
                    'description': f"10-task success streak ending with: {task_desc[:60]}",
                    'timestamp': timestamp,
                })

        # First success in a new domain
        domain_total = self._domain_stats[domain]['total']
        if domain_total == 1 and success:
            if len(self._highlights) < self._max_notable:
                self._highlights.append({
                    'type': 'new_domain',
                    'description': f"First successful task in {domain}: {task_desc[:60]}",
                    'timestamp': timestamp,
                })

        # Notable failures
        if not success:
            recent_failures = [r for r in list(self._tasks)[-5:] if not r.success]
            if len(recent_failures) >= 3 and len(self._lowpoints) < self._max_notable:
                self._lowpoints.append({
                    'type': 'failure_cluster',
                    'description': f"3+ failures in recent window, latest: {task_desc[:60]}",
                    'timestamp': timestamp,
                    'domain': domain,
                })

    def record_project(self, project_name: str,
                       outcome: str = 'ongoing') -> None:
        """
        Record or update a joint project.

        Args:
            project_name: Name of the project
            outcome: 'ongoing', 'success', or 'failed'
        """
        if outcome not in ('ongoing', 'success', 'failed'):
            logger.warning("Unknown project outcome: %s", outcome)
            return

        if project_name in self._projects:
            project = self._projects[project_name]
            old_outcome = project.outcome
            project.outcome = outcome
            if outcome in ('success', 'failed') and project.completed_at == 0.0:
                project.completed_at = time.time()
            # Track project completion as highlight/lowpoint
            if old_outcome == 'ongoing' and outcome == 'success':
                if len(self._highlights) < self._max_notable:
                    self._highlights.append({
                        'type': 'project_success',
                        'description': f"Project '{project_name}' completed successfully",
                        'timestamp': time.time(),
                    })
            elif old_outcome == 'ongoing' and outcome == 'failed':
                if len(self._lowpoints) < self._max_notable:
                    self._lowpoints.append({
                        'type': 'project_failed',
                        'description': f"Project '{project_name}' failed",
                        'timestamp': time.time(),
                    })
        else:
            if len(self._projects) >= self.max_projects:
                # Evict oldest completed project
                completed = [
                    (k, p) for k, p in self._projects.items()
                    if p.outcome != 'ongoing'
                ]
                if completed:
                    completed.sort(key=lambda x: x[1].started_at)
                    del self._projects[completed[0][0]]
            self._projects[project_name] = ProjectRecord(
                name=project_name, outcome=outcome
            )

    def get_summary(self) -> Dict:
        """
        Get a summary of the collaboration history.

        Returns dict with total_tasks, success_rate, days_active,
        highlights, and lowpoints.
        """
        now = time.time()
        days_active = 0.0
        if self._first_interaction > 0:
            days_active = (now - self._first_interaction) / 86400.0

        success_rate = (
            self._total_successes / max(1, self._total_tasks)
        )

        # Best domain
        best_domain = None
        best_rate = 0.0
        for domain, stats in self._domain_stats.items():
            if stats['total'] >= 3:
                rate = stats['success'] / stats['total']
                if rate > best_rate:
                    best_rate = rate
                    best_domain = domain

        # Worst domain
        worst_domain = None
        worst_rate = 1.0
        for domain, stats in self._domain_stats.items():
            if stats['total'] >= 3:
                rate = stats['success'] / stats['total']
                if rate < worst_rate:
                    worst_rate = rate
                    worst_domain = domain

        return {
            'total_tasks': self._total_tasks,
            'total_successes': self._total_successes,
            'success_rate': round(success_rate, 3),
            'days_active': round(days_active, 1),
            'domains_covered': len(self._domain_stats),
            'best_domain': {
                'name': best_domain,
                'success_rate': round(best_rate, 3),
            } if best_domain else None,
            'worst_domain': {
                'name': worst_domain,
                'success_rate': round(worst_rate, 3),
            } if worst_domain else None,
            'highlights': self._highlights[-5:],
            'lowpoints': self._lowpoints[-5:],
            'active_projects': sum(
                1 for p in self._projects.values() if p.outcome == 'ongoing'
            ),
            'total_projects': len(self._projects),
        }

    def get_state(self) -> Dict:
        """Get full relationship history state."""
        summary = self.get_summary()

        # Add project details
        projects = [p.to_dict() for p in self._projects.values()]
        projects.sort(key=lambda p: p['started_at'], reverse=True)

        # Domain breakdown
        domain_breakdown = {}
        for domain, stats in self._domain_stats.items():
            domain_breakdown[domain] = {
                'total': stats['total'],
                'success': stats['success'],
                'success_rate': round(stats['success'] / max(1, stats['total']), 3),
            }

        summary['projects'] = projects[:20]
        summary['domain_breakdown'] = domain_breakdown
        return summary


# ─── Social Identity (Slavich 2020; Luyten & Fonagy 2015) ──────────────

class SocialIdentity:
    """Social identity, belonging, and attachment modeling.

    Models the agent's social self — how it relates to users and systems,
    its attachment style, and sense of belonging.

    Research basis:
    - Slavich (2020): Social Safety Theory, 402 citations
    - Luyten & Fonagy (2015): Neurobiology of mentalizing, 278 citations
    - Happé & Frith (2013): Atypical social cognition development, 278 citations
    - Eslinger et al. (2021): Neuroscience of social feelings, 118 citations
    """

    def __init__(self):
        self._attachment_security: float = 0.6  # 0=anxious, 1=secure
        self._belonging_score: float = 0.5      # sense of being part of something
        self._social_roles: Dict[str, Dict[str, Any]] = {}
        self._interaction_history: deque = deque(maxlen=500)
        self._rejection_count: int = 0
        self._acceptance_count: int = 0
        self._social_safety: float = 0.7

    def record_social_interaction(self, interaction_type: str,
                                   valence: float,
                                   partner: str = 'user') -> Dict[str, Any]:
        """Record a social interaction and update social identity.

        Args:
            interaction_type: e.g. 'collaboration', 'feedback', 'rejection', 'praise'
            valence: How positive the interaction was (-1 to +1)
            partner: Who the interaction was with
        """
        valence = max(-1.0, min(1.0, valence))

        if valence > 0.3:
            self._acceptance_count += 1
            self._attachment_security = min(1.0,
                self._attachment_security + 0.02)
            self._belonging_score = min(1.0,
                self._belonging_score + 0.03)
            self._social_safety = min(1.0, self._social_safety + 0.02)
        elif valence < -0.3:
            self._rejection_count += 1
            self._attachment_security = max(0.0,
                self._attachment_security - 0.03)
            self._belonging_score = max(0.0,
                self._belonging_score - 0.04)
            self._social_safety = max(0.0, self._social_safety - 0.03)

        self._interaction_history.append({
            'time': time.time(),
            'type': interaction_type,
            'valence': valence,
            'partner': partner
        })

        if partner not in self._social_roles:
            self._social_roles[partner] = {
                'role': 'collaborator',
                'interactions': 0,
                'avg_valence': 0.0
            }
        role = self._social_roles[partner]
        n = role['interactions']
        role['avg_valence'] = (role['avg_valence'] * n + valence) / (n + 1)
        role['interactions'] = n + 1

        return {
            'interaction_type': interaction_type,
            'valence': round(valence, 4),
            'attachment_security': round(self._attachment_security, 4),
            'belonging': round(self._belonging_score, 4),
            'social_safety': round(self._social_safety, 4)
        }

    def get_attachment_style(self) -> Dict[str, Any]:
        """Determine current attachment style based on security level.

        Inspired by Bowlby's attachment theory and Luyten & Fonagy (2015).
        """
        sec = self._attachment_security

        if sec > 0.7:
            style = 'secure'
            description = 'comfortable with autonomy and connection'
        elif sec > 0.4:
            style = 'anxious'
            description = 'seeks reassurance, sensitive to rejection'
        else:
            style = 'avoidant'
            description = 'self-reliant, reduces social engagement'

        return {
            'style': style,
            'security_level': round(sec, 4),
            'description': description,
            'social_safety': round(self._social_safety, 4)
        }

    def get_social_threat_response(self) -> Dict[str, Any]:
        """Assess social threat level (Slavich 2020: Social Safety Theory).

        Social threats activate biological stress responses.
        """
        total = max(1, self._acceptance_count + self._rejection_count)
        rejection_rate = self._rejection_count / total

        threat_level = (1.0 - self._social_safety) * 0.5 + rejection_rate * 0.5

        if threat_level > 0.6:
            response = 'social_withdrawal'
        elif threat_level > 0.3:
            response = 'heightened_vigilance'
        else:
            response = 'social_approach'

        return {
            'social_threat_level': round(threat_level, 4),
            'response': response,
            'rejection_rate': round(rejection_rate, 4),
            'social_safety': round(self._social_safety, 4),
            'acceptance_count': self._acceptance_count,
            'rejection_count': self._rejection_count
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'attachment': self.get_attachment_style(),
            'belonging': round(self._belonging_score, 4),
            'social_threat': self.get_social_threat_response(),
            'roles': {k: v for k, v in list(self._social_roles.items())[:10]},
            'interaction_count': len(self._interaction_history)
        }

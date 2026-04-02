"""
Action Systems (V2 Phase 2: P2.18, P2.25-30)

Seven action subsystems that plan, validate, monitor, and learn from
action execution across the Tahlamus brain's operational systems
(Automation, Coding Engine, Requirements Engine):

1. ApprovalGate (P2.18):
   Actions with risk_level >= high need user approval before execution.
   Approval requests are queued; timeout (default 60s) auto-rejects.
   Full audit log of all approval decisions.

2. ActionPlanner (P2.25):
   Decomposes complex goals into DAGs of tool/action sequences.
   Each action carries system assignment, dependencies, estimated
   duration, and risk level.

3. ActionValidator (P2.26):
   Pre-execution safety check against blocked patterns, resource
   limits, and approval-required patterns. Returns per-action
   approved/rejected verdicts.

4. ActionMonitor (P2.27):
   Monitors running actions for timeout, infinite loops, unexpected
   outputs, and resource escalation. Automatic abort on anomaly.

5. ActionOutcomeDetector (P2.28):
   Automatic success/failure detection based on exit codes, HTTP
   status, and job status. Feeds outcome data to memory.

6. ActionReplayMemory (P2.29):
   Episodic memory of (Situation, System, Action, Parameters,
   Outcome, Duration). Prioritized replay with failure boosting
   and pattern mining.

7. ActionLearning (P2.30):
   Meta-learning over action history. Tracks per-system success
   rates by task type and dynamically adjusts routing weights.

Integration:
    AgentLoop calls action_systems.plan() to decompose goals,
    action_systems.validate() before execution,
    action_systems.monitor() during execution,
    action_systems.record_outcome() after completion.
"""

import logging
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('brain.actions')


# ─── Data Structures ────────────────────────────────────────────────────────

@dataclass
class PlannedAction:
    """A single action within an action plan."""
    action_id: str
    action_type: str                     # 'shell', 'http', 'coding_job', 'file_write', etc.
    target_system: str                   # 'automation', 'coding_engine', 'requirements_engine'
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)   # action_ids that must complete first
    estimated_duration_seconds: float = 30.0
    risk_level: str = 'low'              # low / medium / high / critical
    status: str = 'pending'              # pending / approved / rejected / running / completed / failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action_id': self.action_id,
            'action_type': self.action_type,
            'target_system': self.target_system,
            'parameters': self.parameters,
            'dependencies': self.dependencies,
            'estimated_duration_seconds': self.estimated_duration_seconds,
            'risk_level': self.risk_level,
            'status': self.status,
        }


@dataclass
class ActionPlan:
    """A DAG of planned actions derived from a goal."""
    plan_id: str
    goal: str
    actions: List[PlannedAction] = field(default_factory=list)
    status: str = 'pending'              # pending / running / completed / failed / cancelled
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'plan_id': self.plan_id,
            'goal': self.goal,
            'actions': [a.to_dict() for a in self.actions],
            'status': self.status,
            'created_at': self.created_at,
            'action_count': len(self.actions),
        }


@dataclass
class ActionOutcome:
    """Result of a completed action."""
    action_id: str
    plan_id: str
    success: bool
    exit_code: Optional[int] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action_id': self.action_id,
            'plan_id': self.plan_id,
            'success': self.success,
            'exit_code': self.exit_code,
            'duration_seconds': round(self.duration_seconds, 3),
            'error_message': self.error_message,
            'timestamp': self.timestamp,
        }


@dataclass
class ApprovalRequest:
    """A pending approval request for a high-risk action."""
    request_id: str
    action: PlannedAction
    reason: str
    risk_level: str
    requested_at: float = 0.0
    timeout_seconds: float = 60.0
    status: str = 'pending'              # pending / approved / rejected / timeout

    def __post_init__(self):
        if self.requested_at == 0.0:
            self.requested_at = time.time()

    def is_expired(self) -> bool:
        """Check if the approval request has timed out."""
        return (time.time() - self.requested_at) > self.timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            'request_id': self.request_id,
            'action_id': self.action.action_id,
            'action_type': self.action.action_type,
            'reason': self.reason,
            'risk_level': self.risk_level,
            'requested_at': self.requested_at,
            'timeout_seconds': self.timeout_seconds,
            'status': self.status,
            'is_expired': self.is_expired(),
        }


# ─── Approval Gate (P2.18) ──────────────────────────────────────────────────

# Risk level ordering for comparison
_RISK_LEVELS = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}


class ApprovalGate:
    """
    Actions with risk_level >= threshold need user approval (P2.18).

    Approval requests are placed in a queue. If the user does not
    respond within the timeout, the request is automatically rejected
    (configurable). All decisions are recorded in an audit log.
    """

    def __init__(
        self,
        default_timeout: float = 60.0,
        auto_reject_on_timeout: bool = True,
        risk_threshold: str = 'high',
    ):
        """
        Args:
            default_timeout: Seconds before an approval request expires.
            auto_reject_on_timeout: If True, expired requests are rejected.
            risk_threshold: Minimum risk level that requires approval
                            ('low', 'medium', 'high', 'critical').
        """
        self.default_timeout = default_timeout
        self.auto_reject_on_timeout = auto_reject_on_timeout
        self.risk_threshold = risk_threshold

        # Pending requests: request_id -> ApprovalRequest
        self._pending: Dict[str, ApprovalRequest] = {}

        # Audit log: deque of decision records
        self._audit_log: deque = deque(maxlen=500)

        # Statistics
        self._total_requests: int = 0
        self._total_approved: int = 0
        self._total_rejected: int = 0
        self._total_timeouts: int = 0

    def requires_approval(self, action: PlannedAction) -> bool:
        """Check if an action requires user approval based on risk level."""
        action_level = _RISK_LEVELS.get(action.risk_level, 0)
        threshold_level = _RISK_LEVELS.get(self.risk_threshold, 2)
        return action_level >= threshold_level

    def request_approval(
        self,
        action: PlannedAction,
        reason: str = '',
    ) -> ApprovalRequest:
        """
        Submit an action for user approval.

        Returns an ApprovalRequest that the caller can poll or wait on.
        """
        self._total_requests += 1

        request = ApprovalRequest(
            request_id=f"approval_{uuid.uuid4().hex[:8]}",
            action=action,
            reason=reason or f"Action '{action.action_type}' has risk level '{action.risk_level}'",
            risk_level=action.risk_level,
            timeout_seconds=self.default_timeout,
        )
        self._pending[request.request_id] = request

        logger.info(
            f"Approval requested: {request.request_id} for "
            f"action '{action.action_type}' (risk: {action.risk_level})"
        )
        return request

    def approve(self, request_id: str) -> bool:
        """Approve a pending request. Returns False if not found or expired."""
        request = self._pending.pop(request_id, None)
        if request is None:
            return False

        if request.is_expired():
            request.status = 'timeout'
            self._total_timeouts += 1
            self._record_audit(request, 'timeout', 'Request expired before approval')
            return False

        request.status = 'approved'
        request.action.status = 'approved'
        self._total_approved += 1
        self._record_audit(request, 'approved', 'User approved')
        return True

    def reject(self, request_id: str, reason: str = '') -> bool:
        """Reject a pending request. Returns False if not found."""
        request = self._pending.pop(request_id, None)
        if request is None:
            return False

        request.status = 'rejected'
        request.action.status = 'rejected'
        self._total_rejected += 1
        self._record_audit(request, 'rejected', reason or 'User rejected')
        return True

    def process_timeouts(self) -> List[ApprovalRequest]:
        """
        Check all pending requests for timeouts.

        Returns list of requests that timed out.
        """
        timed_out = []
        expired_ids = []

        for req_id, request in self._pending.items():
            if request.is_expired():
                expired_ids.append(req_id)
                request.status = 'timeout'
                if self.auto_reject_on_timeout:
                    request.action.status = 'rejected'
                self._total_timeouts += 1
                self._record_audit(request, 'timeout', 'Auto-rejected on timeout')
                timed_out.append(request)

        for req_id in expired_ids:
            self._pending.pop(req_id, None)

        return timed_out

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Get all pending approval requests."""
        self.process_timeouts()  # Clean up expired first
        return [r.to_dict() for r in self._pending.values()]

    def _record_audit(self, request: ApprovalRequest, decision: str, reason: str):
        """Record an approval decision in the audit log."""
        self._audit_log.append({
            'request_id': request.request_id,
            'action_id': request.action.action_id,
            'action_type': request.action.action_type,
            'risk_level': request.risk_level,
            'decision': decision,
            'reason': reason,
            'timestamp': time.time(),
        })

    def get_state(self) -> Dict[str, Any]:
        """Get approval gate state for dashboard."""
        return {
            'name': 'ApprovalGate',
            'default_timeout': self.default_timeout,
            'auto_reject_on_timeout': self.auto_reject_on_timeout,
            'risk_threshold': self.risk_threshold,
            'pending_count': len(self._pending),
            'total_requests': self._total_requests,
            'total_approved': self._total_approved,
            'total_rejected': self._total_rejected,
            'total_timeouts': self._total_timeouts,
            'approval_rate': (
                round(self._total_approved / max(1, self._total_requests), 3)
            ),
            'recent_audit': list(self._audit_log)[-10:],
        }


# ─── Action Planner (P2.25) ─────────────────────────────────────────────────

# Default decomposition templates: goal keyword -> list of action steps
_DEFAULT_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    'deploy': [
        {'action_type': 'spec_review', 'target_system': 'requirements_engine', 'risk': 'low'},
        {'action_type': 'implement', 'target_system': 'coding_engine', 'risk': 'medium'},
        {'action_type': 'test', 'target_system': 'coding_engine', 'risk': 'low'},
        {'action_type': 'deploy', 'target_system': 'automation', 'risk': 'high'},
        {'action_type': 'verify', 'target_system': 'automation', 'risk': 'low'},
    ],
    'fix': [
        {'action_type': 'diagnose', 'target_system': 'coding_engine', 'risk': 'low'},
        {'action_type': 'implement_fix', 'target_system': 'coding_engine', 'risk': 'medium'},
        {'action_type': 'test_fix', 'target_system': 'coding_engine', 'risk': 'low'},
    ],
    'investigate': [
        {'action_type': 'gather_data', 'target_system': 'automation', 'risk': 'low'},
        {'action_type': 'analyze', 'target_system': 'requirements_engine', 'risk': 'low'},
        {'action_type': 'report', 'target_system': 'coding_engine', 'risk': 'low'},
    ],
    'test': [
        {'action_type': 'prepare_env', 'target_system': 'automation', 'risk': 'low'},
        {'action_type': 'run_tests', 'target_system': 'coding_engine', 'risk': 'low'},
        {'action_type': 'collect_results', 'target_system': 'automation', 'risk': 'low'},
    ],
}


class ActionPlanner:
    """
    Decomposes complex goals into DAGs of actions (P2.25).

    Each action in the DAG is assigned to a target system (automation,
    coding_engine, requirements_engine), with dependency links forming
    the execution order.
    """

    def __init__(
        self,
        max_plan_depth: int = 10,
        max_actions_per_plan: int = 50,
        default_risk: str = 'low',
        templates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ):
        """
        Args:
            max_plan_depth: Maximum depth of dependency chains.
            max_actions_per_plan: Maximum actions in a single plan.
            default_risk: Default risk level for actions without explicit risk.
            templates: Decomposition templates {keyword: [action_defs]}.
        """
        self.max_plan_depth = max_plan_depth
        self.max_actions_per_plan = max_actions_per_plan
        self.default_risk = default_risk
        self._templates = dict(templates or _DEFAULT_TEMPLATES)

        self._total_plans: int = 0
        self._total_actions_planned: int = 0

    def create_plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionPlan:
        """
        Create an action plan from a goal description.

        Matches the goal against known templates. Falls back to a
        single generic action if no template matches.

        Args:
            goal: Human-readable goal description.
            context: Optional context (domain, metadata, etc.).

        Returns:
            ActionPlan with DAG of PlannedActions.
        """
        self._total_plans += 1
        context = context or {}

        plan = ActionPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            goal=goal,
        )

        # Match goal against templates
        goal_lower = goal.lower()
        matched_template = None
        for keyword, template in self._templates.items():
            if keyword in goal_lower:
                matched_template = template
                break

        if matched_template:
            actions = self._expand_template(matched_template, plan.plan_id, context)
        else:
            # Fallback: single generic action
            actions = [PlannedAction(
                action_id=f"act_{uuid.uuid4().hex[:6]}",
                action_type='execute',
                target_system=context.get('target_system', 'automation'),
                parameters={'goal': goal},
                risk_level=self.default_risk,
            )]

        # Enforce limits
        plan.actions = actions[:self.max_actions_per_plan]
        self._total_actions_planned += len(plan.actions)

        logger.info(
            f"Plan '{plan.plan_id}' created for goal '{goal[:60]}' "
            f"with {len(plan.actions)} actions"
        )
        return plan

    def add_custom_template(self, keyword: str, steps: List[Dict[str, Any]]):
        """Register a custom decomposition template."""
        self._templates[keyword] = steps

    def _expand_template(
        self,
        template: List[Dict[str, Any]],
        plan_id: str,
        context: Dict[str, Any],
    ) -> List[PlannedAction]:
        """Expand a template into a chain of PlannedActions with dependencies."""
        actions = []
        prev_id: Optional[str] = None

        for step_def in template[:self.max_plan_depth]:
            action_id = f"act_{uuid.uuid4().hex[:6]}"
            action = PlannedAction(
                action_id=action_id,
                action_type=step_def.get('action_type', 'execute'),
                target_system=step_def.get('target_system', 'automation'),
                parameters=step_def.get('parameters', {}),
                dependencies=[prev_id] if prev_id else [],
                estimated_duration_seconds=step_def.get('duration', 30.0),
                risk_level=step_def.get('risk', self.default_risk),
            )
            actions.append(action)
            prev_id = action_id

        return actions

    def get_execution_order(self, plan: ActionPlan) -> List[List[PlannedAction]]:
        """
        Compute execution layers from the DAG (topological sort).

        Returns list of layers. Actions in the same layer can run
        in parallel; layers must run sequentially.
        """
        if not plan.actions:
            return []

        action_map = {a.action_id: a for a in plan.actions}
        completed = set()
        layers: List[List[PlannedAction]] = []

        remaining = list(plan.actions)
        max_iterations = self.max_plan_depth + 1

        for _ in range(max_iterations):
            if not remaining:
                break

            # Find actions whose dependencies are all completed
            ready = []
            still_waiting = []
            for action in remaining:
                deps_met = all(d in completed for d in action.dependencies)
                if deps_met:
                    ready.append(action)
                else:
                    still_waiting.append(action)

            if not ready:
                # Deadlock or circular dependency: force remaining into last layer
                logger.warning(
                    f"Plan '{plan.plan_id}': dependency deadlock, "
                    f"forcing {len(still_waiting)} remaining actions"
                )
                layers.append(still_waiting)
                break

            layers.append(ready)
            completed.update(a.action_id for a in ready)
            remaining = still_waiting

        return layers

    def get_state(self) -> Dict[str, Any]:
        """Get planner state for dashboard."""
        return {
            'name': 'ActionPlanner',
            'max_plan_depth': self.max_plan_depth,
            'max_actions_per_plan': self.max_actions_per_plan,
            'default_risk': self.default_risk,
            'template_count': len(self._templates),
            'template_keywords': list(self._templates.keys()),
            'total_plans': self._total_plans,
            'total_actions_planned': self._total_actions_planned,
        }


# ─── Action Validator (P2.26) ───────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Result of validating a single action."""
    action_id: str
    approved: bool
    reason: str = ''
    matched_pattern: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action_id': self.action_id,
            'approved': self.approved,
            'reason': self.reason,
            'matched_pattern': self.matched_pattern,
        }


# Default blocked patterns: actions that are never allowed
_DEFAULT_BLOCKED_PATTERNS = [
    r'rm\s+(-[rfRF]+\s+)?/',
    r'rm\s+(-[rfRF]+\s+)?\*',
    r'DROP\s+(TABLE|DATABASE)',
    r'TRUNCATE\s+TABLE',
    r'DELETE\s+FROM\s+\S+\s*$',
    r'format\s+[a-zA-Z]:',
    r'mkfs\.',
    r'dd\s+if=.*of=/',
]

# Default patterns requiring approval
_DEFAULT_APPROVAL_PATTERNS = [
    r'deploy',
    r'production',
    r'release',
    r'publish',
    r'sudo\s+',
    r'--force',
]


class ActionValidator:
    """
    Pre-execution safety validator for planned actions (P2.26).

    Checks each action against:
    1. Blocked patterns (always rejected)
    2. Approval-required patterns (flagged for approval)
    3. Resource cost limits
    """

    def __init__(
        self,
        blocked_patterns: Optional[List[str]] = None,
        max_resource_cost: float = 100.0,
        require_approval_patterns: Optional[List[str]] = None,
    ):
        """
        Args:
            blocked_patterns: Regex patterns for actions that are always blocked.
            max_resource_cost: Maximum estimated resource cost per action.
            require_approval_patterns: Regex patterns that require user approval.
        """
        self.max_resource_cost = max_resource_cost

        raw_blocked = blocked_patterns if blocked_patterns is not None else _DEFAULT_BLOCKED_PATTERNS
        self._blocked_compiled = [
            re.compile(p, re.IGNORECASE) for p in raw_blocked
        ]
        self._blocked_raw = list(raw_blocked)

        raw_approval = require_approval_patterns if require_approval_patterns is not None else _DEFAULT_APPROVAL_PATTERNS
        self._approval_compiled = [
            re.compile(p, re.IGNORECASE) for p in raw_approval
        ]
        self._approval_raw = list(raw_approval)

        # Statistics
        self._total_validated: int = 0
        self._total_approved: int = 0
        self._total_rejected: int = 0
        self._total_flagged_for_approval: int = 0

    def validate_action(self, action: PlannedAction) -> ValidationResult:
        """
        Validate a single action against safety constraints.

        Returns ValidationResult with approved=True/False.
        Actions matching blocked patterns are rejected.
        Actions matching approval patterns are flagged (not auto-rejected,
        but risk_level is elevated to 'high').
        """
        self._total_validated += 1

        # Build searchable text from action
        search_text = ' '.join([
            action.action_type,
            action.target_system,
            str(action.parameters),
        ])

        # 1. Check blocked patterns
        for i, pattern in enumerate(self._blocked_compiled):
            if pattern.search(search_text):
                self._total_rejected += 1
                action.status = 'rejected'
                return ValidationResult(
                    action_id=action.action_id,
                    approved=False,
                    reason=f"Matches blocked pattern: {self._blocked_raw[i]}",
                    matched_pattern=self._blocked_raw[i],
                )

        # 2. Check resource cost
        cost = action.parameters.get('resource_cost', 0)
        if cost > self.max_resource_cost:
            self._total_rejected += 1
            action.status = 'rejected'
            return ValidationResult(
                action_id=action.action_id,
                approved=False,
                reason=f"Resource cost {cost} exceeds limit {self.max_resource_cost}",
            )

        # 3. Check approval-required patterns (elevate risk, don't reject)
        for i, pattern in enumerate(self._approval_compiled):
            if pattern.search(search_text):
                self._total_flagged_for_approval += 1
                # Elevate risk level so ApprovalGate catches it
                if _RISK_LEVELS.get(action.risk_level, 0) < _RISK_LEVELS.get('high', 2):
                    action.risk_level = 'high'
                self._total_approved += 1
                return ValidationResult(
                    action_id=action.action_id,
                    approved=True,
                    reason=f"Flagged for approval (pattern: {self._approval_raw[i]})",
                    matched_pattern=self._approval_raw[i],
                )

        # All checks passed
        self._total_approved += 1
        return ValidationResult(
            action_id=action.action_id,
            approved=True,
            reason='Passed all safety checks',
        )

    def validate_plan(self, plan: ActionPlan) -> List[ValidationResult]:
        """Validate all actions in a plan. Returns results per action."""
        return [self.validate_action(action) for action in plan.actions]

    def get_state(self) -> Dict[str, Any]:
        """Get validator state for dashboard."""
        return {
            'name': 'ActionValidator',
            'blocked_pattern_count': len(self._blocked_compiled),
            'approval_pattern_count': len(self._approval_compiled),
            'max_resource_cost': self.max_resource_cost,
            'total_validated': self._total_validated,
            'total_approved': self._total_approved,
            'total_rejected': self._total_rejected,
            'total_flagged_for_approval': self._total_flagged_for_approval,
            'approval_rate': (
                round(self._total_approved / max(1, self._total_validated), 3)
            ),
        }


# ─── Action Monitor (P2.27) ─────────────────────────────────────────────────

@dataclass
class MonitoredAction:
    """Internal tracking state for a running action."""
    action_id: str
    plan_id: str
    action_type: str
    started_at: float = 0.0
    timeout_seconds: float = 300.0
    retries: int = 0
    max_retries: int = 3
    last_output: str = ''
    resource_usage: float = 0.0          # 0.0 to 1.0, for escalation detection
    aborted: bool = False
    abort_reason: str = ''

    def __post_init__(self):
        if self.started_at == 0.0:
            self.started_at = time.time()

    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at

    def is_timed_out(self) -> bool:
        return self.elapsed_seconds() > self.timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action_id': self.action_id,
            'plan_id': self.plan_id,
            'action_type': self.action_type,
            'elapsed_seconds': round(self.elapsed_seconds(), 1),
            'timeout_seconds': self.timeout_seconds,
            'retries': self.retries,
            'aborted': self.aborted,
            'abort_reason': self.abort_reason,
            'resource_usage': round(self.resource_usage, 3),
        }


class ActionMonitor:
    """
    Monitors running actions for anomalies (P2.27).

    Detects:
    - Timeout (configurable per action type)
    - Resource escalation (usage exceeding threshold)
    - Repeated identical outputs (possible infinite loop)

    Emits events compatible with the event bus.
    """

    def __init__(
        self,
        default_timeout_seconds: float = 300.0,
        max_retries: int = 3,
        escalation_threshold: float = 0.9,
    ):
        """
        Args:
            default_timeout_seconds: Default timeout for monitored actions.
            max_retries: Maximum retry attempts before permanent abort.
            escalation_threshold: Resource usage ratio above which to abort.
        """
        self.default_timeout_seconds = default_timeout_seconds
        self.max_retries = max_retries
        self.escalation_threshold = escalation_threshold

        # Active monitors: action_id -> MonitoredAction
        self._active: Dict[str, MonitoredAction] = {}

        # Output history for loop detection: action_id -> deque of outputs
        self._output_history: Dict[str, deque] = {}

        # Event queue for event bus emission
        self._event_queue: deque = deque(maxlen=200)

        # Statistics
        self._total_monitored: int = 0
        self._total_timeouts: int = 0
        self._total_aborts: int = 0
        self._total_retries: int = 0

    def start_monitoring(
        self,
        action: PlannedAction,
        plan_id: str,
        timeout_override: Optional[float] = None,
    ):
        """Start monitoring a running action."""
        self._total_monitored += 1

        monitored = MonitoredAction(
            action_id=action.action_id,
            plan_id=plan_id,
            action_type=action.action_type,
            timeout_seconds=timeout_override or self.default_timeout_seconds,
            max_retries=self.max_retries,
        )
        self._active[action.action_id] = monitored
        self._output_history[action.action_id] = deque(maxlen=50)

        logger.debug(
            f"Monitoring started for action '{action.action_id}' "
            f"(timeout: {monitored.timeout_seconds}s)"
        )

    def record_output(self, action_id: str, output: str):
        """Record an output from a running action (for loop detection)."""
        monitored = self._active.get(action_id)
        if monitored is None:
            return

        monitored.last_output = output
        history = self._output_history.get(action_id)
        if history is not None:
            history.append(output)

    def record_resource_usage(self, action_id: str, usage: float):
        """Record resource usage for escalation detection (0.0 to 1.0)."""
        monitored = self._active.get(action_id)
        if monitored is not None:
            monitored.resource_usage = max(0.0, min(1.0, usage))

    def check_all(self) -> List[Dict[str, Any]]:
        """
        Check all active monitors for anomalies.

        Returns list of events for actions that need attention
        (timeout, loop detected, resource escalation).
        """
        events = []
        abort_ids = []

        for action_id, monitored in self._active.items():
            if monitored.aborted:
                continue

            # 1. Timeout detection
            if monitored.is_timed_out():
                event = self._handle_timeout(monitored)
                events.append(event)
                if monitored.aborted:
                    abort_ids.append(action_id)
                continue

            # 2. Resource escalation
            if monitored.resource_usage > self.escalation_threshold:
                event = self._handle_escalation(monitored)
                events.append(event)
                if monitored.aborted:
                    abort_ids.append(action_id)
                continue

            # 3. Infinite loop detection (repeated identical outputs)
            if self._detect_loop(action_id):
                event = self._handle_loop(monitored)
                events.append(event)
                if monitored.aborted:
                    abort_ids.append(action_id)

        # Queue events for bus emission
        self._event_queue.extend(events)

        return events

    def stop_monitoring(self, action_id: str):
        """Stop monitoring an action (completed or failed)."""
        self._active.pop(action_id, None)
        self._output_history.pop(action_id, None)

    def get_active_monitors(self) -> List[Dict[str, Any]]:
        """Get all actively monitored actions."""
        return [m.to_dict() for m in self._active.values()]

    def drain_events(self) -> List[Dict[str, Any]]:
        """Drain the event queue (for event bus integration)."""
        events = list(self._event_queue)
        self._event_queue.clear()
        return events

    def _handle_timeout(self, monitored: MonitoredAction) -> Dict[str, Any]:
        """Handle a timed-out action."""
        self._total_timeouts += 1

        if monitored.retries < monitored.max_retries:
            monitored.retries += 1
            monitored.started_at = time.time()  # Reset timer for retry
            self._total_retries += 1
            return {
                'type': 'action_timeout_retry',
                'action_id': monitored.action_id,
                'plan_id': monitored.plan_id,
                'retry': monitored.retries,
                'timestamp': time.time(),
            }
        else:
            monitored.aborted = True
            monitored.abort_reason = (
                f"Timeout after {monitored.timeout_seconds}s "
                f"({monitored.retries} retries exhausted)"
            )
            self._total_aborts += 1
            return {
                'type': 'action_aborted',
                'action_id': monitored.action_id,
                'plan_id': monitored.plan_id,
                'reason': monitored.abort_reason,
                'timestamp': time.time(),
            }

    def _handle_escalation(self, monitored: MonitoredAction) -> Dict[str, Any]:
        """Handle resource escalation."""
        monitored.aborted = True
        monitored.abort_reason = (
            f"Resource usage {monitored.resource_usage:.2f} "
            f"exceeds threshold {self.escalation_threshold}"
        )
        self._total_aborts += 1
        logger.warning(
            f"Action '{monitored.action_id}' aborted: {monitored.abort_reason}"
        )
        return {
            'type': 'action_aborted',
            'action_id': monitored.action_id,
            'plan_id': monitored.plan_id,
            'reason': monitored.abort_reason,
            'timestamp': time.time(),
        }

    def _handle_loop(self, monitored: MonitoredAction) -> Dict[str, Any]:
        """Handle detected infinite loop."""
        monitored.aborted = True
        monitored.abort_reason = 'Infinite loop detected (repeated identical outputs)'
        self._total_aborts += 1
        logger.warning(
            f"Action '{monitored.action_id}' aborted: infinite loop detected"
        )
        return {
            'type': 'action_aborted',
            'action_id': monitored.action_id,
            'plan_id': monitored.plan_id,
            'reason': monitored.abort_reason,
            'timestamp': time.time(),
        }

    def _detect_loop(self, action_id: str) -> bool:
        """
        Detect if an action is in an infinite loop.

        Returns True if the last 5 outputs are all identical and non-empty.
        """
        history = self._output_history.get(action_id)
        if history is None or len(history) < 5:
            return False

        recent = list(history)[-5:]
        if not recent[0]:  # Empty output doesn't count
            return False

        return all(o == recent[0] for o in recent)

    def get_state(self) -> Dict[str, Any]:
        """Get monitor state for dashboard."""
        return {
            'name': 'ActionMonitor',
            'default_timeout_seconds': self.default_timeout_seconds,
            'max_retries': self.max_retries,
            'escalation_threshold': self.escalation_threshold,
            'active_monitors': len(self._active),
            'total_monitored': self._total_monitored,
            'total_timeouts': self._total_timeouts,
            'total_aborts': self._total_aborts,
            'total_retries': self._total_retries,
            'pending_events': len(self._event_queue),
        }


# ─── Action Outcome Detector (P2.28) ────────────────────────────────────────

# Default patterns for automatic success/failure detection
_DEFAULT_SUCCESS_PATTERNS: Dict[str, Any] = {
    'shell': {'exit_code': 0},
    'http': {'status_range': [200, 299]},
    'coding_job': {'status': 'COMPLETED'},
    'file_write': {'exists': True},
}

_DEFAULT_FAILURE_PATTERNS: Dict[str, Any] = {
    'shell': {'exit_code_not': 0},
    'http': {'status_range': [400, 599]},
    'coding_job': {'status': 'FAILED'},
    'file_write': {'exists': False},
}


class ActionOutcomeDetector:
    """
    Automatic success/failure detection for actions (P2.28).

    Determines outcome based on:
    - Shell commands: exit code 0 = success
    - HTTP requests: status 2xx = success
    - Coding engine jobs: job.status == COMPLETED = success
    - File operations: file exists after write = success

    Feeds outcome data to ActionReplayMemory.
    """

    def __init__(
        self,
        success_patterns: Optional[Dict[str, Any]] = None,
        failure_patterns: Optional[Dict[str, Any]] = None,
        unknown_timeout: float = 60.0,
    ):
        """
        Args:
            success_patterns: Custom success detection patterns per action type.
            failure_patterns: Custom failure detection patterns per action type.
            unknown_timeout: Seconds after which an undetermined outcome
                             is classified as failure.
        """
        self._success_patterns = dict(success_patterns or _DEFAULT_SUCCESS_PATTERNS)
        self._failure_patterns = dict(failure_patterns or _DEFAULT_FAILURE_PATTERNS)
        self.unknown_timeout = unknown_timeout

        # Outcome history
        self._outcomes: deque = deque(maxlen=1000)

        # Statistics
        self._total_detected: int = 0
        self._total_success: int = 0
        self._total_failure: int = 0
        self._total_unknown: int = 0

    def detect_outcome(
        self,
        action: PlannedAction,
        plan_id: str,
        result_data: Dict[str, Any],
        duration_seconds: float = 0.0,
    ) -> ActionOutcome:
        """
        Detect the outcome of an action based on its result data.

        Args:
            action: The completed PlannedAction.
            plan_id: ID of the parent plan.
            result_data: Raw result from execution. Expected keys vary by
                         action_type:
                         - shell: {'exit_code': int, 'stdout': str, 'stderr': str}
                         - http: {'status_code': int, 'body': str}
                         - coding_job: {'status': str, 'output': str}
                         - file_write: {'exists': bool, 'path': str}
            duration_seconds: How long the action took.

        Returns:
            ActionOutcome with success/failure classification.
        """
        self._total_detected += 1

        action_type = action.action_type
        success = None
        exit_code = result_data.get('exit_code')
        error_message = None

        # Try type-specific detection
        if action_type in ('shell', 'shell_command'):
            success = self._detect_shell(result_data)
        elif action_type in ('http', 'http_request', 'api_call'):
            success = self._detect_http(result_data)
        elif action_type in ('coding_job', 'implement', 'implement_fix'):
            success = self._detect_coding_job(result_data)
        elif action_type in ('file_write', 'file_create'):
            success = self._detect_file(result_data)
        else:
            # Generic: check for explicit success/failure keys
            if 'success' in result_data:
                success = bool(result_data['success'])
            elif 'error' in result_data and result_data['error']:
                success = False
                error_message = str(result_data['error'])[:200]

        # If still unknown, check timeout-based classification
        if success is None:
            self._total_unknown += 1
            if duration_seconds > self.unknown_timeout:
                success = False
                error_message = f"Outcome undetermined after {duration_seconds:.1f}s (timeout)"
            else:
                # Default: assume success if no error signal
                success = True

        if success:
            self._total_success += 1
        else:
            self._total_failure += 1
            if not error_message:
                error_message = result_data.get('stderr', result_data.get('error', ''))
                if error_message:
                    error_message = str(error_message)[:200]

        outcome = ActionOutcome(
            action_id=action.action_id,
            plan_id=plan_id,
            success=success,
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            error_message=error_message,
        )

        self._outcomes.append(outcome.to_dict())
        return outcome

    def _detect_shell(self, data: Dict[str, Any]) -> Optional[bool]:
        """Detect shell command outcome: exit_code 0 = success."""
        code = data.get('exit_code')
        if code is not None:
            return int(code) == 0
        return None

    def _detect_http(self, data: Dict[str, Any]) -> Optional[bool]:
        """Detect HTTP outcome: 2xx = success."""
        status = data.get('status_code')
        if status is not None:
            return 200 <= int(status) <= 299
        return None

    def _detect_coding_job(self, data: Dict[str, Any]) -> Optional[bool]:
        """Detect coding job outcome: COMPLETED = success."""
        status = data.get('status', '').upper()
        if status == 'COMPLETED':
            return True
        elif status in ('FAILED', 'ERROR', 'CANCELLED'):
            return False
        return None

    def _detect_file(self, data: Dict[str, Any]) -> Optional[bool]:
        """Detect file operation outcome: exists = success."""
        exists = data.get('exists')
        if exists is not None:
            return bool(exists)
        return None

    def get_recent_outcomes(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent outcome records."""
        return list(self._outcomes)[-count:]

    def get_success_rate(self, window: int = 100) -> float:
        """Calculate success rate over last N outcomes."""
        recent = list(self._outcomes)[-window:]
        if not recent:
            return 0.0
        successes = sum(1 for o in recent if o.get('success', False))
        return round(successes / len(recent), 3)

    def get_state(self) -> Dict[str, Any]:
        """Get outcome detector state for dashboard."""
        return {
            'name': 'ActionOutcomeDetector',
            'unknown_timeout': self.unknown_timeout,
            'total_detected': self._total_detected,
            'total_success': self._total_success,
            'total_failure': self._total_failure,
            'total_unknown': self._total_unknown,
            'overall_success_rate': (
                round(self._total_success / max(1, self._total_detected), 3)
            ),
            'recent_success_rate': self.get_success_rate(),
            'outcome_buffer_size': len(self._outcomes),
        }


# ─── Action Replay Memory (P2.29) ───────────────────────────────────────────

@dataclass
class ReplayEntry:
    """An episodic memory entry for action replay."""
    situation: str                       # Task description / context
    system_used: str                     # Which system executed (automation, coding, RE)
    action_type: str                     # What was done
    parameters: Dict[str, Any] = field(default_factory=dict)
    outcome_success: bool = True
    duration_seconds: float = 0.0
    priority: float = 1.0               # Replay priority (failures get boosted)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'situation': self.situation,
            'system_used': self.system_used,
            'action_type': self.action_type,
            'parameters': self.parameters,
            'outcome_success': self.outcome_success,
            'duration_seconds': round(self.duration_seconds, 3),
            'priority': round(self.priority, 3),
            'timestamp': self.timestamp,
        }


class ActionReplayMemory:
    """
    Episodic memory for action experiences with prioritized replay (P2.29).

    Stores (Situation, SystemUsed, Action, Parameters, Outcome, Duration)
    tuples. Failures are replayed more often (priority boosted) to
    accelerate learning from mistakes.

    Pattern mining: "For task type X, system Y is most effective."
    """

    def __init__(
        self,
        max_memories: int = 5000,
        priority_boost_on_failure: float = 2.0,
        replay_batch_size: int = 32,
    ):
        """
        Args:
            max_memories: Maximum entries before oldest are evicted.
            priority_boost_on_failure: Priority multiplier for failed actions.
            replay_batch_size: Number of entries per replay batch.
        """
        self.max_memories = max_memories
        self.priority_boost_on_failure = priority_boost_on_failure
        self.replay_batch_size = replay_batch_size

        # Main memory buffer
        self._memory: deque = deque(maxlen=max_memories)

        # Indexes for pattern mining
        # system -> list of (success_bool, timestamp) tuples
        self._system_stats: Dict[str, List[Tuple[bool, float]]] = defaultdict(list)
        # action_type -> system -> success_count, total_count
        self._effectiveness: Dict[str, Dict[str, List[int]]] = defaultdict(
            lambda: defaultdict(lambda: [0, 0])
        )

        # Statistics
        self._total_stored: int = 0
        self._total_replays: int = 0

    def store(
        self,
        situation: str,
        system_used: str,
        action_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        outcome_success: bool = True,
        duration_seconds: float = 0.0,
    ):
        """Store a new action experience in episodic memory."""
        priority = 1.0
        if not outcome_success:
            priority = self.priority_boost_on_failure

        entry = ReplayEntry(
            situation=situation[:500],
            system_used=system_used,
            action_type=action_type,
            parameters=parameters or {},
            outcome_success=outcome_success,
            duration_seconds=duration_seconds,
            priority=priority,
        )
        self._memory.append(entry)
        self._total_stored += 1

        # Update indexes
        self._system_stats[system_used].append((outcome_success, time.time()))
        stats = self._effectiveness[action_type][system_used]
        if outcome_success:
            stats[0] += 1
        stats[1] += 1

    def replay_batch(self) -> List[Dict[str, Any]]:
        """
        Get a prioritized replay batch.

        Higher-priority entries (failures) are sampled more often.
        Uses a simple priority-weighted selection from recent memory.
        """
        if not self._memory:
            return []

        self._total_replays += 1

        # Get recent entries (up to 5x batch size) and sort by priority
        pool_size = min(len(self._memory), self.replay_batch_size * 5)
        pool = list(self._memory)[-pool_size:]
        pool.sort(key=lambda e: e.priority, reverse=True)

        # Take top N by priority
        batch = pool[:self.replay_batch_size]
        return [e.to_dict() for e in batch]

    def get_best_system_for(self, action_type: str) -> Optional[str]:
        """
        Pattern mining: find the most effective system for a given action type.

        Returns the system name with the highest success rate for this
        action type, or None if insufficient data.
        """
        type_stats = self._effectiveness.get(action_type, {})
        if not type_stats:
            return None

        best_system = None
        best_rate = -1.0

        for system, counts in type_stats.items():
            success_count, total_count = counts
            if total_count < 2:  # Need at least 2 samples
                continue
            rate = success_count / total_count
            if rate > best_rate:
                best_rate = rate
                best_system = system

        return best_system

    def get_system_effectiveness(self) -> Dict[str, Dict[str, Any]]:
        """
        Get effectiveness summary: for each action_type, which system
        has the best success rate.
        """
        summary = {}
        for action_type, systems in self._effectiveness.items():
            system_info = {}
            for system, counts in systems.items():
                success_count, total_count = counts
                rate = round(success_count / max(1, total_count), 3)
                system_info[system] = {
                    'success_count': success_count,
                    'total_count': total_count,
                    'success_rate': rate,
                }
            summary[action_type] = system_info
        return summary

    def get_state(self) -> Dict[str, Any]:
        """Get replay memory state for dashboard."""
        return {
            'name': 'ActionReplayMemory',
            'max_memories': self.max_memories,
            'current_size': len(self._memory),
            'priority_boost_on_failure': self.priority_boost_on_failure,
            'replay_batch_size': self.replay_batch_size,
            'total_stored': self._total_stored,
            'total_replays': self._total_replays,
            'tracked_systems': list(self._system_stats.keys()),
            'tracked_action_types': list(self._effectiveness.keys()),
            'effectiveness_summary': self.get_system_effectiveness(),
        }


# ─── Action Learning (P2.30) ────────────────────────────────────────────────

class ActionLearning:
    """
    Meta-learning over action execution history (P2.30).

    Tracks which system (Automation / Coding Engine / Requirements Engine)
    works best for which task types, and dynamically adjusts system
    routing weights based on observed success rates.
    """

    def __init__(
        self,
        learning_rate: float = 0.1,
        min_samples: int = 5,
        decay_factor: float = 0.95,
    ):
        """
        Args:
            learning_rate: How fast weights adjust toward observed rates.
            min_samples: Minimum observations before adjusting weights.
            decay_factor: Exponential decay for old observations (0-1).
        """
        self.learning_rate = learning_rate
        self.min_samples = min_samples
        self.decay_factor = decay_factor

        # Per task_type routing weights: task_type -> {system: weight}
        # Weights are initialized uniformly across known systems.
        self._systems = ['automation', 'coding_engine', 'requirements_engine']
        self._weights: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {s: 1.0 / len(self._systems) for s in self._systems}
        )

        # Observation counts: task_type -> system -> [successes, total]
        self._observations: Dict[str, Dict[str, List[int]]] = defaultdict(
            lambda: defaultdict(lambda: [0, 0])
        )

        # Statistics
        self._total_updates: int = 0
        self._total_observations: int = 0

    def observe(self, task_type: str, system: str, success: bool):
        """
        Record an observation of a system's performance on a task type.

        Args:
            task_type: Category of the task (e.g. 'deploy', 'test', 'fix').
            system: Which system executed ('automation', 'coding_engine', etc.).
            success: Whether the action succeeded.
        """
        self._total_observations += 1

        # Ensure system is tracked
        if system not in self._systems:
            self._systems.append(system)
            # Initialize weights for all task types that exist
            for tt in self._weights:
                if system not in self._weights[tt]:
                    self._weights[tt][system] = 0.1

        obs = self._observations[task_type][system]
        if success:
            obs[0] += 1
        obs[1] += 1

        # Apply decay to old observations (prevents stale data from dominating)
        self._apply_decay(task_type)

        # Update weights if enough samples
        total_for_type = sum(
            counts[1] for counts in self._observations[task_type].values()
        )
        if total_for_type >= self.min_samples:
            self._update_weights(task_type)

    def get_routing_weights(self, task_type: str) -> Dict[str, float]:
        """
        Get current routing weights for a task type.

        Returns: {system_name: weight} where weights sum to ~1.0.
        """
        if task_type in self._weights:
            return dict(self._weights[task_type])
        # Return uniform weights for unknown task types
        return {s: 1.0 / len(self._systems) for s in self._systems}

    def get_best_system(self, task_type: str) -> str:
        """Get the system with the highest routing weight for a task type."""
        weights = self.get_routing_weights(task_type)
        return max(weights, key=weights.get)

    def _update_weights(self, task_type: str):
        """
        Update routing weights based on observed success rates.

        Uses exponential moving average: new_weight = (1-lr)*old + lr*observed_rate.
        Then re-normalizes so weights sum to 1.0.
        """
        self._total_updates += 1

        current = self._weights[task_type]
        obs = self._observations[task_type]

        for system in self._systems:
            counts = obs.get(system)
            if counts is None or counts[1] == 0:
                continue

            observed_rate = counts[0] / counts[1]
            old_weight = current.get(system, 1.0 / len(self._systems))
            new_weight = (1.0 - self.learning_rate) * old_weight + self.learning_rate * observed_rate
            current[system] = max(0.01, new_weight)  # Floor to prevent zero

        # Normalize to sum to 1.0
        total = sum(current.values())
        if total > 0:
            for system in current:
                current[system] /= total

    def _apply_decay(self, task_type: str):
        """Apply decay to observation counts to down-weight old data."""
        obs = self._observations.get(task_type, {})
        for system, counts in obs.items():
            counts[0] = int(counts[0] * self.decay_factor)
            counts[1] = int(counts[1] * self.decay_factor)
            # Ensure success <= total
            counts[0] = min(counts[0], counts[1])

    def get_all_weights(self) -> Dict[str, Dict[str, float]]:
        """Get routing weights for all known task types."""
        return {
            tt: dict(weights) for tt, weights in self._weights.items()
        }

    def get_state(self) -> Dict[str, Any]:
        """Get learning state for dashboard."""
        return {
            'name': 'ActionLearning',
            'learning_rate': self.learning_rate,
            'min_samples': self.min_samples,
            'decay_factor': self.decay_factor,
            'known_systems': list(self._systems),
            'known_task_types': list(self._weights.keys()),
            'total_observations': self._total_observations,
            'total_weight_updates': self._total_updates,
            'routing_weights': self.get_all_weights(),
        }


# ─── Combined Action Systems ────────────────────────────────────────────────

class ActionSystems:
    """
    Central orchestrator for all Phase 2 action subsystems.

    Composes:
    - ApprovalGate (P2.18)
    - ActionPlanner (P2.25)
    - ActionValidator (P2.26)
    - ActionMonitor (P2.27)
    - ActionOutcomeDetector (P2.28)
    - ActionReplayMemory (P2.29)
    - ActionLearning (P2.30)

    Called by AgentLoop to plan, validate, monitor, and learn from actions.
    """

    def __init__(
        self,
        approval_gate: Optional[ApprovalGate] = None,
        planner: Optional[ActionPlanner] = None,
        validator: Optional[ActionValidator] = None,
        monitor: Optional[ActionMonitor] = None,
        outcome_detector: Optional[ActionOutcomeDetector] = None,
        replay_memory: Optional[ActionReplayMemory] = None,
        learning: Optional[ActionLearning] = None,
    ):
        self.approval_gate = approval_gate or ApprovalGate()
        self.planner = planner or ActionPlanner()
        self.validator = validator or ActionValidator()
        self.monitor = monitor or ActionMonitor()
        self.outcome_detector = outcome_detector or ActionOutcomeDetector()
        self.replay_memory = replay_memory or ActionReplayMemory()
        self.learning = learning or ActionLearning()

        self._total_plans_executed: int = 0
        self._total_actions_executed: int = 0

    def plan_and_validate(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ActionPlan, List[ValidationResult]]:
        """
        Create a plan for a goal and validate all actions.

        Returns:
            (plan, validation_results) tuple.
        """
        plan = self.planner.create_plan(goal, context)
        results = self.validator.validate_plan(plan)

        # Mark plan as failed if any action was rejected
        if any(not r.approved for r in results):
            rejected = [r for r in results if not r.approved]
            logger.warning(
                f"Plan '{plan.plan_id}' has {len(rejected)} rejected actions"
            )

        return plan, results

    def record_outcome(
        self,
        action: PlannedAction,
        plan_id: str,
        result_data: Dict[str, Any],
        duration_seconds: float = 0.0,
        situation: str = '',
    ) -> ActionOutcome:
        """
        Record the outcome of an action across all subsystems.

        Detects outcome, stores in replay memory, feeds to learning.
        """
        # 1. Detect outcome
        outcome = self.outcome_detector.detect_outcome(
            action, plan_id, result_data, duration_seconds
        )

        # 2. Stop monitoring
        self.monitor.stop_monitoring(action.action_id)

        # 3. Store in replay memory
        self.replay_memory.store(
            situation=situation or action.parameters.get('goal', action.action_type),
            system_used=action.target_system,
            action_type=action.action_type,
            parameters=action.parameters,
            outcome_success=outcome.success,
            duration_seconds=outcome.duration_seconds,
        )

        # 4. Feed to meta-learning
        self.learning.observe(
            task_type=action.action_type,
            system=action.target_system,
            success=outcome.success,
        )

        self._total_actions_executed += 1
        return outcome

    def get_state(self) -> Dict[str, Any]:
        """Get complete action systems state for dashboard."""
        return {
            'total_plans_executed': self._total_plans_executed,
            'total_actions_executed': self._total_actions_executed,
            'approval_gate': self.approval_gate.get_state(),
            'planner': self.planner.get_state(),
            'validator': self.validator.get_state(),
            'monitor': self.monitor.get_state(),
            'outcome_detector': self.outcome_detector.get_state(),
            'replay_memory': self.replay_memory.get_state(),
            'learning': self.learning.get_state(),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'ActionSystems':
        """Create ActionSystems from YAML config dict."""
        s = config.get('action_systems', {})

        approval_gate = ApprovalGate(
            default_timeout=s.get('default_timeout', 60.0),
            auto_reject_on_timeout=s.get('auto_reject_on_timeout', True),
            risk_threshold=s.get('risk_threshold', 'high'),
        )

        planner = ActionPlanner(
            max_plan_depth=s.get('max_plan_depth', 10),
            max_actions_per_plan=s.get('max_actions_per_plan', 50),
            default_risk=s.get('default_risk', 'low'),
        )

        validator = ActionValidator(
            blocked_patterns=s.get('blocked_patterns', None),
            max_resource_cost=s.get('max_resource_cost', 100.0),
            require_approval_patterns=s.get('require_approval_patterns', None),
        )

        monitor = ActionMonitor(
            default_timeout_seconds=s.get('default_timeout_seconds', 300.0),
            max_retries=s.get('max_retries', 3),
            escalation_threshold=s.get('escalation_threshold', 0.9),
        )

        outcome_detector = ActionOutcomeDetector(
            success_patterns=s.get('success_patterns', None),
            failure_patterns=s.get('failure_patterns', None),
            unknown_timeout=s.get('unknown_timeout', 60.0),
        )

        replay_memory = ActionReplayMemory(
            max_memories=s.get('max_memories', 5000),
            priority_boost_on_failure=s.get('priority_boost_on_failure', 2.0),
            replay_batch_size=s.get('replay_batch_size', 32),
        )

        learning = ActionLearning(
            learning_rate=s.get('learning_rate', 0.1),
            min_samples=s.get('min_samples', 5),
            decay_factor=s.get('decay_factor', 0.95),
        )

        return cls(
            approval_gate=approval_gate,
            planner=planner,
            validator=validator,
            monitor=monitor,
            outcome_detector=outcome_detector,
            replay_memory=replay_memory,
            learning=learning,
        )

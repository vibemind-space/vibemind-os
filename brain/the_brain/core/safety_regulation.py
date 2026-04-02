"""
Safety Regulation System (V2 Phase 3: P3.44-45)

Two systems that ensure Tahlamus operates safely within boundaries:

1. AutonomyBudgetManager (P3.44):
   Category-specific rate limits for autonomous actions:
   - Max 50 shell commands/hour (without approval)
   - Max 10 file writes/hour
   - Max 5 coding jobs/day
   - Max 1000 LLM tokens/minute for own language generation
   Budget configurable in configs/default.yaml. Escalation on exhaustion.

2. SafetyGovernor (P3.45):
   Veto system for dangerous actions:
   - Destructive commands (rm -rf, DROP TABLE, etc.)
   - File access outside configured paths
   - Network calls to unknown hosts
   - Actions exceeding CPU time limits
   Kill-switch: User can stop everything via /shutdown (POST).

Integration with AgentLoop:
    Before executing any task, the AgentLoop checks:
    1. safety_governor.check_action(action) → approve/veto/escalate
    2. autonomy_budget.can_perform(category) → within budget?
    Both can be bypassed for USER_REQUEST priority tasks.
"""

import logging
import time
import re
import os
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger('brain.safety')


# ─── Autonomy Budget Categories ──────────────────────────────────────────────

class BudgetCategory(Enum):
    """Categories of rate-limited actions."""
    SHELL_COMMAND = "shell_command"     # Shell/system commands
    FILE_WRITE = "file_write"          # File creation/modification
    CODING_JOB = "coding_job"          # Coding engine invocations
    LLM_TOKEN = "llm_token"            # LLM token generation
    NETWORK_CALL = "network_call"      # External network requests
    TASK_EXECUTION = "task_execution"   # General task execution


class BudgetPeriod(Enum):
    """Time periods for budget enforcement."""
    MINUTE = 60
    HOUR = 3600
    DAY = 86400


@dataclass
class BudgetLimit:
    """A rate limit for a specific category and period."""
    category: BudgetCategory
    period: BudgetPeriod
    max_count: int
    description: str = ""

    # Tracking state
    timestamps: List[float] = field(default_factory=list)

    def record(self, now: Optional[float] = None):
        """Record an action occurrence."""
        self.timestamps.append(now or time.time())

    def count_in_window(self, now: Optional[float] = None) -> int:
        """Count actions within the current time window."""
        now = now or time.time()
        cutoff = now - self.period.value
        self._prune(cutoff)
        return len(self.timestamps)

    def remaining(self, now: Optional[float] = None) -> int:
        """How many actions remain before budget exhaustion."""
        return max(0, self.max_count - self.count_in_window(now))

    def is_exhausted(self, now: Optional[float] = None) -> bool:
        """Check if the budget is exhausted."""
        return self.count_in_window(now) >= self.max_count

    def utilization(self, now: Optional[float] = None) -> float:
        """Budget utilization ratio (0-1)."""
        count = self.count_in_window(now)
        return min(1.0, count / max(1, self.max_count))

    def _prune(self, cutoff: float):
        """Remove timestamps older than cutoff."""
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def to_dict(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = now or time.time()
        return {
            'category': self.category.value,
            'period': self.period.name.lower(),
            'period_seconds': self.period.value,
            'max_count': self.max_count,
            'current_count': self.count_in_window(now),
            'remaining': self.remaining(now),
            'utilization': round(self.utilization(now), 3),
            'exhausted': self.is_exhausted(now),
        }


class AutonomyBudgetManager:
    """
    Category-specific rate limits for autonomous actions (P3.44).

    Tracks usage across multiple categories with different time windows.
    When a budget is exhausted, the system escalates to user approval.
    """

    def __init__(
        self,
        shell_commands_per_hour: int = 50,
        file_writes_per_hour: int = 10,
        coding_jobs_per_day: int = 5,
        llm_tokens_per_minute: int = 1000,
        network_calls_per_hour: int = 30,
        tasks_per_hour: int = 50,
        escalation_threshold: float = 0.8,
    ):
        """
        Args:
            shell_commands_per_hour: Max shell commands per hour
            file_writes_per_hour: Max file writes per hour
            coding_jobs_per_day: Max coding jobs per day
            llm_tokens_per_minute: Max LLM tokens per minute
            network_calls_per_hour: Max network calls per hour
            tasks_per_hour: Max general task executions per hour
            escalation_threshold: Utilization ratio above which to warn
        """
        self.escalation_threshold = escalation_threshold

        self._limits: Dict[str, BudgetLimit] = {
            'shell_hour': BudgetLimit(
                category=BudgetCategory.SHELL_COMMAND,
                period=BudgetPeriod.HOUR,
                max_count=shell_commands_per_hour,
                description=f"Shell commands: max {shell_commands_per_hour}/hour",
            ),
            'file_hour': BudgetLimit(
                category=BudgetCategory.FILE_WRITE,
                period=BudgetPeriod.HOUR,
                max_count=file_writes_per_hour,
                description=f"File writes: max {file_writes_per_hour}/hour",
            ),
            'coding_day': BudgetLimit(
                category=BudgetCategory.CODING_JOB,
                period=BudgetPeriod.DAY,
                max_count=coding_jobs_per_day,
                description=f"Coding jobs: max {coding_jobs_per_day}/day",
            ),
            'llm_minute': BudgetLimit(
                category=BudgetCategory.LLM_TOKEN,
                period=BudgetPeriod.MINUTE,
                max_count=llm_tokens_per_minute,
                description=f"LLM tokens: max {llm_tokens_per_minute}/minute",
            ),
            'network_hour': BudgetLimit(
                category=BudgetCategory.NETWORK_CALL,
                period=BudgetPeriod.HOUR,
                max_count=network_calls_per_hour,
                description=f"Network calls: max {network_calls_per_hour}/hour",
            ),
            'task_hour': BudgetLimit(
                category=BudgetCategory.TASK_EXECUTION,
                period=BudgetPeriod.HOUR,
                max_count=tasks_per_hour,
                description=f"Tasks: max {tasks_per_hour}/hour",
            ),
        }

        # Statistics
        self._total_allowed: int = 0
        self._total_denied: int = 0
        self._total_escalated: int = 0
        self._denial_history: deque = deque(maxlen=100)

    def can_perform(self, category: BudgetCategory) -> bool:
        """
        Check if an action in this category is within budget.

        Returns True if action is allowed, False if budget exhausted.
        """
        for limit in self._limits.values():
            if limit.category == category:
                if limit.is_exhausted():
                    self._total_denied += 1
                    self._denial_history.append({
                        'category': category.value,
                        'time': time.time(),
                        'reason': f"Budget exhausted: {limit.description}",
                    })
                    return False
        return True

    def record_action(self, category: BudgetCategory, count: int = 1):
        """Record that an action was performed (for budget tracking)."""
        now = time.time()
        for limit in self._limits.values():
            if limit.category == category:
                for _ in range(count):
                    limit.record(now)
        self._total_allowed += 1

    def should_escalate(self, category: BudgetCategory) -> bool:
        """
        Check if we should escalate (warn user) for this category.
        Returns True if utilization > escalation_threshold.
        """
        for limit in self._limits.values():
            if limit.category == category:
                if limit.utilization() > self.escalation_threshold:
                    self._total_escalated += 1
                    return True
        return False

    def get_budget_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all budget limits."""
        now = time.time()
        return {
            name: limit.to_dict(now)
            for name, limit in self._limits.items()
        }

    def get_category_remaining(self, category: BudgetCategory) -> int:
        """Get remaining actions for a category (uses first matching limit)."""
        for limit in self._limits.values():
            if limit.category == category:
                return limit.remaining()
        return 999  # No limit configured

    def reset_category(self, category: BudgetCategory):
        """Reset a category's usage history (admin override)."""
        for limit in self._limits.values():
            if limit.category == category:
                limit.timestamps.clear()

    def get_state(self) -> Dict[str, Any]:
        """Get complete budget state for dashboard."""
        return {
            'name': 'AutonomyBudgetManager',
            'total_allowed': self._total_allowed,
            'total_denied': self._total_denied,
            'total_escalated': self._total_escalated,
            'escalation_threshold': self.escalation_threshold,
            'budgets': self.get_budget_status(),
            'recent_denials': list(self._denial_history)[-10:],
        }


# ─── Safety Governor (P3.45) ──────────────────────────────────────────────────

class SafetyVerdict(Enum):
    """Result of a safety check."""
    APPROVE = "approve"          # Action is safe to proceed
    DENY = "deny"                # Action is blocked
    ESCALATE = "escalate"        # Needs user approval


class VetoReason(Enum):
    """Reasons for denying an action."""
    DESTRUCTIVE_COMMAND = "destructive_command"
    PATH_VIOLATION = "path_violation"
    UNKNOWN_HOST = "unknown_host"
    CPU_LIMIT_EXCEEDED = "cpu_limit_exceeded"
    SENSITIVE_DATA = "sensitive_data"
    RATE_LIMITED = "rate_limited"
    UNKNOWN_ACTION = "unknown_action"


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    verdict: SafetyVerdict
    reason: Optional[VetoReason] = None
    message: str = ""
    confidence: float = 1.0     # How confident are we in this decision
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'verdict': self.verdict.value,
            'reason': self.reason.value if self.reason else None,
            'message': self.message,
            'confidence': round(self.confidence, 3),
            'details': self.details,
        }


class SafetyGovernor:
    """
    Safety veto system for dangerous autonomous actions (P3.45).

    Checks actions before execution against a set of safety rules:
    1. Destructive command patterns (rm -rf, DROP TABLE, etc.)
    2. File path access restrictions (only within allowed directories)
    3. Network access restrictions (only to allowed hosts)
    4. CPU time limits
    5. Sensitive data handling

    The governor can:
    - APPROVE: Action is safe
    - DENY: Action is blocked (returns immediately)
    - ESCALATE: Action needs user approval before proceeding
    """

    def __init__(
        self,
        allowed_paths: Optional[List[str]] = None,
        allowed_hosts: Optional[List[str]] = None,
        max_cpu_seconds: float = 300.0,
        destructive_pattern_override: Optional[List[str]] = None,
        enable_path_check: bool = True,
        enable_host_check: bool = True,
        enable_destructive_check: bool = True,
        enable_cpu_check: bool = True,
    ):
        """
        Args:
            allowed_paths: List of allowed filesystem paths (parent dirs)
            allowed_hosts: List of allowed network hosts
            max_cpu_seconds: Max CPU seconds per action
            destructive_pattern_override: Extra destructive patterns to check
            enable_*: Toggle individual checks
        """
        self.allowed_paths = allowed_paths or []
        self.allowed_hosts = allowed_hosts or [
            'localhost', '127.0.0.1', '0.0.0.0',
        ]
        self.max_cpu_seconds = max_cpu_seconds
        self.enable_path_check = enable_path_check
        self.enable_host_check = enable_host_check
        self.enable_destructive_check = enable_destructive_check
        self.enable_cpu_check = enable_cpu_check

        # Destructive command patterns (case-insensitive)
        self._destructive_patterns = [
            r'rm\s+(-[rfRF]+\s+)?/',          # rm -rf /
            r'rm\s+(-[rfRF]+\s+)?\*',         # rm -rf *
            r'rmdir\s+/s',                      # rmdir /s (Windows)
            r'del\s+/[sfSF]',                   # del /s /f (Windows)
            r'format\s+[a-zA-Z]:',             # format C:
            r'DROP\s+(TABLE|DATABASE|SCHEMA)',  # SQL drops
            r'TRUNCATE\s+TABLE',               # SQL truncate
            r'DELETE\s+FROM\s+\S+\s*$',        # DELETE without WHERE
            r'mkfs\.',                          # Filesystem format
            r'dd\s+if=.*\s+of=/',              # dd to disk
            r'>\s*/dev/sd[a-z]',               # Redirect to block device
            r'chmod\s+-R\s+777\s+/',           # Recursive 777 from root
            r'shutdown\s+',                      # System shutdown
            r'reboot',                           # System reboot
            r'init\s+[06]',                     # Init shutdown/reboot
        ]

        if destructive_pattern_override:
            self._destructive_patterns.extend(destructive_pattern_override)

        # Compile patterns
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self._destructive_patterns
        ]

        # Sensitive data patterns
        self._sensitive_patterns = [
            re.compile(r'password\s*[=:]\s*\S+', re.IGNORECASE),
            re.compile(r'api[_-]?key\s*[=:]\s*\S+', re.IGNORECASE),
            re.compile(r'secret\s*[=:]\s*\S+', re.IGNORECASE),
            re.compile(r'token\s*[=:]\s*[A-Za-z0-9_-]{20,}', re.IGNORECASE),
        ]

        # Statistics
        self._total_checks: int = 0
        self._total_approved: int = 0
        self._total_denied: int = 0
        self._total_escalated: int = 0
        self._veto_history: deque = deque(maxlen=100)

    def check_action(
        self,
        action_description: str,
        action_type: str = 'general',
        target_path: Optional[str] = None,
        target_host: Optional[str] = None,
        estimated_cpu_seconds: Optional[float] = None,
    ) -> SafetyCheckResult:
        """
        Check if an action is safe to perform.

        Args:
            action_description: Human-readable description of the action
            action_type: Type of action (shell, file_write, network, etc.)
            target_path: Filesystem path being accessed
            target_host: Network host being contacted
            estimated_cpu_seconds: Estimated CPU time

        Returns:
            SafetyCheckResult with verdict (APPROVE/DENY/ESCALATE)
        """
        self._total_checks += 1

        # ── 1. Check for destructive commands ──
        if self.enable_destructive_check:
            result = self._check_destructive(action_description)
            if result.verdict != SafetyVerdict.APPROVE:
                self._record_veto(result)
                return result

        # ── 2. Check file path access ──
        if self.enable_path_check and target_path:
            result = self._check_path(target_path)
            if result.verdict != SafetyVerdict.APPROVE:
                self._record_veto(result)
                return result

        # ── 3. Check network host access ──
        if self.enable_host_check and target_host:
            result = self._check_host(target_host)
            if result.verdict != SafetyVerdict.APPROVE:
                self._record_veto(result)
                return result

        # ── 4. Check CPU time limit ──
        if self.enable_cpu_check and estimated_cpu_seconds is not None:
            result = self._check_cpu(estimated_cpu_seconds)
            if result.verdict != SafetyVerdict.APPROVE:
                self._record_veto(result)
                return result

        # ── 5. Check for sensitive data exposure ──
        result = self._check_sensitive_data(action_description)
        if result.verdict != SafetyVerdict.APPROVE:
            self._record_veto(result)
            return result

        # All checks passed
        self._total_approved += 1
        return SafetyCheckResult(
            verdict=SafetyVerdict.APPROVE,
            message="Action approved by SafetyGovernor",
        )

    def _check_destructive(self, description: str) -> SafetyCheckResult:
        """Check for destructive command patterns."""
        for pattern in self._compiled_patterns:
            if pattern.search(description):
                self._total_denied += 1
                return SafetyCheckResult(
                    verdict=SafetyVerdict.DENY,
                    reason=VetoReason.DESTRUCTIVE_COMMAND,
                    message=f"Destructive command detected: {pattern.pattern}",
                    confidence=0.95,
                    details={'pattern': pattern.pattern},
                )
        return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

    def _check_path(self, path: str) -> SafetyCheckResult:
        """Check if path is within allowed directories."""
        if not self.allowed_paths:
            return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

        # Normalize path
        try:
            norm_path = os.path.normpath(os.path.abspath(path))
        except (ValueError, OSError):
            norm_path = path

        for allowed in self.allowed_paths:
            try:
                norm_allowed = os.path.normpath(os.path.abspath(allowed))
                if norm_path.startswith(norm_allowed):
                    return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)
            except (ValueError, OSError):
                if path.startswith(allowed):
                    return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

        # Path not in allowed list → escalate (not deny, user might approve)
        self._total_escalated += 1
        return SafetyCheckResult(
            verdict=SafetyVerdict.ESCALATE,
            reason=VetoReason.PATH_VIOLATION,
            message=f"Path '{path}' is outside allowed directories",
            confidence=0.9,
            details={
                'requested_path': path,
                'allowed_paths': self.allowed_paths,
            },
        )

    def _check_host(self, host: str) -> SafetyCheckResult:
        """Check if host is in the allowed list."""
        if not self.allowed_hosts:
            return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

        host_lower = host.lower().strip()
        for allowed in self.allowed_hosts:
            if host_lower == allowed.lower().strip():
                return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

        # Unknown host → escalate
        self._total_escalated += 1
        return SafetyCheckResult(
            verdict=SafetyVerdict.ESCALATE,
            reason=VetoReason.UNKNOWN_HOST,
            message=f"Host '{host}' is not in the allowed hosts list",
            confidence=0.85,
            details={
                'requested_host': host,
                'allowed_hosts': self.allowed_hosts[:10],  # Don't expose full list
            },
        )

    def _check_cpu(self, estimated_seconds: float) -> SafetyCheckResult:
        """Check if estimated CPU time is within limits."""
        if estimated_seconds <= self.max_cpu_seconds:
            return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

        self._total_escalated += 1
        return SafetyCheckResult(
            verdict=SafetyVerdict.ESCALATE,
            reason=VetoReason.CPU_LIMIT_EXCEEDED,
            message=f"Estimated CPU time ({estimated_seconds:.0f}s) exceeds "
                    f"limit ({self.max_cpu_seconds:.0f}s)",
            confidence=0.7,  # CPU estimates are uncertain
            details={
                'estimated_seconds': estimated_seconds,
                'max_seconds': self.max_cpu_seconds,
            },
        )

    def _check_sensitive_data(self, description: str) -> SafetyCheckResult:
        """Check if the action exposes sensitive data."""
        for pattern in self._sensitive_patterns:
            if pattern.search(description):
                self._total_escalated += 1
                return SafetyCheckResult(
                    verdict=SafetyVerdict.ESCALATE,
                    reason=VetoReason.SENSITIVE_DATA,
                    message="Action may expose sensitive data (API keys, passwords, etc.)",
                    confidence=0.8,
                    details={'pattern': pattern.pattern},
                )
        return SafetyCheckResult(verdict=SafetyVerdict.APPROVE)

    def add_allowed_path(self, path: str):
        """Add a path to the allowed paths list."""
        if path not in self.allowed_paths:
            self.allowed_paths.append(path)

    def add_allowed_host(self, host: str):
        """Add a host to the allowed hosts list."""
        if host.lower() not in [h.lower() for h in self.allowed_hosts]:
            self.allowed_hosts.append(host)

    def _record_veto(self, result: SafetyCheckResult):
        """Record a veto/escalation event."""
        self._veto_history.append({
            'verdict': result.verdict.value,
            'reason': result.reason.value if result.reason else None,
            'message': result.message,
            'time': time.time(),
        })

    def get_state(self) -> Dict[str, Any]:
        """Get governor state for dashboard."""
        return {
            'name': 'SafetyGovernor',
            'total_checks': self._total_checks,
            'total_approved': self._total_approved,
            'total_denied': self._total_denied,
            'total_escalated': self._total_escalated,
            'approval_rate': (
                round(self._total_approved / max(1, self._total_checks), 3)
            ),
            'config': {
                'allowed_paths_count': len(self.allowed_paths),
                'allowed_hosts_count': len(self.allowed_hosts),
                'max_cpu_seconds': self.max_cpu_seconds,
                'checks_enabled': {
                    'destructive': self.enable_destructive_check,
                    'path': self.enable_path_check,
                    'host': self.enable_host_check,
                    'cpu': self.enable_cpu_check,
                },
            },
            'recent_vetoes': list(self._veto_history)[-10:],
        }


# ─── Combined Safety System ─────────────────────────────────────────────────

class SafetyRegulation:
    """
    Combines AutonomyBudgetManager and SafetyGovernor into a unified interface.

    The AgentLoop calls `check_action()` before executing any task.
    Results determine whether the task proceeds, is blocked, or needs approval.
    """

    def __init__(
        self,
        budget: Optional[AutonomyBudgetManager] = None,
        governor: Optional[SafetyGovernor] = None,
    ):
        self.budget = budget or AutonomyBudgetManager()
        self.governor = governor or SafetyGovernor()

        self._total_checks: int = 0
        self._total_blocks: int = 0

    def check_and_record(
        self,
        action_description: str,
        category: BudgetCategory = BudgetCategory.TASK_EXECUTION,
        action_type: str = 'general',
        target_path: Optional[str] = None,
        target_host: Optional[str] = None,
        estimated_cpu_seconds: Optional[float] = None,
        skip_budget_check: bool = False,
    ) -> SafetyCheckResult:
        """
        Full safety check: budget + governor.

        Args:
            action_description: What the action does
            category: Budget category for rate limiting
            action_type: Type of action for governor
            target_path: File path being accessed
            target_host: Network host being contacted
            estimated_cpu_seconds: Estimated CPU time
            skip_budget_check: True for USER_REQUEST tasks (bypass budget)

        Returns:
            SafetyCheckResult with verdict
        """
        self._total_checks += 1

        # ── 1. Budget check (skip for user requests) ──
        if not skip_budget_check:
            if not self.budget.can_perform(category):
                self._total_blocks += 1
                return SafetyCheckResult(
                    verdict=SafetyVerdict.ESCALATE,
                    reason=VetoReason.RATE_LIMITED,
                    message=f"Autonomy budget exhausted for '{category.value}'. "
                            f"Remaining: {self.budget.get_category_remaining(category)}",
                    confidence=1.0,
                    details={
                        'category': category.value,
                        'remaining': self.budget.get_category_remaining(category),
                    },
                )

            # Check if we should warn about approaching limit
            if self.budget.should_escalate(category):
                logger.warning(
                    f"Autonomy budget warning: '{category.value}' approaching limit "
                    f"(remaining: {self.budget.get_category_remaining(category)})"
                )

        # ── 2. Safety governor check ──
        result = self.governor.check_action(
            action_description=action_description,
            action_type=action_type,
            target_path=target_path,
            target_host=target_host,
            estimated_cpu_seconds=estimated_cpu_seconds,
        )

        if result.verdict == SafetyVerdict.DENY:
            self._total_blocks += 1
            return result

        if result.verdict == SafetyVerdict.ESCALATE:
            return result

        # ── 3. Record in budget (action approved) ──
        if not skip_budget_check:
            self.budget.record_action(category)

        return result

    def get_state(self) -> Dict[str, Any]:
        """Get complete safety regulation state."""
        return {
            'total_checks': self._total_checks,
            'total_blocks': self._total_blocks,
            'budget': self.budget.get_state(),
            'governor': self.governor.get_state(),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'SafetyRegulation':
        """Create SafetyRegulation from YAML config dict."""
        s = config.get('safety_regulation', {})

        budget = AutonomyBudgetManager(
            shell_commands_per_hour=s.get('shell_commands_per_hour', 50),
            file_writes_per_hour=s.get('file_writes_per_hour', 10),
            coding_jobs_per_day=s.get('coding_jobs_per_day', 5),
            llm_tokens_per_minute=s.get('llm_tokens_per_minute', 1000),
            network_calls_per_hour=s.get('network_calls_per_hour', 30),
            tasks_per_hour=s.get('tasks_per_hour', 50),
            escalation_threshold=s.get('escalation_threshold', 0.8),
        )

        governor = SafetyGovernor(
            allowed_paths=s.get('allowed_paths', []),
            allowed_hosts=s.get('allowed_hosts', [
                'localhost', '127.0.0.1', '0.0.0.0',
            ]),
            max_cpu_seconds=s.get('max_cpu_seconds', 300.0),
            enable_path_check=s.get('enable_path_check', True),
            enable_host_check=s.get('enable_host_check', True),
            enable_destructive_check=s.get('enable_destructive_check', True),
            enable_cpu_check=s.get('enable_cpu_check', True),
        )

        return cls(budget=budget, governor=governor)

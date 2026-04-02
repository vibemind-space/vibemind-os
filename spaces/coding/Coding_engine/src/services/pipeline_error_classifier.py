"""Pipeline error classifier — classifies errors by type, severity, and recovery."""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SEVERITY_LEVELS = ("low", "medium", "high", "critical")

ERROR_CATEGORIES = (
    "syntax", "runtime", "timeout", "resource", "network",
    "permission", "configuration", "dependency", "unknown",
)

RECOVERY_ACTIONS = {
    "syntax": "fix_code",
    "runtime": "retry_with_backoff",
    "timeout": "increase_timeout",
    "resource": "free_resources",
    "network": "retry_connection",
    "permission": "check_permissions",
    "configuration": "validate_config",
    "dependency": "resolve_dependencies",
    "unknown": "investigate",
}


@dataclass
class ClassificationRule:
    """A rule for classifying errors."""
    rule_id: str
    name: str
    pattern: str  # regex pattern
    category: str
    severity: str
    recovery_action: str = ""
    priority: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)
    match_count: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class ClassifiedError:
    """A classified error record."""
    error_id: str
    message: str
    category: str
    severity: str
    recovery_action: str
    matched_rule: str
    source: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineErrorClassifier:
    """Classifies pipeline errors with rules, patterns, and statistics."""

    def __init__(self, max_rules: int = 500, max_errors: int = 10000):
        self._rules: Dict[str, ClassificationRule] = {}
        self._errors: Dict[str, ClassifiedError] = {}
        self._max_rules = max_rules
        self._max_errors = max_errors
        self._callbacks: Dict[str, Any] = {}

        # Stats
        self._total_classified = 0
        self._total_unclassified = 0

        # Install default rules
        self._install_defaults()

    def _install_defaults(self) -> None:
        """Install built-in classification rules."""
        defaults = [
            ("syntax_error", "SyntaxError", r"(?i)syntax\s*error|unexpected token|parse error",
             "syntax", "high", "fix_code", 10),
            ("name_error", "NameError", r"(?i)name\s*error|undefined variable|not defined",
             "runtime", "high", "fix_code", 10),
            ("type_error", "TypeError", r"(?i)type\s*error|not callable|unsupported operand",
             "runtime", "high", "fix_code", 10),
            ("import_error", "ImportError", r"(?i)import\s*error|module not found|no module named",
             "dependency", "high", "resolve_dependencies", 10),
            ("timeout", "Timeout", r"(?i)timeout|timed?\s*out|deadline exceeded",
             "timeout", "medium", "increase_timeout", 10),
            ("connection_error", "ConnectionError", r"(?i)connection\s*(refused|reset|error)|ECONNREFUSED|ECONNRESET",
             "network", "medium", "retry_connection", 10),
            ("permission_denied", "PermissionDenied", r"(?i)permission\s*denied|access\s*denied|forbidden|EACCES",
             "permission", "high", "check_permissions", 10),
            ("out_of_memory", "OutOfMemory", r"(?i)out\s*of\s*memory|OOM|memory\s*error|heap\s*space",
             "resource", "critical", "free_resources", 10),
            ("disk_full", "DiskFull", r"(?i)disk\s*full|no\s*space|ENOSPC",
             "resource", "critical", "free_resources", 10),
            ("config_error", "ConfigError", r"(?i)config\s*(error|invalid|missing)|invalid\s*configuration",
             "configuration", "medium", "validate_config", 10),
            ("file_not_found", "FileNotFound", r"(?i)file\s*not\s*found|ENOENT|no\s*such\s*file",
             "runtime", "medium", "investigate", 10),
        ]
        for rule_id, name, pattern, cat, sev, action, pri in defaults:
            self._rules[rule_id] = ClassificationRule(
                rule_id=rule_id, name=name, pattern=pattern,
                category=cat, severity=sev, recovery_action=action,
                priority=pri,
            )

    # ── Rule Management ──

    def add_rule(self, name: str, pattern: str, category: str, severity: str,
                 recovery_action: str = "", priority: int = 50,
                 metadata: Optional[Dict] = None) -> str:
        """Add a classification rule. Returns rule_id or empty string."""
        if category not in ERROR_CATEGORIES:
            return ""
        if severity not in SEVERITY_LEVELS:
            return ""
        if len(self._rules) >= self._max_rules:
            return ""

        # Validate regex
        try:
            re.compile(pattern)
        except re.error:
            return ""

        rule_id = f"rule-{uuid.uuid4().hex[:8]}"
        if not recovery_action:
            recovery_action = RECOVERY_ACTIONS.get(category, "investigate")

        self._rules[rule_id] = ClassificationRule(
            rule_id=rule_id,
            name=name,
            pattern=pattern,
            category=category,
            severity=severity,
            recovery_action=recovery_action,
            priority=priority,
            metadata=metadata or {},
        )
        return rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a classification rule."""
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        return True

    def get_rule(self, rule_id: str) -> Optional[Dict]:
        """Get rule info."""
        rule = self._rules.get(rule_id)
        if rule is None:
            return None
        return {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "pattern": rule.pattern,
            "category": rule.category,
            "severity": rule.severity,
            "recovery_action": rule.recovery_action,
            "priority": rule.priority,
            "match_count": rule.match_count,
            "metadata": dict(rule.metadata),
        }

    def list_rules(self, category: str = "", limit: int = 50) -> List[Dict]:
        """List rules with optional category filter."""
        result = []
        for rule in sorted(self._rules.values(), key=lambda r: -r.priority):
            if category and rule.category != category:
                continue
            info = self.get_rule(rule.rule_id)
            if info:
                result.append(info)
            if len(result) >= limit:
                break
        return result

    # ── Classification ──

    def classify(self, message: str, source: str = "",
                 metadata: Optional[Dict] = None) -> Dict:
        """Classify an error message. Returns classification result."""
        if not message:
            return {
                "error_id": "",
                "category": "unknown",
                "severity": "low",
                "recovery_action": "investigate",
                "matched_rule": "",
                "classified": False,
            }

        # Try rules in priority order (highest first)
        sorted_rules = sorted(self._rules.values(), key=lambda r: -r.priority)
        for rule in sorted_rules:
            try:
                if re.search(rule.pattern, message):
                    rule.match_count += 1
                    error_id = self._record_error(
                        message, rule.category, rule.severity,
                        rule.recovery_action, rule.rule_id, source, metadata,
                    )
                    self._total_classified += 1
                    self._fire_callbacks(error_id, rule.category, rule.severity)
                    return {
                        "error_id": error_id,
                        "category": rule.category,
                        "severity": rule.severity,
                        "recovery_action": rule.recovery_action,
                        "matched_rule": rule.rule_id,
                        "rule_name": rule.name,
                        "classified": True,
                    }
            except re.error:
                continue

        # No match
        error_id = self._record_error(
            message, "unknown", "low", "investigate", "", source, metadata,
        )
        self._total_unclassified += 1
        return {
            "error_id": error_id,
            "category": "unknown",
            "severity": "low",
            "recovery_action": "investigate",
            "matched_rule": "",
            "classified": False,
        }

    def classify_batch(self, messages: List[str], source: str = "") -> List[Dict]:
        """Classify multiple error messages."""
        return [self.classify(m, source=source) for m in messages]

    def _record_error(self, message: str, category: str, severity: str,
                      recovery_action: str, matched_rule: str, source: str,
                      metadata: Optional[Dict]) -> str:
        """Record a classified error."""
        # Prune if at max
        if len(self._errors) >= self._max_errors:
            oldest = min(self._errors.values(), key=lambda e: e.created_at)
            del self._errors[oldest.error_id]

        error_id = f"err-{uuid.uuid4().hex[:8]}"
        self._errors[error_id] = ClassifiedError(
            error_id=error_id,
            message=message[:500],
            category=category,
            severity=severity,
            recovery_action=recovery_action,
            matched_rule=matched_rule,
            source=source,
            metadata=metadata or {},
        )
        return error_id

    # ── Error Queries ──

    def get_error(self, error_id: str) -> Optional[Dict]:
        """Get a classified error."""
        err = self._errors.get(error_id)
        if err is None:
            return None
        return {
            "error_id": err.error_id,
            "message": err.message,
            "category": err.category,
            "severity": err.severity,
            "recovery_action": err.recovery_action,
            "matched_rule": err.matched_rule,
            "source": err.source,
            "created_at": err.created_at,
            "metadata": dict(err.metadata),
        }

    def list_errors(self, category: str = "", severity: str = "",
                    source: str = "", limit: int = 50) -> List[Dict]:
        """List errors with optional filters."""
        result = []
        for err in sorted(self._errors.values(), key=lambda e: -e.created_at):
            if category and err.category != category:
                continue
            if severity and err.severity != severity:
                continue
            if source and err.source != source:
                continue
            info = self.get_error(err.error_id)
            if info:
                result.append(info)
            if len(result) >= limit:
                break
        return result

    def search_errors(self, query: str, limit: int = 20) -> List[Dict]:
        """Search errors by message content."""
        query_lower = query.lower()
        result = []
        for err in self._errors.values():
            if query_lower in err.message.lower():
                info = self.get_error(err.error_id)
                if info:
                    result.append(info)
                if len(result) >= limit:
                    break
        return result

    def delete_error(self, error_id: str) -> bool:
        """Delete an error record."""
        if error_id not in self._errors:
            return False
        del self._errors[error_id]
        return True

    # ── Analytics ──

    def get_category_counts(self) -> Dict[str, int]:
        """Count errors by category."""
        counts: Dict[str, int] = {}
        for err in self._errors.values():
            counts[err.category] = counts.get(err.category, 0) + 1
        return counts

    def get_severity_counts(self) -> Dict[str, int]:
        """Count errors by severity."""
        counts: Dict[str, int] = {}
        for err in self._errors.values():
            counts[err.severity] = counts.get(err.severity, 0) + 1
        return counts

    def get_top_rules(self, limit: int = 10) -> List[Dict]:
        """Get most matched rules."""
        rules = sorted(self._rules.values(), key=lambda r: -r.match_count)
        result = []
        for rule in rules[:limit]:
            if rule.match_count > 0:
                result.append({
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "match_count": rule.match_count,
                    "category": rule.category,
                })
        return result

    def get_source_counts(self) -> Dict[str, int]:
        """Count errors by source."""
        counts: Dict[str, int] = {}
        for err in self._errors.values():
            if err.source:
                counts[err.source] = counts.get(err.source, 0) + 1
        return counts

    # ── Callbacks ──

    def on_error(self, name: str, callback) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, error_id: str, category: str, severity: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(error_id, category, severity)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            "total_rules": len(self._rules),
            "total_errors": len(self._errors),
            "total_classified": self._total_classified,
            "total_unclassified": self._total_unclassified,
            "classification_rate": round(
                self._total_classified / max(1, self._total_classified + self._total_unclassified) * 100, 1
            ),
        }

    def reset(self) -> None:
        self._rules.clear()
        self._errors.clear()
        self._callbacks.clear()
        self._total_classified = 0
        self._total_unclassified = 0
        self._install_defaults()

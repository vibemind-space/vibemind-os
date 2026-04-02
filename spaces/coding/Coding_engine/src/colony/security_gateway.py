"""
Security Gateway - Central security verification and credential management.

Provides a unified security interface for the Cell Colony:
- Credential distribution with time-limited tokens
- Access control enforcement with RBAC
- Audit logging for all security-sensitive operations
- Rate limiting for sensitive endpoints
- Security event monitoring and alerting
"""

import asyncio
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

import structlog

from src.security.vault_client import VaultSecretManager, VaultConfig, CellSecretPolicy
from src.security.llm_security import LLMSecurityMiddleware
from src.security.supply_chain import SupplyChainSecurity
from src.mind.event_bus import EventBus, Event

logger = structlog.get_logger()


class SecurityEventType(str, Enum):
    """Types of security events for audit and alerting."""
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    TOKEN_ISSUED = "token_issued"
    TOKEN_REVOKED = "token_revoked"
    TOKEN_EXPIRED = "token_expired"
    SECRET_ACCESSED = "secret_accessed"
    SECRET_ROTATED = "secret_rotated"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    MUTATION_APPROVED = "mutation_approved"
    MUTATION_REJECTED = "mutation_rejected"
    SECURITY_SCAN_COMPLETED = "security_scan_completed"
    VULNERABILITY_DETECTED = "vulnerability_detected"


class AccessLevel(str, Enum):
    """Access levels for RBAC."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"


class ResourceType(str, Enum):
    """Types of resources that can be protected."""
    CELL = "cell"
    SECRET = "secret"
    CONFIG = "config"
    LOG = "log"
    MUTATION = "mutation"
    COLONY = "colony"
    NAMESPACE = "namespace"


@dataclass
class SecurityToken:
    """Time-limited security token for cells and services."""
    id: str
    cell_id: Optional[str]
    tenant_id: Optional[str]
    policies: List[str]
    scopes: List[str]
    issued_at: datetime
    expires_at: datetime
    renewable: bool = True
    max_renewals: int = 5
    renewal_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def time_remaining(self) -> int:
        """Get seconds remaining until expiry."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))

    @property
    def can_renew(self) -> bool:
        """Check if token can be renewed."""
        return self.renewable and self.renewal_count < self.max_renewals

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "cell_id": self.cell_id,
            "tenant_id": self.tenant_id,
            "policies": self.policies,
            "scopes": self.scopes,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "renewable": self.renewable,
            "time_remaining": self.time_remaining,
        }


@dataclass
class SecurityAuditEntry:
    """Audit log entry for security events."""
    id: str
    timestamp: datetime
    event_type: SecurityEventType
    actor_id: Optional[str]  # Cell ID, user ID, or service ID
    actor_type: str  # "cell", "user", "service", "system"
    resource_type: ResourceType
    resource_id: str
    action: str
    success: bool
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "action": self.action,
            "success": self.success,
            "ip_address": self.ip_address,
            "error": self.error,
            "details": self.details,
        }


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10
    cooldown_seconds: int = 60


@dataclass
class AccessRule:
    """Access control rule."""
    resource_type: ResourceType
    resource_pattern: str  # Glob pattern or specific ID
    allowed_actions: Set[str]
    required_level: AccessLevel
    conditions: Dict[str, Any] = field(default_factory=dict)


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed.

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        async with self._lock:
            now = time.time()

            if key not in self._buckets:
                self._buckets[key] = {
                    "tokens": self.config.burst_limit,
                    "last_update": now,
                    "requests_minute": [],
                    "requests_hour": [],
                }

            bucket = self._buckets[key]

            # Refill tokens based on time passed
            time_passed = now - bucket["last_update"]
            tokens_to_add = time_passed * (self.config.requests_per_minute / 60)
            bucket["tokens"] = min(self.config.burst_limit, bucket["tokens"] + tokens_to_add)
            bucket["last_update"] = now

            # Clean old request timestamps
            minute_ago = now - 60
            hour_ago = now - 3600
            bucket["requests_minute"] = [t for t in bucket["requests_minute"] if t > minute_ago]
            bucket["requests_hour"] = [t for t in bucket["requests_hour"] if t > hour_ago]

            # Check limits
            if bucket["tokens"] < 1:
                return False, self.config.cooldown_seconds

            if len(bucket["requests_minute"]) >= self.config.requests_per_minute:
                return False, 60

            if len(bucket["requests_hour"]) >= self.config.requests_per_hour:
                return False, 3600

            # Consume token
            bucket["tokens"] -= 1
            bucket["requests_minute"].append(now)
            bucket["requests_hour"].append(now)

            return True, None

    async def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        async with self._lock:
            self._buckets.pop(key, None)


class AccessController:
    """Role-Based Access Control (RBAC) implementation."""

    def __init__(self):
        self._rules: List[AccessRule] = []
        self._role_permissions: Dict[str, Set[str]] = {
            "viewer": {"read"},
            "developer": {"read", "write", "execute"},
            "admin": {"read", "write", "execute", "delete", "admin"},
            "owner": {"read", "write", "execute", "delete", "admin", "transfer"},
        }
        self._user_roles: Dict[str, Dict[str, str]] = {}  # user_id -> {resource_id: role}
        self.logger = logger.bind(component="AccessController")

    def add_rule(self, rule: AccessRule) -> None:
        """Add an access control rule."""
        self._rules.append(rule)

    def assign_role(self, user_id: str, resource_id: str, role: str) -> None:
        """Assign a role to a user for a resource."""
        if user_id not in self._user_roles:
            self._user_roles[user_id] = {}
        self._user_roles[user_id][resource_id] = role

    def revoke_role(self, user_id: str, resource_id: str) -> None:
        """Revoke a user's role for a resource."""
        if user_id in self._user_roles:
            self._user_roles[user_id].pop(resource_id, None)

    def check_access(
        self,
        actor_id: str,
        resource_type: ResourceType,
        resource_id: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if actor has permission to perform action on resource.

        Returns:
            Tuple of (allowed, reason)
        """
        context = context or {}

        # Get actor's role for this resource
        user_roles = self._user_roles.get(actor_id, {})
        role = user_roles.get(resource_id) or user_roles.get("*")

        if not role:
            # Check namespace/parent resource roles
            parts = resource_id.split("/")
            for i in range(len(parts) - 1, 0, -1):
                parent = "/".join(parts[:i])
                if parent in user_roles:
                    role = user_roles[parent]
                    break

        if not role:
            return False, "No role assigned for resource"

        # Get permissions for role
        permissions = self._role_permissions.get(role, set())

        if action not in permissions:
            return False, f"Role '{role}' does not have '{action}' permission"

        # Check additional rules
        for rule in self._rules:
            if rule.resource_type != resource_type:
                continue

            # Check pattern match
            if not self._match_pattern(rule.resource_pattern, resource_id):
                continue

            # Check required level
            role_level = self._role_to_level(role)
            if role_level < self._level_value(rule.required_level):
                return False, f"Requires {rule.required_level.value} access"

            # Check conditions
            for key, value in rule.conditions.items():
                if context.get(key) != value:
                    return False, f"Condition not met: {key}"

        return True, None

    def _match_pattern(self, pattern: str, resource_id: str) -> bool:
        """Match glob-like pattern against resource ID."""
        if pattern == "*":
            return True
        if pattern.endswith("/*"):
            return resource_id.startswith(pattern[:-1])
        return pattern == resource_id

    def _role_to_level(self, role: str) -> int:
        """Convert role to numeric level."""
        levels = {"viewer": 1, "developer": 2, "admin": 3, "owner": 4}
        return levels.get(role, 0)

    def _level_value(self, level: AccessLevel) -> int:
        """Convert AccessLevel to numeric value."""
        values = {
            AccessLevel.NONE: 0,
            AccessLevel.READ: 1,
            AccessLevel.WRITE: 2,
            AccessLevel.ADMIN: 3,
            AccessLevel.OWNER: 4,
        }
        return values.get(level, 0)


class SecurityGateway:
    """
    Central security gateway for the Cell Colony system.

    Provides:
    - Unified security interface for all components
    - Token-based authentication with time limits
    - Role-based access control
    - Rate limiting for sensitive operations
    - Comprehensive audit logging
    - Security event monitoring and alerting
    - Integration with Vault for secret management
    """

    def __init__(
        self,
        vault_config: Optional[VaultConfig] = None,
        event_bus: Optional[EventBus] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ):
        self.logger = logger.bind(component="SecurityGateway")

        # Core components
        self.vault = VaultSecretManager(vault_config)
        self.event_bus = event_bus
        self.access_controller = AccessController()
        self.rate_limiter = RateLimiter(rate_limit_config or RateLimitConfig())

        # Token storage
        self._tokens: Dict[str, SecurityToken] = {}
        self._token_by_cell: Dict[str, str] = {}  # cell_id -> token_id

        # Audit log (in production, would use database)
        self._audit_log: List[SecurityAuditEntry] = []
        self._max_audit_entries = 50000

        # Alert thresholds
        self._alert_handlers: List[Callable[[SecurityAuditEntry], None]] = []
        self._suspicious_activity_threshold = 10  # Failed attempts before alert
        self._failed_attempts: Dict[str, int] = {}

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self) -> bool:
        """Initialize the security gateway."""
        self.logger.info("Initializing Security Gateway")

        try:
            # Initialize Vault
            vault_initialized = await self.vault.initialize()
            if not vault_initialized:
                self.logger.warning("Vault not available, running in limited mode")

            # Start background cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self.logger.info("Security Gateway initialized")
            return True

        except Exception as e:
            self.logger.error("Failed to initialize Security Gateway", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Shutdown the security gateway."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.vault.shutdown()
        self.logger.info("Security Gateway shutdown")

    # Token Management

    async def issue_token(
        self,
        cell_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        policies: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None,
        ttl_seconds: int = 3600,
        renewable: bool = True,
        max_renewals: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[SecurityToken]:
        """
        Issue a new security token.

        Args:
            cell_id: Cell identifier (if for a cell)
            tenant_id: Tenant identifier for multi-tenancy
            policies: Vault policies to attach
            scopes: OAuth-like scopes for fine-grained permissions
            ttl_seconds: Token lifetime in seconds
            renewable: Whether token can be renewed
            max_renewals: Maximum number of renewals allowed
            metadata: Additional metadata to attach

        Returns:
            SecurityToken or None if failed
        """
        self.logger.info("Issuing security token", cell_id=cell_id, ttl=ttl_seconds)

        now = datetime.now(timezone.utc)

        token = SecurityToken(
            id=f"sgt_{secrets.token_hex(24)}",
            cell_id=cell_id,
            tenant_id=tenant_id,
            policies=policies or [],
            scopes=scopes or ["read"],
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            renewable=renewable,
            max_renewals=max_renewals,
            metadata=metadata or {},
        )

        # Store token
        self._tokens[token.id] = token
        if cell_id:
            # Revoke any existing token for this cell
            old_token_id = self._token_by_cell.get(cell_id)
            if old_token_id:
                await self.revoke_token(old_token_id, reason="Replaced by new token")
            self._token_by_cell[cell_id] = token.id

        # Generate corresponding Vault token if policies specified
        if policies:
            vault_token = await self.vault.generate_cell_token(
                cell_id or token.id,
                policies,
                ttl=f"{ttl_seconds}s",
                renewable=renewable,
            )
            if vault_token:
                token.metadata["vault_token"] = vault_token

        # Audit log
        self._log_event(
            SecurityEventType.TOKEN_ISSUED,
            actor_id=cell_id,
            actor_type="cell" if cell_id else "system",
            resource_type=ResourceType.SECRET,
            resource_id=token.id,
            action="issue_token",
            success=True,
            details={"ttl": ttl_seconds, "policies": policies},
        )

        self.logger.info("Token issued", token_id=token.id[:16])
        return token

    async def validate_token(self, token_id: str) -> Tuple[bool, Optional[SecurityToken], Optional[str]]:
        """
        Validate a security token.

        Returns:
            Tuple of (valid, token, error_message)
        """
        token = self._tokens.get(token_id)

        if not token:
            return False, None, "Token not found"

        if token.is_expired:
            # Clean up expired token
            await self.revoke_token(token_id, reason="Expired")
            return False, None, "Token expired"

        return True, token, None

    async def renew_token(self, token_id: str, ttl_seconds: int = 3600) -> Tuple[bool, Optional[str]]:
        """
        Renew a security token.

        Returns:
            Tuple of (success, error_message)
        """
        valid, token, error = await self.validate_token(token_id)

        if not valid:
            return False, error

        if not token.can_renew:
            return False, "Token not renewable or max renewals exceeded"

        # Renew token
        token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        token.renewal_count += 1

        self._log_event(
            SecurityEventType.TOKEN_ISSUED,
            actor_id=token.cell_id,
            actor_type="cell" if token.cell_id else "system",
            resource_type=ResourceType.SECRET,
            resource_id=token_id,
            action="renew_token",
            success=True,
            details={"renewal_count": token.renewal_count},
        )

        self.logger.debug("Token renewed", token_id=token_id[:16], renewal=token.renewal_count)
        return True, None

    async def revoke_token(self, token_id: str, reason: str = "Manual revocation") -> bool:
        """Revoke a security token."""
        token = self._tokens.pop(token_id, None)

        if not token:
            return False

        # Remove cell mapping
        if token.cell_id:
            self._token_by_cell.pop(token.cell_id, None)

        # Revoke Vault token if exists
        vault_token = token.metadata.get("vault_token")
        if vault_token:
            await self.vault.revoke_cell_token(vault_token)

        self._log_event(
            SecurityEventType.TOKEN_REVOKED,
            actor_id=token.cell_id,
            actor_type="system",
            resource_type=ResourceType.SECRET,
            resource_id=token_id,
            action="revoke_token",
            success=True,
            details={"reason": reason},
        )

        self.logger.info("Token revoked", token_id=token_id[:16], reason=reason)
        return True

    # Access Control

    async def check_access(
        self,
        token_id: str,
        resource_type: ResourceType,
        resource_id: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if token holder has access to perform action on resource.

        Returns:
            Tuple of (allowed, reason)
        """
        # Validate token
        valid, token, error = await self.validate_token(token_id)
        if not valid:
            self._log_event(
                SecurityEventType.ACCESS_DENIED,
                actor_id=None,
                actor_type="unknown",
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                success=False,
                error=error,
            )
            return False, error

        # Check rate limit
        rate_key = f"{token.cell_id or token_id}:{action}"
        allowed, retry_after = await self.rate_limiter.check(rate_key)
        if not allowed:
            self._log_event(
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                actor_id=token.cell_id,
                actor_type="cell" if token.cell_id else "service",
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                success=False,
                details={"retry_after": retry_after},
            )
            return False, f"Rate limit exceeded. Retry after {retry_after}s"

        # Check scope
        if action == "read" and "read" not in token.scopes and "*" not in token.scopes:
            return False, "Token does not have read scope"
        if action in ("write", "delete") and "write" not in token.scopes and "*" not in token.scopes:
            return False, "Token does not have write scope"

        # Check RBAC
        actor_id = token.cell_id or token_id
        allowed, reason = self.access_controller.check_access(
            actor_id,
            resource_type,
            resource_id,
            action,
            context,
        )

        event_type = SecurityEventType.ACCESS_GRANTED if allowed else SecurityEventType.ACCESS_DENIED
        self._log_event(
            event_type,
            actor_id=actor_id,
            actor_type="cell" if token.cell_id else "service",
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=allowed,
            error=reason if not allowed else None,
        )

        # Track failed attempts for suspicious activity detection
        if not allowed:
            self._track_failed_attempt(actor_id)

        return allowed, reason

    # Secret Management (Facade to Vault)

    async def get_secret(
        self,
        token_id: str,
        secret_path: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get a secret from Vault using token authorization.

        Returns:
            Tuple of (secret_data, error_message)
        """
        # Check access
        allowed, reason = await self.check_access(
            token_id,
            ResourceType.SECRET,
            secret_path,
            "read",
        )

        if not allowed:
            return None, reason

        # Get token for cell_id
        token = self._tokens.get(token_id)
        cell_id = token.cell_id if token else None

        # Get secret from Vault
        secret = await self.vault.get_secret(secret_path, cell_id=cell_id)

        if secret:
            self._log_event(
                SecurityEventType.SECRET_ACCESSED,
                actor_id=cell_id,
                actor_type="cell" if cell_id else "service",
                resource_type=ResourceType.SECRET,
                resource_id=secret_path,
                action="read",
                success=True,
            )
            return secret, None

        return None, "Secret not found"

    async def put_secret(
        self,
        token_id: str,
        secret_path: str,
        data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Store a secret in Vault using token authorization.

        Returns:
            Tuple of (success, error_message)
        """
        # Check access
        allowed, reason = await self.check_access(
            token_id,
            ResourceType.SECRET,
            secret_path,
            "write",
        )

        if not allowed:
            return False, reason

        token = self._tokens.get(token_id)
        cell_id = token.cell_id if token else None

        success = await self.vault.put_secret(secret_path, data, cell_id=cell_id)

        return success, None if success else "Failed to store secret"

    # Mutation Approval

    async def request_mutation_approval(
        self,
        cell_id: str,
        mutation_severity: str,
        mutation_details: Dict[str, Any],
        timeout_seconds: int = 300,
    ) -> Tuple[bool, Optional[str]]:
        """
        Request approval for a critical mutation.

        Args:
            cell_id: Cell requesting mutation
            mutation_severity: Severity level (high, critical)
            mutation_details: Details about the mutation
            timeout_seconds: Timeout for approval

        Returns:
            Tuple of (approved, reason)
        """
        request_id = str(uuid.uuid4())

        self.logger.info(
            "Mutation approval requested",
            cell_id=cell_id,
            severity=mutation_severity,
            request_id=request_id,
        )

        # Emit event for human review
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="MUTATION_APPROVAL_REQUIRED",
                source=f"cell:{cell_id}",
                data={
                    "request_id": request_id,
                    "cell_id": cell_id,
                    "severity": mutation_severity,
                    "details": mutation_details,
                    "timeout_seconds": timeout_seconds,
                },
            ))

        self._log_event(
            SecurityEventType.MUTATION_APPROVED,  # Will be updated based on response
            actor_id=cell_id,
            actor_type="cell",
            resource_type=ResourceType.MUTATION,
            resource_id=request_id,
            action="request_approval",
            success=True,
            details=mutation_details,
        )

        # In production, this would wait for human approval
        # For now, auto-approve medium and below, require approval for high/critical
        if mutation_severity in ("high", "critical"):
            self.logger.warning(
                "Critical mutation requires human approval",
                cell_id=cell_id,
                request_id=request_id,
            )
            # Would wait for approval event here
            return False, "Awaiting human approval"

        return True, None

    # Audit and Monitoring

    def _log_event(
        self,
        event_type: SecurityEventType,
        actor_id: Optional[str],
        actor_type: str,
        resource_type: ResourceType,
        resource_id: str,
        action: str,
        success: bool,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> SecurityAuditEntry:
        """Log a security event."""
        entry = SecurityAuditEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=success,
            error=error,
            details=details or {},
            ip_address=ip_address,
        )

        self._audit_log.append(entry)

        # Trim log if too large
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries:]

        # Trigger alerts for critical events
        if event_type in (
            SecurityEventType.SUSPICIOUS_ACTIVITY,
            SecurityEventType.VULNERABILITY_DETECTED,
        ):
            self._trigger_alerts(entry)

        return entry

    def _track_failed_attempt(self, actor_id: str) -> None:
        """Track failed access attempts for suspicious activity detection."""
        self._failed_attempts[actor_id] = self._failed_attempts.get(actor_id, 0) + 1

        if self._failed_attempts[actor_id] >= self._suspicious_activity_threshold:
            entry = self._log_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                actor_id=actor_id,
                actor_type="unknown",
                resource_type=ResourceType.CELL,
                resource_id=actor_id,
                action="multiple_failed_attempts",
                success=False,
                details={"failed_attempts": self._failed_attempts[actor_id]},
            )
            self.logger.warning(
                "Suspicious activity detected",
                actor_id=actor_id,
                failed_attempts=self._failed_attempts[actor_id],
            )

    def _trigger_alerts(self, entry: SecurityAuditEntry) -> None:
        """Trigger registered alert handlers."""
        for handler in self._alert_handlers:
            try:
                handler(entry)
            except Exception as e:
                self.logger.error("Alert handler failed", error=str(e))

    def register_alert_handler(self, handler: Callable[[SecurityAuditEntry], None]) -> None:
        """Register a handler for security alerts."""
        self._alert_handlers.append(handler)

    def get_audit_log(
        self,
        actor_id: Optional[str] = None,
        event_type: Optional[SecurityEventType] = None,
        resource_type: Optional[ResourceType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SecurityAuditEntry]:
        """Get filtered audit log entries."""
        entries = self._audit_log

        if actor_id:
            entries = [e for e in entries if e.actor_id == actor_id]
        if event_type:
            entries = [e for e in entries if e.event_type == event_type]
        if resource_type:
            entries = [e for e in entries if e.resource_type == resource_type]
        if since:
            entries = [e for e in entries if e.timestamp >= since]

        return entries[-limit:]

    # Background Tasks

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired tokens and reset counters."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute

                # Clean expired tokens
                now = datetime.now(timezone.utc)
                expired = [
                    tid for tid, token in self._tokens.items()
                    if token.is_expired
                ]

                for tid in expired:
                    await self.revoke_token(tid, reason="Expired")

                if expired:
                    self.logger.debug("Cleaned expired tokens", count=len(expired))

                # Reset failed attempts counter periodically
                self._failed_attempts.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Cleanup loop error", error=str(e))

    # Utility Methods

    def get_token_for_cell(self, cell_id: str) -> Optional[SecurityToken]:
        """Get active token for a cell."""
        token_id = self._token_by_cell.get(cell_id)
        if token_id:
            return self._tokens.get(token_id)
        return None

    def get_active_tokens_count(self) -> int:
        """Get count of active tokens."""
        return len(self._tokens)

    def generate_cell_policy(self, cell_id: str, namespace: str = "default") -> str:
        """Generate Vault policy for a cell."""
        return CellSecretPolicy.generate_policy(cell_id, namespace)

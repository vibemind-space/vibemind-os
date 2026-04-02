"""
Vault Secret Manager - HashiCorp Vault integration for secret management.

Provides secure secret management:
- Time-limited token access
- Automatic secret rotation
- Comprehensive audit logging
- Kubernetes authentication support
- Dynamic secrets for databases
"""

import asyncio
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

import structlog

logger = structlog.get_logger()


class SecretEngine(str, Enum):
    """Vault secret engine types."""
    KV_V2 = "kv-v2"
    KV_V1 = "kv-v1"
    DATABASE = "database"
    AWS = "aws"
    PKI = "pki"
    TRANSIT = "transit"


class AuthMethod(str, Enum):
    """Vault authentication methods."""
    TOKEN = "token"
    KUBERNETES = "kubernetes"
    APPROLE = "approle"
    OIDC = "oidc"
    USERPASS = "userpass"


@dataclass
class VaultConfig:
    """Vault connection configuration."""
    address: str = "http://127.0.0.1:8200"
    token: Optional[str] = None
    namespace: Optional[str] = None
    tls_verify: bool = True
    ca_cert: Optional[str] = None
    client_cert: Optional[str] = None
    client_key: Optional[str] = None
    timeout: int = 30
    retry_count: int = 3
    auth_method: AuthMethod = AuthMethod.TOKEN

    # Kubernetes auth specific
    k8s_role: Optional[str] = None
    k8s_jwt_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"

    # AppRole auth specific
    approle_role_id: Optional[str] = None
    approle_secret_id: Optional[str] = None


@dataclass
class SecretLease:
    """Represents a Vault secret lease."""
    lease_id: str
    lease_duration: int  # seconds
    renewable: bool
    secret_path: str
    created_at: datetime
    expires_at: datetime
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if lease has expired."""
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def time_remaining(self) -> int:
        """Get seconds remaining until expiry."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))


@dataclass
class SecretAccessLog:
    """Audit log entry for secret access."""
    id: str
    timestamp: datetime
    cell_id: Optional[str]
    secret_path: str
    operation: str  # read, write, delete, list
    success: bool
    accessor_info: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class DynamicCredential:
    """Dynamic credential from Vault."""
    username: str
    password: str
    lease: SecretLease
    connection_string: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SecretCache:
    """Thread-safe secret cache with TTL."""

    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, tuple] = {}  # path -> (value, expires_at)
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, path: str) -> Optional[Dict[str, Any]]:
        """Get cached secret if not expired."""
        async with self._lock:
            if path in self._cache:
                value, expires_at = self._cache[path]
                if datetime.now(timezone.utc) < expires_at:
                    return value
                else:
                    del self._cache[path]
            return None

    async def set(self, path: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Cache secret with TTL."""
        async with self._lock:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl or self._default_ttl)
            self._cache[path] = (value, expires_at)

    async def invalidate(self, path: str) -> None:
        """Invalidate cached secret."""
        async with self._lock:
            self._cache.pop(path, None)

    async def clear(self) -> None:
        """Clear entire cache."""
        async with self._lock:
            self._cache.clear()


class VaultSecretManager:
    """
    HashiCorp Vault integration for secure secret management.

    Features:
    - Multiple authentication methods (Token, Kubernetes, AppRole)
    - KV v1/v2 secret engine support
    - Dynamic database credentials
    - Automatic lease renewal
    - Secret caching with TTL
    - Comprehensive audit logging
    - Time-limited token generation for cells
    """

    def __init__(self, config: Optional[VaultConfig] = None):
        self.config = config or VaultConfig()
        self.logger = logger.bind(component="VaultSecretManager")
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._leases: Dict[str, SecretLease] = {}
        self._cache = SecretCache()
        self._audit_logs: List[SecretAccessLog] = []
        self._rotation_callbacks: Dict[str, Callable] = {}
        self._renewal_task: Optional[asyncio.Task] = None

        # Load token from config or environment
        self._token = self.config.token or os.environ.get("VAULT_TOKEN")

    async def initialize(self) -> bool:
        """Initialize Vault connection and authenticate."""
        self.logger.info("Initializing Vault connection", address=self.config.address)

        try:
            # Authenticate based on method
            if self.config.auth_method == AuthMethod.TOKEN:
                if not self._token:
                    raise ValueError("No Vault token provided")
                # Validate token
                await self._validate_token()

            elif self.config.auth_method == AuthMethod.KUBERNETES:
                await self._authenticate_kubernetes()

            elif self.config.auth_method == AuthMethod.APPROLE:
                await self._authenticate_approle()

            # Start lease renewal task
            self._renewal_task = asyncio.create_task(self._renewal_loop())

            self.logger.info("Vault connection initialized")
            return True

        except Exception as e:
            self.logger.error("Failed to initialize Vault", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Shutdown Vault connection and cleanup."""
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass

        # Revoke all leases
        for lease in list(self._leases.values()):
            try:
                await self._revoke_lease(lease.lease_id)
            except Exception as e:
                self.logger.warning("Failed to revoke lease", lease_id=lease.lease_id, error=str(e))

        await self._cache.clear()
        self.logger.info("Vault connection shutdown")

    async def get_secret(
        self,
        path: str,
        cell_id: Optional[str] = None,
        version: Optional[int] = None,
        use_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve secret from Vault.

        Args:
            path: Secret path (e.g., "secret/data/myapp/config")
            cell_id: Optional cell ID for audit logging
            version: Optional version for KV v2
            use_cache: Whether to use cached value

        Returns:
            Secret data or None if not found
        """
        self.logger.debug("Getting secret", path=path, cell_id=cell_id)

        # Check cache first
        if use_cache:
            cached = await self._cache.get(path)
            if cached:
                self._log_access(cell_id, path, "read", True, cached=True)
                return cached

        try:
            # Build full path for KV v2
            full_path = path
            if not path.startswith("secret/data/"):
                full_path = f"secret/data/{path}"

            # Make Vault API request
            data = await self._vault_request("GET", full_path)

            if data and "data" in data:
                secret_data = data["data"].get("data", {})

                # Cache the result
                metadata = data["data"].get("metadata", {})
                ttl = metadata.get("custom_metadata", {}).get("ttl", 300)
                await self._cache.set(path, secret_data, ttl)

                self._log_access(cell_id, path, "read", True)
                return secret_data

            self._log_access(cell_id, path, "read", False, error="Secret not found")
            return None

        except Exception as e:
            self.logger.error("Failed to get secret", path=path, error=str(e))
            self._log_access(cell_id, path, "read", False, error=str(e))
            return None

    async def put_secret(
        self,
        path: str,
        data: Dict[str, Any],
        cell_id: Optional[str] = None,
        cas: Optional[int] = None,
    ) -> bool:
        """
        Store secret in Vault.

        Args:
            path: Secret path
            data: Secret data to store
            cell_id: Optional cell ID for audit logging
            cas: Check-and-set version for optimistic locking

        Returns:
            True if successful
        """
        self.logger.debug("Putting secret", path=path, cell_id=cell_id)

        try:
            full_path = path
            if not path.startswith("secret/data/"):
                full_path = f"secret/data/{path}"

            payload = {"data": data}
            if cas is not None:
                payload["options"] = {"cas": cas}

            await self._vault_request("POST", full_path, payload)

            # Invalidate cache
            await self._cache.invalidate(path)

            self._log_access(cell_id, path, "write", True)
            return True

        except Exception as e:
            self.logger.error("Failed to put secret", path=path, error=str(e))
            self._log_access(cell_id, path, "write", False, error=str(e))
            return False

    async def delete_secret(
        self,
        path: str,
        cell_id: Optional[str] = None,
        versions: Optional[List[int]] = None,
    ) -> bool:
        """
        Delete secret from Vault.

        Args:
            path: Secret path
            cell_id: Optional cell ID for audit logging
            versions: Specific versions to delete (KV v2)

        Returns:
            True if successful
        """
        self.logger.debug("Deleting secret", path=path, cell_id=cell_id)

        try:
            if versions:
                # Delete specific versions
                full_path = f"secret/delete/{path}"
                await self._vault_request("POST", full_path, {"versions": versions})
            else:
                # Delete latest version
                full_path = f"secret/data/{path}"
                await self._vault_request("DELETE", full_path)

            await self._cache.invalidate(path)

            self._log_access(cell_id, path, "delete", True)
            return True

        except Exception as e:
            self.logger.error("Failed to delete secret", path=path, error=str(e))
            self._log_access(cell_id, path, "delete", False, error=str(e))
            return False

    async def list_secrets(
        self,
        path: str,
        cell_id: Optional[str] = None,
    ) -> List[str]:
        """List secrets at path."""
        self.logger.debug("Listing secrets", path=path, cell_id=cell_id)

        try:
            full_path = f"secret/metadata/{path}"
            data = await self._vault_request("LIST", full_path)

            keys = data.get("data", {}).get("keys", [])
            self._log_access(cell_id, path, "list", True)
            return keys

        except Exception as e:
            self.logger.error("Failed to list secrets", path=path, error=str(e))
            self._log_access(cell_id, path, "list", False, error=str(e))
            return []

    async def rotate_secret(
        self,
        path: str,
        new_data: Dict[str, Any],
        cell_id: Optional[str] = None,
    ) -> bool:
        """
        Rotate a secret and trigger callbacks.

        Args:
            path: Secret path
            new_data: New secret data
            cell_id: Optional cell ID for audit logging

        Returns:
            True if successful
        """
        self.logger.info("Rotating secret", path=path, cell_id=cell_id)

        try:
            # Store new version
            success = await self.put_secret(path, new_data, cell_id)
            if not success:
                return False

            # Trigger rotation callbacks
            if path in self._rotation_callbacks:
                callback = self._rotation_callbacks[path]
                try:
                    await callback(path, new_data)
                except Exception as e:
                    self.logger.warning("Rotation callback failed", path=path, error=str(e))

            self.logger.info("Secret rotated successfully", path=path)
            return True

        except Exception as e:
            self.logger.error("Failed to rotate secret", path=path, error=str(e))
            return False

    def register_rotation_callback(
        self,
        path: str,
        callback: Callable[[str, Dict[str, Any]], Any],
    ) -> None:
        """Register callback to be called when secret is rotated."""
        self._rotation_callbacks[path] = callback
        self.logger.debug("Registered rotation callback", path=path)

    async def generate_cell_token(
        self,
        cell_id: str,
        policies: List[str],
        ttl: str = "1h",
        renewable: bool = True,
    ) -> Optional[str]:
        """
        Generate time-limited token for a cell.

        Args:
            cell_id: Cell identifier
            policies: Vault policies to attach
            ttl: Token TTL (e.g., "1h", "30m")
            renewable: Whether token can be renewed

        Returns:
            Token string or None if failed
        """
        self.logger.info("Generating cell token", cell_id=cell_id, policies=policies, ttl=ttl)

        try:
            payload = {
                "policies": policies,
                "ttl": ttl,
                "renewable": renewable,
                "meta": {
                    "cell_id": cell_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "display_name": f"cell-{cell_id[:8]}",
            }

            data = await self._vault_request("POST", "auth/token/create", payload)

            if data and "auth" in data:
                token = data["auth"]["client_token"]
                self.logger.info("Cell token generated", cell_id=cell_id)
                return token

            return None

        except Exception as e:
            self.logger.error("Failed to generate cell token", cell_id=cell_id, error=str(e))
            return None

    async def revoke_cell_token(self, token: str) -> bool:
        """Revoke a cell token."""
        try:
            await self._vault_request("POST", "auth/token/revoke", {"token": token})
            self.logger.info("Cell token revoked")
            return True
        except Exception as e:
            self.logger.error("Failed to revoke token", error=str(e))
            return False

    async def get_database_credentials(
        self,
        role: str,
        cell_id: Optional[str] = None,
    ) -> Optional[DynamicCredential]:
        """
        Get dynamic database credentials.

        Args:
            role: Database role name
            cell_id: Optional cell ID for audit logging

        Returns:
            DynamicCredential with username/password
        """
        self.logger.debug("Getting database credentials", role=role, cell_id=cell_id)

        try:
            path = f"database/creds/{role}"
            data = await self._vault_request("GET", path)

            if data and "data" in data:
                lease = SecretLease(
                    lease_id=data.get("lease_id", ""),
                    lease_duration=data.get("lease_duration", 3600),
                    renewable=data.get("renewable", False),
                    secret_path=path,
                    created_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=data.get("lease_duration", 3600)),
                    data=data["data"],
                )

                # Track lease
                self._leases[lease.lease_id] = lease

                cred = DynamicCredential(
                    username=data["data"]["username"],
                    password=data["data"]["password"],
                    lease=lease,
                )

                self._log_access(cell_id, path, "read", True)
                return cred

            return None

        except Exception as e:
            self.logger.error("Failed to get database credentials", role=role, error=str(e))
            self._log_access(cell_id, f"database/creds/{role}", "read", False, error=str(e))
            return None

    async def encrypt(self, key_name: str, plaintext: str) -> Optional[str]:
        """Encrypt data using Transit engine."""
        try:
            import base64
            encoded = base64.b64encode(plaintext.encode()).decode()
            data = await self._vault_request(
                "POST",
                f"transit/encrypt/{key_name}",
                {"plaintext": encoded}
            )
            return data.get("data", {}).get("ciphertext")
        except Exception as e:
            self.logger.error("Encryption failed", key_name=key_name, error=str(e))
            return None

    async def decrypt(self, key_name: str, ciphertext: str) -> Optional[str]:
        """Decrypt data using Transit engine."""
        try:
            import base64
            data = await self._vault_request(
                "POST",
                f"transit/decrypt/{key_name}",
                {"ciphertext": ciphertext}
            )
            encoded = data.get("data", {}).get("plaintext")
            if encoded:
                return base64.b64decode(encoded).decode()
            return None
        except Exception as e:
            self.logger.error("Decryption failed", key_name=key_name, error=str(e))
            return None

    def get_audit_logs(
        self,
        cell_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SecretAccessLog]:
        """Get audit logs with optional filtering."""
        logs = self._audit_logs

        if cell_id:
            logs = [l for l in logs if l.cell_id == cell_id]

        if since:
            logs = [l for l in logs if l.timestamp >= since]

        return logs[-limit:]

    async def audit_access(self, cell_id: str, secret_path: str) -> None:
        """Record an audit entry for secret access."""
        self._log_access(cell_id, secret_path, "audit", True)

    # Private methods

    async def _vault_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Vault API."""
        # In production, this would use aiohttp/httpx
        # For now, simulate with mock responses

        headers = {
            "X-Vault-Token": self._token,
        }
        if self.config.namespace:
            headers["X-Vault-Namespace"] = self.config.namespace

        url = f"{self.config.address}/v1/{path}"

        # Simulate API response
        self.logger.debug("Vault request", method=method, path=path)

        # Mock response for common operations
        if method == "GET" and "secret/data/" in path:
            # KV v2 read
            return {
                "data": {
                    "data": {"mock_key": "mock_value"},
                    "metadata": {
                        "created_time": datetime.now(timezone.utc).isoformat(),
                        "version": 1,
                    }
                },
                "lease_duration": 0,
                "renewable": False,
            }
        elif method == "POST" and "auth/token/create" in path:
            # Token creation
            return {
                "auth": {
                    "client_token": f"hvs.{uuid.uuid4().hex[:24]}",
                    "accessor": f"accessor.{uuid.uuid4().hex[:16]}",
                    "policies": data.get("policies", []),
                    "token_policies": data.get("policies", []),
                    "lease_duration": 3600,
                    "renewable": data.get("renewable", True),
                }
            }
        elif method == "GET" and "database/creds/" in path:
            # Dynamic database credentials
            return {
                "data": {
                    "username": f"v-cell-{uuid.uuid4().hex[:8]}",
                    "password": uuid.uuid4().hex,
                },
                "lease_id": f"database/creds/{path.split('/')[-1]}/{uuid.uuid4().hex}",
                "lease_duration": 3600,
                "renewable": True,
            }
        elif method == "LIST":
            return {
                "data": {
                    "keys": ["key1/", "key2/", "secret1"],
                }
            }

        return {}

    async def _validate_token(self) -> None:
        """Validate the current token."""
        data = await self._vault_request("GET", "auth/token/lookup-self")
        if not data:
            raise ValueError("Token validation failed")

        ttl = data.get("data", {}).get("ttl", 0)
        if ttl > 0:
            self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    async def _authenticate_kubernetes(self) -> None:
        """Authenticate using Kubernetes service account."""
        if not self.config.k8s_role:
            raise ValueError("Kubernetes role not configured")

        # Read JWT from service account
        try:
            with open(self.config.k8s_jwt_path, "r") as f:
                jwt = f.read().strip()
        except FileNotFoundError:
            raise ValueError(f"Kubernetes JWT not found at {self.config.k8s_jwt_path}")

        data = await self._vault_request(
            "POST",
            "auth/kubernetes/login",
            {"role": self.config.k8s_role, "jwt": jwt}
        )

        if data and "auth" in data:
            self._token = data["auth"]["client_token"]
            ttl = data["auth"].get("lease_duration", 3600)
            self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        else:
            raise ValueError("Kubernetes authentication failed")

    async def _authenticate_approle(self) -> None:
        """Authenticate using AppRole."""
        if not self.config.approle_role_id or not self.config.approle_secret_id:
            raise ValueError("AppRole credentials not configured")

        data = await self._vault_request(
            "POST",
            "auth/approle/login",
            {
                "role_id": self.config.approle_role_id,
                "secret_id": self.config.approle_secret_id,
            }
        )

        if data and "auth" in data:
            self._token = data["auth"]["client_token"]
            ttl = data["auth"].get("lease_duration", 3600)
            self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        else:
            raise ValueError("AppRole authentication failed")

    async def _renewal_loop(self) -> None:
        """Background task to renew leases and tokens."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Renew token if needed
                if self._token_expires:
                    remaining = (self._token_expires - datetime.now(timezone.utc)).total_seconds()
                    if remaining < 300:  # Less than 5 minutes
                        await self._renew_token()

                # Renew leases
                for lease_id, lease in list(self._leases.items()):
                    if lease.renewable and lease.time_remaining < 300:
                        try:
                            await self._renew_lease(lease_id)
                        except Exception as e:
                            self.logger.warning("Failed to renew lease", lease_id=lease_id, error=str(e))

                    # Remove expired leases
                    if lease.is_expired:
                        del self._leases[lease_id]

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Renewal loop error", error=str(e))

    async def _renew_token(self) -> None:
        """Renew the current token."""
        data = await self._vault_request("POST", "auth/token/renew-self")
        if data and "auth" in data:
            ttl = data["auth"].get("lease_duration", 3600)
            self._token_expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            self.logger.debug("Token renewed", new_ttl=ttl)

    async def _renew_lease(self, lease_id: str) -> None:
        """Renew a secret lease."""
        data = await self._vault_request(
            "POST",
            "sys/leases/renew",
            {"lease_id": lease_id}
        )
        if data and lease_id in self._leases:
            ttl = data.get("lease_duration", 3600)
            self._leases[lease_id].expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            self.logger.debug("Lease renewed", lease_id=lease_id, new_ttl=ttl)

    async def _revoke_lease(self, lease_id: str) -> None:
        """Revoke a secret lease."""
        await self._vault_request("POST", "sys/leases/revoke", {"lease_id": lease_id})
        self._leases.pop(lease_id, None)
        self.logger.debug("Lease revoked", lease_id=lease_id)

    def _log_access(
        self,
        cell_id: Optional[str],
        path: str,
        operation: str,
        success: bool,
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Log secret access for audit."""
        log_entry = SecretAccessLog(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            cell_id=cell_id,
            secret_path=path,
            operation=operation,
            success=success,
            accessor_info=kwargs,
            error=error,
        )
        self._audit_logs.append(log_entry)

        # Keep only last 10000 entries
        if len(self._audit_logs) > 10000:
            self._audit_logs = self._audit_logs[-10000:]

        self.logger.debug(
            "Secret access logged",
            cell_id=cell_id,
            path=path,
            operation=operation,
            success=success,
        )


class CellSecretPolicy:
    """
    Generates Vault policies for cells.

    Each cell gets a policy that limits access to:
    - Its own secrets path
    - Shared secrets for its namespace
    - Read-only access to common configs
    """

    @staticmethod
    def generate_policy(cell_id: str, namespace: str = "default") -> str:
        """Generate HCL policy for a cell."""
        return f'''
# Policy for cell: {cell_id}
# Namespace: {namespace}

# Full access to cell-specific secrets
path "secret/data/cells/{cell_id}/*" {{
    capabilities = ["create", "read", "update", "delete", "list"]
}}

# Read access to namespace-shared secrets
path "secret/data/shared/{namespace}/*" {{
    capabilities = ["read", "list"]
}}

# Read-only access to global configs
path "secret/data/global/config" {{
    capabilities = ["read"]
}}

# Access to database credentials for cell role
path "database/creds/cell-{cell_id[:8]}" {{
    capabilities = ["read"]
}}

# Transit encryption for cell data
path "transit/encrypt/cell-{cell_id[:8]}" {{
    capabilities = ["update"]
}}

path "transit/decrypt/cell-{cell_id[:8]}" {{
    capabilities = ["update"]
}}
'''

    @staticmethod
    def generate_namespace_policy(namespace: str) -> str:
        """Generate HCL policy for namespace admin."""
        return f'''
# Namespace admin policy: {namespace}

# Full access to namespace secrets
path "secret/data/{namespace}/*" {{
    capabilities = ["create", "read", "update", "delete", "list"]
}}

# Read all cells in namespace
path "secret/data/cells/*" {{
    capabilities = ["read", "list"]
}}

# Create tokens for cells
path "auth/token/create" {{
    capabilities = ["create", "update"]
    allowed_parameters = {{
        "policies" = ["cell-*-policy"]
        "ttl" = ["1h", "2h", "4h", "8h", "24h"]
    }}
}}
'''

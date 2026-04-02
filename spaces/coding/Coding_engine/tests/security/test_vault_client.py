"""
Tests for Vault Secret Manager.

Tests:
- Secret retrieval
- Secret creation/update
- Configuration
- Secret caching
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security.vault_client import (
    VaultSecretManager,
    VaultConfig,
    AuthMethod,
    SecretCache,
    SecretLease,
)


@pytest.fixture
def vault_config():
    """Create a test VaultConfig."""
    return VaultConfig(
        address="https://vault.example.com",
        token="test-token",
        namespace="test",
        auth_method=AuthMethod.TOKEN,
    )


@pytest.fixture
def vault_manager(vault_config: VaultConfig):
    """Create VaultSecretManager with test config."""
    return VaultSecretManager(config=vault_config)


class TestVaultSecretManagerInitialization:
    """Tests for VaultSecretManager initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        manager = VaultSecretManager()

        assert manager.config.address == "http://127.0.0.1:8200"
        assert manager.config.auth_method == AuthMethod.TOKEN

    def test_custom_config(self, vault_config: VaultConfig):
        """Test custom config initialization."""
        manager = VaultSecretManager(config=vault_config)

        assert manager.config.address == "https://vault.example.com"
        assert manager.config.token == "test-token"
        assert manager.config.namespace == "test"

    def test_token_from_config(self, vault_config: VaultConfig):
        """Test token is loaded from config."""
        manager = VaultSecretManager(config=vault_config)

        assert manager._token == "test-token"

    def test_kubernetes_auth_method(self):
        """Test Kubernetes auth method configuration."""
        config = VaultConfig(
            auth_method=AuthMethod.KUBERNETES,
            k8s_role="cell-colony",
        )
        manager = VaultSecretManager(config=config)

        assert manager.config.auth_method == AuthMethod.KUBERNETES
        assert manager.config.k8s_role == "cell-colony"


class TestVaultConfig:
    """Tests for VaultConfig dataclass."""

    def test_default_values(self):
        """Test VaultConfig default values."""
        config = VaultConfig()

        assert config.address == "http://127.0.0.1:8200"
        assert config.tls_verify is True
        assert config.timeout == 30
        assert config.retry_count == 3

    def test_custom_values(self):
        """Test VaultConfig with custom values."""
        config = VaultConfig(
            address="https://vault.production.com",
            token="prod-token",
            namespace="production",
            tls_verify=True,
            timeout=60,
        )

        assert config.address == "https://vault.production.com"
        assert config.namespace == "production"
        assert config.timeout == 60

    def test_approle_config(self):
        """Test AppRole auth configuration."""
        config = VaultConfig(
            auth_method=AuthMethod.APPROLE,
            approle_role_id="role-123",
            approle_secret_id="secret-456",
        )

        assert config.auth_method == AuthMethod.APPROLE
        assert config.approle_role_id == "role-123"
        assert config.approle_secret_id == "secret-456"


class TestSecretCache:
    """Tests for SecretCache."""

    @pytest.fixture
    def cache(self):
        """Create a SecretCache."""
        return SecretCache()

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: SecretCache):
        """Test setting and getting cached secrets."""
        await cache.set("test/path", {"key": "value"}, ttl=300)
        result = await cache.get("test/path")

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_missing(self, cache: SecretCache):
        """Test getting missing secret returns None."""
        result = await cache.get("nonexistent/path")

        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self, cache: SecretCache):
        """Test clearing cache."""
        await cache.set("test/path", {"key": "value"}, ttl=300)
        await cache.clear()
        result = await cache.get("test/path")

        assert result is None


class TestSecretLease:
    """Tests for SecretLease dataclass."""

    def test_is_expired(self):
        """Test lease expiration check."""
        # Expired lease
        lease = SecretLease(
            lease_id="lease-123",
            lease_duration=3600,
            renewable=True,
            secret_path="test/path",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # Past date
        )

        assert lease.is_expired is True

    def test_is_not_expired(self):
        """Test lease not expired."""
        lease = SecretLease(
            lease_id="lease-123",
            lease_duration=3600,
            renewable=True,
            secret_path="test/path",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime(2099, 12, 31, tzinfo=timezone.utc),  # Future date
        )

        assert lease.is_expired is False

    def test_time_remaining(self):
        """Test time remaining calculation."""
        future = datetime(2099, 12, 31, tzinfo=timezone.utc)
        lease = SecretLease(
            lease_id="lease-123",
            lease_duration=3600,
            renewable=True,
            secret_path="test/path",
            created_at=datetime.now(timezone.utc),
            expires_at=future,
        )

        assert lease.time_remaining > 0


class TestVaultSecretManagerMethods:
    """Tests for VaultSecretManager methods."""

    @pytest.mark.asyncio
    async def test_get_secret_uses_cache(self, vault_manager: VaultSecretManager):
        """Test get_secret uses cache."""
        # Prime the cache
        await vault_manager._cache.set("test/secret", {"api_key": "cached-value"}, ttl=300)

        # Should return cached value without making API call
        result = await vault_manager.get_secret("test/secret", use_cache=True)

        assert result == {"api_key": "cached-value"}

    @pytest.mark.asyncio
    async def test_get_secret_bypasses_cache(self, vault_manager: VaultSecretManager):
        """Test get_secret can bypass cache."""
        await vault_manager._cache.set("test/secret", {"api_key": "cached-value"}, ttl=300)

        # Mock the API request to return None (since we're not making real requests)
        vault_manager._vault_request = AsyncMock(return_value=None)

        result = await vault_manager.get_secret("test/secret", use_cache=False)

        # Should have called API instead of using cache
        vault_manager._vault_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_secret_logs_access(self, vault_manager: VaultSecretManager):
        """Test get_secret logs access."""
        await vault_manager._cache.set("test/secret", {"key": "value"}, ttl=300)

        await vault_manager.get_secret("test/secret", cell_id="cell-123")

        # Should have logged access
        assert len(vault_manager._audit_logs) >= 1
        log = vault_manager._audit_logs[-1]
        assert log.cell_id == "cell-123"
        assert log.secret_path == "test/secret"


class TestAuthMethods:
    """Tests for authentication method enum."""

    def test_auth_method_values(self):
        """Test AuthMethod enum values."""
        assert AuthMethod.TOKEN.value == "token"
        assert AuthMethod.KUBERNETES.value == "kubernetes"
        assert AuthMethod.APPROLE.value == "approle"
        assert AuthMethod.OIDC.value == "oidc"
        assert AuthMethod.USERPASS.value == "userpass"


class TestVaultSecretManagerAudit:
    """Tests for audit logging."""

    @pytest.mark.asyncio
    async def test_audit_logs_recorded(self, vault_manager: VaultSecretManager):
        """Test that audit logs are recorded."""
        await vault_manager._cache.set("test/secret", {"key": "value"}, ttl=300)

        await vault_manager.get_secret("test/secret", cell_id="cell-abc")

        assert len(vault_manager._audit_logs) >= 1

    @pytest.mark.asyncio
    async def test_audit_log_structure(self, vault_manager: VaultSecretManager):
        """Test audit log structure."""
        await vault_manager._cache.set("test/secret", {"key": "value"}, ttl=300)

        await vault_manager.get_secret("test/secret", cell_id="cell-xyz")

        log = vault_manager._audit_logs[-1]
        assert hasattr(log, "timestamp")
        assert hasattr(log, "cell_id")
        assert hasattr(log, "secret_path")
        assert hasattr(log, "operation")  # Uses 'operation' not 'action'

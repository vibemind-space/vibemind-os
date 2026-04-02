"""
Tests for Runtime Security Manager.

Tests:
- mTLS configuration
- NetworkPolicy generation
- RBAC setup
- Security context application
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from src.security.runtime_security import (
    RuntimeSecurityManager,
    MTLSConfig,
    NetworkPolicyConfig,
    NetworkPolicyType,
    RBACConfig,
    PodSecurityConfig,
    SecurityLevel,
)


@pytest.fixture
def security_manager():
    """Create RuntimeSecurityManager."""
    return RuntimeSecurityManager(namespace="test-namespace")


@pytest.fixture
def sample_cell_id():
    """Sample cell ID."""
    return "abc12345-1234-5678-abcd-123456789012"


@pytest.fixture
def sample_cell_name():
    """Sample cell name."""
    return "test-service"


class TestRuntimeSecurityManagerInitialization:
    """Tests for RuntimeSecurityManager initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        manager = RuntimeSecurityManager()
        assert manager.namespace == "default"

    def test_custom_namespace(self):
        """Test custom namespace initialization."""
        manager = RuntimeSecurityManager(namespace="cell-colony")
        assert manager.namespace == "cell-colony"


class TestMTLSConfiguration:
    """Tests for mTLS configuration."""

    def test_configure_mtls_returns_manifests(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
    ):
        """Test mTLS configuration returns manifests."""
        result = security_manager.configure_mtls(sample_cell_id)

        assert "peer_authentication" in result
        assert "destination_rule" in result

    def test_configure_mtls_peer_auth_structure(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
    ):
        """Test PeerAuthentication structure."""
        result = security_manager.configure_mtls(sample_cell_id)
        peer_auth = result["peer_authentication"]

        assert peer_auth["kind"] == "PeerAuthentication"
        assert peer_auth["apiVersion"] == "security.istio.io/v1beta1"
        assert peer_auth["spec"]["mtls"]["mode"] == "STRICT"

    def test_configure_mtls_destination_rule_structure(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
    ):
        """Test DestinationRule structure."""
        result = security_manager.configure_mtls(sample_cell_id)
        dest_rule = result["destination_rule"]

        assert dest_rule["kind"] == "DestinationRule"
        assert dest_rule["apiVersion"] == "networking.istio.io/v1beta1"
        assert dest_rule["spec"]["trafficPolicy"]["tls"]["mode"] == "ISTIO_MUTUAL"

    def test_configure_mtls_includes_cell_id_label(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
    ):
        """Test that cell ID is included in labels."""
        result = security_manager.configure_mtls(sample_cell_id)
        peer_auth = result["peer_authentication"]

        assert peer_auth["metadata"]["labels"]["colony.codingengine.io/cell-id"] == sample_cell_id


class TestNetworkPolicyGeneration:
    """Tests for NetworkPolicy generation."""

    def test_apply_network_policies_returns_list(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test apply_network_policies returns list of policies."""
        result = security_manager.apply_network_policies(sample_cell_id, sample_cell_name)

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_generate_default_deny_policy(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test generating default-deny NetworkPolicy."""
        result = security_manager.apply_network_policies(sample_cell_id, sample_cell_name)

        # Find default deny policy
        default_deny = next(
            (p for p in result if "default-deny" in p["metadata"]["name"]),
            None
        )

        assert default_deny is not None
        assert default_deny["kind"] == "NetworkPolicy"
        assert "Ingress" in default_deny["spec"]["policyTypes"]
        assert "Egress" in default_deny["spec"]["policyTypes"]

    def test_generate_allow_dns_policy(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test generating DNS allow NetworkPolicy."""
        config = NetworkPolicyConfig(allow_dns=True)
        result = security_manager.apply_network_policies(
            sample_cell_id, sample_cell_name, config
        )

        # Find DNS policy
        dns_policy = next(
            (p for p in result if "allow-dns" in p["metadata"]["name"]),
            None
        )

        assert dns_policy is not None
        # Check DNS ports (53) are allowed
        egress_ports = dns_policy["spec"]["egress"][0]["ports"]
        assert any(p["port"] == 53 for p in egress_ports)

    def test_allow_same_namespace_ingress(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test allowing ingress from same namespace."""
        config = NetworkPolicyConfig(policy_type=NetworkPolicyType.ALLOW_SAME_NAMESPACE)
        result = security_manager.apply_network_policies(
            sample_cell_id, sample_cell_name, config
        )

        # Find same namespace policy
        same_ns = next(
            (p for p in result if "allow-same-ns" in p["metadata"]["name"]),
            None
        )

        assert same_ns is not None
        assert "Ingress" in same_ns["spec"]["policyTypes"]


class TestRBACGeneration:
    """Tests for RBAC generation."""

    def test_setup_rbac_returns_manifests(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test setup_rbac returns RBAC manifests."""
        result = security_manager.setup_rbac(sample_cell_id, sample_cell_name)

        assert "service_account" in result
        assert "role" in result
        assert "role_binding" in result

    def test_generate_service_account(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test ServiceAccount generation."""
        result = security_manager.setup_rbac(sample_cell_id, sample_cell_name)
        sa = result["service_account"]

        assert sa["kind"] == "ServiceAccount"
        assert sa["apiVersion"] == "v1"
        assert sample_cell_name in sa["metadata"]["name"]

    def test_generate_role(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test Role generation."""
        result = security_manager.setup_rbac(sample_cell_id, sample_cell_name)
        role = result["role"]

        assert role["kind"] == "Role"
        assert role["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert "rules" in role

    def test_generate_role_binding(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test RoleBinding generation."""
        result = security_manager.setup_rbac(sample_cell_id, sample_cell_name)
        rb = result["role_binding"]

        assert rb["kind"] == "RoleBinding"
        assert rb["apiVersion"] == "rbac.authorization.k8s.io/v1"

    def test_service_account_no_automount_by_default(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test ServiceAccount doesn't automount token by default."""
        result = security_manager.setup_rbac(sample_cell_id, sample_cell_name)
        sa = result["service_account"]

        assert sa["automountServiceAccountToken"] is False


class TestPodSecurityConfig:
    """Tests for PodSecurityConfig dataclass."""

    def test_default_values(self):
        """Test PodSecurityConfig default values."""
        config = PodSecurityConfig()

        assert config.run_as_non_root is True
        assert config.read_only_root_filesystem is True
        assert config.allow_privilege_escalation is False

    def test_restricted_security_level(self):
        """Test restricted security level config."""
        config = PodSecurityConfig(security_level=SecurityLevel.RESTRICTED)

        assert config.security_level == SecurityLevel.RESTRICTED
        assert config.run_as_non_root is True

    def test_seccomp_profile(self):
        """Test seccomp profile config."""
        config = PodSecurityConfig(seccomp_profile="RuntimeDefault")

        assert config.seccomp_profile == "RuntimeDefault"

    def test_drop_all_capabilities(self):
        """Test drop all capabilities config."""
        config = PodSecurityConfig()

        assert "ALL" in config.drop_capabilities


class TestCellIsolation:
    """Tests for cell isolation."""

    def test_isolate_cell_network(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test cell network isolation."""
        policies = security_manager.apply_network_policies(
            sample_cell_id,
            sample_cell_name,
            NetworkPolicyConfig(policy_type=NetworkPolicyType.DEFAULT_DENY)
        )

        # Should have default deny policy
        assert any("default-deny" in p["metadata"]["name"] for p in policies)

    def test_allow_cell_ingress_from_specific_sources(
        self,
        security_manager: RuntimeSecurityManager,
        sample_cell_id: str,
        sample_cell_name: str,
    ):
        """Test allowing ingress from specific sources."""
        config = NetworkPolicyConfig(
            policy_type=NetworkPolicyType.ALLOW_INGRESS,
            allowed_ingress_namespaces=["api-gateway"],
        )
        policies = security_manager.apply_network_policies(
            sample_cell_id, sample_cell_name, config
        )

        # Should have policies
        assert len(policies) >= 1

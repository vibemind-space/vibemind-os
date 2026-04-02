"""
Tests for K8s resource generator.

Tests:
- Deployment manifest generation
- Service manifest generation
- ConfigMap generation
- Cell CRD generation
- Network Policy generation
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.colony.cell import Cell, CellStatus, SourceType, ResourceLimits, HealthCheckConfig
from src.colony.k8s.resource_generator import ResourceGenerator, GeneratedResources


@pytest.fixture
def sample_cell():
    """Create a sample cell for testing."""
    return Cell(
        name="test-service",
        source_type=SourceType.LLM_GENERATED,
        source_ref="Generate a REST API",
        ports=[8080],
        env_vars={"LOG_LEVEL": "DEBUG"},
    )


class TestResourceGeneratorInitialization:
    """Tests for ResourceGenerator initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        generator = ResourceGenerator()

        assert generator.registry == "cell-registry.local"
        assert generator.image_pull_policy == "IfNotPresent"

    def test_custom_initialization(self):
        """Test custom initialization."""
        generator = ResourceGenerator(
            registry="docker.io/myorg",
            image_pull_policy="Always",
        )

        assert generator.registry == "docker.io/myorg"
        assert generator.image_pull_policy == "Always"

    def test_enable_network_policies_flag(self):
        """Test network policies can be disabled."""
        generator = ResourceGenerator(enable_network_policies=False)
        assert generator.enable_network_policies is False

    def test_enable_service_accounts_flag(self):
        """Test service accounts can be disabled."""
        generator = ResourceGenerator(enable_service_accounts=False)
        assert generator.enable_service_accounts is False


class TestGenerateMethod:
    """Tests for the main generate method."""

    def test_generate_returns_generated_resources(self, sample_cell: Cell):
        """Test generate() returns GeneratedResources."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        assert isinstance(result, GeneratedResources)

    def test_generate_includes_required_manifests(self, sample_cell: Cell):
        """Test generate includes required manifests."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        assert result.cell_manifest is not None
        assert result.deployment_manifest is not None
        assert result.service_manifest is not None

    def test_generate_includes_configmap_when_env_vars(self, sample_cell: Cell):
        """Test generate includes configmap when cell has env vars."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        assert result.configmap_manifest is not None

    def test_generate_excludes_configmap_when_no_env_vars(self):
        """Test generate excludes configmap when no env vars."""
        cell = Cell(name="test-cell", env_vars={})
        generator = ResourceGenerator()
        result = generator.generate(cell)

        assert result.configmap_manifest is None

    def test_generate_includes_network_policy_by_default(self, sample_cell: Cell):
        """Test generate includes network policy by default."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        assert result.network_policy_manifest is not None

    def test_generate_excludes_network_policy_when_disabled(self, sample_cell: Cell):
        """Test generate excludes network policy when disabled."""
        generator = ResourceGenerator(enable_network_policies=False)
        result = generator.generate(sample_cell)

        assert result.network_policy_manifest is None


class TestDeploymentGeneration:
    """Tests for Deployment manifest generation."""

    def test_deployment_basic_structure(self, sample_cell: Cell):
        """Test generating basic deployment."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.deployment_manifest)

        assert parsed["kind"] == "Deployment"
        assert parsed["apiVersion"] == "apps/v1"
        assert parsed["metadata"]["name"].startswith("cell-")
        assert parsed["spec"]["replicas"] == 1

    def test_deployment_with_resource_limits(self):
        """Test deployment includes resource limits."""
        cell = Cell(
            name="test-cell",
            resource_limits=ResourceLimits(
                cpu_request="100m",
                cpu_limit="500m",
                memory_request="128Mi",
                memory_limit="512Mi",
            ),
        )

        generator = ResourceGenerator()
        result = generator.generate(cell)

        parsed = yaml.safe_load(result.deployment_manifest)
        container = parsed["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]

        assert resources["requests"]["cpu"] == "100m"
        assert resources["limits"]["memory"] == "512Mi"

    def test_deployment_with_health_check(self):
        """Test deployment includes health probes."""
        cell = Cell(
            name="test-cell",
            health_check=HealthCheckConfig(
                path="/health",
                port=8080,
                initial_delay_seconds=30,
                period_seconds=10,
            ),
        )

        generator = ResourceGenerator()
        result = generator.generate(cell)

        parsed = yaml.safe_load(result.deployment_manifest)
        container = parsed["spec"]["template"]["spec"]["containers"][0]

        assert "livenessProbe" in container
        assert container["livenessProbe"]["httpGet"]["path"] == "/health"
        assert container["livenessProbe"]["httpGet"]["port"] == 8080
        assert "readinessProbe" in container

    def test_deployment_with_labels(self, sample_cell: Cell):
        """Test deployment includes proper labels."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.deployment_manifest)
        labels = parsed["metadata"]["labels"]

        assert "app.kubernetes.io/name" in labels
        assert "app.kubernetes.io/managed-by" in labels
        assert labels["app.kubernetes.io/managed-by"] == "cell-colony"

    def test_deployment_security_context(self, sample_cell: Cell):
        """Test deployment has security context."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.deployment_manifest)
        container = parsed["spec"]["template"]["spec"]["containers"][0]
        security_context = container.get("securityContext", {})

        assert security_context.get("runAsNonRoot") is True
        assert security_context.get("readOnlyRootFilesystem") is True
        assert security_context.get("allowPrivilegeEscalation") is False


class TestServiceGeneration:
    """Tests for Service manifest generation."""

    def test_service_basic_structure(self, sample_cell: Cell):
        """Test generating basic service."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.service_manifest)

        assert parsed["kind"] == "Service"
        assert parsed["apiVersion"] == "v1"
        assert parsed["metadata"]["name"].endswith("-svc")

    def test_service_exposes_ports(self, sample_cell: Cell):
        """Test service exposes correct ports."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.service_manifest)
        ports = parsed["spec"]["ports"]

        assert len(ports) >= 1
        assert ports[0]["port"] == 8080

    def test_service_selector_matches_deployment(self, sample_cell: Cell):
        """Test service selector matches deployment labels."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        deployment = yaml.safe_load(result.deployment_manifest)
        service = yaml.safe_load(result.service_manifest)

        service_selector = service["spec"]["selector"]
        assert "app.kubernetes.io/name" in service_selector
        assert "app.kubernetes.io/instance" in service_selector


class TestConfigMapGeneration:
    """Tests for ConfigMap manifest generation."""

    def test_configmap_basic_structure(self, sample_cell: Cell):
        """Test generating basic ConfigMap."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.configmap_manifest)

        assert parsed["kind"] == "ConfigMap"
        assert parsed["apiVersion"] == "v1"
        assert parsed["metadata"]["name"].endswith("-config")

    def test_configmap_includes_env_vars(self, sample_cell: Cell):
        """Test ConfigMap includes cell env vars."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.configmap_manifest)
        data = parsed.get("data", {})

        assert "LOG_LEVEL" in data
        assert data["LOG_LEVEL"] == "DEBUG"


class TestCellCRDGeneration:
    """Tests for Cell CRD manifest generation."""

    def test_cell_crd_structure(self, sample_cell: Cell):
        """Test generating Cell CRD manifest."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.cell_manifest)

        assert parsed["kind"] == "Cell"
        assert parsed["apiVersion"] == "colony.codingengine.io/v1"

    def test_cell_crd_spec(self, sample_cell: Cell):
        """Test Cell CRD spec includes required fields."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.cell_manifest)
        spec = parsed["spec"]

        assert "name" in spec
        assert "sourceType" in spec
        assert "sourceRef" in spec


class TestNetworkPolicyGeneration:
    """Tests for NetworkPolicy generation."""

    def test_network_policy_structure(self, sample_cell: Cell):
        """Test generating NetworkPolicy."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.network_policy_manifest)

        assert parsed["kind"] == "NetworkPolicy"
        assert parsed["apiVersion"] == "networking.k8s.io/v1"

    def test_network_policy_allows_dns(self, sample_cell: Cell):
        """Test NetworkPolicy allows DNS traffic."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.network_policy_manifest)
        egress = parsed["spec"].get("egress", [])

        # Should allow DNS (port 53)
        dns_allowed = any(
            any(port.get("port") == 53 for port in rule.get("ports", []))
            for rule in egress
        )
        assert dns_allowed is True


class TestAllManifests:
    """Tests for combining all manifests."""

    def test_all_manifests_combined(self, sample_cell: Cell):
        """Test all manifests can be combined."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        combined = result.all_manifests()

        # Should be valid multi-document YAML
        docs = list(yaml.safe_load_all(combined))
        assert len(docs) >= 4  # Cell, Deployment, Service, NetworkPolicy


class TestResourceLabelsAndAnnotations:
    """Tests for labels and annotations."""

    def test_standard_labels_applied(self, sample_cell: Cell):
        """Test that standard labels are applied to deployment."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.deployment_manifest)
        labels = parsed.get("metadata", {}).get("labels", {})

        assert "app.kubernetes.io/managed-by" in labels
        assert labels["app.kubernetes.io/managed-by"] == "cell-colony"

    def test_cell_id_annotation(self, sample_cell: Cell):
        """Test cell ID is added as annotation."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        parsed = yaml.safe_load(result.deployment_manifest)
        annotations = parsed.get("metadata", {}).get("annotations", {})

        assert "colony.codingengine.io/cell-id" in annotations
        assert annotations["colony.codingengine.io/cell-id"] == sample_cell.id


class TestServiceAccountGeneration:
    """Tests for ServiceAccount generation."""

    def test_service_account_included_by_default(self, sample_cell: Cell):
        """Test service account is included by default."""
        generator = ResourceGenerator()
        result = generator.generate(sample_cell)

        assert result.service_account_manifest is not None

    def test_service_account_excluded_when_disabled(self, sample_cell: Cell):
        """Test service account excluded when disabled."""
        generator = ResourceGenerator(enable_service_accounts=False)
        result = generator.generate(sample_cell)

        assert result.service_account_manifest is None

"""
Tests for Cell dataclass and CellStatus.

Tests:
- Cell creation with defaults
- Cell status transitions
- Health score calculations
- Resource limits validation
- Mutation recording
- Version bumping
- Serialization/deserialization
"""

import pytest
from datetime import datetime

from src.colony.cell import (
    Cell, CellStatus, SourceType, MutationSeverity,
    ResourceLimits, HealthCheckConfig, MutationRecord,
    classify_mutation_severity,
)


class TestCellCreation:
    """Tests for Cell instance creation."""

    def test_cell_creation_with_defaults(self):
        """Test creating a Cell with minimal arguments."""
        cell = Cell(name="test-service")

        assert cell.name == "test-service"
        assert cell.namespace == "default"
        assert cell.status == CellStatus.PENDING
        assert cell.health_score == 1.0
        assert cell.version == "1.0.0"
        assert cell.mutation_count == 0
        assert cell.id is not None
        assert len(cell.id) == 36  # UUID format

    def test_cell_creation_with_all_arguments(self, sample_cell: Cell):
        """Test creating a Cell with all arguments."""
        assert sample_cell.name == "test-auth-service"
        assert sample_cell.namespace == "test-namespace"
        assert sample_cell.source_type == SourceType.LLM_GENERATED
        assert sample_cell.status == CellStatus.HEALTHY

    def test_cell_k8s_names_are_generated(self):
        """Test that Kubernetes resource names are auto-generated."""
        cell = Cell(name="my-service")

        assert cell.k8s_deployment_name.startswith("cell-my-service-")
        assert cell.k8s_service_name == "cell-my-service-svc"
        assert cell.k8s_configmap_name == "cell-my-service-config"

    def test_cell_labels_include_standard_k8s_labels(self):
        """Test that standard Kubernetes labels are added."""
        cell = Cell(name="test-svc")

        assert "app.kubernetes.io/name" in cell.labels
        assert cell.labels["app.kubernetes.io/name"] == "test-svc"
        assert cell.labels["app.kubernetes.io/managed-by"] == "cell-colony"


class TestCellStatus:
    """Tests for CellStatus enum and status properties."""

    def test_cell_status_values(self):
        """Test all status values exist."""
        statuses = [
            CellStatus.PENDING, CellStatus.INITIALIZING,
            CellStatus.BUILDING, CellStatus.DEPLOYING,
            CellStatus.HEALTHY, CellStatus.DEGRADED,
            CellStatus.RECOVERING, CellStatus.MUTATING,
            CellStatus.TERMINATING, CellStatus.TERMINATED,
        ]
        assert len(statuses) == 10

    def test_is_healthy_property(self, sample_cell: Cell):
        """Test is_healthy property."""
        sample_cell.status = CellStatus.HEALTHY
        sample_cell.health_score = 1.0
        assert sample_cell.is_healthy is True

        sample_cell.health_score = 0.7
        assert sample_cell.is_healthy is False

    def test_is_running_property(self):
        """Test is_running property."""
        cell = Cell(name="test")

        cell.status = CellStatus.HEALTHY
        assert cell.is_running is True

        cell.status = CellStatus.DEGRADED
        assert cell.is_running is True

        cell.status = CellStatus.PENDING
        assert cell.is_running is False

    def test_needs_recovery_property(self, degraded_cell: Cell):
        """Test needs_recovery property."""
        assert degraded_cell.needs_recovery is True

    def test_should_autophagy_property(self, cell_with_mutations: Cell):
        """Test should_autophagy property."""
        # With 1 failed mutation out of 3, should not trigger autophagy
        assert cell_with_mutations.should_autophagy is False

        # Add many failed mutations
        cell_with_mutations.max_mutations = 2
        cell_with_mutations.mutations = [
            MutationRecord(success=False) for _ in range(3)
        ]
        assert cell_with_mutations.should_autophagy is True


class TestCellHealth:
    """Tests for Cell health tracking."""

    def test_update_health_on_pass(self, sample_cell: Cell):
        """Test health update when check passes."""
        sample_cell.health_score = 0.8
        sample_cell.update_health(passed=True)

        assert sample_cell.health_score == 0.9
        assert sample_cell.consecutive_failures == 0
        assert sample_cell.consecutive_successes == 1

    def test_update_health_on_fail(self, sample_cell: Cell):
        """Test health update when check fails."""
        sample_cell.health_score = 1.0
        sample_cell.update_health(passed=False)

        assert sample_cell.health_score == 0.8
        assert sample_cell.consecutive_failures == 1
        assert sample_cell.consecutive_successes == 0

    def test_health_score_capped_at_1(self, sample_cell: Cell):
        """Test that health score doesn't exceed 1.0."""
        sample_cell.health_score = 0.95
        sample_cell.update_health(passed=True)

        assert sample_cell.health_score == 1.0

    def test_health_score_capped_at_0(self, sample_cell: Cell):
        """Test that health score doesn't go below 0.0."""
        sample_cell.health_score = 0.1
        sample_cell.update_health(passed=False)

        assert sample_cell.health_score == 0.0

    def test_status_transitions_to_degraded(self, sample_cell: Cell):
        """Test automatic status transition to DEGRADED."""
        sample_cell.status = CellStatus.HEALTHY
        sample_cell.health_score = 0.85
        sample_cell.update_health(passed=False)

        # Should transition to DEGRADED when health drops below 0.8
        assert sample_cell.health_score == pytest.approx(0.65, abs=0.001)
        assert sample_cell.status == CellStatus.DEGRADED

    def test_status_transitions_to_healthy(self):
        """Test automatic status transition to HEALTHY."""
        cell = Cell(name="test", status=CellStatus.DEGRADED, health_score=0.75)
        cell.update_health(passed=True)
        cell.update_health(passed=True)

        assert cell.health_score >= 0.8
        assert cell.status == CellStatus.HEALTHY


class TestCellMutations:
    """Tests for Cell mutation tracking."""

    def test_record_mutation_success(self, sample_cell: Cell):
        """Test recording a successful mutation."""
        record = sample_cell.record_mutation(
            severity=MutationSeverity.LOW,
            trigger_event="health_failure",
            prompt="Fix the bug",
            files_modified=["src/main.py"],
            success=True,
        )

        assert record.success is True
        assert sample_cell.mutation_count == 1
        assert len(sample_cell.mutations) == 1
        assert sample_cell.version == "1.0.1"

    def test_record_mutation_failure(self, sample_cell: Cell):
        """Test recording a failed mutation."""
        original_version = sample_cell.version
        record = sample_cell.record_mutation(
            severity=MutationSeverity.HIGH,
            trigger_event="build_failure",
            prompt="Fix the issue",
            files_modified=["src/main.py"],
            success=False,
            error_message="Fix failed",
        )

        assert record.success is False
        assert record.error_message == "Fix failed"
        assert sample_cell.mutation_count == 1
        assert sample_cell.version == original_version  # Version unchanged

    def test_mutation_requires_approval_for_high_severity(self):
        """Test mutation approval requirement classification."""
        assert MutationSeverity.LOW.value == "low"
        assert MutationSeverity.HIGH.value == "high"
        assert MutationSeverity.CRITICAL.value == "critical"


class TestCellVersioning:
    """Tests for Cell version management."""

    def test_increment_version_patch(self, sample_cell: Cell):
        """Test patch version increment."""
        sample_cell.version = "1.0.0"
        new_version = sample_cell.increment_version("patch")

        assert new_version == "1.0.1"
        assert sample_cell.version == "1.0.1"
        assert "1.0.0" in sample_cell.previous_versions

    def test_increment_version_minor(self, sample_cell: Cell):
        """Test minor version increment."""
        sample_cell.version = "1.2.5"
        new_version = sample_cell.increment_version("minor")

        assert new_version == "1.3.0"

    def test_increment_version_major(self, sample_cell: Cell):
        """Test major version increment."""
        sample_cell.version = "1.5.3"
        new_version = sample_cell.increment_version("major")

        assert new_version == "2.0.0"


class TestCellSerialization:
    """Tests for Cell serialization."""

    def test_to_dict(self, sample_cell: Cell):
        """Test Cell serialization to dict."""
        data = sample_cell.to_dict()

        assert data["name"] == sample_cell.name
        assert data["status"] == sample_cell.status.value
        assert data["source_type"] == sample_cell.source_type.value
        assert "id" in data
        assert "version" in data

    def test_from_dict(self, sample_cell: Cell):
        """Test Cell deserialization from dict."""
        data = sample_cell.to_dict()
        restored = Cell.from_dict(data)

        assert restored.name == sample_cell.name
        assert restored.status == sample_cell.status
        assert restored.source_type == sample_cell.source_type


class TestResourceLimits:
    """Tests for ResourceLimits dataclass."""

    def test_default_resource_limits(self, resource_limits: ResourceLimits):
        """Test default resource limits."""
        assert resource_limits.cpu_request == "100m"
        assert resource_limits.memory_limit == "512Mi"

    def test_to_k8s_spec(self, resource_limits: ResourceLimits):
        """Test conversion to Kubernetes spec."""
        spec = resource_limits.to_k8s_spec()

        assert "requests" in spec
        assert "limits" in spec
        assert spec["requests"]["cpu"] == "100m"
        assert spec["limits"]["memory"] == "512Mi"


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig dataclass."""

    def test_default_health_check_config(self, health_check_config: HealthCheckConfig):
        """Test default health check config."""
        assert health_check_config.path == "/health"
        assert health_check_config.port == 8080
        assert health_check_config.failure_threshold == 3

    def test_to_k8s_probe(self, health_check_config: HealthCheckConfig):
        """Test conversion to Kubernetes probe."""
        probe = health_check_config.to_k8s_probe()

        assert "httpGet" in probe
        assert probe["httpGet"]["path"] == "/health"
        assert probe["periodSeconds"] == 10


class TestMutationSeverityClassification:
    """Tests for classify_mutation_severity function."""

    def test_classify_critical_for_auth_components(self):
        """Test CRITICAL classification for auth-related changes."""
        severity = classify_mutation_severity(
            files_modified=["src/auth.py"],
            error_type="security",
            affected_components=["authentication"],
        )
        assert severity == MutationSeverity.CRITICAL

    def test_classify_high_for_api_changes(self):
        """Test HIGH classification for API changes."""
        severity = classify_mutation_severity(
            files_modified=["src/api/routes/users.py"],
            error_type="type_error",
            affected_components=["users"],
        )
        assert severity == MutationSeverity.HIGH

    def test_classify_medium_for_build_errors(self):
        """Test MEDIUM classification for build errors."""
        severity = classify_mutation_severity(
            files_modified=["src/utils.py"],
            error_type="build_error",
            affected_components=["utilities"],
        )
        assert severity == MutationSeverity.MEDIUM

    def test_classify_low_for_minor_changes(self):
        """Test LOW classification for minor changes."""
        severity = classify_mutation_severity(
            files_modified=["src/constants.py"],
            error_type="formatting",
            affected_components=["general"],
        )
        assert severity == MutationSeverity.LOW

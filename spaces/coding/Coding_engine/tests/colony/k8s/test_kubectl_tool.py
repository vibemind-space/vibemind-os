"""
Tests for KubectlTool wrapper.

Tests:
- Manifest operations (apply, delete)
- Resource operations (get, list, patch)
- Pod operations (status, logs, exec)
- Deployment operations (status, scale, restart, rollback)
- Cell-specific operations
- Error handling
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.colony.k8s.kubectl_tool import (
    KubectlTool, KubectlResult, PodStatus, DeploymentStatus,
)


class TestKubectlToolInitialization:
    """Tests for KubectlTool initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        tool = KubectlTool()

        assert tool.namespace == "default"
        assert tool.context is None
        assert tool.kubeconfig is None
        assert tool.timeout == 60

    def test_custom_initialization(self):
        """Test initialization with custom values."""
        tool = KubectlTool(
            namespace="cell-colony",
            context="production",
            kubeconfig="/path/to/config",
            timeout=120,
        )

        assert tool.namespace == "cell-colony"
        assert tool.context == "production"
        assert tool.kubeconfig == "/path/to/config"
        assert tool.timeout == 120


class TestKubectlToolCommandBuilding:
    """Tests for command building."""

    def test_build_base_command_default(self):
        """Test base command with defaults."""
        tool = KubectlTool(namespace="test")

        cmd = tool._build_base_command()

        assert cmd[0] == "kubectl"
        assert "-n" in cmd
        assert "test" in cmd

    def test_build_base_command_with_context(self):
        """Test base command with context."""
        tool = KubectlTool(context="prod")

        cmd = tool._build_base_command()

        assert "--context" in cmd
        assert "prod" in cmd

    def test_build_base_command_with_kubeconfig(self):
        """Test base command with kubeconfig."""
        tool = KubectlTool(kubeconfig="/path/to/config")

        cmd = tool._build_base_command()

        assert "--kubeconfig" in cmd
        assert "/path/to/config" in cmd


class TestKubectlToolManifestOperations:
    """Tests for manifest operations."""

    @pytest.mark.asyncio
    async def test_apply_manifest_success(self, mock_kubectl_tool: MagicMock):
        """Test applying a manifest successfully."""
        manifest = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  key: value
"""
        result = await mock_kubectl_tool.apply_manifest(manifest)

        assert result.success is True
        mock_kubectl_tool.apply_manifest.assert_called_once_with(manifest)

    @pytest.mark.asyncio
    async def test_apply_manifest_with_dry_run(self):
        """Test applying manifest with dry-run."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"created", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.apply_manifest("test: yaml", dry_run=True)

            # Check that --dry-run was added to command
            call_args = mock_exec.call_args[0]
            assert "--dry-run=client" in call_args

    @pytest.mark.asyncio
    async def test_delete_manifest(self, mock_kubectl_tool: MagicMock):
        """Test deleting a manifest."""
        manifest = "kind: ConfigMap\nname: test"

        result = await mock_kubectl_tool.delete_manifest(manifest)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_delete_resource(self, mock_kubectl_tool: MagicMock):
        """Test deleting a specific resource."""
        result = await mock_kubectl_tool.delete_resource("pod", "test-pod")

        assert result.success is True


class TestKubectlToolResourceOperations:
    """Tests for resource operations."""

    @pytest.mark.asyncio
    async def test_get_resource(self, mock_kubectl_tool: MagicMock):
        """Test getting a resource."""
        result = await mock_kubectl_tool.get_resource("pod", "test-pod")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_list_resources_with_selector(self):
        """Test listing resources with label selector."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(
                b'{"items": []}',
                b"",
            ))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.list_resources(
                "pod",
                label_selector="app=myapp",
            )

            call_args = mock_exec.call_args[0]
            assert "-l" in call_args
            assert "app=myapp" in call_args

    @pytest.mark.asyncio
    async def test_patch_resource(self):
        """Test patching a resource."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"patched", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            patch_data = {"spec": {"replicas": 3}}
            result = await tool.patch_resource("deployment", "test", patch_data)

            assert result.success is True


class TestKubectlToolPodOperations:
    """Tests for pod operations."""

    @pytest.mark.asyncio
    async def test_get_pod_status(self, mock_kubectl_tool: MagicMock):
        """Test getting pod status."""
        status = await mock_kubectl_tool.get_pod_status("test-pod")

        assert status is not None
        assert status.name == "test-pod"
        assert status.is_running is True

    @pytest.mark.asyncio
    async def test_get_pod_logs(self, mock_kubectl_tool: MagicMock):
        """Test getting pod logs."""
        result = await mock_kubectl_tool.get_pod_logs("test-pod")

        assert result.success is True
        assert "Application started" in result.stdout

    @pytest.mark.asyncio
    async def test_get_pod_logs_with_options(self):
        """Test getting pod logs with options."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"log lines", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.get_pod_logs(
                "test-pod",
                container="main",
                tail=50,
                previous=True,
            )

            call_args = mock_exec.call_args[0]
            assert "-c" in call_args
            assert "main" in call_args
            assert "--tail=50" in call_args
            assert "--previous" in call_args

    @pytest.mark.asyncio
    async def test_exec_in_pod(self):
        """Test executing command in pod."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"output", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.exec_in_pod("test-pod", ["ls", "-la"])

            call_args = mock_exec.call_args[0]
            assert "exec" in call_args
            assert "--" in call_args


class TestKubectlToolDeploymentOperations:
    """Tests for deployment operations."""

    @pytest.mark.asyncio
    async def test_get_deployment_status(self, mock_kubectl_tool: MagicMock):
        """Test getting deployment status."""
        status = await mock_kubectl_tool.get_deployment_status("test-deployment")

        assert status is not None
        assert status.name == "test-deployment"
        assert status.is_ready is True

    @pytest.mark.asyncio
    async def test_scale_deployment(self):
        """Test scaling a deployment."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"scaled", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.scale_deployment("test-deploy", 5)

            call_args = mock_exec.call_args[0]
            assert "scale" in call_args
            assert "--replicas=5" in call_args

    @pytest.mark.asyncio
    async def test_restart_deployment(self):
        """Test restarting a deployment."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"restarted", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.restart_deployment("test-deploy")

            assert result.success is True

    @pytest.mark.asyncio
    async def test_rollback_deployment(self):
        """Test rolling back a deployment."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"rolled back", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.rollback_deployment("test-deploy", revision=2)

            call_args = mock_exec.call_args[0]
            assert "rollout" in call_args
            assert "undo" in call_args
            assert "--to-revision=2" in call_args


class TestKubectlToolCellOperations:
    """Tests for Cell-specific operations."""

    @pytest.mark.asyncio
    async def test_apply_cell_resources(self, mock_kubectl_tool: MagicMock):
        """Test applying all cell resources."""
        success, errors = await mock_kubectl_tool.apply_cell_resources(
            cell_manifest="cell yaml",
            deployment_manifest="deployment yaml",
            service_manifest="service yaml",
        )

        assert success is True
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_delete_cell_resources(self, mock_kubectl_tool: MagicMock):
        """Test deleting all cell resources."""
        success, errors = await mock_kubectl_tool.delete_cell_resources("test-cell")

        assert success is True
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_update_cell_status(self):
        """Test updating Cell CRD status."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"patched", b""))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.update_cell_status(
                "test-cell",
                {"phase": "Running", "healthScore": 0.9},
            )

            call_args = mock_exec.call_args[0]
            assert "--subresource=status" in call_args


class TestKubectlToolClusterOperations:
    """Tests for cluster operations."""

    @pytest.mark.asyncio
    async def test_check_connectivity(self, mock_kubectl_tool: MagicMock):
        """Test checking cluster connectivity."""
        result = await mock_kubectl_tool.check_connectivity()

        assert result is True

    @pytest.mark.asyncio
    async def test_get_namespaces(self):
        """Test getting namespaces."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(
                json.dumps({
                    "items": [
                        {"metadata": {"name": "default"}},
                        {"metadata": {"name": "kube-system"}},
                    ]
                }).encode(),
                b"",
            ))
            mock_exec.return_value = mock_process

            tool = KubectlTool(namespace=None)  # No default namespace
            namespaces = await tool.get_namespaces()

            assert "default" in namespaces
            assert "kube-system" in namespaces


class TestKubectlToolErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_command_failure(self):
        """Test handling command failure."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(
                b"",
                b"Error: resource not found",
            ))
            mock_exec.return_value = mock_process

            tool = KubectlTool()
            result = await tool.get_resource("pod", "nonexistent")

            assert result.success is False
            assert "not found" in result.stderr

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """Test handling command timeout."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_exec.return_value = mock_process

            tool = KubectlTool(timeout=1)
            result = await tool._run_command(["get", "pods"])

            assert result.success is False
            assert "timed out" in result.stderr

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test handling unexpected exceptions."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = Exception("Unexpected error")

            tool = KubectlTool()
            result = await tool._run_command(["get", "pods"])

            assert result.success is False
            assert "Unexpected error" in result.stderr


class TestKubectlResult:
    """Tests for KubectlResult dataclass."""

    def test_kubectl_result_success(self, kubectl_result_success: KubectlResult):
        """Test successful KubectlResult."""
        assert kubectl_result_success.success is True
        assert "created" in kubectl_result_success.stdout

    def test_kubectl_result_failure(self, kubectl_result_failure: KubectlResult):
        """Test failed KubectlResult."""
        assert kubectl_result_failure.success is False
        assert kubectl_result_failure.return_code == 1

    def test_kubectl_result_json_output(self):
        """Test JSON output parsing."""
        result = KubectlResult(
            success=True,
            stdout='{"kind": "Pod", "metadata": {"name": "test"}}',
        )

        json_output = result.json_output

        assert json_output is not None
        assert json_output["kind"] == "Pod"

    def test_kubectl_result_invalid_json(self):
        """Test invalid JSON handling."""
        result = KubectlResult(
            success=True,
            stdout="not json",
        )

        assert result.json_output is None


class TestPodStatus:
    """Tests for PodStatus dataclass."""

    def test_pod_status_is_running(self):
        """Test is_running property."""
        status = PodStatus(
            name="test",
            namespace="default",
            phase="Running",
            ready=True,
            containers_ready=1,
            containers_total=1,
            restarts=0,
            age="1h",
        )

        assert status.is_running is True

    def test_pod_status_not_running(self):
        """Test is_running when pod not ready."""
        status = PodStatus(
            name="test",
            namespace="default",
            phase="Pending",
            ready=False,
            containers_ready=0,
            containers_total=1,
            restarts=0,
            age="1m",
        )

        assert status.is_running is False


class TestDeploymentStatus:
    """Tests for DeploymentStatus dataclass."""

    def test_deployment_status_is_ready(self):
        """Test is_ready property."""
        status = DeploymentStatus(
            name="test",
            namespace="default",
            ready_replicas=3,
            desired_replicas=3,
            available_replicas=3,
            unavailable_replicas=0,
        )

        assert status.is_ready is True

    def test_deployment_status_not_ready(self):
        """Test is_ready when deployment not ready."""
        status = DeploymentStatus(
            name="test",
            namespace="default",
            ready_replicas=2,
            desired_replicas=3,
            available_replicas=2,
            unavailable_replicas=1,
        )

        assert status.is_ready is False

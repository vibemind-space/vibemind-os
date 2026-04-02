"""
Kubectl Tool - Wrapper for Kubernetes operations.

Provides async operations for:
- Applying and deleting manifests
- Getting resource status
- Retrieving pod logs
- Port forwarding
- Executing commands in pods

Used by CellAgent and ColonyManager for K8s interactions.
"""

import asyncio
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import structlog
import yaml

logger = structlog.get_logger(__name__)


@dataclass
class KubectlResult:
    """Result of a kubectl command."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    command: str = ""
    duration_ms: int = 0

    @property
    def json_output(self) -> Optional[Dict[str, Any]]:
        """Parse stdout as JSON if possible."""
        if self.success and self.stdout:
            try:
                return json.loads(self.stdout)
            except json.JSONDecodeError:
                return None
        return None


@dataclass
class PodStatus:
    """Status of a Kubernetes pod."""
    name: str
    namespace: str
    phase: str  # Pending, Running, Succeeded, Failed, Unknown
    ready: bool
    containers_ready: int
    containers_total: int
    restarts: int
    age: str
    ip: Optional[str] = None
    node: Optional[str] = None
    conditions: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        return self.phase == "Running" and self.ready


@dataclass
class DeploymentStatus:
    """Status of a Kubernetes deployment."""
    name: str
    namespace: str
    ready_replicas: int
    desired_replicas: int
    available_replicas: int
    unavailable_replicas: int
    conditions: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return self.ready_replicas == self.desired_replicas and self.desired_replicas > 0


class KubectlTool:
    """
    Async wrapper for kubectl operations.

    Provides high-level operations for managing Kubernetes resources
    used by the Cell Colony system.

    Usage:
        tool = KubectlTool(namespace="cell-colony")
        await tool.apply_manifest(yaml_content)
        status = await tool.get_deployment_status("my-deployment")
    """

    def __init__(
        self,
        namespace: str = "default",
        context: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        timeout: int = 60,
    ):
        """
        Initialize the kubectl tool.

        Args:
            namespace: Default namespace for operations
            context: Kubernetes context to use
            kubeconfig: Path to kubeconfig file
            timeout: Default timeout for operations in seconds
        """
        self.namespace = namespace
        self.context = context
        self.kubeconfig = kubeconfig
        self.timeout = timeout
        self.logger = logger.bind(component="kubectl_tool", namespace=namespace)

    def _build_base_command(self) -> List[str]:
        """Build base kubectl command with common flags."""
        cmd = ["kubectl"]

        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            cmd.extend(["--context", self.context])
        if self.namespace:
            cmd.extend(["-n", self.namespace])

        return cmd

    async def _run_command(
        self,
        args: List[str],
        input_data: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> KubectlResult:
        """
        Run a kubectl command asynchronously.

        Args:
            args: Command arguments (excluding 'kubectl')
            input_data: Optional stdin data
            timeout: Command timeout in seconds

        Returns:
            KubectlResult with output and status
        """
        import time

        cmd = self._build_base_command() + args
        cmd_str = " ".join(cmd)
        effective_timeout = timeout or self.timeout

        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_data.encode() if input_data else None),
                timeout=effective_timeout,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            result = KubectlResult(
                success=process.returncode == 0,
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                return_code=process.returncode or 0,
                command=cmd_str,
                duration_ms=duration_ms,
            )

            if not result.success:
                self.logger.warning(
                    "kubectl_command_failed",
                    command=cmd_str,
                    return_code=result.return_code,
                    stderr=result.stderr[:500],
                )

            return result

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            return KubectlResult(
                success=False,
                stderr=f"Command timed out after {effective_timeout}s",
                command=cmd_str,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return KubectlResult(
                success=False,
                stderr=str(e),
                command=cmd_str,
                duration_ms=duration_ms,
            )

    # =========================================================================
    # Manifest Operations
    # =========================================================================

    async def apply_manifest(
        self,
        manifest: str,
        dry_run: bool = False,
    ) -> KubectlResult:
        """
        Apply a YAML manifest to the cluster.

        Args:
            manifest: YAML manifest content
            dry_run: If True, only validate without applying

        Returns:
            KubectlResult
        """
        args = ["apply", "-f", "-"]
        if dry_run:
            args.append("--dry-run=client")

        self.logger.debug("applying_manifest", dry_run=dry_run)
        return await self._run_command(args, input_data=manifest)

    async def apply_file(
        self,
        file_path: str,
        dry_run: bool = False,
    ) -> KubectlResult:
        """Apply a manifest file."""
        args = ["apply", "-f", file_path]
        if dry_run:
            args.append("--dry-run=client")

        return await self._run_command(args)

    async def delete_manifest(self, manifest: str) -> KubectlResult:
        """Delete resources defined in a manifest."""
        return await self._run_command(
            ["delete", "-f", "-", "--ignore-not-found"],
            input_data=manifest,
        )

    async def delete_resource(
        self,
        kind: str,
        name: str,
        wait: bool = False,
    ) -> KubectlResult:
        """
        Delete a specific resource.

        Args:
            kind: Resource kind (pod, deployment, service, etc.)
            name: Resource name
            wait: Wait for deletion to complete

        Returns:
            KubectlResult
        """
        args = ["delete", kind, name, "--ignore-not-found"]
        if wait:
            args.append("--wait=true")

        return await self._run_command(args)

    # =========================================================================
    # Resource Operations
    # =========================================================================

    async def get_resource(
        self,
        kind: str,
        name: str,
        output: str = "json",
    ) -> KubectlResult:
        """
        Get a specific resource.

        Args:
            kind: Resource kind
            name: Resource name
            output: Output format (json, yaml, wide)

        Returns:
            KubectlResult with resource data
        """
        return await self._run_command(
            ["get", kind, name, "-o", output]
        )

    async def list_resources(
        self,
        kind: str,
        label_selector: Optional[str] = None,
        field_selector: Optional[str] = None,
        output: str = "json",
    ) -> KubectlResult:
        """
        List resources of a specific kind.

        Args:
            kind: Resource kind
            label_selector: Label selector (e.g., "app=myapp")
            field_selector: Field selector
            output: Output format

        Returns:
            KubectlResult with list data
        """
        args = ["get", kind, "-o", output]
        if label_selector:
            args.extend(["-l", label_selector])
        if field_selector:
            args.extend(["--field-selector", field_selector])

        return await self._run_command(args)

    async def patch_resource(
        self,
        kind: str,
        name: str,
        patch: Dict[str, Any],
        patch_type: str = "strategic",
    ) -> KubectlResult:
        """
        Patch a resource.

        Args:
            kind: Resource kind
            name: Resource name
            patch: Patch data
            patch_type: Type of patch (strategic, merge, json)

        Returns:
            KubectlResult
        """
        return await self._run_command(
            ["patch", kind, name, "--type", patch_type, "-p", json.dumps(patch)]
        )

    # =========================================================================
    # Pod Operations
    # =========================================================================

    async def get_pod_status(self, name: str) -> Optional[PodStatus]:
        """Get detailed status of a pod."""
        result = await self.get_resource("pod", name)
        if not result.success or not result.json_output:
            return None

        pod = result.json_output
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        spec = pod.get("spec", {})

        containers = status.get("containerStatuses", [])
        ready_containers = sum(1 for c in containers if c.get("ready", False))
        total_containers = len(spec.get("containers", []))
        restarts = sum(c.get("restartCount", 0) for c in containers)

        conditions = status.get("conditions", [])
        ready_condition = next(
            (c for c in conditions if c.get("type") == "Ready"),
            {}
        )

        return PodStatus(
            name=metadata.get("name", name),
            namespace=metadata.get("namespace", self.namespace),
            phase=status.get("phase", "Unknown"),
            ready=ready_condition.get("status") == "True",
            containers_ready=ready_containers,
            containers_total=total_containers,
            restarts=restarts,
            age=metadata.get("creationTimestamp", ""),
            ip=status.get("podIP"),
            node=spec.get("nodeName"),
            conditions=conditions,
        )

    async def get_pod_logs(
        self,
        name: str,
        container: Optional[str] = None,
        tail: int = 100,
        previous: bool = False,
    ) -> KubectlResult:
        """
        Get logs from a pod.

        Args:
            name: Pod name
            container: Container name (if multiple)
            tail: Number of lines to return
            previous: Get logs from previous container instance

        Returns:
            KubectlResult with logs in stdout
        """
        args = ["logs", name, f"--tail={tail}"]
        if container:
            args.extend(["-c", container])
        if previous:
            args.append("--previous")

        return await self._run_command(args)

    async def exec_in_pod(
        self,
        name: str,
        command: List[str],
        container: Optional[str] = None,
    ) -> KubectlResult:
        """
        Execute a command in a pod.

        Args:
            name: Pod name
            command: Command to execute
            container: Container name (if multiple)

        Returns:
            KubectlResult with command output
        """
        args = ["exec", name]
        if container:
            args.extend(["-c", container])
        args.append("--")
        args.extend(command)

        return await self._run_command(args)

    # =========================================================================
    # Deployment Operations
    # =========================================================================

    async def get_deployment_status(self, name: str) -> Optional[DeploymentStatus]:
        """Get detailed status of a deployment."""
        result = await self.get_resource("deployment", name)
        if not result.success or not result.json_output:
            return None

        deployment = result.json_output
        metadata = deployment.get("metadata", {})
        status = deployment.get("status", {})
        spec = deployment.get("spec", {})

        return DeploymentStatus(
            name=metadata.get("name", name),
            namespace=metadata.get("namespace", self.namespace),
            ready_replicas=status.get("readyReplicas", 0),
            desired_replicas=spec.get("replicas", 0),
            available_replicas=status.get("availableReplicas", 0),
            unavailable_replicas=status.get("unavailableReplicas", 0),
            conditions=status.get("conditions", []),
        )

    async def scale_deployment(
        self,
        name: str,
        replicas: int,
    ) -> KubectlResult:
        """Scale a deployment to a specific number of replicas."""
        return await self._run_command(
            ["scale", "deployment", name, f"--replicas={replicas}"]
        )

    async def restart_deployment(self, name: str) -> KubectlResult:
        """Restart a deployment by patching the annotation."""
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": datetime.now().isoformat()
                        }
                    }
                }
            }
        }
        return await self.patch_resource("deployment", name, patch)

    async def rollback_deployment(
        self,
        name: str,
        revision: Optional[int] = None,
    ) -> KubectlResult:
        """Rollback a deployment to a previous revision."""
        args = ["rollout", "undo", "deployment", name]
        if revision:
            args.extend([f"--to-revision={revision}"])

        return await self._run_command(args)

    async def get_rollout_status(self, name: str) -> KubectlResult:
        """Get the rollout status of a deployment."""
        return await self._run_command(
            ["rollout", "status", "deployment", name, "--watch=false"]
        )

    # =========================================================================
    # Service Operations
    # =========================================================================

    async def port_forward(
        self,
        resource: str,
        local_port: int,
        remote_port: int,
    ) -> asyncio.subprocess.Process:
        """
        Start port forwarding (non-blocking).

        Note: Returns the process - caller is responsible for terminating.

        Args:
            resource: Resource to forward to (e.g., "pod/mypod", "svc/myservice")
            local_port: Local port
            remote_port: Remote port

        Returns:
            asyncio.subprocess.Process
        """
        cmd = self._build_base_command() + [
            "port-forward",
            resource,
            f"{local_port}:{remote_port}",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return process

    # =========================================================================
    # Cell-Specific Operations
    # =========================================================================

    async def apply_cell_resources(
        self,
        cell_manifest: str,
        deployment_manifest: str,
        service_manifest: str,
        configmap_manifest: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Apply all resources for a cell.

        Args:
            cell_manifest: Cell CRD manifest
            deployment_manifest: Deployment manifest
            service_manifest: Service manifest
            configmap_manifest: Optional ConfigMap manifest

        Returns:
            Tuple of (success, list of errors)
        """
        errors = []

        # Apply Cell CRD first
        result = await self.apply_manifest(cell_manifest)
        if not result.success:
            errors.append(f"Cell CRD: {result.stderr}")

        # Apply ConfigMap if provided
        if configmap_manifest:
            result = await self.apply_manifest(configmap_manifest)
            if not result.success:
                errors.append(f"ConfigMap: {result.stderr}")

        # Apply Deployment
        result = await self.apply_manifest(deployment_manifest)
        if not result.success:
            errors.append(f"Deployment: {result.stderr}")

        # Apply Service
        result = await self.apply_manifest(service_manifest)
        if not result.success:
            errors.append(f"Service: {result.stderr}")

        return len(errors) == 0, errors

    async def delete_cell_resources(
        self,
        cell_name: str,
        wait: bool = True,
    ) -> Tuple[bool, List[str]]:
        """
        Delete all resources for a cell.

        Args:
            cell_name: Name of the cell
            wait: Wait for deletion to complete

        Returns:
            Tuple of (success, list of errors)
        """
        errors = []
        resource_types = ["service", "deployment", "configmap", "cell"]

        for resource_type in resource_types:
            result = await self.delete_resource(resource_type, cell_name, wait=wait)
            if not result.success and "not found" not in result.stderr.lower():
                errors.append(f"{resource_type}: {result.stderr}")

        return len(errors) == 0, errors

    async def get_cells(
        self,
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all Cell resources.

        Args:
            label_selector: Optional label selector

        Returns:
            List of Cell resource dicts
        """
        result = await self.list_resources("cell", label_selector=label_selector)
        if not result.success or not result.json_output:
            return []

        items = result.json_output.get("items", [])
        return items

    async def update_cell_status(
        self,
        name: str,
        status_patch: Dict[str, Any],
    ) -> KubectlResult:
        """
        Update the status subresource of a Cell.

        Args:
            name: Cell name
            status_patch: Status fields to update

        Returns:
            KubectlResult
        """
        patch = {"status": status_patch}
        return await self._run_command(
            ["patch", "cell", name, "--type", "merge", "--subresource=status",
             "-p", json.dumps(patch)]
        )

    # =========================================================================
    # Cluster Operations
    # =========================================================================

    async def check_connectivity(self) -> bool:
        """Check if kubectl can connect to the cluster."""
        result = await self._run_command(["cluster-info"], timeout=10)
        return result.success

    async def get_namespaces(self) -> List[str]:
        """Get list of all namespaces."""
        result = await self.list_resources("namespace")
        if not result.success or not result.json_output:
            return []

        items = result.json_output.get("items", [])
        return [item.get("metadata", {}).get("name", "") for item in items]

    async def create_namespace(self, name: str) -> KubectlResult:
        """Create a namespace if it doesn't exist."""
        return await self._run_command(
            ["create", "namespace", name, "--dry-run=client", "-o", "yaml"]
        )

    async def apply_crds(self, crd_path: str) -> KubectlResult:
        """Apply Custom Resource Definitions."""
        return await self.apply_file(crd_path)

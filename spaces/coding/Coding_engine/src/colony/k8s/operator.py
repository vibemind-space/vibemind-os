"""
Kubernetes Operator for Cell Colony.

A kopf-based operator that watches Cell and Colony custom resources
and reconciles Kubernetes resources accordingly.

Features:
- Create/Update/Delete Deployments, Services, ConfigMaps for Cells
- Health monitoring and status updates
- Automatic recovery triggers
- Colony-wide scaling decisions

Usage:
    kopf run src/colony/k8s/operator.py --standalone
"""

import asyncio
import structlog
from datetime import datetime
from typing import Optional

try:
    import kopf
    KOPF_AVAILABLE = True
except ImportError:
    KOPF_AVAILABLE = False
    # Create dummy decorators for when kopf isn't installed
    class DummyKopf:
        @staticmethod
        def on(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
        timer = on
        daemon = on
    kopf = DummyKopf()

from src.colony.cell import Cell, CellStatus, SourceType, ResourceLimits
from src.colony.k8s.kubectl_tool import KubectlTool
from src.colony.k8s.resource_generator import ResourceGenerator
from src.mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger()

# Constants
CRD_GROUP = "colony.codingengine.io"
CRD_VERSION = "v1"
CELL_PLURAL = "cells"
COLONY_PLURAL = "colonies"


class CellOperator:
    """
    Operator for managing Cell custom resources.

    Watches for Cell CR changes and reconciles the corresponding
    Kubernetes resources (Deployment, Service, ConfigMap).
    """

    def __init__(
        self,
        kubectl: Optional[KubectlTool] = None,
        resource_generator: Optional[ResourceGenerator] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the operator.

        Args:
            kubectl: Kubectl wrapper for K8s operations
            resource_generator: Generator for K8s manifests
            event_bus: EventBus for emitting lifecycle events
        """
        self.kubectl = kubectl or KubectlTool()
        self.generator = resource_generator or ResourceGenerator()
        self.event_bus = event_bus
        self._cells: dict[str, Cell] = {}

    def _spec_to_cell(self, name: str, namespace: str, spec: dict) -> Cell:
        """
        Convert a Cell CR spec to a Cell object.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec dictionary

        Returns:
            Cell object
        """
        # Parse resource limits if provided
        resource_limits = ResourceLimits()
        if "resources" in spec:
            res = spec["resources"]
            if "requests" in res:
                resource_limits.cpu_request = res["requests"].get("cpu", "100m")
                resource_limits.memory_request = res["requests"].get("memory", "128Mi")
            if "limits" in res:
                resource_limits.cpu_limit = res["limits"].get("cpu", "500m")
                resource_limits.memory_limit = res["limits"].get("memory", "512Mi")

        # Determine source type
        source_type = SourceType.LLM_GENERATED
        if spec.get("sourceType"):
            try:
                source_type = SourceType(spec["sourceType"])
            except ValueError:
                pass

        return Cell(
            id=spec.get("cellId", name),
            name=name,
            namespace=namespace,
            source_type=source_type,
            source_ref=spec.get("sourceRef", ""),
            working_dir=spec.get("workingDir", f"/app/cells/{name}"),
            image=spec.get("image"),
            resource_limits=resource_limits,
            ports=spec.get("ports", [8080]),
            env_vars=spec.get("env", {}),
        )

    async def _publish_event(self, event_type: EventType, cell: Cell, **kwargs) -> None:
        """Publish an event if event bus is available."""
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=event_type,
                source=f"cell_operator/{cell.id}",
                data={
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "namespace": cell.namespace,
                    **kwargs,
                },
            ))

    async def on_create(self, name: str, namespace: str, spec: dict, **kwargs) -> dict:
        """
        Handle Cell creation.

        Creates Deployment, Service, and ConfigMap for the cell.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec

        Returns:
            Status update for the CR
        """
        logger.info("cell_create", name=name, namespace=namespace)

        cell = self._spec_to_cell(name, namespace, spec)
        self._cells[cell.id] = cell

        # Generate K8s resources
        resources = self.generator.generate_all(cell)

        # Apply resources
        try:
            # Apply ConfigMap first
            config_result = await self.kubectl.apply_manifest(resources.configmap_yaml)
            if not config_result.success:
                raise Exception(f"Failed to create ConfigMap: {config_result.error}")

            # Apply Service
            svc_result = await self.kubectl.apply_manifest(resources.service_yaml)
            if not svc_result.success:
                raise Exception(f"Failed to create Service: {svc_result.error}")

            # Apply Deployment
            deploy_result = await self.kubectl.apply_manifest(resources.deployment_yaml)
            if not deploy_result.success:
                raise Exception(f"Failed to create Deployment: {deploy_result.error}")

            # Apply HPA if present
            if resources.hpa_yaml:
                await self.kubectl.apply_manifest(resources.hpa_yaml)

            # Apply NetworkPolicy if present
            if resources.network_policy_yaml:
                await self.kubectl.apply_manifest(resources.network_policy_yaml)

            cell.status = CellStatus.DEPLOYING
            await self._publish_event(EventType.CELL_CREATED, cell)

            return {
                "phase": "Deploying",
                "message": "Resources created successfully",
                "deploymentName": cell.k8s_deployment_name,
                "serviceName": cell.k8s_service_name,
            }

        except Exception as e:
            logger.error("cell_create_failed", name=name, error=str(e))
            cell.status = CellStatus.DEGRADED
            return {
                "phase": "Failed",
                "message": str(e),
            }

    async def on_update(self, name: str, namespace: str, spec: dict, status: dict, **kwargs) -> dict:
        """
        Handle Cell update.

        Updates existing K8s resources based on spec changes.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec
            status: Current CR status

        Returns:
            Status update for the CR
        """
        logger.info("cell_update", name=name, namespace=namespace)

        cell = self._spec_to_cell(name, namespace, spec)
        self._cells[cell.id] = cell

        # Regenerate resources
        resources = self.generator.generate_all(cell)

        try:
            # Apply updated resources
            await self.kubectl.apply_manifest(resources.configmap_yaml)
            await self.kubectl.apply_manifest(resources.service_yaml)
            await self.kubectl.apply_manifest(resources.deployment_yaml)

            return {
                "phase": "Running",
                "message": "Resources updated successfully",
                "lastUpdated": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("cell_update_failed", name=name, error=str(e))
            return {
                "phase": "Degraded",
                "message": f"Update failed: {e}",
            }

    async def on_delete(self, name: str, namespace: str, spec: dict, **kwargs) -> None:
        """
        Handle Cell deletion.

        Cleans up all K8s resources associated with the cell.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec
        """
        logger.info("cell_delete", name=name, namespace=namespace)

        cell_id = spec.get("cellId", name)

        # Delete K8s resources
        try:
            await self.kubectl.delete_resource("deployment", f"cell-{name}-{cell_id[:8]}", namespace)
            await self.kubectl.delete_resource("service", f"cell-{name}-svc", namespace)
            await self.kubectl.delete_resource("configmap", f"cell-{name}-config", namespace)
            await self.kubectl.delete_resource("hpa", f"cell-{name}-hpa", namespace)
            await self.kubectl.delete_resource("networkpolicy", f"cell-{name}-netpol", namespace)
        except Exception as e:
            logger.warning("cell_delete_resource_error", name=name, error=str(e))

        # Remove from internal tracking
        if cell_id in self._cells:
            cell = self._cells.pop(cell_id)
            await self._publish_event(EventType.CELL_TERMINATED, cell)

    async def check_health(self, name: str, namespace: str, spec: dict, status: dict) -> dict:
        """
        Check health of a cell and update status.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec
            status: Current CR status

        Returns:
            Updated status
        """
        cell_id = spec.get("cellId", name)

        try:
            # Get deployment status
            deploy_status = await self.kubectl.get_deployment_status(
                f"cell-{name}-{cell_id[:8]}",
                namespace,
            )

            if deploy_status.ready_replicas == deploy_status.desired_replicas:
                phase = "Healthy"
                health_score = 1.0
            elif deploy_status.ready_replicas > 0:
                phase = "Degraded"
                health_score = deploy_status.ready_replicas / deploy_status.desired_replicas
            else:
                phase = "Unhealthy"
                health_score = 0.0

            return {
                "phase": phase,
                "healthScore": health_score,
                "readyReplicas": deploy_status.ready_replicas,
                "desiredReplicas": deploy_status.desired_replicas,
                "lastHealthCheck": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("health_check_failed", name=name, error=str(e))
            return {
                "phase": "Unknown",
                "message": f"Health check failed: {e}",
            }


class ColonyOperator:
    """
    Operator for managing Colony custom resources.

    Watches for Colony CR changes and manages colony-wide settings
    like autoscaling policies and health thresholds.
    """

    def __init__(
        self,
        kubectl: Optional[KubectlTool] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the operator.

        Args:
            kubectl: Kubectl wrapper for K8s operations
            event_bus: EventBus for emitting lifecycle events
        """
        self.kubectl = kubectl or KubectlTool()
        self.event_bus = event_bus
        self._colonies: dict[str, dict] = {}

    async def on_create(self, name: str, namespace: str, spec: dict, **kwargs) -> dict:
        """
        Handle Colony creation.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec

        Returns:
            Status update for the CR
        """
        logger.info("colony_create", name=name, namespace=namespace)

        self._colonies[name] = {
            "name": name,
            "namespace": namespace,
            "spec": spec,
            "cells": [],
        }

        return {
            "phase": "Active",
            "totalCells": 0,
            "healthyCells": 0,
            "degradedCells": 0,
            "convergenceStatus": "initializing",
        }

    async def on_update(self, name: str, namespace: str, spec: dict, status: dict, **kwargs) -> dict:
        """
        Handle Colony update.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec
            status: Current CR status

        Returns:
            Status update for the CR
        """
        logger.info("colony_update", name=name, namespace=namespace)

        if name in self._colonies:
            self._colonies[name]["spec"] = spec

        return {
            "phase": status.get("phase", "Active"),
            "lastUpdated": datetime.now().isoformat(),
        }

    async def on_delete(self, name: str, namespace: str, spec: dict, **kwargs) -> None:
        """
        Handle Colony deletion.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec
        """
        logger.info("colony_delete", name=name, namespace=namespace)

        if name in self._colonies:
            del self._colonies[name]

    async def reconcile_colony(self, name: str, namespace: str, spec: dict, status: dict) -> dict:
        """
        Reconcile colony state.

        Checks all cells in the colony and updates status.

        Args:
            name: Resource name
            namespace: K8s namespace
            spec: CR spec
            status: Current CR status

        Returns:
            Updated status
        """
        try:
            # List all Cell CRs in this namespace with colony label
            cells = await self.kubectl.list_resources(
                "cells.colony.codingengine.io",
                namespace,
                label_selector=f"colony.codingengine.io/colony={name}",
            )

            total_cells = len(cells)
            healthy_cells = sum(1 for c in cells if c.get("status", {}).get("phase") == "Healthy")
            degraded_cells = sum(1 for c in cells if c.get("status", {}).get("phase") == "Degraded")

            health_ratio = healthy_cells / total_cells if total_cells > 0 else 1.0

            # Check if rebalancing is needed
            min_health_ratio = spec.get("minHealthRatio", 0.8)
            convergence_status = "converged" if health_ratio >= min_health_ratio else "rebalancing"

            # Check autoscaling
            autoscaling = spec.get("autoScaling", {})
            if autoscaling.get("enabled", False):
                max_cells = autoscaling.get("maxCells", 10)
                min_cells = autoscaling.get("minCells", 1)

                if total_cells < min_cells:
                    convergence_status = "scaling_up"
                elif total_cells > max_cells:
                    convergence_status = "scaling_down"

            return {
                "phase": "Active",
                "totalCells": total_cells,
                "healthyCells": healthy_cells,
                "degradedCells": degraded_cells,
                "failedCells": total_cells - healthy_cells - degraded_cells,
                "healthRatio": health_ratio,
                "convergenceStatus": convergence_status,
                "lastReconciled": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("colony_reconcile_failed", name=name, error=str(e))
            return {
                "phase": "Degraded",
                "message": f"Reconciliation failed: {e}",
            }


# Initialize operators
cell_operator = CellOperator()
colony_operator = ColonyOperator()


# Register kopf handlers if available
if KOPF_AVAILABLE:

    @kopf.on.create(CRD_GROUP, CRD_VERSION, CELL_PLURAL)
    async def cell_create_handler(name, namespace, spec, **kwargs):
        return await cell_operator.on_create(name, namespace, spec, **kwargs)

    @kopf.on.update(CRD_GROUP, CRD_VERSION, CELL_PLURAL)
    async def cell_update_handler(name, namespace, spec, status, **kwargs):
        return await cell_operator.on_update(name, namespace, spec, status, **kwargs)

    @kopf.on.delete(CRD_GROUP, CRD_VERSION, CELL_PLURAL)
    async def cell_delete_handler(name, namespace, spec, **kwargs):
        await cell_operator.on_delete(name, namespace, spec, **kwargs)

    @kopf.timer(CRD_GROUP, CRD_VERSION, CELL_PLURAL, interval=30.0)
    async def cell_health_timer(name, namespace, spec, status, **kwargs):
        return await cell_operator.check_health(name, namespace, spec, status)

    @kopf.on.create(CRD_GROUP, CRD_VERSION, COLONY_PLURAL)
    async def colony_create_handler(name, namespace, spec, **kwargs):
        return await colony_operator.on_create(name, namespace, spec, **kwargs)

    @kopf.on.update(CRD_GROUP, CRD_VERSION, COLONY_PLURAL)
    async def colony_update_handler(name, namespace, spec, status, **kwargs):
        return await colony_operator.on_update(name, namespace, spec, status, **kwargs)

    @kopf.on.delete(CRD_GROUP, CRD_VERSION, COLONY_PLURAL)
    async def colony_delete_handler(name, namespace, spec, **kwargs):
        await colony_operator.on_delete(name, namespace, spec, **kwargs)

    @kopf.timer(CRD_GROUP, CRD_VERSION, COLONY_PLURAL, interval=60.0)
    async def colony_reconcile_timer(name, namespace, spec, status, **kwargs):
        return await colony_operator.reconcile_colony(name, namespace, spec, status)


def run_operator():
    """Run the operator standalone."""
    if not KOPF_AVAILABLE:
        raise ImportError("kopf is required to run the operator. Install with: pip install kopf")
    import kopf as real_kopf
    real_kopf.run()


if __name__ == "__main__":
    run_operator()

"""
Resource Generator - Generates Kubernetes manifests from Cell specs.

Converts Cell dataclass instances into K8s resource YAMLs:
- Deployment with resource limits and health probes
- Service for network access
- ConfigMap for configuration
- NetworkPolicy for isolation
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import yaml

from ..cell import Cell, CellStatus


@dataclass
class GeneratedResources:
    """Collection of generated K8s resources."""
    cell_manifest: str
    deployment_manifest: str
    service_manifest: str
    configmap_manifest: Optional[str] = None
    network_policy_manifest: Optional[str] = None
    service_account_manifest: Optional[str] = None

    def all_manifests(self) -> str:
        """Combine all manifests into a single YAML document."""
        manifests = [
            self.cell_manifest,
            self.deployment_manifest,
            self.service_manifest,
        ]
        if self.configmap_manifest:
            manifests.append(self.configmap_manifest)
        if self.network_policy_manifest:
            manifests.append(self.network_policy_manifest)
        if self.service_account_manifest:
            manifests.append(self.service_account_manifest)

        return "\n---\n".join(manifests)


class ResourceGenerator:
    """
    Generates Kubernetes manifests from Cell specifications.

    Usage:
        generator = ResourceGenerator()
        resources = generator.generate(cell)
        kubectl.apply_manifest(resources.deployment_manifest)
    """

    def __init__(
        self,
        registry: str = "cell-registry.local",
        image_pull_policy: str = "IfNotPresent",
        enable_network_policies: bool = True,
        enable_service_accounts: bool = True,
    ):
        self.registry = registry
        self.image_pull_policy = image_pull_policy
        self.enable_network_policies = enable_network_policies
        self.enable_service_accounts = enable_service_accounts

    def generate(
        self,
        cell: Cell,
        include_network_policy: bool = True,
        include_service_account: bool = True,
    ) -> GeneratedResources:
        """
        Generate all K8s resources for a cell.

        Args:
            cell: Cell to generate resources for
            include_network_policy: Include NetworkPolicy
            include_service_account: Include ServiceAccount

        Returns:
            GeneratedResources with all manifests
        """
        return GeneratedResources(
            cell_manifest=self._generate_cell_crd(cell),
            deployment_manifest=self._generate_deployment(cell),
            service_manifest=self._generate_service(cell),
            configmap_manifest=self._generate_configmap(cell) if cell.env_vars else None,
            network_policy_manifest=(
                self._generate_network_policy(cell)
                if include_network_policy and self.enable_network_policies
                else None
            ),
            service_account_manifest=(
                self._generate_service_account(cell)
                if include_service_account and self.enable_service_accounts
                else None
            ),
        )

    def _generate_cell_crd(self, cell: Cell) -> str:
        """Generate Cell CRD instance."""
        manifest = {
            "apiVersion": "colony.codingengine.io/v1",
            "kind": "Cell",
            "metadata": {
                "name": cell.name,
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
                "annotations": cell.annotations,
            },
            "spec": {
                "name": cell.name,
                "sourceType": cell.source_type.value,
                "sourceRef": cell.source_ref,
                "workingDir": cell.working_dir,
                "image": cell.image,
                "imageTag": cell.image_tag,
                "resources": {
                    "cpuRequest": cell.resource_limits.cpu_request,
                    "cpuLimit": cell.resource_limits.cpu_limit,
                    "memoryRequest": cell.resource_limits.memory_request,
                    "memoryLimit": cell.resource_limits.memory_limit,
                    "ephemeralStorageLimit": cell.resource_limits.ephemeral_storage_limit,
                },
                "healthCheck": {
                    "path": cell.health_check.path,
                    "port": cell.health_check.port,
                    "initialDelaySeconds": cell.health_check.initial_delay_seconds,
                    "periodSeconds": cell.health_check.period_seconds,
                    "timeoutSeconds": cell.health_check.timeout_seconds,
                    "failureThreshold": cell.health_check.failure_threshold,
                    "successThreshold": cell.health_check.success_threshold,
                },
                "ports": cell.ports,
                "dependsOn": cell.depends_on,
                "mutationPolicy": {
                    "maxMutations": cell.max_mutations,
                },
            },
        }

        if cell.owner_tenant_id:
            manifest["spec"]["ownerTenantId"] = cell.owner_tenant_id

        if cell.resource_limits.gpu_limit:
            manifest["spec"]["resources"]["gpuLimit"] = cell.resource_limits.gpu_limit
        if cell.resource_limits.gpu_request:
            manifest["spec"]["resources"]["gpuRequest"] = cell.resource_limits.gpu_request

        return yaml.dump(manifest, default_flow_style=False)

    def _generate_deployment(self, cell: Cell) -> str:
        """Generate Deployment manifest."""
        image_name = cell.full_image_name
        if self.registry and not cell.image:
            image_name = f"{self.registry}/{image_name}"

        container = {
            "name": cell.name,
            "image": image_name,
            "imagePullPolicy": self.image_pull_policy,
            "ports": [
                {"containerPort": port, "protocol": "TCP"}
                for port in cell.ports
            ],
            "resources": cell.resource_limits.to_k8s_spec(),
            "livenessProbe": cell.health_check.to_k8s_probe(),
            "readinessProbe": cell.health_check.to_k8s_probe(),
            "securityContext": {
                "runAsNonRoot": True,
                "readOnlyRootFilesystem": True,
                "allowPrivilegeEscalation": False,
                "capabilities": {
                    "drop": ["ALL"],
                },
            },
        }

        # Add environment variables
        if cell.env_vars:
            container["envFrom"] = [
                {"configMapRef": {"name": cell.k8s_configmap_name}}
            ]

        manifest = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": cell.k8s_deployment_name,
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
                "annotations": {
                    "colony.codingengine.io/cell-id": cell.id,
                    "colony.codingengine.io/version": cell.version,
                },
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": cell.name,
                        "app.kubernetes.io/instance": cell.id[:8],
                    },
                },
                "template": {
                    "metadata": {
                        "labels": self._standard_labels(cell),
                        "annotations": {
                            "colony.codingengine.io/cell-id": cell.id,
                        },
                    },
                    "spec": {
                        "containers": [container],
                        "restartPolicy": "Always",
                        "terminationGracePeriodSeconds": 30,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "seccompProfile": {
                                "type": "RuntimeDefault",
                            },
                        },
                    },
                },
            },
        }

        # Add service account if enabled
        if self.enable_service_accounts:
            manifest["spec"]["template"]["spec"]["serviceAccountName"] = f"cell-{cell.name}-sa"

        return yaml.dump(manifest, default_flow_style=False)

    def _generate_service(self, cell: Cell) -> str:
        """Generate Service manifest."""
        ports = [
            {
                "name": f"port-{port}",
                "port": port,
                "targetPort": port,
                "protocol": "TCP",
            }
            for port in cell.ports
        ]

        manifest = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": cell.k8s_service_name,
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {
                    "app.kubernetes.io/name": cell.name,
                    "app.kubernetes.io/instance": cell.id[:8],
                },
                "ports": ports,
            },
        }

        return yaml.dump(manifest, default_flow_style=False)

    def _generate_configmap(self, cell: Cell) -> str:
        """Generate ConfigMap manifest."""
        manifest = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": cell.k8s_configmap_name,
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
            },
            "data": cell.env_vars,
        }

        return yaml.dump(manifest, default_flow_style=False)

    def _generate_network_policy(self, cell: Cell) -> str:
        """Generate NetworkPolicy manifest with default-deny and explicit allows."""
        # Allow ingress from same namespace only
        ingress_rules = [
            {
                "from": [
                    {"namespaceSelector": {"matchLabels": {"name": cell.namespace}}}
                ],
                "ports": [
                    {"protocol": "TCP", "port": port}
                    for port in cell.ports
                ],
            }
        ]

        # Allow egress to DNS and dependent cells
        egress_rules = [
            # Allow DNS
            {
                "to": [{"namespaceSelector": {}}],
                "ports": [
                    {"protocol": "UDP", "port": 53},
                    {"protocol": "TCP", "port": 53},
                ],
            },
        ]

        # Add rules for dependencies
        for dep_id in cell.depends_on:
            egress_rules.append({
                "to": [
                    {
                        "podSelector": {
                            "matchLabels": {
                                "colony.codingengine.io/cell-id": dep_id[:8],
                            }
                        }
                    }
                ],
            })

        manifest = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"cell-{cell.name}-netpol",
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
            },
            "spec": {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": cell.name,
                        "app.kubernetes.io/instance": cell.id[:8],
                    },
                },
                "policyTypes": ["Ingress", "Egress"],
                "ingress": ingress_rules,
                "egress": egress_rules,
            },
        }

        return yaml.dump(manifest, default_flow_style=False)

    def _generate_service_account(self, cell: Cell) -> str:
        """Generate ServiceAccount with minimal permissions."""
        sa_name = f"cell-{cell.name}-sa"

        # ServiceAccount
        sa_manifest = {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": sa_name,
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
            },
            "automountServiceAccountToken": False,
        }

        # Role with minimal permissions
        role_manifest = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {
                "name": f"cell-{cell.name}-role",
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
            },
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["configmaps"],
                    "resourceNames": [cell.k8s_configmap_name],
                    "verbs": ["get"],
                },
            ],
        }

        # RoleBinding
        rolebinding_manifest = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": f"cell-{cell.name}-rolebinding",
                "namespace": cell.namespace,
                "labels": self._standard_labels(cell),
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": sa_name,
                    "namespace": cell.namespace,
                },
            ],
            "roleRef": {
                "kind": "Role",
                "name": f"cell-{cell.name}-role",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        }

        manifests = [
            yaml.dump(sa_manifest, default_flow_style=False),
            yaml.dump(role_manifest, default_flow_style=False),
            yaml.dump(rolebinding_manifest, default_flow_style=False),
        ]

        return "\n---\n".join(manifests)

    def _standard_labels(self, cell: Cell) -> Dict[str, str]:
        """Get standard labels for all cell resources."""
        return {
            "app.kubernetes.io/name": cell.name,
            "app.kubernetes.io/instance": cell.id[:8],
            "app.kubernetes.io/version": cell.version,
            "app.kubernetes.io/managed-by": "cell-colony",
            "colony.codingengine.io/cell-id": cell.id,
        }


# CRD definitions as Python dataclasses for type safety
@dataclass
class CellCRD:
    """Python representation of Cell CRD spec."""
    name: str
    source_type: str
    source_ref: str
    namespace: str = "default"
    working_dir: str = ""
    image: Optional[str] = None
    image_tag: str = "latest"

    def to_manifest(self) -> str:
        """Convert to YAML manifest."""
        manifest = {
            "apiVersion": "colony.codingengine.io/v1",
            "kind": "Cell",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "name": self.name,
                "sourceType": self.source_type,
                "sourceRef": self.source_ref,
            },
        }
        if self.working_dir:
            manifest["spec"]["workingDir"] = self.working_dir
        if self.image:
            manifest["spec"]["image"] = self.image
            manifest["spec"]["imageTag"] = self.image_tag

        return yaml.dump(manifest, default_flow_style=False)


@dataclass
class ColonyCRD:
    """Python representation of Colony CRD spec."""
    name: str
    namespace: str = "default"
    max_cells: int = 100
    min_healthy_cells: int = 1
    health_check_interval: int = 30
    rebalance_threshold: float = 0.8

    def to_manifest(self) -> str:
        """Convert to YAML manifest."""
        manifest = {
            "apiVersion": "colony.codingengine.io/v1",
            "kind": "Colony",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
            },
            "spec": {
                "maxCells": self.max_cells,
                "minHealthyCells": self.min_healthy_cells,
                "healthCheckIntervalSeconds": self.health_check_interval,
                "rebalanceThreshold": self.rebalance_threshold,
            },
        }

        return yaml.dump(manifest, default_flow_style=False)

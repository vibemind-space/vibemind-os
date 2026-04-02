"""
Microservice Orchestrator - Manages 8 separate Docker containers for microservices.

This tool provides:
1. Per-service Docker containers with isolated ports
2. Combined VNC dashboard showing all services
3. Redis event bus for inter-service communication
4. Kubernetes manifest generation for cloud deployment
5. Port allocation via PortManager

Usage:
    orchestrator = MicroserviceOrchestrator(output_dir="./output")
    await orchestrator.initialize_services(requirements)
    await orchestrator.start_all()
    # Combined VNC at http://localhost:6080/vnc.html
"""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import structlog

from ..infra.port_manager import get_port_manager, PortAllocation

logger = structlog.get_logger(__name__)


class ServiceState(str, Enum):
    """State of a microservice container."""
    STOPPED = "stopped"
    STARTING = "starting"
    BUILDING = "building"
    RUNNING = "running"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    ERROR = "error"


@dataclass
class MicroserviceConfig:
    """Configuration for a single microservice."""
    service_name: str
    display_name: str
    port_frontend: int
    port_backend: int
    k8s_nodeport: int
    depends_on: List[str] = field(default_factory=list)
    requirements: List[dict] = field(default_factory=list)
    state: ServiceState = ServiceState.STOPPED
    container_id: Optional[str] = None
    health_endpoint: str = "/health"

    @property
    def service_dir(self) -> str:
        return f"services/{self.service_name}"


@dataclass
class OrchestratorResult:
    """Result from orchestrator operations."""
    success: bool
    services: Dict[str, MicroserviceConfig] = field(default_factory=dict)
    vnc_dashboard_url: Optional[str] = None
    redis_url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "services": {k: v.service_name for k, v in self.services.items()},
            "vnc_dashboard_url": self.vnc_dashboard_url,
            "redis_url": self.redis_url,
            "error": self.error,
        }


# Domain to Service mapping (12 logical domains -> 8 actual services)
DOMAIN_TO_SERVICE_MAP = {
    "auth": "auth-service",
    "user": "user-service",
    "payment": "billing-service",
    "dashboard": "transport-service",
    "admin": "auth-service",        # Merged into auth
    "notifications": "user-service",  # Merged into user
    "search": "gateway-service",
    "reports": "pod-service",
    "settings": "user-service",     # Merged into user
    "api": "gateway-service",
    "storage": "pod-service",
    "other": "gateway-service",
}


class MicroserviceOrchestrator:
    """
    Orchestrates 8 separate Docker containers for microservices.

    Services:
    - auth-service: Authentication, authorization, RBAC
    - user-service: User profiles, settings, notifications
    - transport-service: Transport tracking, GPS, routes
    - pod-service: POD management, documents, reports
    - billing-service: Billing, invoicing, payments
    - orders-service: Order management, scheduling
    - partners-service: Partner/vendor management
    - gateway-service: API Gateway, integrations, search
    """

    # Service definitions with port allocations
    SERVICE_DEFINITIONS = {
        "auth-service": {
            "display_name": "Auth & RBAC",
            "port_frontend": 3100,
            "port_backend": 8100,
            "k8s_nodeport": 30100,
            "depends_on": [],
        },
        "user-service": {
            "display_name": "User Management",
            "port_frontend": 3101,
            "port_backend": 8101,
            "k8s_nodeport": 30101,
            "depends_on": ["auth-service"],
        },
        "transport-service": {
            "display_name": "Transport Tracking",
            "port_frontend": 3102,
            "port_backend": 8102,
            "k8s_nodeport": 30102,
            "depends_on": ["auth-service"],
        },
        "pod-service": {
            "display_name": "POD Management",
            "port_frontend": 3103,
            "port_backend": 8103,
            "k8s_nodeport": 30103,
            "depends_on": ["auth-service", "transport-service"],
        },
        "billing-service": {
            "display_name": "Billing & Invoicing",
            "port_frontend": 3104,
            "port_backend": 8104,
            "k8s_nodeport": 30104,
            "depends_on": ["auth-service", "orders-service"],
        },
        "orders-service": {
            "display_name": "Order Management",
            "port_frontend": 3105,
            "port_backend": 8105,
            "k8s_nodeport": 30105,
            "depends_on": ["auth-service", "partners-service"],
        },
        "partners-service": {
            "display_name": "Partner Management",
            "port_frontend": 3106,
            "port_backend": 8106,
            "k8s_nodeport": 30106,
            "depends_on": ["auth-service"],
        },
        "gateway-service": {
            "display_name": "API Gateway",
            "port_frontend": 3107,
            "port_backend": 8107,
            "k8s_nodeport": 30107,
            "depends_on": ["auth-service"],
        },
    }

    # Redis configuration
    REDIS_PORT = 6379
    REDIS_K8S_NODEPORT = 30379

    # VNC Dashboard
    VNC_DASHBOARD_PORT = 6080
    VNC_K8S_NODEPORT = 30080

    def __init__(
        self,
        output_dir: str,
        vnc_port: int = 6080,
        enable_redis: bool = True,
        network_name: str = "microservices-net",
    ):
        """
        Initialize the microservice orchestrator.

        Args:
            output_dir: Base output directory for generated code
            vnc_port: Port for combined VNC dashboard
            enable_redis: Whether to start Redis for event bus
            network_name: Docker network name for service communication
        """
        self.output_dir = Path(output_dir).resolve()
        self.vnc_port = vnc_port
        self.enable_redis = enable_redis
        self.network_name = network_name

        # Initialize services
        self.services: Dict[str, MicroserviceConfig] = {}
        for name, config in self.SERVICE_DEFINITIONS.items():
            self.services[name] = MicroserviceConfig(
                service_name=name,
                display_name=config["display_name"],
                port_frontend=config["port_frontend"],
                port_backend=config["port_backend"],
                k8s_nodeport=config["k8s_nodeport"],
                depends_on=config["depends_on"],
            )

        # Redis container
        self.redis_container_id: Optional[str] = None

        # Dashboard container
        self.dashboard_container_id: Optional[str] = None

        logger.info(
            "microservice_orchestrator_initialized",
            output_dir=str(self.output_dir),
            service_count=len(self.services),
            vnc_port=self.vnc_port,
        )

    async def create_service_directories(self) -> None:
        """Create output directories for each service."""
        services_dir = self.output_dir / "services"
        services_dir.mkdir(parents=True, exist_ok=True)

        for service_name in self.services:
            service_dir = services_dir / service_name
            (service_dir / "src").mkdir(parents=True, exist_ok=True)
            (service_dir / "tests").mkdir(parents=True, exist_ok=True)

            logger.debug(
                "service_directory_created",
                service=service_name,
                path=str(service_dir),
            )

        logger.info(
            "service_directories_created",
            count=len(self.services),
            path=str(services_dir),
        )

    def assign_requirements_to_services(
        self,
        requirements: List[dict],
    ) -> Dict[str, List[dict]]:
        """
        Assign requirements to their target microservices.

        Args:
            requirements: List of requirement dictionaries

        Returns:
            Dict mapping service_name to list of requirements
        """
        assignments: Dict[str, List[dict]] = {name: [] for name in self.services}

        for req in requirements:
            # Try to get service from requirement metadata
            service_hint = req.get("service", "").lower()

            # Map common German service names to our services
            service_mapping = {
                "abrechnung": "billing-service",
                "billing": "billing-service",
                "auftragsmanagement": "orders-service",
                "orders": "orders-service",
                "transport": "transport-service",
                "tracking": "transport-service",
                "pod": "pod-service",
                "liefernachweis": "pod-service",
                "partner": "partners-service",
                "geschftspartner": "partners-service",
                "benutzer": "user-service",
                "user": "user-service",
                "auth": "auth-service",
                "rollenverwaltung": "auth-service",
                "disposition": "transport-service",
                "api": "gateway-service",
                "gateway": "gateway-service",
                "integration": "gateway-service",
            }

            # Find matching service
            target_service = "gateway-service"  # Default
            for pattern, service in service_mapping.items():
                if pattern in service_hint:
                    target_service = service
                    break

            # Use domain keywords as fallback
            if target_service == "gateway-service":
                text = f"{req.get('title', '')} {req.get('text', '')}".lower()
                domain_keywords = {
                    "auth-service": ["login", "logout", "password", "token", "session", "role", "permission"],
                    "user-service": ["user", "profile", "settings", "notification", "avatar"],
                    "billing-service": ["invoice", "billing", "payment", "rechnung", "faktur"],
                    "orders-service": ["order", "auftrag", "booking", "buchung"],
                    "transport-service": ["transport", "route", "gps", "tracking", "disposition", "tour"],
                    "pod-service": ["pod", "document", "proof", "report", "export", "pdf"],
                    "partners-service": ["partner", "vendor", "supplier", "customer", "kunde"],
                }

                for service, keywords in domain_keywords.items():
                    if any(kw in text for kw in keywords):
                        target_service = service
                        break

            assignments[target_service].append(req)

        # Update service configs with requirements
        for service_name, reqs in assignments.items():
            self.services[service_name].requirements = reqs

        logger.info(
            "requirements_assigned",
            distribution={k: len(v) for k, v in assignments.items()},
            total=len(requirements),
        )

        return assignments

    async def generate_docker_compose(self) -> str:
        """Generate docker-compose.microservices.yml for all services."""
        compose = {
            "version": "3.9",
            "services": {},
            "networks": {
                self.network_name: {
                    "driver": "bridge",
                    "ipam": {
                        "config": [{"subnet": "172.30.0.0/16"}]
                    }
                }
            },
            "volumes": {
                "redis_data": {},
            }
        }

        # Add Redis service
        if self.enable_redis:
            compose["services"]["redis"] = {
                "image": "redis:7-alpine",
                "container_name": "logistics-redis",
                "ports": [f"{self.REDIS_PORT}:6379"],
                "volumes": ["redis_data:/data"],
                "networks": [self.network_name],
                "healthcheck": {
                    "test": ["CMD", "redis-cli", "ping"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 3,
                },
                "restart": "unless-stopped",
            }

        # Add microservices
        for name, config in self.services.items():
            service_def = {
                "build": {
                    "context": f"./services/{name}",
                    "dockerfile": "Dockerfile",
                },
                "container_name": f"logistics-{name}",
                "ports": [
                    f"{config.port_frontend}:3000",
                    f"{config.port_backend}:8000",
                ],
                "networks": [self.network_name],
                "environment": {
                    "SERVICE_NAME": name,
                    "REDIS_URL": "redis://redis:6379",
                    "NODE_ENV": "production",
                },
                "healthcheck": {
                    "test": ["CMD", "curl", "-f", f"http://localhost:8000{config.health_endpoint}"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                    "start_period": "40s",
                },
                "restart": "unless-stopped",
                "deploy": {
                    "resources": {
                        "limits": {"cpus": "1.0", "memory": "1G"},
                        "reservations": {"cpus": "0.25", "memory": "256M"},
                    }
                },
            }

            # Add dependencies
            if config.depends_on:
                service_def["depends_on"] = {}
                for dep in config.depends_on:
                    service_def["depends_on"][dep] = {"condition": "service_healthy"}
                # Always depend on Redis
                if self.enable_redis:
                    service_def["depends_on"]["redis"] = {"condition": "service_healthy"}
            elif self.enable_redis:
                service_def["depends_on"] = {"redis": {"condition": "service_healthy"}}

            compose["services"][name] = service_def

        # Write docker-compose file
        compose_path = self.output_dir / "docker-compose.microservices.yml"
        with open(compose_path, "w") as f:
            import yaml
            yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

        logger.info(
            "docker_compose_generated",
            path=str(compose_path),
            services=len(compose["services"]),
        )

        return str(compose_path)

    async def generate_kubernetes_manifests(self) -> str:
        """Generate Kubernetes manifests for cloud deployment."""
        k8s_dir = self.output_dir / "k8s"
        k8s_dir.mkdir(parents=True, exist_ok=True)

        # Namespace
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "logistics-platform"}
        }
        self._write_yaml(k8s_dir / "namespace.yaml", namespace)

        # ConfigMap
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "logistics-config",
                "namespace": "logistics-platform",
            },
            "data": {
                "REDIS_URL": "redis://redis:6379",
                "NODE_ENV": "production",
            }
        }
        self._write_yaml(k8s_dir / "configmap.yaml", configmap)

        # Redis StatefulSet
        redis_manifests = self._generate_redis_k8s()
        self._write_yaml(k8s_dir / "redis.yaml", redis_manifests)

        # Service manifests
        services_dir = k8s_dir / "services"
        services_dir.mkdir(exist_ok=True)

        for name, config in self.services.items():
            manifests = self._generate_service_k8s(name, config)
            self._write_yaml(services_dir / f"{name}.yaml", manifests)

        # Ingress
        ingress = self._generate_ingress_k8s()
        self._write_yaml(k8s_dir / "ingress.yaml", ingress)

        # Kustomization
        kustomization = {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": "logistics-platform",
            "resources": [
                "namespace.yaml",
                "configmap.yaml",
                "redis.yaml",
                "ingress.yaml",
            ] + [f"services/{name}.yaml" for name in self.services],
        }
        self._write_yaml(k8s_dir / "kustomization.yaml", kustomization)

        logger.info(
            "kubernetes_manifests_generated",
            path=str(k8s_dir),
            services=len(self.services),
        )

        return str(k8s_dir)

    def _generate_service_k8s(self, name: str, config: MicroserviceConfig) -> List[dict]:
        """Generate K8s Deployment, Service, and HPA for a microservice."""
        return [
            # Deployment
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": name,
                    "namespace": "logistics-platform",
                    "labels": {"app": name},
                },
                "spec": {
                    "replicas": 2,
                    "selector": {"matchLabels": {"app": name}},
                    "template": {
                        "metadata": {"labels": {"app": name}},
                        "spec": {
                            "containers": [{
                                "name": name,
                                "image": f"logistics/{name}:latest",
                                "ports": [
                                    {"containerPort": 3000, "name": "frontend"},
                                    {"containerPort": 8000, "name": "backend"},
                                ],
                                "envFrom": [{"configMapRef": {"name": "logistics-config"}}],
                                "resources": {
                                    "limits": {"cpu": "1000m", "memory": "1Gi"},
                                    "requests": {"cpu": "250m", "memory": "256Mi"},
                                },
                                "livenessProbe": {
                                    "httpGet": {"path": config.health_endpoint, "port": 8000},
                                    "initialDelaySeconds": 30,
                                    "periodSeconds": 10,
                                },
                                "readinessProbe": {
                                    "httpGet": {"path": config.health_endpoint, "port": 8000},
                                    "initialDelaySeconds": 5,
                                    "periodSeconds": 5,
                                },
                            }],
                        },
                    },
                },
            },
            # Service
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": name,
                    "namespace": "logistics-platform",
                },
                "spec": {
                    "type": "NodePort",
                    "selector": {"app": name},
                    "ports": [
                        {"name": "frontend", "port": 3000, "targetPort": 3000, "nodePort": config.k8s_nodeport},
                        {"name": "backend", "port": 8000, "targetPort": 8000, "nodePort": config.k8s_nodeport + 100},
                    ],
                },
            },
            # HPA
            {
                "apiVersion": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "metadata": {
                    "name": f"{name}-hpa",
                    "namespace": "logistics-platform",
                },
                "spec": {
                    "scaleTargetRef": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "name": name,
                    },
                    "minReplicas": 2,
                    "maxReplicas": 10,
                    "metrics": [{
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {"type": "Utilization", "averageUtilization": 70},
                        },
                    }],
                },
            },
        ]

    def _generate_redis_k8s(self) -> List[dict]:
        """Generate Redis StatefulSet and Service."""
        return [
            {
                "apiVersion": "apps/v1",
                "kind": "StatefulSet",
                "metadata": {
                    "name": "redis",
                    "namespace": "logistics-platform",
                },
                "spec": {
                    "serviceName": "redis",
                    "replicas": 1,
                    "selector": {"matchLabels": {"app": "redis"}},
                    "template": {
                        "metadata": {"labels": {"app": "redis"}},
                        "spec": {
                            "containers": [{
                                "name": "redis",
                                "image": "redis:7-alpine",
                                "ports": [{"containerPort": 6379}],
                                "resources": {
                                    "limits": {"cpu": "500m", "memory": "512Mi"},
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                },
                                "volumeMounts": [{
                                    "name": "redis-data",
                                    "mountPath": "/data",
                                }],
                            }],
                        },
                    },
                    "volumeClaimTemplates": [{
                        "metadata": {"name": "redis-data"},
                        "spec": {
                            "accessModes": ["ReadWriteOnce"],
                            "resources": {"requests": {"storage": "1Gi"}},
                        },
                    }],
                },
            },
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "redis",
                    "namespace": "logistics-platform",
                },
                "spec": {
                    "type": "ClusterIP",
                    "selector": {"app": "redis"},
                    "ports": [{"port": 6379, "targetPort": 6379}],
                },
            },
        ]

    def _generate_ingress_k8s(self) -> dict:
        """Generate NGINX Ingress for API Gateway."""
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": "logistics-ingress",
                "namespace": "logistics-platform",
                "annotations": {
                    "nginx.ingress.kubernetes.io/rewrite-target": "/",
                    "nginx.ingress.kubernetes.io/ssl-redirect": "true",
                },
            },
            "spec": {
                "ingressClassName": "nginx",
                "rules": [{
                    "host": "api.logistics.local",
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": "gateway-service",
                                    "port": {"number": 8000},
                                },
                            },
                        }],
                    },
                }],
            },
        }

    def _write_yaml(self, path: Path, data: Any) -> None:
        """Write data as YAML to a file."""
        import yaml
        with open(path, "w") as f:
            if isinstance(data, list):
                yaml.dump_all(data, f, default_flow_style=False, sort_keys=False)
            else:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    async def generate_service_dockerfiles(self) -> None:
        """Generate Dockerfile for each service."""
        for name in self.services:
            service_dir = self.output_dir / "services" / name
            dockerfile_path = service_dir / "Dockerfile"

            dockerfile_content = f"""# Auto-generated Dockerfile for {name}
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:20-alpine AS runner
WORKDIR /app

# Copy dependencies
COPY --from=builder /app/node_modules ./node_modules
COPY . .

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

# Expose ports
EXPOSE 3000 8000

# Start command
CMD ["npm", "start"]
"""

            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)

            logger.debug("dockerfile_generated", service=name, path=str(dockerfile_path))

        logger.info("dockerfiles_generated", count=len(self.services))

    def get_service_for_requirement(self, requirement: dict) -> str:
        """Get the target service name for a requirement."""
        service_hint = requirement.get("service", "").lower()

        # Direct service mapping
        for name in self.services:
            if name in service_hint or name.replace("-service", "") in service_hint:
                return name

        # Domain-based mapping
        text = f"{requirement.get('title', '')} {requirement.get('text', '')}".lower()

        for domain, service in DOMAIN_TO_SERVICE_MAP.items():
            if domain in text:
                return service

        return "gateway-service"  # Default fallback

    def get_output_path_for_requirement(self, requirement: dict) -> Path:
        """Get the output directory path for a requirement."""
        service = self.get_service_for_requirement(requirement)
        return self.output_dir / "services" / service / "src"

    async def cleanup(self) -> None:
        """Clean up all containers and networks."""
        # Implementation would stop all service containers
        logger.info("orchestrator_cleanup_complete")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of all services."""
        return {
            "services": {
                name: {
                    "state": config.state.value,
                    "requirements_count": len(config.requirements),
                    "ports": {
                        "frontend": config.port_frontend,
                        "backend": config.port_backend,
                    },
                }
                for name, config in self.services.items()
            },
            "redis_enabled": self.enable_redis,
            "vnc_port": self.vnc_port,
        }


# Factory function
def create_microservice_orchestrator(
    output_dir: str,
    vnc_port: int = 6080,
    enable_redis: bool = True,
) -> MicroserviceOrchestrator:
    """Create a new MicroserviceOrchestrator instance."""
    return MicroserviceOrchestrator(
        output_dir=output_dir,
        vnc_port=vnc_port,
        enable_redis=enable_redis,
    )

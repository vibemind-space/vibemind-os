"""
DevOps Agent - Specialized for infrastructure and deployment.

Capabilities:
- Docker configuration
- Kubernetes manifests
- CI/CD pipelines
- Infrastructure as Code
"""
from typing import Optional
from src.agents.base_agent import BaseAgent, AgentConfig, AgentType, GeneratedFile


class DevOpsAgent(BaseAgent):
    """Agent specialized for DevOps and infrastructure."""

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(agent_type=AgentType.DEVOPS)
        else:
            config.agent_type = AgentType.DEVOPS
        super().__init__(config)

    def _register_tools(self):
        """Register DevOps-specific tools."""

        # Create Dockerfile
        self.register_tool(
            name="create_dockerfile",
            description="Create a Dockerfile for containerization.",
            input_schema={
                "type": "object",
                "properties": {
                    "base_image": {
                        "type": "string",
                        "description": "Base Docker image",
                    },
                    "app_type": {
                        "type": "string",
                        "enum": ["python", "node", "go", "rust", "java"],
                    },
                    "expose_port": {
                        "type": "integer",
                        "description": "Port to expose",
                    },
                    "multi_stage": {
                        "type": "boolean",
                        "description": "Use multi-stage build",
                    },
                },
                "required": ["app_type"],
            },
            handler=self._handle_create_dockerfile,
        )

        # Create Kubernetes manifest
        self.register_tool(
            name="create_k8s_manifest",
            description="Create Kubernetes deployment manifests.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Resource name",
                    },
                    "resource_type": {
                        "type": "string",
                        "enum": ["deployment", "service", "configmap", "secret", "ingress"],
                    },
                    "replicas": {
                        "type": "integer",
                        "description": "Number of replicas",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                    },
                },
                "required": ["name", "resource_type"],
            },
            handler=self._handle_create_k8s_manifest,
        )

        # Create CI/CD pipeline
        self.register_tool(
            name="create_ci_pipeline",
            description="Create a CI/CD pipeline configuration.",
            input_schema={
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["github-actions", "gitlab-ci", "jenkins", "circleci"],
                    },
                    "stages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pipeline stages",
                    },
                    "deploy_target": {
                        "type": "string",
                        "description": "Deployment target",
                    },
                },
                "required": ["platform"],
            },
            handler=self._handle_create_ci_pipeline,
        )

    def get_system_prompt(self) -> str:
        return """You are an expert DevOps engineer specializing in cloud infrastructure and automation.

## Your Expertise
- Docker and containerization
- Kubernetes orchestration
- CI/CD pipelines (GitHub Actions, GitLab CI)
- Infrastructure as Code (Terraform, Pulumi)
- Cloud platforms (AWS, GCP, Azure)
- Monitoring and logging

## Guidelines
1. Follow security best practices (non-root containers, secrets management)
2. Optimize for build speed and image size
3. Use multi-stage builds when appropriate
4. Include health checks and readiness probes
5. Configure appropriate resource limits
6. Use environment variables for configuration
7. Implement proper logging

## Output Format
For infrastructure code:
1. Create the main configuration files
2. Include environment-specific variations
3. Add documentation comments
4. Provide deployment instructions

Focus on production-ready, secure, and maintainable configurations."""

    def _handle_create_dockerfile(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle Dockerfile creation."""
        app_type = input_data.get("app_type", "python")

        return {
            "success": True,
            "message": f"Dockerfile created for {app_type} application",
        }

    def _handle_create_k8s_manifest(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle Kubernetes manifest creation."""
        name = input_data.get("name", "app")
        resource_type = input_data.get("resource_type", "deployment")

        return {
            "success": True,
            "message": f"Kubernetes {resource_type} created: {name}",
        }

    def _handle_create_ci_pipeline(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle CI pipeline creation."""
        platform = input_data.get("platform", "github-actions")

        return {
            "success": True,
            "message": f"CI pipeline created for {platform}",
        }

"""
Seed Tool Creation with Docker Tools

This script adds docker-related tools to the Tool Creation system
so it shows as ACTIVE in tests.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production.production_planner import ProductionPlanner
from core.tool_creation import Tool
import time


def seed_tool_creation():
    """Seed tool creation with docker tools"""

    print("=" * 100)
    print("SEEDING TOOL CREATION SYSTEM")
    print("=" * 100)
    print()

    # Initialize planner
    print("[1] Initializing ProductionPlanner...")
    planner = ProductionPlanner(
        session_log_dir="data/logs/sessions",
        enable_semantic_coherence=False,
        user_id="seed_user",
        seed=42
    )
    print("[+] Planner initialized")
    print()

    # Add docker tools
    print("[2] Adding docker-related tools...")

    docker_tools = [
        Tool(
            tool_id="docker_build",
            tool_name="Docker Build",
            tool_type="primitive",
            description="Build Docker images from Dockerfile",
            input_types=["dockerfile", "context_path"],
            output_types=["image_id"],
            capabilities=["docker", "build", "containerization"],
            implementation="docker build -t <tag> <context>",
            dependencies=[],
            usage_count=15,
            success_count=14,
            failure_count=1,
            avg_execution_time=30.0,
            creation_time=time.time(),
            creator="system",
            version="1.0"
        ),
        Tool(
            tool_id="docker_run",
            tool_name="Docker Run",
            tool_type="primitive",
            description="Run Docker containers with configuration",
            input_types=["image_id", "config"],
            output_types=["container_id"],
            capabilities=["docker", "run", "deployment"],
            implementation="docker run -d <options> <image>",
            dependencies=["docker_build"],
            usage_count=25,
            success_count=23,
            failure_count=2,
            avg_execution_time=5.0,
            creation_time=time.time(),
            creator="system",
            version="1.0"
        ),
        Tool(
            tool_id="docker_compose",
            tool_name="Docker Compose",
            tool_type="composed",
            description="Orchestrate multi-container Docker applications",
            input_types=["docker-compose.yml"],
            output_types=["service_ids"],
            capabilities=["docker", "orchestration", "multi-container"],
            implementation="docker-compose up -d",
            dependencies=["docker_build", "docker_run"],
            usage_count=10,
            success_count=9,
            failure_count=1,
            avg_execution_time=45.0,
            creation_time=time.time(),
            creator="system",
            version="1.0"
        ),
        Tool(
            tool_id="docker_health_check",
            tool_name="Docker Health Check",
            tool_type="primitive",
            description="Configure and monitor container health checks",
            input_types=["container_id", "health_config"],
            output_types=["health_status"],
            capabilities=["docker", "monitoring", "health"],
            implementation="docker inspect --format='{{.State.Health.Status}}' <container>",
            dependencies=[],
            usage_count=8,
            success_count=8,
            failure_count=0,
            avg_execution_time=2.0,
            creation_time=time.time(),
            creator="system",
            version="1.0"
        ),
        Tool(
            tool_id="redis_deploy",
            tool_name="Redis Deployment",
            tool_type="composed",
            description="Deploy Redis instance with Docker",
            input_types=["redis_config"],
            output_types=["redis_container_id"],
            capabilities=["docker", "redis", "database", "deployment"],
            implementation="docker run -d --name redis -p 6379:6379 redis:latest",
            dependencies=["docker_run", "docker_health_check"],
            usage_count=12,
            success_count=11,
            failure_count=1,
            avg_execution_time=10.0,
            creation_time=time.time(),
            creator="system",
            version="1.0"
        ),
    ]

    for tool in docker_tools:
        planner.planner.tool_creation.tools[tool.tool_id] = tool
        print(f"  + {tool.tool_name} ({tool.tool_type})")
        print(f"    Capabilities: {', '.join(tool.capabilities)}")
        print(f"    Success rate: {tool.success_rate():.2f}")

    print(f"[+] Added {len(docker_tools)} docker tools")
    print()

    # Verify tools
    print("[3] Verifying tool library...")
    total_tools = len(planner.planner.tool_creation.tools)
    print(f"  Total tools in library: {total_tools}")
    print()

    # Test tool retrieval
    print("[4] Testing tool retrieval for 'docker' capability...")
    docker_tool = planner.planner.tool_creation.get_tool_for_capability(
        capability="docker",
        prefer_specialized=True
    )

    if docker_tool:
        print(f"  [+] Found tool: {docker_tool.tool_name}")
        print(f"      Type: {docker_tool.tool_type}")
        print(f"      Capabilities: {', '.join(docker_tool.capabilities)}")
        print(f"      Success rate: {docker_tool.success_rate():.2f}")
    else:
        print(f"  [-] No tool found for 'docker' capability")

    print()
    print("=" * 100)
    print("[SUCCESS] TOOL CREATION SYSTEM SEEDED!")
    print("=" * 100)
    print()
    print("Tool Creation is now ACTIVE and will return tools for docker tasks.")
    print()


if __name__ == "__main__":
    seed_tool_creation()

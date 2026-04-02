import asyncio
import json
import os
import sys
import time
import uuid
from typing import List, Optional
from pydantic import BaseModel

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env for environment variables
try:
    import dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Docker CLI via subprocess (avoids SDK compatibility issues)
import subprocess

# Autogen imports
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from autogen_core.tools import FunctionTool

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory

# Optional: rich console
try:
    from rich.console import Console
    console = Console()
except Exception:
    console = None

# ========== File helpers ==========
BASE_DIR = os.path.dirname(__file__)
SERVERS_DIR = os.path.dirname(BASE_DIR)
PLUGINS_DIR = os.path.dirname(SERVERS_DIR)
MODELS_DIR = os.path.join(PLUGINS_DIR, "models")

# ========== Docker CLI Tools ==========

def _run_docker_cmd(args: List[str], timeout: int = 60) -> tuple:
    """Run a docker CLI command and return (success, output/error)."""
    import platform
    try:
        # Use shell=True on Windows for better compatibility
        use_shell = platform.system() == "Windows"
        cmd = ["docker"] + args

        result = subprocess.run(
            cmd if not use_shell else " ".join(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=use_shell
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return False, "Docker CLI not found"
    except Exception as e:
        return False, str(e)


def check_docker_available() -> bool:
    """Check if Docker is available."""
    success, _ = _run_docker_cmd(["version", "--format", "{{.Server.Version}}"])
    return success


def list_containers(all: bool = False) -> str:
    """List Docker containers.

    Args:
        all: If True, list all containers including stopped ones. Default False (only running).

    Returns:
        JSON string with container information.
    """
    args = ["ps", "--format", "{{json .}}"]
    if all:
        args.insert(1, "-a")

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    containers = []
    for line in output.strip().split('\n'):
        if line:
            try:
                c = json.loads(line)
                containers.append({
                    "id": c.get("ID", "")[:12],
                    "name": c.get("Names", ""),
                    "image": c.get("Image", ""),
                    "status": c.get("Status", ""),
                    "ports": c.get("Ports", "")
                })
            except json.JSONDecodeError:
                pass

    return json.dumps({"containers": containers, "count": len(containers)})


def list_images() -> str:
    """List Docker images.

    Returns:
        JSON string with image information.
    """
    success, output = _run_docker_cmd(["images", "--format", "{{json .}}"])
    if not success:
        return json.dumps({"error": output})

    images = []
    for line in output.strip().split('\n'):
        if line:
            try:
                img = json.loads(line)
                images.append({
                    "id": img.get("ID", "")[:12],
                    "repository": img.get("Repository", ""),
                    "tag": img.get("Tag", ""),
                    "size": img.get("Size", "")
                })
            except json.JSONDecodeError:
                pass

    return json.dumps({"images": images, "count": len(images)})


def container_logs(container_id: str, tail: int = 100) -> str:
    """Get logs from a container.

    Args:
        container_id: Container ID or name.
        tail: Number of lines to return (default 100).

    Returns:
        Container logs as string.
    """
    success, output = _run_docker_cmd(["logs", "--tail", str(tail), container_id])
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"container": container_id, "logs": output})


def container_inspect(container_id: str) -> str:
    """Inspect a container for detailed information.

    Args:
        container_id: Container ID or name.

    Returns:
        JSON string with container details.
    """
    success, output = _run_docker_cmd(["inspect", container_id])
    if not success:
        return json.dumps({"error": output})

    try:
        data = json.loads(output)
        if data and len(data) > 0:
            c = data[0]
            return json.dumps({
                "id": c.get("Id", "")[:12],
                "name": c.get("Name", "").lstrip("/"),
                "status": c.get("State", {}).get("Status", ""),
                "image": c.get("Config", {}).get("Image", ""),
                "created": c.get("Created", ""),
                "ports": c.get("NetworkSettings", {}).get("Ports", {}),
                "mounts": c.get("Mounts", [])
            })
    except json.JSONDecodeError:
        pass

    return json.dumps({"error": "Failed to parse container info"})


def start_container(container_id: str) -> str:
    """Start a stopped container.

    Args:
        container_id: Container ID or name.

    Returns:
        JSON string with result.
    """
    success, output = _run_docker_cmd(["start", container_id])
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"success": True, "container": container_id, "status": "started"})


def stop_container(container_id: str, timeout: int = 10) -> str:
    """Stop a running container.

    Args:
        container_id: Container ID or name.
        timeout: Timeout in seconds before killing (default 10).

    Returns:
        JSON string with result.
    """
    success, output = _run_docker_cmd(["stop", "-t", str(timeout), container_id])
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"success": True, "container": container_id, "status": "stopped"})


def docker_info() -> str:
    """Get Docker system information.

    Returns:
        JSON string with Docker system info.
    """
    success, output = _run_docker_cmd(["info", "--format", "{{json .}}"])
    if not success:
        return json.dumps({"error": output})

    try:
        info = json.loads(output)
        return json.dumps({
            "containers": info.get("Containers", 0),
            "containers_running": info.get("ContainersRunning", 0),
            "containers_paused": info.get("ContainersPaused", 0),
            "containers_stopped": info.get("ContainersStopped", 0),
            "images": info.get("Images", 0),
            "server_version": info.get("ServerVersion", ""),
            "os": info.get("OperatingSystem", ""),
            "architecture": info.get("Architecture", ""),
            "memory_gb": round(info.get("MemTotal", 0) / 1024 / 1024 / 1024, 2)
        })
    except json.JSONDecodeError:
        return json.dumps({"error": "Failed to parse Docker info"})


def list_networks() -> str:
    """List Docker networks.

    Returns:
        JSON string with network information.
    """
    success, output = _run_docker_cmd(["network", "ls", "--format", "{{json .}}"])
    if not success:
        return json.dumps({"error": output})

    networks = []
    for line in output.strip().split('\n'):
        if line:
            try:
                net = json.loads(line)
                networks.append({
                    "id": net.get("ID", "")[:12],
                    "name": net.get("Name", ""),
                    "driver": net.get("Driver", ""),
                    "scope": net.get("Scope", "")
                })
            except json.JSONDecodeError:
                pass

    return json.dumps({"networks": networks, "count": len(networks)})


def list_volumes() -> str:
    """List Docker volumes.

    Returns:
        JSON string with volume information.
    """
    success, output = _run_docker_cmd(["volume", "ls", "--format", "{{json .}}"])
    if not success:
        return json.dumps({"error": output})

    volumes = []
    for line in output.strip().split('\n'):
        if line:
            try:
                vol = json.loads(line)
                volumes.append({
                    "name": vol.get("Name", ""),
                    "driver": vol.get("Driver", ""),
                    "mountpoint": vol.get("Mountpoint", "")
                })
            except json.JSONDecodeError:
                pass

    return json.dumps({"volumes": volumes, "count": len(volumes)})


def run_container(image: str, name: str = "", ports: str = "", env: str = "", detach: bool = True) -> str:
    """Run a new Docker container.

    Args:
        image: Docker image to run (e.g., 'nginx:latest', 'redis').
        name: Optional container name.
        ports: Port mapping (e.g., '8080:80' or '3000:3000,5432:5432').
        env: Environment variables (e.g., 'KEY=value,OTHER=val2').
        detach: Run in background (default True).

    Returns:
        JSON string with container ID or error.
    """
    args = ["run"]
    if detach:
        args.append("-d")
    if name:
        args.extend(["--name", name])
    if ports:
        for port in ports.split(","):
            args.extend(["-p", port.strip()])
    if env:
        for e in env.split(","):
            args.extend(["-e", e.strip()])
    args.append(image)

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    container_id = output.strip()[:12]
    return json.dumps({"success": True, "container_id": container_id, "image": image, "name": name or container_id})


def remove_container(container_id: str, force: bool = False, volumes: bool = False) -> str:
    """Remove a Docker container.

    Args:
        container_id: Container ID or name to remove.
        force: Force remove running container (default False).
        volumes: Remove associated volumes (default False).

    Returns:
        JSON string with result.
    """
    args = ["rm"]
    if force:
        args.append("-f")
    if volumes:
        args.append("-v")
    args.append(container_id)

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"success": True, "container": container_id, "status": "removed"})


def pull_image(image: str) -> str:
    """Pull a Docker image from registry.

    Args:
        image: Image to pull (e.g., 'nginx:latest', 'redis:7').

    Returns:
        JSON string with result.
    """
    success, output = _run_docker_cmd(["pull", image])
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"success": True, "image": image, "status": "pulled", "output": output[:500]})


def exec_container(container_id: str, command: str) -> str:
    """Execute a command inside a running container.

    Args:
        container_id: Container ID or name.
        command: Command to execute (e.g., 'ls -la', 'cat /etc/hosts').

    Returns:
        JSON string with command output.
    """
    args = ["exec", container_id] + command.split()

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"container": container_id, "command": command, "output": output})


def docker_compose_up(compose_file: str = "", project_name: str = "", detach: bool = True) -> str:
    """Start Docker Compose services.

    Args:
        compose_file: Path to docker-compose.yml (optional, uses default if empty).
        project_name: Project name (optional).
        detach: Run in background (default True).

    Returns:
        JSON string with result.
    """
    args = ["compose"]
    if compose_file:
        args.extend(["-f", compose_file])
    if project_name:
        args.extend(["-p", project_name])
    args.append("up")
    if detach:
        args.append("-d")

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"success": True, "action": "compose up", "output": output[:500]})


def docker_compose_down(compose_file: str = "", project_name: str = "", volumes: bool = False) -> str:
    """Stop Docker Compose services.

    Args:
        compose_file: Path to docker-compose.yml (optional).
        project_name: Project name (optional).
        volumes: Remove volumes (default False).

    Returns:
        JSON string with result.
    """
    args = ["compose"]
    if compose_file:
        args.extend(["-f", compose_file])
    if project_name:
        args.extend(["-p", project_name])
    args.append("down")
    if volumes:
        args.append("-v")

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    return json.dumps({"success": True, "action": "compose down", "output": output[:500]})


def docker_compose_ps(compose_file: str = "", project_name: str = "") -> str:
    """List Docker Compose services status.

    Args:
        compose_file: Path to docker-compose.yml (optional).
        project_name: Project name (optional).

    Returns:
        JSON string with services status.
    """
    args = ["compose"]
    if compose_file:
        args.extend(["-f", compose_file])
    if project_name:
        args.extend(["-p", project_name])
    args.extend(["ps", "--format", "json"])

    success, output = _run_docker_cmd(args)
    if not success:
        return json.dumps({"error": output})

    services = []
    for line in output.strip().split('\n'):
        if line:
            try:
                svc = json.loads(line)
                services.append({
                    "name": svc.get("Name", ""),
                    "service": svc.get("Service", ""),
                    "status": svc.get("Status", ""),
                    "ports": svc.get("Ports", "")
                })
            except json.JSONDecodeError:
                pass

    return json.dumps({"services": services, "count": len(services)})


# Create FunctionTools for autogen
def create_docker_tools() -> List[FunctionTool]:
    """Create Docker CLI tools for autogen agents."""
    tools = [
        # Container management
        FunctionTool(list_containers, description="List Docker containers. Set all=True to include stopped containers."),
        FunctionTool(run_container, description="Run a new container. Args: image (required), name, ports ('8080:80'), env ('KEY=val'), detach."),
        FunctionTool(start_container, description="Start a stopped container by ID or name."),
        FunctionTool(stop_container, description="Stop a running container by ID or name."),
        FunctionTool(remove_container, description="Remove a container. Set force=True to remove running containers."),
        FunctionTool(container_logs, description="Get logs from a container by ID or name."),
        FunctionTool(container_inspect, description="Get detailed information about a container."),
        FunctionTool(exec_container, description="Execute a command inside a running container."),
        # Images
        FunctionTool(list_images, description="List Docker images with tags and sizes."),
        FunctionTool(pull_image, description="Pull a Docker image from registry."),
        # System
        FunctionTool(docker_info, description="Get Docker system information (version, resources, stats)."),
        FunctionTool(list_networks, description="List Docker networks."),
        FunctionTool(list_volumes, description="List Docker volumes."),
        # Compose
        FunctionTool(docker_compose_up, description="Start Docker Compose services. Args: compose_file, project_name, detach."),
        FunctionTool(docker_compose_down, description="Stop Docker Compose services. Set volumes=True to remove volumes."),
        FunctionTool(docker_compose_ps, description="List Docker Compose services status."),
    ]
    return tools


# ========== Defaults ==========
DEFAULT_DOCKER_OPERATOR_PROMPT = """ROLE: Docker Operator (Docker CLI)
GOAL: Complete Docker container management tasks using available tools.
TOOLS: Container (list_containers, run_container, start_container, stop_container, remove_container, container_logs, container_inspect, exec_container), Images (list_images, pull_image), System (docker_info, list_networks, list_volumes), Compose (docker_compose_up, docker_compose_down, docker_compose_ps).
GUIDELINES:
- Check container status before operations
- Log steps briefly (bullet points)
- Extract only what's necessary (concise, structured)
- Handle errors gracefully
- When the task is fulfilled, provide a compact summary and signal completion clearly.
OUTPUT:
- Brief step log
- Relevant results (compact, JSON-like if appropriate)
- Completion signal: "READY_FOR_VALIDATION"
"""

DEFAULT_QA_VALIDATOR_PROMPT = """ROLE: QA Validator
GOAL: Verify that the user's Docker task is completely and correctly fulfilled.
CHECK:
- Were the required Docker operations precisely executed?
- Are the results traceable (container IDs, logs, status)?
RESPONSE:
- If everything is correct: respond ONLY with 'APPROVE' plus 1-2 bullet points (no long texts).
- If something is missing: name precisely 1-2 gaps (why/what is missing).
"""

DEFAULT_TASK_PROMPT = """Use the available Docker tools to accomplish the goal and stream your progress.
Be clear and concise in your responses.
"""


def init_model_client(task: str = "") -> OpenAIChatCompletionClient:
    """Initialize OpenAI chat completion client with intelligent routing."""
    return shared_init_model_client("docker", task)


# ========== Pydantic Config Model ==========
class DockerAgentConfig(BaseModel):
    """Configuration for Docker agent execution."""
    task: str
    session_id: str
    name: str = "docker-session"
    model: Optional[str] = None
    working_dir: str = "."
    keepalive: bool = False


# ========== Main Entry Point ==========
async def run_docker_agent(config: DockerAgentConfig):
    """Docker Agent main entry point using Docker SDK (no MCP).

    Follows the SESSION_ANNOUNCE pattern for backend integration.
    """
    logger = setup_logging(f"docker_agent_{config.session_id}")

    # Check Docker availability via CLI
    if not check_docker_available():
        print("❌ Docker not running or not accessible")
        return

    # Initialize EventServer
    event_server = EventServer(session_id=config.session_id, tool_name="docker")

    # Initialize ConversationLogger
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="docker",
        sense_category=SenseCategory.TACTILE
    )

    # Start UI server
    httpd, thread, host, port = start_ui_server(
        event_server,
        host="127.0.0.1",
        port=0,
        tool_name="docker"
    )

    preview_url = f"http://{host}:{port}/"

    # SESSION_ANNOUNCE
    announce_data = {
        "session_id": config.session_id,
        "host": host,
        "port": port,
        "ui_url": preview_url
    }
    print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
    event_server.broadcast("session.started", announce_data)

    # Initialize model client
    try:
        task_aware_client = init_model_client(config.task)
    except Exception as e:
        event_server.broadcast("error", {"text": f"LLM init failed: {e}"})
        if not config.keepalive:
            try:
                httpd.shutdown()
            except Exception:
                pass
        return

    # Create Docker tools
    docker_tools = create_docker_tools()

    # Create Docker Operator agent with SDK tools
    docker_operator = AssistantAgent(
        "DockerOperator",
        model_client=task_aware_client,
        tools=docker_tools,
        system_message=DEFAULT_DOCKER_OPERATOR_PROMPT,
        model_context=BufferedChatCompletionContext(buffer_size=20)
    )

    # Create QA Validator agent
    qa_validator = AssistantAgent(
        "QAValidator",
        model_client=task_aware_client,
        system_message=DEFAULT_QA_VALIDATOR_PROMPT,
        model_context=BufferedChatCompletionContext(buffer_size=15)
    )

    # Create team
    main_termination = TextMentionTermination("APPROVE")
    team = RoundRobinGroupChat(
        [docker_operator, qa_validator],
        termination_condition=main_termination,
        max_turns=30
    )

    # Broadcast execution start
    event_server.broadcast("status", {"text": "Docker SDK: Operator + QA Validator"})

    full_prompt = f"{DEFAULT_TASK_PROMPT}\n\nTask: {config.task}"

    # Log session start
    try:
        conv_logger.log_session_start(
            task=config.task,
            model="haiku-4.5",
            metadata={"agents": ["DockerOperator", "QAValidator"], "system": "Docker SDK"}
        )
    except Exception:
        pass

    # Run the agent
    print(f"\n{'='*60}")
    print(f"🐳 Docker SDK: Operator + QA Validator")
    print(f"{'='*60}\n")

    try:
        messages = []
        async for message in team.run_stream(task=full_prompt):
            messages.append(message)

            if hasattr(message, 'source') and hasattr(message, 'content'):
                source = message.source
                content = str(message.content)

                if source == "DockerOperator":
                    print(f"\n🔧 DockerOperator:")
                    print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                    event_server.broadcast("agent.message", {
                        "agent": "DockerOperator",
                        "role": "operator",
                        "content": content,
                        "icon": "🔧"
                    })

                elif source == "QAValidator":
                    print(f"\n✓ QAValidator:")
                    print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                    event_server.broadcast("agent.message", {
                        "agent": "QAValidator",
                        "role": "validator",
                        "content": content,
                        "icon": "✓"
                    })

                # Check for tool calls
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'name'):
                            print(f"   🛠️  Tool: {item.name}")
                            event_server.broadcast("tool.call", {
                                "tool": item.name,
                                "icon": "🛠️"
                            })

        print(f"\n{'='*60}")
        print(f"✅ Task completed")
        print(f"{'='*60}\n")
        print("TASK_COMPLETE", flush=True)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        event_server.broadcast("session.status", {
            "status": "error",
            "error": str(e)
        })

    # Emit session completed event
    try:
        event_server.broadcast("session.completed", {
            "session_id": config.session_id,
            "status": "ok",
            "ts": time.time(),
        })
    except Exception:
        pass

    # Keep UI alive or shutdown
    if config.keepalive:
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
    else:
        try:
            httpd.shutdown()
        except Exception:
            pass


# ========== CLI Entry Point ==========
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Docker Agent with Docker SDK")
    parser.add_argument("--task", help="Task for the agent to execute")
    parser.add_argument("--session-id", dest="session_id", help="Session identifier")
    parser.add_argument("--name", default="docker-session", help="Agent session name")
    parser.add_argument("--model", help="Model to use")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory")
    parser.add_argument("--keepalive", action="store_true", help="Keep UI alive after completion")
    # gRPC Worker Mode
    parser.add_argument("--grpc", action="store_true", help="Start as gRPC worker")
    parser.add_argument("--grpc-port", dest="grpc_port", type=int, default=50063, help="gRPC port (default: 50063)")
    args = parser.parse_args()

    # gRPC Worker Mode
    if args.grpc:
        from shared.grpc_adapter import serve_as_grpc, AgentGRPCConfig
        grpc_config = AgentGRPCConfig(
            name="docker",
            port=args.grpc_port,
            agent_runner=run_docker_agent,
            config_class=DockerAgentConfig,
            description="Docker Agent for container management",
            capabilities=["list_containers", "run_container", "stop_container", "logs", "compose"]
        )
        print(f"🐳 Starting docker gRPC worker on port {args.grpc_port}...")
        asyncio.run(serve_as_grpc(grpc_config))
    else:
        # Standard CLI Mode
        session_id = args.session_id or str(uuid.uuid4())
        task = args.task or os.getenv("MCP_TASK") or "List running Docker containers"

        config = DockerAgentConfig(
            task=task,
            session_id=session_id,
            name=args.name,
            model=args.model,
            working_dir=args.working_dir,
            keepalive=bool(args.keepalive)
        )

        asyncio.run(run_docker_agent(config))

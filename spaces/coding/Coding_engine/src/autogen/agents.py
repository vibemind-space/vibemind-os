"""
AutoGen Agents - Specialized agents using Claude CLI.

Each agent:
1. Has a specific system message for its domain
2. Uses Claude CLI for actual code generation
3. Can hand off to other agents via AutoGen
"""
from typing import Optional, Callable, Any
import json

try:
    from autogen import ConversableAgent, AssistantAgent, UserProxyAgent
    AUTOGEN_AVAILABLE = True
except ImportError:
    AUTOGEN_AVAILABLE = False
    # Stub classes for when autogen is not installed
    class ConversableAgent:
        pass
    class AssistantAgent:
        pass
    class UserProxyAgent:
        pass

from src.autogen.cli_wrapper import ClaudeCLI, CLIResponse


def create_cli_executor(agent_type: str, working_dir: Optional[str] = None) -> Callable:
    """Create a function that executes prompts via Claude CLI."""

    cli = ClaudeCLI(working_dir=working_dir)

    def execute_with_cli(prompt: str) -> str:
        """Execute prompt using Claude CLI and return response."""
        response = cli.execute_sync(prompt)

        if response.success:
            result = {
                "status": "success",
                "output": response.output,
                "files": [
                    {"path": f.path, "language": f.language, "content": f.content[:500] + "..." if len(f.content) > 500 else f.content}
                    for f in response.files
                ],
            }
        else:
            result = {
                "status": "error",
                "error": response.error,
            }

        return json.dumps(result, indent=2)

    return execute_with_cli


# Agent system messages
COORDINATOR_SYSTEM_MESSAGE = """You are the Coordinator Agent for a coding engine.

Your role is to:
1. Analyze incoming task slices
2. Delegate to appropriate specialized agents
3. Track progress and handle failures
4. Assemble final results

When you receive a slice, identify the best agent to handle it and hand off the task.
Available agents: frontend, backend, testing, security, devops

Respond with HANDOFF: <agent_name> to delegate a task."""

FRONTEND_SYSTEM_MESSAGE = """You are a Frontend Development Agent specializing in UI implementation.

Your expertise:
- React, Vue, Svelte components
- TypeScript
- CSS, Tailwind, styled-components
- Responsive design
- Accessibility

When given a requirement:
1. Analyze what UI components are needed
2. Design the component structure
3. Implement clean, reusable code
4. Include proper types and props

Always output complete, working code files."""

BACKEND_SYSTEM_MESSAGE = """You are a Backend Development Agent specializing in APIs and data.

Your expertise:
- Python (FastAPI, Django)
- Node.js (Express, NestJS)
- Database design (PostgreSQL, MongoDB)
- REST and GraphQL APIs
- Authentication/Authorization

When given a requirement:
1. Design the API structure
2. Create database models if needed
3. Implement endpoint handlers
4. Include error handling and validation

Always output complete, working code files."""

TESTING_SYSTEM_MESSAGE = """You are a Testing Agent specializing in test automation.

Your expertise:
- Unit testing (pytest, Jest)
- Integration testing
- E2E testing (Playwright, Cypress)
- Test fixtures and mocks
- Code coverage

When given a requirement:
1. Identify what needs to be tested
2. Design comprehensive test cases
3. Implement tests with proper assertions
4. Include edge cases and error scenarios

Always output complete test files."""

SECURITY_SYSTEM_MESSAGE = """You are a Security Agent specializing in application security.

Your expertise:
- OWASP Top 10
- Secure coding practices
- Authentication/Authorization
- Input validation
- Cryptography

When given code to review:
1. Identify potential vulnerabilities
2. Assess severity and impact
3. Provide specific fixes
4. Explain the security implications

Output a security report with findings and remediation."""

DEVOPS_SYSTEM_MESSAGE = """You are a DevOps Agent specializing in infrastructure and deployment.

Your expertise:
- Docker containerization
- Kubernetes orchestration
- CI/CD pipelines
- Infrastructure as Code
- Cloud platforms (AWS, GCP, Azure)

When given a requirement:
1. Design the infrastructure needed
2. Create configuration files
3. Set up CI/CD pipelines
4. Include security best practices

Always output complete configuration files."""


def create_coordinator_agent(
    name: str = "Coordinator",
    working_dir: Optional[str] = None,
) -> "ConversableAgent":
    """Create the coordinator agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return AssistantAgent(
        name=name,
        system_message=COORDINATOR_SYSTEM_MESSAGE,
        llm_config=False,  # We'll use CLI instead
    )


def create_frontend_agent(
    name: str = "Frontend",
    working_dir: Optional[str] = None,
) -> "ConversableAgent":
    """Create the frontend development agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agent = AssistantAgent(
        name=name,
        system_message=FRONTEND_SYSTEM_MESSAGE,
        llm_config=False,
    )

    # Attach CLI executor
    agent.cli_executor = create_cli_executor("frontend", working_dir)

    return agent


def create_backend_agent(
    name: str = "Backend",
    working_dir: Optional[str] = None,
) -> "ConversableAgent":
    """Create the backend development agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agent = AssistantAgent(
        name=name,
        system_message=BACKEND_SYSTEM_MESSAGE,
        llm_config=False,
    )

    agent.cli_executor = create_cli_executor("backend", working_dir)

    return agent


def create_testing_agent(
    name: str = "Testing",
    working_dir: Optional[str] = None,
) -> "ConversableAgent":
    """Create the testing agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agent = AssistantAgent(
        name=name,
        system_message=TESTING_SYSTEM_MESSAGE,
        llm_config=False,
    )

    agent.cli_executor = create_cli_executor("testing", working_dir)

    return agent


def create_security_agent(
    name: str = "Security",
    working_dir: Optional[str] = None,
) -> "ConversableAgent":
    """Create the security review agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agent = AssistantAgent(
        name=name,
        system_message=SECURITY_SYSTEM_MESSAGE,
        llm_config=False,
    )

    agent.cli_executor = create_cli_executor("security", working_dir)

    return agent


def create_devops_agent(
    name: str = "DevOps",
    working_dir: Optional[str] = None,
) -> "ConversableAgent":
    """Create the DevOps agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agent = AssistantAgent(
        name=name,
        system_message=DEVOPS_SYSTEM_MESSAGE,
        llm_config=False,
    )

    agent.cli_executor = create_cli_executor("devops", working_dir)

    return agent


def create_all_agents(working_dir: Optional[str] = None) -> dict[str, "ConversableAgent"]:
    """Create all specialized agents."""
    return {
        "coordinator": create_coordinator_agent(working_dir=working_dir),
        "frontend": create_frontend_agent(working_dir=working_dir),
        "backend": create_backend_agent(working_dir=working_dir),
        "testing": create_testing_agent(working_dir=working_dir),
        "security": create_security_agent(working_dir=working_dir),
        "devops": create_devops_agent(working_dir=working_dir),
    }

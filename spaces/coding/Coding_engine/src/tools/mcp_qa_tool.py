# -*- coding: utf-8 -*-
"""
MCP QA Verification Tool - Gives QA Validators the ability to verify
Operator work via the MCP Orchestrator.

The QA Validator can call `verify_with_mcp` to independently check:
- File existence and content
- Build success
- Configuration correctness
- Docker container status
- Database schema validity

Usage:
    from src.tools.mcp_qa_tool import create_mcp_qa_tool

    qa_tool = create_mcp_qa_tool(working_dir="./output/my-project")
    # Pass to create_team(qa_tools=[qa_tool])
"""
import json
import structlog

logger = structlog.get_logger()


def create_mcp_qa_tool(working_dir: str = "."):
    """
    Create an MCP QA verification FunctionTool for AutoGen QA Validators.

    The tool wraps the MCPOrchestrator to let QA agents independently
    verify the Operator's work using real MCP tools (filesystem, npm,
    docker, prisma, etc.).

    Args:
        working_dir: Project working directory for MCP operations

    Returns:
        FunctionTool configured for QA verification
    """
    try:
        from autogen_core.tools import FunctionTool
    except ImportError:
        logger.warning("mcp_qa_tool_autogen_not_available",
                       msg="Install autogen-agentchat to use MCP QA tools")
        return None

    async def verify_with_mcp(verification_task: str) -> str:
        """
        Verify Operator work using MCP tools via the Orchestrator.

        The MCP Orchestrator will plan which tools to use (filesystem, npm,
        docker, etc.), execute the verification steps, and return results.

        Args:
            verification_task: What to verify in natural language.
                Examples:
                - "Check if prisma/schema.prisma exists and contains a User model"
                - "Verify package.json has @nestjs/websockets dependency"
                - "Check if docker-compose.yml includes a redis service"
                - "Run 'npx tsc --noEmit' to verify TypeScript compiles"

        Returns:
            JSON string with verification results including:
            - verified: bool - whether verification passed
            - steps_executed: int - number of MCP tool calls made
            - output: str - detailed output from tools
            - errors: list - any errors encountered
        """
        try:
            from src.mcp.mcp_orchestrator import MCPOrchestrator

            orchestrator = MCPOrchestrator(
                working_dir=working_dir,
                recovery_enabled=False,
                publish_events=False,
            )

            result = await orchestrator.execute_task(
                task=verification_task,
                context={
                    "phase": "qa_validation",
                    "working_dir": working_dir,
                },
            )

            logger.info(
                "mcp_qa_verification_complete",
                task=verification_task[:80],
                success=result.success,
                steps=result.steps_executed,
            )

            return json.dumps({
                "verified": result.success,
                "steps_executed": result.steps_executed,
                "output": str(result.output)[:2000] if result.output else "",
                "errors": result.errors[:5] if result.errors else [],
            })

        except ImportError:
            return json.dumps({
                "verified": False,
                "steps_executed": 0,
                "output": "MCP Orchestrator not available",
                "errors": [{"error": "MCPOrchestrator import failed"}],
            })
        except Exception as e:
            logger.error("mcp_qa_verification_failed", error=str(e))
            return json.dumps({
                "verified": False,
                "steps_executed": 0,
                "output": "",
                "errors": [{"error": str(e)}],
            })

    return FunctionTool(
        func=verify_with_mcp,
        name="verify_with_mcp",
        description=(
            "Verify Operator work using MCP tools (filesystem, npm, docker, prisma). "
            "Pass a natural language verification task. Returns JSON with verified/output/errors. "
            "Use for read-only checks: file existence, build validation, config correctness."
        ),
    )


# Default QA system prompt addition when MCP tool is available
MCP_QA_PROMPT_ADDITION = """

## MCP Verification Tool

You have access to `verify_with_mcp` - a tool that can independently verify the Operator's work
using real MCP tools (filesystem, npm, docker, prisma, etc.).

VERIFICATION WORKFLOW:
1. Review the Operator's work description carefully
2. Use `verify_with_mcp` to check 2-3 critical claims:
   - File existence: "Check if src/websocket/gateway.ts exists and contains @WebSocketGateway"
   - Dependencies: "Verify package.json includes socket.io dependency"
   - Config: "Check if docker-compose.yml has a redis service on port 6379"
   - Build: "Run npx tsc --noEmit to check TypeScript compilation"
3. Based on verification results:
   - If all checks pass → say "APPROVE"
   - If checks fail → list specific gaps with evidence from verification

RULES:
- Use the tool for VERIFICATION only (read-only checks)
- Do NOT use it to generate, fix, or modify code
- Verify at least 2 critical claims before approving
- Include verification evidence in your response
"""

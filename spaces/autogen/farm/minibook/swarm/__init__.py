"""AutoGen Swarm — modular pipeline package."""

from .constants import (
    CascadeContext, MINIBOOK_URL, POLL_INTERVAL, STEP_TIMEOUT, MAX_REVISIONS,
    OUTPUT_DIR, CREDS_FILE, LLM_PROVIDER, MCP_GATEWAY_PORT,
    FORGE_STATE_FILE, FORGE_METRICS_FILE, FORGE_API_PORT, STALL_THRESHOLD,
    MAX_CASCADE_DEPTH, FORGE_SCHEDULE, FORGE_HOURLY_BUDGET, DOC_RESEARCH_TOPICS,
)
from .knowledge import (
    AUTOGEN_PATTERNS, AUTOGEN_KNOWLEDGE, MCP_DOMAIN_HINTS, MCP_SERVER_CONFIG_INFO,
    AUTOGEN_RAG_TOOLS, GENERIC_MAIN_PY, AGENT_ROLES, FLOW, FORGE_AGENT_ROLES,
)
from .api_client import api_post, api_get, load_credentials, save_credentials, register_agent
from .llm import call_gpt4o, call_gpt4o_json, call_gpt4o_with_tools
from .docker_ops import (
    get_mcp_catalog, format_catalog_for_llm, classify_task_domain,
    prepare_docker_context, docker_build_test, docker_run_test, docker_run_test_with_args,
    enable_mcp_servers, get_mcp_server_tools, format_mcp_tools_for_prompt,
    get_installed_mcp_servers,
    start_mcp_gateway, stop_mcp_gateway,
    gordon_diagnose, gordon_fix_and_rebuild, gordon_fix_and_rerun,
    configure_mcp_server, set_mcp_secret,
)
from .code_processing import (
    parse_code_blocks, parse_yaml_blocks, find_code_post,
    test_generated_code, write_output, load_cascade_context,
)
from .pipeline import SwarmPipeline
from .forge_agents import (
    ForgeState, load_forge_state, save_forge_state, ForgePostTracker,
    DocResearcherAgent, DependencyAgent, SecurityAgent, BenchmarkAgent, RepoAgent,
)
from .forge_orchestrator import ForgeOrchestrator, ForgeAPI
from .input_parser import (
    parse_input_file_llm, generate_core_team_yamls, generate_sub_team_yamls,
    generate_sales_tools_py, generate_wiring_tools, get_wiring_tool_names,
)
from .todo_implementer import implement_todos, scan_todo_tools

__all__ = [
    "CascadeContext", "MINIBOOK_URL", "POLL_INTERVAL", "STEP_TIMEOUT",
    "MAX_REVISIONS", "OUTPUT_DIR", "CREDS_FILE", "LLM_PROVIDER", "MCP_GATEWAY_PORT",
    "AUTOGEN_PATTERNS", "AUTOGEN_KNOWLEDGE", "MCP_DOMAIN_HINTS", "AUTOGEN_RAG_TOOLS",
    "GENERIC_MAIN_PY", "AGENT_ROLES", "FLOW", "FORGE_AGENT_ROLES",
    "api_post", "api_get", "load_credentials", "save_credentials", "register_agent",
    "call_gpt4o", "call_gpt4o_json", "call_gpt4o_with_tools",
    "get_mcp_catalog", "format_catalog_for_llm", "classify_task_domain",
    "prepare_docker_context", "docker_build_test", "docker_run_test", "docker_run_test_with_args",
    "enable_mcp_servers", "get_mcp_server_tools", "format_mcp_tools_for_prompt",
    "get_installed_mcp_servers",
    "start_mcp_gateway", "stop_mcp_gateway",
    "gordon_diagnose", "gordon_fix_and_rebuild", "gordon_fix_and_rerun",
    "parse_code_blocks", "parse_yaml_blocks", "find_code_post",
    "test_generated_code", "write_output", "load_cascade_context",
    "SwarmPipeline",
    "ForgeState", "load_forge_state", "save_forge_state", "ForgePostTracker",
    "DocResearcherAgent", "DependencyAgent", "SecurityAgent", "BenchmarkAgent", "RepoAgent",
    "ForgeOrchestrator", "ForgeAPI",
    "parse_input_file_llm", "generate_core_team_yamls", "generate_sub_team_yamls",
    "generate_sales_tools_py", "generate_wiring_tools", "get_wiring_tool_names",
    "implement_todos", "scan_todo_tools",
]

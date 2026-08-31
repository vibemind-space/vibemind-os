"""
Tool Call Generator - Convert Abstract Interventions to Concrete Tool Calls

This module bridges the gap between abstract routing decisions (suggest, retry, wait)
and concrete executable tool calls with parameters. It uses task features and learned
patterns to generate appropriate tool invocations.

Key Insight: Abstract interventions are meaningless without concrete actions
- "suggest" intervention -> What should we suggest? Which tool? What parameters?
- "retry" intervention -> Retry what? With what modifications?
- "wait" intervention -> Wait for what? How long? What condition?

Tool Call Generation Strategy:
1. Extract task features (type, complexity, urgency, context)
2. Select appropriate tool template based on features
3. Infer parameters from task description using patterns
4. Generate executable tool call with confidence score
5. Include fallback options for robustness

Architecture:
- ToolTemplate: Defines tool signature and parameter inference rules
- ToolCallGenerator: Main class that generates tool calls from interventions
- ParameterInferencer: Extracts parameter values from task descriptions
- ToolLibrary: Registry of available tools and their templates
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum
import re
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ToolType(Enum):
    """Categories of tools available"""
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    GIT = "git"
    FILE_SYSTEM = "file_system"
    DATABASE = "database"
    MONITORING = "monitoring"
    API = "api"
    SHELL = "shell"
    SEARCH = "search"
    VALIDATION = "validation"
    LLM_AGENT = "llm_agent"  # Phase E: dispatch subtasks to LLM-backed agents (Claude, Groq, etc.)


@dataclass
class ToolParameter:
    """Definition of a tool parameter"""
    name: str                           # Parameter name
    param_type: str                     # Data type (str, int, bool, list, dict)
    required: bool                      # Whether parameter is required
    default: Any = None                 # Default value if not inferred
    description: str = ""               # Human-readable description
    inference_patterns: List[str] = field(default_factory=list)  # Regex patterns to extract from task


@dataclass
class ToolTemplate:
    """Template defining a tool's signature and parameter inference"""
    tool_name: str                      # Name of the tool (e.g., "docker_deploy")
    tool_type: ToolType                 # Category of tool
    intervention_type: str              # Primary intervention (suggest/retry/wait/execute)
    parameters: List[ToolParameter]     # Parameter definitions
    description: str = ""               # What the tool does
    confidence_threshold: float = 0.5   # Minimum confidence to use this tool
    task_type_keywords: List[str] = field(default_factory=list)  # Keywords indicating this tool


@dataclass
class ToolCall:
    """Generated tool call with parameters and metadata"""
    tool_name: str                      # Tool to invoke
    tool_type: ToolType                 # Tool category
    parameters: Dict[str, Any]          # Inferred parameters
    confidence: float                   # Confidence in parameter inference (0.0-1.0)
    intervention_source: str            # Source intervention (suggest/retry/etc)
    reasoning: str = ""                 # Explanation of why this tool was selected
    fallback_tools: List[str] = field(default_factory=list)  # Alternative tools if this fails


class ParameterInferencer:
    """
    Infers parameter values from task descriptions using patterns and heuristics

    Uses regex patterns, keyword matching, and contextual inference to extract
    parameter values from natural language task descriptions.
    """

    def __init__(self):
        """Initialize parameter inference engine"""
        # Common parameter extraction patterns
        self.patterns = {
            # Container/image names
            'container': [
                r'container[:\s]+([a-zA-Z0-9_-]+)',
                r'deploy[:\s]+([a-zA-Z0-9_-]+)',
                r'image[:\s]+([a-zA-Z0-9_/-]+)'
            ],
            # Port numbers
            'port': [
                r'port[:\s]+(\d+)',
                r':(\d{2,5})\b',
                r'on port (\d+)'
            ],
            # Service names
            'service': [
                r'service[:\s]+([a-zA-Z0-9_-]+)',
                r'([a-zA-Z0-9_-]+)\s+service',
                r'in ([a-zA-Z0-9_-]+)'
            ],
            # File paths
            'file': [
                r'file[:\s]+([^\s]+)',
                r'path[:\s]+([^\s]+)',
                r'([/\\][^\s]+)'
            ],
            # Urgency/priority
            'urgent': [
                r'urgent',
                r'immediately',
                r'critical',
                r'high priority'
            ],
            # Time durations
            'duration': [
                r'(\d+)\s*(second|minute|hour)s?',
                r'wait\s+(\d+)',
                r'timeout[:\s]+(\d+)'
            ]
        }

        logger.info("[ParameterInferencer] Initialized with pattern library")

    def infer_parameter(
        self,
        param_def: ToolParameter,
        task: str,
        context: Dict = None
    ) -> Tuple[Any, float]:
        """
        Infer parameter value from task description

        Args:
            param_def: Parameter definition with inference patterns
            task: Task description
            context: Additional context (previous parameters, task type, etc.)

        Returns:
            (inferred_value, confidence)
        """
        task_lower = task.lower()

        # Try custom inference patterns first
        if param_def.inference_patterns:
            for pattern in param_def.inference_patterns:
                match = re.search(pattern, task, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    return self._cast_value(value, param_def.param_type), 0.9

        # Try common patterns by parameter name
        param_name_lower = param_def.name.lower()
        if param_name_lower in self.patterns:
            for pattern in self.patterns[param_name_lower]:
                match = re.search(pattern, task, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    return self._cast_value(value, param_def.param_type), 0.8

        # Boolean parameters - check for keywords
        if param_def.param_type == 'bool':
            if param_name_lower in task_lower:
                return True, 0.7
            return param_def.default if param_def.default is not None else False, 0.5

        # Use default if available
        if param_def.default is not None:
            return param_def.default, 0.4

        # Return None with low confidence
        return None, 0.0

    def _cast_value(self, value: str, target_type: str) -> Any:
        """Cast string value to target type"""
        try:
            if target_type == 'int':
                return int(value)
            elif target_type == 'float':
                return float(value)
            elif target_type == 'bool':
                return value.lower() in ['true', '1', 'yes']
            elif target_type == 'list':
                return [v.strip() for v in value.split(',')]
            else:
                return str(value)
        except (ValueError, AttributeError):
            return value


class ToolLibrary:
    """
    Registry of available tools with templates for parameter inference

    Tools are organized by intervention type and task type for efficient lookup.
    """

    def __init__(self):
        """Initialize tool library with standard tools"""
        self.tools: Dict[str, ToolTemplate] = {}
        self._initialize_standard_tools()

        logger.info(f"[ToolLibrary] Initialized with {len(self.tools)} tools")

    def _initialize_standard_tools(self):
        """Initialize standard tool templates"""

        # Docker deployment tool
        self.add_tool(ToolTemplate(
            tool_name="docker_deploy",
            tool_type=ToolType.DOCKER,
            intervention_type="suggest",
            parameters=[
                ToolParameter(
                    name="image",
                    param_type="str",
                    required=True,
                    description="Docker image name",
                    inference_patterns=[r'image[:\s]+([a-zA-Z0-9_/-]+)', r'deploy[:\s]+([a-zA-Z0-9_/-]+)']
                ),
                ToolParameter(
                    name="container_name",
                    param_type="str",
                    required=False,
                    default="app",
                    description="Container name",
                    inference_patterns=[r'container[:\s]+([a-zA-Z0-9_-]+)']
                ),
                ToolParameter(
                    name="port",
                    param_type="int",
                    required=False,
                    default=8080,
                    description="Port mapping",
                    inference_patterns=[r'port[:\s]+(\d+)', r':(\d{2,5})\b']
                ),
                ToolParameter(
                    name="detached",
                    param_type="bool",
                    required=False,
                    default=True,
                    description="Run in background"
                )
            ],
            description="Deploy a Docker container with specified image and configuration",
            confidence_threshold=0.6,
            task_type_keywords=["docker", "container", "deploy", "image"]
        ))

        # Kubernetes deployment tool
        self.add_tool(ToolTemplate(
            tool_name="kubectl_apply",
            tool_type=ToolType.KUBERNETES,
            intervention_type="suggest",
            parameters=[
                ToolParameter(
                    name="manifest_file",
                    param_type="str",
                    required=True,
                    description="Path to Kubernetes manifest",
                    inference_patterns=[r'manifest[:\s]+([^\s]+)', r'file[:\s]+([^\s]+)']
                ),
                ToolParameter(
                    name="namespace",
                    param_type="str",
                    required=False,
                    default="default",
                    description="Kubernetes namespace",
                    inference_patterns=[r'namespace[:\s]+([a-zA-Z0-9_-]+)']
                )
            ],
            description="Apply Kubernetes manifest to cluster",
            confidence_threshold=0.7,
            task_type_keywords=["kubernetes", "kubectl", "manifest", "k8s"]
        ))

        # Git operations tool
        self.add_tool(ToolTemplate(
            tool_name="git_commit_push",
            tool_type=ToolType.GIT,
            intervention_type="suggest",
            parameters=[
                ToolParameter(
                    name="message",
                    param_type="str",
                    required=True,
                    description="Commit message",
                    inference_patterns=[r'commit[:\s]+["\']([^"\']+)["\']', r'message[:\s]+["\']([^"\']+)["\']']
                ),
                ToolParameter(
                    name="branch",
                    param_type="str",
                    required=False,
                    default="main",
                    description="Target branch",
                    inference_patterns=[r'branch[:\s]+([a-zA-Z0-9_/-]+)', r'to ([a-zA-Z0-9_/-]+)']
                )
            ],
            description="Commit changes and push to remote repository",
            confidence_threshold=0.6,
            task_type_keywords=["git", "commit", "push", "repository"]
        ))

        # Retry with modification tool
        self.add_tool(ToolTemplate(
            tool_name="retry_with_modification",
            tool_type=ToolType.SHELL,
            intervention_type="retry",
            parameters=[
                ToolParameter(
                    name="original_command",
                    param_type="str",
                    required=True,
                    description="Command to retry"
                ),
                ToolParameter(
                    name="modification",
                    param_type="str",
                    required=True,
                    description="What to change",
                    inference_patterns=[r'change[:\s]+([^,]+)', r'modify[:\s]+([^,]+)']
                ),
                ToolParameter(
                    name="max_retries",
                    param_type="int",
                    required=False,
                    default=3,
                    description="Maximum retry attempts"
                )
            ],
            description="Retry failed command with modifications",
            confidence_threshold=0.5,
            task_type_keywords=["retry", "failed", "error", "again"]
        ))

        # Wait for condition tool
        self.add_tool(ToolTemplate(
            tool_name="wait_for_condition",
            tool_type=ToolType.MONITORING,
            intervention_type="wait",
            parameters=[
                ToolParameter(
                    name="condition",
                    param_type="str",
                    required=True,
                    description="Condition to wait for",
                    inference_patterns=[r'wait for ([^,]+)', r'until ([^,]+)']
                ),
                ToolParameter(
                    name="timeout",
                    param_type="int",
                    required=False,
                    default=60,
                    description="Timeout in seconds",
                    inference_patterns=[r'timeout[:\s]+(\d+)', r'(\d+)\s*second']
                ),
                ToolParameter(
                    name="check_interval",
                    param_type="int",
                    required=False,
                    default=5,
                    description="Check interval in seconds"
                )
            ],
            description="Wait for a specific condition to be met",
            confidence_threshold=0.6,
            task_type_keywords=["wait", "until", "condition", "ready"]
        ))

        # Generic shell execution tool
        self.add_tool(ToolTemplate(
            tool_name="shell_execute",
            tool_type=ToolType.SHELL,
            intervention_type="execute",
            parameters=[
                ToolParameter(
                    name="command",
                    param_type="str",
                    required=True,
                    description="Shell command to execute"
                ),
                ToolParameter(
                    name="timeout",
                    param_type="int",
                    required=False,
                    default=30,
                    description="Execution timeout"
                )
            ],
            description="Execute arbitrary shell command",
            confidence_threshold=0.4,
            task_type_keywords=["execute", "run", "command", "shell"]
        ))

        # Phase E — Claude as subagent
        # Brain dispatches a focused subtask to Claude (Anthropic API via OpenRouter
        # or direct). Use for: code generation, complex reasoning, refactoring,
        # text composition that exceeds Brain's heuristic responder.
        self.add_tool(ToolTemplate(
            tool_name="claude_subagent",
            tool_type=ToolType.LLM_AGENT,
            intervention_type="execute",
            parameters=[
                ToolParameter(
                    name="prompt",
                    param_type="str",
                    required=True,
                    description="Subtask prompt (clear, focused, single-shot)",
                ),
                ToolParameter(
                    name="system",
                    param_type="str",
                    required=False,
                    default="",
                    description="Optional system prompt (role/persona)",
                ),
                ToolParameter(
                    name="model",
                    param_type="str",
                    required=False,
                    default="anthropic/claude-haiku-4.5",
                    description="OpenRouter model id (default: claude-haiku-4.5)",
                ),
                ToolParameter(
                    name="max_tokens",
                    param_type="int",
                    required=False,
                    default=1024,
                    description="Max output tokens",
                ),
                ToolParameter(
                    name="temperature",
                    param_type="int",  # ToolParameter doesn't have float — int OK for now
                    required=False,
                    default=0,
                    description="Sampling temperature (0=deterministic)",
                ),
            ],
            description=(
                "Dispatch a focused subtask to Claude as Brain's coding/reasoning "
                "subagent. Returns the LLM response. Use for tasks that exceed "
                "Brain's internal responder (code, complex reasoning, refactoring)."
            ),
            confidence_threshold=0.5,
            task_type_keywords=[
                "code", "refactor", "rewrite", "explain", "design",
                "implement", "review", "debug", "claude",
            ],
        ))

        # Groq fast-reasoning subagent (for cheap, fast subtasks)
        self.add_tool(ToolTemplate(
            tool_name="groq_subagent",
            tool_type=ToolType.LLM_AGENT,
            intervention_type="execute",
            parameters=[
                ToolParameter(
                    name="prompt",
                    param_type="str",
                    required=True,
                    description="Subtask prompt",
                ),
                ToolParameter(
                    name="model",
                    param_type="str",
                    required=False,
                    default="groq::llama-3.3-70b-versatile",
                    description="Groq model (groq:: prefix routes via direct API)",
                ),
                ToolParameter(
                    name="max_tokens",
                    param_type="int",
                    required=False,
                    default=512,
                    description="Max output tokens",
                ),
            ],
            description=(
                "Dispatch a fast/cheap subtask to Groq (Llama 3.3 70B). "
                "Use for: classification, summarization, quick reasoning, "
                "anything where Brain's existing responder agent would do."
            ),
            confidence_threshold=0.4,
            task_type_keywords=[
                "summarize", "classify", "extract", "quick", "fast", "groq",
            ],
        ))

    def add_tool(self, template: ToolTemplate) -> None:
        """Add tool template to library"""
        self.tools[template.tool_name] = template
        logger.debug(f"[ToolLibrary] Added tool: {template.tool_name}")

    def get_tool(self, tool_name: str) -> Optional[ToolTemplate]:
        """Get tool template by name"""
        return self.tools.get(tool_name)

    def find_tools_for_intervention(
        self,
        intervention_type: str,
        task: str = "",
        min_confidence: float = 0.0
    ) -> List[ToolTemplate]:
        """
        Find tools matching intervention type and task

        Args:
            intervention_type: Type of intervention (suggest/retry/wait/execute)
            task: Task description for keyword matching
            min_confidence: Minimum confidence threshold

        Returns:
            List of matching tool templates sorted by relevance
        """
        matching_tools = []
        task_lower = task.lower()

        for template in self.tools.values():
            # Match intervention type
            if template.intervention_type != intervention_type:
                continue

            # Check confidence threshold
            if template.confidence_threshold < min_confidence:
                continue

            # Calculate relevance score based on keyword matches
            relevance = 0.0
            for keyword in template.task_type_keywords:
                if keyword in task_lower:
                    relevance += 1.0

            # Normalize relevance
            if template.task_type_keywords:
                relevance /= len(template.task_type_keywords)

            matching_tools.append((template, relevance))

        # Sort by relevance (highest first)
        matching_tools.sort(key=lambda x: x[1], reverse=True)

        return [template for template, _ in matching_tools]


class ToolCallGenerator:
    """
    Main class that generates concrete tool calls from abstract interventions

    Workflow:
    1. Receive intervention decision from routing system
    2. Analyze task features and context
    3. Select appropriate tool template
    4. Infer parameter values from task description
    5. Generate executable tool call with confidence
    6. Include fallback options
    """

    def __init__(self, tool_library: Optional[ToolLibrary] = None):
        """
        Initialize tool call generator

        Args:
            tool_library: Custom tool library (uses default if None)
        """
        self.tool_library = tool_library if tool_library else ToolLibrary()
        self.param_inferencer = ParameterInferencer()

        logger.info("[ToolCallGenerator] Initialized")

    def generate_tool_call(
        self,
        intervention_type: str,
        task: str,
        task_features: Dict = None,
        context: Dict = None,
        min_confidence: float = 0.5
    ) -> Optional[ToolCall]:
        """
        Generate tool call from intervention decision

        Args:
            intervention_type: Type of intervention (suggest/retry/wait/execute)
            task: Task description
            task_features: Extracted task features (complexity, urgency, etc.)
            context: Additional context (previous actions, errors, etc.)
            min_confidence: Minimum confidence to generate tool call

        Returns:
            ToolCall object or None if no suitable tool found
        """
        # Find matching tools
        matching_tools = self.tool_library.find_tools_for_intervention(
            intervention_type=intervention_type,
            task=task,
            min_confidence=min_confidence
        )

        if not matching_tools:
            logger.warning(f"[ToolCallGenerator] No tools found for intervention '{intervention_type}'")
            return None

        # Try each tool in order of relevance
        for template in matching_tools:
            tool_call = self._generate_from_template(
                template=template,
                task=task,
                task_features=task_features,
                context=context
            )

            if tool_call and tool_call.confidence >= min_confidence:
                logger.info(f"[ToolCallGenerator] Generated tool call: {tool_call.tool_name} (confidence={tool_call.confidence:.2f})")
                return tool_call

        # No tool met confidence threshold
        logger.warning(f"[ToolCallGenerator] No tool met confidence threshold {min_confidence}")
        return None

    def _generate_from_template(
        self,
        template: ToolTemplate,
        task: str,
        task_features: Dict = None,
        context: Dict = None
    ) -> Optional[ToolCall]:
        """Generate tool call from specific template"""
        parameters = {}
        confidence_scores = []

        # Infer each parameter
        for param_def in template.parameters:
            value, conf = self.param_inferencer.infer_parameter(
                param_def=param_def,
                task=task,
                context=context
            )

            # Check required parameters
            if param_def.required and (value is None or conf < 0.3):
                logger.debug(f"[ToolCallGenerator] Failed to infer required parameter: {param_def.name}")
                return None

            if value is not None:
                parameters[param_def.name] = value
                confidence_scores.append(conf)

        # Calculate overall confidence
        overall_confidence = np.mean(confidence_scores) if confidence_scores else 0.0

        # Generate reasoning
        reasoning = f"Selected {template.tool_name} for {template.intervention_type} intervention based on task keywords"

        # Get fallback tools
        fallback_tools = [
            t.tool_name for t in self.tool_library.find_tools_for_intervention(
                intervention_type=template.intervention_type,
                task=task
            ) if t.tool_name != template.tool_name
        ][:2]  # Top 2 fallbacks

        return ToolCall(
            tool_name=template.tool_name,
            tool_type=template.tool_type,
            parameters=parameters,
            confidence=overall_confidence,
            intervention_source=template.intervention_type,
            reasoning=reasoning,
            fallback_tools=fallback_tools
        )

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self.tool_library.tools.keys())


# Demo usage
if __name__ == "__main__":
    print("="*70)
    print("TOOL CALL GENERATOR - DEMO")
    print("="*70)

    # Initialize generator
    generator = ToolCallGenerator()

    print(f"\n[Setup] Tool library: {len(generator.tool_library.tools)} tools")
    print(f"[Setup] Available tools: {', '.join(generator.get_available_tools())}")

    # Test cases
    test_cases = [
        ("suggest", "Deploy Docker container nginx with monitoring on port 8080"),
        ("suggest", "Apply Kubernetes manifest deploy.yaml to production namespace"),
        ("retry", "Retry failed deployment with increased timeout"),
        ("wait", "Wait for service to be ready, timeout 120 seconds"),
        ("execute", "Run database migration script")
    ]

    print("\n" + "-"*70)
    print("TEST CASES")
    print("-"*70)

    for intervention, task in test_cases:
        print(f"\n[Test] Intervention: {intervention}")
        print(f"[Test] Task: {task}")

        tool_call = generator.generate_tool_call(
            intervention_type=intervention,
            task=task,
            min_confidence=0.5
        )

        if tool_call:
            print(f"  [OK] Tool: {tool_call.tool_name}")
            print(f"  [OK] Type: {tool_call.tool_type.value}")
            print(f"  [OK] Confidence: {tool_call.confidence:.2f}")
            print(f"  [OK] Parameters:")
            for param, value in tool_call.parameters.items():
                print(f"       - {param}: {value}")
            if tool_call.fallback_tools:
                print(f"  [OK] Fallbacks: {', '.join(tool_call.fallback_tools)}")
        else:
            print(f"  [FAIL] No tool call generated")

    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)

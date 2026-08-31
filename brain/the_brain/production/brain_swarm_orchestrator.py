"""
Brain Swarm Orchestrator
========================

Integrates AutoGen Swarm pattern with Tahlamus cognitive brain.

Architecture:
- Tahlamus ProductionPlanner provides cognitive decision-making (13 features)
- AutoGen Swarm agents handle specialized task execution
- Bidirectional integration: Brain guides agents, agents provide feedback

Key Components:
- BrainSwarmOrchestrator: Main coordinator
- Specialized agents: Memory, CTM, Decision, Execution agents
- CLI interface for command-line access
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json

from production.production_planner import ProductionPlanner
from production.cognitive_feature_agents import CognitiveFeatureAgentFactory
from production.unified_brain_client import UnifiedBrainClient

# AutoGen imports (will be installed)
try:
    from autogen_agentchat.teams import Swarm
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.messages import HandoffMessage, TextMessage
    from autogen_agentchat.conditions import HandoffTermination, TextMentionTermination
    from autogen_ext.models.openai import OpenAIChatCompletionClient
except ImportError:
    print("Warning: AutoGen not installed. Install with: pip install autogen-agentchat autogen-ext")
    Swarm = None
    AssistantAgent = None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BrainState:
    """Current state of Tahlamus brain for agent access"""
    task: str
    prediction: Dict[str, Any]
    memory_context: Dict[str, Any]
    attention_state: Dict[str, Any]
    consciousness_metrics: Dict[str, Any]
    ctm_task_id: Optional[str]
    semantic_coherence: Dict[str, Any]
    active_inference: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert brain state to dictionary for agent context"""
        return {
            'task': self.task,
            'prediction': self.prediction,
            'memory_context': self.memory_context,
            'attention_state': self.attention_state,
            'consciousness_metrics': self.consciousness_metrics,
            'ctm_task_id': self.ctm_task_id,
            'semantic_coherence': self.semantic_coherence,
            'active_inference': self.active_inference
        }

    def get_suggested_agent(self) -> str:
        """Use brain to suggest which agent should handle task"""
        task_type = self.prediction.get('task_type', 'unknown')
        primary_action = self.prediction['primary_action']

        # Map task type + action to specialized agent
        if primary_action == 'wait':
            # Needs clarification - hand to active inference agent
            return 'active_inference_agent'

        if self.ctm_task_id:
            # Complex task - use CTM agent for deep reasoning
            return 'ctm_reasoning_agent'

        # Map task types to specialized agents
        task_agent_map = {
            'docker': 'docker_execution_agent',
            'database': 'database_execution_agent',
            'debugging': 'debugging_agent',
            'api': 'api_execution_agent',
            'monitoring': 'monitoring_agent',
            'deployment': 'deployment_agent',
            'testing': 'testing_agent',
            'refactoring': 'refactoring_agent',
            'documentation': 'documentation_agent',
            'security': 'security_agent'
        }

        return task_agent_map.get(task_type, 'general_execution_agent')


class BrainSwarmOrchestrator:
    """
    Orchestrates AutoGen swarm with Tahlamus cognitive brain.

    The brain provides:
    - Memory Systems: Retrieve relevant past experiences
    - Predictive Coding: Curiosity-driven exploration
    - Attention Mechanisms: Focus on relevant information
    - Meta-Learning: Adaptive learning rates
    - CTM Async: Deep reasoning for complex tasks
    - Active Inference: Generate clarifying questions
    - Semantic Coherence: Validate agent decisions

    Agents provide:
    - Specialized execution capabilities
    - Domain expertise (Docker, Database, API, etc.)
    - Handoff coordination for complex workflows
    - Human-in-the-loop when needed
    """

    def __init__(
        self,
        session_log_dir: str = "data/logs",
        user_id: str = "swarm_user",
        openrouter_api_key: Optional[str] = None,
        use_unified_brain: bool = True,
        unified_brain_url: str = "http://localhost:5003"
    ):
        """
        Initialize brain-swarm orchestrator.

        Args:
            session_log_dir: Directory for session logs
            user_id: User ID for memory isolation
            openrouter_api_key: OpenRouter API key (required)
            use_unified_brain: Use unified brain service (recommended)
            unified_brain_url: URL of unified brain service
        """
        self.user_id = user_id
        self.openrouter_api_key = openrouter_api_key
        self.use_unified_brain = use_unified_brain

        if use_unified_brain:
            # Connect to unified brain service
            logger.info(f"Connecting to unified brain at {unified_brain_url}")
            self.brain_client = UnifiedBrainClient(
                service_name='swarm',
                brain_url=unified_brain_url
            )
            self.brain = None  # No local brain instance
            logger.info("Connected to unified brain service")
        else:
            # Fallback: Create local brain instance
            logger.info("Using local brain instance (fallback mode)")
            self.brain = ProductionPlanner(
                session_log_dir=session_log_dir,
                user_id=user_id,
                openrouter_api_key=openrouter_api_key,
                enable_continuous_learning=True,
                enable_semantic_coherence=True,
                embedding_type="hash"
            )
            self.brain_client = None

        # Track current brain state
        self.current_brain_state: Optional[BrainState] = None

        # Swarm agents
        self.agents: Dict[str, Any] = {}
        self.swarm: Optional[Any] = None

        logger.info(f"BrainSwarmOrchestrator initialized for user: {user_id}")

    def _create_model_client(self):
        """
        Create model client for agents.

        Pulls model + base_url + api_key from llm_config.yml via vibemind_shared.
        Returns an autogen OpenAIChatCompletionClient (autogen has its own client class
        that we can't replace with vibemind_shared.get_client, but we can centralize
        the config so swapping providers requires only editing llm_config.yml).
        """
        from vibemind_shared import get_model, get_provider_info
        from vibemind_shared.llm_client import _get_api_key

        # Role is "planning" (defined in llm_config.yml, with a production override
        # to openai/gpt-5-pro). The earlier "brain_planning" did NOT exist as a
        # role, so this silently fell back to `default` (groq llama, temp 0.5) —
        # the swarm never used the configured planning model. (Baustein D.3 fix.)
        _PLANNING_ROLE = "planning"
        info = get_provider_info(_PLANNING_ROLE)
        api_key = _get_api_key(info["provider"])

        if not api_key:
            raise ValueError(
                f"No API key found for provider '{info['provider']}'.\n"
                "Set the corresponding *_API_KEY in .env, or change the planning "
                "role in llm_config.yml to use a provider with a key set."
            )

        logger.info(f"Using {info['provider']}/{info['model']} for swarm agents (role={_PLANNING_ROLE})")

        return OpenAIChatCompletionClient(
            model=get_model(_PLANNING_ROLE),
            api_key=api_key,
            base_url=info["base_url"],
            # Disable parallel tool calls to prevent multiple handoffs
            model_kwargs={
                "parallel_tool_calls": False,
                "extra_headers": {
                    "HTTP-Referer": "https://github.com/Flissel/the_brain",
                    "X-Title": "Tahlamus Brain Swarm"
                }
            }
        )

    def _create_brain_context_message(self) -> str:
        """Create context message with brain state for agents"""
        if not self.current_brain_state:
            return "No brain state available yet."

        state = self.current_brain_state

        context_parts = [
            f"## Brain Analysis for Task: {state.task}",
            "",
            f"**Primary Action**: {state.prediction['primary_action']}",
            f"**Task Type**: {state.prediction.get('task_type', 'unknown')}",
            f"**Confidence**: {state.prediction.get('confidence', 0.0):.2f}",
            f"**Processing Mode**: {state.prediction.get('processing_mode', 'unknown')}",
            "",
            "### Memory Context:",
            f"- Working Memory: {len(state.memory_context.get('working_memory', []))} items",
            f"- Episodic Memories: {len(state.memory_context.get('episodic_memories', []))} relevant",
            "",
            "### Attention State:",
            f"- Focus: {state.attention_state.get('top_modality', 'unknown')}",
            "",
            "### Consciousness Metrics:",
            f"- Awareness: {state.consciousness_metrics.get('awareness_score', 0.0):.2f}",
            f"- State: {state.consciousness_metrics.get('global_workspace_state', 'unknown')}",
            ""
        ]

        # Add active inference questions if available
        if state.active_inference.get('questions_to_ask'):
            context_parts.append("### Clarifying Questions Needed:")
            for q in state.active_inference['questions_to_ask']:
                context_parts.append(f"- {q}")
            context_parts.append("")

        # Add CTM insights if available
        if state.ctm_task_id:
            context_parts.append(f"### Deep Reasoning Active:")
            context_parts.append(f"- CTM Task ID: {state.ctm_task_id}")
            if 'ctm_insights' in state.prediction:
                context_parts.append(f"- Insights: {state.prediction['ctm_insights'][:200]}...")
            context_parts.append("")

        # Add semantic coherence status
        if state.semantic_coherence:
            context_parts.append("### Semantic Coherence:")
            context_parts.append(f"- Status: {state.semantic_coherence.get('semantic_status', 'unknown')}")
            context_parts.append(f"- Coherence: {state.semantic_coherence.get('coherence_K', 0.0):.2f}")
            context_parts.append("")

        return "\n".join(context_parts)

    def initialize_swarm_agents(self):
        """Initialize AutoGen swarm agents with brain integration"""
        if not Swarm or not AssistantAgent:
            raise RuntimeError("AutoGen not installed. Install with: pip install autogen-agentchat autogen-ext")

        model_client = self._create_model_client()

        # Create cognitive feature agents - one for each of 13 brain features
        # The factory creates all 14 agents: coordinator + 13 feature interpreters
        agent_factory = CognitiveFeatureAgentFactory(model_client)
        cognitive_agents = agent_factory.create_all_agents()
        self.agents.update(cognitive_agents)

        logger.info(f"Created {len(cognitive_agents)} cognitive feature agents")

        # Note: All agents are now created by the factory
        # No need for manual agent definitions - factory handles:
        # - coordinator (orchestrates feature agents)
        # - memory_agent (interprets memory_context)
        # - predictive_agent (interprets predictive_coding)
        # - attention_agent (interprets attention_state)
        # - compositional_agent (interprets composition)
        # - tool_agent (interprets tool_recommendations)
        # - consciousness_agent (interprets consciousness_metrics)
        # - active_inference_agent (interprets active_inference)
        # - meta_learning_agent (interprets meta_learning)
        # - neuromodulation_agent (interprets neuromodulation)
        # - temporal_agent (interprets temporal_memory)
        # - semantic_coherence_agent (interprets semantic_coherence)
        # - ctm_agent (interprets ctm_insights)
        # - infinite_chat_agent (interprets infinite_chat_context)

        logger.info(f"Initialized {len(self.agents)} cognitive feature agents")

    def create_swarm(self):
        """Create AutoGen swarm team with cognitive feature agents"""
        if not self.agents:
            raise RuntimeError("Agents not initialized. Call initialize_swarm_agents() first")

        # Create termination condition - terminate when coordinator is done
        termination = HandoffTermination(target="coordinator") | TextMentionTermination("TASK_COMPLETE")

        # Create swarm team with all cognitive feature agents
        self.swarm = Swarm(
            participants=list(self.agents.values()),
            termination_condition=termination
        )

        logger.info(f"Swarm team created with {len(self.agents)} cognitive feature agents")

    async def process_task(self, task: str) -> Dict[str, Any]:
        """
        Process task using brain + swarm coordination.

        Workflow:
        1. Brain analyzes task (all 13 cognitive features)
        2. Create brain state for agent context
        3. Coordinator agent routes based on brain recommendation
        4. Specialized agents execute with brain guidance
        5. Results fed back to brain for learning

        Args:
            task: Task description

        Returns:
            Dictionary with brain prediction, swarm result, and metadata
        """
        # Step 1: Brain analysis
        logger.info(f"Brain analyzing task: {task}")

        if self.use_unified_brain:
            # Use unified brain service
            response = self.brain_client.predict(task)
            if 'error' in response:
                raise RuntimeError(f"Unified brain error: {response['error']}")
            brain_result = response['result']
        else:
            # Fallback to local brain
            brain_result = self.brain.predict(task)

        # Step 2: Create brain state
        self.current_brain_state = BrainState(
            task=task,
            prediction=brain_result['prediction'],
            memory_context=brain_result.get('memory_context', {}),
            attention_state=brain_result.get('attention_state', {}),
            consciousness_metrics=brain_result.get('consciousness_metrics', {}),
            ctm_task_id=brain_result.get('ctm_task_id'),
            semantic_coherence=brain_result.get('semantic_coherence', {}),
            active_inference=brain_result.get('active_inference', {})
        )

        # Get brain's suggested agent
        suggested_agent = self.current_brain_state.get_suggested_agent()
        logger.info(f"Brain suggests routing to: {suggested_agent}")

        # Step 3: Create context message for swarm
        brain_context = self._create_brain_context_message()

        # Step 4: Run swarm
        if not self.swarm:
            self.create_swarm()

        # Prepare task message with brain context
        task_message = f"""Task: {task}

{brain_context}

Brain recommends routing to: {suggested_agent}

Please coordinate execution of this task."""

        # Run swarm asynchronously with timeout
        logger.info("Swarm executing task...")

        # run_stream returns an async generator, need to collect results
        swarm_messages = []
        try:
            # Add 30-second timeout to prevent hanging
            async with asyncio.timeout(30.0):
                async for message in self.swarm.run_stream(task=task_message):
                    swarm_messages.append(message)
                    logger.info(f"Swarm message: {message}")
        except asyncio.TimeoutError:
            logger.warning("Swarm execution timed out after 30 seconds")
            swarm_messages.append("TIMEOUT: Swarm execution exceeded 30 seconds")
        except Exception as e:
            logger.error(f"Swarm execution failed: {e}")
            swarm_messages.append(f"ERROR: {str(e)}")

        # Format swarm result
        swarm_result = "\n".join([str(msg) for msg in swarm_messages])

        # Step 5: Return combined result
        return {
            'task': task,
            'brain_analysis': brain_result,
            'brain_state': self.current_brain_state.to_dict(),
            'suggested_agent': suggested_agent,
            'swarm_result': swarm_result,
            'swarm_messages': swarm_messages,
            'timestamp': brain_result.get('timestamp')
        }

    async def submit_feedback(
        self,
        task: str,
        success: bool,
        user_rating: float,
        execution_time: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """
        Submit feedback to brain for continuous learning.

        Args:
            task: Task that was executed
            success: Whether task succeeded
            user_rating: User rating (0-1)
            execution_time: Time taken in seconds
            error_message: Error message if failed
        """
        # Convert execution_time to ms
        execution_time_ms = execution_time * 1000 if execution_time else None

        if self.use_unified_brain:
            # Get the brain result for this task
            response = self.brain_client.predict(task)
            if 'error' not in response:
                prediction = response['result']

                # Submit feedback to unified brain
                self.brain_client.submit_feedback(
                    task=task,
                    prediction=prediction,
                    success=success,
                    user_rating=user_rating,
                    execution_time_ms=execution_time_ms
                )
        else:
            # Fallback to local brain
            brain_result = self.brain.predict(task)
            self.brain.submit_feedback(
                task=task,
                prediction=brain_result,
                success=success,
                user_rating=user_rating,
                execution_time_ms=execution_time_ms
            )

        logger.info(f"Feedback submitted to brain: success={success}, rating={user_rating}")

    def get_brain_stats(self) -> Dict[str, Any]:
        """Get brain statistics"""

        if self.use_unified_brain:
            response = self.brain_client.get_statistics()
            if 'error' in response:
                return {'error': response['error']}
            stats = response.get('statistics', {})
        else:
            stats = self.brain.get_statistics()

        # Format for web dashboard compatibility
        return {
            'total_predictions': stats.get('total_predictions', 0),
            'success_rate': stats.get('success_rate', 0.0),
            'average_confidence': stats.get('average_confidence', 0.0)
        }

    def get_swarm_status(self) -> Dict[str, Any]:
        """Get swarm status"""
        return {
            'agents_initialized': len(self.agents),
            'agent_names': list(self.agents.keys()),
            'swarm_created': self.swarm is not None,
            'current_brain_state': self.current_brain_state.to_dict() if self.current_brain_state else None
        }


# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    async def demo():
        # Initialize orchestrator
        # Phase B3: central config (Swarm secret -> env -> .env).
        try:
            from core import config as _cfg
            _or_key = _cfg.openrouter_key()
        except Exception:
            _or_key = os.getenv("OPENROUTER_API_KEY")
        orchestrator = BrainSwarmOrchestrator(
            session_log_dir="data/logs",
            user_id="demo_user",
            openrouter_api_key=_or_key
        )

        # Initialize swarm agents
        orchestrator.initialize_swarm_agents()

        # Process task
        result = await orchestrator.process_task(
            "Deploy Docker container with Redis and health monitoring"
        )

        print("\n=== Brain Analysis ===")
        print(json.dumps(result['brain_analysis']['prediction'], indent=2))

        print("\n=== Suggested Agent ===")
        print(result['suggested_agent'])

        print("\n=== Swarm Result ===")
        print(result['swarm_result'])

        # Submit feedback
        await orchestrator.submit_feedback(
            task="Deploy Docker container with Redis and health monitoring",
            success=True,
            user_rating=0.9,
            execution_time=45.0
        )

        print("\n=== Brain Stats ===")
        print(json.dumps(orchestrator.get_brain_stats(), indent=2))

    asyncio.run(demo())

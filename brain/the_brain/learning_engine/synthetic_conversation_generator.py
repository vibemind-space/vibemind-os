"""
Synthetic Conversation Generator

Generates realistic conversation scenarios for training the quantum checkpoint system.
Creates conversations with:
- Varying context alignment (familiar vs new topics)
- Labeled checkpoints (successful tool calls)
- Action hierarchy (tool_call > agent_response > thinking)
- Realistic timing and error patterns

Author: Tahlamus Brain Team
Date: 2025-10-24
"""

import random
import uuid
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
from core.context_aligned_state import (
    ContextAlignedState,
    ActionMetadata,
    ContextDimensions
)


class SyntheticConversationGenerator:
    """
    Generate synthetic agent conversations for training.

    Scenarios include:
    - File operations (read, write, edit)
    - API calls (GET, POST, debug)
    - DevOps tasks (deploy, configure, monitor)
    - Bug fixing (analyze, test, fix)
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.tool_library = self._build_tool_library()
        self.response_templates = self._build_response_templates()
        self.error_patterns = self._build_error_patterns()

    def _build_tool_library(self) -> Dict[str, Dict]:
        """Tool library with success probabilities and timing"""
        return {
            'read_file': {
                'success_prob': 0.9,
                'avg_duration': 0.5,
                'checkpoint_value': 1.0
            },
            'write_file': {
                'success_prob': 0.85,
                'avg_duration': 1.0,
                'checkpoint_value': 1.0
            },
            'edit_file': {
                'success_prob': 0.8,
                'avg_duration': 1.5,
                'checkpoint_value': 1.0
            },
            'api_get': {
                'success_prob': 0.9,
                'avg_duration': 2.0,
                'checkpoint_value': 1.0
            },
            'api_post': {
                'success_prob': 0.85,
                'avg_duration': 2.5,
                'checkpoint_value': 1.0
            },
            'deploy': {
                'success_prob': 0.7,
                'avg_duration': 5.0,
                'checkpoint_value': 1.0
            },
            'run_tests': {
                'success_prob': 0.75,
                'avg_duration': 3.0,
                'checkpoint_value': 1.0
            },
            'debug': {
                'success_prob': 0.6,
                'avg_duration': 4.0,
                'checkpoint_value': 1.0
            }
        }

    def _build_response_templates(self) -> Dict[str, List[str]]:
        """Agent response templates by context"""
        return {
            'analyzing': [
                "I'm analyzing the situation...",
                "Let me check the current state...",
                "Looking at the error logs...",
                "Examining the code structure..."
            ],
            'planning': [
                "I'll need to perform these steps:",
                "Here's my plan:",
                "The approach should be:",
                "Let me break this down..."
            ],
            'executing': [
                "Executing the operation...",
                "Running the command...",
                "Applying the changes...",
                "Deploying now..."
            ],
            'success': [
                "Operation completed successfully!",
                "That worked!",
                "Successfully applied changes.",
                "Done!"
            ],
            'failure': [
                "That didn't work...",
                "Encountered an error.",
                "Operation failed.",
                "Let me try a different approach..."
            ]
        }

    def _build_error_patterns(self) -> List[Dict]:
        """Common error patterns and recovery strategies"""
        return [
            {
                'error': 'FileNotFoundError',
                'recovery': ['read_file', 'write_file'],
                'retry_prob': 0.8
            },
            {
                'error': 'PermissionError',
                'recovery': ['check_permissions', 'write_file'],
                'retry_prob': 0.7
            },
            {
                'error': 'APIError: 404',
                'recovery': ['api_get', 'check_endpoint'],
                'retry_prob': 0.6
            },
            {
                'error': 'DeploymentFailed',
                'recovery': ['debug', 'fix_config', 'deploy'],
                'retry_prob': 0.5
            }
        ]

    def generate_conversation(
        self,
        task_description: str,
        target_steps: int = 10,
        context_type: str = 'balanced',  # 'new', 'familiar', 'balanced'
        include_errors: bool = True
    ) -> List[ContextAlignedState]:
        """
        Generate a synthetic conversation trace.

        Args:
            task_description: High-level task description
            target_steps: Approximate number of steps
            context_type: 'new' (low context), 'familiar' (high context), 'balanced'
            include_errors: Whether to include failure/retry patterns

        Returns:
            List of ContextAlignedState objects forming a conversation
        """
        conversation = []
        current_time = datetime.now()
        cumulative_time = 0.0

        # Initialize context based on type
        initial_context = self._get_initial_context(context_type)

        # Select task-appropriate tools
        task_tools = self._select_tools_for_task(task_description)

        step = 0
        while step < target_steps:
            # Determine action type (tool call, response, thinking)
            action_type = self._select_action_type(step, target_steps)

            if action_type == 'tool_call':
                state = self._generate_tool_call_state(
                    step, task_tools, include_errors, current_time, cumulative_time, initial_context
                )
            elif action_type == 'agent_response':
                state = self._generate_agent_response_state(
                    step, conversation, current_time, cumulative_time, initial_context
                )
            else:  # thinking
                state = self._generate_thinking_state(
                    step, current_time, cumulative_time, initial_context
                )

            # Calculate context alignment (updates state internal tracking)
            if conversation:
                alignment = state.calculate_context_alignment(conversation)
                # Context dimensions already set in state initialization
                # overall_alignment is computed property, no need to set

            # Update path progress
            state.path_progress = step / target_steps

            # Add to conversation
            conversation.append(state)

            # Update timing
            if state.last_action:
                cumulative_time += state.last_action.duration
                current_time += timedelta(seconds=state.last_action.duration)

            step += 1

        # Mark final state as goal
        conversation[-1].is_goal = True
        conversation[-1].path_progress = 1.0

        return conversation

    def _get_initial_context(self, context_type: str) -> ContextDimensions:
        """Initialize context dimensions based on familiarity"""
        if context_type == 'new':
            return ContextDimensions(
                technical_context=random.uniform(0.0, 0.3),
                user_preference_context=random.uniform(0.0, 0.3),
                task_context=random.uniform(0.0, 0.3),
                conversation_continuity=0.0
            )
        elif context_type == 'familiar':
            return ContextDimensions(
                technical_context=random.uniform(0.7, 1.0),
                user_preference_context=random.uniform(0.7, 1.0),
                task_context=random.uniform(0.7, 1.0),
                conversation_continuity=random.uniform(0.8, 1.0)
            )
        else:  # balanced
            return ContextDimensions(
                technical_context=random.uniform(0.4, 0.7),
                user_preference_context=random.uniform(0.4, 0.7),
                task_context=random.uniform(0.4, 0.7),
                conversation_continuity=random.uniform(0.3, 0.7)
            )

    def _select_tools_for_task(self, task_description: str) -> List[str]:
        """Select appropriate tools based on task description"""
        task_lower = task_description.lower()

        if 'file' in task_lower or 'edit' in task_lower:
            return ['read_file', 'write_file', 'edit_file']
        elif 'api' in task_lower or 'request' in task_lower:
            return ['api_get', 'api_post']
        elif 'deploy' in task_lower or 'configure' in task_lower:
            return ['deploy', 'run_tests', 'debug']
        elif 'bug' in task_lower or 'fix' in task_lower:
            return ['read_file', 'debug', 'edit_file', 'run_tests']
        else:
            # General task
            return list(self.tool_library.keys())

    def _select_action_type(self, step: int, total_steps: int) -> str:
        """
        Select action type based on position in conversation.

        Early steps: more thinking/planning
        Middle steps: more tool calls
        Late steps: verification and responses
        """
        progress = step / total_steps

        if progress < 0.2:
            # Early: 30% tool, 50% response, 20% thinking
            return random.choices(
                ['tool_call', 'agent_response', 'thinking'],
                weights=[30, 50, 20]
            )[0]
        elif progress < 0.8:
            # Middle: 60% tool, 30% response, 10% thinking
            return random.choices(
                ['tool_call', 'agent_response', 'thinking'],
                weights=[60, 30, 10]
            )[0]
        else:
            # Late: 40% tool, 50% response, 10% thinking
            return random.choices(
                ['tool_call', 'agent_response', 'thinking'],
                weights=[40, 50, 10]
            )[0]

    def _generate_tool_call_state(
        self,
        step: int,
        available_tools: List[str],
        include_errors: bool,
        current_time: datetime,
        cumulative_time: float,
        context: ContextDimensions
    ) -> ContextAlignedState:
        """Generate state with tool call action"""
        tool_name = random.choice(available_tools)
        tool_info = self.tool_library[tool_name]

        # Determine success (with some randomness)
        base_success_prob = tool_info['success_prob']
        if not include_errors:
            base_success_prob = 1.0

        success = random.random() < base_success_prob

        # Duration with variance
        duration = tool_info['avg_duration'] * random.uniform(0.8, 1.2)

        # Create action metadata
        action = ActionMetadata(
            action_type='tool_call',
            action_name=tool_name,
            success=success,
            duration=duration,
            result=f"Executed {tool_name}" if success else None,
            error=random.choice([ep['error'] for ep in self.error_patterns]) if not success else None
        )

        # Create state
        state = ContextAlignedState(
            state_id=str(uuid.uuid4()),
            step_count=step,
            timestamp=current_time,
            state_summary=f"Tool call: {tool_name}",
            context=context,
            last_action=action,
            cumulative_time=cumulative_time + duration
        )

        # Mark as checkpoint if successful tool call
        if success:
            state.mark_as_checkpoint(
                checkpoint_type='tool_success',
                reliability_score=random.uniform(0.8, 1.0)
            )

        return state

    def _generate_agent_response_state(
        self,
        step: int,
        conversation: List[ContextAlignedState],
        current_time: datetime,
        cumulative_time: float,
        context: ContextDimensions
    ) -> ContextAlignedState:
        """Generate state with agent response action"""
        # Select appropriate response template
        if not conversation:
            response_type = 'planning'
        elif conversation[-1].last_action and conversation[-1].last_action.success:
            response_type = 'success'
        elif conversation[-1].last_action and not conversation[-1].last_action.success:
            response_type = 'failure'
        else:
            response_type = random.choice(['analyzing', 'planning', 'executing'])

        response_text = random.choice(self.response_templates[response_type])

        # Duration (response time)
        duration = random.uniform(0.5, 2.0)

        # Create action metadata
        action = ActionMetadata(
            action_type='agent_response',
            action_name='generate_response',
            success=True,
            duration=duration,
            result=response_text
        )

        # Create state
        state = ContextAlignedState(
            state_id=str(uuid.uuid4()),
            step_count=step,
            timestamp=current_time,
            state_summary=f"Agent: {response_text[:50]}...",
            context=context,
            last_action=action,
            cumulative_time=cumulative_time + duration
        )

        # Agent responses can be checkpoints if they represent semantic progress
        if response_type in ['success', 'planning']:
            state.mark_as_checkpoint(
                checkpoint_type='semantic_progress',
                reliability_score=random.uniform(0.5, 0.8)
            )

        return state

    def _generate_thinking_state(
        self,
        step: int,
        current_time: datetime,
        cumulative_time: float,
        context: ContextDimensions
    ) -> ContextAlignedState:
        """Generate state with thinking/waiting action"""
        # Duration (thinking time)
        duration = random.uniform(0.2, 1.0)

        # Create action metadata
        action = ActionMetadata(
            action_type='thinking',
            action_name='evaluate_options',
            success=True,
            duration=duration
        )

        # Create state
        state = ContextAlignedState(
            state_id=str(uuid.uuid4()),
            step_count=step,
            timestamp=current_time,
            state_summary="Thinking...",
            context=context,
            last_action=action,
            cumulative_time=cumulative_time + duration
        )

        # Thinking states are never checkpoints
        return state

    def generate_batch(
        self,
        num_conversations: int = 50,
        context_distribution: Dict[str, float] = None
    ) -> List[List[ContextAlignedState]]:
        """
        Generate a batch of synthetic conversations.

        Args:
            num_conversations: Number of conversations to generate
            context_distribution: Distribution of context types
                                 e.g., {'new': 0.3, 'familiar': 0.3, 'balanced': 0.4}

        Returns:
            List of conversation traces
        """
        if context_distribution is None:
            context_distribution = {'new': 0.3, 'familiar': 0.3, 'balanced': 0.4}

        # Task templates
        tasks = [
            "Fix bug in authentication module",
            "Deploy new API endpoint",
            "Update configuration file",
            "Read and analyze error logs",
            "Write unit tests for feature X",
            "Debug failing CI/CD pipeline",
            "Migrate database schema",
            "Optimize query performance",
            "Set up monitoring dashboard",
            "Refactor legacy code module"
        ]

        conversations = []
        for i in range(num_conversations):
            # Select context type based on distribution
            context_type = random.choices(
                list(context_distribution.keys()),
                weights=list(context_distribution.values())
            )[0]

            # Select task
            task = random.choice(tasks)

            # Generate conversation
            target_steps = random.randint(5, 15)
            conversation = self.generate_conversation(
                task_description=task,
                target_steps=target_steps,
                context_type=context_type,
                include_errors=True
            )

            conversations.append(conversation)

        return conversations


# Utility functions

def save_conversations(
    conversations: List[List[ContextAlignedState]],
    output_path: str
):
    """Save conversations to JSON file"""
    import json

    data = []
    for conv in conversations:
        conv_data = [state.to_dict() for state in conv]
        data.append(conv_data)

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def load_conversations(input_path: str) -> List[List[ContextAlignedState]]:
    """Load conversations from JSON file"""
    import json

    with open(input_path, 'r') as f:
        data = json.load(f)

    conversations = []
    for conv_data in data:
        conv = [ContextAlignedState.from_dict(state_dict) for state_dict in conv_data]
        conversations.append(conv)

    return conversations


if __name__ == '__main__':
    # Demo: Generate 10 synthetic conversations
    generator = SyntheticConversationGenerator(seed=42)

    print("Generating 10 synthetic conversations...\n")

    conversations = generator.generate_batch(num_conversations=10)

    for i, conv in enumerate(conversations):
        checkpoints = [s for s in conv if s.is_checkpoint]
        print(f"Conversation {i+1}:")
        print(f"  Steps: {len(conv)}")
        print(f"  Checkpoints: {len(checkpoints)}")
        print(f"  Total time: {conv[-1].cumulative_time:.1f}s")
        print(f"  Context alignment: {conv[-1].context.overall_alignment:.2f}")
        print(f"  Tool calls: {sum(1 for s in conv if s.last_action and s.last_action.action_type == 'tool_call')}")
        print()

    # Save to file
    save_conversations(conversations, 'data/synthetic_conversations_demo.json')
    print("Saved to: data/synthetic_conversations_demo.json")

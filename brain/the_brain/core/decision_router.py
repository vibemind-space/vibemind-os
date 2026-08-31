"""
Decision Router (Phase 4 - Layer 3)

Concept from logical_brain/routed_brain.py:
Route predictions to actionable decisions with context from all layers.

Original PyTorch implementation:
```python
class ModuleRouter(nn.Module):
    def route_to_modules(self, brain_output, sensory_routing):
        # Combine brain output with sensory context
        combined = torch.cat([brain_output, sensory_routing], dim=-1)

        # Route to output modules
        module_weights = self.output_router(combined)

        return module_weights
```

Our NumPy adaptation:
- Combines prediction from Layer 2 (PathPlanner) with routing from Layer 1 (Features)
- Uses MultiTargetDecisionRouter (Phase 3) to generate weighted decisions
- Adds context-aware reasoning
- Returns actionable interventions with full provenance
"""

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from core.multi_target_router import MultiTargetDecisionRouter, MultiTargetDecision
from core.task_feature_router import RoutingState

# Import tool call generator (Phase 2 integration)
try:
    from core.tool_call_generator import ToolCallGenerator
    TOOL_CALL_GENERATOR_AVAILABLE = True
except ImportError:
    TOOL_CALL_GENERATOR_AVAILABLE = False
    print("[WARNING] ToolCallGenerator not available - executable tool calls disabled")


@dataclass
class ActionableDecision:
    """
    Final actionable decision with full context from all 3 layers
    """
    # Layer 1 context
    task_features: Dict
    layer1_routing: Dict

    # Layer 2 context
    predicted_sequence: List[str]
    confidence: float
    success_probability: float
    dominant_modalities: List[str]

    # Layer 3 output
    multi_target_decision: Dict
    processing_mode: str
    reasoning_chain: List[str]  # Step-by-step reasoning from all layers

    # NEW: Executable tool calls (when intervention = 'execute')
    executable_tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'layer1_context': {
                'task_features': self.task_features,
                'routing': self.layer1_routing
            },
            'layer2_context': {
                'predicted_sequence': self.predicted_sequence,
                'confidence': float(self.confidence),
                'success_probability': float(self.success_probability),
                'dominant_modalities': self.dominant_modalities
            },
            'layer3_output': {
                'multi_target_decision': self.multi_target_decision,
                'processing_mode': self.processing_mode,
                'reasoning_chain': self.reasoning_chain
            }
        }

        # Include executable tool calls if present
        if self.executable_tool_calls is not None:
            result['executable_tool_calls'] = self.executable_tool_calls

        return result


class DecisionRouter:
    """
    Layer 3: Routes predictions to actionable decisions

    Combines information from:
    - Layer 1: Task features and initial routing
    - Layer 2: Path planning and brain state
    - Multi-target routing (Phase 3): Weighted intervention decisions

    Produces final actionable decision with full reasoning chain.
    """

    def __init__(
        self,
        num_modalities: int = 10,
        intervention_types: Optional[List[str]] = None,
        seed: int = 42
    ):
        """
        Initialize decision router

        Args:
            num_modalities: Number of brain modalities
            intervention_types: List of intervention types
            seed: Random seed
        """
        self.rng = np.random.RandomState(seed)

        # Initialize multi-target router (Phase 3)
        if intervention_types is None:
            # NEW: Added 'execute' as 5th intervention type
            intervention_types = ['suggest', 'retry', 'wait', 'terminate', 'execute']

        self.intervention_types = intervention_types
        self.multi_target_router = MultiTargetDecisionRouter(
            num_modalities=num_modalities,
            intervention_types=intervention_types,
            seed=seed
        )

        # Initialize tool call generator (Phase 2 integration)
        self.tool_call_generator = None
        if TOOL_CALL_GENERATOR_AVAILABLE:
            try:
                self.tool_call_generator = ToolCallGenerator()
                print("[DecisionRouter] Tool call generator initialized - executable tool calls enabled")
            except Exception as e:
                print(f"[DecisionRouter] Failed to initialize tool call generator: {e}")

        # Statistics
        self.total_decisions = 0
        self.mode_counts = {'urgent': 0, 'analytical': 0, 'creative': 0, 'routine': 0}
        self.tool_calls_generated = 0

    def route_to_action(
        self,
        layer1_state: RoutingState,
        layer2_prediction: Dict,
        brain_gates: Optional[np.ndarray] = None,
        per_modality_pes: Optional[Dict[str, float]] = None,
        memory_context: Optional[Dict] = None,  # Memory context
        task_text: Optional[str] = None  # NEW: Original task text for tool parameter inference
    ) -> ActionableDecision:
        """
        Route Layer 1 + Layer 2 information to final actionable decision

        Args:
            layer1_state: RoutingState from TaskFeatureRouter
            layer2_prediction: Prediction dict from ConversationPathPlanner
            brain_gates: Optional brain gate distribution [10]
            per_modality_pes: Optional per-modality prediction errors
            memory_context: Optional memory context (working + episodic)
            task_text: Optional original task text for ToolCallGenerator parameter inference

        Returns:
            ActionableDecision with full context and reasoning
        """
        # Extract Layer 2 information
        predicted_sequence = layer2_prediction.get('predicted_sequence', [])
        confidence = layer2_prediction.get('confidence', 0.5)
        success_probability = layer2_prediction.get('success_probability', 0.5)
        dominant_modalities = layer2_prediction.get('dominant_modalities', [])

        # If brain gates not provided, use Layer 1 routing weights
        if brain_gates is None:
            brain_gates = layer1_state.routing_weights

        # Build reasoning chain
        reasoning_chain = []

        # Layer 1 reasoning
        reasoning_chain.append(
            f"L1: Task classified as '{layer1_state.features.task_type}' "
            f"(complexity={layer1_state.features.complexity:.2f}, "
            f"urgency={layer1_state.features.urgency:.2f})"
        )

        reasoning_chain.append(
            f"L1: Routing to brain areas: {', '.join(layer1_state.dominant_areas[:3])}"
        )

        reasoning_chain.append(
            f"L1: Processing mode selected: {layer1_state.processing_mode}"
        )

        # Layer 2 reasoning
        reasoning_chain.append(
            f"L2: Predicted sequence: {' -> '.join(predicted_sequence[:3])}"
            + (" -> ..." if len(predicted_sequence) > 3 else "")
        )

        reasoning_chain.append(
            f"L2: Confidence={confidence:.1%}, Success probability={success_probability:.1%}"
        )

        reasoning_chain.append(
            f"L2: Dominant brain modalities: {', '.join(dominant_modalities[:3])}"
        )

        # Memory context reasoning (NEW)
        if memory_context:
            working_mem = memory_context.get('working_memory', {})
            success_rate = working_mem.get('recent_success_rate', 0.5)
            decision_patterns = working_mem.get('decision_patterns', {})

            if decision_patterns:
                top_decision = max(decision_patterns.items(), key=lambda x: x[1])
                reasoning_chain.append(
                    f"Memory: Recent pattern shows {top_decision[1]:.0%} '{top_decision[0]}' decisions "
                    f"(success rate: {success_rate:.0%})"
                )

        # Compute multi-target decision (Layer 3)
        decision = self.multi_target_router.route_decision(
            gates=brain_gates,
            confidence=confidence,
            dominant_modalities=dominant_modalities,
            per_modality_pes=per_modality_pes
        )

        # Layer 3 reasoning
        primary = decision.primary
        reasoning_chain.append(
            f"L3: Primary intervention: {primary.intervention_type} "
            f"(weight={primary.weight:.1%}, confidence={primary.confidence:.1%})"
        )

        reasoning_chain.append(
            f"L3: Reasoning: {primary.reasoning}"
        )

        # Add alternative options
        if decision.alternatives:
            alt_str = ', '.join([
                f"{alt.intervention_type}({alt.weight:.0%})"
                for alt in decision.alternatives[:2]
            ])
            reasoning_chain.append(f"L3: Alternatives: {alt_str}")

        # Context-aware adjustments based on processing mode
        adjusted_reasoning = self._adjust_for_processing_mode(
            decision,
            layer1_state.processing_mode,
            layer1_state.features
        )
        if adjusted_reasoning:
            reasoning_chain.append(f"L3: Mode adjustment: {adjusted_reasoning}")

        # NEW: Generate executable tool calls if intervention is 'execute'
        executable_tool_calls = None
        if decision.primary.intervention_type == 'execute' and predicted_sequence:
            executable_tool_calls = self._generate_executable_tool_calls(
                predicted_sequence,
                layer1_state.features.task_type,
                confidence,
                task_text=task_text or "",  # NEW: Pass task text for parameter inference
                task_features=layer1_state.features.to_dict()  # NEW: Pass task features
            )
            reasoning_chain.append(
                f"L3: Generated {len(executable_tool_calls)} executable tool calls"
            )

        # Create actionable decision
        actionable = ActionableDecision(
            task_features=layer1_state.features.to_dict(),
            layer1_routing=layer1_state.to_dict(),
            predicted_sequence=predicted_sequence,
            confidence=confidence,
            success_probability=success_probability,
            dominant_modalities=dominant_modalities,
            multi_target_decision=decision.to_dict(),
            processing_mode=layer1_state.processing_mode,
            reasoning_chain=reasoning_chain,
            executable_tool_calls=executable_tool_calls
        )

        # Update statistics
        self.total_decisions += 1
        self.mode_counts[layer1_state.processing_mode] += 1

        return actionable

    def _generate_executable_tool_calls(
        self,
        predicted_sequence: List[str],
        task_type: str,
        confidence: float,
        task_text: str = "",
        task_features: Dict = None
    ) -> List[Dict[str, Any]]:
        """
        Generate executable tool calls from predicted sequence

        NOW ENHANCED WITH TOOL_CALL_GENERATOR (Phase 2):
        - Uses ToolCallGenerator for intelligent parameter inference
        - Falls back to legacy method if generator unavailable
        - Generates executable tool calls with inferred parameters

        Args:
            predicted_sequence: List of tool/action names from Layer 2
            task_type: Task type classification
            confidence: Confidence in the prediction
            task_text: Original task text for parameter inference
            task_features: Task features dict for context

        Returns:
            List of executable tool call dictionaries with parameters
        """
        tool_calls = []

        # Use ToolCallGenerator if available (NEW - Phase 2)
        if self.tool_call_generator and task_text:
            for step_num, tool_name in enumerate(predicted_sequence, 1):
                # Map tool name to intervention type
                intervention_type = self._map_tool_to_intervention(tool_name)

                # Generate tool call using ToolCallGenerator
                generated_call = self.tool_call_generator.generate_tool_call(
                    intervention_type=intervention_type,
                    task=task_text,
                    task_features=task_features,
                    min_confidence=0.4  # Lower threshold for fallback
                )

                if generated_call:
                    # Convert ToolCall object to dictionary
                    tool_call = {
                        'step': step_num,
                        'tool': generated_call.tool_name,
                        'tool_type': generated_call.tool_type.value,
                        'confidence': float(generated_call.confidence),
                        'task_type': task_type,
                        'parameters': generated_call.parameters,
                        'reasoning': generated_call.reasoning,
                        'fallback_tools': generated_call.fallback_tools,
                        'metadata': {
                            'required': step_num == 1,
                            'can_skip': generated_call.confidence < 0.5 and step_num > 1,
                            'retry_on_error': True,
                            'timeout_seconds': 300 if 'deploy' in generated_call.tool_name else 60,
                            'intervention_source': generated_call.intervention_source
                        }
                    }
                    tool_calls.append(tool_call)
                    self.tool_calls_generated += 1
                else:
                    # Fallback to legacy method for this tool
                    legacy_call = self._generate_legacy_tool_call(tool_name, task_type, step_num, confidence)
                    tool_calls.append(legacy_call)
        else:
            # Legacy method (backward compatibility)
            for step_num, tool_name in enumerate(predicted_sequence, 1):
                tool_call = self._generate_legacy_tool_call(tool_name, task_type, step_num, confidence)
                tool_calls.append(tool_call)

        return tool_calls

    def _generate_legacy_tool_call(
        self,
        tool_name: str,
        task_type: str,
        step_num: int,
        confidence: float
    ) -> Dict[str, Any]:
        """Legacy tool call generation (backward compatibility)"""
        tool_call = {
            'step': step_num,
            'tool': tool_name,
            'confidence': float(confidence),
            'task_type': task_type,
            'parameters': {}
        }

        # Add task-type specific parameters
        params = self._infer_tool_parameters(tool_name, task_type, step_num)
        if params:
            tool_call['parameters'] = params

        # Add execution metadata
        tool_call['metadata'] = {
            'required': step_num == 1,
            'can_skip': confidence < 0.5 and step_num > 1,
            'retry_on_error': tool_name in ['build', 'deploy', 'test', 'commit', 'push'],
            'timeout_seconds': 300 if tool_name in ['build', 'deploy'] else 60
        }

        return tool_call

    def _map_tool_to_intervention(self, tool_name: str) -> str:
        """
        Map tool name to intervention type for ToolCallGenerator

        Args:
            tool_name: Name of the tool

        Returns:
            Intervention type (suggest/retry/wait/execute)
        """
        tool_lower = tool_name.lower()

        # Retry interventions
        if any(word in tool_lower for word in ['retry', 'redo', 'again', 'fix']):
            return 'retry'

        # Wait interventions
        if any(word in tool_lower for word in ['wait', 'poll', 'check', 'monitor']):
            return 'wait'

        # Suggest interventions (most common)
        if any(word in tool_lower for word in ['deploy', 'build', 'commit', 'apply', 'run']):
            return 'suggest'

        # Default to execute for concrete actions
        return 'execute'

    def _infer_tool_parameters(
        self,
        tool_name: str,
        task_type: str,
        step_num: int
    ) -> Dict[str, Any]:
        """
        Infer parameters for tool calls based on context

        Args:
            tool_name: Name of the tool
            task_type: Type of task
            step_num: Step number in sequence

        Returns:
            Dictionary of inferred parameters
        """
        params = {}

        # Git-related tools
        if task_type == 'github' or task_type == 'git':
            if tool_name == 'git_add' or tool_name == 'add':
                params['files'] = '.'  # Add all files by default
                params['options'] = []
            elif tool_name == 'git_commit' or tool_name == 'commit':
                params['message'] = f'Auto-commit: {task_type} task'
                params['options'] = []
            elif tool_name == 'git_push' or tool_name == 'push':
                params['remote'] = 'origin'
                params['branch'] = 'main'  # Could be inferred from git status
            elif tool_name == 'git_status' or tool_name == 'status':
                params['options'] = ['--short']

        # Docker-related tools
        elif task_type == 'docker':
            if tool_name == 'docker_build' or tool_name == 'build' or tool_name == 'build_image':
                params['dockerfile'] = 'Dockerfile'
                params['tag'] = 'latest'
                params['context'] = '.'
            elif tool_name == 'docker_run' or tool_name == 'deploy':
                params['image'] = 'latest'
                params['detach'] = True
                params['ports'] = []
            elif tool_name == 'docker_ps' or tool_name == 'list':
                params['all'] = False
            elif tool_name == 'test' or tool_name == 'test_container':
                params['command'] = 'echo "Test passed"'

        # Memory/monitoring tools
        elif task_type == 'memory':
            if tool_name == 'check' or tool_name == 'monitor_memory':
                params['format'] = 'human-readable'
                params['interval'] = 1
            elif tool_name == 'complete' or tool_name == 'report_status':
                params['format'] = 'json'

        # Filesystem tools
        elif task_type == 'filesystem' or task_type == 'search':
            if tool_name == 'find' or tool_name == 'search':
                params['path'] = '.'
                params['type'] = 'f'  # files
            elif tool_name == 'list' or tool_name == 'ls':
                params['long_format'] = True
                params['all'] = False

        # Playwright/browser tools
        elif task_type == 'playwright':
            if tool_name == 'navigate' or tool_name == 'goto':
                params['url'] = 'about:blank'  # Would need to be filled in
                params['wait_until'] = 'networkidle'
            elif tool_name == 'screenshot' or tool_name == 'capture':
                params['path'] = 'screenshot.png'
                params['full_page'] = True
            elif tool_name == 'complete' or tool_name == 'scrape':
                params['selector'] = 'body'
                params['format'] = 'text'

        # Generic fallback
        else:
            if tool_name == 'complete':
                params['status'] = 'success'

        return params

    def _adjust_for_processing_mode(
        self,
        decision: MultiTargetDecision,
        processing_mode: str,
        features
    ) -> Optional[str]:
        """
        Generate context-aware reasoning based on processing mode

        Args:
            decision: Multi-target decision
            processing_mode: Processing mode (urgent/analytical/creative/routine)
            features: Task features

        Returns:
            Additional reasoning string or None
        """
        if processing_mode == 'urgent':
            # Urgent mode: bias toward immediate action
            if decision.primary.intervention_type == 'wait':
                return "Urgent mode: Consider 'suggest' or 'retry' over 'wait'"
            else:
                return "Urgent mode: Prioritizing immediate action"

        elif processing_mode == 'analytical':
            # Analytical mode: emphasize careful planning
            if decision.primary.intervention_type == 'suggest' and features.complexity > 0.7:
                return "Analytical mode: Complex task requires careful step-by-step guidance"
            else:
                return "Analytical mode: Thorough analysis recommended"

        elif processing_mode == 'routine':
            # Routine mode: straightforward execution
            if decision.primary.intervention_type == 'suggest':
                return "Routine mode: Standard procedure, direct suggestion appropriate"
            else:
                return "Routine mode: Simple task, minimal intervention needed"

        elif processing_mode == 'creative':
            # Creative mode: allow exploration
            if decision.primary.weight < 0.5:
                return "Creative mode: Multiple valid approaches, explore alternatives"
            else:
                return "Creative mode: Flexible approach encouraged"

        return None

    def get_statistics(self) -> Dict:
        """Get routing statistics"""
        return {
            'total_decisions': self.total_decisions,
            'mode_counts': self.mode_counts.copy(),
            'mode_distribution': {
                mode: count / self.total_decisions if self.total_decisions > 0 else 0.0
                for mode, count in self.mode_counts.items()
            },
            'multi_target_stats': self.multi_target_router.get_statistics()
        }

    def reset_statistics(self):
        """Reset decision statistics"""
        self.total_decisions = 0
        self.mode_counts = {'urgent': 0, 'analytical': 0, 'creative': 0, 'routine': 0}
        self.multi_target_router.reset_statistics()

    def __repr__(self):
        return (
            f"DecisionRouter("
            f"interventions={len(self.multi_target_router.intervention_types)}, "
            f"decisions={self.total_decisions})"
        )


if __name__ == "__main__":
    from core.task_feature_router import TaskFeatureRouter

    print("=" * 70)
    print("TESTING DECISION ROUTER (Phase 4 - Layer 3)")
    print("=" * 70)
    print()

    # Initialize Layer 1 and Layer 3
    layer1 = TaskFeatureRouter(seed=42)
    layer3 = DecisionRouter(seed=42)

    print(f"Layer 1: {layer1}")
    print(f"Layer 3: {layer3}")
    print()

    # Test scenario
    test_cases = [
        {
            'task': "Check memory status urgently",
            'layer2_prediction': {
                'predicted_sequence': ['monitor_memory', 'check_logs', 'report_status'],
                'confidence': 0.85,
                'success_probability': 0.92,
                'dominant_modalities': ['tool_trace', 'temporal_pattern']
            }
        },
        {
            'task': "Analyze this complex architecture and refactor",
            'layer2_prediction': {
                'predicted_sequence': ['read_code', 'understand_structure', 'identify_issues', 'refactor'],
                'confidence': 0.45,
                'success_probability': 0.67,
                'dominant_modalities': ['tool_trace', 'temporal_pattern', 'error_signal']
            }
        },
        {
            'task': "Deploy with Docker immediately",
            'layer2_prediction': {
                'predicted_sequence': ['build_image', 'test_container', 'deploy'],
                'confidence': 0.70,
                'success_probability': 0.80,
                'dominant_modalities': ['tool_trace', 'error_signal', 'threat']
            }
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}: \"{test_case['task']}\"")
        print("=" * 70)

        # Layer 1: Route task features
        layer1_state = layer1.route_task(test_case['task'])

        # Layer 3: Route to action
        decision = layer3.route_to_action(
            layer1_state=layer1_state,
            layer2_prediction=test_case['layer2_prediction']
        )

        # Display decision
        print(f"\nPROCESSING MODE: {decision.processing_mode}")
        print(f"\nREASONING CHAIN:")
        for j, step in enumerate(decision.reasoning_chain, 1):
            print(f"  {j}. {step}")

        print(f"\nFINAL DECISION:")
        mtd = decision.multi_target_decision
        primary = mtd['primary']
        print(f"  Primary: {primary['type']} (weight={primary['weight']:.1%})")
        print(f"  Reasoning: {primary['reasoning']}")

        print(f"\n  Alternatives:")
        for alt in mtd['alternatives'][:3]:
            bar = '#' * int(alt['weight'] * 40)
            print(f"    {alt['type']:12s} {alt['weight']:.1%} {bar}")

        print()
        print("-" * 70)
        print()

    # Show statistics
    print("=" * 70)
    print("ROUTING STATISTICS")
    print("=" * 70)
    stats = layer3.get_statistics()
    print(f"Total decisions: {stats['total_decisions']}")
    print()
    print("Processing mode distribution:")
    for mode, prob in sorted(stats['mode_distribution'].items(),
                            key=lambda x: x[1], reverse=True):
        if prob > 0:
            bar = '#' * int(prob * 50)
            print(f"  {mode:12s} {prob:.1%} {bar}")

    print()
    print("=" * 70)
    print("LAYER 3 TEST COMPLETE!")
    print("=" * 70)

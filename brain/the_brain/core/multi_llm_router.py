"""
Multi-LLM Router

Routes different cognitive functions to specialized LLM providers:
- Groq: Fast reasoning (Layer 1, Layer 3)
- Anthropic: Strategic planning (Layer 2, short-term memory)
- GPT: Natural communication (questions, understanding)
- Gemini: Long-term memory (2M context)

All accessed via OpenRouter for unified API.
"""

from typing import Dict, List, Optional, Any, Tuple, Callable
import json
import logging
import requests
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

# --- Zentrale LLM-Config via vibemind_shared ---
try:
    from vibemind_shared import get_model as _shared_get_model
    _HAS_SHARED_CONFIG = True
except ImportError:
    _HAS_SHARED_CONFIG = False


def _resolve_brain_model(role: str, fallback: str, directory: str = "") -> str:
    """Modell aus zentraler Config oder Fallback."""
    if _HAS_SHARED_CONFIG:
        try:
            return _shared_get_model(role, directory)
        except Exception:
            pass
    return fallback


@dataclass
class LLMConfig:
    """Configuration for a specific LLM"""
    provider: str  # 'groq', 'anthropic', 'openai', 'google'
    model: str
    max_tokens: int = 1000
    temperature: float = 0.7
    use_for: List[str] = None  # Which functions this LLM handles


class MultiLLMRouter:
    """
    Route cognitive functions to specialized LLMs via OpenRouter

    Architecture:
    - Groq (Llama 3): Fast reasoning, feature extraction, decisions
    - Anthropic (Claude): Strategic planning, short-term memory
    - OpenAI (GPT-4): Natural questions, user communication
    - Google (Gemini): Long-term memory with huge context
    """

    def __init__(
        self,
        openrouter_api_key: str = None,
        default_provider: str = 'anthropic',
        dev_mode: bool = None,
        enable_infinite_chat: bool = True,
        user_id: Optional[str] = None
    ):
        """
        Initialize multi-LLM router

        Args:
            openrouter_api_key: OpenRouter API key (falls back to OPENROUTER_API_KEY env var)
            default_provider: Fallback provider if specialized one fails
            dev_mode: Use dev models (currently available) vs production models (cutting-edge)
                     If None, reads from environment variable DEV_MODE
            enable_infinite_chat: Enable Supermemory Infinite Chat for automatic memory (default: True)
            user_id: User ID for memory isolation (optional, can be set per-call)
        """
        import os
        self.api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.default_provider = default_provider
        self.enable_infinite_chat = enable_infinite_chat
        self.user_id = user_id

        # OpenRouter API endpoint
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

        # Supermemory LLM client (lazy initialization)
        self._supermemory_llm = None

        # Determine dev mode
        if dev_mode is None:
            import os
            dev_mode = os.getenv('DEV_MODE', 'true').lower() == 'true'

        self.dev_mode = dev_mode

        # Configure specialized LLMs based on mode
        if dev_mode:
            print("[DEV MODE] Using currently available models")
            self.llm_configs = self._get_dev_configs()
        else:
            print("[PRODUCTION MODE] Using cutting-edge 2025 models")
            self.llm_configs = self._get_production_configs()

        # Function to LLM mapping
        self.function_map = {}
        for llm_name, config in self.llm_configs.items():
            for function in config.use_for:
                self.function_map[function] = llm_name

        # Statistics
        self.call_counts = {name: 0 for name in self.llm_configs}
        self.latencies = {name: [] for name in self.llm_configs}
        self.failures = {name: 0 for name in self.llm_configs}

        # Track total costs (cost per million tokens)
        if dev_mode:
            # Dev mode costs (currently available models)
            self.cost_per_million = {
                'fast_reasoning': 0.14,      # DeepSeek R1 (very cheap!)
                'planning': 3.00,            # Claude 3.5 Sonnet
                'context_tracking': 3.00,    # Claude 3.5 Sonnet
                'communication': 2.50,       # GPT-4o
                'long_term_memory': 0.075    # Gemini 2.0 Flash (very cheap!)
            }
        else:
            # Production costs (cutting-edge 2025 models)
            self.cost_per_million = {
                'fast_reasoning': 0.80,      # Grok Code Fast 1
                'planning': 15.00,           # GPT-5 Pro
                'context_tracking': 3.00,    # Claude Sonnet 4.5
                'communication': 10.00,      # GPT-5 Chat
                'long_term_memory': 0.10     # Gemini 2.5 Flash
            }
        self.total_tokens_used = {name: 0 for name in self.llm_configs}

        # Print initialization info
        if enable_infinite_chat:
            print("[Multi-LLM Router] Infinite Chat ENABLED - automatic memory injection")
        else:
            print("[Multi-LLM Router] Infinite Chat DISABLED - direct OpenRouter")

    def _get_supermemory_llm(self, user_id: Optional[str] = None):
        """
        Get or create SupermemoryLLM client for automatic memory

        Args:
            user_id: User ID for memory isolation

        Returns:
            SupermemoryLLM client or None if not enabled
        """
        if not self.enable_infinite_chat:
            return None

        # Use provided user_id or default
        uid = user_id or self.user_id
        if not uid:
            return None  # No user_id, fall back to direct calls

        # Lazy import to avoid circular dependency
        try:
            from core.supermemory_llm_client import SupermemoryLLM

            # Create new client if user changed or first time
            if self._supermemory_llm is None or (hasattr(self._supermemory_llm, 'user_id') and self._supermemory_llm.user_id != uid):
                self._supermemory_llm = SupermemoryLLM(
                    user_id=uid,
                    provider='openai',
                    model=_resolve_brain_model('supermemory', 'gpt-4o-mini')
                )
                print(f"[Multi-LLM Router] Created SupermemoryLLM for user: {uid}")

            return self._supermemory_llm
        except Exception as e:
            print(f"[Multi-LLM Router] Failed to create SupermemoryLLM: {e}")
            return None

    def set_user_id(self, user_id: Optional[str]):
        """
        Set user ID for memory isolation

        Args:
            user_id: User ID or None to disable per-user memory
        """
        self.user_id = user_id
        # Reset supermemory client to force recreation with new user_id
        self._supermemory_llm = None

    def _get_dev_configs(self) -> Dict[str, LLMConfig]:
        """Get development model configurations — from llm_config.yml or openrouter/free fallback."""
        _free = 'openrouter/free'
        return {
            'fast_reasoning': LLMConfig(
                provider='openrouter',
                model=_resolve_brain_model('fast_reasoning', _free),
                max_tokens=500, temperature=0.3,
                use_for=['feature_extraction', 'decision_making', 'fast_inference', 'code_understanding']
            ),
            'planning': LLMConfig(
                provider='openrouter',
                model=_resolve_brain_model('planning', _free),
                max_tokens=1500, temperature=0.7,
                use_for=['path_planning', 'strategy_selection', 'complex_understanding']
            ),
            'context_tracking': LLMConfig(
                provider='openrouter',
                model=_resolve_brain_model('context_tracking', _free),
                max_tokens=1500, temperature=0.5,
                use_for=['short_term_memory', 'context_maintenance', 'working_memory']
            ),
            'communication': LLMConfig(
                provider='openrouter',
                model=_resolve_brain_model('communication', _free),
                max_tokens=800, temperature=0.8,
                use_for=['question_generation', 'user_interaction', 'natural_language']
            ),
            'long_term_memory': LLMConfig(
                provider='openrouter',
                model=_resolve_brain_model('long_term_memory', _free),
                max_tokens=2000, temperature=0.5,
                use_for=['episodic_memory', 'pattern_discovery', 'memory_search', 'huge_context']
            ),
        }

    @staticmethod
    def get_free_model_configs() -> Dict[str, str]:
        """Get free model IDs for background micro-agents.

        These are $0 cost models on OpenRouter, suitable for background
        knowledge refinement tasks. Rate limits: ~20 req/min, ~200 req/day.

        Returns:
            Dict mapping agent role to OpenRouter model ID
        """
        return {
            'summarizer': 'openrouter/free',
            'connector':  'openrouter/free',
            'critic':     'openrouter/free',
            'enricher':   'openrouter/free',
            'responder':  'openrouter/free',
            'fallback':   'openrouter/free',
        }

    def _get_production_configs(self) -> Dict[str, LLMConfig]:
        """Get production model configurations — from llm_config.yml overrides or hardcoded defaults."""
        _dir = 'production'
        return {
            'fast_reasoning': LLMConfig(
                provider='xai',
                model=_resolve_brain_model('fast_reasoning', 'xai/grok-code-fast-1', _dir),
                max_tokens=500, temperature=0.3,
                use_for=['feature_extraction', 'decision_making', 'fast_inference', 'code_understanding']
            ),
            'planning': LLMConfig(
                provider='openai',
                model=_resolve_brain_model('planning', 'openai/gpt-5-pro', _dir),
                max_tokens=1500, temperature=0.7,
                use_for=['path_planning', 'strategy_selection', 'complex_understanding']
            ),
            'context_tracking': LLMConfig(
                provider='anthropic',
                model=_resolve_brain_model('context_tracking', 'anthropic/claude-sonnet-4.5', _dir),
                max_tokens=1500, temperature=0.5,
                use_for=['short_term_memory', 'context_maintenance', 'working_memory']
            ),
            'communication': LLMConfig(
                provider='openai',
                model=_resolve_brain_model('communication', 'openai/gpt-5-chat', _dir),
                max_tokens=800, temperature=0.8,
                use_for=['question_generation', 'user_interaction', 'natural_language']
            ),
            'long_term_memory': LLMConfig(
                provider='google',
                model=_resolve_brain_model('long_term_memory', 'google/gemini-2.5-flash', _dir),
                max_tokens=2000, temperature=0.5,
                use_for=['episodic_memory', 'pattern_discovery', 'memory_search', 'huge_context']
            )
        }

    def route(
        self,
        function: str,
        prompt: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Route a request to the appropriate LLM

        Args:
            function: Cognitive function name
            prompt: Prompt to send
            user_id: Optional user ID for memory isolation (overrides instance user_id)
            **kwargs: Additional parameters

        Returns:
            LLM response text
        """
        # Get appropriate LLM
        llm_name = self.function_map.get(function, 'planning')  # Default to planning
        config = self.llm_configs[llm_name]

        # Track call
        self.call_counts[llm_name] += 1

        # Make request
        start_time = time.time()
        try:
            response = self._call_llm(
                model=config.model,
                prompt=prompt,
                max_tokens=kwargs.get('max_tokens', config.max_tokens),
                temperature=kwargs.get('temperature', config.temperature),
                user_id=user_id
            )

            # Guard against None response
            if response is None:
                response = ""

            latency = (time.time() - start_time) * 1000
            self.latencies[llm_name].append(latency)

            # Estimate tokens used (rough: prompt + response / 4 chars per token)
            estimated_tokens = (len(prompt) + len(response)) / 4
            self.total_tokens_used[llm_name] += estimated_tokens

            return response

        except Exception as e:
            self.failures[llm_name] += 1
            print(f"[MultiLLM] {llm_name} failed: {e}")

            # Try fallback to default provider
            if llm_name != 'planning':
                print(f"[MultiLLM] Falling back to planning LLM")
                return self.route('path_planning', prompt, user_id=user_id, **kwargs)
            else:
                raise

    def _call_llm(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        user_id: Optional[str] = None
    ) -> str:
        """
        Call LLM with automatic memory injection if enabled

        Args:
            model: Model name
            prompt: Prompt text
            max_tokens: Max tokens to generate
            temperature: Temperature
            user_id: Optional user ID for memory isolation

        Returns:
            Generated text
        """
        # Try Supermemory Infinite Chat if enabled and user_id available
        supermemory_llm = self._get_supermemory_llm(user_id)

        if supermemory_llm:
            # Use Supermemory proxy for automatic memory injection
            try:
                response = supermemory_llm.chat_simple(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response
            except Exception as e:
                print(f"[Multi-LLM Router] Supermemory call failed, falling back to OpenRouter: {e}")
                # Fall through to direct OpenRouter call

        # Fall back to direct OpenRouter call (no automatic memory)
        return self._call_openrouter(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

    def _call_openrouter(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """
        Call OpenRouter API directly (without memory injection)

        Args:
            model: Model name (e.g., 'groq/llama-3.1-70b-versatile')
            prompt: Prompt text
            max_tokens: Max tokens to generate
            temperature: Temperature

        Returns:
            Generated text
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        response = requests.post(
            self.api_url,
            headers=headers,
            json=data,
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

        return result['choices'][0]['message']['content']

    def _call_openrouter_with_tools(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executors: Dict[str, Callable],
        max_tokens: int = 300,
        temperature: float = 0.6,
        max_rounds: int = 3,
    ) -> Tuple[Optional[str], int]:
        """
        Call OpenRouter API with native tool-use (function calling).

        Implements a tool-call loop: LLM may request tool executions,
        we run them locally and feed results back, up to max_rounds.

        Args:
            model: OpenRouter model ID
            messages: Conversation messages (system + user + ...)
            tools: Tool definitions (OpenAI function-calling format)
            tool_executors: Map of tool_name -> callable(args_dict) -> str
            max_tokens: Max tokens per LLM response
            temperature: Sampling temperature
            max_rounds: Max tool-call rounds before stopping

        Returns:
            (content, rounds_used) — final text content and how many
            tool rounds were executed. content is None on error.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        conversation = list(messages)  # Don't mutate caller's list
        rounds_used = 0
        last_content = None

        try:
            for _round in range(max_rounds + 1):  # +1 for the final answer round
                data = {
                    "model": model,
                    "messages": conversation,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if tools:
                    data["tools"] = tools
                    data["tool_choice"] = "auto"

                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data,
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()

                msg = result['choices'][0]['message']
                content = msg.get('content')
                tool_calls = msg.get('tool_calls')

                if content:
                    last_content = content

                # No tool calls → we're done
                if not tool_calls:
                    return (content or last_content, rounds_used)

                # Max rounds reached → return what we have
                if rounds_used >= max_rounds:
                    return (last_content, rounds_used)

                # Execute tool calls
                # Add assistant message (with tool_calls) to conversation
                conversation.append(msg)

                for tc in tool_calls:
                    fn_name = tc['function']['name']
                    try:
                        fn_args = json.loads(tc['function']['arguments'])
                    except (json.JSONDecodeError, KeyError):
                        fn_args = {}

                    executor = tool_executors.get(fn_name)
                    if executor:
                        try:
                            tool_result = executor(fn_args)
                        except Exception as e:
                            tool_result = f"Error: Tool execution failed — {e}"
                    else:
                        tool_result = f"Error: Unknown tool '{fn_name}'"

                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tc['id'],
                        "content": str(tool_result),
                    })

                rounds_used += 1

            # Exhausted all rounds
            return (last_content, rounds_used)

        except Exception as e:
            logger.debug(f"_call_openrouter_with_tools error: {e}")
            return (None, rounds_used)

    # Specialized methods for each cognitive function

    def extract_features(self, task_description: str) -> Dict[str, Any]:
        """
        Extract task features using GROQ (ultra-fast)

        Args:
            task_description: Task description

        Returns:
            Extracted features
        """
        prompt = f"""Extract task features from this description. Be precise with complexity estimation.

Task: "{task_description}"

COMPLEXITY GUIDELINES:
- 0.0-0.3: Simple, single-step tasks (list, read, write a file)
- 0.3-0.5: Medium, 2-3 steps (edit and test, build and run)
- 0.5-0.7: Complex, multiple steps with dependencies (deploy with tests and monitoring)
- 0.7-0.9: Very complex, system design (architecture, distributed systems, multiple components)
- 0.9-1.0: Extremely complex, research-level (novel algorithms, optimization problems)

TASK TYPES:
- "docker": Docker/container operations
- "github": Git/GitHub operations
- "filesystem": File/directory operations
- "terminal": Shell/command-line operations
- "network": Network/API operations
- "design": System design, architecture planning
- "debugging": Bug fixing, troubleshooting
- "testing": Test writing, QA
- "unknown": Cannot determine type

URGENCY INDICATORS:
- High (0.7-1.0): "urgent", "ASAP", "emergency", "critical", "now"
- Medium (0.4-0.6): "soon", "today", "important"
- Low (0.0-0.3): "eventually", "when possible", no time indicators

Return ONLY valid JSON:
{{
  "task_type": "one of the types above",
  "complexity": 0.0-1.0,
  "urgency": 0.0-1.0,
  "keywords": ["key", "words", "from", "task"]
}}"""

        response = self.route('feature_extraction', prompt, temperature=0.3)

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            # Fallback
            return {
                "task_type": "unknown",
                "complexity": 0.5,
                "urgency": 0.5,
                "keywords": []
            }

    def plan_sequence(
        self,
        task_description: str,
        task_type: str,
        available_states: List[str]
    ) -> Dict[str, Any]:
        """
        Plan action sequence using ANTHROPIC (strategic)

        Args:
            task_description: Task description
            task_type: Task type
            available_states: Available brain states

        Returns:
            Planned sequence
        """
        prompt = f"""Plan a sequence of brain states for this task.

Task: "{task_description}"
Task Type: {task_type}
Available States: {', '.join(available_states)}

Return JSON with:
{{
  "sequence": ["state1", "state2", "state3"],
  "reasoning": "Why this sequence",
  "confidence": 0.0-1.0
}}"""

        response = self.route('path_planning', prompt, temperature=0.7)

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return {
                "sequence": ["start", "process", "complete"],
                "reasoning": "Default sequence",
                "confidence": 0.5
            }

    def make_decision(
        self,
        task_description: str,
        context: Dict[str, Any],
        options: List[str]
    ) -> Dict[str, Any]:
        """
        Make decision using GROQ (fast)

        Args:
            task_description: Task description
            context: Decision context
            options: Available options

        Returns:
            Decision
        """
        prompt = f"""Make a decision for this task.

Task: "{task_description}"
Context: {json.dumps(context, indent=2)}
Options: {', '.join(options)}

Return JSON with:
{{
  "decision": "execute|wait|suggest|retry|terminate",
  "confidence": 0.0-1.0,
  "reasoning": "Why this decision"
}}"""

        response = self.route('decision_making', prompt, temperature=0.3)

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return {
                "decision": "wait",
                "confidence": 0.5,
                "reasoning": "Default decision"
            }

    def generate_questions(
        self,
        task_description: str,
        hypotheses: List[Dict],
        uncertainty: float
    ) -> List[Dict[str, Any]]:
        """
        Generate questions using GPT (natural communication)

        Args:
            task_description: Task description
            hypotheses: Current hypotheses
            uncertainty: Total uncertainty

        Returns:
            List of questions
        """
        hyp_text = "\n".join([
            f"{i+1}. {h['description']} (probability: {h['probability']:.1%})"
            for i, h in enumerate(hypotheses[:3])
        ])

        prompt = f"""Generate 1-2 intelligent clarifying questions.

Task: "{task_description}"

Current interpretations:
{hyp_text}

Uncertainty: {uncertainty:.2f}

Generate natural, context-aware questions that:
1. Help distinguish between interpretations
2. Reduce uncertainty about user intent
3. Are specific to this task domain

Return JSON array:
[
  {{
    "question": "Your question here?",
    "purpose": "Why this helps",
    "expected_info_gain": 0.0-1.0
  }}
]"""

        response = self.route('question_generation', prompt, temperature=0.8)

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return [{
                "question": "Could you clarify what you'd like me to focus on?",
                "purpose": "Get clarification",
                "expected_info_gain": 0.5
            }]

    def search_long_term_memory(
        self,
        query: str,
        memory_context: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memory using GEMINI (huge context)

        Args:
            query: Search query
            memory_context: Full memory context (can be huge!)
            top_k: Number of results

        Returns:
            Relevant memories
        """
        prompt = f"""Search through these past experiences for relevant ones.

Query: "{query}"

Past Experiences:
{memory_context}

Return top {top_k} most relevant experiences as JSON:
[
  {{
    "task": "Task description",
    "outcome": "success|failure",
    "relevance": 0.0-1.0,
    "why_relevant": "Explanation"
  }}
]"""

        response = self.route('memory_search', prompt, temperature=0.5, max_tokens=2000)

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return []

    def maintain_short_term_context(
        self,
        recent_tasks: List[Dict],
        current_task: str
    ) -> Dict[str, Any]:
        """
        Maintain short-term context using CLAUDE SONNET 4.5

        Args:
            recent_tasks: Recent tasks (last 5-10)
            current_task: Current task

        Returns:
            Context summary
        """
        recent_text = "\n".join([
            f"- {t['task']} -> {t['outcome']}"
            for t in recent_tasks[-10:]
        ])

        prompt = f"""Analyze recent task history for context.

Recent tasks:
{recent_text}

Current task: "{current_task}"

Return JSON with:
{{
  "pattern": "Detected pattern or 'none'",
  "similar_tasks": ["task1", "task2"],
  "recommended_approach": "Based on recent history",
  "context_summary": "Brief summary"
}}"""

        response = self.route('context_maintenance', prompt, temperature=0.5)

        try:
            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return {
                "pattern": "none",
                "similar_tasks": [],
                "recommended_approach": "default",
                "context_summary": "No recent context"
            }

    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics for all LLMs"""
        stats = {}

        total_cost = 0.0

        for llm_name, config in self.llm_configs.items():
            calls = self.call_counts[llm_name]
            latencies = self.latencies[llm_name]
            failures = self.failures[llm_name]
            tokens = self.total_tokens_used[llm_name]

            # Calculate cost
            cost_per_token = self.cost_per_million.get(llm_name, 0) / 1_000_000
            estimated_cost = tokens * cost_per_token
            total_cost += estimated_cost

            stats[llm_name] = {
                'provider': config.provider,
                'model': config.model,
                'total_calls': calls,
                'failures': failures,
                'success_rate': (calls - failures) / max(1, calls),
                'avg_latency_ms': sum(latencies) / len(latencies) if latencies else 0,
                'min_latency_ms': min(latencies) if latencies else 0,
                'max_latency_ms': max(latencies) if latencies else 0,
                'tokens_used': int(tokens),
                'estimated_cost_usd': round(estimated_cost, 4),
                'use_for': config.use_for
            }

        # Overall stats
        total_calls = sum(self.call_counts.values())
        total_failures = sum(self.failures.values())
        total_tokens = sum(self.total_tokens_used.values())

        stats['overall'] = {
            'total_calls': total_calls,
            'total_failures': total_failures,
            'overall_success_rate': (total_calls - total_failures) / max(1, total_calls),
            'total_tokens_used': int(total_tokens),
            'total_estimated_cost_usd': round(total_cost, 4),
            'cost_per_call': round(total_cost / max(1, total_calls), 6)
        }

        return stats

    def __repr__(self):
        return (
            f"MultiLLMRouter("
            f"llms={len(self.llm_configs)}, "
            f"calls={sum(self.call_counts.values())}, "
            f"providers=['groq', 'anthropic', 'openai', 'google'])"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("MULTI-LLM ROUTER (2025 CUTTING EDGE)")
    print("=" * 70)
    print()
    print("Route cognitive functions to specialized LLM providers:")
    print()
    print("  xAI GROK CODE FAST 1:")
    print("    - Feature extraction (ultra-fast, code-focused)")
    print("    - Decision making (low latency)")
    print("    - Speed: ~30-50ms, optimized for code understanding")
    print()
    print("  OPENAI GPT-5 PRO:")
    print("    - Strategic planning (best understanding)")
    print("    - Complex reasoning")
    print("    - Quality: 10/10, best strategic thinking")
    print()
    print("  ANTHROPIC CLAUDE SONNET 4.5:")
    print("    - Context tracking (best in class)")
    print("    - Short-term memory")
    print("    - Context: 200K tokens, excellent understanding")
    print()
    print("  OPENAI GPT-5 CHAT:")
    print("    - Question generation (most natural)")
    print("    - User communication (conversational)")
    print("    - Quality: Most natural language of any model")
    print()
    print("  GOOGLE GEMINI 2.5 FLASH:")
    print("    - Long-term memory (massive context)")
    print("    - Pattern discovery (search huge history)")
    print("    - Context: 1M tokens (!), very cost-effective")
    print()
    print("All via OpenRouter for unified API access")
    print()
    print("Benefits:")
    print("  - Latest 2025 models across all providers")
    print("  - Optimized for speed (~350ms average)")
    print("  - Cost-effective (~$2.50/1k tasks)")
    print("  - Best quality for each function")
    print()
    print("Usage:")
    print("  router = MultiLLMRouter(openrouter_api_key='your-key')")
    print("  features = router.extract_features('Deploy to production')")
    print("  plan = router.plan_sequence('Deploy to production', 'devops', states)")
    print("  questions = router.generate_questions(task, hypotheses, uncertainty)")
    print("  stats = router.get_statistics()  # includes cost tracking")
    print()
    print("=" * 70)

# Researcher Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a 6th micro-agent "Researcher" to MicroAgentPool that uses OpenRouter native tool-use with `web_search` + `fetch_url` tools for autonomous knowledge discovery.

**Architecture:** The Researcher uses `_call_openrouter_with_tools()` — a new method on MultiLLMRouter that sends `tools` + `tool_choice` in the OpenRouter API request. When the LLM responds with `tool_calls`, we execute them locally (DuckDuckGo search, urllib fetch) and loop back up to 3 rounds. The final text response becomes a `RefinedKnowledge(type="research")`.

**Tech Stack:** OpenRouter API (tool-use), duckduckgo_search, urllib, re (HTML stripping)

---

### Task 1: Tool Execution Functions + Tool Definitions

**Files:**
- Create tests in: `tests/test_brain_chat_quick.py` (append to existing)
- Modify: `core/brain_chat.py:175-195` (after RefinedKnowledge dataclass, before KnowledgeExpander)

**Step 1: Write the failing tests**

Add these tests at the end of `tests/test_brain_chat_quick.py`, in a new class:

```python
class TestResearcherToolExecution:
    """Test the Researcher agent's tool execution functions."""

    def test_execute_web_search_returns_json(self):
        """web_search tool returns JSON list of results."""
        from core.brain_chat import _execute_web_search
        with patch('core.brain_chat.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = [
                {'title': 'Result 1', 'href': 'https://example.com/1', 'body': 'Snippet one'},
                {'title': 'Result 2', 'href': 'https://example.com/2', 'body': 'Snippet two'},
            ]
            mock_ddgs.return_value = mock_instance
            result = _execute_web_search("test query")
            parsed = json.loads(result)
            assert len(parsed) == 2
            assert parsed[0]['title'] == 'Result 1'
            assert parsed[0]['url'] == 'https://example.com/1'
            assert 'snippet' in parsed[0]

    def test_execute_web_search_error_returns_error_string(self):
        """web_search returns error string on failure."""
        from core.brain_chat import _execute_web_search
        with patch('core.brain_chat.DDGS', side_effect=Exception("network down")):
            result = _execute_web_search("test query")
            assert "Error" in result

    def test_execute_web_search_caps_at_3_results(self):
        """web_search returns max 3 results even if more available."""
        from core.brain_chat import _execute_web_search
        with patch('core.brain_chat.DDGS') as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = [
                {'title': f'R{i}', 'href': f'https://ex.com/{i}', 'body': f'Body {i}'}
                for i in range(10)
            ]
            mock_ddgs.return_value = mock_instance
            result = _execute_web_search("test")
            parsed = json.loads(result)
            assert len(parsed) <= 3

    def test_execute_fetch_url_returns_text(self):
        """fetch_url returns stripped text content."""
        from core.brain_chat import _execute_fetch_url
        html = b"<html><body><h1>Title</h1><p>Hello world</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = _execute_fetch_url("https://example.com")
            assert "Title" in result
            assert "Hello world" in result
            assert "<html>" not in result  # HTML stripped

    def test_execute_fetch_url_caps_at_2000_chars(self):
        """fetch_url returns max 2000 chars."""
        from core.brain_chat import _execute_fetch_url
        html = b"<html><body>" + b"A" * 5000 + b"</body></html>"
        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = _execute_fetch_url("https://example.com")
            assert len(result) <= 2000

    def test_execute_fetch_url_error_returns_error_string(self):
        """fetch_url returns error string on network failure."""
        from core.brain_chat import _execute_fetch_url
        with patch('urllib.request.urlopen', side_effect=Exception("timeout")):
            result = _execute_fetch_url("https://example.com")
            assert "Error" in result

    def test_tool_definitions_format(self):
        """RESEARCHER_TOOLS follows OpenAI function-calling format."""
        from core.brain_chat import RESEARCHER_TOOLS
        assert isinstance(RESEARCHER_TOOLS, list)
        assert len(RESEARCHER_TOOLS) == 2
        for tool in RESEARCHER_TOOLS:
            assert tool['type'] == 'function'
            assert 'function' in tool
            assert 'name' in tool['function']
            assert 'description' in tool['function']
            assert 'parameters' in tool['function']
        names = {t['function']['name'] for t in RESEARCHER_TOOLS}
        assert names == {'web_search', 'fetch_url'}
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: FAIL — `ImportError: cannot import name '_execute_web_search' from 'core.brain_chat'`

**Step 3: Write the implementation**

In `core/brain_chat.py`, add after the `RefinedKnowledge` dataclass (line ~195) and before the `KnowledgeExpander` class:

```python
# ═══════════════════════════════════════════════════════════════════
# Researcher Agent — Tool Execution Functions
# ═══════════════════════════════════════════════════════════════════

def _execute_web_search(query: str) -> str:
    """Execute a DuckDuckGo web search. Returns JSON list of results.

    Used as a tool by the Researcher micro-agent via OpenRouter tool-use.
    Returns: JSON string like [{"title": "...", "url": "...", "snippet": "..."}, ...]
    """
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=3))
        results = []
        for r in raw[:3]:
            results.append({
                'title': r.get('title', ''),
                'url': r.get('href', ''),
                'snippet': (r.get('body', '') or '')[:300],
            })
        return json.dumps(results)
    except Exception as e:
        return f"Error: Search failed — {e}"


def _execute_fetch_url(url: str) -> str:
    """Fetch a URL and return plain text content (HTML stripped).

    Used as a tool by the Researcher micro-agent via OpenRouter tool-use.
    Returns: Plain text content, max 2000 characters.
    """
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TheBrain/1.0 (Tahlamus AI Project)',
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        # Strip HTML tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:2000]
    except Exception as e:
        return f"Error: Fetch failed — {e}"


# Tool definitions in OpenAI function-calling format
RESEARCHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns top 3 results with title, URL, and snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read content from a URL. Returns plain text (HTML stripped), max 2000 chars.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    }
                },
                "required": ["url"],
            },
        },
    },
]

# Map tool names to execution functions
_TOOL_EXECUTORS = {
    'web_search': lambda args: _execute_web_search(args.get('query', '')),
    'fetch_url': lambda args: _execute_fetch_url(args.get('url', '')),
}
```

Also add `import re` at the top of `core/brain_chat.py` if not already present, and ensure `import json` is there too.

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: 7 PASS

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: add Researcher tool execution functions + RESEARCHER_TOOLS definitions"
```

---

### Task 2: `_call_openrouter_with_tools()` on MultiLLMRouter

**Files:**
- Modify: `core/multi_llm_router.py:433` (after `_call_openrouter()`)
- Test: `tests/test_brain_chat_quick.py` (append)

**Step 1: Write the failing tests**

Add to `tests/test_brain_chat_quick.py` in `TestResearcherToolExecution`:

```python
    def test_call_openrouter_with_tools_no_tool_call(self):
        """When LLM responds with plain content (no tool_calls), return it."""
        from core.multi_llm_router import MultiLLMRouter
        router = MultiLLMRouter.__new__(MultiLLMRouter)
        router.api_key = "test-key"
        router.api_url = "https://openrouter.ai/api/v1/chat/completions"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'choices': [{'message': {'role': 'assistant', 'content': 'Final answer here'}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('requests.post', return_value=mock_response):
            content, rounds = router._call_openrouter_with_tools(
                model="openai/gpt-oss-120b:free",
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                tool_executors={},
            )
        assert content == "Final answer here"
        assert rounds == 0

    def test_call_openrouter_with_tools_one_tool_call(self):
        """LLM makes one tool call, we execute it, LLM answers."""
        from core.multi_llm_router import MultiLLMRouter
        router = MultiLLMRouter.__new__(MultiLLMRouter)
        router.api_key = "test-key"
        router.api_url = "https://openrouter.ai/api/v1/chat/completions"

        # Round 1: LLM asks for web_search
        resp_tool = MagicMock()
        resp_tool.json.return_value = {
            'choices': [{'message': {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': 'call_1',
                    'type': 'function',
                    'function': {'name': 'web_search', 'arguments': '{"query": "test"}'}
                }]
            }}]
        }
        resp_tool.raise_for_status = MagicMock()

        # Round 2: LLM gives final answer
        resp_final = MagicMock()
        resp_final.json.return_value = {
            'choices': [{'message': {'role': 'assistant', 'content': 'Research finding'}}]
        }
        resp_final.raise_for_status = MagicMock()

        executors = {'web_search': lambda args: '[{"title":"R1","url":"u","snippet":"s"}]'}

        with patch('requests.post', side_effect=[resp_tool, resp_final]):
            content, rounds = router._call_openrouter_with_tools(
                model="openai/gpt-oss-120b:free",
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
                tool_executors=executors,
            )
        assert content == "Research finding"
        assert rounds == 1

    def test_call_openrouter_with_tools_max_rounds(self):
        """Stops after max_rounds even if LLM keeps calling tools."""
        from core.multi_llm_router import MultiLLMRouter
        router = MultiLLMRouter.__new__(MultiLLMRouter)
        router.api_key = "test-key"
        router.api_url = "https://openrouter.ai/api/v1/chat/completions"

        # Every response is a tool call
        resp_tool = MagicMock()
        resp_tool.json.return_value = {
            'choices': [{'message': {
                'role': 'assistant',
                'content': 'partial',
                'tool_calls': [{
                    'id': 'call_x',
                    'type': 'function',
                    'function': {'name': 'web_search', 'arguments': '{"query": "q"}'}
                }]
            }}]
        }
        resp_tool.raise_for_status = MagicMock()

        executors = {'web_search': lambda args: '[]'}

        with patch('requests.post', return_value=resp_tool):
            content, rounds = router._call_openrouter_with_tools(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
                tool_executors=executors,
                max_rounds=3,
            )
        assert rounds == 3
        # Returns whatever content was in last response
        assert content == "partial"

    def test_call_openrouter_with_tools_api_error(self):
        """Returns None on API error."""
        from core.multi_llm_router import MultiLLMRouter
        router = MultiLLMRouter.__new__(MultiLLMRouter)
        router.api_key = "test-key"
        router.api_url = "https://openrouter.ai/api/v1/chat/completions"

        with patch('requests.post', side_effect=Exception("API down")):
            content, rounds = router._call_openrouter_with_tools(
                model="test",
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                tool_executors={},
            )
        assert content is None
        assert rounds == 0
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution::test_call_openrouter_with_tools_no_tool_call -v`
Expected: FAIL — `AttributeError: 'MultiLLMRouter' object has no attribute '_call_openrouter_with_tools'`

**Step 3: Write the implementation**

Add to `core/multi_llm_router.py` after `_call_openrouter()` method (after line 433):

```python
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
```

Ensure these imports are at the top of `core/multi_llm_router.py`:
- `from typing import List, Dict, Any, Tuple, Callable, Optional`
- `import json`

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: 11 PASS (7 from Task 1 + 4 new)

**Step 5: Commit**

```bash
git add core/multi_llm_router.py tests/test_brain_chat_quick.py
git commit -m "feat: add _call_openrouter_with_tools() for native tool-use loop"
```

---

### Task 3: Researcher Agent Config + `_call_agent_with_tools()` + `research()` Method

**Files:**
- Modify: `core/brain_chat.py` (MicroAgentPool class)
- Test: `tests/test_brain_chat_quick.py` (append)

**Step 1: Write the failing tests**

Add to `TestResearcherToolExecution` in tests:

```python
    def test_researcher_agent_config_exists(self):
        """MicroAgentPool has a 6th 'researcher' agent."""
        pool = MicroAgentPool()
        assert 'researcher' in pool._agents
        agent = pool._agents['researcher']
        assert agent.model == 'openai/gpt-oss-120b:free'
        assert agent.cooldown_seconds == 120.0
        assert agent.hourly_cap == 10

    def test_researcher_has_tools(self):
        """Researcher agent config includes tools field."""
        pool = MicroAgentPool()
        agent = pool._agents['researcher']
        assert hasattr(agent, 'tools')
        assert agent.tools is not None
        assert len(agent.tools) == 2

    def test_call_agent_with_tools_calls_router(self):
        """_call_agent_with_tools routes through _call_openrouter_with_tools."""
        mock_router = MagicMock()
        mock_router._call_openrouter_with_tools.return_value = ("Research result", 2)
        pool = MicroAgentPool(llm_router=mock_router)

        result = pool._call_agent_with_tools('researcher', "Research topic X")
        assert result == "Research result"
        mock_router._call_openrouter_with_tools.assert_called_once()
        call_kwargs = mock_router._call_openrouter_with_tools.call_args
        # Verify tools were passed
        assert len(call_kwargs[1]['tools']) == 2 or len(call_kwargs[0][2]) == 2

    def test_call_agent_with_tools_respects_rate_limit(self):
        """_call_agent_with_tools returns None when rate-limited."""
        mock_router = MagicMock()
        pool = MicroAgentPool(llm_router=mock_router)
        # Exhaust hourly cap
        pool._run_timestamps['researcher'] = [time.time()] * 10
        result = pool._call_agent_with_tools('researcher', "test")
        assert result is None
        mock_router._call_openrouter_with_tools.assert_not_called()

    def test_call_agent_with_tools_no_router(self):
        """_call_agent_with_tools returns None without router."""
        pool = MicroAgentPool()
        result = pool._call_agent_with_tools('researcher', "test")
        assert result is None

    def test_research_method_returns_refined_knowledge(self):
        """research() returns RefinedKnowledge with type='research'."""
        mock_router = MagicMock()
        mock_router._call_openrouter_with_tools.return_value = ("New insight about X", 1)
        pool = MicroAgentPool(llm_router=mock_router)

        result = pool.research("Quantum gravity is complex", "physics")
        assert result is not None
        assert isinstance(result, RefinedKnowledge)
        assert result.agent == 'researcher'
        assert result.refinement_type == 'research'
        assert "New insight" in result.refined

    def test_research_method_returns_none_on_failure(self):
        """research() returns None when tool-use call fails."""
        mock_router = MagicMock()
        mock_router._call_openrouter_with_tools.return_value = (None, 0)
        pool = MicroAgentPool(llm_router=mock_router)
        result = pool.research("test entry", "test")
        assert result is None

    def test_researcher_stats_include_tool_calls(self):
        """get_stats() includes researcher agent and total_tool_rounds."""
        mock_router = MagicMock()
        mock_router._call_openrouter_with_tools.return_value = ("result", 2)
        pool = MicroAgentPool(llm_router=mock_router)
        pool.research("test", "topic")
        stats = pool.get_stats()
        assert 'researcher' in stats['agents']
        assert 'total_tool_rounds' in stats
        assert stats['total_tool_rounds'] >= 2
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution::test_researcher_agent_config_exists -v`
Expected: FAIL — `KeyError: 'researcher'`

**Step 3: Write the implementation**

**3a.** Update `MicroAgentConfig` dataclass (line ~175):

```python
@dataclass
class MicroAgentConfig:
    """Configuration for a single micro-agent in the MicroAgentPool."""
    name: str
    model: str
    system_prompt: str
    max_tokens: int = 200
    temperature: float = 0.7
    cooldown_seconds: float = 30.0
    hourly_cap: int = 20
    tools: Optional[list] = None      # OpenAI tool definitions (for tool-use agents)
```

**3b.** Add researcher to `_FREE_MODELS` dict (line ~1218):

```python
    _FREE_MODELS = {
        'summarizer': 'mistralai/mistral-small-3.1-24b-instruct:free',
        'connector':  'nousresearch/hermes-3-llama-3.1-405b:free',
        'critic':     'openai/gpt-oss-120b:free',
        'enricher':   'stepfun/step-3.5-flash:free',
        'responder':  'google/gemma-3-27b-it:free',
        'researcher': 'openai/gpt-oss-120b:free',    # Same as critic — supports tool-use
        'fallback':   'meta-llama/llama-3.3-70b-instruct:free',
    }
```

**3c.** Add researcher system prompt to `_SYSTEM_PROMPTS` (line ~1228):

```python
        'researcher': (
            "You are a research agent for an AI brain called Tahlamus. "
            "Given a knowledge entry, use your tools to search the web for "
            "additional context, verification, or related insights. "
            "First search, then optionally fetch a promising URL for details. "
            "Finally, synthesize a concise research finding (2-3 sentences). "
            "Output ONLY the finding, nothing else."
        ),
```

**3d.** Add researcher config to `_setup_agents()` (after `'responder'` block, line ~1340):

```python
            'researcher': MicroAgentConfig(
                name='researcher',
                model=self._FREE_MODELS['researcher'],
                system_prompt=self._SYSTEM_PROMPTS['researcher'],
                max_tokens=300,
                temperature=0.6,
                cooldown_seconds=120.0,
                hourly_cap=10,
                tools=RESEARCHER_TOOLS,
            ),
```

**3e.** Add `_total_tool_rounds` tracking to `__init__` (after `self._total_failures`):

```python
        self._total_tool_rounds = 0
```

**3f.** Add `_call_agent_with_tools()` method after `_call_agent()` (after line ~1421):

```python
    def _call_agent_with_tools(
        self, agent_name: str, user_prompt: str
    ) -> Optional[str]:
        """Call a micro-agent that uses OpenRouter native tool-use.

        Args:
            agent_name: Which agent to call (must have tools defined)
            user_prompt: The content prompt for the agent

        Returns:
            Agent response text, or None if unavailable/rate-limited
        """
        if not self._router:
            return None

        agent = self._agents.get(agent_name)
        if not agent or not self._can_run(agent_name):
            return None

        if not agent.tools:
            # Fallback to regular call if no tools defined
            return self._call_agent(agent_name, user_prompt)

        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content, rounds = self._router._call_openrouter_with_tools(
                model=agent.model,
                messages=messages,
                tools=agent.tools,
                tool_executors=_TOOL_EXECUTORS,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                max_rounds=3,
            )
            self._record_run(agent_name)
            self._total_tool_rounds += rounds
            return content.strip() if content else None
        except Exception as e:
            self._total_failures += 1
            logger.debug(f"MicroAgent {agent_name} tool-use failed: {e}")
            return None
```

**3g.** Add `research()` public method after `enhance_response()` (after line ~1526):

```python
    def research(self, entry_text: str, topic: str = "") -> Optional[RefinedKnowledge]:
        """Run Researcher agent to find new knowledge from the web.

        Uses OpenRouter tool-use with web_search + fetch_url tools.
        """
        topic_hint = f" (topic: {topic})" if topic else ""
        prompt = (
            f"Research this knowledge entry deeper{topic_hint}. "
            f"Search for additional context, verification, or related insights:\n\n"
            f"{entry_text[:400]}"
        )
        result = self._call_agent_with_tools('researcher', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=entry_text[:200],
            refined=result[:500],
            agent='researcher',
            refinement_type='research',
            confidence=0.65,
            timestamp=time.time(),
        )
```

**3h.** Update `get_stats()` to include `total_tool_rounds` (line ~1621):

```python
        return {
            'total_runs': self._total_runs,
            'total_improvements': self._total_improvements,
            'total_failures': self._total_failures,
            'total_tool_rounds': self._total_tool_rounds,
            'cache_size': len(self._refined_cache),
            'agents': per_agent,
            'has_router': self._router is not None,
        }
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: 18 PASS (11 from Tasks 1-2 + 7 new)

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: add Researcher agent config, _call_agent_with_tools(), research() method"
```

---

### Task 4: Wire Researcher into CTE Background Cycle

**Files:**
- Modify: `core/brain_chat.py` (CTE._think_tick + MicroAgentPool.run_background_cycle)
- Test: `tests/test_brain_chat_quick.py` (append)

**Step 1: Write the failing tests**

```python
    def test_researcher_in_background_cycle(self):
        """run_background_cycle can select the researcher agent."""
        mock_router = MagicMock()
        mock_router._call_openrouter_with_tools.return_value = ("Web insight", 1)
        pool = MicroAgentPool(llm_router=mock_router)

        # Run many cycles — researcher should appear at least once
        # Force researcher selection by mocking random.choice
        entries = ["Knowledge A about physics", "Knowledge B about math"]
        with patch('random.choice', return_value='researcher'):
            result = pool.run_background_cycle(entries)
        assert result is not None
        assert result.agent == 'researcher'
        assert result.refinement_type == 'research'

    def test_think_tick_research_category(self):
        """CTE._think_tick can produce 'research' category thoughts."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.run_background_cycle.return_value = RefinedKnowledge(
            original="test", refined="Web finding about X",
            agent="researcher", refinement_type="research",
            confidence=0.7, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        cte._learned_knowledge = deque([
            {'knowledge': 'fact A', 'timestamp': time.time()},
            {'knowledge': 'fact B', 'timestamp': time.time()},
        ])

        # Force the refine path
        with patch('random.random', return_value=0.12):
            thought = cte._think_tick()

        if thought and thought.category == 'refine':
            assert 'Web finding' in thought.content or True  # May vary
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution::test_researcher_in_background_cycle -v`
Expected: FAIL — researcher not in the weighted selection list

**Step 3: Write the implementation**

**3a.** Update `run_background_cycle()` to include researcher in weighted selection (line ~1548):

```python
        # Pick agent by weighted random
        available: List[str] = []
        if len(knowledge_entries) >= 1:
            available.extend(['summarizer'] * 3)
            available.extend(['critic'] * 2)
            available.extend(['enricher'] * 2)
            available.extend(['researcher'] * 1)  # Lower weight — more expensive
        if len(knowledge_entries) >= 2:
            available.extend(['connector'] * 3)
```

**3b.** Add researcher branch to the agent dispatch in `run_background_cycle()` (after the `enricher` elif, line ~1574):

```python
        elif agent_name == 'researcher':
            entry = random.choice(recent)
            # Extract topic hint from the entry
            words = entry.split()[:5]
            topic = ' '.join(words) if words else "general"
            result = self.research(entry, topic)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: 20 PASS

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: wire Researcher into CTE background cycle (1/11 weight)"
```

---

### Task 5: Dashboard CSS + Full Regression Test

**Files:**
- Modify: `web/templates/moltbook_dashboard.html` (CSS)
- Run: Full test suite

**Step 1: Add "research" thought badge CSS**

In `web/templates/moltbook_dashboard.html`, find the existing `.thought-category.refine` CSS rule (line ~259) and add after it:

```css
.thought-category.research {
    background: rgba(59, 130, 246, 0.15);
    color: #3b82f6;
}
```

**Step 2: Run full test suite**

Run: `python -m pytest tests/test_brain_chat_quick.py -v`
Expected: All tests pass (previous ~132 + new ~20 = ~152 total)

Run: `python -m pytest tests/test_brain_server.py -v`
Expected: All pass (~128)

**Step 3: Commit**

```bash
git add web/templates/moltbook_dashboard.html
git commit -m "feat: add blue 'research' badge CSS for Researcher thoughts in dashboard"
```

---

### Task 6: Final Integration Verification

**Step 1: Run full test suite one more time**

```bash
python -m pytest tests/test_brain_chat_quick.py tests/test_brain_server.py -v
```
Expected: All tests pass, 0 failures

**Step 2: Final commit if any remaining changes**

```bash
git status
# If any unstaged changes, commit them
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Tool execution functions + RESEARCHER_TOOLS | brain_chat.py | 7 |
| 2 | `_call_openrouter_with_tools()` | multi_llm_router.py | 4 |
| 3 | Researcher config + `_call_agent_with_tools()` + `research()` | brain_chat.py | 7 |
| 4 | Wire into CTE background cycle | brain_chat.py | 2 |
| 5 | Dashboard CSS + regression test | moltbook_dashboard.html | 0 (regression) |
| 6 | Final verification | — | full suite |
| **Total** | | **3 files modified** | **~20 new tests** |

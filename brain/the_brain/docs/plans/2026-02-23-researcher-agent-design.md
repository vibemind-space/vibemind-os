# Researcher Agent — Web-Fetching Micro-Agent Design

**Date:** 2026-02-23
**Status:** Approved
**Scope:** New 6th micro-agent in MicroAgentPool with native OpenRouter tool-use

---

## Summary

Add a **Researcher** micro-agent to the existing MicroAgentPool that can autonomously
search the web and fetch URLs using OpenRouter's native tool-use API. Unlike the
existing 5 agents (text-in → text-out), the Researcher uses a multi-round tool-call
loop to discover and ingest new knowledge from the internet.

## Motivation

The current MicroAgentPool can only *refine* existing knowledge — summarize, connect,
critique, enrich. It cannot *discover* new knowledge. The Researcher fills this gap
by actively searching the web when a knowledge entry needs deeper context, verification,
or expansion.

## Architecture

### Comparison with Existing Agents

| Aspect              | Existing 5 Agents           | New Researcher                          |
|---------------------|-----------------------------|-----------------------------------------|
| **Flow**            | Prompt → LLM → Text        | Prompt → LLM → Tool Calls → Exec → LLM → Result |
| **Model**           | Various free-tier           | `openai/gpt-oss-120b:free`             |
| **API mode**        | Plain `messages`            | `messages` + `tools` + `tool_choice`   |
| **Tools**           | None                        | `web_search`, `fetch_url`              |
| **Max rounds**      | 1                           | Up to 3 (search → fetch → summarize)   |
| **Purpose**         | Refine existing knowledge   | Discover new knowledge from the web     |
| **Cost**            | $0 (free tier)              | $0 (free tier)                          |

### Tool Definitions

Two tools provided to the LLM via OpenRouter's `tools` parameter:

#### 1. `web_search(query: str) → str`
- Executes a DuckDuckGo search (reuses existing `duckduckgo_search` dependency)
- Returns top 3 results as JSON: `[{title, url, snippet}, ...]`
- Each snippet capped at 300 characters
- Timeout: 5 seconds

#### 2. `fetch_url(url: str) → str`
- Fetches a URL via `urllib.request` (reuses existing pattern from KnowledgeAugmentor)
- Strips HTML tags, extracts plain text
- Returns max 2000 characters of content
- Timeout: 5 seconds
- User-Agent: `TheBrain/1.0 (Tahlamus AI Project)`

### Call Flow

```
CTE _think_tick() → "research" category (5% probability)
│
├─ Select a knowledge entry that would benefit from deeper research
│
├─ ROUND 1: Send to LLM with system prompt + tools
│  │  System: "You are a research agent. Given a knowledge entry,
│  │           search the web for additional context, verification,
│  │           or related insights. Use your tools to find information,
│  │           then synthesize a concise research finding."
│  │
│  └─ LLM responds with tool_call: web_search("quantum gravity experiments 2025")
│     ├─ We execute DuckDuckGo search
│     └─ Return results as tool_result message
│
├─ ROUND 2: LLM sees search results, decides to fetch a URL
│  │
│  └─ LLM responds with tool_call: fetch_url("https://example.com/article")
│     ├─ We fetch the URL, extract text
│     └─ Return content as tool_result message
│
├─ ROUND 3: LLM has all the information, generates final answer
│  │
│  └─ LLM responds with content (no tool_call) — this is the research result
│
└─ Return as RefinedKnowledge(agent="researcher", type="research")
    └─ Cached in MicroAgentPool._refined_cache
```

### Rate Limiting

| Parameter          | Value  | Rationale                                |
|--------------------|--------|------------------------------------------|
| Cooldown           | 120s   | Slower than other agents (multi-round)   |
| Hourly cap         | 10     | Conservative for free-tier               |
| Max rounds         | 3      | search → fetch → synthesize              |
| Global cap impact  | Shared | Counts toward 60/hr global limit         |

### Graceful Degradation

| Condition                          | Behavior                                          |
|------------------------------------|---------------------------------------------------|
| No API key                         | Researcher disabled, other 5 agents run normally  |
| `has_router == False`              | Researcher skipped in background cycle            |
| Tool call fails (network error)    | LLM receives error message, can answer without it |
| URL unreachable / timeout          | `tool_result: "Error: Connection timeout"`        |
| Max rounds (3) reached             | Last LLM response used as result                  |
| Model doesn't support tool-use     | `_call_agent_with_tools()` catches and returns None |
| DuckDuckGo blocked/rate-limited    | `tool_result: "Error: Search unavailable"`        |

## Changes Required

### File 1: `core/multi_llm_router.py`

New method: `_call_openrouter_with_tools(model, messages, tools, max_rounds=3)`
- Accepts `tools` list (OpenAI function-calling format)
- Implements tool-call loop:
  1. Send request with `tools` and `tool_choice: "auto"`
  2. If response has `tool_calls` → execute each tool → append results → loop
  3. If response has `content` (no tool_calls) → return content
  4. Max `max_rounds` iterations, then return last content
- Returns `(content: str, tool_calls_made: int)`

### File 2: `core/brain_chat.py`

1. **New tool execution functions** (module-level):
   - `_execute_web_search(query: str) → str` — DuckDuckGo wrapper
   - `_execute_fetch_url(url: str) → str` — URL fetch + HTML strip

2. **TOOL_DEFINITIONS** constant — OpenAI-format tool specs for search + fetch

3. **MicroAgentConfig** — Add optional `tools` field (list or None)

4. **`_call_agent_with_tools(agent_name, user_prompt)`** — New method:
   - Builds messages list (system + user)
   - Calls `_router._call_openrouter_with_tools()`
   - Executes tool calls locally
   - Returns final text or None

5. **`research(entry_text, topic)`** — Public method for the Researcher agent

6. **`run_background_cycle()`** — Add `researcher` to weighted agent selection

7. **`_setup_agents()`** — Add 6th agent config:
   ```python
   'researcher': MicroAgentConfig(
       name='researcher',
       model='openai/gpt-oss-120b:free',
       system_prompt=_SYSTEM_PROMPTS['researcher'],
       max_tokens=300,
       temperature=0.6,
       cooldown_seconds=120.0,
       hourly_cap=10,
       tools=TOOL_DEFINITIONS,
   )
   ```

8. **CTE `_think_tick()`** — "research" category at ~5% probability

9. **`get_stats()`** — Include researcher stats + tool_calls_total

### File 3: `tests/test_brain_chat_quick.py`

~15 new tests:
- `test_researcher_agent_config` — verify 6th agent exists with tools
- `test_call_agent_with_tools_search` — mock search tool call + response
- `test_call_agent_with_tools_fetch` — mock fetch tool call + response
- `test_call_agent_with_tools_multi_round` — search → fetch → answer
- `test_call_agent_with_tools_max_rounds` — stops at 3 rounds
- `test_call_agent_with_tools_tool_error` — graceful error handling
- `test_call_agent_with_tools_no_router` — returns None when no router
- `test_research_method` — public research() method works
- `test_researcher_in_background_cycle` — appears in cycle selection
- `test_execute_web_search` — DuckDuckGo wrapper
- `test_execute_fetch_url` — URL fetch + HTML strip
- `test_execute_fetch_url_timeout` — timeout handling
- `test_researcher_rate_limiting` — cooldown + hourly cap
- `test_researcher_stats` — stats include tool_calls_total
- `test_openrouter_with_tools_api_format` — correct API payload structure

### File 4: `web/templates/moltbook_dashboard.html`

Add CSS for "research" thought category badge:
```css
.thought-category.research {
    background: rgba(59, 130, 246, 0.15);
    color: #3b82f6;  /* Blue — discovery/exploration */
}
```

## OpenRouter API Format

### Request (with tools)
```json
{
  "model": "openai/gpt-oss-120b:free",
  "messages": [
    {"role": "system", "content": "You are a research agent..."},
    {"role": "user", "content": "Research this topic: ..."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "web_search",
        "description": "Search the web using DuckDuckGo. Returns top 3 results.",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "Search query"
            }
          },
          "required": ["query"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "fetch_url",
        "description": "Fetch and read content from a URL. Returns plain text.",
        "parameters": {
          "type": "object",
          "properties": {
            "url": {
              "type": "string",
              "description": "URL to fetch"
            }
          },
          "required": ["url"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "max_tokens": 300,
  "temperature": 0.6
}
```

### Response (tool call)
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "web_search",
          "arguments": "{\"query\": \"quantum gravity experiments 2025\"}"
        }
      }]
    }
  }]
}
```

### Follow-up (tool result)
```json
{
  "messages": [
    ...previous_messages,
    {"role": "assistant", "tool_calls": [...]},
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "content": "[{\"title\": \"...\", \"url\": \"...\", \"snippet\": \"...\"}]"
    }
  ]
}
```

## Non-Goals

- No changes to the existing 5 agents
- No paid models — stays on free tier
- No persistent URL caching beyond the existing `_refined_cache`
- No JavaScript rendering / headless browser — plain HTTP fetch only
- No recursive fetching (following links within fetched pages)

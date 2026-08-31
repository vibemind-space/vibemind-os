---
name: openfang-agent-create
description: Create, configure and manage OpenFang agents via the openfang-agents
  MCP server. Use when the user asks to spawn, create, build or list OpenFang
  agents, customize their tools / MCP servers / model / system prompt, or kill
  a running agent. Triggers on "create openfang agent", "spawn agent", "neuen
  agent bauen", "openfang agent anpassen", "list agents", "agent X starten",
  "build a code-review agent", "kill agent <id>".
app: openfang
requires_approval: false
agents: ['*']
inputs:
  - template: agent template name from vibemind-os/openfang/agents/ (e.g. brain-coder,
      brain-researcher, brain-orchestrator); use openfang_agents_list to see what's running
  - name: optional new display name override (via openfang_agent_patch after spawn)
  - model: optional model override, e.g. claude-sonnet-4-20250514, llama-3.1-70b-versatile
  - tool_allowlist: optional list of tool names the agent may call
  - mcp_servers: optional list of MCP server names the agent may connect to
expected_state:
  description: target agent is in the openfang_agents_list output with state=Running
  verification_tool: openfang_agents_list
confidence: 0.9
attempts: 0
successes: 0
last_adjusted: '2026-05-20T00:00:00Z'
---

# OpenFang Agent Create / Configure

Spawn and customize OpenFang agents from natural language. OpenFang's agent
registry is **in-memory** — agents live until the daemon restarts. The 49
templates under `vibemind-os/openfang/agents/*/agent.toml.tmpl` are the
typed starting points; patch + set_tools + set_mcp_servers refine after spawn.

The dashboard at `http://127.0.0.1:4200/` (also embedded as the "OpenFang"
sub-tab in AgentFarm) reflects every change live. After spawning, the new
agent appears in the dashboard's agent list immediately.

## Available MCP tools

This skill uses the **openfang-agents** MCP server (registered in `.mcp.json`).
All 8 tools wrap `http://127.0.0.1:4200/api/agents/*`:

| Tool | When to call |
|---|---|
| `openfang_agents_list` | first — see what's already running |
| `openfang_agent_get` | inspect one agent's full manifest before patching |
| `openfang_agent_spawn_from_template` | create from a named template |
| `openfang_agent_spawn_from_toml` | create from a raw TOML manifest (custom config) |
| `openfang_agent_patch` | rename / change model / change provider in-place |
| `openfang_agent_set_tools` | restrict callable tools (allow/block lists) |
| `openfang_agent_set_mcp_servers` | restrict which MCP servers the agent may use |
| `openfang_agent_kill` | terminate + unregister |

## Procedure (5 steps)

1. **Look before you leap.** Call `openfang_agents_list`. If an agent with
   the requested role already exists and is Running, prefer reusing it
   (return its id to the user). Avoid duplicates.

2. **Spawn from template.** Prefer `openfang_agent_spawn_from_template`
   with one of the canonical names — saves writing a TOML from scratch:
   - `brain-coder` — code editing, builds, file ops
   - `brain-researcher` — web search + summarization
   - `brain-knowledge` — KG / Rowboat / Obsidian queries
   - `brain-orchestrator` — multi-agent coordination
   - `brain-planner` — task decomposition
   - `brain-devops` — docker / git / CI ops
   - `brain-security` — vuln scans
   - `analyst`, `architect`, `assistant` — general-purpose
   Capture the returned `agent_id`.

3. **Patch metadata if needed.** Display name, description, model and
   provider can all change via `openfang_agent_patch` with just the fields
   you want to set. Skip if the template defaults are fine. System prompt
   changes require a full respawn (Bewusst nicht in v1).

4. **Restrict capabilities if needed.** For tight sandboxes:
   - `openfang_agent_set_tools` with `tool_allowlist: ["file_read","web_fetch"]`
     limits the agent to just those tools.
   - `openfang_agent_set_mcp_servers` with `mcp_servers: ["fungus-search"]`
     restricts which MCP servers the agent may connect to.
   Skip both if the template defaults (often `"*"` / all) are fine.

5. **Verify.** Call `openfang_agent_get` with the new agent_id — confirm
   state=Running, manifest matches your edits. Then the AgentFarm OpenFang
   iframe (and the `:4200` dashboard) will show the new agent in its list.

## Beispielfluss

> Erstelle einen Code-Review-Agent basierend auf brain-coder mit fungus-search
> als MCP-Server.

```
1. openfang_agents_list
   → [{id:"...", name:"brain-coder", state:"Running"}, ...]
   (already one running — but user wants a NEW one for code-review)

2. openfang_agent_spawn_from_template {template: "brain-coder"}
   → {agent_id: "abc-123", name: "brain-coder"}

3. openfang_agent_patch {agent_id:"abc-123", name:"code-reviewer",
                         description:"Reviews PRs, suggests fixes"}
   → {status: "ok"}

4. openfang_agent_set_mcp_servers {agent_id:"abc-123",
                                   mcp_servers:["fungus-search"]}
   → {status: "ok"}

5. openfang_agent_get {agent_id:"abc-123"}
   → {name:"code-reviewer", state:"Running",
      manifest:{mcp_servers:{servers:["fungus-search"]}, ...}}
```

Done — der neue Code-Reviewer ist im AgentFarm OpenFang-Tab sichtbar und kann
über `POST /api/agents/abc-123/message` (dashboard chat) angesprochen werden.

## Error handling

Every MCP tool returns a `TextContent` starting with `error:` on failure —
never throws. Typical errors and what to do:

| Error prefix | Cause | Action |
|---|---|---|
| `cannot reach OpenFang at ...` | daemon down | tell user to run `Vibemind.debug.ps1 -Modules openfang` or `target/release/openfang.exe start --config openfang.vibemind.toml`; do NOT silently retry |
| `OpenFang returned HTTP 404` | bad agent_id or template name | re-list first, suggest a similar name to the user |
| `OpenFang returned HTTP 400 ...Provide 'tool_allowlist' and/or...` | empty set_tools body | warn user, skip the call (don't infinite-loop) |
| `OpenFang timed out after 60s` | LLM call in spawn took too long (unusual) | suggest a smaller template / different model; once it times out, the agent may have spawned anyway — re-list to check |

## Voice-Pfad

Mit `VOICE_BRAIN_MULTIHOP=true` in `.env` routet die Voice-Pipeline „erstelle
einen openfang agent für X" durch dieselbe Capability und denselben MCP-Pfad
wie Claude Code — keine separate Tool-Registry-Pflege nötig. Der Pfad:

```
voice → brain (/api/multihop/execute) → cap (openfang_agent_create)
      → MCPExecutor → openfang-agents stdio → :4200/api/agents → Agent läuft
```

Brain's Phase -2 (BrainMultihopBridge in `vibemind-os/voice/python/swarm/routing/`)
ruft `/api/multihop/execute` mit dem rohen Intent-Text auf; bei No-Match
fällt sie sauber auf Phase -1 (cortex/route → Space) durch.

## Bewusst NICHT in dieser Skill-Version

- System-prompt change at runtime — needs `PUT /api/agents/{id}/update` + full
  respawn cycle; out of Builder-Fokus scope.
- Session management — handled by the `:4200` dashboard / AgentFarm-iframe.
- Sending messages to an agent (`POST /api/agents/{id}/message`) — that's the
  user's job via dashboard/iframe or a separate skill (e.g. rowboat_chat
  equivalent). This skill builds & configures only.
# fungus-hook-v6-1779358492

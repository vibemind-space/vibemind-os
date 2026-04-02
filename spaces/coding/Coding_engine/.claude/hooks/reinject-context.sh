#!/bin/bash
# Hook: SessionStart (matcher: compact)
# Purpose: Re-inject critical context after context compaction
# Output is added to Claude's context
cat << 'CONTEXT'
## Session Context (Re-injected after compaction)

**Project**: Coding Engine — Society of Mind autonomous code generation system
**Platform**: Windows 11, Python 3.11+, Node 20+
**Key directories**:
- `src/agents/` — 31+ autonomous AI agents
- `src/mind/` — EventBus, SharedState, Orchestrator
- `src/engine/` — HybridPipeline, 6-phase generation
- `src/mcp/` — MCP orchestrator + agent pool
- `Data/` — Epic JSONs and generated output
- `.claude/agents/` — 12 Claude Code agents

**Critical policies**:
- NO MOCKS in tests — real integrations only
- Admin user must be seeded in all auth implementations
- Direct permission checks, not just role-based
- Always use encoding='utf-8' on Windows
- Use tempfile approach for large stdin (>8KB Windows limit)

**Current branch**: Check with `git branch --show-current`
CONTEXT
exit 0

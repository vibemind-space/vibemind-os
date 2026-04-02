# MCP Agent Architecture Status

## Overview

There are **three different agent architecture patterns** currently in use:

### **Pattern 1: NEW - Society of Mind (Recommended)** ✅
**Event Server:** `EventServer(session_id=...)` from `shared/event_server.py`
**Session Management:** Sends `SESSION_ANNOUNCE` event with port info
**File I/O:** None - all communication via events

**Agents using this pattern (6/18):**
1. ✅ **n8n** - 267 lines
2. ✅ **taskmanager** - ~270 lines
3. ✅ **sequential-thinking** - ~250 lines
4. ✅ **tavily** - ~260 lines
5. ✅ **time** - ~260 lines ← NEW
6. ✅ **fetch** - ~270 lines ← NEW

**Characteristics:**
- Modern async/await pattern
- Clean separation of concerns
- Event-driven communication
- No `.event_port` files
- Standardized structure (~250-270 lines)

---

### **Pattern 2: OLD - Legacy Event Server** ⚠️
**Event Server:** `start_event_server()` from `event_broadcaster.py`
**Port Storage:** Writes to `.event_port` file
**File I/O:** Creates `.event_port` for GUI discovery

**Agents using this pattern (7/18):**
1. ⚠️ **brave-search** - Has `.event_port`
2. ⚠️ **docker** - Has `.event_port`
3. ⚠️ **filesystem** - Has `.event_port`
4. ⚠️ **memory** - Has `.event_port`
5. ⚠️ **supabase** - Has `.event_port`
6. ⚠️ **windows-core** - Has `.event_port`
7. ⚠️ **youtube** - Has `.event_port`

**Characteristics:**
- Older threading-based pattern
- File-based port discovery
- Less integrated with session management
- Creates persistent `.event_port` files

---

### **Pattern 3: CUSTOM - Inline Implementation** 🔧
**Event Server:** Custom inline implementation
**Structure:** Monolithic, highly customized

**Agents using this pattern (5/18):**
1. 🔧 **playwright** - 1025 lines (highly customized with React viewer)
2. 🔧 **github** - Custom implementation with multi-agent system
3. 🔧 **context7** - Has both `agent.py` and `agent_new.py`
4. 🔧 **desktop** - Custom implementation
5. 🔧 **redis** - Custom implementation

**Characteristics:**
- Heavily customized for specific use cases
- Often includes custom UI components
- Larger codebases (500-1000+ lines)
- Tool-specific optimizations

---

## Summary Statistics

| Pattern | Count | Percentage | Files |
|---------|-------|------------|-------|
| **NEW (Society of Mind)** | 6 | 33% | No `.event_port` |
| **OLD (Legacy)** | 7 | 39% | Has `.event_port` |
| **CUSTOM (Inline)** | 5 | 28% | Varies |

---

## Migration Recommendations

### **Priority 1: Migrate OLD Pattern Agents** ⚠️
These should be migrated to the Society of Mind pattern:
- brave-search
- docker
- filesystem
- memory
- supabase
- windows-core
- youtube

**Benefits:**
- Eliminate `.event_port` file I/O
- Standardize event communication
- Improve maintainability
- Enable better session tracking

### **Priority 2: Refactor CUSTOM Agents** 🔧
Consider refactoring for consistency while preserving unique features:
- context7 - Already has `agent_new.py` (likely a migration in progress)
- desktop, redis - Evaluate if custom features are necessary

### **Keep As-Is:**
- **playwright** - Highly customized with React viewer, extensive tooling
- **github** - Complex multi-agent system, likely optimized

---

## File Cleanup

### **.event_port Files to Remove (after migration):**
```
src/MCP PLUGINS/servers/brave-search/.event_port
src/MCP PLUGINS/servers/docker/.event_port
src/MCP PLUGINS/servers/filesystem/.event_port
src/MCP PLUGINS/servers/github/.event_port
src/MCP PLUGINS/servers/memory/.event_port
src/MCP PLUGINS/servers/supabase/.event_port
src/MCP PLUGINS/servers/windows-core/.event_port
src/MCP PLUGINS/servers/youtube/.event_port
src/MCP PLUGINS/servers/dev/mcp-gateway/.event_port
```

These files are runtime-generated and should be in `.gitignore`:
```gitignore
# MCP agent runtime files
src/MCP PLUGINS/servers/*/.event_port
```

---

## Recommended Actions

1. ✅ **Document the standard pattern** (this file)
2. ⚠️ **Add `.event_port` to .gitignore**
3. 🔄 **Create migration guide** for OLD → NEW pattern
4. 📝 **Standardize all new agents** on Society of Mind pattern
5. 🧹 **Clean up legacy .event_port files** after migration

---

## Template for New Agents

All new MCP agents should follow the **Society of Mind pattern**:

**Reference implementations:**
- `src/MCP PLUGINS/servers/time/agent.py` (time operations)
- `src/MCP PLUGINS/servers/fetch/agent.py` (HTTP requests)
- `src/MCP PLUGINS/servers/n8n/agent.py` (workflow automation)

**Key components:**
1. Config class with BaseModel
2. Agent class with initialize(), _create_team(), run_task(), cleanup()
3. EventServer with session_id and tool_name
4. SESSION_ANNOUNCE event on initialization
5. BufferedChatCompletionContext for agents
6. RoundRobinGroupChat with termination conditions
7. Operator + QA_Validator pattern

---

**Last Updated:** 2025-10-08
**Status:** 6/18 agents using recommended pattern, 12/18 need migration

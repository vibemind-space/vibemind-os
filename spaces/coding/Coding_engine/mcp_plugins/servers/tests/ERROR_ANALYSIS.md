# MCP Tools Error Analysis

Analysed from session logs in `data/logs/sessions/` with new naming format `{tool}_{timestamp}_{session_id}.log`

## Summary

| Tool | Status | Primary Error | Severity |
|------|--------|---------------|----------|
| brave-search | ❌ FAIL | Missing `BRAVE_API_KEY` | HIGH |
| fetch | ❌ FAIL | `RuntimeError: generator didn't yield` | HIGH |
| n8n | ⚠️ WARNING | Process termination issues | LOW |
| sequential-thinking | ⚠️ WARNING | Process termination issues | LOW |
| time | ✅ PASS | No errors | - |
| github | ✅ PASS | No errors (credentials configured) | - |
| playwright | ✅ PASS | No errors | - |
| memory | ✅ PASS | No errors | - |
| filesystem | ✅ PASS | No errors | - |
| docker | ✅ PASS | No errors | - |
| desktop | ✅ PASS | No errors | - |
| context7 | ✅ PASS | No errors | - |
| redis | ✅ PASS | No errors | - |
| supabase | ✅ PASS | No errors | - |

## Detailed Error Reports

### 1. brave-search ❌

**Log File:** `brave-search_20251008_221641_nh6Pr5i-zdNT-SFwJQD8vw.log`

**Root Cause:**
```
Error: BRAVE_API_KEY environment variable is required
```

**Exception Chain:**
1. Missing `BRAVE_API_KEY` environment variable
2. MCP server fails to initialize
3. `mcp.shared.exceptions.McpError: Connection closed`
4. Cascades through AutoGen agent stack
5. RuntimeError in Society of Mind team coordination

**Stack Trace Depth:** 200+ lines

**Impact:** Complete failure - agent cannot execute any tasks

**Solution:**
```bash
export BRAVE_API_KEY="your_api_key_here"
```

**Related Files:**
- Agent: `src/MCP PLUGINS/servers/brave-search/agent.py`
- Config: `src/MCP PLUGINS/servers/servers.json` (requires env:BRAVE_API_KEY)

---

### 2. fetch ❌

**Log File:** `fetch_20251008_221720_J6nD27a3gdqYamQrT0ArBw.log`

**Root Cause:**
```
RuntimeError: generator didn't yield
```

**Error Details:**
```python
File "src/MCP PLUGINS/servers/fetch/agent.py", line 119, in initialize
RuntimeError: generator didn't yield
```

**Secondary Errors:**
- `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`
- `RuntimeError: athrow(): asynchronous generator is already running`

**Impact:** Agent initialization fails completely

**Analysis:**
The fetch MCP server's `create_mcp_server_session()` generator is not yielding properly. This is an **async context manager issue** in the agent implementation.

**Possible Causes:**
1. Incorrect async generator usage
2. Missing `yield` statement in context manager
3. Task cancellation scope mismatch
4. MCP server startup race condition

**Solution Required:**
Review `src/MCP PLUGINS/servers/fetch/agent.py` line 119 and ensure proper async context manager implementation.

---

### 3. n8n ⚠️

**Log File:** `n8n_20251008_221758_dpxMwVSeqWkGg-2e9XDSSg.log`

**Issue:**
```
Force taskkill also failed: FEHLER: Der Prozess "24148" wurde nicht gefunden.
```

**Analysis:**
Process termination cleanup issue - process exits before force-kill attempt. This is actually **not critical** as it indicates the process already terminated naturally.

**Impact:** LOW - Cleanup warning only, no functional impact

---

### 4. sequential-thinking ⚠️

**Log File:** `sequential-thinking_20251008_221827_B8daCBLg9vosYx83BIkCpA.log`

**Issue:**
```
Graceful taskkill failed: FEHLER: Der Prozess "32844" wurde nicht gefunden.
Force taskkill also failed: FEHLER: Der Prozess "32844" wurde nicht gefunden.
```

**Analysis:**
Same as n8n - process exits before termination commands execute.

**Impact:** LOW - Cleanup warning only

---

## Process Termination Pattern

**Tools Affected:** n8n, sequential-thinking, brave-search (partially)

**Pattern:**
```
1. Agent spawned with PID
2. Agent executes task
3. Session manager calls stop_agent()
4. Graceful taskkill fails (process already gone)
5. Force taskkill fails (process already gone)
6. Session cleanup completes successfully
```

**Root Cause:**
Windows process tree cleanup race condition - agent subprocess exits before parent can terminate it.

**Impact:**
- Logs show ERROR/WARNING but functionality is not impaired
- Process cleanup still succeeds
- No zombie processes left behind

**Recommendation:**
Enhance `stop_agent()` in `src/ui/mcp_session_manager.py` to:
1. Check if process exists before taskkill
2. Downgrade "process not found" from ERROR to INFO
3. Add process existence check: `proc.poll() is not None`

---

## Critical Errors Requiring Fixes

### Priority 1: fetch tool (BLOCKER)

**File:** `src/MCP PLUGINS/servers/fetch/agent.py`

**Line:** ~119

**Issue:** Async generator not yielding properly

**Fix Required:**
- Review async context manager implementation
- Ensure proper `yield` in generator
- Fix task cancellation scope issues

### Priority 2: brave-search (CONFIGURATION)

**Issue:** Missing environment variable

**Fix:**
Add to `.env` or environment:
```bash
BRAVE_API_KEY=your_key_here
```

Update `.env.example`:
```bash
# Brave Search API (optional)
BRAVE_API_KEY=
```

---

## Tools Working Correctly ✅

**11 tools tested successfully:**
- time, github, playwright, memory, filesystem
- docker, desktop, context7, redis, supabase

**Characteristics of working tools:**
- Proper async/await patterns
- Clean session initialization
- Graceful error handling
- No missing dependencies

---

## Recommendations

### Immediate Actions

1. **Fix fetch agent** - Critical bug blocking tool usage
2. **Document required API keys** - Update README with credential requirements
3. **Improve error messages** - Make missing credentials more obvious

### Code Improvements

1. **Process termination** - Check if process exists before taskkill
2. **Error logging** - Downgrade non-critical warnings
3. **Agent templates** - Create standard template with proven patterns

### Testing

1. **Add credential checks** - Validate env vars before agent spawn
2. **E2E tests** - Run after credential fixes to verify success
3. **Error handling tests** - Verify graceful degradation

---

## Log Naming Success ✅

**New format working perfectly:**
```
{tool}_{timestamp}_{session_id}.log

Examples:
- brave-search_20251008_221641_nh6Pr5i-zdNT-SFwJQD8vw.log
- fetch_20251008_221720_J6nD27a3gdqYamQrT0ArBw.log
- time_20251008_221258_Cjf-zpPjf4h2HpkIu-1Gog.log
```

**Benefits:**
- Instantly identify which tool generated the log
- Timestamp shows when session was created
- Session ID enables correlation with API calls
- Grep-friendly for error analysis: `grep -l "ERROR" data/logs/sessions/fetch_*.log`

---

## Next Steps

1. ✅ **Complete** - Session log naming implemented and verified
2. ⏳ **In Progress** - Error analysis from logs
3. 🔜 **Next** - Fix fetch agent async generator issue
4. 🔜 **Next** - Add credential validation before agent spawn
5. 🔜 **Next** - Update documentation with API key requirements

# Issue Detector — OpenFang Integration Guide

This document explains how OpenFang (or any external process) can trigger the
self-healing loop **without polling** — purely event-driven.

## Two Integration Paths

| Path | Use when | How |
|------|----------|-----|
| **A. MCP Tool Call** | OpenFang agent wants to report something it detected itself | Configure issue-detector as MCP server, agents call `trigger_event` |
| **B. File Drop** | Rust code in OpenFang core wants minimal-overhead reporting | Drop a JSON file into `event_drops/` |

Both run through the same reaction pipeline (`_react_to_event`) and end up as
pending findings the user reviews.

---

## Path A: MCP Tool Call (Agent-driven)

### Setup
Already configured. The issue-detector is registered in
`openfang/openfang.vibemind.toml` as `[[mcp_servers]]` with name `issue-detector`.

### Available Tools (for OpenFang Agents)
- `trigger_event(event_type, source, details, auto_react)`
- `notify_user(message, level)`
- `list_pending_findings(filter_space, filter_severity)`
- `scan_security()`, `scan_system_health()`, `scan_space(name)`

### Example: Security Auditor reports a finding
```python
# Inside an OpenFang agent
mcp_call("issue-detector", "trigger_event", {
    "event_type": "vulnerability_detected",
    "source": "openfang",
    "details": {
        "agent": "security-auditor",
        "space": "coding",
        "cve": "CVE-2025-12345",
        "severity": "HIGH",
    },
    "auto_react": True,
})
```

The detector will:
1. Record the event with auto-incrementing ID (E0001, E0002, ...)
2. React based on `source=openfang`: scan the referenced space + run security scan
3. Add findings to pending state with IDs (P0001, ...)
4. Write a `🚨 ALERT` notification to `vibemind_inbox.md`

### When to use Path A
- OpenFang agent has structured information about the problem
- You want the agent to participate in the reaction (e.g. attach extra context)
- You want the call to be auditable in OpenFang's tool-call log

---

## Path B: File Drop (Fire-and-Forget)

### Setup
Already configured. The watcher source `file_drop` is enabled by default in
`watcher_config.json`. The drop folder is auto-created on server boot:

```
vibemind-os/issue-detector/event_drops/
```

### Drop File Format
```json
{
  "source": "openfang",
  "event_type": "agent_panic",
  "details": {
    "agent": "security-auditor",
    "error": "Rust panic in tool execution",
    "space": "coding",
    "stack_trace": "..."
  }
}
```

The filename can be anything ending in `.json`. The watcher polls every
30 seconds (configurable), processes new files, and **deletes them after read**.
Broken JSON files are renamed to `.broken` instead of being deleted.

### Example: Rust Code in OpenFang
```rust
use serde_json::json;
use std::fs::File;
use std::path::PathBuf;

fn report_panic(agent: &str, error: &str, space: &str) -> std::io::Result<()> {
    let drop_dir = PathBuf::from(
        r"C:\Users\User\Desktop\Vibemind_V1\vibemind-os\issue-detector\event_drops"
    );
    std::fs::create_dir_all(&drop_dir)?;

    let event = json!({
        "source": "openfang",
        "event_type": "agent_panic",
        "details": {
            "agent": agent,
            "error": error,
            "space": space,
        }
    });

    let filename = format!("panic_{}.json", chrono::Utc::now().timestamp_millis());
    let path = drop_dir.join(filename);
    serde_json::to_writer(File::create(path)?, &event)?;
    Ok(())
}
```

### When to use Path B
- You're in low-level Rust code where calling out to an MCP tool would be heavy
- You want fire-and-forget semantics (no waiting for reaction)
- You want the integration to keep working even if the issue-detector is offline
  (drops queue up until next poll)
- You're integrating from a non-OpenFang process (CI/CD, systemd, cron job)

---

## Recommended Hook Points in OpenFang

These are places where adding event triggers would give the best ROI:

| OpenFang Module | Hook Event | Suggested `event_type` |
|-----------------|-----------|----------------------|
| `kernel/approval.rs` | Approval rejected | `approval_rejected` |
| `kernel/metering.rs` | Quota exceeded | `quota_exceeded` |
| `runtime/tool_runner.rs` | Tool execution error | `tool_failed` |
| `extensions/health.rs` | MCP server health degraded | `mcp_unhealthy` |
| `runtime/wasm.rs` | WASM sandbox violation | `wasm_violation` |
| `kernel/audit.rs` | Audit chain integrity broken | `audit_tamper` |
| Rust panic handler | Any unhandled panic | `rust_panic` |

For each, choose Path A (if you have agent context) or Path B (if you're in
synchronous Rust code). All result in pending findings the user reviews and
approves before they become GitHub issues.

---

## Verification

To verify the integration is working after a code change:

```python
# Drop a test event
import json
from pathlib import Path

drop_dir = Path(r"C:\Users\User\Desktop\Vibemind_V1\vibemind-os\issue-detector\event_drops")
drop_dir.mkdir(parents=True, exist_ok=True)

(drop_dir / "test.json").write_text(json.dumps({
    "source": "openfang",
    "event_type": "test_integration",
    "details": {"test": True}
}))
```

Then in Claude:
> "Show me triggered events and pending findings"

Claude will call `list_triggered_events()` and `list_pending_findings()` and
show you the test event landed in the system.

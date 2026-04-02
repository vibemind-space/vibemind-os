# MCP Tools E2E Tests

End-to-end tests for all MCP tools to verify functionality and detect errors in execution logs.

## Structure

```
tests/
├── README.md                    # This file
├── run_all_e2e_tests.py        # Master test runner for all tools
├── test_time_e2e.py            # Individual test for Time tool
├── test_github_e2e.py          # Individual test for GitHub tool
└── test_playwright_e2e.py      # Individual test for Playwright tool
```

## Test Workflow

Each E2E test follows this pattern:

1. **Create Session** - Initialize MCP tool session via API
2. **Start Agent** - Execute a tool-specific task
3. **Monitor Execution** - Track session status until completion
4. **Analyze Logs** - Check session logs for errors and exceptions
5. **Cleanup** - Delete session

## Running Tests

### Run All Tests

```bash
cd "src/MCP PLUGINS/servers/tests"
python run_all_e2e_tests.py
```

This will:
- Test 10+ MCP tools with real tasks
- Generate detailed report with pass/fail status
- Save JSON report to `data/test_results/`
- Show error summary for failed tests

### Run Individual Test

```bash
cd "src/MCP PLUGINS/servers/tests"
python test_time_e2e.py
python test_github_e2e.py
python test_playwright_e2e.py
```

## Test Coverage

| Tool | Task | Credentials Required |
|------|------|---------------------|
| **time** | UTC to PST timezone conversion | No |
| **github** | List recent VS Code issues | Yes (GITHUB_PERSONAL_ACCESS_TOKEN) |
| **playwright** | Navigate and screenshot | No |
| **fetch** | HTTP GET request | No |
| **memory** | Create knowledge graph entity | No |
| **filesystem** | List directory contents | No |
| **taskmanager** | Create task | No |
| **windows-core** | Get system info | No |
| **docker** | List containers | No |
| **desktop** | List files | No |

## Output

### Console Output

```
======================================================================
E2E Test: TIME
======================================================================

[1/4] Creating session...
[OK] Session created: abc123

[2/4] Starting agent...
[OK] Agent started with task: Get the current time in UTC and convert it to PST timezone

[3/4] Monitoring execution...
  [15s] Status: completed
[OK] Agent finished with status: completed

[4/4] Checking session logs...
[OK] Log file created: time_20251008_123456_abc123.log
[OK] No errors in log file

======================================================================
[SUCCESS] Time tool E2E test passed
======================================================================
```

### JSON Report

Reports saved to `data/test_results/e2e_test_report_YYYYMMDD_HHMMSS.json`:

```json
{
  "timestamp": "2025-10-08T22:30:00",
  "total": 10,
  "success": 8,
  "failed": 1,
  "skipped": 1,
  "results": [
    {
      "tool": "time",
      "status": "success",
      "duration": 15.3,
      "errors": [],
      "log_file": "time_20251008_123456_abc123.log"
    }
  ]
}
```

## Log File Verification

Tests verify the new log naming format:

**Format:** `{tool}_{timestamp}_{session_id}.log`

**Example:** `time_20251008_221258_Cjf-zpPjf4h2HpkIu-1Gog.log`

- **tool**: MCP tool name (time, github, playwright, etc.)
- **timestamp**: Creation time (YYYYMMDD_HHMMSS)
- **session_id**: Unique session identifier

## Error Detection

Tests scan logs for:
- `ERROR` level messages
- Python tracebacks (`Traceback`)
- Uncaught exceptions (`Exception`)
- Tool-specific failures

Filters out expected warnings:
- Deprecation warnings
- Agent spawn diagnostics
- Credential configuration notices

## Prerequisites

1. **Backend Running** - Sakana backend must be running on `http://127.0.0.1:8765`
2. **Credentials** - Set environment variables for tools requiring authentication:
   ```bash
   export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_xxx"
   export BRAVE_API_KEY="xxx"
   export TAVILY_API_KEY="xxx"
   ```
3. **Dependencies** - Install test dependencies:
   ```bash
   pip install requests
   ```

## Adding New Tests

To add a test for a new MCP tool:

1. **Copy template** from `test_time_e2e.py`
2. **Update tool name** and task
3. **Adjust timeout** based on expected execution time
4. **Add to TEST_CONFIGS** in `run_all_e2e_tests.py`

Example:

```python
'my-tool': {
    'task': 'Task description for my-tool',
    'timeout': 30,
    'requires_credentials': False
}
```

## Exit Codes

- `0` - All tests passed
- `1` - One or more tests failed

Use in CI/CD pipelines:

```bash
python run_all_e2e_tests.py || exit 1
```

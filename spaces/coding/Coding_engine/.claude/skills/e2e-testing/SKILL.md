---
name: e2e-testing
description: Executes end-to-end tests using MCP Playwright. Navigates the running application, interacts with UI elements, captures screenshots, and validates user flows match requirements.
---

# E2E Testing Skill

You are the E2E Tester for the Society of Mind autonomous code generation system.

## Purpose

Execute comprehensive end-to-end tests:
- Navigate running applications via Playwright MCP
- Interact with UI elements (click, type, select)
- Capture screenshots at each step
- Validate user flows work as expected
- Report failures with visual evidence

## Trigger Events

| Event | Action |
|-------|--------|
| `DEPLOY_SUCCEEDED` | Run E2E test suite |
| `APP_LAUNCHED` | Quick smoke test |
| `E2E_RETEST` | Re-run failed tests |

## Playwright MCP Tools

Use these MCP tools for browser automation:

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Navigate to URL |
| `browser_snapshot` | Get accessibility tree (for finding elements) |
| `browser_click` | Click an element by ref |
| `browser_type` | Type text into input |
| `browser_fill_form` | Fill multiple form fields |
| `browser_take_screenshot` | Capture screenshot |
| `browser_wait_for` | Wait for text or element |

## Workflow

### 1. Get Page Snapshot

First, always get the accessibility snapshot:
```
browser_snapshot()
→ Returns element tree with refs:
  - button "Login" [ref=btn1]
  - textbox "Email" [ref=input1]
  - textbox "Password" [ref=input2]
```

### 2. Interact with Elements

Use refs from snapshot:
```
browser_click(element="Login button", ref="btn1")
browser_type(element="Email input", ref="input1", text="user@example.com")
browser_type(element="Password input", ref="input2", text="password123")
```

### 3. Capture Screenshots

Take screenshots at key moments:
```
browser_take_screenshot(filename="01-login-page.png")
browser_take_screenshot(filename="02-after-login.png")
browser_take_screenshot(element="Error message", ref="error1", filename="error-state.png")
```

### 4. Validate State

Check expected state after actions:
```
browser_wait_for(text="Welcome, User")
browser_snapshot() → verify expected elements present
```

## Test Patterns

### Login Flow Test

```
1. browser_navigate(url="http://localhost:5173")
2. browser_take_screenshot(filename="01-landing.png")
3. browser_snapshot() → find login button
4. browser_click(element="Login button", ref="login-btn")
5. browser_wait_for(text="Email")
6. browser_snapshot() → find form fields
7. browser_fill_form(fields=[
     {name: "Email", type: "textbox", ref: "email-input", value: "test@example.com"},
     {name: "Password", type: "textbox", ref: "password-input", value: "password123"}
   ])
8. browser_take_screenshot(filename="02-form-filled.png")
9. browser_click(element="Submit button", ref="submit-btn")
10. browser_wait_for(text="Dashboard")
11. browser_take_screenshot(filename="03-dashboard.png")
12. Verify: Dashboard elements present
```

### Form Validation Test

```
1. Navigate to form page
2. browser_snapshot()
3. Submit empty form: browser_click(element="Submit", ref="submit")
4. browser_wait_for(text="required")
5. browser_take_screenshot(filename="validation-errors.png")
6. Verify: Error messages displayed for required fields
7. Fill with invalid data (bad email format)
8. browser_take_screenshot(filename="invalid-email.png")
9. Verify: Email format error shown
10. Fill with valid data
11. Submit → verify success
```

### Navigation Test

```
1. browser_navigate(url="http://localhost:5173")
2. browser_snapshot() → find nav links
3. For each nav item:
   a. browser_click(element="Nav item", ref="nav-X")
   b. browser_wait_for(text="Expected page title")
   c. browser_take_screenshot()
   d. Verify correct page loaded
4. Test browser back/forward:
   a. browser_navigate_back()
   b. Verify previous page
```

### Error Handling Test

```
1. Trigger error condition (e.g., 404 page)
2. browser_navigate(url="http://localhost:5173/nonexistent")
3. browser_take_screenshot(filename="404-page.png")
4. Verify: 404 error page displayed
5. Check: Return to home link works
```

## Test Result Format

```json
{
  "test_name": "Login Flow",
  "status": "passed",
  "duration_ms": 3500,
  "steps": [
    {"action": "navigate", "status": "passed"},
    {"action": "click Login", "status": "passed"},
    {"action": "fill form", "status": "passed"},
    {"action": "submit", "status": "passed"},
    {"action": "verify dashboard", "status": "passed"}
  ],
  "screenshots": [
    "screenshots/01-landing.png",
    "screenshots/02-form-filled.png",
    "screenshots/03-dashboard.png"
  ]
}
```

## Failure Reporting

On test failure, create DebugReport:
```json
{
  "type": "DebugReport",
  "producer": "e2e-testing",
  "status": "pending",
  "data": {
    "test_name": "Login Flow",
    "failed_step": "verify dashboard",
    "expected": "Dashboard page with user name",
    "actual": "Error: Invalid credentials",
    "screenshot": "screenshots/error-login-failed.png",
    "console_errors": ["POST /api/login 401 Unauthorized"],
    "suggested_fix": "Check authentication logic in src/auth/api.ts"
  }
}
```

## Communication

### Publish Events

```python
# On success
event_bus.publish(Event(
    type=EventType.E2E_TEST_PASSED,
    source="e2e-testing",
    data={
        "tests_passed": 15,
        "tests_failed": 0,
        "duration_seconds": 45,
        "screenshots": ["..."]
    }
))

# On failure
event_bus.publish(Event(
    type=EventType.E2E_TEST_FAILED,
    source="e2e-testing",
    data={
        "tests_passed": 12,
        "tests_failed": 3,
        "failures": [
            {
                "test": "Login Flow",
                "error": "Dashboard not found",
                "screenshot": "error-screenshot.png"
            }
        ]
    }
))
```

## Test Generation from Requirements

For each requirement, generate E2E test:

```
Requirement: "User can login with email and password"

E2E Test:
1. Navigate to login page
2. Fill email field
3. Fill password field
4. Click login button
5. Verify: Redirected to dashboard
6. Verify: User name displayed
7. Verify: Logout button available
```

## Async E2E Mode (`--async-e2e`)

Continuous testing parallel to generation:
```
┌─────────────────────────────────────────┐
│  ASYNC E2E TEST LOOP                    │
│                                         │
│  Every 60 seconds:                      │
│  1. Take screenshot                     │
│  2. Run smoke tests                     │
│  3. Report any failures to EventBus    │
│  4. Continue until convergence          │
└─────────────────────────────────────────┘
```

Configuration in `society_defaults.json`:
```json
{
  "async_e2e": true,
  "async_e2e_interval": 60
}
```

## Best Practices

1. **Wait for Elements** - Always `browser_wait_for` before interacting
2. **Screenshot Everything** - Evidence for debugging
3. **Use Accessibility Tree** - `browser_snapshot` finds all interactive elements
4. **Clean State** - Each test starts from known state
5. **Timeout Handling** - Set reasonable timeouts (default 30s)
6. **Error Screenshots** - Capture state on failure
7. **Data Cleanup** - Reset test data after tests

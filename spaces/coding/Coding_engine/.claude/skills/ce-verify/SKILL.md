# ce-verify — Autonomous Code Verification

## Purpose
Verify that generated code actually works — not just that tasks are marked "completed" in the DB.
This skill performs real verification: file existence, build check, runtime test, browser E2E.

## Trigger
- After `!fixall` completes with 0 errors
- After generation finishes
- Manual: `!verify [project]`

## Verification Steps

### Step 1: File Existence Check
```bash
# Count generated files (expect >10 for a real project)
find $OUTPUT_DIR/src -type f | wc -l
find $OUTPUT_DIR/frontend -type f | wc -l
ls $OUTPUT_DIR/prisma/schema.prisma
ls $OUTPUT_DIR/package.json
```

### Step 2: Build Check
```bash
cd $OUTPUT_DIR && npm run build 2>&1
# OR for TypeScript-only check:
cd $OUTPUT_DIR && npx tsc --noEmit 2>&1
```

### Step 3: Prisma Validation
```bash
cd $OUTPUT_DIR && npx prisma validate 2>&1
cd $OUTPUT_DIR && npx prisma db push --accept-data-loss 2>&1
```

### Step 4: Lint Check
```bash
cd $OUTPUT_DIR && npx eslint 'src/**/*.{ts,tsx}' 2>&1 | tail -20
```

### Step 5: Runtime Check (if app can start)
```bash
cd $OUTPUT_DIR && timeout 15 npm run start 2>&1 | tail -10
# Check if server starts on expected port
curl -s http://localhost:3100 | head -5
```

### Step 6: Browser E2E (via Playwright MCP)
- Navigate to http://localhost:3100
- Take screenshot
- Check for error messages in DOM
- Check console for JS errors
- Verify key pages load (login, dashboard, etc.)

## Verification Report Format
```
📋 Verification Report:
📁 Files: 142 (src: 98, frontend: 44)
🏗️ Build: ✅ PASS
📐 Prisma: ✅ 41 models synced
🧹 Lint: ⚠️ 3 warnings (no errors)
🌐 Runtime: ✅ Server started on :3100
🖥️ Browser: ✅ Login page renders correctly

Overall: ✅ VERIFIED — ready for PR
```

## Decision Matrix
| Check | Result | Action |
|-------|--------|--------|
| Build PASS + Runtime PASS | ✅ | Create PR |
| Build PASS + Runtime FAIL | ⚠️ | Fix runtime errors, retry |
| Build FAIL | ❌ | Run !fixall, retry verify |
| Files < 10 | ❌ | Generation incomplete, restart |

## Output
- Posts verification report to Discord #dev-tasks
- If VERIFIED: triggers PR creation
- If FAILED: triggers !fixall with specific error context

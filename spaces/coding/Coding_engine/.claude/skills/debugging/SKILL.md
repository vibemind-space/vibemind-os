---
name: debugging
description: Analyzes build failures, runtime errors, and test failures. Parses error logs, traces root causes, syncs file changes to containers, and coordinates fixes across the system.
tier_tokens:
  minimal: 80
  standard: 200
  full: 400
---

# Debugging

## MUST

- Parse errors into structured format (file, line, code, message)
- Trace to root cause (not just symptoms)
- Verify fix after applying
- Sync files to container after fix

## MUST NOT

- No guessing without evidence
- No fixing symptoms without root cause
- No leaving container out of sync

## TypeScript Errors

| Code   | Meaning              | Fix                         |
| ------ | -------------------- | --------------------------- |
| TS2339 | Property not found   | Add to interface or fix typo |
| TS2322 | Type not assignable  | Cast or convert type         |
| TS2307 | Module not found     | Install package or create file |
| TS2345 | Argument mismatch    | Fix parameter types          |
| TS2532 | Possibly undefined   | Add null check `?.`          |

<!-- END_TIER_MINIMAL -->

## React Errors

| Error                      | Cause                  | Fix                     |
| -------------------------- | ---------------------- | ----------------------- |
| Invalid hook call          | Hook outside component | Move into component     |
| Too many re-renders        | State update in render | Use useEffect           |
| Can't update unmounted     | Async after unmount    | Cleanup in useEffect    |
| Each child needs key       | Missing key in list    | Add unique key prop     |

## Runtime Errors

| Error                      | Cause         | Fix                    |
| -------------------------- | ------------- | ---------------------- |
| Cannot read 'X' of undefined | Null access | Optional chaining `?.` |
| Maximum call stack         | Infinite loop | Fix recursion          |
| Failed to fetch            | Network/CORS  | Check URL, add handler |

<!-- END_TIER_STANDARD -->

## Container Debugging

```bash
# Sync file to container
docker cp src/App.tsx sandbox-runner:/app/src/App.tsx

# Get logs
docker logs sandbox-runner --tail 100

# Trigger hot-reload
docker exec sandbox-runner pkill -HUP node
```

## Debug Strategy

1. Parse structured error data
2. Categorize severity (critical > high > medium)
3. Trace to root cause
4. Generate fix suggestion
5. Apply fix + sync to container
6. Verify fix resolved error

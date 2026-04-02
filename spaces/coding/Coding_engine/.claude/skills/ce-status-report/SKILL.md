---
name: ce-status-report
description: Generate a comprehensive Coding Engine status report in under 60 seconds. Covers DB task stats, generated files, generation loop progress, container health, Discord bot status, and error analysis.
trigger: When user asks for status, progress, "how's the generation going", "what's the current state", "status report", or "show me where we are"
---

# ce-status-report — Comprehensive Engine Status Report

Generate a full status report by running these checks IN PARALLEL where possible.

## Step 1: Gather Data (run all in parallel)

### 1a. DB Task Stats
```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -t -c "
SELECT status, COUNT(*) FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) GROUP BY status ORDER BY status;"
```

### 1b. Task Breakdown by Type
```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -t -c "
SELECT
  CASE
    WHEN task_id LIKE '%FE-%' THEN 'FRONTEND'
    WHEN task_id LIKE '%API-%' THEN 'API'
    WHEN task_id LIKE '%SCHEMA%' THEN 'SCHEMA'
    WHEN task_id LIKE '%VERIFY%' THEN 'VERIFY'
    WHEN task_id LIKE '%SETUP%' THEN 'SETUP'
    ELSE 'OTHER'
  END as type, status, COUNT(*)
FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs)
GROUP BY 1, 2 ORDER BY 1, 2;"
```

### 1c. Generated Files Count
```bash
docker exec coding-engine-api bash -c "
echo 'TS/TSX files:' && find /app/output/*/src -type f \( -name '*.ts' -o -name '*.tsx' \) 2>/dev/null | grep -v node_modules | wc -l
echo 'Total src size:' && du -sh /app/output/*/src/ 2>/dev/null
echo 'Frontend pages:' && find /app/output/*/frontend/src -name '*.tsx' 2>/dev/null | grep -v node_modules | wc -l
echo 'Backend modules:' && ls /app/output/*/src/modules/ 2>/dev/null | wc -l"
```

### 1d. Generation Loop Status
```bash
docker exec coding-engine-api bash -c "
echo '=== LOCK ===' && cat /app/output/*/.generation_running 2>/dev/null || echo 'NO LOCK'
echo '=== LAST LOG ===' && tail -5 /app/output/*/generation.log 2>/dev/null
echo '=== ROUNDS ===' && grep 'GENERATION ROUND\|Round.*result\|No progress\|GENERATION LOOP' /app/output/*/generation.log 2>/dev/null | tail -5"
```

Also check if the process is running:
```bash
docker top coding-engine-api 2>/dev/null | grep run_generation | head -1 || echo "NOT RUNNING"
```

### 1e. Container Health
```bash
docker ps --format "{{.Names}} {{.Status}}" | grep coding-engine
```

### 1f. Recent Errors
```bash
docker exec coding-engine-api bash -c "grep -i 'ERROR\|FAILED\|402\|429\|500' /app/output/*/generation.log 2>/dev/null | grep -v 'subscriber\|entity_req\|debug' | tail -10"
```

### 1g. Discord Bot Status
```bash
docker logs coding-engine-automation-ui --tail 5 2>&1 | grep -i "status\|error\|POST.*discord"
```

### 1h. LLM Usage (if available)
```bash
docker exec coding-engine-api bash -c "cat /app/Data/all_services/*/_checkpoints/llm_usage.json 2>/dev/null | python3 -c \"
import json,sys
d=json.load(sys.stdin)
print('Total cost: \$%.2f' % d.get('total_cost_usd', 0))
print('Total calls:', d.get('total_calls', 0))
print('Avg latency: %dms' % d.get('avg_latency_ms', 0))
\" 2>/dev/null || echo 'No usage data'"
```

## Step 2: Format Report

Present as a structured table:

```
# 📊 Coding Engine Status Report

## Generation
| Metrik | Wert |
|--------|------|
| Round | X/10 |
| Process | Running/Stopped |
| Elapsed | Xm |

## Tasks (Total: XXXX)
| Status | Count | % |
|--------|-------|---|
| COMPLETED | X | X% |
| FAILED | X | X% |
| PENDING | X | X% |
| ...

## Task Breakdown
| Type | Completed | Failed | Pending |
|------|-----------|--------|---------|

## Generated Files
| Metric | Count |
|--------|-------|
| .ts/.tsx files | X |
| Frontend pages | X |
| Backend modules | X |
| Total src size | X |

## Containers
| Container | Status |
|-----------|--------|

## Recent Errors
- Error 1
- Error 2

## LLM Usage
| Metric | Value |
|--------|-------|
| Cost | $X |
| Calls | X |
```

## Step 3: Insights

After presenting data, add a **Insights** section:
- Is the generation making progress? (compare completed count to previous)
- Are there cascade failures? (many SKIPPED = dependency chain broken)
- Are there cost concerns? (high LLM usage with low file output)
- Is the bot alive? (can it auto-fix?)
- Any containers unhealthy?

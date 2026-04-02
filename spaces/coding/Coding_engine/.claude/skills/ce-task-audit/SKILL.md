---
name: ce-task-audit
description: Audit task splitting, dependency chains, and identify bottlenecks. Finds over-granular tasks, broken dependency chains, cascade failures, and suggests consolidation. Answers "why are there 2000+ tasks?" and "why are tasks stuck?"
trigger: When user asks about "task splitting", "why so many tasks", "task audit", "dependency analysis", "why are tasks cancelled/skipped", "bottleneck analysis"
---

# ce-task-audit — Task Splitting & Dependency Audit

## Step 1: Task Statistics

```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -t -c "
-- Overall stats
SELECT 'Total tasks', COUNT(*) FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs)
UNION ALL
SELECT 'Unique task types', COUNT(DISTINCT
  CASE
    WHEN task_id LIKE '%controller' THEN 'controller'
    WHEN task_id LIKE '%service' THEN 'service'
    WHEN task_id LIKE '%dto' THEN 'dto'
    WHEN task_id LIKE '%guard' THEN 'guard'
    WHEN task_id LIKE '%validation' THEN 'validation'
    WHEN task_id LIKE '%model' THEN 'model'
    WHEN task_id LIKE '%migration' THEN 'migration'
    WHEN task_id LIKE '%relations' THEN 'relations'
    WHEN task_id LIKE '%FE-%' THEN 'frontend'
    WHEN task_id LIKE '%VERIFY%' THEN 'verify'
    WHEN task_id LIKE '%SETUP%' THEN 'setup'
    ELSE 'other'
  END
) FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs);"
```

## Step 2: Task Type Distribution

```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "
SELECT
  CASE
    WHEN task_id LIKE '%-controller' THEN 'API-controller'
    WHEN task_id LIKE '%-service' THEN 'API-service'
    WHEN task_id LIKE '%-dto' THEN 'API-dto'
    WHEN task_id LIKE '%-guard' THEN 'API-guard'
    WHEN task_id LIKE '%-validation' THEN 'API-validation'
    WHEN task_id LIKE '%-model' THEN 'SCHEMA-model'
    WHEN task_id LIKE '%-migration' THEN 'SCHEMA-migration'
    WHEN task_id LIKE '%-relations' THEN 'SCHEMA-relations'
    WHEN task_id LIKE '%FE-%page' THEN 'FE-page'
    WHEN task_id LIKE '%FE-%hook' THEN 'FE-hook'
    WHEN task_id LIKE '%FE-%component%' THEN 'FE-component'
    WHEN task_id LIKE '%FE-%form' THEN 'FE-form'
    WHEN task_id LIKE '%FE-%api' THEN 'FE-api-client'
    WHEN task_id LIKE '%VERIFY%' THEN 'VERIFY'
    WHEN task_id LIKE '%SETUP%' THEN 'SETUP'
    WHEN task_id LIKE '%CHECKPOINT%' THEN 'CHECKPOINT'
    ELSE 'OTHER'
  END as task_type,
  COUNT(*) as total,
  SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) as completed,
  SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) as failed,
  SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) as pending,
  SUM(CASE WHEN status IN ('CANCELLED','SKIPPED') THEN 1 ELSE 0 END) as skipped
FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs)
GROUP BY 1 ORDER BY total DESC;"
```

## Step 3: Epic Size Analysis

```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "
SELECT
  SPLIT_PART(task_id, '-', 1) || '-' || SPLIT_PART(task_id, '-', 2) as epic,
  COUNT(*) as total_tasks,
  SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) as completed,
  ROUND(100.0 * SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) / COUNT(*), 1) as pct
FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs)
GROUP BY 1 ORDER BY 1;"
```

## Step 4: Dependency Chain Analysis

```bash
docker exec coding-engine-api bash -c '
python3 -c "
import json, glob
from collections import Counter

dep_chains = Counter()
orphan_skips = 0
cascade_roots = set()

for f in sorted(glob.glob(\"/app/Data/all_services/*/tasks/epic-*-tasks-enriched.json\")):
    data = json.loads(open(f).read())
    task_map = {t[\"id\"]: t for t in data.get(\"tasks\", [])}

    for t in data.get(\"tasks\", []):
        if t.get(\"status\") in (\"skipped\", \"cancelled\"):
            # Find which dependency failed
            for dep in t.get(\"dependencies\", []):
                dep_task = task_map.get(dep, {})
                if dep_task.get(\"status\") in (\"failed\", \"skipped\"):
                    cascade_roots.add(dep)
                    dep_chains[dep] += 1

print(\"=== TOP CASCADE ROOTS (tasks whose failure cancelled the most others) ===\")
for tid, count in dep_chains.most_common(10):
    print(f\"  {tid}: cancelled {count} downstream tasks\")

print(f\"\nTotal cascade roots: {len(cascade_roots)}\")
print(f\"Total skipped by cascade: {sum(dep_chains.values())}\")
"
'
```

## Step 5: Consolidation Analysis

```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "
-- How many unique API endpoints have 5+ tasks?
SELECT endpoint, COUNT(*) as task_count FROM (
  SELECT
    REGEXP_REPLACE(task_id, '-(controller|service|dto|guard|validation|module)$', '') as endpoint
  FROM tasks
  WHERE job_id=(SELECT MAX(id) FROM jobs) AND task_id LIKE '%API%'
) sub
GROUP BY endpoint
HAVING COUNT(*) >= 4
ORDER BY task_count DESC
LIMIT 10;"
```

## Step 6: Report

```
# 📋 Task Audit Report

## Task Explosion Analysis
- Total tasks: XXXX
- API tasks: XXXX (XX% — controller/service/dto/guard/validation split)
- If consolidated to 1-per-endpoint: ~XXX tasks (XX% reduction)

## Dependency Chain Health
- Cascade root failures: X tasks caused Y downstream cancellations
- Worst offender: TASK-ID (cancelled X tasks)

## Epic Balance
| Epic | Tasks | % Complete |
|------|-------|------------|

## Consolidation Recommendation
- Current: X tasks × Y LLM calls = Z total calls
- Consolidated: X tasks × Y LLM calls = Z total calls
- Savings: XX% fewer calls, $XX estimated cost reduction

## Bottlenecks
1. ...
2. ...
```

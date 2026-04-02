---
name: ce-pipeline-doctor
description: Diagnoses pipeline problems and outputs actionable fix commands. Combines insights from status-report, code-quality, task-audit, and health-check into concrete recommendations with copy-paste-ready commands. Answers "what should I do next?" and "why is generation stuck?"
trigger: When user asks "what's wrong", "fix the pipeline", "what should I do next", "why is it stuck", "diagnose", "doctor", "help me fix this"
---

# ce-pipeline-doctor — Pipeline Diagnosis & Action Plan

Run a full diagnosis, then output a prioritized action plan with ready-to-execute commands.

## Phase 1: Quick Triage (10 seconds)

Run these checks to classify the problem:

```bash
# ONE-SHOT TRIAGE
echo "=== CONTAINERS ===" && docker ps -a --format "{{.Names}} {{.Status}}" | grep coding-engine | sort
echo "=== API HEALTH ===" && curl -s --max-time 3 http://localhost:8000/health 2>&1 || echo "API DOWN"
echo "=== GENERATION ===" && docker top coding-engine-api 2>/dev/null | grep run_generation | head -1 || echo "NOT RUNNING"
echo "=== DB TASKS ===" && docker exec coding-engine-postgres psql -U postgres -d coding_engine -t -c "SELECT status, COUNT(*) FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) GROUP BY status ORDER BY status;" 2>&1
echo "=== LAST ERROR ===" && docker exec coding-engine-api bash -c "grep 'ERROR\|OOM\|Kill\|Exit\|FAILED' /app/output/*/generation.log 2>/dev/null | grep -v 'subscriber\|entity_req\|_initialized\|enrichment' | tail -3" 2>&1
echo "=== STALE RUNNING ===" && docker exec coding-engine-postgres psql -U postgres -d coding_engine -t -c "SELECT COUNT(*) FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) AND status='RUNNING';" 2>&1
echo "=== MEMORY ===" && docker stats coding-engine-api --no-stream --format "{{.MemUsage}}" 2>/dev/null || echo "Container not running"
```

## Phase 2: Classify Problem

Based on triage results, classify into one of these categories:

### Category A: Container Down
- Symptom: API/Bot/Sandbox container Exited
- Check exit code: 137=OOM, 139=SIGSEGV, 255=restart-failure

### Category B: Generation Stuck/Dead
- Symptom: `run_generation.py` not in process list but RUNNING tasks in DB
- Stale RUNNING tasks = generation crashed mid-execution

### Category C: Cascade Failure
- Symptom: Many CANCELLED/SKIPPED tasks, few FAILED
- Root cause: One upstream task failed → all dependents cancelled

### Category D: LLM Issues
- Symptom: 402 Payment Required, 429 Rate Limit, timeouts
- Check which LLM backend and if credits are available

### Category E: Task Explosion
- Symptom: 2000+ PENDING tasks, generation runs but completes quickly with few results
- Root cause: Tasks too granular, LLM calls wasted on tiny files

### Category F: Code Quality Issues
- Symptom: Build fails, wrong imports, empty generated files
- Check: react-native in backend, missing prisma client, etc.

## Phase 3: Generate Action Plan

For each problem found, output a **numbered action** with the **exact command** to fix it.

### Template Actions:

#### Fix A: Container Down (OOM)
```
ACTION 1: Restart container with memory limit
  docker compose up -d api

ACTION 2: Set memory limit in docker-compose.yml
  deploy:
    resources:
      limits:
        memory: 4G

ACTION 3: Reduce parallelism to lower memory usage
  # In engine_settings.yml: generation.parallelism: 2 (was 3)
```

#### Fix B: Generation Stuck
```
ACTION 1: Reset stale RUNNING tasks
  docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "UPDATE tasks SET status='PENDING' WHERE job_id=(SELECT MAX(id) FROM jobs) AND status='RUNNING';"

ACTION 2: Remove stale lock file
  docker exec coding-engine-api bash -c "rm -f /app/output/*/.generation_running"

ACTION 3: Restart generation
  docker exec -d coding-engine-api bash -c "cd /app && python run_generation.py --project-path /app/Data/all_services/whatsapp-messaging-service_20260211_025459 --output-dir /app/output/whatsapp-messaging-service_20260211_025459 --project-id whatsapp-messaging-service --db-schema whatsapp_app --parallelism 2 --max-rounds 10 >> /app/output/whatsapp-messaging-service_20260211_025459/generation.log 2>&1"
```

#### Fix C: Cascade Failure
```
ACTION 1: Find cascade roots
  docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "SELECT task_id, status, status_message FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) AND status='FAILED' LIMIT 10;"

ACTION 2: Fix root failures (usually schema/migration)
  # If migrations: mark as COMPLETED (schema already synced)
  docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "UPDATE tasks SET status='COMPLETED', status_message='Schema already synced' WHERE job_id=(SELECT MAX(id) FROM jobs) AND task_id LIKE '%migration%' AND status='FAILED';"

ACTION 3: Reset cancelled tasks and regenerate
  docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "UPDATE tasks SET status='PENDING' WHERE job_id=(SELECT MAX(id) FROM jobs) AND status IN ('CANCELLED','SKIPPED');"
```

#### Fix D: LLM Issues
```
ACTION 1: Check API key balance
  curl -s https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $OPENROUTER_API_KEY" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['usage'])"

ACTION 2: Switch to OpenAI if OpenRouter empty
  # In docker-compose.yml: LLM_BACKEND=openai
  docker compose up -d api

ACTION 3: Use free models as fallback
  # In engine_settings.yml: models.fixing.model: qwen/qwen3-coder:free
```

#### Fix E: Task Explosion
```
ACTION 1: Count the damage
  docker exec coding-engine-postgres psql -U postgres -d coding_engine -t -c "SELECT 'API tasks: ' || COUNT(*) FROM tasks WHERE job_id=(SELECT MAX(id) FROM jobs) AND task_id LIKE '%API%';"

ACTION 2: Mark redundant sub-tasks as COMPLETED
  # Keep only -controller tasks, mark -guard, -validation as done
  docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "UPDATE tasks SET status='COMPLETED', status_message='Consolidated: generated with controller' WHERE job_id=(SELECT MAX(id) FROM jobs) AND (task_id LIKE '%-guard' OR task_id LIKE '%-validation') AND status='PENDING';"

ACTION 3: For future projects: modify epic_task_generator.py
  # Change _generate_api_tasks() to create 1 task per endpoint group instead of 5
```

#### Fix F: Code Quality
```
ACTION 1: Remove react-native imports from backend
  docker exec coding-engine-api bash -c "cd /app/output/*/ && rm -f src/api/loginpageAPI.ts src/api/registerpageAPI.ts src/api/twofactorauthAPI.ts"

ACTION 2: Generate prisma client
  docker exec coding-engine-api bash -c "cd /app/output/*/ && DATABASE_URL='postgresql://postgres:postgres@postgres:5432/whatsapp_app?schema=public' npx prisma generate"

ACTION 3: Run build check
  docker exec coding-engine-api bash -c "cd /app/output/*/ && npx tsc --noEmit 2>&1 | head -20"
```

## Phase 4: Priority Matrix

After generating actions, present them in priority order:

```
# 🏥 Pipeline Doctor — Diagnosis

## Problem: [Category Name]
[One sentence description]

## Action Plan (in order):

| # | Action | Impact | Command Ready? |
|---|--------|--------|----------------|
| 1 | [Most urgent] | HIGH | ✅ |
| 2 | [Next] | HIGH | ✅ |
| 3 | [Nice to have] | MEDIUM | ✅ |

## Commands to Execute:
[Copy-paste ready block of all commands in sequence]

## Expected Outcome:
- After Action 1: [what changes]
- After Action 2: [what changes]
- After all actions: [final state]
```

## Phase 5: Verify

After actions are executed, re-run Phase 1 triage to confirm fixes worked.

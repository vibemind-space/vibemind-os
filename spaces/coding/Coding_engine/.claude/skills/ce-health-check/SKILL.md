---
name: ce-health-check
description: Quick health check of all Coding Engine infrastructure. Checks containers, DB connectivity, API endpoints, Discord bot, sandbox preview, LLM API keys, and generation process. Takes 15 seconds.
trigger: When user asks "is everything running", "health check", "check infrastructure", "what's broken", "container status"
---

# ce-health-check — Infrastructure Health Check

Run ALL checks in parallel for speed (target: 15 seconds).

## Checks

### 1. Containers
```bash
docker ps --format "{{.Names}} {{.Status}}" | grep coding-engine | sort
```
Expected: api (healthy), postgres (healthy), redis (healthy), sandbox (healthy), automation-ui (healthy), openclaw (healthy)

### 2. API Health
```bash
curl -s --max-time 3 http://localhost:8000/health
```
Expected: `{"status":"healthy"}`

### 3. DB Connectivity
```bash
docker exec coding-engine-postgres psql -U postgres -d coding_engine -c "SELECT COUNT(*) FROM tasks;" 2>&1
```

### 4. Redis
```bash
docker exec coding-engine-redis redis-cli ping
```

### 5. Sandbox Preview
```bash
curl -s --max-time 3 http://localhost:3100 2>/dev/null | head -1
curl -s --max-time 3 http://localhost:6090 2>/dev/null | head -1
```

### 6. Discord Bot
```bash
docker logs coding-engine-automation-ui --tail 3 2>&1
```

### 7. LLM API Keys
```bash
docker exec coding-engine-api bash -c "
echo 'OPENAI_API_KEY:' && [ -n \"\$OPENAI_API_KEY\" ] && echo 'SET' || echo 'MISSING'
echo 'OPENROUTER_API_KEY:' && [ -n \"\$OPENROUTER_API_KEY\" ] && echo 'SET' || echo 'MISSING'
echo 'ANTHROPIC_API_KEY:' && [ -n \"\$ANTHROPIC_API_KEY\" ] && echo 'SET' || echo 'MISSING'
echo 'LLM_BACKEND:' \$LLM_BACKEND
echo 'GITHUB_TOKEN:' && [ -n \"\$GITHUB_TOKEN\" ] && echo 'SET' || echo 'MISSING'
echo 'DISCORD_BOT_TOKEN:' && [ -n \"\$DISCORD_BOT_TOKEN\" ] && echo 'SET' || echo 'MISSING'
"
```

### 8. Generation Process
```bash
docker top coding-engine-api 2>/dev/null | grep run_generation | head -1 || echo "NO GENERATION RUNNING"
```

### 9. Disk Space
```bash
docker exec coding-engine-api bash -c "df -h /app/output | tail -1"
```

### 10. OpenRouter Credits (if used)
```bash
curl -s https://openrouter.ai/api/v1/auth/key \
  -H "Authorization: Bearer $(docker exec coding-engine-api bash -c 'echo $OPENROUTER_API_KEY')" 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print('Usage: \$%.2f' % d.get('usage',0))" 2>/dev/null || echo "Cannot check"
```

## Report Format

```
# 🏥 Health Check

| Service | Status | Details |
|---------|--------|---------|
| API | ✅/❌ | |
| Postgres | ✅/❌ | X tasks in DB |
| Redis | ✅/❌ | |
| Sandbox | ✅/❌ | Preview on :3100 |
| VNC | ✅/❌ | Emulator on :6090 |
| Discord Bot | ✅/❌ | |
| Generation | 🔄/⏹️ | Round X/10 |
| OpenAI Key | ✅/❌ | |
| OpenRouter | ✅/❌ | $X used |
| Disk | ✅/⚠️ | X% used |

Issues: X found
```

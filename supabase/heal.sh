#!/bin/bash
# Supabase Self-Healing Script
# Restart crashed containers, flush Kong DNS cache.
# Run when `curl http://localhost:54321/rest/v1/...` returns 503.

set -e

echo "=== Supabase Heal ==="

# 1. Find exited containers and restart them
EXITED=$(docker ps -a --filter "name=supabase" --filter "status=exited" --format "{{.Names}}")
if [ -n "$EXITED" ]; then
  echo "Restarting exited containers:"
  for c in $EXITED; do
    # Skip vector container (known Windows issue)
    if [[ "$c" == *"vector"* ]]; then
      echo "  SKIP $c (vector has Windows Docker socket issue)"
      continue
    fi
    echo "  $c"
    docker start "$c" > /dev/null
  done
fi

# 2. Stop vector container if running (causes DNS issues)
if docker ps --filter "name=supabase_vector" --format "{{.Names}}" | grep -q vector; then
  echo "Stopping supabase_vector (crashes on Windows)..."
  docker stop supabase_vector_supabase > /dev/null 2>&1 || true
fi

# 3. Restart Kong to flush DNS cache
echo "Restarting Kong (flush DNS)..."
docker restart supabase_kong_supabase > /dev/null

# 4. Wait for Kong to come back
for i in 1 2 3 4 5; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 \
    "http://localhost:54321/rest/v1/ideas?limit=1" \
    -H "apikey: sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH" 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "Supabase healthy: HTTP $STATUS"
    exit 0
  fi
  sleep 1
done

echo "Supabase still unhealthy after restart. Check logs:"
echo "  docker logs supabase_kong_supabase --tail 20"
echo "  docker logs supabase_rest_supabase --tail 20"
exit 1

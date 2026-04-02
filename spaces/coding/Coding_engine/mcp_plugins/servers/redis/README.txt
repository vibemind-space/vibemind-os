MCPTools Scaffold: redis.db_interaction

Purpose: Placeholder for Redis database/kv interaction MCP server/tool (GET/SET, pubsub, streams, scripts).
Status: scaffold only (no transport/runtime implementation yet)

Notes:
- Intended to expose Redis operations via MCP.
- Configure via env vars or config.yaml. Do not commit secrets.
- Add an inactive servers.json entry until implementation is complete.
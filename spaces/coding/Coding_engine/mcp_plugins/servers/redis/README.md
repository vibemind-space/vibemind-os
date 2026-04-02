# Redis MCP Server

AutoGen agent wrapper for Redis MCP server integration.

## Overview

Redis MCP provides access to Redis key-value store operations, caching, vector search, and JSON document storage. It enables high-performance data operations for the Sakana Desktop Assistant.

## Features

- **Key-Value Operations**: GET, SET, DEL, EXISTS, EXPIRE
- **Data Structures**: Strings, Hashes, Lists, Sets, Sorted Sets
- **JSON Support**: Store and query JSON documents
- **Vector Search**: Embeddings and similarity search
- **Caching**: TTL-based expiration for temporary data
- **Pub/Sub**: Real-time messaging
- **Transactions**: Atomic multi-command operations
- **Pipelining**: Batch operations for performance

## Prerequisites

**Redis Server Required**:
- Redis 6.0+ installed and running
- Default port: 6379
- Install: https://redis.io/download

**Installation Options**:

### Windows
```bash
# Via Chocolatey
choco install redis-64

# Via WSL
wsl sudo apt-get install redis-server
wsl sudo service redis-server start
```

### macOS
```bash
brew install redis
brew services start redis
```

### Linux
```bash
sudo apt-get install redis-server
sudo systemctl start redis-server
```

### Docker
```bash
docker run -d -p 6379:6379 redis:latest
```

## Configuration

### servers.json

```json
{
  "name": "redis",
  "active": true,
  "type": "stdio",
  "command": "C:\\Windows\\System32\\cmd.exe",
  "args": ["/c", "npx", "-y", "@modelcontextprotocol/server-redis"],
  "read_timeout_seconds": 120,
  "env_vars": {
    "REDIS_URL": "env:REDIS_URL"
  },
  "description": "Redis MCP for key-value store, caching, and vector search"
}
```

### secrets.json

Redis connection URL is required:

```json
{
  "redis": {
    "REDIS_URL": "redis://localhost:6379"
  }
}
```

**Connection URL Format**:
```
redis://[username:password@]host:port[/database]
```

**Examples**:
- Local: `redis://localhost:6379`
- With password: `redis://:password@localhost:6379`
- With database: `redis://localhost:6379/1`
- Remote: `redis://user:pass@redis.example.com:6379`

## Usage

### Programmatic Usage

```python
from src.MCP_PLUGINS.servers.redis.agent import RedisAgent

async def example():
    agent = RedisAgent()
    await agent.initialize()

    # Caching example
    result = await agent.run_task(
        "Store user session data in Redis with key 'session:abc123' and 1-hour expiration"
    )

    print(result)
    await agent.shutdown()
```

### Via Orchestrator

The Orchestrator automatically routes tasks to Redis based on keywords:

```python
# These phrases trigger Redis routing:
"cache this data in Redis"
"store key-value in kvstore"
"perform vector search"
"use Redis for session storage"
```

**Routing Keywords**: redis, cache, key-value, kvstore, vector search, embedding

## Available Tools

Redis MCP provides comprehensive tools:

### Basic Operations
- `get`: Get value by key
- `set`: Set key-value with optional TTL
- `del`: Delete key(s)
- `exists`: Check if key exists
- `expire`: Set expiration time
- `ttl`: Get time to live

### Hash Operations
- `hset`: Set hash field
- `hget`: Get hash field
- `hgetall`: Get all hash fields
- `hdel`: Delete hash field

### List Operations
- `lpush`: Push to list (left)
- `rpush`: Push to list (right)
- `lrange`: Get list range
- `lpop`: Pop from list (left)

### Set Operations
- `sadd`: Add to set
- `smembers`: Get set members
- `sinter`: Set intersection
- `sunion`: Set union

### Sorted Set Operations
- `zadd`: Add to sorted set with score
- `zrange`: Get sorted set range
- `zrevrange`: Get sorted set (reverse)

### Advanced
- `json_set`: Store JSON document
- `json_get`: Retrieve JSON document
- `vector_search`: Similarity search with embeddings
- `publish`: Pub/Sub publish
- `subscribe`: Pub/Sub subscribe

## Use Cases

### Session Management

```python
task = """
Store session data:
Key: session:user:1234
Value: {"user_id": 1234, "login_time": "2024-01-01T10:00:00Z"}
TTL: 3600 seconds
"""
result = await agent.run_task(task)
```

### Caching API Responses

```python
task = """
Cache API response:
Key: cache:api:weather:NYC
Value: {"temp": 72, "condition": "sunny"}
TTL: 300 seconds
"""
result = await agent.run_task(task)
```

### Leaderboard

```python
task = """
Create game leaderboard:
Add players: Alice (1000), Bob (1500), Charlie (800)
Get top 10 players with scores
"""
result = await agent.run_task(task)
```

### Activity Feed

```python
task = """
Maintain activity feed for user:1234
Add activities: "posted article", "liked comment"
Retrieve latest 20 activities
"""
result = await agent.run_task(task)
```

### Vector Search

```python
task = """
Store document embeddings and perform similarity search:
Documents: ["doc1", "doc2", "doc3"]
Query: "similar to doc1"
Return top 5 matches
"""
result = await agent.run_task(task)
```

## Best Practices

### Key Naming Conventions

Use hierarchical namespaces:
```
✅ user:1234:profile
✅ cache:api:weather:NYC
✅ session:abc123
❌ user1234profile
❌ weatherNYC
```

### TTL Management

Always set expiration for temporary data:
```python
# ✅ Cache with expiration
SET cache:key value EX 3600

# ❌ No expiration (potential memory leak)
SET cache:key value
```

### Data Structure Selection

Choose appropriate structures:
- Simple values → Strings
- Objects → Hashes or JSON
- Collections → Sets or Lists
- Rankings → Sorted Sets
- Documents → JSON
- Embeddings → Vectors

### Error Handling

```python
# Always handle connection errors
try:
    result = await agent.run_task(task)
except ConnectionError:
    # Fallback or retry logic
    pass
```

## Troubleshooting

### Common Issues

**Connection refused**:
```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# Start Redis
# Windows (Chocolatey): redis-server
# macOS: brew services start redis
# Linux: sudo systemctl start redis-server
# Docker: docker run -d -p 6379:6379 redis:latest
```

**Authentication failed**:
- Verify REDIS_URL includes password: `redis://:password@localhost:6379`
- Check Redis config for `requirepass` setting

**Memory limit reached**:
```bash
# Check memory usage
redis-cli INFO memory

# Configure eviction policy in redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

**Slow operations**:
- Use pipelining for batch operations
- Monitor slow log: `redis-cli SLOWLOG GET 10`
- Avoid KEYS command (use SCAN instead)

### Debug Mode

Enable debug logging:

```bash
export MCP_DEBUG=1
export LOG_LEVEL=DEBUG
```

Monitor Redis operations:
```bash
redis-cli MONITOR
```

## Performance Optimization

1. **Use Pipelining**: Batch multiple commands
2. **Set Appropriate TTLs**: Prevent memory bloat
3. **Choose Right Data Structures**: Match structure to use case
4. **Monitor Memory**: Track memory usage and set limits
5. **Use Connection Pooling**: Reuse connections
6. **Avoid Blocking Commands**: Use async operations

## Security Best Practices

1. **Use Password Authentication**: Set `requirepass` in redis.conf
2. **Bind to Localhost**: Avoid exposing Redis to internet
3. **Use TLS**: Enable encryption for remote connections
4. **Limit Commands**: Use `rename-command` for dangerous operations
5. **Monitor Access**: Track connection patterns

## References

- [Redis Documentation](https://redis.io/documentation)
- [Redis MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/redis)
- [Redis Commands](https://redis.io/commands)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification)
- [AutoGen Documentation](https://microsoft.github.io/autogen/)

## Support

For issues specific to:
- **Redis MCP**: https://github.com/modelcontextprotocol/servers/issues
- **Redis Server**: https://github.com/redis/redis/issues
- **Sakana Integration**: Report in main project repository
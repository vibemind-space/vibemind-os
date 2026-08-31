# Context7 MCP Server

AutoGen agent wrapper for Context7 MCP server integration.

## Overview

Context7 provides access to up-to-date code documentation, API references, and real-world examples from official sources. It helps developers find current information about frameworks, libraries, and tools.

## Features

- **Current Documentation**: Access real-time API documentation
- **Version-Specific**: Query documentation for specific versions
- **Official Sources**: Documentation from official framework sources
- **Code Examples**: Real-world examples from official repositories
- **Multi-Framework**: Supports React, Vue, Django, Express, and more
- **Migration Guides**: Access framework upgrade documentation

## Installation

Context7 is installed via npx:

```bash
npx -y @upstash/context7-mcp
```

## Configuration

### servers.json

```json
{
  "name": "context7",
  "active": true,
  "type": "stdio",
  "command": "C:\\Windows\\System32\\cmd.exe",
  "args": ["/c", "npx", "-y", "@upstash/context7-mcp"],
  "read_timeout_seconds": 120,
  "env_vars": {
    "CONTEXT7_API_KEY": "env:CONTEXT7_API_KEY"
  },
  "description": "Context7 MCP for up-to-date code documentation and examples"
}
```

### secrets.json

Context7 API key is optional but recommended for higher rate limits:

```json
{
  "context7": {
    "CONTEXT7_API_KEY": "ctx7_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

**Getting an API Key** (Optional):
1. Visit https://context7.com
2. Create a free account
3. Generate an API key from dashboard
4. Add to secrets.json

**Rate Limits**:
- Free tier (no API key): Limited requests per day
- With API key: Higher rate limits based on plan

## Usage

### Programmatic Usage

```python
from src.MCP_PLUGINS.servers.context7.agent import Context7Agent

async def example():
    agent = Context7Agent()
    await agent.initialize()

    # Query documentation
    result = await agent.run_task(
        "Find React 18 hooks documentation and examples for useState and useEffect"
    )

    print(result)
    await agent.shutdown()
```

### Via Orchestrator

The Orchestrator automatically routes tasks to Context7 based on keywords:

```python
# These phrases trigger Context7 routing:
"get documentation for React hooks"
"find API reference for Django ORM"
"show me examples of Express middleware"
"get docs for TypeScript generics"
```

**Routing Keywords**: documentation, docs, api reference, context7, code example

## Available Tools

Context7 provides tools through the MCP interface:

- `search_docs`: Search documentation across frameworks
- `get_api_reference`: Get specific API documentation
- `find_examples`: Find code examples
- `get_version_docs`: Get version-specific documentation
- `search_migration`: Find migration guides

## Query Examples

### Framework Documentation

```python
task = "Get React 18 documentation for useContext hook"
result = await agent.run_task(task)
```

### Library API Reference

```python
task = "Find Django 4.2 ORM QuerySet API documentation"
result = await agent.run_task(task)
```

### Code Examples

```python
task = "Show examples of Express.js authentication middleware"
result = await agent.run_task(task)
```

### Version-Specific Queries

```python
task = "Get TypeScript 5.0 documentation for decorators"
result = await agent.run_task(task)
```

### Migration Guides

```python
task = "Find migration guide from React 17 to React 18"
result = await agent.run_task(task)
```

## Supported Frameworks and Libraries

Context7 supports documentation for:

- **Frontend**: React, Vue, Angular, Svelte, Next.js, Nuxt.js
- **Backend**: Express, Django, Flask, Spring Boot, ASP.NET
- **Languages**: JavaScript, TypeScript, Python, Go, Java, C#
- **Tools**: Docker, Kubernetes, Git, Webpack, Vite
- **Cloud**: AWS, Azure, GCP, Cloudflare
- **Databases**: PostgreSQL, MongoDB, Redis, MySQL

## Best Practices

1. **Be Version-Specific**: Always specify versions when possible
   - ✅ "React 18 hooks API"
   - ❌ "React hooks API"

2. **Include Context**: Provide framework/library context
   - ✅ "Django ORM filtering examples"
   - ❌ "ORM filtering"

3. **Target Platform**: Specify platform when relevant
   - ✅ "AWS Lambda Python 3.11 runtime"
   - ❌ "serverless Python"

4. **Check Versions**: Verify documentation matches your project versions

5. **Handle Rate Limits**: Add API key for production use

## Troubleshooting

### Common Issues

**Rate limit exceeded**:
- Get a free API key from https://context7.com
- Add to secrets.json: `CONTEXT7_API_KEY`
- Consider upgrading plan for higher limits

**Documentation not found**:
- Verify framework/library name spelling
- Check if version is supported
- Try broader queries first

**Stale results**:
- Context7 updates regularly but may have slight delays
- Cross-reference with official documentation
- Specify version explicitly

### Debug Mode

Enable debug logging:

```bash
export MCP_DEBUG=1
export LOG_LEVEL=DEBUG
```

## Performance Notes

- npx commands cache after first run
- Documentation queries are fast (< 2 seconds)
- Rate limits apply per day/hour depending on plan
- Results are current within 24 hours of official updates

## Integration Patterns

### Documentation Assistant

```python
# Embed Context7 in development workflow
task = f"Get documentation for {framework} {feature} version {version}"
docs = await agent.run_task(task)
```

### Code Generation Helper

```python
# Combine with code generation
task = f"Find {library} {api} examples and best practices"
examples = await agent.run_task(task)
# Use examples to generate code
```

### Migration Assistant

```python
# Help with version upgrades
task = f"Find breaking changes from {old_version} to {new_version} for {framework}"
changes = await agent.run_task(task)
```

## References

- [Context7 Website](https://context7.com)
- [Context7 MCP GitHub](https://github.com/upstash/context7)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification)
- [AutoGen Documentation](https://microsoft.github.io/autogen/)

## Support

For issues specific to:
- **Context7 MCP**: https://github.com/upstash/context7/issues
- **Sakana Integration**: Report in main project repository
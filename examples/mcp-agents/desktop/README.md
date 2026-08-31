# Desktop Commander MCP Server

AutoGen agent wrapper for Desktop Commander MCP server integration.

## Overview

Desktop Commander provides terminal control, file system operations, process management, and in-memory code execution capabilities to the Sakana Desktop Assistant.

## Features

- **Terminal Command Execution**: Run shell commands and capture output
- **File System Operations**: Read, write, list, and delete files/directories
- **Process Management**: Monitor and manage system processes
- **Code Execution**: Run Python, Node.js, and R code in memory
- **Long-Running Commands**: Monitor commands that take time to complete
- **System Information**: Access system details and environment

## Installation

Desktop Commander is installed via npx and requires no credentials:

```bash
npx @wonderwhy-er/desktop-commander@latest
```

## Configuration

### servers.json

```json
{
  "name": "desktop",
  "active": true,
  "type": "stdio",
  "command": "C:\\Windows\\System32\\cmd.exe",
  "args": ["/c", "npx", "@wonderwhy-er/desktop-commander@latest"],
  "read_timeout_seconds": 120,
  "description": "Desktop Commander MCP for terminal control and file system operations"
}
```

### secrets.json

Desktop Commander does not require credentials:

```json
{
  "desktop": {}
}
```

## Usage

### Programmatic Usage

```python
from src.MCP_PLUGINS.servers.desktop.agent import DesktopAgent

async def example():
    agent = DesktopAgent()
    await agent.initialize()

    # Execute a task
    result = await agent.run_task(
        "List all Python files in the current directory and show their sizes"
    )

    print(result)
    await agent.shutdown()
```

### Via Orchestrator

The Orchestrator automatically routes tasks to Desktop Commander based on keywords:

```python
# These phrases trigger Desktop Commander routing:
"execute this command"
"list files in directory"
"run this shell script"
"check process status"
"file system operations"
```

**Routing Keywords**: terminal, command, shell, execute, process, file system, directory

## Available Tools

Desktop Commander provides various tools through the MCP interface:

- `execute_command`: Run shell commands
- `read_file`: Read file contents
- `write_file`: Write content to files
- `list_directory`: List directory contents
- `delete_file`: Remove files
- `run_code`: Execute code in memory (Python/Node.js/R)
- `monitor_process`: Track long-running processes
- `get_system_info`: Access system information

## Security Considerations

⚠️ **Important Security Notes**:

1. **Command Validation**: Always validate commands before execution
2. **File Path Validation**: Check paths to avoid unintended operations
3. **Destructive Operations**: Be cautious with delete/modify operations
4. **Code Execution**: Review code before running in memory
5. **Permissions**: Ensure appropriate file/process permissions

## Examples

### List Directory Contents

```python
task = "List all files in the project root directory"
result = await agent.run_task(task)
```

### Execute Command

```python
task = "Run 'git status' and show the result"
result = await agent.run_task(task)
```

### Read and Process Files

```python
task = "Read config.yaml and extract all port numbers"
result = await agent.run_task(task)
```

### Run Code in Memory

```python
task = "Execute this Python code in memory: print('Hello from MCP')"
result = await agent.run_task(task)
```

## Troubleshooting

### Common Issues

**Desktop Commander not found**:
- Ensure npm/npx is installed and in PATH
- Try running `npx @wonderwhy-er/desktop-commander@latest` manually

**Permission denied errors**:
- Check file/directory permissions
- Run with appropriate user privileges
- Verify path accessibility

**Command timeout**:
- Increase `read_timeout_seconds` in servers.json
- Use async monitoring for long-running commands

### Debug Mode

Enable debug logging:

```bash
export MCP_DEBUG=1
export LOG_LEVEL=DEBUG
```

## Performance Notes

- npx commands cache after first run (subsequent runs are faster)
- File operations are local and fast
- Long-running commands should use monitoring
- In-memory code execution has minimal overhead

## References

- [Desktop Commander GitHub](https://github.com/wonderwhy-er/DesktopCommanderMCP)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification)
- [AutoGen Documentation](https://microsoft.github.io/autogen/)

## Support

For issues specific to:
- **Desktop Commander MCP**: https://github.com/wonderwhy-er/DesktopCommanderMCP/issues
- **Sakana Integration**: Report in main project repository
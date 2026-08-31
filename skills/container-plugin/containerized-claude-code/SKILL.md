---
name: containerized-claude-code
description: 'Run Claude Code CLI sessions in isolated Podman/Docker containers. Use
  this skill when you need to delegate coding tasks to Claude Code with hard resource
  limits, network isolation, and crash recovery. Especially useful with --dangerously-skip-permissions
  where blast radius matters. Provides tools: claude_code_start, claude_code_status,
  claude_code_output, claude_code_cancel, claude_code_cleanup, claude_code_sessions.
  Trigger keywords: ''run claude code in container'', ''containerized claude'', ''sandbox
  coding agent'', ''use claude max subscription for agents''.'
metadata:
  source_pack: 13rac1/openclaw-plugin-claude-code
  format: openclaw-plugin
  license: Apache-2.0
  homepage: https://github.com/13rac1/openclaw-plugin-claude-code
  node_min: '>=22'
  runtime: podman (recommended) or docker
  image: ghcr.io/13rac1/openclaw-claude-code:latest
  tools:
  - claude_code_start
  - claude_code_status
  - claude_code_output
  - claude_code_cancel
  - claude_code_cleanup
  - claude_code_sessions
  version: 1.1.0
license: Apache-2.0
---

# Containerized Claude Code

OpenClaw plugin that runs Claude Code CLI sessions in **rootless Podman containers**
(or Docker, if configured). Each session gets:

- All Linux capabilities dropped
- Configurable network isolation
- Memory + CPU limits (default 2GB, 1 CPU)
- Optional AppArmor profile
- Automatic cleanup of idle sessions
- Persistent state across interactions

## When to use

- Running Claude Code with `--dangerously-skip-permissions` and need containment
- Multi-step coding tasks that benefit from session persistence
- Hard resource isolation for untrusted/experimental code
- Using a Claude Max subscription (vs API-per-token)

## When NOT to use (use `coding-agent` skill instead)

- Quick one-shot tasks that don't need isolation
- Multi-engine work (this plugin is Claude-Code-only)
- Lightweight delegation already covered by OpenClaw's sandbox

## Tools registered

### `claude_code_start`

Start a Claude Code task in the background. Returns immediately with a job ID.

**Parameters:**
- `prompt` (required): The task or prompt to send to Claude Code
- `session_id` (optional): Session ID to continue a previous session

**Returns:** `{ jobId: string, sessionId: string }`

### `claude_code_status`

Check the status of a running or completed job.

**Parameters:**
- `job_id` (required): Job ID returned from `claude_code_start`
- `session_id` (optional): Session ID

**Returns:**
- `status`: Job status (pending, running, completed, failed, cancelled)
- `elapsedSeconds`: Time since job started
- `outputSize`: Total output size in bytes
- `tailOutput`: Last ~500 chars of output (for quick preview)
- `lastOutputSecondsAgo`: Seconds since last output was produced
- `activityState`: "active" (producing output), "processing" (CPU busy), or "idle"
- `metrics`: CPU and memory usage
- `exitCode`: Process exit code (when completed)
- `error`: Error message (if failed)

### `claude_code_output`

Read or tail output from a job.

**Parameters:**
- `job_id` (required): Job ID
- `session_id` (optional): Session ID
- `offset` (optional): Byte offset to start reading from (for tailing)
- `limit` (optional): Maximum bytes to read (default 64KB)

**Returns:** Output content with `hasMore` flag for pagination

### `claude_code_cancel`

Cancel a running job and stop its container.

**Parameters:**
- `job_id` (required): Job ID
- `session_id` (optional): Session ID

### `claude_code_cleanup`

Clean up idle sessions and their jobs.

### `claude_code_sessions`

List all active sessions with age, last activity, message count, and active job info.

## Installation

```bash
# Requires OpenClaw >= 2025.1.0 + Podman (or Docker)
openclaw plugins install @13rac1/openclaw-plugin-claude-code

# Or via npm
npm install -g @13rac1/openclaw-plugin-claude-code
```

## Authentication

Two paths:
- **API key**: standard `ANTHROPIC_API_KEY` env var
- **OAuth / Claude Max**: existing OAuth credentials are passed into the container

## Reference

- Upstream repo: https://github.com/13rac1/openclaw-plugin-claude-code
- Container image: `ghcr.io/13rac1/openclaw-claude-code:latest`
- Plugin manifest format: OpenClaw plugin (`openclaw.plugin.json`)
- This SKILL.md was synthesized from manifest + README for discoverability.

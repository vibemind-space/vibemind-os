"""Tests for execute_streaming in ClaudeCLI (Phase 31 Vibe-Coding)."""
import pytest
import json
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from src.autogen.cli_wrapper import ClaudeCLI


class AsyncLineIterator:
    """Helper: wraps a list of bytes into an async iterator (like process.stdout)."""
    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


def _make_process(lines: list[bytes], returncode: int = 0):
    """Create a mock subprocess with async-iterable stdout."""
    mock = AsyncMock()
    mock.stdout = AsyncLineIterator(lines)
    mock.stderr = AsyncMock()
    mock.stderr.read = AsyncMock(return_value=b"")
    mock.wait = AsyncMock(return_value=returncode)
    mock.returncode = returncode
    return mock


@pytest.fixture
def cli(tmp_path):
    return ClaudeCLI(working_dir=str(tmp_path), agent_name="test")


def test_execute_streaming_exists(cli):
    """execute_streaming method exists and is async generator."""
    assert hasattr(cli, 'execute_streaming')
    assert inspect.isasyncgenfunction(cli.execute_streaming)


@pytest.mark.asyncio
async def test_execute_streaming_yields_text_frame(cli):
    """Streaming yields text frames from assistant messages."""
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world"}]}}).encode() + b'\n',
        json.dumps({"type": "result", "result": "done", "session_id": "sess-abc"}).encode() + b'\n',
    ]
    mock_process = _make_process(lines)
    frames = []

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        async for frame in cli.execute_streaming("test prompt"):
            frames.append(frame)

    text_frames = [f for f in frames if f["type"] == "text"]
    assert len(text_frames) == 1
    assert text_frames[0]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_execute_streaming_yields_complete_frame(cli):
    """Last frame should be type=complete with session_id."""
    lines = [
        json.dumps({"type": "result", "result": "done", "session_id": "sess-123"}).encode() + b'\n',
    ]
    mock_process = _make_process(lines)
    frames = []

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        async for frame in cli.execute_streaming("test"):
            frames.append(frame)

    complete_frames = [f for f in frames if f.get("type") == "complete"]
    assert len(complete_frames) == 1
    assert complete_frames[0]["session_id"] == "sess-123"
    assert complete_frames[0]["success"] is True


@pytest.mark.asyncio
async def test_execute_streaming_yields_tool_use_frame(cli):
    """Tool use events produce tool_use frames with file tracking."""
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/app.tsx"}}
        ]}}).encode() + b'\n',
        json.dumps({"type": "result", "result": "done", "session_id": None}).encode() + b'\n',
    ]
    mock_process = _make_process(lines)
    frames = []

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        async for frame in cli.execute_streaming("fix app"):
            frames.append(frame)

    tool_frames = [f for f in frames if f["type"] == "tool_use"]
    assert len(tool_frames) == 1
    assert tool_frames[0]["tool"] == "Edit"
    assert tool_frames[0]["file"] == "src/app.tsx"

    complete = [f for f in frames if f["type"] == "complete"][0]
    assert "src/app.tsx" in complete["files"]


@pytest.mark.asyncio
async def test_execute_streaming_agent_flag(cli):
    """Agent name is passed as --agent flag."""
    mock_process = _make_process([])

    with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
        async for _ in cli.execute_streaming("test", agent_name="debugger"):
            pass

        cmd_parts = [str(a) for a in mock_exec.call_args[0]]
        assert "--agent" in cmd_parts
        assert "debugger" in cmd_parts


@pytest.mark.asyncio
async def test_execute_streaming_allowed_tools(cli):
    """allowed_tools uses --allowedTools instead of --dangerously-skip-permissions."""
    mock_process = _make_process([])

    with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
        async for _ in cli.execute_streaming("test", allowed_tools=["Read", "Edit"]):
            pass

        cmd_parts = [str(a) for a in mock_exec.call_args[0]]
        assert "--allowedTools" in cmd_parts
        assert "--dangerously-skip-permissions" not in cmd_parts


@pytest.mark.asyncio
async def test_execute_streaming_uses_stream_json(cli):
    """Command uses --output-format stream-json."""
    mock_process = _make_process([])

    with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
        async for _ in cli.execute_streaming("test"):
            pass

        cmd_parts = [str(a) for a in mock_exec.call_args[0]]
        assert "stream-json" in cmd_parts


@pytest.mark.asyncio
async def test_execute_streaming_error_on_nonzero_exit(cli):
    """Non-zero exit code yields error frame."""
    mock_process = _make_process([], returncode=1)
    mock_process.stderr.read = AsyncMock(return_value=b"auth failed")
    frames = []

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        async for frame in cli.execute_streaming("test"):
            frames.append(frame)

    error_frames = [f for f in frames if f["type"] == "error"]
    assert len(error_frames) == 1
    assert "auth failed" in error_frames[0]["message"]


@pytest.mark.asyncio
async def test_execute_streaming_fallback_complete_no_result(cli):
    """If no result frame from CLI, still yields complete on exit 0."""
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done"}]}}).encode() + b'\n',
    ]
    mock_process = _make_process(lines)
    frames = []

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        async for frame in cli.execute_streaming("test"):
            frames.append(frame)

    complete_frames = [f for f in frames if f["type"] == "complete"]
    assert len(complete_frames) == 1
    assert complete_frames[0]["success"] is True

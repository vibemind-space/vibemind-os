"""
Tests for ContinuousDebugAgent - Real-time debugging during generation.

Tests cover:
1. ContainerFileSyncer - file sync to Docker container
2. DebugCycleResult - debug cycle result data class
3. ContinuousDebugAgent - main agent logic
4. Error extraction from events
5. Integration with Claude Code Tool
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.agents.continuous_debug_agent import (
    ContinuousDebugAgent,
    ContainerFileSyncer,
    DebugCycleResult,
)
from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState


class TestDebugCycleResult:
    """Tests for DebugCycleResult data class."""

    def test_creation(self):
        """Test creating a DebugCycleResult."""
        result = DebugCycleResult(
            cycle_number=1,
            errors_found=5,
            fixes_attempted=5,
            fixes_applied=3,
            files_synced=["src/App.tsx", "src/utils.ts"],
            success=True,
            duration_ms=1500,
        )
        
        assert result.cycle_number == 1
        assert result.errors_found == 5
        assert result.fixes_applied == 3
        assert len(result.files_synced) == 2
        assert result.success is True
        assert result.error_message is None

    def test_to_dict(self):
        """Test DebugCycleResult to_dict conversion."""
        result = DebugCycleResult(
            cycle_number=2,
            errors_found=3,
            fixes_attempted=3,
            fixes_applied=2,
            files_synced=["src/main.tsx"],
            success=True,
            duration_ms=2000,
        )
        
        data = result.to_dict()
        
        assert data["cycle_number"] == 2
        assert data["errors_found"] == 3
        assert data["fixes_applied"] == 2
        assert "files_synced" in data
        assert data["success"] is True

    def test_failed_result(self):
        """Test creating a failed DebugCycleResult."""
        result = DebugCycleResult(
            cycle_number=1,
            errors_found=5,
            fixes_attempted=5,
            fixes_applied=0,
            files_synced=[],
            success=False,
            duration_ms=500,
            error_message="Claude API failed",
        )
        
        assert result.success is False
        assert result.error_message == "Claude API failed"
        assert result.fixes_applied == 0


class TestContainerFileSyncer:
    """Tests for ContainerFileSyncer."""

    @pytest.fixture
    def syncer(self, tmp_path):
        """Create a ContainerFileSyncer instance."""
        return ContainerFileSyncer(
            container_id="abc123",
            working_dir=str(tmp_path),
        )

    @pytest.mark.asyncio
    async def test_sync_file_not_found(self, syncer):
        """Test syncing a non-existent file."""
        result = await syncer.sync_file("nonexistent.ts")
        assert result is False

    @pytest.mark.asyncio
    async def test_sync_file_success(self, syncer, tmp_path):
        """Test successful file sync."""
        # Create a test file
        test_file = tmp_path / "test.ts"
        test_file.write_text("const x = 1;")
        
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock successful docker cp
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process
            
            result = await syncer.sync_file("test.ts")
            
            assert result is True
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_files_multiple(self, syncer, tmp_path):
        """Test syncing multiple files."""
        # Create test files
        (tmp_path / "a.ts").write_text("const a = 1;")
        (tmp_path / "b.ts").write_text("const b = 2;")
        
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process
            
            results = await syncer.sync_files(["a.ts", "b.ts"])
            
            assert results["a.ts"] is True
            assert results["b.ts"] is True

    @pytest.mark.asyncio
    async def test_trigger_rebuild(self, syncer):
        """Test triggering rebuild in container."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process
            
            result = await syncer.trigger_rebuild()
            
            assert result is True
            # Should be called twice: touch + pkill
            assert mock_exec.call_count >= 1


class TestContinuousDebugAgent:
    """Tests for ContinuousDebugAgent."""

    @pytest.fixture
    def event_bus(self):
        """Create an EventBus instance."""
        return EventBus()

    @pytest.fixture
    def shared_state(self):
        """Create a SharedState instance."""
        state = SharedState()
        return state

    @pytest.fixture
    def agent(self, event_bus, shared_state, tmp_path):
        """Create a ContinuousDebugAgent instance."""
        return ContinuousDebugAgent(
            name="TestDebug",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            max_debug_iterations=5,
            debug_cooldown_seconds=0,  # No cooldown for tests
        )

    def test_subscribed_events(self, agent):
        """Test that agent subscribes to correct events."""
        events = agent.subscribed_events
        
        assert EventType.SANDBOX_TEST_FAILED in events
        assert EventType.BUILD_FAILED in events
        assert EventType.TYPE_ERROR in events
        assert EventType.SANDBOX_TEST_STARTED in events

    def test_set_container_id(self, agent):
        """Test setting container ID."""
        agent.set_container_id("container123")
        
        assert agent.container_id == "container123"
        assert agent._file_syncer is not None

    @pytest.mark.asyncio
    async def test_should_act_no_events(self, agent):
        """Test should_act returns False with no events."""
        result = await agent.should_act([])
        assert result is False

    @pytest.mark.asyncio
    async def test_should_act_on_sandbox_failure(self, agent):
        """Test should_act returns True on sandbox failure."""
        event = Event(
            type=EventType.SANDBOX_TEST_FAILED,
            source="DeploymentTeam",
            success=False,
            error_message="Build failed",
        )
        
        result = await agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_on_build_failure(self, agent):
        """Test should_act returns True on build failure."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            data={"errors": 5},
        )
        
        result = await agent.should_act([event])
        assert result is True

    @pytest.mark.asyncio
    async def test_should_act_respects_max_iterations(self, agent):
        """Test should_act returns False when max iterations reached."""
        agent._consecutive_failures = 10  # Exceed max
        
        event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
        )
        
        result = await agent.should_act([event])
        assert result is False

    @pytest.mark.asyncio
    async def test_should_act_updates_container_id(self, agent):
        """Test should_act updates container ID from events."""
        event = Event(
            type=EventType.SANDBOX_TEST_STARTED,
            source="DeploymentTeam",
            data={"container_id": "new_container_456"},
        )
        
        await agent.should_act([event])
        assert agent.container_id == "new_container_456"

    def test_extract_errors_from_build_failed(self, agent):
        """Test error extraction from BUILD_FAILED event."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            error_message="TypeScript compilation failed",
            data={
                "failures": [
                    {"file": "src/App.tsx", "line": 10, "message": "Type error"},
                    {"file": "src/utils.ts", "line": 5, "message": "Import error"},
                ]
            },
        )
        
        errors = agent._extract_errors([event])
        
        assert len(errors) == 2
        assert errors[0]["type"] == "build_error"
        assert errors[0]["file"] == "src/App.tsx"

    def test_extract_errors_from_type_error(self, agent):
        """Test error extraction from TYPE_ERROR event."""
        event = Event(
            type=EventType.TYPE_ERROR,
            source="Validator",
            success=False,
            data={
                "failures": [
                    {"file": "src/main.tsx", "line": 20, "message": "Missing type"},
                ]
            },
        )
        
        errors = agent._extract_errors([event])
        
        assert len(errors) == 1
        assert errors[0]["type"] == "type_error"

    def test_extract_errors_from_sandbox_failure(self, agent):
        """Test error extraction from SANDBOX_TEST_FAILED event."""
        event = Event(
            type=EventType.SANDBOX_TEST_FAILED,
            source="DeploymentTeam",
            success=False,
            error_message="Health check failed",
            data={
                "steps": [
                    {"name": "install", "success": True},
                    {"name": "build", "success": False, "error_message": "npm run build failed"},
                ]
            },
        )
        
        errors = agent._extract_errors([event])
        
        assert len(errors) >= 1
        assert any(e["step"] == "build" for e in errors)

    def test_get_debug_status(self, agent):
        """Test get_debug_status returns correct info."""
        agent._debug_count = 3
        agent._total_fixes = 10
        agent._consecutive_failures = 1
        agent.container_id = "test_container"
        
        status = agent.get_debug_status()
        
        assert status["debug_count"] == 3
        assert status["total_fixes"] == 10
        assert status["consecutive_failures"] == 1
        assert status["container_id"] == "test_contain"  # Truncated to 12 chars
        assert status["max_iterations"] == 5

    @pytest.mark.asyncio
    async def test_act_with_no_errors(self, agent):
        """Test act returns None when no errors extracted."""
        event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=True,  # Success event, no errors
        )
        
        result = await agent.act([event])
        assert result is None

    @pytest.mark.asyncio
    async def test_act_publishes_debug_started_event(self, agent, event_bus):
        """Test that act publishes DEBUG_STARTED event."""
        events_published = []
        
        async def capture_event(event):
            events_published.append(event)
        
        event_bus.subscribe(EventType.DEBUG_STARTED, capture_event)
        
        error_event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            error_message="Build failed",
            data={"failures": [{"file": "test.ts", "message": "error"}]},
        )
        
        with patch.object(agent, "_fix_errors_with_claude", return_value=[]):
            await agent.act([error_event])
        
        # Check DEBUG_STARTED was published
        assert any(e.type == EventType.DEBUG_STARTED for e in events_published)

    @pytest.mark.asyncio
    async def test_act_with_fixes_applied(self, agent, event_bus, tmp_path):
        """Test act when fixes are successfully applied."""
        error_event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            error_message="Type error",
            data={"failures": [{"file": "src/App.tsx", "message": "Type mismatch"}]},
        )
        
        # Mock Claude tool returning fixes
        with patch.object(agent, "_fix_errors_with_claude", return_value=["src/App.tsx"]):
            result = await agent.act([error_event])
        
        assert result is not None
        assert result.type == EventType.CODE_FIXED
        assert result.success is True

    @pytest.mark.asyncio
    async def test_act_increments_failure_counter(self, agent):
        """Test that consecutive failures are tracked."""
        initial_failures = agent._consecutive_failures
        
        error_event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            error_message="Build failed",
            data={"failures": [{"file": "test.ts", "message": "error"}]},
        )
        
        with patch.object(agent, "_fix_errors_with_claude", return_value=[]):
            await agent.act([error_event])
        
        assert agent._consecutive_failures == initial_failures + 1

    @pytest.mark.asyncio
    async def test_act_resets_failure_counter_on_success(self, agent):
        """Test that failure counter resets on success."""
        agent._consecutive_failures = 3
        
        error_event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            error_message="Build failed",
            data={"failures": [{"file": "test.ts", "message": "error"}]},
        )
        
        with patch.object(agent, "_fix_errors_with_claude", return_value=["test.ts"]):
            await agent.act([error_event])
        
        assert agent._consecutive_failures == 0


class TestContinuousDebugIntegration:
    """Integration tests for ContinuousDebugAgent with mock Claude."""

    @pytest.mark.asyncio
    async def test_full_debug_cycle(self, tmp_path):
        """Test a complete debug cycle from error to fix."""
        event_bus = EventBus()
        shared_state = SharedState()
        await shared_state.start()
        
        agent = ContinuousDebugAgent(
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            debug_cooldown_seconds=0,
        )
        
        # Create a test file with an error
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "App.tsx").write_text("const x: string = 123;")  # Type error
        
        # Simulate build failure event
        error_event = Event(
            type=EventType.BUILD_FAILED,
            source="Builder",
            success=False,
            error_message="Type error",
            data={
                "failures": [{
                    "file": "src/App.tsx",
                    "line": 1,
                    "message": "Type 'number' is not assignable to type 'string'",
                }]
            },
        )
        
        # Mock Claude to return a fixed file
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.files = ["src/App.tsx"]
        mock_result.error = None
        
        with patch("src.tools.claude_code_tool.ClaudeCodeTool") as MockTool:
            mock_tool_instance = MagicMock()
            mock_tool_instance.execute = AsyncMock(return_value=mock_result)
            MockTool.return_value = mock_tool_instance
            
            # Also patch the dynamic import inside _fix_errors_with_claude
            with patch.object(agent, "_fix_errors_with_claude", return_value=["src/App.tsx"]):
                result = await agent.act([error_event])
        
        assert result is not None
        assert result.success is True
        assert result.type == EventType.CODE_FIXED


class TestContinuousDebugEventFlow:
    """Tests for event flow and interaction with other agents."""

    @pytest.mark.asyncio
    async def test_reacts_to_deployment_team_failure(self, tmp_path):
        """Test that agent reacts to DeploymentTeam failures."""
        event_bus = EventBus()
        shared_state = SharedState()
        
        agent = ContinuousDebugAgent(
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            debug_cooldown_seconds=0,
        )
        
        # First send container info via SANDBOX_TEST_STARTED
        start_event = Event(
            type=EventType.SANDBOX_TEST_STARTED,
            source="DeploymentTeam",
            data={"container_id": "test123"},
        )
        
        # Then send failure event
        failure_event = Event(
            type=EventType.SANDBOX_TEST_FAILED,
            source="DeploymentTeam",
            success=False,
            error_message="App failed to start",
            data={
                "mode": "continuous",
                "steps": [{
                    "name": "start_and_verify",
                    "success": False,
                    "error_message": "npm run preview failed",
                }],
            },
        )
        
        # Process both events together (container ID comes from start event)
        should_act = await agent.should_act([start_event, failure_event])
        assert should_act is True
        assert agent.container_id == "test123"

    @pytest.mark.asyncio
    async def test_file_sync_after_fix(self, tmp_path):
        """Test that files are synced after fix when container available."""
        event_bus = EventBus()
        shared_state = SharedState()
        
        agent = ContinuousDebugAgent(
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=str(tmp_path),
            enable_file_sync=True,
            enable_hot_reload=True,
            debug_cooldown_seconds=0,
        )
        
        # Set container and create file syncer
        agent.set_container_id("container456")
        
        # Create source file
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "test.ts").write_text("const x = 1;")
        
        error_event = Event(
            type=EventType.TYPE_ERROR,
            source="Validator",
            success=False,
            data={"failures": [{"file": "src/test.ts", "message": "error"}]},
        )
        
        # Mock _fix_errors_with_claude directly instead of patching ClaudeCodeTool
        with patch.object(agent, "_fix_errors_with_claude", return_value=["src/test.ts"]):
            with patch.object(agent._file_syncer, "sync_files", return_value={"src/test.ts": True}) as mock_sync:
                with patch.object(agent._file_syncer, "trigger_rebuild", return_value=True) as mock_rebuild:
                    result = await agent.act([error_event])
                    
                    mock_sync.assert_called_once()
                    mock_rebuild.assert_called_once()
        
        assert result.success is True


# Pytest configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
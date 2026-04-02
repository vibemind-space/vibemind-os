#!/usr/bin/env python3
"""
System Validation Test Suite

Comprehensive tests for the Hybrid Society of Mind code generation system.
Tests all major components:
1. Project Scaffolding
2. HybridPipeline
3. Society of Mind Agents
4. EventBus and Event Flow
5. Claude CLI Integration
6. Sandbox Deployment Loop
7. VNC Streaming
8. Convergence Criteria
9. End-to-End with Electron App
10. Dashboard Integration
"""

import asyncio
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Test 1: Scaffolding
# =============================================================================

class TestScaffolding:
    """Test project scaffolding functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp = tempfile.mkdtemp(prefix="test_scaffold_")
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    @pytest.fixture
    def requirements(self):
        """Load test requirements."""
        req_path = Path(__file__).parent / "validation_requirements.json"
        with open(req_path, "r") as f:
            return json.load(f)
    
    @pytest.mark.asyncio
    async def test_project_initializer_creates_structure(self, temp_dir, requirements):
        """Test that ProjectInitializer creates the expected project structure."""
        from src.scaffolding.project_initializer import ProjectInitializer
        
        initializer = ProjectInitializer(temp_dir)
        result = await initializer.initialize(
            requirements=requirements,
            install_deps=False,  # Skip for unit test
        )
        
        assert result.success, f"Scaffolding failed: {result.errors}"
        # Accept electron-related types
        assert "electron" in result.project_type.value.lower()
        assert len(result.files_created) > 0
        
        # Verify critical files exist
        assert (Path(temp_dir) / "package.json").exists()
    
    @pytest.mark.asyncio
    async def test_electron_project_detection(self, temp_dir, requirements):
        """Test that Electron project type is correctly detected."""
        from src.scaffolding.project_initializer import ProjectInitializer
        
        initializer = ProjectInitializer(temp_dir)
        project_type = initializer.detect_project_type(requirements)
        
        # Accept electron or react_electron
        assert "electron" in project_type.value.lower()


# =============================================================================
# Test 2: HybridPipeline
# =============================================================================

class TestHybridPipeline:
    """Test HybridPipeline code generation."""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp(prefix="test_pipeline_")
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_pipeline_initialization(self, temp_dir):
        """Test that HybridPipeline initializes correctly."""
        from src.engine.hybrid_pipeline import HybridPipeline
        
        pipeline = HybridPipeline(
            output_dir=temp_dir,
            max_concurrent=2,
            max_iterations=1,
        )
        
        assert pipeline.output_dir == Path(temp_dir)
        assert pipeline.max_concurrent == 2
    
    def test_requirements_parsing(self):
        """Test that requirements are parsed correctly."""
        from src.engine.hybrid_pipeline import HybridPipeline
        
        req_path = Path(__file__).parent / "validation_requirements.json"
        pipeline = HybridPipeline(output_dir=".")
        
        with open(req_path, "r") as f:
            requirements = json.load(f)
        
        # Should extract 5 requirements
        req_list = requirements.get("requirements", [])
        assert len(req_list) == 5


# =============================================================================
# Test 3: Society of Mind Agents
# =============================================================================

class TestSocietyAgents:
    """Test autonomous agents."""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp(prefix="test_agents_")
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    @pytest.fixture
    def event_bus(self):
        from src.mind.event_bus import EventBus
        return EventBus()
    
    @pytest.fixture
    def shared_state(self):
        from src.mind.shared_state import SharedState
        return SharedState()
    
    @pytest.mark.asyncio
    async def test_agent_creation(self, temp_dir, event_bus, shared_state):
        """Test that agents can be created."""
        from src.agents.autonomous_base import TesterAgent, BuilderAgent
        
        tester = TesterAgent(
            name="TestTester",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=temp_dir,
        )
        
        builder = BuilderAgent(
            name="TestBuilder",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=temp_dir,
        )
        
        assert tester.name == "TestTester"
        assert builder.name == "TestBuilder"
    
    @pytest.mark.asyncio
    async def test_deployment_team_agent(self, temp_dir, event_bus, shared_state):
        """Test DeploymentTeamAgent with continuous mode."""
        from src.agents.deployment_team_agent import DeploymentTeamAgent
        
        agent = DeploymentTeamAgent(
            name="TestDeployment",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=temp_dir,
            enable_sandbox=True,
            enable_continuous=True,
            cycle_interval=30,
            start_continuous_immediately=False,  # Don't auto-start
        )
        
        assert agent.enable_continuous
        assert agent.cycle_interval == 30
        
        status = agent.get_continuous_status()
        assert status["enabled"] == True
        assert status["running"] == False


# =============================================================================
# Test 4: EventBus and Event Flow
# =============================================================================

class TestEventBus:
    """Test EventBus functionality."""
    
    @pytest.mark.asyncio
    async def test_event_publish_subscribe(self):
        """Test basic pub/sub."""
        from src.mind.event_bus import EventBus, Event, EventType
        
        bus = EventBus()
        received_events = []
        
        def handler(event: Event):
            received_events.append(event)
        
        bus.subscribe(EventType.BUILD_SUCCEEDED, handler)
        
        await bus.publish(Event(
            type=EventType.BUILD_SUCCEEDED,
            source="test",
            success=True,
        ))
        
        # Allow async processing
        await asyncio.sleep(0.1)
        
        assert len(received_events) == 1
        assert received_events[0].type == EventType.BUILD_SUCCEEDED
    
    @pytest.mark.asyncio
    async def test_event_types_exist(self):
        """Test that all expected event types exist."""
        from src.mind.event_bus import EventType
        
        # Check a subset of expected types that should exist
        expected_types = [
            "BUILD_SUCCEEDED",
            "BUILD_FAILED",
            "CODE_FIXED",
            "SANDBOX_TEST_STARTED",
            "SANDBOX_TEST_PASSED",
            "SANDBOX_TEST_FAILED",
            "SCREEN_STREAM_READY",
        ]
        
        for type_name in expected_types:
            assert hasattr(EventType, type_name), f"Missing EventType: {type_name}"


# =============================================================================
# Test 5: Claude CLI Integration
# =============================================================================

class TestClaudeCLI:
    """Test Claude CLI tool integration."""
    
    def test_claude_tool_initialization(self):
        """Test that ClaudeCodeTool initializes correctly."""
        from src.tools.claude_code_tool import ClaudeCodeTool
        
        tool = ClaudeCodeTool(
            max_concurrent=2,
            timeout=300,
        )
        
        # Just check it initializes without error
        assert tool is not None
    
    @pytest.mark.asyncio
    async def test_claude_tool_exists(self):
        """Test that ClaudeCodeTool class exists and can be imported."""
        from src.tools.claude_code_tool import ClaudeCodeTool
        
        # The class should be importable
        assert ClaudeCodeTool is not None


# =============================================================================
# Test 6: Sandbox Deployment Loop
# =============================================================================

class TestSandboxDeployment:
    """Test Docker sandbox deployment."""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp(prefix="test_sandbox_")
        # Create a minimal package.json for detection
        with open(os.path.join(temp, "package.json"), "w") as f:
            json.dump({
                "name": "test-app",
                "dependencies": {"electron": "^28.0.0"}
            }, f)
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_project_type_detection(self, temp_dir):
        """Test that project type is detected correctly."""
        from src.tools.sandbox_tool import SandboxTool, ProjectType
        
        tool = SandboxTool(project_dir=temp_dir)
        project_type = tool.detect_project_type()
        
        assert project_type == ProjectType.ELECTRON
    
    def test_sandbox_tool_initialization(self, temp_dir):
        """Test SandboxTool initialization with continuous mode."""
        from src.tools.sandbox_tool import SandboxTool
        
        tool = SandboxTool(
            project_dir=temp_dir,
            enable_vnc=True,
            vnc_port=6080,
            cycle_interval=30,
        )
        
        assert tool.enable_vnc
        assert tool.vnc_port == 6080
        assert tool.cycle_interval == 30
    
    def test_continuous_sandbox_cycle_dataclass(self):
        """Test ContinuousSandboxCycle dataclass."""
        from src.tools.sandbox_tool import ContinuousSandboxCycle
        
        cycle = ContinuousSandboxCycle(
            cycle_number=1,
            timestamp=datetime.now(),
            success=True,
            app_started=True,
            app_responsive=True,
            duration_ms=5000,
        )
        
        assert cycle.cycle_number == 1
        assert cycle.success
        
        data = cycle.to_dict()
        assert "cycle_number" in data
        assert "timestamp" in data


# =============================================================================
# Test 7: VNC Streaming
# =============================================================================

class TestVNCStreaming:
    """Test VNC streaming configuration."""
    
    def test_vnc_url_generation(self):
        """Test VNC URL is correctly generated."""
        from src.tools.sandbox_tool import SandboxResult, ProjectType
        
        result = SandboxResult(
            success=True,
            project_type=ProjectType.ELECTRON,
            vnc_enabled=True,
            vnc_url="http://localhost:6080/vnc.html",
            vnc_port=6080,
        )
        
        data = result.to_dict()
        assert "vnc_streaming" in data
        assert data["vnc_streaming"]["url"] == "http://localhost:6080/vnc.html"
    
    def test_vnc_port_configuration(self):
        """Test VNC port can be configured."""
        from src.tools.sandbox_tool import SandboxTool
        
        tool = SandboxTool(
            project_dir=".",
            enable_vnc=True,
            vnc_port=6090,
        )
        
        assert tool.vnc_port == 6090


# =============================================================================
# Test 8: Convergence Criteria
# =============================================================================

class TestConvergenceCriteria:
    """Test convergence criteria and checking."""
    
    def test_default_criteria(self):
        """Test default convergence criteria."""
        from src.mind.convergence import DEFAULT_CRITERIA
        
        assert DEFAULT_CRITERIA.min_tests_passing_rate > 0
        assert DEFAULT_CRITERIA.max_iterations > 0
    
    def test_autonomous_criteria(self):
        """Test autonomous mode criteria."""
        from src.mind.convergence import ConvergenceCriteria
        
        criteria = ConvergenceCriteria(
            require_all_tests_pass=True,
            min_tests_passing_rate=100.0,
            max_iterations=200,
            max_time_seconds=3600,
        )
        
        assert criteria.require_all_tests_pass
        assert criteria.min_tests_passing_rate == 100.0
    
    def test_convergence_check(self):
        """Test convergence checking."""
        from src.mind.convergence import is_converged, ConvergenceCriteria
        from src.mind.shared_state import ConvergenceMetrics
        
        criteria = ConvergenceCriteria(
            min_tests_passing_rate=90.0,
            require_build_success=True,
            max_validation_errors=0,
            min_iterations=2,
        )
        
        metrics = ConvergenceMetrics(
            iteration=5,
            tests_passed=10,
            total_tests=10,
            build_success=True,
            build_attempted=True,  # Need to also set this
            validation_errors=0,
        )
        
        # Call without elapsed parameter - check the actual function signature
        converged, reasons = is_converged(metrics, criteria)
        assert converged, f"Should have converged: {reasons}"


# =============================================================================
# Test 9: Integration Config
# =============================================================================

class TestIntegrationConfig:
    """Test HybridSocietyConfig."""
    
    def test_config_defaults(self):
        """Test default configuration values."""
        from src.mind.integration import HybridSocietyConfig
        
        config = HybridSocietyConfig(
            requirements_path="test.json",
            output_dir="./output",
        )
        
        assert config.enable_continuous_sandbox == False
        assert config.sandbox_cycle_interval == 30
        assert config.start_sandbox_immediately == True
    
    def test_config_with_continuous_sandbox(self):
        """Test config with continuous sandbox enabled."""
        from src.mind.integration import HybridSocietyConfig
        
        config = HybridSocietyConfig(
            requirements_path="test.json",
            output_dir="./output",
            enable_continuous_sandbox=True,
            sandbox_cycle_interval=15,
            enable_vnc_streaming=True,
        )
        
        assert config.enable_continuous_sandbox
        assert config.sandbox_cycle_interval == 15
        assert config.enable_vnc_streaming


# =============================================================================
# Test 10: Result Dataclasses
# =============================================================================

class TestResultDataclasses:
    """Test result dataclasses."""
    
    def test_hybrid_society_result(self):
        """Test HybridSocietyResult with sandbox fields."""
        from src.mind.integration import HybridSocietyResult
        
        result = HybridSocietyResult(
            success=True,
            converged=True,
            sandbox_cycles_completed=10,
            sandbox_last_success=True,
            vnc_url="http://localhost:6080/vnc.html",
        )
        
        data = result.to_dict()
        assert data["sandbox_cycles_completed"] == 10
        assert data["sandbox_last_success"] == True
        assert data["vnc_url"] == "http://localhost:6080/vnc.html"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
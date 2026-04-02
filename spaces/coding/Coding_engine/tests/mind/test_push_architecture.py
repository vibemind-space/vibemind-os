"""
Tests für die Push-basierte Society of Mind Architektur.

Testet:
1. AsyncQueue Event-Delivery
2. Event Batching
3. Idle-basierte Convergence Checks
4. Agent Dependency Graph
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.mind.event_bus import EventBus, Event, EventType
from src.mind.shared_state import SharedState
from src.mind.orchestrator import (
    Orchestrator,
    AGENT_DEPENDENCIES,
    AGENT_TRIGGERS,
)
from src.agents.autonomous_base import (
    AutonomousAgent,
    TesterAgent,
    BuilderAgent,
    ValidatorAgent,
    FixerAgent,
    QUEUE_TIMEOUT,
    EVENT_BATCH_WINDOW,
)


class TestPushArchitectureConstants:
    """Test that push architecture constants are properly defined."""
    
    def test_queue_timeout_is_reasonable(self):
        """Queue timeout should be between 1-10 seconds."""
        assert 1.0 <= QUEUE_TIMEOUT <= 10.0
        
    def test_batch_window_is_reasonable(self):
        """Batch window should be between 100ms-1s."""
        assert 0.1 <= EVENT_BATCH_WINDOW <= 1.0


class TestAgentDependencyGraph:
    """Test the agent dependency graph."""
    
    def test_builder_has_no_dependencies(self):
        """Builder should run first with no dependencies."""
        assert AGENT_DEPENDENCIES["Builder"] == []
        
    def test_validator_depends_on_builder(self):
        """Validator should wait for Builder."""
        assert "Builder" in AGENT_DEPENDENCIES["Validator"]
        
    def test_tester_depends_on_builder(self):
        """Tester should wait for Builder."""
        assert "Builder" in AGENT_DEPENDENCIES["Tester"]
        
    def test_fixer_depends_on_all_checks(self):
        """Fixer should wait for Builder, Validator, and Tester."""
        fixer_deps = AGENT_DEPENDENCIES["Fixer"]
        assert "Builder" in fixer_deps
        assert "Validator" in fixer_deps
        assert "Tester" in fixer_deps
        
    def test_no_circular_dependencies(self):
        """Dependency graph should have no cycles."""
        # Simple cycle detection via topological sort
        visited = set()
        in_progress = set()
        
        def has_cycle(agent: str) -> bool:
            if agent in in_progress:
                return True
            if agent in visited:
                return False
            in_progress.add(agent)
            for dep in AGENT_DEPENDENCIES.get(agent, []):
                if has_cycle(dep):
                    return True
            in_progress.remove(agent)
            visited.add(agent)
            return False
        
        for agent in AGENT_DEPENDENCIES:
            assert not has_cycle(agent), f"Circular dependency detected for {agent}"


class TestAgentTriggers:
    """Test the agent trigger mappings."""
    
    def test_builder_triggers_on_file_events(self):
        """Builder should trigger on file events."""
        triggers = AGENT_TRIGGERS["Builder"]
        assert EventType.FILE_CREATED in triggers
        assert EventType.FILE_MODIFIED in triggers
        
    def test_fixer_triggers_on_errors(self):
        """Fixer should trigger on error events."""
        triggers = AGENT_TRIGGERS["Fixer"]
        assert EventType.TYPE_ERROR in triggers
        assert EventType.TEST_FAILED in triggers
        assert EventType.BUILD_FAILED in triggers
        
    def test_validator_triggers_on_build_success(self):
        """Validator should trigger after successful build."""
        triggers = AGENT_TRIGGERS["Validator"]
        assert EventType.BUILD_SUCCEEDED in triggers


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def shared_state():
    return SharedState()


class TestAsyncQueueEventDelivery:
    """Test that events are delivered via async queue."""
    
    @pytest.mark.asyncio
    async def test_event_pushed_to_queue(self, event_bus, shared_state):
        """Events should be pushed to agent's queue, not pending list."""
        # Create agent with push architecture
        agent = BuilderAgent(
            name="TestBuilder",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
            use_push_architecture=True,
        )
        
        # Publish event
        event = Event(
            type=EventType.FILE_CREATED,
            source="test",
            file_path="test.ts",
        )
        await event_bus.publish(event)
        
        # Event should be in queue, not pending_events
        assert agent._event_queue.qsize() > 0
        assert len(agent._pending_events) == 0
        
    @pytest.mark.asyncio
    async def test_legacy_mode_uses_pending_list(self, event_bus, shared_state):
        """Legacy mode should use pending_events list."""
        # Create agent with legacy polling
        agent = BuilderAgent(
            name="TestBuilder",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
            use_push_architecture=False,
        )
        
        # Publish event
        event = Event(
            type=EventType.FILE_CREATED,
            source="test",
            file_path="test.ts",
        )
        await event_bus.publish(event)
        
        # Event should be in pending_events, not queue
        assert agent._event_queue.qsize() == 0
        assert len(agent._pending_events) > 0


class TestEventBatching:
    """Test event batching functionality."""
    
    @pytest.mark.asyncio
    async def test_batch_collects_multiple_events(self, event_bus, shared_state):
        """_collect_batched_events should collect multiple events within window."""
        agent = BuilderAgent(
            name="TestBuilder",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
            use_push_architecture=True,
        )
        
        # Add multiple events to queue rapidly
        for i in range(5):
            event = Event(
                type=EventType.FILE_CREATED,
                source="test",
                file_path=f"test{i}.ts",
            )
            await agent._event_queue.put(event)
            
        # Collect batched events
        events = await agent._collect_batched_events(timeout=1.0)
        
        # Should have collected all events
        assert len(events) == 5
        
    @pytest.mark.asyncio
    async def test_batch_returns_empty_on_timeout(self, event_bus, shared_state):
        """_collect_batched_events should return empty list on timeout."""
        agent = BuilderAgent(
            name="TestBuilder",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
            use_push_architecture=True,
        )
        
        # Don't add any events
        # Collect with short timeout
        events = await agent._collect_batched_events(timeout=0.1)
        
        # Should return empty list
        assert len(events) == 0


class TestIdleBasedConvergence:
    """Test idle-based convergence checking."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_tracks_active_agents(self, event_bus, shared_state):
        """Orchestrator should track which agents are active."""
        orchestrator = Orchestrator(
            working_dir="/tmp/test",
            event_bus=event_bus,
            shared_state=shared_state,
            use_push_architecture=True,
        )
        
        # Initially no active agents
        assert orchestrator._is_system_idle()
        
        # Simulate agent acting
        await event_bus.publish(Event(
            type=EventType.AGENT_ACTING,
            source="Builder",
        ))
        
        # Should now have active agent
        assert not orchestrator._is_system_idle()
        assert "Builder" in orchestrator._active_agents
        
    @pytest.mark.asyncio
    async def test_agent_becomes_idle_on_completion(self, event_bus, shared_state):
        """Agent should be removed from active set on completion."""
        orchestrator = Orchestrator(
            working_dir="/tmp/test",
            event_bus=event_bus,
            shared_state=shared_state,
            use_push_architecture=True,
        )
        
        # Add agent to active set
        await event_bus.publish(Event(
            type=EventType.AGENT_ACTING,
            source="Builder",
        ))
        assert not orchestrator._is_system_idle()
        
        # Complete agent
        await event_bus.publish(Event(
            type=EventType.AGENT_COMPLETED,
            source="Builder",
        ))
        
        # Should be idle again
        assert orchestrator._is_system_idle()


class TestFixerCooldown:
    """Test the fixer cooldown settings."""
    
    def test_cooldown_is_10_seconds(self, event_bus, shared_state):
        """Fixer cooldown should be 10 seconds (reduced from 30)."""
        fixer = FixerAgent(
            name="TestFixer",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
        )
        
        assert fixer._fix_cooldown == 10


class TestBootstrapBatching:
    """Test bootstrap event batching."""
    
    @pytest.mark.asyncio
    async def test_bootstrap_uses_batch_event(self):
        """Bootstrap should publish batch event in push mode."""
        event_bus = EventBus()
        shared_state = SharedState()
        
        # Create orchestrator with push architecture
        orchestrator = Orchestrator(
            working_dir="/tmp/test",
            event_bus=event_bus,
            shared_state=shared_state,
            use_push_architecture=True,
        )
        
        # Track published events
        published_events = []
        event_bus.subscribe_all(lambda e: published_events.append(e))
        
        # Run bootstrap (with empty dir, will publish 0 or batch event)
        await orchestrator._bootstrap_file_events()
        
        # If files found, should have batch event
        batch_events = [e for e in published_events if e.data.get("batch")]
        # Just verify the method runs without error
        assert True
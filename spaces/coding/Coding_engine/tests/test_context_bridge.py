"""
Test AgentContextBridge integration.

Verifies that:
1. AgentContextBridge can be created from RichContextProvider
2. MergedContext properly combines static and dynamic context
3. Agents can access context via get_task_context()
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path


class TestAgentContextBridge:
    """Test AgentContextBridge functionality."""

    def test_merged_context_dataclass(self):
        """Test MergedContext dataclass initialization."""
        from src.engine.agent_context_bridge import MergedContext

        ctx = MergedContext(
            tech_stack={"backend": {"framework": "NestJS"}},
            requirements=[{"id": "REQ-1", "description": "Test requirement"}],
            diagrams=[{"diagram_type": "erDiagram", "title": "ER", "content": "graph TB"}],
            entities=[{"name": "User", "description": "User entity"}],
            design_tokens={"colors": {"primary": "#1E3A8A"}},
            api_endpoints=[{"method": "GET", "path": "/api/users"}],
            rag_results=[{"file_path": "example.ts", "content": "code", "score": 0.9}],
        )

        assert ctx.tech_stack["backend"]["framework"] == "NestJS"
        assert len(ctx.requirements) == 1
        assert len(ctx.diagrams) == 1
        assert len(ctx.entities) == 1
        assert ctx.design_tokens["colors"]["primary"] == "#1E3A8A"
        assert len(ctx.api_endpoints) == 1
        assert len(ctx.rag_results) == 1

    def test_merged_context_get_prompt_context(self):
        """Test prompt context generation."""
        from src.engine.agent_context_bridge import MergedContext

        ctx = MergedContext(
            tech_stack={
                "backend": {"framework": "NestJS", "language": "TypeScript"},
                "frontend": {"framework": "React"},
                "database": {"type": "PostgreSQL"},
            },
            entities=[{"name": "User", "description": "User entity", "attributes": [{"name": "email", "type": "string"}]}],
            diagrams=[{"diagram_type": "erDiagram", "title": "Database Schema", "content": "User ||--o{ Order"}],
            design_tokens={"colors": {"primary": "#1E3A8A"}, "typography": {"fontFamily": "Inter"}},
            rag_results=[{"relative_path": "src/models/user.ts", "content": "export interface User {}", "score": 0.95}],
        )

        prompt_context = ctx.get_prompt_context(max_diagrams=2, max_entities=5, max_rag_results=3)

        # Should contain tech stack
        assert "## Tech Stack" in prompt_context
        assert "NestJS" in prompt_context
        assert "React" in prompt_context
        assert "PostgreSQL" in prompt_context

        # Should contain entities
        assert "## Data Entities" in prompt_context
        assert "User" in prompt_context

        # Should contain diagrams
        assert "## Relevant Diagrams" in prompt_context
        assert "erDiagram" in prompt_context or "Database Schema" in prompt_context

        # Should contain design tokens
        assert "## Design System" in prompt_context
        assert "#1E3A8A" in prompt_context

        # Should contain RAG results
        assert "## Relevant Code Examples" in prompt_context
        assert "src/models/user.ts" in prompt_context

    def test_merged_context_to_dict(self):
        """Test summary dict generation."""
        from src.engine.agent_context_bridge import MergedContext

        ctx = MergedContext(
            entities=[{"name": "User"}, {"name": "Order"}],
            diagrams=[{"type": "erDiagram"}],
            rag_results=[{"file": "test.ts"}],
            design_tokens={"colors": {"primary": "#fff"}},
            api_endpoints=[{"path": "/api/test"}],
            epic_info={"epic_id": "EPIC-001"},
        )

        summary = ctx.to_dict()

        assert summary["entities_count"] == 2
        assert summary["diagrams_count"] == 1
        assert summary["rag_results_count"] == 1
        assert summary["has_design_tokens"] is True
        assert summary["api_endpoints_count"] == 1
        assert summary["epic"] == "EPIC-001"


class TestAgentContextBridgeCreation:
    """Test AgentContextBridge creation and context retrieval."""

    @pytest.fixture
    def mock_context_provider(self):
        """Create a mock RichContextProvider."""
        provider = Mock()
        provider.for_database_agent.return_value = Mock(
            tech_stack={"database": {"type": "PostgreSQL"}},
            requirements=[],
            diagrams=[{"diagram_type": "erDiagram", "title": "ER", "content": "graph"}],
            entities=[{"name": "User"}],
            design_tokens={},
            api_endpoints=[],
            epic_info=None,
            feature_info=None,
        )
        provider.for_api_agent.return_value = Mock(
            tech_stack={"backend": {"framework": "NestJS"}},
            requirements=[],
            diagrams=[{"diagram_type": "sequenceDiagram", "title": "Flow", "content": "sequence"}],
            entities=[],
            design_tokens={},
            api_endpoints=[{"method": "GET", "path": "/api/users"}],
            epic_info=None,
            feature_info=None,
        )
        provider.for_frontend_agent.return_value = Mock(
            tech_stack={"frontend": {"framework": "React"}},
            requirements=[],
            diagrams=[],
            entities=[],
            design_tokens={"colors": {"primary": "#1E3A8A"}},
            api_endpoints=[],
            epic_info=None,
            feature_info=None,
        )
        provider.for_generator.return_value = provider.for_frontend_agent.return_value
        return provider

    def test_bridge_creation_without_fungus(self, mock_context_provider):
        """Test bridge creation without Fungus agent."""
        from src.engine.agent_context_bridge import AgentContextBridge

        bridge = AgentContextBridge(
            context_provider=mock_context_provider,
            fungus_agent=None,
            enable_rag=False,
        )

        assert bridge.provider is mock_context_provider
        assert bridge.fungus is None
        assert bridge.enable_rag is False

    @pytest.mark.asyncio
    async def test_get_context_for_database_task(self, mock_context_provider):
        """Test getting context for database task type."""
        from src.engine.agent_context_bridge import AgentContextBridge

        bridge = AgentContextBridge(
            context_provider=mock_context_provider,
            fungus_agent=None,
            enable_rag=False,
        )

        context = await bridge.get_context_for_task(task_type="database")

        assert len(context.diagrams) > 0
        assert context.diagrams[0]["diagram_type"] == "erDiagram"
        mock_context_provider.for_database_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_context_for_api_task(self, mock_context_provider):
        """Test getting context for API task type."""
        from src.engine.agent_context_bridge import AgentContextBridge

        bridge = AgentContextBridge(
            context_provider=mock_context_provider,
            fungus_agent=None,
            enable_rag=False,
        )

        context = await bridge.get_context_for_task(task_type="api")

        assert len(context.api_endpoints) > 0
        mock_context_provider.for_api_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_context_for_frontend_task(self, mock_context_provider):
        """Test getting context for frontend task type."""
        from src.engine.agent_context_bridge import AgentContextBridge

        bridge = AgentContextBridge(
            context_provider=mock_context_provider,
            fungus_agent=None,
            enable_rag=False,
        )

        context = await bridge.get_context_for_task(task_type="frontend")

        assert context.design_tokens.get("colors", {}).get("primary") == "#1E3A8A"
        mock_context_provider.for_frontend_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_caching(self, mock_context_provider):
        """Test that context is cached."""
        from src.engine.agent_context_bridge import AgentContextBridge

        bridge = AgentContextBridge(
            context_provider=mock_context_provider,
            fungus_agent=None,
            enable_rag=False,
            cache_ttl=300,
        )

        # First call
        context1 = await bridge.get_context_for_task(task_type="database")

        # Second call - should hit cache
        context2 = await bridge.get_context_for_task(task_type="database")

        # Provider should only be called once due to caching
        assert mock_context_provider.for_database_agent.call_count == 1
        assert context1 is context2  # Same cached object

    @pytest.mark.asyncio
    async def test_convenience_methods(self, mock_context_provider):
        """Test convenience methods for common task types."""
        from src.engine.agent_context_bridge import AgentContextBridge

        bridge = AgentContextBridge(
            context_provider=mock_context_provider,
            fungus_agent=None,
            enable_rag=False,
        )

        # Test for_database
        db_ctx = await bridge.for_database()
        assert len(db_ctx.diagrams) > 0

        # Test for_api
        bridge.clear_cache()
        api_ctx = await bridge.for_api()
        assert len(api_ctx.api_endpoints) > 0

        # Test for_frontend
        bridge.clear_cache()
        fe_ctx = await bridge.for_frontend()
        assert fe_ctx.design_tokens.get("colors") is not None


class TestAutonomousAgentContextIntegration:
    """Test context integration in AutonomousAgent base class."""

    def test_agent_has_context_bridge_attribute(self):
        """Test that AutonomousAgent accepts context_bridge parameter."""
        from src.agents.autonomous_base import AutonomousAgent
        from src.mind.event_bus import EventBus
        from src.mind.shared_state import SharedState

        # These are abstract class tests - just verify the signature
        # by checking __init__ accepts context_bridge
        import inspect
        sig = inspect.signature(AutonomousAgent.__init__)
        params = list(sig.parameters.keys())
        assert "context_bridge" in params

    def test_get_task_type_default(self):
        """Test default task type returns 'generic'."""
        # This would require creating a concrete agent subclass
        # For now, we verify the method exists
        from src.agents.autonomous_base import AutonomousAgent
        assert hasattr(AutonomousAgent, "_get_task_type")


class TestDatabaseAgentContextIntegration:
    """Test context integration in DatabaseAgent."""

    def test_database_agent_has_get_task_type(self):
        """Test DatabaseAgent has _get_task_type method."""
        from src.agents.database_agent import DatabaseAgent
        assert hasattr(DatabaseAgent, "_get_task_type")

    def test_database_agent_task_type_returns_database(self):
        """Test DatabaseAgent returns 'database' task type."""
        from src.agents.database_agent import DatabaseAgent
        from src.mind.event_bus import EventBus
        from src.mind.shared_state import SharedState

        event_bus = EventBus()
        shared_state = SharedState()

        agent = DatabaseAgent(
            name="TestDatabaseAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
        )

        assert agent._get_task_type() == "database"


class TestAPIAgentContextIntegration:
    """Test context integration in APIAgent."""

    def test_api_agent_has_get_task_type(self):
        """Test APIAgent has _get_task_type method."""
        from src.agents.api_agent import APIAgent
        assert hasattr(APIAgent, "_get_task_type")

    def test_api_agent_task_type_returns_api(self):
        """Test APIAgent returns 'api' task type."""
        from src.agents.api_agent import APIAgent
        from src.mind.event_bus import EventBus
        from src.mind.shared_state import SharedState

        event_bus = EventBus()
        shared_state = SharedState()

        agent = APIAgent(
            name="TestAPIAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
        )

        assert agent._get_task_type() == "api"


class TestGeneratorAgentContextIntegration:
    """Test context integration in GeneratorAgent."""

    def test_generator_agent_has_get_task_type(self):
        """Test GeneratorAgent has _get_task_type method."""
        from src.agents.generator_agent import GeneratorAgent
        assert hasattr(GeneratorAgent, "_get_task_type")

    def test_generator_agent_task_type_returns_frontend(self):
        """Test GeneratorAgent returns 'frontend' task type."""
        from src.agents.generator_agent import GeneratorAgent
        from src.mind.event_bus import EventBus
        from src.mind.shared_state import SharedState

        event_bus = EventBus()
        shared_state = SharedState()

        agent = GeneratorAgent(
            name="TestGeneratorAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir="/tmp/test",
        )

        assert agent._get_task_type() == "frontend"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

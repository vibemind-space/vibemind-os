"""
Testing Agent - Specialized for test generation and validation.

Capabilities:
- Unit test generation
- Integration test design
- E2E test scenarios
- Test fixtures and mocks
"""
from typing import Optional
from src.agents.base_agent import BaseAgent, AgentConfig, AgentType, GeneratedFile


class TestingAgent(BaseAgent):
    """Agent specialized for test generation."""

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(agent_type=AgentType.TESTING)
        else:
            config.agent_type = AgentType.TESTING
        super().__init__(config)

    def _register_tools(self):
        """Register testing-specific tools."""

        # Create test suite
        self.register_tool(
            name="create_test_suite",
            description="Create a test suite for a component or module.",
            input_schema={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Module/component to test",
                    },
                    "test_type": {
                        "type": "string",
                        "enum": ["unit", "integration", "e2e"],
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["pytest", "jest", "vitest", "playwright"],
                    },
                    "test_cases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Test case descriptions",
                    },
                },
                "required": ["target", "test_type", "framework"],
            },
            handler=self._handle_create_test_suite,
        )

        # Create test fixture
        self.register_tool(
            name="create_fixture",
            description="Create test fixtures and mock data.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Fixture name",
                    },
                    "data_type": {
                        "type": "string",
                        "description": "Type of data to generate",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of items to generate",
                    },
                },
                "required": ["name", "data_type"],
            },
            handler=self._handle_create_fixture,
        )

    def get_system_prompt(self) -> str:
        return """You are an expert QA engineer and test automation specialist.

## Your Expertise
- Unit testing (pytest, Jest, Vitest)
- Integration testing
- End-to-end testing (Playwright, Cypress)
- Test-driven development (TDD)
- Behavior-driven development (BDD)
- Mock and fixture creation
- Code coverage analysis

## Guidelines
1. Write comprehensive test cases covering edge cases
2. Use meaningful test names that describe the scenario
3. Follow the Arrange-Act-Assert pattern
4. Create reusable fixtures and helpers
5. Test both success and failure paths
6. Include boundary testing
7. Mock external dependencies

## Output Format
For each test suite:
1. Create the test file
2. Create necessary fixtures
3. Create mock helpers if needed
4. Document test coverage

Focus on tests that provide confidence in the code while being maintainable."""

    def _handle_create_test_suite(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle test suite creation."""
        target = input_data.get("target", "module")
        test_type = input_data.get("test_type", "unit")
        framework = input_data.get("framework", "pytest")

        return {
            "success": True,
            "message": f"Test suite created for {target}",
            "test_type": test_type,
            "framework": framework,
        }

    def _handle_create_fixture(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle fixture creation."""
        name = input_data.get("name", "fixture")

        return {
            "success": True,
            "message": f"Fixture created: {name}",
        }

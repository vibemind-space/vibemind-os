"""
Frontend Agent - Specialized for UI and frontend development.

Capabilities:
- React/Vue/Svelte component generation
- CSS/Tailwind styling
- Responsive design
- State management
"""
from typing import Optional
from src.agents.base_agent import BaseAgent, AgentConfig, AgentType, GeneratedFile


class FrontendAgent(BaseAgent):
    """Agent specialized for frontend development."""

    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(agent_type=AgentType.FRONTEND)
        else:
            config.agent_type = AgentType.FRONTEND
        super().__init__(config)

    def _register_tools(self):
        """Register frontend-specific tools."""

        # Create React component
        self.register_tool(
            name="create_component",
            description="Create a React/Vue/Svelte component with proper structure.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Component name (PascalCase)",
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["react", "vue", "svelte"],
                        "description": "Frontend framework",
                    },
                    "props": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "required": {"type": "boolean"},
                            },
                        },
                        "description": "Component props",
                    },
                    "styling": {
                        "type": "string",
                        "enum": ["css", "tailwind", "styled-components", "css-modules"],
                        "description": "Styling approach",
                    },
                },
                "required": ["name", "framework"],
            },
            handler=self._handle_create_component,
        )

        # Generate styles
        self.register_tool(
            name="generate_styles",
            description="Generate CSS/Tailwind styles for a component.",
            input_schema={
                "type": "object",
                "properties": {
                    "component_name": {
                        "type": "string",
                        "description": "Component to style",
                    },
                    "style_type": {
                        "type": "string",
                        "enum": ["css", "tailwind", "scss"],
                    },
                    "responsive": {
                        "type": "boolean",
                        "description": "Include responsive breakpoints",
                    },
                },
                "required": ["component_name", "style_type"],
            },
            handler=self._handle_generate_styles,
        )

    def get_system_prompt(self) -> str:
        return """You are an expert frontend developer specializing in modern web applications.

## Your Expertise
- React, Vue, and Svelte frameworks
- TypeScript for type-safe code
- CSS, Tailwind CSS, and styled-components
- Responsive design and accessibility
- State management (Redux, Zustand, Pinia)
- Component-driven development

## Guidelines
1. Write TypeScript by default unless specified otherwise
2. Create reusable, composable components
3. Follow accessibility best practices (ARIA, semantic HTML)
4. Implement responsive designs (mobile-first)
5. Use proper prop validation
6. Include loading and error states

## Output Format
Use the available tools to create components and styles. For each component:
1. Create the main component file
2. Create associated styles if needed
3. Create any helper/utility files
4. Provide usage examples in your response

Focus on clean, maintainable code that follows modern frontend best practices."""

    def _handle_create_component(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle component creation."""
        name = input_data.get("name", "Component")
        framework = input_data.get("framework", "react")

        # Determine file extension
        ext = ".tsx" if framework == "react" else ".vue" if framework == "vue" else ".svelte"
        path = f"src/components/{name}{ext}"

        return {
            "success": True,
            "message": f"Component template created: {name}",
            "path": path,
            "framework": framework,
        }

    def _handle_generate_styles(
        self,
        input_data: dict,
        generated_files: list[GeneratedFile],
    ) -> dict:
        """Handle style generation."""
        component = input_data.get("component_name", "")
        style_type = input_data.get("style_type", "css")

        ext = ".css" if style_type == "css" else ".scss" if style_type == "scss" else ".css"
        path = f"src/components/{component}{ext}"

        return {
            "success": True,
            "message": f"Styles template created for {component}",
            "path": path,
        }

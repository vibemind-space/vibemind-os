#!/usr/bin/env python3
"""
Mermaid Diagram Generator - Phase 3.5

Generates Mermaid diagrams showing requirement relationships:
Epic -> Requirements -> Entities -> APIs -> Tests

Features:
- Generates per-Epic relationship diagrams
- Full project overview diagram
- Exports as .md files for documentation
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Try to import parsers
try:
    from epic_parser import EpicParser, Epic
    from api_documentation_parser import APIDocumentationParser
    from test_documentation_parser import TestDocumentationParser
except ImportError:
    from mcp_plugins.servers.grpc_host.epic_parser import EpicParser, Epic
    from mcp_plugins.servers.grpc_host.api_documentation_parser import APIDocumentationParser
    from mcp_plugins.servers.grpc_host.test_documentation_parser import TestDocumentationParser


@dataclass
class DiagramConfig:
    """Configuration for diagram generation"""
    max_entities_per_req: int = 5
    max_apis_per_req: int = 5
    max_scenarios_per_us: int = 3
    include_tests: bool = True
    include_apis: bool = True
    include_entities: bool = True
    direction: str = "TD"  # TD (top-down), LR (left-right)


class MermaidGenerator:
    """
    Generates Mermaid diagrams for requirement relationships.

    Visualizes:
    - Epic to Requirements relationships
    - Requirements to Entities relationships
    - Requirements to API Endpoints relationships
    - User Stories to Test Cases relationships
    """

    def __init__(self, project_path: str):
        """
        Args:
            project_path: Path to the input project
        """
        self.project_path = Path(project_path)
        self.epic_parser = EpicParser(str(project_path))
        self.api_parser = APIDocumentationParser(str(project_path))
        self.test_parser = TestDocumentationParser(str(project_path))

        # Load all data
        self._epics: List[Epic] = []
        self._loaded = False

        logger.info(f"MermaidGenerator initialized for: {project_path}")

    def _ensure_loaded(self):
        """Ensure all parsers have loaded their data"""
        if not self._loaded:
            self._epics = self.epic_parser.parse_all_epics()
            self.api_parser.parse_all_endpoints()
            self.test_parser.parse_all_features()
            self._loaded = True

    def generate_epic_diagram(self, epic_id: str, config: Optional[DiagramConfig] = None) -> str:
        """
        Generate a Mermaid diagram for a single Epic.

        Args:
            epic_id: Epic ID (e.g., "EPIC-001")
            config: Optional diagram configuration

        Returns:
            Mermaid diagram as string
        """
        self._ensure_loaded()
        config = config or DiagramConfig()

        epic = next((e for e in self._epics if e.id == epic_id), None)
        if not epic:
            return f"graph {config.direction}\n    ERROR[Epic {epic_id} not found]"

        lines = [
            f"graph {config.direction}",
            f"    %% {epic.id}: {epic.name}",
            "",
            "    %% Epic node",
            f"    E{epic.id.replace('-', '')}[<b>{epic.id}</b><br/>{self._escape(epic.name[:40])}]",
            f"    style E{epic.id.replace('-', '')} fill:#4f46e5,color:#fff,stroke:#4338ca",
            "",
            "    %% Requirements"
        ]

        # Requirements
        for i, req in enumerate(epic.requirements[:10]):  # Limit to 10
            req_safe = req.replace('-', '_')
            lines.append(f"    R{req_safe}[{req}]")
            lines.append(f"    E{epic.id.replace('-', '')} --> R{req_safe}")
            lines.append(f"    style R{req_safe} fill:#7c3aed,color:#fff")

        lines.append("")
        lines.append("    %% Entities")

        # Entities
        if config.include_entities:
            for i, req in enumerate(epic.requirements[:5]):
                req_safe = req.replace('-', '_')
                entities = self.epic_parser._requirement_to_entities.get(req, [])

                for j, entity in enumerate(entities[:config.max_entities_per_req]):
                    entity_safe = entity.replace(' ', '_')
                    lines.append(f"    ENT_{req_safe}_{entity_safe}[{entity}]")
                    lines.append(f"    R{req_safe} --> ENT_{req_safe}_{entity_safe}")
                    lines.append(f"    style ENT_{req_safe}_{entity_safe} fill:#10b981,color:#fff")

        lines.append("")
        lines.append("    %% APIs")

        # APIs
        if config.include_apis:
            for i, req in enumerate(epic.requirements[:5]):
                req_safe = req.replace('-', '_')
                endpoints = self.api_parser.get_endpoints_by_requirement(req)

                for j, ep in enumerate(endpoints[:config.max_apis_per_req]):
                    api_id = f"API_{i}_{j}"
                    api_label = f"{ep.method} {ep.path.split('/')[-1]}"
                    lines.append(f"    {api_id}[{api_label}]")
                    lines.append(f"    R{req_safe} --> {api_id}")
                    lines.append(f"    style {api_id} fill:#f59e0b,color:#000")

        lines.append("")
        lines.append("    %% User Stories & Tests")

        # User Stories and Tests
        if config.include_tests:
            for i, us_id in enumerate(epic.user_stories[:5]):
                us_safe = us_id.replace('-', '_')
                lines.append(f"    US_{us_safe}[{us_id}]")
                lines.append(f"    E{epic.id.replace('-', '')} --> US_{us_safe}")
                lines.append(f"    style US_{us_safe} fill:#3b82f6,color:#fff")

                # Tests for this user story
                features = self.test_parser.get_features_by_user_story(us_id)
                for feature in features[:1]:  # One feature per US
                    for k, scenario in enumerate(feature.scenarios[:config.max_scenarios_per_us]):
                        test_id = f"TC_{us_safe}_{k}"
                        test_label = scenario.name[:25] + "..." if len(scenario.name) > 25 else scenario.name
                        lines.append(f"    {test_id}[{self._escape(test_label)}]")
                        lines.append(f"    US_{us_safe} --> {test_id}")

                        # Color by test category
                        if scenario.is_happy_path:
                            lines.append(f"    style {test_id} fill:#22c55e,color:#000")
                        elif scenario.is_negative:
                            lines.append(f"    style {test_id} fill:#ef4444,color:#fff")
                        elif scenario.is_boundary:
                            lines.append(f"    style {test_id} fill:#f97316,color:#000")
                        else:
                            lines.append(f"    style {test_id} fill:#64748b,color:#fff")

        return '\n'.join(lines)

    def generate_project_overview_diagram(self, config: Optional[DiagramConfig] = None) -> str:
        """
        Generate overview diagram showing all Epics.

        Returns:
            Mermaid diagram as string
        """
        self._ensure_loaded()
        config = config or DiagramConfig()

        lines = [
            f"graph {config.direction}",
            "    %% Project Overview",
            "",
            "    subgraph Project[WhatsApp-like Messaging Platform]",
        ]

        # Add all epics
        for epic in self._epics:
            epic_safe = epic.id.replace('-', '')
            us_count = len(epic.user_stories)
            req_count = len(epic.requirements)

            lines.append(f"        {epic_safe}[<b>{epic.id}</b><br/>{self._escape(epic.name[:30])}<br/>{us_count} US / {req_count} REQ]")

        lines.append("    end")
        lines.append("")

        # Add epic dependencies (simplified - just sequential for now)
        for i, epic in enumerate(self._epics[:-1]):
            curr_safe = epic.id.replace('-', '')
            next_safe = self._epics[i + 1].id.replace('-', '')
            lines.append(f"    {curr_safe} --> {next_safe}")

        lines.append("")
        lines.append("    %% Styling")

        # Color epics by status
        for epic in self._epics:
            epic_safe = epic.id.replace('-', '')
            if epic.status == "completed":
                lines.append(f"    style {epic_safe} fill:#22c55e,color:#fff")
            elif epic.status == "running":
                lines.append(f"    style {epic_safe} fill:#f59e0b,color:#000")
            elif epic.status == "failed":
                lines.append(f"    style {epic_safe} fill:#ef4444,color:#fff")
            else:
                lines.append(f"    style {epic_safe} fill:#4f46e5,color:#fff")

        return '\n'.join(lines)

    def generate_requirement_chain_diagram(self, req_id: str) -> str:
        """
        Generate diagram for a single requirement showing all linked items.

        Args:
            req_id: Requirement ID (e.g., "WA-AUTH-001")

        Returns:
            Mermaid diagram as string
        """
        self._ensure_loaded()

        # Find which epic this requirement belongs to
        epic = None
        for e in self._epics:
            if req_id in e.requirements:
                epic = e
                break

        lines = [
            "graph LR",
            f"    %% Requirement Chain: {req_id}",
            "",
            f"    REQ[{req_id}]",
            "    style REQ fill:#7c3aed,color:#fff,stroke-width:3px",
            "",
        ]

        # Epic
        if epic:
            epic_safe = epic.id.replace('-', '')
            lines.append(f"    EPIC_{epic_safe}[{epic.id}]")
            lines.append(f"    EPIC_{epic_safe} --> REQ")
            lines.append(f"    style EPIC_{epic_safe} fill:#4f46e5,color:#fff")
            lines.append("")

        # Entities
        entities = self.epic_parser._requirement_to_entities.get(req_id, [])
        if entities:
            lines.append("    %% Entities")
            for entity in entities:
                entity_safe = entity.replace(' ', '_')
                lines.append(f"    ENT_{entity_safe}[{entity}]")
                lines.append(f"    REQ --> ENT_{entity_safe}")
                lines.append(f"    style ENT_{entity_safe} fill:#10b981,color:#fff")
            lines.append("")

        # APIs
        endpoints = self.api_parser.get_endpoints_by_requirement(req_id)
        if endpoints:
            lines.append("    %% APIs")
            for i, ep in enumerate(endpoints[:8]):
                api_id = f"API_{i}"
                lines.append(f"    {api_id}[{ep.method} {ep.path.split('/')[-1]}]")
                lines.append(f"    REQ --> {api_id}")
                lines.append(f"    style {api_id} fill:#f59e0b,color:#000")
            lines.append("")

        return '\n'.join(lines)

    def _escape(self, text: str) -> str:
        """Escape special characters for Mermaid"""
        return text.replace('"', "'").replace('<', '&lt;').replace('>', '&gt;')

    def save_epic_diagram(self, epic_id: str, output_dir: Optional[str] = None) -> str:
        """
        Save Epic diagram to file.

        Args:
            epic_id: Epic ID
            output_dir: Output directory (default: project/docs/diagrams)

        Returns:
            Path to saved file
        """
        if output_dir is None:
            output_dir = self.project_path / "docs" / "diagrams"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        diagram = self.generate_epic_diagram(epic_id)
        filename = f"{epic_id.lower()}-diagram.md"
        output_path = output_dir / filename

        content = f"""# {epic_id} Relationship Diagram

```mermaid
{diagram}
```

## Legend

- **Purple**: Epic and Requirements
- **Green**: Entities (Data Models)
- **Orange**: API Endpoints
- **Blue**: User Stories
- **Green Tests**: Happy Path
- **Red Tests**: Negative Cases
- **Orange Tests**: Boundary Cases
"""

        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved diagram to: {output_path}")
        return str(output_path)

    def save_all_diagrams(self, output_dir: Optional[str] = None) -> List[str]:
        """
        Save all diagrams (overview + per-epic).

        Returns:
            List of saved file paths
        """
        self._ensure_loaded()

        if output_dir is None:
            output_dir = self.project_path / "docs" / "diagrams"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        saved_files = []

        # Save overview
        overview_diagram = self.generate_project_overview_diagram()
        overview_path = output_dir / "project-overview.md"
        overview_content = f"""# Project Overview Diagram

```mermaid
{overview_diagram}
```

## Epics Summary

| Epic | Name | User Stories | Requirements |
|------|------|--------------|--------------|
"""
        for epic in self._epics:
            overview_content += f"| {epic.id} | {epic.name} | {len(epic.user_stories)} | {len(epic.requirements)} |\n"

        overview_path.write_text(overview_content, encoding="utf-8")
        saved_files.append(str(overview_path))

        # Save per-epic diagrams
        for epic in self._epics:
            path = self.save_epic_diagram(epic.id, str(output_dir))
            saved_files.append(path)

        logger.info(f"Saved {len(saved_files)} diagram files")
        return saved_files


# =============================================================================
# Test
# =============================================================================

def test_mermaid_generator():
    """Test the MermaidGenerator"""
    print("=== Mermaid Generator Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    generator = MermaidGenerator(str(test_path))

    # Test 1: Generate EPIC-001 diagram
    print("1. Generate EPIC-001 diagram:")
    diagram = generator.generate_epic_diagram("EPIC-001")
    print(f"   Generated diagram ({len(diagram)} chars)")
    print(f"   Preview:\n{diagram[:500]}...")

    # Test 2: Generate project overview
    print("\n2. Generate project overview:")
    overview = generator.generate_project_overview_diagram()
    print(f"   Generated overview ({len(overview)} chars)")
    print(f"   Preview:\n{overview[:400]}...")

    # Test 3: Generate requirement chain
    print("\n3. Generate requirement chain for WA-AUTH-001:")
    chain = generator.generate_requirement_chain_diagram("WA-AUTH-001")
    print(f"   Generated chain ({len(chain)} chars)")
    print(f"   Preview:\n{chain[:300]}...")

    # Test 4: Save diagrams (dry run)
    print("\n4. Save test:")
    output_dir = test_path / "tasks" / "diagrams"
    print(f"   Would save to: {output_dir}")

    # Actually save one
    saved_path = generator.save_epic_diagram("EPIC-001", str(output_dir))
    print(f"   Saved: {saved_path}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_mermaid_generator()

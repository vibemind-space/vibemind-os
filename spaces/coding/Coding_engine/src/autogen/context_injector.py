"""
Phase 29: Context Injector for TaskExecutor prompts.

Formats the enrichment_context dict (from TaskEnricher) into prompt-friendly
text blocks that Claude CLI can use during code generation. Injected into
TaskExecutor._gather_context() between the existing sections and the
final "## Instructions" block.

Token budget: ~1500 chars max per section, ~3000 chars total enrichment.
"""

from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ContextInjector:
    """
    Formats task.enrichment_context into prompt text blocks.

    Usage in TaskExecutor._gather_context():
        enrichment_text = ContextInjector.format_enrichment(task)
        prompt_parts.append(enrichment_text)
    """

    @staticmethod
    def format_enrichment(task: Any) -> str:
        """
        Format all enrichment context into a single prompt string.

        Returns empty string if no enrichment context exists.
        Keeps total output under ~3000 chars to stay within token budget.
        """
        ctx = getattr(task, "enrichment_context", None)
        if not ctx:
            return ""

        sections: List[str] = []

        # 1. Diagrams (architecture/flow context)
        diagrams = ctx.get("diagrams", [])
        if diagrams:
            diagram_text = ContextInjector._format_diagrams(diagrams)
            if diagram_text:
                sections.append(diagram_text)

        # 2. Known gaps / self-critique warnings
        known_gaps = ctx.get("known_gaps", [])
        if known_gaps:
            gap_text = ContextInjector._format_known_gaps(known_gaps)
            if gap_text:
                sections.append(gap_text)

        # 3. Related DTOs (OpenAPI schemas for schema tasks)
        related_dtos = ctx.get("related_dtos", [])
        if related_dtos:
            dto_text = ContextInjector._format_related_dtos(related_dtos)
            if dto_text:
                sections.append(dto_text)

        # 4. Gherkin test scenarios (for test_* tasks)
        test_scenarios = ctx.get("test_scenarios", "")
        if test_scenarios:
            scenario_text = ContextInjector._format_test_scenarios(test_scenarios)
            if scenario_text:
                sections.append(scenario_text)

        # 5. Component spec (for fe_component tasks)
        comp_spec = ctx.get("component_spec")
        if comp_spec:
            comp_text = ContextInjector._format_component_spec(comp_spec)
            if comp_text:
                sections.append(comp_text)

        # 6. Screen spec (for fe_page tasks)
        screen_spec = ctx.get("screen_spec")
        if screen_spec:
            screen_text = ContextInjector._format_screen_spec(screen_spec)
            if screen_text:
                sections.append(screen_text)

        # 7. Accessibility rules (for fe_* tasks)
        a11y_rules = ctx.get("accessibility_rules", [])
        if a11y_rules:
            a11y_text = ContextInjector._format_accessibility(a11y_rules)
            if a11y_text:
                sections.append(a11y_text)

        # 8. Route map (for fe_page tasks)
        routes = ctx.get("routes", [])
        if routes:
            route_text = ContextInjector._format_routes(routes)
            if route_text:
                sections.append(route_text)

        # 9. Design tokens (for fe_* tasks) — Phase 29c
        design_tokens = ctx.get("design_tokens")
        if design_tokens:
            tokens_text = ContextInjector._format_design_tokens(design_tokens)
            if tokens_text:
                sections.append(tokens_text)

        if not sections:
            return ""

        # Combine with header
        header = "## Enrichment Context (from project documentation)"
        result = header + "\n\n" + "\n\n".join(sections)

        # Hard cap at 3500 chars to protect token budget
        if len(result) > 3500:
            result = result[:3470] + "\n... (truncated)"

        return result

    @staticmethod
    def format_user_stories_detail(task: Any) -> str:
        """
        Format linked user stories with their full descriptions.

        Augments the existing 'Related User Stories' section (which only
        shows IDs) with the actual story details: as_a / i_want / so_that.

        Returns empty string if no enrichment context or no user story details.
        """
        ctx = getattr(task, "enrichment_context", None)
        if not ctx:
            return ""

        # We stored user story details in enrichment_context during enrichment
        stories = ctx.get("user_story_details", [])
        if not stories:
            return ""

        lines = ["## User Story Details"]
        for story in stories[:3]:  # Cap at 3 for token budget
            title = story.get("title", "")
            as_a = story.get("as_a", "")
            i_want = story.get("i_want", "")
            so_that = story.get("so_that", "")

            if as_a and i_want:
                lines.append(f"- **{title}**: As {as_a}, I want {i_want}")
                if so_that:
                    lines.append(f"  so that {so_that}")
            elif title:
                lines.append(f"- {title}")

        return "\n".join(lines) if len(lines) > 1 else ""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION FORMATTERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _format_diagrams(diagrams: List[Dict]) -> str:
        """Format diagram content for the prompt (max ~1200 chars)."""
        lines = ["### Architecture Diagrams"]
        budget = 1200
        used = 0

        for d in diagrams[:3]:
            dtype = d.get("type", "diagram")
            fname = d.get("file", "")
            content = d.get("content", "")

            header_line = f"**{dtype}** (`{fname}`):"
            content_block = f"```mermaid\n{content}\n```"
            block = f"{header_line}\n{content_block}"

            if used + len(block) > budget:
                # Try truncating the content
                remaining = budget - used - len(header_line) - 20
                if remaining > 100:
                    truncated_content = content[:remaining] + "..."
                    block = f"{header_line}\n```mermaid\n{truncated_content}\n```"
                else:
                    break

            lines.append(block)
            used += len(block)

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _format_known_gaps(gaps: List[Dict]) -> str:
        """Format self-critique warnings (max ~600 chars)."""
        lines = ["### Known Issues (from self-critique)"]

        for gap in gaps[:3]:
            severity = gap.get("severity", "").upper()
            title = gap.get("title", "")
            suggestion = gap.get("suggestion", "")

            if suggestion:
                lines.append(f"- [{severity}] {title}: {suggestion[:150]}")
            elif title:
                lines.append(f"- [{severity}] {title}")

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _format_related_dtos(dtos: List[Dict]) -> str:
        """Format OpenAPI DTO schemas for schema tasks (max ~1000 chars)."""
        lines = ["### Related DTOs (from OpenAPI spec)"]
        lines.append("These DTOs will consume this Prisma model. Ensure field names align:")

        budget = 900
        used = 0

        for dto in dtos[:4]:
            name = dto.get("name", "")
            properties = dto.get("properties", [])

            dto_line = f"- **{name}**: "
            prop_parts = []
            for p in properties[:8]:
                pname = p.get("name", "")
                ptype = p.get("type", "")
                enum = p.get("enum", [])
                if enum:
                    prop_parts.append(f"{pname}: {ptype} enum({','.join(str(e) for e in enum[:5])})")
                else:
                    prop_parts.append(f"{pname}: {ptype}")

            dto_line += ", ".join(prop_parts)

            if used + len(dto_line) > budget:
                break

            lines.append(dto_line)
            used += len(dto_line)

        return "\n".join(lines) if len(lines) > 2 else ""

    @staticmethod
    def _format_test_scenarios(gherkin: str) -> str:
        """Format Gherkin test scenarios for the prompt (max ~900 chars)."""
        lines = ["### Test Scenarios (from test documentation)"]
        lines.append("Implement these Gherkin scenarios:")
        truncated = gherkin[:850] if len(gherkin) > 850 else gherkin
        lines.append(f"```gherkin\n{truncated}\n```")
        return "\n".join(lines)

    @staticmethod
    def _format_component_spec(spec: Dict) -> str:
        """Format component specification for the prompt."""
        name = spec.get("name", "")
        lines = [f"### Component Spec: {name}"]

        # Variants
        variants = spec.get("variants", [])
        if variants:
            lines.append(f"**Variants:** {', '.join(variants)}")

        # Props table
        props = spec.get("props", [])
        if props:
            lines.append("**Props:**")
            for p in props[:8]:
                lines.append(f"- `{p['name']}`: `{p['type']}`")

        # Accessibility
        accessibility = spec.get("accessibility", {})
        if accessibility:
            lines.append("**Accessibility:**")
            for key, val in accessibility.items():
                lines.append(f"- {key}: {val}")

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _format_screen_spec(spec: Dict) -> str:
        """Format screen specification for the prompt."""
        title = spec.get("title", "")
        route = spec.get("route", "")
        lines = [f"### Screen Spec: {title}"]
        lines.append(f"**Route:** `{route}`")

        # API endpoints this screen must call
        api_endpoints = spec.get("api_endpoints", [])
        if api_endpoints:
            lines.append("**API Calls Required:**")
            for ep in api_endpoints[:6]:
                lines.append(f"- `{ep}`")

        # Components to use with their details
        comp_details = spec.get("component_details", [])
        if comp_details:
            lines.append("**Components to Import:**")
            for cd in comp_details[:5]:
                comp_name = cd.get("name", "")
                a11y = cd.get("accessibility", {})
                role = a11y.get("role", "")
                prop_names = [p["name"] for p in cd.get("props", [])[:4]]
                detail = f"- `{comp_name}` (props: {', '.join(prop_names)})"
                if role:
                    detail += f" [role={role}]"
                lines.append(detail)
        else:
            # Fallback: just list component IDs
            components = spec.get("components", [])
            if components:
                lines.append(f"**Components:** {', '.join(components[:8])}")

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _format_accessibility(rules: List[str]) -> str:
        """Format WCAG accessibility rules for the prompt."""
        lines = ["### Accessibility Requirements (WCAG 2.1 AA)"]
        for rule in rules[:6]:
            lines.append(f"- {rule}")
        return "\n".join(lines)

    @staticmethod
    def _format_routes(routes: List[Dict]) -> str:
        """Format related routes for the prompt."""
        lines = ["### Related Routes"]
        for r in routes[:5]:
            name = r.get("name", "")
            route = r.get("route", "")
            content = r.get("content", "")
            lines.append(f"- `{route}` — {name} ({content})")
        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _format_design_tokens(tokens: Dict) -> str:
        """Format design system tokens for the prompt (~400 chars)."""
        lines = ["### Design System Tokens"]

        # Colors
        colors = tokens.get("colors", {})
        if colors:
            color_parts = [f"{k}: {v}" for k, v in list(colors.items())[:8]]
            lines.append(f"**Colors:** {', '.join(color_parts)}")

        # Font family
        font = tokens.get("font_family", "")
        if font:
            lines.append(f"**Font:** {font}")

        # Typography scale
        typo = tokens.get("typography", {})
        if typo:
            typo_parts = [f"{k}: {v}" for k, v in list(typo.items())[:6]]
            lines.append(f"**Typography:** {', '.join(typo_parts)}")

        # Spacing
        spacing = tokens.get("spacing", {})
        if spacing:
            sp_parts = [f"{k}: {v}" for k, v in list(spacing.items())[:7]]
            lines.append(f"**Spacing:** {', '.join(sp_parts)}")

        # Breakpoints
        breakpoints = tokens.get("breakpoints", {})
        if breakpoints:
            bp_parts = [f"{k}: {v}px" for k, v in list(breakpoints.items())[:5]]
            lines.append(f"**Breakpoints:** {', '.join(bp_parts)}")

        # Border radius
        radius = tokens.get("border_radius", {})
        if radius:
            br_parts = [f"{k}: {v}" for k, v in list(radius.items())[:5]]
            lines.append(f"**Border Radius:** {', '.join(br_parts)}")

        return "\n".join(lines) if len(lines) > 1 else ""

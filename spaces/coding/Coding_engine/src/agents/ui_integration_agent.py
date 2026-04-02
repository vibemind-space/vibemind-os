"""
UIIntegrationAgent - Automatically integrates new components into the main App.

Monitors for new component files and automatically:
1. Detects new components in src/components/
2. Groups them by category (billing, orders, analytics, etc.)
3. Updates App.tsx with proper navigation/routing
4. Maintains a sidebar navigation structure

Events:
- Subscribes to: FILE_CREATED, CODE_GENERATED, GENERATION_COMPLETE
- Publishes: UI_INTEGRATED, UI_INTEGRATION_FAILED
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType
from src.utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

logger = structlog.get_logger(__name__)


@dataclass
class ComponentInfo:
    """Information about a discovered component."""
    name: str  # Component name (e.g., "ProcessMonitor")
    path: str  # Import path (e.g., "./components/ProcessMonitor")
    category: str  # Category for grouping (e.g., "monitoring", "billing")
    display_name: str  # Human-readable name for navigation
    export_name: str  # The exported component name


@dataclass
class IntegrationResult:
    """Result of UI integration."""
    components_found: int = 0
    components_added: int = 0
    categories: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Category mappings for organizing navigation
CATEGORY_MAPPINGS = {
    "billing": ["billing", "abrechnung", "invoice", "payment", "dunning", "discount"],
    "orders": ["order", "auftragsmanagement", "cancellation", "draft"],
    "analytics": ["analytics", "reports", "financial"],
    "monitoring": ["monitor", "process", "tracking", "port"],
    "validation": ["validation", "compliance", "quality"],
    "documents": ["document", "pod", "upload", "export", "import"],
    "communication": ["communication", "notification", "edi"],
    "configuration": ["config", "settings", "template", "rule"],
    "transport": ["transport", "geofence", "route"],
}

CATEGORY_DISPLAY_NAMES = {
    "billing": "Abrechnung",
    "orders": "Aufträge",
    "analytics": "Analyse",
    "monitoring": "Monitoring",
    "validation": "Validierung",
    "documents": "Dokumente",
    "communication": "Kommunikation",
    "configuration": "Konfiguration",
    "transport": "Transport",
    "other": "Weitere",
}


class UIIntegrationAgent(AutonomousAgent):
    """
    Automatically integrates new components into the main App.

    Monitors component directories and updates App.tsx to include
    new components with proper navigation structure.
    """

    COOLDOWN_SECONDS = 10.0  # Run more frequently to catch new components
    DEBOUNCE_SECONDS = 2.0   # Shorter debounce for faster integration

    def __init__(
        self,
        name: str = "UIIntegrationAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self._pending_integration: Optional[asyncio.Task] = None
        self._last_integration: Optional[datetime] = None
        self._known_components: list[ComponentInfo] = []
        self.logger = logger.bind(agent=name)

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.FILE_CREATED,
            EventType.FILE_MODIFIED,
            EventType.CODE_GENERATED,
            EventType.CODE_FIXED,
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Check if we should integrate new components - triggers on every CLI complete."""
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Always act on these completion events
            if event.type in (
                EventType.GENERATION_COMPLETE,
                EventType.CODE_GENERATED,
                EventType.CODE_FIXED,
                EventType.BUILD_SUCCEEDED,
            ):
                self.logger.debug("ui_integration_triggered", event_type=event.type.value)
                return True

            # For file events, check if it's a component/page file
            if event.type in (EventType.FILE_CREATED, EventType.FILE_MODIFIED):
                file_path = event.data.get("file_path", "") if event.data else ""
                # Trigger for components, pages, or App.tsx changes
                if any(p in file_path for p in ["/components/", "\\components\\", "/pages/", "\\pages\\"]):
                    if file_path.endswith(".tsx") or file_path.endswith("index.ts"):
                        return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Integrate new components into App.tsx using LLM."""
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        # Cancel any pending integration
        if self._pending_integration and not self._pending_integration.done():
            self._pending_integration.cancel()

        # Debounce: wait for files to settle
        await asyncio.sleep(self.DEBOUNCE_SECONDS)

        # Discover all components
        components = self._discover_components()

        if not components:
            self.logger.info("no_components_found")
            return

        # Check for new components
        current_component_set = {(c.path, c.export_name) for c in components}
        known_set = {(c.path, c.export_name) for c in self._known_components} if isinstance(self._known_components, list) else set()

        # Convert _known_components if it's still using old format
        if isinstance(self._known_components, set) and self._known_components:
            if isinstance(next(iter(self._known_components)), str):
                known_set = {(p, "") for p in self._known_components}

        new_components = current_component_set - known_set

        # Skip if no new components and not a major event
        if not new_components and event.type not in (
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
        ):
            # But still check periodically
            if self._last_integration:
                time_since_last = (datetime.now() - self._last_integration).total_seconds()
                if time_since_last < self.COOLDOWN_SECONDS:
                    self.logger.debug("no_new_components_cooldown_active")
                    return
            else:
                self.logger.debug("no_new_components")
                return

        self.logger.info(
            "integrating_components",
            total=len(components),
            new=len(new_components),
        )

        # Use LLM to generate App.tsx integration
        result = await self._update_app_tsx_with_llm(components)

        # Update known components (store as list for comparison)
        self._known_components = components.copy()
        self._last_integration = datetime.now()

        # Publish result
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=EventType.FILE_MODIFIED,
                source=self.name,
                data={
                    "action": "ui_integrated",
                    "components_added": result.components_added,
                    "categories": result.categories,
                    "errors": result.errors,
                },
            ))

    def _discover_components(self) -> list[ComponentInfo]:
        """Discover all exportable components in src/components/."""
        components = []
        components_dir = Path(self.working_dir) / "src" / "components"

        if not components_dir.exists():
            return components

        for subdir in components_dir.iterdir():
            if not subdir.is_dir():
                continue

            # Skip utility directories
            if subdir.name in ("__tests__", "common", "shared", "ui"):
                continue

            # Look for index.ts or main component file
            index_file = subdir / "index.ts"
            if index_file.exists():
                exports = self._parse_exports(index_file)
                for export_name in exports:
                    component = ComponentInfo(
                        name=subdir.name,
                        path=f"./components/{subdir.name}",
                        category=self._categorize_component(subdir.name),
                        display_name=self._format_display_name(subdir.name),
                        export_name=export_name,
                    )
                    components.append(component)
            else:
                # Look for main .tsx file
                for tsx_file in subdir.glob("*.tsx"):
                    if tsx_file.name.startswith("_"):
                        continue
                    exports = self._parse_exports(tsx_file)
                    for export_name in exports:
                        component = ComponentInfo(
                            name=subdir.name,
                            path=f"./components/{subdir.name}",
                            category=self._categorize_component(subdir.name),
                            display_name=self._format_display_name(export_name),
                            export_name=export_name,
                        )
                        components.append(component)
                    break  # Only use first .tsx file

        return components

    def _parse_exports(self, file_path: Path) -> list[str]:
        """Parse export statements from a file."""
        exports = []
        try:
            content = file_path.read_text(encoding="utf-8")

            # Match: export { ComponentName } or export { ComponentName as X }
            re_exports = re.findall(
                r"export\s*\{\s*(\w+)(?:\s+as\s+\w+)?\s*\}",
                content
            )
            exports.extend(re_exports)

            # Match: export const ComponentName or export function ComponentName
            named_exports = re.findall(
                r"export\s+(?:const|function|class)\s+(\w+)",
                content
            )
            exports.extend(named_exports)

            # Match: export default ComponentName
            default_match = re.search(
                r"export\s+default\s+(\w+)",
                content
            )
            if default_match:
                exports.append(default_match.group(1))

        except Exception as e:
            self.logger.debug("parse_exports_failed", file=str(file_path), error=str(e))

        # Filter out non-component exports
        return [e for e in exports if e[0].isupper() and "Props" not in e]

    def _categorize_component(self, name: str) -> str:
        """
        Determine category based on component name using pattern matching.

        Uses comprehensive keyword patterns with caching support.
        Returns category string (e.g., 'billing', 'orders', 'other').
        """
        name_lower = name.lower()

        # Check standard category mappings first
        for category, keywords in CATEGORY_MAPPINGS.items():
            if any(kw in name_lower for kw in keywords):
                return category

        # Extended patterns for better coverage
        extended_patterns = [
            # Layout/Structure
            (["layout", "header", "footer", "sidebar", "navbar", "container", "wrapper"], "layout"),
            # Pages
            (["page", "view", "screen", "dashboard"], "page"),
            # Forms
            (["form", "input", "editor", "wizard", "stepper"], "form"),
            # Display/Data
            (["table", "list", "grid", "card", "display", "view", "detail"], "display"),
            # Navigation
            (["nav", "menu", "breadcrumb", "tabs", "link"], "navigation"),
            # Modals/Dialogs
            (["modal", "dialog", "popup", "overlay", "drawer"], "modal"),
            # Utility
            (["button", "icon", "loading", "spinner", "tooltip", "badge"], "utility"),
            # Status/Feedback
            (["status", "progress", "alert", "toast", "error", "success"], "feedback"),
        ]

        for keywords, category in extended_patterns:
            if any(kw in name_lower for kw in keywords):
                return category

        return "other"

    async def _detect_component_category_with_llm(
        self, component_code: str, file_path: str
    ) -> dict:
        """
        Use LLM to detect component category based on code analysis.

        This provides semantic categorization that goes beyond filename patterns,
        understanding what the component actually does.

        Args:
            component_code: The component source code
            file_path: Path to the component file

        Returns:
            Dict with category, parent_component, import_suggestion
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        prompt = f"""Analyze this React component and determine its category.

## FILE: {file_path}

## CODE:
```tsx
{component_code[:2000]}
```

## CATEGORIES (choose one):
- **layout**: Contains layout structure (Header, Footer, Sidebar, MainLayout, Page wrappers)
- **page**: Represents a full page/route component
- **form**: Contains form inputs, validation, and submission logic
- **display**: Displays data (tables, cards, lists, grids)
- **navigation**: Handles routing, menus, breadcrumbs
- **modal**: Dialog/popup components
- **utility**: Reusable UI helpers (Button, Input, Loading, Tooltip)
- **billing**: Invoice, payment, dunning, discount components
- **orders**: Order management, draft, cancellation
- **analytics**: Reports, charts, dashboards
- **monitoring**: Process tracking, status displays
- **documents**: Document upload, export, import, POD
- **communication**: Notifications, messaging, EDI
- **configuration**: Settings, templates, rules

## ANALYSIS REQUIRED:
1. What is the primary purpose of this component?
2. What category best describes its function?
3. Where should it appear in navigation (parent component)?
4. How should it be imported/used?

Respond with JSON:
```json
{{
    "category": "category_name",
    "parent_component": "MainLayout or specific parent",
    "import_suggestion": "Where to import this",
    "display_name": "Human-readable name for navigation",
    "confidence": 0.9,
    "reasoning": "Brief explanation"
}}
```
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context="Component categorization for UI integration",
                agent_type="component_categorizer",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                category_info = json.loads(json_match.group(1))
                self.logger.debug(
                    "llm_category_detected",
                    file=file_path,
                    category=category_info.get("category"),
                    confidence=category_info.get("confidence"),
                )
                return category_info

        except Exception as e:
            self.logger.warning("llm_categorization_failed", file=file_path, error=str(e))

        # Fallback to rule-based categorization
        name = Path(file_path).stem
        return {
            "category": self._categorize_component(name),
            "parent_component": "MainLayout",
            "import_suggestion": f"./components/{name}",
            "display_name": self._format_display_name(name),
            "confidence": 0.5,
            "reasoning": "Fallback to keyword matching",
        }

    async def _categorize_components_batch(
        self, components: list[ComponentInfo]
    ) -> list[ComponentInfo]:
        """
        Categorize multiple components using LLM, with fallback to rules.

        Uses LLM for components that don't match known patterns.

        Args:
            components: List of discovered components

        Returns:
            Components with updated categories
        """
        updated = []

        for comp in components:
            # If already categorized by keywords, skip LLM
            if comp.category != "other":
                updated.append(comp)
                continue

            # Try to read component code
            comp_path = Path(self.working_dir) / "src" / comp.path.lstrip("./")
            if comp_path.is_dir():
                comp_file = comp_path / "index.tsx"
                if not comp_file.exists():
                    comp_file = comp_path / f"{comp.name}.tsx"
            else:
                comp_file = comp_path

            if comp_file.exists():
                try:
                    code = comp_file.read_text(encoding="utf-8")
                    llm_result = await self._detect_component_category_with_llm(
                        code, str(comp_file.relative_to(self.working_dir))
                    )

                    # Update component with LLM-detected category
                    comp.category = llm_result.get("category", comp.category)
                    comp.display_name = llm_result.get("display_name", comp.display_name)

                except Exception as e:
                    self.logger.debug("component_read_failed", path=str(comp_file), error=str(e))

            updated.append(comp)

        return updated

    def _format_display_name(self, name: str) -> str:
        """Convert CamelCase or kebab-case to display name."""
        # Split on capital letters or dashes
        parts = re.split(r'(?=[A-Z])|[-_]', name)
        parts = [p for p in parts if p]
        return " ".join(p.capitalize() for p in parts)

    async def _update_app_tsx_with_llm(self, components: list[ComponentInfo]) -> IntegrationResult:
        """Use LLM to intelligently generate App.tsx with proper navigation."""
        result = IntegrationResult()

        app_path = Path(self.working_dir) / "src" / "App.tsx"
        index_css_path = Path(self.working_dir) / "src" / "index.css"

        # Read existing CSS to understand available styles
        css_content = ""
        if index_css_path.exists():
            try:
                css_content = index_css_path.read_text(encoding="utf-8")[:2000]
            except Exception:
                pass

        # Build component info for LLM
        component_details = []
        for comp in components:
            comp_path = Path(self.working_dir) / "src" / comp.path.lstrip("./")
            if comp_path.is_dir():
                comp_file = comp_path / f"{comp.name}.tsx"
                if not comp_file.exists():
                    comp_file = comp_path / "index.tsx"
            else:
                comp_file = comp_path

            # Read component code snippet
            code_snippet = ""
            if comp_file.exists():
                try:
                    code = comp_file.read_text(encoding="utf-8")
                    # Get first 50 lines
                    code_snippet = "\n".join(code.split("\n")[:50])
                except Exception:
                    pass

            component_details.append({
                "name": comp.name,
                "export_name": comp.export_name,
                "import_path": comp.path,
                "code_preview": code_snippet[:800],
            })

        result.components_found = len(components)

        # Also check for pages
        pages_dir = Path(self.working_dir) / "src" / "pages"
        pages = []
        if pages_dir.exists():
            for page_file in pages_dir.glob("*.tsx"):
                if not page_file.name.startswith("_"):
                    exports = self._parse_exports(page_file)
                    for exp in exports:
                        pages.append({
                            "name": page_file.stem,
                            "export_name": exp,
                            "import_path": f"./pages/{page_file.stem}",
                        })

        prompt = f"""Generate a complete App.tsx that integrates all discovered components with a sidebar navigation.

## DISCOVERED COMPONENTS ({len(component_details)} total):
```json
{json.dumps(component_details, indent=2)[:4000]}
```

## DISCOVERED PAGES ({len(pages)} total):
```json
{json.dumps(pages, indent=2)[:1000]}
```

## EXISTING CSS CLASSES (from index.css):
```css
{css_content[:1500]}
```

## REQUIREMENTS:
1. Import ALL components using their exact export_name and import_path
2. Create a sidebar navigation grouped by logical categories (analyze component names/purposes)
3. Use the existing CSS classes from index.css (glass-card, btn-primary, gradient-text, etc.)
4. Implement useState for active view switching
5. Make sidebar collapsible
6. Add category headers (Main, Security, Billing, Settings, etc.)
7. Use appropriate icons/emojis for each nav item
8. Handle the case where a component might not exist yet gracefully

## OUTPUT FORMAT:
Return ONLY the complete App.tsx code, starting with imports and ending with export default App.
No markdown code blocks, no explanations - just the TypeScript code.
"""

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=120)
            llm_result = await tool.execute(
                prompt=prompt,
                context="Generate App.tsx with sidebar navigation for all components",
                agent_type="ui_integrator",
            )

            if llm_result.output:
                # Clean up the output (remove markdown if present)
                code = llm_result.output.strip()
                if code.startswith("```"):
                    # Remove markdown code block
                    lines = code.split("\n")
                    code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

                # Validate it looks like valid TSX
                if "import" in code and "export default" in code and "function App" in code:
                    app_path.write_text(code, encoding="utf-8")
                    result.components_added = len(components)
                    self.logger.info(
                        "app_tsx_generated_by_llm",
                        components=len(components),
                        pages=len(pages),
                    )
                else:
                    # Fallback to template-based generation
                    self.logger.warning("llm_output_invalid_falling_back")
                    return await self._update_app_tsx(components)
            else:
                return await self._update_app_tsx(components)

        except Exception as e:
            self.logger.error("llm_app_tsx_generation_failed", error=str(e))
            # Fallback to template-based generation
            return await self._update_app_tsx(components)

        return result

    async def _update_app_tsx(self, components: list[ComponentInfo]) -> IntegrationResult:
        """Update App.tsx with sidebar navigation for all components."""
        result = IntegrationResult()

        app_path = Path(self.working_dir) / "src" / "App.tsx"
        if not app_path.exists():
            result.errors.append("App.tsx not found")
            return result

        # Group components by category
        by_category: dict[str, list[ComponentInfo]] = {}
        for comp in components:
            if comp.category not in by_category:
                by_category[comp.category] = []
            by_category[comp.category].append(comp)

        result.categories = list(by_category.keys())
        result.components_found = len(components)

        # Generate new App.tsx content
        new_content = self._generate_app_tsx(by_category)

        try:
            app_path.write_text(new_content, encoding="utf-8")
            result.components_added = len(components)
            self.logger.info(
                "app_tsx_updated",
                components=len(components),
                categories=len(by_category),
            )
        except Exception as e:
            result.errors.append(f"Failed to write App.tsx: {e}")
            self.logger.error("app_tsx_write_failed", error=str(e))

        return result

    def _generate_app_tsx(self, by_category: dict[str, list[ComponentInfo]]) -> str:
        """Generate complete App.tsx with sidebar navigation."""
        # Build imports - track by export_name to avoid duplicates
        seen_exports: dict[str, str] = {}  # export_name -> import_statement
        alias_counter: dict[str, int] = {}  # export_name -> count for aliasing

        for category, comps in sorted(by_category.items()):
            for comp in comps:
                if comp.export_name not in seen_exports:
                    # First occurrence - use as-is
                    seen_exports[comp.export_name] = f"import {{ {comp.export_name} }} from '{comp.path}';"
                elif seen_exports[comp.export_name] != f"import {{ {comp.export_name} }} from '{comp.path}';":
                    # Duplicate export_name from different path - skip (keep first)
                    # Could use alias here if needed:
                    # alias_counter[comp.export_name] = alias_counter.get(comp.export_name, 1) + 1
                    # alias = f"{comp.export_name}_{alias_counter[comp.export_name]}"
                    self.logger.debug(
                        "duplicate_export_skipped",
                        export_name=comp.export_name,
                        path=comp.path,
                    )

        imports_str = "\n".join(sorted(seen_exports.values()))

        # Build navigation items
        nav_items = []
        for category in sorted(by_category.keys()):
            display_name = CATEGORY_DISPLAY_NAMES.get(category, category.title())
            comps = by_category[category]
            items = ", ".join(
                f'{{ id: "{c.export_name.lower()}", name: "{c.display_name}", component: {c.export_name} }}'
                for c in comps
            )
            nav_items.append(
                f'  {{ category: "{display_name}", items: [{items}] }}'
            )

        nav_items_str = ",\n".join(nav_items)

        return f'''/**
 * Auto-generated App.tsx with Sidebar Navigation
 * Generated by UIIntegrationAgent
 * Categories: {", ".join(sorted(by_category.keys()))}
 * Total Components: {sum(len(c) for c in by_category.values())}
 */

import React, {{ useState, useEffect }} from 'react';
{imports_str}

interface NavItem {{
  id: string;
  name: string;
  component: React.ComponentType;
}}

interface NavCategory {{
  category: string;
  items: NavItem[];
}}

const navigation: NavCategory[] = [
{nav_items_str}
];

function App() {{
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Set default active item
  useEffect(() => {{
    if (!activeItem && navigation.length > 0 && navigation[0].items.length > 0) {{
      setActiveItem(navigation[0].items[0].id);
      setExpandedCategories(new Set([navigation[0].category]));
    }}
  }}, []);

  const toggleCategory = (category: string) => {{
    setExpandedCategories(prev => {{
      const next = new Set(prev);
      if (next.has(category)) {{
        next.delete(category);
      }} else {{
        next.add(category);
      }}
      return next;
    }});
  }};

  const ActiveComponent = navigation
    .flatMap(cat => cat.items)
    .find(item => item.id === activeItem)?.component;

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui, sans-serif' }}>
      {{/* Sidebar */}}
      <aside
        style={{
          width: sidebarCollapsed ? '60px' : '260px',
          backgroundColor: '#1e293b',
          color: 'white',
          overflow: 'hidden',
          transition: 'width 0.2s ease',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {{/* Header */}}
        <div
          style={{
            padding: '16px',
            borderBottom: '1px solid #334155',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          {{!sidebarCollapsed && (
            <span style={{ fontWeight: 700, fontSize: '18px' }}>Microservices</span>
          )}}
          <button
            onClick={{() => setSidebarCollapsed(!sidebarCollapsed)}}
            style={{
              background: 'none',
              border: 'none',
              color: 'white',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            {{sidebarCollapsed ? '→' : '←'}}
          </button>
        </div>

        {{/* Navigation */}}
        <nav style={{ flex: 1, overflow: 'auto', padding: '8px' }}>
          {{navigation.map(cat => (
            <div key={{cat.category}} style={{ marginBottom: '4px' }}>
              <button
                onClick={{() => toggleCategory(cat.category)}}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '12px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                {{!sidebarCollapsed && cat.category}}
                {{!sidebarCollapsed && (
                  <span>{{expandedCategories.has(cat.category) ? '▼' : '▶'}}</span>
                )}}
              </button>

              {{!sidebarCollapsed && expandedCategories.has(cat.category) && (
                <div style={{ paddingLeft: '8px' }}>
                  {{cat.items.map(item => (
                    <button
                      key={{item.id}}
                      onClick={{() => setActiveItem(item.id)}}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        background: activeItem === item.id ? '#3b82f6' : 'none',
                        border: 'none',
                        borderRadius: '6px',
                        color: activeItem === item.id ? 'white' : '#cbd5e1',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontSize: '14px',
                        marginBottom: '2px',
                      }}
                    >
                      {{item.name}}
                    </button>
                  ))}}
                </div>
              )}}
            </div>
          ))}}
        </nav>

        {{/* Footer */}}
        {{!sidebarCollapsed && (
          <div
            style={{
              padding: '12px 16px',
              borderTop: '1px solid #334155',
              fontSize: '11px',
              color: '#64748b',
            }}
          >
            {{navigation.reduce((acc, cat) => acc + cat.items.length, 0)}} Module
          </div>
        )}}
      </aside>

      {{/* Main Content */}}
      <main style={{ flex: 1, overflow: 'auto', backgroundColor: '#f8fafc' }}>
        {{ActiveComponent ? (
          <ActiveComponent />
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: '#64748b',
            }}
          >
            Wähle ein Modul aus der Seitenleiste
          </div>
        )}}
      </main>
    </div>
  );
}}

export default App;
'''

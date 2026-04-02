"""Smart Context Injection — Prio 5 of Pipeline Improvements.

Assembles optimal per-file context for LLM agents.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from src.engine.spec_parser import ParsedSpec, ParsedService

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4

CONTEXT_RULES: dict[str, dict] = {
    ".service.ts": {
        "must_include": ["schema.prisma", ".dto.ts"],
        "spec_include": ["user_stories", "state_machines"],
        "max_tokens": 8000,
    },
    ".controller.ts": {
        "must_include": [".service.ts", ".dto.ts", ".guard.ts"],
        "spec_include": ["endpoints"],
        "max_tokens": 6000,
    },
    ".dto.ts": {
        "must_include": ["schema.prisma"],
        "spec_include": ["openapi"],
        "max_tokens": 3000,
    },
    ".guard.ts": {
        "must_include": [".service.ts"],
        "spec_include": [],
        "max_tokens": 2000,
    },
    ".module.ts": {
        "must_include": [".controller.ts", ".service.ts"],
        "spec_include": [],
        "max_tokens": 2000,
    },
    ".spec.ts": {
        "must_include": [".controller.ts", ".service.ts", ".dto.ts"],
        "spec_include": ["acceptance_criteria", "endpoints"],
        "max_tokens": 10000,
    },
}


class ContextInjector:
    def __init__(self, spec: ParsedSpec, completed_services: dict[str, Path] | None = None):
        self.spec = spec
        self.completed_services = completed_services or {}

    def get_context_for(self, file: Path, service: ParsedService) -> str:
        """Assemble context for a single file being filled by LLM."""
        rules = self._get_rules(file)
        max_chars = rules["max_tokens"] * CHARS_PER_TOKEN
        sections: list[str] = []

        # 1. FILE itself (always included, highest priority)
        sections.append(f"=== FILE TO IMPLEMENT ===\n{file.read_text(encoding='utf-8')}")

        # 2. must_include — sibling files
        for pattern in rules.get("must_include", []):
            for sibling in file.parent.rglob(f"*{pattern}"):
                if sibling != file and sibling.exists():
                    sections.append(f"=== {sibling.name} ===\n{sibling.read_text(encoding='utf-8')}")
            if "schema.prisma" in pattern:
                for schema in file.parents[2].rglob("schema.prisma"):
                    sections.append(f"=== PRISMA SCHEMA ===\n{schema.read_text(encoding='utf-8')}")

        # 3. spec_include — relevant specs
        for spec_type in rules.get("spec_include", []):
            sections.append(self._get_spec_context(spec_type, service))

        # 4. Dependency exports
        for dep_name in service.service_dependencies:
            if dep_name in self.completed_services:
                sections.append(self._get_dependency_exports(dep_name))

        # 5. Token budget enforcement — prioritized truncation
        context = "\n\n".join(s for s in sections if s)
        if len(context) > max_chars:
            while len(context) > max_chars and len(sections) > 1:
                sections.pop()
                context = "\n\n".join(s for s in sections if s)
            if len(context) > max_chars:
                context = context[:max_chars] + "\n// CONTEXT_TRUNCATED"
            logger.warning("Context truncated for %s (exceeded %d tokens)", file.name, rules["max_tokens"])

        return context

    def _get_rules(self, file: Path) -> dict:
        for suffix, rules in CONTEXT_RULES.items():
            if file.name.endswith(suffix):
                return rules
        return {"must_include": [], "spec_include": [], "max_tokens": 4000}

    def _get_spec_context(self, spec_type: str, service: ParsedService) -> str:
        if spec_type == "user_stories":
            lines = [f"=== USER STORIES for {service.name} ==="]
            for story in service.stories[:20]:
                lines.append(f"\n{story.id}: {story.title}")
                for ac in story.acceptance_criteria[:5]:
                    lines.append(f"  AC: {ac}")
            return "\n".join(lines)
        elif spec_type == "state_machines":
            lines = [f"=== STATE MACHINES for {service.name} ==="]
            for sm in service.state_machines:
                lines.append(f"\n{sm.name}: states={sm.states}")
                for t in sm.transitions[:10]:
                    lines.append(f"  {t.from_state} -> {t.to_state} : {t.trigger}")
            return "\n".join(lines)
        elif spec_type == "endpoints":
            lines = [f"=== ENDPOINTS for {service.name} ==="]
            for ep in service.endpoints:
                codes = ", ".join(f"{k}:{v}" for k, v in list(ep.status_codes.items())[:3])
                lines.append(f"  {ep.method} {ep.path} [{codes}]")
            return "\n".join(lines)
        elif spec_type == "acceptance_criteria":
            lines = ["=== ACCEPTANCE CRITERIA ==="]
            for story in service.stories[:30]:
                for ac in story.acceptance_criteria:
                    lines.append(f"  {story.id}: {ac}")
            return "\n".join(lines)
        return ""

    def _get_dependency_exports(self, dep_name: str) -> str:
        dep_dir = self.completed_services.get(dep_name)
        if not dep_dir:
            return ""
        lines = [f"=== DEPENDENCY: {dep_name} (public API) ==="]
        for ts_file in dep_dir.rglob("*.service.ts"):
            content = ts_file.read_text(encoding="utf-8")
            for m in re.finditer(r"(async\s+\w+\([^)]*\)[^{]*)", content):
                lines.append(f"  {m.group(1).strip()}")
        return "\n".join(lines)

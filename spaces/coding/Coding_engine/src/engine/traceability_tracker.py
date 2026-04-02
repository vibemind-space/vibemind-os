"""Traceability Tracker — Prio 6 of Pipeline Improvements.

Tracks requirement-to-code mapping during generation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

from src.engine.spec_parser import ParsedSpec

logger = logging.getLogger(__name__)


@dataclass
class TraceEntry:
    requirement_id: str
    user_story_id: str
    epic: str
    endpoint: str
    service: str
    files: list[str] = field(default_factory=list)
    test_file: str = ""
    validation_score: float = 0.0
    status: str = "SKELETON"  # SKELETON | IMPLEMENTED | PARTIAL | MISSING


class TraceabilityTracker:
    def __init__(self):
        self._entries: list[TraceEntry] = []

    def register_from_spec(self, spec: ParsedSpec) -> None:
        for svc_name, svc in spec.services.items():
            for ep in svc.endpoints:
                for story_id in ep.linked_stories:
                    story = next((s for s in svc.stories if s.id == story_id), None)
                    req_ids = story.linked_requirements if story else []
                    for req_id in req_ids:
                        self._entries.append(TraceEntry(
                            requirement_id=req_id, user_story_id=story_id,
                            epic=story.epic if story else "",
                            endpoint=f"{ep.method} {ep.path}",
                            service=svc_name, status="SKELETON",
                        ))
            for story in svc.stories:
                if not any(e.user_story_id == story.id for e in self._entries):
                    for req_id in story.linked_requirements:
                        self._entries.append(TraceEntry(
                            requirement_id=req_id, user_story_id=story.id,
                            epic=story.epic, endpoint="", service=svc_name, status="SKELETON",
                        ))

    def update_status(self, req_id: str, service: str, status: str) -> None:
        for entry in self._entries:
            if entry.requirement_id == req_id and entry.service == service:
                entry.status = status

    def update_files(self, req_id: str, service: str, files: list[str]) -> None:
        for entry in self._entries:
            if entry.requirement_id == req_id and entry.service == service:
                entry.files = files

    def get_entries(self, service: str) -> list[TraceEntry]:
        return [e for e in self._entries if e.service == service]

    def get_all_entries(self) -> list[TraceEntry]:
        return self._entries

    def generate_report(self) -> dict:
        total = len(self._entries)
        by_status = {}
        for entry in self._entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
        return {
            "total_requirements": total,
            "by_status": by_status,
            "coverage": f"{by_status.get('IMPLEMENTED', 0)}/{total}",
        }

    def save_json(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"report": self.generate_report(), "entries": [asdict(e) for e in self._entries]}
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save_markdown(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report = self.generate_report()
        lines = [
            "# Traceability Matrix", "",
            f"**Coverage:** {report['coverage']}", "",
            "| Requirement | Story | Endpoint | Service | Status |",
            "|------------|-------|----------|---------|--------|",
        ]
        for entry in sorted(self._entries, key=lambda e: e.requirement_id):
            lines.append(f"| {entry.requirement_id} | {entry.user_story_id} | {entry.endpoint} | {entry.service} | {entry.status} |")
        output_path.write_text("\n".join(lines), encoding="utf-8")

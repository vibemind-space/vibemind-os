"""Canonical routing and safety contract for the Desktop space."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DesktopRoute:
    event_id: str
    space: str
    agent: str
    tool: str
    requires_confirmation: bool
    result_validation: str


class DesktopOrchestration:
    """Resolve Desktop-family events from the canonical space registry."""

    def __init__(self, registry_path: Path) -> None:
        data = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        desktop = (data.get("spaces") or {}).get("desktop") or {}
        self._agent = str(desktop.get("agent") or "")
        self._events: dict[str, dict[str, Any]] = desktop.get("events") or {}

    def resolve_event(self, event_id: str) -> DesktopRoute:
        contract = self._events.get(event_id)
        if not isinstance(contract, dict):
            raise KeyError(f"desktop event is not registered: {event_id}")
        return DesktopRoute(
            event_id=event_id,
            space="desktop",
            agent=self._agent,
            tool=str(contract.get("tool") or ""),
            requires_confirmation=bool(contract.get("requires_confirmation", False)),
            result_validation=str(contract.get("result_validation") or "external_receipt"),
        )

    def can_execute(self, event_id: str, *, confirmed: bool) -> bool:
        route = self.resolve_event(event_id)
        return confirmed or not route.requires_confirmation

    def resolve_capability(self, capability: str, intent: str) -> DesktopRoute:
        text = (intent or "").lower()
        if capability == "desktop_skill":
            event_id = "desktop.screenshot" if "screenshot" in text else "desktop.task"
        elif capability == "browser_automation":
            event_id = "openclaw.fill_form" if any(
                marker in text for marker in ("fill", "form", "formular", "login", "log in")
            ) else "openclaw.browse"
        else:
            raise KeyError(f"capability is not desktop-scoped: {capability}")
        return self.resolve_event(event_id)

    @classmethod
    def from_repository(cls) -> "DesktopOrchestration":
        root = Path(__file__).resolve().parents[3]
        return cls(root / "config" / "space_agent_registry.yml")

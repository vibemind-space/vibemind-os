"""
VibeMind Multiverse Spaces

Verschiedene Spaces im Multiverse:
- Ideas Space - Ideen-Verwaltung
- Coding Space - Code-Generierung
- Desktop Space - Desktop-Kontrolle via Automation_ui
- OpenClaw Space - AutoGen Desktop Swarm
- Transformer Space - Bubble-to-Coding Pipeline
- Roarboot Space - Rowboat Knowledge Graph
- Minibook Space - Inter-Space Collaboration
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class SpaceType(Enum):
    """Verfügbare Space-Typen im Multiverse."""
    IDEAS = "ideas"
    CODING = "coding"
    DESKTOP_SPACE = "desktop_space"
    OPENCLAW = "openclaw"
    TRANSFORMER = "transformer"
    ROWBOAT = "rowboat"
    SWE_DESIGN = "swe_design"
    MINIBOOK = "minibook"


@dataclass
class SpaceConfig:
    """Konfiguration für einen Multiverse-Space."""
    type: SpaceType
    name: str
    description: str
    position: Dict[str, float]  # x, y, z im 3D-Raum
    agent_slug: Optional[str] = None  # Zuständiger Agent
    color: int = 0x4488ff  # Hex-Farbe
    visualization: str = "bubble"  # bubble, planet, nebula, etc.
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# Space-Definitionen
SPACES = {
    SpaceType.IDEAS: SpaceConfig(
        type=SpaceType.IDEAS,
        name="Ideas Universe",
        description="Rachels Ideen-Bubbles - Sammlung und Organisation von Ideen",
        position={"x": 0, "y": 0, "z": 0},
        agent_slug="rachel",
        color=0x4488ff,
        visualization="bubbles",
        metadata={
            "entry_point": True,
            "allows_creation": True,
        }
    ),
    SpaceType.CODING: SpaceConfig(
        type=SpaceType.CODING,
        name="Coding Workshop",
        description="Code-Werkstatt - Code-Generierung und Projekte",
        position={"x": -8, "y": 2, "z": -3},
        agent_slug=None,
        color=0x44ff88,  # Grün
        visualization="nebula",
        metadata={
            "entry_point": False,
            "allows_creation": True,
        }
    ),
    SpaceType.DESKTOP_SPACE: SpaceConfig(
        type=SpaceType.DESKTOP_SPACE,
        name="Desktop Space",
        description="Desktop-Kontrolle via Automation_ui - System-Operationen und App-Steuerung",
        position={"x": 10, "y": 0, "z": -5},
        agent_slug=None,
        color=0xff8844,  # Warmes Orange
        visualization="light_planet",
        metadata={
            "entry_point": False,
            "requires_hand_motion": True,
            "planet_config": {
                "core_intensity": 1.0,
                "pulsation_speed": 0.5,
                "gravity_effect": True,
            }
        }
    ),
    SpaceType.OPENCLAW: SpaceConfig(
        type=SpaceType.OPENCLAW,
        name="OpenClaw Desktop",
        description="AutoGen Society of Mind - Desktop Swarm mit Claude CLI",
        position={"x": 12, "y": 3, "z": -8},
        agent_slug="openclaw",
        color=0xff4444,  # Rot
        visualization="planet",
        metadata={
            "entry_point": False,
            "uses_autogen": True,
            "uses_mcp": True,
        }
    ),
    SpaceType.TRANSFORMER: SpaceConfig(
        type=SpaceType.TRANSFORMER,
        name="Transformer Pipeline",
        description="Bubble-to-Coding Pipeline - Ideen zu Spezifikationen",
        position={"x": -4, "y": 4, "z": -6},
        agent_slug=None,
        color=0xaa44ff,  # Lila
        visualization="portal",
        metadata={
            "entry_point": False,
            "pipeline": True,
        }
    ),
    SpaceType.ROWBOAT: SpaceConfig(
        type=SpaceType.ROWBOAT,
        name="Rowboat",
        description="Rowboat Space - Knowledge Graph (Emails, Meetings, Wissen)",
        position={"x": -12, "y": -2, "z": -10},
        agent_slug="rowboat",
        color=0xffaa00,  # Gold
        visualization="nebula",
        metadata={
            "entry_point": True,
            "uses_docker": True,
            "rowboat_url": "http://localhost:3000",
        }
    ),
    SpaceType.SWE_DESIGN: SpaceConfig(
        type=SpaceType.SWE_DESIGN,
        name="SWE Design Factory",
        description="Software Engineering Design Factory - Shuttles land here for full spec generation",
        position={"x": 8, "y": 0, "z": 5.5},
        agent_slug=None,
        color=0xff6633,
        visualization="factory",
        metadata={
            "entry_point": False,
            "pipeline": True,
            "arch_team_url": "http://localhost:8087",
        }
    ),
    SpaceType.MINIBOOK: SpaceConfig(
        type=SpaceType.MINIBOOK,
        name="Minibook",
        description="Minibook Space - Inter-Space Collaboration (Multi-Agent Diskussionen)",
        position={"x": 6, "y": -3, "z": -12},
        agent_slug="minibook",
        color=0x00aaff,  # Hellblau
        visualization="nebula",
        metadata={
            "entry_point": False,
            "minibook_url": "http://localhost:3480",
        }
    ),
}


def get_space(space_type: SpaceType) -> Optional[SpaceConfig]:
    """Hole Space-Konfiguration nach Typ."""
    return SPACES.get(space_type)


def get_all_spaces():
    """Hole alle Space-Konfigurationen."""
    return list(SPACES.values())


def get_space_by_agent(agent_slug: str) -> Optional[SpaceConfig]:
    """Hole Space-Konfiguration nach zuständigem Agent."""
    for space in SPACES.values():
        if space.agent_slug == agent_slug:
            return space
    return None


__all__ = [
    "SpaceType",
    "SpaceConfig",
    "SPACES",
    "get_space",
    "get_all_spaces",
    "get_space_by_agent",
]
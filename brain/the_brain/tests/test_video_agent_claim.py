"""brain-video besitzt alle video.*-Events — Ownership bleibt vollstaendig.

AgentYamlRegistry-Invariante: pro Event genau EIN Agent. Ein doppelter
Claim ist ein Routing-Bug, der sich sonst erst zur Laufzeit zeigt.

Ruling R9 (Fix Round 1): pinnt Ownership statt nur Exklusivitaet fuer ein
einzelnes Event. Ein Event ohne besitzenden Agent ist kein neutraler
Zustand, sondern ein stiller Routing-Fehlschlag — get_event_agent()
liefert None, die Auflösung schlaegt fehl. Die Spec haelt u.a. lipsync
und vision ausdruecklich am Leben ("behalten"); wuerde brain-video sie
verlieren, waeren sie nicht mehr routbar. Das gestufte Rollout betrifft
nur die Tool-Bindungen in config/space_agent_registry.yml, nicht die
Event-Ownership hier.
"""
from core.agent_yaml_registry import AgentYamlRegistry

VIDEO_EVENTS = [
    "video.demo_analyze",
    "video.demo_build",
    "video.lipsync",
    "video.status",
    "video.team_run",
    "video.team_status",
    "video.vision",
    "video.voice_clone",
    "video.voice_tts",
]


def test_video_events_are_owned_by_brain_video():
    reg = AgentYamlRegistry()
    for event_id in VIDEO_EVENTS:
        assert reg.get_event_agent(event_id) == "brain-video", event_id


def test_registry_has_no_conflicts():
    reg = AgentYamlRegistry()
    assert reg.validate() == []

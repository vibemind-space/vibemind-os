"""Die video-Sektion muss echte Tools binden, keine db_*-Platzhalter."""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY = REPO_ROOT / "config" / "space_agent_registry.yml"


def _video_section():
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return data["spaces"]["video"]


def test_video_space_has_laura_scope():
    assert _video_section()["mcp_servers"] == ["laura", "vibemind-db"]


def test_video_status_binds_the_real_tool():
    events = _video_section()["events"]
    assert events["video.status"]["tool"] == "video_status"


def test_no_db_placeholders_left_on_wired_events():
    """db_query/db_update auf video.status war der Platzhalter-Zustand."""
    events = _video_section()["events"]
    assert not events["video.status"]["tool"].startswith("db_")

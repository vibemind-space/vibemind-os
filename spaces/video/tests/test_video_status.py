"""video_status meldet Laura + Sidecar ehrlich — auch wenn sie tot sind.

Ein toter Dienst ist ein BEFUND, kein Absturz und kein Timeout: die Spec
verlangt eine klare Meldung statt eines haengenden Events.
"""
import pytest

from spaces.video.tools import video_tools


class _FakeResponse:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_reports_both_services_up(monkeypatch):
    monkeypatch.setattr(video_tools, "urlopen", lambda url, timeout=2.0: _FakeResponse(200))
    result = video_tools.video_status()
    assert result["success"] is True
    assert result["laura"]["ok"] is True
    assert result["voiceover"]["ok"] is True


def test_down_service_is_a_finding_not_an_exception(monkeypatch):
    def _boom(url, timeout=2.0):
        raise OSError("connection refused")
    monkeypatch.setattr(video_tools, "urlopen", _boom)
    result = video_tools.video_status()
    assert result["success"] is True          # das Tool selbst funktioniert
    assert result["laura"]["ok"] is False     # der Dienst nicht
    assert "connection refused" in result["laura"]["error"]


def test_faceswap_is_reported(monkeypatch):
    """FaceSwap ist der Aufnahme-Pfad und muss sichtbar bleiben."""
    monkeypatch.setattr(video_tools, "urlopen", lambda url, timeout=2.0: _FakeResponse(200))
    assert "faceswap_installed" in video_tools.video_status()


def test_legacy_keys_remain_for_existing_uis(monkeypatch):
    """video-ui und agentfarm deklarieren diese als non-optional (types.ts:6-8 / :71-73).

    Die Spec sagt video_status ist 'behalten und erweitern' — dropping these
    would make both UIs silently render 'nothing installed'.
    """
    monkeypatch.setattr(video_tools, "urlopen", lambda url, timeout=2.0: _FakeResponse(200))
    result = video_tools.video_status()
    assert isinstance(result["vibevideo_installed"], bool)
    assert isinstance(result["deepfake_installed"], bool)
    assert isinstance(result["available_tools"], list)

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from brain.the_brain.core.capability_executor import DirectExecutor
from spaces.video import execution_target


def _wait_for_terminal(job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = execution_target.execute_video({"event_type": "video.status", "job_id": job_id})
        if result["status"] in {"completed", "failed"}:
            return result
        time.sleep(0.01)
    raise AssertionError(f"video job {job_id} did not finish")


@pytest.fixture(autouse=True)
def isolated_job_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIBEMIND_VIDEO_JOB_DIR", str(tmp_path / "jobs"))


def test_video_capabilities_route_to_the_real_space_target() -> None:
    registry_path = Path(__file__).parents[1] / "data" / "capabilities.yaml"
    capabilities = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    by_name = {entry["capability"]: entry for entry in capabilities}

    expected = {
        "video_status",
        "video_team_status",
        "video_team_run",
        "video_vision",
        "video_demo_build",
        "video_lipsync",
        "video_voice_clone",
        "video_voice_tts",
    }
    assert expected <= by_name.keys()
    assert {
        by_name[name]["execution_target"] for name in expected
    } == {"direct:spaces.video.execution_target:execute_video"}


def test_media_job_returns_id_and_completes_only_with_existing_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "render.mp4"
    artifact.write_bytes(b"video")
    monkeypatch.setattr(
        execution_target,
        "_resolve_tool",
        lambda _event_type: lambda **_params: {
            "success": True,
            "output_path": str(artifact),
        },
    )

    accepted = execution_target.execute_video(
        {"event_type": "video.demo_build", "description": "Brain demo"}
    )

    assert accepted["success"] is True
    assert accepted["status"] == "accepted"
    assert accepted["job_id"].startswith("video-")
    result = _wait_for_terminal(accepted["job_id"])
    assert result["status"] == "completed"
    assert result["artifacts"] == [{"path": str(artifact.resolve()), "exists": True}]
    assert result["media_paths"] == [str(artifact.resolve())]


def test_provider_failure_is_persisted_as_failed_without_artifact_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        execution_target,
        "_resolve_tool",
        lambda _event_type: lambda **_params: {
            "success": False,
            "message": "provider unavailable",
        },
    )

    accepted = execution_target.execute_video(
        {"event_type": "video.voice_tts", "text": "Hallo"}
    )
    result = _wait_for_terminal(accepted["job_id"])

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error"] == "provider unavailable"
    assert result["artifacts"] == []
    assert result["media_paths"] == []


def test_media_job_fails_closed_when_tool_claims_success_without_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        execution_target,
        "_resolve_tool",
        lambda _event_type: lambda **_params: {"success": True, "message": "done"},
    )

    accepted = execution_target.execute_video(
        {"event_type": "video.lipsync", "video": "input.mp4", "audio": "voice.wav"}
    )
    result = _wait_for_terminal(accepted["job_id"])

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error"] == "provider returned no existing artifact evidence"


def test_media_job_detects_artifact_written_by_legacy_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "legacy-output"
    output_dir.mkdir()

    def tool(**_params: object) -> dict:
        (output_dir / "generated.mp4").write_bytes(b"video")
        return {"success": True, "message": "done"}

    monkeypatch.setattr(execution_target, "_artifact_roots", lambda: (output_dir,))
    monkeypatch.setattr(execution_target, "_resolve_tool", lambda _event_type: tool)

    accepted = execution_target.execute_video(
        {"event_type": "video.vision", "url": "https://example.invalid/reference"}
    )
    result = _wait_for_terminal(accepted["job_id"])

    assert result["status"] == "completed"
    assert result["media_paths"] == [str((output_dir / "generated.mp4").resolve())]


def test_missing_required_parameter_fails_before_job_acceptance() -> None:
    with pytest.raises(ValueError, match="video.voice_clone requires: audio"):
        execution_target.execute_video({"event_type": "video.voice_clone"})


def test_unknown_job_status_fails_closed() -> None:
    with pytest.raises(LookupError, match="video job not found"):
        execution_target.execute_video({"event_type": "video.status", "job_id": "video-missing"})


def test_provider_status_fails_closed_when_video_clis_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        execution_target,
        "_resolve_tool",
        lambda _event_type: lambda: {
            "success": True,
            "vibevideo_installed": False,
            "deepfake_installed": False,
        },
    )

    with pytest.raises(RuntimeError, match="video providers unavailable"):
        execution_target.execute_video({"event_type": "video.status"})


def test_brain_direct_executor_forwards_plan_payload_to_video_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "voice.wav"
    artifact.write_bytes(b"audio")
    received = {}

    def tool(**params: object) -> dict:
        received.update(params)
        return {"success": True, "output_path": str(artifact)}

    monkeypatch.setattr(execution_target, "_resolve_tool", lambda _event_type: tool)
    executor = DirectExecutor("direct:spaces.video.execution_target:execute_video")

    response = executor.call_with_arg(
        {"text": "Hallo aus dem Brain"},
        extra_params={"_capability": "video_voice_tts"},
    )

    assert response["ok"] is True
    accepted = response["result"]
    assert accepted["status"] == "accepted"
    assert _wait_for_terminal(accepted["job_id"])["status"] == "completed"
    assert received["text"] == "Hallo aus dem Brain"

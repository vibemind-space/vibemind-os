"""
Video Production Tools — Wraps vibevideo + vibevideo-deepfake CLIs.

Provides tool functions for the VideoBackendAgent to call via event routing.
Each tool delegates to the underlying CLI scripts in the submodules.
"""

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VIBEVIDEO_DIR = Path(__file__).parent.parent / "vibevideo"
DEEPFAKE_DIR = Path(__file__).parent.parent / "vibevideo_deepfake"


def _run_cli(script: Path, args: List[str], cwd: Path = None) -> Dict[str, Any]:
    """Run a CLI script and return structured result."""
    if not script.exists():
        return {"success": False, "message": f"Script not found: {script}"}

    cmd = [sys.executable, str(script)] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd or script.parent),
            capture_output=True,
            text=True,
            timeout=600,
        )
        return {
            "success": result.returncode == 0,
            "message": result.stdout.strip() if result.returncode == 0 else result.stderr.strip(),
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Command timed out (600s)"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Team Video Pipeline ──────────────────────────────────────

def team_pipeline_status() -> Dict[str, Any]:
    """Get status of the team video pipeline (available steps, outputs)."""
    steps = ["analyze", "backgrounds", "composite", "build", "split", "final"]
    available = VIBEVIDEO_DIR.exists()
    return {
        "success": True,
        "message": "Team video pipeline status",
        "available": available,
        "steps": steps,
        "vibevideo_path": str(VIBEVIDEO_DIR),
    }


def team_run_step(step: str = "all", **kwargs) -> Dict[str, Any]:
    """Run a team video pipeline step."""
    valid = ["analyze", "backgrounds", "composite", "build", "split", "final", "all"]
    if step not in valid:
        return {"success": False, "message": f"Invalid step '{step}'. Valid: {valid}"}
    return _run_cli(VIBEVIDEO_DIR / "vibevideo.py", ["team", step], cwd=VIBEVIDEO_DIR)


# ── Vision Video (Sora AI) ───────────────────────────────────

def vision_generate(**kwargs) -> Dict[str, Any]:
    """Generate a Her-style vision video with Sora AI scenes."""
    args = ["vision", "--all"]
    if kwargs.get("generate_sora"):
        args = ["vision", "--generate-sora"]
    elif kwargs.get("generate_tts"):
        args = ["vision", "--generate-tts"]
    elif kwargs.get("build_only"):
        args = ["vision", "--build"]
    return _run_cli(VIBEVIDEO_DIR / "vibevideo.py", args, cwd=VIBEVIDEO_DIR)


# ── Product Demo ─────────────────────────────────────────────

def demo_analyze(input_file: str, target_duration: int = 60, **kwargs) -> Dict[str, Any]:
    """Analyze a screenrecording for demo video production."""
    args = ["demo", "analyze", input_file, "--target", str(target_duration)]
    return _run_cli(VIBEVIDEO_DIR / "vibevideo.py", args, cwd=VIBEVIDEO_DIR)


def demo_build(config_path: str, **kwargs) -> Dict[str, Any]:
    """Build a demo video from a scene config."""
    args = ["demo", "build", "-c", config_path]
    return _run_cli(VIBEVIDEO_DIR / "vibevideo.py", args, cwd=VIBEVIDEO_DIR)


# ── Lip Sync (Deepfake) ──────────────────────────────────────

def lipsync_run(person: str = None, **kwargs) -> Dict[str, Any]:
    """Run MuseTalk lip sync on team videos."""
    args = ["lipsync", "run"]
    if person:
        args += ["--only", person]
    return _run_cli(DEEPFAKE_DIR / "deepfake.py", args, cwd=DEEPFAKE_DIR)


def lipsync_analyze(**kwargs) -> Dict[str, Any]:
    """Run quality analysis on lip sync results."""
    return _run_cli(DEEPFAKE_DIR / "deepfake.py", ["lipsync", "analyze"], cwd=DEEPFAKE_DIR)


# ── Voice Cloning ────────────────────────────────────────────

def voice_clone(**kwargs) -> Dict[str, Any]:
    """Extract reference audio for Chatterbox voice cloning (local)."""
    return _run_cli(DEEPFAKE_DIR / "deepfake.py", ["voice", "clone"], cwd=DEEPFAKE_DIR)


def voice_tts(person: str = None, **kwargs) -> Dict[str, Any]:
    """Generate TTS voiceover per person."""
    args = ["voice", "tts"]
    if person:
        args += ["--only", person]
    return _run_cli(DEEPFAKE_DIR / "deepfake.py", args, cwd=DEEPFAKE_DIR)


# ── Status / Info ────────────────────────────────────────────

def video_status(**kwargs) -> Dict[str, Any]:
    """Get overall video space status (installed tools, submodules)."""
    vibevideo_ok = (VIBEVIDEO_DIR / "vibevideo.py").exists()
    deepfake_ok = (DEEPFAKE_DIR / "deepfake.py").exists()

    tools = []
    if vibevideo_ok:
        tools.extend(["team", "vision", "demo"])
    if deepfake_ok:
        tools.extend(["lipsync", "voice"])

    return {
        "success": True,
        "message": f"Video space: {len(tools)} tools available",
        "vibevideo_installed": vibevideo_ok,
        "deepfake_installed": deepfake_ok,
        "available_tools": tools,
    }


# ── Video Gallery (scan outputs) ────────────────────────────

def _categorize_root(filepath: Path) -> str:
    """Categorize root-level vibevideo mp4 files by name."""
    name = filepath.stem.lower()
    if "team" in name:
        return "Team"
    if "product" in name:
        return "Product"
    if "final" in name:
        return "Final"
    if "application" in name:
        return "Application"
    if "vision" in name:
        return "Vision"
    return "Other"


def _human_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def scan_video_outputs(**kwargs) -> Dict[str, Any]:
    """Return videos from database. Falls back to filesystem scan if DB is empty."""
    try:
        from data.video_repository import VideoRepository
        repo = VideoRepository()
        count = repo.count()
        if count > 0:
            videos = repo.to_gallery_format()
            return {
                "success": True,
                "message": f"Found {len(videos)} video(s)",
                "videos": videos,
            }
    except Exception as e:
        logger.warning("VideoRepository unavailable, falling back to filesystem scan: %s", e)

    # Filesystem fallback (legacy behavior)
    videos: List[Dict[str, Any]] = []

    scan_dirs: List[tuple] = []

    if VIBEVIDEO_DIR.exists():
        scan_dirs.extend([
            (VIBEVIDEO_DIR, _categorize_root),
            (VIBEVIDEO_DIR / "lip_sync", lambda _f: "Lipsync"),
            (VIBEVIDEO_DIR / "composited", lambda _f: "Composited"),
            (VIBEVIDEO_DIR / "backgrounds", lambda _f: "Background"),
            (VIBEVIDEO_DIR / "vision", lambda _f: "Vision"),
            (VIBEVIDEO_DIR / "output", lambda _f: "Output"),
        ])

    if DEEPFAKE_DIR.exists():
        scan_dirs.extend([
            (DEEPFAKE_DIR / "lip_sync", lambda _f: "Deepfake Lipsync"),
        ])

    for directory, categorizer in scan_dirs:
        if not directory.exists():
            continue
        for mp4 in directory.glob("*.mp4"):
            if not mp4.is_file():
                continue
            stat = mp4.stat()
            videos.append({
                "path": str(mp4.resolve()),
                "filename": mp4.name,
                "size_bytes": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "category": categorizer(mp4),
                "modified": stat.st_mtime,
                "modified_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    videos.sort(key=lambda v: v["modified"], reverse=True)

    return {
        "success": True,
        "message": f"Found {len(videos)} video(s)",
        "videos": videos,
    }


def import_videos(source_dir: str = None, **kwargs) -> Dict[str, Any]:
    """Import videos from an external directory into the database."""
    try:
        from data.video_repository import VideoRepository
        repo = VideoRepository()
        if not source_dir:
            return {"success": False, "message": "source_dir is required"}
        return repo.import_directory(source_dir)
    except Exception as e:
        return {"success": False, "message": f"Import failed: {e}"}


# ── Video Projects ──────────────────────────────────────────

def create_video_project(name: str, description: str = "", **kwargs) -> Dict[str, Any]:
    """Create a new video production project."""
    try:
        from data.video_project_repository import VideoProjectRepository
        repo = VideoProjectRepository()
        return {"success": True, **repo.create_project(name, description)}
    except Exception as e:
        return {"success": False, "message": str(e)}


def add_project_person(
    project_id: str, name: str, role: str = "", raw_video_path: str = "", **kwargs
) -> Dict[str, Any]:
    """Add a person to a video project."""
    try:
        from data.video_project_repository import VideoProjectRepository
        repo = VideoProjectRepository()
        person = repo.add_person(project_id, name, role, raw_video_path)
        return {"success": True, **person}
    except Exception as e:
        return {"success": False, "message": str(e)}


def list_video_projects(**kwargs) -> Dict[str, Any]:
    """List all video projects."""
    try:
        from data.video_project_repository import VideoProjectRepository
        repo = VideoProjectRepository()
        projects = repo.list_projects()
        return {"success": True, "projects": projects}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_project_pipeline(project_id: str, **kwargs) -> Dict[str, Any]:
    """Get pipeline matrix for a project."""
    try:
        from data.video_project_repository import VideoProjectRepository
        repo = VideoProjectRepository()
        matrix = repo.get_pipeline_matrix(project_id)
        return {"success": True, **matrix}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_reference_pipeline(**kwargs) -> Dict[str, Any]:
    """Get Surya's reference pipeline for the UI."""
    try:
        from data.video_project_repository import VideoProjectRepository
        repo = VideoProjectRepository()
        ref = repo.get_reference_pipeline("Surya")
        return {"success": True, **ref}
    except Exception as e:
        return {"success": False, "message": str(e)}


def run_pipeline_step(
    project_id: str, person_name: str, step_name: str, **kwargs
) -> Dict[str, Any]:
    """Run a specific pipeline step for a person in a project."""
    try:
        from data.video_project_repository import VideoProjectRepository
        proj_repo = VideoProjectRepository()

        project = proj_repo.get_project(project_id)
        if not project:
            return {"success": False, "message": f"Project {project_id} not found"}

        # Find person
        person = None
        for p in project["persons"]:
            if p["name"] == person_name:
                person = p
                break
        if not person:
            return {"success": False, "message": f"Person {person_name} not found in project"}

        # Mark step as running
        proj_repo.update_step(project_id, person_name, step_name, "running")

        # Execute the appropriate CLI command
        result = _execute_pipeline_step(step_name, person_name, person)

        if result["success"]:
            output_path = result.get("output_path", "")
            proj_repo.update_step(
                project_id, person_name, step_name, "completed",
                output_path=output_path,
            )
        else:
            proj_repo.update_step(
                project_id, person_name, step_name, "failed",
                error_message=result.get("message", "Unknown error"),
            )

        return result
    except Exception as e:
        return {"success": False, "message": str(e)}


def _execute_pipeline_step(
    step_name: str, person_name: str, person: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a single pipeline step via CLI."""
    if step_name == "analyze":
        return _run_cli(
            VIBEVIDEO_DIR / "vibevideo.py",
            ["team", "analyze"],
            cwd=VIBEVIDEO_DIR,
        )

    elif step_name == "voice_clone":
        return _run_cli(
            DEEPFAKE_DIR / "deepfake.py",
            ["voice", "clone", "--only", person_name],
            cwd=DEEPFAKE_DIR,
        )

    elif step_name == "transcript":
        return _run_cli(
            DEEPFAKE_DIR / "deepfake.py",
            ["voice", "transcripts", "--only", person_name],
            cwd=DEEPFAKE_DIR,
        )

    elif step_name == "tts":
        return _run_cli(
            DEEPFAKE_DIR / "deepfake.py",
            ["voice", "tts", "--only", person_name],
            cwd=DEEPFAKE_DIR,
        )

    elif step_name == "lipsync":
        return _run_cli(
            DEEPFAKE_DIR / "deepfake.py",
            ["lipsync", "run", "--only", person_name],
            cwd=DEEPFAKE_DIR,
        )

    elif step_name == "background":
        return _run_cli(
            VIBEVIDEO_DIR / "vibevideo.py",
            ["team", "backgrounds", "--only", person_name],
            cwd=VIBEVIDEO_DIR,
        )

    elif step_name == "composite":
        return _run_cli(
            VIBEVIDEO_DIR / "vibevideo.py",
            ["team", "composite"],
            cwd=VIBEVIDEO_DIR,
        )

    elif step_name == "build":
        return _run_cli(
            VIBEVIDEO_DIR / "vibevideo.py",
            ["team", "build"],
            cwd=VIBEVIDEO_DIR,
        )

    elif step_name == "final":
        return _run_cli(
            VIBEVIDEO_DIR / "vibevideo.py",
            ["team", "final"],
            cwd=VIBEVIDEO_DIR,
        )

    else:
        return {"success": False, "message": f"Unknown step: {step_name}"}


# ── Rowboat Publishing ──────────────────────────────────────

def _build_video_note(v: Dict[str, Any]) -> str:
    """Build markdown note for a single video."""
    lines = [
        f"# {v['title'] or v['filename']}",
        "",
        f"**Datei:** {v['filename']}",
        f"**Pfad:** {v['file_path']}",
        f"**Person:** {v['person'] or 'n/a'}",
        f"**Kategorie:** {v['category']}",
        f"**Pipeline-Stage:** {v['pipeline_stage']}",
        f"**Groesse:** {v['size_bytes'] / 1e6:.1f} MB",
    ]
    if v.get("notes"):
        lines += ["", f"**Notizen:** {v['notes']}"]
    return "\n".join(lines)


def _publish_videos_filesystem(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fallback: write video metadata as Markdown to ~/.rowboat/vibemind/videos/."""
    out_dir = Path.home() / ".rowboat" / "vibemind" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    for v in videos:
        stem = v["filename"].replace(" ", "_").rsplit(".", 1)[0]
        stage = v.get("pipeline_stage", "other")
        slug = f"{stage}--{stem}"
        (out_dir / f"{slug}.md").write_text(_build_video_note(v), encoding="utf-8")
    return {
        "success": True,
        "message": f"{len(videos)} Videos als Markdown exportiert nach {out_dir}",
    }


def publish_videos_to_rowboat(**kwargs) -> Dict[str, Any]:
    """Publish all videos from DB to Rowboat as a knowledge source."""
    try:
        from data.video_repository import VideoRepository

        repo = VideoRepository()
        videos = repo.list_all(limit=500)
        if not videos:
            return {"success": False, "message": "Keine Videos in der DB"}

        # Try MongoDB publisher
        try:
            from publishing import _try_create_mongo_publisher
            publisher = _try_create_mongo_publisher()
        except Exception:
            publisher = None

        if publisher:
            source_id = publisher._create_source(
                name="Video Production Pipeline",
                description=f"{len(videos)} Videos aus Team-Produktion",
            )

            notes = []
            for v in videos:
                tags = [v["category"], v["pipeline_stage"]]
                if v.get("person"):
                    tags.append(v["person"])
                notes.append({
                    "title": v["title"] or v["filename"],
                    "content": _build_video_note(v),
                    "tags": tags,
                    "node_type": "video",
                })

            publisher._insert_docs(source_id, notes)
            return {
                "success": True,
                "message": f"{len(notes)} Videos zu Rowboat publiziert (MongoDB)",
                "source_id": source_id,
            }
        else:
            # Filesystem fallback
            return _publish_videos_filesystem(videos)

    except Exception as e:
        return {"success": False, "message": f"Publish failed: {e}"}

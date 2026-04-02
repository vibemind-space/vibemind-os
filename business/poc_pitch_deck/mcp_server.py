"""
Pitch Deck MCP Server
======================
Complete pitch deck generation, data crawling, and iteration via MCP tools.

Tools:
  - generate_deck: Generate interactive HTML pitch deck
  - crawl_data: Crawl codebase + PDFs + website for context data
  - crawl_spaces: Deep-crawl detailed Space descriptions
  - update_slide: Modify a specific slide with feedback
  - list_slides: Show current slide titles and types
  - set_company_info: Update company metadata (team, URL, slogan)
  - deploy_deck: Prepare deck for deployment (zip or folder)

Start:
  python mcp_server.py              # stdio mode (for Claude Code)
  python mcp_server.py --sse 8852   # SSE mode (for browser)
"""

import json
import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Pitch Deck Generator",
    instructions=(
        "Interactive pitch deck generation with AI agents. "
        "Use 'generate_deck' to create a full deck, 'crawl_data' to update context from codebase, "
        "'update_slide' to fix individual slides, 'list_slides' to see current deck structure, "
        "'set_company_info' to update team/URL/slogan."
    ),
)

PROJECT_ROOT = Path(__file__).parent.parent
DECK_CONTEXT = PROJECT_ROOT / "deck_context.json"
LAST_DECK = PROJECT_ROOT / ".last_deck.json"


def _load_context():
    if DECK_CONTEXT.exists():
        return json.loads(DECK_CONTEXT.read_text(encoding="utf-8"))
    return None


def _save_last_deck(deck_path, slides_data):
    LAST_DECK.write_text(json.dumps({
        "path": str(deck_path),
        "slides": slides_data,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_last_deck():
    if LAST_DECK.exists():
        return json.loads(LAST_DECK.read_text(encoding="utf-8"))
    return None


@mcp.tool()
async def generate_deck(
    company: str = "VibeMind",
    description: str = "Voice-first AI workspace - Speak ideas into existence",
    theme: str = "auto",
    images: bool = True,
):
    """
    Generate a complete interactive pitch deck with Three.js, GSAP animations,
    video backgrounds, and SDXL-generated images.

    Args:
        company: Company name
        description: Short company description
        theme: Color theme (auto, midnight, emerald, crimson, arctic, obsidian, sunset)
        images: Generate SDXL background images for intro/CTA
    """
    args = [sys.executable, str(PROJECT_ROOT / "pitch_deck_agent.py"), company, description]
    if theme != "auto":
        args.append(f"--theme={theme}")
    if images:
        args.append("--images")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(args, capture_output=True, text=True, timeout=600, cwd=str(PROJECT_ROOT), env=env)

    # Find the generated HTML file
    output = result.stdout + result.stderr
    html_file = None
    for line in output.split("\n"):
        if "HTML:" in line:
            html_file = line.split("HTML:")[-1].strip()
        if "Slides:" in line:
            slides_count = line.split(":")[-1].strip()

    if html_file:
        return json.dumps({
            "status": "success",
            "file": html_file,
            "slides": slides_count if 'slides_count' in dir() else "?",
            "message": f"Deck generated: {html_file}",
            "open_url": f"file:///{(PROJECT_ROOT / html_file).resolve()}",
        }, indent=2)
    else:
        return json.dumps({
            "status": "error",
            "stdout": output[-500:],
            "stderr": result.stderr[-500:] if result.stderr else "",
        }, indent=2)


@mcp.tool()
async def crawl_data(force: bool = False):
    """
    Crawl the codebase via Fungus search index, PitchdeckData PDFs,
    website FAQ, and investor one-pager. Updates deck_context.json.

    Args:
        force: Force re-crawl even if deck_context.json exists
    """
    if DECK_CONTEXT.exists() and not force:
        ctx = _load_context()
        return json.dumps({
            "status": "exists",
            "chunks": ctx["summary"]["total_chunks"],
            "categories": ctx["summary"]["categories"],
            "message": "deck_context.json already exists. Use force=True to re-crawl.",
        }, indent=2)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "crawl_for_deck.py")],
        capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT), env=env,
    )

    ctx = _load_context()
    if ctx:
        return json.dumps({
            "status": "success",
            "chunks": ctx["summary"]["total_chunks"],
            "categories": ctx["summary"]["categories"],
            "message": "Crawl complete. deck_context.json updated.",
        }, indent=2)
    else:
        return json.dumps({"status": "error", "output": result.stdout[-500:]}, indent=2)


@mcp.tool()
async def crawl_spaces():
    """
    Deep-crawl detailed descriptions for each of the 12 VibeMind Spaces
    from the Fungus search index. Adds space_details category to deck_context.json.
    """
    crawl_script = PROJECT_ROOT / "crawl_spaces.py"
    if not crawl_script.exists():
        return json.dumps({"status": "error", "message": "crawl_spaces.py not found"})

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(crawl_script)],
        capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT), env=env,
    )

    ctx = _load_context()
    space_count = len(ctx.get("categories", {}).get("space_details", []))
    return json.dumps({
        "status": "success",
        "spaces": space_count,
        "message": f"Deep-crawled {space_count} space descriptions.",
    }, indent=2)


@mcp.tool()
async def list_slides():
    """
    List all slides in the most recently generated deck with their
    titles, types, layouts, and whether they have videos/screenshots.
    """
    last = _load_last_deck()
    if not last:
        # Parse from HTML
        import glob
        htmls = sorted(glob.glob(str(PROJECT_ROOT / "vibemind_deck_*.html")), reverse=True)
        if not htmls:
            return json.dumps({"status": "error", "message": "No deck found. Run generate_deck first."})
        return json.dumps({
            "status": "info",
            "latest_file": Path(htmls[0]).name,
            "message": "Deck found but no slide data cached. Regenerate to get details.",
        }, indent=2)

    slides = []
    for s in last.get("slides", []):
        slides.append({
            "index": s.get("idx"),
            "type": s.get("type"),
            "title": s.get("title", "")[:60],
            "layout": s.get("layout", "bullets"),
            "has_video": bool(s.get("video")),
            "has_screenshot": bool(s.get("screenshot")),
            "has_chart": bool(s.get("chart")),
            "bullets": len(s.get("bullets", [])),
        })

    return json.dumps({
        "status": "success",
        "file": last.get("path"),
        "total_slides": len(slides),
        "slides": slides,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def update_slide(slide_index: int, feedback: str):
    """
    Update a specific slide based on feedback. Uses LLM to modify
    only the affected slide, then regenerates the deck.

    Args:
        slide_index: Which slide to update (0-based index)
        feedback: What to change (e.g. "make bullets more specific", "add revenue numbers")
    """
    last = _load_last_deck()
    if not last:
        return json.dumps({"status": "error", "message": "No deck found. Run generate_deck first."})

    slides = last.get("slides", [])
    if slide_index < 0 or slide_index >= len(slides):
        return json.dumps({"status": "error", "message": f"Invalid index. Deck has {len(slides)} slides (0-{len(slides)-1})."})

    target = slides[slide_index]
    from llm_client import get_client_sync, get_model
    client = get_client_sync("default", "pitch_deck_agent")
    model = get_model("default", "pitch_deck_agent")

    prompt = f"""You are editing a pitch deck slide. Here is the current slide:
Title: {target.get('title')}
Subtitle: {target.get('subtitle')}
Type: {target.get('type')}
Bullets: {json.dumps(target.get('bullets', []))}

User feedback: "{feedback}"

Return ONLY valid JSON with the updated slide fields (title, subtitle, bullets). Keep the same structure.
Only change what the feedback asks for. Keep everything else identical."""

    try:
        from pitch_deck_agent import _safe_content, _parse_json_response
        resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        data = _parse_json_response(_safe_content(resp))
        if data:
            for key in ["title", "subtitle", "bullets"]:
                if key in data:
                    slides[slide_index][key] = data[key]
            _save_last_deck(last["path"], slides)
            return json.dumps({
                "status": "success",
                "slide_index": slide_index,
                "updated_fields": list(data.keys()),
                "message": f"Slide {slide_index} updated. Run generate_deck to rebuild.",
            }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)[:200]})

    return json.dumps({"status": "error", "message": "LLM returned empty response"})


@mcp.tool()
async def set_company_info(
    website: str = "",
    slogan: str = "",
    team_member: str = "",
    team_role: str = "",
):
    """
    Update company metadata used in deck generation.
    Changes are applied to the pitch_deck_agent.py prompts.

    Args:
        website: Company website URL (e.g. vibemind.space)
        slogan: Company slogan/tagline
        team_member: Add or update a team member name
        team_role: Role for the team member
    """
    changes = []
    if website:
        changes.append(f"Website: {website}")
    if slogan:
        changes.append(f"Slogan: {slogan}")
    if team_member and team_role:
        changes.append(f"Team: {team_member} — {team_role}")

    return json.dumps({
        "status": "info",
        "changes_requested": changes,
        "message": "To apply these changes, edit pitch_deck_agent.py prompts or deck_context.json directly.",
    }, indent=2)


@mcp.tool()
async def deploy_deck(target: str = "folder"):
    """
    Prepare the latest deck for deployment/sharing.

    Args:
        target: Deployment target - 'folder' (copy all files to deploy/), 'info' (show what's needed)
    """
    import glob
    htmls = sorted(glob.glob(str(PROJECT_ROOT / "vibemind_deck_*.html")), reverse=True)
    if not htmls:
        return json.dumps({"status": "error", "message": "No deck found."})

    latest = Path(htmls[0])
    deploy_dir = PROJECT_ROOT / "deploy_deck"
    deploy_dir.mkdir(exist_ok=True)

    # Copy HTML
    import shutil
    shutil.copy(latest, deploy_dir / "index.html")

    # Copy media
    ss_dir = deploy_dir / "deck_screenshots"
    ss_dir.mkdir(exist_ok=True)
    for f in (PROJECT_ROOT / "deck_screenshots").glob("*"):
        if f.suffix in (".mp4", ".png", ".jpg", ".gif"):
            shutil.copy(f, ss_dir / f.name)

    charts_dir = deploy_dir / "deck_charts"
    charts_dir.mkdir(exist_ok=True)
    for f in (PROJECT_ROOT / "deck_charts").glob("*.png"):
        shutil.copy(f, charts_dir / f.name)

    # Count files
    total_files = sum(1 for _ in deploy_dir.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in deploy_dir.rglob("*") if f.is_file())

    return json.dumps({
        "status": "success",
        "deploy_dir": str(deploy_dir),
        "files": total_files,
        "size_mb": round(total_size / 1024 / 1024, 1),
        "message": f"Deploy folder ready: {deploy_dir}\n"
                   f"Upload this folder to vibemind.space/pitch or any static host.\n"
                   f"The index.html references deck_screenshots/ and deck_charts/ relatively.",
    }, indent=2)


@mcp.tool()
async def get_context_stats():
    """
    Show statistics about the current deck_context.json data source.
    """
    ctx = _load_context()
    if not ctx:
        return json.dumps({"status": "error", "message": "No deck_context.json. Run crawl_data first."})

    stats = {}
    for cat, chunks in ctx.get("categories", {}).items():
        total_chars = sum(len(c["content"]) for c in chunks)
        avg_score = sum(c["score"] for c in chunks) / len(chunks) if chunks else 0
        stats[cat] = {
            "chunks": len(chunks),
            "total_chars": total_chars,
            "avg_score": round(avg_score, 3),
        }

    return json.dumps({
        "status": "success",
        "source": ctx.get("crawl_source", "unknown"),
        "total_chunks": ctx["summary"]["total_chunks"],
        "categories": stats,
    }, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sse", type=int, help="Run in SSE mode on given port")
    args = parser.parse_args()

    if args.sse:
        from mcp.server.fastmcp import create_sse_app
        import uvicorn
        app = create_sse_app(mcp)
        print(f"Pitch Deck MCP Server running on http://localhost:{args.sse}")
        uvicorn.run(app, host="0.0.0.0", port=args.sse)
    else:
        mcp.run(transport="stdio")

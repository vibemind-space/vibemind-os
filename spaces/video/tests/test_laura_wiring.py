"""Laura-Anbindung: Submodul-Pin und MCP-Entry-Point.

Billige Struktur-Tests, die Drift fangen: wandert der Pin oder verschwindet
der Entry-Point, laeuft der MCP-Server nicht mehr an und die 28 Tools sind weg.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LAURA_DIR = REPO_ROOT / "spaces" / "video" / "laura"
EXPECTED_LAURA_PIN = "909a43d499ffe00f4fd3d779127da45debf64f0c"


def test_gitmodules_declares_laura():
    text = (REPO_ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert 'path = spaces/video/laura' in text
    assert "Lauras_star" in text


def test_laura_mcp_entrypoint_declared():
    pyproject = LAURA_DIR / "services" / "mcp" / "pyproject.toml"
    assert pyproject.exists(), f"Laura-Submodul nicht ausgecheckt: {pyproject}"
    text = pyproject.read_text(encoding="utf-8")
    assert 'laura-mcp = "laura_mcp.server:main"' in text


def test_laura_gitlink_pin_is_expected_sha():
    """Ein wandernder Pin ist der stille Bruch: er entfernt build_narrated_reel,
    ohne dass irgendetwas laut schreit.

    Der Pin wird aus git gelesen (ls-tree HEAD), nicht aus dem Working Tree
    im Dateisystem — ein zufaellig falsch ausgecheckter Submodul-Stand soll
    diesen Test nicht faelschlich gruen erscheinen lassen.
    """
    try:
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "spaces/video/laura"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git ist auf diesem System nicht verfuegbar")

    if result.returncode != 0:
        pytest.skip(f"git ls-tree fehlgeschlagen: {result.stderr.strip()}")

    output = result.stdout.strip()
    assert output, "git ls-tree HEAD spaces/video/laura lieferte keine Ausgabe (Gitlink fehlt?)"

    # Format: "<mode> commit <sha>\t<path>"
    parts = output.split()
    assert len(parts) >= 3, f"unerwartetes ls-tree-Format: {output!r}"
    mode, obj_type, sha = parts[0], parts[1], parts[2]
    assert obj_type == "commit", f"spaces/video/laura ist kein Gitlink (type={obj_type})"
    assert sha == EXPECTED_LAURA_PIN, (
        f"Laura-Pin ist gewandert: {sha} statt {EXPECTED_LAURA_PIN}"
    )


def test_openfang_template_declares_laura_mcp():
    """Die versionierte Vorlage muss den laura-Eintrag tragen.

    Wirksam ist ~/.openfang/config.toml (channel_bridge.rs:1814 loest
    home_dir/config.toml auf) — die Vorlage haelt ihn reproduzierbar.
    """
    import tomllib
    toml_path = REPO_ROOT / "openfang" / "openfang.vibemind.toml"
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    servers = {s.get("name"): s for s in data.get("mcp_servers", [])}
    assert "laura" in servers, f"laura fehlt; vorhanden: {sorted(servers)}"
    laura = servers["laura"]
    assert laura["transport"]["type"] == "stdio"
    # Nur der NAME der Variable gehoert in die Config, nie der Wert
    assert laura.get("env") == ["LAURA_TOKEN"]

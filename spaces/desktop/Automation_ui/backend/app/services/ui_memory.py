"""
UI Memory Service - Element Position Cache + ASCII Screen Layout

Two optimizations to reduce expensive vision/OCR calls:

1. Element Cache: Remember positions of UI elements.
   Elements like "Save button in Word" are always at the same pixel
   coordinates on the same PC at the same resolution. Cache them once,
   reuse forever (until resolution changes or cache expires).

2. ASCII Screen Layout: Convert detected UI elements into a compact
   text grid (80x24 chars) with a scaling factor. Much cheaper to send
   to the LLM than full OCR dumps or screenshots. Gives spatial
   understanding of what's on screen.
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Persistent cache directory (survives server restarts)
CACHE_DIR = Path(__file__).parent.parent.parent / "ui_memory"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_FILE = CACHE_DIR / "element_cache.json"

# Cache settings
CACHE_MAX_AGE_HOURS = 168  # 7 days - elements are very stable
MIN_CONFIDENCE = 0.5       # Don't cache low-confidence results
USER_CONFIRM_THRESHOLD = 3 # After 3 user confirmations → auto-trust (no more asking)

# ASCII grid dimensions
GRID_COLS = 100  # chars wide
GRID_ROWS = 30   # chars tall


# ============================================
# Element Position Cache
# ============================================

def _normalize_key(app_context: str, element: str) -> str:
    """Create normalized cache key from app name and element description."""
    # Normalize: lowercase, collapse whitespace, remove special chars
    app = app_context.lower().strip()
    # Extract just the app name from window titles like "Document1 - Microsoft Word"
    for sep in [" - ", " – ", " — "]:
        if sep in app:
            parts = app.split(sep)
            # Usually the app name is last
            app = parts[-1].strip()
            break
    app = app.replace(" ", "_")

    elem = element.lower().strip().replace(" ", "_")
    return f"{app}:{elem}"


def _load_cache() -> Dict:
    """Load element cache from disk."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"resolution": "", "elements": {}, "version": 1}


def _save_cache(data: Dict) -> None:
    """Save element cache to disk."""
    try:
        CACHE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except OSError as e:
        logger.error(f"[UIMemory] Failed to save cache: {e}")


def get_screen_resolution() -> str:
    """Get current primary screen resolution."""
    try:
        import pyautogui
        size = pyautogui.size()
        return f"{size.width}x{size.height}"
    except Exception:
        return "unknown"


def cache_element(
    app_context: str,
    element: str,
    x: int,
    y: int,
    confidence: float = 1.0
) -> None:
    """
    Store a found element position in cache.

    Args:
        app_context: Window title or app name (e.g., "Microsoft Word")
        element: Element description (e.g., "Save button", "File menu")
        x, y: Pixel coordinates of element center
        confidence: Detection confidence (0-1)
    """
    if confidence < MIN_CONFIDENCE:
        return

    cache = _load_cache()
    resolution = get_screen_resolution()

    # Invalidate entire cache if resolution changed
    if cache.get("resolution") != resolution:
        logger.info(f"[UIMemory] Resolution changed to {resolution}, clearing cache")
        cache = {"resolution": resolution, "elements": {}, "version": 1}

    key = _normalize_key(app_context, element)
    existing = cache["elements"].get(key, {})

    cache["elements"][key] = {
        "x": x,
        "y": y,
        "confidence": confidence,
        "last_verified": time.time(),
        "hits": existing.get("hits", 0) + 1,
        "user_confirmed": existing.get("user_confirmed", 0),
        "app_raw": app_context,
        "element_raw": element
    }
    _save_cache(cache)
    logger.info(f"[UIMemory] Cached: {key} -> ({x},{y}) conf={confidence:.2f}")


def lookup_element(app_context: str, element: str) -> Optional[Dict[str, Any]]:
    """
    Look up cached element position.

    Returns dict with {x, y, confidence, hits, cached: True} or None if not found/stale.
    """
    cache = _load_cache()
    resolution = get_screen_resolution()

    # Resolution mismatch = cache invalid
    if cache.get("resolution") != resolution:
        return None

    key = _normalize_key(app_context, element)
    entry = cache["elements"].get(key)

    if not entry:
        # Try fuzzy match - element description might vary slightly
        for cached_key, cached_entry in cache["elements"].items():
            cached_app, cached_elem = cached_key.split(":", 1)
            norm_app = _normalize_key(app_context, "x").split(":")[0]
            if cached_app == norm_app and _fuzzy_match(element, cached_entry.get("element_raw", "")):
                entry = cached_entry
                break

    if not entry:
        return None

    # Check age
    age_hours = (time.time() - entry.get("last_verified", 0)) / 3600
    if age_hours > CACHE_MAX_AGE_HOURS:
        return None

    # Update hit count
    entry["hits"] = entry.get("hits", 0) + 1
    entry["last_verified"] = time.time()
    cache["elements"][key] = entry
    _save_cache(cache)

    confirmed = entry.get("user_confirmed", 0)
    return {
        "x": entry["x"],
        "y": entry["y"],
        "confidence": entry["confidence"],
        "hits": entry["hits"],
        "user_confirmed": confirmed,
        "trusted": confirmed >= USER_CONFIRM_THRESHOLD,
        "age_hours": round(age_hours, 1),
        "cached": True
    }


def _fuzzy_match(query: str, stored: str) -> bool:
    """Simple fuzzy match for element descriptions."""
    q = query.lower().strip()
    s = stored.lower().strip()
    # Exact substring match
    if q in s or s in q:
        return True
    # Word overlap
    q_words = set(q.split())
    s_words = set(s.split())
    if len(q_words & s_words) >= min(len(q_words), len(s_words)) * 0.7:
        return True
    return False


def invalidate_element(app_context: str, element: str) -> bool:
    """Remove element from cache (e.g., after failed click at cached coords)."""
    cache = _load_cache()
    key = _normalize_key(app_context, element)
    if key in cache["elements"]:
        del cache["elements"][key]
        _save_cache(cache)
        logger.info(f"[UIMemory] Invalidated: {key}")
        return True
    return False


def confirm_element(app_context: str, element: str) -> bool:
    """User confirmed that click on this element was correct. Increment counter."""
    cache = _load_cache()
    key = _normalize_key(app_context, element)
    entry = cache["elements"].get(key)
    if not entry:
        return False

    entry["user_confirmed"] = entry.get("user_confirmed", 0) + 1
    entry["confidence"] = min(1.0, entry.get("confidence", 0.5) + 0.1)
    entry["last_verified"] = time.time()
    cache["elements"][key] = entry
    _save_cache(cache)

    trusted = entry["user_confirmed"] >= USER_CONFIRM_THRESHOLD
    logger.info(f"[UIMemory] Confirmed: {key} ({entry['user_confirmed']}/{USER_CONFIRM_THRESHOLD}) trusted={trusted}")
    return trusted


def deny_element(app_context: str, element: str) -> bool:
    """User said click was wrong. Invalidate cached position."""
    logger.info(f"[UIMemory] Denied: {_normalize_key(app_context, element)}")
    return invalidate_element(app_context, element)


def is_trusted(app_context: str, element: str) -> bool:
    """Check if element has enough user confirmations to skip asking."""
    cache = _load_cache()
    key = _normalize_key(app_context, element)
    entry = cache["elements"].get(key)
    if not entry:
        return False
    return entry.get("user_confirmed", 0) >= USER_CONFIRM_THRESHOLD


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    cache = _load_cache()
    elements = cache.get("elements", {})
    return {
        "resolution": cache.get("resolution", "unknown"),
        "total_elements": len(elements),
        "total_hits": sum(e.get("hits", 0) for e in elements.values()),
        "apps": list(set(k.split(":")[0] for k in elements.keys())),
    }


def clear_cache() -> None:
    """Clear entire element cache."""
    _save_cache({"resolution": get_screen_resolution(), "elements": {}, "version": 1})
    logger.info("[UIMemory] Cache cleared")


# ============================================
# ASCII Screen Layout
# ============================================

def build_ascii_layout(
    elements: List[Dict[str, Any]],
    screen_width: int = 1920,
    screen_height: int = 1080,
    window_title: str = ""
) -> str:
    """
    Build ASCII representation of screen from detected UI elements.

    Each UI element's text is placed on a character grid at its
    approximate position. The grid uses a scaling factor so the
    LLM can understand spatial layout without expensive vision.

    Args:
        elements: List of {text, x, y, width, height} dicts (from OCR/detection)
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        window_title: Optional window title to show

    Returns:
        Compact ASCII layout string with coordinate annotations
    """
    # Calculate scale factors
    char_w = screen_width / GRID_COLS    # pixels per character horizontally
    char_h = screen_height / GRID_ROWS   # pixels per character vertically

    # Initialize grid with spaces
    grid = [[' ' for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]

    # Sort elements by y position (top to bottom), then x (left to right)
    sorted_elements = sorted(
        [e for e in elements if e.get("text", "").strip()],
        key=lambda e: (e.get("y", 0), e.get("x", 0))
    )

    # Place each element's text on the grid
    placed = []
    for elem in sorted_elements:
        text = elem.get("text", "").strip()
        if not text:
            continue

        # Get element center position
        ex = elem.get("x", 0)
        ey = elem.get("y", 0)
        ew = elem.get("width", 0)
        eh = elem.get("height", 0)
        cx = ex + ew / 2
        cy = ey + eh / 2

        # Convert to grid position
        col = int(ex / char_w)
        row = int(cy / char_h)

        # Clamp to grid bounds
        col = max(0, min(col, GRID_COLS - 1))
        row = max(0, min(row, GRID_ROWS - 1))

        # Truncate text to fit remaining grid width
        max_len = GRID_COLS - col
        text_short = text[:max_len]

        # Check for collision - if space is occupied, skip or find next row
        occupied = any(grid[row][col + i] != ' ' for i in range(min(len(text_short), max_len)))
        if occupied:
            # Try one row below
            if row + 1 < GRID_ROWS:
                row += 1
                occupied = any(grid[row][col + i] != ' ' for i in range(min(len(text_short), max_len)))

        if not occupied:
            # Place text on grid
            for i, ch in enumerate(text_short):
                if col + i < GRID_COLS:
                    grid[row][col + i] = ch

        placed.append({
            "text": text_short,
            "grid": f"[{col},{row}]",
            "px": f"({int(cx)},{int(cy)})"
        })

    # Build output string
    lines = []
    lines.append(f"ASCII-LAYOUT {screen_width}x{screen_height} | 1char={int(char_w)}x{int(char_h)}px | {len(placed)} Elemente")
    if window_title:
        lines.append(f"Fenster: {window_title}")

    # Grid border
    lines.append("+" + "-" * GRID_COLS + "+")
    for row in grid:
        line = "".join(row).rstrip()
        lines.append("|" + line.ljust(GRID_COLS) + "|")
    lines.append("+" + "-" * GRID_COLS + "+")

    # Element index (compact) - only show first 40
    if placed:
        lines.append(f"\nElemente ({len(placed)}):")
        for i, p in enumerate(placed[:40]):
            lines.append(f"  {p['grid']} \"{p['text']}\" px{p['px']}")
        if len(placed) > 40:
            lines.append(f"  ... +{len(placed) - 40} weitere")

    return "\n".join(lines)


def ocr_text_to_elements(ocr_text: str, screen_width: int = 1920, screen_height: int = 1080) -> List[Dict]:
    """
    Convert raw OCR text lines into element dicts with approximate positions.

    When we only have raw text (not structured UIElements), we estimate
    positions based on line number and text content.
    """
    lines = [l for l in ocr_text.split("\n") if l.strip()]
    if not lines:
        return []

    elements = []
    line_height = screen_height / max(len(lines), 1)

    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        elements.append({
            "text": text,
            "x": 10,  # Left margin estimate
            "y": int(i * line_height),
            "width": min(len(text) * 8, screen_width - 20),  # ~8px per char estimate
            "height": int(line_height * 0.8)
        })

    return elements

"""Maps Brain space names to OpenFang agent template names via YAML config."""

import logging
from pathlib import Path

import yaml

from bridge.config import settings

logger = logging.getLogger(__name__)

_mappings: dict[str, str] = {}
_min_confidence: float = 0.3
_FALLBACK = "vibemind"


def load(path: str | None = None):
    """Load the space->agent mapping from YAML config."""
    global _mappings, _min_confidence, _FALLBACK

    config_path = Path(path or settings.space_map_path)
    if not config_path.exists():
        logger.warning(f"Space map not found at {config_path}, using defaults")
        _mappings = {}
        return

    with open(config_path) as f:
        data = yaml.safe_load(f)

    _mappings = data.get("mappings", {})
    _min_confidence = data.get("min_confidence", settings.min_confidence)
    _FALLBACK = data.get("fallback_agent", "vibemind")
    logger.info(f"Loaded {len(_mappings)} space->agent mappings (fallback={_FALLBACK})")


def map_space(space: str, confidence: float) -> str:
    """Map a Brain space name to an OpenFang agent name.

    Returns fallback agent if confidence is below threshold or space unknown.
    """
    if confidence < _min_confidence:
        return _FALLBACK
    return _mappings.get(space, _FALLBACK)


def get_mappings() -> dict:
    """Return current mappings for the /bridge/mapping endpoint."""
    return {"mappings": dict(_mappings), "min_confidence": _min_confidence}


def reload():
    """Hot-reload the YAML config."""
    load()

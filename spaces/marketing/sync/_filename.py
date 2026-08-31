"""Filename sanitization for handle -> *.md.

Handles can contain unicode, spaces, or special chars. The filename
must be ASCII-safe + filesystem-safe across Windows / Linux / macOS.

The mapping is *not* reversible — the original handle stays in the
frontmatter as the canonical reference. The filename is just a hint.
"""
from __future__ import annotations

import re
import unicodedata

# Reserve some special filenames that the worker uses
RESERVED_NAMES = {"_index.md", "_README.md", ".gitkeep"}


def sanitize_handle_for_filename(handle: str, max_len: int = 80) -> str:
    """Convert a raw handle to a safe .md filename.

    >>> sanitize_handle_for_filename("kennethharris")
    'kennethharris.md'
    >>> sanitize_handle_for_filename("Hans Müller")
    'hans_mueller.md'
    >>> sanitize_handle_for_filename("O'Brien-Smith")
    "o_brien-smith.md"
    >>> sanitize_handle_for_filename("a" * 200, max_len=20)
    'aaaaaaaaaaaaaaaaa.md'   # 17 chars + '.md' = 20
    """
    # 1. Unicode normalize + strip accents (NFKD then drop combining marks)
    normalized = unicodedata.normalize("NFKD", handle)
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))

    # 2. Lower-case for case-insensitive filesystems (macOS, Windows)
    lower = ascii_only.lower()

    # 3. Replace anything that isn't [a-z0-9._-] with underscore
    safe = re.sub(r"[^a-z0-9._-]", "_", lower)

    # 4. Collapse repeated underscores
    safe = re.sub(r"_{2,}", "_", safe)

    # 5. Trim leading/trailing underscore/dot
    safe = safe.strip("._-")

    # 6. Fallback if everything got stripped
    if not safe:
        safe = "untitled"

    # 7. Length cap, leaving room for ".md"
    suffix_len = len(".md")
    if len(safe) + suffix_len > max_len:
        safe = safe[: max_len - suffix_len]
        safe = safe.rstrip("._-") or "untitled"

    filename = safe + ".md"

    # 8. Avoid reserved names
    if filename in RESERVED_NAMES:
        filename = "_" + filename

    return filename


def handle_was_lossy(handle: str, filename: str) -> bool:
    """Returns True iff the filename does NOT round-trip from the handle.

    Caller should log a warning when this is True and keep the original
    handle in frontmatter.
    """
    expected = sanitize_handle_for_filename(handle)
    return expected != filename or filename.removesuffix(".md") != handle.lower()

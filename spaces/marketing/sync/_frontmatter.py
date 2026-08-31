"""Deterministic YAML frontmatter serializer.

Hand-rolled instead of PyYAML so we get exact control over:
  - field ordering (must be stable for diff-friendliness)
  - quoting style (use double-quotes only when needed)
  - null representation ('null' vs '' vs absent)
  - list formatting (block-style for readability, even single-item)

The schema is FIXED — we serialise a known set of fields in a known order.
This is not a general YAML writer; it's a renderer for one specific schema.

Schema groups (in this order):
  1. sync-meta:      sync_id, sync_version, sync_source, sync_path, last_synced_at
  2. identity:       handle, display_name, niche, source, followers, created_at
  3. email roll-up:  primary_email, all_emails (list of objects)
  4. tags:           tags (list of strings)
  5. audience:       audience_memberships (list of objects)
  6. engagement:     send_history_count, last_send_at, last_open_at,
                     last_click_at, last_reply_at
  7. inbound:        inbound_count, last_inbound_at
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

# Stable schema definition — field name and group.
# When a new field is added, also bump sync_version in the rendered output.
SCHEMA_GROUPS: list[tuple[str, list[str]]] = [
    ("sync-meta",  ["sync_id", "sync_version", "sync_source", "sync_path", "last_synced_at"]),
    ("identity",   ["handle", "display_name", "niche", "source", "followers", "created_at"]),
    ("email",      ["primary_email", "all_emails"]),
    ("tags",       ["tags"]),
    ("audience",   ["audience_memberships"]),
    ("engagement", ["send_history_count", "last_send_at", "last_open_at",
                    "last_click_at", "last_reply_at"]),
    ("inbound",    ["inbound_count", "last_inbound_at"]),
]

# Flat ordered list of every field name (faster lookups + ordering)
SCHEMA_FIELDS: list[str] = [f for _, fields in SCHEMA_GROUPS for f in fields]


def _scalar(value: Any) -> str:
    """Serialise a YAML scalar with safe quoting.

    Rules:
      None      -> 'null'
      bool      -> 'true' / 'false'
      int/float -> str(value)
      datetime  -> ISO-8601 with explicit timezone (UTC)
      str       -> bare if safe, else double-quoted with escapes
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        # Always UTC-aware. If naive, assume UTC.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if isinstance(value, str):
        # Bare-safe condition: no leading special char, no special chars in body,
        # not a YAML reserved-looking string ("null", "true", "false", "yes" etc.)
        if not value:
            return '""'
        reserved = {"null", "true", "false", "yes", "no", "on", "off", "~"}
        bare_safe = (
            value not in reserved
            and value[0] not in ' \t-?[{!&*|>"\'%@`#,'
            and value[-1] not in " \t"
            and not any(c in value for c in ":#\n\r\t\"\\")
            and not value.replace(".", "").replace("-", "").isdigit()  # avoid quote-less numbers
        )
        if bare_safe:
            return value
        # Need quoting. Escape \ and " inside.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    raise TypeError(f"Unhandled YAML scalar type: {type(value).__name__}")


def _emit_list(key: str, items: list[Any], indent: int = 0) -> list[str]:
    """Emit a list — block style (`- item`) so each line diffs cleanly."""
    prefix = " " * indent
    if not items:
        return [f"{prefix}{key}: []"]
    out = [f"{prefix}{key}:"]
    for item in items:
        if isinstance(item, dict):
            # Object item — emit each key on its own line under `- `
            keys = list(item.keys())
            first_key = keys[0]
            out.append(f"{prefix}  - {first_key}: {_scalar(item[first_key])}")
            for k in keys[1:]:
                out.append(f"{prefix}    {k}: {_scalar(item[k])}")
        else:
            out.append(f"{prefix}  - {_scalar(item)}")
    return out


def render_frontmatter(data: dict) -> str:
    """Render a frontmatter dict to the canonical YAML form.

    Unknown fields are silently dropped — the schema is closed.
    Missing fields appear as `key: null`.
    """
    lines: list[str] = ["---"]

    for group_name, fields in SCHEMA_GROUPS:
        # Group separator comment between groups (after the first)
        if group_name != "sync-meta":
            lines.append("")
        for field in fields:
            value = data.get(field)
            if isinstance(value, list):
                lines.extend(_emit_list(field, value))
            else:
                lines.append(f"{field}: {_scalar(value)}")

    lines.append("---")
    return "\n".join(lines)


def parse_frontmatter(md_text: str) -> dict | None:
    """Tiny frontmatter parser for round-trip diffing.

    Only handles what we emit (no edge cases). Returns None if no
    frontmatter block found.

    Used by worker_fs_to_db to compare file content against DB-rendered
    content for loop detection (= "did Felix edit this, or is this my
    own last write?").
    """
    if not md_text.startswith("---\n"):
        return None
    end = md_text.find("\n---\n", 4)
    if end < 0:
        return None
    fm_block = md_text[4:end]

    out: dict[str, Any] = {}
    current_list_key: str | None = None
    current_list_items: list = []
    current_dict_item: dict | None = None
    for raw_line in fm_block.split("\n"):
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        # In a list?
        if current_list_key is not None:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent >= 2 and stripped.startswith("- "):
                # New item
                if current_dict_item is not None:
                    current_list_items.append(current_dict_item)
                    current_dict_item = None
                item_text = stripped[2:].strip()
                if ":" in item_text:
                    k, _, v = item_text.partition(":")
                    current_dict_item = {k.strip(): _parse_scalar(v.strip())}
                else:
                    current_list_items.append(_parse_scalar(item_text))
                continue
            if indent >= 4 and current_dict_item is not None and ":" in stripped:
                k, _, v = stripped.partition(":")
                current_dict_item[k.strip()] = _parse_scalar(v.strip())
                continue
            # List ended
            if current_dict_item is not None:
                current_list_items.append(current_dict_item)
                current_dict_item = None
            out[current_list_key] = current_list_items
            current_list_key = None
            current_list_items = []
            # fall through to non-list parsing below

        # Top-level "key: value" or "key:"
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "" or val == "[]":
                if val == "[]":
                    out[key] = []
                else:
                    current_list_key = key
                    current_list_items = []
                    current_dict_item = None
            else:
                out[key] = _parse_scalar(val)

    # Flush trailing list
    if current_list_key is not None:
        if current_dict_item is not None:
            current_list_items.append(current_dict_item)
        out[current_list_key] = current_list_items

    return out


def _parse_scalar(text: str) -> Any:
    """Inverse of _scalar — minimal."""
    if text == "null":
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
    # number?
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text

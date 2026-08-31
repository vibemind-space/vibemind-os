"""Pure-function Markdown renderer for marketing.accounts rows.

Phase 2 of the marketing-data-sync plan. No file I/O, no DB writes —
takes a handle, queries the DB, returns a Markdown string. Workers
(Phase 4/5) handle the FS side and the back-propagation.

Usage:
    from spaces.marketing.sync.render_md import render_person_md
    md = render_person_md('kennethharris')
    print(md)

CLI:
    python -m spaces.marketing.sync.render_md --handle kennethharris
    python -m spaces.marketing.sync.render_md --handle kennethharris --output /tmp/test.md
    python -m spaces.marketing.sync.render_md --all --output-dir /tmp/render-test/
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import _db, _queries
from ._filename import sanitize_handle_for_filename
from ._frontmatter import render_frontmatter

SYNC_VERSION = 1
SYNC_SOURCE = "supabase"
STALE_THRESHOLD_DAYS = int(os.environ.get("MARKETING_STALE_DAYS", "90"))
HISTORY_LIMIT = 20

# Final user-content fence — body below this fence is owned by the user
USER_FENCE = "<!-- ──────────────────────────────────────────────────────────────────── -->"
USER_FENCE_NOTE = (
    "<!-- Custom notes below this line.                                         -->\n"
    "<!-- Everything BELOW this fence is owned by the user and will NOT be      -->\n"
    "<!-- overwritten by the sync worker. Frontmatter and sections ABOVE        -->\n"
    "<!-- this fence are DB-rendered and re-generated on every sync.            -->"
)


# ─── helpers ──────────────────────────────────────────────────────────────


def _iso(dt) -> str:
    """ISO-8601 UTC. Accepts datetime, str (passthrough), or None."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return str(dt)


def _bool_mark(value) -> str:
    if value is True:
        return "✓"
    if value is False:
        return "✗"
    return "—"


def _smtp_mark(value) -> str:
    if value == 1:
        return "OK"
    if value == 0:
        return "fail"
    return "—"


def _stale_or_iso(iso_str: str | None, now: datetime) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return iso_str
    age_days = (now - dt).days
    if age_days > STALE_THRESHOLD_DAYS:
        return f"_stale_ ({age_days}d)"
    return iso_str.split("T")[0]


# ─── core renderer ─────────────────────────────────────────────────────────


def render_person_md(
    handle: str,
    *,
    now: datetime | None = None,
    container: str | None = None,
    row: dict | None = None,
) -> tuple[str, dict]:
    """Render a single account's markdown.

    Returns (markdown_text, debug_info_dict).
    `row` can be passed to skip the DB query (used by snapshot tests).
    """
    started = time.perf_counter()
    if now is None:
        now = datetime.now(timezone.utc)

    if row is None:
        row = _db.query_one(_queries.ACCOUNT_RENDER_QUERY, {"handle": handle}, container)
    if row is None:
        raise LookupError(f"No marketing.accounts row for handle={handle!r}")

    md = _render_from_row(row, now=now)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    debug = {
        "handle": handle,
        "render_ms": round(elapsed_ms, 2),
        "byte_count": len(md.encode("utf-8")),
        "send_count": row.get("send_history_count", 0),
        "inbound_count": row.get("inbound_count", 0),
    }
    return md, debug


def _render_from_row(row: dict, *, now: datetime) -> str:
    handle = row["handle"]
    display_name = row.get("display_name") or ""
    niche = row.get("niche") or ""
    source = row.get("source") or ""
    followers = row.get("followers") or 0
    created_at_iso = _iso(row.get("created_at"))
    last_synced_at_iso = _iso(row.get("last_synced_at"))

    emails = row.get("emails") or []
    primary_email = row.get("primary_email")
    tags = row.get("tags") or []
    audience_memberships = row.get("audience_memberships") or []
    recent_sends = row.get("recent_sends") or []
    recent_inbound = row.get("recent_inbound") or []
    strategies = row.get("strategies") or []

    send_count = row.get("send_history_count") or 0
    inbound_count = row.get("inbound_count") or 0

    # ─── Frontmatter ──────────────────────────────────────────────────────
    fm_data = {
        # sync-meta
        "sync_id": row["sync_id"],
        "sync_version": SYNC_VERSION,
        "sync_source": SYNC_SOURCE,
        "sync_path": f"marketing.accounts/{handle}",
        "last_synced_at": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        # identity
        "handle": handle,
        "display_name": display_name,
        "niche": niche,
        "source": source,
        "followers": followers,
        "created_at": created_at_iso or None,
        # email rollup
        "primary_email": primary_email,
        "all_emails": [
            {
                "email": e["email"],
                "confidence": e["confidence"],
                "mx_valid": e["mx_valid"],
                "smtp_valid": e["smtp_valid"],
                "domain": e["domain"],
                "country": e["country"],
                "catch_all": e["catch_all"],
                "consent_given_at": e.get("consent_given_at"),
                "consent_source": e.get("consent_source") or "",
                "unsubscribed_at": e.get("unsubscribed_at"),
                "bounce_count": e.get("bounce_count", 0),
                "last_engagement_at": e.get("last_engagement_at"),
                "investor_already_sent": e.get("investor_already_sent", False),
            }
            for e in emails
        ],
        # tags
        "tags": tags,
        # audience
        "audience_memberships": [
            {"audience_id": m["audience_id"], "audience_name": m["audience_name"], "added_at": m.get("added_at")}
            for m in audience_memberships
        ],
        # engagement
        "send_history_count": send_count,
        "last_send_at": row.get("last_send_at"),
        "last_open_at": row.get("last_open_at"),
        "last_click_at": row.get("last_click_at"),
        "last_reply_at": row.get("last_reply_at"),
        # inbound
        "inbound_count": inbound_count,
        "last_inbound_at": row.get("last_inbound_at"),
    }
    fm_block = render_frontmatter(fm_data)

    # ─── Body ─────────────────────────────────────────────────────────────
    title = display_name if display_name else handle
    out = [fm_block, "", f"# {title}", ""]

    # Identity block
    out += [
        f"**Handle:** `{handle}`",
    ]
    if niche:
        out.append(f"**Region:** {niche}")
    if source:
        out.append(f"**Source:** {source}")
    out.append(f"**Followers:** {followers}")
    if created_at_iso:
        out.append(f"**Created:** {created_at_iso.split('T')[0]}")
    out.append("")

    # Bio
    bio = row.get("bio") or ""
    if bio:
        out.append("## Bio")
        out.append("")
        out.append(bio)
        out.append("")

    # Emails
    out.append("## Emails")
    out.append("")
    if not emails:
        out.append("_No emails (handle exists in marketing.accounts but no entries in marketing.emails)._")
    else:
        out.append("| Email | Confidence | MX | SMTP | Consent | Last Engagement | Lockout |")
        out.append("|---|---:|:-:|:-:|---|---|:-:|")
        for e in emails:
            consent = "_none_" if not e.get("consent_given_at") else _iso(e["consent_given_at"]).split("T")[0]
            last_eng = _stale_or_iso(_iso(e.get("last_engagement_at")), now)
            lockout = "🔒 _sent_" if e.get("investor_already_sent") else "_open_"
            out.append(
                f"| `{e['email']}` | {e['confidence']:.2f} | {_bool_mark(e['mx_valid'])} | "
                f"{_smtp_mark(e['smtp_valid'])} | {consent} | {last_eng} | {lockout} |"
            )
    out.append("")

    # Tags
    out.append("## Tags")
    out.append("")
    if not tags:
        out.append("_None._")
    else:
        for t in tags:
            out.append(f"- {t}")
    out.append("")

    # Audience memberships
    out.append("## Audience Memberships")
    out.append("")
    if not audience_memberships:
        out.append("_Not in any audience._")
    else:
        for m in audience_memberships:
            added = _iso(m.get("added_at")).split("T")[0] if m.get("added_at") else "?"
            out.append(f"- **{m['audience_name']}** _(since {added})_")
    out.append("")

    # Send history
    out.append("## Send History")
    out.append("")
    if not recent_sends:
        out.append("_No campaigns sent to this person yet._")
    else:
        out.append("| Campaign | Email | Sent | Opened | Clicked | Replied | Bounced |")
        out.append("|---|---|---|---|---|---|---|")
        for s in recent_sends:
            out.append(
                f"| {s.get('campaign_name') or '_(unnamed)_'} | `{s['email']}` | "
                f"{_iso(s.get('sent_at')).split('T')[0] or '—'} | "
                f"{_iso(s.get('opened_at')).split('T')[0] or '—'} | "
                f"{_iso(s.get('clicked_at')).split('T')[0] or '—'} | "
                f"{_iso(s.get('replied_at')).split('T')[0] or '—'} | "
                f"{_iso(s.get('bounced_at')).split('T')[0] or '—'} |"
            )
        if send_count > HISTORY_LIMIT:
            out.append(f"")
            out.append(f"_Showing last {HISTORY_LIMIT} of {send_count}. See `marketing.campaign_sends` for the full history._")
    out.append("")

    # Reply history
    out.append("## Reply History")
    out.append("")
    if not recent_inbound:
        out.append("_No inbound messages._")
    else:
        out.append("| Received | From | Subject | Type |")
        out.append("|---|---|---|---|")
        for r in recent_inbound:
            kind = "bounce" if r.get("is_bounce") else ("auto-reply" if r.get("is_autoreply") else "reply")
            subject = (r.get("subject") or "_(no subject)_")[:80]
            from_label = r.get("from_name") or r.get("from_email") or "?"
            out.append(f"| {_iso(r.get('received_at')).split('T')[0]} | {from_label} | {subject} | {kind} |")
        if inbound_count > HISTORY_LIMIT:
            out.append("")
            out.append(f"_Showing last {HISTORY_LIMIT} of {inbound_count}. See `marketing.inbound_messages`._")
    out.append("")

    # Strategies
    if strategies:
        out.append("## Strategies that Generated This Person")
        out.append("")
        out.append("| Strategy ID | Pattern | Domain | Fitness | Successes |")
        out.append("|---|---|---|---:|---:|")
        for s in sorted(strategies, key=lambda x: -(x.get("fitness") or 0)):
            out.append(
                f"| `{s['id']}` | `{s.get('format_pattern') or '?'}` | "
                f"{s.get('domain') or '—'} | {s.get('fitness', 0):.2f} | {s.get('success_count', 0)} |"
            )
        out.append("")

    # User fence (everything below is editable by Felix)
    out.append("---")
    out.append("")
    out.append(USER_FENCE)
    out.append(USER_FENCE_NOTE)
    out.append(USER_FENCE)
    out.append("")
    out.append("")

    return "\n".join(out)


# ─── CLI ───────────────────────────────────────────────────────────────────


def _main() -> int:
    # Windows console cp1252 chokes on ✓/✗/🔒; force UTF-8 stdout
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--handle", help="Render exactly one handle")
    p.add_argument("--all", action="store_true", help="Render all accounts")
    p.add_argument("--limit", type=int, default=None, help="With --all: only first N (for testing)")
    p.add_argument("--output", help="With --handle: write to this file (else stdout)")
    p.add_argument("--output-dir", help="With --all: write each handle to <dir>/<handle>.md")
    args = p.parse_args()

    if not args.handle and not args.all:
        p.error("--handle OR --all required")

    container = _db.find_supabase_container()

    if args.handle:
        md, dbg = render_person_md(args.handle, container=container)
        if args.output:
            Path(args.output).write_text(md, encoding="utf-8")
            print(f"Wrote {len(md)} bytes to {args.output}  (render_ms={dbg['render_ms']})")
        else:
            sys.stdout.write(md)
        return 0

    # --all
    rows = _db.query_via_docker(_queries.LIST_ALL_HANDLES_QUERY, container=container)
    if args.limit:
        rows = rows[: args.limit]
    if not args.output_dir:
        p.error("--all requires --output-dir")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    start = time.perf_counter()
    for i, r in enumerate(rows, 1):
        md, dbg = render_person_md(r["handle"], container=container)
        fname = sanitize_handle_for_filename(r["handle"])
        (out_dir / fname).write_text(md, encoding="utf-8")
        if i % 100 == 0 or i == total:
            elapsed = time.perf_counter() - start
            rate = i / elapsed if elapsed else 0
            print(f"  [{i}/{total}]  {rate:.0f} renders/s")
    print(f"Done. {total} files in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

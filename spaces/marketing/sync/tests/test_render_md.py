"""Snapshot + property tests for render_md.

These don't need pytest — they're plain functions called from __main__.
Run:
    python -m spaces.marketing.sync.tests.test_render_md

Exit 0 if all pass.
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone

# Stable now() for deterministic test output
FROZEN_NOW = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)


def _sample_row(**overrides) -> dict:
    """Build a canonical minimal account row with overridable fields."""
    base = {
        "sync_id": "00000000-0000-0000-0000-000000000001",
        "handle": "testperson",
        "display_name": "Test Person",
        "niche": "DACH",
        "source": "test",
        "followers": 42,
        "bio": "",
        "created_at": "2026-01-15T10:00:00+00:00",
        "last_synced_at": None,
        "emails": [],
        "primary_email": None,
        "tags": [],
        "audience_memberships": [],
        "send_history_count": 0,
        "last_send_at": None,
        "last_open_at": None,
        "last_click_at": None,
        "last_reply_at": None,
        "inbound_count": 0,
        "last_inbound_at": None,
        "recent_sends": [],
        "recent_inbound": [],
        "strategies": [],
    }
    base.update(overrides)
    return base


def _render(row) -> str:
    from spaces.marketing.sync.render_md import render_person_md
    md, _ = render_person_md(row["handle"], now=FROZEN_NOW, row=row)
    return md


def _check(label: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -- {detail}" if detail else ""))
    return cond


def test_empty_account():
    """Account with 0 emails - all empty-states should render correctly."""
    md = _render(_sample_row())
    return all([
        _check("empty: 'No emails' text", "_No emails" in md),
        _check("empty: 'None.' for tags", "## Tags\n\n_None._" in md),
        _check("empty: 'Not in any audience' text", "_Not in any audience._" in md),
        _check("empty: 'No campaigns sent' text", "_No campaigns sent" in md),
        _check("empty: 'No inbound messages' text", "_No inbound messages._" in md),
        _check("empty: primary_email null in frontmatter", "primary_email: null" in md),
        _check("empty: all_emails empty list", "all_emails: []" in md),
    ])


def test_single_email_account():
    """Account with one email — table + frontmatter populated."""
    md = _render(_sample_row(
        emails=[{
            "email": "test@example.com",
            "confidence": 0.92,
            "mx_valid": True,
            "smtp_valid": 1,
            "domain": "example.com",
            "country": "DE",
            "catch_all": False,
            "consent_given_at": None,
            "consent_source": "manual",
            "unsubscribed_at": None,
            "bounce_count": 0,
            "last_engagement_at": None,
            "investor_already_sent": False,
        }],
        primary_email="test@example.com",
    ))
    return all([
        _check("single: primary_email set in fm", "primary_email: test@example.com" in md),
        _check("single: email in body table", "`test@example.com`" in md),
        _check("single: confidence shown", "0.92" in md),
        _check("single: lockout 'open'", "_open_" in md),
    ])


def test_multi_email_ordering():
    """3 emails, primary = highest confidence."""
    md = _render(_sample_row(
        emails=[
            {"email": "a@x.com", "confidence": 0.50, "mx_valid": False, "smtp_valid": -1,
             "domain": "x.com", "country": "X", "catch_all": False, "consent_given_at": None,
             "consent_source": "", "unsubscribed_at": None, "bounce_count": 0,
             "last_engagement_at": None, "investor_already_sent": False},
            {"email": "b@x.com", "confidence": 0.99, "mx_valid": True, "smtp_valid": 1,
             "domain": "x.com", "country": "X", "catch_all": False, "consent_given_at": None,
             "consent_source": "", "unsubscribed_at": None, "bounce_count": 0,
             "last_engagement_at": None, "investor_already_sent": False},
            {"email": "c@x.com", "confidence": 0.75, "mx_valid": True, "smtp_valid": 0,
             "domain": "x.com", "country": "X", "catch_all": False, "consent_given_at": None,
             "consent_source": "", "unsubscribed_at": None, "bounce_count": 0,
             "last_engagement_at": None, "investor_already_sent": False},
        ],
        primary_email="b@x.com",  # highest confidence
    ))
    # Check that b@ appears before a@ and c@ in the body table (already sorted by query)
    pos_a = md.find("`a@x.com`")
    pos_b = md.find("`b@x.com`")
    pos_c = md.find("`c@x.com`")
    return all([
        _check("multi: b@ is primary", "primary_email: b@x.com" in md),
        _check("multi: all 3 in body", pos_a > 0 and pos_b > 0 and pos_c > 0),
    ])


def test_determinism():
    """Same input twice -> identical output bytes."""
    row = _sample_row(
        emails=[{
            "email": "deterministic@example.com",
            "confidence": 0.80, "mx_valid": True, "smtp_valid": 1,
            "domain": "example.com", "country": "DE", "catch_all": False,
            "consent_given_at": None, "consent_source": "", "unsubscribed_at": None,
            "bounce_count": 0, "last_engagement_at": None, "investor_already_sent": False,
        }],
        primary_email="deterministic@example.com",
    )
    md1 = _render(row)
    md2 = _render(row)
    h1 = hashlib.sha256(md1.encode()).hexdigest()
    h2 = hashlib.sha256(md2.encode()).hexdigest()
    return _check("determinism: identical hash on re-render", h1 == h2, f"h1={h1[:12]} h2={h2[:12]}")


def test_quoting():
    """Special chars in display_name → proper YAML quoting."""
    md = _render(_sample_row(
        display_name='Mary "Mike" O\'Brien',
    ))
    return _check(
        "quoting: special-char name in frontmatter",
        'display_name: "Mary \\"Mike\\" O' in md,
    )


def test_frontmatter_roundtrip():
    """Render -> parse -> compare key fields."""
    from spaces.marketing.sync._frontmatter import parse_frontmatter
    row = _sample_row(
        emails=[{
            "email": "rt@example.com",
            "confidence": 0.85, "mx_valid": True, "smtp_valid": 1,
            "domain": "example.com", "country": "FR", "catch_all": False,
            "consent_given_at": None, "consent_source": "", "unsubscribed_at": None,
            "bounce_count": 0, "last_engagement_at": None, "investor_already_sent": False,
        }],
        primary_email="rt@example.com",
        tags=["enterprise", "warm"],
    )
    md = _render(row)
    parsed = parse_frontmatter(md)
    return all([
        _check("roundtrip: parser found block", parsed is not None),
        _check("roundtrip: handle preserved", parsed and parsed.get("handle") == "testperson"),
        _check("roundtrip: primary_email preserved", parsed and parsed.get("primary_email") == "rt@example.com"),
        _check("roundtrip: tags list", parsed and parsed.get("tags") == ["enterprise", "warm"]),
    ])


def test_lockout_flag():
    md = _render(_sample_row(
        emails=[{
            "email": "locked@x.com", "confidence": 0.9, "mx_valid": True, "smtp_valid": 1,
            "domain": "x.com", "country": "X", "catch_all": False, "consent_given_at": None,
            "consent_source": "", "unsubscribed_at": None, "bounce_count": 0,
            "last_engagement_at": None, "investor_already_sent": True,
        }],
        primary_email="locked@x.com",
    ))
    return all([
        _check("lockout: investor_already_sent: true in fm", "investor_already_sent: true" in md),
        _check("lockout: 🔒 _sent_ symbol in body", "_sent_" in md),
    ])


def test_user_fence_present():
    md = _render(_sample_row())
    fence_count = md.count("Custom notes below this line")
    return _check("fence: user content fence present once", fence_count == 1)


def test_strategies_section():
    md = _render(_sample_row(
        strategies=[
            {"id": "email_0007", "format_pattern": "<first><last>", "domain": "gmail.com",
             "fitness": 0.95, "success_count": 268},
        ],
    ))
    return all([
        _check("strategies: section header", "## Strategies that Generated This Person" in md),
        _check("strategies: pattern shown", "<first><last>" in md),
    ])


def main():
    tests = [
        test_empty_account,
        test_single_email_account,
        test_multi_email_ordering,
        test_determinism,
        test_quoting,
        test_frontmatter_roundtrip,
        test_lockout_flag,
        test_user_fence_present,
        test_strategies_section,
    ]
    print(f"Running {len(tests)} snapshot tests...\n")
    passed = 0
    for t in tests:
        print(f"== {t.__name__} ==")
        if t():
            passed += 1
        print()
    print(f"=== {passed}/{len(tests)} test groups passed ===")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())

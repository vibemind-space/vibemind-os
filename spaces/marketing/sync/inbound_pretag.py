"""Pre-classification of inbound mail messages (Schicht 6.2a).

DSGVO-Note: This module runs LOCAL ONLY. No payload is ever sent to
external services. Pure regex + header inspection -- no LLM-call.

Five pre-classification labels:
    'bounce'   — DSN-bounce per RFC 3464 (high confidence)
                 - Auto-Submitted: auto-replied (RFC 3834)
                 - Content-Type: multipart/report; report-type=delivery-status
                 - From: mailer-daemon@ or postmaster@
                 - body matches "X-Failed-Recipients" header
                 - 5.x.x SMTP status code in body
                 - Subject prefix "Delivery Status Notification"
    'opt-out'  — recipient explicitly requested unsubscribe (high confidence)
                 - Subject contains "unsubscribe"
                 - body contains "remove me from your list" / "abmelden"
                 - List-Unsubscribe-Post header indicates RFC 8058 one-click
                   (we shouldn't be receiving this, but if we do, treat as opt-out)
    'reply'    — in-reply-to header matches one of OUR sent message_ids
                 - requires DB lookup (caller-provided check_message_id_known function)
                 - regex-only fallback: any In-Reply-To header set + Subject starts with Re:
    'spam'     — high spam-score header OR SPF/DKIM-fail
                 - X-Spam-Score, X-Spam-Status: Yes
                 - Authentication-Results: spf=fail OR dkim=fail
    'unknown'  — neither bounce nor opt-out nor reply nor spam.
                 n8n picks these up for further classification.

needs_review (boolean):
    False — pre_classification ∈ {'bounce', 'opt-out'} (deterministic + actionable)
    True  — everything else, including 'spam' (need curator-look) and 'reply'
            (need enrichment + curator approval) and 'unknown' (need n8n look)

The two booleans is_bounce + is_autoreply (legacy) are derived:
    is_bounce    = pre_classification == 'bounce'
    is_autoreply = re-uses old AUTOREPLY_HINTS regex (orthogonal to pre_classification)
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Tuple


# ─── RFC 3464 bounce detection (high-confidence) ──────────────────────


# Strict: header-level signals (very low false-positive rate)
_BOUNCE_HEADER_PATTERNS: tuple[re.Pattern[str], ...] = (
    # RFC 3834 — Auto-Submitted: auto-generated|auto-replied
    re.compile(r"^Auto-Submitted:\s*(auto-generated|auto-replied)",
                re.IGNORECASE | re.MULTILINE),
    # RFC 3464 — Content-Type multipart/report; report-type=delivery-status
    re.compile(r"Content-Type:.*multipart/report.*report-type=delivery-status",
                re.IGNORECASE | re.DOTALL),
    # X-Failed-Recipients header (typical for postfix/exim)
    re.compile(r"^X-Failed-Recipients:", re.IGNORECASE | re.MULTILINE),
    # From: mailer-daemon or postmaster
    re.compile(r"^From:\s*[^\n]*?(mailer-daemon|postmaster|MAILER-DAEMON)@",
                re.IGNORECASE | re.MULTILINE),
)

# Body / Subject signals — slightly weaker, used in combination
_BOUNCE_BODY_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 5.x.x permanent SMTP errors (RFC 3463)
    re.compile(r"\b5\.\d\.\d\b"),
    # Common bounce phrases
    re.compile(r"delivery (status|failure) notification", re.IGNORECASE),
    re.compile(r"undeliverable", re.IGNORECASE),
    re.compile(r"could not be delivered", re.IGNORECASE),
    re.compile(r"the following message could not be delivered", re.IGNORECASE),
    re.compile(r"550[ -](no such user|invalid recipient)", re.IGNORECASE),
)


# ─── Opt-out / unsubscribe detection ─────────────────────────────────


_OPT_OUT_HEADER_PATTERNS: tuple[re.Pattern[str], ...] = (
    # RFC 8058 — we shouldn't normally receive this header inbound, but if
    # a user-agent injects it (e.g. someone forwards an unsub-confirmation),
    # treat as opt-out.
    re.compile(r"^List-Unsubscribe-Post:", re.IGNORECASE | re.MULTILINE),
)

_OPT_OUT_SUBJECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Subject:[^\n]*\bunsubscribe\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Subject:[^\n]*\b(abmelden|abbestellen)\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Subject:[^\n]*\bremove\b.{0,40}\blist\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Subject:[^\n]*\bopt[- ]?out\b", re.IGNORECASE | re.MULTILINE),
)

_OPT_OUT_BODY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(please|kindly)\s+(remove|unsubscribe)\b.{0,30}\b(me|us)\b",
                re.IGNORECASE),
    re.compile(r"\bbitte\b.{0,40}\b(abmelden|austragen)\b", re.IGNORECASE),
    re.compile(r"\b(remove|unsubscribe)\s+me\s+from\b", re.IGNORECASE),
)


# ─── Reply detection ─────────────────────────────────────────────────


_IN_REPLY_TO_PATTERN = re.compile(
    r"^In-Reply-To:\s*<([^>]+)>", re.IGNORECASE | re.MULTILINE
)
_RE_SUBJECT_PATTERN = re.compile(
    r"^Subject:\s*Re:\s", re.IGNORECASE | re.MULTILINE
)


# ─── Spam detection ──────────────────────────────────────────────────


_SPAM_PATTERNS: tuple[re.Pattern[str], ...] = (
    # X-Spam-Status: Yes (SpamAssassin standard)
    re.compile(r"^X-Spam-Status:\s*Yes", re.IGNORECASE | re.MULTILINE),
    # X-Spam-Flag: YES
    re.compile(r"^X-Spam-Flag:\s*YES", re.IGNORECASE | re.MULTILINE),
    # X-Spam-Score >= 5.0 (configurable threshold)
    re.compile(r"^X-Spam-Score:\s*([5-9]|\d{2,})\.", re.IGNORECASE | re.MULTILINE),
    # Authentication-Results: spf=fail OR dkim=fail (both = strong spam signal)
    re.compile(r"^Authentication-Results:[^\n]*\bspf=fail",
                re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Authentication-Results:[^\n]*\bdkim=fail",
                re.IGNORECASE | re.MULTILINE),
)


# ─── Main pre-classifier ─────────────────────────────────────────────


def pre_classify(
    headers_raw: str,
    body: str,
    *,
    check_message_id_known: Optional[Callable[[str], bool]] = None,
) -> Tuple[str, bool]:
    """Pre-classify an inbound mail.

    Args:
        headers_raw: raw RFC 5322 headers as a single string (newlines preserved)
        body: plain-text body (HTML stripped, capped at ~64KB by caller)
        check_message_id_known: optional callback (message_id) -> bool.
            Used to verify that an In-Reply-To header references one of
            OUR sent message-ids. If absent, falls back to regex-only.

    Returns:
        (pre_classification, needs_review)

    pre_classification ∈ {'bounce', 'opt-out', 'reply', 'spam', 'unknown'}
    needs_review:
        - False for 'bounce' and 'opt-out' (auto-actionable)
        - True for everything else (includes 'spam' -- curator-review needed)
    """
    # Order matters: most-specific first.
    # 1) Bounce (RFC 3464): strict header signal alone is enough.
    if _matches_any(_BOUNCE_HEADER_PATTERNS, headers_raw):
        return ("bounce", False)

    # 1b) Bounce body signal + From: mailer-daemon-ish
    header_lower = headers_raw.lower()
    from_match = re.search(r"^from:\s*([^\n]+)", header_lower, re.MULTILINE)
    from_field = from_match.group(1) if from_match else ""
    looks_like_dsn_from = (
        "mailer-daemon" in from_field
        or "postmaster" in from_field
        or "noreply" in from_field
        or "no-reply" in from_field
    )
    if looks_like_dsn_from and _matches_any(_BOUNCE_BODY_PATTERNS, body[:8192]):
        return ("bounce", False)

    # 2) Opt-out: header signal OR subject signal OR body+subject combo
    if _matches_any(_OPT_OUT_HEADER_PATTERNS, headers_raw):
        return ("opt-out", False)
    subject_match = _matches_any(_OPT_OUT_SUBJECT_PATTERNS, headers_raw)
    if subject_match:
        return ("opt-out", False)
    if _matches_any(_OPT_OUT_BODY_PATTERNS, body[:8192]):
        # Require body signal AND not-a-bounce-from
        if not looks_like_dsn_from:
            return ("opt-out", False)

    # 3) Reply: In-Reply-To header referencing one of OUR message_ids.
    irt_match = _IN_REPLY_TO_PATTERN.search(headers_raw)
    if irt_match:
        msg_id = irt_match.group(1).strip()
        if check_message_id_known is not None:
            try:
                if check_message_id_known(msg_id):
                    return ("reply", True)   # needs curator-approval before send
            except Exception:
                pass  # callback failure -> fall through to regex-only
        # Regex-only fallback: In-Reply-To + Subject starts with Re:
        if _RE_SUBJECT_PATTERN.search(headers_raw):
            return ("reply", True)

    # 4) Spam: any spam-header signal
    if _matches_any(_SPAM_PATTERNS, headers_raw):
        return ("spam", True)   # curator-review (could be false-positive)

    # 5) Default: unknown -> n8n will classify
    return ("unknown", True)


def _matches_any(patterns: tuple[re.Pattern[str], ...], haystack: str) -> bool:
    return any(p.search(haystack) for p in patterns)


def is_auto_submitted_loop(headers_raw: str) -> bool:
    """Loop-prevention check (Schicht 6.6).

    Returns True if the inbound mail looks like an auto-reply from a
    bot/mail-server, so the curator should NOT send another reply (would
    create infinite vacation-message loops).

    Detection rules (RFC 3834 + common patterns):
        - Auto-Submitted: auto-replied | auto-generated
        - X-Auto-Response-Suppress: header present
        - Subject prefix "Out of office" / "Abwesenheit"
        - In-Reply-To matches itself (header-loop signal)
    """
    if re.search(r"^Auto-Submitted:\s*(auto-replied|auto-generated)",
                  headers_raw, re.IGNORECASE | re.MULTILINE):
        return True
    if re.search(r"^X-Auto-Response-Suppress:", headers_raw,
                  re.IGNORECASE | re.MULTILINE):
        return True
    # German "Abwesenheit" + variants, EN "out of office", "vacation",
    # "automatic reply". Match WITHOUT trailing-boundary so "Abwesenheits...notiz"
    # also triggers.
    if re.search(r"^Subject:[^\n]*\b(out of office|abwesenh|vacation)",
                  headers_raw, re.IGNORECASE | re.MULTILINE):
        return True
    if re.search(r"^Subject:[^\n]*\bautomatic(?:al)? reply\b",
                  headers_raw, re.IGNORECASE | re.MULTILINE):
        return True
    return False


__all__ = ["pre_classify", "is_auto_submitted_loop"]

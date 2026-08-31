"""Open- + click-tracking primitives.

This module owns three concerns:
  1. Token sign/verify (HMAC-SHA256 with MARKETING_TRACKING_SECRET).
     Separate from MARKETING_PROPOSAL_API_KEY -- tracking tokens travel
     inside email bodies that recipients see, so the secret has a wider
     blast radius and we keep it isolated.
  2. Pixel injection (Schicht 5.1).
  3. Link rewrite (Schicht 5.2).

Token format:
    `<v>.<short_campaign>.<short_email_hash>.<short_hmac>`
where:
    v                = "o" (open) or "c" (click) — single char, lets us
                       route on token-prefix without parsing
    short_campaign   = first 8 chars of the campaign UUID (no dashes).
                       Enough entropy for 16M campaigns; collisions just
                       mean two ambiguous candidates and we pick the most
                       recent send for that email.
    short_email_hash = first 12 chars of SHA-256(email). Recipients can't
                       reverse this to other recipients' emails.
    short_hmac       = first 16 chars of HMAC-SHA256(secret, canonical).
                       64 bits is enough for tracking-pixel forgery
                       resistance (worst-case = false-open spam).

Canonical for HMAC:
    open:  f"o|{campaign_id}|{email}|{msgid_core or ''}"
    click: f"c|{campaign_id}|{email}|{url_hash}|{msgid_core or ''}"

The click variant binds the URL hash into the HMAC. If someone tampers
with the `u=` query-param redirecting to a phishing site, the HMAC no
longer verifies -> 404. This prevents the tracking domain from being
used as an open-redirect.

NEVER raises. Token-parse failures return None -- the caller (the
public-facing route) responds with 404, never a 5xx that would leak.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import urllib.parse
from typing import List, Optional, Tuple


logger = logging.getLogger("marketing.tracking")


# ─── Secret + base URL ────────────────────────────────────────────────


def _resolve_secret() -> Optional[bytes]:
    """Returns the tracking secret as bytes, or None if unset / too short."""
    s = os.environ.get("MARKETING_TRACKING_SECRET", "").strip()
    if not s or len(s) < 32:
        return None
    return s.encode("utf-8")


def _tracking_base_url() -> Optional[str]:
    """Returns the configured tracking base URL, or None if unset.

    The base URL is the prefix in front of /t/o/{token} and /t/c/{token}.
    Example: https://track.vibemind.space  (no trailing slash).
    """
    u = os.environ.get("MARKETING_TRACKING_BASE_URL", "").strip().rstrip("/")
    if not u:
        return None
    if not (u.startswith("http://") or u.startswith("https://")):
        return None
    return u


def is_tracking_configured() -> bool:
    """Cheap check used by the send-worker to decide whether to inject."""
    return _resolve_secret() is not None and _tracking_base_url() is not None


# ─── Token compute ────────────────────────────────────────────────────


def _short(s: str, n: int) -> str:
    return s[:n]


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _campaign_short(campaign_id: str) -> str:
    return _short(campaign_id.replace("-", ""), 8)


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def compute_open_token(campaign_id: str, email: str,
                        msgid_core: Optional[str] = None,
                        secret: Optional[bytes] = None) -> Optional[str]:
    """Build an open-tracking token. Returns None if secret unset."""
    if secret is None:
        secret = _resolve_secret()
    if secret is None:
        return None
    canonical = f"o|{campaign_id}|{email.strip().lower()}|{msgid_core or ''}"
    hmac_full = hmac.new(secret, canonical.encode("utf-8"),
                          hashlib.sha256).hexdigest()
    return (
        f"o.{_campaign_short(campaign_id)}."
        f"{_short(_email_hash(email), 12)}."
        f"{_short(hmac_full, 16)}"
    )


def compute_click_token(campaign_id: str, email: str, url: str,
                         msgid_core: Optional[str] = None,
                         secret: Optional[bytes] = None) -> Optional[str]:
    """Build a click-tracking token. Returns None if secret unset.

    URL is hashed and bound into the HMAC. Receiver verifies that the
    URL it's about to redirect to hashes to the same value -- otherwise
    refuse.
    """
    if secret is None:
        secret = _resolve_secret()
    if secret is None:
        return None
    canonical = f"c|{campaign_id}|{email.strip().lower()}|{_url_hash(url)}|{msgid_core or ''}"
    hmac_full = hmac.new(secret, canonical.encode("utf-8"),
                          hashlib.sha256).hexdigest()
    return (
        f"c.{_campaign_short(campaign_id)}."
        f"{_short(_email_hash(email), 12)}."
        f"{_short(hmac_full, 16)}"
    )


# ─── Token verify ─────────────────────────────────────────────────────


def parse_token(token: str) -> Optional[Tuple[str, str, str, str]]:
    """Split a token into (kind, campaign_short, email_hash_short, hmac_short).
    Returns None on malformed tokens. NEVER raises.
    """
    if not isinstance(token, str) or not token:
        return None
    parts = token.split(".")
    if len(parts) != 4:
        return None
    kind, camp, eh, hm = parts
    if kind not in ("o", "c"):
        return None
    if len(camp) != 8 or not all(c in "0123456789abcdef" for c in camp.lower()):
        return None
    if len(eh) != 12 or not all(c in "0123456789abcdef" for c in eh.lower()):
        return None
    if len(hm) != 16 or not all(c in "0123456789abcdef" for c in hm.lower()):
        return None
    return (kind, camp, eh, hm)


def verify_open_token(token: str, campaign_id: str, email: str,
                       msgid_core: Optional[str] = None,
                       secret: Optional[bytes] = None) -> bool:
    """Constant-time verify."""
    if secret is None:
        secret = _resolve_secret()
    if secret is None:
        return False
    expected = compute_open_token(campaign_id, email, msgid_core, secret=secret)
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


def verify_click_token(token: str, campaign_id: str, email: str, url: str,
                        msgid_core: Optional[str] = None,
                        secret: Optional[bytes] = None) -> bool:
    """Constant-time verify + URL-hash bound check."""
    if secret is None:
        secret = _resolve_secret()
    if secret is None:
        return False
    expected = compute_click_token(campaign_id, email, url, msgid_core, secret=secret)
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


# ─── Pixel injection (Schicht 5.1) ───────────────────────────────────


def build_open_pixel_tag(campaign_id: str, email: str,
                          msgid_core: Optional[str] = None) -> Optional[str]:
    """Return the literal HTML <img/> tag, or None if tracking is unset.

    Caller decides whether to append to body_html (we don't mutate the
    template in this helper). Tag is 1x1, transparent, role=presentation
    so screen-readers don't announce it.
    """
    base = _tracking_base_url()
    if base is None:
        return None
    token = compute_open_token(campaign_id, email, msgid_core)
    if token is None:
        return None
    src = f"{base}/t/o/{token}"
    return (f'<img src="{src}" width="1" height="1" alt="" '
            f'style="display:none;border:0;width:1px;height:1px;" '
            f'role="presentation"/>')


def inject_open_pixel(body_html: str, campaign_id: str, email: str,
                       msgid_core: Optional[str] = None) -> str:
    """Append the open-pixel tag to the end of body_html.

    Tries to insert just before </body> if present (so receivers that
    only render content inside <body> still fetch the pixel). If no
    </body>, appends at the very end -- still works for HTML fragments.

    If tracking is not configured OR body_html is empty, returns body_html
    unchanged. NEVER raises.
    """
    if not body_html:
        return body_html
    tag = build_open_pixel_tag(campaign_id, email, msgid_core)
    if tag is None:
        return body_html
    # Case-insensitive </body> replace, last occurrence wins
    matches = list(re.finditer(r"</body\s*>", body_html, flags=re.IGNORECASE))
    if matches:
        last = matches[-1]
        return body_html[:last.start()] + tag + body_html[last.start():]
    return body_html + tag


# ─── Link rewrite (Schicht 5.2 — stub here, full impl when 5.2 lands) ──


_LINK_REWRITE_SKIP_PREFIXES = (
    "mailto:", "tel:", "#", "javascript:", "sms:",
)


def rewrite_links(body_html: str, campaign_id: str, email: str,
                   msgid_core: Optional[str] = None,
                   *, skip_tracking_domain: bool = True) -> str:
    """Rewrite every http(s) <a href> in body_html to go through our
    click-tracker. Returns body_html unchanged if tracking is unset.

    Skipped:
      - mailto:, tel:, sms:, javascript:, anchors (#...), templates ({{x}})
      - URLs that already start with MARKETING_TRACKING_BASE_URL (idempotent
        re-render shouldn't double-wrap)

    NEVER raises. If a URL fails to encode, leaves the original href.
    """
    if not body_html:
        return body_html
    base = _tracking_base_url()
    secret = _resolve_secret()
    if base is None or secret is None:
        return body_html

    tracking_origin = base.rstrip("/")

    def _replace_href(match: re.Match) -> str:
        before = match.group("before")
        url = match.group("url")
        after = match.group("after")
        # Skip non-http schemes and template-merge placeholders
        if any(url.startswith(p) for p in _LINK_REWRITE_SKIP_PREFIXES):
            return match.group(0)
        if "{{" in url or "}}" in url:
            return match.group(0)
        if skip_tracking_domain and url.startswith(tracking_origin):
            return match.group(0)
        if not (url.startswith("http://") or url.startswith("https://")):
            return match.group(0)
        try:
            token = compute_click_token(campaign_id, email, url,
                                         msgid_core, secret=secret)
            if not token:
                return match.group(0)
            wrapped = f"{base}/t/c/{token}?u={urllib.parse.quote(url, safe='')}"
            return f'{before}{wrapped}{after}'
        except Exception:
            logger.debug("rewrite_links: failed for url=%r", url, exc_info=True)
            return match.group(0)

    pattern = re.compile(
        r"(?P<before>href\s*=\s*[\"'])"
        r"(?P<url>[^\"']+)"
        r"(?P<after>[\"'])",
        flags=re.IGNORECASE,
    )
    return pattern.sub(_replace_href, body_html)


# ─── 1x1 transparent GIF (used by /t/o/{token} route) ─────────────────


# 43-byte transparent GIF89a, 1x1. Hex-decoded once at import.
TRANSPARENT_GIF: bytes = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c"
    "00000000010001000002024401003b"
)
assert len(TRANSPARENT_GIF) == 43, "GIF blob has wrong size"


__all__ = [
    "is_tracking_configured",
    "compute_open_token",
    "verify_open_token",
    "compute_click_token",
    "verify_click_token",
    "parse_token",
    "build_open_pixel_tag",
    "inject_open_pixel",
    "rewrite_links",
    "TRANSPARENT_GIF",
]

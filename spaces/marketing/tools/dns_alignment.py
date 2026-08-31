"""DKIM / SPF / DMARC alignment pre-flight checks.

Read-only DNS lookups against the sender domain. NEVER opens SMTP,
NEVER reaches the recipient. Result is cached for 5 minutes per
(domain, selector) in-process so a tight send-batch doesn't hammer
the resolver.

The send-worker (gates 1-12) calls `check_sender_alignment(sender)`
right before opening the SMTP connection in LIVE mode. If any record
is missing AND `MARKETING_REQUIRE_DNS_ALIGNMENT=true`, ParanoidAbort.
Otherwise (default Phase-1 dev mode) a warning is logged + alignment
report stored in the campaign audit row, but the send proceeds. This
lets you see what's missing before flipping the strict gate on.

Rationale:
  - SPF missing => receivers can spoof "From: marketing@vibemind.space"
    OR receivers reject our legit mail as spam. Both kinds of bad.
  - DKIM missing => no cryptographic ownership proof of the sender
    domain on the message. Gmail rejects anything not DKIM-signed
    from "common" domains.
  - DMARC missing => no policy direction for receivers; mails treated
    as best-effort. With "p=quarantine" or "p=reject" we get telemetry
    (DMARC reports via the rua= mailbox).
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("marketing.dns_alignment")


# In-process cache: (key) -> (result, expires_at_epoch)
_CACHE: Dict[str, Tuple[Any, float]] = {}
_CACHE_TTL = 300.0   # 5 minutes


def _cache_get(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    result, expires = entry
    if expires < time.monotonic():
        _CACHE.pop(key, None)
        return None
    return result


def _cache_put(key: str, value: Any) -> None:
    _CACHE[key] = (value, time.monotonic() + _CACHE_TTL)


def _txt_records(domain: str, timeout_s: float = 3.0) -> Optional[List[str]]:
    """Look up TXT records for a domain.

    Returns None on transient DNS error (so caller can distinguish
    "definitively no record" (=[]) from "DNS broken" (=None)).
    Uses dnspython; returns None if not installed.
    """
    cache_key = f"txt:{domain}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import dns.resolver  # type: ignore
        import dns.exception  # type: ignore
    except ImportError:
        logger.warning("[dns_alignment] dnspython not available; cannot check %s", domain)
        return None

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout_s
        resolver.lifetime = timeout_s
        answers = resolver.resolve(domain, "TXT")
        records: List[str] = []
        for ans in answers:
            # Each TXT record is a sequence of byte-strings; concatenate.
            try:
                # dnspython newer API
                strings = [s.decode("utf-8", errors="replace") if isinstance(s, bytes) else str(s)
                           for s in ans.strings]
            except AttributeError:
                # Old API path
                strings = [str(ans)]
            records.append("".join(strings).strip().strip('"'))
        _cache_put(cache_key, records)
        return records
    except dns.resolver.NXDOMAIN:
        _cache_put(cache_key, [])
        return []
    except dns.resolver.NoAnswer:
        _cache_put(cache_key, [])
        return []
    except (dns.resolver.Timeout, dns.exception.DNSException) as e:
        logger.warning("[dns_alignment] TXT lookup failed for %s: %s", domain, e)
        return None


# ─── SPF ────────────────────────────────────────────────────────────────


def check_spf(domain: str) -> Dict[str, Any]:
    """Look up the SPF TXT record for the domain.

    Returns:
      {present: bool, record: str|None, mechanisms: [...], all_qualifier: str|None}

    `present=True` means an `v=spf1 ...` record was found. `mechanisms`
    is the list of tokens after `v=spf1`. `all_qualifier` is `+`, `~`,
    `-` or `?` -- the policy for unmatched IPs. `-all` is strict
    (reject), `~all` soft-fail (= flag as suspicious), `?all` neutral.
    """
    records = _txt_records(domain)
    if records is None:
        return {"present": None, "record": None, "error": "dns lookup failed"}
    spf_lines = [r for r in records if r.lower().startswith("v=spf1")]
    if not spf_lines:
        return {"present": False, "record": None,
                "mechanisms": [], "all_qualifier": None}
    if len(spf_lines) > 1:
        # RFC violation: only one v=spf1 allowed. Caller decides whether to abort.
        return {"present": True, "record": " | ".join(spf_lines),
                "mechanisms": [], "all_qualifier": None,
                "error": f"{len(spf_lines)} SPF records (RFC violation; only one allowed)"}
    record = spf_lines[0]
    tokens = record.split()[1:]   # drop v=spf1
    all_qual = None
    for tok in tokens:
        if tok in ("all", "+all", "-all", "~all", "?all"):
            all_qual = tok if tok.startswith(("+", "-", "~", "?")) else "+all"
            break
    return {"present": True, "record": record,
            "mechanisms": tokens, "all_qualifier": all_qual}


# ─── DKIM ───────────────────────────────────────────────────────────────


def check_dkim(domain: str, selectors: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check whether ANY of the common selectors yields a DKIM record.

    DKIM records live at `<selector>._domainkey.<domain>`. Common Mailcow
    selectors are `dkim`, `default`, `mail`. The send-worker passes the
    selector the running Mailcow is configured to use; we fall back to
    a small probe list when no explicit selector is configured.
    """
    if selectors is None:
        env_sel = os.environ.get("MARKETING_DKIM_SELECTOR", "").strip()
        if env_sel:
            selectors = [env_sel]
        else:
            selectors = ["dkim", "default", "mail", "selector1", "k1"]

    found_selectors: List[Dict[str, Any]] = []
    for sel in selectors:
        host = f"{sel}._domainkey.{domain}"
        records = _txt_records(host)
        if records is None:
            continue   # transient failure -- try next selector
        for r in records:
            if "v=dkim1" in r.lower() or r.startswith("k="):
                # Match relaxed: some implementations omit the v=DKIM1 prefix.
                found_selectors.append({
                    "selector": sel,
                    "host": host,
                    "record_preview": r[:80] + ("..." if len(r) > 80 else ""),
                })
                break
    return {
        "present": len(found_selectors) > 0,
        "found_selectors": found_selectors,
        "probed_selectors": selectors,
    }


# ─── DMARC ──────────────────────────────────────────────────────────────


def check_dmarc(domain: str) -> Dict[str, Any]:
    """Look up _dmarc.<domain> TXT.

    Returns {present, record, policy ('none'|'quarantine'|'reject'|None),
            sub_policy, percentage, rua, ruf}.
    """
    records = _txt_records(f"_dmarc.{domain}")
    if records is None:
        return {"present": None, "record": None, "error": "dns lookup failed"}
    dmarc_lines = [r for r in records if r.lower().startswith("v=dmarc1")]
    if not dmarc_lines:
        return {"present": False, "record": None,
                "policy": None, "sub_policy": None,
                "percentage": None, "rua": None, "ruf": None}
    record = dmarc_lines[0]
    # Parse k=v;k=v
    parts = {}
    for kv in record.split(";"):
        kv = kv.strip()
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        parts[k.strip().lower()] = v.strip()
    return {
        "present": True,
        "record": record,
        "policy": parts.get("p"),
        "sub_policy": parts.get("sp") or parts.get("p"),
        "percentage": parts.get("pct"),
        "rua": parts.get("rua"),
        "ruf": parts.get("ruf"),
    }


# ─── Aggregate alignment check ─────────────────────────────────────────


def check_sender_alignment(sender_email: str) -> Dict[str, Any]:
    """Full SPF/DKIM/DMARC pre-flight on a sender email's domain.

    Returns swarm-envelope shape. data carries the three sub-reports
    plus an aggregate `aligned` boolean: True iff SPF+DKIM+DMARC all
    present (regardless of strictness of policy).
    """
    if "@" not in sender_email:
        return {"success": False, "message": "invalid sender email",
                "data": None}
    domain = sender_email.rsplit("@", 1)[1].lower()

    spf = check_spf(domain)
    dkim = check_dkim(domain)
    dmarc = check_dmarc(domain)

    aligned = (
        spf.get("present") is True
        and dkim.get("present") is True
        and dmarc.get("present") is True
    )
    missing = []
    if spf.get("present") is False:
        missing.append("SPF")
    if dkim.get("present") is False:
        missing.append("DKIM")
    if dmarc.get("present") is False:
        missing.append("DMARC")

    msg = "all 3 DNS records present" if aligned else (
        f"missing: {', '.join(missing)}" if missing else "partial: DNS lookups failed"
    )
    return {
        "success": True,
        "message": msg,
        "data": {
            "domain": domain,
            "aligned": aligned,
            "missing": missing,
            "spf": spf,
            "dkim": dkim,
            "dmarc": dmarc,
        },
    }


def assert_alignment_or_abort(sender_email: str) -> Dict[str, Any]:
    """Used by the send-worker as gate 2.5 (after kill-switch + freeze,
    before campaign resolve). Raises ParanoidAbort if env-strict mode
    is on AND any record is missing. Always returns the report.
    """
    from ._send_paranoid import ParanoidAbort
    report = check_sender_alignment(sender_email)
    strict = os.environ.get("MARKETING_REQUIRE_DNS_ALIGNMENT", "").lower() in (
        "1", "true", "yes",
    )
    if strict and not report["data"]["aligned"]:
        raise ParanoidAbort(
            "dns_alignment",
            f"sender {sender_email!r}: {report['message']}. "
            f"Set MARKETING_REQUIRE_DNS_ALIGNMENT=false to bypass for "
            f"Phase-1 dev (records still logged).",
        )
    return report


__all__ = [
    "check_spf",
    "check_dkim",
    "check_dmarc",
    "check_sender_alignment",
    "assert_alignment_or_abort",
]

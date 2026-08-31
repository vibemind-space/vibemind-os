"""
Alert System
=============
Sends security alerts via Telegram, Slack, and Email.
Includes deduplication to prevent alert fatigue.

Nutzung:
  # Als Library (Import in andere Module)
  from alerter import send_alert
  await send_alert("CRITICAL", "Mimikatz detected", "PID 1234, User admin")

  # Standalone Test
  python alerter.py --test
  python alerter.py --test-telegram
  python alerter.py --test-slack
  python alerter.py --test-email
"""

import asyncio
import hashlib
import json
import smtplib
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    SLACK_WEBHOOK_URL,
    ALERT_EMAIL_TO, ALERT_EMAIL_FROM,
    ALERT_SMTP_HOST, ALERT_SMTP_PORT, ALERT_SMTP_USER, ALERT_SMTP_PASS,
    DEDUP_DB_PATH, DEDUP_WINDOW_SECONDS, MIN_SEVERITY,
)


SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
SEVERITY_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "⚪"}


# ================================================================
# DEDUPLICATION
# ================================================================

def _init_dedup_db():
    conn = sqlite3.connect(DEDUP_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_alerts (
            alert_hash TEXT PRIMARY KEY,
            first_sent REAL,
            last_sent REAL,
            count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


def _is_duplicate(alert_hash: str) -> bool:
    conn = _init_dedup_db()
    row = conn.execute(
        "SELECT last_sent FROM sent_alerts WHERE alert_hash = ?",
        (alert_hash,)
    ).fetchone()
    conn.close()

    if row is None:
        return False

    elapsed = time.time() - row[0]
    return elapsed < DEDUP_WINDOW_SECONDS


def _record_alert(alert_hash: str):
    conn = _init_dedup_db()
    now = time.time()
    conn.execute("""
        INSERT INTO sent_alerts (alert_hash, first_sent, last_sent, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(alert_hash) DO UPDATE SET
            last_sent = ?,
            count = count + 1
    """, (alert_hash, now, now, now))
    conn.commit()
    conn.close()


def _compute_hash(severity: str, title: str) -> str:
    return hashlib.sha256(f"{severity}:{title}".encode()).hexdigest()[:16]


# ================================================================
# TELEGRAM
# ================================================================

async def send_telegram(severity: str, title: str, details: str = "") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    emoji = SEVERITY_EMOJI.get(severity, "")
    text = f"{emoji} *{severity}: {title}*\n\n{details}\n\n_{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}_"

    # Truncate for Telegram (max 4096 chars)
    if len(text) > 4000:
        text = text[:3997] + "..."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=10)
        )
        return resp.status == 200
    except Exception as e:
        print(f"  [ALERT] Telegram error: {e}")
        return False


# ================================================================
# SLACK
# ================================================================

async def send_slack(severity: str, title: str, details: str = "") -> bool:
    if not SLACK_WEBHOOK_URL:
        return False

    emoji = SEVERITY_EMOJI.get(severity, "")
    color = {"CRITICAL": "#e74c3c", "HIGH": "#e67e22", "MEDIUM": "#f39c12", "LOW": "#3498db"}.get(severity, "#95a5a6")

    payload = json.dumps({
        "attachments": [{
            "color": color,
            "title": f"{emoji} {severity}: {title}",
            "text": details[:2000],
            "footer": f"OS Shield | {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        }]
    }).encode("utf-8")

    req = urllib.request.Request(SLACK_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"})

    try:
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=10)
        )
        return resp.status == 200
    except Exception as e:
        print(f"  [ALERT] Slack error: {e}")
        return False


# ================================================================
# EMAIL
# ================================================================

async def send_email(severity: str, title: str, details: str = "") -> bool:
    if not ALERT_EMAIL_TO or not ALERT_EMAIL_FROM:
        return False

    def _send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{severity}] {title}"
        msg["From"] = ALERT_EMAIL_FROM
        msg["To"] = ALERT_EMAIL_TO

        html = f"""
        <html><body>
        <h2 style="color: {'#e74c3c' if severity == 'CRITICAL' else '#e67e22'}">
            {severity}: {title}
        </h2>
        <pre>{details}</pre>
        <hr>
        <p style="color: #999;">OS Shield Alert | {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        try:
            server = smtplib.SMTP(ALERT_SMTP_HOST, ALERT_SMTP_PORT)
            server.starttls()
            if ALERT_SMTP_USER and ALERT_SMTP_PASS:
                server.login(ALERT_SMTP_USER, ALERT_SMTP_PASS)
            server.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"  [ALERT] Email error: {e}")
            return False

    return await asyncio.get_event_loop().run_in_executor(None, _send)


# ================================================================
# MAIN ALERT FUNCTION
# ================================================================

async def send_alert(
    severity: str,
    title: str,
    details: str = "",
    source: str = "OS Shield",
    skip_dedup: bool = False,
) -> dict:
    """
    Send a security alert to all configured channels.

    Args:
        severity: CRITICAL, HIGH, MEDIUM, LOW, INFO
        title: Short alert title
        details: Extended details
        source: Which tool generated the alert
        skip_dedup: Skip deduplication check

    Returns:
        dict with results per channel
    """
    result = {
        "severity": severity,
        "title": title,
        "sent": False,
        "channels": {},
        "deduplicated": False,
    }

    # Severity filter
    min_sev = SEVERITY_ORDER.get(MIN_SEVERITY, 1)
    alert_sev = SEVERITY_ORDER.get(severity, 4)
    if alert_sev > min_sev:
        result["channels"]["skipped"] = f"Below minimum severity ({MIN_SEVERITY})"
        return result

    # Deduplication
    if not skip_dedup:
        alert_hash = _compute_hash(severity, title)
        if _is_duplicate(alert_hash):
            result["deduplicated"] = True
            result["channels"]["skipped"] = "Duplicate alert (within dedup window)"
            return result
        _record_alert(alert_hash)

    details_with_source = f"Source: {source}\n\n{details}"

    # Send to all configured channels in parallel
    tasks = {}

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        tasks["telegram"] = send_telegram(severity, title, details_with_source)

    if SLACK_WEBHOOK_URL:
        tasks["slack"] = send_slack(severity, title, details_with_source)

    if ALERT_EMAIL_TO:
        tasks["email"] = send_email(severity, title, details_with_source)

    if tasks:
        results = await asyncio.gather(*tasks.values())
        for channel, success in zip(tasks.keys(), results):
            result["channels"][channel] = "sent" if success else "failed"
            if success:
                result["sent"] = True
    else:
        result["channels"]["none"] = "No alert channels configured"

    return result


async def send_alert_batch(findings: list, source: str = "OS Shield") -> list:
    """Send alerts for a list of findings (from any scanner)."""
    results = []
    for finding in findings:
        severity = finding.get("severity", "INFO")
        title = finding.get("title", "Unknown finding")
        details = finding.get("description", "") + "\n" + finding.get("detail", "")

        r = await send_alert(severity, title, details, source=source)
        results.append(r)

        if r["sent"]:
            print(f"  [ALERT] Sent: [{severity}] {title}")
        elif r["deduplicated"]:
            print(f"  [ALERT] Dedup: [{severity}] {title}")

    return results


# ================================================================
# CLI
# ================================================================

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Security Alert System")
    parser.add_argument("--test", action="store_true", help="Send test alert to all channels")
    parser.add_argument("--test-telegram", action="store_true", help="Test Telegram only")
    parser.add_argument("--test-slack", action="store_true", help="Test Slack only")
    parser.add_argument("--test-email", action="store_true", help="Test Email only")
    parser.add_argument("--stats", action="store_true", help="Show alert statistics")
    args = parser.parse_args()

    print("\n  SECURITY ALERT SYSTEM")
    print("  " + "=" * 40)

    # Show configured channels
    channels = []
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        channels.append("Telegram")
    if SLACK_WEBHOOK_URL:
        channels.append("Slack")
    if ALERT_EMAIL_TO:
        channels.append(f"Email ({ALERT_EMAIL_TO})")

    if channels:
        print(f"  Channels: {', '.join(channels)}")
    else:
        print("  WARNING: No alert channels configured!")
        print("  Add to .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        print("  Or: SLACK_WEBHOOK_URL")
        print("  Or: ALERT_EMAIL_TO, ALERT_EMAIL_FROM")

    print(f"  Min Severity: {MIN_SEVERITY}")
    print()

    if args.stats:
        conn = _init_dedup_db()
        rows = conn.execute(
            "SELECT alert_hash, first_sent, last_sent, count FROM sent_alerts ORDER BY last_sent DESC LIMIT 20"
        ).fetchall()
        conn.close()
        print(f"  Last 20 alerts:")
        for row in rows:
            dt = datetime.fromtimestamp(row[2]).strftime("%d.%m.%Y %H:%M")
            print(f"    {dt} | Count: {row[3]} | Hash: {row[0]}")
        return

    if args.test or args.test_telegram or args.test_slack or args.test_email:
        title = "Test Alert — OS Shield"
        details = "This is a test alert from the OS Shield Security Alert System.\nIf you see this, alerts are working!"

        if args.test or args.test_telegram:
            ok = await send_telegram("HIGH", title, details)
            print(f"  Telegram: {'OK' if ok else 'FAILED'}")

        if args.test or args.test_slack:
            ok = await send_slack("HIGH", title, details)
            print(f"  Slack: {'OK' if ok else 'FAILED'}")

        if args.test or args.test_email:
            ok = await send_email("HIGH", title, details)
            print(f"  Email: {'OK' if ok else 'FAILED'}")

        print()


if __name__ == "__main__":
    asyncio.run(main())

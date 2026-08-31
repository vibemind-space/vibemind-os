"""
Alerter Configuration
======================
Loads alert channel credentials from .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Slack
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# Email
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "")
ALERT_SMTP_HOST = os.environ.get("ALERT_SMTP_HOST", "smtp.gmail.com")
ALERT_SMTP_PORT = int(os.environ.get("ALERT_SMTP_PORT", "587"))
ALERT_SMTP_USER = os.environ.get("ALERT_SMTP_USER", "")
ALERT_SMTP_PASS = os.environ.get("ALERT_SMTP_PASS", "")

# Deduplication
DEDUP_DB_PATH = Path(__file__).parent / "alert_dedup.db"
DEDUP_WINDOW_SECONDS = 3600  # Same alert max 1x per hour

# Severity filter
MIN_SEVERITY = os.environ.get("ALERT_MIN_SEVERITY", "HIGH")  # CRITICAL, HIGH, MEDIUM, LOW, INFO

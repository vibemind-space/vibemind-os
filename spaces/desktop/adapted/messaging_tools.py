"""
Adapted Messaging Tools for Clawdbot Bridge

Routes messaging commands through the AutomationUIClient HTTP bridge
to the Automation_ui FastAPI backend's Clawdbot integration.

Replaces the deleted OpenClaw messaging tools.
"""

import logging

logger = logging.getLogger(__name__)


def send_whatsapp(recipient: str = None, message: str = None) -> str:
    """Send a WhatsApp message via Clawdbot."""
    return _send_message(recipient, message, "whatsapp")


def send_telegram(recipient: str = None, message: str = None) -> str:
    """Send a Telegram message via Clawdbot."""
    return _send_message(recipient, message, "telegram")


def send_message(recipient: str = None, message: str = None, platform: str = None) -> str:
    """Send a message via Clawdbot (auto-detect platform)."""
    return _send_message(recipient, message, platform)


def web_search(query: str = None) -> str:
    """Search the web via Clawdbot browser tools."""
    if not query:
        return "Fehler: Keine Suchanfrage angegeben."

    from spaces.desktop.automation_ui_client import get_automation_client
    client = get_automation_client()
    if not client.is_available():
        return "Web-Suche nicht verfuegbar. Automation_ui Backend laeuft nicht."

    try:
        result = client.llm_intent(f"Suche im Web nach: {query}")
        if result.get("success"):
            return result.get("summary", "Suche ausgefuehrt.")
        return f"Suche fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}"
    except Exception as e:
        logger.error("web_search error: %s", e)
        return f"Web-Suche Fehler: {e}"


def web_fetch(url: str = None) -> str:
    """Fetch and summarize a web page via Clawdbot browser."""
    if not url:
        return "Fehler: Keine URL angegeben."

    from spaces.desktop.automation_ui_client import get_automation_client
    client = get_automation_client()
    if not client.is_available():
        return "Web-Fetch nicht verfuegbar. Automation_ui Backend laeuft nicht."

    try:
        result = client.llm_intent(f"Oeffne die Seite {url} und fasse den Inhalt zusammen")
        if result.get("success"):
            return result.get("summary", "Seite abgerufen.")
        return f"Fetch fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}"
    except Exception as e:
        logger.error("web_fetch error: %s", e)
        return f"Web-Fetch Fehler: {e}"


def get_clawdbot_status() -> str:
    """Get the Clawdbot messaging gateway status."""
    from spaces.desktop.automation_ui_client import get_automation_client
    client = get_automation_client()
    if not client.is_available():
        return "Clawdbot nicht verfuegbar. Automation_ui Backend laeuft nicht."

    try:
        result = client.clawdbot_status()
        if result.get("success", True):
            return f"Clawdbot Status: verbunden. {result.get('message', '')}"
        return f"Clawdbot Status: {result.get('error', 'nicht verbunden')}"
    except Exception as e:
        logger.error("get_clawdbot_status error: %s", e)
        return f"Status-Abfrage Fehler: {e}"


def get_notifications() -> str:
    """Get pending notifications from messaging platforms."""
    from spaces.desktop.automation_ui_client import get_automation_client
    client = get_automation_client()
    if not client.is_available():
        return "Benachrichtigungen nicht verfuegbar. Automation_ui Backend laeuft nicht."

    try:
        result = client.clawdbot_status()
        sessions = result.get("sessions", [])
        if not sessions:
            return "Keine neuen Benachrichtigungen."
        return f"{len(sessions)} aktive Sessions: {sessions}"
    except Exception as e:
        logger.error("get_notifications error: %s", e)
        return f"Benachrichtigungen Fehler: {e}"


# --- Internal helper ---

def _send_message(recipient: str, message: str, platform: str = None) -> str:
    """Internal: send message via Clawdbot bridge."""
    if not recipient:
        return "Fehler: Kein Empfaenger angegeben."
    if not message:
        return "Fehler: Keine Nachricht angegeben."

    from spaces.desktop.automation_ui_client import get_automation_client
    client = get_automation_client()
    if not client.is_available():
        return "Messaging nicht verfuegbar. Automation_ui Backend laeuft nicht."

    try:
        result = client.clawdbot_send(recipient, message, platform or "whatsapp")
        if result.get("success", True):
            plat = platform or "default"
            return f"Nachricht an {recipient} gesendet ({plat})."
        return f"Nachricht fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}"
    except Exception as e:
        logger.error("_send_message error: %s", e)
        return f"Messaging Fehler: {e}"

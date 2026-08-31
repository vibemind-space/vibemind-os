"""
Roarboot Tools - Voice-controllable tools for Rowboat integration

Each tool wraps a RoarbootClient method and returns a
VibeMind-standard result dict with broadcast to Electron.
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _broadcast_to_electron(message: Dict[str, Any]):
    """Broadcast message to Electron UI."""
    try:
        print(json.dumps(message), flush=True)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")


def _broadcast_conversation_update(client, context: str):
    """Broadcast conversation URL to Electron for iframe sync."""
    conversations = client.list_conversations()
    conversation_id = conversations.get(context)
    if conversation_id and client.project_id:
        _broadcast_to_electron({
            "type": "roarboot_conversation_update",
            "conversation_id": conversation_id,
            "project_id": client.project_id,
            "context": context,
        })


def search_knowledge(query: str) -> Dict[str, Any]:
    """
    Search the Rowboat knowledge graph.

    Args:
        query: Search query

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.search: query='{query}'")
    client = get_roarboot_client()
    result = client.search_knowledge(query)

    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "search",
        "query": query,
        "result": result.get("response", ""),
    })
    _broadcast_conversation_update(client, "search")

    return {
        "success": result.get("success", False),
        "message": result.get("response", "No results."),
        "response_hint": result.get("response", "I couldn't find anything.")[:200],
    }


def query_knowledge(subject: str, question: str = None) -> Dict[str, Any]:
    """
    Query knowledge about a person, project, or topic.

    Args:
        subject: Subject to query about
        question: Optional specific question

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.query: subject='{subject}', question='{question}'")
    client = get_roarboot_client()
    result = client.query_knowledge(subject, question)

    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "query",
        "subject": subject,
        "result": result.get("response", ""),
    })
    _broadcast_conversation_update(client, "query")

    return {
        "success": result.get("success", False),
        "message": result.get("response", "No information found."),
        "response_hint": result.get("response", "I don't have information on that.")[:200],
    }


def draft_email(recipient: str, topic: str, context: str = "") -> Dict[str, Any]:
    """
    Draft an email using Rowboat's knowledge context.

    Args:
        recipient: Recipient name/email
        topic: Email topic
        context: Additional context

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.email_draft: to='{recipient}', topic='{topic}'")
    client = get_roarboot_client()
    result = client.draft_email(recipient, topic, context)

    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "email_draft",
        "recipient": recipient,
        "topic": topic,
        "result": result.get("response", ""),
    })
    _broadcast_conversation_update(client, "email")

    return {
        "success": result.get("success", False),
        "message": result.get("response", "Email draft could not be created."),
        "response_hint": f"I created an email draft to {recipient} about {topic}.",
    }


def generate_meeting_brief(meeting: str, participants: str = "") -> Dict[str, Any]:
    """
    Generate a meeting brief with relevant context.

    Args:
        meeting: Meeting description
        participants: Participant names

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.meeting_brief: meeting='{meeting}'")
    client = get_roarboot_client()
    result = client.generate_meeting_brief(meeting, participants)

    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "meeting_brief",
        "meeting": meeting,
        "result": result.get("response", ""),
    })
    _broadcast_conversation_update(client, "meeting")

    return {
        "success": result.get("success", False),
        "message": result.get("response", "Meeting brief could not be created."),
        "response_hint": f"I prepared a meeting brief for {meeting}.",
    }


def generate_deck(topic: str, context: str = "") -> Dict[str, Any]:
    """
    Generate a presentation deck outline.

    Args:
        topic: Presentation topic
        context: Additional context

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.deck: topic='{topic}'")
    client = get_roarboot_client()
    result = client.generate_deck(topic, context)

    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "deck",
        "topic": topic,
        "result": result.get("response", ""),
    })
    _broadcast_conversation_update(client, "deck")

    return {
        "success": result.get("success", False),
        "message": result.get("response", "Presentation could not be created."),
        "response_hint": f"I created a presentation about {topic}.",
    }


def process_voice_note(text: str) -> Dict[str, Any]:
    """
    Process a voice note and update the knowledge graph.

    Args:
        text: Voice note transcription

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.voice_note: text='{text[:50]}...'")
    client = get_roarboot_client()
    result = client.process_voice_note(text)

    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "voice_note",
        "result": result.get("response", ""),
    })
    _broadcast_conversation_update(client, "voice_note")

    return {
        "success": result.get("success", False),
        "message": result.get("response", "Note could not be processed."),
        "response_hint": "I processed your note and updated the knowledge graph.",
    }


def get_status() -> Dict[str, Any]:
    """
    Check Rowboat connection status.

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info("roarboot.status")
    client = get_roarboot_client()
    result = client.get_status()

    _broadcast_to_electron({
        "type": "roarboot_status",
        "status": result.get("status", "unknown"),
        "url": result.get("url", ""),
    })

    return {
        "success": result.get("success", False),
        "message": result.get("message", "Status unknown."),
        "response_hint": result.get("message", "Status unknown."),
    }


def open_webview(context: str = "default") -> Dict[str, Any]:
    """
    Signal Electron to show the Rowboat WebView.

    Opens the WebView navigated to the active conversation for the given
    context, or falls back to the base Rowboat URL if no conversation exists.

    Args:
        context: Conversation context key (e.g., "default", "search", "email")

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.open: context={context}")
    client = get_roarboot_client()
    status = client.get_status()
    base_url = status.get("url", "http://localhost:3000")

    # Build conversation-specific URL if available
    conversations = client.list_conversations()
    conversation_id = conversations.get(context)
    if conversation_id and client.project_id:
        url = f"{base_url}/projects/{client.project_id}/conversations/{conversation_id}"
    else:
        url = base_url

    _broadcast_to_electron({
        "type": "roarboot_open_webview",
        "url": url,
        "conversation_id": conversation_id,
    })

    if status.get("success"):
        return {
            "success": True,
            "message": "Rowboat WebView opened.",
            "response_hint": "Opening Rowboat for you.",
        }
    else:
        return {
            "success": False,
            "message": f"Rowboat not reachable: {status.get('message', '')}",
            "response_hint": "Rowboat is not reachable. Is the Docker container started?",
        }


def reset_conversation(context: str = None) -> Dict[str, Any]:
    """
    Reset Rowboat conversation context.

    Args:
        context: Specific context to reset (e.g., "search", "email"),
                 or None to reset all conversations

    Returns:
        VibeMind result dict
    """
    from .roarboot_client import get_roarboot_client

    logger.info(f"roarboot.reset: context={context}")
    client = get_roarboot_client()

    active_before = len(client.list_conversations())
    client.reset_conversation(context)
    active_after = len(client.list_conversations())

    if context:
        msg = f"Roarboot conversation '{context}' reset."
    else:
        msg = f"All Roarboot conversations reset ({active_before} -> {active_after})."

    return {
        "success": True,
        "message": msg,
        "response_hint": "New conversation with Roarboot started.",
    }


# =========================================================================
# High-Value Tools (roarboot.chat, roarboot.rag.search, roarboot.upload)
# =========================================================================

def chat(message: str, context: str = "general", **kwargs) -> Dict[str, Any]:
    """
    Free multi-turn chat with Rowboat — the core conversation interface.
    Rowboat responds with full knowledge graph context.

    Args:
        message: User message text
        context: Conversation context (default: "general")
    """
    from spaces.rowboat.tools.roarboot_client import get_roarboot_client
    client = get_roarboot_client()
    if not client:
        return {"success": False, "message": "Rowboat not configured", "response_hint": "Rowboat ist nicht konfiguriert."}

    result = client.chat(message, context=context)
    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "chat",
        "result": result,
    })
    _broadcast_conversation_update(client, context)
    return {
        **result,
        "response_hint": result.get("response", "Keine Antwort von Rowboat."),
    }


def rag_search(query: str, threshold: float = 0.7, limit: int = 5, **kwargs) -> Dict[str, Any]:
    """
    Semantic RAG search via Qdrant vector DB — finds conceptually similar content.

    Args:
        query: Semantic search query
        threshold: Minimum similarity score (0-1)
        limit: Max results to return
    """
    from spaces.rowboat.tools.roarboot_client import get_roarboot_client
    client = get_roarboot_client()
    if not client:
        return {"success": False, "message": "Rowboat not configured", "response_hint": "Rowboat ist nicht konfiguriert."}

    # Use chat with RAG-specific context to trigger vector search
    rag_prompt = f"Search the knowledge graph semantically for: {query}. Show the top {limit} most relevant results with similarity scores."
    result = client.chat(rag_prompt, context="rag_search")
    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "rag_search",
        "query": query,
        "result": result,
    })
    return {
        **result,
        "response_hint": result.get("response", f"Keine semantischen Treffer fuer '{query}'."),
    }


def upload_document(file_path: str = None, text: str = None, title: str = None, **kwargs) -> Dict[str, Any]:
    """
    Upload a document to Rowboat's knowledge graph for RAG indexing.
    Supports file path (PDF, DOCX, MD, TXT) or raw text.

    Args:
        file_path: Path to document file
        text: Raw text content (alternative to file_path)
        title: Optional title for the document
    """
    from spaces.rowboat.tools.roarboot_client import get_roarboot_client
    client = get_roarboot_client()
    if not client:
        return {"success": False, "message": "Rowboat not configured", "response_hint": "Rowboat ist nicht konfiguriert."}

    if not file_path and not text:
        return {"success": False, "message": "file_path or text required", "response_hint": "Bitte gib eine Datei oder Text an."}

    # If text provided, use chat to inject into knowledge graph
    if text:
        inject_prompt = f"Add this to the knowledge graph{f' (title: {title})' if title else ''}: {text}"
        result = client.chat(inject_prompt, context="upload")
        return {
            **result,
            "response_hint": result.get("response", "Dokument in Knowledge Graph aufgenommen."),
        }

    # If file path, attempt upload via Rowboat API
    try:
        import requests
        url = f"{client._url}/api/v1/{client._project_id}/upload"
        headers = {"Authorization": f"Bearer {client._api_key}"}
        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1].split("\\")[-1], f)}
            data = {}
            if title:
                data["title"] = title
            resp = requests.post(url, files=files, data=data, headers=headers, timeout=60)

        if resp.status_code == 200:
            result = resp.json()
            _broadcast_to_electron({
                "type": "roarboot_result",
                "action": "upload",
                "file_path": file_path,
                "result": result,
            })
            return {
                "success": True,
                "message": f"Document uploaded: {file_path}",
                "response_hint": f"Dokument '{file_path.split('/')[-1].split(chr(92))[-1]}' wurde in den Knowledge Graph aufgenommen.",
                **result,
            }
        else:
            return {"success": False, "message": f"Upload failed: HTTP {resp.status_code}", "response_hint": f"Upload fehlgeschlagen: HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return {"success": False, "message": str(e), "response_hint": f"Upload-Fehler: {e}"}


# =========================================================================
# Medium-Value Tools (roarboot.graph.explore, roarboot.tools.list)
# =========================================================================

def explore_graph(subject: str = None, **kwargs) -> Dict[str, Any]:
    """
    Explore knowledge graph connections for a subject.
    Shows relationships, linked notes, and context.

    Args:
        subject: Person, project, or topic to explore connections for
    """
    from spaces.rowboat.tools.roarboot_client import get_roarboot_client
    client = get_roarboot_client()
    if not client:
        return {"success": False, "message": "Rowboat not configured", "response_hint": "Rowboat ist nicht konfiguriert."}

    explore_prompt = f"Show me all connections and relationships for '{subject}' in the knowledge graph. Include linked notes, people, projects, and topics."
    result = client.chat(explore_prompt, context="graph_explore")
    _broadcast_to_electron({
        "type": "roarboot_result",
        "action": "graph_explore",
        "subject": subject,
        "result": result,
    })
    return {
        **result,
        "response_hint": result.get("response", f"Keine Verbindungen fuer '{subject}' gefunden."),
    }


def list_tools(**kwargs) -> Dict[str, Any]:
    """List all available Rowboat tools and integrations."""
    from spaces.rowboat.tools.roarboot_client import get_roarboot_client
    client = get_roarboot_client()
    if not client:
        return {"success": False, "message": "Rowboat not configured", "response_hint": "Rowboat ist nicht konfiguriert."}

    result = client.chat("List all available tools and integrations that I can use.", context="tools")
    return {
        **result,
        "response_hint": result.get("response", "Konnte Rowboat-Tools nicht abrufen."),
    }


__all__ = [
    "search_knowledge",
    "query_knowledge",
    "draft_email",
    "generate_meeting_brief",
    "generate_deck",
    "process_voice_note",
    "get_status",
    "open_webview",
    "reset_conversation",
    "chat",
    "rag_search",
    "upload_document",
    "explore_graph",
    "list_tools",
]

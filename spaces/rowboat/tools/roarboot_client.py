"""
Roarboot Client - Wrapper around Rowboat Python SDK

Provides VibeMind-compatible interface to communicate with
Rowboat's HTTP API running in Docker.

Supports two modes:
1. SDK mode: Uses rowboat Python SDK (if installed)
2. Direct HTTP mode: Falls back to raw requests (no SDK dependency)

Conversation Management:
- Per-context conversations (search, email, meeting, etc.)
- Persistent conversation IDs across turns
- Reset individual or all conversations
"""

import logging
import os
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class RoarbootClient:
    """
    Client for communicating with Rowboat API.

    Uses the Rowboat Python SDK for stateless chat turns
    with fallback to direct HTTP calls if SDK is not installed.
    """

    def __init__(self, url: str = None, api_key: str = None, project_id: str = None):
        self._url = url or os.getenv("ROWBOAT_URL", "http://localhost:3000")
        self._api_key = api_key or os.getenv("ROWBOAT_API_KEY", "")
        self._project_id = project_id or os.getenv("ROWBOAT_PROJECT_ID", "")
        self._sdk_client = None
        self._sdk_available = None  # None = not checked yet

        # Per-context conversation tracking
        self._conversations: Dict[str, str] = {}  # context_key -> conversation_id

    @property
    def project_id(self) -> str:
        """Expose project ID for URL construction."""
        return self._project_id

    # -------------------------------------------------------------------------
    # SDK Client (lazy-loaded)
    # -------------------------------------------------------------------------

    def _check_sdk(self) -> bool:
        """Check if Rowboat SDK is available."""
        if self._sdk_available is None:
            try:
                from rowboat.client import Client
                from rowboat.schema import UserMessage
                self._sdk_available = True
                logger.info("RoarbootClient: Rowboat SDK available")
            except ImportError:
                self._sdk_available = False
                logger.info("RoarbootClient: Rowboat SDK not installed, using direct HTTP")
        return self._sdk_available

    def _get_sdk_client(self):
        """Lazy-load Rowboat SDK client."""
        if self._sdk_client is None:
            from rowboat.client import Client
            self._sdk_client = Client(
                host=self._url,
                projectId=self._project_id,
                apiKey=self._api_key,
            )
            logger.info(f"RoarbootClient: SDK client connected to {self._url}")
        return self._sdk_client

    # -------------------------------------------------------------------------
    # Core Chat (SDK + Direct HTTP fallback)
    # -------------------------------------------------------------------------

    def chat(self, message: str, context: str = "default") -> Dict[str, Any]:
        """
        Send a chat message to Rowboat and get a response.

        Supports per-context conversations for independent threads.

        Args:
            message: User message text
            context: Conversation context key (e.g., "search", "email", "meeting")

        Returns:
            Dict with response text, conversation_id, and success status
        """
        conversation_id = self._conversations.get(context)

        if self._check_sdk():
            return self._chat_via_sdk(message, context, conversation_id)
        else:
            return self._chat_via_http(message, context, conversation_id)

    def _chat_via_sdk(self, message: str, context: str, conversation_id: Optional[str]) -> Dict[str, Any]:
        """Chat using the Rowboat Python SDK."""
        try:
            from rowboat.schema import UserMessage

            client = self._get_sdk_client()
            response = client.run_turn(
                messages=[UserMessage(role="user", content=message)],
                conversationId=conversation_id,
            )

            # Update conversation ID for this context
            if hasattr(response, "conversationId") and response.conversationId:
                self._conversations[context] = response.conversationId

            # Extract response text from turn output
            response_text = self._extract_response_text(response)

            return {
                "success": True,
                "response": response_text,
                "conversation_id": self._conversations.get(context),
                "context": context,
            }

        except Exception as e:
            logger.error(f"RoarbootClient: SDK chat error: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": f"Rowboat-Fehler: {e}",
            }

    def _chat_via_http(self, message: str, context: str, conversation_id: Optional[str]) -> Dict[str, Any]:
        """Chat using direct HTTP calls (no SDK dependency)."""
        try:
            url = f"{self._url}/api/v1/{self._project_id}/chat"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            }
            payload = {
                "messages": [{"role": "user", "content": message}],
            }
            if conversation_id:
                payload["conversationId"] = conversation_id

            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text}",
                    "response": f"Rowboat API Fehler: HTTP {resp.status_code}",
                }

            data = resp.json()

            # Update conversation ID
            if data.get("conversationId"):
                self._conversations[context] = data["conversationId"]

            # Extract response text from turn output
            response_text = ""
            turn = data.get("turn", {})
            output = turn.get("output", [])
            for msg in reversed(output):
                if msg.get("role") == "assistant" and msg.get("content"):
                    response_text = msg["content"]
                    break

            return {
                "success": True,
                "response": response_text,
                "conversation_id": self._conversations.get(context),
                "context": context,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "Connection refused",
                "response": "Rowboat nicht erreichbar. Ist der Docker-Container gestartet?",
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Timeout",
                "response": "Rowboat antwortet nicht (Timeout).",
            }
        except Exception as e:
            logger.error(f"RoarbootClient: HTTP chat error: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": f"Rowboat-Fehler: {e}",
            }

    def _extract_response_text(self, response) -> str:
        """Extract the assistant's response text from SDK ApiResponse."""
        try:
            if hasattr(response, "turn") and hasattr(response.turn, "output"):
                # Walk output in reverse to find the last assistant message
                for msg in reversed(response.turn.output):
                    if hasattr(msg, "role") and msg.role == "assistant":
                        if hasattr(msg, "content") and msg.content:
                            return msg.content
            return ""
        except Exception as e:
            logger.warning(f"RoarbootClient: Could not extract response: {e}")
            return ""

    # -------------------------------------------------------------------------
    # Knowledge Graph Operations
    # -------------------------------------------------------------------------

    def search_knowledge(self, query: str) -> Dict[str, Any]:
        """Search the Rowboat knowledge graph."""
        return self.chat(
            f"Search my knowledge graph for: {query}",
            context="search",
        )

    def query_knowledge(self, subject: str, question: str = None) -> Dict[str, Any]:
        """Query knowledge about a subject (person, project, etc.)."""
        if question:
            prompt = f"What do I know about {subject}? Specifically: {question}"
        else:
            prompt = (
                f"Tell me everything I know about {subject}. "
                "Include related people, projects, decisions, and open items."
            )
        return self.chat(prompt, context="query")

    # -------------------------------------------------------------------------
    # Content Generation
    # -------------------------------------------------------------------------

    def draft_email(self, recipient: str, topic: str, context: str = "") -> Dict[str, Any]:
        """Draft an email using Rowboat's knowledge context."""
        prompt = f"Draft an email to {recipient} about {topic}."
        if context:
            prompt += f" Context: {context}"
        prompt += " Use relevant knowledge from past interactions."
        return self.chat(prompt, context="email")

    def generate_meeting_brief(self, meeting: str, participants: str = "") -> Dict[str, Any]:
        """Generate a meeting brief with relevant context."""
        prompt = f"Prepare a meeting brief for: {meeting}."
        if participants:
            prompt += f" Participants: {participants}."
        prompt += " Include past decisions, open questions, and relevant context."
        return self.chat(prompt, context="meeting")

    def generate_deck(self, topic: str, context: str = "") -> Dict[str, Any]:
        """Generate a presentation deck outline."""
        prompt = f"Create a presentation deck about {topic}."
        if context:
            prompt += f" Context: {context}"
        prompt += " Use knowledge from my work history."
        return self.chat(prompt, context="deck")

    def process_voice_note(self, text: str) -> Dict[str, Any]:
        """Process a voice note and update the knowledge graph."""
        return self.chat(
            f"Process this voice note and update relevant knowledge: {text}",
            context="voice_note",
        )

    # -------------------------------------------------------------------------
    # System Operations
    # -------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Check Rowboat connection status.

        Uses HEAD request to root URL to check if the Next.js server is up.
        Rowboat has no dedicated /api/health endpoint, so any 2xx/3xx response
        from the server indicates it's running.
        """
        try:
            resp = requests.head(self._url, timeout=5, allow_redirects=True)
            if resp.status_code < 400:
                return {
                    "success": True,
                    "status": "connected",
                    "url": self._url,
                    "sdk_available": self._check_sdk(),
                    "active_conversations": len(self._conversations),
                    "message": "Rowboat ist verbunden und bereit.",
                }
            else:
                return {
                    "success": False,
                    "status": "error",
                    "url": self._url,
                    "message": f"Rowboat antwortet mit Status {resp.status_code}",
                }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "status": "disconnected",
                "url": self._url,
                "message": "Rowboat nicht erreichbar. Docker-Container gestartet?",
            }
        except Exception as e:
            return {
                "success": False,
                "status": "disconnected",
                "url": self._url,
                "message": f"Rowboat nicht erreichbar: {e}",
            }

    # -------------------------------------------------------------------------
    # Conversation Management
    # -------------------------------------------------------------------------

    def reset_conversation(self, context: str = None):
        """
        Reset conversation context.

        Args:
            context: Specific context to reset, or None for all
        """
        if context:
            if context in self._conversations:
                del self._conversations[context]
                logger.info(f"RoarbootClient: Conversation '{context}' reset")
        else:
            self._conversations.clear()
            logger.info("RoarbootClient: All conversations reset")

    def list_conversations(self) -> Dict[str, str]:
        """List active conversation contexts and their IDs."""
        return dict(self._conversations)


# Singleton
_client: Optional[RoarbootClient] = None


def get_roarboot_client() -> RoarbootClient:
    """Get or create RoarbootClient singleton."""
    global _client
    if _client is None:
        _client = RoarbootClient()
    return _client


__all__ = ["RoarbootClient", "get_roarboot_client"]

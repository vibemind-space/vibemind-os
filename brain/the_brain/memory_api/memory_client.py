"""
Memory API Client

Simple REST client for the Tahlamus brain to call the Memory API service.
This replaces direct Supermemory integration with clean API calls.

Usage:
    from memory_api.memory_client import MemoryClient

    client = MemoryClient(base_url="http://localhost:8001")

    # Store execution memory
    client.store_execution(
        task="Deploy Docker container",
        result="SUCCESS",
        confidence=0.95,
        session_log="Step 1: docker build...",
        agent_name="deployment_agent"
    )

    # Query for planning
    context = client.get_planning_context("Deploy Docker container")
"""

import requests
from typing import List, Dict, Optional, Any


class MemoryClient:
    """Client for Tahlamus Memory API service."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        """
        Initialize memory client.

        Args:
            base_url: Base URL of Memory API service
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

    def health_check(self) -> bool:
        """Check if memory service is available."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except (requests.RequestException, ConnectionError, OSError):
            return False

    def store_memory(
        self,
        content: str,
        memory_type: str = "general",
        title: str = "Untitled",
        description: str = "",
        url: str = None,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
        user_id: str = None
    ) -> Dict:
        """Store a general memory."""
        data = {
            "content": content,
            "memory_type": memory_type,
            "title": title,
            "description": description,
            "url": url,
            "tags": tags or [],
            "metadata": metadata,
            "user_id": user_id
        }

        response = self.session.post(f"{self.base_url}/memories", json=data)
        response.raise_for_status()
        return response.json()

    def store_visual(
        self,
        window_title: str,
        screen_data: Dict,
        ocr_text: str = None,
        visible_files: List[str] = None,
        user_id: str = None
    ) -> Dict:
        """Store a visual memory."""
        data = {
            "window_title": window_title,
            "screen_data": screen_data,
            "ocr_text": ocr_text,
            "visible_files": visible_files or [],
            "user_id": user_id
        }

        response = self.session.post(f"{self.base_url}/memories/visual", json=data)
        response.raise_for_status()
        return response.json()

    def store_execution(
        self,
        task: str,
        result: str,
        confidence: float,
        session_log: str = None,
        agent_name: str = None,
        duration_ms: int = None,
        user_id: str = None
    ) -> Dict:
        """Store an execution memory."""
        data = {
            "task": task,
            "result": result,
            "confidence": confidence,
            "session_log": session_log,
            "agent_name": agent_name,
            "duration_ms": duration_ms,
            "user_id": user_id
        }

        response = self.session.post(f"{self.base_url}/memories/execution", json=data)
        response.raise_for_status()
        return response.json()

    def store_chat(
        self,
        messages: List[Dict[str, str]],
        topics: List[str] = None,
        planning_triggered: bool = False,
        user_id: str = None
    ) -> Dict:
        """Store a chat memory."""
        data = {
            "messages": messages,
            "topics": topics or [],
            "planning_triggered": planning_triggered,
            "user_id": user_id
        }

        response = self.session.post(f"{self.base_url}/memories/chat", json=data)
        response.raise_for_status()
        return response.json()

    def query_memories(
        self,
        query: str = None,
        memory_type: str = None,
        tags: List[str] = None,
        limit: int = 10,
        include_content: bool = True,
        user_id: str = None
    ) -> Dict:
        """Query memories with filters."""
        data = {
            "query": query,
            "memory_type": memory_type,
            "tags": tags or [],
            "limit": limit,
            "include_content": include_content,
            "user_id": user_id
        }

        response = self.session.post(f"{self.base_url}/memories/query", json=data)
        response.raise_for_status()
        return response.json()

    def get_by_tag(
        self,
        tag: str,
        limit: int = 10,
        include_content: bool = True
    ) -> Dict:
        """Get memories by tag."""
        params = {
            "limit": limit,
            "include_content": include_content
        }

        response = self.session.get(
            f"{self.base_url}/memories/by-tag/{tag}",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def get_planning_context(
        self,
        task: str,
        user_id: str = None,
        include_visual: bool = True,
        include_execution: bool = True,
        include_chat: bool = True
    ) -> Dict:
        """
        Get memory context for planning.

        This is the main method the brain uses to retrieve relevant
        memories before planning a task.
        """
        params = {
            "task": task,
            "user_id": user_id,
            "include_visual": include_visual,
            "include_execution": include_execution,
            "include_chat": include_chat
        }

        response = self.session.post(f"{self.base_url}/planning/context", params=params)
        response.raise_for_status()
        return response.json()


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("MEMORY API CLIENT TEST")
    print("=" * 70)
    print()

    client = MemoryClient()

    # Check health
    print("[1] Checking memory service health...")
    if client.health_check():
        print("  [OK] Memory service is running")
    else:
        print("  [ERROR] Memory service is not available")
        print("  Start it with: python memory_api/memory_service.py")
        exit(1)

    # Store execution memory
    print("\n[2] Storing execution memory...")
    result = client.store_execution(
        task="Deploy Docker container to production",
        result="SUCCESS",
        confidence=0.95,
        session_log="Step 1: docker build\nStep 2: docker run\nStep 3: health check",
        agent_name="deployment_agent",
        duration_ms=5400
    )
    print(f"  [OK] Stored: {result}")

    # Store chat memory
    print("\n[3] Storing chat memory...")
    result = client.store_chat(
        messages=[
            {"role": "user", "content": "How do I deploy a Docker container?"},
            {"role": "assistant", "content": "I can help you deploy a container..."}
        ],
        topics=["docker", "deployment"],
        planning_triggered=True
    )
    print(f"  [OK] Stored: {result}")

    # Query for planning
    print("\n[4] Getting planning context...")
    context = client.get_planning_context("Deploy Docker container")
    print(f"  [OK] Retrieved {context['memories']['total_memories']} memories")
    print(f"      - Execution memories: {len(context['memories']['execution_memories'])}")
    print(f"      - Chat memories: {len(context['memories']['chat_memories'])}")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETE")
    print("=" * 70)

"""
Supermemory API Client

Python wrapper for the Supermemory REST API (https://supermemory.ai).
Provides methods for storing and retrieving memories for AI systems.

Features:
- Add memories (visual, execution, chat)
- Search memories semantically
- Query by type, space, or filters
- Connection testing

Environment Variables:
- SUPERMEMORY_API_KEY: Your Supermemory API key from console.supermemory.ai
- SUPERMEMORY_BASE_URL: API base URL (default: https://v2.api.supermemory.ai)
"""

import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
import requests


class SupermemoryClient:
    """
    Client for Supermemory API.

    The Supermemory API allows storing and retrieving contextual memories
    for AI systems. Memories are stored with semantic embeddings for
    intelligent retrieval.
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None
    ):
        """
        Initialize Supermemory client.

        Args:
            api_key: Supermemory API key (or from env var SUPERMEMORY_API_KEY)
            base_url: API base URL (or from env var SUPERMEMORY_BASE_URL,
                     default: https://v2.api.supermemory.ai)
        """
        self.api_key = api_key or os.getenv('SUPERMEMORY_API_KEY')
        self.base_url = base_url or os.getenv(
            'SUPERMEMORY_BASE_URL',
            'https://api.supermemory.ai'  # V3 API base URL
        )

        if not self.api_key:
            raise ValueError(
                "Supermemory API key not provided. "
                "Set SUPERMEMORY_API_KEY environment variable "
                "or pass api_key to constructor. "
                "Get your API key from https://console.supermemory.ai"
            )

        # Remove trailing slash from base URL
        self.base_url = self.base_url.rstrip('/')

        # Request headers for V3 API (Bearer token)
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict:
        """
        Make HTTP request to Supermemory API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON as dict

        Raises:
            Exception if request fails
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_msg = f"Supermemory API error: {e}"
            if response.text:
                error_msg += f"\nResponse: {response.text}"
            raise Exception(error_msg)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Supermemory API request failed: {e}")

    def add_memory(
        self,
        page_content: str,
        url: str = None,
        memory_type: str = "page",
        title: str = "Untitled",
        description: str = "",
        og_image: str = None,
        image: str = None,
        spaces: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict:
        """
        Add a memory to Supermemory v3 API.

        Args:
            page_content: Main content to remember
            url: URL reference (optional, can be custom URI like tahlamus://...)
            memory_type: Type of memory (page, note, execution_log, etc.)
            title: Memory title
            description: Brief description
            og_image: OpenGraph image URL
            image: Image URL
            spaces: List of categories/tags
            metadata: Additional metadata (will be JSON stringified and included)

        Returns:
            API response dict
        """
        # v3 API uses structured format
        # Format content with title and type
        content_parts = []

        # Add title and type at the beginning
        if title != "Untitled":
            content_parts.append(f"# {title}")
        if memory_type:
            content_parts.append(f"Type: {memory_type}")

        # Add main content
        content_parts.append(f"\n{page_content}")

        # Add description
        if description:
            content_parts.append(f"\nDescription: {description}")

        # Combine into single content string
        full_content = '\n'.join(content_parts)

        # Build metadata dict (v3 API only accepts primitive types)
        api_metadata = {}
        if memory_type:
            api_metadata['type'] = memory_type
        if url:
            api_metadata['url'] = url
        if og_image:
            api_metadata['og_image'] = og_image
        if image:
            api_metadata['image'] = image

        # Flatten nested metadata - convert objects to strings
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (dict, list)):
                    # JSON-stringify complex types
                    api_metadata[f'meta_{key}'] = json.dumps(value)
                elif isinstance(value, (str, int, float, bool)):
                    # Keep primitives as-is
                    api_metadata[f'meta_{key}'] = value
                else:
                    # Convert other types to string
                    api_metadata[f'meta_{key}'] = str(value)

        # Build containerTags from spaces
        container_tags = spaces or []

        # v3 API schema
        data = {
            'content': full_content,
            'metadata': api_metadata,
            'containerTags': container_tags
        }

        # Add custom ID if URL provided (use URL as unique ID)
        if url:
            data['customId'] = url

        return self._make_request('POST', '/v3/documents', data=data)

    def add_visual_memory(
        self,
        screen_data: Dict,
        window_title: str = None,
        ocr_text: str = None,
        visible_files: List[str] = None
    ) -> Dict:
        """
        Add a visual memory from screen/desktop data.

        Args:
            screen_data: Screen data dict (from Supabase or screen capture)
            window_title: Active window title
            ocr_text: OCR extracted text from screen
            visible_files: List of visible file paths

        Returns:
            API response dict
        """
        # Extract key information
        window_title = window_title or screen_data.get('window_title', 'Unknown')
        ocr_text = ocr_text or screen_data.get('ocr_text', '')
        captured_at = screen_data.get('captured_at', int(datetime.now().timestamp() * 1000))

        # Build content
        content_parts = [f"Window: {window_title}"]
        if visible_files:
            content_parts.append(f"Files: {', '.join(visible_files[:5])}")
        if ocr_text:
            content_parts.append(f"Screen Text: {ocr_text[:500]}...")

        page_content = '\n'.join(content_parts)

        # Generate URL
        timestamp = datetime.fromtimestamp(captured_at / 1000).isoformat()
        url = f"tahlamus://visual/{timestamp}"

        # Metadata
        metadata = {
            'captured_at': captured_at,
            'window_title': window_title,
            'has_ocr': bool(ocr_text),
            'visible_files': visible_files or [],
            'screen_data': screen_data
        }

        return self.add_memory(
            page_content=page_content,
            url=url,
            memory_type='visual_context',
            title=f"Screen - {window_title}",
            description=f"Visual context captured at {timestamp}",
            spaces=['visual', 'screen_capture'],
            metadata=metadata
        )

    def add_execution_memory(
        self,
        task: str,
        result: str,
        confidence: float,
        session_log: str = None,
        agent_name: str = None,
        duration_ms: int = None
    ) -> Dict:
        """
        Add an execution memory from agent task completion.

        Args:
            task: Task description
            result: Execution result (SUCCESS, FAILURE, etc.)
            confidence: Agent confidence score (0.0 to 1.0)
            session_log: Full session logs
            agent_name: Name of executing agent
            duration_ms: Execution duration in milliseconds

        Returns:
            API response dict
        """
        timestamp = datetime.now().isoformat()
        session_id = f"session-{int(datetime.now().timestamp())}"

        # Build content
        content_parts = [
            f"Task: {task}",
            f"Result: {result}",
            f"Confidence: {confidence:.2%}",
        ]
        if agent_name:
            content_parts.append(f"Agent: {agent_name}")
        if duration_ms:
            content_parts.append(f"Duration: {duration_ms}ms")
        if session_log:
            content_parts.append(f"\nLogs:\n{session_log[:1000]}...")

        page_content = '\n'.join(content_parts)

        # URL
        url = f"tahlamus://execution/{session_id}"

        # Metadata
        metadata = {
            'task': task,
            'result': result,
            'confidence': confidence,
            'agent_name': agent_name,
            'duration_ms': duration_ms,
            'timestamp': timestamp,
            'session_id': session_id
        }

        # Spaces
        spaces = ['execution', 'agent']
        if result.lower() == 'success':
            spaces.append('success')
        else:
            spaces.append('failure')

        return self.add_memory(
            page_content=page_content,
            url=url,
            memory_type='agent_execution',
            title=f"{result} - {task[:50]}",
            description=f"Agent {result.lower()} with {confidence:.1%} confidence",
            spaces=spaces,
            metadata=metadata
        )

    def add_chat_memory(
        self,
        messages: List[Dict[str, str]],
        topics: List[str] = None,
        planning_triggered: bool = False
    ) -> Dict:
        """
        Add a chat memory from conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            topics: List of conversation topics
            planning_triggered: Whether planning was triggered

        Returns:
            API response dict
        """
        timestamp = datetime.now().isoformat()

        # Build content from messages
        content_lines = []
        for msg in messages:
            role = msg.get('role', 'unknown').capitalize()
            content = msg.get('content', '')
            content_lines.append(f"{role}: {content}")

        page_content = '\n'.join(content_lines)

        # URL
        url = f"tahlamus://chat/{timestamp}"

        # Extract title from first user message
        first_user_msg = next((m for m in messages if m.get('role') == 'user'), None)
        title = "Chat"
        if first_user_msg:
            first_content = first_user_msg.get('content', '')
            title = f"Chat - {first_content[:50]}..."

        # Metadata
        metadata = {
            'message_count': len(messages),
            'topics': topics or [],
            'planning_triggered': planning_triggered,
            'timestamp': timestamp
        }

        # Spaces
        spaces = ['chat', 'conversation']
        if topics:
            spaces.extend(topics[:3])  # Add up to 3 topics as spaces

        return self.add_memory(
            page_content=page_content,
            url=url,
            memory_type='conversation',
            title=title,
            description=f"Conversation with {len(messages)} messages",
            spaces=spaces,
            metadata=metadata
        )

    def search(
        self,
        query: str = None,
        memory_type: str = None,
        spaces: List[str] = None,
        limit: int = 10,
        include_content: bool = True
    ) -> List[Dict]:
        """
        Search/list memories using V3 API.

        Args:
            query: Search query text (not used for filtering yet, V3 doesn't have semantic search)
            memory_type: Filter by memory type in metadata
            spaces: Filter by containerTags
            limit: Maximum results to return
            include_content: Include full document content in response

        Returns:
            List of memory dicts
        """
        # Build filters
        filters = None
        if memory_type:
            filters = {
                'AND': [{
                    'filterType': 'metadata',
                    'key': 'type',
                    'value': memory_type
                }]
            }

        # Build request body for V3 list endpoint
        data = {
            'limit': limit,
            'page': 1,
            'includeContent': include_content
        }

        if spaces:
            data['containerTags'] = spaces

        if filters:
            data['filters'] = filters

        try:
            response = self._make_request('POST', '/v3/documents/list', data=data)
            # Return the memories array from response
            return response.get('memories', [])
        except Exception as e:
            print(f"[SupermemoryClient] List query failed: {e}")
            return []

    def get_memories(
        self,
        memory_type: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get recent memories.

        Args:
            memory_type: Filter by type
            limit: Maximum results

        Returns:
            List of memory dicts
        """
        params = {'limit': limit}
        if memory_type:
            params['type'] = memory_type

        try:
            return self._make_request('GET', '/memories', params=params)
        except Exception as e:
            print(f"[SupermemoryClient] Get memories failed: {e}")
            return []

    def get_by_space(
        self,
        space: str,
        limit: int = 10,
        include_content: bool = True
    ) -> List[Dict]:
        """
        Get memories by space/tag (containerTag).

        Args:
            space: Space/tag name
            limit: Maximum results
            include_content: Include full document content

        Returns:
            List of memory dicts
        """
        data = {
            'containerTags': [space],
            'limit': limit,
            'page': 1,
            'includeContent': include_content
        }

        try:
            response = self._make_request('POST', '/v3/documents/list', data=data)
            return response.get('memories', [])
        except Exception as e:
            print(f"[SupermemoryClient] Get by space failed: {e}")
            return []

    def test_connection(self) -> bool:
        """
        Test connection to Supermemory API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to add a test memory
            test_memory = self.add_memory(
                page_content="Connection test",
                url="tahlamus://test/connection",
                memory_type="test",
                title="Connection Test",
                description="Testing Supermemory API connection",
                spaces=['test']
            )
            print(f"[SupermemoryClient] Connection test successful!")
            print(f"  API Base URL: {self.base_url}")
            print(f"  Test memory created: {test_memory}")
            return True
        except Exception as e:
            print(f"[SupermemoryClient] Connection test failed: {e}")
            print(f"  API Base URL: {self.base_url}")
            print(f"  Make sure you have a valid API key from console.supermemory.ai")
            return False


# Example usage
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from load_env import load_env_file

    # Load .env file
    load_env_file()

    # Test with API key from environment
    api_key = os.getenv('SUPERMEMORY_API_KEY')

    if not api_key:
        print("ERROR: SUPERMEMORY_API_KEY not set in .env file")
        print("Get your API key from https://console.supermemory.ai")
        print("Then add to .env: SUPERMEMORY_API_KEY=your_key_here")
        exit(1)

    client = SupermemoryClient(api_key=api_key)

    print("=" * 70)
    print("SUPERMEMORY CLIENT TEST")
    print("=" * 70)
    print()

    # Test connection
    if client.test_connection():
        print("\n" + "=" * 70)
        print("TEST MEMORIES")
        print("=" * 70)

        # Test visual memory
        print("\n[1] Adding visual memory...")
        visual_result = client.add_visual_memory(
            screen_data={
                'window_title': 'VSCode - main.py',
                'ocr_text': 'def process_data(): return result',
                'captured_at': int(datetime.now().timestamp() * 1000)
            },
            visible_files=['main.py', 'config.yaml']
        )
        print(f"  Result: {visual_result}")

        # Test execution memory
        print("\n[2] Adding execution memory...")
        exec_result = client.add_execution_memory(
            task="Deploy Docker container to production",
            result="SUCCESS",
            confidence=0.95,
            agent_name="deployment_agent",
            duration_ms=5400
        )
        print(f"  Result: {exec_result}")

        # Test chat memory
        print("\n[3] Adding chat memory...")
        chat_result = client.add_chat_memory(
            messages=[
                {'role': 'user', 'content': 'How do I deploy a container?'},
                {'role': 'assistant', 'content': 'I can help you deploy a container...'}
            ],
            topics=['docker', 'deployment'],
            planning_triggered=True
        )
        print(f"  Result: {chat_result}")

        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETE")
        print("=" * 70)
    else:
        print("\nConnection test failed. Cannot proceed with memory tests.")

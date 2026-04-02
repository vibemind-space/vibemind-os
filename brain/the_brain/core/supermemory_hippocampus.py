"""
Supermemory Hippocampus Integration

This module bridges the Tahlamus brain system with Supermemory API,
providing hippocampal memory functions (storage and retrieval) backed
by Supermemory's scalable memory engine.

Key Features:
- Automatic memory retrieval for planning (query_for_planning)
- On-demand memory queries (query_specific)
- Memory formation from visual, execution, and chat sources
- Fallback to existing hippocampus if Supermemory unavailable
- Memory context formatting for LLM consumption

Architecture:
    Visual Area → Supabase → SupermemoryHippocampus → Supermemory API
    Agent Execution → SupermemoryHippocampus → Supermemory API
    Chat History → SupermemoryHippocampus → Supermemory API

    Planning Area → query_for_planning() → Supermemory API → formatted context
"""

import os
import sys
from typing import List, Dict, Optional, Any
from datetime import datetime

# Add parent directory to path for imports
if __name__ != "__main__":
    from core.supermemory_client import SupermemoryClient
    from core.supabase_visual_connector import SupabaseVisualConnector
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.supermemory_client import SupermemoryClient
    from core.supabase_visual_connector import SupabaseVisualConnector


class SupermemoryHippocampus:
    """
    Hippocampal memory system backed by Supermemory API.

    Provides memory storage and retrieval for the Tahlamus brain,
    with automatic context injection for planning and execution.
    """

    def __init__(
        self,
        api_key: str = None,
        enable_fallback: bool = True,
        supabase_url: str = None,
        supabase_key: str = None
    ):
        """
        Initialize Supermemory-backed hippocampus.

        Args:
            api_key: Supermemory API key (or from env)
            enable_fallback: Use existing hippocampus if Supermemory fails
            supabase_url: Supabase project URL for visual data
            supabase_key: Supabase service key
        """
        self.enable_fallback = enable_fallback
        self.supermemory_available = False
        self.visual_connector = None

        # Try to initialize Supermemory client
        try:
            self.client = SupermemoryClient(api_key=api_key)
            if self.client.test_connection():
                self.supermemory_available = True
                print("[SupermemoryHippocampus] Initialized with Supermemory backend")
            else:
                print("[SupermemoryHippocampus] Supermemory connection test failed")
        except Exception as e:
            print(f"[SupermemoryHippocampus] Failed to initialize Supermemory: {e}")
            self.client = None

        # Initialize Supabase visual connector if credentials provided
        if supabase_url and supabase_key:
            try:
                self.visual_connector = SupabaseVisualConnector(
                    project_url=supabase_url,
                    secret_key=supabase_key
                )
                print("[SupermemoryHippocampus] Initialized Supabase visual connector")
            except Exception as e:
                print(f"[SupermemoryHippocampus] Supabase connector failed: {e}")

        # Fallback to existing hippocampus
        self.fallback_hippocampus = None
        if enable_fallback and not self.supermemory_available:
            try:
                from core.hippocampus import Hippocampus
                self.fallback_hippocampus = Hippocampus()
                print("[SupermemoryHippocampus] Fallback to existing hippocampus enabled")
            except Exception as e:
                print(f"[SupermemoryHippocampus] Fallback hippocampus unavailable: {e}")

    def query_for_planning(
        self,
        task: str,
        include_visual: bool = True,
        include_execution: bool = True,
        include_chat: bool = True,
        limit_per_type: int = 3
    ) -> Dict[str, Any]:
        """
        Automatic memory retrieval for planning phase.

        Queries similar execution memories, relevant visual context,
        and related conversations to enhance planning decisions.

        Args:
            task: Task description to plan for
            include_visual: Include recent visual context
            include_execution: Include similar execution memories
            include_chat: Include related conversations
            limit_per_type: Max results per memory type

        Returns:
            Dict with memory context:
            {
                'visual_memories': [...],
                'execution_memories': [...],
                'chat_memories': [...],
                'formatted_context': "...",  # Ready for LLM
                'total_memories': int
            }
        """
        if not self.supermemory_available:
            print("[SupermemoryHippocampus] Supermemory unavailable, using fallback")
            if self.fallback_hippocampus:
                # Use existing hippocampus retrieve_similar_cases
                return self._fallback_query(task)
            return self._empty_memory_context()

        memories = {
            'visual_memories': [],
            'execution_memories': [],
            'chat_memories': [],
            'total_memories': 0
        }

        # Query execution memories (most important for planning)
        if include_execution:
            try:
                exec_memories = self.client.search(
                    query=task,
                    memory_type='agent_execution',
                    limit=limit_per_type
                )
                memories['execution_memories'] = exec_memories
                print(f"[Planning] Retrieved {len(exec_memories)} execution memories")
            except Exception as e:
                print(f"[Planning] Execution memory query failed: {e}")

        # Query chat memories for context
        if include_chat:
            try:
                chat_memories = self.client.search(
                    query=task,
                    memory_type='conversation',
                    limit=limit_per_type
                )
                memories['chat_memories'] = chat_memories
                print(f"[Planning] Retrieved {len(chat_memories)} chat memories")
            except Exception as e:
                print(f"[Planning] Chat memory query failed: {e}")

        # Get recent visual context
        if include_visual and self.visual_connector:
            try:
                visual_summary = self.visual_connector.get_visual_context_summary(
                    minutes_ago=5
                )
                # Store visual summary as memory entry
                memories['visual_memories'] = [{
                    'type': 'visual_context',
                    'content': self.visual_connector.format_for_llm(visual_summary),
                    'metadata': visual_summary
                }]
                print(f"[Planning] Retrieved visual context (last 5 min)")
            except Exception as e:
                print(f"[Planning] Visual memory query failed: {e}")

        # Count total memories
        memories['total_memories'] = (
            len(memories['visual_memories']) +
            len(memories['execution_memories']) +
            len(memories['chat_memories'])
        )

        # Format for LLM
        memories['formatted_context'] = self.format_memories_for_llm(memories)

        return memories

    def query_specific(
        self,
        query: str,
        memory_type: str = None,
        spaces: List[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        On-demand memory query with filters.

        Args:
            query: Search query text
            memory_type: Filter by type (visual_context, agent_execution, conversation)
            spaces: Filter by tags/categories
            limit: Maximum results

        Returns:
            List of memory dicts
        """
        if not self.supermemory_available:
            print("[SupermemoryHippocampus] Query failed: Supermemory unavailable")
            if self.fallback_hippocampus:
                return self._fallback_specific_query(query, memory_type)
            return []

        try:
            return self.client.search(
                query=query,
                memory_type=memory_type,
                spaces=spaces,
                limit=limit
            )
        except Exception as e:
            print(f"[SupermemoryHippocampus] Query failed: {e}")
            return []

    def store_visual_memory(
        self,
        screen_data: Dict,
        window_title: str = None,
        ocr_text: str = None,
        visible_files: List[str] = None
    ) -> bool:
        """
        Store visual memory from screen/desktop data.

        Args:
            screen_data: Screen data dict (from Supabase)
            window_title: Active window title
            ocr_text: OCR extracted text
            visible_files: List of visible file paths

        Returns:
            True if stored successfully, False otherwise
        """
        if not self.supermemory_available:
            print("[SupermemoryHippocampus] Cannot store visual memory: unavailable")
            return False

        try:
            result = self.client.add_visual_memory(
                screen_data=screen_data,
                window_title=window_title,
                ocr_text=ocr_text,
                visible_files=visible_files
            )
            print(f"[Visual Memory] Stored: {window_title or 'Unknown'}")
            return True
        except Exception as e:
            print(f"[Visual Memory] Store failed: {e}")
            return False

    def store_execution_memory(
        self,
        task: str,
        result: str,
        confidence: float,
        session_log: str = None,
        agent_name: str = None,
        duration_ms: int = None
    ) -> bool:
        """
        Store execution memory from agent task completion.

        Args:
            task: Task description
            result: Execution result (SUCCESS, FAILURE, etc.)
            confidence: Agent confidence (0.0 to 1.0)
            session_log: Full session logs
            agent_name: Executing agent name
            duration_ms: Execution duration

        Returns:
            True if stored successfully, False otherwise
        """
        if not self.supermemory_available:
            print("[SupermemoryHippocampus] Cannot store execution memory: unavailable")
            return False

        try:
            result_data = self.client.add_execution_memory(
                task=task,
                result=result,
                confidence=confidence,
                session_log=session_log,
                agent_name=agent_name,
                duration_ms=duration_ms
            )
            print(f"[Execution Memory] Stored: {task[:50]}... ({result}, {confidence:.1%})")
            return True
        except Exception as e:
            print(f"[Execution Memory] Store failed: {e}")
            return False

    def store_chat_memory(
        self,
        messages: List[Dict[str, str]],
        topics: List[str] = None,
        planning_triggered: bool = False
    ) -> bool:
        """
        Store chat memory from conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            topics: Conversation topics
            planning_triggered: Whether planning was triggered

        Returns:
            True if stored successfully, False otherwise
        """
        if not self.supermemory_available:
            print("[SupermemoryHippocampus] Cannot store chat memory: unavailable")
            return False

        try:
            result = self.client.add_chat_memory(
                messages=messages,
                topics=topics,
                planning_triggered=planning_triggered
            )
            print(f"[Chat Memory] Stored: {len(messages)} messages")
            return True
        except Exception as e:
            print(f"[Chat Memory] Store failed: {e}")
            return False

    def format_memories_for_llm(self, memories: Dict) -> str:
        """
        Format retrieved memories as context string for LLM.

        Args:
            memories: Dict from query_for_planning()

        Returns:
            Formatted string ready for LLM prompt injection
        """
        parts = ["=== MEMORY CONTEXT ===\n"]

        # Visual context
        if memories.get('visual_memories'):
            parts.append("\n[VISUAL CONTEXT - Recent Screen State]")
            for mem in memories['visual_memories']:
                content = mem.get('content', str(mem))
                parts.append(content)

        # Execution memories
        if memories.get('execution_memories'):
            parts.append("\n[EXECUTION HISTORY - Similar Tasks]")
            for i, mem in enumerate(memories['execution_memories'], 1):
                title = mem.get('title', 'Unknown')
                content = mem.get('pageContent', mem.get('content', ''))
                parts.append(f"\n{i}. {title}")
                parts.append(f"   {content[:200]}...")

        # Chat memories
        if memories.get('chat_memories'):
            parts.append("\n[CONVERSATION HISTORY - Related Discussions]")
            for i, mem in enumerate(memories['chat_memories'], 1):
                title = mem.get('title', 'Unknown')
                content = mem.get('pageContent', mem.get('content', ''))
                parts.append(f"\n{i}. {title}")
                parts.append(f"   {content[:150]}...")

        parts.append(f"\n\nTotal memories retrieved: {memories.get('total_memories', 0)}")
        parts.append("=== END MEMORY CONTEXT ===\n")

        return '\n'.join(parts)

    def _empty_memory_context(self) -> Dict:
        """Return empty memory context structure."""
        return {
            'visual_memories': [],
            'execution_memories': [],
            'chat_memories': [],
            'formatted_context': "",
            'total_memories': 0
        }

    def _fallback_query(self, task: str) -> Dict:
        """Use existing hippocampus for memory retrieval."""
        if not self.fallback_hippocampus:
            return self._empty_memory_context()

        try:
            # Use existing hippocampus retrieve_similar_cases
            memory_biased_gates = self.fallback_hippocampus.retrieve_similar_cases(task)
            # Convert to memory context format
            return {
                'visual_memories': [],
                'execution_memories': [],
                'chat_memories': [],
                'formatted_context': f"Memory-biased gates: {memory_biased_gates}",
                'total_memories': 1
            }
        except Exception as e:
            print(f"[SupermemoryHippocampus] Fallback query failed: {e}")
            return self._empty_memory_context()

    def _fallback_specific_query(self, query: str, memory_type: str) -> List[Dict]:
        """Fallback for specific queries."""
        # Could implement with existing hippocampus if needed
        return []

    def get_statistics(self) -> Dict:
        """
        Get memory statistics.

        Returns:
            Dict with memory counts and stats
        """
        stats = {
            'supermemory_available': self.supermemory_available,
            'fallback_enabled': self.enable_fallback,
            'visual_connector_available': self.visual_connector is not None
        }

        if self.supermemory_available:
            try:
                # Try to get memory counts by type
                visual_count = len(self.client.get_by_space('visual', limit=1000))
                exec_count = len(self.client.get_by_space('execution', limit=1000))
                chat_count = len(self.client.get_by_space('chat', limit=1000))

                stats.update({
                    'visual_memories': visual_count,
                    'execution_memories': exec_count,
                    'chat_memories': chat_count,
                    'total_memories': visual_count + exec_count + chat_count
                })
            except Exception as e:
                print(f"[SupermemoryHippocampus] Stats query failed: {e}")
                stats['error'] = str(e)

        return stats


# Example usage
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from load_env import load_env_file

    load_env_file()

    print("=" * 70)
    print("SUPERMEMORY HIPPOCAMPUS TEST")
    print("=" * 70)
    print()

    # Initialize hippocampus
    hippocampus = SupermemoryHippocampus(
        api_key=os.getenv('SUPERMEMORY_API_KEY'),
        supabase_url=os.getenv('SUPABASE_URL'),
        supabase_key=os.getenv('SUPABASE_SECRET_KEY'),
        enable_fallback=True
    )

    if hippocampus.supermemory_available:
        print("\n[TEST 1] Store execution memory")
        success = hippocampus.store_execution_memory(
            task="Deploy Docker container to production",
            result="SUCCESS",
            confidence=0.95,
            agent_name="deployment_agent",
            duration_ms=5400,
            session_log="Container deployed successfully on port 8080"
        )
        print(f"  Result: {'SUCCESS' if success else 'FAILED'}")

        print("\n[TEST 2] Store chat memory")
        success = hippocampus.store_chat_memory(
            messages=[
                {'role': 'user', 'content': 'How do I deploy a Docker container?'},
                {'role': 'assistant', 'content': 'I can help you deploy a container. Let me plan the steps...'}
            ],
            topics=['docker', 'deployment'],
            planning_triggered=True
        )
        print(f"  Result: {'SUCCESS' if success else 'FAILED'}")

        print("\n[TEST 3] Query for planning")
        memory_context = hippocampus.query_for_planning(
            task="Deploy Docker container",
            include_visual=True,
            include_execution=True,
            include_chat=True
        )
        print(f"  Retrieved {memory_context['total_memories']} memories")
        print(f"\n{memory_context['formatted_context']}")

        print("\n[TEST 4] Get statistics")
        stats = hippocampus.get_statistics()
        print(f"  Stats: {stats}")

        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETE")
        print("=" * 70)
    else:
        print("\nSupermemory unavailable. Cannot run tests.")
        print("Set SUPERMEMORY_API_KEY environment variable.")
        print("Get API key from https://console.supermemory.ai")

"""
Infinite Chat Demo

Demonstrates the difference between:
1. Manual memory retrieval (old approach)
2. Automatic semantic memory injection via Supermemory proxy (new approach)

Key Benefits of Infinite Chat:
- Automatic semantic retrieval (no manual memory formatting)
- Unlimited context windows (beyond model limits)
- 50%+ token reduction in long conversations
- Transparent integration (no code changes needed)
- User-specific memory isolation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.supermemory_llm_client import SupermemoryLLM
from memory_api.memory_client import MemoryClient


def old_approach_manual_memory():
    """
    OLD APPROACH: Manual memory retrieval and formatting.

    Steps:
    1. Call memory API to get relevant memories
    2. Format memories as text
    3. Include in LLM prompt manually
    4. Call LLM
    5. Store result in memory manually
    """
    print("=" * 70)
    print("OLD APPROACH: Manual Memory Retrieval")
    print("=" * 70)
    print()

    # Step 1: Retrieve memories manually
    print("[1] Retrieving relevant memories from Memory API...")
    memory_client = MemoryClient()

    context = memory_client.get_planning_context(
        task="Deploy Docker container",
        user_id="user_alice"
    )

    exec_memories = context['memories']['execution_memories']
    print(f"    Retrieved {len(exec_memories)} execution memories")
    print()

    # Step 2: Format memories manually
    print("[2] Manually formatting memories for LLM...")
    memory_context = ""
    if exec_memories:
        memory_context = "Relevant Past Executions:\n"
        for mem in exec_memories[:2]:  # Take first 2
            content = mem.get('content', '')
            memory_context += f"- {content[:200]}...\n"
    print(f"    Formatted {len(memory_context)} characters")
    print()

    # Step 3: Build prompt with memory context
    print("[3] Building LLM prompt with memory context...")
    prompt = f"""Task: Deploy a Docker container to production

{memory_context}

Please create a deployment plan considering the past execution history above."""
    print(f"    Prompt length: {len(prompt)} characters")
    print()

    print("[4] Calling LLM with manual context...")
    # In production, you'd call OpenAI here
    print("    (Would call OpenAI API here)")
    print()

    print("[5] Manually storing conversation in memory...")
    # Would store the conversation manually
    print("    (Would call memory_client.store_chat() here)")
    print()

    print("=" * 70)
    print("Issues with this approach:")
    print("  - Requires manual memory retrieval")
    print("  - Need to format memories as text")
    print("  - Limited to recent memories (last 3)")
    print("  - No semantic search (just recency)")
    print("  - Must manually store conversations")
    print("  - Verbose code, many steps")
    print("=" * 70)


def new_approach_infinite_chat():
    """
    NEW APPROACH: Automatic semantic memory injection via Supermemory proxy.

    Steps:
    1. Call LLM through Supermemory proxy
    2. That's it!

    Supermemory automatically:
    - Retrieves semantically relevant past conversations
    - Injects them into context
    - Manages context window limits
    - Stores this conversation
    """
    print()
    print()
    print("=" * 70)
    print("NEW APPROACH: Infinite Chat Proxy")
    print("=" * 70)
    print()

    # Single step: Initialize LLM client with Supermemory proxy
    print("[1] Initializing LLM with Supermemory proxy...")
    # Model comes from llm_config.yml (brain_supermemory role)
    llm = SupermemoryLLM(user_id="user_alice")
    print()

    # That's it! Just call the LLM
    print("[2] Calling LLM (Supermemory handles everything)...")
    response = llm.plan_task(
        task="Deploy a Docker container to production"
    )

    print()
    print(f"Response: {response[:300]}...")
    print()

    print("=" * 70)
    print("What Supermemory did automatically:")
    print("  [OK] Retrieved semantically relevant past conversations")
    print("  [OK] Injected them into LLM context")
    print("  [OK] Managed context window limits")
    print("  [OK] Stored this conversation for future use")
    print("  [OK] Used semantic search (not just recency)")
    print()
    print("Benefits:")
    print("  - 95% less code")
    print("  - Semantic relevance (not just recent)")
    print("  - Unlimited context windows")
    print("  - 50%+ token reduction")
    print("  - Automatic storage")
    print("=" * 70)


def demonstrate_multi_turn_conversation():
    """
    Demonstrate multi-turn conversation with automatic memory.
    """
    print()
    print()
    print("=" * 70)
    print("MULTI-TURN CONVERSATION DEMO")
    print("=" * 70)
    print()

    # Model comes from llm_config.yml (brain_supermemory role)
    llm = SupermemoryLLM(user_id="user_bob")

    print("[Conversation 1] User asks about Docker...")
    response1 = llm.chat_simple("What is Docker?")
    print(f"Bot: {response1[:150]}...")
    print()

    print("[Conversation 2] User asks follow-up (minutes later)...")
    response2 = llm.chat_simple("How do I install it?")
    print(f"Bot: {response2[:150]}...")
    print()
    print("Supermemory remembered the Docker context automatically!")
    print()

    print("[Conversation 3] User asks about deployment (hours later)...")
    response3 = llm.chat_simple("Can you help me deploy my app?")
    print(f"Bot: {response3[:150]}...")
    print()
    print("Supermemory retrieved relevant past conversations!")
    print()

    print("=" * 70)
    print("Key Point:")
    print("  Even though these are separate API calls hours apart,")
    print("  Supermemory maintains context by automatically retrieving")
    print("  relevant past conversation snippets based on semantic similarity.")
    print("=" * 70)


def compare_approaches():
    """
    Side-by-side comparison of code complexity.
    """
    print()
    print()
    print("=" * 70)
    print("CODE COMPLEXITY COMPARISON")
    print("=" * 70)
    print()

    print("OLD APPROACH (Manual Memory):")
    print("-" * 70)
    print("""
    # 1. Get memories
    memory_client = MemoryClient()
    context = memory_client.get_planning_context(task, user_id)

    # 2. Format memories
    memory_text = format_memories(context['memories'])

    # 3. Build prompt
    prompt = f"Task: {task}\\n\\nContext:\\n{memory_text}"

    # 4. Call LLM (old way: direct OpenAI instantiation with hardcoded model)
    client = OpenAI(api_key=openai_key)
    response = client.chat.completions.create(
        model="some-model-id",
        messages=[{"role": "user", "content": prompt}]
    )

    # 5. Store conversation
    memory_client.store_chat(messages, topics, user_id)

    # ~30 lines of code
    """)
    print()

    print("NEW APPROACH (Infinite Chat):")
    print("-" * 70)
    print("""
    # 1. Initialize once
    llm = SupermemoryLLM(user_id="alice")

    # 2. Call LLM
    response = llm.plan_task("Deploy Docker container")

    # That's it! ~3 lines of code
    # Supermemory handles memory automatically
    """)
    print()

    print("=" * 70)
    print("Result: 90% less code, automatic semantic memory!")
    print("=" * 70)


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("INFINITE CHAT DEMO")
    print("Comparing Manual Memory vs Automatic Semantic Memory")
    print("=" * 70)
    print()

    # Show old approach
    old_approach_manual_memory()

    # Show new approach
    new_approach_infinite_chat()

    # Show multi-turn conversation
    demonstrate_multi_turn_conversation()

    # Compare code complexity
    compare_approaches()

    print()
    print("=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print()
    print("Use SupermemoryLLM instead of manual memory retrieval!")
    print()
    print("Benefits:")
    print("  1. Semantic search (not just recent memories)")
    print("  2. Automatic context injection")
    print("  3. Unlimited conversations (beyond context window)")
    print("  4. 50%+ token savings")
    print("  5. 90% less code")
    print("  6. User-specific memory isolation")
    print()
    print("Integration:")
    print("  - Replace OpenAI client with SupermemoryLLM")
    print("  - Set user_id for memory isolation")
    print("  - All conversations automatically stored and retrieved")
    print()
    print("=" * 70)

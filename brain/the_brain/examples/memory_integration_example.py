"""
Memory Integration Example

Demonstrates how to integrate the Memory API into the Tahlamus brain
planning and execution flow.

This example shows:
1. Retrieving memory context before planning
2. Using memory context in LLM prompts
3. Tracking execution sessions
4. Storing execution results with confidence
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_api.memory_client import MemoryClient
from core.execution_tracker import ExecutionTracker
from datetime import datetime


def simulate_brain_planning_with_memory():
    """
    Simulates the brain's planning flow with memory integration.
    """
    print("=" * 70)
    print("BRAIN PLANNING WITH MEMORY INTEGRATION")
    print("=" * 70)
    print()

    # Initialize Memory API client
    memory_client = MemoryClient(base_url="http://localhost:8001")

    # Check if memory service is available
    if not memory_client.health_check():
        print("[ERROR] Memory API service is not running")
        print("Start it with: python memory_api/memory_service.py")
        return

    print("[OK] Memory API service connected")
    print()

    # Step 1: User provides a task
    task = "Deploy a Docker container to AWS ECS"
    user_id = "user_alice"

    print(f"[TASK] {task}")
    print(f"[USER] {user_id}")
    print()

    # Step 2: Brain retrieves memory context before planning
    print("[1] Retrieving memory context...")
    context = memory_client.get_planning_context(
        task=task,
        user_id=user_id,
        include_visual=True,
        include_execution=True,
        include_chat=True
    )

    total_memories = context['memories']['total_memories']
    exec_memories = context['memories']['execution_memories']
    chat_memories = context['memories']['chat_memories']

    print(f"    Retrieved {total_memories} memories:")
    print(f"    - {len(exec_memories)} execution memories")
    print(f"    - {len(chat_memories)} chat memories")
    print()

    # Step 3: Format memory context for LLM
    memory_context = format_memory_for_llm(context)

    print("[2] Memory context for LLM:")
    print("-" * 70)
    print(memory_context)
    print("-" * 70)
    print()

    # Step 4: Brain sends to LLM for planning (simulated)
    print("[3] Sending to LLM for planning...")
    llm_prompt = f"""
Task: {task}

Memory Context:
{memory_context}

Please create a step-by-step plan for this task, taking into account
the execution history and previous conversations.
"""

    # Simulated LLM response (in production, this would be actual LLM call)
    plan = """
1. Check AWS credentials are configured
2. Build Docker image: docker build -t myapp:latest .
3. Tag image for ECR: docker tag myapp:latest {ecr_url}/myapp:latest
4. Push to ECR: docker push {ecr_url}/myapp:latest
5. Update ECS service with new image
6. Verify deployment health
"""

    print("[OK] Plan received from LLM:")
    print(plan)
    print()

    # Step 5: Agent executes the plan (simulated)
    print("[4] Agent executing plan...")
    tracker = ExecutionTracker(
        task=task,
        agent_name="aws_deployment_agent",
        user_id=user_id
    )

    # Simulate execution steps
    steps = [
        ("Check AWS credentials", "SUCCESS", "Credentials valid: aws-access-key-***", 120),
        ("docker build -t myapp:latest .", "SUCCESS", "Image built successfully", 3200),
        ("docker tag myapp:latest registry.example.com/myapp:latest", "SUCCESS", "Tagged", 150),
        ("docker push registry.example.com/myapp:latest", "SUCCESS", "Pushed to registry", 8500),
        ("Update ECS service", "SUCCESS", "Service updated, deployment in progress", 1200),
        ("Verify deployment health", "SUCCESS", "Deployment healthy, 3/3 tasks running", 2000)
    ]

    for i, (command, result, output, duration_ms) in enumerate(steps, 1):
        tracker.add_execution(
            step=i,
            command=command,
            result=result,
            output=output,
            duration_ms=duration_ms,
            metadata={"region": "us-east-1"}
        )
        print(f"    [{result}] Step {i}: {command} ({duration_ms}ms)")

    # Mark execution as complete with agent-determined confidence
    agent_confidence = 0.95  # Agent determines this based on execution
    tracker.mark_complete("SUCCESS", confidence=agent_confidence)

    print()
    print(f"[OK] Execution complete with {agent_confidence:.1%} confidence")
    print()

    # Step 6: Store execution session in memory
    print("[5] Storing execution session in memory...")
    session_log = tracker.format_as_text()

    result = memory_client.store_execution(
        task=task,
        result="SUCCESS",
        confidence=agent_confidence,
        session_log=session_log,
        agent_name="aws_deployment_agent",
        duration_ms=tracker.get_total_duration(),
        user_id=user_id
    )

    print(f"[OK] Execution memory stored: {result['id']}")
    print()

    # Step 7: Also store the conversation
    print("[6] Storing conversation in memory...")
    conversation = [
        {"role": "user", "content": task},
        {"role": "assistant", "content": f"I'll help you deploy the container. Here's the plan:\n{plan}"}
    ]

    chat_result = memory_client.store_chat(
        messages=conversation,
        topics=["docker", "aws", "ecs", "deployment"],
        planning_triggered=True,
        user_id=user_id
    )

    print(f"[OK] Chat memory stored: {chat_result['id']}")
    print()

    # Show formatted session log
    print("[7] Session log that was stored:")
    print("=" * 70)
    print(session_log)
    print("=" * 70)
    print()

    print("[COMPLETE] All memories stored successfully!")
    print()
    print("Next time the brain encounters a similar task, it will:")
    print("  - Retrieve this execution history")
    print("  - Know that the deployment succeeded")
    print("  - Reuse the successful approach")
    print("  - Adjust confidence based on past performance")


def format_memory_for_llm(context):
    """
    Format memory context into LLM-friendly text.
    """
    lines = []

    memories = context['memories']

    # Execution memories
    if memories['execution_memories']:
        lines.append("Recent Execution History:")
        for mem in memories['execution_memories']:
            # Extract from content
            content = mem.get('content', '')
            lines.append(f"  - {content[:200]}...")
        lines.append("")

    # Chat memories
    if memories['chat_memories']:
        lines.append("Recent Conversations:")
        for mem in memories['chat_memories']:
            content = mem.get('content', '')
            lines.append(f"  - {content[:200]}...")
        lines.append("")

    if not memories['execution_memories'] and not memories['chat_memories']:
        lines.append("No relevant memory context found.")

    return "\n".join(lines)


def simulate_failure_with_memory():
    """
    Simulates a failed execution that will help the brain learn.
    """
    print("=" * 70)
    print("EXECUTION FAILURE - LEARNING FROM MISTAKES")
    print("=" * 70)
    print()

    memory_client = MemoryClient()

    task = "Deploy application without building Docker image first"
    tracker = ExecutionTracker(task=task, agent_name="deployment_agent")

    # Simulate failed execution
    tracker.add_execution(
        step=1,
        command="docker push myapp:latest",
        result="FAILURE",
        output="Error: image not found - did you forget to build?",
        duration_ms=200
    )

    tracker.mark_complete("FAILURE", confidence=0.0)

    # Store the failure
    result = memory_client.store_execution(
        task=task,
        result="FAILURE",
        confidence=0.0,
        session_log=tracker.format_as_text(),
        agent_name="deployment_agent",
        duration_ms=tracker.get_total_duration()
    )

    print(f"[OK] Failure stored: {result['id']}")
    print()
    print("The brain will now remember:")
    print("  - Don't push Docker images before building them")
    print("  - This approach has 0% confidence")
    print("  - Future planning will avoid this mistake")
    print()


if __name__ == "__main__":
    # Run the full planning-execution-memory cycle
    simulate_brain_planning_with_memory()

    print()
    print("=" * 70)
    print()

    # Show how failures are stored for learning
    simulate_failure_with_memory()

    print()
    print("=" * 70)
    print("INTEGRATION EXAMPLE COMPLETE")
    print("=" * 70)
    print()
    print("Key Takeaways:")
    print("  1. Memory context is retrieved BEFORE planning")
    print("  2. Past executions inform future plans")
    print("  3. Agent sets confidence AFTER execution")
    print("  4. Both successes and failures are stored")
    print("  5. Memory forms during execution, not just planning")
    print()
    print("Next steps:")
    print("  - Integrate into core/hierarchical_planner.py")
    print("  - Add memory panel to web/brain_dashboard.html")
    print("  - Create visual memory poller service")
    print("  - Build agent bridge for real execution tracking")

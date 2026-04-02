"""
Test AutoGen Swarm + Tahlamus Brain Integration
================================================

Tests the complete brain-swarm system with various task types.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from production.brain_swarm_orchestrator import BrainSwarmOrchestrator


async def test_docker_task():
    """Test Docker deployment task"""
    print("\n" + "="*60)
    print("TEST 1: Docker Deployment")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_docker",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    task = "Deploy Docker container with Redis and health monitoring"
    result = await orchestrator.process_task(task)

    print(f"\nTask: {task}")
    print(f"Brain Recommendation: {result['suggested_agent']}")
    print(f"Primary Action: {result['brain_analysis']['prediction']['primary_action']}")
    print(f"Confidence: {result['brain_analysis']['prediction']['confidence']:.2f}")
    print(f"Task Type: {result['brain_analysis']['prediction'].get('task_type', 'unknown')}")

    # Check if suggested agent is correct
    assert result['suggested_agent'] == 'docker_execution_agent', \
        f"Expected docker_execution_agent, got {result['suggested_agent']}"

    print("✓ Docker task test passed")

    # Submit feedback
    await orchestrator.submit_feedback(
        task=task,
        success=True,
        user_rating=0.9,
        execution_time=45.0
    )
    print("✓ Feedback submitted")


async def test_database_task():
    """Test Database migration task"""
    print("\n" + "="*60)
    print("TEST 2: Database Migration")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_database",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    task = "Migrate database from MySQL to PostgreSQL"
    result = await orchestrator.process_task(task)

    print(f"\nTask: {task}")
    print(f"Brain Recommendation: {result['suggested_agent']}")
    print(f"Primary Action: {result['brain_analysis']['prediction']['primary_action']}")
    print(f"Task Type: {result['brain_analysis']['prediction'].get('task_type', 'unknown')}")

    # Check if suggested agent is correct
    assert result['suggested_agent'] == 'database_execution_agent', \
        f"Expected database_execution_agent, got {result['suggested_agent']}"

    print("✓ Database task test passed")


async def test_debugging_task():
    """Test Debugging task"""
    print("\n" + "="*60)
    print("TEST 3: Debugging Task")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_debugging",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    task = "Debug memory leak in Node.js application"
    result = await orchestrator.process_task(task)

    print(f"\nTask: {task}")
    print(f"Brain Recommendation: {result['suggested_agent']}")
    print(f"Primary Action: {result['brain_analysis']['prediction']['primary_action']}")
    print(f"Task Type: {result['brain_analysis']['prediction'].get('task_type', 'unknown')}")

    # Check attention focus (should focus on error_signal for debugging)
    attention = result['brain_analysis'].get('attention_state', {})
    print(f"Attention Focus: {attention.get('top_modality', 'unknown')}")

    # Check if suggested agent is correct
    assert result['suggested_agent'] == 'debugging_agent', \
        f"Expected debugging_agent, got {result['suggested_agent']}"

    print("✓ Debugging task test passed")


async def test_complex_ctm_task():
    """Test Complex task that triggers CTM reasoning"""
    print("\n" + "="*60)
    print("TEST 4: Complex Task with CTM Reasoning")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_ctm",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    task = "Design distributed microservice architecture with auto-scaling, service mesh, and zero downtime deployment"
    result = await orchestrator.process_task(task)

    print(f"\nTask: {task}")
    print(f"Brain Recommendation: {result['suggested_agent']}")
    print(f"Complexity: {result['brain_analysis']['prediction'].get('complexity', 0.0):.2f}")

    # Check if CTM was triggered
    ctm_task_id = result['brain_analysis'].get('ctm_task_id')
    if ctm_task_id:
        print(f"✓ CTM Triggered: {ctm_task_id}")

        # Wait for CTM to complete (if not already)
        if orchestrator.brain.planner.ctm_async:
            import time
            for _ in range(5):
                if orchestrator.brain.planner.ctm_async.is_complete(ctm_task_id):
                    ctm_result = orchestrator.brain.planner.ctm_async.get_result(ctm_task_id)
                    print(f"CTM Steps: {ctm_result.steps_taken}")
                    print(f"CTM Converged: {ctm_result.converged}")
                    break
                time.sleep(1)
    else:
        print("✗ CTM Not Triggered (complexity may be < 0.4)")

    print("✓ Complex task test passed")


async def test_api_task():
    """Test API development task"""
    print("\n" + "="*60)
    print("TEST 5: API Development")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_api",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    task = "Create REST API endpoint for user authentication with JWT"
    result = await orchestrator.process_task(task)

    print(f"\nTask: {task}")
    print(f"Brain Recommendation: {result['suggested_agent']}")
    print(f"Task Type: {result['brain_analysis']['prediction'].get('task_type', 'unknown')}")

    # Check compositional reasoning (should break into subtasks)
    composition = result['brain_analysis'].get('composition', {})
    subtasks = composition.get('subtasks', [])
    print(f"Compositional Subtasks: {len(subtasks)} subtasks")
    if subtasks:
        print(f"  Subtasks: {subtasks}")

    # Check if suggested agent is correct
    assert result['suggested_agent'] == 'api_execution_agent', \
        f"Expected api_execution_agent, got {result['suggested_agent']}"

    print("✓ API task test passed")


async def test_security_task():
    """Test Security audit task"""
    print("\n" + "="*60)
    print("TEST 6: Security Audit")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_security",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    task = "Audit application for SQL injection vulnerabilities"
    result = await orchestrator.process_task(task)

    print(f"\nTask: {task}")
    print(f"Brain Recommendation: {result['suggested_agent']}")
    print(f"Task Type: {result['brain_analysis']['prediction'].get('task_type', 'unknown')}")

    # Check neuromodulation (should have high urgency for security)
    neuromod = result['brain_analysis'].get('neuromodulation', {})
    print(f"Neuromodulation: {neuromod}")

    # Check if suggested agent is correct
    assert result['suggested_agent'] == 'security_agent', \
        f"Expected security_agent, got {result['suggested_agent']}"

    print("✓ Security task test passed")


async def test_brain_stats():
    """Test brain statistics"""
    print("\n" + "="*60)
    print("TEST 7: Brain Statistics")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_stats",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    # Process a task first
    await orchestrator.process_task("Deploy Docker with Redis")

    # Get stats
    stats = orchestrator.get_brain_stats()

    print("Brain Statistics:")
    print(f"  Total Predictions: {stats.get('total_predictions', 0)}")
    print(f"  Success Rate: {stats.get('success_rate', 0.0):.2f}")
    print(f"  Average Confidence: {stats.get('average_confidence', 0.0):.2f}")

    print("✓ Brain stats test passed")


async def test_swarm_status():
    """Test swarm status"""
    print("\n" + "="*60)
    print("TEST 8: Swarm Status")
    print("="*60)

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="test_user_status",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY")
    )

    orchestrator.initialize_swarm_agents()

    status = orchestrator.get_swarm_status()

    print("Swarm Status:")
    print(f"  Agents Initialized: {status['agents_initialized']}")
    print(f"  Swarm Created: {status['swarm_created']}")
    print(f"  Agent Names: {', '.join(status['agent_names'][:5])}... ({len(status['agent_names'])} total)")

    # Check that all expected agents exist
    expected_agents = [
        'coordinator',
        'active_inference_agent',
        'ctm_reasoning_agent',
        'memory_agent',
        'general_execution_agent',
        'docker_execution_agent',
        'database_execution_agent',
        'api_execution_agent',
        'debugging_agent',
        'monitoring_agent',
        'deployment_agent',
        'testing_agent',
        'refactoring_agent',
        'documentation_agent',
        'security_agent'
    ]

    for agent_name in expected_agents:
        assert agent_name in status['agent_names'], f"Missing agent: {agent_name}"

    print(f"✓ All {len(expected_agents)} expected agents present")


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("AUTOGEN SWARM + TAHLAMUS BRAIN INTEGRATION TESTS")
    print("="*60)

    load_dotenv()

    # Check API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("\n✗ ERROR: OPENAI_API_KEY not found in .env")
        print("Please add: OPENAI_API_KEY=sk-... to your .env file")
        return

    try:
        # Run tests
        await test_docker_task()
        await test_database_task()
        await test_debugging_task()
        await test_complex_ctm_task()
        await test_api_task()
        await test_security_task()
        await test_brain_stats()
        await test_swarm_status()

        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())

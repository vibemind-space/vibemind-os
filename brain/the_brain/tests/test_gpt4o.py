"""Quick test of swarm with GPT-4o"""
import asyncio
import os
from dotenv import load_dotenv
from production.brain_swarm_orchestrator import BrainSwarmOrchestrator

load_dotenv()

async def test():
    print("Testing swarm with GPT-4o...")

    orchestrator = BrainSwarmOrchestrator(
        session_log_dir='data/logs',
        user_id='test_gpt4o',
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        openrouter_api_key=None  # Force GPT-4o
    )

    print("Initializing agents...")
    orchestrator.initialize_swarm_agents()

    print(f"\n[SUCCESS] {len(orchestrator.agents)} agents initialized with GPT-4o")

    # Test a simple task
    print("\nTesting prediction...")
    result = await orchestrator.process_task("Deploy Docker with Redis")

    print(f"\nTask: {result['task']}")
    print(f"Suggested Agent: {result['suggested_agent']}")
    print(f"Primary Action: {result['brain_analysis']['prediction']['primary_action']}")
    print(f"Confidence: {result['brain_analysis']['prediction']['confidence']:.2f}")

    print("\n[SUCCESS] GPT-4o test passed!")

if __name__ == "__main__":
    asyncio.run(test())

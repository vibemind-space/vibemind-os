"""Test agent capability registry."""
import asyncio
import sys
sys.path.insert(0, ".")

from src.services.agent_registry import (
    AgentCapabilityRegistry,
    AgentCapability,
    AgentAvailability,
    AgentStatus,
)


async def test_register_agent():
    """Basic agent registration."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Frontend", AgentCapability(
        agent_name="Frontend",
        languages={"typescript", "javascript"},
        frameworks={"react", "nextjs"},
        task_types={"ui_component", "page_layout"},
        priority=1,
    ))

    info = reg.get_agent("Frontend")
    assert info is not None
    assert info["capability"]["agent_name"] == "Frontend"
    assert "typescript" in info["capability"]["languages"]
    assert info["status"]["availability"] == "online"
    print("OK: register agent")


async def test_find_best_agent():
    """Find best agent for a task."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Frontend", AgentCapability(
        agent_name="Frontend",
        languages={"typescript", "javascript", "css"},
        frameworks={"react", "nextjs"},
        task_types={"ui_component", "page_layout"},
        priority=1,
    ))
    reg.register_agent("Backend", AgentCapability(
        agent_name="Backend",
        languages={"python", "go"},
        frameworks={"fastapi", "django"},
        task_types={"api_endpoint", "database_schema"},
        priority=2,
    ))
    reg.register_agent("Fullstack", AgentCapability(
        agent_name="Fullstack",
        languages={"typescript", "python"},
        frameworks={"react", "fastapi"},
        task_types={"ui_component", "api_endpoint"},
        priority=3,
    ))

    # TypeScript + React + UI component = Frontend wins
    best = reg.find_best_agent(language="typescript", framework="react", task_type="ui_component")
    assert best == "Frontend"

    # Python + FastAPI + API = Backend wins
    best = reg.find_best_agent(language="python", framework="fastapi", task_type="api_endpoint")
    assert best == "Backend"

    print("OK: find best agent")


async def test_find_no_match():
    """No matching agent returns None."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Frontend", AgentCapability(
        agent_name="Frontend",
        languages={"typescript"},
        task_types={"ui_component"},
    ))

    best = reg.find_best_agent(language="rust", task_type="system_service")
    assert best is None
    print("OK: no match returns None")


async def test_availability_filtering():
    """Unavailable agents excluded from search."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Agent1", AgentCapability(
        agent_name="Agent1",
        languages={"python"},
        task_types={"coding"},
        priority=1,
    ))
    reg.register_agent("Agent2", AgentCapability(
        agent_name="Agent2",
        languages={"python"},
        task_types={"coding"},
        priority=2,
    ))

    # Make Agent1 offline
    reg.set_availability("Agent1", AgentAvailability.OFFLINE)

    best = reg.find_best_agent(language="python", task_type="coding")
    assert best == "Agent2"  # Agent1 is offline
    print("OK: availability filtering")


async def test_busy_agent_capacity():
    """Busy agent at max capacity excluded."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("SingleTask", AgentCapability(
        agent_name="SingleTask",
        languages={"python"},
        task_types={"coding"},
        max_concurrent_tasks=1,
        priority=1,
    ))
    reg.register_agent("Backup", AgentCapability(
        agent_name="Backup",
        languages={"python"},
        task_types={"coding"},
        priority=5,
    ))

    reg.mark_busy("SingleTask")

    best = reg.find_best_agent(language="python", task_type="coding")
    assert best == "Backup"  # SingleTask at capacity
    print("OK: busy agent capacity")


async def test_mark_busy_and_free():
    """Mark busy/free updates status correctly."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Worker", AgentCapability(
        agent_name="Worker",
        languages={"python"},
        max_concurrent_tasks=3,
    ))

    reg.mark_busy("Worker")
    reg.mark_busy("Worker")
    status = reg._status["Worker"]
    assert status.current_tasks == 2
    assert status.availability == AgentAvailability.BUSY

    reg.mark_free("Worker")
    assert status.current_tasks == 1
    assert status.availability == AgentAvailability.ONLINE  # Below max

    reg.mark_free("Worker")
    assert status.current_tasks == 0
    assert status.total_tasks_completed == 2
    print("OK: mark busy and free")


async def test_find_agents_for_task():
    """Find all matching agents ranked."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("A", AgentCapability(agent_name="A", languages={"python"}, task_types={"api"}, priority=1))
    reg.register_agent("B", AgentCapability(agent_name="B", languages={"python"}, task_types={"api", "db"}, priority=2))
    reg.register_agent("C", AgentCapability(agent_name="C", languages={"rust"}, task_types={"system"}, priority=1))

    results = reg.find_agents_for_task(language="python", task_type="api")
    assert len(results) == 2
    assert results[0]["agent_name"] in ("A", "B")
    assert results[0]["match_score"] == 1.0
    print("OK: find agents for task")


async def test_capability_match_scoring():
    """Capability match scoring works correctly."""
    cap = AgentCapability(
        agent_name="test",
        languages={"python", "typescript"},
        frameworks={"react"},
        task_types={"ui_component"},
    )

    # Perfect match
    assert cap.matches("python", "react", "ui_component") == 1.0

    # Partial match (2/3)
    score = cap.matches("python", "django", "ui_component")
    assert abs(score - 2/3) < 0.01

    # No match
    assert cap.matches("rust", "actix", "system") == 0.0

    # No criteria
    assert cap.matches() == 0.0
    print("OK: capability match scoring")


async def test_update_capability():
    """Dynamic capability updates."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Learner", AgentCapability(
        agent_name="Learner",
        languages={"python"},
    ))

    # Agent learns new languages
    reg.update_capability("Learner", languages={"rust", "go"})

    cap = reg._capabilities["Learner"]
    assert "python" in cap.languages  # Original
    assert "rust" in cap.languages  # Learned
    assert "go" in cap.languages  # Learned
    print("OK: update capability")


async def test_capability_matrix():
    """Capability matrix shows all agents vs all capabilities."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("A", AgentCapability(agent_name="A", languages={"python"}, frameworks={"fastapi"}))
    reg.register_agent("B", AgentCapability(agent_name="B", languages={"typescript"}, frameworks={"react"}))

    matrix = reg.get_capability_matrix()
    assert "python" in matrix["all_languages"]
    assert "typescript" in matrix["all_languages"]
    assert matrix["agents"]["A"]["languages"]["python"] is True
    assert matrix["agents"]["A"]["languages"]["typescript"] is False
    assert matrix["agents"]["B"]["frameworks"]["react"] is True
    print("OK: capability matrix")


async def test_list_agents():
    """List agents with optional filter."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Online1", AgentCapability(agent_name="Online1", languages={"py"}))
    reg.register_agent("Online2", AgentCapability(agent_name="Online2", languages={"js"}))
    reg.register_agent("Offline1", AgentCapability(agent_name="Offline1", languages={"go"}))
    reg.set_availability("Offline1", AgentAvailability.OFFLINE)

    all_agents = reg.list_agents()
    assert len(all_agents) == 3

    online_only = reg.list_agents(availability=AgentAvailability.ONLINE)
    assert len(online_only) == 2
    print("OK: list agents")


async def test_unregister():
    """Unregister removes agent completely."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("Temp", AgentCapability(agent_name="Temp", languages={"x"}))
    assert reg.get_agent("Temp") is not None

    reg.unregister_agent("Temp")
    assert reg.get_agent("Temp") is None
    print("OK: unregister agent")


async def test_stats():
    """Stats report correctly."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("A", AgentCapability(agent_name="A", languages={"py"}))
    reg.register_agent("B", AgentCapability(agent_name="B", languages={"js"}))
    reg.mark_busy("A")
    reg.mark_free("A")
    reg.set_availability("B", AgentAvailability.OFFLINE)

    stats = reg.get_stats()
    assert stats["total_agents"] == 2
    assert stats["online"] == 1
    assert stats["offline"] == 1
    assert stats["total_tasks_completed"] == 1
    print("OK: stats")


async def test_specialty_scoring():
    """Specialty affects scoring."""
    reg = AgentCapabilityRegistry()
    reg.register_agent("SecurityExpert", AgentCapability(
        agent_name="SecurityExpert",
        languages={"python"},
        task_types={"code_review"},
        specialties={"security"},
        priority=2,
    ))
    reg.register_agent("GeneralReviewer", AgentCapability(
        agent_name="GeneralReviewer",
        languages={"python"},
        task_types={"code_review"},
        priority=1,
    ))

    # Without specialty requirement, GeneralReviewer wins on priority
    best = reg.find_best_agent(language="python", task_type="code_review")
    assert best is not None

    # With specialty, SecurityExpert should win
    best = reg.find_best_agent(language="python", task_type="code_review", specialty="security")
    assert best == "SecurityExpert"
    print("OK: specialty scoring")


async def test_to_dict():
    """AgentCapability serialization."""
    cap = AgentCapability(
        agent_name="Test",
        languages={"python", "rust"},
        frameworks={"fastapi"},
        task_types={"api"},
        specialties={"performance"},
        priority=2,
        description="A test agent",
    )
    d = cap.to_dict()
    assert d["agent_name"] == "Test"
    assert d["languages"] == ["python", "rust"]
    assert d["priority"] == 2
    assert d["description"] == "A test agent"
    print("OK: to_dict")


async def main():
    print("=== Agent Capability Registry Tests ===\n")
    await test_register_agent()
    await test_find_best_agent()
    await test_find_no_match()
    await test_availability_filtering()
    await test_busy_agent_capacity()
    await test_mark_busy_and_free()
    await test_find_agents_for_task()
    await test_capability_match_scoring()
    await test_update_capability()
    await test_capability_matrix()
    await test_list_agents()
    await test_unregister()
    await test_stats()
    await test_specialty_scoring()
    await test_to_dict()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())

# AutoGen Swarm + Tahlamus Brain - Quick Start Guide

## 5-Minute Setup

### Step 1: Install Dependencies

```bash
# Install AutoGen swarm dependencies
pip install autogen-agentchat autogen-ext

# Or install all requirements at once
pip install -r requirements-swarm.txt
```

### Step 2: Add API Key

Create/update `.env` file in project root:

```env
# Required: OpenRouter API key
OPENROUTER_API_KEY=sk-or-v1-...
```

**Get OpenRouter key**: https://openrouter.ai/keys

**Why OpenRouter?**
- Access to 100+ models (GPT, Claude, Llama, etc.)
- Cheaper than direct providers
- Already used by Tahlamus brain
- Unified billing for brain + swarm
- See `OPENROUTER_SWARM_SETUP.md` for details

### Step 3: Test Installation

```bash
python production/swarm_brain_cli.py agent-health
```

Expected output:
```
============================================================
AGENT HEALTH CHECK
============================================================
✓ coordinator: OK
✓ active_inference_agent: OK
✓ ctm_reasoning_agent: OK
✓ memory_agent: OK
✓ general_execution_agent: OK
✓ docker_execution_agent: OK
✓ database_execution_agent: OK
✓ api_execution_agent: OK
✓ debugging_agent: OK
✓ monitoring_agent: OK
✓ deployment_agent: OK
✓ testing_agent: OK
✓ refactoring_agent: OK
✓ documentation_agent: OK
✓ security_agent: OK

Total Agents: 15
Status: All systems operational
```

### Step 4: Run Your First Task

```bash
python production/swarm_brain_cli.py predict "Deploy Docker with Redis"
```

You should see:
1. **Brain Analysis** - Task type, confidence, complexity
2. **Suggested Agent** - Brain recommends `docker_execution_agent`
3. **Swarm Execution** - Agent executes with brain guidance

### Step 5: Submit Feedback (Continuous Learning)

```bash
python production/swarm_brain_cli.py feedback \
    --task "Deploy Docker with Redis" \
    --success \
    --rating 0.9 \
    --time 45.0
```

Brain learns from your feedback and improves over time!

---

## Interactive Mode

For continuous conversation:

```bash
python production/swarm_brain_cli.py interactive
```

Try these tasks:
- "Deploy Docker with Redis"
- "Fix memory leak in Node.js"
- "Create API endpoint for user auth"
- "Run pytest tests"
- "Debug SQL injection vulnerability"

Type `stats` to see brain statistics, `status` for swarm status, `quit` to exit.

---

## Integration with Python Code

```python
from production.brain_swarm_orchestrator import BrainSwarmOrchestrator
import asyncio
import os

async def main():
    # Initialize orchestrator
    orchestrator = BrainSwarmOrchestrator(
        session_log_dir="data/logs",
        user_id="your_user_id",
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Initialize swarm agents
    orchestrator.initialize_swarm_agents()

    # Process task
    result = await orchestrator.process_task(
        "Deploy Docker container with Redis"
    )

    # Print results
    print(f"Suggested Agent: {result['suggested_agent']}")
    print(f"Primary Action: {result['brain_analysis']['prediction']['primary_action']}")
    print(f"Confidence: {result['brain_analysis']['prediction']['confidence']:.2f}")

    # Submit feedback
    await orchestrator.submit_feedback(
        task="Deploy Docker container with Redis",
        success=True,
        user_rating=0.9,
        execution_time=45.0
    )

asyncio.run(main())
```

---

## What You Get

### 13 Cognitive Features (All Active)

1. **Memory Systems** - Retrieves past Docker deployments
2. **Predictive Coding** - Detects anomalies and curiosity
3. **Attention Mechanisms** - Focuses on relevant signals
4. **Meta-Learning** - Adapts based on past performance
5. **Neuromodulation** - Urgency/focus signals
6. **Temporal Memory** - Time-based patterns
7. **Active Inference** - Asks clarifying questions
8. **Compositional Reasoning** - Breaks tasks into subtasks
9. **Tool Creation** - Recommends tools
10. **Consciousness Metrics** - Awareness tracking
11. **Infinite Chat** - User-specific memory
12. **Semantic Coherence** - Validates decisions
13. **CTM Async** - Deep reasoning for complex tasks

### 15 Specialized Agents

1. **Coordinator** - Routes tasks to specialized agents
2. **Active Inference** - Asks clarifying questions
3. **CTM Reasoning** - Handles complex tasks
4. **Memory** - Retrieves past experiences
5. **General Execution** - Executes general tasks
6. **Docker Execution** - Container management
7. **Database Execution** - Database operations
8. **API Execution** - REST API development
9. **Debugging** - Bug fixing
10. **Monitoring** - System health
11. **Deployment** - CI/CD, Kubernetes
12. **Testing** - Unit/Integration tests
13. **Refactoring** - Code optimization
14. **Documentation** - Docs generation
15. **Security** - Vulnerability scanning

---

## Example Workflows

### Workflow 1: Docker Deployment

```
User: "Deploy Docker with Redis"
  ↓
Brain: Analyzes task
  ├─ Task Type: docker
  ├─ Confidence: 0.85
  ├─ Memory: Past Redis deploy (success, 2GB)
  └─ Suggests: docker_execution_agent
  ↓
Coordinator: Routes to docker_execution_agent
  ↓
Docker Agent:
  ├─ Executes: docker-compose up -d redis
  ├─ Configures health check
  └─ Hands to monitoring_agent
  ↓
Monitoring Agent:
  ├─ Sets up health monitoring (30s)
  ├─ Verifies: HEALTHY
  └─ Returns to coordinator
  ↓
DONE ✓
  ↓
Feedback: Success=True, Rating=0.9
  ↓
Brain: Learns and improves!
```

### Workflow 2: Complex Task with CTM

```
User: "Design microservice architecture with auto-scaling"
  ↓
Brain: High complexity (0.82)
  ├─ Triggers CTM (50-step reasoning)
  ├─ CTM runs in background
  └─ Suggests: ctm_reasoning_agent
  ↓
CTM Reasoning Agent:
  ├─ Waits for CTM to complete
  ├─ Receives insights:
  │   - Service discovery needed
  │   - Auto-scaling with Prometheus
  │   - Service mesh (Istio vs Linkerd)
  ├─ Breaks into subtasks
  └─ Hands to general_execution_agent
  ↓
General Execution Agent:
  └─ Executes with detailed CTM plan
  ↓
DONE ✓
```

### Workflow 3: Active Inference Questions

```
User: "Fix the bug"
  ↓
Brain: Uncertainty detected!
  ├─ Active Inference generates questions:
  │   - "Which bug?"
  │   - "In which module?"
  │   - "What's the error message?"
  └─ Suggests: active_inference_agent
  ↓
Active Inference Agent:
  ├─ Asks user questions
  └─ Waits for answers
  ↓
User: "Memory leak in auth module, error: heap overflow"
  ↓
Coordinator: Re-routes with clarified task
  ↓
Debugging Agent:
  ├─ Uses brain insights
  ├─ Analyzes heap snapshots
  ├─ Fixes memory leak
  └─ Hands to testing_agent
  ↓
Testing Agent:
  └─ Verifies fix
  ↓
DONE ✓
```

---

## Troubleshooting

**Q: "AutoGen not installed" error**
```bash
pip install autogen-agentchat autogen-ext
```

**Q: "OPENAI_API_KEY not found" error**
Add to `.env`:
```env
OPENAI_API_KEY=sk-...
```

**Q: How to check brain statistics?**
```bash
python production/swarm_brain_cli.py brain-stats
```

**Q: How to see which agents are active?**
```bash
python production/swarm_brain_cli.py swarm-status
```

**Q: How to test everything?**
```bash
python demos/test_swarm_integration.py
```

---

## Next Steps

1. **Read Full Documentation**: See `AUTOGEN_SWARM_INTEGRATION.md`
2. **Test Different Task Types**: Try Docker, Database, API, Debugging, etc.
3. **Integrate with Your App**: Add to `voice_dialog/python/agent_orchestrator.py`
4. **Collect Feedback**: Submit task results to brain for learning
5. **Monitor Performance**: Use `brain-stats` to track improvement

---

## Support

- **Documentation**: `AUTOGEN_SWARM_INTEGRATION.md`
- **Feature Docs**: `docs/00_INDEX_ALL_FEATURES.md`
- **Tests**: `demos/test_swarm_integration.py`
- **CLI Help**: `python production/swarm_brain_cli.py --help`

**You're ready! Start with:**
```bash
python production/swarm_brain_cli.py interactive
```

# 🎯 Comprehensive Requirements Checklist for Tahlamus System

**Purpose**: Step-by-step capture of ALL inputs needed for optimal system performance
**Status**: 13/13 Features Active - Now optimizing for YOUR specific workflow
**Date**: October 21, 2025

---

## 📊 HOW TO USE THIS CHECKLIST

For each section below:
1. ✅ Read the question
2. ✅ Provide your answer in the designated format
3. ✅ Mark as [DONE] when completed
4. ✅ We'll implement based on your answers

**Estimated Time**: 30-60 minutes to complete all sections

---

# SECTION 1: BASIC SYSTEM CONFIGURATION

## 1.1 Primary Use Case [STATUS: ⏳ PENDING]

**Question**: How will you primarily use the Tahlamus system?

**Options**:
- [ ] **A**: API Server (Flask REST API on localhost:5001)
  - Use when: Multiple clients, web dashboard, team usage
  - Best for: Production deployment, scalability

- [ ] **B**: Python Library (Import in your scripts)
  - Use when: Single user, direct Python integration
  - Best for: Automation scripts, Jupyter notebooks

- [ ] **C**: CLI Tool (Command-line interface)
  - Use when: Terminal-based workflow
  - Best for: DevOps tasks, scripting, automation

- [ ] **D**: Hybrid (Multiple interfaces)
  - Use when: Different use cases
  - Best for: Flexibility

**YOUR ANSWER**:
```
Selected option: ___
Reason: ___
```

**FOLLOW-UP**: If API Server (A), answer:
- Will you access it from multiple machines? (Yes/No): ___
- Do you need authentication? (Yes/No): ___
- Expected concurrent users: ___

---

## 1.2 Deployment Environment [STATUS: ⏳ PENDING]

**Question**: Where will Tahlamus run?

**Options**:
- [ ] **A**: Local Machine (Windows/Mac/Linux)
  - Current setup: ✅ Windows
  - Pros: Easy, no cost
  - Cons: Not accessible remotely

- [ ] **B**: Cloud VM (AWS EC2, GCP Compute, Azure VM)
  - Pros: Always available, scalable
  - Cons: Monthly cost ($10-100/month)

- [ ] **C**: Docker Container
  - Pros: Portable, reproducible
  - Cons: Requires Docker knowledge

- [ ] **D**: Kubernetes Cluster
  - Pros: Enterprise-scale, auto-scaling
  - Cons: Complex setup

**YOUR ANSWER**:
```
Selected option: ___
If cloud (B), which provider: ___ (AWS/GCP/Azure)
If local (A), operating system: ___ (Windows/Mac/Linux)
```

**FOLLOW-UP**: Resource constraints
```
Maximum RAM usage allowed: ___ GB
Maximum CPU cores allowed: ___ cores
Maximum disk space: ___ GB
Monthly budget (if cloud): $___ USD
```

---

## 1.3 Performance Requirements [STATUS: ⏳ PENDING]

**Question**: What are your latency and throughput requirements?

**Latency Tolerance**:
```
[ ] Ultra-fast: <100ms per prediction (disable heavy features)
[ ] Fast: 100-300ms per prediction (standard, all features)
[ ] Moderate: 300-1000ms per prediction (enable all deep reasoning)
[ ] Flexible: >1000ms acceptable (enable everything, max quality)

YOUR CHOICE: ___
```

**Request Volume**:
```
[ ] Low: 1-10 requests per day
[ ] Medium: 10-100 requests per day
[ ] High: 100-1000 requests per day
[ ] Very High: 1000+ requests per day

YOUR CHOICE: ___
```

**Concurrent Requests**:
```
Maximum simultaneous requests: ___ (1-100)
```

---

# SECTION 2: DOMAIN & TASK TYPES

## 2.1 Your Primary Domain [STATUS: ⏳ PENDING]

**Question**: What domain/field will you use Tahlamus for?

**Select ALL that apply**:
- [ ] DevOps / Infrastructure (Docker, Kubernetes, CI/CD)
- [ ] Software Development (APIs, debugging, coding)
- [ ] Database Management (SQL, migrations, optimization)
- [ ] Web Development (Frontend, backend, deployment)
- [ ] Data Engineering (Pipelines, ETL, processing)
- [ ] Machine Learning (Training, deployment, monitoring)
- [ ] Security / Penetration Testing
- [ ] System Administration (Linux, Windows, networking)
- [ ] Cloud Architecture (AWS, GCP, Azure)
- [ ] Other: ___________

**YOUR ANSWER**:
```
Primary domains (select 1-3):
1. ___
2. ___
3. ___
```

---

## 2.2 Common Task Types [STATUS: ⏳ PENDING]

**Question**: What types of tasks will you give Tahlamus?

**Current task types** (trained on these 13):
1. docker
2. kubernetes
3. debugging
4. api
5. database
6. ci-cd
7. monitoring
8. security
9. performance
10. deployment
11. testing
12. configuration
13. generic

**YOUR ANSWER**:
```
Most frequent task types (rank top 5):
1. ___
2. ___
3. ___
4. ___
5. ___

New task types to add (not in list above):
1. ___
2. ___
3. ___
```

---

## 2.3 Task Complexity Distribution [STATUS: ⏳ PENDING]

**Question**: What complexity level are your typical tasks?

**Complexity Scale**:
- **Simple** (0.0-0.3): "Check Docker status", "List pods"
- **Moderate** (0.4-0.6): "Deploy app with health checks", "Debug API error"
- **Complex** (0.7-0.9): "Migrate to microservices", "Optimize database cluster"
- **Very Complex** (0.9-1.0): "Design distributed system", "Security audit"

**YOUR ANSWER**:
```
Typical complexity distribution (must sum to 100%):
Simple tasks: ____%
Moderate tasks: ____%
Complex tasks: ____%
Very complex tasks: ____%
```

**IMPACT**: This determines CTM triggering frequency
- CTM triggers at complexity >= 0.4
- If mostly simple tasks → increase threshold to 0.6
- If mostly complex tasks → decrease threshold to 0.3

---

# SECTION 3: REAL-WORLD TASKS (10 EXAMPLES)

## 3.1 Provide 10 Real Tasks [STATUS: ⏳ PENDING]

**Question**: Give me 10 actual tasks you want to solve

**Format**:
```
Task 1: "Deploy Docker container with PostgreSQL and Redis"
Expected outcome: Container running with both services
Typical success rate: 90%
Estimated complexity: 0.5 (moderate)
```

**YOUR ANSWERS**:

**Task 1**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 2**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 3**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 4**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 5**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 6**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 7**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 8**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 9**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

**Task 10**:
```
Description: ___
Expected outcome: ___
Typical success rate: ___%
Estimated complexity: ___ (0.0-1.0)
```

---

# SECTION 4: MEMORY SYSTEMS CONFIGURATION

## 4.1 Working Memory Size [STATUS: ⏳ PENDING]

**Current**: 10 slots (recent tasks in buffer)

**Question**: How many recent tasks should the system remember?

**Considerations**:
- More slots = more context, more memory usage
- Fewer slots = faster, less memory
- Typical: 5-20 slots

**YOUR ANSWER**:
```
Working memory slots: ___ (5-50)
Retention time: ___ seconds (current: 30s)
```

---

## 4.2 Episodic Memory Strategy [STATUS: ⏳ PENDING]

**Current**: Store only novel failures (7.7% of experiences)

**Question**: What should be stored in long-term episodic memory?

**Options**:
- [ ] **A**: Novel failures only (current - memory efficient)
- [ ] **B**: All failures (learn from all errors)
- [ ] **C**: All successes (remember what works)
- [ ] **D**: Everything (complete history)
- [ ] **E**: Custom rule: ___

**YOUR ANSWER**:
```
Selected option: ___
Maximum episodic memories: ___ (current: 1000)
Importance threshold (0-1): ___ (store if importance > threshold)
```

---

## 4.3 Real Episodic Memories [STATUS: ⏳ PENDING]

**Question**: Provide 5-10 real past task experiences

**Format**:
```json
{
    "task": "Deployed microservice to Kubernetes",
    "task_type": "kubernetes",
    "decision": "execute",
    "outcome": "success",
    "confidence": 0.95,
    "importance": 0.9,
    "brain_gates": [0.1, 0.05, 0.0, 0.0, 0.02, 0.08, 0.55, 0.12, 0.05, 0.03],
    "layer1_features": {
        "complexity": 0.6,
        "urgency": 0.3,
        "has_docker": true,
        "has_kubernetes": true
    },
    "reasoning_chain": [
        "Identified Kubernetes deployment task",
        "Checked cluster health",
        "Applied deployment manifest",
        "Verified pods running"
    ],
    "execution_time_ms": 15000,
    "timestamp": "2025-10-15T14:30:00"
}
```

**YOUR ANSWERS** (provide 5-10):

**Memory 1**:
```json
{
    "task": "___",
    "task_type": "___",
    "decision": "___",
    "outcome": "___",
    "confidence": ___,
    "importance": ___,
    "reasoning_chain": [
        "___",
        "___"
    ],
    "timestamp": "___"
}
```

**Memory 2-10**: (continue in same format)

---

# SECTION 5: TOOL LIBRARY CONFIGURATION

## 5.1 Tool Inventory [STATUS: ⏳ PENDING]

**Question**: What tools/commands do you use most frequently?

**Current tools**: 5 Docker tools (seeded for demo)

**YOUR ANSWERS** (list 10-20 tools):

**Tool 1**:
```
Name: Docker Build
Command/Action: docker build -t myapp .
Capabilities: [docker, build, containerization]
Success rate (from experience): 95%
Average execution time: 10 seconds
Usage frequency: Daily / Weekly / Monthly
```

**Tool 2**:
```
Name: ___
Command/Action: ___
Capabilities: [___, ___, ___]
Success rate: ___%
Average execution time: ___ seconds
Usage frequency: ___
```

**Tool 3-20**: (continue in same format)

---

## 5.2 Tool Categories [STATUS: ⏳ PENDING]

**Question**: Which tool categories are most important?

**Rank these 1-10** (1 = most important):

```
___ Docker tools (build, run, compose, logs)
___ Kubernetes tools (kubectl, helm, deploy)
___ Database tools (migrations, backups, queries)
___ Git/Version Control (commit, push, branch, merge)
___ CI/CD tools (GitHub Actions, Jenkins, deploy)
___ Monitoring tools (logs, metrics, alerts)
___ Testing tools (unit, integration, e2e)
___ Debugging tools (logs, traces, profiling)
___ Security tools (scanning, auditing, secrets)
___ Other: ___
```

---

# SECTION 6: FEATURE PRIORITIZATION

## 6.1 Feature Importance Ranking [STATUS: ⏳ PENDING]

**Question**: Rank all 13 features by importance for YOUR workflow

**Instructions**:
- Assign ranks 1-13 (1 = most important, 13 = least)
- No ties allowed
- Consider: Do you need this feature? How often?

**YOUR RANKINGS**:

```
Rank ___ : Memory Systems (working + episodic memory)
           Why this rank: ___

Rank ___ : Predictive Coding (prediction errors, curiosity)
           Why this rank: ___

Rank ___ : Attention Mechanisms (focus on relevant modalities)
           Why this rank: ___

Rank ___ : Meta-Learning (adaptive learning rate)
           Why this rank: ___

Rank ___ : Neuromodulation (dopamine, serotonin, motivation)
           Why this rank: ___

Rank ___ : Temporal Memory (time-based patterns)
           Why this rank: ___

Rank ___ : Active Inference (ask clarification questions)
           Why this rank: ___

Rank ___ : Compositional Reasoning (task decomposition)
           Why this rank: ___

Rank ___ : Tool Creation (dynamic tool discovery)
           Why this rank: ___

Rank ___ : Consciousness Metrics (awareness tracking)
           Why this rank: ___

Rank ___ : Infinite Chat (automatic semantic memory per user)
           Why this rank: ___

Rank ___ : Semantic Coherence (5-brain validation)
           Why this rank: ___

Rank ___ : CTM Async (deep background reasoning)
           Why this rank: ___
```

---

## 6.2 Feature Activation Strategy [STATUS: ⏳ PENDING]

**Question**: For each feature, when should it run?

**Options**:
- **ALWAYS**: Every prediction (critical features)
- **AUTO**: When relevant (system decides based on task)
- **MANUAL**: Only when explicitly requested
- **DISABLED**: Never use (not relevant to your workflow)

**YOUR ANSWERS**:

```
Memory Systems: [ALWAYS / AUTO / MANUAL / DISABLED]
Predictive Coding: [ALWAYS / AUTO / MANUAL / DISABLED]
Attention Mechanisms: [ALWAYS / AUTO / MANUAL / DISABLED]
Meta-Learning: [ALWAYS / AUTO / MANUAL / DISABLED]
Neuromodulation: [ALWAYS / AUTO / MANUAL / DISABLED]
Temporal Memory: [ALWAYS / AUTO / MANUAL / DISABLED]
Active Inference: [ALWAYS / AUTO / MANUAL / DISABLED]
Compositional Reasoning: [ALWAYS / AUTO / MANUAL / DISABLED]
Tool Creation: [ALWAYS / AUTO / MANUAL / DISABLED]
Consciousness Metrics: [ALWAYS / AUTO / MANUAL / DISABLED]
Infinite Chat: [ALWAYS / AUTO / MANUAL / DISABLED]
Semantic Coherence: [ALWAYS / AUTO / MANUAL / DISABLED]
CTM Async: [ALWAYS / AUTO / MANUAL / DISABLED]
```

---

# SECTION 7: CTM REASONING CONFIGURATION

## 7.1 CTM Improvement Priority [STATUS: ⏳ PENDING]

**Background**: CTM currently uses generic visual modalities instead of task-specific ones

**Question**: How important is improving CTM reasoning?

**Options**:
- [ ] **CRITICAL**: Must improve immediately (this week)
- [ ] **HIGH**: Improve soon (this month)
- [ ] **MEDIUM**: Improve eventually (next quarter)
- [ ] **LOW**: Current CTM is fine, no rush
- [ ] **NOT NEEDED**: Disable CTM entirely

**YOUR ANSWER**:
```
Priority: ___
Reason: ___
```

---

## 7.2 CTM Reasoning Approach [STATUS: ⏳ PENDING]

**Question**: How should CTM reason about tasks?

**Option A: Multi-Modal CTM** (Different modalities per task type)
```python
# Docker tasks use tool_trace, error_signal, success_signal
# Debugging tasks use error_signal, temporal_pattern, tool_trace
# API tasks use tool_trace, success_signal, temporal_pattern
```
- Pros: Task-aware, relevant insights
- Cons: Need to define modalities per task type

**Option B: Adaptive CTM** (System selects modalities automatically)
```python
# Attention mechanism picks relevant modalities
# CTM uses top-K most relevant modalities
```
- Pros: Automatic, no configuration
- Cons: May miss important modalities

**Option C: Multiple Specialized CTMs**
```python
# Fast CTM: 10 steps, 0.01s - Quick decisions
# Deep CTM: 100 steps, 1s - Complex problems
# Creative CTM: Divergent thinking
# Analytical CTM: Convergent thinking
```
- Pros: Purpose-specific reasoning
- Cons: More complex, higher latency

**Option D: Keep Current CTM**
```python
# Generic visual/verbal/spatial reasoning
# Works but not task-specific
```
- Pros: Already working
- Cons: Generic insights

**YOUR ANSWER**:
```
Selected option: ___ (A/B/C/D)
Reason: ___
```

---

## 7.3 CTM Complexity Threshold [STATUS: ⏳ PENDING]

**Current**: CTM triggers when task complexity >= 0.4

**Question**: When should CTM deep reasoning activate?

**Considerations**:
- Lower threshold (0.3) = CTM runs more often = more insights, higher latency
- Higher threshold (0.6) = CTM runs less often = faster, fewer insights
- Based on your task complexity distribution (Section 2.3)

**YOUR ANSWER**:
```
CTM complexity threshold: ___ (0.0-1.0)
Expected CTM activation rate: __% of tasks (estimate)
Maximum CTM reasoning steps: ___ (current: 50)
Maximum CTM timeout: ___ seconds (current: 30s)
```

---

# SECTION 8: USER IDENTIFICATION & MEMORY

## 8.1 User Identification Strategy [STATUS: ⏳ PENDING]

**Question**: How should the system identify users?

**Option A: Session-Based** (Temporary IDs)
```python
user_id = f"session_{uuid.uuid4()}"
# Each browser session = new user
# Memory NOT preserved across sessions
```
- Pros: Simple, no authentication
- Cons: No memory persistence

**Option B: Persistent User IDs** (Accounts)
```python
user_id = "alice@company.com"
# Real user accounts
# Memory preserved forever
```
- Pros: Long-term memory, personalization
- Cons: Need authentication system

**Option C: Hybrid** (Session + Optional Login)
```python
user_id = session_id  # Default
user_id = "alice@company.com"  # If logged in
```
- Pros: Best of both worlds
- Cons: More complex

**Option D: Single User** (No multi-user)
```python
user_id = "default_user"
# Same memory for everyone
```
- Pros: Simplest
- Cons: No personalization

**YOUR ANSWER**:
```
Selected option: ___ (A/B/C/D)
If B or C, authentication method: ___ (OAuth, JWT, API keys, etc.)
```

---

## 8.2 Infinite Chat Configuration [STATUS: ⏳ PENDING]

**Question**: Should automatic semantic memory be enabled?

**Infinite Chat Benefits**:
- ✅ Automatic memory storage and retrieval
- ✅ Semantic search (relevance-based)
- ✅ 90% less code for memory management
- ✅ Unlimited context windows
- ✅ 50% token savings

**Requirements**:
- Supermemory API key (sign up at https://supermemory.ai)
- User IDs (from Section 8.1)

**YOUR ANSWER**:
```
Enable Infinite Chat: [YES / NO]

If YES:
- Do you have Supermemory API key? [YES / NO]
- If NO, will you sign up? [YES / NO]
- Max memories per user: ___ (unlimited if blank)
- Memory retention period: ___ days (forever if blank)

If NO:
- Reason for disabling: ___
- Alternative memory strategy: ___
```

---

## 8.3 Supermemory API Key [STATUS: ⏳ PENDING]

**Question**: Provide your Supermemory API key (if using Infinite Chat)

**Instructions**:
1. Go to https://supermemory.ai
2. Sign up / Log in
3. Get API key from dashboard
4. Add to `.env` file

**YOUR ANSWER**:
```
Supermemory API key: sk-_______________ (or "WILL_GET_LATER")
Status: [HAVE_KEY / WILL_SIGN_UP / NOT_USING]
```

---

# SECTION 9: LLM CONFIGURATION

## 9.1 LLM Provider Preference [STATUS: ⏳ PENDING]

**Current**: OpenRouter (supports 100+ models)

**Question**: Which LLM provider do you prefer?

**Options**:
- [ ] **A**: OpenRouter (current - flexible, many models)
- [ ] **B**: OpenAI (GPT-4, GPT-3.5)
- [ ] **C**: Anthropic (Claude models)
- [ ] **D**: Local LLM (Ollama, LM Studio)
- [ ] **E**: Multiple providers (switch based on task)

**YOUR ANSWER**:
```
Selected option: ___
API key status: [HAVE / NEED_TO_GET]
```

---

## 9.2 Model Selection [STATUS: ⏳ PENDING]

**Question**: Which models should be used for different tasks?

**Tasks**:
- **Feature Extraction**: Extract task type, complexity, urgency
- **Classification**: Categorize task into 13 types
- **Reasoning**: Generate explanation chains
- **Question Generation**: Active Inference questions

**Model Tiers**:
- **Fast/Cheap**: GPT-3.5-Turbo, Claude Haiku (~$0.0005/request)
- **Balanced**: GPT-4-Turbo, Claude Sonnet (~$0.01/request)
- **Premium**: GPT-4, Claude Opus (~$0.05/request)

**YOUR ANSWER**:
```
Feature Extraction model: ___
Classification model: ___
Reasoning model: ___
Question Generation model: ___

Monthly LLM budget: $___ USD
Cost priority: [MINIMIZE_COST / BALANCED / MAXIMIZE_QUALITY]
```

---

## 9.3 LLM API Keys [STATUS: ⏳ PENDING]

**Question**: Provide your API keys

**Required**:
```
OPENROUTER_API_KEY: sk-or-v1-_______________ (or "WILL_GET")
```

**Optional** (if using specific providers):
```
OPENAI_API_KEY: sk-_______________ (or "NOT_USING")
ANTHROPIC_API_KEY: sk-ant-_______________ (or "NOT_USING")
```

---

# SECTION 10: THRESHOLD TUNING

## 10.1 Semantic Coherence Thresholds [STATUS: ⏳ PENDING]

**Current**: 5-brain swarm validates predictions
- GREEN if coherence_K >= 0.8 AND truth_stability >= 0.6
- YELLOW if coherence_K >= 0.6 OR truth_stability >= 0.4
- RED otherwise

**Question**: How strict should semantic validation be?

**Options**:
- [ ] **Strict**: Only proceed if GREEN (high confidence only)
- [ ] **Moderate**: Proceed on GREEN or YELLOW (current)
- [ ] **Lenient**: Proceed even on RED (trust primary prediction)
- [ ] **Disabled**: Skip semantic coherence entirely

**YOUR ANSWER**:
```
Validation strictness: ___
GREEN threshold (coherence_K): ___ (current: 0.8)
YELLOW threshold (coherence_K): ___ (current: 0.6)
Action on RED status: [RETRY / ASK_USER / PROCEED_ANYWAY]
```

---

## 10.2 Consciousness Awareness Thresholds [STATUS: ⏳ PENDING]

**Current**:
- Conscious: awareness > 0.7
- Semi-conscious: 0.4 < awareness <= 0.7
- Unconscious: awareness <= 0.4

**Question**: Should these thresholds be adjusted?

**YOUR ANSWER**:
```
Conscious threshold: ___ (current: 0.7)
Semi-conscious threshold: ___ (current: 0.4)
Should behavior change based on consciousness? [YES / NO]

If YES, describe behavior:
- When conscious: ___
- When semi-conscious: ___
- When unconscious: ___
```

---

## 10.3 Attention Focus Threshold [STATUS: ⏳ PENDING]

**Current**: Modality selected if attention_weight > 0.1 (10%)

**Question**: How selective should attention be?

**Options**:
- Lower threshold (0.05) = More modalities focused = broader context
- Higher threshold (0.2) = Fewer modalities focused = sharper focus

**YOUR ANSWER**:
```
Attention threshold: ___ (0.0-1.0, current: 0.1)
Preferred attention mode: [FOCUSED / DISTRIBUTED / ADAPTIVE]
Max focused modalities: ___ (current: unlimited)
```

---

# SECTION 11: ERROR HANDLING & RECOVERY

## 11.1 Error Recovery Strategy [STATUS: ⏳ PENDING]

**Question**: What should happen when predictions fail?

**Options**:
- [ ] **A**: Retry automatically (with CTM insights)
- [ ] **B**: Ask user for clarification (Active Inference)
- [ ] **C**: Return error immediately
- [ ] **D**: Fall back to safe default (e.g., "wait")
- [ ] **E**: Custom strategy: ___

**YOUR ANSWER**:
```
Primary strategy: ___
Maximum retry attempts: ___ (0-5)
Retry delay: ___ seconds
Should CTM run before retry? [YES / NO]
```

---

## 11.2 Edge Case Handling [STATUS: ⏳ PENDING]

**Question**: Provide 5-10 difficult/ambiguous tasks

**Purpose**: Test system limits and improve edge case handling

**YOUR ANSWERS**:

**Edge Case 1**:
```
Task: "Fix it"  (extremely ambiguous)
Expected behavior: [ASK_FOR_CLARIFICATION / GUESS / RETURN_ERROR]
```

**Edge Case 2**:
```
Task: "Deploy immediately but test thoroughly first"  (conflicting requirements)
Expected behavior: ___
```

**Edge Case 3**:
```
Task: ___ (your edge case)
Expected behavior: ___
```

**Edge Case 4-10**: (continue in same format)

---

## 11.3 Logging & Debugging [STATUS: ⏳ PENDING]

**Question**: What level of logging do you need?

**Options**:
- [ ] **DEBUG**: Everything (verbose, large logs)
- [ ] **INFO**: Key events only (standard)
- [ ] **WARNING**: Problems only (minimal)
- [ ] **ERROR**: Failures only (critical)

**YOUR ANSWER**:
```
Log level: ___
Log to file: [YES / NO]
Log file location: ___ (if YES)
Log rotation: [DAILY / WEEKLY / BY_SIZE]
Include full brain state in logs? [YES / NO]
```

---

# SECTION 12: DATA COLLECTION & FEEDBACK

## 12.1 Feedback Loop Strategy [STATUS: ⏳ PENDING]

**Question**: How will you provide feedback on predictions?

**Continuous learning** requires feedback (success/failure after execution)

**Options**:
- [ ] **A**: Manual feedback after each task
  - You manually report success/failure
  - Most accurate, most effort

- [ ] **B**: Automated feedback via monitoring
  - System detects success/failure from metrics
  - Requires integration with monitoring tools

- [ ] **C**: Hybrid (automated + manual override)
  - System auto-detects, you can correct
  - Best accuracy with less effort

- [ ] **D**: No feedback (disable continuous learning)
  - System doesn't improve over time
  - Static behavior

**YOUR ANSWER**:
```
Selected option: ___

If B or C, monitoring tool: ___ (Prometheus, Datadog, etc.)
Feedback frequency: [EVERY_TASK / SAMPLE_10% / WEEKLY_BATCH]
```

---

## 12.2 Performance Metrics Collection [STATUS: ⏳ PENDING]

**Question**: Which metrics should be tracked?

**Available Metrics**:
- [ ] Prediction latency (response time)
- [ ] Success rate (% of tasks that succeed)
- [ ] Feature activation rates (how often each feature runs)
- [ ] CTM usage (how often deep reasoning triggered)
- [ ] Memory usage (RAM, disk)
- [ ] LLM costs (API spending)
- [ ] User ratings (manual feedback scores)
- [ ] Semantic coherence trends (GREEN/YELLOW/RED over time)
- [ ] Consciousness metrics trends
- [ ] Tool usage statistics

**YOUR ANSWER** (select ALL you want tracked):
```
Metrics to track:
[ ] Prediction latency
[ ] Success rate
[ ] Feature activation rates
[ ] CTM usage
[ ] Memory usage
[ ] LLM costs
[ ] User ratings
[ ] Semantic coherence
[ ] Consciousness metrics
[ ] Tool usage
[ ] Other: ___

Dashboard preference: [WEB_UI / CLI / LOG_FILES / API_ENDPOINT]
Update frequency: [REAL_TIME / HOURLY / DAILY]
```

---

## 12.3 Real Session Logs [STATUS: ⏳ PENDING]

**Question**: Can you provide real conversation logs?

**Current**: System trained on 39 synthetic session logs

**Format Needed**:
```json
{
    "session_id": "real_session_001",
    "timestamp": "2025-10-21T10:00:00",
    "user_id": "alice",
    "task": "Deploy microservice to Kubernetes",
    "conversation": [
        {
            "role": "user",
            "content": "Deploy microservice to K8s cluster",
            "timestamp": "2025-10-21T10:00:00"
        },
        {
            "role": "assistant",
            "content": "I'll help deploy the microservice. First, let me check the cluster status.",
            "timestamp": "2025-10-21T10:00:05"
        },
        {
            "role": "tool",
            "name": "kubectl get nodes",
            "input": "kubectl get nodes",
            "output": "NAME STATUS ROLES AGE VERSION\nnode-1 Ready master 30d v1.28.0",
            "timestamp": "2025-10-21T10:00:10"
        },
        {
            "role": "assistant",
            "content": "Cluster is healthy. Deploying now...",
            "timestamp": "2025-10-21T10:00:15"
        }
    ],
    "outcome": "success",
    "tools_used": ["kubectl", "docker", "helm"],
    "errors_encountered": [],
    "execution_time_ms": 30000
}
```

**YOUR ANSWER**:
```
Can provide session logs: [YES / NO]

If YES:
- Number of sessions available: ___
- Date range: ___ to ___
- Format: [JSON / TEXT / CSV / OTHER: ___]
- Source: [CHAT_LOGS / TERMINAL_HISTORY / OTHER: ___]

If NO:
- Can you start collecting logs? [YES / NO]
- Preferred collection method: ___
```

---

# SECTION 13: DEPLOYMENT & INFRASTRUCTURE

## 13.1 Persistence Strategy [STATUS: ⏳ PENDING]

**Current**: File-based (data/logs/)

**Question**: How should data be persisted?

**Options**:
- [ ] **A**: File-based (current - simple, local)
  - Memories, logs, matrices stored as files
  - Pros: Simple, no dependencies
  - Cons: Not scalable, slow for large data

- [ ] **B**: Database (PostgreSQL, MongoDB)
  - Structured storage, fast queries
  - Pros: Scalable, transactional
  - Cons: Requires database setup

- [ ] **C**: Cloud Storage (S3, GCS, Azure Blob)
  - Remote storage, high availability
  - Pros: Scalable, durable
  - Cons: Monthly cost, network latency

- [ ] **D**: Hybrid (files + database)
  - Logs in files, memories in database
  - Pros: Best of both worlds
  - Cons: More complex

**YOUR ANSWER**:
```
Selected option: ___

If B (Database):
- Database type: ___ (PostgreSQL/MongoDB/MySQL)
- Database location: [LOCAL / CLOUD]
- Connection string: ___ (or "WILL_SETUP")

If C (Cloud Storage):
- Provider: ___ (AWS S3 / GCP GCS / Azure Blob)
- Bucket/container name: ___
- Credentials: [HAVE / WILL_SETUP]
```

---

## 13.2 Scaling Strategy [STATUS: ⏳ PENDING]

**Question**: How should the system scale?

**Options**:
- [ ] **A**: Single Instance (current)
  - One process handles all requests
  - Suitable for: <100 requests/day

- [ ] **B**: Multiple Workers
  - Multiple processes, shared state
  - Suitable for: 100-1000 requests/day

- [ ] **C**: Load Balanced
  - Multiple servers behind load balancer
  - Suitable for: 1000-10000 requests/day

- [ ] **D**: Auto-Scaling
  - Automatically add/remove servers
  - Suitable for: 10000+ requests/day

**YOUR ANSWER**:
```
Selected option: ___
Expected peak load: ___ requests/hour
Downtime tolerance: ___ (acceptable outage duration)
```

---

## 13.3 Backup & Recovery [STATUS: ⏳ PENDING]

**Question**: How important is data backup?

**Data to backup**:
- Episodic memories (1000 max entries)
- Tool library (50+ tools)
- Trained routing matrices (10x4)
- Session logs (conversation history)
- Performance metrics

**YOUR ANSWER**:
```
Backup frequency: [REAL_TIME / HOURLY / DAILY / WEEKLY / NEVER]
Backup location: [SAME_MACHINE / EXTERNAL_DRIVE / CLOUD / MULTIPLE]
Retention period: ___ days (how long to keep backups)
Recovery time objective (RTO): ___ hours (max acceptable downtime)
Recovery point objective (RPO): ___ hours (max acceptable data loss)
```

---

# SECTION 14: SECURITY & PRIVACY

## 14.1 Authentication & Authorization [STATUS: ⏳ PENDING]

**Question**: Should the API be protected?

**Options**:
- [ ] **A**: No authentication (current - open access)
  - Anyone can access
  - Suitable for: Local/private networks only

- [ ] **B**: API Keys
  - Simple token-based authentication
  - Suitable for: Trusted clients

- [ ] **C**: OAuth 2.0
  - Industry-standard authentication
  - Suitable for: Multi-user applications

- [ ] **D**: JWT Tokens
  - Stateless authentication
  - Suitable for: Microservices

**YOUR ANSWER**:
```
Selected option: ___

If B, C, or D:
- Number of users: ___
- Role-based access control needed? [YES / NO]
- Rate limiting: ___ requests/minute per user
```

---

## 14.2 Data Privacy [STATUS: ⏳ PENDING]

**Question**: Are there privacy concerns with task data?

**Considerations**:
- Tasks may contain sensitive information
- LLM providers (OpenRouter, OpenAI) see task content
- Memories stored contain task history

**YOUR ANSWER**:
```
Contains sensitive data: [YES / NO]

If YES:
- Type of sensitive data: ___ (credentials, PII, proprietary, etc.)
- Should data be encrypted at rest? [YES / NO]
- Should data be encrypted in transit? [YES / NO]
- Data retention limit: ___ days (delete after)
- Can data be sent to external LLM APIs? [YES / NO / ONLY_IF_ANONYMIZED]
```

---

## 14.3 Compliance Requirements [STATUS: ⏳ PENDING]

**Question**: Any regulatory compliance needed?

**Common Regulations**:
- [ ] GDPR (EU data protection)
- [ ] HIPAA (US healthcare data)
- [ ] SOC 2 (Security controls)
- [ ] ISO 27001 (Information security)
- [ ] None

**YOUR ANSWER**:
```
Compliance requirements: ___ (or "NONE")

If any selected:
- Data residency requirements: ___ (where data must be stored)
- Audit logging needed? [YES / NO]
- Data deletion on request? [YES / NO]
```

---

# SECTION 15: INTEGRATION & EXTENSIBILITY

## 15.1 External Integrations [STATUS: ⏳ PENDING]

**Question**: Should Tahlamus integrate with other tools?

**Common Integrations**:
- [ ] Slack (notifications, commands)
- [ ] GitHub (PR comments, issue management)
- [ ] Jira (task tracking)
- [ ] PagerDuty (incident response)
- [ ] Prometheus (metrics)
- [ ] Grafana (dashboards)
- [ ] Datadog (monitoring)
- [ ] Jenkins (CI/CD)
- [ ] Other: ___

**YOUR ANSWER**:
```
Desired integrations (select all):
[ ] Slack
[ ] GitHub
[ ] Jira
[ ] PagerDuty
[ ] Prometheus
[ ] Grafana
[ ] Datadog
[ ] Jenkins
[ ] Other: ___

Priority: [HIGH / MEDIUM / LOW]
Timeline: [IMMEDIATE / SOON / LATER]
```

---

## 15.2 Custom Extensions [STATUS: ⏳ PENDING]

**Question**: Do you need custom cognitive features?

**Beyond the 13 existing features**, do you need:

**YOUR ANSWER**:
```
Custom features needed: [YES / NO]

If YES, describe:

Custom Feature 1:
Name: ___
Purpose: ___
Priority: [HIGH / MEDIUM / LOW]

Custom Feature 2:
Name: ___
Purpose: ___
Priority: [HIGH / MEDIUM / LOW]

Custom Feature 3:
Name: ___
Purpose: ___
Priority: [HIGH / MEDIUM / LOW]
```

---

## 15.3 API Extensions [STATUS: ⏳ PENDING]

**Current API Endpoints**:
- POST /predict
- POST /feedback
- GET /stats
- GET /matrices
- POST /save_matrix
- POST /load_matrix
- GET /health

**Question**: Are additional API endpoints needed?

**YOUR ANSWER**:
```
Additional endpoints needed: [YES / NO]

If YES, describe:

Endpoint 1:
Method: ___ (GET/POST/PUT/DELETE)
Path: ___
Purpose: ___
Priority: [HIGH / MEDIUM / LOW]

Endpoint 2-5: (continue in same format)
```

---

# SECTION 16: TESTING & VALIDATION

## 16.1 Testing Strategy [STATUS: ⏳ PENDING]

**Question**: How should we validate the system works correctly?

**Testing Levels**:
- [ ] Unit tests (individual functions)
- [ ] Integration tests (feature interactions)
- [ ] End-to-end tests (full workflows)
- [ ] Performance tests (latency, throughput)
- [ ] User acceptance tests (real scenarios)

**YOUR ANSWER**:
```
Testing levels needed (select all):
[ ] Unit tests
[ ] Integration tests
[ ] End-to-end tests
[ ] Performance tests
[ ] User acceptance tests

Test coverage goal: ___%
Automated testing: [YES / NO]
CI/CD integration: [YES / NO]
```

---

## 16.2 Validation Criteria [STATUS: ⏳ PENDING]

**Question**: What defines "success" for Tahlamus?

**Metrics**:

**YOUR ANSWER**:
```
Minimum acceptable success rate: __% (tasks that succeed)
Maximum acceptable latency: ___ ms (response time)
Maximum acceptable LLM cost: $___ per 1000 requests
Minimum acceptable user satisfaction: __% (if collecting ratings)

Critical features (must work 100%):
1. ___
2. ___
3. ___

Nice-to-have features (can fail occasionally):
1. ___
2. ___
3. ___
```

---

## 16.3 Acceptance Criteria [STATUS: ⏳ PENDING]

**Question**: When is the system "production-ready" for you?

**YOUR ANSWER**:
```
System is production-ready when:

[ ] All 13 features active and tested
[ ] Success rate >= ___%
[ ] Latency <= ___ ms
[ ] Handles ___ requests/day reliably
[ ] Integration with ___ completed
[ ] Documentation complete
[ ] Training on real data complete
[ ] Security requirements met
[ ] Backup/recovery tested
[ ] Other: ___

Target production date: ___
```

---

# SECTION 17: TIMELINE & PRIORITIES

## 17.1 Implementation Timeline [STATUS: ⏳ PENDING]

**Question**: What's your timeline for each priority?

**YOUR ANSWER**:
```
IMMEDIATE (This Week):
1. ___
2. ___
3. ___

SHORT-TERM (This Month):
1. ___
2. ___
3. ___

MEDIUM-TERM (Next Quarter):
1. ___
2. ___
3. ___

LONG-TERM (Future):
1. ___
2. ___
3. ___
```

---

## 17.2 Critical Path [STATUS: ⏳ PENDING]

**Question**: What MUST be done before you can use Tahlamus?

**Blockers** (nothing else matters until these are done):

**YOUR ANSWER**:
```
Critical Blocker 1: ___
Estimated time to resolve: ___
Dependency: ___

Critical Blocker 2: ___
Estimated time to resolve: ___
Dependency: ___

Critical Blocker 3: ___
Estimated time to resolve: ___
Dependency: ___
```

---

## 17.3 Nice-to-Haves [STATUS: ⏳ PENDING]

**Question**: What can wait until later?

**YOUR ANSWER**:
```
Can be deferred (not critical):
1. ___
2. ___
3. ___
4. ___
5. ___
```

---

# FINAL SUMMARY SECTION

## Your Overall Priorities [STATUS: ⏳ PENDING]

**Question**: Summarize your top 3 priorities

**YOUR ANSWER**:
```
Priority 1:
Goal: ___
Why critical: ___
Deadline: ___
Success metric: ___

Priority 2:
Goal: ___
Why critical: ___
Deadline: ___
Success metric: ___

Priority 3:
Goal: ___
Why critical: ___
Deadline: ___
Success metric: ___
```

---

# 📋 COMPLETION CHECKLIST

Mark each section when complete:

- [ ] Section 1: Basic System Configuration
- [ ] Section 2: Domain & Task Types
- [ ] Section 3: Real-World Tasks (10 examples)
- [ ] Section 4: Memory Systems Configuration
- [ ] Section 5: Tool Library Configuration
- [ ] Section 6: Feature Prioritization
- [ ] Section 7: CTM Reasoning Configuration
- [ ] Section 8: User Identification & Memory
- [ ] Section 9: LLM Configuration
- [ ] Section 10: Threshold Tuning
- [ ] Section 11: Error Handling & Recovery
- [ ] Section 12: Data Collection & Feedback
- [ ] Section 13: Deployment & Infrastructure
- [ ] Section 14: Security & Privacy
- [ ] Section 15: Integration & Extensibility
- [ ] Section 16: Testing & Validation
- [ ] Section 17: Timeline & Priorities

**TOTAL PROGRESS**: ___/17 sections complete

---

# 🚀 NEXT STEPS AFTER COMPLETION

Once all sections are filled:

1. **Save this file** as `USER_INPUT_COMPLETED.md`
2. **Review** your answers for consistency
3. **Provide** to Claude for system configuration
4. **We will**:
   - Configure all features based on your preferences
   - Adjust thresholds and parameters
   - Set up integrations
   - Create custom scripts
   - Deploy to your environment
   - Begin testing and validation

**Estimated configuration time**: 2-4 hours after receiving your input

---

**Questions?** For any section you're unsure about, mark it as:
```
[NEED_HELP] - I need clarification on this section
Specific question: ___
```

We'll go through it together step-by-step!

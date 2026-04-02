---
name: chunk-planning
description: Intelligently chunks and schedules requirements for parallel code generation. Uses LLM analysis for service grouping, dependency detection, complexity scoring, and load balancing across workers.
---

# Chunk Planning Skill

You are the Chunk Planner for the Society of Mind autonomous code generation system.

## Purpose

Analyze requirements and create an optimal execution plan:
- Group related requirements by service domain
- Detect dependencies between features
- Score complexity for time estimation
- Balance load across available workers
- Create parallel execution waves

## Trigger Events

| Event | Action |
|-------|--------|
| Phase 2 Start | Create execution plan for requirements |
| `CHUNK_REPLAN_NEEDED` | Adjust plan based on failures |

## Workflow

### 1. Analyze Requirements

Parse requirements JSON and identify:
- Service domains (auth, user, payment, dashboard)
- Shared dependencies (what must come first)
- Technical complexity indicators

### 2. Group by Service

```
┌──────────────────────────────────────────────────────────────┐
│  Requirements Analysis                                        │
├──────────────────────────────────────────────────────────────┤
│  Auth Service:                                                │
│    - REQ_001: User Login                                      │
│    - REQ_002: User Logout                                     │
│    - REQ_003: Password Reset                                  │
│                                                               │
│  User Service (depends on Auth):                              │
│    - REQ_004: User Profile View                               │
│    - REQ_005: User Profile Edit                               │
│    - REQ_006: User Avatar Upload                              │
│                                                               │
│  Dashboard Service (depends on Auth, User):                   │
│    - REQ_007: Dashboard Layout                                │
│    - REQ_008: User Stats Widget                               │
│    - REQ_009: Activity Chart                                  │
└──────────────────────────────────────────────────────────────┘
```

### 3. Score Complexity

| Level | Criteria | Time Estimate |
|-------|----------|---------------|
| `simple` | 1-2 files, standard CRUD, no external API | 3 minutes |
| `medium` | 3-5 files, some logic, local state | 5 minutes |
| `complex` | 5+ files, external APIs, security, complex logic | 10 minutes |

Complexity indicators:
- External API integration → complex
- Authentication/Authorization → complex
- File upload/storage → complex
- Real-time features → complex
- Simple forms → simple
- Display components → simple
- CRUD operations → medium

### 4. Build Dependency Graph

```
Auth ──────────────────┐
  │                    │
  ▼                    │
User ──────┐           │
  │        │           │
  ▼        ▼           ▼
Profile  Settings   Dashboard
  │                    │
  ▼                    ▼
Avatar               Charts
```

### 5. Create Execution Waves

Topologically sort dependencies into parallel waves:

```
Wave 1 (parallel, no dependencies):
  ├── Auth Login     [Worker 1] (simple)
  ├── Auth Logout    [Worker 1] (simple)
  ├── Auth Register  [Worker 2] (simple)
  └── Dashboard Layout [Worker 3] (simple)

Wave 2 (after Auth complete):
  ├── User Profile   [Worker 1] (medium)
  ├── User Settings  [Worker 2] (medium)
  └── Dashboard Nav  [Worker 3] (simple)

Wave 3 (after User complete):
  ├── Avatar Upload  [Worker 1] (medium)
  ├── User Stats Widget [Worker 2] (medium)
  └── Activity Chart [Worker 3] (complex)
```

### 6. Balance Load

Distribute chunks to minimize total execution time:

```
Worker 1: [Auth:3min] → [Profile:5min] → [Avatar:5min] = 13 min
Worker 2: [Register:3min] → [Settings:5min] → [Stats:5min] = 13 min
Worker 3: [Layout:3min] → [Nav:3min] → [Chart:10min] = 16 min

Total: 16 min (longest worker)
Sequential: 42 min
Speedup: 2.6x
```

## Output Format: ExecutionPlan

```json
{
  "waves": [
    {
      "wave_id": 1,
      "chunks": ["chunk_001", "chunk_002", "chunk_003"],
      "blocked_by": [],
      "estimated_minutes": 3
    },
    {
      "wave_id": 2,
      "chunks": ["chunk_004", "chunk_005", "chunk_006"],
      "blocked_by": ["chunk_001", "chunk_002"],
      "estimated_minutes": 5
    }
  ],
  "worker_assignments": [
    {
      "worker_id": 1,
      "chunks": [
        {"chunk_id": "chunk_001", "requirements": ["REQ_001", "REQ_002"]},
        {"chunk_id": "chunk_004", "requirements": ["REQ_004"]}
      ],
      "estimated_duration_minutes": 8
    }
  ],
  "chunks": [
    {
      "chunk_id": "chunk_001",
      "requirements": ["REQ_001", "REQ_002"],
      "service_group": "auth",
      "complexity": "simple",
      "depends_on_chunks": [],
      "estimated_minutes": 3
    }
  ],
  "service_groups": [
    {
      "service_name": "auth",
      "requirements": ["REQ_001", "REQ_002", "REQ_003"],
      "estimated_files": ["src/auth/Login.tsx", "src/auth/api.ts"],
      "complexity": "simple",
      "depends_on": []
    }
  ],
  "total_estimated_minutes": 16,
  "sequential_estimated_minutes": 42,
  "parallelization_factor": 2.6,
  "reasoning": "Grouped auth features together since they share context. User features depend on auth. Dashboard layout can start parallel since it only needs styling."
}
```

## Chunking Rules

### Maximum Chunk Size
- Max 5 requirements per chunk (configurable)
- Min 1 requirement per chunk

### Grouping Priority
1. Same service domain (auth, user, payment)
2. Shared file dependencies
3. Similar complexity level
4. Dependency relationships

### Load Balancing
- Target: All workers finish within 20% of each other
- Formula: `variance(worker_times) / mean(worker_times) < 0.2`

## Configuration

From `config/society_defaults.json`:
```json
{
  "intelligent_chunking": true,
  "chunk_planner_llm": true,
  "max_requirements_per_chunk": 5,
  "min_requirements_per_chunk": 1,
  "chunk_time_simple": 3,
  "chunk_time_medium": 5,
  "chunk_time_complex": 10,
  "load_balance_threshold": 0.2
}
```

## Communication

### Publish Events

```python
event_bus.publish(Event(
    type=EventType.EXECUTION_PLAN_CREATED,
    source="chunk-planning",
    data={
        "total_chunks": 12,
        "total_waves": 4,
        "workers": 5,
        "estimated_minutes": 16,
        "speedup": "2.6x"
    }
))
```

## Visual Output

```
╔═══════════════════════════════════════════════════════════════════╗
║  EXECUTION PLAN - 20 Requirements, 5 Workers                      ║
╠═══════════════════════════════════════════════════════════════════╣
║  Wave 1 (3 Min):                                                  ║
║    Worker 1: [Auth] Login, Logout, Register         (simple)      ║
║    Worker 2: [User] Profile View, Edit              (medium)      ║
║    Worker 3: [Dashboard] Layout, Navigation         (simple)      ║
║                                                                   ║
║  Wave 2 (5 Min):                                                  ║
║    Worker 1: [User] Avatar, Settings                (medium)      ║
║    Worker 2: [Payment] Setup, Process               (complex)     ║
║    Worker 3: [Dashboard] Widgets, Cards             (medium)      ║
║                                                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║  Total: 16 Min | Sequential: 42 Min | Speedup: 2.6x              ║
╚═══════════════════════════════════════════════════════════════════╝
```

## Best Practices

1. **Keep Related Code Together** - Same service, same chunk
2. **Respect Dependencies** - Don't schedule before prerequisites
3. **Balance Workers** - Avoid one worker doing all the work
4. **Account for Complexity** - Complex chunks need more time
5. **Plan for Failure** - Be ready to replan if chunks fail

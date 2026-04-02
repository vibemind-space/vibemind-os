# Tool Creation (Phase 10)

## Overview

**Purpose**: Dynamically find or create tools for task execution
**Inspired by**: Tool use in primates, program synthesis
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│           TOOL CREATION SYSTEM                       │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │ Capability │───▶│    Tool    │───▶│  Matching │ │
│  │    Need    │    │  Library   │    │   Tools   │ │
│  │            │    │            │    │           │ │
│  │   docker   │    │ 50+ tools  │    │  Docker   │ │
│  │  redis     │    │ indexed by │    │  Build,   │ │
│  │  health    │    │capability  │    │  Health   │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│   Task Analysis     Tool Search        Selection    │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Tool Library** (`core/tool_creation.py:50-130`)
- Repository of available tools
- Indexed by capabilities
- Success rates and usage statistics

**2. Capability Analyzer** (`core/tool_creation.py:132-200`)
- Identifies required capabilities from task
- Maps task keywords to capabilities
- Detects missing capabilities

**3. Tool Matcher** (`core/tool_creation.py:202-280`)
- Searches library for matching tools
- Scores tools by relevance
- Returns best matches

---

## Input

### From HierarchicalPlanner
```python
{
    "capability": str,           # Required capability (e.g., 'docker')
    "task_context": {
        "task_type": str,        # Task category
        "complexity": float,     # 0-1
        "keywords": List[str]    # ['docker', 'redis', 'health']
    },
    "prefer_specialized": bool   # True for specialized tools
}
```

### Tool Structure
```python
class Tool:
    tool_id: str
    tool_name: str
    tool_type: str              # 'primitive', 'composite', 'meta'
    capabilities: List[str]      # ['docker', 'health', 'monitoring']
    success_rate: float         # 0-1
    usage_count: int
    avg_execution_time: float
    specialization_score: float # How specific to capability
```

---

## Processing

### 1. Identify Required Capability
```python
# Location: core/tool_creation.py:50-130

def identify_capability_gap(task_description, task_type):
    # Extract required capabilities from task

    capabilities = []

    # Keyword-based capability extraction
    capability_keywords = {
        'docker': ['docker', 'container', 'dockerfile'],
        'redis': ['redis', 'cache', 'key-value'],
        'health': ['health', 'monitoring', 'check'],
        'api': ['api', 'endpoint', 'rest'],
        'debugging': ['debug', 'error', 'fix']
    }

    # Search for keywords
    task_lower = task_description.lower()
    for capability, keywords in capability_keywords.items():
        if any(kw in task_lower for kw in keywords):
            capabilities.append(capability)

    # Fallback to task_type
    if not capabilities:
        capabilities = [task_type]

    return capabilities
```

### 2. Search Tool Library
```python
# Location: core/tool_creation.py:132-200

def get_tool_for_capability(capability, prefer_specialized=True):
    # Search tool library for matching tools

    matching_tools = []

    for tool_id, tool in self.tools.items():
        # Check if tool has required capability
        if capability in tool.capabilities:
            # Compute relevance score
            relevance = (
                tool.success_rate * 0.5 +           # Success rate
                tool.specialization_score * 0.3 +   # Specialization
                (tool.usage_count / 100.0) * 0.2   # Popularity
            )

            matching_tools.append({
                'tool': tool,
                'relevance': relevance
            })

    # Sort by relevance
    matching_tools.sort(key=lambda t: t['relevance'], reverse=True)

    # Return best match
    if matching_tools:
        return matching_tools[0]['tool']
    else:
        # No matching tool found
        return None
```

### 3. Create New Tool (if needed)
```python
# Location: core/tool_creation.py:202-280

def create_tool_for_capability(capability, task_context):
    # Dynamically create new tool if none exists

    # Generate tool name
    tool_name = f"{capability.title()} Tool"

    # Create tool
    new_tool = Tool(
        tool_id=generate_id(),
        tool_name=tool_name,
        tool_type='primitive',
        capabilities=[capability],
        success_rate=0.5,  # Initial estimate
        usage_count=0,
        avg_execution_time=5.0,
        specialization_score=1.0  # Highly specialized
    )

    # Add to library
    self.tools[new_tool.tool_id] = new_tool

    return new_tool
```

### 4. Update Tool Statistics
```python
# Location: core/tool_creation.py:282-340

def update_tool_stats(tool_id, success, execution_time):
    # Update tool statistics after use

    tool = self.tools.get(tool_id)
    if not tool:
        return

    # Update usage count
    tool.usage_count += 1

    # Update success rate (exponential moving average)
    alpha = 0.1  # Learning rate
    tool.success_rate = (
        tool.success_rate * (1 - alpha) +
        (1.0 if success else 0.0) * alpha
    )

    # Update avg execution time
    tool.avg_execution_time = (
        tool.avg_execution_time * (1 - alpha) +
        execution_time * alpha
    )
```

---

## Output

### API Response Format
```json
{
  "tool_creation": {
    "new_tools_created": [
      {
        "tool_id": "tool_docker_123",
        "tool_name": "Docker Health Check",
        "tool_type": "primitive",
        "capabilities": ["docker", "monitoring", "health"],
        "success_rate": 1.0,
        "usage_count": 15,
        "avg_execution_time": 2.5,
        "specialization_score": 0.9
      }
    ],
    "total_tools_in_library": 52,
    "capability_match_rate": 0.95
  }
}
```

---

## Data Flow

```
Input: Task Context + Required Capability
         │
         ▼
┌─────────────────────┐
│ Identify Capability │
│ keywords → cap      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Search Tool Library │
│ capability → tools  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Score Tools         │
│ relevance ranking   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Return Best Match   │
│ or create new tool  │
└─────────────────────┘
         │
         ▼
    Output: Matching Tools
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:633-643

# Tool creation
created_tools = None
if self.enable_tool_creation and self.tool_creation:
    # Get tool for task
    tool = self.tool_creation.get_tool_for_capability(
        capability=task_type,
        prefer_specialized=True
    )

    if tool:
        created_tools = [{
            'tool_id': tool.tool_id,
            'tool_name': tool.tool_name,
            'tool_type': tool.tool_type,
            'capabilities': tool.capabilities,
            'success_rate': tool.success_rate,
            'usage_count': tool.usage_count
        }]
```

### Seeding Tool Library
```python
# Location: seed_tool_creation.py

from core.tool_creation import Tool, ToolCreation

# Create tool creation system
tool_creation = ToolCreation()

# Add docker tools
docker_build = Tool(
    tool_id='tool_docker_build',
    tool_name='Docker Build',
    tool_type='primitive',
    capabilities=['docker', 'build'],
    success_rate=0.95,
    usage_count=50,
    avg_execution_time=10.0,
    specialization_score=0.9
)

tool_creation.tools['tool_docker_build'] = docker_build
```

---

## Key Algorithms

### Tool Relevance Scoring
```
Relevance = α·success_rate + β·specialization + γ·popularity

where:
- α=0.5: Success rate weight
- β=0.3: Specialization weight
- γ=0.2: Popularity weight (usage_count / 100)
```

### Specialization Score
```
Specialization = 1.0 / num_capabilities

Highly specialized tools (1-2 capabilities) score higher than
general-purpose tools (5+ capabilities)
```

### Success Rate Update (EMA)
```
success_rate[t+1] = success_rate[t] · (1-α) + outcome · α

where:
- α: Learning rate (0.1)
- outcome: 1.0 (success) or 0.0 (failure)
- Smooths out noise from individual failures
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~2ms |
| **Memory Usage** | ~500B per tool |
| **Library Size** | 50+ tools typical |

---

## Dependencies

- **uuid**: Tool ID generation
- **None**: Self-contained module

---

## Future Enhancements

1. **Auto-Generation**: Generate tool code from patterns
2. **Composition**: Combine primitive tools into composite tools
3. **Learning from Execution**: Improve tools based on outcomes
4. **Transfer Learning**: Apply tools across domains
5. **Tool Discovery**: Mine successful patterns from logs

---

## Related Files

- **Implementation**: `core/tool_creation.py`
- **Integration**: `core/hierarchical_planner.py:633-643`
- **API**: `production/production_planner.py:469-484`
- **Seeding**: `seed_tool_creation.py`
- **Tests**: `test_all_features_seeded.py`

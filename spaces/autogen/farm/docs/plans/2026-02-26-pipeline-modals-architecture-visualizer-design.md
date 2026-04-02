# Design: Pipeline Decision Modals + Architecture Visualizer

## Problem

The pipeline makes critical decisions via LLM that would benefit from human oversight:
- **MCP Server Selection**: GPT-4o picks from 317+ servers, but doesn't know user's infrastructure or new servers post-training-cutoff.
- **Tool Assignment**: Default tool lists may not match user's actual APIs/services.
- **Architecture**: Agent structure, handoffs, and tool wiring are designed by LLM without user review.

## Solution

Extend the WebSocket question modal system (built in previous task) with 3 new question types that give the user interactive decision UIs at key pipeline steps.

## New Question Types

### 1. `mcp_selection` (CatalogAgent)

**When:** After CatalogAgent's Pass 1 LLM selection, before enabling servers.

**UI:** Checkbox list of all available MCP servers. Pre-selected servers are checked. Domain hints shown as tags. User can add/remove servers, then "Confirm Selection".

**Question metadata:**
```json
{
  "available_servers": [
    {"name": "filesystem", "description": "...", "needs_key": false},
    {"name": "github", "description": "...", "needs_key": true}
  ],
  "selected_servers": ["filesystem", "git"],
  "domain_hints": ["sales", "crm"],
  "reasoning": "Selected because..."
}
```

**Answer:** JSON string with final server list: `{"servers": ["filesystem", "git", "fetch"]}`

### 2. `tool_assignment` (Input Parser)

**When:** After parsing input.md, before generating tools.py.

**UI:** Accordion per agent (expandable). Each agent shows its tool list as chips/tags. User can remove tools (X button) or add from available tools (dropdown). "Confirm Tools" button.

**Question metadata:**
```json
{
  "agents": {
    "CSOAgent": {"tools": ["claude_code", "enrich_contact"], "role": "manager"},
    "DataAnalyst": {"tools": ["claude_code", "fetch_linkedin"], "role": "specialist"}
  },
  "available_tools": ["claude_code", "enrich_contact", "fetch_linkedin", "send_email", ...]
}
```

**Answer:** JSON string with modified tool assignments: `{"agents": {"CSOAgent": ["claude_code", "enrich_contact", "new_tool"], ...}}`

### 3. `architecture_review` (ArchitectAgent)

**When:** After ArchitectAgent generates YAML files, before CoderAgent starts.

**UI:** React Flow canvas embedded in modal. Read-only (no drag & drop in V1). Zoom + pan. Tooltip on hover over nodes. Approve/Reject/Reply buttons.

**Question metadata:**
```json
{
  "nodes": [
    {"id": "CSOAgent", "type": "manager", "label": "CSOAgent", "group": "core"},
    {"id": "DataAnalyst", "type": "specialist", "label": "DataAnalyst", "group": "research"},
    {"id": "input", "type": "input", "label": "New Sales Lead"},
    {"id": "output", "type": "output", "label": "Output Report"}
  ],
  "edges": [
    {"source": "input", "target": "CSOAgent", "type": "data", "label": "task"},
    {"source": "CSOAgent", "target": "VPSalesAgent", "type": "handoff", "label": "handoff"},
    {"source": "VPSalesAgent", "target": "research", "type": "delegation", "label": "run_research_team"},
    {"source": "DataAnalyst", "target": "enrich_contact", "type": "tool", "label": "enrich_contact"},
    {"source": "CSOAgent", "target": "output", "type": "data", "label": "report"}
  ],
  "groups": [
    {"id": "core", "label": "Core Team"},
    {"id": "research", "label": "Research Team"}
  ]
}
```

## React Flow Node Types

| Node Type | Visual | Color |
|-----------|--------|-------|
| `manager` | Large box, bold title | Blue border, light blue bg |
| `specialist` | Normal box | Gray border, white bg |
| `input` | Rounded box, left side | Green border |
| `output` | Rounded box, right side | Orange border |
| `group` | Dashed container (subflow) | Light gray dashed border |

## React Flow Edge Types

| Edge Type | Visual | Label |
|-----------|--------|-------|
| `handoff` | Solid arrow | "handoff" |
| `tool` | Dashed line | Tool name |
| `delegation` | Thick arrow | `run_X_team` |
| `data` | Green/orange colored line | I/O label |

## Backend Changes

### Question model extension

Add `_metadata` column to the Question model (same Text+JSON property pattern):

```python
_metadata = Column("metadata", Text, default="{}")

@property
def metadata(self):
    return json.loads(self._metadata) if self._metadata else {}

@metadata.setter
def metadata(self, value):
    self._metadata = json.dumps(value)
```

### Schema extension

Add `metadata` field to QuestionCreate, QuestionResponse:

```python
class QuestionCreate(BaseModel):
    ...
    metadata: dict = {}

class QuestionResponse(BaseModel):
    ...
    metadata: dict
```

### Endpoint updates

All existing endpoints pass `metadata` through (create, get, list, answer). The WebSocket broadcast includes metadata.

## Frontend Changes

### New dependencies

- `@xyflow/react` (React Flow v12) for architecture diagram
- `dagre` for auto-layout of the graph

### QuestionModal extension

The modal renders different content based on `question.type`:

- `approval`, `missing_info`, `implementation_choice` -> existing code (unchanged)
- `mcp_selection` -> `<McpSelectionView />`
- `tool_assignment` -> `<ToolAssignmentView />`
- `architecture_review` -> `<ArchitectureReviewView />`

Modal width: `sm:max-w-4xl` for the new types (wider for diagrams/lists).

### McpSelectionView component

- Reads `metadata.available_servers` and `metadata.selected_servers`
- Renders checkbox list grouped by "needs_key" (key-free first)
- Domain hint badges
- "Confirm Selection" sends answer with JSON `{"servers": [...]}`

### ToolAssignmentView component

- Reads `metadata.agents` and `metadata.available_tools`
- Accordion per agent (Radix Accordion or custom collapsible)
- Tool chips with X to remove
- Dropdown to add tools from available list
- "Confirm Tools" sends answer with JSON `{"agents": {...}}`

### ArchitectureReviewView component

- Reads `metadata.nodes`, `metadata.edges`, `metadata.groups`
- Converts to React Flow format (with dagre auto-layout)
- Custom node components for manager/specialist/input/output
- Read-only (no editing in V1)
- Zoom/pan enabled
- Tooltip on node hover (shows agent details)
- Approve/Reject/Reply buttons below the canvas

## Pipeline Changes

### CatalogAgent (`pipeline.py: step_catalog`)

After Pass 1 LLM selection, before enabling servers:

```python
answer = await ask_user(
    question_type="mcp_selection",
    tool_name="CatalogAgent",
    message="Review MCP server selection for this task",
    metadata={
        "available_servers": [...],
        "selected_servers": selected_names,
        "domain_hints": domain_info["domains"],
        "reasoning": reasoning,
    }
)
if answer["action"] == "reply" and answer["text"]:
    user_selection = json.loads(answer["text"])
    selected_names = user_selection.get("servers", selected_names)
```

### Input Parser (`input_parser.py`)

New function `ask_user_tool_assignment()` called from `generate_sales_tools_py()`:

```python
answer = await ask_user(
    question_type="tool_assignment",
    tool_name="InputParser",
    message="Review tool assignments for agents",
    metadata={
        "agents": {name: {"tools": info.get("tools", []), "role": "..."} for name, info in agents.items()},
        "available_tools": list(SALES_TOOL_IMPLEMENTATIONS.keys()),
    }
)
```

### ArchitectAgent (`pipeline.py: step_architect`)

After YAML generation, before posting to Minibook:

```python
graph = build_architecture_graph(self.yaml_files, self.input_manifest)
answer = await ask_user(
    question_type="architecture_review",
    tool_name="ArchitectAgent",
    message="Review the agent architecture before code generation begins",
    metadata=graph,
)
```

New helper function `build_architecture_graph()` that parses YAML files into nodes/edges/groups format.

### ask_user() extension

Add `metadata: dict = None` parameter:

```python
async def ask_user(..., metadata: dict = None) -> dict:
    payload = {
        ...
        "metadata": metadata or {},
    }
```

## File Changes

| File | Change |
|------|--------|
| `minibook/src/models.py` | Add `_metadata` column + property to Question |
| `minibook/src/schemas.py` | Add `metadata` to QuestionCreate, QuestionResponse |
| `minibook/src/main.py` | Pass metadata through in all question endpoints + WS broadcast |
| `minibook/frontend/package.json` | Add `@xyflow/react`, `dagre` dependencies |
| `minibook/frontend/src/components/question-modal.tsx` | Route to new view components by type, wider modal |
| `minibook/frontend/src/components/mcp-selection-view.tsx` | New: checkbox list for MCP servers |
| `minibook/frontend/src/components/tool-assignment-view.tsx` | New: accordion + chips for tool assignment |
| `minibook/frontend/src/components/architecture-review-view.tsx` | New: React Flow diagram |
| `minibook/frontend/src/components/ws-provider.tsx` | Add metadata to Question interface |
| `minibook/frontend/src/lib/api.ts` | Add metadata to Question type |
| `minibook/swarm/todo_implementer.py` | Add metadata param to ask_user() |
| `minibook/swarm/pipeline.py` | Add ask_user() calls in CatalogAgent + ArchitectAgent steps |
| `minibook/swarm/input_parser.py` | Add ask_user() call for tool assignment |

## Timeout Behavior

- `mcp_selection`: 60s timeout -> use LLM selection as-is
- `tool_assignment`: 60s timeout -> use defaults as-is
- `architecture_review`: 120s timeout -> auto-approve

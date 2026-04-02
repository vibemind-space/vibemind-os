# Pipeline Decision Modals + Architecture Visualizer — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add interactive human-decision modals at 3 pipeline steps (MCP selection, tool assignment, architecture review) with a React Flow architecture diagram embedded in the modal.

**Architecture:** Extend the existing Question model with a `metadata` JSON column. Frontend renders different views per question type: checkbox list (MCP), accordion+chips (tools), React Flow canvas (architecture). Pipeline calls `ask_user()` at each decision point.

**Tech Stack:** FastAPI, SQLAlchemy, React 19, Next.js 16, React Flow (@xyflow/react), dagre (auto-layout), shadcn/ui, Tailwind CSS 4

---

### Task 1: Add metadata column to Question model + schemas

**Files:**
- Modify: `minibook/src/models.py:290-300`
- Modify: `minibook/src/schemas.py:190-216`

**Step 1: Add `_metadata` column to Question model**

In `minibook/src/models.py`, after `answered_at` (line 292), add:

```python
    _metadata = Column("metadata", Text, default="{}")
```

After the `options` property setter (line 300), add:

```python
    @property
    def metadata(self):
        return json.loads(self._metadata) if self._metadata else {}

    @metadata.setter
    def metadata(self, value):
        self._metadata = json.dumps(value)
```

**Step 2: Add metadata to schemas**

In `minibook/src/schemas.py`:

Add `metadata: dict = {}` to `QuestionCreate` (after `message: str`, line 197):
```python
    metadata: dict = {}
```

Add `metadata: dict` to `QuestionResponse` (after `answered_at`, line 212):
```python
    metadata: dict
```

**Step 3: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/src/models.py', doraise=True); py_compile.compile('minibook/src/schemas.py', doraise=True); print('OK')"`

---

### Task 2: Pass metadata through all backend endpoints

**Files:**
- Modify: `minibook/src/main.py:1102-1192` (Question endpoints + WS)

**Step 1: Update create_question endpoint (line 1105-1113)**

After `q.options = data.options` (line 1113), add:
```python
    q.metadata = data.metadata
```

In the WS broadcast dict (lines 1120-1125), add `"metadata": q.metadata`:
```python
        "question": {
            "id": q.id, "type": q.type, "tool_name": q.tool_name,
            "todo_hint": q.todo_hint, "mock_code": q.mock_code,
            "generated_code": q.generated_code, "options": q.options,
            "message": q.message, "status": q.status,
            "metadata": q.metadata,
        }
```

In every `QuestionResponse(...)` constructor (lines 1128-1134, 1141-1146, 1153-1159, 1172-1178), add `metadata=q.metadata`. There are 4 occurrences total.

**Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/src/main.py', doraise=True); print('OK')"`

---

### Task 3: Update frontend types for metadata

**Files:**
- Modify: `minibook/frontend/src/components/ws-provider.tsx:5-15`
- Modify: `minibook/frontend/src/lib/api.ts:99-113`

**Step 1: Add metadata to Question interface in ws-provider.tsx**

In `ws-provider.tsx`, add to the `Question` interface (after `status: string`, line 14):
```typescript
  metadata: Record<string, unknown>;
```

**Step 2: Add metadata to Question interface in api.ts**

In `api.ts`, add to the `Question` interface (after `answered_at`, line 112):
```typescript
  metadata: Record<string, unknown>;
```

---

### Task 4: Update ask_user() with metadata parameter

**Files:**
- Modify: `minibook/swarm/todo_implementer.py:141-155`

**Step 1: Add metadata param to ask_user**

Change the signature (lines 141-149) to include `metadata`:

```python
async def ask_user(
    question_type: str,
    tool_name: str,
    todo_hint: str = "",
    mock_code: str = "",
    generated_code: str = None,
    options: list = None,
    message: str = None,
    metadata: dict = None,
    timeout: int = None,
) -> dict:
```

In the payload dict (around line 162), add:
```python
        "metadata": metadata or {},
```

**Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/swarm/todo_implementer.py', doraise=True); print('OK')"`

---

### Task 5: Install React Flow + dagre in frontend

**Files:**
- Modify: `minibook/frontend/package.json`

**Step 1: Install dependencies**

Run: `cd minibook/frontend && npm install @xyflow/react dagre @types/dagre`

**Step 2: Verify install**

Run: `cd minibook/frontend && node -e "require('@xyflow/react'); require('dagre'); console.log('OK')"`

---

### Task 6: Create McpSelectionView component

**Files:**
- Create: `minibook/frontend/src/components/mcp-selection-view.tsx`

**Step 1: Create the component**

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useWS, Question } from "@/components/ws-provider";

interface ServerInfo {
  name: string;
  description?: string;
  needs_key?: boolean;
}

export function McpSelectionView({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const meta = question.metadata as {
    available_servers?: ServerInfo[];
    selected_servers?: string[];
    domain_hints?: string[];
    reasoning?: string;
  };

  const available = meta.available_servers || [];
  const [selected, setSelected] = useState<Set<string>>(
    new Set(meta.selected_servers || [])
  );

  const toggle = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleConfirm = () => {
    sendAnswer(question.id, "reply", JSON.stringify({ servers: [...selected] }));
  };

  const keyFree = available.filter(s => !s.needs_key);
  const needsKey = available.filter(s => s.needs_key);

  const renderGroup = (servers: ServerInfo[], label: string) => (
    servers.length > 0 && (
      <div className="mb-4">
        <h4 className="text-xs font-medium text-neutral-400 mb-2">{label}</h4>
        <div className="space-y-1.5">
          {servers.map(s => (
            <label key={s.name} className="flex items-start gap-3 p-2 rounded hover:bg-neutral-800 cursor-pointer">
              <input
                type="checkbox"
                checked={selected.has(s.name)}
                onChange={() => toggle(s.name)}
                className="mt-0.5 accent-blue-500"
              />
              <div className="flex-1 min-w-0">
                <span className="text-sm text-neutral-50 font-medium">{s.name}</span>
                {s.description && (
                  <p className="text-xs text-neutral-400 truncate">{s.description}</p>
                )}
              </div>
              {s.needs_key && <Badge className="bg-amber-500/20 text-amber-400 border-0 text-xs shrink-0">API Key</Badge>}
            </label>
          ))}
        </div>
      </div>
    )
  );

  return (
    <div className="space-y-4">
      {meta.domain_hints && meta.domain_hints.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-neutral-400">Domains:</span>
          {meta.domain_hints.map(d => (
            <Badge key={d} className="bg-blue-500/20 text-blue-400 border-0 text-xs">{d}</Badge>
          ))}
        </div>
      )}
      {meta.reasoning && (
        <p className="text-xs text-neutral-400 italic">{meta.reasoning}</p>
      )}
      <div className="max-h-[50vh] overflow-y-auto">
        {renderGroup(keyFree, "Key-Free Servers")}
        {renderGroup(needsKey, "Servers Requiring API Key")}
      </div>
      <div className="flex justify-between items-center pt-2 border-t border-neutral-700">
        <span className="text-xs text-neutral-400">{selected.size} selected</span>
        <Button onClick={handleConfirm} className="bg-blue-600 hover:bg-blue-700 text-white">
          Confirm Selection
        </Button>
      </div>
    </div>
  );
}
```

---

### Task 7: Create ToolAssignmentView component

**Files:**
- Create: `minibook/frontend/src/components/tool-assignment-view.tsx`

**Step 1: Create the component**

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useWS, Question } from "@/components/ws-provider";

interface AgentTools {
  tools: string[];
  role?: string;
}

export function ToolAssignmentView({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const meta = question.metadata as {
    agents?: Record<string, AgentTools>;
    available_tools?: string[];
  };

  const [assignments, setAssignments] = useState<Record<string, string[]>>(() => {
    const init: Record<string, string[]> = {};
    for (const [name, info] of Object.entries(meta.agents || {})) {
      init[name] = [...info.tools];
    }
    return init;
  });

  const [expanded, setExpanded] = useState<string | null>(null);
  const availableTools = meta.available_tools || [];

  const removeTool = (agent: string, tool: string) => {
    setAssignments(prev => ({
      ...prev,
      [agent]: prev[agent].filter(t => t !== tool),
    }));
  };

  const addTool = (agent: string, tool: string) => {
    setAssignments(prev => ({
      ...prev,
      [agent]: [...prev[agent], tool],
    }));
  };

  const handleConfirm = () => {
    sendAnswer(question.id, "reply", JSON.stringify({ agents: assignments }));
  };

  const roleColor: Record<string, string> = {
    manager: "bg-blue-500/20 text-blue-400",
    specialist: "bg-neutral-500/20 text-neutral-300",
    executive: "bg-purple-500/20 text-purple-400",
  };

  return (
    <div className="space-y-2">
      <div className="max-h-[55vh] overflow-y-auto space-y-1">
        {Object.entries(assignments).map(([agent, tools]) => {
          const info = meta.agents?.[agent];
          const isOpen = expanded === agent;
          return (
            <div key={agent} className="border border-neutral-700 rounded">
              <button
                className="w-full flex items-center justify-between p-3 hover:bg-neutral-800 text-left"
                onClick={() => setExpanded(isOpen ? null : agent)}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-neutral-50">{agent}</span>
                  {info?.role && (
                    <Badge className={`${roleColor[info.role] || ""} border-0 text-xs`}>{info.role}</Badge>
                  )}
                </div>
                <span className="text-xs text-neutral-400">{tools.length} tools {isOpen ? "▲" : "▼"}</span>
              </button>
              {isOpen && (
                <div className="px-3 pb-3 space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    {tools.map(t => (
                      <Badge key={t} className="bg-neutral-700 text-neutral-200 border-0 text-xs gap-1">
                        {t}
                        <button onClick={() => removeTool(agent, t)} className="ml-1 hover:text-red-400">×</button>
                      </Badge>
                    ))}
                  </div>
                  <select
                    className="w-full bg-neutral-800 border border-neutral-600 text-neutral-200 text-xs rounded p-1.5"
                    value=""
                    onChange={(e) => { if (e.target.value) addTool(agent, e.target.value); }}
                  >
                    <option value="">+ Add tool...</option>
                    {availableTools.filter(t => !tools.includes(t)).map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex justify-end pt-2 border-t border-neutral-700">
        <Button onClick={handleConfirm} className="bg-blue-600 hover:bg-blue-700 text-white">
          Confirm Tools
        </Button>
      </div>
    </div>
  );
}
```

---

### Task 8: Create ArchitectureReviewView component (React Flow)

**Files:**
- Create: `minibook/frontend/src/components/architecture-review-view.tsx`

**Step 1: Create the component**

```tsx
"use client";

import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Button } from "@/components/ui/button";
import { useWS, Question } from "@/components/ws-provider";

interface GraphNode {
  id: string;
  type: string;     // "manager" | "specialist" | "input" | "output"
  label: string;
  group?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;     // "handoff" | "tool" | "delegation" | "data"
  label?: string;
}

interface GraphGroup {
  id: string;
  label: string;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 50;

const nodeStyles: Record<string, React.CSSProperties> = {
  manager: { border: "2px solid #3b82f6", background: "#1e3a5f", borderRadius: 8, padding: "8px 16px", color: "#e2e8f0", fontWeight: 600, fontSize: 13 },
  specialist: { border: "1px solid #525252", background: "#262626", borderRadius: 8, padding: "8px 16px", color: "#d4d4d4", fontSize: 13 },
  input: { border: "2px solid #22c55e", background: "#14532d", borderRadius: 20, padding: "8px 16px", color: "#bbf7d0", fontSize: 13 },
  output: { border: "2px solid #f97316", background: "#7c2d12", borderRadius: 20, padding: "8px 16px", color: "#fed7aa", fontSize: 13 },
};

const edgeStyles: Record<string, { stroke: string; strokeDasharray?: string; strokeWidth?: number }> = {
  handoff: { stroke: "#3b82f6", strokeWidth: 2 },
  tool: { stroke: "#737373", strokeDasharray: "5 3", strokeWidth: 1 },
  delegation: { stroke: "#a855f7", strokeWidth: 3 },
  data: { stroke: "#22c55e", strokeWidth: 2 },
};

function layoutGraph(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });

  nodes.forEach(n => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach(e => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map(n => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 } };
  });
}

export function ArchitectureReviewView({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const meta = question.metadata as {
    nodes?: GraphNode[];
    edges?: GraphEdge[];
    groups?: GraphGroup[];
  };

  const { flowNodes, flowEdges } = useMemo(() => {
    const rawNodes: Node[] = (meta.nodes || []).map(n => ({
      id: n.id,
      data: { label: n.label },
      position: { x: 0, y: 0 },
      style: nodeStyles[n.type] || nodeStyles.specialist,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      parentId: n.group || undefined,
    }));

    const groupNodes: Node[] = (meta.groups || []).map((g, i) => ({
      id: g.id,
      data: { label: g.label },
      position: { x: 0, y: i * 300 },
      style: {
        border: "1px dashed #525252",
        background: "rgba(38,38,38,0.5)",
        borderRadius: 12,
        padding: 20,
        fontSize: 11,
        color: "#737373",
        width: 400,
        height: 200,
      },
      type: "group",
    }));

    const fEdges: Edge[] = (meta.edges || []).map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      label: e.label,
      style: edgeStyles[e.type] || edgeStyles.tool,
      labelStyle: { fontSize: 10, fill: "#a3a3a3" },
      animated: e.type === "delegation",
    }));

    const allNodes = [...groupNodes, ...rawNodes];
    const laid = layoutGraph(allNodes.filter(n => n.type !== "group"), fEdges);
    const finalNodes = [...groupNodes, ...laid.filter(n => n.type !== "group")];

    return { flowNodes: finalNodes, flowEdges: fEdges };
  }, [meta]);

  const handleApprove = useCallback(() => sendAnswer(question.id, "approve"), [question.id, sendAnswer]);
  const handleReject = useCallback(() => sendAnswer(question.id, "reject"), [question.id, sendAnswer]);

  return (
    <div className="space-y-3">
      <div className="h-[55vh] w-full border border-neutral-700 rounded-lg overflow-hidden bg-neutral-950">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background color="#333" gap={20} />
          <Controls showInteractive={false} />
          <MiniMap
            nodeStrokeColor="#525252"
            nodeColor="#262626"
            maskColor="rgba(0,0,0,0.7)"
          />
        </ReactFlow>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={handleReject} className="border-red-800 text-red-400 hover:bg-red-950">
          Reject
        </Button>
        <Button onClick={handleApprove} className="bg-green-600 hover:bg-green-700 text-white">
          Approve Architecture
        </Button>
      </div>
    </div>
  );
}
```

---

### Task 9: Update QuestionModal to route to new views

**Files:**
- Modify: `minibook/frontend/src/components/question-modal.tsx:1-154`

**Step 1: Add imports**

At the top of `question-modal.tsx`, add:
```tsx
import { McpSelectionView } from "@/components/mcp-selection-view";
import { ToolAssignmentView } from "@/components/tool-assignment-view";
import { ArchitectureReviewView } from "@/components/architecture-review-view";
```

**Step 2: Update QuestionContent to route by type**

In the `QuestionContent` function, BEFORE the existing `return (<>...)` block, add an early return for the new types:

```tsx
  // Route to specialized views for new question types
  if (question.type === "mcp_selection") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        </DialogHeader>
        <McpSelectionView question={question} />
      </>
    );
  }

  if (question.type === "tool_assignment") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        </DialogHeader>
        <ToolAssignmentView question={question} />
      </>
    );
  }

  if (question.type === "architecture_review") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
          {question.todo_hint && <DialogDescription>{question.todo_hint}</DialogDescription>}
        </DialogHeader>
        <ArchitectureReviewView question={question} />
      </>
    );
  }
```

**Step 3: Make modal wider for new types**

In the `QuestionModal` export function, update `DialogContent` className to be wider for new types:

```tsx
  const isWide = currentQuestion && ["mcp_selection", "tool_assignment", "architecture_review"].includes(currentQuestion.type);

  return (
    <Dialog open={!!currentQuestion}>
      <DialogContent className={`${isWide ? "sm:max-w-4xl" : "sm:max-w-2xl"} bg-neutral-900 border-neutral-700 text-neutral-50`} showCloseButton={false}>
        {currentQuestion && <QuestionContent question={currentQuestion} />}
      </DialogContent>
    </Dialog>
  );
```

---

### Task 10: Pipeline integration — CatalogAgent MCP selection modal

**Files:**
- Modify: `minibook/swarm/pipeline.py:504-506`

**Step 1: Add ask_user import**

At the top of `pipeline.py`, add to the existing import from `todo_implementer`:

```python
from .todo_implementer import implement_todos, scan_todo_tools, ask_user
```

**Step 2: Add MCP selection modal after Pass 1**

After `self.mcp_selection = reasoning or str(selected_names)` (line 504), and before `print(f"[CatalogAgent] Pass 1 selected:` (line 505), insert:

```python
        # Human review: let user adjust MCP server selection
        if selected_names:
            available = [
                {"name": name, "description": info.get("description", "")[:100], "needs_key": bool(info.get("secrets"))}
                for name, info in registry.items()
            ]
            answer = await ask_user(
                question_type="mcp_selection",
                tool_name="CatalogAgent",
                message=f"Review MCP server selection for: {self.task_name}",
                metadata={
                    "available_servers": available[:50],  # limit to 50 for UI
                    "selected_servers": selected_names,
                    "domain_hints": domain_info.get("domains", []),
                    "reasoning": reasoning,
                },
                timeout=60,
            )
            if answer["action"] == "reply" and answer["text"]:
                try:
                    user_sel = json.loads(answer["text"])
                    selected_names = [s for s in user_sel.get("servers", selected_names) if s in registry]
                    print(f"[CatalogAgent] User adjusted selection: {selected_names}")
                except (json.JSONDecodeError, KeyError):
                    pass
```

Make sure `import json` is available at the top of pipeline.py (it already is).

**Step 3: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/swarm/pipeline.py', doraise=True); print('OK')"`

---

### Task 11: Pipeline integration — ArchitectAgent architecture review modal

**Files:**
- Modify: `minibook/swarm/pipeline.py:689-695`

**Step 1: Add build_architecture_graph helper**

Add this function before `step_swarm_manager` (around line 238):

```python
    def _build_architecture_graph(self) -> dict:
        """Convert YAML files into a graph structure for React Flow visualization."""
        nodes = []
        edges = []
        groups = []
        agent_names = set()

        for path, content in self.yaml_files.items():
            if not path.endswith("agent.yml"):
                continue
            try:
                cfg = yaml.safe_load(content)
                if not isinstance(cfg, dict) or "name" not in cfg:
                    continue
                name = cfg["name"]
                agent_names.add(name)

                # Determine group from path: agents/SubTeam/AgentName/agent.yml
                parts = path.split("/")
                group = parts[1] if len(parts) >= 3 else "core"

                # Determine type
                agent_type = "specialist"
                if any(kw in name.lower() for kw in ["manager", "lead", "vp", "cso", "director"]):
                    agent_type = "manager"

                nodes.append({"id": name, "type": agent_type, "label": name, "group": group})

                # Extract tool edges
                for tool in cfg.get("domain_tools", []):
                    edges.append({"source": name, "target": f"tool_{tool}", "type": "tool", "label": tool})

                # Extract handoffs
                for handoff in cfg.get("handoffs", []):
                    target = handoff if isinstance(handoff, str) else handoff.get("target", "")
                    if target:
                        edges.append({"source": name, "target": target, "type": "handoff", "label": "handoff"})

            except yaml.YAMLError:
                continue

        # Collect unique groups
        seen_groups = set()
        for n in nodes:
            g = n.get("group", "core")
            if g not in seen_groups:
                groups.append({"id": g, "label": g.replace("_", " ").title()})
                seen_groups.add(g)

        # Add input/output nodes
        task_label = self.task_name[:40] if self.task_name else "Task"
        nodes.insert(0, {"id": "input", "type": "input", "label": task_label})
        nodes.append({"id": "output", "type": "output", "label": "Output"})

        # Connect input to first manager, last to output
        managers = [n["id"] for n in nodes if n.get("type") == "manager"]
        if managers:
            edges.insert(0, {"source": "input", "target": managers[0], "type": "data", "label": "task"})
            edges.append({"source": managers[0], "target": "output", "type": "data", "label": "report"})

        # Remove tool-only nodes (edges reference them but they don't need to be nodes)
        edges = [e for e in edges if e["target"] in agent_names or e["target"] in ("input", "output") or e["type"] != "tool" or False]
        # Actually keep tool edges but remove tool pseudo-nodes; tools are just edge labels
        edges = [e for e in edges if e["type"] != "tool"]
        # Re-add tools as labels on handoff/delegation edges where applicable

        return {"nodes": nodes, "edges": edges, "groups": groups}
```

**Step 2: Add architecture review modal after YAML generation**

After `self.architect_output = architecture` (line 694), before the `else:` on line 696, insert:

```python
            # Human review: show architecture diagram
            graph = self._build_architecture_graph()
            if graph["nodes"]:
                answer = await ask_user(
                    question_type="architecture_review",
                    tool_name="ArchitectAgent",
                    message=f"Review agent architecture for: {self.task_name}",
                    metadata=graph,
                    timeout=120,
                )
                if answer["action"] == "reject":
                    print(f"[ArchitectAgent] User rejected architecture — continuing anyway (no regeneration in V1)")
```

**Step 3: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/swarm/pipeline.py', doraise=True); print('OK')"`

---

### Task 12: Pipeline integration — Input Parser tool assignment modal

**Files:**
- Modify: `minibook/swarm/input_parser.py:992-1029`

**Step 1: Add ask_user import**

At the top of `input_parser.py`, add:
```python
import asyncio
```

(The `ask_user` function is in `todo_implementer.py` but input_parser is called synchronously from pipeline. We'll make tool assignment async-compatible.)

**Step 2: Add tool review function**

Add before `generate_sales_tools_py` (line 992):

```python
async def review_tool_assignments(agents: dict) -> dict:
    """Let user review and modify tool assignments via the question modal."""
    from .todo_implementer import ask_user

    agent_data = {}
    for name, info in agents.items():
        tools = info.get("tools", info.get("domain_tools", []))
        role = "manager" if any(kw in name.lower() for kw in ["manager", "lead", "vp", "cso", "director"]) else "specialist"
        agent_data[name] = {"tools": tools, "role": role}

    available = list(SALES_TOOL_IMPLEMENTATIONS.keys())

    answer = await ask_user(
        question_type="tool_assignment",
        tool_name="InputParser",
        message="Review tool assignments for agents",
        metadata={"agents": agent_data, "available_tools": available},
        timeout=60,
    )

    if answer["action"] == "reply" and answer["text"]:
        try:
            user_assignments = json.loads(answer["text"])
            user_agents = user_assignments.get("agents", {})
            for name, tools in user_agents.items():
                if name in agents and isinstance(tools, list):
                    agents[name]["tools"] = tools
            print(f"[InputParser] User adjusted tool assignments for {len(user_agents)} agents")
        except (json.JSONDecodeError, KeyError):
            pass

    return agents
```

**Step 3: Call review from pipeline**

In `minibook/swarm/pipeline.py`, in `step_architect` where it calls `generate_sales_tools_py` for core team (line 653) and sub-teams (line 661), add the review call before tools generation.

Before line 653 (`self.generated_files["src/tools.py"] = generate_sales_tools_py(core_agents)`), add:
```python
                from .input_parser import review_tool_assignments
                core_agents = await review_tool_assignments(dict(core_agents))
```

Before line 661 (sub-team tools generation), add:
```python
                all_agents = await review_tool_assignments(all_agents)
```

**Step 4: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/swarm/input_parser.py', doraise=True); py_compile.compile('minibook/swarm/pipeline.py', doraise=True); print('OK')"`

---

### Task 13: End-to-end test — fire test questions for all 3 new types

**Step 1: Test mcp_selection**

```bash
curl -s -X POST http://localhost:8899/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "mcp_selection",
    "tool_name": "CatalogAgent",
    "message": "Review MCP server selection",
    "metadata": {
      "available_servers": [
        {"name": "filesystem", "description": "Read/write files", "needs_key": false},
        {"name": "git", "description": "Git operations", "needs_key": false},
        {"name": "github", "description": "GitHub API", "needs_key": true},
        {"name": "fetch", "description": "HTTP fetch", "needs_key": false}
      ],
      "selected_servers": ["filesystem", "git"],
      "domain_hints": ["sales", "crm"],
      "reasoning": "Selected filesystem and git for local operations"
    }
  }'
```

Verify: Modal shows checkbox list in browser.

**Step 2: Test tool_assignment**

```bash
curl -s -X POST http://localhost:8899/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "tool_assignment",
    "tool_name": "InputParser",
    "message": "Review tool assignments for agents",
    "metadata": {
      "agents": {
        "CSOAgent": {"tools": ["claude_code", "enrich_contact"], "role": "manager"},
        "DataAnalyst": {"tools": ["claude_code", "fetch_linkedin"], "role": "specialist"},
        "EmailSpecialist": {"tools": ["send_email", "claude_code"], "role": "specialist"}
      },
      "available_tools": ["claude_code", "enrich_contact", "fetch_linkedin", "send_email", "write_report", "search_web"]
    }
  }'
```

Verify: Modal shows accordion with agent tool lists.

**Step 3: Test architecture_review**

```bash
curl -s -X POST http://localhost:8899/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "architecture_review",
    "tool_name": "ArchitectAgent",
    "message": "Review agent architecture",
    "metadata": {
      "nodes": [
        {"id": "input", "type": "input", "label": "New Sales Lead"},
        {"id": "CSOAgent", "type": "manager", "label": "CSOAgent", "group": "core"},
        {"id": "VPSales", "type": "manager", "label": "VPSalesAgent", "group": "core"},
        {"id": "ResearchMgr", "type": "manager", "label": "ResearchManager", "group": "research"},
        {"id": "DataAnalyst", "type": "specialist", "label": "DataAnalyst", "group": "research"},
        {"id": "output", "type": "output", "label": "Output Report"}
      ],
      "edges": [
        {"source": "input", "target": "CSOAgent", "type": "data", "label": "task"},
        {"source": "CSOAgent", "target": "VPSales", "type": "handoff", "label": "handoff"},
        {"source": "VPSales", "target": "ResearchMgr", "type": "delegation", "label": "run_research"},
        {"source": "ResearchMgr", "target": "DataAnalyst", "type": "handoff", "label": "handoff"},
        {"source": "CSOAgent", "target": "output", "type": "data", "label": "report"}
      ],
      "groups": [
        {"id": "core", "label": "Core Team"},
        {"id": "research", "label": "Research Team"}
      ]
    }
  }'
```

Verify: Modal shows React Flow diagram with nodes, edges, zoom/pan working.

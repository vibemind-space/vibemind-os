"use client";

import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Button } from "@/components/ui/button";
import { useWS, Question } from "@/components/ws-provider";

interface GraphNode {
  id: string;
  type: string;
  label: string;
  group?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  label?: string;
}

interface GraphGroup {
  id: string;
  label: string;
}

const NODE_WIDTH = 220;
const NODE_HEIGHT = 50;

const nodeStyles: Record<string, React.CSSProperties> = {
  manager: { border: "2px solid #3b82f6", background: "#1e3a5f", borderRadius: 8, padding: "10px 18px", color: "#e2e8f0", fontWeight: 600, fontSize: 14 },
  specialist: { border: "1px solid #525252", background: "#262626", borderRadius: 8, padding: "10px 18px", color: "#d4d4d4", fontSize: 14 },
  input: { border: "2px solid #22c55e", background: "#14532d", borderRadius: 20, padding: "10px 18px", color: "#bbf7d0", fontSize: 14 },
  output: { border: "2px solid #f97316", background: "#7c2d12", borderRadius: 20, padding: "10px 18px", color: "#fed7aa", fontSize: 14 },
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
  g.setGraph({ rankdir: "LR", nodesep: 80, ranksep: 160 });

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

    const laid = layoutGraph(rawNodes, fEdges);
    return { flowNodes: laid, flowEdges: fEdges };
  }, [meta]);

  const handleApprove = useCallback(() => sendAnswer(question.id, "approve"), [question.id, sendAnswer]);
  const handleReject = useCallback(() => sendAnswer(question.id, "reject"), [question.id, sendAnswer]);

  return (
    <div className="flex flex-col flex-1 gap-3 min-h-0">
      <div className="flex-1 min-h-0 w-full border border-neutral-700 rounded-lg overflow-hidden bg-neutral-950">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          minZoom={0.2}
          maxZoom={2}
        >
          <Background color="#333" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <div className="flex justify-end gap-2 shrink-0">
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

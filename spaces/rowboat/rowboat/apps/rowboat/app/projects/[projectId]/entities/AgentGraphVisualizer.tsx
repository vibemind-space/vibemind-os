"use client";

import React, { useEffect, useRef } from "react";
import mermaid from "mermaid";
import { Workflow } from "../../../lib/types/workflow_types";

function sanitizeId(name: string): string {
  return name.replace(/[^a-zA-Z0-9\s_-]/g, "").replace(/[\s-]+/g, "_");
}

function generateMermaidFromWorkflow(workflow: any, isDark: boolean): string {
  const startAgentName = workflow.startAgent;
  const agents: any[] = workflow.agents || [];
  const tools: any[] = workflow.tools || [];

  // Light and dark mode colors
  const toolFillLight = '#ede9fe';
  const toolStrokeLight = '#a78bfa';
  const toolFillDark = '#312e81';
  const toolStrokeDark = '#a78bfa';
  const agentFillLight = '#EBF5FB';
  const agentStrokeLight = '#85C1E9';
  const agentFillDark = '#1e293b';
  const agentStrokeDark = '#a78bfa';
  const startFillLight = '#FEF9E7';
  const startStrokeLight = '#F8C471';
  const startFillDark = '#92400e';
  const startStrokeDark = '#f59e0b';
  const entryFillLight = '#22C55E';
  const entryStrokeLight = '#16A34A';
  const entryFillDark = '#22c55e';
  const entryStrokeDark = '#4ade80';
  const textLight = '#34495E';
  const textDark = '#fff';

  const mermaidCode = [
    "graph LR",
    // Agent node style
    `    classDef agent fill:${isDark ? agentFillDark : agentFillLight},stroke:${isDark ? agentStrokeDark : agentStrokeLight},stroke-width:3px,color:${isDark ? textDark : textLight},font-size:16px,radius:12px`,
    // Tool node style
    `    classDef tool fill:${isDark ? toolFillDark : toolFillLight},stroke:${toolStrokeLight},stroke-width:3px,color:${isDark ? textDark : textLight},font-size:16px,radius:12px`,
    // Start agent node style
    `    classDef startAgent fill:${isDark ? startFillDark : startFillLight},stroke:${isDark ? startStrokeDark : startStrokeLight},stroke-width:3px,color:${isDark ? textDark : textLight},font-size:18px,radius:12px`,
    // Entry node style
    `    classDef entry fill:${isDark ? entryFillDark : entryFillLight},stroke:${isDark ? entryStrokeDark : entryStrokeLight},stroke-width:3px,color:${isDark ? textDark : '#fff'},font-size:16px,radius:12px`
  ];

  if (startAgentName) {
    const startAgentId = sanitizeId(startAgentName);
    mermaidCode.push(`\n    %% -- Entry Point --`);
    mermaidCode.push(`    Entry([Start]) --> ${startAgentId}`);
    mermaidCode.push(`    class Entry entry`);
  }

  mermaidCode.push(`\n    %% -- Agent Nodes --`);
  for (const agent of agents) {
    const agentName = agent.name;
    const agentId = sanitizeId(agentName);
    const nodeLabel = `🤖 ${agentName}`;
    mermaidCode.push(`    ${agentId}([\"${nodeLabel}\"])`);
    if (agentName === startAgentName) {
      mermaidCode.push(`    class ${agentId} startAgent`);
    } else {
      mermaidCode.push(`    class ${agentId} agent`);
    }
  }

  // --- Tool Nodes ---
  // 1. Collect all tool names from workflow.tools
  const toolNamesFromArray = new Set(tools.map((tool: any) => tool.name));
  // 2. Collect all tool names mentioned in agent instructions
  const agentMentionPattern = /\[@agent:([^\]]+)\]\(#mention[^\)]*\)/g;
  const toolMentionPattern = /\[@tool:([^\]]+)\]\(#mention[^\)]*\)/g;
  const toolNamesFromMentions = new Set<string>();
  for (const agent of agents) {
    const instructions = agent.instructions || "";
    let match: RegExpExecArray | null;
    while ((match = toolMentionPattern.exec(instructions))) {
      toolNamesFromMentions.add(match[1]);
    }
  }
  // 3. Union of all tool names
  const allToolNames = new Set([...toolNamesFromArray, ...toolNamesFromMentions]);
  // 4. Generate tool nodes for all
  mermaidCode.push(`\n    %% -- Tool Nodes --`);
  for (const toolName of allToolNames) {
    const toolId = sanitizeId(toolName);
    mermaidCode.push(`    ${toolId}([\"🛠️ ${toolName}\"])`);
    mermaidCode.push(`    class ${toolId} tool`);
  }

  // --- Connections ---
  mermaidCode.push(`\n    %% -- Connections --`);
  for (const agent of agents) {
    const currentAgentId = sanitizeId(agent.name);
    const instructions = agent.instructions || "";

    const calledAgents = new Set<string>();
    let match: RegExpExecArray | null;
    while ((match = agentMentionPattern.exec(instructions))) {
      calledAgents.add(match[1]);
    }
    for (const calledAgent of Array.from(calledAgents)) {
      const calledAgentId = sanitizeId(calledAgent);
      mermaidCode.push(`    ${currentAgentId} -- \"delegates to\" --> ${calledAgentId}`);
    }

    const calledTools = new Set<string>();
    while ((match = toolMentionPattern.exec(instructions))) {
      calledTools.add(match[1]);
    }
    for (const calledTool of Array.from(calledTools)) {
      const calledToolId = sanitizeId(calledTool);
      mermaidCode.push(`    ${currentAgentId} -- \"uses\" --> ${calledToolId}`);
    }
  }

  return mermaidCode.join("\n");
}

function getCssVarValue(varName: string, fallback: string) {
  if (typeof window === 'undefined') return fallback;
  let value = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  // If the value looks like HSL (e.g. '0 0% 9%' or '0 0% 3.9%' or '0 0% 9% / 1'), wrap it in hsl()
  if (/^[\d.]+\s+[\d.]+%\s+[\d.]+%(\s*\/\s*[\d.]+)?$/.test(value)) {
    value = `hsl(${value})`;
  }
  return value || fallback;
}

export const AgentGraphVisualizer = ({ workflow }: { workflow: any }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current && workflow) {
      // Only check theme on mount/render
      const isDark = document.documentElement.classList.contains('dark');
      mermaid.initialize({
        startOnLoad: true,
        theme: isDark ? 'dark' : 'default',
        themeVariables: {
          background: getCssVarValue('--background', isDark ? '#18181b' : '#fff'),
          primaryColor: isDark ? '#a78bfa' : getCssVarValue('--primary', '#4f46e5'),
          primaryTextColor: isDark ? '#fff' : getCssVarValue('--foreground', '#18181b'),
          fontSize: '20px',
          nodeTextColor: isDark ? '#fff' : getCssVarValue('--foreground', '#18181b'),
          edgeLabelBackground: isDark ? 'transparent' : getCssVarValue('--background', '#fff'),
          clusterBkg: getCssVarValue('--background', isDark ? '#18181b' : '#fff'),
          clusterBorder: isDark ? '#a78bfa' : getCssVarValue('--border', '#e5e7eb'),
          lineColor: isDark ? '#a78bfa' : '#6366f1',
          arrowheadColor: isDark ? '#a78bfa' : '#6366f1',
        },
      });
      ref.current.innerHTML = generateMermaidFromWorkflow(workflow, isDark);
      ref.current.className = "mermaid";
      mermaid.init(undefined, ref.current);
    }
  }, [workflow]);

  // Center the graph vertically and horizontally
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        minHeight: 0,
        background: "var(--background)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        overflow: "auto",
        padding: "16px",
      }}
    >
      <div
        ref={ref}
        style={{
          width: "100%",
          height: "fit-content",
          minHeight: 0,
          fontSize: 20,
        }}
      />
    </div>
  );
}; 
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
                <span className="text-xs text-neutral-400">{tools.length} tools {isOpen ? "\u25B2" : "\u25BC"}</span>
              </button>
              {isOpen && (
                <div className="px-3 pb-3 space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    {tools.map(t => (
                      <Badge key={t} className="bg-neutral-700 text-neutral-200 border-0 text-xs gap-1">
                        {t}
                        <button onClick={() => removeTool(agent, t)} className="ml-1 hover:text-red-400">&times;</button>
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

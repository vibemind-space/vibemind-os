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
    servers.length > 0 ? (
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
    ) : null
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

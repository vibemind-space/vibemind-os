"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useWS, Question } from "@/components/ws-provider";

interface FieldInfo {
  key: string;
  label?: string;
  input_type?: string; // "password" | "text"
  description?: string;
  how_to_get?: string;
  default?: string | null;
  required?: boolean;
}

interface ServerConfig {
  name: string;
  description?: string;
  type: string; // "secret" | "config"
  auto_config?: Record<string, unknown> | null;
  fields: FieldInfo[];
}

export function McpConfigView({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const meta = question.metadata as { servers?: ServerConfig[] };
  const servers = meta.servers || [];

  const autoServers = servers.filter(s => s.auto_config && s.fields.length === 0);
  const inputServers = servers.filter(s => !s.auto_config || s.fields.length > 0);

  const [values, setValues] = useState<Record<string, Record<string, string>>>(() => {
    const init: Record<string, Record<string, string>> = {};
    for (const server of inputServers) {
      init[server.name] = {};
      for (const field of server.fields) {
        init[server.name][field.key] = field.default || "";
      }
    }
    return init;
  });

  const setValue = (server: string, key: string, value: string) => {
    setValues(prev => ({
      ...prev,
      [server]: { ...prev[server], [key]: value },
    }));
  };

  const handleApply = () => {
    const configs: Record<string, Record<string, string>> = {};
    for (const [server, fields] of Object.entries(values)) {
      const filled: Record<string, string> = {};
      for (const [key, val] of Object.entries(fields)) {
        if (val.trim()) filled[key] = val.trim();
      }
      if (Object.keys(filled).length > 0) configs[server] = filled;
    }
    sendAnswer(question.id, "reply", JSON.stringify({ configs }));
  };

  const handleSkip = () => {
    sendAnswer(question.id, "reply", "skip");
  };

  const hasRequiredEmpty = inputServers.some(s =>
    s.fields.some(f => f.required && !values[s.name]?.[f.key]?.trim())
  );

  return (
    <div className="space-y-4">
      {autoServers.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-neutral-400">Auto-konfiguriert</h4>
          {autoServers.map(s => (
            <div key={s.name} className="flex items-center gap-2 p-2 rounded bg-neutral-800/50">
              <Badge className="bg-green-500/20 text-green-400 border-0 text-xs">Auto</Badge>
              <span className="text-sm text-neutral-200 font-medium">{s.name}</span>
              <span className="text-xs text-neutral-500">{s.description}</span>
              <code className="ml-auto text-xs text-neutral-500">{JSON.stringify(s.auto_config)}</code>
            </div>
          ))}
        </div>
      )}

      {inputServers.length > 0 && (
        <div className="space-y-3 max-h-[50vh] overflow-y-auto">
          {inputServers.map(s => (
            <div key={s.name} className="border border-neutral-700 rounded p-3 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-neutral-50">{s.name}</span>
                <Badge className={`${s.type === "secret" ? "bg-red-500/20 text-red-400" : "bg-blue-500/20 text-blue-400"} border-0 text-xs`}>
                  {s.type === "secret" ? "API Key" : "Config"}
                </Badge>
              </div>
              {s.description && <p className="text-xs text-neutral-400">{s.description}</p>}

              {s.fields.map(field => (
                <div key={field.key} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-neutral-300">
                      {field.label || field.key}
                      {field.required && <span className="text-red-400 ml-0.5">*</span>}
                    </label>
                    {field.how_to_get && (
                      <a
                        href={field.how_to_get}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-400 hover:text-blue-300 underline"
                      >
                        How to get
                      </a>
                    )}
                  </div>
                  {field.description && (
                    <p className="text-xs text-neutral-500">{field.description}</p>
                  )}
                  <input
                    type={field.input_type === "password" ? "password" : "text"}
                    value={values[s.name]?.[field.key] || ""}
                    onChange={e => setValue(s.name, field.key, e.target.value)}
                    placeholder={field.default || `Enter ${field.key}...`}
                    className="w-full bg-neutral-800 border border-neutral-600 text-neutral-200 text-sm rounded px-3 py-1.5 placeholder:text-neutral-600 focus:border-blue-500 focus:outline-none"
                  />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {inputServers.length === 0 && (
        <p className="text-sm text-neutral-400">Alle Server wurden automatisch konfiguriert.</p>
      )}

      <div className="flex justify-between items-center pt-2 border-t border-neutral-700">
        <Button variant="outline" onClick={handleSkip} className="border-neutral-600 text-neutral-400 hover:bg-neutral-800">
          Skip
        </Button>
        <Button
          onClick={handleApply}
          disabled={hasRequiredEmpty}
          className="bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
        >
          Apply Configuration
        </Button>
      </div>
    </div>
  );
}

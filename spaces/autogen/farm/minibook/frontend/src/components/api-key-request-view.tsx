"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useWS, Question } from "@/components/ws-provider";

export function ApiKeyRequestView({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const [keyValue, setKeyValue] = useState("");

  const meta = typeof question.metadata === "string"
    ? JSON.parse(question.metadata || "{}")
    : (question.metadata || {});
  const keyName = meta.key_name || question.tool_name || "API_KEY";
  const service = meta.service || "";

  const handleSubmit = () => {
    if (keyValue.trim()) {
      sendAnswer(question.id, "approve", keyValue.trim());
    }
  };

  const handleSkip = () => {
    sendAnswer(question.id, "reject", "");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Badge className="bg-purple-500/20 text-purple-400 border-0 text-xs">
          API Key Request
        </Badge>
        <code className="text-sm text-neutral-400 bg-neutral-800 px-2 py-0.5 rounded">
          {keyName}
        </code>
      </div>

      {service && (
        <p className="text-sm text-neutral-400">{service}</p>
      )}

      <div>
        <label className="text-xs font-medium text-neutral-400 mb-1 block">
          {keyName}
        </label>
        <input
          type="password"
          value={keyValue}
          onChange={(e) => setKeyValue(e.target.value)}
          placeholder={`Enter ${keyName}...`}
          className="w-full bg-neutral-800 border border-neutral-700 text-neutral-50 rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
        />
      </div>

      <div className="flex gap-2 justify-end">
        <Button
          variant="outline"
          onClick={handleSkip}
          className="border-neutral-700 text-neutral-400 hover:bg-neutral-800"
        >
          Skip
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!keyValue.trim()}
          className="bg-purple-600 hover:bg-purple-700 text-white"
        >
          Set Key
        </Button>
      </div>
    </div>
  );
}

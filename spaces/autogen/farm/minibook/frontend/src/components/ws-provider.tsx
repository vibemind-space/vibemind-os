"use client";

import { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from "react";

export interface Question {
  id: string;
  type: string;
  tool_name: string;
  todo_hint: string;
  mock_code: string;
  generated_code: string | null;
  options: string[];
  message: string;
  status: string;
  metadata: Record<string, unknown>;
}

interface WSContextValue {
  connected: boolean;
  questions: Question[];
  sendAnswer: (questionId: string, action: string, text?: string) => void;
  dismissQuestion: (questionId: string) => void;
}

const WSContext = createContext<WSContextValue>({
  connected: false,
  questions: [],
  sendAnswer: () => {},
  dismissQuestion: () => {},
});

export function useWS() {
  return useContext(WSContext);
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8899/ws/human";

export function WSProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Fetch any pending questions we missed
      fetch("/api/v1/questions/pending")
        .then(r => r.json())
        .then((pending: Question[]) => {
          if (pending.length > 0) {
            setQuestions(prev => {
              const ids = new Set(prev.map(q => q.id));
              return [...prev, ...pending.filter(q => !ids.has(q.id))];
            });
          }
        })
        .catch(() => {});
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event === "new_question") {
        setQuestions(prev => [...prev, data.question]);
      } else if (data.event === "question_answered") {
        setQuestions(prev => prev.filter(q => q.id !== data.question_id));
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendAnswer = useCallback((questionId: string, action: string, text = "") => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        event: "answer",
        question_id: questionId,
        action,
        text,
      }));
    } else {
      fetch(`/api/v1/questions/${questionId}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, text }),
      }).catch(console.error);
    }
    setQuestions(prev => prev.filter(q => q.id !== questionId));
  }, []);

  const dismissQuestion = useCallback((questionId: string) => {
    setQuestions(prev => prev.filter(q => q.id !== questionId));
  }, []);

  return (
    <WSContext.Provider value={{ connected, questions, sendAnswer, dismissQuestion }}>
      {children}
    </WSContext.Provider>
  );
}

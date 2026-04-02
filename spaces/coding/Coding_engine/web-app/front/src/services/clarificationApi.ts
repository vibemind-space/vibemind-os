// web-app/front/src/services/clarificationApi.ts
import { API_URL } from './api';
const API_BASE = API_URL;

export interface Clarification {
  id: string;
  task_id: string;
  question: string;
  options?: { id: string; label: string; description?: string }[];
  status: 'pending' | 'resolved';
}

export const getClarifications = async (): Promise<Clarification[]> => {
  const res = await fetch(`${API_BASE}/clarifications`);
  return res.json();
};

export const submitClarificationChoice = async (id: string, choiceId: string): Promise<void> => {
  await fetch(`${API_BASE}/clarifications/${id}/choice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ choice_id: choiceId }),
  });
};

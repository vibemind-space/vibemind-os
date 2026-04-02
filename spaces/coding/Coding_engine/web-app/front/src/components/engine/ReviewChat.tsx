// web-app/front/src/components/engine/ReviewChat.tsx
import { useState } from 'react';
import { useEngineStore } from '@/stores/engineStore';

import { API_URL } from '@/services/api';
const API_BASE = API_URL;

export function ReviewChat({ projectId }: { projectId: string }) {
  const reviewPaused = useEngineStore(state => state.reviewPaused);
  const [feedback, setFeedback] = useState('');
  const [sending, setSending] = useState(false);

  const handlePause = async () => {
    await fetch(`${API_BASE}/dashboard/generation/${projectId}/pause`, { method: 'POST' });
  };

  const handleResume = async () => {
    setSending(true);
    try {
      await fetch(`${API_BASE}/dashboard/generation/${projectId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback }),
      });
      setFeedback('');
    } finally {
      setSending(false);
    }
  };

  if (!reviewPaused) {
    return (
      <div className="p-4">
        <button
          onClick={handlePause}
          className="px-4 py-2 rounded-lg bg-yellow-600 hover:bg-yellow-500 text-white text-sm font-medium"
        >
          Pause for Review
        </button>
        <p className="text-xs text-white/40 mt-2">
          Pauses generation at the next checkpoint so you can review and provide feedback.
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 border border-yellow-500/30 rounded-lg bg-yellow-500/5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
        <span className="text-sm font-semibold text-yellow-400">Generation Paused — Awaiting Review</span>
      </div>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder="Describe issues or adjustments needed..."
        className="w-full h-32 p-3 rounded-lg bg-white/5 border border-white/20 text-white text-sm placeholder:text-white/30 resize-none"
      />
      <div className="flex gap-2 mt-3">
        <button
          onClick={handleResume}
          disabled={sending}
          className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium disabled:opacity-50"
        >
          {sending ? 'Resuming...' : 'Resume with Feedback'}
        </button>
        <button
          onClick={() => { setFeedback(''); handleResume(); }}
          disabled={sending}
          className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm"
        >
          Resume (No Changes)
        </button>
      </div>
    </div>
  );
}

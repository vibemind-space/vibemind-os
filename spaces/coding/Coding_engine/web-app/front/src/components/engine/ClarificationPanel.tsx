// web-app/front/src/components/engine/ClarificationPanel.tsx
import { useState, useEffect } from 'react';
import { useEngineStore } from '@/stores/engineStore';
import { getClarifications, submitClarificationChoice, type Clarification } from '@/services/clarificationApi';

export function ClarificationPanel() {
  const wsClarifications = useEngineStore(state => state.clarifications);
  const [clarifications, setClarifications] = useState<Clarification[]>([]);
  const [submitting, setSubmitting] = useState<string | null>(null);

  useEffect(() => {
    getClarifications()
      .then((data) => setClarifications(Array.isArray(data) ? data : []))
      .catch(() => setClarifications([]));
  }, [wsClarifications.length]);

  const handleChoice = async (clarId: string, choiceId: string) => {
    setSubmitting(clarId);
    try {
      await submitClarificationChoice(clarId, choiceId);
      setClarifications(prev => prev.filter(c => c.id !== clarId));
    } finally {
      setSubmitting(null);
    }
  };

  const pending = clarifications.filter(c => c.status === 'pending');

  if (pending.length === 0) {
    return <div className="p-4 text-sm text-white/40">No pending clarifications.</div>;
  }

  return (
    <div className="p-4 space-y-4">
      {pending.map(clar => (
        <div key={clar.id} className="p-4 bg-white/5 rounded-lg border border-amber-500/20">
          <div className="text-sm font-medium text-amber-400 mb-1">Clarification Needed</div>
          <p className="text-sm text-white mb-3">{clar.question}</p>
          {clar.options && (
            <div className="space-y-2">
              {clar.options.map(opt => (
                <button
                  key={opt.id}
                  onClick={() => handleChoice(clar.id, opt.id)}
                  disabled={submitting === clar.id}
                  className="w-full text-left p-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition-colors disabled:opacity-50"
                >
                  <div className="text-sm text-white font-medium">{opt.label}</div>
                  {opt.description && <div className="text-xs text-white/50 mt-1">{opt.description}</div>}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

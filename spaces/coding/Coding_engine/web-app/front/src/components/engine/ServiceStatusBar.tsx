// web-app/front/src/components/engine/ServiceStatusBar.tsx
import { useState, useEffect } from 'react';
import { platform, platformEvents, isElectron } from '@/services/platform';
import { API_URL } from '@/services/api';

interface Status {
  fastapi: boolean;
  docker: boolean;
}

export function ServiceStatusBar() {
  const [status, setStatus] = useState<Status>({ fastapi: false, docker: false });

  useEffect(() => {
    const checkStatus = async () => {
      try {
        if (isElectron()) {
          const s = await window.electronAPI!.services.getStatus();
          setStatus({ fastapi: s.fastapi, docker: s.docker });
        } else {
          // Use root endpoint as health check (returns 200 if API is running)
          const res = await fetch(API_URL.replace('/api/v1', '/'));
          setStatus({ fastapi: res.ok, docker: false });
        }
      } catch {
        setStatus({ fastapi: false, docker: false });
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 10000);

    platformEvents.onServiceStatusUpdate((s) => {
      setStatus({ fastapi: s.fastapi, docker: s.docker });
    });

    return () => clearInterval(interval);
  }, []);

  const Dot = ({ active }: { active: boolean }) => (
    <span className={`w-1.5 h-1.5 rounded-full inline-block ${active ? 'bg-green-400' : 'bg-red-400'}`} />
  );

  return (
    <div className="flex items-center gap-3 text-xs text-white/60">
      <span className="flex items-center gap-1"><Dot active={status.fastapi} /> API</span>
      {isElectron() && <span className="flex items-center gap-1"><Dot active={status.docker} /> Docker</span>}
    </div>
  );
}

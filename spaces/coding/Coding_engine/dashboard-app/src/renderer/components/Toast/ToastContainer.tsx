import React from 'react'
import { useEngineStore } from '../../stores/engineStore'
import type { Toast } from '../../stores/engineStore'
import { X, AlertCircle, CheckCircle2, AlertTriangle } from 'lucide-react'

const iconMap: Record<Toast['type'], React.ReactNode> = {
  error: <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />,
  success: <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0" />,
  warning: <AlertTriangle className="w-5 h-5 text-yellow-400 shrink-0" />,
}

const borderColorMap: Record<Toast['type'], string> = {
  error: 'border-l-red-500',
  success: 'border-l-green-500',
  warning: 'border-l-yellow-500',
}

export function ToastContainer() {
  const toasts = useEngineStore((s) => s.toasts)
  const removeToast = useEngineStore((s) => s.removeToast)

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`
            animate-slide-in-right
            bg-slate-800 border-l-4 ${borderColorMap[toast.type]}
            rounded-lg shadow-xl p-3 flex items-start gap-3
            text-sm text-slate-200
          `}
        >
          {iconMap[toast.type]}
          <div className="flex-1 min-w-0">
            <div className="font-medium text-white truncate">{toast.title}</div>
            <div className="text-slate-400 mt-0.5 line-clamp-2">{toast.message}</div>
          </div>
          <button
            onClick={() => removeToast(toast.id)}
            className="shrink-0 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  )
}

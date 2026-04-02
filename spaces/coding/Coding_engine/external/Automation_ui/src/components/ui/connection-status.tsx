/**
 * Connection Status Component
 * Displays WebSocket connection status with visual indicators
 * Works with useWebSocketReconnect hook
 */

import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Wifi, WifiOff, RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import type { ConnectionStatus } from '@/hooks/useWebSocketReconnect';

interface ConnectionStatusIndicatorProps {
  /** Current connection status */
  status: ConnectionStatus;
  /** Number of reconnection attempts */
  reconnectAttempt?: number;
  /** Last error message */
  lastError?: string | null;
  /** Callback for manual reconnection */
  onReconnect?: () => void;
  /** Show detailed status text (default: true) */
  showDetails?: boolean;
  /** Compact mode (default: false) */
  compact?: boolean;
}

const statusConfig = {
  connected: {
    icon: Wifi,
    label: 'Connected',
    color: 'bg-green-500/10 text-green-600 border-green-500/20',
    iconColor: 'text-green-600',
  },
  connecting: {
    icon: Loader2,
    label: 'Connecting...',
    color: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
    iconColor: 'text-blue-600 animate-spin',
  },
  reconnecting: {
    icon: RefreshCw,
    label: 'Reconnecting...',
    color: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20',
    iconColor: 'text-yellow-600 animate-spin',
  },
  disconnected: {
    icon: WifiOff,
    label: 'Disconnected',
    color: 'bg-gray-500/10 text-gray-600 border-gray-500/20',
    iconColor: 'text-gray-600',
  },
  error: {
    icon: AlertCircle,
    label: 'Error',
    color: 'bg-red-500/10 text-red-600 border-red-500/20',
    iconColor: 'text-red-600',
  },
};

export const ConnectionStatusIndicator: React.FC<ConnectionStatusIndicatorProps> = ({
  status,
  reconnectAttempt = 0,
  lastError,
  onReconnect,
  showDetails = true,
  compact = false,
}) => {
  const config = statusConfig[status];
  const Icon = config.icon;
  const showReconnectButton = (status === 'disconnected' || status === 'error') && onReconnect;

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="outline" className={`${config.color} flex items-center gap-1.5 px-2 py-1`}>
          <Icon className={`h-3 w-3 ${config.iconColor}`} />
          <span className="text-xs font-medium">{config.label}</span>
        </Badge>
        {showReconnectButton && (
          <Button
            size="sm"
            variant="ghost"
            onClick={onReconnect}
            className="h-7 w-7 p-0"
            title="Reconnect"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card p-3">
      <div className={`rounded-full p-2 ${config.color}`}>
        <Icon className={`h-4 w-4 ${config.iconColor}`} />
      </div>

      <div className="flex-1 space-y-0.5">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium leading-none">{config.label}</p>
          {status === 'reconnecting' && reconnectAttempt > 0 && showDetails && (
            <Badge variant="outline" className="text-xs">
              Attempt {reconnectAttempt}
            </Badge>
          )}
        </div>

        {showDetails && (
          <>
            {lastError && (
              <p className="text-xs text-muted-foreground text-red-600">
                {lastError}
              </p>
            )}
            {status === 'connected' && (
              <p className="text-xs text-muted-foreground">
                Real-time connection active
              </p>
            )}
            {status === 'reconnecting' && (
              <p className="text-xs text-muted-foreground">
                Attempting to restore connection...
              </p>
            )}
          </>
        )}
      </div>

      {showReconnectButton && (
        <Button
          size="sm"
          variant="outline"
          onClick={onReconnect}
          className="gap-2"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Reconnect
        </Button>
      )}
    </div>
  );
};

/**
 * Minimal connection indicator (just icon + color)
 */
export const ConnectionStatusDot: React.FC<Pick<ConnectionStatusIndicatorProps, 'status'>> = ({ status }) => {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 ${config.color}`}
      title={config.label}
    >
      <Icon className={`h-3 w-3 ${config.iconColor}`} />
    </div>
  );
};

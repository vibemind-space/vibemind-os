import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Wifi, WifiOff, RefreshCw, AlertCircle } from "lucide-react";
import type {
  ConnectionStatus,
  CircuitBreakerState,
} from "@/hooks/useWebSocketReconnect";

interface ConnectionStatusCardProps {
  status: ConnectionStatus;
  isConnected: boolean;
  isLoading?: boolean;
  lastError?: string | null;
  reconnectAttempt?: number;
  maxReconnectAttempts?: number;
  circuitBreakerState?: CircuitBreakerState;
  onConnect: () => void;
  onDisconnect: () => void;
  onRetry?: () => void;
  onResetCircuitBreaker?: () => void;
}

export const ConnectionStatusCard: React.FC<ConnectionStatusCardProps> = ({
  status,
  isConnected,
  isLoading = false,
  lastError,
  reconnectAttempt = 0,
  maxReconnectAttempts = 10,
  circuitBreakerState,
  onConnect,
  onDisconnect,
  onRetry,
  onResetCircuitBreaker,
}) => {
  const getStatusColor = () => {
    if (circuitBreakerState === "open") {return "text-red-500";}
    switch (status) {
      case "connected":
        return "text-green-500";
      case "connecting":
      case "reconnecting":
        return "text-yellow-500";
      case "disconnected":
      case "failed":
        return "text-red-500";
      default:
        return "text-gray-500";
    }
  };

  const getStatusText = () => {
    if (circuitBreakerState === "open") {return "Circuit Breaker Open";}
    switch (status) {
      case "connected":
        return "Connected";
      case "connecting":
        return "Connecting...";
      case "reconnecting":
        return `Reconnecting (${reconnectAttempt}/${maxReconnectAttempts})`;
      case "disconnected":
        return "Disconnected";
      case "failed":
        return "Connection Failed";
      default:
        return "Unknown";
    }
  };

  return (
    <Card className="mb-4">
      <CardContent className="p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isConnected ? (
              <Wifi className={`w-4 h-4 ${getStatusColor()}`} />
            ) : (
              <WifiOff className={`w-4 h-4 ${getStatusColor()}`} />
            )}
            <span className={`text-sm font-medium ${getStatusColor()}`}>
              {getStatusText()}
            </span>
            {lastError && (
              <span className="text-xs text-red-400 ml-2 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {lastError}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            {circuitBreakerState === "open" && onResetCircuitBreaker && (
              <Button
                size="sm"
                variant="outline"
                onClick={onResetCircuitBreaker}
              >
                Reset
              </Button>
            )}
            {isConnected ? (
              <Button size="sm" variant="outline" onClick={onDisconnect}>
                Disconnect
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={onRetry || onConnect}
                disabled={isLoading}
              >
                {isLoading && (
                  <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                )}
                {status === "failed" ? "Retry" : "Connect"}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

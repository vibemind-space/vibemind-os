import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Monitor } from "lucide-react";

interface DualMonitorWorkflowProps {
  primaryStreamUrl: string | null;
  secondaryStreamUrl: string | null;
  isConnected: boolean;
  websocket: WebSocket | null;
  onWorkflowExecute?: (monitorId: string, steps: any[]) => void;
  onWorkflowStop?: (monitorId: string) => void;
}

export const DualMonitorWorkflow: React.FC<DualMonitorWorkflowProps> = ({
  primaryStreamUrl,
  secondaryStreamUrl,
  isConnected,
}) => {
  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Monitor className="w-4 h-4" />
          Dual Monitor View
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {/* Primary Monitor */}
          <div className="space-y-2">
            <span className="text-xs text-muted-foreground">
              Primary Monitor
            </span>
            <div className="aspect-video bg-muted rounded overflow-hidden">
              {primaryStreamUrl ? (
                <img
                  src={primaryStreamUrl}
                  alt="Primary Monitor"
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-sm text-muted-foreground">
                    {isConnected ? "Waiting for stream..." : "Not connected"}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Secondary Monitor */}
          <div className="space-y-2">
            <span className="text-xs text-muted-foreground">
              Secondary Monitor
            </span>
            <div className="aspect-video bg-muted rounded overflow-hidden">
              {secondaryStreamUrl ? (
                <img
                  src={secondaryStreamUrl}
                  alt="Secondary Monitor"
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-sm text-muted-foreground">
                    {isConnected ? "No secondary monitor" : "Not connected"}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

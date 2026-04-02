import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { RefreshCw, Monitor } from "lucide-react";

export interface DesktopClient {
  id: string;
  connected: boolean;
  monitors?: string[];
  availableMonitors?: any[];
  timestamp?: string;
}

interface ClientSelectorCardProps {
  availableClients: DesktopClient[];
  selectedClients: string[];
  isConnected: boolean;
  onToggleClient: (clientId: string) => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onRefresh: () => void;
}

export const ClientSelectorCard: React.FC<ClientSelectorCardProps> = ({
  availableClients,
  selectedClients,
  isConnected,
  onToggleClient,
  onSelectAll,
  onClearSelection,
  onRefresh,
}) => {
  return (
    <Card className="mb-4">
      <CardHeader className="py-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Monitor className="w-4 h-4" />
            Desktop Clients ({availableClients.length})
          </CardTitle>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={onRefresh}
              disabled={!isConnected}
            >
              <RefreshCw className="w-3 h-3" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onSelectAll}
              disabled={!isConnected}
            >
              Select All
            </Button>
            <Button size="sm" variant="outline" onClick={onClearSelection}>
              Clear
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {availableClients.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No desktop clients connected
          </p>
        ) : (
          <div className="space-y-2">
            {availableClients.map((client) => (
              <div
                key={client.id}
                className="flex items-center gap-2 p-2 rounded border hover:bg-muted/50 cursor-pointer"
                onClick={() => onToggleClient(client.id)}
              >
                <Checkbox
                  checked={selectedClients.includes(client.id)}
                  onCheckedChange={() => onToggleClient(client.id)}
                />
                <span className="text-sm flex-1">{client.id}</span>
                <span
                  className={`text-xs ${client.connected ? "text-green-500" : "text-red-500"}`}
                >
                  {client.connected ? "Connected" : "Disconnected"}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

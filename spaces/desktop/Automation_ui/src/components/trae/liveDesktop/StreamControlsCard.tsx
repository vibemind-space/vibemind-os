import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Play, Square } from "lucide-react";

interface StreamControlsCardProps {
  isStreamingActive: boolean;
  isConnected: boolean;
  selectedClientsCount: number;
  onStartStream: () => void;
  onStopStream: () => void;
}

export const StreamControlsCard: React.FC<StreamControlsCardProps> = ({
  isStreamingActive,
  isConnected,
  selectedClientsCount,
  onStartStream,
  onStopStream,
}) => {
  return (
    <Card className="mb-4">
      <CardContent className="p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {selectedClientsCount} client(s) selected
            </span>
          </div>
          <div className="flex gap-2">
            {isStreamingActive ? (
              <Button size="sm" variant="destructive" onClick={onStopStream}>
                <Square className="w-3 h-3 mr-1" />
                Stop Stream
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={onStartStream}
                disabled={!isConnected || selectedClientsCount === 0}
              >
                <Play className="w-3 h-3 mr-1" />
                Start Stream
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

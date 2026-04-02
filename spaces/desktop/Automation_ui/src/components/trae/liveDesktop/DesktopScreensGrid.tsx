import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, Monitor } from "lucide-react";

export interface DesktopScreen {
  id: string;
  name: string;
  thumbnail?: string;
  isActive: boolean;
  resolution: {
    width: number;
    height: number;
  };
  connected: boolean;
}

interface DesktopScreensGridProps {
  desktopScreens: DesktopScreen[];
  latestScreenshots: { [key: string]: string };
  onSwitchDesktop: (desktopId: string) => void;
  onCreateNewDesktop: () => void;
}

export const DesktopScreensGrid: React.FC<DesktopScreensGridProps> = ({
  desktopScreens,
  latestScreenshots,
  onSwitchDesktop,
  onCreateNewDesktop,
}) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-4">
      {desktopScreens.map((screen) => (
        <Card
          key={screen.id}
          className={`cursor-pointer transition-all hover:ring-2 hover:ring-primary ${
            screen.isActive ? "ring-2 ring-primary" : ""
          }`}
          onClick={() => onSwitchDesktop(screen.id)}
        >
          <CardContent className="p-2">
            <div className="aspect-video bg-muted rounded overflow-hidden mb-2">
              {latestScreenshots[screen.id] ? (
                <img
                  src={latestScreenshots[screen.id]}
                  alt={screen.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <Monitor className="w-8 h-8 text-muted-foreground" />
                </div>
              )}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium truncate">
                {screen.name}
              </span>
              <span
                className={`w-2 h-2 rounded-full ${screen.connected ? "bg-green-500" : "bg-red-500"}`}
              />
            </div>
          </CardContent>
        </Card>
      ))}
      <Card
        className="cursor-pointer transition-all hover:ring-2 hover:ring-primary border-dashed"
        onClick={onCreateNewDesktop}
      >
        <CardContent className="p-2">
          <div className="aspect-video bg-muted/50 rounded flex items-center justify-center mb-2">
            <Plus className="w-8 h-8 text-muted-foreground" />
          </div>
          <span className="text-xs text-muted-foreground">Add Desktop</span>
        </CardContent>
      </Card>
    </div>
  );
};

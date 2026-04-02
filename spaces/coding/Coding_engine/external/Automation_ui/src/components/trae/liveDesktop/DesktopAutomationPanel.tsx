import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Mouse, Keyboard, Send } from "lucide-react";

interface DesktopAutomationPanelProps {
  desktopClientId: string;
  monitorId: string;
  wsConnection: WebSocket | null;
  isConnected: boolean;
  streamWidth: number;
  streamHeight: number;
}

export const DesktopAutomationPanel: React.FC<DesktopAutomationPanelProps> = ({
  desktopClientId,
  monitorId,
  wsConnection,
  isConnected,
  streamWidth,
  streamHeight,
}) => {
  const [textInput, setTextInput] = useState("");
  const [clickX, setClickX] = useState(0);
  const [clickY, setClickY] = useState(0);

  const sendCommand = (command: object) => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
      wsConnection.send(
        JSON.stringify({
          ...command,
          desktopClientId,
          monitorId,
          timestamp: new Date().toISOString(),
        }),
      );
    }
  };

  const handleClick = () => {
    sendCommand({
      type: "mouse_click",
      x: clickX,
      y: clickY,
      button: "left",
    });
  };

  const handleTypeText = () => {
    if (!textInput.trim()) {return;}
    sendCommand({
      type: "type_text",
      text: textInput,
    });
    setTextInput("");
  };

  const handleKeyPress = (key: string) => {
    sendCommand({
      type: "key_press",
      key,
    });
  };

  return (
    <Card>
      <CardHeader className="py-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Mouse className="w-4 h-4" />
          Desktop Automation
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Click Controls */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">
            Click Position
          </label>
          <div className="flex gap-2">
            <Input
              type="number"
              placeholder="X"
              value={clickX}
              onChange={(e) => setClickX(parseInt(e.target.value) || 0)}
              className="w-20"
              max={streamWidth}
            />
            <Input
              type="number"
              placeholder="Y"
              value={clickY}
              onChange={(e) => setClickY(parseInt(e.target.value) || 0)}
              className="w-20"
              max={streamHeight}
            />
            <Button size="sm" onClick={handleClick} disabled={!isConnected}>
              <Mouse className="w-3 h-3 mr-1" />
              Click
            </Button>
          </div>
        </div>

        {/* Type Text */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Type Text</label>
          <div className="flex gap-2">
            <Input
              placeholder="Text to type..."
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleTypeText()}
              className="flex-1"
            />
            <Button
              size="sm"
              onClick={handleTypeText}
              disabled={!isConnected || !textInput.trim()}
            >
              <Send className="w-3 h-3 mr-1" />
              Send
            </Button>
          </div>
        </div>

        {/* Quick Keys */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Quick Keys</label>
          <div className="flex gap-2 flex-wrap">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleKeyPress("enter")}
              disabled={!isConnected}
            >
              <Keyboard className="w-3 h-3 mr-1" />
              Enter
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleKeyPress("escape")}
              disabled={!isConnected}
            >
              Esc
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleKeyPress("tab")}
              disabled={!isConnected}
            >
              Tab
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleKeyPress("backspace")}
              disabled={!isConnected}
            >
              ←
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

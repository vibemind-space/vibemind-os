/**
 * Clawdbot Status Panel
 *
 * Displays the status of the Clawdbot messaging integration,
 * active sessions, message history, and allows testing commands.
 */

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  ClawdbotService,
  type ClawdbotStatus,
  type ClawdbotSession,
  type ClawdbotMessage,
} from "@/services/clawdbotService";
import {
  RefreshCw,
  Send,
  Camera,
  MessageSquare,
  Users,
  Activity,
  Wifi,
  WifiOff,
  Smartphone,
  Package,
} from "lucide-react";
import { InstalledSkillsPanel } from "./InstalledSkillsPanel";
import { SkillMarketplace } from "./SkillMarketplace";

// Platform icons/labels
const PLATFORM_INFO: Record<
  string,
  { icon: string; label: string; color: string }
> = {
  whatsapp: { icon: "📱", label: "WhatsApp", color: "bg-green-500" },
  telegram: { icon: "✈️", label: "Telegram", color: "bg-blue-500" },
  discord: { icon: "🎮", label: "Discord", color: "bg-indigo-500" },
  slack: { icon: "💼", label: "Slack", color: "bg-purple-500" },
  signal: { icon: "🔒", label: "Signal", color: "bg-blue-600" },
  imessage: { icon: "💬", label: "iMessage", color: "bg-blue-400" },
  web: { icon: "🌐", label: "Web", color: "bg-gray-500" },
  api: { icon: "⚡", label: "API", color: "bg-yellow-500" },
};

export function ClawdbotStatusPanel() {
  const [status, setStatus] = useState<ClawdbotStatus | null>(null);
  const [sessions, setSessions] = useState<ClawdbotSession[]>([]);
  const [messages, setMessages] = useState<ClawdbotMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [command, setCommand] = useState("");
  const [executing, setExecuting] = useState(false);
  const [skillsView, setSkillsView] = useState<"installed" | "marketplace">(
    "installed",
  );

  // Fetch status
  const fetchStatus = useCallback(async () => {
    try {
      const [statusData, sessionsData] = await Promise.all([
        ClawdbotService.getStatus(),
        ClawdbotService.getSessions(),
      ]);
      setStatus(statusData);
      setSessions(sessionsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + polling
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Update message history from service
  useEffect(() => {
    const updateMessages = () => {
      setMessages(ClawdbotService.getMessageHistory(50));
    };
    updateMessages();
    const interval = setInterval(updateMessages, 2000);
    return () => clearInterval(interval);
  }, []);

  // Execute command
  const handleExecute = async () => {
    if (!command.trim()) {
      return;
    }

    setExecuting(true);
    try {
      const result = await ClawdbotService.executeCommand({
        command: command.trim(),
        platform: "web",
        user_id: "web_user",
      });

      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message || "Command failed");
      }

      setCommand("");
      setMessages(ClawdbotService.getMessageHistory(50));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setExecuting(false);
    }
  };

  // Take screenshot
  const handleScreenshot = async () => {
    setExecuting(true);
    try {
      const result = await ClawdbotService.executeCommand({
        command: "screenshot",
        platform: "web",
        user_id: "web_user",
      });

      if (result.success) {
        toast.success("Screenshot aufgenommen");
        setMessages(ClawdbotService.getMessageHistory(50));
      } else {
        toast.error(result.message || "Screenshot failed");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Screenshot failed");
    } finally {
      setExecuting(false);
    }
  };

  // Status indicator
  const StatusIndicator = () => {
    if (loading) {
      return (
        <Badge variant="outline" className="animate-pulse">
          <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
          Connecting...
        </Badge>
      );
    }

    if (error || !status) {
      return (
        <Badge variant="destructive">
          <WifiOff className="w-3 h-3 mr-1" />
          Disconnected
        </Badge>
      );
    }

    return (
      <Badge variant="default" className="bg-green-500">
        <Wifi className="w-3 h-3 mr-1" />
        Connected
      </Badge>
    );
  };

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="w-5 h-5" />
              Clawdbot Integration
            </CardTitle>
            <CardDescription>
              Desktop automation via WhatsApp, Telegram & more
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <StatusIndicator />
            <Button
              variant="ghost"
              size="icon"
              onClick={fetchStatus}
              disabled={loading}
            >
              <RefreshCw
                className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <Tabs defaultValue="status" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="status">
              <Activity className="w-4 h-4 mr-1" />
              Status
            </TabsTrigger>
            <TabsTrigger value="skills">
              <Package className="w-4 h-4 mr-1" />
              Skills
            </TabsTrigger>
            <TabsTrigger value="sessions">
              <Users className="w-4 h-4 mr-1" />
              Sessions ({sessions.length})
            </TabsTrigger>
            <TabsTrigger value="messages">
              <MessageSquare className="w-4 h-4 mr-1" />
              History
            </TabsTrigger>
          </TabsList>

          {/* Status Tab */}
          <TabsContent value="status" className="space-y-4">
            {status ? (
              <>
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <div className="p-3 rounded-lg bg-muted">
                    <div className="text-sm text-muted-foreground">Status</div>
                    <div className="text-lg font-semibold capitalize">
                      {status.status}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-muted">
                    <div className="text-sm text-muted-foreground">
                      Active Sessions
                    </div>
                    <div className="text-lg font-semibold">
                      {status.active_sessions}
                    </div>
                  </div>
                </div>

                <div>
                  <div className="mb-2 text-sm font-medium">Capabilities</div>
                  <div className="flex flex-wrap gap-1">
                    {status.capabilities.map((cap) => (
                      <Badge key={cap} variant="secondary" className="text-xs">
                        {cap}
                      </Badge>
                    ))}
                  </div>
                </div>

                <Separator />

                {/* Test Command */}
                <div className="space-y-2">
                  <div className="text-sm font-medium">Test Command</div>
                  <div className="flex gap-2">
                    <Input
                      value={command}
                      onChange={(e) => setCommand(e.target.value)}
                      placeholder="z.B. 'öffne chrome' oder 'screenshot'"
                      onKeyDown={(e) => e.key === "Enter" && handleExecute()}
                      disabled={executing}
                    />
                    <Button
                      onClick={handleExecute}
                      disabled={executing || !command.trim()}
                    >
                      <Send className="w-4 h-4 mr-1" />
                      Send
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleScreenshot}
                      disabled={executing}
                    >
                      <Camera className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <div className="py-8 text-center text-muted-foreground">
                {error || "Unable to connect to Clawdbot bridge"}
              </div>
            )}
          </TabsContent>

          {/* Skills Tab */}
          <TabsContent value="skills" className="mt-4">
            <div className="flex items-center gap-2 mb-3">
              <button
                onClick={() => setSkillsView("installed")}
                className={`text-sm px-3 py-1 rounded-md transition-colors ${
                  skillsView === "installed"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:text-foreground"
                }`}
              >
                Installed
              </button>
              <button
                onClick={() => setSkillsView("marketplace")}
                className={`text-sm px-3 py-1 rounded-md transition-colors ${
                  skillsView === "marketplace"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:text-foreground"
                }`}
              >
                Marketplace
              </button>
            </div>

            {skillsView === "installed" ? (
              <InstalledSkillsPanel
                onBrowseMarketplace={() => setSkillsView("marketplace")}
                maxHeight="350px"
              />
            ) : (
              <SkillMarketplace maxHeight="350px" />
            )}
          </TabsContent>

          {/* Sessions Tab */}
          <TabsContent value="sessions">
            <ScrollArea className="h-[300px] mt-4">
              {sessions.length > 0 ? (
                <div className="space-y-2">
                  {sessions.map((session, idx) => {
                    const platformInfo =
                      PLATFORM_INFO[session.platform] || PLATFORM_INFO.web;
                    return (
                      <div
                        key={`${session.platform}-${session.user_id}-${idx}`}
                        className="flex items-center gap-3 p-3 rounded-lg bg-muted"
                      >
                        <div
                          className={`w-8 h-8 rounded-full flex items-center justify-center ${platformInfo.color}`}
                        >
                          <span className="text-white text-sm">
                            {platformInfo.icon}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">
                            {session.user_id}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {platformInfo.label} •{" "}
                            {session.last_command || "No commands yet"}
                          </div>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {new Date(session.updated_at).toLocaleTimeString()}
                        </Badge>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  <Smartphone className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>No active sessions</p>
                  <p className="text-xs mt-1">
                    Connect via WhatsApp, Telegram, or other platforms
                  </p>
                </div>
              )}
            </ScrollArea>
          </TabsContent>

          {/* Messages Tab */}
          <TabsContent value="messages">
            <ScrollArea className="h-[300px] mt-4">
              {messages.length > 0 ? (
                <div className="space-y-2">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`p-3 rounded-lg ${
                        msg.direction === "outgoing"
                          ? "bg-primary/10 ml-8"
                          : "bg-muted mr-8"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs">
                            {PLATFORM_INFO[msg.platform]?.icon || "🌐"}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {msg.direction === "outgoing" ? "You" : "Response"}
                          </span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-sm">{msg.text}</p>
                      {msg.image && (
                        <img
                          src={`data:image/jpeg;base64,${msg.image}`}
                          alt="Screenshot"
                          className="mt-2 rounded max-h-32 object-contain"
                        />
                      )}
                      {msg.success !== undefined && (
                        <Badge
                          variant={msg.success ? "default" : "destructive"}
                          className="mt-1 text-xs"
                        >
                          {msg.success ? "Success" : "Failed"}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  <MessageSquare className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>No messages yet</p>
                  <p className="text-xs mt-1">
                    Send a test command or connect via messaging platform
                  </p>
                </div>
              )}
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

export default ClawdbotStatusPanel;

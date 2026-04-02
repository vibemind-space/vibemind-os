/**
 * InstalledSkillsPanel - Manage locally installed skills
 *
 * Shows installed skills with toggle, execute, and uninstall actions.
 */

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import {
  Play,
  Trash2,
  Loader2,
  Package,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
} from "lucide-react";
import {
  ClawHubService,
  CATEGORY_INFO,
  type InstalledSkill,
  type SkillStats,
  type SkillCategory,
} from "@/services/clawhubService";

interface InstalledSkillsPanelProps {
  onExecuteSkill?: (skillId: string) => void;
  onBrowseMarketplace?: () => void;
  maxHeight?: string;
}

export function InstalledSkillsPanel({
  onExecuteSkill,
  onBrowseMarketplace,
  maxHeight = "400px",
}: InstalledSkillsPanelProps) {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [stats, setStats] = useState<SkillStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState<string | null>(null);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const [installed, statsData] = await Promise.all([
        ClawHubService.getInstalledSkills(),
        ClawHubService.getStats(),
      ]);
      setSkills(installed);
      setStats(statsData);
    } catch (err) {
      console.error("Failed to load installed skills:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const handleToggle = async (skillId: string, enabled: boolean) => {
    try {
      await ClawHubService.toggleSkill(skillId, enabled);
      setSkills((prev) =>
        prev.map((s) => (s.id === skillId ? { ...s, enabled } : s)),
      );
      toast.success(`${skillId} ${enabled ? "enabled" : "disabled"}`);
    } catch (err) {
      toast.error("Toggle failed");
    }
  };

  const handleExecute = async (skillId: string) => {
    if (onExecuteSkill) {
      onExecuteSkill(skillId);
      return;
    }

    setExecuting(skillId);
    try {
      const result = await ClawHubService.executeSkill(skillId);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message || "Execution failed");
      }
      loadSkills(); // Refresh execution counts
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setExecuting(null);
    }
  };

  const handleUninstall = async (skillId: string, skillName: string) => {
    try {
      await ClawHubService.uninstallSkill(skillId);
      setSkills((prev) => prev.filter((s) => s.id !== skillId));
      toast.success(`${skillName} uninstalled`);
    } catch (err) {
      toast.error("Uninstall failed");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Stats Bar */}
      {stats && (
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Package className="w-3 h-3" />
            {stats.total_installed} installed
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle className="w-3 h-3 text-green-500" />
            {stats.enabled} enabled
          </span>
          {stats.disabled > 0 && (
            <span className="flex items-center gap-1">
              <XCircle className="w-3 h-3 text-yellow-500" />
              {stats.disabled} disabled
            </span>
          )}
          <span className="flex items-center gap-1">
            <Play className="w-3 h-3" />
            {stats.total_executions} runs
          </span>
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={loadSkills}
          >
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      )}

      {/* Skills List */}
      <ScrollArea style={{ maxHeight }}>
        {skills.length > 0 ? (
          <div className="space-y-2 pr-2">
            {skills.map((skill) => {
              const catInfo =
                CATEGORY_INFO[skill.category as SkillCategory] ||
                CATEGORY_INFO.custom;

              return (
                <div
                  key={skill.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border ${
                    skill.enabled ? "bg-card" : "bg-muted/50 opacity-60"
                  }`}
                >
                  {/* Icon */}
                  <div
                    className={`w-8 h-8 rounded-md flex items-center justify-center ${catInfo.color} text-white text-xs flex-shrink-0`}
                  >
                    {skill.name.charAt(0).toUpperCase()}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm truncate">
                        {skill.name}
                      </span>
                      <Badge
                        variant="outline"
                        className="text-[10px] px-1 py-0"
                      >
                        v{skill.version}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                      <span>{catInfo.label}</span>
                      {skill.execution_count > 0 && (
                        <>
                          <span>-</span>
                          <span className="flex items-center gap-0.5">
                            <Clock className="w-3 h-3" />
                            {skill.execution_count} runs
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {/* Toggle */}
                    <Switch
                      checked={skill.enabled}
                      onCheckedChange={(checked) =>
                        handleToggle(skill.id, checked)
                      }
                      className="scale-75"
                    />

                    {/* Execute */}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0"
                      onClick={() => handleExecute(skill.id)}
                      disabled={!skill.enabled || executing === skill.id}
                    >
                      {executing === skill.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Play className="w-3.5 h-3.5" />
                      )}
                    </Button>

                    {/* Uninstall */}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                      onClick={() => handleUninstall(skill.id, skill.name)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="py-8 text-center text-muted-foreground">
            <Package className="w-10 h-10 mx-auto mb-2 opacity-40" />
            <p className="text-sm">No skills installed yet</p>
            <p className="text-xs mt-1">
              Browse the marketplace to discover skills
            </p>
            {onBrowseMarketplace && (
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={onBrowseMarketplace}
              >
                Browse Marketplace
              </Button>
            )}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

export default InstalledSkillsPanel;

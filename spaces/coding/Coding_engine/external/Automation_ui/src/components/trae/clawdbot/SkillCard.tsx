/**
 * SkillCard - Compact skill display for marketplace grid
 *
 * Shows skill name, description, rating, install count,
 * and install/execute actions.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import {
  Download,
  Trash2,
  Play,
  Star,
  Users,
  Loader2,
  Globe,
  Monitor,
  Folder,
  Code,
  Database,
  Mail,
  Brain,
  Terminal,
  Zap,
  Puzzle,
  Camera,
} from "lucide-react";
import {
  ClawHubService,
  CATEGORY_INFO,
  type SkillSummary,
} from "@/services/clawhubService";

// Map icon names to Lucide components
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  globe: Globe,
  monitor: Monitor,
  folder: Folder,
  code: Code,
  database: Database,
  mail: Mail,
  brain: Brain,
  terminal: Terminal,
  zap: Zap,
  puzzle: Puzzle,
  camera: Camera,
  "git-branch": Code,
  home: Monitor,
  type: Code,
  "play-circle": Play,
};

interface SkillCardProps {
  skill: SkillSummary;
  onInstallChange?: () => void;
  onExecute?: (skillId: string) => void;
  compact?: boolean;
}

export function SkillCard({
  skill,
  onInstallChange,
  onExecute,
  compact = false,
}: SkillCardProps) {
  const [installing, setInstalling] = useState(false);
  const [uninstalling, setUninstalling] = useState(false);
  const [isInstalled, setIsInstalled] = useState(skill.installed);

  const categoryInfo = CATEGORY_INFO[skill.category] || CATEGORY_INFO.custom;
  const IconComponent = ICON_MAP[skill.icon || categoryInfo.icon] || Puzzle;

  const handleInstall = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setInstalling(true);
    try {
      const result = await ClawHubService.installSkill(skill.id);
      setIsInstalled(true);
      toast.success(`${skill.name} installed`);
      onInstallChange?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Installation failed");
    } finally {
      setInstalling(false);
    }
  };

  const handleUninstall = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setUninstalling(true);
    try {
      await ClawHubService.uninstallSkill(skill.id);
      setIsInstalled(false);
      toast.success(`${skill.name} removed`);
      onInstallChange?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Uninstall failed");
    } finally {
      setUninstalling(false);
    }
  };

  const handleExecute = (e: React.MouseEvent) => {
    e.stopPropagation();
    onExecute?.(skill.id);
  };

  // Star rating display
  const stars = Math.round(skill.rating * 2) / 2;
  const fullStars = Math.floor(stars);

  return (
    <Card
      className={`group hover:shadow-md transition-shadow ${compact ? "p-0" : ""}`}
    >
      <CardContent className={compact ? "p-3" : "p-4"}>
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div
            className={`flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${categoryInfo.color} text-white`}
          >
            <IconComponent className="w-5 h-5" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            {/* Header */}
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-semibold text-sm truncate">{skill.name}</h4>
              <Badge
                variant="outline"
                className="text-[10px] px-1 py-0 flex-shrink-0"
              >
                v{skill.version}
              </Badge>
            </div>

            {/* Description */}
            <p className="text-xs text-muted-foreground line-clamp-2 mb-2">
              {skill.description}
            </p>

            {/* Meta row */}
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {/* Rating */}
              <span className="flex items-center gap-0.5">
                <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                {skill.rating.toFixed(1)}
              </span>

              {/* Installs */}
              <span className="flex items-center gap-0.5">
                <Users className="w-3 h-3" />
                {skill.install_count >= 1000
                  ? `${(skill.install_count / 1000).toFixed(1)}k`
                  : skill.install_count}
              </span>

              {/* Author */}
              <span className="truncate">{skill.author}</span>
            </div>

            {/* Tags */}
            {!compact && skill.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {skill.tags.slice(0, 3).map((tag) => (
                  <Badge
                    key={tag}
                    variant="secondary"
                    className="text-[10px] px-1.5 py-0"
                  >
                    {tag}
                  </Badge>
                ))}
                {skill.tags.length > 3 && (
                  <span className="text-[10px] text-muted-foreground">
                    +{skill.tags.length - 3}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-1 flex-shrink-0">
            {isInstalled ? (
              <>
                <Button
                  size="sm"
                  variant="default"
                  className="h-7 text-xs px-2"
                  onClick={handleExecute}
                >
                  <Play className="w-3 h-3 mr-1" />
                  Run
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs px-2 text-destructive hover:text-destructive"
                  onClick={handleUninstall}
                  disabled={uninstalling}
                >
                  {uninstalling ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Trash2 className="w-3 h-3" />
                  )}
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs px-2"
                onClick={handleInstall}
                disabled={installing}
              >
                {installing ? (
                  <Loader2 className="w-3 h-3 animate-spin mr-1" />
                ) : (
                  <Download className="w-3 h-3 mr-1" />
                )}
                Install
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default SkillCard;

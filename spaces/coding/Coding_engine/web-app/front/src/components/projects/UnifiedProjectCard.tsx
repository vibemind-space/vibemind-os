// front/src/components/projects/UnifiedProjectCard.tsx
import { useNavigate } from 'react-router-dom';
import type { Project } from '@/services/api';
import type { EngineProject } from '@/services/engineApi';

type CardProject = {
  type: 'engine' | 'vibe';
  name: string;
  description: string;
  stats: { label: string; value: string | number }[];
  status: string;
  progressPct?: number;
  navigateTo: string;
};

function toCardProject(project: Project): CardProject {
  return {
    type: 'vibe',
    name: project.name,
    description: project.description || 'Vibe project',
    stats: [
      { label: 'Files', value: project.files?.length || 0 },
    ],
    status: project.status || 'active',
    navigateTo: `/editor/${project.id}`,
  };
}

function engineToCardProject(project: EngineProject): CardProject {
  // Clean up name: remove timestamps like _20260211_025459, replace separators
  const cleanName = project.name
    .replace(/_\d{8}_\d{6}$/, '')
    .replace(/[-_]/g, ' ');

  // Build description from available docs
  const docs: string[] = [];
  if (project.has_user_stories) docs.push('User Stories');
  if (project.has_api_docs) docs.push('API Docs');
  if (project.has_data_dictionary) docs.push('Data Dictionary');
  const description = docs.length > 0 ? docs.join(' · ') : 'Engine project';

  // Build stats from available data
  const stats: { label: string; value: string | number }[] = [];
  if (project.epic_count > 0) stats.push({ label: 'Epics', value: project.epic_count });
  if (project.story_count > 0) stats.push({ label: 'Stories', value: project.story_count });
  if (project.endpoint_count > 0) stats.push({ label: 'Endpoints', value: project.endpoint_count });
  if (stats.length === 0) stats.push({ label: 'Docs', value: docs.length });

  return {
    type: 'engine',
    name: cleanName,
    description,
    stats,
    status: 'ready',
    navigateTo: `/engine-editor/${encodeURIComponent(project.name)}`,
  };
}

interface UnifiedProjectCardProps {
  project?: Project;
  engineProject?: EngineProject;
}

export function UnifiedProjectCard({ project, engineProject }: UnifiedProjectCardProps) {
  const navigate = useNavigate();
  const card = project ? toCardProject(project) : engineProject ? engineToCardProject(engineProject) : null;
  if (!card) return null;

  return (
    <div
      onClick={() => navigate(card.navigateTo)}
      className="group bg-card rounded-2xl overflow-hidden border border-border/30 hover:border-primary/40 transition-all cursor-pointer hover:-translate-y-1 hover:shadow-xl"
    >
      <div className={`h-28 flex items-center justify-center relative ${
        card.type === 'engine'
          ? 'bg-gradient-to-br from-blue-950/50 to-background'
          : 'bg-gradient-to-br from-purple-950/50 to-background'
      }`}>
        <span className="text-4xl opacity-20">
          {card.type === 'engine' ? '\u26A1' : '\u2728'}
        </span>
        <span className={`absolute top-3 right-3 text-[10px] font-semibold px-2.5 py-1 rounded-full border ${
          card.type === 'engine'
            ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
            : 'bg-purple-500/10 text-purple-400 border-purple-500/30'
        }`}>
          {card.type === 'engine' ? 'Engine' : 'Vibe'}
        </span>
        <span className="absolute bottom-3 left-3 text-[10px] font-medium px-2 py-0.5 rounded-full glass text-muted-foreground capitalize">
          {card.status}
        </span>
      </div>
      {card.progressPct !== undefined && (
        <div className="h-0.5 bg-muted">
          <div className="h-full bg-gradient-to-r from-primary to-green-500 transition-all" style={{ width: `${card.progressPct}%` }} />
        </div>
      )}
      <div className="p-5">
        <h3 className="text-base font-bold capitalize group-hover:text-primary transition-colors line-clamp-1">
          {card.name}
        </h3>
        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{card.description}</p>
        <div className="flex gap-4 mt-3 text-[11px] text-muted-foreground">
          {card.stats.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="font-semibold text-foreground/70">{s.value}</span> {s.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export { toCardProject, engineToCardProject };

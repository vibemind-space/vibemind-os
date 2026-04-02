// front/src/components/projects/ProjectFilters.tsx
interface ProjectFiltersProps {
  active: string;
  onChange: (filter: string) => void;
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'engine', label: 'Engine' },
  { key: 'vibe', label: 'Vibe' },
  { key: 'running', label: 'Running' },
];

export function ProjectFilters({ active, onChange }: ProjectFiltersProps) {
  return (
    <div className="flex gap-2">
      {FILTERS.map((f) => (
        <button
          key={f.key}
          onClick={() => onChange(f.key)}
          className={`px-4 py-1.5 rounded-full text-xs font-medium border transition-all ${
            active === f.key
              ? 'bg-primary/10 border-primary/40 text-primary'
              : 'border-border/30 text-muted-foreground hover:text-foreground hover:border-border/60'
          }`}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}

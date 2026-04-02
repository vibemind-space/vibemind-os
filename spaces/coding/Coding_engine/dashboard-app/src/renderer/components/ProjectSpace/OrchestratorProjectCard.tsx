import { OrchestratorProject } from '../../stores/projectStore'
import {
  CheckCircle,
  XCircle,
  FileText,
  Calendar,
  Layers,
  CheckSquare,
  Square,
  Rocket
} from 'lucide-react'

interface OrchestratorProjectCardProps {
  project: OrchestratorProject
  isSelected: boolean
  onToggleSelect: () => void
  onGenerate: () => void
}

// Tech stack color mapping
const techColors: Record<string, { bg: string; text: string }> = {
  // Frontend
  'React': { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  'Vue.js': { bg: 'bg-green-500/20', text: 'text-green-400' },
  'Angular': { bg: 'bg-red-500/20', text: 'text-red-400' },
  'TypeScript': { bg: 'bg-blue-600/20', text: 'text-blue-300' },
  'Tailwind CSS': { bg: 'bg-cyan-500/20', text: 'text-cyan-400' },

  // Backend
  'FastAPI': { bg: 'bg-teal-500/20', text: 'text-teal-400' },
  'Python': { bg: 'bg-yellow-500/20', text: 'text-yellow-400' },
  'Python 3.11+': { bg: 'bg-yellow-500/20', text: 'text-yellow-400' },
  'Node.js': { bg: 'bg-green-600/20', text: 'text-green-300' },
  'Express': { bg: 'bg-gray-500/20', text: 'text-gray-300' },

  // Database
  'PostgreSQL': { bg: 'bg-blue-700/20', text: 'text-blue-300' },
  'SQLite': { bg: 'bg-blue-400/20', text: 'text-blue-300' },
  'SQLAlchemy': { bg: 'bg-orange-500/20', text: 'text-orange-400' },
  'SQLAlchemy 2.0': { bg: 'bg-orange-500/20', text: 'text-orange-400' },
  'MongoDB': { bg: 'bg-green-700/20', text: 'text-green-300' },
  'Prisma': { bg: 'bg-indigo-500/20', text: 'text-indigo-400' },

  // Tools
  'Docker': { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  'Alembic': { bg: 'bg-purple-500/20', text: 'text-purple-400' },
  'Pydantic v2': { bg: 'bg-pink-500/20', text: 'text-pink-400' },
  'JWT': { bg: 'bg-amber-500/20', text: 'text-amber-400' },
  'Redis': { bg: 'bg-red-600/20', text: 'text-red-400' },
  'GraphQL': { bg: 'bg-pink-600/20', text: 'text-pink-400' },

  // Default
  'default': { bg: 'bg-gray-500/20', text: 'text-gray-400' }
}

function getTechColor(tech: string): { bg: string; text: string } {
  return techColors[tech] || techColors['default']
}

export function OrchestratorProjectCard({
  project,
  isSelected,
  onToggleSelect,
  onGenerate
}: OrchestratorProjectCardProps) {
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    })
  }

  const { validation_summary } = project
  const hasValidation = validation_summary.total > 0
  const validationRate = hasValidation
    ? Math.round((validation_summary.passed / validation_summary.total) * 100)
    : 0

  return (
    <div
      className={`
        bg-engine-dark rounded-lg border overflow-hidden transition-all
        ${isSelected ? 'border-engine-primary ring-2 ring-engine-primary/30' : 'border-gray-700 hover:border-gray-600'}
      `}
    >
      {/* Header with checkbox */}
      <div className="p-4 border-b border-gray-700 flex items-start gap-3">
        <button
          onClick={onToggleSelect}
          className="mt-0.5 shrink-0 text-gray-400 hover:text-white transition"
        >
          {isSelected ? (
            <CheckSquare className="w-5 h-5 text-engine-primary" />
          ) : (
            <Square className="w-5 h-5" />
          )}
        </button>

        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-white truncate">{project.project_name}</h3>
          <div className="flex items-center gap-2 mt-1 text-sm text-gray-400">
            <Layers className="w-3.5 h-3.5" />
            <span>{project.template_name}</span>
            <span className="text-gray-600">|</span>
            <span className="px-1.5 py-0.5 bg-gray-700 rounded text-xs">
              {project.template_category}
            </span>
          </div>
        </div>
      </div>

      {/* Tech Stack Badges */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex flex-wrap gap-1.5">
          {project.tech_stack.map((tech) => {
            const { bg, text } = getTechColor(tech)
            return (
              <span
                key={tech}
                className={`px-2 py-0.5 text-xs font-medium rounded ${bg} ${text}`}
              >
                {tech}
              </span>
            )
          })}
        </div>
      </div>

      {/* Stats */}
      <div className="p-4 grid grid-cols-3 gap-4 text-sm">
        {/* Requirements count */}
        <div className="flex items-center gap-2 text-gray-400">
          <FileText className="w-4 h-4" />
          <span>{project.requirements_count} reqs</span>
        </div>

        {/* Validation summary */}
        <div className="flex items-center gap-2">
          {hasValidation ? (
            validationRate === 100 ? (
              <CheckCircle className="w-4 h-4 text-green-400" />
            ) : (
              <XCircle className="w-4 h-4 text-yellow-400" />
            )
          ) : (
            <span className="w-4 h-4" />
          )}
          <span className={hasValidation ? (validationRate === 100 ? 'text-green-400' : 'text-yellow-400') : 'text-gray-500'}>
            {hasValidation ? `${validationRate}% valid` : 'Not validated'}
          </span>
        </div>

        {/* Date */}
        <div className="flex items-center gap-2 text-gray-400 justify-end">
          <Calendar className="w-4 h-4" />
          <span>{formatDate(project.created_at)}</span>
        </div>
      </div>

      {/* Source file */}
      {project.source_file && (
        <div className="px-4 pb-4">
          <span className="text-xs text-gray-500">
            Source: {project.source_file}
          </span>
        </div>
      )}

      {/* Generate button (only if selected) */}
      {isSelected && (
        <div className="p-4 border-t border-gray-700">
          <button
            onClick={onGenerate}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition"
          >
            <Rocket className="w-4 h-4" />
            Generate Code
          </button>
        </div>
      )}
    </div>
  )
}

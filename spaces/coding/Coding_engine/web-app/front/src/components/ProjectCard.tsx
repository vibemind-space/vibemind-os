import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, MoreVertical, Trash2, Sparkles, Star } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { projectApi } from '@/services/api';

interface ProjectCardProps {
  project: {
    id: number;
    name: string;
    description?: string;
    status?: string;
    created_at: string;
    thumbnail?: string;
    is_favorite?: boolean;
  };
  index: number;
  onDelete: (id: number, name: string, e: React.MouseEvent) => void;
  onToggleFavorite: (id: number, e: React.MouseEvent) => void;
}

export const ProjectCard = ({ project, index, onDelete, onToggleFavorite }: ProjectCardProps) => {
  const [thumbnail, setThumbnail] = useState<string | null>(project.thumbnail || null);
  const [isLoading, setIsLoading] = useState(!project.thumbnail);
  const [isVisible, setIsVisible] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Intersection Observer to detect when card is visible
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
            observer.disconnect();
          }
        });
      },
      {
        rootMargin: '50px', // Start loading 50px before entering viewport
      }
    );

    if (cardRef.current) {
      observer.observe(cardRef.current);
    }

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    // Load thumbnail when card becomes visible
    if (isVisible && !thumbnail && isLoading) {
      const loadThumbnail = async () => {
        try {
          const data = await projectApi.getThumbnail(project.id);
          if (data.thumbnail) {
            setThumbnail(data.thumbnail);
          }
        } catch (error) {
          console.error('Failed to load thumbnail:', error);
        } finally {
          setIsLoading(false);
        }
      };

      loadThumbnail();
    }
  }, [isVisible, thumbnail, isLoading, project.id]);

  return (
    <div
      ref={cardRef}
      className="group relative h-full"
      style={{
        animation: `fadeInUp 0.5s ease-out ${index * 0.1}s both`
      }}
    >
      <Link to={`/editor/${project.id}`} className="block h-full">
        <div className="glass rounded-2xl overflow-hidden hover:border-primary/50 transition-all duration-300 hover:shadow-xl hover:-translate-y-1">
          {/* Thumbnail */}
          <div className="relative h-48 bg-gradient-to-br from-primary/20 to-purple-500/20 overflow-hidden">
            {isLoading ? (
              <div className="w-full h-full flex items-center justify-center">
                <div className="w-16 h-16 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
              </div>
            ) : thumbnail ? (
              <img
                src={thumbnail}
                alt={project.name}
                loading="lazy"
                decoding="async"
                className="w-full h-full object-cover object-top transition-transform duration-300 group-hover:scale-110"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Sparkles className="w-16 h-16 text-primary/40 animate-pulse" />
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

            {/* Status Badge */}
            <div className="absolute top-3 right-3">
              <span className="text-xs px-3 py-1.5 rounded-full glass text-foreground capitalize font-medium">
                {project.status}
              </span>
            </div>
          </div>

          {/* Project Details */}
          <div className="p-6">
            <h3 className="text-xl font-bold mb-2 group-hover:text-primary transition-colors line-clamp-1">
              {project.name}
            </h3>
            <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
              {project.description || 'No description available'}
            </p>
            <div className="flex items-center text-xs text-muted-foreground">
              <Calendar className="w-3.5 h-3.5 mr-1.5" />
              {new Date(project.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
              })}
            </div>
          </div>
        </div>
      </Link>

      {/* Actions Menu */}
      <div className="absolute top-52 right-3 z-10">
        <DropdownMenu>
          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
            <button className="p-2 glass hover:bg-background/80 rounded-lg transition-all opacity-0 group-hover:opacity-100">
              <MoreVertical className="w-4 h-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={(e) => onToggleFavorite(project.id, e)}
            >
              <Star className={`w-4 h-4 mr-2 ${project.is_favorite ? 'fill-yellow-400 text-yellow-400' : ''}`} />
              {project.is_favorite ? 'Remove from Favorites' : 'Add to Favorites'}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={(e) => onDelete(project.id, project.name, e)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete Project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
};

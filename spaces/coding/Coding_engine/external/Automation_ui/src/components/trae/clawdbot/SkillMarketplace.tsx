/**
 * SkillMarketplace - Browse and search ClawHub.ai skills
 *
 * Full marketplace view with search, category filters,
 * sorting, and skill installation.
 */

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Search,
  TrendingUp,
  RefreshCw,
  Loader2,
  Package,
  X,
} from "lucide-react";
import {
  ClawHubService,
  CATEGORY_INFO,
  type SkillSummary,
  type SkillCategory,
  type CategoryInfo,
} from "@/services/clawhubService";
import { SkillCard } from "./SkillCard";

interface SkillMarketplaceProps {
  onExecuteSkill?: (skillId: string) => void;
  maxHeight?: string;
}

export function SkillMarketplace({
  onExecuteSkill,
  maxHeight = "500px",
}: SkillMarketplaceProps) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("relevance");
  const [total, setTotal] = useState(0);
  const [view, setView] = useState<"search" | "trending">("trending");

  // Load categories on mount
  useEffect(() => {
    ClawHubService.getCategories()
      .then(setCategories)
      .catch((err) => console.error("Failed to load categories:", err));
  }, []);

  // Load trending on mount
  useEffect(() => {
    loadTrending();
  }, []);

  const loadTrending = async () => {
    setLoading(true);
    try {
      const trending = await ClawHubService.getTrending(20);
      setSkills(trending);
      setTotal(trending.length);
      setView("trending");
    } catch (err) {
      toast.error("Failed to load trending skills");
    } finally {
      setLoading(false);
    }
  };

  const searchSkills = useCallback(async () => {
    setLoading(true);
    try {
      const result = await ClawHubService.searchSkills(searchQuery, {
        category:
          selectedCategory !== "all"
            ? (selectedCategory as SkillCategory)
            : undefined,
        sort_by: sortBy as "relevance" | "rating" | "installs" | "newest",
        limit: 20,
      });
      setSkills(result.skills);
      setTotal(result.total);
      setView("search");
    } catch (err) {
      toast.error("Search failed");
    } finally {
      setLoading(false);
    }
  }, [searchQuery, selectedCategory, sortBy]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    searchSkills();
  };

  const handleCategoryChange = (value: string) => {
    setSelectedCategory(value);
    // Trigger search with new category
    setTimeout(() => searchSkills(), 0);
  };

  const clearSearch = () => {
    setSearchQuery("");
    setSelectedCategory("all");
    loadTrending();
  };

  return (
    <div className="space-y-3">
      {/* Search Bar */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search skills... (e.g. 'browser automation')"
            className="pl-9 h-9"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={clearSearch}
              className="absolute right-2.5 top-2.5"
            >
              <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
            </button>
          )}
        </div>
        <Button type="submit" size="sm" className="h-9" disabled={loading}>
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
        </Button>
      </form>

      {/* Filters Row */}
      <div className="flex items-center gap-2">
        {/* Category Filter */}
        <Select value={selectedCategory} onValueChange={handleCategoryChange}>
          <SelectTrigger className="h-8 w-[150px] text-xs">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            {categories.map((cat) => {
              const info = CATEGORY_INFO[cat.category as SkillCategory];
              return (
                <SelectItem key={cat.category} value={cat.category}>
                  {info?.label || cat.category} ({cat.count})
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>

        {/* Sort */}
        <Select value={sortBy} onValueChange={setSortBy}>
          <SelectTrigger className="h-8 w-[130px] text-xs">
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="relevance">Relevance</SelectItem>
            <SelectItem value="rating">Rating</SelectItem>
            <SelectItem value="installs">Most Installed</SelectItem>
            <SelectItem value="newest">Newest</SelectItem>
          </SelectContent>
        </Select>

        <div className="flex-1" />

        {/* Trending Button */}
        <Button
          variant={view === "trending" ? "secondary" : "ghost"}
          size="sm"
          className="h-8 text-xs"
          onClick={loadTrending}
        >
          <TrendingUp className="w-3 h-3 mr-1" />
          Trending
        </Button>

        {/* Refresh */}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={searchSkills}
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {/* Results Header */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {view === "trending" ? (
            <span className="flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              Trending Skills
            </span>
          ) : (
            `${total} results for "${searchQuery}"`
          )}
        </span>
        <span className="flex items-center gap-1">
          <Package className="w-3 h-3" />
          ClawHub.ai
        </span>
      </div>

      {/* Skills Grid */}
      <ScrollArea style={{ maxHeight }}>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : skills.length > 0 ? (
          <div className="space-y-2 pr-2">
            {skills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                onInstallChange={searchSkills}
                onExecute={onExecuteSkill}
              />
            ))}
          </div>
        ) : (
          <div className="py-12 text-center text-muted-foreground">
            <Package className="w-10 h-10 mx-auto mb-2 opacity-40" />
            <p className="text-sm">No skills found</p>
            <p className="text-xs mt-1">Try a different search query</p>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

export default SkillMarketplace;

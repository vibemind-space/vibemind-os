import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, ArrowUp, Loader2, Image as ImageIcon, FileText, X, Sparkles } from "lucide-react";
import { useCreateProject } from "@/hooks/useProjects";
import { useProjects } from "@/hooks/useProjects";
import { useToast } from "@/hooks/use-toast";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import FeaturesSection from "@/components/FeaturesSection";
import HowItWorksSection from "@/components/HowItWorksSection";
import DocsSection from "@/components/DocsSection";
import { ProjectCard } from "@/components/ProjectCard";
import { API_URL } from "@/services/api";

interface FileAttachment {
  id: string;
  name: string;
  type: 'image' | 'pdf';
  mime_type: string;
  size: number;
  url?: string;
  data?: string;
}

const Index = () => {
  const [message, setMessage] = useState("");
  const [showGallery, setShowGallery] = useState(false);
  const [displayedProjects, setDisplayedProjects] = useState(16);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<FileAttachment[]>([]);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const galleryRef = useRef<HTMLDivElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();
  const createProject = useCreateProject();
  const { data: projects } = useProjects();

  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY;
      if (scrollPosition > 300 && !showGallery) {
        setShowGallery(true);
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [showGallery]);

  // Close attach menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (showAttachMenu) {
        const target = event.target as HTMLElement;
        if (!target.closest('.attach-menu-container')) {
          setShowAttachMenu(false);
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAttachMenu]);

  // Handle image selection
  const handleImageSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setIsUploadingFile(true);

    try {
      const newAttachments: FileAttachment[] = [];

      for (const file of Array.from(files)) {
        if (!file.type.startsWith('image/')) {
          toast({
            title: "Invalid file type",
            description: `${file.name} is not an image`,
            variant: "destructive"
          });
          continue;
        }

        if (file.size > 10 * 1024 * 1024) {
          toast({
            title: "File too large",
            description: `${file.name} exceeds 10MB`,
            variant: "destructive"
          });
          continue;
        }

        const reader = new FileReader();
        const base64Data = await new Promise<string>((resolve, reject) => {
          reader.onload = () => {
            const result = reader.result as string;
            resolve(result.split(',')[1]);
          };
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });

        const previewUrl = URL.createObjectURL(file);

        newAttachments.push({
          id: `${Date.now()}-${file.name}`,
          name: file.name,
          type: 'image',
          mime_type: file.type,
          size: file.size,
          url: previewUrl,
          data: base64Data
        });
      }

      setAttachedFiles(prev => [...prev, ...newAttachments]);
      setShowAttachMenu(false);
      toast({
        title: "Images attached",
        description: `${newAttachments.length} image(s) ready`
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to process images",
        variant: "destructive"
      });
    } finally {
      setIsUploadingFile(false);
      if (imageInputRef.current) {
        imageInputRef.current.value = '';
      }
    }
  };

  // Handle PDF selection
  const handlePdfSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setIsUploadingFile(true);

    try {
      const newAttachments: FileAttachment[] = [];

      for (const file of Array.from(files)) {
        if (file.type !== 'application/pdf') {
          toast({
            title: "Invalid file type",
            description: `${file.name} is not a PDF`,
            variant: "destructive"
          });
          continue;
        }

        if (file.size > 20 * 1024 * 1024) {
          toast({
            title: "File too large",
            description: `${file.name} exceeds 20MB`,
            variant: "destructive"
          });
          continue;
        }

        const reader = new FileReader();
        const base64Data = await new Promise<string>((resolve, reject) => {
          reader.onload = () => {
            const result = reader.result as string;
            resolve(result.split(',')[1]);
          };
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });

        newAttachments.push({
          id: `${Date.now()}-${file.name}`,
          name: file.name,
          type: 'pdf',
          mime_type: 'application/pdf',
          size: file.size,
          data: base64Data
        });
      }

      setAttachedFiles(prev => [...prev, ...newAttachments]);
      setShowAttachMenu(false);
      toast({
        title: "PDFs attached",
        description: `${newAttachments.length} PDF(s) ready`
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to process PDFs",
        variant: "destructive"
      });
    } finally {
      setIsUploadingFile(false);
      if (pdfInputRef.current) {
        pdfInputRef.current.value = '';
      }
    }
  };

  // Remove attachment
  const removeAttachment = (id: string) => {
    setAttachedFiles(prev => {
      const file = prev.find(f => f.id === id);
      if (file?.url) {
        URL.revokeObjectURL(file.url);
      }
      return prev.filter(f => f.id !== id);
    });
  };

  const handleSubmit = async () => {
    if (!message.trim() && attachedFiles.length === 0) {
      toast({
        title: "Empty message",
        description: "Please describe what you want to build or attach files",
        variant: "destructive",
      });
      return;
    }

    if (isSubmitting) {
      return;
    }

    setIsSubmitting(true);

    try {
      // Auto-enhance message if images are attached
      let enhancedMessage = message;
      const hasImages = attachedFiles.some(f => f.type === 'image');
      if (hasImages && !message.toLowerCase().includes('ui') && !message.toLowerCase().includes('design')) {
        enhancedMessage = `${message}\n\n[Note: The attached image(s) show a UI/UX design that should be converted to React code with Tailwind CSS.]`;
      }

      // Call the new endpoint that uses AI to generate project metadata
      const response = await fetch(`${API_URL}/projects/from-message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: enhancedMessage.substring(0, 1000),
          attachments: attachedFiles.length > 0 ? attachedFiles.map(file => ({
            type: file.type,
            mime_type: file.mime_type,
            data: file.data,
            name: file.name
          })) : undefined,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create project');
      }

      const data = await response.json();
      const project = data.project;
      const initialMessage = data.initial_message;
      const responseAttachments = data.attachments;

      toast({
        title: "Project created!",
        description: "Redirecting to editor...",
      });

      // Clean up attached file URLs (but keep data for editor)
      attachedFiles.forEach(file => {
        if (file.url) {
          URL.revokeObjectURL(file.url);
        }
      });

      // Navigate to editor with the initial message and attachments in state
      setTimeout(() => {
        navigate(`/editor/${project.id}`, {
          state: {
            initialMessage,
            attachments: responseAttachments
          }
        });

        // Clear state after navigation
        setAttachedFiles([]);
        setMessage('');
      }, 500);
    } catch (error) {
      toast({
        title: "Error creating project",
        description: "Please try again",
        variant: "destructive",
      });
      setIsSubmitting(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const loadMoreProjects = () => {
    setDisplayedProjects(prev => prev + 16);
  };

  return (
    <main className="min-h-screen bg-background">
      <Navbar />

      {/* Hero Section with Input */}
      <section className="relative min-h-screen flex items-center justify-center pt-20 overflow-hidden">
        {/* Background Effects */}
        <div className="absolute inset-0 bg-gradient-subtle" />
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-3xl animate-pulse-glow" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-accent/15 rounded-full blur-3xl animate-pulse-glow delay-500" />

        {/* Grid Pattern */}
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: `linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)`,
            backgroundSize: '60px 60px',
          }}
        />

        <div className="container mx-auto px-6 relative z-10">
          <div className="max-w-4xl mx-auto text-center">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8 animate-fade-in">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-sm text-muted-foreground">Powered by AI</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl md:text-5xl font-extrabold leading-tight mb-6 animate-fade-in-up">
              What can I{" "}
              <span className="text-gradient">build</span>{" "}
              for you?
            </h1>

            {/* Subheadline */}
            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 animate-fade-in-up delay-200">
              Describe what you want to build, and watch AI transform your ideas into
              production-ready applications in minutes.
            </p>

            {/* Input Box */}
            <div className="w-full max-w-5xl mx-auto mb-8 animate-fade-in-up delay-300">
              {/* File attachments preview */}
              {attachedFiles.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-2 justify-center">
                  {attachedFiles.map(file => (
                    <div
                      key={file.id}
                      className="relative group bg-background/80 border border-border rounded-lg p-2 flex items-center gap-2 max-w-xs"
                    >
                      {file.type === 'image' && file.url ? (
                        <img
                          src={file.url}
                          alt={file.name}
                          className="w-12 h-12 object-cover rounded"
                        />
                      ) : (
                        <div className="w-12 h-12 flex items-center justify-center bg-muted/50 rounded">
                          <FileText className="w-6 h-6 text-muted-foreground" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate">{file.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {(file.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                      <button
                        onClick={() => removeAttachment(file.id)}
                        className="absolute -top-1 -right-1 w-5 h-5 bg-destructive text-destructive-foreground rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Remove"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="glass rounded-3xl glow-accent flex items-start gap-4 p-6 hover:border-primary/50 transition-all">
                <div className="relative attach-menu-container">
                  <button
                    className="w-11 h-11 rounded-full border border-border bg-background hover:bg-muted flex items-center justify-center transition-colors shrink-0 mt-1"
                    onClick={() => setShowAttachMenu(!showAttachMenu)}
                    disabled={isSubmitting || isUploadingFile}
                  >
                    <Plus className="w-6 h-6 text-muted-foreground" />
                  </button>

                  {/* Attach menu */}
                  {showAttachMenu && (
                    <div className="absolute top-full left-0 mt-2 bg-background border border-border rounded-lg shadow-lg p-2 z-50 min-w-[160px]">
                      <button
                        onClick={() => imageInputRef.current?.click()}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted rounded text-sm transition-colors"
                      >
                        <ImageIcon className="w-4 h-4" />
                        <span>Add images</span>
                      </button>
                      <button
                        onClick={() => pdfInputRef.current?.click()}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted rounded text-sm transition-colors"
                      >
                        <FileText className="w-4 h-4" />
                        <span>Add PDF</span>
                      </button>
                    </div>
                  )}

                  {/* Hidden file inputs */}
                  <input
                    ref={imageInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
                    multiple
                    onChange={handleImageSelect}
                    className="hidden"
                  />
                  <input
                    ref={pdfInputRef}
                    type="file"
                    accept="application/pdf"
                    multiple
                    onChange={handlePdfSelect}
                    className="hidden"
                  />
                </div>

                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={attachedFiles.length > 0 ? "Describe what you want to build with these files..." : "Describe your project or ask anything..."}
                  rows={4}
                  disabled={isSubmitting}
                  className="flex-1 bg-transparent border-none outline-none text-lg text-foreground placeholder:text-muted-foreground resize-none disabled:opacity-50 disabled:cursor-not-allowed"
                />

                <div className="flex flex-col items-center gap-3 shrink-0 mt-1">
                  <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse" />

                  <button
                    onClick={handleSubmit}
                    disabled={(!message.trim() && attachedFiles.length === 0) || isSubmitting}
                    className="w-11 h-11 rounded-full bg-gradient-primary hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 flex items-center justify-center transition-all glow-primary"
                  >
                    {isSubmitting ? (
                      <Loader2 className="w-6 h-6 text-primary-foreground animate-spin" />
                    ) : (
                      <ArrowUp className="w-6 h-6 text-primary-foreground" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Social Proof */}
            <div className="mt-12 animate-fade-in delay-500">
              <p className="text-sm text-muted-foreground mb-4">
                Join thousands of developers building faster with AI
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Project Gallery */}
      {showGallery && (
        <section ref={galleryRef} className="py-20 px-4 bg-muted/20">
          <div className="max-w-7xl mx-auto">
            <h2 className="text-3xl font-semibold text-center mb-12">
              Recent Projects
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
              {projects?.slice(0, displayedProjects).map((project, index) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  index={index}
                  onDelete={() => {}} // No delete in gallery view
                />
              ))}
            </div>

            {projects && projects.length > displayedProjects && (
              <div className="flex justify-center">
                <button
                  onClick={loadMoreProjects}
                  className="px-8 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
                >
                  Load More
                </button>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Features Section */}
      <FeaturesSection />

      {/* How It Works Section */}
      <HowItWorksSection />

      {/* Docs Section */}
      <DocsSection />

      <Footer />
    </main>
  );
};

export default Index;

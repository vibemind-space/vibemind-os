import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Index from "./pages/Index";
import Projects from "./pages/Projects";
import Editor from "./pages/Editor";
import NotFound from "./pages/NotFound";
import Documentation from "./pages/Documentation";
import Marketplace from "./pages/Marketplace";
import EngineEditor from "./pages/EngineEditor";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/editor" element={<Navigate to="/projects" replace />} />
          <Route path="/editor/:projectId" element={<Editor />} />
          <Route path="/docs" element={<Documentation />} />
          <Route path="/marketplace" element={<Marketplace />} />
          <Route path="/engine-editor/:projectName" element={<EngineEditor />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;

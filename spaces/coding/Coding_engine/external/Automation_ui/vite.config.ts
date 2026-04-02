import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// Vite configuration for the frontend development server
// Note: Keep config minimal and consistent with other agents' standards
export default defineConfig(() => ({
  plugins: [react(), componentTagger()],
  server: {
    host: "0.0.0.0",
    port: 3003,
    strictPort: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"), // Support '@/xyz' imports
    },
  },
}));


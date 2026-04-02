import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // In Docker: VITE_PROXY_TARGET=http://api:8000, locally: http://localhost:8000
  const apiTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000';

  return {
  server: {
    host: "::",
    port: 5173,
    headers: {
      // COEP/COOP removed — blocks cross-origin VNC iframe and health checks
    },
    proxy: {
      '/api/v1': { target: apiTarget, changeOrigin: true, ws: true },
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}});

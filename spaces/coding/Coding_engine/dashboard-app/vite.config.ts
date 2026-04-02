import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * Standalone Vite config for web mode (without Electron)
 * Run with: npm run dev:web
 */
export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname, 'src/renderer'),
  publicDir: resolve(__dirname, 'src/renderer/public'),
  build: {
    outDir: resolve(__dirname, 'dist-web'),
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer'),
    },
  },
  server: {
    port: 5180,
    host: true,
    open: true,
    cors: true,
    allowedHosts: ['host.docker.internal', 'localhost'],
    proxy: {
      // Proxy API requests to FastAPI backend (Coding Engine)
      // Use /api/v1 to avoid catching source file imports like /api/webAPI.ts
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,  // Enable WebSocket proxying
      },
      // Proxy orchestrator requests to req-orchestrator container
      '/orchestrator': {
        target: 'http://localhost:8087',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/orchestrator/, '/api/v1'),
      },
    },
  },
  define: {
    // Mark as web mode
    'import.meta.env.ELECTRON': 'false',
  },
})

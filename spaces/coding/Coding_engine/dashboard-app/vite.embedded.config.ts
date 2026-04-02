import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * Vite config for embedded mode (VibeMind BrowserView)
 *
 * This build is optimized for running inside VibeMind's BrowserView:
 * - Uses relative paths for file:// protocol loading
 * - Outputs to dist-embedded/
 * - No dev server (loaded directly from filesystem)
 *
 * Run with: npm run build:embedded
 */
export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname, 'src/renderer'),
  publicDir: resolve(__dirname, 'src/renderer/public'),

  // Use relative paths for file:// protocol
  base: './',

  build: {
    outDir: resolve(__dirname, 'dist-embedded'),
    emptyOutDir: true,

    // Optimize for embedded use (esbuild is faster and built-in)
    minify: 'esbuild',
    sourcemap: false,

    rollupOptions: {
      output: {
        // Keep asset names simple for easier debugging
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',

        // Manual chunks for better caching
        manualChunks: {
          vendor: ['react', 'react-dom'],
          zustand: ['zustand'],
        },
      },
    },

    // Target modern browsers (Electron Chromium)
    target: 'chrome110',
  },

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer'),
    },
  },

  define: {
    // Mark as embedded mode
    'import.meta.env.ELECTRON': 'true',
    'import.meta.env.EMBEDDED': 'true',
  },
})

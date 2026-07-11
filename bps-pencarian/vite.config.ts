/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from "path"

// https://vite.dev/config/
export default defineConfig({
  // Inject a build-time stamp so the entry/chunk content-hashes change on
  // every build. Without this, edits to a lazy chunk (e.g. ChartModal) leave
  // the entry hash stable, and a front CDN (Cloudflare) keeps serving the
  // cached old chunk. A new hash => new URL => CDN cache miss => fresh build.
  define: {
    __BUILD_STAMP__: JSON.stringify(new Date().toISOString()),
  },
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      '/pencarian/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
  },
})

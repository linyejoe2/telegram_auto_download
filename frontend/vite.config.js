import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Built into ../library/static, which the Python server (library/server.py) serves.
// `npm run dev` proxies the API to a running app on port 8765.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: '../library/static', emptyOutDir: true },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/media': 'http://127.0.0.1:8765',
    },
  },
})

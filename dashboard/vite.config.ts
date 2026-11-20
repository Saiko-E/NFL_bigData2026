import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Relative assets keep static builds portable; API calls proxy to the local service in development.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})

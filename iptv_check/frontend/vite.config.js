import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8900',
      '/ws': { target: 'ws://localhost:8900', ws: true },
      '/proxy': 'http://localhost:8900',
      '/player': 'http://localhost:8900',
      '/hls-static': 'http://localhost:8900',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})

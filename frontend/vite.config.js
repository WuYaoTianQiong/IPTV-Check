import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:9528',
      '/ws': { target: 'ws://localhost:9528', ws: true },
      '/proxy': 'http://localhost:9528',
      '/player': 'http://localhost:9528',
      '/hls-static': 'http://localhost:9528',
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../backend/iptv_check/static'),
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      },
    },
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  test: {
    environment: 'happy-dom',
    globals: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:9529',
      '/ws': { target: 'ws://localhost:9529', ws: true },
      '/proxy': 'http://localhost:9529',
      '/player': 'http://localhost:9529',
      '/hls-static': 'http://localhost:9529',
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

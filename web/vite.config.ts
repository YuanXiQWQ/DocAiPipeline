import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // SSE 响应禁止缓冲，确保流式推送
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache';
              proxyRes.headers['x-accel-buffering'] = 'no';
            }
          });
        },
      },
      '/health': 'http://127.0.0.1:8000',
      '/process': 'http://127.0.0.1:8000',
      '/download': 'http://127.0.0.1:8000',
    },
  },
})

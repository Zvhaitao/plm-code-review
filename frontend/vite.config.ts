import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时把 /api 与 /webhooks 代理到后端
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/webhooks': 'http://localhost:8000',
    },
  },
})

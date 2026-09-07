import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
        '/health': { target, changeOrigin: true },
        '/docs': { target, changeOrigin: true },
        '/openapi.json': { target, changeOrigin: true },
      },
    },
  }
})


import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const envDir = resolve(__dirname, '..')
const env = loadEnv(process.env.NODE_ENV || 'development', envDir, '')
const frontendPort = Number(env.FRONTEND_PORT || 3000)
const backendPort = env.BACKEND_PORT || '8000'
const backendTarget = `http://127.0.0.1:${backendPort}`

export default defineConfig({
  envDir,
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler', // 使用现代 Sass API
        silenceDeprecations: ['legacy-js-api'], // 静默旧警告
      }
    }
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'es2022'
    },
    force: true,
    exclude: ['tree-sitter'],
  },
  build: {
    target: 'es2022',
  },
  server: {
    port: frontendPort,
    host: '0.0.0.0',
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    proxy: {
      '^/api/': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      },
      '^/media/': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  assetsInclude: ['**/*.wasm'],
})

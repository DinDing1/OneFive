import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'

// 从项目根目录的 VERSION 文件读取版本号
const versionFile = path.resolve(__dirname, '../VERSION')
const appVersion = fs.existsSync(versionFile)
  ? fs.readFileSync(versionFile, 'utf-8').trim()
  : '0.0.0'

export default defineConfig({
  plugins: [vue()],
  base: '/app/onefive/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  define: {
    __APP_VERSION__: JSON.stringify(appVersion)
  },
  server: {
    port: 5173,
    proxy: {
      '/app/onefive/api': {
        target: 'http://localhost:11580',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/app\/onefive/, '')
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets'
  }
})

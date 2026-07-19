import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'

// 从项目根目录的 VERSION 文件读取版本号
const versionFile = path.resolve(__dirname, '../VERSION')
const appVersion = fs.existsSync(versionFile)
  ? fs.readFileSync(versionFile, 'utf-8').trim()
  : '0.0.0'

/**
 * 开发态路径纠正：
 * 1) / -> /app/onefive/
 * 2) /app/onefive（无尾斜杠）-> /app/onefive/
 *
 * Vite base 为 /app/onefive/ 时，访问无尾斜杠地址会导致
 * 相对资源解析到 /app/*，页面空白/打不开。
 */
function redirectToBase() {
  const base = '/app/onefive/'
  const baseNoSlash = '/app/onefive'
  return {
    name: 'redirect-to-base',
    configureServer(server: any) {
      server.middlewares.use((req: any, res: any, next: any) => {
        const raw = req.url || '/'
        const qIndex = raw.indexOf('?')
        const pathOnly = qIndex >= 0 ? raw.slice(0, qIndex) : raw
        const query = qIndex >= 0 ? raw.slice(qIndex) : '' // includes leading ?

        const sendRedirect = (locationPath: string) => {
          res.statusCode = 302
          res.setHeader('Location', locationPath + query)
          res.end()
        }

        if (pathOnly === '/' || pathOnly === '' || pathOnly === '/index.html') {
          sendRedirect(base)
          return
        }

        // 关键修复：/app/onefive -> /app/onefive/
        if (pathOnly === baseNoSlash) {
          sendRedirect(base)
          return
        }

        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), redirectToBase()],
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
    // 同时监听 IPv4/IPv6，避免只有 [::1] 导致 127.0.0.1 打不开
    host: true,
    port: 5173,
    strictPort: true,
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

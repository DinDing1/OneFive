import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'

/**
 * 读取 VERSION 文件，返回去空白后的版本号字符串。
 *
 * 为什么不直接用 readFileSync(file, 'utf-8')：
 * Node 的 'utf-8' 不会识别 UTF-16 的 BOM，会把 UTF-16 字节当作 UTF-8
 * 硬解成乱码（如 "��1\0.\0..."），再经 vite define 注入前端，版本号就花了。
 * 这里按 BOM 判断真实编码后正确解码，兼容 UTF-8 / UTF-8 BOM / UTF-16 LE/BE。
 */
function readVersionFile(filePath: string): string {
  if (!fs.existsSync(filePath)) return '0.0.0'
  const buf = fs.readFileSync(filePath)
  if (buf.length === 0) return '0.0.0'

  // 按 BOM 判断编码：UTF-8(EF BB BF) / UTF-16 LE(FF FE) / UTF-16 BE(FE FF)
  if (buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf) {
    return buf.subarray(3).toString('utf-8').trim()   // 剥离 UTF-8 BOM
  }
  if (buf[0] === 0xff && buf[1] === 0xfe) {
    return buf.subarray(2).toString('utf16le').trim() // 剥离 UTF-16 LE BOM
  }
  if (buf[0] === 0xfe && buf[1] === 0xff) {
    // Node 不直接支持 utf16be，交换相邻字节后按 LE 解码
    const swapped = Buffer.alloc(buf.length - 2)
    for (let i = 2; i < buf.length; i += 2) {
      swapped[i - 2] = buf[i + 1]
      swapped[i - 1] = buf[i]
    }
    return swapped.toString('utf16le').trim()
  }
  return buf.toString('utf-8').trim()                 // 无 BOM，按 UTF-8
}

// 从项目根目录的 VERSION 文件读取版本号
const versionFile = path.resolve(__dirname, '../VERSION')
const appVersion = readVersionFile(versionFile)

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

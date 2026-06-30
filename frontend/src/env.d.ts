/// <reference types="vite/client" />

// vite.config.ts define 注入的全局变量
declare const __APP_VERSION__: string

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

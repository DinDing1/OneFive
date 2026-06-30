<template>
  <Teleport to="body">
    <Transition name="toast">
      <div v-if="visible" class="toast glass-solid" :class="type">
        <svg v-if="type === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
        <svg v-else-if="type === 'error'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span>{{ message }}</span>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const visible = ref(false)
const message = ref('')
const type = ref<'success' | 'error' | 'info'>('info')

let timer: number | null = null

function show(msg: string, msgType: 'success' | 'error' | 'info' = 'info', duration = 3000) {
  if (timer) clearTimeout(timer)
  message.value = msg
  type.value = msgType
  visible.value = true
  timer = window.setTimeout(() => {
    visible.value = false
  }, duration)
}

defineExpose({ show })
</script>

<style scoped>
/* Toast：由 glass-solid 提供背景/模糊/边框/阴影 */
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  color: var(--text-inverse);  /* 暗底亮字，保持高对比 */
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  z-index: 9999;
  max-width: 90%;
}

.toast svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* 图标颜色 token 化 */
.toast.success svg { color: var(--success); }
.toast.error svg { color: var(--danger); }
.toast.info svg { color: var(--accent); }

/* 进出动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}
</style>

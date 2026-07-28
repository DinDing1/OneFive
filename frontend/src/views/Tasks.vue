<template>
  <div class="tasks-page">
    <div v-if="errorMsg" class="toast danger">{{ errorMsg }}</div>
    <div v-if="infoMsg" class="toast info">{{ infoMsg }}</div>
    <div v-if="!loading && tasks.length && !schedulerReady" class="toast warn">
      调度器未就绪（可能未安装 APScheduler）。配置仍可保存，重启后生效。
    </div>

    <!-- 加载 / 空 -->
    <section v-if="loading && !tasks.length" class="empty glass-card">
      <div class="orbit"><span></span><span></span><span></span></div>
      <h2>加载任务</h2>
      <p>正在读取定时任务配置…</p>
    </section>

    <section v-else-if="!loading && !tasks.length" class="empty glass-card">
      <div class="empty-ico">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
        </svg>
      </div>
      <h2>暂无定时任务</h2>
      <p>后端尚未注册任务定义，请确认服务已更新。</p>
    </section>

    <!-- 任务卡片 -->
    <section v-else class="stack">
      <article
        v-for="task in tasks"
        :key="task.id"
        class="task glass-card"
        :class="[
          task.category || 'general',
          { on: task.enabled, run: task.running }
        ]"
      >
        <div class="task-glow" aria-hidden="true"></div>

        <!-- 上：身份 + 开关 -->
        <div class="task-top">
          <div class="who">
            <div class="avatar" :class="task.icon || 'task'">
              <svg v-if="task.icon === 'organize'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M4 8h6l2 2h8v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z"/>
                <path d="M9 15h6M12 12v6"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
              </svg>
            </div>
            <div class="who-text">
              <div class="name-row">
                <h2>{{ task.name }}</h2>
                <span v-if="task.category_label" class="tag">{{ task.category_label }}</span>
                <span class="tag state" :class="statusClass(task)">{{ statusText(task) }}</span>
              </div>
              <p>{{ task.description }}</p>
            </div>
          </div>

          <div class="power">
            <span class="power-label">{{ task.enabled ? '开启' : '关闭' }}</span>
            <label class="switch">
              <input
                type="checkbox"
                :checked="task.enabled"
                :disabled="savingId === task.id || task.running"
                @change="onToggleEvent(task, $event)"
              />
              <span class="track"><span class="knob"></span></span>
            </label>
          </div>
        </div>

        <!-- 时间信息 -->
        <div class="timebar">
          <div class="time-cell">
            <div class="time-ico next">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 1.5"/>
              </svg>
            </div>
            <div>
              <div class="time-k">下次执行</div>
              <div class="time-v">{{ nextText(task) }}</div>
            </div>
          </div>
          <div class="time-divider"></div>
          <div class="time-cell">
            <div class="time-ico last">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 9 8 9"/>
              </svg>
            </div>
            <div>
              <div class="time-k">上次执行</div>
              <div class="time-v">{{ task.last_run_time || '尚未运行' }}</div>
            </div>
          </div>
          <div class="time-divider hide-sm"></div>
          <div class="time-cell plan hide-sm">
            <div class="time-ico plan">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <rect x="3" y="5" width="18" height="16" rx="2"/>
                <path d="M3 10h18M8 3v4M16 3v4"/>
              </svg>
            </div>
            <div>
              <div class="time-k">当前计划</div>
              <div class="time-v accent">{{ draftLabel(task) }}</div>
            </div>
          </div>
        </div>

        <!-- 下：计划编辑 + 操作 -->
        <div class="task-bottom">
          <div class="schedule">
            <div class="field">
              <label>频率</label>
              <div class="seg neu-inset">
                <button
                  v-for="opt in freqOptions"
                  :key="opt.value"
                  type="button"
                  class="seg-btn"
                  :class="{ active: (draft[task.id]?.frequency || 'daily') === opt.value }"
                  :disabled="savingId === task.id"
                  @click="setFreq(task, opt.value)"
                >{{ opt.label }}</button>
              </div>
            </div>

            <div v-if="(draft[task.id]?.frequency || 'daily') === 'weekly'" class="field">
              <label>星期</label>
              <select
                class="ctrl"
                :value="draft[task.id]?.weekday ?? 1"
                :disabled="savingId === task.id"
                @change="onWeekdayEvent(task, $event)"
              >
                <option v-for="w in weekdays" :key="w.value" :value="w.value">{{ w.label }}</option>
              </select>
            </div>

            <div v-if="(draft[task.id]?.frequency || 'daily') === 'minutely'" class="field">
              <label>间隔</label>
              <select
                class="ctrl"
                :value="draft[task.id]?.interval || 5"
                :disabled="savingId === task.id"
                @change="onIntervalEvent(task, $event)"
              >
                <option v-for="n in minuteIntervals" :key="n" :value="n">
                  {{ n <= 1 ? '每分钟' : `每 ${n} 分钟` }}
                </option>
              </select>
            </div>

            <div v-if="(draft[task.id]?.frequency || 'daily') === 'hourly'" class="field">
              <label>间隔</label>
              <select
                class="ctrl"
                :value="draft[task.id]?.interval || 6"
                :disabled="savingId === task.id"
                @change="onIntervalEvent(task, $event)"
              >
                <option v-for="n in hourIntervals" :key="n" :value="n">每 {{ n }} 小时</option>
              </select>
            </div>

            <div
              v-if="(draft[task.id]?.frequency || 'daily') !== 'hourly' && (draft[task.id]?.frequency || 'daily') !== 'minutely'"
              class="field grow"
            >
              <label>时刻</label>
              <div class="clock">
                <select
                  class="ctrl clock-part"
                  :value="draft[task.id]?.hour ?? 3"
                  :disabled="savingId === task.id"
                  @change="onHourEvent(task, $event)"
                >
                  <option v-for="h in hours" :key="h" :value="h">{{ pad2(h) }}</option>
                </select>
                <span class="colon">:</span>
                <select
                  class="ctrl clock-part"
                  :value="draft[task.id]?.minute ?? 0"
                  :disabled="savingId === task.id"
                  @change="onMinuteEvent(task, $event)"
                >
                  <option v-for="m in minutes" :key="m" :value="m">{{ pad2(m) }}</option>
                </select>
              </div>
            </div>

            <div v-else-if="(draft[task.id]?.frequency || 'daily') === 'hourly'" class="field">
              <label>分钟</label>
              <select
                class="ctrl"
                :value="draft[task.id]?.minute ?? 0"
                :disabled="savingId === task.id"
                @change="onMinuteEvent(task, $event)"
              >
                <option v-for="m in minutes" :key="m" :value="m">第 {{ pad2(m) }} 分</option>
              </select>
            </div>
          </div>

          <div class="actions">
            <button
              class="btn btn-soft"
              :disabled="savingId === task.id || !isDraftDirty(task)"
              @click="saveTask(task)"
            >
              <span v-if="savingId === task.id" class="spinner"></span>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <path d="M17 21v-8H7v8M7 3v5h8"/>
              </svg>
              保存计划
            </button>
            <button
              class="btn btn-primary"
              :disabled="task.running || runningId === task.id"
              @click="runNow(task)"
            >
              <span v-if="task.running || runningId === task.id" class="spinner light"></span>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="7 4 19 12 7 20 7 4"/>
              </svg>
              {{ task.running || runningId === task.id ? '执行中…' : '立即执行' }}
            </button>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { tasksApi, type TaskItem, type TaskUpdatePayload } from '@/api/tasks'

const loading = ref(false)
const tasks = ref<TaskItem[]>([])
const errorMsg = ref('')
const infoMsg = ref('')
const savingId = ref('')
const runningId = ref('')
let infoTimer: number | undefined
let pollTimer: number | undefined

interface Draft {
  frequency: 'minutely' | 'daily' | 'weekly' | 'hourly'
  hour: number
  minute: number
  interval: number
  weekday: number
}

const draft = reactive<Record<string, Draft>>({})

const hours = Array.from({ length: 24 }, (_, i) => i)
const minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
const hourIntervals = [1, 2, 3, 4, 6, 8, 12]
const minuteIntervals = [1, 2, 3, 5, 10, 15, 20, 30]
const weekdays = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
]
const freqOptions = [
  { value: 'minutely' as const, label: '每 N 分钟' },
  { value: 'hourly' as const, label: '每 N 小时' },
  { value: 'daily' as const, label: '每天' },
  { value: 'weekly' as const, label: '每周' },
]

const schedulerReady = computed(
  () => tasks.value.length === 0 || tasks.value.some(t => t.scheduler_ready),
)

function pad2(n: number) {
  return String(n).padStart(2, '0')
}

function ensureDraft(task: TaskItem) {
  const p = task.schedule_preset || { frequency: 'daily' as const }
  const freq = (p.frequency === 'weekly' || p.frequency === 'hourly' || p.frequency === 'minutely')
    ? p.frequency
    : 'daily'
  draft[task.id] = {
    frequency: freq,
    hour: Number.isFinite(p.hour as number) ? Number(p.hour) : 3,
    minute: Number.isFinite(p.minute as number) ? Number(p.minute) : 0,
    interval: Number.isFinite(p.interval as number) ? Number(p.interval) : 6,
    weekday: Number.isFinite(p.weekday as number) ? Number(p.weekday) : 1,
  }
}

function draftLabel(task: TaskItem) {
  const d = draft[task.id]
  if (!d) return task.cron_label || task.cron || '-'
  if (d.frequency === 'minutely') {
    return d.interval <= 1 ? '每分钟' : `每 ${d.interval} 分钟`
  }
  if (d.frequency === 'hourly') return `每 ${d.interval} 小时 · ${pad2(d.minute)} 分`
  if (d.frequency === 'weekly') {
    const w = weekdays.find(x => x.value === d.weekday)?.label || '周一'
    return `${w} ${pad2(d.hour)}:${pad2(d.minute)}`
  }
  return `每天 ${pad2(d.hour)}:${pad2(d.minute)}`
}

function isDraftDirty(task: TaskItem) {
  const d = draft[task.id]
  if (!d) return false
  const p = task.schedule_preset || {}
  const freq = (p.frequency === 'weekly' || p.frequency === 'hourly' || p.frequency === 'minutely')
    ? p.frequency
    : 'daily'
  return (
    d.frequency !== freq
    || d.hour !== (Number(p.hour) || 0)
    || d.minute !== (Number(p.minute) || 0)
    || d.interval !== (Number(p.interval) || 6)
    || d.weekday !== (Number.isFinite(p.weekday as number) ? Number(p.weekday) : 1)
  )
}

function statusText(task: TaskItem) {
  if (task.running) return '运行中'
  if (task.enabled) return '已启用'
  return '已关闭'
}

function statusClass(task: TaskItem) {
  if (task.running) return 'run'
  if (task.enabled) return 'on'
  return 'off'
}

function nextText(task: TaskItem) {
  if (task.running) return '正在执行…'
  if (!task.enabled) return '未启用'
  return task.next_run_time || '等待调度'
}

function flash(msg: string) {
  infoMsg.value = msg
  if (infoTimer) window.clearTimeout(infoTimer)
  infoTimer = window.setTimeout(() => { infoMsg.value = '' }, 2800)
}

function startPoll() {
  if (pollTimer) return
  pollTimer = window.setInterval(() => { loadTasks(true) }, 4000)
}

function stopPoll() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function loadTasks(quiet = false) {
  if (!quiet) loading.value = true
  errorMsg.value = ''
  try {
    const res = await tasksApi.list()
    if (res.code !== 0) {
      errorMsg.value = res.message || '加载失败'
      return
    }
    const list = res.data?.tasks || []
    tasks.value = list
    for (const t of list) {
      if (!draft[t.id] || !isDraftDirty(t)) ensureDraft(t)
    }
    if (list.some(t => t.running)) startPoll()
    else {
      stopPoll()
      runningId.value = ''
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '加载任务失败'
  } finally {
    loading.value = false
  }
}

function eventValue(ev: Event): string {
  const el = ev.target as HTMLInputElement | HTMLSelectElement | null
  return el ? String(el.value) : ''
}

function onToggleEvent(task: TaskItem, ev: Event) {
  const el = ev.target as HTMLInputElement | null
  onToggle(task, !!(el && el.checked))
}

function setFreq(task: TaskItem, value: 'minutely' | 'daily' | 'weekly' | 'hourly') {
  if (!draft[task.id]) ensureDraft(task)
  const d = draft[task.id]
  const prev = d.frequency
  d.frequency = value
  // 切换频率时给合理默认间隔，避免小时间隔落到分钟语义
  if (value === 'minutely' && (prev !== 'minutely' || d.interval > 60 || d.interval < 1)) {
    d.interval = minuteIntervals.includes(d.interval) ? d.interval : 5
  }
  if (value === 'hourly' && (prev !== 'hourly' || d.interval > 24)) {
    d.interval = hourIntervals.includes(d.interval) ? d.interval : 6
  }
}

function onHourEvent(task: TaskItem, ev: Event) {
  draft[task.id].hour = Number(eventValue(ev))
}

function onMinuteEvent(task: TaskItem, ev: Event) {
  draft[task.id].minute = Number(eventValue(ev))
}

function onIntervalEvent(task: TaskItem, ev: Event) {
  draft[task.id].interval = Number(eventValue(ev))
}

function onWeekdayEvent(task: TaskItem, ev: Event) {
  draft[task.id].weekday = Number(eventValue(ev))
}

async function onToggle(task: TaskItem, enabled: boolean) {
  savingId.value = task.id
  errorMsg.value = ''
  try {
    const res = await tasksApi.update(task.id, { enabled })
    if (res.code !== 0) {
      errorMsg.value = res.message || '更新失败'
      await loadTasks(true)
      return
    }
    if (res.data) {
      const idx = tasks.value.findIndex(t => t.id === task.id)
      if (idx >= 0) tasks.value[idx] = res.data
      ensureDraft(res.data)
    }
    flash(enabled ? '已启用任务' : '已关闭任务')
  } catch (e: any) {
    errorMsg.value = e?.message || '更新失败'
    await loadTasks(true)
  } finally {
    savingId.value = ''
  }
}

async function saveTask(task: TaskItem) {
  const d = draft[task.id]
  if (!d) return
  savingId.value = task.id
  errorMsg.value = ''
  const payload: TaskUpdatePayload = {
    frequency: d.frequency,
    hour: d.hour,
    minute: d.minute,
    interval: d.interval,
    weekday: d.weekday,
  }
  try {
    const res = await tasksApi.update(task.id, payload)
    if (res.code !== 0) {
      errorMsg.value = res.message || '保存失败'
      return
    }
    if (res.data) {
      const idx = tasks.value.findIndex(t => t.id === task.id)
      if (idx >= 0) tasks.value[idx] = res.data
      ensureDraft(res.data)
    }
    flash('执行计划已保存')
  } catch (e: any) {
    errorMsg.value = e?.message || '保存失败'
  } finally {
    savingId.value = ''
  }
}

async function runNow(task: TaskItem) {
  runningId.value = task.id
  errorMsg.value = ''
  try {
    const res = await tasksApi.run(task.id)
    if (res.code !== 0) {
      errorMsg.value = res.message || '启动失败'
      runningId.value = ''
      return
    }
    flash(res.message || '任务已开始')
    const idx = tasks.value.findIndex(t => t.id === task.id)
    if (idx >= 0) tasks.value[idx] = { ...tasks.value[idx], running: true }
    startPoll()
    await loadTasks(true)
  } catch (e: any) {
    errorMsg.value = e?.message || '启动失败'
    runningId.value = ''
  }
}

onMounted(() => { loadTasks() })
onUnmounted(() => {
  stopPoll()
  if (infoTimer) window.clearTimeout(infoTimer)
})
</script>

<style scoped>
.tasks-page {
  --task-pad: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 36px;
  font-family: var(--font-sans);
}

/* ========== Toast ========== */
.toast {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid transparent;
}
.toast.danger {
  color: var(--danger);
  background: var(--danger-bg);
  border-color: rgba(255, 59, 48, 0.16);
}
.toast.info {
  color: var(--accent);
  background: var(--accent-bg);
  border-color: rgba(0, 113, 227, 0.14);
}
.toast.warn {
  color: #b36b00;
  background: var(--warning-bg);
  border-color: rgba(255, 149, 0, 0.2);
}

/* ========== Empty ========== */
.empty {
  padding: 56px 24px;
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
}
.empty h2 {
  margin: 6px 0 0;
  font-size: 16px;
  font-weight: 750;
  color: var(--text-primary);
}
.empty p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 360px;
}
.empty-ico {
  width: 68px;
  height: 68px;
  border-radius: 20px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: linear-gradient(145deg, rgba(0, 113, 227, 0.12), rgba(88, 86, 214, 0.08));
}
.empty-ico svg { width: 30px; height: 30px; }
.orbit {
  width: 52px;
  height: 52px;
  position: relative;
}
.orbit span {
  position: absolute;
  inset: 0;
  border: 2px solid transparent;
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
.orbit span:nth-child(2) {
  inset: 6px;
  animation-duration: 1.35s;
  border-top-color: var(--purple);
}
.orbit span:nth-child(3) {
  inset: 12px;
  animation-duration: 1.7s;
  border-top-color: var(--success);
}

/* ========== Task card ========== */
.stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.task {
  position: relative;
  overflow: hidden;
  border-radius: 22px;
  padding: 0;
  border: 1px solid var(--border);
  transition: transform var(--transition-base), box-shadow var(--transition-base), border-color var(--transition-base);
}
.task:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-lg);
}
.task.on {
  border-color: rgba(0, 113, 227, 0.18);
  box-shadow:
    var(--shadow-md),
    0 0 0 1px rgba(0, 113, 227, 0.04);
}
.task.run {
  border-color: rgba(0, 113, 227, 0.28);
  box-shadow:
    0 14px 36px rgba(0, 113, 227, 0.14),
    0 0 0 1px rgba(0, 113, 227, 0.08);
}
.task-glow {
  position: absolute;
  inset: auto -20% -40% auto;
  width: 280px;
  height: 280px;
  border-radius: 50%;
  pointer-events: none;
  opacity: 0.55;
  background: radial-gradient(circle, rgba(0, 113, 227, 0.12), transparent 68%);
}
.task.media .task-glow {
  background: radial-gradient(circle, rgba(88, 86, 214, 0.14), transparent 68%);
}
.task.general .task-glow {
  background: radial-gradient(circle, rgba(52, 199, 89, 0.12), transparent 68%);
}

.task-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: var(--task-pad) var(--task-pad) 14px;
}
.who {
  display: flex;
  gap: 14px;
  min-width: 0;
  flex: 1;
}
.avatar {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: var(--text-secondary);
  background: var(--bg-input);
  border: 1px solid var(--border);
}
.avatar.organize {
  color: #fff;
  border: none;
  background: linear-gradient(145deg, #4ea1ff, #0071e3 50%, #5856d6);
  box-shadow: 0 10px 20px rgba(0, 113, 227, 0.28);
}
.avatar svg { width: 24px; height: 24px; }
.who-text { min-width: 0; }
.name-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.name-row h2 {
  margin: 0;
  font-size: 17.5px;
  font-weight: 780;
  letter-spacing: -0.2px;
  color: var(--text-primary);
}
.tag {
  font-size: 11px;
  font-weight: 720;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.tag.state.on {
  color: var(--success);
  background: var(--success-bg);
  border-color: rgba(52, 199, 89, 0.18);
}
.tag.state.off {
  color: var(--text-tertiary);
}
.tag.state.run {
  color: var(--accent);
  background: var(--accent-bg);
  border-color: rgba(0, 113, 227, 0.16);
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.62; }
}
.who-text p {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-secondary);
  max-width: 640px;
}

.power {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding: 8px 10px 8px 14px;
  border-radius: 999px;
  background: var(--bg-solid);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.power-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  min-width: 28px;
}
.task.on .power-label { color: var(--success); }

.switch {
  position: relative;
  width: 48px;
  height: 28px;
  cursor: pointer;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}
.track {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.12);
  border: 1px solid var(--border);
  transition: all var(--transition-base);
}
.knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
  transition: transform var(--transition-base);
}
.switch input:checked + .track {
  background: linear-gradient(180deg, #34d399, var(--success));
  border-color: transparent;
}
.switch input:checked + .track .knob {
  transform: translateX(20px);
}
.switch input:disabled + .track {
  opacity: 0.55;
  cursor: not-allowed;
}

/* 时间条 */
.timebar {
  position: relative;
  z-index: 1;
  margin: 0 var(--task-pad);
  padding: 14px 16px;
  border-radius: 16px;
  display: grid;
  grid-template-columns: 1fr auto 1fr auto 1fr;
  gap: 12px;
  align-items: center;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0.28)),
    var(--bg-input);
  border: 1px solid var(--border);
}
:root[data-theme='dark'] .timebar {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02)),
    var(--bg-input);
}
.time-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.time-ico {
  width: 36px;
  height: 36px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.time-ico svg { width: 17px; height: 17px; }
.time-ico.next {
  color: var(--accent);
  background: var(--accent-bg);
}
.time-ico.last {
  color: var(--purple);
  background: var(--purple-bg);
}
.time-ico.plan {
  color: #0a7;
  background: rgba(48, 176, 199, 0.12);
}
.time-k {
  font-size: 11px;
  font-weight: 720;
  color: var(--text-tertiary);
  margin-bottom: 2px;
}
.time-v {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.time-v.accent { color: var(--accent); }
.time-divider {
  width: 1px;
  height: 28px;
  background: var(--border-strong);
  opacity: 0.7;
}

/* 底部 */
.task-bottom {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 16px var(--task-pad) var(--task-pad);
  flex-wrap: wrap;
}
.schedule {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  flex: 1;
  min-width: 0;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 120px;
}
.field.grow { min-width: 150px; }
.field label {
  font-size: 11px;
  font-weight: 720;
  color: var(--text-tertiary);
  padding-left: 2px;
}
.seg {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border-radius: 12px;
  width: fit-content;
  background: var(--bg-input);
}
.seg-btn {
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  padding: 8px 12px;
  border-radius: 9px;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-base);
  white-space: nowrap;
}
.seg-btn:hover:not(:disabled) { color: var(--text-secondary); }
.seg-btn.active {
  background: var(--bg-solid);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
.seg-btn:disabled { opacity: 0.55; cursor: not-allowed; }

.ctrl {
  appearance: none;
  border: 1px solid var(--border);
  background: var(--bg-solid);
  color: var(--text-primary);
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 650;
  outline: none;
  min-width: 120px;
  transition: border-color var(--transition-base), box-shadow var(--transition-base);
}
.ctrl:focus {
  border-color: rgba(0, 113, 227, 0.45);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.12);
}
.clock {
  display: flex;
  align-items: center;
  gap: 6px;
}
.clock-part {
  min-width: 72px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.colon {
  font-weight: 800;
  color: var(--text-tertiary);
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* 按钮 */
.btn {
  border: none;
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  transition: all var(--transition-base);
  white-space: nowrap;
}
.btn svg { width: 15px; height: 15px; flex-shrink: 0; }
.btn:disabled { opacity: 0.48; cursor: not-allowed; }
.btn-primary {
  background: linear-gradient(180deg, var(--accent-hover), var(--accent));
  color: #fff;
  box-shadow: 0 8px 18px rgba(0, 113, 227, 0.28);
}
.btn-primary:hover:not(:disabled) {
  filter: brightness(1.05);
  transform: translateY(-1px);
}
.btn-soft {
  background: var(--bg-solid);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.btn-soft:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0, 0, 0, 0.12);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
.spinner.light {
  border-color: rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
}
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .timebar {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .time-divider { display: none; }
  .hide-sm { display: none !important; }
}
@media (max-width: 640px) {
  .task-top, .task-bottom { padding-left: 16px; padding-right: 16px; }
  .timebar { margin-left: 16px; margin-right: 16px; }
  .power-label { display: none; }
  .actions { width: 100%; }
  .actions .btn { flex: 1; }
}
</style>

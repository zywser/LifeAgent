<template>
  <div class="chat-layout">
    <div class="chat-main">
      <div class="chat-header">
        <div>
          <h2>对话助手</h2>
          <span class="sub">多智能体生活管家</span>
        </div>
        <el-button size="small" plain @click="newChat">+ 新对话</el-button>
      </div>

      <div class="messages" ref="scrollEl">
        <div v-if="!messages.length && !running" class="empty">
          <div class="empty-card">
            <div class="empty-badge">✨</div>
            <h3>开始你的任务</h3>
            <p>试试：帮我规划从曲靖出发 2 天 1 晚自驾，预算 700</p>
          </div>
        </div>

        <template v-for="(m, i) in messages" :key="i">
          <div v-if="showDateDivider(m, i)" class="date-divider">{{ dateLabel(m) }}</div>
          <div :class="['row', m.role]">
            <div class="avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
            <div class="bubble-wrap">
              <div :class="['bubble', m.role]">
                <div class="bubble-text">{{ m.content }}</div>
                <div v-if="m.time" class="bubble-time">{{ formatTime(m.time) }}</div>
              </div>
              <div class="msg-line" :class="m.role">
                <el-button v-if="m.role === 'assistant' && m.content" size="small" text class="copy-btn" @click="copy(m.content)">复制</el-button>
              </div>
            </div>
          </div>
        </template>

        <div v-if="running" class="row assistant">
          <div class="avatar">AI</div>
          <div class="bubble assistant thinking">
            <span class="thinking-dot"></span>
            <span class="thinking-text">{{ thinkingLabel }}</span>
          </div>
        </div>
      </div>

      <div class="composer">
        <div class="quick-actions">
          <el-button size="small" :type="tool==='expense'?'success':'default'" plain @click="toggleTool('expense')">💰 记账</el-button>
          <el-button size="small" :type="tool==='todo'?'success':'default'" plain @click="toggleTool('todo')">✅ 待办</el-button>
          <el-button size="small" :type="tool==='plan'?'success':'default'" plain @click="toggleTool('plan')">📅 规划</el-button>
          <el-button size="small" :type="tool==='review'?'success':'default'" plain @click="toggleTool('review')">📊 复盘</el-button>
          <el-button size="small" :type="tool==='habit'?'success':'default'" plain @click="toggleTool('habit')">🏃 习惯</el-button>
        </div>
        <div class="input-wrap">
          <el-input v-model="input" type="textarea" :autosize="{minRows:1,maxRows:4}"
            :placeholder="placeholder" @keydown.enter.exact.prevent="send" />
          <el-button type="primary" :loading="loading" @click="send" class="send-btn">发送</el-button>
        </div>
      </div>
    </div>

    <aside class="agent-panel">
      <div class="panel-title">
        <span class="dot-indicator" :class="{ pulse: running }"></span>
        Agent 执行链路
      </div>
      <div class="timeline">
        <div v-if="!orderedSteps.length" class="tl-empty">
          <div class="tl-empty-icon">🤖</div>
          <div>发送任务后这里展示<br/>多智能体执行进度</div>
        </div>
        <div v-for="(s, i) in orderedSteps" :key="i" class="tl-item" :class="s.status">
          <div class="tl-marker">
            <div class="tl-circle">
              <span v-if="s.status === 'done'">✓</span>
              <span v-else-if="s.status === 'running'" class="spinner"></span>
              <span v-else>{{ i + 1 }}</span>
            </div>
            <div v-if="i < orderedSteps.length - 1" class="tl-line"></div>
          </div>
          <div class="tl-body">
            <div class="tl-name">{{ s.label }}</div>
            <div class="tl-status">
              <span v-if="s.status === 'running'" class="badge running">执行中</span>
              <span v-else-if="s.status === 'done'" class="badge done">已完成</span>
              <span v-else class="badge waiting">等待</span>
            </div>
          </div>
        </div>
      </div>
      <div class="panel-actions">
        <el-button type="primary" class="full" @click="$router.push('/graph')">查看链路图</el-button>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useRunStore } from '../stores/run'
import { streamChat } from '../api/chat'
import { formatTime, formatDate } from '../utils/format'

const run = useRunStore()
const route = useRoute()
const input = ref('')
const loading = ref(false)
const messages = computed(() => run.messages)
const scrollEl = ref(null)
const tool = ref('')

// —— 消息日期分组（兼容旧数据：无 time 的消息不显示时间、不产生分隔线）——
function dateOf(m) {
  if (!m.time) return ''
  const d = new Date(m.time)
  if (isNaN(d)) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function showDateDivider(m, i) {
  if (!m.time) return false
  if (i === 0) return true
  return dateOf(m) !== dateOf(messages.value[i - 1])
}
function dateLabel(m) {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const d = new Date(m.time)
  if (isNaN(d)) return ''
  const startOf = new Date(d); startOf.setHours(0, 0, 0, 0)
  const diff = Math.round((today - startOf) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  return formatDate(m.time)
}

const PLACEHOLDERS = {
  expense: '说：红包支出20元午饭 / 工资收入5000元 / 交通支出15元打车',
  todo: '说：明天下午3点开会 / 周五前交报告',
  plan: '描述你的需求，Agent 帮你规划',
  review: '问：今天花了多少？/ 这周记账情况',
  habit: '问：我最近打卡怎么样？'
}
const placeholder = computed(() => PLACEHOLDERS[tool.value] || '输入任务，Enter 发送，Shift+Enter 换行')
function toggleTool(t){ tool.value = tool.value === t ? '' : t }

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text; document.body.appendChild(ta); ta.select()
    document.execCommand('copy'); ta.remove()
  }
  ElMessage.success('已复制')
}

const ORDER = ['planner', 'retriever', 'executor', 'synthesizer', 'reviewer']
const orderedSteps = computed(() => {
  // 按节点顺序铺开，executor 循环多次会出现多条（用 filter 而不是 find）
  const out = []
  for (const n of ORDER) {
    for (const s of run.steps) {
      if (s.node === n) out.push(s)
    }
  }
  return out
})
const thinkingLabel = computed(() => {
  const cur = orderedSteps.value.find(s => s.status === 'running')
  if (!cur) return '思考中…'
  const labels = {
    planner: '正在规划任务',
    retriever: '正在检索知识',
    executor: '正在执行子任务',
    synthesizer: '正在汇总结果',
    reviewer: '正在审核结果'
  }
  return labels[cur.node] || '处理中…'
})

async function scrollBottom() {
  await nextTick()
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
}
function newChat() {
  run.newChat()
  window.dispatchEvent(new Event('conversations-updated'))
  scrollBottom()
}
function typewriter(fullText, role = 'assistant') {
  return new Promise(resolve => {
    run.messages.push({ role, content: '', time: new Date().toISOString() })
    const idx = run.messages.length - 1
    let i = 0
    const timer = setInterval(() => {
      run.messages[idx].content = fullText.slice(0, i + 2)
      i += 2; scrollBottom()
      if (i >= fullText.length) { clearInterval(timer); resolve() }
    }, 18)
  })
}
async function send() {
  let q = input.value.trim()
  if (!q || loading.value) return
  if (tool.value) {
    const hints = {
      expense: '[记账] ',
      todo: '[待办] ',
      plan: '[规划] ',
      review: '[复盘] ',
      habit: '[习惯] '
    }
    q = hints[tool.value] + q
  }
  input.value = ''
  run.reset(); run.addMessage('user', q); run.setRunning(true); loading.value = true
  scrollBottom()
  try {
    await streamChat(q, async (event, data) => {
      if (event === 'node_start') run.startNode(data.node)
      else if (event === 'node_end') run.finishNode(data.node)
      else if (event === 'final') {
        const answer = (data.answer || '').trim() || '（未获取到回答，请稍后重试）'
        run.setRunning(false)
        // 打字机期间保持 loading 锁定，防止并发发送导致气泡乱序
        await typewriter(answer)
        loading.value = false
        run.setAnswer(answer)
        await run.saveConversation()
        window.dispatchEvent(new Event('conversations-updated'))
        if (route.path !== '/chat') {
          window.dispatchEvent(new CustomEvent('new-reply', { detail: { id: run.currentId } }))
        }
      }
      scrollBottom()
    })
  } catch (e) {
    run.setRunning(false); run.addMessage('assistant', '出错了：' + e.message); await run.saveConversation()
  } finally { loading.value = false; scrollBottom() }
}
</script>

<style scoped>
.chat-layout { display: flex; gap: 20px; height: calc(100vh - 56px - 48px); }
.chat-main { flex: 1; display: flex; flex-direction: column; background: #fff; border-radius: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.04); min-width: 0; }
.chat-header { padding: 20px 24px 0; }
.chat-header h2 { margin: 0; font-size: 20px; color: #111827; }
.chat-header .sub { font-size: 13px; color: #9ca3af; }
.messages { flex: 1; overflow-y: auto; padding: 20px 24px; }
.empty { display: flex; align-items: center; justify-content: center; height: 100%; }
.empty-card { text-align: center; color: #6b7280; }
.empty-badge { font-size: 40px; }
.empty-card h3 { margin: 12px 0 6px; color: #111827; }
.empty-card p { font-size: 13px; }
.row { display: flex; gap: 12px; margin: 16px 0; align-items: flex-start; }
.row.user { flex-direction: row-reverse; }
.date-divider {
  text-align: center; color: #9ca3af; font-size: 12px;
  margin: 26px 0 10px; display: flex; align-items: center; gap: 12px;
}
.date-divider::before, .date-divider::after { content: ''; flex: 1; height: 1px; background: #eef0f3; }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: #e5e7eb; color: #374151; display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.row.user .avatar { background: #2563eb; color: #fff; }
.bubble-wrap { max-width: 72%; display: flex; flex-direction: column; min-width: 0; }
.bubble { max-width: 100%; padding: 12px 16px; border-radius: 14px; font-size: 14px; line-height: 1.7; }
.bubble.user { background: #2563eb; color: #fff; border-top-right-radius: 4px; }
.bubble.assistant { background: #f8fafc; border: 1px solid #eef0f3; border-top-left-radius: 4px; color: #1f2937; }
.bubble-text { white-space: pre-wrap; word-break: break-word; }
.bubble-time { margin-top: 6px; font-size: 11px; text-align: right; line-height: 1.4; }
.bubble.user .bubble-time { color: rgba(255,255,255,.72); }
.bubble.assistant .bubble-time { color: #b0b8c4; }
.msg-line { display: flex; align-items: center; justify-content: flex-end; margin-top: 4px; }
.msg-line.user { justify-content: flex-end; }
.copy-btn { font-size: 11px; height: 22px; padding: 0 6px; color: #9ca3af; }
.copy-btn:hover { color: #2563eb; }
.thinking { display: flex; align-items: center; gap: 10px; color: #6b7280; }
.thinking-dot { width: 8px; height: 8px; border-radius: 50%; background: #2563eb; animation: pulse 1.2s ease-in-out infinite; }
.thinking-text { font-size: 13px; }
@keyframes pulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: .5; } }
.composer { padding: 16px 20px 20px; border-top: 1px solid #f0f1f3; }
.quick-actions { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.input-wrap { display: flex; gap: 10px; align-items: flex-end; }
.input-wrap .el-textarea { flex: 1; }
.send-btn { align-self: stretch; }
.agent-panel { width: 300px; background: #fff; border-radius: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.04); padding: 20px; display: flex; flex-direction: column; }
.panel-title { font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 18px; display: flex; align-items: center; gap: 8px; }
.dot-indicator { width: 8px; height: 8px; border-radius: 50%; background: #d1d5db; }
.dot-indicator.pulse { background: #2563eb; animation: pulse 1.2s ease-in-out infinite; }
.timeline { flex: 1; position: relative; }
.tl-empty { text-align: center; color: #9ca3af; font-size: 13px; margin-top: 40px; line-height: 1.7; }
.tl-empty-icon { font-size: 36px; margin-bottom: 8px; }
.tl-item { display: flex; gap: 14px; position: relative; padding-bottom: 22px; }
.tl-item:last-child { padding-bottom: 0; }
.tl-marker { position: relative; display: flex; flex-direction: column; align-items: center; width: 28px; flex-shrink: 0; }
.tl-circle { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; background: #f3f4f6; color: #9ca3af; border: 2px solid #e5e7eb; z-index: 1; transition: all .3s; }
.tl-item.running .tl-circle { background: #eff6ff; border-color: #2563eb; color: #2563eb; box-shadow: 0 0 0 4px rgba(37,99,235,.1); }
.tl-item.done .tl-circle { background: #10b981; border-color: #10b981; color: #fff; }
.tl-line { position: absolute; top: 28px; left: 50%; transform: translateX(-50%); width: 2px; height: calc(100% - 28px); background: #e5e7eb; }
.tl-item.done .tl-line { background: #10b981; }
.spinner { width: 12px; height: 12px; border: 2px solid rgba(37,99,235,.2); border-top-color: #2563eb; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.tl-body { padding-top: 3px; flex: 1; }
.tl-name { font-size: 14px; font-weight: 600; color: #1f2937; }
.tl-item.waiting .tl-name { color: #9ca3af; font-weight: 500; }
.tl-status { margin-top: 4px; }
.badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; line-height: 1.4; }
.badge.running { background: #eff6ff; color: #2563eb; }
.badge.done { background: #ecfdf5; color: #059669; }
.badge.waiting { background: #f3f4f6; color: #9ca3af; }
.panel-actions { margin-top: 16px; padding-top: 16px; border-top: 1px solid #f0f1f3; }
.full { width: 100%; }

/* 窄屏隐藏 Agent 面板，聊天区优先 */
@media (max-width: 1100px) {
  .agent-panel { display: none; }
}
@media (max-width: 600px) {
  .chat-layout { height: calc(100vh - 56px - 40px); }
  .messages { padding: 14px 16px; }
  .composer { padding: 12px 14px 14px; }
  .quick-actions { gap: 6px; }
  .bubble-wrap { max-width: 85%; }
}
</style>

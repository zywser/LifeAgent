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
                <div class="bubble-text" v-html="linkify(m.content)"></div>
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
            <div class="tl-name">{{ s.label }}<span v-if="s.count > 1" class="tl-count">×{{ s.count }}</span></div>
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
import { ref, computed, nextTick, watch, onActivated, onDeactivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useRunStore } from '../stores/run'
import { streamChat } from '../api/chat'
import { getConversation } from '../api/conversations'
import { formatTime, formatDate } from '../utils/format'

// 组件名：配合 App.vue 的 keep-alive include="Chat"，切页时组件缓存不销毁，
// 回来时消息区、执行链路、输入框全部原样保留（与豆包网页对话一致）
defineOptions({ name: 'Chat' })

const run = useRunStore()
const route = useRoute()
const router = useRouter()
const input = ref('')
const loading = ref(false)
const messages = computed(() => run.messages)
// 模板里直接用 run.running 会报警告；这里统一暴露为响应式 running
const running = computed(() => run.running)
const scrollEl = ref(null)
const tool = ref('')

// —— 回答文本里的链接转为可点击 <a>（先转义再链接化，防 XSS）——
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function linkify(text) {
  const escaped = escapeHtml(text)
  const placeholders = []
  let html = escaped
  // 1. 先处理 markdown 链接 [文字](url)：收集成占位符，避免与裸 URL 正则互相嵌套
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (m, label, url) => {
      const ph = `@@LINK${placeholders.length}@@`
      placeholders.push(`<a href="${url}" target="_blank" rel="noopener noreferrer" class="msg-link">${label}</a>`)
      return ph
    }
  )
  // 2. 再处理裸 URL（含后端追加的"参考来源：\n- url"形式）
  html = html.replace(/https?:\/\/[^\s<>"'（）()。，！？；：、]+/g, (url) => {
    const ph = `@@LINK${placeholders.length}@@`
    placeholders.push(`<a href="${url}" target="_blank" rel="noopener noreferrer" class="msg-link">${url}</a>`)
    return ph
  })
  // 3. 还原占位
  html = html.replace(/@@LINK(\d+)@@/g, (m, i) => placeholders[Number(i)])
  return html
}

// —— 历史会话独立路由：/chat/s/:id 进入/切换时加载对应会话（豆包/DeepSeek 式）——
// 双标签页/多端打开不同会话 URL 互不干扰；回答进行中切到别的会话由 round 接管，
// 完成时保存回发起会话，不污染当前浏览的会话。
async function loadFromRoute() {
  const id = route.params.id
  if (!id) return
  // 正在回答且正是发起会话：保留现场（store 已是最新），不重新加载打断
  if (run.running && run._round && String(run._round.id) === String(id)) return
  if (String(run.currentId) === String(id)) return
  try {
    const { data } = await getConversation(id)
    if (data && Array.isArray(data.messages)) {
      run.loadConversation({ id: String(data.id), title: data.title, preview: data.preview, time: data.time, messages: data.messages })
    }
  } catch {
    // 云端没有（本地占位/离线）→ 本地 localStorage 兜底
    const arr = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]')
    const c = arr.find(x => String(x.id) === String(id))
    if (c) run.loadConversation(c)
  }
}
// /chat（无 id）= 永远的新对话页（欢迎界面）：
// 只要 URL 不带会话 id，一律空白新对话，绝不残留任何历史会话内容；
// 唯一例外是回答进行中切回 /chat（round 接管现场，回答完成自动跳转到新会话 URL）。
watch(() => route.params.id, (id) => {
  if (!id) {
    // 回答进行中：round 接管现场，不打断
    if (run.running) return
    // 当前对话（发过消息/回答完成/回答中断）：保留问答现场，直到用户新建对话或打开历史会话
    if (run.currentIsActive && run.messages.length) return
    run.newChat()
    return
  }
  loadFromRoute()
}, { immediate: true })
// 组件激活标记：仅在 chat 页可见时做 URL 收尾跳转，避免切到别的页面被强制跳回；
// 同时兜底：无论以何种方式回到 /chat（非 watch 路径，如浏览器前进后退），
// 无会话 id 一律清成新对话欢迎页（回答进行中除外，round 接管现场）。
let isActive = true
onActivated(() => {
  isActive = true
  // 兜底：任何方式回到 /chat（无 id）→ 保持欢迎页空白；
  // 例外：回答进行中（round 接管）或当前对话有内容（保留问答现场）
  if (!route.params.id && !run.running && !(run.currentIsActive && run.messages.length)) run.newChat()
})
onDeactivated(() => { isActive = false })

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
  // 按节点顺序铺开；连续重复节点（如 executor 逐个子任务循环）折叠成一条 ×N，
  // 避免链路刷屏撑出页面；executor 循环多次会出现多条（用 filter 而不是 find）
  const out = []
  for (const n of ORDER) {
    for (const s of run.steps) {
      if (s.node === n) {
        const last = out[out.length - 1]
        if (last && last.node === n && last.status === s.status) {
          last.count = (last.count || 1) + 1
        } else {
          out.push({ ...s, count: 1 })
        }
      }
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
  // 新对话回到无 id 的 /chat（独立路由归零）；发消息保存后 URL 再更新为新会话
  if (route.params.id) router.replace('/chat')
  window.dispatchEvent(new Event('conversations-updated'))
  scrollBottom()
}
function typewriter(fullText, role = 'assistant') {
  return new Promise(resolve => {
    // 回答进行中若已切换到别的会话（currentId 不再是发起会话），
    // 打字机写到 round 的独立缓冲，避免污染当前浏览的会话；回答完成时由 saveRound 写回原会话
    const switched = run.currentId !== (run._round?.id)
    const target = switched ? (run._round.buffer || (run._round.buffer = [])) : run.messages
    target.push({ role, content: '', time: new Date().toISOString() })
    const idx = target.length - 1
    let i = 0
    const timer = setInterval(() => {
      target[idx].content = fullText.slice(0, i + 2)
      i += 2
      if (!switched) scrollBottom()
      // 打字机中间态每约 180ms 落一次盘，刷新页面时也能恢复大部分内容
      if (i % 10 === 0) run._persist()
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
  // 先加入用户消息再记录本轮上下文：快照包含本轮提问；
  // 回答进行中切换会话，回答仍会保存回本轮发起的会话
  run.addMessage('user', q)
  // 发送消息后标记为"当前对话"：无论从新对话页还是历史会话 URL 发起，
  // 切走再点"对话助手"回来都保留问答现场（豆包式），不再被清成欢迎页
  run.setCurrentActive(true)
  run.startRound()
  run.setRunning(true); loading.value = true
  // 发消息立即跳转到"这个对话"的独立路由（先用本地占位 id）：
  // 刷新/切走/回答完成都不会把现场挂在新对话页上丢失，回答完成后再换成服务器 id
  router.replace(`/chat/s/${run.currentId}`)
  scrollBottom()
  // 防重入：个别网络环境下 SSE 的 final/error 事件可能重复到达，
  // 只允许处理一次，避免同一轮回答被 typewriter 重复写气泡、saveRound 重复保存
  let finalized = false
  try {
    await streamChat(q, async (event, data) => {
      if (event === 'node_start') run.startNode(data.node)
      else if (event === 'node_end') run.finishNode(data.node)
      else if (event === 'error') {
        if (finalized) return
        finalized = true
        const msg = (data && data.message) || '服务异常，请稍后重试'
        run.setRunning(false)
        const answer = '出错了：' + msg
        run.addMessage('assistant', answer)
        const saved = await run.saveRound(answer)
        loading.value = false
        window.dispatchEvent(new CustomEvent('agent-reply-done', {
          detail: { id: saved?.id || run._round?.id || run.currentId, title: saved?.title || '', preview: '任务执行出错：' + msg }
        }))
      }
      else if (event === 'final') {
        if (finalized) return
        finalized = true
        const answer = (data.answer || '').trim() || '（未获取到回答，请稍后重试）'
        run.setRunning(false)
        // 打字机期间保持 loading 锁定，防止并发发送导致气泡乱序
        await typewriter(answer)
        loading.value = false
        run.setAnswer(answer)
        // 保存到发起回答的会话（round.id）：即使中途切换过会话，数据也完整回到原会话
        const roundId = run._round?.id
        const saved = await run.saveRound(answer)
        // 新会话保存成功后把 URL 更新为该会话的独立路由（用户在发起会话时）；
        // 用 route.path 判断（不依赖 keep-alive 时序）：切到别的页面时保持当前浏览 URL 不动，
        // 避免强制跳转、也避免触发加载逻辑把"当前对话"标记清掉
        const onRound = route.params.id === undefined || (roundId != null && String(route.params.id) === String(roundId))
        const onChat = route.path === '/chat' || route.path.startsWith('/chat/')
        if (onChat && onRound && saved?.id && String(saved.id) !== String(route.params.id || '')) {
          router.replace(`/chat/s/${saved.id}`)
        }
        window.dispatchEvent(new Event('conversations-updated'))
        // 无论是否还在对话页都派发完成提醒（跨页可见：红点 + toast + 系统通知）
        window.dispatchEvent(new CustomEvent('agent-reply-done', {
          detail: { id: saved?.id || run._round?.id || run.currentId, title: saved?.title || '', preview: saved?.preview || '' }
        }))
        if (route.path !== '/chat') {
          window.dispatchEvent(new CustomEvent('new-reply', { detail: { id: run._round?.id || run.currentId } }))
        }
      }
      scrollBottom()
    })
  } catch (e) {
    run.setRunning(false)
    // 页面刷新/关闭/切走导致 SSE 连接中断：不保存"出错了"垃圾气泡，
    // 已发出的提问（user 消息）已持久化到本地，重进页面可见、可重新提问；
    // 只有后端/网络真实报错才记录错误消息，避免污染会话
    const isConn = e && (e.name === 'TypeError' || /fetch|network|abort|interrupted/i.test(String(e.message || '')))
    if (!isConn) {
      const answer = '出错了：' + (e.message || '未知错误')
      run.addMessage('assistant', answer)
      const saved = await run.saveRound(answer)
      window.dispatchEvent(new CustomEvent('agent-reply-done', {
        detail: { id: saved?.id || run._round?.id || run.currentId, title: saved?.title || '', preview: '回答中断：' + e.message }
      }))
    } else {
      // 连接中断：不写错误气泡；结束 round，避免"对话助手"入口残留现场
      run.finishRound()
    }
  } finally { loading.value = false; scrollBottom() }
}
</script>

<style scoped>
.chat-layout { display: flex; gap: 20px; height: calc(100vh - 56px - 48px); }
.chat-main { flex: 1; display: flex; flex-direction: column; background: var(--card); border-radius: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.04); min-width: 0; }
.chat-header { padding: 20px 24px 0; }
.chat-header h2 { margin: 0; font-size: 20px; color: var(--text); }
.chat-header .sub { font-size: 13px; color: var(--text-3); }
.messages { flex: 1; overflow-y: auto; padding: 20px 24px; }
.empty { display: flex; align-items: center; justify-content: center; height: 100%; }
.empty-card { text-align: center; color: var(--text-2); }
.empty-badge { font-size: 40px; }
.empty-card h3 { margin: 12px 0 6px; color: var(--text); }
.empty-card p { font-size: 13px; }
.row { display: flex; gap: 12px; margin: 16px 0; align-items: flex-start; }
.row.user { flex-direction: row-reverse; }
.date-divider {
  text-align: center; color: var(--text-3); font-size: 12px;
  margin: 26px 0 10px; display: flex; align-items: center; gap: 12px;
}
.date-divider::before, .date-divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--border); color: var(--text); display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.row.user .avatar { background: #2563eb; color: #fff; }
.bubble-wrap { max-width: 72%; display: flex; flex-direction: column; min-width: 0; }
.bubble { max-width: 100%; padding: 12px 16px; border-radius: 14px; font-size: 14px; line-height: 1.7; }
.bubble.user { background: #2563eb; color: #fff; border-top-right-radius: 4px; }
.bubble.assistant { background: var(--card-2); border: 1px solid var(--border); border-top-left-radius: 4px; color: var(--text); }
.bubble-text { white-space: pre-wrap; word-break: break-word; }
.msg-link { color: var(--primary); text-decoration: underline; word-break: break-all; }
.msg-link:hover { opacity: .8; }
.bubble-time { margin-top: 6px; font-size: 11px; text-align: right; line-height: 1.4; }
.bubble.user .bubble-time { color: rgba(255,255,255,.72); }
.bubble.assistant .bubble-time { color: #b0b8c4; }
.msg-line { display: flex; align-items: center; justify-content: flex-end; margin-top: 4px; }
.msg-line.user { justify-content: flex-end; }
.copy-btn { font-size: 11px; height: 22px; padding: 0 6px; color: var(--text-3); }
.copy-btn:hover { color: #2563eb; }
.thinking { display: flex; align-items: center; gap: 10px; color: var(--text-2); }
.thinking-dot { width: 8px; height: 8px; border-radius: 50%; background: #2563eb; animation: pulse 1.2s ease-in-out infinite; }
.thinking-text { font-size: 13px; }
@keyframes pulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: .5; } }
.composer { padding: 16px 20px 20px; border-top: 1px solid #f0f1f3; }
.quick-actions { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.input-wrap { display: flex; gap: 10px; align-items: flex-end; }
.input-wrap .el-textarea { flex: 1; }
.send-btn { align-self: stretch; }
.agent-panel { width: 300px; background: var(--card); border-radius: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.04); padding: 20px; display: flex; flex-direction: column; }
.panel-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 18px; display: flex; align-items: center; gap: 8px; }
.dot-indicator { width: 8px; height: 8px; border-radius: 50%; background: #d1d5db; }
.dot-indicator.pulse { background: #2563eb; animation: pulse 1.2s ease-in-out infinite; }
.timeline { flex: 1; position: relative; overflow-y: auto; min-height: 0; scrollbar-width: thin; }
.tl-count { font-size: 11px; color: var(--text-3); background: var(--hover); padding: 0 6px; border-radius: 8px; margin-left: 6px; vertical-align: 1px; }
.tl-empty { text-align: center; color: var(--text-3); font-size: 13px; margin-top: 40px; line-height: 1.7; }
.tl-empty-icon { font-size: 36px; margin-bottom: 8px; }
.tl-item { display: flex; gap: 14px; position: relative; padding-bottom: 22px; }
.tl-item:last-child { padding-bottom: 0; }
.tl-marker { position: relative; display: flex; flex-direction: column; align-items: center; width: 28px; flex-shrink: 0; }
.tl-circle { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; background: var(--hover); color: var(--text-3); border: 2px solid var(--border); z-index: 1; transition: all .3s; }
.tl-item.running .tl-circle { background: var(--primary-bg); border-color: #2563eb; color: #2563eb; box-shadow: 0 0 0 4px rgba(37,99,235,.1); }
.tl-item.done .tl-circle { background: #10b981; border-color: #10b981; color: #fff; }
.tl-line { position: absolute; top: 28px; left: 50%; transform: translateX(-50%); width: 2px; height: calc(100% - 28px); background: var(--border); }
.tl-item.done .tl-line { background: #10b981; }
.spinner { width: 12px; height: 12px; border: 2px solid rgba(37,99,235,.2); border-top-color: #2563eb; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.tl-body { padding-top: 3px; flex: 1; }
.tl-name { font-size: 14px; font-weight: 600; color: var(--text); }
.tl-item.waiting .tl-name { color: var(--text-3); font-weight: 500; }
.tl-status { margin-top: 4px; }
.badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; line-height: 1.4; }
.badge.running { background: var(--primary-bg); color: #2563eb; }
.badge.done { background: rgba(16,185,129,.12); color: #059669; }
.badge.waiting { background: var(--hover); color: var(--text-3); }
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

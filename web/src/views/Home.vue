<template>
  <div class="home">
    <div class="home-head">
      <h1 class="page-title">私人生活智能管家</h1>
      <div class="head-actions">
        <el-button size="small" :loading="syncing" @click="doSync">同步</el-button>
        <el-button size="small" type="primary" :loading="summarizing" @click="genSummary">{{ summary ? '重新生成' : '今日摘要' }}</el-button>
      </div>
    </div>

    <div v-if="summary" class="summary-result">{{ summary }}</div>

    <div class="dashboard">
      <!-- 左列：今日行动 + 功能入口 3×3 -->
      <div class="dash-left">
        <div class="today-card">
          <div class="tc-head">
            <span class="tc-title">🗓 今日行动</span>
            <span class="tc-count">{{ actions.length ? actions.length + ' 项待处理' : '全部搞定' }}</span>
          </div>
          <div v-if="!actions.length" class="tc-empty">今天没有待处理的事项 🎉</div>
          <div v-for="(a, i) in actions" :key="i" class="tc-item" :class="{ urgent: a.urgent }" @click="$router.push(a.link)">
            <span class="tc-icon">{{ a.icon }}</span>
            <div class="tc-body">
              <div class="tc-text">{{ a.text }}</div>
              <div class="tc-sub">{{ a.sub }}</div>
            </div>
            <span class="tc-go">→</span>
          </div>
        </div>

        <div class="feature-grid">
          <div class="card feature primary" @click="$router.push('/chat')">
            <div class="f-icon"><el-icon><Notebook /></el-icon></div>
            <div class="f-label">生活规划</div>
            <div class="f-desc">规划行程</div>
          </div>
          <div class="card feature" @click="$router.push('/accounting')">
            <div class="f-icon"><el-icon><Plus /></el-icon></div>
            <div class="f-label">轻量记账</div>
            <div class="f-desc">收支记账</div>
          </div>
          <div class="card feature" @click="$router.push('/todo')">
            <div class="f-icon"><el-icon><Finished /></el-icon></div>
            <div class="f-label">待办清单</div>
            <div class="f-desc">任务管理</div>
          </div>
          <div class="card feature" @click="$router.push('/habit')">
            <div class="f-icon"><el-icon><Pointer /></el-icon></div>
            <div class="f-label">习惯打卡</div>
            <div class="f-desc">每日坚持</div>
          </div>
          <div class="card feature" @click="$router.push('/diary')">
            <div class="f-icon"><el-icon><EditPen /></el-icon></div>
            <div class="f-label">每日日记</div>
            <div class="f-desc">心情记录</div>
          </div>
          <div class="card feature" @click="$router.push('/water')">
            <div class="f-icon"><el-icon><Coffee /></el-icon></div>
            <div class="f-label">喝水记录</div>
            <div class="f-desc">补水打卡</div>
          </div>
          <div class="card feature" @click="$router.push('/savings')">
            <div class="f-icon"><el-icon><Wallet /></el-icon></div>
            <div class="f-label">存钱目标</div>
            <div class="f-desc">攒钱进度</div>
          </div>
          <div class="card feature" @click="$router.push('/anniversary')">
            <div class="f-icon"><el-icon><Calendar /></el-icon></div>
            <div class="f-label">纪念日</div>
            <div class="f-desc">重要日子</div>
          </div>
          <div class="card feature" @click="$router.push('/memory')">
            <div class="f-icon"><el-icon><Collection /></el-icon></div>
            <div class="f-label">经验记忆</div>
            <div class="f-desc">智能沉淀</div>
          </div>
          <div class="card feature" @click="$router.push('/profile')">
            <div class="f-icon"><el-icon><User /></el-icon></div>
            <div class="f-label">个人资料</div>
            <div class="f-desc">账号信息</div>
          </div>
        </div>
      </div>

      <!-- 右列：今日概况 + 最近记录 + Agent 提醒 -->
      <div class="dash-right">
        <div class="card overview">
          <h3>今日概况</h3>
          <div class="ov-grid">
            <div class="ov-cell">
              <span class="ov-label">本周消费</span>
              <span class="ov-value">¥{{ weekSpent }}</span>
            </div>
            <div class="ov-cell">
              <span class="ov-label">已存笔记</span>
              <span class="ov-value">{{ noteCount }} 篇</span>
            </div>
            <div class="ov-cell">
              <span class="ov-label">记账笔数</span>
              <span class="ov-value">{{ expenseCount }} 笔</span>
            </div>
            <div class="ov-cell">
              <span class="ov-label">今日喝水</span>
              <span class="ov-value">{{ waterCount }} 杯</span>
            </div>
            <div class="ov-cell">
              <span class="ov-label">待办进度</span>
              <span class="ov-value">{{ doneTodos }}/{{ todos.length }}</span>
            </div>
            <div class="ov-cell clickable" @click="openNotifs">
              <span class="ov-label">未读提醒 <span v-if="unreadNotifs" class="mini-dot">{{ unreadNotifs }}</span></span>
              <span class="ov-value">{{ unreadNotifs ? '查看' : '无' }}</span>
            </div>
          </div>
        </div>

        <!-- Agent 提醒：放在最近记录上面，只展示最近 2 条 -->
        <div class="card notif-card">
          <div class="nc-head">
            <span class="nc-title">🔔 Agent 提醒</span>
            <span v-if="unreadNotifs" class="mini-dot">{{ unreadNotifs }} 条未读</span>
            <span class="nc-spacer"></span>
            <el-button size="small" text type="primary" @click="openNotifs">查看全部</el-button>
          </div>
          <div v-if="!notifs.length" class="todo-empty">暂无提醒，Agent 会在重要时刻通知你</div>
          <div v-for="n in notifs.slice(0, 2)" :key="n.id" class="nc-item" :class="{ unread: !n.read }" @click="viewNotif(n)">
            <span class="nc-dot" :class="{ unread: !n.read }"></span>
            <div class="nc-body">
              <div class="nc-title2">{{ n.title }}</div>
              <div class="nc-text">{{ n.body }}</div>
            </div>
            <span class="nc-time">{{ formatShort(n.time) }}</span>
          </div>
        </div>

        <div class="card recent-card">
          <div class="rc-head">
            <h3>最近记录</h3>
            <el-button size="small" text type="primary" @click="$router.push('/accounting')">去记账</el-button>
          </div>
          <div v-if="!recentExpenses.length" class="todo-empty">暂无记录，记一笔开始吧</div>
          <div v-for="r in recentExpenses" :key="r.id" class="recent-row">
            <span class="r-cat" :class="r.kind">{{ r.kind === 'income' ? '收入' : r.category }}</span>
            <span class="r-note">{{ r.note || '—' }}</span>
            <span class="r-time">{{ formatShort(r.time) }}</span>
            <span class="r-amt" :class="r.kind">{{ r.kind === 'income' ? '+' : '-' }}¥{{ r.amount }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="notifVisible" title="Agent 历史提醒" width="560px">
      <div style="display:flex;justify-content:flex-end;margin-bottom:10px">
        <el-button size="small" @click="readAll">全部已读</el-button>
      </div>
      <div v-if="!notifs.length" style="text-align:center;color:#9ca3af;padding:30px">暂无提醒</div>
      <div v-for="n in notifs" :key="n.id" class="notif-full" @click="markRead(n)" style="cursor:pointer">
        <div class="nf-head">
          <span class="nf-title">{{ n.title }}<span v-if="!n.read" class="mini-dot">新</span></span>
          <span class="nf-time">{{ formatDateTime(n.time) }}</span>
        </div>
        <div class="nf-body">{{ n.body }}</div>
        <el-button size="small" text type="danger" @click.stop="delNotif(n.id)">删除</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/request'
import { syncLife } from '../api/sync'
import { useRunStore } from '../stores/run'
import { Notebook, Plus, Finished, Pointer, EditPen, Coffee, Wallet, Calendar, Collection, User } from '@element-plus/icons-vue'
import { formatDateTime, formatShort } from '../utils/format'

const router = useRouter()
const run = useRunStore()

const noteCount = ref(0)
const weekSpent = ref('0.00')
const expenseCount = ref(0)
const recentExpenses = ref([])
const todos = ref([])
const waterCount = ref(0)
const doneTodos = computed(() => todos.value.filter(t=>t.done).length)
const summary = ref('')
const summarizing = ref(false)
const syncing = ref(false)
const notifs = ref([])
const notifVisible = ref(false)
const unreadNotifs = computed(() => notifs.value.filter(n=>!n.read).length)
const conversations = ref([])
const anniv = ref([])
const habits = ref([])
const savings = ref([])

function daysLeft(a) {
  const now = new Date(); now.setHours(0, 0, 0, 0)
  const [m, d] = a.event_date.split('-').map(Number)
  let target = new Date(now.getFullYear(), m - 1, d)
  if (target < now) target = new Date(now.getFullYear() + 1, m - 1, d)
  return Math.ceil((target - now) / 86400000)
}

// 今日行动聚合：待办截止/纪念日倒计时/习惯打卡/喝水/存钱，全部可点跳转
const actions = computed(() => {
  const out = []
  const now = new Date()
  for (const t of todos.value.filter(x => !x.done).slice(0, 3)) {
    if (t.due_at) {
      const due = new Date(t.due_at)
      const todayEnd = new Date(); todayEnd.setHours(23, 59, 59, 999)
      if (due <= todayEnd) out.push({ icon: '⏰', text: t.text, sub: '已到截止时间', link: '/todo', urgent: true })
      else out.push({ icon: '📌', text: t.text, sub: '待办', link: '/todo' })
    } else {
      out.push({ icon: '📌', text: t.text, sub: '未完成待办', link: '/todo' })
    }
  }
  for (const a of anniv.value) {
    const d = daysLeft(a)
    if (d <= 3) out.push({ icon: '🎂', text: a.name, sub: d === 0 ? '就是今天！' : `还有 ${d} 天`, link: '/anniversary', urgent: d <= 1 })
  }
  for (const h of habits.value) {
    if (!h.checked_today) out.push({ icon: h.icon || '🏃', text: `打卡：${h.name}`, sub: '今天还没完成', link: '/habit' })
  }
  if (waterCount.value < 8) out.push({ icon: '💧', text: `还差 ${8 - waterCount.value} 杯水`, sub: `今日已喝 ${waterCount.value} 杯`, link: '/water' })
  for (const g of savings.value) {
    const days = Math.ceil((new Date(g.deadline) - now) / 86400000)
    if (days >= 0 && days <= 7 && g.saved_amount < g.target_amount) {
      const need = Math.max(0, g.target_amount - g.saved_amount)
      out.push({ icon: '💰', text: `每天存 ¥${(need / Math.max(days, 1)).toFixed(0)}`, sub: `「${g.purpose}」还差 ¥${need.toFixed(0)}`, link: '/savings' })
    }
  }
  return out.slice(0, 4)
})

function loadTodos(){ todos.value = JSON.parse(localStorage.getItem('lifeagent_todos') || '[]') }
function loadConvs(){ conversations.value = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]') }
function openChat(c){ run.loadConversation(c); router.push('/chat') }
function toggleTodo(i){ todos.value[i].done = !todos.value[i].done; localStorage.setItem('lifeagent_todos', JSON.stringify(todos.value)) }

async function doSync(){
  syncing.value = true
  await syncLife()
  syncing.value = false
  loadTodos()
}

async function genSummary(){  summarizing.value = true
  try {
    const payload = {
      todos: JSON.parse(localStorage.getItem('lifeagent_todos') || '[]'),
      expenses: JSON.parse(localStorage.getItem('lifeagent_expenses') || '[]'),
      anniversaries: JSON.parse(localStorage.getItem('lifeagent_anniv') || '[]'),
      habits: JSON.parse(localStorage.getItem('lifeagent_habits') || '{}'),
      water: waterCount.value,
      savings: JSON.parse(localStorage.getItem('lifeagent_savings') || '{}')
    }
    const { data } = await api.post('/summary/today', payload)
    summary.value = data.summary
  } catch(e) { summary.value = '生成失败：' + (e.response?.data?.detail || e.message) }
  summarizing.value = false
}

onMounted(async () => {
  loadTodos()
  loadConvs()
  // 先读上次缓存的统计
  const cached = JSON.parse(localStorage.getItem('lifeagent_stats') || '{}')
  if(cached.noteCount != null) noteCount.value = cached.noteCount
  if(cached.weekSpent) weekSpent.value = cached.weekSpent
  if(cached.expenseCount != null) expenseCount.value = cached.expenseCount
  if(cached.recentExpenses) recentExpenses.value = cached.recentExpenses
  // 通知先读本地缓存
  notifs.value = JSON.parse(localStorage.getItem('lifeagent_notifs') || '[]')
  const todayISO = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` })()
  const tasks = [
    api.get('/life/water').then(r => {
      const w = r.data.find(x => x.date === todayISO)
      waterCount.value = w ? w.cups : 0
    }).catch(()=>{}),
    api.get('/notes/stats').then(r => noteCount.value = r.data.note_count).catch(()=>{}),
    api.get('/life/expenses').then(r => {
      const exps = r.data
      // 本周（周一起）支出合计——每周一自动滚动清零，不会累计
      const weekStart = new Date(); weekStart.setHours(0, 0, 0, 0); weekStart.setDate(weekStart.getDate() - (weekStart.getDay() || 7) + 1)
      weekSpent.value = exps.filter(e => e.kind !== 'income' && new Date(e.time) >= weekStart).reduce((s, r) => s + Number(r.amount), 0).toFixed(2)
      expenseCount.value = exps.length
      // 最近 5 条：支出和收入都显示
      recentExpenses.value = exps.slice(0, 5)
      localStorage.setItem('lifeagent_stats', JSON.stringify({ noteCount: noteCount.value, weekSpent: weekSpent.value, expenseCount: expenseCount.value, recentExpenses: recentExpenses.value }))
    }).catch(()=>{}),
    api.get('/notify/list').then(r => {
      notifs.value = r.data
      localStorage.setItem('lifeagent_notifs', JSON.stringify(r.data))
    }).catch(()=>{}),
    api.get('/life/anniversaries').then(r => anniv.value = r.data).catch(()=>{}),
    api.get('/life/habits').then(r => habits.value = r.data).catch(()=>{}),
    api.get('/life/savings').then(r => savings.value = r.data).catch(()=>{}),
    syncLife()
  ]
  await Promise.all(tasks)
})

async function delNotif(id){
  await api.delete(`/notify/${id}`)
  notifs.value = notifs.value.filter(n=>n.id!==id)
  localStorage.setItem('lifeagent_notifs', JSON.stringify(notifs.value))
}
async function markRead(n){
  if(n.read) return
  await api.post(`/notify/read/${n.id}`)
  n.read = 1
  localStorage.setItem('lifeagent_notifs', JSON.stringify(notifs.value))
  window.dispatchEvent(new Event('notify-updated'))
}
async function readAll(){
  await api.post('/notify/read-all')
  notifs.value.forEach(n=>n.read=1)
  localStorage.setItem('lifeagent_notifs', JSON.stringify(notifs.value))
  window.dispatchEvent(new Event('notify-updated'))
}
function viewNotif(n){
  notifVisible.value = true
  markRead(n)
}
async function openNotifs(){
  notifVisible.value = true
  try {
    notifs.value = (await api.get('/notify/list')).data
    localStorage.setItem('lifeagent_notifs', JSON.stringify(notifs.value))
  } catch {}
}
</script>

<style scoped>
.home { width: 100%; height: 100%; display: flex; flex-direction: column; overflow: hidden; }

/* 头部（紧凑一行） */
.home-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-shrink: 0; }
.page-title { font-size: 22px; font-weight: 700; color: #111827; margin: 0; }
.head-actions { display: flex; gap: 8px; }

.summary-result {
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
  border: 1px solid #dbeafe; border-radius: 12px; padding: 10px 16px;
  font-size: 13px; line-height: 1.7; color: #1f2937;
  margin-bottom: 12px; white-space: pre-wrap;
  max-height: 76px; overflow: auto; flex-shrink: 0;
}

/* 主面板：一屏内铺满 */
.dashboard { flex: 1; display: grid; grid-template-columns: 1fr 320px; gap: 14px; min-height: 0; }
.dash-left { display: flex; flex-direction: column; gap: 12px; min-height: 0; min-width: 0; }
.dash-right { display: flex; flex-direction: column; gap: 12px; min-height: 0; }

/* 今日行动（紧凑） */
.today-card {
  background: #fff; border-radius: 12px; padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.04); border: 1px solid #eef0f3; flex-shrink: 0;
}
.tc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.tc-title { font-size: 14px; font-weight: 700; color: #111827; }
.tc-count { font-size: 11px; color: #6b7280; background: #f3f4f6; padding: 2px 10px; border-radius: 10px; }
.tc-empty { color: #9ca3af; font-size: 13px; text-align: center; padding: 10px 0; }
.tc-item { display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 8px; cursor: pointer; transition: all .15s; }
.tc-item:hover { background: #f9fafb; }
.tc-item.urgent { background: #fef2f2; }
.tc-item.urgent:hover { background: #fee2e2; }
.tc-icon { font-size: 16px; flex-shrink: 0; }
.tc-body { flex: 1; min-width: 0; }
.tc-text { font-size: 13px; color: #111827; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tc-item.urgent .tc-text { color: #b91c1c; }
.tc-sub { font-size: 11px; color: #6b7280; }
.tc-go { font-size: 12px; color: #2563eb; flex-shrink: 0; }

/* 功能入口 2×5（桌面双列布局下左列窄，2 列格子更宽不挤） */
.feature-grid { flex: 1; display: grid; grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(5, 1fr); gap: 10px; min-height: 0; }
.card {
  background: #fff; border-radius: 12px; padding: 10px 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
  display: flex; flex-direction: column;
  cursor: pointer; border: 1px solid #eef0f3; transition: all .15s;
}
.card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.07); border-color: #dbeafe; }
.card.feature { align-items: center; justify-content: center; gap: 8px; }
.card.feature.primary { border-color: #2563eb; background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); }
.f-icon {
  width: 56px; height: 56px; border-radius: 14px;
  background: #2563eb; color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 28px;
}
.f-icon :deep(svg) { width: 28px; height: 28px; }
.f-label { font-size: 15px; font-weight: 600; color: #111827; }
.f-desc { font-size: 13px; color: #9ca3af; white-space: nowrap; }

/* 右列卡片 */
.overview { padding: 14px 16px; flex-shrink: 0; }
.overview h3 { margin: 0 0 10px; font-size: 14px; color: #111827; }
.ov-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.ov-cell { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; background: #f9fafb; border-radius: 10px; }
.ov-cell.clickable { cursor: pointer; }
.ov-cell.clickable:hover { background: #eef2ff; }
.ov-label { font-size: 11px; color: #6b7280; }
.ov-value { font-size: 17px; font-weight: 700; color: #111827; }
.mini-dot { background: #ef4444; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 4px; }

.recent-card { padding: 14px 16px; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.rc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.rc-head h3 { margin: 0; font-size: 14px; color: #111827; }
.recent-row { display: flex; align-items: center; gap: 8px; padding: 11px 0; border-bottom: 1px solid #f3f4f6; font-size: 13px; }
.recent-row:last-child { border: none; }
.r-cat { width: 52px; text-align: center; background: #eff6ff; color: #2563eb; padding: 1px 0; border-radius: 8px; font-size: 11px; flex-shrink: 0; }
.r-cat.income { background: #ecfdf5; color: #059669; }
.r-note { flex: 1; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.r-time { width: 76px; text-align: right; font-size: 11px; color: #9ca3af; flex-shrink: 0; }
.r-amt { width: 78px; text-align: right; color: #ef4444; font-weight: 600; flex-shrink: 0; }
.r-amt.income { color: #059669; }
.todo-empty { color: #9ca3af; font-size: 13px; text-align: center; padding: 20px 0; }

/* Agent 提醒卡片（右列） */
.notif-card { padding: 14px 16px; flex-shrink: 0; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.nc-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.nc-title { font-size: 14px; font-weight: 700; color: #111827; white-space: nowrap; }
.nc-spacer { flex: 1; }
.nc-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 10px; background: #f9fafb; cursor: pointer; min-width: 0; overflow: hidden; }
.nc-item:hover { background: #eef2ff; }
.nc-item.unread { background: #eff6ff; }
.nc-dot { width: 8px; height: 8px; border-radius: 50%; background: #d1d5db; flex-shrink: 0; }
.nc-dot.unread { background: #2563eb; }
.nc-body { flex: 1; min-width: 0; }
.nc-title2 { font-size: 13px; font-weight: 600; color: #111827; }
.nc-text { font-size: 12px; color: #4b5563; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nc-time { font-size: 11px; color: #9ca3af; flex-shrink: 0; }

/* 通知弹窗 */
.notif-full { padding: 12px 0; border-bottom: 1px solid #f0f1f3; }
.notif-full:last-child { border: none; }
.nf-head { display: flex; justify-content: space-between; align-items: center; }
.nf-title { font-weight: 600; color: #111; font-size: 14px; }
.nf-time { font-size: 11px; color: #9ca3af; }
.nf-body { margin: 8px 0; color: #374151; font-size: 13px; line-height: 1.7; white-space: pre-wrap; }

/* 窄屏退回可滚动 */
@media (max-width: 900px) {
  .home { overflow: auto; height: auto; min-height: 100%; }
  .dashboard { grid-template-columns: 1fr; }
  .feature-grid { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 118px); }
  .recent-card { flex: none; }
}
@media (max-width: 600px) {
  .feature-grid { grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(5, 118px); }
  .head-actions { gap: 4px; }
}
</style>

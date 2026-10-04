<template>
  <div class="layout">
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="logo"><span class="logo-dot"></span><span class="logo-text">Life Agent</span></div>
      <nav class="nav">
        <div class="nav-group">核心</div>
        <router-link to="/home" class="nav-item">
          <span class="nav-icon">🏠</span><span>首页</span>
          <span v-if="unread" class="nav-badge">{{ unread }}</span>
        </router-link>
        <router-link to="/chat" class="nav-item">
          <span class="nav-icon">💬</span><span>对话助手</span>
        </router-link>
        <div class="nav-group">生活管理</div>
        <router-link to="/accounting" class="nav-item"><span class="nav-icon">💰</span><span>记账</span></router-link>
        <router-link to="/todo" class="nav-item"><span class="nav-icon">✅</span><span>待办</span></router-link>
        <router-link to="/habit" class="nav-item"><span class="nav-icon">🏃</span><span>习惯</span></router-link>
        <router-link to="/diary" class="nav-item"><span class="nav-icon">📔</span><span>日记</span></router-link>
        <router-link to="/water" class="nav-item"><span class="nav-icon">💧</span><span>喝水</span></router-link>
        <router-link to="/savings" class="nav-item"><span class="nav-icon">🎯</span><span>存钱</span></router-link>
        <router-link to="/anniversary" class="nav-item"><span class="nav-icon">🎂</span><span>纪念日</span></router-link>
        <div class="nav-group">智能中心</div>
        <router-link to="/notes" class="nav-item"><span class="nav-icon">📚</span><span>我的资料</span></router-link>
        <router-link to="/memory" class="nav-item"><span class="nav-icon">🧠</span><span>经验记忆</span></router-link>
        <router-link to="/history" class="nav-item"><span class="nav-icon">📜</span><span>历史对话</span></router-link>
        <router-link to="/graph" class="nav-item"><span class="nav-icon">🔀</span><span>Agent 链路</span></router-link>
      </nav>
      <div class="sidebar-history">
        <div class="sh-title">最近对话 <router-link to="/history" class="sh-all">全部</router-link></div>
        <div v-if="!convs.length" class="sh-empty">暂无</div>
        <div v-for="c in convs.slice(0,5)" :key="c.id" class="sh-item" :class="{new: newConvIds.has(c.id)}" @click="openConv(c)">
          <div class="sh-item-title">{{ c.title }}</div>
          <span v-if="newConvIds.has(c.id)" class="new-dot"></span>
          <span class="sh-del" @click.stop="delConv(c.id)">×</span>
        </div>
      </div>
      <div class="sidebar-footer" v-if="auth.user">
        <span class="user-avatar" :style="{background: profile.avatarColor || '#e5e7eb'}">{{ profile.nickname ? profile.nickname.slice(0,1).toUpperCase() : 'U' }}</span>
        <span class="user-name">{{ profile.nickname || auth.user }}</span>
        <el-button size="small" text @click="logout">退出</el-button>
      </div>
    </aside>
    <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>
    <div class="main">
      <header class="topbar">
        <div class="top-left">
          <el-button class="menu-btn" text :icon="Menu" @click="sidebarOpen = true"></el-button>
          <el-button v-if="!isHome" text :icon="ArrowLeft" @click="router.back()">返回</el-button>
          <span class="crumb">Life Agent</span>
        </div>
        <div class="top-actions">
          <el-icon><Setting /></el-icon>
        </div>
      </header>
      <main class="content"><router-view /></main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useRunStore } from './stores/run'
import { Setting, ArrowLeft, Menu } from '@element-plus/icons-vue'
import api from './api/request'
import { listConversations, getConversation, deleteConversation } from './api/conversations'
const auth = useAuthStore()
const router = useRouter()
const run = useRunStore()
const route = useRoute()
const isHome = computed(() => route.path === '/home' || route.path === '/')
const profile = ref(JSON.parse(localStorage.getItem('lifeagent_profile') || '{}'))
const unread = ref(0)
const convs = ref([])
const newConvIds = ref(new Set())
const sidebarOpen = ref(false)
let timer = null

// 会话列表：云端优先，本地 localStorage 兜底（离线/后端不可用时）
async function loadConvs() {
  const local = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]')
  // 未登录时不要发 API 请求：会触发 401→refresh 失败→强制跳登录的死循环
  if (!localStorage.getItem('access_token')) { convs.value = local; return }
  try {
    const { data } = await listConversations()
    const localById = new Map(local.map(c => [String(c.id), c]))
    const server = data.map(c => {
      const l = localById.get(String(c.id))
      return { id: String(c.id), title: c.title, preview: c.preview, time: c.time, messages: l?.messages || [] }
    })
    const serverIds = new Set(server.map(c => c.id))
    const extra = local.filter(c => !serverIds.has(c.id))
    convs.value = [...server, ...extra]
    localStorage.setItem('lifeagent_conversations', JSON.stringify(convs.value.slice(0, 50)))
  } catch {
    convs.value = local
  }
}
async function openConv(c) {
  newConvIds.value.delete(c.id)
  // 本地没有消息全文时（云端列表不带 messages），拉取单条
  if (!c.messages || !c.messages.length) {
    try {
      const { data } = await getConversation(c.id)
      c = { ...c, ...data, id: String(data.id) }
    } catch {}
  }
  run.loadConversation(c); router.push('/chat')
}
async function delConv(id) {
  try { await deleteConversation(id) } catch {}
  const arr = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]').filter(x => x.id !== id)
  localStorage.setItem('lifeagent_conversations', JSON.stringify(arr))
  loadConvs()
}

async function pollUnread(){
  // token 不存在就不发请求，避免 401 触发刷新死循环
  if(!localStorage.getItem('access_token')) return
  try { unread.value = (await api.get('/notify/unread')).data.count } catch {}
}

// —— 浏览器通知推送：轮询新通知，系统级弹出 ——
const seenNotifIds = new Set()
let notifReady = false
let notifPermRequested = false

function requestNotifPermission() {
  if (notifPermRequested || !('Notification' in window)) return
  notifPermRequested = true
  Notification.requestPermission().catch(() => {})
}

async function pollNotifs() {
  if (!localStorage.getItem('access_token')) return
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  try {
    const { data } = await api.get('/notify/list')
    // 首次拉取只建立"已见"基线，不推送旧通知
    if (!notifReady) {
      data.forEach(n => seenNotifIds.add(n.id))
      notifReady = true
      return
    }
    data.forEach(n => {
      if (seenNotifIds.has(n.id)) return
      seenNotifIds.add(n.id)
      try { new Notification(n.title || 'Life Agent', { body: n.body || '' }) } catch {}
    })
  } catch {}
}

onMounted(() => { pollUnread(); loadConvs(); pollNotifs(); timer = setInterval(() => { pollUnread(); loadConvs(); pollNotifs() }, 10000); window.addEventListener('notify-updated', pollUnread); window.addEventListener('conversations-updated', loadConvs); window.addEventListener('new-reply', e => { if(e.detail?.id) newConvIds.value.add(e.detail.id) }); window.addEventListener('click', requestNotifPermission, { once: true }) })
onUnmounted(() => { clearInterval(timer); window.removeEventListener('notify-updated', pollUnread); window.removeEventListener('conversations-updated', loadConvs); window.removeEventListener('click', requestNotifPermission) })
watch(() => route.path, p => { if (p === '/chat') newConvIds.value = new Set(); sidebarOpen.value = false })
function logout() { auth.logout(); router.push('/login') }
</script>

<style scoped>
.layout { display: flex; height: 100vh; background: #f3f5f9; }
.sidebar { width: 232px; background: #fff; border-right: 1px solid #eaecef; display: flex; flex-direction: column; padding: 20px 14px; box-sizing: border-box; }
.logo { display: flex; align-items: center; gap: 10px; padding: 4px 10px 24px; }
.logo-dot { width: 26px; height: 26px; border-radius: 50%; background: #2563eb; }
.logo-text { font-size: 17px; font-weight: 700; color: #111827; }
.nav { display: flex; flex-direction: column; gap: 2px; }
.nav-group { font-size: 11px; color: #9ca3af; font-weight: 600; padding: 14px 14px 4px; letter-spacing: .5px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 9px 14px; border-radius: 10px; color: #4b5563; text-decoration: none; font-size: 14px; transition: all .15s; }
.nav-item:hover { background: #f3f4f6; }
.nav-item.router-link-active { background: #eff6ff; color: #2563eb; font-weight: 600; }
.nav-icon { width: 20px; text-align: center; }
.nav-badge {
  margin-left: auto; background: #ef4444; color: #fff;
  font-size: 11px; min-width: 18px; height: 18px;
  border-radius: 9px; display: flex; align-items: center; justify-content: center;
  padding: 0 5px;
}
.sidebar-history { padding: 12px 10px; border-top: 1px solid #f0f1f3; margin-top: 8px; overflow: auto; flex: 1; min-height: 0; }
.sh-title { font-size: 12px; color: #9ca3af; margin-bottom: 8px; font-weight: 600; display: flex; align-items: center; justify-content: space-between; }
.sh-all { font-size: 12px; color: #2563eb; text-decoration: none; font-weight: 500; }
.sh-all:hover { text-decoration: underline; }
.sh-empty { font-size: 12px; color: #d1d5db; text-align: center; padding: 8px; }
.sh-item { padding: 7px 10px; border-radius: 8px; cursor: pointer; font-size: 13px; color: #4b5563; display: flex; align-items: center; justify-content: space-between; }
.sh-item:hover { background: #f3f4f6; color: #2563eb; }
.sh-item-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.sh-del { color: #d1d5db; font-size: 16px; padding: 0 4px; line-height: 1; }
.sh-del:hover { color: #ef4444; }
.new-dot { width: 8px; height: 8px; border-radius: 50%; background: #ef4444; flex-shrink: 0; }
.sidebar-footer { display: flex; align-items: center; gap: 8px; padding: 12px 10px 0; border-top: 1px solid #f0f1f3; }
.user-avatar { width: 30px; height: 30px; border-radius: 50%; background: #e5e7eb; display: flex; align-items: center; justify-content: center; font-size: 13px; color: #374151; }
.user-name { flex: 1; font-size: 13px; color: #374151; }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar { height: 56px; background: #fff; border-bottom: 1px solid #eaecef; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; }
.top-left { display: flex; align-items: center; gap: 12px; }
.crumb { font-size: 15px; font-weight: 600; color: #111827; }
.top-actions { display: flex; gap: 18px; color: #6b7280; font-size: 18px; align-items: center; }
.content { flex: 1; overflow: auto; padding: 24px; height: 0; }

/* —— 移动端适配：侧边栏折叠为抽屉 —— */
.menu-btn { display: none; }
.sidebar-mask { display: none; }
@media (max-width: 768px) {
  .menu-btn { display: inline-flex !important; }
  .sidebar {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 100;
    transform: translateX(-100%); transition: transform .22s ease;
    box-shadow: 4px 0 16px rgba(0,0,0,.08);
  }
  .sidebar.open { transform: translateX(0); }
  .sidebar-mask { display: block; position: fixed; inset: 0; background: rgba(17,24,39,.4); z-index: 90; }
  .topbar { padding: 0 14px; }
  .content { padding: 14px; }
}
</style>

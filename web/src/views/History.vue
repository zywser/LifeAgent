<template>
  <div class="history-page">
    <div class="page-head">
      <h2>历史对话</h2>
      <span class="sub">共 {{ list.length }} 条会话</span>
    </div>

    <div v-if="!list.length" class="empty">
      <div class="empty-icon">🗂️</div>
      <h3>还没有历史对话</h3>
      <p>去对话助手发一条消息，这里会自动保存</p>
      <el-button type="primary" @click="goChat">开始对话</el-button>
    </div>

    <div v-else class="grid">
      <div v-for="c in pagedList" :key="c.id" class="card" :class="{new: isNew(c)}" @click="open(c)">
        <div class="card-top">
          <div class="card-title">
            {{ c.title }}
            <span v-if="isNew(c)" class="new-dot">新</span>
          </div>
          <el-button size="small" text type="danger" @click.stop="remove(c.id)">删除</el-button>
        </div>
        <div class="card-preview">{{ c.preview }}</div>
        <div class="card-meta">
          <span>{{ formatRelative(c.time) }}</span>
          <span>{{ (c.message_count ?? c.messages.length) }} 条消息</span>
        </div>
      </div>
    </div>
    <el-pagination v-if="list.length > pageSize" :total="list.length" :page-size="pageSize"
      :current-page="page" layout="prev, pager, next" class="pager"
      @current-change="p => page = p" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useRunStore } from '../stores/run'
import { formatRelative } from '../utils/format'
import { listConversations, getConversation, deleteConversation } from '../api/conversations'

const router = useRouter()
const run = useRunStore()
const list = ref([])
const lastView = ref(Number(localStorage.getItem('lifeagent_history_viewed') || 0))
// 分页：10 条/页
const page = ref(1)
const pageSize = 10
const pagedList = computed(() => list.value.slice((page.value - 1) * pageSize, page.value * pageSize))

function isNew(c){ return new Date(c.time).getTime() > lastView.value }

// 云端优先，本地兜底
async function load() {
  // 过滤掉历史遗留的"新对话"占位（非数字 id 且空消息）
  const local = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]')
    .filter(c => /^\d+$/.test(String(c.id)) || (c.messages && c.messages.length))
  try {
    const { data } = await listConversations()
    const localById = new Map(local.map(c => [String(c.id), c]))
    list.value = data.map(c => ({
      id: String(c.id), title: c.title, preview: c.preview, time: c.time,
      message_count: c.message_count,
      messages: localById.get(String(c.id))?.messages || []
    }))
  } catch {
    list.value = local
  }
}
onMounted(async () => {
  await load()
  // 进历史页就把所有都标为已读
  localStorage.setItem('lifeagent_history_viewed', String(Date.now()))
  lastView.value = Date.now()
})

// 对话助手入口：回答进行中切回现场，平时默认新对话（不残留历史会话内容）
function goChat() {
  if (run._round) { router.push('/chat'); return }
  run.newChat(); router.push('/chat')
}

async function open(c) {  if (!c.messages || !c.messages.length) {
    try {
      const { data } = await getConversation(c.id)
      c = { ...c, ...data, id: String(data.id) }
    } catch {}
  }
  // 回答进行中且点击的正是发起会话：store 已是最新现场，直接切回，避免覆盖丢失进行中的用户消息
  if (run._round?.id && String(c.id) === String(run._round.id)) {
    router.push(`/chat/s/${c.id}`); return
  }
  // 回答进行中也可切换其他会话：进行中的回答由 round 上下文接管，完成时保存回原会话
  run.loadConversation(c)
  // 每个历史会话独立路由（豆包/DeepSeek 式）；无数字 id 的本地占位走 /chat
  router.push(c.id && /^\d+$/.test(String(c.id)) ? `/chat/s/${c.id}` : '/chat')
}
async function remove(id) {
  // 云端会话（数字 id）调 DELETE；本地占位 id（非数字）只删本地，避免 422
  if (/^\d+$/.test(String(id))) {
    try { await deleteConversation(id) } catch {}
  }
  const arr = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]')
  localStorage.setItem('lifeagent_conversations', JSON.stringify(arr.filter(x => x.id !== id)))
  load()
}
</script>

<style scoped>
.history-page { max-width: 1100px; margin: 0 auto; width: 100%; }
.page-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 20px; }
.page-head h2 { margin: 0; font-size: 20px; color: var(--text); }
.sub { color: var(--text-3); font-size: 13px; }
.empty { text-align: center; padding: 80px 0; color: var(--text-2); }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty h3 { margin: 8px 0; color: var(--text); }
.empty p { font-size: 13px; margin-bottom: 16px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card {
  background: var(--card); border-radius: 12px; padding: 16px;
  cursor: pointer; transition: all .15s; border: 1px solid var(--border);
}
.card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.06); transform: translateY(-2px); border-color: var(--primary-border); }
.card.new { border-color: #f59e0b; background: rgba(245,158,11,.12); }
.new-dot { background: #ef4444; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px; }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.card-title {
  font-size: 14px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.card-preview {
  font-size: 13px; color: var(--text-2); margin: 10px 0; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.card-meta { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-3); }
.pager { display: flex; justify-content: center; padding: 20px 0 0; }
</style>

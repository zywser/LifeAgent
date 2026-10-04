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
      <el-button type="primary" @click="$router.push('/chat')">开始对话</el-button>
    </div>

    <div v-else class="grid">
      <div v-for="c in list" :key="c.id" class="card" :class="{new: isNew(c)}" @click="open(c)">
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useRunStore } from '../stores/run'
import { formatRelative } from '../utils/format'
import { listConversations, getConversation, deleteConversation } from '../api/conversations'

const router = useRouter()
const run = useRunStore()
const list = ref([])
const lastView = ref(Number(localStorage.getItem('lifeagent_history_viewed') || 0))

function isNew(c){ return new Date(c.time).getTime() > lastView.value }

// 云端优先，本地兜底
async function load() {
  const local = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]')
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

async function open(c) {
  if (!c.messages || !c.messages.length) {
    try {
      const { data } = await getConversation(c.id)
      c = { ...c, ...data, id: String(data.id) }
    } catch {}
  }
  run.loadConversation(c)
  router.push('/chat')
}
async function remove(id) {
  try { await deleteConversation(id) } catch {}
  const arr = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]')
  localStorage.setItem('lifeagent_conversations', JSON.stringify(arr.filter(x => x.id !== id)))
  load()
}
</script>

<style scoped>
.history-page { max-width: 1100px; margin: 0 auto; width: 100%; }
.page-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 20px; }
.page-head h2 { margin: 0; font-size: 20px; color: #111827; }
.sub { color: #9ca3af; font-size: 13px; }
.empty { text-align: center; padding: 80px 0; color: #6b7280; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty h3 { margin: 8px 0; color: #111827; }
.empty p { font-size: 13px; margin-bottom: 16px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card {
  background: #fff; border-radius: 12px; padding: 16px;
  cursor: pointer; transition: all .15s; border: 1px solid #eef0f3;
}
.card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.06); transform: translateY(-2px); border-color: #dbeafe; }
.card.new { border-color: #f59e0b; background: #fffbeb; }
.new-dot { background: #ef4444; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px; }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.card-title {
  font-size: 14px; font-weight: 600; color: #111827;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.card-preview {
  font-size: 13px; color: #6b7280; margin: 10px 0; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.card-meta { display: flex; justify-content: space-between; font-size: 12px; color: #9ca3af; }
</style>

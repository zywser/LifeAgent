<template>
  <div class="page">
    <h2>经验记忆</h2>
    <p class="hint">这是 Life Agent 从你过往对话、日记中自动沉淀的长期经验，会在下次对话时作为参考。</p>

    <div class="card">
      <div class="row"><span class="k">记忆条目</span><span class="v">{{ count }} 条</span></div>
      <div class="row"><span class="k">来源</span><span class="v">对话 / 日记 自动沉淀</span></div>
    </div>

    <div v-if="!items.length" class="empty">
      <div>🧠</div>
      <p>还没有沉淀任何经验。多和助手对话、多写日记，它会自动记住你的偏好和习惯。</p>
    </div>

    <div v-else class="list">
      <div v-for="it in items" :key="it.id" class="item">
        <div class="it-head">
          <span class="it-kind" :class="it.kind">{{ it.kind === 'diary' ? '📔 日记' : '💬 对话' }}</span>
          <span class="it-time">{{ formatDateTime(it.time) }}</span>
          <el-button size="small" text type="danger" @click="del(it.id)">删除</el-button>
        </div>
        <div class="it-content">{{ it.content }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api/request'
import { formatDateTime } from '../utils/format'

const items = ref([])
const count = ref(0)

async function load() {
  try {
    const { data } = await api.get('/memory/list')
    items.value = data.items || []
    count.value = data.count || 0
  } catch {
    items.value = []
    count.value = 0
  }
}
async function del(id) {
  try { await api.delete(`/memory/${id}`) } catch {}
  load()
}
onMounted(load)
</script>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; width: 100%; }
h2 { font-size: 20px; margin: 0 0 8px; }
.hint { color: #6b7280; font-size: 13px; margin-bottom: 16px; }
.card { background: #fff; border-radius: 12px; padding: 8px 20px; margin-bottom: 16px; }
.row { display: flex; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid #f3f4f6; font-size: 14px; }
.row:last-child { border: none; }
.k { color: #6b7280; }
.v { color: #111827; font-weight: 500; }
.empty { text-align: center; color: #9ca3af; padding: 40px; font-size: 14px; }
.empty > div { font-size: 40px; margin-bottom: 8px; }
.list { display: flex; flex-direction: column; gap: 10px; }
.item { background: #fff; border-radius: 12px; padding: 14px 18px; }
.it-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.it-kind { font-size: 12px; padding: 2px 10px; border-radius: 10px; background: #eff6ff; color: #2563eb; }
.it-kind.diary { background: #fef3c7; color: #b45309; }
.it-time { font-size: 12px; color: #9ca3af; flex: 1; }
.it-content { font-size: 13px; color: #374151; line-height: 1.7; white-space: pre-wrap; }
</style>

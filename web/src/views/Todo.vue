<template>
  <div class="page">
    <div class="head">
      <h2>待办清单</h2>
      <span class="sub">{{ doneCount }}/{{ list.length }} 已完成</span>
    </div>
    <div class="form-card">
      <el-input v-model="newTask" placeholder="要做点什么？" @keydown.enter="add" />
      <el-date-picker v-model="dueAt" type="datetime" placeholder="提醒时间（可选）"
        format="YYYY-MM-DD HH:mm" value-format="YYYY-MM-DDTHH:mm" style="width: 220px" />
      <el-button type="primary" @click="add">添加</el-button>
    </div>
    <div class="list">
      <div v-if="!list.length" class="empty">暂无待办，添加一件想做的事吧</div>
      <div v-for="t in sortedList" :key="t.id" class="row" :class="{ done: t.done, overdue: isOverdue(t) }">
        <el-checkbox :model-value="!!t.done" @change="toggle(t)" />
        <span class="txt">{{ t.text }}</span>
        <span v-if="t.due_at" class="due" :class="{ overdue: isOverdue(t) }">⏰ {{ formatDateTime(t.due_at) }}<span v-if="isOverdue(t)">（已逾期）</span></span>
        <span class="time">{{ formatDate(t.time) }}</span>
        <el-button size="small" text type="danger" @click="del(t)">删</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'
import { formatDateTime, formatDate } from '../utils/format'

const newTask = ref('')
const dueAt = ref(null)
const list = ref([])
const doneCount = computed(() => list.value.filter(t => t.done).length)

// 未完成在前、按截止时间升序；完成的沉底
const sortedList = computed(() => {
  const now = Date.now()
  return [...list.value].sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1
    const da = a.due_at ? new Date(a.due_at).getTime() : Number.MAX_SAFE_INTEGER
    const db = b.due_at ? new Date(b.due_at).getTime() : Number.MAX_SAFE_INTEGER
    return da - db
  })
})
function isOverdue(t) {
  if (t.done || !t.due_at) return false
  return new Date(t.due_at).getTime() < Date.now()
}

async function load(){ list.value = (await api.get('/life/todos')).data }
async function add(){
  const t = newTask.value.trim(); if(!t) return
  await api.post('/life/todos', { text: t, due_at: dueAt.value || null })
  newTask.value=''; dueAt.value=null
  load()
}
async function toggle(t){ await api.put(`/life/todos/${t.id}`); load() }
async function del(t){ await api.delete(`/life/todos/${t.id}`); load() }
onMounted(load)
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; width: 100%; }
.head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.head h2 { margin: 0; font-size: 20px; }
.sub { color: var(--text-2); font-size: 13px; }
.form-card { display: flex; gap: 10px; background: var(--card); padding: 16px; border-radius: 12px; margin-bottom: 16px; }
.list { background: var(--card); border-radius: 12px; padding: 8px 16px; }
.empty { text-align: center; color: var(--text-3); padding: 40px; }
.row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f3f4f6; font-size: 14px; }
.row:last-child { border: none; }
.row.overdue { background: #fef2f2; border-radius: 8px; padding-left: 10px; padding-right: 10px; }
.txt { flex: 1; }
.row.done .txt { text-decoration: line-through; color: var(--text-3); }
.due { color: #f59e0b; font-size: 12px; }
.due.overdue { color: #dc2626; font-weight: 600; }
.time { color: var(--text-3); font-size: 12px; }
</style>

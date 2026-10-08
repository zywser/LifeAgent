<template>
  <div class="page">
    <h2>每日日记</h2>
    <p class="hint">记录今天的心情，Agent 会自动生成小结</p>

    <div class="card">
      <div class="moods">
        <span v-for="m in moods" :key="m" class="mood" :class="{ sel: mood===m }" @click="mood=m">{{ m }}</span>
      </div>
      <el-input v-model="text" type="textarea" :autosize="{minRows:3}" placeholder="今天发生了什么？" />
      <div class="btn-row">
        <el-button type="primary" :loading="saving" @click="save">{{ editingId ? '保存修改' : '写下今天' }}</el-button>
        <el-button v-if="editingId" text @click="cancelEdit">取消编辑</el-button>
      </div>
    </div>

    <div v-if="trend" class="trend">
      <h3>📈 最近情绪趋势</h3>
      <p>{{ trend }}</p>
    </div>

    <div class="list">
      <div v-if="!entries.length" class="empty">还没有记录，写下今天的第一篇吧</div>
      <div v-for="e in pagedList" :key="e.id" class="entry">
        <div class="e-head">
          <span class="e-mood">{{ e.mood }}</span>
          <span class="e-date">{{ formatDateTime(e.date) }}</span>
          <span class="e-ops">
            <el-button size="small" text @click="startEdit(e)">编辑</el-button>
            <el-button size="small" text type="danger" @click="del(e)">删除</el-button>
          </span>
        </div>
        <div class="e-text">{{ e.content }}</div>
        <div v-if="e.summary" class="e-summary">✨ {{ e.summary }}</div>
      </div>
      <el-pagination v-if="entries.length > pageSize" :total="entries.length" :page-size="pageSize"
        :current-page="page" layout="prev, pager, next" small class="pager"
        @current-change="p => page = p" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'
import { formatDateTime } from '../utils/format'

const moods = ['😄','🙂','😐','😔','😡']
const mood = ref('🙂')
const text = ref('')
const saving = ref(false)
const editingId = ref(null)
const entries = ref([])
const trend = ref('')
// 分页：10 条/页
const page = ref(1)
const pageSize = 10
const pagedList = computed(() => entries.value.slice((page.value - 1) * pageSize, page.value * pageSize))

async function load(){
  entries.value = (await api.get('/life/diary')).data
  try { trend.value = (await api.get('/life/diary/mood-trend')).data.analysis } catch {}
}
async function save(){
  if(!text.value.trim() || saving.value) return
  saving.value = true
  if (editingId.value) {
    await api.put(`/life/diary/${editingId.value}`, { mood: mood.value, content: text.value })
    editingId.value = null
  } else {
    await api.post('/life/diary', { mood: mood.value, content: text.value })
  }
  text.value = ''
  mood.value = '🙂'
  saving.value = false
  page.value = 1
  load()
}
function startEdit(e) {
  editingId.value = e.id
  mood.value = e.mood
  text.value = e.content
}
function cancelEdit() {
  editingId.value = null
  text.value = ''
  mood.value = '🙂'
}
async function del(e) {
  await api.delete(`/life/diary/${e.id}`)
  if (editingId.value === e.id) cancelEdit()
  load()
}
onMounted(load)
</script>

<style scoped>
.page { max-width: 700px; margin: 0 auto; width: 100%; }
h2 { font-size: 20px; margin: 0 0 8px; }
.hint { color: var(--text-2); font-size: 13px; margin-bottom: 16px; }
.card { background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
.btn-row { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.moods { display: flex; gap: 12px; margin-bottom: 12px; }
.mood { font-size: 28px; cursor: pointer; opacity: .4; transition: all .15s; }
.mood.sel { opacity: 1; transform: scale(1.2); }
.trend { background: rgba(249,115,22,.12); border: 1px solid #fed7aa; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
.trend h3 { margin: 0 0 6px; font-size: 14px; color: #9a3412; }
.trend p { margin: 0; font-size: 13px; color: #7c2d12; line-height: 1.6; }
.list { display: flex; flex-direction: column; gap: 12px; }
.empty { text-align: center; color: var(--text-3); padding: 40px; background: var(--card); border-radius: 12px; }
.entry { background: var(--card); border-radius: 12px; padding: 16px; }
.e-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.e-mood { font-size: 20px; }
.e-date { font-size: 12px; color: var(--text-3); flex: 1; }
.e-ops { display: flex; gap: 2px; }
.e-text { font-size: 14px; color: var(--text); line-height: 1.6; }
.e-summary { margin-top: 10px; padding: 10px 12px; background: rgba(59,130,246,.1); border-radius: 8px; font-size: 13px; color: #0369a1; line-height: 1.6; }
.pager { display: flex; justify-content: center; padding: 6px 0 0; }
</style>

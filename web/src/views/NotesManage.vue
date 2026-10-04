<template>
  <div class="notes-page">
    <h2 class="page-title">我的资料</h2>
    <div class="notes-layout">
      <div class="main-col">
        <div class="upload-card">
          <div class="upload-left">
            <div class="upload-icon">📄</div>
            <div>
              <div class="upload-title">上传生活笔记</div>
              <div class="upload-sub">支持 MD、TXT、PDF、Word，自动切片并向量化</div>
            </div>
          </div>
          <el-upload :show-file-list="false" :http-request="upload" accept=".md,.txt,.pdf,.docx">
            <el-button type="primary" :loading="uploading">选择文件</el-button>
          </el-upload>
        </div>

        <div class="table-card">
          <div class="table-head">
            <span>资料名称</span><span>类型</span><span>入库时间</span><span class="op">操作</span>
          </div>
          <div v-if="!notes.length" class="empty">还没有笔记，上传一份开始吧</div>
          <div v-for="n in notes" :key="n.doc_id" class="row">
            <span class="name">📎 {{ n.filename }}</span>
            <span class="type">{{ ext(n.filename) }}</span>
            <span class="time">{{ formatDateTime(n.created_at) }}</span>
            <span class="op"><el-button size="small" type="danger" link @click="remove(n.doc_id)">删除</el-button></span>
          </div>
        </div>

        <div class="search-bar">
          <input v-model="kw" placeholder="搜索我的笔记：原生态景点推荐" @input="onSearch" />
          <div v-if="searching" class="search-hint">搜索中…</div>
          <div v-else-if="kw && !results.length" class="search-hint">没有找到相关内容</div>
        </div>

        <div v-if="results.length" class="search-results">
          <div v-for="(r, i) in results" :key="i" class="sr-item">
            <div class="sr-filename">📄 {{ r.filename || '未命名笔记' }}</div>
            <div class="sr-content">{{ r.content }}</div>
          </div>
        </div>
      </div>

      <aside class="stats-card">
        <div class="stats-title">向量库</div>
        <div class="stat-row"><span class="sq"></span>personal_notes_idx</div>
        <div class="stat-row val">： {{ notes.length }} 篇</div>
        <div class="stat-row"><span class="sq"></span>life_task_memory_idx</div>
        <div class="stat-row val">： {{ stats.memory_count ?? '-' }} 条</div>
        <div class="stat-row"><span class="sq"></span>最近入库</div>
        <div class="stat-row val">： {{ stats.last_upload ? formatDate(stats.last_upload) : '—' }}</div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { listNotes, uploadNote, deleteNote } from '../api/notes'
import { formatDateTime, formatDate } from '../utils/format'
import api from '../api/request'

const notes = ref([])
const kw = ref('')
const uploading = ref(false)
const results = ref([])
const searching = ref(false)
const stats = ref({})
let searchTimer = null

async function load() { notes.value = (await listNotes()).data }

async function loadStats() {
  try { stats.value = (await api.get('/notes/stats')).data } catch {}
}

// 输入防抖 400ms 后语义搜索
function onSearch() {
  clearTimeout(searchTimer)
  const q = kw.value.trim()
  if (!q) { results.value = []; return }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const { data } = await api.get('/notes/search', { params: { q } })
      results.value = data.results || []
    } catch { results.value = [] }
    searching.value = false
  }, 400)
}

async function upload({ file }) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await uploadNote(fd)
    await load()
    await loadStats()
  } finally { uploading.value = false }
}
async function remove(id) { await deleteNote(id); load(); loadStats() }

function ext(name) { return (name.split('.').pop() || '').toUpperCase() }
onMounted(() => { load(); loadStats() })
</script>

<style scoped>
.page-title { margin: 0 0 18px; font-size: 20px; color: #111827; }
.notes-layout { display: flex; gap: 20px; align-items: flex-start; }
.main-col { flex: 1; display: flex; flex-direction: column; gap: 16px; min-width: 0; }

.upload-card { background: #fff; border-radius: 16px; padding: 24px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.upload-left { display: flex; align-items: center; gap: 14px; }
.upload-icon { width: 48px; height: 48px; border-radius: 12px; background: #eff6ff; display: flex; align-items: center; justify-content: center; font-size: 22px; }
.upload-title { font-size: 16px; font-weight: 600; color: #111827; }
.upload-sub { font-size: 13px; color: #9ca3af; margin-top: 2px; }

.table-card { background: #fff; border-radius: 16px; padding: 12px 24px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.table-head, .row { display: grid; grid-template-columns: 1fr 80px 200px 80px; gap: 12px; align-items: center; padding: 14px 0; }
.table-head { font-size: 13px; color: #6b7280; border-bottom: 1px solid #f0f1f3; }
.row { border-bottom: 1px solid #f7f8fa; font-size: 14px; color: #1f2937; }
.row:last-child { border-bottom: none; }
.op { text-align: right; }
.empty { padding: 40px; text-align: center; color: #9ca3af; font-size: 13px; }

.search-bar { background: #fff; border-radius: 16px; padding: 14px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.search-bar input { width: 100%; border: none; outline: none; font-size: 14px; color: #374151; background: transparent; }
.search-hint { font-size: 12px; color: #9ca3af; padding-top: 6px; }
.search-results { display: flex; flex-direction: column; gap: 10px; }
.sr-item { background: #fff; border-radius: 12px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.sr-filename { font-size: 13px; font-weight: 600; color: #111827; margin-bottom: 6px; }
.sr-content { font-size: 13px; color: #374151; line-height: 1.7; white-space: pre-wrap; max-height: 120px; overflow: auto; }

@media (max-width: 900px) {
  .notes-layout { flex-direction: column; }
  .stats-card { width: 100%; }
}
@media (max-width: 600px) {
  .table-head, .row { grid-template-columns: 1fr 60px 60px; }
  .table-head .time, .row .time { display: none; }
}

.stats-card { width: 280px; background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.stats-title { font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 14px; }
.stat-row { font-size: 14px; color: #374151; display: flex; align-items: center; gap: 8px; margin: 10px 0; }
.stat-row.val { padding-left: 26px; color: #6b7280; }
.stat-row.val strong { color: #111827; }
.sq { width: 12px; height: 12px; border-radius: 3px; background: #dbeafe; }
</style>

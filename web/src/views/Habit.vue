<template>
  <div class="page">
    <div class="head">
      <h2>习惯打卡</h2>
      <el-button type="primary" size="small" @click="dialog = true">+ 自定义习惯</el-button>
    </div>
    <div class="grid">
      <div v-for="h in pagedList" :key="h.id" class="card" :class="{ done: h.checked_today }">
        <div class="h-icon">{{ h.icon || '✨' }}</div>
        <div class="h-name">{{ h.name }}</div>
        <div class="h-streak">连续 {{ h.streak }} 天 · 累计 {{ h.checked_count }} 次 · 每天 {{ h.remind_time }}</div>
        <el-button v-if="!h.checked_today" type="primary" plain size="small" @click="check(h)">打卡</el-button>
        <span v-else class="done-tag">✓ 今日已完成</span>
        <el-button size="small" text type="danger" style="margin-top:6px" @click="del(h)">删除</el-button>
      </div>
      <div v-if="!list.length" class="empty">还没有习惯，点右上角添加一个吧</div>
    </div>
    <el-pagination v-if="list.length > pageSize" :total="list.length" :page-size="pageSize"
      :current-page="page" layout="prev, pager, next" small class="pager"
      @current-change="p => page = p" />

    <el-dialog v-model="dialog" title="新建习惯" width="420px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如：喝水/早起/运动" /></el-form-item>
        <el-form-item label="图标">
          <div class="icon-picker">
            <span v-for="ic in ICONS" :key="ic" class="ic" :class="{sel: form.icon===ic}" @click="form.icon=ic">{{ ic }}</span>
          </div>
        </el-form-item>
        <el-form-item label="提醒时间">
          <el-time-select v-model="form.remind_time" start="06:00" step="0:30" end="23:00" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog=false">取消</el-button>
        <el-button type="primary" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'

const list = ref([])
const dialog = ref(false)
const form = ref({ name: '', icon: '💧', remind_time: '09:00' })
const ICONS = ['💧','🏃','😴','📖','🚫','🗣️','🧘','🥗','☀️','🎯','✍️','🎨','💪','🎵','📚','💊']
// 分页：10 条/页
const page = ref(1)
const pageSize = 10
const pagedList = computed(() => list.value.slice((page.value - 1) * pageSize, page.value * pageSize))

// 首次进入时自动创建的默认习惯（可删可改，保留自定义）
const DEFAULTS = [
  { name: '早起', icon: '☀️', remind_time: '07:00' },
  { name: '早睡', icon: '😴', remind_time: '22:30' },
  { name: '运动 30 分钟', icon: '🏃', remind_time: '18:30' },
  { name: '阅读 30 分钟', icon: '📖', remind_time: '21:00' },
  { name: '健康饮食', icon: '🥗', remind_time: '12:00' },
  { name: '冥想 10 分钟', icon: '🧘', remind_time: '08:00' }
]

async function load() {
  let data = (await api.get('/life/habits')).data
  if (!data.length) {
    for (const d of DEFAULTS) await api.post('/life/habits', d)
    data = (await api.get('/life/habits')).data
  }
  list.value = data
}
async function create(){
  if(!form.value.name.trim()) return
  await api.post('/life/habits', form.value)
  dialog.value = false; form.value = { name: '', icon: '💧', remind_time: '09:00' }
  page.value = 1
  load()
}
async function check(h){ await api.post(`/life/habits/${h.id}/check`); load() }
async function del(h){ await api.delete(`/life/habits/${h.id}`); load() }
onMounted(load)
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.head h2 { margin: 0; font-size: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
.card { background: var(--card); border-radius: 12px; padding: 22px; text-align: center; border: 1px solid var(--border); }
.card.done { border-color: #10b981; background: rgba(16,185,129,.12); }
.h-icon { font-size: 36px; }
.h-name { font-size: 14px; font-weight: 600; margin: 8px 0 4px; }
.h-streak { font-size: 12px; color: #f59e0b; margin-bottom: 12px; }
.done-tag { color: #10b981; font-size: 13px; }
.empty { grid-column: 1/-1; text-align: center; color: var(--text-3); padding: 40px; background: var(--card); border-radius: 12px; }
.icon-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.ic { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 8px; font-size: 18px; cursor: pointer; border: 1px solid var(--border); }
.ic.sel { border-color: #2563eb; background: var(--primary-bg); }
.pager { display: flex; justify-content: center; padding: 16px 0 0; }
</style>

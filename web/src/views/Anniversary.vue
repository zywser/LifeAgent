<template>
  <div class="page">
    <h2>纪念日提醒</h2>
    <p class="hint">记下重要的日子，Agent 会提前 3 天开始提醒你</p>
    <div class="form-card">
      <el-input v-model="form.name" placeholder="纪念日名称" style="width:160px" />
      <el-date-picker v-model="form.date" type="date" placeholder="日期" value-format="YYYY-MM-DD" style="width:160px" />
      <el-button type="primary" @click="add">添加</el-button>
    </div>
    <div class="list">
      <div v-if="!items.length" class="empty">还没有纪念日，加一个吧</div>
      <div v-for="a in pagedList" :key="a.id" class="item">
        <div>
          <div class="a-name">{{ a.name }}</div>
          <div class="a-date">{{ a.event_date }} {{ a.year ? a.year : '(每年)' }}</div>
        </div>
        <div class="a-count">
          <span class="n">{{ daysLeft(a) }}</span> 天
        </div>
        <el-button size="small" text type="danger" @click="del(a)">删</el-button>
      </div>
      <el-pagination v-if="items.length > pageSize" :total="items.length" :page-size="pageSize"
        :current-page="page" layout="prev, pager, next" small class="pager"
        @current-change="p => page = p" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'

const form = ref({ name: '', date: null })
const items = ref([])
// 分页：10 条/页
const page = ref(1)
const pageSize = 10
const pagedList = computed(() => items.value.slice((page.value - 1) * pageSize, page.value * pageSize))

function daysLeft(a){
  const now = new Date(); now.setHours(0,0,0,0)
  const [m,d] = a.event_date.split('-').map(Number)
  let target = new Date(now.getFullYear(), m-1, d)
  if(target < now) target = new Date(now.getFullYear()+1, m-1, d)
  return Math.ceil((target - now) / 86400000)
}

async function load(){ items.value = (await api.get('/life/anniversaries')).data }
async function add(){
  if(!form.value.name || !form.value.date) return
  const [y,m,d] = form.value.date.split('-')
  await api.post('/life/anniversaries', { name: form.value.name, event_date: `${m}-${d}`, year: parseInt(y) })
  form.value = { name: '', date: null }
  page.value = 1
  load()
}
async function del(a){ await api.delete(`/life/anniversaries/${a.id}`); load() }
onMounted(load)
</script>

<style scoped>
.page { max-width: 700px; margin: 0 auto; width: 100%; }
h2 { font-size: 20px; margin: 0 0 8px; }
.hint { color: var(--text-2); font-size: 13px; margin-bottom: 16px; }
.form-card { display: flex; gap: 10px; background: var(--card); padding: 16px; border-radius: 12px; margin-bottom: 16px; }
.list { display: flex; flex-direction: column; gap: 10px; }
.empty { text-align: center; color: var(--text-3); padding: 40px; background: var(--card); border-radius: 12px; }
.item { background: var(--card); border-radius: 12px; padding: 16px 20px; display: flex; align-items: center; gap: 16px; }
.a-name { font-size: 14px; font-weight: 600; }
.a-date { font-size: 12px; color: var(--text-3); margin-top: 2px; }
.a-count { margin-left: auto; font-size: 13px; color: var(--text-2); }
.a-count .n { font-size: 20px; font-weight: 700; color: #f59e0b; }
.pager { display: flex; justify-content: center; padding: 6px 0 0; }
</style>

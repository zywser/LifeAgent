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
      <div v-for="a in items" :key="a.id" class="item">
        <div>
          <div class="a-name">{{ a.name }}</div>
          <div class="a-date">{{ a.event_date }} {{ a.year ? a.year : '(每年)' }}</div>
        </div>
        <div class="a-count">
          <span class="n">{{ daysLeft(a) }}</span> 天
        </div>
        <el-button size="small" text type="danger" @click="del(a)">删</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api/request'

const form = ref({ name: '', date: null })
const items = ref([])

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
  load()
}
async function del(a){ await api.delete(`/life/anniversaries/${a.id}`); load() }
onMounted(load)
</script>

<style scoped>
.page { max-width: 700px; margin: 0 auto; width: 100%; }
h2 { font-size: 20px; margin: 0 0 8px; }
.hint { color: #6b7280; font-size: 13px; margin-bottom: 16px; }
.form-card { display: flex; gap: 10px; background: #fff; padding: 16px; border-radius: 12px; margin-bottom: 16px; }
.list { display: flex; flex-direction: column; gap: 10px; }
.empty { text-align: center; color: #9ca3af; padding: 40px; background: #fff; border-radius: 12px; }
.item { background: #fff; border-radius: 12px; padding: 16px 20px; display: flex; align-items: center; gap: 16px; }
.a-name { font-size: 14px; font-weight: 600; }
.a-date { font-size: 12px; color: #9ca3af; margin-top: 2px; }
.a-count { margin-left: auto; font-size: 13px; color: #6b7280; }
.a-count .n { font-size: 20px; font-weight: 700; color: #f59e0b; }
</style>

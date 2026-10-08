<template>
  <div class="page">
    <div class="head">
      <h2>存钱目标</h2>
      <el-button type="primary" @click="dialog = true">新建目标</el-button>
    </div>
    <div class="grid">
      <div v-for="g in pagedList" :key="g.id" class="card">
        <div class="goal-name">{{ g.purpose }}</div>
        <div class="bar"><div class="fill" :style="{width: pct(g)+'%'}"></div></div>
        <div class="nums">已存 ¥{{ g.saved_amount }} / ¥{{ g.target_amount }}</div>
        <div class="pct">{{ pct(g) }}% · 截止 {{ formatDate(g.deadline) }}</div>
        <div class="actions">
          <el-input v-model="g._amt" type="number" placeholder="存入" style="width:100px" />
          <el-button size="small" type="primary" @click="save(g)">存入</el-button>
          <el-button size="small" text type="danger" @click="del(g)">删除</el-button>
        </div>
      </div>
      <div v-if="!list.length" class="empty">还没有存钱目标，新建一个吧</div>
    </div>
    <el-pagination v-if="list.length > pageSize" :total="list.length" :page-size="pageSize"
      :current-page="page" layout="prev, pager, next" small class="pager"
      @current-change="p => page = p" />

    <el-dialog v-model="dialog" title="新建存钱目标" width="420px">
      <el-form label-width="80px">
        <el-form-item label="目的"><el-input v-model="form.purpose" placeholder="如：旅行基金 / 买电脑 / 考研经费" /></el-form-item>
        <el-form-item label="目标金额"><el-input v-model.number="form.target_amount" type="number" /></el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" /></el-form-item>
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
import { formatDate } from '../utils/format'

const list = ref([])
const dialog = ref(false)
const form = ref({ purpose: '', target_amount: 10000, deadline: '' })
// 分页：10 条/页
const page = ref(1)
const pageSize = 10
const pagedList = computed(() => list.value.slice((page.value - 1) * pageSize, page.value * pageSize))

function pct(g){ return Math.min(100, Math.round(g.saved_amount/g.target_amount*100)) }
async function load(){ const rows = (await api.get('/life/savings')).data; list.value = rows.map(g => ({...g, _amt: ''})) }
async function create(){
  if(!form.value.purpose || !form.value.target_amount || !form.value.deadline) return
  await api.post('/life/savings', { ...form.value, saved_amount: 0 })
  dialog.value = false
  form.value = { purpose: '', target_amount: 10000, deadline: '' }
  page.value = 1
  load()
}
async function save(g){
  const v = parseFloat(g._amt); if(!v||v<=0) return
  await api.put(`/life/savings/${g.id}`, { purpose: g.purpose, target_amount: g.target_amount, saved_amount: g.saved_amount + v, deadline: g.deadline })
  load()
}
async function del(g){ await api.delete(`/life/savings/${g.id}`); load() }
onMounted(load)
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; width: 100%; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.head h2 { margin: 0; font-size: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.card { background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }
.goal-name { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.bar { height: 10px; background: var(--hover); border-radius: 5px; overflow: hidden; margin-bottom: 10px; }
.fill { height: 100%; background: #10b981; transition: width .3s; }
.nums { color: var(--text-2); font-size: 13px; }
.pct { font-size: 14px; font-weight: 600; color: #10b981; margin: 6px 0 12px; }
.actions { display: flex; gap: 8px; align-items: center; }
.empty { grid-column: 1/-1; text-align: center; color: var(--text-3); padding: 40px; background: var(--card); border-radius: 12px; }
.pager { display: flex; justify-content: center; padding: 16px 0 0; }
</style>

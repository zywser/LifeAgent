<template>
  <div class="page">
    <div class="head">
      <h2>轻量记账</h2>
      <span class="sub">支出 ¥{{ spent }} · 收入 ¥{{ earned }} · 余额 ¥{{ balance }}</span>
    </div>

    <div class="form-card">
      <el-radio-group v-model="kind" size="default">
        <el-radio-button value="expense">支出</el-radio-button>
        <el-radio-button value="income">收入</el-radio-button>
      </el-radio-group>
      <el-input v-model="amount" type="number" placeholder="金额" style="width:120px" />
      <el-select v-model="category" placeholder="分类" style="width:120px">
        <el-option v-for="c in cats" :key="c" :label="c" :value="c" />
      </el-select>
      <el-input v-model="note" placeholder="备注（可选）" style="flex:1" />
      <el-button :type="kind==='income'?'success':'danger'" @click="add">记一笔</el-button>
    </div>

    <div class="analytics">
      <div class="ana-card">
        <h3>近 7 天支出</h3>
        <div class="week">
          <div v-for="(d, i) in weekData" :key="i" class="wk-day">
            <div class="wk-bar-wrap">
              <div class="wk-bar" :style="{ height: pct(d.total, maxDay) + '%' }"></div>
            </div>
            <div class="wk-num">¥{{ d.total ? d.total.toFixed(0) : 0 }}</div>
            <div class="wk-label">{{ d.label }}</div>
          </div>
        </div>
      </div>
      <div class="ana-card">
        <h3>分类支出占比</h3>
        <div v-if="!catData.length" class="ana-empty">暂无支出数据</div>
        <div v-else class="cats">
          <div v-for="c in catData" :key="c.cat" class="cat-row">
            <span class="cat-name">{{ c.cat }}</span>
            <div class="cat-bar-wrap">
              <div class="cat-bar" :style="{ width: pct(c.total, catMax) + '%' }"></div>
            </div>
            <span class="cat-val">¥{{ c.total.toFixed(0) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="list">
      <div v-if="!list.length" class="empty">还没有记录，记一笔开始吧</div>
      <div v-for="r in list" :key="r.id" class="row">
        <span class="cat" :class="r.kind">{{ r.kind === 'income' ? '收入' : r.category }}</span>
        <span class="note">{{ r.note || '—' }}</span>
        <span class="time">{{ formatShort(r.time) }}</span>
        <span class="amount" :class="r.kind">
          {{ r.kind === 'income' ? '+' : '-' }}¥{{ r.amount }}
        </span>
        <el-button size="small" text type="danger" @click="del(r.id)">删</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'
import { formatShort } from '../utils/format'

const kind = ref('expense')
const amount = ref(''); const category = ref('餐饮'); const note = ref('')
const cats = ['餐饮', '交通', '购物', '工资', '兼职', '红包', '理财', '其他']
const list = ref([])

const spent = computed(() => list.value.filter(r=>r.kind!=='income').reduce((s,r)=>s+Number(r.amount),0).toFixed(2))
const earned = computed(() => list.value.filter(r=>r.kind==='income').reduce((s,r)=>s+Number(r.amount),0).toFixed(2))
const balance = computed(() => (Number(earned.value) - Number(spent.value)).toFixed(2))

// 近 7 天支出（按本地日期分组）
const weekData = computed(() => {
  const days = []
  for (let i = 6; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i)
    const key = d.toDateString()
    const total = list.value
      .filter(r => r.kind !== 'income' && new Date(r.time).toDateString() === key)
      .reduce((s, r) => s + Number(r.amount), 0)
    days.push({ label: `${d.getMonth() + 1}/${d.getDate()}`, total })
  }
  return days
})
const maxDay = computed(() => Math.max(1, ...weekData.value.map(d => d.total)))

// 分类支出聚合，金额降序
const catData = computed(() => {
  const map = {}
  for (const r of list.value) {
    if (r.kind === 'income') continue
    const c = r.category || '其他'
    map[c] = (map[c] || 0) + Number(r.amount)
  }
  return Object.entries(map).map(([cat, total]) => ({ cat, total })).sort((a, b) => b.total - a.total)
})
const catMax = computed(() => Math.max(1, ...catData.value.map(c => c.total)))
function pct(v, max) { return Math.round(v / max * 100) }

async function load(){
  const { data } = await api.get('/life/expenses')
  list.value = data
  const old = JSON.parse(localStorage.getItem('lifeagent_expenses') || '[]')
  if (old.length && !data.length) {
    for (const e of old) {
      await api.post('/life/expenses', { amount: e.amount, kind: 'expense', category: e.category, note: e.note || '' }).catch(()=>{})
    }
    localStorage.removeItem('lifeagent_expenses')
    const { data: d2 } = await api.get('/life/expenses')
    list.value = d2
  }
}
onMounted(load)

async function add(){
  const v = parseFloat(amount.value)
  if(!v || v<=0) return
  await api.post('/life/expenses', { amount: v, kind: kind.value, category: category.value, note: note.value })
  amount.value=''; note.value=''
  load()
}
async function del(id){
  await api.delete(`/life/expenses/${id}`)
  load()
}
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; width: 100%; }
.head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.head h2 { margin: 0; font-size: 20px; }
.sub { color: #6b7280; font-size: 13px; }
.form-card { display: flex; gap: 10px; background: #fff; padding: 16px; border-radius: 12px; margin-bottom: 16px; align-items: center; }
.analytics { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.ana-card { background: #fff; border-radius: 12px; padding: 18px 20px; }
.ana-card h3 { margin: 0 0 16px; font-size: 15px; color: #111827; }
.ana-empty { color: #9ca3af; font-size: 13px; text-align: center; padding: 20px 0; }
.week { display: flex; align-items: flex-end; gap: 10px; height: 130px; }
.wk-day { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; }
.wk-bar-wrap { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; }
.wk-bar { width: 55%; min-height: 2px; background: linear-gradient(180deg, #f87171, #ef4444); border-radius: 4px 4px 0 0; transition: height .3s; }
.wk-num { font-size: 11px; color: #374151; }
.wk-label { font-size: 11px; color: #9ca3af; }
.cats { display: flex; flex-direction: column; gap: 10px; }
.cat-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.cat-name { width: 48px; color: #374151; flex-shrink: 0; }
.cat-bar-wrap { flex: 1; height: 14px; background: #f3f4f6; border-radius: 7px; overflow: hidden; }
.cat-bar { height: 100%; background: linear-gradient(90deg, #93c5fd, #2563eb); border-radius: 7px; transition: width .3s; }
.cat-val { width: 56px; text-align: right; color: #111827; font-weight: 600; flex-shrink: 0; }
.list { background: #fff; border-radius: 12px; padding: 8px 16px; }
.empty { text-align: center; color: #9ca3af; padding: 40px; }
.row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f3f4f6; font-size: 14px; }
.row:last-child { border: none; }
.cat { background: #eff6ff; color: #2563eb; padding: 2px 10px; border-radius: 10px; font-size: 12px; }
.cat.income { background: #ecfdf5; color: #059669; }
.note { flex: 1; color: #374151; }
.time { color: #9ca3af; font-size: 12px; }
.amount { color: #ef4444; font-weight: 600; }
.amount.income { color: #059669; }

@media (max-width: 768px) {
  .analytics { grid-template-columns: 1fr; }
  .form-card { flex-wrap: wrap; }
  .form-card .el-input { flex: 1 1 100% !important; }
}
</style>

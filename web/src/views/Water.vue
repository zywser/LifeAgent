<template>
  <div class="page">
    <h2>喝水记录</h2>
    <p class="hint">
      今天已喝 <b>{{ count }}</b> 杯，目标
      <el-input-number v-model="target" :min="1" :max="20" size="small" style="width: 84px" @change="onTargetChange" />
      杯
    </p>
    <div class="cups">
      <div v-for="n in target" :key="n" class="cup" :class="{ full: n <= count }" @click="set(n)">💧</div>
    </div>
    <el-button type="primary" @click="oneMore">+ 喝一杯</el-button>

    <div class="week-card">
      <h3>近 7 天</h3>
      <div class="week">
        <div v-for="(w, i) in week" :key="i" class="wk-day">
          <div class="wk-bar-wrap">
            <div class="wk-bar" :style="{ height: pct(w.count) + '%' }"></div>
          </div>
          <div class="wk-num">{{ w.count }}</div>
          <div class="wk-label">{{ w.label }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'

const TARGET_KEY = 'lifeagent_water_target'
const target = ref(Number(localStorage.getItem(TARGET_KEY)) || 8)
const logs = ref([])  // [{date: 'YYYY-MM-DD', cups}]

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const today = iso(new Date())
const map = computed(() => Object.fromEntries(logs.value.map(l => [l.date, l.cups])))
const count = ref(0)

async function load() {
  logs.value = (await api.get('/life/water')).data
  count.value = map.value[today] || 0
}
async function persist() {
  await api.post('/life/water', { date: today, cups: count.value })
  const idx = logs.value.findIndex(l => l.date === today)
  if (idx >= 0) logs.value[idx].cups = count.value
  else logs.value.push({ date: today, cups: count.value })
}
function onTargetChange(v) {
  target.value = Math.max(1, Math.min(20, v || 8))
  localStorage.setItem(TARGET_KEY, String(target.value))
}
function set(n) { count.value = n; persist() }
function oneMore() { if (count.value < target.value) { count.value++; persist() } }

const week = computed(() => {
  const out = []
  for (let i = 6; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i)
    out.push({ label: `${d.getMonth() + 1}/${d.getDate()}`, count: map.value[iso(d)] || 0 })
  }
  return out
})
const maxWeek = computed(() => Math.max(1, ...week.value.map(w => w.count), target.value))
function pct(c) { return Math.round(c / maxWeek.value * 100) }
onMounted(load)
</script>

<style scoped>
.page { max-width: 600px; margin: 0 auto; width: 100%; text-align: center; }
h2 { font-size: 20px; }
.hint { color: #6b7280; margin-bottom: 24px; }
.cups { display: flex; justify-content: center; gap: 10px; margin-bottom: 24px; flex-wrap: wrap; }
.cup { font-size: 34px; opacity: .25; cursor: pointer; transition: all .15s; }
.cup.full { opacity: 1; transform: scale(1.1); }
.week-card { background: #fff; border-radius: 12px; padding: 20px; margin-top: 28px; text-align: left; }
.week-card h3 { margin: 0 0 18px; font-size: 15px; color: #111827; }
.week { display: flex; align-items: flex-end; gap: 14px; height: 140px; }
.wk-day { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; }
.wk-bar-wrap { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; }
.wk-bar { width: 60%; min-height: 2px; background: linear-gradient(180deg, #60a5fa, #2563eb); border-radius: 4px 4px 0 0; transition: height .3s; }
.wk-num { font-size: 12px; color: #374151; font-weight: 600; }
.wk-label { font-size: 11px; color: #9ca3af; }
</style>

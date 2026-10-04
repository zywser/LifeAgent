<template>
  <div class="graph-page">
    <h2 class="page-title">Agent 执行链路</h2>
    <div class="graph-layout">
      <div class="graph-card">
        <div class="flow">
          <div v-for="(n, i) in nodes" :key="n.name" class="node-wrap" :class="{first: i===0}">
            <div class="node" :class="statusOf(n.name)">
              <span class="node-icon">{{ n.icon }}</span>
              <span class="node-label">{{ n.label }}</span>
            </div>
            <span class="badge" :class="statusOf(n.name)">{{ badgeText(n.name) }}</span>
            <span v-if="i < nodes.length - 1" class="arrow">→</span>
          </div>
        </div>
        <div class="supervisor-note">
          <span class="node-icon">🧭</span> 由 Supervisor 统一调度，Reviewer 不通过时最多回环重规划 3 次
        </div>
      </div>

      <aside class="log-card">
        <div class="log-title">执行日志</div>
        <div v-if="!run.steps.length" class="log-empty">暂无运行记录，去对话页发起一次任务。</div>
        <ul v-else class="log-list">
          <li v-for="(s, i) in run.steps" :key="i">
            <span class="log-dot" :class="s.status"></span>
            <span class="log-name">{{ s.label }}</span>
            <span class="log-state" :class="s.status">
              {{ s.status === 'done' ? '已完成' : s.status === 'running' ? '执行中' : '等待' }}
            </span>
          </li>
        </ul>
        <div v-if="run.lastAnswer" class="result-box">
          <div class="result-title">最终结果</div>
          <div class="result-text">{{ run.lastAnswer }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRunStore } from '../stores/run'
const run = useRunStore()

const nodes = [
  { name: 'planner', label: 'Planner', icon: '📋' },
  { name: 'retriever', label: 'Retriever', icon: '🔎' },
  { name: 'executor', label: 'Executor', icon: '⚙️' },
  { name: 'synthesizer', label: 'Synthesizer', icon: '🧩' },
  { name: 'reviewer', label: 'Reviewer', icon: '✅' }
]

function statusOf(name) {
  const s = run.steps.find(x => x.node === name)
  return s ? s.status : 'idle'
}
function badgeText(name) {
  const st = statusOf(name)
  return st === 'done' ? '已完成' : st === 'running' ? '执行中' : '待执行'
}
</script>

<style scoped>
.page-title { margin: 0 0 18px; font-size: 20px; color: #111827; }
.graph-layout { display: flex; gap: 20px; }
.graph-card { flex: 1; background: #fff; border-radius: 16px; padding: 40px 28px; box-shadow: 0 1px 3px rgba(0,0,0,.04); min-width: 0; }
.flow { display: flex; align-items: flex-start; justify-content: center; gap: 8px; flex-wrap: wrap; }
.node-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; position: relative; }
.node { width: 110px; padding: 18px 10px; border: 2px solid #e5e7eb; border-radius: 12px; background: #fff; display: flex; flex-direction: column; align-items: center; gap: 6px; font-size: 13px; color: #374151; }
.node.running { border-color: #2563eb; background: #eff6ff; }
.node.done { border-color: #10b981; background: #ecfdf5; }
.node-icon { font-size: 22px; }
.node-label { font-weight: 600; }
.badge { font-size: 12px; padding: 3px 10px; border-radius: 999px; background: #f3f4f6; color: #6b7280; }
.badge.running { background: #dbeafe; color: #2563eb; }
.badge.done { background: #d1fae5; color: #059669; }
.arrow { position: absolute; top: 38px; right: -16px; font-size: 20px; color: #9ca3af; }
.supervisor-note { margin-top: 36px; text-align: center; color: #6b7280; font-size: 13px; }

.log-card { width: 320px; background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.log-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; color: #111827; }
.log-empty { color: #9ca3af; font-size: 13px; }
.log-list { list-style: none; padding: 0; margin: 0; }
.log-list li { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f3f4f6; font-size: 14px; }
.log-dot { width: 9px; height: 9px; border-radius: 50%; background: #d1d5db; }
.log-dot.running { background: #2563eb; }
.log-dot.done { background: #10b981; }
.log-name { flex: 1; color: #1f2937; }
.log-state.running { color: #2563eb; font-size: 12px; }
.log-state.done { color: #10b981; font-size: 12px; }
.result-box { margin-top: 16px; background: #f8fafc; border-radius: 10px; padding: 12px; }
.result-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #111827; }
.result-text { font-size: 13px; color: #374151; white-space: pre-wrap; max-height: 220px; overflow: auto; }
</style>

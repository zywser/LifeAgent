import { defineStore } from 'pinia'
import { saveConversation as apiSaveConversation } from '../api/conversations'

const NODE_LABELS = {
  supervisor: '调度器',
  planner: 'Planner',
  retriever: 'Retriever',
  executor: 'Executor',
  synthesizer: 'Synthesizer',
  reviewer: 'Reviewer'
}

const STORAGE_KEY = 'lifeagent_conversations'

export const useRunStore = defineStore('run', {
  state: () => ({
    steps: [],
    messages: [],
    running: false,
    lastAnswer: '',
    currentId: null
  }),
  actions: {
    reset() {
      this.steps = []
      this.running = false
      this.lastAnswer = ''
    },
    startNode(name) {
      // 只在"同名且正在运行"时跳过；同名已 done 说明是新一轮循环（executor），
      // 新建一条带序号的步骤，直观展示子任务被逐个执行。
      const running = this.steps.find(s => s.node === name && s.status === 'running')
      if (running) return
      const round = this.steps.filter(s => s.node === name).length
      const base = NODE_LABELS[name] || name
      this.steps.push({
        node: name,
        label: round > 0 ? `${base} (${round + 1})` : base,
        status: 'running',
        round
      })
    },
    finishNode(name) {
      const s = this.steps.find(s => s.node === name && s.status === 'running')
      if (s) s.status = 'done'
    },
    addMessage(role, content, time) {
      // 每条消息带本地时间戳；兼容旧数据（无 time 时前端自动跳过显示）
      this.messages.push({ role, content, time: time || new Date().toISOString() })
    },
    setRunning(v) { this.running = v },
    setAnswer(a) { this.lastAnswer = a },

    async saveConversation() {
      if (!this.messages.length) return null
      const userMsg = this.messages.find(m => m.role === 'user')
      const aiMsg = [...this.messages].reverse().find(m => m.role === 'assistant')
      const title = (userMsg?.content || '新对话').slice(0, 20)
      const preview = (aiMsg?.content || '').slice(0, 80)

      // 云端保存（后端返回数字 id）；失败则回退本地，不阻塞聊天
      let serverId = null
      try {
        const payload = { title, preview, messages: this.messages }
        if (this.currentId && /^\d+$/.test(this.currentId)) payload.id = Number(this.currentId)
        const { data } = await apiSaveConversation(payload)
        serverId = data.id
      } catch { serverId = null }

      const finalId = serverId != null ? String(serverId) : (this.currentId || Date.now().toString(36))
      const conv = {
        id: finalId,
        title, preview,
        time: new Date().toISOString(),
        messages: [...this.messages]
      }
      let arr = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
      const idx = arr.findIndex(x => x.id === finalId)
      if (idx >= 0) arr[idx] = conv
      else {
        // 后端新建了 id：把旧的本地占位/字符串 id 条目替换掉，避免重复
        if (this.currentId && this.currentId !== finalId) arr = arr.filter(x => x.id !== this.currentId)
        arr.unshift(conv)
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(arr.slice(0, 50)))
      this.currentId = finalId
      return finalId
    },

    loadConversation(c) {
      // 旧会话消息可能没有 time 字段：用会话时间兜底补上，保证气泡时间必显示
      const base = c.time || new Date().toISOString()
      this.messages = (c.messages || []).map(m => ({ ...m, time: m.time || base }))
      this.currentId = c.id
      this.steps = []
      this.running = false
    },

    newChat() {
      this.messages = []
      this.currentId = Date.now().toString(36)
      this.steps = []
      this.running = false
      // 立即在历史列表创建一条占位
      const arr = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
      arr.unshift({
        id: this.currentId,
        title: '新对话',
        preview: '',
        time: new Date().toISOString(),
        messages: []
      })
      localStorage.setItem(STORAGE_KEY, JSON.stringify(arr.slice(0, 50)))
    }
  }
})

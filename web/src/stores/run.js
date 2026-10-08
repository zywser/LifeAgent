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
// 进行中对话的持久化 key：页面刷新/重载后恢复现场，避免"消息被删除"
const RUN_KEY = 'lifeagent_run_state'

function loadSaved() {
  try {
    const s = JSON.parse(localStorage.getItem(RUN_KEY) || '{}')
    return {
      steps: Array.isArray(s.steps) ? s.steps : [],
      messages: Array.isArray(s.messages) ? s.messages : [],
      // running 不恢复：页面重载后 SSE 已中断，恢复为待机态
      lastAnswer: typeof s.lastAnswer === 'string' ? s.lastAnswer : '',
      currentId: s.currentId || null
    }
  } catch {
    return {}
  }
}

export const useRunStore = defineStore('run', {
  state: () => ({
    running: false,
    // "当前对话"标记（不持久化）：发消息后即为当前对话（回答完成/中断后切回 chat 保留现场）；
    // 打开历史会话（loadConversation）时清除，之后点"对话助手"回到新对话欢迎页
    currentIsActive: false,
    ...loadSaved()
  }),
  actions: {
    _persist() {
      // 不持久化 running：刷新后永远回到待机态，避免卡在"思考中"
      try {
        localStorage.setItem(RUN_KEY, JSON.stringify({
          steps: this.steps,
          messages: this.messages,
          lastAnswer: this.lastAnswer,
          currentId: this.currentId
        }))
      } catch {}
    },
    reset() {
      this.steps = []
      this.running = false
      this.lastAnswer = ''
      this._persist()
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
      this._persist()
    },
    finishNode(name) {
      const s = this.steps.find(s => s.node === name && s.status === 'running')
      if (s) s.status = 'done'
      this._persist()
    },
    addMessage(role, content, time) {
      // 每条消息带本地时间戳；兼容旧数据（无 time 时前端自动跳过显示）
      this.messages.push({ role, content, time: time || new Date().toISOString() })
      this._persist()
    },
    setRunning(v) { this.running = v; this._persist() },
    setAnswer(a) { this.lastAnswer = a; this._persist() },

    // 规范化消息/载荷：双标签页并发写坏 localStorage 后，坏数据不再上行导致后端 422
    _normMsg(m) {
      return {
        role: (m && m.role === 'user') ? 'user' : 'assistant',
        content: String((m && m.content != null) ? m.content : ''),
        time: (m && typeof m.time === 'string' && m.time) ? m.time : new Date().toISOString()
      }
    },
    _normPayload(msgs, title, preview) {
      return {
        title: String(title || '新对话').slice(0, 255),
        preview: String(preview || '').slice(0, 500),
        messages: (Array.isArray(msgs) ? msgs : []).filter(m => m && typeof m === 'object').map(m => this._normMsg(m))
      }
    },

    // —— 回答轮次（round）上下文：回答进行中可自由切换会话，回答仍保存回发起会话 ——
    // _round 不持久化（刷新后 SSE 已中断）；{ id: 发起会话, messages: 发起时快照(含 user), buffer: 切走后打字机缓冲 }
    // 调用前务必先 addMessage('user', q)，快照才能包含本轮用户消息
    startRound() {
      this._round = {
        id: this.currentId,
        messages: this.messages.map(m => ({ ...m })),
        buffer: null
      }
      // 新一轮执行链路从零开始
      this.steps = []
    },

    // 用 round 上下文保存：即使回答进行中用户切到了别的会话，也保存到发起会话，不污染当前浏览的会话
    async saveRound(answer) {
      const round = this._round
      if (!round) return this.saveConversation()
      const msgs = [...round.messages, { role: 'assistant', content: answer, time: new Date().toISOString() }]
      const userMsg = round.messages.find(m => m && m.role === 'user')
      const title = (userMsg?.content || '新对话').slice(0, 20)
      const preview = (answer || '').slice(0, 80)
      const payload = this._normPayload(msgs, title, preview)
      let serverId = null
      try {
        if (round.id && /^\d+$/.test(round.id)) payload.id = Number(round.id)
        const { data } = await apiSaveConversation(payload)
        serverId = data.id
      } catch { serverId = null }
      const finalId = serverId != null ? String(serverId) : (round.id || Date.now().toString(36))
      const conv = { id: finalId, title, preview, time: new Date().toISOString(), messages: payload.messages }
      let arr = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
      const idx = arr.findIndex(x => x.id === finalId)
      if (idx >= 0) arr[idx] = conv
      else {
        if (round.id && round.id !== finalId) arr = arr.filter(x => x.id !== round.id)
        arr.unshift(conv)
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(arr.slice(0, 50)))
      // 仅当用户仍在发起会话时才更新 currentId（新建会话后下一轮回答才能接续）；
      // 若保存期间已切到别的会话，保持当前浏览的会话不变
      if (this.currentId === round.id) this.currentId = finalId
      this._persist()
      const result = { id: finalId, title, preview }
      // 回答已保存完成，round 使命结束：之后点"对话助手"应默认新对话，不再残留现场
      this._round = null
      return result
    },
    // 回答中断/连接断开时手动结束 round，避免现场残留
    finishRound() {
      this._round = null
      this._persist()
    },

    async saveConversation() {
      if (!this.messages.length) return null
      const userMsg = this.messages.find(m => m && m.role === 'user')
      const aiMsg = [...this.messages].reverse().find(m => m && m.role === 'assistant')
      const title = (userMsg?.content || '新对话').slice(0, 20)
      const preview = (aiMsg?.content || '').slice(0, 80)

      // 云端保存（后端返回数字 id）；失败则回退本地，不阻塞聊天
      const payload = this._normPayload(this.messages, title, preview)
      let serverId = null
      try {
        if (this.currentId && /^\d+$/.test(this.currentId)) payload.id = Number(this.currentId)
        const { data } = await apiSaveConversation(payload)
        serverId = data.id
      } catch { serverId = null }

      const finalId = serverId != null ? String(serverId) : (this.currentId || Date.now().toString(36))
      const conv = {
        id: finalId,
        title, preview,
        time: new Date().toISOString(),
        messages: payload.messages
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
      this._persist()
      return { id: finalId, title, preview }
    },

    loadConversation(c) {
      // 允许回答进行中切换会话（豆包式）：正在进行的回答由 round 上下文接管，
      // 完成时保存回发起会话，不会破坏当前浏览的会话
      this.justFinished = false
      this.currentIsActive = false
      const base = c.time || new Date().toISOString()
      this.messages = (Array.isArray(c.messages) ? c.messages : [])
        .filter(m => m && typeof m === 'object')
        .map(m => ({ ...m, time: m.time || base }))
      this.currentId = c.id
      this.steps = []
      this.running = false
      this._persist()
    },

    newChat() {
      this.messages = []
      this.currentId = Date.now().toString(36)
      this.steps = []
      this.running = false
      this.justFinished = false
      this.currentIsActive = true
      this._persist()
      // 注意：不在这里向会话列表写入"新对话"占位。
      // 占位会话只在内存（currentId）里存在，发消息后回答完成才以真实会话入库；
      // 否则打开 /chat 页面就会在"最近对话"里堆出一堆"新对话"占位（路由都指向 /chat）。
    }
  }
})

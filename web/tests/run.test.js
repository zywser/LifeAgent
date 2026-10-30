import { describe, it, expect, beforeEach, beforeAll } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// node 环境无 localStorage，提供内存实现（run store 初始化时会读取）
beforeAll(() => {
  const map = new Map()
  globalThis.localStorage = {
    getItem: k => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: k => map.delete(k),
    clear: () => map.clear()
  }
})

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})

async function useStore() {
  const { useRunStore } = await import('../src/stores/run')
  return useRunStore()
}

describe('run store 节点状态', () => {
  it('startNode 推入运行中节点并使用中文标签', async () => {
    const store = await useStore()
    store.startNode('supervisor')
    expect(store.steps).toHaveLength(1)
    expect(store.steps[0].status).toBe('running')
    expect(store.steps[0].label).toBe('调度器')
  })

  it('同名运行中节点不重复添加', async () => {
    const store = await useStore()
    store.startNode('executor')
    store.startNode('executor')
    expect(store.steps).toHaveLength(1)
  })

  it('同名新一轮节点加序号', async () => {
    const store = await useStore()
    store.startNode('executor')
    store.finishNode('executor')
    store.startNode('executor')
    expect(store.steps).toHaveLength(2)
    expect(store.steps[1].label).toBe('Executor (2)')
  })

  it('finishAllNodes 把所有节点置为 done', async () => {
    const store = await useStore()
    store.startNode('planner')
    store.startNode('reviewer')
    store.finishAllNodes()
    expect(store.steps.every(s => s.status === 'done')).toBe(true)
  })

  it('addMessage 默认带时间戳', async () => {
    const store = await useStore()
    store.addMessage('user', '你好')
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].time).toBeTruthy()
  })

  it('_normMsg 规范化非法角色与空内容', async () => {
    const store = await useStore()
    const m = store._normMsg({ role: 'hacker', content: null })
    expect(m.role).toBe('assistant')
    expect(m.content).toBe('')
  })
})

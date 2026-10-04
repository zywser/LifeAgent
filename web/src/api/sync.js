import api from './request'

export function collectLifeData() {
  const today = new Date().toDateString()
  return {
    todos: JSON.parse(localStorage.getItem('lifeagent_todos') || '[]'),
    expenses: JSON.parse(localStorage.getItem('lifeagent_expenses') || '[]'),
    anniversaries: JSON.parse(localStorage.getItem('lifeagent_anniv') || '[]'),
    habits: JSON.parse(localStorage.getItem('lifeagent_habits') || '{}'),
    water: (JSON.parse(localStorage.getItem('lifeagent_water') || '{}'))[today] || 0,
    savings: JSON.parse(localStorage.getItem('lifeagent_savings') || '{}'),
    diary: JSON.parse(localStorage.getItem('lifeagent_diary') || '[]')
  }
}

export async function syncLife() {
  try {
    const { data } = await api.post('/sync/life', collectLifeData())
    console.log('[sync]', data)
    return data
  } catch (e) {
    console.warn('[sync] failed', e)
  }
}

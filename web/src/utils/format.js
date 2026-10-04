/**
 * 统一时间格式化工具
 * 所有前端显示时间的地方都应该从这里导入，避免格式混乱。
 */

const pad = n => String(n).padStart(2, '0')

/** 解析任意时间输入为 Date，失败返回 null */
function parse(t) {
  if (!t) return null
  if (t instanceof Date) return isNaN(t) ? null : t
  if (typeof t === 'number') return new Date(t)
  let s = String(t).trim()
  // 先直接解析：ISO 格式 "2026-09-30T14:30:00" 可以直接被 new Date() 识别
  let d = new Date(s)
  if (!isNaN(d)) return d
  // 失败再做兼容：把 "-" 换成 "/"、"T" 换成空格，兼容 "2026-09-30 14:30"、"2026/9/30 14:30:00" 等
  s = s.replace(/-/g, '/').replace('T', ' ')
  d = new Date(s)
  return isNaN(d) ? null : d
}

/** 2026-09-30 14:30 */
export function formatDateTime(t) {
  const d = parse(t)
  if (!d) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 2026-09-30 */
export function formatDate(t) {
  const d = parse(t)
  if (!d) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 14:30 */
export function formatTime(t) {
  const d = parse(t)
  if (!d) return ''
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 09-30 14:30（列表里省略年份，更紧凑） */
export function formatShort(t) {
  const d = parse(t)
  if (!d) return ''
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 相对时间：刚刚 / x分钟前 / x小时前 / 昨天 / x天前 / 具体日期 */
export function formatRelative(t) {
  const d = parse(t)
  if (!d) return ''
  const now = new Date()
  const diff = (now - d) / 1000 // 秒
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 172800) return '昨天'
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return formatDate(d)
}

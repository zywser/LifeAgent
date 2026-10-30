import { describe, it, expect } from 'vitest'
import {
  formatDateTime, formatDate, formatTime, formatShort, formatRelative
} from '../src/utils/format'

describe('format 时间工具', () => {
  const d = new Date(2026, 8, 30, 14, 5) // 本地时间 2026-09-30 14:05

  it('空值/非法输入返回空串', () => {
    expect(formatDateTime(null)).toBe('')
    expect(formatDate('')).toBe('')
    expect(formatTime('not-a-date')).toBe('')
    expect(formatShort(undefined)).toBe('')
  })

  it('formatDateTime 补零到分', () => {
    expect(formatDateTime(d)).toBe('2026-09-30 14:05')
  })

  it('formatDate 只到日', () => {
    expect(formatDate(d)).toBe('2026-09-30')
  })

  it('formatTime 只到分', () => {
    expect(formatTime(d)).toBe('14:05')
  })

  it('formatShort 省略年份', () => {
    expect(formatShort(d)).toBe('09-30 14:05')
  })

  it('接受 ISO 字符串', () => {
    expect(formatDate('2026-09-30T14:05:00')).toBe('2026-09-30')
  })

  it('formatRelative 对当前时间返回刚刚', () => {
    expect(formatRelative(new Date())).toBe('刚刚')
  })
})

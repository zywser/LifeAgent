import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ baseURL: '/life/api' })

// 防止多个并发请求同时触发 refresh
let isRefreshing = false
let failedQueue = []

function processQueue(error, token = null) {
  failedQueue.forEach(p => {
    if (error) p.reject(error)
    else p.resolve(token)
  })
  failedQueue = []
}

function clearAuthAndRedirect() {
  // 关键：refresh 失败后必须清掉 localStorage，
  // 否则整页刷新后 auth.user 仍为"已登录"，轮询又会触发 401 → 死循环
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  if (!window.__logging_out) {
    window.__logging_out = true
    window.location.href = '/life/login'
  }
}

api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  r => r,
  async error => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      // 已经有请求在刷新 token 了，把当前请求排队等刷新结果
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        }).catch(() => Promise.reject(error))
      }

      original._retry = true
      isRefreshing = true

      const rt = localStorage.getItem('refresh_token')
      if (!rt) {
        clearAuthAndRedirect()
        return Promise.reject(error)
      }

      try {
        // 注意：这里用裸 axios，不走 api 拦截器，避免 refresh 请求自己也触发 401 处理
        const { data } = await axios.post('/life/api/auth/refresh', { refresh_token: rt })
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        processQueue(null, data.access_token)
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        // refresh 失败（token 过期/被吊销）：清 token + 跳登录
        processQueue(new Error('refresh failed'), null)
        clearAuthAndRedirect()
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }
    // 全局错误提示：非 401、非 GET（轮询/加载类请求失败静默，避免刷屏）
    // 操作类请求（保存/删除/上传等）失败时让用户看到原因
    const method = (original?.method || 'get').toLowerCase()
    if (method !== 'get' && !error.__toasted) {
      error.__toasted = true
      const detail = error.response?.data?.detail
      const msg = typeof detail === 'string' && detail ? detail : (error.message || '请求失败，请稍后重试')
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default api

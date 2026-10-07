<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand"><span class="dot"></span> Life Agent</div>
      <h2>重置密码</h2>
      <p class="desc">通过邮件链接验证身份，设置新密码</p>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="新密码（至少 6 位）" size="large" show-password />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.confirm" type="password" placeholder="确认新密码" size="large" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" size="large" class="block" :loading="submitting">重置密码</el-button>
      </el-form>
      <div class="switch">想起来了？<router-link to="/login">去登录</router-link></div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/request'
const form = reactive({ password: '', confirm: '' })
const submitting = ref(false)
const route = useRoute()
const router = useRouter()
const token = route.query.token || ''
onMounted(() => { if (!token) { ElMessage.error('链接无效或已过期，请重新发送'); router.replace('/login') } })
async function submit() {
  if (!form.password) { ElMessage.warning('请输入新密码'); return }
  if (form.password.length < 6) { ElMessage.warning('新密码至少 6 位'); return }
  if (form.password !== form.confirm) { ElMessage.warning('两次输入的密码不一致'); return }
  submitting.value = true
  try {
    await api.post('/auth/reset_password', { token, new_password: form.password })
    ElMessage.success('密码已重置，请用新密码登录')
    router.push('/login')
  } catch { /* 全局拦截器已提示 */ }
  finally { submitting.value = false }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, var(--primary-bg) 0%, var(--bg) 100%); }
.auth-card { width: 380px; background: var(--card); border-radius: 18px; padding: 36px 32px; box-shadow: 0 10px 40px var(--shadow); }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 16px; color: var(--text); margin-bottom: 24px; }
.dot { width: 22px; height: 22px; border-radius: 50%; background: var(--primary); }
h2 { margin: 0 0 6px; font-size: 22px; }
.desc { margin: 0 0 22px; color: var(--text-3); font-size: 13px; }
.block { width: 100%; }
.switch { margin-top: 16px; text-align: center; font-size: 13px; color: var(--text-2); }
.switch a { color: var(--primary); text-decoration: none; }
</style>

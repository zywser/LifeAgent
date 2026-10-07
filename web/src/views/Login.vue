<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand"><span class="dot"></span> Life Agent</div>
      <h2>欢迎登录</h2>
      <p class="desc">多智能体生活管家，规划你的每一次出行</p>
      <el-form @submit.prevent="submit">
        <el-form-item><el-input v-model="form.email" placeholder="邮箱" size="large" /></el-form-item>
        <el-form-item><el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password /></el-form-item>
        <el-button type="primary" native-type="submit" size="large" class="block">登录</el-button>
      </el-form>
      <div class="extra">
        <span class="link" @click="forgotVisible = true">忘记密码？</span>
      </div>
      <div class="switch">还没有账号？<router-link to="/register">注册</router-link></div>
    </div>

    <!-- 忘记密码弹窗 -->
    <el-dialog v-model="forgotVisible" title="找回密码" width="400px" :close-on-click-modal="false">
      <p class="forgot-desc">输入注册邮箱，我们将发送一封含重置链接的邮件（1 小时内有效）</p>
      <el-input v-model="forgotEmail" placeholder="注册邮箱" size="large" />
      <template #footer>
        <el-button @click="forgotVisible = false">取消</el-button>
        <el-button type="primary" :loading="forgotSending" @click="sendForgot">发送邮件</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../api/request'
const form = reactive({ email: '', password: '' })
const router = useRouter()
const auth = useAuthStore()
async function submit() { await auth.login(form); router.push('/chat') }
const forgotVisible = ref(false)
const forgotEmail = ref('')
const forgotSending = ref(false)
async function sendForgot() {
  if (!forgotEmail.value) { ElMessage.warning('请先填写邮箱'); return }
  forgotSending.value = true
  try {
    await api.post('/auth/forgot_password', { email: forgotEmail.value })
    ElMessage.success('邮件已发送，请查收（未注册的邮箱不会收到邮件）')
    forgotVisible.value = false
    forgotEmail.value = ''
  } catch { /* 全局拦截器已提示 */ }
  finally { forgotSending.value = false }
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
.extra { margin-top: 12px; text-align: right; }
.link { font-size: 13px; color: var(--text-2); cursor: pointer; }
.link:hover { color: var(--primary); }
.forgot-desc { font-size: 13px; color: var(--text-2); margin: 0 0 14px; line-height: 1.7; }
</style>

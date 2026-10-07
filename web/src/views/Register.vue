<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand"><span class="dot"></span> Life Agent</div>
      <h2>创建账号</h2>
      <p class="desc">邮箱验证码激活后即可注册</p>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.email" placeholder="邮箱" size="large" />
        </el-form-item>
        <el-form-item>
          <div class="code-row">
            <el-input v-model="form.verify_code" placeholder="邮箱验证码" size="large" style="flex:1" />
            <el-button :disabled="countdown > 0 || !form.email" size="large" @click="sendCode">
              {{ countdown > 0 ? countdown + 's 后重发' : '发送验证码' }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" size="large" class="block" :disabled="sending">注册</el-button>
      </el-form>
      <div class="switch">已有账号？<router-link to="/login">去登录</router-link></div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../api/request'
const form = reactive({ email: '', password: '', verify_code: '' })
const countdown = ref(0)
const sending = ref(false)
let timer = null
const router = useRouter()
const auth = useAuthStore()
async function sendCode() {
  if (!form.email) { ElMessage.warning('请先填写邮箱'); return }
  sending.value = true
  try {
    await api.post('/auth/send_code', { email: form.email })
    ElMessage.success('验证码已发送，请查收邮件')
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) clearInterval(timer)
    }, 1000)
  } catch { /* 全局拦截器已提示错误 */ }
  finally { sending.value = false }
}
async function submit() {
  if (!form.verify_code) { ElMessage.warning('请填写邮箱验证码'); return }
  await auth.register(form)
  router.push('/chat')
}
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, var(--primary-bg) 0%, var(--bg) 100%); }
.auth-card { width: 380px; background: var(--card); border-radius: 18px; padding: 36px 32px; box-shadow: 0 10px 40px var(--shadow); }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 16px; color: var(--text); margin-bottom: 24px; }
.dot { width: 22px; height: 22px; border-radius: 50%; background: var(--primary); }
h2 { margin: 0 0 6px; font-size: 22px; }
.desc { margin: 0 0 22px; color: var(--text-3); font-size: 13px; }
.block { width: 100%; }
.code-row { display: flex; gap: 8px; width: 100%; }
.switch { margin-top: 16px; text-align: center; font-size: 13px; color: var(--text-2); }
.switch a { color: var(--primary); text-decoration: none; }
</style>
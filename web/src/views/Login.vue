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
      <div class="switch">还没有账号？<router-link to="/register">注册</router-link></div>
    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
const form = reactive({ email: '', password: '' })
const router = useRouter()
const auth = useAuthStore()
async function submit() { await auth.login(form); router.push('/chat') }
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

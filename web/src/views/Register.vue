<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand"><span class="dot"></span> Life Agent</div>
      <h2>创建账号</h2>
      <p class="desc">注册后即可上传笔记、发起智能任务</p>
      <el-form @submit.prevent="submit">
        <el-form-item><el-input v-model="form.email" placeholder="邮箱" size="large" /></el-form-item>
        <el-form-item><el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password /></el-form-item>
        <el-button type="primary" native-type="submit" size="large" class="block">注册</el-button>
      </el-form>
      <div class="switch">已有账号？<router-link to="/login">去登录</router-link></div>
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
async function submit() { await auth.register(form); router.push('/chat') }
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #eff6ff 0%, #f3f5f9 100%); }
.auth-card { width: 380px; background: #fff; border-radius: 18px; padding: 36px 32px; box-shadow: 0 10px 40px rgba(37,99,235,.08); }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 16px; color: #111827; margin-bottom: 24px; }
.dot { width: 22px; height: 22px; border-radius: 50%; background: #2563eb; }
h2 { margin: 0 0 6px; font-size: 22px; }
.desc { margin: 0 0 22px; color: #9ca3af; font-size: 13px; }
.block { width: 100%; }
.switch { margin-top: 16px; text-align: center; font-size: 13px; color: #6b7280; }
.switch a { color: #2563eb; text-decoration: none; }
</style>

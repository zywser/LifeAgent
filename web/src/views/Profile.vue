<template>
  <div class="page">
    <!-- 个人资料卡片 -->
    <div class="card profile-card">
      <div class="hero">
        <img v-if="avatarSrc" :src="avatarSrc" class="avatar avatar-img" alt="" />
        <div v-else class="avatar" :style="{background: avatarColor}">{{ nickname.slice(0,1).toUpperCase() }}</div>
        <div class="hero-info">
          <h2>{{ nickname }}</h2>
          <p>{{ userEmail }}</p>
        </div>
        <el-button @click="editVisible = true">编辑资料</el-button>
      </div>
    </div>

    <!-- 数据统计 -->
    <div class="stat-grid">
      <div class="stat"><div class="stat-num">{{ noteCount }}</div><div class="stat-label">已存笔记</div></div>
      <div class="stat"><div class="stat-num">{{ expenseCount }}</div><div class="stat-label">记账笔数</div></div>
      <div class="stat"><div class="stat-num">¥{{ weekSpent }}</div><div class="stat-label">累计支出</div></div>
      <div class="stat"><div class="stat-num">¥{{ earned }}</div><div class="stat-label">累计收入</div></div>
      <div class="stat"><div class="stat-num">{{ todoCount }}</div><div class="stat-label">待办总数</div></div>
      <div class="stat"><div class="stat-num">{{ convCount }}</div><div class="stat-label">历史会话</div></div>
    </div>

    <!-- AI 印象 -->
    <div class="card impression">
      <div class="imp-head">
        <div>
          <h3>🤖 我的 AI 印象</h3>
          <p class="imp-sub">Agent 根据和你的对话、笔记、生活数据生成的画像</p>
        </div>
        <el-button type="primary" :loading="impressing" @click="genImpression">
          {{ impression ? '重新生成' : '生成 AI 印象' }}
        </el-button>
      </div>
      <div v-if="impression" class="imp-body">{{ impression }}</div>
      <div v-else class="imp-empty">还没有生成，点上面按钮让 Agent 认识你</div>
    </div>

    <!-- 设置 -->
    <div class="section">
      <h3>常用功能</h3>
      <div class="actions">
        <button class="action" @click="$router.push('/chat')">
          <span class="a-icon">💬</span>
          <div><div class="a-title">继续对话</div><div class="a-desc">和多智能体聊聊今天的计划</div></div>
        </button>
        <button class="action" @click="$router.push('/notes')">
          <span class="a-icon">📚</span>
          <div><div class="a-title">管理资料</div><div class="a-desc">上传笔记，让 Agent 更懂你</div></div>
        </button>
        <button class="action" @click="$router.push('/accounting')">
          <span class="a-icon">💰</span>
          <div><div class="a-title">查看账单</div><div class="a-desc">回顾近期消费记录</div></div>
        </button>
        <button class="action" @click="logout">
          <span class="a-icon">🚪</span>
          <div><div class="a-title">退出登录</div><div class="a-desc">当前账号：{{ userEmail }}</div></div>
        </button>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑资料" width="400px">
      <el-form label-width="80px">
        <el-form-item label="昵称">
          <el-input v-model="nicknameInput" placeholder="给自己起个名字" />
        </el-form-item>
        <el-form-item label="头像">
          <el-upload :show-file-list="false" :before-upload="beforeAvatar" accept="image/*">
            <div class="avatar-uploader">
              <img v-if="avatarInput" :src="avatarInputSrc" class="avatar-preview" alt="" />
              <div v-else class="avatar-placeholder">点击上传</div>
            </div>
            <div class="avatar-tip">支持 jpg/png/webp/gif，不超过 5MB，选图后可裁剪</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="头像颜色">
          <el-color-picker v-model="avatarColorInput" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveProfile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 头像裁剪弹窗 -->
    <el-dialog v-model="cropVisible" title="裁剪头像" width="440px" :close-on-click-modal="false" @opened="initCropper" @closed="destroyCropper">
      <div class="crop-wrap">
        <img id="crop-img" :src="cropSrc" alt="" />
      </div>
      <p class="crop-tip">拖拽移动选区 · 滚轮或拖动边角调整大小 · 头像将按 1:1 正方形保存</p>
      <template #footer>
        <el-button @click="cropVisible = false">取消</el-button>
        <el-button type="primary" :loading="cropSaving" @click="onCropSave">保存头像</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/request'
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'

const auth = useAuthStore(); const router = useRouter()
const userEmail = ref('')
const noteCount = ref(0); const expenseCount = ref(0)
const weekSpent = ref('0.00'); const earned = ref('0.00')
const convCount = ref(0); const todoCount = ref(0)

const nickname = ref('我')
const avatarColor = ref('#2563eb')
const impression = ref('')
const impressing = ref(false)
const editVisible = ref(false)
const nicknameInput = ref('')
const avatarColorInput = ref('#2563eb')
const avatar = ref('')
const avatarInput = ref('')
const avatarSrc = computed(() => avatar.value ? '/api/' + avatar.value : '')
const avatarInputSrc = computed(() => avatarInput.value ? '/api/' + avatarInput.value : '')

onMounted(async () => {
  userEmail.value = localStorage.getItem('user_email') || auth.user || ''
  const saved = JSON.parse(localStorage.getItem('lifeagent_profile') || '{}')
  nickname.value = saved.nickname || auth.user || (userEmail.value.split('@')[0] || '我')
  avatarColor.value = saved.avatarColor || '#2563eb'
  avatar.value = saved.avatar || ''
  try { const { data } = await api.get('/notes/stats'); noteCount.value = data.note_count } catch {}
  try {
    const exps = (await api.get('/life/expenses')).data
    expenseCount.value = exps.length
    weekSpent.value = exps.filter(e=>e.kind!=='income').reduce((s,r)=>s+Number(r.amount),0).toFixed(2)
    earned.value = exps.filter(e=>e.kind==='income').reduce((s,r)=>s+Number(r.amount),0).toFixed(2)
  } catch {}
  try { todoCount.value = (await api.get('/life/todos')).data.length } catch {}
  convCount.value = JSON.parse(localStorage.getItem('lifeagent_conversations') || '[]').length
})

function openEdit(){
  nicknameInput.value = nickname.value
  avatarColorInput.value = avatarColor.value
  avatarInput.value = avatar.value
  editVisible.value = true
}
// 让点"编辑资料"打开弹窗
import { watch } from 'vue'
watch(editVisible, v => { if(v) openEdit() })

function saveProfile(){
  nickname.value = nicknameInput.value || '我'
  avatarColor.value = avatarColorInput.value
  if (avatarInput.value) avatar.value = avatarInput.value
  localStorage.setItem('lifeagent_profile', JSON.stringify({ nickname: nickname.value, avatarColor: avatarColor.value, avatar: avatar.value }))
  window.dispatchEvent(new Event('profile-updated'))
  editVisible.value = false
}
function beforeAvatar(file){
  if (file.size > 5 * 1024 * 1024) { alert('图片不能超过 5MB'); return false }
  if (!['image/jpeg','image/png','image/webp','image/gif'].includes(file.type)) { alert('仅支持 jpg/png/webp/gif'); return false }
  cropFile = file
  cropSrc.value = URL.createObjectURL(file)
  cropVisible.value = true
  return false // 阻止直接上传，先进入裁剪
}
// ===== 头像裁剪 =====
const cropVisible = ref(false)
const cropSrc = ref('')
const cropSaving = ref(false)
let cropper = null
let cropFile = null
function initCropper(){
  if (!cropSrc.value) return
  const img = document.getElementById('crop-img')
  if (!img) return
  if (cropper) cropper.destroy()
  cropper = new Cropper(img, {
    aspectRatio: 1,          // 1:1 正方形，适配圆形头像
    viewMode: 1,             // 选区不能超出画布
    dragMode: 'move',
    autoCropArea: 0.9,
    background: false,
    guides: true,
    center: true,
    highlight: false,
    responsive: true
  })
}
function destroyCropper(){
  if (cropper) { cropper.destroy(); cropper = null }
  if (cropSrc.value) { URL.revokeObjectURL(cropSrc.value); cropSrc.value = '' }
  cropFile = null
}
async function onCropSave(){
  if (!cropper || !cropFile) return
  cropSaving.value = true
  try {
    const canvas = cropper.getCroppedCanvas({ width: 512, height: 512, imageSmoothingQuality: 'high' })
    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.92))
    const fd = new FormData()
    fd.append('file', blob, 'avatar-' + Date.now() + '.jpg')
    const { data } = await api.post('/profile/avatar', fd)
    avatarInput.value = data.avatar
    cropVisible.value = false
    alert('头像已更新')
  } catch(e) { alert('上传失败：' + (e.response?.data?.detail || e.message)) }
  finally { cropSaving.value = false }
}
async function genImpression(){
  impressing.value = true
  try {
    const { data } = await api.post('/profile/impression')
    impression.value = data.impression
  } catch(e) { impression.value = '生成失败：' + (e.response?.data?.detail || e.message) }
  impressing.value = false
}

function logout(){ auth.logout(); router.push('/login') }
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; width: 100%; }
.card { background: var(--card); border-radius: 16px; padding: 28px; box-shadow: 0 1px 3px var(--shadow); margin-bottom: 20px; }
.hero { display: flex; align-items: center; gap: 18px; }
.avatar { width: 64px; height: 64px; border-radius: 50%; color: #fff; font-size: 26px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.avatar-img { object-fit: cover; }
.hero-info { flex: 1; }
.hero-info h2 { margin: 0; font-size: 20px; color: var(--text); }
.hero-info p { margin: 4px 0 0; font-size: 13px; color: var(--text-2); }

.stat-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; margin-bottom: 24px; }
.stat { background: var(--card); border-radius: 12px; padding: 18px 10px; text-align: center; }
.stat-num { font-size: 22px; font-weight: 700; color: var(--primary); }
.stat-label { font-size: 12px; color: var(--text-2); margin-top: 4px; }

.impression { background: linear-gradient(135deg, var(--primary-bg) 0%, var(--card) 100%); border: 1px solid var(--primary-border); }
.imp-head { display: flex; justify-content: space-between; align-items: flex-start; }
.imp-head h3 { margin: 0; font-size: 17px; color: var(--text); }
.imp-sub { font-size: 12px; color: var(--text-2); margin: 4px 0 0; }
.imp-body { margin-top: 16px; font-size: 14px; line-height: 1.9; color: var(--text); white-space: pre-wrap; }
.imp-empty { margin-top: 16px; color: var(--text-3); font-size: 13px; text-align: center; padding: 20px; }
.stat-num { font-size: 22px; font-weight: 700; color: var(--primary); }
.stat-label { font-size: 12px; color: var(--text-2); margin-top: 4px; }

.section h3 { font-size: 15px; color: var(--text); margin: 0 0 12px; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.action {
  display: flex; align-items: center; gap: 14px;
  background: var(--card); border: none; border-radius: 12px;
  padding: 16px; cursor: pointer; text-align: left;
  transition: all .15s;
}
.action:hover { box-shadow: 0 4px 12px var(--shadow); transform: translateY(-1px); }
.a-icon { font-size: 24px; }
.a-title { font-size: 14px; font-weight: 600; color: var(--text); }
.a-desc { font-size: 12px; color: var(--text-2); margin-top: 2px; }
.avatar-uploader { width: 64px; height: 64px; border-radius: 50%; border: 1px dashed var(--primary-border); background: var(--primary-bg); display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: pointer; }
.avatar-preview { width: 100%; height: 100%; object-fit: cover; }
.avatar-placeholder { font-size: 11px; color: var(--primary); text-align: center; line-height: 1.4; }
.avatar-tip { font-size: 11px; color: var(--text-3); margin-top: 4px; }
.crop-wrap { max-height: 330px; display: flex; justify-content: center; background: #f3f4f6; border-radius: 8px; overflow: hidden; }
.crop-wrap img { max-width: 100%; max-height: 330px; display: block; }
.crop-tip { font-size: 12px; color: var(--text-2); text-align: center; margin: 12px 0 0; }

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 600px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .actions { grid-template-columns: 1fr; }
  .hero { flex-direction: column; align-items: flex-start; }
}
</style>

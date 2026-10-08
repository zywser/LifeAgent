import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import ResetPassword from '../views/ResetPassword.vue'
import Chat from '../views/Chat.vue'
import NotesManage from '../views/NotesManage.vue'
import AgentGraph from '../views/AgentGraph.vue'
import History from '../views/History.vue'
import Home from '../views/Home.vue'
import Accounting from '../views/Accounting.vue'
import Profile from '../views/Profile.vue'
import Memory from '../views/Memory.vue'
import Todo from '../views/Todo.vue'
import Habit from '../views/Habit.vue'
import Diary from '../views/Diary.vue'
import Water from '../views/Water.vue'
import Savings from '../views/Savings.vue'
import Anniversary from '../views/Anniversary.vue'

const router = createRouter({
  history: createWebHistory('/life/'),
  routes: [
    { path: '/login', component: Login },
    { path: '/register', component: Register },
    { path: '/reset-password', component: ResetPassword },
    { path: '/', redirect: '/home' },
    { path: '/home', component: Home, meta: { auth: true } },
    { path: '/chat', component: Chat, meta: { auth: true } },
    // 历史会话独立路由（豆包/DeepSeek 式）：每个对话一个 URL，双标签页/多端打开互不干扰
    { path: '/chat/s/:id', component: Chat, meta: { auth: true } },
    { path: '/graph', component: AgentGraph, meta: { auth: true } },
    { path: '/notes', component: NotesManage, meta: { auth: true } },
    { path: '/history', component: History, meta: { auth: true } },
    { path: '/accounting', component: Accounting, meta: { auth: true } },
    { path: '/profile', component: Profile, meta: { auth: true } },
    { path: '/memory', component: Memory, meta: { auth: true } },
    { path: '/todo', component: Todo, meta: { auth: true } },
    { path: '/habit', component: Habit, meta: { auth: true } },
    { path: '/diary', component: Diary, meta: { auth: true } },
    { path: '/water', component: Water, meta: { auth: true } },
    { path: '/savings', component: Savings, meta: { auth: true } },
    { path: '/anniversary', component: Anniversary, meta: { auth: true } }
  ]
})
router.beforeEach((to) => {
  if (to.meta.auth && !localStorage.getItem('access_token')) return '/login'
})
export default router

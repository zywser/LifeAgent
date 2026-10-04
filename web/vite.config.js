import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue({ include: /\.vue$/ })], server: { port: 5173, host: '0.0.0.0', proxy: { '/api': { target:'http://localhost:8000', rewrite:(p)=>p.replace(/^\/api/,'') } } } })

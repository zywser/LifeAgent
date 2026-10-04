import api from './request'; export const login=p=>api.post('/auth/login',p); export const register=p=>api.post('/auth/register',p)

import api from './request'

export const listConversations = () => api.get('/conversations')
export const saveConversation = (payload) => api.post('/conversations', payload)
export const getConversation = (id) => api.get(`/conversations/${id}`)
export const deleteConversation = (id) => api.delete(`/conversations/${id}`)

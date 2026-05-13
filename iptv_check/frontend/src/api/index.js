import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

export const getInfo = () => api.get('/info')
export const getIsp = () => api.get('/isp')
export const refreshIsp = () => api.post('/isp/refresh')
export const getOnlineSources = () => api.get('/online-sources')
export const startCheck = (data) => api.post('/check/start', data)
export const stopCheck = () => api.post('/check/stop')
export const getResults = (params) => api.get('/results', { params })
export const getResultsStats = () => api.get('/results/stats')
export const exportResults = (data) => api.post('/export', data)
export const convertFormat = (data) => api.post('/convert', data)
export const smartOptimize = () => api.post('/optimize')
export const uploadFile = (data) => api.post('/upload', data)

export function createWebSocket(onMessage) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${location.host}/ws`)
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  ws.onerror = (err) => {
    console.warn('WebSocket error:', err)
  }
  ws.onclose = () => {
    setTimeout(() => createWebSocket(onMessage), 3000)
  }
  return ws
}

export default api

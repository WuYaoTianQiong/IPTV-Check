import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.message || err.response?.data?.detail || err.message
    if (status === 400) console.warn('请求参数错误:', msg)
    else if (status === 404) console.warn('资源不存在:', msg)
    else if (status === 500) console.error('服务器错误:', msg)
    else if (status === 429) console.warn('请求过于频繁')
    else if (!err.response) console.error('网络连接失败:', msg)
    return Promise.reject(err)
  }
)

export const getInfo = () => api.get('/info')
export const getIsp = () => api.get('/isp')
export const refreshIsp = () => api.post('/isp/refresh')
export const getOnlineSources = () => api.get('/online-sources')
export const startCheck = (data) => api.post('/check/start', data)
export const stopCheck = () => api.post('/check/stop')
export const getCheckState = () => api.get('/check/state')
export const getResults = (params) => api.get('/results', { params })
export const getResultsStats = () => api.get('/results/stats')
export const getCheckHistory = (limit = 20) => api.get('/results/history', { params: { limit } })
export const saveResults = () => api.post('/results/save')
export const exportResults = (data) => api.post('/export', data)
export const convertFormat = (data) => api.post('/convert', data)
export const convertText = (data) => api.post('/convert-text', data)
export const smartOptimize = () => api.post('/optimize')
export const uploadFile = (data) => api.post('/upload', data)

export const getFavorites = () => api.get('/favorites')
export const addFavorite = (data) => api.post('/favorites', data)
export const removeFavorite = (id) => api.delete(`/favorites/${id}`)

export const getQualityReport = () => api.get('/report')

export const startM3uServer = () => api.post('/m3u/start')
export const stopM3uServer = () => api.post('/m3u/stop')
export const getM3uState = () => api.get('/m3u/state')
export const getAvailablePorts = () => api.get('/available-ports')

export const getMediaProbeStatus = () => api.get('/settings/media-probe')
export const setMediaProbeStatus = (enabled) => api.post(`/settings/media-probe?enabled=${enabled}`)
export const getMediaProbeFullStatus = () => api.get('/settings/media-probe/status')

export const getChannelTrend = (channelId, days = 7) => api.get(`/trends/channel/${channelId}`, { params: { days } })
export const getTopStableChannels = (days = 7, limit = 50) => api.get('/trends/stable-channels', { params: { days, limit } })
export const compareHistory = (h1, h2) => api.get('/trends/history-compare', { params: { h1, h2 } })

export const getProxyStats = () => api.get('/proxy/stats')

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

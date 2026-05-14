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
export const getCategoryTree = (params = {}) => api.get('/results/category-tree', { params })
export const getAvailableLanguages = () => api.get('/results/languages')
export const getSourceHealth = () => api.get('/results/source-health')
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

export const getRecommendations = (maxPerGroup = 3) => api.get('/recommend', { params: { max_per_group: maxPerGroup } })
export const getRecommendM3u = (maxPerGroup = 3) => api.get('/recommend/m3u', { params: { max_per_group: maxPerGroup }, responseType: 'blob' })
export const getIspRecommendations = (targetIsp = null) => api.get('/recommend/isp', { params: { target_isp: targetIsp } })

export const getChannelEpg = (channelName, params = {}) => api.get(`/epg/channel/${encodeURIComponent(channelName)}`, { params })
export const getCurrentPrograms = (sourceId = '') => api.get('/epg/now', { params: { source_id: sourceId } })
export const refreshEpg = (sourceId) => api.post('/epg/refresh', { source_id: sourceId })
export const getEpgStats = () => api.get('/epg/stats')
export const loadAllEpg = () => api.post('/epg/load')

export const getLogo = (channelName, params = {}) => api.get(`/logos/${encodeURIComponent(channelName)}`, { params, responseType: 'blob' })
export const batchDownloadLogos = (channels, sourceId = '') => api.post('/logos/download', { channels, source_id: sourceId })
export const getLogoStats = () => api.get('/logos/stats')
export const cleanupLogos = (maxAgeDays = 30) => api.post(`/logos/cleanup?max_age_days=${maxAgeDays}`)

export const getCacheStats = () => api.get('/cache/stats')
export const clearCache = (namespace = '') => api.post(`/cache/clear?namespace=${namespace}`)

export const getCheckProgress = () => api.get('/check/progress')

export const sseStatus = { connected: false, reconnecting: false }

export function createSSEConnection(onMessage) {
  const url = '/api/events/stream'
  const es = new EventSource(url)

  sseStatus.connected = true
  sseStatus.reconnecting = false

  es.onopen = () => {
    sseStatus.connected = true
    sseStatus.reconnecting = false
  }

  es.addEventListener('init', (e) => {
    try { onMessage({ event: 'init', ...JSON.parse(e.data) }) } catch {}
  })

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onMessage(data)
    } catch {}
  }

  es.onerror = () => {
    sseStatus.connected = false
    sseStatus.reconnecting = true
  }

  return es
}

export default api

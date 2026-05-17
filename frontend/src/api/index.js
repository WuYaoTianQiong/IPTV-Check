import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

let _toastFn = null

export function setToastHandler(fn) {
  _toastFn = fn
}

function showToast(message, type = 'error') {
  if (_toastFn) _toastFn(message, type)
}

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.error?.message || err.response?.data?.message || err.response?.data?.detail || err.message
    if (status === 400) {
      showToast(msg || '请求参数错误', 'warning')
    } else if (status === 404) {
      showToast(msg || '资源不存在', 'warning')
    } else if (status === 429) {
      showToast('请求过于频繁，请稍后再试', 'warning')
    } else if (status === 502 || status === 503) {
      showToast('服务暂时不可用，请稍后重试', 'error')
    } else if (status === 500) {
      showToast(msg || '服务器内部错误', 'error')
    } else if (!err.response) {
      showToast('网络连接失败，请检查服务是否启动', 'error')
    }
    return Promise.reject(err)
  }
)

export const getInfo = () => api.get('/info')
export const getIsp = () => api.get('/isp')
export const refreshIsp = () => api.post('/isp/refresh')
export const getOnlineSources = () => api.get('/online-sources')
export const startCheck = (data) => api.post('/check/start', data)
export const checkFromFetched = (data) => api.post('/check/from-fetched', data)
export const stopCheck = () => api.post('/check/stop')
export const getCheckState = () => api.get('/check/state')
export const getResults = (params) => api.get('/results', { params })
export const getCategoryTree = (params = {}) => api.get('/results/category-tree', { params })
export const getAvailableLanguages = () => api.get('/results/languages')
export const getAvailableCountries = () => api.get('/results/countries')
export const getAvailableRegions = () => api.get('/results/regions')
export const getSourceHealth = () => api.get('/results/source-health')
export const getResultsStats = () => api.get('/results/stats')
export const getCheckHistory = (limit = 20) => api.get('/results/history', { params: { limit } })
export const saveResults = () => api.post('/results/save')
export const exportResults = (data) => api.post('/export', data)
export const convertFormat = (data) => api.post('/convert', data)
export const convertText = (data) => api.post('/convert-text', data)
export const smartOptimize = () => api.post('/optimize')
export const uploadFile = (data) => api.post('/upload', data)

export const getFavorites = (params = {}) => api.get('/favorites', { params })
export const addFavorite = (data) => api.post('/favorites', data)
export const removeFavorite = (id) => api.delete(`/favorites/${id}`)
export const updateFavorite = (id, data) => api.put(`/favorites/${id}`, data)
export const exportFavoritesM3u = () => api.get('/favorites/m3u', { responseType: 'blob' })

export const getFavoriteFolders = () => api.get('/favorite-folders')
export const createFavoriteFolder = (data) => api.post('/favorite-folders', data)
export const updateFavoriteFolder = (id, data) => api.put(`/favorite-folders/${id}`, data)
export const deleteFavoriteFolder = (id) => api.delete(`/favorite-folders/${id}`)

export const getCustomChannels = () => api.get('/custom-channels')
export const addCustomChannel = (data) => api.post('/custom-channels', data)
export const deleteCustomChannel = (id) => api.delete(`/custom-channels/${id}`)

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

export const startScheduler = (data) => api.post('/scheduler/start', data)
export const stopScheduler = () => api.post('/scheduler/stop')
export const getSchedulerState = () => api.get('/scheduler/state')

export const triggerSourceSync = (data = {}) => api.post('/source-sync/trigger', data)
export const getSourceSyncStatus = () => api.get('/source-sync/status')
export const getSourceSyncProgress = () => api.get('/source-sync/progress')
export const startSourceSyncScheduler = (data = {}) => api.post('/source-sync/scheduler/start', data)
export const stopSourceSyncScheduler = () => api.post('/source-sync/scheduler/stop')
export const getSourceSyncSchedulerState = () => api.get('/source-sync/scheduler/state')

export const getUserSettings = () => api.get('/settings')
export const updateUserSettings = (data) => api.post('/settings', data)

export const getCheckProgress = () => api.get('/check/progress')

export const startFetch = (data) => api.post('/fetch/start', data)
export const getFetchProgress = () => api.get('/fetch/progress')
export const getFetchedChannels = () => api.get('/fetch/channels')
export const clearFetchedChannels = () => api.delete('/fetch/channels')

export const getLiveChannels = (params = {}) => api.get('/live-channels', { params })

export const sseStatus = { connected: false, reconnecting: false }

export function createSSEConnection(onMessage) {
  const url = '/api/events/stream'
  let es = null
  let retryCount = 0
  const maxRetryDelay = 30000
  const baseRetryDelay = 1000

  console.log('[SSE] 创建连接, URL:', url)

  function connect() {
    es = new EventSource(url)

    sseStatus.connected = true
    sseStatus.reconnecting = false

    console.log('[SSE] 连接已建立')

    es.onopen = () => {
      console.log('[SSE] onopen 触发')
      sseStatus.connected = true
      sseStatus.reconnecting = false
      retryCount = 0
    }

    es.addEventListener('init', (e) => {
      console.log('[SSE] 收到 init 事件')
      try { onMessage({ event: 'init', ...JSON.parse(e.data) }) } catch {}
    })

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        console.log('[SSE] onmessage 收到:', data.event, data)
        onMessage(data)
      } catch (err) {
        console.error('[SSE] 解析消息失败:', err)
      }
    }

    es.onerror = () => {
      console.error('[SSE] onerror 触发, retryCount:', retryCount)
      sseStatus.connected = false
      sseStatus.reconnecting = true
      es.close()
      retryCount++
      const delay = Math.min(baseRetryDelay * Math.pow(2, retryCount - 1), maxRetryDelay)
      console.log('[SSE] 将在', delay, 'ms 后重连')
      setTimeout(connect, delay)
    }
  }

  connect()

  return {
    close: () => { 
      console.log('[SSE] 连接已关闭')
      if (es) es.close() 
    }
  }
}

export default api

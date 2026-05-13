import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getInfo,
  getIsp,
  refreshIsp,
  getOnlineSources,
  getResults,
  getResultsStats,
  getM3uState,
  startM3uServer,
  stopM3uServer,
  getMediaProbeFullStatus,
} from '../api'

export const useAppStore = defineStore('app', () => {
  const appInfo = ref({})
  const localIsp = ref('检测中...')
  const onlineSources = ref([])
  const isChecking = ref(false)
  const checkTotal = ref(0)
  const checkedCount = ref(0)
  const validCount = ref(0)
  const invalidCount = ref(0)
  const checkResults = ref([])
  const resultsPage = ref(1)
  const resultsTotal = ref(0)
  const resultsPerPage = ref(50)
  const currentTab = ref('all')
  const searchQuery = ref('')
  const activeView = ref('source')
  const logs = ref([])
  const m3uState = ref({ running: false, url: '', file_exists: false, valid_channels: 0 })
  const mediaProbeStatus = ref({ enabled: false, ffmpeg_available: false, usable: false })

  const progress = computed(() =>
    checkTotal.value ? Math.round((checkedCount.value / checkTotal.value) * 100) : 0
  )
  const validRate = computed(() =>
    checkedCount.value ? Math.round((validCount.value / checkedCount.value) * 100) : 0
  )
  const currentStatus = computed(() => {
    if (!isChecking.value) return '准备就绪'
    if (checkTotal.value === 0) return '正在加载直播源...'
    if (checkedCount.value === 0) return `已加载 ${checkTotal.value} 个频道，正在检测...`
    return `检测中: ${checkedCount.value}/${checkTotal.value}`
  })

  async function fetchInfo() {
    const { data } = await getInfo()
    appInfo.value = data
    localIsp.value = data.local_isp
    isChecking.value = data.is_checking
  }

  async function fetchIsp() {
    const { data } = await getIsp()
    localIsp.value = data.local_isp
  }

  async function doRefreshIsp() {
    const { data } = await refreshIsp()
    localIsp.value = data.local_isp
  }

  async function fetchOnlineSources() {
    const { data } = await getOnlineSources()
    onlineSources.value = data.sources
    if (data.local_isp) localIsp.value = data.local_isp
  }

  async function fetchResults() {
    const { data } = await getResults({
      tab: currentTab.value,
      page: resultsPage.value,
      per_page: resultsPerPage.value,
      search: searchQuery.value,
    })
    checkResults.value = data.items
    resultsTotal.value = data.total
  }

  async function fetchStats() {
    const { data } = await getResultsStats()
    checkTotal.value = data.total
    checkedCount.value = data.checked
    validCount.value = data.valid
    invalidCount.value = data.invalid
    isChecking.value = data.is_running
  }

  async function fetchM3uState() {
    try {
      const { data } = await getM3uState()
      m3uState.value = data
    } catch {
      m3uState.value = { running: false, url: '', file_exists: false, valid_channels: 0 }
    }
  }

  async function doStartM3u() {
    const { data } = await startM3uServer()
    await fetchM3uState()
    return data
  }

  async function doStopM3u() {
    await stopM3uServer()
    m3uState.value = { running: false, url: '', file_exists: false, valid_channels: 0 }
  }

  async function fetchMediaProbeStatus() {
    try {
      const { data } = await getMediaProbeFullStatus()
      mediaProbeStatus.value = data
    } catch {
      mediaProbeStatus.value = { enabled: false, ffmpeg_available: false, usable: false }
    }
  }

  function addLog(message, type = 'info') {
    logs.value.push({
      id: Date.now() + Math.random(),
      message,
      type,
      time: new Date().toLocaleTimeString(),
    })
    if (logs.value.length > 500) {
      logs.value = logs.value.slice(-300)
    }
  }

  function clearLogs() {
    logs.value = []
  }

  function handleWsMessage(msg) {
    const { event } = msg
    if (event === 'channel_checked') {
      checkedCount.value++
      if (msg.is_valid) validCount.value++
      else invalidCount.value++
    } else if (event === 'check_completed') {
      isChecking.value = false
      addLog(`检测完成 | 总计: ${checkTotal.value} | 有效: ${validCount.value} | 无效: ${invalidCount.value}`, 'info')
    } else if (event === 'check_started') {
      isChecking.value = true
      checkTotal.value = msg.total || 0
      checkedCount.value = 0
      validCount.value = 0
      invalidCount.value = 0
      addLog('检测开始', 'info')
    } else if (event === 'channels_loaded') {
      checkTotal.value = msg.total
      addLog(`共加载 ${msg.total} 个频道，开始检测`, 'info')
    } else if (event === 'check_stopped') {
      isChecking.value = false
      addLog('检测已停止', 'warning')
    }
  }

  return {
    appInfo,
    localIsp,
    onlineSources,
    isChecking,
    checkTotal,
    checkedCount,
    validCount,
    invalidCount,
    checkResults,
    resultsPage,
    resultsTotal,
    resultsPerPage,
    currentTab,
    searchQuery,
    activeView,
    logs,
    m3uState,
    mediaProbeStatus,
    progress,
    validRate,
    currentStatus,
    fetchInfo,
    fetchIsp,
    doRefreshIsp,
    fetchOnlineSources,
    fetchResults,
    fetchStats,
    fetchM3uState,
    doStartM3u,
    doStopM3u,
    fetchMediaProbeStatus,
    addLog,
    clearLogs,
    handleWsMessage,
  }
})

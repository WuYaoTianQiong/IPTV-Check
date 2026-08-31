import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getInfo,
  getIsp,
  refreshIsp,
  getM3uState,
  startM3uServer,
  stopM3uServer,
  getMediaProbeFullStatus,
  createSSEConnection,
  loadAllEpg,
  saveResults,
} from '../api'
import { useToast } from '../composables/useToast'
import { useSourceStore } from './source'
import { useCheckStore } from './check'
import { useResultStore } from './result'

export const useAppStore = defineStore('app', () => {
  const appInfo = ref({})
  const localIsp = ref('检测中...')
  const m3uState = ref({ running: false, url: '', file_exists: false, valid_channels: 0 })
  const mediaProbeStatus = ref({ enabled: false, ffmpeg_available: false, usable: false })
  const syncProgress = ref({ is_syncing: false, stage: '', current_url_index: 0, total_urls: 0, current_url_label: '', fetched_channel_count: 0, added: 0, updated: 0, elapsed_seconds: 0, eta_seconds: null })
  const refreshLatencyProgress = ref({ checked: 0, total: 0, updated: 0 })
  const isRefreshLatencyRunning = ref(false)

  let ispCheckTimeout = null
  const ISP_CHECK_TIMEOUT = 10000

  const sourceStore = useSourceStore()
  const checkStore = useCheckStore()
  const resultStore = useResultStore()
  const { toast } = useToast()

  const isChecking = computed(() => checkStore.isChecking)
  const onlineSources = computed(() => sourceStore.onlineSources)
  const checkResults = computed(() => resultStore.checkResults)

  function showToast(message, type = 'error') {
    const typeMethodMap = {
      success: toast.success,
      error: toast.error,
      warning: toast.warning,
      info: toast.info,
    }
    const method = typeMethodMap[type] || toast.error
    method(message)
  }

  async function fetchInfo() {
    const { data } = await getInfo()
    appInfo.value = data
    localIsp.value = data.local_isp
    checkStore.isChecking = data.is_checking

    if (data.local_isp === '未知' || data.local_isp === '检测中...') {
      startIspCheckTimeout()
    }
  }

  async function fetchIsp() {
    const { data } = await getIsp()
    localIsp.value = data.local_isp
  }

  async function doRefreshIsp() {
    try {
      const previousIsp = localIsp.value
      localIsp.value = '检测中...'
      const { data } = await refreshIsp()
      localIsp.value = data.local_isp
      
      if (data.local_isp !== previousIsp) {
        toast.success('运营商检测完成', `当前运营商：${data.local_isp}`)
      } else {
        toast.info('运营商未变化', `当前运营商：${data.local_isp}`)
      }
    } catch (e) {
      localIsp.value = '检测失败'
      toast.error('运营商检测失败', e.message || '请稍后重试')
    }
  }

  async function fetchOnlineSources() {
    return sourceStore.fetchOnlineSources()
  }

  async function fetchResults(params = {}) {
    return resultStore.fetchResults(params)
  }

  async function fetchStats() {
    const { data } = await getResultsStats()
    checkStore.checkTotal.value = data.total
    checkStore.checkedCount.value = data.checked
    checkStore.validCount.value = data.valid
    checkStore.invalidCount.value = data.invalid
    checkStore.isChecking.value = data.is_running
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

  function startReconciliation() {
    checkStore.startReconciliation()
  }

  function stopReconciliation() {
    checkStore.stopReconciliation()
  }

  function handleSSEMessage(msg) {
    const { event } = msg
    console.log('[SSE] 收到事件:', event, msg)

    if (event === 'init') {
      if (msg.local_isp) localIsp.value = msg.local_isp
      if (msg.is_checking !== undefined) checkStore.isChecking.value = msg.is_checking
      if (msg.total !== undefined) checkStore.checkTotal.value = msg.total
      if (msg.checked !== undefined) checkStore.checkedCount.value = msg.checked
      if (msg.valid !== undefined) checkStore.validCount.value = msg.valid
      if (msg.invalid !== undefined) checkStore.invalidCount.value = msg.invalid

      if (msg.refresh_latency_running !== undefined) {
        isRefreshLatencyRunning.value = msg.refresh_latency_running
      }
      if (msg.refresh_latency_progress) {
        refreshLatencyProgress.value = msg.refresh_latency_progress
      }

      if (msg.local_isp === '未知' || msg.local_isp === '检测中...') {
        startIspCheckTimeout()
      } else {
        clearIspCheckTimeout()
      }
      return
    }

    if (event === 'isp_updated') {
      localIsp.value = msg.local_isp
      clearIspCheckTimeout()
      checkStore.addLog(`运营商检测完成：${msg.local_isp}`, 'info')
      const { toast } = useToast()
      toast.success('运营商检测完成', `当前运营商：${msg.local_isp}`)
      return
    }

    if (event === 'channel_checked') {
      checkStore.handleChannelChecked(msg)
    } else if (event === 'check_completed') {
      checkStore.completeCheckState(
        msg.total || checkStore.checkTotal.value,
        msg.valid || checkStore.validCount.value,
        msg.likely_valid || checkStore.likelyValidCount.value,
        msg.invalid || checkStore.invalidCount.value
      )
      loadAllEpg().catch(() => {})
      autoSaveResults().catch(() => {})
    } else if (event === 'check_started') {
      console.log('[SSE] check_started 事件详情:', msg)
      if (!checkStore.isChecking) {
        checkStore.startCheckState(msg.total || 0)
      }
      resultStore.reset()
    } else if (event === 'channels_loaded') {
      checkStore.handleChannelsLoaded(msg.total)
    } else if (event === 'progress_update') {
      checkStore.handleProgressUpdate(msg)
    } else if (event === 'check_stopped') {
      checkStore.stopCheckState()
    } else if (event === 'stage_changed') {
      checkStore.stage.value = msg.stage || ''
      checkStore.stageMessage.value = msg.message || ''
    } else if (event === 'fetch_started') {
      checkStore.stage.value = 'fetching'
      checkStore.stageMessage.value = `正在拉取 ${msg.total_sources || 0} 个在线源...`
      syncProgress.value = { ...syncProgress.value, is_syncing: true, stage: 'fetching_channels', total_urls: msg.total_sources || 0, current_url_index: 0, current_url_label: `正在拉取 ${msg.total_sources || 0} 个源的频道...`, started_at: syncProgress.value.started_at || Date.now() / 1000 }
    } else if (event === 'fetch_completed') {
      checkStore.stage.value = 'fetch_done'
      const fetched = msg.fetched_channels || 0
      const raw = msg.raw_channels || 0
      const dedup = msg.dedup_channels || 0
      if (dedup > 0) {
        checkStore.stageMessage.value = `拉取完成，共 ${fetched} 个唯一频道（去重前 ${raw}，跨源重复 ${dedup} 个）`
      } else {
        checkStore.stageMessage.value = `拉取完成，共 ${fetched} 个频道`
      }
      syncProgress.value = { ...syncProgress.value, is_syncing: false, stage: 'completed' }
    } else if (event === 'fetch_progress') {
      syncProgress.value = { ...syncProgress.value, current_url_index: msg.done_sources || 0, total_urls: msg.total_sources || 0, fetched_channel_count: msg.fetched_channels || 0, current_url_label: `拉取频道 ${msg.done_sources || 0}/${msg.total_sources || 0}，已获取 ${msg.fetched_channels || 0} 个` }
    } else if (event === 'health_alert') {
      const { toast } = useToast()
      const unhealthy = msg.unhealthy_sources || []
      toast.warning('源健康告警', `${unhealthy.length} 个源有效率低于阈值`)
    } else if (event === 'sync_progress') {
      syncProgress.value = { ...syncProgress.value, ...msg }
    } else if (event === 'refresh_latency_progress') {
      const incoming = msg.checked || 0
      const current = refreshLatencyProgress.value.checked || 0
      if (incoming >= current) {
        refreshLatencyProgress.value = {
          checked: msg.checked || 0,
          total: msg.total || 0,
          updated: msg.updated || 0,
        }
      }
    } else if (event === 'refresh_latency_completed') {
      refreshLatencyProgress.value = {
        checked: msg.checked || 0,
        total: msg.total || 0,
        updated: msg.updated || 0,
      }
      isRefreshLatencyRunning.value = false
    } else if (event === 'refresh_latency_failed') {
      isRefreshLatencyRunning.value = false
      const { toast } = useToast()
      toast.error('全量刷新失败', msg.error || '未知错误')
    } else if (event === 'queue_overflow') {
      const { toast } = useToast()
      toast.warning('实时更新延迟', msg.message || '部分更新被跳过，数据将在轮询时自动修正')
    }
  }

  function handleWsMessage(msg) {
    handleSSEMessage(msg)
  }

  function initSSE() {
    createSSEConnection(handleSSEMessage)
    startReconciliation()
  }

  function startIspCheckTimeout() {
    if (ispCheckTimeout) return
    ispCheckTimeout = setTimeout(async () => {
      if (localIsp.value === '未知' || localIsp.value === '检测中...') {
        checkStore.addLog('运营商检测超时，主动重试...', 'warning')
        try {
          await doRefreshIsp()
          clearIspCheckTimeout()
        } catch (e) {
          checkStore.addLog('主动重试失败：' + (e.message || '未知错误'), 'error')
        }
      }
    }, ISP_CHECK_TIMEOUT)
  }

  function clearIspCheckTimeout() {
    if (ispCheckTimeout) {
      clearTimeout(ispCheckTimeout)
      ispCheckTimeout = null
    }
  }

  async function autoSaveResults() {
    if (checkStore.checkTotal.value === 0) return
    try {
      const { data } = await saveResults()
      checkStore.markResultsSaved(data.history_id, data.saved)
      checkStore.addLog(`检测结果已自动保存到数据库 (ID: ${data.history_id}, 共 ${data.saved} 条)`, 'success')
    } catch (e) {
      checkStore.addLog('自动保存检测结果失败: ' + (e.response?.data?.detail || e.message), 'warning')
    }
  }

  async function manualSaveResults() {
    if (checkStore.checkTotal.value === 0) {
      toast.warning('无可保存结果', '请先进行检测')
      return
    }
    try {
      const { data } = await saveResults()
      checkStore.markResultsSaved(data.history_id, data.saved)
      toast.success('保存成功', `已保存 ${data.saved} 条检测结果到数据库`)
      return data
    } catch (e) {
      toast.error('保存失败', e.response?.data?.detail || e.message)
      throw e
    }
  }

  return {
    appInfo,
    localIsp,
    m3uState,
    mediaProbeStatus,
    syncProgress,
    refreshLatencyProgress,
    isRefreshLatencyRunning,
    isChecking,
    onlineSources,
    checkResults,
    showToast,
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
    handleSSEMessage,
    handleWsMessage,
    initSSE,
    startReconciliation,
    stopReconciliation,
    clearIspCheckTimeout,
    autoSaveResults,
    manualSaveResults,
  }
})

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

  let ispCheckTimeout = null
  const ISP_CHECK_TIMEOUT = 10000

  const sourceStore = useSourceStore()
  const checkStore = useCheckStore()
  const resultStore = useResultStore()

  const isChecking = computed(() => checkStore.isChecking)
  const onlineSources = computed(() => sourceStore.onlineSources)
  const checkResults = computed(() => resultStore.checkResults)

  async function fetchInfo() {
    const { data } = await getInfo()
    appInfo.value = data
    localIsp.value = data.local_isp
    checkStore.isChecking.value = data.is_checking

    if (data.local_isp === '未知' || data.local_isp === '检测中...') {
      startIspCheckTimeout()
    }
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

  function addLog(message, type = 'info') {
    checkStore.addLog(message, type)
  }

  function clearLogs() {
    checkStore.clearLogs()
  }

  function startReconciliation() {
    checkStore.startReconciliation()
  }

  function stopReconciliation() {
    checkStore.stopReconciliation()
  }

  function handleSSEMessage(msg) {
    const { event } = msg

    if (event === 'init') {
      if (msg.local_isp) localIsp.value = msg.local_isp
      if (msg.is_checking !== undefined) checkStore.isChecking.value = msg.is_checking
      if (msg.total !== undefined) checkStore.checkTotal.value = msg.total
      if (msg.checked !== undefined) checkStore.checkedCount.value = msg.checked
      if (msg.valid !== undefined) checkStore.validCount.value = msg.valid
      if (msg.invalid !== undefined) checkStore.invalidCount.value = msg.invalid

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
      addLog(`运营商检测完成：${msg.local_isp}`, 'info')
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
        msg.invalid || checkStore.invalidCount.value
      )
    } else if (event === 'check_started') {
      checkStore.startCheckState(msg.total || 0)
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
    } else if (event === 'health_alert') {
      const { toast } = useToast()
      const unhealthy = msg.unhealthy_sources || []
      toast.warning('源健康告警', `${unhealthy.length} 个源有效率低于阈值`)
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
        addLog('运营商检测超时，主动重试...', 'warning')
        try {
          await doRefreshIsp()
          clearIspCheckTimeout()
        } catch (e) {
          addLog('主动重试失败：' + (e.message || '未知错误'), 'error')
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

  return {
    appInfo,
    localIsp,
    m3uState,
    mediaProbeStatus,
    isChecking,
    onlineSources,
    checkResults,
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
    handleSSEMessage,
    handleWsMessage,
    initSSE,
    startReconciliation,
    stopReconciliation,
    clearIspCheckTimeout,
  }
})

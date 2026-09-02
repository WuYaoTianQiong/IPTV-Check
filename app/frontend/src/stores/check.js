import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getCheckProgress, getCheckState, getResultsStats } from '../api'
import { sseStatus } from '../api'
import { useToast } from '../composables/useToast'

const RECONCILIATION_INTERVAL = 2000

export const useCheckStore = defineStore('check', () => {
  const isChecking = ref(false)
  const sessionId = ref('')
  const checkTotal = ref(0)
  const checkedCount = ref(0)
  const validCount = ref(0)
  const likelyValidCount = ref(0)
  const invalidCount = ref(0)
  const downloadDone = ref(0)
  const downloadTotal = ref(0)
  const phase = ref('idle')
  const stage = ref('') // parsing | downloading | checking | finalizing
  const stageMessage = ref('')
  const startTime = ref(null)
  const lastSavedHistoryId = ref(null)
  const lastSavedCount = ref(0)
  const lastSavedAt = ref(null)

  const logs = ref([])
  const MAX_LOGS = 500

  let reconciliationTimer = null
  let _reconciliationInterval = 2000
  let _sseWasConnected = false

  // 阶段权重：解析 10% + 下载 15% + 检测 70% + 收尾 5%
  const stageWeights = {
    parsing: { weight: 10, progress: 0 },
    downloading: { weight: 15, progress: 0 },
    checking: { weight: 70, progress: 0 },
    rechecking: { weight: 5, progress: 0 },
    finalizing: { weight: 5, progress: 0 },
  }

  const progress = computed(() => {
    if (phase.value === 'completed') return 100
    if (checkTotal.value === 0) {
      if (stage.value === 'parsing') return 5
      if (stage.value === 'downloading') {
        // 下载阶段权重 15%：按真实下载完成度映射（解析后 10% 起跳 → 检测前 25%），
        // 替代固定 15%，避免"下载 0/28428 却显示 15%"的误导
        if (downloadTotal.value > 0) {
          return Math.min(10 + Math.round((downloadDone.value / downloadTotal.value) * 15), 25)
        }
        return 5
      }
      return 0
    }
    let baseProgress = 0
    if (stage.value === 'checking' || stage.value === 'rechecking' || stage.value === 'finalizing' || checkedCount.value > 0) {
      baseProgress = 25
      const checkProgress = (checkedCount.value / checkTotal.value) * 70
      baseProgress += checkProgress
    }
    if (stage.value === 'finalizing') {
      baseProgress += 5
    }
    return Math.min(Math.round(baseProgress), 100)
  })

  const validRate = computed(() => {
    if (checkedCount.value === 0) return 0
    return Math.round((validCount.value / checkedCount.value) * 100)
  })

  const currentStatus = computed(() => {
    if (!isChecking.value) return '准备就绪'
    if (stageMessage.value) return stageMessage.value
    if (checkTotal.value === 0) return '正在加载直播源...'
    if (checkedCount.value === 0) return `已加载 ${checkTotal.value} 个频道，正在检测...`
    if (checkedCount.value >= checkTotal.value && isChecking.value) {
      if (stage.value === 'rechecking') {
        const recheckRemaining = invalidCount.value + likelyValidCount.value
        return `正在复检无效频道... (${recheckRemaining} 个待复检)`
      }
      if (stage.value === 'finalizing') {
        return '正在生成报告...'
      }
      return `首轮检测完成，正在处理结果...`
    }
    return `检测中: ${checkedCount.value}/${checkTotal.value}`
  })

  const eta = computed(() => {
    if (!isChecking.value || checkedCount.value === 0 || checkTotal.value === 0) return null
    const elapsed = Date.now() - (startTime.value || Date.now())
    const avgTime = elapsed / checkedCount.value
    let remaining = checkTotal.value - checkedCount.value
    if (checkedCount.value >= checkTotal.value && isChecking.value) {
      if (stage.value === 'rechecking') {
        const recheckRemaining = invalidCount.value
        remaining = recheckRemaining
      } else if (stage.value === 'finalizing') {
        return '即将完成'
      } else {
        return '即将完成'
      }
    }
    if (remaining <= 0) return '即将完成'
    const ms = avgTime * remaining
    if (ms < 60000) return `${Math.round(ms / 1000)}秒`
    return `${Math.round(ms / 60000)}分钟`
  })

  function resetCheckState() {
    isChecking.value = false
    sessionId.value = ''
    checkTotal.value = 0
    checkedCount.value = 0
    validCount.value = 0
    likelyValidCount.value = 0
    invalidCount.value = 0
    phase.value = 'idle'
    startTime.value = null
    lastSavedHistoryId.value = null
    lastSavedCount.value = 0
    lastSavedAt.value = null
  }

  function startCheckState(total = 0) {
    isChecking.value = true
    checkTotal.value = total
    checkedCount.value = 0
    validCount.value = 0
    likelyValidCount.value = 0
    invalidCount.value = 0
    phase.value = 'checking'
    stage.value = 'parsing'
    stageMessage.value = '正在解析直播源...'
    startTime.value = Date.now()
    startReconciliation()
  }

  function completeCheckState(total, valid, likelyValid, invalid) {
    isChecking.value = false
    checkTotal.value = total
    checkedCount.value = total
    validCount.value = valid
    likelyValidCount.value = likelyValid || 0
    invalidCount.value = invalid
    phase.value = 'completed'
    stage.value = ''
    stageMessage.value = ''
    stopReconciliation()
  }

  function stopCheckState() {
    isChecking.value = false
    phase.value = 'stopped'
    stage.value = ''
    stageMessage.value = ''
    stopReconciliation()
  }

  function handleChannelChecked(msg) {
    checkedCount.value++
    if (msg.is_valid) validCount.value++
    else invalidCount.value++
  }

  function handleChannelsLoaded(total) {
    checkTotal.value = total
    stage.value = 'checking'
    stageMessage.value = `正在检测 ${total} 个频道...`
  }

  function handleProgressUpdate(data) {
    checkTotal.value = data.total || checkTotal.value
    checkedCount.value = data.checked || 0
    validCount.value = data.valid || 0
    likelyValidCount.value = data.likely_valid || 0
    invalidCount.value = data.invalid || 0
  }

  function startReconciliation() {
    if (reconciliationTimer) return
    reconciliationTimer = setInterval(async () => {
      try {
        const { data } = await getCheckState()
        const sseOk = sseStatus.connected

        if (data.download_total != null) downloadTotal.value = data.download_total
        if (data.download_done != null) downloadDone.value = data.download_done

        if (data.session_id) sessionId.value = data.session_id

        if (data.is_running && !isChecking.value) {
          isChecking.value = true
          phase.value = data.phase || 'checking'
        }

        // 阶段文案/进度以 API 为权威同步：SSE 可能错过事件、重连或消息丢失，
        // 轮询兜底必须覆盖，否则页面会停留在旧阶段（如一直显示"正在解析本地文件..."）
        if (data.stage && data.stage !== stage.value) {
          stage.value = data.stage
        }
        if (data.stage_message && data.stage_message !== stageMessage.value) {
          stageMessage.value = data.stage_message
        }

        if (!sseOk) {
          if (data.checked >= checkedCount.value) {
            checkTotal.value = data.total
            checkedCount.value = data.checked
            validCount.value = data.valid
            likelyValidCount.value = data.likely_valid || 0
            invalidCount.value = data.invalid
          }
          isChecking.value = data.is_running
        }

        if (data.phase === 'completed') {
          if (phase.value !== 'completed') {
            phase.value = 'completed'
            isChecking.value = false
            checkTotal.value = data.total || checkTotal.value
            checkedCount.value = data.checked || checkedCount.value
            validCount.value = data.valid || validCount.value
            likelyValidCount.value = data.likely_valid || likelyValidCount.value
            invalidCount.value = data.invalid || invalidCount.value
            stage.value = ''
            stageMessage.value = ''
          }
          stopReconciliation()
        } else if (!data.is_running && isChecking.value) {
          isChecking.value = false
          phase.value = 'completed'
          checkTotal.value = data.total
          checkedCount.value = data.checked
          validCount.value = data.valid
          likelyValidCount.value = data.likely_valid || 0
          invalidCount.value = data.invalid
          stage.value = ''
          stageMessage.value = ''
          stopReconciliation()
        } else if (!data.is_running && !isChecking.value && checkedCount.value === 0) {
          stopReconciliation()
        }
      } catch {}
    }, _reconciliationInterval)
  }

  function stopReconciliation() {
    if (reconciliationTimer) {
      clearInterval(reconciliationTimer)
      reconciliationTimer = null
    }
  }

  function markResultsSaved(historyId, count) {
    lastSavedHistoryId.value = historyId
    lastSavedCount.value = count
    lastSavedAt.value = Date.now()
  }

  function addLog(message, type = 'info') {
    logs.value.push({ message, type, time: Date.now() })
    if (logs.value.length > MAX_LOGS) {
      logs.value = logs.value.slice(-MAX_LOGS)
    }
  }

  function clearLogs() {
    logs.value = []
  }

  return {
    isChecking,
    sessionId,
    checkTotal,
    checkedCount,
    validCount,
    likelyValidCount,
    invalidCount,
    downloadDone,
    downloadTotal,
    phase,
    stage,
    stageMessage,
    startTime,
    progress,
    validRate,
    currentStatus,
    eta,
    lastSavedHistoryId,
    lastSavedCount,
    lastSavedAt,
    logs,
    addLog,
    clearLogs,
    resetCheckState,
    startCheckState,
    completeCheckState,
    stopCheckState,
    handleChannelChecked,
    handleChannelsLoaded,
    handleProgressUpdate,
    startReconciliation,
    stopReconciliation,
    markResultsSaved,
  }
})

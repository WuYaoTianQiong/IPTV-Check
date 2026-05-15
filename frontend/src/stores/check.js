import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getCheckProgress, getResultsStats } from '../api'
import { useToast } from '../composables/useToast'

const RECONCILIATION_INTERVAL = 2000

export const useCheckStore = defineStore('check', () => {
  const isChecking = ref(false)
  const checkTotal = ref(0)
  const checkedCount = ref(0)
  const validCount = ref(0)
  const invalidCount = ref(0)
  const logs = ref([])
  const phase = ref('idle')
  const stage = ref('') // parsing | downloading | checking | finalizing
  const stageMessage = ref('')
  const startTime = ref(null)

  let reconciliationTimer = null
  let _reconciliationInterval = 2000

  // 阶段权重：解析 10% + 下载 15% + 检测 70% + 收尾 5%
  const stageWeights = {
    parsing: { weight: 10, progress: 0 },
    downloading: { weight: 15, progress: 0 },
    checking: { weight: 70, progress: 0 },
    finalizing: { weight: 5, progress: 0 },
  }

  const progress = computed(() => {
    if (checkTotal.value === 0) {
      // 没有总数时，按阶段显示固定进度
      if (stage.value === 'parsing') return 5
      if (stage.value === 'downloading') return 15
      return 0
    }
    // 阶段加权进度
    let baseProgress = 0
    if (stage.value === 'checking' || stage.value === 'finalizing' || checkedCount.value > 0) {
      baseProgress = 25 // parsing + downloading 完成
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
    return `检测中: ${checkedCount.value}/${checkTotal.value}`
  })

  const eta = computed(() => {
    if (!isChecking.value || checkedCount.value === 0 || checkTotal.value === 0) return null
    const elapsed = Date.now() - (startTime.value || Date.now())
    const avgTime = elapsed / checkedCount.value
    const remaining = checkTotal.value - checkedCount.value
    const ms = avgTime * remaining
    if (ms < 60000) return `${Math.round(ms / 1000)}秒`
    return `${Math.round(ms / 60000)}分钟`
  })

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

  function resetCheckState() {
    isChecking.value = false
    checkTotal.value = 0
    checkedCount.value = 0
    validCount.value = 0
    invalidCount.value = 0
    phase.value = 'idle'
    startTime.value = null
  }

  function startCheckState(total = 0) {
    isChecking.value = true
    checkTotal.value = total
    checkedCount.value = 0
    validCount.value = 0
    invalidCount.value = 0
    logs.value = []
    phase.value = 'checking'
    stage.value = 'parsing'
    stageMessage.value = '正在解析直播源...'
    startTime.value = Date.now()
    addLog('检测开始', 'info')
    startReconciliation()
  }

  function completeCheckState(total, valid, invalid) {
    isChecking.value = false
    checkTotal.value = total
    checkedCount.value = total
    validCount.value = valid
    invalidCount.value = invalid
    phase.value = 'completed'
    stage.value = ''
    stageMessage.value = ''
    addLog(`检测完成 | 总计: ${total} | 有效: ${valid} | 无效: ${invalid}`, 'info')
    const rate = total ? Math.round((valid / total) * 100) : 0
    const { toast } = useToast()
    toast.success('检测完成', `共 ${total} 个频道，有效 ${valid}，有效率 ${rate}%`)
    stopReconciliation()
  }

  function stopCheckState() {
    isChecking.value = false
    phase.value = 'stopped'
    stage.value = ''
    stageMessage.value = ''
    addLog('检测已停止', 'warning')
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
    addLog(`共加载 ${total} 个频道，开始检测`, 'info')
  }

  function handleProgressUpdate(data) {
    checkTotal.value = data.total || checkTotal.value
    checkedCount.value = data.checked || 0
    validCount.value = data.valid || 0
    invalidCount.value = data.invalid || 0
  }

  function startReconciliation() {
    if (reconciliationTimer) return
    reconciliationTimer = setInterval(async () => {
      try {
        const { data } = await getCheckProgress()
        if (
          data.total !== checkTotal.value ||
          data.checked !== checkedCount.value ||
          data.valid !== validCount.value
        ) {
          checkTotal.value = data.total
          checkedCount.value = data.checked
          validCount.value = data.valid
          invalidCount.value = data.invalid
          isChecking.value = data.is_running
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

  return {
    isChecking,
    checkTotal,
    checkedCount,
    validCount,
    invalidCount,
    logs,
    phase,
    stage,
    stageMessage,
    startTime,
    progress,
    validRate,
    currentStatus,
    eta,
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
  }
})

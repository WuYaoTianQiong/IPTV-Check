import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getInfo,
  getIsp,
  refreshIsp,
  getOnlineSources,
  getResults,
  getResultsStats,
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
      
      // 每10条记录一次详细日志，每50条记录一次汇总
      if (checkedCount.value % 10 === 0) {
        const rate = validCount.value / checkedCount.value * 100
        addLog(`进度 ${checkedCount.value}/${checkTotal.value} | 有效: ${validCount.value} | 无效: ${invalidCount.value} | 有效率: ${rate.toFixed(1)}%`, 'info')
      } else if (msg.is_valid && checkedCount.value % 3 === 0) {
        // 每检测3个有效频道时，显示频道名称（给用户反馈）
        addLog(`✓ ${msg.name} [${msg.latency || '-'}]`, 'success')
      } else if (checkedCount.value % 20 === 0) {
        // 每20个频道记录一次简短进度
        addLog(`已检测 ${checkedCount.value}/${checkTotal.value}`, 'info')
      }
    } else if (event === 'check_completed') {
      isChecking.value = false
      // 不使用后端传来的统计数据，保持前端实时累加的结果
      // 后端发送时可能存在数据未完全同步的问题
      addLog(`检测完成 | 总计: ${checkTotal.value} | 有效: ${validCount.value} | 无效: ${invalidCount.value}`, 'info')
    } else if (event === 'check_started') {
      isChecking.value = true
      checkTotal.value = msg.total || 0
      checkedCount.value = 0
      validCount.value = 0
      invalidCount.value = 0
      if (logs.value.length > 0 && logs.value[logs.value.length - 1].message.includes('正在启动')) {
        logs.value.pop()
      }
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
    progress,
    validRate,
    currentStatus,
    fetchInfo,
    fetchIsp,
    doRefreshIsp,
    fetchOnlineSources,
    fetchResults,
    fetchStats,
    addLog,
    clearLogs,
    handleWsMessage,
  }
})

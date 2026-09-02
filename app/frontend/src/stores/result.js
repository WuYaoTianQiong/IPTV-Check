import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getResults, getResultsStats, getCheckHistory } from '../api'

export const useResultStore = defineStore('result', () => {
  const checkResults = ref([])
  const resultsPage = ref(1)
  const resultsTotal = ref(0)
  // 当前会话+当前筛选条件下各 tab 的计数（由后端 /api/results 返回），
  // 用于 tab 栏/标题行的口径统一，避免与 checkStore（最新检测会话）混淆。
  const tabCounts = ref(null)
  const resultsPerPage = ref(50)
  try {
    const saved = localStorage.getItem('iptv_result_per_page')
    if (saved) resultsPerPage.value = parseInt(saved, 10)
  } catch {}
  const currentTab = ref('all')
  try {
    const saved = localStorage.getItem('iptv_result_tab')
    if (saved) currentTab.value = saved
  } catch {}

  const searchQuery = ref('')
  try {
    const saved = localStorage.getItem('iptv_result_search_query')
    if (saved) searchQuery.value = saved
  } catch {}

  const sortOrder = ref('best')
  try {
    const saved = localStorage.getItem('iptv_result_sort_order')
    if (saved) sortOrder.value = saved
  } catch {}

  const isLoading = ref(false)
  const error = ref(null)
  const history = ref([])
  const selectedSessionId = ref('')
  try {
    const saved = localStorage.getItem('iptv_result_session_id')
    if (saved) selectedSessionId.value = saved
  } catch {}

  const isHistoryLoading = ref(false)

  watch(currentTab, (val) => {
    try { localStorage.setItem('iptv_result_tab', val) } catch {}
  })

  watch(searchQuery, (val) => {
    try { localStorage.setItem('iptv_result_search_query', val) } catch {}
  })

  watch(selectedSessionId, (val) => {
    try { localStorage.setItem('iptv_result_session_id', val) } catch {}
  })

  // 请求序号：静默刷新与手动刷新并发时，丢弃过期响应防止旧数据覆盖新数据
  let _fetchSeq = 0

  /**
   * 拉取结果列表。
   * @param {object} params 筛选/分页参数
   * @param {{silent?: boolean}} opts silent=true 时不置 isLoading（不闪骨架屏），
   *        用于检测中/复检中的后台静默刷新，避免整表被骨架屏打断无法查看。
   */
  async function fetchResults(params = {}, opts = {}) {
    const silent = !!(opts && opts.silent)
    const seq = ++_fetchSeq
    if (!silent) {
      isLoading.value = true
      error.value = null
    }
    try {
      const baseParams = {
        tab: currentTab.value,
        page: resultsPage.value,
        per_page: resultsPerPage.value,
        search: searchQuery.value,
        sort: sortOrder.value,
        ...params,
      }
      // 显式传入 session_id 时优先（实时跟随当前检测会话），否则用历史选中会话
      const hasExplicitSession = Object.prototype.hasOwnProperty.call(params, 'session_id')
      if (!hasExplicitSession && selectedSessionId.value) {
        baseParams.session_id = selectedSessionId.value
      }
      const { data } = await getResults(baseParams)
      if (seq !== _fetchSeq) return null // 已有更新的请求，丢弃本次过期响应
      checkResults.value = data.items || []
      resultsTotal.value = data.total || 0
      tabCounts.value = data.tab_counts || null
      return data
    } catch (e) {
      if (seq !== _fetchSeq) throw e
      error.value = e.message || '获取结果失败'
      throw e
    } finally {
      if (seq === _fetchSeq && !silent) isLoading.value = false
    }
  }

  async function fetchHistory() {
    isHistoryLoading.value = true
    try {
      const { data } = await getCheckHistory(50)
      history.value = Array.isArray(data) ? data : []
      if (history.value.length > 0 && !selectedSessionId.value) {
        selectedSessionId.value = history.value[0].session_id
      }
    } catch (e) {
      console.warn('加载历史记录失败:', e)
      history.value = []
    } finally {
      isHistoryLoading.value = false
    }
  }

  function selectSession(sessionId) {
    selectedSessionId.value = sessionId
    resultsPage.value = 1
  }

  function setTab(tab) {
    currentTab.value = tab
    resultsPage.value = 1
  }

  function setSearch(query) {
    searchQuery.value = query
    resultsPage.value = 1
  }

  function setPage(page) {
    resultsPage.value = page
  }

  function setSort(sort) {
    sortOrder.value = sort
    try { localStorage.setItem('iptv_result_sort_order', sort) } catch {}
  }

  function reset() {
    checkResults.value = []
    resultsPage.value = 1
    resultsTotal.value = 0
    tabCounts.value = null
    currentTab.value = 'all'
    searchQuery.value = ''
    isLoading.value = false
    error.value = null
    history.value = []
    selectedSessionId.value = ''
    isHistoryLoading.value = false
  }

  return {
    checkResults,
    resultsPage,
    resultsTotal,
    tabCounts,
    resultsPerPage,
    currentTab,
    searchQuery,
    sortOrder,
    isLoading,
    error,
    history,
    selectedSessionId,
    isHistoryLoading,
    fetchResults,
    fetchHistory,
    selectSession,
    setTab,
    setSearch,
    setPage,
    setSort,
    reset,
  }
})
